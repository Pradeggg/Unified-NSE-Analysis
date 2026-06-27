# Governance Evaluation Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic, single-stock NSE governance evaluation engine with source-trailed evidence, scoring, Markdown output, and optional LLM opinion generation.

**Architecture:** Add a new `terminal/governance/` package with strict boundaries: models, parsers, audit parsing, source readers, scoring, opinion generation, orchestration, and Markdown rendering. The engine scores facts deterministically first; an LLM may only summarize the structured report into a bounded governance opinion.

**Tech Stack:** Python 3.10+ dataclasses, stdlib JSON/CSV/pathlib/datetime/argparse, existing `requests` dependency for NSE client, existing `terminal.research_council.llm_client.call_llm_json`, pytest fixture tests with no live network or live LLM calls.

---

## Scope Check

This plan implements V1 from `docs/superpowers/specs/2026-06-27-governance-evaluation-engine-design.md`: single-symbol governance evaluation. It deliberately excludes batch universe scanning, persistence migrations, and full Research Council specialist integration.

## File Structure

- Create `terminal/governance/__init__.py`
  - Public package exports for `evaluate_governance`, `GovernanceReport`, and `render_markdown`.

- Create `terminal/governance/models.py`
  - JSON-safe dataclasses: `GovernanceSource`, `GovernanceMissingEvidence`, `ShareholdingSnapshot`, `InsiderDisclosure`, `DealEvent`, `GovernanceAnnouncement`, `AuditSignal`, `ComplaintSignal`, `CapitalAllocationSignal`, `GovernanceRawSources`, `GovernanceEvidence`, `ComponentScore`, `GovernanceReport`.

- Create `terminal/governance/parsers.py`
  - Pure normalization helpers for dates, percentages, NSE shareholding, PIT/SAST insider disclosures, bulk/block deals, announcements, complaints, and Screener-like capital-allocation payloads.

- Create `terminal/governance/audit_parser.py`
  - Text-first annual-report audit parser. PDF text extraction remains optional; core tests target text parsing and section slicing.

- Create `terminal/governance/cache_sources.py`
  - Reads local data files and filing manifests. No live network calls. Returns `GovernanceRawSources` and source trail entries.

- Create `terminal/governance/nse_client.py`
  - Small NSE JSON client with session warm-up, retries, timeout, and error results.

- Create `terminal/governance/scorer.py`
  - Deterministic 0-100 governance scorer and confidence/rating logic.

- Create `terminal/governance/opinion.py`
  - LLM opinion generator with schema validation and graceful failure.

- Create `terminal/governance/markdown.py`
  - Markdown report renderer.

- Create `terminal/governance/engine.py`
  - `evaluate_governance()` orchestration and `python -m terminal.governance.engine` CLI.

- Create tests:
  - `tests/test_governance_models.py`
  - `tests/test_governance_parsers.py`
  - `tests/test_governance_audit_parser.py`
  - `tests/test_governance_sources.py`
  - `tests/test_governance_scorer.py`
  - `tests/test_governance_opinion.py`
  - `tests/test_governance_engine.py`

## Task 1: Core Models

**Files:**
- Create: `terminal/governance/__init__.py`
- Create: `terminal/governance/models.py`
- Test: `tests/test_governance_models.py`

- [ ] **Step 1: Write the failing model tests**

Create `tests/test_governance_models.py`:

```python
from datetime import date

from terminal.governance.models import (
    AuditSignal,
    ComponentScore,
    GovernanceEvidence,
    GovernanceMissingEvidence,
    GovernanceRawSources,
    GovernanceReport,
    GovernanceSource,
    ShareholdingSnapshot,
)


def test_governance_report_to_dict_is_json_safe():
    source = GovernanceSource(
        name="nse.corporates-shp",
        status="ok",
        rows=2,
        latest_date=date(2026, 6, 30),
        fallback=False,
    )
    evidence = GovernanceEvidence(
        symbol="INFY",
        as_of=date(2026, 6, 27),
        shareholding=[
            ShareholdingSnapshot(
                quarter="Jun 2026",
                quarter_end=date(2026, 6, 30),
                promoter_pct=14.7,
                pledge_pct=0.0,
                pledge_of_total_pct=0.0,
                fii_pct=32.0,
                dii_pct=36.0,
                public_pct=17.3,
                source="NSE",
            )
        ],
        audit=AuditSignal(
            auditor_name="Deloitte Haskins & Sells LLP",
            auditor_tier="Big4",
            opinion_type="Clean",
            emphasis_of_matter=False,
            key_audit_matters_count=3,
            auditor_tenure_years=5,
            related_party_txn_pct_revenue=2.5,
            source="annual_report",
        ),
        source_trail=[source],
    )
    report = GovernanceReport(
        symbol="INFY",
        as_of=date(2026, 6, 27),
        score=91.5,
        rating="STRONG",
        confidence="High",
        component_scores=[
            ComponentScore(
                name="promoter_pledge",
                score=20.0,
                max_score=20.0,
                status="green",
                notes=["No pledge"],
                source_names=["nse.corporates-shp"],
            )
        ],
        flags=[],
        evidence=evidence,
        source_trail=[source],
        missing_evidence=[],
        llm_status="not_requested",
    )

    data = report.to_dict()

    assert data["as_of"] == "2026-06-27"
    assert data["evidence"]["shareholding"][0]["quarter_end"] == "2026-06-30"
    assert data["source_trail"][0]["latest_date"] == "2026-06-30"
    assert data["component_scores"][0]["name"] == "promoter_pledge"


def test_raw_sources_can_capture_source_errors_and_missing_evidence():
    raw = GovernanceRawSources(
        symbol="AAA",
        source_trail=[
            GovernanceSource(
                name="nse.corporates-cgr",
                status="error",
                error="HTTP 404",
            )
        ],
        missing_evidence=[
            GovernanceMissingEvidence(
                scope="governance",
                subject="AAA",
                field="corporate_governance_report",
                severity="warn",
                reason="NSE endpoint unavailable",
            )
        ],
    )

    data = raw.to_dict()

    assert data["symbol"] == "AAA"
    assert data["source_trail"][0]["status"] == "error"
    assert data["missing_evidence"][0]["field"] == "corporate_governance_report"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
./.venv/bin/python -m pytest -q tests/test_governance_models.py
```

Expected:

```text
ModuleNotFoundError: No module named 'terminal.governance'
```

- [ ] **Step 3: Add the model implementation**

Create `terminal/governance/models.py` with these public dataclasses and JSON helpers:

