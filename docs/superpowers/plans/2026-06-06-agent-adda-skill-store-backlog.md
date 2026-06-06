# Agent Adda Skill Store Implementation Backlog

> For agentic workers: this backlog is implementation-ready. Claim one task row at a time, read the listed context first, keep edits scoped to the named files, and run the task-specific verification before handing off.

**Goal:** Build a validated scenario and skill retrieval layer for Agent Adda. The store will contain LLM-generated and human-authored scenario cards, but only tested and validated cards can influence runtime planning. Runtime execution remains constrained to trusted Agent Adda tools and read-only PostgreSQL templates.

**Primary outcome:** When a user asks an open-ended query, Agent Adda can retrieve similar validated workflows, rank and review them, execute the best evidence plan, validate the output, and synthesize a grounded answer with a visible source trail.

**Architecture principle:** Retrieval suggests plans. It does not execute plans. Execution flows through trusted tool registry calls, approved SQL templates, and evidence validators.

```text
user query
  -> deterministic bypass
  -> skill retrieval
  -> reranker
  -> reviewer
  -> trusted execution
  -> evidence validation
  -> final synthesis
  -> retrieval/execution feedback log
```

**Tech stack:** Python 3.10+, PostgreSQL, pgvector, existing `terminal.tools`, existing `terminal.situation_assessment`, existing `terminal.skills`, pytest, no broker integration, no untrusted code execution.

## Coordination Rules

- Do not edit generated reports/data unless a task explicitly asks for report regeneration.
- Keep changes out of `nse_agent.py` where a focused module can own the behavior.
- Runtime skill retrieval must be feature-flagged until the benchmark suite passes.
- Only runtime statuses `validated` and `production` are eligible for user-query execution.
- LLM-generated skills start as `generated`; they cannot be runtime eligible until tests and reviewer gates pass.
- Never execute arbitrary generated Python, shell, or SQL from a skill card.
- SQL templates must be read-only, parameterized, row-limited, and validated before execution.
- Existing slash commands and high-confidence deterministic routing must remain authoritative.
- Use `.venv/bin/python -m pytest`, not bare `pytest`.
- If the worktree is dirty, stage only files required for the claimed row.

## Canonical Context To Read

- `docs/superpowers/specs/2026-06-06-agent-adda-skill-store-design.md`
- `terminal/agent.py`
- `terminal/situation_assessment.py`
- `terminal/skills/schema.py`
- `terminal/skills/registry.py`
- `terminal/skills/selector.py`
- `terminal/tools.py`
- `terminal/router/providers.py`
- `terminal/router/validation.py`
- `terminal/postgres_tools.py`
- `scripts/maintenance/benchmark_agent_models.py`
- `docs/superpowers/plans/2026-06-04-agent-adda-skills-mvp.md`
- `docs/superpowers/plans/2026-06-04-agent-adda-copilot-superpowers-backlog.md`

## Status Legend

| Status | Meaning |
|---|---|
| READY | Can be picked up now |
| BLOCKED | Needs dependency or product decision |
| PARTIAL | Some code exists but integration/tests are incomplete |
| DONE | Implemented, tested, and wired |
| DEFERRED | Intentionally later |

## Work Lanes

| Lane | Owns | Can Run In Parallel With |
|---|---|---|
| Data Model | PostgreSQL schema, pgvector extension, migrations | Test fixtures |
| Skill Contracts | Python dataclasses, JSON schema, validators | Data model |
| Retrieval | embeddings, vector search, tag search | Scenario generator after schema stabilizes |
| Reranking | score fusion, abstention, deterministic compatibility | Retrieval |
| Reviewer | selected skill validation, fallback decisions | Reranking |
| Execution | SQL template runner, tool-plan adapter | Reviewer after contracts stabilize |
| Runtime Integration | situation-assessment stage, feature flag, visible trace | Retrieval dry-run |
| Offline Generation | LLM scenario generator, repair loop, promotion | Data model and contracts |
| Evaluation | benchmark queries, regression suite, quality metrics | Runtime integration |
| Operations | logs, feedback, maintenance commands | All lanes |

---

## Epic AA-SKILLSTORE-0: Product Contract And Design Control

### AA-SKILLSTORE-0.1 Finalize Skill Store Product Contract

**Status:** READY  
**Priority:** P0  
**Suggested owner:** Product/spec assistant  
**Files:**
- Modify: `docs/superpowers/specs/2026-06-06-agent-adda-skill-store-design.md`
- Modify: `docs/superpowers/plans/2026-06-06-agent-adda-skill-store-backlog.md`

**Work:**
- [ ] Review the design with the user.
- [ ] Confirm whether V1 uses PostgreSQL + pgvector only.
- [ ] Confirm runtime placement after deterministic router and before contextual situation assessment.
- [ ] Confirm that generated skills are not runtime eligible until validation.
- [ ] Confirm V1 domains:
  - market analysis
  - stock research
  - screening
  - portfolio review
  - report QA
  - data debugging

