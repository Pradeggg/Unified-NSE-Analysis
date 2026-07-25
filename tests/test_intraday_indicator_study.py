import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from terminal.backtest import handle_backtest_command
from terminal.intraday_indicator_study import (
    StudyConfig,
    build_strategy_map,
    build_quant_research_thesis,
    build_report,
    confirmed_setup_symbol_drilldown,
    build_statistical_model_diagnostics,
    build_volatility_context,
    enrich_trades_with_quant_context,
    enrich_trades_with_fno_context,
    fno_regime_leaderboard,
    prepare_features,
    rolling_window_stability,
    run_indicator_backtest,
    run_intraday_indicator_study,
    strategy_map_frame,
    time_of_day_leaderboard,
    volatility_regime_leaderboard,
    walk_forward_validation,
)


def _fixture_bars(symbol: str = "AAA", timeframe: str = "5m", rows: int = 140) -> pd.DataFrame:
    start = datetime(2026, 6, 1, 9, 15)
    out = []
    close = 100.0
    for i in range(rows):
        # Gentle trend, then stronger momentum so EMA/Supertrend and MACD setups fire.
        drift = 0.04 if i < 65 else 0.18
        close += drift
        open_ = close - 0.08
        high = close + 0.18
        low = close - 0.22
        volume = 1000 + i * 8
        if i in {70, 71, 72, 95, 96}:
            volume *= 3
            high += 0.25
            close += 0.12
        out.append(
            {
                "timestamp": start + timedelta(minutes=5 * i),
                "symbol": symbol,
                "timeframe": timeframe,
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
            }
        )
    return pd.DataFrame(out)


