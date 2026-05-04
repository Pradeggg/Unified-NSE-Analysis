#!/usr/bin/env python3
"""
Sector Rotation Stage Tracker
==============================
Captures daily EOD snapshots of the Stage screener results into a SQLite
database and computes day-over-day / week-over-week changes.

Usage
-----
  # Capture today's snapshot (idempotent – safe to re-run):
  python sector_rotation_tracker.py --snapshot

  # Print change report (default: compare today vs yesterday + week ago):
  python sector_rotation_tracker.py --report

  # Use a custom comparison date:
  python sector_rotation_tracker.py --report --vs 2026-04-28

  # Save HTML change report:
  python sector_rotation_tracker.py --report --html

  # Full pipeline: snapshot + HTML report:
  python sector_rotation_tracker.py --all

Database
--------
  data/sector_rotation_tracker.db
  Tables:
    stage_snapshots  – one row per (snapshot_date, symbol)
    stage_changes    – pre-computed diffs written after each snapshot
"""
from __future__ import annotations

import argparse
import html
import json
import math
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "data" / "sector_rotation_tracker.db"
REPORTS_DIR = ROOT / "reports" / "sector_rotation"
STOCK_CSV = ROOT / "data" / "nse_sec_full_data.csv"

# ─────────────────────────────────────────────────────────────────────────────
# DB helpers
# ─────────────────────────────────────────────────────────────────────────────

DDL = """
CREATE TABLE IF NOT EXISTS stage_snapshots (
    snapshot_date  TEXT NOT NULL,          -- ISO date: YYYY-MM-DD
    symbol         TEXT NOT NULL,
    company_name   TEXT,
    stage          TEXT,                   -- STAGE_1 / STAGE_2 / STAGE_3 / STAGE_4 / UNKNOWN
    stage_score    REAL,
    price          REAL,                   -- price used in screener (from comprehensive CSV)
    live_price     REAL,                   -- Yahoo Finance live price fetched at snapshot time
    technical_score REAL,
    rsi            REAL,
    trading_signal TEXT,
    trend_signal   TEXT,
    relative_strength REAL,
    change_1d_pct  REAL,
    change_1w_pct  REAL,
    change_1m_pct  REAL,
    market_cap_cat TEXT,
    source_csv     TEXT,                   -- comprehensive CSV filename used
    PRIMARY KEY (snapshot_date, symbol)
);

CREATE TABLE IF NOT EXISTS stage_changes (
    change_date    TEXT NOT NULL,          -- date of the newer snapshot
    compare_date   TEXT NOT NULL,          -- date of the older snapshot
    symbol         TEXT NOT NULL,
    company_name   TEXT,
    stage_now      TEXT,
    stage_prev     TEXT,
    stage_changed  INTEGER,               -- 1 if stage changed, 0 if same
    price_now      REAL,
    price_prev     REAL,
    price_chg_pct  REAL,                  -- (price_now - price_prev) / price_prev * 100
    live_price     REAL,
    live_vs_prev_pct REAL,               -- (live_price - price_prev) / price_prev * 100
    stage_score_now  REAL,
    stage_score_prev REAL,
    trading_signal TEXT,
    change_type    TEXT,                  -- NEW_STAGE2 / EXIT_STAGE2 / STAGE_UP / STAGE_DOWN / UNCHANGED
    PRIMARY KEY (change_date, compare_date, symbol)
);

CREATE INDEX IF NOT EXISTS idx_snap_date   ON stage_snapshots (snapshot_date);
CREATE INDEX IF NOT EXISTS idx_snap_stage  ON stage_snapshots (snapshot_date, stage);
CREATE INDEX IF NOT EXISTS idx_chg_date    ON stage_changes   (change_date);
CREATE INDEX IF NOT EXISTS idx_chg_type    ON stage_changes   (change_date, change_type);
"""

MIGRATION_SQL: list[str] = [
    "ALTER TABLE stage_snapshots ADD COLUMN sector TEXT",
    "ALTER TABLE stage_snapshots ADD COLUMN fundamental_score REAL",
    "ALTER TABLE stage_snapshots ADD COLUMN enhanced_fund_score REAL",
    "ALTER TABLE stage_snapshots ADD COLUMN earnings_quality REAL",
    "ALTER TABLE stage_snapshots ADD COLUMN sales_growth REAL",
    "ALTER TABLE stage_snapshots ADD COLUMN financial_strength REAL",
    "ALTER TABLE stage_snapshots ADD COLUMN institutional_backing REAL",
    "ALTER TABLE stage_snapshots ADD COLUMN can_slim_score REAL",
    "ALTER TABLE stage_snapshots ADD COLUMN minervini_score REAL",
    "ALTER TABLE stage_snapshots ADD COLUMN investment_score REAL",
    "ALTER TABLE stage_snapshots ADD COLUMN fund_details TEXT",
    "ALTER TABLE stage_snapshots ADD COLUMN narrative TEXT",
    "ALTER TABLE stage_snapshots ADD COLUMN stance TEXT",
]


def _migrate_db(conn: sqlite3.Connection) -> None:
    for sql in MIGRATION_SQL:
        try:
            conn.execute(sql)
        except sqlite3.OperationalError:
            pass  # column already exists
    conn.commit()


_STAGE_ORDER = {"STAGE_1": 1, "STAGE_2": 2, "STAGE_3": 3, "STAGE_4": 4, "UNKNOWN": 5}


def get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(DDL)
    _migrate_db(conn)
    return conn


def list_snapshot_dates(conn: sqlite3.Connection) -> list[str]:
    cur = conn.execute("SELECT DISTINCT snapshot_date FROM stage_snapshots ORDER BY snapshot_date DESC")
    return [r[0] for r in cur.fetchall()]


def load_snapshot(conn: sqlite3.Connection, snap_date: str) -> pd.DataFrame:
    return pd.read_sql_query(
        "SELECT * FROM stage_snapshots WHERE snapshot_date=?", conn, params=(snap_date,)
    )


# ─────────────────────────────────────────────────────────────────────────────
# Data helpers
# ─────────────────────────────────────────────────────────────────────────────

def _latest_comprehensive_csv() -> Optional[Path]:
    candidates = list((ROOT / "reports" / "generated_csv").rglob("comprehensive_nse_enhanced_*.csv"))
    return max(candidates, key=lambda p: p.stat().st_mtime) if candidates else None


def _load_price_history() -> pd.DataFrame:
    if not STOCK_CSV.exists():
        return pd.DataFrame()
    print("  Loading price history from nse_sec_full_data.csv …")
    df = pd.read_csv(STOCK_CSV, usecols=["SYMBOL", "TIMESTAMP", "OPEN", "HIGH", "LOW", "CLOSE"])
    df["TIMESTAMP"] = pd.to_datetime(df["TIMESTAMP"])
    return df


def _run_screener(analysis: pd.DataFrame, hist: pd.DataFrame) -> pd.DataFrame:
    import sys
    sys.path.insert(0, str(ROOT))
    from screeners import run_stage_screener, enrich_with_stage
    df = analysis.rename(columns={"CURRENT_PRICE": "CLOSE"}).copy()
    return run_stage_screener(df, history=hist if not hist.empty else None)


def _fetch_live_prices(symbols: list[str]) -> dict[str, float]:
    """Fetch latest prices from Yahoo Finance (.NS suffix). Returns {symbol: price}."""
    try:
        import yfinance as yf
    except ImportError:
        print("  yfinance not available – skipping live prices.")
        return {}

    skip = {"LIQUID", "CASHIETF", "CPSEETF", "COMMOIETF", "GROWWLIQID", "LIQUIDPLUS",
            "LIQUIDADD", "LIQUIDCASE", "LIQUIDBETF", "LIQUID1", "LIQUIDBEES"}
    valid = [s for s in symbols if not any(k in s for k in skip)]
    results: dict[str, float] = {}

    print(f"  Fetching live prices for {len(valid)} symbols via Yahoo Finance …")
    for i in range(0, len(valid), 50):
        chunk = valid[i:i + 50]
        tickers = [f"{s}.NS" for s in chunk]
        try:
            data = yf.download(tickers, period="2d", progress=False, auto_adjust=True)
            close = data.get("Close", pd.DataFrame())
            if not close.empty:
                last = close.iloc[-1]
                for t in tickers:
                    sym = t.replace(".NS", "")
                    val = last.get(t)
                    if val is not None and pd.notna(val):
                        results[sym] = round(float(val), 2)
        except Exception as e:
            print(f"    Chunk {i}–{i+50} error: {e}")

    print(f"  Got live prices for {len(results)}/{len(valid)} symbols.")
    return results


# ─────────────────────────────────────────────────────────────────────────────
# Snapshot writer
# ─────────────────────────────────────────────────────────────────────────────

def _closest_snapshot(dates: list[str], target: date, max_gap_days: int = 10) -> Optional[str]:
    """Return the snapshot date closest to `target` (within max_gap_days), excluding today."""
    best, best_delta = None, max_gap_days + 1
    for d in dates:
        delta = abs((date.fromisoformat(d) - target).days)
        if delta < best_delta:
            best, best_delta = d, delta
    return best


