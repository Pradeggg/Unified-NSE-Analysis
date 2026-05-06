#!/usr/bin/env python3
"""One-time migration: merge all legacy fundamental sources into the single cache file.

P0-4 — Consolidate Data Sources.

This script merges:
  1. data/_sector_rotation_fund_cache.csv           (primary — kept as-is)
  2. reports/Apex_Resilience_screener_fundamentals_*.csv  (legacy — if present)
  3. working-sector/output/fundamental_details.csv  (legacy — if present)

After merging, the cache file is the single source of truth.
Legacy files are NOT deleted (kept for audit trail) but are no longer read
by sector_rotation_report.py._load_fundamental_details().

Usage:
  python scripts/migrate_fund_cache.py          # dry-run (default)
  python scripts/migrate_fund_cache.py --apply  # write merged cache
"""

from __future__ import annotations

import argparse
import glob
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "_sector_rotation_fund_cache.csv"
FUND_COLS = ["SYMBOL", "pnl_summary", "quarterly_summary", "balance_sheet_summary", "ratios_summary"]


def _read_src(path: Path) -> pd.DataFrame | None:
    try:
        df = pd.read_csv(path)
        if "symbol" in df.columns and "SYMBOL" not in df.columns:
            df = df.rename(columns={"symbol": "SYMBOL"})
        if "SYMBOL" in df.columns and "pnl_summary" in df.columns:
            return df[[c for c in FUND_COLS if c in df.columns]]
    except Exception as exc:
        print(f"  WARN: could not read {path}: {exc}")
    return None


def migrate(apply: bool = False) -> None:
    print(f"{'='*60}")
    print("P0-4: Fundamental Data Cache Migration")
    print(f"{'='*60}\n")

    # Collect all sources
    sources: list[tuple[str, Path]] = []

    # Primary cache
    if CACHE.exists():
        sources.append(("cache (primary)", CACHE))

    # Legacy: Apex screener files (glob for date variants)
    for p in sorted(glob.glob(str(ROOT / "reports" / "Apex_Resilience_screener_fundamentals_*.csv"))):
        sources.append(("legacy-apex", Path(p)))

    # Legacy: working-sector fundamental_details
    ws = ROOT / "working-sector" / "output" / "fundamental_details.csv"
    if ws.exists():
        sources.append(("legacy-ws", ws))

    if not sources:
        print("No data sources found. Nothing to migrate.")
        return

    # Read and merge (first occurrence wins — cache takes priority)
    frames = []
    for label, path in sources:
        df = _read_src(path)
        if df is not None:
            print(f"  [{label}] {path.name}: {len(df)} symbols")
            frames.append(df)
        else:
            print(f"  [{label}] {path.name}: SKIPPED (unreadable or wrong schema)")

    if not frames:
        print("\nNo valid data found. Nothing to merge.")
        return

    merged = pd.concat(frames).drop_duplicates("SYMBOL", keep="first")
    print(f"\n  Merged total: {len(merged)} unique symbols")

    if CACHE.exists():
        existing = _read_src(CACHE)
        existing_count = len(existing) if existing is not None else 0
        new_count = len(merged) - existing_count
        print(f"  New symbols added: {new_count}")
    else:
        print(f"  Cache will be created with {len(merged)} symbols")

    if apply:
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        merged.to_csv(CACHE, index=False)
        print(f"\n  ✅ Cache written: {CACHE}")

        # Clean up tmp file if it exists
        tmp = ROOT / "data" / "_sector_rotation_fund_tmp.csv"
        if tmp.exists():
            tmp.unlink()
            print(f"  🗑  Removed tmp file: {tmp.name}")
    else:
        print(f"\n  DRY RUN — no changes written. Use --apply to write.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate fundamental data to single cache.")
    parser.add_argument("--apply", action="store_true", help="Write merged cache (default: dry-run).")
    args = parser.parse_args()
    migrate(apply=args.apply)
