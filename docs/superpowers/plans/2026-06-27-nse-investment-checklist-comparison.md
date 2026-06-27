# NSE Investment Checklist Comparison Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `/investment-checklist` as a deterministic, evidence-gated, multi-stock NSE value checklist comparison report.

**Architecture:** Add a focused `terminal/value_checklist.py` module that owns data models, scoring, verdict caps, report rendering, output writing, and the command handler. Wire the command through `nse_agent._build_command_registry()` and the visible slash/help surfaces, while keeping V1 independent of Research Council orchestration.

**Tech Stack:** Python 3 dataclasses, stdlib `csv` for summary output, existing Agent Adda command registry, existing `terminal.tools.get_symbol_snapshot`, existing `terminal.financials_cache.screener_payload_from_cache`, existing `terminal.reports._md_to_html_basic`, pytest.

---

## File Structure

- Create `terminal/value_checklist.py`
  - Data classes: `ValueChecklistEvidence`, `ChecklistDimensionScore`, `ValueChecklistResult`, `ValueChecklistReport`.
  - Scoring constants and verdict priority.
  - Pure scoring functions for synthetic and real evidence.
  - Evidence collection from local Agent Adda providers.
  - Markdown, HTML, CSV summary, and report output writing.
  - `handle_investment_checklist_command(text, project_root=None) -> str`.

- Create `tests/test_value_checklist.py`
  - Unit tests for scoring weights, missing evidence, hard caps, ranking, mirror-test behavior, and synthetic comparison results.

- Create `tests/test_value_checklist_report.py`
  - Unit tests for Markdown report shape, HTML conversion, CSV/latest output writing, and deterministic disclaimer/source trail.

- Create `tests/test_terminal_investment_checklist.py`
  - Command-registry and slash-command visibility tests with monkeypatched command output.

- Modify `nse_agent.py`
  - Add `/investment-checklist` to `_SLASH_COMMANDS`.
  - Add `/investment-checklist` to `_CMD_CATEGORIES`.
  - Register an `investment-checklist` `CommandHandler` in `_build_command_registry()`.

- Modify `terminal/help.py`
  - Add a help entry under Research, Reports, or Fundamentals for `/investment-checklist`.

## Task 1: Add Core Scoring Tests

**Files:**
- Create: `tests/test_value_checklist.py`
- Create: `terminal/value_checklist.py`

- [ ] **Step 1: Write failing tests for deterministic scoring**

Create `tests/test_value_checklist.py` with:

```python
from terminal.value_checklist import (
    CHECKLIST_DIMENSIONS,
    ValueChecklistEvidence,
    build_checklist_result,
    compare_checklist_results,
)


def _evidence(
    symbol: str,
    *,
    fundamentals: dict | None = None,
    valuation: dict | None = None,
    governance: dict | None = None,
    technical: dict | None = None,
    missing_evidence: tuple[str, ...] = (),
) -> ValueChecklistEvidence:
    return ValueChecklistEvidence(
        symbol=symbol,
        company_name=f"{symbol} Ltd",
        sector="Information Technology",
        fundamentals={
            "roe": 24.0,
            "roce": 31.0,
            "opm_pct": 26.0,
            "free_cash_flow_positive": True,
            "debt_to_equity": 0.05,
            "sales_growth": 12.0,
            "profit_growth": 14.0,
            "enhanced_fund_score": 82.0,
        } if fundamentals is None else fundamentals,
        valuation={
            "pe": 24.0,
            "pb": 5.5,
            "earnings_yield_pct": 4.2,
            "valuation_signal": "reasonable",
        } if valuation is None else valuation,
        governance={
            "promoter_pledge_pct": 0.0,
            "forensic_risk": "low",
            "insider_signal": "neutral",
        } if governance is None else governance,
        technical={
            "stage": "STAGE_2",
            "relative_strength": 1.18,
            "rsi": 61.0,
            "technical_score": 78.0,
            "trend_signal": "BULLISH",
            "trading_signal": "BUY",
        } if technical is None else technical,
        latest_results={"status": "ok", "sales_yoy_pct": 10.0, "pat_yoy_pct": 13.0},
        source_trail=(
            {"name": "scores.stage_snapshots", "status": "ok"},
            {"name": "screener_cache", "status": "ok"},
        ),
        missing_evidence=missing_evidence,
        freshness={"stage_snapshot": "2026-06-26", "fundamentals": "cached"},
    )


def test_checklist_weights_sum_to_100():
    assert sum(item.weight for item in CHECKLIST_DIMENSIONS) == 100


def test_missing_fundamentals_returns_insufficient_evidence():
    result = build_checklist_result(
        _evidence("MISS", fundamentals={}, missing_evidence=("fundamentals",))
    )

    assert result.verdict == "INSUFFICIENT_EVIDENCE"
    assert result.total_score == 0
    assert "fundamentals" in result.missing_evidence
    assert "Missing fundamentals" in " ".join(result.hard_caps)


def test_governance_red_flag_caps_verdict():
    result = build_checklist_result(
        _evidence(
            "PLEDGE",
            governance={
                "promoter_pledge_pct": 28.0,
                "forensic_risk": "high",
                "insider_signal": "negative",
            },
        )
    )

    assert result.verdict in {"WATCH", "AVOID"}
    assert any("governance" in cap.lower() for cap in result.hard_caps)


def test_stage4_caps_verdict_at_watch():
    result = build_checklist_result(
        _evidence(
            "WEAKTECH",
            technical={
                "stage": "STAGE_4",
                "relative_strength": 0.72,
                "rsi": 38.0,
                "technical_score": 22.0,
                "trend_signal": "BEARISH",
                "trading_signal": "SELL",
            },
        )
    )

    assert result.verdict in {"WATCH", "AVOID"}
    assert any("Stage 4" in cap for cap in result.hard_caps)


def test_strong_quality_reasonable_valuation_outranks_weak_expensive_name():
    strong = build_checklist_result(_evidence("STRONG"))
    weak = build_checklist_result(
        _evidence(
            "EXPENSIVE",
            fundamentals={
                "roe": 8.0,
                "roce": 10.0,
                "opm_pct": 8.0,
                "free_cash_flow_positive": False,
                "debt_to_equity": 1.4,
                "sales_growth": 2.0,
                "profit_growth": -3.0,
                "enhanced_fund_score": 35.0,
            },
            valuation={
                "pe": 88.0,
                "pb": 14.0,
                "earnings_yield_pct": 1.1,
                "valuation_signal": "expensive",
            },
            technical={
                "stage": "STAGE_3",
                "relative_strength": 0.88,
                "rsi": 49.0,
                "technical_score": 42.0,
                "trend_signal": "MIXED",
                "trading_signal": "HOLD",
            },
        )
    )

    ranked = compare_checklist_results([weak, strong])

    assert ranked[0].symbol == "STRONG"
    assert ranked[0].total_score > ranked[1].total_score


def test_mirror_test_fails_when_core_claims_are_missing():
    result = build_checklist_result(
        _evidence("THIN", valuation={}, missing_evidence=("valuation",))
    )

    assert result.mirror_test_passed is False
    assert any("valuation" in item.lower() for item in result.mirror_test)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
./.venv/bin/python -m pytest -q tests/test_value_checklist.py
```

