from __future__ import annotations

import io
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from terminal.governance.models import GovernanceMissingEvidence, GovernanceRawSources, GovernanceSource
from terminal.governance.nse_client import NSEJsonClient


Fetcher = Callable[..., dict[str, Any]]
PdfFetcher = Callable[[str], bytes]


def refresh_live_sources(
    symbol: str,
    *,
    data_dir: str | Path = "data",
    nse_client: Any = None,
    announcements_fetcher: Fetcher | None = None,
    corporate_actions_fetcher: Fetcher | None = None,
    screener_fetcher: Callable[[str], dict[str, Any]] | None = None,
    pdf_fetcher: PdfFetcher | None = None,
) -> GovernanceRawSources:
    target = _normalized_symbol(symbol)
    nse_client = nse_client or NSEJsonClient()
    announcements_fetcher = announcements_fetcher or _default_announcements_fetcher
    corporate_actions_fetcher = corporate_actions_fetcher or _default_corporate_actions_fetcher
    screener_fetcher = screener_fetcher or _default_screener_fetcher
    pdf_fetcher = pdf_fetcher or _download_pdf_bytes

    root = Path(data_dir) / "governance" / target
    raw_dir = root / "raw"
    parsed_dir = root / "parsed"
    raw_dir.mkdir(parents=True, exist_ok=True)
    parsed_dir.mkdir(parents=True, exist_ok=True)

    source_trail: list[GovernanceSource] = []
    missing_evidence: list[GovernanceMissingEvidence] = []

    pit_payload = _fetch_pit(target, nse_client, source_trail, missing_evidence)
    _write_json(raw_dir / "nse_pit.json", pit_payload)

    announcements_payload = _call_fetcher(announcements_fetcher, target, max_results=8)
    _write_json(raw_dir / "announcements.json", announcements_payload)
    announcement_rows = _announcement_rows(target, announcements_payload)
    _record_fetcher_source(
        source_trail,
        missing_evidence,
        name="live.announcements",
        field="corporate_events",
        payload=announcements_payload,
        rows=len(announcement_rows),
        fallback=True,
    )

    actions_payload = _call_fetcher(corporate_actions_fetcher, target, max_results=8)
    _write_json(raw_dir / "corporate_actions.json", actions_payload)
    action_rows = _corporate_action_rows(target, actions_payload)
    _record_fetcher_source(
        source_trail,
        missing_evidence,
        name="live.corporate_actions",
        field="corporate_actions",
        payload=actions_payload,
        rows=len(action_rows),
        fallback=False,
    )

    screener_payload = _call_symbol_fetcher(screener_fetcher, target)
    _write_json(raw_dir / "screener.json", screener_payload)
    screener_ok = not _payload_error(screener_payload)
    shareholding_rows = _shareholding_rows(screener_payload if screener_ok else {})
    _record_fetcher_source(
        source_trail,
        missing_evidence,
        name="live.screener.company",
        field="screener_payload",
        payload=screener_payload,
        rows=1 if screener_ok else 0,
        fallback=True,
    )
    if not shareholding_rows:
        missing_evidence.append(_missing(target, "shareholding", "Screener shareholding trend unavailable"))

    annual_text = ""
    if screener_ok:
        annual_text = _fetch_annual_report_text(
            target,
            screener_payload,
            pdf_fetcher,
            raw_dir,
            source_trail,
            missing_evidence,
        )
    else:
        source_trail.append(
            GovernanceSource(
                name="live.annual_report",
                status="missing",
                rows=0,
                fallback=True,
                error="Screener payload unavailable",
            )
        )
        missing_evidence.append(_missing(target, "annual_report_text", "Screener annual-report links unavailable"))

    raw_sources = GovernanceRawSources(
        symbol=target,
        shareholding_payloads=[{"data": shareholding_rows}],
        insider_payloads=[pit_payload],
        announcement_rows=[*announcement_rows, *action_rows],
        screener_payload=screener_payload if screener_ok else None,
        annual_report_text=annual_text or None,
        source_trail=source_trail,
        missing_evidence=missing_evidence,
    )
    _write_json(parsed_dir / "raw_sources.json", raw_sources.to_dict())
    _write_json(
        root / "manifest.json",
        {
            "symbol": target,
            "refreshed_at": datetime.now(timezone.utc).isoformat(),
            "source_count": len(source_trail),
            "sources": [source.to_dict() for source in source_trail],
        },
    )
    return raw_sources


