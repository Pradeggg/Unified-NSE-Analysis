"""Public branch deliberation state."""

from __future__ import annotations

from terminal.research_council.persistence import save_branch_summaries
from terminal.research_council.schemas import AgentFinding, BranchSummary, CouncilState


CANONICAL_BRANCHES = (
    "momentum_leadership",
    "minervini_stage2",
    "sector_rotation",
    "earnings_catalyst",
    "fno_positioning",
    "defensive_no_trade",
)


def run(state: CouncilState) -> CouncilState:
    if state.flags.get("dry_run"):
        return state
    if state.mode == "report_review":
        return state
    summaries = compose_branch_summaries(state.run_id, state.specialist_findings)
    if summaries:
        save_branch_summaries(summaries, run_id=state.run_id)
    data = state.to_dict()
    data["branch_summaries"] = [summary.to_dict() for summary in summaries]
    return CouncilState.from_dict(data)


def compose_branch_summaries(run_id: str, findings: dict[str, AgentFinding]) -> list[BranchSummary]:
    technical = findings.get("technical")
    sector = findings.get("sector_rotation")
    fundamental = findings.get("fundamental")
    branches = [
        _branch(
            run_id,
            "momentum_leadership",
            stance=_stance_from(technical),
            supporting=[technical.agent] if technical and technical.candidates else [],
            dissenting=[],
            candidates=technical.candidates if technical else [],
            risks=technical.risks if technical else ["technical evidence missing"],
            requires_quant=True,
        ),
        _branch(
            run_id,
            "minervini_stage2",
            stance="selective" if technical and technical.candidates else "wait",
            supporting=["technical"] if technical and technical.candidates else [],
            dissenting=[],
            candidates=technical.candidates if technical else [],
            risks=["requires VCP/tightness confirmation"],
            requires_quant=True,
        ),
        _branch(
            run_id,
            "sector_rotation",
            stance=_stance_from(sector),
            supporting=[sector.agent] if sector and sector.candidates else [],
            dissenting=[],
            candidates=sector.candidates if sector else [],
            risks=sector.risks if sector else ["sector evidence missing"],
        ),
        _branch(
            run_id,
            "earnings_catalyst",
            stance=_stance_from(fundamental),
            supporting=[fundamental.agent] if fundamental and fundamental.candidates else [],
            dissenting=[],
            candidates=fundamental.candidates if fundamental else [],
            risks=fundamental.risks if fundamental else ["catalyst evidence missing"],
        ),
        _branch(
            run_id,
            "fno_positioning",
            stance="wait",
            supporting=[],
            dissenting=[],
            candidates=[],
            risks=["F&O positioning branch awaits derivatives agent"],
        ),
        _branch(
            run_id,
            "defensive_no_trade",
            stance="available",
            supporting=_risk_supporters(findings),
            dissenting=_bullish_supporters(findings),
            candidates=[],
            risks=[],
        ),
    ]
    return branches


def _branch(
    run_id: str,
    branch: str,
    *,
    stance: str,
    supporting: list[str],
    dissenting: list[str],
    candidates: list[str],
    risks: list[str],
    requires_quant: bool = False,
) -> BranchSummary:
    return BranchSummary(
        summary_id=f"{run_id}_{branch}",
        branch=branch,
        stance=stance,
        supporting_agents=supporting,
        dissenting_agents=dissenting,
        candidates=_unique(candidates),
        risks=list(risks),
        requires_quant=requires_quant,
        body={
            "public_summary": f"{branch} branch generated from specialist findings.",
            "required_next_step": "validate with plan execution" if requires_quant else "review evidence trail",
        },
    )


def _stance_from(finding: AgentFinding | None) -> str:
    if not finding:
        return "unavailable"
    return finding.stance


def _risk_supporters(findings: dict[str, AgentFinding]) -> list[str]:
    return [finding.agent for finding in findings.values() if finding.risks and not finding.candidates]


def _bullish_supporters(findings: dict[str, AgentFinding]) -> list[str]:
    return [finding.agent for finding in findings.values() if finding.candidates]


def _unique(values: list[str]) -> list[str]:
    seen = set()
    out = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out
