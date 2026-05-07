#!/usr/bin/env python3
"""US / global market intelligence data foundation for Agent Adda.

The first slice owns a curated US/global universe, yfinance-compatible OHLCV
normalization, and a cache-first daily loader. Technical metrics and reports are
implemented in later backlog tasks.
"""

from __future__ import annotations

import argparse
import html
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


def _pct_return(close: pd.Series, periods: int) -> float | None:
    clean = close.dropna()
    if len(clean) <= periods:
        return None
    base = float(clean.iloc[-periods - 1])
    latest = float(clean.iloc[-1])
    if base == 0:
        return None
    return round((latest / base - 1) * 100, 2)


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.astype(float).diff()
    gain = delta.clip(lower=0).rolling(period, min_periods=period).mean()
    loss = (-delta.clip(upper=0)).rolling(period, min_periods=period).mean()
    rs = gain / loss.replace(0, pd.NA)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(100).clip(0, 100)


def _macd(close: pd.Series) -> pd.DataFrame:
    close = close.astype(float)
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    line = ema12 - ema26
    signal = line.ewm(span=9, adjust=False).mean()
    hist = line - signal
    return pd.DataFrame({"MACD": line, "MACD_SIGNAL_LINE": signal, "MACD_HIST": hist})


def _support_resistance(hist: pd.DataFrame, window: int = 20) -> tuple[float | None, float | None]:
    if hist.empty:
        return None, None
    recent = hist.tail(window)
    support = float(pd.to_numeric(recent["LOW"], errors="coerce").min())
    resistance = float(pd.to_numeric(recent["HIGH"], errors="coerce").max())
    return round(support, 2), round(resistance, 2)


def _stage_from_latest(close: float, sma50: float | None, sma200: float | None, sma50_slope: float | None) -> str:
    if sma50 is None or sma200 is None or pd.isna(sma50) or pd.isna(sma200):
        return "UNKNOWN"
    if close > sma50 > sma200 and (sma50_slope or 0) >= 0:
        return "STAGE_2"
    if close < sma50 < sma200:
        return "STAGE_4"
    if close > sma200 and close < sma50:
        return "STAGE_3"
    return "STAGE_1"


def _vcp_flag(hist: pd.DataFrame) -> bool:
    if len(hist) < 60:
        return False
    high = pd.to_numeric(hist["HIGH"], errors="coerce")
    low = pd.to_numeric(hist["LOW"], errors="coerce")
    close = pd.to_numeric(hist["CLOSE"], errors="coerce")
    range_pct = ((high - low) / close.replace(0, pd.NA)).rolling(10, min_periods=8).mean()
    recent = float(range_pct.tail(10).mean())
    prior = float(range_pct.tail(60).head(30).mean())
    hi_52w = float(close.tail(252).max())
    latest = float(close.iloc[-1])
    near_high = hi_52w > 0 and latest >= hi_52w * 0.85
    return bool(prior > 0 and recent < prior * 0.75 and near_high)


