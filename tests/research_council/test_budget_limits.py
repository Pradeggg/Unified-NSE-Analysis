"""RC-10.2: Wall-clock budget enforcement tests."""

from __future__ import annotations

import datetime as _dt_mod
from typing import Any

import pytest

from terminal.research_council.engine import initialize_state, run_council
import terminal.research_council.engine as engine_mod


def test_zero_wall_clock_cap_aborts_immediately():
    state = run_council("today swing", dry_run=True, max_wall_clock_s=0)

    assert state.stage == "abort_budget"
    assert state.flags.get("budget_abort") == "wall_clock_s"


def test_very_tight_wall_clock_cap_aborts_during_run(monkeypatch):
    # initialize_state calls datetime.now() once (call 1), then start_time
    # assignment is call 2 — both return real time. Call 3+ jumps by 1000s
    # so the budget check in the first loop iteration sees elapsed > cap.
    fake = _FakeDatetime(setup_calls=2, jump_s=1000)
    monkeypatch.setattr(engine_mod, "datetime", fake)

    result = run_council("today swing", dry_run=True, max_wall_clock_s=1)

    assert result.stage == "abort_budget"
    assert result.flags.get("budget_abort") == "wall_clock_s"
    assert result.budgets.get("remaining_wall_clock_s") == 0


def test_budget_tracks_elapsed_and_remaining():
    state = run_council("today swing", dry_run=True, max_wall_clock_s=480)

    assert "elapsed_s" in state.budgets
    assert "remaining_wall_clock_s" in state.budgets
    assert state.budgets["elapsed_s"] >= 0
    assert state.budgets["remaining_wall_clock_s"] >= 0


def test_initialize_state_sets_budget_from_profile():
    state = initialize_state("today swing")

    assert "wall_clock_s" in state.budgets
    assert state.budgets["wall_clock_s"] > 0
    assert "tokens" in state.budgets


def test_initialize_state_respects_max_wall_clock_s_override():
    state = initialize_state("today swing", max_wall_clock_s=120)

    assert state.budgets["wall_clock_s"] == 120


class _FakeDatetime:
    """Replaces `datetime` in engine_mod for testing budget enforcement.

    The first `setup_calls` calls return real time (covering initialize_state
    and start_time assignment inside run_council). Subsequent calls return
    base_time + timedelta(jump_s), so elapsed >> cap.
    """

    def __init__(self, setup_calls: int, jump_s: float) -> None:
        self._setup_calls = setup_calls
        self._jump_s = jump_s
        self._call = 0
        self._base: Any = None

    def now(self) -> _dt_mod.datetime:
        self._call += 1
        real = _dt_mod.datetime.now()
        if self._call <= self._setup_calls:
            self._base = real
            return real
        assert self._base is not None
        return self._base + _dt_mod.timedelta(seconds=self._jump_s)

    def __getattr__(self, name: str) -> Any:
        return getattr(_dt_mod.datetime, name)
