import io
import unittest
from unittest.mock import patch

import nse_agent
from terminal import monitor
from terminal import tools


class NSEAgentMonitorCommandTests(unittest.TestCase):
    def test_parse_monitor_start_keeps_nifty_50_as_index_and_extracts_interval(self):
        parsed = nse_agent._parse_monitor_start_args(
            ["/monitor", "start", "breakout", "NIFTY", "50", "15", "buy"]
        )

        self.assertEqual(parsed["strategy"], "breakout")
        self.assertEqual(parsed["index"], "NIFTY 50")
        self.assertEqual(parsed["interval"], 15)
        self.assertEqual(parsed["direction"], "buy")

    def test_parse_monitor_start_defaults_all_strategy_to_nifty_500(self):
        parsed = nse_agent._parse_monitor_start_args(["/monitor", "start", "all", "15", "sell"])

        self.assertEqual(parsed["strategy"], "all")
        self.assertEqual(parsed["index"], "NIFTY 500")
        self.assertEqual(parsed["interval"], 15)
        self.assertEqual(parsed["direction"], "sell")

    def test_handle_monitor_start_uses_parsed_arguments(self):
        class FakeMonitor:
            def __init__(self):
                self.calls = []

            def start(self, **kwargs):
                self.calls.append(kwargs)
                return "started"

        fake = FakeMonitor()
        captured = io.StringIO()
        original_stdout = nse_agent.sys.__stdout__
        try:
            nse_agent.sys.__stdout__ = captured
            with patch.object(nse_agent, "get_monitor", return_value=fake):
                nse_agent._handle_monitor_command(
                    ["/monitor", "start", "momentum", "NIFTY", "BANK", "10", "sell"]
                )
        finally:
            nse_agent.sys.__stdout__ = original_stdout

        self.assertEqual(
            fake.calls,
            [
                {
                    "strategy": "momentum",
                    "index": "NIFTY BANK",
                    "interval_min": 10,
                    "direction": "sell",
                }
            ],
        )
        self.assertIn("Scanning: NIFTY BANK", captured.getvalue())
        self.assertIn("Interval: 10m", captured.getvalue())
        self.assertIn("Direction: sell", captured.getvalue())


class NSEAgentScanRewriteTests(unittest.TestCase):
    def test_rewrite_default_scan_to_nifty_50_all_strategy_query(self):
        rewritten, status = nse_agent._rewrite_scan_command("/scan")

        self.assertEqual(
            rewritten,
            "Scan NIFTY 50 for intraday research setups using all strategies on 15m charts",
        )
        self.assertEqual(status, "Intraday scan: NIFTY 50")

    def test_rewrite_index_scan_preserves_multi_word_index(self):
        rewritten, status = nse_agent._rewrite_scan_command("/scan NIFTY BANK")

        self.assertEqual(
            rewritten,
            "Scan NIFTY BANK for intraday research setups using all strategies on 15m charts",
        )
        self.assertEqual(status, "Intraday scan: NIFTY BANK")

    def test_rewrite_scan_aliases_to_intraday_screener_types(self):
        cases = {
            "orb": ("opening_range_breakout", "Opening Range Breakout"),
            "gap": ("gap_and_go", "Gap & Go"),
            "macd": ("macd_crossover", "MACD Crossover"),
            "rsi": ("rsi_divergence", "RSI Divergence"),
            "bb": ("bb_squeeze", "Bollinger Squeeze"),
            "vwap": ("vwap_reclaim", "VWAP Reclaim"),
            "vcp": ("vcp", "VCP"),
            "momentum": ("momentum", "Momentum"),
        }

        for alias, (screen_type, label) in cases.items():
            with self.subTest(alias=alias):
                rewritten, status = nse_agent._rewrite_scan_command(f"/scan {alias}")
                self.assertEqual(
                    rewritten,
                    f"Run intraday screener {screen_type} on NIFTY 500 on 15m charts",
                )
                self.assertEqual(status, f"Intraday screener: {label}")