def compute_technical_metrics(
    prices: pd.DataFrame,
    benchmark_symbols: tuple[str, str] = ("SPY", "QQQ"),
) -> pd.DataFrame:
    """Compute daily technical metrics for the US/global normalized OHLCV table."""
    columns = [
        "SYMBOL", "DATE", "CLOSE", "RET_1D", "RET_5D", "RET_1M", "RET_3M",
        "SMA_20", "SMA_50", "SMA_200", "SMA_ALIGNMENT", "RSI_14",
        "MACD", "MACD_SIGNAL_LINE", "MACD_HIST", "MACD_SIGNAL",
        "DIST_52W_HIGH_PCT", "SUPPORT", "RESISTANCE", "VCP_FLAG",
        "STAGE", "RS_SPY_1M", "RS_SPY_3M", "RS_QQQ_1M", "RS_QQQ_3M", "RS_STATUS",
    ]
    if prices is None or prices.empty:
        return pd.DataFrame(columns=columns)

    df = prices.copy()
    df["SYMBOL"] = df["SYMBOL"].astype(str).str.upper()
    df["DATE"] = pd.to_datetime(df["DATE"], errors="coerce")
    for col in ["OPEN", "HIGH", "LOW", "CLOSE", "VOLUME"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["SYMBOL", "DATE", "CLOSE"]).sort_values(["SYMBOL", "DATE"])

    benchmark_returns: dict[str, dict[str, float | None]] = {}
    for benchmark in benchmark_symbols:
        b_hist = df[df["SYMBOL"] == benchmark].sort_values("DATE")
        b_close = b_hist["CLOSE"]
        benchmark_returns[benchmark] = {
            "1M": _pct_return(b_close, 21),
            "3M": _pct_return(b_close, 63),
        }

    rows = []
    for symbol, hist in df.groupby("SYMBOL", sort=False):
        hist = hist.sort_values("DATE").copy()
        close = hist["CLOSE"].astype(float)
        latest_close = float(close.iloc[-1])
        sma20_series = close.rolling(20, min_periods=10).mean()
        sma50_series = close.rolling(50, min_periods=25).mean()
        sma200_series = close.rolling(200, min_periods=100).mean()
        sma20 = float(sma20_series.iloc[-1]) if not pd.isna(sma20_series.iloc[-1]) else None
        sma50 = float(sma50_series.iloc[-1]) if not pd.isna(sma50_series.iloc[-1]) else None
        sma200 = float(sma200_series.iloc[-1]) if not pd.isna(sma200_series.iloc[-1]) else None
        sma50_prev = float(sma50_series.iloc[-11]) if len(sma50_series) > 10 and not pd.isna(sma50_series.iloc[-11]) else None
        sma50_slope = None if sma50 is None or sma50_prev in (None, 0) else (sma50 / sma50_prev - 1)

        if sma20 is not None and sma50 is not None and sma200 is not None and latest_close > sma20 > sma50 > sma200:
            sma_alignment = "BULLISH"
        elif sma20 is not None and sma50 is not None and sma200 is not None and latest_close < sma20 < sma50 < sma200:
            sma_alignment = "BEARISH"
        else:
            sma_alignment = "MIXED"

        macd_df = _macd(close)
        macd_latest = macd_df.iloc[-1]
        macd_signal = "BULLISH" if float(macd_latest["MACD_HIST"]) >= 0 else "BEARISH"
        support, resistance = _support_resistance(hist)
        hi_52w = float(close.tail(252).max())
        dist_52w = round((latest_close / hi_52w - 1) * 100, 2) if hi_52w else None
        ret_1m = _pct_return(close, 21)
        ret_3m = _pct_return(close, 63)

        spy_1m = benchmark_returns.get("SPY", {}).get("1M")
        spy_3m = benchmark_returns.get("SPY", {}).get("3M")
        qqq_1m = benchmark_returns.get("QQQ", {}).get("1M")
        qqq_3m = benchmark_returns.get("QQQ", {}).get("3M")
        rs_status = "OK" if spy_1m is not None and qqq_1m is not None else "BENCHMARK_UNAVAILABLE"

        rows.append(
            {
                "SYMBOL": symbol,
                "DATE": hist["DATE"].iloc[-1],
                "CLOSE": round(latest_close, 2),
                "RET_1D": _pct_return(close, 1),
                "RET_5D": _pct_return(close, 5),
                "RET_1M": ret_1m,
                "RET_3M": ret_3m,
                "SMA_20": round(sma20, 2) if sma20 is not None else None,
                "SMA_50": round(sma50, 2) if sma50 is not None else None,
                "SMA_200": round(sma200, 2) if sma200 is not None else None,
                "SMA_ALIGNMENT": sma_alignment,
                "RSI_14": round(float(_rsi(close).iloc[-1]), 2),
                "MACD": round(float(macd_latest["MACD"]), 4),
                "MACD_SIGNAL_LINE": round(float(macd_latest["MACD_SIGNAL_LINE"]), 4),
                "MACD_HIST": round(float(macd_latest["MACD_HIST"]), 4),
                "MACD_SIGNAL": macd_signal,
                "DIST_52W_HIGH_PCT": dist_52w,
                "SUPPORT": support,
                "RESISTANCE": resistance,
                "VCP_FLAG": _vcp_flag(hist),
                "STAGE": _stage_from_latest(latest_close, sma50, sma200, sma50_slope),
                "RS_SPY_1M": round(ret_1m - spy_1m, 2) if ret_1m is not None and spy_1m is not None else pd.NA,
                "RS_SPY_3M": round(ret_3m - spy_3m, 2) if ret_3m is not None and spy_3m is not None else pd.NA,
                "RS_QQQ_1M": round(ret_1m - qqq_1m, 2) if ret_1m is not None and qqq_1m is not None else pd.NA,
                "RS_QQQ_3M": round(ret_3m - qqq_3m, 2) if ret_3m is not None and qqq_3m is not None else pd.NA,
                "RS_STATUS": rs_status,
            }
        )

    return pd.DataFrame(rows).reindex(columns=columns)


