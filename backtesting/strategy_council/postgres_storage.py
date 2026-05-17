"""PostgreSQL persistence for Strategy Council simulations."""

from __future__ import annotations

import os
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

import psycopg2
from psycopg2.extras import Json, execute_values

from backtesting.strategy_council.types import BacktestSliceResult, CouncilResult


PG_DSN = os.environ.get("AGENT_ADDA_PG_DSN") or os.environ.get("PG_DSN") or "dbname=nse_market user=nse_admin host=/tmp"


SCHEMA_SQL = """
CREATE SCHEMA IF NOT EXISTS strategy_council;

CREATE TABLE IF NOT EXISTS strategy_council.runs (
    run_id              UUID PRIMARY KEY,
    symbol              TEXT NOT NULL,
    evidence_as_of      TEXT,
    recommendation      TEXT NOT NULL,
    rationale           TEXT,
    report_path         TEXT,
    locked_strategy_id  TEXT,
    locked_horizon_days INTEGER,
    config              JSONB NOT NULL DEFAULT '{}'::jsonb,
    evidence            JSONB NOT NULL DEFAULT '{}'::jsonb,
    locked_strategy     JSONB,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS strategy_council.iterations (
    id                  BIGSERIAL PRIMARY KEY,
    run_id              UUID NOT NULL REFERENCES strategy_council.runs(run_id) ON DELETE CASCADE,
    iteration_index     INTEGER NOT NULL,
    strategist_revision TEXT,
    candidate_count     INTEGER NOT NULL DEFAULT 0,
    train_result_count  INTEGER NOT NULL DEFAULT 0,
    validation_result_count INTEGER NOT NULL DEFAULT 0,
    critique_count      INTEGER NOT NULL DEFAULT 0,
    raw_json            JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (run_id, iteration_index)
);

CREATE TABLE IF NOT EXISTS strategy_council.candidates (
    id                  BIGSERIAL PRIMARY KEY,
    run_id              UUID NOT NULL REFERENCES strategy_council.runs(run_id) ON DELETE CASCADE,
    iteration_index     INTEGER NOT NULL,
    candidate_index     INTEGER NOT NULL,
    strategy_id         TEXT NOT NULL,
    horizon_days        INTEGER NOT NULL,
    status              TEXT,
    origin              TEXT,
    spec                JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (run_id, iteration_index, candidate_index)
);

CREATE TABLE IF NOT EXISTS strategy_council.critiques (
    id                  BIGSERIAL PRIMARY KEY,
    run_id              UUID NOT NULL REFERENCES strategy_council.runs(run_id) ON DELETE CASCADE,
    iteration_index     INTEGER NOT NULL,
    critique_index      INTEGER NOT NULL,
    critic              TEXT NOT NULL,
    verdict             TEXT NOT NULL,
    confidence_delta    NUMERIC(10,6),
    issues              TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    required_changes    TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    raw_json            JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (run_id, iteration_index, critique_index)
);

CREATE TABLE IF NOT EXISTS strategy_council.split_results (
    id                  BIGSERIAL PRIMARY KEY,
    run_id              UUID NOT NULL REFERENCES strategy_council.runs(run_id) ON DELETE CASCADE,
    phase               TEXT NOT NULL,
    iteration_index     INTEGER,
    result_index        INTEGER NOT NULL,
    split               TEXT NOT NULL,
    strategy_id         TEXT NOT NULL,
    horizon_days        INTEGER NOT NULL,
    trade_count         INTEGER NOT NULL DEFAULT 0,
    metrics             JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_strategy_council_runs_symbol_created
    ON strategy_council.runs (symbol, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_strategy_council_candidates_strategy
    ON strategy_council.candidates (strategy_id, horizon_days);
CREATE INDEX IF NOT EXISTS idx_strategy_council_split_results_run
    ON strategy_council.split_results (run_id, phase, split);
"""


def connect(dsn: str | None = None):
    return psycopg2.connect(dsn or PG_DSN)


def ensure_strategy_council_schema(conn, *, commit: bool = True) -> None:
    with conn.cursor() as cur:
        cur.execute(SCHEMA_SQL)
    if commit:
        conn.commit()


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def _split_result_row(
    run_id: Any,
    result: BacktestSliceResult,
    *,
    phase: str,
    iteration_index: int | None,
    result_index: int,
) -> tuple[Any, ...]:
    return (
        run_id,
        phase,
        iteration_index,
        result_index,
        result.split,
        result.strategy_id,
        result.horizon_days,
        result.trade_count,
        Json(_jsonable(result.metrics)),
    )


