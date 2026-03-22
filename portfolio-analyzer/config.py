"""
Configuration for portfolio analyzer (Phases 0-6).
Paths for inputs (PnL CSV, CAS), output dir, and shared project data (NSE, fundamentals).
"""
from pathlib import Path

# Project root (parent of portfolio-analyzer)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
PORTFOLIO_ANALYZER = Path(__file__).resolve().parent

# Shared project data (NSE, fundamentals – same as working-sector)
DATA_DIR = PROJECT_ROOT / "data"
ORGANIZED_DATA = PROJECT_ROOT / "organized" / "data"
WORKING_SECTOR = PROJECT_ROOT / "working-sector"

# Inputs: PnL CSV and optional CAS (holdings). Override via env or pass to phase0.
PNL_CSV = PORTFOLIO_ANALYZER / "8500589913_EQProfitLossDetails.csv"
CAS_PDF = PORTFOLIO_ANALYZER / "NSDLe-CAS_104270072_JAN_2026.PDF.pdf"
HOLDINGS_CSV = PORTFOLIO_ANALYZER / "holdings_export.csv"  # Optional: manual export if PDF not parseable

# NSE / fundamentals (for phases 2–4)
STOCK_CSV = DATA_DIR / "nse_sec_full_data.csv"
INDEX_CSV = DATA_DIR / "nse_index_data.csv"
FUNDAMENTAL_CSV = ORGANIZED_DATA / "fundamental_scores_database.csv"
if not FUNDAMENTAL_CSV.exists():
    FUNDAMENTAL_CSV = DATA_DIR / "fundamental_scores_database.csv"

# Output
OUTPUT_DIR = PORTFOLIO_ANALYZER / "output"
OUTPUT_DIR.mkdir(exist_ok=True, parents=True)

# Phase 0 outputs
HOLDINGS_CSV_OUT = OUTPUT_DIR / "holdings.csv"
CLOSED_PNL_CSV = OUTPUT_DIR / "closed_pnl.csv"
PORTFOLIO_SUMMARY_JSON = OUTPUT_DIR / "portfolio_summary.json"

# Phase 1
PNL_SUMMARY_MD = OUTPUT_DIR / "pnl_summary.md"
PNL_AGGREGATES_CSV = OUTPUT_DIR / "pnl_aggregates.csv"

# Phase 2
SECTOR_ASSESSMENT_MD = OUTPUT_DIR / "sector_assessment.md"

# Phase 3
TECHNICAL_BY_STOCK_CSV = OUTPUT_DIR / "technical_by_stock.csv"
TECHNICAL_SUMMARY_MD = OUTPUT_DIR / "technical_summary.md"

# Phase 4
FUNDAMENTAL_BY_STOCK_CSV = OUTPUT_DIR / "fundamental_by_stock.csv"
FUNDAMENTAL_DETAILS_CSV = OUTPUT_DIR / "fundamental_details.csv"
CALL_TRANSCRIPTS_SUMMARY_CSV = OUTPUT_DIR / "call_transcripts_summary.csv"
CREDIT_RATINGS_CSV = OUTPUT_DIR / "credit_ratings.csv"

# Phase 5
STOCK_NARRATIVES_JSON = OUTPUT_DIR / "stock_narratives.json"
STOCK_NARRATIVES_MD = OUTPUT_DIR / "stock_narratives.md"

# Phase 6
REPORT_MD = OUTPUT_DIR / "portfolio_comprehensive_report.md"
REPORT_HTML = OUTPUT_DIR / "portfolio_comprehensive_report.html"
REPORT_XLSX = OUTPUT_DIR / "portfolio_comprehensive_report.xlsx"

# Phase 7: Risk and scenarios
RISK_METRICS_CSV = OUTPUT_DIR / "risk_metrics.csv"
RISK_METRICS_JSON = OUTPUT_DIR / "risk_metrics.json"
SCENARIO_PROJECTIONS_CSV = OUTPUT_DIR / "scenario_projections.csv"
SCENARIO_NARRATIVE_MD = OUTPUT_DIR / "scenario_narrative.md"

# Market sentiment (search + LLM)
MARKET_SENTIMENT_MD = OUTPUT_DIR / "market_sentiment.md"
MARKET_SENTIMENT_SOURCES_JSON = OUTPUT_DIR / "market_sentiment_sources.json"

# LLM (optional)
OLLAMA_MODEL = "granite4:latest"
OLLAMA_URL = "http://localhost:11434"
