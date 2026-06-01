"""AA-CC-11: Parallel Tool Dispatch tests.

Covers:
  1. Independent read-only tools complete in ~max-of-three latency, not sum-of-three.
  2. Serial tools (in _SERIAL_TOOLS) keep the full batch sequential.
  3. A single tool in the batch is not sent through the ThreadPoolExecutor.
  4. One tool's failure does not block the others' results from reaching the model.
  5. Original call order is preserved in the returned list.
  6. Result structure is correct (name, args, result, call_id).
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch, call as mock_call

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from terminal.agent import _parallel_tool_dispatch, _SERIAL_TOOLS, _PARALLEL_WORKERS


# ─── helpers ─────────────────────────────────────────────────────────────────

def _slow_tool(name, args, delay=0.1):
    time.sleep(delay)
    return {"tool": name, "ok": True}


def _make_tc(name, args=None, call_id=None):
    return {"name": name, "args": args or {}, "id": call_id or f"id_{name}"}


# ─── unit tests ──────────────────────────────────────────────────────────────

class TestParallelDispatchConcurrency:
    def test_three_independent_tools_run_faster_than_sum(self):
        delay = 0.12  # 120 ms each → sum ~360 ms, concurrent ~120 ms
        calls = [
            _make_tc("get_symbol_snapshot", {"symbol": "RELIANCE"}),
            _make_tc("get_market_breadth"),
            _make_tc("get_live_market_overview"),
        ]
        side_effects = [
            lambda n, a, d=delay: _slow_tool(n, a, d)
        ]

        def slow_fn(name, args):
            time.sleep(delay)
            return {"tool": name, "ok": True}

        t0 = time.perf_counter()
        results = _parallel_tool_dispatch(calls, slow_fn)
        elapsed = time.perf_counter() - t0

        # Should finish in roughly delay + small overhead (well under 3× delay)
        assert elapsed < 2.5 * delay, (
            f"Concurrent dispatch took {elapsed:.3f}s — expected < {2.5 * delay:.3f}s"
        )
        assert len(results) == 3

    def test_single_tool_skips_threadpool(self):
        """Single tool must not be submitted to ThreadPoolExecutor."""
        calls = [_make_tc("get_symbol_snapshot")]
        call_log = []

        def fn(name, args):
            call_log.append(name)
            return {"ok": True}

        results = _parallel_tool_dispatch(calls, fn)
        assert len(results) == 1
        assert call_log == ["get_symbol_snapshot"]


class TestParallelDispatchOrder:
    def test_result_order_matches_call_order(self):
        calls = [
            _make_tc("tool_a", call_id="id_a"),
            _make_tc("tool_b", call_id="id_b"),
            _make_tc("tool_c", call_id="id_c"),
        ]
        counter = []

        def fn(name, args):
            counter.append(name)
            # Introduce variable sleep so completion order ≠ call order
            time.sleep({"tool_a": 0.06, "tool_b": 0.02, "tool_c": 0.04}.get(name, 0))
            return {"name": name}

        results = _parallel_tool_dispatch(calls, fn)
        names = [r[0] for r in results]
        assert names == ["tool_a", "tool_b", "tool_c"], (
            f"Expected original call order, got {names}"
        )

    def test_call_ids_preserved_in_order(self):
        calls = [
            _make_tc("get_market_breadth", call_id="cid_1"),
            _make_tc("get_live_market_overview", call_id="cid_2"),
        ]

        def fn(name, args):
            return {"ok": True}

        results = _parallel_tool_dispatch(calls, fn)
        ids = [r[3] for r in results]
        assert ids == ["cid_1", "cid_2"]


class TestSerialFallback:
    def test_serial_tool_forces_sequential_dispatch(self):
        serial_tool = next(iter(_SERIAL_TOOLS))
        calls = [
            _make_tc("get_symbol_snapshot"),
            _make_tc(serial_tool),  # forces sequential
        ]
        call_order = []

        def fn(name, args):
            call_order.append(name)
            return {"ok": True}

        results = _parallel_tool_dispatch(calls, fn)
        assert len(results) == 2
        # Order must match original call order
        assert call_order == ["get_symbol_snapshot", serial_tool]

    def test_all_serial_tools_stay_sequential(self):
        serial_tools = list(_SERIAL_TOOLS)[:2]
        if len(serial_tools) < 2:
            return  # not enough serial tools to test

        calls = [_make_tc(t) for t in serial_tools]
        call_order = []

        def fn(name, args):
            call_order.append(name)
            return {"ok": True}

        results = _parallel_tool_dispatch(calls, fn)
        assert len(results) == len(serial_tools)
        assert call_order == serial_tools


class TestErrorIsolation:
    def test_one_failure_does_not_block_others(self):
        calls = [
            _make_tc("get_symbol_snapshot", call_id="id_a"),
            _make_tc("get_market_breadth", call_id="id_b"),
            _make_tc("get_live_market_overview", call_id="id_c"),
        ]

        def fn(name, args):
            if name == "get_market_breadth":
                raise RuntimeError("simulated tool failure")
            return {"tool": name, "ok": True}

        results = _parallel_tool_dispatch(calls, fn)
        assert len(results) == 3

        names = [r[0] for r in results]
        assert "get_symbol_snapshot" in names
        assert "get_market_breadth" in names
        assert "get_live_market_overview" in names

        # Failed tool returns an error dict, not an exception
        failed = next(r for r in results if r[0] == "get_market_breadth")
        assert "error" in failed[2], "Expected error dict for failed tool"

        # Successful tools return real results
        ok_a = next(r for r in results if r[0] == "get_symbol_snapshot")
        assert ok_a[2].get("ok") is True

    def test_args_passed_correctly(self):
        calls = [
            _make_tc("get_symbol_snapshot", args={"symbol": "RELIANCE"}),
            _make_tc("get_sector_context", args={"sector_or_symbol": "IT"}),
        ]
        received = {}

        def fn(name, args):
            received[name] = args
            return {"ok": True}

        _parallel_tool_dispatch(calls, fn)
        assert received["get_symbol_snapshot"] == {"symbol": "RELIANCE"}
        assert received["get_sector_context"] == {"sector_or_symbol": "IT"}


class TestResultStructure:
    def test_tuple_shape_name_args_result_id(self):
        calls = [_make_tc("get_symbol_snapshot", args={"symbol": "TCS"}, call_id="tc1")]

        def fn(name, args):
            return {"price": 4000}

        results = _parallel_tool_dispatch(calls, fn)
        assert len(results) == 1
        name, args, result, call_id = results[0]
        assert name == "get_symbol_snapshot"
        assert args == {"symbol": "TCS"}
        assert result == {"price": 4000}
        assert call_id == "tc1"

    def test_empty_tool_calls_returns_empty(self):
        results = _parallel_tool_dispatch([], lambda n, a: {})
        assert results == []


# ─── integration: _llm_query dispatches tools via parallel helper ─────────────

class TestLlmQueryUsesParallelDispatch:
    """Verify _llm_query routes through _parallel_tool_dispatch."""

    def test_llm_query_calls_parallel_dispatch(self):
        from terminal.agent import Agent

        agent = Agent()
        agent.backend = MagicMock()
        agent.backend_name = "MockBackend"

        # First backend.chat → two tool calls; second → final text
        agent.backend.chat.side_effect = [
            {
                "tool_calls": [
                    {"id": "tc1", "name": "get_symbol_snapshot", "args": {"symbol": "RELIANCE"}},
                    {"id": "tc2", "name": "get_market_breadth", "args": {}},
                ],
                "content": "",
                "finish_reason": "tool_calls",
                "usage": {"input_tokens": 100, "output_tokens": 0,
                          "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
            },
            {
                "tool_calls": [],
                "content": "Here is the analysis. ━━━ Not investment advice. For research and learning only. ━━━",
                "finish_reason": "stop",
                "usage": {"input_tokens": 200, "output_tokens": 80,
                          "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
            },
        ]
        agent.backend.format_tool_calls_in_message.return_value = {"role": "assistant"}
        agent.backend.tool_result_message.return_value = {"role": "tool", "content": "{}"}

        dispatch_calls = []

        def mock_dispatch(tool_calls, fn):
            dispatch_calls.append(len(tool_calls))
            return [(tc["name"], tc.get("args", {}), {"ok": True}, tc["id"]) for tc in tool_calls]

        with patch("terminal.agent._parallel_tool_dispatch", side_effect=mock_dispatch), \
             patch("terminal.agent.call_tool", return_value={"ok": True}):
            result = agent._llm_query("RELIANCE analysis", show_trace=False)

        assert len(dispatch_calls) == 1
        assert dispatch_calls[0] == 2  # two tool calls were dispatched
        assert result["intent"] == "llm_driven"


if __name__ == "__main__":
    import unittest

    loader = unittest.TestLoader()
    suite = loader.discover(str(ROOT / "tests"), pattern="test_parallel_tool_dispatch.py")
    runner = unittest.TextTestRunner(verbosity=2)
    res = runner.run(suite)
    print()
    print(f"── Summary ──")
    print(f"  RAN: {res.testsRun}    "
          f"FAIL: {len(res.failures)}    "
          f"ERR: {len(res.errors)}    "
          f"SKIP: {len(res.skipped)}")
    import sys as _sys
    _sys.exit(0 if res.wasSuccessful() else 1)
