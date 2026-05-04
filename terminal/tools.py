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

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT      = Path(__file__).parent.parent
DB_PATH   = ROOT / "data" / "sector_rotation_tracker.db"
STOCK_CSV = ROOT / "data" / "nse_sec_full_data.csv"
INDEX_CSV = ROOT / "data" / "nse_index_data.csv"
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

    # Case-insensitive sector match
    rows = conn.execute(
        """SELECT symbol, company_name, stage, investment_score, relative_strength,
                  change_1d_pct, change_1w_pct, change_1m_pct, rsi, trading_signal
           FROM stage_snapshots
           WHERE UPPER(sector)=UPPER(?) AND snapshot_date=?
           ORDER BY investment_score DESC""",
        (sector, snap_date),
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

    sql = query_map.get(screen_type.lower(), query_map["stage2"])
    cols = ["symbol","company_name","stage_score","investment_score","price",
            "relative_strength","change","rsi","trading_signal","sector"]

    if "new_entrants" in screen_type:
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
        "screen_type":    screen_type,
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

        results = []
        for r in parser.results[:max_results]:
            if r.get("title") and len(r["title"]) > 5:
                results.append({
                    "title":   r.get("title", ""),
                    "url":     r.get("url", ""),
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
# Tool registry — name → (function, description, param_schema)
# ─────────────────────────────────────────────────────────────────────────────

TOOL_REGISTRY: dict[str, Any] = {
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
        "Run a screener: stage2, supertrend_buy, strong_buy, new_entrants",
        {
            "type": "object",
            "properties": {
                "screen_type": {"type": "string", "enum": ["stage2","supertrend_buy","strong_buy","new_entrants"]},
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
