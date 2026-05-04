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
    "ALTER TABLE stage_snapshots ADD COLUMN supertrend_state TEXT",
    "ALTER TABLE stage_snapshots ADD COLUMN supertrend_value REAL",
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


try:
    from sector_rotation_report import compute_supertrend as _compute_supertrend  # type: ignore
    HAS_SUPERTREND = True
except ImportError:
    HAS_SUPERTREND = False


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


def _compute_rs_map(hist: pd.DataFrame) -> dict[str, float]:
    """Compute RS (stock return - Nifty 500 return) over last 50 trading days for all symbols."""
    if hist.empty:
        return {}

    INDEX_CSV = ROOT / "data" / "nse_index_data.csv"
    if not INDEX_CSV.exists():
        return {}
    try:
        idx_df = pd.read_csv(INDEX_CSV, usecols=["SYMBOL", "TIMESTAMP", "CLOSE"])
        idx_df["TIMESTAMP"] = pd.to_datetime(idx_df["TIMESTAMP"])
        nifty500 = idx_df[idx_df["SYMBOL"].str.strip().str.lower() == "nifty 500"].sort_values("TIMESTAMP")
        if len(nifty500) < 50:
            return {}
        n500_now  = float(nifty500["CLOSE"].iloc[-1])
        n500_old  = float(nifty500["CLOSE"].iloc[-50])
        if n500_old == 0:
            return {}
        idx_ret = (n500_now / n500_old) - 1.0
    except Exception:
        return {}

    rs_map: dict[str, float] = {}
    for sym, grp in hist.groupby("SYMBOL"):
        grp = grp.sort_values("TIMESTAMP")
        if len(grp) < 50:
            continue
        try:
            s_now = float(grp["CLOSE"].iloc[-1])
            s_old = float(grp["CLOSE"].iloc[-50])
            if s_old == 0:
                continue
            rs_map[sym] = round((s_now / s_old - 1.0) - idx_ret, 4)
        except Exception:
            pass
    return rs_map


def _compute_supertrend_for_symbols(hist: pd.DataFrame, symbols: list) -> dict:
    """Returns {symbol: {state: str, value: float}} using price history."""
    if hist.empty or not HAS_SUPERTREND:
        return {}
    results: dict = {}
    hist_all = hist.copy()
    hist_all["TIMESTAMP"] = pd.to_datetime(hist_all["TIMESTAMP"])
    for sym in symbols:
        try:
            sym_hist = hist_all[hist_all["SYMBOL"] == sym].sort_values("TIMESTAMP").tail(60)
            if len(sym_hist) < 20:
                continue
            # compute_supertrend expects uppercase HIGH/LOW/CLOSE columns (already present)
            st = _compute_supertrend(sym_hist)
            if st is not None and not st.empty:
                results[sym] = {
                    "state": str(st["SUPERTREND_STATE"].iloc[-1]),
                    "value": float(st["SUPERTREND"].iloc[-1]),
                }
        except Exception:
            pass
    return results


def _run_screener(analysis: pd.DataFrame, hist: pd.DataFrame) -> pd.DataFrame:
    import sys
    sys.path.insert(0, str(ROOT))
    from screeners import run_stage_screener, enrich_with_stage
    df = analysis.rename(columns={"CURRENT_PRICE": "CLOSE"}).copy()
    return run_stage_screener(df, history=hist if not hist.empty else None)


# NSE indices to sweep for live prices — covers large/mid/small/micro cap universe
_NSE_LIVE_INDICES = [
    "NIFTY 500",
    "NIFTY SMALLCAP 250",
    "NIFTY MICROCAP 250",
    "NIFTY MIDSMALLCAP 400",
    "NIFTY TOTAL MARKET",
]

_NSE_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_NSE_COOKIE_JAR = ROOT / "data" / "_nse_cookies.txt"


def _ensure_nse_session() -> bool:
    """Warm up NSE session cookie via curl. Returns True if cookie jar exists."""
    import subprocess, time
    age_ok = (
        _NSE_COOKIE_JAR.exists()
        and (time.time() - _NSE_COOKIE_JAR.stat().st_mtime) < 600
    )
    if age_ok:
        return True
    _NSE_COOKIE_JAR.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            ["curl", "-sS", "-L", "--http1.1",
             "-c", str(_NSE_COOKIE_JAR), "-o", "/dev/null", "--max-time", "30",
             "-H", f"User-Agent: {_NSE_UA}",
             "-H", "Accept: text/html,application/xhtml+xml",
             "https://www.nseindia.com"],
            capture_output=True, timeout=40,
        )
        return _NSE_COOKIE_JAR.exists() and _NSE_COOKIE_JAR.stat().st_size > 0
    except Exception:
        return False


def _nse_index_prices(index_name: str) -> dict[str, float]:
    """Fetch lastPrice for all stocks in an NSE index. Returns {symbol: price}."""
    import subprocess, json as _json, tempfile
    tmp = Path(tempfile.mktemp(suffix=".json"))
    url = f"https://www.nseindia.com/api/equity-stockIndices?index={index_name.replace(' ', '%20')}"
    try:
        r = subprocess.run(
            ["curl", "-sS", "-L", "--http1.1",
             "-o", str(tmp), "-w", "%{http_code}", "--max-time", "25",
             "-H", f"User-Agent: {_NSE_UA}",
             "-H", "Accept: application/json, text/plain, */*",
             "-H", "Referer: https://www.nseindia.com/",
             "-b", str(_NSE_COOKIE_JAR),
             url],
            capture_output=True, text=True, timeout=35,
        )
        if r.stdout.strip() != "200" or not tmp.exists():
            return {}
        with open(tmp) as f:
            data = _json.load(f)
        result = {}
        for item in data.get("data", []):
            sym = item.get("symbol", "")
            price = item.get("lastPrice")
            # skip the index row itself (no series field)
            if sym and price is not None and item.get("series"):
                try:
                    result[sym] = round(float(price), 2)
                except (TypeError, ValueError):
                    pass
        return result
    except Exception:
        return {}
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def _fetch_live_prices(symbols: list[str]) -> dict[str, float]:
    """
    Fetch latest prices from NSE India (primary) with Yahoo Finance fallback.
    Returns {symbol: price}.
    """
    results: dict[str, float] = {}

    # ── 1. NSE India bulk fetch ──────────────────────────────────────────────
    print("  Fetching live prices from NSE India …")
    if _ensure_nse_session():
        for idx in _NSE_LIVE_INDICES:
            batch = _nse_index_prices(idx)
            results.update(batch)
            print(f"    {idx}: {len(batch)} prices")
            # stop only once we've covered all requested symbols
            if all(s in results for s in symbols):
                break
    else:
        print("  NSE session could not be established.")

    covered = {s for s in symbols if s in results}
    missing = [s for s in symbols if s not in results]
    print(f"  NSE India: {len(covered)}/{len(symbols)} covered. Missing: {len(missing)}")

    # ── 2. Yahoo Finance fallback for any remaining symbols ──────────────────
    if missing:
        print(f"  Falling back to Yahoo Finance for {len(missing)} symbols …")
        try:
            import yfinance as yf
            skip = {"LIQUID", "CASHIETF", "CPSEETF", "COMMOIETF", "GROWWLIQID",
                    "LIQUIDPLUS", "LIQUIDADD", "LIQUIDCASE", "LIQUIDBETF",
                    "LIQUID1", "LIQUIDBEES"}
            yf_syms = [s for s in missing if not any(k in s for k in skip)]
            for i in range(0, len(yf_syms), 50):
                chunk = yf_syms[i:i + 50]
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
                    print(f"    YF chunk {i}–{i+50} error: {e}")
        except ImportError:
            print("  yfinance not available – skipping fallback.")

    total_covered = sum(1 for s in symbols if s in results)
    print(f"  Total live prices: {total_covered}/{len(symbols)} symbols.")
    return results