```python
from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import date, datetime
from typing import Any, Literal


Confidence = Literal["Low", "Medium", "High"]
Rating = Literal["STRONG", "WATCH", "CONCERN", "HIGH_RISK", "INSUFFICIENT_EVIDENCE"]
SignalStatus = Literal["green", "amber", "red", "missing"]
Severity = Literal["info", "warn", "block"]


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return {key: _jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return value


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
```

Create `terminal/governance/__init__.py`:

```python
"""Governance evaluation engine for NSE-listed companies."""

from terminal.governance.models import GovernanceReport

__all__ = ["GovernanceReport"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
./.venv/bin/python -m pytest -q tests/test_governance_models.py
```

Expected:

```text
2 passed
```

- [ ] **Step 5: Commit**

```bash
git add terminal/governance/__init__.py terminal/governance/models.py tests/test_governance_models.py
git commit -m "feat: add governance report models"
```

## Task 2: Parsers

**Files:**
- Create: `terminal/governance/parsers.py`
- Test: `tests/test_governance_parsers.py`

- [ ] **Step 1: Write failing parser tests**

Create `tests/test_governance_parsers.py`:

```python
from datetime import date

from terminal.governance.parsers import (
    normalize_transaction_type,
    parse_complaint_signal,
    parse_deal_rows,
    parse_nse_insider_disclosures,
    parse_nse_shareholding,
    parse_screener_capital_allocation,
)


def test_parse_nse_shareholding_orders_latest_quarter_first():
    raw = {
        "data": [
            {
                "quarter": "Mar 2026",
                "promoterAndPromoterGroupShareHolding": "52.0",
                "pledgedSharesPercent": "3.0",
                "pledgedSharesPercentOfTotalShareCapital": "1.56",
                "fii": "11.0",
                "dii": "12.0",
                "public": "25.0",
            },
            {
                "quarter": "Jun 2026",
                "promoterAndPromoterGroupShareHolding": "51.0",
                "pledgedSharesPercent": "12.5",
                "pledgedSharesPercentOfTotalShareCapital": "6.38",
                "fii": "10.5",
                "dii": "12.5",
                "public": "26.0",
            },
        ]
    }

    snapshots = parse_nse_shareholding(raw)

    assert [s.quarter for s in snapshots] == ["Jun 2026", "Mar 2026"]
    assert snapshots[0].quarter_end == date(2026, 6, 30)
    assert snapshots[0].pledge_pct == 12.5


def test_parse_nse_insider_disclosures_uses_real_dates_and_values():
    raw = {
        "data": [
            {
                "symbol": "AAA",
                "acqName": "Promoter One",
                "personCategory": "Promoter",
                "tdpTransactionType": "Disposal",
                "secAcq": "100000",
                "sellValue": "45000000",
                "date": "15-Feb-2026",
            },
            {
                "symbol": "AAA",
                "acqName": "Director Two",
                "personCategory": "Director",
                "tdpTransactionType": "Acquisition",
                "noSecAcq": "20000",
                "tdpVal": "12000000",
                "tdpAcqDisposalDate": "20-03-2026",
            },
        ]
    }

    disclosures = parse_nse_insider_disclosures(raw, symbol="AAA")

    assert disclosures[0].trade_date == date(2026, 2, 15)
    assert disclosures[0].transaction_type == "SELL"
    assert disclosures[0].value_cr == 4.5
    assert disclosures[1].trade_date == date(2026, 3, 20)
    assert disclosures[1].transaction_type == "BUY"
    assert disclosures[1].shares == 20000


def test_normalize_transaction_type_classifies_pledge_and_revoke():
    assert normalize_transaction_type("Acquisition") == "BUY"
    assert normalize_transaction_type("Disposal") == "SELL"
    assert normalize_transaction_type("Pledge Creation") == "PLEDGE"
    assert normalize_transaction_type("Revocation of Pledge") == "REVOKE_PLEDGE"
    assert normalize_transaction_type("ESOP Exercise") == "OTHER"


def test_parse_deal_rows_normalizes_bulk_and_block_values():
    rows = [
        {
            "DATE": "25-Jun-2026",
            "SYMBOL": "AAA",
            "ENTITY": "Fund A",
            "SIDE": "BUY",
            "QTY": "500000",
            "PRICE": "120.50",
            "SOURCE": "BULK_DEAL",
        }
    ]

    deals = parse_deal_rows(rows, symbol="AAA")

    assert deals[0].deal_date == date(2026, 6, 25)
    assert deals[0].value_cr == 6.03
    assert deals[0].deal_type == "BULK_DEAL"


def test_parse_complaint_signal_sums_rows():
    signal = parse_complaint_signal(
        {"data": [{"totalComplaints": "10", "pendingComplaints": "1"}, {"totalComplaints": "5", "pendingComplaints": "0"}]}
    )

    assert signal.total_complaints_fy == 15
    assert signal.pending_complaints == 1
    assert signal.resolution_rate_pct == 93.3


def test_parse_screener_capital_allocation_is_conservative_on_missing_values():
    payload = {
        "annual_pl": {
            "_headers": ["Mar 2024", "Mar 2025", "Mar 2026"],
            "Net Profit": ["100", "120", "150"],
            "Dividend Payout %": ["20", "25", "30"],
        },
        "cash_flow": {
            "_headers": ["Mar 2024", "Mar 2025", "Mar 2026"],
            "Cash from Operating Activity": ["90", "130", "170"],
        },
        "ratios": {"Dividend Yield": "1.2"},
    }

    signal = parse_screener_capital_allocation(payload)

    assert signal.dividend_payout_consistency == "High"
    assert signal.fcf_to_net_income_ratio_3y == 1.1
    assert signal.source == "screener"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
./.venv/bin/python -m pytest -q tests/test_governance_parsers.py
```

Expected:

```text
ModuleNotFoundError: No module named 'terminal.governance.parsers'
```

- [ ] **Step 3: Add parser implementation**

Create `terminal/governance/parsers.py` with:

```python
from __future__ import annotations

import calendar
import re
from datetime import date, datetime
from typing import Any

from terminal.governance.models import (
    CapitalAllocationSignal,
    ComplaintSignal,
    DealEvent,
    GovernanceAnnouncement,
    InsiderDisclosure,
    ShareholdingSnapshot,
)


MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_abbr) if m}


def to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace(",", "").replace("%", "").replace("₹", "").strip()
    if not text or text in {"-", "NA", "None", "nan"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def to_int(value: Any) -> int:
    parsed = to_float(value)
    return int(parsed) if parsed is not None else 0


def parse_date(value: Any) -> date | None:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%d-%b-%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y", "%d %b %Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text[:10]).date()
    except ValueError:
        return None


def parse_quarter_end(label: str) -> date | None:
    match = re.search(r"\b([A-Za-z]{3})\s+(\d{4})\b", label or "")
    if not match:
        return None
    month = MONTHS.get(match.group(1).lower())
    if not month:
        return None
    year = int(match.group(2))
    return date(year, month, calendar.monthrange(year, month)[1])


def normalize_transaction_type(value: Any) -> str:
    text = str(value or "").lower()
    if "revoke" in text or "revocation" in text:
        return "REVOKE_PLEDGE"
    if "pledge" in text:
        return "PLEDGE"
    if "buy" in text or "acquisition" in text:
        return "BUY"
    if "sell" in text or "disposal" in text:
        return "SELL"
    return "OTHER"


def parse_nse_shareholding(raw: dict[str, Any]) -> list[ShareholdingSnapshot]:
    rows = raw.get("data") if isinstance(raw, dict) else []
    snapshots: list[ShareholdingSnapshot] = []
    for row in rows or []:
        quarter = str(row.get("quarter") or row.get("Quarter") or "").strip()
        snapshots.append(
            ShareholdingSnapshot(
                quarter=quarter,
                quarter_end=parse_quarter_end(quarter),
                promoter_pct=to_float(row.get("promoterAndPromoterGroupShareHolding")),
                pledge_pct=to_float(row.get("pledgedSharesPercent")),
                pledge_of_total_pct=to_float(row.get("pledgedSharesPercentOfTotalShareCapital")),
                fii_pct=to_float(row.get("fii")),
                dii_pct=to_float(row.get("dii")),
                public_pct=to_float(row.get("public")),
                source="NSE",
            )
        )
    return sorted(snapshots, key=lambda item: item.quarter_end or date.min, reverse=True)


def _value_cr(row: dict[str, Any]) -> float:
    for key in ("sellValue", "buyValue", "secVal", "tdpVal"):
        value = to_float(row.get(key))
        if value is not None:
            return round(value / 1e7, 2)
    return 0.0


def parse_nse_insider_disclosures(raw: dict[str, Any], *, symbol: str) -> list[InsiderDisclosure]:
    rows = raw.get("data") if isinstance(raw, dict) else []
    output: list[InsiderDisclosure] = []
    wanted = symbol.upper()
    for row in rows or []:
        row_symbol = str(row.get("symbol") or wanted).upper()
        if row_symbol != wanted:
            continue
        output.append(
            InsiderDisclosure(
                trade_date=parse_date(row.get("date") or row.get("tdpAcqDisposalDate") or row.get("acqfromDt")),
                symbol=row_symbol,
                name=str(row.get("acqName") or "").strip(),
                category=str(row.get("personCategory") or "").strip(),
                transaction_type=normalize_transaction_type(row.get("tdpTransactionType")),
                shares=to_int(row.get("secAcq") or row.get("noSecAcq")),
                value_cr=_value_cr(row),
                source="NSE_PIT",
            )
        )
    return sorted(output, key=lambda item: item.trade_date or date.min, reverse=True)


def parse_deal_rows(rows: list[dict[str, Any]], *, symbol: str) -> list[DealEvent]:
    wanted = symbol.upper()
    deals: list[DealEvent] = []
    for row in rows:
        row_symbol = str(row.get("SYMBOL") or row.get("symbol") or "").upper()
        if row_symbol != wanted:
            continue
        qty = to_int(row.get("QTY") or row.get("qty"))
        price = to_float(row.get("PRICE") or row.get("price"))
        value_cr = round((qty * (price or 0.0)) / 1e7, 2)
        deals.append(
            DealEvent(
                deal_date=parse_date(row.get("DATE") or row.get("deal_date")),
                symbol=row_symbol,
                entity=str(row.get("ENTITY") or row.get("entity") or "").strip(),
                side=str(row.get("SIDE") or row.get("side") or "").upper(),
                qty=qty,
                price=price,
                value_cr=value_cr,
                deal_type=str(row.get("SOURCE") or row.get("deal_type") or "DEAL").upper(),
                source=str(row.get("SOURCE") or row.get("source") or "cache"),
            )
        )
    return sorted(deals, key=lambda item: item.deal_date or date.min, reverse=True)


def parse_governance_announcements(rows: list[dict[str, Any]], *, symbol: str) -> list[GovernanceAnnouncement]:
    wanted = symbol.upper()
    output: list[GovernanceAnnouncement] = []
    for row in rows:
        row_symbol = str(row.get("symbol") or row.get("SYMBOL") or wanted).upper()
        if row_symbol != wanted:
            continue
        subject = str(row.get("subject") or row.get("PURPOSE_RAW") or row.get("detail") or "").strip()
        lower = subject.lower()
        if "resignation" in lower or "auditor" in lower or "fine" in lower or "penalty" in lower:
            severity = "red"
            category = "governance_risk"
        elif "board" in lower or "agm" in lower or "analyst" in lower:
            severity = "amber"
            category = "governance_event"
        else:
            severity = "green"
            category = "general"
        output.append(
            GovernanceAnnouncement(
                announcement_date=parse_date(row.get("date") or row.get("EVENT_DATE") or row.get("announcement_date")),
                symbol=row_symbol,
                subject=subject,
                category=category,
                severity=severity,
                source=str(row.get("source") or row.get("SOURCE") or "announcement"),
                url=row.get("url"),
            )
        )
    return output


def parse_complaint_signal(raw: dict[str, Any]) -> ComplaintSignal:
    rows = raw.get("data") if isinstance(raw, dict) else []
    total = sum(to_int(row.get("totalComplaints")) for row in rows or [])
    pending = sum(to_int(row.get("pendingComplaints")) for row in rows or [])
    resolved = max(0, total - pending)
    rate = round((resolved / total) * 100, 1) if total else 100.0
    return ComplaintSignal(total, pending, rate, "NSE_COMPLAINTS")


def parse_screener_capital_allocation(payload: dict[str, Any] | None) -> CapitalAllocationSignal | None:
    if not payload:
        return None
    annual = payload.get("annual_pl") or payload.get("annual") or {}
    cash_flow = payload.get("cash_flow") or {}
    dividends = [to_float(v) or 0.0 for v in annual.get("Dividend Payout %", [])]
    positive_divs = sum(1 for value in dividends if value > 0)
    consistency = "Unknown"
    if dividends:
        ratio = positive_divs / len(dividends)
        consistency = "High" if ratio >= 0.8 else "Medium" if ratio >= 0.5 else "Low" if ratio > 0 else "None"
    profits = [to_float(v) for v in annual.get("Net Profit", [])][-3:]
    cfo = [to_float(v) for v in cash_flow.get("Cash from Operating Activity", [])][-3:]
    pairs = [(a, b) for a, b in zip(cfo, profits) if a is not None and b not in (None, 0)]
    fcf_ratio = round(sum(a / b for a, b in pairs) / len(pairs), 2) if pairs else None
    ratios = payload.get("ratios") if isinstance(payload.get("ratios"), dict) else {}
    return CapitalAllocationSignal(
        dividend_payout_consistency=consistency,
        dividend_yield_5y_avg=to_float(ratios.get("Dividend Yield")),
        buyback_count_5y=0,
        fcf_to_net_income_ratio_3y=fcf_ratio,
        esop_dilution_pct_annual=None,
        acquisitions_goodwill_impairment=False,
        source="screener",
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
./.venv/bin/python -m pytest -q tests/test_governance_parsers.py
```

