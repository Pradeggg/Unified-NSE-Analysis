"""
terminal/tools.py — Read-only tool implementations for the NSE Agent Adda.

Each tool returns a plain dict (JSON-serialisable).  Tools must NOT mutate any
data, execute shell commands, or access the network beyond approved sources.
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

# ── Web research module (screener.in, Yahoo Finance, multi-site search) ───────
from terminal.web_research import (
    scrape_screener_in,
    search_yahoo_finance,
    multi_source_web_search,
    comprehensive_stock_research,
)

# ── Intraday screener engine ──────────────────────────────────────────────────
from terminal.intraday import (
    compute_all as _compute_intraday_all,
    get_intraday_analysis,
    run_intraday_screener as _run_intraday_screener,
    get_intraday_candles,
    key_levels as _intraday_key_levels,
    run_all_signals as _run_intraday_all_signals,
)

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT      = Path(__file__).parent.parent
DB_PATH   = ROOT / "data" / "sector_rotation_tracker.db"
STOCK_CSV = ROOT / "data" / "nse_sec_full_data.csv"
INDEX_CSV = ROOT / "data" / "nse_index_data.csv"
GLOBAL_INDEX_CSV = ROOT / "data" / "global_indices.csv"
GLOBAL_CORR_CSV  = ROOT / "data" / "global_correlations.csv"
REPORTS   = ROOT / "reports"


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _db_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def _latest_snapshot_date() -> str:
    if not DB_PATH.exists():
        return "N/A"
    conn = _db_conn()
    row = conn.execute("SELECT MAX(snapshot_date) FROM stage_snapshots").fetchone()
    conn.close()
    return row[0] if row and row[0] else "N/A"


def _load_price_history(symbol: str, days: int = 400) -> pd.DataFrame:
    if not STOCK_CSV.exists():
        return pd.DataFrame()
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    df = pd.read_csv(
        STOCK_CSV,
        usecols=["SYMBOL", "TIMESTAMP", "OPEN", "HIGH", "LOW", "CLOSE", "TOTTRDQTY"],
        low_memory=False,
    )
    df = df[(df["SYMBOL"] == symbol) & (df["TIMESTAMP"] >= cutoff)]
    df["TIMESTAMP"] = pd.to_datetime(df["TIMESTAMP"])
    for c in ["OPEN", "HIGH", "LOW", "CLOSE", "TOTTRDQTY"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.sort_values("TIMESTAMP")


def _compute_rsi(closes: pd.Series, period: int = 14) -> float:
    if len(closes) < period + 1:
        return float("nan")
    delta = closes.diff().dropna()
    gain  = delta.clip(lower=0).ewm(com=period - 1, adjust=False).mean()
    loss  = (-delta.clip(upper=0)).ewm(com=period - 1, adjust=False).mean()
    rs    = gain / loss.replace(0, 1e-9)
    return round(float(100 - 100 / (1 + rs.iloc[-1])), 1)


def _compute_adx(grp: pd.DataFrame, period: int = 14) -> float:
    if len(grp) < period + 2:
        return 0.0
    h, l, c = grp["HIGH"].values, grp["LOW"].values, grp["CLOSE"].values
    tr  = [max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1])) for i in range(1, len(c))]
    pdm = [max(h[i]-h[i-1], 0) if (h[i]-h[i-1]) > (l[i-1]-l[i]) else 0 for i in range(1, len(h))]
    ndm = [max(l[i-1]-l[i], 0) if (l[i-1]-l[i]) > (h[i]-h[i-1]) else 0 for i in range(1, len(l))]
    atr = pd.Series(tr).ewm(span=period, adjust=False).mean()
    pdi = 100 * pd.Series(pdm).ewm(span=period, adjust=False).mean() / atr.replace(0, 1e-9)
    ndi = 100 * pd.Series(ndm).ewm(span=period, adjust=False).mean() / atr.replace(0, 1e-9)
    dx  = 100 * abs(pdi - ndi) / (pdi + ndi).replace(0, 1e-9)
    return round(float(dx.ewm(span=period, adjust=False).mean().iloc[-1]), 1)


def _compute_macd_signal(closes: pd.Series) -> str:
    if len(closes) < 26:
        return "N/A"
    ema12  = closes.ewm(span=12, adjust=False).mean()
    ema26  = closes.ewm(span=26, adjust=False).mean()
    macd   = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    hist   = float(macd.iloc[-1] - signal.iloc[-1])
    return "bullish" if hist > 0 else "bearish"


def _safe_float(v: Any, digits: int = 2) -> float | None:
    """Return a rounded plain float, or None for missing/non-numeric values."""
    if v is None:
        return None
    try:
        fv = float(v)
    except (TypeError, ValueError):
        return None
    if pd.isna(fv):
        return None
    return round(fv, digits)


def _supertrend(grp: pd.DataFrame, period: int = 10, mult: float = 3.0) -> str | None:
    grp = grp.tail(60)
    if len(grp) < 20:
        return None
    h, l, c = grp["HIGH"].values, grp["LOW"].values, grp["CLOSE"].values
    tr  = [max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1])) for i in range(1, len(c))]
    atr = pd.Series(tr).ewm(span=period, adjust=False).mean().values
    ub  = [(h[i]+l[i])/2 + mult*atr[i-1] for i in range(1, len(c))]
    lb  = [(h[i]+l[i])/2 - mult*atr[i-1] for i in range(1, len(c))]
    st, direction = ub[0], 1
    for i in range(1, len(ub)):
        if c[i] > st:
            direction = 1
            st = lb[i]
        else:
            direction = -1
            st = ub[i]
    return "BUY" if direction == 1 else "SELL"


def _all_symbols_map() -> dict[str, str]:
    """Return {normalized_name: symbol, symbol: symbol} for fuzzy resolution."""
    if not DB_PATH.exists():
        return {}
    conn = _db_conn()
    rows = conn.execute(
        "SELECT DISTINCT symbol, company_name FROM stage_snapshots "
        "WHERE snapshot_date=(SELECT MAX(snapshot_date) FROM stage_snapshots)"
    ).fetchall()
    conn.close()
    mapping: dict[str, str] = {}
    for sym, name in rows:
        mapping[sym.upper()] = sym.upper()
        if name:
            mapping[name.upper()] = sym.upper()
            # Add short tokens: "Reliance Industries" → "RELIANCE"
            tokens = re.sub(r"[^A-Z0-9 ]", "", name.upper()).split()
            for t in tokens:
                if len(t) >= 4:
                    mapping.setdefault(t, sym.upper())
    return mapping


# ─────────────────────────────────────────────────────────────────────────────
# Tool functions (all return dict)
# ─────────────────────────────────────────────────────────────────────────────

def resolve_symbol(query: str) -> dict:
    """Resolve a company name / partial name / alias to its NSE symbol."""
    q = query.strip().upper()
    mapping = _all_symbols_map()

    # Exact match first
    if q in mapping:
        sym = mapping[q]
        return {"symbol": sym, "confidence": "exact", "query": query}

    # Fuzzy: find all keys containing the query as substring
    hits: list[tuple[str, str]] = []  # (matched_key, symbol)
    for key, sym in mapping.items():
        if q in key:
            hits.append((key, sym))

    if hits:
        # Sort by shortest match (most specific)
        hits.sort(key=lambda x: len(x[0]))
        best = hits[0][1]
        return {
            "symbol":     best,
            "confidence": "fuzzy",
            "query":      query,
            "candidates": list({h[1] for h in hits[:5]}),
        }

    return {"symbol": None, "confidence": "none", "query": query,
            "error": f"No NSE symbol found for '{query}'"}


def get_symbol_snapshot(symbol: str) -> dict:
    """Get latest EOD snapshot for a symbol: price, stage, RS, RSI, signals, sector."""
    sym = symbol.upper()
    snap: dict[str, Any] = {"symbol": sym, "data_source": "stage_snapshots DB"}

    if DB_PATH.exists():
        conn = _db_conn()
        row = conn.execute(
            "SELECT company_name, stage, stage_score, investment_score, price, "
            "rsi, relative_strength, change_1d_pct, change_1w_pct, change_1m_pct, "
            "market_cap_cat, sector, trading_signal, trend_signal, supertrend_state, "
            "supertrend_value, technical_score, fundamental_score, narrative, stance "
            "FROM stage_snapshots "
            "WHERE symbol=? AND snapshot_date=(SELECT MAX(snapshot_date) FROM stage_snapshots)",
            (sym,),
        ).fetchone()
        conn.close()
        if row:
            cols = ["company_name","stage","stage_score","investment_score","price",
                    "rsi","relative_strength","change_1d_pct","change_1w_pct","change_1m_pct",
                    "market_cap_cat","sector","trading_signal","trend_signal","supertrend_state",
                    "supertrend_value","technical_score","fundamental_score","narrative","stance"]
            snap.update(dict(zip(cols, row)))
            rs = snap.get("relative_strength")
            if rs is not None:
                snap["rs_pct"] = round(float(rs) * 100, 1)
        else:
            snap["error"] = f"{sym} not found in DB snapshot"

    snap["snapshot_date"] = _latest_snapshot_date()
    return snap


def get_technical_setup(symbol: str, days: int = 400) -> dict:
    """Compute technical indicators for a symbol from price history CSV."""
    sym = symbol.upper()
    grp = _load_price_history(sym, days)
    if grp.empty:
        return {"symbol": sym, "error": "No price history available"}

    closes = grp["CLOSE"]
    latest = grp.iloc[-1]
    prev   = grp.iloc[-2] if len(grp) > 1 else grp.iloc[-1]

    rsi  = _compute_rsi(closes)
    adx  = _compute_adx(grp)
    macd = _compute_macd_signal(closes)
    st   = _supertrend(grp)

    c   = closes.values
    sma20  = round(float(c[-20:].mean()), 2)  if len(c) >= 20  else None
    sma50  = round(float(c[-50:].mean()), 2)  if len(c) >= 50  else None
    sma200 = round(float(c[-200:].mean()), 2) if len(c) >= 200 else None
    cur    = round(float(latest["CLOSE"]), 2)

    w52_high = round(float(grp["HIGH"].max()), 2)
    w52_low  = round(float(grp["LOW"].min()), 2)
    pct_from_52h = round((cur / w52_high - 1) * 100, 1) if w52_high else None

    avg_vol = round(float(grp["TOTTRDQTY"].tail(20).mean())) if "TOTTRDQTY" in grp else None
    last_vol = int(latest["TOTTRDQTY"]) if pd.notna(latest.get("TOTTRDQTY")) else None
    vol_ratio = round(last_vol / avg_vol, 2) if avg_vol and last_vol else None

    return {
        "symbol":        sym,
        "price":         cur,
        "open":          round(float(latest["OPEN"]), 2),
        "high":          round(float(latest["HIGH"]), 2),
        "low":           round(float(latest["LOW"]), 2),
        "chg_pct":       round((cur / float(prev["CLOSE"]) - 1) * 100, 2),
        "rsi":           rsi,
        "adx":           adx,
        "macd":          macd,
        "supertrend":    st,
        "sma20":         sma20,
        "sma50":         sma50,
        "sma200":        sma200,
        "above_sma20":   (cur > sma20)  if sma20  else None,
        "above_sma50":   (cur > sma50)  if sma50  else None,
        "above_sma200":  (cur > sma200) if sma200 else None,
        "52w_high":      w52_high,
        "52w_low":       w52_low,
        "pct_from_52h":  pct_from_52h,
        "vol_last":      last_vol,
        "vol_avg_20d":   avg_vol,
        "vol_ratio":     vol_ratio,
        "data_bars":     len(grp),
        "as_of":         str(latest["TIMESTAMP"].date()),
    }


def get_sector_context(sector_or_symbol: str) -> dict:
    """Get sector performance and stock composition context.
    Pass a stock symbol (e.g. 'BHEL') to auto-detect its sector, or a sector name directly."""
    q = sector_or_symbol.upper()
    if not DB_PATH.exists():
        return {"error": "DB not available"}

    conn = _db_conn()
    snap_date = _latest_snapshot_date()

    # If it looks like a symbol, resolve its sector first
    sym_row = conn.execute(
        "SELECT sector FROM stage_snapshots WHERE symbol=? AND snapshot_date=?",
        (q, snap_date),
    ).fetchone()
    sector = sym_row[0] if sym_row and sym_row[0] else sector_or_symbol  # preserve original case

    # Case-insensitive sector match — try exact first, then LIKE fuzzy
    rows = conn.execute(
        """SELECT symbol, company_name, stage, investment_score, relative_strength,
                  change_1d_pct, change_1w_pct, change_1m_pct, rsi, trading_signal
           FROM stage_snapshots
           WHERE UPPER(sector)=UPPER(?) AND snapshot_date=?
           ORDER BY investment_score DESC""",
        (sector, snap_date),
    ).fetchall()

    if not rows:
        # Fuzzy fallback: LIKE '%sector%'
        rows = conn.execute(
            """SELECT symbol, company_name, stage, investment_score, relative_strength,
                      change_1d_pct, change_1w_pct, change_1m_pct, rsi, trading_signal
               FROM stage_snapshots
               WHERE UPPER(sector) LIKE UPPER(?) AND snapshot_date=?
               ORDER BY investment_score DESC""",
            (f"%{sector}%", snap_date),
        ).fetchall()
        # Also resolve common abbreviations
        if not rows:
            abbrev_map = {
                "IT": "Information Technology", "TECH": "Information Technology",
                "PHARMA": "Pharma & Healthcare", "HEALTH": "Pharma & Healthcare",
                "BANK": "Banking & Finance", "FINANCE": "Banking & Finance",
                "AUTO": "EV & Auto Ancillaries", "EV": "EV & Auto Ancillaries",
                "FMCG": "FMCG & Consumer Goods", "CONSUMER": "FMCG & Consumer Goods",
                "ENERGY": "Energy - Oil & Gas", "OIL": "Energy - Oil & Gas",
                "POWER": "Energy - Power", "METAL": "Metals & Mining",
                "MINING": "Metals & Mining", "DEFENCE": "Defence & Aerospace",
                "REALTY": "Realty", "REAL ESTATE": "Realty",
            }
            mapped = abbrev_map.get(sector.upper())
            if mapped:
                rows = conn.execute(
                    """SELECT symbol, company_name, stage, investment_score, relative_strength,
                              change_1d_pct, change_1w_pct, change_1m_pct, rsi, trading_signal
                       FROM stage_snapshots
                       WHERE UPPER(sector) LIKE UPPER(?) AND snapshot_date=?
                       ORDER BY investment_score DESC""",
                    (f"%{mapped}%", snap_date),
                ).fetchall()
    conn.close()

    if not rows:
        return {"sector": sector, "error": f"No stocks found for sector '{sector}'"}

    cols = ["symbol","company_name","stage","investment_score","relative_strength",
            "change_1d_pct","change_1w_pct","change_1m_pct","rsi","trading_signal"]
    stocks = [dict(zip(cols, r)) for r in rows]

    # Sector stats
    s2_count  = sum(1 for s in stocks if s["stage"] == "STAGE_2")
    avg_rs    = round(sum(float(s["relative_strength"] or 0) for s in stocks) / len(stocks) * 100, 1)
    avg_1m    = round(sum(float(s["change_1m_pct"] or 0) for s in stocks) / len(stocks), 2)
    buy_sigs  = sum(1 for s in stocks if (s["trading_signal"] or "").startswith("BUY"))

    return {
        "sector":         sector,
        "snapshot_date":  snap_date,
        "total_stocks":   len(stocks),
        "stage2_count":   s2_count,
        "buy_signals":    buy_sigs,
        "avg_rs_pct":     avg_rs,
        "avg_1m_pct":     avg_1m,
        "top5_by_score":  stocks[:5],
        "weakest_3":      stocks[-3:],
    }


def run_screener_query(screen_type: str = "stage2", top_n: int = 10) -> dict:
    """Run a pre-built screener from DB snapshot data.

    screen_type options: stage2, breakouts, supertrend_buy, vcp, darvas, momentum_52w,
                         strong_buy, new_entrants
    """
    if not DB_PATH.exists():
        return {"error": "DB not available"}

    conn = _db_conn()
    snap_date = _latest_snapshot_date()

    query_map: dict[str, str] = {
        "stage2": (
            "SELECT symbol, company_name, stage_score, investment_score, price, "
            "relative_strength, change_1m_pct, rsi, trading_signal, sector "
            "FROM stage_snapshots WHERE snapshot_date=? AND stage='STAGE_2' "
            "ORDER BY investment_score DESC"
        ),
        "breakouts": (
            "SELECT symbol, company_name, stage_score, investment_score, price, "
            "relative_strength, change_1m_pct, rsi, trading_signal, sector "
            "FROM stage_snapshots WHERE snapshot_date=? AND stage='STAGE_2' "
            "AND COALESCE(relative_strength, 0) > 0 "
            "AND COALESCE(change_1m_pct, 0) > 0 "
            "AND COALESCE(rsi, 0) >= 55 "
            "ORDER BY investment_score DESC, relative_strength DESC, change_1m_pct DESC"
        ),
        "supertrend_buy": (
            "SELECT symbol, company_name, stage_score, investment_score, price, "
            "relative_strength, change_1d_pct, rsi, trading_signal, sector "
            "FROM stage_snapshots WHERE snapshot_date=? AND supertrend_state='BUY' "
            "ORDER BY technical_score DESC"
        ),
        "strong_buy": (
            "SELECT symbol, company_name, stage_score, investment_score, price, "
            "relative_strength, change_1m_pct, rsi, trading_signal, sector "
            "FROM stage_snapshots WHERE snapshot_date=? AND trading_signal='STRONG_BUY' "
            "ORDER BY investment_score DESC"
        ),
        "new_entrants": (
            "SELECT s.symbol, s.company_name, s.stage_score, s.investment_score, "
            "s.price, s.relative_strength, s.change_1m_pct, s.rsi, s.trading_signal, s.sector "
            "FROM stage_snapshots s "
            "LEFT JOIN stage_changes c ON s.symbol=c.symbol AND c.new_stage='STAGE_2' "
            "WHERE s.snapshot_date=? AND s.stage='STAGE_2' "
            "AND c.change_date >= date(?, '-14 days') ORDER BY s.investment_score DESC"
        ),
    }

    screen_key = screen_type.lower()
    if screen_key not in query_map:
        return {"error": f"Unknown screener: {screen_type}"}

    sql = query_map[screen_key]
    cols = ["symbol","company_name","stage_score","investment_score","price",
            "relative_strength","change","rsi","trading_signal","sector"]

    if screen_key == "new_entrants":
        rows = conn.execute(sql, (snap_date, snap_date)).fetchmany(top_n)
    else:
        rows = conn.execute(sql, (snap_date,)).fetchmany(top_n)
    conn.close()

    stocks = []
    for r in rows:
        d = dict(zip(cols, r))
        if d.get("relative_strength") is not None:
            d["rs_pct"] = round(float(d["relative_strength"]) * 100, 1)
        stocks.append(d)

    return {
        "screen_type":    screen_key,
        "snapshot_date":  snap_date,
        "count":          len(stocks),
        "results":        stocks,
    }


def get_index_snapshot(index_name: str = "NIFTY 50") -> dict:
    """Get latest index OHLCV and 10-day trend from index CSV."""
    if not INDEX_CSV.exists():
        return {"error": "Index CSV not available"}

    df = pd.read_csv(
        INDEX_CSV,
        usecols=["SYMBOL", "OPEN", "HIGH", "LOW", "CLOSE", "TIMESTAMP", "HI_52_WK", "LO_52_WK"],
        low_memory=False,
    )
    df["TIMESTAMP"] = pd.to_datetime(df["TIMESTAMP"])
    for c in ["OPEN", "HIGH", "LOW", "CLOSE"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # Fuzzy match index name
    names = df["SYMBOL"].unique()
    q = index_name.upper().replace("NIFTY", "NIFTY").replace("  ", " ")
    match = next((n for n in names if q in n.upper() or n.upper() in q), None)
    if not match:
        match = next((n for n in names if any(w in n.upper() for w in q.split())), None)
    if not match:
        return {"error": f"Index '{index_name}' not found", "available": list(names[:20])}

    idx = df[df["SYMBOL"] == match].sort_values("TIMESTAMP")
    if idx.empty:
        return {"error": f"No data for {match}"}

    latest = idx.iloc[-1]
    prev   = idx.iloc[-2] if len(idx) > 1 else latest
    cur    = float(latest["CLOSE"])
    pr     = float(prev["CLOSE"])
    chg    = round((cur / pr - 1) * 100, 2)

    trend_10 = idx.tail(10)
    closes   = trend_10["CLOSE"].tolist()
    up_days  = sum(1 for i in range(1, len(closes)) if closes[i] >= closes[i-1])
    trend_chg = round((closes[-1] / closes[0] - 1) * 100, 2) if closes[0] > 0 else 0

    return {
        "index":       match,
        "as_of":       str(latest["TIMESTAMP"].date()),
        "close":       round(cur, 2),
        "open":        round(float(latest["OPEN"]), 2),
        "high":        round(float(latest["HIGH"]), 2),
        "low":         round(float(latest["LOW"]), 2),
        "chg_pct":     chg,
        "52w_high":    float(latest["HI_52_WK"]) if pd.notna(latest.get("HI_52_WK")) else None,
        "52w_low":     float(latest["LO_52_WK"]) if pd.notna(latest.get("LO_52_WK")) else None,
        "trend_10d":   {"closes": [round(c, 2) for c in closes], "up_days": up_days,
                        "chg_pct": trend_chg},
    }


def get_market_breadth() -> dict:
    """Compute market breadth: A/D ratio, %>200MA, sector overview."""
    if not DB_PATH.exists():
        return {"error": "DB not available"}

    conn = _db_conn()
    snap_date = _latest_snapshot_date()

    # A/D from 1d change
    rows = conn.execute(
        "SELECT symbol, change_1d_pct, change_1w_pct, relative_strength "
        "FROM stage_snapshots WHERE snapshot_date=?", (snap_date,)
    ).fetchall()
    conn.close()

    advances = sum(1 for r in rows if (r[1] or 0) > 0)
    declines = sum(1 for r in rows if (r[1] or 0) < 0)
    unchanged = len(rows) - advances - declines
    ad_ratio  = round(advances / declines, 2) if declines > 0 else 0.0
    avg_rs    = round(sum(float(r[3] or 0) * 100 for r in rows) / len(rows), 1) if rows else 0

    # %>200MA from CSV (fast approximation using DB)
    conn2 = _db_conn()
    stage_dist = dict(conn2.execute(
        "SELECT stage, COUNT(*) FROM stage_snapshots WHERE snapshot_date=? GROUP BY stage",
        (snap_date,)
    ).fetchall())
    conn2.close()

    return {
        "snapshot_date": snap_date,
        "total_stocks":  len(rows),
        "advances":      advances,
        "declines":      declines,
        "unchanged":     unchanged,
        "ad_ratio":      ad_ratio,
        "avg_rs_pct":    avg_rs,
        "stage_distribution": stage_dist,
    }


def get_global_market_assessment() -> dict:
    """Assess global market cues from cached global index and correlation files."""
    if not GLOBAL_INDEX_CSV.exists():
        return {"error": f"Global indices file not found: {GLOBAL_INDEX_CSV}"}

    df = pd.read_csv(GLOBAL_INDEX_CSV)
    if "Date" not in df.columns or df.empty:
        return {"error": "Global indices CSV is empty or missing Date column"}

    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"]).sort_values("Date")
    if len(df) < 2:
        return {"error": "Global indices CSV needs at least two dated rows"}

    latest = df.iloc[-1]
    prev_idx = len(df) - 2
    moves: dict[str, dict[str, Any]] = {}
    for asset in [c for c in df.columns if c != "Date"]:
        latest_val = pd.to_numeric(pd.Series([latest.get(asset)]), errors="coerce").iloc[0]
        if pd.isna(latest_val):
            continue

        prev_val = None
        for i in range(prev_idx, -1, -1):
            candidate = pd.to_numeric(pd.Series([df.iloc[i].get(asset)]), errors="coerce").iloc[0]
            if pd.notna(candidate) and candidate != 0:
                prev_val = float(candidate)
                break
        if prev_val is None:
            continue

        pct_change = round((float(latest_val) / prev_val - 1) * 100, 2)
        moves[asset] = {
            "price": round(float(latest_val), 2),
            "pct_change": pct_change,
        }

    def _avg(names: list[str]) -> float | None:
        vals = [moves[n]["pct_change"] for n in names if n in moves]
        return round(sum(vals) / len(vals), 2) if vals else None

    def _bias(avg: float | None) -> str:
        if avg is None:
            return "unknown"
        if avg > 0.35:
            return "positive"
        if avg < -0.35:
            return "negative"
        return "mixed"

    us_avg = _avg(["S&P 500", "Nasdaq"])
    asia_avg = _avg(["Hang Seng", "Nikkei 225"])
    commodity_avg = _avg(["Gold", "Crude Oil", "Copper"])
    fx_avg = _avg(["DXY", "USDINR"])

    regions = {
        "US": {"avg_pct_change": us_avg, "bias": _bias(us_avg)},
        "Asia": {"avg_pct_change": asia_avg, "bias": _bias(asia_avg)},
        "Commodities": {"avg_pct_change": commodity_avg, "bias": _bias(commodity_avg)},
        "FX": {"avg_pct_change": fx_avg, "bias": _bias(fx_avg)},
    }

    risk_points = 0
    if us_avg is not None:
        risk_points += 2 if us_avg > 1.0 else (1 if us_avg > 0.35 else (-2 if us_avg < -1.0 else (-1 if us_avg < -0.35 else 0)))
    if asia_avg is not None:
        risk_points += 1 if asia_avg > 0.35 else (-1 if asia_avg < -0.35 else 0)
    if moves.get("DXY", {}).get("pct_change", 0) > 0.35:
        risk_points -= 1
    if moves.get("Gold", {}).get("pct_change", 0) > 1 and risk_points < 1:
        risk_points -= 1

    if risk_points >= 2:
        risk_regime = "RISK_ON"
    elif risk_points <= -2:
        risk_regime = "RISK_OFF"
    else:
        risk_regime = "MIXED"

    india_readthrough: list[str] = []
    nasdaq = moves.get("Nasdaq", {}).get("pct_change")
    crude = moves.get("Crude Oil", {}).get("pct_change")
    usdinr = moves.get("USDINR", {}).get("pct_change")
    copper = moves.get("Copper", {}).get("pct_change")
    dxy = moves.get("DXY", {}).get("pct_change")

    if nasdaq is not None and nasdaq > 0.75:
        india_readthrough.append("Nasdaq strength is supportive for IT, digital, and growth-oriented Indian equities.")
    elif nasdaq is not None and nasdaq < -0.75:
        india_readthrough.append("Nasdaq weakness is a caution flag for IT and growth-oriented Indian equities.")

    if crude is not None and crude > 1.0:
        india_readthrough.append("Crude up is a headwind for oil importers, OMCs, aviation, paints, tyres, and broad inflation sentiment.")
    elif crude is not None and crude < -1.0:
        india_readthrough.append("Crude weakness can ease pressure on import-sensitive sectors and inflation expectations.")

    if usdinr is not None and usdinr > 0.2:
        india_readthrough.append("USDINR firmness can support exporters such as IT and pharma but pressures import-heavy sectors.")
    elif usdinr is not None and usdinr < -0.2:
        india_readthrough.append("USDINR softness can help importers but reduces currency tailwind for exporters.")

    if copper is not None and copper > 1.0:
        india_readthrough.append("Copper strength supports the cyclicals and metals read-through.")
    elif copper is not None and copper < -1.0:
        india_readthrough.append("Copper weakness is a caution flag for cyclicals and metals demand.")

    if dxy is not None and dxy > 0.35:
        india_readthrough.append("DXY strength can tighten global liquidity conditions for emerging markets, including India.")

    if not india_readthrough:
        india_readthrough.append("Global cues are balanced; confirm with Nifty breadth, Bank Nifty, and FII/DII flow.")

    watch_items = [
        "Nifty gap risk versus overnight US and Asia moves",
        "Bank Nifty follow-through after the first 30 minutes",
        "FII/DII flow confirmation",
        "Crude, USDINR, and DXY continuation during Indian market hours",
    ]

    correlations: list[dict[str, Any]] = []
    if GLOBAL_CORR_CSV.exists():
        corr = pd.read_csv(GLOBAL_CORR_CSV)
        keep = ["asset", "price", "corr_30d", "corr_60d", "change", "alert"]
        if not corr.empty and all(c in corr.columns for c in keep):
            for _, row in corr[keep].head(12).iterrows():
                correlations.append(row.where(pd.notna(row), None).to_dict())

    return {
        "risk_regime": risk_regime,
        "as_of": str(latest["Date"].date()),
        "regions": regions,
        "moves": moves,
        "india_readthrough": india_readthrough,
        "watch_items": watch_items,
        "correlations": correlations,
        "source": "Cached global market CSVs",
        "source_files": {
            "global_indices": str(GLOBAL_INDEX_CSV.relative_to(ROOT)) if GLOBAL_INDEX_CSV.is_relative_to(ROOT) else str(GLOBAL_INDEX_CSV),
            "global_correlations": str(GLOBAL_CORR_CSV.relative_to(ROOT)) if GLOBAL_CORR_CSV.is_relative_to(ROOT) else str(GLOBAL_CORR_CSV),
        },
    }


def _sqlite_table_exists(table_name: str) -> bool:
    if not DB_PATH.exists():
        return False
    conn = _db_conn()
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    conn.close()
    return bool(row)


def get_intraday_source_health(max_age_minutes: int = 30) -> dict:
    """Report health of SQLite intraday source tables."""
    table_names = [
        "intraday_quotes",
        "intraday_ohlcv",
        "intraday_indicators",
        "intraday_signals",
        "intraday_levels",
        "intraday_agent_runs",
    ]
    result: dict[str, Any] = {
        "data_mode": "intraday",
        "db_path": str(DB_PATH.relative_to(ROOT)) if DB_PATH.is_relative_to(ROOT) else str(DB_PATH),
        "max_age_minutes": max_age_minutes,
        "tables": {},
    }
    if not DB_PATH.exists():
        result["overall_status"] = "MISSING"
        result["error"] = "Intraday SQLite database not found"
        return result

    now = datetime.now()
    conn = _db_conn()
    statuses: list[str] = []
    for table in table_names:
        exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
        if not exists:
            result["tables"][table] = {"exists": False, "status": "MISSING"}
            statuses.append("MISSING")
            continue

        row_count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
        timestamp_col = next((c for c in cols if c.lower() in ("timestamp", "datetime", "time", "as_of")), None)
        latest_ts = None
        age_minutes = None
        status = "EMPTY" if row_count == 0 else "UNKNOWN"
        if row_count and timestamp_col:
            raw_ts = conn.execute(f"SELECT MAX({timestamp_col}) FROM {table}").fetchone()[0]
            parsed = pd.to_datetime(raw_ts, errors="coerce")
            if pd.notna(parsed):
                latest_dt = parsed.to_pydatetime()
                latest_ts = latest_dt.strftime("%Y-%m-%d %H:%M:%S")
                age_minutes = round((now - latest_dt).total_seconds() / 60, 1)
                status = "FRESH" if age_minutes <= max_age_minutes else "STALE"
        elif row_count:
            status = "PRESENT"

        result["tables"][table] = {
            "exists": True,
            "status": status,
            "rows": row_count,
            "latest_timestamp": latest_ts,
            "age_minutes": age_minutes,
        }
        statuses.append(status)
    conn.close()

    if result["tables"].get("intraday_ohlcv", {}).get("status") == "FRESH":
        result["overall_status"] = "FRESH"
    elif result["tables"].get("intraday_ohlcv", {}).get("exists"):
        result["overall_status"] = result["tables"]["intraday_ohlcv"]["status"]
    elif "MISSING" in statuses:
        result["overall_status"] = "MISSING"
    else:
        result["overall_status"] = "UNKNOWN"
    return result


def get_intraday_bars(
    symbol: str,
    timeframe: str = "15m",
    lookback: int = 120,
) -> dict:
    """Read intraday OHLCV bars from SQLite intraday_ohlcv."""
    sym = symbol.strip().upper()
    if not DB_PATH.exists():
        return {"symbol": sym, "data_mode": "intraday", "error": "Intraday SQLite database not found"}
    if not _sqlite_table_exists("intraday_ohlcv"):
        return {"symbol": sym, "data_mode": "intraday", "error": "intraday_ohlcv table not found"}

    conn = _db_conn()
    df = pd.read_sql_query(
        "SELECT * FROM intraday_ohlcv WHERE UPPER(symbol)=? AND timeframe=?",
        conn,
        params=(sym, timeframe),
    )
    conn.close()
    if df.empty:
        return {
            "symbol": sym,
            "timeframe": timeframe,
            "data_mode": "intraday",
            "source": "SQLite intraday_ohlcv",
            "bars": [],
            "error": f"No intraday bars for {sym} at {timeframe}",
        }

    df.columns = [str(c).lower() for c in df.columns]
    required = ["timestamp", "open", "high", "low", "close", "volume"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        return {
            "symbol": sym,
            "timeframe": timeframe,
            "data_mode": "intraday",
            "source": "SQLite intraday_ohlcv",
            "error": f"intraday_ohlcv missing columns: {', '.join(missing)}",
        }

    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp"]).sort_values("timestamp").tail(lookback)
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["open", "high", "low", "close"])
    bars = [
        {
            "timestamp": row["timestamp"].strftime("%Y-%m-%d %H:%M:%S"),
            "open": round(float(row["open"]), 2),
            "high": round(float(row["high"]), 2),
            "low": round(float(row["low"]), 2),
            "close": round(float(row["close"]), 2),
            "volume": int(row["volume"]) if pd.notna(row["volume"]) else None,
        }
        for _, row in df.iterrows()
    ]
    return {
        "symbol": sym,
        "timeframe": timeframe,
        "lookback": lookback,
        "data_mode": "intraday",
        "source": "SQLite intraday_ohlcv",
        "count": len(bars),
        "latest_timestamp": bars[-1]["timestamp"] if bars else None,
        "bars": bars,
    }


def _bars_to_intraday_df(bars: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(bars)
    if df.empty:
        return df
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp"]).set_index("timestamp").sort_index()
    return df.rename(
        columns={
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
        }
    )[["Open", "High", "Low", "Close", "Volume"]]


def get_intraday_levels(symbol: str, timeframe: str = "15m") -> dict:
    """Compute support/resistance levels from SQLite intraday OHLCV bars."""
    sym = symbol.strip().upper()
    bars_result = get_intraday_bars(sym, timeframe=timeframe, lookback=240)
    if bars_result.get("error"):
        return bars_result

    df = _bars_to_intraday_df(bars_result.get("bars", []))
    if df.empty or len(df) < 10:
        return {
            "symbol": sym,
            "timeframe": timeframe,
            "data_mode": "intraday",
            "source": "SQLite intraday_ohlcv",
            "error": "Insufficient SQLite intraday bars for level analysis",
        }

    df_ind = _compute_intraday_all(df)
    levels = _intraday_key_levels(df_ind)
    latest_close = float(df_ind["Close"].iloc[-1])
    return {
        "symbol": sym,
        "timeframe": timeframe,
        "data_mode": "intraday",
        "source": "SQLite intraday_ohlcv",
        "latest_timestamp": bars_result.get("latest_timestamp"),
        "latest_close": round(latest_close, 2),
        "pivot": levels.get("pivot"),
        "supports": levels.get("supports", []),
        "resistances": levels.get("resistances", []),
        "ema_levels": {
            "ema9": levels.get("ema9"),
            "ema21": levels.get("ema21"),
            "ema50": levels.get("ema50"),
            "ema200": levels.get("ema200"),
        },
        "pivot_levels": levels.get("pivot_levels", {}),
        "copy_rule": "Technical levels only. Not investment advice or a trade recommendation.",
    }


def _normalise_signal_direction(direction: str | None) -> str:
    d = (direction or "").upper()
    if d == "BUY":
        return "LONG_SETUP"
    if d == "SELL":
        return "SHORT_SETUP"
    if d == "WATCH":
        return "WATCH"
    return "AVOID"


def compute_intraday_indicators(symbol: str, timeframe: str = "15m") -> dict:
    """Compute latest intraday indicators from SQLite intraday_ohlcv bars."""
    sym = symbol.strip().upper()
    bars_result = get_intraday_bars(sym, timeframe=timeframe, lookback=240)
    if bars_result.get("error"):
        return bars_result

    df = _bars_to_intraday_df(bars_result.get("bars", []))
    if df.empty or len(df) < 30:
        return {
            "symbol": sym,
            "timeframe": timeframe,
            "data_mode": "intraday",
            "source": "SQLite intraday_ohlcv",
            "error": "Insufficient SQLite intraday bars for indicator calculation",
        }

    df_ind = _compute_intraday_all(df)
    last = df_ind.iloc[-1]
    first_close = float(df_ind["Close"].iloc[0])
    latest_close = float(last["Close"])
    volume_avg_20 = float(df_ind["Volume"].tail(20).mean()) if len(df_ind) >= 20 else None
    volume_last = float(last["Volume"]) if pd.notna(last["Volume"]) else None
    volume_ratio = round(volume_last / volume_avg_20, 2) if volume_avg_20 and volume_last else None
    roc = round((latest_close / first_close - 1) * 100, 2) if first_close else None
    macd_hist = float(last["MACD_hist"]) if pd.notna(last["MACD_hist"]) else 0.0
    supertrend_dir = int(last["Supertrend_dir"]) if pd.notna(last["Supertrend_dir"]) else 0

    momentum_score = 0
    momentum_score += 20 if latest_close > float(last["EMA21"]) else -10
    momentum_score += 20 if latest_close > float(last["EMA50"]) else -10
    momentum_score += 15 if macd_hist > 0 else -10
    rsi = float(last["RSI"]) if pd.notna(last["RSI"]) else 50.0
    momentum_score += 15 if 50 <= rsi <= 75 else (-10 if rsi > 80 or rsi < 35 else 0)
    momentum_score += 15 if supertrend_dir == 1 else -10
    momentum_score += 15 if (volume_ratio or 0) >= 1.2 else 0
    score = max(0, min(100, 50 + momentum_score))

    return {
        "symbol": sym,
        "timeframe": timeframe,
        "data_mode": "intraday",
        "source": "SQLite intraday_ohlcv",
        "latest_timestamp": bars_result.get("latest_timestamp"),
        "latest_close": round(latest_close, 2),
        "pct_change": roc,
        "bars": len(df_ind),
        "score": round(score, 1),
        "indicators": {
            "rsi": _safe_float(last["RSI"], 1),
            "macd": _safe_float(last["MACD"], 4),
            "macd_signal": _safe_float(last["MACD_signal"], 4),
            "macd_hist": _safe_float(last["MACD_hist"], 4),
            "supertrend": _safe_float(last["Supertrend"]),
            "supertrend_dir": supertrend_dir,
            "ema9": _safe_float(last["EMA9"]),
            "ema21": _safe_float(last["EMA21"]),
            "ema50": _safe_float(last["EMA50"]),
            "ema200": _safe_float(last["EMA200"]),
            "bb_pct": _safe_float(last["BB_pct"]),
            "bb_width": _safe_float(last["BB_width"], 4),
            "atr": _safe_float(last["ATR"]),
            "volume_ratio": volume_ratio,
        },
    }


def explain_intraday_setup(symbol: str, timeframe: str = "15m") -> dict:
    """Explain an intraday setup from SQLite bars with research-only labels."""
    sym = symbol.strip().upper()
    ind = compute_intraday_indicators(sym, timeframe=timeframe)
    if ind.get("error"):
        return ind

    bars_result = get_intraday_bars(sym, timeframe=timeframe, lookback=240)
    df = _bars_to_intraday_df(bars_result.get("bars", []))
    df_ind = _compute_intraday_all(df)
    raw_signals = _run_intraday_all_signals(df_ind)
    levels = get_intraday_levels(sym, timeframe=timeframe)
    indicators = ind.get("indicators", {})

    long_evidence: list[str] = []
    short_evidence: list[str] = []
    watch_evidence: list[str] = []

    if (indicators.get("supertrend_dir") or 0) == 1:
        long_evidence.append("Supertrend is bullish")
    elif (indicators.get("supertrend_dir") or 0) == -1:
        short_evidence.append("Supertrend is bearish")

    if (indicators.get("macd_hist") or 0) > 0:
        long_evidence.append("MACD histogram is positive")
    elif (indicators.get("macd_hist") or 0) < 0:
        short_evidence.append("MACD histogram is negative")

    rsi = indicators.get("rsi")
    if isinstance(rsi, (int, float)):
        if 50 <= rsi <= 75:
            long_evidence.append(f"RSI {rsi} supports momentum without extreme overextension")
        elif rsi > 80:
            watch_evidence.append(f"RSI {rsi} is extended")
        elif rsi < 40:
            short_evidence.append(f"RSI {rsi} shows weak momentum")

    latest_close = ind.get("latest_close")
    ema21 = indicators.get("ema21")
    ema50 = indicators.get("ema50")
    if isinstance(latest_close, (int, float)) and isinstance(ema21, (int, float)):
        if latest_close > ema21:
            long_evidence.append("Price is above EMA21")
        else:
            short_evidence.append("Price is below EMA21")
    if isinstance(latest_close, (int, float)) and isinstance(ema50, (int, float)):
        if latest_close > ema50:
            long_evidence.append("Price is above EMA50")
        else:
            short_evidence.append("Price is below EMA50")

    signal_labels = [_normalise_signal_direction(s.get("direction")) for s in raw_signals]
    if "LONG_SETUP" in signal_labels:
        long_evidence.append("At least one indicator strategy triggered a long-side setup")
    if "SHORT_SETUP" in signal_labels:
        short_evidence.append("At least one indicator strategy triggered a short-side setup")
    if "WATCH" in signal_labels:
        watch_evidence.append("At least one volatility or pattern alert is in watch state")

    long_score = len(long_evidence) * 12
    short_score = len(short_evidence) * 12
    score = ind.get("score", 0)
    if long_score >= 36 and long_score >= short_score:
        setup_label = "LONG_SETUP"
    elif short_score >= 36 and short_score > long_score:
        setup_label = "SHORT_SETUP"
    elif watch_evidence or score >= 55:
        setup_label = "WATCH"
    else:
        setup_label = "AVOID"

    supports = levels.get("supports") or []
    resistances = levels.get("resistances") or []
    atr = indicators.get("atr") or 0
    invalidation = None
    target_zones: list[float] = []
    if setup_label == "LONG_SETUP":
        invalidation = supports[0] if supports else (round(latest_close - atr, 2) if latest_close and atr else None)
        target_zones = resistances[:2] or ([round(latest_close + atr, 2)] if latest_close and atr else [])
    elif setup_label == "SHORT_SETUP":
        invalidation = resistances[0] if resistances else (round(latest_close + atr, 2) if latest_close and atr else None)
        target_zones = supports[:2] or ([round(latest_close - atr, 2)] if latest_close and atr else [])

    analyzers = {
        "TrendAgent": long_evidence[:2] if long_evidence else short_evidence[:2],
        "MomentumAgent": [e for e in long_evidence + short_evidence + watch_evidence if "RSI" in e or "MACD" in e],
        "LevelsAgent": {
            "support": supports[:2],
            "resistance": resistances[:2],
            "invalidation_level": invalidation,
            "technical_target_zones": target_zones,
        },
        "RiskAgent": [
            "Technical setup only; no order placement or recommendation",
            "Confirm freshness, liquidity, spreads, and market regime before using this for research",
        ],
    }

    return {
        "symbol": sym,
        "timeframe": timeframe,
        "data_mode": "intraday",
        "source": "SQLite intraday_ohlcv",
        "latest_timestamp": ind.get("latest_timestamp"),
        "latest_close": latest_close,
        "setup_label": setup_label,
        "setup_side": "long" if setup_label == "LONG_SETUP" else ("short" if setup_label == "SHORT_SETUP" else "neutral"),
        "score": score,
        "indicators": indicators,
        "signals": [
            {
                **s,
                "setup_label": _normalise_signal_direction(s.get("direction")),
                "copy_rule": "Research setup only; not a buy/sell recommendation.",
            }
            for s in raw_signals
        ],
        "analyzers": analyzers,
        "levels": levels,
        "invalidation_level": invalidation,
        "technical_target_zones": target_zones,
        "disclaimer": (
            "Research and learning only. Not investment advice. Not a recommendation to buy, "
            "sell, trade, copy, or replicate. Users are responsible for their own risk, "
            "compliance, and legal obligations. Agent Adda is not SEBI registered."
        ),
    }


def run_intraday_screener(
    screen_type: str = "momentum",
    timeframe: str = "15m",
    min_score: float = 55,
    top_n: int = 10,
    symbols: list[str] | None = None,
) -> dict:
    """Run a SQLite-backed intraday screener with research-only setup labels.

    Automatically falls back to live yfinance scan (NIFTY 500) when the
    local SQLite intraday_ohlcv table is absent or stale.
    """
    screen_key = screen_type.lower().strip()
    supported = {"momentum", "breakouts", "vcp", "supertrend", "levels", "all"}
    if screen_key not in supported:
        return {"error": f"Unknown intraday screener: {screen_type}", "supported": sorted(supported)}

    # ── SQLite unavailable → live yfinance fallback ─────────────────────────
    if not DB_PATH.exists() or not _sqlite_table_exists("intraday_ohlcv"):
        strategy_map = {
            "breakouts":  ["ema", "volume", "macd"],
            "momentum":   ["macd", "rsi", "supertrend"],
            "vcp":        ["vcp", "volume"],
            "supertrend": ["supertrend"],
            "levels":     ["ema", "bollinger"],
            "all":        None,
        }
        strategies = strategy_map.get(screen_key)
        result = scan_intraday_market(
            index="NIFTY 500",
            interval=timeframe if timeframe in ("5m","15m","30m","1h") else "15m",
            strategies=strategies,
            direction_filter="buy",
            min_rr=1.3,
            top_n=top_n,
        )
        result["screen_type"]  = screen_key
        result["data_mode"]    = "live-yfinance-fallback"
        result["fallback_note"] = (
            "SQLite intraday_ohlcv not available — ran live yfinance scan on NIFTY 500"
        )
        return result

    if symbols is None:
        conn = _db_conn()
        rows = conn.execute(
            "SELECT DISTINCT UPPER(symbol) FROM intraday_ohlcv WHERE timeframe=? ORDER BY UPPER(symbol)",
            (timeframe,),
        ).fetchall()
        conn.close()
        symbols = [r[0] for r in rows]

    results: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for sym in symbols:
        setup = explain_intraday_setup(sym, timeframe=timeframe)
        if setup.get("error"):
            errors.append({"symbol": sym, "error": setup["error"]})
            continue
        label = setup.get("setup_label")
        indicators = setup.get("indicators", {})
        include = setup.get("score", 0) >= min_score
        if screen_key == "breakouts":
            include = include and label in ("LONG_SETUP", "WATCH") and bool(setup.get("technical_target_zones"))
        elif screen_key == "vcp":
            include = any(s.get("strategy_key") == "vcp" for s in setup.get("signals", [])) or label == "WATCH"
        elif screen_key == "supertrend":
            include = include and indicators.get("supertrend_dir") in (1, -1)
        elif screen_key == "levels":
            include = True

        if include:
            levels = setup.get("levels", {})
            results.append({
                "symbol": setup["symbol"],
                "timeframe": timeframe,
                "setup_label": label,
                "setup_side": setup.get("setup_side"),
                "score": setup.get("score"),
                "price": setup.get("latest_close"),
                "rsi": indicators.get("rsi"),
                "macd_hist": indicators.get("macd_hist"),
                "supertrend_dir": indicators.get("supertrend_dir"),
                "support": (levels.get("supports") or [None])[0],
                "resistance": (levels.get("resistances") or [None])[0],
                "invalidation_level": setup.get("invalidation_level"),
                "technical_target_zones": setup.get("technical_target_zones"),
                "freshness": setup.get("latest_timestamp"),
            })

    results.sort(key=lambda r: (r.get("score") or 0), reverse=True)
    return {
        "screen_type": screen_key,
        "timeframe": timeframe,
        "data_mode": "intraday",
        "source": "SQLite intraday_ohlcv",
        "min_score": min_score,
        "scanned": len(symbols),
        "count": len(results[:top_n]),
        "results": results[:top_n],
        "errors": errors,
        "disclaimer": "Research and learning only. Not investment advice or a trade recommendation.",
    }


def get_data_health() -> dict:
    """Check freshness of all data sources."""
    today = date.today()

    def _days_old(path: Path, date_col: str | None = None) -> dict:
        if not path.exists():
            return {"exists": False}
        stat = path.stat()
        mtime = datetime.fromtimestamp(stat.st_mtime).date()
        return {"exists": True, "file_mtime": str(mtime), "mtime_days_old": (today - mtime).days,
                "size_mb": round(stat.st_size / 1e6, 2)}

    stock_info = _days_old(STOCK_CSV)
    index_info = _days_old(INDEX_CSV)
    db_info    = _days_old(DB_PATH)

    snap_date = _latest_snapshot_date()
    db_age = (today - date.fromisoformat(snap_date)).days if snap_date != "N/A" else -1

    return {
        "as_of":              str(today),
        "stock_csv":          stock_info,
        "index_csv":          index_info,
        "tracker_db":         {**db_info, "latest_snapshot": snap_date, "snapshot_days_old": db_age},
        "overall_status":     "FRESH" if db_age <= 3 else ("STALE" if db_age <= 7 else "OLD"),
    }


def find_latest_report(report_type: str = "any") -> dict:
    """List available generated reports."""
    report_dirs = [REPORTS / "latest", REPORTS / "generated_csv"]
    files: list[dict] = []
    for d in report_dirs:
        if not d.exists():
            continue
        for f in sorted(d.iterdir(), reverse=True):
            if f.is_file() and f.suffix in (".html", ".csv", ".json"):
                keyword = report_type.lower()
                if keyword == "any" or keyword in f.name.lower():
                    files.append({
                        "name": f.name,
                        "path": str(f.relative_to(ROOT)),
                        "size_kb": round(f.stat().st_size / 1024, 1),
                        "modified": str(datetime.fromtimestamp(f.stat().st_mtime).date()),
                    })
    return {"report_type": report_type, "count": len(files), "files": files[:10]}


def search_latest_catalysts(symbol: str, max_results: int = 5) -> dict:
    """Search for recent news/catalysts for a symbol via DuckDuckGo Lite."""
    try:
        import requests
        from html.parser import HTMLParser

        class _ResultParser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.results: list[dict] = []
                self._in_result = False
                self._cur: dict = {}
                self._tag_stack: list[str] = []

            def handle_starttag(self, tag, attrs):
                attrs_d = dict(attrs)
                self._tag_stack.append(tag)
                if tag == "a" and attrs_d.get("class") == "result__a":
                    self._cur = {"url": attrs_d.get("href", ""), "title": ""}
                    self._in_result = True
                elif tag == "td" and "result__snippet" in attrs_d.get("class", ""):
                    self._in_result = True

            def handle_data(self, data):
                if self._in_result and data.strip():
                    if "title" in self._cur and not self._cur["title"]:
                        self._cur["title"] = data.strip()
                    elif "snippet" not in self._cur:
                        self._cur["snippet"] = data.strip()

            def handle_endtag(self, tag):
                if self._tag_stack:
                    self._tag_stack.pop()
                if tag == "a" and self._in_result and self._cur.get("title"):
                    self.results.append(dict(self._cur))
                    self._cur = {}
                    self._in_result = False

        # Get company name for better search
        sym_data = get_symbol_snapshot(symbol)
        company  = sym_data.get("company_name") or symbol
        query    = f"{company} NSE India news 2026"

        import urllib.parse
        url  = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=8)

        parser = _ResultParser()
        parser.feed(resp.text)

        def _decode_url(raw: str) -> str:
            """Extract real URL from DuckDuckGo redirect (/l/?uddg=<encoded>)."""
            import urllib.parse
            if not raw:
                return ""
            # Add scheme if missing
            if raw.startswith("//"):
                raw = "https:" + raw
            parsed = urllib.parse.urlparse(raw)
            qs = urllib.parse.parse_qs(parsed.query)
            if "uddg" in qs:
                return qs["uddg"][0]
            return raw

        results = []
        for r in parser.results[:max_results]:
            if r.get("title") and len(r["title"]) > 5:
                results.append({
                    "title":   r.get("title", ""),
                    "url":     _decode_url(r.get("url", "")),
                    "snippet": r.get("snippet", ""),
                })

        return {
            "symbol":  symbol.upper(),
            "company": company,
            "query":   query,
            "results": results,
            "source":  "DuckDuckGo",
            "disclaimer": "Web search results — verify before acting",
        }
    except Exception as e:
        return {"symbol": symbol.upper(), "error": str(e), "results": []}


# ─────────────────────────────────────────────────────────────────────────────
# Portfolio tools
# ─────────────────────────────────────────────────────────────────────────────

HOLDINGS_CSV = ROOT / "portfolio-analyzer" / "output" / "holdings.csv"


def get_portfolio_exposure(sector: str = None) -> dict:
    """Return portfolio holdings summary, optionally filtered by sector.

    Returns total_stocks, sector_counts, top_holdings.  If sector is given,
    also returns filtered symbol list for that sector.
    """
    if not HOLDINGS_CSV.exists():
        return {"error": f"Holdings file not found: {HOLDINGS_CSV}"}
    try:
        df = pd.read_csv(HOLDINGS_CSV)
        df.columns = df.columns.str.lower()
        sym_col = "symbol" if "symbol" in df.columns else df.columns[0]
        val_col = next(
            (c for c in ["value_rs", "value", "current_value"] if c in df.columns), None
        )
        symbols = df[sym_col].str.upper().tolist()

        # Sector mapping from DB
        sector_counts: dict[str, int] = {}
        sym_sector: dict[str, str] = {}
        if DB_PATH.exists():
            conn = _db_conn()
            placeholders = ",".join("?" * len(symbols))
            rows = conn.execute(
                f"SELECT symbol, sector FROM stage_snapshots "
                f"WHERE symbol IN ({placeholders}) "
                f"GROUP BY symbol ORDER BY snapshot_date DESC",
                symbols,
            ).fetchall()
            conn.close()
            sym_sector = {r[0]: (r[1] or "Unknown") for r in rows}
        for sym in symbols:
            sec = sym_sector.get(sym, "Unknown")
            sector_counts[sec] = sector_counts.get(sec, 0) + 1

        # Top 10 by value
        top_holdings: list[dict] = []
        if val_col and val_col in df.columns:
            df[val_col] = pd.to_numeric(df[val_col], errors="coerce").fillna(0)
            for _, row in df.nlargest(10, val_col).iterrows():
                top_holdings.append({
                    "symbol": row[sym_col],
                    "value":  round(float(row[val_col]), 2),
                    "sector": sym_sector.get(str(row[sym_col]).upper(), "—"),
                })

        result: dict[str, Any] = {
            "total_stocks":  len(df),
            "sector_counts": sector_counts,
            "top_holdings":  top_holdings,
        }
        if sector:
            result["filtered_by_sector"] = sector
            result["sector_symbols"] = [
                sym for sym in symbols
                if sector.lower() in sym_sector.get(sym, "").lower()
            ]
        return result
    except Exception as e:
        return {"error": str(e)}


def find_portfolio_overlap(screener: str = "stage2") -> dict:
    """Find portfolio holdings that also appear in a DB screener result.

    screener: 'stage2' | 'supertrend_buy' | 'all'
    Returns overlap_count, overlapping_symbols with stage/signal data.
    """
    if not HOLDINGS_CSV.exists():
        return {"error": f"Holdings file not found: {HOLDINGS_CSV}"}
    if not DB_PATH.exists():
        return {"error": "Stage snapshots DB not found"}
    try:
        df = pd.read_csv(HOLDINGS_CSV)
        df.columns = df.columns.str.lower()
        sym_col = "symbol" if "symbol" in df.columns else df.columns[0]
        portfolio_symbols = set(df[sym_col].str.upper().tolist())

        conn = _db_conn()
        if screener == "stage2":
            rows = conn.execute(
                "SELECT symbol, stage, investment_score, trading_signal FROM stage_snapshots "
                "WHERE stage='STAGE_2' "
                "AND snapshot_date=(SELECT MAX(snapshot_date) FROM stage_snapshots)"
            ).fetchall()
        elif screener == "supertrend_buy":
            rows = conn.execute(
                "SELECT symbol, stage, investment_score, trading_signal FROM stage_snapshots "
                "WHERE supertrend_state='BUY' "
                "AND snapshot_date=(SELECT MAX(snapshot_date) FROM stage_snapshots)"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT symbol, stage, investment_score, trading_signal FROM stage_snapshots "
                "WHERE snapshot_date=(SELECT MAX(snapshot_date) FROM stage_snapshots)"
            ).fetchall()
        conn.close()

        screener_map = {r[0]: r for r in rows}
        overlap = [
            {
                "symbol":          sym,
                "stage":           screener_map[sym][1],
                "investment_score": screener_map[sym][2],
                "trading_signal":  screener_map[sym][3],
            }
            for sym in portfolio_symbols
            if sym in screener_map
        ]
        return {
            "screener":          screener,
            "portfolio_count":   len(portfolio_symbols),
            "screener_count":    len(screener_map),
            "overlap_count":     len(overlap),
            "overlapping_symbols": overlap,
        }
    except Exception as e:
        return {"error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# Live NSE quote tool
# ─────────────────────────────────────────────────────────────────────────────

_NSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer":         "https://www.nseindia.com/",
}

_live_session: Any = None
_live_session_ts: float = 0.0


def _get_live_session():
    import requests, time as _time
    global _live_session, _live_session_ts
    if _live_session is None or (_time.time() - _live_session_ts) > 180:
        s = requests.Session()
        s.headers.update(_NSE_HEADERS)
        try:
            s.get("https://www.nseindia.com/", timeout=8)
            # Second warmup required for equity-stockIndices and gated endpoints
            s.get("https://www.nseindia.com/market-data/live-equity-market?symbol=NIFTY+50", timeout=8)
        except Exception:
            pass
        _live_session = s
        _live_session_ts = _time.time()
    return _live_session


def get_live_quote(symbol: str) -> dict:
    """Fetch live intraday quote for a single NSE symbol from the NSE API.

    Returns current price, day OHLC, volume, % change, and 52-week range.
    """
    import requests
    sym = symbol.strip().upper()
    try:
        s   = _get_live_session()
        url = f"https://www.nseindia.com/api/quote-equity?symbol={requests.utils.quote(sym)}"
        r   = s.get(url, timeout=10)
        r.raise_for_status()
        d   = r.json()

        info  = d.get("info", {})
        price = d.get("priceInfo", {})
        week  = d.get("priceInfo", {}).get("weekHighLow", {})

        last   = price.get("lastPrice",        price.get("close", None))
        open_  = price.get("open",             None)
        high   = price.get("intraDayHighLow",  {}).get("max", None)
        low    = price.get("intraDayHighLow",  {}).get("min", None)
        prev   = price.get("previousClose",    None)
        chg    = price.get("change",           None)
        pchg   = price.get("pChange",          None)
        vol    = d.get("marketDeptOrderBook",  {}).get("tradeInfo", {}).get("totalTradedVolume", None)

        if last is None:
            return {"symbol": sym, "error": "No price data returned"}

        result = {
            "symbol":         sym,
            "name":           info.get("companyName", sym),
            "last_price":     last,
            "open":           open_,
            "day_high":       high,
            "day_low":        low,
            "prev_close":     prev,
            "change":         round(chg,  2) if chg  is not None else None,
            "pct_change":     round(pchg, 2) if pchg is not None else None,
            "volume":         vol,
            "52w_high":       week.get("max"),
            "52w_low":        week.get("min"),
            "as_of":          datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "source":         "NSE live API",
        }
        return result
    except Exception as e:
        return {"symbol": sym, "error": str(e)}


def get_live_market_overview() -> dict:
    """Fetch live Nifty 50, Nifty Bank, and Nifty IT index values plus advances/declines."""
    import requests
    try:
        s   = _get_live_session()
        url = "https://www.nseindia.com/api/allIndices"
        r   = s.get(url, timeout=10)
        r.raise_for_status()
        data    = r.json().get("data", [])
        indices = {}
        for item in data:
            nm = item.get("index", "")
            if nm in ("NIFTY 50", "NIFTY BANK", "NIFTY IT", "NIFTY MIDCAP 100",
                      "NIFTY SMALLCAP 100"):
                last  = item.get("last",          item.get("lastPrice", 0))
                prev  = item.get("previousClose", 0)
                chg   = round(last - prev, 2) if last and prev else 0
                pchg  = round(chg / prev * 100, 2) if prev else 0
                indices[nm] = {
                    "last":       last,
                    "change":     chg,
                    "pct_change": pchg,
                    "day_high":   item.get("dayHigh"),
                    "day_low":    item.get("dayLow"),
                }
        adv_dec = {}
        try:
            url2 = "https://www.nseindia.com/api/equity-stockIndices?index=NIFTY%20500"
            r2   = s.get(url2, timeout=10)
            items = r2.json().get("data", [])
            advances = sum(1 for x in items if float(x.get("pChange", 0) or 0) > 0)
            declines = sum(1 for x in items if float(x.get("pChange", 0) or 0) < 0)
            adv_dec  = {"advances": advances, "declines": declines,
                        "unchanged": len(items) - advances - declines}
        except Exception:
            pass
        return {
            "indices":    indices,
            "adv_dec":    adv_dec,
            "as_of":      datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "source":     "NSE live API",
        }
    except Exception as e:
        return {"error": str(e)}


def get_top_gainers_losers(
    index: str = "NIFTY 500",
    top_n: int = 10,
    direction: str = "both",
) -> dict:
    """Return top gaining and/or losing stocks from an NSE index right now.

    Args:
        index: Index name — 'NIFTY 50', 'NIFTY BANK', 'NIFTY IT', 'NIFTY 500',
               'NIFTY MIDCAP 100', 'NIFTY SMALLCAP 100', etc.
        top_n: Number of stocks to return in each list (default 10).
        direction: 'gainers', 'losers', or 'both' (default 'both').
    """
    try:
        s = _get_live_session()
        # Use the NSE built-in variations endpoint for Nifty/BankNifty (faster)
        _BUILTIN_KEYS = {
            "NIFTY 50":       "NIFTY",
            "NIFTY BANK":     "BANKNIFTY",
            "NIFTY NEXT 50":  "NIFTYNEXT50",
        }
        builtin_key = _BUILTIN_KEYS.get(index.upper())

        if builtin_key:
            g_url = "https://www.nseindia.com/api/live-analysis-variations?index=gainers"
            l_url = "https://www.nseindia.com/api/live-analysis-variations?index=losers"
            g_data = s.get(g_url, timeout=10).json()
            gainers_raw = g_data.get(builtin_key, {}).get("data", [])[:top_n]
            # losers endpoint may be missing — try allIndices losers from NIFTY 500 instead
            l_data = s.get(l_url, timeout=10).json()
            losers_raw = l_data.get(builtin_key, {}).get("data", [])
            if not losers_raw:
                losers_raw = []
        else:
            gainers_raw = []
            losers_raw  = []

        # For broad indexes or if built-in losers is empty, fetch from equity-stockIndices
        idx_param = index.upper().replace(" ", "%20")
        r2 = s.get(
            f"https://www.nseindia.com/api/equity-stockIndices?index={idx_param}",
            timeout=10,
        )
        stocks = r2.json().get("data", [])
        # Remove index summary row (priority=1, symbol matches index name). Keep all stocks (priority=0).
        stocks = [x for x in stocks if x.get("symbol") and x.get("priority") != 1]

        sorted_asc  = sorted(stocks, key=lambda x: float(x.get("pChange", 0) or 0))
        sorted_desc = sorted(stocks, key=lambda x: float(x.get("pChange", 0) or 0), reverse=True)

        def _fmt(x: dict) -> dict:
            return {
                "symbol":     x.get("symbol"),
                "last_price": x.get("lastPrice"),
                "change":     round(float(x.get("change",  0) or 0), 2),
                "pct_change": round(float(x.get("pChange", 0) or 0), 2),
                "volume":     x.get("totalTradedVolume"),
                "day_high":   x.get("dayHigh"),
                "day_low":    x.get("dayLow"),
                "year_high":  x.get("yearHigh"),
                "year_low":   x.get("yearLow"),
            }

        result: dict = {
            "index":  index,
            "as_of":  datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "source": "NSE live API",
        }
        if direction in ("gainers", "both"):
            result["gainers"] = [_fmt(x) for x in sorted_desc[:top_n]]
        if direction in ("losers", "both"):
            result["losers"]  = [_fmt(x) for x in sorted_asc[:top_n]]
        return result
    except Exception as e:
        return {"error": str(e), "index": index}


def get_most_active_stocks(
    by: str = "value",
    index: str = "NIFTY 500",
    top_n: int = 10,
) -> dict:
    """Return most actively traded stocks by volume or traded value.

    Args:
        by: 'volume' or 'value' (default 'value').
        index: NSE index to scan (default 'NIFTY 500').
        top_n: Number of results (default 10).
    """
    try:
        s = _get_live_session()
        idx_param = index.upper().replace(" ", "%20")
        r = s.get(
            f"https://www.nseindia.com/api/equity-stockIndices?index={idx_param}",
            timeout=10,
        )
        stocks = r.json().get("data", [])
        stocks = [x for x in stocks if x.get("symbol") and x.get("priority") != 1]
        sort_key = "totalTradedVolume" if by == "volume" else "totalTradedValue"
        sorted_stocks = sorted(
            stocks,
            key=lambda x: float(x.get(sort_key, 0) or 0),
            reverse=True,
        )[:top_n]

        return {
            "by":     by,
            "index":  index,
            "as_of":  datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "source": "NSE live API",
            "stocks": [
                {
                    "symbol":       x.get("symbol"),
                    "last_price":   x.get("lastPrice"),
                    "pct_change":   round(float(x.get("pChange", 0) or 0), 2),
                    "volume":       x.get("totalTradedVolume"),
                    "traded_value": x.get("totalTradedValue"),
                }
                for x in sorted_stocks
            ],
        }
    except Exception as e:
        return {"error": str(e)}


def get_52week_extremes(
    direction: str = "high",
    index: str = "NIFTY 500",
    top_n: int = 15,
) -> dict:
    """Return stocks near their 52-week high or low from an NSE index.

    Args:
        direction: 'high' (near 52w high) or 'low' (near 52w low).
        index: NSE index name (default 'NIFTY 500').
        top_n: Number of stocks to return (default 15).
    """
    try:
        s = _get_live_session()
        idx_param = index.upper().replace(" ", "%20")
        r = s.get(
            f"https://www.nseindia.com/api/equity-stockIndices?index={idx_param}",
            timeout=10,
        )
        stocks = r.json().get("data", [])
        stocks = [x for x in stocks if x.get("symbol") and x.get("priority") != 1
                  and x.get("yearHigh") and x.get("lastPrice")]

        results = []
        for x in stocks:
            ltp   = float(x.get("lastPrice",  0) or 0)
            y_hi  = float(x.get("yearHigh",   0) or 0)
            y_lo  = float(x.get("yearLow",    0) or 0)
            if y_hi <= 0 or ltp <= 0:
                continue
            pct_from_high = round((ltp - y_hi) / y_hi * 100, 1)
            pct_from_low  = round((ltp - y_lo) / y_lo * 100, 1) if y_lo > 0 else None
            results.append({
                "symbol":         x.get("symbol"),
                "last_price":     ltp,
                "52w_high":       y_hi,
                "52w_low":        y_lo,
                "pct_from_high":  pct_from_high,
                "pct_from_low":   pct_from_low,
                "pct_change_day": round(float(x.get("pChange", 0) or 0), 2),
            })

        if direction == "high":
            # closest to 52w high → pct_from_high nearest 0 (from below)
            filtered = sorted(results, key=lambda x: abs(x["pct_from_high"]))
        else:
            # nearest 52w low → smallest pct_from_low
            filtered = sorted(results, key=lambda x: (x["pct_from_low"] or 999))

        return {
            "direction": direction,
            "index":     index,
            "as_of":     datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "source":    "NSE live API",
            "stocks":    filtered[:top_n],
        }
    except Exception as e:
        return {"error": str(e)}


def get_fii_dii_activity() -> dict:
    """Fetch today's FII (Foreign Institutional Investors) and DII (Domestic)
    buy/sell activity from NSE. Returns net values in crores.
    """
    try:
        s = _get_live_session()
        r = s.get("https://www.nseindia.com/api/fiidiiTradeReact", timeout=10)
        raw = r.json()
        result: dict = {"as_of": datetime.now().strftime("%Y-%m-%d"), "data": []}
        for entry in raw:
            buy  = float(entry.get("buyValue",  0) or 0)
            sell = float(entry.get("sellValue", 0) or 0)
            net  = float(entry.get("netValue",  buy - sell) or 0)
            result["data"].append({
                "category":   entry.get("category"),
                "date":       entry.get("date"),
                "buy_crore":  round(buy,  2),
                "sell_crore": round(sell, 2),
                "net_crore":  round(net,  2),
                "sentiment":  "BUYING" if net > 0 else "SELLING",
            })
        return result
    except Exception as e:
        return {"error": str(e)}


def get_bulk_block_deals(top_n: int = 20) -> dict:
    """Fetch today's bulk deals and block deals from NSE.

    Bulk deals (> 0.5% of total shares) and block deals (≥ 5 lakh shares
    or ≥ ₹5 crore in value) indicate institutional activity.

    Args:
        top_n: Max number of deals to return (default 20).
    """
    try:
        import time as _time
        s = _get_live_session()
        # Extra warm-up hit needed for this endpoint to return session-gated data
        s.get("https://www.nseindia.com/market-data/bulk-deals", timeout=8)
        _time.sleep(0.5)
        r = s.get(
            "https://www.nseindia.com/api/snapshot-capital-market-largedeal",
            timeout=10,
        )
        d = r.json()
        bulk  = d.get("BULK_DEALS_DATA",  [])[:top_n]
        block = d.get("BLOCK_DEALS_DATA", [])[:top_n]   # block deals

        def _fmt(x: dict) -> dict:
            return {
                "date":        x.get("date"),
                "symbol":      x.get("symbol"),
                "company":     x.get("name"),
                "client":      x.get("clientName"),
                "buy_sell":    x.get("buySell"),
                "qty":         x.get("qty"),
                "price":       x.get("watp"),   # weighted average trade price
                "remarks":     x.get("remarks"),
            }

        return {
            "as_of":       d.get("as_on_date", datetime.now().strftime("%Y-%m-%d")),
            "source":      "NSE live API",
            "bulk_deals":  [_fmt(x) for x in bulk],
            "block_deals": [_fmt(x) for x in block],
        }
    except Exception as e:
        return {"error": str(e)}


def _ratio_pb(ratios: dict) -> str | None:
    """Derive P/B from Current Price and Book Value."""
    price = ratios.get("Current Price", "").replace(",", "")
    bv    = ratios.get("Book Value",    "").replace(",", "")
    try:
        return str(round(float(price) / float(bv), 1)) if price and bv else None
    except (ValueError, ZeroDivisionError):
        return None


def compare_stocks(
    symbols: list[str],
    aspects: list[str] | None = None,
) -> dict:
    """Compare multiple NSE stocks side-by-side on technical AND fundamental metrics.

    Combines EOD DB snapshot (stage, RS, RSI, signals, scores) with screener.in ratios
    (P/E, ROE, ROCE, market cap, P/B, dividend yield) into one unified comparison table.

    Args:
        symbols: List of NSE ticker symbols, e.g. ['TCS', 'INFY', 'WIPRO'].
        aspects: Optional list; 'technical', 'fundamental', or 'both' (default).
    """
    if not symbols:
        return {"error": "No symbols provided"}

    fetch_tech = True
    fetch_fund = True
    if aspects:
        fetch_tech = any(a in ("technical", "both") for a in aspects)
        fetch_fund = any(a in ("fundamental", "both") for a in aspects)

    rows: list[dict] = []

    for raw in symbols:
        sym = raw.strip().upper()
        row: dict = {"symbol": sym}

        if fetch_tech:
            try:
                snap = get_symbol_snapshot(sym)
                if not snap.get("error"):
                    row.update({
                        "company":          snap.get("company_name", sym),
                        "stage":            snap.get("stage"),
                        "rsi":              snap.get("rsi"),
                        "rs_pct":           snap.get("rs_pct"),
                        "technical_score":  snap.get("technical_score"),
                        "investment_score": snap.get("investment_score"),
                        "trading_signal":   snap.get("trading_signal"),
                        "trend_signal":     snap.get("trend_signal"),
                        "supertrend":       snap.get("supertrend_state"),
                        "sector":           snap.get("sector"),
                        "change_1d_pct":    snap.get("change_1d_pct"),
                        "change_1w_pct":    snap.get("change_1w_pct"),
                        "change_1m_pct":    snap.get("change_1m_pct"),
                        "db_price":         snap.get("price"),
                        "snapshot_date":    snap.get("snapshot_date"),
                        "stance":           snap.get("stance"),
                        "narrative":        snap.get("narrative"),
                    })
                else:
                    row["tech_error"] = snap["error"]
            except Exception as e:
                row["tech_error"] = str(e)

        if fetch_fund:
            try:
                sr = scrape_screener_in(sym)
                if not sr.get("error"):
                    ratios = sr.get("ratios", {})
                    row.update({
                        "pe":            ratios.get("Stock P/E"),
                        "pb":            _ratio_pb(ratios),
                        "roe":           ratios.get("ROE"),
                        "roce":          ratios.get("ROCE"),
                        "div_yield":     ratios.get("Dividend Yield"),
                        "market_cap_cr": ratios.get("Market Cap"),
                        "book_value":    ratios.get("Book Value"),
                        "current_price": ratios.get("Current Price"),
                        "high_low_52w":  ratios.get("High / Low"),
                        "screener_url":  sr.get("source_url"),
                        "pros":          sr.get("pros", [])[:3],
                        "cons":          sr.get("cons", [])[:2],
                    })
                else:
                    row["fund_error"] = sr["error"]
            except Exception as e:
                row["fund_error"] = str(e)

        rows.append(row)

    tech_cols = ["stage", "rsi", "rs_pct", "technical_score", "investment_score",
                 "trading_signal", "trend_signal", "supertrend",
                 "change_1d_pct", "change_1w_pct", "change_1m_pct"]
    fund_cols = ["pe", "pb", "roe", "roce", "div_yield", "market_cap_cr"]
    active_cols = (tech_cols if fetch_tech else []) + (fund_cols if fetch_fund else [])

    comparison_table = {col: {r["symbol"]: r.get(col) for r in rows} for col in active_cols}

    return {
        "symbols":          [r["symbol"] for r in rows],
        "as_of":            date.today().isoformat(),
        "aspects":          aspects or ["both"],
        "comparison_table": comparison_table,
        "stock_details":    rows,
    }



# ── Intraday screener wrapper ────────────────────────────────────────────────

def scan_intraday_market(
    index: str = "NIFTY 50",
    interval: str = "15m",
    strategies: list[str] | None = None,
    direction_filter: str = "all",
    min_rr: float = 1.5,
    top_n: int = 5,
) -> dict:
    """Scan all stocks in an NSE index for intraday trading signals.

    Args:
        index:            Index name: NIFTY 50, NIFTY BANK, NIFTY IT, NIFTY 500, NIFTY PHARMA...
        interval:         Candle interval: 5m, 15m, 30m, 1h.
        strategies:       Strategy keys: macd, rsi, supertrend, bollinger, ema, vcp, volume.
        direction_filter: buy, sell, or all.
        min_rr:           Minimum R:R ratio (default 1.5).
        top_n:            Top signals to highlight.
    """
    try:
        s = _get_live_session()
        idx_param = index.upper().replace(" ", "%20")
        r = s.get(
            f"https://www.nseindia.com/api/equity-stockIndices?index={idx_param}",
            timeout=10,
        )
        stocks = [x["symbol"] for x in r.json().get("data", []) if x.get("priority") != 1]
    except Exception as e:
        return {"error": f"Could not fetch {index} constituents: {e}"}

    if not stocks:
        return {"error": f"No stocks found for index: {index}"}

    result = _run_intraday_screener(
        symbols=stocks,
        interval=interval,
        strategies=strategies,
        direction_filter=direction_filter,
        min_rr=min_rr,
    )
    result["index"]    = index
    result["top_buy"]  = result["buy_signals"][:top_n]
    result["top_sell"] = result["sell_signals"][:top_n]
    return result


def scan_symbols_intraday(
    symbols: list[str],
    interval: str = "15m",
    strategies: list[str] | None = None,
    direction_filter: str = "all",
    min_rr: float = 1.3,
    top_n: int = 10,
) -> dict:
    """Scan a specific list of NSE stocks for intraday signals.

    Use this when you already have a list of stocks from EOD screening,
    breakout analysis, or any source — NOT just index constituents.
    Returns ranked BUY/SELL signals with entry/target/SL/R:R.

    Args:
        symbols:          List of NSE tickers, e.g. ['RELIANCE', 'TCS', 'CHENNPETRO'].
        interval:         Candle interval: 5m, 15m, 30m, 1h.
        strategies:       Strategy keys: macd, rsi, supertrend, bollinger, ema, vcp, volume. None = all.
        direction_filter: 'buy', 'sell', or 'all'.
        min_rr:           Minimum Risk:Reward ratio (default 1.3).
        top_n:            Max signals to return.
    """
    if not symbols:
        return {"error": "No symbols provided"}
    # Clean and deduplicate
    clean_syms = list(dict.fromkeys(s.strip().upper() for s in symbols if s.strip()))
    result = _run_intraday_screener(
        symbols=clean_syms,
        interval=interval,
        strategies=strategies,
        direction_filter=direction_filter,
        min_rr=min_rr,
    )
    result["symbols_scanned"] = clean_syms
    result["top_buy"]         = result["buy_signals"][:top_n]
    result["top_sell"]        = result["sell_signals"][:top_n]
    return result

TOOL_REGISTRY: dict[str, Any] = {
    "get_live_quote": (
        get_live_quote,
        "Fetch live intraday price quote for a single NSE symbol (real-time: last price, OHLC, % change, volume, 52w range). Use for 'current price', 'live', 'today', 'now' queries.",
        {"type": "object", "properties": {"symbol": {"type": "string"}}, "required": ["symbol"]},
    ),
    "get_live_market_overview": (
        get_live_market_overview,
        "Fetch live NSE index levels (Nifty 50, Bank Nifty, IT, Midcap, Smallcap) plus advances/declines. Use for 'how is the market', 'market today', 'live market' queries.",
        {"type": "object", "properties": {}, "required": []},
    ),
    "get_top_gainers_losers": (
        get_top_gainers_losers,
        (
            "Get top gaining and/or losing stocks from an NSE index RIGHT NOW (live). "
            "Returns symbol, LTP, % change, volume, 52w range for each stock. "
            "Use for 'top gainers', 'top losers', 'biggest movers', 'what is up/down today'. "
            "index can be: 'NIFTY 50', 'NIFTY BANK', 'NIFTY IT', 'NIFTY 500', "
            "'NIFTY MIDCAP 100', 'NIFTY SMALLCAP 100', 'NIFTY PHARMA', etc."
        ),
        {
            "type": "object",
            "properties": {
                "index":     {"type": "string", "default": "NIFTY 500"},
                "top_n":     {"type": "integer", "default": 10},
                "direction": {"type": "string", "enum": ["gainers", "losers", "both"], "default": "both"},
            },
            "required": [],
        },
    ),
    "get_most_active_stocks": (
        get_most_active_stocks,
        (
            "Get the most actively traded stocks by volume or traded value from an NSE index. "
            "Use for 'most active', 'highest volume', 'most traded', 'activity leaders'. "
            "'by' can be 'volume' or 'value'."
        ),
        {
            "type": "object",
            "properties": {
                "by":    {"type": "string", "enum": ["volume", "value"], "default": "value"},
                "index": {"type": "string", "default": "NIFTY 500"},
                "top_n": {"type": "integer", "default": 10},
            },
            "required": [],
        },
    ),
    "get_52week_extremes": (
        get_52week_extremes,
        (
            "Find stocks nearest to their 52-week high or low in a given index. "
            "Use for '52-week high', '52-week low', 'new highs', 'new lows', "
            "'near 52w high', 'breakout candidates', 'stocks at lows'. "
            "direction: 'high' or 'low'."
        ),
        {
            "type": "object",
            "properties": {
                "direction": {"type": "string", "enum": ["high", "low"], "default": "high"},
                "index":     {"type": "string", "default": "NIFTY 500"},
                "top_n":     {"type": "integer", "default": 15},
            },
            "required": [],
        },
    ),
    "get_fii_dii_activity": (
        get_fii_dii_activity,
        (
            "Fetch today's FII (Foreign Institutional Investors) and DII (Domestic Institutional) "
            "buy/sell activity from NSE. Returns net buy/sell values in crores and sentiment. "
            "Use for 'FII', 'DII', 'institutional activity', 'foreign investors', 'FII buying/selling'."
        ),
        {"type": "object", "properties": {}, "required": []},
    ),
    "get_bulk_block_deals": (
        get_bulk_block_deals,
        (
            "Fetch today's bulk deals (> 0.5% of shares) and block deals from NSE. "
            "Shows which institutional clients bought or sold large stakes. "
            "Use for 'bulk deals', 'block deals', 'institutional trades', 'large trades', 'who is buying'."
        ),
        {
            "type": "object",
            "properties": {"top_n": {"type": "integer", "default": 20}},
            "required": [],
        },
    ),
    "compare_stocks": (
        compare_stocks,
        (
            "Compare multiple NSE stocks SIDE-BY-SIDE on both technical AND fundamental metrics. "
            "Technical: stage (Weinstein 1-4), RSI, Relative Strength %, technical score, "
            "investment score, trading signal (BUY/SELL/HOLD), trend, supertrend, 1d/1w/1m returns. "
            "Fundamental (from screener.in): P/E, P/B, ROE, ROCE, dividend yield, market cap, book value. "
            "Returns a comparison_table dict and full stock_details list with pros/cons/narrative. "
            "Use for: 'compare X vs Y', 'X vs Y vs Z', 'which is better: X or Y', "
            "'peer comparison', 'compare IT stocks', 'TCS vs INFY', 'rank by ROE'."
        ),
        {
            "type": "object",
            "properties": {
                "symbols": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of NSE symbols, e.g. ['TCS', 'INFY', 'WIPRO']",
                },
                "aspects": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["technical", "fundamental", "both"]},
                    "description": "What to compare. Default is both.",
                },
            },
            "required": ["symbols"],
        },
    ),
    "get_intraday_analysis": (
        get_intraday_analysis,
        (
            "Deep intraday technical analysis of a SINGLE NSE stock. "
            "Computes: MACD crossover, RSI reversal, Supertrend direction, Bollinger Band bounce, "
            "EMA 9/21 crossover, VCP pattern, Volume spike signals — each with entry price, "
            "target, stop-loss, and Risk:Reward ratio. Also returns key support/resistance levels "
            "(pivot points, swing highs/lows, EMAs), full indicator readings, and overall bias. "
            "Use for: 'intraday setup for X', 'should I buy X today', 'entry target SL for X', "
            "'technical signals X', 'trading strategy for X'."
        ),
        {
            "type": "object",
            "properties": {
                "symbol":     {"type": "string"},
                "interval":   {"type": "string", "enum": ["5m","15m","30m","1h"], "default": "15m"},
                "strategies": {
                    "type": "array",
                    "items": {"type": "string",
                              "enum": ["macd","rsi","supertrend","bollinger","ema","vcp","volume"]},
                    "description": "Strategies to run. Default is all.",
                },
            },
            "required": ["symbol"],
        },
    ),
    "scan_intraday_market": (
        scan_intraday_market,
        (
            "Scan ALL stocks in an NSE index for live intraday trading signals RIGHT NOW. "
            "Runs MACD, RSI, Supertrend, Bollinger, EMA crossover, VCP, Volume spike strategies "
            "across every constituent stock. Returns ranked BUY and SELL signals with entry/target/SL/R:R. "
            "Use for: 'intraday screener', 'scan Nifty 50 for buy signals', 'which BANK NIFTY stocks "
            "have buy signals', 'best intraday stocks today', 'top momentum plays', '/scan'."
        ),
        {
            "type": "object",
            "properties": {
                "index":            {"type": "string", "default": "NIFTY 50",
                                     "description": "NIFTY 50, NIFTY BANK, NIFTY IT, NIFTY 500, NIFTY PHARMA, etc."},
                "interval":         {"type": "string", "enum": ["5m","15m","30m","1h"], "default": "15m"},
                "strategies":       {"type": "array",
                                     "items": {"type": "string",
                                               "enum": ["macd","rsi","supertrend","bollinger","ema","vcp","volume"]}},
                "direction_filter": {"type": "string", "enum": ["buy","sell","all"], "default": "all"},
                "min_rr":           {"type": "number", "default": 1.5},
                "top_n":            {"type": "integer", "default": 5},
            },
            "required": [],
        },
    ),
    "scan_symbols_intraday": (
        scan_symbols_intraday,
        (
            "Scan a SPECIFIC LIST of NSE stocks for intraday signals — use when you already know which stocks to check. "
            "Works for ANY stock (not just index constituents). Ideal after EOD screening, breakout hunting, or "
            "when user asks 'check these stocks intraday', 'intraday setup for CHENNPETRO, NAM-INDIA, YATHARTH', "
            "'scan my watchlist intraday', 'which of these have buy signals'. "
            "Includes market-session awareness and EOD fallback for pre-market queries."
        ),
        {
            "type": "object",
            "properties": {
                "symbols":          {"type": "array", "items": {"type": "string"},
                                     "description": "List of NSE tickers, e.g. ['RELIANCE','CHENNPETRO']"},
                "interval":         {"type": "string", "enum": ["5m","15m","30m","1h"], "default": "15m"},
                "strategies":       {"type": "array",
                                     "items": {"type": "string",
                                               "enum": ["macd","rsi","supertrend","bollinger","ema","vcp","volume"]}},
                "direction_filter": {"type": "string", "enum": ["buy","sell","all"], "default": "all"},
                "min_rr":           {"type": "number", "default": 1.3},
                "top_n":            {"type": "integer", "default": 10},
            },
            "required": ["symbols"],
        },
    ),
    "resolve_symbol": (
        resolve_symbol,
        "Resolve a company name or alias to its NSE ticker symbol",
        {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
    ),
    "get_symbol_snapshot": (
        get_symbol_snapshot,
        "Get the latest DB snapshot for a symbol: stage, RS, RSI, trading signal, sector, price",
        {"type": "object", "properties": {"symbol": {"type": "string"}}, "required": ["symbol"]},
    ),
    "get_technical_setup": (
        get_technical_setup,
        "Compute technical indicators (RSI, ADX, MACD, supertrend, MAs, 52w position) from price history",
        {"type": "object", "properties": {"symbol": {"type": "string"}}, "required": ["symbol"]},
    ),
    "get_sector_context": (
        get_sector_context,
        "Get sector breadth, top stocks, and performance. Pass a stock SYMBOL (e.g. 'BHEL') to auto-detect its sector, or a sector name like 'Pharma'",
        {"type": "object", "properties": {"sector_or_symbol": {"type": "string"}}, "required": ["sector_or_symbol"]},
    ),
    "run_screener_query": (
        run_screener_query,
        "Run a screener: stage2, breakouts, supertrend_buy, strong_buy, new_entrants",
        {
            "type": "object",
            "properties": {
                "screen_type": {"type": "string", "enum": ["stage2","breakouts","supertrend_buy","strong_buy","new_entrants"]},
                "top_n": {"type": "integer", "default": 10},
            },
            "required": ["screen_type"],
        },
    ),
    "get_index_snapshot": (
        get_index_snapshot,
        "Get the latest OHLCV and 10-day trend for a Nifty index",
        {"type": "object", "properties": {"index_name": {"type": "string"}}, "required": ["index_name"]},
    ),
    "get_market_breadth": (
        get_market_breadth,
        "Get overall NSE market breadth: advance/decline, RS distribution, stage breakdown",
        {"type": "object", "properties": {}, "required": []},
    ),
    "get_global_market_assessment": (
        get_global_market_assessment,
        (
            "Assess global market cues for Indian markets from cached global index, FX, "
            "commodity, and correlation data. Returns risk regime, US/Asia/commodity/FX "
            "bias, India sector read-through, watch items, and Nifty correlation context. "
            "Use for global market assessment, overnight cues, US/Asia markets, crude, "
            "DXY, USDINR, and India read-through questions."
        ),
        {"type": "object", "properties": {}, "required": []},
    ),
    "get_intraday_source_health": (
        get_intraday_source_health,
        (
            "Check SQLite intraday source health. Reports whether intraday_ohlcv and "
            "related live tables exist, row counts, latest timestamps, freshness, and "
            "overall intraday status. Use before intraday calculations."
        ),
        {
            "type": "object",
            "properties": {
                "max_age_minutes": {"type": "integer", "default": 30},
            },
            "required": [],
        },
    ),
    "get_intraday_bars": (
        get_intraday_bars,
        (
            "Read OHLCV bars from the SQLite intraday_ohlcv table for one symbol and "
            "timeframe. Returns bars with source metadata and does not use EOD/yfinance fallback."
        ),
        {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "timeframe": {"type": "string", "enum": ["5m", "15m", "30m", "1h"], "default": "15m"},
                "lookback": {"type": "integer", "default": 120},
            },
            "required": ["symbol"],
        },
    ),
    "get_intraday_levels": (
        get_intraday_levels,
        (
            "Compute support, resistance, pivot, EMA, and latest close levels from "
            "SQLite intraday_ohlcv bars. Technical levels only; not a trade recommendation."
        ),
        {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "timeframe": {"type": "string", "enum": ["5m", "15m", "30m", "1h"], "default": "15m"},
            },
            "required": ["symbol"],
        },
    ),
    "compute_intraday_indicators": (
        compute_intraday_indicators,
        (
            "Compute RSI, MACD, Supertrend, EMA, Bollinger, ATR, volume ratio, and "
            "a research setup score from SQLite intraday_ohlcv bars. Does not use "
            "EOD/yfinance fallback."
        ),
        {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "timeframe": {"type": "string", "enum": ["5m", "15m", "30m", "1h"], "default": "15m"},
            },
            "required": ["symbol"],
        },
    ),
    "explain_intraday_setup": (
        explain_intraday_setup,
        (
            "Explain a symbol's SQLite-backed intraday setup using analyzer-style evidence, "
            "research-only labels LONG_SETUP/SHORT_SETUP/WATCH/AVOID/SETUP_INVALIDATED, "
            "technical target zones, and setup invalidation levels."
        ),
        {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "timeframe": {"type": "string", "enum": ["5m", "15m", "30m", "1h"], "default": "15m"},
            },
            "required": ["symbol"],
        },
    ),
    "run_intraday_screener": (
        run_intraday_screener,
        (
            "Run a SQLite-backed intraday screener over symbols in intraday_ohlcv. "
            "Screen types: momentum, breakouts, vcp, supertrend, levels, all. Returns "
            "research-only setup labels, support/resistance, invalidation, target zones, "
            "freshness, and source metadata."
        ),
        {
            "type": "object",
            "properties": {
                "screen_type": {"type": "string", "enum": ["momentum", "breakouts", "vcp", "supertrend", "levels", "all"], "default": "momentum"},
                "timeframe": {"type": "string", "enum": ["5m", "15m", "30m", "1h"], "default": "15m"},
                "min_score": {"type": "number", "default": 55},
                "top_n": {"type": "integer", "default": 10},
                "symbols": {"type": "array", "items": {"type": "string"}},
            },
            "required": [],
        },
    ),
    "get_data_health": (
        get_data_health,
        "Check freshness of all local data sources (CSV files, DB snapshots)",
        {"type": "object", "properties": {}, "required": []},
    ),
    "find_latest_report": (
        find_latest_report,
        "List available generated reports (HTML/CSV) by type keyword",
        {"type": "object", "properties": {"report_type": {"type": "string"}}, "required": []},
    ),
    "search_latest_catalysts": (
        search_latest_catalysts,
        "Search for recent news and catalysts for a stock symbol via web search",
        {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "max_results": {"type": "integer", "default": 5},
            },
            "required": ["symbol"],
        },
    ),
    "scrape_screener_in": (
        scrape_screener_in,
        (
            "Scrape screener.in for deep fundamental data: key ratios (P/E, P/B, ROE, ROCE, "
            "market-cap, dividend yield), Screener's pros/cons analysis, last 6 quarters of "
            "financials, 5-year annual P&L, peer comparison table, shareholding pattern, "
            "BSE corporate-announcement PDF links, annual-report PDF links. "
            "Use for 'fundamentals', 'ratios', 'financial statements', 'peers', 'valuation' queries."
        ),
        {"type": "object", "properties": {"symbol": {"type": "string"}}, "required": ["symbol"]},
    ),
    "search_yahoo_finance": (
        search_yahoo_finance,
        (
            "Fetch Yahoo Finance data for an NSE stock: current price stats (52-week range, "
            "day range, prev close) and up to 6 recent news articles with real URLs. "
            "Use for 'yahoo finance', 'YF news', 'latest news', or as a supplementary "
            "news source alongside search_latest_catalysts."
        ),
        {"type": "object", "properties": {"symbol": {"type": "string"}}, "required": ["symbol"]},
    ),
    "multi_source_web_search": (
        multi_source_web_search,
        (
            "Search multiple finance websites (moneycontrol.com, screener.in, "
            "economictimes.indiatimes.com, nseindia.com, bseindia.com) for a stock. "
            "Returns up to 4 real results per site with decoded URLs. "
            "Use for 'moneycontrol', 'concall', 'transcript', 'BSE filings', 'announcements', "
            "or when comprehensive multi-source research is needed."
        ),
        {
            "type": "object",
            "properties": {
                "symbol":       {"type": "string"},
                "company_name": {"type": "string", "description": "Full company name for better search"},
                "extra_query":  {"type": "string", "description": "Additional search terms e.g. 'concall Q4 2026'"},
            },
            "required": ["symbol"],
        },
    ),
    "comprehensive_stock_research": (
        comprehensive_stock_research,
        (
            "One-call deep research across ALL sources: screener.in fundamentals + Yahoo Finance "
            "stats + multi-site news search (moneycontrol, ET, NSE, BSE). Returns ratios, "
            "pros/cons, quarterly results, peer table, shareholding, filings, news, and direct "
            "deep-links to screener.in, NSE, BSE, Yahoo Finance pages. "
            "Use for broad 'research', 'full analysis', or when user asks for comprehensive info "
            "about a stock from multiple sources."
        ),
        {
            "type": "object",
            "properties": {
                "symbol":  {"type": "string"},
                "aspects": {
                    "type": "array",
                    "items": {"type": "string",
                              "enum": ["fundamentals","news","concalls","peers","filings","ratios","all"]},
                    "description": "Which aspects to fetch. Defaults to all.",
                },
            },
            "required": ["symbol"],
        },
    ),
    "get_portfolio_exposure": (
        get_portfolio_exposure,
        "Return portfolio holdings summary (total stocks, sector distribution, top holdings). Optionally filter by sector.",
        {
            "type": "object",
            "properties": {
                "sector": {"type": "string", "description": "Optional sector name to filter holdings"},
            },
            "required": [],
        },
    ),
    "find_portfolio_overlap": (
        find_portfolio_overlap,
        "Find portfolio holdings that also appear in a screener (stage2, supertrend_buy, all)",
        {
            "type": "object",
            "properties": {
                "screener": {
                    "type": "string",
                    "enum": ["stage2", "supertrend_buy", "all"],
                    "default": "stage2",
                },
            },
            "required": [],
        },
    ),
}


def call_tool(name: str, args: dict) -> dict:
    """Execute a registered tool by name with given arguments."""
    if name not in TOOL_REGISTRY:
        return {"error": f"Unknown tool: {name}"}
    fn = TOOL_REGISTRY[name][0]
    try:
        return fn(**args)
    except Exception as e:
        return {"error": str(e), "tool": name}


def openai_tool_schemas() -> list[dict]:
    """Return OpenAI-compatible tool schemas for all registered tools."""
    schemas = []
    for name, (_, description, params) in TOOL_REGISTRY.items():
        schemas.append({
            "type": "function",
            "function": {"name": name, "description": description, "parameters": params},
        })
    return schemas