def update_live_prices(snap_date: Optional[str] = None) -> int:
    """Update live_price column for all symbols in the given (or latest) snapshot."""
    conn = get_conn()
    dates = list_snapshot_dates(conn)
    if not dates:
        print("  No snapshots available.")
        conn.close()
        return 0
    target = snap_date or dates[0]
    print(f"  Updating live prices for snapshot: {target}")
    symbols = [r[0] for r in conn.execute(
        "SELECT symbol FROM stage_snapshots WHERE snapshot_date=?", (target,)
    ).fetchall()]
    if not symbols:
        print("  No symbols found for this snapshot date.")
        conn.close()
        return 0
    live_prices = _fetch_live_prices(symbols)
    updated = 0
    for sym, price in live_prices.items():
        conn.execute(
            "UPDATE stage_snapshots SET live_price=? WHERE snapshot_date=? AND symbol=?",
            (price, target, sym),
        )
        updated += 1
    conn.commit()
    print(f"  Updated {updated} live prices for {target}.")
    conn.close()
    return updated


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

    # Pre-compute RS from price history as fallback for when CSV has NULLs
    rs_map = _compute_rs_map(hist)
    print(f"  RS computed from price history: {len(rs_map)} symbols")

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
            "relative_strength": _f(r.get("RELATIVE_STRENGTH")) or rs_map.get(sym),
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

        # Fill missing enhanced fund scores from scraped fund_details
        needs_scores = (
            fund_details_dict
            and (
                base.get("enhanced_fund_score") is None
                or (isinstance(base.get("enhanced_fund_score"), float) and base["enhanced_fund_score"] != base["enhanced_fund_score"])  # NaN
            )
        )
        if needs_scores:
            computed = _scores_from_fund_details(fund_details_dict)
            for k, v in computed.items():
                if base.get(k) is None or (isinstance(base.get(k), float) and base[k] != base[k]):
                    base[k] = v

        base["investment_score"] = _investment_score(base)
        narrative_text, stance_val = _generate_narrative(base, fund_details_dict)
        base["narrative"] = narrative_text
        base["stance"] = stance_val
        rows.append(base)

    if existing and force:
        conn.execute("DELETE FROM stage_snapshots WHERE snapshot_date=?", (today,))

    print("  Computing supertrend …")
    st_map = _compute_supertrend_for_symbols(hist, [r["symbol"] for r in rows])
    for row in rows:
        st_info = st_map.get(row["symbol"], {})
        row["supertrend_state"] = st_info.get("state")
        row["supertrend_value"] = _f(st_info.get("value"))

    conn.executemany(
        """INSERT OR REPLACE INTO stage_snapshots
            (snapshot_date, symbol, company_name, stage, stage_score, price, live_price,
             technical_score, rsi, trading_signal, trend_signal, relative_strength,
             change_1d_pct, change_1w_pct, change_1m_pct, market_cap_cat, source_csv,
             sector, fundamental_score, enhanced_fund_score, earnings_quality, sales_growth,
             financial_strength, institutional_backing, can_slim_score, minervini_score,
             investment_score, fund_details, narrative, stance, supertrend_state, supertrend_value)
           VALUES
            (:snapshot_date,:symbol,:company_name,:stage,:stage_score,:price,:live_price,
             :technical_score,:rsi,:trading_signal,:trend_signal,:relative_strength,
             :change_1d_pct,:change_1w_pct,:change_1m_pct,:market_cap_cat,:source_csv,
             :sector,:fundamental_score,:enhanced_fund_score,:earnings_quality,:sales_growth,
             :financial_strength,:institutional_backing,:can_slim_score,:minervini_score,
             :investment_score,:fund_details,:narrative,:stance,:supertrend_state,:supertrend_value)""",
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


def _scores_from_fund_details(fd: dict) -> dict:
    """
    Derive enhanced_fund_score, earnings_quality, sales_growth,
    financial_strength, institutional_backing from scraped fund_details.
    Returns dict with those keys (0-100 scale).
    """
    import re

    def _extract_num(text, pattern: str) -> float | None:
        if not isinstance(text, str):
            return None
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            try:
                return float(m.group(1).replace(",", ""))
            except Exception:
                pass
        return None

    pnl    = fd.get("pnl_summary", "")           if fd else ""
    ratios = fd.get("ratios_summary", "")         if fd else ""
    bs     = fd.get("balance_sheet_summary", "")  if fd else ""
    pnl    = pnl    if isinstance(pnl, str)    else ""
    ratios = ratios if isinstance(ratios, str) else ""
    bs     = bs     if isinstance(bs, str)     else ""

    # Sales YoY → sales_growth score (0-100)
    sales_yoy = _extract_num(pnl, r"Sales.*?YoY\s*([+\-]?\d+\.?\d*)%")
    if sales_yoy is None:
        sales_growth_score = 50.0
    else:
        # +30% → 100, 0% → 60, -20% → 20
        sales_growth_score = max(0.0, min(100.0, 60 + sales_yoy * 1.3))

    # Net Profit YoY → earnings_quality score
    np_yoy = _extract_num(pnl, r"NetProfit.*?YoY\s*([+\-]?\d+\.?\d*)%")
    if np_yoy is None:
        earnings_quality = 50.0
    else:
        earnings_quality = max(0.0, min(100.0, 60 + np_yoy * 0.8))

    # ROCE → financial_strength
    roce = _extract_num(ratios, r"ROCE[:\s]*([0-9.]+)")
    npm = _extract_num(ratios, r"NPM[:\s]*([0-9.]+)")
    debt_cr = _extract_num(bs, r"Debt[:\s]*([\d,]+)")
    assets_cr = _extract_num(bs, r"Assets[:\s]*([\d,]+)")
    if roce is not None:
        fs = max(0.0, min(100.0, roce * 2.5))   # ROCE 20% → 50, 40% → 100
    elif npm is not None:
        fs = max(0.0, min(100.0, npm * 5))
    else:
        fs = 50.0
    # Penalise high debt/assets ratio
    if debt_cr and assets_cr and assets_cr > 0:
        debt_ratio = debt_cr / assets_cr
        fs = max(0.0, fs - debt_ratio * 30)
    financial_strength = fs

    # institutional_backing: no per-stock data from screener; use moderate default
    institutional_backing = 50.0

    # Composite enhanced_fund_score
    enhanced_fund_score = round(
        sales_growth_score * 0.30
        + earnings_quality * 0.35
        + financial_strength * 0.25
        + institutional_backing * 0.10,
        1,
    )

    return {
        "enhanced_fund_score": enhanced_fund_score,
        "earnings_quality": round(earnings_quality, 1),
        "sales_growth": round(sales_growth_score, 1),
        "financial_strength": round(financial_strength, 1),
        "institutional_backing": round(institutional_backing, 1),
    }


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

    # Trend data across last 10 snapshots
    result["trend"] = _build_trend_data(conn, today_snap)

    conn.close()
    return result


def _build_trend_data(conn: sqlite3.Connection, snap_date: str) -> dict:
    """Query last 10 snapshots for trend charts: breadth, sector, avg metrics."""
    # Last 10 dates up to snap_date
    rows = conn.execute(
        "SELECT DISTINCT snapshot_date FROM stage_snapshots "
        "WHERE snapshot_date <= ? ORDER BY snapshot_date DESC LIMIT 10",
        (snap_date,)
    ).fetchall()
    dates = [r[0] for r in reversed(rows)]

    # Stage counts per day
    breadth = []
    for d in dates:
        r = conn.execute(
            "SELECT "
            "  SUM(CASE WHEN stage='STAGE_1' THEN 1 ELSE 0 END),"
            "  SUM(CASE WHEN stage='STAGE_2' THEN 1 ELSE 0 END),"
            "  SUM(CASE WHEN stage='STAGE_3' THEN 1 ELSE 0 END),"
            "  SUM(CASE WHEN stage='STAGE_4' THEN 1 ELSE 0 END),"
            "  COUNT(*)"
            " FROM stage_snapshots WHERE snapshot_date=?", (d,)
        ).fetchone()
        breadth.append({"date": d, "s1": r[0] or 0, "s2": r[1] or 0, "s3": r[2] or 0, "s4": r[3] or 0, "total": r[4] or 0})

    # Avg metrics for Stage 2 per day
    metrics = []
    for d in dates:
        r = conn.execute(
            "SELECT ROUND(AVG(CAST(technical_score AS REAL)),1),"
            "       ROUND(AVG(CAST(rsi AS REAL)),1),"
            "       ROUND(AVG(CAST(change_1m_pct AS REAL)),1),"
            "       ROUND(AVG(CAST(investment_score AS REAL)),1)"
            " FROM stage_snapshots WHERE snapshot_date=? AND stage='STAGE_2'", (d,)
        ).fetchone()
        metrics.append({"date": d, "avg_tech": r[0], "avg_rsi": r[1], "avg_1m": r[2], "avg_inv": r[3]})

    # Sector breakdown for Stage 2 today
    sec_rows = conn.execute(
        "SELECT sector, COUNT(*) cnt FROM stage_snapshots "
        "WHERE snapshot_date=? AND stage='STAGE_2' "
        "GROUP BY sector ORDER BY cnt DESC", (snap_date,)
    ).fetchall()
    sectors = [{"sector": r[0] or "Unknown", "count": r[1]} for r in sec_rows]

    # Entries/exits for snap_date vs previous
    prev_date_row = conn.execute(
        "SELECT MAX(snapshot_date) FROM stage_snapshots WHERE snapshot_date < ?", (snap_date,)
    ).fetchone()
    prev_date = prev_date_row[0] if prev_date_row else None
    entries, exits = [], []
    if prev_date:
        e_rows = conn.execute(
            "SELECT sc.symbol, ss.sector, ss.live_price, ss.rsi, ss.change_1m_pct "
            "FROM stage_changes sc "
            "JOIN stage_snapshots ss ON sc.symbol=ss.symbol AND ss.snapshot_date=? "
            "WHERE sc.change_date=? AND sc.compare_date=? AND sc.change_type='NEW_STAGE2' "
            "GROUP BY sc.symbol",
            (snap_date, snap_date, prev_date)
        ).fetchall()
        entries = [{"symbol": r[0], "sector": r[1] or "Other", "price": r[2], "rsi": r[3], "chg_1m": r[4]} for r in e_rows]
        x_rows = conn.execute(
            "SELECT sc.symbol, ss.sector, ss.live_price, ss.rsi, sc.stage_now "
            "FROM stage_changes sc "
            "JOIN stage_snapshots ss ON sc.symbol=ss.symbol AND ss.snapshot_date=? "
            "WHERE sc.change_date=? AND sc.compare_date=? AND sc.change_type='EXIT_STAGE2' "
            "GROUP BY sc.symbol",
            (snap_date, snap_date, prev_date)
        ).fetchall()
        exits = [{"symbol": r[0], "sector": r[1] or "Other", "price": r[2], "rsi": r[3], "now_stage": r[4]} for r in x_rows]

    return {
        "dates": dates,
        "breadth": breadth,
        "metrics": metrics,
        "sectors": sectors,
        "entries": entries,
        "exits": exits,
    }


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
.sum-card{background:#fff;border-radius:8px;padding:14px 20px;box-shadow:0 1px 3px rgba(0,0,0,.08);min-width:140px;border-top:3px solid transparent}
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
/* ── Modal overlay ── */
.modal-overlay{display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,.5);z-index:100;align-items:center;justify-content:center}
.modal-overlay.open{display:flex}
.modal-box{background:#fff;border-radius:12px;padding:24px;max-width:640px;width:90%;max-height:85vh;overflow-y:auto;position:relative;box-shadow:0 20px 60px rgba(0,0,0,.2)}
.modal-close{position:absolute;top:12px;right:16px;font-size:1.4rem;cursor:pointer;color:#64748b;border:none;background:none;line-height:1}
.modal-title{font-size:1.1rem;font-weight:700;margin-bottom:4px}
.modal-sector{font-size:.8rem;color:#0369a1;background:#e0f2fe;padding:2px 8px;border-radius:4px;display:inline-block;margin-bottom:12px}
.mfund-bars{display:flex;flex-direction:column;gap:8px;margin:12px 0}
.mfund-row{display:flex;align-items:center;gap:8px}
.mfund-lbl{font-size:.78rem;color:#475569;min-width:140px}
.mfund-track{flex:1;height:7px;background:#e2e8f0;border-radius:4px}
.mfund-fill{height:100%;border-radius:4px}
.mfund-num{font-size:.78rem;font-weight:600;min-width:28px;text-align:right}
.mnarr{font-size:.85rem;color:#334155;line-height:1.6;margin:10px 0;padding:10px 14px;background:#f8fafc;border-radius:6px;border-left:3px solid #059669}
.mfund-txt{font-size:.78rem;color:#475569;margin-top:6px;line-height:1.5;padding:8px 12px;background:#f1f5f9;border-radius:6px}
/* ── Transition section ── */
.trans-section{background:#fff;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,.08);padding:14px 18px;margin-bottom:20px;display:flex;align-items:center;flex-wrap:wrap;gap:12px}
.trans-label{font-size:.72rem;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:.06em;white-space:nowrap}
.trans-flows{display:flex;flex-wrap:wrap;gap:16px;flex:1}
.trans-group{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.tg-hdr{font-size:.72rem;font-weight:700;padding:2px 8px;border-radius:4px;white-space:nowrap}
.tg-up{background:#dcfce7;color:#166534}.tg-dn{background:#fee2e2;color:#991b1b}
.trans-flow-item{display:flex;align-items:center;gap:3px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:5px 10px;cursor:default}
.tf-from,.tf-to{font-size:.78rem;font-weight:700;color:#334155}
.tf-arrow{font-size:1rem;font-weight:900;line-height:1;padding:0 2px}
.tf-count{font-size:.85rem;font-weight:800;padding:1px 7px;border-radius:10px;margin-left:4px}
.trans-note{font-size:.78rem;color:#94a3b8;font-style:italic}
</style>"""


def _build_trend_html(trend: dict, snap_date: str) -> str:
    """Build a Market Trends panel with Chart.js charts."""
    if not trend or not trend.get("dates"):
        return ""

    import json as _json

    dates     = trend["dates"]
    breadth   = trend["breadth"]
    metrics   = trend["metrics"]
    sectors   = trend["sectors"]
    entries   = trend["entries"]
    exits     = trend["exits"]

    # Short date labels e.g. "Apr 21"
    def short_date(d: str) -> str:
        try:
            from datetime import datetime as _dt
            return _dt.fromisoformat(d).strftime("%b %d")
        except Exception:
            return d

    labels_js   = _json.dumps([short_date(d) for d in dates])
    s2_counts   = _json.dumps([b["s2"] for b in breadth])
    s1_counts   = _json.dumps([b["s1"] for b in breadth])
    s3_counts   = _json.dumps([b["s3"] for b in breadth])
    s4_counts   = _json.dumps([b["s4"] for b in breadth])
    rsi_vals    = _json.dumps([m["avg_rsi"]  for m in metrics])
    tech_vals   = _json.dumps([m["avg_tech"] for m in metrics])
    chg1m_vals  = _json.dumps([m["avg_1m"]   for m in metrics])

    sec_labels  = _json.dumps([s["sector"] for s in sectors])
    sec_counts  = _json.dumps([s["count"]  for s in sectors])

    # Entries/exits table rows
    def entry_rows():
        rows = ""
        for e in entries:
            rsi_v = f'{e["rsi"]:.0f}' if e["rsi"] else "—"
            chg   = f'{e["chg_1m"]:.1f}%' if e["chg_1m"] is not None else "—"
            price = f'₹{e["price"]:,.2f}' if e["price"] else "—"
            rows += f'<tr><td><strong>{_H(e["symbol"])}</strong></td><td>{_H(e["sector"])}</td><td>{price}</td><td>{rsi_v}</td><td style="color:#16a34a;font-weight:600">{chg}</td></tr>\n'
        return rows or '<tr><td colspan="5" style="text-align:center;color:#94a3b8">No entries</td></tr>'

    def exit_rows():
        rows = ""
        for e in exits:
            price = f'₹{e["price"]:,.2f}' if e["price"] else "—"
            rsi_v = f'{e["rsi"]:.0f}' if e["rsi"] else "—"
            rows += f'<tr><td><strong>{_H(e["symbol"])}</strong></td><td>{_H(e["sector"])}</td><td>{price}</td><td>{rsi_v}</td><td><span style="background:#fee2e2;color:#991b1b;padding:1px 7px;border-radius:4px;font-size:.75rem">{_H(e["now_stage"])}</span></td></tr>\n'
        return rows or '<tr><td colspan="5" style="text-align:center;color:#94a3b8">No exits</td></tr>'

    # Colour palette for sector donut
    palette = ["#0ea5e9","#16a34a","#7c3aed","#f59e0b","#ef4444","#06b6d4","#84cc16","#ec4899","#6366f1","#14b8a6","#f97316","#a855f7"]
    bg_colors = _json.dumps((palette * 4)[:len(sectors)])

    return f"""
<div class="section" style="margin-bottom:20px">
  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px">
    <h2 style="font-size:1.05rem;font-weight:700;color:#0f172a;margin:0">📊 Market Trends &nbsp;<span style="font-size:.8rem;font-weight:400;color:#64748b">Last {len(dates)} trading days</span></h2>
  </div>

  <!-- Row 1: Breadth + Sector donut -->
  <div style="display:grid;grid-template-columns:2fr 1fr;gap:16px;margin-bottom:16px">

    <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;padding:16px">
      <div style="font-size:.8rem;font-weight:700;text-transform:uppercase;letter-spacing:.05em;color:#64748b;margin-bottom:10px">Market Breadth — Stage Distribution</div>
      <div style="position:relative;height:220px"><canvas id="breadthChart"></canvas></div>
    </div>

    <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;padding:16px">
      <div style="font-size:.8rem;font-weight:700;text-transform:uppercase;letter-spacing:.05em;color:#64748b;margin-bottom:10px">Stage 2 Sectors — Today</div>
      <div style="position:relative;height:220px"><canvas id="sectorChart"></canvas></div>
    </div>

  </div>

  <!-- Row 2: RSI + Tech + 1m perf line charts -->
  <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px;margin-bottom:16px">

    <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;padding:16px">
      <div style="font-size:.8rem;font-weight:700;text-transform:uppercase;letter-spacing:.05em;color:#64748b;margin-bottom:10px">Avg RSI — Stage 2</div>
      <div style="position:relative;height:160px"><canvas id="rsiChart"></canvas></div>
    </div>

    <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;padding:16px">
      <div style="font-size:.8rem;font-weight:700;text-transform:uppercase;letter-spacing:.05em;color:#64748b;margin-bottom:10px">Avg Tech Score — Stage 2</div>
      <div style="position:relative;height:160px"><canvas id="techChart"></canvas></div>
    </div>

    <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;padding:16px">
      <div style="font-size:.8rem;font-weight:700;text-transform:uppercase;letter-spacing:.05em;color:#64748b;margin-bottom:10px">Avg 1-Month Return — Stage 2</div>
      <div style="position:relative;height:160px"><canvas id="chg1mChart"></canvas></div>
    </div>

  </div>

  <!-- Row 3: Entries / Exits tables -->
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">

    <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:10px;padding:16px">
      <div style="font-size:.8rem;font-weight:700;text-transform:uppercase;letter-spacing:.05em;color:#15803d;margin-bottom:10px">🟢 New Stage 2 Entries ({len(entries)})</div>
      <table style="width:100%;font-size:.78rem;border-collapse:collapse">
        <thead><tr style="color:#64748b;border-bottom:1px solid #e2e8f0">
          <th style="text-align:left;padding:4px 6px">Symbol</th>
          <th style="text-align:left;padding:4px 6px">Sector</th>
          <th style="text-align:right;padding:4px 6px">Price</th>
          <th style="text-align:right;padding:4px 6px">RSI</th>
          <th style="text-align:right;padding:4px 6px">1M Chg</th>
        </tr></thead>
        <tbody>{entry_rows()}</tbody>
      </table>
    </div>

    <div style="background:#fff5f5;border:1px solid #fecaca;border-radius:10px;padding:16px">
      <div style="font-size:.8rem;font-weight:700;text-transform:uppercase;letter-spacing:.05em;color:#991b1b;margin-bottom:10px">🔴 Stage 2 Exits ({len(exits)})</div>
      <table style="width:100%;font-size:.78rem;border-collapse:collapse">
        <thead><tr style="color:#64748b;border-bottom:1px solid #e2e8f0">
          <th style="text-align:left;padding:4px 6px">Symbol</th>
          <th style="text-align:left;padding:4px 6px">Sector</th>
          <th style="text-align:right;padding:4px 6px">Price</th>
          <th style="text-align:right;padding:4px 6px">RSI</th>
          <th style="text-align:right;padding:4px 6px">Now</th>
        </tr></thead>
        <tbody>{exit_rows()}</tbody>
      </table>
    </div>

  </div>
</div>

<script>
(function(){{
  var labels = {labels_js};
  var s2 = {s2_counts}, s1 = {s1_counts}, s3 = {s3_counts}, s4 = {s4_counts};

  // Breadth stacked bar
  new Chart(document.getElementById('breadthChart'), {{
    type: 'bar',
    data: {{
      labels: labels,
      datasets: [
        {{label:'Stage 2 ✅', data: s2, backgroundColor:'#16a34a', stack:'a'}},
        {{label:'Stage 1',    data: s1, backgroundColor:'#f59e0b', stack:'a'}},
        {{label:'Stage 3',    data: s3, backgroundColor:'#f97316', stack:'a'}},
        {{label:'Stage 4 ❌', data: s4, backgroundColor:'#dc2626', stack:'a'}},
      ]
    }},
    options: {{responsive:true, maintainAspectRatio:false,
      plugins:{{legend:{{position:'bottom', labels:{{font:{{size:10}}}}}}}},
      scales:{{x:{{stacked:true, ticks:{{font:{{size:10}}}}}}, y:{{stacked:true, ticks:{{font:{{size:10}}}}}}}}
    }}
  }});

  // Sector donut
  new Chart(document.getElementById('sectorChart'), {{
    type: 'doughnut',
    data: {{
      labels: {sec_labels},
      datasets: [{{data: {sec_counts}, backgroundColor: {bg_colors}, borderWidth: 1}}]
    }},
    options: {{responsive:true, maintainAspectRatio:false,
      plugins:{{legend:{{position:'right', labels:{{font:{{size:10}}, boxWidth:10}}}}, tooltip:{{callbacks:{{label: function(ctx){{ return ctx.label + ': ' + ctx.raw; }}}}}}}}
    }}
  }});

  function lineChart(id, data, color, label, minY, maxY) {{
    new Chart(document.getElementById(id), {{
      type: 'line',
      data: {{labels: labels, datasets: [{{label: label, data: data,
        borderColor: color, backgroundColor: color + '22',
        fill: true, tension: 0.3, pointRadius: 4, pointHoverRadius: 6}}]}},
      options: {{responsive:true, maintainAspectRatio:false,
        plugins:{{legend:{{display:false}}}},
        scales:{{
          x:{{ticks:{{font:{{size:10}}}}}},
          y:{{min: minY, max: maxY, ticks:{{font:{{size:10}}}}}}
        }}
      }}
    }});
  }}

  var rsiData  = {rsi_vals};
  var techData = {tech_vals};
  var chgData  = {chg1m_vals};

  var rsiMin  = Math.max(0,  Math.min.apply(null, rsiData.filter(function(v){{return v!=null;}})) - 5);
  var rsiMax  = Math.min(100,Math.max.apply(null, rsiData.filter(function(v){{return v!=null;}})) + 5);
  var techMin = Math.max(0,  Math.min.apply(null, techData.filter(function(v){{return v!=null;}})) - 5);
  var techMax = Math.min(100,Math.max.apply(null, techData.filter(function(v){{return v!=null;}})) + 5);
  var chgMin  = Math.min.apply(null, chgData.filter(function(v){{return v!=null;}})) - 2;
  var chgMax  = Math.max.apply(null, chgData.filter(function(v){{return v!=null;}})) + 2;

  lineChart('rsiChart',   rsiData,  '#0891b2', 'Avg RSI',        rsiMin,  rsiMax);
  lineChart('techChart',  techData, '#7c3aed', 'Avg Tech Score', techMin, techMax);
  lineChart('chg1mChart', chgData,  '#16a34a', 'Avg 1M Chg %',  chgMin,  chgMax);
}})();
</script>
"""


def build_html_report(report: dict) -> str:
    snap = report.get("snap_date", "N/A")
    prev = report.get("prev_date", "N/A")
    week = report.get("week_snap", "N/A")
    summ = report.get("summary", {})
    now_ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    trend = report.get("trend", {})

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
            if fv != fv:  # NaN check
                return "—"
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
                if fv != fv:  # NaN check
                    return "—"
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
                {"key": "rank",        "label": "#",                     "toggleable": False},
                {"key": "symbol",      "label": "Symbol",                "toggleable": False},
                {"key": "company",     "label": "Company",               "toggleable": True, "default": True},
                {"key": "sector",      "label": "Sector",                "toggleable": True, "default": True},
                {"key": "stage",       "label": "Stage",                 "toggleable": True, "default": True},
                {"key": "signal",      "label": "Signal",                "toggleable": True, "default": True},
                {"key": "live_price",  "label": "Live ₹",                "toggleable": True, "default": True},
                {"key": "csv_price",   "label": f"Close {snap[:10]}",    "toggleable": True, "default": True},
                {"key": "live_pct",    "label": "Live Chg%",             "toggleable": True, "default": True},
                {"key": "tech_score",  "label": "Tech Score",            "toggleable": True, "default": True},
                {"key": "rsi",         "label": "RSI",                   "toggleable": True, "default": True},
                {"key": "supertrend",  "label": "Supertrend",            "toggleable": True, "default": True},
                {"key": "trend",       "label": "Trend",                 "toggleable": True, "default": False},
                {"key": "rs",          "label": "RS",                    "toggleable": True, "default": True},
                {"key": "chg1d",       "label": "1D%",                   "toggleable": True, "default": True},
                {"key": "chg1w",       "label": "1W%",                   "toggleable": True, "default": True},
                {"key": "chg1m",       "label": "1M%",                   "toggleable": True, "default": False},
                {"key": "cap",         "label": "Cap",                   "toggleable": True, "default": False},
                {"key": "stage_score", "label": "Score",                 "toggleable": True, "default": True},
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
                st_state = r.get("supertrend_state")
                st_value = r.get("supertrend_value")

                def _supertrend_cell(state, value, col_idx):
                    if not state or state == "UNKNOWN":
                        return f'<td{td_style(col_idx)} style="color:#94a3b8">—</td>'
                    color = "#16a34a" if state == "BULLISH" else "#dc2626"
                    arrow = "↑" if state == "BULLISH" else "↓"
                    val_str = f"₹{float(value):,.0f}" if value else ""
                    return (f'<td{td_style(col_idx)}>'
                            f'<span style="color:{color};font-weight:600;font-size:.82rem">{arrow} {state}</span>'
                            f'<br><span style="font-size:.72rem;color:#64748b">{val_str}</span>'
                            f'</td>')

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
                    _supertrend_cell(st_state, st_value, 11),
                    f'<td{td_style(12)} style="font-size:.75rem">{_H(str(r.get("trend_signal","") or ""))}</td>',
                    _pct_cell(rs_val).replace("<td", f'<td{td_style(13)}', 1),
                    _pct_cell(r.get("change_1d_pct")).replace("<td", f'<td{td_style(14)}', 1),
                    _pct_cell(r.get("change_1w_pct")).replace("<td", f'<td{td_style(15)}', 1),
                    _pct_cell(r.get("change_1m_pct")).replace("<td", f'<td{td_style(16)}', 1),
                    f'<td{td_style(17)} style="font-size:.75rem">{_H(str(r.get("market_cap_cat","") or ""))}</td>',
                    f'<td{td_style(18)} style="text-align:right">{r.get("stage_score") or "—"}</td>',
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

    # ── helpers for delta badge on cards ─────────────────────────────────────
    def _delta_badge(net: int) -> str:
        """Green ▲N or red ▼N badge, or blank if zero."""
        if net > 0:
            return f'<span style="font-size:.75rem;font-weight:700;color:#16a34a;margin-left:6px">▲{net}</span>'
        if net < 0:
            return f'<span style="font-size:.75rem;font-weight:700;color:#dc2626;margin-left:6px">▼{abs(net)}</span>'
        return '<span style="font-size:.75rem;color:#94a3b8;margin-left:6px">—</span>'

    # net change per stage: entries into - exits from each stage
    s1_net = trans.get("S2_to_S1", 0) - trans.get("S1_to_S2", 0)
    s2_net = (trans.get("S1_to_S2", 0) + trans.get("S3_to_S2", 0)
              - trans.get("S2_to_S1", 0) - trans.get("S2_to_S3", 0))
    s3_net = trans.get("S2_to_S3", 0) - trans.get("S3_to_S2", 0) - trans.get("S3_to_S4", 0)
    s4_net = trans.get("S3_to_S4", 0)

    def _stage_card(label: str, count: int, color: str, emoji: str, delta: int, sublabel: str = "") -> str:
        return (
            f'<div class="sum-card" style="border-top:3px solid {color}">'
            f'<div style="display:flex;align-items:baseline;gap:0">'
            f'<div class="sc-val" style="color:{color}">{count}</div>'
            f'{_delta_badge(delta)}'
            f'</div>'
            f'<div class="sc-lbl">{emoji} {label}</div>'
            + (f'<div style="font-size:.7rem;color:#94a3b8;margin-top:2px">{sublabel}</div>' if sublabel else '')
            + '</div>'
        )

    stage_count_html = (
        _stage_card("Stage 1", stage_counts.get("STAGE_1", 0), "#ca8a04", "🟡", s1_net, "Accumulation / Basing")
        + _stage_card("Stage 2", stage_counts.get("STAGE_2", 0), "#16a34a", "🟢", s2_net, "Advancing / Uptrend")
        + _stage_card("Stage 3", stage_counts.get("STAGE_3", 0), "#ea580c", "🟠", s3_net, "Topping / Distribution")
        + _stage_card("Stage 4", stage_counts.get("STAGE_4", 0), "#dc2626", "🔴", s4_net, "Declining / Downtrend")
    )

    # ── Transition flow visual ────────────────────────────────────────────────
    def _trans_arrow(frm: str, to: str, count: int, is_upgrade: bool) -> str:
        if not count:
            return ""
        color = "#16a34a" if is_upgrade else "#dc2626"
        arrow = "↑" if is_upgrade else "↓"
        title = f"{frm} → {to}: {count} stock{'s' if count!=1 else ''} moved {'up' if is_upgrade else 'down'}"
        return (
            f'<div class="trans-flow-item" title="{title}">'
            f'<span class="tf-from">{frm}</span>'
            f'<span class="tf-arrow" style="color:{color}">{arrow}</span>'
            f'<span class="tf-to">{to}</span>'
            f'<span class="tf-count" style="background:{color}20;color:{color}">{count}</span>'
            f'</div>'
        )

    upgrades = (
        _trans_arrow("S1", "S2", trans.get("S1_to_S2", 0), True)
        + _trans_arrow("S2", "S3", trans.get("S2_to_S3", 0), False)  # S3 is distribution — bad
        + _trans_arrow("S3", "S4", trans.get("S3_to_S4", 0), False)
    )
    downgrades = (
        _trans_arrow("S2", "S1", trans.get("S2_to_S1", 0), False)
        + _trans_arrow("S3", "S2", trans.get("S3_to_S2", 0), True)   # S3→S2 would be unusual
    )

    has_transitions = any(trans.values())
    if has_transitions:
        trans_html = (
            '<div class="trans-section">'
            '<div class="trans-label">Stage Transitions (vs prev snapshot)</div>'
            '<div class="trans-flows">'
            + (f'<div class="trans-group"><span class="tg-hdr tg-up">▲ Upgrades</span>{upgrades}</div>' if upgrades else '')
            + (f'<div class="trans-group"><span class="tg-hdr tg-dn">▼ Downgrades</span>{downgrades}</div>' if downgrades else '')
            + '</div>'
            + (f'<div class="trans-note">No stage transitions recorded yet — add more daily snapshots to track movement.</div>' if not upgrades and not downgrades else '')
            + '</div>'
        )
    else:
        trans_html = (
            '<div class="trans-section">'
            '<div class="trans-label">Stage Transitions</div>'
            '<div class="trans-note">No transitions yet — run daily snapshots to track movement over time.</div>'
            '</div>'
        )

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
        import json as _json

        # Build JSON data for all picks (for the modal)
        picks_data = []
        for pk in picks:
            fd = {}
            try:
                fd = _json.loads(pk.get("fund_details") or "{}")
            except Exception:
                pass
            picks_data.append({
                "symbol": str(pk.get("symbol", "")),
                "company": str(pk.get("company_name", ""))[:60],
                "sector": str(pk.get("sector", "Other")),
                "investment_score": float(pk.get("investment_score") or 0),
                "stance": str(pk.get("stance") or "NEUTRAL"),
                "narrative": str(pk.get("narrative") or ""),
                "technical_score": float(pk.get("technical_score") or 0),
                "rsi": float(pk.get("rsi") or 0),
                "enhanced_fund_score": float(pk.get("enhanced_fund_score") or 0),
                "earnings_quality": float(pk.get("earnings_quality") or 0),
                "sales_growth": float(pk.get("sales_growth") or 0),
                "financial_strength": float(pk.get("financial_strength") or 0),
                "institutional_backing": float(pk.get("institutional_backing") or 0),
                "can_slim_score": float(pk.get("can_slim_score") or 0),
                "minervini_score": float(pk.get("minervini_score") or 0),
                "pnl_summary": str(fd.get("pnl_summary") or ""),
                "quarterly_summary": str(fd.get("quarterly_summary") or ""),
                "ratios_summary": str(fd.get("ratios_summary") or ""),
                "trend_signal": str(pk.get("trend_signal") or ""),
                "live_price": float(pk.get("live_price") or pk.get("price") or 0),
                "stage_score": float(pk.get("stage_score") or 0),
            })
        picks_json = _json.dumps(picks_data)

        pick_cards = []
        for i, pk in enumerate(picks):
            inv = pk.get("investment_score") or 0
            stance = str(pk.get("stance") or "NEUTRAL").upper()
            stance_cls = {"BULLISH": "stance-bull", "BEARISH": "stance-bear"}.get(stance, "stance-neut")
            pick_cards.append(
                f'<div class="pick-card" data-idx="{i}" onclick="showPickModal({i})">'
                f'<div class="pk-sym">{_H(str(pk.get("symbol","")))}</div>'
                f'<div class="pk-co">{_H(str(pk.get("company_name",""))[:40])}</div>'
                f'<span class="pk-sector">{_H(str(pk.get("sector","Other")))}</span>'
                f'<div class="pk-inv">{float(inv):.0f} <span style="font-size:.8rem;color:#64748b">inv. score</span></div>'
                f'<div class="pk-meta">Tech {pk.get("technical_score") or "—"} · RSI {pk.get("rsi") or "—"} · <span class="{stance_cls}">{stance}</span></div>'
                f'</div>'
            )

        modal_html = (
            '<div id="pick-modal" class="modal-overlay" onclick="if(event.target===this)closePickModal()">'
            '<div class="modal-box" id="pick-modal-box">'
            '<button class="modal-close" onclick="closePickModal()">×</button>'
            '<div id="pick-modal-content"></div>'
            '</div></div>'
        )

        return (
            f'<script>var PICKS_DATA={picks_json};</script>'
            + modal_html
            + '<div class="section" style="margin-bottom:20px">'
            '<div class="sec-hdr" style="border-left:4px solid #059669">'
            '<h2>🏆 Top Investment Picks (Stage 2)</h2>'
            f'<span class="badge-count">{len(picks)}</span>'
            '<span style="font-size:.75rem;color:#64748b;margin-left:8px">Click any card for details</span>'
            '</div>'
            f'<div class="picks-grid">{"".join(pick_cards)}</div>'
            '</div>'
        )
    picks_section = top_picks_html(top_picks)

    # ── Trend Section ─────────────────────────────────────────────────────────
    trend_section = _build_trend_html(trend, snap)

    # ── Tabs ─────────────────────────────────────────────────────────────────
    help_tab_content = """
<div style="padding:24px 28px;max-width:900px;font-size:.88rem;line-height:1.7;color:#334155">

  <h2 style="font-size:1.1rem;font-weight:700;color:#065f46;margin-bottom:16px">📖 How to Read This Report</h2>

  <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:20px">

    <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:10px;padding:16px">
      <h3 style="font-size:.9rem;font-weight:700;color:#15803d;margin-bottom:10px">🏗 Weinstein Stage Method</h3>
      <p style="margin-bottom:8px"><span style="background:#fef9c3;color:#854d0e;font-weight:700;padding:1px 7px;border-radius:4px;font-size:.8rem">Stage 1 – Basing</span><br>
      Price moves sideways, SMA50 flattening. Stock consolidating after decline. <em>Watch for breakout.</em></p>
      <p style="margin-bottom:8px"><span style="background:#dcfce7;color:#166534;font-weight:700;padding:1px 7px;border-radius:4px;font-size:.8rem">Stage 2 ✅ – Advancing</span><br>
      Price above SMA50 &amp; SMA200, both rising. <strong>Best risk/reward for new positions.</strong></p>
      <p style="margin-bottom:8px"><span style="background:#ffedd5;color:#9a3412;font-weight:700;padding:1px 7px;border-radius:4px;font-size:.8rem">Stage 3 – Topping</span><br>
      Price stalls near highs, SMA50 flattening. <em>Tighten stops or exit.</em></p>
      <p><span style="background:#fee2e2;color:#991b1b;font-weight:700;padding:1px 7px;border-radius:4px;font-size:.8rem">Stage 4 ❌ – Declining</span><br>
      Price below SMA50 &amp; SMA200, both falling. <em>Avoid.</em></p>
    </div>

    <div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:10px;padding:16px">
      <h3 style="font-size:.9rem;font-weight:700;color:#1d4ed8;margin-bottom:10px">📊 RSI (Relative Strength Index)</h3>
      <p style="margin-bottom:6px"><span style="color:#1e40af;font-weight:700">&lt; 30</span> — Oversold (potential reversal up)</p>
      <p style="margin-bottom:6px"><span style="color:#475569;font-weight:700">30–50</span> — Weak / recovering</p>
      <p style="margin-bottom:6px"><span style="color:#166534;font-weight:700">50–70 ✅</span> — Bullish momentum</p>
      <p style="margin-bottom:12px"><span style="color:#991b1b;font-weight:700">&gt; 70</span> — Overbought (watch for pullback)</p>

      <h3 style="font-size:.9rem;font-weight:700;color:#1d4ed8;margin-bottom:8px">📈 Relative Strength (RS)</h3>
      <p>Price performance vs Nifty 500 over 12 months. <strong>Positive RS</strong> = outperforming the index.</p>
    </div>

  </div>

  <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:20px">

    <div style="background:#fdf4ff;border:1px solid #e9d5ff;border-radius:10px;padding:16px">
      <h3 style="font-size:.9rem;font-weight:700;color:#7e22ce;margin-bottom:10px">⚡ Supertrend (ATR-based)</h3>
      <p style="margin-bottom:8px">Period = 10, Multiplier = 3. Uses Average True Range (ATR) to set dynamic support/resistance bands.</p>
      <p style="margin-bottom:6px"><span style="color:#16a34a;font-weight:700">↑ BULLISH</span> — Price above supertrend band (green support). Trend is up — trailing stop holds.</p>
      <p><span style="color:#dc2626;font-weight:700">↓ BEARISH</span> — Price below supertrend band (red resistance). Trend has reversed down.</p>
    </div>

    <div style="background:#fff7ed;border:1px solid #fed7aa;border-radius:10px;padding:16px">
      <h3 style="font-size:.9rem;font-weight:700;color:#c2410c;margin-bottom:10px">📡 Trend Signal</h3>
      <p style="margin-bottom:6px"><strong>STRONG_BULLISH</strong> — Both SMA50 &amp; SMA200 rising, price above both.</p>
      <p style="margin-bottom:6px"><strong>BULLISH</strong> — Price above SMA50.</p>
      <p style="margin-bottom:6px"><strong>NEUTRAL</strong> — Mixed signals.</p>
      <p><strong>BEARISH</strong> — Price below SMA50 and/or SMA200.</p>
    </div>

  </div>

  <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;padding:16px;margin-bottom:20px">
    <h3 style="font-size:.9rem;font-weight:700;color:#0f172a;margin-bottom:10px">🏆 Investment Score (0–100)</h3>
    <p style="margin-bottom:8px">Composite metric combining:</p>
    <div style="display:flex;flex-wrap:wrap;gap:8px">
      <span style="background:#dcfce7;color:#166534;padding:3px 10px;border-radius:6px;font-size:.8rem;font-weight:600">Technical Score 30%</span>
      <span style="background:#ede9fe;color:#6d28d9;padding:3px 10px;border-radius:6px;font-size:.8rem;font-weight:600">Fund Score 25%</span>
      <span style="background:#dbeafe;color:#1e40af;padding:3px 10px;border-radius:6px;font-size:.8rem;font-weight:600">Relative Strength 15%</span>
      <span style="background:#fef9c3;color:#854d0e;padding:3px 10px;border-radius:6px;font-size:.8rem;font-weight:600">Stage Score 15%</span>
      <span style="background:#fce7f3;color:#9d174d;padding:3px 10px;border-radius:6px;font-size:.8rem;font-weight:600">RSI Optimality 15%</span>
    </div>
  </div>

  <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;padding:16px;margin-bottom:20px">
    <h3 style="font-size:.9rem;font-weight:700;color:#0f172a;margin-bottom:10px">🔬 Technical Score (0–100)</h3>
    <p>Composite of: RSI momentum · Supertrend direction · SMA trend alignment · 1W/1M price momentum · Distance from 52-week high · Relative Strength vs index.</p>
  </div>

  <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;padding:16px;margin-bottom:20px">
    <h3 style="font-size:.9rem;font-weight:700;color:#0f172a;margin-bottom:10px">📋 Fundamental Metrics</h3>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;font-size:.82rem">
      <p><strong>Enhanced Fund Score</strong> — Quality-adjusted earnings + growth composite.</p>
      <p><strong>Earnings Quality</strong> — Consistency and reliability of profits.</p>
      <p><strong>Sales Growth</strong> — Revenue growth trajectory.</p>
      <p><strong>Financial Strength</strong> — Debt/equity, interest coverage, cash flow.</p>
      <p><strong>Institutional Backing</strong> — FII/DII ownership trend.</p>
      <p><strong>CAN SLIM Score</strong> — O'Neil's criteria: EPS growth, RS, New highs, etc.</p>
      <p><strong>Minervini Score</strong> — Trend template: price &gt; SMA50 &gt; SMA150 &gt; SMA200.</p>
    </div>
  </div>

  <div style="background:#ecfdf5;border:1px solid #a7f3d0;border-radius:10px;padding:16px">
    <h3 style="font-size:.9rem;font-weight:700;color:#065f46;margin-bottom:10px">🔄 Stage Transitions</h3>
    <p style="margin-bottom:8px">
      <span style="background:#dcfce7;color:#166534;font-weight:700;padding:2px 8px;border-radius:4px;font-size:.8rem">S1 → S2 ↑</span>
      &nbsp;Stock just entered uptrend — high-priority watchlist entry.</p>
    <p>
      <span style="background:#fee2e2;color:#991b1b;font-weight:700;padding:2px 8px;border-radius:4px;font-size:.8rem">S2 → S3 ↓</span>
      &nbsp;Stage 2 stock showing topping signs — consider tightening stops or exiting.</p>
  </div>

</div>"""

    tabs_html = (
        '<div class="tabs">'
        '<button class="tab-btn active" data-tab="t-s2" onclick="showTab(\'t-s2\',this)">Stage 2 Now</button>'
        '<button class="tab-btn" data-tab="t-new" onclick="showTab(\'t-new\',this)">New Entrants (Day)</button>'
        '<button class="tab-btn" data-tab="t-exit" onclick="showTab(\'t-exit\',this)">Exits (Day)</button>'
        '<button class="tab-btn" data-tab="t-all" onclick="showTab(\'t-all\',this)">All Stage Changes (Day)</button>'
        f'<button class="tab-btn" data-tab="t-week" onclick="showTab(\'t-week\',this)">Weekly View ({week})</button>'
        '<button class="tab-btn" data-tab="t-help" onclick="showTab(\'t-help\',this)">📖 How to Read</button>'
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
        f'<div class="tab-panel" id="t-help">{help_tab_content}</div>'
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

  // Hide only data rows — never touch detail rows (they manage their own display)
  Array.from(tbody.querySelectorAll('tr')).forEach(function(r) {
    if (!r.classList.contains('detail-row')) r.style.display = 'none';
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
  if (!row) return;
  var isOpen = row.style.display === 'table-row';
  row.style.display = isOpen ? 'none' : 'table-row';
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

/* ── Pick modal ── */
function showPickModal(idx) {
  var pk = (typeof PICKS_DATA !== 'undefined') ? PICKS_DATA[idx] : null;
  if (!pk) return;
  var stanceColor = pk.stance === 'BULLISH' ? '#166534' : (pk.stance === 'BEARISH' ? '#991b1b' : '#854d0e');
  var stanceBg    = pk.stance === 'BULLISH' ? '#dcfce7' : (pk.stance === 'BEARISH' ? '#fee2e2' : '#fef9c3');
  var invColor    = pk.investment_score >= 65 ? '#16a34a' : (pk.investment_score <= 40 ? '#dc2626' : '#d97706');
  var liveStr     = pk.live_price ? '₹' + pk.live_price.toLocaleString('en-IN', {maximumFractionDigits:2}) : '—';

  function mbar(lbl, val, color) {
    if (val === null || val === undefined || isNaN(val)) {
      return '<div class="mfund-row">'
        + '<span class="mfund-lbl">'+lbl+'</span>'
        + '<span class="mfund-num" style="color:#9ca3af">—</span>'
        + '</div>';
    }
    var w = Math.min(100, Math.max(0, val));
    return '<div class="mfund-row">'
      + '<span class="mfund-lbl">'+lbl+'</span>'
      + '<div class="mfund-track"><div class="mfund-fill" style="width:'+w+'%;background:'+color+'"></div></div>'
      + '<span class="mfund-num">'+val.toFixed(0)+'</span>'
      + '</div>';
  }

  var bars = '<div class="mfund-bars">'
    + mbar('Enhanced Fund Score', pk.enhanced_fund_score, '#7c3aed')
    + mbar('Earnings Quality',    pk.earnings_quality,    '#0891b2')
    + mbar('Sales Growth',        pk.sales_growth,        '#059669')
    + mbar('Financial Strength',  pk.financial_strength,  '#d97706')
    + mbar('Institutional Backing',pk.institutional_backing,'#db2777')
    + mbar('CAN SLIM Score',      pk.can_slim_score,      '#0284c7')
    + mbar('Minervini Score',     pk.minervini_score,     '#7c3aed')
    + '</div>';

  var pnlHtml = pk.pnl_summary
    ? '<div class="mfund-txt"><strong>P&amp;L:</strong> ' + pk.pnl_summary + '</div>' : '';
  var ratHtml = pk.ratios_summary
    ? '<div class="mfund-txt" style="margin-top:6px"><strong>Ratios:</strong> ' + pk.ratios_summary + '</div>' : '';

  var content = '<div class="modal-title">' + pk.symbol + ' &nbsp;<span style="font-size:.85rem;font-weight:400;color:#64748b">' + pk.company + '</span></div>'
    + '<span class="modal-sector">' + pk.sector + '</span>'
    + '<div style="display:flex;align-items:center;gap:14px;margin-bottom:12px">'
    + '<span style="font-size:2.4rem;font-weight:800;color:'+invColor+';line-height:1">' + pk.investment_score.toFixed(0) + '</span>'
    + '<div><div style="font-size:.75rem;color:#64748b">Investment Score / 100</div>'
    + '<span style="font-size:.82rem;font-weight:700;padding:2px 9px;border-radius:4px;background:'+stanceBg+';color:'+stanceColor+'">' + pk.stance + '</span></div>'
    + '<div style="margin-left:auto;text-align:right;font-size:.8rem;color:#64748b">Live price<br><strong style="font-size:1rem;color:#0f172a">' + liveStr + '</strong></div>'
    + '</div>'
    + (pk.narrative ? '<div class="mnarr">' + pk.narrative + '</div>' : '')
    + '<h4 style="font-size:.78rem;font-weight:700;text-transform:uppercase;letter-spacing:.05em;color:#64748b;margin:14px 0 4px">Fundamental Scores</h4>'
    + bars
    + pnlHtml + ratHtml;

  document.getElementById('pick-modal-content').innerHTML = content;
  document.getElementById('pick-modal').classList.add('open');
}
function closePickModal() {
  var m = document.getElementById('pick-modal');
  if (m) m.classList.remove('open');
}
</script>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Stage 2 Tracker – {snap}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist/chart.umd.min.js"></script>
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
  {trend_section}
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
    parser.add_argument("--update-live", action="store_true", help="Update live prices for latest snapshot without re-running screener")
    args = parser.parse_args()

    if args.update_live:
        update_live_prices(snap_date=args.date)
        return

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
