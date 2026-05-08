"""
terminal/tools.py — Read-only tool implementations for the NSE Agent Adda.

Each tool returns a plain dict (JSON-serialisable).  Tools must NOT mutate any
data, execute shell commands, or access the network beyond approved sources.
"""

from __future__ import annotations

import json
import re
import sqlite3
from difflib import SequenceMatcher
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

# ── F&O data and options analysis ────────────────────────────────────────────
from terminal.fno_data import (
    fetch_live_option_chain,
    fetch_live_futures,
    load_and_store_latest as _fno_load_latest,
    get_available_dates as _fno_available_dates,
    days_to_expiry,
    get_expiry_dates,
)
from terminal.options_analysis import (
    analyze_option_chain,
    analyze_futures,
    build_strategy,
    recommend_strategies,
    STRATEGY_CATALOG,
    analyze_buying_opportunity,
    scan_options_buying_opportunities,
    calc_expected_move,
    theta_decay_profile,
    calc_chain_ivs,
)

# ── Web research module (screener.in, Yahoo Finance, multi-site search) ───────
from terminal.web_research import (
    scrape_screener_in,
    search_yahoo_finance,
    multi_source_web_search,
    comprehensive_stock_research,
)

# ── Deep Search Engine ────────────────────────────────────────────────────────
from terminal.search_engine import (
    search_nse_announcements,
    search_corporate_actions,
    search_insider_trades,
    search_bse_filings,
    search_shareholding_analysis,
    search_analyst_coverage,
    search_concall_transcripts,
    search_sector_news,
    search_social_buzz,
    search_broker_research,
    search_mf_holdings,
    deep_search,
)

# ── Forensic accounting suite ─────────────────────────────────────────────────
from terminal.forensics import run_forensic_analysis, screen_forensic_watchlist

# ── Seasonal / macro modules ──────────────────────────────────────────────────
import sys as _sys
_sys.path.insert(0, str(Path(__file__).parent.parent))
from seasonal_heat_calendar import build_seasonal_heat_calendar, get_all_seasonal_signals
from economic_cycle import detect_economic_cycle_phase

# ── Chart module ─────────────────────────────────────────────────────────────
from terminal.charts import render_chart, render_html_chart, chart_summary

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


# F&O index alias mapping — maps common user names to NSE derivatives symbols
_FO_INDEX_ALIASES: dict[str, str] = {
    # MIDCPNIFTY (Nifty Midcap Select)
    "NIFTY MIDCAP":            "MIDCPNIFTY",
    "NIFTY MIDCAP 50":         "MIDCPNIFTY",
    "NIFTY MIDCAP SELECT":     "MIDCPNIFTY",
    "NIFTY MIDCAP100":         "MIDCPNIFTY",
    "NIFTY MIDCAP 100":        "MIDCPNIFTY",
    "MIDCAP NIFTY":            "MIDCPNIFTY",
    "MIDCPNIFTY":              "MIDCPNIFTY",
    # BANKNIFTY
    "NIFTY BANK":              "BANKNIFTY",
    "BANK NIFTY":              "BANKNIFTY",
    "BANKNIFTY":               "BANKNIFTY",
    # FINNIFTY
    "NIFTY FINANCIAL":         "FINNIFTY",
    "NIFTY FINANCIAL SERVICES": "FINNIFTY",
    "NIFTY FIN":               "FINNIFTY",
    "FINNIFTY":                "FINNIFTY",
    # NIFTY
    "NIFTY":                   "NIFTY",
    "NIFTY 50":                "NIFTY",
    "NIFTY50":                 "NIFTY",
    # NIFTY NEXT 50
    "NIFTY NEXT 50":           "NIFTYNXT50",
    "NIFTY NXT 50":            "NIFTYNXT50",
    "NIFTYNXT50":              "NIFTYNXT50",
}


def _all_symbols_map() -> dict[str, str]:
    """Return {normalized_name: symbol, symbol: symbol} for fuzzy resolution."""
    # Start with F&O index aliases — always available
    mapping: dict[str, str] = dict(_FO_INDEX_ALIASES)

    if not DB_PATH.exists():
        return mapping
    conn = _db_conn()
    rows = conn.execute(
        "SELECT DISTINCT symbol, company_name FROM stage_snapshots "
        "WHERE snapshot_date=(SELECT MAX(snapshot_date) FROM stage_snapshots)"
    ).fetchall()
    conn.close()
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


def _lookup_key(value: str) -> str:
    """Normalize symbol/name text for local symbol matching."""
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def _resolve_local_symbol(query: str) -> dict:
    """Resolve a symbol/name from local DB aliases without network access."""
    q = str(query or "").strip().upper()
    q_key = _lookup_key(q)
    if not q_key:
        return {"symbol": None, "confidence": "none", "query": query}

    mapping = _all_symbols_map()
    if q in mapping:
        return {"symbol": mapping[q], "confidence": "exact", "query": query}

    normalized: dict[str, tuple[str, str]] = {}
    for key, sym in mapping.items():
        key_norm = _lookup_key(key)
        if key_norm:
            normalized.setdefault(key_norm, (key, sym))

    if q_key in normalized:
        key, sym = normalized[q_key]
        return {"symbol": sym, "confidence": "exact", "query": query, "matched": key}

    contains_hits: list[tuple[int, str, str]] = []
    for key_norm, (key, sym) in normalized.items():
        if q_key in key_norm or key_norm in q_key:
            contains_hits.append((abs(len(key_norm) - len(q_key)), key, sym))
    if contains_hits:
        contains_hits.sort(key=lambda x: x[0])
        best = contains_hits[0][2]
        return {
            "symbol": best,
            "confidence": "fuzzy",
            "query": query,
            "candidates": list(dict.fromkeys(hit[2] for hit in contains_hits[:5])),
        }

    near_hits: list[tuple[float, str, str]] = []
    for key_norm, (key, sym) in normalized.items():
        if len(key_norm) < 4 or q_key[:4] != key_norm[:4]:
            continue
        ratio = SequenceMatcher(None, q_key, key_norm).ratio()
        if ratio >= 0.84:
            near_hits.append((ratio, key, sym))
    if near_hits:
        near_hits.sort(key=lambda x: x[0], reverse=True)
        best = near_hits[0][2]
        return {
            "symbol": best,
            "confidence": "near-match",
            "query": query,
            "candidates": list(dict.fromkeys(hit[2] for hit in near_hits[:5])),
        }

    return {"symbol": None, "confidence": "none", "query": query}


def _canonical_symbol(symbol: str) -> str:
    resolved = _resolve_local_symbol(symbol)
    return str(resolved.get("symbol") or symbol).strip().upper()


# ─────────────────────────────────────────────────────────────────────────────
# Tool functions (all return dict)
# ─────────────────────────────────────────────────────────────────────────────

def resolve_symbol(query: str) -> dict:
    """Resolve a company name / partial name / alias to its NSE symbol.

    Tries local DB first, then falls back to NSE live search API.
    """
    import requests as _req
    q = query.strip().upper()
    local = _resolve_local_symbol(q)
    if local.get("symbol"):
        return local

    # Fall back to NSE live search API
    try:
        s   = _get_live_session()
        url = f"https://www.nseindia.com/api/search?q={_req.utils.quote(query)}&type=equity"
        r   = s.get(url, timeout=10)
        r.raise_for_status()
        results = r.json().get("results", [])
        if results:
            top = results[0]
            return {
                "symbol":     top.get("symbol"),
                "name":       top.get("symbol_info"),
                "confidence": "nse-search",
                "query":      query,
                "candidates": [x.get("symbol") for x in results[:5]],
            }
    except Exception:
        pass

    return {"symbol": None, "confidence": "none", "query": query,
            "error": f"No NSE symbol found for '{query}'"}


