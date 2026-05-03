#!/usr/bin/env python3
"""
Phase 3: Technical analysis per holding.

Data source priority:
  1. comprehensive_nse_enhanced_*.csv  — latest full-pipeline analysis
     (sector_rotation_report.py output in reports/generated_csv/)
  2. nse_analysis.db stocks_analysis   — pre-computed DB scores
  3. nse_sec_full_data.csv             — raw OHLCV; RSI/SMA computed on the fly
"""
from __future__ import annotations

import glob
from pathlib import Path

try:
    from config import OUTPUT_DIR, HOLDINGS_CSV_OUT, TECHNICAL_BY_STOCK_CSV, TECHNICAL_SUMMARY_MD
except ImportError:
    OUTPUT_DIR = Path(__file__).resolve().parent / "output"
    HOLDINGS_CSV_OUT = OUTPUT_DIR / "holdings.csv"
    TECHNICAL_BY_STOCK_CSV = OUTPUT_DIR / "technical_by_stock.csv"
    TECHNICAL_SUMMARY_MD = OUTPUT_DIR / "technical_summary.md"

_HERE = Path(__file__).resolve().parent
REPORTS_DIR    = _HERE.parent / "reports" / "generated_csv"
NSE_DB         = _HERE.parent / "data" / "nse_analysis.db"
NSE_SEC_FULL_CSV = _HERE.parent / "data" / "nse_sec_full_data.csv"

# Map trading_signal → friendly recommendation
_SIGNAL_MAP = {
    "STRONG_BUY": "STRONG ADD",
    "BUY": "ADD",
    "HOLD": "HOLD",
    "WEAK_HOLD": "REDUCE",
    "SELL": "SELL",
}


def _rsi(closes: "pd.Series", period: int = 14) -> float:
    """Compute RSI(14) on a close-price series. Returns NaN if insufficient data."""
    import pandas as pd
    if len(closes) < period + 1:
        return float("nan")
    delta = closes.diff().dropna()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, float("nan"))
    rsi_series = 100 - (100 / (1 + rs))
    v = rsi_series.dropna()
    return float(v.iloc[-1]) if len(v) else float("nan")


def _tech_score_from_rsi_sma(closes: "pd.Series") -> dict:
    """Derive a basic technical score from price series when DB data unavailable."""
    import pandas as pd, numpy as np
    result: dict = {}
    if len(closes) < 20:
        return result
    c = closes.reset_index(drop=True)
    last = float(c.iloc[-1])
    result["current_price"] = last
    result["rsi"] = round(_rsi(c), 1)
    sma50 = float(c.tail(50).mean()) if len(c) >= 50 else float("nan")
    sma200 = float(c.tail(200).mean()) if len(c) >= 200 else float("nan")
    # change metrics
    result["change_1d"] = round((last / float(c.iloc[-2]) - 1) * 100, 2) if len(c) >= 2 else float("nan")
    result["change_1w"] = round((last / float(c.iloc[-6]) - 1) * 100, 2) if len(c) >= 6 else float("nan")
    result["change_1m"] = round((last / float(c.iloc[-22]) - 1) * 100, 2) if len(c) >= 22 else float("nan")
    # simple score: RSI + trend vs SMAs (0–100)
    rsi = result["rsi"]
    score = 50.0
    if not np.isnan(rsi):
        score += (rsi - 50) * 0.3
    if not np.isnan(sma50):
        score += 10 if last > sma50 else -10
    if not np.isnan(sma200):
        score += 10 if last > sma200 else -10
    score = max(0.0, min(100.0, score))
    result["technical_score"] = round(score, 1)
    if score >= 70:
        result["trend_signal"] = "BULLISH"
        result["trading_signal"] = "BUY"
    elif score >= 55:
        result["trend_signal"] = "NEUTRAL"
        result["trading_signal"] = "HOLD"
    elif score >= 35:
        result["trend_signal"] = "BEARISH"
        result["trading_signal"] = "WEAK_HOLD"
    else:
        result["trend_signal"] = "STRONG_BEARISH"
        result["trading_signal"] = "SELL"
    return result


