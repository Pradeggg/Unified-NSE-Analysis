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


if __name__ == "__main__":
    unittest.main()
