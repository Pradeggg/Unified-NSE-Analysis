#!/usr/bin/env python3
"""
Re-fetch Screener.in fundamentals for rows where APEX_GUIDANCE == REVIEW_DATA,
patch the full Apex CSV + consolidated screener fundamentals + regenerate MD/HTML.

Usage (project root):
  python3 refill_apex_screener_review.py
  python3 refill_apex_screener_review.py --full-csv reports/Apex_Resilience_Full_20260422.csv
  python3 refill_apex_screener_review.py --batch-size 25 --workers 1
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from apex_resilience_full_report import (
    REPORTS_DIR,
    SCREENER_DISPLAY_NAME,
    SCREENER_SLUG,
    SCREENER_TAGLINE,
    TARGET_INDICES,
    build_html_full,
    build_markdown_report,
    compute_apex_guidance,
    latest_comprehensive_csv,
    run_screener_fetch_batched,
    screener_row_complete,
)
from pullback_recovery_screener import PROJECT_ROOT


def _day_key_from_full_path(p: Path) -> str:
    m = re.search(r"_Full_(\d{8})\.csv$", p.name)
    if m:
        return m.group(1)
    raise ValueError(f"Cannot infer YYYYMMDD from filename: {p}")


def patch_master_screener_csv(master_path: Path, patch: pd.DataFrame) -> None:
    """Update rows in consolidated Screener CSV by SYMBOL."""
    cols = ["pnl_summary", "quarterly_summary", "balance_sheet_summary", "ratios_summary"]
    master = pd.read_csv(master_path)
    if "SYMBOL" not in master.columns and "symbol" in master.columns:
        master["SYMBOL"] = master["symbol"].astype(str).str.upper().str.strip()
    master["SYMBOL"] = master["SYMBOL"].astype(str).str.upper().str.strip()
    patch = patch.copy()
    patch["SYMBOL"] = patch["SYMBOL"].astype(str).str.upper().str.strip()
    for _, row in patch.iterrows():
        sym = row["SYMBOL"]
        mask = master["SYMBOL"] == sym
        if not mask.any():
            add = {c: row.get(c, "") for c in cols}
            add["SYMBOL"] = sym
            master = pd.concat([master, pd.DataFrame([add])], ignore_index=True)
        else:
            i = master.index[mask][0]
            for c in cols:
                if c in row.index:
                    master.loc[i, c] = row[c]
    master.to_csv(master_path, index=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="Refetch Screener for REVIEW_DATA rows and patch reports.")
    parser.add_argument(
        "--full-csv",
        type=Path,
        default=REPORTS_DIR / "Apex_Resilience_Full_20260422.csv",
        help="Existing Apex full report CSV to patch.",
    )
    parser.add_argument("--batch-size", type=int, default=25, help="Symbols per R subprocess.")
    parser.add_argument("--workers", type=int, default=1, help="Parallel R jobs (1 = safest).")
    args = parser.parse_args()

    full_path = args.full_csv.resolve()
    if not full_path.is_file():
        print(f"Not found: {full_path}", file=sys.stderr)
        sys.exit(1)

    df = pd.read_csv(full_path)
    if "APEX_GUIDANCE" not in df.columns:
        print("CSV missing APEX_GUIDANCE column.", file=sys.stderr)
        sys.exit(1)

    review = df[df["APEX_GUIDANCE"].astype(str).str.upper().eq("REVIEW_DATA")].copy()
    syms = review["SYMBOL"].astype(str).str.upper().tolist()
    if not syms:
        print("No REVIEW_DATA rows — nothing to refill.")
        sys.exit(0)

    day_key = _day_key_from_full_path(full_path)
    refill_tag = "refill_review"
    out_refill = REPORTS_DIR / f"_apex_refill_{refill_tag}_{day_key}.csv"

    print(f"Refilling Screener for {len(syms)} symbols (REVIEW_DATA). day_key={day_key}", file=sys.stderr)
    refill_df, ok, r_log = run_screener_fetch_batched(
        syms,
        out_refill,
        PROJECT_ROOT,
        f"{day_key}_{refill_tag}",
        batch_size=max(1, args.batch_size),
        max_workers=max(1, args.workers),
    )
    if not ok:
        print("Warning: some refill batches failed:\n", r_log[-3000:], file=sys.stderr)

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    ts_note = ts + (" (refill partial)" if not ok else " (refill REVIEW_DATA)")

    # Patch main dataframe columns from refill
    fund_cols = ["pnl_summary", "quarterly_summary", "balance_sheet_summary", "ratios_summary"]
    refill_idx = refill_df.set_index("SYMBOL")
    for col in fund_cols:
        if col not in df.columns:
            df[col] = ""
    for sym in syms:
        if sym not in refill_idx.index:
            continue
        row = refill_idx.loc[sym]
        for col in fund_cols:
            if col in row.index:
                df.loc[df["SYMBOL"].astype(str).str.upper() == sym, col] = str(row[col]) if pd.notna(row[col]) else ""

    df["SCREENER_FETCH_AT"] = df["SCREENER_FETCH_AT"].astype(str)
    for sym in syms:
        m = df["SYMBOL"].astype(str).str.upper() == sym
        df.loc[m, "SCREENER_FETCH_AT"] = ts_note

    df["SCREENER_DATA_COMPLETE"] = df.apply(screener_row_complete, axis=1)

    med = float(df["COMPOSITE"].astype(float).median())
    df["APEX_GUIDANCE"] = df.apply(lambda r: compute_apex_guidance(r, med), axis=1)

    out_csv = REPORTS_DIR / f"{SCREENER_SLUG}_Full_{day_key}.csv"
    df.to_csv(out_csv, index=False)

    master_scr = REPORTS_DIR / f"{SCREENER_SLUG}_screener_fundamentals_{day_key}.csv"
    if master_scr.is_file():
        patch_master_screener_csv(master_scr, refill_df[fund_cols + ["SYMBOL"]])
    else:
        refill_df.to_csv(master_scr, index=False)

    comp_path = latest_comprehensive_csv(REPORTS_DIR, None)
    methodology = [
        "Universe context: index_stock_mapping — " + ", ".join(TARGET_INDICES) + ".",
        "This artifact was **patched** by refill_apex_screener_review.py: re-fetched Screener.in for symbols "
        f"that previously had APEX_GUIDANCE=REVIEW_DATA ({len(syms)} symbols).",
        f"Composite median after patch: {med:.6f}; APEX_GUIDANCE recomputed from TRADING_SIGNAL + COMPOSITE vs median + Screener completeness.",
        "VERIFY figures on screener.in.",
    ]

    build_markdown_report(
        day_key,
        df,
        methodology,
        str(comp_path) if comp_path else None,
        str(master_scr),
        REPORTS_DIR / f"{SCREENER_SLUG}_Full_{day_key}.md",
    )

    build_html_full(
        SCREENER_DISPLAY_NAME,
        pd.to_datetime(df["LAST_DATE"].iloc[0]).strftime("%d %b %Y"),
        pd.to_datetime(df["LAST_DATE"].iloc[0]).strftime("%Y-%m-%d"),
        df,
        methodology,
        str(comp_path) if comp_path else None,
        str(master_scr),
        REPORTS_DIR / f"{SCREENER_SLUG}_Full_{day_key}.html",
        narrative_map={},
    )

    still_review = int(df["APEX_GUIDANCE"].astype(str).str.upper().eq("REVIEW_DATA").sum())
    print("Wrote:", out_csv, file=sys.stderr)
    print("HTML:", REPORTS_DIR / f"{SCREENER_SLUG}_Full_{day_key}.html", file=sys.stderr)
    print(f"REVIEW_DATA remaining: {still_review} (still incomplete Screener text or missing tech merge)", file=sys.stderr)


if __name__ == "__main__":
    main()
