"""Document → semantic chunks. Handles PDF and HTML.

Chunking policy:
    - Extract clean text (PDF: per page; HTML: visible text via BS4).
    - Concatenate, then split on paragraph/heading boundaries.
    - Pack into chunks of ~CHUNK_TOKENS tokens with CHUNK_OVERLAP token overlap.
    - Each chunk carries: source_id, category, tier, hub_label, source_url,
      fetched_date, page_range (PDFs), chunk_index, chunk_id (sha1).
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Iterator

CHUNK_TOKENS  = 700      # ~3-4 paragraphs of dense prose
CHUNK_OVERLAP = 80       # tokens of overlap between adjacent chunks


def _tok_count(s: str) -> int:
    """Cheap token estimator (1 token ≈ 4 chars / 0.75 words). Avoids tiktoken cost."""
    return max(1, int(len(s) / 4))


def _sha1(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:16]


def _pdf_to_pages(path: Path) -> list[tuple[int, str]]:
    try:
        from pypdf import PdfReader
    except Exception:
        return []
    pages: list[tuple[int, str]] = []
    try:
        reader = PdfReader(str(path))
        for i, p in enumerate(reader.pages, start=1):
            try:
                txt = p.extract_text() or ""
            except Exception:
                txt = ""
            txt = re.sub(r"[ \t]+", " ", txt).strip()
            if txt:
                pages.append((i, txt))
    except Exception:
        return []
    return pages


def _html_to_text(path: Path) -> str:
    try:
        from bs4 import BeautifulSoup
    except Exception:
        return ""
    try:
        soup = BeautifulSoup(path.read_bytes(), "html.parser")
    except Exception:
        return ""
    for bad in soup(["script", "style", "noscript", "header", "footer", "nav", "form"]):
        bad.decompose()
    text = soup.get_text("\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def _split_paragraphs(text: str) -> list[str]:
    paras = re.split(r"\n\s*\n+", text)
    return [p.strip() for p in paras if p.strip()]


def _pack_chunks(paragraphs: list[str]) -> list[str]:
    chunks: list[str] = []
    cur: list[str] = []
    cur_tokens = 0
    for p in paragraphs:
        n = _tok_count(p)
        if cur_tokens + n > CHUNK_TOKENS and cur:
            chunks.append("\n\n".join(cur))
            # carry overlap forward (last paragraph or two)
            carry: list[str] = []
            ct = 0
            for q in reversed(cur):
                ct += _tok_count(q)
                carry.insert(0, q)
                if ct >= CHUNK_OVERLAP:
                    break
            cur = list(carry)
            cur_tokens = sum(_tok_count(x) for x in cur)
        cur.append(p)
        cur_tokens += n
    if cur:
        chunks.append("\n\n".join(cur))
    return chunks


def chunk_document(manifest_row: dict) -> Iterator[dict]:
    """Yield chunk dicts for a single fetched artefact (manifest row)."""
    path = Path(manifest_row.get("path", ""))
    if not path.exists():
        return
    kind = manifest_row.get("kind", "")
    base_meta = {
        "source_id":    manifest_row.get("source_id"),
        "source_name":  manifest_row.get("source_name"),
        "category":     manifest_row.get("category"),
        "tier":         manifest_row.get("tier"),
        "hub_label":    manifest_row.get("hub_label"),
        "source_url":   manifest_row.get("url"),
        "fetched_date": manifest_row.get("fetched_date"),
        "kind":         kind,
        "path":         str(path),
    }

    if kind == "pdf":
        pages = _pdf_to_pages(path)
        if not pages:
            return
        # Pack page-by-page so we can record page ranges per chunk.
        cur_text: list[str] = []
        cur_tokens = 0
        cur_pages: list[int] = []
        idx = 0
        for pno, ptext in pages:
            n = _tok_count(ptext)
            if cur_tokens + n > CHUNK_TOKENS and cur_text:
                blob = "\n\n".join(cur_text)
                yield _make_chunk(blob, base_meta, idx, page_range=(cur_pages[0], cur_pages[-1]))
                idx += 1
                cur_text, cur_tokens, cur_pages = [], 0, []
            cur_text.append(ptext)
            cur_tokens += n
            cur_pages.append(pno)
        if cur_text:
            blob = "\n\n".join(cur_text)
            yield _make_chunk(blob, base_meta, idx, page_range=(cur_pages[0], cur_pages[-1]))
        return

    if kind == "html":
        text = _html_to_text(path)
        if not text:
            return
        paras = _split_paragraphs(text)
        for idx, blob in enumerate(_pack_chunks(paras)):
            yield _make_chunk(blob, base_meta, idx, page_range=None)
        return


def _make_chunk(text: str, base_meta: dict, idx: int, *, page_range: tuple[int, int] | None) -> dict:
    cid = _sha1(f"{base_meta.get('path')}::{idx}::{text[:200]}")
    chunk: dict = {
        **base_meta,
        "chunk_index": idx,
        "chunk_id":    cid,
        "text":        text,
        "n_tokens_est": _tok_count(text),
    }
    if page_range:
        chunk["page_start"] = page_range[0]
        chunk["page_end"]   = page_range[1]
    return chunk
