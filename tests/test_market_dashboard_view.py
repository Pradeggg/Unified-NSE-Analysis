import unittest

from rich.console import Console

import nse_agent


def _dashboard_snapshot():
    return {
        "focus": "whole market",
        "fetched_at": "2026-05-15 13:20:00",
        "get_live_market_overview": {
            "indices": {
                "NIFTY 50": {"last": 23600.0, "pct_change": 0.42},
                "NIFTY BANK": {"last": 54100.0, "pct_change": 0.12},
                "NIFTY IT": {"last": 28200.0, "pct_change": -0.55},
                "NIFTY METAL": {"last": 13000.0, "pct_change": 1.1},
                "INDIA VIX": {"last": 15.7, "pct_change": -1.2},
            },
            "adv_dec": {"advances": 320, "declines": 180},
        },
        "get_market_breadth": {
            "advances": 620,
            "declines": 380,
            "ad_ratio": 1.63,
            "avg_rs_pct": 1.5,
            "stage_distribution": {"STAGE_1": 100, "STAGE_2": 420, "STAGE_3": 200, "STAGE_4": 280},
        },
        "get_top_gainers_losers": {
            "gainers": [{"symbol": "AAA", "pct_change": 6.1}],
            "losers": [{"symbol": "ZZZ", "pct_change": -5.4}],
        },
        "get_fii_dii_activity": {"data": [{"category": "FII", "net_crore": 850.0}]},
        "get_global_market_assessment": {"risk_regime": "risk-on"},
        "search_latest_catalysts": {"results": [{"title": "Market headline"}]},
        "get_options_chain": {
            "pcr": 1.28,
            "max_pain": 23500,
            "calls": [{"strike": 23800, "oi": 900000}, {"strike": 24000, "oi": 700000}],
            "puts": [{"strike": 23500, "oi": 1200000}, {"strike": 23400, "oi": 600000}],
        },
        "get_futures_analysis": {
            "futures": [
                {
                    "basis": 42.5,
                    "basis_pct": 0.18,
                    "cost_of_carry_annualised_pct": 8.4,
                }
            ],
            "rollover": {"rollover_pct": 62.0},
        },
        "run_screener_query": {"results": [{"symbol": "AAA", "rs_pct": 88.0}]},
    }


def _render_text(renderable) -> str:
    console = Console(width=160, height=44, record=True, force_terminal=False)
    console.print(renderable)
    return console.export_text()


class MarketDashboardViewTests(unittest.TestCase):
    def test_dashboard_fno_line_includes_options_bias_support_resistance_and_futures(self):
        line = nse_agent._dashboard_fno_line(_dashboard_snapshot())

        self.assertIn("Options Bias", line)
        self.assertIn("Support 23,500", line)
        self.assertIn("Resistance 23,800", line)
        self.assertIn("Futures", line)
        self.assertIn("Basis 42", line)
        self.assertIn("CoC 8.4%", line)

    def test_dashboard_live_ticker_colors_positive_and_negative_moves(self):
        ticker = nse_agent._dashboard_ticker(_dashboard_snapshot(), width=220)

        self.assertIn("[green]NIFTY 50 23,600 +0.42%[/]", ticker)
        self.assertIn("[red]NIFTY IT 28,200 -0.55%[/]", ticker)
        self.assertIn("[green]▲ AAA +6.10%[/]", ticker)
        self.assertIn("[red]▼ ZZZ -5.40%[/]", ticker)

    def test_dashboard_renderable_includes_recommendations_and_derivatives_context(self):
        text = _render_text(nse_agent._market_dashboard_renderable(_dashboard_snapshot(), width=160, height=44))

        self.assertIn("Tape Bias", text)
        self.assertIn("Breadth Gauge", text)
        self.assertIn("Index Momentum", text)
        self.assertIn("Sector Strength", text)
        self.assertIn("Mover Velocity", text)
        self.assertIn("█", text)
        self.assertIn("Recommendations", text)
        self.assertIn("Research stance", text)
        self.assertIn("Derivatives", text)
        self.assertIn("Support 23,500", text)
        self.assertIn("Resistance 23,800", text)

    def test_dashboard_recommendations_handles_missing_fno_data(self):
        snapshot = _dashboard_snapshot()
        snapshot["get_options_chain"] = {"error": "options unavailable"}
        snapshot["get_futures_analysis"] = {"error": "futures unavailable"}

        text = _render_text(nse_agent._market_dashboard_renderable(snapshot, width=120, height=32))

        self.assertIn("Recommendations", text)
        self.assertIn("Options unavailable", text)
        self.assertIn("Futures unavailable", text)


if __name__ == "__main__":
    unittest.main()
