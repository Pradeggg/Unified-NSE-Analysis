"""Tests for ``_execute_plan_layered`` (parallel layer execution).

Verifies that:
* Layers from ``dependency_layers`` run concurrently.
* Sequential layers run in order.
* ``resolve_symbol`` substitution propagates across layer boundaries.
* Results preserve deterministic layered order.
* Empty plan returns empty results.
* Behaviour matches sequential ``_execute_plan`` for dep-free plans.
"""
from __future__ import annotations

import threading
import time
from unittest.mock import patch

import pytest

from terminal.agent import _execute_plan, _execute_plan_layered
from terminal.router.schema import ToolCallSpec
from terminal.router.task_graph import add_blocks


def _make_specs():
    """3-layer plan: resolve -> (a, b) -> c."""
    base = (
        ToolCallSpec(tool="resolve_symbol", args={"query": "reliance"}, task_id="resolve"),
        ToolCallSpec(tool="get_live_quote", args={"symbol": ""}, task_id="a"),
        ToolCallSpec(tool="get_fno_overview", args={"symbol": ""}, task_id="b"),
        ToolCallSpec(tool="explain_intraday_setup", args={"symbol": ""}, task_id="c"),
    )
    plan = add_blocks(base, "resolve", "a", "b", "c")
    plan = add_blocks(plan, "a", "c")
    plan = add_blocks(plan, "b", "c")
    return plan


class TestLayeredExecution:
    def test_empty_plan_returns_empty(self) -> None:
        assert _execute_plan_layered(()) == []

    def test_single_layer_calls_in_order(self) -> None:
        calls: list[str] = []

        def fake(name, args):
            calls.append(name)
            return {"ok": True}

        specs = (
            ToolCallSpec(tool="x", args={}, task_id="x"),
            ToolCallSpec(tool="y", args={}, task_id="y"),
        )
        with patch("terminal.agent.call_tool", side_effect=fake):
            out = _execute_plan_layered(specs)
        assert [r["tool"] for r in out] == ["x", "y"]
        assert calls == ["x", "y"]

    def test_independent_calls_run_in_parallel(self) -> None:
        """Two independent slow calls should run truly concurrently."""
        barrier = threading.Barrier(2, timeout=2)

        def slow(name, args):
            if name == "resolve_symbol":
                return {"symbol": "X"}
            barrier.wait()  # both parallel-layer threads must arrive
            time.sleep(0.05)
            return {"name": name}

        specs = (
            ToolCallSpec(tool="resolve_symbol", args={"query": "x"}, task_id="r"),
            ToolCallSpec(tool="get_live_quote", args={"symbol": "X"}, task_id="a"),
            ToolCallSpec(tool="get_fno_overview", args={"symbol": "X"}, task_id="b"),
        )
        specs = add_blocks(specs, "r", "a", "b")

        with patch("terminal.agent.call_tool", side_effect=slow):
            out = _execute_plan_layered(specs)
        assert {r["tool"] for r in out} == {"resolve_symbol", "get_live_quote", "get_fno_overview"}

    def test_resolve_symbol_propagates_across_layers(self) -> None:
        seen_symbols: dict[str, str] = {}

        def fake(name, args):
            if name == "resolve_symbol":
                return {"symbol": "RELIANCE"}
            seen_symbols[name] = args.get("symbol", "")
            return {"ok": True}

        specs = _make_specs()
        with patch("terminal.agent.call_tool", side_effect=fake):
            _execute_plan_layered(specs)
        assert seen_symbols["get_live_quote"] == "RELIANCE"
        assert seen_symbols["get_fno_overview"] == "RELIANCE"
        assert seen_symbols["explain_intraday_setup"] == "RELIANCE"

    def test_deterministic_layered_order(self) -> None:
        def fake(name, args):
            return {"name": name}

        specs = _make_specs()
        with patch("terminal.agent.call_tool", side_effect=fake):
            out = _execute_plan_layered(specs)
        tools = [r["tool"] for r in out]
        # Layer 0: resolve, Layer 1: a, b (input order), Layer 2: c.
        assert tools[0] == "resolve_symbol"
        assert set(tools[1:3]) == {"get_live_quote", "get_fno_overview"}
        assert tools[3] == "explain_intraday_setup"

    def test_matches_sequential_for_depfree_plan(self) -> None:
        """For dep-free plans with explicit ordering deps, layered ==
        sequential."""
        def fake(name, args):
            if name == "resolve_symbol":
                return {"symbol": "X"}
            return {"tool": name, "symbol": args.get("symbol")}

        base = (
            ToolCallSpec(tool="resolve_symbol", args={"query": "x"}, task_id="r"),
            ToolCallSpec(tool="get_live_quote", args={"symbol": ""}, task_id="q"),
        )
        specs = add_blocks(base, "r", "q")
        tuples = [(s.tool, dict(s.args)) for s in specs]

        with patch("terminal.agent.call_tool", side_effect=fake):
            seq = _execute_plan(tuples)
        with patch("terminal.agent.call_tool", side_effect=fake):
            par = _execute_plan_layered(specs)

        assert [r["tool"] for r in seq] == [r["tool"] for r in par]
        assert [r["result"] for r in seq] == [r["result"] for r in par]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
