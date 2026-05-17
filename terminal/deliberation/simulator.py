"""Scenario simulation helpers for strategy framing."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScenarioResult:
    scenario: str
    implication: str
    action_bias: str


def simulate_scenarios(regime: str = "mixed") -> list[ScenarioResult]:
    regime = (regime or "mixed").lower()
    if "risk_on" in regime or "bull" in regime:
        return [
            ScenarioResult("continuation", "Leaders may extend if breadth confirms.", "trail winners"),
            ScenarioResult("failed_breakout", "Weak breadth can turn breakouts into traps.", "tight stops"),
        ]
    if "risk_off" in regime or "bear" in regime:
        return [
            ScenarioResult("defensive_grind", "Weak breadth favors cash, hedges, and relative-strength leaders.", "reduce risk"),
            ScenarioResult("relief_bounce", "Oversold bounces need confirmation from breadth.", "wait for confirmation"),
        ]
    return [
        ScenarioResult("range", "Mixed evidence favors selectivity.", "trade smaller"),
        ScenarioResult("rotation", "Capital may rotate into narrow leader pockets.", "follow RS leaders"),
    ]
