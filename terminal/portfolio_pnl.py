"""Portfolio P&L dashboard — loads holdings.csv and computes live unrealised P&L."""
from __future__ import annotations
import os, sys
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOLDINGS_FILE = os.path.join(ROOT, "data", "holdings.csv")
SAMPLE_HOLDINGS = """symbol,qty,avg_cost,buy_date
RELIANCE,10,1400.00,2024-01-15
TCS,5,3800.00,2024-02-10
INFY,20,1600.00,2024-03-01
HDFCBANK,15,1550.00,2024-04-05
WIPRO,30,480.00,2024-05-12
"""


def load_holdings() -> pd.DataFrame:
    """Load holdings from data/holdings.csv. Creates sample file if missing."""
    if not os.path.exists(HOLDINGS_FILE):
        os.makedirs(os.path.dirname(HOLDINGS_FILE), exist_ok=True)
        with open(HOLDINGS_FILE, "w") as f:
            f.write(SAMPLE_HOLDINGS)
    df = pd.read_csv(HOLDINGS_FILE)
    required = {"symbol", "qty", "avg_cost"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"holdings.csv missing columns: {missing}")
    df["symbol"] = df["symbol"].str.upper().str.strip()
    df["qty"] = pd.to_numeric(df["qty"], errors="coerce").fillna(0).astype(int)
    df["avg_cost"] = pd.to_numeric(df["avg_cost"], errors="coerce").fillna(0.0)
    return df[df["qty"] > 0].copy()


def compute_pnl() -> dict:
    """Fetch live prices and compute unrealised P&L for all holdings."""
    sys.path.insert(0, ROOT)
    from terminal.tools import call_tool

    df = load_holdings()
    rows = []

    for _, holding in df.iterrows():
        sym = holding["symbol"]
        qty = int(holding["qty"])
        avg_cost = float(holding["avg_cost"])

        # Fetch live snapshot
        snap = call_tool("get_symbol_snapshot", {"symbol": sym})
        if "error" in snap or not snap.get("price"):
            ltp = avg_cost  # fallback: no change
            day_chg_pct = 0.0
        else:
            ltp = float(snap.get("price", avg_cost))
            day_chg_pct = float(snap.get("pct_change", 0) or 0)

        invested = avg_cost * qty
        current = ltp * qty
        pnl = current - invested
        pnl_pct = (pnl / invested * 100) if invested else 0
        day_pnl = current * (day_chg_pct / 100)

        rows.append({
            "symbol":    sym,
            "qty":       qty,
            "avg_cost":  round(avg_cost, 2),
            "ltp":       round(ltp, 2),
            "invested":  round(invested, 2),
            "current":   round(current, 2),
            "pnl":       round(pnl, 2),
            "pnl_pct":   round(pnl_pct, 2),
            "day_chg_pct": round(day_chg_pct, 2),
            "day_pnl":   round(day_pnl, 2),
        })

    result_df = pd.DataFrame(rows).sort_values("pnl", ascending=False)

    total_invested = result_df["invested"].sum()
    total_current  = result_df["current"].sum()
    total_pnl      = result_df["pnl"].sum()
    total_pnl_pct  = (total_pnl / total_invested * 100) if total_invested else 0
    total_day_pnl  = result_df["day_pnl"].sum()

    return {
        "rows": result_df.to_dict("records"),
        "total_invested":  round(total_invested, 2),
        "total_current":   round(total_current, 2),
        "total_pnl":       round(total_pnl, 2),
        "total_pnl_pct":   round(total_pnl_pct, 2),
        "total_day_pnl":   round(total_day_pnl, 2),
    }
