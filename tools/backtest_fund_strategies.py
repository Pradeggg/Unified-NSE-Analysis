#!/usr/bin/env python3
"""
backtest_fund_strategies.py — Agent Adda Fund Strategy Backtest
=================================================================
Data source : scores.stage_snapshots (Jun 2023 → Aug 2026, daily)
Rebalancing : Monthly (last trading snapshot of each calendar month)
SC universe : market_cap_cat IN ('SMALL_CAP')
MC universe : market_cap_cat IN ('MID_CAP')
Portfolio   : Equal-weight, top-N by technical_score within each strategy filter
Benchmark   : ^NSEI (Nifty 50) for SC,  ^NSEMDCP50 for MC

5 Strategies (applied identically to SC and MC):
  S1  Baseline          – Stage 2 only
  S2  RS / Stage        – Stage 2 + RS > 15
  S3  Darvas Only       – BUY or STRONG_BUY signal
  S4  Darvas + ST       – S3 + trend STRONG_BULLISH
  S5  Darvas+ST+HighRS  – S4 + RS > 30

Usage:
  python tools/backtest_fund_strategies.py
  python tools/backtest_fund_strategies.py --json
  python tools/backtest_fund_strategies.py --top-sc 9 --top-mc 15
"""

import argparse
import json
import sys
import warnings
from datetime import date

import numpy as np
import pandas as pd
import psycopg2

warnings.filterwarnings("ignore")

# ── CONFIG ──────────────────────────────────────────────────────────────────
SC_TOP_N   = 9
MC_TOP_N   = 15
SC_CAPS    = ('SMALL_CAP',)
MC_CAPS    = ('MID_CAP',)
MIN_STOCKS = 3          # skip month if fewer than MIN_STOCKS pass filter
RISK_FREE  = 0.065      # ~6.5% India 10Y yield for Sharpe calculation

# Strategy filters — cross-year compatible notes:
#  - STRONG_BUY / STRONG_BULLISH only exist in 2026 data; older data uses BUY / BULLISH
#  - RS is percentile-scaled 0-100 in 2023-25, outperformance % in 2026
#  - S5 uses a per-month dynamic RS threshold (top-30% within each snapshot)
#    to remain consistent across both RS scaling eras

def _buy(r):   return r["signal"] in ("BUY", "STRONG_BUY")
def _bull(r):  return r["trend"] in ("BULLISH", "STRONG_BULLISH")

STRATEGY_DEFS = {
    "S1_Baseline":         lambda r: r["stage"] == "STAGE_2",
    "S2_RS_Stage":         lambda r: r["stage"] == "STAGE_2" and r["rs"] > r.get("_rs_p70", 0),
    "S3_Darvas":           lambda r: _buy(r),
    "S4_Darvas_ST":        lambda r: _buy(r) and _bull(r),
    "S5_Darvas_ST_HighRS": lambda r: _buy(r) and _bull(r) and r["rs"] > r.get("_rs_p70", 0),
}

STRATEGY_LABELS = {
    "S1_Baseline":         "1 · Baseline (Stage 2)",
    "S2_RS_Stage":         "2 · RS / Stage (Stage 2 + RS >15)",
    "S3_Darvas":           "3 · Darvas Only (BUY signal)",
    "S4_Darvas_ST":        "4 · Darvas + Supertrend",
    "S5_Darvas_ST_HighRS": "5 · Darvas + ST + High RS (>30)",
}


# ── DATA LOAD ────────────────────────────────────────────────────────────────

def load_universe_symbols(conn, caps: tuple) -> set:
    """
    market_cap_cat is only populated in 2026 data.
    Get the distinct symbols classified under each cap tier in 2026
    and use them as a static universe for the full backtest period.
    """
    cap_list = "','".join(caps)
    df = pd.read_sql_query(f"""
        SELECT DISTINCT symbol
        FROM scores.stage_snapshots
        WHERE market_cap_cat IN ('{cap_list}')
          AND snapshot_date >= '2026-01-01'
    """, conn)
    symbols = set(df["symbol"].tolist())
    print(f"  Universe ({caps}): {len(symbols)} symbols from 2026 cap data", file=sys.stderr)
    return symbols


