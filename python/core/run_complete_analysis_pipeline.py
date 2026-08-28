#!/usr/bin/env python3
"""
Python end-to-end pipeline to:

1. Ensure NSE historical stock CSV is up to date (legacy + new API)
2. Append NSE index data from PR archives through the target end date
3. Run the enhanced NSE universe analysis
4. Optionally generate LLM narratives (skip if NARRATIVE_SKIP=1)
5. Generate an interactive HTML dashboard

Environment:
  ANALYSIS_END_DATE=YYYY-MM-DD  — last calendar day to load (default: 2026-03-27)
  NARRATIVE_SKIP=1              — skip Ollama narrative step
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

# python/core/this_file.py → repo root is three levels up
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS_DIR = Path(__file__).resolve().parent


def _run(cmd: list[str], *, cwd: Path = SCRIPTS_DIR) -> None:
    print(f"\n$ {' '.join(cmd)}")
    proc = subprocess.run(cmd, cwd=cwd)
    if proc.returncode != 0:
        raise SystemExit(f"Command failed with exit code {proc.returncode}: {' '.join(cmd)}")


def _ensure_stock_csv_from_legacy_locations() -> None:
    """Copy consolidated stock file into data/ if missing (older layouts)."""
    dest = REPO_ROOT / "data" / "nse_sec_full_data.csv"
    if dest.exists():
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    for alt in (
        SCRIPTS_DIR / "data" / "nse_sec_full_data.csv",
        REPO_ROOT / "core" / "NSE-index" / "nse_sec_full_data.csv",
    ):
        if alt.exists():
            shutil.copy2(alt, dest)
            print(f"Copied stock data: {alt} → {dest}")
            return


def _max_stock_date() -> date | None:
    p = REPO_ROOT / "data" / "nse_sec_full_data.csv"
    if not p.exists():
        return None
    ts = pd.read_csv(p, usecols=["TIMESTAMP"])
    ts["TIMESTAMP"] = pd.to_datetime(ts["TIMESTAMP"])
    return ts["TIMESTAMP"].max().date()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run full NSE analysis pipeline (data → analysis → dashboard)")
    parser.add_argument(
        "--end-date",
        default=os.environ.get("ANALYSIS_END_DATE", "2026-03-27"),
        help="Last date to load (YYYY-MM-DD). Also set via ANALYSIS_END_DATE.",
    )
    args = parser.parse_args()
    end = date.fromisoformat(args.end_date)

    print(f"📅 Pipeline end date: {end.isoformat()}\n")

    _ensure_stock_csv_from_legacy_locations()

    # 1) Base history via legacy archives (only if no stock file yet)
    stock_path = REPO_ROOT / "data" / "nse_sec_full_data.csv"
    if not stock_path.exists():
        _run(
            [
                sys.executable,
                "download_nse_historical_data.py",
                "--days",
                "730",
                "--end-date",
                end.isoformat(),
            ]
        )

    # 2) New API: fill from 2024-07-06 (or day after last row) through end
    last = _max_stock_date()
    new_api_start = date(2024, 7, 6)
    if last and last >= new_api_start:
        new_api_start = last + timedelta(days=1)
    if new_api_start <= end:
        _run(
            [
                sys.executable,
                "download_nse_historical_data_new_api.py",
                "--start-date",
                new_api_start.isoformat(),
                "--end-date",
                end.isoformat(),
            ]
        )
    else:
        print(
            "Stock CSV already has rows through the target end date; skipping new-API download."
        )

    # 3) Index PR archives through end
    _run([sys.executable, "download_nse_index_pr.py", "--end-date", end.isoformat()])

    # 4) Analysis + optional narratives + dashboard
    os.environ.setdefault("NARRATIVE_SKIP", "1")
    _run([sys.executable, "fixed_nse_universe_analysis.py"])
    _run([sys.executable, "narrative_pipeline_runner.py"])
    _run([sys.executable, "generate_nse_interactive_dashboard.py"])

    print("\n✅ Python end-to-end analysis pipeline completed successfully.")


if __name__ == "__main__":
    main()
