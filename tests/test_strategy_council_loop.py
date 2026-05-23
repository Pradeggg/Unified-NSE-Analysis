import unittest
from unittest.mock import patch

import pandas as pd

from backtesting.strategy_council.council import run_strategy_council
from backtesting.strategy_council.llm import JSONLLMCritic, JSONLLMStrategist, RuleBasedRiskCritic, RuleBasedStrategist
from backtesting.strategy_council.types import BacktestSliceResult, CouncilConfig, EvidencePack, StrategySpec


class StrategyCouncilLoopTests(unittest.TestCase):
    def test_rule_based_strategist_returns_bounded_candidates(self):
        strategist = RuleBasedStrategist()
        config = CouncilConfig(symbol="DMART", max_candidates=2)
        evidence = EvidencePack(symbol="DMART", as_of="2026-05-14", technical={"close": 100, "bars": 260})

        candidates = strategist.propose(evidence=evidence, config=config, prior_feedback=())

        self.assertLessEqual(len(candidates), 2)
        self.assertTrue(all(c.strategy_id in config.allowed_strategies for c in candidates))
        self.assertTrue(all(c.origin == "deterministic_fallback" for c in candidates))

    def test_rule_based_risk_critic_rejects_zero_trade_results(self):
        critic = RuleBasedRiskCritic()
        critique = critic.critique(
            candidates=(),
            train_results=(
                BacktestSliceResult("train", "stage2", 10, {"total_return_pct": 0}, 0),
            ),
            validation_results=(),
        )

        self.assertEqual(critique.verdict, "revise")
        self.assertIn("trade count", " ".join(critique.issues).lower())

    def test_json_llm_strategist_and_critic_adapt_structured_llm_output(self):
        strategist = JSONLLMStrategist(
            llm_call=lambda _system, _prompt: {
                "strategies": [
                    {
                        "strategy_id": "stage2",
                        "horizon_days": 10,
                        "entry_rules": ["stage == Stage 2"],
                        "exit_rules": ["close < sma_50"],
                        "risk_rules": ["max_position_pct=10"],
                        "thesis": "LLM proposed Stage 2 continuation.",
                    }
                ]
            }
        )
        critic = JSONLLMCritic(
            critic_name="data_leakage",
            llm_call=lambda _system, _prompt: {
                "verdict": "revise",
                "issues": ["validation trade count is low"],
                "required_changes": ["try no-trade branch"],
                "confidence_delta": -0.2,
            },
        )
        config = CouncilConfig(symbol="DMART")
        evidence = EvidencePack(symbol="DMART", as_of="2026-05-14", technical={"close": 100, "bars": 260})

        candidates = strategist.propose(evidence=evidence, config=config, prior_feedback=())
        critique = critic.critique(candidates=candidates, train_results=(), validation_results=())

        self.assertEqual(candidates[0].thesis, "LLM proposed Stage 2 continuation.")
        self.assertEqual(candidates[0].origin, "llm")
        self.assertEqual(critique.verdict, "revise")
        self.assertIn("no-trade", critique.required_changes[0])


