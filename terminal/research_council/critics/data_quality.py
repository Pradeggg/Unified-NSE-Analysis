"""Data quality critic."""

from __future__ import annotations

from terminal.research_council.critics.base import Critic, finding


class DataQualityCritic(Critic):
    name = "data_quality"

    def run_deterministic(self, state):
        findings = []
        pack = getattr(state, "evidence_pack", None)
        if pack:
            for item in pack.missing_evidence:
                findings.append(
                    finding(
                        finding_id=f"data_quality_{item.field}",
                        severity=item.severity,
                        target={"kind": "missing_evidence", "id": item.field},
                        description=f"Missing or stale evidence: {item.field}",
                        recommendation="Refresh data or downgrade claims depending on severity.",
                    )
                )
            report_review = pack.sections.get("report_review") if isinstance(pack.sections, dict) else None
            if report_review:
                for item in report_review.get("findings") or []:
                    findings.append(
                        finding(
                            finding_id=f"report_review_{item.get('code', 'finding')}_{item.get('line', 'unknown')}",
                            severity=item.get("severity", "warn"),
                            target={
                                "kind": "report_line",
                                "id": str(report_review.get("path") or "report"),
                                "line": str(item.get("line", "")),
                            },
                            description=str(item.get("message") or "Report review finding"),
                            recommendation=str(item.get("remediation") or "Review and regenerate report with complete evidence."),
                        )
                    )
        decision = getattr(state, "decision", None)
        if decision and decision.candidates and (not pack or not pack.source_trail):
            findings.append(
                finding(
                    finding_id="data_quality_source_trail",
                    severity="block",
                    target={"kind": "decision", "id": "source_trail"},
                    description="Decision candidates exist without source-trail evidence.",
                    recommendation="Attach source trail before allowing a research-long conclusion.",
                )
            )
        return self.make_review(state, findings, summary=f"{len(findings)} data-quality findings.")
