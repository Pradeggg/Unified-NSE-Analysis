"""Market state / Evidence Pack state handler."""

from __future__ import annotations

from terminal.research_council.evidence_pack_builder import build_research_evidence_pack, build_sector_opportunity_evidence_pack
from terminal.research_council.report_review import build_report_review_evidence_pack
from terminal.research_council.schemas import CouncilState


def run(state: CouncilState) -> CouncilState:
    if state.flags.get("dry_run"):
        return state
    if state.mode == "report_review":
        pack = build_report_review_evidence_pack(
            report_path=_report_path(state),
            as_of=state.created_at.date(),
        )
        data = state.to_dict()
        data["evidence_pack_id"] = pack.pack_id
        data["evidence_pack"] = pack.to_dict()
        return CouncilState.from_dict(data)
    if state.mode == "sector_opportunity":
        pack = build_sector_opportunity_evidence_pack(
            sector=_sector_from_route(state),
            as_of=state.steward_verdict.as_of if state.steward_verdict else state.created_at.date(),
            universe_filter=state.universe_filter,
            steward_verdict=state.steward_verdict,
        )
        data = state.to_dict()
        data["evidence_pack_id"] = pack.pack_id
        data["evidence_pack"] = pack.to_dict()
        return CouncilState.from_dict(data)
    pack = build_research_evidence_pack(
        mode=state.mode,
        as_of=state.steward_verdict.as_of if state.steward_verdict else state.created_at.date(),
        universe_filter=state.universe_filter,
        symbols=state.symbols,
        steward_verdict=state.steward_verdict,
    )
    data = state.to_dict()
    data["evidence_pack_id"] = pack.pack_id
    data["evidence_pack"] = pack.to_dict()
    return CouncilState.from_dict(data)


def _report_path(state: CouncilState) -> str:
    path = state.flags.get("report_path") or state.flags.get("file") or state.flags.get("path")
    if path:
        return str(path)
    tokens = state.objective.split()
    for idx, token in enumerate(tokens):
        if token in {"--file", "--path", "--report"} and idx + 1 < len(tokens):
            return tokens[idx + 1]
    raise ValueError("report_review mode requires report_path, --file, --path, or --report")


def _sector_from_route(state: CouncilState) -> str:
    route_decision = state.route_decision or {}
    if route_decision.get("sector"):
        return str(route_decision["sector"])
    return state.symbols[0] if state.symbols else state.objective
