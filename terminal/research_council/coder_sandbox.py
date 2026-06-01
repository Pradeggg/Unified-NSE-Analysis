"""Restricted file and code guards for the Research Council Coder agent."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


FEATURE_DIR = Path("terminal/research_council/features")
STRATEGY_DIR = Path("terminal/research_council/strategies")
FEATURE_TEST_DIR = Path("tests/research_council/features")
DESTRUCTIVE_SQL = re.compile(r"\b(drop|delete|update|truncate)\b", re.IGNORECASE)
BROKER_LIVE_ORDER = re.compile(
    r"\b("
    r"broker|kiteconnect|zerodha|upstox|fyers|aliceblue|smartapi|"
    r"place_order|execute_order|execute_live_order|live_order|buy_order|sell_order"
    r")\b",
    re.IGNORECASE,
)


class SandboxViolation(RuntimeError):
    """Raised when generated coder work violates sandbox policy."""


@dataclass(frozen=True)
class FeatureWriteResult:
    feature_path: Path
    test_path: Path


class CoderSandbox:
    """Restrict generated coder artifacts to Research Council-owned paths."""

    def __init__(self, project_root: str | Path | None = None) -> None:
        self.project_root = Path(project_root or Path.cwd()).resolve()
        self.feature_dir = self.project_root / FEATURE_DIR
        self.strategy_dir = self.project_root / STRATEGY_DIR
        self.feature_test_dir = self.project_root / FEATURE_TEST_DIR

    def write_feature_module(
        self,
        name: str,
        source: str,
        *,
        test_source: str | None = None,
    ) -> FeatureWriteResult:
        """Write a generated feature module and its mandatory test scaffold."""
        self.validate_source(source)
        feature_name = _safe_module_name(name)
        feature_path = self._resolve_under(self.feature_dir, f"{feature_name}.py")
        test_path = self._resolve_under(self.feature_test_dir, f"test_{feature_name}.py")
        self._write_checked(feature_path, source)
        self._write_checked(test_path, test_source or _default_feature_test(feature_name))
        return FeatureWriteResult(feature_path=feature_path, test_path=test_path)

    def write_strategy_spec(self, name: str, content: str, *, suffix: str = ".json") -> Path:
        """Write a generated strategy spec under the strategy sandbox."""
        self.validate_source(content)
        spec_name = _safe_module_name(name)
        clean_suffix = suffix if suffix.startswith(".") else f".{suffix}"
        path = self._resolve_under(self.strategy_dir, f"{spec_name}{clean_suffix}")
        self._write_checked(path, content)
        return path

    def assert_feature_ready(self, name: str) -> bool:
        """Require both generated feature code and its test scaffold to exist."""
        feature_name = _safe_module_name(name)
        feature_path = self._resolve_under(self.feature_dir, f"{feature_name}.py")
        test_path = self._resolve_under(self.feature_test_dir, f"test_{feature_name}.py")
        if not feature_path.exists() or not test_path.exists():
            raise SandboxViolation(
                f"Generated feature {feature_name!r} is not usable until feature file and test scaffold both exist."
            )
        return True

    def write_sandbox_file(self, relative_path: str | Path, content: str) -> Path:
        """Low-level write helper for sanctioned sandbox directories only."""
        rel = Path(relative_path)
        base = self.feature_dir if not rel.parts or rel.parts[0] != "strategies" else self.strategy_dir
        if rel.parts and rel.parts[0] in {"features", "strategies"}:
            rel = Path(*rel.parts[1:])
        path = self._resolve_under(base, rel)
        self.validate_source(content)
        self._write_checked(path, content)
        return path

    def validate_sql(self, sql: str, *, allow_mutation: bool = False) -> bool:
        """Reject destructive SQL unless the caller passes explicit approval."""
        if allow_mutation:
            return True
        normalized = _strip_sql_literals_and_comments(sql or "")
        match = DESTRUCTIVE_SQL.search(normalized)
        if match:
            raise SandboxViolation(f"Destructive SQL is blocked without explicit approval: {match.group(1).upper()}")
        return True

    def validate_source(self, source: str) -> bool:
        """Reject generated code that attempts live order or broker integration."""
        match = BROKER_LIVE_ORDER.search(source or "")
        if match:
            raise SandboxViolation(f"Generated code references blocked broker/live-order capability: {match.group(1)}")
        return True

    def _resolve_under(self, directory: Path, relative_path: str | Path) -> Path:
        base = directory.resolve()
        path = (base / relative_path).resolve()
        try:
            path.relative_to(base)
        except ValueError as exc:
            raise SandboxViolation(f"Attempted write outside sandbox: {path}") from exc
        return path

    def _write_checked(self, path: Path, content: str) -> None:
        allowed_roots = (self.feature_dir.resolve(), self.strategy_dir.resolve(), self.feature_test_dir.resolve())
        if not any(_is_relative_to(path, root) for root in allowed_roots):
            raise SandboxViolation(f"Attempted write outside sandbox: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def _safe_module_name(value: str) -> str:
    name = re.sub(r"[^A-Za-z0-9_]+", "_", (value or "").strip().lower()).strip("_")
    if not name:
        raise SandboxViolation("Generated artifact name is empty")
    if name[0].isdigit():
        name = f"f_{name}"
    return name


def _default_feature_test(feature_name: str) -> str:
    return (
        f"from terminal.research_council.features import {feature_name}\n\n\n"
        f"def test_{feature_name}_compute_contract():\n"
        f"    assert callable({feature_name}.compute)\n"
    )


def _strip_sql_literals_and_comments(sql: str) -> str:
    without_line_comments = re.sub(r"--.*?$", "", sql, flags=re.MULTILINE)
    without_block_comments = re.sub(r"/\*.*?\*/", "", without_line_comments, flags=re.DOTALL)
    return re.sub(r"'(?:''|[^'])*'", "''", without_block_comments)


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False
