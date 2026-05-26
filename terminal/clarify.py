"""AA-CC-1: Ergonomic builder API for structured user clarifications.

Inspired by Claude Code's AskUserQuestion primitive. Provides a clean
developer-facing surface for constructing structured clarification
prompts without manipulating ``SituationAssessment`` /
``ClarificationQuestion`` / ``ClarificationOption`` internals directly.

Typical usage from a provider / tool::

    from terminal.clarify import AskUserQuestion, Question, Option

    ask = AskUserQuestion(
        user_is_asking="The user wants to see RELIANCE but didn't specify timeframe.",
        context_found="No prior RELIANCE context in this session.",
        source_assessment="No data yet — need to choose a fetch.",
        questions=[
            Question(
                prompt="What timeframe should I pull for RELIANCE?",
                options=[
                    Option.run_tool_plan(
                        label="A", text="EOD daily setup",
                        tools=[("get_technical_setup", {"symbol": "RELIANCE"})],
                        preview="Daily candles, EMA stack, ADX, last 30 sessions",
                    ),
                    Option.run_tool_plan(
                        label="B", text="15m intraday setup",
                        tools=[("scan_symbols_intraday", {"symbols": ["RELIANCE"], "tf": "15m"})],
                        preview="Live 15m bars, VWAP, intraday momentum",
                    ),
                    Option.answer_from_context(
                        label="C", text="Just summarize what we already know",
                        preview="Skip the fetch — answer from session memory",
                    ),
                ],
                default_label="A",
            ),
        ],
    )

    # Hand it to the agent's pending-clarification slot:
    self._pending_clarification = ask.to_assessment()

The resulting :class:`SituationAssessment` plugs into the existing
:meth:`Agent._stage_clarification_binding` pipeline unchanged — reply
matching, typo reprompt, and `bound_action` execution all reuse the
plumbing already in ``terminal.agent`` and
``terminal.situation_assessment``.

Constraints (mirror Claude Code's AskUserQuestion):
  * 1–4 questions per ``AskUserQuestion``.
  * 2–4 options per question.
  * Labels must be a contiguous alphabetic sequence starting at "A".

``Question.multi_select`` is reserved for a future phase: the schema
carries it through but ``Agent._stage_clarification_binding`` still
matches one option per turn. Setting it today is a no-op and emits a
warning at build time.
"""
from __future__ import annotations

import logging
import string
from dataclasses import dataclass, field
from typing import Any, Iterable

from .situation_assessment import (
    ClarificationOption,
    ClarificationQuestion,
    SituationAssessment,
)

logger = logging.getLogger(__name__)

_MAX_QUESTIONS = 4
_MIN_OPTIONS = 2
_MAX_OPTIONS = 4


@dataclass(frozen=True)
class Option:
    """One selectable answer.

    Use the :meth:`run_tool_plan` or :meth:`answer_from_context` class
    methods to construct a properly-shaped ``bound_action`` payload —
    instantiating ``Option`` directly is allowed but the caller is
    responsible for shaping ``bound_action`` correctly.
    """
    label: str
    text: str
    bound_action: dict = field(default_factory=dict)
    preview: str = ""

    @classmethod
    def run_tool_plan(
        cls,
        label: str,
        text: str,
        tools: list[tuple[str, dict[str, Any]]],
        resolved_entities: Iterable[str] = (),
        preview: str = "",
        evidence_plan: Iterable[str] | None = None,
        user_is_asking: str = "",
        context_found: str = "",
    ) -> "Option":
        """Build an option that runs a tool plan when selected.

        Optional ``evidence_plan`` / ``user_is_asking`` / ``context_found``
        propagate into ``bound_action`` for downstream evidence-gate and
        synthesis-intent inference once the user picks this option.
        """
        action: dict[str, Any] = {
            "decision": "run_tool_plan",
            "tool_plan": list(tools),
            "resolved_entities": list(resolved_entities),
        }
        if evidence_plan is not None:
            action["evidence_plan"] = list(evidence_plan)
        if user_is_asking:
            action["user_is_asking"] = user_is_asking
        if context_found:
            action["context_found"] = context_found
        return cls(
            label=label,
            text=text,
            preview=preview,
            bound_action=action,
        )

    @classmethod
    def answer_from_context(
        cls,
        label: str,
        text: str,
        preview: str = "",
    ) -> "Option":
        """Build an option that answers from session context (no fresh tools)."""
        return cls(
            label=label,
            text=text,
            preview=preview,
            bound_action={"decision": "answer_from_context"},
        )

    def to_clarification_option(self) -> ClarificationOption:
        return ClarificationOption(
            label=self.label,
            text=self.text,
            bound_action=dict(self.bound_action),
            preview=self.preview,
        )


