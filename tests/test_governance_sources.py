import json
from datetime import date

from terminal.governance.cache_sources import load_cached_sources
from terminal.governance.models import GovernanceMissingEvidence, GovernanceRawSources, GovernanceSource
from terminal.governance.nse_client import NSEJsonClient


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self):
        self.headers = {}
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params, timeout))
        if url == "https://www.nseindia.com":
            return FakeResponse(200, {})
        return FakeResponse(200, {"data": [{"symbol": "AAA"}]})


class ErrorSession(FakeSession):
    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params, timeout))
        if url == "https://www.nseindia.com":
            return FakeResponse(200, {})
        return FakeResponse(503, {"error": "down"})


class SeedFailureThenSuccessSession(FakeSession):
    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params, timeout))
        if url == "https://www.nseindia.com":
            if sum(1 for call in self.calls if call[0] == url) == 1:
                raise RuntimeError("seed failed")
            return FakeResponse(200, {})
        return FakeResponse(200, {"data": [{"symbol": "AAA"}]})


def test_load_cached_sources_filters_symbol_and_records_missing_files(tmp_path):
    data_dir = tmp_path
    cache = data_dir / "_insider_cache"
    cache.mkdir()
    (cache / "pit_2026-06-25.json").write_text(
        json.dumps(
            [
                {"symbol": "AAA", "acqName": "Promoter", "tdpTransactionType": "Disposal"},
                {"symbol": "BBB", "acqName": "Other", "tdpTransactionType": "Acquisition"},
                {"acqName": "No Symbol", "tdpTransactionType": "Disposal"},
            ]
        ),
        encoding="utf-8",
    )
    (cache / "bulk_2026-06-25.csv").write_text(
        "DATE,SYMBOL,ENTITY,SIDE,QTY,PRICE,SOURCE\n"
        "25-Jun-2026,AAA,Fund A,BUY,1000,25,BULK_DEAL\n"
        "25-Jun-2026,,Fund B,BUY,1000,25,BULK_DEAL\n",
        encoding="utf-8",
    )
    (data_dir / "corporate_events.csv").write_text(
        "SYMBOL,EVENT_TYPE,EVENT_DATE,PURPOSE_RAW,DETAIL,SOURCE\n"
        "AAA,AGM,2026-06-30,Annual General Meeting,,NSE\n"
        ",BOARD,2026-06-30,No Symbol Event,,NSE\n",
        encoding="utf-8",
    )

    raw = load_cached_sources("AAA", data_dir=data_dir)

    assert raw.symbol == "AAA"
    assert len(raw.insider_payloads) == 1
    assert len(raw.insider_payloads[0]["data"]) == 1
    assert raw.insider_payloads[0]["data"][0]["symbol"] == "AAA"
    assert len(raw.deal_rows) == 1
    assert raw.announcement_rows[0]["SYMBOL"] == "AAA"
    assert raw.announcement_rows[0]["SUBJECT"] == "Annual General Meeting"
    assert {entry.name for entry in raw.source_trail} >= {
        "cache.pit",
        "cache.bulk_block_deals",
        "cache.corporate_events",
    }


def test_load_cached_sources_prefers_governance_raw_sources_cache(tmp_path):
    parsed_dir = tmp_path / "governance" / "INFY" / "parsed"
    parsed_dir.mkdir(parents=True)
    cached = GovernanceRawSources(
        symbol="INFY",
        shareholding_payloads=[{"data": [{"quarter": "Mar 2026", "promoter_pct": "14.5"}]}],
        insider_payloads=[{"data": [{"symbol": "INFY", "acqName": "Trust"}]}],
        announcement_rows=[{"SYMBOL": "INFY", "subject": "Board meeting"}],
        screener_payload={"symbol": "INFY"},
        annual_report_text="Independent Auditor's Report",
        source_trail=[
            GovernanceSource(
                name="live.screener.company",
                status="ok",
                rows=1,
                latest_date=date(2026, 6, 27),
                fallback=True,
            )
        ],
        missing_evidence=[
            GovernanceMissingEvidence(
                scope="governance",
                subject="INFY",
                field="complaints",
                severity="warn",
                reason="Not fetched",
            )
        ],
    )
    (parsed_dir / "raw_sources.json").write_text(json.dumps(cached.to_dict()), encoding="utf-8")

    raw = load_cached_sources("INFY", data_dir=tmp_path)

    assert raw.symbol == "INFY"
    assert raw.shareholding_payloads[0]["data"][0]["quarter"] == "Mar 2026"
    assert raw.annual_report_text == "Independent Auditor's Report"
    assert raw.screener_payload == {"symbol": "INFY"}
    assert raw.source_trail[0].name == "live.screener.company"
    assert raw.source_trail[0].latest_date == date(2026, 6, 27)
    assert raw.missing_evidence[0].field == "complaints"