def get_symbol_snapshot(symbol: str) -> dict:
    """Get latest EOD snapshot for a symbol: price, stage, RS, RSI, signals, sector."""
    sym = _canonical_symbol(symbol)
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
    sym = _canonical_symbol(symbol)
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
    q = _canonical_symbol(sector_or_symbol)
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
    """Run a pre-built EOD screener from the DB snapshot data.

    screen_type options:
      Original  : stage2, breakouts, supertrend_buy, strong_buy, new_entrants
      New EOD   : momentum_52w, high_rs, turnaround, stage1_base, tight_range, oversold_bounce
    """
    if not DB_PATH.exists():
        return {"error": "DB not available"}

    conn = _db_conn()
    snap_date = _latest_snapshot_date()

    _base_cols = (
        "symbol, company_name, stage_score, investment_score, price, "
        "relative_strength, change_1m_pct, rsi, trading_signal, sector"
    )
    _base_from = "FROM stage_snapshots WHERE snapshot_date=?"

    query_map: dict[str, str | tuple] = {
        # ── Original screeners ────────────────────────────────────────────────
        "stage2": (
            f"SELECT {_base_cols} {_base_from} AND stage='STAGE_2' "
            "ORDER BY investment_score DESC"
        ),
        "breakouts": (
            f"SELECT {_base_cols} {_base_from} AND stage='STAGE_2' "
            "AND COALESCE(change_1m_pct, 0) > 3.0 "
            "AND COALESCE(rsi, 0) BETWEEN 55 AND 85 "
            "AND supertrend_state='BULLISH' "
            "ORDER BY investment_score DESC, change_1m_pct DESC"
        ),
        "supertrend_buy": (
            "SELECT symbol, company_name, stage_score, investment_score, price, "
            "relative_strength, change_1d_pct, rsi, trading_signal, sector "
            f"{_base_from} AND supertrend_state='BULLISH' "
            "AND stage IN ('STAGE_1','STAGE_2') "
            "ORDER BY investment_score DESC, rsi DESC"
        ),
        "strong_buy": (
            f"SELECT {_base_cols} {_base_from} AND trading_signal IN ('STRONG_BUY','BUY','HOLD') "
            "AND stage='STAGE_2' AND supertrend_state='BULLISH' "
            "ORDER BY investment_score DESC"
        ),
        "new_entrants": (
            "SELECT s.symbol, s.company_name, s.stage_score, s.investment_score, "
            "s.price, s.relative_strength, s.change_1m_pct, s.rsi, s.trading_signal, s.sector "
            "FROM stage_snapshots s "
            "LEFT JOIN stage_changes c ON s.symbol=c.symbol AND c.stage_now='STAGE_2' "
            "AND c.stage_prev != 'STAGE_2' "
            "WHERE s.snapshot_date=? AND s.stage='STAGE_2' "
            "AND (c.change_date >= date(?, '-14 days') OR c.change_date IS NULL) "
            "ORDER BY s.investment_score DESC"
        ),

        # ── New EOD screeners ─────────────────────────────────────────────────

        # Stocks within 5% of their 52-week high with positive RS and upward momentum.
        # Classic "buy strength" — trend-following stocks leading the market.
        "momentum_52w": (
            f"SELECT {_base_cols} {_base_from} AND stage='STAGE_2' "
            "AND COALESCE(change_1m_pct, 0) > 5.0 "
            "AND COALESCE(rsi, 0) BETWEEN 50 AND 85 "
            "AND supertrend_state='BULLISH' "
            "ORDER BY change_1m_pct DESC, investment_score DESC"
        ),

        # Top RS ranked stocks — market leaders by relative strength score.
        # RS > 1.15 means outperforming 85%+ of the market.
        "high_rs": (
            f"SELECT {_base_cols} {_base_from} "
            "AND stage IN ('STAGE_2', 'STAGE_1') "
            "AND COALESCE(change_1m_pct, 0) > 8.0 "
            "AND COALESCE(rsi, 0) >= 55 "
            "ORDER BY change_1m_pct DESC, investment_score DESC"
        ),

        # Turnaround candidates: down >20% from recent highs but showing recovery.
        # RSI recovering from oversold + positive recent change signals base building.
        "turnaround": (
            f"SELECT {_base_cols} {_base_from} "
            "AND stage IN ('STAGE_1', 'STAGE_2') "
            "AND COALESCE(change_1m_pct, 0) > 5.0 "
            "AND COALESCE(rsi, 0) BETWEEN 40 AND 65 "
            "AND COALESCE(investment_score, 0) < 60 "
            "ORDER BY change_1m_pct DESC, investment_score DESC"
        ),

        # Stage 1 basing stocks — consolidating sideways before a potential breakout.
        # Low RS + flat price action = coiled spring. Watch for volume expansion.
        "stage1_base": (
            f"SELECT {_base_cols} {_base_from} AND stage='STAGE_1' "
            "AND COALESCE(rsi, 0) BETWEEN 40 AND 60 "
            "AND ABS(COALESCE(change_1m_pct, 0)) < 5.0 "
            "ORDER BY investment_score DESC, relative_strength DESC"
        ),

        # Tight range consolidation: low volatility + near recent highs + good RS.
        # VCP-like setup — volatility contraction precedes explosive moves.
        "tight_range": (
            f"SELECT {_base_cols} {_base_from} AND stage='STAGE_2' "
            "AND supertrend_state='BULLISH' "
            "AND ABS(COALESCE(change_1w_pct, 0)) < 2.0 "
            "AND COALESCE(rsi, 0) BETWEEN 45 AND 65 "
            "ORDER BY investment_score DESC, rsi DESC"
        ),

        # Oversold stocks in Stage 2 uptrend — mean-reversion bounce candidates.
        # RSI below 40 in an otherwise bullish stage = potential entry dip.
        "oversold_bounce": (
            f"SELECT {_base_cols} {_base_from} AND stage='STAGE_2' "
            "AND COALESCE(rsi, 0) < 40 "
            "AND supertrend_state='BULLISH' "
            "ORDER BY rsi ASC, investment_score DESC"
        ),
    }

    _multi_param_keys = {"new_entrants"}
    screen_key = screen_type.lower()
    if screen_key not in query_map:
        available = sorted(query_map.keys())
        return {"error": f"Unknown screener: {screen_type}", "available": available}

    sql = query_map[screen_key]
    cols = ["symbol","company_name","stage_score","investment_score","price",
            "relative_strength","change","rsi","trading_signal","sector"]

    if screen_key in _multi_param_keys:
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

    _descriptions = {
        "stage2":           "Stage 2 uptrend stocks — William O'Neil buy zone",
        "breakouts":        "Stage 2 stocks breaking out with rising RS + RSI ≥ 55",
        "supertrend_buy":   "Supertrend BUY state stocks",
        "strong_buy":       "STRONG_BUY signal stocks",
        "new_entrants":     "Stage 2 new entrants in the last 14 days",
        "momentum_52w":     "Near 52W high momentum leaders — RS ≥ 1.0, 1M chg > 2%",
        "high_rs":          "Top relative strength leaders — RS ≥ 1.15",
        "turnaround":       "Recovery setups — dip + rising momentum + RS improving",
        "stage1_base":      "Stage 1 basing stocks — coiled, waiting for breakout",
        "tight_range":      "Tight weekly range + RS ≥ 1.0 — VCP-like consolidation",
        "oversold_bounce":  "Stage 2 stocks with RSI < 40 — dip-buy in uptrend",
    }

    return {
        "screen_type":    screen_key,
        "description":    _descriptions.get(screen_key, ""),
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

    asset_cols = [c for c in df.columns if c != "Date"]
    # Convert all asset columns to numeric once for efficiency
    num_df = df[asset_cols].apply(pd.to_numeric, errors="coerce")

    moves: dict[str, dict[str, Any]] = {}
    for asset in asset_cols:
        col = num_df[asset].dropna()
        if len(col) < 2:
            continue
        # Use the most-recent valid row for this asset (not necessarily df.iloc[-1])
        latest_idx = col.index[-1]
        prev_idx   = col.index[-2]
        latest_val = col.iloc[-1]
        prev_val   = col.iloc[-2]
        if prev_val == 0:
            continue

        pct_change = round((latest_val / prev_val - 1) * 100, 2)
        moves[asset] = {
            "price":      round(float(latest_val), 2),
            "pct_change": pct_change,
            "as_of":      str(df.loc[latest_idx, "Date"].date()),
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

    # Determine the "as_of" date: latest date that has any data
    last_dates = {asset: m["as_of"] for asset, m in moves.items()}
    as_of = max(last_dates.values()) if last_dates else str(df.iloc[-1]["Date"].date())

    return {
        "risk_regime": risk_regime,
        "as_of": as_of,
        "asset_dates": last_dates,   # per-asset last-available date (useful when markets are closed)
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
    """Run an intraday screener (SQLite-backed or live yfinance fallback).

    Screen types:
      Original : momentum, breakouts, vcp, supertrend, levels, all
      New      : opening_range_breakout, gap_and_go, macd_crossover,
                 rsi_divergence, bb_squeeze, vwap_reclaim
    """
    screen_key = screen_type.lower().strip()
    supported = {
        # original
        "momentum", "breakouts", "vcp", "supertrend", "levels", "all",
        # new
        "opening_range_breakout", "gap_and_go", "macd_crossover",
        "rsi_divergence", "bb_squeeze", "vwap_reclaim",
    }
    if screen_key not in supported:
        return {"error": f"Unknown intraday screener: {screen_type}", "supported": sorted(supported)}

    # ── SQLite unavailable → live yfinance fallback ─────────────────────────
    if not DB_PATH.exists() or not _sqlite_table_exists("intraday_ohlcv"):
        strategy_map = {
            # original
            "breakouts":              ["ema", "volume", "macd"],
            "momentum":               ["macd", "rsi", "supertrend"],
            "vcp":                    ["vcp", "volume"],
            "supertrend":             ["supertrend"],
            "levels":                 ["ema", "bollinger"],
            "all":                    None,
            # new intraday screeners
            "opening_range_breakout": ["ema", "volume"],   # ORB = EMA crossover + volume
            "gap_and_go":             ["volume", "macd"],  # gap continuation via vol + MACD
            "macd_crossover":         ["macd"],            # pure MACD signal line cross
            "rsi_divergence":         ["rsi", "bollinger"],# RSI extreme + Bollinger
            "bb_squeeze":             ["bollinger", "volume"],  # BB bandwidth squeeze
            "vwap_reclaim":           ["ema", "rsi"],      # VWAP proxy via short EMA + RSI
        }

        _descriptions = {
            "opening_range_breakout": "Opening Range Breakout — price breaks above/below first 15-30min range with volume",
            "gap_and_go":             "Gap & Go — stocks gapping up/down continuing with volume + MACD momentum",
            "macd_crossover":         "MACD Crossover — fresh MACD signal line cross (bullish or bearish)",
            "rsi_divergence":         "RSI Divergence — RSI extreme reversal setup with Bollinger mean-reversion",
            "bb_squeeze":             "Bollinger Squeeze — low-volatility band squeeze followed by expansion breakout",
            "vwap_reclaim":           "VWAP Reclaim — price reclaiming short EMA (VWAP proxy) from below (bullish) or losing it (bearish)",
            "momentum":               "MACD + RSI + Supertrend momentum alignment",
            "breakouts":              "EMA crossover + volume + MACD breakout",
            "vcp":                    "Volatility Contraction Pattern — tight consolidation before expansion",
            "supertrend":             "Supertrend state flip or continuation",
            "levels":                 "Support/Resistance levels with EMA + Bollinger context",
            "all":                    "All strategies combined",
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
        result["screen_type"]    = screen_key
        result["description"]    = _descriptions.get(screen_key, "")
        result["data_mode"]      = "live-yfinance-fallback"
        result["fallback_note"]  = (
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
            """Extract real URL from DuckDuckGo redirect (/l/?uddg=<encoded>).
            Returns '' for DDG ad/tracking URLs (y.js) so they get filtered out."""
            import urllib.parse
            if not raw:
                return ""
            # Add scheme if missing
            if raw.startswith("//"):
                raw = "https:" + raw
            # DDG ad tracking URLs — opaque Bing redirect chains, not useful results
            if "duckduckgo.com/y.js" in raw:
                return ""
            parsed = urllib.parse.urlparse(raw)
            qs = urllib.parse.parse_qs(parsed.query)
            if "uddg" in qs:
                return qs["uddg"][0]
            return raw

        results = []
        for r in parser.results[:max_results]:
            if r.get("title") and len(r["title"]) > 5:
                decoded_url = _decode_url(r.get("url", ""))
                if not decoded_url:  # skip DDG ad/tracking URLs
                    continue
                results.append({
                    "title":   r.get("title", ""),
                    "url":     decoded_url,
                    "snippet": r.get("snippet", ""),
                })

        # Fetch article content for top results — gives LLM real text to summarize
        for item in results[:3]:
            url = item.get("url", "")
            if not url:
                continue
            try:
                art_resp = requests.get(
                    url,
                    headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},
                    timeout=6,
                    allow_redirects=True,
                )
                if art_resp.status_code == 200 and "text/html" in art_resp.headers.get("Content-Type", ""):
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(art_resp.text, "lxml")
                    # Remove noise: scripts, styles, nav, ads, footers
                    for tag in soup(["script", "style", "nav", "footer", "header",
                                     "aside", "iframe", "form", "noscript"]):
                        tag.decompose()
                    # Extract article body — try common selectors first
                    body = (
                        soup.select_one("article") or
                        soup.select_one('[class*="article"]') or
                        soup.select_one('[class*="story"]') or
                        soup.select_one('[class*="content"]') or
                        soup.select_one("main") or
                        soup.body
                    )
                    if body:
                        text = body.get_text(separator="\n", strip=True)
                        # Clean up: collapse whitespace, take first ~2000 chars
                        import re as _re
                        text = _re.sub(r'\n{3,}', '\n\n', text)
                        text = _re.sub(r'[ \t]{2,}', ' ', text)
                        item["article_text"] = text[:2000]
            except Exception:
                pass  # Fetch failed — snippet is still available

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


def fetch_article_content(url: str, max_chars: int = 3000) -> dict:
    """Fetch and extract readable text from a news article URL.

    Strips navigation, ads, footers — returns clean article body text.
    Use this to read full articles found via search tools when you need
    deeper context for summary and opinion.
    """
    import requests
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},
            timeout=8,
            allow_redirects=True,
        )
        if resp.status_code != 200:
            return {"url": url, "error": f"HTTP {resp.status_code}"}
        if "text/html" not in resp.headers.get("Content-Type", ""):
            return {"url": url, "error": "Not an HTML page"}

        from bs4 import BeautifulSoup
        import re as _re
        soup = BeautifulSoup(resp.text, "lxml")
        # Remove noise
        for tag in soup(["script", "style", "nav", "footer", "header",
                         "aside", "iframe", "form", "noscript"]):
            tag.decompose()
        # Try common article selectors, fall back to body
        body = (
            soup.select_one("article") or
            soup.select_one('[class*="article"]') or
            soup.select_one('[class*="story"]') or
            soup.select_one('[class*="content"]') or
            soup.select_one("main") or
            soup.body
        )
        if not body:
            return {"url": url, "error": "No readable content found"}

        text = body.get_text(separator="\n", strip=True)
        text = _re.sub(r'\n{3,}', '\n\n', text)
        text = _re.sub(r'[ \t]{2,}', ' ', text)

        # Extract title
        title = ""
        title_tag = soup.find("title")
        if title_tag:
            title = title_tag.get_text(strip=True)

        return {
            "url": url,
            "title": title,
            "text": text[:max_chars],
            "truncated": len(text) > max_chars,
            "total_chars": len(text),
        }
    except Exception as e:
        return {"url": url, "error": str(e)}


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

    Returns current price, VWAP, day OHLC, volume, % change, 52-week range,
    circuit limits, sector P/E, and last-update timestamp — all from NSE live.
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
        meta  = d.get("metadata", {})
        price = d.get("priceInfo", {})
        week  = price.get("weekHighLow", {})
        idhl  = price.get("intraDayHighLow", {})

        last   = price.get("lastPrice",     idhl.get("value"))
        open_  = price.get("open",          None)
        high   = idhl.get("max",            None)
        low    = idhl.get("min",            None)
        prev   = price.get("previousClose", None)
        chg    = price.get("change",        None)
        pchg   = price.get("pChange",       None)
        vwap   = price.get("vwap",          None)

        if last is None:
            return {"symbol": sym, "error": "No price data returned"}

        # Fetch trade info (volume, value, market cap) via separate section call
        vol_lakh = None; val_cr = None; mkt_cap_cr = None
        try:
            r2 = s.get(
                f"https://www.nseindia.com/api/quote-equity?symbol={requests.utils.quote(sym)}&section=trade_info",
                timeout=8,
            )
            ti = r2.json().get("marketDeptOrderBook", {}).get("tradeInfo", {})
            vol_lakh   = ti.get("totalTradedVolume")   # in lakh shares
            val_cr     = ti.get("totalTradedValue")    # in crores
            mkt_cap_cr = ti.get("totalMarketCap")      # in crores
        except Exception:
            pass

        return {
            "symbol":          sym,
            "name":            info.get("companyName", meta.get("symbol", sym)),
            "series":          meta.get("series", "EQ"),
            "last_price":      last,
            "open":            open_,
            "day_high":        high,
            "day_low":         low,
            "vwap":            vwap,
            "prev_close":      prev,
            "change":          round(chg,  2) if chg  is not None else None,
            "pct_change":      round(pchg, 2) if pchg is not None else None,
            "volume":          vol_lakh,        # in lakh shares
            "volume_shares":   round(vol_lakh * 1e5) if vol_lakh else None,
            "traded_value_cr": val_cr,
            "market_cap_cr":   mkt_cap_cr,
            "52w_high":        week.get("max"),
            "52w_low":         week.get("min"),
            "52w_high_date":   week.get("maxDate"),
            "52w_low_date":    week.get("minDate"),
            "lower_circuit":   price.get("lowerCP"),
            "upper_circuit":   price.get("upperCP"),
            "sector":          meta.get("industry"),
            "sector_pe":       meta.get("pdSectorPe"),
            "stock_pe":        meta.get("pdSymbolPe"),
            "indices":         meta.get("pdSectorIndAll", [])[:5],
            "as_of":           meta.get("lastUpdateTime",
                                        datetime.now().strftime("%d-%b-%Y %H:%M:%S")),
            "source":          "NSE live API (real-time)",
        }
    except Exception as e:
        return {"symbol": sym, "error": str(e)}


def get_nse_quotes(symbols: list[str]) -> dict:
    """Fetch live NSE prices for multiple symbols in parallel.

    Returns a dict keyed by symbol with price, % change, VWAP, volume.
    Faster than calling get_live_quote() sequentially.
    Use for: 'prices of RELIANCE, TCS, INFY', 'watchlist prices',
    'how are these stocks doing: X, Y, Z'.

    Args:
        symbols: List of NSE tickers, up to 20.
    """
    import requests
    from concurrent.futures import ThreadPoolExecutor, as_completed

    syms    = [s.strip().upper() for s in symbols[:20] if s.strip()]
    session = _get_live_session()

    def _fetch(sym: str) -> tuple[str, dict]:
        try:
            url = f"https://www.nseindia.com/api/quote-equity?symbol={requests.utils.quote(sym)}"
            r   = session.get(url, timeout=10)
            r.raise_for_status()
            d     = r.json()
            meta  = d.get("metadata", {})
            price = d.get("priceInfo", {})
            idhl  = price.get("intraDayHighLow", {})
            trade = d.get("marketDeptOrderBook", {}).get("tradeInfo", {})
            last  = price.get("lastPrice", idhl.get("value"))
            return sym, {
                "symbol":     sym,
                "name":       d.get("info", {}).get("companyName", sym),
                "last_price": last,
                "change":     round(price.get("change", 0), 2),
                "pct_change": round(price.get("pChange", 0), 2),
                "day_high":   idhl.get("max"),
                "day_low":    idhl.get("min"),
                "vwap":       price.get("vwap"),
                "volume":     trade.get("totalTradedVolume"),
                "prev_close": price.get("previousClose"),
                "lower_circuit": price.get("lowerCP"),
                "upper_circuit": price.get("upperCP"),
                "sector":     meta.get("industry"),
                "sector_pe":  meta.get("pdSectorPe"),
                "stock_pe":   meta.get("pdSymbolPe"),
                "as_of":      meta.get("lastUpdateTime"),
            }
        except Exception as e:
            return sym, {"symbol": sym, "error": str(e)}

    results: dict = {}
    with ThreadPoolExecutor(max_workers=6) as ex:
        futures = {ex.submit(_fetch, s): s for s in syms}
        for fut in as_completed(futures):
            sym, data = fut.result()
            results[sym] = data

    return {
        "quotes":     results,
        "count":      len(results),
        "as_of":      datetime.now().strftime("%d-%b-%Y %H:%M:%S"),
        "source":     "NSE live API (real-time, parallel fetch)",
    }


def nse_search(query: str, top_n: int = 5) -> dict:
    """Search NSE by company name or partial symbol → returns matching stocks with live price.

    Useful for: 'search for Tata companies', 'find steel stocks on NSE',
    'what is the symbol for Adani Ports', 'price of Larsen and Toubro'.

    Args:
        query: Company name, partial name, or keyword (e.g. 'Tata Steel', 'HDFC').
        top_n: Max results to return.
    """
    import requests
    try:
        s   = _get_live_session()
        url = f"https://www.nseindia.com/api/search?q={requests.utils.quote(query)}&type=equity"
        r   = s.get(url, timeout=10)
        r.raise_for_status()
        results = r.json().get("results", [])[:top_n]
        if not results:
            return {"query": query, "results": [], "error": "No matches found on NSE"}

        # Enrich with live prices for top results
        syms   = [x["symbol"] for x in results if x.get("symbol")]
        prices = {}
        if syms:
            batch = get_nse_quotes(syms[:5])
            prices = batch.get("quotes", {})

        enriched = []
        for item in results:
            sym  = item.get("symbol", "")
            info = item.get("symbol_info", "")
            q    = prices.get(sym, {})
            enriched.append({
                "symbol":     sym,
                "name":       info,
                "last_price": q.get("last_price"),
                "pct_change": q.get("pct_change"),
                "sector":     q.get("sector"),
                "series":     item.get("activeSeries", ["EQ"])[0],
            })

        return {
            "query":   query,
            "results": enriched,
            "source":  "NSE search API + live prices",
        }
    except Exception as e:
        return {"query": query, "error": str(e)}


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


# ── E4: Event-Driven Alert Engine ────────────────────────────────────────────

def get_upcoming_events(
    symbols: list[str] | None = None,
    index: str = "NIFTY 50",
    days_ahead: int = 30,
    event_types: list[str] | None = None,
) -> dict:
    """
    E4 Event-Driven Alert Engine: fetch upcoming corporate action events for
    a list of symbols or an entire index.

    Event types tracked:
      • Dividend  — ex-dividend dates, record dates, amount
      • Bonus Issue — bonus ratio (e.g. 1:1, 2:1)
      • Stock Split  — split ratio and record date
      • Rights Issue — entitlement and pricing
      • AGM / EGM   — Annual / Extraordinary General Meeting dates
      • Board Meeting — typically announcing results or dividends
      • Results Calendar — Q1/Q2/Q3/Q4 earnings announcement dates

    Args:
        symbols:     Explicit list of NSE tickers (e.g. ['TCS', 'INFY']).
                     If None, fetches top symbols from the Nifty 50 DB snapshot.
        index:       Index name for auto-symbol lookup when symbols=None.
        days_ahead:  Window in calendar days to consider events "upcoming".
        event_types: Filter to specific types e.g. ['Dividend', 'Results'].
                     None means return all types.

    Returns:
        {
          "events_by_date":  {date_str: [events]},
          "events_by_type":  {type_str: [events]},
          "upcoming":        [...sorted by ex_date...],
          "total":           int,
          "next_7_days":     [...],
          "next_30_days":    [...],
        }
    """
    import urllib.parse
    from datetime import date, timedelta

    today = date.today()
    cutoff = today + timedelta(days=days_ahead)

    # Get symbols list
    if not symbols:
        symbols = _get_index_symbols(index)[:50]  # top 50 from index

    all_events: list[dict[str, Any]] = []

    # Batch NSE corporate actions API calls
    sess = _get_live_session()

    def _fetch_actions(sym: str) -> list[dict]:
        url = (
            f"https://www.nseindia.com/api/corporates-corporateActions"
            f"?index=equities&symbol={urllib.parse.quote(sym)}&issuer="
        )
        try:
            r = sess.get(url, timeout=8)
            if not r.ok:
                return []
            items = r.json()
            if isinstance(items, dict):
                items = items.get("data", [])
            return items or []
        except Exception:
            return []

    from concurrent.futures import ThreadPoolExecutor, as_completed as _as_completed
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(_fetch_actions, sym): sym for sym in (symbols or [])}
        for fut in _as_completed(futures):
            sym = futures[fut]
            try:
                items = fut.result()
                for item in items:
                    subject = str(item.get("subject", "")).strip()
                    ex_date_str = item.get("exDate", "") or item.get("ex_date", "")
                    rec_date_str = item.get("recDate", "") or item.get("rec_date", "")

                    # Parse date
                    ex_date = None
                    for fmt in ("%d-%b-%Y", "%Y-%m-%d", "%d/%m/%Y", "%b %d %Y"):
                        try:
                            ex_date = datetime.strptime(ex_date_str, fmt).date()
                            break
                        except (ValueError, TypeError):
                            continue

                    # Classify event type
                    subj_lower = subject.lower()
                    if "dividend" in subj_lower:
                        etype = "Dividend"
                    elif "bonus" in subj_lower:
                        etype = "Bonus"
                    elif "split" in subj_lower or "sub-division" in subj_lower:
                        etype = "Split"
                    elif "rights" in subj_lower:
                        etype = "Rights"
                    elif "agm" in subj_lower or "annual general" in subj_lower:
                        etype = "AGM"
                    elif "egm" in subj_lower or "extra" in subj_lower:
                        etype = "EGM"
                    elif "board meeting" in subj_lower:
                        etype = "Board Meeting"
                    elif "result" in subj_lower:
                        etype = "Results"
                    else:
                        etype = "Corporate Action"

                    if event_types and etype not in event_types:
                        continue

                    days_until = (ex_date - today).days if ex_date else None

                    all_events.append({
                        "symbol":      sym,
                        "type":        etype,
                        "subject":     subject,
                        "ex_date":     ex_date_str,
                        "ex_date_obj": ex_date,
                        "record_date": rec_date_str,
                        "face_value":  item.get("faceVal"),
                        "series":      item.get("series", "EQ"),
                        "days_until":  days_until,
                        "is_upcoming": (
                            ex_date is not None and today <= ex_date <= cutoff
                        ),
                    })
            except Exception:
                pass

    # Filter to upcoming + sort by date
    upcoming = sorted(
        [e for e in all_events if e.get("is_upcoming")],
        key=lambda x: x["ex_date_obj"] or date.max,
    )

    # Clean up non-serializable date objects
    for e in all_events:
        e.pop("ex_date_obj", None)
    for e in upcoming:
        e.pop("ex_date_obj", None)

    # Group by date
    events_by_date: dict[str, list] = {}
    for ev in upcoming:
        d = ev["ex_date"]
        events_by_date.setdefault(d, []).append(ev)

    # Group by type
    events_by_type: dict[str, list] = {}
    for ev in upcoming:
        events_by_type.setdefault(ev["type"], []).append(ev)

    # Next 7 days
    week_cutoff = today + timedelta(days=7)
    next_7 = [
        e for e in upcoming
        if e.get("days_until") is not None and 0 <= e["days_until"] <= 7
    ]

    return {
        "as_of":          today.isoformat(),
        "days_window":    days_ahead,
        "symbols_scanned": len(symbols or []),
        "total":          len(upcoming),
        "events_by_date": events_by_date,
        "events_by_type": events_by_type,
        "upcoming":       upcoming,
        "next_7_days":    next_7,
        "types_found":    list(events_by_type.keys()),
        "source":         "NSE Corporate Actions API (live)",
    }


def get_event_calendar_summary(
    index: str = "NIFTY 50",
    days_ahead: int = 14,
) -> dict:
    """
    Quick event calendar overview for an index — upcoming dividends, splits,
    bonuses, results, and board meetings in the next N days.

    Args:
        index:      Index name (e.g. 'NIFTY 50', 'NIFTY NEXT 50', 'NIFTY 500').
        days_ahead: Calendar days to look ahead (default 14).

    Returns compact event summary suitable for terminal sidebar display.
    """
    full = get_upcoming_events(index=index, days_ahead=days_ahead)
    if full.get("error"):
        return full

    # Compact view for each upcoming event
    compact = []
    for ev in full.get("upcoming", []):
        compact.append({
            "symbol":    ev["symbol"],
            "type":      ev["type"],
            "ex_date":   ev["ex_date"],
            "days_away": ev.get("days_until"),
            "detail":    ev["subject"][:80],
        })

    type_counts = {t: len(v) for t, v in full.get("events_by_type", {}).items()}

    return {
        "index":         index,
        "days_ahead":    days_ahead,
        "total_events":  full.get("total", 0),
        "event_counts":  type_counts,
        "events":        compact,
        "next_7_days":   full.get("next_7_days", []),
        "source":        full.get("source"),
    }


def _get_index_symbols(index: str = "NIFTY 50", top_n: int = 50) -> list[str]:
    """Get symbols for an index from the DB snapshot."""
    syms: list[str] = []
    try:
        if DB_PATH.exists():
            conn = _db_conn()
            idx_lower = index.lower()
            rows = conn.execute(
                "SELECT DISTINCT symbol FROM stage_snapshots "
                "WHERE LOWER(sector) != '' "
                "AND snapshot_date = (SELECT MAX(snapshot_date) FROM stage_snapshots) "
                "ORDER BY investment_score DESC NULLS LAST LIMIT ?",
                (top_n,),
            ).fetchall()
            conn.close()
            syms = [r[0] for r in rows]
    except Exception:
        pass
    # Fallback to a small hardcoded Nifty 50 subset
    if not syms:
        syms = [
            "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "HINDUNILVR",
            "ITC", "SBIN", "BHARTIARTL", "BAJFINANCE", "KOTAKBANK", "LT",
            "AXISBANK", "ASIANPAINT", "MARUTI", "TITAN", "SUNPHARMA", "WIPRO",
            "ULTRACEMCO", "HCLTECH", "NESTLEIND", "POWERGRID", "NTPC",
            "TATAMOTORS", "TATASTEEL", "M&M", "TECHM", "ONGC", "DRREDDY",
            "DIVISLAB", "ADANIPORTS", "BAJAJFINSV", "CIPLA", "HEROMOTOCO",
            "EICHERMOT", "GRASIM", "BRITANNIA", "COALINDIA", "INDUSINDBK",
            "JSWSTEEL", "BPCL", "APOLLOHOSP", "TATACONSUM", "LTIM",
            "HINDALCO", "UPL", "SBILIFE", "HDFCLIFE", "BAJAJ-AUTO", "VEDL",
        ][:top_n]
    return syms


# ── B3: Sectoral Heat Calendar ────────────────────────────────────────────────

_SECTOR_INDEX_MAP = {
    "NIFTY IT":                 "IT",
    "NIFTY BANK":               "Banking",
    "NIFTY PHARMA":             "Pharma",
    "NIFTY AUTO":               "Auto",
    "NIFTY FMCG":               "FMCG",
    "NIFTY METAL":              "Metals",
    "NIFTY REALTY":             "Realty",
    "NIFTY ENERGY":             "Energy",
    "NIFTY FINANCIAL SERVICES": "Financials",
    "NIFTY INFRA":              "Infra",
}

# yfinance tickers for NSE sector indices (when local CSV lacks them)
_SECTOR_YF_MAP = {
    "NIFTY IT":                 "^CNXIT",
    "NIFTY BANK":               "^NSEBANK",
    "NIFTY PHARMA":             "^CNXPHARMA",
    "NIFTY AUTO":               "^CNXAUTO",
    "NIFTY FMCG":               "^CNXFMCG",
    "NIFTY METAL":              "^CNXMETAL",
    "NIFTY REALTY":             "^CNXREALTY",
    "NIFTY ENERGY":             "^CNXENERGY",
    "NIFTY FINANCIAL SERVICES": "^CNXFIN",
    "NIFTY INFRA":              "^CNXINFRA",
}


def _fetch_sector_monthly_returns_yf(lookback_years: int = 7) -> pd.DataFrame:
    """Fetch monthly returns for sector indices via yfinance (fallback path)."""
    import yfinance as yf

    records = []
    for index_name, sector in _SECTOR_INDEX_MAP.items():
        ticker = _SECTOR_YF_MAP.get(index_name)
        if not ticker:
            continue
        try:
            df = yf.download(ticker, period=f"{lookback_years}y", interval="1mo",
                             progress=False, auto_adjust=True)
            if df.empty:
                continue
            closes = df["Close"].squeeze().dropna()
            monthly_ret = closes.pct_change().dropna() * 100
            for period, ret in monthly_ret.items():
                records.append({
                    "sector":    sector,
                    "month_num": period.month,
                    "return_pct": float(ret),
                })
        except Exception:
            continue

    if not records:
        return pd.DataFrame(columns=["sector", "month_num", "return_pct"])
    return pd.DataFrame(records)


def get_sector_heat_calendar(month: int | None = None) -> dict:
    """
    B3 Sectoral Heat Calendar — monthly seasonal return heatmap for NSE sectors.

    Builds a 12-month × 10-sector matrix of average historical monthly returns
    and classifies each sector-month as TAILWIND (>+2%), HEADWIND (<-1%), or NEUTRAL.

    Args:
        month: Target month number 1-12 (default: current month).

    Returns:
        {
          "current_month": {"IT": "TAILWIND", "Banking": "HEADWIND", ...},
          "heatmap": {sector: {month_name: avg_pct, ...}, ...},
          "current_month_name": "May",
          "tailwinds": [...],
          "headwinds": [...],
          "neutral": [...],
          "note": str,
        }
    """
    target_month = month or datetime.now().month
    month_name = ["Jan","Feb","Mar","Apr","May","Jun",
                  "Jul","Aug","Sep","Oct","Nov","Dec"][target_month - 1]

    # Try local index CSV first, fall back to yfinance
    try:
        matrix, heat = build_seasonal_heat_calendar(_SECTOR_INDEX_MAP)
        if heat.empty:
            raise ValueError("Local index CSV lacks sector data — using yfinance")
        use_yf = False
    except Exception:
        heat = None
        use_yf = True

    if use_yf:
        raw = _fetch_sector_monthly_returns_yf()
        if raw.empty:
            return {"error": "Unable to fetch sector index data for heat calendar"}
        heat = (
            raw.groupby(["sector", "month_num"])["return_pct"]
            .agg(avg="mean", std="std", n="count")
            .reset_index()
            .rename(columns={"avg": "avg", "std": "std", "n": "n"})
        )
        heat.columns = ["sector", "month_num", "avg", "std", "n"]

    # Current-month signals
    _TAILWIND = 2.0
    _HEADWIND = -1.0
    _MIN_OBS = 5
    signals = {}
    for _, row in heat[heat["month_num"] == target_month].iterrows():
        if row["n"] < _MIN_OBS:
            signals[row["sector"]] = "NEUTRAL"
        elif row["avg"] > _TAILWIND:
            signals[row["sector"]] = "TAILWIND"
        elif row["avg"] < _HEADWIND:
            signals[row["sector"]] = "HEADWIND"
        else:
            signals[row["sector"]] = "NEUTRAL"

    # Full heatmap
    month_names = ["Jan","Feb","Mar","Apr","May","Jun",
                   "Jul","Aug","Sep","Oct","Nov","Dec"]
    heatmap: dict[str, dict] = {}
    for _, row in heat.iterrows():
        sec = row["sector"]
        mn  = int(row["month_num"])
        if sec not in heatmap:
            heatmap[sec] = {}
        heatmap[sec][month_names[mn - 1]] = round(float(row["avg"]), 2)

    tailwinds = [s for s, sig in signals.items() if sig == "TAILWIND"]
    headwinds = [s for s, sig in signals.items() if sig == "HEADWIND"]
    neutral   = [s for s, sig in signals.items() if sig == "NEUTRAL"]

    return {
        "current_month":      month_name,
        "current_month_num":  target_month,
        "current_month_signals": signals,
        "tailwinds":          tailwinds,
        "headwinds":          headwinds,
        "neutral":            neutral,
        "heatmap":            heatmap,
        "source":             "yfinance NSE sector indices" if use_yf else "local nse_index_data.csv",
        "note": (
            f"Seasonal analysis based on 7yr history. "
            f"{len(tailwinds)} sector(s) show historical tailwind in {month_name}."
        ),
    }


# ── B5: Economic Cycle Tracker ────────────────────────────────────────────────

def get_economic_cycle_assessment() -> dict:
    """
    B5 Economic Cycle Tracker — detect current macro cycle phase and sector positioning.

    Reads macro proxy signals (USD/INR, Brent, Copper, US10Y, VIX, CPI, PMI, IIP, GST)
    from the local data store and classifies the market into one of four phases:
      • EARLY_EXPANSION   — growth improving, rates/inflation contained
      • LATE_EXPANSION    — growth firm but inflation/commodities/rates rising
      • SLOWDOWN          — trend weakens, volatility/inflation rise
      • RECOVERY          — risk eases, trend starting to improve

    Returns:
        {
          "cycle_phase":        str,
          "confidence":         float (0-1),
          "definition":         str,
          "preferred_sectors":  list[str],
          "avoid_sectors":      list[str],
          "alignment":          {indicator: score, ...},
          "macro_snapshot":     {indicator: {signal, value, direction}, ...},
          "note":               str,
        }
    """
    macro_csv = ROOT / "data" / "macro_proxy_signals.csv"
    if not macro_csv.exists():
        return {"error": "macro_proxy_signals.csv not found — run fetch_macro_proxies.py first"}

    try:
        df = pd.read_csv(str(macro_csv))
    except Exception as e:
        return {"error": f"Failed to read macro signals: {e}"}

    try:
        result = detect_economic_cycle_phase(df)
    except Exception as e:
        return {"error": f"Cycle detection failed: {e}"}

    # Build macro snapshot for display
    macro_snapshot = {}
    for _, row in df.iterrows():
        ind = str(row.get("indicator", "")).strip()
        if not ind:
            continue
        macro_snapshot[ind] = {
            "signal":    str(row.get("signal",    "")),
            "value":     str(row.get("value",     "")),
            "direction": str(row.get("direction", "")),
        }

    return {
        "cycle_phase":       result.get("cycle_phase"),
        "confidence":        result.get("confidence"),
        "definition":        result.get("definition", ""),
        "preferred_sectors": result.get("preferred_sectors", []),
        "avoid_sectors":     result.get("avoid_sectors", []),
        "alignment":         result.get("alignment", {}),
        "macro_snapshot":    macro_snapshot,
        "updated":           str(pd.Timestamp.now().date()),
        "note": (
            f"Cycle phase: {result.get('cycle_phase')} "
            f"(confidence {result.get('confidence', 0):.0%}). "
            f"Prefer: {', '.join(result.get('preferred_sectors', [])[:3])}."
        ),
    }


# ── D4: Concall NLP Sentiment Engine ─────────────────────────────────────────

def analyze_concall_sentiment(symbol: str) -> dict:
    """
    D4 Concall NLP — extract management tone, key themes, and sentiment from
    the most recent earnings call / investor day transcript for a stock.

    Fetches transcript content via the deep search engine, then uses the
    OpenAI LLM to extract:
      • Overall sentiment (Bullish / Cautious / Bearish / Neutral)
      • Tone score (-1.0 to +1.0)
      • Top 3-5 key themes from management (growth drivers, concerns, guidance)
      • Risk flags (revenue miss, margin pressure, write-offs, promoter concerns)
      • Key quotes (direct management statements worth tracking)

    Args:
        symbol: NSE ticker symbol (e.g. 'TCS', 'RELIANCE').

    Returns:
        {
          "symbol":     str,
          "sentiment":  "Bullish" | "Cautious" | "Bearish" | "Neutral",
          "tone_score": float,
          "themes":     list[str],
          "risk_flags": list[str],
          "key_quotes": list[str],
          "guidance":   str,
          "transcript_source": str,
          "note":       str,
        }
    """
    import openai, os, json as _json

    sym = symbol.upper().strip()

    # Step 1: Fetch transcript content
    concall_data = search_concall_transcripts(sym)
    screener_data = {}
    try:
        from terminal.web_research import scrape_screener_in
        screener_data = scrape_screener_in(sym)
    except Exception:
        pass

    # Gather concall text
    transcript_text = ""
    transcript_source = "N/A"
    for item in concall_data.get("results", []):
        snip = item.get("snippet", "") or item.get("body", "") or ""
        transcript_text += "\n" + snip
        if not transcript_source or transcript_source == "N/A":
            transcript_source = item.get("url", "N/A")

    # Also pull from screener concalls list if available
    concalls = screener_data.get("concalls", [])
    if concalls:
        for c in concalls[:3]:
            transcript_text += f"\n[Transcript: {c.get('date','')} {c.get('title','')}]"
            if transcript_source == "N/A" and c.get("ppt_url"):
                transcript_source = c["ppt_url"]

    if not transcript_text.strip():
        return {
            "symbol": sym,
            "error": "No concall transcript content found. Try /search SYMBOL concall for manual lookup.",
        }

    # Step 2: LLM extraction
    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return {"symbol": sym, "error": "OPENAI_API_KEY not set — cannot run NLP extraction."}

    client = openai.OpenAI(api_key=api_key) if os.environ.get("OPENAI_API_KEY") else None
    if not client:
        return {"symbol": sym, "error": "OpenAI client unavailable."}

    prompt = f"""You are a buy-side analyst specializing in earnings call analysis.

Analyze the following concall excerpts for {sym} and return a JSON object with:
- "sentiment": "Bullish" | "Cautious" | "Bearish" | "Neutral"
- "tone_score": float from -1.0 (very bearish) to +1.0 (very bullish)
- "themes": list of 3-5 key themes management discussed (growth drivers, product launches, capex, guidance)
- "risk_flags": list of specific risks mentioned (margin pressure, write-offs, slower demand, pricing pressure)
- "key_quotes": list of 2-4 direct or paraphrased management quotes worth tracking
- "guidance": one-line summary of forward guidance given

Return ONLY the JSON object, no markdown fences.

TRANSCRIPT EXCERPTS:
{transcript_text[:3000]}
"""
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=600,
        )
        raw = resp.choices[0].message.content.strip()
        parsed = _json.loads(raw)
    except Exception as e:
        return {"symbol": sym, "error": f"LLM extraction failed: {e}", "raw_snippets": transcript_text[:500]}

    return {
        "symbol":            sym,
        "sentiment":         parsed.get("sentiment", "Neutral"),
        "tone_score":        parsed.get("tone_score", 0.0),
        "themes":            parsed.get("themes", []),
        "risk_flags":        parsed.get("risk_flags", []),
        "key_quotes":        parsed.get("key_quotes", []),
        "guidance":          parsed.get("guidance", ""),
        "transcript_source": transcript_source,
        "note": f"NLP analysis of {sym} concall via LLM. Verify with original transcript.",
    }