def write_snapshot(
    snap_date: Optional[str] = None,
    fetch_live: bool = True,
    force: bool = False,
) -> int:
    """
    Capture today's stage screener results and write to DB.
    Returns number of rows written (0 if already exists and not forced).
    """
    today = snap_date or date.today().isoformat()
    conn = get_conn()

    existing = conn.execute(
        "SELECT COUNT(*) FROM stage_snapshots WHERE snapshot_date=?", (today,)
    ).fetchone()[0]
    if existing and not force:
        print(f"  Snapshot for {today} already exists ({existing} rows). Use --force to overwrite.")
        conn.close()
        return 0

    csv_path = _latest_comprehensive_csv()
    if csv_path is None:
        raise FileNotFoundError("No comprehensive_nse_enhanced_*.csv found in reports/generated_csv/")

    print(f"  Source CSV: {csv_path.name}")
    analysis = pd.read_csv(csv_path)
    hist = _load_price_history()
    screener_df = _run_screener(analysis, hist)

    live_prices: dict[str, float] = {}
    if fetch_live:
        live_prices = _fetch_live_prices(screener_df["SYMBOL"].tolist())

    # Build enrichment lookups
    sector_map = _build_sector_map()

    fund_cache: dict[str, dict] = {}
    fund_cache_path = ROOT / "data" / "_sector_rotation_fund_cache.csv"
    try:
        if fund_cache_path.exists():
            fc_df = pd.read_csv(fund_cache_path)
            for _, fcr in fc_df.iterrows():
                fund_cache[str(fcr.get("SYMBOL", "")).upper()] = fcr.to_dict()
    except Exception as e:
        print(f"  Warning: could not load fund cache: {e}")

    comp_lookup: dict[str, dict] = {}
    try:
        for _, cr in analysis.iterrows():
            comp_lookup[str(cr.get("SYMBOL", "")).upper()] = cr.to_dict()
    except Exception as e:
        print(f"  Warning: could not build comp lookup: {e}")

    rows = []
    for _, r in screener_df.iterrows():
        sym = str(r.get("SYMBOL", ""))
        sym_up = sym.upper()
        comp_row = comp_lookup.get(sym_up, {})
        fc_row = fund_cache.get(sym_up, {})

        base = {
            "snapshot_date": today,
            "symbol": sym,
            "company_name": str(r.get("COMPANY_NAME", "") or ""),
            "stage": str(r.get("STAGE", "UNKNOWN") or "UNKNOWN"),
            "stage_score": _f(r.get("STAGE_SCORE")),
            "price": _f(r.get("CLOSE") or r.get("CURRENT_PRICE")),
            "live_price": live_prices.get(sym),
            "technical_score": _f(r.get("TECHNICAL_SCORE")),
            "rsi": _f(r.get("RSI")),
            "trading_signal": str(r.get("TRADING_SIGNAL", "") or ""),
            "trend_signal": str(r.get("TREND_SIGNAL", "") or ""),
            "relative_strength": _f(r.get("RELATIVE_STRENGTH")),
            "change_1d_pct": _f(r.get("CHANGE_1D")),
            "change_1w_pct": _f(r.get("CHANGE_1W")),
            "change_1m_pct": _f(r.get("CHANGE_1M")),
            "market_cap_cat": str(r.get("MARKET_CAP_CATEGORY", "") or ""),
            "source_csv": csv_path.name,
            "sector": sector_map.get(sym_up, "Other"),
            "fundamental_score": _f(comp_row.get("FUNDAMENTAL_SCORE")),
            "enhanced_fund_score": _f(comp_row.get("ENHANCED_FUND_SCORE")),
            "earnings_quality": _f(comp_row.get("EARNINGS_QUALITY")),
            "sales_growth": _f(comp_row.get("SALES_GROWTH")),
            "financial_strength": _f(comp_row.get("FINANCIAL_STRENGTH")),
            "institutional_backing": _f(comp_row.get("INSTITUTIONAL_BACKING")),
            "can_slim_score": _f(comp_row.get("CAN_SLIM_SCORE")),
            "minervini_score": _f(comp_row.get("MINERVINI_SCORE")),
        }
        fund_details_dict: dict | None = None
        if fc_row:
            fund_details_dict = {
                "pnl_summary": fc_row.get("pnl_summary"),
                "quarterly_summary": fc_row.get("quarterly_summary"),
                "balance_sheet_summary": fc_row.get("balance_sheet_summary"),
                "ratios_summary": fc_row.get("ratios_summary"),
            }
        base["fund_details"] = json.dumps(fund_details_dict) if fund_details_dict else None
        base["investment_score"] = _investment_score(base)
        narrative_text, stance_val = _generate_narrative(base, fund_details_dict)
        base["narrative"] = narrative_text
        base["stance"] = stance_val
        rows.append(base)

    if existing and force:
        conn.execute("DELETE FROM stage_snapshots WHERE snapshot_date=?", (today,))

    conn.executemany(
        """INSERT OR REPLACE INTO stage_snapshots
            (snapshot_date, symbol, company_name, stage, stage_score, price, live_price,
             technical_score, rsi, trading_signal, trend_signal, relative_strength,
             change_1d_pct, change_1w_pct, change_1m_pct, market_cap_cat, source_csv,
             sector, fundamental_score, enhanced_fund_score, earnings_quality, sales_growth,
             financial_strength, institutional_backing, can_slim_score, minervini_score,
             investment_score, fund_details, narrative, stance)
           VALUES
            (:snapshot_date,:symbol,:company_name,:stage,:stage_score,:price,:live_price,
             :technical_score,:rsi,:trading_signal,:trend_signal,:relative_strength,
             :change_1d_pct,:change_1w_pct,:change_1m_pct,:market_cap_cat,:source_csv,
             :sector,:fundamental_score,:enhanced_fund_score,:earnings_quality,:sales_growth,
             :financial_strength,:institutional_backing,:can_slim_score,:minervini_score,
             :investment_score,:fund_details,:narrative,:stance)""",
        rows,
    )
    conn.commit()
    print(f"  Wrote {len(rows)} rows for {today} ({sum(1 for r in rows if r['stage']=='STAGE_2')} Stage 2).")

    # Auto-compute changes against previous available snapshot
    dates = list_snapshot_dates(conn)
    if len(dates) >= 2:
        _compute_changes(conn, dates[0], dates[1])   # today vs yesterday
    # Also vs ~7 days ago — find closest snapshot within ±3 days of a week ago
    week_target = datetime.fromisoformat(today).date() - timedelta(days=7)
    week_snap = _closest_snapshot(dates, week_target)
    if week_snap and week_snap != dates[1]:
        _compute_changes(conn, today, week_snap)

    conn.close()
    return len(rows)


def _f(v) -> Optional[float]:
    """Safe float conversion."""
    try:
        fv = float(v)
        return None if math.isnan(fv) else round(fv, 4)
    except (TypeError, ValueError):
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Sector map, investment score, narrative helpers
# ─────────────────────────────────────────────────────────────────────────────

_SECTOR_MAP_CACHE: dict | None = None


def _build_sector_map() -> dict[str, str]:
    global _SECTOR_MAP_CACHE
    if _SECTOR_MAP_CACHE is not None:
        return _SECTOR_MAP_CACHE
    result: dict[str, str] = {}
    try:
        import sys
        sys.path.insert(0, str(ROOT))
        from sector_rotation_report import SECTOR_KEYWORDS, ROTATING_INDEXES  # type: ignore
        # Invert SECTOR_KEYWORDS: symbol → sector
        for sector, symbols in SECTOR_KEYWORDS.items():
            for sym in symbols:
                result[sym.upper()] = sector
        # Load index_stock_mapping.csv if exists
        idx_map_path = ROOT / "data" / "index_stock_mapping.csv"
        if idx_map_path.exists():
            try:
                import pandas as _pd
                idx_df = _pd.read_csv(idx_map_path)
                # Expected cols: INDEX_NAME, SYMBOL (or similar)
                idx_col = next((c for c in idx_df.columns if "index" in c.lower()), None)
                sym_col = next((c for c in idx_df.columns if "symbol" in c.lower()), None)
                if idx_col and sym_col:
                    for _, row in idx_df.iterrows():
                        idx_name = str(row[idx_col])
                        sym = str(row[sym_col]).upper()
                        sector = ROTATING_INDEXES.get(idx_name)
                        if sector and sym not in result:
                            result[sym] = sector
            except Exception:
                pass
    except ImportError:
        pass
    _SECTOR_MAP_CACHE = result
    return result


def _investment_score(r: dict) -> float:
    """Composite investment score 0-100."""
    def _n(v, lo=0, hi=100):
        try:
            fv = float(v)
            return max(0.0, min(100.0, (fv - lo) / (hi - lo) * 100))
        except (TypeError, ValueError):
            return 50.0  # neutral

    tech = _n(r.get("technical_score"))
    fund = _n(r.get("enhanced_fund_score") if r.get("enhanced_fund_score") is not None else r.get("fundamental_score"))
    rs = _n(r.get("relative_strength"), -50, 50)
    stage_s = _n(r.get("stage_score"))

    # RSI: optimal 50-70 = 1.0, degrade outside
    try:
        rsi = float(r.get("rsi") or 50)
        if 50 <= rsi <= 70:
            rsi_score = 100.0
        elif rsi < 50:
            rsi_score = max(0, (rsi - 20) / 30 * 100)
        else:
            rsi_score = max(0, (90 - rsi) / 20 * 100)
    except (TypeError, ValueError):
        rsi_score = 50.0

    score = (tech * 0.30 + fund * 0.25 + rs * 0.15 + stage_s * 0.15 + rsi_score * 0.15)
    return round(score, 1)


