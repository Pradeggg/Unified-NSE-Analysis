#!/usr/bin/env python3
"""
SQLite persistence for Ollama-generated market and stock narratives.

Table: llm_narratives — one row per (narrative_type, analysis_date, symbol).
Market narratives use symbol = '' (empty string).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

# Project root (python/core -> ../..)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "nse_analysis.db"

# Idempotent DDL — keep in sync with initialize_database() in fixed_nse_universe_analysis.py
LLM_NARRATIVES_DDL = """
CREATE TABLE IF NOT EXISTS llm_narratives (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    narrative_type TEXT NOT NULL CHECK (narrative_type IN ('market', 'stock')),
    analysis_date TEXT NOT NULL,
    symbol TEXT NOT NULL DEFAULT '',
    ollama_model TEXT NOT NULL,
    content TEXT NOT NULL,
    context_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(narrative_type, analysis_date, symbol)
);
"""


def _iso(d: date | str) -> str:
    if isinstance(d, date):
        return d.isoformat()
    return str(d)[:10]


def ensure_narratives_schema(conn: sqlite3.Connection) -> None:
    """Create llm_narratives if missing (safe for existing DBs)."""
    conn.executescript(LLM_NARRATIVES_DDL)
    conn.commit()


def connect_db(db_path: Optional[Path] = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path else DEFAULT_DB_PATH
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    ensure_narratives_schema(conn)
    return conn


def get_latest_analysis_date(conn: sqlite3.Connection) -> Optional[str]:
    """Most recent analysis_date from stocks_analysis (authoritative for dashboard as-of)."""
    try:
        row = conn.execute("SELECT MAX(analysis_date) AS m FROM stocks_analysis").fetchone()
        if row and row["m"] is not None:
            return str(row["m"])[:10]
    except sqlite3.Error:
        pass
    return None


def get_narrative(
    conn: sqlite3.Connection,
    narrative_type: str,
    analysis_date: str | date,
    symbol: str = "",
) -> Optional[dict[str, Any]]:
    """
    Return stored narrative row as dict, or None.
    narrative_type: 'market' | 'stock'
    symbol: NSE symbol uppercased; use '' for market.
    """
    ad = _iso(analysis_date)
    sym = (symbol or "").strip().upper()
    if narrative_type not in ("market", "stock"):
        raise ValueError("narrative_type must be 'market' or 'stock'")
    row = conn.execute(
        """
        SELECT id, narrative_type, analysis_date, symbol, ollama_model, content, context_json,
               created_at, updated_at
        FROM llm_narratives
        WHERE narrative_type = ? AND analysis_date = ? AND symbol = ?
        """,
        (narrative_type, ad, sym),
    ).fetchone()
    if row is None:
        return None
    return {
        "id": row["id"],
        "narrative_type": row["narrative_type"],
        "analysis_date": row["analysis_date"],
        "symbol": row["symbol"],
        "ollama_model": row["ollama_model"],
        "content": row["content"],
        "context_json": row["context_json"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def upsert_narrative(
    conn: sqlite3.Connection,
    narrative_type: str,
    analysis_date: str | date,
    symbol: str,
    ollama_model: str,
    content: str,
    context_obj: Optional[dict[str, Any]] = None,
) -> None:
    """Insert or replace narrative for (type, date, symbol)."""
    ad = _iso(analysis_date)
    sym = (symbol or "").strip().upper()
    if narrative_type not in ("market", "stock"):
        raise ValueError("narrative_type must be 'market' or 'stock'")
    now = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    ctx = json.dumps(context_obj, ensure_ascii=False, default=str) if context_obj is not None else None

    existing = get_narrative(conn, narrative_type, ad, sym)
    if existing is None:
        conn.execute(
            """
            INSERT INTO llm_narratives
            (narrative_type, analysis_date, symbol, ollama_model, content, context_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (narrative_type, ad, sym, ollama_model, content, ctx, now, now),
        )
    else:
        conn.execute(
            """
            UPDATE llm_narratives
            SET ollama_model = ?, content = ?, context_json = ?, updated_at = ?
            WHERE narrative_type = ? AND analysis_date = ? AND symbol = ?
            """,
            (ollama_model, content, ctx, now, narrative_type, ad, sym),
        )
    conn.commit()


def list_narratives_for_date(
    conn: sqlite3.Connection,
    analysis_date: str | date,
    narrative_type: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Optional helper: all narratives for an analysis date."""
    ad = _iso(analysis_date)
    if narrative_type:
        rows = conn.execute(
            "SELECT * FROM llm_narratives WHERE analysis_date = ? AND narrative_type = ? ORDER BY symbol",
            (ad, narrative_type),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM llm_narratives WHERE analysis_date = ? ORDER BY narrative_type, symbol",
            (ad,),
        ).fetchall()
    return [dict(r) for r in rows]
