"""Markdown renderer for Research Council reports."""

from __future__ import annotations

from pathlib import Path
from typing import Any

DISCLAIMER = "Not investment advice. For research and learning only."


def render_markdown(state: object) -> str:
    lines: list[str] = [
        "# Research Council Report",
        "",
        f"**{DISCLAIMER}**",
        "",
        "## Objective And Mode",
        f"- Objective: {_get(state, 'objective', 'unknown')}",
        f"- Mode: {_get(state, 'mode', 'unknown')}",
        f"- Horizon: {_get(state, 'horizon', 'unknown')}",
        f"- Risk budget: {_get(state, 'risk_budget', 'unknown')}",
        "",
    ]
    lines.extend(_data_freshness(state))
    lines.extend(_market_state(state))
    lines.extend(_sector_view(state))
    lines.extend(_candidate_table(state))
    lines.extend(_candidate_score_drivers(state))
    lines.extend(_evidence_gates(state))
    lines.extend(_agent_findings(state))
    lines.extend(_branch_summaries(state))
    lines.extend(_plan_steps(state))
    lines.extend(_execution_results(state))
    lines.extend(_route_sweep_details(state))
    lines.extend(_plan_reviews(state))
    lines.extend(_critic_review(state))
    lines.extend(_final_research_plan(state))
    lines.extend(_invalidation_and_next_actions(state))
    lines.extend(_missing_evidence(state))
    lines.extend(["", f"**{DISCLAIMER}**", ""])
    return "\n".join(lines)


def write_markdown_report(state: object, *, output_dir: str | Path = "reports/research_council") -> Path:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    path = output_path / f"{_get(state, 'run_id', 'research_council')}.md"
    path.write_text(render_markdown(state), encoding="utf-8")
    return path


def _data_freshness(state: object) -> list[str]:
    pack = _get(state, "evidence_pack")
    rows = ["## Data Freshness"]
    if not pack:
        return [*rows, "- Evidence pack unavailable.", ""]
    rows.append(f"- As of: {pack.as_of}")
    rows.append(f"- Evidence pack: {pack.pack_id}")
    for entry in pack.source_trail:
        rows.append(f"- {entry.source}: rows={entry.rows or 'n/a'}, latest={entry.latest_date or 'n/a'}, freshness={entry.freshness or 'n/a'}")
    rows.append("")
    return rows


def _market_state(state: object) -> list[str]:
    market = _section(state, "market")
    rows = ["## Market State"]
    rows.extend(_dict_bullets(market) or ["- Market state unavailable."])
    rows.append("")
    return rows


def _sector_view(state: object) -> list[str]:
    sectors = _section(state, "sectors").get("items", [])
    rows = ["## Sector View"]
    if not sectors:
        rows.append("- Sector view unavailable.")
    for sector in sectors:
        rows.append(
            f"- {sector.get('sector', 'Unknown')}: RS 1M={sector.get('rs_1m', 'n/a')}, breadth>{sector.get('breadth_pct_above_50dma', 'n/a')}%"
        )
    rows.append("")
    return rows


def _candidate_table(state: object) -> list[str]:
    decision = _get(state, "decision")
    rows = [
        "## Candidate Table",
        "| Symbol | Score | Label | Supporting Branch | Quant Verdict | Best Route | Validation Return | Symbol Contribution |",
        "|---|---|---|---|---|---|---|---|",
    ]
    candidates = decision.candidates if decision else []
    if not candidates:
        rows.append("| n/a | n/a | NO_TRADE | n/a | n/a | n/a | n/a | n/a |")
    for candidate in candidates:
        quant = candidate.get("quant_sweep") or {}
        route = _quant_route(quant)
        rows.append(
            f"| {_display(candidate.get('symbol'))} | {_display(candidate.get('research_score'))} | {decision.final_label} | {_display(candidate.get('supporting_branch'))} | "
            f"{_display(quant.get('verdict'))} | {route} | {_display(quant.get('validation_return_pct'))} | {_symbol_contribution(quant)} |"
        )
    rows.append("")
    return rows


def _agent_findings(state: object) -> list[str]:
    rows = ["## Agent Findings"]
    findings = _get(state, "specialist_findings", {})
    if not findings:
        rows.append("- No specialist findings recorded.")
    for finding in findings.values():
        rows.append(f"- {finding.agent}: {finding.stance} ({finding.confidence:.2f}) - {finding.thesis}")
    rows.append("")
    return rows


