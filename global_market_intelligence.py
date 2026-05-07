#!/usr/bin/env python3
"""US / global market intelligence data foundation for Agent Adda.

The first slice owns a curated US/global universe, yfinance-compatible OHLCV
normalization, and a cache-first daily loader. Technical metrics and reports are
implemented in later backlog tasks.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Iterable

import pandas as pd


DEFAULT_ROOT = Path("data") / "global_market"
CACHE_TTL_HOURS = 24
PRICE_COLUMNS = ["SYMBOL", "DATE", "OPEN", "HIGH", "LOW", "CLOSE", "VOLUME", "SOURCE"]


@dataclass(frozen=True)
class UniverseSymbol:
    symbol: str
    name: str
    asset_type: str
    group: str
    benchmark: str
    india_readthrough_tags: tuple[str, ...] = ()


DEFAULT_US_UNIVERSE: tuple[UniverseSymbol, ...] = (
    UniverseSymbol("^GSPC", "S&P 500", "index", "indices", "SPY", ("global_risk",)),
    UniverseSymbol("^IXIC", "Nasdaq Composite", "index", "indices", "QQQ", ("it", "growth")),
    UniverseSymbol("^NDX", "Nasdaq 100", "index", "indices", "QQQ", ("it", "growth")),
    UniverseSymbol("^DJI", "Dow Jones Industrial Average", "index", "indices", "DIA", ("industrials",)),
    UniverseSymbol("^RUT", "Russell 2000", "index", "indices", "IWM", ("risk_on", "smallcaps")),
    UniverseSymbol("^VIX", "CBOE Volatility Index", "index", "risk", "SPY", ("risk_off",)),
    UniverseSymbol("SPY", "SPDR S&P 500 ETF", "etf", "core_etf", "SPY", ("global_risk",)),
    UniverseSymbol("QQQ", "Invesco QQQ Trust", "etf", "core_etf", "QQQ", ("it", "growth")),
    UniverseSymbol("DIA", "SPDR Dow Jones Industrial Average ETF", "etf", "core_etf", "SPY", ("industrials",)),
    UniverseSymbol("IWM", "iShares Russell 2000 ETF", "etf", "core_etf", "SPY", ("risk_on", "smallcaps")),
    UniverseSymbol("XLK", "Technology Select Sector SPDR", "etf", "sector_etf", "SPY", ("it",)),
    UniverseSymbol("XLF", "Financial Select Sector SPDR", "etf", "sector_etf", "SPY", ("banks", "nbfc")),
    UniverseSymbol("XLE", "Energy Select Sector SPDR", "etf", "sector_etf", "SPY", ("energy",)),
    UniverseSymbol("XLY", "Consumer Discretionary Select Sector SPDR", "etf", "sector_etf", "SPY", ("consumption",)),
    UniverseSymbol("XLI", "Industrial Select Sector SPDR", "etf", "sector_etf", "SPY", ("industrials", "capital_goods")),
    UniverseSymbol("XLU", "Utilities Select Sector SPDR", "etf", "sector_etf", "SPY", ("defensive", "power")),
    UniverseSymbol("XLV", "Health Care Select Sector SPDR", "etf", "sector_etf", "SPY", ("pharma", "healthcare")),
    UniverseSymbol("XLP", "Consumer Staples Select Sector SPDR", "etf", "sector_etf", "SPY", ("fmcg", "defensive")),
    UniverseSymbol("XLB", "Materials Select Sector SPDR", "etf", "sector_etf", "SPY", ("metals", "chemicals")),
    UniverseSymbol("XLRE", "Real Estate Select Sector SPDR", "etf", "sector_etf", "SPY", ("realty",)),
    UniverseSymbol("SMH", "VanEck Semiconductor ETF", "etf", "theme_etf", "QQQ", ("semiconductors", "ems", "it")),
    UniverseSymbol("SOXX", "iShares Semiconductor ETF", "etf", "theme_etf", "QQQ", ("semiconductors", "ems", "it")),
    UniverseSymbol("ARKK", "ARK Innovation ETF", "etf", "theme_etf", "QQQ", ("growth", "risk_on")),
    UniverseSymbol("TLT", "iShares 20+ Year Treasury Bond ETF", "rates_proxy", "macro_etf", "SPY", ("rates", "fii_flows")),
    UniverseSymbol("HYG", "iShares High Yield Corporate Bond ETF", "rates_proxy", "macro_etf", "SPY", ("credit", "risk_on")),
    UniverseSymbol("LQD", "iShares Investment Grade Corporate Bond ETF", "rates_proxy", "macro_etf", "SPY", ("credit",)),
    UniverseSymbol("GLD", "SPDR Gold Shares", "commodity", "macro_etf", "SPY", ("gold", "risk_off")),
    UniverseSymbol("USO", "United States Oil Fund", "commodity", "macro_etf", "SPY", ("crude", "energy")),
    UniverseSymbol("UUP", "Invesco DB US Dollar Index Bullish Fund", "currency", "macro_etf", "SPY", ("dxy", "fii_flows")),
    UniverseSymbol("AAPL", "Apple", "stock", "mag7", "QQQ", ("it", "electronics")),
    UniverseSymbol("MSFT", "Microsoft", "stock", "mag7", "QQQ", ("it", "cloud")),
    UniverseSymbol("NVDA", "NVIDIA", "stock", "mag7", "QQQ", ("semiconductors", "ai", "ems")),
    UniverseSymbol("AMZN", "Amazon", "stock", "mag7", "QQQ", ("consumption", "cloud")),
    UniverseSymbol("META", "Meta Platforms", "stock", "mag7", "QQQ", ("internet", "growth")),
    UniverseSymbol("GOOGL", "Alphabet", "stock", "mag7", "QQQ", ("internet", "it")),
    UniverseSymbol("TSLA", "Tesla", "stock", "mag7", "QQQ", ("auto", "ev")),
    UniverseSymbol("AMD", "Advanced Micro Devices", "stock", "semis_ai", "QQQ", ("semiconductors", "it")),
    UniverseSymbol("AVGO", "Broadcom", "stock", "semis_ai", "QQQ", ("semiconductors", "it")),
    UniverseSymbol("MU", "Micron Technology", "stock", "semis_ai", "QQQ", ("semiconductors", "memory")),
    UniverseSymbol("ARM", "Arm Holdings", "stock", "semis_ai", "QQQ", ("semiconductors", "ip")),
    UniverseSymbol("TSM", "Taiwan Semiconductor", "stock", "semis_ai", "QQQ", ("semiconductors", "ems")),
    UniverseSymbol("ASML", "ASML Holding", "stock", "semis_ai", "QQQ", ("semiconductors", "capital_goods")),
    UniverseSymbol("MRVL", "Marvell Technology", "stock", "semis_ai", "QQQ", ("semiconductors", "networking")),
    UniverseSymbol("JPM", "JPMorgan Chase", "stock", "financials", "SPY", ("banks",)),
    UniverseSymbol("BAC", "Bank of America", "stock", "financials", "SPY", ("banks",)),
    UniverseSymbol("GS", "Goldman Sachs", "stock", "financials", "SPY", ("capital_markets",)),
    UniverseSymbol("MS", "Morgan Stanley", "stock", "financials", "SPY", ("capital_markets",)),
    UniverseSymbol("V", "Visa", "stock", "financials", "SPY", ("payments", "consumption")),
    UniverseSymbol("MA", "Mastercard", "stock", "financials", "SPY", ("payments", "consumption")),
    UniverseSymbol("XOM", "Exxon Mobil", "stock", "energy_industrial_defense", "SPY", ("energy", "crude")),
    UniverseSymbol("CVX", "Chevron", "stock", "energy_industrial_defense", "SPY", ("energy", "crude")),
    UniverseSymbol("CAT", "Caterpillar", "stock", "energy_industrial_defense", "SPY", ("capital_goods", "industrials")),
    UniverseSymbol("GE", "GE Aerospace", "stock", "energy_industrial_defense", "SPY", ("capital_goods", "defense")),
    UniverseSymbol("LMT", "Lockheed Martin", "stock", "energy_industrial_defense", "SPY", ("defense",)),
    UniverseSymbol("RTX", "RTX", "stock", "energy_industrial_defense", "SPY", ("defense",)),
    UniverseSymbol("WMT", "Walmart", "stock", "consumer_retail", "SPY", ("fmcg", "consumption")),
    UniverseSymbol("COST", "Costco", "stock", "consumer_retail", "SPY", ("fmcg", "consumption")),
    UniverseSymbol("HD", "Home Depot", "stock", "consumer_retail", "SPY", ("realty", "consumption")),
    UniverseSymbol("MCD", "McDonald's", "stock", "consumer_retail", "SPY", ("consumption",)),
    UniverseSymbol("NKE", "Nike", "stock", "consumer_retail", "SPY", ("consumption",)),
    UniverseSymbol("CRM", "Salesforce", "stock", "software_cloud", "QQQ", ("it", "cloud")),
    UniverseSymbol("ORCL", "Oracle", "stock", "software_cloud", "QQQ", ("it", "cloud")),
    UniverseSymbol("ADBE", "Adobe", "stock", "software_cloud", "QQQ", ("it", "software")),
    UniverseSymbol("NOW", "ServiceNow", "stock", "software_cloud", "QQQ", ("it", "software")),
    UniverseSymbol("SNOW", "Snowflake", "stock", "software_cloud", "QQQ", ("it", "cloud")),
    UniverseSymbol("PLTR", "Palantir", "stock", "software_cloud", "QQQ", ("it", "ai")),
)


def universe_records(universe: Iterable[UniverseSymbol] = DEFAULT_US_UNIVERSE) -> list[dict]:
    """Return JSON/CSV-friendly universe records."""
    records = []
    for item in universe:
        row = asdict(item)
        row["india_readthrough_tags"] = list(item.india_readthrough_tags)
        records.append(row)
    return records


def cache_is_fresh(path: Path | str, ttl_hours: int = CACHE_TTL_HOURS) -> bool:
    cache_path = Path(path)
    if not cache_path.exists():
        return False
    age = datetime.now() - datetime.fromtimestamp(cache_path.stat().st_mtime)
    return age < timedelta(hours=ttl_hours)


def normalize_ohlcv(symbol: str, raw: pd.DataFrame, source: str = "yfinance") -> pd.DataFrame:
    """Normalize yfinance-style OHLCV to Agent Adda's stable schema."""
    if raw is None or raw.empty:
        return pd.DataFrame(columns=PRICE_COLUMNS)

    df = raw.copy()
    if "Date" not in df.columns:
        df = df.reset_index()
    column_map = {
        "Date": "DATE",
        "Datetime": "DATE",
        "Open": "OPEN",
        "High": "HIGH",
        "Low": "LOW",
        "Close": "CLOSE",
        "Volume": "VOLUME",
    }
    df = df.rename(columns=column_map)
    for col in ["OPEN", "HIGH", "LOW", "CLOSE", "VOLUME"]:
        if col not in df.columns:
            df[col] = pd.NA
    if "DATE" not in df.columns:
        df["DATE"] = pd.NaT

    out = pd.DataFrame(
        {
            "SYMBOL": str(symbol).upper(),
            "DATE": pd.to_datetime(df["DATE"], errors="coerce").dt.tz_localize(None),
            "OPEN": pd.to_numeric(df["OPEN"], errors="coerce"),
            "HIGH": pd.to_numeric(df["HIGH"], errors="coerce"),
            "LOW": pd.to_numeric(df["LOW"], errors="coerce"),
            "CLOSE": pd.to_numeric(df["CLOSE"], errors="coerce"),
            "VOLUME": pd.to_numeric(df["VOLUME"], errors="coerce").fillna(0).astype("int64"),
            "SOURCE": source,
        }
    )
    return out.dropna(subset=["DATE", "CLOSE"]).sort_values(["SYMBOL", "DATE"]).reset_index(drop=True)


