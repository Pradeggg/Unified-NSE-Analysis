"""First-class confidence scoring + clarification gate (PG 2026-05-22).

A small, dependency-light module that lets every stage of Agent Adda's
pipeline emit a structured ``ConfidenceScore`` and, when confidence is
low, surface a non-blocking clarification panel to the user before the
stage proceeds with its best guess.

Three pipeline stages currently emit confidence:

* **intent**     — the freeform MTF / slash-command pre-routers in
  :mod:`nse_agent` (e.g. ``_detect_mtf_intent``). Conflicts like
  "bullish ... for short" lower the score so the clarification gate
  warns the user instead of silently flipping direction.

* **plan**       — :func:`terminal.agent._build_market_situation_assessment_plan`
  attaches a confidence based on how many trigger families fired and
  whether typo-tolerant routes were used.

* **synthesis**  — a post-hoc heuristic (:func:`score_synthesis`) reads
  the final assistant text and downgrades confidence when hedge
  density, stale-data markers, or "data unavailable" phrases dominate.

The clarification gate is intentionally **non-blocking**: it prints
the best guess + the top alternatives + the reason for low confidence
and lets the user re-prompt if the chosen path was wrong. This avoids
adding a synchronous prompt-input dependency to the agent loop while
still giving the user the option to course-correct.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Optional


# Thresholds used across stages. Anything below CLARIFY_THRESHOLD is
# surfaced to the user via the clarification gate.
HIGH: float = 0.85
MEDIUM: float = 0.65
LOW: float = 0.40
CLARIFY_THRESHOLD: float = 0.65


def _band(score: float) -> str:
    if score >= HIGH:
        return "high"
    if score >= MEDIUM:
        return "medium"
    if score >= LOW:
        return "low"
    return "very_low"


@dataclass
class ConfidenceScore:
    """Structured confidence carrier.

    Attributes:
        score:        0.0 – 1.0
        stage:        ``intent`` | ``plan`` | ``synthesis``
        decision:     short string describing what the stage chose
                      (e.g. ``"/mtf scan NIFTY 500 bullish"``)
        reasons:      human-readable reasons for the score
                      (especially for the *low* cases)
        signals:      raw signal dict, useful for tests / logs
        alternatives: other interpretations the user could pick
    """

    score: float
    stage: str
    decision: str = ""
    reasons: list[str] = field(default_factory=list)
    signals: dict[str, Any] = field(default_factory=dict)
    alternatives: list[str] = field(default_factory=list)

    @property
    def band(self) -> str:
        return _band(self.score)

    @property
    def needs_clarification(self) -> bool:
        return self.score < CLARIFY_THRESHOLD

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": round(float(self.score), 3),
            "band": self.band,
            "stage": self.stage,
            "decision": self.decision,
            "reasons": list(self.reasons),
            "signals": dict(self.signals),
            "alternatives": list(self.alternatives),
        }


# ─────────────────────────────────────────────────────────────────────
# Stage scorers
# ─────────────────────────────────────────────────────────────────────


def score_intent(
    *,
    decision: str,
    has_direction_conflict: bool = False,
    direction_explicit: bool = False,
    has_index_or_symbol: bool = False,
    multiple_symbol_candidates: bool = False,
    typo_route: bool = False,
    extra_signals: Optional[dict[str, Any]] = None,
    alternatives: Optional[Iterable[str]] = None,
) -> ConfidenceScore:
    """Score the freeform-prompt → slash-command rewrite step.

    Starts at 1.0 and deducts per ambiguity signal. Reasons are recorded
    so the clarification panel can explain *why* confidence dropped.
    """
    score = 1.0
    reasons: list[str] = []

    if has_direction_conflict:
        score -= 0.40
        reasons.append(
            "Prompt mixes bullish and bearish cues — direction is ambiguous."
        )
    if not direction_explicit:
        score -= 0.10
        reasons.append("No explicit direction (bullish/bearish) — defaulted.")
    if not has_index_or_symbol:
        score -= 0.20
        reasons.append("No index or symbol detected — defaulted to NIFTY 50.")
    if multiple_symbol_candidates:
        score -= 0.15
        reasons.append("Multiple plausible symbols in prompt.")
    if typo_route:
        score -= 0.05
        reasons.append("Matched via typo-tolerant alias.")

    score = max(0.0, min(1.0, score))
    return ConfidenceScore(
        score=score,
        stage="intent",
        decision=decision,
        reasons=reasons,
        signals=dict(extra_signals or {}),
        alternatives=list(alternatives or []),
    )


def score_plan(
    *,
    decision: str,
    trigger_count: int,
    has_mtf_or_recommendation: bool,
    has_market_word: bool,
    typo_route: bool = False,
    extra_signals: Optional[dict[str, Any]] = None,
    alternatives: Optional[Iterable[str]] = None,
) -> ConfidenceScore:
    """Score the situation-assessment plan builder.

    Confidence rises with the number of distinct trigger families that
    fired (status, breadth, movers, flows, news, mtf, recommendation)
    and drops when the plan was inferred from a single fuzzy trigger.
    """
    # A single clear trigger ("show me top gainers") is a high-confidence
    # ask — the plan addresses exactly one intent without ambiguity.
    # Confidence rises with breadth (multi-faceted asks), and only drops
    # below the clarification threshold when no trigger fires at all
    # (which usually means the plan shouldn't have been built).
    if trigger_count >= 3:
        score = 0.95
    elif trigger_count == 2:
        score = 0.90
    elif trigger_count == 1:
        score = 0.85
    else:
        score = 0.40

    reasons: list[str] = []
    if has_mtf_or_recommendation and not has_market_word:
        # Loosened gate fires here — flag it so the user can confirm.
        score -= 0.10
        reasons.append(
            "MTF/recommendation intent without an explicit market/index word."
        )
    if typo_route:
        score -= 0.10
        reasons.append("Plan inferred from a typo-tolerant alias match.")
    if trigger_count == 0:
        reasons.append("No clear trigger family fired — plan may be off-target.")

    score = max(0.0, min(1.0, score))
    return ConfidenceScore(
        score=score,
        stage="plan",
        decision=decision,
        reasons=reasons,
        signals=dict(extra_signals or {}, trigger_count=trigger_count),
        alternatives=list(alternatives or []),
    )


# Hedge / uncertainty markers used by ``score_synthesis``.
_HEDGE_TERMS = (
    "uncertain", "unclear", "ambiguous", "possibly", "maybe",
    "might be", "could be", "appears to", "seems to", "likely",
    "not entirely sure", "hard to tell", "i'm not certain",
)
_STALE_TERMS = (
    "data unavailable", "no data", "could not fetch", "fetch failed",
    "data is stale", "stale data", "missing data", "tool error",
    "fallback", "skipped due to error",
)
_NO_RESULT_TERMS = (
    "no matches", "empty universe", "no candidates", "no results found",
)


def score_synthesis(
    text: str,
    *,
    decision: str = "final-answer",
    extra_signals: Optional[dict[str, Any]] = None,
) -> ConfidenceScore:
    """Score the final synthesized answer using a small heuristic.

    The heuristic counts hedge phrases, stale-data markers and "no
    result" phrases. Each lowers confidence. The threshold for
    surfacing a clarification is :data:`CLARIFY_THRESHOLD` (0.65).

    This is intentionally simple — it complements, rather than
    replaces, the structured per-task error reporting that the
    situation assessor already emits via the SOURCE TRAIL line.
    """
    if not isinstance(text, str) or not text.strip():
        return ConfidenceScore(
            score=0.30,
            stage="synthesis",
            decision=decision,
            reasons=["Empty synthesis output."],
            signals=dict(extra_signals or {}),
        )
    # Very short outputs (e.g. "ok", "done") are suspect — they almost
    # never represent a complete grounded answer for a market query.
    if len(text.strip()) < 30:
        return ConfidenceScore(
            score=0.35,
            stage="synthesis",
            decision=decision,
            reasons=[f"Synthesis output is unusually short ({len(text.strip())} chars)."],
            signals=dict(extra_signals or {}, length=len(text)),
        )

    lower = text.lower()
    hedge_hits = sum(1 for term in _HEDGE_TERMS if term in lower)
    stale_hits = sum(1 for term in _STALE_TERMS if term in lower)
    empty_hits = sum(1 for term in _NO_RESULT_TERMS if term in lower)

    score = 0.95
    reasons: list[str] = []
    if hedge_hits >= 5:
        score -= 0.35
        reasons.append(f"Very high hedge density ({hedge_hits} hedge phrases).")
    elif hedge_hits >= 3:
        score -= 0.25
        reasons.append(f"High hedge density ({hedge_hits} hedge phrases).")
    elif hedge_hits == 2:
        score -= 0.10
        reasons.append("Multiple hedge phrases in the output.")
    if stale_hits:
        score -= 0.20
        reasons.append(
            f"Stale-data / tool-error markers present ({stale_hits})."
        )
    if empty_hits:
        score -= 0.15
        reasons.append("Answer notes that no results were found.")

    score = max(0.0, min(1.0, score))
    return ConfidenceScore(
        score=score,
        stage="synthesis",
        decision=decision,
        reasons=reasons,
        signals=dict(
            extra_signals or {},
            hedge_hits=hedge_hits,
            stale_hits=stale_hits,
            empty_hits=empty_hits,
            length=len(text),
        ),
    )


# ─────────────────────────────────────────────────────────────────────
# Non-blocking clarification gate
# ─────────────────────────────────────────────────────────────────────


def render_clarification(
    score: ConfidenceScore,
    console: Any = None,
    *,
    force: bool = False,
) -> bool:
    """Render the clarification panel if confidence is below threshold.

    Returns ``True`` if the panel was rendered (caller may want to
    surface this in logs), ``False`` otherwise. Never blocks — always
    proceeds with the stage's best guess.

    The renderer is defensive: if rich is unavailable or the console
    crashes (e.g. inside a non-TTY pipe), it falls back to a plain
    ``print`` so the warning is never lost.
    """
    if not force and not score.needs_clarification:
        return False

    if console is None:  # pragma: no cover — agent always passes one
        try:
            from rich.console import Console as _Console

            console = _Console()
        except Exception:
            console = None

    lines: list[str] = []
    lines.append(
        f"[bold]Stage:[/bold] {score.stage}   "
        f"[bold]Confidence:[/bold] {score.score:.0%} "
        f"([{'red' if score.band in ('low','very_low') else 'yellow'}]{score.band}[/])"
    )
    if score.decision:
        lines.append(f"[bold]Best guess:[/bold] {score.decision}")
    if score.reasons:
        lines.append("[bold]Why low confidence:[/bold]")
        for r in score.reasons:
            lines.append(f"  • {r}")
    if score.alternatives:
        lines.append("[bold]Possible alternatives:[/bold]")
        for i, alt in enumerate(score.alternatives, 1):
            lines.append(f"  {i}. {alt}")
    lines.append(
        "[dim]Proceeding with the best guess. Re-prompt explicitly "
        "(e.g. add 'bullish' / 'bearish', or use the slash form) to override.[/dim]"
    )

    body = "\n".join(lines)
    try:
        from rich.panel import Panel

        console.print(
            Panel(
                body,
                title="⚠ Clarification — low confidence",
                border_style="yellow",
            )
        )
        return True
    except Exception:
        # Plain text fallback — strip rich markup tokens.
        import re

        plain = re.sub(r"\[/?[^\]]+\]", "", body)
        print("--- Clarification (low confidence) ---")
        print(plain)
        print("---------------------------------------")
        return True


__all__ = [
    "HIGH",
    "MEDIUM",
    "LOW",
    "CLARIFY_THRESHOLD",
    "ConfidenceScore",
    "score_intent",
    "score_plan",
    "score_synthesis",
    "render_clarification",
]