Expected:

```text
6 passed
```

- [ ] **Step 5: Commit**

```bash
git add terminal/governance/parsers.py tests/test_governance_parsers.py
git commit -m "feat: add governance source parsers"
```

## Task 3: Annual Report Audit Parser

**Files:**
- Create: `terminal/governance/audit_parser.py`
- Test: `tests/test_governance_audit_parser.py`

- [ ] **Step 1: Write failing audit parser tests**

Create `tests/test_governance_audit_parser.py`:

```python
from terminal.governance.audit_parser import (
    classify_auditor,
    extract_auditor_section,
    parse_audit_text,
)


def test_extract_auditor_section_accepts_marker_at_character_zero():
    text = (
        "Independent Auditor's Report\n"
        "To the Members of Example Limited\n"
        "In our opinion, the financial statements give a true and fair view.\n"
        "Balance Sheet\n"
        "Assets and liabilities"
    )

    section = extract_auditor_section(text)

    assert section is not None
    assert section.startswith("Independent Auditor's Report")
    assert "Balance Sheet" not in section


def test_parse_audit_text_detects_big4_clean_opinion_and_eom_absence():
    text = (
        "Independent Auditor's Report\n"
        "For Deloitte Haskins & Sells LLP\n"
        "Chartered Accountants\n"
        "In our opinion the financial statements give a true and fair view.\n"
        "Key Audit Matter 1 Revenue recognition\n"
        "Key Audit Matter 2 Tax matters\n"
        "Balance Sheet\n"
    )

    signal = parse_audit_text(text, revenue_cr=1000)

    assert signal.auditor_name == "Deloitte Haskins & Sells LLP"
    assert signal.auditor_tier == "Big4"
    assert signal.opinion_type == "Clean"
    assert signal.emphasis_of_matter is False
    assert signal.key_audit_matters_count == 2


def test_parse_audit_text_detects_qualified_opinion_and_related_party_pct():
    text = (
        "Independent Auditor's Report\n"
        "For Gupta & Associates\n"
        "Qualified opinion\n"
        "Except for the matters described below, the statements are prepared.\n"
        "Emphasis of Matter\n"
        "Related party transactions aggregated to Rs. 250 crore.\n"
        "Statement of Profit and Loss\n"
    )

    signal = parse_audit_text(text, revenue_cr=1000)

    assert signal.auditor_tier == "Unknown"
    assert signal.opinion_type == "Qualified"
    assert signal.emphasis_of_matter is True
    assert signal.related_party_txn_pct_revenue == 25.0


def test_classify_auditor_identifies_mid_tier():
    assert classify_auditor("Lodha & Co LLP") == "MidTier"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
./.venv/bin/python -m pytest -q tests/test_governance_audit_parser.py
```

Expected:

```text
ModuleNotFoundError: No module named 'terminal.governance.audit_parser'
```

- [ ] **Step 3: Add audit parser implementation**

Create `terminal/governance/audit_parser.py` with text-first parsing and optional PDF extraction:

```python
from __future__ import annotations

import re
from pathlib import Path

from terminal.governance.models import AuditSignal


BIG4_NAMES = {
    "deloitte",
    "haskins & sells",
    "price waterhouse",
    "pricewaterhousecoopers",
    "ernst & young",
    "walker chandiok",
    "s r batliboi",
    "kpmg",
    "b s r",
}
MID_TIER_NAMES = {"lodha & co", "chaturvedi & shah", "nangia", "pkf", "s p jain"}


def classify_auditor(name: str) -> str:
    lowered = str(name or "").lower()
    if any(term in lowered for term in BIG4_NAMES):
        return "Big4"
    if any(term in lowered for term in MID_TIER_NAMES):
        return "MidTier"
    return "Unknown"


def extract_text_from_pdf(pdf_path: str | Path) -> str:
    path = Path(pdf_path)
    if not path.exists():
        return ""
    try:
        from pdfminer.high_level import extract_text
        return extract_text(str(path))
    except Exception:
        return ""


def extract_auditor_section(text: str) -> str | None:
    lowered = text.lower()
    start = None
    for marker in ("independent auditor", "auditor's report", "to the members of"):
        idx = lowered.find(marker)
        if idx != -1:
            start = idx
            break
    if start is None:
        return None
    end = len(text)
    for marker in ("balance sheet", "statement of profit and loss", "cash flow statement"):
        idx = lowered.find(marker, start + 100)
        if idx != -1:
            end = idx
            break
    return text[start:end]


def _auditor_name(text: str) -> str:
    known = [
        "Deloitte Haskins & Sells LLP",
        "Price Waterhouse",
        "Walker Chandiok",
        "S R Batliboi",
        "B S R",
        "KPMG",
        "Lodha & Co LLP",
        "Gupta & Associates",
    ]
    lowered = text.lower()
    for name in known:
        if name.lower() in lowered:
            return name
    match = re.search(r"for\s+([A-Z][A-Za-z\s&.]+(?:LLP|Associates|& Co))", text)
    return match.group(1).strip() if match else "Unknown"


def _opinion_type(text: str) -> str:
    lowered = text.lower()
    if "adverse opinion" in lowered:
        return "Adverse"
    if "disclaimer of opinion" in lowered or "unable to obtain sufficient appropriate audit evidence" in lowered:
        return "Disclaimer"
    if "qualified opinion" in lowered or "except for the matters" in lowered:
        return "Qualified"
    if "true and fair view" in lowered or "unmodified opinion" in lowered:
        return "Clean"
    return "Unknown"


def _rpt_pct(text: str, revenue_cr: float) -> float:
    if revenue_cr <= 0:
        return 0.0
    match = re.search(
        r"related\s+party\s+transactions?.*?(?:aggregated\s+to|amounted\s+to|totalled\s+to|totaled\s+to)\s*(?:rs\.?|₹)?\s*([\d,]+(?:\.\d+)?)\s*(crore|lakh|million)?",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return 0.0
    value = float(match.group(1).replace(",", ""))
    unit = (match.group(2) or "crore").lower()
    if unit == "lakh":
        value = value / 100
    if unit == "million":
        value = value / 10
    return round((value / revenue_cr) * 100, 1)


def parse_audit_text(text: str, *, revenue_cr: float = 0.0) -> AuditSignal:
    section = extract_auditor_section(text) or text
    auditor = _auditor_name(section)
    return AuditSignal(
        auditor_name=auditor,
        auditor_tier=classify_auditor(auditor),
        opinion_type=_opinion_type(section),
        emphasis_of_matter="emphasis of matter" in section.lower(),
        key_audit_matters_count=len(re.findall(r"key\s+audit\s+matter\s+\d+", section, re.IGNORECASE)),
        auditor_tenure_years=0,
        related_party_txn_pct_revenue=_rpt_pct(text, revenue_cr),
        source="annual_report",
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
./.venv/bin/python -m pytest -q tests/test_governance_audit_parser.py
```

