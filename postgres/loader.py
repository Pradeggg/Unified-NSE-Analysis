#!/usr/bin/env python3
"""
postgres/loader.py
==================
Daily incremental loader — called by daily_refresh.py after each EOD run.
Loads today's data from the fresh CSVs/SQLite into PostgreSQL, then runs
all 40 screeners and refreshes all materialized views.

Idempotent: all inserts use ON CONFLICT DO UPDATE so re-runs are safe.
"""

import os
import sys
import json
import glob
import sqlite3
from datetime import date, datetime
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values
import pandas as pd

BASE    = Path(__file__).parent.parent
DATA    = BASE / "data"
GEN_CSV = BASE / "reports" / "generated_csv" / "2026"
REPORTS_DIR = BASE / "reports"
PAGE_SIZE = 500
PG_DSN  = "dbname=nse_market user=nse_admin host=/tmp"
FUNDAMENTAL_SCORE_CSVS = [
    DATA / "fundamental_scores_database.csv",
    BASE / "organized" / "data" / "fundamental_scores_database.csv",
    BASE / "archive" / "repo-cleanup-20260511" / "organized" / "data" / "fundamental_scores_database.csv",
    BASE / "archive" / "fundamental_scores_database.csv",
]
SCREENER_FUND_CACHE = DATA / "_sector_rotation_fund_cache.csv"
WORKING_SECTOR_OUTPUT = BASE / "working-sector" / "output"

TODAY   = str(date.today())


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(BASE))
    except ValueError:
        return str(path)


def pg():
    return psycopg2.connect(PG_DSN)


def safe_float(v):
    try:
        return float(v) if v is not None and str(v).strip() not in ('', 'NA', 'nan', 'NaN', 'None') else None
    except (ValueError, TypeError):
        return None


def safe_int(v):
    try:
        return int(float(v)) if v is not None and str(v).strip() not in ('', 'NA', 'nan', 'NaN', 'None') else None
    except (ValueError, TypeError):
        return None


def safe_numeric_8_4(v):
    try:
        value = float(v)
    except (ValueError, TypeError):
        return None
    if abs(value) >= 10000:
        return None
    return value


def safe_bool(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.strip().upper() in ('TRUE', '1', 'YES', 'T')
    return None


def upsert(cur, table, rows, conflict_cols, update_cols=None):
    if not rows:
        return 0
    cols   = list(rows[0].keys())
    values = [[r.get(c) for c in cols] for r in rows]
    conflict = ", ".join(conflict_cols)
    if update_cols:
        updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_cols)
        sql = (f"INSERT INTO {table} ({', '.join(cols)}) VALUES %s "
               f"ON CONFLICT ({conflict}) DO UPDATE SET {updates}")
    else:
        sql = (f"INSERT INTO {table} ({', '.join(cols)}) VALUES %s "
               f"ON CONFLICT ({conflict}) DO NOTHING")
    execute_values(cur, sql, values, page_size=PAGE_SIZE)
    return len(values)


def benchmark_return_1m(cur, snapshot_date, index_symbol="Nifty 500"):
    """Return benchmark 1M % move for deriving RS when upstream RS is absent."""
    cur.execute(
        """
        WITH latest AS (
            SELECT trade_date, close
            FROM market.index_eod
            WHERE UPPER(index_symbol)=UPPER(%s)
              AND trade_date <= %s
              AND close IS NOT NULL
            ORDER BY trade_date DESC
            LIMIT 1
        ),
        prev AS (
            SELECT close
            FROM market.index_eod
            WHERE UPPER(index_symbol)=UPPER(%s)
              AND trade_date <= (SELECT trade_date FROM latest) - INTERVAL '1 month'
              AND close IS NOT NULL
            ORDER BY trade_date DESC
            LIMIT 1
        )
        SELECT CASE
            WHEN latest.close IS NOT NULL AND prev.close IS NOT NULL AND prev.close <> 0
            THEN (latest.close / prev.close - 1) * 100
        END
        FROM latest, prev
        """,
        (index_symbol, snapshot_date, index_symbol),
    )
    row = cur.fetchone()
    return safe_float(row[0]) if row else None


def update_existing(cur, table, rows, key_cols, update_cols):
    if not rows:
        return 0
    cols = list(dict.fromkeys([*key_cols, *update_cols]))
    values = [[r.get(c) for c in cols] for r in rows]
    join_clause = " AND ".join(f"t.{c} = src.{c}" for c in key_cols)
    set_clause = ", ".join(f"{c} = src.{c}" for c in update_cols)
    sql = (f"UPDATE {table} AS t SET {set_clause} "
           f"FROM (VALUES %s) AS src ({', '.join(cols)}) "
           f"WHERE {join_clause}")
    execute_values(cur, sql, values, page_size=PAGE_SIZE)
    return len(values)


