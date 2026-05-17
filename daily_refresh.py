#!/usr/bin/env python3
"""
Daily NSE Data Refresh Orchestrator
=====================================
Runs the full pipeline after NSE market close (3:30 PM IST / 10:00 UTC).

Pipeline stages:
  1. Fetch auxiliary data: FII/DII flows, F&O signals, corporate events,
     insider alerts, macro proxies
  2. Load latest EOD bhavcopy into PostgreSQL market.equity_eod
  3. Run comprehensive NSE universe analysis → writes PostgreSQL scores.daily_scores
  4. Update sector rotation tracker from PostgreSQL scores + EOD history
  5. Generate HTML/PDF reports

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
PYTHON = sys.executable

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

_IST_OFFSET = 5.5 * 3600   # seconds


def _now_ist() -> str:
    utc = datetime.now(timezone.utc)
    ist_ts = utc.timestamp() + _IST_OFFSET
    return datetime.fromtimestamp(ist_ts, tz=timezone.utc).replace(tzinfo=None).strftime("%Y-%m-%d %H:%M IST")


def _run(label: str, cmd: list[str], dry_run: bool = False, cwd: Path | None = None, env: dict | None = None) -> bool:
    """Run a subprocess step. Returns True on success."""
    print(f"\n{'─'*60}")
    print(f"▶  {label}")
    print(f"   {' '.join(str(c) for c in cmd)}")
    if dry_run:
        print("   [DRY RUN — skipped]")
        return True
    t0 = time.time()
    result = subprocess.run(
        cmd,
        cwd=str(cwd or ROOT),
        capture_output=False,
        env=env,
    )
    elapsed = time.time() - t0
    if result.returncode == 0:
        print(f"   ✅ Done in {elapsed:.0f}s")
        return True
    else:
        print(f"   ❌ FAILED (exit {result.returncode}) after {elapsed:.0f}s")
        return False


def _ensure_postgres_running(dry_run: bool = False) -> bool:
    """Start the local project PostgreSQL cluster if it is not already running."""
    script = ROOT / "postgres" / "start_pg.sh"
    if dry_run:
        print(f"   [DRY RUN — would ensure PostgreSQL via {script}]")
        return True
    if not script.exists():
        print(f"   ⚠️  PostgreSQL start script not found: {script}")
        return False
    status = subprocess.run(
        [str(script), "status"],
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if status.returncode == 0:
        return True
    print("   PostgreSQL is not running; attempting local start …")
    return _run("Start local PostgreSQL", [str(script), "start"], dry_run=False)


def _section(title: str) -> None:
    print(f"\n{'═'*60}")
    print(f"  {title}")
    print(f"{'═'*60}")


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline steps
# ─────────────────────────────────────────────────────────────────────────────

def step_fetch_eod_data(dry_run: bool) -> bool:
    """Fetch EOD bhavcopy from NSE archives into local ingress files."""
    _section("STEP 0 — Fetch EOD Bhavcopy (NSE Archives)")

    # Pass PROJECT_ROOT so R script resolves paths relative to repo root
    import os
    env = {**os.environ, "PROJECT_ROOT": str(ROOT)}
    ok = _run(
        "Download latest NSE bhavcopy → data/nse-raw/ + data/",
        ["Rscript", str(ROOT / "load_latest_nse_data_comprehensive.R")],
        dry_run=dry_run,
        env=env,
    )
    if ok and not dry_run:
        print(f"   ✅ NSE data written to {ROOT / 'data'}")
    return ok


def step_postgres_eod_load(dry_run: bool) -> bool:
    """Load latest local equity and index EOD files into PostgreSQL before analysis."""
    _section("STEP 0B — PostgreSQL Equity + Index EOD Load")
    if not _ensure_postgres_running(dry_run=dry_run):
        return False
    return _run(
        "Load latest bhavcopy/index EOD → market.equity_eod + market.index_eod",
        [PYTHON, "postgres/loader.py", "--eod-only"],
        dry_run=dry_run,
    )


def step_fetch_auxiliary(dry_run: bool) -> dict[str, bool]:
    """Fetch FII/DII, F&O, corporate events, insider alerts, macro proxies."""
    _section("STEP 1 — Fetch Auxiliary Market Data")
    results = {}

    scripts = [
        ("FII/DII Flows",        [PYTHON, "fetch_fii_dii_flows.py"]),
        ("F&O OI + PCR",         [PYTHON, "fetch_fno_data.py"]),
        ("Corporate Events",     [PYTHON, "fetch_corporate_events.py"]),
        ("Insider Alerts",       [PYTHON, "fetch_insider_alerts.py"]),
        ("Macro Proxies",        [PYTHON, "fetch_macro_proxies.py"]),
    ]
    for label, cmd in scripts:
        ok = _run(label, cmd, dry_run=dry_run)
        results[label] = ok
        if not ok:
            print(f"   ⚠️  {label} failed — continuing with stale data")
    return results


def step_comprehensive_analysis(dry_run: bool) -> bool:
    """Run the full NSE universe analysis and write scores.daily_scores directly."""
    _section("STEP 2 — Comprehensive NSE Universe Analysis")
    return _run(
        "NSE Universe Analysis",
        [PYTHON, "fixed_nse_universe_analysis.py"],
        dry_run=dry_run,
    )


def step_tracker_snapshot(dry_run: bool, live_only: bool = False) -> bool:
    """Capture EOD snapshot with live prices, compute changes."""
    _section("STEP 3 — Sector Rotation Tracker")

    if live_only:
        # Fast path: only refresh live prices (no screener re-run)
        return _run(
            "Update live prices (NSE India + YF fallback)",
            [PYTHON, "sector_rotation_tracker.py", "--update-live"],
            dry_run=dry_run,
        )
    else:
        # Full snapshot: re-run screener from PostgreSQL scores + fetch live prices
        ok = _run(
            "EOD snapshot (screener + live prices)",
            [PYTHON, "sector_rotation_tracker.py", "--snapshot"],
            dry_run=dry_run,
        )
        return ok


def step_generate_report(dry_run: bool) -> bool:
    """Generate Stage 2 tracker HTML report."""
    _section("STEP 4 — Generate HTML Report")
    return _run(
        "Stage 2 Tracker HTML Report",
        [PYTHON, "sector_rotation_tracker.py", "--report", "--html"],
        dry_run=dry_run,
    )


def step_sector_rotation_report(dry_run: bool) -> bool:
    """Regenerate full sector rotation report — populates signal_log.csv."""
    _section("STEP 5 — Sector Rotation Report")
    return _run(
        "Sector Rotation Report",
        [PYTHON, "sector_rotation_report.py"],
        dry_run=dry_run,
    )


def step_voice_briefing(dry_run: bool) -> bool:
    """Generate today's voice briefing script from fresh signal_log.csv data."""
    _section("STEP 6 — Voice Briefing (script only, no audio)")
    return _run(
        "Voice Briefing",
        [PYTHON, "generate_voice_briefing.py", "--no-tts"],
        dry_run=dry_run,
    )


