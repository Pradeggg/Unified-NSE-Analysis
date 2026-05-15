# First-Class Situation Assessment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a comprehensive situation-assessment layer that handles contextual, ambiguous, and source-sensitive follow-ups before normal Agent Adda keyword routing.

**Architecture:** Add a focused `terminal/situation_assessment.py` module with dataclasses, trigger detection, compact turn-context building, deterministic assessment decisions, and rendering. Integrate it into `terminal/agent.py` before `_keyword_intent` so contextual turns can answer from prior context, ask clarification, or run an explicit tool plan without falling into unrelated routes.

**Tech Stack:** Python 3.10+, existing Agent Adda terminal agent, existing `terminal.tools` results, unittest/pytest tests, no new external dependencies.

---

## Product Contract

### When Assessment Appears

Show `▶ SITUATION ASSESSMENT` only for:

- Contextual references: `these`, `this list`, `above`, `previous`, `same stocks`.
- Source/freshness questions: `pulled from`, `source`, `last 30`, `live`, `fresh`, `stale`, `fallback`.
- Ambiguous actions on prior results: `scan these live`, `what about these`, `compare these`.

Do not show the assessment block for direct standalone queries such as:

- `show Stage 2 stocks`
- `/fno NIFTY`
- `RELIANCE technical setup`
- `market overview`

### Decision Outcomes

| Decision | Behavior |
|---|---|
| `answer_from_context` | Return an assessment block plus direct answer, with no tool calls. |
| `ask_clarification` | Return an assessment block plus one focused question, with no tool calls. |
| `run_tool_plan` | Return assessment block, execute explicit tool plan, synthesize normally. |
| `fallback_to_router` | Continue current `_keyword_intent` behavior. |

### Guardrails

- Do not expose private chain-of-thought; the visible assessment is an auditable summary.
- Do not route source/freshness follow-ups to `get_intraday_market_recap` unless the user explicitly asks for a new recap.
- If confidence is not high, ask clarification instead of guessing.
- Store compact context only; do not retain full raw tool payloads.

---

## File Structure

**Create:**

- `terminal/situation_assessment.py`
  - Dataclasses: `TurnContext`, `SituationAssessment`.
  - Functions: `needs_situation_assessment`, `build_turn_context`, `assess_followup`, `render_assessment_block`, `render_context_answer`.

**Modify:**

- `terminal/agent.py`
  - Add `self._last_turn_context`.
  - Store compact context after deterministic and LLM tool-backed responses.
  - Run situation assessment before `_keyword_intent`.
  - Short-circuit with no tools for `answer_from_context` and `ask_clarification`.
  - Execute explicit `tool_plan` for `run_tool_plan`.

**Tests:**

- Add: `tests/test_situation_assessment.py`
- Modify: `tests/test_terminal_agent_market_prompt.py`

---

## Task 1: Define Situation Assessment Data Contracts

**Files:**
- Create: `terminal/situation_assessment.py`
- Test: `tests/test_situation_assessment.py`

- [ ] **Step 1: Write failing dataclass tests**

Create `tests/test_situation_assessment.py`:

```python
from terminal.situation_assessment import SituationAssessment, TurnContext


def test_turn_context_defaults_are_compact():
    ctx = TurnContext(
        user_input="show Stage 2 stocks",
        intent="screener",
        mode="historical",
        tools=["run_screener_query"],
        source_label="EOD CSV + DB snapshot",
        freshness="2026-05-14",
        result_type="stage2_screener",
        result_summary="Stage 2 screener returned 10 results.",
        symbols=["BLISSGVS", "IPCALAB"],
        result_items=["BLISSGVS", "IPCALAB"],
    )

    assert ctx.intent == "screener"
    assert ctx.tool_args == []
    assert ctx.result_items == ["BLISSGVS", "IPCALAB"]


def test_situation_assessment_defaults():
    assessment = SituationAssessment(applies=False, decision="fallback_to_router")

    assert assessment.confidence == "low"
    assert assessment.tool_plan == []
    assert assessment.plan == []
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_situation_assessment.py -q
```

Expected: fails with `ModuleNotFoundError: No module named 'terminal.situation_assessment'`.

- [ ] **Step 3: Implement dataclasses**

Create `terminal/situation_assessment.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


ToolPlan = list[tuple[str, dict[str, Any]]]


@dataclass(frozen=True)
class TurnContext:
    user_input: str
    intent: str
    mode: str
    tools: list[str] = field(default_factory=list)
    tool_args: list[dict[str, Any]] = field(default_factory=list)
    source_label: str = ""
    freshness: str = ""
    symbols: list[str] = field(default_factory=list)
    result_type: str = ""
    result_summary: str = ""
    result_items: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SituationAssessment:
    applies: bool
    decision: str
    confidence: str = "low"
    user_is_asking: str = ""
    context_found: str = ""
    source_assessment: str = ""
    plan: list[str] = field(default_factory=list)
    tool_plan: ToolPlan = field(default_factory=list)
    clarification_question: str = ""
```

