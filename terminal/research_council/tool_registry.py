"""Logical Research Council tool registry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from terminal.research_council import tool_adapters


@dataclass(frozen=True)
class ToolSpec:
    name: str
    adapter: Callable[..., object]


class ToolNotRegistered(KeyError):
    def __init__(self, tool_name: str):
        super().__init__(tool_name)
        self.tool_name = tool_name

    def to_result(self) -> dict[str, str | bool]:
        return {"ok": False, "error": "tool_not_registered", "tool_name": self.tool_name}


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, name: str, adapter: Callable[..., object]) -> None:
        self._tools[name] = ToolSpec(name=name, adapter=adapter)

    def resolve(self, name: str) -> Callable[..., object]:
        try:
            return self._tools[name].adapter
        except KeyError as exc:
            raise ToolNotRegistered(name) from exc

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._tools))


def build_default_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register("regime.detect", tool_adapters.regime_detect)
    registry.register("breadth.summarize", tool_adapters.breadth_summarize)
    registry.register("flows.fii_dii_5d", tool_adapters.flows_fii_dii_5d)
    registry.register("macro.proxy_signals", tool_adapters.macro_proxy_signals)
    registry.register("sector.rs_ranking", tool_adapters.sector_rs_ranking)
    registry.register("sector.breadth_health", tool_adapters.sector_breadth_health)
    registry.register("sector.top_stocks", tool_adapters.sector_top_stocks)
    registry.register("screen.stage2", tool_adapters.screen_stage2)
    registry.register("screen.high_rs", tool_adapters.screen_high_rs)
    registry.register("screen.momentum_52w", tool_adapters.screen_momentum_52w)
    registry.register("fund.results_trend", tool_adapters.fund_results_trend)
    registry.register("fund.balance_sheet_health", tool_adapters.fund_balance_sheet_health)
    registry.register("events.upcoming", tool_adapters.events_upcoming)
    registry.register("fno.buildup", tool_adapters.fno_buildup)
    registry.register("strategy.build", tool_adapters.strategy_build)
    return registry


DEFAULT_REGISTRY = build_default_registry()
