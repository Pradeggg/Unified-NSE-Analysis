"""Web search layer for the Agent Adda Knowledge Base.

Provides DuckDuckGo-backed web search with title + snippet extraction,
scoped to NSE/financial queries when appropriate.

Used as an optional augmentation layer on top of BM25 (Layer 1) and
ChromaDB (Layer 2):

    Layer 1: BM25  → which command / tool to use          (< 10 ms, offline)
    Layer 2: Chroma → financial document search            (optional, local)
    Layer 3: Web   → latest real-world data + news        (--web flag)

Usage
-----
    from knowledge_base.web_search import web_search, format_web_block

    hits = web_search("NIFTY 50 performance August 2026", max_results=4)
    for h in hits:
        print(h["title"], h["url"])
        print(h["snippet"])

    block = format_web_block(hits, query="NIFTY performance")
    # → markdown block ready to append to a context block

CLI
---
    python -m knowledge_base query "NIFTY sector rotation August 2026" --web
    python -m knowledge_base query "HDFC Bank latest earnings" --web --top 3
"""
from __future__ import annotations

import re
import time
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import requests

from ._common import USER_AGENT

DDG_HTML = "https://html.duckduckgo.com/html/"
DDG_TIMEOUT = 15

# Finance-domain boost: these sources get score +0.3
FINANCE_DOMAINS = {
    "nseindia.com", "bseindia.com", "moneycontrol.com",
    "economictimes.indiatimes.com", "livemint.com", "business-standard.com",
    "financialexpress.com", "thehindu.com", "cnbctv18.com",
    "zeebiz.com", "ndtvprofit.com", "screener.in",
    "tradingview.com", "investing.com", "reuters.com", "bloomberg.com",
    "rbi.org.in", "sebi.gov.in",
}

# Spam / low-quality domains to skip
SKIP_DOMAINS = {
    "quora.com", "reddit.com", "facebook.com", "twitter.com",
    "instagram.com", "youtube.com", "pinterest.com",
}


def _unwrap_ddg(url: str) -> str:
    if "uddg=" in url:
        try:
            qs = parse_qs(urlparse(url).query)
            return unquote(qs.get("uddg", [url])[0]) or url
        except Exception:
            pass
    return url


def _domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().lstrip("www.")
    except Exception:
        return ""


