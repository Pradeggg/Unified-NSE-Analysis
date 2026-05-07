"""
Financial filing ingestion and registry for Agent Adda.

This module is deliberately deterministic. It downloads and registers filing
artifacts, but it does not ask an LLM to interpret raw documents.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping
from urllib.parse import urlparse

import requests


DEFAULT_ROOT = Path("data") / "filings"


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


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Agent Adda financial filing ingestion")
    sub = parser.add_subparsers(dest="command", required=True)
    ingest = sub.add_parser("ingest", help="Download and register a direct filing URL")
    ingest.add_argument("url")
    ingest.add_argument("--symbol", default=None)
    ingest.add_argument("--period", default=None)
    ingest.add_argument("--root-dir", default=str(DEFAULT_ROOT))
    ingest.add_argument("--force", action="store_true")
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
    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
