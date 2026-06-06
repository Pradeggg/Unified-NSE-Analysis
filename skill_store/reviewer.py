from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .config import GenerationConfig, load_generation_config


@dataclass(frozen=True)
class ReviewDecision:
    status: str
    findings: list[str]
    rationale: str = ""


def deterministic_review(card: dict[str, Any], findings: list[str]) -> ReviewDecision:
    return ReviewDecision(
        status="needs_heal" if findings else "pass",
        findings=list(findings),
        rationale="Static audit and test findings drive deterministic review.",
    )


def llm_review_card(
    card: dict[str, Any],
    findings: list[str],
    *,
    config: GenerationConfig | None = None,
) -> ReviewDecision:
    from openai import OpenAI

    cfg = config or load_generation_config()
    client = OpenAI()
    prompt = {
        "task": "Review an untrusted generated Agent Adda skill card.",
        "allowed_statuses": ["pass", "needs_heal", "reject"],
        "rules": [
            "Return strict JSON with keys: status, findings, rationale.",
            "Use needs_heal when issues look repairable.",
            "Use reject for unsafe intent, broker/order automation, or repeated unfixable schema mismatch.",
            "Do not approve cards with unresolved static audit or test findings.",
        ],
        "card": card,
        "findings": findings,
    }
    response = client.responses.create(
        model=cfg.model,
        input=[
            {"role": "system", "content": "You are a strict reviewer for generated market-intelligence skills."},
            {"role": "user", "content": json.dumps(prompt, default=str)},
        ],
        text={"format": {"type": "json_object"}},
    )
    payload = json.loads(getattr(response, "output_text", "") or "{}")
    status = str(payload.get("status") or "reject")
    if status not in {"pass", "needs_heal", "reject"}:
        status = "reject"
    raw_findings = payload.get("findings") or findings
    return ReviewDecision(
        status=status,
        findings=[str(item) for item in raw_findings],
        rationale=str(payload.get("rationale") or ""),
    )