**Acceptance Criteria:**
- Design has no unresolved product choices.
- Backlog reflects accepted scope.
- No section contains unfinished marker text.

**Verification:**

```bash
.venv/bin/python - <<'PY'
from pathlib import Path
markers = ["TO" + "DO", "TB" + "D", "FIX" + "ME", "UN" + "RESOLVED", "decide" + " later"]
paths = [
    Path("docs/superpowers/specs/2026-06-06-agent-adda-skill-store-design.md"),
    Path("docs/superpowers/plans/2026-06-06-agent-adda-skill-store-backlog.md"),
]
hits = []
for path in paths:
    for lineno, line in enumerate(path.read_text().splitlines(), 1):
        if any(marker in line for marker in markers):
            hits.append(f"{path}:{lineno}:{line}")
if hits:
    raise SystemExit("\n".join(hits))
PY
```

Expected: no unfinished markers.

---

## Epic AA-SKILLSTORE-1: PostgreSQL And pgvector Foundation

### AA-SKILLSTORE-1.1 Add Agent Skills Schema Migration

**Status:** READY  
**Priority:** P0  
**Suggested owner:** PostgreSQL assistant  
**Dependencies:** AA-SKILLSTORE-0.1  
**Files:**
- Modify: `postgres/schema.sql`
- Create: `tests/test_skill_store_schema.py`

**Work:**
- [ ] Add `CREATE EXTENSION IF NOT EXISTS vector;`.
- [ ] Add schema `agent_skills`.
- [ ] Add tables:
  - `agent_skills.skill_cards`
  - `agent_skills.skill_embeddings`
  - `agent_skills.skill_sql_templates`
  - `agent_skills.skill_tests`
  - `agent_skills.skill_validation_runs`
  - `agent_skills.skill_retrieval_logs`
  - `agent_skills.skill_execution_logs`
  - `agent_skills.skill_feedback`
- [ ] Add status constraints for:
  - `generated`
  - `test_failed`
  - `review_pending`
  - `validated`
  - `production`
  - `deprecated`
- [ ] Add indexes:
  - `skill_cards(status)`
  - `skill_cards(domain)`
  - `skill_cards(tags)`
  - vector ANN index on `skill_embeddings.embedding`
- [ ] Add `updated_at` fields and uniqueness constraints for `(id, version)`.

**Acceptance Criteria:**
- Schema can be applied to an empty local database.
- Tables exist under `agent_skills`.
- Invalid statuses are rejected.
- `skill_embeddings` records model and dimension explicitly.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_skill_store_schema.py -q
```

### AA-SKILLSTORE-1.2 Add Skill Store Repository Layer

**Status:** READY  
**Priority:** P0  
**Suggested owner:** Persistence assistant  
**Dependencies:** AA-SKILLSTORE-1.1  
**Files:**
- Create: `terminal/skills/store_repo.py`
- Test: `tests/test_skill_store_repo.py`

**Work:**
- [ ] Add `SkillStoreRepository`.
- [ ] Implement methods:
  - `upsert_skill_card(card)`
  - `get_skill_card(skill_id, version=None)`
  - `list_runtime_eligible(domain=None)`
  - `save_embedding(skill_id, model, dimension, vector, embedding_text)`
  - `log_retrieval(event)`
  - `log_execution(event)`
  - `save_feedback(event)`
- [ ] Use parameterized SQL only.
- [ ] Return plain dataclasses or dictionaries, not pandas objects.

**Acceptance Criteria:**
- Repository can insert, update, fetch, and list cards.
- Only `validated` and `production` cards are returned by `list_runtime_eligible`.
- Tests do not require live external network.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_skill_store_repo.py -q
```

---

## Epic AA-SKILLSTORE-2: Skill Card Contracts

### AA-SKILLSTORE-2.1 Add Skill Card Dataclasses

**Status:** READY  
**Priority:** P0  
**Suggested owner:** Contracts assistant  
**Dependencies:** AA-SKILLSTORE-0.1  
**Files:**
- Create: `terminal/skills/store_schema.py`
- Test: `tests/test_skill_store_contracts.py`

**Work:**
- [ ] Add dataclasses:
  - `SkillCard`
  - `SkillEvidenceRequirement`
  - `SkillSQLTemplate`
  - `SkillToolTemplate`
  - `SkillValidationRule`
  - `SkillRetrievalCandidate`
  - `SkillReviewerDecision`
- [ ] Add serialization helpers:
  - `skill_card_to_dict`
  - `skill_card_from_dict`
- [ ] Validate required fields at construction or via explicit validator.
- [ ] Ensure `status` is typed and restricted.

