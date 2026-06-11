from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from terminal.learning.repository import LearningRepository


@dataclass(frozen=True)
class LearningProposal:
    proposal_type: str
    title: str
    source_pattern_id: int | None
    observed_pattern: dict[str, Any]
    proposed_behavior: dict[str, Any]
    affected_surfaces: dict[str, list[str]]
    generated_test_cases: list[dict[str, Any]]
    expected_tool_calls: list[str]
    must_not_call_rules: list[str]
    acceptance_criteria: list[str]
    status: str = "proposed"

    def to_record(self) -> dict[str, Any]:
        return {
            "proposal_type": self.proposal_type,
            "title": self.title,
            "status": self.status,
            "source_pattern_id": self.source_pattern_id,
            "proposal_payload": {
                "proposal_type": self.proposal_type,
                "title": self.title,
                "observed_pattern": self.observed_pattern,
                "proposed_behavior": self.proposed_behavior,
                "affected_surfaces": self.affected_surfaces,
                "generated_test_cases": self.generated_test_cases,
                "expected_tool_calls": self.expected_tool_calls,
                "must_not_call_rules": self.must_not_call_rules,
                "acceptance_criteria": self.acceptance_criteria,
            },
        }


@dataclass(frozen=True)
class LearningProposalResult:
    proposals: list[LearningProposal]
    saved_proposal_ids: list[int] = field(default_factory=list)


def generate_learning_proposals(patterns: Iterable[Mapping[str, Any]]) -> LearningProposalResult:
    proposals = [_proposal_from_pattern(_normalize_pattern(pattern)) for pattern in patterns]
    proposals = [proposal for proposal in proposals if proposal is not None]
    proposals.sort(key=lambda item: (item.proposal_type, item.title))
    return LearningProposalResult(proposals=proposals)


def generate_and_save_learning_proposals(
    *,
    repository: Any | None = None,
    status: str = "observed",
    limit: int | None = None,
) -> LearningProposalResult:
    repo = repository or LearningRepository()
    patterns = repo.list_patterns(status=status, limit=limit)
    result = generate_learning_proposals(patterns)
    saved_ids = [int(repo.save_proposal(proposal.to_record())) for proposal in result.proposals]
    return LearningProposalResult(proposals=result.proposals, saved_proposal_ids=saved_ids)


def _proposal_from_pattern(pattern: dict[str, Any]) -> LearningProposal | None:
    label = pattern["label"]
    candidate_type = pattern["candidate_type"]
    pattern_type = pattern["pattern_type"]
    lowered = f"{pattern['pattern_key']} {label} {' '.join(pattern['examples'])}".lower()

    if candidate_type == "report_validation_proposal" or pattern_type == "repeated_report_validation_issue":
        return _report_validation_proposal(pattern)
    if pattern_type == "recurring_workflow_chain" or candidate_type == "workflow_proposal":
        return _workflow_proposal(pattern)
    if "vcp" in lowered or "breakout" in lowered or "new highs" in lowered:
        return _vcp_skill_proposal(pattern)
    if candidate_type == "route_tool_skill_candidate" or pattern_type == "repeated_llm_fallback_failure":
        return _fallback_tool_proposal(pattern)
    if pattern_type == "repeated_user_phrasing":
        return _prompt_route_proposal(pattern)
    return None


def _fallback_tool_proposal(pattern: dict[str, Any]) -> LearningProposal:
    tool_name = _extract_missing_tool(pattern["label"]) or "deterministic_evidence_tool"
    return LearningProposal(
        proposal_type="tool_proposal",
        title=f"Add deterministic coverage for {pattern['label']}",
        source_pattern_id=pattern["pattern_id"],
        observed_pattern=_observed(pattern),
        proposed_behavior={
            "summary": f"Add deterministic evidence/tool coverage for {pattern['label']} before fallback synthesis.",
            "implementation_notes": [
                "Create or expose the missing tool in the deterministic tool registry.",
                "Add route validation so the plan fails closed when mandatory evidence is unavailable.",
                "Feed collected evidence into the final synthesizer instead of generic fallback output.",
            ],
        },
        affected_surfaces={
            "routes": ["llm_driven_fallback", "situation_assessment"],
            "tools": [tool_name],
            "skills": [],
            "reports": [],
        },
        generated_test_cases=[
            {
                "name": "routes_latest_results_to_required_tool",
                "input": _first_example(pattern, "latest quarterly results analysis"),
                "assertions": [
                    f"calls {tool_name}",
                    "does not render final answer when mandatory evidence is missing",
                ],
            }
        ],
        expected_tool_calls=[tool_name],
        must_not_call_rules=[
            "Do not route this query through generic llm_driven_fallback until evidence collection succeeds.",
            "Do not synthesize a market conclusion without the mandatory result evidence.",
        ],
        acceptance_criteria=[
            f"Repeated pattern {pattern['pattern_key']} is handled by a deterministic route or tool.",
            "Tool validation exposes missing_evidence when source data is unavailable.",
            "The final response includes source trail and does not hide mandatory evidence failures.",
        ],
    )


