"""Discover broker research PDFs via DuckDuckGo HTML search and auto-ingest.

PG 2026-05-27: Best-effort discovery — no broker login, no Google API key.
Works well for publicly-indexed PDFs on icicidirect.com / groww.in /
moneycontrol.com / equitymaster.com. Paywalled or JS-only reports won't
surface; that's expected.

Usage:
    from knowledge_base.research import research_symbol
    r = research_symbol("TATASTEEL", brand="auto", max_results=3)
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import requests

from ._common import USER_AGENT, load_dotenv
from .ingest import ingest_pdf_url

load_dotenv()

# PG: brand → (source_id, site_filter, hint_keywords)
BRAND_PROFILES: dict[str, dict[str, str]] = {
    "icici": {
        "source_id": "ICICI_DIRECT",
        "source_name": "ICICI Direct Retail Research",
        "site": "icicidirect.com",
        "hint": "research equity report",
    },
    "groww": {
        "source_id": "GROWW",
        "source_name": "Groww Research",
        "site": "groww.in",
        "hint": "research analysis",
    },
    "moneycontrol": {
        "source_id": "MONEYCONTROL",
        "source_name": "Moneycontrol Research",
        "site": "moneycontrol.com",
        "hint": "broker report",
    },
    "equitymaster": {
        "source_id": "EQUITYMASTER",
        "source_name": "Equitymaster Research",
        "site": "equitymaster.com",
        "hint": "stock research",
    },
}

DDG_URL = "https://html.duckduckgo.com/html/"
REQUEST_TIMEOUT = 20


# ─────────────────────────────────────────────────────────────────────────────
# DuckDuckGo HTML search
# ─────────────────────────────────────────────────────────────────────────────

def _unwrap_ddg(url: str) -> str:
    """DDG wraps result URLs as /l/?uddg=<encoded>. Unwrap to the real target."""
    if "uddg=" not in url:
        return url
    try:
        qs = parse_qs(urlparse(url).query)
        return unquote(qs.get("uddg", [url])[0]) or url
    except Exception:
        return url


def _ddg_search(query: str, *, max_results: int = 5) -> list[str]:
    """Return a list of unique result URLs for `query` (best effort)."""
    try:
        from bs4 import BeautifulSoup
    except Exception:
        return []

    headers = {"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"}
    try:
        # PG: DDG html endpoint accepts POST too but GET is more cacheable
        r = requests.get(DDG_URL, params={"q": query},
                         headers=headers, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
    except Exception:
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    urls: list[str] = []
    seen: set[str] = set()

    # PG: result__a holds the title link; result__url shows the raw URL text.
    for a in soup.select("a.result__a, a.result__url"):
        href = a.get("href") or ""
        if not href:
            continue
        href = _unwrap_ddg(href)
        # Skip relative / DDG-internal links
        if not href.startswith("http"):
            continue
        if href in seen:
            continue
        seen.add(href)
        urls.append(href)
        if len(urls) >= max_results * 3:
            break
    return urls


def _looks_like_pdf(url: str) -> bool:
    return url.lower().split("?")[0].endswith(".pdf")


# ─────────────────────────────────────────────────────────────────────────────
# top-level discovery
# ─────────────────────────────────────────────────────────────────────────────

def search_research_reports(
    symbol: str,
    *,
    brand: str = "auto",
    max_results: int = 3,
) -> list[dict[str, str]]:
    """Return candidate PDF URLs for `symbol` from one or all brand profiles.

    Each result: {url, brand, source_id, source_name, query}.
    """
    sym = symbol.upper().strip()
    brand = (brand or "auto").lower()
    if brand == "auto":
        profiles = list(BRAND_PROFILES.values())
        profile_keys = list(BRAND_PROFILES.keys())
    elif brand in BRAND_PROFILES:
        profiles = [BRAND_PROFILES[brand]]
        profile_keys = [brand]
    else:
        return []

    out: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    for key, prof in zip(profile_keys, profiles):
        query = f"site:{prof['site']} {sym} {prof['hint']} filetype:pdf"
        urls = _ddg_search(query, max_results=max_results)
        kept = 0
        for u in urls:
            if not _looks_like_pdf(u):
                continue
            if u in seen_urls:
                continue
            seen_urls.add(u)
            out.append({
                "url": u,
                "brand": key,
                "source_id": prof["source_id"],
                "source_name": prof["source_name"],
                "query": query,
            })
            kept += 1
            if kept >= max_results:
                break
    return out


def _fetch_nse_annual_report(symbol: str, *, do_qa: bool = True) -> dict[str, Any]:
    """Auto-fetch the latest NSE annual report for symbol into the KB.

    Silently skips if already cached or NSE API is unavailable — never raises.
    Returns a summary dict compatible with research_symbol's ingested list.
    """
    try:
        import sys as _sys
        import importlib as _importlib
        # fetch_annual_reports lives in scripts/ — not on the package path
        _scripts_dir = str(Path(__file__).resolve().parent.parent / "scripts")
        if _scripts_dir not in _sys.path:
            _sys.path.insert(0, _scripts_dir)
        _mod = _importlib.import_module("fetch_annual_reports")
        entries = _mod.fetch_ar_listing(symbol)
        if not entries:
            return {}
        entry = entries[0]  # most recent year
        from_yr = entry.get("fromYr", "?")
        to_yr   = entry.get("toYr", "?")
        source_id = _mod._source_id(symbol, from_yr, to_yr)
        # Skip if already in KB
        raw_dir = Path(__file__).resolve().parent.parent / "data" / "knowledge_base" / "raw" / source_id
        if raw_dir.exists() and any(raw_dir.rglob("*.pdf")):
            return {"url": entry.get("fileName", ""), "brand": "nse_annual_report",
                    "chunks": "cached", "qa": 0, "note": "already_indexed"}
        result = _mod.ingest_annual_report(symbol, entry, dry_run=False, force=False)
        if result.get("status") == "ok":
            return {"url": entry.get("fileName", ""), "brand": "nse_annual_report",
                    "chunks": result.get("chunks"), "qa": result.get("qa", 0)}
        return {}
    except Exception:
        return {}  # best-effort, never block the main flow


def research_symbol(
    symbol: str,
    *,
    brand: str = "auto",
    max_results: int = 3,
    do_qa: bool = True,
    dry_run: bool = False,
    include_annual_report: bool = True,
) -> dict[str, Any]:
    """Search → download → ingest. Returns a summary of what landed in the KB.

    `dry_run=True` skips ingestion, only returns the candidate URLs.
    `include_annual_report=True` (default) also auto-fetches the latest NSE
    annual report so critique_report() has first-party source data.
    """
    sym = symbol.upper().strip()
    candidates = search_research_reports(sym, brand=brand, max_results=max_results)

    summary: dict[str, Any] = {
        "ok": True,
        "symbol": sym,
        "brand": brand,
        "candidates": candidates,
        "ingested": [],
        "errors": [],
    }

    # Step 0: auto-fetch NSE annual report as first-party KB grounding
    if include_annual_report and not dry_run:
        ar = _fetch_nse_annual_report(sym, do_qa=do_qa)
        if ar:
            summary["ingested"].append(ar)

    if dry_run or not candidates:
        if not candidates:
            summary["ok"] = False
            summary["error"] = (
                f"no public PDF reports found for {sym} via DuckDuckGo "
                f"(brand={brand}). Try a different brand, or `/kb ingest <url>` "
                "directly if you have a link."
            )
        return summary

    for cand in candidates:
        try:
            r = ingest_pdf_url(
                cand["url"],
                source_id=cand["source_id"],
                source_name=cand["source_name"],
                category="broker_research",
                tier=3,
                hub_label=cand["brand"],
                do_qa=do_qa,
            )
            if r.get("ok"):
                summary["ingested"].append({
                    "url": cand["url"],
                    "brand": cand["brand"],
                    "chunks": r.get("chunks"),
                    "qa": r.get("qa"),
                    "path": r.get("path"),
                })
            else:
                summary["errors"].append({
                    "url": cand["url"], "brand": cand["brand"],
                    "error": r.get("error"),
                })
        except Exception as exc:
            summary["errors"].append({
                "url": cand["url"], "brand": cand["brand"],
                "error": str(exc),
            })

    summary["ok"] = bool(summary["ingested"])
    return summary


__all__ = ["search_research_reports", "research_symbol", "BRAND_PROFILES"]