**Acceptance Criteria:**
- Minimal valid card serializes and deserializes losslessly.
- Missing `id`, `domain`, `status`, or `output_contract` fails validation.
- Invalid runtime status cannot be marked eligible.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_skill_store_contracts.py -q
```

### AA-SKILLSTORE-2.2 Add JSON Schema Export For Skill Cards

**Status:** READY  
**Priority:** P1  
**Suggested owner:** Contracts assistant  
**Dependencies:** AA-SKILLSTORE-2.1  
**Files:**
- Create: `terminal/skills/store_contract.schema.json`
- Modify: `terminal/skills/store_schema.py`
- Test: `tests/test_skill_store_contract_schema.py`

**Work:**
- [ ] Define JSON schema for imported/generated skill cards.
- [ ] Add a validator function for dict payloads.
- [ ] Keep schema strict enough to reject unknown execution types.
- [ ] Permit future metadata under `metadata`.

**Acceptance Criteria:**
- Valid fixture passes.
- Unknown execution type fails.
- Missing validation rules fails for SQL-backed cards.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_skill_store_contract_schema.py -q
```

---

## Epic AA-SKILLSTORE-3: SQL Template Safety

### AA-SKILLSTORE-3.1 Add Read-Only SQL Template Validator

**Status:** READY  
**Priority:** P0  
**Suggested owner:** SQL safety assistant  
**Dependencies:** AA-SKILLSTORE-2.1  
**Files:**
- Create: `terminal/skills/sql_safety.py`
- Test: `tests/test_skill_sql_safety.py`

**Work:**
- [ ] Add static SQL checks:
  - starts with `SELECT` or `WITH`
  - rejects `INSERT`, `UPDATE`, `DELETE`, `DROP`, `CREATE`, `ALTER`, `TRUNCATE`, `GRANT`, `COPY`, `CALL`, `DO`
  - rejects semicolon-chained statements
  - rejects `pg_sleep`
  - rejects unparameterized string formatting markers
- [ ] Add required parameter validation.
- [ ] Add optional expected-column validation.
- [ ] Return structured failures, not booleans only.

**Acceptance Criteria:**
- Safe `WITH ... SELECT` passes.
- DDL/DML fails.
- Multiple statements fail.
- Missing required params fails.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_skill_sql_safety.py -q
```

### AA-SKILLSTORE-3.2 Add Approved SQL Template Runner

**Status:** READY  
**Priority:** P0  
**Suggested owner:** Execution assistant  
**Dependencies:** AA-SKILLSTORE-1.2, AA-SKILLSTORE-3.1  
**Files:**
- Create: `terminal/skills/sql_runner.py`
- Test: `tests/test_skill_sql_runner.py`

**Work:**
- [ ] Implement `run_skill_sql_template(skill_id, template_name, params)`.
- [ ] Load template from repository.
- [ ] Validate SQL safety before execution.
- [ ] Enforce read-only transaction.
- [ ] Enforce timeout and row limit.
- [ ] Return JSON-serializable result:
  - columns
  - rows
  - row_count
  - as_of_date if available
  - warnings

**Acceptance Criteria:**
- Runner executes approved read-only query.
- Runner blocks unsafe template.
- Runner labels empty result clearly.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_skill_sql_runner.py -q
```

---

## Epic AA-SKILLSTORE-4: Embeddings And Retrieval

### AA-SKILLSTORE-4.1 Add Embedding Text Builder

**Status:** READY  
**Priority:** P0  
**Suggested owner:** Retrieval assistant  
**Dependencies:** AA-SKILLSTORE-2.1  
**Files:**
- Create: `terminal/skills/embedding_text.py`
- Test: `tests/test_skill_embedding_text.py`

**Work:**
- [ ] Build embedding text from:
  - title
  - description
  - input patterns
  - tags
  - intent tags
  - evidence requirements
  - output contract
- [ ] Exclude full SQL by default.
- [ ] Normalize whitespace.
- [ ] Include stable separators.

**Acceptance Criteria:**
- Embedding text contains user-facing patterns.
- SQL text is excluded.
- Output is deterministic for same card.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_skill_embedding_text.py -q
```

### AA-SKILLSTORE-4.2 Add Embedding Provider Abstraction

**Status:** READY  
**Priority:** P1  
**Suggested owner:** Retrieval assistant  
**Dependencies:** AA-SKILLSTORE-4.1  
**Files:**
- Create: `terminal/skills/embedding_provider.py`
- Test: `tests/test_skill_embedding_provider.py`

**Work:**
- [ ] Add interface `embed_texts(texts, model)`.
- [ ] Add deterministic fake provider for tests.
- [ ] Add OpenAI provider behind environment configuration.
- [ ] Record model name and dimension.
- [ ] Fail gracefully when no provider is configured.

**Acceptance Criteria:**
- Tests use fake provider only.
- OpenAI provider is optional.
- Dimension mismatch fails before DB insert.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_skill_embedding_provider.py -q
```

