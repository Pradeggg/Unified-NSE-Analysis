"""
terminal/web_research.py
Multi-source web research for Agent Adda.

Sources
───────
• screener.in      — fundamentals, ratios, pros/cons, quarterly P&L,
                     BSE filings links, annual-report links
• finance.yahoo.com — price stats, YF news feed
• moneycontrol.com  — via DuckDuckGo site: search (direct API blocks)
• NSE / BSE         — corporate-announcement links via screener.in scrape
• General web       — multi-site DuckDuckGo search with real URL decoding

All functions return plain dicts so they can be passed directly to the LLM.
Every result includes a `source_url` field (the page that was scraped) and
real hyperlinks wherever possible.
"""

from __future__ import annotations

import re
import urllib.parse
from typing import Any

import requests
from bs4 import BeautifulSoup

# ── shared session + headers ──────────────────────────────────────────────────
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

_TIMEOUT = 12


def _get(url: str, extra_headers: dict | None = None, **kw) -> requests.Response:
    h = {**_HEADERS, **(extra_headers or {})}
    return requests.get(url, headers=h, timeout=_TIMEOUT, **kw)


def _decode_ddg_url(raw: str) -> str:
    """Extract real URL from DuckDuckGo redirect (/l/?uddg=<encoded>).
    Returns '' for DDG ad/tracking URLs (y.js) so they get filtered out."""
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


# ─────────────────────────────────────────────────────────────────────────────
# 1a. yfinance helpers — fill in when screener.in JS-renders its numbers
# ─────────────────────────────────────────────────────────────────────────────

def _fmt(v, pct: bool = False, crore: bool = False) -> str:
    """Format a numeric value for display."""
    if v is None:
        return "N/A"
    try:
        f = float(v)
        if crore:
            return f"₹{f/1e7:.0f} Cr"
        if pct:
            return f"{f*100:.2f}%"
        return f"{f:.2f}"
    except (TypeError, ValueError):
        return str(v)


def _get_yfinance_ratios(symbol: str) -> dict:
    """Fetch key financial ratios from yfinance for an NSE stock."""
    try:
        import yfinance as yf
        info = yf.Ticker(f"{symbol}.NS").info
    except Exception:
        return {}

    def _pct(key): return _fmt(info.get(key), pct=True)
    def _num(key): return _fmt(info.get(key))
    def _cr(key):  return _fmt(info.get(key), crore=True)

    # dividendYield from yfinance for NSE stocks is already expressed as a percentage
    # (0.19 means 0.19%, not 19%). Don't multiply by 100.
    div_yield_raw = info.get("dividendYield") or info.get("trailingAnnualDividendYield")
    div_str = f"{div_yield_raw:.2f}%" if div_yield_raw else "0.00%"

    return {
        "Market Cap":       _cr("marketCap"),
        "Current Price":    f"₹{_fmt(info.get('currentPrice'))}",
        "52W High":         f"₹{_fmt(info.get('fiftyTwoWeekHigh'))}",
        "52W Low":          f"₹{_fmt(info.get('fiftyTwoWeekLow'))}",
        "Stock P/E":        _num("trailingPE"),
        "Forward P/E":      _num("forwardPE"),
        "Price to Book":    _num("priceToBook"),
        "Book Value":       f"₹{_fmt(info.get('bookValue'))}",
        "Dividend Yield":   div_str,
        "ROE":              _pct("returnOnEquity") if info.get("returnOnEquity") else "N/A (see financials)",
        "Gross Margin":     _pct("grossMargins"),
        "Operating Margin": _pct("operatingMargins"),
        "Net Margin":       _pct("profitMargins"),
        "Revenue Growth":   _pct("revenueGrowth"),
        "Earnings Growth":  _pct("earningsGrowth"),
        "Debt/Equity":      _num("debtToEquity"),
        "EV/EBITDA":        _num("enterpriseToEbitda"),
        "Beta":             _num("beta"),
        "_source":          "yfinance (screener.in values are JS-rendered)",
    }