def load_snapshots(conn, universe_sc: set, universe_mc: set) -> pd.DataFrame:
    """
    Load all historical snapshots for the SC+MC universe symbols.
    Signals are available for all years; cap_group is assigned from our universe dict.
    """
    all_symbols = universe_sc | universe_mc
    sym_list = "','".join(sorted(all_symbols))
    print(f"Loading {len(all_symbols)} universe symbols from stage_snapshots...", file=sys.stderr)
    df = pd.read_sql_query(f"""
        SELECT
            snapshot_date,
            symbol,
            CAST(price AS float)              AS price,
            stage,
            trading_signal                    AS signal,
            trend_signal                      AS trend,
            supertrend_state,
            COALESCE(CAST(relative_strength AS float), 0) AS rs,
            COALESCE(CAST(rsi AS float), 50)              AS rsi,
            COALESCE(CAST(technical_score AS float), 0)   AS tech_score
        FROM scores.stage_snapshots
        WHERE symbol IN ('{sym_list}')
          AND price IS NOT NULL
          AND price > 0
          AND stage IS NOT NULL
        ORDER BY snapshot_date, symbol
    """, conn, parse_dates=["snapshot_date"])

    # Tag each row with its fund group
    df["cap_group"] = df["symbol"].apply(
        lambda s: "SC" if s in universe_sc else ("MC" if s in universe_mc else None)
    )
    print(f"  Loaded {len(df):,} rows, {df['snapshot_date'].nunique()} dates", file=sys.stderr)
    return df


def build_monthly_snapshots(df: pd.DataFrame) -> dict:
    """Return {year_month_str: DataFrame} using last trading day of each month.
    Adds _rs_p70 column: 70th-percentile RS for that snapshot, for a cross-era
    consistent 'High RS' filter (works with both percentile-based and % RS scales).
    """
    df = df.copy()
    df["ym"] = df["snapshot_date"].dt.to_period("M")
    monthly = {}
    for ym, grp in df.groupby("ym"):
        last_date = grp["snapshot_date"].max()
        snap = grp[grp["snapshot_date"] == last_date].copy()
        snap = snap.sort_values("tech_score", ascending=False).drop_duplicates("symbol")
        # Dynamic RS threshold: 70th percentile across the whole snap (not just cap-filtered)
        snap["_rs_p70"] = snap["rs"].quantile(0.70)
        monthly[str(ym)] = snap
    months_sorted = sorted(monthly.keys())
    print(f"  Monthly snapshots: {months_sorted[0]} → {months_sorted[-1]} "
          f"({len(months_sorted)} months)", file=sys.stderr)
    return monthly, months_sorted


# ── STRATEGY ENGINE ──────────────────────────────────────────────────────────

def select_portfolio(snap: pd.DataFrame, cap_group: str, strat_fn, top_n: int) -> pd.DataFrame:
    """Filter by cap_group tag, apply strategy, return top-N by tech_score."""
    pool = snap[snap["cap_group"] == cap_group].copy()
    if pool.empty:
        return pool
    pool["_pass"] = pool.apply(lambda r: strat_fn(r), axis=1)
    passing = pool[pool["_pass"]].sort_values("tech_score", ascending=False).head(top_n)
    cols = [c for c in ["symbol", "price", "tech_score", "rs", "stage", "signal", "trend"] if c in passing.columns]
    return passing[cols]


def compute_portfolio_return(holdings: pd.DataFrame, next_snap: pd.DataFrame) -> dict:
    """
    Equal-weight return from current holdings to next month's prices.
    Stocks missing from next_snap are dropped (reduces to actual coverage).
    """
    merged = holdings.merge(
        next_snap[["symbol", "price"]].rename(columns={"price": "price_next"}),
        on="symbol", how="inner"
    )
    if len(merged) == 0:
        return {"ret": 0.0, "n_held": 0, "n_found": 0, "stocks": []}
    merged["stock_ret"] = merged["price_next"] / merged["price"] - 1
    port_ret = merged["stock_ret"].mean()
    return {
        "ret": port_ret,
        "n_held": len(holdings),
        "n_found": len(merged),
        "stocks": merged[["symbol", "price", "price_next", "stock_ret"]].to_dict("records"),
    }


# ── METRICS ─────────────────────────────────────────────────────────────────

def compute_metrics(monthly_rets: list[float], label: str) -> dict:
    rets = np.array(monthly_rets)
    n = len(rets)
    if n == 0:
        return {}

    cum = np.cumprod(1 + rets)
    total_ret = cum[-1] - 1
    years = n / 12
    cagr = (cum[-1] ** (1 / years) - 1) if years > 0 else 0

    # Drawdown
    running_max = np.maximum.accumulate(cum)
    drawdowns = (cum - running_max) / running_max
    max_dd = drawdowns.min()

    # Sharpe (monthly)
    rf_monthly = (1 + RISK_FREE) ** (1 / 12) - 1
    excess = rets - rf_monthly
    sharpe = (excess.mean() / excess.std() * np.sqrt(12)) if excess.std() > 0 else 0

    # Win rate
    win_rate = (rets > 0).mean()

    # Best / worst month
    best_month = rets.max()
    worst_month = rets.min()

    return {
        "label": label,
        "n_months": n,
        "total_ret_pct": round(total_ret * 100, 2),
        "cagr_pct": round(cagr * 100, 2),
        "max_drawdown_pct": round(max_dd * 100, 2),
        "sharpe": round(sharpe, 2),
        "win_rate_pct": round(win_rate * 100, 1),
        "best_month_pct": round(best_month * 100, 2),
        "worst_month_pct": round(worst_month * 100, 2),
        "monthly_rets": [round(r * 100, 4) for r in rets.tolist()],
        "cumulative": [round(v, 6) for v in cum.tolist()],
    }


