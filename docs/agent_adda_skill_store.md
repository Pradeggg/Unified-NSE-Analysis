# Agent Adda Skill Store Operator Guide

The Skill Store is Agent Adda's local repository for reusable workflow cards. A card captures when a workflow should be used, what evidence it must collect, which read-only SQL or tool steps are allowed, and what output contract the final answer must satisfy.

Runtime retrieval is intentionally conservative. Generated skills are untrusted and must not be used by the main workflow until validation and promotion gates pass.

## Storage And Retrieval

Skill cards live in PostgreSQL under the `agent_skills` schema. Embeddings are stored with pgvector so runtime retrieval can match user intent against input patterns, tags, descriptions, and output contracts.

The runtime may only retrieve statuses that are explicitly eligible:

- `generated`: created by learning or mining; not runtime eligible.
- `review_pending`: awaiting operator review; not runtime eligible.
- `validated`: passed validation; runtime eligible.
- `production`: approved default runtime card; runtime eligible.
- `test_failed`: failed validation; not runtime eligible.
- `deprecated`: retained for audit; not runtime eligible.

## Operator Loop

Use this loop for every new or changed card:

1. Generate or mine a candidate from successful traces, repeated user phrasing, or a deliberate design task.
2. Validate the card against read-only SQL checks, required tables, evidence requirements, output contract checks, and replay scenarios.
3. Promote only after validation evidence is present and the card improves grounded answers without breaking deterministic routing.
4. Deprecate cards that are stale, redundant, unsafe, or producing low-quality retrieval matches.

The common verbs are validate, promote, and deprecate. If a command is not available in the current shell, perform the same action through the repository helpers and record the decision in the card metadata.

## Learning Capture

Daily learning capture records useful interaction patterns without changing answers. The learning path must remain observational: it can write proposals and logs, but it cannot alter the response selected for the user.

The 14-day pattern mining flow looks for repeated high-value workflows, repeated missing-evidence failures, and repeated user requests that map to the same evidence chain. Run learning analyze on the collected traces, review the generated proposal, then validate before promotion.

Proposal approval is a human gate. A proposal should explain:

- the user situations it covers
- the intended status transition
- required evidence
- SQL and tool constraints
- expected answer shape
- known failure modes

## Inspection

Use `/skills` in Agent Adda for read-only runtime inspection.

- `/skills` shows status counts and runtime-eligible cards.
- `/skills search VCP fundamentals` searches only validated and production cards.
- `/skills show market_3m_rotation_swing_v1` renders the card contract, evidence requirements, and validation rules.
- `/skills recent` shows recent retrieval logs and execution logs.

For deeper audits, query retrieval logs in `agent_skills.skill_retrieval_logs` and execution logs in `agent_skills.skill_execution_logs`. Retrieval logs are required before runtime enablement because they prove what was selected, what was skipped, and whether the chosen card stayed inside the expected contract.

## Safety Guardrails

- Generated skills are untrusted until explicitly validated or promoted.
- Runtime retrieval must exclude `generated`, `review_pending`, `test_failed`, and `deprecated`.
- SQL templates must be read-only and must reject DDL, DML, comments used for injection, multi-statement execution, and unsafe table access.
- Cards must name their evidence requirements and output contract.
- Learning capture must not affect the current user answer.
- Missing evidence should be surfaced to the synthesizer instead of filled with assumptions.
- Runtime retrieval is enabled by default after the release gate has passed and user approval has been recorded. Use `AGENT_ADDA_SKILL_STORE=0` as the explicit kill switch.

## Examples

### 3M Market Analysis

Use a market-analysis card for questions such as "last 3 months market analysis and swing candidates." Required evidence should include index returns, sector rotation, breadth, relative strength, and a ranked candidate list. The output contract should make the time window explicit and separate market regime, sector strength, candidates, and risks.

### VCP Breakouts With Fundamentals

Use a screening card for questions such as "VCP breakouts with fundamentals." Required evidence should include the contraction pattern, breakout proximity, volume behavior, relative strength, and fundamental quality. The output should include candidates, filters passed, TradingView symbols when requested, and risks.

### Portfolio Add Or Trim

Use a portfolio card only when holdings or watchlist evidence is available. Required evidence should include current positions, P&L, trend state, risk concentration, and available alternatives. The output should separate add, hold, trim, and exit candidates, with each recommendation tied back to evidence.

## Runtime Enablement Gate

Skill Store retrieval is now a runtime feature by default. Before changing that default again, confirm:

- benchmark pass rate is at or above the agreed threshold
- deterministic routing smoke tests pass with `AGENT_ADDA_SKILL_STORE=0`
- skill-store E2E and benchmark tests pass with `AGENT_ADDA_SKILL_STORE=1`
- unsafe SQL tests pass
- retrieval logs are written
- learning capture remains answer-neutral
- explicit user approval has been recorded

The release-gate preflight is read-only. It reports whether the system is ready and whether default runtime enablement is allowed. It does not edit configuration; use `AGENT_ADDA_SKILL_STORE=0` to disable the runtime path for a process.
