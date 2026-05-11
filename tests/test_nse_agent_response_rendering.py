import unittest
from unittest.mock import patch

from rich.console import Console

import nse_agent


class AgentResponseRenderingTests(unittest.TestCase):
    def test_plain_market_brief_preserves_section_line_breaks(self):
        answer = "\n".join(
            [
                "━━━ MAYURUNIQ (MAYURUNIQ) — Market Brief ━━━",
                "Data: EOD snapshot 2026-05-08",
                "",
                "▶ SNAPSHOT",
                "  Price:  ₹629.40  (+5.33%)",
                "  Stage:  STAGE_1  (score: 0.0)",
                "  Signal: HOLD",
                "  RS:     +6%",
                "  MCap:   SMALL_CAP",
                "",
                "▶ TECHNICAL SETUP",
                "  Derived score: 85 (derived from EOD MA alignment, RSI, MACD, Supertrend, and ADX)",
                "  RSI:        70.6",
                "  ADX:        32.2  (>25 = trending)",
                "  MAs:        ▲ SMA20 | ▲ SMA50 | ▲ SMA200",
                "",
                "▶ SOURCE TRAIL",
                "  resolve_symbol: ok",
                "  get_symbol_snapshot: ok",
                "",
                "━━━ Not investment advice. For research and learning only. ━━━",
                "",
                "_Mode: Historical | Sources: EOD CSV + DB snapshot | Market: NSE: OPEN until 15:30 | Clock: Mon, 11 May 2026 12:03:45 IST_",
            ]
        )
        test_console = Console(record=True, width=120, color_system=None)
        original_console = nse_agent.console

        try:
            nse_agent.console = test_console
            with patch(
                "nse_agent.pre_render_plan",
                return_value={
                    "render_mode": "narrative_first",
                    "show_summary_strip": False,
                    "bold_symbols": [],
                    "render_tools": [],
                    "sentiment": "neutral",
                    "alert_level": "none",
                },
            ), patch("nse_agent.apply_render_plan", return_value="white"):
                nse_agent._print_response({"answer": answer, "backend": "Test"})
        finally:
            nse_agent.console = original_console

        rendered = test_console.export_text()
        self.assertIn("▶ SNAPSHOT\n  Price:", rendered)
        self.assertIn("▶ TECHNICAL SETUP\n  Derived score:", rendered)
        self.assertIn("▶ SOURCE TRAIL\n  resolve_symbol:", rendered)
        self.assertIn("Mode: Historical | Sources:", rendered)
        self.assertNotIn("_Mode:", rendered)
        self.assertNotIn("▶ SNAPSHOT Price:", rendered)
        self.assertNotIn("▶ TECHNICAL SETUP Derived score:", rendered)


if __name__ == "__main__":
    unittest.main()
