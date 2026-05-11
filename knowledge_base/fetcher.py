"""Fetch HTML/PDF artefacts from registry hubs.

Strategy:
    - Fetch the hub URL (HTML page).
    - Parse it for <a href="*.pdf">; download up to N PDFs per hub.
    - Save artefacts under data/knowledge_base/raw/<source_id>/<YYYY-MM-DD>/
    - Append a manifest row for every URL attempted (success or failure).

Respects robots.txt by default by sending a clear User-Agent and rate-limiting.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from ._common import (
    MANIFEST_PATH, RAW_DIR, USER_AGENT, now_iso, safe_filename, today_str
)
from .registry import iter_sources

REQUEST_TIMEOUT = 25
MAX_PDFS_PER_HUB = 5         # cap per hub per run (be polite + bounded)
MIN_DELAY_SEC    = 1.0       # between requests to same host
MAX_BYTES        = 25 * 1024 * 1024  # 25 MB safety cap on a single PDF


def _sha1(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()[:12]


def _append_manifest(row: dict) -> None:
    with MANIFEST_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _http_get(url: str, *, session: requests.Session) -> requests.Response | None:
    try:
        r = session.get(
            url,
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
            allow_redirects=True,
            stream=True,
        )
        r.raise_for_status()
        return r
    except Exception as exc:
        _append_manifest({
            "ts": now_iso(), "url": url, "status": "error", "error": str(exc)[:200],
        })
        return None


def _save_artefact(content: bytes, *, source_id: str, original_url: str, suffix: str) -> Path:
    """Persist bytes to raw/<source_id>/<YYYY-MM-DD>/<safe>__<sha>.suffix"""
    folder = RAW_DIR / source_id / today_str()
    folder.mkdir(parents=True, exist_ok=True)
    base = safe_filename(Path(urlparse(original_url).path).name or "doc")
    stem = base.rsplit(".", 1)[0]
    out = folder / f"{stem}__{_sha1(content)}.{suffix.lstrip('.')}"
    if not out.exists():  # idempotent
        out.write_bytes(content)
    return out


def _looks_like_pdf(url: str, content_type: str = "") -> bool:
    if "application/pdf" in content_type.lower():
        return True
    return urlparse(url).path.lower().endswith(".pdf")


def fetch_source(hub: dict, *, max_pdfs: int = MAX_PDFS_PER_HUB) -> list[dict]:
    """Fetch the hub URL plus up to `max_pdfs` PDF links discovered on it.

    Returns list of manifest rows (also persisted to manifest.jsonl).
    """
    rows: list[dict] = []
    session = requests.Session()
    url = hub["url"]
    sid = hub["source_id"]

    resp = _http_get(url, session=session)
    if resp is None:
        return rows
    ct = resp.headers.get("Content-Type", "")
    body = b""
    for chunk in resp.iter_content(8192):
        body += chunk
        if len(body) > MAX_BYTES:
            break

    # Case 1: hub itself is a PDF
    if _looks_like_pdf(url, ct):
        path = _save_artefact(body, source_id=sid, original_url=url, suffix="pdf")
        row = {
            "ts": now_iso(), "url": url, "status": "ok", "kind": "pdf",
            "bytes": len(body), "path": str(path),
            "source_id": sid, "category": hub["category"], "tier": hub["tier"],
            "hub_label": hub["hub_label"], "fetched_date": today_str(),
        }
        rows.append(row)
        _append_manifest(row)
        return rows

    # Case 2: HTML — save it, then discover PDF links.
    html_path = _save_artefact(body, source_id=sid, original_url=url, suffix="html")
    rows.append({
        "ts": now_iso(), "url": url, "status": "ok", "kind": "html",
        "bytes": len(body), "path": str(html_path),
        "source_id": sid, "category": hub["category"], "tier": hub["tier"],
        "hub_label": hub["hub_label"], "fetched_date": today_str(),
    })
    _append_manifest(rows[-1])

    try:
        soup = BeautifulSoup(body, "html.parser")
    except Exception:
        return rows

    pdf_links: list[str] = []
    for a in soup.find_all("a", href=True):
        href = (a.get("href") or "").strip()
        if not href or href.startswith(("#", "mailto:", "javascript:")):
            continue
        absolute = urljoin(url, href)
        if absolute.lower().split("?")[0].endswith(".pdf") and absolute not in pdf_links:
            pdf_links.append(absolute)
        if len(pdf_links) >= max_pdfs:
            break

    for pdf_url in pdf_links:
        time.sleep(MIN_DELAY_SEC)
        r = _http_get(pdf_url, session=session)
        if r is None:
            continue
        data = b""
        for chunk in r.iter_content(8192):
            data += chunk
            if len(data) > MAX_BYTES:
                break
        try:
            path = _save_artefact(data, source_id=sid, original_url=pdf_url, suffix="pdf")
        except Exception as exc:
            _append_manifest({
                "ts": now_iso(), "url": pdf_url, "status": "error",
                "error": f"save: {exc}"[:200],
            })
            continue
        row = {
            "ts": now_iso(), "url": pdf_url, "status": "ok", "kind": "pdf",
            "bytes": len(data), "path": str(path),
            "source_id": sid, "category": hub["category"], "tier": hub["tier"],
            "hub_label": hub["hub_label"], "fetched_date": today_str(),
            "discovered_from": url,
        }
        rows.append(row)
        _append_manifest(row)

    return rows


def fetch_all(
    *,
    categories: list[str] | None = None,
    tiers: list[int] | None = None,
    source_ids: list[str] | None = None,
    max_pdfs_per_hub: int = MAX_PDFS_PER_HUB,
    delay_between_hubs: float = 1.5,
) -> list[dict]:
    """Walk the registry and fetch everything matching the filters."""
    all_rows: list[dict] = []
    for hub in iter_sources(categories=categories, tiers=tiers, source_ids=source_ids):
        rows = fetch_source(hub, max_pdfs=max_pdfs_per_hub)
        all_rows.extend(rows)
        time.sleep(delay_between_hubs)
    return all_rows
