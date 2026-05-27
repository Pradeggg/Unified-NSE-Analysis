"""Regression tests for AA-COUNCIL-LOCK: concurrent /council runs must not deadlock.

The fix introduces a Postgres advisory transaction lock at the top of every
research-council save_* transaction. We verify here that:

  1. The advisory lock SQL is executed before any INSERT inside each save_*
     function (so concurrent runs serialize instead of dead-locking on
     shared indexes / FKs).
  2. The lock key is shared (single global key) so ALL council writes
     queue against each other, not just same-table writes.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import pytest

from terminal.research_council.persistence import (
    _PERSIST_LOCK_KEY,
    save_agent_findings,
    save_branch_summaries,
    save_council_plans,
    save_council_run_metadata,
    save_critic_reviews,
    save_evidence_pack,
    save_execution_results,
)
from terminal.research_council.schemas import (
    AgentFinding,
    BranchSummary,
    CouncilState,
    CriticFinding,
    CriticReview,
    EvidencePack,
    ExecutionResult,
    Plan,
    PlanStep,
    ToolCall,
)


class RecordingCursor:
    """Captures the order of SQL statements without executing anything."""

    def __init__(self, conn: "RecordingConnection") -> None:
        self.conn = conn

    def __enter__(self) -> "RecordingCursor":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        return False

    def execute(self, sql: str, params: Any = None) -> None:
        self.conn.calls.append((sql.strip().split("\n", 1)[0].strip(), params))


class RecordingConnection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []
        self.committed = 0

    def cursor(self) -> RecordingCursor:
        return RecordingCursor(self)

    def commit(self) -> None:
        self.committed += 1

    def close(self) -> None:
        pass


def _assert_lock_before_insert(conn: RecordingConnection, table: str) -> None:
    sqls = [s for s, _ in conn.calls]
    lock_idx = next((i for i, s in enumerate(sqls) if "pg_advisory_xact_lock" in s), None)
    insert_idx = next((i for i, s in enumerate(sqls) if table in s), None)
    assert lock_idx is not None, f"advisory lock missing before {table}"
    assert insert_idx is not None, f"INSERT for {table} missing"
    assert lock_idx < insert_idx, (
        f"advisory lock (idx {lock_idx}) must precede INSERT into {table} (idx {insert_idx})"
    )


def _lock_param_value(conn: RecordingConnection) -> Any:
    for sql, params in conn.calls:
        if "pg_advisory_xact_lock" in sql:
            return params[0] if params else None
    raise AssertionError("no advisory-lock call recorded")


def test_save_evidence_pack_acquires_lock_before_insert() -> None:
    pack = EvidencePack(
        pack_id="ep_test",
        as_of=date(2026, 5, 27),
        mode="market_council",
        universe_filter="liquid",
        symbols=[],
        sections={},
    )
    conn = RecordingConnection()
    save_evidence_pack(pack, conn=conn)
    _assert_lock_before_insert(conn, "recommendation_reports.evidence_packs")
    assert _lock_param_value(conn) == _PERSIST_LOCK_KEY


def test_save_agent_findings_acquires_lock_before_insert() -> None:
    finding = AgentFinding(
        finding_id="af_test",
        agent="macro_regime",
        stance="neutral",
        confidence=0.5,
        thesis="t",
    )
    conn = RecordingConnection()
    save_agent_findings([finding], run_id="run_test", conn=conn)
    _assert_lock_before_insert(conn, "recommendation_reports.agent_findings")


def test_save_branch_summaries_acquires_lock_before_insert() -> None:
    summary = BranchSummary(
        summary_id="bs_test",
        branch="momentum_leadership",
        stance="neutral",
    )
    conn = RecordingConnection()
    save_branch_summaries([summary], run_id="run_test", conn=conn)
    _assert_lock_before_insert(conn, "recommendation_reports.branch_summaries")


def test_save_execution_results_acquires_lock_before_insert() -> None:
    result = ExecutionResult(
        result_id="er_test",
        step_id="s1",
        status="success",
        outputs={},
        error=None,
        elapsed_ms=1,
    )
    conn = RecordingConnection()
    save_execution_results([result], plan_id="p_test", conn=conn)
    _assert_lock_before_insert(conn, "recommendation_reports.execution_results")


def test_save_council_run_metadata_acquires_lock_before_insert() -> None:
    state = CouncilState(
        run_id="run_test",
        session_id="sess_test",
        created_at=datetime(2026, 5, 27, 0, 0, 0),
        mode="market_council",
        stage="intake",
        objective="test",
        horizon="swing",
        risk_budget="moderate",
        universe_filter="liquid",
    )
    conn = RecordingConnection()
    save_council_run_metadata(state, conn=conn)
    _assert_lock_before_insert(conn, "recommendation_reports.runs")


def test_save_council_plans_acquires_lock_before_insert() -> None:
    plan = Plan(
        plan_id="p_test",
        run_id="run_test",
        iteration=0,
        central_question="q",
        steps=[
            PlanStep(
                step_id="s1",
                sequence=0,
                question="q1",
                tool_calls=[ToolCall(tool_name="regime.detect")],
            )
        ],
    )
    conn = RecordingConnection()
    save_council_plans([plan], run_id="run_test", conn=conn)
    _assert_lock_before_insert(conn, "recommendation_reports.council_plans")


def test_save_critic_reviews_acquires_lock_before_insert() -> None:
    review = CriticReview(
        review_id="cr_test",
        critic="data_quality",
        run_id="run_test",
        iteration=0,
        severity_max="info",
        findings=[
            CriticFinding(
                finding_id="cf_test",
                severity="info",
                target={"kind": "plan"},
                description="ok",
                recommendation="continue",
            )
        ],
        summary="ok",
    )
    conn = RecordingConnection()
    save_critic_reviews([review], conn=conn)
    _assert_lock_before_insert(conn, "recommendation_reports.critic_reviews")


def test_all_save_functions_share_same_lock_key() -> None:
    """All council writers must use the SAME advisory key so they queue
    against each other. Different keys would not serialize."""
    pack = EvidencePack(
        pack_id="ep_k",
        as_of=date(2026, 5, 27),
        mode="market_council",
        universe_filter="liquid",
        symbols=[],
        sections={},
    )
    finding = AgentFinding(
        finding_id="af_k", agent="macro_regime", stance="neutral", confidence=0.5, thesis="t"
    )

    conn_a = RecordingConnection()
    save_evidence_pack(pack, conn=conn_a)
    conn_b = RecordingConnection()
    save_agent_findings([finding], run_id="r_k", conn=conn_b)

    assert _lock_param_value(conn_a) == _lock_param_value(conn_b) == _PERSIST_LOCK_KEY
