from hashlib import sha256
from pathlib import Path

from broker_research.fetch import fetch_broker_report_pdf
from broker_research.storage import find_report_by_hash, update_report_fetch_metadata


class FakeResponse:
    def __init__(self, content: bytes, content_type: str = "application/pdf"):
        self.content = content
        self.headers = {"content-type": content_type}

    def raise_for_status(self):
        return None


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
        if "FROM company_intel.broker_reports" in normalized and "pdf_hash = %s" in normalized:
            self.rows = list(self.conn.hash_rows)
        else:
            self.rows = []

    def fetchone(self):
        return self.rows[0] if self.rows else None


class FakeConnection:
    def __init__(self, hash_rows=None):
        self.hash_rows = hash_rows or []
        self.executed = []
        self.commits = 0

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.commits += 1


def test_fetch_broker_report_pdf_writes_hash_named_file(tmp_path):
    content = b"%PDF broker research"
    expected_hash = sha256(content).hexdigest()

    result = fetch_broker_report_pdf(
        broker_code="icici",
        symbol="BEL",
        pdf_url="https://www.icicidirect.com/mailcontent/idirect_bharatelectronics_q3fy26.pdf",
        root_dir=tmp_path,
        fetcher=lambda url: FakeResponse(content),
    )

    assert result["status"] == "ok"
    assert result["pdf_hash"] == expected_hash
    assert result["content_length"] == len(content)
    assert Path(result["local_path"]).exists()
    assert Path(result["local_path"]).read_bytes() == content
    assert "icici/BEL" in result["local_path"]


def test_fetch_broker_report_pdf_blocks_oversized_content(tmp_path):
    result = fetch_broker_report_pdf(
        broker_code="icici",
        symbol="BEL",
        pdf_url="https://example.com/large.pdf",
        root_dir=tmp_path,
        fetcher=lambda url: FakeResponse(b"123456"),
        max_bytes=4,
    )

    assert result["status"] == "pdf_too_large"
    assert result["local_path"] == ""
    assert result["content_length"] == 6
    assert not list(tmp_path.rglob("*.pdf"))


def test_report_hash_lookup_and_fetch_metadata_update_use_broker_tables():
    existing_hash = "abc123"
    conn = FakeConnection(hash_rows=[(9, "hdfc_hsie", "BEL", "reports/existing.pdf")])

    duplicate = find_report_by_hash(conn, existing_hash)
    update_report_fetch_metadata(
        conn,
        broker_report_id=11,
        fetch_status="duplicate_pdf",
        pdf_hash=existing_hash,
        local_path=duplicate["local_path"],
    )

    executed = "\n".join(sql for sql, _params in conn.executed)
    assert duplicate == {
        "broker_report_id": 9,
        "broker_code": "hdfc_hsie",
        "symbol": "BEL",
        "local_path": "reports/existing.pdf",
    }
    assert "FROM company_intel.broker_reports" in executed
    assert "UPDATE company_intel.broker_reports" in executed
    assert conn.commits == 1
