"""
Financial filing ingestion and registry for Agent Adda.

This module is deliberately deterministic. It downloads and registers filing
artifacts, but it does not ask an LLM to interpret raw documents.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping
from urllib.parse import urlparse

import requests


DEFAULT_ROOT = Path("data") / "filings"
PDF_BACKEND_INSTALL_HINT = "Install PyMuPDF with: .venv/bin/python -m pip install pymupdf"


@dataclass(frozen=True)
class FilingResponse:
    content: bytes
    headers: Mapping[str, str]
    status_code: int = 200

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def safe_path_part(value: str | None) -> str:
    """Return a filesystem-safe uppercase path component."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "").strip())
    cleaned = cleaned.strip("._-")
    cleaned = re.sub(r"_+", "_", cleaned)
    return cleaned.upper() if cleaned else "UNKNOWN"


def _content_type_value(headers_or_content_type: Mapping[str, str] | str | None) -> str:
    if isinstance(headers_or_content_type, str):
        return headers_or_content_type.lower()
    if not headers_or_content_type:
        return ""
    for key, value in headers_or_content_type.items():
        if key.lower() == "content-type":
            return str(value).lower()
    return ""


def detect_document_type(url: str, content_type: str | Mapping[str, str] = "", content: bytes = b"") -> str:
    """Classify a filing artifact without parsing its business meaning."""
    path = urlparse(url).path.lower()
    ctype = _content_type_value(content_type)
    sample = (content or b"")[:4096].lower()

    if path.endswith(".pdf") or "application/pdf" in ctype or sample.startswith(b"%pdf"):
        return "pdf"
    if path.endswith(".zip") or "zip" in ctype or sample.startswith(b"pk\x03\x04"):
        return "zip"
    if (
        path.endswith((".xml", ".xbrl"))
        or "xml" in ctype
        or b"<xbrli:xbrl" in sample
        or b"<xbrl" in sample
    ):
        return "xbrl"
    if path.endswith((".html", ".htm")) or "html" in ctype:
        if b"ix:" in sample or b"inline xbrl" in sample or b"www.xbrl.org" in sample:
            return "ixbrl"
        return "html"
    return "unknown"


def _default_fetcher(url: str) -> FilingResponse:
    response = requests.get(
        url,
        timeout=30,
        headers={
            "User-Agent": "Mozilla/5.0 AgentAdda/1.0",
            "Accept": "application/pdf,application/xml,text/html,*/*",
        },
    )
    return FilingResponse(content=response.content, headers=response.headers, status_code=response.status_code)


def _filename_from_url(url: str, document_type: str) -> str:
    name = Path(urlparse(url).path).name
    if name:
        return safe_path_part(name).lower()
    ext = {
        "pdf": ".pdf",
        "xbrl": ".xml",
        "ixbrl": ".html",
        "html": ".html",
        "zip": ".zip",
    }.get(document_type, ".bin")
    return f"filing{ext}"


def _manifest_path(root_dir: Path, symbol: str | None, period: str | None) -> Path:
    return root_dir / safe_path_part(symbol) / safe_path_part(period) / "manifest.json"


def _existing_manifest(root_dir: Path, symbol: str | None, period: str | None, source_url: str) -> dict | None:
    path = _manifest_path(root_dir, symbol, period)
    if not path.exists():
        return None
    try:
        manifest = json.loads(path.read_text())
    except json.JSONDecodeError:
        return None
    if manifest.get("source_url") == source_url and manifest.get("status") == "ok":
        local_path = Path(str(manifest.get("local_path", "")))
        if local_path.exists():
            return manifest
    return None