def _candidate_score_drivers(state: object) -> list[str]:
    decision = _get(state, "decision")
    rows = ["## Candidate Score Drivers"]
    candidates = decision.candidates if decision else []
    if not candidates:
        rows.append("- No candidates ranked.")
    for candidate in candidates:
        symbol = candidate.get("symbol", "n/a")
        rows.append(f"- {symbol}: {_score_driver_text(candidate.get('score_components') or {})}")
    rows.append("")
    return rows


def _evidence_gates(state: object) -> list[str]:
    findings = _get(state, "specialist_findings", {}) or {}
    gate_rows = []
    for agent in ("technical", "fno_risk", "fundamental", "catalyst", "sector_rotation"):
        finding = findings.get(agent)
        if not finding:
            continue
        status = "CONFIRMED" if finding.candidates else "PENDING"
        gate_rows.append((agent, status, finding.stance, finding.thesis))
    rows = [
        "## Evidence Gates",
        "| Gate | Status | Stance | Evidence Note |",
        "|---|---|---|---|",
    ]
    if not gate_rows:
        rows.append("| n/a | PENDING | n/a | No specialist gates recorded. |")
    for agent, status, stance, thesis in gate_rows:
        rows.append(f"| {agent} | {status} | {_display(stance)} | {_display(thesis)} |")
    rows.append("")
    return rows


def _branch_summaries(state: object) -> list[str]:
    rows = ["## Public POT/TOT Summaries"]
    summaries = _get(state, "branch_summaries", [])
    if not summaries:
        rows.append("- No branch summaries recorded.")
    for summary in summaries:
        rows.append(f"- {summary.branch}: {summary.stance}; candidates={', '.join(summary.candidates) or 'none'}")
    rows.append("")
    return rows


def _plan_steps(state: object) -> list[str]:
    rows = ["## Plan Steps"]
    plans = _get(state, "plans", [])
    if not plans:
        rows.append("- No plan recorded.")
    for plan in plans:
        rows.append(f"- Plan {plan.plan_id}: {plan.central_question}")
        for step in plan.steps:
            tools = ", ".join(call.tool_name for call in step.tool_calls) or "none"
            rows.append(f"  - {step.step_id}: {step.question} [{tools}]")
    rows.append("")
    return rows


def _execution_results(state: object) -> list[str]:
    rows = ["## Execution Results"]
    execution_results = _get(state, "execution_results", {})
    if not execution_results:
        rows.append("- No execution results recorded.")
    for plan_id, results in execution_results.items():
        rows.append(f"- Plan {plan_id}")
        for result in results.values():
            status, error = _execution_display_status(result)
            rows.append(f"  - {result.step_id}: {status}; error={error or 'none'}")
    rows.append("")
    return rows


def _route_sweep_details(state: object) -> list[str]:
    route_rows = _route_sweep_rows(state)
    if not route_rows:
        return []
    rows = [
        "## Route Sweep Details",
        "| Route | Verdict | Validation Return | Validation Sharpe | Validation Trades | Rank/Error |",
        "|---|---|---|---|---|---|",
    ]
    for row in route_rows:
        rows.append(
            f"| {row['route']} | {row['verdict']} | {row['validation_return']} | "
            f"{row['validation_sharpe']} | {row['validation_trades']} | {row['rank_or_error']} |"
        )
    rows.append("")
    return rows


def _plan_reviews(state: object) -> list[str]:
    rows = ["## Plan Review"]
    reviews = _get(state, "plan_reviews", [])
    if not reviews:
        rows.append("- No plan review recorded.")
    for review in reviews:
        rows.append(f"- Plan {review.plan_id}")
        rows.append(f"  - Advance: {review.advance}")
        rows.append(f"  - Rationale: {review.advance_rationale}")
        for verdict in review.step_verdicts:
            rows.append(
                f"  - {verdict.get('step_id', 'n/a')}: {verdict.get('status', 'n/a')}; "
                f"error={verdict.get('error') or 'none'}"
            )
    rows.append("")
    return rows


def _critic_review(state: object) -> list[str]:
    rows = ["## Critic Review"]
    reviews = [review for group in _get(state, "critic_reviews", []) for review in group]
    if not reviews:
        rows.append("- No critic blocks recorded.")
    for review in reviews:
        rows.append(f"- {review.critic}: {review.severity_max} - {review.summary}")
    rows.append("")
    return rows