def extract_annual_report_text_from_pdf_bytes(
    pdf_bytes: bytes,
    *,
    pages_after_heading: int = 20,
) -> tuple[str, dict[str, Any]]:
    if not pdf_bytes:
        return "", {"error": "empty pdf bytes"}

    try:
        import fitz
    except Exception as exc:
        return "", {"error": f"PyMuPDF unavailable: {exc}"}

    try:
        doc = fitz.open(stream=io.BytesIO(pdf_bytes), filetype="pdf")
    except Exception as exc:
        return "", {"error": f"PDF open failed: {exc}"}

    try:
        heading = re.compile(r"independent\s+auditor\S*\s+report", re.IGNORECASE)
        selected_pages: set[int] = set()
        auditor_start_page = None
        for page_idx in range(len(doc)):
            page_text = doc[page_idx].get_text("text")
            if _annual_report_toc_page(page_text):
                continue
            if auditor_start_page is None and heading.search(page_text):
                auditor_start_page = page_idx
                selected_pages.update(range(page_idx, min(len(doc), page_idx + max(1, pages_after_heading))))
            if _annual_report_review_page(page_text):
                selected_pages.add(page_idx)
        if not selected_pages:
            return "", {"error": "auditor/governance review sections not found", "total_pages": len(doc)}

        parts = []
        for page_idx in sorted(selected_pages):
            text = doc[page_idx].get_text("text").strip()
            if text:
                parts.append(f"--- Page {page_idx + 1} ---\n{text}")
        if not parts:
            return "", {"error": "annual report text extraction failed", "total_pages": len(doc)}
        first_page = min(selected_pages) + 1
        last_page = max(selected_pages) + 1
        return "\n\n".join(parts), {
            "start_page": first_page,
            "pages": [first_page, last_page],
            "selected_pages": [page_idx + 1 for page_idx in sorted(selected_pages)],
            "total_pages": len(doc),
        }
    finally:
        doc.close()


def _annual_report_review_page(text: str) -> bool:
    lowered = str(text or "").lower()
    keywords = (
        "independent auditor",
        "auditors' report",
        "auditor's report",
        "basis for opinion",
        "qualified opinion",
        "adverse opinion",
        "disclaimer of opinion",
        "key audit matter",
        "companies (auditor's report) order",
        "caro",
        "internal financial control",
        "related party",
        "contingent liabil",
        "litigation",
        "corporate governance",
        "whistle",
        "vigil mechanism",
        "subsidiar",
    )
    return any(keyword in lowered for keyword in keywords)


def _annual_report_toc_page(text: str) -> bool:
    lowered = str(text or "").lower()
    if "contents" not in lowered and "page no" not in lowered and "particulars" not in lowered:
        return False
    dotted_rows = len(re.findall(r"\.{4,}\s*\d{1,4}", lowered))
    section_mentions = sum(
        1
        for keyword in (
            "corporate governance",
            "independent auditor",
            "related party",
            "financial statement",
            "board's report",
        )
        if keyword in lowered
    )
    return dotted_rows >= 2 or section_mentions >= 3


def _fetch_pit(
    symbol: str,
    nse_client: Any,
    source_trail: list[GovernanceSource],
    missing_evidence: list[GovernanceMissingEvidence],
) -> dict[str, Any]:
    result = nse_client.get_json(
        "/api/corporates-pit",
        params={
            "symbol": symbol,
            "issuer": "",
            "fromDate": "",
            "toDate": "",
            "acquisitionMode": "",
            "before": "",
            "after": "",
            "modeVal": "",
            "modeCategory": "",
        },
        retries=1,
    )
    if result.get("status") != "ok":
        source_trail.append(
            GovernanceSource(
                name="live.nse.pit",
                status="error",
                rows=0,
                fallback=False,
                error=str(result.get("error") or "NSE PIT fetch failed"),
                metadata={"status_code": result.get("status_code"), "url": result.get("url")},
            )
        )
        missing_evidence.append(_missing(symbol, "insider_disclosures", "NSE PIT fetch failed"))
        return {"data": []}

    payload = result.get("json") if isinstance(result.get("json"), dict) else {"data": []}
    rows = _payload_rows(payload)
    source_trail.append(
        GovernanceSource(
            name="live.nse.pit",
            status="ok",
            rows=len(rows),
            fallback=False,
            metadata={"status_code": result.get("status_code"), "url": result.get("url")},
        )
    )
    return payload