def _latest_comprehensive_csv() -> Path | None:
    """Return the most recent comprehensive_nse_enhanced_*.csv from reports/generated_csv/."""
    candidates = sorted(
        REPORTS_DIR.rglob("comprehensive_nse_enhanced_*.csv"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def run_phase3() -> dict:
    """Run Phase 3: technical by stock. Writes technical_by_stock.csv, technical_summary.md."""
    import pandas as pd
    import sqlite3

    OUTPUT_DIR.mkdir(exist_ok=True, parents=True)
    if not HOLDINGS_CSV_OUT.exists():
        TECHNICAL_SUMMARY_MD.write_text(
            "# Technical summary\n\nRun Phase 0 first to generate holdings.\n", encoding="utf-8"
        )
        return {"n_stocks": 0, "note": "No holdings; run Phase 0 first."}

    holdings = pd.read_csv(HOLDINGS_CSV_OUT)
    symbols = holdings["symbol"].str.upper().tolist()

    # ── Source 1: comprehensive_nse_enhanced_*.csv (full pipeline output) ──
    comprehensive_data: dict = {}
    comp_csv = _latest_comprehensive_csv()
    if comp_csv:
        try:
            comp_df = pd.read_csv(comp_csv)
            comp_df["SYMBOL"] = comp_df["SYMBOL"].str.upper()
            comp_df = comp_df.drop_duplicates("SYMBOL")
            for _, row in comp_df.iterrows():
                comprehensive_data[row["SYMBOL"]] = {
                    "current_price":    row.get("CURRENT_PRICE"),
                    "technical_score":  row.get("TECHNICAL_SCORE"),
                    "rsi":              row.get("RSI"),
                    "trend_signal":     row.get("TREND_SIGNAL"),
                    "trading_signal":   row.get("TRADING_SIGNAL"),
                    "change_1d":        row.get("CHANGE_1D"),
                    "change_1w":        row.get("CHANGE_1W"),
                    "change_1m":        row.get("CHANGE_1M"),
                    "relative_strength":row.get("RELATIVE_STRENGTH"),
                    "enhanced_fund_score": row.get("ENHANCED_FUND_SCORE"),
                    "earnings_quality": row.get("EARNINGS_QUALITY"),
                    "financial_strength": row.get("FINANCIAL_STRENGTH"),
                }
            print(f"[phase3] Loaded {len(comprehensive_data)} symbols from {comp_csv.name}")
        except Exception as e:
            print(f"[phase3] Comprehensive CSV warning: {e}")

    # ── Source 2: nse_analysis.db — for symbols not in comprehensive CSV ────
    db_data: dict = {}
    missing_after_comp = [s for s in symbols if s not in comprehensive_data]
    if missing_after_comp and NSE_DB.exists():
        try:
            con = sqlite3.connect(NSE_DB)
            df_db = pd.read_sql(
                """SELECT symbol, current_price, technical_score, rsi,
                          trend_signal, trading_signal, change_1d, change_1w, change_1m,
                          relative_strength
                   FROM stocks_analysis
                   WHERE (symbol, analysis_date) IN (
                       SELECT symbol, MAX(analysis_date) FROM stocks_analysis GROUP BY symbol
                   )""",
                con,
            )
            con.close()
            df_db["symbol"] = df_db["symbol"].str.upper()
            for _, row in df_db.iterrows():
                if row["symbol"] in missing_after_comp:
                    db_data[row["symbol"]] = row.to_dict()
            print(f"[phase3] DB covered {len(db_data)} additional symbols")
        except Exception as e:
            print(f"[phase3] DB read warning: {e}")

    # ── Source 3: nse_sec_full_data.csv — compute RSI/SMA for remainder ────
    raw_data: dict = {}
    still_missing = [s for s in missing_after_comp if s not in db_data]
    if still_missing and NSE_SEC_FULL_CSV.exists():
        try:
            price_df = pd.read_csv(NSE_SEC_FULL_CSV, parse_dates=["TIMESTAMP"])
            price_df["SYMBOL"] = price_df["SYMBOL"].str.upper()
            for sym in still_missing:
                sub = price_df[price_df["SYMBOL"] == sym].sort_values("TIMESTAMP")
                if len(sub) >= 20:
                    result = _tech_score_from_rsi_sma(sub["CLOSE"])
                    if result:
                        raw_data[sym] = result
            print(f"[phase3] Computed scores for {len(raw_data)} symbols from raw price CSV")
        except Exception as e:
            print(f"[phase3] Raw CSV fallback warning: {e}")

    # ── Build output DataFrame ─────────────────────────────────────────────
    rows = []
    for _, h in holdings.iterrows():
        sym = str(h["symbol"]).upper()
        base = {
            "symbol":    h["symbol"],
            "quantity":  h["quantity"],
            "value_rs":  h["value_rs"],
        }
        if sym in comprehensive_data:
            d = comprehensive_data[sym]
            src = "comprehensive_csv"
        elif sym in db_data:
            d = db_data[sym]
            src = "db"
        elif sym in raw_data:
            d = raw_data[sym]
            src = "computed"
        else:
            d = {}
            src = "none"

        base["current_price"]    = d.get("current_price")
        base["technical_score"]  = d.get("technical_score", 50)
        base["rsi"]              = d.get("rsi")
        base["trend_signal"]     = d.get("trend_signal", "UNKNOWN")
        trading = d.get("trading_signal") or "HOLD"
        base["trading_signal"]   = trading
        base["recommendation"]   = _SIGNAL_MAP.get(str(trading).upper(), trading)
        base["change_1d_pct"]    = d.get("change_1d")
        base["change_1w_pct"]    = d.get("change_1w")
        base["change_1m_pct"]    = d.get("change_1m")
        base["relative_strength"]= d.get("relative_strength")
        base["enhanced_fund_score"] = d.get("enhanced_fund_score")
        base["data_source"]      = src
        rows.append(base)

    tech = pd.DataFrame(rows)
    TECHNICAL_BY_STOCK_CSV.parent.mkdir(exist_ok=True, parents=True)
    tech.to_csv(TECHNICAL_BY_STOCK_CSV, index=False)

    # ── Summary markdown ────────────────────────────────────────────────────
    n_comp = (tech["data_source"] == "comprehensive_csv").sum()
    n_db   = (tech["data_source"] == "db").sum()
    n_raw  = (tech["data_source"] == "computed").sum()
    n_none = (tech["data_source"] == "none").sum()
    rec_counts = tech["recommendation"].value_counts().to_dict()

    summary_lines = [
        "# Technical summary",
        "",
        f"**{len(tech)}** holdings analysed.  "
        f"Comprehensive CSV: **{n_comp}** | DB: **{n_db}** | Computed: **{n_raw}** | No data: **{n_none}**",
        "",
        "## Recommendation breakdown",
        "",
    ]
    for rec, cnt in sorted(rec_counts.items()):
        summary_lines.append(f"- **{rec}**: {cnt} stocks")
    summary_lines.append("")
    TECHNICAL_SUMMARY_MD.write_text("\n".join(summary_lines), encoding="utf-8")

    return {
        "n_stocks": len(tech),
        "db_coverage": int(n_db),
        "csv_coverage": int(n_raw),
        "no_data": int(n_none),
        "output": str(TECHNICAL_BY_STOCK_CSV),
    }


if __name__ == "__main__":
    result = run_phase3()
    print("Phase 3 done.", result)