- [ ] **Step 4: Run tests and verify GREEN**

Run:

```bash
.venv/bin/python -m pytest tests/test_situation_assessment.py -q
```

Expected: `2 passed`.

---

## Task 2: Detect Contextual And Source-Sensitive Follow-Ups

**Files:**
- Modify: `terminal/situation_assessment.py`
- Test: `tests/test_situation_assessment.py`

- [ ] **Step 1: Write failing trigger tests**

Append:

```python
from terminal.situation_assessment import needs_situation_assessment


def test_contextual_source_questions_trigger_assessment():
    assert needs_situation_assessment("were these pulled from last 30mins")
    assert needs_situation_assessment("what about these")
    assert needs_situation_assessment("scan these live")
    assert needs_situation_assessment("is this from PostgreSQL or fallback")
    assert needs_situation_assessment("what expiry was this from")


def test_direct_queries_do_not_trigger_assessment():
    assert not needs_situation_assessment("show Stage 2 stocks")
    assert not needs_situation_assessment("/fno NIFTY")
    assert not needs_situation_assessment("RELIANCE technical setup")
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_situation_assessment.py::test_contextual_source_questions_trigger_assessment tests/test_situation_assessment.py::test_direct_queries_do_not_trigger_assessment -q
```

Expected: fails because `needs_situation_assessment` is missing.

- [ ] **Step 3: Implement trigger detection**

Add to `terminal/situation_assessment.py`:

```python
import re


_CONTEXT_TERMS = (
    "these", "this list", "those names", "same stocks", "above", "previous",
    "what about these", "compare these", "scan these", "check these",
)
_SOURCE_TERMS = (
    "pulled from", "source", "where did", "from last", "last 30", "last 15",
    "last 5", "live", "fresh", "stale", "as of", "is this current",
    "fallback", "postgres", "postgresql", "expiry was this",
)


def needs_situation_assessment(query: str) -> bool:
    q = (query or "").strip().lower()
    if not q:
        return False
    if q.startswith(("/fno", "/chain", "/screen", "/scan", "/live", "/eod")):
        return False
    return any(term in q for term in _CONTEXT_TERMS + _SOURCE_TERMS)
```

- [ ] **Step 4: Run tests and verify GREEN**

Run:

```bash
.venv/bin/python -m pytest tests/test_situation_assessment.py -q
```

Expected: all current situation-assessment tests pass.

---

## Task 3: Build Compact Turn Context From Tool Results

**Files:**
- Modify: `terminal/situation_assessment.py`
- Test: `tests/test_situation_assessment.py`

- [ ] **Step 1: Write failing context-builder tests**

Append:

```python
from terminal.situation_assessment import build_turn_context


def test_build_context_from_stage2_screener_results():
    tool_results = [
        {
            "tool": "run_screener_query",
            "args": {"screen_type": "stage2"},
            "result": {
                "screen_type": "stage2",
                "count": 2,
                "results": [
                    {"symbol": "BLISSGVS"},
                    {"symbol": "IPCALAB"},
                ],
            },
        }
    ]

    ctx = build_turn_context(
        user_input="show Stage 2 stocks",
        intent="screener",
        mode="historical",
        source_label="EOD CSV + DB snapshot",
        tool_results=tool_results,
        answer="Data Freshness: snapshot 2026-05-14",
    )

    assert ctx.result_type == "stage2_screener"
    assert ctx.freshness == "2026-05-14"
    assert ctx.symbols == ["BLISSGVS", "IPCALAB"]
    assert "2 results" in ctx.result_summary


def test_build_context_from_fno_overview_results():
    tool_results = [
        {
            "tool": "get_options_chain",
            "args": {"symbol": "NIFTY", "expiry_index": 0},
            "result": {"symbol": "NIFTY", "expiry": "2026-05-21", "pcr": 0.9},
        },
        {
            "tool": "get_futures_analysis",
            "args": {"symbol": "NIFTY"},
            "result": {"symbol": "NIFTY", "as_of": "2026-05-15 13:45:00"},
        },
    ]

    ctx = build_turn_context(
        user_input="/fno NIFTY",
        intent="fno_overview",
        mode="intraday",
        source_label="NSE options/futures API + F&O EOD fallback",
        tool_results=tool_results,
        answer="",
    )

    assert ctx.result_type == "fno_overview"
    assert ctx.freshness == "2026-05-15 13:45:00"
    assert ctx.symbols == ["NIFTY"]
    assert "expiry 2026-05-21" in ctx.result_summary
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_situation_assessment.py::test_build_context_from_stage2_screener_results tests/test_situation_assessment.py::test_build_context_from_fno_overview_results -q
```

Expected: fails because `build_turn_context` is missing.

- [ ] **Step 3: Implement compact context building**

Add to `terminal/situation_assessment.py`:

