import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from global_market_intelligence import (
    DEFAULT_US_UNIVERSE,
    GlobalMarketDataLoader,
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


if __name__ == "__main__":
    unittest.main()