Expected:

```text
4 passed
```

- [ ] **Step 5: Commit**

```bash
git add terminal/governance/audit_parser.py tests/test_governance_audit_parser.py
git commit -m "feat: add governance audit parser"
```

## Task 4: Cache Sources And NSE Client

**Files:**
- Create: `terminal/governance/cache_sources.py`
- Create: `terminal/governance/nse_client.py`
- Test: `tests/test_governance_sources.py`

- [ ] **Step 1: Write failing source-reader tests**

Create `tests/test_governance_sources.py`:

```python
import json

from terminal.governance.cache_sources import load_cached_sources
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


def test_load_cached_sources_filters_symbol_and_records_missing_files(tmp_path):
    data_dir = tmp_path
    cache = data_dir / "_insider_cache"
    cache.mkdir()
    (cache / "pit_2026-06-25.json").write_text(
        json.dumps([
            {"symbol": "AAA", "acqName": "Promoter", "tdpTransactionType": "Disposal"},
            {"symbol": "BBB", "acqName": "Other", "tdpTransactionType": "Acquisition"},
        ]),
        encoding="utf-8",
    )
    (cache / "bulk_2026-06-25.csv").write_text(
        "DATE,SYMBOL,ENTITY,SIDE,QTY,PRICE,SOURCE\n25-Jun-2026,AAA,Fund A,BUY,1000,25,BULK_DEAL\n",
        encoding="utf-8",
    )
    (data_dir / "corporate_events.csv").write_text(
        "SYMBOL,EVENT_TYPE,EVENT_DATE,PURPOSE_RAW,DETAIL,SOURCE\nAAA,AGM,2026-06-30,Annual General Meeting,,NSE\n",
        encoding="utf-8",
    )

    raw = load_cached_sources("AAA", data_dir=data_dir)

    assert raw.symbol == "AAA"
    assert len(raw.insider_payloads) == 1
    assert raw.insider_payloads[0]["data"][0]["symbol"] == "AAA"
    assert len(raw.deal_rows) == 1
    assert raw.announcement_rows[0]["SYMBOL"] == "AAA"
    assert {entry.name for entry in raw.source_trail} >= {
        "cache.pit",
        "cache.bulk_block_deals",
        "cache.corporate_events",
    }


def test_nse_json_client_returns_error_source_shape_without_raising():
    session = FakeSession()
    client = NSEJsonClient(session=session, seed_delay_s=0)

    result = client.get_json("/api/test", params={"symbol": "AAA"})

    assert result["status"] == "ok"
    assert result["json"] == {"data": [{"symbol": "AAA"}]}
    assert session.calls[0][0] == "https://www.nseindia.com"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
./.venv/bin/python -m pytest -q tests/test_governance_sources.py
```

Expected:

```text
ModuleNotFoundError: No module named 'terminal.governance.cache_sources'
```

- [ ] **Step 3: Add cache source implementation**

Create `terminal/governance/cache_sources.py`:

```python
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from terminal.governance.models import GovernanceMissingEvidence, GovernanceRawSources, GovernanceSource
from terminal.governance.parsers import parse_date


def _latest_file(paths: list[Path]) -> Path | None:
    return max(paths, key=lambda item: item.name) if paths else None


def _read_csv(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def load_cached_sources(symbol: str, *, data_dir: str | Path = "data") -> GovernanceRawSources:
    sym = symbol.upper().strip()
    root = Path(data_dir)
    source_trail: list[GovernanceSource] = []
    missing: list[GovernanceMissingEvidence] = []
    insider_payloads: list[dict[str, Any]] = []
    deal_rows: list[dict[str, Any]] = []
    announcement_rows: list[dict[str, Any]] = []

    cache = root / "_insider_cache"
    pit_file = _latest_file(sorted(cache.glob("pit_*.json"))) if cache.exists() else None
    if pit_file:
        rows = json.loads(pit_file.read_text(encoding="utf-8"))
        filtered = [row for row in rows if str(row.get("symbol") or "").upper() == sym]
        insider_payloads.append({"data": filtered})
        source_trail.append(GovernanceSource("cache.pit", "ok", rows=len(filtered), latest_date=parse_date(pit_file.stem[-10:]), fallback=True))
    else:
        missing.append(GovernanceMissingEvidence("governance", sym, "pit_cache", "warn", "No PIT cache file found"))

    if cache.exists():
        for file_path in sorted(list(cache.glob("bulk_*.csv")) + list(cache.glob("block_*.csv"))):
            for row in _read_csv(file_path):
                if str(row.get("SYMBOL") or "").upper() == sym:
                    deal_rows.append(row)
        source_trail.append(GovernanceSource("cache.bulk_block_deals", "ok", rows=len(deal_rows), fallback=True))
    else:
        missing.append(GovernanceMissingEvidence("governance", sym, "bulk_block_cache", "warn", "No insider cache directory found"))

    events = root / "corporate_events.csv"
    if events.exists():
        for row in _read_csv(events):
            if str(row.get("SYMBOL") or "").upper() == sym:
                announcement_rows.append(row)
        source_trail.append(GovernanceSource("cache.corporate_events", "ok", rows=len(announcement_rows), fallback=True))
    else:
        missing.append(GovernanceMissingEvidence("governance", sym, "corporate_events", "warn", "corporate_events.csv not found"))

    return GovernanceRawSources(
        symbol=sym,
        insider_payloads=insider_payloads,
        deal_rows=deal_rows,
        announcement_rows=announcement_rows,
        source_trail=source_trail,
        missing_evidence=missing,
    )
```

- [ ] **Step 4: Add NSE client implementation**

