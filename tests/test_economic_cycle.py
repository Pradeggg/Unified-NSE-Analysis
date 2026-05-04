import unittest

import pandas as pd

from economic_cycle import (
    apply_cycle_to_candidates,
    apply_cycle_to_sectors,
    detect_economic_cycle_phase,
)


class EconomicCycleTests(unittest.TestCase):
    def test_detects_slowdown_when_growth_weakens_and_volatility_rises(self):
        macro = pd.DataFrame(
            [
                {"indicator": "Nifty 50", "trend": "FALLING", "signal_score": -0.8},
                {"indicator": "India VIX", "trend": "RISING", "signal_score": -2.5},
                {"indicator": "India CPI Index", "trend": "RISING", "signal_score": -1.2},
                {"indicator": "Brent Crude", "trend": "RISING", "signal_score": -1.5},
                {"indicator": "US 10Y Treasury", "trend": "RISING", "signal_score": -1.0},
            ]
        )

        cycle = detect_economic_cycle_phase(macro, market_regime="BEAR_TREND")

        self.assertEqual(cycle["cycle_phase"], "SLOWDOWN")
        self.assertGreaterEqual(cycle["confidence"], 0.6)
        self.assertEqual(cycle["regime_cycle_alignment"], "ALIGNED_RISK_OFF")
        self.assertIn("FMCG", cycle["preferred_sectors"])

    def test_detects_recovery_when_risk_eases_and_market_turns_up(self):
        macro = pd.DataFrame(
            [
                {"indicator": "Nifty 50", "trend": "RISING", "signal_score": 1.3},
                {"indicator": "India VIX", "trend": "FALLING", "signal_score": 2.0},
                {"indicator": "India Interest Rate", "trend": "FALLING", "signal_score": 0.6},
                {"indicator": "Brent Crude", "trend": "FALLING", "signal_score": 0.8},
                {"indicator": "Copper (USD/MT)", "trend": "RISING", "signal_score": 0.7},
            ]
        )

        cycle = detect_economic_cycle_phase(macro, market_regime="ROTATION")

        self.assertEqual(cycle["cycle_phase"], "RECOVERY")
        self.assertEqual(cycle["regime_cycle_alignment"], "EARLY_MARKET_RECOVERY")
        self.assertIn("Banking", cycle["preferred_sectors"])

    def test_applies_cycle_tags_and_score_adjustments_to_sectors_and_candidates(self):
        cycle = {
            "cycle_phase": "SLOWDOWN",
            "preferred_sectors": ["FMCG", "Pharma", "IT"],
            "avoid_sectors": ["Metals", "Auto", "Real Estate"],
        }
        sectors = pd.DataFrame(
            [
                {"SECTOR_NAME": "Nifty FMCG", "ROTATION_SCORE": 12.0},
                {"SECTOR_NAME": "Auto", "ROTATION_SCORE": 11.0},
                {"SECTOR_NAME": "Defence", "ROTATION_SCORE": 10.0},
            ]
        )
        candidates = pd.DataFrame(
            [
                {"SYMBOL": "DEF", "SECTOR_NAME": "Defence", "INVESTMENT_SCORE": 70.0},
                {"SYMBOL": "FMCG", "SECTOR_NAME": "FMCG", "INVESTMENT_SCORE": 69.0},
                {"SYMBOL": "AUTO", "SECTOR_NAME": "Auto", "INVESTMENT_SCORE": 72.0},
            ]
        )

        adjusted_sectors = apply_cycle_to_sectors(sectors, cycle)
        adjusted_candidates = apply_cycle_to_candidates(candidates, cycle)

        fmcg_sector = adjusted_sectors.set_index("SECTOR_NAME").loc["Nifty FMCG"]
        auto_sector = adjusted_sectors.set_index("SECTOR_NAME").loc["Auto"]
        self.assertEqual(fmcg_sector["CYCLE_TAG"], "CYCLE_FAVOURED")
        self.assertEqual(fmcg_sector["CYCLE_ADJUSTMENT"], 4)
        self.assertEqual(fmcg_sector["ROTATION_SCORE"], 16.0)
        self.assertEqual(auto_sector["CYCLE_TAG"], "CYCLE_UNFAVOURED")
        self.assertEqual(auto_sector["ROTATION_SCORE"], 8.0)

        adjusted = adjusted_candidates.set_index("SYMBOL")
        self.assertEqual(adjusted.loc["FMCG", "CYCLE_TAG"], "CYCLE_FAVOURED")
        self.assertEqual(adjusted.loc["FMCG", "INVESTMENT_SCORE"], 73.0)
        self.assertEqual(adjusted.loc["AUTO", "CYCLE_TAG"], "CYCLE_UNFAVOURED")
        self.assertEqual(adjusted.loc["AUTO", "INVESTMENT_SCORE"], 69.0)


if __name__ == "__main__":
    unittest.main()
