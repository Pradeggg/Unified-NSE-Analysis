from company_intelligence_pg import (
    REQUIRED_TABLES,
    add_company_alias,
    get_company_aliases,
    init_company_intelligence_pg,
    record_analysis_run,
    schema_sql,
    upsert_company,
)


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self._rows = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.conn.executed.append((sql, params))
        normalized = " ".join(sql.split())
        if "RETURNING analysis_run_id" in sql:
            self._rows = [(42,)]
        elif "SELECT alias FROM company_intel.company_aliases" in normalized:
            self._rows = [("AVENUE SUPERMARTS",), ("Avenue Supermarts",), ("DMART",)]
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
        self.closed = False

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.commits += 1

    def close(self):
        self.closed = True


def test_schema_sql_defines_company_intel_tables_and_indexes():
    sql = schema_sql()

    assert "CREATE SCHEMA IF NOT EXISTS company_intel" in sql
    for table in REQUIRED_TABLES:
        assert f"CREATE TABLE IF NOT EXISTS company_intel.{table}" in sql
    assert "CREATE INDEX IF NOT EXISTS idx_company_intel_website_chunks_search" in sql


def test_init_company_intelligence_pg_executes_schema_and_commits():
    conn = FakeConnection()

    result = init_company_intelligence_pg(conn=conn)

    assert result == {"status": "ready", "schema": "company_intel", "tables": REQUIRED_TABLES}
    assert len(conn.executed) == 1
    assert "CREATE SCHEMA IF NOT EXISTS company_intel" in conn.executed[0][0]
    assert conn.commits == 1


def test_pg_company_crud_helpers_use_company_intel_schema():
    conn = FakeConnection()

    upsert_company(conn, "DMART", company_name="Avenue Supermarts", sector="Retail")
    add_company_alias(conn, "DMART", "Avenue Supermarts", "company_name")
    aliases = get_company_aliases(conn, "DMART")
    run_id = record_analysis_run(conn, "DMART", "company_xray", "strict", "ok", report_path="reports/x.html")

    executed_sql = "\n".join(sql for sql, _params in conn.executed)
    assert "INSERT INTO company_intel.companies" in executed_sql
    assert "INSERT INTO company_intel.company_aliases" in executed_sql
    assert "FROM company_intel.company_aliases" in executed_sql
    assert "INSERT INTO company_intel.analysis_runs" in executed_sql
    assert aliases == ["AVENUE SUPERMARTS", "Avenue Supermarts", "DMART"]
    assert run_id == 42


def test_postgres_migrate_exposes_company_intel_section():
    from postgres import migrate

    assert "company_intel" in migrate.SECTIONS
