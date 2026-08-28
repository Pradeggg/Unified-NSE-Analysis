#!/usr/bin/env python3
"""Dependency-free stdio MCP server for the bounded Agent Adda tool surface."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, BinaryIO


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from terminal.tools import TOOL_REGISTRY, call_tool  # noqa: E402


SERVER_NAME = "agent-adda-finance"
SERVER_VERSION = "1.0.0"
PROTOCOL_VERSION = "2024-11-05"
EXPOSED_TOOLS = (
    "query_kb_tools",
    "render_fundamental_analysis_report",
    "list_agent_adda_skills",
    "find_agent_adda_skills",
    "execute_agent_adda_skill",
    "sync_research_sources",
    "ingest_news_feeds",
    "search_evidence",
    "build_evidence_pack",
    "ingest_company_filings",
    "ingest_company_concalls",
)

# PG 2026-08-25: KB query tool — separate from TOOL_REGISTRY (no terminal dep)
_KB_TOOL = {
    "name": "query_kb_tools",
    "description": (
        "Query the Agent Adda Knowledge Base for skills, commands, tools, and workflows. "
        "Call this FIRST when you need to know HOW to do something in Agent Adda — "
        "run the pipeline, build a chart, screen for stocks, set up Ollama, etc. "
        "Returns a markdown context block with ranked results, exact CLI commands, "
        "ordering rules, and token-savings metadata. "
        "Faster than reading source files: < 100 ms, zero LLM calls."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Natural-language question (e.g. 'how to run daily pipeline', 'chart RELIANCE', 'stage 2 screener')"
            },
            "top_k": {
                "type": "integer",
                "default": 5,
                "description": "Number of results to return (default 5, max 10)"
            },
            "fmt": {
                "type": "string",
                "default": "context",
                "enum": ["context", "context-compact", "json", "text"],
                "description": "'context' for prompt-ready markdown (default), 'json' for machine-readable, 'context-compact' for tight token budgets"
            },
            "web": {
                "type": "boolean",
                "default": False,
                "description": "Append live web results. If web_results is also provided, uses those directly (Claude WebSearch). Otherwise falls back to DuckDuckGo (~1–3s)."
            },
            "web_results": {
                "type": "array",
                "description": "Pre-fetched Claude WebSearch results to inject — bypasses DuckDuckGo entirely. Each item: {title, url, snippet}. Use this when calling from Claude Code after running WebSearch natively.",
                "items": {
                    "type": "object",
                    "properties": {
                        "title":   {"type": "string"},
                        "url":     {"type": "string"},
                        "snippet": {"type": "string"}
                    }
                }
            }
        },
        "required": ["query"]
    }
}

_SYNC_RESEARCH_SOURCES_TOOL = {
    "name": "sync_research_sources",
    "description": (
        "Sync curated research sources from config/research_sources.yml into PostgreSQL "
        "(company_intel.research_sources). Idempotent upsert keyed by (source_kind, source_url)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "config_path": {
                "type": "string",
                "default": "config/research_sources.yml",
                "description": "Workspace-relative path to the curated sources YAML file."
            },
            "dry_run": {
                "type": "boolean",
                "default": False,
                "description": "If true, reads config but does not write to PostgreSQL."
            },
        },
        "required": [],
    },
}

_INGEST_NEWS_FEEDS_TOOL = {
    "name": "ingest_news_feeds",
    "description": (
        "Fetch active RSS/Atom feeds from PostgreSQL (company_intel.research_sources) and ingest "
        "feed entries into company_intel.source_documents + company_intel.evidence_chunks. "
        "Stores titles + short summaries as evidence (not full articles)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "max_items_per_feed": {
                "type": "integer",
                "default": 25,
                "description": "Max items ingested per feed (1–100)."
            },
            "since_days": {
                "type": "integer",
                "default": 7,
                "description": "Only ingest entries newer than N days when published_at is available (0–30)."
            },
            "sleep_ms": {
                "type": "integer",
                "default": 250,
                "description": "Politeness delay between feeds (0–2000 ms)."
            },
            "dry_run": {
                "type": "boolean",
                "default": False,
                "description": "If true, simulates ingestion without writing to PostgreSQL."
            },
        },
        "required": [],
    },
}

_SEARCH_EVIDENCE_TOOL = {
    "name": "search_evidence",
    "description": (
        "Lexical evidence search over company_intel.evidence_chunks using PostgreSQL FTS. "
        "Returns an evidence pack: top matching passages with source, tier, and dates."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "FTS query (natural language)."},
            "symbol": {"type": "string", "default": "", "description": "Optional NSE symbol filter."},
            "include_market_wide": {
                "type": "boolean",
                "default": True,
                "description": "If symbol is set, also include symbol='' market-wide evidence."
            },
            "source_tier_max": {
                "type": "integer",
                "default": 4,
                "description": "Filter by authority tier (1–4)."
            },
            "limit": {"type": "integer", "default": 12, "description": "Max passages (1–50)."},
            "days": {"type": "integer", "default": 0, "description": "If >0, restrict to last N days (1–365)."},
        },
        "required": ["query"],
    },
}

_BUILD_EVIDENCE_PACK_TOOL = {
    "name": "build_evidence_pack",
    "description": (
        "Run multi-pass evidence retrieval (broad + freshness + authority sweeps) using "
        "dimension templates from config/evidence_dimensions.yml. Returns a structured "
        "evidence pack grouped by source tier for report generation."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "symbol": {"type": "string", "description": "NSE symbol (e.g., HDFCBANK)"},
            "sector_overlay": {
                "type": "string",
                "default": "",
                "description": "Optional overlay key: banks_nbfc, infra_shipping, defence, pharma, auto",
            },
            "dimensions": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional list of dimension keys (default: all).",
            },
            "days_passes": {
                "type": "array",
                "items": {"type": "integer"},
                "default": [0, 7, 30, 90],
                "description": "Freshness passes (days).",
            },
            "tier_passes": {
                "type": "array",
                "items": {"type": "integer"},
                "default": [1, 2, 3, 4],
                "description": "Authority tier passes (1..4).",
            },
            "limit_per_query": {"type": "integer", "default": 10, "description": "Max results per query (1..25)."},
            "include_market_wide": {"type": "boolean", "default": True, "description": "Include symbol='' evidence."},
            "store_run": {
                "type": "boolean",
                "default": False,
                "description": "If true, persist the retrieval run to company_intel.evidence_pack_runs."
            },
            "config_path": {
                "type": "string",
                "default": "config/evidence_dimensions.yml",
                "description": "Path to dimension config YAML (workspace-relative).",
            },
        },
        "required": ["symbol"],
    },
}

_INGEST_COMPANY_FILINGS_TOOL = {
    "name": "ingest_company_filings",
    "description": (
        "Discover and ingest company financial-result filings (NSE/BSE/Screener candidates) into "
        "company_intel.source_documents + company_intel.evidence_chunks as Tier-1 evidence. "
        "Downloads PDFs to data/filings_evidence/ and chunks them for FTS."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "symbol": {"type": "string", "description": "NSE symbol (e.g., HDFCBANK)"},
            "max_docs": {"type": "integer", "default": 3, "description": "Max filings to ingest (1–10)."},
            "period": {"type": "string", "default": "latest_results", "description": "Storage bucket label (e.g., latest_results)."},
            "force_download": {"type": "boolean", "default": False, "description": "Force re-download even if cached."},
            "dry_run": {"type": "boolean", "default": False, "description": "Discover only; do not download or write to PG."},
        },
        "required": ["symbol"],
    },
}

_INGEST_COMPANY_CONCALLS_TOOL = {
    "name": "ingest_company_concalls",
    "description": (
        "Ingest latest concall transcript PDFs (via Screener.in concalls list) into "
        "company_intel.source_documents + company_intel.evidence_chunks as Tier-1 evidence. "
        "Downloads PDFs to data/concall_evidence/ and chunks them for FTS."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "symbol": {"type": "string", "description": "NSE symbol (e.g., HDFCBANK)"},
            "max_docs": {"type": "integer", "default": 3, "description": "Max concalls to ingest (1–10)."},
            "force_download": {"type": "boolean", "default": False, "description": "Force re-download even if cached."},
            "dry_run": {"type": "boolean", "default": False, "description": "Discover only; do not download or write to PG."},
        },
        "required": ["symbol"],
    },
}


def _call_kb(arguments: dict) -> str:
    """Handle query_kb_tools calls without going through TOOL_REGISTRY.

    Web search priority
    -------------------
    1. ``web_results`` key present → use injected results (Claude WebSearch, best quality)
    2. ``web=true``, no ``web_results`` → fall back to DuckDuckGo scraper (~1–3 s)
    3. Neither → KB-only (BM25, < 50 ms)

    Claude Code pattern (preferred)::

        # Step 1: run WebSearch tool natively in Claude Code
        hits = WebSearch("RELIANCE Q1 FY27 results")
        # Step 2: pass results into query_kb_tools
        result = query_kb_tools(
            query="company story RELIANCE",
            web_results=[{"title": h.title, "url": h.url, "snippet": h.snippet}
                         for h in hits]
        )
    """
    try:
        from knowledge_base.kb_tools_query import query_tools  # noqa: WPS433
        k         = max(1, min(int(arguments.get("top_k") or 5), 10))
        fmt       = str(arguments.get("fmt") or "context")
        use_web   = bool(arguments.get("web") or False)
        injected  = arguments.get("web_results") or None
        # injected results → force web=True and skip DuckDuckGo
        if injected:
            use_web = True

        result = query_tools(
            arguments["query"],
            k=k,
            fmt=fmt,
            web=use_web,
            web_results=injected,
            caller="claude-mcp",
        )
        block = result["context_block"]
        web_n = len(result.get("web_hits", []))
        backend = result.get("web_backend", "")
        web_note = f" web={web_n}hits({backend})" if web_n else ""
        block += (
            f"\n\n<!-- KB: in={result['tokens_in']} out={result['tokens_out']} "
            f"saved≈{result['token_savings']} | {result['search_method']}{web_note} "
            f"{result['latency_ms']:.0f}ms -->"
        )
        return block
    except Exception as exc:
        return (
            f"KB query failed: {exc}\n"
            f"Fallback: run `python -m knowledge_base query \"{arguments.get('query', '')}\"` in the terminal."
        )


def tool_definitions() -> list[dict[str, Any]]:
    defs: list[dict[str, Any]] = []
    for name in EXPOSED_TOOLS:
        if name == "query_kb_tools":
            defs.append(_KB_TOOL)
        elif name == "sync_research_sources":
            defs.append(_SYNC_RESEARCH_SOURCES_TOOL)
        elif name == "ingest_news_feeds":
            defs.append(_INGEST_NEWS_FEEDS_TOOL)
        elif name == "search_evidence":
            defs.append(_SEARCH_EVIDENCE_TOOL)
        elif name == "build_evidence_pack":
            defs.append(_BUILD_EVIDENCE_PACK_TOOL)
        elif name == "ingest_company_filings":
            defs.append(_INGEST_COMPANY_FILINGS_TOOL)
        elif name == "ingest_company_concalls":
            defs.append(_INGEST_COMPANY_CONCALLS_TOOL)
        else:
            defs.append({"name": name, "description": TOOL_REGISTRY[name][1], "inputSchema": TOOL_REGISTRY[name][2]})
    return defs


def dispatch(message: dict[str, Any]) -> dict[str, Any] | None:
    method, request_id = message.get("method"), message.get("id")
    if method == "notifications/initialized":
        return None
    if method == "initialize":
        requested = str((message.get("params") or {}).get("protocolVersion") or PROTOCOL_VERSION)
        return _result(request_id, {
            "protocolVersion": requested,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        })
    if method == "ping":
        return _result(request_id, {})
    if method == "tools/list":
        return _result(request_id, {"tools": tool_definitions()})
    if method == "tools/call":
        params = message.get("params") or {}
        name, arguments = str(params.get("name") or ""), params.get("arguments") or {}
        if not isinstance(arguments, dict):
            return _error(request_id, -32602, "tool arguments must be an object")
        # PG 2026-08-25: KB query handled inline (not via TOOL_REGISTRY)
        if name == "query_kb_tools":
            text = _call_kb(arguments)
            return _result(request_id, {"content": [{"type": "text", "text": text}], "isError": False})
        if name == "sync_research_sources":
            payload = _sync_research_sources(arguments)
            failed = bool(payload.get("error"))
            return _result(request_id, {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, default=str)}], "isError": failed})
        if name == "ingest_news_feeds":
            payload = _ingest_news_feeds(arguments)
            failed = bool(payload.get("error"))
            return _result(request_id, {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, default=str)}], "isError": failed})
        if name == "search_evidence":
            payload = _search_evidence(arguments)
            failed = bool(payload.get("error"))
            return _result(request_id, {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, default=str)}], "isError": failed})
        if name == "build_evidence_pack":
            payload = _build_evidence_pack(arguments)
            failed = bool(payload.get("error"))
            return _result(request_id, {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, default=str)}], "isError": failed})
        if name == "ingest_company_filings":
            payload = _ingest_company_filings(arguments)
            failed = bool(payload.get("error"))
            return _result(request_id, {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, default=str)}], "isError": failed})
        if name == "ingest_company_concalls":
            payload = _ingest_company_concalls(arguments)
            failed = bool(payload.get("error"))
            return _result(request_id, {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, default=str)}], "isError": failed})
        if name not in EXPOSED_TOOLS:
            return _error(request_id, -32602, f"tool is not exposed: {name}")
        output = call_tool(name, arguments)
        failed = isinstance(output, dict) and (bool(output.get("error")) or output.get("success") is False or output.get("passed") is False)
        return _result(request_id, {
            "content": [{"type": "text", "text": json.dumps(output, ensure_ascii=False, default=str)}],
            "isError": failed,
        })
    return _error(request_id, -32601, f"method not found: {method}")


def _pg_conn():
    from company_intelligence.company_intelligence_pg import connect

    return connect(os.environ.get("AGENT_ADDA_PG_DSN") or os.environ.get("PG_DSN"))


def _sync_research_sources(arguments: dict) -> dict[str, Any]:
    try:
        config_path = str(arguments.get("config_path") or "config/research_sources.yml")
        dry_run = bool(arguments.get("dry_run") or False)

        from tools.ingest_news_feeds import load_sources, sync_sources  # noqa: WPS433

        path = (PROJECT_ROOT / config_path).resolve()
        sources = load_sources(path)
        conn = _pg_conn()
        try:
            result = sync_sources(conn, sources, dry_run=dry_run)
            result.update({"config_path": config_path, "dry_run": dry_run})
            return result
        finally:
            conn.close()
    except Exception as exc:
        return {"error": str(exc)}


def _ingest_news_feeds(arguments: dict) -> dict[str, Any]:
    try:
        max_items_per_feed = max(1, min(int(arguments.get("max_items_per_feed") or 25), 100))
        since_days = max(0, min(int(arguments.get("since_days") or 7), 30))
        sleep_ms = max(0, min(int(arguments.get("sleep_ms") or 250), 2000))
        dry_run = bool(arguments.get("dry_run") or False)

        from tools.ingest_news_feeds import ingest_active_rss  # noqa: WPS433

        conn = _pg_conn()
        try:
            stats = ingest_active_rss(
                conn,
                max_items_per_feed=max_items_per_feed,
                since_days=since_days,
                sleep_ms=sleep_ms,
                dry_run=dry_run,
            )
            stats.update({"dry_run": dry_run})
            return stats
        finally:
            conn.close()
    except Exception as exc:
        return {"error": str(exc)}


def _search_evidence(arguments: dict) -> dict[str, Any]:
    try:
        query = str(arguments.get("query") or "").strip()
        if not query:
            return {"error": "query is required"}
        symbol = str(arguments.get("symbol") or "").strip().upper()
        include_market_wide = bool(True if arguments.get("include_market_wide") is None else arguments.get("include_market_wide"))
        source_tier_max = max(1, min(int(arguments.get("source_tier_max") or 4), 4))
        limit = max(1, min(int(arguments.get("limit") or 12), 50))
        days = max(0, min(int(arguments.get("days") or 0), 365))

        where = ["to_tsvector('english', coalesce(ec.text,'')) @@ websearch_to_tsquery('english', %s)"]
        params: list[Any] = [query]

        if symbol:
            if include_market_wide:
                where.append("(ec.symbol = %s OR ec.symbol = '')")
                params.append(symbol)
            else:
                where.append("ec.symbol = %s")
                params.append(symbol)

        where.append("ec.source_tier <= %s")
        params.append(int(source_tier_max))

        if days > 0:
            where.append(
                "COALESCE(NULLIF(ec.evidence_date,''), NULLIF(sd.document_date,''))::date >= (CURRENT_DATE - %s)"
            )
            params.append(int(days))

        sql = f"""
            SELECT
                ec.chunk_id,
                ec.document_id,
                ec.symbol,
                ec.category,
                ec.source_tier,
                ec.evidence_date,
                left(ec.text, 1200) AS snippet,
                sd.source_name,
                sd.source_url,
                sd.document_type,
                sd.document_date,
                sd.metadata,
                ts_rank(to_tsvector('english', coalesce(ec.text,'')), websearch_to_tsquery('english', %s)) AS rank
            FROM company_intel.evidence_chunks ec
            JOIN company_intel.source_documents sd
              ON sd.document_id = ec.document_id
            WHERE {" AND ".join(where)}
            ORDER BY rank DESC, ec.source_tier ASC, ec.chunk_id DESC
            LIMIT %s
        """
        # rank query param is first param again (kept separate for plan stability)
        params_for_sql = [query, *params, int(limit)]

        conn = _pg_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params_for_sql)
                rows = cur.fetchall()
        finally:
            conn.close()

        results = []
        for row in rows:
            (
                chunk_id,
                document_id,
                row_symbol,
                category,
                source_tier,
                evidence_date,
                snippet,
                source_name,
                source_url,
                document_type,
                document_date,
                metadata,
                rank,
            ) = row
            results.append(
                {
                    "chunk_id": int(chunk_id),
                    "document_id": str(document_id),
                    "symbol": str(row_symbol),
                    "category": str(category),
                    "source_tier": int(source_tier),
                    "evidence_date": str(evidence_date or ""),
                    "document_date": str(document_date or ""),
                    "document_type": str(document_type or ""),
                    "source_name": str(source_name or ""),
                    "source_url": str(source_url or ""),
                    "snippet": str(snippet or ""),
                    "rank": float(rank or 0.0),
                    "metadata": metadata if isinstance(metadata, dict) else metadata,
                }
            )

        return {
            "query": query,
            "symbol": symbol,
            "include_market_wide": include_market_wide,
            "source_tier_max": source_tier_max,
            "days": days,
            "limit": limit,
            "results": results,
            "count": len(results),
        }
    except Exception as exc:
        return {"error": str(exc)}


def _build_evidence_pack(arguments: dict) -> dict[str, Any]:
    try:
        symbol = str(arguments.get("symbol") or "").strip().upper()
        if not symbol:
            return {"error": "symbol is required"}
        sector_overlay = str(arguments.get("sector_overlay") or "").strip()
        dimensions = arguments.get("dimensions") or None
        if dimensions is not None and not isinstance(dimensions, list):
            return {"error": "dimensions must be an array of strings"}
        days_passes = arguments.get("days_passes") or [0, 7, 30, 90]
        tier_passes = arguments.get("tier_passes") or [1, 2, 3, 4]
        if not isinstance(days_passes, list) or not isinstance(tier_passes, list):
            return {"error": "days_passes and tier_passes must be arrays of integers"}
        limit_per_query = max(1, min(int(arguments.get("limit_per_query") or 10), 25))
        include_market_wide = bool(True if arguments.get("include_market_wide") is None else arguments.get("include_market_wide"))
        store_run = bool(arguments.get("store_run") or False)
        config_path = str(arguments.get("config_path") or "config/evidence_dimensions.yml")

        from tools.build_evidence_pack import build_evidence_pack as _build  # noqa: WPS433

        return _build(
            symbol=symbol,
            sector_overlay=sector_overlay,
            dimensions=[str(x) for x in dimensions] if dimensions else None,
            days_passes=[int(x) for x in days_passes],
            tier_passes=[int(x) for x in tier_passes],
            limit_per_query=limit_per_query,
            include_market_wide=include_market_wide,
            store_run=store_run,
            config_path=(PROJECT_ROOT / config_path).resolve(),
        )
    except Exception as exc:
        return {"error": str(exc)}


def _ingest_company_filings(arguments: dict) -> dict[str, Any]:
    try:
        symbol = str(arguments.get("symbol") or "").strip().upper()
        if not symbol:
            return {"error": "symbol is required"}
        max_docs = max(1, min(int(arguments.get("max_docs") or 3), 10))
        period = str(arguments.get("period") or "latest_results").strip() or "latest_results"
        force_download = bool(arguments.get("force_download") or False)
        dry_run = bool(arguments.get("dry_run") or False)

        from tools.ingest_company_filings import ingest_company_filings  # noqa: WPS433

        return ingest_company_filings(
            symbol=symbol,
            max_docs=max_docs,
            period=period,
            force_download=force_download,
            dry_run=dry_run,
        )
    except Exception as exc:
        return {"error": str(exc)}


def _ingest_company_concalls(arguments: dict) -> dict[str, Any]:
    try:
        symbol = str(arguments.get("symbol") or "").strip().upper()
        if not symbol:
            return {"error": "symbol is required"}
        max_docs = max(1, min(int(arguments.get("max_docs") or 3), 10))
        force_download = bool(arguments.get("force_download") or False)
        dry_run = bool(arguments.get("dry_run") or False)

        from tools.ingest_company_concalls import ingest_company_concalls  # noqa: WPS433

        return ingest_company_concalls(
            symbol=symbol,
            max_docs=max_docs,
            force_download=force_download,
            dry_run=dry_run,
        )
    except Exception as exc:
        return {"error": str(exc)}


def serve(stdin: BinaryIO | None = None, stdout: BinaryIO | None = None) -> int:
    source, sink = stdin or sys.stdin.buffer, stdout or sys.stdout.buffer
    while True:
        message = _read_message(source)
        if message is None:
            return 0
        response = dispatch(message)
        if response is not None:
            _write_message(sink, response)


def _read_message(stream: BinaryIO) -> dict[str, Any] | None:
    first = stream.readline()
    if not first:
        return None
    if first.lower().startswith(b"content-length:"):
        length = int(first.split(b":", 1)[1].strip())
        while True:
            header = stream.readline()
            if header in {b"\r\n", b"\n", b""}:
                break
        raw = stream.read(length)
    else:
        raw = first.strip()
    if not raw:
        return _read_message(stream)
    return json.loads(raw.decode("utf-8"))


def _write_message(stream: BinaryIO, message: dict[str, Any]) -> None:
    payload = json.dumps(message, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8") + b"\n"
    stream.write(payload)
    stream.flush()


def _result(request_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list-tools", action="store_true")
    parser.add_argument("--call", metavar="TOOL")
    parser.add_argument("--arguments", default="{}", help="JSON object used with --call")
    args = parser.parse_args(argv)
    if args.list_tools:
        print(json.dumps({"tools": tool_definitions()}, indent=2))
        return 0
    if args.call:
        arguments = json.loads(args.arguments)
        if args.call == "query_kb_tools":
            print(_call_kb(arguments))
            return 0
        if args.call not in EXPOSED_TOOLS:
            parser.error(f"tool is not exposed: {args.call}")
        print(json.dumps(call_tool(args.call, arguments), indent=2, ensure_ascii=False, default=str))
        return 0
    return serve()


if __name__ == "__main__":
    raise SystemExit(main())
