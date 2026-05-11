import unittest

from terminal.renderer import sanitize_render_plan


class TerminalRendererGuardTests(unittest.TestCase):
    def test_intraday_gap_suppresses_actionable_summary_strip(self):
        answer = (
            "SQLite intraday data for NIFTY 50 is currently unavailable, "
            "and we are in the pre-market session. Based on EOD fallback context..."
        )
        plan = {
            "show_summary_strip": True,
            "summary_line": "NIFTY 50 shows bearish momentum with oversold RSI.",
            "sentiment": "bearish",
            "key_metrics": [{"label": "RSI", "value": "30", "style": "red"}],
        }

        guarded = sanitize_render_plan(plan, answer, trace=[])

        self.assertFalse(guarded["show_summary_strip"])
        self.assertEqual(guarded["summary_line"], "")
        self.assertEqual(guarded["key_metrics"], [])


if __name__ == "__main__":
    unittest.main()