```python
def _dedupe(values: list[str]) -> list[str]:
    out: list[str] = []
    for value in values:
        clean = str(value or "").strip().upper()
        if clean and clean not in out:
            out.append(clean)
    return out


def _extract_freshness(answer: str, tool_results: list[dict]) -> str:
    for tr in tool_results:
        result = tr.get("result") if isinstance(tr.get("result"), dict) else {}
        for key in ("as_of", "timestamp", "freshness", "snapshot_date", "expiry"):
            value = result.get(key)
            if value:
                return str(value)
    match = re.search(r"snapshot\s+(\d{4}-\d{2}-\d{2})", answer or "", flags=re.I)
    return match.group(1) if match else ""


def build_turn_context(
    *,
    user_input: str,
    intent: str,
    mode: str,
    source_label: str,
    tool_results: list[dict],
    answer: str,
) -> TurnContext:
    tools = [str(tr.get("tool") or "") for tr in tool_results if tr.get("tool")]
    tool_args = [
        dict(tr.get("args") or {})
        for tr in tool_results
        if isinstance(tr.get("args"), dict)
    ]
    symbols: list[str] = []
    result_items: list[str] = []
    result_type = intent
    summary = intent.replace("_", " ")

    for tr in tool_results:
        args = tr.get("args") if isinstance(tr.get("args"), dict) else {}
        result = tr.get("result") if isinstance(tr.get("result"), dict) else {}
        if args.get("symbol"):
            symbols.append(str(args["symbol"]))
        if result.get("symbol"):
            symbols.append(str(result["symbol"]))

        if tr.get("tool") == "run_screener_query":
            screen_type = str(result.get("screen_type") or args.get("screen_type") or "").lower()
            result_type = f"{screen_type}_screener" if screen_type else "screener"
            rows = result.get("results") or result.get("stocks") or []
            for row in rows[:20]:
                if isinstance(row, dict) and row.get("symbol"):
                    result_items.append(str(row["symbol"]).upper())
            symbols.extend(result_items)
            count = result.get("count") or len(rows)
            summary = f"{screen_type or 'screener'} screener returned {count} results."

        if tr.get("tool") == "get_options_chain":
            result_type = "fno_overview"
            expiry = result.get("expiry")
            if expiry:
                summary = f"F&O overview for {result.get('symbol', args.get('symbol', 'NIFTY'))}, expiry {expiry}."

    return TurnContext(
        user_input=user_input,
        intent=intent,
        mode=mode,
        tools=tools,
        tool_args=tool_args,
        source_label=source_label,
        freshness=_extract_freshness(answer, tool_results),
        symbols=_dedupe(symbols),
        result_type=result_type,
        result_summary=summary,
        result_items=_dedupe(result_items)[:20],
    )
```

- [ ] **Step 4: Run tests and verify GREEN**

Run:

```bash
.venv/bin/python -m pytest tests/test_situation_assessment.py -q
```

Expected: all situation-assessment tests pass.

---

## Task 4: Assess Source/Freshness Follow-Ups From Prior Context

**Files:**
- Modify: `terminal/situation_assessment.py`
- Test: `tests/test_situation_assessment.py`

- [ ] **Step 1: Write failing assessment tests**

Append:

```python
from terminal.situation_assessment import assess_followup


def test_stage2_last_30_minutes_question_answers_from_context():
    ctx = TurnContext(
        user_input="show Stage 2 stocks",
        intent="screener",
        mode="historical",
        tools=["run_screener_query"],
        source_label="EOD CSV + DB snapshot",
        freshness="2026-05-14",
        result_type="stage2_screener",
        result_summary="stage2 screener returned 10 results.",
        result_items=["BLISSGVS", "IPCALAB"],
    )

    assessment = assess_followup("were these pulled from last 30mins", ctx)

    assert assessment.applies
    assert assessment.confidence == "high"
    assert assessment.decision == "answer_from_context"
    assert assessment.tool_plan == []
    assert "Stage 2" in assessment.user_is_asking
    assert "not generated from last-30-minute" in assessment.source_assessment


def test_postgres_or_fallback_question_answers_from_intraday_context():
    ctx = TurnContext(
        user_input="TMPV intraday setup",
        intent="intraday_setup",
        mode="intraday",
        tools=["resolve_symbol", "explain_intraday_setup", "get_nse_intraday_snapshot"],
        source_label="PG intraday.quote_snapshots + PG intraday.ohlcv_bars",
        freshness="2026-05-15 13:15:00",
        symbols=["TMPV"],
        result_type="intraday_setup",
        result_summary="TMPV intraday setup from PostgreSQL bars and NSE snapshot.",
    )

    assessment = assess_followup("is this from PostgreSQL or fallback", ctx)

    assert assessment.decision == "answer_from_context"
    assert "PostgreSQL" in assessment.source_assessment


def test_fno_expiry_question_answers_from_context():
    ctx = TurnContext(
        user_input="/fno NIFTY",
        intent="fno_overview",
        mode="intraday",
        tools=["get_options_chain", "get_futures_analysis"],
        source_label="NSE options/futures API + F&O EOD fallback",
        freshness="2026-05-15 13:45:00",
        symbols=["NIFTY"],
        result_type="fno_overview",
        result_summary="F&O overview for NIFTY, expiry 2026-05-21.",
    )

    assessment = assess_followup("what expiry was this from", ctx)

    assert assessment.decision == "answer_from_context"
    assert "2026-05-21" in assessment.source_assessment
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_situation_assessment.py::test_stage2_last_30_minutes_question_answers_from_context tests/test_situation_assessment.py::test_postgres_or_fallback_question_answers_from_intraday_context tests/test_situation_assessment.py::test_fno_expiry_question_answers_from_context -q
```

