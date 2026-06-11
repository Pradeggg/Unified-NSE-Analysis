from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping


DEFAULT_MAX_ROWS = 1000


@dataclass(frozen=True)
class SkillEvidenceValidation:
    passed: bool
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    missing_evidence: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "errors", _string_tuple(self.errors))
        object.__setattr__(self, "warnings", _string_tuple(self.warnings))
        object.__setattr__(self, "missing_evidence", _string_tuple(self.missing_evidence))
        object.__setattr__(self, "metadata", dict(self.metadata or {}))

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "missing_evidence": list(self.missing_evidence),
            "metadata": dict(self.metadata),
        }


def validate_skill_evidence(
    execution_plan_or_steps: Any,
    *,
    evidence: Mapping[str, Any],
    output_contract: Iterable[str] | None = None,
    freshness: Mapping[str, Any] | None = None,
    max_rows: int = DEFAULT_MAX_ROWS,
    today: dt.date | None = None,
) -> SkillEvidenceValidation:
    check_date = today or dt.date.today()
    steps = _normalize_steps(execution_plan_or_steps)
    evidence_by_key = {str(key): value for key, value in dict(evidence or {}).items()}
    required_outputs = _string_tuple(output_contract)
    errors: list[str] = []
    warnings: list[str] = []
    missing_evidence: list[str] = []

    for output_key in required_outputs:
        if output_key not in evidence_by_key:
            errors.append(f"missing required output key: {output_key}")

    for step in steps:
        step_name = str(step.get("name") or step.get("target") or step.get("step_id") or "")
        if not step_name:
            errors.append("evidence step name is required")
            continue
        is_optional = _is_optional_step(step)
        result = evidence_by_key.get(step_name)
        if result is None:
            if is_optional:
                warnings.append(f"optional result set missing: {step_name}")
            else:
                errors.append(f"missing required result set: {step_name}")
                missing_evidence.append(step_name)
            continue

        normalized_result = _normalize_result(result)
        rows = normalized_result["rows"]
        row_count = normalized_result["row_count"]
        if row_count == 0:
            if is_optional:
                warnings.append(f"optional result set empty: {step_name}")
            else:
                errors.append(f"required result set empty: {step_name}")
                missing_evidence.append(step_name)

        if row_count != len(rows):
            warnings.append(f"row_count mismatch in {step_name}: declared {row_count}, actual {len(rows)}")
        if row_count > max_rows:
            warnings.append(f"row_count exceeds max_rows in {step_name}: {row_count} > {max_rows}")

        dates = _dates_in_result(normalized_result)
        for found_date in dates:
            if found_date > check_date:
                errors.append(f"future date in {step_name}: {found_date.isoformat()}")

        as_of_date = _as_of_date(normalized_result)
        if as_of_date is None:
            warnings.append(f"source freshness missing in {step_name}")
        else:
            _apply_freshness(
                step_name,
                as_of_date=as_of_date,
                today=check_date,
                freshness=freshness or {},
                errors=errors,
                warnings=warnings,
            )

        errors.extend(_filter_errors(step_name, step, rows))

    return SkillEvidenceValidation(
        passed=not errors,
        errors=tuple(sorted(dict.fromkeys(errors))),
        warnings=tuple(sorted(dict.fromkeys(warnings))),
        missing_evidence=tuple(sorted(dict.fromkeys(missing_evidence))),
        metadata={"checked_steps": len(steps), "checked_outputs": len(required_outputs)},
    )


def _normalize_steps(execution_plan_or_steps: Any) -> list[dict[str, Any]]:
    if execution_plan_or_steps is None:
        return []
    if hasattr(execution_plan_or_steps, "steps"):
        raw_steps = list(getattr(execution_plan_or_steps, "steps") or ())
    elif isinstance(execution_plan_or_steps, Iterable) and not isinstance(execution_plan_or_steps, (str, bytes, Mapping)):
        raw_steps = list(execution_plan_or_steps)
    else:
        raw_steps = [execution_plan_or_steps]
    return [_step_to_dict(step) for step in raw_steps]


