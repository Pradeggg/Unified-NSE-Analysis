"""
terminal/search_engine.py
Deep Search Engine for Agent Adda — NSE Market Research Terminal.

Nine distinct, parallel search verticals:
──────────────────────────────────────────────────────────────────
  1. nse_corp_announcements   — NSE corporate announcements (live JSON)
  2. nse_corporate_actions    — Dividends, splits, bonuses, rights (NSE)
  3. nse_insider_trades       — SAST/PIT insider trade disclosures (NSE)
  4. bse_filings              — BSE corporate filings by company
  5. shareholding_analysis    — Promoter / FII / DII holding trends (screener.in)
  6. analyst_coverage         — Analyst targets, ratings, recommendations (DDG + Screener)
  7. concall_transcripts      — Earnings call transcripts & highlights
  8. sector_news_pulse        — Sector-specific news across 6 financial portals
  9. social_market_buzz       — Reddit / StockTwits / forum mentions

Orchestration:
  deep_search(symbol, context) — runs all relevant verticals in parallel via
  ThreadPoolExecutor, merges results, deduplicates URLs.

All functions return plain dicts for direct LLM consumption.
"""

from __future__ import annotations

import re
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Any

import requests
from bs4 import BeautifulSoup

# ── shared HTTP helpers ───────────────────────────────────────────────────────

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "*/*",
}

_TIMEOUT = 12
_NSE_REF = "https://www.nseindia.com/"

# One reusable NSE-authenticated session (warm-up on first use)
_nse_session: requests.Session | None = None


def _nse() -> requests.Session:
    """Return a warm NSE session (auto warm-ups on first call)."""
    global _nse_session
    if _nse_session is None:
        s = requests.Session()
        s.headers.update({**_HEADERS, "Referer": _NSE_REF})
        try:
            s.get(_NSE_REF, timeout=8)
            time.sleep(0.3)
        except Exception:
            pass
        _nse_session = s
    return _nse_session


def _get(url: str, headers: dict | None = None, **kw) -> requests.Response:
    h = {**_HEADERS, **(headers or {})}
    return requests.get(url, headers=h, timeout=_TIMEOUT, **kw)


def _decode_ddg_url(raw: str) -> str:
    if not raw:
        return ""
    if raw.startswith("//"):
        raw = "https:" + raw
    # DDG ad tracking URLs — opaque Bing redirect chains, not useful results
    if "duckduckgo.com/y.js" in raw:
        return ""
    parsed = urllib.parse.urlparse(raw)
    qs = urllib.parse.parse_qs(parsed.query)
    return qs["uddg"][0] if "uddg" in qs else raw


def _ddg(query: str, max_results: int = 6) -> list[dict]:
    """Minimal DuckDuckGo HTML search — no external dependency."""
    from html.parser import HTMLParser

    results: list[dict] = []
    cur: dict = {}
    in_result = False
    in_snippet = False

    class _P(HTMLParser):
        nonlocal in_result, in_snippet, cur, results

        def handle_starttag(self, tag, attrs):
            nonlocal in_result, in_snippet, cur
            ad = dict(attrs)
            if tag == "a" and ad.get("class") == "result__a":
                cur = {"url": _decode_ddg_url(ad.get("href", "")), "title": ""}
                in_result = True
                in_snippet = False
            elif tag == "td" and "result__snippet" in ad.get("class", ""):
                in_snippet = True

        def handle_data(self, data):
            nonlocal in_result, in_snippet, cur
            d = data.strip()
            if not d:
                return
            if in_result and "title" in cur and not cur["title"]:
                cur["title"] = d
            elif in_snippet and "snippet" not in cur:
                cur["snippet"] = d

        def handle_endtag(self, tag):
            nonlocal in_result, in_snippet, cur
            if tag == "a" and in_result and cur.get("title") and len(cur["title"]) > 5:
                results.append(dict(cur))
                cur = {}
                in_result = False
            if tag == "td":
                in_snippet = False

    try:
        url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
        resp = _get(url)
        _P().feed(resp.text)
    except Exception:
        pass
    return [r for r in results if r.get("url")][:max_results]


# ═════════════════════════════════════════════════════════════════════════════
# Vertical 1 — NSE Corporate Announcements
# ═════════════════════════════════════════════════════════════════════════════

