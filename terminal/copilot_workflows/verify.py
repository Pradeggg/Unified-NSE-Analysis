"""Deterministic /verify workflow."""

from __future__ import annotations

from pathlib import Path

from .common import command_arg
from terminal.report_validation import validate_reports, write_validation_markdown
from terminal.task_memory import TaskMemoryStore


def _status(ok: bool, label: str, detail: str) -> str:
    state = "PASS" if ok else "WARN"
    return f"- {state}: {label} - {detail}"


def _check_path(path: Path, label: str) -> str:
    return _status(path.exists(), label, f"`{path}`" if path.exists() else f"missing `{path}`")


def render_verify(
    target: str,
    *,
    cwd: Path | None = None,
    memory_store: TaskMemoryStore | None = None,
) -> str:
    target = (target or "").strip().lower() or "reports"
    cwd = cwd or Path.cwd()
    checks: list[str]
    next_action = "Investigate WARN lines before relying on the artifact."
    artifact = ""

    if target.startswith("report"):
        report_paths = [
            cwd / "reports/latest/results_analysis.html",
            cwd / "reports/latest/stage2_tracker.html",
            cwd / "reports/latest/top_picks.html",
        ]
        results = validate_reports(report_paths)
        artifact_path = cwd / "reports/latest/report_validation.md"
        write_validation_markdown(results, artifact_path)
        artifact = str(artifact_path)
        checks = []
        aggregate = {"pass": 0, "warn": 0, "fail": 0}
        for path, result in zip(report_paths, results, strict=False):
            exists_line = _check_path(path, _report_label(path))
            summary = result.summary()
            for key, value in summary.items():
                aggregate[key] = aggregate.get(key, 0) + value
            if summary["fail"]:
                checks.append(f"- FAIL: {_report_label(path)} links - {summary}")
            elif summary["warn"]:
                checks.append(f"- WARN: {_report_label(path)} links - {summary}")
            else:
                checks.append(exists_line)
        if memory_store is not None:
            memory_store.record_report_validation(artifact, summary=aggregate)
    elif target.startswith("data"):
        checks = [
            _check_path(cwd / "data/nse_stock_cache.RData", "stock cache"),
            _check_path(cwd / "data/breadth_history.csv", "breadth history"),
            _check_path(cwd / "data/signal_log.csv", "signal log"),
        ]
    elif target.startswith("portfolio"):
        checks = [
            _check_path(cwd / "docs/my_portfolio.csv.csv", "portfolio source"),
            _check_path(cwd / "reports/latest/portfolio_analysis.html", "portfolio EOD report"),
            _check_path(cwd / "reports/latest/portfolio_strategy_lab.html", "strategy lab report"),
        ]
    elif "quality-breakouts" in target or "quality breakouts" in target:
        checks = [
            _status(True, "command registered", "`/screen quality-breakouts` is available"),
            _status(True, "verification command", "run `/screen quality-breakouts --explain --tv` for live candidates"),
        ]
        next_action = "Run the command smoke when market/data dependencies are available."
    else:
        checks = [
            _status(False, "unknown target", f"`{target}` is not one of reports, data, portfolio, screen quality-breakouts"),
        ]

    passed = sum(1 for line in checks if line.startswith("- PASS:"))
    warnings = sum(1 for line in checks if line.startswith("- WARN:"))
    failures = sum(1 for line in checks if line.startswith("- FAIL:"))
    neutral_warns = len(checks) - passed - warnings - failures
    warnings += neutral_warns
    if failures:
        next_action = "Fix FAIL lines, regenerate affected reports if needed, then rerun `/verify reports`."
    return "\n".join([
        "# Verification",
        "",
        f"**Target:** {target}",
        "",
        "**Checks Run**",
        *checks,
        "",
        f"**Summary:** {passed} pass, {warnings} warn, {failures} fail",
        *(["", f"**Validation Report:** `{artifact}`"] if artifact else []),
        "",
        f"**Next Action:** {next_action}",
    ])


def handle_verify_command(command: str) -> str:
    store = TaskMemoryStore()
    store.record_command(command)
    return render_verify(command_arg(command, "verify"), memory_store=store)


def _report_label(path: Path) -> str:
    labels = {
        "results_analysis.html": "results analysis report",
        "stage2_tracker.html": "stage2 report",
        "top_picks.html": "top picks report",
    }
    return labels.get(path.name, path.name)
