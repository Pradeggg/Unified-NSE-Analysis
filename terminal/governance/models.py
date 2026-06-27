from __future__ import annotations

import math
from dataclasses import dataclass, field, fields, is_dataclass
from datetime import date, datetime
from typing import Any, Literal


Confidence = Literal["Low", "Medium", "High"]
Rating = Literal["STRONG", "WATCH", "CONCERN", "HIGH_RISK", "INSUFFICIENT_EVIDENCE"]
SignalStatus = Literal["green", "amber", "red", "missing"]
Severity = Literal["info", "warn", "block"]


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return {item.name: _jsonable(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Non-finite float values are not JSON safe")
        return value
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    raise TypeError(f"Unsupported JSON value: {type(value).__name__}")


class JsonMixin:
    def to_dict(self) -> dict[str, Any]:
        return _jsonable(self)


@dataclass(frozen=True)
class GovernanceSource(JsonMixin):
    name: str
    status: str
    rows: int | None = None
    latest_date: date | None = None
    fallback: bool = False
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GovernanceMissingEvidence(JsonMixin):
    scope: str
    subject: str
    field: str
    severity: Severity = "warn"
    reason: str | None = None


@dataclass(frozen=True)
class ShareholdingSnapshot(JsonMixin):
    quarter: str
    quarter_end: date | None
    promoter_pct: float | None
    pledge_pct: float | None
    pledge_of_total_pct: float | None
    fii_pct: float | None
    dii_pct: float | None
    public_pct: float | None
    source: str


@dataclass(frozen=True)
class InsiderDisclosure(JsonMixin):
    trade_date: date | None
    symbol: str
    name: str
    category: str
    transaction_type: str
    shares: int
    value_cr: float
    source: str


@dataclass(frozen=True)
class DealEvent(JsonMixin):
    deal_date: date | None
    symbol: str
    entity: str
    side: str
    qty: int
    price: float | None
    value_cr: float
    deal_type: str
    source: str


@dataclass(frozen=True)
class GovernanceAnnouncement(JsonMixin):
    announcement_date: date | None
    symbol: str
    subject: str
    category: str
    severity: SignalStatus
    source: str
    url: str | None = None


@dataclass(frozen=True)
class AuditSignal(JsonMixin):
    auditor_name: str
    auditor_tier: str
    opinion_type: str
    emphasis_of_matter: bool
    key_audit_matters_count: int
    auditor_tenure_years: int
    related_party_txn_pct_revenue: float
    source: str


@dataclass(frozen=True)
class ComplaintSignal(JsonMixin):
    total_complaints_fy: int
    pending_complaints: int
    resolution_rate_pct: float
    source: str


@dataclass(frozen=True)
class CapitalAllocationSignal(JsonMixin):
    dividend_payout_consistency: str
    dividend_yield_5y_avg: float | None
    buyback_count_5y: int
    fcf_to_net_income_ratio_3y: float | None
    esop_dilution_pct_annual: float | None
    acquisitions_goodwill_impairment: bool
    source: str


@dataclass(frozen=True)
class GovernanceRawSources(JsonMixin):
    symbol: str
    shareholding_payloads: list[dict[str, Any]] = field(default_factory=list)
    insider_payloads: list[dict[str, Any]] = field(default_factory=list)
    deal_rows: list[dict[str, Any]] = field(default_factory=list)
    announcement_rows: list[dict[str, Any]] = field(default_factory=list)
    complaint_payloads: list[dict[str, Any]] = field(default_factory=list)
    screener_payload: dict[str, Any] | None = None
    annual_report_text: str | None = None
    source_trail: list[GovernanceSource] = field(default_factory=list)
    missing_evidence: list[GovernanceMissingEvidence] = field(default_factory=list)


@dataclass(frozen=True)
class GovernanceEvidence(JsonMixin):
    symbol: str
    as_of: date
    shareholding: list[ShareholdingSnapshot] = field(default_factory=list)
    insider_disclosures: list[InsiderDisclosure] = field(default_factory=list)
    deals: list[DealEvent] = field(default_factory=list)
    announcements: list[GovernanceAnnouncement] = field(default_factory=list)
    audit: AuditSignal | None = None
    complaints: ComplaintSignal | None = None
    capital_allocation: CapitalAllocationSignal | None = None
    source_trail: list[GovernanceSource] = field(default_factory=list)
    missing_evidence: list[GovernanceMissingEvidence] = field(default_factory=list)


@dataclass(frozen=True)
class ComponentScore(JsonMixin):
    name: str
    score: float
    max_score: float
    status: SignalStatus
    notes: list[str] = field(default_factory=list)
    source_names: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class GovernanceReport(JsonMixin):
    symbol: str
    as_of: date
    score: float
    rating: Rating
    confidence: Confidence
    component_scores: list[ComponentScore]
    flags: list[str]
    evidence: GovernanceEvidence
    source_trail: list[GovernanceSource]
    missing_evidence: list[GovernanceMissingEvidence]
    llm_status: str
    llm_opinion: dict[str, Any] | None = None
