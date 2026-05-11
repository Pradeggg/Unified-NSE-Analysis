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

from .pipeline import query_kb, run_pipeline
from .vector_store import KBVectorStore


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

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
