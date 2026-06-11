from __future__ import annotations

import re
from typing import Any

from .schema_catalog import SchemaCatalog


_SQL_KEYWORDS = {
    "and",
    "as",
    "asc",
    "avg",
    "between",
    "by",
    "case",
    "coalesce",
    "count",
    "current_date",
    "desc",
    "distinct",
    "else",
    "end",
    "false",
    "first_value",
    "from",
    "group",
    "having",
    "in",
    "interval",
    "is",
    "join",
    "left",
    "like",
    "limit",
    "lower",
    "max",
    "min",
    "not",
    "null",
    "on",
    "or",
    "order",
    "outer",
    "over",
    "partition",
    "percentile_cont",
    "round",
    "select",
    "sum",
    "then",
    "true",
    "when",
    "where",
    "with",
    "within",
}


def normalize_evidence_required(evidence_required: Any) -> dict[str, Any]:
    if not isinstance(evidence_required, dict):
        return {"tables": []}
    normalized = dict(evidence_required)
    tables = (
        normalized.get("tables")
        or normalized.get("required_tables")
        or normalized.get("primary_tables")
        or []
    )
    normalized["tables"] = list(tables) if isinstance(tables, (list, tuple)) else []
    normalized.pop("required_tables", None)
    normalized.pop("primary_tables", None)
    return normalized


def _walk_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        strings: list[str] = []
        for item in value.values():
            strings.extend(_walk_strings(item))
        return strings
    if isinstance(value, list):
        strings = []
        for item in value:
            strings.extend(_walk_strings(item))
        return strings
    return []


def _sql_templates(card: dict[str, Any]) -> list[str]:
    return [
        text
        for text in _walk_strings(card.get("sql_templates", {}))
        if text.strip().lower().startswith(("select ", "with "))
    ]


def _strip_parameters(sql: str) -> str:
    no_jinja = re.sub(r"\{\{[^}]+\}\}", " ", sql)
    no_pyformat = re.sub(r"%\([a-z_][a-z0-9_]*\)s|%s", " ", no_jinja, flags=re.I)
    no_params = re.sub(r":[a-z_][a-z0-9_]*", " ", no_pyformat, flags=re.I)
    return re.sub(r"'(?:''|[^'])*'", " ", no_params)


def _referenced_tables(sql: str, catalog: SchemaCatalog) -> set[str]:
    refs = set(
        re.findall(
            r"\b(?:from|join)\s+([a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*)\b",
            sql,
            flags=re.I,
        )
    )
    return {ref.lower() for ref in refs}


def _unqualified_from_names(sql: str) -> set[str]:
    return {
        ref.lower()
        for ref in re.findall(
            r"\b(?:from|join)\s+([a-z_][a-z0-9_]*)(?!\.)\b",
            sql,
            flags=re.I,
        )
    }


def _alias_map(sql: str, catalog: SchemaCatalog) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for match in re.finditer(
        r"\b(?:from|join)\s+([a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*)(?:\s+(?:as\s+)?([a-z_][a-z0-9_]*))?",
        sql,
        flags=re.I,
    ):
        table = match.group(1).lower()
        alias = (match.group(2) or "").lower()
        if catalog.has_table(table):
            aliases[table] = table
            if alias and alias not in _SQL_KEYWORDS:
                aliases[alias] = table
    return aliases


def _candidate_unqualified_columns(sql: str, table_names: set[str], aliases: set[str] | None = None) -> set[str]:
    columns: set[str] = set()
    alias_names = aliases or set()
    for pattern in (
        r"\bselect\s+(.*?)\s+\bfrom\b",
        r"\bwhere\s+(.*?)(?:\border\s+by\b|\bgroup\s+by\b|\blimit\b|$)",
    ):
        for clause in re.findall(pattern, sql, flags=re.I | re.S):
            for token in re.findall(r"\b[a-z_][a-z0-9_]*\b", clause, flags=re.I):
                lowered = token.lower()
                if lowered not in _SQL_KEYWORDS and lowered not in table_names and lowered not in alias_names:
                    columns.add(lowered)
    return columns


def _is_simple_single_table_sql(sql: str) -> bool:
    lowered = sql.strip().lower()
    if lowered.startswith("with "):
        return False
    return len(re.findall(r"\b(?:from|join)\s+[a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*", lowered)) == 1


def audit_skill_card(card: dict[str, Any], catalog: SchemaCatalog) -> list[str]:
    findings: list[str] = []
    skill_id = str(card.get("id") or "<missing-id>")
    evidence = normalize_evidence_required(card.get("evidence_required"))
    for table_name in evidence.get("tables", []):
        if not catalog.has_table(str(table_name)):
            findings.append(f"unknown table {table_name}")

    for raw_sql in _sql_templates(card):
        raw_lowered_sql = raw_sql.lower()
        if "date('now'" in raw_lowered_sql or 'date("now"' in raw_lowered_sql:
            findings.append("SQLite date('now', ...) syntax is not approved; use PostgreSQL CURRENT_DATE - INTERVAL syntax")
        if re.search(r"\bstage\s*=\s*2\b", raw_lowered_sql):
            findings.append("stage = 2 is not approved; use stage = 'STAGE_2'")
        if re.search(r"\bstage\s*=\s*'vcp'", raw_lowered_sql):
            findings.append("stage = 'VCP' is not approved; use scores.stage2_vcp_picks for VCP evidence")
        sql = _strip_parameters(raw_sql)
        tables = _referenced_tables(sql, catalog)
        aliases = _alias_map(sql, catalog)
        for table_name in sorted(tables):
            if not catalog.has_table(table_name):
                findings.append(f"unknown table {table_name}")

        for alias, column in re.findall(r"\b([a-z_][a-z0-9_]*)\.([a-z_][a-z0-9_]*)\b", sql, flags=re.I):
            alias_l = alias.lower()
            column_l = column.lower()
            table_name = aliases.get(alias_l)
            if table_name and not catalog.has_column(table_name, column_l):
                findings.append(f"{table_name}.{column_l} is not approved")

        known_tables = {table.rsplit(".", 1)[-1] for table in tables} | _unqualified_from_names(sql)
        if _is_simple_single_table_sql(sql) and len([table for table in tables if catalog.has_table(table)]) == 1:
            table_name = next(table for table in tables if catalog.has_table(table))
            for column in _candidate_unqualified_columns(sql, known_tables, set(aliases)):
                if not catalog.has_column(table_name, column):
                    findings.append(f"{table_name}.{column} is not approved")

    return sorted(dict.fromkeys(findings))
