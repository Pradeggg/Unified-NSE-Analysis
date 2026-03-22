#!/usr/bin/env python3
"""
Phase 5: Stock narratives.
Combines holdings, fundamental_by_stock, and market_sentiment into stock_narratives.json and stock_narratives.md.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

try:
    from config import (
        OUTPUT_DIR,
        HOLDINGS_CSV_OUT,
        FUNDAMENTAL_BY_STOCK_CSV,
        FUNDAMENTAL_DETAILS_CSV,
        MARKET_SENTIMENT_MD,
        STOCK_NARRATIVES_JSON,
        STOCK_NARRATIVES_MD,
        WORKING_SECTOR,
    )
except ImportError:
    OUTPUT_DIR = Path(__file__).resolve().parent / "output"
    HOLDINGS_CSV_OUT = OUTPUT_DIR / "holdings.csv"
    FUNDAMENTAL_BY_STOCK_CSV = OUTPUT_DIR / "fundamental_by_stock.csv"
    FUNDAMENTAL_DETAILS_CSV = OUTPUT_DIR / "fundamental_details.csv"
    MARKET_SENTIMENT_MD = OUTPUT_DIR / "market_sentiment.md"
    STOCK_NARRATIVES_JSON = OUTPUT_DIR / "stock_narratives.json"
    STOCK_NARRATIVES_MD = OUTPUT_DIR / "stock_narratives.md"
    WORKING_SECTOR = Path(__file__).resolve().parent.parent / "working-sector"


def _parse_sentiment_by_stock(md_path: Path) -> dict[str, str]:
    """Extract per-stock sentiment blocks from market_sentiment.md (## Stock: SYMBOL ...)."""
    out = {}
    if not md_path.exists():
        return out
    text = md_path.read_text(encoding="utf-8")
    pattern = re.compile(r"##\s*Stock:\s*(\w+)\s*\n(.*?)(?=\n##\s|\Z)", re.DOTALL)
    for m in pattern.finditer(text):
        sym, block = m.group(1).strip(), m.group(2).strip()
        out[sym] = block
    return out


def _load_fundamental_details() -> dict[str, dict] | None:
    """Load P&L, quarterly, balance sheet, ratios by symbol. Tries portfolio output then working-sector/output/fundamental_details.csv."""
    import pandas as pd
    candidates = [Path(FUNDAMENTAL_DETAILS_CSV)]
    try:
        ws = Path(WORKING_SECTOR) / "output" / "fundamental_details.csv"
        candidates.append(ws)
    except Exception:
        pass
    for path in candidates:
        if not path.exists():
            continue
        try:
            df = pd.read_csv(path)
            col = "symbol" if "symbol" in df.columns else "SYMBOL"
            df[col] = df[col].astype(str).str.strip().str.upper()
            out = {}
            for _, r in df.iterrows():
                sym = r[col]
                out[sym] = {
                    k: str(r[k]).strip()
                    for k in ("pnl_summary", "quarterly_summary", "balance_sheet_summary", "ratios_summary")
                    if k in r.index and pd.notna(r.get(k)) and str(r.get(k)).strip()
                }
            return out if out else None
        except Exception:
            continue
    return None


def _sentiment_to_one_line(sent_block: str, max_chars: int = 120) -> str | None:
    """
    Extract a single clean sentence from a sentiment block for use in narratives.
    Strips out 'Sources (retrieved...)', '1. Title:', 'URL:', 'Excerpt:' and similar.
    Returns None if only structured source list (no prose).
    """
    if not sent_block or not sent_block.strip():
        return None
    # Take only content before structured source list
    for sep in ("Sources (retrieved", "1. Title:", "2. Title:", "URL: http", "Excerpt:", "\n1. "):
        idx = sent_block.find(sep)
        if idx != -1:
            sent_block = sent_block[:idx]
    sent_block = sent_block.strip()
    if not sent_block:
        return None
    # Take first sentence or first max_chars of prose
    first_line = sent_block.split("\n")[0].strip()
    for end in (". ", ".\n", "? ", "! "):
        i = first_line.find(end)
        if i != -1:
            first_line = first_line[: i + 1].strip()
            break
    if len(first_line) > max_chars:
        first_line = first_line[: max_chars - 1].rstrip()
        if not first_line.endswith("."):
            first_line += "…"
    # Skip if it looks like a source header or URL
    if re.match(r"^(Sources|Title:|URL:|Excerpt:|Retrieved:|\d+\.)\s*", first_line, re.I):
        return None
    if first_line.startswith("http") or "http" in first_line[:50]:
        return None
    return first_line if len(first_line) > 20 else None


def _format_fundamental_line(fund_row) -> str | None:
    """Format *Fundamental (0–100):* **Earnings Quality:** x | ... like working-sector."""
    if fund_row is None:
        return None
    labels = [
        ("EARNINGS_QUALITY", "Earnings Quality"),
        ("SALES_GROWTH", "Sales Growth"),
        ("FINANCIAL_STRENGTH", "Financial Strength"),
        ("INSTITUTIONAL_BACKING", "Institutional Backing"),
    ]
    parts = []
    for col, label in labels:
        if col in fund_row.index and fund_row.get(col) is not None:
            try:
                v = float(fund_row[col])
                parts.append(f"**{label}:** {v:.1f}")
            except (TypeError, ValueError):
                pass
    if not parts:
        return None
    return "*Fundamental (0–100):* " + " | ".join(parts)


def run_phase5() -> dict:
    """Run Phase 5: stock narratives. Writes stock_narratives.json, stock_narratives.md. Structure matches working-sector (fundamental breakdown, P&L, quarterly, balance sheet, ratios)."""
    OUTPUT_DIR.mkdir(exist_ok=True, parents=True)
    if not HOLDINGS_CSV_OUT.exists():
        STOCK_NARRATIVES_MD.write_text("# Stock narratives\n\nRun Phase 0 first.\n", encoding="utf-8")
        return {"n_stocks": 0, "note": "No holdings; run Phase 0 first."}

    import pandas as pd
    holdings = pd.read_csv(HOLDINGS_CSV_OUT)
    fund = pd.read_csv(FUNDAMENTAL_BY_STOCK_CSV) if FUNDAMENTAL_BY_STOCK_CSV.exists() else None
    details_by_sym = _load_fundamental_details() or {}
    sentiment_by_stock = _parse_sentiment_by_stock(MARKET_SENTIMENT_MD)

    narratives = []
    md_lines = ["# Stock narratives (with fundamental details)", ""]
    md_lines.append("Per-stock narratives, fundamental scores (0–100), and when available: P&L (Sales, Net Profit, EPS, YoY), quarterly results, balance sheet (Equity, Debt, Cash, D/E), and ratios (ROCE, ROE, EPS, PE, PB, OPM, NPM, etc.).")
    md_lines.append("")

    for _, row in holdings.iterrows():
        sym = str(row.get("symbol", "")).strip().upper()
        if not sym:
            continue
        qty = row.get("quantity", 0)
        val = row.get("value_rs", 0)
        rec = "HOLD"

        fund_row = None
        if fund is not None and not fund.empty and "symbol" in fund.columns:
            match = fund[fund["symbol"].astype(str).str.strip().str.upper() == sym]
            if not match.empty:
                fund_row = match.iloc[0]

        fund_score = None
        if fund_row is not None and "ENHANCED_FUND_SCORE" in fund_row.index:
            try:
                fund_score = float(fund_row["ENHANCED_FUND_SCORE"])
            except (TypeError, ValueError):
                pass

        extra = details_by_sym.get(sym, {})
        sent_text = sentiment_by_stock.get(sym, "")
        sentiment_line = _sentiment_to_one_line(sent_text)

        # Build structured narrative (same format as working-sector auto_components_comprehensive_report)
        block = []
        fund_line = _format_fundamental_line(fund_row)
        if fund_line:
            block.append(fund_line)
            block.append("")
        if extra.get("pnl_summary"):
            block.append(f"*P&L:* {extra['pnl_summary']}")
            block.append("")
        if extra.get("quarterly_summary"):
            block.append(f"*Quarterly:* {extra['quarterly_summary']}")
            block.append("")
        if extra.get("balance_sheet_summary"):
            block.append(f"*Balance sheet:* {extra['balance_sheet_summary']}")
            block.append("")
        if extra.get("ratios_summary"):
            block.append(f"*Ratios:* {extra['ratios_summary']}")
            block.append("")
        # Closing line: position, optional sentiment, recommendation
        closing = [f"Holdings: {qty} shares, value Rs {val:,.0f}."]
        if sentiment_line:
            closing.append(f" {sentiment_line}")
        else:
            closing.append(" News and sentiment: see Market sentiment tab.")
        closing.append(f" Recommendation: {rec}.")
        block.append(" ".join(closing))

        narrative = "\n".join(block)
        entry = {
            "symbol": sym,
            "quantity": int(qty),
            "value_rs": float(val) if isinstance(val, (int, float)) else None,
            "fund_score": fund_score,
            "recommendation": rec,
            "narrative": narrative,
        }
        if fund_row is not None:
            for col in ("EARNINGS_QUALITY", "SALES_GROWTH", "FINANCIAL_STRENGTH", "INSTITUTIONAL_BACKING"):
                if col in fund_row.index and pd.notna(fund_row.get(col)):
                    try:
                        entry[f"fund_{col.lower()}"] = float(fund_row[col])
                    except (TypeError, ValueError):
                        pass
        for k in ("pnl_summary", "quarterly_summary", "balance_sheet_summary", "ratios_summary"):
            if extra.get(k):
                entry[k] = extra[k]
        narratives.append(entry)

        md_lines.append(f"### {sym}")
        md_lines.append("")
        md_lines.append(narrative)
        md_lines.append("")

    with open(STOCK_NARRATIVES_JSON, "w", encoding="utf-8") as f:
        json.dump(narratives, f, indent=2)

    STOCK_NARRATIVES_MD.write_text("\n".join(md_lines), encoding="utf-8")
    return {"n_stocks": len(narratives), "output_json": str(STOCK_NARRATIVES_JSON), "output_md": str(STOCK_NARRATIVES_MD)}


if __name__ == "__main__":
    run_phase5()
    print("Phase 5 done.", STOCK_NARRATIVES_JSON, STOCK_NARRATIVES_MD)
