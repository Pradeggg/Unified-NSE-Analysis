"""
Phase 4: Backtest
Historical simulation: at each rebalance date, apply momentum screen (RS_6M > 0),
form equal-weight portfolio; compute forward 1Y return vs Nifty 500.
Note: We use only price-based criteria (RS) for backtest since historical
fundamental scores are not available in the dataset.
"""
import sys
from pathlib import Path

import pandas as pd
import numpy as np

WORKING_SECTOR = Path(__file__).resolve().parent
if str(WORKING_SECTOR) not in sys.path:
    sys.path.insert(0, str(WORKING_SECTOR))

from config import (
    UNIVERSE_CSV,
    STOCK_CSV,
    INDEX_CSV,
    NIFTY_500_INDEX,
    LOOKBACK_6M,
    BACKTEST_START_YEAR,
    FORWARD_RETURN_DAYS,
    REBALANCE_FREQ_DAYS,
    PHASE4_BACKTEST_CSV,
    OUTPUT_DIR,
)


def load_universe() -> list[str]:
    df = pd.read_csv(UNIVERSE_CSV)
    return df["SYMBOL"].str.strip().tolist()


def load_stock_data() -> pd.DataFrame:
    df = pd.read_csv(STOCK_CSV, low_memory=False)
    df["TIMESTAMP"] = pd.to_datetime(df["TIMESTAMP"]).dt.date
    df["CLOSE"] = pd.to_numeric(df["CLOSE"], errors="coerce")
    df = df.dropna(subset=["SYMBOL", "TIMESTAMP", "CLOSE"])
    df = df[df["CLOSE"] > 0]
    df = df.sort_values(["SYMBOL", "TIMESTAMP"])
    df = df.drop_duplicates(subset=["SYMBOL", "TIMESTAMP"], keep="first")
    return df


def load_index_series(index_df: pd.DataFrame, index_name: str) -> pd.Series:
    idx = index_df[index_df["SYMBOL"].str.upper() == index_name.upper()]
    if len(idx) == 0:
        idx = index_df[index_df["SYMBOL"].str.contains("NIFTY 500", case=False, na=False)]
    idx = idx.sort_values("TIMESTAMP").drop_duplicates("TIMESTAMP", keep="first")
    return idx.set_index("TIMESTAMP")["CLOSE"].sort_index()


