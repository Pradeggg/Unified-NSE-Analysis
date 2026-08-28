"""Evidence storage and deterministic categorization for Company X-Ray."""

from __future__ import annotations

import sqlite3
from typing import Any


CATEGORY_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("business model", ("business model", "revenue model", "value retail", "subscription", "distribution model")),
    ("revenue segments", ("segment", "revenue mix", "sales mix", "product line")),
    ("customer base", ("customer", "client", "clients", "bfsi", "retail clients", "consumer base")),
    ("client concentration", ("client concentration", "top customer", "largest customer")),
    ("operating model", ("same store", "store addition", "new store", "capacity", "network", "operating model")),
    ("market share", ("market share", "organized", "share increased", "share declined")),
    ("competitor list", ("competitor", "competition", "peer", "rival")),
    ("competitive advantage", ("moat", "advantage", "pricing power", "switching cost", "brand")),
    ("RBI monetary policy sensitivity", ("repo rate", "monetary policy", "rbi", "borrowing cost", "interest rate")),
    ("Union Budget sensitivity", ("budget", "capex allocation", "tax relief", "infrastructure demand")),
    ("commodity/input sensitivity", ("commodity", "raw material", "input cost", "crude", "steel", "cotton")),
    ("risks", ("risk", "headwind", "litigation", "regulatory", "slowdown")),
]


def store_evidence_chunk(
    conn: sqlite3.Connection,
    document_id: str,
    symbol: str,
    category: str,
    text: str,
    source_tier: int,
    confidence: float,
    page_number: int | None = None,
    table_id: str = "",
    evidence_date: str = "",
) -> int:
    cur = conn.execute(
        """
        INSERT INTO evidence_chunks
            (document_id, symbol, category, text, page_number, table_id, source_tier, confidence, evidence_date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            document_id,
            symbol.strip().upper(),
            category,
            text,
            page_number,
            table_id,
            int(source_tier),
            float(confidence),
            evidence_date,
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def list_evidence_by_symbol(
    conn: sqlite3.Connection,
    symbol: str,
    category: str | None = None,
) -> list[dict[str, Any]]:
    params: list[Any] = [symbol.strip().upper()]
    where = "WHERE symbol = ?"
    if category:
        where += " AND category = ?"
        params.append(category)

    rows = conn.execute(
        f"""
        SELECT chunk_id, document_id, symbol, category, text, page_number, table_id,
               source_tier, confidence, evidence_date
        FROM evidence_chunks
        {where}
        ORDER BY chunk_id
        """,
        params,
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


def classify_evidence_text(text: str) -> list[str]:
    lowered = text.lower()
    categories = [
        category
        for category, keywords in CATEGORY_KEYWORDS
        if any(keyword in lowered for keyword in keywords)
    ]
    return categories or ["uncategorized"]
