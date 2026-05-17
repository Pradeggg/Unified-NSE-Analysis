import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

import seasonal_heat_calendar as seasonal


class SeasonalHeatCalendarTests(unittest.TestCase):
    def test_empty_cache_is_ignored_and_rebuilt_from_index_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "seasonal_monthly_returns.csv"
            pd.DataFrame(columns=["symbol", "period", "CLOSE", "return_pct", "month_num"]).to_csv(cache, index=False)

            rows = []
            for month in pd.period_range("2025-01", "2026-06", freq="M"):
                rows.append(
                    {
                        "SYMBOL": "Nifty 50",
                        "TIMESTAMP": month.to_timestamp(how="end").date().isoformat(),
                        "CLOSE": 100 + len(rows),
                    }
                )

            old_cache = seasonal._CACHE_CSV
            try:
                seasonal._CACHE_CSV = cache
                with patch("seasonal_heat_calendar._load_index_data", return_value=pd.DataFrame(rows)):
                    matrix, heat = seasonal.build_seasonal_heat_calendar({"Nifty 50": "Broad Market"}, lookback_years=7)
            finally:
                seasonal._CACHE_CSV = old_cache

        self.assertFalse(matrix.empty)
        self.assertFalse(heat.empty)
        self.assertIn("Broad Market", matrix.columns)

    def test_index_symbol_matching_is_case_insensitive_and_alias_aware(self):
        rows = [
            {"SYMBOL": "Nifty Bank", "TIMESTAMP": "2025-01-31", "CLOSE": 100},
            {"SYMBOL": "Nifty Bank", "TIMESTAMP": "2025-02-28", "CLOSE": 110},
            {"SYMBOL": "Nifty Fin Service", "TIMESTAMP": "2025-01-31", "CLOSE": 200},
            {"SYMBOL": "Nifty Fin Service", "TIMESTAMP": "2025-02-28", "CLOSE": 230},
        ]

        with patch("seasonal_heat_calendar._load_index_data", return_value=pd.DataFrame(rows)):
            monthly = seasonal._build_monthly_returns(["NIFTY BANK", "NIFTY FINANCIAL SERVICES"])

        self.assertEqual(set(monthly["SYMBOL"]), {"NIFTY BANK", "NIFTY FINANCIAL SERVICES"})
        returns = dict(zip(monthly["SYMBOL"], monthly["return_pct"]))
        self.assertAlmostEqual(returns["NIFTY BANK"], 10.0)
        self.assertAlmostEqual(returns["NIFTY FINANCIAL SERVICES"], 15.0)


if __name__ == "__main__":
    unittest.main()
