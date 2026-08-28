#!/usr/bin/env python3
"""Ingest company filings into company_intel evidence store (Tier 1, FTS-only).

Pipeline:
  1) Discover candidate filing URLs (NSE/BSE/Screener) via terminal.results_tools
  2) Download/register artifacts via financial_filing_agent.ingest_filing_url
  3) Store document metadata in company_intel.source_documents
  4) Chunk local PDF/HTML and store passages in company_intel.evidence_chunks
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _pg_conn():
    import psycopg2

    dsn = os.environ.get("AGENT_ADDA_PG_DSN") or os.environ.get("PG_DSN") or "dbname=nse_market user=nse_admin host=/tmp"
    return psycopg2.connect(dsn)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tier_confidence(tier: int) -> float:
    if tier <= 1:
        return 0.8
    if tier == 2:
        return 0.7
    if tier == 3:
        return 0.6
    return 0.5


def _doc_id(prefix: str, sha256: str) -> str:
    clean = (sha256 or "").strip()
    return f"{prefix}_{clean[:32]}" if clean else f"{prefix}_unknown"


def _chunk_local(path: Path, *, source_id: str, source_name: str, category: str, tier: int, url: str, fetched_date: str) -> list[dict[str, Any]]:
    from knowledge_base.chunker import chunk_document

    kind = "pdf" if path.suffix.lower() == ".pdf" else "html"
    manifest_row = {
        "path": str(path),
        "kind": kind,
        "source_id": source_id,
        "source_name": source_name,
        "category": category,
        "tier": tier,
        "hub_label": category,
        "url": url,
        "fetched_date": fetched_date,
    }
    return list(chunk_document(manifest_row))


def ingest_company_filings(
    *,
    symbol: str,
    max_docs: int = 3,
    period: str = "latest_results",
    force_download: bool = False,
    dry_run: bool = False,
    root_dir: str | Path = "data/filings_evidence",
) -> dict[str, Any]:
    from terminal.results_tools import discover_financial_filings
    from financial_filing_agent import ingest_filing_url

    sym = (symbol or "").strip().upper()
    if not sym:
        return {"error": "symbol is required"}

    discovered_at = _now_iso()
    discovery = discover_financial_filings(sym, max_results=max(10, int(max_docs) * 5))
    candidates = list(discovery.get("candidates") or [])

    picked: list[dict[str, Any]] = []
    for c in candidates:
        url = str(c.get("url") or "").strip()
        if not url:
            continue
        picked.append(c)
        if len(picked) >= max(1, int(max_docs)):
            break

    if dry_run:
        return {
            "status": "dry_run",
            "symbol": sym,
            "picked": [{"title": p.get("title"), "url": p.get("url"), "source": p.get("source"), "score": p.get("score")} for p in picked],
            "discovery_status": discovery.get("status"),
            "source_trail": discovery.get("source_trail"),
            "discovered_at": discovered_at,
        }

    conn = _pg_conn()
    conn.autocommit = False
    stats = {
        "symbol": sym,
        "picked": len(picked),
        "documents_inserted": 0,
        "documents_skipped": 0,
        "chunks_inserted": 0,
        "errors": [],
        "discovery_status": discovery.get("status"),
        "source_trail": discovery.get("source_trail"),
        "discovered_at": discovered_at,
    }

    try:
        for c in picked:
            title = str(c.get("title") or "").strip()
            url = str(c.get("url") or "").strip()
            source = str(c.get("source") or "").strip()
            score = int(c.get("score") or 0)

            manifest = ingest_filing_url(url, symbol=sym, period=period, root_dir=Path(root_dir), force=bool(force_download))
            if manifest.get("status") != "ok":
                stats["errors"].append({"url": url, "title": title, "error": manifest.get("error")})
                continue

            sha256 = str(manifest.get("sha256") or "").strip()
            local_path = Path(str(manifest.get("local_path") or ""))
            if not sha256 or not local_path.exists():
                stats["errors"].append({"url": url, "title": title, "error": "missing sha256 or local file"})
                continue

            document_id = _doc_id("filing", sha256)
            document_date = str((c.get("raw") or {}).get("date") or (c.get("raw") or {}).get("published") or "").strip()
            meta = {
                "title": title,
                "source": source,
                "score": score,
                "rank": c.get("rank"),
                "discovered_at": discovered_at,
                "manifest_path": str(manifest.get("manifest_path") or ""),
                "fetched_at": str(manifest.get("fetched_at") or ""),
                "candidate": c,
            }

            inserted = False
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO company_intel.source_documents
                            (document_id, symbol, source_tier, source_name, source_url, document_type,
                             document_date, local_path, content_hash, fetch_status, parse_status, failure_reason, metadata)
                        VALUES
                            (%s, %s, %s, %s, %s, %s,
                             %s, %s, %s, %s, %s, %s, %s::jsonb)
                        ON CONFLICT (document_id) DO NOTHING
                        """,
                        (
                            document_id,
                            sym,
                            1,
                            f"{sym} filing ({source or 'unknown'})",
                            url,
                            "filing_pdf",
                            document_date,
                            str(local_path),
                            sha256,
                            "ok",
                            "downloaded",
                            "",
                            json.dumps(meta, ensure_ascii=False),
                        ),
                    )
                    inserted = cur.rowcount > 0
                conn.commit()
            except Exception as exc:
                conn.rollback()
                stats["errors"].append({"url": url, "title": title, "error": str(exc)})
                continue

            if not inserted:
                stats["documents_skipped"] += 1
                continue

            stats["documents_inserted"] += 1

            try:
                chunks = _chunk_local(
                    local_path,
                    source_id=document_id,
                    source_name=f"{sym} filing ({source or 'unknown'})",
                    category="filing",
                    tier=1,
                    url=url,
                    fetched_date=str(manifest.get("fetched_at") or ""),
                )
                if not chunks:
                    chunks = [
                        {
                            "text": (title + "\n" + url).strip(),
                            "page_start": None,
                            "page_end": None,
                        }
                    ]

                with conn.cursor() as cur:
                    for ch in chunks:
                        text = str(ch.get("text") or "").strip()
                        if not text:
                            continue
                        p1 = ch.get("page_start")
                        p2 = ch.get("page_end")
                        table_id = ""
                        page_number = None
                        if isinstance(p1, int) and isinstance(p2, int):
                            page_number = p1
                            table_id = f"p{p1}-{p2}"
                        cur.execute(
                            """
                            INSERT INTO company_intel.evidence_chunks
                                (document_id, symbol, category, text, page_number, table_id, source_tier, confidence, evidence_date)
                            VALUES
                                (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                            """,
                            (
                                document_id,
                                sym,
                                "filing",
                                text,
                                page_number,
                                table_id,
                                1,
                                float(_tier_confidence(1)),
                                document_date,
                            ),
                        )
                        stats["chunks_inserted"] += 1
                conn.commit()
            except Exception as exc:
                conn.rollback()
                stats["errors"].append({"document_id": document_id, "url": url, "error": str(exc)})

        return {"status": "ok", **stats}
    finally:
        conn.close()


def main() -> None:
    ap = argparse.ArgumentParser(prog="ingest_company_filings.py")
    ap.add_argument("--symbol", required=True, help="NSE symbol (e.g., HDFCBANK)")
    ap.add_argument("--max-docs", type=int, default=3)
    ap.add_argument("--period", default="latest_results")
    ap.add_argument("--force-download", action="store_true")
    ap.add_argument("--root-dir", default="data/filings_evidence")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    out = ingest_company_filings(
        symbol=str(args.symbol),
        max_docs=int(args.max_docs),
        period=str(args.period),
        force_download=bool(args.force_download),
        dry_run=bool(args.dry_run),
        root_dir=str(args.root_dir),
    )
    print(json.dumps(out, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()

