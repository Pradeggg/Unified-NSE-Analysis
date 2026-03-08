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
  %(prog)s --sector auto_components --interactive   Start agent for Auto Components
  %(prog)s --sector pharma                          Start agent for Pharma (requires pharma_universe.csv)
        """,
    )
    parser.add_argument(
        "--sector",
        default=os.environ.get("NSE_SECTOR", "auto_components"),
        help="Sector name or key (e.g. 'Auto Components' or auto_components). Default: NSE_SECTOR or auto_components.",
    )
    parser.add_argument(
        "--run-all",
        action="store_true",
        help="Run full pipeline (Phase 2–5) and then generate stock narratives; then exit.",
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
    args = parser.parse_args()

    sector = normalize_sector(args.sector)
    os.environ["NSE_SECTOR"] = sector

    if str(WORKING_SECTOR) not in sys.path:
        sys.path.insert(0, str(WORKING_SECTOR))
    try:
        os.chdir(PROJECT_ROOT)
    except OSError:
        pass

    if args.run_all:
        _run_full_pipeline_and_narratives(sector)
        if args.interactive:
            print("\n--- Starting interactive agent ---\n")
            _run_agent(sector, args.model)
    elif args.interactive:
        _run_agent(sector, args.model)
    else:
        # Default: run full pipeline + narratives for the sector, then suggest interactive
        _run_full_pipeline_and_narratives(sector)
        print("\nTo chat with the agent for this sector, run: python agent_cli.py --sector", repr(args.sector), "--interactive")


def _run_full_pipeline_and_narratives(sector: str) -> None:
    """Run Phase 2–5 and then stock narratives for the current sector."""
    from pipeline_tools import run_full_pipeline, run_narratives

    print(f"Sector: {sector}")
    print("Running full pipeline (Phase 2 → 3 → 4 → 5)...")
    result = run_full_pipeline()
    print(result)
    print("\nGenerating stock narratives (Ollama)...")
    nar_result = run_narratives()
    print(nar_result)
    from config import OUTPUT_DIR
    print(f"\nOutputs in: {OUTPUT_DIR}")


def _run_agent(sector: str, model: str) -> None:
    """Start the agent loop with sector in context."""
    from config import SECTOR_DISPLAY_NAME
    from agent import run_agent_loop

    print(f"Agent context: sector = {sector} ({SECTOR_DISPLAY_NAME})")
    run_agent_loop(model=model, sector_name=SECTOR_DISPLAY_NAME)


if __name__ == "__main__":
    main()