def search_nse_announcements(symbol: str, max_results: int = 15) -> dict:
    """
    Fetch recent corporate announcements/filings for a stock.

    Primary source: screener.in documents section (BSE XML attachment links).
    Fallback: DuckDuckGo site:bseindia.com search.

    Returns filing title, date hint, attachment PDF/XML URL.

    Args:
        symbol: NSE ticker symbol (e.g. 'RELIANCE').
        max_results: How many recent announcements to return.
    """
    sym = symbol.upper().strip()
    url = f"https://www.screener.in/company/{sym}/consolidated/"
    results = []

    try:
        resp = _get(url)
        if resp.status_code == 404:
            url = f"https://www.screener.in/company/{sym}/"
            resp = _get(url)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        # screener.in documents section — BSE filing links
        for a in soup.select(
            '#documents a[href*="bseindia.com"], '
            'a[href*="xml-data/corpfiling"], '
            'a[href*="nsearchives.nseindia.com"]'
        )[:max_results]:
            title = a.get_text(strip=True)
            href  = a.get("href", "")
            if href and len(title) > 5:
                # Exclude "All" nav links
                if title.lower() in ("all", "view all", "announcements"):
                    continue
                results.append({
                    "subject":    title[:150],
                    "url":        href,
                    "source_site": "bseindia.com" if "bseindia" in href else "nseindia.com",
                })

    except Exception:
        pass

    # Fallback: DuckDuckGo search for recent NSE/BSE filings
    if not results:
        company = sym
        try:
            from terminal.tools import get_symbol_snapshot
            info = get_symbol_snapshot(sym)
            company = info.get("company_name") or sym
        except Exception:
            pass
        hits = _ddg(
            f"{company} corporate announcement BSE filing 2025 2026 site:bseindia.com",
            max_results=max_results,
        )
        results = [{"subject": h["title"], "url": h["url"], "source_site": "bseindia.com"}
                   for h in hits]

    # Also get recent exchange fillings via NSE corp-info API (may return empty but worth trying)
    nse_items = []
    try:
        s = _nse()
        r = s.get(
            f"https://www.nseindia.com/api/corp-info"
            f"?symbol={urllib.parse.quote(sym)}&corpType=announcements&market=equities",
            timeout=_TIMEOUT,
        )
        if r.ok:
            data = r.json()
            items = data.get("data", []) if isinstance(data, dict) else []
            for item in items[:5]:
                sub = item.get("subject") or item.get("desc") or ""
                dt  = item.get("an_dt") or ""
                att = item.get("attchmntFile") or ""
                att_url = att if att.startswith("http") else (
                    f"https://nsearchives.nseindia.com/corporate/{att}" if att else ""
                )
                if sub:
                    nse_items.append({
                        "date":       dt,
                        "subject":    sub,
                        "url":        att_url,
                        "source_site": "nseindia.com",
                    })
    except Exception:
        pass

    return {
        "symbol":       sym,
        "count":        len(results) + len(nse_items),
        "bse_filings":  results[:max_results],
        "nse_filings":  nse_items,
        "source":       "screener.in (BSE filing links) + NSE corp-info API",
        "source_url":   url,
    }


# ═════════════════════════════════════════════════════════════════════════════
# Vertical 2 — NSE Corporate Actions (Dividends, Splits, Bonuses, Rights)
# ═════════════════════════════════════════════════════════════════════════════

def search_corporate_actions(symbol: str, max_results: int = 12) -> dict:
    """
    Fetch dividends, stock splits, bonus issues, rights issues, and AGMs
    directly from NSE's corporate actions API.

    Args:
        symbol: NSE ticker symbol.
        max_results: Number of upcoming/recent corporate actions to return.
    """
    sym = symbol.upper().strip()
    url = (
        f"https://www.nseindia.com/api/corporates-corporateActions"
        f"?index=equities&symbol={urllib.parse.quote(sym)}&issuer="
    )
    try:
        s = _nse()
        r = s.get(url, timeout=_TIMEOUT)
        r.raise_for_status()
        items = r.json()
        if isinstance(items, dict):
            items = items.get("data", [])
    except Exception as e:
        return {"symbol": sym, "error": str(e), "source": "NSE corporate actions API"}

    results = []
    for item in (items or [])[:max_results]:
        subject = item.get("subject", "")
        ex_date = item.get("exDate", "") or item.get("ex_date", "")
        rec_dt  = item.get("recDate", "") or item.get("rec_date", "")
        results.append({
            "ex_date":    ex_date,
            "record_date": rec_dt,
            "subject":    subject,
            "face_value": item.get("faceVal"),
            "series":     item.get("series", "EQ"),
        })

    upcoming = [r for r in results if r["ex_date"] and r["ex_date"] != "-"]

    return {
        "symbol":   sym,
        "count":    len(results),
        "upcoming": upcoming[:5],
        "all":      results,
        "source":   "NSE corporate actions API (live)",
        "source_url": f"https://www.nseindia.com/companies-listing/corporate-filings-corporate-actions",
    }


# ═════════════════════════════════════════════════════════════════════════════
# Vertical 3 — NSE Insider Trades (PIT/SAST disclosures)
# ═════════════════════════════════════════════════════════════════════════════

