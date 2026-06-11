from __future__ import annotations

import json
from pathlib import Path


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self._rows = []
        self.description = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.conn.executed.append((sql, params))
        lowered = " ".join(str(sql).lower().split())
        if "insert into agent_learning.interaction_events" in lowered:
            self._rows = [{"event_id": 101}]
        elif "insert into agent_learning.workflow_chains" in lowered:
            self._rows = [{"chain_id": 102}]
        elif "insert into agent_learning.daily_summaries" in lowered:
            self._rows = [{"summary_id": 103}]
        elif "insert into agent_learning.patterns" in lowered:
            self._rows = [{"pattern_id": 104}]
        elif "insert into agent_learning.proposals" in lowered:
            self._rows = [{"proposal_id": 105}]
        elif "update agent_learning.proposals" in lowered:
            self._rows = [{"proposal_id": params[1]}]
        elif "insert into agent_learning.proposal_validation_runs" in lowered:
            self._rows = [{"validation_run_id": 107}]
        elif "select * from agent_learning.proposals where proposal_id" in lowered:
            self._rows = [row for row in self.conn.proposals if row["proposal_id"] == params[0]]
        elif "from agent_learning.proposals" in lowered:
            rows = list(self.conn.proposals)
            if "where status = %s" in lowered:
                rows = [row for row in rows if row["status"] == params[0]]
            self._rows = rows
        elif "insert into agent_learning.promotion_runs" in lowered:
            self._rows = [{"promotion_run_id": 106}]
        elif "from agent_learning.promotion_runs" in lowered:
            self._rows = list(self.conn.promotion_runs)
        elif "insert into agent_learning.learning_audits" in lowered:
            self._rows = [{"audit_id": 108}]
        elif "from agent_learning.interaction_events" in lowered:
            self._rows = list(self.conn.interaction_events)
        elif "from agent_learning.workflow_chains" in lowered:
            self._rows = list(self.conn.workflow_chains)
        elif "from agent_learning.patterns" in lowered:
            rows = list(self.conn.patterns)
            if "where status = %s" in lowered:
                rows = [row for row in rows if row["status"] == params[0]]
            if "limit %s" in lowered:
                rows = rows[: params[-1]]
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
        self.proposals = [
            {
                "proposal_id": 201,
                "status": "proposed",
                "proposal_type": "route",
                "title": "Add route",
                "proposal_payload": {"route": "market"},
            },
            {
                "proposal_id": 202,
                "status": "validated",
                "proposal_type": "skill",
                "title": "Validated skill",
                "proposal_payload": {"skill": "vcp"},
            },
        ]
        self.interaction_events = [{"event_id": 301, "selected_intent": "report_open"}]
        self.workflow_chains = [{"chain_id": 401, "chain_payload": {"chain_type": "daily_refresh_report_review_email"}}]
        self.patterns = [
            {"pattern_id": 501, "status": "observed", "pattern_payload": {"pattern_key": "query:vcp"}},
            {"pattern_id": 502, "status": "proposed", "pattern_payload": {"pattern_key": "workflow:refresh"}},
        ]
        self.promotion_runs = [
            {"promotion_run_id": 601, "proposal_id": 201, "status": "validated", "promotion_payload": {}}
        ]

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.commits += 1


def _normalized_schema_sql() -> str:
    return " ".join(Path("postgres/schema.sql").read_text(encoding="utf-8").split()).lower()


def test_agent_learning_schema_and_tables_are_declared():
    sql = _normalized_schema_sql()

    assert "create schema if not exists agent_learning" in sql
    for table in [
        "agent_learning.interaction_events",
        "agent_learning.workflow_chains",
        "agent_learning.daily_summaries",
        "agent_learning.patterns",
        "agent_learning.proposals",
        "agent_learning.proposal_validation_runs",
        "agent_learning.promotion_runs",
        "agent_learning.learning_audits",
    ]:
        assert f"create table if not exists {table}" in sql


def test_agent_learning_proposal_status_lifecycle_is_constrained():
    sql = _normalized_schema_sql()

    for status in [
        "observed",
        "proposed",
        "generated",
        "test_failed",
        "review_pending",
        "validated",
        "production",
        "deprecated",
    ]:
        assert f"'{status}'" in sql
    assert "agent_learning.proposals" in sql
    assert "check (status in (" in sql


