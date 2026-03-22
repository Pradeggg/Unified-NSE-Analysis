#!/usr/bin/env python3
"""
Phase 2: Sectoral assessment.
Maps holdings to sectors (when NSE/ref sector data available) and writes sector_assessment.md.
"""
from __future__ import annotations

from pathlib import Path

try:
    from config import OUTPUT_DIR, HOLDINGS_CSV_OUT, SECTOR_ASSESSMENT_MD, STOCK_CSV
except ImportError:
    OUTPUT_DIR = Path(__file__).resolve().parent / "output"
    HOLDINGS_CSV_OUT = OUTPUT_DIR / "holdings.csv"
    SECTOR_ASSESSMENT_MD = OUTPUT_DIR / "sector_assessment.md"
    STOCK_CSV = Path(__file__).resolve().parent.parent / "data" / "nse_sec_full_data.csv"


def run_phase2() -> dict:
    """Run Phase 2: sectoral assessment. Writes sector_assessment.md."""
    OUTPUT_DIR.mkdir(exist_ok=True, parents=True)
    if not HOLDINGS_CSV_OUT.exists():
        SECTOR_ASSESSMENT_MD.write_text(
            "# Sector assessment\n\nRun Phase 0 first to generate holdings.\n", encoding="utf-8"
        )
        return {"n_sectors": 0, "note": "No holdings; run Phase 0 first."}

    import pandas as pd
    holdings = pd.read_csv(HOLDINGS_CSV_OUT)
    total_value = holdings["value_rs"].sum() if "value_rs" in holdings.columns else 0
    n_stocks = len(holdings)

    # Optional: merge with NSE sector/industry if available in project data
    sector_col = None
    try:
        if STOCK_CSV.exists():
            nse = pd.read_csv(STOCK_CSV, nrows=50000)
            for c in ("industry", "Industry", "sector", "Sector", "SUBSECTOR", "subsector"):
                if c in nse.columns and "SYMBOL" in nse.columns:
                    nse_sym = nse.drop_duplicates(subset=["SYMBOL"], keep="last")
                    holdings = holdings.merge(
                        nse_sym[["SYMBOL", c]].rename(columns={c: "sector"}),
                        left_on="symbol",
                        right_on="SYMBOL",
                        how="left",
                    )
                    if "sector" in holdings.columns:
                        sector_col = "sector"
                    break
    except Exception:
        pass

    lines = [
        "# Sectoral assessment",
        "",
        f"Portfolio: **{n_stocks}** stocks, total value (from CAS) **Rs {total_value:,.0f}**.",
        "",
    ]
    n_sectors = 0
    if sector_col and holdings[sector_col].notna().any():
        sector_counts = holdings.groupby(sector_col).agg(
            count=("symbol", "count"),
            value_rs=("value_rs", "sum") if "value_rs" in holdings.columns else ("symbol", "count"),
        ).reset_index()
        if "value_rs" in sector_counts.columns:
            sector_counts = sector_counts.sort_values("value_rs", ascending=False)
        n_sectors = len(sector_counts)
        lines += ["## Exposure by sector", ""]
        for _, row in sector_counts.iterrows():
            sec = row.get("sector", row.get(sector_col, ""))
            cnt = int(row["count"])
            val = row.get("value_rs", 0)
            if isinstance(val, (int, float)):
                lines.append(f"- **{sec}**: {cnt} stocks, Rs {val:,.0f}")
            else:
                lines.append(f"- **{sec}**: {cnt} stocks")
            lines.append("")
        lines.append("")
    else:
        lines += [
            "Sector exposure by industry is not available in this run. Portfolio totals are shown above.",
            "",
        ]

    SECTOR_ASSESSMENT_MD.write_text("\n".join(lines), encoding="utf-8")
    return {"n_stocks": n_stocks, "total_value_rs": float(total_value), "n_sectors": n_sectors}


if __name__ == "__main__":
    run_phase2()
    print("Phase 2 done.", SECTOR_ASSESSMENT_MD)
