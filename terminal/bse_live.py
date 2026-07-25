"""BSE public website quote helpers for live Agent Adda scans.

These helpers use BSE website endpoints, not a licensed exchange feed. Keep
callers explicit about the source so reports do not describe this as NSE data.
"""

from __future__ import annotations

import html
import json
import re
from datetime import datetime
from typing import Any

import pandas as pd

_BSE_SESSION = None
_BSE_SCRIP_CACHE: dict[str, str] = {}

_BSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.bseindia.com",
    "Referer": "https://www.bseindia.com/",
}


def get_bse_session():
    """Return a warmed requests session for BSE website APIs."""
    global _BSE_SESSION
    if _BSE_SESSION is None:
        import requests

        session = requests.Session()
        session.headers.update(_BSE_HEADERS)
        try:
            session.get("https://www.bseindia.com/", timeout=8)
        except Exception:
            pass
        _BSE_SESSION = session
    return _BSE_SESSION


def bse_get_text(url: str, *, timeout: int = 10, referer: str | None = None) -> str:
    """Fetch raw or JSON-string text from a BSE website API endpoint."""
    session = get_bse_session()
    headers = dict(_BSE_HEADERS)
    if referer:
        headers["Referer"] = referer
    resp = session.get(url, headers=headers, timeout=timeout)
    status = getattr(resp, "status_code", 0)
    body = resp.text if hasattr(resp, "text") else ""
    if status >= 400:
        raise RuntimeError(f"BSE returned HTTP {status} for {url}; body preview: {body.strip()[:160]!r}")
    if not body.strip():
        raise RuntimeError(f"BSE returned empty body for {url}")
    try:
        decoded = resp.json()
        if isinstance(decoded, str):
            return decoded
    except Exception:
        pass
    return body


def bse_get_json(url: str, *, timeout: int = 10, referer: str | None = None) -> Any:
    """Fetch JSON from a BSE website API endpoint."""
    text = bse_get_text(url, timeout=timeout, referer=referer)
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        resp_json = get_bse_session().get(url, headers=_BSE_HEADERS, timeout=timeout).json()
        return resp_json


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        cleaned = str(value).replace(",", "").replace("%", "").strip()
        if not cleaned:
            return None
        return float(cleaned)
    except (TypeError, ValueError):
        return None


def _clean_html_text(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(text or ""))).strip()


def resolve_bse_scrip_code(symbol: str) -> str | None:
    """Resolve an NSE-style symbol to a BSE scrip code using BSE smart search."""
    from urllib.parse import quote

    sym = symbol.strip().upper()
    if not sym:
        return None
    if sym.isdigit():
        return sym
    cached = _BSE_SCRIP_CACHE.get(sym)
    if cached:
        return cached

    url = f"https://api.bseindia.com/BseIndiaAPI/api/PeerSmartSearch/w?Type=EQ&text={quote(sym)}"
    text = bse_get_text(url)
    rows = []
    pattern = re.compile(
        r"liclick\('(?P<code>\d+)'\s*,\s*'(?P<name>[^']*)'\).*?<span>(?P<span>.*?)</span>",
        re.IGNORECASE | re.DOTALL,
    )
    for match in pattern.finditer(text):
        span = _clean_html_text(match.group("span")).upper()
        rows.append((match.group("code"), match.group("name"), span))

    for code, _, span in rows:
        tokens = set(re.split(r"[^A-Z0-9&.-]+", span))
        if sym in tokens:
            _BSE_SCRIP_CACHE[sym] = code
            return code
    if rows:
        _BSE_SCRIP_CACHE[sym] = rows[0][0]
        return rows[0][0]

    fallback = re.search(r"liclick\('(\d+)'\s*,", text)
    if fallback:
        code = fallback.group(1)
        _BSE_SCRIP_CACHE[sym] = code
        return code
    return None


def normalize_bse_header_payload(symbol: str, scrip_code: str, payload: dict) -> dict:
    """Normalize BSE getScripHeaderData JSON into the live quote shape."""
    sym = symbol.strip().upper()
    curr = payload.get("CurrRate", {}) if isinstance(payload, dict) else {}
    company = payload.get("Cmpname", {}) if isinstance(payload, dict) else {}
    header = payload.get("Header", {}) if isinstance(payload, dict) else {}
    last = _float_or_none(curr.get("LTP") or header.get("LTP"))
    if last is None:
        return {
            "symbol": sym,
            "source": "BSE live API",
            "exchange": "BSE",
            "bse_scrip_code": scrip_code,
            "error": "No price data returned from BSE header endpoint",
            "fallback_disabled": True,
        }
    return {
        "symbol": sym,
        "name": company.get("FullN") or company.get("SeriesN") or sym,
        "series": "EQ",
        "exchange": "BSE",
        "bse_scrip_code": scrip_code,
        "last_price": round(last, 2),
        "open": _float_or_none(header.get("Open")),
        "day_high": _float_or_none(header.get("High")),
        "day_low": _float_or_none(header.get("Low")),
        "prev_close": _float_or_none(header.get("PrevClose")),
        "change": _float_or_none(curr.get("Chg")),
        "pct_change": _float_or_none(curr.get("PcChg")),
        "as_of": header.get("Ason") or datetime.now().strftime("%d-%b-%Y %H:%M:%S"),
        "source": "BSE live API",
    }


def fetch_bse_header_payload(scrip_code: str) -> dict:
    url = (
        "https://api.bseindia.com/BseIndiaAPI/api/getScripHeaderData/w"
        f"?Debtflag=&scripcode={scrip_code}&seriesid="
    )
    payload = bse_get_json(url)
    return payload if isinstance(payload, dict) else {}


def fetch_bse_stock_reach_graph_payload(scrip_code: str) -> dict:
    url = (
        "https://api.bseindia.com/BseIndiaAPI/api/StockReachGraph/w"
        f"?scripcode={scrip_code}&flag=0&fromdate=&todate=&seriesid="
    )
    payload = bse_get_json(url)
    return payload if isinstance(payload, dict) else {}


def bse_stock_reach_graph_to_candles(payload: dict) -> pd.DataFrame:
    """Convert BSE StockReachGraph points to a standard OHLCV frame."""
    raw = payload.get("Data") if isinstance(payload, dict) else None
    if isinstance(raw, str):
        try:
            rows = json.loads(raw)
        except (TypeError, ValueError):
            rows = []
    elif isinstance(raw, list):
        rows = raw
    else:
        rows = []
    if not rows:
        return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])

    out = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        ts = pd.to_datetime(row.get("dttm"), errors="coerce")
        price = _float_or_none(row.get("vale1"))
        volume = _float_or_none(row.get("vole")) or 0.0
        if pd.isna(ts) or price is None:
            continue
        out.append((ts, price, price, price, price, int(volume)))
    if not out:
        return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])

    df = pd.DataFrame(out, columns=["Date", "Open", "High", "Low", "Close", "Volume"])
    df = df.drop_duplicates(subset=["Date"], keep="last").sort_values("Date").set_index("Date")
    return df[["Open", "High", "Low", "Close", "Volume"]]