@dataclass(frozen=True)
class Question:
    """One question with 2-4 selectable options.

    ``multi_select`` is reserved — see module docstring.
    """
    prompt: str
    options: list[Option]
    default_label: str = ""
    multi_select: bool = False

    def to_clarification_question(self) -> ClarificationQuestion:
        return ClarificationQuestion(
            prompt=self.prompt,
            options=tuple(o.to_clarification_option() for o in self.options),
            default_label=self.default_label,
        )


@dataclass(frozen=True)
class AskUserQuestion:
    """High-level builder for a multi-question clarification prompt.

    Pass the result of :meth:`to_assessment` to the agent's pending
    clarification slot; the existing pipeline takes over from there.
    """
    questions: list[Question]
    user_is_asking: str = ""
    context_found: str = ""
    source_assessment: str = ""
    confidence: str = "medium"
    clarification_question: str = ""
    plan: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._validate()

    def _validate(self) -> None:
        if not self.questions:
            raise ValueError("AskUserQuestion requires at least 1 question.")
        if len(self.questions) > _MAX_QUESTIONS:
            raise ValueError(
                f"AskUserQuestion accepts at most {_MAX_QUESTIONS} questions, got {len(self.questions)}."
            )
        for q_idx, q in enumerate(self.questions, start=1):
            if not q.prompt.strip():
                raise ValueError(f"Q{q_idx} has empty prompt.")
            n_opts = len(q.options)
            if n_opts < _MIN_OPTIONS or n_opts > _MAX_OPTIONS:
                raise ValueError(
                    f"Q{q_idx} must have {_MIN_OPTIONS}-{_MAX_OPTIONS} options, got {n_opts}."
                )
            labels = [o.label for o in q.options]
            expected = list(string.ascii_uppercase[:n_opts])
            if labels != expected:
                raise ValueError(
                    f"Q{q_idx} option labels must be {expected}, got {labels}."
                )
            if q.default_label and q.default_label not in labels:
                raise ValueError(
                    f"Q{q_idx} default_label {q.default_label!r} not in option labels {labels}."
                )
            for opt in q.options:
                action = opt.bound_action or {}
                decision = action.get("decision")
                if decision not in {"run_tool_plan", "answer_from_context"}:
                    raise ValueError(
                        f"Q{q_idx} option [{opt.label}] has invalid bound_action.decision={decision!r}."
                    )
                if decision == "run_tool_plan" and not action.get("tool_plan"):
                    raise ValueError(
                        f"Q{q_idx} option [{opt.label}] is run_tool_plan but has empty tool_plan."
                    )
            if q.multi_select:
                logger.warning(
                    "Question.multi_select=True is reserved for a future phase; "
                    "single-option dispatch will be used for now."
                )

    def to_assessment(self) -> SituationAssessment:
        """Produce a :class:`SituationAssessment` ready for the agent's pending slot."""
        return SituationAssessment(
            applies=True,
            decision="ask_clarification",
            confidence=self.confidence,
            user_is_asking=self.user_is_asking,
            context_found=self.context_found,
            source_assessment=self.source_assessment,
            clarification_question=self.clarification_question,
            clarification_questions=tuple(
                q.to_clarification_question() for q in self.questions
            ),
            plan=list(self.plan),
        )


__all__ = ["AskUserQuestion", "Question", "Option"]
