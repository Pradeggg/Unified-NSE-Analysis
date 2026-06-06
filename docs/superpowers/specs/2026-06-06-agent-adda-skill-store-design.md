# Agent Adda Skill Store Design

Date: 2026-06-06
Scope: Agent Adda user-query understanding, situation assessment, tool planning, and reusable scenario memory
Status: design-only
Stance: research and learning only; not investment advice

Related artifacts:

- Backlog: `docs/superpowers/plans/2026-06-06-agent-adda-skill-store-backlog.md`
- Existing situation assessment design: `docs/superpowers/specs/2026-05-15-first-class-situation-assessment-design.md`
- Existing skills MVP plan: `docs/superpowers/plans/2026-06-04-agent-adda-skills-mvp.md`
- Existing copilot backlog: `docs/superpowers/plans/2026-06-04-agent-adda-copilot-superpowers-backlog.md`

## Purpose

Agent Adda already has PostgreSQL-backed market data, deterministic tools, reports, slash commands, natural-language routing, a situation assessment layer, and a small first-generation skills package. The next step is to make Agent Adda learn reusable workflows from prior and synthetic scenarios without allowing untrusted generated code or prompts to bypass evidence controls.

This design adds a validated skill store: a PostgreSQL-backed retrieval layer containing thousands of tested scenario cards. Each card maps a class of user input to an evidence plan, allowed tools, SQL templates, validation rules, and synthesis guidance. At runtime, Agent Adda retrieves relevant cards during situation assessment, reviews them, executes only through trusted tools and PostgreSQL, validates the outputs, and then passes evidence to the final synthesizer.

The skill store is not a prompt dump and not an autonomous code executor. It is a retrieval-backed planning aid with validation gates.

## Goals

- Store reusable Agent Adda workflows as versioned, testable skill cards.
- Generate large numbers of candidate scenarios with LLMs, but promote only validated cards into runtime use.
- Improve open-ended user queries by retrieving similar validated scenarios before falling to the generic LLM loop.
- Keep deterministic slash commands and prompt-library routes authoritative.
- Use PostgreSQL as the system of record and add vector search through `pgvector` rather than introducing a second database in the first version.
- Make every retrieved workflow auditable: why it matched, what evidence it requires, what tools it can run, and what validation passed.
- Prevent vector retrieval from executing arbitrary code, SQL, or prompt text.
- Capture feedback and runtime outcomes so skill quality improves over time.

## Non-Goals

- No broker order execution.
- No investment advice or unmanaged buy/sell recommendations.
- No hidden chain-of-thought exposure.
- No runtime execution of LLM-generated Python or arbitrary SQL.
- No replacement of existing slash commands, `terminal.tools`, unified router, or situation assessment.
- No dependence on vector similarity alone for routing.
- No production use of untested synthetic scenarios.
- No separate vector database in V1 unless PostgreSQL vector search proves insufficient.

## Product Contract

When the user enters an open-ended query, Agent Adda should first decide whether deterministic routing can answer it. If not, the skill store can contribute a structured plan.

Example:

```text
User: Do a last 3 months market analysis and find swing candidates

Skill retrieval:
  1. market_3m_rotation_swing_v1
  2. stage2_sector_leadership_watchlist_v1
  3. vcp_breakout_with_fundamentals_v1

Reviewer:
  selected market_3m_rotation_swing_v1
  required tables available
  SQL templates read-only and parameterized
  evidence contract complete

Execution:
  market.index_eod -> index returns
  scores.stage_snapshots -> stage distribution
  market.equity_eod + scores.stage_snapshots -> sector returns and candidates
  scores.stage2_vcp_picks -> VCP overlap

Synthesis:
  market regime, sector leadership, focus list, risks, source trail
```

The visible answer may show a compact operational trace, but it must not expose private reasoning. It should show:

- selected skill card
- evidence plan
- source freshness
- validation status
- missing evidence
- final result

## Architecture Overview