# ── P2-2: Scenario Analysis Engine ───────────────────────────────────────────

def run_scenario_analysis(
    symbol: str,
    price_scenarios: list[float] | None = None,
    scenario_labels: list[str] | None = None,
) -> dict:
    """
    P2-2 Scenario Engine — what-if price analysis for a held stock.

    For each hypothetical price level, calculates:
      • % change from current price
      • New implied RSI (interpolated from historical distribution)
      • New RS rank vs NIFTY (estimated)
      • Stage implication (Stage 1/2/3/4 boundary crossings)
      • Support/resistance proximity
      • Risk/reward vs current technical levels

    Args:
        symbol:          NSE ticker (e.g. 'TCS').
        price_scenarios: List of price levels to evaluate.
                         Defaults to ±5%, ±10%, ±20% from current price.
        scenario_labels: Optional labels for each scenario (e.g. ['Base', 'Bull', 'Bear']).

    Returns:
        {
          "symbol":          str,
          "current_price":   float,
          "scenarios":       [{label, price, pct_chg, stage_implication, rsi_est, note}, ...],
          "key_levels":      {support, resistance, ma50, ma200},
          "current_rsi":     float,
          "current_stage":   str,
        }
    """
    sym = symbol.upper().strip()

    # Get current snapshot
    snap = get_symbol_snapshot(sym)
    if snap.get("error"):
        return {"error": snap["error"], "symbol": sym}

    current_price = snap.get("last_price") or snap.get("price") or snap.get("close")
    if not current_price:
        return {"error": "No current price available", "symbol": sym}

    current_price = float(current_price)
    current_rsi   = float(snap.get("rsi") or 50.0)
    current_stage = str(snap.get("stage") or "Unknown")
    ma50  = float(snap.get("ma50")  or current_price)
    ma200 = float(snap.get("ma200") or current_price)

    # Load price history for support/resistance
    hist = _load_price_history(sym, days=200)
    support    = float(hist["LOW"].quantile(0.15))  if not hist.empty else current_price * 0.90
    resistance = float(hist["HIGH"].quantile(0.85)) if not hist.empty else current_price * 1.10

    # Build price scenarios
    if not price_scenarios:
        price_scenarios = [
            round(current_price * m, 2)
            for m in [0.80, 0.90, 0.95, 1.00, 1.05, 1.10, 1.20]
        ]
        scenario_labels = ["Bear -20%", "Bear -10%", "Dip -5%", "Current",
                           "Bull +5%", "Bull +10%", "Bull +20%"]

    if not scenario_labels:
        scenario_labels = [f"S{i+1}" for i in range(len(price_scenarios))]

    scenarios = []
    for label, price in zip(scenario_labels, price_scenarios):
        price = float(price)
        pct   = (price - current_price) / current_price * 100

        # Estimate RSI at scenario price (linear approximation from current distribution)
        rsi_delta = pct * 0.8  # rough: ±10% price → ±8 RSI points
        rsi_est = min(100, max(0, current_rsi + rsi_delta))

        # Stage implication
        if price > max(ma50, ma200) * 1.02:
            stage_impl = "Stage 2 (uptrend) — above both MAs"
        elif price > ma200 and price < ma50:
            stage_impl = "Stage 1/2 transition — above 200MA, below 50MA"
        elif price < ma200 and price > ma200 * 0.95:
            stage_impl = "Stage 3 warning — near/at 200MA"
        elif price < ma200 * 0.95:
            stage_impl = "Stage 4 (downtrend) — below 200MA"
        else:
            stage_impl = "Stage transition zone"

        # Key observations
        notes = []
        if abs(price - support) / current_price < 0.03:
            notes.append(f"Near support ₹{support:.0f}")
        if abs(price - resistance) / current_price < 0.03:
            notes.append(f"Near resistance ₹{resistance:.0f}")
        if abs(price - ma50) / current_price < 0.02:
            notes.append(f"Near 50-DMA ₹{ma50:.0f}")
        if abs(price - ma200) / current_price < 0.02:
            notes.append(f"At 200-DMA ₹{ma200:.0f} — critical level")

        scenarios.append({
            "label":            label,
            "price":            round(price, 2),
            "pct_change":       round(pct, 1),
            "rsi_estimate":     round(rsi_est, 1),
            "stage_implication": stage_impl,
            "notes":            "; ".join(notes) if notes else "No key level proximity",
        })

    return {
        "symbol":        sym,
        "current_price": current_price,
        "current_rsi":   current_rsi,
        "current_stage": current_stage,
        "key_levels": {
            "support":    round(support, 2),
            "resistance": round(resistance, 2),
            "ma50":       round(ma50, 2),
            "ma200":      round(ma200, 2),
        },
        "scenarios": scenarios,
        "note": f"What-if scenario analysis for {sym}. RSI estimates are approximate linear projections.",
    }