def run_phase4() -> pd.DataFrame:
    """Run backtest: monthly rebalance, RS_6M > 0, forward 1Y return."""
    print("Phase 4: Backtest (momentum screen: RS_6M > 0)")
    symbols = load_universe()
    stock = load_stock_data()
    stock = stock[stock["SYMBOL"].isin(symbols)]

    index_all = pd.read_csv(INDEX_CSV, low_memory=False)
    index_all["TIMESTAMP"] = pd.to_datetime(index_all["TIMESTAMP"]).dt.date
    index_all["CLOSE"] = pd.to_numeric(index_all["CLOSE"], errors="coerce")
    index_all = index_all.dropna(subset=["SYMBOL", "TIMESTAMP", "CLOSE"])
    n500 = load_index_series(index_all, NIFTY_500_INDEX)
    if n500.empty:
        print("  Warning: NIFTY 500 not found; benchmark returns will be NaN")

    dates = sorted(stock["TIMESTAMP"].unique())
    dates = [d for d in dates if d >= pd.Timestamp(f"{BACKTEST_START_YEAR}-01-01").date()]
    if not dates:
        print("  No dates after BACKTEST_START_YEAR; skip backtest.")
        return pd.DataFrame()

    # Rebalance dates: every REBALANCE_FREQ_DAYS
    rebal_dates = []
    for i, d in enumerate(dates):
        if i % REBALANCE_FREQ_DAYS == 0 and i + LOOKBACK_6M < len(dates) and i + FORWARD_RETURN_DAYS < len(dates):
            rebal_dates.append(d)

    results = []
    for rebal_date in rebal_dates:
        idx = dates.index(rebal_date)
        hist_end = dates[min(idx + 1, len(dates) - 1)]
        # Stock returns 6M up to rebal_date
        start_6m = dates[max(0, idx - LOOKBACK_6M)]
        forward_start = dates[min(idx + 1, len(dates) - 1)]
        forward_end_idx = min(len(dates) - 1, idx + FORWARD_RETURN_DAYS)
        if forward_end_idx <= idx + 1:
            continue
        forward_end = dates[forward_end_idx]

        # RS at rebal_date: need close at rebal_date and 6M before
        portfolio_ret = np.nan
        bench_ret = np.nan
        n_stocks = 0

        pass_symbols = []
        for sym in symbols:
            sh = stock[(stock["SYMBOL"] == sym) & (stock["TIMESTAMP"] <= rebal_date)].sort_values("TIMESTAMP")
            if len(sh) < LOOKBACK_6M + 1:
                continue
            close = sh.set_index("TIMESTAMP")["CLOSE"]
            ret_6m = (close.iloc[-1] / close.iloc[-1 - LOOKBACK_6M]) - 1
            if ret_6m > 0:
                pass_symbols.append(sym)

        if not pass_symbols:
            results.append({
                "REBAL_DATE": rebal_date,
                "N_STOCKS": 0,
                "PORTFOLIO_RET_1Y": np.nan,
                "BENCH_RET_1Y": np.nan,
                "EXCESS_RET": np.nan,
            })
            continue

        # Forward 1Y: equal-weight portfolio return
        fwd_stock = stock[(stock["TIMESTAMP"] >= forward_start) & (stock["TIMESTAMP"] <= forward_end)]
        fwd_stock = fwd_stock[fwd_stock["SYMBOL"].isin(pass_symbols)]
        if fwd_stock.empty:
            results.append({
                "REBAL_DATE": rebal_date,
                "N_STOCKS": len(pass_symbols),
                "PORTFOLIO_RET_1Y": np.nan,
                "BENCH_RET_1Y": np.nan,
                "EXCESS_RET": np.nan,
            })
            continue

        # Simple: get first and last close for each symbol in window, then equal-weight return
        first = fwd_stock.groupby("SYMBOL")["CLOSE"].first()
        last = fwd_stock.groupby("SYMBOL")["CLOSE"].last()
        common = first.index.intersection(last.index)
        if len(common) == 0:
            results.append({
                "REBAL_DATE": rebal_date,
                "N_STOCKS": len(pass_symbols),
                "PORTFOLIO_RET_1Y": np.nan,
                "BENCH_RET_1Y": np.nan,
                "EXCESS_RET": np.nan,
            })
            continue
        rets = (last / first - 1).reindex(common).dropna()
        portfolio_ret = rets.mean()

        if not n500.empty and forward_start in n500.index and forward_end in n500.index:
            bench_ret = (n500.loc[forward_end] / n500.loc[forward_start]) - 1
        else:
            bench_ret = np.nan

        results.append({
            "REBAL_DATE": rebal_date,
            "N_STOCKS": len(pass_symbols),
            "PORTFOLIO_RET_1Y": portfolio_ret,
            "BENCH_RET_1Y": bench_ret,
            "EXCESS_RET": portfolio_ret - bench_ret if not np.isnan(bench_ret) else np.nan,
        })

    out = pd.DataFrame(results)
    out.to_csv(PHASE4_BACKTEST_CSV, index=False)
    print(f"  Rebalance dates: {len(out)}")
    if not out.empty and out["EXCESS_RET"].notna().any():
        print(f"  Mean excess return (1Y): {out['EXCESS_RET'].mean()*100:.2f}%")
        print(f"  Hit rate (excess > 0): {(out['EXCESS_RET'] > 0).sum() / max(1, (out['EXCESS_RET'].notna()).sum())*100:.0f}%")
    print(f"  Wrote {PHASE4_BACKTEST_CSV}")
    return out


if __name__ == "__main__":
    run_phase4()