def search_insider_trades(symbol: str, max_results: int = 15) -> dict:
    """
    Fetch promoter / director / key-person insider trading disclosures from NSE.

    Source: NSE PIT (Prohibition of Insider Trading) disclosure database.
    Covers: Regulation 7(2) SEBI PIT — acquisition / disposal by insiders.

    Args:
        symbol: NSE ticker symbol.
        max_results: Number of disclosures to return.
    """
    sym = symbol.upper().strip()
    url = (
        f"https://www.nseindia.com/api/corporates-pit"
        f"?symbol={urllib.parse.quote(sym)}&issuer=&fromDate=&toDate="
        f"&acquisitionMode=&before=&after=&modeVal=&modeCategory="
    )
    try:
        s = _nse()
        r = s.get(url, timeout=_TIMEOUT)
        r.raise_for_status()
        data = r.json()
        items = data.get("data", data) if isinstance(data, dict) else data
    except Exception as e:
        return {"symbol": sym, "error": str(e), "source": "NSE PIT disclosures"}

    buys = sells = 0
    results = []
    for item in (items or [])[:max_results]:
        txn    = (item.get("tdpTransactionType") or "").strip()
        qty    = int(item.get("secAcq") or 0)
        bval   = float(item.get("buyValue") or 0)
        sval   = float(item.get("sellValue") or 0)
        xbrl   = item.get("xbrl", "")
        if txn == "Buy":
            buys += 1
        elif txn == "Sell":
            sells += 1
        results.append({
            "date":           item.get("date", ""),
            "name":           item.get("acqName", ""),
            "transaction":    txn,
            "quantity":       qty,
            "buy_value_cr":   round(bval / 1e7, 2) if bval else 0,
            "sell_value_cr":  round(sval / 1e7, 2) if sval else 0,
            "security_type":  item.get("secType", ""),
            "disclosure_url": xbrl if xbrl.startswith("http") else "",
        })

    sentiment = "BULLISH (insiders buying)" if buys > sells else (
                "BEARISH (insiders selling)" if sells > buys else "NEUTRAL")

    return {
        "symbol":       sym,
        "company":      (items[0].get("company", sym) if items else sym),
        "total_shown":  len(results),
        "insider_buys": buys,
        "insider_sells": sells,
        "insider_sentiment": sentiment,
        "disclosures":  results,
        "source":       "NSE PIT disclosures (live)",
        "source_url":   "https://www.nseindia.com/companies-listing/corporate-filings-insider-trading",
    }


# ═════════════════════════════════════════════════════════════════════════════
# Vertical 4 — BSE Corporate Filings
# ═════════════════════════════════════════════════════════════════════════════

def search_bse_filings(symbol: str, max_results: int = 10) -> dict:
    """
    Fetch recent corporate filings from BSE India.

    Uses DuckDuckGo site:bseindia.com search to surface filings, annual reports,
    concall notices, and result publications for the company.

    Args:
        symbol: NSE ticker symbol (company name derived internally).
        max_results: Number of results per BSE category.
    """
    sym = symbol.upper().strip()

    # Get company name from NSE for better search
    company = sym
    try:
        from terminal.tools import get_symbol_snapshot
        info = get_symbol_snapshot(sym)
        company = info.get("company_name") or sym
    except Exception:
        pass

    categories = {
        "board_meeting":     f"{company} board meeting results BSE India site:bseindia.com",
        "annual_report":     f"{company} annual report site:bseindia.com",
        "concall_notice":    f"{company} concall earnings call site:bseindia.com",
        "investor_pres":     f"{company} investor presentation BSE site:bseindia.com",
    }

    results: dict[str, list[dict]] = {}
    for cat, query in categories.items():
        hits = _ddg(query, max_results=4)
        if hits:
            results[cat] = hits

    # Direct BSE search page link
    bse_search_url = (
        f"https://www.bseindia.com/corporates/ann.html"
        f"?expandable=0&strScrip=&strCat=-1&strType=C&strSearch=P"
    )

    return {
        "symbol":     sym,
        "company":    company,
        "results":    results,
        "total":      sum(len(v) for v in results.values()),
        "source":     "BSE India filings (via DuckDuckGo site:bseindia.com)",
        "source_url": bse_search_url,
    }


# ═════════════════════════════════════════════════════════════════════════════
# Vertical 5 — Shareholding Pattern Analysis
# ═════════════════════════════════════════════════════════════════════════════

