"""Data readiness checks for Agent Adda startup and terminal commands."""

from __future__ import annotations

import os
import shlex
import sqlite3
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Callable


TECHNICAL_COLUMNS = ("technical_score", "rsi", "relative_strength", "trading_signal")
FUNDAMENTAL_COLUMNS = ("enhanced_fund_score", "financial_strength", "can_slim_score")
PG_DSN = os.environ.get("AGENT_ADDA_PG_DSN") or os.environ.get("PG_DSN") or "dbname=nse_market user=nse_admin host=/tmp"


@dataclass(frozen=True)
class DataReadinessStatus:
    db_path: Path
    status: str
    latest_snapshot_date: str | None = None
    row_count: int = 0
    technical_covered: int = 0
    fundamental_covered: int = 0
    technical_coverage_pct: float = 0.0
    fundamental_coverage_pct: float = 0.0
    technical_status: str = "missing"
    fundamental_status: str = "missing"
    blockers: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    needs_refresh: bool = False


@dataclass(frozen=True)
class RefreshPlan:
    action: str
    reason: str
    command: tuple[str, ...] = ()


@dataclass(frozen=True)
class RefreshResult:
    exit_code: int | None
    plan: RefreshPlan
    status: DataReadinessStatus
    error: str = ""


Runner = Callable[[tuple[str, ...], Path], int]


def _project_root(project_root: Path | None = None) -> Path:
    return Path(project_root or Path.cwd()).resolve()


def _parse_today(today: str | date | None = None) -> date:
    if today is None:
        return date.today()
    if isinstance(today, date):
        return today
    return datetime.strptime(today, "%Y-%m-%d").date()


def _count_covered_expr(columns: tuple[str, ...]) -> str:
    checks = " AND ".join(f"{column} IS NOT NULL" for column in columns)
    return f"SUM(CASE WHEN {checks} THEN 1 ELSE 0 END)"


def _legacy_sqlite_fallbacks_enabled() -> bool:
    return os.environ.get("AGENT_ADDA_ENABLE_SQLITE_FALLBACKS", "").strip().lower() in {"1", "true", "yes"}


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(row[1]) for row in rows}


