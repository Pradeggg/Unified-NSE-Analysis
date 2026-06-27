from datetime import date
import json

from terminal.governance.annual_report_review import (
    build_annual_report_review_sections,
    build_annual_report_review_payload,
    generate_annual_report_review,
)
from terminal.governance.models import GovernanceEvidence, GovernanceReport


def _report(symbol: str = "AAA") -> GovernanceReport:
    return GovernanceReport(
        symbol=symbol,
        as_of=date(2026, 6, 27),
        score=72,
        rating="WATCH",
        confidence="Medium",
        component_scores=[],
        flags=["Amber governance announcement detected"],
        evidence=GovernanceEvidence(symbol=symbol, as_of=date(2026, 6, 27)),
        source_trail=[],
        missing_evidence=[],
        llm_status="not_requested",
    )


def _annual_text() -> str:
    return """
--- Page 4 ---
Corporate overview content.

--- Page 42 ---
Independent Auditor's Report
Opinion
In our opinion the financial statements give a true and fair view.
For Deloitte Haskins & Sells LLP
Key Audit Matters
Revenue recognition was a key audit matter.

--- Page 52 ---
Annexure A to the Independent Auditor's Report
The company has an internal audit system commensurate with size.
No fraud by the company has been noticed or reported during the year.

--- Page 77 ---
Related Party Transactions
All related party transactions were placed before the audit committee.

--- Page 88 ---
Corporate Governance Report
The company has a whistle blower mechanism and vigil mechanism.
""".strip()


def test_auditor_opinion_section_ignores_governance_and_ceo_cfo_certificates():
    text = """
--- Page 61 ---
Independent Auditor's Certificate on Corporate Governance
It is neither an audit nor an expression of opinion on the financial statements of the Company.

--- Page 142 ---
CEO and CFO Certification
The financial statements present a true and fair view in all material respects.

--- Page 144 ---
Independent Auditor's Report
Standalone Financial Statements
Opinion
In our opinion the financial statements give a true and fair view.
For Deloitte Haskins & Sells LLP
""".strip()

    sections = build_annual_report_review_sections(text)
    auditor = next(section for section in sections if section["section_id"] == "auditor_opinion")

    assert auditor["pages"] == [144]


def test_build_annual_report_review_payload_is_page_aware_and_bounded():
    payload = build_annual_report_review_payload(_report("AAA"), _annual_text(), max_chars=1200)

    assert payload["symbol"] == "AAA"
    assert payload["rating"] == "WATCH"
    assert payload["sections"]
    assert {section["page"] for section in payload["sections"]} >= {42, 52, 77, 88}
    assert "Corporate overview content" not in str(payload["sections"])
    assert len(str(payload["sections"])) <= 1600


def test_build_annual_report_review_sections_groups_pages_by_review_topic():
    sections = build_annual_report_review_sections(_annual_text(), max_chars_per_section=900)
    by_id = {section["section_id"]: section for section in sections}

    assert {"auditor_opinion", "caro_and_fraud", "related_party", "corporate_governance"} <= set(by_id)
    assert by_id["auditor_opinion"]["pages"] == [42]
    assert by_id["caro_and_fraud"]["pages"] == [52]
    assert by_id["related_party"]["pages"] == [77]
    assert by_id["corporate_governance"]["pages"] == [88]
    assert "Corporate overview content" not in str(sections)