Expected:

```text
ModuleNotFoundError: No module named 'terminal.value_checklist'
```

- [ ] **Step 3: Add minimal scoring module**

Create `terminal/value_checklist.py` with:

```python
"""NSE investment checklist comparison workflow.

Deterministic scoring and report rendering for `/investment-checklist`.
"""

from __future__ import annotations

import csv
import datetime as _dt
import html as _html
import math
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping


ROOT = Path(__file__).resolve().parent.parent
VALUE_CHECKLIST_DIR = ROOT / "reports" / "value_checklists"
LATEST_DIR = ROOT / "reports" / "latest"


@dataclass(frozen=True)
class ChecklistDimension:
    key: str
    label: str
    weight: int


CHECKLIST_DIMENSIONS: tuple[ChecklistDimension, ...] = (
    ChecklistDimension("understandable_business", "Understandable Business", 10),
    ChecklistDimension("business_quality", "Business Quality", 20),
    ChecklistDimension("moat", "Moat / Competitive Position", 15),
    ChecklistDimension("governance", "Management / Governance", 15),
    ChecklistDimension("valuation", "Valuation / Safety Margin", 15),
    ChecklistDimension("technical", "Technical Confirmation", 15),
    ChecklistDimension("decision_discipline", "Decision Discipline", 10),
)

VERDICT_PRIORITY = {
    "PASS": 0,
    "CONDITIONAL": 1,
    "WATCH": 2,
    "AVOID": 3,
    "INSUFFICIENT_EVIDENCE": 4,
}


@dataclass(frozen=True)
class ValueChecklistEvidence:
    symbol: str
    company_name: str = ""
    sector: str = ""
    fundamentals: Mapping[str, Any] | None = None
    valuation: Mapping[str, Any] | None = None
    governance: Mapping[str, Any] | None = None
    technical: Mapping[str, Any] | None = None
    latest_results: Mapping[str, Any] | None = None
    source_trail: tuple[Mapping[str, Any], ...] = ()
    missing_evidence: tuple[str, ...] = ()
    freshness: Mapping[str, str] | None = None


@dataclass(frozen=True)
class ChecklistDimensionScore:
    name: str
    weight: float
    raw_score: float
    weighted_score: float
    reasons: tuple[str, ...]
    missing_evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class ValueChecklistResult:
    symbol: str
    company_name: str
    verdict: str
    total_score: float
    evidence_quality: str
    dimension_scores: tuple[ChecklistDimensionScore, ...]
    hard_caps: tuple[str, ...]
    top_strengths: tuple[str, ...]
    top_risks: tuple[str, ...]
    mirror_test: tuple[str, ...]
    mirror_test_passed: bool
    source_trail: tuple[Mapping[str, Any], ...]
    missing_evidence: tuple[str, ...]


@dataclass(frozen=True)
class ValueChecklistReport:
    markdown: str
    html: str
    summary_rows: tuple[dict[str, Any], ...]
    markdown_path: str
    html_path: str
    summary_csv_path: str
    latest_markdown_path: str
    latest_html_path: str
    latest_summary_csv_path: str


def build_checklist_result(evidence: ValueChecklistEvidence) -> ValueChecklistResult:
    missing = tuple(dict.fromkeys(str(item) for item in (evidence.missing_evidence or ())))
    fundamentals = dict(evidence.fundamentals or {})
    if not fundamentals:
        return _insufficient_result(evidence, missing + ("fundamentals",), "Missing fundamentals")

    scores = (
        _score_understandable_business(evidence),
        _score_business_quality(evidence),
        _score_moat(evidence),
        _score_governance(evidence),
        _score_valuation(evidence),
        _score_technical(evidence),
        _score_decision_discipline(evidence),
    )
    total = round(sum(item.weighted_score for item in scores), 2)
    hard_caps = _hard_caps(evidence)
    verdict = _base_verdict(total, _evidence_quality(evidence, missing))
    verdict = _apply_caps(verdict, hard_caps)
    strengths, risks = _strengths_and_risks(scores, hard_caps)
    mirror_test, mirror_passed = _mirror_test(evidence, missing, verdict)
    return ValueChecklistResult(
        symbol=_sym(evidence.symbol),
        company_name=str(evidence.company_name or evidence.symbol or "").strip(),
        verdict=verdict,
        total_score=total,
        evidence_quality=_evidence_quality(evidence, missing),
        dimension_scores=scores,
        hard_caps=hard_caps,
        top_strengths=strengths,
        top_risks=risks,
        mirror_test=mirror_test,
        mirror_test_passed=mirror_passed,
        source_trail=tuple(evidence.source_trail or ()),
        missing_evidence=missing,
    )


def compare_checklist_results(results: Iterable[ValueChecklistResult]) -> list[ValueChecklistResult]:
    return sorted(
        list(results),
        key=lambda item: (
            VERDICT_PRIORITY.get(item.verdict, 99),
            -item.total_score,
            _quality_rank(item.evidence_quality),
            item.symbol,
        ),
    )
```

Append helper functions:

```python
def _sym(value: Any) -> str:
    return re.sub(r"[^A-Z0-9&-]", "", str(value or "").upper())


def _num(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
        return out if math.isfinite(out) else default
    except Exception:
        return default


def _has_missing(evidence: ValueChecklistEvidence, name: str) -> bool:
    missing = {str(item).lower() for item in evidence.missing_evidence or ()}
    return name.lower() in missing


def _dimension(name: str, weight: float, raw: float, reasons: list[str], missing: tuple[str, ...] = ()) -> ChecklistDimensionScore:
    raw = max(0.0, min(100.0, float(raw)))
    return ChecklistDimensionScore(
        name=name,
        weight=weight,
        raw_score=round(raw, 2),
        weighted_score=round(raw * weight / 100.0, 2),
        reasons=tuple(reasons),
        missing_evidence=missing,
    )


def _score_understandable_business(evidence: ValueChecklistEvidence) -> ChecklistDimensionScore:
    sector = str(evidence.sector or "").strip()
    raw = 80.0 if sector else 45.0
    reasons = [f"Sector identified as {sector}."] if sector else ["Sector/business context is missing."]
    return _dimension("Understandable Business", 10, raw, reasons, () if sector else ("sector",))


def _score_business_quality(evidence: ValueChecklistEvidence) -> ChecklistDimensionScore:
    f = dict(evidence.fundamentals or {})
    raw = 35.0
    reasons: list[str] = []
    roe = _num(f.get("roe"))
    roce = _num(f.get("roce"))
    opm = _num(f.get("opm_pct"))
    debt = _num(f.get("debt_to_equity"))
    fund_score = _num(f.get("enhanced_fund_score") or f.get("fundamental_score"))
    if roe >= 20 or roce >= 25:
        raw += 20
        reasons.append("High return ratios.")
    if opm >= 18:
        raw += 12
        reasons.append("Healthy operating margin.")
    if f.get("free_cash_flow_positive") is True:
        raw += 12
        reasons.append("Positive cash conversion.")
    if debt <= 0.5:
        raw += 10
        reasons.append("Low leverage.")
    if fund_score >= 70:
        raw += 12
        reasons.append("Strong Agent Adda fundamental score.")
    return _dimension("Business Quality", 20, raw, reasons or ["Business quality evidence is mixed."])


def _score_moat(evidence: ValueChecklistEvidence) -> ChecklistDimensionScore:
    t = dict(evidence.technical or {})
    f = dict(evidence.fundamentals or {})
    raw = 45.0
    reasons: list[str] = []
    if _num(t.get("relative_strength")) >= 1.0:
        raw += 18
        reasons.append("Relative strength is above market baseline.")
    if _num(f.get("enhanced_fund_score") or f.get("fundamental_score")) >= 75:
        raw += 16
        reasons.append("Quality score supports competitive position.")
    if str(evidence.sector or ""):
        raw += 8
        reasons.append("Sector context is available.")
    return _dimension("Moat / Competitive Position", 15, raw, reasons or ["Moat evidence is not conclusive."])


def _score_governance(evidence: ValueChecklistEvidence) -> ChecklistDimensionScore:
    g = dict(evidence.governance or {})
    pledge = _num(g.get("promoter_pledge_pct"))
    risk = str(g.get("forensic_risk") or "").lower()
    raw = 80.0
    reasons = ["No severe governance issue found in collected evidence."]
    if pledge > 0:
        raw -= min(35.0, pledge)
        reasons.append(f"Promoter pledge detected at {pledge:.1f}%.")
    if risk in {"high", "severe"}:
        raw -= 35
        reasons.append("Forensic risk is high.")
    elif risk in {"medium", "watch"}:
        raw -= 15
        reasons.append("Forensic risk requires monitoring.")
    return _dimension("Management / Governance", 15, raw, reasons)


def _score_valuation(evidence: ValueChecklistEvidence) -> ChecklistDimensionScore:
    v = dict(evidence.valuation or {})
    if not v:
        return _dimension("Valuation / Safety Margin", 15, 35.0, ["Valuation evidence is missing."], ("valuation",))
    pe = _num(v.get("pe"))
    pb = _num(v.get("pb"))
    earnings_yield = _num(v.get("earnings_yield_pct"))
    signal = str(v.get("valuation_signal") or "").lower()
    raw = 55.0
    reasons: list[str] = []
    if 0 < pe <= 30:
        raw += 18
        reasons.append("PE is not stretched for a quality screen.")
    if 0 < pb <= 8:
        raw += 8
        reasons.append("PB is within a tolerable range.")
    if earnings_yield >= 3:
        raw += 10
        reasons.append("Earnings yield offers some valuation support.")
    if signal == "expensive" or pe >= 70:
        raw -= 25
        reasons.append("Valuation appears stretched.")
    return _dimension("Valuation / Safety Margin", 15, raw, reasons or ["Valuation evidence is neutral."])


def _score_technical(evidence: ValueChecklistEvidence) -> ChecklistDimensionScore:
    t = dict(evidence.technical or {})
    stage = str(t.get("stage") or "").upper()
    score = _num(t.get("technical_score"))
    raw = score if score else 45.0
    reasons: list[str] = []
    if stage == "STAGE_2":
        raw += 15
        reasons.append("Stage 2 technical confirmation.")
    elif stage == "STAGE_4":
        raw -= 25
        reasons.append("Stage 4 technical breakdown.")
    if str(t.get("trend_signal") or "").upper() in {"BULLISH", "STRONG_BULLISH"}:
        raw += 8
        reasons.append("Bullish trend signal.")
    if str(t.get("trading_signal") or "").upper() in {"BUY", "STRONG_BUY"}:
        raw += 7
        reasons.append("Constructive trading signal.")
    return _dimension("Technical Confirmation", 15, raw, reasons or ["Technical evidence is mixed."])


def _score_decision_discipline(evidence: ValueChecklistEvidence) -> ChecklistDimensionScore:
    missing = tuple(evidence.missing_evidence or ())
    raw = 80.0 - min(40.0, len(missing) * 10.0)
    reasons = ["Mirror-test claims can be built from collected evidence."] if raw >= 70 else ["Mirror-test claims have evidence gaps."]
    return _dimension("Decision Discipline", 10, raw, reasons, missing)
```

Append verdict helpers:

```python
def _evidence_quality(evidence: ValueChecklistEvidence, missing: tuple[str, ...]) -> str:
    if len(missing) >= 3:
        return "low"
    if missing:
        return "medium"
    if evidence.source_trail:
        return "higher"
    return "medium"


def _quality_rank(value: str) -> int:
    return {"higher": 0, "medium": 1, "low": 2}.get(str(value or "").lower(), 3)


def _base_verdict(total: float, quality: str) -> str:
    if quality == "low":
        return "INSUFFICIENT_EVIDENCE"
    if total >= 78:
        return "PASS"
    if total >= 65:
        return "CONDITIONAL"
    if total >= 50:
        return "WATCH"
    return "AVOID"


def _hard_caps(evidence: ValueChecklistEvidence) -> tuple[str, ...]:
    caps: list[str] = []
    g = dict(evidence.governance or {})
    f = dict(evidence.fundamentals or {})
    v = dict(evidence.valuation or {})
    t = dict(evidence.technical or {})
    if _num(g.get("promoter_pledge_pct")) >= 20 or str(g.get("forensic_risk") or "").lower() in {"high", "severe"}:
        caps.append("Severe governance or promoter pledge red flag caps verdict.")
    if f.get("free_cash_flow_positive") is False:
        caps.append("Weak cash conversion caps verdict at CONDITIONAL.")
    if str(t.get("stage") or "").upper() == "STAGE_4":
        caps.append("Stage 4 technical breakdown caps verdict at WATCH.")
    if str(v.get("valuation_signal") or "").lower() == "expensive" or _num(v.get("pe")) >= 70:
        caps.append("Excessive valuation caps verdict at WATCH.")
    return tuple(caps)


def _apply_caps(verdict: str, hard_caps: tuple[str, ...]) -> str:
    capped = verdict
    for cap in hard_caps:
        low = cap.lower()
        if "governance" in low:
            capped = _worse_verdict(capped, "WATCH")
        if "cash conversion" in low:
            capped = _worse_verdict(capped, "CONDITIONAL")
        if "stage 4" in low:
            capped = _worse_verdict(capped, "WATCH")
        if "valuation" in low:
            capped = _worse_verdict(capped, "WATCH")
    return capped


def _worse_verdict(current: str, cap: str) -> str:
    if VERDICT_PRIORITY.get(current, 99) < VERDICT_PRIORITY.get(cap, 99):
        return cap
    return current


def _strengths_and_risks(scores: tuple[ChecklistDimensionScore, ...], caps: tuple[str, ...]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    strengths: list[str] = []
    risks: list[str] = list(caps)
    for score in sorted(scores, key=lambda item: item.raw_score, reverse=True):
        if score.raw_score >= 70 and score.reasons:
            strengths.append(f"{score.name}: {score.reasons[0]}")
        if score.raw_score < 50 and score.reasons:
            risks.append(f"{score.name}: {score.reasons[0]}")
    return tuple(strengths[:3] or ("No decisive strength surfaced.",)), tuple(risks[:3] or ("No severe risk surfaced in collected evidence.",))


def _mirror_test(evidence: ValueChecklistEvidence, missing: tuple[str, ...], verdict: str) -> tuple[tuple[str, ...], bool]:
    if any(item in {"fundamentals", "valuation"} for item in missing):
        return (
            "Mirror test failed: fundamentals or valuation evidence is missing.",
            f"Missing evidence: {', '.join(missing)}.",
        ), False
    f = dict(evidence.fundamentals or {})
    v = dict(evidence.valuation or {})
    t = dict(evidence.technical or {})
    claims = (
        f"{_sym(evidence.symbol)} business context is tied to {evidence.sector or 'an identified NSE sector'}.",
        f"Quality evidence: ROE {_num(f.get('roe')):.1f}%, ROCE {_num(f.get('roce')):.1f}%.",
        f"Governance evidence does not force an avoid verdict; final verdict is {verdict}.",
        f"Valuation evidence: PE {_num(v.get('pe')):.1f}, earnings yield {_num(v.get('earnings_yield_pct')):.1f}%.",
        f"Technical evidence: {str(t.get('stage') or 'UNKNOWN')} with signal {str(t.get('trading_signal') or 'n/a')}.",
    )
    return claims, verdict not in {"INSUFFICIENT_EVIDENCE", "AVOID"}


def _insufficient_result(evidence: ValueChecklistEvidence, missing: tuple[str, ...], reason: str) -> ValueChecklistResult:
    clean_missing = tuple(dict.fromkeys(str(item) for item in missing if str(item)))
    return ValueChecklistResult(
        symbol=_sym(evidence.symbol),
        company_name=str(evidence.company_name or evidence.symbol or "").strip(),
        verdict="INSUFFICIENT_EVIDENCE",
        total_score=0.0,
        evidence_quality="low",
        dimension_scores=(),
        hard_caps=(reason,),
        top_strengths=("No ranking strength assigned because required evidence is missing.",),
        top_risks=(reason,),
        mirror_test=(f"Mirror test failed: {reason}.",),
        mirror_test_passed=False,
        source_trail=tuple(evidence.source_trail or ()),
        missing_evidence=clean_missing,
    )
```