def step_postgres_load(dry_run: bool) -> bool:
    """Load today's EOD data into PostgreSQL and run all 40 screeners."""
    _section("STEP 7 — PostgreSQL Load + Screener Run")
    if not _ensure_postgres_running(dry_run=dry_run):
        return False
    return _run(
        "PostgreSQL loader + screeners",
        [PYTHON, "postgres/loader.py"],
        dry_run=dry_run,
    )


def step_screener_fundamentals_backfill(
    dry_run: bool,
    index: str = "NIFTY 500",
    delay: float = 2.5,
    skip_fresh_days: int = 7,
) -> bool:
    """Refresh PG fundamentals cache for the given index via screener.in.

    Polite (delay+jitter) by default; only re-scrapes symbols whose snapshot
    is older than ``skip_fresh_days`` so weekly runs cost ~zero on no-op days.
    """
    _section(f"STEP 8 — Fundamentals Backfill ({index})")
    if not _ensure_postgres_running(dry_run=dry_run):
        return False
    cmd = [
        PYTHON, "-u", "-m", "scripts.backfill_screener_fundamentals",
        "--index", index,
        "--delay", str(delay),
        "--skip-fresh-days", str(skip_fresh_days),
    ]
    return _run(f"Screener fundamentals backfill ({index})", cmd, dry_run=dry_run)


