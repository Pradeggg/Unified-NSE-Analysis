#!/usr/bin/env python3
"""Evidence search (FTS-only) over company_intel.evidence_chunks.

Returns an "evidence pack" style JSON payload suitable for report generation.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _pg_conn():
    import psycopg2

    dsn = os.environ.get("AGENT_ADDA_PG_DSN") or os.environ.get("PG_DSN") or "dbname=nse_market user=nse_admin host=/tmp"
    return psycopg2.connect(dsn)


def search_evidence(
    query: str,
    *,
    symbol: str = "",
    include_market_wide: bool = True,
    source_tier_max: int = 4,
    limit: int = 12,
    days: int = 0,
) -> dict[str, Any]:
    q = (query or "").strip()
    if not q:
        return {"error": "query is required"}

    clean_symbol = (symbol or "").strip().upper()
    tier_max = max(1, min(int(source_tier_max or 4), 4))
    lim = max(1, min(int(limit or 12), 50))
    day_window = max(0, min(int(days or 0), 365))

    where = ["to_tsvector('english', coalesce(ec.text,'')) @@ websearch_to_tsquery('english', %s)"]
    params: list[Any] = [q]

    if clean_symbol:
        if include_market_wide:
            where.append("(ec.symbol = %s OR ec.symbol = '')")
            params.append(clean_symbol)
        else:
            where.append("ec.symbol = %s")
            params.append(clean_symbol)

    where.append("ec.source_tier <= %s")
    params.append(int(tier_max))

    if day_window > 0:
        where.append(
            "COALESCE(NULLIF(ec.evidence_date,''), NULLIF(sd.document_date,''))::date >= (CURRENT_DATE - %s)"
        )
        params.append(int(day_window))

    sql = f"""
        SELECT
            ec.chunk_id,
            ec.document_id,
            ec.symbol,
            ec.category,
            ec.source_tier,
            ec.evidence_date,
            left(ec.text, 1200) AS snippet,
            sd.source_name,
            sd.source_url,
            sd.document_type,
            sd.document_date,
            sd.metadata,
            ts_rank(to_tsvector('english', coalesce(ec.text,'')), websearch_to_tsquery('english', %s)) AS rank
        FROM company_intel.evidence_chunks ec
        JOIN company_intel.source_documents sd
          ON sd.document_id = ec.document_id
        WHERE {" AND ".join(where)}
        ORDER BY rank DESC, ec.source_tier ASC, ec.chunk_id DESC
        LIMIT %s
    """
    params_for_sql = [q, *params, int(lim)]

    conn = _pg_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params_for_sql)
            rows = cur.fetchall()
    finally:
        conn.close()

    results = []
    for row in rows:
        (
            chunk_id,
            document_id,
            row_symbol,
            category,
            source_tier,
            evidence_date,
            snippet,
            source_name,
            source_url,
            document_type,
            document_date,
            metadata,
            rank,
        ) = row
        results.append(
            {
                "chunk_id": int(chunk_id),
                "document_id": str(document_id),
                "symbol": str(row_symbol),
                "category": str(category),
                "source_tier": int(source_tier),
                "evidence_date": str(evidence_date or ""),
                "document_date": str(document_date or ""),
                "document_type": str(document_type or ""),
                "source_name": str(source_name or ""),
                "source_url": str(source_url or ""),
                "snippet": str(snippet or ""),
                "rank": float(rank or 0.0),
                "metadata": metadata if isinstance(metadata, dict) else metadata,
            }
        )

    return {
        "query": q,
        "symbol": clean_symbol,
        "include_market_wide": bool(include_market_wide),
        "source_tier_max": tier_max,
        "days": day_window,
        "limit": lim,
        "results": results,
        "count": len(results),
    }


def main() -> None:
    ap = argparse.ArgumentParser(prog="search_evidence.py")
    ap.add_argument("query", help="FTS query (natural language)")
    ap.add_argument("--symbol", default="", help="Optional NSE symbol filter")
    ap.add_argument("--no-market-wide", dest="include_market_wide", action="store_false", help="Exclude symbol='' evidence")
    ap.add_argument("--source-tier-max", type=int, default=4, help="Max source tier (1–4)")
    ap.add_argument("--limit", type=int, default=12, help="Max passages (1–50)")
    ap.add_argument("--days", type=int, default=0, help="Restrict to last N days (0–365)")
    args = ap.parse_args()

    out = search_evidence(
        args.query,
        symbol=args.symbol,
        include_market_wide=bool(args.include_market_wide),
        source_tier_max=int(args.source_tier_max),
        limit=int(args.limit),
        days=int(args.days),
    )
    print(json.dumps(out, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
