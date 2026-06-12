from broker_research.discovery import DiscoveredReportLink
from broker_research.sources import BROKER_SOURCES
from broker_research.storage import (
    complete_index_run,
    insert_broker_research_facts,
    list_broker_sources,
    record_index_run,
    seed_broker_sources,
    upsert_discovered_report,
)


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.rows = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.conn.executed.append((sql, params))
        normalized = " ".join(sql.split())
        if "RETURNING index_run_id" in sql:
            self.rows = [(17,)]
        elif "RETURNING broker_report_id" in sql:
            self.rows = [(33,)]
        elif "FROM company_intel.broker_sources" in normalized:
            self.rows = [("icici", "ICICI Direct", "index_page", "public", True, "https://example.com")]
        else:
            self.rows = []

    def executemany(self, sql, params):
        self.conn.executed.append((sql, list(params)))

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return list(self.rows)


class FakeConnection:
    def __init__(self):
        self.executed = []
        self.commits = 0

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.commits += 1


def test_seed_broker_sources_upserts_registry_rows():
    conn = FakeConnection()

    count = seed_broker_sources(conn)

    sql = conn.executed[0][0]
    params = conn.executed[0][1]
    assert "INSERT INTO company_intel.broker_sources" in sql
    assert "ON CONFLICT (broker_code, source_kind, source_url) DO UPDATE" in sql
    assert len(params) == len(BROKER_SOURCES)
    assert count == len(BROKER_SOURCES)
    assert conn.commits == 1


def test_index_run_and_report_helpers_use_company_intel_tables():
    conn = FakeConnection()
    run_id = record_index_run(conn, source_id=5)
    report_id = upsert_discovered_report(
        conn,
        symbol="BEL",
        company_name="Bharat Electronics",
        link=DiscoveredReportLink(
            broker_code="icici",
            title="Bharat Electronics Q3FY26",
            pdf_url="https://www.icicidirect.com/mailcontent/idirect_bharatelectronics_q3fy26.pdf",
            source_url="https://www.icicidirect.com/mailcontent/co_reports.html",
        ),
        match_score=0.9,
    )
    complete_index_run(conn, index_run_id=run_id, status="ok", reports_found=2, reports_new=1)

    executed = "\n".join(sql for sql, _params in conn.executed)
    assert "INSERT INTO company_intel.broker_index_runs" in executed
    assert "INSERT INTO company_intel.broker_reports" in executed
    assert "UPDATE company_intel.broker_index_runs" in executed
    assert run_id == 17
    assert report_id == 33


def test_list_broker_sources_returns_dicts():
    conn = FakeConnection()

    rows = list_broker_sources(conn)

    assert rows == [
        {
            "broker_code": "icici",
            "broker_name": "ICICI Direct",
            "source_kind": "index_page",
            "access_mode": "public",
            "is_active": True,
            "source_url": "https://example.com",
        }
    ]


def test_insert_broker_research_facts_uses_company_intel_table():
    conn = FakeConnection()

    count = insert_broker_research_facts(
        conn,
        [
            {
                "broker_report_id": 33,
                "symbol": "BEL",
                "fact_type": "rating",
                "fact_name": "broker_rating",
                "fact_value": "BUY",
                "unit": "",
                "period": "",
                "page_number": 1,
                "confidence": 0.8,
                "extractor": "deterministic",
            }
        ],
    )

    sql = conn.executed[0][0]
    params = conn.executed[0][1]
    assert "INSERT INTO company_intel.broker_research_facts" in sql
    assert params == [(33, "BEL", "rating", "broker_rating", "BUY", "", "", 1, 0.8, "deterministic")]
    assert count == 1
    assert conn.commits == 1
