import unittest
from unittest.mock import patch

from terminal.tools import run_screener_query


class TerminalToolsScreenerTests(unittest.TestCase):
    def test_new_highs_screener_uses_postgres_52w_high_computation(self):
        captured = {}

        def fake_pg_fetchall(sql, params=()):
            captured["sql"] = sql
            captured["params"] = params
            return [
                (
                    "MCX",
                    "Multi Commodity Exchange",
                    "STAGE_2",
                    0.8,
                    70.0,
                    72.0,
                    3156.90,
                    96.95,
                    1.2,
                    61.0,
                    "HOLD",
                    "Capital Markets",
                )
            ]

        with patch("terminal.tools._latest_snapshot_date", return_value="2026-05-12"), patch(
            "terminal.tools._pg_fetchall", side_effect=fake_pg_fetchall
        ):
            result = run_screener_query("new_highs", top_n=5)

        self.assertIn("market.equity_eod", captured["sql"])
        self.assertIn("MAX(high) AS high_52w", captured["sql"])
        self.assertIn("l.close >= h.high_52w * 0.95", captured["sql"])
        self.assertEqual(captured["params"], ("2026-05-12", 5))
        self.assertEqual(result["screen_type"], "new_highs")
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["results"][0]["symbol"], "MCX")

    def test_strong_buy_screener_returns_stage_and_rs_pct_from_pg_snapshot(self):
        captured = {}

        def fake_pg_fetchall(sql, params=()):
            captured["sql"] = sql
            captured["params"] = params
            return [
                (
                    "ABC",
                    "ABC Limited",
                    "STAGE_2",
                    0.72,
                    88.0,
                    81.0,
                    123.45,
                    12.34,
                    12.34,
                    61.0,
                    "STRONG_BUY",
                    "Capital Goods",
                )
            ]

        with patch("terminal.tools._latest_snapshot_date", return_value="2026-05-12"), patch(
            "terminal.tools._pg_fetchall", side_effect=fake_pg_fetchall
        ):
            result = run_screener_query("strong_buy", top_n=5)

        self.assertIn("trading_signal='STRONG_BUY'", captured["sql"])
        self.assertNotIn("'HOLD'", captured["sql"])
        self.assertEqual(captured["params"], ("2026-05-12", 5))
        self.assertEqual(result["count"], 1)
        row = result["results"][0]
        self.assertEqual(row["stage"], "STAGE_2")
        self.assertEqual(row["trading_signal"], "STRONG_BUY")
        self.assertEqual(row["relative_strength"], 12.34)
        self.assertEqual(row["rs_pct"], 12.34)
        self.assertEqual(row["technical_score"], 81.0)


if __name__ == "__main__":
    unittest.main()