class StrategyCouncilOrchestrationTests(unittest.TestCase):
    def _flat_eod(self):
        return pd.DataFrame(
            {
                "date": pd.date_range("2024-01-01", periods=520, freq="D"),
                "symbol": ["DMART"] * 520,
                "open": [100.0] * 520,
                "high": [101.0] * 520,
                "low": [99.0] * 520,
                "close": [100.0] * 520,
                "volume": [1000] * 520,
            }
        )

    def _single_stage2_strategist(self):
        class StaticStrategist:
            def propose(self, *, evidence, config, prior_feedback):
                return (
                    StrategySpec(
                        "stage2",
                        5,
                        ("entry",),
                        ("exit",),
                        ("risk",),
                        "static test strategy",
                    ),
                )

        return StaticStrategist()

    def test_positive_test_does_not_override_negative_validation(self):
        def fake_run(_df, spec, *, split_name, initial_capital):
            if split_name == "validation":
                return BacktestSliceResult("validation", spec.strategy_id, spec.horizon_days, {"total_return_pct": -7.0}, 5)
            if split_name == "test":
                return BacktestSliceResult("test", spec.strategy_id, spec.horizon_days, {"total_return_pct": 8.0}, 1)
            return BacktestSliceResult("train", spec.strategy_id, spec.horizon_days, {"total_return_pct": 12.0}, 5)

        config = CouncilConfig(symbol="DMART", iterations=1, max_candidates=1)
        evidence = EvidencePack(symbol="DMART", as_of="2026-05-14", technical={"close": 100, "bars": 520})

        with patch("backtesting.strategy_council.council.run_strategy_spec_on_split", side_effect=fake_run):
            result = run_strategy_council(
                self._flat_eod(),
                evidence=evidence,
                config=config,
                strategist=self._single_stage2_strategist(),
            )

        self.assertEqual(result.recommendation, "WAIT")
        self.assertIn("validation", result.rationale.lower())

    def test_positive_test_does_not_override_zero_trade_validation(self):
        def fake_run(_df, spec, *, split_name, initial_capital):
            if split_name == "validation":
                return BacktestSliceResult("validation", spec.strategy_id, spec.horizon_days, {"total_return_pct": 0.0}, 0)
            if split_name == "test":
                return BacktestSliceResult("test", spec.strategy_id, spec.horizon_days, {"total_return_pct": 8.0}, 1)
            return BacktestSliceResult("train", spec.strategy_id, spec.horizon_days, {"total_return_pct": 12.0}, 5)

        config = CouncilConfig(symbol="DMART", iterations=1, max_candidates=1)
        evidence = EvidencePack(symbol="DMART", as_of="2026-05-14", technical={"close": 100, "bars": 520})

        with patch("backtesting.strategy_council.council.run_strategy_spec_on_split", side_effect=fake_run):
            result = run_strategy_council(
                self._flat_eod(),
                evidence=evidence,
                config=config,
                strategist=self._single_stage2_strategist(),
            )

        self.assertEqual(result.recommendation, "WAIT")
        self.assertIn("validation", result.rationale.lower())

    def test_council_runs_iterations_then_only_runs_test_after_lock(self):
        df = pd.DataFrame(
            {
                "date": pd.date_range("2024-01-01", periods=520, freq="D"),
                "symbol": ["DMART"] * 520,
                "open": [100 + i * 0.2 for i in range(520)],
                "high": [101 + i * 0.2 for i in range(520)],
                "low": [99 + i * 0.2 for i in range(520)],
                "close": [100.5 + i * 0.2 for i in range(520)],
                "volume": [1000] * 520,
            }
        )
        config = CouncilConfig(symbol="DMART", iterations=2, max_candidates=2)
        evidence = EvidencePack(symbol="DMART", as_of="2026-05-14", technical={"close": 200, "bars": 520})

        result = run_strategy_council(df, evidence=evidence, config=config)

        self.assertEqual(len(result.iterations), 2)
        self.assertIsNotNone(result.locked_strategy)
        self.assertTrue(result.test_results)
        self.assertTrue(all(r.split == "test" for r in result.test_results))
        self.assertIn(result.recommendation, {"TRADE_RESEARCH", "WAIT", "NO_TRADE"})

    def test_council_computes_stage_features_before_splitting(self):
        df = pd.DataFrame(
            {
                "date": pd.date_range("2024-01-01", periods=520, freq="D"),
                "symbol": ["DMART"] * 520,
                "open": [100 + i * 0.5 for i in range(520)],
                "high": [101 + i * 0.5 for i in range(520)],
                "low": [99 + i * 0.5 for i in range(520)],
                "close": [100.5 + i * 0.5 for i in range(520)],
                "volume": [1000] * 520,
            }
        )
        config = CouncilConfig(
            symbol="DMART",
            iterations=1,
            max_candidates=1,
            allowed_strategies=("stage2",),
        )
        evidence = EvidencePack(symbol="DMART", as_of="2026-05-14", technical={"close": 300, "bars": 520})

        result = run_strategy_council(df, evidence=evidence, config=config)

        validation = result.iterations[0].validation_results[0]
        test = result.test_results[0]
        self.assertGreater(validation.trade_count, 0)
        self.assertGreater(test.trade_count, 0)
