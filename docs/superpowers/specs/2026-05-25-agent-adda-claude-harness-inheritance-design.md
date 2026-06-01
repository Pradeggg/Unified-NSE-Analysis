# Agent Adda Claude-Harness Inheritance Design

## Purpose

Agent Adda already has deterministic market tools, PostgreSQL-backed conversation memory, rich terminal commands, and a large LLM system prompt. The next improvement is not another market feature. It is a harness upgrade: make Agent Adda's LLM loop explicit, replayable, inspectable, budgeted, and modular in the style of mature coding agents such as Claude Code, without copying vendor prompt text or losing Agent Adda's market-data grounding.

The guiding split is:

- PostgreSQL remains compact working memory for queryable session state.
- JSONL becomes transcript truth for replay, audit, resume, and fork.
- A context builder becomes the only path for assembling LLM payloads.
- Prompt fragments and runtime reminders replace one large prompt blob.
- Tool activity is represented as typed blocks, not hidden side-channel state.

## Goals

- Build a single canonical context assembly path for every LLM backend call.
- Preserve deterministic routes and existing market guardrails.
- Add typed, provider-neutral message and tool blocks.
- Add an append-only JSONL session transcript that can reconstruct payloads.
- Split prompt behavior into atomic fragments with budgets and mode filters.
- Inject runtime reminders for stale data, missing evidence, low confidence, and repeated failures.
- Show users and developers what context is being sent through `/context`.
- Add loop-depth and payload-size controls so agentic tool loops do not run away silently.

## Non-Goals

- Do not copy extracted Claude Code prompt text.
- Do not implement team/shared memory in this slice.
- Do not replace the unified router or deterministic market workflows.
- Do not make memory prose a source for market facts.
- Do not add a vector index or embedding store.
- Do not expose private chain-of-thought. Any thinking-like block must be a concise public summary only.
- Do not require OpenAI-only protocol assumptions. The internal protocol must support OpenAI, Ollama, and deterministic tool plans.

## Architecture

The harness should be built around five modules.

### `terminal.agent_context`

Owns final context assembly. This module takes the current user input, mode context, memory, recent history, evidence ledger, tool catalog, reminders, and selected schemas, then returns a provider-neutral payload object.

It should be the only place that decides:

- Which prompt fragments are included.
- Which memory summaries are included.
- Which recent turns are included.
- Which tool evidence is included.
- Which tool schemas are included.
- Which sections are excluded due to budget.
- Which runtime reminders are injected.

`terminal.agent.Agent._llm_query()` should stop manually constructing `system + _trim_history() + user_input` and instead call this builder.

### `terminal.llm_protocol`

Defines provider-neutral message and event blocks:

- `system_context`
- `user_message`
- `assistant_text`
- `tool_use`
- `tool_result`
- `route_decision`
- `final_answer`
- `compaction_summary`
- `public_thinking_summary`, where a provider supplies a safe summary

Provider adapters project these blocks into OpenAI/Ollama-compatible payloads. Deterministic route tool plans should also be represented in the same block model, even when no LLM selected the tools.

### `terminal.session_log`

Writes append-only JSONL under `logs/sessions/`.

Each event should include:

- schema version
- session id
- parent session id when forked
- turn id
- timestamp
- event type
- redacted payload metadata
- block content or compact reference
- related tool id where applicable

The JSONL log is not a replacement for PostgreSQL memory. It is the full transcript and replay substrate. PostgreSQL remains optimized for current context binding, reports, workflows, pending options, and compact state.

### `terminal.prompt_fragments`

Defines atomic prompt fragments by concern. Each fragment should have:

- `id`
- `category`
- `purpose`
- `text`
- `modes`
- `priority`
- `char_budget`
- `dependencies`
- `snapshot_name`

Initial fragment families:

- base identity
- market clock and freshness
- evidence and claim discipline
- missing data guardrails
- terminal style
- follow-up question style
- F&O/options guardrails
- email pipe rules
- NSE fallback rules
- symbol-resolution rules
- memory scope descriptors
- plan mode overlay
- minimal mode overlay
- audit/debug overlay
- tool amendment fragments

### `terminal.system_reminders`

Generates short event-driven reminders. These should be runtime artifacts, not static prompt text.

Initial reminders:

- stale EOD snapshot
- stale or missing intraday data
- low-confidence symbol resolution
- options evidence missing
- futures evidence missing
- PostgreSQL unavailable
- data readiness below threshold
- repeated tool failure
- loop-depth warning
- context budget warning
- email pipe output captured
- active `/plan` mode
- active `/minimal` mode
- active `/audit` mode

Reminders should be concise and source-linked where possible.

## Data Flow

### Normal LLM Turn

1. User enters a prompt.
2. Agent router handles deterministic commands first where applicable.
3. If LLM path is needed, `AgentContextBuilder` assembles a payload.
4. Payload includes prompt fragments, recent turns, compact memory, evidence ledger, runtime reminders, selected tool schemas, and current input.
5. Provider adapter sends the payload to the backend.
6. Backend returns typed text/tool blocks.
7. Tool calls execute and produce typed tool-result blocks.
8. A fresh payload is assembled for the next backend round-trip with the tool result included.
9. Final answer is rendered.
10. PostgreSQL memory is updated with compact state.
11. JSONL session log receives the full typed transcript events.

