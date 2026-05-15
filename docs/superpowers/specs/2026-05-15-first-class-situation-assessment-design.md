# First-Class Situation Assessment Design

## Purpose

Agent Adda currently routes many turns directly from keywords to tools. That is fast for direct commands, but it fails on contextual follow-ups such as "were these pulled from last 30mins" after an EOD Stage 2 screener. The agent should first assess ambiguous, contextual, or source-sensitive turns before routing so it can answer what the user actually asked.

This design adds a first-class situation assessment layer for those cases. It interprets the user request, resolves references to prior context, checks source and freshness, decides whether tools are needed, and asks for clarification when intent is unclear.

## Goals

- Preserve the existing concise behavior for direct standalone requests.
- Add a comprehensive visible assessment for contextual, ambiguous, multi-step, or source-sensitive turns.
- Store enough last-turn context to answer provenance/freshness questions without accidentally running unrelated market tools.
- Add a clarification gate when the assessment cannot confidently resolve the user's intent.
- Keep the implementation deterministic and testable first, with optional LLM wording support later.

## Non-Goals

- Do not expose private chain-of-thought. The assessment is a concise, user-facing decision summary.
- Do not replace the existing router, tool executor, or response synthesizer.
- Do not show the assessment block for every direct command.
- Do not turn source/freshness questions into market recaps unless the user explicitly asks for a fresh recap.

## Trigger Conditions

The assessment layer should run before normal keyword routing when a query is likely to depend on prior context or source interpretation. Initial trigger phrases include:

- Context references: `these`, `this`, `that`, `above`, `this list`, `those names`, `same stocks`, `previous`.
- Source/freshness questions: `pulled from`, `source`, `where did`, `from last`, `last 30`, `live`, `fresh`, `stale`, `as of`, `is this current`, `fallback`.
- Ambiguous actions on prior results: `scan these`, `check these live`, `what about these`, `compare these`, `are these valid`.

Direct standalone queries continue through the existing router unless they match one of these contextual/source-sensitive patterns.

## Context Model

After each deterministic or LLM-backed response, Agent Adda should store a compact `last_turn_context` object on the `Agent` instance.

Fields:

- `user_input`: normalized user query.
- `intent`: final intent, such as `screener`, `intraday_setup`, `fno_overview`, `stock_brief`.
- `mode`: `historical`, `intraday`, `global`, or other route mode.
- `tools`: ordered list of tool names called.
- `tool_args`: compact ordered list of tool arguments.
- `source_label`: rendered source label, such as `EOD CSV + DB snapshot`, `PG intraday.quote_snapshots`, `NSE options/futures API`.
- `freshness`: best available date/time string from tool results or readiness metadata.
- `symbols`: symbols extracted from args/results.
- `result_type`: high-level category, such as `stage2_screener`, `intraday_recap`, `fno_overview`, `stock_snapshot`.
- `result_summary`: short deterministic summary of result count, screener type, source, and key symbols.
- `result_items`: compact list of result symbols/items where available, capped to avoid bloating memory.

This context should not store full raw tool payloads.

## Assessment Object

The assessment module should return a structured object:

- `applies`: whether the assessment should intercept this turn.
- `confidence`: `high`, `medium`, or `low`.
- `user_is_asking`: one-sentence interpretation.
- `context_found`: concise prior-context summary.
- `source_assessment`: what the prior data source can and cannot support.
- `decision`: one of `answer_from_context`, `run_tool_plan`, `ask_clarification`, or `fallback_to_router`.
- `plan`: user-facing plan lines.
- `tool_plan`: optional existing `(tool, args)` tuples when tools should run.
- `clarification_question`: one focused question when confidence is not high.

## Decision Rules

### Answer From Context

Use this when the user asks about source, freshness, provenance, or whether a prior result came from a certain data window and prior context is sufficient.

Example:

- Prior context: `screener`, tool `run_screener_query(stage2)`, source `EOD CSV + DB snapshot`, freshness `2026-05-14`.
- User: `were these pulled from last 30mins`
- Decision: `answer_from_context`.
- Tool calls: none.

Expected answer:

```text
▶ SITUATION ASSESSMENT
User is asking: Whether the Stage 2 list shown above came from last-30-minute intraday data.
Context found: Previous result was the Stage 2 EOD screener from EOD CSV + DB snapshot, freshness 2026-05-14.
Source assessment: The list was not generated from last-30-minute intraday data.
Decision: Answer from prior context; do not run a market recap.
Plan: Explain the source, clarify the time basis, and offer a separate intraday scan if needed.

No. The Stage 2 list was pulled from the latest EOD/stage snapshot, not from the last 30 minutes.
```

### Run Tool Plan

Use this when the prior context resolves the target and the user asks for a new analysis.

Example:

- Prior context: Stage 2 screener with symbols.
- User: `scan these live for intraday strength`.
- If intent is clear enough, run a tool plan against prior result symbols or a suitable intraday scanner.
- If "live strength" is ambiguous, ask clarification instead.

### Ask Clarification

Use this when intent or reference target is unclear. Do not call tools.

Examples:

- User: `what about these`
- Context has multiple possible targets.
- Ask: `Do you mean the Stage 2 stock list, the F&O strikes, or the market breadth?`

- User: `scan these live`
- Context has symbols but "live" could mean live quote, last-30-minute momentum, or intraday setup.
- Ask: `Do you want live quotes, last-30-minute momentum, or 15-minute intraday trade setups for the prior list?`

### Fallback To Router

Use this when the query is standalone or assessment triggers weakly but finds no relevant context. If the query is otherwise understandable, normal routing should continue. If it depends on missing context, ask clarification.

## User-Facing Assessment Format

When displayed, the assessment block should be compact but complete:

```text
▶ SITUATION ASSESSMENT
User is asking: ...
Context found: ...
Source assessment: ...
Decision: ...
Plan:
  1. ...
  2. ...
  3. ...
```

The block is displayed only for contextual, ambiguous, multi-step, or source-sensitive turns. It should not appear for direct commands such as `/fno NIFTY`, `RELIANCE technical setup`, or `show Stage 2 stocks`.

## Architecture

Add a focused module:

- `terminal/situation_assessment.py`
  - Defines dataclasses for `TurnContext` and `SituationAssessment`.
  - Builds compact context from `intent`, mode, source label, tool results, and answer.
  - Detects whether a query needs assessment.
  - Produces deterministic assessment decisions.
  - Renders the assessment block.

Modify:

- `terminal/agent.py`
  - Add `self._last_turn_context`.
  - Build and store context after deterministic and LLM tool-backed responses.
  - Before `_keyword_intent`, call the assessment module.
  - If decision is `answer_from_context`, synthesize answer without tool execution.
  - If decision is `ask_clarification`, return clarification without tool execution.
  - If decision is `run_tool_plan`, execute that plan through existing `_execute_plan`.
  - Otherwise continue existing routing.

## Testing Requirements

Add tests covering:

- Stage 2 screener followed by `were these pulled from last 30mins` answers from prior context and does not call `get_intraday_market_recap`.
- Stage 2 screener followed by `what about these` asks clarification and does not call tools.
- Stage 2 screener followed by `scan these live` asks clarification unless the wording specifies the live analysis type.
- Intraday setup followed by `is this from PostgreSQL or fallback` answers from prior context.
- F&O overview followed by `what expiry was this from` answers from prior context.
- Direct commands still route without showing the assessment block.

## Rollout

Implement deterministically first. Once stable, an LLM can optionally polish `user_is_asking` and plan wording, but it must not override deterministic decision rules or tool plans.

The assessment layer should be conservative: if context is unclear, ask a concise clarification question instead of guessing.
