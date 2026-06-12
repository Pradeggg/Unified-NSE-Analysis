from broker_research.commands import (
    BrokerFetchOptions,
    BrokerIndexOptions,
    handle_broker_crawl_command,
    handle_broker_fetch_command,
    handle_broker_index_command,
    handle_broker_research_command,
    parse_broker_fetch_command,
    parse_broker_index_command,
    render_broker_sources,
)
from broker_research.scheduler import ScheduledBrokerCrawlResult


ICICI_URL = "https://www.icicidirect.com/mailcontent/co_reports.html"


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
        elif "SELECT broker_report_id, broker_code, symbol, pdf_url, local_path" in normalized:
            self.rows = list(self.conn.report_rows)
        elif "FROM company_intel.broker_research_facts" in normalized:
            self.rows = list(self.conn.fact_rows)
        elif "FROM company_intel.broker_reports" in normalized and "pdf_hash = %s" in normalized:
            self.rows = list(self.conn.hash_rows)
        elif "RETURNING research_run_id" in sql:
            self.rows = [(101,)]
        else:
            self.rows = []

    def executemany(self, sql, params):
        self.conn.executed.append((sql, list(params)))

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return list(self.rows)

    def fetchall(self):
        return list(self.rows)


class FakeConnection:
    def __init__(self):
        self.executed = []
        self.report_rows = []
        self.hash_rows = []
        self.fact_rows = []
        self.commits = 0

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.commits += 1


def test_parse_broker_index_command_defaults():
    options = parse_broker_index_command("/broker-index BEL")

    assert options == BrokerIndexOptions(symbol="BEL", broker="", all_public=False, refresh=False)


def test_parse_broker_index_command_flags():
    options = parse_broker_index_command("/broker-index bel --broker icici --all-public --refresh")

    assert options == BrokerIndexOptions(symbol="BEL", broker="icici", all_public=True, refresh=True)


def test_parse_broker_fetch_command_flags():
    options = parse_broker_fetch_command("/broker-fetch bel --broker icici --limit 5")

    assert options == BrokerFetchOptions(symbol="BEL", broker="icici", limit=5)


def test_render_broker_sources_has_research_only_framing():
    output = render_broker_sources(
        [
            {
                "broker_code": "icici",
                "broker_name": "ICICI Direct",
                "source_kind": "index_page",
                "access_mode": "public",
                "is_active": True,
                "source_url": ICICI_URL,
            }
        ]
    )

    assert "Not investment advice" in output
    assert "ICICI Direct" in output
    assert "public" in output


def test_handle_broker_index_command_uses_injected_html_without_network():
    conn = FakeConnection()
    html = '<a href="idirect_bharatelectronics_q3fy26.pdf">Bharat Electronics Q3FY26 Result Update</a>'

    output = handle_broker_index_command(
        "/broker-index BEL --broker icici",
        conn=conn,
        html_by_source_url={ICICI_URL: html},
    )

    executed_sql = "\n".join(sql for sql, _params in conn.executed)
    assert "Broker Index: BEL" in output
    assert "Links discovered: 1" in output
    assert "Symbol matches: 1" in output
    assert "INSERT INTO company_intel.broker_reports" in executed_sql


def test_handle_broker_fetch_command_fetches_and_parses_discovered_reports(tmp_path):
    conn = FakeConnection()
    conn.report_rows = [
        (
            88,
            "icici",
            "BEL",
            "https://www.icicidirect.com/mailcontent/idirect_bharatelectronics_q3fy26.pdf",
            "",
        )
    ]

    class Response:
        content = b"%PDF broker research"
        headers = {"content-type": "application/pdf"}

        def raise_for_status(self):
            return None

    def parser(path):
        return {"status": "ok", "pages": [{"page_number": 1, "text": "Broker page", "char_count": 11}]}

    output = handle_broker_fetch_command(
        "/broker-fetch BEL --broker icici --limit 1",
        conn=conn,
        root_dir=tmp_path,
        fetcher=lambda url: Response(),
        parser=parser,
    )

    executed_sql = "\n".join(sql for sql, _params in conn.executed)
    assert "Broker Fetch: BEL" in output
    assert "Fetched PDFs: 1" in output
    assert "Parsed reports: 1" in output
    assert "UPDATE company_intel.broker_reports" in executed_sql
    assert "INSERT INTO company_intel.broker_report_pages" in executed_sql


def test_handle_broker_research_command_writes_report_and_records_run(tmp_path):
    conn = FakeConnection()
    conn.fact_rows = [
        (1, "icici", "BEL", "ICICI BEL", "https://example.com/icici.pdf", "rating", "BUY", 1),
        (1, "icici", "BEL", "ICICI BEL", "https://example.com/icici.pdf", "target_price", "520", 1),
        (2, "hdfc_hsie", "BEL", "HSIE BEL", "https://example.com/hdfc.pdf", "rating", "ADD", 1),
        (2, "hdfc_hsie", "BEL", "HSIE BEL", "https://example.com/hdfc.pdf", "target_price", "475", 1),
    ]

    output = handle_broker_research_command(
        "/broker-research BEL",
        conn=conn,
        output_dir=tmp_path / "broker_research",
        latest_dir=tmp_path / "latest",
    )

    executed_sql = "\n".join(sql for sql, _params in conn.executed)
    assert "Broker Research: BEL" in output
    assert "reports/latest/broker_research_bel.html" not in output
    assert "HTML:" in output
    assert "INSERT INTO company_intel.broker_research_runs" in executed_sql
    assert (tmp_path / "latest" / "broker_research_bel.html").exists()


def test_handle_broker_research_command_accepts_report_broker_alias(tmp_path):
    conn = FakeConnection()
    conn.fact_rows = [(1, "icici", "BEL", "ICICI BEL", "https://example.com/icici.pdf", "rating", "BUY", 1)]

    output = handle_broker_research_command(
        "/report broker BEL html",
        conn=conn,
        output_dir=tmp_path / "broker_research",
        latest_dir=tmp_path / "latest",
    )

    assert "Broker Research: BEL" in output
    assert (tmp_path / "latest" / "broker_research_bel.html").exists()


def test_handle_broker_crawl_command_renders_scheduled_summary():
    conn = FakeConnection()

    def fake_runner(**kwargs):
        assert kwargs["symbol"] == "BEL"
        assert kwargs["max_sources"] == 2
        return ScheduledBrokerCrawlResult(
            symbol="BEL",
            sources_seen=2,
            sources_succeeded=2,
            sources_failed=0,
            links_discovered=4,
            reports_stored=3,
            skipped_sources=6,
            failures=[],
        )

    output = handle_broker_crawl_command("/broker-crawl BEL --max-sources 2", conn=conn, runner=fake_runner)

    assert "Broker Crawl: BEL" in output
    assert "Sources scanned: 2" in output
    assert "Reports stored: 3" in output
