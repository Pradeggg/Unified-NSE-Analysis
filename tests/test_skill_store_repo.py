from __future__ import annotations

import json


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.description = []
        self._rows = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.conn.executed.append((sql, params))
        lowered = " ".join(str(sql).lower().split())
        if "returning *" in lowered:
            row = dict(self.conn.skill_row)
            row["status"] = params[2]
            row["domain"] = params[3]
            row["title"] = params[4]
            row["card_payload"] = json.loads(params[13])
            self._rows = [row]
        elif "insert into agent_skills.skill_sql_templates" in lowered:
            self.conn.sql_template_upserts.append(params)
            self._rows = []
        elif "from agent_skills.skill_embeddings" in lowered:
            self.conn.vector_searches.append(params)
            statuses = set(params[1])
            limit = params[-1]
            model = None
            if "e.embedding_model = %s" in lowered:
                model = params[-3]
            rows = [
                row
                for row in self.conn.vector_candidates
                if row["status"] in statuses and (model is None or row["embedding_model"] == model)
            ]
            self._rows = rows[:limit]
        elif "from agent_skills.skill_embeddings" in lowered:
            statuses = set(params[1])
            rows = [row for row in self.conn.embedding_rows if row["status"] in statuses]
            if "c.domain = %s" in lowered:
                rows = [row for row in rows if row["domain"] == params[2]]
            self._rows = rows[: params[-1]]
        elif "from agent_skills.skill_cards" in lowered and "status = any" in lowered:
            statuses = set(params[0])
            rows = [row for row in self.conn.cards if row["status"] in statuses]
            if len(params) > 1:
                rows = [row for row in rows if row["domain"] == params[1]]
            self._rows = rows
        elif "from agent_skills.skill_cards" in lowered:
            skill_id = params[0]
            rows = [row for row in self.conn.cards if row["id"] == skill_id]
            if len(params) > 1:
                rows = [row for row in rows if row["version"] == params[1]]
            rows.sort(key=lambda row: row["version"], reverse=True)
            self._rows = rows[:1]
        elif "from agent_skills.skill_sql_templates" in lowered:
            skill_id = params[0]
            if len(params) == 2:
                template_name = params[1]
                rows = [
                    row
                    for row in self.conn.sql_templates
                    if row["skill_id"] == skill_id and row["template_name"] == template_name
                ]
            else:
                version = params[1]
                template_name = params[2]
                rows = [
                    row
                    for row in self.conn.sql_templates
                    if row["skill_id"] == skill_id
                    and row["skill_version"] == version
                    and row["template_name"] == template_name
                ]
            rows.sort(key=lambda row: row["skill_version"], reverse=True)
            self._rows = rows[:1]
        elif "returning embedding_id" in lowered:
            self._rows = [
                {
                    "embedding_id": 7,
                    "skill_id": params[0],
                    "skill_version": params[1],
                    "embedding_model": params[2],
                    "embedding_dimension": params[3],
                    "embedding_text": params[4],
                }
            ]
        elif "returning retrieval_id" in lowered:
            self._rows = [{"retrieval_id": 11}]
        elif "returning execution_id" in lowered:
            self._rows = [{"execution_id": 12}]
        elif "returning feedback_id" in lowered:
            self._rows = [{"feedback_id": 13}]
        elif "from agent_skills.skill_retrieval_logs" in lowered and "union all" in lowered:
            skill_id = params[0]
            limit = params[-1]
            self._rows = [
                {"kind": "retrieval", "skill_id": skill_id, "retrieval_id": 11, "execution_id": None},
                {"kind": "execution", "skill_id": skill_id, "retrieval_id": 11, "execution_id": 12},
            ][:limit]
        elif "from agent_skills.skill_feedback" in lowered and "runtime_success_rate" in lowered:
            rows = [
                {
                    "skill_id": "market_review_v1",
                    "total": 5,
                    "positive": 4,
                    "negative": 1,
                    "runtime_success_rate": 0.8,
                }
            ]
            if params:
                rows = [row for row in rows if row["skill_id"] == params[0]]
            self._rows = rows
        else:
            self._rows = []

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


