#!/usr/bin/env python3
"""scripts/run_multiturn_demo.py — Interactive multi-turn conversation demo.

Drives the Agent Adda terminal through multi-turn conversations
using the --query CLI flag, simulating real user sessions.

Usage:
  python scripts/run_multiturn_demo.py               # run all 30 sampled scenarios
  python scripts/run_multiturn_demo.py --cat C1      # only command→NLP scenarios
  python scripts/run_multiturn_demo.py --cat C4      # only portfolio scenarios
  python scripts/run_multiturn_demo.py --id C2-03    # specific scenario
  python scripts/run_multiturn_demo.py --list        # list all scenarios
  python scripts/run_multiturn_demo.py --dry-run     # show routing only, no LLM

Each conversation shows:
  [Turn 1] user message → routing decision + thinking display
  [Turn 2] follow-up    → routing decision + thinking display
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable

DEMO_SCENARIOS = [
    # C1 — Command → NLP follow-up
    ("C1-01", "/scan NIFTY",              "which of these setups looks strongest"),
    ("C1-04", "/my-portfolio sell",       "why should I exit ITC Hotels"),
    ("C1-05", "/my-portfolio buy",        "how much should I add to KIRLOSENG"),
    ("C1-06", "/mtf RELIANCE",            "what is the entry trigger based on this"),
    ("C1-09", "/my-portfolio eod",        "which stocks are in the SELL zone"),
    # C2 — Market → Stock drill-down
    ("C2-01", "which sectors are doing well",  "show me top stocks in IT sector"),
    ("C2-02", "top gainers today",             "tell me more about the first stock"),
    ("C2-03", "sector rotation",              "which pharma stocks are leading"),
    ("C2-07", "stage 2 stocks today",         "filter by pharma and healthcare"),
    ("C2-11", "momentum leaders today",       "RPTECH is on the list — give me detail"),
    # C3 — Stock → Comparative
    ("C3-01", "RELIANCE technical setup",     "compare with ONGC on same metrics"),
    ("C3-02", "HDFC Bank fundamentals",       "is it better than ICICI Bank right now"),
    ("C3-07", "GRANULES pharma analysis",     "GRANULES or LAURUSLABS — which is stronger"),
    ("C3-15", "ICICIBANK technical",          "which private bank strongest — ICICI HDFC AXIS KOTAK"),
    ("C3-25", "NETWEB IT analysis",           "Netweb vs Tata Elxsi vs RPTECH — best growth"),
    # C4 — Portfolio → Action
    ("C4-01", "/my-portfolio",               "which holdings have worst signal score"),
    ("C4-05", "portfolio performance",        "which positions are dragging the most"),
    ("C4-10", "/my-portfolio",               "rebalance to reduce banking exposure below 20%"),
    ("C4-19", "/my-portfolio buy",            "I have ₹2 lakh free — allocate across top 3 buys"),
    ("C4-20", "/my-portfolio sell",           "ITC is in stage 4 — exit all or partial"),
    # C5 — RIC → Deep dive
    ("C5-01", "/ric sherlock RELIANCE",       "explain the EPS trend from the above data"),
    ("C5-03", "/ric sherlock AGARIND",        "EPS crashed to 29 — value trap or recovery"),
    ("C5-06", "/ric breakout-hunter",         "narrow list to stocks with CANSLIM above 16"),
    ("C5-11", "/ric sherlock GRANULES",       "stage 2 continuation risk if market turns risk-off"),
    ("C5-25", "/ric sherlock RPTECH",         "technical trigger to add if already holding"),
    # C6 — Ambiguous → Clarified
    ("C6-01", "IT",                           "I meant IT sector — show me leading IT stocks"),
    ("C6-04", "which",                        "which sectors are doing well today"),
    ("C6-07", "banks",                        "private banks — HDFC ICICI AXIS — which strongest"),
    ("C6-16", "rotation",                     "sector rotation — current sector strength ranking"),
    ("C6-24", "small cap",                    "small cap with stage 2 and CANSLIM above 16"),
]

CAT_LABELS = {
    "C1": "Command → NLP follow-up",
    "C2": "Market overview → Stock drill-down",
    "C3": "Single stock → Comparative",
    "C4": "Portfolio → Action planning",
    "C5": "RIC workflow → Deep dive",
    "C6": "Ambiguous → Clarified",
}


def _print_banner(text: str, char: str = "═") -> None:
    w = min(80, len(text) + 4)
    print(f"\n{char * w}")
    print(f"  {text}")
    print(f"{char * w}")


def _route_only(query: str) -> str:
    """Return routing summary without calling LLM."""
    try:
        import importlib
        sys.path.insert(0, str(ROOT))
        import terminal.router.providers
        importlib.reload(terminal.router.providers)
        from terminal.router import UnifiedRouter, ContextPack
        router = UnifiedRouter()
        pack = ContextPack(session_id="demo")
        clean = query.lstrip("/intraday ").lstrip("/historical ").strip()
        r = router.route(clean, pack)
        intent = r.intent or "fallback_llm"
        provider = r.reasoning_summary.selected_branch or "LLM"
        tools = [t.tool for t in (r.tool_plan or [])]
        tool_str = " → ".join(tools[:4]) if tools else "LLM tool loop"
        return f"  💭 Route: {intent}  ({provider})\n  📋 Plan:  {tool_str}"
    except Exception as e:
        return f"  ⚠  Routing error: {e}"


def _run_query(query: str, dry_run: bool = False) -> None:
    """Run a single query through the agent terminal."""
    if dry_run:
        route_info = _route_only(query)
        print(f"  ❯ {query}")
        print(route_info)
        return

    try:
        result = subprocess.run(
            [PYTHON, str(ROOT / "nse_agent.py"), "--query", query],
            cwd=str(ROOT),
            capture_output=False,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        print("  ⚠  Query timed out after 120s")
    except Exception as e:
        print(f"  ⚠  Error: {e}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Multi-turn conversation demo for Agent Adda")
    parser.add_argument("--cat",      help="Filter by category (C1-C6)")
    parser.add_argument("--id",       help="Run a specific scenario ID")
    parser.add_argument("--list",     action="store_true", help="List all scenarios")
    parser.add_argument("--dry-run",  action="store_true", help="Show routing only, no LLM")
    parser.add_argument("--pause",    type=float, default=1.0,
                        help="Seconds between turns (default 1.0)")
    args = parser.parse_args()

    scenarios = DEMO_SCENARIOS

    if args.list:
        print(f"\n{'ID':<8} {'Cat':<6} {'Turn 1':<40} {'Turn 2'}")
        print("-" * 110)
        for sid, t1, t2 in scenarios:
            cat = sid[:2]
            print(f"{sid:<8} {cat:<6} {t1[:38]:<40} {t2[:45]}")
        return

    if args.id:
        scenarios = [(sid, t1, t2) for sid, t1, t2 in scenarios if sid == args.id]
        if not scenarios:
            print(f"Scenario {args.id!r} not found")
            return

    if args.cat:
        scenarios = [(sid, t1, t2) for sid, t1, t2 in scenarios
                     if sid.startswith(args.cat)]
        if not scenarios:
            print(f"No scenarios for category {args.cat!r}")
            return

    _print_banner(
        f"Agent Adda — Multi-Turn Demo  ({len(scenarios)} conversations)"
        + ("  [DRY RUN — routing only]" if args.dry_run else "  [LIVE — calling LLM]")
    )

    for i, (sid, turn1, turn2) in enumerate(scenarios, 1):
        cat = sid[:2]
        cat_label = CAT_LABELS.get(cat, cat)

        _print_banner(
            f"[{i}/{len(scenarios)}]  {sid}  ·  {cat_label}",
            char="─"
        )

        print(f"\n┌─ TURN 1 ─────────────────────────────────────────────────────────")
        _run_query(turn1, dry_run=args.dry_run)

        time.sleep(args.pause)

        print(f"\n└─ TURN 2 (follow-up) ─────────────────────────────────────────────")
        _run_query(turn2, dry_run=args.dry_run)

        print()
        if i < len(scenarios):
            time.sleep(args.pause)

    _print_banner(f"Demo complete  ·  {len(scenarios)} conversations tested")


if __name__ == "__main__":
    main()
