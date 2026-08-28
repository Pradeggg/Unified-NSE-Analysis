"""
terminal/fno_data.py
────────────────────
F&O Data Layer for Agent Adda.

Provides:
  • EOD F&O Bhavcopy download + PostgreSQL persistence
  • Live NSE option-chain scraper (requires browser-like session)
  • Live futures chain fetcher
  • Utility helpers: lot sizes, expiry calendar, rollover dates
"""

from __future__ import annotations

import io
import json
import logging
import os
import sqlite3
import time
import warnings
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import requests

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────────────────────────────────────
ROOT    = Path(__file__).resolve().parent.parent
DATA    = ROOT / "data"
FNO_DIR = DATA / "fno"
FNO_DIR.mkdir(parents=True, exist_ok=True)

FNO_DB  = FNO_DIR / "fno_eod.db"
PG_DSN  = (
    os.environ.get("AGENT_ADDA_PG_DSN")
    or os.environ.get("PG_DSN")
    or "dbname=nse_market user=nse_admin host=/tmp"
)

# ─────────────────────────────────────────────────────────────────────────────
# NSE HTTP Session (cookie-based auth)
# ─────────────────────────────────────────────────────────────────────────────
_NSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept":          "*/*",
    "Accept-Encoding": "gzip, deflate",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection":      "keep-alive",
    "Referer":         "https://www.nseindia.com/option-chain",
}
_ARCHIVE_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer":    "https://nsearchives.nseindia.com/",
}

_nse_session: requests.Session | None = None


def _get_nse_session(force_refresh: bool = False) -> requests.Session:
    """Return a cookie-seeded NSE session (cached)."""
    global _nse_session
    if _nse_session and not force_refresh:
        return _nse_session

    s = requests.Session()
    s.headers.update(_NSE_HEADERS)
    try:
        s.get("https://www.nseindia.com", timeout=10)
        time.sleep(0.5)
        s.get("https://www.nseindia.com/option-chain", timeout=10)
        time.sleep(0.5)
    except Exception:
        pass  # proceed even if seed page fails

    _nse_session = s
    return s


# ─────────────────────────────────────────────────────────────────────────────
# SQLite helpers
# ─────────────────────────────────────────────────────────────────────────────
def _db_conn() -> sqlite3.Connection:
    return sqlite3.connect(FNO_DB)


def _legacy_sqlite_fallbacks_enabled() -> bool:
    return os.environ.get("AGENT_ADDA_ENABLE_SQLITE_FALLBACKS", "").strip().lower() in {"1", "true", "yes"}


def _pg_conn():
    import psycopg2
    return psycopg2.connect(PG_DSN)


def _pg_read_sql(sql: str, params: tuple[Any, ...] = ()) -> pd.DataFrame:
    try:
        conn = _pg_conn()
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                return pd.read_sql_query(sql, conn, params=params)
        finally:
            conn.close()
    except Exception:
        return pd.DataFrame()


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS fno_eod (
        trade_date    TEXT NOT NULL,
        symbol        TEXT NOT NULL,
        expiry_date   TEXT NOT NULL,
        instrument    TEXT NOT NULL,   -- STF/STO/IDO/IDF
        option_type   TEXT,            -- CE / PE / NULL for futures
        strike        REAL,
        open          REAL,
        high          REAL,
        low           REAL,
        close         REAL,
        last_price    REAL,
        prev_close    REAL,
        settle_price  REAL,
        underlying    REAL,
        oi            INTEGER,
        oi_change     INTEGER,
        volume        INTEGER,
        turnover_cr   REAL,
        PRIMARY KEY (trade_date, symbol, expiry_date, instrument, option_type, strike)
    );

    CREATE INDEX IF NOT EXISTS idx_fno_date   ON fno_eod(trade_date);
    CREATE INDEX IF NOT EXISTS idx_fno_symbol ON fno_eod(symbol, trade_date);
    CREATE INDEX IF NOT EXISTS idx_fno_expiry ON fno_eod(symbol, expiry_date, trade_date);
    """)
    conn.commit()


# ─────────────────────────────────────────────────────────────────────────────
# EOD Bhavcopy Download
# ─────────────────────────────────────────────────────────────────────────────
def _bhavcopy_url(d: date) -> str:
    return (
        f"https://nsearchives.nseindia.com/content/fo/"
        f"BhavCopy_NSE_FO_0_0_0_{d.strftime('%Y%m%d')}_F_0000.csv.zip"
    )


def _last_n_trading_days(n: int = 5) -> list[date]:
    """Return the last n calendar dates (exchange may still be closed; caller validates)."""
    days, d = [], date.today()
    while len(days) < n:
        d -= timedelta(days=1)
        if d.weekday() < 5:          # Mon-Fri
            days.append(d)
    return days


def download_fno_bhavcopy(trade_date: date | None = None) -> pd.DataFrame | None:
    """
    Download F&O EOD bhavcopy for a given date (defaults to latest available).
    Returns a normalised DataFrame or None on failure.
    """
    candidates = [trade_date] if trade_date else _last_n_trading_days(7)

    for d in candidates:
        url = _bhavcopy_url(d)
        cache_csv = FNO_DIR / f"fno_bhavcopy_{d.strftime('%Y%m%d')}.csv"

        # Return from cache if present
        if cache_csv.exists():
            logger.info(f"Loading F&O bhavcopy from cache: {cache_csv.name}")
            return _normalise_bhavcopy(pd.read_csv(cache_csv))

        try:
            r = requests.get(url, headers=_ARCHIVE_HEADERS, timeout=30)
            if r.status_code == 404:
                continue
            r.raise_for_status()

            z = zipfile.ZipFile(io.BytesIO(r.content))
            df = pd.read_csv(z.open(z.namelist()[0]))
            df.to_csv(cache_csv, index=False)          # cache for reuse
            logger.info(f"Downloaded F&O bhavcopy for {d}: {len(df)} rows")
            return _normalise_bhavcopy(df)

        except Exception as exc:
            logger.warning(f"Bhavcopy download failed for {d}: {exc}")
            continue

    return None


def _normalise_bhavcopy(df: pd.DataFrame) -> pd.DataFrame:
    """Standardise raw NSE bhavcopy column names."""
    col_map = {
        "TradDt":          "trade_date",
        "TckrSymb":        "symbol",
        "XpryDt":          "expiry_date",
        "FinInstrmTp":     "instrument",
        "OptnTp":          "option_type",
        "StrkPric":        "strike",
        "OpnPric":         "open",
        "HghPric":         "high",
        "LwPric":          "low",
        "ClsPric":         "close",
        "LastPric":        "last_price",
        "PrvsClsgPric":    "prev_close",
        "SttlmPric":       "settle_price",
        "UndrlygPric":     "underlying",
        "OpnIntrst":       "oi",
        "ChngInOpnIntrst": "oi_change",
        "TtlTradgVol":     "volume",
        "TtlTrfVal":       "turnover_cr",
    }
    df = df.rename(columns=col_map)

    # Keep only mapped columns that exist
    keep = [v for v in col_map.values() if v in df.columns]
    df = df[keep].copy()

    # Type coercions
    for col in ["strike", "open", "high", "low", "close", "last_price",
                "prev_close", "settle_price", "underlying", "turnover_cr"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    for col in ["oi", "oi_change", "volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    df["trade_date"]  = pd.to_datetime(df["trade_date"],  errors="coerce").dt.strftime("%Y-%m-%d")
    df["expiry_date"] = pd.to_datetime(df["expiry_date"], errors="coerce").dt.strftime("%Y-%m-%d")

    return df.dropna(subset=["trade_date", "symbol"])


def store_fno_bhavcopy(df: pd.DataFrame) -> int:
    """Persist normalised bhavcopy DataFrame to optional legacy SQLite cache."""
    conn = _db_conn()
    _ensure_schema(conn)

    rows = df.to_dict(orient="records")
    inserted = 0
    for row in rows:
        try:
            conn.execute("""
                INSERT OR REPLACE INTO fno_eod
                  (trade_date,symbol,expiry_date,instrument,option_type,strike,
                   open,high,low,close,last_price,prev_close,settle_price,
                   underlying,oi,oi_change,volume,turnover_cr)
                VALUES
                  (:trade_date,:symbol,:expiry_date,:instrument,:option_type,:strike,
                   :open,:high,:low,:close,:last_price,:prev_close,:settle_price,
                   :underlying,:oi,:oi_change,:volume,:turnover_cr)
            """, row)
            inserted += 1
        except Exception:
            pass
    conn.commit()
    conn.close()
    return inserted


def _store_fno_bhavcopy_pg(df: pd.DataFrame) -> int:
    """Persist normalised bhavcopy DataFrame to partitioned PostgreSQL."""
    if df.empty:
        return 0
    try:
        from psycopg2.extras import execute_values
        conn = _pg_conn()
    except Exception:
        return 0

    rows = []
    for _, r in df.iterrows():
        trade_date = r.get("trade_date")
        symbol = str(r.get("symbol") or "").strip().upper()
        expiry_date = r.get("expiry_date")
        instrument = str(r.get("instrument") or "").strip()
        option_type_raw = str(r.get("option_type") or "").strip()
        option_type = "FUT" if option_type_raw.lower() in ("", "nan", "none", "na", "null") else option_type_raw
        if not trade_date or not symbol or not expiry_date or not instrument:
            continue
        turnover = pd.to_numeric(pd.Series([r.get("turnover_cr")]), errors="coerce").iloc[0]
        rows.append({
            "trade_date": trade_date,
            "symbol": symbol,
            "expiry_date": expiry_date,
            "instrument": instrument,
            "option_type": option_type,
            "strike": float(r.get("strike") or 0),
            "open": r.get("open"),
            "high": r.get("high"),
            "low": r.get("low"),
            "close": r.get("close"),
            "last_price": r.get("last_price"),
            "prev_close": r.get("prev_close"),
            "underlying_price": r.get("underlying"),
            "settle_price": r.get("settle_price"),
            "open_interest": int(r.get("oi") or 0),
            "oi_change": int(r.get("oi_change") or 0),
            "volume": int(r.get("volume") or 0),
            "turnover_cr": round(float(turnover) / 1e7, 4) if pd.notna(turnover) else None,
            "total_trades": None,
            "lot_size": None,
        })
    if not rows:
        conn.close()
        return 0

    cols = list(rows[0].keys())
    values = [[row.get(col) for col in cols] for row in rows]
    sql = (
        f"INSERT INTO derivatives.fno_eod ({', '.join(cols)}) VALUES %s "
        "ON CONFLICT ON CONSTRAINT fno_eod_pkey DO UPDATE SET "
        "open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low, "
        "close = EXCLUDED.close, last_price = EXCLUDED.last_price, "
        "prev_close = EXCLUDED.prev_close, underlying_price = EXCLUDED.underlying_price, "
        "settle_price = EXCLUDED.settle_price, open_interest = EXCLUDED.open_interest, "
        "oi_change = EXCLUDED.oi_change, volume = EXCLUDED.volume, turnover_cr = EXCLUDED.turnover_cr"
    )
    try:
        with conn, conn.cursor() as cur:
            for trade_date in sorted({row["trade_date"] for row in rows}):
                cur.execute("SELECT derivatives.ensure_fno_monthly_partition(%s)", (trade_date,))
            execute_values(cur, sql, values, page_size=500)
            cur.execute("SELECT derivatives.refresh_fno_analytics()")
    except Exception:
        return 0
    finally:
        conn.close()
    return len(rows)


def load_and_store_latest() -> dict:
    """Download latest bhavcopy and store in PostgreSQL."""
    df = download_fno_bhavcopy()
    if df is None:
        return {"status": "error", "message": "Could not download F&O bhavcopy"}

    n = store_fno_bhavcopy(df) if _legacy_sqlite_fallbacks_enabled() else 0
    pg_n = _store_fno_bhavcopy_pg(df)
    td = df["trade_date"].iloc[0] if not df.empty else "unknown"
    return {
        "status": "ok",
        "trade_date": td,
        "rows_stored": pg_n or n,
        "postgres_rows_stored": pg_n,
        "sqlite_rows_stored": n,
        "options": int((df["option_type"].fillna("").astype(str).str.upper().isin(["CE", "PE"])).sum()),
        "futures": int((~df["option_type"].fillna("").astype(str).str.upper().isin(["CE", "PE"])).sum()),
    }


# ─────────────────────────────────────────────────────────────────────────────
# EOD DB Queries
# ─────────────────────────────────────────────────────────────────────────────
def get_available_dates() -> list[str]:
    pg_df = _pg_read_sql(
        "SELECT DISTINCT trade_date::text AS trade_date "
        "FROM derivatives.fno_eod ORDER BY trade_date DESC LIMIT 30"
    )
    if not pg_df.empty:
        return pg_df["trade_date"].astype(str).tolist()

    if not _legacy_sqlite_fallbacks_enabled() or not FNO_DB.exists():
        return []
    conn = _db_conn()
    rows = conn.execute(
        "SELECT DISTINCT trade_date FROM fno_eod ORDER BY trade_date DESC LIMIT 30"
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]


def get_eod_option_chain(symbol: str, trade_date: str | None = None,
                          expiry_date: str | None = None) -> pd.DataFrame:
    """
    Fetch EOD option chain from PostgreSQL for a symbol.
    Returns CE + PE rows for the given expiry (nearest if not specified).
    Legacy SQLite fallback is disabled by default; set
    AGENT_ADDA_ENABLE_SQLITE_FALLBACKS=1 to opt in.
    """
    sym = symbol.upper()
    pg_params: list[Any] = [sym]
    pg_where = ["symbol = %s", "option_type IN ('CE','PE')"]
    if trade_date:
        pg_where.append("trade_date = %s")
        pg_params.append(trade_date)
    else:
        pg_where.append("trade_date = (SELECT max(trade_date) FROM derivatives.fno_eod)")
    if expiry_date:
        pg_where.append("expiry_date = %s")
        pg_params.append(expiry_date)
    else:
        pg_where.append(
            "expiry_date = ("
            "SELECT min(expiry_date) FROM derivatives.fno_eod "
            "WHERE symbol = %s AND option_type IN ('CE','PE') "
            "AND trade_date = COALESCE(%s::date, (SELECT max(trade_date) FROM derivatives.fno_eod)) "
            "AND expiry_date >= trade_date)"
        )
        pg_params.extend([sym, trade_date])
    pg_df = _pg_read_sql(
        """
        SELECT
            trade_date::text AS trade_date,
            symbol,
            expiry_date::text AS expiry_date,
            instrument,
            option_type,
            strike,
            open,
            high,
            low,
            close,
            last_price,
            prev_close,
            settle_price,
            underlying_price AS underlying,
            open_interest AS oi,
            oi_change,
            volume,
            turnover_cr,
            lot_size
        FROM derivatives.fno_eod
        WHERE """ + " AND ".join(pg_where) + """
        ORDER BY strike, option_type
        """,
        tuple(pg_params),
    )
    if not pg_df.empty:
        return pg_df

    if not _legacy_sqlite_fallbacks_enabled() or not FNO_DB.exists():
        return pd.DataFrame()

    conn = _db_conn()
    dates = get_available_dates()
    if not dates:
        conn.close()
        return pd.DataFrame()

    td = trade_date or dates[0]

    # Find nearest expiry if not specified
    if not expiry_date:
        expiry_rows = conn.execute(
            "SELECT DISTINCT expiry_date FROM fno_eod "
            "WHERE symbol=? AND trade_date=? AND option_type IS NOT NULL "
            "ORDER BY expiry_date", (symbol.upper(), td)
        ).fetchall()
        if not expiry_rows:
            conn.close()
            return pd.DataFrame()
        expiry_date = expiry_rows[0][0]

    df = pd.read_sql_query("""
        SELECT * FROM fno_eod
        WHERE symbol=? AND trade_date=? AND expiry_date=?
          AND option_type IN ('CE','PE')
        ORDER BY strike, option_type
    """, conn, params=(symbol.upper(), td, expiry_date))
    conn.close()
    return df


def get_eod_futures(symbol: str, trade_date: str | None = None) -> pd.DataFrame:
    """Fetch EOD futures rows for a symbol (all expiries)."""
    sym = symbol.upper()
    pg_params: list[Any] = [sym]
    pg_where = ["symbol = %s", "instrument IN ('STF','IDF','FUTSTK','FUTIDX')", "option_type = 'FUT'"]
    if trade_date:
        pg_where.append("trade_date = %s")
        pg_params.append(trade_date)
    else:
        pg_where.append("trade_date = (SELECT max(trade_date) FROM derivatives.fno_eod)")
    pg_df = _pg_read_sql(
        """
        SELECT
            trade_date::text AS trade_date,
            symbol,
            expiry_date::text AS expiry_date,
            instrument,
            option_type,
            strike,
            open,
            high,
            low,
            close,
            last_price,
            prev_close,
            settle_price,
            underlying_price AS underlying,
            open_interest AS oi,
            oi_change,
            volume,
            turnover_cr,
            lot_size
        FROM derivatives.fno_eod
        WHERE """ + " AND ".join(pg_where) + """
        ORDER BY expiry_date
        """,
        tuple(pg_params),
    )
    if not pg_df.empty:
        return pg_df

    if not _legacy_sqlite_fallbacks_enabled() or not FNO_DB.exists():
        return pd.DataFrame()

    conn = _db_conn()
    dates = get_available_dates()
    td = trade_date or (dates[0] if dates else "")
    if not td:
        conn.close()
        return pd.DataFrame()

    df = pd.read_sql_query("""
        SELECT * FROM fno_eod
        WHERE symbol=? AND trade_date=? AND option_type IS NULL
        ORDER BY expiry_date
    """, conn, params=(symbol.upper(), td))
    conn.close()
    return df


def get_oi_history(symbol: str, expiry_date: str, option_type: str = "CE",
                   strike: float | None = None, days: int = 10) -> pd.DataFrame:
    """OI history for a specific strike/option to track buildup/unwinding."""
    sym = symbol.upper()
    opt_type = option_type.upper()
    pg_params: list[Any] = [sym, expiry_date, opt_type]
    pg_where = "symbol = %s AND expiry_date = %s AND option_type = %s"
    if strike is not None:
        pg_where += " AND strike = %s"
        pg_params.append(strike)
    pg_df = _pg_read_sql(
        f"""
        SELECT trade_date::text AS trade_date, strike, open_interest AS oi,
               oi_change, volume, last_price, underlying_price AS underlying
        FROM derivatives.fno_eod
        WHERE {pg_where}
        ORDER BY trade_date DESC
        LIMIT {days * 30}
        """,
        tuple(pg_params),
    )
    if not pg_df.empty:
        return pg_df

    if not _legacy_sqlite_fallbacks_enabled() or not FNO_DB.exists():
        return pd.DataFrame()

    conn = _db_conn()
    params: list[Any] = [symbol.upper(), expiry_date, option_type.upper()]
    where = "symbol=? AND expiry_date=? AND option_type=?"
    if strike is not None:
        where += " AND strike=?"
        params.append(strike)

    df = pd.read_sql_query(f"""
        SELECT trade_date, strike, oi, oi_change, volume, last_price, underlying
        FROM fno_eod WHERE {where}
        ORDER BY trade_date DESC LIMIT {days * 30}
    """, conn, params=params)
    conn.close()
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Live Option Chain (NSE API – intraday)
# ─────────────────────────────────────────────────────────────────────────────
_INDEX_SYMBOLS  = {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50", "SENSEX"}


def fetch_live_option_chain(symbol: str, expiry: str | None = None,
                             retries: int = 2) -> dict:
    """
    Fetch live option chain from NSE for an index or stock.
    Returns dict with keys: symbol, underlying, expiry_dates, expiry, data (list of strikes).
    """
    sym = symbol.upper().strip()
    is_index = sym in _INDEX_SYMBOLS

    for attempt in range(retries + 1):
        try:
            sess = _get_nse_session(force_refresh=(attempt > 0))
            chain_type = "Indices" if is_index else "Equity"
            if expiry is None:
                contract_url = f"https://www.nseindia.com/api/option-chain-contract-info?symbol={sym}"
                contract_response = sess.get(contract_url, timeout=20)
                contract_response.raise_for_status()
                contract_info = contract_response.json()
                expiry = (contract_info.get("expiryDates") or [None])[0]
            endpoint = (
                f"https://www.nseindia.com/api/option-chain-v3?type={chain_type}"
                f"&symbol={sym}"
                + (f"&expiry={expiry}" if expiry else "")
            )
            r = sess.get(endpoint, timeout=20)
            if r.status_code == 401 and attempt < retries:
                time.sleep(1)
                continue
            if r.status_code == 404:
                fallback = _live_chain_from_eod(sym, expiry)
                if "error" not in fallback:
                    fallback["live_error"] = "NSE option-chain-v3 endpoint returned 404"
                return fallback
            r.raise_for_status()
            raw = r.json()
        except Exception as exc:
            if attempt < retries:
                time.sleep(1.5)
                continue
            return {"error": f"NSE API error: {exc}", "symbol": sym}

        records = raw.get("records", {})
        underlying = records.get("underlyingValue")

        if underlying is None or not records.get("data"):
            # Market may be closed – fall back to EOD data
            return _live_chain_from_eod(sym, expiry)

        expiry_dates = records.get("expiryDates", [])
        target_expiry = expiry or (expiry_dates[0] if expiry_dates else None)

        rows = []
        for item in records["data"]:
            exp = item.get("expiryDate") or item.get("expiryDates", "")
            if target_expiry and exp != target_expiry:
                continue
            strike = item.get("strikePrice")
            ce = item.get("CE", {})
            pe = item.get("PE", {})
            rows.append({
                "strike":        strike,
                "ce_oi":         ce.get("openInterest", 0),
                "ce_oi_chg":     ce.get("changeinOpenInterest", 0),
                "ce_vol":        ce.get("totalTradedVolume", 0),
                "ce_iv":         ce.get("impliedVolatility", 0),
                "ce_ltp":        ce.get("lastPrice", 0),
                "ce_bid":        ce.get("bidprice", 0),
                "ce_ask":        ce.get("askPrice", 0),
                "ce_delta":      ce.get("delta"),
                "ce_theta":      ce.get("theta"),
                "ce_gamma":      ce.get("gamma"),
                "ce_vega":       ce.get("vega"),
                "pe_oi":         pe.get("openInterest", 0),
                "pe_oi_chg":     pe.get("changeinOpenInterest", 0),
                "pe_vol":        pe.get("totalTradedVolume", 0),
                "pe_iv":         pe.get("impliedVolatility", 0),
                "pe_ltp":        pe.get("lastPrice", 0),
                "pe_bid":        pe.get("bidprice", 0),
                "pe_ask":        pe.get("askPrice", 0),
                "pe_delta":      pe.get("delta"),
                "pe_theta":      pe.get("theta"),
                "pe_gamma":      pe.get("gamma"),
                "pe_vega":       pe.get("vega"),
            })

        return {
            "symbol":       sym,
            "underlying":   underlying,
            "expiry_dates": expiry_dates,
            "expiry":       target_expiry,
            "data":         rows,
            "source":       "live-nse-api",
            "as_of":        datetime.now().strftime("%H:%M:%S"),
        }

    return {"error": "Max retries exceeded", "symbol": sym}


def _live_chain_from_eod(symbol: str, expiry: str | None) -> dict:
    """Fallback: build option-chain-like structure from PostgreSQL EOD data."""
    df = get_eod_option_chain(symbol, expiry_date=expiry)
    if df.empty:
        return {"error": f"No EOD data found for {symbol}", "symbol": symbol, "source": "eod-fallback"}

    rows = []
    strikes = sorted(df["strike"].unique())
    expiry_used = df["expiry_date"].iloc[0] if not df.empty else expiry

    for s in strikes:
        ce_row = df[(df["strike"] == s) & (df["option_type"] == "CE")]
        pe_row = df[(df["strike"] == s) & (df["option_type"] == "PE")]
        rows.append({
            "strike":    s,
            "ce_oi":     int(ce_row["oi"].iloc[0])       if not ce_row.empty else 0,
            "ce_oi_chg": int(ce_row["oi_change"].iloc[0]) if not ce_row.empty else 0,
            "ce_vol":    int(ce_row["volume"].iloc[0])    if not ce_row.empty else 0,
            "ce_ltp":    float(ce_row["last_price"].iloc[0]) if not ce_row.empty else 0,
            "ce_iv":     None,
            "pe_oi":     int(pe_row["oi"].iloc[0])       if not pe_row.empty else 0,
            "pe_oi_chg": int(pe_row["oi_change"].iloc[0]) if not pe_row.empty else 0,
            "pe_vol":    int(pe_row["volume"].iloc[0])    if not pe_row.empty else 0,
            "pe_ltp":    float(pe_row["last_price"].iloc[0]) if not pe_row.empty else 0,
            "pe_iv":     None,
        })

    underlying = float(df["underlying"].iloc[0]) if "underlying" in df.columns and not df.empty else None

    return {
        "symbol":       symbol,
        "underlying":   underlying,
        "expiry_dates": [expiry_used],
        "expiry":       expiry_used,
        "data":         rows,
        "source":       "eod-fallback",
        "as_of":        df["trade_date"].iloc[0] if not df.empty else "N/A",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Live Futures Chain
# ─────────────────────────────────────────────────────────────────────────────
# NSE deprecated /api/quote-derivative in 2025 (returns 404). The current
# endpoint is /api/liveEquity-derivatives?index={slug}, keyed by per-symbol
# index slugs. Index futures use the per-index slug below; **stock futures**
# share a single bulk slug ``stock_fut`` that returns the top-by-volume
# contracts in one payload — we filter client-side and cache briefly to
# avoid hammering NSE when multiple stock symbols are requested in sequence.
_INDEX_FUTURE_SLUGS: dict[str, str] = {
    "NIFTY":      "nse50_fut",
    "BANKNIFTY":  "nifty_bank_fut",
    "FINNIFTY":   "finnifty_fut",
    "MIDCPNIFTY": "niftymidcap_fut",
    "NIFTYNXT50": "niftynxt50_fut",
}

# Bulk stock-futures cache (TTL=30s). Keeps the live payload warm for the
# common case where a compound query asks about several stock futures in
# quick succession.
_STOCK_FUT_BULK_CACHE: dict[str, Any] = {"ts": 0.0, "rows": None}
_STOCK_FUT_BULK_TTL = 30.0


def _fetch_stock_futures_bulk() -> list[dict] | None:
    """Fetch and cache the bulk ``stock_fut`` liveEquity-derivatives payload.

    Returns the raw ``data`` list (every contract row), or ``None`` when
    NSE refuses the request. Cached for ``_STOCK_FUT_BULK_TTL`` seconds.
    """
    cached_ts = _STOCK_FUT_BULK_CACHE["ts"]
    cached_rows = _STOCK_FUT_BULK_CACHE["rows"]
    if cached_rows is not None and (time.time() - cached_ts) < _STOCK_FUT_BULK_TTL:
        return cached_rows

    endpoint = "https://www.nseindia.com/api/liveEquity-derivatives?index=stock_fut"
    try:
        from terminal.tools import _get_live_session
        sess = _get_live_session()
    except Exception:
        sess = _get_nse_session()

    try:
        r = sess.get(endpoint, timeout=15)
        if r.status_code != 200 or not r.text:
            return None
        raw = r.json()
    except Exception:
        return None

    rows = raw.get("data") or []
    if not isinstance(rows, list):
        return None
    _STOCK_FUT_BULK_CACHE["ts"] = time.time()
    _STOCK_FUT_BULK_CACHE["rows"] = rows
    return rows


def _fetch_live_stock_futures(sym: str) -> dict | None:
    """Fetch live stock-futures contracts for ``sym`` from the bulk payload.

    The NSE ``liveEquity-derivatives?index=stock_fut`` endpoint returns the
    most-active stock-futures contracts in a single payload. We filter by
    ``underlying`` so heavily-traded names (RELIANCE, HDFCBANK, TCS, etc.)
    get live prices instead of falling through to EOD. Returns ``None``
    when no rows match — the caller is expected to fall back to EOD.
    """
    rows = _fetch_stock_futures_bulk()
    if not rows:
        return None
    matched = [
        r for r in rows
        if str(r.get("underlying", "")).upper() == sym
        and r.get("instrument") == "Stock Futures"
    ]
    if not matched:
        return None

    futures: list[dict[str, Any]] = []
    underlying: float | None = None
    for row in matched:
        if underlying is None and row.get("underlyingValue") is not None:
            try:
                underlying = float(row.get("underlyingValue"))
            except (TypeError, ValueError):
                pass
        futures.append({
            "expiry":     row.get("expiryDate"),
            "last_price": row.get("lastPrice"),
            "change_pct": row.get("pChange"),
            "oi":         row.get("openInterest"),
            "oi_change":  None,
            "volume":     row.get("volume"),
            "underlying": row.get("underlyingValue"),
        })

    if not futures or underlying is None:
        return None

    return {
        "symbol":     sym,
        "underlying": underlying,
        "futures":    futures,
        "source":     "live-nse-api",
        "as_of":      datetime.now().strftime("%H:%M:%S"),
    }


def _fetch_live_index_futures(sym: str) -> dict | None:
    """Fetch index futures via NSE's modern liveEquity-derivatives endpoint.

    Returns ``None`` if the symbol has no known index slug, the endpoint
    fails, or the response carries no Index Futures rows. The caller is
    expected to fall back to EOD data in that case.
    """
    slug = _INDEX_FUTURE_SLUGS.get(sym)
    if not slug:
        return None

    endpoint = f"https://www.nseindia.com/api/liveEquity-derivatives?index={slug}"

    # The shared cookie-seeded session in this module has historically
    # been brittle for derivatives. Prefer the live-session helper from
    # terminal.tools (warmed against multiple NSE pages) when available.
    sess: requests.Session
    try:
        from terminal.tools import _get_live_session
        sess = _get_live_session()
    except Exception:
        sess = _get_nse_session()

    try:
        r = sess.get(endpoint, timeout=15)
        if r.status_code != 200 or not r.text:
            return None
        raw = r.json()
    except Exception:
        return None

    rows = raw.get("data", []) or []
    futures: list[dict[str, Any]] = []
    underlying: float | None = None

    for row in rows:
        if row.get("instrument") != "Index Futures":
            continue
        if underlying is None and row.get("underlyingValue") is not None:
            try:
                underlying = float(row.get("underlyingValue"))
            except (TypeError, ValueError):
                pass
        futures.append({
            "expiry":     row.get("expiryDate"),
            "last_price": row.get("lastPrice"),
            "change_pct": row.get("pChange"),
            "oi":         row.get("openInterest"),
            # liveEquity-derivatives does not expose changeinOpenInterest;
            # downstream consumers tolerate None / 0.
            "oi_change":  None,
            "volume":     row.get("volume"),
            "underlying": row.get("underlyingValue"),
        })

    if not futures or underlying is None:
        return None

    return {
        "symbol":     sym,
        "underlying": underlying,
        "futures":    futures,
        "source":     "live-nse-api",
        "as_of":      datetime.now().strftime("%H:%M:%S"),
    }


def fetch_live_futures(symbol: str) -> dict:
    """
    Fetch live futures data for a symbol from NSE.
    Falls back to EOD data if the live endpoint is unavailable or
    returns no usable Index Futures rows (e.g. market closed).
    """
    sym = symbol.upper().strip()

    if sym in _INDEX_FUTURE_SLUGS:
        result = _fetch_live_index_futures(sym)
        if result is not None:
            return result
        return _futures_from_eod(sym)

    # Stock futures: try the bulk liveEquity-derivatives?index=stock_fut
    # payload first (covers most-active contracts in a single call).
    # Fall back to EOD when the symbol isn't present in the live payload
    # (illiquid names, market closed, NSE refused, etc.).
    result = _fetch_live_stock_futures(sym)
    if result is not None:
        return result
    return _futures_from_eod(sym)


def _futures_from_eod(symbol: str) -> dict:
    df = get_eod_futures(symbol)
    if df.empty:
        return {"error": f"No futures data for {symbol}", "symbol": symbol}

    futures = []
    for _, row in df.iterrows():
        futures.append({
            "expiry":      row.get("expiry_date"),
            "last_price":  row.get("last_price"),
            "settle_price":row.get("settle_price"),
            "oi":          int(row.get("oi", 0)),
            "oi_change":   int(row.get("oi_change", 0)),
            "volume":      int(row.get("volume", 0)),
            "underlying":  row.get("underlying"),
        })

    underlying = float(df["underlying"].iloc[0]) if "underlying" in df.columns else None
    return {
        "symbol":     symbol,
        "underlying": underlying,
        "futures":    futures,
        "source":     "eod-fallback",
        "as_of":      df["trade_date"].iloc[0] if not df.empty else "N/A",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Lot Size Reference
# ─────────────────────────────────────────────────────────────────────────────
# NSE standard lot sizes (updated periodically)
_LOT_SIZES: dict[str, int] = {
    "NIFTY":       75,
    "BANKNIFTY":   30,
    "FINNIFTY":    40,
    "MIDCPNIFTY":  75,
    "NIFTYNXT50":  25,
    "SENSEX":      10,
}


def get_lot_size(symbol: str) -> int | None:
    """Return the F&O lot size for a symbol (index or stock)."""
    sym = symbol.upper().strip()
    if sym in _LOT_SIZES:
        return _LOT_SIZES[sym]
    pg_df = _pg_read_sql(
        """
        SELECT lot_size
        FROM derivatives.fno_eod
        WHERE symbol=%s AND lot_size IS NOT NULL
        ORDER BY trade_date DESC
        LIMIT 1
        """,
        (sym,),
    )
    if not pg_df.empty and pd.notna(pg_df["lot_size"].iloc[0]):
        return int(pg_df["lot_size"].iloc[0])
    if _legacy_sqlite_fallbacks_enabled() and FNO_DB.exists():
        conn = _db_conn()
        row = conn.execute(
            "SELECT NewBrdLotQty FROM fno_eod WHERE symbol=? LIMIT 1",
            (sym,)
        ).fetchone()
        conn.close()
        if row and row[0]:
            return int(row[0])
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Expiry Calendar
# ─────────────────────────────────────────────────────────────────────────────
def get_expiry_dates(symbol: str) -> list[str]:
    """Return sorted list of available expiry dates from PostgreSQL."""
    pg_df = _pg_read_sql(
        """
        SELECT DISTINCT expiry_date::text AS expiry_date
        FROM derivatives.fno_eod
        WHERE symbol=%s
        ORDER BY expiry_date
        """,
        (symbol.upper(),),
    )
    if not pg_df.empty:
        return pg_df["expiry_date"].astype(str).tolist()
    if not _legacy_sqlite_fallbacks_enabled() or not FNO_DB.exists():
        return []
    conn = _db_conn()
    rows = conn.execute(
        "SELECT DISTINCT expiry_date FROM fno_eod WHERE symbol=? "
        "ORDER BY expiry_date", (symbol.upper(),)
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]


def days_to_expiry(expiry_date_str: str) -> int:
    """Calendar days to expiry from today."""
    try:
        exp = datetime.strptime(expiry_date_str, "%Y-%m-%d").date()
        return max(0, (exp - date.today()).days)
    except ValueError:
        return 0