class FakeConnection:
    def __init__(self):
        self.executed = []
        self.commits = 0
        self.sql_template_upserts = []
        self.vector_searches = []
        self.skill_row = {
            "id": "market_review_v1",
            "version": 1,
            "status": "generated",
            "domain": "market_analysis",
            "title": "Market Review",
            "description": "Review market state.",
            "card_payload": {},
        }
        self.cards = [
            {
                "id": "generated_v1",
                "version": 1,
                "status": "generated",
                "domain": "market_analysis",
                "title": "Generated",
            },
            {
                "id": "validated_v1",
                "version": 1,
                "status": "validated",
                "domain": "market_analysis",
                "title": "Validated",
            },
            {
                "id": "production_v2",
                "version": 2,
                "status": "production",
                "domain": "screening",
                "title": "Production",
            },
        ]
        self.sql_templates = [
            {
                "skill_id": "market_review_v1",
                "skill_version": 1,
                "template_name": "latest_index",
                "sql_text": "SELECT * FROM market.index_eod LIMIT 10",
                "required_params": [],
                "expected_columns": ["trade_date"],
                "row_limit": 10,
                "safety_status": "passed",
            },
            {
                "skill_id": "market_review_v1",
                "skill_version": 2,
                "template_name": "latest_index",
                "sql_text": "SELECT * FROM market.index_eod LIMIT 20",
                "required_params": [],
                "expected_columns": ["trade_date"],
                "row_limit": 20,
                "safety_status": "passed",
            },
        ]
        self.vector_candidates = [
            {
                "id": "validated_v1",
                "skill_id": "validated_v1",
                "version": 1,
                "status": "validated",
                "domain": "market_analysis",
                "title": "Validated",
                "tags": ["market"],
                "input_patterns": ["market review"],
                "vector_score": 0.77,
                "embedding_model": "fake-sentence-transformer",
            },
            {
                "id": "generated_v1",
                "skill_id": "generated_v1",
                "version": 1,
                "status": "generated",
                "domain": "market_analysis",
                "title": "Generated",
                "tags": ["market"],
                "input_patterns": ["market review"],
                "vector_score": 0.99,
                "embedding_model": "fake-sentence-transformer",
            },
        ]
        self.embedding_rows = [
            {
                "id": "validated_v1",
                "version": 1,
                "status": "validated",
                "domain": "market_analysis",
                "title": "Validated",
                "tags": ["market"],
                "vector_score": 0.92,
            },
            {
                "id": "generated_v1",
                "version": 1,
                "status": "generated",
                "domain": "market_analysis",
                "title": "Generated",
                "tags": ["market"],
                "vector_score": 0.99,
            },
        ]

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.commits += 1


def _minimal_card(**overrides):
    card = {
        "id": "market_review_v1",
        "version": 1,
        "status": "review_pending",
        "domain": "market_analysis",
        "title": "Market Review",
        "description": "Review market state.",
        "input_patterns": ["last 3 months market analysis"],
        "tags": ["market"],
        "evidence_required": {"tables": ["market.index_eod"]},
        "tool_plan_template": [],
        "output_contract": ["summary"],
        "validation_rules": ["required_tables_exist"],
        "synthesis_guidance": "Use evidence only.",
        "generation_model": "gpt-4o",
        "created_by": "test",
    }
    card.update(overrides)
    return card


def test_skill_store_repository_upserts_card_and_sql_templates_then_fetches_card():
    from terminal.skills.store_repo import SkillStoreRepository

    conn = FakeConnection()
    repo = SkillStoreRepository(conn=conn)
    card = _minimal_card(
        sql_templates=[
            {
                "name": "latest_index",
                "sql": "SELECT trade_date FROM market.index_eod LIMIT :limit",
                "required_params": ["limit"],
                "expected_columns": ["trade_date"],
                "row_limit": 25,
                "safety_status": "passed",
                "safety_findings": [],
            }
        ]
    )

    row = repo.upsert_skill_card(card)
    fetched = repo.get_skill_card("validated_v1")

    assert row["id"] == "market_review_v1"
    assert row["status"] == "review_pending"
    assert fetched["id"] == "validated_v1"
    assert conn.commits == 2
    assert conn.sql_template_upserts == [
        (
            "market_review_v1",
            1,
            "latest_index",
            "SELECT trade_date FROM market.index_eod LIMIT :limit",
            ["limit"],
            ["trade_date"],
            25,
            "passed",
            "[]",
        )
    ]
    assert all("%s" in sql for sql, _ in conn.executed)
    assert all(params is not None for _, params in conn.executed)


def test_skill_store_repository_lists_only_runtime_eligible_cards():
    from terminal.skills.store_repo import SkillStoreRepository

    repo = SkillStoreRepository(conn=FakeConnection())

    rows = repo.list_runtime_eligible()
    market_rows = repo.list_runtime_eligible(domain="market_analysis")

    assert [row["id"] for row in rows] == ["validated_v1", "production_v2"]
    assert [row["id"] for row in market_rows] == ["validated_v1"]


def test_skill_store_repository_fetches_latest_or_versioned_sql_template():
    from terminal.skills.store_repo import SkillStoreRepository

    repo = SkillStoreRepository(conn=FakeConnection())

    latest = repo.get_sql_template("market_review_v1", "latest_index")
    versioned = repo.get_sql_template("market_review_v1", "latest_index", version=1)

    assert latest["skill_version"] == 2
    assert latest["row_limit"] == 20
    assert versioned["skill_version"] == 1
    assert versioned["row_limit"] == 10


def test_skill_store_repository_searches_embedding_candidates_with_runtime_filter():
    from terminal.skills.store_repo import EMBEDDING_DIMENSION, SkillStoreRepository

    conn = FakeConnection()
    repo = SkillStoreRepository(conn=conn)

    rows = repo.search_embedding_candidates([0.1] * EMBEDDING_DIMENSION, top_n=5, domain="market_analysis")

    assert [row["id"] for row in rows] == ["validated_v1"]
    sql, params = conn.executed[-1]
    assert "agent_skills.skill_embeddings" in sql
    assert "%s::vector" in sql
    assert params[1] == ["validated", "production"]
    assert params[2] == "market_analysis"
    assert params[-1] == 5


