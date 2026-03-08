#!/usr/bin/env python3
"""
Run Auto Components research pipeline: Phase 2 → Phase 3 → Phase 4 → Phase 5.
Execute from project root or working-sector: python run_pipeline.py
"""
import sys
from pathlib import Path

# Ensure working-sector is on path
WORKING_SECTOR = Path(__file__).resolve().parent
if str(WORKING_SECTOR) not in sys.path:
    sys.path.insert(0, str(WORKING_SECTOR))

def main():
    print("=" * 60)
    print("Auto Components Pipeline (Phases 2–5)")
    print("=" * 60)

    # Phase 2: Data
    from phase2_data import run_phase2
    phase2_table = run_phase2()
    print()

    # Phase 3: Screens and shortlist
    from phase3_screens import run_phase3
    full_table, shortlist = run_phase3(phase2_table=phase2_table)
    print()

    # Phase 4: Backtest
    from phase4_backtest import run_phase4
    backtest_df = run_phase4()
    print()

    # Phase 5: Report and dashboard
    from phase5_report import run_phase5
    run_phase5(
        phase2_table=phase2_table,
        shortlist=shortlist,
        backtest_df=backtest_df,
    )
    print()
    print("=" * 60)
    print("Pipeline complete. Outputs in working-sector/output/")
    print("  - phase2_universe_metrics.csv")
    print("  - phase3_shortlist.csv")
    print("  - phase3_full_with_composite.csv")
    print("  - phase4_backtest_results.csv")
    print("  - auto_components_sector_note.md")
    print("  - auto_components_dashboard.html")
    print("=" * 60)


if __name__ == "__main__":
    main()
