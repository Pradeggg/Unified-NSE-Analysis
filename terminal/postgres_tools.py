"""PostgreSQL operational tools for Agent Adda.

These helpers are intentionally small and JSON-serialisable so they can be
used both by terminal commands and by the OpenAI tool registry.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any


DEFAULT_DSN = os.environ.get("AGENT_ADDA_PG_DSN") or os.environ.get("PG_DSN") or "dbname=nse_market user=nse_admin host=/tmp"

REQUIRED_SCHEMAS: tuple[str, ...] = (
    "market",
    "scores",
    "intraday",
    "report",
)

REQUIRED_TABLES: tuple[str, ...] = (
    "market.equity_eod",
    "scores.stage_snapshots",
    "intraday.quote_snapshots",
    "intraday.ohlcv_bars",
    "intraday.futures_snapshots",
    "intraday.scan_signals",
    "report.enhanced_runs",
)


def _connect(dsn: str | None = None):
    import psycopg2

    return psycopg2.connect(dsn or DEFAULT_DSN)


def _parse_dsn(dsn: str | None = None) -> dict[str, str]:
    raw = dsn or DEFAULT_DSN
    result: dict[str, str] = {"raw": raw}
    for part in shlex.split(raw):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        result[key] = value
    return result


def _socket_path(parsed_dsn: dict[str, str]) -> str | None:
    host = parsed_dsn.get("host", "")
    if not host.startswith("/"):
        return None
    port = parsed_dsn.get("port", "5432")
    return str(Path(host) / f".s.PGSQL.{port}")


def _pg_isready_status(dsn: str | None = None) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            ["pg_isready", "-d", dsn or DEFAULT_DSN],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except FileNotFoundError:
        return {"available": False, "status": "pg_isready_not_found"}
    except Exception as exc:
        return {"available": False, "status": "error", "error": str(exc)}
    return {
        "available": proc.returncode == 0,
        "status": "ok" if proc.returncode == 0 else "not_ready",
        "exit_code": proc.returncode,
        "stdout": (proc.stdout or "").strip(),
        "stderr": (proc.stderr or "").strip(),
    }


def _safe_count(cur, table: str) -> int | None:
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*$", table):
        return None
    try:
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        row = cur.fetchone()
        return int(row[0] or 0) if row else 0
    except Exception:
        return None


def get_data_source_manifest() -> dict[str, Any]:
    return {
        "primary_store": "PostgreSQL",
        "dsn": _parse_dsn(),
        "required_tables": list(REQUIRED_TABLES),
        "legacy_sqlite": {
            "role": "fallback/cache",
            "enabled_by_env": os.environ.get("AGENT_ADDA_ENABLE_SQLITE_FALLBACKS", "").lower() in {"1", "true", "yes"},
        },
        "fallback_policy": {
            "silent_sqlite_fallback": False,
            "missing_evidence_required": True,
            "yfinance_intraday_seed_allowed": True,
        },
    }


def get_postgres_health(dsn: str | None = None) -> dict[str, Any]:
    parsed = _parse_dsn(dsn)
    out: dict[str, Any] = {
        "tool": "get_postgres_health",
        "dsn": parsed.get("raw"),
        "host": parsed.get("host", "localhost"),
        "database": parsed.get("dbname", ""),
        "user": parsed.get("user", ""),
        "required_schemas": list(REQUIRED_SCHEMAS),
        "required_tables": list(REQUIRED_TABLES),
        "missing_schemas": [],
        "tables": {},
        "missing_tables": [],
        "migration_status": "not_checked",
        "server_check": _pg_isready_status(dsn),
    }
    socket_path = _socket_path(parsed)
    if socket_path:
        out["socket_path"] = socket_path
        out["socket_exists"] = Path(socket_path).exists()

    try:
        with _connect(dsn) as conn, conn.cursor() as cur:
            cur.execute("SELECT current_database(), current_user")
            row = cur.fetchone()
            if row:
                out["database"], out["user"] = row[0], row[1]
            cur.execute("SELECT version()")
            version_row = cur.fetchone()
            out["version"] = version_row[0] if version_row else ""

            cur.execute(
                """
                SELECT schema_name
                FROM information_schema.schemata
                WHERE schema_name = ANY(%s::text[])
                """,
                (list(REQUIRED_SCHEMAS),),
            )
            existing_schemas = {str(row[0]) for row in (cur.fetchall() or [])}
            out["missing_schemas"] = [
                schema for schema in REQUIRED_SCHEMAS if schema not in existing_schemas
            ]

            cur.execute(
                "SELECT to_regclass(table_name) FROM unnest(%s::text[]) AS table_name",
                (list(REQUIRED_TABLES),),
            )
            existence_rows = cur.fetchall() or []
            for index, table in enumerate(REQUIRED_TABLES):
                exists_row = existence_rows[index] if index < len(existence_rows) else None
                exists = bool(exists_row and exists_row[0])
                entry = {"exists": exists, "row_count": None}
                if exists:
                    entry["row_count"] = _safe_count(cur, table)
                else:
                    out["missing_tables"].append(table)
                out["tables"][table] = entry
    except Exception as exc:
        out.update(
            {
                "status": "error",
                "error": str(exc),
                "migration_status": "connection_error",
                "next_action": "./postgres/start_pg.sh status && ./postgres/start_pg.sh start",
            }
        )
        return out

    if out["missing_schemas"]:
        out["migration_status"] = "schema_missing"
    elif out["missing_tables"]:
        out["migration_status"] = "table_missing"
    else:
        out["migration_status"] = "ready"
    out["status"] = "ok" if out["migration_status"] == "ready" else "degraded"
    out["next_action"] = (
        "no action needed"
        if out["status"] == "ok"
        else "run /doctor --repair, then postgres/migrate.py or postgres/loader.py for missing data tables"
    )
    return out


def ensure_postgres_schema(dsn: str | None = None) -> dict[str, Any]:
    statements = (
        "CREATE SCHEMA IF NOT EXISTS market",
        "CREATE SCHEMA IF NOT EXISTS scores",
        "CREATE SCHEMA IF NOT EXISTS intraday",
        "CREATE SCHEMA IF NOT EXISTS report",
        """
        CREATE TABLE IF NOT EXISTS intraday.quote_snapshots (
            id BIGSERIAL PRIMARY KEY,
            symbol TEXT NOT NULL,
            captured_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            source TEXT,
            payload JSONB NOT NULL DEFAULT '{}'::jsonb
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS intraday.ohlcv_bars (
            symbol TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            ts TIMESTAMPTZ NOT NULL,
            open NUMERIC,
            high NUMERIC,
            low NUMERIC,
            close NUMERIC,
            volume NUMERIC,
            source TEXT,
            PRIMARY KEY (symbol, timeframe, ts)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS report.enhanced_runs (
            id BIGSERIAL PRIMARY KEY,
            run_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            report_type TEXT,
            payload JSONB NOT NULL DEFAULT '{}'::jsonb
        )
        """,
    )
    try:
        with _connect(dsn) as conn, conn.cursor() as cur:
            for statement in statements:
                cur.execute(statement)
            conn.commit()
    except Exception as exc:
        return {"tool": "ensure_postgres_schema", "status": "error", "error": str(exc)}
    return {"tool": "ensure_postgres_schema", "status": "ok", "statements": len(statements)}


def audit_postgres_coverage(dsn: str | None = None) -> dict[str, Any]:
    health = get_postgres_health(dsn)
    tables = health.get("tables", {})
    populated = {
        table: details
        for table, details in tables.items()
        if isinstance(details, dict) and details.get("exists") and (details.get("row_count") or 0) > 0
    }
    return {
        "tool": "audit_postgres_coverage",
        "status": health.get("status"),
        "required_table_count": len(REQUIRED_TABLES),
        "existing_table_count": sum(1 for details in tables.values() if details.get("exists")),
        "populated_table_count": len(populated),
        "missing_tables": health.get("missing_tables", []),
        "tables": tables,
    }


def load_historical_eod_to_postgres(symbol: str | None = None, days: int = 0, dsn: str | None = None) -> dict[str, Any]:
    return {
        "tool": "load_historical_eod_to_postgres",
        "status": "not_run",
        "reason": "Historical EOD load is executed by postgres/loader.py; use /load historical once wired.",
        "symbol": symbol,
        "days": days,
        "dsn": _parse_dsn(dsn).get("raw"),
    }


def load_intraday_ohlcv_to_postgres(symbol: str | None = None, timeframe: str = "15m", dsn: str | None = None) -> dict[str, Any]:
    return {
        "tool": "load_intraday_ohlcv_to_postgres",
        "status": "not_run",
        "reason": "Intraday OHLCV seeding is handled by terminal.intraday_ohlcv_loader until /load intraday is wired.",
        "symbol": symbol,
        "timeframe": timeframe,
        "dsn": _parse_dsn(dsn).get("raw"),
    }


def render_postgres_doctor(repair: bool = False, dsn: str | None = None) -> str:
    if repair:
        repair_result = ensure_postgres_schema(dsn)
        if repair_result.get("status") != "ok":
            return f"PostgreSQL doctor repair failed: {repair_result.get('error')}"

    health = get_postgres_health(dsn)
    lines = ["PostgreSQL Doctor"]
    lines.append(f"Status: {health.get('status')}")
    lines.append(f"DSN: {health.get('dsn')}")
    lines.append(f"Host: {health.get('host')}")
    if health.get("socket_path"):
        socket_label = "exists" if health.get("socket_exists") else "missing"
        lines.append(f"Socket: {health.get('socket_path')} ({socket_label})")
    missing_schemas = health.get("missing_schemas") or []
    lines.append(f"Schemas: {', '.join(missing_schemas) if missing_schemas else 'ready'}")
    lines.append(f"Migration status: {health.get('migration_status')}")
    if health.get("error"):
        lines.append(f"Error: {health.get('error')}")
    tables = health.get("tables") or {}
    if tables:
        lines.append("Tables:")
        for table in sorted(tables):
            details = tables[table] or {}
            if details.get("exists"):
                row_count = details.get("row_count")
                row_label = "unknown rows" if row_count is None else f"{row_count} rows"
                lines.append(f"  - {table}: ok ({row_label})")
            else:
                lines.append(f"  - {table}: missing")
    missing = health.get("missing_tables") or []
    lines.append(f"Missing tables: {', '.join(missing) if missing else 'none'}")
    lines.append(f"Next action: {health.get('next_action')}")
    return "\n".join(lines)