- [ ] **Step 4: Run core tests**

Run:

```bash
./.venv/bin/python -m pytest -q tests/test_value_checklist.py
```

Expected:

```text
6 passed
```

- [ ] **Step 5: Commit Task 1**

Run:

```bash
git add terminal/value_checklist.py tests/test_value_checklist.py
git commit -m "feat: add NSE value checklist scoring"
```

## Task 2: Add Evidence Collection And Command Parser Tests

**Files:**
- Modify: `tests/test_value_checklist.py`
- Modify: `terminal/value_checklist.py`

- [ ] **Step 1: Add tests for symbol parsing and provider normalization**

Append to `tests/test_value_checklist.py`:

```python
from terminal.value_checklist import (
    collect_value_checklist_evidence,
    parse_investment_checklist_symbols,
)


def test_parse_investment_checklist_symbols_accepts_commas_spaces_and_dedupes():
    assert parse_investment_checklist_symbols("/investment-checklist TCS, INFY HDFCBANK TCS") == [
        "TCS",
        "INFY",
        "HDFCBANK",
    ]


def test_parse_investment_checklist_symbols_limits_to_ten():
    text = "/investment-checklist " + " ".join(f"S{i}" for i in range(12))

    assert parse_investment_checklist_symbols(text) == [f"S{i}" for i in range(10)]


def test_collect_evidence_uses_stage_snapshot_and_cached_screener(monkeypatch):
    def fake_snapshot(symbol):
        return {
            "symbol": symbol,
            "company_name": f"{symbol} Ltd",
            "sector": "IT",
            "stage": "STAGE_2",
            "relative_strength": 1.2,
            "rsi": 62,
            "technical_score": 81,
            "trend_signal": "BULLISH",
            "trading_signal": "BUY",
            "enhanced_fund_score": 84,
            "fundamental_score": 78,
            "earnings_quality": 82,
            "sales_growth": 13,
            "financial_strength": 88,
            "data_source": "scores.stage_snapshots",
            "snapshot_date": "2026-06-26",
            "missing_evidence": [],
        }

    def fake_cache(symbol, max_age_hours=None):
        return {
            "ratios": {"Stock P/E": "24", "ROE": "24%", "ROCE": "31%", "Debt to equity": "0.05"},
            "annual_pl": {"OPM %": ["22%", "24%", "26%"], "_headers": ["Mar 2024", "Mar 2025", "Mar 2026"]},
            "cash_flow": {"Free Cash Flow": ["1200", "1500", "1800"], "_headers": ["Mar 2024", "Mar 2025", "Mar 2026"]},
            "_cache_age_hours": 2.5,
        }

    monkeypatch.setattr("terminal.tools.get_symbol_snapshot", fake_snapshot)
    monkeypatch.setattr("terminal.financials_cache.screener_payload_from_cache", fake_cache)

    evidence = collect_value_checklist_evidence(["TCS"])[0]

    assert evidence.symbol == "TCS"
    assert evidence.company_name == "TCS Ltd"
    assert evidence.fundamentals["roe"] == 24.0
    assert evidence.valuation["pe"] == 24.0
    assert evidence.technical["stage"] == "STAGE_2"
    assert evidence.missing_evidence == ()
    assert any(item["name"] == "scores.stage_snapshots" for item in evidence.source_trail)


def test_collect_evidence_marks_missing_fundamentals(monkeypatch):
    monkeypatch.setattr(
        "terminal.tools.get_symbol_snapshot",
        lambda symbol: {"symbol": symbol, "error": "not found", "missing_evidence": ["stage_snapshot"]},
    )
    monkeypatch.setattr("terminal.financials_cache.screener_payload_from_cache", lambda symbol, max_age_hours=None: None)

    evidence = collect_value_checklist_evidence(["NOPE"])[0]

    assert evidence.symbol == "NOPE"
    assert "fundamentals" in evidence.missing_evidence
    assert "stage_snapshot" in evidence.missing_evidence
```

- [ ] **Step 2: Run the new tests to verify failures**

Run:

```bash
./.venv/bin/python -m pytest -q tests/test_value_checklist.py::test_parse_investment_checklist_symbols_accepts_commas_spaces_and_dedupes tests/test_value_checklist.py::test_collect_evidence_uses_stage_snapshot_and_cached_screener
```

Expected:

```text
ImportError: cannot import name 'collect_value_checklist_evidence'
```

- [ ] **Step 3: Implement parsing and evidence collection**

Append to `terminal/value_checklist.py`:

```python
def parse_investment_checklist_symbols(text: str, *, limit: int = 10) -> list[str]:
    raw = re.sub(r"^\s*/(?:investment-checklist|investment_checklist)\b", "", text or "", flags=re.IGNORECASE)
    tokens = re.split(r"[\s,，、]+", raw.strip())
    symbols: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        sym = _sym(token)
        if not sym or sym in seen:
            continue
        seen.add(sym)
        symbols.append(sym)
        if len(symbols) >= limit:
            break
    return symbols


def collect_value_checklist_evidence(symbols: Iterable[str]) -> list[ValueChecklistEvidence]:
    evidence: list[ValueChecklistEvidence] = []
    for symbol in symbols:
        evidence.append(_collect_one_symbol_evidence(_sym(symbol)))
    return evidence


def _collect_one_symbol_evidence(symbol: str) -> ValueChecklistEvidence:
    snapshot: dict[str, Any] = {}
    screener: dict[str, Any] | None = None
    missing: list[str] = []
    source_trail: list[dict[str, Any]] = []

    try:
        from terminal.tools import get_symbol_snapshot

        snapshot = get_symbol_snapshot(symbol)
        if snapshot.get("error"):
            missing.extend(snapshot.get("missing_evidence") or ["stage_snapshot"])
            source_trail.append({"name": "scores.stage_snapshots", "status": f"ERROR: {snapshot.get('error')}"})
        else:
            source_trail.append({"name": "scores.stage_snapshots", "status": "ok", "date": snapshot.get("snapshot_date")})
    except Exception as exc:
        missing.append("stage_snapshot")
        source_trail.append({"name": "scores.stage_snapshots", "status": f"ERROR: {exc}"})

    try:
        from terminal.financials_cache import screener_payload_from_cache

        screener = screener_payload_from_cache(symbol, max_age_hours=None)
        if screener:
            source_trail.append({"name": "screener_cache", "status": "ok", "age_hours": screener.get("_cache_age_hours")})
        else:
            missing.append("fundamentals")
            source_trail.append({"name": "screener_cache", "status": "missing"})
    except Exception as exc:
        missing.append("fundamentals")
        source_trail.append({"name": "screener_cache", "status": f"ERROR: {exc}"})

    fundamentals = _fundamentals_from_sources(snapshot, screener or {})
    valuation = _valuation_from_screener(screener or {})
    governance = _governance_from_screener(screener or {})
    technical = _technical_from_snapshot(snapshot)
    if not fundamentals:
        missing.append("fundamentals")
    if not valuation:
        missing.append("valuation")
    return ValueChecklistEvidence(
        symbol=symbol,
        company_name=str(snapshot.get("company_name") or symbol),
        sector=str(snapshot.get("sector") or ""),
        fundamentals=fundamentals,
        valuation=valuation,
        governance=governance,
        technical=technical,
        latest_results=_latest_results_from_snapshot(snapshot),
        source_trail=tuple(source_trail),
        missing_evidence=tuple(dict.fromkeys(item for item in missing if item)),
        freshness={
            "stage_snapshot": str(snapshot.get("snapshot_date") or ""),
            "fundamentals": str((screener or {}).get("_cache_age_hours") or "cached"),
        },
    )


def _fundamentals_from_sources(snapshot: Mapping[str, Any], screener: Mapping[str, Any]) -> dict[str, Any]:
    ratios = dict(screener.get("ratios") or {})
    annual = dict(screener.get("annual_pl") or {})
    cash_flow = dict(screener.get("cash_flow") or {})
    out: dict[str, Any] = {}
    out["roe"] = _first_number(ratios, ("ROE", "Return on equity"))
    out["roce"] = _first_number(ratios, ("ROCE", "Return on capital employed"))
    out["debt_to_equity"] = _first_number(ratios, ("Debt to equity", "Debt / Equity"))
    out["opm_pct"] = _last_series_number(annual, ("OPM %", "OPM"))
    out["free_cash_flow_positive"] = _last_series_number(cash_flow, ("Free Cash Flow", "FCF")) > 0
    for key in ("enhanced_fund_score", "fundamental_score", "earnings_quality", "sales_growth", "financial_strength"):
        if snapshot.get(key) is not None:
            out[key] = _num(snapshot.get(key))
    return {key: value for key, value in out.items() if value not in (None, "")}


def _valuation_from_screener(screener: Mapping[str, Any]) -> dict[str, Any]:
    ratios = dict(screener.get("ratios") or {})
    pe = _first_number(ratios, ("Stock P/E", "P/E", "PE"))
    pb = _first_number(ratios, ("Price to book value", "Price to Book", "PB"))
    out: dict[str, Any] = {}
    if pe:
        out["pe"] = pe
        out["earnings_yield_pct"] = round(100.0 / pe, 2) if pe else None
        out["valuation_signal"] = "expensive" if pe >= 70 else ("reasonable" if pe <= 35 else "neutral")
    if pb:
        out["pb"] = pb
    return {key: value for key, value in out.items() if value not in (None, "")}


def _governance_from_screener(screener: Mapping[str, Any]) -> dict[str, Any]:
    shareholding = dict(screener.get("shareholding") or {})
    pledge = _first_number(shareholding, ("Pledged", "Promoter Pledge", "pledged"))
    return {
        "promoter_pledge_pct": pledge or 0.0,
        "forensic_risk": "unknown",
        "insider_signal": "neutral",
    }


def _technical_from_snapshot(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "stage": snapshot.get("stage"),
        "relative_strength": snapshot.get("relative_strength"),
        "rsi": snapshot.get("rsi"),
        "technical_score": snapshot.get("technical_score"),
        "trend_signal": snapshot.get("trend_signal"),
        "trading_signal": snapshot.get("trading_signal"),
    }


def _latest_results_from_snapshot(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "status": "snapshot",
        "sales_growth": snapshot.get("sales_growth"),
        "earnings_quality": snapshot.get("earnings_quality"),
    }


def _first_number(mapping: Mapping[str, Any], keys: tuple[str, ...]) -> float | None:
    lowered = {str(key).strip().lower(): value for key, value in mapping.items()}
    for key in keys:
        value = lowered.get(key.lower())
        parsed = _parse_number(value)
        if parsed is not None:
            return parsed
    return None


def _last_series_number(mapping: Mapping[str, Any], keys: tuple[str, ...]) -> float:
    lowered = {str(key).strip().lower(): value for key, value in mapping.items()}
    for key in keys:
        values = lowered.get(key.lower())
        if isinstance(values, list):
            for item in reversed(values):
                parsed = _parse_number(item)
                if parsed is not None:
                    return parsed
        parsed = _parse_number(values)
        if parsed is not None:
            return parsed
    return 0.0


def _parse_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return _num(value)
    text = str(value).replace(",", "").replace("%", "").strip()
    if not text or text in {"-", "—", "None", "nan"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None
```

- [ ] **Step 4: Run evidence tests**

Run:

```bash
./.venv/bin/python -m pytest -q tests/test_value_checklist.py
```

Expected:

```text
10 passed
```

- [ ] **Step 5: Commit Task 2**

Run:

```bash
git add terminal/value_checklist.py tests/test_value_checklist.py
git commit -m "feat: collect NSE value checklist evidence"
```

## Task 3: Add Report Rendering And Output Writing

**Files:**
- Create: `tests/test_value_checklist_report.py`
- Modify: `terminal/value_checklist.py`

- [ ] **Step 1: Write failing report tests**

Create `tests/test_value_checklist_report.py` with:

