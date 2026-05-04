#!/usr/bin/env python3
"""
Phase 5: Stock narratives.
Combines holdings, technical_by_stock, fundamental_by_stock, and market_sentiment
into rich per-stock narrative cards in stock_narratives.json and stock_narratives.md.
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
        TECHNICAL_BY_STOCK_CSV,
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
    TECHNICAL_BY_STOCK_CSV = OUTPUT_DIR / "technical_by_stock.csv"
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


def _load_fundamental_details() -> dict[str, dict]:
    """Load P&L, quarterly, balance sheet, ratios by symbol."""
    import pandas as pd
    candidates = [Path(FUNDAMENTAL_DETAILS_CSV)]
    try:
        candidates.append(Path(WORKING_SECTOR) / "output" / "fundamental_details.csv")
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
            return out if out else {}
        except Exception:
            continue
    return {}


def _sentiment_to_one_line(sent_block: str, max_chars: int = 150) -> str | None:
    """Extract a single clean sentence from a sentiment block."""
    if not sent_block or not sent_block.strip():
        return None
    for sep in ("Sources (retrieved", "1. Title:", "2. Title:", "URL: http", "Excerpt:", "\n1. "):
        idx = sent_block.find(sep)
        if idx != -1:
            sent_block = sent_block[:idx]
    sent_block = sent_block.strip()
    if not sent_block:
        return None
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
    if re.match(r"^(Sources|Title:|URL:|Excerpt:|Retrieved:|\d+\.)\s*", first_line, re.I):
        return None
    if first_line.startswith("http") or "http" in first_line[:50]:
        return None
    return first_line if len(first_line) > 20 else None


def _composite_decision(tech_score: float, fund_score: float) -> str:
    combined = tech_score * 0.6 + fund_score * 0.4
    if combined >= 70:   return "STRONG ADD"
    elif combined >= 58: return "ADD"
    elif combined >= 42: return "HOLD"
    elif combined >= 28: return "REDUCE"
    else:                return "SELL"


def _trend_emoji(trend: str) -> str:
    t = (trend or "").upper()
    if "STRONG_BULL" in t or "STRONG BULL" in t: return "🚀"
    if "BULL" in t:  return "📈"
    if "BEAR" in t:  return "📉"
    if "NEUTRAL" in t: return "➡"
    return ""


def _chg_arrow(val) -> str:
    try:
        f = float(val)
        return f"{'▲' if f >= 0 else '▼'}{abs(f):.1f}%"
    except (TypeError, ValueError):
        return "—"


def run_phase5() -> dict:
    """Run Phase 5: stock narratives. Writes stock_narratives.json, stock_narratives.md."""
    OUTPUT_DIR.mkdir(exist_ok=True, parents=True)
    if not HOLDINGS_CSV_OUT.exists():
        STOCK_NARRATIVES_MD.write_text("# Stock narratives\n\nRun Phase 0 first.\n", encoding="utf-8")
        return {"n_stocks": 0, "note": "No holdings; run Phase 0 first."}

    import pandas as pd

    holdings = pd.read_csv(HOLDINGS_CSV_OUT)

    # Technical data — primary source for scores, rec, RSI, changes
    tech_dict: dict[str, dict] = {}
    if TECHNICAL_BY_STOCK_CSV.exists():
        tech_df = pd.read_csv(TECHNICAL_BY_STOCK_CSV)
        tech_df["symbol"] = tech_df["symbol"].astype(str).str.strip().str.upper()
        for _, r in tech_df.iterrows():
            tech_dict[r["symbol"]] = r.to_dict()

    # Fundamental breakdown (earnings quality etc.) — 64 symbols
    fund_dict: dict[str, dict] = {}
    if FUNDAMENTAL_BY_STOCK_CSV.exists():
        fund_df = pd.read_csv(FUNDAMENTAL_BY_STOCK_CSV)
        sym_col = "symbol" if "symbol" in fund_df.columns else "SYMBOL"
        fund_df[sym_col] = fund_df[sym_col].astype(str).str.strip().str.upper()
        for _, r in fund_df.iterrows():
            fund_dict[r[sym_col]] = r.to_dict()

    details_by_sym = _load_fundamental_details()
    sentiment_by_stock = _parse_sentiment_by_stock(MARKET_SENTIMENT_MD)

    narratives = []
    md_lines = ["# Stock narratives", "", "Per-stock narratives with technical analysis, fundamental scores (0–100), and market context.", ""]

    for _, row in holdings.iterrows():
        sym = str(row.get("symbol", "")).strip().upper()
        if not sym:
            continue

        qty   = int(row.get("quantity") or 0)
        val   = float(row.get("value_rs") or 0)

        # ── Technical data ───────────────────────────────────────────────
        td = tech_dict.get(sym, {})
        tech_score   = float(td.get("technical_score") or 50)
        rsi          = td.get("rsi")
        trend        = str(td.get("trend_signal") or "UNKNOWN")
        trading_sig  = str(td.get("trading_signal") or "HOLD")
        tech_rec     = str(td.get("recommendation") or "HOLD")
        chg_1d       = td.get("change_1d_pct")
        chg_1w       = td.get("change_1w_pct")
        chg_1m       = td.get("change_1m_pct")
        rel_str      = td.get("relative_strength")
        current_price = td.get("current_price")
        data_src     = str(td.get("data_source") or "none")

        # ── Fundamental data ─────────────────────────────────────────────
        fd = fund_dict.get(sym, {})
        # Prefer enhanced_fund_score from tech CSV (comprehensive pipeline); fallback to fund CSV
        enh_fund = td.get("enhanced_fund_score")
        import math
        if enh_fund is None or (isinstance(enh_fund, float) and math.isnan(enh_fund)):
            enh_fund = None
            if "ENHANCED_FUND_SCORE" in fd:
                try:
                    v = float(fd["ENHANCED_FUND_SCORE"])
                    if not math.isnan(v):
                        enh_fund = v
                except (TypeError, ValueError):
                    pass
        fund_score = float(enh_fund) if enh_fund is not None else 50.0

        eq  = fd.get("EARNINGS_QUALITY")
        sg  = fd.get("SALES_GROWTH")
        fs_ = fd.get("FINANCIAL_STRENGTH")
        ib  = fd.get("INSTITUTIONAL_BACKING")
        has_fund_breakdown = any(v is not None for v in [eq, sg, fs_, ib])
        # Treat placeholder 10.0 as no data
        if has_fund_breakdown and all(float(v or 0) <= 10.0 for v in [eq, sg, fs_, ib] if v is not None):
            has_fund_breakdown = False

        # ── Composite decision ───────────────────────────────────────────
        decision = _composite_decision(tech_score, fund_score)

        extra = details_by_sym.get(sym, {})
        sentiment_line = _sentiment_to_one_line(sentiment_by_stock.get(sym, ""))

        # ── Build narrative text ─────────────────────────────────────────
        block = []

        # 1. Technical snapshot
        trend_em = _trend_emoji(trend)
        tech_parts = [f"Technical score: **{tech_score:.0f}/100**"]
        if rsi is not None:
            try:
                rv = float(rsi)
                rsi_note = " *(oversold)*" if rv < 30 else (" *(overbought)*" if rv > 70 else "")
                tech_parts.append(f"RSI: {rv:.1f}{rsi_note}")
            except (TypeError, ValueError):
                pass
        if trend and trend != "UNKNOWN":
            tech_parts.append(f"Trend: {trend_em}{trend}")
        if trading_sig and trading_sig != "UNKNOWN":
            tech_parts.append(f"Signal: **{trading_sig}**")
        block.append("*Technical:* " + " | ".join(tech_parts))
        block.append("")

        # 2. Price momentum
        momentum_parts = []
        for label, chg in [("1D", chg_1d), ("1W", chg_1w), ("1M", chg_1m)]:
            if chg is not None:
                try:
                    momentum_parts.append(f"{label}: {_chg_arrow(chg)}")
                except (TypeError, ValueError):
                    pass
        if rel_str is not None:
            try: momentum_parts.append(f"Rel. Strength: {float(rel_str):.1f}")
            except (TypeError, ValueError): pass
        if momentum_parts:
            block.append("*Momentum:* " + " | ".join(momentum_parts))
            block.append("")

        # 3. Fundamental breakdown (if real data available)
        if has_fund_breakdown:
            fund_parts = []
            for col_key, label in [("EARNINGS_QUALITY", "Earnings Quality"), ("SALES_GROWTH", "Sales Growth"),
                                    ("FINANCIAL_STRENGTH", "Financial Strength"), ("INSTITUTIONAL_BACKING", "Institutional Backing")]:
                v = fd.get(col_key)
                if v is not None:
                    try: fund_parts.append(f"**{label}:** {float(v):.1f}")
                    except (TypeError, ValueError): pass
            if fund_parts:
                block.append("*Fundamental (0–100):* " + " | ".join(fund_parts))
                block.append("")
        elif enh_fund is not None:
            block.append(f"*Fundamental score:* **{fund_score:.0f}/100** (composite enhanced score)")
            block.append("")

        # 4. P&L / quarterly / balance sheet / ratios (when available)
        for key, label in [("pnl_summary", "P&L"), ("quarterly_summary", "Quarterly"),
                            ("balance_sheet_summary", "Balance sheet"), ("ratios_summary", "Ratios")]:
            if extra.get(key):
                block.append(f"*{label}:* {extra[key]}")
                block.append("")

        # 5. Closing: position + sentiment + decision
        closing = [f"Holdings: **{qty} shares**, value ₹{val:,.0f}."]
        if current_price:
            try: closing.append(f" Current price: ₹{float(current_price):,.2f}.")
            except (TypeError, ValueError): pass
        if sentiment_line:
            closing.append(f" {sentiment_line}")
        closing.append(f" **Decision: {decision}**")
        if data_src and data_src != "none":
            closing.append(f" *(data: {data_src})*")
        block.append("".join(closing))

        narrative = "\n".join(block)

        entry: dict = {
            "symbol": sym,
            "quantity": qty,
            "value_rs": val,
            "current_price": current_price,
            "technical_score": tech_score,
            "rsi": rsi,
            "trend_signal": trend,
            "trading_signal": trading_sig,
            "change_1d_pct": chg_1d,
            "change_1w_pct": chg_1w,
            "change_1m_pct": chg_1m,
            "relative_strength": rel_str,
            "fund_score": fund_score,
            "recommendation": decision,   # composite decision
            "tech_recommendation": tech_rec,
            "narrative": narrative,
            "data_source": data_src,
        }
        # Fundamental breakdown fields
        if has_fund_breakdown:
            for col_key in ("EARNINGS_QUALITY", "SALES_GROWTH", "FINANCIAL_STRENGTH", "INSTITUTIONAL_BACKING"):
                v = fd.get(col_key)
                if v is not None:
                    try: entry[f"fund_{col_key.lower()}"] = float(v)
                    except (TypeError, ValueError): pass
        for k in ("pnl_summary", "quarterly_summary", "balance_sheet_summary", "ratios_summary"):
            if extra.get(k):
                entry[k] = extra[k]
        narratives.append(entry)

        md_lines.append(f"### {sym}  [{decision}]  score: {tech_score:.0f}")
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
