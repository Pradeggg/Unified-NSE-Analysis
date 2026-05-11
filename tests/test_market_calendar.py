import unittest
from datetime import datetime

from terminal.market_calendar import market_session_status, market_context_for_agent


class MarketCalendarTests(unittest.TestCase):
    def test_regular_session_is_open_on_trading_day(self):
        status = market_session_status(datetime(2026, 5, 11, 10, 30, 0))

        self.assertTrue(status.is_trading_day)
        self.assertTrue(status.is_open)
        self.assertEqual(status.phase, "open")
        self.assertIn("OPEN", status.status_label)
        self.assertIn("15:30", status.compact_label)

    def test_before_open_is_trading_day_but_market_closed(self):
        status = market_session_status(datetime(2026, 5, 11, 8, 45, 0))

        self.assertTrue(status.is_trading_day)
        self.assertFalse(status.is_open)
        self.assertEqual(status.phase, "pre_market")
        self.assertIn("Next open: Mon, 11 May 2026 09:15:00 IST", status.status_label)

    def test_weekend_is_not_trading_day(self):
        status = market_session_status(datetime(2026, 5, 16, 10, 30, 0))

        self.assertFalse(status.is_trading_day)
        self.assertFalse(status.is_open)
        self.assertEqual(status.phase, "closed_weekend")
        self.assertIn("weekend", status.reason.lower())

    def test_nse_2026_declared_holiday_is_closed(self):
        status = market_session_status(datetime(2026, 5, 28, 10, 30, 0))

        self.assertFalse(status.is_trading_day)
        self.assertFalse(status.is_open)
        self.assertEqual(status.phase, "closed_holiday")
        self.assertIn("Bakri Id", status.reason)

    def test_agent_context_tells_llm_not_to_imply_live_market_when_closed(self):
        context = market_context_for_agent(datetime(2026, 5, 11, 8, 45, 0))

        self.assertIn("NSE market clock:", context)
        self.assertIn("CLOSED", context)
        self.assertIn("do not imply live market movement", context)


if __name__ == "__main__":
    unittest.main()