Expected: fails because `assess_followup` is missing.

- [ ] **Step 3: Implement deterministic source/freshness assessment**

Add to `terminal/situation_assessment.py`:

```python
def _is_last_window_question(q: str) -> bool:
    return bool(re.search(r"\blast\s*(?:5|15|30|60)?\s*(?:min|mins|minutes)\b", q))


def _is_source_question(q: str) -> bool:
    return any(term in q for term in ("source", "pulled from", "where did", "fresh", "stale", "fallback", "postgres", "postgresql", "expiry"))


def assess_followup(query: str, context: TurnContext | None) -> SituationAssessment:
    q = (query or "").strip().lower()
    if not needs_situation_assessment(query):
        return SituationAssessment(applies=False, decision="fallback_to_router")
    if context is None:
        return SituationAssessment(
            applies=True,
            decision="ask_clarification",
            confidence="low",
            user_is_asking="The request appears to refer to prior output, but no prior context is available.",
            context_found="No previous result context is available.",
            source_assessment="Cannot determine source or freshness without a prior result.",
            plan=["Ask the user what result or symbol they want to inspect."],
            clarification_question="Which prior result or symbol do you want me to assess?",
        )

    if _is_last_window_question(q) and context.intent == "screener":
        return SituationAssessment(
            applies=True,
            decision="answer_from_context",
            confidence="high",
            user_is_asking=f"Whether the prior {context.result_type.replace('_', ' ')} came from last-30-minute intraday data.",
            context_found=f"Previous result: {context.result_summary} Source: {context.source_label}. Freshness: {context.freshness or 'not reported'}.",
            source_assessment=f"The list was not generated from last-30-minute intraday data; it came from {context.source_label}.",
            plan=[
                "Answer directly from prior context.",
                "Do not run a market recap.",
                "Offer a separate intraday scan if the user wants live/last-window screening.",
            ],
        )

    if _is_source_question(q):
        return SituationAssessment(
            applies=True,
            decision="answer_from_context",
            confidence="high",
            user_is_asking="The user is asking about the source, freshness, or provenance of the prior result.",
            context_found=f"Previous result: {context.result_summary} Tools: {', '.join(context.tools) or 'none'}.",
            source_assessment=f"Source: {context.source_label or 'not labelled'}. Freshness: {context.freshness or 'not reported'}.",
            plan=[
                "Answer from stored prior context.",
                "State source and freshness explicitly.",
                "Avoid unrelated tool calls.",
            ],
        )

    return SituationAssessment(applies=False, decision="fallback_to_router")
```

- [ ] **Step 4: Run tests and verify GREEN**

Run:

```bash
.venv/bin/python -m pytest tests/test_situation_assessment.py -q
```

Expected: all situation-assessment tests pass.

---

## Task 5: Add Clarification Gate For Unclear Follow-Ups

**Files:**
- Modify: `terminal/situation_assessment.py`
- Test: `tests/test_situation_assessment.py`

- [ ] **Step 1: Write failing clarification tests**

Append:

```python
def test_what_about_these_asks_clarification():
    ctx = TurnContext(
        user_input="show Stage 2 stocks",
        intent="screener",
        mode="historical",
        tools=["run_screener_query"],
        source_label="EOD CSV + DB snapshot",
        result_type="stage2_screener",
        result_summary="stage2 screener returned 10 results.",
        result_items=["BLISSGVS", "IPCALAB"],
    )

    assessment = assess_followup("what about these", ctx)

    assert assessment.decision == "ask_clarification"
    assert assessment.tool_plan == []
    assert "Do you mean" in assessment.clarification_question


def test_scan_these_live_asks_for_live_analysis_type():
    ctx = TurnContext(
        user_input="show Stage 2 stocks",
        intent="screener",
        mode="historical",
        tools=["run_screener_query"],
        source_label="EOD CSV + DB snapshot",
        result_type="stage2_screener",
        result_summary="stage2 screener returned 10 results.",
        result_items=["BLISSGVS", "IPCALAB"],
    )

    assessment = assess_followup("scan these live", ctx)

    assert assessment.decision == "ask_clarification"
    assert "live quotes" in assessment.clarification_question
    assert "last-30-minute momentum" in assessment.clarification_question
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_situation_assessment.py::test_what_about_these_asks_clarification tests/test_situation_assessment.py::test_scan_these_live_asks_for_live_analysis_type -q
```

