#!/usr/bin/env python3
"""
Daily NSE Data Refresh Orchestrator
=====================================
Runs the full pipeline after NSE market close (3:30 PM IST / 10:00 UTC).

Pipeline stages:
  1. Fetch auxiliary data: FII/DII flows, F&O signals, corporate events,
     insider alerts, macro proxies
  2. Run comprehensive NSE universe analysis → generates comprehensive_nse_enhanced_*.csv
  3. Update sector rotation tracker: live prices + daily EOD snapshot
  4. Generate HTML report

Usage:
  python daily_refresh.py               # full pipeline
  python daily_refresh.py --live-only   # just update live prices (fast, ~1 min)
  python daily_refresh.py --skip-analysis  # skip heavy analysis, just tracker
  python daily_refresh.py --dry-run     # print plan without executing
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

_IST_OFFSET = 5.5 * 3600   # seconds


def _now_ist() -> str:
    utc = datetime.now(timezone.utc)
    ist_ts = utc.timestamp() + _IST_OFFSET
    return datetime.fromtimestamp(ist_ts, tz=timezone.utc).replace(tzinfo=None).strftime("%Y-%m-%d %H:%M IST")


def _run(label: str, cmd: list[str], dry_run: bool = False, cwd: Path | None = None) -> bool:
    """Run a subprocess step. Returns True on success."""
    print(f"\n{'─'*60}")
    print(f"▶  {label}")
    print(f"   {' '.join(cmd)}")
    if dry_run:
        print("   [DRY RUN — skipped]")
        return True
    t0 = time.time()
    result = subprocess.run(
        cmd,
        cwd=str(cwd or ROOT),
        capture_output=False,
    )
    elapsed = time.time() - t0
    if result.returncode == 0:
        print(f"   ✅ Done in {elapsed:.0f}s")
        return True
    else:
        print(f"   ❌ FAILED (exit {result.returncode}) after {elapsed:.0f}s")
        return False


def _section(title: str) -> None:
    print(f"\n{'═'*60}")
    print(f"  {title}")
    print(f"{'═'*60}")


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline steps
# ─────────────────────────────────────────────────────────────────────────────

def step_fetch_auxiliary(dry_run: bool) -> dict[str, bool]:
    """Fetch FII/DII, F&O, corporate events, insider alerts, macro proxies."""
    _section("STEP 1 — Fetch Auxiliary Market Data")
    results = {}

    scripts = [
        ("FII/DII Flows",        ["python", "fetch_fii_dii_flows.py"]),
        ("F&O OI + PCR",         ["python", "fetch_fno_data.py"]),
        ("Corporate Events",     ["python", "fetch_corporate_events.py"]),
        ("Insider Alerts",       ["python", "fetch_insider_alerts.py"]),
        ("Macro Proxies",        ["python", "fetch_macro_proxies.py"]),
    ]
    for label, cmd in scripts:
        ok = _run(label, cmd, dry_run=dry_run)
        results[label] = ok
        if not ok:
            print(f"   ⚠️  {label} failed — continuing with stale data")
    return results


def step_comprehensive_analysis(dry_run: bool) -> bool:
    """Run the full NSE universe analysis to generate comprehensive CSV."""
    _section("STEP 2 — Comprehensive NSE Universe Analysis")
    # fixed_nse_universe_analysis.py generates comprehensive_nse_enhanced_*.csv
    return _run(
        "NSE Universe Analysis",
        ["python", "fixed_nse_universe_analysis.py"],
        dry_run=dry_run,
    )


def step_tracker_snapshot(dry_run: bool, live_only: bool = False) -> bool:
    """Capture EOD snapshot with live prices, compute changes."""
    _section("STEP 3 — Sector Rotation Tracker")

    if live_only:
        # Fast path: only refresh live prices (no screener re-run)
        return _run(
            "Update live prices (NSE India + YF fallback)",
            ["python", "sector_rotation_tracker.py", "--update-live"],
            dry_run=dry_run,
        )
    else:
        # Full snapshot: re-run screener + fetch live prices
        ok = _run(
            "EOD snapshot (screener + live prices)",
            ["python", "sector_rotation_tracker.py", "--snapshot"],
            dry_run=dry_run,
        )
        return ok


def step_generate_report(dry_run: bool) -> bool:
    """Generate Stage 2 tracker HTML report."""
    _section("STEP 4 — Generate HTML Report")
    return _run(
        "Stage 2 Tracker HTML Report",
        ["python", "sector_rotation_tracker.py", "--report", "--html"],
        dry_run=dry_run,
    )


def step_sector_rotation_report(dry_run: bool) -> bool:
    """Regenerate full sector rotation report."""
    _section("STEP 5 — Sector Rotation Report (optional)")
    return _run(
        "Sector Rotation Full Report",
        ["python", "sector_rotation_report.py"],
        dry_run=dry_run,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Daily NSE data refresh orchestrator")
    parser.add_argument("--live-only",       action="store_true",
                        help="Only update live prices for today's snapshot (fast, ~2 min)")
    parser.add_argument("--skip-analysis",   action="store_true",
                        help="Skip heavy comprehensive analysis (use existing CSV)")
    parser.add_argument("--skip-aux",        action="store_true",
                        help="Skip auxiliary data fetch (FII/DII, F&O, events)")
    parser.add_argument("--full-report",     action="store_true",
                        help="Also regenerate full sector rotation report")
    parser.add_argument("--dry-run",         action="store_true",
                        help="Print plan without executing anything")
    args = parser.parse_args()

    print(f"\n{'═'*60}")
    print("  NSE Daily Refresh Pipeline")
    print(f"  Started: {_now_ist()}")
    print(f"{'═'*60}")

    if args.dry_run:
        print("\n  ⚠️  DRY RUN MODE — no commands will execute\n")

    failed: list[str] = []
    t_total = time.time()

    # ── Fast path: live prices only ──────────────────────────────────────────
    if args.live_only:
        if not step_tracker_snapshot(args.dry_run, live_only=True):
            failed.append("Live price update")
        step_generate_report(args.dry_run)
        _print_summary(failed, t_total, args.dry_run)
        return 1 if failed else 0

    # ── Full pipeline ────────────────────────────────────────────────────────

    # 1. Auxiliary data
    if not args.skip_aux:
        aux_results = step_fetch_auxiliary(args.dry_run)
        # Don't fail pipeline on auxiliary errors — they use cached data

    # 2. Comprehensive analysis
    if not args.skip_analysis:
        if not step_comprehensive_analysis(args.dry_run):
            failed.append("Comprehensive analysis")
            print("\n  ⚠️  Analysis failed — will use latest existing CSV for tracker")

    # 3. Tracker snapshot (full: screener + live prices)
    if not step_tracker_snapshot(args.dry_run, live_only=False):
        # Fallback: try live-only update if screener failed
        print("  Snapshot failed — trying live-price update only …")
        if not step_tracker_snapshot(args.dry_run, live_only=True):
            failed.append("Tracker snapshot")

    # 4. HTML report
    if not step_generate_report(args.dry_run):
        failed.append("HTML report")

    # 5. Optional full sector rotation report
    if args.full_report:
        if not step_sector_rotation_report(args.dry_run):
            failed.append("Sector rotation report")

    _print_summary(failed, t_total, args.dry_run)
    return 1 if failed else 0


def _print_summary(failed: list[str], t_start: float, dry_run: bool) -> None:
    elapsed = time.time() - t_start
    print(f"\n{'═'*60}")
    if dry_run:
        print("  DRY RUN complete — no actual changes made")
    elif not failed:
        print(f"  ✅ All steps completed successfully in {elapsed:.0f}s")
    else:
        print(f"  ⚠️  Completed with {len(failed)} failure(s) in {elapsed:.0f}s:")
        for f in failed:
            print(f"     • {f}")
    print(f"  Finished: {_now_ist()}")
    print(f"{'═'*60}\n")


if __name__ == "__main__":
    sys.exit(main())
