#!/usr/bin/env python3
"""
NSE Sector Research CLI – run research by sector with optional agent.

Usage:
  python agent_cli.py --sector "Auto Components" --run-all
  python agent_cli.py --sector auto_components --interactive
  python agent_cli.py --sector pharma

Sector name is normalized to a key (e.g. "Auto Components" -> auto_components).
Set NSE_SECTOR before any pipeline imports; --run-all runs full pipeline + narratives,
--interactive starts the Ollama agent with that sector context.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# CLI must set NSE_SECTOR before any config/pipeline import
WORKING_SECTOR = Path(__file__).resolve().parent
PROJECT_ROOT = WORKING_SECTOR.parent

# Load .env from project root so SERPAPI_API_KEY, BRAVE_API_KEY, etc. are set
try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass


def normalize_sector(s: str) -> str:
    """Normalize sector to key: 'Auto Components' -> auto_components."""
    if not s or not s.strip():
        return "auto_components"
    return s.strip().lower().replace(" ", "_").replace("-", "_")


def main():
    parser = argparse.ArgumentParser(
        description="NSE Sector Research: run pipeline and narratives by sector, or start interactive agent.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --sector "Auto Components" --run-all     Run full pipeline + narratives for Auto Components
  %(prog)s --sector "Plastics and Packaging" --download-universe --run-all   Download NSE universe then run pipeline
  %(prog)s --sector auto_components --interactive   Start agent for Auto Components
  %(prog)s --sector pharma                          Start agent for Pharma (requires pharma_universe.csv)
        """,
    )
    parser.add_argument(
        "--download-universe",
        action="store_true",
        help="Download sector stocks from NSE into <sector>_universe.csv before running (for plastics_and_packaging).",
    )
    parser.add_argument(
        "--sector",
        default=os.environ.get("NSE_SECTOR", "auto_components"),
        help="Sector name or key (e.g. 'Auto Components' or auto_components). Default: NSE_SECTOR or auto_components.",
    )
    parser.add_argument(
        "--run-all",
        action="store_true",
        help="Run sector research (multi-step search + synthesis), full pipeline (Phase 2–5), then narratives; then exit.",
    )
    parser.add_argument(
        "--no-research",
        action="store_true",
        help="With --run-all: skip multi-step sector research (no research_sources.md).",
    )
    parser.add_argument(
        "--engines",
        type=str,
        default=None,
        metavar="LIST",
        help="Comma-separated search engines for sector research (e.g. duckduckgo,yahoo). Default: duckduckgo,google,yahoo,brave.",
    )
    parser.add_argument(
        "--no-fundamental-scores",
        action="store_true",
        help="With --run-all: skip fetching earnings quality/sales growth/etc. into DB. Report may miss fundamental strength table for symbols not already in database.",
    )
    parser.add_argument(
        "--no-fundamental-details",
        action="store_true",
        help="With --run-all: skip fetching P&L/ratios from Screener (no fundamental_details.csv). Use if R is not installed.",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Start the Ollama Granite4 agent for this sector (chat + tool calling).",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("OLLAMA_MODEL", "granite4:latest"),
        help="Ollama model for the agent (default: granite4:latest).",
    )
    parser.add_argument(
        "--prompt",
        type=str,
        default=None,
        metavar="TEXT",
        help="Single prompt for the agent: it will run (search, pipeline, narratives via tools) until done, then exit. Use this to run research via the AI agent instead of --run-all.",
    )
    args = parser.parse_args()

    sector = normalize_sector(args.sector)
    os.environ["NSE_SECTOR"] = sector

    if str(WORKING_SECTOR) not in sys.path:
        sys.path.insert(0, str(WORKING_SECTOR))
    try:
        os.chdir(PROJECT_ROOT)
    except OSError:
        pass

    research_engines = None
    if args.engines:
        research_engines = [e.strip().lower() for e in args.engines.split(",") if e.strip()]

    if args.prompt is not None:
        _run_agent_single_prompt(sector, args.prompt, args.model)
    elif args.run_all:
        _run_full_pipeline_and_narratives(
            sector,
            skip_research=args.no_research,
            skip_fundamental_scores=args.no_fundamental_scores,
            skip_fundamental_details=args.no_fundamental_details,
            research_engines=research_engines,
        )
        if args.interactive:
            print("\n--- Starting interactive agent ---\n")
            _run_agent(sector, args.model)
    elif args.interactive:
        _run_agent(sector, args.model)
    else:
        # Optional: download universe from NSE first (for plastics_and_packaging etc.)
        if args.download_universe:
            _download_sector_universe(sector)
        # Default: run sector research + full pipeline + narratives for the sector, then suggest interactive
        _run_full_pipeline_and_narratives(
            sector,
            skip_research=args.no_research,
            skip_fundamental_scores=args.no_fundamental_scores,
            skip_fundamental_details=args.no_fundamental_details,
            research_engines=research_engines,
        )
        print("\nTo run research via the AI agent instead, use: python agent_cli.py --sector", repr(args.sector), "--prompt \"Run sector research for latest data, then run full pipeline and narratives\"")
        print("To chat interactively: python agent_cli.py --sector", repr(args.sector), "--interactive")


