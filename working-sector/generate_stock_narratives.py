#!/usr/bin/env python3
"""
Generate a short equity narrative for each stock in the final pipeline data
using Ollama Granite 4. Reads phase3_full_with_composite.csv, fundamental
scores (earnings quality, sales growth, etc.), and optional P&L/quarterly/BS
details from fundamental_details.csv. Writes stock_narratives.md and .json.
"""
import json
import re
import sys
import time
from pathlib import Path

import pandas as pd
import requests

WORKING_SECTOR = Path(__file__).resolve().parent
PROJECT_ROOT = WORKING_SECTOR.parent
# Use sector-aware config when available (e.g. when run via CLI/agent)
try:
    from config import OUTPUT_DIR, UNIVERSE_CSV, SECTOR_DISPLAY_NAME
except ImportError:
    OUTPUT_DIR = WORKING_SECTOR / "output" / "auto_components"
    UNIVERSE_CSV = WORKING_SECTOR / "auto_components_universe.csv"
    SECTOR_DISPLAY_NAME = "Auto Components"
FULL_TABLE = OUTPUT_DIR / "phase3_full_with_composite.csv"
FUNDAMENTAL_CSV = PROJECT_ROOT / "organized" / "data" / "fundamental_scores_database.csv"
if not FUNDAMENTAL_CSV.exists():
    FUNDAMENTAL_CSV = PROJECT_ROOT / "data" / "fundamental_scores_database.csv"
FUNDAMENTAL_DETAILS_CSV = OUTPUT_DIR / "fundamental_details.csv"  # P&L, quarterly, balance sheet
NARRATIVES_MD = OUTPUT_DIR / "stock_narratives.md"
NARRATIVES_JSON = OUTPUT_DIR / "stock_narratives.json"
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "granite4:latest"
DELAY_SEC = 1.5  # rate limit between calls


def get_name(symbol: str, universe: pd.DataFrame) -> str:
    if universe is None or universe.empty:
        return symbol
    row = universe[universe["SYMBOL"].str.strip().str.upper() == symbol.upper()]
    if not row.empty and "NAME" in row.columns:
        return str(row["NAME"].iloc[0]).strip()
    return symbol


def load_fundamental_details() -> pd.DataFrame | None:
    """Load fundamental breakdown (EARNINGS_QUALITY, SALES_GROWTH, etc.)."""
    if not FUNDAMENTAL_CSV.exists():
        return None
    df = pd.read_csv(FUNDAMENTAL_CSV)
    if "symbol" in df.columns:
        df["SYMBOL"] = df["symbol"].str.strip().str.upper()
    # Keep latest per symbol
    if "processed_date" in df.columns:
        df = df.sort_values("processed_date").drop_duplicates(subset=["SYMBOL"], keep="last")
    return df


def load_fundamental_details_extra() -> pd.DataFrame | None:
    """Load P&L, quarterly, balance sheet summaries (from fetch_screener_fundamental_details.R)."""
    if not FUNDAMENTAL_DETAILS_CSV.exists():
        return None
    df = pd.read_csv(FUNDAMENTAL_DETAILS_CSV)
    if "symbol" in df.columns:
        df["SYMBOL"] = df["symbol"].str.strip().str.upper()
    return df