def _vcp_skill_proposal(pattern: dict[str, Any]) -> LearningProposal:
    return LearningProposal(
        proposal_type="skill_proposal",
        title="Add VCP breakouts with fundamentals skill",
        source_pattern_id=pattern["pattern_id"],
        observed_pattern=_observed(pattern),
        proposed_behavior={
            "summary": "Create a runtime skill for VCP/new-high/breakout candidates filtered by fundamentals.",
            "implementation_notes": [
                "Use schema-aware SQL over technical setup, breakout distance, volume expansion, and fundamentals.",
                "Return ranked candidates plus a TradingView-compatible watchlist artifact.",
                "Require data freshness checks before publishing candidates.",
            ],
        },
        affected_surfaces={
            "routes": ["quality_breakouts", "watchlist_export"],
            "tools": ["run_quality_breakout_screener", "export_tradingview_watchlist"],
            "skills": ["vcp_breakouts_with_fundamentals"],
            "reports": ["stage2_buy_tradingview.txt"],
        },
        generated_test_cases=[
            {
                "name": "selects_vcp_breakout_skill_for_fundamental_breakout_prompt",
                "input": _first_example(pattern, "stocks creating new highs or VCP or breakouts with good fundamentals"),
                "assertions": [
                    "selects vcp_breakouts_with_fundamentals",
                    "exports TradingView watchlist",
                    "excludes weak-fundamental breakouts",
                ],
            }
        ],
        expected_tool_calls=["run_quality_breakout_screener", "export_tradingview_watchlist"],
        must_not_call_rules=[
            "Do not use generic top gainers without VCP, breakout, and fundamentals filters.",
            "Do not export stale candidates without data freshness validation.",
        ],
        acceptance_criteria=[
            "Repeated VCP/breakout/fundamentals asks select the dedicated skill.",
            "Output includes ranked candidates and a TradingView watchlist artifact.",
            "Candidates include technical and fundamental evidence in the source trail.",
        ],
    )


def _report_validation_proposal(pattern: dict[str, Any]) -> LearningProposal:
    reports = _list(pattern.get("artifacts")) or ["reports/latest/*.html"]
    return LearningProposal(
        proposal_type="report_validation_proposal",
        title=f"Add report validation for {pattern['label']}",
        source_pattern_id=pattern["pattern_id"],
        observed_pattern=_observed(pattern),
        proposed_behavior={
            "summary": f"Validate and heal report issue: {pattern['label']}.",
            "implementation_notes": [
                "Run link/data validation immediately after report generation.",
                "Regenerate or fail closed when validation issues remain.",
                "Persist validation evidence next to the report artifact.",
            ],
        },
        affected_surfaces={"routes": ["report_validation"], "tools": ["validate_report_links", "regenerate_report"], "skills": [], "reports": reports},
        generated_test_cases=[
            {
                "name": "blocks_report_publish_when_validation_fails",
                "input": _first_example(pattern, "open report and verify links"),
                "assertions": ["detects report issue", "regenerates or blocks publish", "records validation evidence"],
            }
        ],
        expected_tool_calls=["validate_report_links", "regenerate_report"],
        must_not_call_rules=[
            "Do not email or publish a report with failed validation.",
            "Do not silently drop broken underlying stock detail links.",
        ],
        acceptance_criteria=[
            "Report validation catches the observed issue before publish/email.",
            "Validation output lists affected report artifacts.",
            "A failed validation produces an actionable repair trail.",
        ],
    )


def _workflow_proposal(pattern: dict[str, Any]) -> LearningProposal:
    workflow = pattern["label"]
    tool_calls = _workflow_tool_calls(workflow)
    return LearningProposal(
        proposal_type="workflow_proposal",
        title=f"Automate recurring workflow {workflow}",
        source_pattern_id=pattern["pattern_id"],
        observed_pattern=_observed(pattern),
        proposed_behavior={
            "summary": f"Add a deterministic workflow route for recurring chain {workflow}.",
            "implementation_notes": [
                "Bundle the repeated actions behind an explicit command or natural-language route.",
                "Validate intermediate artifacts before advancing to the next step.",
                "Emit a concise step trace for every workflow action.",
            ],
        },
        affected_surfaces={"routes": [workflow, *tool_calls[:1]], "tools": tool_calls, "skills": [], "reports": []},
        generated_test_cases=[
            {
                "name": f"runs_{workflow}_workflow",
                "input": _workflow_input(workflow),
                "assertions": [f"calls {tool}" for tool in tool_calls],
            }
        ],
        expected_tool_calls=tool_calls,
        must_not_call_rules=[
            "Do not skip validation steps between workflow actions.",
            "Do not execute email/publish steps when required reports failed validation.",
        ],
        acceptance_criteria=[
            f"Repeated {workflow} chain is available as a deterministic route.",
            "Each step records source trail and validation status.",
            "Workflow is testable without live external side effects.",
        ],
    )