def _generate_narrative(r: dict, fund_details: dict | None) -> tuple[str, str]:
    """Returns (narrative_text, stance)."""
    sym = str(r.get("symbol") or r.get("SYMBOL") or "")
    stage = str(r.get("stage") or "UNKNOWN")
    tech = r.get("technical_score")
    rsi_v = r.get("rsi")
    trend = str(r.get("trend_signal") or "")
    signal = str(r.get("trading_signal") or "")
    efund = r.get("enhanced_fund_score")
    fund = r.get("fundamental_score")
    eq = r.get("earnings_quality")
    sg = r.get("sales_growth")
    inv_s = r.get("investment_score") or _investment_score(r)

    # Determine stance
    try:
        inv_f = float(inv_s)
        if inv_f >= 65:
            stance = "BULLISH"
        elif inv_f <= 40:
            stance = "BEARISH"
        else:
            stance = "NEUTRAL"
    except (TypeError, ValueError):
        stance = "NEUTRAL"

    # Override stance based on signal
    sig_upper = signal.upper().replace(" ", "_")
    if sig_upper in ("STRONG_BUY", "BUY"):
        stance = "BULLISH"
    elif sig_upper in ("SELL"):
        stance = "BEARISH"

    # Tech sentence
    rsi_desc = "neutral"
    try:
        rv = float(rsi_v or 50)
        if rv >= 70:
            rsi_desc = "overbought"
        elif rv >= 55:
            rsi_desc = "bullish zone"
        elif rv >= 40:
            rsi_desc = "neutral"
        else:
            rsi_desc = "oversold"
    except (TypeError, ValueError):
        pass

    tech_str = f"Technical Score {tech:.0f}" if tech is not None else "Technical Score —"
    rsi_str = f"RSI {rsi_v:.0f} ({rsi_desc})" if rsi_v is not None else "RSI —"
    sig_str = signal if signal else "—"
    sent1 = f"{sym} ({stage.replace('_',' ')}) shows {'strong' if stance=='BULLISH' else 'weak' if stance=='BEARISH' else 'mixed'} momentum with {tech_str}, {rsi_str}, and a {sig_str} signal on {trend or 'trend'}."

    # Fundamental sentence
    fund_val = efund if efund is not None else fund
    fs = f"Enhanced Fund Score {fund_val:.0f}" if fund_val is not None else "Fund Score —"
    eq_s = f"Earnings Quality {eq:.0f}" if eq is not None else "Earnings Quality —"
    sg_s = f"Sales Growth {sg:.0f}" if sg is not None else "Sales Growth —"
    sent2 = f"Fundamentals: {fs}, {eq_s}, {sg_s}."

    # Action sentence
    action = {"BULLISH": "well-positioned for a trending move", "BEARISH": "caution advised — consider watching", "NEUTRAL": "suitable for monitoring on confirmation"}[stance]
    sent3 = f"Composite Investment Score {inv_s:.0f} — {action}."

    narrative = f"{sent1} {sent2} {sent3}"
    return narrative, stance


# ─────────────────────────────────────────────────────────────────────────────
# Change computation
# ─────────────────────────────────────────────────────────────────────────────

def _compute_changes(conn: sqlite3.Connection, date_new: str, date_old: str) -> int:
    """Compute and persist stage changes between two snapshot dates."""
    new_df = load_snapshot(conn, date_new)
    old_df = load_snapshot(conn, date_old)
    if new_df.empty or old_df.empty:
        return 0

    merged = new_df.merge(old_df[["symbol", "stage", "price", "stage_score"]],
                          on="symbol", how="outer", suffixes=("", "_prev"))
    rows = []
    for _, r in merged.iterrows():
        stage_now  = r.get("stage") or "UNKNOWN"
        stage_prev = r.get("stage_prev") or "UNKNOWN"
        p_now  = r.get("price")
        p_prev = r.get("price_prev")
        lp     = r.get("live_price")

        # Change type
        if stage_prev == "UNKNOWN" and stage_now == "STAGE_2":
            ctype = "NEW_STAGE2"
        elif stage_now == "STAGE_2" and stage_prev != "STAGE_2":
            ctype = "NEW_STAGE2"
        elif stage_prev == "STAGE_2" and stage_now != "STAGE_2":
            ctype = "EXIT_STAGE2"
        elif (_STAGE_ORDER.get(stage_now, 5) < _STAGE_ORDER.get(stage_prev, 5)):
            ctype = "STAGE_UP"
        elif (_STAGE_ORDER.get(stage_now, 5) > _STAGE_ORDER.get(stage_prev, 5)):
            ctype = "STAGE_DOWN"
        else:
            ctype = "UNCHANGED"

        def pct(a, b):
            try:
                return round((float(a) - float(b)) / float(b) * 100, 2)
            except (TypeError, ValueError, ZeroDivisionError):
                return None

        rows.append({
            "change_date":    date_new,
            "compare_date":   date_old,
            "symbol":         r.get("symbol", ""),
            "company_name":   r.get("company_name", ""),
            "stage_now":      stage_now,
            "stage_prev":     stage_prev,
            "stage_changed":  int(stage_now != stage_prev),
            "price_now":      _f(p_now),
            "price_prev":     _f(p_prev),
            "price_chg_pct":  pct(p_now, p_prev),
            "live_price":     _f(lp),
            "live_vs_prev_pct": pct(lp, p_prev),
            "stage_score_now": _f(r.get("stage_score")),
            "stage_score_prev": _f(r.get("stage_score_prev")),
            "trading_signal": r.get("trading_signal", ""),
            "change_type":    ctype,
        })

    conn.execute(
        "DELETE FROM stage_changes WHERE change_date=? AND compare_date=?",
        (date_new, date_old),
    )
    conn.executemany(
        """INSERT INTO stage_changes VALUES (
            :change_date,:compare_date,:symbol,:company_name,:stage_now,:stage_prev,
            :stage_changed,:price_now,:price_prev,:price_chg_pct,:live_price,
            :live_vs_prev_pct,:stage_score_now,:stage_score_prev,:trading_signal,:change_type)""",
        rows,
    )
    conn.commit()
    n_changed = sum(1 for r in rows if r["stage_changed"])
    print(f"  Changes {date_new} vs {date_old}: {n_changed} stage changes, {len(rows)} total rows.")
    return len(rows)


# ─────────────────────────────────────────────────────────────────────────────
# Change report
# ─────────────────────────────────────────────────────────────────────────────

def build_change_report(
    snap_date: Optional[str] = None,
    vs_date: Optional[str] = None,
    also_vs_week: bool = True,
) -> dict:
    """
    Return a dict with:
      - stage2_now: list of current Stage 2 stocks with live prices
      - new_stage2: stocks that entered Stage 2
      - exit_stage2: stocks that left Stage 2
      - stage_up/down: other stage movers
      - summary: counts
    """
    conn = get_conn()
    dates = list_snapshot_dates(conn)
    if not dates:
        conn.close()
        return {"error": "No snapshots in DB yet. Run --snapshot first."}

    today_snap = snap_date or dates[0]
    prev_snap  = vs_date or (dates[1] if len(dates) > 1 else None)

    result: dict = {"snap_date": today_snap, "prev_date": prev_snap}

    # Stage 2 current
    s2_now = pd.read_sql_query(
        "SELECT * FROM stage_snapshots WHERE snapshot_date=? AND stage='STAGE_2' ORDER BY stage_score DESC",
        conn, params=(today_snap,)
    )
    result["stage2_now"] = s2_now.to_dict("records")

    if prev_snap:
        # Ensure changes computed
        existing = conn.execute(
            "SELECT COUNT(*) FROM stage_changes WHERE change_date=? AND compare_date=?",
            (today_snap, prev_snap)
        ).fetchone()[0]
        if not existing:
            _compute_changes(conn, today_snap, prev_snap)

        chg = pd.read_sql_query(
            "SELECT * FROM stage_changes WHERE change_date=? AND compare_date=? ORDER BY change_type, stage_score_now DESC",
            conn, params=(today_snap, prev_snap)
        )
        result["new_stage2"]   = chg[chg.change_type == "NEW_STAGE2"].to_dict("records")
        result["exit_stage2"]  = chg[chg.change_type == "EXIT_STAGE2"].to_dict("records")
        result["stage_up"]     = chg[chg.change_type == "STAGE_UP"].to_dict("records")
        result["stage_down"]   = chg[chg.change_type == "STAGE_DOWN"].to_dict("records")
        result["all_changes"]  = chg[chg.stage_changed == 1].to_dict("records")

        # Week comparison too
        if also_vs_week:
            week_target = datetime.fromisoformat(today_snap).date() - timedelta(days=7)
            week_snap = _closest_snapshot(dates, week_target)
            if week_snap:
                ex2 = conn.execute(
                    "SELECT COUNT(*) FROM stage_changes WHERE change_date=? AND compare_date=?",
                    (today_snap, week_snap)
                ).fetchone()[0]
                if not ex2:
                    _compute_changes(conn, today_snap, week_snap)
                chg_w = pd.read_sql_query(
                    "SELECT * FROM stage_changes WHERE change_date=? AND compare_date=? ORDER BY change_type",
                    conn, params=(today_snap, week_snap)
                )
                result["week_snap"] = week_snap
                result["week_new_stage2"]  = chg_w[chg_w.change_type == "NEW_STAGE2"].to_dict("records")
                result["week_exit_stage2"] = chg_w[chg_w.change_type == "EXIT_STAGE2"].to_dict("records")
                result["week_price_changes"] = chg_w[chg_w.stage_now == "STAGE_2"].to_dict("records")

    result["summary"] = {
        "total_stage2": len(s2_now),
        "available_dates": dates[:10],
    }
    if prev_snap:
        result["summary"].update({
            "new_entrants_day":   len(result.get("new_stage2", [])),
            "exits_day":          len(result.get("exit_stage2", [])),
            "stage_changes_day":  len(result.get("all_changes", [])),
        })

    result["summary"]["stage_counts"] = {
        "STAGE_1": int(conn.execute("SELECT COUNT(*) FROM stage_snapshots WHERE snapshot_date=? AND stage='STAGE_1'", (today_snap,)).fetchone()[0]),
        "STAGE_2": int(conn.execute("SELECT COUNT(*) FROM stage_snapshots WHERE snapshot_date=? AND stage='STAGE_2'", (today_snap,)).fetchone()[0]),
        "STAGE_3": int(conn.execute("SELECT COUNT(*) FROM stage_snapshots WHERE snapshot_date=? AND stage='STAGE_3'", (today_snap,)).fetchone()[0]),
        "STAGE_4": int(conn.execute("SELECT COUNT(*) FROM stage_snapshots WHERE snapshot_date=? AND stage='STAGE_4'", (today_snap,)).fetchone()[0]),
    }

    if prev_snap and "all_changes" in result:
        chg = pd.DataFrame(result.get("all_changes", []) + result.get("new_stage2", []) + result.get("exit_stage2", []) + result.get("stage_up", []) + result.get("stage_down", []))
        # Re-load full changes for transition counting
        chg_all = pd.read_sql_query(
            "SELECT * FROM stage_changes WHERE change_date=? AND compare_date=?",
            conn, params=(today_snap, prev_snap)
        )
        result["summary"]["transitions"] = {
            "S1_to_S2": int(len(chg_all[(chg_all.stage_prev == "STAGE_1") & (chg_all.stage_now == "STAGE_2")])),
            "S2_to_S3": int(len(chg_all[(chg_all.stage_prev == "STAGE_2") & (chg_all.stage_now == "STAGE_3")])),
            "S3_to_S4": int(len(chg_all[(chg_all.stage_prev == "STAGE_3") & (chg_all.stage_now == "STAGE_4")])),
            "S2_to_S1": int(len(chg_all[(chg_all.stage_prev == "STAGE_2") & (chg_all.stage_now == "STAGE_1")])),
            "S3_to_S2": int(len(chg_all[(chg_all.stage_prev == "STAGE_3") & (chg_all.stage_now == "STAGE_2")])),
        }

    # Top investment picks from stage2_now sorted by investment_score
    top_picks = sorted(result["stage2_now"], key=lambda r: float(r.get("investment_score") or 0), reverse=True)[:15]
    result["top_picks"] = top_picks

    conn.close()
    return result