Create `terminal/governance/nse_client.py`:

```python
from __future__ import annotations

import time
from typing import Any

import requests


class NSEJsonClient:
    BASE_URL = "https://www.nseindia.com"

    def __init__(self, *, session: Any | None = None, seed_delay_s: float = 0.3, timeout_s: float = 12.0):
        self.session = session or requests.Session()
        self.seed_delay_s = seed_delay_s
        self.timeout_s = timeout_s
        self.seeded = False
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124 Safari/537.36",
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": self.BASE_URL + "/",
            }
        )

    def seed(self) -> None:
        if self.seeded:
            return
        try:
            self.session.get(self.BASE_URL, timeout=self.timeout_s)
            if self.seed_delay_s:
                time.sleep(self.seed_delay_s)
        finally:
            self.seeded = True

    def get_json(self, path: str, *, params: dict[str, Any] | None = None, retries: int = 1) -> dict[str, Any]:
        self.seed()
        url = path if path.startswith("http") else self.BASE_URL + path
        last_error = None
        for attempt in range(retries + 1):
            try:
                response = self.session.get(url, params=params, timeout=self.timeout_s)
                if response.status_code == 200:
                    return {"status": "ok", "json": response.json(), "status_code": 200}
                last_error = f"HTTP {response.status_code}"
            except Exception as exc:
                last_error = str(exc)
            if attempt < retries:
                time.sleep(0.5 * (attempt + 1))
        return {"status": "error", "json": None, "error": last_error}
```

- [ ] **Step 5: Run tests to verify they pass**

Run:

```bash
./.venv/bin/python -m pytest -q tests/test_governance_sources.py
```

Expected:

```text
2 passed
```

- [ ] **Step 6: Commit**

```bash
git add terminal/governance/cache_sources.py terminal/governance/nse_client.py tests/test_governance_sources.py
git commit -m "feat: add governance source readers"
```

## Task 5: Deterministic Scorer

**Files:**
- Create: `terminal/governance/scorer.py`
- Test: `tests/test_governance_scorer.py`

- [ ] **Step 1: Write failing scorer tests**

Create `tests/test_governance_scorer.py`:

```python
from datetime import date

from terminal.governance.models import (
    AuditSignal,
    CapitalAllocationSignal,
    ComplaintSignal,
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

    assert result.rating in {"CONCERN", "HIGH_RISK"}
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
./.venv/bin/python -m pytest -q tests/test_governance_scorer.py
```

Expected:

```text
ModuleNotFoundError: No module named 'terminal.governance.scorer'
```

- [ ] **Step 3: Add scorer implementation**

Create `terminal/governance/scorer.py` with these public functions:

```python
from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

from terminal.governance.models import ComponentScore, GovernanceEvidence, GovernanceMissingEvidence, GovernanceReport


def score_governance(evidence: GovernanceEvidence) -> GovernanceReport:
    components = [
        _score_promoter_pledge(evidence),
        _score_insider_activity(evidence),
        _score_institutional_trend(evidence),
        _score_audit(evidence),
        _score_announcements(evidence),
        _score_complaints(evidence),
        _score_capital_allocation(evidence),
    ]
    flags = _flags(evidence)
    score = round(sum(item.score for item in components), 1)
    confidence = _confidence(evidence)
    rating = _rating(score, flags, evidence, confidence)
    return GovernanceReport(
        symbol=evidence.symbol,
        as_of=evidence.as_of,
        score=score,
        rating=rating,
        confidence=confidence,
        component_scores=components,
        flags=flags,
        evidence=evidence,
        source_trail=evidence.source_trail,
        missing_evidence=evidence.missing_evidence,
        llm_status="not_requested",
    )
```

Use helper rules from the design:

```python
def _score_promoter_pledge(evidence: GovernanceEvidence) -> ComponentScore:
    if not evidence.shareholding:
        return ComponentScore("promoter_pledge", 0.0, 20.0, "missing", ["Shareholding evidence missing"], [])
    latest = evidence.shareholding[0]
    pledge = latest.pledge_pct or 0.0
    score = 20.0
    status = "green"
    notes = [f"Latest pledge {pledge:.1f}%"]
    if pledge > 25:
        score = 0.0
        status = "red"
    elif pledge >= 10:
        score = 8.0
        status = "amber"
    elif pledge > 0:
        score = 15.0
        status = "amber"
    if len(evidence.shareholding) >= 4:
        decline = (evidence.shareholding[3].promoter_pct or 0.0) - (latest.promoter_pct or 0.0)
        if decline > 2:
            score = min(score, 12.0)
            status = "amber" if status == "green" else status
            notes.append(f"Promoter holding declined {decline:.1f}pp over four quarters")
    return ComponentScore("promoter_pledge", score, 20.0, status, notes, ["shareholding"])
```

Implement the remaining helpers with the same deterministic pattern:

- `_score_insider_activity`: 15 max; score 15 for net recent buying, 10 for neutral/no activity, 5 for moderate net selling, 0 for selling value above 50 crore. Use `evidence.as_of - timedelta(days=365)` and date objects.
- `_score_institutional_trend`: 10 max; if at least two shareholding snapshots exist and FII+DII is rising, score 10; stable score 7; falling score 4; missing score 0 with status `missing`.
- `_score_audit`: 20 max; Big4 plus clean gets high score; qualified/adverse/disclaimer gets 0-5 and red; unknown missing gets 0 and missing.
- `_score_announcements`: 10 max; red announcements score 0, amber score 6, none score 10.
- `_score_complaints`: 10 max; zero pending and high resolution score 10; pending over 20 score 0; missing score 0 and missing.
- `_score_capital_allocation`: 15 max; strong FCF and low dilution score high; weak FCF/dilution/goodwill impairment reduce score; missing score 0 and missing.
- `_flags`: return strings for high pledge, promoter decline, heavy insider selling, non-clean audit, high RPT, unresolved complaints, weak FCF, high dilution.
- `_confidence`: High when shareholding, insider, audit or complaints/capital allocation are available; Medium for two core areas; Low otherwise.
- `_rating`: return `INSUFFICIENT_EVIDENCE` if no shareholding and no insider disclosures, `HIGH_RISK` for score <45 or severe red flags, `CONCERN` for red flags, `WATCH` for score >=65, otherwise `CONCERN`.

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
./.venv/bin/python -m pytest -q tests/test_governance_scorer.py
```

Expected:

```text
5 passed
```

- [ ] **Step 5: Commit**

```bash
git add terminal/governance/scorer.py tests/test_governance_scorer.py
git commit -m "feat: add deterministic governance scorer"
```

## Task 6: LLM Opinion Generator

**Files:**
- Create: `terminal/governance/opinion.py`
- Test: `tests/test_governance_opinion.py`

- [ ] **Step 1: Write failing opinion tests**

Create `tests/test_governance_opinion.py`:

```python
from datetime import date