Expected: tests fail because current assessment falls through.

- [ ] **Step 3: Implement clarification decisions**

Insert these branches in `assess_followup` before the final fallback:

```python
    if "what about these" in q or q in {"what about this", "what about that"}:
        return SituationAssessment(
            applies=True,
            decision="ask_clarification",
            confidence="medium",
            user_is_asking="The user is referring to a prior result but has not specified the analysis to perform.",
            context_found=f"Previous result: {context.result_summary}",
            source_assessment=f"Prior source: {context.source_label or 'not labelled'}.",
            plan=["Ask what aspect of the prior result should be assessed before calling tools."],
            clarification_question="Do you mean the prior list's source, live intraday strength, fundamentals, or a comparison among the names?",
        )

    if "scan these live" in q or "check these live" in q:
        return SituationAssessment(
            applies=True,
            decision="ask_clarification",
            confidence="medium",
            user_is_asking="The user wants a live scan of prior result items, but the live analysis type is ambiguous.",
            context_found=f"Previous result: {context.result_summary}",
            source_assessment="The prior result can provide the symbol list, but not the requested live analysis type.",
            plan=["Ask the user to choose the live analysis type before calling intraday tools."],
            clarification_question="Do you want live quotes, last-30-minute momentum, or 15-minute intraday trade setups for the prior list?",
        )
```

- [ ] **Step 4: Run tests and verify GREEN**

Run:

```bash
.venv/bin/python -m pytest tests/test_situation_assessment.py -q
```

Expected: all situation-assessment tests pass.

---

## Task 6: Render Assessment Blocks And Direct Context Answers

**Files:**
- Modify: `terminal/situation_assessment.py`
- Test: `tests/test_situation_assessment.py`

- [ ] **Step 1: Write failing rendering tests**

Append:

```python
from terminal.situation_assessment import render_assessment_block, render_context_answer


def test_render_assessment_block_is_comprehensive():
    assessment = SituationAssessment(
        applies=True,
        decision="answer_from_context",
        confidence="high",
        user_is_asking="Whether the prior Stage 2 list came from last-30-minute data.",
        context_found="Previous result was Stage 2 screener.",
        source_assessment="It came from EOD CSV + DB snapshot.",
        plan=["Answer from prior context.", "Do not run market recap."],
    )

    rendered = render_assessment_block(assessment)

    assert "▶ SITUATION ASSESSMENT" in rendered
    assert "User is asking:" in rendered
    assert "Context found:" in rendered
    assert "Source assessment:" in rendered
    assert "Decision:" in rendered
    assert "1. Answer from prior context." in rendered


def test_render_context_answer_for_stage2_last_30_question():
    ctx = TurnContext(
        user_input="show Stage 2 stocks",
        intent="screener",
        mode="historical",
        tools=["run_screener_query"],
        source_label="EOD CSV + DB snapshot",
        freshness="2026-05-14",
        result_type="stage2_screener",
        result_summary="stage2 screener returned 10 results.",
    )
    assessment = assess_followup("were these pulled from last 30mins", ctx)

    answer = render_context_answer("were these pulled from last 30mins", assessment, ctx)

    assert "No." in answer
    assert "2026-05-14" in answer
    assert "not from the last 30 minutes" in answer
    assert "Not investment advice" in answer
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_situation_assessment.py::test_render_assessment_block_is_comprehensive tests/test_situation_assessment.py::test_render_context_answer_for_stage2_last_30_question -q
```

Expected: fails because rendering functions are missing.

- [ ] **Step 3: Implement rendering**

Add:

```python
def render_assessment_block(assessment: SituationAssessment) -> str:
    lines = [
        "▶ SITUATION ASSESSMENT",
        f"User is asking: {assessment.user_is_asking or 'Unclear.'}",
        f"Context found: {assessment.context_found or 'No relevant prior context.'}",
        f"Source assessment: {assessment.source_assessment or 'Not available.'}",
        f"Decision: {assessment.decision.replace('_', ' ')} ({assessment.confidence} confidence)",
    ]
    if assessment.plan:
        lines.append("Plan:")
        for idx, step in enumerate(assessment.plan, start=1):
            lines.append(f"  {idx}. {step}")
    return "\n".join(lines)


def render_context_answer(query: str, assessment: SituationAssessment, context: TurnContext | None) -> str:
    block = render_assessment_block(assessment)
    if assessment.decision == "ask_clarification":
        question = assessment.clarification_question or "Can you clarify what you want me to assess?"
        return f"{block}\n\n{question}\n\n━━━ Not investment advice. For research and learning only. ━━━"

    if context and context.intent == "screener" and _is_last_window_question((query or '').lower()):
        freshness = f" dated {context.freshness}" if context.freshness else ""
        body = (
            f"No. The prior list came from {context.source_label}{freshness}, "
            "not from the last 30 minutes. A last-30-minute read would require a separate intraday scan or recap."
        )
    else:
        body = assessment.source_assessment or "I can answer this from the prior context."
    return f"{block}\n\n{body}\n\n━━━ Not investment advice. For research and learning only. ━━━"
```

