import json
import subprocess
import sys
from datetime import date

from terminal.governance.engine import evaluate_governance, main
from terminal.governance.markdown import render_markdown
from terminal.governance.models import ComponentScore, GovernanceRawSources


def _raw_sources():
    return GovernanceRawSources(
        symbol="AAA",
        shareholding_payloads=[
            {
                "data": [
                    {
                        "quarter": "Jun 2026",
                        "promoterAndPromoterGroupShareHolding": "55",
                        "pledgedSharesPercent": "0",
                        "pledgedSharesPercentOfTotalShareCapital": "0",
                        "fii": "15",
                        "dii": "20",
                        "public": "10",
                    }
                ]
            }
        ],
        insider_payloads=[
            {
                "data": [
                    {
                        "symbol": "AAA",
                        "acqName": "Promoter",
                        "personCategory": "Promoter",
                        "tdpTransactionType": "Acquisition",
                        "secAcq": "10000",
                        "buyValue": "12000000",
                        "date": "01-Jun-2026",
                    }
                ]
            }
        ],
        complaint_payloads=[{"data": [{"totalComplaints": "2", "pendingComplaints": "0"}]}],
        screener_payload={
            "annual_pl": {"_headers": ["Mar 2026"], "Net Profit": ["100"], "Dividend Payout %": ["30"]},
            "cash_flow": {"_headers": ["Mar 2026"], "Cash from Operating Activity": ["110"]},
        },
    )


def test_evaluate_governance_builds_json_serializable_report_without_llm():
    report = evaluate_governance("aaa", raw_sources=_raw_sources(), as_of=date(2026, 6, 27), use_llm=False)

    data = report.to_dict()

    assert report.symbol == "AAA"
    assert data["as_of"] == "2026-06-27"
    assert data["llm_status"] == "not_requested"
    json.dumps(data)


def test_evaluate_governance_attaches_llm_opinion_when_requested():
    def fake_llm(**kwargs):
        return {
            "opinion_label": "Strong",
            "summary": "AAA has strong governance evidence.",
            "strengths": ["No pledge"],
            "concerns": [],
            "data_gaps": [],
            "watch_items": [],
            "research_only_disclaimer": "Research only; not investment advice.",
        }

    report = evaluate_governance(
        "AAA",
        raw_sources=_raw_sources(),
        as_of=date(2026, 6, 27),
        use_llm=True,
        llm_client=fake_llm,
    )

    assert report.llm_status == "ok"
    assert report.llm_opinion["opinion_label"] == "Strong"


def test_evaluate_governance_records_non_ok_llm_status_without_opinion():
    def fake_llm(**kwargs):
        return {
            "opinion_label": "Buy",
            "summary": "Invalid label",
            "strengths": [],
            "concerns": [],
            "data_gaps": [],
            "watch_items": [],
            "research_only_disclaimer": "Research only.",
        }

    report = evaluate_governance(
        "AAA",
        raw_sources=_raw_sources(),
        as_of=date(2026, 6, 27),
        use_llm=True,
        llm_client=fake_llm,
    )

    assert report.llm_status == "invalid"
    assert report.llm_opinion is None


def test_evaluate_governance_synthesizes_missing_evidence_for_empty_raw_sources():
    report = evaluate_governance(
        "AAA",
        raw_sources=GovernanceRawSources(symbol="AAA"),
        as_of=date(2026, 6, 27),
        use_llm=False,
    )

    fields = {item.field for item in report.missing_evidence}

    assert {"shareholding", "insider_disclosures", "annual_report_text", "corporate_events"} <= fields


def test_markdown_renders_score_flags_sources_and_disclaimer():
    report = evaluate_governance("AAA", raw_sources=_raw_sources(), as_of=date(2026, 6, 27), use_llm=False)

    text = render_markdown(report)

    assert "# Governance Evaluation - AAA" in text
    assert "Score:" in text
    assert "Source Trail" in text
    assert "Research-only" in text


def test_markdown_escapes_table_and_list_content():
    report = evaluate_governance("AAA", raw_sources=_raw_sources(), as_of=date(2026, 6, 27), use_llm=False)
    report.component_scores.append(
        ComponentScore("bad|name", 1, 2, "amber", ["note | value\nsecond"], ["source|x"])
    )
    report.flags.append("# injected\n- list")

    text = render_markdown(report)

    assert "bad\\|name" in text
    assert "note \\| value second" in text
    assert "- injected - list" in text


def test_main_prints_json_with_injected_evaluator(capsys):
    def evaluator(symbol, **kwargs):
        return evaluate_governance(symbol, raw_sources=_raw_sources(), as_of=date(2026, 6, 27), use_llm=False)

    code = main(["AAA", "--json"], evaluator=evaluator)

    out = capsys.readouterr().out
    assert code == 0
    assert '"symbol": "AAA"' in out


def test_main_forwards_llm_flag_to_injected_evaluator(capsys):
    calls = []

    def evaluator(symbol, **kwargs):
        calls.append(kwargs)
        return evaluate_governance(symbol, raw_sources=_raw_sources(), as_of=date(2026, 6, 27), use_llm=False)

    code = main(["AAA", "--json", "--llm"], evaluator=evaluator)

    capsys.readouterr()
    assert code == 0
    assert calls[0]["use_llm"] is True


def test_module_cli_prints_json_without_runpy_warning():
    result = subprocess.run(
        [sys.executable, "-m", "terminal.governance.engine", "INFY", "--json"],
        check=True,
        capture_output=True,
        text=True,
    )

    data = json.loads(result.stdout)
    assert data["symbol"] == "INFY"
    assert data["llm_status"] == "not_requested"
    assert "RuntimeWarning" not in result.stderr