def _step_to_dict(step: Any) -> dict[str, Any]:
    if hasattr(step, "to_dict"):
        return step.to_dict()
    if isinstance(step, Mapping):
        return dict(step)
    return dict(step)


def _normalize_result(result: Any) -> dict[str, Any]:
    if hasattr(result, "to_dict"):
        value = result.to_dict()
    elif isinstance(result, Mapping):
        value = dict(result)
    else:
        value = {"rows": result}

    rows = value.get("rows")
    if rows is None and "data" in value:
        rows = value.get("data")
    if rows is None:
        rows = []
    if isinstance(rows, Mapping):
        rows = [dict(rows)]
    elif not isinstance(rows, list):
        rows = list(rows) if isinstance(rows, Iterable) and not isinstance(rows, (str, bytes)) else [rows]

    normalized_rows = [dict(row) if isinstance(row, Mapping) else {"value": row} for row in rows]
    row_count = value.get("row_count")
    if row_count is None:
        row_count = len(normalized_rows)
    return {
        **value,
        "rows": normalized_rows,
        "row_count": int(row_count),
    }


def _is_optional_step(step: dict[str, Any]) -> bool:
    metadata = dict(step.get("metadata") or {})
    return bool(metadata.get("optional") or metadata.get("required") is False or step.get("optional") is True)


def _as_of_date(result: dict[str, Any]) -> dt.date | None:
    for key in ("as_of_date", "snapshot_date", "trade_date", "price_date", "date"):
        parsed = _parse_date(result.get(key))
        if parsed is not None:
            return parsed
    for row in result.get("rows") or []:
        for key in ("as_of_date", "snapshot_date", "trade_date", "price_date", "date"):
            parsed = _parse_date(row.get(key))
            if parsed is not None:
                return parsed
    return None


def _dates_in_result(result: dict[str, Any]) -> list[dt.date]:
    dates: list[dt.date] = []
    for key, value in result.items():
        if _looks_like_date_key(key):
            parsed = _parse_date(value)
            if parsed is not None:
                dates.append(parsed)
    for row in result.get("rows") or []:
        for key, value in row.items():
            if _looks_like_date_key(key):
                parsed = _parse_date(value)
                if parsed is not None:
                    dates.append(parsed)
    return dates


def _apply_freshness(
    step_name: str,
    *,
    as_of_date: dt.date,
    today: dt.date,
    freshness: Mapping[str, Any],
    errors: list[str],
    warnings: list[str],
) -> None:
    max_age_days = freshness.get("max_age_days")
    if max_age_days is None:
        max_age_days = freshness.get("max_eod_age_days")
    if max_age_days is None:
        return
    age_days = (today - as_of_date).days
    if age_days <= int(max_age_days):
        return
    message = f"stale evidence in {step_name}: {age_days} days old"
    if bool(freshness.get("stale_is_error")):
        errors.append(message)
    else:
        warnings.append(message)


def _filter_errors(step_name: str, step: dict[str, Any], rows: list[dict[str, Any]]) -> list[str]:
    metadata = dict(step.get("metadata") or {})
    required_filters = metadata.get("required_filters") or {}
    if not isinstance(required_filters, Mapping) or not required_filters or not rows:
        return []
    errors: list[str] = []
    for field_name, expected in required_filters.items():
        expected_text = str(expected)
        if any(str(row.get(field_name)) != expected_text for row in rows):
            errors.append(f"required filter not applied in {step_name}: {field_name}={expected_text}")
    return errors


def _looks_like_date_key(key: Any) -> bool:
    key_text = str(key).lower()
    return key_text.endswith("_date") or key_text in {"date", "as_of_date"}


def _parse_date(value: Any) -> dt.date | None:
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return dt.date.fromisoformat(text[:10])
    except ValueError:
        return None


def _string_tuple(values: Iterable[Any] | Any | None) -> tuple[str, ...]:
    if values in (None, "", [], {}):
        return ()
    if isinstance(values, str):
        items = [values]
    elif isinstance(values, Iterable):
        items = list(values)
    else:
        items = [values]
    return tuple(str(item).strip() for item in items if str(item).strip())
