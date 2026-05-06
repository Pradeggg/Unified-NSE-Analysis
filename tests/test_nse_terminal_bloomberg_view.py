import sys
import unittest
from io import StringIO
from pathlib import Path

from rich.console import Console

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import nse_terminal
from nse_terminal import _adaptive_signal_rows, _parse_input, build_full_layout


class NSETerminalBloombergViewTests(unittest.TestCase):
    def test_free_text_and_slash_input_do_not_route_to_chat(self):
        self.assertEqual(_parse_input("/breakout stocks"), ("ignore", ""))
        self.assertEqual(_parse_input("breakout stocks in last hour"), ("ignore", ""))

    def test_layout_renders_pulse_as_top_band_without_chat_or_right_sidebar(self):
        layout = build_full_layout(
            indices={},
            signals={},
            last_update="test",
            hist_rows=0,
            top_n=15,
        )

        buf = StringIO()
        console = Console(width=204, height=53, file=buf, color_system=None)
        console.print(layout)
        rendered = buf.getvalue()

        self.assertNotIn("Agent Adda", rendered)
        self.assertNotIn("Query Input", rendered)
        self.assertIn("PULSE", rendered)
        self.assertLess(rendered.index("PULSE"), rendered.index("INDICES"))
        self.assertNotIn("/ query", rendered)
        self.assertNotIn("[/] to query", rendered)

    def test_layout_uses_full_terminal_width_for_signal_panels(self):
        layout = build_full_layout(
            indices={},
            signals={"stage2_leaders": [{"symbol": "TEST", "price": 100, "change_1m_pct": 5, "rs_pct": 10, "rsi": 65, "trading_signal": "HOLD"}]},
            last_update="test",
            hist_rows=1,
            top_n=15,
        )
        buf = StringIO()
        console = Console(width=204, height=53, file=buf, color_system=None)

        console.print(layout)
        rendered = buf.getvalue()

        self.assertIn("STAGE 2 LEADERS", rendered)
        self.assertIn("PULSE", rendered)
        self.assertNotIn("/ query", rendered)
        self.assertNotIn("[/] to query", rendered)
        self.assertIn("Last update", rendered)
        self.assertGreater(max(len(line.rstrip()) for line in rendered.splitlines()), 180)

    def test_adaptive_rows_fit_with_top_pulse_band(self):
        compact_rows = _adaptive_signal_rows(15, terminal_height=53)
        tall_rows = _adaptive_signal_rows(15, terminal_height=68)

        self.assertLessEqual(compact_rows, 5)
        self.assertGreater(tall_rows, compact_rows)

    def test_refresh_data_can_run_silently_for_live_screen(self):
        messages = []
        original_log = nse_terminal.console.log
        original_market_is_open = nse_terminal._market_is_open
        original_fetch_all_indices = nse_terminal.fetch_all_indices
        original_load_eod_indices = nse_terminal.load_eod_indices
        original_load_price_history = nse_terminal.load_price_history
        original_load_eod_stock_prices = nse_terminal.load_eod_stock_prices
        original_run_screener = nse_terminal.run_screener
        original_load_rs_from_db = nse_terminal.load_rs_from_db
        original_load_nifty_trend = nse_terminal.load_nifty_trend
        original_compute_sector_breadth = nse_terminal.compute_sector_breadth

        try:
            nse_terminal.console.log = lambda message: messages.append(message)
            nse_terminal._market_is_open = lambda: False
            nse_terminal.fetch_all_indices = lambda: {}
            nse_terminal.load_eod_indices = lambda: {}
            nse_terminal.load_price_history = lambda days=400: __import__("pandas").DataFrame()
            nse_terminal.load_eod_stock_prices = lambda: {}
            nse_terminal.run_screener = lambda hist, live_prices, top_n: {}
            nse_terminal.load_rs_from_db = lambda: {}
            nse_terminal.load_nifty_trend = lambda days=10: []
            nse_terminal.compute_sector_breadth = lambda hist: {}

            nse_terminal.refresh_data(15, log=False)

            self.assertEqual(messages, [])
        finally:
            nse_terminal.console.log = original_log
            nse_terminal._market_is_open = original_market_is_open
            nse_terminal.fetch_all_indices = original_fetch_all_indices
            nse_terminal.load_eod_indices = original_load_eod_indices
            nse_terminal.load_price_history = original_load_price_history
            nse_terminal.load_eod_stock_prices = original_load_eod_stock_prices
            nse_terminal.run_screener = original_run_screener
            nse_terminal.load_rs_from_db = original_load_rs_from_db
            nse_terminal.load_nifty_trend = original_load_nifty_trend
            nse_terminal.compute_sector_breadth = original_compute_sector_breadth


if __name__ == "__main__":
    unittest.main()