# ── P2-4: Portfolio Narrative Generator ──────────────────────────────────────

def generate_portfolio_narratives(
    symbols: list[str] | None = None,
    top_n: int = 5,
) -> dict:
    """
    P2-4 Portfolio Narrative Engine — per-stock LLM commentary combining technical,
    fundamental, and market context into a concise investment narrative.

    For each stock in the portfolio (or provided list), synthesises:
      • Current stage + RSI + key signals
      • Fundamental snapshot (P/E, ROE, ROCE from screener.in)
      • Recent news catalyst
      • 2-3 sentence investment thesis (bull) and 1-2 sentence bear case

    Args:
        symbols: Explicit list of symbols. If None, uses top portfolio holdings by score.
        top_n:   Number of stocks to narrate (default 5).

    Returns:
        {
          "narratives": [{symbol, thesis, bear_case, signals, action_hint}, ...],
          "generated_at": str,
        }
    """
    # Get symbols from portfolio if not provided
    if not symbols:
        port = get_portfolio_exposure()
        if port.get("error"):
            return {"error": "No symbols provided and portfolio is empty."}
        holdings = port.get("holdings", [])
        symbols = [h["symbol"] for h in holdings[:top_n] if h.get("symbol")]

    if not symbols:
        return {"error": "No symbols to narrate"}

    narratives = []
    for sym in symbols[:top_n]:
        sym = sym.upper().strip()
        snap = get_symbol_snapshot(sym)
        if snap.get("error"):
            narratives.append({"symbol": sym, "error": snap["error"]})
            continue

        stage   = snap.get("stage", "Unknown")
        rsi     = snap.get("rsi")
        rs_pct  = snap.get("rs_pct")
        signal  = snap.get("trading_signal", "")
        score   = snap.get("investment_score")
        price   = snap.get("last_price") or snap.get("price") or snap.get("close")
        ma50    = snap.get("ma50")
        ma200   = snap.get("ma200")

        # Compute MA50/MA200 from price history if not in snapshot
        if not ma50 or not ma200:
            try:
                _hist = _load_price_history(sym, days=220)
                if not _hist.empty:
                    _c = _hist["CLOSE"].dropna()
                    if not ma50 and len(_c) >= 50:
                        ma50 = round(float(_c.iloc[-50:].mean()), 2)
                    if not ma200 and len(_c) >= 200:
                        ma200 = round(float(_c.iloc[-200:].mean()), 2)
            except Exception:
                pass
        ma50_str  = f"₹{ma50:,.0f}" if ma50 else "50-DMA"
        ma200_str = f"₹{ma200:,.0f}" if ma200 else "200-DMA"

        # Build brief context for LLM (no API call to screener.in to keep this fast)
        context_lines = [
            f"Stock: {sym}",
            f"Stage: {stage}  |  RSI: {rsi}  |  RS%: {rs_pct}",
            f"Signal: {signal}  |  Investment Score: {score}",
            f"Price: {price}  |  50-DMA: {ma50}  |  200-DMA: {ma200}",
        ]

        # Signals
        signals_list = []
        if rsi and float(str(rsi).replace(",", "") or 0) > 70:
            signals_list.append("RSI overbought")
        elif rsi and float(str(rsi).replace(",", "") or 0) < 35:
            signals_list.append("RSI oversold")
        if "Stage 2" in str(stage):
            signals_list.append("Stage 2 uptrend")
        elif "Stage 4" in str(stage):
            signals_list.append("Stage 4 downtrend — caution")
        if rs_pct and float(str(rs_pct).replace(",", "") or 0) > 0:
            signals_list.append(f"Outperforming market (+{rs_pct}% RS)")

        # Craft narrative using rules-based logic (no API call needed for basic output)
        stage_upper = str(stage).upper()
        if ("STAGE_2" in stage_upper or "STAGE 2" in stage_upper) and signals_list:
            thesis = (
                f"{sym} is in a confirmed Stage 2 uptrend with RSI at {rsi}, "
                f"outperforming the broader market by {rs_pct}%. "
                f"Current signal: {signal}. Trend intact while above {ma50_str}."
            )
            bear_case = f"Break below {ma50_str} or Stage 2→3 transition would invalidate the setup."
            action = "Hold / Add on dips above 50-DMA"
        elif "STAGE_4" in stage_upper or "STAGE 4" in stage_upper:
            thesis = (
                f"{sym} is in Stage 4 downtrend. RSI: {rsi}. "
                f"Price below both key MAs. Avoid new positions."
            )
            bear_case = f"Further downside likely unless reclaims {ma200_str}."
            action = "Avoid / Exit on bounces"
        elif "STAGE_1" in stage_upper or "STAGE 1" in stage_upper:
            thesis = (
                f"{sym} is basing (Stage 1). RSI: {rsi}. "
                f"Watching for Stage 2 breakout above {ma50_str} with volume."
            )
            bear_case = "No catalyst yet. Monitor for breakout confirmation."
            action = "Watch / Small starter if breadth improves"
        elif "STAGE_3" in stage_upper or "STAGE 3" in stage_upper:
            thesis = (
                f"{sym} is in Stage 3 topping phase. RSI: {rsi}. "
                f"Distribution or early breakdown — caution warranted."
            )
            bear_case = f"Potential Stage 3→4 transition. Reduce or hedge below {ma50_str}."
            action = "Reduce / Tighten stops"
        else:
            thesis = f"{sym} — Stage: {stage}, RSI: {rsi}, Signal: {signal}. Monitor closely."
            bear_case = "Unclear trend — wait for direction."
            action = "Neutral / Wait for clarity"

        narratives.append({
            "symbol":      sym,
            "stage":       stage,
            "rsi":         rsi,
            "rs_pct":      rs_pct,
            "price":       price,
            "signals":     signals_list,
            "thesis":      thesis,
            "bear_case":   bear_case,
            "action_hint": action,
        })

    return {
        "narratives":    narratives,
        "total_stocks":  len(narratives),
        "generated_at":  str(pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")),
        "note": f"Portfolio narratives for {len(narratives)} stock(s) based on EOD snapshot + stage analysis.",
    }


# ── P3-2: Voice Briefing Generator ───────────────────────────────────────────

def generate_voice_briefing(
    text: str | None = None,
    voice: str = "alloy",
    save_path: str | None = None,
) -> dict:
    """
    P3-2 Daily Voice Briefing — convert market summary to audio using OpenAI TTS.

    If no text is provided, auto-generates a 60-second market briefing using
    the current day's live market overview, top movers, and portfolio status.

    Args:
        text:      Custom text to convert to speech. If None, generates auto-briefing.
        voice:     OpenAI TTS voice — 'alloy', 'echo', 'fable', 'onyx', 'nova', 'shimmer'.
        save_path: Where to save the MP3 file. Defaults to data/voice_briefing.mp3.

    Returns:
        {
          "audio_file": str path,
          "text_used":  str,
          "duration_est": str,
          "voice":      str,
          "note":       str,
        }
    """
    import openai, os
    from pathlib import Path as _Path

    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        return {"error": "OPENAI_API_KEY not set — cannot generate voice briefing."}

    # Auto-generate briefing text if not provided
    if not text:
        try:
            overview = get_live_market_overview()
            mkt_mood = overview.get("market_mood", "mixed")
            nifty_chg = overview.get("nifty_change_pct", 0)
            top_gain = overview.get("top_gainers", [{}])[:2]
            top_loss = overview.get("top_losers",  [{}])[:2]
            gainers_str = ", ".join(g.get("symbol","") for g in top_gain if g.get("symbol"))
            losers_str  = ", ".join(g.get("symbol","") for g in top_loss if g.get("symbol"))
        except Exception:
            overview = {}
            mkt_mood = "mixed"
            nifty_chg = 0
            gainers_str = ""
            losers_str  = ""

        sign = "up" if float(nifty_chg or 0) >= 0 else "down"
        text = (
            f"Good morning. Here is your Agent Adda market briefing. "
            f"NIFTY 50 is {sign} {abs(float(nifty_chg or 0)):.2f} percent. "
            f"Market mood is {mkt_mood}. "
            + (f"Top gainers today include {gainers_str}. " if gainers_str else "")
            + (f"Key stocks under pressure: {losers_str}. " if losers_str else "")
            + "Check Agent Adda for full analysis. Have a great trading day."
        )

    out_path = _Path(save_path) if save_path else ROOT / "data" / "voice_briefing.mp3"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        client = openai.OpenAI(api_key=api_key)
        response = client.audio.speech.create(
            model="tts-1",
            voice=voice,
            input=text,
        )
        response.stream_to_file(str(out_path))
    except Exception as e:
        return {"error": f"TTS generation failed: {e}", "text_used": text}

    word_count = len(text.split())
    duration_secs = word_count / 2.5  # approx 150 wpm
    duration_str = f"~{duration_secs:.0f}s"

    return {
        "audio_file":    str(out_path),
        "text_used":     text,
        "duration_est":  duration_str,
        "voice":         voice,
        "note": f"Voice briefing saved to {out_path.name}. Play with: open '{out_path}'",
    }


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
        (
            "Fetch live NSE price for a single stock — returns last price, VWAP, day OHLC, "
            "% change, volume, traded value, 52w high/low with dates, circuit limits (upper/lower), "
            "sector P/E, stock P/E, and exact NSE last-update timestamp. "
            "First-class NSE real-time data — no lag. "
            "Use for: 'current price of X', 'live quote', 'what is X trading at', 'show me X price'."
        ),
        {"type": "object", "properties": {"symbol": {"type": "string"}}, "required": ["symbol"]},
    ),
    "get_nse_quotes": (
        get_nse_quotes,
        (
            "Fetch live NSE prices for MULTIPLE stocks in parallel — returns last price, VWAP, "
            "% change, volume, circuit limits, and sector P/E for all symbols at once. "
            "Much faster than calling get_live_quote() individually. "
            "Use for: 'prices of RELIANCE, TCS, INFY', 'check my watchlist prices', "
            "'how are these stocks doing: X Y Z', 'batch price check'."
        ),
        {
            "type": "object",
            "properties": {
                "symbols": {"type": "array", "items": {"type": "string"},
                            "description": "List of NSE tickers, up to 20"},
            },
            "required": ["symbols"],
        },
    ),
    "nse_search": (
        nse_search,
        (
            "Search NSE by company name or keyword to find the NSE symbol + live price. "
            "Use when user asks for 'Larsen and Toubro price', 'find Adani companies', "
            "'what is the NSE symbol for X', 'search for [company name]'. "
            "Returns symbol, company name, current price, % change, and sector."
        ),
        {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Company name or keyword, e.g. 'Tata Steel'"},
                "top_n": {"type": "integer", "default": 5},
            },
            "required": ["query"],
        },
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
        "Resolve a company name, alias, or near-match to its canonical NSE ticker symbol. Call this before stock-specific tools.",
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
        (
            "Run an EOD screener from DB snapshot data. "
            "Original: stage2, breakouts, supertrend_buy, strong_buy, new_entrants. "
            "New: momentum_52w (near-52W-high leaders), high_rs (top RS ≥ 1.15), "
            "turnaround (recovery setups), stage1_base (basing/coiling), "
            "tight_range (VCP-like consolidation), oversold_bounce (RSI < 40 in Stage 2 dip)."
        ),
        {
            "type": "object",
            "properties": {
                "screen_type": {
                    "type": "string",
                    "enum": [
                        "stage2", "breakouts", "supertrend_buy", "strong_buy", "new_entrants",
                        "momentum_52w", "high_rs", "turnaround", "stage1_base",
                        "tight_range", "oversold_bounce",
                    ],
                },
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
            "Run an intraday screener (SQLite-backed or live yfinance fallback). "
            "Original types: momentum, breakouts, vcp, supertrend, levels, all. "
            "New types: opening_range_breakout (ORB — first 15-30min range break + volume), "
            "gap_and_go (gap continuation with MACD + volume), "
            "macd_crossover (fresh MACD signal line cross only), "
            "rsi_divergence (RSI extreme + Bollinger mean-reversion), "
            "bb_squeeze (Bollinger Band squeeze breakout), "
            "vwap_reclaim (short-EMA VWAP proxy reclaim or loss). "
            "Returns setup labels, support/resistance, target zones, confidence."
        ),
        {
            "type": "object",
            "properties": {
                "screen_type": {
                    "type": "string",
                    "enum": [
                        "momentum", "breakouts", "vcp", "supertrend", "levels", "all",
                        "opening_range_breakout", "gap_and_go", "macd_crossover",
                        "rsi_divergence", "bb_squeeze", "vwap_reclaim",
                    ],
                    "default": "momentum",
                },
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
        "Search for recent news and catalysts for a stock symbol via web search. "
        "Fetches actual article content from top 3 results — read the 'article_text' "
        "field to provide detailed summary and opinion.",
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

    # ── Deep Search Engine ─────────────────────────────────────────────────────

    "search_nse_announcements": (
        search_nse_announcements,
        (
            "Fetch live NSE corporate announcements for a stock (board meetings, results filings, "
            "regulatory disclosures, pledging changes). Source: nseindia.com live API. "
            "Use when user asks about 'NSE announcements', 'latest filings', 'company disclosures'."
        ),
        {
            "type": "object",
            "properties": {
                "symbol":      {"type": "string"},
                "max_results": {"type": "integer", "default": 15},
            },
            "required": ["symbol"],
        },
    ),

    "search_corporate_actions": (
        search_corporate_actions,
        (
            "Fetch upcoming and recent corporate actions from NSE: dividends, stock splits, "
            "bonus issues, rights issues, AGMs. Source: nseindia.com corporate actions API. "
            "Use when user asks about 'dividend', 'bonus', 'split', 'rights issue', 'ex-date'."
        ),
        {
            "type": "object",
            "properties": {
                "symbol":      {"type": "string"},
                "max_results": {"type": "integer", "default": 12},
            },
            "required": ["symbol"],
        },
    ),

    "search_insider_trades": (
        search_insider_trades,
        (
            "Fetch promoter / director / insider trading disclosures from NSE's SAST/PIT database. "
            "Shows who is buying or selling, quantities, values, and provides SEBI XBRL links. "
            "Use when user asks about 'insider trading', 'promoter buying/selling', 'insider activity'."
        ),
        {
            "type": "object",
            "properties": {
                "symbol":      {"type": "string"},
                "max_results": {"type": "integer", "default": 15},
            },
            "required": ["symbol"],
        },
    ),

    "search_bse_filings": (
        search_bse_filings,
        (
            "Search BSE India corporate filings: board meeting results, annual reports, "
            "concall notices, investor presentations. Uses DuckDuckGo site:bseindia.com. "
            "Use when user asks about 'BSE filings', 'annual report', 'board meeting results'."
        ),
        {
            "type": "object",
            "properties": {
                "symbol":      {"type": "string"},
                "max_results": {"type": "integer", "default": 10},
            },
            "required": ["symbol"],
        },
    ),

    "search_shareholding_analysis": (
        search_shareholding_analysis,
        (
            "Scrape quarterly shareholding pattern from screener.in: promoter %, FII %, DII %, "
            "public %, pledge alerts, and QoQ change trends. "
            "Use when user asks about 'shareholding', 'promoter holding', 'FII holding', "
            "'pledge', 'DII activity'."
        ),
        {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
            },
            "required": ["symbol"],
        },
    ),

    "search_analyst_coverage": (
        search_analyst_coverage,
        (
            "Aggregate analyst price targets, buy/sell/hold ratings, and brokerage recommendations "
            "from Moneycontrol, Economic Times, screener.in and general web. "
            "Use when user asks about 'analyst target', 'buy/sell/hold rating', 'brokerage view', "
            "'consensus target price'."
        ),
        {
            "type": "object",
            "properties": {
                "symbol":      {"type": "string"},
                "max_results": {"type": "integer", "default": 8},
            },
            "required": ["symbol"],
        },
    ),

    "search_concall_transcripts": (
        search_concall_transcripts,
        (
            "Search for earnings call transcripts, investor day presentations, and management "
            "commentary from screener.in, trendlyne, BSE, Moneycontrol, ET. "
            "Use when user asks about 'concall', 'earnings call', 'management commentary', "
            "'Q4 concall', 'investor day transcript'."
        ),
        {
            "type": "object",
            "properties": {
                "symbol":      {"type": "string"},
                "max_results": {"type": "integer", "default": 8},
            },
            "required": ["symbol"],
        },
    ),

    "search_sector_news": (
        search_sector_news,
        (
            "Aggregate sector-level news from 6 portals in parallel: Economic Times, "
            "Business Standard, Mint, Moneycontrol, Financial Express, Hindu BusinessLine. "
            "Use when user asks about 'sector news', 'industry news', 'latest news', "
            "or for macro sector context around a stock."
        ),
        {
            "type": "object",
            "properties": {
                "symbol":      {"type": "string"},
                "sector":      {"type": "string", "description": "Optional sector override"},
                "max_results": {"type": "integer", "default": 5},
            },
            "required": ["symbol"],
        },
    ),

    "search_social_buzz": (
        search_social_buzz,
        (
            "Gauge retail investor sentiment from Indian investing communities: "
            "Reddit r/IndiaInvestments, r/IndianStockMarket, Valuepickr, Traderji, Tijori. "
            "Returns community discussions plus a rough bullish/bearish sentiment signal. "
            "Use when user asks about 'social sentiment', 'retail view', 'community buzz', "
            "'what are investors saying about X'."
        ),
        {
            "type": "object",
            "properties": {
                "symbol":      {"type": "string"},
                "max_results": {"type": "integer", "default": 5},
            },
            "required": ["symbol"],
        },
    ),

    "deep_search": (
        deep_search,
        (
            "Run a full deep-dive search on any NSE stock using up to 9 distinct parallel "
            "search verticals: NSE announcements, corporate actions, insider trades, BSE filings, "
            "shareholding analysis, analyst coverage, concall transcripts, sector news, social buzz. "
            "Intelligently selects verticals based on context (e.g. 'results' → concalls+announcements, "
            "'dividend' → corporate_actions, 'insider' → insider_trades+shareholding). "
            "Use for 'deep search', 'deep dive', 'full search', or when multiple search verticals needed."
        ),
        {
            "type": "object",
            "properties": {
                "symbol":    {"type": "string"},
                "verticals": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": [
                            "announcements", "corporate_actions", "insider_trades",
                            "bse_filings", "shareholding", "analyst_coverage",
                            "concalls", "sector_news", "social_buzz",
                        ],
                    },
                    "description": "Specific verticals to run. Leave empty to auto-select from context.",
                },
                "context": {
                    "type": "string",
                    "description": "Optional context hint to bias vertical selection (e.g. 'dividend ex-date', 'concall highlights', 'insider buying').",
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


# ─────────────────────────────────────────────────────────────────────────────
# F&O / Options Tool Wrappers
# ─────────────────────────────────────────────────────────────────────────────

def get_options_chain(symbol: str = "NIFTY", expiry_index: int = 0) -> dict:
    """Fetch NSE options chain for a symbol with PCR, max pain, and IV data."""
    symbol = symbol.upper()

    try:
        data = None
        try:
            from nsepython import nse_optionchain_scrapper
            data = nse_optionchain_scrapper(symbol)
        except Exception:
            data = None

        if data is None:
            import requests
            session = requests.Session()
            session.headers.update({
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Accept-Encoding": "gzip, deflate, br",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://www.nseindia.com/option-chain",
            })
            session.get("https://www.nseindia.com", timeout=10)
            import time as _t; _t.sleep(1)
            if symbol in ("NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY"):
                url = f"https://www.nseindia.com/api/option-chain-indices?symbol={symbol}"
            else:
                url = f"https://www.nseindia.com/api/option-chain-equities?symbol={symbol}"
            resp = session.get(url, timeout=15)
            data = resp.json()

        if not data or "records" not in data:
            return {"error": f"No options data for {symbol}"}

        records = data["records"]
        expiry_dates = records.get("expiryDates", [])
        if not expiry_dates:
            return {"error": "No expiry dates found"}

        expiry = expiry_dates[min(expiry_index, len(expiry_dates) - 1)]
        underlying = records.get("underlyingValue", 0)

        calls: list[dict] = []
        puts: list[dict] = []
        for row in records.get("data", []):
            if row.get("expiryDate") != expiry:
                continue
            strike = row.get("strikePrice", 0)
            ce = row.get("CE", {})
            pe = row.get("PE", {})
            if ce:
                calls.append({
                    "strike": strike,
                    "oi": ce.get("openInterest", 0),
                    "chg_oi": ce.get("changeinOpenInterest", 0),
                    "volume": ce.get("totalTradedVolume", 0),
                    "iv": ce.get("impliedVolatility", 0),
                    "ltp": ce.get("lastPrice", 0),
                    "bid": ce.get("bidprice", 0),
                    "ask": ce.get("askPrice", 0),
                })
            if pe:
                puts.append({
                    "strike": strike,
                    "oi": pe.get("openInterest", 0),
                    "chg_oi": pe.get("changeinOpenInterest", 0),
                    "volume": pe.get("totalTradedVolume", 0),
                    "iv": pe.get("impliedVolatility", 0),
                    "ltp": pe.get("lastPrice", 0),
                    "bid": pe.get("bidprice", 0),
                    "ask": pe.get("askPrice", 0),
                })

        calls.sort(key=lambda x: x["strike"])
        puts.sort(key=lambda x: x["strike"])

        total_call_oi = sum(c["oi"] for c in calls)
        total_put_oi = sum(p["oi"] for p in puts)
        pcr = round(total_put_oi / total_call_oi, 3) if total_call_oi else 0

        strikes = sorted(set(c["strike"] for c in calls) | set(p["strike"] for p in puts))
        call_map = {c["strike"]: c["oi"] for c in calls}
        put_map = {p["strike"]: p["oi"] for p in puts}
        max_pain_strike = 0
        min_pain = float("inf")
        for s in strikes:
            loss = sum(call_map.get(k, 0) * max(0, k - s) for k in strikes)
            loss += sum(put_map.get(k, 0) * max(0, s - k) for k in strikes)
            if loss < min_pain:
                min_pain = loss
                max_pain_strike = s

        atm = min(strikes, key=lambda s: abs(s - underlying)) if strikes else 0

        return {
            "symbol": symbol,
            "expiry": expiry,
            "expiry_dates": expiry_dates[:4],
            "underlying": underlying,
            "atm": atm,
            "pcr": pcr,
            "max_pain": max_pain_strike,
            "calls": calls,
            "puts": puts,
            "total_call_oi": total_call_oi,
            "total_put_oi": total_put_oi,
        }
    except Exception as e:
        return {"error": str(e)}


def get_option_chain(symbol: str, expiry: str | None = None,
                     use_live: bool = True) -> dict:
    """
    Fetch live option chain for an index or stock.
    Returns OI, IV, PCR, max pain, ATM greeks, OI buildup and support/resistance levels.
    Falls back to EOD data outside market hours.
    """
    return analyze_option_chain(symbol, expiry, use_live=use_live)


def get_oi_analysis(symbol: str, expiry: str | None = None) -> dict:
    """
    Focused open-interest analysis: PCR, max pain, CE/PE OI concentration,
    OI buildup and unwinding at key strikes.  Good for support/resistance.
    """
    result = analyze_option_chain(symbol, expiry, use_live=True)
    if "error" in result:
        return result
    return {
        "symbol":            result["symbol"],
        "underlying":        result["underlying"],
        "expiry":            result["expiry"],
        "dte":               result["dte"],
        "source":            result.get("source"),
        "pcr":               result["pcr"],
        "max_pain":          result["max_pain"],
        "max_pain_vs_spot":  result.get("max_pain_vs_spot"),
        "top_ce_oi_strikes": result["top_ce_oi_strikes"],   # resistance
        "top_pe_oi_strikes": result["top_pe_oi_strikes"],   # support
        "oi_buildup":        result["oi_buildup"],
        "total_ce_oi":       result.get("total_ce_oi"),
        "total_pe_oi":       result.get("total_pe_oi"),
    }


def get_futures_analysis(symbol: str) -> dict:
    """
    Futures basis, cost-of-carry, and rollover analysis for an index or stock.
    """
    return analyze_futures(symbol, use_live=True)


def get_options_strategy(symbol: str, strategy: str,
                          expiry: str | None = None) -> dict:
    """
    Build a specific options strategy with live pricing.
    Returns legs, entry costs, max risk/reward, breakevens, and payoff curve.

    Available strategies: long_call, long_put, bull_call_spread, bear_put_spread,
    long_straddle, long_strangle, iron_condor, covered_call, protective_put,
    calendar_spread.
    """
    return build_strategy(symbol, strategy, expiry, use_live=True)


def get_strategy_recommendations(symbol: str, expiry: str | None = None) -> dict:
    """
    Analyse current option chain context (PCR, IV, DTE, max pain) and
    recommend the top 3 options strategies with rationale.
    """
    return recommend_strategies(symbol, expiry, use_live=True)


def refresh_fno_eod_data() -> dict:
    """
    Download the latest F&O EOD bhavcopy from NSE archives and store in SQLite.
    Returns summary: trade_date, rows_stored, options count, futures count.
    """
    return _fno_load_latest()


def get_fno_data_status() -> dict:
    """
    Return the status of the local F&O EOD database:
    available dates, record counts, and last download time.
    """
    dates = _fno_available_dates()
    if not dates:
        return {
            "status": "no_data",
            "message": "F&O EOD database is empty. Run refresh_fno_eod_data() first.",
            "available_strategies": list(STRATEGY_CATALOG.keys()),
        }
    return {
        "status":             "ok",
        "latest_date":        dates[0],
        "available_dates":    dates[:10],
        "total_dates":        len(dates),
        "available_strategies": list(STRATEGY_CATALOG.keys()),
    }


def analyze_options_buying(symbol: str, direction: str = "bullish",
                            expiry: str | None = None) -> dict:
    """
    Deep options buying analysis for a symbol.
    Returns: ATM IV + regime, IV rank (estimated), expected move, strike selection guide
    (ITM/ATM/OTM with delta/theta/breakeven/probability), theta decay profile,
    OI support/resistance context, buying verdict (BUY / SPREAD / AVOID).
    direction: 'bullish' | 'bearish' | 'volatile'
    """
    return analyze_buying_opportunity(symbol, direction, expiry, use_live=True)


def scan_options_buys(direction: str = "bullish",
                       max_iv: float = 25.0,
                       min_oi: int = 500_000,
                       top_n: int = 10) -> dict:
    """
    Scan all F&O-eligible stocks and indices for the best options buying opportunities.
    Ranks by: low ATM IV (cheap options) + adequate OI liquidity + ideal DTE.
    Returns top N symbols with ATM IV, straddle cost, expected move, and buying score.
    direction: 'bullish' | 'bearish' | 'volatile'
    max_iv: IV ceiling (default 25%) — lower = cheaper options only
    """
    return scan_options_buying_opportunities(direction, min_oi, max_iv, top_n)


# Register F&O tools
TOOL_REGISTRY.update({
    "get_option_chain": (
        get_option_chain,
        (
            "Fetch live option chain for a NIFTY/BANKNIFTY index or any NSE stock. "
            "Returns: underlying price, PCR (put-call ratio), max pain, top CE/PE OI strikes "
            "(key resistance/support), ATM±2 greeks (delta/theta/vega/gamma/IV), OI buildup "
            "and unwinding, IV skew, DTE. Falls back to EOD data outside market hours. "
            "Use for: 'option chain', 'OI analysis', 'PCR', 'max pain', 'support resistance', "
            "'greeks', 'IV', 'option data for NIFTY/BANKNIFTY/<stock>'."
        ),
        {
            "type": "object",
            "properties": {
                "symbol":   {"type": "string", "description": "NSE symbol e.g. NIFTY, BANKNIFTY, RELIANCE"},
                "expiry":   {"type": "string", "description": "Expiry date YYYY-MM-DD or NSE format e.g. 08-May-2026"},
                "use_live": {"type": "boolean", "default": True},
            },
            "required": ["symbol"],
        },
    ),
    "get_oi_analysis": (
        get_oi_analysis,
        (
            "Focused open interest analysis: PCR, max pain, top CE/PE OI concentration strikes, "
            "OI buildup and unwinding. Identifies key support (PE OI) and resistance (CE OI) levels. "
            "Use for: 'where is support/resistance', 'OI buildup', 'PCR signal', 'max pain level', "
            "'where is call writing', 'where is put writing'."
        ),
        {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "expiry": {"type": "string"},
            },
            "required": ["symbol"],
        },
    ),
    "get_futures_analysis": (
        get_futures_analysis,
        (
            "Futures chain analysis: basis (futures vs spot), cost of carry (annualised), "
            "rollover percentage, OI across expiries. Good for gauging institutional positioning. "
            "Use for: 'futures basis', 'cost of carry', 'rollover', 'futures premium/discount', "
            "'long/short build-up in futures', 'what is NIFTY futures price'."
        ),
        {
            "type": "object",
            "properties": {"symbol": {"type": "string"}},
            "required": ["symbol"],
        },
    ),
    "get_options_strategy": (
        get_options_strategy,
        (
            "Build a specific options strategy with live pricing. Returns legs, strikes, "
            "entry costs, max risk, max reward, breakeven points, and payoff curve. "
            "Strategies: long_call, long_put, bull_call_spread, bear_put_spread, "
            "long_straddle, long_strangle, iron_condor, covered_call, protective_put, calendar_spread. "
            "Use for: 'set up a bull call spread on NIFTY', 'long straddle for earnings', "
            "'buy a call option', 'iron condor setup', 'options strategy for <stock>'."
        ),
        {
            "type": "object",
            "properties": {
                "symbol":   {"type": "string"},
                "strategy": {
                    "type": "string",
                    "enum": [
                        "long_call", "long_put", "bull_call_spread", "bear_put_spread",
                        "long_straddle", "long_strangle", "iron_condor",
                        "covered_call", "protective_put", "calendar_spread",
                    ],
                },
                "expiry": {"type": "string"},
            },
            "required": ["symbol", "strategy"],
        },
    ),
    "get_strategy_recommendations": (
        get_strategy_recommendations,
        (
            "Analyse current PCR, IV, DTE, and max pain to recommend the top 3 options strategies "
            "with rationale. Tailors recommendations to current market regime (trending/volatile/range-bound). "
            "Use for: 'what options strategy should I use', 'best strategy for NIFTY now', "
            "'options setup recommendation', 'which strategy fits current conditions'."
        ),
        {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "expiry": {"type": "string"},
            },
            "required": ["symbol"],
        },
    ),
    "refresh_fno_eod_data": (
        refresh_fno_eod_data,
        (
            "Download and store the latest F&O EOD bhavcopy from NSE. "
            "Returns summary of rows stored, options count, futures count, and trade date. "
            "Use when asked to 'update F&O data', 'download bhavcopy', 'refresh options data'."
        ),
        {"type": "object", "properties": {}, "required": []},
    ),
    "get_fno_data_status": (
        get_fno_data_status,
        (
            "Check status of local F&O EOD database: available dates and available strategy list. "
            "Use at the start of any F&O session to confirm data availability."
        ),
        {"type": "object", "properties": {}, "required": []},
    ),
})


# ── Chart tool wrapper ────────────────────────────────────────────────────────

def get_chart_summary(symbol: str, timeframe: str = "3mo") -> dict:
    """
    Get chart data summary for a symbol: current price, change%, RSI, MACD,
    EMA positions, period high/low, trend context.
    Does NOT render the ASCII chart — call render_chart() for that.
    """
    return chart_summary(symbol, timeframe)


def open_html_chart(symbol: str, timeframe: str = "3mo",
                    indicators: list | None = None) -> dict:
    """
    Generate and open a full interactive Plotly HTML chart in the browser.
    Returns the file path.
    """
    inds = indicators or ["volume", "rsi", "macd"]
    try:
        fpath = render_html_chart(symbol, timeframe, inds, open_browser=True)
        return {"status": "opened", "file": fpath, "symbol": symbol, "timeframe": timeframe}
    except Exception as e:
        return {"error": str(e)}

# Register chart + options buying tools
TOOL_REGISTRY.update({
    "get_chart_summary": (
        get_chart_summary,
        (
            "Get chart data and technical summary for a stock or index. Returns current price, "
            "daily change%, RSI(14), MACD signal (bullish/bearish), EMA20/EMA50 positions, "
            "period high/low. Use for: 'chart for X', 'technical levels', 'trend analysis', "
            "'is X above its moving average', 'show me the chart', 'price action for X'."
        ),
        {
            "type": "object",
            "properties": {
                "symbol":    {"type": "string", "description": "NSE symbol e.g. RELIANCE, NIFTY"},
                "timeframe": {
                    "type": "string",
                    "enum": ["1d", "5d", "1mo", "3mo", "6mo", "1y", "2y"],
                    "description": "Chart timeframe (default 3mo)",
                },
            },
            "required": ["symbol"],
        },
    ),
    "open_html_chart": (
        open_html_chart,
        (
            "Generate and open a full interactive HTML chart (Plotly) in the browser. "
            "Shows candlestick + EMA20/50/200 + Bollinger Bands + Volume + RSI + MACD "
            "in a professional dark TradingView-style layout. Fully interactive: zoom, pan, hover. "
            "Use for: 'open chart', 'interactive chart', 'show html chart', 'open in browser', "
            "'full chart for X', 'detailed chart'."
        ),
        {
            "type": "object",
            "properties": {
                "symbol":     {"type": "string"},
                "timeframe":  {"type": "string", "enum": ["1d", "5d", "1mo", "3mo", "6mo", "1y", "2y"]},
                "indicators": {"type": "array", "items": {"type": "string"},
                               "description": "['volume','rsi','macd'] — default: all three"},
            },
            "required": ["symbol"],
        },
    ),
    "analyze_options_buying": (
        analyze_options_buying,
        (
            "Deep options buying analysis for a symbol. Returns ATM IV + regime (cheap/fair/rich), "
            "IV rank estimate, expected move (±1σ/±2σ), strike selection guide (ITM/ATM/OTM with "
            "delta/theta/breakeven/probability), theta decay profile, OI context, and buying verdict "
            "(BUY / USE SPREAD / AVOID). "
            "Use for: 'should I buy calls on X', 'best strike to buy', 'options buying setup for X', "
            "'what call should I buy', 'options trade idea for X', 'options opportunity for X'."
        ),
        {
            "type": "object",
            "properties": {
                "symbol":    {"type": "string"},
                "direction": {
                    "type": "string",
                    "enum": ["bullish", "bearish", "volatile"],
                    "description": "Trade direction (default: bullish)",
                },
                "expiry":    {"type": "string", "description": "Expiry date YYYY-MM-DD (optional)"},
            },
            "required": ["symbol"],
        },
    ),
    "scan_options_buys": (
        scan_options_buys,
        (
            "Scan all F&O-eligible stocks/indices for the best options buying opportunities. "
            "Ranks by: low ATM IV (cheap options) + OI liquidity + ideal DTE. "
            "Returns top symbols with ATM IV, straddle cost, expected move, and buying score. "
            "Use for: 'scan for options buying opportunities', 'which stocks have cheap options', "
            "'best stocks for buying calls today', 'low IV options scan', 'options buying scan'."
        ),
        {
            "type": "object",
            "properties": {
                "direction": {"type": "string", "enum": ["bullish", "bearish", "volatile"]},
                "max_iv":    {"type": "number", "description": "Max ATM IV% (default 25)"},
                "min_oi":    {"type": "integer", "description": "Min OI for liquidity (default 500000)"},
                "top_n":     {"type": "integer", "description": "Number of results to return (default 10)"},
            },
            "required": [],
        },
    ),
})


# Register forensic accounting + event calendar tools
TOOL_REGISTRY.update({
    "run_forensic_analysis": (
        run_forensic_analysis,
        (
            "Run D5 Forensic Accounting analysis on an NSE stock. "
            "Computes three quantitative red-flag models: "
            "(1) Beneish M-score — detects earnings manipulation (M > -1.78 = manipulation risk); "
            "(2) Piotroski F-score — financial health 0-9 (7-9 = strong, 0-3 = weak); "
            "(3) Altman Z'-score — bankruptcy/distress risk (Z' < 1.1 = distress zone). "
            "Data from screener.in annual balance sheet + P&L + cash flow statements. "
            "Use for: forensic analysis, earnings quality, manipulation risk, financial health, "
            "due diligence, red flags, balance sheet quality, accounting risk."
        ),
        {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "NSE ticker e.g. RELIANCE, ADANIENT"},
            },
            "required": ["symbol"],
        },
    ),
    "screen_forensic_watchlist": (
        screen_forensic_watchlist,
        (
            "Run forensic accounting screening across multiple NSE stocks in parallel. "
            "Returns all three forensic scores (Beneish, Piotroski, Altman) for each stock, "
            "ranked by risk level. Use for portfolio-level forensic due diligence, "
            "pre-buy checklist, or identifying high-risk holdings."
        ),
        {
            "type": "object",
            "properties": {
                "symbols": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of NSE tickers to screen (max 8)",
                },
            },
            "required": ["symbols"],
        },
    ),
    "search_broker_research": (
        search_broker_research,
        (
            "Search for broker house research reports, institutional analyst ratings, "
            "and consensus price targets for an NSE stock. "
            "Searches: Trendlyne (consensus estimates), Moneycontrol (broker radar), "
            "Economic Times (analyst reports), major brokers (Motilal/Kotak/ICICI/HDFC/Edelweiss/Axis). "
            "Extracts price targets from report titles where available. "
            "Use for: broker reports, analyst ratings, price targets, buy/sell recommendations, "
            "institutional views, consensus estimate."
        ),
        {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "NSE ticker e.g. TCS"},
            },
            "required": ["symbol"],
        },
    ),
    "search_mf_holdings": (
        search_mf_holdings,
        (
            "Search for mutual fund holdings and FII/DII institutional ownership data for a stock. "
            "Combines screener.in direct shareholding scrape (promoter/FII/DII quarterly trend) "
            "with web search across Trendlyne, Moneycontrol, Tijori Finance. "
            "Use for: MF holdings, institutional ownership, FII activity, DII buying/selling, "
            "promoter pledge, shareholding pattern changes."
        ),
        {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "NSE ticker e.g. HDFCBANK"},
            },
            "required": ["symbol"],
        },
    ),
    "get_upcoming_events": (
        get_upcoming_events,
        (
            "E4 Event-Driven Alert Engine: fetch upcoming corporate action events for a list of "
            "symbols or an entire index. Tracks dividends, bonus issues, stock splits, rights issues, "
            "AGMs, board meetings, and results calendar. Returns events grouped by date and type, "
            "with days-until countdown. "
            "Use for: upcoming dividends, ex-date, bonus issues, stock splits, results dates, "
            "event calendar, corporate actions calendar, board meeting dates."
        ),
        {
            "type": "object",
            "properties": {
                "symbols":    {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "NSE tickers to check (leave empty to use index symbols)",
                },
                "index":      {
                    "type": "string",
                    "description": "Index to scan when symbols is empty (default 'NIFTY 50')",
                    "default": "NIFTY 50",
                },
                "days_ahead": {
                    "type": "integer",
                    "description": "Calendar days ahead to look (default 30)",
                    "default": 30,
                },
                "event_types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Filter to specific types e.g. ['Dividend', 'Results', 'Bonus', 'Split']",
                },
            },
            "required": [],
        },
    ),
    "get_event_calendar_summary": (
        get_event_calendar_summary,
        (
            "Quick event calendar overview for an index — compact list of upcoming dividends, "
            "splits, bonuses, results announcements, and board meetings in the next N days. "
            "Lighter than get_upcoming_events. Use for: what events this week/fortnight, "
            "upcoming ex-dates, results season, event summary for NIFTY."
        ),
        {
            "type": "object",
            "properties": {
                "index":      {
                    "type": "string",
                    "description": "Index name e.g. 'NIFTY 50' (default)",
                    "default": "NIFTY 50",
                },
                "days_ahead": {
                    "type": "integer",
                    "description": "Days ahead to look (default 14)",
                    "default": 14,
                },
            },
            "required": [],
        },
    ),
})

