#!/usr/bin/env python3
"""
Phase 3: Technical analysis per holding.
Produces technical_by_stock.csv with real scores from nse_analysis.db;
falls back to computing RSI/SMA from nse_universe_stock_data.csv for stocks
not in the DB.
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

# Path to the shared NSE analysis DB (sibling data/ directory)
_HERE = Path(__file__).resolve().parent
NSE_DB = _HERE.parent / "data" / "nse_analysis.db"
NSE_UNIVERSE_CSV = _HERE.parent / "data" / "nse_universe_stock_data.csv"

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

    # ── Pull latest row per symbol from nse_analysis.db ────────────────────
    db_data: dict = {}
    if NSE_DB.exists():
        try:
            con = sqlite3.connect(NSE_DB)
            df_db = pd.read_sql(
                """
                SELECT symbol, analysis_date, current_price, technical_score, rsi,
                       trend_signal, trading_signal, change_1d, change_1w, change_1m,
                       relative_strength
                FROM stocks_analysis
                WHERE (symbol, analysis_date) IN (
                    SELECT symbol, MAX(analysis_date) FROM stocks_analysis GROUP BY symbol
                )
                """,
                con,
            )
            con.close()
            df_db["symbol"] = df_db["symbol"].str.upper()
            for _, row in df_db.iterrows():
                db_data[row["symbol"]] = row.to_dict()
        except Exception as e:
            print(f"[phase3] DB read warning: {e}")

    # ── Fall back: compute from price CSV for missing symbols ───────────────
    csv_data: dict = {}
    missing = [s for s in symbols if s not in db_data]
    if missing and NSE_UNIVERSE_CSV.exists():
        try:
            price_df = pd.read_csv(NSE_UNIVERSE_CSV, parse_dates=["TIMESTAMP"])
            price_df["SYMBOL"] = price_df["SYMBOL"].str.upper()
            for sym in missing:
                sub = price_df[price_df["SYMBOL"] == sym].sort_values("TIMESTAMP")
                if len(sub) >= 20:
                    result = _tech_score_from_rsi_sma(sub["CLOSE"])
                    if result:
                        csv_data[sym] = result
        except Exception as e:
            print(f"[phase3] CSV fallback warning: {e}")

    # ── Build output DataFrame ─────────────────────────────────────────────
    rows = []
    for _, h in holdings.iterrows():
        sym = str(h["symbol"]).upper()
        base = {
            "symbol": h["symbol"],
            "quantity": h["quantity"],
            "value_rs": h["value_rs"],
        }
        d = db_data.get(sym) or csv_data.get(sym) or {}
        base["current_price"] = d.get("current_price")
        base["technical_score"] = d.get("technical_score", 50)
        base["rsi"] = d.get("rsi")
        base["trend_signal"] = d.get("trend_signal", "UNKNOWN")
        trading = d.get("trading_signal", "HOLD") or "HOLD"
        base["trading_signal"] = trading
        base["recommendation"] = _SIGNAL_MAP.get(trading, trading)
        base["change_1d_pct"] = d.get("change_1d")
        base["change_1w_pct"] = d.get("change_1w")
        base["change_1m_pct"] = d.get("change_1m")
        base["relative_strength"] = d.get("relative_strength")
        base["data_source"] = "db" if sym in db_data else ("csv_computed" if sym in csv_data else "none")
        rows.append(base)

    tech = pd.DataFrame(rows)
    TECHNICAL_BY_STOCK_CSV.parent.mkdir(exist_ok=True, parents=True)
    tech.to_csv(TECHNICAL_BY_STOCK_CSV, index=False)

    # ── Summary markdown ────────────────────────────────────────────────────
    n_db = (tech["data_source"] == "db").sum()
    n_csv = (tech["data_source"] == "csv_computed").sum()
    n_none = (tech["data_source"] == "none").sum()
    rec_counts = tech["recommendation"].value_counts().to_dict()

    summary_lines = [
        "# Technical summary",
        "",
        f"**{len(tech)}** holdings analysed.  "
        f"DB coverage: **{n_db}** | Computed from price CSV: **{n_csv}** | No data: **{n_none}**",
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
        "csv_coverage": int(n_csv),
        "no_data": int(n_none),
        "output": str(TECHNICAL_BY_STOCK_CSV),
    }


if __name__ == "__main__":
    result = run_phase3()
    print("Phase 3 done.", result)