- [ ] **Step 4: Run tests and verify GREEN**

Run:

```bash
.venv/bin/python -m pytest tests/test_situation_assessment.py -q
```

Expected: all situation-assessment tests pass.

---

## Task 7: Integrate Assessment Into Agent Query Flow

**Files:**
- Modify: `terminal/agent.py`
- Test: `tests/test_terminal_agent_market_prompt.py`

- [ ] **Step 1: Write failing integration tests**

Append to `tests/test_terminal_agent_market_prompt.py`:

```python
    def test_contextual_stage2_source_question_answers_without_market_recap(self):
        agent = Agent()
        agent.backend = object()
        agent.backend_name = "TestBackend"

        with patch("terminal.agent._execute_plan") as execute_plan:
            execute_plan.return_value = [
                {
                    "tool": "run_screener_query",
                    "args": {"screen_type": "stage2"},
                    "result": {
                        "screen_type": "stage2",
                        "count": 2,
                        "results": [{"symbol": "BLISSGVS"}, {"symbol": "IPCALAB"}],
                    },
                }
            ]
            first = agent.query("lets look at the Stage 2 (uptrend) stocks")

        self.assertEqual(first["intent"], "screener")

        with patch("terminal.agent._execute_plan") as execute_plan:
            second = agent.query("were these pulled from last 30mins")

        execute_plan.assert_not_called()
        self.assertEqual(second["intent"], "situation_assessment")
        self.assertIn("SITUATION ASSESSMENT", second["answer"])
        self.assertIn("No.", second["answer"])
        self.assertIn("not from the last 30 minutes", second["answer"])
        self.assertNotIn("Last 30 Minutes", second["answer"])

    def test_contextual_ambiguous_followup_asks_clarification_without_tools(self):
        agent = Agent()
        agent.backend = object()
        agent.backend_name = "TestBackend"

        with patch("terminal.agent._execute_plan") as execute_plan:
            execute_plan.return_value = [
                {
                    "tool": "run_screener_query",
                    "args": {"screen_type": "stage2"},
                    "result": {"screen_type": "stage2", "count": 1, "results": [{"symbol": "BLISSGVS"}]},
                }
            ]
            agent.query("show Stage 2 stocks")

        with patch("terminal.agent._execute_plan") as execute_plan:
            result = agent.query("what about these")

        execute_plan.assert_not_called()
        self.assertEqual(result["intent"], "situation_assessment")
        self.assertIn("Do you mean", result["answer"])
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_terminal_agent_market_prompt.py::TerminalAgentMarketPromptTests::test_contextual_stage2_source_question_answers_without_market_recap tests/test_terminal_agent_market_prompt.py::TerminalAgentMarketPromptTests::test_contextual_ambiguous_followup_asks_clarification_without_tools -q
```

Expected: fails because `Agent` does not store or use situation context.

- [ ] **Step 3: Import assessment helpers and initialize context**

In `terminal/agent.py`, add import near existing imports:

```python
from .situation_assessment import (
    TurnContext,
    assess_followup,
    build_turn_context,
    needs_situation_assessment,
    render_context_answer,
)
```

In `Agent.__init__`, add:

```python
        self._last_turn_context: TurnContext | None = None
```

- [ ] **Step 4: Add context storage helper**

Add method to `Agent`:

```python
    def _remember_turn_context(
        self,
        *,
        user_input: str,
        intent: str,
        mode: str,
        source_label: str,
        tool_results: list[dict],
        answer: str,
    ) -> None:
        try:
            self._last_turn_context = build_turn_context(
                user_input=user_input,
                intent=intent,
                mode=mode,
                source_label=source_label,
                tool_results=tool_results,
                answer=answer,
            )
        except Exception:
            self._last_turn_context = None
```

In `reset_history`, add:

```python
        self._last_turn_context = None
```

- [ ] **Step 5: Add pre-routing assessment gate**

In `_query_single`, after `clean_input = self._contextualize_pronouns(clean_input)` and before `intent_plan = _keyword_intent(...)`, insert:

```python
        if needs_situation_assessment(clean_input):
            assessment = assess_followup(clean_input, self._last_turn_context)
            if assessment.applies and assessment.decision in {"answer_from_context", "ask_clarification"}:
                answer = render_context_answer(clean_input, assessment, self._last_turn_context)
                self._remember_interaction(clean_input, answer, [])
                return {
                    "answer": answer,
                    "trace": [{"step": "situation_assessment", "result": assessment.__dict__}],
                    "backend": self.backend_name,
                    "intent": "situation_assessment",
                }
```

