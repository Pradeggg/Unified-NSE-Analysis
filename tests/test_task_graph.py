"""AA-CC-4: tests for the task dependency graph."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from terminal.router.schema import ToolCallSpec
from terminal.router.task_graph import (
    add_blocked_by,
    add_blocks,
    addBlockedBy,
    addBlocks,
    dependency_layers,
    topological_order,
    validate,
)


def _spec(tid: str, tool: str = "x", **args) -> ToolCallSpec:
    return ToolCallSpec(tool=tool, args=args, task_id=tid)


class TestToolCallSpecDeps(unittest.TestCase):
    def test_default_fields_empty(self):
        s = ToolCallSpec(tool="x")
        self.assertEqual(s.task_id, "")
        self.assertEqual(s.blocked_by, ())

    def test_with_deps_returns_copy(self):
        s = ToolCallSpec(tool="x")
        s2 = s.with_deps(task_id="A", blocked_by=("B",))
        self.assertEqual(s2.task_id, "A")
        self.assertEqual(s2.blocked_by, ("B",))
        self.assertEqual(s.task_id, "")  # original untouched

    def test_to_dict_omits_empty_optional_fields(self):
        d = ToolCallSpec(tool="x").to_dict()
        self.assertNotIn("task_id", d)
        self.assertNotIn("blocked_by", d)

    def test_to_dict_includes_deps_when_set(self):
        d = ToolCallSpec(tool="x", task_id="A", blocked_by=("B",)).to_dict()
        self.assertEqual(d["task_id"], "A")
        self.assertEqual(d["blocked_by"], ["B"])


class TestAddBlocks(unittest.TestCase):
    def test_add_blocks_annotates_dependents(self):
        plan = (_spec("A"), _spec("B"), _spec("C"))
        out = add_blocks(plan, "A", "B", "C")
        self.assertEqual(out[1].blocked_by, ("A",))
        self.assertEqual(out[2].blocked_by, ("A",))

    def test_add_blocks_idempotent(self):
        plan = (_spec("A"), _spec("B"))
        once = add_blocks(plan, "A", "B")
        twice = add_blocks(once, "A", "B")
        self.assertEqual(once[1].blocked_by, twice[1].blocked_by)

    def test_self_block_rejected(self):
        plan = (_spec("A"),)
        with self.assertRaises(ValueError):
            add_blocks(plan, "A", "A")

    def test_unknown_blocker_rejected(self):
        plan = (_spec("A"),)
        with self.assertRaises(ValueError):
            add_blocks(plan, "Z", "A")

    def test_unknown_blocked_rejected(self):
        plan = (_spec("A"),)
        with self.assertRaises(ValueError):
            add_blocks(plan, "A", "Z")

    def test_camelcase_alias(self):
        plan = (_spec("A"), _spec("B"))
        out = addBlocks(plan, "A", "B")
        self.assertEqual(out[1].blocked_by, ("A",))


class TestAddBlockedBy(unittest.TestCase):
    def test_add_blocked_by_appends_deps_in_order(self):
        plan = (_spec("A"), _spec("B"), _spec("C"))
        out = add_blocked_by(plan, "C", "A", "B")
        self.assertEqual(out[2].blocked_by, ("A", "B"))

    def test_add_blocked_by_dedups(self):
        plan = (_spec("A"), _spec("B"))
        out = add_blocked_by(plan, "B", "A")
        out = add_blocked_by(out, "B", "A")
        self.assertEqual(out[1].blocked_by, ("A",))

    def test_camelcase_alias(self):
        plan = (_spec("A"), _spec("B"))
        out = addBlockedBy(plan, "B", "A")
        self.assertEqual(out[1].blocked_by, ("A",))


class TestValidate(unittest.TestCase):
    def test_valid_dag_passes(self):
        plan = add_blocks((_spec("A"), _spec("B"), _spec("C")), "A", "B", "C")
        validate(plan)

    def test_two_node_cycle_rejected(self):
        plan = (
            _spec("A").with_deps(task_id="A", blocked_by=("B",)),
            _spec("B").with_deps(task_id="B", blocked_by=("A",)),
        )
        with self.assertRaises(ValueError) as ctx:
            validate(plan)
        self.assertIn("Cycle", str(ctx.exception))

    def test_self_loop_rejected(self):
        plan = (_spec("A").with_deps(task_id="A", blocked_by=("A",)),)
        with self.assertRaises(ValueError):
            validate(plan)

    def test_unknown_dep_rejected(self):
        plan = (_spec("A").with_deps(task_id="A", blocked_by=("ZZZ",)),)
        with self.assertRaises(ValueError):
            validate(plan)

    def test_duplicate_id_rejected(self):
        plan = (_spec("A"), _spec("A", tool="y"))
        with self.assertRaises(ValueError):
            validate(plan)

    def test_empty_plan_ok(self):
        validate(())


class TestLayersAndTopo(unittest.TestCase):
    def test_layers_groups_independents(self):
        plan = add_blocks(
            (_spec("R"), _spec("L"), _spec("F"), _spec("E"), _spec("A")),
            "R", "L", "F", "E", "A",
        )
        plan = add_blocks(plan, "E", "A")
        layers = dependency_layers(plan)
        self.assertEqual(len(layers), 3)
        self.assertEqual([s.task_id for s in layers[0]], ["R"])
        self.assertEqual({s.task_id for s in layers[1]}, {"L", "F", "E"})
        self.assertEqual([s.task_id for s in layers[2]], ["A"])

    def test_topological_order_is_valid(self):
        plan = add_blocks(
            (_spec("R"), _spec("L"), _spec("F"), _spec("E"), _spec("A")),
            "R", "L", "F", "E", "A",
        )
        plan = add_blocks(plan, "E", "A")
        ordered = topological_order(plan)
        seen: set[str] = set()
        for spec in ordered:
            for dep in spec.blocked_by:
                self.assertIn(dep, seen, f"{spec.task_id} ran before {dep}")
            seen.add(spec.task_id)

    def test_synthetic_ids_assigned_to_unlabeled(self):
        plan = (ToolCallSpec(tool="x"), ToolCallSpec(tool="y"))
        ordered = topological_order(plan)
        ids = {s.task_id for s in ordered}
        self.assertEqual(len(ids), 2)
        self.assertTrue(all(ids))


class TestCompoundStockIntegration(unittest.TestCase):
    def test_compound_plan_has_resolve_as_root(self):
        from terminal.router.compound_stock import CompoundStockProvider
        from terminal.router.context import ContextPack

        text = "live price for reliance and f&o data and intraday setup in 5 min"
        cands = CompoundStockProvider().propose(text, ContextPack(session_id="test"))
        executable = [c for c in cands if c.tool_plan]
        if not executable:
            self.skipTest("symbol resolution unavailable in this env")
        plan = executable[0].tool_plan
        ids = {s.task_id for s in plan}
        self.assertEqual(
            ids,
            {"resolve", "live_quote", "fno_overview",
             "intraday_setup_explain", "intraday_setup_analysis"},
        )
        layers = dependency_layers(plan)
        self.assertEqual([s.task_id for s in layers[0]], ["resolve"])
        layer1_ids = {s.task_id for s in layers[1]}
        self.assertEqual(
            layer1_ids,
            {"live_quote", "fno_overview", "intraday_setup_explain"},
        )
        self.assertEqual([s.task_id for s in layers[2]], ["intraday_setup_analysis"])


if __name__ == "__main__":
    unittest.main()
