"""Risk critic for concentration, liquidity, drawdown, and event risk."""

from __future__ import annotations

from terminal.research_council.critics.base import Critic, finding


class RiskCritic(Critic):
    name = "risk"

    def run_deterministic(self, state):
        findings = []
        decision = getattr(state, "decision", None)
        if decision:
            for candidate in decision.candidates:
                symbol = str(candidate.get("symbol") or "unknown")
                if float(candidate.get("position_weight_pct") or 0) > 20:
                    findings.append(
                        finding(
                            finding_id=f"risk_concentration_{symbol}",
                            severity="block",
                            target={"kind": "candidate", "id": symbol},
                            description="Candidate exceeds concentration risk limits.",
                            recommendation="Cap research-book exposure before advancing.",
                        )
                    )
                liquidity = candidate.get("liquidity_value_cr")
                if liquidity is not None and float(liquidity) < 5:
                    findings.append(
                        finding(
                            finding_id=f"risk_liquidity_{symbol}",
                            severity="warn",
                            target={"kind": "candidate", "id": symbol},
                            description="Candidate has low liquidity.",
                            recommendation="Reduce size assumptions or require manual review.",
                        )
                    )
                if float(candidate.get("max_drawdown_pct") or 0) < -20:
                    findings.append(
                        finding(
                            finding_id=f"risk_drawdown_{symbol}",
                            severity="block",
                            target={"kind": "candidate", "id": symbol},
                            description="Candidate drawdown risk exceeds tolerance.",
                            recommendation="Downgrade or require a tighter invalidation plan.",
                        )
                    )
        catalyst = (getattr(state, "specialist_findings", {}) or {}).get("catalyst")
        if catalyst and "high-impact event within 5 trading days" in catalyst.risks:
            findings.append(
                finding(
                    finding_id="risk_event_catalyst",
                    severity="block",
                    target={"kind": "agent_finding", "id": "catalyst"},
                    description="High-impact event risk is unresolved.",
                    recommendation="Use WAIT_FOR_CONFIRMATION until event risk clears.",
                )
            )
        return self.make_review(state, findings, summary=f"{len(findings)} risk findings.")