# ── BENCHMARK ────────────────────────────────────────────────────────────────

def fetch_benchmark(ticker: str, months_sorted: list[str]) -> dict:
    try:
        import yfinance as yf
        start = months_sorted[0][:7] + "-01"
        end = months_sorted[-1][:7] + "-28"
        tk = yf.Ticker(ticker)
        hist = tk.history(start=start, end=end, interval="1mo", auto_adjust=True)
        if hist.empty:
            return {}
        rets = hist["Close"].pct_change().dropna().tolist()
        # Trim to same length as strategy months
        n = len(months_sorted) - 1   # one fewer because first month is entry
        rets = rets[:n]
        return compute_metrics(rets, f"Benchmark ({ticker})")
    except Exception as e:
        print(f"  Benchmark fetch failed: {e}", file=sys.stderr)
        return {}


# ── MAIN BACKTEST LOOP ───────────────────────────────────────────────────────

def run_backtest(df: pd.DataFrame, cap_group: str, top_n: int, fund_name: str) -> dict:
    monthly, months_sorted = build_monthly_snapshots(df)

    results = {}
    for strat_key, strat_fn in STRATEGY_DEFS.items():
        monthly_rets = []
        detail = []
        skipped = 0

        for i, ym in enumerate(months_sorted[:-1]):
            snap_now  = monthly[ym]
            snap_next = monthly[months_sorted[i + 1]]

            holdings = select_portfolio(snap_now, cap_group, strat_fn, top_n)

            if len(holdings) < MIN_STOCKS:
                skipped += 1
                continue

            pr = compute_portfolio_return(holdings, snap_next)
            if pr["n_found"] < MIN_STOCKS:
                skipped += 1
                continue

            monthly_rets.append(pr["ret"])
            detail.append({
                "month": ym,
                "n_stocks": pr["n_found"],
                "ret_pct": round(pr["ret"] * 100, 4),
                "top3": [s["symbol"] for s in sorted(pr["stocks"], key=lambda x: -x["stock_ret"])[:3]],
            })

        metrics = compute_metrics(monthly_rets, STRATEGY_LABELS[strat_key])
        metrics["skipped_months"] = skipped
        metrics["monthly_detail"] = detail
        results[strat_key] = metrics
        print(f"  [{fund_name}] {strat_key}: {metrics.get('total_ret_pct','?')}% total, "
              f"CAGR {metrics.get('cagr_pct','?')}%, Sharpe {metrics.get('sharpe','?')}, "
              f"MaxDD {metrics.get('max_drawdown_pct','?')}%", file=sys.stderr)

    return results


# ── ENTRY POINT ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Agent Adda Fund Strategy Backtest")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--top-sc", type=int, default=SC_TOP_N)
    parser.add_argument("--top-mc", type=int, default=MC_TOP_N)
    parser.add_argument("--out", default=None, help="Output JSON file path")
    args = parser.parse_args()

    conn = psycopg2.connect(dbname="nse_market", user="pgorai", host="localhost")
    universe_sc = load_universe_symbols(conn, SC_CAPS)
    universe_mc = load_universe_symbols(conn, MC_CAPS)
    df = load_snapshots(conn, universe_sc, universe_mc)
    conn.close()

    _, months_sorted = build_monthly_snapshots(df)

    print("\nRunning SmallCap backtest...", file=sys.stderr)
    sc_results = run_backtest(df, "SC", args.top_sc, "SC")

    print("\nRunning MidCap backtest...", file=sys.stderr)
    mc_results = run_backtest(df, "MC", args.top_mc, "MC")

    # Benchmarks
    print("\nFetching benchmarks...", file=sys.stderr)
    nifty50    = fetch_benchmark("^NSEI",      months_sorted)
    nifty_mid  = fetch_benchmark("^CNXMDCP50", months_sorted)

    output = {
        "meta": {
            "period_start": months_sorted[0],
            "period_end": months_sorted[-1],
            "n_months": len(months_sorted) - 1,
            "sc_top_n": args.top_sc,
            "mc_top_n": args.top_mc,
            "sc_universe": list(SC_CAPS),
            "mc_universe": list(MC_CAPS),
            "risk_free_annual": RISK_FREE,
            "run_date": str(date.today()),
        },
        "smallcap": sc_results,
        "midcap":   mc_results,
        "benchmarks": {
            "nifty50": nifty50,
            "nifty_midcap50": nifty_mid,
        },
    }

    if args.out:
        import pathlib
        pathlib.Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        with open(args.out, "w") as f:
            json.dump(output, f, indent=2)
        print(f"\nResults saved to {args.out}", file=sys.stderr)

    if args.json or args.out is None:
        print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