SECTOR_ETFS = {
    "XLK", "XLF", "XLE", "XLY", "XLI", "XLU", "XLV", "XLP", "XLB", "XLRE",
    "SMH", "SOXX", "ARKK",
}


def _numeric_series(df: pd.DataFrame, column: str, default: float = 0.0) -> pd.Series:
    if column not in df.columns:
        return pd.Series([default] * len(df), index=df.index, dtype=float)
    return pd.to_numeric(df[column], errors="coerce").fillna(default)


def screen_stage2_leaders(metrics: pd.DataFrame, limit: int = 20) -> pd.DataFrame:
    """Rank Stage 2 leaders with positive relative strength."""
    if metrics is None or metrics.empty:
        return pd.DataFrame()
    df = metrics.copy()
    stage = df.get("STAGE", pd.Series("", index=df.index)).astype(str)
    df = df[stage.eq("STAGE_2")].copy()
    if df.empty:
        return df
    rs = _numeric_series(df, "RS_SPY_3M")
    ret = _numeric_series(df, "RET_1M")
    rsi = _numeric_series(df, "RSI_14", 50)
    alignment_bonus = df.get("SMA_ALIGNMENT", pd.Series("", index=df.index)).astype(str).eq("BULLISH").astype(float) * 5
    df["SCREENER_SCORE"] = (rs * 0.50 + ret * 0.30 + (rsi - 50).clip(lower=0) * 0.20 + alignment_bonus).round(2)
    return df.sort_values("SCREENER_SCORE", ascending=False).head(limit).reset_index(drop=True)


def screen_vcp_setups(metrics: pd.DataFrame, limit: int = 20) -> pd.DataFrame:
    """Return constructive volatility-contraction setups."""
    if metrics is None or metrics.empty:
        return pd.DataFrame()
    df = metrics.copy()
    vcp = df.get("VCP_FLAG", pd.Series(False, index=df.index)).fillna(False).astype(bool)
    alignment = df.get("SMA_ALIGNMENT", pd.Series("", index=df.index)).astype(str)
    df = df[vcp & alignment.ne("BEARISH")].copy()
    if df.empty:
        return df
    rs = _numeric_series(df, "RS_SPY_3M")
    ret = _numeric_series(df, "RET_1M")
    distance_score = (20 + _numeric_series(df, "DIST_52W_HIGH_PCT")).clip(lower=0)
    df["SETUP"] = "VCP"
    df["SCREENER_SCORE"] = (rs * 0.45 + ret * 0.25 + distance_score * 0.30).round(2)
    return df.sort_values("SCREENER_SCORE", ascending=False).head(limit).reset_index(drop=True)


def rank_sector_rotation(metrics: pd.DataFrame, limit: int | None = None) -> pd.DataFrame:
    """Rank US sector/theme ETFs by return, RS, and trend confirmation."""
    if metrics is None or metrics.empty:
        return pd.DataFrame()
    df = metrics.copy()
    df["SYMBOL"] = df["SYMBOL"].astype(str).str.upper()
    df = df[df["SYMBOL"].isin(SECTOR_ETFS)].copy()
    if df.empty:
        return df
    ret1 = _numeric_series(df, "RET_1M")
    ret3 = _numeric_series(df, "RET_3M")
    rs3 = _numeric_series(df, "RS_SPY_3M")
    trend_bonus = df.get("SMA_ALIGNMENT", pd.Series("", index=df.index)).astype(str).eq("BULLISH").astype(float) * 5
    macd_bonus = df.get("MACD_SIGNAL", pd.Series("", index=df.index)).astype(str).eq("BULLISH").astype(float) * 3
    df["ROTATION_SCORE"] = (ret1 * 0.35 + ret3 * 0.25 + rs3 * 0.30 + trend_bonus + macd_bonus).round(2)
    ranked = df.sort_values("ROTATION_SCORE", ascending=False).reset_index(drop=True)
    return ranked.head(limit) if limit else ranked


