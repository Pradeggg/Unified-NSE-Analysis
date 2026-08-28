#!/usr/bin/env python3
"""
Run Phases 2-5: if any universe symbols are missing from fundamental_scores_database.csv,
fetch them from Screener.in via R script, then run the full pipeline.
"""
import subprocess
import sys
from pathlib import Path

import pandas as pd

WORKING_SECTOR = Path(__file__).resolve().parent
PROJECT_ROOT = WORKING_SECTOR.parent
if str(WORKING_SECTOR) not in sys.path:
    sys.path.insert(0, str(WORKING_SECTOR))

from config import (
    UNIVERSE_CSV,
    FUNDAMENTAL_CSV,
    OUTPUT_DIR,
    ORGANIZED_DATA,
)


def get_universe_symbols() -> list[str]:
    df = pd.read_csv(UNIVERSE_CSV)
    return df["SYMBOL"].str.strip().str.upper().tolist()


def get_existing_fund_symbols() -> set[str]:
    if not FUNDAMENTAL_CSV.exists():
        return set()
    df = pd.read_csv(FUNDAMENTAL_CSV)
    if "symbol" not in df.columns:
        return set()
    return set(df["symbol"].astype(str).str.strip().str.upper())


def fetch_missing_via_screener(missing: list[str]) -> bool:
    if not missing:
        return True
    symbols_file = OUTPUT_DIR / "symbols_to_fetch.txt"
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    symbols_file.write_text("\n".join(missing) + "\n", encoding="utf-8")
    fund_csv = FUNDAMENTAL_CSV
    r_script = WORKING_SECTOR / "fetch_screener_fundamentals.R"
    cmd = [
        "Rscript",
        str(r_script),
        str(symbols_file),
        str(fund_csv),
    ]
    print("Running Screener fetch (R):", " ".join(cmd))
    try:
        result = subprocess.run(
            cmd,
            cwd=str(PROJECT_ROOT),
            capture_output=False,
            text=True,
            timeout=3600,
        )
        return result.returncode == 0
    except FileNotFoundError:
        print("Rscript not found. Install R and ensure Rscript is on PATH.")
        return False
    except subprocess.TimeoutExpired:
        print("R script timed out.")
        return False


def main():
    print("=" * 60)
    print("Auto Components Pipeline (with Screener fetch if needed)")
    print("=" * 60)

    universe = get_universe_symbols()
    existing = get_existing_fund_symbols()
    missing = [s for s in universe if s not in existing]
    print(f"Universe: {len(universe)} symbols. Already have fundamentals: {len(existing)}. Missing: {len(missing)}")

    if missing:
        print("\nFetching fundamentals from Screener.in for missing symbols...")
        ok = fetch_missing_via_screener(missing)
        if not ok:
            print("Screener fetch failed; continuing with existing fundamental data only.")
        else:
            print("Screener fetch completed.")
    else:
        print("No missing fundamentals; skipping Screener fetch.")

    print("\nRunning Phase 2 -> Phase 5...")
    from phase2_data import run_phase2
    from phase3_screens import run_phase3
    from phase4_backtest import run_phase4
    from phase5_report import run_phase5

    phase2_table = run_phase2()
    print()
    full_table, shortlist = run_phase3(phase2_table=phase2_table)
    print()
    backtest_df = run_phase4()
    print()
    run_phase5(phase2_table=phase2_table, shortlist=shortlist, backtest_df=backtest_df)
    print()
    print("=" * 60)
    print("Pipeline complete. Outputs in working-sector/output/")
    print("=" * 60)


if __name__ == "__main__":
    main()
