"""Deterministic NSE investment checklist scoring."""

from __future__ import annotations

import csv
import datetime as _dt
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
    missing = _normalize_missing_evidence(evidence.missing_evidence)
    fundamentals = dict(evidence.fundamentals or {})
    valuation = dict(evidence.valuation or {})
    governance = dict(evidence.governance or {})
    if not _has_usable_fundamentals(fundamentals):
        missing = _normalize_missing_evidence(missing + ("fundamentals",))
    if not _has_usable_valuation(valuation):
        missing = _normalize_missing_evidence(missing + ("valuation",))
    if not _has_usable_governance(governance):
        missing = _normalize_missing_evidence(missing + ("governance",))
    if not _meaningful_text(evidence.sector):
        missing = _normalize_missing_evidence(missing + ("sector",))
    if not _has_usable_fundamentals(fundamentals):
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
        lines.append("- Ranking sorts by verdict, total score, evidence quality, and symbol.")
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
    body = body.replace('<span class="sig-avoid">PASS</span>', '<span class="sig-buy">PASS</span>')
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
    project_root: Path | str | None = None,
) -> ValueChecklistReport:
    root = Path(project_root) if project_root is not None else ROOT
    report_dir = root / "reports" / "value_checklists"
    latest_dir = root / "reports" / "latest"
    report_dir.mkdir(parents=True, exist_ok=True)
    latest_dir.mkdir(parents=True, exist_ok=True)
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
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


def parse_investment_checklist_symbols(text: str, *, limit: int = 10) -> list[str]:
    raw = re.sub(
        r"^\s*/(?:investment-checklist|investment_checklist)\b",
        "",
        text or "",
        flags=re.IGNORECASE,
    )
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


def collect_value_checklist_evidence(
    symbols: Iterable[str],
) -> list[ValueChecklistEvidence]:
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

        snapshot = get_symbol_snapshot(symbol) or {}
        snapshot_missing = snapshot.get("missing_evidence") or ()
        if snapshot.get("error"):
            missing.extend(snapshot_missing or ["stage_snapshot"])
            source_trail.append(
                {
                    "name": "scores.stage_snapshots",
                    "status": f"ERROR: {snapshot.get('error')}",
                }
            )
        else:
            missing.extend(snapshot_missing)
            source_trail.append(
                {
                    "name": "scores.stage_snapshots",
                    "status": "ok",
                    "date": snapshot.get("snapshot_date"),
                }
            )
    except Exception as exc:
        missing.append("stage_snapshot")
        source_trail.append({"name": "scores.stage_snapshots", "status": f"ERROR: {exc}"})

    try:
        from terminal.financials_cache import screener_payload_from_cache

        screener = screener_payload_from_cache(symbol, max_age_hours=None)
        if screener:
            source_trail.append(
                {
                    "name": "screener_cache",
                    "status": "ok",
                    "age_hours": screener.get("_cache_age_hours"),
                }
            )
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
    fundamentals_freshness = "missing"
    if screener:
        cache_age = screener.get("_cache_age_hours")
        fundamentals_freshness = str(cache_age) if cache_age is not None else "unknown"
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
            "fundamentals": fundamentals_freshness,
        },
    )


def _sym(value: Any) -> str:
    return re.sub(r"[^A-Z0-9&-]", "", str(value or "").upper())


def _result_markdown(result: ValueChecklistResult) -> list[str]:
    lines: list[str] = [
        f"## {result.symbol}",
        "",
        f"**Company:** {result.company_name or result.symbol}",
        "",
        f"**Verdict:** `{result.verdict}`",
        "",
        f"**Score:** {result.total_score:.1f}",
        "",
        f"**Evidence quality:** {result.evidence_quality}",
        "",
        "### Scorecard",
        "",
        "| Dimension | Weight | Raw Score | Weighted Score | Reasons | Missing Evidence |",
        "| --- | ---: | ---: | ---: | --- | --- |",
    ]
    for score in result.dimension_scores:
        reasons = "; ".join(score.reasons) if score.reasons else "-"
        missing = "; ".join(score.missing_evidence) if score.missing_evidence else "-"
        lines.append(
            "| {dimension} | {weight:.0f} | {raw:.1f} | {weighted:.1f} | {reasons} | {missing} |".format(
                dimension=_md(score.name),
                weight=score.weight,
                raw=score.raw_score,
                weighted=score.weighted_score,
                reasons=_md(reasons),
                missing=_md(missing),
            )
        )
    lines.extend(["", "### Key Strengths", ""])
    for strength in result.top_strengths:
        lines.append(f"- {strength}")
    lines.extend(["", "### Key Risks", ""])
    for risk in result.top_risks:
        lines.append(f"- {risk}")
    if result.hard_caps:
        lines.extend(["", "### Hard Caps", ""])
        for cap in result.hard_caps:
            lines.append(f"- {cap}")
    if result.missing_evidence:
        lines.extend(["", "### Missing Evidence", ""])
        for item in result.missing_evidence:
            lines.append(f"- {item}")
    lines.extend(["", "### Mirror Test", ""])
    lines.append(f"- Result: {'PASS' if result.mirror_test_passed else 'FAIL'}")
    for claim in result.mirror_test:
        lines.append(f"- {claim}")
    lines.append("")
    return lines


