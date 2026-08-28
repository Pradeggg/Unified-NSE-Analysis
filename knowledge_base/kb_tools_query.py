"""Unified query interface: BM25 skills index + optional ChromaDB vector search.

This is the single entry point for coding assistants (Claude, Codex, Cursor)
to query the Agent Adda knowledge base before searching source code.

Two search layers
-----------------
Layer 1 — BM25 (always on, < 10 ms, zero LLM calls)
    Covers: all 138 launcher entries, 5 skill YAMLs, 9 project skills,
            9 MCP tools, and curated workflow entries.

Layer 2 — ChromaDB semantic search (optional, requires embeddings)
    Covers: financial documents (SEBI / RBI / CRISIL / broker research)
    Activated by: --semantic flag, or hybrid=True in API calls.

Usage (CLI)
-----------
    # BM25 only (default, fastest)
    python -m knowledge_base query "how to run daily pipeline"
    python -m knowledge_base query "chart RELIANCE" --format context
    python -m knowledge_base query "stage 2 screener" --top 8 --format json

    # Hybrid (BM25 + vector if available)
    python -m knowledge_base query "fundamental analysis" --hybrid

    # Token usage stats
    python -m knowledge_base tokens
    python -m knowledge_base tokens --days 30

Usage (Python API)
------------------
    from knowledge_base.kb_tools_query import query_tools
    result = query_tools("run daily pipeline", k=5)
    print(result["context_block"])  # inject into prompt
    print(result["token_savings"])  # estimated tokens saved
"""
from __future__ import annotations

import json
import time
from typing import Any

from .skills_registry import get_registry
from .token_tracker import QueryTimer, count_tokens, get_tracker

# ── output formats ────────────────────────────────────────────────────────────
FORMAT_TEXT    = "text"
FORMAT_JSON    = "json"
FORMAT_CONTEXT = "context"        # full markdown context block for prompt injection
FORMAT_COMPACT = "context-compact" # one-liner per entry, fits tighter token budgets


def _format_text(hits: list[dict], query: str) -> str:
    if not hits:
        return f"No results for '{query}'"
    lines = [f"KB results for: {query}\n"]
    for i, h in enumerate(hits, 1):
        e = h["entry"]
        lines.append(
            f"[{i}] score={h['score']:.2f}  {e.get('category','')} | {e.get('id','')}"
        )
        lines.append(f"     {e.get('description','')[:120]}")
        if e.get("cli"):
            lines.append(f"     CLI: {e['cli'][:120]}")
        lines.append("")
    return "\n".join(lines)


def _format_json(hits: list[dict], query: str) -> str:
    return json.dumps({
        "query": query,
        "count": len(hits),
        "results": [
            {
                "rank":         i + 1,
                "score":        round(h["score"], 4),
                "id":           h["entry"].get("id"),
                "title":        h["entry"].get("title") or h["entry"].get("id"),
                "category":     h["entry"].get("category"),
                "description":  h["entry"].get("description", "")[:300],
                "cli":          h["entry"].get("cli", ""),
                "tags":         h["entry"].get("tags", []),
                "input_patterns": h["entry"].get("input_patterns", [])[:5],
                "source":       h["entry"].get("source", ""),
                "source_file_tokens": h["entry"].get("source_file_tokens", 0),
            }
            for i, h in enumerate(hits)
        ],
    }, indent=2, ensure_ascii=False)


def _merge_vector_hits(
    bm25_hits: list[dict],
    vector_hits: list[dict],
    total_k: int,
) -> list[dict]:
    """Merge BM25 and vector results, dedup on id, re-rank by combined score."""
    seen: dict[str, dict] = {}
    # normalise scores to [0,1]
    bm25_max = max((h["score"] for h in bm25_hits), default=1.0) or 1.0
    vec_max  = max((h["score"] for h in vector_hits), default=1.0) or 1.0
    for h in bm25_hits:
        eid = h["entry"].get("id", "")
        seen[eid] = {**h, "combined": h["score"] / bm25_max * 0.6}
    for h in vector_hits:
        eid = h.get("metadata", {}).get("id") or h.get("id", "")
        norm = h["score"] / vec_max * 0.4
        if eid in seen:
            seen[eid]["combined"] += norm
        else:
            # wrap vector hit into entry-like shape
            meta = h.get("metadata", {})
            seen[eid] = {
                "score":    h["score"],
                "combined": norm,
                "entry": {
                    "id":          meta.get("source_id", eid),
                    "title":       meta.get("hub_label", eid),
                    "description": h.get("text", "")[:300],
                    "category":    "financial_doc",
                    "tags":        [meta.get("category", "")],
                    "cli":         "",
                    "source":      meta.get("source_url", ""),
                    "source_file_tokens": 0,
                },
            }
    return sorted(seen.values(), key=lambda x: x["combined"], reverse=True)[:total_k]


# ── main query function ────────────────────────────────────────────────────────

