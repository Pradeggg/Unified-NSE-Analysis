#!/usr/bin/env python3
"""
Daily NSE Data Refresh Orchestrator — 7-Phase Pipeline
=======================================================
Run after NSE market close (~16:00 IST / 10:30 UTC). ~25–35 min wall-clock.

Usage:
  python daily_refresh.py                         # full pipeline
  python daily_refresh.py --live-only             # fast price update only (~1 min)
  python daily_refresh.py --skip-analysis         # skip heavy analysis, just tracker
  python daily_refresh.py --dry-run               # print plan without executing
  python daily_refresh.py --fundamentals-backfill # force Nifty 500 screener backfill
  python daily_refresh.py --skip-news             # skip yfinance news in fund dashboard

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 CRITICAL ORDERING RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

 PG-FUND-ORDER (2026-05-26)
   Step 2B (--fundamentals-only) MUST run BEFORE Step 4B (--snapshot).
   If fundamentals run after the snapshot, the Stage-2 HTML detail cards
   render NULL for Earnings Quality, Sales Growth, Financial Strength,
   and Institutional Backing — only Enhanced Fund Score appears.

 CSV-200-ORDER (2026-08-18)
   sector_rotation_tracker.py --snapshot requires ≥200 days of price
   history to compute SMA200 for Weinstein stages. If the local CSV
   (nse_sec_full_data.csv, ~95 days) is used, ALL stages become UNKNOWN.
   The tracker auto-falls-back to market.equity_eod (PostgreSQL, 500+
   days) when CSV has <200 days. Never bypass this check.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 PHASE 1 — DATA INGESTION                               (~3–5 min)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 Step 0   load_latest_nse_data_comprehensive.R
            NSE bhavcopy CSVs (bh*, pr*, hl*, mcap*, bm*.txt) → local disk
 Step 0B  postgres/loader.py --eod-only
            market.equity_eod + market.index_eod (2700+ rows today)
 Step 1   fetch_*.py  (FII/DII, F&O, corp events, insider alerts, macro)
            signals.fii_dii_flows, signals.corporate_events,
            signals.insider_alerts, macro.fred_series
 Step 1B  postgres/loader.py --fno-only
            derivatives.fno_eod (F&O daily chain analytics)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 PHASE 2 — SCORING                                      (~5–8 min)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 Step 2   fixed_nse_universe_analysis.py
            scores.daily_scores (tech + RS vs Nifty 500 percentile)
            RS formula: 40%×3m + 20%×6m + 20%×9m + 20%×12m momentum
            Universe: CLOSE>₹100, vol>100k; RS ranked within Nifty 500
 Step 2B  postgres/loader.py --fundamentals-only          ⚠️ PG-FUND-ORDER
            scores.fundamental_scores (5 sub-scores for all universe stocks)
            MUST complete before Step 4B tracker snapshot
 Step 3A  scripts.backfill_historical_stage_snapshots
            scores.stage_snapshots (history fill, ensures non-empty table)
 Step 2C  scripts/materialize_stage2_vcp_picks.py
            portfolio.vcp_candidates (point-in-time VCP candidates)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 PHASE 3 — STRATEGY LAB                                 (~3–5 min)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 Step 3B  portfolio.cli strategy-lab
            portfolio_strategy_lab.html (best strategy + VCP strategy tabs)
 QA       report_validation("portfolio_strategy_lab") — LLM QA checkpoint

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 PHASE 4 — STAGE & SECTOR                              (~5–8 min)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 Step 4B  sector_rotation_tracker.py --snapshot           ⚠️ CSV-200-ORDER
            scores.stage_snapshots (today's Weinstein stages, all universe)
            Requires ≥200d price history → auto-falls-back to market.equity_eod
            MUST run after Step 2B (PG-FUND-ORDER)
 Step 7   postgres/loader.py
            All 40 screeners → screener.screen_results
            Canonical snapshot load (SQLite → scores.stage_snapshots)
 Step 4B.5  repair_latest_stage_snapshot
            Patches STAGE_UNKNOWN rows using daily_scores fallback
 Step 4A  sector_rotation_report.py
            signal_log.csv, sector rotation HTML report
 Step 4C  sector_rotation_tracker.py --report --html
            Stage-2 HTML tracker (stage cards + strategy tabs)
 Step 4E  rrg_report.py
            Market breadth + RRG HTML (A/D, McClellan, TRIN, sector RRG)
 QA×2     Sector rotation + Stage-2 tracker report validation

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 PHASE 5 — PICKS & MARKET                              (~3–5 min)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 Step 5A  scripts.backfill_screener_fundamentals --symbols <picks>
            Screener.in fundamentals pre-refresh for today's top picks only
 Step 5A.5  fetch_corporate_events.py + fetch_insider_alerts.py (--force)
            signals.corporate_events, signals.insider_alerts (fresh)
 Step 5C  top_picks_report.py
            Top Investment Picks HTML (charts, fund scores, staged alerts)
 Step 5D  scripts/build_eod_market_report.py
            EOD market tape report HTML (breadth, sectors, movers)
 QA×2     Top picks + EOD market report validation

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 PHASE 6 — PORTFOLIO & FUND                            (~3–5 min)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 Step 6   terminal.portfolio_monitor (EOD)
            Personal portfolio EOD report (positions vs stage snapshot)
 Step 6B  terminal.swing_playbook --fresh
            Swing trading playbook HTML (stage+sector+top-picks context)
 Step 6C  tools/fund_refresh.py --no-open
            fund_dashboard.html — 5-tab dashboard for Aug SC + MC funds:
            • P&L tab: SC + MC tables (Entry/CMP/Qty/P&L%/Stop/Days)
            • Orders tab: position log from fund_holdings.json
            • Candidates tab: Stage-2/RS/Tech screened watch list
            • Fund Rules tab: SC/MC governance reference
            • Alerts tab: SL breach, Supertrend, Stage, RS, Fundamentals,
                          Corporate Events, Bulk Deals, News (yfinance)
            Data sources: yfinance prices, scores.stage_snapshots,
                          scores.quarterly_results, signals.corporate_events,
                          signals.bulk_block_deals, signals.insider_alerts
 QA       Portfolio EOD report validation

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 PHASE 7 — DISTRIBUTION & MAINTENANCE                  (~5–10 min)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 Step 5D  terminal.email_dispatcher top_picks
            Outlook draft email for Top Picks (--email-send to send now)
 Step 7A  generate_voice_briefing.py --no-tts
            Voice briefing script from signal_log.csv (no TTS/audio)
 Step 7b  scripts.refresh_results_feed (--days-back 14)
            scores.quarterly_results + financials cache (companies w/ fresh filings)
 Step 7c  scripts.analyze_daily_results (LLM, --days-back 1)
            scores.results_analysis (LLM analyst notes per filing)
 Step 8   scripts.backfill_screener_fundamentals (Sundays / --fundamentals-backfill)
            Full Nifty 500 + Microcap 250 screener.in fundamentals refresh
 Step 8A  analyze_all_indexes.R + analyze_all_sectors.R (--comprehensive only)
            reports/nse_analysis/2026/ (All Indexes + All Sectors HTML)
 Step 9   mutual_funds/working/daily_mf_refresh.py
            Smallcap fund daily research update + market check
 Step 8Z  Remove legacy SQLite artifacts (sector_rotation_tracker.db etc.)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 SINGLE SOURCE OF TRUTH: PostgreSQL nse_market
   All analysis reads from market.equity_eod (not raw CSV files).
   CSV files are loaded into PG in Phase 1 (Steps 0/0B) before any
   scoring or analysis begins. fund_refresh.py reads from scores.*
   and signals.* tables populated by Phases 1–5.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MAIN_WORKTREE_BASE = ROOT.parent.parent if ROOT.parent.name == ".worktrees" else ROOT
PYTHON = sys.executable


def _load_project_env() -> None:
    """Load project .env values for missing or empty process env vars."""
    env_paths = [ROOT / ".env", ROOT.parent / ".env"]
    if ROOT.parent.name == ".worktrees":
        env_paths.append(ROOT.parent.parent / ".env")
    for env_path in env_paths:
        if not env_path.exists():
            continue
        try:
            for line in env_path.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#") or "=" not in stripped:
                    continue
                key, value = stripped.split("=", 1)
                key = key.strip()
                if key and not os.environ.get(key):
                    os.environ[key] = value.strip().strip('"').strip("'")
        except OSError:
            continue


_load_project_env()

PG_DSN = (
    os.environ.get("AGENT_ADDA_PG_DSN")
    or os.environ.get("PG_DSN")
    or "dbname=nse_market user=nse_admin host=/tmp"
)
LEGACY_SQLITE_ARTIFACTS = [
    ROOT / "data" / "sector_rotation_tracker.db",
    ROOT / "data" / "sector_rotation_tracker.db-shm",
    ROOT / "data" / "sector_rotation_tracker.db-wal",
]

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

_IST_OFFSET = 5.5 * 3600   # seconds


def _now_ist() -> str:
    utc = datetime.now(timezone.utc)
    ist_ts = utc.timestamp() + _IST_OFFSET
    return datetime.fromtimestamp(ist_ts, tz=timezone.utc).replace(tzinfo=None).strftime("%Y-%m-%d %H:%M IST")


def _run(
    label: str,
    cmd: list[str],
    dry_run: bool = False,
    cwd: Path | None = None,
    env: dict | None = None,
    timeout: float | None = None,
) -> bool:
    """Run a subprocess step. Returns True on success."""
    print(f"\n{'─'*60}")
    print(f"▶  {label}")
    print(f"   {' '.join(str(c) for c in cmd)}")
    if dry_run:
        print("   [DRY RUN — skipped]")
        return True
    t0 = time.time()
    try:
        result = subprocess.run(
            cmd,
            cwd=str(cwd or ROOT),
            capture_output=False,
            env=env,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        elapsed = time.time() - t0
        print(f"   ❌ TIMED OUT after {elapsed:.0f}s")
        return False
    elapsed = time.time() - t0
    if result.returncode == 0:
        print(f"   ✅ Done in {elapsed:.0f}s")
        return True
    else:
        print(f"   ❌ FAILED (exit {result.returncode}) after {elapsed:.0f}s")
        return False


def _ensure_postgres_running(dry_run: bool = False) -> bool:
    """Start the local project PostgreSQL cluster if it is not already running."""
    if PG_DSN:
        try:
            import psycopg2
            with psycopg2.connect(PG_DSN) as conn, conn.cursor() as cur:
                cur.execute("SELECT 1")
            return True
        except Exception as exc:
            print(f"   ⚠️  PostgreSQL DSN check failed: {exc}")
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


def _latest_equity_eod_date() -> str | None:
    """Return the latest loaded equity EOD trade date from PostgreSQL."""
    try:
        import psycopg2

        conn = psycopg2.connect(PG_DSN)
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT max(trade_date)::text FROM market.equity_eod")
                row = cur.fetchone()
                return str(row[0]) if row and row[0] else None
        finally:
            conn.close()
    except Exception as exc:
        print(f"   ⚠️  Could not read latest equity EOD date: {exc}")
        return None


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

    # In git worktrees, the mutable data cache may live in the main checkout.
    data_root = (
        MAIN_WORKTREE_BASE
        if MAIN_WORKTREE_BASE != ROOT and (MAIN_WORKTREE_BASE / "data" / "nse_sec_full_data.csv").exists()
        else ROOT
    )
    script = ROOT / "load_latest_nse_data_comprehensive.R"
    if not script.exists():
        script = ROOT / "R" / "core" / "load_latest_nse_data_comprehensive.R"
    if not script.exists():
        print("   ❌ EOD downloader missing: load_latest_nse_data_comprehensive.R")
        return False
    # Pass PROJECT_ROOT so R script resolves paths relative to the data root.
    import os
    env = {**os.environ, "PROJECT_ROOT": str(data_root)}
    ok = _run(
        "Download latest NSE bhavcopy → data/nse-raw/ + data/",
        ["Rscript", str(script)],
        dry_run=dry_run,
        env=env,
    )
    if ok and not dry_run:
        print(f"   ✅ NSE data written to {data_root / 'data'}")
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


def step_refresh_stock_csv(dry_run: bool) -> bool:
    """Rebuild data/nse_sec_full_data.csv from PostgreSQL equity_eod (2+ years, EQ/BE series).

    This CSV is the price data source for pullback_recovery_screener.py / apex_resilience.
    Without this step the CSV goes stale and the screener fails MIN_HISTORY checks.
    CSV-200-ORDER: must run AFTER step_postgres_eod_load (Step 0B) so today's prices are in PG.
    """
    _section("STEP 1Z — Refresh nse_sec_full_data.csv from PostgreSQL")
    stock_csv = ROOT / "data" / "nse_sec_full_data.csv"
    if dry_run:
        print(f"  [dry-run] would rebuild {stock_csv} from market.equity_eod")
        return True
    script = (
        "import psycopg2, os; from pathlib import Path; "
        f"stock_csv = Path(r'{stock_csv}'); "
        "conn = psycopg2.connect(host='/tmp', dbname='nse_market', user='nse_admin'); "
        "cur = conn.cursor(); "
        "q = '''SELECT symbol AS \"SYMBOL\", trade_date AS \"TIMESTAMP\", open AS \"OPEN\", "
        "high AS \"HIGH\", low AS \"LOW\", close AS \"CLOSE\", volume AS \"TOTTRDQTY\", "
        "ROUND((turnover_cr * 1e7)::numeric, 0) AS \"TOTTRDVAL\" "
        "FROM market.equity_eod WHERE series IN ('EQ','BE','BZ','SM','ST') "
        "AND close IS NOT NULL AND close > 0 ORDER BY symbol, trade_date'''; "
        "tmp = stock_csv.with_suffix('.tmp'); "
        "f = open(tmp, 'w'); cur.copy_expert(f'COPY ({q}) TO STDOUT WITH CSV HEADER', f); "
        "f.close(); conn.close(); "
        "sz = os.path.getsize(tmp)/1e6; "
        "import shutil; shutil.move(str(tmp), str(stock_csv)); "
        f"print(f'  {{sz:.1f}} MB → {{stock_csv}}')"
    )
    return _run(
        f"Rebuild {stock_csv.name} from PostgreSQL equity_eod",
        [PYTHON, "-c", script],
        dry_run=dry_run,
        timeout=120,
    )


def step_comprehensive_analysis(dry_run: bool) -> bool:
    """Run the full NSE universe analysis and write scores.daily_scores directly."""
    _section("STEP 2 — Comprehensive NSE Universe Analysis")
    return _run(
        "NSE Universe Analysis",
        [PYTHON, "fixed_nse_universe_analysis.py", "--export-csv"],
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
    _section("STEP 4B — Stage 2 Tracker Snapshot")

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
    _section("STEP 4C — Stage 2 Tracker Report")
    return _run(
        "Stage 2 Tracker HTML Report",
        [PYTHON, "sector_rotation_tracker.py", "--report", "--html"],
        dry_run=dry_run,
    )


def step_sector_rotation_report(dry_run: bool) -> bool:
    """Regenerate full sector rotation report — populates signal_log.csv."""
    _section("STEP 4A — Sector Rotation Report")
    ok = _run(
        "Sector Rotation Report",
        [PYTHON, "sector_rotation_report.py"],
        dry_run=dry_run,
    )
    if ok:
        # 4A-SL: Sync signal_log.csv → signals.signal_log (PG) and resolve open signals.
        _run(
            "Sync signal_log.csv → signals.signal_log (PG)",
            [PYTHON, "scripts/sync_signal_log_to_pg.py", "--days-back", "7", "--resolve"],
            dry_run=dry_run,
            timeout=60,
        )
    return ok


def step_materialize_stage2_vcp_picks(dry_run: bool) -> bool:
    """Persist Stage 2 VCP candidates into PG for strategy lab + reports."""
    _section("STEP 2C — Materialize Stage 2 VCP Picks (PostgreSQL)")
    if not _ensure_postgres_running(dry_run=dry_run):
        return False
    return _run(
        "Materialize scores.stage2_vcp_picks",
        [PYTHON, "scripts/materialize_stage2_vcp_picks.py", "--lookback-days", "365"],
        dry_run=dry_run,
    )


def step_rrg_breadth_report(dry_run: bool) -> bool:
    """Generate the Market Breadth + RRG report (3 views: cap-size, sector, thematic)."""
    _section("STEP 4E — Market Breadth & RRG Report")
    return _run(
        "Market Breadth + RRG (broad / sector / thematic)",
        [PYTHON, "rrg_report.py"],
        dry_run=dry_run,
        timeout=360,
    )


def step_top_picks_report(dry_run: bool) -> bool:
    """Generate Top Investment Picks Analysis (merges sector rotation + stage-2 tracker)."""
    _section("STEP 5C — Top Investment Picks Detailed Report")
    cmd = [PYTHON, "top_picks_report.py"]
    if os.environ.get("TOP_PICKS_FORCE_RULE_BASED") == "1":
        cmd.append("--no-llm")
    return _run(
        "Top Investment Picks Analysis",
        cmd,
        dry_run=dry_run,
        timeout=300,
    )


def step_eod_market_report(dry_run: bool) -> bool:
    """Generate the intraday-backed EOD Market Report."""
    _section("STEP 5D — EOD Market Report")
    return _run(
        "EOD Market Report",
        [PYTHON, "scripts/build_eod_market_report.py", "--no-open"],
        dry_run=dry_run,
    )


def step_report_validation(checkpoint: str, dry_run: bool) -> bool:
    """Run LLM-assisted report QA for a logical report checkpoint."""
    _section(f"REPORT QA — {checkpoint}")
    cmd = [PYTHON, "report_validation.py", "--checkpoint", checkpoint]
    if dry_run:
        cmd.extend(["--dry-run", "--skip-llm"])
    return _run(
        f"Report validation ({checkpoint})",
        cmd,
        dry_run=dry_run,
    )


def step_historical_stage_backfill(dry_run: bool) -> bool:
    """Backfill deterministic historical stage snapshots from EOD data.

    This keeps scores.stage_snapshots usable for portfolio backtests from
    Jan 2025 onward while preserving richer existing daily tracker snapshots.
    """
    _section("STEP 3A — Historical Stage Snapshot Backfill")
    if not _ensure_postgres_running(dry_run=dry_run):
        return False
    return _run(
        "Historical Stage Snapshots → scores.stage_snapshots",
        [
            PYTHON,
            "-m",
            "scripts.backfill_historical_stage_snapshots",
            "--start",
            "2025-01-01",
            "--lookback",
            "2024-01-01",
        ],
        dry_run=dry_run,
    )


def step_repair_latest_stage_snapshot(dry_run: bool) -> bool:
    """Overwrite the latest EOD snapshot with deterministic STAGE_1/2/3/4 values."""
    _section("STEP 4B.5 — Repair Latest Stage Snapshot")
    if not _ensure_postgres_running(dry_run=dry_run):
        return False
    latest_date = _latest_equity_eod_date()
    if not latest_date:
        print("   ⚠️  No latest equity EOD date found for stage repair")
        return False
    return _run(
        f"Repair stage snapshot for {latest_date}",
        [
            PYTHON,
            "-m",
            "scripts.backfill_historical_stage_snapshots",
            "--start",
            latest_date,
            "--end",
            latest_date,
            "--lookback",
            "2024-01-01",
            "--replace-existing",
        ],
        dry_run=dry_run,
    )


def step_portfolio_strategy_lab(
    dry_run: bool,
    *,
    output_dir: str,
    top_n: int,
    slippage_bps: float,
    brokerage_bps: float,
) -> bool:
    """Run PostgreSQL-backed paper strategy comparison and Agent Adda report."""
    _section("STEP 3B — Portfolio Strategy Lab")
    if not _ensure_postgres_running(dry_run=dry_run):
        return False
    ok = _run(
        "Portfolio strategy-lab replay",
        [
            PYTHON,
            "-m",
            "portfolio.cli",
            "strategy-lab",
            "--output-dir",
            output_dir,
            "--start",
            "2025-01-01",
            "--lookback",
            "2024-01-01",
            "--top-n",
            str(top_n),
            "--slippage-bps",
            str(slippage_bps),
            "--brokerage-bps",
            str(brokerage_bps),
            "--run-id",
            "NSE-PG-DAILY-STRATEGY-LAB",
        ],
        dry_run=dry_run,
    )
    if not ok:
        return False
    return _run(
        "Agent Adda strategy-lab report",
        [
            PYTHON,
            "-c",
            "from terminal.reports import generate_preset_report; "
            "r=generate_preset_report('strategy-lab','html'); "
            "print(r.get('path')); print(r.get('latest_path',''))",
        ],
        dry_run=dry_run,
    )


def step_portfolio_monitor(dry_run: bool, *, intraday: bool = False) -> bool:
    """Generate the PostgreSQL-backed personal portfolio monitor view."""
    label = "Intraday" if intraday else "EOD"
    _section(f"STEP 6 — My Portfolio Monitor ({label})")
    if dry_run:
        print(f"  DRY-RUN: would generate {label.lower()} portfolio monitor")
        return True
    if not _ensure_postgres_running(dry_run=dry_run):
        return False
    try:
        from terminal.portfolio_monitor import run_eod_report, run_intraday_view

        if intraday:
            result = run_intraday_view()
        else:
            result = run_eod_report()
        if isinstance(result, dict):
            return bool(result.get("success"))
        return bool(result)
    except Exception as exc:
        print(f"  portfolio monitor failed: {exc}")
        return False


def step_fund_dashboard(dry_run: bool) -> bool:
    """Refresh the Aug Fund dashboard (fund_holdings.json → live prices → DB → HTML)."""
    _section("STEP 6C — Aug Fund Dashboard Refresh")
    fund_refresh = Path(__file__).parent / "tools" / "fund_refresh.py"
    if not fund_refresh.exists():
        print("  ⚠️  tools/fund_refresh.py not found — skipping fund dashboard")
        return True  # non-fatal: fund dashboard is supplementary
    return _run(
        "Aug Fund dashboard → reports/latest/fund_dashboard.html",
        [PYTHON, str(fund_refresh), "--no-open"],
        dry_run=dry_run,
        timeout=120,
    )


def step_swing_playbook(dry_run: bool) -> bool:
    """Generate the swing trading playbook from fresh PostgreSQL/report context."""
    _section("STEP 6B — Swing Trading Playbook")
    return _run(
        "Swing trading playbook report",
        [
            PYTHON,
            "-c",
            "from terminal.swing_playbook import generate_swing_playbook, parse_swing_playbook_args; "
            "options=parse_swing_playbook_args('/swing-playbook --fresh'); "
            "result=generate_swing_playbook(options=options); "
            "print(result.html_path); "
            "print(result.markdown_path); "
            "raise SystemExit(0 if result.success else 1)",
        ],
        dry_run=dry_run,
    )


def step_mf_smallcap_refresh(dry_run: bool, run_date: str | None = None) -> bool:
    """Run the daily Agent Adda Smallcap Portfolio refresh (research update + market check)."""
    _section("STEP 9 — Smallcap Fund Portfolio Refresh")
    cmd = [
        PYTHON,
        str(ROOT / "mutual_funds" / "working" / "daily_mf_refresh.py"),
    ]
    if run_date:
        cmd += ["--run-date", run_date]
    return _run("Smallcap fund: research update + market check", cmd, dry_run=dry_run)


def step_publish_www(dry_run: bool, run_date: str | None = None) -> bool:
    """Publish daily reports to agentadda/www repo (→ agentadda.in/stocks/reports).

    Publishes: sector_rotation, stage2_tracker, swing_playbook, eod_market.
    Non-fatal — failure here must not block the rest of the pipeline.
    """
    _section("STEP 9W — Publish Reports to agentadda/www")
    presets = ["sector_rotation", "stage2_tracker", "swing_playbook", "eod_market"]
    date_arg = run_date or datetime.now().strftime("%Y-%m-%d")
    cmd = [PYTHON, "scripts/push_to_www.py", "--all-daily", "--push", "--date", date_arg]
    if dry_run:
        cmd.append("--dry-run")
    ok = _run("Publish reports → agentadda.in", cmd, dry_run=dry_run)
    return ok


def step_cleanup_legacy_sqlite(dry_run: bool) -> bool:
    """Remove transient legacy SQLite artifacts after PostgreSQL load completes."""
    _section("STEP 8Z — Legacy SQLite Artifact Cleanup")
    removed = 0
    for path in LEGACY_SQLITE_ARTIFACTS:
        if dry_run:
            print(f"  DRY-RUN: would remove {path.relative_to(ROOT)} if present")
            continue
        try:
            if path.exists():
                path.unlink()
                removed += 1
                print(f"  removed {path.relative_to(ROOT)}")
        except Exception as exc:
            print(f"  ⚠️  could not remove {path.relative_to(ROOT)}: {exc}")
            return False
    if not dry_run:
        print(f"  cleaned {removed} legacy SQLite artifact(s)")
    return True


def step_refresh_corporate_events(dry_run: bool) -> bool:
    """Refresh corporate events + insider alerts from NSE and load into
    signals.corporate_events and signals.insider_alerts. Non-fatal."""
    _section("STEP 5B — Corporate Events + Insider Alerts Refresh")
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
        with psycopg2.connect(PG_DSN) as conn:
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
    _section("STEP 5D — Email Top Investment Picks (draft in Outlook)")
    cmd = [PYTHON, "-m", "terminal.email_dispatcher", "top_picks", "--mode", "both"]
    if send:
        cmd.append("--send")
    return _run("Email Top Picks", cmd, dry_run=dry_run)


def step_voice_briefing(dry_run: bool) -> bool:
    """Generate today's voice briefing script from fresh signal_log.csv data."""
    _section("STEP 7A — Voice Briefing (script only, no audio)")
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