def inspect_data_readiness(
    project_root: Path | None = None,
    *,
    today: str | date | None = None,
    technical_threshold: float = 95.0,
    fundamental_threshold: float = 30.0,
) -> DataReadinessStatus:
    root = _project_root(project_root)
    db_path = root / "data" / "sector_rotation_tracker.db"
    today_date = _parse_today(today)

    try:
        import psycopg2

        conn = psycopg2.connect(PG_DSN)
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT MAX(snapshot_date)::text FROM scores.stage_snapshots")
                latest = cur.fetchone()[0]
                if latest is None:
                    return DataReadinessStatus(
                        db_path=Path("PostgreSQL:scores.stage_snapshots"),
                        status="missing",
                        blockers=("empty_stage_snapshots",),
                        needs_refresh=True,
                    )
                cur.execute(
                    f"""
                    SELECT
                        COUNT(*),
                        {_count_covered_expr(TECHNICAL_COLUMNS)},
                        {_count_covered_expr(FUNDAMENTAL_COLUMNS)}
                    FROM scores.stage_snapshots
                    WHERE snapshot_date = %s
                    """,
                    (latest,),
                )
                row_count, technical_covered, fundamental_covered = cur.fetchone()
        finally:
            conn.close()
    except Exception as pg_exc:
        if not _legacy_sqlite_fallbacks_enabled():
            return DataReadinessStatus(
                db_path=Path("PostgreSQL:scores.stage_snapshots"),
                status="missing",
                blockers=(f"postgres_error:{pg_exc}",),
                needs_refresh=True,
            )
    else:
        row_count = int(row_count or 0)
        technical_covered = int(technical_covered or 0)
        fundamental_covered = int(fundamental_covered or 0)
        technical_pct = (technical_covered / row_count * 100.0) if row_count else 0.0
        fundamental_pct = (fundamental_covered / row_count * 100.0) if row_count else 0.0

        snapshot_date = datetime.strptime(str(latest), "%Y-%m-%d").date()
        age_days = (today_date - snapshot_date).days
        freshness = "fresh_trading_day" if age_days <= 3 else "stale"
        technical_status = "fresh" if technical_pct >= technical_threshold else "partial_technical"
        fundamental_status = (
            "ready" if fundamental_pct >= fundamental_threshold else "partial_fundamentals"
        )
        blockers: list[str] = []
        warnings: list[str] = []
        if freshness == "stale":
            blockers.append(f"stale_snapshot:{latest}")
        if technical_status == "partial_technical":
            blockers.append(f"low_technical_coverage:{technical_covered}/{row_count}")
        if fundamental_status == "partial_fundamentals":
            warnings.append(f"low_fundamental_coverage:{fundamental_covered}/{row_count}")

        return DataReadinessStatus(
            db_path=Path("PostgreSQL:scores.stage_snapshots"),
            status=freshness,
            latest_snapshot_date=str(latest),
            row_count=row_count,
            technical_covered=technical_covered,
            fundamental_covered=fundamental_covered,
            technical_coverage_pct=round(technical_pct, 2),
            fundamental_coverage_pct=round(fundamental_pct, 2),
            technical_status=technical_status,
            fundamental_status=fundamental_status,
            blockers=tuple(blockers),
            warnings=tuple(warnings),
            needs_refresh=bool(blockers or warnings),
        )

    if not db_path.exists():
        return DataReadinessStatus(
            db_path=db_path,
            status="missing",
            blockers=("missing_db",),
            needs_refresh=True,
        )

    try:
        conn = sqlite3.connect(db_path)
        try:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            if "stage_snapshots" not in tables:
                return DataReadinessStatus(
                    db_path=db_path,
                    status="missing",
                    blockers=("missing_stage_snapshots",),
                    needs_refresh=True,
                )

            columns = _table_columns(conn, "stage_snapshots")
            missing_columns = tuple(
                sorted(
                    ({"snapshot_date", "symbol"} | set(TECHNICAL_COLUMNS) | set(FUNDAMENTAL_COLUMNS))
                    - columns
                )
            )
            if missing_columns:
                return DataReadinessStatus(
                    db_path=db_path,
                    status="missing",
                    blockers=tuple(f"missing_column:{column}" for column in missing_columns),
                    needs_refresh=True,
                )

            latest = conn.execute(
                "SELECT MAX(snapshot_date) FROM stage_snapshots"
            ).fetchone()[0]
            if latest is None:
                return DataReadinessStatus(
                    db_path=db_path,
                    status="missing",
                    blockers=("empty_stage_snapshots",),
                    needs_refresh=True,
                )

            row_count, technical_covered, fundamental_covered = conn.execute(
                f"""
                SELECT
                    COUNT(*),
                    {_count_covered_expr(TECHNICAL_COLUMNS)},
                    {_count_covered_expr(FUNDAMENTAL_COLUMNS)}
                FROM stage_snapshots
                WHERE snapshot_date = ?
                """,
                (latest,),
            ).fetchone()
        finally:
            conn.close()
    except sqlite3.Error as exc:
        return DataReadinessStatus(
            db_path=db_path,
            status="missing",
            blockers=(f"db_error:{exc}",),
            needs_refresh=True,
        )

    row_count = int(row_count or 0)
    technical_covered = int(technical_covered or 0)
    fundamental_covered = int(fundamental_covered or 0)
    technical_pct = (technical_covered / row_count * 100.0) if row_count else 0.0
    fundamental_pct = (fundamental_covered / row_count * 100.0) if row_count else 0.0

    snapshot_date = datetime.strptime(str(latest), "%Y-%m-%d").date()
    age_days = (today_date - snapshot_date).days
    freshness = "fresh_trading_day" if age_days <= 3 else "stale"
    technical_status = "fresh" if technical_pct >= technical_threshold else "partial_technical"
    fundamental_status = (
        "ready" if fundamental_pct >= fundamental_threshold else "partial_fundamentals"
    )
    blockers: list[str] = []
    warnings: list[str] = []
    if freshness == "stale":
        blockers.append(f"stale_snapshot:{latest}")
    if technical_status == "partial_technical":
        blockers.append(f"low_technical_coverage:{technical_covered}/{row_count}")
    if fundamental_status == "partial_fundamentals":
        warnings.append(f"low_fundamental_coverage:{fundamental_covered}/{row_count}")

    return DataReadinessStatus(
        db_path=db_path,
        status=freshness,
        latest_snapshot_date=str(latest),
        row_count=row_count,
        technical_covered=technical_covered,
        fundamental_covered=fundamental_covered,
        technical_coverage_pct=round(technical_pct, 2),
        fundamental_coverage_pct=round(fundamental_pct, 2),
        technical_status=technical_status,
        fundamental_status=fundamental_status,
        blockers=tuple(blockers),
        warnings=tuple(warnings),
        needs_refresh=bool(blockers or warnings),
    )


