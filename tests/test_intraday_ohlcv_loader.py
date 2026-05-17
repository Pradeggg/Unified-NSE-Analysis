import importlib
import os
import sys
import unittest
from unittest.mock import Mock, patch

import pandas as pd


class IntradayOhlcvLoaderTests(unittest.TestCase):
    def _fresh_module(self, env: dict[str, str] | None = None):
        old_env = {key: os.environ.get(key) for key in (env or {})}
        os.environ.update(env or {})
        try:
            sys.modules.pop("terminal.intraday_ohlcv_loader", None)
            return importlib.import_module("terminal.intraday_ohlcv_loader")
        finally:
            for key, value in old_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_env_symbol_universe_is_deduped_and_uppercase(self):
        loader = self._fresh_module({"AGENT_ADDA_OHLCV_SYMBOLS": "geship, RELIANCE, geship"})

        self.assertEqual(loader._symbol_universe(top_n=10), ["GESHIP", "RELIANCE"])

    def test_default_symbol_universe_starts_with_index_futures_symbols(self):
        loader = self._fresh_module()

        self.assertEqual(loader.LOAD_INTERVAL_SEC, 900)
        self.assertEqual(
            loader._symbol_universe(top_n=5),
            ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50"],
        )

    def test_load_once_fetches_candles_and_persists_to_postgres(self):
        loader = self._fresh_module()
        df = pd.DataFrame(
            {
                "Open": [100.0, 101.0],
                "High": [102.0, 103.0],
                "Low": [99.0, 100.0],
                "Close": [101.0, 102.0],
                "Volume": [1000, 2000],
            },
            index=pd.date_range("2026-05-15 09:15:00", periods=2, freq="15min"),
        )

        with patch.object(loader, "get_intraday_candles", return_value=df) as fetch, patch.object(
            loader,
            "persist_intraday_bars",
            return_value={"ok": True, "rows_inserted": 2, "schema": "intraday", "table": "ohlcv_bars"},
        ) as persist:
            result = loader._load_once(symbols=["GESHIP"], timeframes=["15m"])

        fetch.assert_called_once_with("GESHIP", "15m")
        persist.assert_called_once()
        args, kwargs = persist.call_args
        self.assertEqual(args[0], "GESHIP")
        self.assertEqual(kwargs["timeframe"], "15m")
        self.assertEqual(kwargs["source"], "Yahoo Finance (yfinance)")
        self.assertEqual(len(args[1]), 2)
        self.assertEqual(result["symbols_scanned"], 1)
        self.assertEqual(result["attempted"], 1)
        self.assertEqual(result["persisted_rows"], 2)
        self.assertEqual(result["errors"], [])

    def test_load_once_records_empty_candle_errors_without_persisting(self):
        loader = self._fresh_module()

        with patch.object(loader, "get_intraday_candles", return_value=pd.DataFrame()), patch.object(
            loader, "persist_intraday_bars"
        ) as persist:
            result = loader._load_once(symbols=["GESHIP"], timeframes=["15m"])

        persist.assert_not_called()
        self.assertEqual(result["persisted_rows"], 0)
        self.assertEqual(result["errors"], [{"symbol": "GESHIP", "timeframe": "15m", "error": "no_candles"}])

    def test_start_background_loader_is_idempotent(self):
        loader = self._fresh_module()
        loader._started = False
        fake_thread = Mock()

        with patch.object(loader.threading, "Thread", return_value=fake_thread) as thread:
            first = loader.start_background_ohlcv_loader()
            second = loader.start_background_ohlcv_loader()

        self.assertTrue(first)
        self.assertFalse(second)
        thread.assert_called_once()
        fake_thread.start.assert_called_once()


if __name__ == "__main__":
    unittest.main()
