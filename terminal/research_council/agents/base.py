"""Base classes for Research Council agents."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from terminal.research_council.schemas import AgentFinding


class AgentValidationError(ValueError):
    pass


class Agent(ABC):
    name = "base"

    def run(self, evidence: dict, mode_profile: object | None = None) -> AgentFinding:
        payload = self.run_deterministic(evidence, mode_profile)
        return self.validate_output(payload)

    @abstractmethod
    def run_deterministic(self, evidence: dict, mode_profile: object | None = None) -> dict:
        raise NotImplementedError

    @abstractmethod
    def format_evidence_for_llm(self, evidence: dict, mode_profile: object | None = None) -> str:
        raise NotImplementedError

    def validate_output(self, payload: dict[str, Any] | AgentFinding) -> AgentFinding:
        if isinstance(payload, AgentFinding):
            finding = payload
        else:
            required = ("finding_id", "agent", "stance", "confidence", "thesis")
            missing = [key for key in required if key not in payload]
            if missing:
                raise AgentValidationError(f"{self.name} output missing required fields: {', '.join(missing)}")
            finding = AgentFinding.from_dict(payload)

        if finding.agent != self.name:
            raise AgentValidationError(f"{self.name} output agent mismatch: {finding.agent}")
        if not 0 <= float(finding.confidence) <= 1:
            raise AgentValidationError(f"{self.name} confidence must be between 0 and 1")
        if not finding.thesis.strip():
            raise AgentValidationError(f"{self.name} thesis cannot be empty")
        return finding
