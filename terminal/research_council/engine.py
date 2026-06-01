"""State-machine entry point for Research Council runs."""

from __future__ import annotations

import argparse
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from terminal.research_council.mode_profiles import load_mode_profile
from terminal.research_council.persistence import (
    export_council_run,
    resume_council_run,
    save_council_run_metadata as persist_run_metadata,
)
from terminal.research_council.schemas import CouncilState
from terminal.research_council.states import (
    branch_deliberation,
    critic_review,
    data_steward,
    intake,
    market_state,
    persistence,
    plan_build,
    plan_execute,
    plan_review,
    render_html,
    revision,
    route,
    specialist_pass,
    synthesis,
)

STATE_SEQUENCE = (
    "intake",
    "route",
    "data_steward",
    "market_state",
    "specialist_pass",
    "branch_deliberation",
    "plan_build",
    "plan_execute",
    "plan_review",
    "critic_review",
    "revision",
    "synthesis",
    "render_html",
    "persistence",
)

EVIDENCE_ONLY_SEQUENCE = (
    "intake",
    "route",
    "data_steward",
    "market_state",
    "render_html",
    "persistence",
)

TERMINAL_STATES = {
    "persistence",
    "abort_stale_data",
    "abort_budget",
    "escalate_human",
    "commit_no_trade",
}

STATE_HANDLERS: dict[str, Callable[[CouncilState], CouncilState]] = {
    "intake": intake.run,
    "route": route.run,
    "data_steward": data_steward.run,
    "market_state": market_state.run,
    "specialist_pass": specialist_pass.run,
    "branch_deliberation": branch_deliberation.run,
    "plan_build": plan_build.run,
    "plan_execute": plan_execute.run,
    "plan_review": plan_review.run,
    "critic_review": critic_review.run,
    "revision": revision.run,
    "synthesis": synthesis.run,
    "render_html": render_html.run,
    "persistence": persistence.run,
}


def run_council(objective: str, **flags: Any) -> CouncilState:
    """Run a Research Council state-machine pass."""

    state = initialize_state(objective, **flags)
    if _budget_aborts_immediately(state, flags):
        return _abort_budget(state, "wall_clock_s")
    if not state.flags.get("dry_run"):
        persist_run_metadata(state)

    start_time = datetime.now()
    wall_clock_cap = int(state.budgets.get("wall_clock_s", 480))

    for stage in _state_sequence_for(state):
        elapsed = (datetime.now() - start_time).total_seconds()
        remaining = wall_clock_cap - elapsed
        if remaining <= 0:
            state = _update_budgets(state, elapsed=elapsed, remaining_wall_clock_s=0)
            return _abort_budget(state, "wall_clock_s")
        state = _update_budgets(state, elapsed=elapsed, remaining_wall_clock_s=remaining)
        state = _replace_state(state, stage=stage)
        state = STATE_HANDLERS[stage](state)
        state.events.append(_event(stage, state))
        if state.stage in TERMINAL_STATES and state.stage != stage:
            return state
    return state


def initialize_state(objective: str, **flags: Any) -> CouncilState:
    mode = str(flags.get("mode") or _infer_mode(objective))
    profile = load_mode_profile(mode)
    now = datetime.now()
    horizon = str(flags.get("horizon") or _extract_flag_value(objective, "horizon") or _infer_horizon(objective))
    risk_budget = str(flags.get("risk_budget") or flags.get("risk") or _extract_flag_value(objective, "risk") or "moderate")
    symbols = [str(s).upper() for s in flags.get("symbols", [])]

    return CouncilState(
        run_id=_make_run_id(now),
        session_id=str(flags.get("session_id") or "local"),
        created_at=now,
        mode=mode,
        stage="intake",
        objective=objective,
        horizon=horizon,
        risk_budget=risk_budget,
        universe_filter=str(flags.get("universe_filter") or flags.get("universe") or "liquid"),
        symbols=symbols,
        budgets={
            "wall_clock_s": int(flags.get("max_wall_clock_s", profile.wall_clock_s)),
            "tokens": int(flags.get("token_budget", profile.token_budget)),
        },
        flags={k: v for k, v in flags.items() if k not in {"symbols"}},
    )


def _infer_mode(objective: str) -> str:
    text = objective.lower()
    if "strategy" in text or "backtest" in text:
        return "strategy_build"
    if _looks_like_sector_opportunity(text):
        return "sector_opportunity"
    if "intraday" in text or "vwap" in text:
        return "intraday_tactical"
    if "report" in text and ("review" in text or "file" in text):
        return "report_review"
    if "stock " in text or "compare " in text:
        return "stock_deep_dive"
    return "market_council"


def _looks_like_sector_opportunity(text: str) -> bool:
    sector_terms = (
        "nifty auto",
        "auto sector",
        "pharma sector",
        "it sector",
        "bank sector",
        "metal sector",
        "fmcg sector",
        "realty sector",
        "sector opportunity",
    )
    intent_terms = ("best", "potential", "opportunity", "identify", "shortlist", "candidate", "stocks")
    return any(term in text for term in sector_terms) and any(term in text for term in intent_terms)


def _infer_horizon(objective: str) -> str:
    text = objective.lower()
    if "intraday" in text:
        return "intraday"
    if "positional" in text:
        return "positional"
    return "swing"