### AA-SKILLSTORE-4.3 Add Skill Retriever

**Status:** READY  
**Priority:** P0  
**Suggested owner:** Retrieval assistant  
**Dependencies:** AA-SKILLSTORE-1.2, AA-SKILLSTORE-4.2  
**Files:**
- Create: `terminal/skills/retriever.py`
- Test: `tests/test_skill_retriever.py`

**Work:**
- [ ] Implement `retrieve_skill_candidates(query, top_n=30)`.
- [ ] Search only `validated` and `production` cards by default.
- [ ] Combine vector candidates with tag candidates.
- [ ] Return candidate records with:
  - skill id
  - version
  - vector score
  - tag score
  - domain
  - status
  - matched tags
- [ ] Log retrieval event.

**Acceptance Criteria:**
- Generated/test-failed cards are excluded.
- Tag-only retrieval works when embeddings unavailable.
- Retrieval event is logged.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_skill_retriever.py -q
```

---

## Epic AA-SKILLSTORE-5: Reranking And Reviewer

### AA-SKILLSTORE-5.1 Add Deterministic Reranker

**Status:** READY  
**Priority:** P0  
**Suggested owner:** Ranking assistant  
**Dependencies:** AA-SKILLSTORE-4.3  
**Files:**
- Create: `terminal/skills/reranker.py`
- Test: `tests/test_skill_reranker.py`

**Work:**
- [ ] Implement weighted score fusion over:
  - vector score
  - tag overlap
  - intent compatibility
  - evidence availability
  - output contract match
  - runtime success rate
  - status boost
- [ ] Implement reciprocal-rank fusion helper.
- [ ] Add abstention threshold.
- [ ] Return top 10 by default.

**Acceptance Criteria:**
- Strong tag and intent match can outrank weak vector match.
- Low-confidence candidate set abstains.
- Production card gets a modest boost, not an automatic win.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_skill_reranker.py -q
```

### AA-SKILLSTORE-5.2 Add Skill Reviewer

**Status:** READY  
**Priority:** P0  
**Suggested owner:** Reviewer assistant  
**Dependencies:** AA-SKILLSTORE-5.1, AA-SKILLSTORE-3.1  
**Files:**
- Create: `terminal/skills/reviewer.py`
- Test: `tests/test_skill_reviewer.py`

**Work:**
- [ ] Implement reviewer decisions:
  - `select`
  - `merge`
  - `ask_clarification`
  - `fallback_to_router`
  - `reject`
- [ ] Check:
  - skill answers user ask
  - required entities present or resolvable
  - required tools exist
  - required tables exist
  - SQL templates safe
  - output contract sufficient
  - deterministic command not clearly better
- [ ] Return structured reason and missing inputs.

**Acceptance Criteria:**
- Reviewer rejects irrelevant high-vector candidate.
- Reviewer selects valid market 3M skill for 3M swing query.
- Reviewer asks clarification when timeframe is required but absent.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_skill_reviewer.py -q
```

---

## Epic AA-SKILLSTORE-6: Execution And Evidence Validation

### AA-SKILLSTORE-6.1 Add Skill Execution Planner

**Status:** READY  
**Priority:** P0  
**Suggested owner:** Execution assistant  
**Dependencies:** AA-SKILLSTORE-5.2  
**Files:**
- Create: `terminal/skills/execution_plan.py`
- Test: `tests/test_skill_execution_plan.py`

**Work:**
- [ ] Convert reviewer decision into executable steps.
- [ ] Support step types:
  - `tool_call`
  - `sql_template`
  - `report_lookup`
- [ ] Reject unknown step types.
- [ ] Normalize params.
- [ ] Preserve selected skill id and version.

**Acceptance Criteria:**
- Valid reviewer decision becomes executable plan.
- Missing required params fails.
- Unknown tool or SQL template fails.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_skill_execution_plan.py -q
```

### AA-SKILLSTORE-6.2 Add Skill Evidence Validator

**Status:** READY  
**Priority:** P0  
**Suggested owner:** Evidence assistant  
**Dependencies:** AA-SKILLSTORE-6.1  
**Files:**
- Create: `terminal/skills/evidence_validator.py`
- Test: `tests/test_skill_evidence_validator.py`

**Work:**
- [ ] Validate:
  - no future dates
  - required output keys present
  - required result sets non-empty unless optional
  - source freshness present
  - row counts reasonable
  - candidate filters applied
  - missing evidence captured
- [ ] Return `SkillEvidenceValidation` with pass/fail/warnings.