def step_broker_research_crawl(
    symbol: str,
    dry_run: bool,
    max_sources: int | None = None,
    runner=None,
    conn=None,
) -> bool:
    """Run an explicit bounded public broker research crawl for one symbol."""
    _section("Broker Research Crawl")
    clean_symbol = (symbol or "").strip().upper()
    if not clean_symbol:
        print("   ❌ Broker crawl requires a symbol")
        return False
    print(f"   Symbol: {clean_symbol}")
    if max_sources:
        print(f"   Max sources: {max_sources}")
    if dry_run:
        print("   [DRY RUN — skipped]")
        return True
    try:
        from company_intelligence_pg import connect
        from broker_research.scheduler import run_scheduled_broker_crawl

        run = runner or run_scheduled_broker_crawl
        db = conn or connect(PG_DSN)
        try:
            result = run(conn=db, symbol=clean_symbol, max_sources=max_sources)
        finally:
            if conn is None:
                db.close()
        print(f"   Sources scanned: {result.sources_seen}")
        print(f"   Sources succeeded: {result.sources_succeeded}")
        print(f"   Sources failed: {result.sources_failed}")
        print(f"   Links discovered: {result.links_discovered}")
        print(f"   Reports stored: {result.reports_stored}")
        return result.sources_failed == 0
    except Exception as exc:
        print(f"   ❌ Broker research crawl failed: {exc}")
        return False