class FakeWorker:
    instances = []

    def __init__(
        self,
        strategy,
        alert_queue,
        index="NIFTY 500",
        interval_min=15,
        top_n=8,
        direction="all",
    ):
        self.strategy = strategy
        self.alert_queue = alert_queue
        self.index = index
        self.interval_min = interval_min
        self.top_n = top_n
        self.direction = direction
        self.last_run = None
        self.last_count = 0
        self.run_count = 0
        self.errors = 0
        self._running = False
        FakeWorker.instances.append(self)

    def start(self):
        self._running = True

    def stop(self):
        self._running = False

    @property
    def is_running(self):
        return self._running


class FakeDBPath:
    def __init__(self, exists: bool):
        self._exists = exists

    def exists(self):
        return self._exists


class MonitorManagerTests(unittest.TestCase):
    def setUp(self):
        FakeWorker.instances = []

    def test_start_rejects_unknown_strategy_without_worker(self):
        manager = monitor.MonitorManager()

        message = manager.start("unknown")

        self.assertIn("Unknown strategy", message)
        self.assertEqual(FakeWorker.instances, [])
        self.assertEqual(manager.status(), [])

    def test_start_status_duplicate_and_stop_specific_monitor(self):
        manager = monitor.MonitorManager()

        with patch.object(monitor, "AlertWorker", FakeWorker):
            message = manager.start(
                strategy="breakout",
                index="NIFTY 50",
                interval_min=5,
                direction="buy",
            )
            duplicate = manager.start(
                strategy="breakout",
                index="NIFTY 50",
                interval_min=5,
                direction="buy",
            )

        self.assertIn("started", message)
        self.assertIn("already running", duplicate)
        self.assertEqual(len(FakeWorker.instances), 1)
        self.assertTrue(manager.any_active())

        status = manager.status()
        self.assertEqual(len(status), 1)
        self.assertEqual(status[0]["strategy"], "breakout")
        self.assertEqual(status[0]["index"], "NIFTY 50")
        self.assertEqual(status[0]["interval"], "5m")

        stop_message = manager.stop("breakout", "NIFTY 50")

        self.assertIn("Stopped", stop_message)
        self.assertFalse(manager.any_active())
        self.assertEqual(manager.status(), [])

    def test_stop_all_removes_every_active_monitor(self):
        manager = monitor.MonitorManager()

        with patch.object(monitor, "AlertWorker", FakeWorker):
            manager.start("breakout", index="NIFTY 50")
            manager.start("momentum", index="NIFTY BANK")

        self.assertEqual(len(manager.status()), 2)

        stop_message = manager.stop("all")

        self.assertIn("breakout:NIFTY 50", stop_message)
        self.assertIn("momentum:NIFTY BANK", stop_message)
        self.assertEqual(manager.status(), [])

    def test_drain_alerts_respects_max_items_and_preserves_remaining_queue(self):
        manager = monitor.MonitorManager()
        manager.queue.put({"type": "heartbeat", "strategy": "breakout"})
        manager.queue.put({"type": "alerts", "strategy": "momentum"})
        manager.queue.put({"type": "error", "strategy": "vcp"})

        events = manager.drain_alerts(max_items=2)
        remaining = manager.drain_alerts()

        self.assertEqual([event["type"] for event in events], ["heartbeat", "alerts"])
        self.assertEqual([event["type"] for event in remaining], ["error"])

    def test_sig_to_alert_maps_trading_fields_and_confidence(self):
        alert = monitor._sig_to_alert(
            {
                "symbol": "RELIANCE",
                "strategy": "MACD",
                "entry": 2875.5,
                "target": 2925.0,
                "stoploss": 2840.0,
                "risk_reward": 2.1,
            },
            strategy="momentum",
            direction="BUY",
            index="NIFTY 50",
        )

        self.assertEqual(alert.symbol, "RELIANCE")
        self.assertEqual(alert.direction, "BUY")
        self.assertEqual(alert.signal, "MACD")
        self.assertEqual(alert.confidence, "high")
        self.assertEqual(alert.confidence_bar, "▪▪▪")
        self.assertEqual(alert.emoji, "🟢")