def test_generate_annual_report_review_calls_llm_with_guardrails_and_schema():
    calls = []

    def fake_llm(*, system, user, schema, allow_deterministic_fallback=False, model=None):
        calls.append({"system": system, "user": user, "schema": schema, "fallback": allow_deterministic_fallback})
        payload = json.loads(user)
        if payload["mode"] == "section_review":
            section = payload["section"]
            return {
                "section_id": section["section_id"],
                "title": section["title"],
                "status": "ok",
                "risk_label": "Watch",
                "key_findings": [f"Reviewed {section['title']}"],
                "concerns": [],
                "data_gaps": [],
                "page_evidence": [
                    {
                        "page": section["pages"][0],
                        "finding": "Section evidence reviewed.",
                        "quote": "true and fair view",
                    }
                ],
                "needs_human_review": False,
            }
        return {
            "review_label": "Watch",
            "summary": "AAA has a clean audit section but still needs monitoring.",
            "audit_opinion": "Clean",
            "auditor": "Deloitte Haskins & Sells LLP",
            "strengths": ["Auditor report states true and fair view."],
            "concerns": [],
            "data_gaps": [],
            "watch_items": ["Track related-party transaction disclosures."],
            "key_findings": ["Clean audit language identified."],
            "parser_mismatches": [],
            "human_review_checklist": ["Review related-party note in full report."],
            "page_evidence": [
                {
                    "page": 42,
                    "finding": "Clean audit language identified.",
                    "quote": "true and fair view",
                }
            ],
            "needs_human_review": False,
            "research_only_disclaimer": "Research-only governance review; not investment advice.",
        }

    review = generate_annual_report_review(_report(), _annual_text(), llm_client=fake_llm)

    assert review["status"] == "ok"
    assert review["review_label"] == "Watch"
    assert review["section_reviews"]
    assert review["key_findings"] == ["Clean audit language identified."]
    assert any(call["schema"]["additionalProperties"] is False for call in calls)
    assert all(call["fallback"] is False for call in calls)
    assert any("unsupported facts" in call["system"].lower() for call in calls)
    assert any("page references" in call["system"].lower() for call in calls)
    assert all("Corporate overview content" not in call["user"] for call in calls)
    modes = [json.loads(call["user"])["mode"] for call in calls]
    assert modes.count("section_review") >= 4
    assert modes[-1] == "annual_report_synthesis"


def test_generate_annual_report_review_continues_when_one_section_llm_call_fails():
    calls = []

    def fake_llm(*, system, user, schema, allow_deterministic_fallback=False, model=None):
        payload = json.loads(user)
        calls.append(payload["mode"])
        if payload["mode"] == "section_review":
            section = payload["section"]
            if section["section_id"] == "related_party":
                raise RuntimeError("provider timeout")
            return {
                "section_id": section["section_id"],
                "title": section["title"],
                "status": "ok",
                "risk_label": "Clean",
                "key_findings": ["Reviewed"],
                "concerns": [],
                "data_gaps": [],
                "page_evidence": [],
                "needs_human_review": False,
            }
        return {
            "review_label": "Watch",
            "summary": "One section was unavailable.",
            "audit_opinion": "Clean",
            "auditor": "Deloitte Haskins & Sells LLP",
            "strengths": [],
            "concerns": ["Related-party section review unavailable."],
            "data_gaps": ["related_party"],
            "watch_items": [],
            "key_findings": ["Clean audit language"],
            "parser_mismatches": [],
            "human_review_checklist": ["Retry related-party section."],
            "page_evidence": [],
            "needs_human_review": True,
            "research_only_disclaimer": "Research only.",
        }

    review = generate_annual_report_review(_report(), _annual_text(), llm_client=fake_llm)

    assert review["status"] == "ok"
    failed = [section for section in review["section_reviews"] if section["section_id"] == "related_party"][0]
    assert failed["status"] == "unavailable"
    assert failed["risk_label"] == "Insufficient Evidence"
    assert review["needs_human_review"] is True
    assert calls[-1] == "annual_report_synthesis"


def test_generate_annual_report_review_rejects_missing_text_without_calling_llm():
    calls = []

    def fake_llm(**kwargs):
        calls.append(kwargs)
        return {}

    review = generate_annual_report_review(_report(), "", llm_client=fake_llm)

    assert review["status"] == "missing"
    assert "annual report text" in review["error"].lower()
    assert calls == []


def test_generate_annual_report_review_rejects_invalid_labels():
    def fake_llm(**kwargs):
        payload = json.loads(kwargs["user"])
        if payload["mode"] == "section_review":
            section = payload["section"]
            return {
                "section_id": section["section_id"],
                "title": section["title"],
                "status": "ok",
                "risk_label": "Watch",
                "key_findings": [],
                "concerns": [],
                "data_gaps": [],
                "page_evidence": [],
                "needs_human_review": False,
            }
        return {
            "review_label": "Buy",
            "summary": "Invalid",
            "audit_opinion": "Clean",
            "auditor": "Unknown",
            "strengths": [],
            "concerns": [],
            "data_gaps": [],
            "watch_items": [],
            "key_findings": [],
            "parser_mismatches": [],
            "human_review_checklist": [],
            "page_evidence": [],
            "needs_human_review": False,
            "research_only_disclaimer": "Research only.",
        }

    review = generate_annual_report_review(_report(), _annual_text(), llm_client=fake_llm)

    assert review["status"] == "invalid"
    assert "review_label" in review["error"]
