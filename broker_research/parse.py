"""Parse broker report PDFs and store page text evidence."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from financial_filing_agent import parse_pdf_filing

from .storage import replace_report_pages, update_report_parse_status


PdfParser = Callable[[Path], dict[str, Any]]


def parse_and_store_broker_report(
    conn: Any,
    *,
    broker_report_id: int,
    local_path: str,
    parser: PdfParser | None = None,
) -> dict[str, Any]:
    pdf_path = Path(local_path)
    parse = parser or parse_pdf_filing
    result = parse(pdf_path)
    status = str(result.get("status") or "error")
    pages = list(result.get("pages") or [])
    if status in {"ok", "partial"}:
        pages_stored = replace_report_pages(conn, broker_report_id=broker_report_id, pages=pages)
        parse_status = "parsed" if status == "ok" else "partial"
    else:
        pages_stored = 0
        parse_status = "parse_failed"
    update_report_parse_status(conn, broker_report_id=broker_report_id, parse_status=parse_status)
    return {"status": status, "pages_stored": pages_stored, "parse_status": parse_status}
