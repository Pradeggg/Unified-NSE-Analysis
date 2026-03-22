#!/usr/bin/env python3
"""
Phase 3: Technical analysis per holding.
Produces technical_by_stock.csv (and optional technical_summary.md).
When NSE price/RSI data is available, fills technical score and recommendation; otherwise stub from holdings.
"""
from __future__ import annotations

from pathlib import Path

try:
    from config import OUTPUT_DIR, HOLDINGS_CSV_OUT, TECHNICAL_BY_STOCK_CSV, TECHNICAL_SUMMARY_MD
except ImportError:
    OUTPUT_DIR = Path(__file__).resolve().parent / "output"
    HOLDINGS_CSV_OUT = OUTPUT_DIR / "holdings.csv"
    TECHNICAL_BY_STOCK_CSV = OUTPUT_DIR / "technical_by_stock.csv"
    TECHNICAL_SUMMARY_MD = OUTPUT_DIR / "technical_summary.md"


def run_phase3() -> dict:
    """Run Phase 3: technical by stock. Writes technical_by_stock.csv, technical_summary.md."""
    OUTPUT_DIR.mkdir(exist_ok=True, parents=True)
    if not HOLDINGS_CSV_OUT.exists():
        TECHNICAL_SUMMARY_MD.write_text(
            "# Technical summary\n\nRun Phase 0 first to generate holdings.\n", encoding="utf-8"
        )
        return {"n_stocks": 0, "note": "No holdings; run Phase 0 first."}

    import pandas as pd
    holdings = pd.read_csv(HOLDINGS_CSV_OUT)

    # Build technical table from holdings; add placeholders when price/RSI not available
    tech = holdings[["symbol", "quantity", "value_rs"]].copy()
    tech.columns = ["symbol", "quantity", "value_rs"]
    tech["technical_score"] = 50  # placeholder
    tech["recommendation"] = "HOLD"
    tech["buy_timing_note"] = "Technical score and recommendation require NSE price/RSI data (Phase 3 pipeline)."

    TECHNICAL_BY_STOCK_CSV.parent.mkdir(exist_ok=True, parents=True)
    tech.to_csv(TECHNICAL_BY_STOCK_CSV, index=False)

    summary_lines = [
        "# Technical summary",
        "",
        f"**{len(tech)}** holdings. Technical scores and buy/sell recommendations will appear when price and RSI data are available. Per-stock quantity and value are in the Technical table.",
        "",
    ]
    TECHNICAL_SUMMARY_MD.write_text("\n".join(summary_lines), encoding="utf-8")

    return {"n_stocks": len(tech), "output": str(TECHNICAL_BY_STOCK_CSV)}


if __name__ == "__main__":
    run_phase3()
    print("Phase 3 done.", TECHNICAL_BY_STOCK_CSV)