def persist_council_result(
    result: CouncilResult,
    *,
    conn=None,
    dsn: str | None = None,
) -> dict[str, Any]:
    """Persist one Strategy Council run and its normalized audit trail."""
    run_id = str(uuid4())
    own_conn = conn is None
    db = conn or connect(dsn)
    iteration_values = []
    candidate_values = []
    critique_values = []
    split_values = []

    try:
        ensure_strategy_council_schema(db, commit=False)
        with db.cursor() as cur:
            cur.execute(
                """
                INSERT INTO strategy_council.runs (
                    run_id, symbol, evidence_as_of, recommendation, rationale,
                    report_path, locked_strategy_id, locked_horizon_days,
                    config, evidence, locked_strategy
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    run_id,
                    result.config.symbol,
                    result.evidence.as_of,
                    result.recommendation,
                    result.rationale,
                    result.report_path,
                    result.locked_strategy.strategy_id if result.locked_strategy else None,
                    result.locked_strategy.horizon_days if result.locked_strategy else None,
                    Json(_jsonable(result.config)),
                    Json(_jsonable(result.evidence)),
                    Json(_jsonable(result.locked_strategy)) if result.locked_strategy else None,
                ),
            )

            for iteration in result.iterations:
                iteration_values.append(
                    (
                        run_id,
                        iteration.index,
                        iteration.strategist_revision,
                        len(iteration.candidates),
                        len(iteration.train_results),
                        len(iteration.validation_results),
                        len(iteration.critiques),
                        Json(_jsonable(iteration)),
                    )
                )
                for idx, candidate in enumerate(iteration.candidates):
                    candidate_values.append(
                        (
                            run_id,
                            iteration.index,
                            idx,
                            candidate.strategy_id,
                            candidate.horizon_days,
                            candidate.status,
                            candidate.origin,
                            Json(_jsonable(candidate)),
                        )
                    )
                for idx, critique in enumerate(iteration.critiques):
                    critique_values.append(
                        (
                            run_id,
                            iteration.index,
                            idx,
                            critique.critic,
                            critique.verdict,
                            critique.confidence_delta,
                            list(critique.issues),
                            list(critique.required_changes),
                            Json(_jsonable(critique)),
                        )
                    )
                for idx, split_result in enumerate((*iteration.train_results, *iteration.validation_results)):
                    split_values.append(
                        _split_result_row(
                            run_id,
                            split_result,
                            phase="iteration",
                            iteration_index=iteration.index,
                            result_index=idx,
                        )
                    )

            for idx, split_result in enumerate(result.test_results):
                split_values.append(
                    _split_result_row(
                        run_id,
                        split_result,
                        phase="final_test",
                        iteration_index=None,
                        result_index=idx,
                    )
                )

            if iteration_values:
                execute_values(
                    cur,
                    """
                    INSERT INTO strategy_council.iterations (
                        run_id, iteration_index, strategist_revision, candidate_count,
                        train_result_count, validation_result_count, critique_count, raw_json
                    )
                    VALUES %s
                    """,
                    iteration_values,
                    page_size=200,
                )
            if candidate_values:
                execute_values(
                    cur,
                    """
                    INSERT INTO strategy_council.candidates (
                        run_id, iteration_index, candidate_index, strategy_id,
                        horizon_days, status, origin, spec
                    )
                    VALUES %s
                    """,
                    candidate_values,
                    page_size=500,
                )
            if critique_values:
                execute_values(
                    cur,
                    """
                    INSERT INTO strategy_council.critiques (
                        run_id, iteration_index, critique_index, critic, verdict,
                        confidence_delta, issues, required_changes, raw_json
                    )
                    VALUES %s
                    """,
                    critique_values,
                    page_size=500,
                )
            if split_values:
                execute_values(
                    cur,
                    """
                    INSERT INTO strategy_council.split_results (
                        run_id, phase, iteration_index, result_index, split,
                        strategy_id, horizon_days, trade_count, metrics
                    )
                    VALUES %s
                    """,
                    split_values,
                    page_size=500,
                )

        db.commit()
        return {
            "ok": True,
            "run_id": run_id,
            "schema": "strategy_council",
            "iterations_inserted": len(iteration_values),
            "candidates_inserted": len(candidate_values),
            "critiques_inserted": len(critique_values),
            "split_results_inserted": len(split_values),
        }
    except Exception:
        db.rollback()
        raise
    finally:
        if own_conn:
            db.close()