def _fetch_annual_report_text(
    symbol: str,
    screener_payload: dict[str, Any],
    pdf_fetcher: PdfFetcher,
    raw_dir: Path,
    source_trail: list[GovernanceSource],
    missing_evidence: list[GovernanceMissingEvidence],
) -> str:
    reports = screener_payload.get("annual_reports") if isinstance(screener_payload, dict) else []
    reports = reports if isinstance(reports, list) else []
    selected = _select_annual_report(reports)
    url = selected["url"]
    if not url:
        source_trail.append(GovernanceSource("live.annual_report", "missing", rows=0, fallback=True))
        missing_evidence.append(_missing(symbol, "annual_report_text", "No annual-report URL found"))
        return ""

    try:
        pdf_bytes = pdf_fetcher(url)
        text, metadata = extract_annual_report_text_from_pdf_bytes(pdf_bytes)
    except Exception as exc:
        source_trail.append(
            GovernanceSource("live.annual_report", "error", rows=0, fallback=True, error=str(exc), metadata={"url": url})
        )
        missing_evidence.append(_missing(symbol, "annual_report_text", str(exc)))
        return ""

    if not text:
        source_trail.append(
            GovernanceSource(
                "live.annual_report",
                "error",
                rows=0,
                fallback=True,
                error=str(metadata.get("error") or "Annual report text extraction failed"),
                metadata={"url": url, "selected_label": selected["label"], **metadata},
            )
        )
        missing_evidence.append(_missing(symbol, "annual_report_text", "Annual report text extraction failed"))
        return ""

    (raw_dir / "annual_report_text.txt").write_text(text, encoding="utf-8")
    source_trail.append(
        GovernanceSource(
            "live.annual_report",
            "ok",
            rows=1,
            fallback=True,
            metadata={"url": url, "selected_label": selected["label"], **metadata},
        )
    )
    return text