# ─────────────────────────────────────────────────────────────────────────────
# HTML report builder
# ─────────────────────────────────────────────────────────────────────────────

_H = html.escape

def _badge(stage: str) -> str:
    colors = {
        "STAGE_2": ("background:#16a34a;color:#fff", "S2 ✅"),
        "STAGE_1": ("background:#ca8a04;color:#fff", "S1"),
        "STAGE_3": ("background:#ea580c;color:#fff", "S3"),
        "STAGE_4": ("background:#dc2626;color:#fff", "S4"),
        "UNKNOWN": ("background:#94a3b8;color:#fff", "?"),
    }
    st, label = colors.get(stage, colors["UNKNOWN"])
    return f'<span style="display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:700;{st}">{label}</span>'


def _pct_cell(v) -> str:
    if v is None:
        return '<td style="color:#94a3b8">—</td>'
    try:
        fv = float(v)
        color = "#16a34a" if fv > 0 else ("#dc2626" if fv < 0 else "#64748b")
        arrow = "▲" if fv > 0 else ("▼" if fv < 0 else "")
        return f'<td style="color:{color};font-weight:500;text-align:right">{arrow}{abs(fv):.2f}%</td>'
    except (TypeError, ValueError):
        return '<td style="color:#94a3b8">—</td>'


def _price_cell(v) -> str:
    if v is None:
        return '<td style="color:#94a3b8">—</td>'
    try:
        return f'<td style="text-align:right">₹{float(v):,.2f}</td>'
    except (TypeError, ValueError):
        return '<td style="color:#94a3b8">—</td>'


CSS = """
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Segoe UI',system-ui,sans-serif;background:#f1f5f9;color:#0f172a;font-size:14px}
.app-bar{background:linear-gradient(135deg,#065f46,#059669);color:#fff;padding:18px 24px}
.app-bar h1{font-size:1.4rem;font-weight:700}
.app-bar p{font-size:0.82rem;opacity:.8;margin-top:4px}
.container{max-width:1600px;margin:0 auto;padding:20px 16px}
.summary-grid{display:flex;flex-wrap:wrap;gap:12px;margin-bottom:20px}
.sum-card{background:#fff;border-radius:8px;padding:14px 20px;box-shadow:0 1px 3px rgba(0,0,0,.08);min-width:140px}
.sum-card .sc-val{font-size:2rem;font-weight:700;line-height:1}
.sum-card .sc-lbl{font-size:0.75rem;color:#64748b;margin-top:4px;text-transform:uppercase;letter-spacing:.04em}
.sc-green{color:#16a34a}.sc-amber{color:#d97706}.sc-red{color:#dc2626}.sc-blue{color:#2563eb}
.section{background:#fff;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,.08);margin-bottom:20px;overflow:hidden}
.sec-hdr{padding:14px 18px;border-bottom:1px solid #e2e8f0;display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.sec-hdr h2{font-size:1rem;font-weight:600}
.badge-count{background:#e2e8f0;border-radius:12px;padding:2px 10px;font-size:.8rem;font-weight:600;color:#475569}

/* ── Toolbar ── */
.toolbar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;padding:10px 14px;border-bottom:1px solid #e2e8f0;background:#fafafa}
.search-bar{padding:6px 11px;border:1px solid #e2e8f0;border-radius:6px;font-size:13px;outline:none;min-width:200px;flex:1}
.search-bar:focus{border-color:#059669;box-shadow:0 0 0 2px rgba(5,150,105,.15)}
.tb-btn{padding:5px 12px;border:1px solid #e2e8f0;border-radius:6px;font-size:12px;font-weight:500;cursor:pointer;background:#fff;color:#475569;white-space:nowrap}
.tb-btn:hover{background:#f1f5f9}
.tb-btn.active{background:#059669;color:#fff;border-color:#059669}
/* signal filter chips */
.sig-filters{display:flex;gap:4px;flex-wrap:wrap}
.sf-chip{padding:3px 10px;border:1px solid #e2e8f0;border-radius:12px;font-size:11px;font-weight:600;cursor:pointer;background:#f8fafc;transition:all .15s}
.sf-chip:hover{opacity:.8}
.sf-chip.sf-active{box-shadow:0 0 0 2px #059669}
/* column toggle dropdown */
.col-toggle-wrap{position:relative}
.col-panel{display:none;position:absolute;top:calc(100% + 4px);right:0;background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:10px 14px;z-index:30;box-shadow:0 4px 12px rgba(0,0,0,.1);min-width:180px;max-height:360px;overflow-y:auto}
.col-panel.open{display:block}
.col-panel label{display:flex;align-items:center;gap:7px;font-size:12px;margin-bottom:6px;cursor:pointer;user-select:none}
.col-panel label:last-child{margin-bottom:0}
/* export btn */
.export-btn{padding:5px 12px;border:1px solid #059669;border-radius:6px;font-size:12px;font-weight:500;cursor:pointer;background:transparent;color:#059669}
.export-btn:hover{background:#059669;color:#fff}

/* ── Table ── */
.tbl-wrap{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:13px}
th{background:#f8fafc;padding:8px 12px;text-align:left;font-size:.72rem;font-weight:600;color:#64748b;text-transform:uppercase;letter-spacing:.04em;border-bottom:2px solid #e2e8f0;white-space:nowrap;cursor:pointer;user-select:none;position:relative}
th:hover{background:#eef2ff;color:#3730a3}
th .sort-icon{margin-left:4px;opacity:.4;font-size:.7rem}
th.sorted-asc .sort-icon::after{content:'▲';opacity:1;color:#059669}
th.sorted-desc .sort-icon::after{content:'▼';opacity:1;color:#059669}
th:not(.sorted-asc):not(.sorted-desc) .sort-icon::after{content:'⇅'}
td{padding:7px 12px;border-bottom:1px solid #f1f5f9;vertical-align:middle}
tr:last-child td{border-bottom:none}
tr:hover td{background:rgba(5,150,105,.04)!important}
.sym{font-weight:700;color:#0f172a}
.cname{color:#475569;font-size:.82rem}

/* ── Row signal colouring (left border + subtle bg) ── */
tr.row-strong-buy td:first-child{border-left:3px solid #15803d}
tr.row-strong-buy{background:rgba(21,128,61,.04)}
tr.row-buy td:first-child{border-left:3px solid #22c55e}
tr.row-buy{background:rgba(34,197,94,.03)}
tr.row-hold{background:rgba(202,138,4,.03)}
tr.row-hold td:first-child{border-left:3px solid #ca8a04}
tr.row-weak-hold td:first-child{border-left:3px solid #f97316}
tr.row-weak-hold{background:rgba(249,115,22,.03)}
tr.row-sell td:first-child{border-left:3px solid #dc2626}
tr.row-sell{background:rgba(220,38,38,.03)}

/* ── Signal chips ── */
.signal-chip{display:inline-block;padding:2px 8px;border-radius:4px;font-size:10px;font-weight:700;white-space:nowrap}
.sig-strong-buy{background:#dcfce7;color:#14532d}
.sig-buy{background:#bbf7d0;color:#166534}
.sig-hold{background:#fef9c3;color:#854d0e}
.sig-weak-hold{background:#ffedd5;color:#9a3412}
.sig-sell{background:#fee2e2;color:#991b1b}
.sig-unknown{background:#f1f5f9;color:#475569}

/* ── Score bars ── */
.score-bar{display:inline-flex;align-items:center;gap:5px;min-width:90px}
.sb-num{font-weight:600;min-width:26px;font-size:.82rem}
.sb-track{flex:1;height:5px;background:#e2e8f0;border-radius:3px;min-width:45px}
.sb-fill{height:100%;border-radius:3px}

/* ── RSI coloured badge ── */
.rsi-badge{display:inline-block;padding:1px 6px;border-radius:4px;font-weight:600;font-size:.82rem;min-width:34px;text-align:center}
.rsi-ob{background:#fee2e2;color:#991b1b}
.rsi-ok{background:#dcfce7;color:#166534}
.rsi-neutral{background:#f1f5f9;color:#475569}
.rsi-os{background:#dbeafe;color:#1e40af}

/* ── Tabs ── */
.tabs{display:flex;gap:0;padding:0 18px;background:#f8fafc;border-bottom:1px solid #e2e8f0;overflow-x:auto}
.tab-btn{padding:10px 16px;border:none;background:transparent;cursor:pointer;font-size:.85rem;font-weight:500;color:#64748b;border-bottom:2px solid transparent;transition:all .15s;white-space:nowrap}
.tab-btn.active{color:#059669;border-bottom-color:#059669;background:#fff}
.tab-panel{display:none}.tab-panel.active{display:block}

/* ── Pagination ── */
.pager{display:flex;align-items:center;gap:4px;padding:10px 14px;flex-wrap:wrap;border-top:1px solid #f1f5f9}
.pager button{padding:3px 9px;border:1px solid #e2e8f0;border-radius:4px;font-size:12px;cursor:pointer;background:#fff}
.pager button:hover{background:#f1f5f9}
.pager button.pg-active{background:#059669;color:#fff;border-color:#059669}
.pg-info{font-size:12px;color:#64748b;margin:0 6px}
.pg-size{font-size:12px;padding:3px 7px;border:1px solid #e2e8f0;border-radius:4px;outline:none}

/* ── Detail panel (fundamental + narrative expand) ── */
.detail-row{display:none;background:#f8fafc}
.detail-row.open{display:table-row}
.detail-cell{padding:14px 18px!important;border-bottom:2px solid #e2e8f0!important}
.detail-grid{display:flex;flex-wrap:wrap;gap:12px}
.det-card{background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:10px 14px;min-width:160px;flex:1}
.det-card h4{font-size:.72rem;font-weight:600;color:#64748b;text-transform:uppercase;letter-spacing:.04em;margin-bottom:6px}
.det-card p{font-size:.82rem;color:#334155;line-height:1.5}
.stance-bull{color:#166534;font-weight:700;background:#dcfce7;padding:2px 8px;border-radius:4px;font-size:11px}
.stance-bear{color:#991b1b;font-weight:700;background:#fee2e2;padding:2px 8px;border-radius:4px;font-size:11px}
.stance-neut{color:#854d0e;font-weight:700;background:#fef9c3;padding:2px 8px;border-radius:4px;font-size:11px}
.inv-score-big{font-size:1.8rem;font-weight:700;line-height:1}
.fund-detail-text{font-size:.8rem;color:#475569;margin-top:4px;line-height:1.5}
/* ── Stage filter chips ── */
.stage-filters{display:flex;gap:4px;flex-wrap:wrap;align-items:center}
.stage-chip{padding:3px 12px;border-radius:12px;font-size:11px;font-weight:700;cursor:pointer;border:2px solid transparent;transition:all .15s;user-select:none}
.stage-chip.s-all{background:#e2e8f0;color:#475569}
.stage-chip.s-1{background:#fef9c3;color:#854d0e;border-color:#ca8a04}
.stage-chip.s-2{background:#dcfce7;color:#166534;border-color:#16a34a}
.stage-chip.s-3{background:#ffedd5;color:#9a3412;border-color:#ea580c}
.stage-chip.s-4{background:#fee2e2;color:#991b1b;border-color:#dc2626}
.stage-chip.active{box-shadow:0 0 0 2px #0f172a}
/* ── Top picks section ── */
.picks-grid{display:flex;flex-wrap:wrap;gap:12px;padding:16px 18px}
.pick-card{background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:14px 16px;min-width:220px;flex:1;max-width:280px;box-shadow:0 1px 3px rgba(0,0,0,.06);cursor:pointer;transition:box-shadow .15s}
.pick-card:hover{box-shadow:0 4px 12px rgba(5,150,105,.15);border-color:#059669}
.pick-card .pk-sym{font-size:1.1rem;font-weight:700}
.pick-card .pk-co{font-size:.78rem;color:#64748b;margin-bottom:6px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.pick-card .pk-sector{font-size:.75rem;background:#e0f2fe;color:#0369a1;padding:1px 6px;border-radius:4px;display:inline-block;margin-bottom:6px}
.pick-card .pk-inv{font-size:1.4rem;font-weight:700;color:#059669}
.pick-card .pk-meta{font-size:.75rem;color:#64748b;margin-top:4px}
/* ── Transition pills ── */
.trans-wrap{display:flex;flex-wrap:wrap;gap:6px;padding:10px 18px;border-top:1px solid #f1f5f9}
.trans-pill{padding:3px 10px;border-radius:12px;font-size:11px;font-weight:600}
.tp-up{background:#dcfce7;color:#166534}
.tp-down{background:#fee2e2;color:#991b1b}
</style>"""


