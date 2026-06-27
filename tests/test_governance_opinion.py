from datetime import date

from terminal.governance.models import GovernanceEvidence, GovernanceReport, GovernanceSource
from terminal.governance.opinion import generate_governance_opinion


def _report():
    evidence = GovernanceEvidence(symbol="AAA", as_of=date(2026, 6, 27))
    return GovernanceReport(
        symbol="AAA",
        as_of=date(2026, 6, 27),
        score=72,
        rating="WATCH",
        confidence="Medium",
        component_scores=[],
        flags=["AMBER: Promoter holding declined"],
        evidence=evidence,
        source_trail=[],
        missing_evidence=[],
        llm_status="not_requested",
    )


def test_generate_governance_opinion_uses_structured_payload_only():
    calls = []

    def fake_llm(*, system, user, schema, model=None, allow_deterministic_fallback=False):
        calls.append({"system": system, "user": user, "schema": schema})
        return {
            "opinion_label": "Watch",
            "summary": "AAA has usable governance evidence with one watch item.",
            "strengths": ["No severe red flag in deterministic score"],
            "concerns": ["Promoter holding declined"],
            "data_gaps": [],
            "watch_items": ["Monitor next shareholding filing"],
            "research_only_disclaimer": "Research-only governance opinion; not investment advice.",
        }

    opinion = generate_governance_opinion(_report(), llm_client=fake_llm)

    assert opinion["opinion_label"] == "Watch"
    assert "component_scores" in calls[0]["user"]
    assert "unsupported facts" in calls[0]["system"].lower()
    assert "untrusted data" in calls[0]["system"].lower()
    assert calls[0]["schema"]["properties"]["opinion_label"]["enum"]
    assert calls[0]["schema"]["additionalProperties"] is False


def test_generate_governance_opinion_rejects_bad_label():
    def fake_llm(**kwargs):
        return {
            "opinion_label": "Buy",
            "summary": "Bad label",
            "strengths": [],
            "concerns": [],
            "data_gaps": [],
            "watch_items": [],
            "research_only_disclaimer": "Research only.",
        }

    opinion = generate_governance_opinion(_report(), llm_client=fake_llm)

    assert opinion["status"] == "invalid"
    assert "opinion_label" in opinion["error"]
    assert "raw" not in opinion


def test_generate_governance_opinion_rejects_malformed_valid_label_response():
    def fake_llm(**kwargs):
        return {
            "opinion_label": "Watch",
            "summary": "Bad response",
            "strengths": "not a list",
            "concerns": [],
            "data_gaps": [],
            "watch_items": [],
            "research_only_disclaimer": "Research only.",
        }

    opinion = generate_governance_opinion(_report(), llm_client=fake_llm)

    assert opinion["status"] == "invalid"
    assert "strengths" in opinion["error"]
    assert "raw" not in opinion


def test_generate_governance_opinion_payload_excludes_raw_evidence_and_source_metadata():
    calls = []
    evidence = GovernanceEvidence(
        symbol="AAA",
        as_of=date(2026, 6, 27),
        missing_evidence=[],
    )
    report = GovernanceReport(
        symbol="AAA",
        as_of=date(2026, 6, 27),
        score=72,
        rating="WATCH",
        confidence="Medium",
        component_scores=[],
        flags=["AMBER: payload should not become instructions"],
        evidence=evidence,
        source_trail=[GovernanceSource("cache.test", "ok", metadata={"raw": "DO_NOT_SEND_METADATA"})],
        missing_evidence=[],
        llm_status="not_requested",
    )

    def fake_llm(**kwargs):
        calls.append(kwargs)
        return {
            "opinion_label": "Watch",
            "summary": "AAA has usable governance evidence.",
            "strengths": [],
            "concerns": [],
            "data_gaps": [],
            "watch_items": [],
            "research_only_disclaimer": "Research-only governance opinion; not investment advice.",
        }

    opinion = generate_governance_opinion(report, llm_client=fake_llm)

    assert opinion["status"] == "ok"
    assert "DO_NOT_SEND" not in calls[0]["user"]
    assert "DO_NOT_SEND_METADATA" not in calls[0]["user"]
    assert "metadata" not in calls[0]["user"]


def test_generate_governance_opinion_handles_llm_failure():
    def failing_llm(**kwargs):
        raise RuntimeError("provider unavailable")

    opinion = generate_governance_opinion(_report(), llm_client=failing_llm)

    assert opinion["status"] == "unavailable"
    assert "provider unavailable" in opinion["error"]
