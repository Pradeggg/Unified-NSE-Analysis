"""CLI entry point for the knowledge base pipeline.

── Financial documents (SEBI / RBI / broker research) ──────────────────────
    python -m knowledge_base build --tier 1 --max-pdfs 3
    python -m knowledge_base build --source SEBI RBI CRISIL
    python -m knowledge_base build --category credit_rating_agencies
    python -m knowledge_base ask "What did SEBI say about disclosure norms?"
    python -m knowledge_base ask "credit rating outlook for HDFC Bank" --collection chunks
    python -m knowledge_base stats
    python -m knowledge_base ingest https://example.com/report.pdf

── Tools / skills / commands / workflows (BM25 fast search) ─────────────────
    python -m knowledge_base query "how to run daily pipeline"
    python -m knowledge_base query "chart RELIANCE" --format context
    python -m knowledge_base query "stage 2 screener" --top 8 --format json
    python -m knowledge_base query "vcp breakout" --hybrid          # BM25 + vector
    python -m knowledge_base index-skills                           # rebuild BM25 index info

── Token usage analytics ────────────────────────────────────────────────────
    python -m knowledge_base tokens                 # last 7 days
    python -m knowledge_base tokens --days 30       # last 30 days
    python -m knowledge_base tokens --json          # machine-readable

── Episodes (derived + imported) ────────────────────────────────────────────
    python -m knowledge_base episodes --hours 48
    python -m knowledge_base import-episodes --days 60 --project /Users/pradeepgorai/Documents/Projects/finance
    python -m knowledge_base episodes-imported --days 60 --source claude --query finance --top 10
    python -m knowledge_base episodes-real --days 30 --query command_center --top 20

── Synthetic router dataset ────────────────────────────────────────────────
    python -m knowledge_base synth-router --mode both --days 30 --max 300
    python -m knowledge_base eval-router data/knowledge_base/router_synth_....jsonl
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .ingest import ingest_any  # PG 2026-05-27: ad-hoc single-doc ingest
from .pipeline import query_kb, run_pipeline


# PG 2026-05-27: /kb ingest <url|path> — add one report to the KB without
# editing financial_sources_registry.json.
def cmd_ingest(args: argparse.Namespace) -> int:
    result = ingest_any(
        args.target,
        source_id=(args.source_id or "ADHOC").upper(),
        source_name=args.source_name or "",
        category=args.category or "adhoc",
        tier=args.tier,
        hub_label=args.hub_label or "adhoc",
        do_qa=not args.skip_qa,
    )
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("ok") else 1


def cmd_build(args: argparse.Namespace) -> int:
    summary = run_pipeline(
        categories=args.category or None,
        tiers=args.tier or None,
        source_ids=args.source or None,
        max_pdfs_per_hub=args.max_pdfs,
        do_fetch=not args.skip_fetch,
        do_chunk=not args.skip_chunk,
        do_qa=not args.skip_qa,
        do_index=not args.skip_index,
    )
    print("\n" + json.dumps(summary, indent=2, default=str))
    return 0


def cmd_ask(args: argparse.Namespace) -> int:
    hits = query_kb(args.query, k=args.k, collection=args.collection)
    if not hits:
        print("No results.")
        return 1
    for i, h in enumerate(hits, 1):
        m = h.get("metadata", {})
        print(f"\n[{i}] score={h['score']:.3f}  src={m.get('source_id')}/{m.get('hub_label')}  "
              f"({m.get('fetched_date')})  {m.get('source_url')}")
        text = h["text"]
        if len(text) > 800:
            text = text[:800] + " …"
        print(text)
    return 0


def cmd_stats(_: argparse.Namespace) -> int:
    # Stats should be usable even when optional vector-store deps (chromadb, etc.)
    # are not installed.
    from .skills_registry import get_registry  # noqa: WPS433

    out: dict[str, object] = {"skills_index": get_registry().stats}
    try:
        from .vector_store import KBVectorStore  # noqa: WPS433

        out["vector_store"] = {"available": True, "stats": KBVectorStore().stats()}
    except ModuleNotFoundError as exc:
        out["vector_store"] = {"available": False, "error": str(exc)}
    except Exception as exc:
        out["vector_store"] = {"available": False, "error": f"{type(exc).__name__}: {exc}"}

    print(json.dumps(out, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="knowledge_base")
    sub = p.add_subparsers(dest="cmd", required=True)

    pb = sub.add_parser("build", help="Fetch → chunk → QA → embed → index")
    pb.add_argument("--category", nargs="*", help="Restrict to one or more categories")
    pb.add_argument("--tier", nargs="*", type=int, help="Restrict by trust tier (1-4)")
    pb.add_argument("--source", nargs="*", help="Restrict by source IDs (e.g. SEBI RBI CRISIL)")
    pb.add_argument("--max-pdfs", type=int, default=3, help="Max PDFs to download per hub")
    pb.add_argument("--skip-fetch",  action="store_true")
    pb.add_argument("--skip-chunk",  action="store_true")
    pb.add_argument("--skip-qa",     action="store_true")
    pb.add_argument("--skip-index",  action="store_true")
    pb.set_defaults(func=cmd_build)

    pa = sub.add_parser("ask", help="Semantic search the knowledge base")
    pa.add_argument("query", help="Natural-language query")
    pa.add_argument("-k", type=int, default=6, help="Top K results (default 6)")
    pa.add_argument("--collection", choices=["qa", "chunks"], default="qa",
                    help="Search Q&A pairs (default) or full chunks")
    pa.set_defaults(func=cmd_ask)

    ps = sub.add_parser("stats", help="Print collection counts")
    ps.set_defaults(func=cmd_stats)

    # PG 2026-05-27: ad-hoc ingest of a single PDF (URL or local path)
    pi = sub.add_parser("ingest", help="Ingest a single PDF (URL or local path) into the KB")
    pi.add_argument("target", help="PDF URL (https://...) or local file path")
    pi.add_argument("--source-id", default="ADHOC",
                    help="Short source identifier, e.g. ICICI_DIRECT, GROWW (default: ADHOC)")
    pi.add_argument("--source-name", default="",
                    help="Human-readable source name (e.g. 'ICICI Direct Retail Research')")
    pi.add_argument("--category", default="adhoc",
                    help="Registry-style category, e.g. broker_research (default: adhoc)")
    pi.add_argument("--tier", type=int, default=9,
                    help="Trust tier 1–4 for registry sources; 9 = ad-hoc (default)")
    pi.add_argument("--hub-label", default="adhoc",
                    help="Label for this drop point (default: adhoc)")
    pi.add_argument("--skip-qa", action="store_true",
                    help="Skip Q&A generation (faster, indexes raw chunks only)")
    pi.set_defaults(func=cmd_ingest)

    # ── tools/skills/commands query (BM25) ───────────────────────────────────
    pq = sub.add_parser(
        "query",
        help="BM25 search over skills/commands/tools/workflows (fast, no LLM)"
    )
    pq.add_argument("query", help="Natural-language query")
    pq.add_argument("--top", "-k", type=int, default=5, dest="k",
                    help="Number of results (default 5)")
    pq.add_argument(
        "--format", "-f", default="context",
        choices=["text", "json", "context", "context-compact"],
        help="Output format (default: context — markdown block for prompt injection)",
    )
    pq.add_argument("--hybrid", action="store_true",
                    help="Augment BM25 with ChromaDB semantic search")
    pq.add_argument("--web", action="store_true",
                    help="Append live DuckDuckGo web-search results (Layer 3 — latest real-world data)")
    pq.add_argument("--max-tokens", type=int, default=2000,
                    help="Soft token budget for context output (default 2000)")
    pq.add_argument("--caller", default="cli",
                    help="Caller identifier for token tracking (default: cli)")
    pq.set_defaults(func=cmd_query)

    # ── rebuild skills index info ─────────────────────────────────────────────
    pis = sub.add_parser("index-skills", help="Show skills index stats and sample entries")
    pis.add_argument("--sample", type=int, default=3, help="Number of sample entries to show")
    pis.set_defaults(func=cmd_index_skills)

    # ── export flat index files (for grep/awk/jq) ─────────────────────────────
    pex = sub.add_parser(
        "export",
        help="Generate grep/awk/jq-friendly flat index files (kb_flat.txt, kb_index.tsv, kb_index.jsonl)"
    )
    pex.set_defaults(func=cmd_export)

    # ── token usage analytics ─────────────────────────────────────────────────
    pt = sub.add_parser("tokens", help="Show KB token usage analytics")
    pt.add_argument("--days", type=int, default=7, help="Lookback window in days (default 7)")
    pt.add_argument("--json", action="store_true", dest="as_json",
                    help="Output as JSON instead of pretty-printed table")
    pt.set_defaults(func=cmd_tokens)

    # ── derived episodes (from query log) ────────────────────────────────────
    pe = sub.add_parser("episodes", help="Show derived KB usage episodes (from query_log.db)")
    pe.add_argument("--hours", type=int, default=24, help="Look back N hours (default 24)")
    pe.add_argument("--gap-mins", type=int, default=20, help="Split episodes if gap > N minutes (default 20)")
    pe.add_argument("--json", action="store_true", dest="as_json", help="Output JSON")
    pe.set_defaults(func=cmd_episodes)

    pim = sub.add_parser("import-episodes", help="Import external assistant traces as metadata episodes")
    pim.add_argument("--days", type=int, default=60, help="Look back N days (default 60)")
    pim.add_argument("--project", default="",
                     help="Claude project path filter (default: no filter)")
    pim.add_argument("--json", action="store_true", dest="as_json",
                     help="Output JSON instead of a short summary")
    pim.set_defaults(func=cmd_import_episodes)

    pei = sub.add_parser("episodes-imported", help="View/search imported episodes (Cursor + Claude metadata)")
    pei.add_argument("--days", type=int, default=60, help="Look back N days (default 60)")
    pei.add_argument("--source", default="all", choices=["all", "claude", "cursor"],
                     help="Which imported source to view (default: all)")
    pei.add_argument("--query", default="", help="Search query (default: show latest)")
    pei.add_argument("--top", "-k", type=int, default=20, dest="k", help="Max results (default 20)")
    pei.add_argument("--json", action="store_true", dest="as_json", help="Output JSON")
    pei.set_defaults(func=cmd_episodes_imported)

    psyn = sub.add_parser("synth-router", help="Generate a synthetic router dataset (query -> expected tool)")
    psyn.add_argument("--mode", default="both", choices=["workflows", "querylog", "both"],
                      help="Label source mode (default both)")
    psyn.add_argument("--days", type=int, default=30, help="Querylog lookback in days (default 30)")
    psyn.add_argument("--max", type=int, default=300, dest="max_rows", help="Max rows to emit (default 300)")
    psyn.add_argument("--seed", type=int, default=42, help="Deterministic RNG seed (default 42)")
    psyn.add_argument("--symbols", default="",
                      help="Comma-separated symbols for placeholder expansion (default: RELIANCE,HDFCBANK,TCS,INFY,SBIN)")
    psyn.add_argument("--date", default="",
                      help="Optional date string to add to report-style queries (e.g. 2026-08-25)")
    psyn.add_argument("--hard-negatives", type=int, default=2,
                      help="Number of BM25 near-miss candidates to include (default 2)")
    psyn.add_argument("--out", default="", help="Output JSONL path (default under data/knowledge_base/)")
    psyn.add_argument("--json", action="store_true", dest="as_json",
                      help="Output JSON summary instead of writing file")
    psyn.set_defaults(func=cmd_synth_router)

    per = sub.add_parser("eval-router", help="Evaluate BM25 router on a synthetic JSONL dataset")
    per.add_argument("dataset", help="Path to JSONL dataset (e.g. data/knowledge_base/router_synth_*.jsonl)")
    per.add_argument("--top", "-k", type=int, default=20, dest="k", help="BM25 top-k to consider (default 20)")
    per.add_argument("--json", action="store_true", dest="as_json", help="Output JSON")
    per.set_defaults(func=cmd_eval_router)

    prl = sub.add_parser("episodes-real", help="View/search real execution episodes (EpisodeStore events.jsonl)")
    prl.add_argument("--days", type=int, default=30, help="Look back N days (default 30)")
    prl.add_argument("--query", default="", help="Search query (default: show latest)")
    prl.add_argument("--top", "-k", type=int, default=20, dest="k", help="Max results (default 20)")
    prl.add_argument("--json", action="store_true", dest="as_json", help="Output JSON")
    prl.set_defaults(func=cmd_episodes_real)

    args = p.parse_args(argv)
    return args.func(args)


# ── new command handlers ───────────────────────────────────────────────────────

def cmd_query(args: argparse.Namespace) -> int:
    from .kb_tools_query import query_tools  # noqa: WPS433
    result = query_tools(
        args.query,
        k=args.k,
        fmt=args.format,
        hybrid=args.hybrid,
        web=getattr(args, "web", False),
        max_tokens=args.max_tokens,
        caller=args.caller,
    )
    print(result["context_block"])
    # Brief footer with token accounting
    tin   = result["tokens_in"]
    tout  = result["tokens_out"]
    saved = result["token_savings"]
    ms    = result["latency_ms"]
    web_n = len(result.get("web_hits", []))
    web_note = f" | web={web_n} hits" if web_n else ""
    print(
        f"\n<!-- tokens: in={tin} out={tout} saved≈{saved} | "
        f"{result['search_method']}{web_note} | {ms:.1f}ms -->"
    )
    return 0


def cmd_episodes(args: argparse.Namespace) -> int:
    from .episodes import (
        derive_episodes_from_query_log,
        format_episodes_json,
        format_episodes_text,
    )  # noqa: WPS433

    eps = derive_episodes_from_query_log(hours=args.hours, gap_minutes=args.gap_mins)
    if args.as_json:
        print(format_episodes_json(eps))
    else:
        print(format_episodes_text(eps))
    return 0


def cmd_import_episodes(args: argparse.Namespace) -> int:
    from .episode_import import import_all_metadata  # noqa: WPS433

    result = import_all_metadata(days=args.days, claude_project_path=(args.project or None))
    if args.as_json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result.get("ok") else 1

    claude = (result.get("claude") or {})
    cursor = (result.get("cursor") or {})
    print("Imported episodes (metadata-only):")
    print(f"  days:   {result.get('days')}")
    print(f"  claude: {claude.get('episodes_written')} -> {claude.get('out_path')}")
    print(f"  cursor: {cursor.get('episodes_written')} -> {cursor.get('out_path')}")
    if claude.get("started_utc") and claude.get("ended_utc"):
        print(f"  claude range: {claude.get('started_utc')} → {claude.get('ended_utc')}")
    if cursor.get("started_utc") and cursor.get("ended_utc"):
        print(f"  cursor range: {cursor.get('started_utc')} → {cursor.get('ended_utc')}")
    return 0 if result.get("ok") else 1


def cmd_episodes_imported(args: argparse.Namespace) -> int:
    from .imported_episodes import (
        format_imported_hits_json,
        format_imported_hits_text,
        load_imported_episodes,
        search_imported_episodes,
    )  # noqa: WPS433

    sources = None
    if args.source != "all":
        sources = [args.source]
    eps = load_imported_episodes(days=args.days, sources=sources)
    hits = search_imported_episodes(eps, args.query, k=args.k)
    if args.as_json:
        print(format_imported_hits_json(hits))
    else:
        print(format_imported_hits_text(hits))
    return 0


def cmd_synth_router(args: argparse.Namespace) -> int:
    from .synth_router import default_out_path, generate_synth_dataset, write_jsonl  # noqa: WPS433

    symbols = [s.strip().upper() for s in (args.symbols or "").split(",") if s.strip()]
    date_str = (args.date or "").strip() or None
    rows = generate_synth_dataset(
        mode=args.mode,
        days=args.days,
        max_rows=args.max_rows,
        seed=args.seed,
        symbols=(symbols or None),
        date_str=date_str,
        hard_negatives=int(args.hard_negatives or 0),
    )
    out = Path(args.out).expanduser() if args.out else default_out_path(
        mode=args.mode,
        days=args.days,
        max_rows=args.max_rows,
        seed=args.seed,
        hard_negatives=int(args.hard_negatives or 0),
        date_str=date_str,
    )
    if args.as_json:
        print(json.dumps({"count": len(rows), "out": str(out), "mode": args.mode}, indent=2))
        return 0
    n = write_jsonl(out, rows)
    print(f"Wrote {n} rows -> {out}")
    return 0


def cmd_eval_router(args: argparse.Namespace) -> int:
    from .evals.router_eval import eval_router_bm25, format_eval_text  # noqa: WPS433

    ds = Path(args.dataset).expanduser()
    result = eval_router_bm25(ds, k=args.k)
    if args.as_json:
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(format_eval_text(result))
    return 0


def cmd_episodes_real(args: argparse.Namespace) -> int:
    from .real_episodes import (  # noqa: WPS433
        format_real_episodes_json,
        format_real_episodes_text,
        search_real_episodes,
        summarize_real_episodes,
    )

    eps = summarize_real_episodes(days=args.days)
    hits = search_real_episodes(eps, args.query, k=args.k)
    if args.as_json:
        print(format_real_episodes_json(hits))
    else:
        print(format_real_episodes_text(hits))
    return 0


def cmd_export(_: argparse.Namespace) -> int:
    from .skills_registry import get_registry, export_flat_indexes  # noqa: WPS433
    result = export_flat_indexes(get_registry())
    print(json.dumps(result, indent=2))
    print("\nReady for grep/awk/jq search:")
    print(f"  grep -i 'daily pipeline' {result['flat_txt']}")
    print(f"  awk -F'\\t' '$2==\"pipeline\"' {result['tsv']} | cut -f1,4")
    print(f"  grep 'vcp' {result['jsonl']} | python3 -c \"import sys,json; [print(d['id'],'|',d['cli']) for d in map(json.loads,sys.stdin)]\"")
    return 0


def cmd_index_skills(args: argparse.Namespace) -> int:
    from .skills_registry import get_registry  # noqa: WPS433
    reg = get_registry()
    s = reg.stats
    print(json.dumps(s, indent=2))
    print(f"\nSample entries (--sample {args.sample}):")
    import random
    reg._ensure_built()
    sample = random.sample(reg._entries, min(args.sample, len(reg._entries)))
    for e in sample:
        print(f"  [{e.get('category')}] {e.get('id')}")
        print(f"    {e.get('description','')[:100]}")
        print(f"    cli: {e.get('cli','')[:80]}")
    return 0


def cmd_tokens(args: argparse.Namespace) -> int:
    from .token_tracker import get_tracker  # noqa: WPS433
    tracker = get_tracker()
    if args.as_json:
        print(json.dumps(tracker.stats(days=args.days), indent=2))
    else:
        print(tracker.format_stats_report(days=args.days))
    return 0


if __name__ == "__main__":
    sys.exit(main())
