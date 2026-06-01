"""Terminal command surface for Research Council workflows."""

from __future__ import annotations

import shlex
from dataclasses import dataclass, field
from typing import Any


RUN_ACTIONS = {"today", "sector", "stock", "compare", "strategy", "intraday"}
REPORT_ACTIONS = {"review", "report", "resume", "debug", "export"}
ALL_ACTIONS = RUN_ACTIONS | REPORT_ACTIONS | {"steward"}


@dataclass(frozen=True)
class CouncilCommand:
    action: str
    objective: str
    mode: str
    symbols: list[str] = field(default_factory=list)
    horizon: str = "swing"
    risk_budget: str = "moderate"
    options: dict[str, Any] = field(default_factory=dict)


def parse_council_command(text: str) -> CouncilCommand:
    """Parse a `/council ...` terminal command into stable execution args."""
    parts = shlex.split((text or "").strip())
    if not parts or parts[0].lower() != "/council":
        raise ValueError("Usage: /council <today|sector|stock|compare|strategy|intraday|review|report|resume|steward|debug|export>")

    action = parts[1].lower() if len(parts) > 1 and not parts[1].startswith("--") else "today"
    if action not in ALL_ACTIONS:
        raise ValueError(f"Unknown /council action: {action}")

    positionals, flags = _split_positionals_and_flags(parts[2:])
    symbols = _symbols_for(action, positionals)
    mode = _mode_for(action)
    horizon = str(flags.get("horizon") or ("intraday" if action == "intraday" else "swing"))
    risk_budget = str(flags.get("risk") or flags.get("risk_budget") or "moderate")
    options: dict[str, Any] = dict(flags)
    if action == "strategy" and positionals:
        options["hypothesis"] = positionals[0]
    if action == "sector" and positionals:
        options["sector"] = " ".join(positionals).upper()

    return CouncilCommand(
        action=action,
        objective=(text or "").strip(),
        mode=mode,
        symbols=symbols,
        horizon=horizon,
        risk_budget=risk_budget,
        options=options,
    )


def handle_council_command(text: str) -> str:
    """Execute a parsed `/council` command via public terminal tool wrappers."""
    parsed = parse_council_command(text)
    from terminal import tools

    if parsed.action == "steward":
        result = tools.run_data_steward_check(mode=parsed.mode)
        return _render_steward_result(result)

    if parsed.action in RUN_ACTIONS:
        execution_options = _run_options(parsed)
        result = tools.run_research_council(
            parsed.objective,
            mode=parsed.mode,
            symbols=parsed.symbols,
            horizon=parsed.horizon,
            risk_budget=parsed.risk_budget,
            **execution_options,
        )
        return _render_run_result(result)

    report_path = _report_path_option(parsed)
    if parsed.action == "review" and report_path:
        result = tools.run_research_council(
            parsed.objective,
            mode=parsed.mode,
            symbols=parsed.symbols,
            horizon=parsed.horizon,
            risk_budget=parsed.risk_budget,
            report_path=report_path,
        )
        return _render_run_result(result)

    run_id = str(parsed.options.get("run") or parsed.options.get("run_id") or "latest")
    if parsed.action == "report":
        result = tools.render_research_council_report(run_id=run_id, output_format=str(parsed.options.get("format") or "html"))
    elif parsed.action == "export":
        result = tools.resume_council_run(run_id=run_id, output_format=str(parsed.options.get("format") or "json"))
    else:
        result = tools.resume_council_run(run_id=run_id, include_debug=parsed.action == "debug")
    return _render_operational_result(parsed.action, result)


def _split_positionals_and_flags(parts: list[str]) -> tuple[list[str], dict[str, Any]]:
    positionals: list[str] = []
    flags: dict[str, Any] = {}
    i = 0
    while i < len(parts):
        token = parts[i]
        if token.startswith("--"):
            key = token[2:].replace("-", "_")
            if i + 1 < len(parts) and not parts[i + 1].startswith("--"):
                flags[key] = parts[i + 1]
                i += 2
            else:
                flags[key] = True
                i += 1
            continue
        positionals.append(token)
        i += 1
    return positionals, flags


