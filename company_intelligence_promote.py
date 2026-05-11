"""Promotion of indexed company website/doc content into X-Ray evidence."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Callable

from company_intelligence_extract import classify_evidence_text, store_evidence_chunk
from financial_filing_agent import parse_pdf_filing


DEFAULT_PROMOTION_CATEGORIES = {
    "business model",
    "customer base",
    "operating model",
    "market share",
    "competitor list",
    "competitive advantage",
    "sector structure",
    "risks",
}


def promote_indexed_company_evidence(
    conn: sqlite3.Connection,
    symbol: str,
    parse_documents: bool = True,
    pdf_parser: Callable[[Path], dict] | None = None,
    max_website_chunks: int = 25,
    max_document_pages: int = 25,
) -> dict:
    clean_symbol = symbol.strip().upper()
    website_count = _promote_website_chunks(conn, clean_symbol, max_website_chunks)
    documents_parsed = 0
    document_count = 0
    document_errors = 0
    if parse_documents:
        parser = pdf_parser or parse_pdf_filing
        doc_result = _promote_source_documents(conn, clean_symbol, parser, max_document_pages)
        documents_parsed = doc_result["documents_parsed"]
        document_count = doc_result["document_chunks_promoted"]
        document_errors = doc_result["document_errors"]
    return {
        "symbol": clean_symbol,
        "website_chunks_promoted": website_count,
        "documents_parsed": documents_parsed,
        "document_chunks_promoted": document_count,
        "document_errors": document_errors,
    }


def load_indexed_evidence_records(conn: sqlite3.Connection, symbol: str) -> list[dict]:
    rows = conn.execute(
        """
        SELECT chunk_id, document_id, symbol, category, text, page_number, table_id,
               source_tier, confidence, evidence_date
        FROM evidence_chunks
        WHERE symbol = ?
        ORDER BY chunk_id
        """,
        (symbol.strip().upper(),),
    ).fetchall()
    keys = [
        "chunk_id",
        "document_id",
        "symbol",
        "category",
        "text",
        "page_number",
        "table_id",
        "source_tier",
        "confidence",
        "evidence_date",
    ]
    return [dict(zip(keys, row)) for row in rows]


def _promote_website_chunks(conn: sqlite3.Connection, symbol: str, limit: int) -> int:
    rows = conn.execute(
        """
        SELECT chunk_id, page_id, url, chunk_text, category
        FROM website_page_chunks
        WHERE symbol = ?
        ORDER BY chunk_id
        LIMIT ?
        """,
        (symbol, int(limit)),
    ).fetchall()
    promoted = 0
    for chunk_id, page_id, _url, text, stored_category in rows:
        category = _best_category(text, stored_category)
        if category == "uncategorized":
            continue
        document_id = f"website_page:{page_id}"
        if _evidence_exists(conn, symbol, document_id, text):
            continue
        store_evidence_chunk(
            conn,
            document_id=document_id,
            symbol=symbol,
            category=category,
            text=text,
            source_tier=1,
            confidence=0.75,
            table_id=f"website_chunk:{chunk_id}",
        )
        promoted += 1
    return promoted


def _promote_source_documents(
    conn: sqlite3.Connection,
    symbol: str,
    parser: Callable[[Path], dict],
    max_pages: int,
) -> dict:
    rows = conn.execute(
        """
        SELECT document_id, local_path
        FROM source_documents
        WHERE symbol = ? AND fetch_status = 'ok' AND local_path != ''
        ORDER BY created_at
        """,
        (symbol,),
    ).fetchall()
    parsed = 0
    promoted = 0
    errors = 0
    for document_id, local_path in rows:
        path = Path(local_path)
        if not path.exists():
            _update_parse_status(conn, document_id, "error", "local file missing")
            errors += 1
            continue
        result = parser(path)
        if result.get("status") not in {"ok", "partial"}:
            _update_parse_status(conn, document_id, "error", result.get("error", "parse failed"))
            errors += 1
            continue
        parsed += 1
        page_count = 0
        for page in result.get("pages", []):
            if page_count >= int(max_pages):
                break
            text = str(page.get("text", "")).strip()
            if not text:
                continue
            category = _best_category(text, "")
            if category == "uncategorized":
                continue
            if _evidence_exists(conn, symbol, document_id, text):
                continue
            store_evidence_chunk(
                conn,
                document_id=document_id,
                symbol=symbol,
                category=category,
                text=text,
                page_number=page.get("page_number"),
                source_tier=1,
                confidence=0.82,
            )
            promoted += 1
            page_count += 1
        _update_parse_status(conn, document_id, "parsed", "")
    return {"documents_parsed": parsed, "document_chunks_promoted": promoted, "document_errors": errors}


def _best_category(text: str, stored_category: str) -> str:
    categories = [category for category in classify_evidence_text(text) if category in DEFAULT_PROMOTION_CATEGORIES]
    if categories:
        return categories[0]
    if stored_category in DEFAULT_PROMOTION_CATEGORIES:
        return stored_category
    return "uncategorized"


def _evidence_exists(conn: sqlite3.Connection, symbol: str, document_id: str, text: str) -> bool:
    row = conn.execute(
        """
        SELECT 1 FROM evidence_chunks
        WHERE symbol = ? AND document_id = ? AND text = ?
        LIMIT 1
        """,
        (symbol, document_id, text),
    ).fetchone()
    return row is not None


def _update_parse_status(conn: sqlite3.Connection, document_id: str, status: str, failure_reason: str) -> None:
    conn.execute(
        """
        UPDATE source_documents
        SET parse_status = ?, failure_reason = ?
        WHERE document_id = ?
        """,
        (status, failure_reason, document_id),
    )
    conn.commit()