class IntradayScreenerToolTests(unittest.TestCase):
    def test_run_intraday_screener_rejects_unknown_screen_type(self):
        result = tools.run_intraday_screener("not_a_screen")

        self.assertIn("error", result)
        self.assertIn("Unknown intraday screener", result["error"])
        self.assertIn("momentum", result["supported"])

    def test_run_intraday_screener_live_fallback_uses_screen_strategy_mapping(self):
        scan_result = {
            "index": "NIFTY 500",
            "top_buy": [{"symbol": "AAA"}],
            "top_sell": [],
        }

        with patch.object(tools, "DB_PATH", FakeDBPath(False)), patch.object(
            tools, "scan_intraday_market", return_value=scan_result
        ) as scan:
            result = tools.run_intraday_screener(
                screen_type="macd_crossover",
                timeframe="30m",
                top_n=3,
            )

        scan.assert_called_once_with(
            index="NIFTY 500",
            interval="30m",
            strategies=["macd"],
            direction_filter="buy",
            min_rr=1.3,
            top_n=3,
        )
        self.assertEqual(result["screen_type"], "macd_crossover")
        self.assertEqual(result["data_mode"], "live-yfinance-fallback")
        self.assertEqual(
            result["source_priority"],
            [
                "PostgreSQL intraday.ohlcv_bars",
                "SQLite intraday_ohlcv",
                "NSE website live constituents",
                "yfinance candles",
            ],
        )
        self.assertIn("MACD Crossover", result["description"])
        self.assertIn("NSE website constituents first", result["fallback_note"])

    def test_run_intraday_screener_live_fallback_normalizes_bad_timeframe(self):
        with patch.object(tools, "DB_PATH", FakeDBPath(False)), patch.object(
            tools, "scan_intraday_market", return_value={}
        ) as scan:
            tools.run_intraday_screener(screen_type="vwap_reclaim", timeframe="2m")

        self.assertEqual(scan.call_args.kwargs["interval"], "15m")
        self.assertEqual(scan.call_args.kwargs["strategies"], ["ema", "rsi"])

    def test_run_intraday_screener_sqlite_path_filters_and_sorts_results(self):
        setups = {
            "AAA": {
                "symbol": "AAA",
                "setup_label": "LONG_SETUP",
                "setup_side": "long",
                "score": 72,
                "latest_close": 101.5,
                "indicators": {"rsi": 61, "macd_hist": 1.2, "supertrend_dir": 1},
                "levels": {"supports": [99.0], "resistances": [106.0]},
                "invalidation_level": 98.5,
                "technical_target_zones": [{"target": 106.0}],
                "latest_timestamp": "2026-05-08 10:30:00",
            },
            "BBB": {
                "symbol": "BBB",
                "setup_label": "WATCH",
                "setup_side": "long",
                "score": 65,
                "latest_close": 205.0,
                "indicators": {"rsi": 54, "macd_hist": 0.4, "supertrend_dir": 1},
                "levels": {"supports": [201.0], "resistances": [212.0]},
                "invalidation_level": 200.0,
                "technical_target_zones": [{"target": 212.0}],
                "latest_timestamp": "2026-05-08 10:30:00",
            },
            "CCC": {
                "symbol": "CCC",
                "setup_label": "AVOID",
                "setup_side": "none",
                "score": 80,
                "latest_close": 50.0,
                "indicators": {"rsi": 42, "macd_hist": -0.2, "supertrend_dir": -1},
                "levels": {"supports": [48.0], "resistances": [53.0]},
                "invalidation_level": 48.0,
                "technical_target_zones": [{"target": 53.0}],
                "latest_timestamp": "2026-05-08 10:30:00",
            },
        }

        with patch.object(tools, "DB_PATH", FakeDBPath(True)), patch.object(
            tools, "_sqlite_table_exists", return_value=True
        ), patch.object(tools, "explain_intraday_setup", side_effect=lambda sym, timeframe="15m": setups[sym]):
            result = tools.run_intraday_screener(
                screen_type="breakouts",
                timeframe="15m",
                min_score=60,
                top_n=5,
                symbols=["BBB", "AAA", "CCC"],
            )

        self.assertEqual(result["data_mode"], "intraday")
        self.assertEqual(result["source"], "SQLite intraday_ohlcv")
        self.assertEqual(result["scanned"], 3)
        self.assertEqual(result["count"], 2)
        self.assertEqual([row["symbol"] for row in result["results"]], ["AAA", "BBB"])
        self.assertEqual(result["results"][0]["support"], 99.0)
        self.assertEqual(result["results"][0]["resistance"], 106.0)
        self.assertIn("Not investment advice", result["disclaimer"])


if __name__ == "__main__":
    unittest.main()