### Resume Turn

1. User resumes a session id.
2. `session_log` reads JSONL events and reconstructs recent typed blocks.
3. `conversation_memory` loads or rebuilds compact state from PostgreSQL.
4. `agent_context` builds the next payload from compact state plus replayed recent blocks.
5. The resumed session uses the same context builder path as a normal turn.

### Compaction Turn

1. History or payload budget crosses a threshold, or user runs `/compact`.
2. Older turns are summarized into a structured compaction summary.
3. The compaction summary is stored in PostgreSQL and JSONL.
4. Raw older blocks remain in JSONL for audit, but future payloads use the summary.

## Modes

Mode overlays are prompt-fragment filters, not separate agents.

### Auto

Default mode. Execute deterministic tools when confidence is high. Use LLM only for synthesis, ambiguous routing, or tool-driven research.

### Plan

No side-effecting tool execution. Return an execution plan, evidence requirements, expected tools, risk points, and verification steps. Direct read-only context inspection is allowed only if explicitly configured.

### Minimal

Use smaller context and terse answers. Prefer deterministic summaries. Skip optional narrative sections and long follow-ups.

### Audit

Maximize source trails, missing-evidence disclosure, tool traces, freshness labels, and claim gates. Use for debugging and report validation.

### Debug

Expose route decisions, context section budgets, selected tool schemas, reminders, and loop-depth metrics. Do not expose private chain-of-thought.

## First Implementation Slice

The first slice should cover only the harness foundation:

- `AA-CM-1` Canonical LLM Context Builder
- `AA-CM-16` First-Class Tool Call Blocks Across Providers
- `AA-CM-14` Full Typed Session Transcript Log
- `AA-CM-20` Per-Turn Payload Replay Contract
- `AA-CM-22` Prompt Fragment Registry + Runtime System Reminders
- `AA-CM-18` Live `/context` Budget Breakdown

Deferred until after the foundation:

- resume, rewind, and fork
- todo ledger
- live workspace search
- deferred full tool schema loading
- manual `/compact`
- parallel read-only worker execution

## Error Handling

- Memory persistence failures must remain fail-open.
- JSONL logging failures must never block market answers.
- Provider adapter failures should return a clear backend error and preserve the session log event.
- Malformed tool calls should be rejected before side effects.
- Repeated tool failures should stop the loop and render the blocker.
- Oversized tool results should be summarized before entering the next payload.
- Missing market evidence should block market claims, not produce generic narrative.

## Testing Strategy

### Unit Tests

- Prompt fragments render in priority order and obey mode filters.
- Runtime reminders appear only when their trigger facts are present.
- Context builder includes and excludes sections deterministically under budget.
- Provider-neutral blocks project correctly into OpenAI-compatible messages.
- JSONL events append with stable schema and redaction.
- Payload replay reconstructs the same provider-neutral sequence.

### Scenario Tests

Cover these scenarios:

- stock brief with fresh EOD data
- stock brief with stale EOD data
- F&O overview with missing options evidence
- NSE live quote failure / 403 fallback
- email pipe after captured output
- `/plan` mode
- `/minimal` mode
- `/audit` mode
- repeated tool failure
- context budget exceeded

### Snapshot Tests

Snapshot the assembled context sections, not raw model responses. Snapshots should redact timestamps, session ids, paths where needed, and volatile market prices.

## Acceptance Criteria

- `_llm_query()` no longer manually assembles the full prompt string and history list.
- `terminal.agent_context` is the single entry point for LLM payload construction.
- Tool calls and tool results are persisted as typed blocks in JSONL.
- `/context --prompt` can display included fragments, reminders, memory sections, selected schemas, and budget usage.
- Prompt fragments are named, mode-aware, budgeted, and test-covered.
- Runtime reminders cover stale data, missing evidence, low confidence, repeated failures, and budget warnings.
- No vendor or extracted prompt text is copied verbatim.
- Existing deterministic market routes keep passing their current tests.
- Market facts remain grounded in tools, PostgreSQL, CSVs, or generated reports, never prompt memory alone.

## Rollout Plan

1. Add read-only modules and tests with no runtime wiring.
2. Wire context builder behind an environment flag.
3. Log JSONL transcript events in shadow mode.
4. Add `/context --prompt` and compare against existing prompt behavior.
5. Switch LLM path to context builder by default.
6. Add replay tests from JSONL.
7. Remove duplicated prompt assembly from `terminal.agent`.

## Implementation Defaults

- JSONL schema version starts as `agent_adda_session_log.v1`.
- Phase-one `/plan` mode does not execute side-effecting tools. Read-only context inspection remains disabled by default and can be enabled later with an explicit flag.
- Prompt fragments live in Python dataclasses first. Markdown/YAML loading can be added later if the registry proves stable.
- Phase one uses character-count budgets with a conservative token estimate of `chars / 4`. Exact tokenizer counts can be added later behind the same budget interface.
