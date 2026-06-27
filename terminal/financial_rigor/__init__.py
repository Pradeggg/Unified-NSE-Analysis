"""Deterministic financial rigor and report-audit helpers for NSE research."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from random import Random
from typing import Any, Callable, Iterable, Mapping

from terminal.financials_cache import screener_payload_from_cache


_TWOPLACES = Decimal("0.01")


@dataclass(frozen=True)
class ReportDataPoint:
    id: int
    label: str
    reported_value: Decimal
    unit: str
    line_number: int
    raw_text: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "reported_value": str(self.reported_value),
            "unit": self.unit,
            "line_number": self.line_number,
            "raw_text": self.raw_text,
        }


@dataclass(frozen=True)
class ValuationSnapshot:
    symbol: str
    status: str
    metrics: Mapping[str, Decimal]
    source: str
    cache_age_hours: float | None = None
    missing_fields: tuple[str, ...] = ()
    raw_values: Mapping[str, str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "status": self.status,
            "metrics": {key: str(value) for key, value in self.metrics.items()},
            "source": self.source,
            "cache_age_hours": self.cache_age_hours,
            "missing_fields": list(self.missing_fields),
            "raw_values": dict(self.raw_values or {}),
        }


def exact_decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value
    text = str(value).strip()
    if not text or text.lower() in {"-", "n/a", "na", "none", "null", "nan"}:
        return None
    text = (
        text.replace(",", "")
        .replace("\u20b9", "")
        .replace("Rs.", "")
        .replace("Rs", "")
        .replace("INR", "")
        .replace("%", "")
        .replace("x", "")
        .replace("X", "")
        .strip()
    )
    text = re.sub(r"\b(?:cr|crore|crores|rs|inr)\b", "", text, flags=re.IGNORECASE).strip()
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _q2(value: Decimal) -> Decimal:
    return value.quantize(_TWOPLACES, rounding=ROUND_HALF_UP)


def verify_valuation_metrics(
    *,
    price: Any,
    eps: Any | None = None,
    book_value_per_share: Any | None = None,
    fcf_per_share: Any | None = None,
    dividend_per_share: Any | None = None,
) -> dict[str, Decimal]:
    p = exact_decimal(price)
    if p is None or p <= 0:
        return {}
    metrics: dict[str, Decimal] = {}

    e = exact_decimal(eps)
    if e is not None and e > 0:
        metrics["pe"] = _q2(p / e)
        metrics["earnings_yield_pct"] = _q2(e / p * Decimal("100"))

    bvps = exact_decimal(book_value_per_share)
    if bvps is not None and bvps > 0:
        metrics["pb"] = _q2(p / bvps)

    fcf = exact_decimal(fcf_per_share)
    if fcf is not None and fcf > 0:
        metrics["p_fcf"] = _q2(p / fcf)
        metrics["fcf_yield_pct"] = _q2(fcf / p * Decimal("100"))

    dividend = exact_decimal(dividend_per_share)
    if dividend is not None and dividend >= 0:
        metrics["dividend_yield_pct"] = _q2(dividend / p * Decimal("100"))

    return metrics


def extract_report_data_points(markdown_text: str) -> list[ReportDataPoint]:
    lines = str(markdown_text or "").splitlines()
    collected: list[tuple[str, Decimal, str, int, str]] = []
    seen: set[tuple[str, str, str]] = set()

    def add(label: str, value: Decimal | None, unit: str, line_number: int, raw: str) -> None:
        clean_label = re.sub(r"[*_`]+", "", label or "").strip()
        if not clean_label or value is None:
            return
        if re.fullmatch(r"[-:\s|]+", clean_label):
            return
        normalized_unit = _normalize_unit(unit)
        key = (clean_label, str(value), normalized_unit)
        if key in seen:
            return
        seen.add(key)
        collected.append((clean_label, value, normalized_unit, line_number, raw.strip()[:160]))

    for line_number, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("```") or stripped.startswith("#"):
            continue
        if _is_table_separator(stripped):
            continue
        if "|" in stripped:
            continue
        match = re.match(r"^\s*(?P<label>[A-Za-z][A-Za-z0-9 /\-&().]{1,50})\s*:\s*(?P<value>.+?)\s*$", stripped)
        if match:
            value, unit = _parse_value_unit(match.group("value"))
            add(match.group("label"), value, unit, line_number, stripped)

    for row_label, col_header, value, unit, line_number, raw in _table_values(lines):
        label = row_label if not col_header or col_header == row_label else f"{row_label} - {col_header}"
        add(label, value, unit, line_number, raw)

    return [
        ReportDataPoint(idx, label, value, unit, line_number, raw)
        for idx, (label, value, unit, line_number, raw) in enumerate(collected, start=1)
    ]


def sample_report_data_points(
    points: Iterable[ReportDataPoint],
    *,
    ratio: float = 0.15,
    seed: int | None = None,
) -> list[ReportDataPoint]:
    items = list(points)
    if not items:
        return []
    bounded_ratio = min(max(float(ratio), 0.0), 1.0)
    sample_count = max(1, math.ceil(len(items) * bounded_ratio))
    sample_count = min(sample_count, len(items))
    sampled = Random(seed).sample(items, sample_count)
    return sorted(sampled, key=lambda point: point.line_number)


def render_report_audit_json(path: str | Path, *, ratio: float = 0.15, seed: int | None = None) -> str:
    report_path = Path(path).expanduser()
    markdown = report_path.read_text(encoding="utf-8")
    points = extract_report_data_points(markdown)
    sample = sample_report_data_points(points, ratio=ratio, seed=seed)
    return json.dumps(
        {
            "report_path": str(report_path),
            "total_points": len(points),
            "sample_count": len(sample),
            "ratio": ratio,
            "seed": seed,
            "sample": [point.to_dict() for point in sample],
        },
        indent=2,
        sort_keys=True,
    )


def render_report_audit_markdown(path: str | Path, *, ratio: float = 0.15, seed: int | None = None) -> str:
    payload = json.loads(render_report_audit_json(path, ratio=ratio, seed=seed))
    lines = [
        "# NSE Report Data Audit",
        "",
        f"Report: `{payload['report_path']}`",
        f"Total data points: {payload['total_points']}",
        f"Sample count: {payload['sample_count']}",
        "",
        "| ID | Line | Label | Reported Value | Unit |",
        "| ---: | ---: | --- | ---: | --- |",
    ]
    for item in payload["sample"]:
        lines.append(
            "| {id} | {line} | {label} | {value} | {unit} |".format(
                id=item["id"],
                line=item["line_number"],
                label=_md(item["label"]),
                value=item["reported_value"],
                unit=_md(item["unit"] or "-"),
            )
        )
    lines.extend(
        [
            "",
            "Use this as a deterministic claim-audit checklist: verify sampled numbers against source filings or cached NSE/Screener evidence before publishing.",
            "",
            "Research only. Not investment advice.",
        ]
    )
    return "\n".join(lines)


def build_valuation_snapshot(
    symbol: str,
    *,
    cache_loader: Callable[..., Mapping[str, Any] | None] | None = None,
) -> ValuationSnapshot:
    target = str(symbol or "").strip().upper()
    loader = cache_loader or screener_payload_from_cache
    try:
        payload = loader(target, max_age_hours=None)
    except TypeError:
        payload = loader(target)
    except Exception as exc:
        return ValuationSnapshot(target, "error", {}, f"ERROR: {exc}")
    if not payload:
        return ValuationSnapshot(target, "missing", {}, "screener_cache", missing_fields=("screener_cache",))

    ratios = dict(payload.get("ratios") or {})
    price = _first_decimal(ratios, ("Current Price", "Price", "CMP"))
    eps = _first_decimal(ratios, ("EPS", "EPS in Rs", "TTM EPS"))
    book_value = _first_decimal(ratios, ("Book Value", "Book value", "BVPS"))
    fcf_per_share = _first_decimal(ratios, ("FCF Per Share", "Free Cash Flow Per Share"))
    dividend = _first_decimal(ratios, ("Dividend", "Dividend Per Share"))
    metrics = verify_valuation_metrics(
        price=price,
        eps=eps,
        book_value_per_share=book_value,
        fcf_per_share=fcf_per_share,
        dividend_per_share=dividend,
    )

    pe = _first_decimal(ratios, ("Stock P/E", "P/E", "PE"))
    if pe is not None and pe > 0:
        metrics["pe"] = _q2(pe)
        metrics["earnings_yield_pct"] = _q2(Decimal("100") / pe)

    pb = _first_decimal(ratios, ("Price to book value", "Price to Book", "PB"))
    if pb is not None and pb > 0:
        metrics["pb"] = _q2(pb)

    dividend_yield = _first_decimal(ratios, ("Dividend Yield", "Div Yield"))
    if dividend_yield is not None and dividend_yield >= 0:
        metrics["dividend_yield_pct"] = _q2(dividend_yield)

    market_cap = _first_decimal(ratios, ("Market Cap", "Market capitalization"))
    if market_cap is not None and market_cap > 0:
        metrics["market_cap_cr"] = _q2(market_cap)

    missing = []
    if price is None:
        missing.append("price")
    if "pe" not in metrics:
        missing.append("pe")
    if "pb" not in metrics:
        missing.append("pb")

    return ValuationSnapshot(
        target,
        "ok" if metrics else "missing",
        metrics,
        "screener_cache",
        cache_age_hours=payload.get("_cache_age_hours"),
        missing_fields=tuple(missing),
        raw_values={str(key): str(value) for key, value in ratios.items()},
    )


def build_valuation_snapshots(symbols: Iterable[str]) -> list[ValuationSnapshot]:
    return [build_valuation_snapshot(symbol) for symbol in symbols]


def render_financial_rigor_markdown(snapshot: ValuationSnapshot) -> str:
    lines = [
        f"# NSE Financial Rigor - {snapshot.symbol}",
        "",
        f"Status: `{snapshot.status}`",
        f"Source: `{snapshot.source}`",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
    ]
    for key, label in _METRIC_LABELS:
        value = snapshot.metrics.get(key)
        if value is not None:
            lines.append(f"| {label} | {value} |")
    if snapshot.missing_fields:
        lines.extend(["", "Missing fields: " + ", ".join(snapshot.missing_fields)])
    lines.extend(["", "Research only. Not investment advice."])
    return "\n".join(lines)


def render_valuation_check_markdown(snapshots: Iterable[ValuationSnapshot]) -> str:
    lines = [
        "# NSE Valuation Check",
        "",
        "| Symbol | Status | PE | PB | Earnings Yield % | Dividend Yield % | Source |",
        "| --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for snapshot in snapshots:
        lines.append(
            "| {symbol} | {status} | {pe} | {pb} | {ey} | {dy} | {source} |".format(
                symbol=snapshot.symbol,
                status=snapshot.status,
                pe=_metric(snapshot, "pe"),
                pb=_metric(snapshot, "pb"),
                ey=_metric(snapshot, "earnings_yield_pct"),
                dy=_metric(snapshot, "dividend_yield_pct"),
                source=snapshot.source,
            )
        )
    lines.extend(["", "Research only. Not investment advice."])
    return "\n".join(lines)


def _first_decimal(mapping: Mapping[str, Any], keys: tuple[str, ...]) -> Decimal | None:
    lowered = {str(key).strip().lower(): value for key, value in mapping.items()}
    for key in keys:
        value = lowered.get(key.strip().lower())
        parsed = exact_decimal(value)
        if parsed is not None:
            return parsed
    return None


def _parse_value_unit(text: str) -> tuple[Decimal | None, str]:
    cleaned = str(text or "").strip()
    match = re.search(
        r"(?:\u20b9|rs\.?|inr)?\s*(?P<num>[-+]?\d[\d,]*(?:\.\d+)?)\s*(?P<unit>%|x|X|cr|crore|crores)?",
        cleaned,
        flags=re.IGNORECASE,
    )
    if not match:
        return None, ""
    return exact_decimal(match.group("num")), match.group("unit") or ""


def _normalize_unit(unit: str) -> str:
    text = str(unit or "").strip().lower()
    if text in {"crore", "crores"}:
        return "cr"
    if text == "x":
        return "x"
    if text == "%":
        return "%"
    return text


def _table_values(lines: list[str]) -> list[tuple[str, str, Decimal, str, int, str]]:
    out: list[tuple[str, str, Decimal, str, int, str]] = []
    idx = 0
    while idx < len(lines):
        line = lines[idx].strip()
        if "|" not in line or idx + 1 >= len(lines) or not _is_table_separator(lines[idx + 1].strip()):
            idx += 1
            continue
        headers = _cells(line)
        idx += 2
        while idx < len(lines):
            row = lines[idx].strip()
            if "|" not in row or _is_table_separator(row):
                break
            cells = _cells(row)
            if len(cells) >= 2:
                row_label = re.sub(r"[*_`]+", "", cells[0]).strip()
                for col_idx, cell in enumerate(cells[1:], start=1):
                    value, unit = _parse_value_unit(cell)
                    if value is None:
                        continue
                    col_header = headers[col_idx] if col_idx < len(headers) else f"Column {col_idx}"
                    out.append((row_label, col_header, value, unit, idx + 1, row))
            idx += 1
    return out


def _cells(line: str) -> list[str]:
    cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
    return [re.sub(r"[*_`]+", "", cell).strip() for cell in cells]


def _is_table_separator(line: str) -> bool:
    return bool(re.fullmatch(r"\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?", line or ""))


def _metric(snapshot: ValuationSnapshot, key: str) -> str:
    value = snapshot.metrics.get(key)
    return str(value) if value is not None else "-"


def _md(text: Any) -> str:
    return str(text).replace("|", "\\|")


_METRIC_LABELS = (
    ("pe", "PE"),
    ("pb", "PB"),
    ("earnings_yield_pct", "Earnings Yield %"),
    ("fcf_yield_pct", "FCF Yield %"),
    ("dividend_yield_pct", "Dividend Yield %"),
    ("market_cap_cr", "Market Cap Cr"),
)


__all__ = [
    "ReportDataPoint",
    "ValuationSnapshot",
    "build_valuation_snapshot",
    "build_valuation_snapshots",
    "exact_decimal",
    "extract_report_data_points",
    "render_financial_rigor_markdown",
    "render_report_audit_json",
    "render_report_audit_markdown",
    "render_valuation_check_markdown",
    "sample_report_data_points",
    "screener_payload_from_cache",
    "verify_valuation_metrics",
]
