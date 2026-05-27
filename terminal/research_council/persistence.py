"""Persistence helpers for Research Council artifacts."""

from __future__ import annotations

import os
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from backtesting.strategy_council.types import StrategySpec
from terminal.research_council.schemas import (
    AgentFinding,
    BranchSummary,
    CouncilState,
    CriticReview,
    EvidencePack,
    ExecutionResult,
    Plan,
    StrategyBuildRequest,
    StrategyBuildResult,
)

DEFAULT_DSN = os.environ.get("AGENT_ADDA_PG_DSN") or os.environ.get("PG_DSN") or "dbname=nse_market user=nse_admin host=/tmp"


class ResearchCouncilPersistenceError(RuntimeError):
    pass


def connect(dsn: str | None = None):
    try:
        import psycopg2
    except Exception as exc:
        raise ResearchCouncilPersistenceError(f"psycopg2 unavailable: {exc}") from exc
    return psycopg2.connect(dsn or DEFAULT_DSN)


# Single global advisory key used to serialize all council write transactions.
# Two parallel /council runs were observed to deadlock on
# recommendation_reports.agent_findings inserts because each save_* function
# opens its own transaction and the per-table lock acquisition order varied
# across modes. Acquiring this transaction-scoped lock at the start of every
# save_* transaction queues concurrent writers instead of letting them
# interleave (and dead-lock) on shared indexes / FK rows.
_PERSIST_LOCK_KEY = 0x5243504552534953  # 'RCPERSIS'


def _acquire_persist_lock(cur: Any) -> None:
    """Take the council-wide write lock for the current transaction.

    Released automatically at commit/rollback. Safe no-op against fakes that
    ignore the SELECT.
    """
    try:
        cur.execute("SELECT pg_advisory_xact_lock(%s)", (_PERSIST_LOCK_KEY,))
    except Exception:
        # Tests with non-PG fakes may not implement the function; degrade to
        # best-effort rather than break unit tests.
        pass


def save_evidence_pack(
    pack: EvidencePack,
    *,
    conn: Any | None = None,
    dsn: str | None = None,
) -> dict[str, str]:
    own_conn = conn is None
    conn = conn or connect(dsn)
    payload = pack.to_dict()
    source_trail = [entry.to_dict() for entry in pack.source_trail]
    missing_evidence = [item.to_dict() for item in pack.missing_evidence]
    try:
        with conn.cursor() as cur:
            _acquire_persist_lock(cur)
            cur.execute(
                """
                INSERT INTO recommendation_reports.evidence_packs (
                    pack_id, as_of, mode, universe_filter, symbols,
                    pack_body, source_trail, missing_evidence
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (pack_id) DO UPDATE SET
                    created_at = NOW(),
                    as_of = EXCLUDED.as_of,
                    mode = EXCLUDED.mode,
                    universe_filter = EXCLUDED.universe_filter,
                    symbols = EXCLUDED.symbols,
                    pack_body = EXCLUDED.pack_body,
                    source_trail = EXCLUDED.source_trail,
                    missing_evidence = EXCLUDED.missing_evidence
                """,
                (
                    pack.pack_id,
                    pack.as_of,
                    pack.mode,
                    pack.universe_filter,
                    pack.symbols,
                    _json_param(payload),
                    _json_param(source_trail),
                    _json_param(missing_evidence),
                ),
            )
        conn.commit()
        return {"status": "saved", "pack_id": pack.pack_id, "schema": "recommendation_reports"}
    finally:
        if own_conn:
            conn.close()


