"""Specialist agent fan-out state."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

from terminal.research_council.agents.catalyst import CatalystAgent
from terminal.research_council.agents.fno_risk import FnoRiskAgent
from terminal.research_council.agents.fundamental import FundamentalAgent
from terminal.research_council.agents.macro_regime import MacroRegimeAgent
from terminal.research_council.agents.minervini import MinerviniAgent
from terminal.research_council.agents.sector_rotation import SectorRotationAgent
from terminal.research_council.agents.technical import TechnicalAgent
from terminal.research_council.persistence import save_agent_findings
from terminal.research_council.schemas import AgentFinding, CouncilState

DEFAULT_AGENTS = (
    MacroRegimeAgent(),
    SectorRotationAgent(),
    TechnicalAgent(),
    MinerviniAgent(),
    FundamentalAgent(),
    FnoRiskAgent(),
    CatalystAgent(),
)


def run(state: CouncilState) -> CouncilState:
    if state.flags.get("dry_run"):
        return state
    if state.mode == "report_review":
        return state
    evidence = state.evidence_pack.sections if state.evidence_pack else {}
    findings: dict[str, AgentFinding] = {}
    failures: list[dict[str, str]] = []
    with ThreadPoolExecutor(max_workers=len(DEFAULT_AGENTS) or 1) as pool:
        future_to_agent = {pool.submit(agent.run, evidence, None): agent for agent in DEFAULT_AGENTS}
        for future in as_completed(future_to_agent):
            agent = future_to_agent[future]
            try:
                finding = future.result()
                findings[finding.agent] = finding
            except Exception as exc:
                failures.append({"agent": getattr(agent, "name", "unknown"), "error": str(exc)})
    if findings:
        save_agent_findings(list(findings.values()), run_id=state.run_id)
    data = state.to_dict()
    data["specialist_findings"] = {name: finding.to_dict() for name, finding in findings.items()}
    if failures:
        flags = dict(data.get("flags") or {})
        flags["specialist_failures"] = failures
        data["flags"] = flags
    return CouncilState.from_dict(data)