```python
from pathlib import Path

from terminal.value_checklist import (
    ValueChecklistEvidence,
    build_checklist_result,
    build_value_checklist_markdown,
    render_value_checklist_html,
    write_value_checklist_report,
)


def _result(symbol: str):
    evidence = ValueChecklistEvidence(
        symbol=symbol,
        company_name=f"{symbol} Ltd",
        sector="IT",
        fundamentals={
            "roe": 24.0,
            "roce": 31.0,
            "opm_pct": 26.0,
            "free_cash_flow_positive": True,
            "debt_to_equity": 0.05,
            "enhanced_fund_score": 82.0,
        },
        valuation={"pe": 24.0, "pb": 5.5, "earnings_yield_pct": 4.2, "valuation_signal": "reasonable"},
        governance={"promoter_pledge_pct": 0.0, "forensic_risk": "low", "insider_signal": "neutral"},
        technical={
            "stage": "STAGE_2",
            "relative_strength": 1.18,
            "rsi": 61.0,
            "technical_score": 78.0,
            "trend_signal": "BULLISH",
            "trading_signal": "BUY",
        },
        latest_results={"status": "ok"},
        source_trail=({"name": "scores.stage_snapshots", "status": "ok"},),
        missing_evidence=(),
        freshness={"stage_snapshot": "2026-06-26"},
    )
    return build_checklist_result(evidence)


def test_value_checklist_markdown_contains_comparison_sections():
    markdown = build_value_checklist_markdown([_result("TCS"), _result("INFY")])

    assert "# NSE Investment Checklist Comparison" in markdown
    assert "## Ranked Comparison" in markdown
    assert "| Rank | Symbol | Verdict | Score | Evidence | Key Strength | Key Risk |" in markdown
    assert "## TCS" in markdown
    assert "## INFY" in markdown
    assert "Mirror Test" in markdown
    assert "Research only. Not investment advice." in markdown
    assert "scores.stage_snapshots" in markdown


def test_value_checklist_html_renders_tables_without_raw_markdown_separator():
    html = render_value_checklist_html(build_value_checklist_markdown([_result("TCS"), _result("INFY")]))

    assert "<table" in html
    assert "NSE Investment Checklist Comparison" in html
    assert "| ---" not in html


def test_write_value_checklist_report_writes_timestamped_and_latest_outputs(tmp_path):
    report = write_value_checklist_report([_result("TCS"), _result("INFY")], project_root=tmp_path)

    assert Path(report.markdown_path).exists()
    assert Path(report.html_path).exists()
    assert Path(report.summary_csv_path).exists()
    assert Path(report.latest_markdown_path).exists()
    assert Path(report.latest_html_path).exists()
    assert Path(report.latest_summary_csv_path).exists()
    assert Path(report.latest_summary_csv_path).read_text(encoding="utf-8").startswith("rank,symbol,company_name")
```

- [ ] **Step 2: Run report tests to verify failures**

Run:

```bash
./.venv/bin/python -m pytest -q tests/test_value_checklist_report.py
```

Expected:

```text
ImportError: cannot import name 'build_value_checklist_markdown'
```

- [ ] **Step 3: Implement Markdown, HTML, and output writing**

Append to `terminal/value_checklist.py`:

```python
def build_value_checklist_markdown(results: Iterable[ValueChecklistResult]) -> str:
    ranked = compare_checklist_results(results)
    generated = _dt.datetime.now().strftime("%Y-%m-%d %H:%M IST")
    lines: list[str] = [
        "# NSE Investment Checklist Comparison",
        "",
        f"Generated: {generated}",
        "",
        "Research only. Not investment advice.",
        "",
        "## Ranked Comparison",
        "",
        "| Rank | Symbol | Verdict | Score | Evidence | Key Strength | Key Risk |",
        "| ---: | --- | --- | ---: | --- | --- | --- |",
    ]
    for idx, result in enumerate(ranked, start=1):
        lines.append(
            "| {rank} | {symbol} | {verdict} | {score:.1f} | {quality} | {strength} | {risk} |".format(
                rank=idx,
                symbol=_md(result.symbol),
                verdict=result.verdict,
                score=result.total_score,
                quality=result.evidence_quality,
                strength=_md(result.top_strengths[0] if result.top_strengths else "-"),
                risk=_md(result.top_risks[0] if result.top_risks else "-"),
            )
        )
    lines.extend(["", "## Comparison Readout", ""])
    if ranked:
        leader = ranked[0]
        lines.append(
            f"- **Top ranked:** {leader.symbol} with `{leader.verdict}` and score {leader.total_score:.1f}."
        )
        lines.append(
            f"- Ranking sorts by verdict, score, evidence quality, governance safety, valuation reasonableness, and technical confirmation."
        )
    lines.append("")
    for result in ranked:
        lines.extend(_result_markdown(result))
    lines.extend(
        [
            "## Source Trail",
            "",
        ]
    )
    for result in ranked:
        if not result.source_trail:
            lines.append(f"- **{result.symbol}:** no source trail recorded.")
            continue
        for source in result.source_trail:
            name = source.get("name", "source")
            status = source.get("status", "unknown")
            date = source.get("date") or source.get("age_hours") or ""
            suffix = f" ({date})" if date != "" else ""
            lines.append(f"- **{result.symbol}:** `{name}` -> {status}{suffix}")
    lines.extend(
        [
            "",
            "## Limitations",
            "",
            "- Scores are deterministic research labels from available Agent Adda evidence.",
            "- Missing evidence blocks unsupported conclusions instead of being inferred.",
            "- Verdicts are not buy/sell recommendations.",
            "",
            "Research only. Not investment advice.",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def render_value_checklist_html(markdown: str) -> str:
    from terminal.reports import _md_to_html_basic

    body = _md_to_html_basic(markdown)
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>NSE Investment Checklist Comparison</title>"
        "<style>body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;margin:32px;color:#0f172a}"
        "table{border-collapse:collapse;width:100%;margin:12px 0}th,td{border:1px solid #cbd5e1;padding:8px;text-align:left}"
        "th{background:#f1f5f9}.sig-buy{color:#047857;font-weight:700}.sig-avoid,.sig-sell{color:#b91c1c;font-weight:700}"
        ".sig-warn,.sig-hold{color:#b45309;font-weight:700}code{background:#f1f5f9;padding:1px 4px;border-radius:4px}</style>"
        "</head><body>"
        f"{body}"
        "</body></html>"
    )


def write_value_checklist_report(
    results: Iterable[ValueChecklistResult],
    *,
    project_root: Path | str | None = None,
) -> ValueChecklistReport:
    root = Path(project_root) if project_root is not None else ROOT
    report_dir = root / "reports" / "value_checklists"
    latest_dir = root / "reports" / "latest"
    report_dir.mkdir(parents=True, exist_ok=True)
    latest_dir.mkdir(parents=True, exist_ok=True)
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    ranked = compare_checklist_results(results)
    markdown = build_value_checklist_markdown(ranked)
    html = render_value_checklist_html(markdown)
    md_path = report_dir / f"investment_checklist_{stamp}.md"
    html_path = report_dir / f"investment_checklist_{stamp}.html"
    csv_path = report_dir / f"investment_checklist_summary_{stamp}.csv"
    latest_md = latest_dir / "investment_checklist.md"
    latest_html = latest_dir / "investment_checklist.html"
    latest_csv = latest_dir / "investment_checklist_summary.csv"
    rows = _summary_rows(ranked)
    md_path.write_text(markdown, encoding="utf-8")
    html_path.write_text(html, encoding="utf-8")
    _write_summary_csv(csv_path, rows)
    shutil.copy2(md_path, latest_md)
    shutil.copy2(html_path, latest_html)
    shutil.copy2(csv_path, latest_csv)
    return ValueChecklistReport(
        markdown=markdown,
        html=html,
        summary_rows=tuple(rows),
        markdown_path=str(md_path),
        html_path=str(html_path),
        summary_csv_path=str(csv_path),
        latest_markdown_path=str(latest_md),
        latest_html_path=str(latest_html),
        latest_summary_csv_path=str(latest_csv),
    )


def _result_markdown(result: ValueChecklistResult) -> list[str]:
    lines = [
        f"## {result.symbol}",
        "",
        f"**Company:** {result.company_name or result.symbol}",
        f"**Verdict:** `{result.verdict}`",
        f"**Score:** {result.total_score:.1f}",
        f"**Evidence quality:** {result.evidence_quality}",
        "",
        "### Checklist Scores",
        "",
        "| Dimension | Raw | Weighted | Reasons |",
        "| --- | ---: | ---: | --- |",
    ]
    if result.dimension_scores:
        for score in result.dimension_scores:
            lines.append(
                f"| {_md(score.name)} | {score.raw_score:.1f} | {score.weighted_score:.1f} | {_md('; '.join(score.reasons))} |"
            )
    else:
        lines.append("| No score | 0.0 | 0.0 | Required evidence missing |")
    lines.extend(
        [
            "",
            "### Strengths",
            "",
            *[f"- {_md(item)}" for item in result.top_strengths],
            "",
            "### Risks And Caps",
            "",
            *[f"- {_md(item)}" for item in result.top_risks],
            "",
            "### Mirror Test",
            "",
        ]
    )
    lines.extend(f"- {_md(item)}" for item in result.mirror_test)
    lines.append(f"- Mirror test: {'PASS' if result.mirror_test_passed else 'FAIL'}")
    if result.missing_evidence:
        lines.extend(["", "### Missing Evidence", ""])
        lines.extend(f"- `{item}`" for item in result.missing_evidence)
    lines.append("")
    return lines


def _summary_rows(results: list[ValueChecklistResult]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for idx, result in enumerate(results, start=1):
        rows.append(
            {
                "rank": idx,
                "symbol": result.symbol,
                "company_name": result.company_name,
                "verdict": result.verdict,
                "total_score": result.total_score,
                "evidence_quality": result.evidence_quality,
                "top_strength": result.top_strengths[0] if result.top_strengths else "",
                "top_risk": result.top_risks[0] if result.top_risks else "",
                "missing_evidence": "; ".join(result.missing_evidence),
                "mirror_test_passed": result.mirror_test_passed,
            }
        )
    return rows


def _write_summary_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "rank",
        "symbol",
        "company_name",
        "verdict",
        "total_score",
        "evidence_quality",
        "top_strength",
        "top_risk",
        "missing_evidence",
        "mirror_test_passed",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _md(value: Any) -> str:
    text = str(value or "").replace("\n", " ").strip()
    return text.replace("|", "\\|")
```

