from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from terminal.governance.models import (
    AuditSignal,
    CapitalAllocationSignal,
    ComponentScore,
    ComplaintSignal,
    GovernanceAnnouncement,
    GovernanceEvidence,
    GovernanceReport,
    InsiderDisclosure,
    ShareholdingSnapshot,
    SignalStatus,
)


@dataclass
class _ScoredComponent:
    component: ComponentScore
    flags: list[str] = field(default_factory=list)
    severe: bool = False


def score_governance(evidence: GovernanceEvidence) -> GovernanceReport:
    components = [
        _score_promoter_pledge(evidence.shareholding),
        _score_insider_activity(evidence),
        _score_institutional_trend(evidence.shareholding),
        _score_audit(evidence.audit),
        _score_announcements(evidence),
        _score_complaints(evidence.complaints),
        _score_capital_allocation(evidence.capital_allocation),
    ]
    component_scores = [item.component for item in components]
    flags = [flag for item in components for flag in item.flags]
    severe_red = any(item.severe for item in components)
    score = round(sum(component.score for component in component_scores), 2)
    confidence = _confidence(evidence)
    rating = _rating(score, confidence, component_scores, flags, severe_red, evidence)

    return GovernanceReport(
        symbol=evidence.symbol,
        as_of=evidence.as_of,
        score=score,
        rating=rating,
        confidence=confidence,
        component_scores=component_scores,
        flags=flags,
        evidence=evidence,
        source_trail=list(evidence.source_trail),
        missing_evidence=list(evidence.missing_evidence),
        llm_status="not_requested",
    )


def _score_promoter_pledge(shareholding: list[ShareholdingSnapshot]) -> _ScoredComponent:
    if not shareholding:
        return _component("promoter_pledge", 0, 20, "missing", ["Shareholding evidence missing"])

    latest = shareholding[0]
    pledge = latest.pledge_pct
    flags: list[str] = []
    severe = False

    if pledge is None:
        score = 0
        status: SignalStatus = "missing"
        notes = ["Latest promoter pledge unavailable"]
    elif pledge > 25:
        score = 0
        status = "red"
        notes = [f"Latest promoter pledge is {pledge:.1f}%"]
        flags.append("Promoter pledge >25%")
        severe = True
    elif pledge >= 10:
        score = 8
        status = "amber"
        notes = [f"Latest promoter pledge is {pledge:.1f}%"]
        flags.append("Promoter pledge >=10%")
    elif pledge > 0:
        score = 15
        status = "amber"
        notes = [f"Latest promoter pledge is {pledge:.1f}%"]
    else:
        score = 20
        status = "green"
        notes = ["No promoter pledge in latest quarter"]

    if len(shareholding) >= 4:
        latest_promoter = latest.promoter_pct
        oldest_promoter = shareholding[3].promoter_pct
        if latest_promoter is not None and oldest_promoter is not None:
            decline = oldest_promoter - latest_promoter
            if decline > 2:
                score = min(score, 12)
                if status == "green":
                    status = "amber"
                notes.append(f"Promoter holding declined {decline:.1f}pp over four quarters")
                flags.append("Promoter holding declined more than 2pp over four quarters")

    return _component("promoter_pledge", score, 20, status, notes, _shareholding_sources(shareholding), flags, severe)


def _score_insider_activity(evidence: GovernanceEvidence) -> _ScoredComponent:
    disclosures = evidence.insider_disclosures
    if not disclosures:
        return _component("insider_activity", 0, 15, "missing", ["Insider disclosure evidence missing"])

    lookback_start = evidence.as_of - timedelta(days=365)
    recent = [
        item
        for item in disclosures
        if item.trade_date is not None
        and lookback_start <= item.trade_date <= evidence.as_of
        and _is_governance_insider(item)
    ]
    buy_value = sum(item.value_cr for item in recent if _transaction_side(item) == "BUY")
    sell_value = sum(item.value_cr for item in recent if _transaction_side(item) == "SELL")
    net_value = buy_value - sell_value

    if sell_value > 50:
        return _component(
            "insider_activity",
            0,
            15,
            "red",
            [f"Recent insider/promoter selling value is {sell_value:.1f} crore"],
            _insider_sources(disclosures),
            ["Heavy insider/promoter selling >50 crore"],
            True,
        )
    if net_value < 0:
        return _component(
            "insider_activity",
            5,
            15,
            "amber",
            [f"Net recent insider/promoter selling is {abs(net_value):.1f} crore"],
            _insider_sources(disclosures),
            ["Net recent insider/promoter selling detected"],
        )
    if not recent:
        return _component("insider_activity", 10, 15, "green", ["No recent insider/promoter activity"], _insider_sources(disclosures))
    return _component("insider_activity", 15, 15, "green", [f"Net recent insider buying is {net_value:.1f} crore"], _insider_sources(disclosures))


