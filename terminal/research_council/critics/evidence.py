"""Evidence-support critic for final claims."""

from __future__ import annotations

from terminal.research_council.critics.base import Critic, finding


class EvidenceCritic(Critic):
    name = "evidence"

    def run_deterministic(self, state):
        decision = getattr(state, "decision", None)
        findings = []
        if not decision:
            return self.make_review(state, findings, summary="No decision to review.")
        specialist_findings = getattr(state, "specialist_findings", {}) or {}
        for candidate in decision.candidates:
            symbol = str(candidate.get("symbol") or "unknown")
            if (candidate.get("quant_sweep") or {}).get("verdict") == "SUPPORTED":
                findings.extend(_confirmation_findings(symbol, candidate, specialist_findings, reason="Quant is supported"))
            elif _is_sector_only_candidate(candidate):
                findings.extend(_confirmation_findings(symbol, candidate, specialist_findings, reason="Candidate is sector-only"))
            if candidate.get("fno_claim") and not _supports_symbol(specialist_findings.get("fno_risk"), symbol):
                findings.append(
                    finding(
                        finding_id=f"evidence_fno_{symbol}",
                        severity="block",
                        target={"kind": "candidate", "id": symbol},
                        description="F&O claim is not supported by F&O evidence.",
                        recommendation="Remove F&O claim or add source-backed derivatives evidence.",
                    )
                )
            if candidate.get("fundamental_claim") and not _supports_symbol(specialist_findings.get("fundamental"), symbol):
                findings.append(
                    finding(
                        finding_id=f"evidence_fundamental_{symbol}",
                        severity="block",
                        target={"kind": "candidate", "id": symbol},
                        description="Fundamental claim is not supported by fundamental evidence.",
                        recommendation="Remove fundamental claim or add source-backed fundamentals.",
                    )
                )
            if candidate.get("catalyst_claim") and not _supports_symbol(specialist_findings.get("catalyst"), symbol):
                findings.append(
                    finding(
                        finding_id=f"evidence_catalyst_{symbol}",
                        severity="block",
                        target={"kind": "candidate", "id": symbol},
                        description="Catalyst claim is not supported by catalyst evidence.",
                        recommendation="Remove catalyst claim or add source-backed catalyst evidence.",
                    )
                )
        return self.make_review(state, findings, summary=f"{len(findings)} evidence findings.")


def _supports_symbol(finding, symbol: str) -> bool:
    return bool(finding and symbol in finding.candidates)


def _is_sector_only_candidate(candidate: dict) -> bool:
    agents = set(candidate.get("supporting_agents") or [])
    branches = set(candidate.get("supporting_branches") or [])
    branch = candidate.get("supporting_branch")
    if branch:
        branches.add(branch)
    return bool((agents or branches) and agents <= {"sector_rotation"} and branches <= {"sector_rotation"})


def _confirmation_findings(symbol: str, candidate: dict, specialist_findings: dict, *, reason: str) -> list:
    findings = []
    checks = (
        ("technical", "technical confirmation", "technical setup evidence"),
        ("fno_risk", "F&O confirmation", "derivatives positioning evidence"),
        ("fundamental", "fundamental confirmation", "fundamental quality evidence"),
        ("catalyst", "catalyst confirmation", "catalyst or event evidence"),
    )
    supporting_agents = set(candidate.get("supporting_agents") or [])
    for agent_name, label, recommendation in checks:
        agent_finding = specialist_findings.get(agent_name)
        supported = agent_name in supporting_agents or _supports_symbol(agent_finding, symbol)
        if supported:
            continue
        findings.append(
            finding(
                finding_id=f"evidence_{agent_name.replace('_risk', '')}_confirmation_{symbol}",
                severity="warn",
                target={"kind": "candidate", "id": symbol},
                description=f"{reason}, but {label} is not yet source-backed for {symbol}.",
                recommendation=f"Keep as WATCHLIST until {recommendation} confirms or explicitly mark it unavailable.",
            )
        )
    return findings