def step_comprehensive_r_reports(dry_run: bool) -> bool:
    """Run R-based comprehensive reports: All Indexes + All Sectors HTML.

    R scripts use PROJECT_ROOT env var to resolve paths locally.
    Outputs are written to local reports/nse_analysis/2026/.
    """
    _section("STEP 6 — Comprehensive R Reports (Indexes + Sectors)")

    import os
    local_r_out = ROOT / "reports" / "nse_analysis" / "2026"
    local_r_out.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "PROJECT_ROOT": str(ROOT)}

    ok = True
    for label, script in [
        ("All Indexes HTML",  "analyze_all_indexes.R"),
        ("All Sectors HTML",  "analyze_all_sectors.R"),
    ]:
        result = _run(label, ["Rscript", str(ROOT / script)], dry_run=dry_run, env=env)
        ok = ok and result

    if not dry_run and ok:
        print(f"   ✅ R reports written to {local_r_out}")

    return ok


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
    parser.add_argument("--comprehensive",   action="store_true",
                        help="Also run R-based comprehensive index + sector HTML reports")
    parser.add_argument("--fundamentals-backfill", action="store_true",
                        help="Force NIFTY 500 fundamentals backfill (otherwise runs only on Sundays)")
    parser.add_argument("--skip-fundamentals", action="store_true",
                        help="Skip fundamentals backfill even on its scheduled day")
    parser.add_argument("--fundamentals-index", default="NIFTY 500",
                        help="Index label for fundamentals backfill (default: NIFTY 500)")
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

    # 0. EOD data fetch (bhavcopy) — must run before analysis
    if not args.skip_analysis:
        if not step_fetch_eod_data(args.dry_run):
            print("\n  ⚠️  EOD data fetch failed — will use latest cached data")
        if not step_postgres_eod_load(args.dry_run):
            failed.append("PostgreSQL EOD load")
            print("\n  ⚠️  PostgreSQL EOD load failed — analysis may use stale EOD history")

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

    # 5. Sector rotation report (now always runs — populates signal_log.csv for voice briefing)
    if not step_sector_rotation_report(args.dry_run):
        failed.append("Sector rotation report")

    # 6. Voice briefing — generates script from fresh signal_log.csv (fast, no LLM)
    if not step_voice_briefing(args.dry_run):
        failed.append("Voice briefing")

    # 7. PostgreSQL load + run all 40 screeners
    if not step_postgres_load(args.dry_run):
        print("  ⚠️  PostgreSQL load failed — screeners not updated")
        failed.append("PostgreSQL screeners")

    # 7b. Weekly fundamentals backfill (default: Sundays only, or --fundamentals-backfill)
    run_fundamentals = (
        args.fundamentals_backfill
        or (not args.skip_fundamentals and datetime.now().weekday() == 6)
    )
    if run_fundamentals:
        if not step_screener_fundamentals_backfill(args.dry_run, index=args.fundamentals_index):
            print("  ⚠️  Fundamentals backfill had failures — see reports/backfill_screener_errors_*.json")
            failed.append("Fundamentals backfill")
    elif not args.skip_fundamentals:
        print(f"\n  (skipping fundamentals backfill — runs on Sundays or with --fundamentals-backfill)")

    # 8. Optional comprehensive R reports (All Indexes + All Sectors HTML)
    if args.comprehensive:
        if not step_comprehensive_r_reports(args.dry_run):
            failed.append("Comprehensive R reports")

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
