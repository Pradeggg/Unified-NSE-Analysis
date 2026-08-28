#!/usr/bin/env python3
"""Multi-pass evidence-pack builder (FTS-only).

Runs repeated searches over company_intel.evidence_chunks with:
- pass types: broad → tighten → freshness sweeps → authority sweeps
- dimension templates from config/evidence_dimensions.yml
- optional sector overlays (banks/NBFC, infra/shipping, defence, pharma, auto)

Outputs a JSON "evidence pack" that can be fed into report generation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIMENSIONS = ROOT / "config" / "evidence_dimensions.yml"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _pg_conn():
    import psycopg2

    dsn = os.environ.get("AGENT_ADDA_PG_DSN") or os.environ.get("PG_DSN") or "dbname=nse_market user=nse_admin host=/tmp"
    return psycopg2.connect(dsn)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha1(text: str) -> str:
    return hashlib.sha1((text or "").encode("utf-8", errors="ignore")).hexdigest()


@dataclass(frozen=True)
class Dimension:
    key: str
    title: str
    category: str
    templates: list[str]


@dataclass(frozen=True)
class SectorOverlay:
    key: str
    label: str
    templates: list[str]


def load_dimension_config(path: Path) -> tuple[dict[str, Dimension], dict[str, SectorOverlay]]:
    try:
        import yaml  # PyYAML
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(f"PyYAML required to read {path}: {exc}") from exc

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    dims_raw = data.get("dimensions") or {}
    overlays_raw = data.get("sector_overlays") or {}

    dims: dict[str, Dimension] = {}
    for key, row in (dims_raw.items() if isinstance(dims_raw, dict) else []):
        if not isinstance(row, dict):
            continue
        templates = [str(t).strip() for t in (row.get("templates") or []) if str(t).strip()]
        if not templates:
            continue
        dims[str(key)] = Dimension(
            key=str(key),
            title=str(row.get("title") or key),
            category=str(row.get("category") or ""),
            templates=templates,
        )

    overlays: dict[str, SectorOverlay] = {}
    for key, row in (overlays_raw.items() if isinstance(overlays_raw, dict) else []):
        if not isinstance(row, dict):
            continue
        templates = [str(t).strip() for t in (row.get("templates") or []) if str(t).strip()]
        if not templates:
            continue
        overlays[str(key)] = SectorOverlay(
            key=str(key),
            label=str(row.get("label") or key),
            templates=templates,
        )

    return dims, overlays


def _company_aliases(conn: Any, symbol: str, *, max_aliases: int = 5) -> list[str]:
    clean = (symbol or "").strip().upper()
    if not clean:
        return []
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT alias
                FROM company_intel.company_aliases
                WHERE symbol = %s
                ORDER BY length(alias) ASC, lower(alias) ASC
                LIMIT %s
                """,
                (clean, int(max_aliases)),
            )
            return [r[0] for r in cur.fetchall() if r and r[0]]
    except Exception:
        return []


