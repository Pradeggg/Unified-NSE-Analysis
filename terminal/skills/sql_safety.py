from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable


DISALLOWED_SQL_KEYWORDS: frozenset[str] = frozenset(
    {
        "insert",
        "update",
        "delete",
        "drop",
        "create",
        "alter",
        "truncate",
        "grant",
        "copy",
        "call",
        "do",
        "lock",
    }
)

_KEYWORD_RE = re.compile(r"\b([a-z_]+)\b", re.IGNORECASE)
_NAMED_PARAM_RE = re.compile(r":([A-Za-z_][A-Za-z0-9_]*)")
_PERCENT_FORMAT_RE = re.compile(r"%(?:\([A-Za-z_][A-Za-z0-9_]*\))?[#0 +\-]?(?:\d+|\*)?(?:\.\d+)?[bcdeEfFgGnosxXrsi]")
_BRACE_FORMAT_RE = re.compile(r"\{[A-Za-z_][A-Za-z0-9_]*(?:![rsa])?(?::[^{}]+)?\}")


@dataclass(frozen=True)
class SQLSafetyResult:
    passed: bool
    errors: list[str]
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


def validate_sql_template(
    sql: str,
    *,
    required_params: Iterable[str] | None = None,
    params: dict[str, Any] | None = None,
    expected_columns: Iterable[str] | None = None,
    actual_columns: Iterable[str] | None = None,
) -> SQLSafetyResult:
    errors: list[str] = []
    warnings: list[str] = []

    raw_sql = sql or ""
    normalized = _normalize_sql(raw_sql)
    lowered = normalized.lower()

    if not normalized:
        errors.append("sql is required")
    elif not (lowered.startswith("select ") or lowered.startswith("with ")):
        errors.append("sql must start with SELECT or WITH")

    if _has_multiple_statements(raw_sql):
        errors.append("multiple SQL statements are not allowed")

    for keyword in sorted(_disallowed_keywords(lowered)):
        errors.append(f"disallowed SQL keyword: {keyword.upper()}")

    if "pg_sleep" in lowered:
        errors.append("disallowed SQL function: pg_sleep")
    if re.search(r"\bselect\b.+\binto\b", lowered):
        errors.append("disallowed SQL clause: SELECT INTO")
    if re.search(r"\bfor\s+(?:update|share|no\s+key\s+update|key\s+share)\b", lowered):
        errors.append("disallowed SQL locking clause")
    if re.search(r"\bcreate\s+(?:temporary|temp)\b", lowered):
        errors.append("disallowed SQL temporary object creation")

    if _PERCENT_FORMAT_RE.search(raw_sql):
        errors.append("unparameterized percent-format marker is not allowed")
    if _BRACE_FORMAT_RE.search(raw_sql):
        errors.append("unparameterized brace-format marker is not allowed")
    if "f'" in lowered or 'f"' in lowered:
        errors.append("f-string marker is not allowed in SQL templates")

    required = _string_set(required_params)
    supplied = set((params or {}).keys())
    referenced = set(_NAMED_PARAM_RE.findall(raw_sql))
    params_to_check = required | (referenced if params is not None else set())
    for name in sorted(params_to_check):
        if name not in supplied:
            errors.append(f"missing required parameter: {name}")

    if expected_columns is not None and actual_columns is not None:
        actual = {str(item) for item in actual_columns}
        for column in sorted(_string_set(expected_columns) - actual):
            errors.append(f"missing expected output column: {column}")

    return SQLSafetyResult(
        passed=not errors,
        errors=sorted(dict.fromkeys(errors)),
        warnings=sorted(dict.fromkeys(warnings)),
    )


def _normalize_sql(sql: str) -> str:
    return " ".join(sql.strip().split())


def _has_multiple_statements(sql: str) -> bool:
    stripped = sql.strip()
    if not stripped:
        return False
    statements = [part.strip() for part in stripped.split(";") if part.strip()]
    return len(statements) > 1


def _disallowed_keywords(lowered_sql: str) -> set[str]:
    return {match.group(1).lower() for match in _KEYWORD_RE.finditer(lowered_sql)} & DISALLOWED_SQL_KEYWORDS


def _string_set(values: Iterable[str] | None) -> set[str]:
    if values is None:
        return set()
    return {str(item) for item in values}