def _write_manifest(path: Path, manifest: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


def ingest_filing_url(
    url: str,
    symbol: str | None = None,
    period: str | None = None,
    root_dir: Path | str = DEFAULT_ROOT,
    fetcher: Callable[[str], object] | None = None,
    force: bool = False,
) -> dict:
    """
    Download and register a filing URL under data/filings.

    Returns a manifest-shaped dict. Network and HTTP failures are returned as
    structured errors so terminal workflows can continue.
    """
    root = Path(root_dir)
    guessed_type = detect_document_type(url)
    if not force:
        existing = _existing_manifest(root, symbol, period, url)
        if existing:
            return existing

    manifest_path = _manifest_path(root, symbol, period)
    raw_dir = manifest_path.parent / "raw"
    fetched_at = datetime.now(timezone.utc).isoformat()
    fetch = fetcher or _default_fetcher

    try:
        response = fetch(url)
        if hasattr(response, "raise_for_status"):
            response.raise_for_status()
        content = bytes(getattr(response, "content"))
        headers = getattr(response, "headers", {}) or {}
        content_type = _content_type_value(headers)
        document_type = detect_document_type(url, content_type, content)
        sha256 = hashlib.sha256(content).hexdigest()
        filename = _filename_from_url(url, document_type)
        local_path = raw_dir / filename
        raw_dir.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(content)

        manifest = {
            "status": "ok",
            "error": None,
            "symbol": safe_path_part(symbol),
            "period": safe_path_part(period),
            "source_url": url,
            "local_path": str(local_path),
            "manifest_path": str(manifest_path),
            "sha256": sha256,
            "content_type": content_type,
            "document_type": document_type,
            "fetched_at": fetched_at,
        }
        _write_manifest(manifest_path, manifest)
        return manifest
    except Exception as exc:
        return {
            "status": "error",
            "error": str(exc),
            "symbol": safe_path_part(symbol),
            "period": safe_path_part(period),
            "source_url": url,
            "local_path": None,
            "manifest_path": str(manifest_path),
            "sha256": None,
            "content_type": "",
            "document_type": guessed_type,
            "fetched_at": fetched_at,
        }


def _load_pdf_backend():
    try:
        import fitz  # type: ignore
    except ImportError:
        return None
    return fitz


def _empty_parse_error(
    error_code: str,
    error: str,
    source_path: Path,
    warnings: list[str] | None = None,
) -> dict:
    return {
        "status": "error",
        "error_code": error_code,
        "error": error,
        "document_type": "pdf",
        "source_path": str(source_path),
        "page_count": 0,
        "pages": [],
        "tables": [],
        "evidence": [],
        "warnings": warnings or [],
    }


def _clean_table_value(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _extract_page_tables(page: object, page_number: int) -> tuple[list[dict], list[dict]]:
    if not hasattr(page, "find_tables"):
        return [], []

    try:
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            table_finder = page.find_tables()
    except Exception:
        return [], []

    tables = []
    evidence = []
    for table_index, table in enumerate(getattr(table_finder, "tables", []) or [], start=1):
        try:
            raw_rows = table.extract()
        except Exception:
            continue
        rows = [[_clean_table_value(cell) for cell in row] for row in raw_rows if row]
        if not rows:
            continue

        column_count = max((len(row) for row in rows), default=0)
        headers = rows[0] if rows else []
        table_record = {
            "page_number": page_number,
            "table_index": table_index,
            "row_count": len(rows),
            "column_count": column_count,
            "rows": rows,
        }
        tables.append(table_record)

        for row_index, row in enumerate(rows[1:], start=2):
            row_label = row[0] if row else ""
            for column_index, value in enumerate(row[1:], start=2):
                if not value:
                    continue
                column_label = headers[column_index - 1] if column_index - 1 < len(headers) else f"Column {column_index}"
                evidence.append(
                    {
                        "source_type": "pdf_table_cell",
                        "page_number": page_number,
                        "table_index": table_index,
                        "row_index": row_index,
                        "column_index": column_index,
                        "row_label": row_label,
                        "column_label": column_label,
                        "extracted_value": value,
                        "confidence": "table_extraction",
                    }
                )

    return tables, evidence


def _page_image_count(page: object) -> int:
    if not hasattr(page, "get_images"):
        return 0
    try:
        return len(page.get_images(full=True))
    except Exception:
        return 0


def parse_pdf_filing(
    pdf_path: Path | str,
    backend_loader: Callable[[], object | None] | None = None,
) -> dict:
    """
    Extract deterministic page text, detected tables, and evidence from a PDF filing.
    """
    source_path = Path(pdf_path)
    if not source_path.exists():
        return _empty_parse_error("FILE_NOT_FOUND", f"PDF not found: {source_path}", source_path)

    loader = backend_loader or _load_pdf_backend
    backend = loader()
    if backend is None:
        return _empty_parse_error(
            "PDF_BACKEND_MISSING",
            PDF_BACKEND_INSTALL_HINT,
            source_path,
            warnings=["PDF text extraction requires PyMuPDF."],
        )

    pages: list[dict] = []
    evidence: list[dict] = []
    tables: list[dict] = []
    warnings: list[str] = []

    try:
        with backend.open(source_path) as document:
            for page_index, page in enumerate(document, start=1):
                text = str(page.get_text("text") or "").strip()
                image_count = _page_image_count(page)
                pages.append(
                    {
                        "page_number": page_index,
                        "char_count": len(text),
                        "image_count": image_count,
                        "text": text,
                    }
                )
                if text:
                    evidence.append(
                        {
                            "source_type": "pdf_page",
                            "page_number": page_index,
                            "text_excerpt": text[:500],
                            "confidence": "text_extraction",
                        }
                    )
                page_tables, page_table_evidence = _extract_page_tables(page, page_index)
                tables.extend(page_tables)
                evidence.extend(page_table_evidence)
            page_count = len(document)
    except Exception as exc:
        return _empty_parse_error("PDF_PARSE_FAILED", str(exc), source_path)

    scanned_page_count = sum(1 for page in pages if page.get("char_count") == 0 and page.get("image_count", 0) > 0)
    ocr_required = page_count > 0 and scanned_page_count == page_count and not evidence
    if ocr_required:
        warnings.append("OCR required: all PDF pages appear to be image-only and no text/table evidence was extracted.")

    return {
        "status": "partial" if ocr_required else "ok",
        "error_code": "OCR_REQUIRED" if ocr_required else None,
        "error": "Image-only PDF requires OCR extraction." if ocr_required else None,
        "document_type": "pdf",
        "source_path": str(source_path),
        "page_count": page_count,
        "scanned_page_count": scanned_page_count,
        "pages": pages,
        "tables": tables,
        "evidence": evidence,
        "warnings": warnings,
        "parsed_at": datetime.now(timezone.utc).isoformat(),
    }


def parse_registered_filing(
    manifest_path: Path | str,
    parser: Callable[[Path], dict] | None = None,
) -> dict:
    """
    Parse a previously ingested filing manifest and write parsed/filing_parse.json.
    """
    manifest_file = Path(manifest_path)
    try:
        manifest = json.loads(manifest_file.read_text())
    except FileNotFoundError:
        return {
            "status": "error",
            "error_code": "MANIFEST_NOT_FOUND",
            "error": f"Manifest not found: {manifest_file}",
            "manifest_path": str(manifest_file),
        }
    except json.JSONDecodeError as exc:
        return {
            "status": "error",
            "error_code": "MANIFEST_INVALID_JSON",
            "error": str(exc),
            "manifest_path": str(manifest_file),
        }

    if manifest.get("status") != "ok":
        return {
            "status": "error",
            "error_code": "MANIFEST_NOT_READY",
            "error": "Cannot parse a failed or incomplete manifest.",
            "manifest_path": str(manifest_file),
        }

    document_type = manifest.get("document_type")
    if document_type != "pdf":
        return {
            "status": "error",
            "error_code": "UNSUPPORTED_DOCUMENT_TYPE",
            "error": f"Parser currently supports pdf filings only, got: {document_type}",
            "manifest_path": str(manifest_file),
        }

    local_path = Path(str(manifest.get("local_path", "")))
    parse = parser or parse_pdf_filing
    parsed = parse(local_path)
    parsed_path = manifest_file.parent / "parsed" / "filing_parse.json"
    parsed_path.parent.mkdir(parents=True, exist_ok=True)
    parsed_with_registry = {
        **parsed,
        "manifest_path": str(manifest_file),
        "parsed_path": str(parsed_path),
        "symbol": manifest.get("symbol"),
        "period": manifest.get("period"),
        "source_url": manifest.get("source_url"),
    }
    parsed_path.write_text(json.dumps(parsed_with_registry, indent=2, sort_keys=True) + "\n")
    return parsed_with_registry


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Agent Adda financial filing ingestion")
    sub = parser.add_subparsers(dest="command", required=True)
    ingest = sub.add_parser("ingest", help="Download and register a direct filing URL")
    ingest.add_argument("url")
    ingest.add_argument("--symbol", default=None)
    ingest.add_argument("--period", default=None)
    ingest.add_argument("--root-dir", default=str(DEFAULT_ROOT))
    ingest.add_argument("--force", action="store_true")
    parse = sub.add_parser("parse", help="Parse a registered filing manifest")
    parse.add_argument("manifest_path")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    if args.command == "ingest":
        result = ingest_filing_url(
            args.url,
            symbol=args.symbol,
            period=args.period,
            root_dir=Path(args.root_dir),
            force=args.force,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result.get("status") == "ok" else 1
    if args.command == "parse":
        result = parse_registered_filing(Path(args.manifest_path))
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result.get("status") == "ok" else 1
    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