- [ ] **Step 6: Store context after deterministic routes**

In the deterministic intent block, after answer is finalized and before return, add:

```python
            self._remember_turn_context(
                user_input=clean_input,
                intent=intent_plan["intent"],
                mode=mode,
                source_label=mode_sources.get(mode, ""),
                tool_results=tool_results,
                answer=answer,
            )
```

If `mode == "intraday"` and a refined `source_label` was computed, pass that refined string instead of the default source label.

- [ ] **Step 7: Run integration tests and verify GREEN**

Run:

```bash
.venv/bin/python -m pytest tests/test_terminal_agent_market_prompt.py::TerminalAgentMarketPromptTests::test_contextual_stage2_source_question_answers_without_market_recap tests/test_terminal_agent_market_prompt.py::TerminalAgentMarketPromptTests::test_contextual_ambiguous_followup_asks_clarification_without_tools -q
```

Expected: both tests pass.

---

## Task 8: Support Context Tool Plans For Explicit Live Follow-Ups

**Files:**
- Modify: `terminal/situation_assessment.py`
- Modify: `terminal/agent.py`
- Test: `tests/test_situation_assessment.py`
- Test: `tests/test_terminal_agent_market_prompt.py`

- [ ] **Step 1: Write failing tool-plan tests**

Add to `tests/test_situation_assessment.py`:

```python
def test_scan_these_for_15m_setups_builds_tool_plan():
    ctx = TurnContext(
        user_input="show Stage 2 stocks",
        intent="screener",
        mode="historical",
        tools=["run_screener_query"],
        source_label="EOD CSV + DB snapshot",
        result_type="stage2_screener",
        result_summary="stage2 screener returned 2 results.",
        result_items=["BLISSGVS", "IPCALAB"],
        symbols=["BLISSGVS", "IPCALAB"],
    )

    assessment = assess_followup("scan these for 15m intraday setups", ctx)

    assert assessment.decision == "run_tool_plan"
    assert assessment.tool_plan == [
        ("scan_symbols_intraday", {"symbols": ["BLISSGVS", "IPCALAB"], "interval": "15m"})
    ]
```

Add to `tests/test_terminal_agent_market_prompt.py`:

```python
    def test_contextual_explicit_15m_scan_executes_assessment_tool_plan(self):
        agent = Agent()
        agent.backend = object()
        agent.backend_name = "TestBackend"

        with patch("terminal.agent._execute_plan") as execute_plan:
            execute_plan.return_value = [
                {
                    "tool": "run_screener_query",
                    "args": {"screen_type": "stage2"},
                    "result": {"screen_type": "stage2", "count": 2, "results": [{"symbol": "BLISSGVS"}, {"symbol": "IPCALAB"}]},
                }
            ]
            agent.query("show Stage 2 stocks")

        with patch("terminal.agent._execute_plan") as execute_plan:
            execute_plan.return_value = [
                {
                    "tool": "scan_symbols_intraday",
                    "args": {"symbols": ["BLISSGVS", "IPCALAB"], "interval": "15m"},
                    "result": {"symbols": ["BLISSGVS", "IPCALAB"], "results": []},
                }
            ]
            result = agent.query("scan these for 15m intraday setups")

        execute_plan.assert_called_once_with([
            ("scan_symbols_intraday", {"symbols": ["BLISSGVS", "IPCALAB"], "interval": "15m"})
        ])
        self.assertEqual(result["intent"], "situation_assessment")
        self.assertIn("SITUATION ASSESSMENT", result["answer"])
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_situation_assessment.py::test_scan_these_for_15m_setups_builds_tool_plan tests/test_terminal_agent_market_prompt.py::TerminalAgentMarketPromptTests::test_contextual_explicit_15m_scan_executes_assessment_tool_plan -q
```

Expected: fails because `run_tool_plan` is not implemented.

- [ ] **Step 3: Implement deterministic tool-plan branch**

In `assess_followup`, before the ambiguous `scan these live` clarification branch:

```python
    if ("scan these" in q or "check these" in q) and "15m" in q and context.result_items:
        return SituationAssessment(
            applies=True,
            decision="run_tool_plan",
            confidence="high",
            user_is_asking="The user wants 15-minute intraday setups for the prior result list.",
            context_found=f"Previous result: {context.result_summary}",
            source_assessment="Prior context provides the symbol list; a fresh intraday tool call is required for 15-minute setups.",
            plan=[
                "Use the prior result symbols.",
                "Run the intraday symbol scan on 15-minute data.",
                "Render tool results with source trail.",
            ],
            tool_plan=[("scan_symbols_intraday", {"symbols": context.result_items[:20], "interval": "15m"})],
        )
```

- [ ] **Step 4: Integrate `run_tool_plan` in Agent**

In `_query_single`, extend the pre-routing assessment gate:

```python
            if assessment.applies and assessment.decision == "run_tool_plan":
                trace.append({"step": "situation_assessment", "result": assessment.__dict__})
                tool_results = _execute_plan(assessment.tool_plan)
                trace.extend(tool_results)
                body = _synthesize_no_llm("intraday_screener", tool_results)
                answer = render_assessment_block(assessment) + "\n\n" + body + mode_suffix
                self._remember_interaction(clean_input, answer, tool_results)
                self._remember_turn_context(
                    user_input=clean_input,
                    intent="situation_assessment",
                    mode=mode,
                    source_label=mode_sources.get(mode, ""),
                    tool_results=tool_results,
                    answer=answer,
                )
                return {"answer": answer, "trace": trace, "backend": self.backend_name, "intent": "situation_assessment"}
```

Add `render_assessment_block` to imports.

- [ ] **Step 5: Run tests and verify GREEN**

Run:

```bash
.venv/bin/python -m pytest tests/test_situation_assessment.py tests/test_terminal_agent_market_prompt.py -q
```

Expected: all situation-assessment and terminal-agent routing tests pass.

---

## Task 9: Verify Direct Queries Stay Clean

**Files:**
- Modify: `tests/test_terminal_agent_market_prompt.py`

- [ ] **Step 1: Add regression tests for non-contextual queries**

Append:

```python
    def test_direct_stage2_query_does_not_show_situation_assessment(self):
        agent = Agent()
        agent.backend = object()
        agent.backend_name = "TestBackend"

        with patch("terminal.agent._execute_plan") as execute_plan:
            execute_plan.return_value = [
                {
                    "tool": "run_screener_query",
                    "args": {"screen_type": "stage2"},
                    "result": {"screen_type": "stage2", "count": 0, "results": []},
                }
            ]
            result = agent.query("show Stage 2 stocks")

        self.assertEqual(result["intent"], "screener")
        self.assertNotIn("SITUATION ASSESSMENT", result["answer"])

    def test_direct_fno_query_does_not_show_situation_assessment(self):
        agent = Agent()
        agent.backend = object()
        agent.backend_name = "TestBackend"

        with patch("terminal.agent._execute_plan") as execute_plan:
            execute_plan.return_value = [
                {"tool": "get_options_chain", "args": {"symbol": "NIFTY", "expiry_index": 0}, "result": {"symbol": "NIFTY"}},
                {"tool": "get_futures_analysis", "args": {"symbol": "NIFTY"}, "result": {"symbol": "NIFTY"}},
            ]
            result = agent.query("/fno NIFTY")

        self.assertEqual(result["intent"], "fno_overview")
        self.assertNotIn("SITUATION ASSESSMENT", result["answer"])
```

- [ ] **Step 2: Run tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_terminal_agent_market_prompt.py::TerminalAgentMarketPromptTests::test_direct_stage2_query_does_not_show_situation_assessment tests/test_terminal_agent_market_prompt.py::TerminalAgentMarketPromptTests::test_direct_fno_query_does_not_show_situation_assessment -q
```

Expected: both tests pass.

---

## Task 10: Full Verification And Documentation

**Files:**
- Modify if needed: `docs/superpowers/specs/2026-05-15-first-class-situation-assessment-design.md`
- Modify if needed: `docs/AGENT_ADDA_CAPABILITIES.md`

- [ ] **Step 1: Run focused tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_situation_assessment.py tests/test_terminal_agent_market_prompt.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Run broader relevant tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_on_demand_stock_data.py tests/test_recap_and_capture.py tests/test_terminal_intraday_fallback.py -q
```

Expected: all tests pass.

- [ ] **Step 3: Run full suite**

Run:

```bash
.venv/bin/python -m pytest -q
```

Expected: all unrelated existing failures should be documented. If `tests/test_reports_pipeline.py` still errors on missing `run_id` or `html_path` fixtures, note that as pre-existing and outside this feature.

- [ ] **Step 4: Manual smoke test**

Run the terminal and execute:

```text
show Stage 2 stocks
were these pulled from last 30mins
what about these
/fno NIFTY
```

Expected:

- First command returns normal Stage 2 screener with no assessment block.
- Second command returns situation assessment and explains EOD source, no market recap.
- Third command asks clarification.
- Fourth command returns F&O overview with no assessment block.

- [ ] **Step 5: Commit implementation**

Run:

```bash
git add terminal/situation_assessment.py terminal/agent.py tests/test_situation_assessment.py tests/test_terminal_agent_market_prompt.py docs/AGENT_ADDA_CAPABILITIES.md
git commit -m "feat: add contextual situation assessment"
```

Expected: commit includes only situation-assessment implementation and documentation files.

---

## Self-Review Checklist

- Spec coverage: all design requirements are mapped to tasks.
- TDD coverage: every behavior change starts with failing tests.
- Clarification gate: ambiguous follow-ups stop before tool execution.
- Source/freshness guard: prior EOD screener source questions do not call intraday recap tools.
- Direct route preservation: direct commands remain clean.
- No hidden chain-of-thought: visible assessment is a concise decision summary only.