def _prompt_route_proposal(pattern: dict[str, Any]) -> LearningProposal:
    return LearningProposal(
        proposal_type="prompt_proposal",
        title=f"Improve route detection for '{pattern['label']}'",
        source_pattern_id=pattern["pattern_id"],
        observed_pattern=_observed(pattern),
        proposed_behavior={
            "summary": "Add prompt/routing examples for repeated user phrasing.",
            "implementation_notes": [
                "Add the phrase to route examples or skill input patterns.",
                "Add a routing smoke test for the observed input.",
            ],
        },
        affected_surfaces={"routes": ["situation_assessment"], "tools": [], "skills": [], "reports": []},
        generated_test_cases=[
            {
                "name": "routes_repeated_user_phrase",
                "input": _first_example(pattern, pattern["label"]),
                "assertions": ["selects a deterministic route", "does not fall through to unrelated intent"],
            }
        ],
        expected_tool_calls=[],
        must_not_call_rules=["Do not overfit this phrase so unrelated queries route to the same workflow."],
        acceptance_criteria=["Observed phrase has deterministic routing coverage and a regression test."],
    )


def _observed(pattern: dict[str, Any]) -> dict[str, Any]:
    return {
        "pattern_id": pattern["pattern_id"],
        "pattern_key": pattern["pattern_key"],
        "pattern_type": pattern["pattern_type"],
        "label": pattern["label"],
        "frequency": pattern["frequency"],
        "score": pattern["score"],
        "priority": pattern["priority"],
        "examples": pattern["examples"],
        "evidence_event_ids": pattern["evidence_event_ids"],
        "evidence_chain_ids": pattern["evidence_chain_ids"],
    }


def _normalize_pattern(pattern: Mapping[str, Any]) -> dict[str, Any]:
    payload = pattern.get("pattern_payload") if isinstance(pattern.get("pattern_payload"), Mapping) else pattern
    normalized = {
        "pattern_id": int(pattern.get("pattern_id") or payload.get("pattern_id") or 0),
        "pattern_key": str(payload.get("pattern_key") or pattern.get("pattern_key") or ""),
        "pattern_type": str(payload.get("pattern_type") or ""),
        "label": str(payload.get("label") or ""),
        "frequency": int(payload.get("frequency") or 0),
        "score": int(payload.get("score") or 0),
        "priority": str(payload.get("priority") or "medium"),
        "candidate_type": str(payload.get("candidate_type") or ""),
        "examples": _list(payload.get("examples")),
        "evidence_event_ids": _list(payload.get("evidence_event_ids")),
        "evidence_chain_ids": _list(payload.get("evidence_chain_ids")),
    }
    for key, value in payload.items():
        if key not in normalized:
            normalized[key] = value
    return normalized


def _workflow_tool_calls(workflow: str) -> list[str]:
    mapping = {
        "daily_refresh_report_review_email": ["daily_refresh", "generate_eod_reports", "validate_reports", "email_reports"],
        "scanner_to_watchlist": ["run_quality_breakout_screener", "export_tradingview_watchlist"],
        "portfolio_review_debug": ["generate_portfolio_report", "validate_report_links", "regenerate_report"],
        "report_debug_regenerate_validate": ["validate_report_links", "regenerate_report", "validate_reports"],
    }
    return mapping.get(workflow, [workflow])


def _workflow_input(workflow: str) -> str:
    mapping = {
        "daily_refresh_report_review_email": "run the daily refresh and eod reports, validate, then email",
        "scanner_to_watchlist": "get VCP breakouts with good fundamentals and export to TradingView",
        "portfolio_review_debug": "review portfolio report and fix validation issues",
    }
    return mapping.get(workflow, f"run {workflow}")


def _extract_missing_tool(label: str) -> str:
    marker = "missing required tool:"
    lowered = label.lower()
    if marker in lowered:
        return label[lowered.index(marker) + len(marker) :].strip()
    return ""


def _first_example(pattern: Mapping[str, Any], fallback: str) -> str:
    examples = _list(pattern.get("examples"))
    return str(examples[0]) if examples else fallback


def _list(value: Any) -> list[Any]:
    if value in (None, "", [], {}):
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, (tuple, set, frozenset)):
        return list(value)
    return [value]
