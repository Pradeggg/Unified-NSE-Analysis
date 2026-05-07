from __future__ import annotations

import os
import shutil
import sqlite3
import sys
from contextlib import closing
from dataclasses import dataclass

from .config.settings import AppConfig


@dataclass(frozen=True)
class DoctorCheck:
    name: str
    ok: bool
    detail: str


@dataclass(frozen=True)
class DoctorResult:
    checks: list[DoctorCheck]

    @property
    def ok(self) -> bool:
        required = {"python", "config", "historical_database"}
        return all(check.ok for check in self.checks if check.name in required)


def _database_detail(config: AppConfig) -> DoctorCheck:
    if not config.database_path.exists():
        return DoctorCheck(
            "historical_database",
            False,
            f"Missing {config.database_path}; run agent-adda data bootstrap --historical",
        )
    try:
        with closing(sqlite3.connect(config.database_path)) as conn:
            count = conn.execute("select count(*) from daily_prices").fetchone()[0]
    except sqlite3.Error as exc:
        return DoctorCheck("historical_database", False, f"SQLite check failed: {exc}")
    return DoctorCheck("historical_database", True, f"{count} daily price rows")


def run_doctor(config: AppConfig) -> DoctorResult:
    checks = [
        DoctorCheck(
            "python",
            sys.version_info >= (3, 10),
            f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        ),
        DoctorCheck(
            "config",
            config.home_dir.exists(),
            f"Home directory: {config.home_dir}",
        ),
        _database_detail(config),
        DoctorCheck(
            "openai_api_key",
            bool(os.environ.get(config.openai_api_key_env)),
            f"Environment variable: {config.openai_api_key_env}",
        ),
        DoctorCheck(
            "ollama",
            shutil.which("ollama") is not None,
            "Optional local model runtime",
        ),
    ]
    return DoctorResult(checks)
