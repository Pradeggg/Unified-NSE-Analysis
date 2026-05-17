import unittest

from backtesting.strategy_council.dsl import compile_strategy_proposal
from backtesting.strategy_council.types import (
    CouncilConfig,
    Critique,
    EvidencePack,
    StrategySpec,
)


class StrategyCouncilTypesTests(unittest.TestCase):
    def test_council_config_defaults_to_three_horizons_and_three_iterations(self):
        cfg = CouncilConfig(symbol="DMART")

        self.assertEqual(cfg.symbol, "DMART")
        self.assertEqual(cfg.horizons, (5, 10, 20))
        self.assertEqual(cfg.iterations, 3)
        self.assertEqual(cfg.max_candidates, 5)
        self.assertEqual(cfg.recommendation_threshold, "validation_then_test")

    def test_strategy_spec_has_audit_fields(self):
        spec = StrategySpec(
            strategy_id="stage2",
            horizon_days=10,
            entry_rules=("stage == Stage 2",),
            exit_rules=("close < sma_50",),
            risk_rules=("max_position_pct=10",),
            thesis="Stage 2 continuation with RS support.",
        )

        self.assertEqual(spec.strategy_id, "stage2")
        self.assertEqual(spec.horizon_days, 10)
        self.assertIn("Stage 2", spec.entry_rules[0])
        self.assertEqual(spec.status, "candidate")

    def test_evidence_pack_exposes_missing_data(self):
        pack = EvidencePack(symbol="DMART", as_of="2026-05-14", freshness={"eod": "fresh"})
        pack.missing.append("news")

        self.assertIn("news", pack.missing)
        self.assertEqual(pack.freshness["eod"], "fresh")

    def test_critique_blocks_data_leakage(self):
        critique = Critique(
            critic="data_leakage",
            verdict="reject",
            issues=("test-period metric used before final lock",),
            required_changes=("remove test metric from strategist context",),
        )

        self.assertEqual(critique.verdict, "reject")
        self.assertIn("test-period", critique.issues[0])


class StrategyCouncilDSLTests(unittest.TestCase):
    def test_compile_strategy_proposal_accepts_registered_strategy_and_horizon(self):
        spec = compile_strategy_proposal(
            {
                "strategy_id": "stage2",
                "horizon_days": 10,
                "entry_rules": ["stage == Stage 2"],
                "exit_rules": ["close < sma_50"],
                "risk_rules": ["max_position_pct=10"],
                "thesis": "Stage 2 continuation.",
            },
            allowed_strategies=("stage2", "vcp"),
            allowed_horizons=(5, 10, 20),
        )

        self.assertEqual(spec.strategy_id, "stage2")
        self.assertEqual(spec.horizon_days, 10)

    def test_compile_strategy_proposal_rejects_unregistered_strategy(self):
        with self.assertRaisesRegex(ValueError, "not allowed"):
            compile_strategy_proposal(
                {
                    "strategy_id": "unsafe_python",
                    "horizon_days": 10,
                    "entry_rules": ["eval(user_code)"],
                    "exit_rules": ["close < sma_50"],
                    "risk_rules": ["max_position_pct=10"],
                    "thesis": "Unsafe.",
                },
                allowed_strategies=("stage2",),
                allowed_horizons=(5, 10, 20),
            )
