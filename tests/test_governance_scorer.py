from datetime import date

from terminal.governance.models import (
    AuditSignal,
    CapitalAllocationSignal,
    ComplaintSignal,
    GovernanceAnnouncement,
    GovernanceEvidence,
    GovernanceMissingEvidence,
    InsiderDisclosure,
    ShareholdingSnapshot,
)
from terminal.governance.scorer import score_governance


def _snapshot(quarter, promoter, pledge):
    return ShareholdingSnapshot(
        quarter=quarter,
        quarter_end=date(2026, 6, 30),
        promoter_pct=promoter,
        pledge_pct=pledge,
        pledge_of_total_pct=pledge * promoter / 100,
        fii_pct=10,
        dii_pct=12,
        public_pct=26,
        source="NSE",
    )


def _clean_evidence():
    return GovernanceEvidence(
        symbol="CLEAN",
        as_of=date(2026, 6, 27),
        shareholding=[
            _snapshot("Jun 2026", 55.0, 0.0),
            _snapshot("Mar 2026", 55.1, 0.0),
            _snapshot("Dec 2025", 55.0, 0.0),
            _snapshot("Sep 2025", 54.9, 0.0),
        ],
        insider_disclosures=[
            InsiderDisclosure(date(2026, 5, 1), "CLEAN", "Promoter", "Promoter", "BUY", 10000, 1.2, "NSE_PIT")
        ],
        audit=AuditSignal("Deloitte Haskins & Sells LLP", "Big4", "Clean", False, 2, 5, 2.0, "annual_report"),
        complaints=ComplaintSignal(10, 0, 100.0, "NSE_COMPLAINTS"),
        capital_allocation=CapitalAllocationSignal("High", 1.2, 1, 0.9, 0.5, False, "screener"),
    )


def test_clean_complete_evidence_scores_strong():
    result = score_governance(_clean_evidence())

    assert result.score >= 80
    assert result.rating == "STRONG"
    assert result.confidence == "High"
    assert result.flags == []
    assert result.llm_status == "not_requested"
    assert [item.name for item in result.component_scores] == [
        "promoter_pledge",
        "insider_activity",
        "institutional_trend",
        "audit_quality",
        "announcements",
        "complaints",
        "capital_allocation",
    ]
    assert sum(item.max_score for item in result.component_scores) == 100
    assert all(0 <= item.score <= item.max_score for item in result.component_scores)


def test_high_pledge_creates_red_flag_and_concern_rating():
    evidence = _clean_evidence()
    evidence = GovernanceEvidence(
        symbol=evidence.symbol,
        as_of=evidence.as_of,
        shareholding=[_snapshot("Jun 2026", 52.0, 31.0), _snapshot("Mar 2026", 54.0, 20.0)],
        insider_disclosures=evidence.insider_disclosures,
        audit=evidence.audit,
        complaints=evidence.complaints,
        capital_allocation=evidence.capital_allocation,
    )

    result = score_governance(evidence)

    assert result.rating == "HIGH_RISK"
    assert any("Promoter pledge >25%" in flag for flag in result.flags)
    assert result.component_scores[0].status == "red"


def test_promoter_decline_over_four_quarters_is_amber():
    evidence = _clean_evidence()
    evidence = GovernanceEvidence(
        symbol=evidence.symbol,
        as_of=evidence.as_of,
        shareholding=[
            _snapshot("Jun 2026", 50.0, 0.0),
            _snapshot("Mar 2026", 51.0, 0.0),
            _snapshot("Dec 2025", 52.0, 0.0),
            _snapshot("Sep 2025", 53.0, 0.0),
        ],
        insider_disclosures=evidence.insider_disclosures,
        audit=evidence.audit,
        complaints=evidence.complaints,
        capital_allocation=evidence.capital_allocation,
    )

    result = score_governance(evidence)

    assert any("Promoter holding declined" in flag for flag in result.flags)
    assert result.component_scores[0].status == "amber"
    assert result.component_scores[0].score == 12.0


def test_recent_promoter_selling_is_detected_with_date_objects():
    evidence = _clean_evidence()
    evidence = GovernanceEvidence(
        symbol=evidence.symbol,
        as_of=evidence.as_of,
        shareholding=evidence.shareholding,
        insider_disclosures=[
            InsiderDisclosure(date(2026, 6, 1), "CLEAN", "Promoter", "Promoter", "SELL", 200000, 75.0, "NSE_PIT")
        ],
        audit=evidence.audit,
        complaints=evidence.complaints,
        capital_allocation=evidence.capital_allocation,
    )

    result = score_governance(evidence)

    assert any("insider/promoter selling" in flag.lower() for flag in result.flags)


