"""Deterministic NSE investment checklist scoring."""

from __future__ import annotations

import math
import re
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
    missing = _normalize_missing_evidence(evidence.missing_evidence)
    fundamentals = dict(evidence.fundamentals or {})
    valuation = dict(evidence.valuation or {})
    governance = dict(evidence.governance or {})
    if not fundamentals:
        missing = _normalize_missing_evidence(missing + ("fundamentals",))
    if not _has_usable_valuation(valuation):
        missing = _normalize_missing_evidence(missing + ("valuation",))
    if not _has_usable_governance(governance):
        missing = _normalize_missing_evidence(missing + ("governance",))
    if not fundamentals:
        return _insufficient_result(
            evidence,
            missing,
            "Missing fundamentals",
        )

    scores = (
        _score_understandable_business(evidence),
        _score_business_quality(evidence),
        _score_moat(evidence),
        _score_governance(evidence),
        _score_valuation(evidence),
        _score_technical(evidence),
        _score_decision_discipline(missing),
    )
    evidence_quality = _evidence_quality(evidence, missing)
    total = round(sum(item.weighted_score for item in scores), 2)
    hard_caps = _hard_caps(evidence, missing)
    verdict = _apply_caps(_base_verdict(total, evidence_quality), hard_caps)
    strengths, risks = _strengths_and_risks(scores, hard_caps)
    mirror_test, mirror_passed = _mirror_test(evidence, missing, verdict)
    return ValueChecklistResult(
        symbol=_sym(evidence.symbol),
        company_name=str(evidence.company_name or evidence.symbol or "").strip(),
        verdict=verdict,
        total_score=total,
        evidence_quality=evidence_quality,
        dimension_scores=scores,
        hard_caps=hard_caps,
        top_strengths=strengths,
        top_risks=risks,
        mirror_test=mirror_test,
        mirror_test_passed=mirror_passed,
        source_trail=tuple(evidence.source_trail or ()),
        missing_evidence=missing,
    )


def compare_checklist_results(
    results: Iterable[ValueChecklistResult],
) -> list[ValueChecklistResult]:
    return sorted(
        list(results),
        key=lambda item: (
            VERDICT_PRIORITY.get(item.verdict, 99),
            -item.total_score,
            _quality_rank(item.evidence_quality),
            item.symbol,
        ),
    )


def _sym(value: Any) -> str:
    return re.sub(r"[^A-Z0-9&-]", "", str(value or "").upper())