# ── B3, B5, D4, P2-2, P2-4, P3-2: New tool registrations ────────────────────
TOOL_REGISTRY.update({
    "get_sector_heat_calendar": (
        get_sector_heat_calendar,
        (
            "B3 Sectoral Heat Calendar — 12-month seasonal return heatmap for NSE sector indices. "
            "Shows which sectors historically perform best in each month (TAILWIND/HEADWIND/NEUTRAL). "
            "Use for: sector rotation timing, seasonal investing, which sectors favour current month, "
            "historical monthly patterns, seasonal tailwinds and headwinds."
        ),
        {
            "type": "object",
            "properties": {
                "month": {
                    "type": "integer",
                    "description": "Target month 1-12 (default: current month)",
                },
            },
            "required": [],
        },
    ),
    "get_economic_cycle_assessment": (
        get_economic_cycle_assessment,
        (
            "B5 Economic Cycle Tracker — detect current macro cycle phase from proxy signals. "
            "Returns EARLY_EXPANSION / LATE_EXPANSION / SLOWDOWN / RECOVERY with confidence, "
            "preferred sectors to overweight, sectors to avoid, and full macro snapshot. "
            "Use for: macro-driven sector allocation, positioning in current cycle phase, "
            "understanding where we are in the business cycle, rate/inflation/commodity regime."
        ),
        {
            "type": "object",
            "properties": {},
            "required": [],
        },
    ),
    "analyze_concall_sentiment": (
        analyze_concall_sentiment,
        (
            "D4 Concall NLP — extract management tone, key themes, risk flags, and sentiment "
            "from the most recent earnings call or investor day transcript. "
            "Returns: sentiment (Bullish/Cautious/Bearish/Neutral), tone score (-1 to +1), "
            "top themes, risk flags, key management quotes, guidance summary. "
            "Use for: post-results management tone check, earnings quality assessment, "
            "concall digest, what management said about margins/growth/guidance."
        ),
        {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "NSE ticker symbol (e.g. 'TCS', 'RELIANCE')",
                },
            },
            "required": ["symbol"],
        },
    ),
    "run_scenario_analysis": (
        run_scenario_analysis,
        (
            "P2-2 Scenario Engine — what-if price analysis for a stock at various levels. "
            "For each hypothetical price: % change, RSI estimate, stage implication (Stage 2/3/4), "
            "proximity to key levels (support, resistance, 50-DMA, 200-DMA). "
            "Use for: what happens if stock drops 10%? which level triggers Stage 4? "
            "risk/reward analysis, stop-loss placement, bull/base/bear case planning."
        ),
        {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "NSE ticker symbol (e.g. 'TCS')",
                },
                "price_scenarios": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "List of price levels to evaluate. Default: ±5/10/20% from current.",
                },
                "scenario_labels": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Labels for each price scenario (e.g. ['Base', 'Bull', 'Bear'])",
                },
            },
            "required": ["symbol"],
        },
    ),
    "generate_portfolio_narratives": (
        generate_portfolio_narratives,
        (
            "P2-4 Portfolio Narrative Engine — per-stock investment narratives combining "
            "stage analysis, RSI, RS, signals, and fundamental snapshot. "
            "Returns bull thesis, bear case, and action hint for each stock. "
            "Use for: portfolio review, morning briefing narrative, stock-by-stock commentary, "
            "investment thesis validation, portfolio health check."
        ),
        {
            "type": "object",
            "properties": {
                "symbols": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of symbols to narrate. Default: top portfolio holdings.",
                },
                "top_n": {
                    "type": "integer",
                    "description": "Max number of stocks to narrate (default 5)",
                    "default": 5,
                },
            },
            "required": [],
        },
    ),
    "generate_voice_briefing": (
        generate_voice_briefing,
        (
            "P3-2 Voice Briefing — convert market summary to an MP3 audio briefing using OpenAI TTS. "
            "Auto-generates a 60-second daily market briefing if no text provided. "
            "Saves to data/voice_briefing.mp3. Requires OPENAI_API_KEY. "
            "Use for: hands-free morning briefing, audio market update, voice digest."
        ),
        {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Custom text to convert. If None, auto-generates from market overview.",
                },
                "voice": {
                    "type": "string",
                    "description": "TTS voice: alloy, echo, fable, onyx, nova, shimmer (default: alloy)",
                    "default": "alloy",
                },
                "save_path": {
                    "type": "string",
                    "description": "File path for MP3 output. Default: data/voice_briefing.mp3",
                },
            },
            "required": [],
        },
    ),
})


