"""Ad-hoc ingestion of a single PDF (URL or local path) into the KB.

PG 2026-05-27: complements the registry-driven fetcher. Lets users drop a
broker / regulator report directly into the vector store without editing
financial_sources_registry.json.

Public API
----------
ingest_pdf_url(url, *, source_id, source_name="", category="adhoc",
               tier=9, hub_label="adhoc", do_qa=True) -> dict
ingest_local_pdf(path, *, source_id, source_name="", category="adhoc",
                 tier=9, hub_label="adhoc", do_qa=True) -> dict
ingest_any(target, **kwargs) -> dict     # URL or path autodetect

Each call:
  1. Downloads / copies the PDF into data/knowledge_base/raw/<source_id>/<date>/
  2. Appends a manifest row.
  3. Chunks the PDF via the standard chunker.
  4. (optional) Generates Q&A via gpt-4o-mini.
  5. Upserts both into ChromaDB.
  6. Returns a summary dict with counts, chunk_ids, file path.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

from ._common import (
    MANIFEST_PATH,
    QA_PATH,
    CHUNKS_PATH,
    RAW_DIR,
    USER_AGENT,
    now_iso,
    safe_filename,
    today_str,
)
from .chunker import chunk_document
from .qa_generator import generate_qa_for_chunk
from .vector_store import KBVectorStore

# PG: tighter timeout for ad-hoc URL ingest — keeps CLI responsive
REQUEST_TIMEOUT = 30
MAX_BYTES = 25 * 1024 * 1024  # 25 MB cap matches fetcher.py


# ─────────────────────────────────────────────────────────────────────────────
# helpers
# ─────────────────────────────────────────────────────────────────────────────

def _sha1(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()[:12]


def _looks_like_url(target: str) -> bool:
    p = urlparse(target)
    return p.scheme in {"http", "https"} and bool(p.netloc)


def _append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _download_pdf(url: str) -> bytes:
    """Stream-download a PDF with size cap and PDF magic-byte check."""
    headers = {"User-Agent": USER_AGENT, "Accept": "application/pdf,*/*"}
    r = requests.get(url, timeout=REQUEST_TIMEOUT, headers=headers, stream=True, allow_redirects=True)
    r.raise_for_status()
    buf = bytearray()
    for chunk in r.iter_content(chunk_size=64 * 1024):
        if not chunk:
            continue
        buf.extend(chunk)
        if len(buf) > MAX_BYTES:
            raise RuntimeError(f"PDF exceeds {MAX_BYTES} bytes cap")
    data = bytes(buf)
    # PG: guard against silent HTML-redirect-to-login responses
    if not data.startswith(b"%PDF"):
        raise RuntimeError("downloaded content is not a PDF (missing %PDF header)")
    return data


def _save_artefact(data: bytes, *, source_id: str, original_name: str) -> Path:
    folder = RAW_DIR / source_id / today_str()
    folder.mkdir(parents=True, exist_ok=True)
    base = safe_filename(original_name or "doc.pdf")
    stem = base.rsplit(".", 1)[0]
    out = folder / f"{stem}__{_sha1(data)}.pdf"
    if not out.exists():
        out.write_bytes(data)
    return out


def _build_manifest_row(
    *,
    path: Path,
    url: str,
    source_id: str,
    source_name: str,
    category: str,
    tier: int,
    hub_label: str,
) -> dict:
    return {
        "ts": now_iso(),
        "url": url,
        "status": "ok",
        "kind": "pdf",
        "path": str(path),
        "source_id": source_id,
        "source_name": source_name or source_id,
        "category": category,
        "tier": tier,
        "hub_label": hub_label,
        "fetched_date": today_str(),
        "via": "adhoc_ingest",
    }


# ─────────────────────────────────────────────────────────────────────────────
# core ingest
# ─────────────────────────────────────────────────────────────────────────────

def _ingest_from_manifest(
    manifest_row: dict,
    *,
    do_qa: bool = True,
) -> dict[str, Any]:
    """Run chunk → (qa) → embed → upsert for a single manifest row."""
    chunks = list(chunk_document(manifest_row))
    if not chunks:
        return {
            "ok": False,
            "error": "no chunks extracted (PDF may be image-only or empty)",
            "path": manifest_row.get("path"),
            "chunks": 0,
            "qa": 0,
        }

    # PG: persist chunk metadata to chunks.jsonl so existing tooling sees it
    for c in chunks:
        _append_jsonl(CHUNKS_PATH, c)

    store = KBVectorStore()
    n_chunks = store.upsert_chunks(chunks)

    n_qa = 0
    if do_qa:
        all_qa: list[dict] = []
        for c in chunks:
            pairs = generate_qa_for_chunk(c)
            for p in pairs:
                _append_jsonl(QA_PATH, p)
            all_qa.extend(pairs)
        if all_qa:
            n_qa = store.upsert_qa(all_qa)

    return {
        "ok": True,
        "path": manifest_row.get("path"),
        "source_id": manifest_row.get("source_id"),
        "source_url": manifest_row.get("url"),
        "fetched_date": manifest_row.get("fetched_date"),
        "chunks": n_chunks,
        "qa": n_qa,
        "chunk_ids": [c["chunk_id"] for c in chunks],
    }


# ─────────────────────────────────────────────────────────────────────────────
# public entry points
# ─────────────────────────────────────────────────────────────────────────────

def ingest_pdf_url(
    url: str,
    *,
    source_id: str = "ADHOC",
    source_name: str = "",
    category: str = "adhoc",
    tier: int = 9,
    hub_label: str = "adhoc",
    do_qa: bool = True,
) -> dict[str, Any]:
    """Download a remote PDF and index it. Returns summary dict."""
    if not _looks_like_url(url):
        return {"ok": False, "error": f"not a URL: {url}"}
    try:
        data = _download_pdf(url)
    except Exception as exc:
        row = {
            "ts": now_iso(), "url": url, "status": "error",
            "error": str(exc)[:200], "via": "adhoc_ingest",
        }
        _append_jsonl(MANIFEST_PATH, row)
        return {"ok": False, "error": str(exc), "url": url}

    original_name = Path(urlparse(url).path).name or "doc.pdf"
    saved = _save_artefact(data, source_id=source_id, original_name=original_name)
    manifest_row = _build_manifest_row(
        path=saved, url=url, source_id=source_id, source_name=source_name,
        category=category, tier=tier, hub_label=hub_label,
    )
    _append_jsonl(MANIFEST_PATH, manifest_row)
    return _ingest_from_manifest(manifest_row, do_qa=do_qa)


def ingest_local_pdf(
    path: str | Path,
    *,
    source_id: str = "ADHOC",
    source_name: str = "",
    category: str = "adhoc",
    tier: int = 9,
    hub_label: str = "adhoc",
    do_qa: bool = True,
) -> dict[str, Any]:
    """Copy a local PDF into the raw store and index it."""
    src = Path(path).expanduser().resolve()
    if not src.exists():
        return {"ok": False, "error": f"file not found: {src}"}
    if not src.is_file():
        return {"ok": False, "error": f"not a file: {src}"}

    data = src.read_bytes()
    if not data.startswith(b"%PDF"):
        return {"ok": False, "error": f"not a PDF (missing %PDF header): {src}"}

    saved = _save_artefact(data, source_id=source_id, original_name=src.name)
    manifest_row = _build_manifest_row(
        path=saved, url=f"file://{src}", source_id=source_id, source_name=source_name,
        category=category, tier=tier, hub_label=hub_label,
    )
    _append_jsonl(MANIFEST_PATH, manifest_row)
    return _ingest_from_manifest(manifest_row, do_qa=do_qa)


def ingest_any(
    target: str,
    *,
    source_id: str = "ADHOC",
    source_name: str = "",
    category: str = "adhoc",
    tier: int = 9,
    hub_label: str = "adhoc",
    do_qa: bool = True,
) -> dict[str, Any]:
    """Autodetect URL vs local path and route accordingly."""
    if _looks_like_url(target):
        return ingest_pdf_url(
            target, source_id=source_id, source_name=source_name,
            category=category, tier=tier, hub_label=hub_label, do_qa=do_qa,
        )
    return ingest_local_pdf(
        target, source_id=source_id, source_name=source_name,
        category=category, tier=tier, hub_label=hub_label, do_qa=do_qa,
    )


__all__ = ["ingest_pdf_url", "ingest_local_pdf", "ingest_any"]