def _get_yfinance_financials(symbol: str) -> dict:
    """Get quarterly and annual financials from yfinance."""
    try:
        import yfinance as yf
        t = yf.Ticker(f"{symbol}.NS")
        result: dict = {}

        # Quarterly income statement
        try:
            qf = t.quarterly_financials
            if not qf.empty:
                cols = [c.strftime("%b %Y") if hasattr(c, "strftime") else str(c) for c in qf.columns[:5]]
                rows_q: dict = {"_headers": cols}
                for idx in ["Total Revenue", "Gross Profit", "Operating Income", "Net Income"]:
                    if idx in qf.index:
                        rows_q[idx] = [_fmt(qf.loc[idx, c] / 1e7, False) + " Cr"
                                       for c in qf.columns[:5]]
                result["quarterly"] = rows_q
        except Exception:
            pass

        # Annual income statement (last 4 years)
        try:
            af = t.financials
            if not af.empty:
                cols = [c.strftime("%b %Y") if hasattr(c, "strftime") else str(c) for c in af.columns[:5]]
                rows_a: dict = {"_headers": cols}
                for idx in ["Total Revenue", "Gross Profit", "Operating Income", "Net Income"]:
                    if idx in af.index:
                        rows_a[idx] = [_fmt(af.loc[idx, c] / 1e7, False) + " Cr"
                                       for c in af.columns[:5]]
                result["annual_pl"] = rows_a
        except Exception:
            pass

        return result
    except Exception:
        return {}


# ─────────────────────────────────────────────────────────────────────────────
# 1b. Screener.in  — full fundamental page
# ─────────────────────────────────────────────────────────────────────────────

