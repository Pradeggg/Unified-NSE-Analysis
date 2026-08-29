"""Composite latest-results evidence tools.

The functions here provide a single deterministic evidence pack for
"latest results" prompts. They reuse existing discovery/parsing helpers and
never fabricate financial facts when a filing cannot be parsed.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from financial_filing_agent import ingest_filing_url, parse_pdf_filing as _parse_pdf_filing, parse_registered_filing
from terminal.search_engine import search_bse_filings, search_nse_announcements
from terminal.web_research import scrape_screener_in
from terminal.financials_cache import (
    screener_payload_from_cache,
    upsert_screener_payload,
)


def _financials_cache_ttl_hours() -> float:
    import os
    try:
        return float(os.environ.get("AGENT_ADDA_FINANCIALS_CACHE_TTL_H", "24"))
    except (TypeError, ValueError):
        return 24.0


def _status_from(result: Any) -> str:
    if not isinstance(result, dict):
        return "error"
    if result.get("error"):
        return f"ERROR: {result.get('error')}"
    return str(result.get("status") or "ok")


def _invalid_symbol_error(symbol: str) -> dict[str, Any] | None:
    sym = str(symbol or "").strip().upper()
    normalized = re.sub(r"[^A-Z0-9]+", "_", sym).strip("_")
    if (
        not sym
        or "<" in sym
        or ">" in sym
        or normalized in {"SYMBOL", "NSE_SYMBOL", "RESOLVED_SYMBOL", "RESOLVED_NSE_SYMBOL", "TICKER"}
    ):
        return {
            "status": "error",
            "symbol": sym,
            "error": (
                "Invalid unresolved symbol placeholder. Resolve the company "
                "name to a concrete NSE ticker before fetching latest results."
            ),
            "candidates": [],
            "selected_filing": None,
            "facts": {},
            "missing_facts": ["revenue", "pat", "eps"],
            "source_trail": {"symbol_validation": "ERROR: unresolved placeholder"},
            "summary": "Latest results unavailable because the symbol was not resolved.",
        }
    return None


def _candidate_score(title: str, source: str) -> int:
    text = title.lower()
    if any(
        term in text
        for term in (
            "analyst / investor meet",
            "investor meet",
            "audio recording",
            "conference call",
            "transcript",
            "newspaper publication",
            "loss of share certificate",
            "issue of duplicate certificate",
            "postal ballot",
            "e-voting",
            "voting results",
            "scrutinizer report",
        )
    ):
        return -1000
    score = 0
    if any(term in text for term in ("change in management", "change in directorate", "press release", "media release", "board comments", "fine levied")):
        score -= 40
    if "board meeting" in text and "financial result" not in text and "financial results" not in text:
        score -= 20
    if "financial result" in text or "financial results" in text:
        score += 100
    if "audited" in text or "unaudited" in text:
        score += 30
    if "quarter" in text or re.search(r"\bq[1-4]\b", text):
        score += 20
    if any(term in text for term in ("award of order", "receipt of order", "award_of_order", "receipt_of_order", "contract")):
        score += 70
    if "letter of award" in text or "l1 bidder" in text or re.search(r"\bloa\b", text):
        score += 30
    if re.search(r"\bratings?\b", text) or any(term in text for term in ("crisil", "icra", "india ratings")):
        score += 55
    if any(term in text for term in ("dividend", "buyback", "stock split", "bonus issue", "rights issue", "qip", "preferential issue")):
        score += 35
    if "regulation 39" in text or "reg 39" in text:
        score -= 40
    if score > 0:
        if source == "nse_announcements":
            score += 5
        if source == "bse_filings":
            score += 3
    return score


def _url_dedupe_key(url: str) -> str:
    value = str(url or "").strip()
    try:
        parts = urlsplit(value)
    except ValueError:
        return value
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, parts.query, ""))


def _flatten_rows(rows: Any) -> list[dict]:
    if isinstance(rows, dict):
        output: list[dict] = []
        for category, items in rows.items():
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict):
                        output.append({**item, "_category": category})
        return output
    if isinstance(rows, list):
        return [row for row in rows if isinstance(row, dict)]
    return []


def _rows_to_candidates(rows: Any, source: str) -> list[dict]:
    candidates: list[dict] = []
    for row in _flatten_rows(rows):
        title = str(row.get("title") or row.get("subject") or row.get("description") or "").strip()
        url = str(row.get("url") or row.get("link") or row.get("attachment") or row.get("pdf_url") or "").strip()
        if not title and not url:
            continue
        candidates.append(
            {
                "source": source,
                "title": title or url,
                "url": url,
                "score": _candidate_score(title or url, source),
                "category": row.get("_category"),
                "raw": row,
            }
        )
    return candidates


def _candidate_date_key(candidate: dict) -> str:
    raw = candidate.get("raw") or {}
    value = str(raw.get("date") or raw.get("published") or raw.get("an_dt") or "").strip()
    if not value:
        return ""
    for fmt in ("%Y-%m-%d", "%d-%b-%Y", "%d %b %Y", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(value[:11].strip(), fmt).date().isoformat()
        except ValueError:
            continue
    match = re.search(r"\b(20\d{2})[-/](\d{1,2})[-/](\d{1,2})\b", value)
    if match:
        year, month, day = (int(part) for part in match.groups())
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            return ""
    return ""


def _resolve_screener_data(sym: str) -> tuple[dict, str]:
    """PG-first → live screener scrape → cache fallback.

    Order:
      1. If fresh structured rows exist in PG (within
         ``AGENT_ADDA_FINANCIALS_CACHE_TTL_H`` hours, default 24), return a
         reconstructed payload and skip the live scrape.
      2. Otherwise call ``scrape_screener_in``; on success, write the
         structured rows back to PG.
      3. If the live scrape errors out or returns empty, fall back to any
         cached rows regardless of age (stale > nothing).

    Returns ``(screener_data, status_string)``. ``status_string`` is what
    gets recorded into ``source_trail`` and looks like:
      ``pg_cache_hit:<age>h``, ``ok+writeback``, ``ok (writeback_err)``,
      ``pg_cache_fallback:<age>h``, or ``ERROR: ...``.
    """
    ttl = _financials_cache_ttl_hours()
    if ttl > 0:
        cached = screener_payload_from_cache(sym, max_age_hours=ttl)
        if cached is not None:
            age = cached.get("_cache_age_hours")
            return cached, f"pg_cache_hit:{age}h"

    try:
        live = scrape_screener_in(sym)
    except Exception as exc:
        stale = screener_payload_from_cache(sym, max_age_hours=None)
        if stale is not None:
            age = stale.get("_cache_age_hours")
            return stale, f"pg_cache_fallback:{age}h (scrape ERROR: {exc})"
        raise

    if not live or live.get("error") or not any(
        isinstance(live.get(k), dict) and live.get(k)
        for k in ("quarterly", "annual_pl", "balance_sheet", "cash_flow")
    ):
        stale = screener_payload_from_cache(sym, max_age_hours=None)
        if stale is not None:
            age = stale.get("_cache_age_hours")
            err = (live or {}).get("error") or "empty payload"
            return stale, f"pg_cache_fallback:{age}h (scrape {err})"
        return live or {}, _status_from(live)

    writeback_status = "writeback"
    try:
        upsert_screener_payload(sym, live)
    except Exception as exc:
        writeback_status = f"writeback_err:{exc}"
    return live, f"{_status_from(live)} ({writeback_status})"


def discover_financial_filings(symbol: str, max_results: int = 10) -> dict:
    """Discover likely financial-result filings from NSE, BSE, and Screener."""
    sym = str(symbol or "").strip().upper()
    invalid = _invalid_symbol_error(sym)
    if invalid:
        return invalid
    source_trail: dict[str, str] = {}
    candidates: list[dict] = []
    screener_data: dict[str, Any] = {}

    try:
        nse = search_nse_announcements(sym, max_results=max(15, int(max_results) * 6))
        source_trail["search_nse_announcements"] = _status_from(nse)
        candidates.extend(_rows_to_candidates(nse.get("results") or [], "nse_announcements"))
        candidates.extend(_rows_to_candidates(nse.get("nse_filings") or [], "nse_announcements"))
        candidates.extend(_rows_to_candidates(nse.get("bse_filings") or [], "screener_in"))
    except Exception as exc:
        source_trail["search_nse_announcements"] = f"ERROR: {exc}"

    try:
        bse = search_bse_filings(sym, max_results=max(10, int(max_results) * 3))
        source_trail["search_bse_filings"] = _status_from(bse)
        candidates.extend(_rows_to_candidates(bse.get("results") or [], "bse_filings"))
    except Exception as exc:
        source_trail["search_bse_filings"] = f"ERROR: {exc}"

    try:
        screener_data, screener_status = _resolve_screener_data(sym)
        source_trail["scrape_screener_in"] = screener_status
        candidates.extend(_rows_to_candidates(screener_data.get("announcements") or [], "screener_in"))
    except Exception as exc:
        source_trail["scrape_screener_in"] = f"ERROR: {exc}"

    candidates = [candidate for candidate in candidates if candidate.get("score", 0) > 0 and candidate.get("url")]
    candidates.sort(
        key=lambda item: (item.get("score", 0), _candidate_date_key(item), item.get("title", "")),
        reverse=True,
    )
    unique_candidates: list[dict] = []
    seen_urls: set[str] = set()
    for candidate in candidates:
        url_key = _url_dedupe_key(str(candidate.get("url") or ""))
        if not url_key or url_key in seen_urls:
            continue
        seen_urls.add(url_key)
        unique_candidates.append(candidate)
    candidates = unique_candidates
    for idx, candidate in enumerate(candidates, start=1):
        candidate["rank"] = idx
    return {
        "status": "ok" if candidates else "no_candidates",
        "symbol": sym,
        "candidates": candidates[:max_results],
        "source_trail": source_trail,
        "screener_data": screener_data,
    }


def ingest_financial_filing(
    url: str,
    symbol: str = "",
    period: str = "latest",
    root_dir: str | Path | None = None,
    force: bool = False,
) -> dict:
    """Download/register a filing URL using the existing filing agent."""
    return ingest_filing_url(
        url,
        symbol=symbol or None,
        period=period or "latest",
        root_dir=root_dir or Path("data") / "filings",
        force=force,
    )


def parse_pdf_filing(path: str) -> dict:
    """Parse a local PDF filing with the existing deterministic parser."""
    return _parse_pdf_filing(Path(path))


def parse_xbrl_filing(path: str) -> dict:
    """Placeholder XBRL parser contract until an XBRL fact parser is wired."""
    return {
        "status": "unsupported",
        "document_type": "xbrl",
        "source_path": path,
        "facts": {},
        "message": "XBRL parsing is not wired yet.",
    }


def parse_financial_filing(manifest_path: str) -> dict:
    """Parse a registered filing manifest."""
    return parse_registered_filing(Path(manifest_path))


def _quarter_headers(screener_data: dict) -> list[str]:
    quarterly = screener_data.get("quarterly") if isinstance(screener_data, dict) else {}
    headers = quarterly.get("_headers") if isinstance(quarterly, dict) else []
    return [str(h) for h in headers] if isinstance(headers, list) else []


def _first_quarter_value(screener_data: dict, labels: tuple[str, ...]) -> tuple[str, str] | None:
    quarterly = screener_data.get("quarterly") if isinstance(screener_data, dict) else {}
    if not isinstance(quarterly, dict):
        return None
    headers = _quarter_headers(screener_data)
    for label in labels:
        values = quarterly.get(label)
        if isinstance(values, list):
            for idx in range(len(values) - 1, -1, -1):
                value = str(values[idx]).strip()
                if value:
                    period = headers[idx] if idx < len(headers) else "latest"
                    return value, period
    return None


def _period_to_quarter_date(period: str) -> date | None:
    match = re.search(r"\b([A-Za-z]{3})\s+(\d{4})\b", period or "")
    if not match:
        return None
    month_map = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    }
    month = month_map.get(match.group(1).lower())
    if not month:
        return None
    return date(int(match.group(2)), month, 1)


def _months_between(start: date, end: date) -> int:
    return (end.year - start.year) * 12 + (end.month - start.month)


def _results_warning(candidate: dict | None, reconciliation: dict, as_of: date | None = None) -> dict[str, Any] | None:
    facts = reconciliation.get("facts") or {}
    periods = [
        str(item.get("period") or "")
        for item in facts.values()
        if isinstance(item, dict) and item.get("source") == "scrape_screener_in.quarterly"
    ]
    if not periods:
        return None
    period = periods[0]
    period_date = _period_to_quarter_date(period)
    age_months = _months_between(period_date, as_of or date.today()) if period_date else None
    no_filing = not candidate
    stale = age_months is not None and age_months > 6
    if not no_filing and not stale:
        return None
    if no_filing and stale:
        message = f"Latest filing not found; using Screener quarterly data from {period}, which may be stale."
    elif no_filing:
        message = f"Latest filing not found; using Screener quarterly data from {period}."
    else:
        message = f"Reconciled Screener quarterly data is from {period}, which may be stale."
    return {
        "severity": "warning",
        "period": period,
        "age_months": age_months,
        "latest_filing_found": bool(candidate),
        "message": message,
    }


def reconcile_filing_facts(parsed_filing: dict | None = None, screener_data: dict | None = None) -> dict:
    """Reconcile parsed filing evidence with Screener tabular data without invention."""
    parsed_filing = parsed_filing or {}
    screener_data = screener_data or {}
    facts: dict[str, dict[str, str]] = {}

    revenue = _first_quarter_value(screener_data, ("Sales", "Sales+", "Revenue", "Revenue+", "Revenue from Operations"))
    if revenue:
        facts["revenue"] = {"value": revenue[0], "period": revenue[1], "source": "scrape_screener_in.quarterly"}

    pat = _first_quarter_value(screener_data, ("Net Profit", "Net Profit+", "PAT", "Profit after tax"))
    if pat:
        facts["pat"] = {"value": pat[0], "period": pat[1], "source": "scrape_screener_in.quarterly"}

    ratios = screener_data.get("ratios") if isinstance(screener_data, dict) else {}
    if isinstance(ratios, dict):
        eps = ratios.get("EPS") or ratios.get("EPS latest quarter") or ratios.get("EPS (TTM)")
        if eps:
            facts["eps"] = {"value": str(eps), "period": "latest", "source": "scrape_screener_in.ratios"}
    if "eps" not in facts:
        eps_q = _first_quarter_value(screener_data, ("EPS in Rs", "EPS", "EPS in Rs."))
        if eps_q:
            facts["eps"] = {"value": eps_q[0], "period": eps_q[1], "source": "scrape_screener_in.quarterly"}

    missing = [name for name in ("revenue", "pat", "eps") if name not in facts]
    status = "ok" if not missing else "partial"
    return {
        "status": status,
        "facts": facts,
        "missing_facts": missing,
        "parsed_status": parsed_filing.get("status"),
        "parsed_evidence_count": len(parsed_filing.get("evidence") or []),
    }


def get_latest_results(symbol: str, period: str = "latest", ingest: bool = True) -> dict:
    """Build the latest-results evidence pack for one symbol."""
    sym = str(symbol or "").strip().upper()
    invalid = _invalid_symbol_error(sym)
    if invalid:
        invalid["period"] = period
        return invalid
    source_trail: dict[str, str] = {}
    discovery = discover_financial_filings(sym)
    source_trail["discover_financial_filings"] = _status_from(discovery)
    source_trail.update(discovery.get("source_trail") or {})

    candidates = discovery.get("candidates") or []
    candidate: dict[str, Any] | None = candidates[0] if candidates else None
    ingestion: dict[str, Any] = {}
    parsed: dict[str, Any] = {}
    if ingest and candidates:
        # Walk the discovery candidates and stop at the first one that yields a
        # successfully-parsed PDF (annual report / quarterly results PDF). The
        # top-ranked candidate is often a BSE quote/board-meetings HTML page
        # which the parser cannot consume; falling back to the next PDF
        # candidate is what an analyst would do manually.
        attempted = 0
        for cand in candidates:
            url = (cand or {}).get("url")
            if not url:
                continue
            attempted += 1
            ingestion = ingest_financial_filing(url, symbol=sym, period=period)
            manifest_path = ingestion.get("manifest_path")
            if ingestion.get("status") == "ok" and manifest_path:
                parsed = parse_financial_filing(str(manifest_path))
                if parsed.get("status") == "ok":
                    candidate = cand
                    break
            if attempted >= 5:
                break
        source_trail["ingest_financial_filing"] = _status_from(ingestion)
        source_trail["parse_financial_filing"] = _status_from(parsed) if parsed else "skipped"
    else:
        source_trail["ingest_financial_filing"] = "skipped"
        source_trail["parse_financial_filing"] = "skipped"

    reconciliation = reconcile_filing_facts(parsed, discovery.get("screener_data") or {})
    warning = _results_warning(candidate, reconciliation)
    source_trail["reconcile_filing_facts"] = _status_from(reconciliation)
    summary = summarize_latest_results(
        {
            "symbol": sym,
            "period": period,
            "facts": reconciliation.get("facts") or {},
            "missing_facts": reconciliation.get("missing_facts") or [],
            "status": reconciliation.get("status"),
            "source_trail": source_trail,
            "warning": warning,
        }
    )
    return {
        "status": reconciliation.get("status") or discovery.get("status"),
        "symbol": sym,
        "period": period,
        "candidates": discovery.get("candidates") or [],
        "selected_filing": candidate,
        "ingestion": ingestion,
        "parsed_filing": parsed,
        "facts": reconciliation.get("facts") or {},
        "missing_facts": reconciliation.get("missing_facts") or [],
        "warning": warning,
        "source_trail": source_trail,
        "summary": summary.get("summary", ""),
    }


def summarize_latest_results(results_pack: dict) -> dict:
    """Summarize a latest-results evidence pack without filling missing numbers."""
    symbol = str(results_pack.get("symbol") or "").upper()
    period = str(results_pack.get("period") or "latest")
    facts = results_pack.get("facts") or {}
    missing = results_pack.get("missing_facts") or []
    warning = results_pack.get("warning") or {}
    lines = [f"Latest results evidence for {symbol or 'symbol'} ({period})."]
    if warning.get("message"):
        lines.append(f"Warning: {warning.get('message')}")
    if "revenue" in facts:
        item = facts["revenue"]
        lines.append(f"Revenue: {item.get('value')} ({item.get('period')}; {item.get('source')})")
    if "pat" in facts:
        item = facts["pat"]
        lines.append(f"PAT: {item.get('value')} ({item.get('period')}; {item.get('source')})")
    if "eps" in facts:
        item = facts["eps"]
        lines.append(f"EPS: {item.get('value')} ({item.get('period')}; {item.get('source')})")
    if missing:
        lines.append(f"Missing facts: {', '.join(missing)}.")
    return {
        "status": results_pack.get("status") or ("ok" if facts else "partial"),
        "symbol": symbol,
        "period": period,
        "summary": "\n".join(lines),
        "source_trail": results_pack.get("source_trail") or {},
    }
