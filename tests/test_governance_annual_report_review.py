from datetime import date

from terminal.governance.annual_report_review import (
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


def test_build_annual_report_review_payload_is_page_aware_and_bounded():
    payload = build_annual_report_review_payload(_report("AAA"), _annual_text(), max_chars=1200)

    assert payload["symbol"] == "AAA"
    assert payload["rating"] == "WATCH"
    assert payload["sections"]
    assert {section["page"] for section in payload["sections"]} >= {42, 52, 77, 88}
    assert "Corporate overview content" not in str(payload["sections"])
    assert len(str(payload["sections"])) <= 1600


def test_generate_annual_report_review_calls_llm_with_guardrails_and_schema():
    calls = []

    def fake_llm(*, system, user, schema, allow_deterministic_fallback=False, model=None):
        calls.append({"system": system, "user": user, "schema": schema, "fallback": allow_deterministic_fallback})
        return {
            "review_label": "Watch",
            "summary": "AAA has a clean audit section but still needs monitoring.",
            "audit_opinion": "Clean",
            "auditor": "Deloitte Haskins & Sells LLP",
            "strengths": ["Auditor report states true and fair view."],
            "concerns": [],
            "data_gaps": [],
            "watch_items": ["Track related-party transaction disclosures."],
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
    assert "unsupported facts" in calls[0]["system"].lower()
    assert "page references" in calls[0]["system"].lower()
    assert "Corporate overview content" not in calls[0]["user"]
    assert calls[0]["schema"]["additionalProperties"] is False
    assert calls[0]["fallback"] is False


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
        return {
            "review_label": "Buy",
            "summary": "Invalid",
            "audit_opinion": "Clean",
            "auditor": "Unknown",
            "strengths": [],
            "concerns": [],
            "data_gaps": [],
            "watch_items": [],
            "page_evidence": [],
            "needs_human_review": False,
            "research_only_disclaimer": "Research only.",
        }

    review = generate_annual_report_review(_report(), _annual_text(), llm_client=fake_llm)

    assert review["status"] == "invalid"
    assert "review_label" in review["error"]