# ── Watchlist alert tools ──────────────────────────────────────────────────


def get_watchlist_alerts(_args: dict) -> dict:
    from terminal.alerts import list_alerts
    alerts = list_alerts()
    return {"alerts": alerts, "count": len(alerts)}


def add_watchlist_alert(args: dict) -> dict:
    from terminal.alerts import add_alert
    sym = args.get("symbol", "").upper()
    trigger = args.get("trigger", "price_above")
    value = float(args.get("value", 0))
    note = args.get("note", "")
    alert = add_alert(sym, trigger, value, note)
    return {"added": alert}


def delete_watchlist_alert(args: dict) -> dict:
    from terminal.alerts import delete_alert
    aid = int(args.get("alert_id", 0))
    ok = delete_alert(aid)
    return {"deleted": ok, "alert_id": aid}


def check_watchlist_alerts(_args: dict) -> dict:
    from terminal.alerts import check_alerts
    triggered = check_alerts()
    return {"triggered": triggered, "count": len(triggered)}


TOOL_REGISTRY.update({
    "get_watchlist_alerts": (
        get_watchlist_alerts,
        "List all active price/RSI alerts",
        {"type": "object", "properties": {}},
    ),
    "add_watchlist_alert": (
        add_watchlist_alert,
        "Add a price or RSI alert for a symbol",
        {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "trigger": {"type": "string", "enum": ["price_above", "price_below", "rsi_above", "rsi_below"]},
                "value": {"type": "number"},
                "note": {"type": "string"},
            },
        },
    ),
    "delete_watchlist_alert": (
        delete_watchlist_alert,
        "Delete an alert by ID",
        {"type": "object", "properties": {"alert_id": {"type": "integer"}}},
    ),
    "check_watchlist_alerts": (
        check_watchlist_alerts,
        "Check all alerts against live prices/RSI and fire macOS notifications for triggered ones",
        {"type": "object", "properties": {}},
    ),
})