def search_shareholding_analysis(symbol: str) -> dict:
    """
    Scrape quarterly shareholding pattern trends for a stock from screener.in.

    Returns promoter %, FII %, DII %, and public holding % across quarters,
    plus DII/FII change delta and any pledge data.

    Args:
        symbol: NSE ticker symbol.
    """
    sym = symbol.upper().strip()
    url = f"https://www.screener.in/company/{sym}/consolidated/"
    try:
        resp = _get(url)
        if resp.status_code == 404:
            url = f"https://www.screener.in/company/{sym}/"
            resp = _get(url)
        resp.raise_for_status()
    except Exception as e:
        return {"symbol": sym, "error": str(e)}

    soup = BeautifulSoup(resp.text, "lxml")
    shp: dict[str, Any] = {}

    shp_sec = soup.select_one("#shareholding")
    if shp_sec:
        # Table rows: Promoters, FII, DII, Public, ...
        tbl = shp_sec.select("table")
        for t in tbl:
            rows = t.select("tr")
            if not rows:
                continue
            hdrs = [th.get_text(strip=True) for th in rows[0].select("th")]
            for row in rows[1:]:
                cells = [td.get_text(strip=True) for td in row.select("td")]
                if cells and cells[0]:
                    shp[cells[0]] = dict(zip(hdrs[1:], cells[1:])) if hdrs else cells[1:]

    # Pledge %
    pledge = ""
    for li in soup.select(".cons li"):
        txt = li.get_text(strip=True)
        if "pledge" in txt.lower():
            pledge = txt
            break

    # Latest ratios: promoter %, FII %, DII %
    latest: dict[str, str] = {}
    if shp:
        for key, val in shp.items():
            if isinstance(val, dict):
                cols = list(val.values())
                latest[key] = cols[-1] if cols else ""
            elif isinstance(val, list):
                latest[key] = val[-1] if val else ""

    # FII trend: compare last 2 quarters
    fii_trend = ""
    for k in ("FII + FPI", "Foreign Institutional Investors", "FII"):
        if k in shp:
            vals = list(shp[k].values()) if isinstance(shp[k], dict) else shp[k]
            nums = []
            for v in vals:
                try:
                    nums.append(float(str(v).replace("%", "").replace(",", "")))
                except ValueError:
                    pass
            if len(nums) >= 2:
                delta = nums[-1] - nums[-2]
                fii_trend = f"{'+' if delta > 0 else ''}{delta:.2f}% QoQ"
            break

    return {
        "symbol":       sym,
        "latest":       latest,
        "quarterly":    shp,
        "fii_trend":    fii_trend,
        "pledge_alert": pledge,
        "source":       "screener.in shareholding section",
        "source_url":   url,
    }


# ═════════════════════════════════════════════════════════════════════════════
# Vertical 6 — Analyst Coverage (Targets, Ratings, Recommendations)
# ═════════════════════════════════════════════════════════════════════════════

def search_analyst_coverage(symbol: str, max_results: int = 8) -> dict:
    """
    Aggregate analyst price targets, buy/sell/hold ratings, and brokerage
    recommendations from multiple sources.

    Sources:
      • screener.in analyst data section
      • Moneycontrol analyst targets (DuckDuckGo)
      • Economic Times Markets analyst view
      • NSE research reports (DuckDuckGo site:nseindia.com)

    Args:
        symbol: NSE ticker symbol.
        max_results: Number of web results per source.
    """
    sym = symbol.upper().strip()

    company = sym
    try:
        from terminal.tools import get_symbol_snapshot
        info = get_symbol_snapshot(sym)
        company = info.get("company_name") or sym
    except Exception:
        pass

    # Source A: Screener.in analyst section (peer table sometimes has targets)
    screener_analysts: list[dict] = []
    try:
        url = f"https://www.screener.in/company/{sym}/consolidated/"
        resp = _get(url)
        if resp.status_code == 404:
            url = f"https://www.screener.in/company/{sym}/"
            resp = _get(url)
        soup = BeautifulSoup(resp.text, "lxml")
        # Screener notes section (analyst commentary)
        notes_sec = soup.select_one(".company-notes, #notes")
        if notes_sec:
            for note in notes_sec.select("li, p")[:4]:
                txt = note.get_text(strip=True)
                if txt and len(txt) > 30:
                    screener_analysts.append({"text": txt, "source": "screener.in"})
    except Exception:
        pass

    # Source B: Web search for analyst targets
    web_queries = {
        "moneycontrol_target": f"{company} NSE target price analyst recommendation site:moneycontrol.com",
        "et_analyst":         f"{company} NSE analyst buy sell hold target site:economictimes.indiatimes.com",
        "brokerage_reports":  f"{company} NSE brokerage report target price 2025 2026",
        "consensus_target":   f"{company} NSE analyst consensus target",
    }

    web_results: dict[str, list[dict]] = {}
    for key, q in web_queries.items():
        hits = _ddg(q, max_results=4)
        if hits:
            web_results[key] = hits

    return {
        "symbol":            sym,
        "company":           company,
        "screener_insights": screener_analysts,
        "web_results":       web_results,
        "total_web_hits":    sum(len(v) for v in web_results.values()),
        "source":            "screener.in + multi-site web search",
        "tip":               "Click any URL to read full analyst report",
    }


# ═════════════════════════════════════════════════════════════════════════════
# Vertical 7 — Concall Transcripts & Earnings Highlights
# ═════════════════════════════════════════════════════════════════════════════

