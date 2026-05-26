"""AA-CC-2: tests for permission mode + policy."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from terminal.permission_mode import (
    PermissionMode,
    PermissionPolicy,
    parse_permission_mode_flag,
)


class TestPermissionModeParse(unittest.TestCase):
    def test_empty_defaults_to_default(self):
        self.assertEqual(PermissionMode.parse(""), PermissionMode.DEFAULT)
        self.assertEqual(PermissionMode.parse(None), PermissionMode.DEFAULT)
        self.assertEqual(PermissionMode.parse("   "), PermissionMode.DEFAULT)

    def test_canonical_values_parse(self):
        for m in PermissionMode:
            self.assertEqual(PermissionMode.parse(m.value), m)

    def test_case_and_separator_variants(self):
        self.assertEqual(PermissionMode.parse("dontask"), PermissionMode.DONT_ASK)
        self.assertEqual(PermissionMode.parse("DONT-ASK"), PermissionMode.DONT_ASK)
        self.assertEqual(PermissionMode.parse("dont_ask"), PermissionMode.DONT_ASK)
        self.assertEqual(PermissionMode.parse("BypassPermissions"), PermissionMode.BYPASS_PERMISSIONS)
        self.assertEqual(PermissionMode.parse("bypass_permissions"), PermissionMode.BYPASS_PERMISSIONS)

    def test_unknown_value_raises(self):
        with self.assertRaises(ValueError):
            PermissionMode.parse("hyperdrive")


class TestPermissionPolicy(unittest.TestCase):
    def test_default_asks_clarification_and_executes(self):
        p = PermissionPolicy()
        self.assertTrue(p.should_ask_clarification())
        self.assertTrue(p.should_execute_tools())
        self.assertTrue(p.is_default)
        self.assertFalse(p.is_plan)
        self.assertFalse(p.is_bypass)

    def test_dont_ask_skips_clarification_but_executes(self):
        p = PermissionPolicy.of("dontAsk")
        self.assertFalse(p.should_ask_clarification())
        self.assertTrue(p.should_execute_tools())

    def test_bypass_skips_clarification_and_allows_destructive(self):
        p = PermissionPolicy.of("bypassPermissions")
        self.assertFalse(p.should_ask_clarification())
        self.assertTrue(p.should_execute_tools())
        self.assertTrue(p.allows_destructive_ops())
        self.assertTrue(p.is_bypass)

    def test_plan_mode_asks_but_does_not_execute(self):
        p = PermissionPolicy.of("plan")
        self.assertTrue(p.should_ask_clarification())
        self.assertFalse(p.should_execute_tools())
        self.assertTrue(p.is_plan)
        self.assertFalse(p.allows_destructive_ops())

    def test_auto_currently_equivalent_to_default(self):
        p = PermissionPolicy.of("auto")
        self.assertTrue(p.should_ask_clarification())
        self.assertTrue(p.should_execute_tools())

    def test_from_env_reads_var(self):
        p = PermissionPolicy.from_env({"AGENT_ADDA_PERMISSION_MODE": "plan"})
        self.assertEqual(p.mode, PermissionMode.PLAN)

    def test_from_env_falls_back_on_unknown(self):
        p = PermissionPolicy.from_env({"AGENT_ADDA_PERMISSION_MODE": "garbage"})
        self.assertEqual(p.mode, PermissionMode.DEFAULT)

    def test_from_env_falls_back_on_missing(self):
        p = PermissionPolicy.from_env({})
        self.assertEqual(p.mode, PermissionMode.DEFAULT)

    def test_of_accepts_enum_value(self):
        p = PermissionPolicy.of(PermissionMode.PLAN)
        self.assertEqual(p.mode, PermissionMode.PLAN)


class TestParseFlag(unittest.TestCase):
    def test_extracts_permission_mode_flag(self):
        mode, text = parse_permission_mode_flag("/scan NIFTY --permission-mode=plan")
        self.assertEqual(mode, PermissionMode.PLAN)
        self.assertEqual(text, "/scan NIFTY")

    def test_extracts_mode_short_flag(self):
        mode, text = parse_permission_mode_flag("show RELIANCE --mode dontAsk")
        self.assertEqual(mode, PermissionMode.DONT_ASK)
        self.assertEqual(text, "show RELIANCE")

    def test_no_flag_returns_none(self):
        mode, text = parse_permission_mode_flag("just a normal query")
        self.assertIsNone(mode)
        self.assertEqual(text, "just a normal query")

    def test_empty_returns_none(self):
        mode, text = parse_permission_mode_flag("")
        self.assertIsNone(mode)
        self.assertEqual(text, "")


class TestAgentIntegration(unittest.TestCase):
    """Smoke checks that Agent picks up the policy. Heavier dispatch
    paths are covered by the existing situation_assessment tests."""

    def test_agent_defaults_to_default_mode(self):
        from terminal.agent import Agent
        a = Agent()
        self.assertEqual(a.permission_mode, PermissionMode.DEFAULT)

    def test_set_permission_mode_returns_resolved_enum(self):
        from terminal.agent import Agent
        a = Agent()
        self.assertEqual(a.set_permission_mode("dontAsk"), PermissionMode.DONT_ASK)
        self.assertEqual(a.permission_mode, PermissionMode.DONT_ASK)
        self.assertEqual(a.set_permission_mode(PermissionMode.PLAN), PermissionMode.PLAN)


class TestPlanModeRender(unittest.TestCase):
    """AA-CC-2 plan-mode preview helper."""

    def _agent_in_plan(self):
        from terminal.agent import Agent
        a = Agent()
        a.set_permission_mode("plan")
        return a

    def test_preview_lists_steps_with_args(self):
        a = self._agent_in_plan()
        trace: list = []
        plan = [
            ("get_live_quote", {"symbol": "RELIANCE"}),
            ("get_fno_overview", {"symbol": "RELIANCE"}),
        ]
        result = a._render_plan_preview(
            plan, intent="demo", clean_input="show reliance",
            mode_suffix="\n_Mode_", trace=trace,
        )
        self.assertIn("▶ PLAN MODE", result["answer"])
        self.assertIn("2 steps", result["answer"])
        self.assertIn("get_live_quote(symbol='RELIANCE')", result["answer"])
        self.assertIn("get_fno_overview(symbol='RELIANCE')", result["answer"])
        self.assertTrue(result["answer"].endswith("_Mode_"))
        self.assertEqual(result["intent"], "plan_preview:demo")
        self.assertTrue(
            any(step.get("step") == "plan_mode_preview" for step in trace),
        )

    def test_preview_singular_step_grammar(self):
        a = self._agent_in_plan()
        result = a._render_plan_preview(
            [("resolve_symbol", {"query": "RELI"})],
            intent="solo", clean_input="reli", mode_suffix="", trace=[],
        )
        self.assertIn("(1 step)", result["answer"])
        self.assertNotIn("(1 steps)", result["answer"])

    def test_preview_empty_plan_renders_zero_steps(self):
        a = self._agent_in_plan()
        result = a._render_plan_preview(
            [], intent="empty", clean_input="x", mode_suffix="", trace=[],
        )
        self.assertIn("0 steps", result["answer"])


class TestModeSlashCommand(unittest.TestCase):
    """AA-CC-2: ``/mode`` runtime control surface."""

    def _agent(self):
        from terminal.agent import Agent
        return Agent()

    def test_bare_mode_shows_current(self):
        a = self._agent()
        result = a.query("/mode")
        self.assertEqual(result["intent"], "mode_command")
        self.assertIn("PERMISSION MODE", result["answer"])
        self.assertIn(a.permission_mode.value, result["answer"])

    def test_mode_help_lists_modes(self):
        a = self._agent()
        result = a.query("/mode help")
        self.assertEqual(result["intent"], "mode_command")
        for m in PermissionMode:
            self.assertIn(m.value, result["answer"])

    def test_mode_set_updates_policy(self):
        a = self._agent()
        result = a.query("/mode plan")
        self.assertEqual(result["intent"], "mode_command")
        self.assertEqual(a.permission_mode, PermissionMode.PLAN)
        self.assertIn("plan", result["answer"])

    def test_mode_set_accepts_camel_and_kebab_variants(self):
        a = self._agent()
        a.query("/mode dont-ask")
        self.assertEqual(a.permission_mode, PermissionMode.DONT_ASK)
        a.query("/mode bypasspermissions")
        self.assertEqual(a.permission_mode, PermissionMode.BYPASS_PERMISSIONS)

    def test_mode_invalid_keeps_current(self):
        a = self._agent()
        a.set_permission_mode("plan")
        result = a.query("/mode bogus")
        self.assertEqual(result["intent"], "mode_command")
        self.assertIn("error", result["answer"].lower())
        # Current mode is preserved.
        self.assertEqual(a.permission_mode, PermissionMode.PLAN)

    def test_non_mode_input_falls_through(self):
        a = self._agent()
        # Sanity: ``/mode`` must not short-circuit lookalike prefixes.
        from terminal.agent import Agent
        # The handler should return None for anything not starting with /mode.
        self.assertIsNone(a._handle_mode_command("/modest investment"))
        self.assertIsNone(a._handle_mode_command("hello"))
        self.assertIsNone(a._handle_mode_command(""))


if __name__ == "__main__":
    unittest.main()