def test_recent_kmp_selling_is_detected_as_insider_selling():
    evidence = _clean_evidence()
    evidence = GovernanceEvidence(
        symbol=evidence.symbol,
        as_of=evidence.as_of,
        shareholding=evidence.shareholding,
        insider_disclosures=[
            InsiderDisclosure(date(2026, 6, 1), "CLEAN", "CFO", "KMP", "SELL", 200000, 75.0, "NSE_PIT")
        ],
        audit=evidence.audit,
        complaints=evidence.complaints,
        capital_allocation=evidence.capital_allocation,
    )

    result = score_governance(evidence)

    assert result.rating == "HIGH_RISK"
    assert any("insider/promoter selling" in flag.lower() for flag in result.flags)


def test_stale_insider_selling_is_excluded_from_lookback():
    evidence = _clean_evidence()
    evidence = GovernanceEvidence(
        symbol=evidence.symbol,
        as_of=evidence.as_of,
        shareholding=evidence.shareholding,
        insider_disclosures=[
            InsiderDisclosure(date(2025, 1, 1), "CLEAN", "Promoter", "Promoter", "SELL", 200000, 75.0, "NSE_PIT")
        ],
        audit=evidence.audit,
        complaints=evidence.complaints,
        capital_allocation=evidence.capital_allocation,
    )

    result = score_governance(evidence)

    assert not any("insider/promoter selling" in flag.lower() for flag in result.flags)


def test_adverse_audit_overrides_insufficient_core_evidence():
    evidence = GovernanceEvidence(
        symbol="AUDIT",
        as_of=date(2026, 6, 27),
        audit=AuditSignal("Unknown", "Unknown", "Adverse", False, 0, 0, 0.0, "annual_report"),
    )

    result = score_governance(evidence)

    assert result.rating == "HIGH_RISK"
    assert any("Non-clean audit opinion" in flag for flag in result.flags)


def test_missing_corporate_events_does_not_score_announcements_green():
    evidence = _clean_evidence()
    evidence = GovernanceEvidence(
        symbol=evidence.symbol,
        as_of=evidence.as_of,
        shareholding=evidence.shareholding,
        insider_disclosures=evidence.insider_disclosures,
        audit=evidence.audit,
        announcements=[],
        complaints=evidence.complaints,
        capital_allocation=evidence.capital_allocation,
        missing_evidence=[
            GovernanceMissingEvidence("governance", evidence.symbol, "corporate_events", "warn", "missing")
        ],
    )

    result = score_governance(evidence)
    announcements = next(item for item in result.component_scores if item.name == "announcements")

    assert announcements.status == "missing"
    assert announcements.score == 0
    assert result.confidence == "Medium"
    assert result.rating == "WATCH"


def test_high_scoring_amber_watch_item_rates_watch_not_concern():
    evidence = _clean_evidence()
    evidence = GovernanceEvidence(
        symbol=evidence.symbol,
        as_of=evidence.as_of,
        shareholding=[_snapshot("Jun 2026", 55.0, 12.0), _snapshot("Mar 2026", 55.1, 0.0)],
        insider_disclosures=evidence.insider_disclosures,
        audit=evidence.audit,
        complaints=evidence.complaints,
        capital_allocation=evidence.capital_allocation,
    )

    result = score_governance(evidence)

    assert any("Promoter pledge >=10%" in flag for flag in result.flags)
    assert result.rating == "WATCH"


def test_required_risk_flags_for_audit_complaints_and_capital_allocation():
    evidence = _clean_evidence()
    evidence = GovernanceEvidence(
        symbol=evidence.symbol,
        as_of=evidence.as_of,
        shareholding=evidence.shareholding,
        insider_disclosures=evidence.insider_disclosures,
        announcements=[
            GovernanceAnnouncement(date(2026, 6, 1), evidence.symbol, "Auditor resignation", "governance_risk", "red", "NSE")
        ],
        audit=AuditSignal("Unknown", "Unknown", "Qualified", False, 0, 0, 25.0, "annual_report"),
        complaints=ComplaintSignal(100, 25, 75.0, "NSE_COMPLAINTS"),
        capital_allocation=CapitalAllocationSignal("Low", 0.0, 0, 0.4, 6.0, True, "screener"),
    )

    result = score_governance(evidence)

    assert result.rating == "HIGH_RISK"
    assert any("Non-clean audit opinion" in flag for flag in result.flags)
    assert any("related-party" in flag for flag in result.flags)
    assert any("Unresolved complaints" in flag for flag in result.flags)
    assert any("Weak FCF" in flag for flag in result.flags)
    assert any("High dilution" in flag for flag in result.flags)


def test_missing_core_evidence_lowers_confidence_and_rating():
    evidence = GovernanceEvidence(
        symbol="MISS",
        as_of=date(2026, 6, 27),
        missing_evidence=[
            GovernanceMissingEvidence("governance", "MISS", "shareholding", "warn", "missing"),
            GovernanceMissingEvidence("governance", "MISS", "insider_disclosures", "warn", "missing"),
        ],
    )

    result = score_governance(evidence)

    assert result.rating == "INSUFFICIENT_EVIDENCE"
    assert result.confidence == "Low"
    assert len(result.missing_evidence) >= 2
