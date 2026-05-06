#!/usr/bin/env python3
"""
Comprehensive NSE End-of-Day Pipeline
======================================
Single script to run the entire daily workflow after market close.

PG: This is the master orchestrator — replaces running multiple scripts manually.
    Imports functions directly for tighter integration and better error handling.

Pipeline:
  ┌─────────────────────────────────────────────────────────────────────┐
  │ STEP 0  Download NSE bhavcopy (stock + index data)                 │
  │ STEP 1  Fetch auxiliary data (FII/DII, F&O, events, insider, macro)│
  │ STEP 2  Comprehensive NSE universe analysis                        │
  │ STEP 3  Refresh global correlations                                │
  │ STEP 4  Generate full sector rotation report (HTML/MD/PDF)         │
  │ STEP 5  Email reports (optional)                                   │
  └─────────────────────────────────────────────────────────────────────┘

Usage:
  python daily_eod.py                    # full pipeline
  python daily_eod.py --skip-download    # skip bhavcopy download
  python daily_eod.py --skip-analysis    # skip heavy analysis, use existing CSV
  python daily_eod.py --skip-aux         # skip auxiliary fetches
  python daily_eod.py --email            # send report via email at the end
  python daily_eod.py --dry-run          # print plan without executing
  python daily_eod.py --quick            # skip download + aux (report only)
"""
from __future__ import annotations

import argparse
import os
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)  # PG: ensure all relative paths resolve correctly
sys.path.insert(0, str(ROOT))  # PG: ensure local imports work

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

_IST_OFFSET = 5.5 * 3600  # seconds


def _now_ist() -> str:
    utc = datetime.now(timezone.utc)
    ist_ts = utc.timestamp() + _IST_OFFSET
    return datetime.fromtimestamp(ist_ts, tz=timezone.utc).replace(tzinfo=None).strftime("%Y-%m-%d %H:%M IST")


def _section(title: str) -> None:
    print(f"\n{'═' * 70}")
    print(f"  {title}")
    print(f"{'═' * 70}")


def _step_ok(label: str, elapsed: float) -> None:
    print(f"  ✅ {label} ({elapsed:.0f}s)")


def _step_fail(label: str, error: str) -> None:
    print(f"  ❌ {label}: {error}")


def _step_skip(label: str, reason: str = "skipped by flag") -> None:
    print(f"  ⏭  {label} — {reason}")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 0 — Download NSE Bhavcopy Data
# ─────────────────────────────────────────────────────────────────────────────

def step_download_data(dry_run: bool = False) -> bool:
    """Download missing NSE bhavcopy archives (stock + index CSVs)."""
    _section("STEP 0 — Download NSE Bhavcopy Data")
    if dry_run:
        _step_skip("Bhavcopy download", "dry run")
        return True

    t0 = time.time()
    try:
        from download_nse_bhavcopy import download_missing_data
        result = download_missing_data(max_dates=60, delay=1.5)
        total = result.get("stock_rows", 0) + result.get("index_rows", 0)
        if total > 0:
            _step_ok(
                f"Downloaded {result['stock_dates']} stock dates ({result['stock_rows']} rows), "
                f"{result['index_dates']} index dates ({result['index_rows']} rows)",
                time.time() - t0,
            )
        else:
            _step_ok("Data already up to date — no missing dates", time.time() - t0)
        return True
    except Exception as exc:
        _step_fail("Bhavcopy download", str(exc))
        traceback.print_exc()
        return False


# ─────────────────────────────────────────────────────────────────────────────
# STEP 1 — Fetch Auxiliary Market Data
# ─────────────────────────────────────────────────────────────────────────────