def query_tools(
    query: str,
    k: int = 5,
    fmt: str = FORMAT_CONTEXT,
    hybrid: bool = False,
    web: bool = False,
    web_results: list[dict] | None = None,
    max_tokens: int = 2000,
    caller: str = "",
    session_id: str = "",
) -> dict[str, Any]:
    """Query the Agent Adda KB. Returns a result dict with context_block + metadata.

    Parameters
    ----------
    query : str
        Natural-language query.
    k : int
        Number of results to return.
    fmt : str
        Output format: 'text' | 'json' | 'context' | 'context-compact'.
    hybrid : bool
        If True, augment BM25 with ChromaDB semantic search (requires embedding model).
    web : bool
        If True, append a live web-search block.  When running inside Claude Code,
        pass pre-fetched Claude WebSearch results via ``web_results`` instead — they
        are richer (actual numbers) than the DuckDuckGo fallback.
    web_results : list[dict] | None
        Pre-fetched web search results to inject directly — bypasses DuckDuckGo.
        Each dict must have at least ``title`` and ``snippet``; ``url`` and
        ``domain`` are optional but shown in the output block.
        **When provided, sets web=True automatically.**
        Intended for Claude Code MCP callers that have already run WebSearch:

            # Claude Code pattern:
            hits = [{"title": "...", "url": "...", "snippet": "..."}]
            result = query_tools(query, web_results=hits)

    max_tokens : int
        Soft token budget for the context_block.
    caller : str
        Identifier for the calling assistant ('claude' | 'codex' | 'cli' | 'mcp').
    session_id : str
        Optional session identifier for grouping queries.

    Returns
    -------
    dict with keys:
        context_block      : str  — formatted output (inject into prompt)
        hits               : list — raw hits for programmatic use
        token_savings      : int  — estimated tokens saved vs code search
        tokens_in          : int  — tokens in this query
        tokens_out         : int  — tokens in the response
        latency_ms         : float
        search_method      : str  — 'bm25' | 'bm25+web' | 'bm25+web(claude)'
        log_id             : int  — query_log row id
        web_hits           : list — web search results (empty unless web=True)
        web_backend        : str  — 'claude' | 'ddg' | 'injected' | ''
    """
    # Injected results implicitly enable web layer
    if web_results is not None:
        web = True
    reg   = get_registry()
    timer = QueryTimer(query, search_method="bm25", caller=caller, session_id=session_id)
    timer.__enter__()

    # ── Layer 1: BM25 ────────────────────────────────────────────────────────
    bm25_hits = reg.search(query, k=k)
    hits = bm25_hits
    search_method = "bm25"
    llm_tokens_used = 0

    # ── Layer 2: Vector (optional) ───────────────────────────────────────────
    if hybrid:
        try:
            from .vector_store import KBVectorStore  # noqa: WPS433
            t_vec0 = time.perf_counter()
            vs   = KBVectorStore()
            vec_hits = vs.query(query, k=k)
            vec_ms = (time.perf_counter() - t_vec0) * 1000
            # Estimate embedding tokens (rough: 1 token per word)
            llm_tokens_used = count_tokens(query)
            hits = _merge_vector_hits(bm25_hits, vec_hits, k)
            search_method = "hybrid"
        except Exception:
            pass  # fall back to bm25-only silently

    # ── format output ────────────────────────────────────────────────────────
    if fmt == FORMAT_JSON:
        output = _format_json(hits, query)
    elif fmt == FORMAT_TEXT:
        output = _format_text(hits, query)
    elif fmt == FORMAT_COMPACT:
        output = reg.context_block(query, k=k, max_tokens=max_tokens, compact=True)
        # Override hits with fresh search for compact (same results, different render)
    else:
        output = reg.context_block(query, k=k, max_tokens=max_tokens, compact=False)

    # ── Layer 3: Web search (optional) ───────────────────────────────────────
    web_hits: list[dict] = []
    web_tokens = 0
    web_backend = ""
    if web:
        try:
            from .web_search import format_web_block, estimate_web_tokens, web_search  # noqa: WPS433

            if web_results is not None:
                # Pre-fetched from Claude WebSearch — richer than DuckDuckGo
                web_hits   = list(web_results)
                web_backend = "injected"
                label = "claude"
            else:
                # Standalone fallback: DuckDuckGo HTML scraper
                web_hits   = web_search(query, max_results=5)
                web_backend = "ddg"
                label = "ddg"

            web_block  = format_web_block(web_hits, query)
            web_tokens = estimate_web_tokens(web_hits)
            if fmt not in (FORMAT_JSON,):
                output = output + "\n\n" + web_block
            search_method = f"{search_method}+web({label})"
            llm_tokens_used += web_tokens
        except Exception as exc:
            note = f"\n\n<!-- web search skipped: {exc} -->"
            if fmt not in (FORMAT_JSON,):
                output += note

    # ── token savings: sum source_file_tokens for top results ───────────────
    total_source_tokens = 0
    deduped_sources: set[str] = set()
    for h in hits[:k]:
        e = h.get("entry", {}) if isinstance(h.get("entry"), dict) else {}
        sft = e.get("source_file_tokens", 0)
        src = e.get("source", "")
        if src and src not in deduped_sources:
            total_source_tokens += sft
            deduped_sources.add(src)

    log_rec = timer.finish(
        context_block=output,
        entries_returned=len(hits),
        source_file_tokens=total_source_tokens,
        llm_tokens_used=llm_tokens_used,
    )

    return {
        "context_block":  output,
        "hits":           hits,
        "token_savings":  log_rec.get("estimated_savings", 0),
        "tokens_in":      log_rec.get("tokens_in", 0),
        "tokens_out":     log_rec.get("tokens_out", 0),
        "latency_ms":     log_rec.get("latency_ms", 0.0),
        "search_method":  search_method,
        "log_id":         log_rec.get("id"),
        "web_hits":       web_hits,
        "web_backend":    web_backend,
    }


# ── convenience wrappers ──────────────────────────────────────────────────────

def get_context(query: str, k: int = 5, compact: bool = False, **kw: Any) -> str:
    """Return a context block string ready to inject into any prompt."""
    fmt = FORMAT_COMPACT if compact else FORMAT_CONTEXT
    return query_tools(query, k=k, fmt=fmt, **kw)["context_block"]


def get_json(query: str, k: int = 5, **kw: Any) -> str:
    """Return JSON string of results for programmatic use."""
    return query_tools(query, k=k, fmt=FORMAT_JSON, **kw)["context_block"]
