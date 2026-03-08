"""
Phase 5: Output
Generate sector note (Markdown), export CSVs, and simple HTML dashboard.
"""
import sys
from pathlib import Path
from datetime import date

import pandas as pd

WORKING_SECTOR = Path(__file__).resolve().parent
if str(WORKING_SECTOR) not in sys.path:
    sys.path.insert(0, str(WORKING_SECTOR))

from config import (
    PHASE2_TABLE_CSV,
    PHASE3_SHORTLIST_CSV,
    PHASE4_BACKTEST_CSV,
    SECTOR_NOTE_MD,
    SECTOR_NARRATIVE_MD,
    SECTOR_DISPLAY_NAME,
    DASHBOARD_HTML,
    OUTPUT_DIR,
)
PHASE3_FULL_CSV = OUTPUT_DIR / "phase3_full_with_composite.csv"


def load_sector_narrative() -> str:
    if SECTOR_NARRATIVE_MD.exists():
        return SECTOR_NARRATIVE_MD.read_text(encoding="utf-8")
    return f"*(Sector narrative not found; run run_research_workflow.sh or add {SECTOR_NARRATIVE_MD.name})*"


def run_phase5(
    phase2_table: pd.DataFrame | None = None,
    shortlist: pd.DataFrame | None = None,
    backtest_df: pd.DataFrame | None = None,
) -> None:
    """Generate sector note, ensure CSVs in output, and write HTML dashboard."""
    print("Phase 5: Report and Dashboard")
    today = date.today().isoformat()

    # Load data if not passed
    if phase2_table is None and PHASE2_TABLE_CSV.exists():
        phase2_table = pd.read_csv(PHASE2_TABLE_CSV)
    # For dashboard and count, use full table with composite (phase3 output)
    full_table = None
    if PHASE3_FULL_CSV.exists():
        full_table = pd.read_csv(PHASE3_FULL_CSV)
    if full_table is None:
        full_table = phase2_table
    if shortlist is None and PHASE3_SHORTLIST_CSV.exists():
        shortlist = pd.read_csv(PHASE3_SHORTLIST_CSV)
    if backtest_df is None and PHASE4_BACKTEST_CSV.exists():
        backtest_df = pd.read_csv(PHASE4_BACKTEST_CSV)

    narrative = load_sector_narrative()

    # ---- Sector note (Markdown) ----
    as_of = today
    if full_table is not None and not full_table.empty and "AS_OF_DATE" in full_table.columns:
        as_of = full_table["AS_OF_DATE"].iloc[0]
    elif phase2_table is not None and not phase2_table.empty and "AS_OF_DATE" in phase2_table.columns:
        as_of = phase2_table["AS_OF_DATE"].iloc[0]
    # Strip duplicate top-level heading from narrative if present
    narrative_clean = narrative.strip()
    if narrative_clean.startswith("# "):
        narrative_clean = "\n".join(narrative_clean.split("\n")[1:]).strip()
    note_lines = [
        f"# {SECTOR_DISPLAY_NAME} (India) – Sector Note",
        "",
        f"**Report date:** {today}  \n**Data as of:** {as_of}",
        "",
        "---",
        "",
        "## 1. Definition and market size",
        "",
        narrative_clean,
        "",
        "---",
        "",
        "## 2. Universe and metrics",
        "",
        f"This analysis uses a **component-only** universe (ex-OEM), aligned with ACMA. "
        f"Universe: {len(full_table) if full_table is not None and not full_table.empty else 0} stocks.",
        "",
    ]
    if shortlist is not None and not shortlist.empty:
        note_lines += [
            "## 3. Shortlist (top by composite score)",
            "",
            "| SYMBOL | SUBSECTOR | CURRENT_PRICE | RET_6M | RS_VS_NIFTY_500_6M | FUND_SCORE | TECHNICAL_SCORE | COMPOSITE_SCORE |",
            "|--------|-----------|---------------|--------|--------------------|------------|-----------------|-----------------|",
        ]
        for _, row in shortlist.iterrows():
            note_lines.append(
                f"| {row.get('SYMBOL','')} | {row.get('SUBSECTOR','')} | {row.get('CURRENT_PRICE',0):.2f} | "
                f"{row.get('RET_6M',0)*100:.1f}% | {row.get('RS_VS_NIFTY_500_6M',0)*100:.1f}% | "
                f"{row.get('FUND_SCORE',0):.1f} | {row.get('TECHNICAL_SCORE',0):.1f} | {row.get('COMPOSITE_SCORE',0):.1f} |"
            )
        note_lines += ["", ""]
    if backtest_df is not None and not backtest_df.empty and backtest_df.get("EXCESS_RET") is not None:
        excess = backtest_df["EXCESS_RET"].dropna()
        mean_excess = excess.mean() * 100 if len(excess) > 0 else float("nan")
        hit = (excess > 0).sum() / len(excess) * 100 if len(excess) > 0 else 0
        note_lines += [
            "## 4. Backtest (momentum screen: RS_6M > 0)",
            "",
            f"- Mean excess return (portfolio vs Nifty 500, 1Y forward): **{mean_excess:.2f}%**",
            f"- Hit rate (excess > 0): **{hit:.0f}%**",
            "",
            "*Backtest uses only price-based criteria; fundamental screen not applied historically (data limitation).*",
            "",
        ]
    note_lines += [
        "---",
        "",
        "## 5. Sources and data",
        "",
        f"- **Definition and market size:** See {SECTOR_NARRATIVE_MD.name} and literature notes for this sector.",
        "- **Price data:** NSE (nse_sec_full_data.csv, nse_index_data.csv).",
        "- **Fundamental scores:** Screener/organized pipeline (fundamental_scores_database.csv).",
        "",
    ]
    SECTOR_NOTE_MD.write_text("\n".join(note_lines), encoding="utf-8")
    print(f"  Wrote {SECTOR_NOTE_MD}")

    # ---- HTML dashboard ----
    html_parts = [
        f"<!DOCTYPE html><html><head><meta charset='utf-8'><title>{SECTOR_DISPLAY_NAME} – Dashboard</title>",
        "<style>",
        "body { font-family: system-ui, sans-serif; margin: 1rem; }",
        "table { border-collapse: collapse; width: 100%; }",
        "th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }",
        "th { background: #333; color: #fff; }",
        "tr:nth-child(even) { background: #f9f9f9; }",
        ".shortlist { margin-top: 1.5rem; }",
        "h1 { color: #222; }",
        "h2 { margin-top: 1.5rem; color: #444; }",
        "</style></head><body>",
        f"<h1>{SECTOR_DISPLAY_NAME} (India) – Sector Dashboard</h1>",
        f"<p><strong>Data as of:</strong> {as_of}</p>",
        "<h2>Universe metrics</h2>",
    ]
    if full_table is not None and not full_table.empty:
        cols = ["SYMBOL", "SUBSECTOR", "CURRENT_PRICE", "RET_6M", "RS_VS_NIFTY_500_6M", "FUND_SCORE", "TECHNICAL_SCORE", "COMPOSITE_SCORE"]
        cols = [c for c in cols if c in full_table.columns]
        df_show = full_table[cols].copy()
        if "RET_6M" in df_show.columns:
            df_show["RET_6M"] = (df_show["RET_6M"] * 100).round(1).astype(str) + "%"
        if "RS_VS_NIFTY_500_6M" in df_show.columns:
            df_show["RS_VS_NIFTY_500_6M"] = (df_show["RS_VS_NIFTY_500_6M"] * 100).round(1).astype(str) + "%"
        html_parts.append("<table><thead><tr>")
        for c in cols:
            html_parts.append(f"<th>{c}</th>")
        html_parts.append("</tr></thead><tbody>")
        for _, row in df_show.iterrows():
            html_parts.append("<tr>")
            for c in cols:
                v = row.get(c, "")
                html_parts.append(f"<td>{v}</td>")
            html_parts.append("</tr>")
        html_parts.append("</tbody></table>")
    html_parts += ["</body></html>"]
    DASHBOARD_HTML.write_text("\n".join(html_parts), encoding="utf-8")
    print(f"  Wrote {DASHBOARD_HTML}")
    print("  Phase 5 done.")


if __name__ == "__main__":
    run_phase5()