def _fts_search(
    conn: Any,
    *,
    query: str,
    symbol: str,
    include_market_wide: bool,
    source_tier_max: int,
    limit: int,
    days: int,
) -> list[dict[str, Any]]:
    q = (query or "").strip()
    if not q:
        return []
    clean_symbol = (symbol or "").strip().upper()

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
    params.append(int(source_tier_max))

    if days > 0:
        where.append("COALESCE(NULLIF(ec.evidence_date,''), NULLIF(sd.document_date,''))::date >= (CURRENT_DATE - %s)")
        params.append(int(days))

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
            ts_rank(to_tsvector('english', coalesce(ec.text,'')), websearch_to_tsquery('english', %s)) AS rank
        FROM company_intel.evidence_chunks ec
        JOIN company_intel.source_documents sd
          ON sd.document_id = ec.document_id
        WHERE {" AND ".join(where)}
        ORDER BY rank DESC, ec.source_tier ASC, ec.chunk_id DESC
        LIMIT %s
    """
    params_for_sql = [q, *params, int(limit)]

    with conn.cursor() as cur:
        cur.execute(sql, params_for_sql)
        rows = cur.fetchall()

    out = []
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
            rank,
        ) = row
        out.append(
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
            }
        )
    return out


def build_evidence_pack(
    *,
    symbol: str,
    sector_overlay: str = "",
    dimensions: list[str] | None = None,
    days_passes: list[int] | None = None,
    tier_passes: list[int] | None = None,
    limit_per_query: int = 10,
    include_market_wide: bool = True,
    config_path: str | Path = DEFAULT_DIMENSIONS,
    store_run: bool = False,
) -> dict[str, Any]:
    dims, overlays = load_dimension_config(Path(config_path))
    clean_symbol = (symbol or "").strip().upper()
    dim_keys = dimensions or list(dims.keys())
    dim_keys = [d for d in dim_keys if d in dims]
    if not dim_keys:
        return {"error": "no valid dimensions requested", "available_dimensions": sorted(dims.keys())}

    overlay_key = (sector_overlay or "").strip()
    overlay = overlays.get(overlay_key) if overlay_key else None

    days_passes = days_passes or [0, 7, 30, 90]
    tier_passes = tier_passes or [1, 2, 3, 4]
    limit_per_query = max(1, min(int(limit_per_query or 10), 25))

    conn = _pg_conn()
    conn.autocommit = True
    try:
        aliases = _company_aliases(conn, clean_symbol) if clean_symbol else []
        cos = [clean_symbol, *aliases] if clean_symbol else [""]
        cos = [c for c in cos if c]
        if not cos:
            cos = [clean_symbol] if clean_symbol else [""]

        searches_run: list[dict[str, Any]] = []
        all_results: list[dict[str, Any]] = []
        hit_dims: dict[tuple[str, int], set[str]] = {}

        for dim_key in dim_keys:
            dim = dims[dim_key]
            templates = list(dim.templates)
            if overlay is not None:
                templates.extend(overlay.templates)

            # Pass 1: broad recall (tier=4, days=0)
            for t in templates:
                for co in cos[:3]:
                    q = t.replace("{co}", co).replace("{sector}", overlay.label if overlay else "")
                    searches_run.append({"dimension": dim_key, "pass": "broad", "query": q, "days": 0, "tier_max": 4})
                    hits = _fts_search(
                        conn,
                        query=q,
                        symbol=clean_symbol,
                        include_market_wide=include_market_wide,
                        source_tier_max=4,
                        limit=limit_per_query,
                        days=0,
                    )
                    for h in hits:
                        key = (str(h.get("document_id") or ""), int(h.get("chunk_id") or 0))
                        hit_dims.setdefault(key, set()).add(dim_key)
                    all_results.extend(hits)

            # Pass 2/3/4: sweeps across freshness + authority
            for days in days_passes:
                for tier in tier_passes:
                    if days == 0 and tier == 4:
                        continue
                    for t in templates[:4]:
                        co = cos[0] if cos else ""
                        q = t.replace("{co}", co).replace("{sector}", overlay.label if overlay else "")
                        searches_run.append({"dimension": dim_key, "pass": "sweep", "query": q, "days": int(days), "tier_max": int(tier)})
                        hits = _fts_search(
                            conn,
                            query=q,
                            symbol=clean_symbol,
                            include_market_wide=include_market_wide,
                            source_tier_max=int(tier),
                            limit=max(5, limit_per_query // 2),
                            days=int(days),
                        )
                        for h in hits:
                            key = (str(h.get("document_id") or ""), int(h.get("chunk_id") or 0))
                            hit_dims.setdefault(key, set()).add(dim_key)
                        all_results.extend(hits)
    finally:
        conn.close()

    # Dedupe by (document_id, chunk_id) and keep best rank
    seen: set[tuple[str, int]] = set()
    deduped: list[dict[str, Any]] = []
    for r in sorted(all_results, key=lambda x: (x.get("source_tier", 9), -float(x.get("rank", 0.0)))):  # type: ignore[arg-type]
        key = (str(r.get("document_id") or ""), int(r.get("chunk_id") or 0))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(r)

    # Secondary dedupe by snippet hash (avoid duplicates across multiple queries)
    seen_snip: set[str] = set()
    final: list[dict[str, Any]] = []
    for r in deduped:
        h = _sha1(str(r.get("snippet") or ""))
        if h in seen_snip:
            continue
        seen_snip.add(h)
        final.append(r)

    # Split by tier sections for report-friendly use
    by_tier: dict[str, list[dict[str, Any]]] = {"tier1_primary": [], "tier2_semiprimary": [], "tier3_secondary": [], "tier4_opinion": []}
    for r in final:
        tier = int(r.get("source_tier") or 4)
        if tier <= 1:
            by_tier["tier1_primary"].append(r)
        elif tier == 2:
            by_tier["tier2_semiprimary"].append(r)
        elif tier == 3:
            by_tier["tier3_secondary"].append(r)
        else:
            by_tier["tier4_opinion"].append(r)

    dim_counts: dict[str, int] = {k: 0 for k in dim_keys}
    for r in final:
        key = (str(r.get("document_id") or ""), int(r.get("chunk_id") or 0))
        for dim_key in hit_dims.get(key, set()):
            if dim_key in dim_counts:
                dim_counts[dim_key] += 1

    payload = {
        "as_of": _now_iso(),
        "symbol": clean_symbol,
        "aliases_used": aliases[:5] if clean_symbol else [],
        "sector_overlay": overlay_key,
        "dimensions": dim_keys,
        "searches_run": searches_run,
        "dimension_counts": dim_counts,
        "counts": {k: len(v) for k, v in by_tier.items()},
        "results": by_tier,
    }

    if store_run:
        try:
            conn = _pg_conn()
            conn.autocommit = False
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO company_intel.evidence_pack_runs
                            (symbol, sector_overlay, dimensions, searches_run, result_chunk_ids, result_counts, dimension_counts, params)
                        VALUES
                            (%s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb)
                        RETURNING run_id
                        """,
                        (
                            clean_symbol,
                            overlay_key,
                            json.dumps(dim_keys),
                            json.dumps(searches_run),
                            json.dumps([int(r.get("chunk_id") or 0) for r in final]),
                            json.dumps(payload["counts"]),
                            json.dumps(dim_counts),
                            json.dumps(
                                {
                                    "days_passes": days_passes,
                                    "tier_passes": tier_passes,
                                    "limit_per_query": limit_per_query,
                                    "include_market_wide": include_market_wide,
                                    "config_path": str(config_path),
                                }
                            ),
                        ),
                    )
                    run_id = int(cur.fetchone()[0])
                conn.commit()
                payload["stored_run_id"] = run_id
            finally:
                conn.close()
        except Exception as exc:
            payload["store_error"] = str(exc)

    return payload