def test_skill_store_repository_saves_embedding_with_dimension_check():
    from terminal.skills.store_repo import EMBEDDING_DIMENSION, SkillStoreRepository

    conn = FakeConnection()
    repo = SkillStoreRepository(conn=conn)

    row = repo.save_embedding(
        "market_review_v1",
        "BAAI/bge-small-en-v1.5",
        EMBEDDING_DIMENSION,
        [0.1] * EMBEDDING_DIMENSION,
        "Market Review\nlast 3 months market analysis",
    )

    assert row["embedding_id"] == 7
    assert row["embedding_dimension"] == EMBEDDING_DIMENSION
    sql, params = conn.executed[-1]
    assert "%s::vector" in sql
    assert params[-1].startswith("[0.1,0.1,0.1")


def test_skill_store_repository_searches_vector_candidates_with_runtime_status_filter():
    from terminal.skills.store_repo import EMBEDDING_DIMENSION, SkillStoreRepository

    conn = FakeConnection()
    repo = SkillStoreRepository(conn=conn)

    rows = repo.search_vector_candidates(
        [0.1] * EMBEDDING_DIMENSION,
        "fake-sentence-transformer",
        limit=5,
    )

    assert [row["skill_id"] for row in rows] == ["validated_v1"]
    assert conn.vector_searches
    vector_literal, statuses, model, order_vector_literal, limit = conn.vector_searches[0]
    assert vector_literal.startswith("[0.1,0.1,0.1")
    assert order_vector_literal == vector_literal
    assert statuses == ["validated", "production"]
    assert model == "fake-sentence-transformer"
    assert limit == 5


def test_skill_store_repository_rejects_embedding_dimension_mismatch():
    from terminal.skills.store_repo import SkillStoreRepository

    repo = SkillStoreRepository(conn=FakeConnection())

    try:
        repo.save_embedding("market_review_v1", "model", 2, [0.1], "text")
    except ValueError as exc:
        assert "dimension" in str(exc)
    else:
        raise AssertionError("expected dimension mismatch to fail")


def test_skill_store_repository_rejects_embedding_dimension_that_does_not_match_schema():
    from terminal.skills.store_repo import SkillStoreRepository

    repo = SkillStoreRepository(conn=FakeConnection())

    try:
        repo.save_embedding("market_review_v1", "model", 3, [0.1, 0.2, 0.3], "text")
    except ValueError as exc:
        assert "384" in str(exc)
    else:
        raise AssertionError("expected non-schema embedding dimension to fail")


def test_skill_store_repository_logs_retrieval_execution_and_feedback():
    from terminal.skills.store_repo import SkillStoreRepository

    conn = FakeConnection()
    repo = SkillStoreRepository(conn=conn)

    retrieval_id = repo.log_retrieval(
        {
            "query_hash": "abc",
            "normalized_query": "last 3 months market analysis",
            "selected_skill_id": "market_review_v1",
            "selected_version": 1,
            "candidates": [{"id": "market_review_v1", "score": 0.9}],
            "reviewer_decision": {"status": "pass"},
            "elapsed_ms": 12,
            "metadata": {"mode": "test"},
        }
    )
    execution_id = repo.log_execution(
        {
            "retrieval_id": retrieval_id,
            "skill_id": "market_review_v1",
            "skill_version": 1,
            "steps": [{"name": "fetch"}],
            "validation_status": "passed",
            "validation_findings": [],
            "elapsed_ms": 8,
        }
    )
    feedback_id = repo.save_feedback(
        {
            "retrieval_id": retrieval_id,
            "execution_id": execution_id,
            "skill_id": "market_review_v1",
            "skill_version": 1,
            "feedback_type": "thumbs_up",
            "feedback_payload": {"reason": "grounded"},
            "created_by": "test",
        }
    )

    assert (retrieval_id, execution_id, feedback_id) == (11, 12, 13)
    assert conn.commits == 3
    for sql, params in conn.executed:
        assert "%s" in sql
        assert params is not None


def test_skill_store_repository_queries_logs_by_skill_id():
    from terminal.skills.store_repo import SkillStoreRepository

    conn = FakeConnection()
    repo = SkillStoreRepository(conn=conn)

    rows = repo.query_logs_by_skill("market_review_v1", limit=10)

    assert [row["kind"] for row in rows] == ["retrieval", "execution"]
    assert rows[0]["skill_id"] == "market_review_v1"
    sql = conn.executed[-1][0].lower()
    assert "event_ts as created_at" in sql
    assert "order by created_at desc" in sql


def test_skill_store_repository_summarizes_feedback_by_skill_id():
    from terminal.skills.store_repo import SkillStoreRepository

    repo = SkillStoreRepository(conn=FakeConnection())

    rows = repo.get_feedback_summary("market_review_v1")

    assert rows == [
        {
            "skill_id": "market_review_v1",
            "total": 5,
            "positive": 4,
            "negative": 1,
            "runtime_success_rate": 0.8,
        }
    ]