def row_to_summary(
    row: pd.Series,
    name: str,
    fund_row: pd.Series | None,
    extra_row: pd.Series | None = None,
) -> str:
    price = row.get("CURRENT_PRICE")
    ret_1m = row.get("RET_1M")
    ret_3m = row.get("RET_3M")
    ret_6m = row.get("RET_6M")
    rs_500 = row.get("RS_VS_NIFTY_500_6M")
    rsi = row.get("RSI")
    tech = row.get("TECHNICAL_SCORE")
    fund = row.get("FUND_SCORE")
    comp = row.get("COMPOSITE_SCORE")
    subsector = row.get("SUBSECTOR", "")
    pass_screen = row.get("PASS_SCREEN", False)
    parts = [
        f"Symbol: {row.get('SYMBOL', '')}; Name: {name}; Sub-sector: {subsector}.",
        f"Price: Rs {price:.2f}" if pd.notna(price) else "",
        (f"Returns: 1M {ret_1m*100:.1f}%, 3M {ret_3m*100:.1f}%, 6M {ret_6m*100:.1f}%" if all(pd.notna(x) for x in (ret_1m, ret_3m, ret_6m)) else (f"6M return: {ret_6m*100:.1f}%" if pd.notna(ret_6m) else "")),
        f"Relative strength vs Nifty 500 (6M): {rs_500*100:.1f}%" if pd.notna(rs_500) else "",
        f"RSI: {rsi:.1f}" if pd.notna(rsi) else "",
        f"Technical score (0-100): {tech:.1f}" if pd.notna(tech) else "",
        f"Fundamental score (0-100): {fund:.1f}" if pd.notna(fund) else "",
        f"Composite score: {comp:.1f}" if pd.notna(comp) else "",
        f"Passes screen (FUND>=70 & RS_6M>0): {pass_screen}.",
    ]
    # Fundamental details (0-100 scale from Screener pipeline)
    if fund_row is not None and not fund_row.empty:
        for col, label in [
            ("EARNINGS_QUALITY", "Earnings quality"),
            ("SALES_GROWTH", "Sales growth"),
            ("FINANCIAL_STRENGTH", "Financial strength"),
            ("INSTITUTIONAL_BACKING", "Institutional backing"),
        ]:
            if col in fund_row.index:
                v = fund_row.get(col)
                if pd.notna(v):
                    try:
                        parts.append(f"{label}: {float(v):.1f}")
                    except (TypeError, ValueError):
                        parts.append(f"{label}: {v}")
    # P&L changes, quarterly results, balance sheet, ratios (from fundamental_details.csv)
    if extra_row is not None and not extra_row.empty:
        for col, label in [
            ("pnl_summary", "P&L"),
            ("quarterly_summary", "Quarterly"),
            ("balance_sheet_summary", "Balance sheet"),
            ("ratios_summary", "Ratios"),
        ]:
            if col in extra_row.index:
                v = extra_row.get(col)
                if pd.notna(v) and str(v).strip():
                    parts.append(f"{label}: {str(v).strip()}")
    return " ".join(p for p in parts if p).strip()


def _parse_recommendation(narrative: str) -> tuple[str, str]:
    """Extract 'Recommendation: X. Rationale' from narrative. Returns (recommendation, rationale_or_empty)."""
    if not narrative:
        return ("", "")
    # Match "Recommendation: Buy/Accumulate/Hold/Reduce/Avoid." then optional sentence
    m = re.search(r"\*?\*?Recommendation:\s*(\*?\*?(?:Buy|Accumulate|Hold|Reduce|Avoid)\*?\*?)\.?\s*([^.]*\.?)?", narrative, re.I)
    if m:
        rec = m.group(1).strip().strip("*")
        rationale = (m.group(2) or "").strip()
        return (rec, rationale)
    return ("", "")


def get_narrative_from_ollama(summary: str, symbol: str, model: str = OLLAMA_MODEL) -> str:
    prompt = (
        "You are an equity research analyst. Using ONLY the following data, write a short narrative that:\n\n"
        "1. KEY METRICS (synthesize in 1–2 sentences): Price, 1M/3M/6M returns, relative strength vs Nifty 500, RSI, technical score (0–100), and the **fundamental score (0–100)**. "
        "Call out the fundamental score clearly as the main financial-quality metric.\n\n"
        "2. KEY FINANCIAL RATIOS / FUNDAMENTALS: Summarize the four sub-scores (earnings quality, sales growth, financial strength, institutional backing, all 0–100) and, if provided, "
        "P&L (sales/profit, YoY), quarterly progression, balance sheet (equity, debt, cash, Debt/Equity), and Ratios (ROCE, ROE, EPS, PE, PB, OPM, NPM, etc.). Synthesize these into a clear view of financial health and growth.\n\n"
        "3. RECOMMENDATION: End with a single line: **Recommendation: [Buy | Accumulate | Hold | Reduce | Avoid].** "
        "Then one short sentence justifying it based on the metrics (e.g. strong momentum + solid fundamental score = Accumulate; weak RS + low fund score = Avoid). "
        "Use only the data given; be concise and actionable.\n\n"
        "Data:\n"
        + summary
    )
    try:
        r = requests.post(
            OLLAMA_URL,
            json={"model": model, "prompt": prompt, "stream": False},
            timeout=120,
        )
        r.raise_for_status()
        out = r.json()
        return (out.get("response") or "").strip()
    except Exception as e:
        return f"[Narrative unavailable: {e}]"