class IntradayIndicatorStudyTests(unittest.TestCase):
    def test_backtest_builds_leaderboard_from_intraday_features(self):
        bars = _fixture_bars()
        features = prepare_features(bars)
        trades, leaderboard = run_indicator_backtest(
            features,
            StudyConfig(symbols=("AAA",), timeframes=("5m",), min_bars=80),
        )

        self.assertFalse(trades.empty)
        self.assertFalse(leaderboard.empty)
        self.assertIn("setup", leaderboard.columns)
        self.assertIn("expectancy_r", leaderboard.columns)
        self.assertTrue(set(trades["direction"]).issubset({"LONG", "SHORT"}))

    def test_study_with_csv_writes_markdown_and_html_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            csv_path = root / "bars.csv"
            _fixture_bars().to_csv(csv_path, index=False)
            result = run_intraday_indicator_study(
                StudyConfig(
                    symbols=("AAA",),
                    timeframes=("5m",),
                    min_bars=80,
                    data_path=csv_path,
                    output_dir=root / "reports",
                )
            )

            self.assertTrue(result["ok"])
            self.assertGreater(result["trades"], 0)
            self.assertTrue(Path(result["report"]["markdown"]).exists())
            self.assertTrue(Path(result["report"]["html"]).exists())
            self.assertTrue(Path(result["report"]["strategy_map"]).exists())
            self.assertIn("Indicator Leaderboard", Path(result["report"]["markdown"]).read_text())
            self.assertIn("Symbol Strategy Map", Path(result["report"]["markdown"]).read_text())

    def test_strategy_map_classifies_symbol_setups(self):
        bars = _fixture_bars()
        features = prepare_features(bars)
        trades, _ = run_indicator_backtest(
            features,
            StudyConfig(symbols=("AAA",), timeframes=("5m",), min_bars=80),
        )
        strategy_map = build_strategy_map(
            trades,
            ["AAA", "MISSING"],
            StudyConfig(
                symbols=("AAA",),
                timeframes=("5m",),
                min_bars=80,
                promote_min_trades=1,
                promote_min_expectancy_r=-10,
                promote_min_profit_factor=0,
            ),
        )
        frame = strategy_map_frame(strategy_map)

        self.assertIn("AAA", strategy_map["symbols"])
        self.assertEqual(strategy_map["symbols"]["AAA"]["status"], "promoted")
        self.assertEqual(strategy_map["symbols"]["MISSING"]["status"], "insufficient_data")
        self.assertIn("status", frame.columns)

    def test_fno_context_enrichment_adds_pcr_regime_to_trade_results(self):
        bars = _fixture_bars()
        features = prepare_features(bars)
        trades, _ = run_indicator_backtest(
            features,
            StudyConfig(symbols=("AAA",), timeframes=("5m",), min_bars=80, include_fno_context=False),
        )
        context = pd.DataFrame(
            [
                {
                    "symbol": "AAA",
                    "trade_date": "2026-06-01",
                    "expiry_date": "2026-06-30",
                    "pcr": 1.25,
                    "pcr_regime": "put-heavy",
                    "max_pain": 105.0,
                    "ce_wall": 110.0,
                    "pe_floor": 100.0,
                }
            ]
        )

        enriched = enrich_trades_with_fno_context(trades, context)
        regime = fno_regime_leaderboard(enriched)

        self.assertIn("pcr_regime", enriched.columns)
        self.assertFalse(regime.empty)
        self.assertIn("put-heavy", set(regime["pcr_regime"]))

    def test_quant_context_adds_volatility_regime_to_trades(self):
        bars = pd.concat(
            [
                _fixture_bars("AAA", rows=140),
                _fixture_bars("BBB", rows=140).assign(close=lambda df: df["close"] * 1.015),
            ],
            ignore_index=True,
        )
        features = prepare_features(bars)
        trades, _ = run_indicator_backtest(
            features,
            StudyConfig(symbols=("AAA", "BBB"), timeframes=("5m",), min_bars=80, include_fno_context=False),
        )

        context = build_volatility_context(features)
        enriched = enrich_trades_with_quant_context(trades, context)
        regime = volatility_regime_leaderboard(enriched)

        self.assertIn("ewma_volatility", context.columns)
        self.assertIn("volatility_regime", enriched.columns)
        self.assertFalse(regime.empty)
        self.assertTrue(set(enriched["volatility_regime"].dropna()).issubset({"low", "normal", "high"}))

    def test_rolling_stability_and_thesis_tables_identify_research_candidates(self):
        rows = []
        start = datetime(2026, 6, 1, 9, 15)
        outcomes = [0.25, 0.12, -0.08, 0.18, 0.10, 0.15, -0.05, 0.22, 0.08, 0.11]
        for idx, r in enumerate(outcomes):
            rows.append(
                {
                    "symbol": "AAA",
                    "setup": "ORB + VWAP",
                    "timeframe": "5m",
                    "direction": "LONG",
                    "entry_ts": start + timedelta(days=idx),
                    "r": r,
                    "mfe_r": max(r, 0.2),
                    "mae_r": min(r, -0.05),
                    "hold_bars": 4,
                    "volatility_regime": "high" if idx % 2 else "normal",
                    "pcr_regime": "put-heavy",
                }
            )
        trades = pd.DataFrame(rows)
        leaderboard = pd.DataFrame(
            [
                {
                    "setup": "ORB + VWAP",
                    "timeframe": "5m",
                    "direction": "LONG",
                    "trades": len(rows),
                    "win_rate": 80.0,
                    "expectancy_r": trades["r"].mean(),
                    "profit_factor": 4.0,
                    "avg_mfe_r": trades["mfe_r"].mean(),
                    "avg_mae_r": trades["mae_r"].mean(),
                    "avg_hold_bars": trades["hold_bars"].mean(),
                }
            ]
        )

        stability = rolling_window_stability(trades, windows=4, min_trades=2)
        vol_regime = volatility_regime_leaderboard(trades)
        thesis = build_quant_research_thesis(leaderboard, stability, vol_regime, fno_regime_leaderboard(trades))

        self.assertFalse(stability.empty)
        self.assertIn("positive_window_rate", stability.columns)
        self.assertGreaterEqual(float(stability.iloc[0]["positive_window_rate"]), 50.0)
        self.assertFalse(thesis.empty)
        self.assertIn("thesis", thesis.columns)

    def test_report_includes_quant_research_sections(self):
        bars = _fixture_bars()
        features = prepare_features(bars)
        trades, leaderboard = run_indicator_backtest(
            features,
            StudyConfig(symbols=("AAA",), timeframes=("5m",), min_bars=80, include_fno_context=False),
        )
        quant_context = build_volatility_context(features)
        trades = enrich_trades_with_quant_context(trades, quant_context)
        stability = rolling_window_stability(trades, windows=3, min_trades=1)
        vol_regime = volatility_regime_leaderboard(trades)
        thesis = build_quant_research_thesis(leaderboard, stability, vol_regime, pd.DataFrame())

        markdown = build_report(
            StudyConfig(symbols=("AAA",), timeframes=("5m",), min_bars=80, include_fno_context=False),
            ["test"],
            features,
            trades,
            leaderboard,
            rolling_stability=stability,
            volatility_regimes=vol_regime,
            quant_thesis=thesis,
        )

        self.assertIn("Quant Research Thesis", markdown)
        self.assertIn("Rolling Window Stability", markdown)
        self.assertIn("Volatility Regime Read-Through", markdown)

    def test_statistical_model_diagnostics_include_ar1_and_optional_garch_rows(self):
        bars = _fixture_bars(rows=170)
        features = prepare_features(bars)

        diagnostics = build_statistical_model_diagnostics(features, max_symbols=1, min_returns=40)

        self.assertFalse(diagnostics.empty)
        self.assertIn("model_type", diagnostics.columns)
        self.assertIn("status", diagnostics.columns)
        self.assertIn("ar1_ols", set(diagnostics["model_type"]))
        self.assertIn("garch_11", set(diagnostics["model_type"]))
        ar1 = diagnostics[diagnostics["model_type"] == "ar1_ols"].iloc[0]
        self.assertEqual(ar1["status"], "fitted")
        self.assertIsNotNone(ar1["persistence"])

    def test_report_includes_statistical_model_diagnostics_section(self):
        bars = _fixture_bars(rows=170)
        features = prepare_features(bars)
        trades, leaderboard = run_indicator_backtest(
            features,
            StudyConfig(symbols=("AAA",), timeframes=("5m",), min_bars=80, include_fno_context=False),
        )
        diagnostics = build_statistical_model_diagnostics(features, max_symbols=1, min_returns=40)

        markdown = build_report(
            StudyConfig(symbols=("AAA",), timeframes=("5m",), min_bars=80, include_fno_context=False),
            ["test"],
            features,
            trades,
            leaderboard,
            statistical_models=diagnostics,
        )

        self.assertIn("Statistical Model Diagnostics", markdown)
        self.assertIn("ar1_ols", markdown)

    def test_walk_forward_validation_confirms_unseen_positive_setups(self):
        rows = []
        start = datetime(2026, 6, 1, 9, 15)
        outcomes = [
            0.25, 0.18, 0.12, -0.05, 0.20,
            0.16, 0.10, -0.04, 0.15, 0.21,
            0.08, 0.14, -0.03, 0.19, 0.11,
            0.17, 0.09, 0.13, -0.02, 0.18,
        ]
        for idx, r in enumerate(outcomes):
            rows.append(
                {
                    "symbol": "AAA",
                    "setup": "ORB + VWAP",
                    "timeframe": "5m",
                    "direction": "LONG",
                    "entry_ts": start + timedelta(days=idx),
                    "r": r,
                }
            )

        validation = walk_forward_validation(pd.DataFrame(rows), windows=4, min_train_trades=5, min_validation_trades=3)

        self.assertFalse(validation.empty)
        self.assertIn("validation_positive_fold_rate", validation.columns)
        self.assertEqual(validation.iloc[0]["walk_forward_status"], "confirmed")
        self.assertGreater(float(validation.iloc[0]["validation_expectancy_r"]), 0)

    def test_report_includes_walk_forward_validation_section(self):
        bars = _fixture_bars(rows=170)
        features = prepare_features(bars)
        trades, leaderboard = run_indicator_backtest(
            features,
            StudyConfig(symbols=("AAA",), timeframes=("5m",), min_bars=80, include_fno_context=False),
        )
        walk_forward = walk_forward_validation(trades, windows=3, min_train_trades=1, min_validation_trades=1)

        markdown = build_report(
            StudyConfig(symbols=("AAA",), timeframes=("5m",), min_bars=80, include_fno_context=False),
            ["test"],
            features,
            trades,
            leaderboard,
            walk_forward=walk_forward,
        )

        self.assertIn("Walk-Forward Validation", markdown)
        self.assertIn("walk_forward_status", markdown)

    def test_confirmed_setup_symbol_drilldown_identifies_edge_carriers(self):
        rows = []
        start = datetime(2026, 6, 1, 9, 30)
        for idx, r in enumerate([0.4, 0.2, -0.1, 0.3, 0.1, 0.25]):
            rows.append(
                {
                    "symbol": "AAA",
                    "setup": "ORB + VWAP",
                    "timeframe": "5m",
                    "direction": "LONG",
                    "entry_ts": start + timedelta(days=idx),
                    "r": r,
                    "volatility_regime": "normal",
                    "pcr_regime": "call-heavy",
                }
            )
        for idx, r in enumerate([-0.3, -0.1, 0.05, -0.2, 0.02, -0.15]):
            rows.append(
                {
                    "symbol": "BBB",
                    "setup": "ORB + VWAP",
                    "timeframe": "5m",
                    "direction": "LONG",
                    "entry_ts": start + timedelta(days=idx),
                    "r": r,
                    "volatility_regime": "high",
                    "pcr_regime": "put-heavy",
                }
            )

        drilldown = confirmed_setup_symbol_drilldown(pd.DataFrame(rows), min_trades=5)

        self.assertFalse(drilldown.empty)
        self.assertIn("symbol_edge_status", drilldown.columns)
        self.assertEqual(drilldown.iloc[0]["symbol"], "AAA")
        self.assertEqual(drilldown.iloc[0]["symbol_edge_status"], "core_carrier")

    def test_time_of_day_leaderboard_buckets_confirmed_setup_entries(self):
        start = datetime(2026, 6, 1)
        rows = [
            {"symbol": "AAA", "setup": "ORB + VWAP", "timeframe": "5m", "direction": "LONG", "entry_ts": start.replace(hour=9, minute=30), "r": 0.2},
            {"symbol": "AAA", "setup": "ORB + VWAP", "timeframe": "5m", "direction": "LONG", "entry_ts": start.replace(hour=9, minute=45), "r": 0.1},
            {"symbol": "AAA", "setup": "ORB + VWAP", "timeframe": "5m", "direction": "LONG", "entry_ts": start.replace(hour=13, minute=0), "r": -0.1},
            {"symbol": "AAA", "setup": "ORB + VWAP", "timeframe": "5m", "direction": "LONG", "entry_ts": start.replace(hour=13, minute=15), "r": -0.2},
        ]

        buckets = time_of_day_leaderboard(pd.DataFrame(rows), min_trades=2)

        self.assertFalse(buckets.empty)
        self.assertIn("time_bucket", buckets.columns)
        self.assertEqual(buckets.iloc[0]["time_bucket"], "opening_drive")
        self.assertGreater(float(buckets.iloc[0]["expectancy_r"]), 0)

    def test_report_includes_confirmed_setup_drilldown_sections(self):
        rows = []
        start = datetime(2026, 6, 1, 9, 30)
        for idx, r in enumerate([0.4, 0.2, -0.1, 0.3, 0.1, 0.25]):
            rows.append(
                {
                    "symbol": "AAA",
                    "setup": "ORB + VWAP",
                    "timeframe": "5m",
                    "direction": "LONG",
                    "entry_ts": start + timedelta(days=idx),
                    "r": r,
                    "volatility_regime": "normal",
                    "pcr_regime": "call-heavy",
                }
            )
        trades = pd.DataFrame(rows)

        markdown = build_report(
            StudyConfig(symbols=("AAA",), timeframes=("5m",), min_bars=80, include_fno_context=False),
            ["test"],
            pd.DataFrame({"symbol": ["AAA"]}),
            trades,
            pd.DataFrame(),
            confirmed_symbol_drilldown=confirmed_setup_symbol_drilldown(trades, min_trades=5),
            confirmed_time_of_day=time_of_day_leaderboard(trades, min_trades=2),
        )

        self.assertIn("Confirmed Setup Symbol Drilldown", markdown)
        self.assertIn("Confirmed Setup Time-of-Day Filter", markdown)

    def test_terminal_command_runs_intraday_indicator_study_with_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            csv_path = root / "bars.csv"
            _fixture_bars().to_csv(csv_path, index=False)

            output = handle_backtest_command(
                f"/intraday-indicator-study --data {csv_path} --symbols AAA --timeframes 5m --min-bars 80 --output-dir {root / 'reports'}",
                project_root=root,
            )

            self.assertIn("Intraday F&O Indicator Study", output)
            self.assertIn("Top setup:", output)
            self.assertIn("Report:", output)
            self.assertIn("Strategy map JSON:", output)

    def test_terminal_command_can_persist_edge_nodes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            csv_path = root / "bars.csv"
            _fixture_bars().to_csv(csv_path, index=False)

            with patch(
                "terminal.intraday_indicator_study.persist_intraday_edge_nodes",
                return_value={"refresh_id": "refresh_test", "nodes": 1},
                create=True,
            ) as persist_mock:
                output = handle_backtest_command(
                    f"/intraday-indicator-study --data {csv_path} --symbols AAA --timeframes 5m --min-bars 80 "
                    f"--output-dir {root / 'reports'} --persist-edges",
                    project_root=root,
                )

        self.assertIn("Edge nodes: persisted=1 refresh=refresh_test", output)
        persist_mock.assert_called_once()

    def test_terminal_command_can_build_edge_memory_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch(
                "terminal.backtest.generate_edge_memory_report",
                return_value={
                    "summary": {"total_edges": 2, "status_counts": {"candidate": 1, "retired": 1}},
                    "paths": {
                        "html": str(root / "edge_knowledge_report.html"),
                        "markdown": str(root / "edge_knowledge_report.md"),
                        "json": str(root / "edge_knowledge_report.json"),
                    },
                },
                create=True,
            ) as report_mock:
                output = handle_backtest_command(
                    "/edge-knowledge-report --output-dir reports/latest",
                    project_root=root,
                )

        self.assertIn("Edge Knowledge Report: OK", output)
        self.assertIn("Edges: 2", output)
        self.assertIn("candidate=1", output)
        self.assertIn("retired=1", output)
        self.assertIn("HTML:", output)
        report_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