def _metric_value(metrics: pd.DataFrame, symbol: str, column: str) -> float | None:
    if metrics is None or metrics.empty or column not in metrics.columns:
        return None
    rows = metrics[metrics["SYMBOL"].astype(str).str.upper() == symbol.upper()]
    if rows.empty:
        return None
    value = pd.to_numeric(rows.iloc[0][column], errors="coerce")
    return None if pd.isna(value) else float(value)


def build_risk_dashboard(metrics: pd.DataFrame) -> dict:
    """Classify US/global risk appetite from ETF/index relationships."""
    qqq = _metric_value(metrics, "QQQ", "RET_1M")
    spy = _metric_value(metrics, "SPY", "RET_1M")
    iwm = _metric_value(metrics, "IWM", "RET_1M")
    hyg = _metric_value(metrics, "HYG", "RET_1M")
    lqd = _metric_value(metrics, "LQD", "RET_1M")
    vix = _metric_value(metrics, "^VIX", "RET_1M")

    score = 0
    signals: list[str] = []
    if qqq is not None and spy is not None:
        delta = qqq - spy
        score += 1 if delta > 1 else -1 if delta < -1 else 0
        signals.append(f"QQQ vs SPY 1M: {delta:+.2f}pp")
    if iwm is not None and spy is not None:
        delta = iwm - spy
        score += 1 if delta > 0 else -1 if delta < -3 else 0
        signals.append(f"IWM vs SPY 1M: {delta:+.2f}pp")
    if hyg is not None and lqd is not None:
        delta = hyg - lqd
        score += 1 if delta > 0 else -1 if delta < -1 else 0
        signals.append(f"HYG vs LQD 1M: {delta:+.2f}pp")
    if vix is not None:
        score += 1 if vix < -5 else -1 if vix > 10 else 0
        signals.append(f"VIX 1M: {vix:+.2f}%")

    regime = "risk-on" if score >= 2 else "risk-off" if score <= -2 else "neutral"
    return {
        "regime": regime,
        "score": score,
        "signals": signals,
    }


def _has_positive_momentum(metrics: pd.DataFrame, symbol: str, ret_threshold: float = 5.0, rs_threshold: float = 3.0) -> bool:
    ret = _metric_value(metrics, symbol, "RET_1M")
    rs = _metric_value(metrics, symbol, "RS_SPY_3M")
    return (ret is not None and ret >= ret_threshold) or (rs is not None and rs >= rs_threshold)


def _has_negative_momentum(metrics: pd.DataFrame, symbol: str, ret_threshold: float = -5.0, rs_threshold: float = -3.0) -> bool:
    ret = _metric_value(metrics, symbol, "RET_1M")
    rs = _metric_value(metrics, symbol, "RS_SPY_3M")
    return (ret is not None and ret <= ret_threshold) or (rs is not None and rs <= rs_threshold)


def _readthrough_item(
    nse_sector: str,
    stance: str,
    thesis: str,
    symbols: list[str],
    confidence: str = "medium",
) -> dict:
    return {
        "nse_sector": nse_sector,
        "stance": stance,
        "thesis": thesis,
        "symbols": symbols,
        "confidence": confidence,
    }