**Acceptance Criteria:**
- Missing required result set fails.
- Stale data creates warning or failure based on skill requirement.
- Empty optional VCP overlap does not fail market analysis.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_skill_evidence_validator.py -q
```

### AA-SKILLSTORE-6.3 Add Skill Executor

**Status:** READY  
**Priority:** P0  
**Suggested owner:** Execution assistant  
**Dependencies:** AA-SKILLSTORE-3.2, AA-SKILLSTORE-6.1, AA-SKILLSTORE-6.2  
**Files:**
- Create: `terminal/skills/executor.py`
- Test: `tests/test_skill_executor.py`

**Work:**
- [ ] Execute approved plan steps through:
  - existing `terminal.tools.call_tool`
  - approved SQL template runner
  - report lookup helpers
- [ ] Collect evidence payloads.
- [ ] Run evidence validator.
- [ ] Log execution event.
- [ ] Return JSON-serializable execution result.

**Acceptance Criteria:**
- Executor never calls unknown tools.
- Executor blocks invalid SQL step.
- Validation failure prevents final synthesis from claiming success.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_skill_executor.py -q
```

---

## Epic AA-SKILLSTORE-7: Seed Production Skills

### AA-SKILLSTORE-7.1 Seed 3M Market Rotation Swing Skill

**Status:** READY  
**Priority:** P0  
**Suggested owner:** Market workflow assistant  
**Dependencies:** AA-SKILLSTORE-3.2, AA-SKILLSTORE-6.3  
**Files:**
- Create: `terminal/skills/seed_cards/market_3m_rotation_swing_v1.yml`
- Create: `tests/test_seed_market_3m_rotation_swing.py`

**Work:**
- [ ] Create skill card for:
  - 3-month index returns
  - stage distribution change
  - sector-level 3-month returns
  - liquid Stage 2 candidates
  - VCP overlap
- [ ] Add SQL templates:
  - `index_returns_lookback`
  - `stage_distribution_change`
  - `sector_returns_lookback`
  - `stage2_liquid_candidates`
  - `vcp_latest_candidates`
- [ ] Add validation rules.
- [ ] Mark initial status `validated` only after tests pass.

**Acceptance Criteria:**
- SQL templates compile and pass safety validation.
- Skill execution returns all required output fields on local PG.
- Final evidence includes latest available data date.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_seed_market_3m_rotation_swing.py -q
```

### AA-SKILLSTORE-7.2 Seed VCP Breakouts With Fundamentals Skill

**Status:** READY  
**Priority:** P1  
**Suggested owner:** Screening workflow assistant  
**Dependencies:** AA-SKILLSTORE-7.1  
**Files:**
- Create: `terminal/skills/seed_cards/vcp_breakouts_with_fundamentals_v1.yml`
- Test: `tests/test_seed_vcp_breakouts_with_fundamentals.py`

**Work:**
- [ ] Create skill card for user asks like:
  - stocks creating new highs
  - VCP breakouts
  - breakouts with good fundamentals
  - TradingView watchlist candidates
- [ ] Require:
  - Stage 2
  - RS threshold
  - liquidity threshold
  - technical signal
  - investment/fundamental score
  - optional portfolio overlap
- [ ] Output TradingView-ready symbols and evidence table.

**Acceptance Criteria:**
- Produces bounded candidate list.
- Explains filters.
- Does not invent chart patterns when VCP evidence missing.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_seed_vcp_breakouts_with_fundamentals.py -q
```

### AA-SKILLSTORE-7.3 Seed Portfolio Add/Trim Situation Skill

**Status:** READY  
**Priority:** P1  
**Suggested owner:** Portfolio workflow assistant  
**Dependencies:** AA-SKILLSTORE-7.1  
**Files:**
- Create: `terminal/skills/seed_cards/portfolio_incremental_add_trim_v1.yml`
- Test: `tests/test_seed_portfolio_incremental_add_trim.py`

**Work:**
- [ ] Create skill card for portfolio-aware asks:
  - add incrementally
  - reduce exposure
  - sector concentration
  - stock position sizing
  - existing holdings plus target allocation
- [ ] Require:
  - current holdings
  - portfolio market value
  - sector exposure
  - signal/stage/investment score
  - risk constraints
- [ ] Output:
  - add candidates
  - trim candidates
  - hold candidates
  - sector exposure warnings
  - missing target allocation caveats

**Acceptance Criteria:**
- Skill is portfolio-state-aware.
- It does not treat each day as a fresh greenfield portfolio.
- Missing target allocation is explicitly reported.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_seed_portfolio_incremental_add_trim.py -q
```

---

## Epic AA-SKILLSTORE-8: Runtime Integration

### AA-SKILLSTORE-8.1 Add Skill Store Feature Flag

**Status:** READY  
**Priority:** P0  
**Suggested owner:** Runtime assistant  
**Dependencies:** AA-SKILLSTORE-4.3  
**Files:**
- Create or modify: `terminal/skills/config.py`
- Modify: `terminal/agent.py`
- Test: `tests/test_skill_store_feature_flag.py`

**Work:**
- [ ] Add env flag `AGENT_ADDA_SKILL_STORE=0|1`.
- [ ] Default runtime retrieval to disabled until benchmarks pass.
- [ ] Add config helper `skill_store_enabled()`.
- [ ] Ensure disabled flag has zero behavioral impact.

**Acceptance Criteria:**
- Disabled flag skips retrieval.
- Enabled flag permits dry-run retrieval.
- Existing routing tests pass unchanged when disabled.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_skill_store_feature_flag.py tests/test_routing_smoke.py -q
```

