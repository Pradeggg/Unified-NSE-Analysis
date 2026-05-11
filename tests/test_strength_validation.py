import unittest
from unittest.mock import patch

from terminal.agent import _keyword_intent
from terminal.tools import normalize_relative_strength_pct, validate_strength_watchlist


class StrengthValidationTests(unittest.TestCase):
    def test_relative_strength_percent_is_not_double_scaled(self):
        self.assertEqual(normalize_relative_strength_pct(35.57), 35.57)
        self.assertEqual(normalize_relative_strength_pct(0.3557), 35.57)

        row = {"relative_strength": 0.3557}
        row["rs_pct"] = normalize_relative_strength_pct(row["relative_strength"])
        self.assertLess(row["rs_pct"], 200)
        self.assertEqual(row["rs_pct"], 35.57)

    def test_strength_validator_reports_missing_evidence_instead_of_assuming(self):
        def fake_forensic(symbol):
            if symbol == "AAA":
                return {
                    "symbol": "AAA",
                    "beneish": {"score": -2.0, "interpretation": "Low"},
                    "piotroski": {"score": 7, "max_possible": 9, "strength": "Strong"},
                    "altman": {"score": 4.0, "zone": "Safe"},
                    "overall_risk": "low",
                }
            return {"symbol": symbol, "error": "No financial statement data found"}

        with patch("terminal.tools._latest_snapshot_date", return_value="2026-05-08"), patch(
            "terminal.tools._fetch_strength_snapshot_rows",
            return_value={
                "AAA": {
                    "symbol": "AAA",
                    "company_name": "AAA Ltd",
                    "stage": "STAGE_2",
                    "price": 100.0,
                    "change_1m_pct": 12.0,
                    "rsi": 55.0,
                    "relative_strength": 35.57,
                    "can_slim_score": 23.0,
                    "enhanced_fund_score": 66.0,
                    "financial_strength": 61.0,
                    "investment_score": 70.0,
                    "trading_signal": "BUY",
                    "sector": "Test",
                },
                "BBB": {
                    "symbol": "BBB",
                    "company_name": "BBB Ltd",
                    "stage": "STAGE_2",
                    "price": 200.0,
                    "change_1m_pct": 9.0,
                    "rsi": 60.0,
                    "relative_strength": None,
                    "can_slim_score": None,
                    "enhanced_fund_score": None,
                    "financial_strength": None,
                    "investment_score": 60.0,
                    "trading_signal": "HOLD",
                    "sector": "Test",
                },
            },
        ), patch("terminal.tools.run_forensic_analysis", side_effect=fake_forensic):
            result = validate_strength_watchlist(["AAA", "BBB"])

        aaa, bbb = result["results"]
        self.assertEqual(aaa["symbol"], "AAA")
        self.assertEqual(aaa["rs_pct"], 35.57)
        self.assertEqual(aaa["piotroski_score"], 7)
        self.assertEqual(aaa["evidence_coverage"], "complete")

        self.assertEqual(bbb["symbol"], "BBB")
        self.assertIn("relative_strength", bbb["missing_evidence"])
        self.assertIn("can_slim_score", bbb["missing_evidence"])
        self.assertIn("enhanced_fund_score", bbb["missing_evidence"])
        self.assertIn("forensic", bbb["missing_evidence"])
        self.assertEqual(bbb["evidence_coverage"], "partial")
        self.assertIn("missing", bbb["verdict"].lower())

    def test_keyword_router_uses_strength_validator_for_multi_factor_strength_question(self):
        routed = _keyword_intent(
            "out of J&KBANK ROSSTECH APOLLOPIPE which show strength based on CANSLIM RS fundamental analysis Piotroski"
        )

        self.assertEqual(routed["intent"], "strength_validation")
        self.assertEqual(routed["plan"][0][0], "validate_strength_watchlist")
        self.assertEqual(routed["plan"][0][1]["symbols"], ["J&KBANK", "ROSSTECH", "APOLLOPIPE"])


if __name__ == "__main__":
    unittest.main()
