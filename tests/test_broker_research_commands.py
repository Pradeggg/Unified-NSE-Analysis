from broker_research.commands import (
    BrokerIndexOptions,
    handle_broker_index_command,
    parse_broker_index_command,
    render_broker_sources,
)


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


def test_parse_broker_index_command_defaults():
    options = parse_broker_index_command("/broker-index BEL")

    assert options == BrokerIndexOptions(symbol="BEL", broker="", all_public=False, refresh=False)


def test_parse_broker_index_command_flags():
    options = parse_broker_index_command("/broker-index bel --broker icici --all-public --refresh")

    assert options == BrokerIndexOptions(symbol="BEL", broker="icici", all_public=True, refresh=True)


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