def norm_date(v):
    if not v:
        return None
    if isinstance(v, (datetime, date)):
        return v.strftime("%Y-%m-%d")
    if hasattr(v, "to_pydatetime"):
        return v.to_pydatetime().strftime("%Y-%m-%d")
    s = str(v).strip()
    for fmt in ("%Y-%m-%d", "%d-%b-%Y", "%d %b %Y", "%Y%m%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def clean_text(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v).strip()
    return s or None


def latest_report(pattern: str):
    candidates = [p for p in REPORTS_DIR.rglob(pattern) if p.is_file()]
    if not candidates:
        return None
    return max(candidates, key=lambda p: (p.stat().st_mtime, p.name))


def find_latest_fundamental_details_csv() -> Path | None:
    """Return newest working-sector/output/**/fundamental_details.csv if present."""
    candidates: list[Path] = []
    direct = WORKING_SECTOR_OUTPUT / "fundamental_details.csv"
    if direct.exists():
        candidates.append(direct)
    if WORKING_SECTOR_OUTPUT.exists():
        candidates.extend(p for p in WORKING_SECTOR_OUTPUT.glob("*/fundamental_details.csv") if p.is_file())
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


# ---------------------------------------------------------------------------
# Load latest equity EOD CSV → market.equity_eod
# ---------------------------------------------------------------------------

def equity_eod_csv_paths():
    candidates = [
        DATA / "data" / "nse-raw" / "nse_sec_full_data.csv",
        DATA / "data" / "nse_sec_full_data.csv",
        DATA / "nse-raw" / "nse_sec_full_data.csv",
        DATA / "nse_sec_full_data.csv",
    ]
    seen = set()
    paths = []
    for path in candidates:
        if path in seen or not path.exists():
            continue
        seen.add(path)
        paths.append(path)
    return paths


def _equity_rows_from_csv(csv_path: Path):
    try:
        df = pd.read_csv(csv_path, low_memory=False)
    except Exception as exc:
        print(f"  market.equity_eod: skipped {display_path(csv_path)} ({type(exc).__name__}: {exc})")
        return []
    if df.empty:
        return []

    rows = []
    for _, r in df.iterrows():
        sym = clean_text(r.get("SYMBOL"))
        dt = norm_date(r.get("TIMESTAMP"))
        close = safe_float(r.get("CLOSE"))
        if not sym or not dt or close is None:
            continue
        prev_close = safe_float(r.get("PREVCLOSE"))
        change_abs = (close - prev_close) if prev_close is not None else None
        change_pct = safe_numeric_8_4((close - prev_close) / prev_close * 100) if prev_close not in (None, 0) else None
        rows.append({
            "trade_date": dt,
            "symbol": sym.strip().upper(),
            "series": clean_text(r.get("SERIES")) or "EQ",
            "open": safe_float(r.get("OPEN")),
            "high": safe_float(r.get("HIGH")),
            "low": safe_float(r.get("LOW")),
            "close": close,
            "last_price": safe_float(r.get("LAST")),
            "prev_close": prev_close,
            "change_abs": change_abs,
            "change_pct": change_pct,
            "volume": safe_int(r.get("TOTTRDQTY")),
            "turnover_cr": safe_float(r.get("TOTTRDVAL")),
            "total_trades": safe_int(r.get("TOTALTRADES")),
            "week52_high": safe_float(r.get("HI_52_WK")),
            "week52_low": safe_float(r.get("LO_52_WK")),
        })
    print(f"  market.equity_eod: read {len(rows)} rows from {display_path(csv_path)}")
    return rows


def load_equity_eod(cur):
    csv_paths = equity_eod_csv_paths()
    if not csv_paths:
        print("  market.equity_eod: no nse_sec_full_data.csv files found")
        return 0

    rows = []
    for csv_path in csv_paths:
        rows.extend(_equity_rows_from_csv(csv_path))

    deduped = {}
    for row in rows:
        deduped[(row["trade_date"], row["symbol"], row["series"])] = row
    rows = sorted(deduped.values(), key=lambda r: (r["trade_date"], r["symbol"], r["series"]))

    n = upsert(cur, "market.equity_eod", rows,
               ["trade_date", "symbol", "series"],
               ["open", "high", "low", "close", "last_price", "prev_close",
                "change_abs", "change_pct", "volume", "turnover_cr",
                "total_trades", "week52_high", "week52_low"])
    dates = sorted({r["trade_date"] for r in rows})
    suffix = f" ({dates[0]} → {dates[-1]})" if dates else ""
    print(f"  market.equity_eod: {n} rows upserted{suffix}")
    return n


# ---------------------------------------------------------------------------
# Load latest/all available NSE index EOD CSV → market.index_eod
# ---------------------------------------------------------------------------

def load_index_eod(cur):
    csv_path = DATA / "nse_index_data.csv"
    if not csv_path.exists():
        print("  market.index_eod: data/nse_index_data.csv not found")
        return 0

    df = pd.read_csv(csv_path, low_memory=False)
    if df.empty:
        print("  market.index_eod: data/nse_index_data.csv empty")
        return 0

    rows = []
    for _, r in df.iterrows():
        idx = clean_text(r.get("SYMBOL"))
        dt = norm_date(r.get("TIMESTAMP"))
        close = safe_float(r.get("CLOSE"))
        if not idx or not dt or close is None:
            continue
        turnover = safe_float(r.get("TOTTRDVAL"))
        prev_close = safe_float(r.get("PREVCLOSE"))
        change_pct = ((close - prev_close) / prev_close * 100) if prev_close not in (None, 0) else safe_float(r.get("CHANGE_PCT"))
        rows.append({
            "trade_date": dt,
            "index_symbol": idx.strip(),
            "open": safe_float(r.get("OPEN")),
            "high": safe_float(r.get("HIGH")),
            "low": safe_float(r.get("LOW")),
            "close": close,
            "prev_close": prev_close,
            "change_pct": change_pct,
            "volume": safe_int(r.get("TOTTRDQTY")),
            "turnover_cr": round(turnover / 1e7, 4) if turnover is not None else None,
            "total_trades": safe_int(r.get("TOTALTRADES")),
            "week52_high": safe_float(r.get("HI_52_WK")),
            "week52_low": safe_float(r.get("LO_52_WK")),
        })

    n = upsert(
        cur,
        "market.index_eod",
        rows,
        ["trade_date", "index_symbol"],
        ["open", "high", "low", "close", "prev_close", "change_pct", "volume",
         "turnover_cr", "total_trades", "week52_high", "week52_low"],
    )
    dates = sorted({r["trade_date"] for r in rows})
    suffix = f" ({dates[0]} → {dates[-1]})" if dates else ""
    print(f"  market.index_eod: {n} rows upserted from nse_index_data.csv{suffix}")
    return n


# ---------------------------------------------------------------------------
# Keep ref.instruments current from latest enrichment sources
# ---------------------------------------------------------------------------


def load_ref_instruments(cur):
    total = 0

    latest = latest_report("comprehensive_nse_enhanced_*.csv")
    if latest:
        df = pd.read_csv(latest, low_memory=False)
        rows = []
        for _, r in df.iterrows():
            sym = clean_text(r.get("SYMBOL"))
            if not sym:
                continue
            rows.append({
                "symbol": sym,
                "company_name": clean_text(r.get("COMPANY_NAME")) or sym,
                "market_cap_cat": clean_text(r.get("MARKET_CAP_CATEGORY")),
                "sector": clean_text(r.get("SECTOR")),
            })
        if rows:
            total += update_existing(cur, "ref.instruments", rows, ["symbol"], ["company_name", "market_cap_cat", "sector"])
        print(f"  ref.instruments: {len(rows)} rows updated from {latest.name}")

    db = DATA / "sector_rotation_tracker.db"
    if not db.exists():
        return total

    conn = sqlite3.connect(db)
    df = pd.read_sql("SELECT symbol, sector, snapshot_date FROM stage_snapshots", conn)
    conn.close()
    if df.empty:
        return total

    df["symbol"] = df["symbol"].map(clean_text)
    df["sector"] = df["sector"].map(clean_text)
    df = df[df["symbol"].notna() & df["sector"].notna()].copy()
    if df.empty:
        return total
    df["snapshot_date"] = pd.to_datetime(df["snapshot_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    df["_rownum"] = range(len(df))
    df = df.sort_values(["snapshot_date", "_rownum"], na_position="first")
    df = df.groupby("symbol", as_index=False, sort=False).tail(1)
    values = [(r["symbol"], r["sector"]) for _, r in df.iterrows()]
    sql = """
        UPDATE ref.instruments AS i
           SET sector = v.sector
          FROM (VALUES %s) AS v(symbol, sector)
         WHERE i.symbol = v.symbol
           AND v.sector IS NOT NULL
           AND (i.sector IS NULL OR i.sector = '')
    """
    execute_values(cur, sql, values, template="(%s, %s)", page_size=PAGE_SIZE)
    print(f"  ref.instruments: {len(values)} sector backfill rows from stage_snapshots")
    return total + len(values)


# ---------------------------------------------------------------------------
# Load today's stage_snapshots from SQLite → PostgreSQL
# ---------------------------------------------------------------------------

def load_stage_snapshots(cur):
    db = DATA / "sector_rotation_tracker.db"
    if not db.exists():
        return 0
    conn = sqlite3.connect(db)
    df = pd.read_sql(
        "SELECT * FROM stage_snapshots WHERE snapshot_date = ?",
        conn, params=[TODAY]
    )
    conn.close()
    if df.empty:
        # Fall back to latest date
        conn = sqlite3.connect(db)
        df = pd.read_sql(
            "SELECT * FROM stage_snapshots WHERE snapshot_date = "
            "(SELECT MAX(snapshot_date) FROM stage_snapshots)",
            conn
        )
        conn.close()

    snapshot_date = norm_date(df["snapshot_date"].iloc[0]) if not df.empty else TODAY
    bench_1m = benchmark_return_1m(cur, snapshot_date)
    rows = []
    for _, r in df.iterrows():
        sym = str(r.get("symbol", "")).strip()
        dt  = norm_date(r.get("snapshot_date"))
        if not sym or not dt:
            continue
        change_1m = safe_float(r.get("change_1m_pct"))
        relative_strength = safe_float(r.get("relative_strength"))
        if relative_strength is None and change_1m is not None and bench_1m is not None:
            relative_strength = round(change_1m - bench_1m, 4)
        fd = r.get("fund_details")
        if fd and isinstance(fd, str) and fd.strip():
            try:
                fd = json.loads(fd)
            except Exception:
                fd = None
        else:
            fd = None
        rows.append({
            "snapshot_date":      dt,
            "symbol":             sym,
            "company_name":       str(r.get("company_name", sym)).strip(),
            "sector":             str(r.get("sector", "")).strip() or None,
            "market_cap_cat":     str(r.get("market_cap_cat", "")).strip() or None,
            "price":              safe_float(r.get("price")),
            "live_price":         safe_float(r.get("live_price")),
            "price_date":         norm_date(r.get("price_date")),
            "change_1d_pct":      safe_float(r.get("change_1d_pct")),
            "change_1w_pct":      safe_float(r.get("change_1w_pct")),
            "change_1m_pct":      change_1m,
            "stage":              str(r.get("stage", "")).strip() or None,
            "stage_score":        safe_float(r.get("stage_score")),
            "technical_score":    safe_float(r.get("technical_score")),
            "rsi":                safe_float(r.get("rsi")),
            "trend_signal":       str(r.get("trend_signal", "")).strip() or None,
            "trading_signal":     str(r.get("trading_signal", "")).strip() or None,
            "relative_strength":  relative_strength,
            "supertrend_state":   str(r.get("supertrend_state", "")).strip() or None,
            "supertrend_value":   safe_float(r.get("supertrend_value")),
            "can_slim_score":     safe_float(r.get("can_slim_score")),
            "minervini_score":    safe_float(r.get("minervini_score")),
            "fundamental_score":  safe_float(r.get("fundamental_score")),
            "enhanced_fund_score":safe_float(r.get("enhanced_fund_score")),
            "earnings_quality":   safe_float(r.get("earnings_quality")),
            "sales_growth":       safe_float(r.get("sales_growth")),
            "financial_strength": safe_float(r.get("financial_strength")),
            "institutional_backing": safe_float(r.get("institutional_backing")),
            "investment_score":   safe_float(r.get("investment_score")),
            "stance":             str(r.get("stance", "")).strip() or None,
            "narrative":          str(r.get("narrative", "")).strip() or None,
            "fund_details":       json.dumps(fd) if fd else None,
            "source_csv":         str(r.get("source_csv", "")).strip() or None,
        })
    if not rows:
        return 0
    n = upsert(cur, "scores.stage_snapshots", rows,
               ["snapshot_date", "symbol"],
               [c for c in rows[0].keys() if c not in {"snapshot_date", "symbol"}])
    print(f"  scores.stage_snapshots: {n} rows upserted for {dt}")
    return n


def load_stage_changes(cur):
    db = DATA / "sector_rotation_tracker.db"
    if not db.exists():
        return 0
    conn = sqlite3.connect(db)
    df = pd.read_sql("SELECT * FROM stage_changes", conn)
    conn.close()
    if df.empty:
        return 0

    rows = []
    for _, r in df.iterrows():
        change_date = norm_date(r.get("change_date"))
        compare_date = norm_date(r.get("compare_date"))
        sym = str(r.get("symbol", "")).strip().upper()
        if not change_date or not compare_date or not sym:
            continue
        rows.append({
            "change_date":      change_date,
            "compare_date":     compare_date,
            "symbol":           sym,
            "company_name":     str(r.get("company_name", sym)).strip() or None,
            "stage_now":        str(r.get("stage_now", "")).strip() or None,
            "stage_prev":       str(r.get("stage_prev", "")).strip() or None,
            "stage_changed":    safe_bool(r.get("stage_changed")),
            "change_type":      str(r.get("change_type", "")).strip() or None,
            "price_now":        safe_float(r.get("price_now")),
            "price_prev":       safe_float(r.get("price_prev")),
            "price_chg_pct":    safe_float(r.get("price_chg_pct")),
            "live_price":       safe_float(r.get("live_price")),
            "live_vs_prev_pct": safe_float(r.get("live_vs_prev_pct")),
            "stage_score_now":  safe_float(r.get("stage_score_now")),
            "stage_score_prev": safe_float(r.get("stage_score_prev")),
            "trading_signal":   str(r.get("trading_signal", "")).strip() or None,
        })

    n = upsert(cur, "scores.stage_changes", rows,
               ["change_date", "compare_date", "symbol"],
               ["company_name", "stage_now", "stage_prev", "stage_changed",
                "change_type", "price_now", "price_prev", "price_chg_pct",
                "live_price", "live_vs_prev_pct", "stage_score_now",
                "stage_score_prev", "trading_signal"])
    print(f"  scores.stage_changes: {n} rows upserted")
    return n


# ---------------------------------------------------------------------------
# Load Screener.in fundamental details → scores.fundamental_snapshots + latest cache
# ---------------------------------------------------------------------------

def load_screener_fundamentals(cur, snapshot_date=None):
    sources: list[tuple[Path, pd.DataFrame]] = []
    if SCREENER_FUND_CACHE.exists():
        df_cache = pd.read_csv(SCREENER_FUND_CACHE, low_memory=False)
        if not df_cache.empty:
            sources.append((SCREENER_FUND_CACHE, df_cache))

    details_csv = find_latest_fundamental_details_csv()
    if details_csv and details_csv.exists():
        df_details = pd.read_csv(details_csv, low_memory=False)
        if not df_details.empty:
            sources.append((details_csv, df_details))

    if not sources:
        print("  scores.fundamental_snapshots: no Screener fundamental source CSV found")
        return 0

    snap_date = norm_date(snapshot_date) or TODAY
    rows = []
    for source_path, df in sources:
        for _, r in df.iterrows():
            sym = clean_text(r.get("SYMBOL")) or clean_text(r.get("symbol"))
            if not sym:
                continue
            row = {
                "snapshot_date": snap_date,
                "symbol": sym.strip().upper(),
                "pnl_summary": clean_text(r.get("pnl_summary")),
                "quarterly_summary": clean_text(r.get("quarterly_summary")),
                "balance_sheet_summary": clean_text(r.get("balance_sheet_summary")),
                "cash_flow_summary": clean_text(r.get("cash_flow_summary")),
                "investor_summary": clean_text(r.get("investor_summary")),
                "ratios_summary": clean_text(r.get("ratios_summary")),
                "source_file": str(source_path.relative_to(BASE)) if source_path.is_relative_to(BASE) else str(source_path),
            }
            if any(
                row.get(c)
                for c in [
                    "pnl_summary",
                    "quarterly_summary",
                    "balance_sheet_summary",
                    "cash_flow_summary",
                    "investor_summary",
                    "ratios_summary",
                ]
            ):
                rows.append(row)

    if not rows:
        return 0

    # Changed: multiple source files can emit the same (snapshot_date, symbol).
    # Keep the last-seen row (details CSV takes precedence because it is loaded after cache).
    deduped = {}
    for row in rows:
        deduped[(row["snapshot_date"], row["symbol"])] = row
    rows = list(deduped.values())

    n = upsert(cur, "scores.fundamental_snapshots", rows,
               ["snapshot_date", "symbol"],
               ["pnl_summary", "quarterly_summary", "balance_sheet_summary",
                "cash_flow_summary", "investor_summary", "ratios_summary",
                "source_file", "loaded_at"])

    latest_rows = [
        {
            "symbol": r["symbol"],
            "pnl_summary": r["pnl_summary"],
            "quarterly_summary": r["quarterly_summary"],
            "balance_sheet_summary": r["balance_sheet_summary"],
            "cash_flow_summary": r["cash_flow_summary"],
            "investor_summary": r["investor_summary"],
            "ratios_summary": r["ratios_summary"],
            "updated_at": datetime.now(),
        }
        for r in rows
    ]
    upsert(cur, "scores.fundamentals", latest_rows,
           ["symbol"],
           ["pnl_summary", "quarterly_summary", "balance_sheet_summary",
            "cash_flow_summary", "investor_summary", "ratios_summary", "updated_at"])

    # Changed: maintain section-wise snapshots for granular auditability.
    cur.execute("SELECT to_regclass('scores.fundamental_section_snapshots')")
    if cur.fetchone()[0] is not None:
        section_rows = []
        section_map = {
            "pnl": "pnl_summary",
            "quarterly": "quarterly_summary",
            "balance_sheet": "balance_sheet_summary",
            "cash_flow": "cash_flow_summary",
            "investor": "investor_summary",
            "ratios": "ratios_summary",
        }
        for r in rows:
            for section_name, col in section_map.items():
                value = r.get(col)
                if not value:
                    continue
                section_rows.append({
                    "snapshot_date": r["snapshot_date"],
                    "symbol": r["symbol"],
                    "section_name": section_name,
                    "section_summary": value,
                    "source_file": r.get("source_file"),
                    "loaded_at": datetime.now(),
                })
        if section_rows:
            upsert(
                cur,
                "scores.fundamental_section_snapshots",
                section_rows,
                ["snapshot_date", "symbol", "section_name"],
                ["section_summary", "source_file", "loaded_at"],
            )
    print(f"  scores.fundamental_snapshots: {n} rows for {snap_date}")
    return n


# ---------------------------------------------------------------------------
# Load fundamental score components → scores.fundamental_scores
# ---------------------------------------------------------------------------

def load_fundamental_scores(cur):
    path = next((p for p in FUNDAMENTAL_SCORE_CSVS if p.exists()), None)
    if path is None:
        print("  scores.fundamental_scores: no fundamental_scores_database.csv found")
        return 0

    df = pd.read_csv(path, low_memory=False)
    if df.empty:
        return 0

    processed_dates = [norm_date(v) for v in df.get("processed_date", pd.Series(dtype=object)).dropna().tolist()]
    score_date_default = max([d for d in processed_dates if d], default=TODAY)

    rows = []
    for _, r in df.iterrows():
        sym = str(r.get("symbol", "")).strip().upper()
        if not sym:
            continue
        processed_date = norm_date(r.get("processed_date"))
        rows.append({
            "score_date": processed_date or score_date_default,
            "symbol": sym,
            "enhanced_fund_score": safe_float(r.get("ENHANCED_FUND_SCORE")),
            "earnings_quality": safe_float(r.get("EARNINGS_QUALITY")),
            "sales_growth": safe_float(r.get("SALES_GROWTH")),
            "financial_strength": safe_float(r.get("FINANCIAL_STRENGTH")),
            "institutional_backing": safe_float(r.get("INSTITUTIONAL_BACKING")),
            "processed_date": processed_date,
            "processing_batch": clean_text(r.get("processing_batch")),
            "batch_number": safe_int(r.get("batch_number")),
            "source_file": str(path.relative_to(BASE)) if path.is_relative_to(BASE) else str(path),
        })

    n = upsert(cur, "scores.fundamental_scores", rows,
               ["score_date", "symbol"],
               ["enhanced_fund_score", "earnings_quality", "sales_growth",
                "financial_strength", "institutional_backing", "processed_date",
                "processing_batch", "batch_number", "source_file", "loaded_at"])
    print(f"  scores.fundamental_scores: {n} rows from {path.name}")
    return n


# ---------------------------------------------------------------------------
# Optional legacy CSV import → scores.daily_scores
# ---------------------------------------------------------------------------

def load_daily_scores(cur):
    csvs = sorted(GEN_CSV.glob("comprehensive_nse_enhanced_*.csv"))
    if not csvs:
        return 0
    latest = csvs[-1]
    df = pd.read_csv(latest, low_memory=False)
    if df.empty:
        return 0

    # Determine score_date
    if "ANALYSIS_DATE" in df.columns:
        score_date = norm_date(df["ANALYSIS_DATE"].dropna().iloc[0]) if len(df) else TODAY
    else:
        score_date = TODAY

    rows = []
    for _, r in df.iterrows():
        sym = str(r.get("SYMBOL", "")).strip()
        if not sym:
            continue
        rows.append({
            "score_date":          score_date,
            "symbol":              sym,
            "company_name":        str(r.get("COMPANY_NAME", sym)).strip(),
            "market_cap_cat":      str(r.get("MARKET_CAP_CATEGORY", "")).strip() or None,
            "current_price":       safe_float(r.get("CURRENT_PRICE")),
            "change_1d_pct":       safe_float(r.get("CHANGE_1D")),
            "change_1w_pct":       safe_float(r.get("CHANGE_1W")),
            "change_1m_pct":       safe_float(r.get("CHANGE_1M")),
            "trading_value":       safe_float(r.get("TRADING_VALUE")),
            "technical_score":     safe_float(r.get("TECHNICAL_SCORE")),
            "rsi":                 safe_float(r.get("RSI")),
            "relative_strength":   safe_float(r.get("RELATIVE_STRENGTH")),
            "trend_signal":        str(r.get("TREND_SIGNAL", "")).strip() or None,
            "trading_signal":      str(r.get("TRADING_SIGNAL", "")).strip() or None,
            "can_slim_score":      safe_float(r.get("CAN_SLIM_SCORE")),
            "minervini_score":     safe_float(r.get("MINERVINI_SCORE")),
            "fundamental_score":   safe_float(r.get("FUNDAMENTAL_SCORE")),
            "enhanced_fund_score": safe_float(r.get("ENHANCED_FUND_SCORE")),
            "earnings_quality":    safe_float(r.get("EARNINGS_QUALITY")),
            "sales_growth":        safe_float(r.get("SALES_GROWTH")),
            "financial_strength":  safe_float(r.get("FINANCIAL_STRENGTH")),
            "institutional_backing": safe_float(r.get("INSTITUTIONAL_BACKING")),
        })
    cur.execute("DELETE FROM scores.daily_scores WHERE score_date = %s", (score_date,))
    n = upsert(cur, "scores.daily_scores", rows,
               ["score_date", "symbol"],
               ["current_price", "change_1d_pct", "technical_score",
                "rsi", "trading_signal", "enhanced_fund_score"])
    print(f"  scores.daily_scores: {n} rows for {score_date} ({latest.name})")
    return n


# ---------------------------------------------------------------------------
# Load today's FII/DII flows
# ---------------------------------------------------------------------------

def load_fii_dii(cur):
    fii = DATA / "fii_dii_flows.csv"
    if not fii.exists():
        return 0
    df = pd.read_csv(fii, low_memory=False)
    # Get today's or latest row
    rows = []
    for _, r in df.iterrows():
        dt = norm_date(r.get("date"))
        if not dt:
            continue
        rows.append({
            "trade_date":    dt,
            "fii_net_today": safe_float(r.get("fii_net_today")),
            "dii_net_today": safe_float(r.get("dii_net_today")),
            "fii_net_5d":    safe_float(r.get("fii_net_5d")),
            "dii_net_5d":    safe_float(r.get("dii_net_5d")),
            "flow_signal":   str(r.get("flow_signal", "")).strip() or None,
            "fii_trend":     str(r.get("fii_trend", "")).strip() or None,
            "dii_trend":     str(r.get("dii_trend", "")).strip() or None,
            "days_in_window":safe_int(r.get("days_in_window")),
        })
    if rows:
        n = upsert(cur, "signals.fii_dii_flows", rows, ["trade_date"],
                   ["fii_net_today", "dii_net_today", "fii_net_5d",
                    "dii_net_5d", "flow_signal", "fii_trend"])
        print(f"  signals.fii_dii_flows: {n} rows")
    return len(rows)


# ---------------------------------------------------------------------------
# Load today's breadth
# ---------------------------------------------------------------------------

def load_breadth(cur):
    bh = DATA / "breadth_history.csv"
    if not bh.exists():
        return 0
    df = pd.read_csv(bh, low_memory=False)
    rows = []
    for _, r in df.iterrows():
        dt = norm_date(r.get("date"))
        if not dt:
            continue
        rows.append({
            "trade_date":     dt,
            "advances":       safe_int(r.get("advances")),
            "declines":       safe_int(r.get("declines")),
            "net_ad":         safe_int(r.get("net_ad")),
            "ad_oscillator":  safe_float(r.get("oscillator")),
            "ad_summation":   safe_float(r.get("summation")),
            "ad_signal":      str(r.get("signal", "")).strip() or None,
            "adv_volume":     safe_int(r.get("adv_volume")),
            "dec_volume":     safe_int(r.get("dec_volume")),
            "trin":           safe_float(r.get("trin")),
            "trin_5d":        safe_float(r.get("trin_5d")),
            "trin_signal":    str(r.get("trin_signal", "")).strip() or None,
            "trin_5d_signal": str(r.get("trin_5d_signal", "")).strip() or None,
            "divergence":     str(r.get("divergence", "")).strip() or None,
            "nifty500_close": safe_float(r.get("nifty500_close")),
        })
    n = upsert(cur, "breadth.market_daily", rows, ["trade_date"],
               ["advances", "declines", "net_ad", "ad_oscillator", "trin"])
    print(f"  breadth.market_daily: {n} rows")
    return n


# ---------------------------------------------------------------------------
# Load cached FNO bhavcopy history from _fno_cache
# ---------------------------------------------------------------------------

def fno_cache_csv_paths():
    cache = DATA / "_fno_cache"
    if not cache.exists():
        return []
    return sorted(
        path for path in cache.glob("fo_bhav_*.csv")
        if "test" not in path.name.lower()
    )


def _fno_rows_from_csv(csv_path: Path):
    try:
        df = pd.read_csv(csv_path, low_memory=False)
    except Exception as exc:
        print(f"  derivatives.fno_eod: skipped {display_path(csv_path)} ({type(exc).__name__}: {exc})")
        return []
    if df.empty or "TradDt" not in df.columns:
        return []

    rows = []
    for _, r in df.iterrows():
        sym = clean_text(r.get("SYMBOL"))
        dt = norm_date(r.get("TradDt"))
        exp = norm_date(r.get("EXPIRY_DATE"))
        instrument = clean_text(r.get("INSTRUMENT"))
        if not sym or not dt or not exp or not instrument:
            continue
        raw_option_type = clean_text(r.get("OPTION_TYPE"))
        option_type = "FUT" if not raw_option_type or raw_option_type.lower() in ("nan", "none", "na", "null") else raw_option_type
        turnover = safe_float(r.get("TtlTrfVal"))
        rows.append({
            "trade_date":       dt,
            "symbol":           sym.strip().upper(),
            "expiry_date":      exp,
            "instrument":       instrument.strip(),
            "option_type":      option_type.strip().upper(),
            "strike":           safe_float(r.get("STRIKE_PRICE")) or 0.0,
            "open":             safe_float(r.get("OpnPric")),
            "high":             safe_float(r.get("HghPric")),
            "low":              safe_float(r.get("LwPric")),
            "close":            safe_float(r.get("CLOSE")),
            "last_price":       safe_float(r.get("LastPric")),
            "prev_close":       safe_float(r.get("PREV_CLOSE")),
            "underlying_price": safe_float(r.get("UndrlygPric")),
            "settle_price":     safe_float(r.get("SETTLE_PRICE")),
            "open_interest":    safe_int(r.get("OPEN_INTEREST")),
            "oi_change":        safe_int(r.get("CHANGE_IN_OI")),
            "volume":           safe_int(r.get("VOLUME")),
            "turnover_cr":      round(turnover / 1e7, 4) if turnover is not None else None,
            "total_trades":     safe_int(r.get("TtlNbOfTxsExctd")),
            "lot_size":         safe_int(r.get("NewBrdLotQty")),
        })
    print(f"  derivatives.fno_eod: read {len(rows)} rows from {display_path(csv_path)}")
    return rows


def load_fno_today(cur):
    files = fno_cache_csv_paths()
    if not files:
        print("  derivatives.fno_eod: no fo_bhav_*.csv files found")
        return 0

    rows = []
    for csv_path in files:
        rows.extend(_fno_rows_from_csv(csv_path))
    if not rows:
        return 0

    deduped = {}
    for row in rows:
        deduped[
            (
                row["trade_date"],
                row["symbol"],
                row["expiry_date"],
                row["instrument"],
                row["option_type"],
                row["strike"],
            )
        ] = row
    rows = sorted(
        deduped.values(),
        key=lambda r: (r["trade_date"], r["symbol"], r["expiry_date"], r["instrument"], r["option_type"], r["strike"]),
    )

    trade_dates = sorted({row["trade_date"] for row in rows if row.get("trade_date")})
    for trade_date in trade_dates:
        cur.execute("SELECT derivatives.ensure_fno_monthly_partition(%s)", (trade_date,))
    cols   = list(rows[0].keys())
    values = [[r.get(c) for c in cols] for r in rows]
    sql = (f"INSERT INTO derivatives.fno_eod ({', '.join(cols)}) VALUES %s "
           f"ON CONFLICT ON CONSTRAINT fno_eod_pkey DO UPDATE SET "
           f"open=EXCLUDED.open, high=EXCLUDED.high, low=EXCLUDED.low, "
           f"close=EXCLUDED.close, last_price=EXCLUDED.last_price, "
           f"prev_close=EXCLUDED.prev_close, underlying_price=EXCLUDED.underlying_price, "
           f"settle_price=EXCLUDED.settle_price, open_interest=EXCLUDED.open_interest, "
           f"oi_change=EXCLUDED.oi_change, volume=EXCLUDED.volume, "
           f"turnover_cr=EXCLUDED.turnover_cr, total_trades=EXCLUDED.total_trades, "
           f"lot_size=EXCLUDED.lot_size")
    execute_values(cur, sql, values, page_size=PAGE_SIZE)
    suffix = f" ({trade_dates[0]} → {trade_dates[-1]})" if trade_dates else ""
    print(f"  derivatives.fno_eod: {len(values)} rows upserted from {len(files)} cached files{suffix}")
    return len(values)


# ---------------------------------------------------------------------------
# Load today's bulk/block deals
# ---------------------------------------------------------------------------

def load_deals_today(cur):
    cache = DATA / "_insider_cache"
    if not cache.exists():
        return 0
    total = 0
    for f in sorted(cache.glob("*.csv")):
        deal_type = "BULK_DEAL" if "bulk" in f.name else "BLOCK_DEAL"
        df = pd.read_csv(f, low_memory=False)
        rows = []
        for _, r in df.iterrows():
            sym = str(r.get("SYMBOL", "")).strip()
            dt  = norm_date(r.get("DATE"))
            if not sym or not dt:
                continue
            rows.append({
                "deal_date":     dt,
                "symbol":        sym,
                "security_name": str(r.get("Security Name", "")).strip() or None,
                "entity":        str(r.get("ENTITY", "")).strip() or None,
                "side":          str(r.get("SIDE", "")).strip() or None,
                "qty":           safe_int(r.get("QTY")),
                "price":         safe_float(r.get("PRICE")),
                "deal_type":     deal_type,
                "remarks":       str(r.get("Remarks", "")).strip() or None,
                "source":        deal_type,
            })
        if rows:
            upsert(cur, "signals.bulk_block_deals", rows,
                   ["deal_date", "symbol", "entity", "side", "deal_type"])
            total += len(rows)
    if total:
        print(f"  signals.bulk_block_deals: {total} rows")
    return total


# ---------------------------------------------------------------------------
# Load MA breadth snapshot + compute aggregated pct
# ---------------------------------------------------------------------------

def load_sector_top_stocks(cur, snapshot_date: str = None) -> int:
    """Rebuild scores.sector_top_stocks for ``snapshot_date`` directly from
    scores.stage_snapshots — replaces the deprecated R-script CSV pipeline.

    For each sector, rank stocks by technical_score DESC, keep the top 5,
    compute sector_strength = mean(top5.technical_score), total_stocks =
    count of sector members on that date.
    """
    snapshot_date = snapshot_date or TODAY
    cur.execute(
        """
        WITH src AS (
            SELECT s.*, d.trading_value
              FROM scores.stage_snapshots s
              LEFT JOIN scores.daily_scores d
                     ON d.score_date = s.snapshot_date
                    AND d.symbol     = s.symbol
             WHERE s.snapshot_date = %s
               AND s.sector IS NOT NULL
               AND s.technical_score IS NOT NULL
        ),
        ranked AS (
            SELECT s.*,
                   ROW_NUMBER() OVER (PARTITION BY sector
                                      ORDER BY technical_score DESC NULLS LAST,
                                               trading_value     DESC NULLS LAST) AS rnk,
                   COUNT(*)     OVER (PARTITION BY sector)                        AS total_stocks
              FROM src s
        ),
        top5 AS (
            SELECT * FROM ranked WHERE rnk <= 5
        ),
        strength AS (
            SELECT sector,
                   AVG(technical_score)::numeric(6,2) AS sector_strength,
                   MAX(total_stocks)                  AS total_stocks
              FROM top5
             GROUP BY sector
        )
        INSERT INTO scores.sector_top_stocks (
            score_date, sector_name, sector_strength, total_stocks,
            rank, symbol, company_name, market_cap_cat,
            current_price, change_1d_pct, change_1w_pct, change_1m_pct,
            technical_score, rsi, relative_strength,
            can_slim_score, minervini_score, enhanced_fund_score,
            trend_signal, trading_signal, trading_value
        )
        SELECT t.snapshot_date, t.sector, s.sector_strength, s.total_stocks,
               t.rnk, t.symbol, t.company_name, t.market_cap_cat,
               t.price, t.change_1d_pct, t.change_1w_pct, t.change_1m_pct,
               t.technical_score, t.rsi, t.relative_strength,
               t.can_slim_score, t.minervini_score, t.enhanced_fund_score,
               t.trend_signal, t.trading_signal, t.trading_value
          FROM top5 t JOIN strength s USING (sector)
        ON CONFLICT (score_date, sector_name, symbol) DO UPDATE SET
               sector_strength    = EXCLUDED.sector_strength,
               total_stocks       = EXCLUDED.total_stocks,
               rank               = EXCLUDED.rank,
               company_name       = EXCLUDED.company_name,
               market_cap_cat     = EXCLUDED.market_cap_cat,
               current_price      = EXCLUDED.current_price,
               change_1d_pct      = EXCLUDED.change_1d_pct,
               change_1w_pct      = EXCLUDED.change_1w_pct,
               change_1m_pct      = EXCLUDED.change_1m_pct,
               technical_score    = EXCLUDED.technical_score,
               rsi                = EXCLUDED.rsi,
               relative_strength  = EXCLUDED.relative_strength,
               can_slim_score     = EXCLUDED.can_slim_score,
               minervini_score    = EXCLUDED.minervini_score,
               enhanced_fund_score= EXCLUDED.enhanced_fund_score,
               trend_signal       = EXCLUDED.trend_signal,
               trading_signal     = EXCLUDED.trading_signal,
               trading_value      = EXCLUDED.trading_value
        """,
        (snapshot_date,),
    )
    n = cur.rowcount
    print(f"  scores.sector_top_stocks: {n} rows for {snapshot_date}")
    return n


def load_global_index_levels(cur):
    """Load data/global_indices.csv (wide format: Date,S&P 500,Nasdaq,…) into
    market.global_index_levels. Each row of the CSV is exploded into one row
    per index_name, skipping NA values."""
    gi = DATA / "global_indices.csv"
    if not gi.exists():
        return 0
    df = pd.read_csv(gi, low_memory=False)
    rows = []
    for _, r in df.iterrows():
        dt = norm_date(r.get("Date"))
        if not dt:
            continue
        for col in df.columns:
            if col == "Date":
                continue
            v = safe_float(r.get(col))
            if v is None:
                continue
            rows.append({"trade_date": dt, "index_name": col, "close": v})
    if not rows:
        return 0
    n = upsert(cur, "market.global_index_levels", rows,
               ["trade_date", "index_name"], ["close"])
    print(f"  market.global_index_levels: {n} rows")
    return n


def load_ma_breadth(cur):
    csvs = sorted((BASE / "reports" / "generated_csv" / "2026").glob("NIFTY500_Market_Breadth_*.csv"))
    if not csvs:
        return 0
    latest = csvs[-1]
    import re
    m = re.search(r"Breadth_(\d{8})", latest.name)
    if not m:
        return 0
    snap_date = datetime.strptime(m.group(1), "%Y%m%d").strftime("%Y-%m-%d")

    df = pd.read_csv(latest, low_memory=False)
    rows = []
    for _, r in df.iterrows():
        sym = str(r.get("SYMBOL", "")).strip()
        if not sym:
            continue
        rows.append({
            "snapshot_date": snap_date,
            "symbol":        sym,
            "current_price": safe_float(r.get("CURRENT_PRICE")),
            "sma_20":        safe_float(r.get("SMA_20")),
            "sma_50":        safe_float(r.get("SMA_50")),
            "sma_100":       safe_float(r.get("SMA_100")),
            "sma_200":       safe_float(r.get("SMA_200")),
            "above_20dma":   safe_bool(r.get("ABOVE_20DMA")),
            "above_50dma":   safe_bool(r.get("ABOVE_50DMA")),
            "above_100dma":  safe_bool(r.get("ABOVE_100DMA")),
            "above_200dma":  safe_bool(r.get("ABOVE_200DMA")),
        })
    n = upsert(cur, "scores.ma_breadth", rows, ["snapshot_date", "symbol"])
    cur.execute("SELECT breadth.compute_ma_pct(%s)", (snap_date,))
    print(f"  scores.ma_breadth: {n} rows for {snap_date}")
    return n


# ---------------------------------------------------------------------------
# Run screener for today's snapshot
# ---------------------------------------------------------------------------

def run_screeners(cur, run_date: str):
    print(f"\n  Running 40 screeners for {run_date}…")
    cur.execute("SELECT screen_id, stocks_found FROM screener.run_all_screens(%s)", (run_date,))
    results = cur.fetchall()
    total = sum(r[1] for r in results if r[0] != "__SUMMARY__")
    stocks = next((r[1] for r in results if r[0] == "__SUMMARY__"), 0)
    print(f"  ✓ Screeners: {len(results)-1} screens ran | {total} total hits | {stocks} unique stocks")
    return results


def run_fno_analytics(cur):
    print("\n  Running F&O analytics…")
    cur.execute("SELECT derivatives.refresh_fno_analytics()")
    rows = cur.fetchone()[0]
    print(f"  ✓ F&O analytics refreshed | {rows} symbol signals")
    return rows


# ---------------------------------------------------------------------------
# Refresh all materialized views
# ---------------------------------------------------------------------------

def refresh_views(cur):
    print("\n  Refreshing materialized views…")
    cur.execute("SELECT refresh_all_views()")
    cur.execute("SELECT screener.refresh_views()")
    print("  ✓ All views refreshed")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=TODAY, help="Run date (default: today)")
    ap.add_argument("--skip-fno", action="store_true", help="Skip FNO load")
    ap.add_argument("--eod-only", action="store_true",
                    help="Only load data/nse_sec_full_data.csv into market.equity_eod")
    ap.add_argument("--fno-only", action="store_true",
                    help="Only load cached F&O EOD bhavcopy files into derivatives.fno_eod and refresh F&O analytics")
    # PG-FUND-ORDER 2026-05-26: refresh fundamentals BEFORE the sector rotation
    # tracker snapshot/HTML so the snapshot captures fresh fund sub-scores.
    ap.add_argument("--fundamentals-only", action="store_true",
                    help="Only refresh scores.fundamental_scores (+ screener fundamentals) — fast pre-snapshot refresh")
    ap.add_argument("--load-csv-scores", action="store_true",
                    help="Legacy mode: import comprehensive_nse_enhanced_*.csv into scores.daily_scores")
    args = ap.parse_args()
    run_date = args.date

    print(f"\nPostgreSQL Daily Loader — {run_date}")
    print("=" * 45)

    try:
        conn = pg()
    except Exception as e:
        print(f"  ERROR: Cannot connect to PostgreSQL: {e}")
        print("  Hint: Start with:  postgres/start_pg.sh")
        sys.exit(1)

    conn.autocommit = False
    cur = conn.cursor()

    try:
        if args.eod_only:
            load_equity_eod(cur)
            load_index_eod(cur)
            conn.commit()
            print(f"\n✅ PostgreSQL EOD load complete for {run_date}")
            return

        if args.fno_only:
            load_fno_today(cur)
            conn.commit()
            run_fno_analytics(cur)
            conn.commit()
            print(f"\n✅ PostgreSQL F&O EOD load complete for {run_date}")
            return

        # PG-FUND-ORDER 2026-05-26: fast path for refreshing fundamentals
        # ahead of the sector rotation tracker snapshot. Avoids the bug where
        # the snapshot wrote NULLs because fundamentals had not been reloaded
        # since the previous day's universe drifted.
        if args.fundamentals_only:
            load_fundamental_scores(cur)
            load_screener_fundamentals(cur, run_date)
            conn.commit()
            print(f"\n✅ PostgreSQL fundamentals refresh complete for {run_date}")
            return

        load_equity_eod(cur)
        load_index_eod(cur)
        load_ref_instruments(cur)
        load_fundamental_scores(cur)
        load_screener_fundamentals(cur, run_date)
        load_stage_snapshots(cur)
        load_stage_changes(cur)
        if args.load_csv_scores:
            load_daily_scores(cur)
        else:
            print("  scores.daily_scores: using direct PostgreSQL analysis output (CSV import skipped)")
        load_fii_dii(cur)
        load_breadth(cur)
        load_ma_breadth(cur)
        load_global_index_levels(cur)
        load_deals_today(cur)
        if not args.skip_fno:
            load_fno_today(cur)
        # Rebuild scores.sector_top_stocks from today's stage_snapshots — this
        # replaces the deprecated R-script CSV pipeline (analyze_all_sectors.R)
        # whose CSV output stopped flowing after STEP 6 was repurposed.
        load_sector_top_stocks(cur, run_date)
        conn.commit()
        print("\n  ✓ Data loaded")

        run_screeners(cur, run_date)
        conn.commit()

        run_fno_analytics(cur)
        conn.commit()

        refresh_views(cur)
        conn.commit()

        print(f"\n✅ PostgreSQL load complete for {run_date}")

    except Exception as e:
        conn.rollback()
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
