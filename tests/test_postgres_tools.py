from __future__ import annotations

import types

import pytest


class FakeCursor:
    def __init__(self, rows_by_query: dict[str, object] | None = None):
        self.rows_by_query = rows_by_query or {}
        self.last_sql = ""
        self.statements: list[tuple[str, tuple | None]] = []

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def execute(self, sql, params=None):
        self.last_sql = " ".join(str(sql).split())
        self.statements.append((self.last_sql, params))

    def fetchone(self):
        for key, value in self.rows_by_query.items():
            if key in self.last_sql:
                return value
        return None

    def fetchall(self):
        for key, value in self.rows_by_query.items():
            if key in self.last_sql:
                return value
        return []


class FakeConnection:
    def __init__(self, cursor: FakeCursor):
        self.cursor_obj = cursor
        self.closed = False
        self.commits = 0

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.close()
        return False

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.commits += 1

    def close(self):
        self.closed = True


def test_get_data_source_manifest_declares_postgres_primary():
    from terminal.postgres_tools import get_data_source_manifest

    manifest = get_data_source_manifest()

    assert manifest["primary_store"] == "PostgreSQL"
    assert manifest["legacy_sqlite"]["role"] == "fallback/cache"
    assert "intraday.ohlcv_bars" in manifest["required_tables"]
    assert manifest["fallback_policy"]["silent_sqlite_fallback"] is False


def test_get_postgres_health_reports_connection_failure(monkeypatch):
    import terminal.postgres_tools as pgtools

    def fail_connect(_dsn):
        raise RuntimeError("database is not running")

    monkeypatch.setattr(pgtools, "_connect", fail_connect)

    result = pgtools.get_postgres_health("dbname=nse_market user=nse_admin host=/tmp")

    assert result["status"] == "error"
    assert result["host"] == "/tmp"
    assert "database is not running" in result["error"]
    assert "postgres/start_pg.sh" in result["next_action"]


def test_get_postgres_health_reports_missing_required_tables(monkeypatch):
    import terminal.postgres_tools as pgtools

    cursor = FakeCursor(
        {
            "current_database": ("nse_market", "nse_admin"),
            "version()": ("PostgreSQL 16",),
            "information_schema.schemata": [("intraday",), ("report",)],
            "to_regclass": [(None,), ("intraday.ohlcv_bars",), (None,)],
            "COUNT(*) FROM intraday.ohlcv_bars": (42,),
        }
    )
    conn = FakeConnection(cursor)
    monkeypatch.setattr(pgtools, "_connect", lambda _dsn: conn)
    monkeypatch.setattr(
        pgtools,
        "REQUIRED_TABLES",
        ("intraday.quote_snapshots", "intraday.ohlcv_bars", "report.enhanced_runs"),
    )

    result = pgtools.get_postgres_health("dbname=nse_market user=nse_admin host=/tmp")

    assert result["status"] == "degraded"
    assert result["database"] == "nse_market"
    assert result["user"] == "nse_admin"
    assert result["host"] == "/tmp"
    assert result["socket_path"] == "/tmp/.s.PGSQL.5432"
    assert result["missing_schemas"] == ["market", "scores"]
    assert result["migration_status"] == "schema_missing"
    assert result["tables"]["intraday.ohlcv_bars"]["exists"] is True
    assert result["tables"]["intraday.ohlcv_bars"]["row_count"] == 42
    assert "intraday.quote_snapshots" in result["missing_tables"]
    assert "report.enhanced_runs" in result["missing_tables"]


def test_ensure_postgres_schema_executes_idempotent_schema_sql(monkeypatch):
    import terminal.postgres_tools as pgtools

    cursor = FakeCursor()
    conn = FakeConnection(cursor)
    monkeypatch.setattr(pgtools, "_connect", lambda _dsn: conn)

    result = pgtools.ensure_postgres_schema("dbname=nse_market user=nse_admin host=/tmp")

    assert result["status"] == "ok"
    assert conn.commits == 1
    executed = " ".join(sql for sql, _params in cursor.statements)
    assert "CREATE SCHEMA IF NOT EXISTS intraday" in executed
    assert "CREATE SCHEMA IF NOT EXISTS report" in executed


def test_tools_registry_exposes_postgres_tools():
    from terminal.tools import TOOL_REGISTRY

    for name in (
        "get_postgres_health",
        "ensure_postgres_schema",
        "audit_postgres_coverage",
        "get_data_source_manifest",
    ):
        assert name in TOOL_REGISTRY
        assert callable(TOOL_REGISTRY[name][0])


def test_render_postgres_doctor_runs_repair_before_health(monkeypatch):
    import terminal.postgres_tools as pgtools

    calls: list[str] = []

    def fake_repair(dsn=None):
        calls.append("repair")
        return {"status": "ok"}

    def fake_health(dsn=None):
        calls.append("health")
        return {
            "status": "ok",
            "dsn": "dbname=nse_market user=nse_admin host=/tmp",
            "host": "/tmp",
            "socket_path": "/tmp/.s.PGSQL.5432",
            "socket_exists": True,
            "required_schemas": ["market", "scores", "intraday", "report"],
            "missing_schemas": [],
            "migration_status": "ready",
            "missing_tables": [],
            "tables": {
                "intraday.ohlcv_bars": {"exists": True, "row_count": 42},
                "scores.stage_snapshots": {"exists": True, "row_count": 915},
            },
            "next_action": "no action needed",
        }

    monkeypatch.setattr(pgtools, "ensure_postgres_schema", fake_repair)
    monkeypatch.setattr(pgtools, "get_postgres_health", fake_health)

    output = pgtools.render_postgres_doctor(repair=True)

    assert calls == ["repair", "health"]
    assert "PostgreSQL Doctor" in output
    assert "Status: ok" in output
    assert "Socket: /tmp/.s.PGSQL.5432 (exists)" in output
    assert "Schemas: ready" in output
    assert "Migration status: ready" in output
    assert "intraday.ohlcv_bars: ok (42 rows)" in output
    assert "scores.stage_snapshots: ok (915 rows)" in output
    assert "Missing tables: none" in output


def test_doctor_is_registered_as_slash_command():
    import nse_agent

    labels = [label for label, _description in nse_agent._SLASH_COMMANDS]

    assert "/doctor" in labels
    assert "/doctor --repair" in labels


def test_single_query_doctor_routes_to_postgres_doctor(monkeypatch):
    import nse_agent
    import terminal.postgres_tools as pgtools

    calls: list[bool] = []
    monkeypatch.setattr(pgtools, "render_postgres_doctor", lambda repair=False: calls.append(repair) or "PostgreSQL Doctor\nStatus: ok")
    monkeypatch.setattr(nse_agent, "_print_user", lambda query: None)
    monkeypatch.setattr(nse_agent.console, "print", lambda *args, **kwargs: None)

    class DummyAgent:
        def query(self, *_args, **_kwargs):  # pragma: no cover - must not be called
            raise AssertionError("agent.query should not handle /doctor")

    nse_agent._single_query(DummyAgent(), "/doctor --repair", show_trace=False)

    assert calls == [True]
