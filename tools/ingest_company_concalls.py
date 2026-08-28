#!/usr/bin/env python3
"""Ingest company concall transcript PDFs into company_intel evidence store (Tier 1, FTS-only).

Source: Screener.in concalls list (ppt_url links typically point to transcript/investor-presentation PDFs).
Stores:
  - company_intel.source_documents (concall_pdf)
  - company_intel.evidence_chunks (category=concall; chunked from local PDF)
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


def ingest_company_concalls(
    *,
    symbol: str,
    max_docs: int = 3,
    force_download: bool = False,
    dry_run: bool = False,
    root_dir: str | Path = "data/concall_evidence",
) -> dict[str, Any]:
    from terminal.web_research import scrape_screener_in
    from financial_filing_agent import ingest_filing_url

    sym = (symbol or "").strip().upper()
    if not sym:
        return {"error": "symbol is required"}

    discovered_at = _now_iso()
    sc = scrape_screener_in(sym) or {}
    concalls = list(sc.get("concalls") or [])
    concalls_link = str(sc.get("concalls_link") or f"https://www.screener.in/company/{sym}/#concalls")

    picked: list[dict[str, Any]] = []
    for row in concalls:
        url = str(row.get("ppt_url") or "").strip()
        period = str(row.get("period") or "").strip()
        if not url:
            continue
        picked.append({"period": period, "url": url})
        if len(picked) >= max(1, int(max_docs)):
            break

    if dry_run:
        return {
            "status": "dry_run",
            "symbol": sym,
            "picked": picked,
            "concalls_link": concalls_link,
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
        "concalls_link": concalls_link,
        "discovered_at": discovered_at,
    }

    try:
        for item in picked:
            period = str(item.get("period") or "").strip()
            url = str(item.get("url") or "").strip()
            if not url:
                continue

            manifest = ingest_filing_url(url, symbol=sym, period=period or "latest", root_dir=Path(root_dir), force=bool(force_download))
            if manifest.get("status") != "ok":
                stats["errors"].append({"url": url, "period": period, "error": manifest.get("error")})
                continue

            sha256 = str(manifest.get("sha256") or "").strip()
            local_path = Path(str(manifest.get("local_path") or ""))
            if not sha256 or not local_path.exists():
                stats["errors"].append({"url": url, "period": period, "error": "missing sha256 or local file"})
                continue

            document_id = _doc_id("concall", sha256)
            meta = {
                "period": period,
                "concalls_link": concalls_link,
                "discovered_at": discovered_at,
                "manifest_path": str(manifest.get("manifest_path") or ""),
                "fetched_at": str(manifest.get("fetched_at") or ""),
                "source": "screener_in",
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
                            f"{sym} concall {period}".strip(),
                            url,
                            "concall_pdf",
                            "",
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
                stats["errors"].append({"url": url, "period": period, "error": str(exc)})
                continue

            if not inserted:
                stats["documents_skipped"] += 1
                continue

            stats["documents_inserted"] += 1

            try:
                chunks = _chunk_local(
                    local_path,
                    source_id=document_id,
                    source_name=f"{sym} concall {period}".strip(),
                    category="concall",
                    tier=1,
                    url=url,
                    fetched_date=str(manifest.get("fetched_at") or ""),
                )
                if not chunks:
                    chunks = [
                        {
                            "text": (f"{sym} concall {period}\n{url}").strip(),
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
                                "concall",
                                text,
                                page_number,
                                table_id,
                                1,
                                float(_tier_confidence(1)),
                                "",
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
    ap = argparse.ArgumentParser(prog="ingest_company_concalls.py")
    ap.add_argument("--symbol", required=True, help="NSE symbol (e.g., HDFCBANK)")
    ap.add_argument("--max-docs", type=int, default=3)
    ap.add_argument("--force-download", action="store_true")
    ap.add_argument("--root-dir", default="data/concall_evidence")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    out = ingest_company_concalls(
        symbol=str(args.symbol),
        max_docs=int(args.max_docs),
        force_download=bool(args.force_download),
        dry_run=bool(args.dry_run),
        root_dir=str(args.root_dir),
    )
    print(json.dumps(out, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()

