from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ReleaseGateCheck:
    name: str
    passed: bool
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


def build_release_gate_report(
    *,
    benchmark_pass_rate: float | None,
    disabled_routing_passed: bool,
    enabled_skill_tests_passed: bool,
    unsafe_sql_tests_passed: bool,
    retrieval_logs_written: bool,
    learning_capture_safe: bool,
    user_approved_enablement: bool,
    min_benchmark_pass_rate: float = 0.90,
) -> dict[str, Any]:
    """Return a read-only runtime-enable preflight report.

    This intentionally does not flip ``AGENT_ADDA_SKILL_STORE`` or edit config.
    The backlog requires explicit user approval before making runtime retrieval
    a local default.
    """
    rate = float(benchmark_pass_rate or 0.0)
    checks = [
        ReleaseGateCheck(
            "benchmark_pass_rate",
            rate >= min_benchmark_pass_rate,
            f"{rate:.0%} >= {min_benchmark_pass_rate:.0%}",
        ),
        ReleaseGateCheck(
            "disabled_routing_smoke",
            bool(disabled_routing_passed),
            "deterministic routing passes with skill store disabled",
        ),
        ReleaseGateCheck(
            "enabled_skill_store_tests",
            bool(enabled_skill_tests_passed),
            "skill-store E2E and benchmark tests pass with feature flag enabled",
        ),
        ReleaseGateCheck(
            "unsafe_sql_tests",
            bool(unsafe_sql_tests_passed),
            "unsafe SQL templates are rejected",
        ),
        ReleaseGateCheck(
            "retrieval_logs_written",
            bool(retrieval_logs_written),
            "runtime retrieval/execution logs are observable",
        ),
        ReleaseGateCheck(
            "learning_capture_safe",
            bool(learning_capture_safe),
            "learning capture does not affect answers",
        ),
        ReleaseGateCheck(
            "user_approved_enablement",
            bool(user_approved_enablement),
            "explicit user approval is required before enabling by default",
        ),
    ]
    blocked_by = [check.name for check in checks if not check.passed]
    return {
        "ready": not blocked_by,
        "blocked_by": blocked_by,
        "checks": [check.to_dict() for check in checks],
        "would_enable_default": not blocked_by and bool(user_approved_enablement),
    }


def render_release_gate_report(report: dict[str, Any]) -> str:
    lines = [
        "## Skill Store Runtime Enablement Gate",
        "",
        f"Ready: {'yes' if report.get('ready') else 'no'}",
        f"Would enable default: {'yes' if report.get('would_enable_default') else 'no'}",
        "",
        "### Checks",
    ]
    for check in report.get("checks") or []:
        mark = "PASS" if check.get("passed") else "BLOCKED"
        lines.append(f"- {mark}: {check.get('name')} — {check.get('detail')}")
    blocked = report.get("blocked_by") or []
    if blocked:
        lines.extend(["", "### Blocked By"])
        lines.extend(f"- {item}" for item in blocked)
    lines.append("")
    lines.append("This preflight is read-only and does not change AGENT_ADDA_SKILL_STORE.")
    return "\n".join(lines)