```text
user query
  |
  v
input normalizer
  |
  v
deterministic bypass
  |-- slash command / exact prompt / high-confidence router -> existing path
  |
  v
skill retrieval candidate stage
  |
  v
reranker + reviewer
  |
  v
validated execution plan
  |
  v
trusted tools + read-only PG executor
  |
  v
evidence validator
  |
  v
final synthesizer + source trail
```

## Runtime Placement

The best integration point is inside the situation assessment phase, after deterministic routing guards and before the generic keyword/LLM fallback.

Current pipeline in `terminal/agent.py` is:

```text
_stage_clarification_binding
_stage_unified_router
_stage_entity_topic
_stage_situation_assessment
_stage_keyword_and_llm
```

Recommended V1 placement:

```text
_stage_clarification_binding
_stage_unified_router
_stage_entity_topic
_stage_skill_store_assessment
_stage_situation_assessment
_stage_keyword_and_llm
```

This placement keeps deterministic commands safe:

- `/research RELIANCE` continues through the command path.
- `/screen stage2` continues through the screener path.
- Known prompt-library routes continue unchanged.
- Contextual follow-ups can still use existing situation assessment.
- Open-ended, multi-step, ambiguous analytical queries get skill retrieval before generic LLM fallback.

The skill store can also be called from existing situation assessment when a contextual follow-up is both prior-context-aware and analytically open-ended.

## Skill Card Model

A skill card is a declarative, versioned object.

Required fields:

- `id`: stable unique id, for example `market_3m_rotation_swing_v1`.
- `version`: integer version.
- `status`: `generated`, `test_failed`, `review_pending`, `validated`, `production`, or `deprecated`.
- `domain`: `market_analysis`, `symbol_research`, `portfolio_review`, `screening`, `report_qa`, `data_debugging`, or `agent_workflow`.
- `title`: user-readable name.
- `description`: concise workflow description.
- `input_patterns`: sample user asks that this skill handles.
- `tags`: normalized retrieval tags.
- `intent_tags`: route-level labels such as `market_regime`, `sector_rotation`, `swing_trading`.
- `entities_required`: symbols, sector, index, timeframe, portfolio, or none.
- `evidence_required`: required tables, reports, tools, and freshness constraints.
- `tool_plan_template`: allowed tool names and argument templates.
- `sql_templates`: named, read-only, parameterized SQL templates where needed.
- `validation_rules`: checks that must pass after execution.
- `output_contract`: structured fields the skill must produce.
- `synthesis_guidance`: public instructions for final rendering.
- `test_fixtures`: deterministic inputs for offline testing.
- `eval_scores`: precision, reviewer pass rate, execution pass rate, last regression status.
- `created_by`: `llm_generated`, `human_authored`, or `runtime_promoted`.
- `created_at`, `updated_at`, `last_validated_at`.

Example:

```yaml
id: market_3m_rotation_swing_v1
version: 1
status: validated
domain: market_analysis
title: 3M Market Rotation Swing Assessment
description: Analyze broad market, sector rotation, Weinstein stages, and liquid Stage 2 swing candidates.
input_patterns:
  - last 3 months market analysis
  - swing candidates from recent sector rotation
  - what changed in market structure over 3 months
tags:
  - market_regime
  - sector_rotation
  - stage_analysis
  - swing_trading
intent_tags:
  - market_situation_assessment
  - swing_watchlist
entities_required:
  - timeframe
evidence_required:
  tables:
    - market.index_eod
    - market.equity_eod
    - scores.stage_snapshots
    - scores.stage2_vcp_picks
  freshness:
    max_eod_age_days: 3
tool_plan_template:
  - tool: run_skill_sql_template
    args:
      skill_id: market_3m_rotation_swing_v1
      template: index_returns_lookback
  - tool: run_skill_sql_template
    args:
      skill_id: market_3m_rotation_swing_v1
      template: stage_distribution_change
output_contract:
  - as_of_date
  - index_returns
  - stage_distribution_change
  - leading_sectors
  - weak_sectors
  - primary_candidates
  - secondary_candidates
  - risks
validation_rules:
  - no_future_dates
  - required_tables_exist
  - sql_is_read_only
  - index_returns_non_empty
  - stage_counts_reasonable
  - candidates_have_liquidity
```

