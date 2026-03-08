"""
Configuration for sector research pipeline (Phases 2-5).
Sector is set via env NSE_SECTOR (e.g. auto_components); paths depend on it.
"""
import os
from pathlib import Path

# Project root (parent of working-sector)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
WORKING_SECTOR = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
REPORTS_DIR = PROJECT_ROOT / "reports"
# Alternative fundamental scores location
ORGANIZED_DATA = PROJECT_ROOT / "organized" / "data"

# Sector: from env so CLI/agent can set before import (default auto_components)
SECTOR = os.environ.get("NSE_SECTOR", "auto_components").strip().lower().replace(" ", "_")
# Display name for reports (sector key -> title case or custom)
SECTOR_DISPLAY_NAMES = {
    "auto_components": "Auto Components",
    "pharma": "Pharma",
    "textiles": "Textiles",
    "chemicals": "Chemicals",
}
SECTOR_DISPLAY_NAME = SECTOR_DISPLAY_NAMES.get(SECTOR, SECTOR.replace("_", " ").title())

# Input files (universe is per-sector)
UNIVERSE_CSV = WORKING_SECTOR / f"{SECTOR}_universe.csv"
STOCK_CSV = DATA_DIR / "nse_sec_full_data.csv"
INDEX_CSV = DATA_DIR / "nse_index_data.csv"
FUNDAMENTAL_CSV = ORGANIZED_DATA / "fundamental_scores_database.csv"
if not FUNDAMENTAL_CSV.exists():
    FUNDAMENTAL_CSV = DATA_DIR / "fundamental_scores_database.csv"

# Sector narrative (Phase 1 output, used in Phase 5)
SECTOR_NARRATIVE_MD = WORKING_SECTOR / f"sector_narrative_{SECTOR}.md"

# Index names in nse_index_data.csv
NIFTY_AUTO_INDEX = "Nifty Auto"
NIFTY_500_INDEX = "Nifty 500"  # in nse_index_data.csv

# Lookback for RS (trading days): ~21 = 1M, ~63 = 3M, ~126 = 6M
LOOKBACK_1M = 21
LOOKBACK_3M = 63
LOOKBACK_6M = 126

# Screen thresholds (from hypothesis memo)
MIN_FUND_SCORE = 70
MIN_RS_6M = 0  # RS vs Nifty 500 > 0
MIN_TECH_SCORE = 0  # optional; we use composite
COMPOSITE_WEIGHTS = (0.4, 0.4, 0.2)  # fundamental, technical, RS rank
SHORTLIST_TOP_N = 15

# Backtest
BACKTEST_START_YEAR = 2020
FORWARD_RETURN_DAYS = 252  # 1Y
REBALANCE_FREQ_DAYS = 21   # monthly

# Output (per-sector subdir so multiple sectors can coexist)
_out_base = WORKING_SECTOR / "output"
_out_sector = _out_base / SECTOR
# Backward compat: if legacy flat output/ has phase2 data and no sector subdir yet, use it for auto_components
if SECTOR == "auto_components" and (_out_base / "phase2_universe_metrics.csv").exists() and not _out_sector.exists():
    OUTPUT_DIR = _out_base
else:
    OUTPUT_DIR = _out_sector
OUTPUT_DIR.mkdir(exist_ok=True, parents=True)
PHASE2_TABLE_CSV = OUTPUT_DIR / "phase2_universe_metrics.csv"
PHASE3_SHORTLIST_CSV = OUTPUT_DIR / "phase3_shortlist.csv"
PHASE4_BACKTEST_CSV = OUTPUT_DIR / "phase4_backtest_results.csv"
SECTOR_NOTE_MD = OUTPUT_DIR / "sector_note.md"
DASHBOARD_HTML = OUTPUT_DIR / "dashboard.html"