def _announcement_rows(symbol: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    if _payload_error(payload):
        return []
    rows: list[dict[str, Any]] = []
    for item in _list(payload.get("bse_filings")):
        subject = _text(item.get("subject"))
        if subject:
            rows.append(
                {
                    "SYMBOL": symbol,
                    "subject": subject,
                    "url": item.get("url"),
                    "SOURCE": item.get("source_site") or "screener.documents",
                }
            )
    for item in _list(payload.get("nse_filings")):
        subject = _text(item.get("subject"))
        if subject:
            rows.append(
                {
                    "SYMBOL": symbol,
                    "date": item.get("date"),
                    "subject": subject,
                    "url": item.get("url"),
                    "SOURCE": "nse.corp-info",
                }
            )
    return rows


def _corporate_action_rows(symbol: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    if _payload_error(payload):
        return []
    rows: list[dict[str, Any]] = []
    for item in _list(payload.get("all")):
        subject = _text(item.get("subject"))
        if subject:
            rows.append(
                {
                    "SYMBOL": symbol,
                    "date": item.get("ex_date"),
                    "subject": subject,
                    "SOURCE": "nse.corporate-actions",
                }
            )
    return rows


def _shareholding_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    shareholding = payload.get("shareholding") if isinstance(payload, dict) else {}
    if not isinstance(shareholding, dict):
        return []

    quarters = _list(shareholding.get("_quarters"))
    rows: list[dict[str, Any]] = []
    for idx, quarter in enumerate(quarters):
        rows.append(
            {
                "quarter": quarter,
                "promoter_pct": _series_value(shareholding, "Promoters", idx),
                "pledge_pct": _pledge_value(payload),
                "pledge_of_total_pct": _pledge_value(payload),
                "fii": _series_value(shareholding, "FIIs", idx),
                "dii": _series_value(shareholding, "DIIs", idx),
                "public": _series_value(shareholding, "Public", idx),
                "source": "screener",
            }
        )
    return rows


def _series_value(shareholding: dict[str, Any], label: str, idx: int) -> Any:
    values = _list(shareholding.get(f"{label}_trend"))
    if idx < len(values):
        return values[idx]
    value = shareholding.get(label)
    return value if idx == 0 else None


def _pledge_value(payload: dict[str, Any]) -> str:
    alert = _text(payload.get("pledge_alert"))
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*%", alert)
    return match.group(1) if match else "0"


def _record_fetcher_source(
    source_trail: list[GovernanceSource],
    missing_evidence: list[GovernanceMissingEvidence],
    *,
    name: str,
    field: str,
    payload: dict[str, Any],
    rows: int,
    fallback: bool,
) -> None:
    error = _payload_error(payload)
    if error:
        source_trail.append(GovernanceSource(name, "error", rows=0, fallback=fallback, error=error))
        missing_evidence.append(_missing(_normalized_symbol(payload.get("symbol")), field, error))
        return
    source_trail.append(GovernanceSource(name, "ok" if rows else "missing", rows=rows, fallback=fallback))


def _call_fetcher(fetcher: Fetcher, symbol: str, *, max_results: int) -> dict[str, Any]:
    try:
        payload = fetcher(symbol, max_results=max_results)
        return payload if isinstance(payload, dict) else {"symbol": symbol, "error": "Fetcher returned non-dict payload"}
    except Exception as exc:
        return {"symbol": symbol, "error": str(exc)}


def _call_symbol_fetcher(fetcher: Callable[[str], dict[str, Any]], symbol: str) -> dict[str, Any]:
    try:
        payload = fetcher(symbol)
        return payload if isinstance(payload, dict) else {"symbol": symbol, "error": "Fetcher returned non-dict payload"}
    except Exception as exc:
        return {"symbol": symbol, "error": str(exc)}


def _default_announcements_fetcher(symbol: str, max_results: int = 8) -> dict[str, Any]:
    from terminal.search_engine import search_nse_announcements

    return search_nse_announcements(symbol, max_results=max_results)


def _default_corporate_actions_fetcher(symbol: str, max_results: int = 8) -> dict[str, Any]:
    from terminal.search_engine import search_corporate_actions

    return search_corporate_actions(symbol, max_results=max_results)


def _default_screener_fetcher(symbol: str) -> dict[str, Any]:
    from terminal.web_research import scrape_screener_in

    return scrape_screener_in(symbol)


def _download_pdf_bytes(url: str) -> bytes:
    import requests

    response = requests.get(
        str(url or "").split("#", 1)[0],
        headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)", "Accept": "application/pdf,*/*"},
        timeout=25,
        allow_redirects=True,
    )
    response.raise_for_status()
    return response.content


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _payload_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("data") if isinstance(payload, dict) else []
    return rows if isinstance(rows, list) else []


def _payload_error(payload: dict[str, Any]) -> str | None:
    error = payload.get("error") if isinstance(payload, dict) else "Invalid payload"
    text = _text(error)
    return text or None


def _select_annual_report(reports: list[Any]) -> dict[str, str]:
    candidates = []
    for index, item in enumerate(reports):
        if not isinstance(item, dict):
            continue
        url = _text(item.get("url"))
        if not url:
            continue
        label = _text(item.get("label"))
        candidates.append(
            {
                "index": index,
                "label": label,
                "url": url,
                "year": _annual_report_year(label, url),
            }
        )
    if not candidates:
        return {"label": "", "url": ""}

    with_year = [item for item in candidates if item["year"] is not None]
    if with_year:
        selected = max(with_year, key=lambda item: (int(item["year"]), -int(item["index"])))
    else:
        selected = candidates[0]
    return {"label": str(selected["label"]), "url": str(selected["url"])}


def _first_report_url(reports: list[Any]) -> str:
    return _select_annual_report(reports)["url"]


def _annual_report_year(label: str, url: str) -> int | None:
    text = f"{label} {url}"
    years = [int(match) for match in re.findall(r"\b(20\d{2})\b", text)]
    if not years:
        return None
    return max(years)


def _missing(symbol: str, field: str, reason: str) -> GovernanceMissingEvidence:
    return GovernanceMissingEvidence("governance", _normalized_symbol(symbol), field, "warn", reason)


def _normalized_symbol(symbol: Any) -> str:
    return str(symbol or "").strip().upper()


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value or "").strip()