### AA-SKILLSTORE-8.2 Add `_stage_skill_store_assessment`

**Status:** READY  
**Priority:** P0  
**Suggested owner:** Runtime assistant  
**Dependencies:** AA-SKILLSTORE-5.2, AA-SKILLSTORE-8.1  
**Files:**
- Modify: `terminal/agent.py`
- Create: `terminal/skills/runtime_assessment.py`
- Test: `tests/test_skill_store_runtime_assessment.py`

**Work:**
- [ ] Add a pipeline stage after `_stage_entity_topic`.
- [ ] Skip when:
  - feature flag disabled
  - input starts with slash command
  - unified router already returned a result
  - deterministic keyword plan is high-confidence and direct
- [ ] Retrieve, rerank, and review skills.
- [ ] Return `None` on fallback.
- [ ] Return clarification when reviewer asks.
- [ ] Return plan preview in Plan mode.

**Acceptance Criteria:**
- `/screen stage2` is not intercepted.
- `last 3 months market analysis and swing candidates` triggers skill assessment when flag enabled.
- Reviewer rejection falls through to existing route.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_skill_store_runtime_assessment.py -q
```

### AA-SKILLSTORE-8.3 Add Skill Store Visible Trace Renderer

**Status:** READY  
**Priority:** P1  
**Suggested owner:** Renderer assistant  
**Dependencies:** AA-SKILLSTORE-8.2  
**Files:**
- Create: `terminal/renderers/skill_store.py`
- Test: `tests/test_skill_store_renderer.py`

**Work:**
- [ ] Render compact block:
  - selected skill
  - why selected
  - evidence plan
  - validation status
  - missing evidence
- [ ] Avoid private reasoning language.
- [ ] Keep block short unless `/steps on` or verbose profile is active.

**Acceptance Criteria:**
- Renderer shows operational trace, not chain-of-thought.
- Validation failure is visible.
- Missing evidence is visible.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_skill_store_renderer.py -q
```

---

## Epic AA-SKILLSTORE-9: Offline Scenario Generation

### AA-SKILLSTORE-9.1 Add Scenario Generator CLI

**Status:** READY  
**Priority:** P1  
**Suggested owner:** Generation assistant  
**Dependencies:** AA-SKILLSTORE-2.2  
**Files:**
- Create: `scripts/generate_skill_scenarios.py`
- Create: `terminal/skills/generator.py`
- Test: `tests/test_skill_scenario_generator.py`

**Work:**
- [ ] Generate candidate skill cards from seed domains.
- [ ] Support modes:
  - `--domain market_analysis`
  - `--domain screening`
  - `--domain portfolio_review`
  - `--count N`
  - `--dry-run`
- [ ] Output JSONL/YAML files under `data/skill_store/generated/`.
- [ ] Mark all generated cards as `generated`.
- [ ] Do not insert directly as runtime eligible.

**Acceptance Criteria:**
- Dry-run produces valid schema payloads.
- Generated cards cannot be runtime eligible.
- No external API call is required in tests.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_skill_scenario_generator.py -q
```

### AA-SKILLSTORE-9.2 Add Scenario Test And Repair Loop

**Status:** READY  
**Priority:** P1  
**Suggested owner:** Generation assistant  
**Dependencies:** AA-SKILLSTORE-9.1, AA-SKILLSTORE-6.3  
**Files:**
- Create: `scripts/validate_skill_scenarios.py`
- Create: `terminal/skills/scenario_validation.py`
- Test: `tests/test_skill_scenario_validation.py`

**Work:**
- [ ] Load generated skill cards.
- [ ] Run schema validation.
- [ ] Run SQL safety validation.
- [ ] Run fixture execution where possible.
- [ ] Mark failed cards `test_failed`.
- [ ] Mark passed cards `review_pending`.
- [ ] Produce a validation report.

**Acceptance Criteria:**
- Corrupted generated card fails with reasons.
- Safe card advances to `review_pending`.
- Validation report includes counts by status.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_skill_scenario_validation.py -q
```

### AA-SKILLSTORE-9.3 Add Promotion Command

**Status:** READY  
**Priority:** P1  
**Suggested owner:** Operations assistant  
**Dependencies:** AA-SKILLSTORE-9.2  
**Files:**
- Create: `terminal/skills/promote.py`
- Modify: `agent_adda/cli.py`
- Test: `tests/test_skill_promotion.py`

