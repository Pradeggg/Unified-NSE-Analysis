from pathlib import Path

from broker_research.parse import parse_and_store_broker_report
from broker_research.storage import replace_report_pages, update_report_parse_status


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.conn.executed.append((sql, params))

    def executemany(self, sql, params):
        self.conn.executed.append((sql, list(params)))


class FakeConnection:
    def __init__(self):
        self.executed = []
        self.commits = 0

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.commits += 1


def test_replace_report_pages_deletes_existing_rows_and_inserts_pages():
    conn = FakeConnection()

    replace_report_pages(
        conn,
        broker_report_id=44,
        pages=[
            {"page_number": 1, "text": "Rating BUY target price Rs 520", "char_count": 30},
            {"page_number": 2, "text": "Risks include execution delay", "char_count": 29},
        ],
    )

    delete_sql, delete_params = conn.executed[0]
    insert_sql, insert_params = conn.executed[1]
    assert "DELETE FROM company_intel.broker_report_pages" in delete_sql
    assert delete_params == (44,)
    assert "INSERT INTO company_intel.broker_report_pages" in insert_sql
    assert insert_params == [
        (44, 1, "Rating BUY target price Rs 520", 30),
        (44, 2, "Risks include execution delay", 29),
    ]
    assert conn.commits == 1


def test_parse_and_store_broker_report_uses_parser_and_updates_status(tmp_path):
    conn = FakeConnection()
    pdf_path = tmp_path / "report.pdf"
    pdf_path.write_bytes(b"%PDF")

    def fake_parser(path: Path):
        assert path == pdf_path
        return {
            "status": "ok",
            "pages": [
                {"page_number": 1, "text": "Broker thesis page", "char_count": 18},
            ],
        }

    result = parse_and_store_broker_report(
        conn,
        broker_report_id=51,
        local_path=str(pdf_path),
        parser=fake_parser,
    )

    executed = "\n".join(sql for sql, _params in conn.executed)
    assert result["status"] == "ok"
    assert result["pages_stored"] == 1
    assert result["parse_status"] == "parsed"
    assert result["pages"] == [{"page_number": 1, "text": "Broker thesis page", "char_count": 18}]
    assert "INSERT INTO company_intel.broker_report_pages" in executed
    assert "UPDATE company_intel.broker_reports" in executed


def test_update_report_parse_status_uses_broker_reports():
    conn = FakeConnection()

    update_report_parse_status(conn, broker_report_id=7, parse_status="parse_failed")

    sql, params = conn.executed[0]
    assert "UPDATE company_intel.broker_reports" in sql
    assert params == ("parse_failed", 7)