def build_india_readthrough(metrics: pd.DataFrame) -> dict:
    """Map US/global signals to deterministic NSE sector implications."""
    risk = build_risk_dashboard(metrics)
    global_regime = risk["regime"]
    implications: list[dict] = []
    source_signals: list[dict] = []

    if _has_positive_momentum(metrics, "QQQ") or _has_positive_momentum(metrics, "^IXIC"):
        if global_regime == "neutral":
            global_regime = "risk-on"
        implications.append(
            _readthrough_item(
                "IT & Technology",
                "positive",
                "US growth and Nasdaq leadership supports Indian IT, digital, and cloud sentiment.",
                ["QQQ", "^IXIC"],
                "medium",
            )
        )
        source_signals.append({"theme": "nasdaq_growth", "symbols": ["QQQ", "^IXIC"], "direction": "positive"})

    if _has_positive_momentum(metrics, "SMH") or _has_positive_momentum(metrics, "SOXX"):
        if global_regime == "neutral":
            global_regime = "risk-on"
        implications.append(
            _readthrough_item(
                "Electronics / EMS",
                "positive",
                "US semiconductor leadership supports EMS, electronics, and semiconductor supply-chain read-through.",
                ["SMH", "SOXX"],
                "high",
            )
        )
        source_signals.append({"theme": "semiconductors", "symbols": ["SMH", "SOXX"], "direction": "positive"})

    if _has_positive_momentum(metrics, "USO", ret_threshold=6.0, rs_threshold=4.0):
        implications.append(
            _readthrough_item(
                "Energy - Oil & Gas",
                "positive",
                "Crude strength can support upstream energy and oil-linked earnings sensitivity.",
                ["USO"],
                "medium",
            )
        )
        implications.append(
            _readthrough_item(
                "Aviation / Paints / Tyres",
                "negative",
                "Higher crude can pressure fuel and input-cost sensitive sectors.",
                ["USO"],
                "medium",
            )
        )
        source_signals.append({"theme": "crude", "symbols": ["USO"], "direction": "mixed"})

    if _has_positive_momentum(metrics, "UUP", ret_threshold=3.0, rs_threshold=2.0):
        implications.append(
            _readthrough_item(
                "EM Flows / FII Sensitive",
                "negative",
                "US dollar strength can pressure emerging-market flows and valuation appetite.",
                ["UUP"],
                "medium",
            )
        )
        source_signals.append({"theme": "dollar_strength", "symbols": ["UUP"], "direction": "negative"})

    if _has_negative_momentum(metrics, "IWM", ret_threshold=-5.0, rs_threshold=-4.0) or risk["regime"] == "risk-off":
        global_regime = "risk-off"
        implications.append(
            _readthrough_item(
                "High Beta / Smallcaps",
                "negative",
                "Weak US small-cap/risk appetite warns against high-beta and liquidity-sensitive Indian pockets.",
                ["IWM", "HYG", "LQD", "^VIX"],
                "high" if risk["regime"] == "risk-off" else "medium",
            )
        )
        source_signals.append({"theme": "risk_appetite", "symbols": ["IWM", "HYG", "LQD", "^VIX"], "direction": risk["regime"]})

    if _has_positive_momentum(metrics, "XLF", ret_threshold=4.0, rs_threshold=3.0):
        implications.append(
            _readthrough_item(
                "Private Banks / NBFC",
                "watch",
                "US financial strength supports global bank risk appetite, but India mapping should be confirmed with domestic credit data.",
                ["XLF"],
                "low",
            )
        )
        source_signals.append({"theme": "financials", "symbols": ["XLF"], "direction": "watch"})

    if _has_positive_momentum(metrics, "GLD", ret_threshold=4.0, rs_threshold=3.0) and risk["regime"] != "risk-on":
        implications.append(
            _readthrough_item(
                "Defensives / Gold Sensitives",
                "watch",
                "Gold strength outside risk-on regimes points to defensive positioning.",
                ["GLD"],
                "medium",
            )
        )
        source_signals.append({"theme": "gold_defensive", "symbols": ["GLD"], "direction": "watch"})

    if not implications:
        implications.append(
            _readthrough_item(
                "Broad Market",
                "watch",
                "No strong US/global read-through signal crossed rule thresholds.",
                [],
                "low",
            )
        )

    return {
        "global_regime": global_regime,
        "risk_score": risk["score"],
        "india_sector_implications": implications,
        "source_signals": source_signals,
        "risk_signals": risk["signals"],
    }


AGENT_BRAND = "Agent Adda - Market Intelligence Agent"
DISCLAIMER = (
    "Not investment advice. For research and learning only. Do not use this "
    "material as trading, investment, or recommendation guidance."
)


def build_us_market_bundle(prices: pd.DataFrame, warnings: list[str] | None = None) -> dict:
    metrics = compute_technical_metrics(prices)
    return {
        "metrics": metrics,
        "stage2": screen_stage2_leaders(metrics),
        "vcp": screen_vcp_setups(metrics),
        "sector_rotation": rank_sector_rotation(metrics),
        "risk_dashboard": build_risk_dashboard(metrics),
        "india_readthrough": build_india_readthrough(metrics),
        "warnings": warnings or [],
    }


