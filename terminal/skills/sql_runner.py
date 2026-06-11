from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from .sql_safety import validate_sql_template
from .store_repo import SkillStoreRepository


_NAMED_PARAM_RE = re.compile(r"(?<!:):([A-Za-z_][A-Za-z0-9_]*)")
DEFAULT_MAX_ROW_LIMIT = 500


@dataclass(frozen=True)
class SkillSQLRunResult:
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    as_of_date: Any | None
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "columns": list(self.columns),
            "rows": [dict(row) for row in self.rows],
            "row_count": self.row_count,
            "as_of_date": self.as_of_date,
            "warnings": list(self.warnings),
        }


def run_skill_sql_template(
    skill_id: str,
    template_name: str,
    params: dict[str, Any] | None,
    *,
    repository: Any | None = None,
    conn: Any | None = None,
    version: int | None = None,
    timeout_ms: int = 5000,
    max_row_limit: int = DEFAULT_MAX_ROW_LIMIT,
) -> SkillSQLRunResult:
    repo = repository or SkillStoreRepository(conn=conn)
    template = repo.get_sql_template(skill_id, template_name, version=version)
    if not template:
        raise ValueError(f"SQL template not found: {skill_id}/{template_name}")

    if str(template.get("safety_status") or "pending") != "passed":
        raise ValueError("SQL template is not approved")

    runtime_params = dict(params or {})
    sql_text = str(template.get("sql_text") or template.get("sql") or "")
    required_params = list(template.get("required_params") or [])
    expected_columns = list(template.get("expected_columns") or [])
    row_limit = max(1, min(int(template.get("row_limit") or max_row_limit), max_row_limit))

    safety = validate_sql_template(sql_text, required_params=required_params, params=runtime_params)
    if not safety.passed:
        raise ValueError("; ".join(safety.errors))

    db = conn or getattr(repo, "conn", None) or repo._connect()
    query_params = dict(runtime_params)
    query_params["skill_row_limit"] = row_limit
    wrapped_sql = _wrap_limited_query(_to_pyformat_sql(sql_text))

    try:
        with db.cursor() as cur:
            cur.execute("BEGIN READ ONLY")
            cur.execute("SET LOCAL statement_timeout = %s", (timeout_ms,))
            cur.execute(wrapped_sql, query_params)
            columns = [column[0] for column in (getattr(cur, "description", None) or [])]
            raw_rows = cur.fetchall()
        _commit(db)
    except Exception:
        _rollback(db)
        raise

    column_safety = validate_sql_template(sql_text, expected_columns=expected_columns, actual_columns=columns)
    if not column_safety.passed:
        raise ValueError("; ".join(column_safety.errors))

    rows = [_row_to_dict(columns, row) for row in raw_rows]
    warnings = list(safety.warnings)
    if not rows:
        warnings.append("query returned no rows")

    return SkillSQLRunResult(
        columns=columns,
        rows=rows,
        row_count=len(rows),
        as_of_date=_find_as_of_date(rows),
        warnings=warnings,
    )


def _to_pyformat_sql(sql: str) -> str:
    return _NAMED_PARAM_RE.sub(r"%(\1)s", sql.strip().rstrip(";"))


def _wrap_limited_query(sql: str) -> str:
    return f"SELECT * FROM ({sql}) AS skill_query LIMIT %(skill_row_limit)s"


def _row_to_dict(columns: list[str], row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        return {key: _json_safe_value(value) for key, value in row.items()}
    return {column: _json_safe_value(value) for column, value in zip(columns, row)}


def _json_safe_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    return value


def _find_as_of_date(rows: list[dict[str, Any]]) -> Any | None:
    for row in rows:
        for key in ("as_of_date", "snapshot_date", "trade_date", "price_date", "date"):
            value = row.get(key)
            if value is not None:
                return value
    return None


def _commit(conn: Any) -> None:
    commit = getattr(conn, "commit", None)
    if callable(commit):
        commit()


def _rollback(conn: Any) -> None:
    rollback = getattr(conn, "rollback", None)
    if callable(rollback):
        rollback()