def _final_research_plan(state: object) -> list[str]:
    decision = _get(state, "decision")
    rows = ["## Final Research Plan"]
    if not decision:
        rows.append("- Decision unavailable.")
    else:
        rows.extend(
            [
                f"- Final label: {decision.final_label}",
                f"- Confidence: {decision.confidence:.2f}",
                f"- Rationale: {decision.rationale}",
            ]
        )
    rows.append("")
    return rows


def _invalidation_and_next_actions(state: object) -> list[str]:
    decision = _get(state, "decision")
    rows = ["## Invalidation And Next Actions"]
    if decision and decision.dissent_log:
        rows.extend(f"- Watch: {item}" for item in decision.dissent_log)
    else:
        rows.append("- Re-run council after the next data refresh or material market move.")
    rows.append("")
    return rows


def _missing_evidence(state: object) -> list[str]:
    missing = _missing_evidence_rows(state)
    rows = ["## Missing Evidence"]
    if not missing:
        rows.append("- None recorded.")
    for item in missing:
        rows.append(f"- {item['scope']}/{item['subject']}: {item['field']} ({item['severity']})")
    rows.append("")
    return rows


def _execution_display_status(result: object) -> tuple[str, str | None]:
    status = _mapping_get(result, "status")
    error = _mapping_get(result, "error")
    if _mapping_get(result, "step_id") == "coder_quant_shortlist_sweep" and status == "success":
        for output in _mapping_get(result, "outputs", []) or []:
            if not isinstance(output, dict):
                continue
            routes_tested = output.get("routes_tested")
            routes_untestable = output.get("routes_untestable")
            no_ranked_routes = not output.get("ranked_options")
            has_untestable = bool(output.get("untestable"))
            if routes_tested == 0 and (routes_untestable or has_untestable or no_ranked_routes):
                return "degraded", "quant sweep produced no testable routes"
    return str(status), error


def _missing_evidence_rows(state: object) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    pack = _get(state, "evidence_pack")
    for item in (pack.missing_evidence if pack else []) or []:
        rows.append(
            {
                "scope": _display(item.scope),
                "subject": _display(item.subject),
                "field": _display(item.field),
                "severity": _display(item.severity),
            }
        )
    critic_rows = _critic_missing_evidence_rows(state)
    for row in critic_rows:
        if row not in rows:
            rows.append(row)
    if critic_rows:
        return rows
    for agent, finding in (_get(state, "specialist_findings", {}) or {}).items():
        if agent not in {"technical", "fno_risk", "fundamental", "catalyst"}:
            continue
        if getattr(finding, "candidates", None):
            continue
        row = {"scope": str(agent), "subject": "council", "field": "specialist_confirmation", "severity": "warn"}
        if row not in rows:
            rows.append(row)
    return rows


def _critic_missing_evidence_rows(state: object) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for review_group in (_get(state, "critic_reviews", []) or []):
        for review in review_group:
            if _mapping_get(review, "critic") != "evidence":
                continue
            for finding in _mapping_get(review, "findings", []) or []:
                finding_id = _display(_mapping_get(finding, "finding_id"))
                if not finding_id.startswith("evidence_") or "_confirmation_" not in finding_id:
                    continue
                target = _mapping_get(finding, "target", {}) or {}
                subject = _mapping_get(target, "id")
                if not subject:
                    continue
                scope, field = _scope_and_field_from_evidence_finding(finding_id)
                row = {
                    "scope": scope,
                    "subject": _display(subject),
                    "field": field,
                    "severity": _display(_mapping_get(finding, "severity", "warn")),
                }
                if row not in rows:
                    rows.append(row)
    return rows


def _scope_and_field_from_evidence_finding(finding_id: str) -> tuple[str, str]:
    body = finding_id.removeprefix("evidence_")
    raw_scope = body.split("_confirmation_", 1)[0]
    scope = {"fno": "fno_risk"}.get(raw_scope, raw_scope)
    return scope, f"{raw_scope}_confirmation"