def _score_institutional_trend(shareholding: list[ShareholdingSnapshot]) -> _ScoredComponent:
    if len(shareholding) < 2:
        return _component("institutional_trend", 0, 10, "missing", ["Insufficient shareholding trend evidence"])

    latest = _institutional_holding(shareholding[0])
    previous = _institutional_holding(shareholding[1])
    if latest is None or previous is None:
        return _component("institutional_trend", 0, 10, "missing", ["Institutional holding unavailable"])

    change = latest - previous
    if change > 0.5:
        return _component("institutional_trend", 10, 10, "green", [f"Institutional holding rose {change:.1f}pp"], _shareholding_sources(shareholding))
    if change >= -0.5:
        return _component("institutional_trend", 7, 10, "green", [f"Institutional holding stable at {latest:.1f}%"], _shareholding_sources(shareholding))
    return _component("institutional_trend", 4, 10, "amber", [f"Institutional holding fell {abs(change):.1f}pp"], _shareholding_sources(shareholding))


def _score_audit(audit: AuditSignal | None) -> _ScoredComponent:
    if audit is None:
        return _component("audit_quality", 0, 20, "missing", ["Audit evidence missing"])

    opinion = audit.opinion_type.strip().lower()
    tier = audit.auditor_tier.strip().lower()
    rpt = audit.related_party_txn_pct_revenue
    flags: list[str] = []
    severe = False

    if any(term in opinion for term in ("adverse", "disclaimer")):
        score = 0
        status: SignalStatus = "red"
        notes = [f"Audit opinion is {audit.opinion_type}"]
        flags.append(f"Non-clean audit opinion: {audit.opinion_type}")
        severe = True
    elif "qualified" in opinion:
        score = 5
        status = "red"
        notes = [f"Audit opinion is {audit.opinion_type}"]
        flags.append(f"Non-clean audit opinion: {audit.opinion_type}")
        severe = True
    elif "clean" in opinion:
        if tier == "big4" and not audit.emphasis_of_matter and rpt <= 10:
            score = 20
            status = "green"
            notes = ["Clean Big4 audit with limited related-party transactions"]
        else:
            score = 14
            status = "amber"
            notes = ["Clean audit with watch items"]
            if tier != "big4":
                notes.append("Auditor is not Big4")
            if audit.emphasis_of_matter:
                notes.append("Emphasis of matter present")
    else:
        score = 10
        status = "amber"
        notes = [f"Audit opinion is {audit.opinion_type}"]

    if rpt > 20:
        score = min(score, 5)
        status = "red"
        notes.append(f"Related-party transactions are {rpt:.1f}% of revenue")
        flags.append("High related-party transaction percentage >20%")
        severe = True
    elif rpt > 10:
        score = min(score, 14)
        if status == "green":
            status = "amber"
        notes.append(f"Related-party transactions are {rpt:.1f}% of revenue")
        flags.append("High related-party transaction percentage >10%")

    return _component("audit_quality", score, 20, status, notes, [audit.source], flags, severe)


def _score_announcements(evidence: GovernanceEvidence) -> _ScoredComponent:
    announcements = evidence.announcements
    if not announcements and _missing_field(evidence, "corporate_events"):
        return _component(
            "announcements",
            0,
            10,
            "missing",
            ["Corporate event evidence missing"],
        )
    if any(item.severity == "red" for item in announcements):
        return _component("announcements", 0, 10, "red", ["Red governance announcement present"], _announcement_sources(announcements), ["Red governance announcement detected"], True)
    if any(item.severity == "amber" for item in announcements):
        return _component("announcements", 6, 10, "amber", ["Amber governance announcement present"], _announcement_sources(announcements), ["Amber governance announcement detected"])
    return _component("announcements", 10, 10, "green", ["No adverse governance announcements"], _announcement_sources(announcements))


def _score_complaints(complaints: ComplaintSignal | None) -> _ScoredComponent:
    if complaints is None:
        return _component("complaints", 0, 10, "missing", ["Complaint evidence missing"])

    pending = complaints.pending_complaints
    resolution = complaints.resolution_rate_pct
    if pending == 0 and resolution >= 95:
        return _component("complaints", 10, 10, "green", ["No pending complaints and high resolution rate"], [complaints.source])
    if pending > 20 or resolution < 80:
        return _component(
            "complaints",
            0,
            10,
            "red",
            [f"{pending} pending complaints with {resolution:.1f}% resolution"],
            [complaints.source],
            ["Unresolved complaints are elevated"],
            True,
        )
    return _component(
        "complaints",
        6,
        10,
        "amber",
        [f"{pending} pending complaints with {resolution:.1f}% resolution"],
        [complaints.source],
        ["Unresolved complaints require monitoring"] if pending > 0 else [],
    )