from terminal.governance.models import GovernanceEvidence, GovernanceReport
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


def test_generate_governance_opinion_handles_llm_failure():
    def failing_llm(**kwargs):
        raise RuntimeError("provider unavailable")

    opinion = generate_governance_opinion(_report(), llm_client=failing_llm)

    assert opinion["status"] == "unavailable"
    assert "provider unavailable" in opinion["error"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
./.venv/bin/python -m pytest -q tests/test_governance_opinion.py
```

Expected:

```text
ModuleNotFoundError: No module named 'terminal.governance.opinion'
```

- [ ] **Step 3: Add opinion implementation**

Create `terminal/governance/opinion.py`:

```python
from __future__ import annotations

import json
from typing import Any, Callable

from terminal.governance.models import GovernanceReport
from terminal.research_council.llm_client import call_llm_json


ALLOWED_LABELS = {"Strong", "Watch", "Concern", "High Risk", "Insufficient Evidence"}

OPINION_SCHEMA = {
    "type": "object",
    "required": [
        "opinion_label",
        "summary",
        "strengths",
        "concerns",
        "data_gaps",
        "watch_items",
        "research_only_disclaimer",
    ],
    "properties": {
        "opinion_label": {"type": "string"},
        "summary": {"type": "string"},
        "strengths": {"type": "array", "items": {"type": "string"}},
        "concerns": {"type": "array", "items": {"type": "string"}},
        "data_gaps": {"type": "array", "items": {"type": "string"}},
        "watch_items": {"type": "array", "items": {"type": "string"}},
        "research_only_disclaimer": {"type": "string"},
    },
}


SYSTEM_PROMPT = (
    "You write research-only governance opinions for NSE-listed companies. "
    "Use only the structured evidence in the user payload. Do not add unsupported facts. "
    "Do not give investment advice, trading instructions, price targets, or recommendations. "
    "Always mention material data gaps and low confidence when present."
)


def generate_governance_opinion(
    report: GovernanceReport,
    *,
    llm_client: Callable | None = None,
) -> dict[str, Any]:
    client = llm_client or call_llm_json
    payload = {
        "symbol": report.symbol,
        "as_of": report.as_of.isoformat(),
        "score": report.score,
        "rating": report.rating,
        "confidence": report.confidence,
        "component_scores": [item.to_dict() for item in report.component_scores],
        "flags": report.flags,
        "missing_evidence": [item.to_dict() for item in report.missing_evidence],
        "source_trail": [item.to_dict() for item in report.source_trail],
    }
    try:
        opinion = client(
            system=SYSTEM_PROMPT,
            user=json.dumps(payload, sort_keys=True),
            schema=OPINION_SCHEMA,
            allow_deterministic_fallback=False,
        )
    except Exception as exc:
        return {"status": "unavailable", "error": str(exc)}
    label = opinion.get("opinion_label")
    if label not in ALLOWED_LABELS:
        return {"status": "invalid", "error": f"opinion_label must be one of {sorted(ALLOWED_LABELS)}", "raw": opinion}
    opinion["status"] = "ok"
    return opinion
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
./.venv/bin/python -m pytest -q tests/test_governance_opinion.py
```

Expected:

```text
3 passed
```

- [ ] **Step 5: Commit**

```bash
git add terminal/governance/opinion.py tests/test_governance_opinion.py
git commit -m "feat: add governance llm opinion generator"
```

## Task 7: Engine, Markdown, And CLI

**Files:**
- Create: `terminal/governance/engine.py`
- Create: `terminal/governance/markdown.py`
- Modify: `terminal/governance/__init__.py`
- Test: `tests/test_governance_engine.py`

- [ ] **Step 1: Write failing engine and Markdown tests**

Create `tests/test_governance_engine.py`:

```python
import json
from datetime import date

from terminal.governance.engine import evaluate_governance, main
from terminal.governance.markdown import render_markdown
from terminal.governance.models import GovernanceRawSources


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


def test_markdown_renders_score_flags_sources_and_disclaimer():
    report = evaluate_governance("AAA", raw_sources=_raw_sources(), as_of=date(2026, 6, 27), use_llm=False)

    text = render_markdown(report)

    assert "# Governance Evaluation - AAA" in text
    assert "Score:" in text
    assert "Source Trail" in text
    assert "Research-only" in text


def test_main_prints_json_with_injected_evaluator(capsys):
    def evaluator(symbol, **kwargs):
        return evaluate_governance(symbol, raw_sources=_raw_sources(), as_of=date(2026, 6, 27), use_llm=False)

    code = main(["AAA", "--json"], evaluator=evaluator)

    out = capsys.readouterr().out
    assert code == 0
    assert '"symbol": "AAA"' in out
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
./.venv/bin/python -m pytest -q tests/test_governance_engine.py
```

Expected:

```text
ModuleNotFoundError: No module named 'terminal.governance.engine'
```

- [ ] **Step 3: Add Markdown renderer**

Create `terminal/governance/markdown.py`:

```python
from __future__ import annotations

from terminal.governance.models import GovernanceReport


def render_markdown(report: GovernanceReport) -> str:
    lines = [
        f"# Governance Evaluation - {report.symbol}",
        "",
        f"- As of: {report.as_of.isoformat()}",
        f"- Score: {report.score:.1f}/100",
        f"- Rating: {report.rating}",
        f"- Confidence: {report.confidence}",
        "",
        "## Component Scores",
        "",
        "| Component | Score | Status | Notes |",
        "|---|---:|---|---|",
    ]
    for item in report.component_scores:
        lines.append(f"| {item.name} | {item.score:.1f}/{item.max_score:.1f} | {item.status} | {'; '.join(item.notes)} |")
    lines.extend(["", "## Flags", ""])
    if report.flags:
        lines.extend(f"- {flag}" for flag in report.flags)
    else:
        lines.append("- No red or amber flags from available evidence.")
    lines.extend(["", "## Missing Evidence", ""])
    if report.missing_evidence:
        lines.extend(f"- {item.field}: {item.reason or item.severity}" for item in report.missing_evidence)
    else:
        lines.append("- No material missing evidence recorded.")
    lines.extend(["", "## Source Trail", ""])
    if report.source_trail:
        lines.extend(f"- {item.name}: {item.status}, rows={item.rows}, fallback={item.fallback}" for item in report.source_trail)
    else:
        lines.append("- No source trail entries recorded.")
    if report.llm_opinion:
        lines.extend(["", "## LLM Opinion", "", str(report.llm_opinion.get("summary") or "")])
    lines.extend(["", "Research-only governance evaluation. Not investment advice."])
    return "\n".join(lines)
```

- [ ] **Step 4: Add engine implementation**

Create `terminal/governance/engine.py`:

```python
from __future__ import annotations

import argparse
import json
from datetime import date
from typing import Callable

from terminal.governance.audit_parser import parse_audit_text
from terminal.governance.cache_sources import load_cached_sources
from terminal.governance.markdown import render_markdown
from terminal.governance.models import GovernanceEvidence, GovernanceRawSources
from terminal.governance.opinion import generate_governance_opinion
from terminal.governance.parsers import (
    parse_complaint_signal,
    parse_deal_rows,
    parse_governance_announcements,
    parse_nse_insider_disclosures,
    parse_nse_shareholding,
    parse_screener_capital_allocation,
)
from terminal.governance.scorer import score_governance


def _build_evidence(symbol: str, raw: GovernanceRawSources, as_of: date) -> GovernanceEvidence:
    sym = symbol.upper().strip()
    shareholding = []
    for payload in raw.shareholding_payloads:
        shareholding.extend(parse_nse_shareholding(payload))
    shareholding.sort(key=lambda item: item.quarter_end or date.min, reverse=True)
    insiders = []
    for payload in raw.insider_payloads:
        insiders.extend(parse_nse_insider_disclosures(payload, symbol=sym))
    deals = parse_deal_rows(raw.deal_rows, symbol=sym)
    announcements = parse_governance_announcements(raw.announcement_rows, symbol=sym)
    complaints = parse_complaint_signal(raw.complaint_payloads[0]) if raw.complaint_payloads else None
    capital = parse_screener_capital_allocation(raw.screener_payload)
    audit = parse_audit_text(raw.annual_report_text) if raw.annual_report_text else None
    return GovernanceEvidence(
        symbol=sym,
        as_of=as_of,
        shareholding=shareholding,
        insider_disclosures=insiders,
        deals=deals,
        announcements=announcements,
        audit=audit,
        complaints=complaints,
        capital_allocation=capital,
        source_trail=raw.source_trail,
        missing_evidence=raw.missing_evidence,
    )


def evaluate_governance(
    symbol: str,
    *,
    use_llm: bool = False,
    raw_sources: GovernanceRawSources | None = None,
    llm_client: Callable | None = None,
    as_of: date | None = None,
    data_dir: str = "data",
):
    sym = symbol.upper().strip()
    current_date = as_of or date.today()
    raw = raw_sources or load_cached_sources(sym, data_dir=data_dir)
    evidence = _build_evidence(sym, raw, current_date)
    report = score_governance(evidence)
    if not use_llm:
        return report
    opinion = generate_governance_opinion(report, llm_client=llm_client)
    status = opinion.get("status") or "ok"
    from dataclasses import replace
    return replace(report, llm_status=status, llm_opinion=opinion if status == "ok" else None)


def main(argv: list[str] | None = None, *, evaluator=evaluate_governance) -> int:
    parser = argparse.ArgumentParser(description="Evaluate NSE governance evidence for one symbol.")
    parser.add_argument("symbol")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--llm", action="store_true")
    parser.add_argument("--markdown", action="store_true")
    args = parser.parse_args(argv)
    report = evaluator(args.symbol, use_llm=args.llm)
    if args.json:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    else:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Modify `terminal/governance/__init__.py`:

```python
"""Governance evaluation engine for NSE-listed companies."""

from terminal.governance.engine import evaluate_governance
from terminal.governance.markdown import render_markdown
from terminal.governance.models import GovernanceReport

__all__ = ["GovernanceReport", "evaluate_governance", "render_markdown"]
```

- [ ] **Step 5: Run tests to verify they pass**

Run:

```bash
./.venv/bin/python -m pytest -q tests/test_governance_engine.py
```

Expected:

```text
4 passed
```

- [ ] **Step 6: Commit**

```bash
git add terminal/governance/engine.py terminal/governance/markdown.py terminal/governance/__init__.py tests/test_governance_engine.py
git commit -m "feat: add governance evaluation engine"
```

## Task 8: Full Governance Test Suite And Smoke Verification

**Files:**
- Modify: files changed in Tasks 1-7 only if verification exposes defects.

- [ ] **Step 1: Run the focused governance suite**

Run:

```bash
./.venv/bin/python -m pytest -q \
  tests/test_governance_models.py \
  tests/test_governance_parsers.py \
  tests/test_governance_audit_parser.py \
  tests/test_governance_sources.py \
  tests/test_governance_scorer.py \
  tests/test_governance_opinion.py \
  tests/test_governance_engine.py
```

Expected:

```text
26 passed
```

- [ ] **Step 2: Run a no-network CLI smoke against cached data**

Run:

```bash
./.venv/bin/python -m terminal.governance.engine INFY --json
```

Expected:

```text
JSON output containing "symbol": "INFY", "score", "rating", "confidence", and "llm_status": "not_requested".
```

- [ ] **Step 3: Run nearby existing tests that cover reused LLM and parser conventions**

Run:

```bash
./.venv/bin/python -m pytest -q \
  tests/research_council/test_llm_client.py \
  tests/test_results_tools.py \
  tests/test_financial_filing_agent.py
```

Expected:

```text
All selected tests pass.
```

- [ ] **Step 4: Review git diff for unrelated changes**

Run:

```bash
git diff --stat terminal/governance tests/test_governance_*.py
git status --short terminal/governance tests/test_governance_*.py
```

Expected:

```text
Only governance package files and governance tests are listed.
```

- [ ] **Step 5: Commit verification fixes if any were required**

If Step 1, Step 2, or Step 3 required fixes, commit only those governance-related files:

```bash
git add terminal/governance tests/test_governance_*.py
git commit -m "test: verify governance evaluation engine"
```

If no fixes were required after Task 7, do not create an empty commit.

## Self-Review Checklist

- Spec coverage: Tasks 1-7 cover models, parser normalization, audit parsing, cache/NSE source boundaries, deterministic scoring, optional LLM opinion, engine orchestration, Markdown output, and CLI.
- TDD coverage: Every behavior-facing module has a failing test step before implementation.
- Network safety: Normal tests use injected fixtures and fake clients only.
- Type consistency: The plan uses `GovernanceRawSources`, `GovernanceEvidence`, `GovernanceReport`, `ComponentScore`, `GovernanceSource`, and `GovernanceMissingEvidence` consistently across modules.
- Scope discipline: Batch scanner, database migrations, and Research Council agent integration are explicitly outside V1.
