"""Scheduled/stale company website index job."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

from company_index_command import DEFAULT_DB_PATH, run_company_index
from company_intelligence_db import init_company_intelligence_db


def run_company_index_job(
    symbols: list[str],
    stale_days: int = 30,
    max_companies: int = 25,
    refresh: bool = False,
    db_path: str | Path = DEFAULT_DB_PATH,
    include_documents: bool = True,
    document_limit: int = 10,
    max_pages: int = 10,
    respect_robots: bool = True,
    seed_sitemap: bool = True,
    index_runner: Callable[..., dict] = run_company_index,
) -> dict:
    clean_symbols = _dedupe_symbols(symbols)
    db = init_company_intelligence_db(db_path)

    with sqlite3.connect(db) as conn:
        candidates, skipped = _select_stale_symbols(conn, clean_symbols, stale_days, refresh)

    selected = candidates[: max(0, int(max_companies))]
    deferred = candidates[len(selected) :]
    succeeded: list[str] = []
    failed: list[dict] = []
    results: list[dict] = []

    for symbol in selected:
        try:
            result = index_runner(
                symbol,
                db_path=db,
                refresh=refresh,
                include_documents=include_documents,
                document_limit=document_limit,
                max_pages=max_pages,
                respect_robots=respect_robots,
                seed_sitemap=seed_sitemap,
            )
            succeeded.append(symbol)
            results.append(result)
        except Exception as exc:
            error = str(exc)
            failed.append({"symbol": symbol, "error": error})
            _record_failed_crawl(db, symbol, error)

    return {
        "db_path": str(db),
        "requested": clean_symbols,
        "processed": len(selected),
        "succeeded": succeeded,
        "failed": failed,
        "skipped": skipped,
        "deferred": deferred,
        "results": results,
    }


def _dedupe_symbols(symbols: list[str]) -> list[str]:
    seen: set[str] = set()
    clean: list[str] = []
    for symbol in symbols:
        normalized = str(symbol or "").strip().upper()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        clean.append(normalized)
    return clean


def _select_stale_symbols(
    conn: sqlite3.Connection,
    symbols: list[str],
    stale_days: int,
    refresh: bool,
) -> tuple[list[str], list[str]]:
    if refresh:
        return symbols, []
    cutoff = datetime.now() - timedelta(days=int(stale_days))
    candidates: list[str] = []
    skipped: list[str] = []
    for symbol in symbols:
        latest = conn.execute(
            """
            SELECT completed_at, status
            FROM website_crawl_runs
            WHERE symbol = ?
            ORDER BY COALESCE(NULLIF(completed_at, ''), started_at) DESC, crawl_run_id DESC
            LIMIT 1
            """,
            (symbol,),
        ).fetchone()
        if latest is None:
            candidates.append(symbol)
            continue
        completed_at, status = latest
        if str(status).lower() != "completed":
            candidates.append(symbol)
            continue
        completed_dt = _parse_sqlite_datetime(str(completed_at or ""))
        if completed_dt is None or completed_dt < cutoff:
            candidates.append(symbol)
        else:
            skipped.append(symbol)
    return candidates, skipped


def _record_failed_crawl(db_path: Path, symbol: str, failure_reason: str) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO website_crawl_runs
                (symbol, base_url, completed_at, status, failure_reason)
            VALUES (?, '', CURRENT_TIMESTAMP, 'failed', ?)
            """,
            (symbol, failure_reason),
        )
        conn.commit()


def _parse_sqlite_datetime(value: str) -> datetime | None:
    clean = value.strip().replace("Z", "")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(clean, fmt)
        except ValueError:
            continue
    return None
