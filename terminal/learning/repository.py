from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping, Sequence


SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "bearer",
    "cookie",
    "password",
    "secret",
    "token",
}
OVERSIZED_KEYS = {"raw_tool_payload", "html", "email_body", "attachment_bytes"}
PROPOSAL_STATUSES = frozenset(
    {
        "observed",
        "proposed",
        "generated",
        "test_failed",
        "review_pending",
        "validated",
        "production",
        "deprecated",
    }
)


@dataclass(frozen=True)
class LearningRepository:
    conn: Any | None = None
    dsn: str | None = None
    connect_fn: Any | None = None

    def _connect(self) -> Any:
        if self.conn is not None:
            return self.conn
        if self.connect_fn is not None:
            return self.connect_fn(self.dsn)
        import psycopg2

        return psycopg2.connect(self.dsn)

    def _commit(self, conn: Any) -> None:
        commit = getattr(conn, "commit", None)
        if callable(commit):
            commit()

    def _row_to_dict(self, cursor: Any, row: Any) -> dict[str, Any] | None:
        if row is None:
            return None
        if isinstance(row, dict):
            return dict(row)
        description = getattr(cursor, "description", None) or []
        names = [column[0] for column in description]
        if names:
            return dict(zip(names, row))
        if isinstance(row, Sequence) and len(row) == 1 and isinstance(row[0], dict):
            return dict(row[0])
        raise TypeError("database row cannot be converted to dict")

    def _fetchone_dict(self, cursor: Any) -> dict[str, Any] | None:
        return self._row_to_dict(cursor, cursor.fetchone())

    def _fetchall_dicts(self, cursor: Any) -> list[dict[str, Any]]:
        return [row for row in (self._row_to_dict(cursor, item) for item in cursor.fetchall()) if row is not None]

    def list_interaction_events(self, *, start_date: Any, end_date: Any | None = None) -> list[dict[str, Any]]:
        conn = self._connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM agent_learning.interaction_events
                WHERE event_ts::date >= %s
                  AND event_ts::date <= %s
                ORDER BY event_ts ASC, event_id ASC
                """,
                (start_date, end_date or start_date),
            )
            return self._fetchall_dicts(cur)

    def list_workflow_chains(self, *, start_date: Any, end_date: Any | None = None) -> list[dict[str, Any]]:
        conn = self._connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM agent_learning.workflow_chains
                WHERE started_at::date >= %s
                  AND started_at::date <= %s
                ORDER BY started_at ASC, chain_id ASC
                """,
                (start_date, end_date or start_date),
            )
            return self._fetchall_dicts(cur)

    def list_patterns(self, *, status: str | None = None, limit: int | None = None) -> list[dict[str, Any]]:
        conn = self._connect()
        params: list[Any] = []
        sql = """
            SELECT *
            FROM agent_learning.patterns
        """
        if status is not None:
            sql += " WHERE status = %s"
            params.append(status)
        sql += " ORDER BY last_seen_at DESC NULLS LAST, pattern_id DESC"
        if limit is not None:
            sql += " LIMIT %s"
            params.append(int(limit))
        with conn.cursor() as cur:
            cur.execute(sql, tuple(params))
            return self._fetchall_dicts(cur)

    def record_interaction_event(self, event: Mapping[str, Any]) -> int:
        payload = json.dumps(_sanitize_payload(dict(event.get("payload") or {})))
        conn = self._connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO agent_learning.interaction_events (
                    raw_query, normalized_query, selected_intent, route_type,
                    detected_entities, tools_executed, artifacts, errors,
                    missing_evidence, payload
                )
                VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb)
                RETURNING event_id
                """,
                (
                    event.get("raw_query"),
                    event.get("normalized_query"),
                    event.get("selected_intent"),
                    event.get("route_type"),
                    json.dumps(_sanitize_payload(event.get("detected_entities") or [])),
                    json.dumps(_sanitize_payload(event.get("tools_executed") or [])),
                    json.dumps(_sanitize_payload(event.get("artifacts") or [])),
                    json.dumps(_sanitize_payload(event.get("errors") or [])),
                    json.dumps(_sanitize_payload(event.get("missing_evidence") or [])),
                    payload,
                ),
            )
            row = self._fetchone_dict(cur)
        self._commit(conn)
        return int(row["event_id"])

    def record_workflow_chain(self, chain: Mapping[str, Any]) -> int:
        conn = self._connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO agent_learning.workflow_chains (
                    chain_key, ended_at, event_ids, chain_payload
                )
                VALUES (%s, %s, %s, %s::jsonb)
                RETURNING chain_id
                """,
                (
                    str(chain.get("chain_key") or ""),
                    chain.get("ended_at"),
                    list(chain.get("events") or chain.get("event_ids") or []),
                    json.dumps(_sanitize_payload(chain.get("chain_payload") or chain.get("payload") or {})),
                ),
            )
            row = self._fetchone_dict(cur)
        self._commit(conn)
        return int(row["chain_id"])

    def save_daily_summary(self, summary: Mapping[str, Any]) -> int:
        conn = self._connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO agent_learning.daily_summaries (summary_date, summary_payload)
                VALUES (%s, %s::jsonb)
                ON CONFLICT (summary_date) DO UPDATE SET
                    summary_payload = EXCLUDED.summary_payload,
                    created_at = NOW()
                RETURNING summary_id
                """,
                (
                    summary.get("summary_date"),
                    json.dumps(_sanitize_payload(summary.get("summary_payload") or summary.get("payload") or {})),
                ),
            )
            row = self._fetchone_dict(cur)
        self._commit(conn)
        return int(row["summary_id"])

    def save_pattern(self, pattern: Mapping[str, Any]) -> int:
        conn = self._connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO agent_learning.patterns (pattern_key, status, pattern_payload)
                VALUES (%s, %s, %s::jsonb)
                ON CONFLICT (pattern_key) DO UPDATE SET
                    status = EXCLUDED.status,
                    pattern_payload = EXCLUDED.pattern_payload,
                    last_seen_at = NOW()
                RETURNING pattern_id
                """,
                (
                    str(pattern.get("pattern_key") or ""),
                    str(pattern.get("status") or "observed"),
                    json.dumps(_sanitize_payload(pattern.get("pattern_payload") or pattern.get("payload") or {})),
                ),
            )
            row = self._fetchone_dict(cur)
        self._commit(conn)
        return int(row["pattern_id"])

    def save_proposal(self, proposal: Mapping[str, Any]) -> int:
        status = str(proposal.get("status") or "observed")
        if status not in PROPOSAL_STATUSES:
            raise ValueError(f"invalid proposal status: {status}")
        conn = self._connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO agent_learning.proposals (
                    proposal_type, title, status, source_pattern_id, proposal_payload
                )
                VALUES (%s, %s, %s, %s, %s::jsonb)
                RETURNING proposal_id
                """,
                (
                    str(proposal.get("proposal_type") or ""),
                    str(proposal.get("title") or ""),
                    status,
                    proposal.get("source_pattern_id"),
                    json.dumps(_sanitize_payload(proposal.get("proposal_payload") or proposal.get("payload") or {})),
                ),
            )
            row = self._fetchone_dict(cur)
        self._commit(conn)
        return int(row["proposal_id"])

    def list_proposals(self, status: str | None = None) -> list[dict[str, Any]]:
        if status is not None and status not in PROPOSAL_STATUSES:
            raise ValueError(f"invalid proposal status: {status}")
        conn = self._connect()
        if status is None:
            sql = """
                SELECT *
                FROM agent_learning.proposals
                ORDER BY updated_at DESC NULLS LAST, proposal_id DESC
            """
            params: tuple[Any, ...] = ()
        else:
            sql = """
                SELECT *
                FROM agent_learning.proposals
                WHERE status = %s
                ORDER BY updated_at DESC NULLS LAST, proposal_id DESC
            """
            params = (status,)
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return self._fetchall_dicts(cur)

    def get_proposal(self, proposal_id: int) -> dict[str, Any] | None:
        conn = self._connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM agent_learning.proposals
                WHERE proposal_id = %s
                """,
                (proposal_id,),
            )
            return self._fetchone_dict(cur)

    def update_proposal_status(self, proposal_id: int, status: str) -> int:
        if status not in PROPOSAL_STATUSES:
            raise ValueError(f"invalid proposal status: {status}")
        conn = self._connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE agent_learning.proposals
                SET status = %s,
                    updated_at = NOW()
                WHERE proposal_id = %s
                RETURNING proposal_id
                """,
                (status, proposal_id),
            )
            row = self._fetchone_dict(cur)
        self._commit(conn)
        return int(row["proposal_id"])

    def record_proposal_validation_run(self, run: Mapping[str, Any]) -> int:
        conn = self._connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO agent_learning.proposal_validation_runs (
                    proposal_id, status_before, status_after, checks, findings
                )
                VALUES (%s, %s, %s, %s::jsonb, %s::jsonb)
                RETURNING validation_run_id
                """,
                (
                    run.get("proposal_id"),
                    run.get("status_before"),
                    run.get("status_after"),
                    json.dumps(_sanitize_payload(run.get("checks") or [])),
                    json.dumps(_sanitize_payload(run.get("findings") or [])),
                ),
            )
            row = self._fetchone_dict(cur)
        self._commit(conn)
        return int(row["validation_run_id"])

    def record_promotion_run(self, run: Mapping[str, Any]) -> int:
        conn = self._connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO agent_learning.promotion_runs (
                    proposal_id, status, promotion_payload
                )
                VALUES (%s, %s, %s::jsonb)
                RETURNING promotion_run_id
                """,
                (
                    run.get("proposal_id"),
                    str(run.get("status") or ""),
                    json.dumps(_sanitize_payload(run.get("promotion_payload") or run.get("payload") or {})),
                ),
            )
            row = self._fetchone_dict(cur)
        self._commit(conn)
        return int(row["promotion_run_id"])

    def list_promotion_runs(self, *, limit: int | None = None) -> list[dict[str, Any]]:
        conn = self._connect()
        sql = """
            SELECT *
            FROM agent_learning.promotion_runs
            ORDER BY created_at DESC, promotion_run_id DESC
        """
        params: tuple[Any, ...] = ()
        if limit is not None:
            sql += " LIMIT %s"
            params = (int(limit),)
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return self._fetchall_dicts(cur)

    def record_learning_audit(self, audit: Mapping[str, Any]) -> int:
        conn = self._connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO agent_learning.learning_audits (audit_type, audit_payload)
                VALUES (%s, %s::jsonb)
                RETURNING audit_id
                """,
                (
                    str(audit.get("audit_type") or ""),
                    json.dumps(_sanitize_payload(audit.get("audit_payload") or audit.get("payload") or {})),
                ),
            )
            row = self._fetchone_dict(cur)
        self._commit(conn)
        return int(row["audit_id"])


def _sanitize_payload(value: Any) -> Any:
    if isinstance(value, Mapping):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            lowered = key_text.lower()
            if lowered in SENSITIVE_KEYS or any(token in lowered for token in SENSITIVE_KEYS):
                continue
            if lowered in OVERSIZED_KEYS:
                continue
            sanitized[key_text] = _sanitize_payload(item)
        return sanitized
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_sanitize_payload(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)
