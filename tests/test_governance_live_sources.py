import json
from pathlib import Path

from terminal.governance.live_sources import extract_annual_report_text_from_pdf_bytes, refresh_live_sources


class FakeNSEClient:
    def __init__(self):
        self.calls = []

    def get_json(self, path, params=None, retries=1):
        self.calls.append((path, params, retries))
        return {
            "status": "ok",
            "json": {
                "data": [
                    {
                        "symbol": "INFY",
                        "acqName": "Infosys Employee Benefits Trust",
                        "personCategory": "Trust",
                        "tdpTransactionType": "Sell",
                        "secAcq": "1000",
                        "sellValue": "12000000",
                        "date": "01-Jun-2026",
                    }
                ]
            },
            "url": "https://www.nseindia.com/api/corporates-pit",
            "status_code": 200,
        }


def _screener_payload():
    return {
        "symbol": "INFY",
        "source_url": "https://www.screener.in/company/INFY/consolidated/",
        "shareholding": {
            "_quarters": ["Dec 2025", "Mar 2026"],
            "Promoters_trend": ["14.6%", "14.5%"],
            "FIIs_trend": ["31.5%", "32.1%"],
            "DIIs_trend": ["38.9%", "39.5%"],
            "Public_trend": ["15.0%", "13.9%"],
        },
        "annual_pl": {
            "_headers": ["Mar 2024", "Mar 2025", "Mar 2026"],
            "Net Profit+": ["100", "120", "140"],
            "Dividend Payout %": ["40", "42", "45"],
        },
        "cash_flow": {
            "_headers": ["Mar 2024", "Mar 2025", "Mar 2026"],
            "Cash from Operating Activity+": ["110", "135", "150"],
        },
        "annual_reports": [{"label": "Annual Report", "url": "https://example.test/infy.pdf#page=200"}],
    }


def _announcements(symbol, max_results=8):
    return {
        "symbol": symbol,
        "bse_filings": [
            {
                "subject": "Board meeting outcome",
                "url": "https://example.test/board.pdf",
                "source_site": "bseindia.com",
            }
        ],
        "nse_filings": [
            {
                "date": "01-Jun-2026",
                "subject": "Analyst meeting",
                "url": "https://example.test/analyst.pdf",
            }
        ],
    }


def _corporate_actions(symbol, max_results=8):
    return {
        "symbol": symbol,
        "all": [
            {
                "ex_date": "10-Jun-2026",
                "subject": "Dividend - Rs 25 Per Share",
            }
        ],
    }


def _pdf_bytes():
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(
        (72, 72),
        "Board report prose except for fair value instruments.\n"
        "Independent Auditor's Report\n"
        "To the Members of Infosys Limited\n"
        "For Deloitte Haskins & Sells LLP\n"
        "In our opinion the financial statements give a true and fair view.\n"
        "Key Audit Matter 1 Revenue recognition\n",
    )
    payload = doc.tobytes()
    doc.close()
    return payload


def test_extract_annual_report_text_from_pdf_bytes_finds_auditor_report_heading():
    text, metadata = extract_annual_report_text_from_pdf_bytes(_pdf_bytes(), pages_after_heading=5)

    assert "Independent Auditor's Report" in text
    assert "Board report prose" in text
    assert metadata["start_page"] == 1
    assert metadata["pages"] == [1, 1]


def test_refresh_live_sources_returns_raw_sources_and_writes_governance_cache(tmp_path):
    raw = refresh_live_sources(
        "infy",
        data_dir=tmp_path,
        nse_client=FakeNSEClient(),
        announcements_fetcher=_announcements,
        corporate_actions_fetcher=_corporate_actions,
        screener_fetcher=lambda symbol: _screener_payload(),
        pdf_fetcher=lambda url: _pdf_bytes(),
    )

    assert raw.symbol == "INFY"
    assert len(raw.insider_payloads[0]["data"]) == 1
    assert raw.shareholding_payloads[0]["data"][1]["quarter"] == "Mar 2026"
    assert raw.shareholding_payloads[0]["data"][1]["fii"] == "32.1%"
    assert len(raw.announcement_rows) == 3
    assert "Independent Auditor's Report" in (raw.annual_report_text or "")
    assert raw.screener_payload["symbol"] == "INFY"
    assert {entry.name for entry in raw.source_trail} >= {
        "live.nse.pit",
        "live.screener.company",
        "live.announcements",
        "live.corporate_actions",
        "live.annual_report",
    }

    root = tmp_path / "governance" / "INFY"
    assert (root / "manifest.json").exists()
    assert (root / "raw" / "nse_pit.json").exists()
    assert (root / "raw" / "announcements.json").exists()
    assert (root / "raw" / "corporate_actions.json").exists()
    assert (root / "raw" / "screener.json").exists()
    assert (root / "raw" / "annual_report_text.txt").exists()
    parsed = json.loads((root / "parsed" / "raw_sources.json").read_text(encoding="utf-8"))
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    assert parsed["symbol"] == "INFY"
    assert parsed["annual_report_text"]
    assert manifest["symbol"] == "INFY"
    assert manifest["source_count"] == len(raw.source_trail)


def test_refresh_live_sources_records_source_errors_without_raising(tmp_path):
    def bad_screener(symbol):
        return {"symbol": symbol, "error": "blocked"}

    raw = refresh_live_sources(
        "INFY",
        data_dir=tmp_path,
        nse_client=FakeNSEClient(),
        announcements_fetcher=lambda symbol, max_results=8: {"symbol": symbol, "error": "announcements down"},
        corporate_actions_fetcher=lambda symbol, max_results=8: {"symbol": symbol, "error": "actions down"},
        screener_fetcher=bad_screener,
        pdf_fetcher=lambda url: b"",
    )

    statuses = {entry.name: entry for entry in raw.source_trail}
    assert statuses["live.screener.company"].status == "error"
    assert statuses["live.announcements"].status == "error"
    assert statuses["live.corporate_actions"].status == "error"
    assert any(item.field == "screener_payload" for item in raw.missing_evidence)
    assert not raw.shareholding_payloads[0]["data"]
