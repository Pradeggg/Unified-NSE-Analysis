"""CLI entry point for the knowledge base pipeline.

Usage:
    python -m knowledge_base build --tier 1 --max-pdfs 3
    python -m knowledge_base build --source SEBI RBI CRISIL
    python -m knowledge_base build --category credit_rating_agencies
    python -m knowledge_base ask "What did SEBI say about disclosure norms?"
    python -m knowledge_base ask "credit rating outlook for HDFC Bank" --collection chunks
    python -m knowledge_base stats
"""
from __future__ import annotations

import argparse
import json
import sys

from .ingest import ingest_any  # PG 2026-05-27: ad-hoc single-doc ingest
from .pipeline import query_kb, run_pipeline
from .vector_store import KBVectorStore


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
    s = KBVectorStore().stats()
    print(json.dumps(s, indent=2))
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

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