def load_evidence_pack(
    pack_id: str,
    *,
    conn: Any | None = None,
    dsn: str | None = None,
) -> EvidencePack | None:
    own_conn = conn is None
    conn = conn or connect(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT pack_body
                FROM recommendation_reports.evidence_packs
                WHERE pack_id = %s
                """,
                (pack_id,),
            )
            row = cur.fetchone()
        if not row:
            return None
        body = _first_column(row, "pack_body")
        return EvidencePack.from_dict(_unwrap_json(body))
    finally:
        if own_conn:
            conn.close()


def persist_research_council_run(run: object) -> dict:
    return {"status": "not_implemented", "run": run}


def save_agent_findings(
    findings: list[AgentFinding],
    *,
    run_id: str,
    iteration: int = 0,
    conn: Any | None = None,
    dsn: str | None = None,
) -> dict[str, Any]:
    own_conn = conn is None
    conn = conn or connect(dsn)
    try:
        with conn.cursor() as cur:
            _acquire_persist_lock(cur)
            for finding in findings:
                persisted_finding_id = f"{run_id}:{finding.finding_id}"
                cur.execute(
                    """
                    INSERT INTO recommendation_reports.agent_findings (
                        finding_id, run_id, agent_name, iteration, stance, confidence, thesis, body
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (finding_id) DO UPDATE SET
                        run_id = EXCLUDED.run_id,
                        agent_name = EXCLUDED.agent_name,
                        iteration = EXCLUDED.iteration,
                        stance = EXCLUDED.stance,
                        confidence = EXCLUDED.confidence,
                        thesis = EXCLUDED.thesis,
                        body = EXCLUDED.body
                    """,
                    (
                        persisted_finding_id,
                        run_id,
                        finding.agent,
                        iteration,
                        finding.stance,
                        finding.confidence,
                        finding.thesis,
                        _json_param(finding.to_dict()),
                    ),
                )
        conn.commit()
        return {"status": "saved", "count": len(findings), "schema": "recommendation_reports"}
    finally:
        if own_conn:
            conn.close()


def save_branch_summaries(
    summaries: list[BranchSummary],
    *,
    run_id: str,
    conn: Any | None = None,
    dsn: str | None = None,
) -> dict[str, Any]:
    own_conn = conn is None
    conn = conn or connect(dsn)
    try:
        with conn.cursor() as cur:
            _acquire_persist_lock(cur)
            for summary in summaries:
                cur.execute(
                    """
                    INSERT INTO recommendation_reports.branch_summaries (
                        summary_id, run_id, branch, stance, body, requires_quant
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (summary_id) DO UPDATE SET
                        stance = EXCLUDED.stance,
                        body = EXCLUDED.body,
                        requires_quant = EXCLUDED.requires_quant
                    """,
                    (
                        summary.summary_id,
                        run_id,
                        summary.branch,
                        summary.stance,
                        _json_param(summary.to_dict()),
                        summary.requires_quant,
                    ),
                )
        conn.commit()
        return {"status": "saved", "count": len(summaries), "schema": "recommendation_reports"}
    finally:
        if own_conn:
            conn.close()


def save_execution_results(
    results: list[ExecutionResult],
    *,
    plan_id: str,
    conn: Any | None = None,
    dsn: str | None = None,
) -> dict[str, Any]:
    own_conn = conn is None
    conn = conn or connect(dsn)
    try:
        with conn.cursor() as cur:
            _acquire_persist_lock(cur)
            for result in results:
                cur.execute(
                    """
                    INSERT INTO recommendation_reports.execution_results (
                        result_id, plan_id, step_id, status, outputs, error, elapsed_ms
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (result_id) DO UPDATE SET
                        status = EXCLUDED.status,
                        outputs = EXCLUDED.outputs,
                        error = EXCLUDED.error,
                        elapsed_ms = EXCLUDED.elapsed_ms
                    """,
                    (
                        result.result_id,
                        plan_id,
                        result.step_id,
                        result.status,
                        _json_param(result.outputs),
                        result.error,
                        result.elapsed_ms,
                    ),
                )
        conn.commit()
        return {"status": "saved", "count": len(results), "schema": "recommendation_reports"}
    finally:
        if own_conn:
            conn.close()


def save_council_run_metadata(
    state: CouncilState,
    *,
    conn: Any | None = None,
    dsn: str | None = None,
) -> dict[str, Any]:
    own_conn = conn is None
    conn = conn or connect(dsn)
    decision = state.decision
    report_path = state.flags.get("markdown_report_path")
    source_trail = [entry.to_dict() for entry in state.evidence_pack.source_trail] if state.evidence_pack else []
    missing_evidence = [item.to_dict() for item in state.decision.missing_evidence] if state.decision else []
    try:
        with conn.cursor() as cur:
            _acquire_persist_lock(cur)
            cur.execute(
                """
                INSERT INTO recommendation_reports.runs (
                    run_id, generated_at, as_of, report_path, evidence_path, recommendation_count,
                    market_regime, source_trail, missing_evidence, council_mode, horizon,
                    risk_budget, universe_filter, evidence_pack_id, plan_iterations,
                    revision_count, final_label, council_status, budgets_remaining
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (run_id) DO UPDATE SET
                    report_path = EXCLUDED.report_path,
                    evidence_path = EXCLUDED.evidence_path,
                    recommendation_count = EXCLUDED.recommendation_count,
                    market_regime = EXCLUDED.market_regime,
                    source_trail = EXCLUDED.source_trail,
                    missing_evidence = EXCLUDED.missing_evidence,
                    council_mode = EXCLUDED.council_mode,
                    horizon = EXCLUDED.horizon,
                    risk_budget = EXCLUDED.risk_budget,
                    universe_filter = EXCLUDED.universe_filter,
                    evidence_pack_id = EXCLUDED.evidence_pack_id,
                    plan_iterations = EXCLUDED.plan_iterations,
                    revision_count = EXCLUDED.revision_count,
                    final_label = EXCLUDED.final_label,
                    council_status = EXCLUDED.council_status,
                    budgets_remaining = EXCLUDED.budgets_remaining
                """,
                (
                    state.run_id,
                    state.created_at,
                    state.evidence_pack.as_of.isoformat() if state.evidence_pack else None,
                    report_path,
                    state.evidence_pack_id,
                    len(decision.candidates) if decision else 0,
                    _json_param((state.evidence_pack.sections.get("market") if state.evidence_pack else {}) or {}),
                    _json_param(source_trail),
                    _json_param(missing_evidence),
                    state.mode,
                    state.horizon,
                    state.risk_budget,
                    state.universe_filter,
                    state.evidence_pack_id,
                    len(state.plans),
                    len(state.revision_history),
                    decision.final_label if decision else None,
                    state.stage,
                    _json_param(state.budgets),
                ),
            )
        conn.commit()
        return {"status": "saved", "run_id": state.run_id, "schema": "recommendation_reports"}
    finally:
        if own_conn:
            conn.close()


def save_council_plans(
    plans: list[Plan],
    *,
    run_id: str,
    conn: Any | None = None,
    dsn: str | None = None,
) -> dict[str, Any]:
    own_conn = conn is None
    conn = conn or connect(dsn)
    try:
        with conn.cursor() as cur:
            _acquire_persist_lock(cur)
            for plan in plans:
                cur.execute(
                    """
                    INSERT INTO recommendation_reports.council_plans (
                        plan_id, run_id, iteration, central_question, steps
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (plan_id) DO UPDATE SET
                        central_question = EXCLUDED.central_question,
                        steps = EXCLUDED.steps
                    """,
                    (
                        plan.plan_id,
                        run_id,
                        plan.iteration,
                        plan.central_question,
                        _json_param([step.to_dict() for step in plan.steps]),
                    ),
                )
        conn.commit()
        return {"status": "saved", "count": len(plans), "schema": "recommendation_reports"}
    finally:
        if own_conn:
            conn.close()


def save_critic_reviews(
    reviews: list[CriticReview],
    *,
    conn: Any | None = None,
    dsn: str | None = None,
) -> dict[str, Any]:
    own_conn = conn is None
    conn = conn or connect(dsn)
    try:
        with conn.cursor() as cur:
            _acquire_persist_lock(cur)
            for review in reviews:
                cur.execute(
                    """
                    INSERT INTO recommendation_reports.critic_reviews (
                        review_id, run_id, iteration, critic, severity_max, findings, summary
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (review_id) DO UPDATE SET
                        severity_max = EXCLUDED.severity_max,
                        findings = EXCLUDED.findings,
                        summary = EXCLUDED.summary
                    """,
                    (
                        review.review_id,
                        review.run_id,
                        review.iteration,
                        review.critic,
                        review.severity_max,
                        _json_param([finding.to_dict() for finding in review.findings]),
                        review.summary,
                    ),
                )
        conn.commit()
        return {"status": "saved", "count": len(reviews), "schema": "recommendation_reports"}
    finally:
        if own_conn:
            conn.close()


def save_strategy_build_artifacts(
    *,
    run_id: str,
    request: StrategyBuildRequest,
    spec: StrategySpec,
    result: StrategyBuildResult,
    conn: Any | None = None,
    dsn: str | None = None,
) -> dict[str, Any]:
    """Persist a validated strategy spec and locked train/validation backtests."""
    own_conn = conn is None
    conn = conn or connect(dsn)
    spec_id = f"{run_id}:{spec.strategy_id}:{spec.horizon_days}"
    splits = {
        split: body
        for split, body in (result.metrics.get("splits") or {}).items()
        if split in {"train", "validation"}
    }
    try:
        with conn.cursor() as cur:
            _acquire_persist_lock(cur)
            cur.execute(
                """
                INSERT INTO recommendation_reports.strategy_specs (
                    spec_id, run_id, strategy_family, hypothesis, body
                )
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (spec_id) DO UPDATE SET
                    strategy_family = EXCLUDED.strategy_family,
                    hypothesis = EXCLUDED.hypothesis,
                    body = EXCLUDED.body
                """,
                (
                    spec_id,
                    run_id,
                    request.strategy_family,
                    request.hypothesis,
                    _json_param({"request": request, "spec": spec, "result": result}),
                ),
            )
            for split, body in splits.items():
                cur.execute(
                    """
                    INSERT INTO recommendation_reports.backtest_results (
                        result_id, spec_id, split, trade_count, win_rate, return_pct,
                        sharpe, max_drawdown_pct, profit_factor, body
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (result_id) DO UPDATE SET
                        trade_count = EXCLUDED.trade_count,
                        win_rate = EXCLUDED.win_rate,
                        return_pct = EXCLUDED.return_pct,
                        sharpe = EXCLUDED.sharpe,
                        max_drawdown_pct = EXCLUDED.max_drawdown_pct,
                        profit_factor = EXCLUDED.profit_factor,
                        body = EXCLUDED.body
                    """,
                    (
                        f"{spec_id}:{split}",
                        spec_id,
                        split,
                        body.get("trade_count"),
                        body.get("win_rate"),
                        body.get("return_pct"),
                        body.get("sharpe"),
                        body.get("max_drawdown_pct"),
                        body.get("profit_factor"),
                        _json_param(body),
                    ),
                )
        conn.commit()
        return {"status": "saved", "spec_id": spec_id, "count": len(splits), "schema": "recommendation_reports"}
    finally:
        if own_conn:
            conn.close()


def _json_param(value: Any) -> Any:
    value = _json_safe(value)
    try:
        from psycopg2.extras import Json
    except Exception:
        return value
    return Json(value)


def _json_safe(value: Any) -> Any:
    if is_dataclass(value):
        return _json_safe(asdict(value))
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _unwrap_json(value: Any) -> Any:
    if hasattr(value, "adapted"):
        return value.adapted
    return value


def _first_column(row: Any, key: str) -> Any:
    if isinstance(row, dict):
        return row[key]
    try:
        return row[key]
    except Exception:
        return row[0]