def _extract_flag_value(objective: str, flag: str) -> str | None:
    match = re.search(rf"--{re.escape(flag)}\s+([A-Za-z0-9_-]+)", objective)
    return match.group(1) if match else None


def _make_run_id(now: datetime) -> str:
    return f"research_{now.strftime('%Y%m%d')}_{now.strftime('%H%M%S')}"


def _budget_aborts_immediately(state: CouncilState, flags: dict[str, Any]) -> bool:
    return "max_wall_clock_s" in flags and int(flags["max_wall_clock_s"]) <= 0


def _state_sequence_for(state: CouncilState) -> tuple[str, ...]:
    if state.flags.get("evidence_only"):
        return EVIDENCE_ONLY_SEQUENCE
    return STATE_SEQUENCE


def _update_budgets(state: CouncilState, *, elapsed: float, remaining_wall_clock_s: float) -> CouncilState:
    budgets = dict(state.budgets)
    budgets["elapsed_s"] = round(elapsed, 2)
    budgets["remaining_wall_clock_s"] = max(0, round(remaining_wall_clock_s, 2))
    return _replace_state(state, budgets=budgets)


def _abort_budget(state: CouncilState, budget_key: str) -> CouncilState:
    flags = dict(state.flags)
    flags["budget_abort"] = budget_key
    state = _replace_state(state, stage="abort_budget", flags=flags)
    state.events.append(_event("abort_budget", state))
    return state


def _event(stage: str, state: CouncilState) -> dict[str, Any]:
    return {
        "stage": stage,
        "run_id": state.run_id,
        "mode": state.mode,
        "objective": state.objective,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }


def _replace_state(state: CouncilState, **changes: Any) -> CouncilState:
    data = state.to_dict()
    data.update(changes)
    return CouncilState.from_dict(data)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--objective", default=None)
    parser.add_argument("--mode")
    parser.add_argument("--sector")
    parser.add_argument("--horizon")
    parser.add_argument("--risk", "--risk-budget", dest="risk_budget")
    parser.add_argument("--symbol", dest="symbols", action="append", default=[])
    parser.add_argument("--universe", dest="universe_filter")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--evidence-only", action="store_true")
    parser.add_argument("--format", choices=["md", "html", "both"], default="md")
    parser.add_argument("--print-report", action="store_true", help="Print the generated markdown report to stdout.")
    args = parser.parse_args()

    objective = args.objective or _default_cli_objective(args)
    flags = _cli_flags(args)
    result = run_council(objective, **flags)
    _print_cli_summary(result)
    if args.print_report:
        _print_markdown_report(result)


def _default_cli_objective(args: argparse.Namespace) -> str:
    if args.sector:
        objective = f"/council sector {args.sector}"
        if args.horizon:
            objective += f" --horizon {args.horizon}"
        if args.risk_budget:
            objective += f" --risk {args.risk_budget}"
        return objective
    if args.symbols:
        return "review " + " ".join(args.symbols)
    return "today swing"


def _cli_flags(args: argparse.Namespace) -> dict[str, Any]:
    flags: dict[str, Any] = {
        "dry_run": args.dry_run,
        "evidence_only": args.evidence_only,
        "output_format": args.format,
    }
    for key in ("mode", "sector", "horizon", "risk_budget", "universe_filter"):
        value = getattr(args, key)
        if value:
            flags[key] = value
    if args.symbols:
        flags["symbols"] = args.symbols
    return flags


def _print_cli_summary(result: CouncilState) -> None:
    for event in result.events:
        print(f"{event['stage']}: {event['objective']}")
    print(
        f"status: {result.stage} mode={result.mode} horizon={result.horizon} risk={result.risk_budget}"
    )
    decision = result.decision
    if decision:
        print(f"decision: {decision.final_label} confidence={decision.confidence:.2f}")
        for line in _candidate_summary_lines(decision.candidates):
            print(line)
    if result.flags.get("markdown_report_path"):
        print(f"markdown_report: {result.flags['markdown_report_path']}")
    if result.flags.get("html_report_path"):
        print(f"html_report: {result.flags['html_report_path']}")


def _candidate_summary_lines(candidates: list[dict[str, Any]], *, limit: int = 5) -> list[str]:
    lines: list[str] = []
    for index, candidate in enumerate(candidates[:limit], start=1):
        symbol = candidate.get("symbol", "n/a")
        score = candidate.get("research_score", "n/a")
        verdict = (candidate.get("quant_sweep") or {}).get("verdict")
        suffix = f" quant={verdict}" if verdict else ""
        lines.append(f"{index}. {symbol} score={score}{suffix}")
    return lines


def _print_markdown_report(result: CouncilState) -> None:
    report_path = result.flags.get("markdown_report_path")
    if not report_path:
        print("report_body: unavailable")
        return
    path = Path(report_path)
    if not path.exists():
        print(f"report_body: missing {report_path}")
        return
    print("----- BEGIN RESEARCH COUNCIL REPORT -----")
    print(path.read_text(encoding="utf-8").rstrip())
    print("----- END RESEARCH COUNCIL REPORT -----")


if __name__ == "__main__":
    main()
