import io
import unittest
from unittest.mock import patch

import nse_agent
from terminal import monitor
from terminal import tools


class NSEAgentMonitorCommandTests(unittest.TestCase):
    def _capture_stdout(self):
        captured = io.StringIO()
        original_stdout = nse_agent.sys.__stdout__
        nse_agent.sys.__stdout__ = captured
        return captured, original_stdout

    def _restore_stdout(self, original_stdout):
        nse_agent.sys.__stdout__ = original_stdout

    class _FakeConsole:
        def print(self, *args, **kwargs):
            pass

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

    def test_parse_monitor_start_without_strategy_defaults_to_all(self):
        parsed = nse_agent._parse_monitor_start_args(["/monitor", "start"])

        self.assertEqual(parsed["strategy"], "all")
        self.assertEqual(parsed["index"], "NIFTY 500")
        self.assertEqual(parsed["interval"], 15)
        self.assertEqual(parsed["direction"], "all")

    def test_handle_monitor_start_uses_parsed_arguments(self):
        class FakeMonitor:
            def __init__(self):
                self.calls = []

            def start(self, **kwargs):
                self.calls.append(kwargs)
                return "started"

        fake = FakeMonitor()
        captured, original_stdout = self._capture_stdout()
        try:
            with patch.object(nse_agent, "get_monitor", return_value=fake):
                nse_agent._handle_monitor_command(
                    ["/monitor", "start", "momentum", "NIFTY", "BANK", "10", "sell"]
                )
        finally:
            self._restore_stdout(original_stdout)

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

    def test_handle_monitor_strategy_shorthand_starts_monitor(self):
        class FakeMonitor:
            def __init__(self):
                self.calls = []

            def start(self, **kwargs):
                self.calls.append(kwargs)
                return "started"

        fake = FakeMonitor()
        captured, original_stdout = self._capture_stdout()
        try:
            with patch.object(nse_agent, "get_monitor", return_value=fake):
                nse_agent._handle_monitor_command(["/monitor", "vcp"])
        finally:
            self._restore_stdout(original_stdout)

        self.assertEqual(
            fake.calls,
            [
                {
                    "strategy": "vcp",
                    "index": "NIFTY 500",
                    "interval_min": 15,
                    "direction": "all",
                }
            ],
        )
        self.assertIn("Scanning: NIFTY 500", captured.getvalue())
        self.assertIn("Interval: 15m", captured.getvalue())

    def test_handle_monitor_strategy_shorthand_accepts_options(self):
        class FakeMonitor:
            def __init__(self):
                self.calls = []

            def start(self, **kwargs):
                self.calls.append(kwargs)
                return "started"

        fake = FakeMonitor()
        captured, original_stdout = self._capture_stdout()
        try:
            with patch.object(nse_agent, "get_monitor", return_value=fake):
                nse_agent._handle_monitor_command(["/monitor", "breakout", "NIFTY", "500", "15", "buy"])
        finally:
            self._restore_stdout(original_stdout)

        self.assertEqual(
            fake.calls,
            [
                {
                    "strategy": "breakout",
                    "index": "NIFTY 500",
                    "interval_min": 15,
                    "direction": "buy",
                }
            ],
        )
        self.assertIn("Direction: buy", captured.getvalue())

    def test_handle_monitor_all_shorthand_accepts_interval_and_direction(self):
        class FakeMonitor:
            def __init__(self):
                self.calls = []

            def start(self, **kwargs):
                self.calls.append(kwargs)
                return "started"

        fake = FakeMonitor()
        captured, original_stdout = self._capture_stdout()
        try:
            with patch.object(nse_agent, "get_monitor", return_value=fake):
                nse_agent._handle_monitor_command(["/monitor", "all", "5", "sell"])
        finally:
            self._restore_stdout(original_stdout)

        self.assertEqual(
            fake.calls,
            [
                {
                    "strategy": "all",
                    "index": "NIFTY 500",
                    "interval_min": 5,
                    "direction": "sell",
                }
            ],
        )
        self.assertIn("Interval: 5m", captured.getvalue())
        self.assertIn("Direction: sell", captured.getvalue())

    def test_handle_monitor_start_default_starts_all_monitor(self):
        class FakeMonitor:
            def __init__(self):
                self.calls = []

            def start(self, **kwargs):
                self.calls.append(kwargs)
                return "started"

        fake = FakeMonitor()
        captured, original_stdout = self._capture_stdout()
        try:
            with patch.object(nse_agent, "get_monitor", return_value=fake):
                nse_agent._handle_monitor_command(["/monitor", "start"])
        finally:
            self._restore_stdout(original_stdout)

        self.assertEqual(
            fake.calls,
            [
                {
                    "strategy": "all",
                    "index": "NIFTY 500",
                    "interval_min": 15,
                    "direction": "all",
                }
            ],
        )
        self.assertIn("Scanning: NIFTY 500", captured.getvalue())

    def test_handle_monitor_unknown_strategy_does_not_print_scanning_line(self):
        class FakeMonitor:
            def __init__(self):
                self.calls = []

            def start(self, **kwargs):
                self.calls.append(kwargs)
                return "should not be called"

        fake = FakeMonitor()
        captured, original_stdout = self._capture_stdout()
        try:
            with patch.object(nse_agent, "get_monitor", return_value=fake):
                nse_agent._handle_monitor_command(["/monitor", "start", "unknown"])
        finally:
            self._restore_stdout(original_stdout)

        self.assertEqual(fake.calls, [])
        self.assertIn("Unknown strategy 'unknown'", captured.getvalue())
        self.assertNotIn("Scanning:", captured.getvalue())

    def test_handle_monitor_duplicate_start_does_not_print_scanning_line(self):
        class FakeMonitor:
            def start(self, **kwargs):
                return "⚠️  Monitor 'vcp' on NIFTY 500 is already running."

        captured, original_stdout = self._capture_stdout()
        try:
            with patch.object(nse_agent, "get_monitor", return_value=FakeMonitor()):
                nse_agent._handle_monitor_command(["/monitor", "vcp"])
        finally:
            self._restore_stdout(original_stdout)

        self.assertIn("already running", captured.getvalue())
        self.assertNotIn("Scanning:", captured.getvalue())

    def test_handle_monitor_stop_passes_strategy_and_index(self):
        class FakeMonitor:
            def __init__(self):
                self.calls = []

            def stop(self, strategy="all", index=None):
                self.calls.append((strategy, index))
                return "stopped"

        fake = FakeMonitor()
        class FakeConsole:
            def print(self, *args, **kwargs):
                pass

        with patch.object(nse_agent, "get_monitor", return_value=fake), patch.object(nse_agent, "_mcon", return_value=FakeConsole()):
            nse_agent._handle_monitor_command(["/monitor", "stop", "breakout", "NIFTY", "50"])

        self.assertEqual(fake.calls, [("breakout", "NIFTY 50")])

    def test_handle_monitor_status_delegates_to_status_renderer(self):
        with patch.object(nse_agent, "get_monitor"), patch.object(nse_agent, "_print_monitor_status") as status:
            nse_agent._handle_monitor_command(["/monitor", "status"])

        status.assert_called_once_with()

    def test_handle_bare_monitor_shows_results_view(self):
        with patch.object(nse_agent, "get_monitor"), patch.object(nse_agent, "_print_monitor_results") as results:
            nse_agent._handle_monitor_command(["/monitor"])

        results.assert_called_once_with()

    def test_print_monitor_results_renders_queued_events(self):
        class FakeMonitor:
            def status(self):
                return []

            def drain_alerts(self):
                return [{"type": "heartbeat", "strategy": "vcp", "index": "NIFTY 500", "as_of": "10:55", "run_n": 1}]

            def recent_events(self):
                return []

        rendered = []
        with patch.object(nse_agent, "get_monitor", return_value=FakeMonitor()), patch.object(
            nse_agent, "_render_monitor_event_console", side_effect=lambda ev: rendered.append(ev)
        ), patch.object(nse_agent, "_mcon", return_value=self._FakeConsole()):
            nse_agent._print_monitor_results()

        self.assertEqual(len(rendered), 1)
        self.assertEqual(rendered[0]["type"], "heartbeat")

    def test_print_monitor_results_falls_back_to_recent_events(self):
        class FakeMonitor:
            def status(self):
                return []

            def drain_alerts(self):
                return []

            def recent_events(self):
                return [{"type": "error", "strategy": "vcp", "message": "scan failed"}]

        rendered = []
        with patch.object(nse_agent, "get_monitor", return_value=FakeMonitor()), patch.object(
            nse_agent, "_render_monitor_event_console", side_effect=lambda ev: rendered.append(ev)
        ), patch.object(nse_agent, "_mcon", return_value=self._FakeConsole()):
            nse_agent._print_monitor_results()

        self.assertEqual(len(rendered), 1)
        self.assertEqual(rendered[0]["type"], "error")


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


