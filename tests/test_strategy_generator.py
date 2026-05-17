import unittest

from backtesting.strategy_council.dsl import _FORBIDDEN_TOKENS
from backtesting.strategy_council.strategy_generator import (
    COMPOSED_STRATEGY_ID,
    CompositeStrategist,
    ENTRY_RULES,
    EXIT_RULES,
    RISK_RULES,
    RuleComposer,
    generate_candidates_via_rules,
)
from backtesting.strategy_council.types import CouncilConfig, EvidencePack


class RuleComposerTests(unittest.TestCase):
    def test_compose_returns_valid_spec(self):
        composer = RuleComposer()
        spec = composer.compose(
            entry_atoms=("ema_bullish", "rsi_oversold"),
            exit_atoms=("profit_target", "stop_loss"),
            risk_atoms=("position_size",),
            horizon_days=10,
            thesis="EMA recovery on oversold reset.",
            allowed_horizons=(5, 10, 20),
        )
        self.assertEqual(spec.strategy_id, COMPOSED_STRATEGY_ID)
        self.assertEqual(spec.horizon_days, 10)
        self.assertEqual(spec.origin, "rule_composer")
        self.assertEqual(spec.params["entry_atoms"], ["ema_bullish", "rsi_oversold"])
        self.assertEqual(spec.params["exit_atoms"], ["profit_target", "stop_loss"])
        self.assertEqual(spec.params["risk_atoms"], ["position_size"])
        self.assertIn("EMA period 20", " ".join(spec.entry_rules))

    def test_compose_rejects_when_no_valid_entry(self):
        composer = RuleComposer()
        with self.assertRaises(ValueError):
            composer.compose(
                entry_atoms=("unknown_atom",),
                exit_atoms=("profit_target",),
                risk_atoms=("position_size",),
                horizon_days=10,
                thesis="bad entry",
            )

    def test_all_atom_descriptions_pass_dsl_safety(self):
        all_atoms = list(ENTRY_RULES.values()) + list(EXIT_RULES.values()) + list(RISK_RULES.values())
        joined = " ".join(atom.description for atom in all_atoms).lower()
        for token in _FORBIDDEN_TOKENS:
            self.assertNotIn(token, joined, f"atom descriptions must not contain {token!r}")

    def test_compose_thesis_required(self):
        composer = RuleComposer()
        with self.assertRaises(ValueError):
            composer.compose(
                entry_atoms=("ema_bullish",),
                exit_atoms=("profit_target",),
                risk_atoms=("position_size",),
                horizon_days=10,
                thesis="",
            )


class GenerateCandidatesTests(unittest.TestCase):
    def test_sampled_is_deterministic(self):
        config = CouncilConfig(symbol="INFY", max_candidates=4, horizons=(5, 10, 20))
        a = generate_candidates_via_rules(config, method="sampled", seed=42)
        b = generate_candidates_via_rules(config, method="sampled", seed=42)
        self.assertEqual([s.params["entry_atoms"] for s in a], [s.params["entry_atoms"] for s in b])
        self.assertEqual(len(a), 4)
        self.assertTrue(all(s.origin == "rule_composer" for s in a))

    def test_sampled_respects_max_candidates(self):
        config = CouncilConfig(symbol="INFY", max_candidates=2, horizons=(10,))
        result = generate_candidates_via_rules(config, method="sampled", seed=1)
        self.assertEqual(len(result), 2)

    def test_exhaustive_method_runs_and_caps(self):
        config = CouncilConfig(symbol="INFY", max_candidates=3, horizons=(10,))
        result = generate_candidates_via_rules(
            config, method="exhaustive", entry_choices=1, exit_choices=1, risk_choices=1
        )
        self.assertLessEqual(len(result), 3)
        self.assertTrue(all(s.strategy_id == COMPOSED_STRATEGY_ID for s in result))

    def test_unknown_method_raises(self):
        config = CouncilConfig(symbol="INFY", max_candidates=1)
        with self.assertRaises(ValueError):
            generate_candidates_via_rules(config, method="bogus")

    def test_zero_candidates_returns_empty(self):
        config = CouncilConfig(symbol="INFY", max_candidates=0)
        self.assertEqual(generate_candidates_via_rules(config), ())


class _StubStrategist:
    def __init__(self, specs):
        self._specs = tuple(specs)
        self.calls = 0

    def propose(self, *, evidence, config, prior_feedback):
        self.calls += 1
        return self._specs


class CompositeStrategistTests(unittest.TestCase):
    def setUp(self):
        self.config = CouncilConfig(symbol="INFY", max_candidates=5, horizons=(5, 10))
        self.evidence = EvidencePack(symbol="INFY", as_of="2026-05-17")

    def test_combines_inner_and_rule_proposals(self):
        from backtesting.strategy_council.llm import RuleBasedStrategist

        inner = RuleBasedStrategist()
        strategist = CompositeStrategist(inner=inner, llm_ratio=0.4, seed=7)
        proposals = strategist.propose(
            evidence=self.evidence, config=self.config, prior_feedback=()
        )
        self.assertEqual(len(proposals), 5)
        origins = {p.origin for p in proposals}
        self.assertIn("rule_composer", origins)
        self.assertIn("deterministic_fallback", origins)

    def test_zero_inner_ratio_yields_only_rule_proposals(self):
        inner = _StubStrategist(())
        strategist = CompositeStrategist(inner=inner, llm_ratio=0.0, seed=3)
        proposals = strategist.propose(
            evidence=self.evidence, config=self.config, prior_feedback=()
        )
        self.assertEqual(len(proposals), 5)
        self.assertTrue(all(p.origin == "rule_composer" for p in proposals))

    def test_full_inner_ratio_yields_only_inner(self):
        from backtesting.strategy_council.llm import RuleBasedStrategist

        inner = RuleBasedStrategist()
        strategist = CompositeStrategist(inner=inner, llm_ratio=1.0)
        proposals = strategist.propose(
            evidence=self.evidence, config=self.config, prior_feedback=()
        )
        self.assertTrue(all(p.origin == "deterministic_fallback" for p in proposals))

    def test_dedupes_overlapping_proposals(self):
        from backtesting.strategy_council.strategy_generator import generate_candidates_via_rules

        rules = generate_candidates_via_rules(self.config, method="sampled", seed=11)
        inner = _StubStrategist(rules)
        strategist = CompositeStrategist(inner=inner, llm_ratio=0.6, seed=11)
        proposals = strategist.propose(
            evidence=self.evidence, config=self.config, prior_feedback=()
        )
        signatures = {
            (p.strategy_id, p.horizon_days, tuple(p.entry_rules), tuple(p.exit_rules))
            for p in proposals
        }
        self.assertEqual(len(signatures), len(proposals))


if __name__ == "__main__":
    unittest.main()