def _download_sector_universe(sector: str) -> None:
    """Download sector stocks from NSE into working-sector/<sector>_universe.csv."""
    from pipeline_tools import download_nse_sector_universe
    os.environ["NSE_SECTOR"] = sector
    result = download_nse_sector_universe(sector_key=sector, use_nse_api=True)
    print(result)


def _run_full_pipeline_and_narratives(
    sector: str,
    skip_research: bool = False,
    skip_fundamental_scores: bool = False,
    skip_fundamental_details: bool = False,
    research_engines: list[str] | None = None,
) -> None:
    """Run sector research (optional), fetch fundamental scores for DB (optional), Phase 2–5, fetch P&L/ratios (optional), narratives, then comprehensive report."""
    from pipeline_tools import (
        run_sector_research,
        run_fetch_fundamental_scores,
        run_full_pipeline,
        run_fetch_fundamental_details,
        run_narratives,
        run_comprehensive_report,
    )
    from config import OUTPUT_DIR

    print(f"Sector: {sector}")
    if not skip_research:
        engines_msg = f" (engines: {', '.join(research_engines)})" if research_engines else ""
        print(f"Running multi-step sector research (latest data, sources and dates in report){engines_msg}...")
        research_result = run_sector_research(rounds=3, engines=research_engines)
        print(research_result)
        print()
    if not skip_fundamental_scores:
        print("Fetching fundamental scores (earnings quality, sales growth, etc.) for report...")
        fs_result = run_fetch_fundamental_scores()
        print(fs_result)
        print()
    print("Running full pipeline (Phase 2 → 3 → 4 → 5)...")
    result = run_full_pipeline()
    print(result)
    if not skip_fundamental_details:
        print("\nFetching fundamental details (P&L, ratios) for narratives and report...")
        fd_result = run_fetch_fundamental_details()
        print(fd_result)
    print("\nGenerating stock narratives (Ollama)...")
    nar_result = run_narratives()
    print(nar_result)
    print("\nBuilding comprehensive report (MD, HTML, XLSX)...")
    cr_result = run_comprehensive_report()
    print(cr_result)
    print(f"\nOutputs in: {OUTPUT_DIR}")


def _run_agent(sector: str, model: str) -> None:
    """Start the agent loop with sector in context."""
    from config import SECTOR_DISPLAY_NAME
    from agent import run_agent_loop

    print(f"Agent context: sector = {sector} ({SECTOR_DISPLAY_NAME})")
    run_agent_loop(model=model, sector_name=SECTOR_DISPLAY_NAME)


def _run_agent_single_prompt(sector: str, prompt: str, model: str) -> None:
    """Run the agent with one prompt; it uses tools (search, pipeline, narratives) until done, then exit."""
    from config import SECTOR_DISPLAY_NAME
    from agent import run_agent_single_prompt

    print(f"Sector: {sector} ({SECTOR_DISPLAY_NAME})")
    print(f"Prompt: {prompt}\n")
    reply = run_agent_single_prompt(user_prompt=prompt, model=model, sector_name=SECTOR_DISPLAY_NAME)
    print("\nAssistant:", reply)


if __name__ == "__main__":
    main()
