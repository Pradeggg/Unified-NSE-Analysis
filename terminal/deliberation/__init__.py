"""Deliberation primitives for Agent Adda.

This package keeps planning, hypothesis generation, evidence evaluation,
simulation, memory, and persona rendering separated so agentic flows can be
tested without requiring an LLM round-trip.
"""

from .planner import DeliberationPlan, PlanTask, build_plan
from .hypothesis import Hypothesis, build_hypotheses
from .evaluator import EvidenceScore, evaluate_evidence
from .simulator import ScenarioResult, simulate_scenarios
from .memory import MemoryStore
from .renderer import render_final_answer

__all__ = [
    "DeliberationPlan",
    "PlanTask",
    "build_plan",
    "Hypothesis",
    "build_hypotheses",
    "EvidenceScore",
    "evaluate_evidence",
    "ScenarioResult",
    "simulate_scenarios",
    "MemoryStore",
    "render_final_answer",
]