**Work:**
- [ ] Add CLI:
  - `agent_adda skills list`
  - `agent_adda skills validate`
  - `agent_adda skills promote <skill_id>`
  - `agent_adda skills deprecate <skill_id>`
- [ ] Require validation pass before promotion.
- [ ] Log promotion decision.

**Acceptance Criteria:**
- Cannot promote `generated` directly to `production`.
- Can promote `review_pending` to `validated`.
- Can deprecate a bad card.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_skill_promotion.py -q
```

---

## Epic AA-SKILLSTORE-10: Evaluation And Benchmarks

### AA-SKILLSTORE-10.1 Add Skill Retrieval Benchmark Set

**Status:** READY  
**Priority:** P0  
**Suggested owner:** Evaluation assistant  
**Dependencies:** AA-SKILLSTORE-7.1  
**Files:**
- Create: `tests/fixtures/skill_store_benchmark_queries.yml`
- Create: `tests/test_skill_store_benchmarks.py`

**Work:**
- [ ] Add at least 50 benchmark queries across:
  - market analysis
  - swing screening
  - portfolio review
  - stock research
  - report QA
  - data debugging
- [ ] Define expected skill ids or expected abstention.
- [ ] Test retrieval + reranking + reviewer decision.

**Acceptance Criteria:**
- 90% of benchmark queries select expected skill or correctly abstain.
- Deterministic slash-command examples abstain.
- Bad/ambiguous queries ask clarification or abstain.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_skill_store_benchmarks.py -q
```

### AA-SKILLSTORE-10.2 Add End-To-End Skill Store Smoke Tests

**Status:** READY  
**Priority:** P0  
**Suggested owner:** Evaluation assistant  
**Dependencies:** AA-SKILLSTORE-8.2, AA-SKILLSTORE-10.1  
**Files:**
- Modify: `scripts/smoke_user_flows.sh`
- Create: `tests/test_skill_store_e2e.py`

**Work:**
- [ ] Add smoke cases:
  - 3M market analysis and swing candidates
  - VCP breakouts with good fundamentals
  - portfolio add/trim review
  - deterministic command bypass
- [ ] Assert source trail and validation block appear.
- [ ] Assert generated/test_failed cards are not used.

**Acceptance Criteria:**
- E2E tests pass with skill store enabled.
- Existing smoke flows pass with skill store disabled.

**Verification:**

```bash
AGENT_ADDA_SKILL_STORE=1 .venv/bin/python -m pytest tests/test_skill_store_e2e.py -q
AGENT_ADDA_SKILL_STORE=0 .venv/bin/python -m pytest tests/test_routing_smoke.py -q
```

---

## Epic AA-SKILLSTORE-11: Observability And Feedback

### AA-SKILLSTORE-11.1 Add Retrieval And Execution Logs

**Status:** READY  
**Priority:** P1  
**Suggested owner:** Observability assistant  
**Dependencies:** AA-SKILLSTORE-1.2, AA-SKILLSTORE-8.2  
**Files:**
- Create: `terminal/skills/telemetry.py`
- Test: `tests/test_skill_store_telemetry.py`

**Work:**
- [ ] Log retrieval:
  - query hash
  - normalized query
  - candidates
  - scores
  - reviewer decision
- [ ] Log execution:
  - selected skill
  - executed steps
  - validation status
  - final intent
  - elapsed time
- [ ] Avoid storing sensitive raw text when a hash is sufficient.

**Acceptance Criteria:**
- Telemetry is JSON-serializable.
- Missing DB logging does not break user answer.
- Logs can be queried by skill id.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_skill_store_telemetry.py -q
```

### AA-SKILLSTORE-11.2 Add User Feedback Capture

**Status:** READY  
**Priority:** P2  
**Suggested owner:** Feedback assistant  
**Dependencies:** AA-SKILLSTORE-11.1  
**Files:**
- Modify: `terminal/task_memory.py` or create `terminal/skills/feedback.py`
- Test: `tests/test_skill_store_feedback.py`

**Work:**
- [ ] Add feedback API for:
  - useful
  - not useful
  - wrong skill
  - stale data
  - missing evidence
- [ ] Store feedback linked to retrieval/execution id.
- [ ] Feed aggregate feedback into reranker score.

**Acceptance Criteria:**
- Feedback is persisted.
- Reranker can consume aggregate success/failure rates.
- Feedback failures do not break query response.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_skill_store_feedback.py -q
```

---

## Epic AA-SKILLSTORE-12: Documentation And Operator Commands

### AA-SKILLSTORE-12.1 Add Skill Store Operator Docs

**Status:** READY  
**Priority:** P1  
**Suggested owner:** Docs assistant  
**Dependencies:** AA-SKILLSTORE-9.3  
**Files:**
- Create: `docs/agent_adda_skill_store.md`