def build_html_report(report: dict) -> str:
    snap = report.get("snap_date", "N/A")
    prev = report.get("prev_date", "N/A")
    week = report.get("week_snap", "N/A")
    summ = report.get("summary", {})
    now_ts = datetime.now().strftime("%Y-%m-%d %H:%M")

    s2_list   = report.get("stage2_now", [])
    new_s2    = report.get("new_stage2", [])
    exit_s2   = report.get("exit_stage2", [])
    all_chg   = report.get("all_changes", [])
    w_new     = report.get("week_new_stage2", [])
    w_exit    = report.get("week_exit_stage2", [])
    w_price   = report.get("week_price_changes", [])

    # ── helpers ──────────────────────────────────────────────────────────────
    _SIG_MAP = {
        "STRONG_BUY": ("sig-strong-buy", "row-strong-buy"),
        "BUY":        ("sig-buy",         "row-buy"),
        "HOLD":       ("sig-hold",        "row-hold"),
        "WEAK_HOLD":  ("sig-weak-hold",   "row-weak-hold"),
        "SELL":       ("sig-sell",        "row-sell"),
    }

    def sig_chip(s: str) -> str:
        key = str(s).upper().replace(" ", "_")
        chip_cls = _SIG_MAP.get(key, ("sig-unknown", ""))[0]
        return f'<span class="signal-chip {chip_cls}">{_H(s or "—")}</span>'

    def row_cls(r: dict) -> str:
        key = str(r.get("trading_signal", "")).upper().replace(" ", "_")
        return _SIG_MAP.get(key, ("", ""))[1]

    def score_bar(v, max_v: float = 100, color: str = "#059669") -> str:
        try:
            fv = float(v)
            w = min(100, max(0, fv / max_v * 100))
            return (f'<div class="score-bar"><span class="sb-num">{fv:.0f}</span>'
                    f'<div class="sb-track"><div class="sb-fill" style="width:{w}%;background:{color}"></div></div></div>')
        except (TypeError, ValueError):
            return "—"

    def rsi_cell(v) -> str:
        try:
            fv = float(v)
            if fv >= 70:
                cls = "rsi-ob"
            elif fv >= 55:
                cls = "rsi-ok"
            elif fv >= 40:
                cls = "rsi-neutral"
            else:
                cls = "rsi-os"
            return f'<td style="text-align:right"><span class="rsi-badge {cls}">{fv:.0f}</span></td>'
        except (TypeError, ValueError):
            return '<td style="color:#94a3b8">—</td>'

    def _make_detail_row(r: dict, tid: str, ri: int) -> str:
        inv = r.get("investment_score") or 0
        stance = str(r.get("stance") or "NEUTRAL").upper()
        stance_cls = {"BULLISH": "stance-bull", "BEARISH": "stance-bear"}.get(stance, "stance-neut")
        narrative_txt = str(r.get("narrative") or "")

        # Fund details card
        fd_json = r.get("fund_details")
        fd = {}
        if fd_json:
            try:
                fd = json.loads(fd_json)
            except Exception:
                pass
        pnl_txt = str(fd.get("pnl_summary") or "")[:300] if fd else ""
        rat_txt = str(fd.get("ratios_summary") or "")[:300] if fd else ""

        # Score bar helper (local)
        def _sb(v, color="#059669"):
            try:
                fv = float(v)
                w = min(100, max(0, fv))
                return (f'<div class="score-bar"><span class="sb-num">{fv:.0f}</span>'
                        f'<div class="sb-track"><div class="sb-fill" style="width:{w}%;background:{color}"></div></div></div>')
            except (TypeError, ValueError):
                return "—"

        card_inv = (
            f'<div class="det-card"><h4>Investment Score</h4>'
            f'<p><span class="inv-score-big">{float(inv):.0f}</span> / 100</p>'
            f'<p style="margin-top:6px"><span class="{stance_cls}">{stance}</span></p>'
            f'</div>'
        )
        card_narr = (
            f'<div class="det-card" style="flex:3;min-width:260px"><h4>Analysis Narrative</h4>'
            f'<p>{_H(narrative_txt)}</p>'
            f'</div>'
        )
        card_tech = (
            f'<div class="det-card"><h4>Technical</h4>'
            f'<p>Tech Score: {_sb(r.get("technical_score"))}</p>'
            f'<p>RSI: {_H(str(r.get("rsi") or "—"))}</p>'
            f'<p>Trend: {_H(str(r.get("trend_signal") or "—"))}</p>'
            f'<p>Signal: {sig_chip(r.get("trading_signal",""))}</p>'
            f'</div>'
        )
        card_fund = (
            f'<div class="det-card"><h4>Fundamentals</h4>'
            f'<p>Enh Fund: {_sb(r.get("enhanced_fund_score"), "#7c3aed")}</p>'
            f'<p>Earn Qual: {_sb(r.get("earnings_quality"), "#0891b2")}</p>'
            f'<p>Sales Gr: {_sb(r.get("sales_growth"), "#059669")}</p>'
            f'<p>Fin Str: {_sb(r.get("financial_strength"), "#d97706")}</p>'
            f'<p>Inst Back: {_sb(r.get("institutional_backing"), "#db2777")}</p>'
            f'</div>'
        )
        card_fd = (
            f'<div class="det-card" style="flex:2;min-width:200px"><h4>Fund Details</h4>'
            + (f'<p class="fund-detail-text"><strong>P&amp;L:</strong> {_H(pnl_txt)}</p>' if pnl_txt else '')
            + (f'<p class="fund-detail-text"><strong>Ratios:</strong> {_H(rat_txt)}</p>' if rat_txt else '')
            + (f'<p style="color:#94a3b8;font-size:.78rem">No fund data available</p>' if not pnl_txt and not rat_txt else '')
            + f'</div>'
        )
        detail_content = f'<div class="detail-grid">{card_inv}{card_narr}{card_tech}{card_fund}{card_fd}</div>'
        return f'<tr class="detail-row" id="{tid}-dr-{ri}"><td colspan="99" class="detail-cell">{detail_content}</td></tr>'

    _tbl_counter = [0]

    # ── full-featured table ───────────────────────────────────────────────────
    def s2_table(rows: list[dict], show_prev: bool = False) -> str:
        if not rows:
            return '<p style="color:#94a3b8;padding:16px">No data available.</p>'

        _tbl_counter[0] += 1
        tid = f"tbl{_tbl_counter[0]}"

        if show_prev:
            # columns for change / entry / exit views
            col_defs = [
                {"key": "rank",       "label": "#",        "toggleable": False},
                {"key": "symbol",     "label": "Symbol",   "toggleable": False},
                {"key": "company",    "label": "Company",  "toggleable": True, "default": True},
                {"key": "stage_now",  "label": "Stage →",  "toggleable": True, "default": True},
                {"key": "stage_prev", "label": "Stage ←",  "toggleable": True, "default": True},
                {"key": "price_prev", "label": "CSV Price","toggleable": True, "default": True},
                {"key": "live_price", "label": "Live ₹",   "toggleable": True, "default": True},
                {"key": "live_pct",   "label": "Chg%",     "toggleable": True, "default": True},
            ]
        else:
            col_defs = [
                {"key": "rank",        "label": "#",          "toggleable": False},
                {"key": "symbol",      "label": "Symbol",     "toggleable": False},
                {"key": "company",     "label": "Company",    "toggleable": True, "default": True},
                {"key": "sector",      "label": "Sector",     "toggleable": True, "default": True},
                {"key": "stage",       "label": "Stage",      "toggleable": True, "default": True},
                {"key": "signal",      "label": "Signal",     "toggleable": True, "default": True},
                {"key": "live_price",  "label": "Live ₹",     "toggleable": True, "default": True},
                {"key": "csv_price",   "label": "CSV ₹",      "toggleable": True, "default": True},
                {"key": "live_pct",    "label": "Live Chg%",  "toggleable": True, "default": True},
                {"key": "tech_score",  "label": "Tech Score", "toggleable": True, "default": True},
                {"key": "rsi",         "label": "RSI",        "toggleable": True, "default": True},
                {"key": "trend",       "label": "Trend",      "toggleable": True, "default": False},
                {"key": "rs",          "label": "RS",         "toggleable": True, "default": True},
                {"key": "chg1d",       "label": "1D%",        "toggleable": True, "default": True},
                {"key": "chg1w",       "label": "1W%",        "toggleable": True, "default": True},
                {"key": "chg1m",       "label": "1M%",        "toggleable": True, "default": False},
                {"key": "cap",         "label": "Cap",        "toggleable": True, "default": False},
                {"key": "stage_score", "label": "Score",      "toggleable": True, "default": True},
            ]

        # ── column toggle panel ──
        toggle_checks = "".join(
            f'<label><input type="checkbox" {"checked" if c.get("default", True) else ""} '
            f'onchange="toggleCol(\'{tid}\',{i},this.checked)"> {c["label"]}</label>'
            for i, c in enumerate(col_defs) if c.get("toggleable")
        )
        toggle_idx = {c["key"]: i for i, c in enumerate(col_defs)}

        # ── signal filter values ──
        signals_present = sorted({str(r.get("trading_signal","") or "").upper() for r in rows
                                   if r.get("trading_signal")})

        sig_chips_html = "".join(
            f'<span class="sf-chip sf-active" '
            f'onclick="toggleSigFilter(\'{tid}\',\'{s}\',this)">{s}</span>'
            for s in signals_present
        ) if not show_prev else ""

        stage_filters_html = (
            f'<div class="stage-filters" id="{tid}-stf">'
            f'<span class="stage-chip s-all active" onclick="toggleStageFilter(\'{tid}\',\'ALL\',this)">All Stages</span>'
            f'<span class="stage-chip s-1" onclick="toggleStageFilter(\'{tid}\',\'STAGE_1\',this)">S1</span>'
            f'<span class="stage-chip s-2" onclick="toggleStageFilter(\'{tid}\',\'STAGE_2\',this)">S2</span>'
            f'<span class="stage-chip s-3" onclick="toggleStageFilter(\'{tid}\',\'STAGE_3\',this)">S3</span>'
            f'<span class="stage-chip s-4" onclick="toggleStageFilter(\'{tid}\',\'STAGE_4\',this)">S4</span>'
            f'</div>'
        ) if not show_prev else ""

        toolbar = (
            f'<div class="toolbar">'
            f'<input class="search-bar" type="search" placeholder="🔍 Search symbol, company…" '
            f'oninput="filterTbl(\'{tid}\',this.value)">'
            + (f'<div class="sig-filters" id="{tid}-sf">{sig_chips_html}</div>' if sig_chips_html else "")
            + (stage_filters_html if stage_filters_html else "")
            + f'<div class="col-toggle-wrap">'
            f'<button class="tb-btn" onclick="togglePanel(\'{tid}-cp\')">⚙ Columns</button>'
            f'<div class="col-panel" id="{tid}-cp">{toggle_checks}</div>'
            f'</div>'
            f'<button class="export-btn" onclick="exportCSV(\'{tid}\')">⬇ CSV</button>'
            f'</div>'
        )

        # ── hide cols that are off by default ──
        hidden_cols = {i for i, c in enumerate(col_defs) if not c.get("default", True)}
        def th_style(i): return ' style="display:none"' if i in hidden_cols else ""
        def td_style(i): return ' style="display:none"' if i in hidden_cols else ""

        # header row
        hdr_html = "".join(
            f'<th data-col="{i}" onclick="sortTbl(\'{tid}\',{i})" {th_style(i)}>'
            f'{c["label"]}<span class="sort-icon"></span></th>'
            for i, c in enumerate(col_defs)
        )

        tbl_rows = []
        for ri, r in enumerate(rows, 1):
            live  = r.get("live_price")
            price = r.get("price")
            lp_vs_csv = None
            if live and price:
                try: lp_vs_csv = round((float(live) - float(price)) / float(price) * 100, 2)
                except: pass

            sig_key = str(r.get("trading_signal", "")).upper().replace(" ", "_")
            rc = _SIG_MAP.get(sig_key, ("", ""))[1]

            if show_prev:
                cells = [
                    f'<td{td_style(0)}>{ri}</td>',
                    f'<td{td_style(1)} class="sym">{_H(str(r.get("symbol",""))[:14])}</td>',
                    f'<td{td_style(2)} class="cname">{_H(str(r.get("company_name",""))[:35])}</td>',
                    f'<td{td_style(3)}>{_badge(r.get("stage_now","UNKNOWN"))}</td>',
                    f'<td{td_style(4)}>{_badge(r.get("stage_prev","UNKNOWN"))}</td>',
                    _price_cell(r.get("price_prev")).replace("<td", f'<td{td_style(5)}', 1),
                    _price_cell(r.get("live_price")).replace("<td", f'<td{td_style(6)}', 1),
                    _pct_cell(r.get("live_vs_prev_pct")).replace("<td", f'<td{td_style(7)}', 1),
                ]
            else:
                rs_val = r.get("relative_strength")
                cells = [
                    f'<td{td_style(0)}>{ri}</td>',
                    f'<td{td_style(1)} class="sym">{_H(str(r.get("symbol",""))[:14])}</td>',
                    f'<td{td_style(2)} class="cname">{_H(str(r.get("company_name",""))[:35])}</td>',
                    f'<td{td_style(3)} class="cname" style="font-size:.75rem">{_H(str(r.get("sector","") or "Other"))}</td>',
                    f'<td{td_style(4)}>{_badge(r.get("stage","UNKNOWN"))}</td>',
                    f'<td{td_style(5)}>{sig_chip(r.get("trading_signal",""))}</td>',
                    _price_cell(live).replace("<td", f'<td{td_style(6)}', 1),
                    _price_cell(price).replace("<td", f'<td{td_style(7)}', 1),
                    _pct_cell(lp_vs_csv).replace("<td", f'<td{td_style(8)}', 1),
                    f'<td{td_style(9)}>{score_bar(r.get("technical_score"))}</td>',
                    rsi_cell(r.get("rsi")).replace("<td", f'<td{td_style(10)}', 1),
                    f'<td{td_style(11)} style="font-size:.75rem">{_H(str(r.get("trend_signal","") or ""))}</td>',
                    _pct_cell(rs_val).replace("<td", f'<td{td_style(12)}', 1),
                    _pct_cell(r.get("change_1d_pct")).replace("<td", f'<td{td_style(13)}', 1),
                    _pct_cell(r.get("change_1w_pct")).replace("<td", f'<td{td_style(14)}', 1),
                    _pct_cell(r.get("change_1m_pct")).replace("<td", f'<td{td_style(15)}', 1),
                    f'<td{td_style(16)} style="font-size:.75rem">{_H(str(r.get("market_cap_cat","") or ""))}</td>',
                    f'<td{td_style(17)} style="text-align:right">{r.get("stage_score") or "—"}</td>',
                ]

            data_sig = f' data-sig="{sig_key}"' if not show_prev else ''
            data_stage = f' data-stage="{str(r.get("stage",""))}"' if not show_prev else ''
            onclick_str = f' onclick="toggleDetail(\'{tid}-dr-{ri}\')" style="cursor:pointer"' if not show_prev else ''
            tbl_rows.append(f'<tr class="{rc}"{data_sig}{data_stage}{onclick_str}>{"".join(cells)}</tr>')
            if not show_prev:
                tbl_rows.append(_make_detail_row(r, tid, ri))

        body = "\n".join(tbl_rows)
        pg_id = f"{tid}-pager"
        return (
            toolbar
            + f'<div class="tbl-wrap"><table id="{tid}">'
            + f'<thead><tr>{hdr_html}</tr></thead>'
            + f'<tbody id="{tid}-body">{body}</tbody>'
            + f'</table></div>'
            + f'<div class="pager" id="{pg_id}">'
            + f'<span class="pg-info" id="{pg_id}-info"></span>'
            + f'<select class="pg-size" onchange="setPageSize(\'{tid}\',parseInt(this.value))">'
            + '<option value="25">25 / page</option>'
            + '<option value="50" selected>50 / page</option>'
            + '<option value="100">100 / page</option>'
            + '<option value="9999">All</option>'
            + f'</select></div>'
        )

    # ── Summary cards ────────────────────────────────────────────────────────
    trans = summ.get("transitions", {})
    stage_counts = summ.get("stage_counts", {})

    stage_count_html = (
        f'<div class="sum-card"><div class="sc-val" style="color:#ca8a04">{stage_counts.get("STAGE_1",0)}</div><div class="sc-lbl">Stage 1 stocks</div></div>'
        f'<div class="sum-card"><div class="sc-val sc-green">{stage_counts.get("STAGE_2",0)}</div><div class="sc-lbl">Stage 2 stocks</div></div>'
        f'<div class="sum-card"><div class="sc-val" style="color:#ea580c">{stage_counts.get("STAGE_3",0)}</div><div class="sc-lbl">Stage 3 stocks</div></div>'
        f'<div class="sum-card"><div class="sc-val sc-red">{stage_counts.get("STAGE_4",0)}</div><div class="sc-lbl">Stage 4 stocks</div></div>'
    )

    trans_html = ""
    if trans:
        pills = []
        if trans.get("S1_to_S2"): pills.append(f'<span class="trans-pill tp-up">S1→S2: {trans["S1_to_S2"]}</span>')
        if trans.get("S2_to_S3"): pills.append(f'<span class="trans-pill tp-down">S2→S3: {trans["S2_to_S3"]}</span>')
        if trans.get("S3_to_S4"): pills.append(f'<span class="trans-pill tp-down">S3→S4: {trans["S3_to_S4"]}</span>')
        if trans.get("S2_to_S1"): pills.append(f'<span class="trans-pill tp-down">S2→S1: {trans["S2_to_S1"]}</span>')
        if trans.get("S3_to_S2"): pills.append(f'<span class="trans-pill tp-up">S3→S2: {trans["S3_to_S2"]}</span>')
        if pills:
            trans_html = f'<div class="trans-wrap">{"".join(pills)}</div>'

    cards = (
        stage_count_html
        + f'<div class="sum-card"><div class="sc-val sc-blue">{summ.get("new_entrants_day",0)}</div><div class="sc-lbl">New entrants (day)</div></div>'
        f'<div class="sum-card"><div class="sc-val sc-red">{summ.get("exits_day",0)}</div><div class="sc-lbl">Exits (day)</div></div>'
        f'<div class="sum-card"><div class="sc-val sc-amber">{summ.get("stage_changes_day",0)}</div><div class="sc-lbl">Stage changes (day)</div></div>'
        f'<div class="sum-card"><div class="sc-val sc-blue">{len(w_new)}</div><div class="sc-lbl">New entrants (week)</div></div>'
        f'<div class="sum-card"><div class="sc-val sc-red">{len(w_exit)}</div><div class="sc-lbl">Exits (week)</div></div>'
    )

    # ── Top Picks ─────────────────────────────────────────────────────────────
    top_picks = report.get("top_picks", [])
    def top_picks_html(picks):
        if not picks:
            return ""
        pick_cards = []
        for pk in picks:
            inv = pk.get("investment_score") or 0
            stance = str(pk.get("stance") or "NEUTRAL").upper()
            stance_cls = {"BULLISH": "stance-bull", "BEARISH": "stance-bear"}.get(stance, "stance-neut")
            pick_cards.append(
                f'<div class="pick-card">'
                f'<div class="pk-sym">{_H(str(pk.get("symbol","")))}</div>'
                f'<div class="pk-co">{_H(str(pk.get("company_name",""))[:40])}</div>'
                f'<span class="pk-sector">{_H(str(pk.get("sector","Other")))}</span>'
                f'<div class="pk-inv">{float(inv):.0f} <span style="font-size:.8rem;color:#64748b">inv. score</span></div>'
                f'<div class="pk-meta">Tech {pk.get("technical_score") or "—"} · RSI {pk.get("rsi") or "—"} · <span class="{stance_cls}">{stance}</span></div>'
                f'</div>'
            )
        return (
            '<div class="section" style="margin-bottom:20px">'
            '<div class="sec-hdr" style="border-left:4px solid #059669">'
            '<h2>🏆 Top Investment Picks (Stage 2)</h2>'
            f'<span class="badge-count">{len(picks)}</span>'
            '</div>'
            f'<div class="picks-grid">{"".join(pick_cards)}</div>'
            '</div>'
        )
    picks_section = top_picks_html(top_picks)

    # ── Tabs ─────────────────────────────────────────────────────────────────
    tabs_html = (
        '<div class="tabs">'
        '<button class="tab-btn active" data-tab="t-s2" onclick="showTab(\'t-s2\',this)">Stage 2 Now</button>'
        '<button class="tab-btn" data-tab="t-new" onclick="showTab(\'t-new\',this)">New Entrants (Day)</button>'
        '<button class="tab-btn" data-tab="t-exit" onclick="showTab(\'t-exit\',this)">Exits (Day)</button>'
        '<button class="tab-btn" data-tab="t-all" onclick="showTab(\'t-all\',this)">All Stage Changes (Day)</button>'
        f'<button class="tab-btn" data-tab="t-week" onclick="showTab(\'t-week\',this)">Weekly View ({week})</button>'
        '</div>'
        f'<div class="tab-panel active" id="t-s2">{s2_table(s2_list)}</div>'
        f'<div class="tab-panel" id="t-new">{s2_table(new_s2, show_prev=True)}</div>'
        f'<div class="tab-panel" id="t-exit">{s2_table(exit_s2, show_prev=True)}</div>'
        f'<div class="tab-panel" id="t-all">{s2_table(all_chg, show_prev=True)}</div>'
        f'<div class="tab-panel" id="t-week">'
        f'<h3 style="font-size:.9rem;font-weight:600;padding:14px 18px 6px;color:#059669">New Stage 2 entrants this week ({len(w_new)})</h3>'
        f'{s2_table(w_new, show_prev=True)}'
        f'<h3 style="font-size:.9rem;font-weight:600;padding:14px 18px 6px;color:#dc2626">Stage 2 exits this week ({len(w_exit)})</h3>'
        f'{s2_table(w_exit, show_prev=True)}'
        f'<h3 style="font-size:.9rem;font-weight:600;padding:14px 18px 6px;color:#2563eb">Stage 2 price changes this week ({len(w_price)})</h3>'
        f'{s2_table(w_price)}'
        f'</div>'
    )

    js = r"""
<script>
/* ── Tab switching ── */
function showTab(id, btn) {
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.getElementById(id).classList.add('active');
  btn.classList.add('active');
}

/* ── Column toggle panel ── */
function togglePanel(id) {
  var p = document.getElementById(id);
  p.classList.toggle('open');
  document.addEventListener('click', function closer(e) {
    if (!p.contains(e.target) && !e.target.closest('.col-toggle-wrap')) {
      p.classList.remove('open');
      document.removeEventListener('click', closer);
    }
  }, {once: false});
}
function toggleCol(tid, colIdx, show) {
  var tbl = document.getElementById(tid);
  if (!tbl) return;
  tbl.querySelectorAll('th[data-col="'+colIdx+'"], td[data-col="'+colIdx+'"]')
    .forEach(function(el){ el.style.display = show ? '' : 'none'; });
  // also match by nth-child position
  var idx = colIdx + 1;
  tbl.querySelectorAll('tr').forEach(function(row){
    var cell = row.cells[colIdx];
    if (cell) cell.style.display = show ? '' : 'none';
  });
}

/* ── Sorting ── */
var _sortState = {};
function sortTbl(tid, col) {
  var tbl = document.getElementById(tid);
  if (!tbl) return;
  var tbody = document.getElementById(tid + '-body');
  var rows = Array.from(tbody.querySelectorAll('tr'));
  var key = tid + '_' + col;
  var asc = _sortState[key] !== true;
  _sortState[key] = asc;

  tbl.querySelectorAll('th').forEach(function(th, i) {
    th.classList.remove('sorted-asc', 'sorted-desc');
    if (i === col) th.classList.add(asc ? 'sorted-asc' : 'sorted-desc');
  });

  rows.sort(function(a, b) {
    var av = a.cells[col] ? a.cells[col].textContent.trim() : '';
    var bv = b.cells[col] ? b.cells[col].textContent.trim() : '';
    // strip currency / % symbols
    av = av.replace(/[₹,%]/g,'').trim();
    bv = bv.replace(/[₹,%]/g,'').trim();
    var an = parseFloat(av), bn = parseFloat(bv);
    if (!isNaN(an) && !isNaN(bn)) return asc ? an - bn : bn - an;
    return asc ? av.localeCompare(bv) : bv.localeCompare(av);
  });
  rows.forEach(function(r) { tbody.appendChild(r); });
  applyPager(tid);
}

/* ── Text search ── */
function filterTbl(tid, q) {
  q = q.toLowerCase();
  var tbody = document.getElementById(tid + '-body');
  if (!tbody) return;
  tbody.querySelectorAll('tr').forEach(function(r) {
    r.dataset.searchHide = r.textContent.toLowerCase().includes(q) ? '' : '1';
  });
  applyPager(tid);
}

/* ── Signal filter chips ── */
var _sigFilters = {};
function toggleSigFilter(tid, sig, el) {
  if (!_sigFilters[tid]) _sigFilters[tid] = new Set();
  var sf = _sigFilters[tid];
  if (sf.has(sig)) { sf.delete(sig); el.classList.remove('sf-active'); }
  else             { sf.add(sig);    el.classList.add('sf-active'); }
  applyPager(tid);
}
function _sigVisible(tid, row) {
  var sf = _sigFilters[tid];
  if (!sf || sf.size === 0) return true;
  return sf.has((row.dataset.sig || '').toUpperCase());
}

/* ── Pagination ── */
var _pageState = {};
function setPageSize(tid, n) {
  if (!_pageState[tid]) _pageState[tid] = {page: 1, size: 50};
  _pageState[tid].size = n;
  _pageState[tid].page = 1;
  applyPager(tid);
}
function gotoPage(tid, n) {
  if (!_pageState[tid]) _pageState[tid] = {page: 1, size: 50};
  _pageState[tid].page = n;
  applyPager(tid);
}
function applyPager(tid) {
  var tbody = document.getElementById(tid + '-body');
  var pgDiv = document.getElementById(tid + '-pager');
  if (!tbody) return;
  if (!_pageState[tid]) _pageState[tid] = {page: 1, size: 50};
  var state = _pageState[tid];

  var visible = Array.from(tbody.querySelectorAll('tr')).filter(function(r) {
    return r.dataset.searchHide !== '1' && _sigVisible(tid, r) && r.dataset.stageHide !== '1' && !r.classList.contains('detail-row');
  });
  var total = visible.length;
  var pages = Math.max(1, Math.ceil(total / state.size));
  if (state.page > pages) state.page = pages;
  var start = (state.page - 1) * state.size;
  var end   = start + state.size;

  Array.from(tbody.querySelectorAll('tr')).forEach(function(r) {
    r.style.display = 'none';
  });
  visible.forEach(function(r, i) {
    r.style.display = (i >= start && i < end) ? '' : 'none';
  });

  // pager buttons
  if (!pgDiv) return;
  var info = pgDiv.querySelector('[id$="-info"]');
  if (info) info.textContent = total + ' rows · page ' + state.page + ' / ' + pages;

  // remove old page buttons
  pgDiv.querySelectorAll('button').forEach(function(b){ b.remove(); });
  var maxBtns = 7;
  var half = Math.floor(maxBtns/2);
  var s = Math.max(1, state.page - half);
  var e = Math.min(pages, s + maxBtns - 1);
  s = Math.max(1, e - maxBtns + 1);

  function mkBtn(label, pg) {
    var b = document.createElement('button');
    b.textContent = label;
    if (pg === state.page) b.classList.add('pg-active');
    b.onclick = function(){ gotoPage(tid, pg); };
    pgDiv.insertBefore(b, pgDiv.querySelector('select'));
  }
  if (s > 1) mkBtn('«', 1);
  for (var p = s; p <= e; p++) mkBtn(String(p), p);
  if (e < pages) mkBtn('»', pages);
}

/* ── CSV export ── */
function exportCSV(tid) {
  var tbl = document.getElementById(tid);
  if (!tbl) return;
  var rows = [];
  tbl.querySelectorAll('tr').forEach(function(r) {
    if (r.style.display === 'none') return;
    var cells = Array.from(r.querySelectorAll('th,td')).map(function(c) {
      return '"' + c.textContent.trim().replace(/"/g,'""') + '"';
    });
    rows.push(cells.join(','));
  });
  var blob = new Blob([rows.join('\n')], {type:'text/csv'});
  var a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = tid + '.csv';
  a.click();
}

/* ── Detail row expand ── */
function toggleDetail(id) {
  var row = document.getElementById(id);
  if (row) row.classList.toggle('open');
}

/* ── Stage filter chips ── */
var _stageFilter = {};
function toggleStageFilter(tid, stage, el) {
  var container = document.getElementById(tid + '-stf');
  if (container) container.querySelectorAll('.stage-chip').forEach(function(c){ c.classList.remove('active'); });
  el.classList.add('active');
  _stageFilter[tid] = stage === 'ALL' ? null : stage;
  var tbody = document.getElementById(tid + '-body');
  if (!tbody) return;
  tbody.querySelectorAll('tr[data-stage]').forEach(function(r) {
    var s = r.dataset.stage || '';
    r.dataset.stageHide = (!_stageFilter[tid] || s === _stageFilter[tid]) ? '' : '1';
  });
  applyPager(tid);
}

/* ── Init pagers on load ── */
document.addEventListener('DOMContentLoaded', function() {
  document.querySelectorAll('table[id^="tbl"]').forEach(function(t) {
    applyPager(t.id);
  });
  // init all sig-filter sets to "all active" = empty set (show all)
});
</script>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Stage 2 Tracker – {snap}</title>
{CSS}
</head>
<body>
<div class="app-bar">
  <h1>📈 Sector Rotation – Stage 2 Tracker</h1>
  <p>Snapshot: <strong>{snap}</strong> &nbsp;·&nbsp; Compared vs: <strong>{prev}</strong>
     &nbsp;·&nbsp; Week vs: <strong>{week}</strong> &nbsp;·&nbsp; Generated: {now_ts}</p>
</div>
<div class="container">
  <div class="summary-grid">{cards}</div>
  {trans_html}
  {picks_section}
  <div class="section">
    {tabs_html}
  </div>
</div>
{js}
</body></html>"""


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Sector Rotation Stage Tracker")
    parser.add_argument("--snapshot", action="store_true", help="Capture today's EOD snapshot")
    parser.add_argument("--report",   action="store_true", help="Print/save change report")
    parser.add_argument("--html",     action="store_true", help="Save HTML change report")
    parser.add_argument("--all",      action="store_true", help="snapshot + HTML report")
    parser.add_argument("--vs",       help="Compare against this date (YYYY-MM-DD)")
    parser.add_argument("--date",     help="Override snapshot date (YYYY-MM-DD)")
    parser.add_argument("--force",    action="store_true", help="Overwrite existing snapshot")
    parser.add_argument("--list",     action="store_true", help="List available snapshot dates")
    parser.add_argument("--no-live",  action="store_true", help="Skip Yahoo Finance live prices")
    args = parser.parse_args()

    if args.list:
        conn = get_conn()
        dates = list_snapshot_dates(conn)
        conn.close()
        print("Available snapshots:")
        for d in dates:
            conn = get_conn()
            n = conn.execute("SELECT COUNT(*) FROM stage_snapshots WHERE snapshot_date=?", (d,)).fetchone()[0]
            n2 = conn.execute("SELECT COUNT(*) FROM stage_snapshots WHERE snapshot_date=? AND stage='STAGE_2'", (d,)).fetchone()[0]
            conn.close()
            print(f"  {d}  |  {n} stocks  |  {n2} Stage 2")
        return

    if args.snapshot or args.all:
        print(f"[1/2] Writing EOD snapshot …")
        n = write_snapshot(snap_date=args.date, fetch_live=not args.no_live, force=args.force)
        if n == 0 and not args.force:
            pass  # already logged inside write_snapshot

    if args.report or args.html or args.all:
        print(f"[2/2] Building change report …")
        rpt = build_change_report(snap_date=args.date, vs_date=args.vs)

        if "error" in rpt:
            print(f"  Error: {rpt['error']}")
            return

        # Print text summary
        s = rpt.get("summary", {})
        print(f"\n  Snapshot : {rpt['snap_date']}   vs prev: {rpt.get('prev_date','—')}   vs week: {rpt.get('week_snap','—')}")
        print(f"  Stage 2  : {s.get('total_stage2',0)} stocks")
        print(f"  New S2   : {s.get('new_entrants_day',0)} (day)   {len(rpt.get('week_new_stage2',[]))} (week)")
        print(f"  Exit S2  : {s.get('exits_day',0)} (day)   {len(rpt.get('week_exit_stage2',[]))} (week)")

        if rpt.get("new_stage2"):
            print("\n  New Stage 2 entrants today:")
            for r in rpt["new_stage2"]:
                print(f"    + {r['symbol']:<14} {r.get('company_name','')[:35]:<35}  lv={r.get('live_price') or '—'}")
        if rpt.get("exit_stage2"):
            print("\n  Stage 2 exits today:")
            for r in rpt["exit_stage2"]:
                print(f"    - {r['symbol']:<14} {r.get('company_name','')[:35]:<35}  now={r.get('stage_now')}")

        if args.html or args.all:
            REPORTS_DIR.mkdir(parents=True, exist_ok=True)
            snap = rpt.get("snap_date", date.today().isoformat())
            out_path = REPORTS_DIR / f"stage2_tracker_{snap}.html"
            out_path.write_text(build_html_report(rpt), encoding="utf-8")
            print(f"\n  HTML report saved: {out_path}")
            try:
                import subprocess, sys
                if sys.platform == "darwin":
                    subprocess.Popen(["open", str(out_path)])
            except Exception:
                pass


if __name__ == "__main__":
    main()
