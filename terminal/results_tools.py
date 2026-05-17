"""Composite latest-results evidence tools.

The functions here provide a single deterministic evidence pack for
"latest results" prompts. They reuse existing discovery/parsing helpers and
never fabricate financial facts when a filing cannot be parsed.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from financial_filing_agent import ingest_filing_url, parse_pdf_filing as _parse_pdf_filing, parse_registered_filing
from terminal.search_engine import search_bse_filings, search_nse_announcements
from terminal.web_research import scrape_screener_in


def _status_from(result: Any) -> str:
    if not isinstance(result, dict):
        return "error"
    if result.get("error"):
        return f"ERROR: {result.get('error')}"
    return str(result.get("status") or "ok")


def _candidate_score(title: str, source: str) -> int:
    text = title.lower()
    score = 0
    if "financial result" in text or "financial results" in text:
        score += 100
    if "audited" in text or "unaudited" in text:
        score += 30
    if "quarter" in text or re.search(r"\bq[1-4]\b", text):
        score += 20
    if "result" in text:
        score += 15
    if source == "nse_announcements":
        score += 5
    return score


def _rows_to_candidates(rows: list[dict], source: str) -> list[dict]:
    candidates: list[dict] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
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
                "raw": row,
            }
        )
    return candidates


def discover_financial_filings(symbol: str, max_results: int = 10) -> dict:
    """Discover likely financial-result filings from NSE, BSE, and Screener."""
    sym = str(symbol or "").strip().upper()
    source_trail: dict[str, str] = {}
    candidates: list[dict] = []
    screener_data: dict[str, Any] = {}

    try:
        nse = search_nse_announcements(sym, max_results=15)
        source_trail["search_nse_announcements"] = _status_from(nse)
        candidates.extend(_rows_to_candidates(nse.get("results") or [], "nse_announcements"))
    except Exception as exc:
        source_trail["search_nse_announcements"] = f"ERROR: {exc}"

    try:
        bse = search_bse_filings(sym, max_results=10)
        source_trail["search_bse_filings"] = _status_from(bse)
        candidates.extend(_rows_to_candidates(bse.get("results") or [], "bse_filings"))
    except Exception as exc:
        source_trail["search_bse_filings"] = f"ERROR: {exc}"

    try:
        screener_data = scrape_screener_in(sym)
        source_trail["scrape_screener_in"] = _status_from(screener_data)
        candidates.extend(_rows_to_candidates(screener_data.get("announcements") or [], "screener_in"))
    except Exception as exc:
        source_trail["scrape_screener_in"] = f"ERROR: {exc}"

    candidates.sort(key=lambda item: (item.get("score", 0), item.get("title", "")), reverse=True)
    for idx, candidate in enumerate(candidates, start=1):
        candidate["rank"] = idx
    return {
        "status": "ok" if candidates or screener_data else "no_candidates",
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
    period = headers[0] if headers else "latest"
    for label in labels:
        values = quarterly.get(label)
        if isinstance(values, list) and values and str(values[0]).strip():
            return str(values[0]).strip(), period
    return None


def reconcile_filing_facts(parsed_filing: dict | None = None, screener_data: dict | None = None) -> dict:
    """Reconcile parsed filing evidence with Screener tabular data without invention."""
    parsed_filing = parsed_filing or {}
    screener_data = screener_data or {}
    facts: dict[str, dict[str, str]] = {}

    revenue = _first_quarter_value(screener_data, ("Sales", "Revenue", "Revenue from Operations"))
    if revenue:
        facts["revenue"] = {"value": revenue[0], "period": revenue[1], "source": "scrape_screener_in.quarterly"}

    pat = _first_quarter_value(screener_data, ("Net Profit", "PAT", "Profit after tax"))
    if pat:
        facts["pat"] = {"value": pat[0], "period": pat[1], "source": "scrape_screener_in.quarterly"}

    ratios = screener_data.get("ratios") if isinstance(screener_data, dict) else {}
    if isinstance(ratios, dict):
        eps = ratios.get("EPS") or ratios.get("EPS latest quarter") or ratios.get("EPS (TTM)")
        if eps:
            facts["eps"] = {"value": str(eps), "period": "latest", "source": "scrape_screener_in.ratios"}

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
    source_trail: dict[str, str] = {}
    discovery = discover_financial_filings(sym)
    source_trail["discover_financial_filings"] = _status_from(discovery)
    source_trail.update(discovery.get("source_trail") or {})

    candidate = (discovery.get("candidates") or [None])[0]
    ingestion: dict[str, Any] = {}
    parsed: dict[str, Any] = {}
    if ingest and candidate and candidate.get("url"):
        ingestion = ingest_financial_filing(candidate["url"], symbol=sym, period=period)
        source_trail["ingest_financial_filing"] = _status_from(ingestion)
        manifest_path = ingestion.get("manifest_path")
        if ingestion.get("status") == "ok" and manifest_path:
            parsed = parse_financial_filing(str(manifest_path))
            source_trail["parse_financial_filing"] = _status_from(parsed)
        else:
            source_trail["parse_financial_filing"] = "skipped"
    else:
        source_trail["ingest_financial_filing"] = "skipped"
        source_trail["parse_financial_filing"] = "skipped"

    reconciliation = reconcile_filing_facts(parsed, discovery.get("screener_data") or {})
    source_trail["reconcile_filing_facts"] = _status_from(reconciliation)
    summary = summarize_latest_results(
        {
            "symbol": sym,
            "period": period,
            "facts": reconciliation.get("facts") or {},
            "missing_facts": reconciliation.get("missing_facts") or [],
            "status": reconciliation.get("status"),
            "source_trail": source_trail,
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
        "source_trail": source_trail,
        "summary": summary.get("summary", ""),
    }


def summarize_latest_results(results_pack: dict) -> dict:
    """Summarize a latest-results evidence pack without filling missing numbers."""
    symbol = str(results_pack.get("symbol") or "").upper()
    period = str(results_pack.get("period") or "latest")
    facts = results_pack.get("facts") or {}
    missing = results_pack.get("missing_facts") or []
    lines = [f"Latest results evidence for {symbol or 'symbol'} ({period})."]
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
