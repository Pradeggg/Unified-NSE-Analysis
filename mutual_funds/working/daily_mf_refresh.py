#!/usr/bin/env python3
"""
Daily Mutual Funds (Smallcap Portfolio) Refresh
================================================
Runs the two daily pipeline scripts for the Agent Adda Smallcap Portfolio:

  Stage 3: build_smallcap_research_update.py  → readiness overlay + research brief
  Stage 4: check_smallcap_fund_latest_market.py → trigger states + shadow P&L

Use --full to also run the upstream stages (requires preselection + policy inputs):
  Stage 1: apply_smallcap_fund_policy.py       → policy gate + Phase 1 ratings
  Stage 2: build_phase1_evidence_packs.py      → evidence packs + trigger map

Usage:
  python "Mutual Funds/working/daily_mf_refresh.py"
  python "Mutual Funds/working/daily_mf_refresh.py" --run-date 20260816
  python "Mutual Funds/working/daily_mf_refresh.py" --full
  python "Mutual Funds/working/daily_mf_refresh.py" --dry-run
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKING = Path(__file__).resolve().parent
PYTHON = sys.executable


def _run(label: str, cmd: list[str], dry_run: bool = False) -> bool:
    print(f"\n{'─' * 55}")
    print(f"▶  {label}")
    print(f"   {' '.join(str(c) for c in cmd)}")
    if dry_run:
        print("   [DRY RUN — skipped]")
        return True
    t0 = time.time()
    result = subprocess.run(cmd, cwd=str(ROOT))
    elapsed = time.time() - t0
    if result.returncode == 0:
        print(f"   ✅ Done in {elapsed:.0f}s")
        return True
    print(f"   ❌ FAILED (exit {result.returncode}) after {elapsed:.0f}s")
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Daily smallcap portfolio refresh.")
    parser.add_argument(
        "--run-date",
        default=datetime.now().strftime("%Y%m%d"),
        help="Run date in YYYYMMDD format (default: today).",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Also run Stage 1 (policy gate) and Stage 2 (evidence packs). "
             "Requires preselection scores CSV to be present in Mutual Funds/extracted/.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print plan without executing anything.",
    )
    args = parser.parse_args()

    print(f"\n{'═' * 55}")
    print("  Agent Adda Smallcap Portfolio — Daily Refresh")
    print(f"  Run date : {args.run_date}")
    print(f"  Started  : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'═' * 55}")

    if args.dry_run:
        print("\n  ⚠️  DRY RUN MODE — no commands will execute\n")

    failed: list[str] = []
    t_total = time.time()

    if args.full:
        # Stage 1 — Policy gate
        ok = _run(
            "Stage 1: Apply Smallcap Fund Policy",
            [PYTHON, str(WORKING / "apply_smallcap_fund_policy.py")],
            dry_run=args.dry_run,
        )
        if not ok:
            failed.append("Stage 1: Policy gate")
            print("  ⚠️  Policy gate failed — Stage 2 may use stale policy gate CSV")

        # Stage 2 — Evidence packs
        ok = _run(
            "Stage 2: Build Phase 1 Evidence Packs",
            [PYTHON, str(WORKING / "build_phase1_evidence_packs.py")],
            dry_run=args.dry_run,
        )
        if not ok:
            failed.append("Stage 2: Evidence packs")
            print("  ⚠️  Evidence packs failed — Stage 4 market check may use stale packs")

    # Stage 3 — Daily research update
    ok = _run(
        "Stage 3: Smallcap Research Update",
        [PYTHON, str(WORKING / "build_smallcap_research_update.py"), "--run-date", args.run_date],
        dry_run=args.dry_run,
    )
    if not ok:
        failed.append("Stage 3: Research update")

    # Stage 4 — Daily market check
    ok = _run(
        "Stage 4: Latest Market Check + Shadow P&L",
        [PYTHON, str(WORKING / "check_smallcap_fund_latest_market.py"), "--run-date", args.run_date],
        dry_run=args.dry_run,
    )
    if not ok:
        failed.append("Stage 4: Market check")

    elapsed = time.time() - t_total
    print(f"\n{'═' * 55}")
    if args.dry_run:
        print("  DRY RUN complete — no actual changes made")
    elif not failed:
        print(f"  ✅ All steps completed successfully in {elapsed:.0f}s")
        _print_outputs(args.run_date)
    else:
        print(f"  ⚠️  Completed with {len(failed)} failure(s) in {elapsed:.0f}s:")
        for f in failed:
            print(f"     • {f}")
    print(f"{'═' * 55}\n")
    return 1 if failed else 0


def _print_outputs(run_date: str) -> None:
    extracted = ROOT / "Mutual Funds" / "extracted"
    reports = ROOT / "Mutual Funds" / "reports"
    outputs = [
        reports / f"agent_adda_smallcap_research_update_{run_date}.html",
        extracted / f"agent_adda_smallcap_research_update_{run_date}.csv",
        reports / f"agent_adda_smallcap_fund_latest_market_check_{run_date}.html",
        extracted / f"agent_adda_smallcap_fund_latest_market_check_{run_date}.csv",
        extracted / f"agent_adda_smallcap_fund_latest_market_check_{run_date}.json",
    ]
    print("\n  Outputs:")
    for p in outputs:
        status = "✅" if p.exists() else "❌ missing"
        print(f"     {status}  {p.relative_to(ROOT)}")


if __name__ == "__main__":
    sys.exit(main())