def _summary_rows(results: Iterable[ValueChecklistResult]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for idx, result in enumerate(results, start=1):
        rows.append(
            {
                "rank": idx,
                "symbol": result.symbol,
                "company_name": result.company_name,
                "verdict": result.verdict,
                "total_score": f"{result.total_score:.1f}",
                "evidence_quality": result.evidence_quality,
                "top_strength": result.top_strengths[0] if result.top_strengths else "",
                "top_risk": result.top_risks[0] if result.top_risks else "",
                "mirror_test_passed": result.mirror_test_passed,
                "hard_caps": "; ".join(result.hard_caps),
                "missing_evidence": "; ".join(result.missing_evidence),
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
        "mirror_test_passed",
        "hard_caps",
        "missing_evidence",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _md(value: Any) -> str:
    text = str(value if value is not None else "")
    text = re.sub(r"\s+", " ", text).strip()
    return text.replace("\\", "\\\\").replace("|", "/")


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


def _fundamentals_from_sources(
    snapshot: Mapping[str, Any],
    screener: Mapping[str, Any],
) -> dict[str, Any]:
    ratios = dict(screener.get("ratios") or {})
    annual = dict(screener.get("annual_pl") or {})
    cash_flow = dict(screener.get("cash_flow") or {})
    out: dict[str, Any] = {}
    out["roe"] = _first_number(ratios, ("ROE", "Return on equity"))
    out["roce"] = _first_number(ratios, ("ROCE", "Return on capital employed"))
    out["debt_to_equity"] = _first_number(
        ratios,
        ("Debt to equity", "Debt / Equity"),
    )
    out["opm_pct"] = _last_series_number_or_none(annual, ("OPM %", "OPM"))
    fcf = _last_series_number_or_none(cash_flow, ("Free Cash Flow", "FCF"))
    if fcf is not None:
        out["free_cash_flow_positive"] = fcf > 0
    for key in (
        "enhanced_fund_score",
        "fundamental_score",
        "earnings_quality",
        "sales_growth",
        "financial_strength",
    ):
        parsed = _parse_number(snapshot.get(key))
        if parsed is not None:
            out[key] = parsed
    return {key: value for key, value in out.items() if value not in (None, "")}


def _valuation_from_screener(screener: Mapping[str, Any]) -> dict[str, Any]:
    ratios = dict(screener.get("ratios") or {})
    pe = _first_number(ratios, ("Stock P/E", "P/E", "PE"))
    pb = _first_number(ratios, ("Price to book value", "Price to Book", "PB"))
    out: dict[str, Any] = {}
    if pe is not None and pe > 0:
        out["pe"] = pe
        out["earnings_yield_pct"] = round(100.0 / pe, 2)
        out["valuation_signal"] = (
            "expensive" if pe >= 70 else ("reasonable" if pe <= 35 else "neutral")
        )
    if pb is not None and pb > 0:
        out["pb"] = pb
    return {key: value for key, value in out.items() if value not in (None, "")}


def _governance_from_screener(screener: Mapping[str, Any]) -> dict[str, Any]:
    shareholding = dict(screener.get("shareholding") or {})
    pledge = _first_number(shareholding, ("Pledged", "Promoter Pledge", "pledged"))
    out: dict[str, Any] = {}
    if pledge is not None and pledge >= 0:
        out["promoter_pledge_pct"] = pledge
    for key in ("forensic_risk", "insider_signal"):
        value = _meaningful_text(screener.get(key))
        if value:
            out[key] = value
    return out


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
        value = lowered.get(key.strip().lower())
        parsed = _parse_number(value)
        if parsed is not None:
            return parsed
    return None


def _last_series_number(mapping: Mapping[str, Any], keys: tuple[str, ...]) -> float:
    value = _last_series_number_or_none(mapping, keys)
    return value if value is not None else 0.0


def _last_series_number_or_none(
    mapping: Mapping[str, Any],
    keys: tuple[str, ...],
) -> float | None:
    lowered = {str(key).strip().lower(): value for key, value in mapping.items()}
    for key in keys:
        values = lowered.get(key.strip().lower())
        if isinstance(values, list):
            for item in reversed(values):
                parsed = _parse_number(item)
                if parsed is not None:
                    return parsed
            continue
        parsed = _parse_number(values)
        if parsed is not None:
            return parsed
    return None


def _parse_number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    text = str(value).replace(",", "").replace("%", "").strip()
    if not text or text.lower() in {"-", "\u2014", "none", "nan", "n/a", "na"}:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


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


def _has_usable_fundamentals(fundamentals: Mapping[str, Any] | None) -> bool:
    f = dict(fundamentals or {})
    if any(
        _num_or_none(f.get(key)) is not None
        for key in (
            "roe",
            "roce",
            "opm_pct",
            "sales_growth",
            "profit_growth",
            "enhanced_fund_score",
            "fundamental_score",
        )
    ):
        return True
    debt = _num_or_none(f.get("debt_to_equity"))
    if debt is not None and debt >= 0:
        return True
    return isinstance(f.get("free_cash_flow_positive"), bool)


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
    sector = _meaningful_text(evidence.sector)
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
    if _meaningful_text(evidence.sector):
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
        caps.append("Missing governance evidence caps verdict at WATCH.")
    if "sector" in missing:
        caps.append("Missing sector/business context caps verdict at CONDITIONAL.")
    return tuple(caps)


def _apply_caps(verdict: str, hard_caps: tuple[str, ...]) -> str:
    capped = verdict
    for cap in hard_caps:
        low = cap.lower()
        if "missing governance" in low:
            capped = _worse_verdict(capped, "WATCH")
        if "missing sector" in low or "business context" in low:
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
        item
        for item in missing
        if item in {"fundamentals", "valuation", "governance", "sector"}
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
        _quality_mirror_claim(f),
        f"Governance evidence does not force an avoid verdict; final verdict is {verdict}.",
        _valuation_mirror_claim(v),
        f"Technical evidence: {str(t.get('stage') or 'UNKNOWN')} "
        f"with signal {str(t.get('trading_signal') or 'n/a')}.",
    )
    return claims, verdict not in {"INSUFFICIENT_EVIDENCE", "AVOID"}


def _quality_mirror_claim(fundamentals: Mapping[str, Any]) -> str:
    f = dict(fundamentals or {})
    parts: list[str] = []
    roe = _num_or_none(f.get("roe"))
    roce = _num_or_none(f.get("roce"))
    opm = _num_or_none(f.get("opm_pct"))
    debt = _num_or_none(f.get("debt_to_equity"))
    sales_growth = _num_or_none(f.get("sales_growth"))
    profit_growth = _num_or_none(f.get("profit_growth"))
    fund_score = _num_or_none(f.get("enhanced_fund_score"))
    if fund_score is None:
        fund_score = _num_or_none(f.get("fundamental_score"))

    if roe is not None:
        parts.append(f"ROE {roe:.1f}%")
    if roce is not None:
        parts.append(f"ROCE {roce:.1f}%")
    if opm is not None:
        parts.append(f"OPM {opm:.1f}%")
    if debt is not None:
        parts.append(f"debt-to-equity {debt:.2f}")
    if isinstance(f.get("free_cash_flow_positive"), bool):
        fcf = "positive" if f.get("free_cash_flow_positive") else "not positive"
        parts.append(f"free cash flow {fcf}")
    if sales_growth is not None:
        parts.append(f"sales growth {sales_growth:.1f}%")
    if profit_growth is not None:
        parts.append(f"profit growth {profit_growth:.1f}%")
    if fund_score is not None:
        parts.append(f"Agent Adda fundamental score {fund_score:.1f}")
    return f"Quality evidence: {', '.join(parts)}."


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