def _default_yfinance_fetch(symbols: list[str], lookback_days: int) -> pd.DataFrame:
    try:
        import yfinance as yf
    except ImportError:
        raise RuntimeError("yfinance is not installed. Install with: .venv/bin/python -m pip install yfinance")

    frames = []
    period = f"{lookback_days}d"
    for symbol in symbols:
        try:
            raw = yf.Ticker(symbol).history(period=period, auto_adjust=True)
            normalized = normalize_ohlcv(symbol, raw)
            if not normalized.empty:
                frames.append(normalized)
        except Exception:
            continue
    if not frames:
        return pd.DataFrame(columns=PRICE_COLUMNS)
    return pd.concat(frames, ignore_index=True)


class GlobalMarketDataLoader:
    """Cache-first daily OHLCV loader for the curated US/global universe."""

    def __init__(
        self,
        root_dir: Path | str = DEFAULT_ROOT,
        universe: Iterable[UniverseSymbol] = DEFAULT_US_UNIVERSE,
        fetcher: Callable[[list[str], int], pd.DataFrame] | None = None,
        ttl_hours: int = CACHE_TTL_HOURS,
    ):
        self.root_dir = Path(root_dir)
        self.universe = tuple(universe)
        self.fetcher = fetcher or _default_yfinance_fetch
        self.ttl_hours = ttl_hours
        self.prices_path = self.root_dir / "prices.csv"
        self.snapshot_path = self.root_dir / "latest_snapshot.csv"
        self.universe_path = self.root_dir / "universe.json"

    def _write_universe(self) -> None:
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.universe_path.write_text(json.dumps(universe_records(self.universe), indent=2, sort_keys=True) + "\n")

    def _latest_snapshot(self, prices: pd.DataFrame) -> pd.DataFrame:
        if prices.empty:
            return pd.DataFrame(columns=PRICE_COLUMNS)
        df = prices.copy()
        df["DATE"] = pd.to_datetime(df["DATE"], errors="coerce")
        return df.sort_values(["SYMBOL", "DATE"]).groupby("SYMBOL", as_index=False).tail(1).reset_index(drop=True)

    def load(self, symbols: list[str] | None = None, force: bool = False, lookback_days: int = 365) -> dict:
        selected = [s.upper() for s in (symbols or [item.symbol for item in self.universe])]
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self._write_universe()

        if not force and cache_is_fresh(self.prices_path, self.ttl_hours):
            try:
                cached = pd.read_csv(self.prices_path, parse_dates=["DATE"])
                cached = cached[cached["SYMBOL"].isin(selected)].reset_index(drop=True)
                snapshot = self._latest_snapshot(cached)
                snapshot.to_csv(self.snapshot_path, index=False)
                return {
                    "status": "ok",
                    "source": "cache",
                    "warnings": [],
                    "prices": cached,
                    "latest_snapshot": snapshot,
                    "prices_path": str(self.prices_path),
                    "snapshot_path": str(self.snapshot_path),
                    "universe_path": str(self.universe_path),
                }
            except Exception as exc:
                return {
                    "status": "error",
                    "source": "cache",
                    "warnings": [f"Cache read failed. Re-run with force=True. Error: {exc}"],
                    "prices": pd.DataFrame(columns=PRICE_COLUMNS),
                    "latest_snapshot": pd.DataFrame(columns=PRICE_COLUMNS),
                    "prices_path": str(self.prices_path),
                    "snapshot_path": str(self.snapshot_path),
                    "universe_path": str(self.universe_path),
                }

        try:
            prices = self.fetcher(selected, lookback_days)
            prices = prices.reindex(columns=PRICE_COLUMNS)
            prices["DATE"] = pd.to_datetime(prices["DATE"], errors="coerce")
            prices = prices.dropna(subset=["DATE", "CLOSE"]).sort_values(["SYMBOL", "DATE"]).reset_index(drop=True)
            snapshot = self._latest_snapshot(prices)
            prices.to_csv(self.prices_path, index=False)
            snapshot.to_csv(self.snapshot_path, index=False)
            warnings = []
            missing = sorted(set(selected) - set(prices["SYMBOL"].unique()))
            if missing:
                warnings.append(f"Missing symbols: {', '.join(missing)}")
            return {
                "status": "ok" if not prices.empty else "empty",
                "source": "fetch",
                "warnings": warnings,
                "prices": prices,
                "latest_snapshot": snapshot,
                "prices_path": str(self.prices_path),
                "snapshot_path": str(self.snapshot_path),
                "universe_path": str(self.universe_path),
            }
        except Exception as exc:
            return {
                "status": "error",
                "source": "fetch",
                "warnings": [str(exc)],
                "prices": pd.DataFrame(columns=PRICE_COLUMNS),
                "latest_snapshot": pd.DataFrame(columns=PRICE_COLUMNS),
                "prices_path": str(self.prices_path),
                "snapshot_path": str(self.snapshot_path),
                "universe_path": str(self.universe_path),
            }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Agent Adda US/global market intelligence")
    parser.add_argument("--root-dir", default=str(DEFAULT_ROOT))
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--lookback-days", type=int, default=365)
    parser.add_argument("--symbols", nargs="*", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    loader = GlobalMarketDataLoader(root_dir=Path(args.root_dir))
    result = loader.load(symbols=args.symbols, force=args.force, lookback_days=args.lookback_days)
    payload = {
        "status": result["status"],
        "source": result["source"],
        "warnings": result["warnings"],
        "rows": int(len(result["prices"])),
        "snapshot_rows": int(len(result["latest_snapshot"])),
        "prices_path": result["prices_path"],
        "snapshot_path": result["snapshot_path"],
        "universe_path": result["universe_path"],
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if result["status"] in {"ok", "empty"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