def step_fetch_auxiliary(dry_run: bool = False) -> dict[str, bool]:
    """Fetch FII/DII flows, F&O signals, corporate events, insider alerts, macro proxies."""
    _section("STEP 1 — Fetch Auxiliary Market Data")
    if dry_run:
        _step_skip("Auxiliary data", "dry run")
        return {}

    results: dict[str, bool] = {}

    # PG: Each fetcher is imported and called directly for better error isolation
    fetchers = [
        ("FII/DII Flows", "fetch_fii_dii_flows", "generate_flow_signals", {}),
        ("F&O OI + PCR", "fetch_fno_data", "generate_fno_signals", {}),
        ("Corporate Events", "fetch_corporate_events", "fetch_all_events", {"force": False}),
        ("Insider Alerts", "fetch_insider_alerts", "generate_insider_alerts", {}),
        ("Macro Proxies", "fetch_macro_proxies", "generate_macro_signals", {}),
    ]

    for label, module_name, func_name, kwargs in fetchers:
        t0 = time.time()
        try:
            mod = __import__(module_name)
            fn = getattr(mod, func_name)
            fn(**kwargs)
            _step_ok(label, time.time() - t0)
            results[label] = True
        except Exception as exc:
            _step_fail(label, str(exc))
            results[label] = False
            # PG: Don't fail the pipeline on auxiliary errors — cached data will be used

    return results


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 — Comprehensive NSE Universe Analysis
# ─────────────────────────────────────────────────────────────────────────────

def step_comprehensive_analysis(dry_run: bool = False) -> bool:
    """
    Run the full NSE universe analysis to generate comprehensive_nse_enhanced_*.csv.
    PG: Imports functions directly from fixed_nse_universe_analysis.py instead of subprocess.
    """
    _section("STEP 2 — Comprehensive NSE Universe Analysis")
    if dry_run:
        _step_skip("Analysis", "dry run")
        return True

    t0 = time.time()
    try:
        from fixed_nse_universe_analysis import (
            initialize_database,
            load_stock_data,
            load_index_data,
            load_fundamental_data,
            load_company_names,
            analyze_stocks,
            analyze_nse_indices,
            save_stocks_to_database,
            save_indices_to_database,
            save_market_breadth_to_database,
            generate_markdown_report,
            DB_PATH,
            REPORTS_DIR as ANALYSIS_REPORTS_DIR,
        )

        # Initialize database
        initialize_database(DB_PATH)

        # Load data
        stock_data = load_stock_data()
        index_data = load_index_data()
        fundamental_data = load_fundamental_data()
        company_names = load_company_names()

        latest_date = stock_data["TIMESTAMP"].max()
        print(f"  Latest data date: {latest_date}")

        # Analyze stocks
        results = analyze_stocks(stock_data, index_data, fundamental_data, company_names, latest_date)
        results = results.sort_values("TECHNICAL_SCORE", ascending=False)
        print(f"  Analyzed {len(results)} stocks")

        # Analyze indices
        index_results = analyze_nse_indices(index_data, latest_date)
        print(f"  Analyzed {len(index_results)} indices")

        # Save to database
        save_stocks_to_database(results, latest_date, DB_PATH)
        save_indices_to_database(index_results, latest_date, DB_PATH)
        save_market_breadth_to_database(results, latest_date, DB_PATH)

        # Save comprehensive CSV
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        date_str = latest_date.strftime("%d%m%Y") if hasattr(latest_date, "strftime") else str(latest_date).replace("-", "")
        output_file = ANALYSIS_REPORTS_DIR / f"comprehensive_nse_enhanced_{date_str}_{timestamp}.csv"
        output_file.parent.mkdir(parents=True, exist_ok=True)
        results.to_csv(output_file, index=False)
        print(f"  CSV → {output_file.name}")

        # Generate markdown report
        generate_markdown_report(results, index_results, latest_date, timestamp)

        # Print signal summary
        if "TRADING_SIGNAL" in results.columns:
            signal_dist = results["TRADING_SIGNAL"].value_counts()
            summary = ", ".join(f"{s}={c}" for s, c in signal_dist.items())
            print(f"  Signals: {summary}")

        _step_ok(f"Analysis complete — {len(results)} stocks, {len(index_results)} indices", time.time() - t0)
        return True

    except Exception as exc:
        _step_fail("Comprehensive analysis", str(exc))
        traceback.print_exc()
        return False


