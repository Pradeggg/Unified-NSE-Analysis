import unittest
from datetime import datetime
from unittest.mock import patch
import shutil

import nse_agent


class AgentAddaClockTests(unittest.TestCase):
    def test_session_clock_label_includes_full_date_time_and_timezone(self):
        label = nse_agent._session_clock_label(datetime(2026, 5, 11, 9, 7, 5))

        self.assertEqual(label, "Mon, 11 May 2026 09:07:05 IST")

    def test_prompt_includes_latest_date_and_time_label(self):
        prompt = nse_agent._build_prompt().value

        self.assertRegex(prompt, r"\d{2} [A-Z][a-z]{2} \d{4} \d{2}:\d{2}:\d{2} IST")

    def test_bottom_toolbar_includes_live_clock_context(self):
        with patch.object(nse_agent, "_get_cached_market_toolbar_data", return_value=None):
            toolbar = nse_agent._bottom_toolbar_text(lambda: datetime(2026, 5, 11, 9, 7, 5))

        self.assertIn("Mon, 11 May 2026 09:07:05 IST", toolbar)
        self.assertIn("mode:", toolbar)
        self.assertIn("Agent Adda", toolbar)
        self.assertIn("NSE:", toolbar)

    def test_bottom_toolbar_renders_cached_live_ticker(self):
        cached = {
            "indices": [
                {"name": "NIFTY 50", "last": 23884.15, "pct_change": -1.21},
                {"name": "NIFTY BANK", "last": 54445.5, "pct_change": -1.56},
                {"name": "MIDCPNIFTY", "last": 14348.65, "pct_change": -0.99},
            ],
            "adv_dec": {"advances": 100, "declines": 399},
            "source": "NSE live API",
        }

        with patch.object(nse_agent, "_get_cached_market_toolbar_data", return_value=cached), patch(
            "shutil.get_terminal_size", return_value=shutil.os.terminal_size((180, 24))
        ):
            toolbar = nse_agent._bottom_toolbar_text(lambda: datetime(2026, 5, 11, 10, 16, 40))

        self.assertIn("NIFTY 50 23,884.15 -1.21%", toolbar)
        self.assertIn("BANK 54,445.50 -1.56%", toolbar)
        self.assertIn("MIDCP 14,348.65 -0.99%", toolbar)
        self.assertIn("Breadth 100A/399D", toolbar)
        self.assertIn("NSE: OPEN until 15:30", toolbar)
        self.assertIn("10:16:40 IST", toolbar)
        self.assertIn("AUTO", toolbar)

    def test_bottom_toolbar_ticker_compacts_to_terminal_width(self):
        cached = {
            "indices": [
                {"name": "NIFTY 50", "last": 23884.15, "pct_change": -1.21},
                {"name": "NIFTY BANK", "last": 54445.5, "pct_change": -1.56},
                {"name": "MIDCPNIFTY", "last": 14348.65, "pct_change": -0.99},
            ],
            "adv_dec": {"advances": 100, "declines": 399},
            "source": "NSE live API",
        }

        for width in (80, 100, 120):
            with self.subTest(width=width), patch.object(
                nse_agent, "_get_cached_market_toolbar_data", return_value=cached
            ), patch("shutil.get_terminal_size", return_value=shutil.os.terminal_size((width, 24))):
                toolbar = nse_agent._bottom_toolbar_text(lambda: datetime(2026, 5, 11, 10, 16, 40))

            self.assertLessEqual(len(toolbar), width)
            self.assertIn("N50", toolbar)
            self.assertIn("AUTO", toolbar)

    def test_bottom_toolbar_uses_cache_only_and_does_not_fetch_live_data(self):
        nse_agent._market_toolbar_cache.update({"ts": 0.0, "data": None})

        with patch.object(nse_agent, "_get_market_toolbar_data") as fetch:
            toolbar = nse_agent._bottom_toolbar_text(lambda: datetime(2026, 5, 11, 9, 7, 5))

        fetch.assert_not_called()
        self.assertIn("Mon, 11 May 2026 09:07:05 IST", toolbar)


if __name__ == "__main__":
    unittest.main()