def main() -> None:
    ap = argparse.ArgumentParser(prog="build_evidence_pack.py")
    ap.add_argument("--symbol", required=True, help="NSE symbol (e.g., HDFCBANK)")
    ap.add_argument("--sector-overlay", default="", help="Overlay key (banks_nbfc, infra_shipping, defence, pharma, auto)")
    ap.add_argument("--dimensions", default="", help="Comma-separated dimension keys (default: all)")
    ap.add_argument("--days-passes", default="0,7,30,90", help="Comma-separated freshness passes (default: 0,7,30,90)")
    ap.add_argument("--tier-passes", default="1,2,3,4", help="Comma-separated tier passes (default: 1,2,3,4)")
    ap.add_argument("--limit-per-query", type=int, default=10, help="Max results per query (default 10)")
    ap.add_argument("--no-market-wide", dest="include_market_wide", action="store_false", help="Exclude symbol='' evidence")
    ap.add_argument("--config", default=str(DEFAULT_DIMENSIONS), help="Path to evidence_dimensions.yml")
    ap.add_argument("--store-run", action="store_true", help="Persist the retrieval run to company_intel.evidence_pack_runs")
    args = ap.parse_args()

    dims = [d.strip() for d in (args.dimensions or "").split(",") if d.strip()] or None
    days = [int(x) for x in str(args.days_passes).split(",") if x.strip().isdigit()]
    tiers = [int(x) for x in str(args.tier_passes).split(",") if x.strip().isdigit()]

    out = build_evidence_pack(
        symbol=args.symbol,
        sector_overlay=args.sector_overlay,
        dimensions=dims,
        days_passes=days,
        tier_passes=tiers,
        limit_per_query=int(args.limit_per_query),
        include_market_wide=bool(args.include_market_wide),
        config_path=args.config,
        store_run=bool(args.store_run),
    )
    print(json.dumps(out, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
