#!/usr/bin/env python3
"""
Phase 4: Fundamental analysis (per holding).

- Pull fundamental scores and details (P&L, quarterly, balance sheet, ratios) from
  fundamental_scores_database.csv and fundamental_details.csv (Screener pipeline).
- Call transcripts: fetch latest earnings/concall transcripts from NSE or Screener
  (NSE corporate announcements/transcripts; Screener concall/earnings transcript links).
- Credit ratings: from Screener (rating agencies). Used to build financial health
  and future growth prospect in both qualitative and quantitative form.
- Output: fundamental_by_stock.csv, fundamental_details.csv, optional
  call_transcripts_summary.csv, credit_ratings.csv; all feed into stock narratives.
"""
from __future__ import annotations

from pathlib import Path

try:
    from config import (
        OUTPUT_DIR,
        HOLDINGS_CSV_OUT,
        CLOSED_PNL_CSV,
        FUNDAMENTAL_CSV,
        FUNDAMENTAL_BY_STOCK_CSV,
        FUNDAMENTAL_DETAILS_CSV,
        PROJECT_ROOT,
    )
except ImportError:
    PORTFOLIO_ANALYZER = Path(__file__).resolve().parent
    OUTPUT_DIR = PORTFOLIO_ANALYZER / "output"
    HOLDINGS_CSV_OUT = OUTPUT_DIR / "holdings.csv"
    CLOSED_PNL_CSV = OUTPUT_DIR / "closed_pnl.csv"
    FUNDAMENTAL_BY_STOCK_CSV = OUTPUT_DIR / "fundamental_by_stock.csv"
    FUNDAMENTAL_DETAILS_CSV = OUTPUT_DIR / "fundamental_details.csv"
    PROJECT_ROOT = PORTFOLIO_ANALYZER.parent
    FUNDAMENTAL_CSV = PROJECT_ROOT / "organized" / "data" / "fundamental_scores_database.csv"

# Optional outputs (when NSE/Screener fetch is implemented)
CALL_TRANSCRIPTS_SUMMARY_CSV = OUTPUT_DIR / "call_transcripts_summary.csv"
CREDIT_RATINGS_CSV = OUTPUT_DIR / "credit_ratings.csv"

# Data sources (for implementation):
# - Call transcripts: NSE (corporate announcements / transcript PDFs or links),
#   Screener (company page → concall / earnings transcript).
# - Credit ratings: Screener company page (credit rating / agency rating).
# - fundamental_details (P&L, BS, quarterly, ratios): existing fetch_screener_fundamental_details.R or equivalent.


def load_holdings_symbols() -> list[str]:
    """Symbols from holdings or closed_pnl."""
    if HOLDINGS_CSV_OUT.exists():
        import pandas as pd
        df = pd.read_csv(HOLDINGS_CSV_OUT)
        if "symbol" in df.columns:
            return df["symbol"].dropna().astype(str).str.strip().str.upper().unique().tolist()
    if CLOSED_PNL_CSV.exists():
        import pandas as pd
        df = pd.read_csv(CLOSED_PNL_CSV)
        if "symbol" in df.columns:
            return df["symbol"].dropna().astype(str).str.strip().str.upper().unique().tolist()
    return []


def run_phase4() -> dict:
    """
    Run Phase 4: merge fundamental scores (and optional details) per holding.
    Placeholder: call transcripts and credit ratings require NSE/Screener fetch (TODO).
    Returns summary dict.
    """
    import pandas as pd

    symbols = load_holdings_symbols()
    if not symbols:
        return {"n_stocks": 0, "note": "No holdings or closed_pnl; run Phase 0 first."}

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_rows = []

    if FUNDAMENTAL_CSV.exists():
        fund = pd.read_csv(FUNDAMENTAL_CSV)
        if "symbol" in fund.columns:
            fund["SYMBOL"] = fund["symbol"].str.strip().str.upper()
        elif "SYMBOL" in fund.columns:
            fund["SYMBOL"] = fund["SYMBOL"].str.strip().str.upper()
        for sym in symbols:
            row = fund[fund["SYMBOL"] == sym]
            if not row.empty:
                r = row.iloc[0].to_dict()
                r["symbol"] = sym
                out_rows.append(r)

    if out_rows:
        pd.DataFrame(out_rows).to_csv(FUNDAMENTAL_BY_STOCK_CSV, index=False)

    # TODO: Fetch call transcripts from NSE/Screener per symbol → call_transcripts_summary.csv
    # TODO: Fetch credit ratings from Screener per symbol → credit_ratings.csv
    # TODO: Run fetch_screener_fundamental_details.R for portfolio symbols → fundamental_details.csv (P&L, BS, quarterly, ratios incl. EPS, PE, PB, ROCE)

    return {
        "n_stocks": len(symbols),
        "n_with_fundamentals": len(out_rows),
        "fundamental_by_stock_csv": str(FUNDAMENTAL_BY_STOCK_CSV),
        "note": "Call transcripts and credit ratings: implement NSE/Screener fetch; then add to narrative.",
    }


if __name__ == "__main__":
    summary = run_phase4()
    print("Phase 4 (fundamental) done.", summary)
