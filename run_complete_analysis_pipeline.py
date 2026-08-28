#!/usr/bin/env python3
"""
Python end-to-end pipeline to:

1. Ensure NSE historical data CSV is up to date
2. Run the enhanced NSE universe analysis
3. Generate an interactive HTML dashboard

This mirrors the intent of `run_complete_analysis_pipeline.R`, but uses the
Python scripts in this repository:

- download_nse_historical_data.py
- download_nse_historical_data_new_api.py
- fixed_nse_universe_analysis.py
- narrative_pipeline_runner.py (Ollama → SQLite; set NARRATIVE_SKIP=1 to skip)
- generate_nse_interactive_dashboard.py
"""

from __future__ import annotations

import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent


def _run(cmd: list[str]) -> None:
    print(f"\n$ {' '.join(cmd)}")
    proc = subprocess.run(cmd, cwd=PROJECT_ROOT)
    if proc.returncode != 0:
        raise SystemExit(f"Command failed with exit code {proc.returncode}: {' '.join(cmd)}")


def main() -> None:
    # 1) Update historical data using legacy + new API (only recent days from new API)
    today = date.today()
    # Download ~2 years via legacy archives (covers up to the switch to new API)
    _run([sys.executable, "python/core/download_nse_historical_data.py", "--days", "730"])

    # Then extend from 2024-07-06 to today via new API, preserving schema
    _run(
        [
            sys.executable,
            "python/core/download_nse_historical_data_new_api.py",
            "--start-date",
            "2024-07-06",
            "--end-date",
            today.isoformat(),
        ]
    )

    # 2) Run the comprehensive universe + index analysis (Python version)
    _run([sys.executable, "python/core/fixed_nse_universe_analysis.py"])

    # 2b) LLM narratives into SQLite for embedding in shareable HTML
    _run([sys.executable, "python/core/narrative_pipeline_runner.py"])

    # 3) Generate HTML interactive dashboard from analysis outputs
    _run([sys.executable, "python/core/generate_nse_interactive_dashboard.py"])

    print("\n✅ Python end-to-end analysis pipeline completed successfully.")


if __name__ == "__main__":
    main()

