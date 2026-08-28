import math
import unittest

import pandas as pd

from sector_rotation_tracker import (
    _apply_latest_history_prices,
    _backfill_snapshot_dates,
    _tradingview_symbols,
    _stage2_rs_trading_signal,
    _apply_stage2_rs_signals,
    _is_confirmed_vcp_setup,
    _history_as_of,
    _latest_eod_close_date,
    _load_fundamental_score_lookup,
    _vcp_pick_pg_rows,
    _should_skip_unknown_snapshot_overwrite,
    _strategy_lab_report_url,
    _text_or_none,
    backfill_vcp_picks_to_pg,
    build_html_report,
    ROOT,
    write_tradingview_watchlist,
)


class SectorRotationTrackerTests(unittest.TestCase):
    def test_stage2_rs_trading_signal_weights_relative_strength(self):
        strong_rs = {
            "stage": "STAGE_2",
            "technical_score": 72,
            "relative_strength": 92,
            "minervini_score": 18,
            "enhanced_fund_score": 74,
            "trend_signal": "STRONG_BULLISH",
            "trading_signal": "HOLD",
        }
        weak_rs = {
            **strong_rs,
            "relative_strength": 35,
        }

        self.assertEqual(_stage2_rs_trading_signal(strong_rs), "STRONG_BUY")
        self.assertEqual(_stage2_rs_trading_signal(weak_rs), "HOLD")

    def test_missing_fundamentals_do_not_receive_neutral_points_or_fund_buy(self):
        row = {
            "stage": "STAGE_2",
            "technical_score": 98,
            "relative_strength": 99,
            "stage_score": 99,
            "trend_signal": "STRONG_BULLISH",
        }
        result = _apply_stage2_rs_signals([row])[0]

        self.assertEqual(result["technical_signal"], "STRONG_BUY")
        self.assertEqual(result["fund_action"], "RESEARCH_REQUIRED")
        self.assertEqual(result["fundamental_coverage"], 0)
        self.assertLess(result["investment_score"], 100)

    def test_weak_fundamentals_cap_fund_action_despite_strong_technical_setup(self):
        row = {
            "stage": "STAGE_2",
            "technical_score": 98,
            "relative_strength": 99,
            "stage_score": 99,
            "trend_signal": "STRONG_BULLISH",
            "fundamental_score": 10,
            "earnings_quality": 35,
            "sales_growth": 60,
            "financial_strength": 45,
        }
        result = _apply_stage2_rs_signals([row])[0]

        self.assertEqual(result["technical_signal"], "STRONG_BUY")
        self.assertEqual(result["fund_action"], "AVOID")

    def test_vcp_requires_explicit_pattern_measurements(self):
        self.assertFalse(_is_confirmed_vcp_setup({"technical_score": 99, "investment_score": 99}))
        self.assertTrue(_is_confirmed_vcp_setup({
            "vcp_score": 82,
            "vcp_contraction_pct": 12,
            "vcp_breakout_pct": 2.5,
        }))

    def test_tradingview_symbols_are_nse_prefixed_and_deduplicated(self):
        rows = [
            {"symbol": "reliance"},
            {"symbol": "RELIANCE"},
            {"symbol": "TCS.NS"},
            {"symbol": ""},
            {"symbol": None},
        ]

        self.assertEqual(_tradingview_symbols(rows), ["NSE:RELIANCE", "NSE:TCS"])

    def test_write_tradingview_watchlist_uses_all_stage2_buy_signals_with_good_fundamentals(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ready = {
                "stage": "STAGE_2", "technical_score": 90, "relative_strength": 90,
                "trend_signal": "STRONG_BULLISH", "enhanced_fund_score": 72,
                "earnings_quality": 74, "sales_growth": 70, "financial_strength": 66,
            }
            dated, latest = write_tradingview_watchlist(
                {
                    "snap_date": "2026-05-29",
                    "vcp_breakout_picks": [
                        {**ready, "symbol": "VCPONLY", "vcp_score": 80, "vcp_contraction_pct": 10, "vcp_breakout_pct": 2},
                    ],
                    "stage2_now": [
                        {**ready, "symbol": "RELIANCE"},
                        {**ready, "symbol": "TCS"},
                        {**ready, "symbol": "WIPRO", "enhanced_fund_score": 64.9},
                        {"symbol": "MISSING", "stage": "STAGE_2", "technical_score": 99, "relative_strength": 99},
                    ],
                },
                reports_dir=root / "reports" / "sector_rotation",
                latest_dir=root / "reports" / "latest",
            )

            self.assertEqual(dated.name, "stage2_buy_tradingview_2026-05-29.txt")
            self.assertEqual(
                dated.read_text(encoding="utf-8"),
                "NSE:RELIANCE,NSE:TCS,NSE:VCPONLY\n",
            )
            self.assertEqual(latest.name, "stage2_buy_tradingview.txt")
            self.assertEqual(latest.read_text(encoding="utf-8"), dated.read_text(encoding="utf-8"))

    def test_vcp_pick_pg_rows_capture_rank_scores_and_fundamentals(self):
        rows = _vcp_pick_pg_rows(
            {
                "snap_date": "2026-05-29",
                "vcp_breakout_picks": [
                    {
                        "symbol": "bbb",
                        "company_name": "Beta Ltd",
                        "sector": "Capital Goods",
                        "price": 100,
                        "live_price": 101,
                        "price_date": "2026-05-29",
                        "change_1d_pct": 2.0,
                        "change_1w_pct": 1.0,
                        "rsi": 58,
                        "relative_strength": 1.1,
                        "trading_signal": "HOLD",
                        "trend_signal": "STRONG_BULLISH",
                        "supertrend_state": "BULLISH",
                        "investment_score": 68,
                        "enhanced_fund_score": 72,
                        "earnings_quality": 74,
                        "sales_growth": 70,
                        "financial_strength": 66,
                        "vcp_score": 82,
                        "vcp_breakout_pct": 2.5,
                        "vcp_contraction_pct": 1.2,
                        "stance": "BULLISH",
                        "narrative": "VCP setup with strong fundamentals.",
                    }
                ],
            }
        )

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["snapshot_date"], "2026-05-29")
        self.assertEqual(row["rank"], 1)
        self.assertEqual(row["symbol"], "BBB")
        self.assertEqual(row["vcp_score"], 82.0)
        self.assertEqual(row["enhanced_fund_score"], 72.0)
        self.assertEqual(row["earnings_quality"], 74.0)
        self.assertEqual(row["vcp_breakout_pct"], 2.5)
        self.assertEqual(row["vcp_contraction_pct"], 1.2)
        self.assertEqual(row["narrative"], "VCP setup with strong fundamentals.")

    def test_backfill_vcp_picks_to_pg_computes_each_snapshot(self):
        from unittest.mock import patch

        stage2 = pd.DataFrame(
            [
                {
                    "snapshot_date": "2026-05-29",
                    "symbol": "AAA",
                    "stage": "STAGE_2",
                    "price": 100,
                    "change_1d_pct": 2.5,
                    "change_1w_pct": 1.2,
                    "rsi": 58,
                    "relative_strength": 1.1,
                    "trend_signal": "STRONG_BULLISH",
                    "supertrend_state": "BULLISH",
                    "investment_score": 70,
                }
            ]
        )
        reports = []

        with (
            patch("sector_rotation_tracker._pg_query") as mock_query,
            patch("sector_rotation_tracker._pg_stage_snapshots", return_value=stage2),
            patch("sector_rotation_tracker.write_vcp_picks_to_pg") as mock_write,
        ):
            mock_query.return_value = pd.DataFrame({"snapshot_date": ["2026-05-29"]})
            mock_write.side_effect = lambda report: reports.append(report) or len(report["vcp_breakout_picks"])

            saved = backfill_vcp_picks_to_pg(start_date="2026-01-01")

        self.assertEqual(saved, 0)
        self.assertEqual(reports[0]["snap_date"], "2026-05-29")
        self.assertEqual(reports[0]["vcp_breakout_picks"], [])

    def test_latest_eod_close_date_uses_price_history_timestamp(self):
        hist = pd.DataFrame(
            {
                "SYMBOL": ["A", "A", "B"],
                "TIMESTAMP": ["2026-05-05", "2026-05-06", "2026-05-04"],
                "CLOSE": [10, 11, 20],
            }
        )

        self.assertEqual(_latest_eod_close_date(hist), "2026-05-06")

    def test_strategy_lab_report_url_is_share_safe(self):
        self.assertEqual(
            _strategy_lab_report_url(ROOT / "reports" / "latest" / "portfolio_strategy_lab.html"),
            "portfolio_strategy_lab.html",
        )
        self.assertEqual(
            _strategy_lab_report_url(ROOT / "portfolio" / "data" / "nse_pg_strategy_lab" / "latest" / "runs" / "x.md"),
            "",
        )

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
                "week_snap": "2026-05-01",
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
                "tradingview_watchlist": {
                    "latest_path": "reports/latest/stage2_buy_tradingview.txt",
                    "count": 1,
                },
            }
        )

        self.assertIn("Close 2026-05-06", html)
        self.assertIn("EOD Close: <strong>EOD Wednesday, 06 May 2026</strong>", html)
        self.assertIn("Week vs: <strong>EOD Friday, 01 May 2026</strong>", html)
        self.assertIn("Weekly View (EOD Friday, 01 May 2026)", html)
        self.assertIn(
            "Source: <strong>PostgreSQL/scores.stage_snapshots + market.equity_eod; SQLite stage_changes for transition diffs</strong>",
            html,
        )
        self.assertIn("Daily Stage Transitions", html)
        self.assertIn("No stage transitions in the latest comparison", html)
        self.assertIn("2026-05-06", html)
        self.assertNotIn(">nan<", html)
        self.assertNotIn("sb-num\">nan", html)
        self.assertIn("TradingView Upload", html)
        self.assertIn("stage2_buy_tradingview.txt", html)

    def test_stage2_table_sorting_handles_currency_and_detail_rows(self):
        html = build_html_report(
            {
                "snap_date": "2026-06-02",
                "prev_date": None,
                "week_snap": None,
                "summary": {"stage_counts": {"STAGE_1": 0, "STAGE_2": 2, "STAGE_3": 0, "STAGE_4": 0}},
                "snapshot_history": [],
                "stage2_now": [
                    {
                        "symbol": "BETA",
                        "company_name": "Beta Ltd",
                        "stage": "STAGE_2",
                        "price": 1239.20,
                        "live_price": 1239.20,
                        "investment_score": 50.0,
                        "technical_score": 60.0,
                        "rsi": 55.0,
                        "trading_signal": "HOLD",
                        "narrative": "Beta narrative",
                    },
                    {
                        "symbol": "ALPHA",
                        "company_name": "Alpha Ltd",
                        "stage": "STAGE_2",
                        "price": 950.0,
                        "live_price": 950.0,
                        "investment_score": 40.0,
                        "technical_score": 50.0,
                        "rsi": 45.0,
                        "trading_signal": "BUY",
                        "narrative": "Alpha narrative",
                    },
                ],
                "top_picks": [],
            }
        )

        self.assertIn("data-detail-id", html)
        self.assertIn("masterRows", html)
        self.assertIn("tbody.appendChild(detail)", html)
        self.assertIn("₹,%▲▼,", html)

    def test_stage2_table_hides_missing_supertrend_values(self):
        html = build_html_report(
            {
                "snap_date": "2026-06-02",
                "prev_date": None,
                "week_snap": None,
                "summary": {"stage_counts": {"STAGE_1": 0, "STAGE_2": 1, "STAGE_3": 0, "STAGE_4": 0}},
                "snapshot_history": [],
                "stage2_now": [
                    {
                        "symbol": "TEST",
                        "company_name": "Test Ltd",
                        "stage": "STAGE_2",
                        "price": 100,
                        "supertrend_state": "BEARISH",
                        "supertrend_value": math.nan,
                    }
                ],
                "top_picks": [],
            }
        )

        self.assertNotIn("₹nan", html)
        self.assertNotIn(">nan<", html)
        self.assertIn("↓ BEARISH", html)

    def test_top_pick_modal_json_hides_nan_text_fields(self):
        html = build_html_report(
            {
                "snap_date": "2026-06-02",
                "prev_date": None,
                "week_snap": None,
                "summary": {"stage_counts": {"STAGE_1": 0, "STAGE_2": 1, "STAGE_3": 0, "STAGE_4": 0}},
                "snapshot_history": [],
                "stage2_now": [],
                "top_picks": [
                    {
                        "symbol": "TEST",
                        "company_name": "Test Ltd",
                        "sector": math.nan,
                        "investment_score": 75,
                    }
                ],
            }
        )

        self.assertNotIn('"sector": "nan"', html)
        self.assertIn('"sector": "N/A"', html)

    def test_top_picks_section_shows_tradingview_link_and_vcp_fundamentals(self):
        html = build_html_report(
            {
                "snap_date": "2026-05-29",
                "prev_date": None,
                "week_snap": None,
                "summary": {"stage_counts": {"STAGE_1": 0, "STAGE_2": 1, "STAGE_3": 0, "STAGE_4": 0}},
                "snapshot_history": [],
                "stage2_now": [],
                "top_picks": [
                    {
                        "symbol": "AAA",
                        "company_name": "Alpha Ltd",
                        "sector": "Industrials",
                        "investment_score": 70,
                        "technical_score": 75,
                        "rsi": 60,
                        "stance": "BULLISH",
                    }
                ],
                "vcp_breakout_picks": [
                    {
                        "symbol": "BBB",
                        "company_name": "Beta Ltd",
                        "sector": "Capital Goods",
                        "price": 100,
                        "vcp_breakout_pct": 2.5,
                        "vcp_contraction_pct": 1.2,
                        "rsi": 58,
                        "relative_strength": 1.1,
                        "investment_score": 68,
                        "vcp_score": 82,
                        "enhanced_fund_score": 72,
                        "earnings_quality": 74,
                        "sales_growth": 70,
                        "financial_strength": 66,
                    }
                ],
                "tradingview_watchlist": {
                    "latest_path": "reports/latest/stage2_buy_tradingview.txt",
                    "count": 1,
                },
            }
        )

        top_idx = html.index("Fund-Ready Stage 2 Candidates")
        link_idx = html.index("stage2_buy_tradingview.txt", top_idx)
        self.assertGreater(link_idx, top_idx)
        vcp_idx = html.index('id="t-vcp"')
        vcp_end = html.index('id="t-help"', vcp_idx)
        vcp_html = html[vcp_idx:vcp_end]
        self.assertIn("Enh Fund<span", vcp_html)
        self.assertIn("Earnings<span", vcp_html)
        self.assertIn("Sales<span", vcp_html)
        self.assertIn("Fin Strength<span", vcp_html)
        self.assertIn('<span class="sb-num">72</span>', vcp_html)
        self.assertIn('<span class="sb-num">74</span>', vcp_html)
        self.assertIn("VCP Score", vcp_html)
        self.assertIn("toggleCol", vcp_html)
        self.assertIn("exportCSV", vcp_html)
        self.assertIn("sortTbl", vcp_html)
        self.assertIn('id="vcp-bt"', vcp_html)
        self.assertIn("sortTbl('vcp-bt',0)", vcp_html)
        self.assertIn('id="vcp-bt-body"', vcp_html)

    def test_fundamental_score_lookup_fills_missing_pg_subscores_from_csv(self):
        import tempfile
        from pathlib import Path

        pg_scores = pd.DataFrame(
            [
                {
                    "symbol": "TEST",
                    "ENHANCED_FUND_SCORE": 72.0,
                    "EARNINGS_QUALITY": None,
                    "SALES_GROWTH": None,
                }
            ]
        )

        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "fundamental_scores_database.csv"
            pd.DataFrame(
                [
                    {
                        "symbol": "TEST",
                        "ENHANCED_FUND_SCORE": 65.0,
                        "EARNINGS_QUALITY": 81.0,
                        "SALES_GROWTH": 77.0,
                        "FINANCIAL_STRENGTH": 69.0,
                        "INSTITUTIONAL_BACKING": 55.0,
                    }
                ]
            ).to_csv(csv_path, index=False)

            lookup = _load_fundamental_score_lookup(pg_scores, [csv_path])

        self.assertEqual(float(lookup["TEST"]["ENHANCED_FUND_SCORE"]), 72.0)
        self.assertEqual(float(lookup["TEST"]["EARNINGS_QUALITY"]), 81.0)
        self.assertEqual(float(lookup["TEST"]["SALES_GROWTH"]), 77.0)

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

    def test_daily_stage_transitions_are_collapsible_by_default(self):
        html = build_html_report(
            {
                "snap_date": "2026-05-07",
                "prev_date": "2026-05-06",
                "week_snap": None,
                "summary": {"stage_counts": {"STAGE_1": 0, "STAGE_2": 1, "STAGE_3": 0, "STAGE_4": 0}},
                "snapshot_history": [
                    {"snapshot_date": "2026-05-07", "compare_date": "2026-05-06", "total_stocks": 10, "stage2_count": 5},
                    {"snapshot_date": "2026-05-06", "total_stocks": 10, "stage2_count": 4},
                ],
                "stage2_now": [],
                "top_picks": [],
            }
        )

        self.assertIn('<details class="section snapshot-section">', html)
        self.assertIn('<summary class="snapshot-summary">', html)
        self.assertIn("Show / hide daily transition cards", html)
        self.assertNotIn('<details class="section snapshot-section" open>', html)
        self.assertIn("snapshot-grid", html)

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

    def test_forced_backfill_does_not_replace_classified_snapshot_with_all_unknown(self):
        self.assertTrue(
            _should_skip_unknown_snapshot_overwrite(
                existing_classified_count=10,
                rows=[{"stage": "UNKNOWN"}, {"stage": "UNKNOWN"}],
                force=True,
            )
        )
        self.assertFalse(
            _should_skip_unknown_snapshot_overwrite(
                existing_classified_count=10,
                rows=[{"stage": "UNKNOWN"}, {"stage": "STAGE_2"}],
                force=True,
            )
        )
        self.assertFalse(
            _should_skip_unknown_snapshot_overwrite(
                existing_classified_count=0,
                rows=[{"stage": "UNKNOWN"}],
                force=True,
            )
        )


if __name__ == "__main__":
    unittest.main()