def _run_options(parsed: CouncilCommand) -> dict[str, Any]:
    execution_options = {
        key: value
        for key, value in parsed.options.items()
        if key not in {"horizon", "risk", "risk_budget"}
    }
    report_path = _report_path_option(parsed)
    if report_path:
        execution_options["report_path"] = report_path
    for key in {"file", "path", "report"}:
        execution_options.pop(key, None)
    return execution_options


def _report_path_option(parsed: CouncilCommand) -> str | None:
    value = parsed.options.get("report_path") or parsed.options.get("file") or parsed.options.get("path") or parsed.options.get("report")
    return str(value) if value else None


def _symbols_for(action: str, positionals: list[str]) -> list[str]:
    if action == "stock":
        return [positionals[0].upper()] if positionals else []
    if action == "compare":
        return [item.upper() for item in positionals]
    return []


def _mode_for(action: str) -> str:
    if action == "sector":
        return "sector_opportunity"
    if action in {"stock", "compare"}:
        return "stock_deep_dive"
    if action == "strategy":
        return "strategy_build"
    if action == "intraday":
        return "intraday_tactical"
    if action in REPORT_ACTIONS:
        return "report_review"
    return "market_council"


def _render_run_result(result: dict[str, Any]) -> str:
    if not result.get("ok"):
        return f"▶ RESEARCH COUNCIL\n  ERROR: {result.get('error', 'unknown error')}"
    report_paths = result.get("report_paths") or {}
    lines = [
        "▶ RESEARCH COUNCIL",
        f"  Run:    {result.get('run_id', '-')}",
        f"  Mode:   {result.get('mode', '-')}",
        f"  Stage:  {result.get('stage', '-')}",
        f"  Label:  {result.get('final_label') or '-'}",
    ]
    if result.get("evidence_only"):
        lines.append("  Evidence: only")
    if report_paths.get("markdown"):
        lines.append(f"  Report: {report_paths['markdown']}")
    if report_paths.get("html"):
        lines.append(f"  HTML:   {report_paths['html']}")

    # Inline the markdown report body so the user sees the analysis right
    # in the terminal — not just file paths. Falls back silently when the
    # file isn't accessible (test fixtures, race with persistence, etc.).
    md_path = report_paths.get("markdown")
    if md_path:
        try:
            from pathlib import Path
            body = Path(md_path).read_text(encoding="utf-8").strip()
        except (OSError, ValueError):
            body = ""
        if body:
            lines.append("")
            lines.append("─" * 78)
            lines.append(body)
            lines.append("─" * 78)
    return "\n".join(lines)


def _render_steward_result(result: dict[str, Any]) -> str:
    if not result.get("ok"):
        return f"▶ COUNCIL STEWARD\n  ERROR: {result.get('error', 'unknown error')}"
    verdict = result.get("verdict") or {}
    universe = verdict.get("universe") or {}
    return "\n".join(
        [
            "▶ COUNCIL STEWARD",
            f"  Status:   {verdict.get('data_status', '-')}",
            f"  As of:    {verdict.get('as_of', '-')}",
            f"  Universe: {universe.get('analyzed_symbols', universe.get('total_symbols', '-'))} analyzed",
        ]
    )


def _render_operational_result(action: str, result: dict[str, Any]) -> str:
    if not result.get("ok"):
        return f"▶ COUNCIL {action.upper()}\n  ERROR: {result.get('error', 'unknown error')}"
    lines = [f"▶ COUNCIL {action.upper()}", f"  Run: {result.get('run_id', '-')}"]
    if result.get("report_path"):
        lines.append(f"  Report: {result['report_path']}")
    if result.get("export_path"):
        lines.append(f"  Export: {result['export_path']}")
    return "\n".join(lines)