def step_screener_fundamentals_backfill(
    dry_run: bool,
    index: str = "NIFTY 500",
    delay: float = 2.5,
    skip_fresh_days: int = 7,
) -> bool:
    """Refresh PG fundamentals cache for the given index via screener.in.

    Polite (delay+jitter) by default; only re-scrapes symbols whose snapshot
    is older than ``skip_fresh_days`` so weekly runs cost ~zero on no-op days.
    After scraping, recomputes scores.fundamental_scores from the fresh data.
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
    ok = _run(f"Screener fundamentals backfill ({index})", cmd, dry_run=dry_run)
    if ok:
        _run(
            "Recompute fundamental scores from fresh screener data",
            [PYTHON, "-m", "scripts.compute_fund_scores_from_db", "--universe", "all"],
            dry_run=dry_run,
        )
    return ok


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


def step_analyze_daily_results(
    dry_run: bool,
    days_back: int = 1,
    limit: int = 200,
    skip_llm: bool = False,
) -> bool:
    """LLM-driven analysis of every company that filed today's results.

    Reads the cache populated by ``step_refresh_results_feed``, builds an
    evidence pack per symbol, calls the Research-Council LLM and persists
    a structured analyst note into ``scores.results_analysis``. Per-stock
    HTML reports are written under
    ``reports/results_analysis/<YYYY>/<YYYYMMDD>/``.
    """
    _section(f"STEP 7c — Daily Results Analysis (last {days_back}d)")
    if not _ensure_postgres_running(dry_run=dry_run):
        return False
    cmd = [
        PYTHON, "-u", "-m", "scripts.analyze_daily_results",
        "--days-back", str(days_back),
        "--limit", str(limit),
    ]
    if skip_llm:
        cmd.extend(["--skip-llm", "--skip-filing"])
        return _run("Daily results analysis (rules)", cmd, dry_run=dry_run, timeout=300)

    ok = _run("Daily results analysis (LLM)", cmd, dry_run=dry_run, timeout=600)
    if ok:
        return True

    print("  ⚠️  LLM results analysis failed or timed out; retrying rule-based fallback")
    fallback_cmd = [*cmd, "--skip-llm", "--skip-filing"]
    return _run("Daily results analysis (rule fallback)", fallback_cmd, dry_run=dry_run, timeout=300)


def step_comprehensive_r_reports(dry_run: bool) -> bool:
    """Run R-based comprehensive reports: All Indexes + All Sectors HTML.

    R scripts use PROJECT_ROOT env var to resolve paths locally.
    Outputs are written to local reports/nse_analysis/2026/.
    """
    _section("STEP 8A — Comprehensive R Reports (Indexes + Sectors)")

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
    parser.add_argument("--skip-results-analysis", action="store_true",
                        help="Skip the LLM-driven daily results analysis report")
    parser.add_argument("--results-analysis-days-back", type=int, default=1,
                        help="Analyser window in calendar days (default 1)")
    parser.add_argument("--results-analysis-limit", type=int, default=10,
                        help="Maximum filings to analyse in daily refresh (default 10; raise for manual deep runs)")
    parser.add_argument("--results-analysis-skip-llm", action="store_true",
                        help="Run analyser with stub output (no LLM call)")
    parser.add_argument("--skip-portfolio-lab", action="store_true",
                        help="Skip historical stage backfill and portfolio strategy-lab report")
    parser.add_argument("--skip-report-validation", action="store_true",
                        help="Skip LLM-assisted report QA checkpoints")
    parser.add_argument("--portfolio-lab-output-dir",
                        default="portfolio/data/nse_pg_strategy_lab/latest",
                        help="Output directory for portfolio strategy-lab artifacts")
    parser.add_argument("--portfolio-top-n", type=int, default=200,
                        help="Top liquid NSE symbols for portfolio strategy-lab")
    parser.add_argument("--portfolio-slippage-bps", type=float, default=5.0,
                        help="Slippage bps for portfolio strategy-lab fills")
    parser.add_argument("--portfolio-brokerage-bps", type=float, default=3.0,
                        help="Brokerage bps for portfolio strategy-lab fills")
    parser.add_argument("--skip-rrg", action="store_true",
                        help="Skip the Market Breadth & RRG report (STEP 4E)")
    parser.add_argument("--skip-email", action="store_true",
                        help="Skip the Top Picks email step (STEP 5D)")
    parser.add_argument("--email-send", action="store_true",
                        help="Send Top Picks email immediately instead of opening as Outlook draft")
    parser.add_argument("--fundamentals-index",
                        default="NIFTY 500,NIFTY MICROCAP 250",
                        help="Index label(s) for fundamentals backfill (comma-separated). "
                             "Default: NIFTY 500 ∪ NIFTY MICROCAP 250 (~750 symbols).")
    parser.add_argument("--enrich-missing", type=int, default=10, metavar="N",
                        help="During tracker snapshot, live-scrape screener.in for up to N "
                             "symbols missing from the PG fund cache (default 10). Set 0 to disable. "
                             "High values (>20) trigger many HTTP calls and can cause SIGURG kills on macOS.")
    parser.add_argument("--enrich-delay", type=float, default=2.5,
                        help="Seconds between enrichment screener.in calls (default: 2.5)")
    parser.add_argument("--enrich-yfinance-fallback", action="store_true", default=True,
                        help="On screener failure, fall back to yfinance ratios (default: ON)")
    parser.add_argument("--broker-crawl",
                        help="Optional bounded public broker research crawl for one NSE symbol")
    parser.add_argument("--broker-crawl-max-sources", type=int, default=0,
                        help="Maximum broker index sources to crawl when --broker-crawl is set")
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

    # 1Z. Rebuild nse_sec_full_data.csv from PostgreSQL (after EOD load so today's prices are in PG).
    #     Required by pullback_recovery_screener.py / apex_resilience_full_report.py which need
    #     ≥307 trading sessions per symbol (52W rolling peak + SMA50 cushion).
    #     CSV-200-ORDER (2026-08-18): must run after Step 0B.
    if not args.skip_analysis:
        if not step_refresh_stock_csv(args.dry_run):
            print("\n  ⚠️  nse_sec_full_data.csv rebuild failed (non-fatal) — screener may use stale data")

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

    # 3A. Historical stage backfill runs BEFORE materialize_stage2_vcp_picks so
    # that scores.stage_snapshots already contains real STAGE_1/2/3/4 rows when
    # the VCP materialization queries it. On a fresh DB the table is empty and
    # materialize will raise RuntimeError("scores.stage_snapshots is empty").
    if not args.skip_portfolio_lab:
        if not step_historical_stage_backfill(args.dry_run):
            print("  ⚠️  Historical stage backfill failed — portfolio lab may use stale stages")
            failed.append("Historical stage backfill")

    # 2C. Persist VCP candidates before strategy lab. The portfolio lab's
    # persisted_vcp_picks_v1 strategy and Top Picks report both consume this
    # point-in-time table. Runs after the stage backfill so stage_snapshots is
    # populated even on a fresh DB.
    if not step_materialize_stage2_vcp_picks(args.dry_run):
        failed.append("Stage 2 VCP pick materialization")
        print("\n  ⚠️  VCP pick materialization failed — persisted VCP strategy may be empty")

    # 3. Portfolio strategy lab. The Stage 2 tracker reads this artifact
    # to render the Best Strategy and VCP Strategy tabs.
    if not args.skip_portfolio_lab:
        if not step_portfolio_strategy_lab(
            args.dry_run,
            output_dir=args.portfolio_lab_output_dir,
            top_n=args.portfolio_top_n,
            slippage_bps=args.portfolio_slippage_bps,
            brokerage_bps=args.portfolio_brokerage_bps,
        ):
            print("  ⚠️  Portfolio strategy lab failed — see logs above")
            failed.append("Portfolio strategy lab")
        elif not args.skip_report_validation:
            if not step_report_validation("portfolio_strategy_lab", args.dry_run):
                print("  ⚠️  Portfolio strategy-lab report QA failed (non-fatal)")
                failed.append("Report QA: portfolio strategy lab")

    # 4A. Stage 2 tracker snapshot first. The full PostgreSQL loader consumes
    # this SQLite snapshot and makes it the canonical scores.stage_snapshots
    # source for downstream reports.
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

    # 4B. PostgreSQL load + screeners. This must run after the tracker snapshot
    # and before sector rotation so the report reads the same canonical snapshot
    # that remains in PostgreSQL at the end of the run.
    if not step_postgres_load(args.dry_run):
        print("  ⚠️  PostgreSQL load failed — screeners not updated")
        failed.append("PostgreSQL screeners")

    # 4B.5. The tracker snapshot path may write STAGE_UNKNOWN when the upstream
    # comprehensive analysis has no STAGE column. Repair the latest canonical PG
    # snapshot before reports read it.
    if not args.skip_portfolio_lab:
        if not step_repair_latest_stage_snapshot(args.dry_run):
            print("  ⚠️  Latest stage snapshot repair failed — reports may show UNKNOWN stages")
            failed.append("Latest stage snapshot repair")

    if args.broker_crawl:
        if not step_broker_research_crawl(
            args.broker_crawl,
            args.dry_run,
            max_sources=args.broker_crawl_max_sources or None,
        ):
            failed.append("Broker research crawl")

    # 4C. Sector rotation report. This refreshes sector context and signal_log.csv
    # for downstream report links and briefing after canonical snapshot load.
    if not step_sector_rotation_report(args.dry_run):
        failed.append("Sector rotation report")
    elif not args.skip_report_validation:
        if not step_report_validation("sector_rotation", args.dry_run):
            print("  ⚠️  Sector rotation report QA failed (non-fatal)")
            failed.append("Report QA: sector rotation")

    # 4D. Stage 2 tracker HTML report. The HTML report consumes the freshly
    # generated portfolio strategy-lab artifact and canonical PG snapshot.
    if not step_generate_report(args.dry_run):
        failed.append("Stage 2 tracker report")
    elif not args.skip_report_validation:
        if not step_report_validation("stage2_tracker", args.dry_run):
            print("  ⚠️  Stage 2 tracker report QA failed (non-fatal)")
            failed.append("Report QA: stage2 tracker")

    # 4E. Market Breadth & RRG — reads from market.index_eod + market.equity_eod
    #     (populated by STEP 0B). Non-fatal; LLM narratives are best-effort.
    if not args.skip_rrg:
        if not step_rrg_breadth_report(args.dry_run):
            print("  ⚠️  Market Breadth & RRG report failed (non-fatal) — see logs above")
            failed.append("Market Breadth & RRG report")

    # 5A. Pre-refresh screener fundamentals for today's top picks (shareholding,
    #     ratios, structured financials) so the report below renders complete.
    if not step_refresh_top_picks_fundamentals(args.dry_run):
        print("  ⚠️  Top picks fundamentals pre-refresh failed — report may have gaps")
        # non-fatal; carry on to the report

    # 5A.5  Refresh corporate events (NSE → signals.corporate_events) so the
    #       per-stock 'Corporate Events' panel is fresh. Non-fatal.
    if not step_refresh_corporate_events(args.dry_run):
        print("  ⚠️  Corporate events refresh failed (non-fatal) — see logs above")

    # 5. Independent Top Investment Picks detailed report with charts.
    if not step_top_picks_report(args.dry_run):
        failed.append("Top investment picks report")
    elif not args.skip_report_validation:
        if not step_report_validation("top_picks", args.dry_run):
            print("  ⚠️  Top picks report QA failed (non-fatal)")
            failed.append("Report QA: top picks")

    # 5D. Intraday-backed EOD market tape report.
    if not step_eod_market_report(args.dry_run):
        failed.append("EOD market report")
    elif not args.skip_report_validation:
        if not step_report_validation("eod_market", args.dry_run):
            print("  ⚠️  EOD market report QA failed (non-fatal)")
            failed.append("Report QA: EOD market")

    # 6. My portfolio EOD report from latest PostgreSQL stage snapshot.
    if not step_portfolio_monitor(args.dry_run, intraday=False):
        failed.append("My portfolio EOD report")
    elif not args.skip_report_validation:
        if not step_report_validation("portfolio_eod", args.dry_run):
            print("  ⚠️  Portfolio EOD report QA failed (non-fatal)")
            failed.append("Report QA: portfolio EOD")

    # 6B. Swing playbook uses fresh stage, sector, top-picks, and portfolio context.
    if not step_swing_playbook(args.dry_run):
        failed.append("Swing trading playbook")

    # 6C. Aug Fund dashboard — reads fund_holdings.json, fetches live prices via
    #     yfinance, queries DB for stage/fundamentals/results, computes P&L per
    #     position, applies fund-rules compliance gate, writes fund_dashboard.html.
    #     Non-fatal: missing fund_refresh.py is silently skipped.
    if not step_fund_dashboard(args.dry_run):
        print("  ⚠️  Fund dashboard refresh failed (non-fatal) — see logs above")
        failed.append("Fund dashboard")

    # 5C. Email Top Picks report (opens as Outlook draft; --email-send to send)
    if not args.skip_email:
        if not step_email_top_picks(args.dry_run, send=args.email_send):
            print("  ⚠️  Top Picks email step failed (non-fatal) — see logs above")
            failed.append("Top Picks email")

    # 6. Voice briefing — generates script from fresh signal_log.csv (fast, no LLM)
    if not step_voice_briefing(args.dry_run):
        failed.append("Voice briefing")

    # 7a. Daily results-feed refresh — narrow, fast (only companies that
    #     filed results in the last 14d). Keeps the structured financials
    #     cache current so /strategy_council reads PG instead of scraping.
    if not args.skip_results_feed:
        if not step_refresh_results_feed(args.dry_run):
            print("  ⚠️  Results-feed refresh had failures — see scores.financials_refresh_log")
            failed.append("Results-feed refresh")

    # 7c. LLM-driven results analysis — runs after the cache refresh so
    #     the evidence pack reads fresh PG rows. Skipped on --skip-results-analysis
    #     or when the upstream feed step was skipped.
    if not args.skip_results_analysis and not args.skip_results_feed:
        if not step_analyze_daily_results(
            args.dry_run,
            days_back=args.results_analysis_days_back,
            limit=args.results_analysis_limit,
            skip_llm=args.results_analysis_skip_llm,
        ):
            print("  ⚠️  Daily results analysis had failures — see scores.financials_refresh_log")
            failed.append("Daily results analysis")

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

    # 9. Smallcap fund portfolio daily refresh (research update + market check).
    #    Non-fatal: failure here must not block the rest of the pipeline.
    if not step_mf_smallcap_refresh(args.dry_run):
        print("  ⚠️  Smallcap fund refresh failed (non-fatal) — see logs above")
        failed.append("Smallcap fund refresh")

    if not step_cleanup_legacy_sqlite(args.dry_run):
        failed.append("Legacy SQLite cleanup")

    # 9W. Publish daily HTML reports to agentadda/www → agentadda.in/stocks/reports.
    #     Non-fatal: failure here must not block the pipeline summary.
    if not step_publish_www(args.dry_run, run_date=args.run_date if hasattr(args, "run_date") else None):
        print("  ⚠️  www publish failed (non-fatal) — reports committed locally, push manually")
        failed.append("www publish (non-fatal)")

    # 9X. Rebuild docs/PROJECT_RESEARCH.md with live KB + PG stats.
    #     Non-fatal: never blocks the pipeline.
    if not args.dry_run:
        try:
            import importlib.util, subprocess as _sp
            _res = _sp.run(
                [PYTHON, "scripts/build_project_research.py"],
                cwd=ROOT,
                timeout=60,
            )
            if _res.returncode != 0:
                print("  ⚠️  PROJECT_RESEARCH.md rebuild failed (non-fatal)")
        except Exception as _e:
            print(f"  ⚠️  PROJECT_RESEARCH.md rebuild error (non-fatal): {_e}")

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
