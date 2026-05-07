import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from global_market_intelligence import (
    DEFAULT_US_UNIVERSE,
    GlobalMarketDataLoader,
    compute_technical_metrics,
    normalize_ohlcv,
    universe_records,
)


class GlobalMarketIntelligenceTests(unittest.TestCase):
    def test_default_universe_has_required_groups_and_benchmarks(self):
        records = universe_records(DEFAULT_US_UNIVERSE)
        symbols = {row["symbol"] for row in records}

        self.assertIn("SPY", symbols)
        self.assertIn("QQQ", symbols)
        self.assertIn("NVDA", symbols)
        for row in records:
            self.assertIn(row["asset_type"], {"index", "etf", "stock", "commodity", "currency", "rates_proxy"})
            self.assertTrue(row["benchmark"])

    def test_normalize_ohlcv_returns_standard_columns(self):
        raw = pd.DataFrame(
            {
                "Date": pd.to_datetime(["2026-05-04", "2026-05-05"]),
                "Open": [100.0, 101.0],
                "High": [102.0, 103.0],
                "Low": [99.0, 100.0],
                "Close": [101.0, 102.0],
                "Volume": [1000, 1200],
            }
        )

        result = normalize_ohlcv("SPY", raw)

        self.assertEqual(list(result.columns), ["SYMBOL", "DATE", "OPEN", "HIGH", "LOW", "CLOSE", "VOLUME", "SOURCE"])
        self.assertEqual(result.loc[0, "SYMBOL"], "SPY")
        self.assertEqual(result.loc[0, "SOURCE"], "yfinance")

    def test_loader_fetches_writes_cache_and_latest_snapshot(self):
        def fake_fetch(symbols, lookback_days):
            return pd.DataFrame(
                {
                    "SYMBOL": ["SPY", "SPY", "QQQ"],
                    "DATE": pd.to_datetime(["2026-05-04", "2026-05-05", "2026-05-05"]),
                    "OPEN": [100.0, 101.0, 200.0],
                    "HIGH": [102.0, 103.0, 205.0],
                    "LOW": [99.0, 100.0, 198.0],
                    "CLOSE": [101.0, 102.0, 204.0],
                    "VOLUME": [1000, 1200, 1500],
                    "SOURCE": ["fake", "fake", "fake"],
                }
            )

        with TemporaryDirectory() as td:
            loader = GlobalMarketDataLoader(root_dir=Path(td), fetcher=fake_fetch)
            result = loader.load(symbols=["SPY", "QQQ"], force=True)

            self.assertEqual(result["status"], "ok")
            self.assertTrue((Path(td) / "prices.csv").exists())
            self.assertTrue((Path(td) / "latest_snapshot.csv").exists())
            self.assertTrue((Path(td) / "universe.json").exists())
            self.assertEqual(len(result["prices"]), 3)

    def test_loader_uses_fresh_cache_without_fetching(self):
        calls = []

        def fake_fetch(symbols, lookback_days):
            calls.append(symbols)
            return pd.DataFrame(
                {
                    "SYMBOL": ["SPY"],
                    "DATE": pd.to_datetime(["2026-05-05"]),
                    "OPEN": [100.0],
                    "HIGH": [102.0],
                    "LOW": [99.0],
                    "CLOSE": [101.0],
                    "VOLUME": [1000],
                    "SOURCE": ["fake"],
                }
            )

        with TemporaryDirectory() as td:
            loader = GlobalMarketDataLoader(root_dir=Path(td), fetcher=fake_fetch)
            first = loader.load(symbols=["SPY"], force=True)
            second = loader.load(symbols=["SPY"], force=False)

            self.assertEqual(first["status"], "ok")
            self.assertEqual(second["status"], "ok")
            self.assertEqual(len(calls), 1)

    def test_compute_technical_metrics_adds_rs_stage_and_vcp_columns(self):
        dates = pd.date_range("2025-06-01", periods=260, freq="D")
        rows = []
        for i, date in enumerate(dates):
            spy_close = 100 + i * 0.25
            qqq_close = 120 + i * 0.35
            nvda_close = 80 + i * 0.80
            for symbol, close, volume in [
                ("SPY", spy_close, 1_000_000),
                ("QQQ", qqq_close, 1_200_000),
                ("NVDA", nvda_close, 2_000_000),
            ]:
                rows.append(
                    {
                        "SYMBOL": symbol,
                        "DATE": date,
                        "OPEN": close - 0.5,
                        "HIGH": close + 1.0,
                        "LOW": close - 1.0,
                        "CLOSE": close,
                        "VOLUME": volume,
                        "SOURCE": "fixture",
                    }
                )
        prices = pd.DataFrame(rows)

        metrics = compute_technical_metrics(prices)
        nvda = metrics.set_index("SYMBOL").loc["NVDA"]

        self.assertGreater(nvda["RET_1M"], 0)
        self.assertEqual(nvda["SMA_ALIGNMENT"], "BULLISH")
        self.assertEqual(nvda["MACD_SIGNAL"], "BULLISH")
        self.assertEqual(nvda["STAGE"], "STAGE_2")
        self.assertGreater(nvda["RS_SPY_3M"], 0)
        self.assertGreater(nvda["RS_QQQ_3M"], 0)
        self.assertIn("VCP_FLAG", metrics.columns)
        self.assertIn("SUPPORT", metrics.columns)
        self.assertIn("RESISTANCE", metrics.columns)

    def test_compute_technical_metrics_degrades_when_benchmark_missing(self):
        dates = pd.date_range("2026-01-01", periods=60, freq="D")
        prices = pd.DataFrame(
            {
                "SYMBOL": ["AAPL"] * len(dates),
                "DATE": dates,
                "OPEN": range(100, 160),
                "HIGH": range(101, 161),
                "LOW": range(99, 159),
                "CLOSE": range(100, 160),
                "VOLUME": [1_000_000] * len(dates),
                "SOURCE": ["fixture"] * len(dates),
            }
        )

        metrics = compute_technical_metrics(prices)
        row = metrics.iloc[0]

        self.assertTrue(pd.isna(row["RS_SPY_1M"]))
        self.assertTrue(pd.isna(row["RS_QQQ_1M"]))
        self.assertEqual(row["RS_STATUS"], "BENCHMARK_UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
