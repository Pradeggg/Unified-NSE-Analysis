#!/usr/bin/env python3
"""
Download the full NSE equity indices catalog from the official API and save CSV + JSON.

Source: GET https://www.nseindia.com/api/allIndices (same data as Market Data → All Indices).

Categories on NSE (field ``key``):
  - BROAD MARKET INDICES
  - SECTORAL INDICES
  - THEMATIC INDICES
  - STRATEGY INDICES
  - FIXED INCOME INDICES
  - INDICES ELIGIBLE IN DERIVATIVES (subset overlap; tagged separately)

Outputs (default project ``data/``):
  - nse_indices_catalog.csv   — columns for filtering & joining in analysis
  - nse_indices_catalog.json  — raw API snapshot (optional)

Use in analysis:
  - Filter ``is_thematic == True`` for thematic-only work; ``category_code == BROAD`` for benchmarks.
  - ``api_index_name`` is the value to pass to ``/api/equity-stockIndices?index=...`` where applicable
    (often ``indexSymbol``; NSE also accepts many display ``index`` strings — test per index if 404).

Usage:
  python working-sector/fetch_nse_indices_catalog.py
  python working-sector/fetch_nse_indices_catalog.py --output-dir data
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

WORKING_SECTOR = Path(__file__).resolve().parent
PROJECT_ROOT = WORKING_SECTOR.parent


def _nse_session():
    try:
        import requests
    except ImportError:
        raise SystemExit("Install requests: pip install requests")
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; rv:109.0) Gecko/20100101 Firefox/115.0",
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.8",
        "Referer": "https://www.nseindia.com/market-data/all-indices",
    })
    s.get("https://www.nseindia.com", timeout=15)
    return s


def map_category(key: str) -> tuple[str, str, bool]:
    """
    Returns (category_code, category_label, is_thematic).
    is_thematic is True only for THEMATIC INDICES.
    """
    k = (key or "").strip().upper()
    if "BROAD" in k:
        return "BROAD", "Broad market", False
    if "SECTORAL" in k:
        return "SECTORAL", "Sectoral", False
    if "THEMATIC" in k:
        return "THEMATIC", "Thematic", True
    if "STRATEGY" in k:
        return "STRATEGY", "Strategy / factor", False
    if "FIXED INCOME" in k or "FIXED" in k:
        return "FIXED_INCOME", "Fixed income", False
    if "DERIVATIVES" in k:
        return "DERIVATIVES_ELIGIBLE", "Listed for derivatives", False
    return "OTHER", key or "Other", False


def fetch_catalog(session) -> tuple[list[dict], dict]:
    import requests

    url = "https://www.nseindia.com/api/allIndices"
    r = session.get(url, timeout=45)
    r.raise_for_status()
    payload = r.json()
    rows_raw = payload.get("data") or []
    meta = {
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "api_timestamp": payload.get("timestamp"),
        "advances": payload.get("advances"),
        "declines": payload.get("declines"),
        "unchanged": payload.get("unchanged"),
        "count": len(rows_raw),
    }
    out_rows = []
    for row in rows_raw:
        key = row.get("key") or ""
        code, label, thematic = map_category(key)
        display = (row.get("index") or "").strip()
        sym = (row.get("indexSymbol") or display).strip()
        out_rows.append({
            "category_code": code,
            "category_label": label,
            "is_thematic": "1" if thematic else "0",
            "nse_group_raw": key,
            "index_display_name": display,
            "api_index_symbol": sym,
            "last": row.get("last"),
            "percent_change": row.get("percentChange"),
            "pe": row.get("pe"),
            "pb": row.get("pb"),
            "year_high": row.get("yearHigh"),
            "year_low": row.get("yearLow"),
        })
    return out_rows, meta


def write_csv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description="Fetch NSE all-indices catalog from nseindia.com API.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "data",
        help="Directory for nse_indices_catalog.csv and JSON (default: project data/)",
    )
    parser.add_argument(
        "--no-json",
        action="store_true",
        help="Do not write nse_indices_catalog.json snapshot.",
    )
    args = parser.parse_args()
    out_dir = Path(args.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    session = _nse_session()
    rows, meta = fetch_catalog(session)
    csv_path = out_dir / "nse_indices_catalog.csv"
    write_csv(rows, csv_path)

    if not args.no_json:
        json_path = out_dir / "nse_indices_catalog.json"
        snap = {
            "meta": meta,
            "note": "Rows mirror CSV; snapshot for audit. Prefer CSV for pipelines.",
            "rows": rows,
        }
        json_path.write_text(json.dumps(snap, indent=2, ensure_ascii=False), encoding="utf-8")

    # Summary counts
    from collections import Counter
    by_cat = Counter(r["category_code"] for r in rows)
    print(f"Wrote {len(rows)} indices to {csv_path}")
    print("By category_code:")
    for k in sorted(by_cat.keys()):
        print(f"  {k}: {by_cat[k]}")
    thematic_n = sum(1 for r in rows if r["is_thematic"] == "1")
    print(f"Thematic indices (is_thematic): {thematic_n}")
    if not args.no_json:
        print(f"JSON snapshot: {out_dir / 'nse_indices_catalog.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
