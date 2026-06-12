from broker_research.scheduler import ScheduledBrokerCrawlResult, run_scheduled_broker_crawl
from broker_research.sources import BrokerSource


ICICI_URL = "https://www.icicidirect.com/mailcontent/co_reports.html"
HDFC_URL = "https://www.hdfcsec.com/research/equity/stock-research-institutional-reports"


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
        if "SELECT alias FROM company_intel.company_aliases" in normalized:
            self.rows = [("Bharat Electronics",)]
        elif "RETURNING broker_report_id" in sql:
            self.rows = [(77,)]
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


def test_scheduled_broker_crawl_discovers_public_sources_with_limit():
    conn = FakeConnection()
    sources = (
        BrokerSource("icici", "ICICI Direct", "index_page", ICICI_URL, "public"),
        BrokerSource("hdfc_hsie", "HDFC Securities / HSIE", "index_page", HDFC_URL, "public"),
    )
    html = {
        ICICI_URL: '<a href="idirect_bharatelectronics_q3fy26.pdf">Bharat Electronics Q3FY26</a>',
        HDFC_URL: '<a href="/hsl.docs//Bharat Electronics - Q4FY26 - HSIE-1.pdf">Bharat Electronics Q4FY26</a>',
    }

    result = run_scheduled_broker_crawl(
        conn=conn,
        symbol="BEL",
        sources=sources,
        fetch_html=lambda source: html[source.source_url],
        max_sources=1,
    )

    executed = "\n".join(sql for sql, _params in conn.executed)
    assert result == ScheduledBrokerCrawlResult(
        symbol="BEL",
        sources_seen=1,
        sources_succeeded=1,
        sources_failed=0,
        links_discovered=1,
        reports_stored=1,
        skipped_sources=1,
        failures=[],
    )
    assert "INSERT INTO company_intel.broker_sources" in executed
    assert "INSERT INTO company_intel.broker_reports" in executed


def test_scheduled_broker_crawl_skips_inactive_and_login_required_sources():
    conn = FakeConnection()
    sources = (
        BrokerSource("public", "Public", "index_page", "https://example.com/public", "public"),
        BrokerSource("login", "Login", "index_page", "https://example.com/login", "login_required"),
        BrokerSource("inactive", "Inactive", "index_page", "https://example.com/inactive", "public", is_active=False),
    )
    calls = []

    result = run_scheduled_broker_crawl(
        conn=conn,
        symbol="BEL",
        sources=sources,
        fetch_html=lambda source: calls.append(source.source_url) or "",
    )

    assert calls == ["https://example.com/public"]
    assert result.sources_seen == 1
    assert result.skipped_sources == 2


def test_scheduled_broker_crawl_records_source_failures_without_crashing():
    conn = FakeConnection()
    sources = (BrokerSource("icici", "ICICI Direct", "index_page", ICICI_URL, "public"),)

    def failing_fetch(source):
        raise TimeoutError("network timeout")

    result = run_scheduled_broker_crawl(
        conn=conn,
        symbol="BEL",
        sources=sources,
        fetch_html=failing_fetch,
    )

    assert result.sources_seen == 1
    assert result.sources_failed == 1
    assert result.failures == [{"broker_code": "icici", "source_url": ICICI_URL, "error": "network timeout"}]