def write_narratives_md(narratives: list[dict]) -> None:
    """Write stock narratives to markdown with TOC, fundamental table, and paragraph formatting."""
    def slug(symbol: str, name: str) -> str:
        s = f"{symbol}-{name}".lower()
        for c in " &.–'":
            s = s.replace(c, "-")
        return "".join(c if c.isalnum() or c == "-" else "" for c in s).replace("--", "-").strip("-")

    lines = [
        f"# {SECTOR_DISPLAY_NAME} – Stock Narratives",
        "",
        "Short narratives generated from pipeline data and fundamental details (Ollama Granite 4).",
        "",
        "---",
        "",
        "## Table of contents",
        "",
    ]
    for n in narratives:
        anchor = slug(n["symbol"], n["name"])
        lines.append(f"- [{n['symbol']} – {n['name']}](#{anchor})")
    lines += ["", "---", ""]

    for n in narratives:
        lines.append(f"## {n['symbol']} – {n['name']}")
        lines.append("")
        fund_keys = [k for k in n if k.startswith("fund_")]
        if fund_keys:
            labels = [k.replace("fund_", "").replace("_", " ").title() for k in sorted(fund_keys)]
            values = [f"{n[k]:.1f}" for k in sorted(fund_keys)]
            header = "| " + " | ".join(labels) + " |"
            sep = "|" + "|".join(["---"] * len(labels)) + "|"
            row = "| " + " | ".join(values) + " |"
            lines.append("*Fundamental scores (0–100)*")
            lines.append("")
            lines.append(header)
            lines.append(sep)
            lines.append(row)
            lines.append("")
        for key, label in [
            ("pnl_summary", "P&L (key items, YoY)"),
            ("quarterly_summary", "Quarterly results"),
            ("balance_sheet_summary", "Balance sheet"),
            ("ratios_summary", "Ratios (ROCE, ROE, EPS, PE, PB, etc.)"),
        ]:
            if n.get(key) and str(n[key]).strip():
                lines.append(f"*{label}:* " + str(n[key]).strip())
                lines.append("")
        narrative = (n.get("narrative") or "").strip()
        if narrative:
            for para in narrative.split("\n\n"):
                para = para.strip()
                if para:
                    lines.append(para)
                    lines.append("")
        lines.append("")
    NARRATIVES_MD.write_text("\n".join(lines), encoding="utf-8")


def main():
    if not FULL_TABLE.exists():
        print("Missing", FULL_TABLE, "- run pipeline first.")
        sys.exit(1)
    df = pd.read_csv(FULL_TABLE)
    universe = None
    if UNIVERSE_CSV.exists():
        universe = pd.read_csv(UNIVERSE_CSV)
    fund_details = load_fundamental_details()
    if fund_details is not None:
        print("Loaded fundamental details for", len(fund_details), "symbols.")
    extra_details = load_fundamental_details_extra()
    if extra_details is not None and not extra_details.empty:
        print("Loaded P&L/quarterly/balance-sheet details for", len(extra_details), "symbols.")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    narratives = []
    for i, (_, row) in enumerate(df.iterrows()):
        symbol = str(row.get("SYMBOL", "")).strip().upper()
        name = get_name(symbol, universe)
        fund_row = None
        if fund_details is not None and not fund_details.empty:
            match = fund_details[fund_details["SYMBOL"] == symbol]
            if not match.empty:
                fund_row = match.iloc[0]
        extra_row = None
        if extra_details is not None and not extra_details.empty:
            match = extra_details[extra_details["SYMBOL"] == symbol]
            if not match.empty:
                extra_row = match.iloc[0]
        summary = row_to_summary(row, name, fund_row, extra_row)
        print(f"[{i+1}/{len(df)}] {symbol} ... ", end="", flush=True)
        narrative = get_narrative_from_ollama(summary, symbol)
        rec, rec_rationale = _parse_recommendation(narrative)
        entry = {"symbol": symbol, "name": name, "narrative": narrative}
        if rec:
            entry["recommendation"] = rec
            if rec_rationale:
                entry["recommendation_rationale"] = rec_rationale
        if fund_row is not None:
            for col in ["EARNINGS_QUALITY", "SALES_GROWTH", "FINANCIAL_STRENGTH", "INSTITUTIONAL_BACKING"]:
                if col in fund_row.index and pd.notna(fund_row.get(col)):
                    entry[f"fund_{col.lower()}"] = float(fund_row[col])
        if extra_row is not None:
            for col in ["pnl_summary", "quarterly_summary", "balance_sheet_summary", "ratios_summary"]:
                if col in extra_row.index and pd.notna(extra_row.get(col)) and str(extra_row[col]).strip():
                    entry[col] = str(extra_row[col]).strip()
        narratives.append(entry)
        print("ok", flush=True)
        time.sleep(DELAY_SEC)
    # Write JSON
    with open(NARRATIVES_JSON, "w", encoding="utf-8") as f:
        json.dump(narratives, f, indent=2, ensure_ascii=False)
    write_narratives_md(narratives)
    print("Wrote", NARRATIVES_MD, "and", NARRATIVES_JSON)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--format-only":
        if not NARRATIVES_JSON.exists():
            print("Missing", NARRATIVES_JSON, "- run full pipeline first.")
            sys.exit(1)
        narratives = json.loads(NARRATIVES_JSON.read_text(encoding="utf-8"))
        write_narratives_md(narratives)
        print("Reformatted", NARRATIVES_MD)
    else:
        main()