- [ ] **Step 4: Run report tests**

Run:

```bash
./.venv/bin/python -m pytest -q tests/test_value_checklist_report.py
```

Expected:

```text
3 passed
```

- [ ] **Step 5: Run core tests again**

Run:

```bash
./.venv/bin/python -m pytest -q tests/test_value_checklist.py tests/test_value_checklist_report.py
```

Expected:

```text
13 passed
```

- [ ] **Step 6: Commit Task 3**

Run:

```bash
git add terminal/value_checklist.py tests/test_value_checklist_report.py
git commit -m "feat: render NSE investment checklist reports"
```

## Task 4: Add Command Handler And Terminal Wiring

**Files:**
- Create: `tests/test_terminal_investment_checklist.py`
- Modify: `terminal/value_checklist.py`
- Modify: `nse_agent.py`
- Modify: `terminal/help.py`
- Modify: `tests/test_command_dispatch.py`

- [ ] **Step 1: Write failing command tests**

Create `tests/test_terminal_investment_checklist.py` with:

```python
from unittest.mock import patch

import nse_agent


def test_handle_investment_checklist_command_writes_report(monkeypatch, tmp_path):
    from terminal.value_checklist import (
        ValueChecklistEvidence,
        build_checklist_result,
        handle_investment_checklist_command,
    )

    evidence = [
        ValueChecklistEvidence(
            symbol="TCS",
            company_name="TCS Ltd",
            sector="IT",
            fundamentals={
                "roe": 24.0,
                "roce": 31.0,
                "opm_pct": 26.0,
                "free_cash_flow_positive": True,
                "debt_to_equity": 0.05,
                "enhanced_fund_score": 82.0,
            },
            valuation={"pe": 24.0, "pb": 5.5, "earnings_yield_pct": 4.2, "valuation_signal": "reasonable"},
            governance={"promoter_pledge_pct": 0.0, "forensic_risk": "low", "insider_signal": "neutral"},
            technical={
                "stage": "STAGE_2",
                "relative_strength": 1.18,
                "rsi": 61.0,
                "technical_score": 78.0,
                "trend_signal": "BULLISH",
                "trading_signal": "BUY",
            },
            latest_results={"status": "ok"},
            source_trail=({"name": "scores.stage_snapshots", "status": "ok"},),
            missing_evidence=(),
            freshness={"stage_snapshot": "2026-06-26"},
        )
    ]

    monkeypatch.setattr("terminal.value_checklist.collect_value_checklist_evidence", lambda symbols: evidence)

    output = handle_investment_checklist_command("/investment-checklist TCS", project_root=tmp_path)

    assert "NSE Investment Checklist Comparison" in output
    assert "TCS" in output
    assert "Markdown:" in output
    assert "HTML:" in output
    assert (tmp_path / "reports" / "latest" / "investment_checklist.md").exists()


def test_investment_checklist_registry_handler_is_registered(monkeypatch):
    registry = nse_agent._build_command_registry()

    assert "investment-checklist" in registry.handler_names

    with patch(
        "terminal.value_checklist.handle_investment_checklist_command",
        return_value="# NSE Investment Checklist Comparison\n\nMarkdown: x\nHTML: y",
    ) as handle, patch("nse_agent.console.print") as printed:
        handled = registry.dispatch("/investment-checklist TCS INFY", agent=None, show_trace=False, mode="single_query")

    assert handled is True
    handle.assert_called_once_with("/investment-checklist TCS INFY")
    assert printed.called


def test_investment_checklist_is_visible_in_slash_commands_and_help():
    commands = {command for command, _description in nse_agent._SLASH_COMMANDS}

    assert "/investment-checklist" in commands
    assert "/investment-checklist TCS INFY HDFCBANK" in commands
    assert "/investment-checklist" in nse_agent._CMD_CATEGORIES
```

- [ ] **Step 2: Run command tests to verify failures**

Run:

```bash
./.venv/bin/python -m pytest -q tests/test_terminal_investment_checklist.py
```

Expected:

```text
ImportError: cannot import name 'handle_investment_checklist_command'
```

- [ ] **Step 3: Implement the command handler**

