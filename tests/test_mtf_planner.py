"""Integration test: ensure the situation-assessment planner branches into MTF
tasks when the user prompt asks for multi-timeframe analysis or a recommendation
report.

This pins the contract regression-tested by the live trace on 2026-05-22:
before this capability, the planner produced only [current-index-status,
db-universe-breadth] for prompts that explicitly asked for MTF + recommendations.
"""

from __future__ import annotations

from terminal.agent import _build_market_situation_assessment_plan


ORIGINAL_FAILING_PROMPT = (
    "If we look at todays eOD data for indices, stocks and sectors and varios "
    "other parameters including multi time frame analysis and technical and "
    "fundamental analysis and create a recommendataion report, first class "
    "grounded >> superpowers"
)


def _task_ids(plan: dict | None) -> list[str]:
    assert plan is not None, "planner returned None"
    return [t["id"] for t in plan["tasks"]]


def test_planner_fires_on_original_failing_prompt():
    plan = _build_market_situation_assessment_plan(ORIGINAL_FAILING_PROMPT)
    assert plan is not None
    ids = _task_ids(plan)
    assert "mtf-universe-scan" in ids
    assert "mtf-top-symbols" in ids
    assert "recommendation-fundamentals" in ids


def test_planner_mtf_scan_uses_scan_tool_with_bullish_default():
    plan = _build_market_situation_assessment_plan(ORIGINAL_FAILING_PROMPT)
    assert plan is not None
    scan_task = next(t for t in plan["tasks"] if t["id"] == "mtf-universe-scan")
    assert scan_task["tool"] == "scan_mtf_aligned"
    assert scan_task["args"]["direction"] == "bullish"
    assert scan_task["args"]["min_score"] >= 50


def test_planner_explicit_mtf_keyword_triggers_branch():
    plan = _build_market_situation_assessment_plan(
        "Show me a multi timeframe view of the market today and top picks"
    )
    assert plan is not None
    ids = _task_ids(plan)
    assert "mtf-universe-scan" in ids
    assert "mtf-top-symbols" in ids


def test_planner_recommendation_report_triggers_branch():
    plan = _build_market_situation_assessment_plan(
        "Build a recommendation report from today's market across indices and sectors"
    )
    assert plan is not None
    ids = _task_ids(plan)
    assert "mtf-universe-scan" in ids


def test_planner_short_intent_triggers_bearish_scan():
    plan = _build_market_situation_assessment_plan(
        "Across timeframes, which nifty stocks look bearish? short list"
    )
    assert plan is not None
    scan_task = next(t for t in plan["tasks"] if t["id"] == "mtf-universe-scan")
    assert scan_task["args"]["direction"] == "bearish"


def test_planner_does_not_fire_mtf_for_simple_status_query():
    plan = _build_market_situation_assessment_plan("How is the nifty doing today?")
    # Regression guard: the original 2-task plan must still come back unchanged
    # for plain status queries — we did not want to balloon every prompt into MTF.
    assert plan is not None
    ids = _task_ids(plan)
    assert "mtf-universe-scan" not in ids
    assert "current-index-status" in ids
    assert "db-universe-breadth" in ids


def test_planner_mtf_tasks_are_grounded_with_fallbacks():
    plan = _build_market_situation_assessment_plan(ORIGINAL_FAILING_PROMPT)
    assert plan is not None
    for task_id in ("mtf-universe-scan", "mtf-top-symbols", "recommendation-fundamentals"):
        task = next(t for t in plan["tasks"] if t["id"] == task_id)
        assert task.get("fallback"), f"{task_id} missing fallback"
        assert task.get("recovery_plan"), f"{task_id} missing recovery_plan"
