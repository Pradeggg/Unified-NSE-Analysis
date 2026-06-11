from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Sequence


RUNTIME_STATUSES = ("validated", "production")
EMBEDDING_DIMENSION = 384
DEFAULT_PG_DSN = "dbname=nse_market user=nse_admin host=/tmp"


def default_skill_store_dsn() -> str:
    return os.environ.get("AGENT_ADDA_PG_DSN") or os.environ.get("PG_DSN") or DEFAULT_PG_DSN


@dataclass(frozen=True)
class SkillStoreRepository:
    conn: Any | None = None
    dsn: str | None = None
    connect_fn: Callable[[str | None], Any] | None = None

    def __post_init__(self) -> None:
        if self.conn is None and self.dsn is None:
            object.__setattr__(self, "dsn", default_skill_store_dsn())

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

    def _execute_fetchone(self, sql: str, params: tuple[Any, ...]) -> dict[str, Any] | None:
        conn = self._connect()
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return self._fetchone_dict(cur)

    def upsert_skill_card(self, card: dict[str, Any]) -> dict[str, Any]:
        skill_id = str(card["id"])
        version = int(card.get("version") or 1)
        params = (
            skill_id,
            version,
            str(card.get("status") or "generated"),
            str(card["domain"]),
            str(card["title"]),
            str(card["description"]),
            list(card.get("input_patterns") or []),
            list(card.get("tags") or []),
            json.dumps(card.get("evidence_required") or {}),
            json.dumps(card.get("tool_plan_template") or []),
            list(card.get("output_contract") or []),
            list(card.get("validation_rules") or []),
            card.get("synthesis_guidance"),
            json.dumps(card),
            card.get("generation_model"),
            card.get("created_by"),
        )
        conn = self._connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO agent_skills.skill_cards (
                    id, version, status, domain, title, description,
                    input_patterns, tags, evidence_required, tool_plan_template,
                    output_contract, validation_rules, synthesis_guidance,
                    card_payload, generation_model, created_by
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s::jsonb, %s::jsonb,
                    %s, %s, %s,
                    %s::jsonb, %s, %s
                )
                ON CONFLICT (id, version) DO UPDATE SET
                    status = EXCLUDED.status,
                    domain = EXCLUDED.domain,
                    title = EXCLUDED.title,
                    description = EXCLUDED.description,
                    input_patterns = EXCLUDED.input_patterns,
                    tags = EXCLUDED.tags,
                    evidence_required = EXCLUDED.evidence_required,
                    tool_plan_template = EXCLUDED.tool_plan_template,
                    output_contract = EXCLUDED.output_contract,
                    validation_rules = EXCLUDED.validation_rules,
                    synthesis_guidance = EXCLUDED.synthesis_guidance,
                    card_payload = EXCLUDED.card_payload,
                    generation_model = EXCLUDED.generation_model,
                    created_by = EXCLUDED.created_by,
                    updated_at = NOW()
                RETURNING *
                """,
                params,
            )
            row = self._fetchone_dict(cur)
        self._commit(conn)
        self._upsert_sql_templates(card)
        if row is None:
            raise RuntimeError(f"upsert returned no row for skill {skill_id} v{version}")
        return row

    def _upsert_sql_templates(self, card: dict[str, Any]) -> None:
        templates = card.get("sql_templates") or []
        if not templates:
            return
        if not isinstance(templates, list):
            raise ValueError("sql_templates must be a list")
        skill_id = str(card["id"])
        version = int(card.get("version") or 1)
        conn = self._connect()
        with conn.cursor() as cur:
            for index, template in enumerate(templates, 1):
                if not isinstance(template, dict):
                    raise ValueError("sql template must be an object")
                name = str(
                    template.get("name")
                    or template.get("template_name")
                    or template.get("id")
                    or f"template_{index}"
                )
                sql_text = str(template.get("sql_text") or template.get("sql") or template.get("template") or template.get("query") or "")
                if not sql_text:
                    raise ValueError(f"sql template {name} is missing sql_text")
                cur.execute(
                    """
                    INSERT INTO agent_skills.skill_sql_templates (
                        skill_id, skill_version, template_name, sql_text,
                        required_params, expected_columns, row_limit,
                        safety_status, safety_findings
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                    ON CONFLICT (skill_id, skill_version, template_name) DO UPDATE SET
                        sql_text = EXCLUDED.sql_text,
                        required_params = EXCLUDED.required_params,
                        expected_columns = EXCLUDED.expected_columns,
                        row_limit = EXCLUDED.row_limit,
                        safety_status = EXCLUDED.safety_status,
                        safety_findings = EXCLUDED.safety_findings,
                        updated_at = NOW()
                    """,
                    (
                        skill_id,
                        version,
                        name,
                        sql_text,
                        list(template.get("required_params") or []),
                        list(template.get("expected_columns") or []),
                        int(template.get("row_limit") or 500),
                        str(template.get("safety_status") or "pending"),
                        json.dumps(template.get("safety_findings") or []),
                    ),
                )
        self._commit(conn)

    def get_skill_card(self, skill_id: str, version: int | None = None) -> dict[str, Any] | None:
        if version is None:
            return self._execute_fetchone(
                """
                SELECT *
                FROM agent_skills.skill_cards
                WHERE id = %s
                ORDER BY version DESC
                LIMIT 1
                """,
                (skill_id,),
            )
        return self._execute_fetchone(
            """
            SELECT *
            FROM agent_skills.skill_cards
            WHERE id = %s AND version = %s
            LIMIT 1
            """,
            (skill_id, version),
        )

    def get_sql_template(self, skill_id: str, template_name: str, version: int | None = None) -> dict[str, Any] | None:
        if version is None:
            return self._execute_fetchone(
                """
                SELECT *
                FROM agent_skills.skill_sql_templates
                WHERE skill_id = %s AND template_name = %s
                ORDER BY skill_version DESC
                LIMIT 1
                """,
                (skill_id, template_name),
            )
        return self._execute_fetchone(
            """
            SELECT *
            FROM agent_skills.skill_sql_templates
            WHERE skill_id = %s AND skill_version = %s AND template_name = %s
            LIMIT 1
            """,
            (skill_id, version, template_name),
        )

    def search_embedding_candidates(
        self,
        vector: Iterable[float],
        *,
        top_n: int = 30,
        domain: str | None = None,
        model: str | None = None,
    ) -> list[dict[str, Any]]:
        values = [float(item) for item in vector]
        if len(values) != EMBEDDING_DIMENSION:
            raise ValueError(f"embedding dimension must be {EMBEDDING_DIMENSION}")
        vector_literal = "[" + ",".join(f"{value:.12g}" for value in values) + "]"
        conn = self._connect()
        filters = ["c.status = ANY(%s)"]
        filter_params: list[Any] = [list(RUNTIME_STATUSES)]
        if domain:
            filters.append("c.domain = %s")
            filter_params.append(domain)
        if model:
            filters.append("e.embedding_model = %s")
            filter_params.append(model)
        where_sql = " AND ".join(filters)
        params = tuple([vector_literal, *filter_params, vector_literal, int(top_n)])
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    c.id,
                    c.version,
                    c.status,
                    c.domain,
                    c.title,
                    c.tags,
                    c.input_patterns,
                    1 - (e.embedding <=> %s::vector) AS vector_score
                FROM agent_skills.skill_embeddings AS e
                JOIN agent_skills.skill_cards AS c
                  ON c.id = e.skill_id
                 AND c.version = e.skill_version
                WHERE {where_sql}
                ORDER BY e.embedding <=> %s::vector
                LIMIT %s
                """,
                params,
            )
            return self._fetchall_dicts(cur)

    def search_vector_candidates(
        self,
        vector: Iterable[float],
        model: str,
        *,
        limit: int = 30,
        statuses: Sequence[str] = RUNTIME_STATUSES,
    ) -> list[dict[str, Any]]:
        if tuple(statuses) != tuple(RUNTIME_STATUSES):
            raise ValueError("skill vector search only supports runtime-eligible statuses")
        rows = self.search_embedding_candidates(vector, top_n=limit, model=model)
        normalized = []
        for row in rows:
            item = dict(row)
            item.setdefault("skill_id", item.get("id"))
            normalized.append(item)
        return normalized

    def list_runtime_eligible(self, domain: str | None = None) -> list[dict[str, Any]]:
        conn = self._connect()
        params: tuple[Any, ...]
        if domain:
            sql = """
                SELECT *
                FROM agent_skills.skill_cards
                WHERE status = ANY(%s) AND domain = %s
                ORDER BY id, version DESC
            """
            params = (list(RUNTIME_STATUSES), domain)
        else:
            sql = """
                SELECT *
                FROM agent_skills.skill_cards
                WHERE status = ANY(%s)
                ORDER BY id, version DESC
            """
            params = (list(RUNTIME_STATUSES),)
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return self._fetchall_dicts(cur)

    def list_skill_cards(self, status: str | None = None, domain: str | None = None) -> list[dict[str, Any]]:
        conn = self._connect()
        filters: list[str] = []
        params: list[Any] = []
        if status:
            filters.append("status = %s")
            params.append(status)
        if domain:
            filters.append("domain = %s")
            params.append(domain)
        where = "WHERE " + " AND ".join(filters) if filters else ""
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT *
                FROM agent_skills.skill_cards
                {where}
                ORDER BY updated_at DESC NULLS LAST, id, version DESC
                """,
                tuple(params),
            )
            return self._fetchall_dicts(cur)

    def save_embedding(
        self,
        skill_id: str,
        model: str,
        dimension: int,
        vector: Iterable[float],
        embedding_text: str,
        *,
        version: int = 1,
    ) -> dict[str, Any]:
        values = [float(item) for item in vector]
        if len(values) != dimension:
            raise ValueError("embedding dimension does not match vector length")
        if dimension != EMBEDDING_DIMENSION:
            raise ValueError(f"embedding dimension must be {EMBEDDING_DIMENSION}")
        vector_literal = "[" + ",".join(f"{value:.12g}" for value in values) + "]"
        conn = self._connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO agent_skills.skill_embeddings (
                    skill_id, skill_version, embedding_model,
                    embedding_dimension, embedding_text, embedding
                )
                VALUES (%s, %s, %s, %s, %s, %s::vector)
                ON CONFLICT (skill_id, skill_version, embedding_model) DO UPDATE SET
                    embedding_dimension = EXCLUDED.embedding_dimension,
                    embedding_text = EXCLUDED.embedding_text,
                    embedding = EXCLUDED.embedding,
                    created_at = NOW()
                RETURNING embedding_id, skill_id, skill_version, embedding_model, embedding_dimension, embedding_text
                """,
                (skill_id, version, model, dimension, embedding_text, vector_literal),
            )
            row = self._fetchone_dict(cur)
        self._commit(conn)
        if row is None:
            raise RuntimeError(f"embedding upsert returned no row for skill {skill_id} v{version}")
        return row

    def log_retrieval(self, event: dict[str, Any]) -> int | None:
        return self._insert_log_returning_id(
            """
            INSERT INTO agent_skills.skill_retrieval_logs (
                query_hash, normalized_query, selected_skill_id, selected_version,
                candidates, reviewer_decision, elapsed_ms, metadata
            )
            VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s::jsonb)
            RETURNING retrieval_id
            """,
            (
                str(event["query_hash"]),
                event.get("normalized_query"),
                event.get("selected_skill_id"),
                event.get("selected_version"),
                json.dumps(event.get("candidates") or []),
                json.dumps(event.get("reviewer_decision") or {}),
                event.get("elapsed_ms"),
                json.dumps(event.get("metadata") or {}),
            ),
            "retrieval_id",
        )

    def log_execution(self, event: dict[str, Any]) -> int | None:
        return self._insert_log_returning_id(
            """
            INSERT INTO agent_skills.skill_execution_logs (
                retrieval_id, skill_id, skill_version, steps,
                validation_status, validation_findings, elapsed_ms, metadata
            )
            VALUES (%s, %s, %s, %s::jsonb, %s, %s::jsonb, %s, %s::jsonb)
            RETURNING execution_id
            """,
            (
                event.get("retrieval_id"),
                str(event["skill_id"]),
                int(event.get("skill_version") or 1),
                json.dumps(event.get("steps") or []),
                str(event["validation_status"]),
                json.dumps(event.get("validation_findings") or []),
                event.get("elapsed_ms"),
                json.dumps(event.get("metadata") or {}),
            ),
            "execution_id",
        )

    def save_feedback(self, event: dict[str, Any]) -> int | None:
        return self._insert_log_returning_id(
            """
            INSERT INTO agent_skills.skill_feedback (
                retrieval_id, execution_id, skill_id, skill_version,
                feedback_type, feedback_payload, created_by
            )
            VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s)
            RETURNING feedback_id
            """,
            (
                event.get("retrieval_id"),
                event.get("execution_id"),
                event.get("skill_id"),
                event.get("skill_version"),
                str(event["feedback_type"]),
                json.dumps(event.get("feedback_payload") or {}),
                event.get("created_by"),
            ),
            "feedback_id",
        )

    def query_logs_by_skill(self, skill_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        conn = self._connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    'retrieval' AS kind,
                    selected_skill_id AS skill_id,
                    selected_version AS skill_version,
                    retrieval_id,
                    NULL::bigint AS execution_id,
                    elapsed_ms,
                    metadata,
                    event_ts AS created_at
                FROM agent_skills.skill_retrieval_logs
                WHERE selected_skill_id = %s
                UNION ALL
                SELECT
                    'execution' AS kind,
                    skill_id,
                    skill_version,
                    retrieval_id,
                    execution_id,
                    elapsed_ms,
                    metadata,
                    event_ts AS created_at
                FROM agent_skills.skill_execution_logs
                WHERE skill_id = %s
                ORDER BY created_at DESC NULLS LAST
                LIMIT %s
                """,
                (skill_id, skill_id, int(limit)),
            )
            return self._fetchall_dicts(cur)

    def recent_activity(self, *, limit: int = 10) -> list[dict[str, Any]]:
        conn = self._connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    'retrieval' AS kind,
                    selected_skill_id AS skill_id,
                    selected_version AS skill_version,
                    retrieval_id,
                    NULL::bigint AS execution_id,
                    NULL::text AS validation_status,
                    elapsed_ms,
                    event_ts AS created_at
                FROM agent_skills.skill_retrieval_logs
                UNION ALL
                SELECT
                    'execution' AS kind,
                    skill_id,
                    skill_version,
                    retrieval_id,
                    execution_id,
                    validation_status,
                    elapsed_ms,
                    event_ts AS created_at
                FROM agent_skills.skill_execution_logs
                ORDER BY created_at DESC NULLS LAST
                LIMIT %s
                """,
                (int(limit),),
            )
            return self._fetchall_dicts(cur)

    def get_feedback_summary(self, skill_id: str | None = None) -> list[dict[str, Any]]:
        conn = self._connect()
        where = "WHERE skill_id = %s" if skill_id else ""
        params: tuple[Any, ...] = (skill_id,) if skill_id else ()
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    skill_id,
                    COUNT(*)::int AS total,
                    SUM(CASE WHEN feedback_payload->>'sentiment' = 'positive' THEN 1 ELSE 0 END)::int AS positive,
                    SUM(CASE WHEN feedback_payload->>'sentiment' = 'negative' THEN 1 ELSE 0 END)::int AS negative,
                    COALESCE(
                        AVG(CASE WHEN feedback_payload->>'sentiment' = 'positive' THEN 1.0 ELSE 0.0 END),
                        0.0
                    )::float AS runtime_success_rate
                FROM agent_skills.skill_feedback
                {where}
                GROUP BY skill_id
                ORDER BY skill_id
                """,
                params,
            )
            return self._fetchall_dicts(cur)

    def _insert_log_returning_id(self, sql: str, params: tuple[Any, ...], id_column: str) -> int | None:
        conn = self._connect()
        with conn.cursor() as cur:
            cur.execute(sql, params)
            row = self._fetchone_dict(cur)
        self._commit(conn)
        if not row:
            return None
        value = row.get(id_column)
        return int(value) if value is not None else None
