#!/usr/bin/env python3
"""Resolve historical signals in data/signal_log.csv against current prices.

Usage:
  python resolve_signals.py            # resolve 5-day, 22-day, 66-day signals
  python resolve_signals.py --days 5   # resolve only 5-day signals
  python resolve_signals.py --summary  # print performance summary
"""

from __future__ import annotations

import argparse
import math
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
SIGNAL_LOG = ROOT / "data" / "signal_log.csv"
STOCK_DATA = ROOT / "data" / "nse_sec_full_data.csv"


def _load_current_prices(symbols: list[str]) -> dict[str, float]:
    """Load the most recent closing price for each symbol from the stock data CSV."""
    if not STOCK_DATA.exists():
        return {}
    try:
        df = pd.read_csv(STOCK_DATA, usecols=lambda c: c.upper() in {"SYMBOL", "CLOSE", "TIMESTAMP", "DATE"},
                         low_memory=False)
        df.columns = [c.upper() for c in df.columns]
        date_col = "TIMESTAMP" if "TIMESTAMP" in df.columns else "DATE"
        df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
        df = df[df["SYMBOL"].isin(symbols)].dropna(subset=[date_col, "CLOSE"])
        return df.sort_values(date_col).groupby("SYMBOL")["CLOSE"].last().to_dict()
    except Exception as exc:
        print(f"Warning: could not load prices — {exc}")
        return {}


def _load_price_on_date(symbol: str, target_date: datetime) -> float | None:
    """Get closing price for symbol on or after target_date (up to 5 trading days later)."""
    if not STOCK_DATA.exists():
        return None
    try:
        df = pd.read_csv(STOCK_DATA, low_memory=False)
        df.columns = [c.upper() for c in df.columns]
        date_col = "TIMESTAMP" if "TIMESTAMP" in df.columns else "DATE"
        df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
        sym_df = df[(df["SYMBOL"] == symbol) & (df[date_col] >= target_date)].sort_values(date_col)
        if sym_df.empty:
            return None
        return float(sym_df.iloc[0]["CLOSE"])
    except Exception:
        return None


def resolve(horizon_days: int | None = None) -> pd.DataFrame:
    """
    Resolve unresolved signals in the log whose issue date is >= horizon_days ago.
    Updates signal_log.csv in place. Returns updated DataFrame.
    """
    if not SIGNAL_LOG.exists():
        print("No signal log found. Run sector_rotation_report.py first.")
        return pd.DataFrame()

    log = pd.read_csv(SIGNAL_LOG)
    log["date_issued"] = pd.to_datetime(log["date_issued"], errors="coerce")
    unresolved = log[log["date_resolved"].isna() | (log["date_resolved"] == "")]

    horizons = [horizon_days] if horizon_days else [5, 22, 66]
    today = datetime.now()
    resolved_count = 0

    for h in horizons:
        cutoff = today - timedelta(days=h)
        due = unresolved[unresolved["date_issued"] <= cutoff]
        if due.empty:
            continue
        print(f"  Resolving {len(due)} signals at {h}d horizon...")
        symbols = due["symbol"].unique().tolist()
        prices = _load_current_prices(symbols)

        for idx, row in due.iterrows():
            sym = str(row["symbol"])
            issue_date = row["date_issued"]
            resolve_date = issue_date + timedelta(days=h)
            price_at_issue = float(row.get("price_at_issue", math.nan) or math.nan)
            target_1 = float(row.get("target_1", math.nan) or math.nan)
            stop_loss = float(row.get("stop_loss", math.nan) or math.nan)

            # Prefer historical price on resolve_date; fall back to latest available
            resolution_price = _load_price_on_date(sym, resolve_date)
            if resolution_price is None:
                resolution_price = prices.get(sym)
            if resolution_price is None or math.isnan(price_at_issue):
                continue

            ret_pct = (resolution_price / price_at_issue - 1) * 100
            hit_target = not math.isnan(target_1) and resolution_price >= target_1
            hit_stop = not math.isnan(stop_loss) and resolution_price <= stop_loss

            log.at[idx, "date_resolved"] = resolve_date.strftime("%Y-%m-%d")
            log.at[idx, "price_at_resolution"] = round(resolution_price, 2)
            log.at[idx, "return_pct"] = round(ret_pct, 2)
            log.at[idx, "hit_target"] = hit_target
            log.at[idx, "hit_stop"] = hit_stop
            resolved_count += 1

    log.to_csv(SIGNAL_LOG, index=False)
    print(f"  Resolved {resolved_count} signals. Log has {len(log)} total rows.")
    return log


def print_summary(log: pd.DataFrame | None = None) -> None:
    """Print signal performance summary by setup_class and regime."""
    if log is None:
        if not SIGNAL_LOG.exists():
            print("No signal log found.")
            return
        log = pd.read_csv(SIGNAL_LOG)

    resolved = log[log["return_pct"].notna() & (log["return_pct"] != "")]
    if resolved.empty:
        print("No resolved signals yet.")
        return

    resolved = resolved.copy()
    resolved["return_pct"] = pd.to_numeric(resolved["return_pct"], errors="coerce")
    resolved["hit_target"] = resolved["hit_target"].map(lambda x: str(x).lower() in ("true", "1", "yes"))

    print(f"\n=== Signal Performance Summary ({len(resolved)} resolved signals) ===\n")

    # By setup class
    if "setup_class" in resolved.columns:
        by_setup = resolved.groupby("setup_class").agg(
            n=("return_pct", "count"),
            avg_return=("return_pct", "mean"),
            hit_rate=("hit_target", "mean"),
            win_rate=("return_pct", lambda x: (x > 0).mean()),
        ).round(2).sort_values("avg_return", ascending=False)
        print("By Setup Class:")
        print(by_setup.to_string())

    # By regime
    if "regime_at_issue" in resolved.columns:
        by_regime = resolved.groupby("regime_at_issue").agg(
            n=("return_pct", "count"),
            avg_return=("return_pct", "mean"),
            win_rate=("return_pct", lambda x: (x > 0).mean()),
        ).round(2).sort_values("avg_return", ascending=False)
        print("\nBy Market Regime at Issue:")
        print(by_regime.to_string())

    # Top performers
    top = resolved.nlargest(5, "return_pct")[["symbol", "setup_class", "regime_at_issue", "return_pct", "hit_target"]]
    print("\nTop 5 Signals by Return:")
    print(top.to_string(index=False))


def main() -> None:
    parser = argparse.ArgumentParser(description="Resolve NSE signal log outcomes")
    parser.add_argument("--days", type=int, default=None, help="Resolve signals at specific horizon (5/22/66)")
    parser.add_argument("--summary", action="store_true", help="Print performance summary only")
    args = parser.parse_args()

    if args.summary:
        print_summary()
    else:
        log = resolve(args.days)
        print_summary(log)


if __name__ == "__main__":
    main()