def search_concall_transcripts(symbol: str, max_results: int = 8) -> dict:
    """
    Search for earnings call (concall) transcripts, PPTs, and highlights
    from multiple sources.

    Sources:
      • screener.in concall notes/transcripts
      • Trendlyne concall section
      • BSE / NSE investor relations filings
      • Moneycontrol, Economic Times
      • General web (PDF transcripts)

    Args:
        symbol: NSE ticker symbol.
        max_results: Results per source.
    """
    sym = symbol.upper().strip()

    company = sym
    try:
        from terminal.tools import get_symbol_snapshot
        info = get_symbol_snapshot(sym)
        company = info.get("company_name") or sym
    except Exception:
        pass

    year = datetime.now().year
    queries = {
        "screener_concall":   f"{company} concall transcript site:screener.in",
        "trendlyne_concall":  f"{company} concall transcript site:trendlyne.com",
        "bse_concall":        f"{company} concall earnings call transcript site:bseindia.com",
        "mc_concall":         f"{company} concall Q4 Q3 {year} site:moneycontrol.com",
        "et_concall":         f"{company} earnings call {year} site:economictimes.indiatimes.com",
        "general_transcript": f"\"{company}\" concall transcript {year} management commentary",
    }

    results: dict[str, list[dict]] = {}
    for key, q in queries.items():
        hits = _ddg(q, max_results=4)
        if hits:
            results[key] = hits

    # Also try screener.in notes for management commentary
    screener_notes: list[str] = []
    try:
        url = f"https://www.screener.in/company/{sym}/consolidated/"
        resp = _get(url)
        if resp.status_code == 404:
            url = f"https://www.screener.in/company/{sym}/"
            resp = _get(url)
        soup = BeautifulSoup(resp.text, "lxml")
        for sec in soup.select(".notes-body p, .company-notes p")[:3]:
            t = sec.get_text(strip=True)
            if t:
                screener_notes.append(t)
    except Exception:
        pass

    return {
        "symbol":          sym,
        "company":         company,
        "screener_notes":  screener_notes,
        "web_results":     results,
        "total_links":     sum(len(v) for v in results.values()),
        "source":          "screener.in + trendlyne + bse + web search",
    }


# ═════════════════════════════════════════════════════════════════════════════
# Vertical 8 — Sector News Pulse (6 portals in parallel)
# ═════════════════════════════════════════════════════════════════════════════

def search_sector_news(symbol: str, sector: str = "", max_results: int = 5) -> dict:
    """
    Aggregate sector-level news and macro context from 6 distinct portals.

    Runs parallel DuckDuckGo searches targeting:
      ET Markets, Business Standard, Mint, Moneycontrol, NSE India, LiveMint

    Args:
        symbol: NSE ticker symbol (sector auto-detected if not provided).
        sector: Sector name override (e.g. 'Banking', 'IT', 'Pharma').
        max_results: Results per portal.
    """
    sym = symbol.upper().strip()

    # Auto-detect sector
    detected_sector = sector
    if not detected_sector:
        try:
            from terminal.tools import get_symbol_snapshot
            info = get_symbol_snapshot(sym)
            detected_sector = info.get("sector") or info.get("industry") or ""
        except Exception:
            pass

    company = sym
    try:
        from terminal.tools import get_symbol_snapshot
        info = get_symbol_snapshot(sym)
        company = info.get("company_name") or sym
    except Exception:
        pass

    sector_label = detected_sector or "India"
    queries = {
        "et_markets":     f"{company} {sector_label} NSE site:economictimes.indiatimes.com/markets",
        "biz_standard":   f"{company} {sector_label} NSE site:business-standard.com",
        "mint":           f"{company} NSE {sector_label} site:livemint.com",
        "moneycontrol":   f"{company} NSE latest news site:moneycontrol.com",
        "financial_express": f"{company} NSE {sector_label} site:financialexpress.com",
        "hindu_business": f"{company} NSE site:thehindubusinessline.com",
    }

    results: dict[str, list[dict]] = {}
    for portal, q in queries.items():
        hits = _ddg(q, max_results=max_results)
        if hits:
            results[portal] = hits

    return {
        "symbol":          sym,
        "company":         company,
        "sector":          sector_label,
        "portal_results":  results,
        "total_articles":  sum(len(v) for v in results.values()),
        "portals_hit":     list(results.keys()),
        "source":          "6-portal DuckDuckGo search (ET, BS, Mint, MC, FE, HBL)",
    }


# ═════════════════════════════════════════════════════════════════════════════
# Vertical 9 — Social Market Buzz (Forums + Communities)
# ═════════════════════════════════════════════════════════════════════════════

