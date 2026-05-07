import math
import unittest

import pandas as pd

from sector_rotation_tracker import (
    _apply_latest_history_prices,
    _backfill_snapshot_dates,
    _history_as_of,
    _latest_eod_close_date,
    _text_or_none,
    build_html_report,
)


class SectorRotationTrackerTests(unittest.TestCase):
    def test_latest_eod_close_date_uses_price_history_timestamp(self):
        hist = pd.DataFrame(
            {
                "SYMBOL": ["A", "A", "B"],
                "TIMESTAMP": ["2026-05-05", "2026-05-06", "2026-05-04"],
                "CLOSE": [10, 11, 20],
            }
        )

        self.assertEqual(_latest_eod_close_date(hist), "2026-05-06")

    def test_apply_latest_history_prices_overrides_stale_analysis_close(self):
        candidates = pd.DataFrame(
            {
                "SYMBOL": ["RELIANCE", "TCS"],
                "CLOSE": [1000.0, 2000.0],
                "CURRENT_PRICE": [1000.0, 2000.0],
            }
        )
        hist = pd.DataFrame(
            {
                "SYMBOL": ["RELIANCE", "RELIANCE"],
                "TIMESTAMP": pd.to_datetime(["2026-05-05", "2026-05-06"]),
                "CLOSE": [1400.0, 1410.0],
            }
        )

        updated = _apply_latest_history_prices(candidates, hist)

        rel = updated[updated["SYMBOL"] == "RELIANCE"].iloc[0]
        tcs = updated[updated["SYMBOL"] == "TCS"].iloc[0]
        self.assertEqual(rel["CLOSE"], 1410.0)
        self.assertEqual(rel["CURRENT_PRICE"], 1410.0)
        self.assertEqual(tcs["CLOSE"], 2000.0)

    def test_html_close_label_uses_price_date_and_hides_nan_fundamentals(self):
        html = build_html_report(
            {
                "snap_date": "2026-05-07",
                "prev_date": None,
                "week_snap": None,
                "summary": {"stage_counts": {"STAGE_1": 0, "STAGE_2": 1, "STAGE_3": 0, "STAGE_4": 0}},
                "snapshot_history": [
                    {"snapshot_date": "2026-05-07", "total_stocks": 1, "stage2_count": 1},
                    {"snapshot_date": "2026-05-06", "total_stocks": 1, "stage2_count": 1},
                ],
                "stage2_now": [
                    {
                        "symbol": "TEST",
                        "company_name": "Test Ltd",
                        "stage": "STAGE_2",
                        "price": 101.5,
                        "price_date": "2026-05-06",
                        "investment_score": 50.0,
                        "technical_score": 60.0,
                        "rsi": 55.0,
                        "enhanced_fund_score": math.nan,
                        "earnings_quality": math.nan,
                        "sales_growth": math.nan,
                        "financial_strength": math.nan,
                        "institutional_backing": math.nan,
                        "fund_details": None,
                        "narrative": "Test narrative",
                    }
                ],
                "top_picks": [],
            }
        )

        self.assertIn("Close 2026-05-06", html)
        self.assertIn("EOD Close: <strong>2026-05-06</strong>", html)
        self.assertIn("Daily Stage Transitions", html)
        self.assertIn("No stage transitions in the latest comparison", html)
        self.assertIn("2026-05-06", html)
        self.assertNotIn(">nan<", html)
        self.assertNotIn("sb-num\">nan", html)

    def test_daily_snapshots_show_stage_transition_context(self):
        html = build_html_report(
            {
                "snap_date": "2026-05-07",
                "prev_date": "2026-05-06",
                "week_snap": None,
                "summary": {
                    "stage_counts": {"STAGE_1": 10, "STAGE_2": 12, "STAGE_3": 2, "STAGE_4": 1},
                    "transitions": {"S1_to_S2": 2, "S2_to_S3": 1, "S2_to_S1": 1},
                },
                "snapshot_history": [
                    {
                        "snapshot_date": "2026-05-07",
                        "compare_date": "2026-05-06",
                        "total_stocks": 25,
                        "stage2_count": 12,
                        "stage2_delta": 2,
                        "stage_changes": 4,
                        "new_stage2": 2,
                        "exit_stage2": 1,
                        "S1_to_S2": 2,
                        "S2_to_S3": 1,
                        "S2_to_S1": 1,
                    },
                    {
                        "snapshot_date": "2026-05-06",
                        "total_stocks": 25,
                        "stage2_count": 10,
                        "stage2_delta": 0,
                        "stage_changes": 0,
                    },
                ],
                "stage2_now": [],
                "top_picks": [],
            }
        )

        self.assertIn("Daily Stage Transitions", html)
        self.assertIn("vs 2026-05-06", html)
        self.assertIn("S2 Δ +2", html)
        self.assertIn("2 new", html)
        self.assertIn("1 exits", html)
        self.assertIn("S1 → S2", html)
        self.assertIn("S2 → S3", html)

    def test_text_or_none_treats_nan_strings_as_missing(self):
        self.assertIsNone(_text_or_none(math.nan))
        self.assertIsNone(_text_or_none("nan"))
        self.assertIsNone(_text_or_none(""))
        self.assertEqual(_text_or_none("Sales: 100 Cr"), "Sales: 100 Cr")

    def test_backfill_snapshot_dates_returns_last_trading_dates(self):
        hist = pd.DataFrame(
            {
                "SYMBOL": ["A", "A", "A", "A"],
                "TIMESTAMP": ["2026-05-01", "2026-05-04", "2026-05-05", "2026-05-06"],
                "CLOSE": [10, 11, 12, 13],
            }
        )

        dates = _backfill_snapshot_dates(hist, days=3)

        self.assertEqual(dates, ["2026-05-04", "2026-05-05", "2026-05-06"])

    def test_backfill_snapshot_dates_respects_end_date(self):
        hist = pd.DataFrame(
            {
                "SYMBOL": ["A", "A", "A", "A"],
                "TIMESTAMP": ["2026-05-01", "2026-05-04", "2026-05-05", "2026-05-06"],
                "CLOSE": [10, 11, 12, 13],
            }
        )

        dates = _backfill_snapshot_dates(hist, days=2, end_date="2026-05-05")

        self.assertEqual(dates, ["2026-05-04", "2026-05-05"])

    def test_history_as_of_excludes_future_prices(self):
        hist = pd.DataFrame(
            {
                "SYMBOL": ["A", "A", "A"],
                "TIMESTAMP": pd.to_datetime(["2026-05-04", "2026-05-05", "2026-05-06"]),
                "CLOSE": [10, 11, 12],
            }
        )

        filtered = _history_as_of(hist, "2026-05-05")

        self.assertEqual(filtered["TIMESTAMP"].max().date().isoformat(), "2026-05-05")
        self.assertEqual(len(filtered), 2)


if __name__ == "__main__":
    unittest.main()