def _score_capital_allocation(signal: CapitalAllocationSignal | None) -> _ScoredComponent:
    if signal is None:
        return _component("capital_allocation", 0, 15, "missing", ["Capital allocation evidence missing"])

    score = 15
    status: SignalStatus = "green"
    notes: list[str] = ["Capital allocation evidence available"]
    flags: list[str] = []
    severe = False

    fcf_ratio = signal.fcf_to_net_income_ratio_3y
    if fcf_ratio is not None:
        if fcf_ratio < 0.5:
            score -= 7
            status = "red"
            notes.append(f"FCF to net income ratio is {fcf_ratio:.2f}")
            flags.append("Weak FCF conversion below 0.5x net income")
            severe = True
        elif fcf_ratio < 0.8:
            score -= 3
            status = "amber"
            notes.append(f"FCF to net income ratio is {fcf_ratio:.2f}")
            flags.append("Weak FCF conversion below 0.8x net income")

    dilution = signal.esop_dilution_pct_annual
    if dilution is not None:
        if dilution > 5:
            score -= 6
            status = "red"
            notes.append(f"ESOP dilution is {dilution:.1f}% annually")
            flags.append("High dilution from ESOPs >5%")
            severe = True
        elif dilution > 2:
            score -= 3
            if status == "green":
                status = "amber"
            notes.append(f"ESOP dilution is {dilution:.1f}% annually")
            flags.append("High dilution from ESOPs >2%")

    if signal.acquisitions_goodwill_impairment:
        score -= 3
        if status == "green":
            status = "amber"
        notes.append("Goodwill impairment from acquisitions present")

    if signal.dividend_payout_consistency.strip().lower() in {"low", "none"}:
        score -= 1
        if status == "green":
            status = "amber"
        notes.append("Dividend payout consistency is low")

    score = max(score, 0)
    if score == 0:
        status = "red"
    elif status == "red" and score > 8:
        score = 8

    return _component("capital_allocation", score, 15, status, notes, [signal.source], flags, severe)


def _confidence(evidence: GovernanceEvidence) -> str:
    has_shareholding = bool(evidence.shareholding)
    has_insider = bool(evidence.insider_disclosures)
    has_audit = evidence.audit is not None
    has_announcements = bool(evidence.announcements) or not _missing_field(evidence, "corporate_events")
    has_complaints = evidence.complaints is not None
    has_capital_allocation = evidence.capital_allocation is not None

    if has_shareholding and has_insider and has_audit and has_announcements and (has_complaints or has_capital_allocation):
        return "High"

    core_areas = sum([has_shareholding, has_insider, has_audit, has_announcements, has_complaints or has_capital_allocation])
    if core_areas >= 2:
        return "Medium"
    return "Low"


def _rating(
    score: float,
    confidence: str,
    component_scores: list[ComponentScore],
    flags: list[str],
    severe_red: bool,
    evidence: GovernanceEvidence,
) -> str:
    if severe_red:
        return "HIGH_RISK"
    if not evidence.shareholding and not evidence.insider_disclosures:
        return "INSUFFICIENT_EVIDENCE"
    if score < 45:
        return "HIGH_RISK"
    if any(item.status == "red" for item in component_scores):
        return "CONCERN"
    if score >= 80 and confidence == "High" and all(item.status == "green" for item in component_scores):
        return "STRONG"
    if score >= 65:
        return "WATCH"
    return "CONCERN"


def _component(
    name: str,
    score: float,
    max_score: float,
    status: SignalStatus,
    notes: list[str],
    source_names: list[str] | None = None,
    flags: list[str] | None = None,
    severe: bool = False,
) -> _ScoredComponent:
    return _ScoredComponent(
        component=ComponentScore(
            name=name,
            score=float(score),
            max_score=float(max_score),
            status=status,
            notes=notes,
            source_names=source_names or [],
        ),
        flags=flags or [],
        severe=severe,
    )


def _shareholding_sources(shareholding: list[ShareholdingSnapshot]) -> list[str]:
    return _unique(item.source for item in shareholding)


def _insider_sources(disclosures: list[InsiderDisclosure]) -> list[str]:
    return _unique(item.source for item in disclosures)


def _announcement_sources(announcements: list[GovernanceAnnouncement]) -> list[str]:
    return _unique(item.source for item in announcements)


def _unique(values) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _transaction_side(disclosure: InsiderDisclosure) -> str:
    transaction = disclosure.transaction_type.strip().upper()
    if "SELL" in transaction or "DISPOS" in transaction:
        return "SELL"
    if "BUY" in transaction or "ACQUI" in transaction or "PURCHASE" in transaction:
        return "BUY"
    return transaction


def _is_governance_insider(disclosure: InsiderDisclosure) -> bool:
    category = disclosure.category.lower()
    name = disclosure.name.lower()
    return any(
        term in category or term in name
        for term in (
            "promoter",
            "director",
            "kmp",
            "key managerial",
            "officer",
            "designated",
            "insider",
            "management",
        )
    )


def _missing_field(evidence: GovernanceEvidence, field: str) -> bool:
    return any(item.field == field for item in evidence.missing_evidence)


def _institutional_holding(snapshot: ShareholdingSnapshot) -> float | None:
    if snapshot.fii_pct is None or snapshot.dii_pct is None:
        return None
    return snapshot.fii_pct + snapshot.dii_pct
