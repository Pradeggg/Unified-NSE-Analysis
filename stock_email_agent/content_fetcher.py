"""Fetch and extract text from URLs referenced in emails (HTML or PDF)."""
from __future__ import annotations

import hashlib
import io
import logging
import os
from dataclasses import dataclass
from typing import Optional

import requests

log = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (compatible; StockEmailAgent/0.1; +https://github.com/)"


@dataclass
class FetchedContent:
    url: str
    content_type: str
    text: str
    cached_path: Optional[str] = None


def _cache_path(cache_dir: str, url: str, suffix: str) -> str:
    h = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
    return os.path.join(cache_dir, f"{h}{suffix}")


def fetch_url(url: str, cache_dir: str, max_bytes: int, timeout: int) -> Optional[FetchedContent]:
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
            timeout=timeout,
            stream=True,
            allow_redirects=True,
        )
    except Exception as exc:
        log.warning("fetch failed %s: %s", url, exc)
        return None
    if resp.status_code >= 400:
        log.warning("fetch %s -> HTTP %s", url, resp.status_code)
        return None

    ctype = (resp.headers.get("Content-Type") or "").lower()
    final_url = resp.url

    buf = io.BytesIO()
    total = 0
    for chunk in resp.iter_content(chunk_size=64 * 1024):
        if not chunk:
            continue
        buf.write(chunk)
        total += len(chunk)
        if total >= max_bytes:
            break
    data = buf.getvalue()

    suffix = ".pdf" if "pdf" in ctype or final_url.lower().endswith(".pdf") else ".html"
    path = _cache_path(cache_dir, final_url, suffix)
    try:
        with open(path, "wb") as fh:
            fh.write(data)
    except Exception:
        path = None

    if suffix == ".pdf":
        text = _extract_pdf_text(data)
        return FetchedContent(url=final_url, content_type="application/pdf", text=text, cached_path=path)

    text = _extract_html_text(data, ctype)
    return FetchedContent(url=final_url, content_type=ctype or "text/html", text=text, cached_path=path)


def _extract_html_text(data: bytes, ctype: str) -> str:
    try:
        from bs4 import BeautifulSoup
        encoding = "utf-8"
        if "charset=" in ctype:
            encoding = ctype.split("charset=")[-1].strip() or "utf-8"
        try:
            html = data.decode(encoding, errors="replace")
        except LookupError:
            html = data.decode("utf-8", errors="replace")
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        return soup.get_text("\n", strip=True)
    except Exception as exc:
        log.debug("html extract failed: %s", exc)
        return data[:50000].decode("utf-8", errors="replace")


def _extract_pdf_text(data: bytes) -> str:
    # Prefer pymupdf (already a project dependency)
    try:
        import fitz  # pymupdf
        text_parts = []
        with fitz.open(stream=data, filetype="pdf") as doc:
            for page in doc:
                text_parts.append(page.get_text("text"))
        return "\n".join(text_parts).strip()
    except Exception as exc:
        log.debug("pymupdf failed: %s", exc)
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        return "\n".join((page.extract_text() or "") for page in reader.pages).strip()
    except Exception as exc:
        log.warning("pdf extraction failed: %s", exc)
        return ""
