import importlib
import os
import sys
import unittest
from unittest.mock import Mock, patch


class FnoIntradayLoaderTests(unittest.TestCase):
    def _fresh_module(self, env: dict[str, str] | None = None):
        old_env = {key: os.environ.get(key) for key in (env or {})}
        os.environ.update(env or {})
        try:
            sys.modules.pop("terminal.fno_intraday_loader", None)
            return importlib.import_module("terminal.fno_intraday_loader")
        finally:
            for key, value in old_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_default_loader_tracks_index_futures_every_15_minutes(self):
        loader = self._fresh_module()

        self.assertEqual(loader.LOAD_INTERVAL_SEC, 900)
        self.assertEqual(loader._symbol_universe(), ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50"])

    def test_env_symbols_override_default_universe(self):
        loader = self._fresh_module({"AGENT_ADDA_FNO_SYMBOLS": "nifty, banknifty, nifty"})

        self.assertEqual(loader._symbol_universe(), ["NIFTY", "BANKNIFTY"])

    def test_load_once_fetches_and_persists_futures_snapshots(self):
        loader = self._fresh_module()
        snapshot = {
            "symbol": "NIFTY",
            "underlying": 23700.0,
            "source": "live-nse-api",
            "futures": [{"expiry": "2026-05-28", "last_price": 23742.0}],
        }

        with patch.object(loader, "fetch_live_futures", return_value=snapshot) as fetch, patch.object(
            loader, "get_lot_size", return_value=75
        ), patch.object(
            loader,
            "persist_live_futures_snapshot",
            return_value={"ok": True, "rows_inserted": 1, "schema": "intraday", "table": "futures_snapshots"},
        ) as persist:
            result = loader._load_once(symbols=["NIFTY"])

        fetch.assert_called_once_with("NIFTY")
        persist.assert_called_once()
        persisted_snapshot = persist.call_args.args[0]
        self.assertEqual(persisted_snapshot["symbol"], "NIFTY")
        self.assertEqual(persisted_snapshot["lot_size"], 75)
        self.assertIn("as_of", persisted_snapshot)
        self.assertEqual(result["persisted_rows"], 1)
        self.assertEqual(result["errors"], [])

    def test_load_once_skips_eod_fallback_to_keep_intraday_history_live_only(self):
        loader = self._fresh_module()
        snapshot = {
            "symbol": "NIFTY",
            "underlying": 23700.0,
            "source": "eod-fallback",
            "futures": [{"expiry": "2026-05-28", "last_price": 23742.0}],
        }

        with patch.object(loader, "fetch_live_futures", return_value=snapshot), patch.object(
            loader, "persist_live_futures_snapshot"
        ) as persist:
            result = loader._load_once(symbols=["NIFTY"])

        persist.assert_not_called()
        self.assertEqual(result["persisted_rows"], 0)
        self.assertEqual(result["errors"], [{"symbol": "NIFTY", "error": "non_live_source:eod-fallback"}])

    def test_start_background_loader_is_idempotent(self):
        loader = self._fresh_module()
        loader._started = False
        fake_thread = Mock()

        with patch.object(loader.threading, "Thread", return_value=fake_thread) as thread:
            first = loader.start_background_fno_loader()
            second = loader.start_background_fno_loader()

        self.assertTrue(first)
        self.assertFalse(second)
        thread.assert_called_once()
        fake_thread.start.assert_called_once()


if __name__ == "__main__":
    unittest.main()