**Work:**
- [ ] Document:
  - what the skill store is
  - runtime status lifecycle
  - how to generate scenarios
  - how to validate
  - how to promote/deprecate
  - how to inspect retrieval logs
  - safety guardrails
- [ ] Add examples:
  - 3M market analysis
  - VCP breakouts with fundamentals
  - portfolio add/trim

**Acceptance Criteria:**
- A new coding assistant can run validation and promotion commands from the doc.
- Docs explicitly state that generated skills are untrusted.

**Verification:**

```bash
rg -n "generated.*untrusted|validate|promote|deprecate|pgvector" docs/agent_adda_skill_store.md
```

### AA-SKILLSTORE-12.2 Add `/skills` Runtime Inspection Command

**Status:** READY  
**Priority:** P2  
**Suggested owner:** Command assistant  
**Dependencies:** AA-SKILLSTORE-9.3  
**Files:**
- Modify: `nse_agent.py`
- Modify: `terminal/help.py`
- Create: `terminal/skills/commands_store.py`
- Test: `tests/test_skill_store_commands.py`

**Work:**
- [ ] Add commands:
  - `/skills`
  - `/skills search <query>`
  - `/skills show <skill_id>`
  - `/skills recent`
- [ ] Render status counts and top matching skills.
- [ ] Keep command read-only.

**Acceptance Criteria:**
- `/skills` lists status counts.
- `/skills search VCP fundamentals` shows matching validated cards.
- `/skills show market_3m_rotation_swing_v1` shows contract and validation date.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_skill_store_commands.py -q
```

---

## Epic AA-SKILLSTORE-13: Release Gates

### AA-SKILLSTORE-13.1 Runtime Enablement Gate

**Status:** BLOCKED  
**Priority:** P0  
**Suggested owner:** Release assistant  
**Dependencies:** AA-SKILLSTORE-8.3, AA-SKILLSTORE-10.2, AA-SKILLSTORE-11.1  
**Files:**
- Modify: `terminal/skills/config.py`
- Modify: release notes or docs

**Work:**
- [ ] Confirm benchmark pass rate.
- [ ] Confirm deterministic routing smoke tests pass with skill store disabled and enabled.
- [ ] Confirm unsafe SQL tests pass.
- [ ] Confirm retrieval logs are written.
- [ ] Enable feature flag for local default only after user approval.

**Acceptance Criteria:**
- No deterministic command regressions.
- No runtime access to `generated` or `test_failed` cards.
- At least one end-to-end skill run produces validated evidence and source trail.

**Verification:**

```bash
AGENT_ADDA_SKILL_STORE=0 .venv/bin/python -m pytest tests/test_routing_smoke.py -q
AGENT_ADDA_SKILL_STORE=1 .venv/bin/python -m pytest tests/test_skill_store_e2e.py tests/test_skill_store_benchmarks.py -q
```

### AA-SKILLSTORE-13.2 Post-Release Audit

**Status:** BLOCKED  
**Priority:** P1  
**Suggested owner:** Release assistant  
**Dependencies:** AA-SKILLSTORE-13.1  
**Files:**
- Create: `reports/skill_store/skill_store_audit_<date>.md`

**Work:**
- [ ] Query retrieval logs for first 50 runtime uses.
- [ ] Count:
  - selected skill ids
  - abstentions
  - reviewer rejections
  - execution failures
  - user feedback
- [ ] Identify cards to promote, repair, or deprecate.

**Acceptance Criteria:**
- Audit recommends concrete skill-card maintenance actions.
- Any repeated failure has a linked backlog task.

**Verification:**

```bash
test -f reports/skill_store/skill_store_audit_*.md
```

---

## Suggested Implementation Order

1. AA-SKILLSTORE-0.1
2. AA-SKILLSTORE-1.1
3. AA-SKILLSTORE-2.1
4. AA-SKILLSTORE-3.1
5. AA-SKILLSTORE-1.2
6. AA-SKILLSTORE-3.2
7. AA-SKILLSTORE-4.1
8. AA-SKILLSTORE-4.2
9. AA-SKILLSTORE-4.3
10. AA-SKILLSTORE-5.1
11. AA-SKILLSTORE-5.2
12. AA-SKILLSTORE-6.1
13. AA-SKILLSTORE-6.2
14. AA-SKILLSTORE-6.3
15. AA-SKILLSTORE-7.1
16. AA-SKILLSTORE-8.1
17. AA-SKILLSTORE-8.2
18. AA-SKILLSTORE-10.1
19. AA-SKILLSTORE-10.2
20. AA-SKILLSTORE-13.1

The generation pipeline should start after the first seed skill is stable, not before. Synthetic skill volume is useful only after the validation machinery is already strict.