def plan_refresh(status: DataReadinessStatus, *, project_root: Path | None = None) -> RefreshPlan:
    if not status.needs_refresh:
        return RefreshPlan(action="none", reason="no refresh needed")
    root = _project_root(project_root)
    if _has_postgres_connection_blocker(status):
        script = root / "postgres" / "start_pg.sh"
        return RefreshPlan(
            action="start_postgres",
            reason=", ".join(status.blockers),
            command=(str(script), "start"),
        )
    script = root / "daily_refresh.py"
    command = (sys.executable, str(script), "--skip-aux")
    if status.blockers:
        reason = ", ".join(status.blockers)
    elif status.warnings:
        reason = ", ".join(status.warnings)
    else:
        reason = status.status
    return RefreshPlan(action="run_refresh", reason=reason, command=command)


def _has_postgres_connection_blocker(status: DataReadinessStatus) -> bool:
    if not str(status.db_path).startswith("PostgreSQL:"):
        return False
    text = " ".join(status.blockers).lower()
    return (
        "postgres_error:" in text
        and (
            "connection to server" in text
            or "no such file or directory" in text
            or "connection refused" in text
            or "could not connect" in text
        )
    )


def _default_runner(command: tuple[str, ...], cwd: Path) -> int:
    return subprocess.run(command, cwd=cwd, check=False).returncode


def execute_refresh_plan(
    refresh_plan: RefreshPlan,
    *,
    project_root: Path | None = None,
    runner: Runner | None = None,
    today: str | date | None = None,
) -> RefreshResult:
    root = _project_root(project_root)
    if refresh_plan.action not in {"run_refresh", "start_postgres"}:
        return RefreshResult(
            exit_code=None,
            plan=refresh_plan,
            status=inspect_data_readiness(root, today=today),
        )

    try:
        exit_code = (runner or _default_runner)(refresh_plan.command, root)
        status = inspect_data_readiness(root, today=today)
        if exit_code != 0:
            status = DataReadinessStatus(
                db_path=status.db_path,
                status="degraded",
                latest_snapshot_date=status.latest_snapshot_date,
                row_count=status.row_count,
                technical_covered=status.technical_covered,
                fundamental_covered=status.fundamental_covered,
                technical_coverage_pct=status.technical_coverage_pct,
                fundamental_coverage_pct=status.fundamental_coverage_pct,
                technical_status=status.technical_status,
                fundamental_status=status.fundamental_status,
                blockers=status.blockers + (f"refresh_exit:{exit_code}",),
                warnings=status.warnings,
                needs_refresh=True,
            )
        return RefreshResult(exit_code=exit_code, plan=refresh_plan, status=status)
    except Exception as exc:
        status = inspect_data_readiness(root, today=today)
        degraded = DataReadinessStatus(
            db_path=status.db_path,
            status="degraded",
            latest_snapshot_date=status.latest_snapshot_date,
            row_count=status.row_count,
            technical_covered=status.technical_covered,
            fundamental_covered=status.fundamental_covered,
            technical_coverage_pct=status.technical_coverage_pct,
            fundamental_coverage_pct=status.fundamental_coverage_pct,
            technical_status=status.technical_status,
            fundamental_status=status.fundamental_status,
            blockers=status.blockers + (f"refresh_error:{exc}",),
            warnings=status.warnings,
            needs_refresh=True,
        )
        return RefreshResult(exit_code=None, plan=refresh_plan, status=degraded, error=str(exc))


