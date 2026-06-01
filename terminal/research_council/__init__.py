"""Research Council package for Agent Adda."""

from __future__ import annotations

from typing import Any


def run_council(objective: str, **flags: Any) -> object:
    from terminal.research_council.engine import run_council as _run_council

    return _run_council(objective, **flags)

__all__ = ["run_council"]
