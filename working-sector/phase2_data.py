"""
Phase 2: Universe and Data
Load universe, NSE stock and index data; compute returns, relative strength,
technical score; merge fundamentals. Output: one row per stock with all metrics.
"""
import sys
from pathlib import Path

import pandas as pd
import numpy as np

# Add project root for imports if needed
WORKING_SECTOR = Path(__file__).resolve().parent
if str(WORKING_SECTOR) not in sys.path:
    sys.path.insert(0, str(WORKING_SECTOR))

from config import (
    UNIVERSE_CSV,
    STOCK_CSV,
    INDEX_CSV,
    FUNDAMENTAL_CSV,
    NIFTY_AUTO_INDEX,
    NIFTY_500_INDEX,
    LOOKBACK_1M,
    LOOKBACK_3M,
    LOOKBACK_6M,
    PHASE2_TABLE_CSV,
    OUTPUT_DIR,
)


def load_universe() -> pd.DataFrame:
    """Load auto components universe (component-only)."""
    df = pd.read_csv(UNIVERSE_CSV)
    df["SYMBOL"] = df["SYMBOL"].str.strip()
    return df


def load_stock_data() -> pd.DataFrame:
    """Load NSE stock data and clean."""
    df = pd.read_csv(STOCK_CSV, low_memory=False)
    required = ["SYMBOL", "TIMESTAMP", "OPEN", "HIGH", "LOW", "CLOSE", "TOTTRDQTY", "TOTTRDVAL"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing columns: {missing}")
    df["TIMESTAMP"] = pd.to_datetime(df["TIMESTAMP"]).dt.date
    for col in ["CLOSE", "OPEN", "HIGH", "LOW", "TOTTRDQTY", "TOTTRDVAL"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["SYMBOL", "TIMESTAMP", "CLOSE"])
    df = df[df["CLOSE"] > 0]
    df = df.sort_values(["SYMBOL", "TIMESTAMP"])
    df = df.drop_duplicates(subset=["SYMBOL", "TIMESTAMP"], keep="first")
    return df


def load_index_data() -> pd.DataFrame:
    """Load NSE index data."""
    df = pd.read_csv(INDEX_CSV, low_memory=False)
    df["TIMESTAMP"] = pd.to_datetime(df["TIMESTAMP"]).dt.date
    df["CLOSE"] = pd.to_numeric(df["CLOSE"], errors="coerce")
    df = df.dropna(subset=["SYMBOL", "TIMESTAMP", "CLOSE"])
    df = df[df["CLOSE"] > 0]
    return df


def get_index_series(index_df: pd.DataFrame, index_name: str) -> pd.DataFrame:
    """Get time series for one index; normalize name (Nifty Auto / NIFTY 500)."""
    idx = index_df.copy()
    idx["SYMBOL"] = idx["SYMBOL"].str.strip()
    # Try exact then case-insensitive
    sub = idx[idx["SYMBOL"] == index_name]
    if len(sub) == 0:
        sub = idx[idx["SYMBOL"].str.upper() == index_name.upper()]
    if len(sub) == 0 and "NIFTY" in index_name.upper():
        sub = idx[idx["SYMBOL"].str.contains("NIFTY 500", case=False, na=False)]
    sub = sub.sort_values("TIMESTAMP").drop_duplicates(subset=["TIMESTAMP"], keep="first")
    return sub


def compute_returns(series: pd.Series, lookback: int) -> float:
    """Return (current / price lookback ago) - 1; NaN if insufficient data."""
    if len(series) < lookback + 1:
        return np.nan
    return (series.iloc[-1] / series.iloc[-1 - lookback]) - 1


def compute_rsi(prices: pd.Series, period: int = 14) -> float:
    """RSI; returns NaN if insufficient data."""
    if len(prices) < period + 1:
        return np.nan
    delta = prices.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.rolling(period).mean().iloc[-1]
    avg_loss = loss.rolling(period).mean().iloc[-1]
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def technical_score_from_series(prices: pd.Series, rsi: float) -> float:
    """Simple technical score 0-100: trend (SMA) + RSI zone."""
    if len(prices) < 50:
        return np.nan
    score = 50.0
    current = prices.iloc[-1]
    for period in [20, 50]:
        if len(prices) >= period:
            sma = prices.rolling(period).mean().iloc[-1]
            if current > sma:
                score += 10
            else:
                score -= 10
    if not np.isnan(rsi):
        if 40 <= rsi <= 70:
            score += 10
        elif rsi < 30 or rsi > 80:
            score -= 10
    return max(0, min(100, score))


def load_fundamentals() -> pd.DataFrame | None:
    """Load fundamental scores; symbol column may be lower/upper."""
    if not FUNDAMENTAL_CSV.exists():
        return None
    df = pd.read_csv(FUNDAMENTAL_CSV)
    if "symbol" in df.columns:
        df["SYMBOL"] = df["symbol"].str.upper().str.strip()
    # Keep latest per symbol if multiple rows
    if "processed_date" in df.columns:
        df["processed_date"] = pd.to_datetime(df["processed_date"], errors="coerce")
        df = df.sort_values("processed_date").drop_duplicates(subset=["SYMBOL"], keep="last")
    return df


def run_phase2() -> pd.DataFrame:
    """Run Phase 2: build merged table of universe stocks with all metrics."""
    print("Phase 2: Universe and Data")
    print("  Loading universe...")
    universe = load_universe()
    symbols = universe["SYMBOL"].tolist()

    print("  Loading stock data...")
    stock_all = load_stock_data()
    stock = stock_all[stock_all["SYMBOL"].isin(symbols)].copy()
    if stock.empty:
        raise ValueError("No stock data found for universe symbols")

    print("  Loading index data...")
    index_all = load_index_data()
    nifty_auto = get_index_series(index_all, NIFTY_AUTO_INDEX)
    nifty_500 = get_index_series(index_all, NIFTY_500_INDEX)
    if nifty_auto.empty:
        print("  Warning: Nifty Auto series empty; RS vs Auto will be NaN")
    if nifty_500.empty:
        print("  Warning: NIFTY 500 series empty; RS vs 500 will be NaN")

    latest_date = stock["TIMESTAMP"].max()
    print(f"  Latest date in stock data: {latest_date}")

    print("  Loading fundamentals...")
    fund = load_fundamentals()

    # Align index to same dates as stock for merge
    def index_close_on_dates(idx_df: pd.DataFrame, dates: pd.Series) -> pd.Series:
        idx_df = idx_df.set_index("TIMESTAMP")["CLOSE"]
        return dates.map(lambda d: idx_df.index[idx_df.index <= d][-1] if len(idx_df.index[idx_df.index <= d]) else np.nan)

    rows = []
    for sym in symbols:
        sh = stock[stock["SYMBOL"] == sym].sort_values("TIMESTAMP")
        if len(sh) < LOOKBACK_6M + 1:
            continue
        close = sh.set_index("TIMESTAMP")["CLOSE"].sort_index()
        current_price = close.iloc[-1]

        # Returns
        ret_1m = compute_returns(close, LOOKBACK_1M)
        ret_3m = compute_returns(close, LOOKBACK_3M)
        ret_6m = compute_returns(close, LOOKBACK_6M)

        # RS vs Nifty Auto (6M)
        rs_auto_6m = np.nan
        if not nifty_auto.empty and len(nifty_auto) >= LOOKBACK_6M + 1:
            idx_close = nifty_auto.set_index("TIMESTAMP")["CLOSE"].sort_index()
            idx_ret_6m = (idx_close.iloc[-1] / idx_close.iloc[-1 - LOOKBACK_6M]) - 1
            rs_auto_6m = ret_6m - idx_ret_6m if not np.isnan(ret_6m) else np.nan

        # RS vs Nifty 500 (6M) — primary for screen
        rs_500_6m = np.nan
        if not nifty_500.empty and len(nifty_500) >= LOOKBACK_6M + 1:
            idx_close = nifty_500.set_index("TIMESTAMP")["CLOSE"].sort_index()
            idx_ret_6m = (idx_close.iloc[-1] / idx_close.iloc[-1 - LOOKBACK_6M]) - 1
            rs_500_6m = ret_6m - idx_ret_6m if not np.isnan(ret_6m) else np.nan

        rsi = compute_rsi(close, 14)
        tech_score = technical_score_from_series(close, rsi)

        # Fundamentals
        fund_score = np.nan
        if fund is not None and not fund.empty:
            f = fund[fund["SYMBOL"] == sym]
            if not f.empty and "ENHANCED_FUND_SCORE" in f.columns:
                fund_score = pd.to_numeric(f["ENHANCED_FUND_SCORE"].iloc[0], errors="coerce")

        subseg = universe[universe["SYMBOL"] == sym]["SUBSECTOR"]
        subseg = subseg.iloc[0] if len(subseg) > 0 else ""

        rows.append({
            "SYMBOL": sym,
            "SUBSECTOR": subseg,
            "CURRENT_PRICE": current_price,
            "RET_1M": ret_1m,
            "RET_3M": ret_3m,
            "RET_6M": ret_6m,
            "RS_VS_NIFTY_AUTO_6M": rs_auto_6m,
            "RS_VS_NIFTY_500_6M": rs_500_6m,
            "RSI": rsi,
            "TECHNICAL_SCORE": tech_score,
            "FUND_SCORE": fund_score,
            "AS_OF_DATE": latest_date,
        })

    out = pd.DataFrame(rows)
    out.to_csv(PHASE2_TABLE_CSV, index=False)
    print(f"  Wrote {PHASE2_TABLE_CSV} ({len(out)} rows)")
    return out


if __name__ == "__main__":
    run_phase2()