## Storage Design

V1 uses PostgreSQL with `pgvector`.

Recommended schema namespace:

- `agent_skills`

Tables:

- `agent_skills.skill_cards`
- `agent_skills.skill_embeddings`
- `agent_skills.skill_sql_templates`
- `agent_skills.skill_tests`
- `agent_skills.skill_validation_runs`
- `agent_skills.skill_retrieval_logs`
- `agent_skills.skill_execution_logs`
- `agent_skills.skill_feedback`

High-level columns:

```text
skill_cards
  id text primary key
  version integer
  status text
  domain text
  title text
  description text
  input_patterns jsonb
  tags text[]
  intent_tags text[]
  entities_required jsonb
  evidence_required jsonb
  tool_plan_template jsonb
  output_contract jsonb
  synthesis_guidance text
  eval_scores jsonb
  created_by text
  created_at timestamptz
  updated_at timestamptz
  last_validated_at timestamptz

skill_embeddings
  skill_id text references agent_skills.skill_cards(id)
  embedding_model text
  embedding_dimension integer
  embedding vector(...)
  embedding_text text
  created_at timestamptz

skill_sql_templates
  skill_id text
  template_name text
  sql_text text
  parameters jsonb
  read_only boolean
  expected_columns jsonb
  validation_rules jsonb
```

Embedding text should combine:

- title
- description
- input patterns
- tags
- intent tags
- required evidence
- output contract

Do not embed full SQL as the primary retrieval text. SQL can be embedded separately for maintenance/search, but runtime retrieval should match user intent and evidence contracts, not arbitrary query text.

## Offline Generation Pipeline

LLMs can generate thousands of scenario candidates, but every generated scenario starts as untrusted.

Pipeline:

```text
scenario generation
  -> schema normalization
  -> duplicate detection
  -> static validation
  -> SQL/tool dry-run validation
  -> fixture tests
  -> reviewer critique
  -> human or policy promotion
  -> embedding refresh
  -> runtime availability
```

Statuses:

- `generated`: syntactically accepted, not trusted.
- `test_failed`: failed static or execution validation.
- `review_pending`: tests pass but reviewer has not approved.
- `validated`: available for runtime retrieval.
- `production`: repeatedly successful and high confidence.
- `deprecated`: blocked by schema drift, poor results, or replacement.

Only `validated` and `production` cards are eligible at runtime.

## Runtime Retrieval

Retrieval should use multiple signals, not vector search alone.

Candidate generation:

- Vector similarity over normalized user query.
- Tag match from deterministic classifier.
- Intent compatibility from existing router.
- Entity/timeframe compatibility.
- Evidence availability.
- Prior success and freshness.

Fetch size:

- Retrieve top 30 initial candidates.
- Rerank down to top 10.
- Reviewer selects zero, one, or a merged plan from multiple cards.

Reranking signals:

- embedding similarity
- tag overlap
- tool overlap
- output-contract match
- freshness compatibility
- status boost: `production > validated`
- runtime success rate
- recent schema validation
- deterministic route compatibility

The reranker must support abstention. If confidence is low, Agent Adda should use existing situation assessment or ask clarification.

## Reviewer Gate

The reviewer is a deterministic-plus-optional-LLM validation step. It does not execute code.

Checks:

- The skill answers the user ask.
- Required entities are present or can be resolved.
- Required data exists and is fresh enough.
- SQL templates are read-only and parameterized.
- Tool names are in the trusted registry.
- Output contract is sufficient for final synthesis.
- No deterministic command would be better.
- No missing high-stakes guardrails.

Reviewer output:

```json
{
  "decision": "select",
  "selected_skill_id": "market_3m_rotation_swing_v1",
  "confidence": "high",
  "reason": "Matches market regime + sector rotation + swing candidate request.",
  "missing_inputs": [],
  "execution_plan": [
    {"type": "sql_template", "name": "index_returns_lookback"},
    {"type": "sql_template", "name": "stage_distribution_change"}
  ]
}
```