def search_social_buzz(symbol: str, max_results: int = 5) -> dict:
    """
    Gauge retail investor sentiment from Indian investing communities and forums.

    Searches:
      • Reddit r/IndiaInvestments, r/IndianStockMarket
      • Valuepickr forum (long-term fundamental discussions)
      • Traderji (technical discussions)
      • Tijori Finance investor discussions

    Args:
        symbol: NSE ticker symbol.
        max_results: Results per platform.
    """
    sym = symbol.upper().strip()

    company = sym
    try:
        from terminal.tools import get_symbol_snapshot
        info = get_symbol_snapshot(sym)
        company = info.get("company_name") or sym
    except Exception:
        pass

    queries = {
        "reddit_india":     f"{company} NSE OR {sym} site:reddit.com/r/IndiaInvestments OR site:reddit.com/r/IndianStockMarket",
        "valuepickr":       f"{sym} OR \"{company}\" site:valuepickr.com",
        "traderji":         f"{sym} NSE site:traderji.com",
        "tijori":           f"{sym} site:tijorifinance.com",
        "stockdiscussion":  f"{company} NSE buy sell 2025 2026 target investors",
    }

    results: dict[str, list[dict]] = {}
    for platform, q in queries.items():
        hits = _ddg(q, max_results=max_results)
        if hits:
            results[platform] = hits

    # Aggregate total mentions + rough sentiment from titles
    all_titles = " ".join(
        h["title"].lower()
        for hits in results.values()
        for h in hits
    )
    bull_words = {"buy", "bullish", "breakout", "target", "multibagger", "upside", "strong", "rally"}
    bear_words = {"sell", "bearish", "avoid", "caution", "risk", "weak", "fall", "decline"}
    bull_count = sum(all_titles.count(w) for w in bull_words)
    bear_count = sum(all_titles.count(w) for w in bear_words)

    sentiment = "MIXED"
    if bull_count > bear_count * 1.5:
        sentiment = "BULLISH"
    elif bear_count > bull_count * 1.5:
        sentiment = "BEARISH"

    return {
        "symbol":          sym,
        "company":         company,
        "community_results": results,
        "total_mentions":  sum(len(v) for v in results.values()),
        "rough_sentiment": sentiment,
        "bull_signals":    bull_count,
        "bear_signals":    bear_count,
        "source":          "Reddit + Valuepickr + Traderji + Tijori (DuckDuckGo)",
        "disclaimer":      "Social sentiment is anecdotal — not investment advice",
    }


# ═════════════════════════════════════════════════════════════════════════════
# Vertical 10 — Broker & Institutional Research
# ═════════════════════════════════════════════════════════════════════════════