def _route_sweep_rows(state: object) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for plan_results in (_get(state, "execution_results", {}) or {}).values():
        result = _mapping_get(plan_results, "coder_quant_shortlist_sweep")
        if not result:
            continue
        for output in _mapping_get(result, "outputs", []) or []:
            if not isinstance(output, dict):
                continue
            for option in output.get("ranked_options") or []:
                request = option.get("request") or {}
                result_payload = option.get("result") or {}
                validation = ((result_payload.get("metrics") or {}).get("splits") or {}).get("validation") or {}
                rows.append(
                    {
                        "route": _route_from_request(request),
                        "verdict": _display(result_payload.get("verdict")),
                        "validation_return": _display(validation.get("return_pct")),
                        "validation_sharpe": _display(validation.get("sharpe")),
                        "validation_trades": _display(validation.get("trade_count")),
                        "rank_or_error": _display(option.get("rank_score")),
                    }
                )
            for item in output.get("untestable") or []:
                rows.append(
                    {
                        "route": _route_from_request(item.get("request") or {}),
                        "verdict": "UNTESTABLE",
                        "validation_return": "n/a",
                        "validation_sharpe": "n/a",
                        "validation_trades": "n/a",
                        "rank_or_error": _display(item.get("error")),
                    }
                )
    return rows


def _route_from_request(request: dict[str, Any]) -> str:
    family = request.get("strategy_family")
    horizons = request.get("allowed_horizons") or []
    horizon = horizons[0] if horizons else None
    if family and horizon:
        return f"{family}/{horizon}d"
    return _display(family)


def _section(state: object, name: str) -> dict[str, Any]:
    pack = _get(state, "evidence_pack")
    if not pack:
        return {}
    return pack.sections.get(name, {})


def _dict_bullets(payload: dict[str, Any]) -> list[str]:
    return [f"- {key}: {value}" for key, value in payload.items()]


def _quant_route(quant: dict[str, Any]) -> str:
    family = quant.get("strategy_family")
    horizon = quant.get("horizon_days")
    if family and horizon:
        return f"{family}/{horizon}d"
    return "n/a"


def _symbol_contribution(quant: dict[str, Any]) -> str:
    attribution = quant.get("symbol_attribution") or {}
    return_pct = attribution.get("validation_return_pct")
    trades = attribution.get("validation_trade_count")
    if return_pct is None and trades is None:
        return "n/a"
    return f"{return_pct if return_pct is not None else 'n/a'} / {trades if trades is not None else 'n/a'} trades"


def _score_driver_text(components: dict[str, Any]) -> str:
    if not components:
        return "no score breakdown recorded."
    fields: list[str] = []
    if components.get("sector_rank") is not None:
        fields.append(f"sector rank #{_format_number(components['sector_rank'])}")
    if components.get("sector_score") is not None:
        fields.append(f"sector score {_format_number(components['sector_score'])}")
    if components.get("supporting_agents") is not None:
        fields.append(f"agents {components['supporting_agents']}")
    if components.get("supporting_branches") is not None:
        fields.append(f"branches {components['supporting_branches']}")
    if components.get("quant_verdict"):
        fields.append(f"quant {components['quant_verdict']}")
    if components.get("quant_route_verdict") and components.get("quant_route_verdict") != components.get("quant_verdict"):
        fields.append(f"route {components['quant_route_verdict']}")
    if components.get("quant_validation_return") is not None:
        fields.append(f"validation {_format_signed_pct(components['quant_validation_return'])}")
    if components.get("quant_symbol_return") is not None:
        fields.append(f"symbol {_format_signed_pct(components['quant_symbol_return'])}")
    if components.get("risk_count") is not None:
        fields.append(f"risks {components['risk_count']}")
    return ", ".join(fields) if fields else "no score breakdown recorded."


def _format_signed_pct(value: Any) -> str:
    number = _float_or_none(value)
    if number is None:
        return "n/a"
    sign = "+" if number > 0 else ""
    return f"{sign}{_format_number(number)}%"


def _format_number(value: Any) -> str:
    number = _float_or_none(value)
    if number is None:
        return str(value)
    if number.is_integer():
        return str(int(number))
    return f"{number:.2f}".rstrip("0").rstrip(".")


def _display(value: Any) -> str:
    if value is None or value == "":
        return "n/a"
    if isinstance(value, float):
        return _format_number(value)
    return str(value)


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _get(obj: object, name: str, default: Any = None) -> Any:
    return getattr(obj, name, default)


def _mapping_get(payload: object, key: str, default: Any = None) -> Any:
    if isinstance(payload, dict):
        return payload.get(key, default)
    return getattr(payload, key, default)
