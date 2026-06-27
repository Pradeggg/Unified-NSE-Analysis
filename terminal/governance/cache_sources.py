from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from terminal.governance.models import GovernanceMissingEvidence, GovernanceRawSources, GovernanceSource
from terminal.governance.parsers import parse_date


def _normalized_symbol(symbol: str) -> str:
    return str(symbol or "").strip().upper()


def _row_symbol(row: dict[str, Any]) -> str:
    return _normalized_symbol(row.get("symbol") or row.get("SYMBOL"))


def _file_date(path: Path, prefix: str) -> Any:
    stem = path.stem
    if not stem.startswith(prefix):
        return None
    return parse_date(stem[len(prefix) :])


def _missing(symbol: str, field: str, reason: str) -> GovernanceMissingEvidence:
    return GovernanceMissingEvidence(
        scope="governance",
        subject=symbol,
        field=field,
        severity="warn",
        reason=reason,
    )


def _read_csv_rows(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return [dict(row) for row in reader]


def _read_csv_rows_with_headers(path: Path, required_headers: set[str]) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        headers = set(reader.fieldnames or [])
        missing_headers = required_headers - headers
        if missing_headers:
            raise ValueError(f"Missing required CSV headers: {', '.join(sorted(missing_headers))}")
        return [dict(row) for row in reader]


def _latest_pit_file(cache_dir: Path) -> Path | None:
    candidates = list(cache_dir.glob("pit_*.json"))
    if not candidates:
        return None
    return max(candidates, key=lambda item: (_file_date(item, "pit_") or parse_date("1900-01-01"), item.name))


def load_cached_sources(symbol: str, *, data_dir: str | Path = "data") -> GovernanceRawSources:
    target = _normalized_symbol(symbol)
    root = Path(data_dir)
    governance_cache = _load_governance_raw_sources_cache(target, root)
    if governance_cache is not None:
        return governance_cache

    cache_dir = root / "_insider_cache"
    source_trail: list[GovernanceSource] = []
    missing_evidence: list[GovernanceMissingEvidence] = []
    insider_payloads: list[dict[str, Any]] = []
    deal_rows: list[dict[str, Any]] = []
    announcement_rows: list[dict[str, Any]] = []

    if cache_dir.exists():
        pit_file = _latest_pit_file(cache_dir)
        if pit_file is None:
            missing_evidence.append(_missing(target, "pit_cache", "No PIT cache file found"))
        else:
            latest_date = _file_date(pit_file, "pit_")
            try:
                payload = json.loads(pit_file.read_text(encoding="utf-8"))
                rows = payload.get("data", []) if isinstance(payload, dict) else payload
                if not isinstance(rows, list):
                    raise ValueError("PIT cache payload is not a list or data object")
                filtered = [row for row in rows if isinstance(row, dict) and _row_symbol(row) == target]
                insider_payloads.append({"data": filtered})
                source_trail.append(
                    GovernanceSource(
                        name="cache.pit",
                        status="ok",
                        rows=len(filtered),
                        latest_date=latest_date,
                        fallback=True,
                    )
                )
            except Exception as exc:
                source_trail.append(
                    GovernanceSource(
                        name="cache.pit",
                        status="error",
                        latest_date=latest_date,
                        fallback=True,
                        error=str(exc),
                    )
                )
                missing_evidence.append(_missing(target, "pit_cache", str(exc)))

        latest_deal_date = None
        deal_files = sorted([*cache_dir.glob("bulk_*.csv"), *cache_dir.glob("block_*.csv")])
        if not deal_files:
            missing_evidence.append(_missing(target, "bulk_block_deals", "No bulk/block deal cache files found"))
            source_trail.append(
                GovernanceSource(
                    name="cache.bulk_block_deals",
                    status="missing",
                    rows=0,
                    fallback=True,
                )
            )
        deal_file_errors = []
        for deal_file in deal_files:
            prefix = "bulk_" if deal_file.name.startswith("bulk_") else "block_"
            file_date = _file_date(deal_file, prefix)
            if latest_deal_date is None or (file_date is not None and file_date > latest_deal_date):
                latest_deal_date = file_date
            try:
                rows = _read_csv_rows_with_headers(deal_file, {"SYMBOL"})
                deal_rows.extend(row for row in rows if _row_symbol(row) == target)
            except Exception as exc:
                deal_file_errors.append(deal_file.name)
                source_trail.append(
                    GovernanceSource(
                        name="cache.bulk_block_deals",
                        status="error",
                        latest_date=file_date,
                        fallback=True,
                        error=f"{deal_file.name}: {exc}",
                    )
                )
                missing_evidence.append(_missing(target, "bulk_block_deals", f"{deal_file.name}: {exc}"))
        if deal_files:
            source_trail.append(
                GovernanceSource(
                    name="cache.bulk_block_deals",
                    status="degraded" if deal_file_errors else "ok",
                    rows=len(deal_rows),
                    latest_date=latest_deal_date,
                    fallback=True,
                    metadata={"failed_files": deal_file_errors} if deal_file_errors else {},
                )
            )
    else:
        missing_evidence.append(_missing(target, "insider_cache", "No insider cache directory found"))
        missing_evidence.append(_missing(target, "pit_cache", "No PIT cache file found"))
        missing_evidence.append(_missing(target, "bulk_block_deals", "No insider cache directory found"))

    corporate_events = root / "corporate_events.csv"
    if corporate_events.exists():
        try:
            rows = _read_csv_rows_with_headers(corporate_events, {"SYMBOL"})
            announcement_rows = [_normalize_announcement_row(row) for row in rows if _row_symbol(row) == target]
            latest_announcement_date = None
            for row in announcement_rows:
                row_date = parse_date(row.get("EVENT_DATE") or row.get("date") or row.get("announcement_date"))
                if latest_announcement_date is None or (row_date is not None and row_date > latest_announcement_date):
                    latest_announcement_date = row_date
            source_trail.append(
                GovernanceSource(
                    name="cache.corporate_events",
                    status="ok",
                    rows=len(announcement_rows),
                    latest_date=latest_announcement_date,
                    fallback=True,
                )
            )
        except Exception as exc:
            source_trail.append(
                GovernanceSource(
                    name="cache.corporate_events",
                    status="error",
                    fallback=True,
                    error=str(exc),
                )
            )
            missing_evidence.append(_missing(target, "corporate_events", str(exc)))
    else:
        missing_evidence.append(_missing(target, "corporate_events", "No corporate events cache file found"))

    return GovernanceRawSources(
        symbol=target,
        insider_payloads=insider_payloads,
        deal_rows=deal_rows,
        announcement_rows=announcement_rows,
        source_trail=source_trail,
        missing_evidence=missing_evidence,
    )


def _normalize_announcement_row(row: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    subject = _first_non_blank(
        normalized.get("SUBJECT"),
        normalized.get("subject"),
        normalized.get("PURPOSE_RAW"),
        normalized.get("DETAIL"),
        normalized.get("EVENT_TYPE"),
    )
    if subject and not normalized.get("SUBJECT"):
        normalized["SUBJECT"] = subject
    return normalized


def _first_non_blank(*values: Any) -> str | None:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return None


def _load_governance_raw_sources_cache(symbol: str, root: Path) -> GovernanceRawSources | None:
    cache_file = root / "governance" / symbol / "parsed" / "raw_sources.json"
    if not cache_file.exists():
        return None
    try:
        payload = json.loads(cache_file.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict) or _normalized_symbol(payload.get("symbol")) != symbol:
        return None

    return GovernanceRawSources(
        symbol=symbol,
        shareholding_payloads=_dict_list(payload.get("shareholding_payloads")),
        insider_payloads=_dict_list(payload.get("insider_payloads")),
        deal_rows=_dict_list(payload.get("deal_rows")),
        announcement_rows=_dict_list(payload.get("announcement_rows")),
        complaint_payloads=_dict_list(payload.get("complaint_payloads")),
        screener_payload=payload.get("screener_payload") if isinstance(payload.get("screener_payload"), dict) else None,
        annual_report_text=payload.get("annual_report_text") if isinstance(payload.get("annual_report_text"), str) else None,
        source_trail=[_source_from_dict(item) for item in _dict_list(payload.get("source_trail"))],
        missing_evidence=[_missing_from_dict(item) for item in _dict_list(payload.get("missing_evidence"))],
    )


def _source_from_dict(item: dict[str, Any]) -> GovernanceSource:
    return GovernanceSource(
        name=str(item.get("name") or ""),
        status=str(item.get("status") or "unknown"),
        rows=_optional_int(item.get("rows")),
        latest_date=parse_date(item.get("latest_date")),
        fallback=bool(item.get("fallback")),
        error=str(item.get("error")) if item.get("error") is not None else None,
        metadata=item.get("metadata") if isinstance(item.get("metadata"), dict) else {},
    )


def _missing_from_dict(item: dict[str, Any]) -> GovernanceMissingEvidence:
    severity = str(item.get("severity") or "warn")
    if severity not in {"info", "warn", "block"}:
        severity = "warn"
    return GovernanceMissingEvidence(
        scope=str(item.get("scope") or "governance"),
        subject=_normalized_symbol(item.get("subject")),
        field=str(item.get("field") or ""),
        severity=severity,  # type: ignore[arg-type]
        reason=str(item.get("reason")) if item.get("reason") is not None else None,
    )


def _dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
