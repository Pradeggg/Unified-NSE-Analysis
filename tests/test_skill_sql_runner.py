from __future__ import annotations


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
        if lowered.startswith("select * from"):
            self.description = [("symbol",), ("close",), ("as_of_date",)]
            self._rows = [("RELIANCE", 1450.5, "2026-06-05")]
        else:
            self._rows = []

    def fetchall(self):
        return list(self._rows)


class EmptyCursor(FakeCursor):
    def execute(self, sql, params=None):
        self.conn.executed.append((sql, params))
        lowered = " ".join(str(sql).lower().split())
        if lowered.startswith("select * from"):
            self.description = [("symbol",), ("close",)]
            self._rows = []


class FakeConnection:
    cursor_cls = FakeCursor

    def __init__(self):
        self.executed = []
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return self.cursor_cls(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class EmptyConnection(FakeConnection):
    cursor_cls = EmptyCursor


class FakeRepository:
    def __init__(self, template):
        self.template = template
        self.requested = []

    def get_sql_template(self, skill_id, template_name, version=None):
        self.requested.append((skill_id, template_name, version))
        return self.template


def _approved_template(**overrides):
    template = {
        "skill_id": "vcp_breakouts_v1",
        "skill_version": 1,
        "template_name": "latest_candidates",
        "sql_text": "SELECT symbol, close, snapshot_date AS as_of_date FROM scores.stage_snapshots WHERE symbol = :symbol",
        "required_params": ["symbol"],
        "expected_columns": ["symbol", "close", "as_of_date"],
        "row_limit": 25,
        "safety_status": "passed",
        "safety_findings": [],
    }
    template.update(overrides)
    return template


def test_runner_executes_approved_read_only_template():
    from terminal.skills.sql_runner import run_skill_sql_template

    conn = FakeConnection()
    repo = FakeRepository(_approved_template())

    result = run_skill_sql_template(
        "vcp_breakouts_v1",
        "latest_candidates",
        {"symbol": "RELIANCE"},
        repository=repo,
        conn=conn,
        timeout_ms=3000,
    )

    assert result.to_dict() == {
        "columns": ["symbol", "close", "as_of_date"],
        "rows": [{"symbol": "RELIANCE", "close": 1450.5, "as_of_date": "2026-06-05"}],
        "row_count": 1,
        "as_of_date": "2026-06-05",
        "warnings": [],
    }
    assert repo.requested == [("vcp_breakouts_v1", "latest_candidates", None)]
    assert conn.executed[0][0] == "BEGIN READ ONLY"
    assert conn.executed[1] == ("SET LOCAL statement_timeout = %s", (3000,))
    query_sql, query_params = conn.executed[2]
    assert "LIMIT %(skill_row_limit)s" in query_sql
    assert query_params["symbol"] == "RELIANCE"
    assert query_params["skill_row_limit"] == 25
    assert conn.commits == 1


def test_runner_blocks_missing_template():
    import pytest
    from terminal.skills.sql_runner import run_skill_sql_template

    with pytest.raises(ValueError, match="SQL template not found"):
        run_skill_sql_template("missing", "q", {}, repository=FakeRepository(None), conn=FakeConnection())


def test_runner_blocks_unapproved_or_unsafe_template():
    import pytest
    from terminal.skills.sql_runner import run_skill_sql_template

    pending = FakeRepository(_approved_template(safety_status="pending"))
    unsafe = FakeRepository(_approved_template(sql_text="DELETE FROM scores.stage_snapshots", safety_status="passed"))

    with pytest.raises(ValueError, match="SQL template is not approved"):
        run_skill_sql_template("vcp_breakouts_v1", "latest_candidates", {"symbol": "RELIANCE"}, repository=pending, conn=FakeConnection())
    with pytest.raises(ValueError, match="disallowed SQL keyword"):
        run_skill_sql_template("vcp_breakouts_v1", "latest_candidates", {"symbol": "RELIANCE"}, repository=unsafe, conn=FakeConnection())


def test_runner_validates_required_params_before_execution():
    import pytest
    from terminal.skills.sql_runner import run_skill_sql_template

    conn = FakeConnection()

    with pytest.raises(ValueError, match="missing required parameter: symbol"):
        run_skill_sql_template("vcp_breakouts_v1", "latest_candidates", {}, repository=FakeRepository(_approved_template()), conn=conn)

    assert conn.executed == []


def test_runner_labels_empty_result_clearly():
    from terminal.skills.sql_runner import run_skill_sql_template

    result = run_skill_sql_template(
        "vcp_breakouts_v1",
        "latest_candidates",
        {"symbol": "RELIANCE"},
        repository=FakeRepository(_approved_template(expected_columns=["symbol", "close"])),
        conn=EmptyConnection(),
    )

    assert result.rows == []
    assert result.row_count == 0
    assert result.as_of_date is None
    assert "query returned no rows" in result.warnings


def test_runner_caps_template_row_limit():
    from terminal.skills.sql_runner import run_skill_sql_template

    conn = FakeConnection()

    run_skill_sql_template(
        "vcp_breakouts_v1",
        "latest_candidates",
        {"symbol": "RELIANCE"},
        repository=FakeRepository(_approved_template(row_limit=1000000)),
        conn=conn,
        max_row_limit=250,
    )

    query_sql, query_params = conn.executed[2]
    assert "LIMIT %(skill_row_limit)s" in query_sql
    assert query_params["skill_row_limit"] == 250