TOOL_REGISTRY.update({
    "get_options_chain": (
        get_options_chain,
        (
            "Fetch live NSE options chain with full OI, IV, LTP, PCR, and max pain. "
            "Returns side-by-side calls/puts data for all strikes near ATM, total OI, "
            "PCR (put-call ratio), max pain strike, and available expiry dates. "
            "Use for: 'options chain', 'OI buildup', 'PCR', 'max pain', 'IV skew', "
            "'option chain for NIFTY/BANKNIFTY/<stock>', 'show me calls and puts'."
        ),
        {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Index (NIFTY/BANKNIFTY/FINNIFTY) or equity symbol",
                },
                "expiry_index": {
                    "type": "integer",
                    "description": "0=nearest expiry, 1=next, etc.",
                    "default": 0,
                },
            },
            "required": [],
        },
    ),
})


def get_portfolio_pnl(_args: dict = None) -> dict:
    """Compute live unrealised P&L for all holdings in data/holdings.csv."""
    try:
        from terminal.portfolio_pnl import compute_pnl
        return compute_pnl()
    except Exception as e:
        return {"error": str(e)}


TOOL_REGISTRY.update({
    "get_portfolio_pnl": (
        get_portfolio_pnl,
        (
            "Live Portfolio P&L — compute unrealised gains/losses for all holdings in data/holdings.csv. "
            "Fetches live prices for each position and returns per-stock P&L, day P&L, invested value, "
            "current value, P&L %, and portfolio totals. "
            "Use for: 'portfolio P&L', 'my holdings', 'unrealised gains', 'unrealised losses', "
            "'how is my portfolio doing', 'portfolio performance', 'check my holdings'."
        ),
        {
            "type": "object",
            "properties": {},
            "required": [],
        },
    ),
})


def export_session(args: dict) -> dict:
    """Export current session to HTML or PDF."""
    fmt = args.get("format", "html")
    symbol = args.get("symbol", "")
    return {"message": f"Use /export {fmt} {symbol} command to export the session."}


TOOL_REGISTRY.update({
    "export_session": (
        export_session,
        "Export the current research session to HTML or PDF report",
        {
            "type": "object",
            "properties": {
                "format": {"type": "string", "enum": ["html", "pdf"], "default": "html"},
                "symbol": {"type": "string"},
            },
        },
    ),
    "fetch_article_content": (
        fetch_article_content,
        (
            "Fetch and read the full text of a news article from its URL. "
            "Use this to get deeper context from articles found via search tools "
            "when you need to provide a thorough summary and opinion."
        ),
        {
            "type": "object",
            "properties": {
                "url":       {"type": "string", "description": "Full URL of the article to fetch"},
                "max_chars": {"type": "integer", "default": 3000},
            },
            "required": ["url"],
        },
    ),
})


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