Append to `terminal/value_checklist.py`:

```python
def handle_investment_checklist_command(text: str, *, project_root: Path | str | None = None) -> str:
    symbols = parse_investment_checklist_symbols(text)
    if not symbols:
        return (
            "## NSE Investment Checklist Comparison\n\n"
            "Usage: `/investment-checklist TCS INFY HDFCBANK`\n\n"
            "Provide 1-10 NSE symbols. Research only. Not investment advice."
        )
    evidence = collect_value_checklist_evidence(symbols)
    results = [build_checklist_result(item) for item in evidence]
    report = write_value_checklist_report(results, project_root=project_root)
    ranked = compare_checklist_results(results)
    lines = [
        "## NSE Investment Checklist Comparison",
        "",
        f"Compared symbols: {', '.join(item.symbol for item in ranked)}",
        f"Markdown: `{report.markdown_path}`",
        f"HTML: `{report.html_path}`",
        f"Summary CSV: `{report.summary_csv_path}`",
        f"Latest Markdown: `{report.latest_markdown_path}`",
        f"Latest HTML: `{report.latest_html_path}`",
        "",
        "| Rank | Symbol | Verdict | Score |",
        "| ---: | --- | --- | ---: |",
    ]
    for idx, result in enumerate(ranked, start=1):
        lines.append(f"| {idx} | {result.symbol} | {result.verdict} | {result.total_score:.1f} |")
    lines.extend(["", "Research only. Not investment advice."])
    return "\n".join(lines)
```

- [ ] **Step 4: Wire the command registry**

In `nse_agent.py`, inside `_build_command_registry()` after the `/data-coverage` handler and before broker research, add:

```python
    # /investment-checklist
    def _h_investment_checklist(query, agent, show_trace):
        from terminal.value_checklist import handle_investment_checklist_command

        _print_user(query)
        output = handle_investment_checklist_command(query)
        _remember_generated_report(output)
        console.print(Markdown(_linkify_markdown(output)))
        return True
    registry.register(CommandHandler(
        name="investment-checklist",
        match_fn=lambda q: re.match(r"^/(?:investment-checklist|investment_checklist)(?:\s|$)", q) is not None,
        handler_fn=_h_investment_checklist,
        description="NSE multi-stock value checklist comparison",
    ))
```

- [ ] **Step 5: Add slash command entries**

In `nse_agent.py`, add these entries to `_SLASH_COMMANDS` near other research/report commands:

```python
    ("/investment-checklist", "NSE multi-stock value checklist comparison"),
    ("/investment-checklist TCS INFY HDFCBANK", "Compare NSE stocks across quality, valuation, governance, and trend evidence"),
```

In `nse_agent.py`, add this entry to `_CMD_CATEGORIES`:

```python
    "/investment-checklist": ("Research Council", "🧠"),
```

- [ ] **Step 6: Add help section entry**

In `terminal/help.py`, add this command to the Research, Reports, or Fundamentals section command list:

```python
            ("/investment-checklist TCS INFY HDFCBANK", "Compare NSE stocks using deterministic value checklist scoring"),
```

Use the existing `SECTIONS` structure. Do not create a new help renderer.

- [ ] **Step 7: Run command tests**

Run:

```bash
./.venv/bin/python -m pytest -q tests/test_terminal_investment_checklist.py
```

Expected:

```text
3 passed
```

- [ ] **Step 8: Update command dispatch inventory test**

In `tests/test_command_dispatch.py`, update `TestCommandRegistry.EXPECTED_HANDLERS` to include the new handler:

```python
    EXPECTED_HANDLERS = [
        "help", "commands", "dashboard", "intraday-alerts", "interaction", "copilot-workflows", "scan", "quality-breakouts", "strategy-council", "council",
        "backtest", "data-coverage", "investment-checklist", "broker-research", "open-last-report", "visual-scan",
        "doctor", "mtf", "strength", "skills", "email", "my-portfolio",
        "swing-playbook", "diagnose", "report-sector", "report-diagnosis",
    ]
```

- [ ] **Step 9: Run command tests again**

Run:

```bash
./.venv/bin/python -m pytest -q tests/test_terminal_investment_checklist.py
```

Expected:

```text
3 passed
```

- [ ] **Step 10: Run command dispatch regression tests**

Run:

```bash
./.venv/bin/python -m pytest -q tests/test_command_dispatch.py tests/test_terminal_investment_checklist.py
```

Expected:

```text
all selected tests pass
```

- [ ] **Step 11: Commit Task 4**

Run:

```bash
git add terminal/value_checklist.py nse_agent.py terminal/help.py tests/test_terminal_investment_checklist.py tests/test_command_dispatch.py
git commit -m "feat: wire NSE investment checklist command"
```

## Task 5: Full Verification And Smoke Run

**Files:**
- Modify only if verification exposes a specific defect in files touched by Tasks 1-4.

- [ ] **Step 1: Run the focused value-checklist suite**

Run:

```bash
./.venv/bin/python -m pytest -q tests/test_value_checklist.py tests/test_value_checklist_report.py tests/test_terminal_investment_checklist.py tests/test_command_dispatch.py
```

Expected:

```text
all selected tests pass
```

- [ ] **Step 2: Run a no-network command smoke with monkeypatch-free local providers**

Run:

```bash
./.venv/bin/python nse_agent.py --query "/investment-checklist TCS INFY HDFCBANK"
```

Expected:

```text
NSE Investment Checklist Comparison
Markdown: reports/value_checklists/investment_checklist_YYYYMMDD_HHMMSS.md
HTML: reports/value_checklists/investment_checklist_YYYYMMDD_HHMMSS.html
Research only. Not investment advice.
```

The command can mark individual symbols as `INSUFFICIENT_EVIDENCE` if local fundamentals are not cached. It must still write `reports/latest/investment_checklist.md`, `reports/latest/investment_checklist.html`, and `reports/latest/investment_checklist_summary.csv`.

- [ ] **Step 3: Inspect generated latest files**

Run:

```bash
ls -l reports/latest/investment_checklist.md reports/latest/investment_checklist.html reports/latest/investment_checklist_summary.csv
```

Expected:

```text
all three files exist and have non-zero size
```

- [ ] **Step 4: Commit any verification fixes**

If Step 1 or Step 2 required a fix, commit only the touched implementation/test files:

```bash
git add terminal/value_checklist.py nse_agent.py terminal/help.py tests/test_value_checklist.py tests/test_value_checklist_report.py tests/test_terminal_investment_checklist.py tests/test_command_dispatch.py
git commit -m "fix: stabilize NSE investment checklist workflow"
```

If no fixes were needed, do not create an empty commit.

## Final Verification Command

Run before claiming completion:

```bash
./.venv/bin/python -m pytest -q tests/test_value_checklist.py tests/test_value_checklist_report.py tests/test_terminal_investment_checklist.py tests/test_command_dispatch.py
./.venv/bin/python nse_agent.py --query "/investment-checklist TCS INFY HDFCBANK"
```

Expected result:

- The selected pytest suite passes.
- The command produces an NSE Investment Checklist Comparison summary.
- Latest Markdown, HTML, and CSV files exist under `reports/latest/`.
- The report includes the research-only disclaimer.
