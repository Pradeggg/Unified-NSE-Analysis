#!/usr/bin/env python3
"""
postgres/migrate.py
====================
One-shot migration that loads ALL existing data (SQLite + CSV) into PostgreSQL.
Safe to re-run — all inserts use ON CONFLICT DO NOTHING or DO UPDATE.

Usage:
    python3 postgres/migrate.py
    python3 postgres/migrate.py --section signals   # load only one section
    python3 postgres/migrate.py --dry-run           # validate only, no writes
"""

import os
import sys
import glob
import sqlite3
import argparse
import json
import re
from datetime import datetime, date
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values
import pandas as pd

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
BASE = Path(__file__).parent.parent          # project root
DATA = BASE / "data"
REPORTS_CSV = BASE / "reports" / "generated_csv" / "2026"
REPORTS_DIR = BASE / "reports"
PAGE_SIZE = 500

PG_DSN = "dbname=nse_market user=nse_admin host=/tmp"   # unix socket

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def pg():
    return psycopg2.connect(PG_DSN)


def norm_date(v):
    """Return ISO date string or None."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, (date, datetime)):
        return str(v)[:10]
    s = str(v).strip()
    for fmt in ("%Y-%m-%d", "%d-%b-%Y", "%d %b %Y", "%Y%m%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


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


def safe_bool(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.strip().upper() in ('TRUE', '1', 'YES', 'T')
    return None


def upsert(cur, table, rows, conflict_cols, update_cols=None):
    """Generic upsert — INSERT … ON CONFLICT (conflict_cols) DO UPDATE."""
    if not rows:
        return 0
    cols = list(rows[0].keys())
    values = [[r.get(c) for c in cols] for r in rows]
    conflict = ", ".join(conflict_cols)
    if update_cols:
        updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_cols)
        sql = (
            f"INSERT INTO {table} ({', '.join(cols)}) VALUES %s "
            f"ON CONFLICT ({conflict}) DO UPDATE SET {updates}"
        )
    else:
        sql = (
            f"INSERT INTO {table} ({', '.join(cols)}) VALUES %s "
            f"ON CONFLICT ({conflict}) DO NOTHING"
        )
    execute_values(cur, sql, values, page_size=PAGE_SIZE)
    return len(values)


def update_existing(cur, table, rows, key_cols, update_cols):
    if not rows:
        return 0
    cols = list(dict.fromkeys([*key_cols, *update_cols]))
    values = [[r.get(c) for c in cols] for r in rows]
    join_clause = " AND ".join(f"t.{c} = src.{c}" for c in key_cols)
    set_clause = ", ".join(f"{c} = src.{c}" for c in update_cols)
    sql = (
        f"UPDATE {table} AS t SET {set_clause} "
        f"FROM (VALUES %s) AS src ({', '.join(cols)}) "
        f"WHERE {join_clause}"
    )
    execute_values(cur, sql, values, page_size=PAGE_SIZE)
    return len(values)


def normalize_fno_option_type(v):
    s = clean_nullable_token(v)
    return "FUT" if not s else s


def upsert_fno_eod(cur, rows):
    if not rows:
        return 0
    for trade_date in sorted({r["trade_date"] for r in rows if r.get("trade_date")}):
        cur.execute("SELECT derivatives.ensure_fno_monthly_partition(%s)", (trade_date,))
    cols = list(rows[0].keys())
    values = [[r.get(c) for c in cols] for r in rows]
    sql = (
        f"INSERT INTO derivatives.fno_eod ({', '.join(cols)}) VALUES %s "
        "ON CONFLICT ON CONSTRAINT fno_eod_pkey DO UPDATE SET "
        "open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low, "
        "close = EXCLUDED.close, last_price = EXCLUDED.last_price, "
        "prev_close = EXCLUDED.prev_close, underlying_price = EXCLUDED.underlying_price, "
        "settle_price = EXCLUDED.settle_price, open_interest = EXCLUDED.open_interest, "
        "oi_change = EXCLUDED.oi_change, volume = EXCLUDED.volume, "
        "turnover_cr = EXCLUDED.turnover_cr, total_trades = EXCLUDED.total_trades, "
        "lot_size = EXCLUDED.lot_size"
    )
    execute_values(cur, sql, values, page_size=PAGE_SIZE)
    return len(values)


def log(msg):
    print(f"  {msg}", flush=True)


NULL_TOKENS = {"", "na", "nan", "none", "null", "nat"}


def clean_text(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v).strip()
    return s or None


def clean_nullable_token(v):
    s = clean_text(v)
    if not s:
        return None
    return None if s.lower() in NULL_TOKENS else s


def latest_report(pattern: str):
    candidates = [p for p in REPORTS_DIR.rglob(pattern) if p.is_file()]
    if not candidates:
        return None
    return max(candidates, key=lambda p: (p.stat().st_mtime, p.name))


# ---------------------------------------------------------------------------
# 1. REF — instruments + indices + index compositions + sectors
# ---------------------------------------------------------------------------

def load_ref(cur, dry_run=False):
    print("\n[1/8] REF — Instruments, Indices, Index Compositions")

    csv_path = DATA / "nse_sec_full_data.csv"
    if csv_path.exists():
        df = pd.read_csv(csv_path, low_memory=False)
        if not df.empty:
            df["SYMBOL"] = df["SYMBOL"].map(clean_text)
            df = df[df["SYMBOL"].notna()].copy()
            df["trade_date"] = pd.to_datetime(df.get("TIMESTAMP"), errors="coerce").dt.strftime("%Y-%m-%d")
            df["isin_clean"] = df.get("ISIN").map(clean_nullable_token) if "ISIN" in df.columns else None
            df["_rownum"] = range(len(df))
            latest_by_symbol = df.groupby("SYMBOL", as_index=False, sort=False).tail(1).copy()
            latest_by_symbol = latest_by_symbol.sort_values(["trade_date", "_rownum"], na_position="first")
            dup_isin_mask = latest_by_symbol["isin_clean"].notna() & latest_by_symbol["isin_clean"].duplicated(keep="last")
            latest_by_symbol.loc[dup_isin_mask, "isin_clean"] = None
            rows = [
                {
                    "symbol": sym,
                    "isin": r.get("isin_clean"),
                    "company_name": sym,
                    "series": clean_text(r.get("SERIES")) or "EQ",
                }
                for _, r in latest_by_symbol.iterrows()
                if (sym := clean_text(r.get("SYMBOL")))
            ]
            if not dry_run:
                upsert(cur, "ref.instruments", rows, ["symbol"], ["isin", "company_name", "series"])
                symbol_values = [(row["symbol"],) for row in rows]
                cur.execute("CREATE TEMP TABLE ref_symbols_base (symbol TEXT PRIMARY KEY) ON COMMIT DROP")
                execute_values(cur, "INSERT INTO ref_symbols_base (symbol) VALUES %s", symbol_values, page_size=PAGE_SIZE)
                cur.execute("DELETE FROM ref.index_compositions WHERE symbol NOT IN (SELECT symbol FROM ref_symbols_base)")
                cur.execute("DELETE FROM ref.instruments WHERE symbol NOT IN (SELECT symbol FROM ref_symbols_base)")
            log(f"ref.instruments (nse_sec_full_data deduped): {len(rows)} rows")

    mcap_files = sorted(p for p in BASE.rglob("mcap*.csv") if p.is_file())
    for mcap_path in mcap_files:
        df = pd.read_csv(mcap_path, low_memory=False)
        rows = []
        for _, r in df.iterrows():
            sym = clean_text(r.get("Symbol"))
            if not sym:
                continue
            rows.append({
                "symbol": sym,
                "company_name": clean_text(r.get("Security Name")) or sym,
                "face_value": safe_float(r.get("Face Value(Rs.)")),
                "issue_size": safe_int(r.get("Issue Size")),
            })
        if not dry_run:
            update_existing(cur, "ref.instruments", rows, ["symbol"], ["company_name", "face_value", "issue_size"])
        log(f"ref.instruments ({mcap_path.name}): {len(rows)} rows")

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
                "market_cap_cat": clean_nullable_token(r.get("MARKET_CAP_CATEGORY")),
                "sector": clean_nullable_token(r.get("SECTOR")),
            })
        if not dry_run:
            update_existing(cur, "ref.instruments", rows, ["symbol"], ["company_name", "market_cap_cat", "sector"])
        log(f"ref.instruments ({latest.name}): {len(rows)} rows")

    snap_db = DATA / "sector_rotation_tracker.db"
    if snap_db.exists():
        conn = sqlite3.connect(snap_db)
        df = pd.read_sql("SELECT * FROM stage_snapshots", conn)
        conn.close()
        rows = []
        if not df.empty:
            df["symbol"] = df["symbol"].map(clean_text)
            df = df[df["symbol"].notna()].copy()
            df["snapshot_date"] = pd.to_datetime(df.get("snapshot_date"), errors="coerce").dt.strftime("%Y-%m-%d")
            df["_rownum"] = range(len(df))
            df = df.sort_values(["snapshot_date", "_rownum"], na_position="first")
            df = df.groupby("symbol", as_index=False, sort=False).tail(1)
            for _, r in df.iterrows():
                sym = clean_text(r.get("symbol"))
                if not sym:
                    continue
                rows.append({
                    "symbol": sym,
                    "company_name": clean_text(r.get("company_name")) or sym,
                    "sector": clean_nullable_token(r.get("sector")),
                    "market_cap_cat": clean_nullable_token(r.get("market_cap_cat")),
                })
        if not dry_run:
            update_existing(cur, "ref.instruments", rows, ["symbol"], ["company_name", "sector", "market_cap_cat"])
        log(f"ref.instruments (stage_snapshots latest): {len(rows)} rows")

    catalog = DATA / "nse_indices_catalog.csv"
    if catalog.exists():
        df = pd.read_csv(catalog, low_memory=False)
        rows = []
        for _, r in df.iterrows():
            sym = clean_text(r.get("api_index_symbol"))
            if not sym:
                continue
            rows.append({
                "index_symbol": sym,
                "display_name": clean_text(r.get("index_display_name")) or sym,
                "category_code": clean_nullable_token(r.get("category_code")),
                "category_label": clean_nullable_token(r.get("category_label")),
                "nse_group_raw": clean_nullable_token(r.get("nse_group_raw")),
                "is_thematic": safe_bool(r.get("is_thematic")),
                "last_close": safe_float(r.get("last")),
                "pe": safe_float(r.get("pe")),
                "pb": safe_float(r.get("pb")),
                "year_high": safe_float(r.get("year_high")),
                "year_low": safe_float(r.get("year_low")),
            })
        if not dry_run:
            upsert(
                cur,
                "ref.indices",
                rows,
                ["index_symbol"],
                ["display_name", "category_code", "category_label", "nse_group_raw", "is_thematic", "last_close", "pe", "pb", "year_high", "year_low"],
            )
        log(f"ref.indices: {len(rows)} rows")

    mapping = DATA / "index_stock_mapping.csv"
    if mapping.exists():
        df = pd.read_csv(mapping, low_memory=False)
        attempted = 0
        inserted = 0
        for _, r in df.iterrows():
            idx = clean_text(r.get("INDEX_NAME"))
            sym = clean_text(r.get("STOCK_SYMBOL"))
            if not idx or not sym:
                continue
            attempted += 1
            if dry_run:
                inserted += 1
                continue
            cur.execute("SAVEPOINT index_comp_row")
            try:
                cur.execute(
                    "INSERT INTO ref.index_compositions (index_symbol, symbol) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                    (idx, sym),
                )
                inserted += cur.rowcount if cur.rowcount > 0 else 0
                cur.execute("RELEASE SAVEPOINT index_comp_row")
            except Exception:
                cur.execute("ROLLBACK TO SAVEPOINT index_comp_row")
                cur.execute("RELEASE SAVEPOINT index_comp_row")
        log(f"ref.index_compositions: {inserted} rows inserted ({attempted} attempted)")


# ---------------------------------------------------------------------------
# 2. MARKET — equity EOD, index EOD, market cap, global prices
# ---------------------------------------------------------------------------

def load_market(cur, dry_run=False):
    print("\n[2/8] MARKET — EOD Prices, Index Levels, Global Prices")

    # --- equity EOD from nse_sec_full_data.csv (historical) ---
    csv_path = DATA / "nse_sec_full_data.csv"
    if csv_path.exists():
        df = pd.read_csv(csv_path, low_memory=False)
        rows = []
        for _, r in df.iterrows():
            sym = clean_text(r.get("SYMBOL"))
            dt = norm_date(r.get("TIMESTAMP"))
            if not sym or not dt:
                continue
            rows.append({
                "trade_date": dt,
                "symbol": sym,
                "series": clean_text(r.get("SERIES")) or "EQ",
                "open": safe_float(r.get("OPEN")),
                "high": safe_float(r.get("HIGH")),
                "low": safe_float(r.get("LOW")),
                "close": safe_float(r.get("CLOSE")),
                "last_price": safe_float(r.get("LAST")),
                "prev_close": safe_float(r.get("PREVCLOSE")),
                "volume": safe_int(r.get("TOTTRDQTY")),
                "turnover_cr": safe_float(r.get("TOTTRDVAL")),
                "total_trades": safe_int(r.get("TOTALTRADES")),
                "week52_high": safe_float(r.get("HI_52_WK")),
                "week52_low": safe_float(r.get("LO_52_WK")),
            })
        if not dry_run and rows:
            upsert(cur, "market.equity_eod", rows, ["trade_date", "symbol", "series"])
        log(f"market.equity_eod (nse_sec_full_data): {len(rows)} rows")

    # --- index EOD from nse_index_data.csv ---
    index_csv = DATA / "nse_index_data.csv"
    if index_csv.exists():
        df = pd.read_csv(index_csv, low_memory=False)
        rows = []
        for _, r in df.iterrows():
            idx = clean_text(r.get("SYMBOL"))
            dt = norm_date(r.get("TIMESTAMP"))
            if not idx or not dt:
                continue
            turnover = safe_float(r.get("TOTTRDVAL"))
            rows.append({
                "trade_date": dt,
                "index_symbol": idx,
                "open": safe_float(r.get("OPEN")),
                "high": safe_float(r.get("HIGH")),
                "low": safe_float(r.get("LOW")),
                "close": safe_float(r.get("CLOSE")),
                "prev_close": safe_float(r.get("PREVCLOSE")),
                "volume": safe_int(r.get("TOTTRDQTY")),
                "turnover_cr": round(turnover / 1e7, 4) if turnover is not None else None,
                "total_trades": safe_int(r.get("TOTALTRADES")),
                "week52_high": safe_float(r.get("HI_52_WK")),
                "week52_low": safe_float(r.get("LO_52_WK")),
            })
        if not dry_run and rows:
            upsert(
                cur,
                "market.index_eod",
                rows,
                ["trade_date", "index_symbol"],
                ["open", "high", "low", "close", "prev_close", "volume", "turnover_cr", "total_trades", "week52_high", "week52_low"],
            )
        log(f"market.index_eod (nse_index_data): {len(rows)} rows")

    # --- market cap history from root bhavcopy ---
    for mcap_path in sorted(BASE.glob("mcap*.csv")):
        # filename: mcap29102025.csv → date 2025-10-29
        m = re.search(r"mcap(\d{2})(\d{2})(\d{4})", mcap_path.name)
        snap_date = f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else None
        if not snap_date:
            continue
        df = pd.read_csv(mcap_path, low_memory=False)
        rows = []
        for _, r in df.iterrows():
            sym = str(r.get("Symbol","")).strip()
            if not sym:
                continue
            mc_str = str(r.get("Market Cap(Rs.)", "")).strip().replace(",","")
            rows.append({
                "snapshot_date": snap_date,
                "symbol":        sym,
                "series":        str(r.get("Series","EQ")).strip(),
                "face_value":    safe_float(r.get("Face Value(Rs.)")),
                "issue_size":    safe_int(r.get("Issue Size")),
                "close_price":   safe_float(r.get("Close Price/Paid up value(Rs.)")),
                "market_cap_cr": safe_float(mc_str) / 1e7 if mc_str else None,
            })
        if not dry_run and rows:
            upsert(cur, "market.market_cap_history", rows,
                   ["snapshot_date","symbol","series"])
        log(f"market.market_cap_history ({mcap_path.name}): {len(rows)} rows")

    # --- 52-week H/L ---
    for hl_path in sorted(BASE.glob("hl*.csv")):
        m = re.search(r"hl(\d{2})(\d{2})(\d{4})", hl_path.name)
        snap_date = f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else None
        if not snap_date:
            continue
        df = pd.read_csv(hl_path, low_memory=False)
        rows = []
        for _, r in df.iterrows():
            sym = str(r.get("SECURITY","")).strip()
            if not sym:
                continue
            rows.append({
                "snapshot_date": snap_date,
                "symbol":        sym,
                "new_high":      safe_float(r.get("NEW")),
                "prev_high":     safe_float(r.get("PREVIOUS")),
                "status":        str(r.get("NEW_STATUS","")).strip() or None,
            })
        if not dry_run and rows:
            upsert(cur, "market.week52_extremes", rows, ["snapshot_date","symbol"])
        log(f"market.week52_extremes ({hl_path.name}): {len(rows)} rows")

    # --- nse_analysis.db → index_analysis ---
    for db_path in [DATA / "nse_analysis.db", BASE / "nse_analysis.db"]:
        if not db_path.exists():
            continue
        conn = sqlite3.connect(db_path)
        df = pd.read_sql("SELECT * FROM index_analysis", conn)
        conn.close()
        rows = []
        for _, r in df.iterrows():
            rows.append({
                "trade_date":       norm_date(r.get("analysis_date")),
                "index_symbol":     str(r.get("index_name","")).strip(),
                "close":            safe_float(r.get("current_level")),
                "technical_score":  safe_float(r.get("technical_score")),
                "rsi":              safe_float(r.get("rsi")),
                "momentum_50d":     safe_float(r.get("momentum_50d")),
                "relative_strength":safe_float(r.get("relative_strength")),
                "trend_signal":     str(r.get("trend_signal","")).strip() or None,
                "trading_signal":   str(r.get("trading_signal","")).strip() or None,
            })
        rows = [r for r in rows if r["trade_date"] and r["index_symbol"]]
        if not dry_run and rows:
            upsert(cur, "market.index_eod", rows, ["trade_date","index_symbol"],
                   ["technical_score","rsi","momentum_50d","trend_signal","trading_signal"])
        log(f"market.index_eod (nse_analysis.db): {len(rows)} rows")
        break

    # --- global prices ---
    for gp in [DATA / "global_market" / "prices.csv",
               DATA / "global_market" / "latest_snapshot.csv"]:
        if not gp.exists():
            continue
        df = pd.read_csv(gp, low_memory=False)
        rows = []
        for _, r in df.iterrows():
            sym = str(r.get("SYMBOL","")).strip()
            dt  = norm_date(r.get("DATE"))
            if not sym or not dt:
                continue
            rows.append({
                "trade_date": dt, "symbol": sym,
                "open":  safe_float(r.get("OPEN")),
                "high":  safe_float(r.get("HIGH")),
                "low":   safe_float(r.get("LOW")),
                "close": safe_float(r.get("CLOSE")),
                "volume":safe_int(r.get("VOLUME")),
                "source":str(r.get("SOURCE","yfinance")).strip(),
            })
        if not dry_run and rows:
            upsert(cur, "market.global_prices", rows, ["trade_date","symbol"],
                   ["close","volume"])
        log(f"market.global_prices ({gp.name}): {len(rows)} rows")

    # --- global index levels ---
    gi = DATA / "global_indices.csv"
    if gi.exists():
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
                if v is not None:
                    rows.append({"trade_date": dt, "index_name": col, "close": v})
        if not dry_run and rows:
            upsert(cur, "market.global_index_levels", rows,
                   ["trade_date","index_name"], ["close"])
        log(f"market.global_index_levels: {len(rows)} rows")

    # --- intraday snapshots ---
    for f in sorted((BASE / "core").glob("*Intraday_Analysis_*.csv")):
        df = pd.read_csv(f, low_memory=False)
        # extract date from filename
        m = re.search(r"(\d{8})", f.name)
        dt = datetime.strptime(m.group(1), "%Y%m%d").strftime("%Y-%m-%d") if m else None
        if not dt:
            continue
        at_col = "Analysis_Time" if "Analysis_Time" in df.columns else None
        rows = []
        for _, r in df.iterrows():
            sym = str(r.get("Symbol","")).strip()
            if not sym:
                continue
            at_raw = str(r.get("Analysis_Time","")).strip() if at_col else ""
            # Analysis_Time can be "2025-08-11 11:03" or just "11:03"
            if at_raw and " " in at_raw:
                # already has date prefix — use as-is
                ts = at_raw
            elif at_raw and len(at_raw) >= 4:
                ts = f"{dt} {at_raw}"
            else:
                ts = f"{dt} 15:30:00"
            rows.append({
                "snapshot_ts":             ts,
                "trade_date":              dt,
                "symbol":                  sym,
                "current_price":           safe_float(r.get("Current_Price")),
                "price_change":            safe_float(r.get("Price_Change")),
                "change_pct":              safe_float(r.get("Price_Change_Pct")),
                "technical_score":         safe_float(r.get("Technical_Score")),
                "trend_score":             safe_float(r.get("trend_score")),
                "momentum_score":          safe_float(r.get("momentum_score")),
                "volume_score":            safe_float(r.get("volume_score")),
                "support_resistance_score":safe_float(r.get("support_resistance_score")),
                "volatility_score":        safe_float(r.get("volatility_score")),
                "data_points":             safe_int(r.get("Data_Points")),
            })
        if not dry_run and rows:
            upsert(cur, "market.intraday_snapshots", rows,
                   ["snapshot_ts","symbol"], ["technical_score","current_price"])
        log(f"market.intraday_snapshots ({f.name}): {len(rows)} rows")


# ---------------------------------------------------------------------------
# 3. DERIVATIVES — FNO EOD + signals
# ---------------------------------------------------------------------------

def load_derivatives(cur, dry_run=False):
    print("\n[3/8] DERIVATIVES — F&O EOD, Signals")

    # --- from SQLite ---
    fno_db = DATA / "fno" / "fno_eod.db"
    if fno_db.exists():
        conn = sqlite3.connect(fno_db)
        df = pd.read_sql("SELECT * FROM fno_eod", conn)
        conn.close()
        rows = []
        for _, r in df.iterrows():
            rows.append({
                "trade_date":     norm_date(r.get("trade_date")),
                "symbol":         str(r.get("symbol","")).strip(),
                "expiry_date":    norm_date(r.get("expiry_date")),
                "instrument":     str(r.get("instrument","")).strip(),
                "option_type":    normalize_fno_option_type(r.get("option_type")),
                "strike":         safe_float(r.get("strike")) or 0.0,
                "open":           safe_float(r.get("open")),
                "high":           safe_float(r.get("high")),
                "low":            safe_float(r.get("low")),
                "close":          safe_float(r.get("close")),
                "last_price":     safe_float(r.get("last_price")),
                "prev_close":     safe_float(r.get("prev_close")),
                "underlying_price":safe_float(r.get("underlying")),
                "settle_price":   safe_float(r.get("settle_price")),
                "open_interest":  safe_int(r.get("oi")),
                "oi_change":      safe_int(r.get("oi_change")),
                "volume":         safe_int(r.get("volume")),
                "turnover_cr":    safe_float(r.get("turnover_cr")),
            })
        rows = [r for r in rows if r["trade_date"] and r["symbol"] and r["expiry_date"]]
        if not dry_run and rows:
            upsert_fno_eod(cur, rows)
        log(f"derivatives.fno_eod (SQLite): {len(rows)} rows")

    # --- from _fno_cache CSVs (new format) ---
    n_loaded = 0
    for fno_csv in sorted((DATA / "_fno_cache").glob("fo_bhav_*.csv")):
        if "test" in fno_csv.name:
            continue
        try:
            df = pd.read_csv(fno_csv, low_memory=False)
        except Exception as exc:
            log(f"derivatives.fno_eod ({fno_csv.name}): skipped malformed CSV ({exc})")
            continue
        if "TradDt" not in df.columns:
            log(f"derivatives.fno_eod ({fno_csv.name}): skipped missing TradDt")
            continue
        rows = []
        for _, r in df.iterrows():
            sym = str(r.get("SYMBOL","")).strip()
            dt  = norm_date(r.get("TradDt"))
            exp = norm_date(r.get("EXPIRY_DATE"))
            if not sym or not dt or not exp:
                continue
            rows.append({
                "trade_date":      dt,
                "symbol":          sym,
                "expiry_date":     exp,
                "instrument":      str(r.get("INSTRUMENT","")).strip(),
                "option_type":     normalize_fno_option_type(r.get("OPTION_TYPE")),
                "strike":          safe_float(r.get("STRIKE_PRICE")) or 0.0,
                "open":            safe_float(r.get("OpnPric")),
                "high":            safe_float(r.get("HghPric")),
                "low":             safe_float(r.get("LwPric")),
                "close":           safe_float(r.get("CLOSE")),
                "last_price":      safe_float(r.get("LastPric")),
                "prev_close":      safe_float(r.get("PREV_CLOSE")),
                "underlying_price":safe_float(r.get("UndrlygPric")),
                "settle_price":    safe_float(r.get("SETTLE_PRICE")),
                "open_interest":   safe_int(r.get("OPEN_INTEREST")),
                "oi_change":       safe_int(r.get("CHANGE_IN_OI")),
                "volume":          safe_int(r.get("VOLUME")),
                "turnover_cr":     round(safe_float(r.get("TtlTrfVal")) / 1e7, 4) if safe_float(r.get("TtlTrfVal")) else None,
                "total_trades":    safe_int(r.get("TtlNbOfTxsExctd")),
                "lot_size":        safe_int(r.get("NewBrdLotQty")),
            })
        if not dry_run and rows:
            upsert_fno_eod(cur, rows)
        n_loaded += len(rows)
    log(f"derivatives.fno_eod (_fno_cache CSVs): {n_loaded} rows")

    # --- fno_signals.csv ---
    fno_sig = DATA / "fno_signals.csv"
    if fno_sig.exists():
        df = pd.read_csv(fno_sig, low_memory=False)
        # use today's date as snapshot since file has no date col
        today = str(date.today())
        rows = []
        for _, r in df.iterrows():
            sym = str(r.get("SYMBOL","")).strip()
            if not sym:
                continue
            rows.append({
                "snapshot_date": today,
                "symbol":        sym,
                "pcr":           safe_float(r.get("FNO_PCR")),
                "oi_change_5d":  safe_float(r.get("FNO_OI_CHANGE_5D")),
                "price_change":  safe_float(r.get("FNO_PRICE_CHANGE")),
                "buildup":       str(r.get("FNO_BUILDUP","")).strip() or None,
                "max_pain":      safe_float(r.get("FNO_MAX_PAIN")),
                "fno_signal":    str(r.get("FNO_SIGNAL","")).strip() or None,
            })
        if not dry_run and rows:
            upsert(cur, "derivatives.fno_signals", rows,
                   ["snapshot_date","symbol"], ["pcr","oi_change_5d","buildup","fno_signal"])
        log(f"derivatives.fno_signals: {len(rows)} rows")


# ---------------------------------------------------------------------------
# 4. SCORES — daily_scores, stage_snapshots, stage_changes, screeners, ma_breadth
# ---------------------------------------------------------------------------

def load_scores(cur, dry_run=False):
    print("\n[4/8] SCORES — Daily Scores, Stage Snapshots, Screeners, MA Breadth")

    # --- comprehensive_nse_enhanced_*.csv → scores.daily_scores ---
    n_total = 0
    processed_dates = set()
    for csv_path in sorted(REPORTS_CSV.glob("comprehensive_nse_enhanced_*.csv")):
        df = pd.read_csv(csv_path, low_memory=False)
        if df.empty:
            continue
        # Determine score_date from ANALYSIS_DATE col or filename
        if "ANALYSIS_DATE" in df.columns:
            score_date = norm_date(df["ANALYSIS_DATE"].dropna().iloc[0]) if len(df) else None
        else:
            m = re.search(r"(\d{8})(?:_\d+)?\.csv$", csv_path.name)
            if m:
                score_date = datetime.strptime(m.group(1), "%Y%m%d").strftime("%Y-%m-%d")
            else:
                # Try ddmmyyyy prefix
                m2 = re.search(r"enhanced_(\d{2})(\d{2})(\d{4})", csv_path.name)
                score_date = f"{m2.group(3)}-{m2.group(2)}-{m2.group(1)}" if m2 else None
        if not score_date or score_date in processed_dates:
            continue
        processed_dates.add(score_date)
        rows = []
        for _, r in df.iterrows():
            sym = str(r.get("SYMBOL","")).strip()
            if not sym:
                continue
            rows.append({
                "score_date":         score_date,
                "symbol":             sym,
                "company_name":       str(r.get("COMPANY_NAME", sym)).strip(),
                "market_cap_cat":     str(r.get("MARKET_CAP_CATEGORY","")).strip() or None,
                "current_price":      safe_float(r.get("CURRENT_PRICE")),
                "change_1d_pct":      safe_float(r.get("CHANGE_1D")),
                "change_1w_pct":      safe_float(r.get("CHANGE_1W")),
                "change_1m_pct":      safe_float(r.get("CHANGE_1M")),
                "trading_value":      safe_float(r.get("TRADING_VALUE")),
                "technical_score":    safe_float(r.get("TECHNICAL_SCORE")),
                "rsi":                safe_float(r.get("RSI")),
                "relative_strength":  safe_float(r.get("RELATIVE_STRENGTH")),
                "trend_signal":       str(r.get("TREND_SIGNAL","")).strip() or None,
                "trading_signal":     str(r.get("TRADING_SIGNAL","")).strip() or None,
                "can_slim_score":     safe_float(r.get("CAN_SLIM_SCORE")),
                "minervini_score":    safe_float(r.get("MINERVINI_SCORE")),
                "fundamental_score":  safe_float(r.get("FUNDAMENTAL_SCORE")),
                "enhanced_fund_score":safe_float(r.get("ENHANCED_FUND_SCORE")),
                "earnings_quality":   safe_float(r.get("EARNINGS_QUALITY")),
                "sales_growth":       safe_float(r.get("SALES_GROWTH")),
                "financial_strength": safe_float(r.get("FINANCIAL_STRENGTH")),
                "institutional_backing":safe_float(r.get("INSTITUTIONAL_BACKING")),
            })
        if not dry_run and rows:
            upsert(cur, "scores.daily_scores", rows, ["score_date","symbol"],
                   ["current_price","change_1d_pct","technical_score","rsi",
                    "trading_signal","investment_score" if False else "enhanced_fund_score"])
        n_total += len(rows)
    log(f"scores.daily_scores (comprehensive CSVs, {len(processed_dates)} dates): {n_total} rows")

    # --- sector_rotation_tracker.db → stage_snapshots ---
    snap_db = DATA / "sector_rotation_tracker.db"
    if snap_db.exists():
        conn = sqlite3.connect(snap_db)
        df = pd.read_sql("SELECT * FROM stage_snapshots", conn)
        conn.close()
        rows = []
        for _, r in df.iterrows():
            sym = str(r.get("symbol","")).strip()
            dt  = norm_date(r.get("snapshot_date"))
            if not sym or not dt:
                continue
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
                "company_name":       str(r.get("company_name",sym)).strip(),
                "sector":             str(r.get("sector","")).strip() or None,
                "market_cap_cat":     str(r.get("market_cap_cat","")).strip() or None,
                "price":              safe_float(r.get("price")),
                "live_price":         safe_float(r.get("live_price")),
                "price_date":         norm_date(r.get("price_date")),
                "change_1d_pct":      safe_float(r.get("change_1d_pct")),
                "change_1w_pct":      safe_float(r.get("change_1w_pct")),
                "change_1m_pct":      safe_float(r.get("change_1m_pct")),
                "stage":              str(r.get("stage","")).strip() or None,
                "stage_score":        safe_float(r.get("stage_score")),
                "technical_score":    safe_float(r.get("technical_score")),
                "rsi":                safe_float(r.get("rsi")),
                "trend_signal":       str(r.get("trend_signal","")).strip() or None,
                "trading_signal":     str(r.get("trading_signal","")).strip() or None,
                "relative_strength":  safe_float(r.get("relative_strength")),
                "supertrend_state":   str(r.get("supertrend_state","")).strip() or None,
                "supertrend_value":   safe_float(r.get("supertrend_value")),
                "can_slim_score":     safe_float(r.get("can_slim_score")),
                "minervini_score":    safe_float(r.get("minervini_score")),
                "fundamental_score":  safe_float(r.get("fundamental_score")),
                "enhanced_fund_score":safe_float(r.get("enhanced_fund_score")),
                "earnings_quality":   safe_float(r.get("earnings_quality")),
                "sales_growth":       safe_float(r.get("sales_growth")),
                "financial_strength": safe_float(r.get("financial_strength")),
                "institutional_backing":safe_float(r.get("institutional_backing")),
                "investment_score":   safe_float(r.get("investment_score")),
                "stance":             str(r.get("stance","")).strip() or None,
                "narrative":          str(r.get("narrative","")).strip() or None,
                "fund_details":       json.dumps(fd) if fd else None,
                "source_csv":         str(r.get("source_csv","")).strip() or None,
            })
        if not dry_run and rows:
            upsert(cur, "scores.stage_snapshots", rows, ["snapshot_date","symbol"],
                   ["live_price","stage","stage_score","technical_score","investment_score",
                    "trading_signal","narrative"])
        log(f"scores.stage_snapshots: {len(rows)} rows")

        # --- stage_changes ---
        conn = sqlite3.connect(snap_db)
        df2 = pd.read_sql("SELECT * FROM stage_changes", conn)
        conn.close()
        rows2 = []
        for _, r in df2.iterrows():
            sym = str(r.get("symbol","")).strip()
            dt  = norm_date(r.get("change_date"))
            if not sym or not dt:
                continue
            rows2.append({
                "change_date":    dt,
                "compare_date":   norm_date(r.get("compare_date")),
                "symbol":         sym,
                "company_name":   str(r.get("company_name",sym)).strip(),
                "stage_now":      str(r.get("stage_now","")).strip() or None,
                "stage_prev":     str(r.get("stage_prev","")).strip() or None,
                "stage_changed":  bool(r.get("stage_changed",False)),
                "change_type":    str(r.get("change_type","")).strip() or None,
                "price_now":      safe_float(r.get("price_now")),
                "price_prev":     safe_float(r.get("price_prev")),
                "price_chg_pct":  safe_float(r.get("price_chg_pct")),
                "live_price":     safe_float(r.get("live_price")),
                "live_vs_prev_pct":safe_float(r.get("live_vs_prev_pct")),
                "stage_score_now":safe_float(r.get("stage_score_now")),
                "stage_score_prev":safe_float(r.get("stage_score_prev")),
                "trading_signal": str(r.get("trading_signal","")).strip() or None,
            })
        if not dry_run and rows2:
            upsert(cur, "scores.stage_changes", rows2, ["change_date","symbol"])
        log(f"scores.stage_changes: {len(rows2)} rows")

    # --- fundamentals cache ---
    fund_cache = DATA / "_sector_rotation_fund_cache.csv"
    if fund_cache.exists():
        df = pd.read_csv(fund_cache, low_memory=False)
        rows = []
        for _, r in df.iterrows():
            sym = str(r.get("SYMBOL","")).strip()
            if not sym:
                continue
            rows.append({
                "symbol":               sym,
                "pnl_summary":          str(r.get("pnl_summary","")).strip() or None,
                "quarterly_summary":    str(r.get("quarterly_summary","")).strip() or None,
                "balance_sheet_summary":str(r.get("balance_sheet_summary","")).strip() or None,
                "cash_flow_summary":    str(r.get("cash_flow_summary","")).strip() or None,
                "investor_summary":     str(r.get("investor_summary","")).strip() or None,
                "ratios_summary":       str(r.get("ratios_summary","")).strip() or None,
            })
        if not dry_run and rows:
            upsert(cur, "scores.fundamentals", rows, ["symbol"],
                   [
                       "pnl_summary",
                       "quarterly_summary",
                       "balance_sheet_summary",
                       "cash_flow_summary",
                       "investor_summary",
                       "ratios_summary",
                   ])
        log(f"scores.fundamentals (fund_cache): {len(rows)} rows")

    # --- long_term_screeners_*.csv ---
    n_lt = 0
    proc_lt = set()
    for csv_path in sorted(REPORTS_CSV.glob("long_term_screeners_*.csv")):
        df = pd.read_csv(csv_path, low_memory=False)
        if df.empty:
            continue
        m = re.search(r"(\d{8})(?:_\d+)?\.csv$", csv_path.name)
        if m:
            score_date = datetime.strptime(m.group(1), "%Y%m%d").strftime("%Y-%m-%d")
        else:
            m2 = re.search(r"screeners_(\d{2})(\d{2})(\d{4})", csv_path.name)
            score_date = f"{m2.group(3)}-{m2.group(2)}-{m2.group(1)}" if m2 else None
        if not score_date or score_date in proc_lt:
            continue
        proc_lt.add(score_date)
        rows = []
        for _, r in df.iterrows():
            sym = str(r.get("SYMBOL","")).strip()
            if not sym:
                continue
            rows.append({
                "score_date":           score_date,
                "symbol":               sym,
                "market_cap_cat":       str(r.get("MARKET_CAP_CATEGORY","")).strip() or None,
                "current_price":        safe_float(r.get("CURRENT_PRICE")),
                "monthly_rs":           safe_float(r.get("MONTHLY_RS")),
                "technical_score":      safe_float(r.get("TECHNICAL_SCORE")),
                "consolidation_breakout":safe_bool(r.get("CONSOLIDATION_BREAKOUT")),
                "cup_handle":           safe_bool(r.get("CUP_HANDLE")),
                "long_term_uptrend":    safe_bool(r.get("LONG_TERM_UPTREND")),
                "momentum_breakout":    safe_bool(r.get("MOMENTUM_BREAKOUT")),
                "support_bounce":       safe_bool(r.get("SUPPORT_BOUNCE")),
                "volume_accumulation":  safe_bool(r.get("VOLUME_ACCUMULATION")),
                "earnings_momentum":    safe_bool(r.get("EARNINGS_MOMENTUM")),
                "week52_high_breakout": safe_bool(r.get("WEEK52_HIGH_BREAKOUT")),
            })
        if not dry_run and rows:
            upsert(cur, "scores.long_term_screeners", rows, ["score_date","symbol"])
        n_lt += len(rows)
    log(f"scores.long_term_screeners ({len(proc_lt)} dates): {n_lt} rows")

    # --- NIFTY500_Market_Breadth → scores.ma_breadth ---
    n_mab = 0
    proc_mab = set()
    for csv_path in sorted(REPORTS_CSV.glob("NIFTY500_Market_Breadth_*.csv")):
        df = pd.read_csv(csv_path, low_memory=False)
        m = re.search(r"Breadth_(\d{8})", csv_path.name)
        snap_date = datetime.strptime(m.group(1), "%Y%m%d").strftime("%Y-%m-%d") if m else None
        if not snap_date or snap_date in proc_mab:
            continue
        proc_mab.add(snap_date)
        rows = []
        for _, r in df.iterrows():
            sym = str(r.get("SYMBOL","")).strip()
            if not sym:
                continue
            rows.append({
                "snapshot_date":  snap_date,
                "symbol":         sym,
                "current_price":  safe_float(r.get("CURRENT_PRICE")),
                "sma_20":         safe_float(r.get("SMA_20")),
                "sma_50":         safe_float(r.get("SMA_50")),
                "sma_100":        safe_float(r.get("SMA_100")),
                "sma_200":        safe_float(r.get("SMA_200")),
                "above_20dma":    safe_bool(r.get("ABOVE_20DMA")),
                "above_50dma":    safe_bool(r.get("ABOVE_50DMA")),
                "above_100dma":   safe_bool(r.get("ABOVE_100DMA")),
                "above_200dma":   safe_bool(r.get("ABOVE_200DMA")),
            })
        if not dry_run and rows:
            upsert(cur, "scores.ma_breadth", rows, ["snapshot_date","symbol"])
            # Update aggregated pct table
            cur.execute("SELECT breadth.compute_ma_pct(%s)", (snap_date,))
        n_mab += len(rows)
    log(f"scores.ma_breadth ({len(proc_mab)} dates): {n_mab} rows")

    # --- all_indexes / all_sectors top analysis ---
    for csv_path in sorted(REPORTS_CSV.glob("all_indexes_top5_analysis_*.csv")):
        df = pd.read_csv(csv_path, low_memory=False)
        m = re.search(r"(\d{8})", csv_path.name)
        score_date = datetime.strptime(m.group(1), "%Y%m%d").strftime("%Y-%m-%d") if m else norm_date(df.get("ANALYSIS_DATE", pd.Series()).iloc[0] if len(df) else None)
        if not score_date:
            continue
        rows = []
        for _, r in df.iterrows():
            sym = str(r.get("SYMBOL","")).strip()
            idx = str(r.get("INDEX_NAME","")).strip()
            if not sym and not idx:
                continue
            rows.append({
                "score_date":       score_date,
                "index_name":       idx,
                "index_strength":   safe_float(r.get("INDEX_STRENGTH")),
                "rank":             safe_int(r.get("RANK")),
                "symbol":           sym or "__INDEX__",
                "company_name":     str(r.get("COMPANY_NAME",sym)).strip() or None,
                "market_cap_cat":   str(r.get("MARKET_CAP_CATEGORY","")).strip() or None,
                "current_price":    safe_float(r.get("CURRENT_PRICE")),
                "change_1d_pct":    safe_float(r.get("CHANGE_1D")),
                "change_1w_pct":    safe_float(r.get("CHANGE_1W")),
                "change_1m_pct":    safe_float(r.get("CHANGE_1M")),
                "technical_score":  safe_float(r.get("TECHNICAL_SCORE")),
                "rsi":              safe_float(r.get("RSI")),
                "relative_strength":safe_float(r.get("RELATIVE_STRENGTH")),
                "can_slim_score":   safe_float(r.get("CAN_SLIM_SCORE")),
                "minervini_score":  safe_float(r.get("MINERVINI_SCORE")),
                "enhanced_fund_score":safe_float(r.get("ENHANCED_FUND_SCORE")),
                "trend_signal":     str(r.get("TREND_SIGNAL","")).strip() or None,
                "trading_signal":   str(r.get("TRADING_SIGNAL","")).strip() or None,
                "trading_value":    safe_float(r.get("TRADING_VALUE")),
            })
        if not dry_run and rows:
            upsert(cur, "scores.index_strength", rows, ["score_date","index_name","symbol"])

    for csv_path in sorted(REPORTS_CSV.glob("all_sectors_top5_analysis_*.csv")):
        df = pd.read_csv(csv_path, low_memory=False)
        m = re.search(r"(\d{8})", csv_path.name)
        score_date = datetime.strptime(m.group(1), "%Y%m%d").strftime("%Y-%m-%d") if m else None
        if not score_date:
            continue
        rows = []
        for _, r in df.iterrows():
            sym  = str(r.get("SYMBOL","")).strip()
            sect = str(r.get("SECTOR_NAME","")).strip()
            if not sym or not sect:
                continue
            rows.append({
                "score_date":       score_date,
                "sector_name":      sect,
                "sector_strength":  safe_float(r.get("SECTOR_STRENGTH")),
                "total_stocks":     safe_int(r.get("TOTAL_STOCKS")),
                "rank":             safe_int(r.get("RANK")),
                "symbol":           sym,
                "company_name":     str(r.get("COMPANY_NAME",sym)).strip() or None,
                "market_cap_cat":   str(r.get("MARKET_CAP_CATEGORY","")).strip() or None,
                "current_price":    safe_float(r.get("CURRENT_PRICE")),
                "change_1d_pct":    safe_float(r.get("CHANGE_1D")),
                "change_1w_pct":    safe_float(r.get("CHANGE_1W")),
                "change_1m_pct":    safe_float(r.get("CHANGE_1M")),
                "technical_score":  safe_float(r.get("TECHNICAL_SCORE")),
                "rsi":              safe_float(r.get("RSI")),
                "relative_strength":safe_float(r.get("RELATIVE_STRENGTH")),
                "can_slim_score":   safe_float(r.get("CAN_SLIM_SCORE")),
                "minervini_score":  safe_float(r.get("MINERVINI_SCORE")),
                "enhanced_fund_score":safe_float(r.get("ENHANCED_FUND_SCORE")),
                "trend_signal":     str(r.get("TREND_SIGNAL","")).strip() or None,
                "trading_signal":   str(r.get("TRADING_SIGNAL","")).strip() or None,
                "trading_value":    safe_float(r.get("TRADING_VALUE")),
            })
        if not dry_run and rows:
            upsert(cur, "scores.sector_top_stocks", rows, ["score_date","sector_name","symbol"])


# ---------------------------------------------------------------------------
# 5. SIGNALS — signal_log, FII/DII, regime, bulk/block, corporate, insider
# ---------------------------------------------------------------------------

def load_signals(cur, dry_run=False):
    print("\n[5/8] SIGNALS — Signal Log, FII/DII, Regime, Deals, Events, Insider")

    # --- signal_log ---
    sig = DATA / "signal_log.csv"
    if sig.exists():
        df = pd.read_csv(sig, low_memory=False)
        rows = []
        for _, r in df.iterrows():
            sym = str(r.get("symbol","")).strip()
            dt  = norm_date(r.get("date_issued"))
            if not sym or not dt:
                continue
            rows.append({
                "date_issued":      dt,
                "symbol":           sym,
                "sector":           str(r.get("sector","")).strip() or None,
                "company":          str(r.get("company","")).strip() or None,
                "signal":           str(r.get("signal","")).strip() or None,
                "setup_class":      str(r.get("setup_class","")).strip() or None,
                "investment_score": safe_float(r.get("investment_score")),
                "technical_score":  safe_float(r.get("technical_score")),
                "rsi":              safe_float(r.get("rsi")),
                "supertrend_state": str(r.get("supertrend_state","")).strip() or None,
                "price_at_issue":   safe_float(r.get("price_at_issue")),
                "entry_low":        safe_float(r.get("entry_low")),
                "entry_high":       safe_float(r.get("entry_high")),
                "stop_loss":        safe_float(r.get("stop_loss")),
                "target_1":         safe_float(r.get("target_1")),
                "target_2":         safe_float(r.get("target_2")),
                "regime_at_issue":  str(r.get("regime_at_issue","")).strip() or None,
                "fno_pcr":          safe_float(r.get("fno_pcr")),
                "fno_oi_change_5d": safe_float(r.get("fno_oi_change_5d")),
                "fno_buildup":      str(r.get("fno_buildup","")).strip() or None,
                "fno_signal":       str(r.get("fno_signal","")).strip() or None,
                "fii_flow_signal":  str(r.get("fii_flow_signal","")).strip() or None,
                "insider_alert":    str(r.get("insider_alert","")).strip() or None,
                "insider_score":    safe_float(r.get("insider_score")),
                "insider_detail":   str(r.get("insider_detail","")).strip() or None,
                "date_resolved":    norm_date(r.get("date_resolved")),
                "price_at_resolution":safe_float(r.get("price_at_resolution")),
                "return_pct":       safe_float(r.get("return_pct")),
                "hit_target":       safe_bool(r.get("hit_target")),
                "hit_stop":         safe_bool(r.get("hit_stop")),
                "action_bucket":    str(r.get("action_bucket","")).strip() or None,
                "action_reason":    str(r.get("action_reason","")).strip() or None,
            })
        if not dry_run and rows:
            upsert(cur, "signals.signal_log", rows, ["date_issued","symbol"],
                   ["signal","investment_score","return_pct","hit_target","hit_stop"])
        log(f"signals.signal_log: {len(rows)} rows")

    # --- FII/DII flows ---
    fii = DATA / "fii_dii_flows.csv"
    if fii.exists():
        df = pd.read_csv(fii, low_memory=False)
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
                "flow_signal":   str(r.get("flow_signal","")).strip() or None,
                "fii_trend":     str(r.get("fii_trend","")).strip() or None,
                "dii_trend":     str(r.get("dii_trend","")).strip() or None,
                "days_in_window":safe_int(r.get("days_in_window")),
            })
        if not dry_run and rows:
            upsert(cur, "signals.fii_dii_flows", rows, ["trade_date"],
                   ["fii_net_today","dii_net_today","flow_signal"])
        log(f"signals.fii_dii_flows: {len(rows)} rows")

    # --- regime history ---
    reg = DATA / "regime_history.csv"
    if reg.exists():
        df = pd.read_csv(reg, low_memory=False)
        rows = []
        for _, r in df.iterrows():
            dt = norm_date(r.get("date"))
            if not dt:
                continue
            rows.append({
                "trade_date": dt,
                "regime":     str(r.get("regime","")).strip() or None,
            })
        if not dry_run and rows:
            upsert(cur, "signals.regime_history", rows, ["trade_date"], ["regime"])
        log(f"signals.regime_history: {len(rows)} rows")

    # --- bulk & block deals from _insider_cache ---
    n_deals = 0
    for f in sorted((DATA / "_insider_cache").glob("*.csv")):
        deal_type = "BULK_DEAL" if "bulk" in f.name else "BLOCK_DEAL"
        df = pd.read_csv(f, low_memory=False)
        rows = []
        for _, r in df.iterrows():
            sym = str(r.get("SYMBOL","")).strip()
            dt  = norm_date(r.get("DATE"))
            if not sym or not dt:
                continue
            rows.append({
                "deal_date":    dt,
                "symbol":       sym,
                "security_name":str(r.get("Security Name","")).strip() or None,
                "entity":       str(r.get("ENTITY","")).strip() or None,
                "side":         str(r.get("SIDE","")).strip() or None,
                "qty":          safe_int(r.get("QTY")),
                "price":        safe_float(r.get("PRICE")),
                "deal_type":    deal_type,
                "remarks":      str(r.get("Remarks","")).strip() or None,
                "source":       deal_type,
            })
        if not dry_run and rows:
            upsert(cur, "signals.bulk_block_deals", rows,
                   ["deal_date","symbol","entity","side","deal_type"])
        n_deals += len(rows)
    log(f"signals.bulk_block_deals (_insider_cache): {n_deals} rows")

    # --- corporate events ---
    ce = DATA / "corporate_events.csv"
    if ce.exists():
        df = pd.read_csv(ce, low_memory=False)
        rows = []
        for _, r in df.iterrows():
            sym = str(r.get("SYMBOL","")).strip()
            if not sym:
                continue
            rows.append({
                "symbol":     sym,
                "event_type": str(r.get("EVENT_TYPE","")).strip() or None,
                "event_date": norm_date(r.get("EVENT_DATE")),
                "purpose_raw":str(r.get("PURPOSE_RAW","")).strip() or None,
                "detail":     str(r.get("DETAIL","")).strip() or None,
                "source":     str(r.get("SOURCE","")).strip() or None,
            })
        if not dry_run and rows:
            upsert(cur, "signals.corporate_events", rows,
                   ["symbol","event_type","event_date"])
        log(f"signals.corporate_events: {len(rows)} rows")

    # --- insider alerts ---
    ia = DATA / "insider_alerts.csv"
    if ia.exists():
        df = pd.read_csv(ia, low_memory=False)
        rows = []
        today = str(date.today())
        for _, r in df.iterrows():
            sym = str(r.get("SYMBOL","")).strip()
            if not sym:
                continue
            rows.append({
                "alert_date": norm_date(r.get("DATE")) or today,
                "symbol":     sym,
                "alert_type": str(r.get("ALERT_TYPE","")).strip() or None,
                "entity":     str(r.get("ENTITY","")).strip() or None,
                "qty":        safe_int(r.get("QTY")),
                "value_cr":   safe_float(r.get("VALUE_CR")),
                "category":   str(r.get("CATEGORY","")).strip() or None,
                "detail":     str(r.get("DETAIL","")).strip() or None,
                "source":     str(r.get("SOURCE","")).strip() or None,
            })
        # insider_alerts_agg — has score
        ia_agg = DATA / "insider_alerts_agg.csv"
        score_map = {}
        if ia_agg.exists():
            df2 = pd.read_csv(ia_agg, low_memory=False)
            for _, r2 in df2.iterrows():
                s = str(r2.get("SYMBOL","")).strip()
                sc = safe_float(r2.get("INSIDER_SCORE"))
                if s and sc is not None:
                    score_map[s] = sc
        for row in rows:
            row["insider_score"] = score_map.get(row["symbol"])
        if not dry_run and rows:
            upsert(cur, "signals.insider_alerts", rows,
                   ["alert_date","symbol","entity","alert_type"])
        log(f"signals.insider_alerts: {len(rows)} rows")


# ---------------------------------------------------------------------------
# 6. BREADTH
# ---------------------------------------------------------------------------

def load_breadth(cur, dry_run=False):
    print("\n[6/8] BREADTH — Market Daily, Sector Daily")

    # --- nse_analysis.db market_breadth ---
    for db_path in [DATA / "nse_analysis.db", BASE / "nse_analysis.db"]:
        if not db_path.exists():
            continue
        conn = sqlite3.connect(db_path)
        df = pd.read_sql("SELECT * FROM market_breadth", conn)
        conn.close()
        rows = []
        for _, r in df.iterrows():
            dt = norm_date(r.get("analysis_date"))
            if not dt:
                continue
            rows.append({
                "trade_date":        dt,
                "total_stocks":      safe_int(r.get("total_stocks")),
                "strong_buy_count":  safe_int(r.get("strong_buy_count")),
                "buy_count":         safe_int(r.get("buy_count")),
                "hold_count":        safe_int(r.get("hold_count")),
                "weak_hold_count":   safe_int(r.get("weak_hold_count")),
                "sell_count":        safe_int(r.get("sell_count")),
                "bullish_pct":       safe_float(r.get("bullish_percentage")),
                "bearish_pct":       safe_float(r.get("bearish_percentage")),
                "avg_technical_score":safe_float(r.get("average_technical_score")),
                "market_sentiment":  str(r.get("market_sentiment","")).strip() or None,
            })
        if not dry_run and rows:
            upsert(cur, "breadth.market_daily", rows, ["trade_date"],
                   ["total_stocks","strong_buy_count","buy_count","market_sentiment"])
        log(f"breadth.market_daily (nse_analysis.db): {len(rows)} rows")
        break

    # --- breadth_history.csv ---
    bh = DATA / "breadth_history.csv"
    if bh.exists():
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
                "ad_signal":      str(r.get("signal","")).strip() or None,
                "adv_volume":     safe_int(r.get("adv_volume")),
                "dec_volume":     safe_int(r.get("dec_volume")),
                "trin":           safe_float(r.get("trin")),
                "trin_5d":        safe_float(r.get("trin_5d")),
                "trin_signal":    str(r.get("trin_signal","")).strip() or None,
                "trin_5d_signal": str(r.get("trin_5d_signal","")).strip() or None,
                "divergence":     str(r.get("divergence","")).strip() or None,
                "nifty500_close": safe_float(r.get("nifty500_close")),
                "generated_at":   str(r.get("generated_at","")).strip() or None,
            })
        if not dry_run and rows:
            upsert(cur, "breadth.market_daily", rows, ["trade_date"],
                   ["advances","declines","net_ad","ad_oscillator","trin","trin_signal"])
        log(f"breadth.market_daily (breadth_history.csv): {len(rows)} rows")

    # --- sector_breadth.csv ---
    sb = DATA / "sector_breadth.csv"
    if sb.exists():
        df = pd.read_csv(sb, low_memory=False)
        today = str(date.today())
        rows = []
        for _, r in df.iterrows():
            sect = str(r.get("sector","")).strip()
            dt   = norm_date(r.get("as_of_date")) or today
            if not sect:
                continue
            rows.append({
                "snapshot_date":  dt,
                "sector":         sect,
                "index_name":     str(r.get("index_name","")).strip() or None,
                "pct_above_50dma":safe_float(r.get("pct_above_50dma")),
                "change_5d":      safe_float(r.get("change_5d")),
                "breadth_signal": str(r.get("breadth_signal","")).strip() or None,
                "divergence_alert":str(r.get("divergence_alert","")).strip() or None,
            })
        if not dry_run and rows:
            upsert(cur, "breadth.sector_daily", rows, ["snapshot_date","sector"])
        log(f"breadth.sector_daily: {len(rows)} rows")


# ---------------------------------------------------------------------------
# 7. MACRO
# ---------------------------------------------------------------------------

def load_macro(cur, dry_run=False):
    print("\n[7/8] MACRO — FRED Series, Indicators, Correlations, Tailwinds, Seasonal")

    # --- FRED series ---
    n_fred = 0
    for f in sorted((DATA / "_macro_cache").glob("fred_*.csv")):
        series_id = f.stem.replace("fred_","")
        df = pd.read_csv(f, low_memory=False)
        rows = []
        for _, r in df.iterrows():
            dt = norm_date(r.get("observation_date"))
            v  = safe_float(r.get(series_id))
            if not dt or v is None:
                continue
            rows.append({"series_id": series_id, "observation_date": dt, "value": v})
        if not dry_run and rows:
            upsert(cur, "macro.fred_series", rows, ["series_id","observation_date"], ["value"])
        n_fred += len(rows)
    log(f"macro.fred_series: {n_fred} rows")

    # --- macro_proxy_signals.csv ---
    mp = DATA / "macro_proxy_signals.csv"
    if mp.exists():
        df = pd.read_csv(mp, low_memory=False)
        today = str(date.today())
        rows = []
        for _, r in df.iterrows():
            ind = str(r.get("indicator","")).strip()
            dt  = norm_date(r.get("date")) or today
            if not ind:
                continue
            rows.append({
                "snapshot_date": dt,
                "indicator":     ind,
                "series_id":     str(r.get("series_id","")).strip() or None,
                "frequency":     str(r.get("frequency","")).strip() or None,
                "latest_value":  safe_float(r.get("latest_value")),
                "latest_date":   norm_date(r.get("latest_date")),
                "trend":         str(r.get("trend","")).strip() or None,
                "momentum_1m_pct":safe_float(r.get("momentum_1m_pct")),
                "momentum_3m_pct":safe_float(r.get("momentum_3m_pct")),
                "z_score":       safe_float(r.get("z_score")),
                "signal_score":  safe_float(r.get("signal_score")),
            })
        if not dry_run and rows:
            upsert(cur, "macro.indicators", rows, ["snapshot_date","indicator"], ["latest_value","trend"])
        log(f"macro.indicators: {len(rows)} rows")

    # --- global_correlations.csv ---
    gc = DATA / "global_correlations.csv"
    if gc.exists():
        df = pd.read_csv(gc, low_memory=False)
        today = str(date.today())
        rows = []
        for _, r in df.iterrows():
            asset = str(r.get("asset","")).strip()
            if not asset:
                continue
            rows.append({
                "snapshot_date": today,
                "asset":         asset,
                "price":         safe_float(r.get("price")),
                "corr_30d":      safe_float(r.get("corr_30d")),
                "corr_60d":      safe_float(r.get("corr_60d")),
                "change_pct":    safe_float(r.get("change")),
                "alert":         str(r.get("alert","")).strip() or None,
            })
        if not dry_run and rows:
            upsert(cur, "macro.global_correlations", rows,
                   ["snapshot_date","asset"], ["price","corr_30d","corr_60d"])
        log(f"macro.global_correlations: {len(rows)} rows")

    # --- macro_sector_tailwind.csv ---
    mt = DATA / "macro_sector_tailwind.csv"
    if mt.exists():
        df = pd.read_csv(mt, low_memory=False)
        today = str(date.today())
        rows = []
        for _, r in df.iterrows():
            sect = str(r.get("SECTOR_NAME","")).strip()
            if not sect:
                continue
            rows.append({
                "snapshot_date": today,
                "sector_name":   sect,
                "macro_tailwind":str(r.get("MACRO_TAILWIND","")).strip() or None,
                "macro_detail":  str(r.get("MACRO_DETAIL","")).strip() or None,
            })
        if not dry_run and rows:
            upsert(cur, "macro.sector_tailwinds", rows,
                   ["snapshot_date","sector_name"], ["macro_tailwind","macro_detail"])
        log(f"macro.sector_tailwinds: {len(rows)} rows")

    # --- seasonal_monthly_returns.csv ---
    sr = DATA / "seasonal_monthly_returns.csv"
    if sr.exists():
        df = pd.read_csv(sr, low_memory=False)
        rows = []
        for _, r in df.iterrows():
            sym = str(r.get("symbol","")).strip()
            per = str(r.get("period","")).strip()
            if not sym or not per:
                continue
            rows.append({
                "symbol":     sym,
                "period":     per,
                "month_num":  safe_int(r.get("month_num")),
                "close":      safe_float(r.get("CLOSE")),
                "return_pct": safe_float(r.get("return_pct")),
            })
        if not dry_run and rows:
            upsert(cur, "macro.seasonal_returns", rows, ["symbol","period"], ["return_pct"])
        log(f"macro.seasonal_returns: {len(rows)} rows")


# ---------------------------------------------------------------------------
# 8. COMPANY INTELLIGENCE
# ---------------------------------------------------------------------------

def load_company_intel_schema(cur, dry_run=False):
    print("\n[8/9] COMPANY INTELLIGENCE — PostgreSQL schema")
    migrations_dir = BASE / "postgres" / "migrations"
    migration_paths = sorted(migrations_dir.glob("*company_intel*.sql"))
    if not migration_paths:
        raise FileNotFoundError(f"No company_intel migrations found under {migrations_dir}")
    sql = "\n\n".join(path.read_text(encoding="utf-8") for path in migration_paths)
    if not dry_run:
        cur.execute(sql)
    log("company_intel schema: ready")


# ---------------------------------------------------------------------------
# 9. PORTFOLIO
# ---------------------------------------------------------------------------

def load_portfolio(cur, dry_run=False):
    print("\n[9/9] PORTFOLIO — Holdings")
    h = DATA / "holdings.csv"
    if h.exists():
        df = pd.read_csv(h, low_memory=False)
        rows = []
        for _, r in df.iterrows():
            sym = str(r.get("symbol","")).strip()
            if not sym:
                continue
            rows.append({
                "symbol":   sym,
                "qty":      safe_float(r.get("qty")),
                "avg_cost": safe_float(r.get("avg_cost")),
                "buy_date": norm_date(r.get("buy_date")),
            })
        if not dry_run and rows:
            for row in rows:
                try:
                    cur.execute(
                        "INSERT INTO portfolio.holdings (symbol, qty, avg_cost, buy_date) "
                        "VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                        (row["symbol"], row["qty"], row["avg_cost"], row["buy_date"])
                    )
                except Exception:
                    pass
        log(f"portfolio.holdings: {len(rows)} rows")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

SECTIONS = {
    "ref":         load_ref,
    "market":      load_market,
    "derivatives": load_derivatives,
    "scores":      load_scores,
    "signals":     load_signals,
    "breadth":     load_breadth,
    "macro":       load_macro,
    "company_intel": load_company_intel_schema,
    "portfolio":   load_portfolio,
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--section", choices=list(SECTIONS.keys()),
                    help="Load only one section")
    ap.add_argument("--dry-run", action="store_true",
                    help="Validate parsing only, no DB writes")
    args = ap.parse_args()

    print(f"NSE PostgreSQL Migration — {'DRY RUN' if args.dry_run else 'LIVE'}")
    print(f"Project root: {BASE}")
    print(f"PostgreSQL: {PG_DSN}\n")

    conn = pg()
    conn.autocommit = False
    cur  = conn.cursor()

    sections = {args.section: SECTIONS[args.section]} if args.section else SECTIONS

    try:
        for name, fn in sections.items():
            fn(cur, dry_run=args.dry_run)
            if not args.dry_run:
                conn.commit()
                print(f"  ✓ {name} committed")

        if not args.dry_run:
            print("\nRefreshing materialized views…")
            cur.execute("SELECT refresh_all_views()")
            conn.commit()
            print("✓ All views refreshed")

    except Exception as e:
        conn.rollback()
        print(f"\nERROR: {e}")
        import traceback; traceback.print_exc()
        sys.exit(1)
    finally:
        cur.close()
        conn.close()

    print("\n✅ Migration complete.")


if __name__ == "__main__":
    main()
