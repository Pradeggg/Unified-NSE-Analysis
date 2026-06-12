"""Fetch and persist public broker research PDFs."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from urllib.parse import unquote, urlparse


DEFAULT_REPORT_ROOT = Path("data/company_intelligence/broker_reports")
DEFAULT_MAX_BYTES = 25_000_000


def _safe_part(value: str, fallback: str = "UNKNOWN") -> str:
    clean = re.sub(r"[^A-Za-z0-9_.-]+", "_", (value or "").strip()).strip("._")
    return clean or fallback


def _filename_from_url(pdf_url: str, pdf_hash: str) -> str:
    parsed = urlparse(pdf_url)
    name = unquote(Path(parsed.path).name)
    if not name.lower().endswith(".pdf"):
        name = f"{pdf_hash[:16]}.pdf"
    return f"{pdf_hash[:12]}_{_safe_part(name, 'report.pdf')}"


def _default_fetcher(url: str):
    import requests

    return requests.get(url, timeout=20, headers={"User-Agent": "AgentAddaResearchBot/1.0 (+research-only)"})


def _response_content(response: object) -> tuple[bytes, str]:
    if hasattr(response, "raise_for_status"):
        response.raise_for_status()
    content = bytes(getattr(response, "content", b""))
    headers = getattr(response, "headers", {}) or {}
    content_type = str(headers.get("content-type") or headers.get("Content-Type") or "")
    return content, content_type


def fetch_broker_report_pdf(
    *,
    broker_code: str,
    symbol: str,
    pdf_url: str,
    root_dir: Path | str = DEFAULT_REPORT_ROOT,
    fetcher=None,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> dict[str, object]:
    fetch = fetcher or _default_fetcher
    try:
        content, content_type = _response_content(fetch(pdf_url))
    except Exception as exc:
        return {
            "status": "fetch_error",
            "error": str(exc),
            "pdf_url": pdf_url,
            "pdf_hash": "",
            "local_path": "",
            "content_type": "",
            "content_length": 0,
        }

    content_length = len(content)
    if content_length > max_bytes:
        return {
            "status": "pdf_too_large",
            "error": f"PDF size {content_length} exceeds max_bytes {max_bytes}",
            "pdf_url": pdf_url,
            "pdf_hash": "",
            "local_path": "",
            "content_type": content_type,
            "content_length": content_length,
        }

    pdf_hash = hashlib.sha256(content).hexdigest()
    target_dir = Path(root_dir) / _safe_part(broker_code.lower()) / _safe_part(symbol.upper())
    target_dir.mkdir(parents=True, exist_ok=True)
    local_path = target_dir / _filename_from_url(pdf_url, pdf_hash)
    if not local_path.exists():
        local_path.write_bytes(content)

    return {
        "status": "ok",
        "error": "",
        "pdf_url": pdf_url,
        "pdf_hash": pdf_hash,
        "local_path": str(local_path),
        "content_type": content_type,
        "content_length": content_length,
    }
