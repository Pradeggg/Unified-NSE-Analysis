"""Base classes for Research Council critics."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from terminal.research_council.schemas import CriticFinding, CriticReview


SEVERITY_RANK = {"info": 0, "warn": 1, "block": 2}


class CriticValidationError(ValueError):
    pass


class Critic(ABC):
    name = "base"

    def review(self, state: object) -> CriticReview:
        return self.validate_output(self.run_deterministic(state), state)

    @abstractmethod
    def run_deterministic(self, state: object) -> CriticReview | dict[str, Any]:
        raise NotImplementedError

    def validate_output(self, payload: CriticReview | dict[str, Any], state: object) -> CriticReview:
        review = payload if isinstance(payload, CriticReview) else CriticReview.from_dict(payload)
        if review.critic != self.name:
            raise CriticValidationError(f"{self.name} output critic mismatch: {review.critic}")
        expected = _severity_max(review.findings)
        if review.severity_max != expected:
            raise CriticValidationError(f"{self.name} severity_max {review.severity_max} != {expected}")
        return review

    def make_review(self, state: object, findings: list[CriticFinding], *, summary: str = "") -> CriticReview:
        iteration = _iteration(state)
        return CriticReview(
            review_id=f"{self.name}_{getattr(state, 'run_id', 'run')}_{iteration}",
            critic=self.name,
            run_id=getattr(state, "run_id", "run"),
            iteration=iteration,
            findings=findings,
            severity_max=_severity_max(findings),
            summary=summary,
        )


def finding(
    *,
    finding_id: str,
    severity: str,
    target: dict[str, str],
    description: str,
    recommendation: str,
) -> CriticFinding:
    return CriticFinding(
        finding_id=finding_id,
        severity=severity,  # type: ignore[arg-type]
        target=target,
        description=description,
        recommendation=recommendation,
    )


def _severity_max(findings: list[CriticFinding]) -> str:
    severity = "info"
    for item in findings:
        if SEVERITY_RANK[item.severity] > SEVERITY_RANK[severity]:
            severity = item.severity
    return severity


def _iteration(state: object) -> int:
    plans = getattr(state, "plans", []) or []
    return int(plans[-1].iteration) if plans else 0
