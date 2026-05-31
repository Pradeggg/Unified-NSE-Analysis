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


def step_fno_postgres_load(dry_run: bool) -> bool:
    """Load cached historical/latest F&O EOD bhavcopy into PostgreSQL before reports."""
    _section("STEP 1B — PostgreSQL F&O EOD Load")
    if not _ensure_postgres_running(dry_run=dry_run):
        return False
    return _run(
        "Load cached F&O bhavcopy history → derivatives.fno_eod + analytics",
        [PYTHON, "postgres/loader.py", "--fno-only"],
        dry_run=dry_run,
    )


def step_fetch_auxiliary(dry_run: bool) -> dict[str, bool]:
    """Fetch FII/DII, F&O, corporate events, insider alerts, macro proxies."""
    _section("STEP 1 — Fetch Auxiliary Market Data")
    results = {}

    scripts = [
        ("FII/DII Flows",        [PYTHON, "fetch_fii_dii_flows.py"]),
        # Optimus/2026-05-27: pass --backfill 7 so missing FO bhavcopy CSVs are
        # downloaded into data/_fno_cache/ before STEP 1B loads them into Postgres.
        # Without this, generate_fno_signals() short-circuits on stale PG cache
        # and derivatives.fno_eod stays frozen at the last successful bhavcopy date.
        ("F&O OI + PCR",         [PYTHON, "fetch_fno_data.py", "--backfill", "7"]),
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


def step_tracker_snapshot(
    dry_run: bool,
    live_only: bool = False,
    *,
    enrich_missing: int = 0,
    enrich_delay: float = 2.5,
    enrich_yfinance_fallback: bool = False,
) -> bool:
    """Capture EOD snapshot with live prices, compute changes.

    When ``enrich_missing`` > 0, the tracker live-scrapes screener.in (and
    optionally yfinance) for up to that many symbols missing from the
    PG fund cache, persisting results so the universe gap closes
    incrementally across daily runs.
    """
    _section("STEP 3 — Sector Rotation Tracker")

    if live_only:
        # Fast path: only refresh live prices (no screener re-run)
        return _run(
            "Update live prices (NSE India + YF fallback)",
            [PYTHON, "sector_rotation_tracker.py", "--update-live"],
            dry_run=dry_run,
        )
    else:
        cmd = [PYTHON, "sector_rotation_tracker.py", "--snapshot"]
        if enrich_missing > 0:
            cmd += [
                "--enrich-missing", str(enrich_missing),
                "--enrich-delay", str(enrich_delay),
            ]
            if enrich_yfinance_fallback:
                cmd += ["--enrich-yfinance-fallback"]
        # Full snapshot: re-run screener from PostgreSQL scores + fetch live prices
        ok = _run(
            "EOD snapshot (screener + live prices)",
            cmd,
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


def step_top_picks_report(dry_run: bool) -> bool:
    """Generate Top Investment Picks Analysis (merges sector rotation + stage-2 tracker)."""
    _section("STEP 5B — Top Investment Picks Analysis")
    return _run(
        "Top Investment Picks Analysis",
        [PYTHON, "top_picks_report.py"],
        dry_run=dry_run,
    )


def step_refresh_corporate_events(dry_run: bool) -> bool:
    """Refresh corporate events + insider alerts from NSE and load into
    signals.corporate_events and signals.insider_alerts. Non-fatal."""
    _section("STEP 4D — Corporate Events + Insider Alerts Refresh")
    if dry_run:
        print("  DRY-RUN: would force-refresh CSV caches + upsert into DB")
        return True
    if not _ensure_postgres_running(dry_run=dry_run):
        return False
    # 1) Force-refresh CSV caches via the existing fetchers (best-effort).
    _run("Fetch corporate events (NSE)",
         [PYTHON, "fetch_corporate_events.py", "--force"],
         dry_run=dry_run)
    _run("Fetch insider alerts (NSE)",
         [PYTHON, "fetch_insider_alerts.py", "--force"],
         dry_run=dry_run)
    # 2) Upsert CSVs → signals tables via loaders.
    try:
        import psycopg2  # local import keeps daily_refresh import-light
        from postgres.loader import load_corporate_events, load_insider_alerts  # type: ignore
        with psycopg2.connect(dbname="nse_market") as conn:
            with conn.cursor() as cur:
                load_corporate_events(cur)
                load_insider_alerts(cur)
            conn.commit()
        return True
    except Exception as exc:
        print(f"  ⚠️  signals DB load failed: {exc}")
        return False


def step_refresh_top_picks_fundamentals(dry_run: bool) -> bool:
    """Pre-refresh screener fundamentals for today's top picks so the report
    renders with up-to-date shareholding, ratios, and structured financials.
    Non-fatal: a failure here must not block the report itself."""
    _section("STEP 5A — Top Picks Fundamentals Pre-Refresh (screener)")
    if dry_run:
        print("  DRY-RUN: would print picks and run screener backfill for them")
        return True
    if not _ensure_postgres_running(dry_run=dry_run):
        return False
    try:
        out = subprocess.run(
            [PYTHON, "top_picks_report.py", "--print-picks"],
            capture_output=True, text=True, timeout=120,
        )
        if out.returncode != 0:
            print(f"  ⚠️  could not determine picks: {out.stderr.strip()}")
            return False
        syms = (out.stdout or "").strip().splitlines()[-1].strip()
        if not syms:
            print("  no picks to refresh — skipping")
            return True
        print(f"  Refreshing fundamentals for picks: {syms}")
        return _run(
            "Top Picks fundamentals backfill",
            [PYTHON, "-m", "scripts.backfill_screener_fundamentals",
             "--symbols", syms, "--skip-fresh-days", "0", "--delay", "2.0"],
            dry_run=dry_run,
        )
    except Exception as exc:
        print(f"  ⚠️  top-picks fundamentals pre-refresh failed: {exc}")
        return False


def step_email_top_picks(dry_run: bool, send: bool = False) -> bool:
    """Compose + open (or send) the Top Picks email via Outlook using the
    recipients in config/report_recipients.yml. Non-fatal: a failure here
    must not break the rest of the refresh."""
    _section("STEP 5C — Email Top Investment Picks (draft in Outlook)")
    cmd = [PYTHON, "-m", "terminal.email_dispatcher", "top_picks", "--mode", "both"]
    if send:
        cmd.append("--send")
    return _run("Email Top Picks", cmd, dry_run=dry_run)


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


# PG-FUND-ORDER 2026-05-26: refresh fundamentals BEFORE the sector rotation
# tracker snapshot so HTML detail cards include all 5 fund sub-scores. Prior
# behaviour deferred fundamentals refresh to STEP 7 (after HTML render), which
# caused only `enhanced_fund_score` (sourced from a fallback CSV) to appear in
# the rendered card while the other 4 sub-scores showed "—".
def step_fundamentals_refresh(dry_run: bool) -> bool:
    """Pre-snapshot fundamentals refresh — guarantees the tracker snapshot
    sees fresh scores.fundamental_scores rows for the current universe."""
    _section("STEP 2B — PostgreSQL Fundamentals Pre-Refresh")
    if not _ensure_postgres_running(dry_run=dry_run):
        return False
    return _run(
        "Fundamentals refresh (scores.fundamental_scores)",
        [PYTHON, "postgres/loader.py", "--fundamentals-only"],
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


def step_refresh_results_feed(
    dry_run: bool,
    days_back: int = 14,
    limit: int = 200,
    delay: float = 2.5,
    skip_fresh_hours: float = 6.0,
) -> bool:
    """Refresh structured financials cache for companies that filed results recently.

    Narrow daily counterpart to the weekly fundamentals backfill: only
    touches symbols listed in the NSE corporates-financial-results feed
    within the last ``days_back`` days. Polite (delay+jitter) and skips
    symbols already refreshed within ``skip_fresh_hours``.
    """
    _section(f"STEP 7b — Results-Feed Refresh (last {days_back}d)")
    if not _ensure_postgres_running(dry_run=dry_run):
        return False
    cmd = [
        PYTHON, "-u", "-m", "scripts.refresh_results_feed",
        "--days-back", str(days_back),
        "--limit", str(limit),
        "--delay", str(delay),
        "--skip-fresh-hours", str(skip_fresh_hours),
    ]
    return _run("Results-feed structured refresh", cmd, dry_run=dry_run)


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
                        help="Force fundamentals backfill (otherwise runs only on Sundays)")
    parser.add_argument("--skip-fundamentals", action="store_true",
                        help="Skip fundamentals backfill even on its scheduled day")
    parser.add_argument("--skip-results-feed", action="store_true",
                        help="Skip daily results-feed cache refresh")
    parser.add_argument("--skip-email", action="store_true",
                        help="Skip the Top Picks email step (STEP 5C)")
    parser.add_argument("--email-send", action="store_true",
                        help="Send Top Picks email immediately instead of opening as Outlook draft")
    parser.add_argument("--fundamentals-index",
                        default="NIFTY 500,NIFTY MICROCAP 250",
                        help="Index label(s) for fundamentals backfill (comma-separated). "
                             "Default: NIFTY 500 ∪ NIFTY MICROCAP 250 (~750 symbols).")
    parser.add_argument("--enrich-missing", type=int, default=60, metavar="N",
                        help="During tracker snapshot, live-scrape screener.in for up to N "
                             "symbols missing from the PG fund cache (default 60). Set 0 to disable.")
    parser.add_argument("--enrich-delay", type=float, default=2.5,
                        help="Seconds between enrichment screener.in calls (default: 2.5)")
    parser.add_argument("--enrich-yfinance-fallback", action="store_true", default=True,
                        help="On screener failure, fall back to yfinance ratios (default: ON)")
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

    # F&O analytics are consumed by the sector rotation report before the full
    # PostgreSQL loader runs, so refresh them from cached bhavcopy files here.
    if not step_fno_postgres_load(args.dry_run):
        failed.append("PostgreSQL F&O EOD load")
        print("\n  ⚠️  PostgreSQL F&O load failed — sector report may use stale derivatives analytics")

    # 2. Comprehensive analysis
    if not args.skip_analysis:
        if not step_comprehensive_analysis(args.dry_run):
            failed.append("Comprehensive analysis")
            print("\n  ⚠️  Analysis failed — will use latest existing CSV for tracker")

    # PG-FUND-ORDER 2026-05-26: Refresh fundamentals BEFORE snapshot so the
    # HTML detail cards render all 5 fund sub-scores (Enh Fund, Earn Qual,
    # Sales Gr, Fin Str, Inst Back). Previously this only happened in STEP 7,
    # after the HTML was already written.
    if not step_fundamentals_refresh(args.dry_run):
        failed.append("Fundamentals pre-refresh")
        print("\n  ⚠️  Fundamentals pre-refresh failed — tracker snapshot may render NULL sub-scores")

    # 3. Tracker snapshot (full: screener + live prices)
    if not step_tracker_snapshot(
        args.dry_run,
        live_only=False,
        enrich_missing=args.enrich_missing,
        enrich_delay=args.enrich_delay,
        enrich_yfinance_fallback=args.enrich_yfinance_fallback,
    ):
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

    # 5A. Pre-refresh screener fundamentals for today's top picks (shareholding,
    #     ratios, structured financials) so the report below renders complete.
    if not step_refresh_top_picks_fundamentals(args.dry_run):
        print("  ⚠️  Top picks fundamentals pre-refresh failed — report may have gaps")
        # non-fatal; carry on to the report

    # 5A.5  Refresh corporate events (NSE → signals.corporate_events) so the
    #       per-stock 'Corporate Events' panel is fresh. Non-fatal.
    if not step_refresh_corporate_events(args.dry_run):
        print("  ⚠️  Corporate events refresh failed (non-fatal) — see logs above")

    # 5B. Top Investment Picks Analysis (merges sector rotation + stage-2 tracker)
    if not step_top_picks_report(args.dry_run):
        failed.append("Top investment picks report")

    # 5C. Email Top Picks report (opens as Outlook draft; --email-send to send)
    if not args.skip_email:
        if not step_email_top_picks(args.dry_run, send=args.email_send):
            print("  ⚠️  Top Picks email step failed (non-fatal) — see logs above")
            failed.append("Top Picks email")

    # 6. Voice briefing — generates script from fresh signal_log.csv (fast, no LLM)
    if not step_voice_briefing(args.dry_run):
        failed.append("Voice briefing")

    # 7. PostgreSQL load + run all 40 screeners
    if not step_postgres_load(args.dry_run):
        print("  ⚠️  PostgreSQL load failed — screeners not updated")
        failed.append("PostgreSQL screeners")

    # 7a. Daily results-feed refresh — narrow, fast (only companies that
    #     filed results in the last 14d). Keeps the structured financials
    #     cache current so /strategy_council reads PG instead of scraping.
    if not args.skip_results_feed:
        if not step_refresh_results_feed(args.dry_run):
            print("  ⚠️  Results-feed refresh had failures — see scores.financials_refresh_log")
            failed.append("Results-feed refresh")

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