# ─────────────────────────────────────────────────────────────────────────────
# STEP 3 — Refresh Global Correlations
# ─────────────────────────────────────────────────────────────────────────────

def step_global_correlations(dry_run: bool = False) -> bool:
    """Refresh global market correlations (Nifty 500 vs 9 global assets)."""
    _section("STEP 3 — Refresh Global Correlations")
    if dry_run:
        _step_skip("Global correlations", "dry run")
        return True

    t0 = time.time()
    try:
        from global_correlation import generate_global_correlations
        indices_df, corr_df = generate_global_correlations(force=True)
        n_assets = len(corr_df) if corr_df is not None else 0
        alerts = corr_df["alert"].notna().sum() if corr_df is not None and "alert" in corr_df.columns else 0
        _step_ok(f"{n_assets} assets correlated, {alerts} alert(s)", time.time() - t0)
        return True
    except ImportError:
        _step_skip("Global correlations", "yfinance not installed")
        return True  # non-critical
    except Exception as exc:
        _step_fail("Global correlations", str(exc))
        return False


# ─────────────────────────────────────────────────────────────────────────────
# STEP 4 — Generate Full Sector Rotation Report
# ─────────────────────────────────────────────────────────────────────────────

def step_generate_report(dry_run: bool = False) -> bool:
    """Generate the comprehensive sector rotation report (HTML/MD/PDF)."""
    _section("STEP 4 — Generate Sector Rotation Report")
    if dry_run:
        _step_skip("Report generation", "dry run")
        return True

    t0 = time.time()
    try:
        from sector_rotation_report import generate_report
        paths = generate_report(top_n_sectors=6, top_n_per_sector=8)
        print(f"  HTML → {paths.html.name}")
        print(f"  MD   → {paths.markdown.name}")
        if paths.pdf.exists():
            print(f"  PDF  → {paths.pdf.name}")
        _step_ok("Report generation complete", time.time() - t0)
        return True
    except Exception as exc:
        _step_fail("Report generation", str(exc))
        traceback.print_exc()
        return False


# ─────────────────────────────────────────────────────────────────────────────
# STEP 5 — Email Reports (optional)
# ─────────────────────────────────────────────────────────────────────────────