def _web_search_ddgs(
    query: str,
    *,
    max_results: int = 5,
    finance_boost: bool = True,
    timeout: int = DDG_TIMEOUT,
) -> list[dict[str, Any]]:
    """Search via the ddgs Python library (bot-detection-resistant, replaces HTML scrape).

    Uses the official DuckDuckGo Search API client which rotates vqd tokens
    and does NOT hit html.duckduckgo.com — so it avoids the 202/CAPTCHA block.
    Falls back to the legacy HTML scrape if ddgs is not installed.
    """
    fetched_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    results: list[dict[str, Any]] = []
    try:
        from ddgs import DDGS  # type: ignore
    except ImportError:
        try:
            from duckduckgo_search import DDGS  # type: ignore  # older package name
        except ImportError:
            return []  # caller will fall back to HTML scrape

    try:
        with DDGS(timeout=timeout) as ddg:
            hits = ddg.text(query, max_results=max_results)
    except Exception:
        return []

    for h in hits or []:
        url  = h.get("href") or h.get("url") or ""
        if not url.startswith("http"):
            continue
        dom = _domain(url)
        if dom in SKIP_DOMAINS:
            continue
        snippet = re.sub(r"^\w+ \d+, \d{4} [–—-] ", "", h.get("body") or "")
        score = 1.3 if (finance_boost and any(fd in dom for fd in FINANCE_DOMAINS)) else 1.0
        results.append({
            "title":      h.get("title", ""),
            "url":        url,
            "snippet":    snippet[:400],
            "domain":     dom,
            "score":      score,
            "fetched_at": fetched_at,
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:max_results]


def _web_search_html_scrape(
    query: str,
    *,
    max_results: int = 5,
    finance_boost: bool = True,
    timeout: int = DDG_TIMEOUT,
) -> list[dict[str, Any]]:
    """Legacy DuckDuckGo HTML scrape — kept as fallback; prone to 202/bot blocks."""
    try:
        from bs4 import BeautifulSoup  # noqa: WPS433
    except ImportError:
        return []

    headers = {
        "User-Agent": USER_AGENT,
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    try:
        resp = requests.get(
            DDG_HTML,
            params={"q": query, "kl": "us-en"},
            headers=headers,
            timeout=timeout,
        )
        resp.raise_for_status()
    except Exception:
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    # Bail out if DDG served a bot-challenge page (no result divs, "bot" in body)
    if not soup.select("div.result"):
        return []

    results: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    fetched_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    for result_div in soup.select("div.result"):
        a_tag = result_div.select_one("a.result__a")
        if not a_tag:
            continue
        title = a_tag.get_text(strip=True)
        href  = _unwrap_ddg(a_tag.get("href", ""))
        if not href.startswith("http"):
            continue
        domain = _domain(href)
        if domain in SKIP_DOMAINS or href in seen_urls:
            continue
        seen_urls.add(href)

        snip_tag = result_div.select_one("a.result__snippet, .result__snippet")
        snippet = snip_tag.get_text(" ", strip=True) if snip_tag else ""
        snippet = re.sub(r"^\w+ \d+, \d{4} [–—-] ", "", snippet)

        score = 1.3 if (finance_boost and any(fd in domain for fd in FINANCE_DOMAINS)) else 1.0
        results.append({
            "title":      title,
            "url":        href,
            "snippet":    snippet[:400],
            "domain":     domain,
            "score":      score,
            "fetched_at": fetched_at,
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:max_results]


def web_search(
    query: str,
    *,
    max_results: int = 5,
    finance_boost: bool = True,
    timeout: int = DDG_TIMEOUT,
) -> list[dict[str, Any]]:
    """Search DuckDuckGo and return [{title, url, snippet, domain, score}].

    Primary: ddgs Python library (bot-detection-resistant, fixed 2026-08-27).
    Fallback: legacy HTML scrape (html.duckduckgo.com — may return 0 hits if
              IP is CAPTCHA-challenged).

    Parameters
    ----------
    query : str
        Search query string.
    max_results : int
        Maximum results to return (default 5).
    finance_boost : bool
        Boost known finance domains (moneycontrol, screener.in, etc.) by +0.3.
    timeout : int
        HTTP timeout in seconds.

    Returns
    -------
    list of dicts: title, url, snippet, domain, score, fetched_at
    """
    # Primary: ddgs library (avoids HTML scrape bot-block)
    hits = _web_search_ddgs(query, max_results=max_results,
                            finance_boost=finance_boost, timeout=timeout)
    if hits:
        return hits

    # Fallback: HTML scrape
    return _web_search_html_scrape(query, max_results=max_results,
                                   finance_boost=finance_boost, timeout=timeout)


def format_web_block(
    hits: list[dict[str, Any]],
    query: str,
    *,
    max_chars: int = 2000,
) -> str:
    """Format web search results as a markdown context block."""
    if not hits or (len(hits) == 1 and not hits[0].get("url")):
        return f"<!-- web: no results for '{query}' -->"

    lines: list[str] = [
        f"## 🌐 Web — latest results for: {query}",
        "",
    ]
    chars = 0
    for i, h in enumerate(hits, 1):
        title   = h.get("title", "")
        url     = h.get("url", "")
        snippet = h.get("snippet", "")
        domain  = h.get("domain", "")
        chunk = f"**{i}. {title}**  \n{snippet}  \n*[{domain}]({url})*\n"
        if chars + len(chunk) > max_chars and i > 2:
            lines.append(f"*… {len(hits) - i + 1} more results omitted*")
            break
        lines.append(chunk)
        chars += len(chunk)

    return "\n".join(lines)


def estimate_web_tokens(hits: list[dict]) -> int:
    """Rough token count for a web results block."""
    total = sum(
        len((h.get("title", "") + h.get("snippet", "") + h.get("url", "")).split()) * 2
        for h in hits
    )
    return total