def test_learning_repository_persists_core_learning_objects_with_sanitized_payloads():
    from terminal.learning.repository import LearningRepository

    conn = FakeConnection()
    repo = LearningRepository(conn=conn)

    event_id = repo.record_interaction_event(
        {
            "raw_query": "run report",
            "normalized_query": "run report",
            "selected_intent": "report_lookup",
            "payload": {
                "api_key": "sk-secret",
                "nested": {"password": "hidden", "ok": True},
                "raw_tool_payload": {"large": "x" * 10000},
            },
        }
    )
    chain_id = repo.record_workflow_chain({"chain_key": "daily_refresh->reports", "events": [event_id]})
    summary_id = repo.save_daily_summary({"summary_date": "2026-06-06", "summary_payload": {"queries": 12}})
    pattern_id = repo.save_pattern({"pattern_key": "report_refresh", "pattern_payload": {"count": 4}})
    proposal_id = repo.save_proposal({"proposal_type": "route", "title": "Add report route", "status": "proposed"})
    promotion_id = repo.record_promotion_run({"proposal_id": proposal_id, "status": "completed"})

    assert (event_id, chain_id, summary_id, pattern_id, proposal_id, promotion_id) == (101, 102, 103, 104, 105, 106)
    assert conn.commits == 6
    first_params = conn.executed[0][1]
    assert isinstance(first_params[-1], str)
    payload = json.loads(first_params[-1])
    serialized_payload = json.dumps(payload)
    assert "sk-secret" not in serialized_payload
    assert "password" not in serialized_payload
    assert "raw_tool_payload" not in serialized_payload


def test_learning_repository_lists_proposals_with_optional_status_filter():
    from terminal.learning.repository import LearningRepository

    conn = FakeConnection()
    repo = LearningRepository(conn=conn)

    all_rows = repo.list_proposals()
    proposed_rows = repo.list_proposals(status="proposed")

    assert [row["proposal_id"] for row in all_rows] == [201, 202]
    assert [row["proposal_id"] for row in proposed_rows] == [201]


def test_learning_repository_lists_daily_events_and_workflow_chains_by_date():
    from terminal.learning.repository import LearningRepository

    conn = FakeConnection()
    repo = LearningRepository(conn=conn)

    events = repo.list_interaction_events(start_date="2026-06-06", end_date="2026-06-06")
    chains = repo.list_workflow_chains(start_date="2026-06-06", end_date="2026-06-06")

    assert events == [{"event_id": 301, "selected_intent": "report_open"}]
    assert chains == [{"chain_id": 401, "chain_payload": {"chain_type": "daily_refresh_report_review_email"}}]
    assert "from agent_learning.interaction_events" in conn.executed[-2][0].lower()
    assert conn.executed[-2][1] == ("2026-06-06", "2026-06-06")
    assert "from agent_learning.workflow_chains" in conn.executed[-1][0].lower()
    assert conn.executed[-1][1] == ("2026-06-06", "2026-06-06")


def test_learning_repository_lists_patterns_with_status_and_limit():
    from terminal.learning.repository import LearningRepository

    conn = FakeConnection()
    repo = LearningRepository(conn=conn)

    rows = repo.list_patterns(status="observed", limit=1)

    assert rows == [{"pattern_id": 501, "status": "observed", "pattern_payload": {"pattern_key": "query:vcp"}}]
    assert "from agent_learning.patterns" in conn.executed[-1][0].lower()
    assert conn.executed[-1][1] == ("observed", 1)


def test_learning_repository_updates_proposal_status_and_records_validation_run():
    from terminal.learning.repository import LearningRepository

    conn = FakeConnection()
    repo = LearningRepository(conn=conn)

    updated_id = repo.update_proposal_status(105, "review_pending")
    run_id = repo.record_proposal_validation_run(
        {
            "proposal_id": 105,
            "status_before": "proposed",
            "status_after": "review_pending",
            "checks": [{"name": "generated_test_cases", "status": "pass"}],
            "findings": [],
        }
    )

    assert updated_id == 105
    assert run_id == 107
    assert "update agent_learning.proposals" in conn.executed[-2][0].lower()
    assert conn.executed[-2][1] == ("review_pending", 105)
    assert "insert into agent_learning.proposal_validation_runs" in conn.executed[-1][0].lower()


def test_learning_repository_gets_proposal_lists_promotion_runs_and_records_audit():
    from terminal.learning.repository import LearningRepository

    conn = FakeConnection()
    repo = LearningRepository(conn=conn)

    proposal = repo.get_proposal(201)
    runs = repo.list_promotion_runs(limit=5)
    audit_id = repo.record_learning_audit({"audit_type": "fortnightly_learning", "audit_payload": {"window": "14d"}})

    assert proposal["proposal_id"] == 201
    assert runs == [{"promotion_run_id": 601, "proposal_id": 201, "status": "validated", "promotion_payload": {}}]
    assert audit_id == 108
    assert "insert into agent_learning.learning_audits" in conn.executed[-1][0].lower()