def step_email_reports(dry_run: bool = False) -> bool:
    """Send the generated reports via email."""
    _section("STEP 5 — Email Reports")
    if dry_run:
        _step_skip("Email", "dry run")
        return True

    t0 = time.time()
    try:
        from email_nse_reports import main as email_main
        email_main()
        _step_ok("Reports emailed", time.time() - t0)
        return True
    except Exception as exc:
        _step_fail("Email reports", str(exc))
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Main Orchestrator
# ─────────────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Comprehensive NSE End-of-Day Pipeline — download, analyze, report",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python daily_eod.py                    # full pipeline
  python daily_eod.py --quick            # report-only (skip download + aux)
  python daily_eod.py --skip-download    # use existing data files
  python daily_eod.py --skip-analysis    # use existing comprehensive CSV
  python daily_eod.py --email            # full pipeline + email
  python daily_eod.py --dry-run          # show plan without executing
        """,
    )
    parser.add_argument("--skip-download", action="store_true",
                        help="Skip NSE bhavcopy download (use existing stock/index CSVs)")
    parser.add_argument("--skip-analysis", action="store_true",
                        help="Skip comprehensive analysis (use existing CSV)")
    parser.add_argument("--skip-aux", action="store_true",
                        help="Skip auxiliary data fetch (FII/DII, F&O, events, macro)")
    parser.add_argument("--skip-correlations", action="store_true",
                        help="Skip global correlation refresh")
    parser.add_argument("--quick", action="store_true",
                        help="Quick mode: skip download + aux, just run analysis + report")
    parser.add_argument("--report-only", action="store_true",
                        help="Only regenerate the report from existing data")
    parser.add_argument("--email", action="store_true",
                        help="Send reports via email after generation")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print plan without executing anything")
    args = parser.parse_args()

    # PG: --quick is a shortcut for --skip-download --skip-aux
    if args.quick:
        args.skip_download = True
        args.skip_aux = True

    # PG: --report-only skips everything except report generation
    if args.report_only:
        args.skip_download = True
        args.skip_aux = True
        args.skip_analysis = True
        args.skip_correlations = True

    # ── Banner ───────────────────────────────────────────────────────────────
    print(f"\n{'╔' + '═' * 68 + '╗'}")
    print(f"{'║'} {'NSE End-of-Day Pipeline':^66s} {'║'}")
    print(f"{'║'} {'Started: ' + _now_ist():^66s} {'║'}")
    print(f"{'╚' + '═' * 68 + '╝'}")

    plan = []
    if not args.skip_download:
        plan.append("0. Download bhavcopy")
    if not args.skip_aux:
        plan.append("1. Fetch auxiliary data")
    if not args.skip_analysis:
        plan.append("2. Comprehensive analysis")
    if not args.skip_correlations:
        plan.append("3. Global correlations")
    plan.append("4. Generate report")
    if args.email:
        plan.append("5. Email reports")

    print(f"\n  Plan: {' → '.join(plan)}")
    if args.dry_run:
        print("\n  ⚠️  DRY RUN MODE — no commands will execute\n")

    failed: list[str] = []
    t_total = time.time()

    # ── STEP 0: Download ─────────────────────────────────────────────────────
    if not args.skip_download:
        if not step_download_data(args.dry_run):
            failed.append("Data download")
            print("  ⚠️  Download failed — continuing with existing data")
    else:
        _section("STEP 0 — Download NSE Bhavcopy Data")
        _step_skip("Bhavcopy download")

    # ── STEP 1: Auxiliary ─────────────────────────────────────────────────────
    if not args.skip_aux:
        aux_results = step_fetch_auxiliary(args.dry_run)
        # PG: Don't fail pipeline on auxiliary errors — they use cached data
    else:
        _section("STEP 1 — Fetch Auxiliary Market Data")
        _step_skip("Auxiliary data fetch")

    # ── STEP 2: Analysis ──────────────────────────────────────────────────────
    if not args.skip_analysis:
        if not step_comprehensive_analysis(args.dry_run):
            failed.append("Comprehensive analysis")
            print("  ⚠️  Analysis failed — report will use latest existing CSV")
    else:
        _section("STEP 2 — Comprehensive NSE Universe Analysis")
        _step_skip("Comprehensive analysis")

    # ── STEP 3: Global Correlations ───────────────────────────────────────────
    if not args.skip_correlations:
        if not step_global_correlations(args.dry_run):
            failed.append("Global correlations")
            # non-critical, continue
    else:
        _section("STEP 3 — Refresh Global Correlations")
        _step_skip("Global correlations")

    # ── STEP 4: Report ────────────────────────────────────────────────────────
    if not step_generate_report(args.dry_run):
        failed.append("Report generation")

    # ── STEP 5: Email (optional) ──────────────────────────────────────────────
    if args.email:
        if not step_email_reports(args.dry_run):
            failed.append("Email reports")

    # ── Summary ───────────────────────────────────────────────────────────────
    elapsed = time.time() - t_total
    print(f"\n{'╔' + '═' * 68 + '╗'}")
    if args.dry_run:
        print(f"{'║'} {'DRY RUN complete — no actual changes made':^66s} {'║'}")
    elif not failed:
        msg = f"✅ All steps completed successfully in {elapsed:.0f}s"
        print(f"{'║'} {msg:^66s} {'║'}")
    else:
        msg = f"⚠️  Completed with {len(failed)} failure(s) in {elapsed:.0f}s"
        print(f"{'║'} {msg:^66s} {'║'}")
        for f in failed:
            print(f"{'║'}   • {f:<64s} {'║'}")
    print(f"{'║'} {'Finished: ' + _now_ist():^66s} {'║'}")
    print(f"{'╚' + '═' * 68 + '╝'}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