def render_readiness_panel(status: DataReadinessStatus, plan: RefreshPlan | None = None) -> str:
    action = plan.action if plan else ("run_refresh" if status.needs_refresh else "none")
    if action == "run_refresh":
        command = " ".join(shlex.quote(part) for part in (plan.command if plan else ()))
        action_text = f"run {command}".strip()
    elif action == "start_postgres":
        command = " ".join(shlex.quote(part) for part in (plan.command if plan else ()))
        action_text = f"start local PostgreSQL: {command}".strip()
    else:
        action_text = "no refresh needed"

    technical_date = status.latest_snapshot_date or "not found"
    lines = [
        "Data Readiness",
        (
            f"Technical DB: {technical_date} · {status.row_count} stocks · "
            f"{status.technical_covered}/{status.row_count} technical "
            f"({status.technical_coverage_pct:.0f}%)"
        ),
        (
            f"Fundamental DB: {technical_date} · "
            f"{status.fundamental_covered}/{status.row_count} enhanced fundamentals · "
            f"{status.fundamental_status}"
        ),
        f"Status: {status.status}",
        f"Action: {action_text}",
    ]
    try:
        from terminal.postgres_tools import get_postgres_health

        pg_health = get_postgres_health(PG_DSN)
        missing = pg_health.get("missing_tables") or []
        if pg_health.get("status") == "ok":
            missing_label = f"missing {len(missing)} table(s)" if missing else "required tables ready"
        else:
            missing_label = f"missing {len(missing)} table(s)" if missing else "schema unavailable"
        lines.append(f"PostgreSQL: {pg_health.get('status')} · {missing_label}")
    except Exception as exc:
        lines.append(f"PostgreSQL: error · {exc}")
    if status.blockers:
        lines.append(f"Blockers: {', '.join(status.blockers)}")
    if status.warnings:
        lines.append(f"Warnings: {', '.join(status.warnings)}")
    return "\n".join(lines)


def handle_data_readiness_command(
    text: str,
    *,
    project_root: Path | None = None,
    today: str | date | None = None,
    runner: Runner | None = None,
) -> str:
    raw = text.strip()
    parts = shlex.split(raw)
    root = _project_root(project_root)
    status = inspect_data_readiness(root, today=today)
    refresh_plan = plan_refresh(status, project_root=root)

    if not parts or parts[0] not in {"/data-status", "/refresh-data"}:
        return "Usage:\n  /data-status\n  /refresh-data [--check]"

    if parts[0] == "/data-status" or "--check" in parts:
        return render_readiness_panel(status, refresh_plan)

    result = execute_refresh_plan(refresh_plan, project_root=root, runner=runner, today=today)
    lines = [render_readiness_panel(result.status, plan_refresh(result.status, project_root=root))]
    if result.exit_code is not None:
        lines.append(f"Refresh exit code: {result.exit_code}")
    if result.error:
        lines.append(f"Refresh error: {result.error}")
    return "\n".join(lines)


def append_readiness_metadata(
    answer: str,
    *,
    project_root: Path | None = None,
    today: str | date | None = None,
) -> str:
    status = inspect_data_readiness(project_root, today=today)
    date_label = status.latest_snapshot_date or "not found in DB"
    missing_bits: list[str] = []
    if status.technical_status != "fresh":
        missing_bits.append("technical fields not found in DB")
    if status.fundamental_status != "ready":
        missing_bits.append("fundamental fields not found in DB")
    if status.status in {"missing", "stale", "degraded"}:
        missing_bits.append(f"readiness status {status.status}")
    gap_text = "; ".join(missing_bits) if missing_bits else "coverage meets readiness thresholds"
    metadata = (
        f"\n\n_Data Freshness: snapshot {date_label} · "
        f"technical {status.technical_covered}/{status.row_count} · "
        f"fundamentals {status.fundamental_covered}/{status.row_count} · {gap_text}_"
    )
    if "Data Freshness:" in answer[-800:]:
        return answer
    return answer + metadata


def readiness_enabled(skip_readiness: bool = False) -> bool:
    return not skip_readiness and os.environ.get("AGENT_ADDA_SKIP_READINESS") != "1"