def _fmt(value: object, digits: int = 2) -> str:
    if value is None or pd.isna(value):
        return "-"
    if isinstance(value, (int, float)):
        return f"{float(value):,.{digits}f}"
    return html.escape(str(value))


def _table_html(df: pd.DataFrame, columns: list[str], empty_text: str) -> str:
    if df is None or df.empty:
        return f'<p class="empty">{html.escape(empty_text)}</p>'
    existing = [col for col in columns if col in df.columns]
    if not existing:
        return f'<p class="empty">{html.escape(empty_text)}</p>'
    head = "".join(f"<th>{html.escape(col)}</th>" for col in existing)
    rows = []
    for _, row in df.head(20).iterrows():
        cells = "".join(f"<td>{_fmt(row.get(col))}</td>" for col in existing)
        rows.append(f"<tr>{cells}</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table>"


def _readthrough_html(readthrough: dict) -> str:
    items = readthrough.get("india_sector_implications", []) if isinstance(readthrough, dict) else []
    if not items:
        return '<p class="empty">No India read-through signals available.</p>'
    rows = []
    for item in items:
        symbols = ", ".join(item.get("symbols", []))
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(item.get('nse_sector', '-')))}</td>"
            f"<td><span class=\"badge {html.escape(str(item.get('stance', 'watch')))}\">{html.escape(str(item.get('stance', 'watch')).upper())}</span></td>"
            f"<td>{html.escape(str(item.get('thesis', '-')))}</td>"
            f"<td>{html.escape(symbols)}</td>"
            f"<td>{html.escape(str(item.get('confidence', '-')))}</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr><th>NSE Sector</th><th>Stance</th><th>Thesis</th><th>Sources</th><th>Confidence</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def render_us_market_report(
    bundle: dict,
    output_dir: Path | str = Path("reports") / "global",
    latest_dir: Path | str = Path("reports") / "latest",
    report_date: str | None = None,
) -> dict:
    """Render standalone US/global market report and latest pointer."""
    output = Path(output_dir)
    latest = Path(latest_dir)
    output.mkdir(parents=True, exist_ok=True)
    latest.mkdir(parents=True, exist_ok=True)
    as_of = report_date or datetime.now().strftime("%Y-%m-%d")
    filename_date = as_of.replace("-", "")
    report_path = output / f"us_market_report_{filename_date}.html"
    latest_path = latest / "us_market_report.html"

    metrics = bundle.get("metrics", pd.DataFrame())
    index_symbols = {"^GSPC", "^IXIC", "^NDX", "^DJI", "^RUT", "^VIX", "SPY", "QQQ", "DIA", "IWM"}
    index_tape = metrics[metrics["SYMBOL"].astype(str).str.upper().isin(index_symbols)].copy() if not metrics.empty else pd.DataFrame()
    risk = bundle.get("risk_dashboard", {})
    readthrough = bundle.get("india_readthrough", {})
    warnings = bundle.get("warnings", [])
    warnings_html = "".join(f"<li>{html.escape(str(w))}</li>" for w in warnings) if warnings else "<li>No data warnings.</li>"

    html_doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>US / Global Market Context - {html.escape(as_of)}</title>
  <style>
    body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; background:#f3f6fb; color:#0f172a; }}
    header {{ background:#08111f; color:#e5f0ff; padding:28px 36px; }}
    main {{ max-width:1180px; margin:0 auto; padding:24px; }}
    h1 {{ margin:0 0 8px; font-size:30px; }}
    h2 {{ margin:0 0 14px; font-size:18px; }}
    .brand {{ color:#8dd3ff; font-weight:700; font-size:13px; letter-spacing:.04em; text-transform:uppercase; }}
    .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:16px; }}
    .card {{ background:#fff; border:1px solid #dbe3ef; border-radius:8px; box-shadow:0 1px 2px rgba(15,23,42,.05); padding:18px; margin-bottom:16px; }}
    .metric {{ font-size:30px; font-weight:800; text-transform:capitalize; }}
    .muted {{ color:#64748b; }}
    table {{ width:100%; border-collapse:collapse; font-size:13px; }}
    th,td {{ padding:9px 8px; border-bottom:1px solid #e2e8f0; text-align:left; vertical-align:top; }}
    th {{ color:#475569; background:#f8fafc; font-size:12px; text-transform:uppercase; letter-spacing:.03em; }}
    .badge {{ display:inline-block; padding:3px 8px; border-radius:999px; font-size:11px; font-weight:800; }}
    .positive {{ background:#dcfce7; color:#166534; }}
    .negative {{ background:#fee2e2; color:#991b1b; }}
    .watch {{ background:#fef3c7; color:#92400e; }}
    .empty {{ color:#64748b; font-style:italic; }}
    .disclaimer {{ background:#fff7ed; border-color:#fed7aa; color:#7c2d12; }}
  </style>
</head>
<body>
  <header>
    <div class="brand">{AGENT_BRAND}</div>
    <h1>Global / US Market Context</h1>
    <div class="muted">As of {html.escape(as_of)} · Daily US/global research layer</div>
  </header>
  <main>
    <section class="grid">
      <div class="card">
        <h2>Risk Regime</h2>
        <div class="metric">{html.escape(str(risk.get("regime", "unavailable")))}</div>
        <p class="muted">Score: {_fmt(risk.get("score"), 0)}</p>
      </div>
      <div class="card">
        <h2>Source Signals</h2>
        <ul>{"".join(f"<li>{html.escape(str(s))}</li>" for s in risk.get("signals", [])) or "<li>No risk signals available.</li>"}</ul>
      </div>
    </section>
    <section class="card">
      <h2>US Index Tape</h2>
      {_table_html(index_tape, ["SYMBOL", "CLOSE", "RET_1D", "RET_1M", "SMA_ALIGNMENT", "MACD_SIGNAL", "STAGE"], "No US index tape available.")}
    </section>
    <section class="card">
      <h2>Sector ETF Rotation</h2>
      {_table_html(bundle.get("sector_rotation", pd.DataFrame()), ["SYMBOL", "RET_1M", "RET_3M", "RS_SPY_3M", "ROTATION_SCORE", "SMA_ALIGNMENT", "MACD_SIGNAL"], "No sector ETF rotation available.")}
    </section>
    <section class="card">
      <h2>Stage 2 Leaders</h2>
      {_table_html(bundle.get("stage2", pd.DataFrame()), ["SYMBOL", "RET_1M", "RS_SPY_3M", "RSI_14", "STAGE", "SCREENER_SCORE"], "No Stage 2 leaders available.")}
    </section>
    <section class="card">
      <h2>VCP Setups</h2>
      {_table_html(bundle.get("vcp", pd.DataFrame()), ["SYMBOL", "SETUP", "RET_1M", "RS_SPY_3M", "DIST_52W_HIGH_PCT", "SCREENER_SCORE"], "No VCP setups available.")}
    </section>
    <section class="card">
      <h2>India Read-Through</h2>
      {_readthrough_html(readthrough)}
    </section>
    <section class="card">
      <h2>Data Freshness & Warnings</h2>
      <ul>{warnings_html}</ul>
    </section>
    <section class="card disclaimer">
      <h2>Disclaimer</h2>
      <p>{DISCLAIMER}</p>
    </section>
  </main>
</body>
</html>
"""
    report_path.write_text(html_doc)
    latest_path.write_text(html_doc)
    return {
        "status": "ok",
        "report_path": str(report_path),
        "latest_path": str(latest_path),
        "report_date": as_of,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Agent Adda US/global market intelligence")
    parser.add_argument("--root-dir", default=str(DEFAULT_ROOT))
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--lookback-days", type=int, default=365)
    parser.add_argument("--symbols", nargs="*", default=None)
    parser.add_argument("--report", action="store_true", help="Render the standalone US/global HTML report")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    loader = GlobalMarketDataLoader(root_dir=Path(args.root_dir))
    result = loader.load(symbols=args.symbols, force=args.force, lookback_days=args.lookback_days)
    report_result = None
    if args.report and result["status"] in {"ok", "empty"}:
        bundle = build_us_market_bundle(result["prices"], warnings=result["warnings"])
        report_result = render_us_market_report(bundle)
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
    if report_result:
        payload["report_path"] = report_result["report_path"]
        payload["latest_path"] = report_result["latest_path"]
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if result["status"] in {"ok", "empty"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