def _num(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
        return out if math.isfinite(out) else default
    except Exception:
        return default


def _num_or_none(value: Any) -> float | None:
    try:
        if value is None:
            return None
        out = float(value)
        return out if math.isfinite(out) else None
    except Exception:
        return None


_EMPTY_TEXT_VALUES = {"", "n/a", "na", "none", "null", "unknown", "-"}


def _normalize_missing_evidence(items: Iterable[Any]) -> tuple[str, ...]:
    labels: list[str] = []
    seen: set[str] = set()
    for item in items or ():
        label = str(item or "").strip().lower()
        if not label or label in seen:
            continue
        seen.add(label)
        labels.append(label)
    return tuple(labels)


def _meaningful_text(value: Any) -> str:
    text = str(value or "").strip()
    return "" if text.lower() in _EMPTY_TEXT_VALUES else text


def _normalized_text(value: Any) -> str:
    return _meaningful_text(value).lower()


def _positive_num_or_none(value: Any) -> float | None:
    number = _num_or_none(value)
    return number if number is not None and number > 0 else None


def _has_usable_valuation(valuation: Mapping[str, Any] | None) -> bool:
    v = dict(valuation or {})
    if any(
        _positive_num_or_none(v.get(key)) is not None
        for key in ("pe", "pb", "earnings_yield_pct")
    ):
        return True
    return bool(_meaningful_text(v.get("valuation_signal")))


def _has_usable_governance(governance: Mapping[str, Any] | None) -> bool:
    g = dict(governance or {})
    if _num_or_none(g.get("promoter_pledge_pct")) is not None:
        return True
    return any(
        _meaningful_text(g.get(key))
        for key in ("forensic_risk", "insider_signal")
    )


def _dimension(
    name: str,
    weight: float,
    raw: float,
    reasons: list[str],
    missing: tuple[str, ...] = (),
) -> ChecklistDimensionScore:
    raw = max(0.0, min(100.0, float(raw)))
    return ChecklistDimensionScore(
        name=name,
        weight=weight,
        raw_score=round(raw, 2),
        weighted_score=round(raw * weight / 100.0, 2),
        reasons=tuple(reasons),
        missing_evidence=missing,
    )


def _score_understandable_business(
    evidence: ValueChecklistEvidence,
) -> ChecklistDimensionScore:
    sector = str(evidence.sector or "").strip()
    raw = 80.0 if sector else 45.0
    reasons = (
        [f"Sector identified as {sector}."]
        if sector
        else ["Sector/business context is missing."]
    )
    return _dimension("Understandable Business", 10, raw, reasons, () if sector else ("sector",))


def _score_business_quality(evidence: ValueChecklistEvidence) -> ChecklistDimensionScore:
    f = dict(evidence.fundamentals or {})
    raw = 35.0
    reasons: list[str] = []
    roe = _num_or_none(f.get("roe"))
    roce = _num_or_none(f.get("roce"))
    opm = _num_or_none(f.get("opm_pct"))
    debt = _num_or_none(f.get("debt_to_equity"))
    fund_score = _num_or_none(f.get("enhanced_fund_score") or f.get("fundamental_score"))
    if (roe is not None and roe >= 20) or (roce is not None and roce >= 25):
        raw += 20
        reasons.append("High return ratios.")
    if opm is not None and opm >= 18:
        raw += 12
        reasons.append("Healthy operating margin.")
    if f.get("free_cash_flow_positive") is True:
        raw += 12
        reasons.append("Positive cash conversion.")
    if debt is not None and debt <= 0.5:
        raw += 10
        reasons.append("Low leverage.")
    if fund_score is not None and fund_score >= 70:
        raw += 12
        reasons.append("Strong Agent Adda fundamental score.")
    return _dimension(
        "Business Quality",
        20,
        raw,
        reasons or ["Business quality evidence is mixed."],
    )


def _score_moat(evidence: ValueChecklistEvidence) -> ChecklistDimensionScore:
    t = dict(evidence.technical or {})
    f = dict(evidence.fundamentals or {})
    raw = 45.0
    reasons: list[str] = []
    relative_strength = _num_or_none(t.get("relative_strength"))
    fund_score = _num_or_none(f.get("enhanced_fund_score") or f.get("fundamental_score"))
    if relative_strength is not None and relative_strength >= 1.0:
        raw += 18
        reasons.append("Relative strength is above market baseline.")
    if fund_score is not None and fund_score >= 75:
        raw += 16
        reasons.append("Quality score supports competitive position.")
    if str(evidence.sector or ""):
        raw += 8
        reasons.append("Sector context is available.")
    return _dimension(
        "Moat / Competitive Position",
        15,
        raw,
        reasons or ["Moat evidence is not conclusive."],
    )


def _score_governance(evidence: ValueChecklistEvidence) -> ChecklistDimensionScore:
    g = dict(evidence.governance or {})
    if not _has_usable_governance(g):
        return _dimension(
            "Management / Governance",
            15,
            45.0,
            ["Governance evidence is missing."],
            ("governance",),
        )
    pledge = _num_or_none(g.get("promoter_pledge_pct"))
    risk = _normalized_text(g.get("forensic_risk"))
    raw = 80.0
    reasons: list[str] = []
    severe_issue = (pledge is not None and pledge >= 20) or risk in {"high", "severe"}
    if pledge is not None and pledge > 0:
        raw -= min(35.0, pledge)
        reasons.append(f"Promoter pledge detected at {pledge:.1f}%.")
    if risk in {"high", "severe"}:
        raw -= 35
        reasons.append("Forensic risk is high.")
    elif risk in {"medium", "watch"}:
        raw -= 15
        reasons.append("Forensic risk requires monitoring.")
    if not severe_issue:
        reasons.insert(0, "No severe governance issue found in collected evidence.")
    return _dimension("Management / Governance", 15, raw, reasons)


def _score_valuation(evidence: ValueChecklistEvidence) -> ChecklistDimensionScore:
    v = dict(evidence.valuation or {})
    if not _has_usable_valuation(v):
        return _dimension(
            "Valuation / Safety Margin",
            15,
            35.0,
            ["Valuation evidence is missing."],
            ("valuation",),
        )
    pe = _positive_num_or_none(v.get("pe"))
    pb = _positive_num_or_none(v.get("pb"))
    earnings_yield = _positive_num_or_none(v.get("earnings_yield_pct"))
    signal = _normalized_text(v.get("valuation_signal"))
    raw = 55.0
    reasons: list[str] = []
    if pe is not None and 0 < pe <= 30:
        raw += 18
        reasons.append("PE is not stretched for a quality screen.")
    if pb is not None and 0 < pb <= 8:
        raw += 8
        reasons.append("PB is within a tolerable range.")
    if earnings_yield is not None and earnings_yield >= 3:
        raw += 10
        reasons.append("Earnings yield offers some valuation support.")
    if signal == "expensive" or (pe is not None and pe >= 70):
        raw -= 25
        reasons.append("Valuation appears stretched.")
    return _dimension(
        "Valuation / Safety Margin",
        15,
        raw,
        reasons or ["Valuation evidence is neutral."],
    )


def _score_technical(evidence: ValueChecklistEvidence) -> ChecklistDimensionScore:
    t = dict(evidence.technical or {})
    stage = _meaningful_text(t.get("stage")).upper()
    score = _num_or_none(t.get("technical_score"))
    raw = score if score is not None else 45.0
    reasons: list[str] = []
    if stage == "STAGE_2":
        raw += 15
        reasons.append("Stage 2 technical confirmation.")
    elif stage == "STAGE_4":
        raw -= 25
        reasons.append("Stage 4 technical breakdown.")
    if _meaningful_text(t.get("trend_signal")).upper() in {"BULLISH", "STRONG_BULLISH"}:
        raw += 8
        reasons.append("Bullish trend signal.")
    if _meaningful_text(t.get("trading_signal")).upper() in {"BUY", "STRONG_BUY"}:
        raw += 7
        reasons.append("Constructive trading signal.")
    return _dimension(
        "Technical Confirmation",
        15,
        raw,
        reasons or ["Technical evidence is mixed."],
    )


def _score_decision_discipline(missing: tuple[str, ...]) -> ChecklistDimensionScore:
    raw = 80.0 - min(40.0, len(missing) * 10.0)
    reasons = (
        ["Mirror-test claims have evidence gaps."]
        if missing
        else ["Mirror-test claims can be built from collected evidence."]
    )
    return _dimension("Decision Discipline", 10, raw, reasons, missing)


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


def _hard_caps(evidence: ValueChecklistEvidence, missing: tuple[str, ...]) -> tuple[str, ...]:
    caps: list[str] = []
    g = dict(evidence.governance or {})
    f = dict(evidence.fundamentals or {})
    v = dict(evidence.valuation or {})
    t = dict(evidence.technical or {})
    governance_risk = _normalized_text(g.get("forensic_risk"))
    pledge = _num_or_none(g.get("promoter_pledge_pct"))
    if (pledge is not None and pledge >= 20) or governance_risk in {"high", "severe"}:
        caps.append("Severe governance or promoter pledge red flag caps verdict.")
    if f.get("free_cash_flow_positive") is False:
        caps.append("Weak cash conversion caps verdict at CONDITIONAL.")
    if _meaningful_text(t.get("stage")).upper() == "STAGE_4":
        caps.append("Stage 4 technical breakdown caps verdict at WATCH.")
    pe = _positive_num_or_none(v.get("pe"))
    if _normalized_text(v.get("valuation_signal")) == "expensive" or (pe is not None and pe >= 70):
        caps.append("Excessive valuation caps verdict at WATCH.")
    if "valuation" in missing:
        caps.append("Missing valuation evidence caps verdict at WATCH.")
    if "governance" in missing:
        caps.append("Missing governance evidence caps verdict at CONDITIONAL.")
    return tuple(caps)


def _apply_caps(verdict: str, hard_caps: tuple[str, ...]) -> str:
    capped = verdict
    for cap in hard_caps:
        low = cap.lower()
        if "missing governance" in low:
            capped = _worse_verdict(capped, "CONDITIONAL")
        elif "governance" in low:
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


def _strengths_and_risks(
    scores: tuple[ChecklistDimensionScore, ...],
    caps: tuple[str, ...],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    strengths: list[str] = []
    risks: list[str] = list(caps)
    for score in sorted(scores, key=lambda item: item.raw_score, reverse=True):
        if score.raw_score >= 70 and score.reasons:
            strengths.append(f"{score.name}: {score.reasons[0]}")
        if score.raw_score < 50 and score.reasons:
            risks.append(f"{score.name}: {score.reasons[0]}")
    return (
        tuple(strengths[:3] or ("No decisive strength surfaced.",)),
        tuple(risks[:3] or ("No severe risk surfaced in collected evidence.",)),
    )


def _mirror_test(
    evidence: ValueChecklistEvidence,
    missing: tuple[str, ...],
    verdict: str,
) -> tuple[tuple[str, ...], bool]:
    missing_core = tuple(
        item for item in missing if item in {"fundamentals", "valuation", "governance"}
    )
    if missing_core:
        return (
            f"Mirror test failed: {', '.join(missing_core)} evidence is missing.",
            f"Missing evidence: {', '.join(missing)}.",
        ), False
    f = dict(evidence.fundamentals or {})
    v = dict(evidence.valuation or {})
    t = dict(evidence.technical or {})
    claims = (
        f"{_sym(evidence.symbol)} business context is tied to "
        f"{evidence.sector or 'an identified NSE sector'}.",
        f"Quality evidence: ROE {_num(f.get('roe')):.1f}%, "
        f"ROCE {_num(f.get('roce')):.1f}%.",
        f"Governance evidence does not force an avoid verdict; final verdict is {verdict}.",
        _valuation_mirror_claim(v),
        f"Technical evidence: {str(t.get('stage') or 'UNKNOWN')} "
        f"with signal {str(t.get('trading_signal') or 'n/a')}.",
    )
    return claims, verdict not in {"INSUFFICIENT_EVIDENCE", "AVOID"}


def _valuation_mirror_claim(valuation: Mapping[str, Any]) -> str:
    v = dict(valuation or {})
    parts: list[str] = []
    pe = _positive_num_or_none(v.get("pe"))
    pb = _positive_num_or_none(v.get("pb"))
    earnings_yield = _positive_num_or_none(v.get("earnings_yield_pct"))
    signal = _meaningful_text(v.get("valuation_signal"))
    if pe is not None:
        parts.append(f"PE {pe:.1f}")
    if pb is not None:
        parts.append(f"PB {pb:.1f}")
    if earnings_yield is not None:
        parts.append(f"earnings yield {earnings_yield:.1f}%")
    if signal:
        parts.append(f"signal {signal}")
    return f"Valuation evidence: {', '.join(parts)}."


def _insufficient_result(
    evidence: ValueChecklistEvidence,
    missing: tuple[str, ...],
    reason: str,
) -> ValueChecklistResult:
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