def scrape_screener_in(symbol: str) -> dict:
    """
    Scrape screener.in/company/{SYMBOL}/consolidated/ for:
      • key ratios  (P/E, P/B, ROE, ROCE, mkt-cap, div-yield …)
      • pros / cons from Screener's analysis
      • last 6 quarters of financials  (Sales, OPM%, Net Profit)
      • last 5 years of annual P&L
      • peer comparison column headers + up to 5 peer rows
      • BSE corporate-announcement PDF links (recent filings)
      • annual-report PDF links
      • shareholding data (promoter %, FII %, DII %)
      • direct deep links (screener page, NSE page, BSE page)
    """
    sym = symbol.upper().strip()
    base_url = f"https://www.screener.in/company/{sym}/consolidated/"
    try:
        resp = _get(base_url)
        if resp.status_code == 404:
            # Try standalone (non-consolidated) page
            base_url = f"https://www.screener.in/company/{sym}/"
            resp = _get(base_url)
        resp.raise_for_status()
    except Exception as e:
        return {"symbol": sym, "error": str(e), "source_url": base_url}

    soup = BeautifulSoup(resp.text, "lxml")

    # ── Extract BSE scrip code ──────────────────────────────────────────────
    bse_link_tag = soup.select_one('a[href*="bseindia.com"][href*="/stock-share-price/"]')
    bse_url = bse_link_tag["href"] if bse_link_tag else ""
    scrip_m = re.search(r"/(\d{6})/", bse_url)
    bse_scrip = scrip_m.group(1) if scrip_m else ""
    nse_url = f"https://www.nseindia.com/get-quotes/equity?symbol={sym}"

    # ── Key ratios (top bar) ────────────────────────────────────────────────
    ratios: dict[str, str] = {}
    for li in soup.select("#top-ratios li"):
        name = li.select_one(".name")
        val  = li.select_one(".number")
        if name and val:
            ratios[name.get_text(strip=True)] = val.get_text(strip=True)

    # ── Pros / Cons ─────────────────────────────────────────────────────────
    pros = [li.get_text(strip=True) for li in soup.select(".pros li")][:6]
    cons = [li.get_text(strip=True) for li in soup.select(".cons li")][:6]

    # ── Quarterly results (latest 6 columns) ────────────────────────────────
    quarterly: dict[str, Any] = {}
    qtable = soup.select_one("#quarters")
    if qtable:
        rows = qtable.select("tr")
        if rows:
            all_headers = [td.get_text(strip=True) for td in rows[0].select("td,th")][1:]
            headers = all_headers[-6:]
            for row in rows[1:]:
                cells = [td.get_text(strip=True) for td in row.select("td,th")]
                if cells:
                    values = cells[1:]
                    quarterly[cells[0]] = values[-len(headers):] if headers else values
            quarterly["_headers"] = headers

    # ── Annual P&L (latest 5 columns, including TTM when present) ───────────
    annual_pl: dict[str, Any] = {}
    plt = soup.select_one("#profit-loss")
    if plt:
        rows = plt.select("tr")
        if rows:
            all_headers = [td.get_text(strip=True) for td in rows[0].select("td,th")][1:]
            yr_headers = all_headers[-5:]
            for row in rows[1:]:
                cells = [td.get_text(strip=True) for td in row.select("td,th")]
                if cells and len(cells) > 1:
                    values = cells[1:]
                    if yr_headers and len(values) < len(yr_headers):
                        continue
                    annual_pl[cells[0]] = values[-len(yr_headers):] if yr_headers else values
            annual_pl["_headers"] = yr_headers

    # ── Peer comparison ──────────────────────────────────────────────────────
    peers: list[dict] = []
    peer_sec = soup.select_one("#peers")
    if peer_sec:
        p_rows = peer_sec.select("table tr")
        if p_rows:
            p_heads = [th.get_text(strip=True) for th in p_rows[0].select("th,td")]
            for row in p_rows[1:6]:
                cells = [td.get_text(strip=True) for td in row.select("td,th")]
                if cells and cells[0]:
                    peers.append(dict(zip(p_heads, cells)))

    # ── Shareholding (latest quarter) ────────────────────────────────────────
    shareholding: dict[str, str] = {}
    shp_sec = soup.select_one("#shareholding")
    if shp_sec:
        tbl_rows = shp_sec.select("table tr")
        headers_row = tbl_rows[0] if tbl_rows else None
        shp_headers = [th.get_text(strip=True) for th in headers_row.select("td,th")] if headers_row else []
        shareholding["_quarters"] = shp_headers[1:] if shp_headers else []
        for row in tbl_rows[1:6]:
            cells = [td.get_text(strip=True) for td in row.select("td,th")]
            if len(cells) >= 2:
                label = cells[0].rstrip("+").strip()
                shareholding[label] = cells[-1]   # latest column value
                shareholding[f"{label}_trend"] = cells[1:]  # full trend array

    # ── BSE Announcements (recent filings with PDF links) ────────────────────
    announcements: list[dict] = []
    ann_sec = soup.select_one("#company-announcements-tab")
    if not ann_sec:
        ann_sec = soup.find(id="company-announcements-tab")
    if ann_sec:
        for a in ann_sec.select("a[href*='bseindia.com']")[:8]:
            title = a.get_text(strip=True)
            href  = a.get("href", "")
            if title and href:
                announcements.append({"title": title[:120], "url": href})

    # Fallback: collect all BSE filing PDFs from anywhere on page
    if not announcements:
        for a in soup.select("a[href*='bseindia.com/xml-data/corpfiling']")[:8]:
            title = a.get_text(strip=True) or a.get("title", "BSE Filing")
            announcements.append({"title": title[:120], "url": a["href"]})

    # ── Annual Reports ───────────────────────────────────────────────────────
    annual_reports: list[dict] = []
    for a in soup.select("a[href*='AnnualReport'], a[href*='annual-report'], "
                         "a[href*='bseplus/AnnualReport']")[:6]:
        txt  = a.get_text(strip=True)
        href = a.get("href", "")
        if href:
            annual_reports.append({"label": txt or "Annual Report", "url": href})

    # ── Concall transcripts — parsed from static HTML ────────────────────────
    # screener.in summary page requires login but transcript PDFs, PPTs, and
    # recording links are directly accessible without auth
    concalls: list[dict] = []
    concalls_link = f"https://www.screener.in/company/{sym}/#concalls"
    concall_div   = soup.find(class_="concalls")
    if concall_div:
        for li in concall_div.select("ul.list-links li")[:8]:
            # Period label (e.g. "Feb 2026")
            label_tag = li.find("div", class_=lambda c: c and "ink-600" in c)
            period    = label_tag.get_text(strip=True) if label_tag else ""
            entry: dict = {"period": period}
            for a in li.select("a.concall-link"):
                href  = a.get("href", "")
                title = a.get_text(strip=True)
                if "Transcript" in a.get("title", "") or title == "Transcript":
                    entry["transcript_url"] = href
                    entry["transcript_label"] = f"{period} Earnings Call Transcript"
                elif title == "REC":
                    entry["recording_url"] = href
                elif title == "PPT":
                    entry["ppt_url"] = href
            # AI Summary button — note the title/url but it needs login
            for btn in li.select("button.concall-link"):
                entry["ai_summary_title"] = btn.get("data-title", "")
            if entry.get("period"):
                concalls.append(entry)

    # ── Enrich with yfinance when screener.in values are JS-rendered ────────
    # screener.in populates .number spans via JavaScript; static HTML has empty spans.
    if not any(v for v in ratios.values()):
        ratios = _get_yfinance_ratios(sym)

    # Supplement empty quarterly/annual tables with yfinance financials
    if not quarterly or not any(v for k, v in quarterly.items() if k != "_headers" and v):
        yf_fin = _get_yfinance_financials(sym)
        if yf_fin.get("quarterly"):
            quarterly = yf_fin["quarterly"]
        if yf_fin.get("annual_pl"):
            annual_pl = yf_fin["annual_pl"]

    return {
        "symbol":         sym,
        "source_url":     base_url,
        "nse_url":        nse_url,
        "bse_url":        bse_url,
        "bse_scrip":      bse_scrip,
        "ratios":         ratios,
        "pros":           pros,
        "cons":           cons,
        "quarterly":      quarterly,
        "annual_pl":      annual_pl,
        "peers":          peers,
        "shareholding":   shareholding,
        "announcements":  announcements,
        "annual_reports": annual_reports,
        "concalls":       concalls,
        "concalls_link":  concalls_link,
        "note": (
            f"Found {len(concalls)} concall entries. Transcript PDFs are directly accessible. "
            "AI summaries on screener.in require login. "
            f"Full concall list: {concalls_link}"
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 2.  Yahoo Finance  — price stats + news
# ─────────────────────────────────────────────────────────────────────────────

def search_yahoo_finance(symbol: str) -> dict:
    """
    Fetch from Yahoo Finance:
      • current price, 52-week range, day range, volume  (chart API)
      • up to 6 news articles with real URLs              (search API)
    NSE symbols use the .NS suffix (e.g. TCS.NS).
    """
    sym_yf  = symbol.upper().strip()
    sym_ns  = sym_yf if sym_yf.endswith(".NS") else f"{sym_yf}.NS"
    yf_page = f"https://finance.yahoo.com/quote/{sym_ns}/"

    # ── Price stats ─────────────────────────────────────────────────────────
    stats: dict[str, Any] = {}
    try:
        chart_url = (
            f"https://query1.finance.yahoo.com/v8/finance/chart/{sym_ns}"
            "?range=1d&interval=1d"
        )
        r = _get(chart_url)
        meta = (r.json().get("chart", {}).get("result") or [{}])[0].get("meta", {})
        stats = {
            "current_price":     meta.get("regularMarketPrice"),
            "previous_close":    meta.get("chartPreviousClose"),
            "52w_high":          meta.get("fiftyTwoWeekHigh"),
            "52w_low":           meta.get("fiftyTwoWeekLow"),
            "currency":          meta.get("currency"),
            "exchange_timezone": meta.get("exchangeTimezoneName"),
        }
    except Exception as e:
        stats = {"error": str(e)}

    # ── News ─────────────────────────────────────────────────────────────────
    news: list[dict] = []
    try:
        search_url = (
            f"https://query2.finance.yahoo.com/v1/finance/search"
            f"?q={urllib.parse.quote(sym_yf + ' NSE India')}"
            f"&newsCount=6&quotesCount=1&lang=en-US&region=IN"
        )
        d = _get(search_url).json()
        for n in d.get("news", [])[:6]:
            title = n.get("title", "")
            url   = n.get("link", "")
            if title and url:
                news.append({
                    "title":     title,
                    "url":       url,
                    "publisher": n.get("publisher", ""),
                })
    except Exception as e:
        news = [{"error": str(e)}]

    return {
        "symbol":      sym_yf,
        "yf_page_url": yf_page,
        "stats":       stats,
        "news":        news,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 3.  Multi-site DuckDuckGo search
# ─────────────────────────────────────────────────────────────────────────────

class _DDGParser(object):
    """Minimal DuckDuckGo HTML result parser (no external dep)."""

    def parse(self, html: str) -> list[dict]:
        from html.parser import HTMLParser

        results: list[dict] = []
        cur: dict = {}
        in_result = False

        class _P(HTMLParser):
            def handle_starttag(self_, tag, attrs):
                nonlocal in_result, cur
                ad = dict(attrs)
                if tag == "a" and ad.get("class") == "result__a":
                    cur = {"url": _decode_ddg_url(ad.get("href", "")), "title": ""}
                    in_result = True
                elif tag == "td" and "result__snippet" in ad.get("class", ""):
                    in_result = True

            def handle_data(self_, data):
                nonlocal in_result, cur
                if in_result and data.strip():
                    if "title" in cur and not cur["title"]:
                        cur["title"] = data.strip()
                    elif "snippet" not in cur:
                        cur["snippet"] = data.strip()

            def handle_endtag(self_, tag):
                nonlocal in_result, cur
                if tag == "a" and in_result and cur.get("title"):
                    if len(cur["title"]) > 5:
                        results.append(dict(cur))
                    cur = {}
                    in_result = False

        _P().feed(html)
        return results


_ddg = _DDGParser()


def _ddg_search(query: str, max_results: int = 5) -> list[dict]:
    """Single DuckDuckGo HTML search, returns [{title, url, snippet}]."""
    try:
        url  = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
        resp = _get(url)
        raw  = _ddg.parse(resp.text)
        return [r for r in raw if r.get("url") and r.get("title")][:max_results]
    except Exception:
        return []


def multi_source_web_search(symbol: str, company_name: str = "",
                             extra_query: str = "") -> dict:
    """
    Run parallel DuckDuckGo searches targeting high-quality finance sites:
      • moneycontrol.com  (news + analysis)
      • screener.in       (fundamental data page)
      • economictimes.indiatimes.com  (news)
      • nseindia.com      (official data)
      • bseindia.com      (filings, corporate actions)
    Returns up to 5 results per source with real decoded URLs.
    """
    sym   = symbol.upper().strip()
    co    = company_name or sym
    extra = extra_query.strip()

    site_queries = {
        "moneycontrol": f"{co} NSE {extra} site:moneycontrol.com",
        "screener_in":  f"{sym} {extra} site:screener.in",
        "economic_times": f"{co} NSE {extra} site:economictimes.indiatimes.com",
        "nse_india":    f"{sym} site:nseindia.com",
        "bse_india":    f"{co} site:bseindia.com",
    }

    results: dict[str, list[dict]] = {}
    for source, q in site_queries.items():
        hits = _ddg_search(q, max_results=4)
        if hits:
            results[source] = hits

    # Also run a general search for concalls / transcripts
    concall_hits = _ddg_search(
        f"{co} concall transcript {extra} 2025 2026 site:screener.in OR site:moneycontrol.com OR site:bseindia.com",
        max_results=4,
    )
    if concall_hits:
        results["concalls"] = concall_hits

    return {
        "symbol":   sym,
        "company":  co,
        "results":  results,
        "total_results": sum(len(v) for v in results.values()),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 4.  Comprehensive stock research  (calls all sources, merges output)
# ─────────────────────────────────────────────────────────────────────────────

def comprehensive_stock_research(symbol: str, aspects: list[str] | None = None) -> dict:
    """
    One-call deep research across all sources.

    aspects: list of strings from {"fundamentals", "news", "concalls",
                                    "peers", "filings", "ratios", "all"}
    Defaults to all aspects.

    Returns a merged dict with sections from each source plus
    direct deep-link URLs for every data point.
    """
    sym     = symbol.upper().strip()
    aspects = [a.lower() for a in (aspects or ["all"])]
    want    = lambda k: "all" in aspects or k in aspects

    out: dict[str, Any] = {"symbol": sym, "sources_fetched": []}

    # ── Screener.in (fundamentals, ratios, docs, peers) ────────────────────
    if want("fundamentals") or want("ratios") or want("peers") or want("filings"):
        sc = scrape_screener_in(sym)
        if "error" not in sc:
            out["screener"] = sc
            out["sources_fetched"].append("screener.in")

    # ── Yahoo Finance (price stats + news) ──────────────────────────────────
    if want("news") or want("fundamentals"):
        yf = search_yahoo_finance(sym)
        out["yahoo_finance"] = yf
        if yf.get("news"):
            out["sources_fetched"].append("finance.yahoo.com")

    # ── Multi-site search (moneycontrol, ET, NSE, BSE, concalls) ──────────
    if want("news") or want("concalls"):
        co = (out.get("screener", {}).get("ratios", {}).get("Name", "")
              or sym)
        ms = multi_source_web_search(sym, company_name=co)
        out["web_search"] = ms
        if ms.get("total_results", 0) > 0:
            out["sources_fetched"].append("multi-site (moneycontrol/ET/NSE/BSE)")

    # ── Direct deep-links summary ────────────────────────────────────────────
    links: dict[str, str] = {
        "screener_in_fundamentals": f"https://www.screener.in/company/{sym}/consolidated/",
        "screener_in_concalls":     f"https://www.screener.in/company/{sym}/#concalls",
        "nse_quote":                f"https://www.nseindia.com/get-quotes/equity?symbol={sym}",
        "yahoo_finance":            f"https://finance.yahoo.com/quote/{sym}.NS/",
        "moneycontrol_search":      f"https://www.moneycontrol.com/markets/indian-indices/top-nse-listed-companies/?classic=true&tab=MC500",
        "google_news":              f"https://news.google.com/search?q={urllib.parse.quote(sym + ' NSE India')}",
    }
    bse_scrip = out.get("screener", {}).get("bse_scrip", "")
    if bse_scrip:
        links["bse_announcements"] = (
            f"https://www.bseindia.com/stock-share-price/"
            f"company/TCS/{bse_scrip}/corp-announcements/"
        )
    out["direct_links"] = links

    return out
