import unittest

from terminal.renderer import sanitize_render_plan


class TerminalRendererGuardTests(unittest.TestCase):
    def test_intraday_gap_suppresses_actionable_summary_strip(self):
        answer = (
            "PostgreSQL intraday data for NIFTY 50 is currently unavailable, "
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

    def test_placeholder_metrics_are_removed_from_summary_strip(self):
        plan = {
            "show_summary_strip": True,
            "summary_line": "United Spirits audited FY26 results are available.",
            "sentiment": "neutral",
            "key_metrics": [
                {"label": "Quarterly Revenue", "value": "₹X", "style": "bold"},
                {"label": "Yearly Revenue", "value": "₹Y", "style": "bold"},
                {"label": "Net Profit", "value": "₹Z", "style": "bold"},
                {"label": "EPS", "value": "₹A", "style": "bold"},
                {"label": "FY26 Revenue", "value": "₹27,781 cr", "style": "green"},
            ],
        }

        guarded = sanitize_render_plan(plan, "FY26 revenue was ₹27,781 crores.", trace=[])

        self.assertTrue(guarded["show_summary_strip"])
        self.assertEqual(
            guarded["key_metrics"],
            [{"label": "FY26 Revenue", "value": "₹27,781 cr", "style": "green"}],
        )

    def test_missing_value_metrics_are_removed_from_summary_strip(self):
        plan = {
            "show_summary_strip": True,
            "summary_line": "NIFTY MIDCAP SELECT movers are scoped correctly.",
            "sentiment": "neutral",
            "key_metrics": [
                {"label": "NIFTY MID SELECT", "value": "14,503", "style": "bold"},
                {"label": "Top Gainer", "value": "COFORGE", "style": "green"},
                {"label": "Total Advancers", "value": "None", "style": "yellow"},
                {
                    "label": "Market Breadth",
                    "value": "Advancers: None, Decliners: None",
                    "style": "yellow",
                },
            ],
        }

        guarded = sanitize_render_plan(plan, "Top gainers: COFORGE +4.44%", trace=[])

        self.assertTrue(guarded["show_summary_strip"])
        self.assertEqual(
            guarded["key_metrics"],
            [
                {"label": "NIFTY MID SELECT", "value": "14,503", "style": "bold"},
                {"label": "Top Gainer", "value": "COFORGE", "style": "green"},
            ],
        )

    def test_placeholder_only_summary_strip_is_hidden(self):
        plan = {
            "show_summary_strip": True,
            "summary_line": "Quarterly Revenue: ₹X · Yearly Revenue: ₹Y",
            "key_metrics": [{"label": "EPS", "value": "₹A", "style": "bold"}],
        }

        guarded = sanitize_render_plan(plan, "Document analysis completed.", trace=[])

        self.assertFalse(guarded["show_summary_strip"])
        self.assertEqual(guarded["summary_line"], "")
        self.assertEqual(guarded["key_metrics"], [])

    def test_index_summary_strip_with_xx_placeholders_is_hidden(self):
        plan = {
            "show_summary_strip": True,
            "summary_line": (
                "NIFTY MIDCAP SELECT shows stable breadth with key movers "
                "COFORGE, PERSISTENT, DIXON."
            ),
            "key_metrics": [
                {"label": "NIFTY MIDCAP SELECT Price", "value": "X,XXX", "style": "bold"},
                {"label": "Advancers", "value": "XX", "style": "green"},
                {"label": "Decliners", "value": "XX", "style": "red"},
                {"label": "Market Breadth", "value": "XX:XX", "style": "yellow"},
            ],
        }

        guarded = sanitize_render_plan(plan, "Advances: 15  Declines: 8", trace=[])

        self.assertFalse(guarded["show_summary_strip"])
        self.assertEqual(guarded["summary_line"], "")
        self.assertEqual(guarded["key_metrics"], [])


if __name__ == "__main__":
    unittest.main()