class MarketDashboardLiveTests(unittest.TestCase):
    def _sample_snapshot(self):
        return {
            "focus": "banks",
            "fetched_at": "2026-05-12 11:30:00",
            "get_live_market_overview": {
                "source": "NSE live API",
                "as_of": "2026-05-12 11:30:00",
                "indices": {
                    "NIFTY 50": {"last": 23600.0, "pct_change": -0.5},
                    "NIFTY BANK": {"last": 54000.0, "pct_change": -0.2},
                    "INDIA VIX": {"last": 19.0, "pct_change": 4.0},
                    "NIFTY METAL": {"last": 13000.0, "pct_change": 1.2},
                    "NIFTY IT": {"last": 28000.0, "pct_change": -2.0},
                },
                "adv_dec": {"advances": 100, "declines": 400},
            },
            "get_market_breadth": {
                "advances": 300,
                "declines": 700,
                "ad_ratio": 0.43,
                "avg_rs_pct": -1.2,
                "stage_distribution": {"STAGE_1": 10, "STAGE_2": 20, "STAGE_3": 30, "STAGE_4": 40},
            },
            "get_top_gainers_losers": {
                "gainers": [{"symbol": "AAA", "pct_change": 5.0}],
                "losers": [{"symbol": "ZZZ", "pct_change": -4.0}],
            },
            "get_fii_dii_activity": {"data": [{"category": "FII", "net_crore": -1000.0}]},
            "get_global_market_assessment": {"risk_regime": "RISK_OFF"},
            "search_latest_catalysts": {"results": [{"title": "Market headline"}]},
        }

    def test_market_dashboard_renderable_is_compact_and_excludes_vix_from_leaders(self):
        from rich.console import Console as RichConsole

        capture = io.StringIO()
        con = RichConsole(file=capture, force_terminal=False, width=100, height=28)
        con.print(nse_agent._market_dashboard_renderable(self._sample_snapshot(), width=100, height=28))
        output = capture.getvalue()

        self.assertIn("Market Dashboard", output)
        self.assertIn("INDIA VIX", output)
        self.assertIn("NIFTY METAL", output)
        self.assertIn("NIFTY IT", output)
        self.assertIn("defensive / risk-off", output)
        self.assertEqual(output.count("INDIA VIX"), 1)

    def test_live_dashboard_loop_supports_single_cycle_for_tests(self):
        class FakeLive:
            def __init__(self, renderable, **kwargs):
                self.updates = []

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def update(self, renderable, refresh=False):
                self.updates.append((renderable, refresh))

        with patch.object(nse_agent, "_fetch_market_dashboard_snapshot", return_value=self._sample_snapshot()) as fetch, patch.object(
            nse_agent, "Live", FakeLive
        ):
            nse_agent._run_market_dashboard_live("banks", refresh_secs=0, max_cycles=1)

        fetch.assert_called_once_with("banks")

    def test_fetch_market_dashboard_snapshot_calls_expected_tools(self):
        calls = []

        def fake_call_tool(name, args):
            calls.append((name, args))
            return {"ok": True}

        with patch("terminal.tools.call_tool", side_effect=fake_call_tool):
            snapshot = nse_agent._fetch_market_dashboard_snapshot("banks")

        self.assertEqual(snapshot["focus"], "banks")
        self.assertIn("fetched_at", snapshot)
        self.assertEqual(
            [name for name, _ in calls],
            [
                "get_live_market_overview",
                "get_market_breadth",
                "get_top_gainers_losers",
                "get_fii_dii_activity",
                "get_global_market_assessment",
                "search_latest_catalysts",
            ],
        )


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

    def test_drain_alerts_records_recent_events_for_manual_monitor_view(self):
        manager = monitor.MonitorManager()
        manager.queue.put({"type": "heartbeat", "strategy": "breakout"})
        manager.queue.put({"type": "error", "strategy": "vcp"})

        manager.drain_alerts(max_items=1)
        manager.drain_alerts(max_items=1)

        recent = manager.recent_events()
        self.assertEqual([event["type"] for event in recent], ["heartbeat", "error"])
        self.assertEqual([event["strategy"] for event in manager.recent_events(max_items=1)], ["vcp"])

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