Decisions:

- `select`
- `merge`
- `ask_clarification`
- `fallback_to_router`
- `reject`

## Execution Guardrails

Runtime execution must be constrained.

Rules:

- Execute only trusted tool registry calls and approved SQL templates.
- SQL must be read-only.
- SQL must be parameterized.
- SQL templates must be stored separately from generated prose.
- Block semicolon-chained statements, DDL, DML, temp functions, unsafe extensions, and unbounded queries.
- Enforce row limits unless the template explicitly permits aggregation.
- Run schema existence checks before execution.
- Attach source freshness to every evidence result.

The final synthesizer receives evidence, not raw unvalidated retrieval cards.

## Validation

Validation happens in two places.

Offline validation:

- schema validates
- SQL parses
- required tables exist
- required tools exist
- fixture run produces expected fields
- output contract can be satisfied
- reviewer critique passes

Runtime validation:

- no future dates
- latest data date reported
- row counts non-empty where required
- candidate counts within expected range
- missing evidence recorded
- numeric sanity checks
- source trail complete
- final answer claims map to evidence fields

## Final Synthesis

The final synthesizer should receive:

- original user query
- selected skill id and title
- public skill description
- executed evidence payloads
- validation results
- missing evidence list
- source trail

It should not receive:

- untrusted candidate cards that were rejected
- arbitrary generated code
- hidden reviewer reasoning

Required final answer structure for complex skill-store runs:

- situation summary
- evidence used
- result
- risks and missing evidence
- source trail
- research-only disclaimer

## Relationship To Existing `terminal/skills`

The current `terminal/skills` package contains static skill definitions and a deterministic fundamental-driver diagnosis skill. The new skill store should extend this model:

- `terminal/skills/schema.py` gains persisted skill card contracts.
- `terminal/skills/registry.py` remains the static built-in registry.
- New modules handle persisted retrieval, validation, and execution.
- Static built-in skills can be mirrored into the database later, but they remain authoritative.

Recommended new modules:

- `terminal/skills/store_schema.py`
- `terminal/skills/retriever.py`
- `terminal/skills/reranker.py`
- `terminal/skills/reviewer.py`
- `terminal/skills/executor.py`
- `terminal/skills/validator.py`
- `terminal/skills/generator.py`
- `terminal/skills/ingest.py`

## Failure Modes

When retrieval fails:

- Continue existing routing or ask clarification.

When a selected skill fails validation:

- Show `skill_store_validation_failed`.
- Include missing table/tool/evidence.
- Do not synthesize unsupported conclusions.

When SQL returns empty:

- Report empty result as evidence.
- Offer likely reasons: stale data, filters too strict, missing latest load.

When vector search returns irrelevant candidates:

- Reviewer must reject or fallback.
- Log the miss for evaluation.

## Observability

Every skill-store runtime turn should log:

- user query hash and normalized query
- deterministic bypass decision
- retrieved candidates and scores
- reranked candidates
- reviewer decision
- selected skill id
- executed tools/templates
- validation outcome
- final intent
- user feedback if provided

Logs should be stored in PostgreSQL and optionally JSONL for debugging.

## Rollout Plan

Phase 1: Schema and static seed cards.

Phase 2: Retrieval and dry-run CLI.

Phase 3: Reviewer and execution guardrails.

Phase 4: Situation-assessment integration behind a feature flag.

Phase 5: Offline LLM scenario generation and repair loop.

Phase 6: Runtime feedback and production promotion.

## Acceptance Criteria

- Deterministic commands are not intercepted by skill retrieval.
- Only `validated` and `production` cards are eligible at runtime.
- The retriever can return top candidates for at least 50 benchmark user queries.
- The reviewer can reject irrelevant retrieved skills.
- Execution is limited to trusted tools and approved read-only SQL templates.
- A 3-month market analysis query can run end-to-end from retrieved skill to validated evidence to final synthesis.
- All skill-store answers include source trail and validation status.
- Missing evidence blocks unsupported claims.