def test_load_cached_sources_uses_non_blank_corporate_event_subject_fallback(tmp_path):
    cache = tmp_path / "_insider_cache"
    cache.mkdir()
    (cache / "pit_2026-06-25.json").write_text(json.dumps([{"symbol": "AAA"}]), encoding="utf-8")
    (cache / "bulk_2026-06-25.csv").write_text("DATE,SYMBOL\n25-Jun-2026,AAA\n", encoding="utf-8")
    (tmp_path / "corporate_events.csv").write_text(
        "SYMBOL,EVENT_TYPE,EVENT_DATE,PURPOSE_RAW,DETAIL,SOURCE\n"
        "AAA,BOARD,2026-06-30,   ,Board resignation,NSE\n",
        encoding="utf-8",
    )

    raw = load_cached_sources("AAA", data_dir=tmp_path)

    assert raw.announcement_rows[0]["SUBJECT"] == "Board resignation"


def test_load_cached_sources_marks_missing_deal_files(tmp_path):
    cache = tmp_path / "_insider_cache"
    cache.mkdir()
    (cache / "pit_2026-06-25.json").write_text(json.dumps([{"symbol": "AAA"}]), encoding="utf-8")

    raw = load_cached_sources("AAA", data_dir=tmp_path)

    deal_source = next(entry for entry in raw.source_trail if entry.name == "cache.bulk_block_deals")
    assert deal_source.status == "missing"
    assert any(item.field == "bulk_block_deals" for item in raw.missing_evidence)


def test_load_cached_sources_records_malformed_deal_csv_headers(tmp_path):
    cache = tmp_path / "_insider_cache"
    cache.mkdir()
    (cache / "pit_2026-06-25.json").write_text(json.dumps([{"symbol": "AAA"}]), encoding="utf-8")
    (cache / "bulk_2026-06-25.csv").write_text("DATE,ENTITY\n25-Jun-2026,Fund A\n", encoding="utf-8")

    raw = load_cached_sources("AAA", data_dir=tmp_path)

    deal_error = next(
        entry for entry in raw.source_trail if entry.name == "cache.bulk_block_deals" and entry.status == "error"
    )
    aggregate = raw.source_trail[-1]
    assert deal_error.error and "SYMBOL" in deal_error.error
    assert aggregate.name == "cache.bulk_block_deals"
    assert aggregate.status == "degraded"
    assert aggregate.metadata["failed_files"] == ["bulk_2026-06-25.csv"]


def test_load_cached_sources_records_malformed_pit_as_error(tmp_path):
    cache = tmp_path / "_insider_cache"
    cache.mkdir()
    (cache / "pit_2026-06-25.json").write_text("{bad", encoding="utf-8")

    raw = load_cached_sources("AAA", data_dir=tmp_path)

    pit_source = next(entry for entry in raw.source_trail if entry.name == "cache.pit")
    assert pit_source.status == "error"
    assert pit_source.error


def test_nse_json_client_returns_error_source_shape_without_raising():
    session = FakeSession()
    client = NSEJsonClient(session=session, seed_delay_s=0)

    result = client.get_json("/api/test", params={"symbol": "AAA"})

    assert result["status"] == "ok"
    assert result["json"] == {"data": [{"symbol": "AAA"}]}
    assert session.calls[0][0] == "https://www.nseindia.com"
    assert result["url"] == "https://www.nseindia.com/api/test"


def test_nse_json_client_http_error_includes_status_code_and_url():
    session = ErrorSession()
    client = NSEJsonClient(session=session, seed_delay_s=0)

    result = client.get_json("/api/test", params={"symbol": "AAA"}, retries=0)

    assert result["status"] == "error"
    assert result["status_code"] == 503
    assert result["url"] == "https://www.nseindia.com/api/test"
    assert "HTTP 503" in result["error"]


def test_nse_json_client_retries_seed_after_seed_failure():
    session = SeedFailureThenSuccessSession()
    client = NSEJsonClient(session=session, seed_delay_s=0)

    first = client.get_json("/api/test", retries=0)
    second = client.get_json("/api/test", retries=0)

    seed_calls = [call for call in session.calls if call[0] == "https://www.nseindia.com"]
    assert first["status"] == "ok"
    assert second["status"] == "ok"
    assert len(seed_calls) == 2
