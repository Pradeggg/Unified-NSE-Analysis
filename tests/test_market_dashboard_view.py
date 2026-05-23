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
            "gainers": [{"symbol": "AAA", "last_price": 120.0, "pct_change": 6.1, "volume": 1500000}],
            "losers": [{"symbol": "ZZZ", "last_price": 88.0, "pct_change": -5.4, "volume": 900000}],
            "source": "NSE live API",
        },
        "get_top_gainers_losers_NIFTY_METAL": {
            "index": "NIFTY METAL",
            "gainers": [{"symbol": "TATASTEEL", "last_price": 172.5, "pct_change": 3.2, "volume": 2100000}],
            "losers": [{"symbol": "HINDZINC", "last_price": 410.0, "pct_change": -0.8, "volume": 500000}],
            "source": "NSE live API",
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
        "get_options_chain_BANKNIFTY": {
            "symbol": "BANKNIFTY",
            "pcr": 1.05,
            "max_pain": 54000,
            "calls": [{"strike": 54500, "oi": 500000}],
            "puts": [{"strike": 53500, "oi": 650000}],
        },
        "get_futures_analysis_BANKNIFTY": {
            "symbol": "BANKNIFTY",
            "futures": [{"basis": 85.0, "basis_pct": 0.16, "cost_of_carry_annualised_pct": 7.5}],
            "rollover": {"rollover_pct": 58.0},
        },
        "run_screener_query": {"results": [{"symbol": "AAA", "rs_pct": 88.0, "change": 2.5}]},
        "run_intraday_screener_vcp": {
            "screen_type": "vcp",
            "results": [{"symbol": "AAA", "score": 72, "setup_label": "WATCH", "setup_side": "long", "timeframe": "15m"}],
            "source": "PostgreSQL intraday.ohlcv_bars",
        },
        "run_intraday_screener_supertrend": {
            "screen_type": "supertrend",
            "results": [{"symbol": "BBB", "score": 68, "setup_label": "LONG_SETUP", "setup_side": "long", "supertrend_dir": 1, "timeframe": "15m"}],
            "source": "PostgreSQL intraday.ohlcv_bars",
        },
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

    def test_dashboard_reactions_actions_and_opportunity_radar_are_source_backed(self):
        snapshot = _dashboard_snapshot()

        reactions = nse_agent._dashboard_reactions(snapshot)
        actions = nse_agent._dashboard_action_cards(snapshot, reactions)
        opportunities = nse_agent._dashboard_opportunity_radar(snapshot)

        self.assertTrue(any(row["label"] == "Risk-on confirmation" for row in reactions))
        self.assertTrue(any(row["command"] == "/scan momentum" for row in actions))
        self.assertTrue(any(row["label"] == "Pocket of Strength" for row in opportunities))
        self.assertTrue(any("VCP" in row["setup_tags"] for row in opportunities))
        self.assertTrue(any("Supertrend" in row["setup_tags"] for row in opportunities))
        self.assertFalse(
            any(
                "confirmed" in row["evidence"].lower() and "VCP" in row["setup_tags"]
                for row in opportunities
                if row.get("confidence") != "high"
            )
        )

    def test_dashboard_fno_details_include_nifty_banknifty_and_status(self):
        fno = nse_agent._dashboard_fno_details(_dashboard_snapshot())

        self.assertIn("NIFTY", fno)
        self.assertIn("BANKNIFTY", fno)
        self.assertEqual(fno["NIFTY"]["status"], "available")
        self.assertEqual(fno["BANKNIFTY"]["status"], "available")
        self.assertEqual(fno["NIFTY"]["support"], "23,500")
        self.assertEqual(fno["BANKNIFTY"]["resistance"], "54,500")

    def test_dashboard_top_index_drilldown_uses_top_indices_and_stock_actions(self):
        rows = nse_agent._dashboard_top_index_drilldown(_dashboard_snapshot())

        self.assertEqual(rows[0]["index"], "NIFTY METAL")
        self.assertTrue(rows[0]["stocks"])
        self.assertEqual(rows[0]["stocks"][0]["symbol"], "TATASTEEL")
        self.assertIn("/analyze TATASTEEL", rows[0]["stocks"][0]["actions"])

    def test_dashboard_renderable_includes_action_sections_and_drilldown(self):
        text = _render_text(nse_agent._market_dashboard_renderable(_dashboard_snapshot(), width=160, height=44, drilldown=True))

        self.assertIn("Reaction Engine", text)
        self.assertIn("Action Board", text)
        self.assertIn("Opportunity Radar", text)
        self.assertIn("Top Stocks in Top Indices", text)
        self.assertIn("VCP", text)
        self.assertIn("Supertrend", text)

    def test_dashboard_html_contains_command_center_sections_and_clickable_drilldown(self):
        html = nse_agent._render_market_dashboard_html(_dashboard_snapshot(), drilldown=True)

        self.assertIn("Reaction Engine", html)
        self.assertIn("Action Board", html)
        self.assertIn("Opportunity Radar", html)
        self.assertIn("F&amp;O Control", html)
        self.assertIn("Top Stocks in Top Indices", html)
        self.assertIn("data-index-card", html)
        self.assertIn("/scan vcp", html)


if __name__ == "__main__":
    unittest.main()
