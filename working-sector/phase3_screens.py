"""
Phase 3: Screens and Composite Score
Apply quality and momentum screens; compute composite; produce shortlist.
"""
import sys
from pathlib import Path

import pandas as pd
import numpy as np

WORKING_SECTOR = Path(__file__).resolve().parent
if str(WORKING_SECTOR) not in sys.path:
    sys.path.insert(0, str(WORKING_SECTOR))

from config import (
    PHASE2_TABLE_CSV,
    PHASE3_SHORTLIST_CSV,
    MIN_FUND_SCORE,
    MIN_RS_6M,
    COMPOSITE_WEIGHTS,
    SHORTLIST_TOP_N,
    OUTPUT_DIR,
)


def run_phase3(phase2_table: pd.DataFrame | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Run Phase 3: screens + composite + shortlist.
    Returns (full_table_with_composite, shortlist).
    """
    print("Phase 3: Screens and Composite Score")
    if phase2_table is not None:
        df = phase2_table.copy()
    else:
        df = pd.read_csv(PHASE2_TABLE_CSV)
        if df.empty:
            raise ValueError("Phase 2 table empty; run phase2_data.py first.")

    # Normalize for composite: 0-100 scale
    # Fundamental: already 0-100 (or NaN)
    df["FUND_NORM"] = df["FUND_SCORE"].clip(0, 100).fillna(50)
    # Technical: already 0-100 (or NaN)
    df["TECH_NORM"] = df["TECHNICAL_SCORE"].clip(0, 100).fillna(50)
    # RS rank: percentile rank within universe (0-100)
    rs = df["RS_VS_NIFTY_500_6M"]
    df["RS_RANK"] = rs.rank(pct=True, na_option="keep").fillna(0.5) * 100

    w_f, w_t, w_r = COMPOSITE_WEIGHTS
    df["COMPOSITE_SCORE"] = (
        w_f * df["FUND_NORM"] + w_t * df["TECH_NORM"] + w_r * df["RS_RANK"]
    )

    # Screen flags (from hypothesis: quality + momentum)
    df["PASS_FUND"] = df["FUND_SCORE"].ge(MIN_FUND_SCORE)
    df["PASS_RS"] = df["RS_VS_NIFTY_500_6M"].gt(MIN_RS_6M)
    df["PASS_SCREEN"] = df["PASS_FUND"] & df["PASS_RS"]

    # Shortlist: top N by composite (among those with sufficient data)
    eligible = df[
        df["FUND_SCORE"].notna() & df["RS_VS_NIFTY_500_6M"].notna()
    ].copy()
    eligible = eligible.sort_values("COMPOSITE_SCORE", ascending=False)
    shortlist = eligible.head(SHORTLIST_TOP_N)

    shortlist.to_csv(PHASE3_SHORTLIST_CSV, index=False)
    print(f"  Pass screen (FUND>={MIN_FUND_SCORE} & RS_6M>{MIN_RS_6M}): {df['PASS_SCREEN'].sum()}")
    print(f"  Shortlist (top {SHORTLIST_TOP_N} by composite): {len(shortlist)}")
    print(f"  Wrote {PHASE3_SHORTLIST_CSV}")

    # Keep full table with composite for Phase 4/5
    full_path = OUTPUT_DIR / "phase3_full_with_composite.csv"
    df.to_csv(full_path, index=False)
    print(f"  Wrote {full_path}")
    return df, shortlist


if __name__ == "__main__":
    run_phase3()