def search_broker_research(symbol: str, max_per_source: int = 5) -> dict:
    """
    Search for broker house research reports, institutional ratings, and price targets.

    Sources:
      • Trendlyne analyst view & consensus estimates (via DDG)
      • Moneycontrol broker radar & analyst reports (via DDG)
      • Economic Times Markets analyst reports (via DDG)
      • Finology broker research & buy/sell ratings (via DDG)
      • Screener.in analyst notes section (via DDG)
      • NSE research reports (via DDG)
      • Kotak / ICICI / HDFC / Edelweiss / Motilal reports (via DDG)

    Returns unified list of broker report links with titles, sources, and URLs.
    """
    sym = symbol.upper().strip()
    company = sym
    try:
        from terminal.tools import get_symbol_snapshot
        info = get_symbol_snapshot(sym)
        company = info.get("company_name") or sym
    except Exception:
        pass

    queries = {
        "trendlyne_consensus": (
            f"{sym} site:trendlyne.com analyst price target consensus rating"
        ),
        "moneycontrol_analyst": (
            f"\"{company}\" OR {sym} NSE site:moneycontrol.com broker recommendation target"
        ),
        "et_markets_reports": (
            f"{sym} OR \"{company}\" NSE analyst recommendation target 2025 2026 "
            f"site:economictimes.indiatimes.com"
        ),
        "finology_research": (
            f"{sym} NSE site:finology.in OR site:finviz.com buy sell recommendation"
        ),
        "broker_reports_general": (
            f"\"{company}\" NSE buy rating target price broker report "
            f"Motilal OR Kotak OR ICICI OR HDFC OR Edelweiss OR Axis 2025 2026"
        ),
        "nse_research": (
            f"{sym} NSE research report analyst equity 2025 site:nseindia.com OR site:nse500.in"
        ),
        "screener_notes": (
            f"{sym} site:screener.in analyst note price target earnings"
        ),
    }

    results: dict[str, list[dict]] = {}
    all_results: list[dict] = []

    for source, q in queries.items():
        hits = _ddg(q, max_results=max_per_source)
        if hits:
            results[source] = hits
            for h in hits:
                h["search_source"] = source
            all_results.extend(hits)

    # Deduplicate by URL
    seen_urls: set[str] = set()
    unique_results: list[dict] = []
    for item in all_results:
        url = item.get("url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique_results.append(item)

    # Extract price targets from titles using regex
    targets: list[dict] = []
    target_pattern = re.compile(
        r"(?:target|TP|price target)[:\s]+(?:Rs?\.?\s*|INR\s*)?([\d,]+)",
        re.I,
    )
    for item in unique_results:
        m = target_pattern.search(item.get("title", "") + " " + item.get("snippet", ""))
        if m:
            targets.append({
                "source": item.get("search_source", ""),
                "target": m.group(1).replace(",", ""),
                "title":  item["title"][:120],
                "url":    item.get("url", ""),
            })

    return {
        "symbol":         sym,
        "company":        company,
        "by_source":      results,
        "all_results":    unique_results[:25],
        "price_targets":  targets[:8],
        "total_results":  len(unique_results),
        "total_targets":  len(targets),
        "source":         "Trendlyne, Moneycontrol, ET, Finology, Broker PDFs (DuckDuckGo)",
        "disclaimer":     "Broker targets are forward-looking estimates — verify before trading",
    }


# ═════════════════════════════════════════════════════════════════════════════
# Vertical 11 — Mutual Fund & FII Holdings
# ═════════════════════════════════════════════════════════════════════════════

def search_mf_holdings(symbol: str, max_results: int = 8) -> dict:
    """
    Search for mutual fund and FII/DII institutional holding data.

    Sources:
      • Trendlyne MF holdings & FII activity (via DDG)
      • Moneycontrol mutual funds holding this stock (via DDG)
      • Screener.in shareholding section (direct scrape for promoter/FII/DII trend)
      • Tijori Finance institutional holdings (via DDG)
      • Value Research MF portfolio overlap (via DDG)

    Returns MF scheme names, holding percentages, recent changes.
    """
    sym = symbol.upper().strip()
    company = sym
    try:
        from terminal.tools import get_symbol_snapshot
        info = get_symbol_snapshot(sym)
        company = info.get("company_name") or sym
    except Exception:
        pass

    queries = {
        "trendlyne_mf": (
            f"{sym} site:trendlyne.com mutual fund holdings FII DII institutional"
        ),
        "moneycontrol_mf": (
            f"\"{company}\" OR {sym} NSE mutual fund holding bought sold "
            f"site:moneycontrol.com"
        ),
        "screener_shareholding": (
            f"{sym} shareholding pattern FII DII promoter pledge "
            f"site:screener.in"
        ),
        "tijori_holdings": (
            f"{sym} site:tijorifinance.com institutional holdings mutual fund"
        ),
        "value_research_mf": (
            f"\"{company}\" OR {sym} NSE mutual fund portfolio holding 2025 "
            f"site:valueresearchonline.com OR site:advisorkhoj.com"
        ),
        "nse_mf_change": (
            f"{sym} NSE FII DII institutional activity bought sold 2025 2026"
        ),
    }

    results: dict[str, list[dict]] = {}
    all_results: list[dict] = []

    for source, q in queries.items():
        hits = _ddg(q, max_results=max_results)
        if hits:
            results[source] = hits
            for h in hits:
                h["search_source"] = source
            all_results.extend(hits)

    # Deduplicate
    seen_urls: set[str] = set()
    unique_results: list[dict] = []
    for item in all_results:
        url = item.get("url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique_results.append(item)

    # Also try screener.in shareholding direct
    shareholding_data: dict = {}
    try:
        import requests as _req
        from bs4 import BeautifulSoup as _BS
        url_sc = f"https://www.screener.in/company/{sym}/consolidated/"
        r = _req.get(url_sc, headers=_HEADERS, timeout=10)
        if r.ok:
            soup = _BS(r.text, "lxml")
            shp_sec = soup.select_one("#shareholding")
            if shp_sec:
                tbl_rows = shp_sec.select("table tr")
                if tbl_rows:
                    hdr = [th.get_text(strip=True) for th in tbl_rows[0].select("td,th")]
                    for row in tbl_rows[1:6]:
                        cells = [td.get_text(strip=True) for td in row.select("td,th")]
                        if len(cells) >= 2:
                            label = cells[0].rstrip("+").strip()
                            shareholding_data[label] = {
                                "latest":    cells[-1],
                                "prev":      cells[-2] if len(cells) > 2 else None,
                                "trend":     cells[1:],
                                "quarters":  hdr[1:],
                            }
    except Exception:
        pass

    return {
        "symbol":            sym,
        "company":           company,
        "shareholding":      shareholding_data,
        "by_source":         results,
        "all_results":       unique_results[:20],
        "total_results":     len(unique_results),
        "shareholding_note": (
            "Direct screener.in shareholding data included where available. "
            "FII/DII/Promoter quarterly trend shown."
        ),
        "source": "Screener.in (direct) + Trendlyne, Moneycontrol, Tijori (DuckDuckGo)",
    }


# ═════════════════════════════════════════════════════════════════════════════
# Orchestrator — deep_search (runs all verticals in parallel)
# ═════════════════════════════════════════════════════════════════════════════

_ALL_VERTICALS = {
    "announcements":    search_nse_announcements,
    "corporate_actions": search_corporate_actions,
    "insider_trades":   search_insider_trades,
    "bse_filings":      search_bse_filings,
    "shareholding":     search_shareholding_analysis,
    "analyst_coverage": search_analyst_coverage,
    "concalls":         search_concall_transcripts,
    "sector_news":      search_sector_news,
    "social_buzz":      search_social_buzz,
    "broker_research":  search_broker_research,
    "mf_holdings":      search_mf_holdings,
}

# Which verticals are always fast (direct API, no web scraping)
_FAST_VERTICALS = {"announcements", "corporate_actions", "insider_trades"}


def deep_search(
    symbol: str,
    verticals: list[str] | None = None,
    context: str = "",
) -> dict:
    """
    Run multiple distinct search verticals in parallel for a comprehensive
    deep-dive on any NSE stock.

    Verticals available:
      • announcements     — NSE corporate announcements (live JSON)
      • corporate_actions — Dividends, splits, bonuses (NSE live)
      • insider_trades    — SAST/PIT insider buy/sell disclosures (NSE)
      • bse_filings       — BSE filings search
      • shareholding      — Promoter/FII/DII trend from screener.in
      • analyst_coverage  — Analyst targets + brokerage views
      • concalls          — Concall transcripts & PPTs
      • sector_news       — 6-portal sector news pulse
      • social_buzz       — Retail investor community sentiment

    Args:
        symbol:    NSE ticker symbol (e.g. 'TATACONSUM').
        verticals: List of vertical names to run. Defaults to all.
        context:   Optional free-text hint to bias which verticals to run
                   (e.g. 'results', 'dividends', 'insider', 'news').
    """
    sym = symbol.upper().strip()

    # Auto-select verticals from context keywords
    if not verticals:
        ctx = context.lower()
        if any(k in ctx for k in ("result", "quarterly", "earnings", "revenue", "profit")):
            verticals = ["announcements", "concalls", "analyst_coverage", "sector_news", "broker_research"]
        elif any(k in ctx for k in ("dividend", "bonus", "split", "rights", "action")):
            verticals = ["corporate_actions", "announcements", "shareholding"]
        elif any(k in ctx for k in ("insider", "promoter", "pledge", "holding")):
            verticals = ["insider_trades", "shareholding", "bse_filings", "mf_holdings"]
        elif any(k in ctx for k in ("analyst", "target", "rating", "recommend", "broker")):
            verticals = ["analyst_coverage", "broker_research", "concalls", "sector_news"]
        elif any(k in ctx for k in ("mf", "mutual fund", "fii", "dii", "institution")):
            verticals = ["mf_holdings", "shareholding", "insider_trades"]
        elif any(k in ctx for k in ("news", "latest", "recent", "update")):
            verticals = ["announcements", "sector_news", "bse_filings", "social_buzz"]
        elif any(k in ctx for k in ("social", "buzz", "sentiment", "forum", "reddit")):
            verticals = ["social_buzz", "analyst_coverage", "sector_news"]
        else:
            # Default: run most verticals (skip social + slow ones for speed)
            verticals = [
                "announcements", "corporate_actions", "insider_trades",
                "shareholding", "analyst_coverage", "concalls", "sector_news",
            ]

    tasks = {v: _ALL_VERTICALS[v] for v in verticals if v in _ALL_VERTICALS}

    results: dict[str, Any] = {
        "symbol":    sym,
        "verticals": list(tasks.keys()),
        "context":   context,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }
    errors: dict[str, str] = {}

    # Run all verticals in parallel
    with ThreadPoolExecutor(max_workers=min(len(tasks), 6)) as pool:
        futures = {pool.submit(fn, sym): name for name, fn in tasks.items()}
        for fut in as_completed(futures):
            name = futures[fut]
            try:
                results[name] = fut.result()
            except Exception as e:
                errors[name] = str(e)

    if errors:
        results["errors"] = errors

    # Summary line for LLM
    total_items = 0
    for v in tasks:
        vdata = results.get(v, {})
        if isinstance(vdata, dict):
            total_items += (
                vdata.get("count", 0) or
                vdata.get("total", 0) or
                vdata.get("total_articles", 0) or
                vdata.get("total_links", 0) or
                vdata.get("total_mentions", 0) or
                len(vdata.get("results", [])) or
                len(vdata.get("disclosures", []))
            )

    results["_summary"] = (
        f"Deep search for {sym}: ran {len(tasks)} verticals, "
        f"~{total_items} data points retrieved."
    )

    return results
