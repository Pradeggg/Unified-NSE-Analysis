# Agent Adda Research Council Implementation Backlog

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this backlog task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Agent Adda's Research Council: a state-machine driven, evidence-first, multi-agent research workflow that can route objectives, freeze a market evidence pack, run specialist agents, compile and execute plans against existing tools, critique results, synthesize a research-only conclusion, and render durable reports.

**Architecture:** Implement the Research Council as a new `terminal/research_council/` package with explicit schemas, mode profiles, state handlers, deterministic agents first, plan compiler/executor, PostgreSQL persistence, and markdown/HTML reports. The system must orchestrate existing data/report/backtesting modules instead of duplicating them. LLM personas are Phase 2 overlays after deterministic behavior is stable.

**Tech Stack:** Python dataclasses/TypedDicts, pytest, psycopg/PostgreSQL JSONB, Jinja2, existing Agent Adda terminal router/tools, existing `recommendation_reports` schema, existing `backtesting.strategy_council`, existing EOD/F&O/fundamental refresh outputs.

---

## Coordination Rules For Parallel AI Assistants

- Claim one backlog row at a time.
- Do not edit another row's files unless explicitly coordinating.
- Start each implementation task by reading:
  - `docs/superpowers/specs/2026-05-26-agent-adda-research-council-design.md`
  - `docs/RESEARCH_COUNCIL_IMPLEMENTATION_ARTIFACT.md`
  - this backlog file
- Keep the first implementation deterministic. Do not add LLM calls until the deterministic path and schema tests pass.
- Treat every final label as research-only. Never introduce order execution, broker integration, or investment advice language.
- Use PostgreSQL and existing cached data as source truth; do not make report prose a source of facts.
- Keep migrations additive and idempotent.
- If a tool name from the artifact does not exist, create a small adapter or mark the backlog row blocked. Do not invent imports that fail at runtime.
- Run targeted tests before handing off a row.

## Canonical References

- Design spec: `docs/superpowers/specs/2026-05-26-agent-adda-research-council-design.md`
- Implementation artifact: `docs/RESEARCH_COUNCIL_IMPLEMENTATION_ARTIFACT.md`
- Existing Strategy Council: `docs/STRATEGY_COUNCIL_DESIGN.md`
- Recommendation report design: `docs/superpowers/specs/2026-05-22-grounded-recommendation-report-design.md`
- Harness inheritance design: `docs/superpowers/specs/2026-05-25-agent-adda-claude-harness-inheritance-design.md`
- Current schema: `postgres/schema.sql`
- Current recommendation reports migration: `postgres/migrations/20260522_recommendation_reports.sql`

## Status Legend

| Status | Meaning |
|---|---|
| READY | Can be picked up now |
| BLOCKED | Needs a dependency or decision first |
| PARTIAL | Some code exists but integration/tests are incomplete |
| DONE | Implemented, tested, and wired |
| DEFERRED | Explicitly out of first build |

## Parallel Work Lanes

| Lane | Owns | Can run in parallel with |
|---|---|---|
| Schema/Persistence | migrations, `schemas.py`, `persistence.py` | Agents, Reports after schemas stabilize |
| Evidence/Data | `data_steward.py`, `evidence_pack_builder.py` | Agents once fixtures exist |
| Agents/Critics | deterministic personas and critics | Plan executor after schemas exist |
| Plan Engine | state machine, plan compiler, executor | Reports using fixtures |
| Reporting/UX | markdown/html renderers, `/council` commands | Persistence after run fixture exists |
| Strategy/Coder | coder sandbox, Strategy Build mode | Only after deterministic council loop |

---

## Epic RC-0: Pre-Implementation Corrections

### RC-0.1 Align Document References

**Status:** DONE  
**Priority:** P0  
**Suggested owner:** Docs/coordination assistant  
**Files:**
- Modify: `docs/RESEARCH_COUNCIL_IMPLEMENTATION_ARTIFACT.md`
- Modify: `docs/superpowers/specs/2026-05-26-agent-adda-research-council-design.md`

**Work:**
- [x] Replace references to missing `docs/RESEARCH_COUNCIL_DESIGN.md` with `docs/superpowers/specs/2026-05-26-agent-adda-research-council-design.md`.
- [x] Either remove or explicitly mark `docs/UNIFIED_NSE_DATA_MODEL.md` as future/canonical-missing.
- [x] Add a note that `docs/RESEARCH_COUNCIL_IMPLEMENTATION_ARTIFACT.md` is the implementation blueprint and this file is the execution backlog.

**Acceptance Criteria:**
- `rg 'RESEARCH_COUNCIL_DESIGN|UNIFIED_NSE_DATA_MODEL|RESEARCH_COUNCIL_STATE_MACHINE_DESIGN' docs/RESEARCH_COUNCIL_IMPLEMENTATION_ARTIFACT.md` returns only intentional historical notes or no hits.
- Other assistants can find the design and backlog without guessing filenames.

### RC-0.2 Harden Migration Requirements Before Build

**Status:** DONE  
**Priority:** P0  
**Suggested owner:** PostgreSQL assistant  
**Files:**
- Create: `postgres/migrations/20260526_research_council.sql`
- Modify: `postgres/schema.sql`
- Test: `tests/research_council/test_migrations.py`

**Work:**
- [x] Convert the implementation artifact's migration SQL into one idempotent migration.
- [x] Use `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` for existing tables.
- [x] Use `CREATE TABLE IF NOT EXISTS` for new tables.
- [x] Use `CREATE INDEX IF NOT EXISTS` for all indexes.
- [x] Add missing `disclaimer_version` fields required by the artifact:
  - `recommendation_reports.recommendations.disclaimer_version TEXT DEFAULT 'v1.0_research_only'`
  - `signals.signal_log.council_run_id TEXT`
  - `signals.signal_log.disclaimer_version TEXT`
- [x] Add council fields to `recommendation_reports.runs`:
  - `council_mode TEXT`
  - `horizon TEXT`
  - `risk_budget TEXT`
  - `universe_filter TEXT`
  - `evidence_pack_id TEXT`
  - `plan_iterations INTEGER DEFAULT 0`
  - `revision_count INTEGER DEFAULT 0`
  - `final_label TEXT`
  - `council_status TEXT`
  - `budgets_remaining JSONB`
  - `wall_clock_ms INTEGER`
- [x] Add new tables:
  - `recommendation_reports.evidence_packs`
  - `recommendation_reports.agent_findings`
  - `recommendation_reports.branch_summaries`
  - `recommendation_reports.council_plans`
  - `recommendation_reports.execution_results`
  - `recommendation_reports.strategy_specs`
  - `recommendation_reports.backtest_results`
  - `recommendation_reports.critic_reviews`

**Acceptance Criteria:**
- Migration can be run twice without error.
- Existing `recommendation_reports.runs`, `evidence`, and `recommendations` behavior remains compatible.
- `pytest -q tests/research_council/test_migrations.py` passes.

### RC-0.3 Validate Existing Tool Names Before Registry Work

**Status:** DONE  
**Priority:** P0  
**Suggested owner:** Tooling assistant  
**Files:**
- Create: `docs/research_council_tool_mapping_audit.md`
- No production code yet

**Work:**
- [x] Audit every logical tool in `docs/RESEARCH_COUNCIL_IMPLEMENTATION_ARTIFACT.md` §7.2 and §14.
- [x] For each logical tool, record one of:
  - exact existing callable path
  - adapter required
  - missing and deferred
- [x] Pay special attention to speculative names such as:
  - `postgres.loader.run_stage2_screen`
  - `regime_detector.detect_current_regime`
  - `market_breadth.summarize_breadth`
  - `backtesting.engine.run_strategy`
  - `fetch_fno_data.option_chain_sr`
  - `fetch_fno_data.iv_percentile`
- [x] Identify existing equivalents in `terminal/tools.py`, `terminal/recommendation_report.py`, `sector_rotation_report.py`, `fetch_fno_data.py`, and `backtesting/strategy_council/`.

**Acceptance Criteria:**
- Audit file contains a table with columns: `logical_tool`, `artifact_target`, `actual_callable`, `adapter_needed`, `status`, `notes`.
- No implementation row assumes a callable that has not been audited.

---

## Epic RC-1: Foundations

### RC-1.1 Create Package Layout

**Status:** DONE  
**Priority:** P0  
**Suggested owner:** Foundation assistant  
**Dependencies:** RC-0.1  
**Files:**
- Create: `terminal/research_council/__init__.py`
- Create: `terminal/research_council/engine.py`
- Create: `terminal/research_council/schemas.py`
- Create: `terminal/research_council/mode_profiles.py`
- Create: `terminal/research_council/tool_registry.py`
- Create: `terminal/research_council/plan_compiler.py`
- Create: `terminal/research_council/plan_executor.py`
- Create: `terminal/research_council/decision_math.py`
- Create: `terminal/research_council/evidence_pack_builder.py`
- Create: `terminal/research_council/persistence.py`
- Create: `terminal/research_council/llm_client.py`
- Create: `terminal/research_council/states/__init__.py`
- Create: `terminal/research_council/agents/__init__.py`
- Create: `terminal/research_council/critics/__init__.py`
- Create: `terminal/research_council/reports/__init__.py`
- Test: `tests/research_council/test_package_imports.py`

**Work:**
- [x] Create the package tree from implementation artifact §11.
- [x] Add empty or minimal modules that import cleanly.
- [x] Add `tests/research_council/fixtures/` directory.
- [x] Add import smoke tests for all modules.

**Acceptance Criteria:**
- `pytest -q tests/research_council/test_package_imports.py` passes.
- Importing `terminal.research_council` has no OpenAI/API-key side effects.

### RC-1.2 Define Core Schemas

**Status:** DONE  
**Priority:** P0  
**Suggested owner:** Schema assistant  
**Dependencies:** RC-1.1  
**Files:**
- Modify: `terminal/research_council/schemas.py`
- Test: `tests/research_council/test_schemas.py`

**Work:**
- [x] Implement these enums/literals:
  - `Stage`
  - `CouncilMode`
  - `FinalLabel`
  - `PlanStepStatus`
  - `CriticSeverity`
- [x] Implement dataclasses:
  - `CouncilState`
  - `ModeProfile`
  - `StewardVerdict`
  - `EvidencePack`
  - `SourceTrailEntry`
  - `MissingEvidence`
  - `AgentFinding`
  - `BranchSummary`
  - `ToolCall`
  - `SuccessCriterion`
  - `PlanStep`
  - `Plan`
  - `ExecutionResult`
  - `PlanReview`
  - `CriticFinding`
  - `CriticReview`
  - `RevisionResult`
  - `Decision`
  - `StrategyBuildRequest`
  - `StrategyBuildResult`
- [x] Prefer structured `SuccessCriterion` objects over string-evaluated criteria:
  - `metric`
  - `operator`
  - `value`
  - `source`
  - `required`
- [x] Add `to_dict` / `from_dict` helpers where needed for JSONB persistence.
- [x] Add schema fixture roundtrip tests.

**Acceptance Criteria:**
- `pytest -q tests/research_council/test_schemas.py` passes.
- All dataclasses serialize to JSON-compatible dicts.
- No schema requires pandas/PostgreSQL/OpenAI imports.

### RC-1.3 Mode Profiles

**Status:** DONE  
**Priority:** P0  
**Suggested owner:** Foundation assistant  
**Dependencies:** RC-1.2  
**Files:**
- Modify: `terminal/research_council/mode_profiles.py`
- Test: `tests/research_council/test_mode_profiles.py`

**Work:**
- [x] Implement profiles:
  - `market_council`
  - `stock_deep_dive`
  - `strategy_build`
  - `intraday_tactical`
  - `report_review`
- [x] Encode loop caps from artifact §4.3:
  - market plan cap 3, revision cap 2, wall clock 8 min, token budget 200K
  - stock plan cap 3, revision cap 2, wall clock 8 min, token budget 150K
  - strategy plan cap 5, revision cap 3, wall clock 12 min, token budget 350K
  - intraday plan cap 1, revision cap 0, wall clock 90s, token budget 50K
  - report review plan cap 0, revision cap 0, wall clock 3 min, token budget 30K
- [x] Encode agent/critic sets per mode.
- [x] Encode data freshness gates per mode.
- [x] Add `load_mode_profile(mode: CouncilMode)`.

**Acceptance Criteria:**
- `pytest -q tests/research_council/test_mode_profiles.py` passes.
- Each mode declares whether coder is enabled, which critics run, and whether HTML is full/minimal.

### RC-1.4 State Machine Driver

**Status:** DONE  
**Priority:** P0  
**Suggested owner:** Engine assistant  
**Dependencies:** RC-1.2, RC-1.3  
**Files:**
- Modify: `terminal/research_council/engine.py`
- Create: `terminal/research_council/states/intake.py`
- Create: `terminal/research_council/states/route.py`
- Create: `terminal/research_council/states/data_steward.py`
- Create: `terminal/research_council/states/market_state.py`
- Create: `terminal/research_council/states/specialist_pass.py`
- Create: `terminal/research_council/states/branch_deliberation.py`
- Create: `terminal/research_council/states/plan_build.py`
- Create: `terminal/research_council/states/plan_execute.py`
- Create: `terminal/research_council/states/plan_review.py`
- Create: `terminal/research_council/states/critic_review.py`
- Create: `terminal/research_council/states/revision.py`
- Create: `terminal/research_council/states/synthesis.py`
- Create: `terminal/research_council/states/render_html.py`
- Create: `terminal/research_council/states/persistence.py`
- Test: `tests/research_council/test_engine_state_machine.py`

**Work:**
- [x] Implement `run_council(objective: str, **flags) -> CouncilState`.
- [x] Initialize `run_id` as `research_<YYYYMMDD>_<NNN-like suffix>`.
- [x] Add terminal states:
  - `persistence`
  - `abort_stale_data`
  - `abort_budget`
  - `escalate_human`
  - `commit_no_trade`
- [x] Implement no-op handlers that advance through all states.
- [x] Add budget checks but keep enforcement simple in first slice.
- [x] Append a minimal event entry per state transition.

**Acceptance Criteria:**
- `python -m terminal.research_council.engine --dry-run --objective "today swing"` walks the state machine and prints transitions.
- `pytest -q tests/research_council/test_engine_state_machine.py` passes.

---

## Epic RC-2: Data Steward And Evidence Pack

### RC-2.1 Data Steward Gate

**Status:** DONE (2026-05-31)  
**Priority:** P0  
**Suggested owner:** Data assistant  
**Dependencies:** RC-1.2, RC-1.3, RC-0.2  
**Files:**
- Modify: `terminal/research_council/states/data_steward.py`
- Test: `tests/research_council/test_data_steward.py`

**Work:**
- [x] Implement checks:
  - latest `market.equity_eod`
  - latest `scores.stage_snapshots`
  - latest `derivatives.fno_eod` when mode requires F&O
  - latest `scores.financials_refresh_log` or available fundamentals snapshot when fundamentals required
  - latest intraday snapshot when intraday mode
  - universe count and liquid universe count
- [x] Use current known liquid universe filters:
  - latest valid symbols
  - `close > 100`
  - `volume > 100000`
  - at least 50 bars when required by analysis
- [x] Return `usable`, `degraded`, or `blocked`.
- [x] Include remediation text for blocked states.

**Acceptance Criteria:**
- Current refreshed DB returns a real verdict through `run_check(mode="market_council")`; `/council steward` terminal wiring remains in RC-7.2.
- Tests cover usable, degraded, and blocked cases using fake query results.
- Missing F&O/options evidence is flagged but does not crash non-F&O routes.

### RC-2.2 Evidence Pack Builder

**Status:** DONE  
**Priority:** P0  
**Suggested owner:** Evidence assistant  
**Dependencies:** RC-2.1  
**Files:**
- Modify: `terminal/research_council/evidence_pack_builder.py`
- Modify: `terminal/research_council/states/market_state.py`
- Test: `tests/research_council/test_evidence_pack_builder.py`
- Fixture: `tests/research_council/fixtures/evidence_pack_small.json`

**Work:**
- [x] Build `EvidencePack` with sections:
  - `market`
  - `sectors`
  - `stocks`
  - `derivatives`
  - `fundamentals`
  - `events`
  - `reports`
  - `source_trail`
  - `missing_evidence`
- [x] Query PostgreSQL first.
- [x] Use CSV/report fallbacks only when existing project behavior already uses them.
- [x] Include row counts, latest dates, table/file names, and fallback flags.
- [x] Freeze the evidence pack per run. Do not refresh live data mid-run.
- [x] Limit full stock payload size for initial agent passes; preserve full detail in persisted pack or referenced JSON.

**Acceptance Criteria:**
- `pytest -q tests/research_council/test_evidence_pack_builder.py` passes.
- Evidence pack can be serialized to JSON and reloaded.
- Source trail names every table/file used.

### RC-2.3 Evidence Pack Persistence

**Status:** DONE (2026-05-31)  
**Priority:** P0  
**Suggested owner:** Persistence assistant  
**Dependencies:** RC-0.2, RC-2.2  
**Files:**
- Modify: `terminal/research_council/persistence.py`
- Test: `tests/research_council/test_persistence.py`

**Work:**
- [x] Add `save_evidence_pack(pack)`.
- [x] Add `load_evidence_pack(pack_id)`.
- [x] Store in `recommendation_reports.evidence_packs`.
- [x] Include `pack_body`, `source_trail`, and `missing_evidence` JSONB.
- [x] Keep failures explicit for council runs; do not silently continue if persistence is required.

**Acceptance Criteria:**
- Evidence pack persistence roundtrip passes using a fake DB-API connection; transaction rollback fixture remains for later PG integration tests.
- `/council today --evidence-only` terminal command remains in RC-7.2.

---

## Epic RC-3: Deterministic Specialist Agents

### RC-3.1 Agent Base And Output Validation

**Status:** DONE  
**Priority:** P0  
**Suggested owner:** Agents assistant  
**Dependencies:** RC-1.2, RC-2.2  
**Files:**
- Create: `terminal/research_council/agents/base.py`
- Create: `terminal/research_council/agents/prompts.py`
- Test: `tests/research_council/test_agent_base.py`

**Work:**
- [x] Define base `Agent` class with:
  - `name`
  - `run_deterministic`
  - optional `run_llm`
  - `validate_output`
  - `format_evidence_for_llm`
- [x] Keep LLM disabled by default.
- [x] Store persona prompts as named constants, but do not call them yet.
- [x] Add schema validation for `AgentFinding`.

**Acceptance Criteria:**
- Deterministic test agent returns a valid `AgentFinding`.
- Missing required fields fail validation.
- Importing prompts has no provider side effects.

### RC-3.2 Sector Rotation Agent

**Status:** DONE  
**Priority:** P0  
**Suggested owner:** Sector assistant  
**Dependencies:** RC-3.1  
**Files:**
- Create: `terminal/research_council/agents/sector_rotation.py`
- Test: `tests/research_council/test_specialists/test_sector_rotation.py`

**Work:**
- [x] Classify leader, improver, laggard, and deteriorating sectors from evidence.
- [x] Use 1M/3M RS, Stage 2 count, breadth, and macro tailwinds where available.
- [x] Produce candidate clusters from `scores.sector_top_stocks` or evidence pack stock rankings.
- [x] Include dissent/risk for momentum-peak and breadth-breakdown conditions.

**Acceptance Criteria:**
- Fixture with one clear leader and one deteriorating sector produces expected classification.
- Agent does not recommend candidates from deteriorating sectors.

### RC-3.3 Technical Agent

**Status:** DONE  
**Priority:** P0  
**Suggested owner:** Technical assistant  
**Dependencies:** RC-3.1  
**Files:**
- Create: `terminal/research_council/agents/technical.py`
- Test: `tests/research_council/test_specialists/test_technical.py`

**Work:**
- [x] Classify setups using stage, RS, SMA alignment, RSI, MACD, ADX, Supertrend, 52W proximity, and volume ratio.
- [x] Bucket candidates:
  - `ACTIONABLE`
  - `EXTENDED`
  - `DAMAGED`
  - `CHOP`
  - `INSUFFICIENT_DATA`
- [x] Compute research entry zones and invalidation notes only when evidence exists.

**Acceptance Criteria:**
- Stage 2 + RS leader + volume confirmation is actionable.
- Extended RSI or missing volume confirmation is downgraded.
- Missing evidence is reported, not inferred.

### RC-3.4 Fundamental Agent

**Status:** DONE  
**Priority:** P0  
**Suggested owner:** Fundamentals assistant  
**Dependencies:** RC-3.1  
**Files:**
- Create: `terminal/research_council/agents/fundamental.py`
- Test: `tests/research_council/test_specialists/test_fundamental.py`

**Work:**
- [x] Classify fundamentals as:
  - `quality_supportive`
  - `quality_mixed`
  - `quality_weak`
  - `quality_unknown`
- [x] Use sales/profit growth, margins, ROE/ROCE, debt, promoter pledge, valuation, quarterly trend, and screener pros/cons where available.
- [x] Downgrade unsupported claims to `quality_unknown`.

**Acceptance Criteria:**
- Weak debt/pledge fixture produces `quality_weak` or `quality_mixed`.
- Missing fundamental evidence never creates a false quality claim.

### RC-3.5 Specialist Fan-Out State

**Status:** DONE  
**Priority:** P0  
**Suggested owner:** Engine/agents assistant  
**Dependencies:** RC-3.2, RC-3.3, RC-3.4, RC-2.3  
**Files:**
- Modify: `terminal/research_council/states/specialist_pass.py`
- Modify: `terminal/research_council/persistence.py`
- Test: `tests/research_council/test_specialist_pass.py`

**Work:**
- [x] Run the first three deterministic agents in parallel.
- [x] Persist to `recommendation_reports.agent_findings`.
- [x] Store outputs in `CouncilState.specialist_findings`.
- [x] Capture agent failures as absent/degraded findings, not hard crashes, unless quorum fails.

**Acceptance Criteria:**
- `/council today --horizon swing` produces three persisted findings.
- Parallel execution test proves all three agents run and validate.

---

## Epic RC-4: Branches, Plan Compiler, And Executor

### RC-4.1 Branch Deliberation

**Status:** DONE  
**Priority:** P0  
**Suggested owner:** Deliberation assistant  
**Dependencies:** RC-3.5  
**Files:**
- Modify: `terminal/research_council/states/branch_deliberation.py`
- Modify: `terminal/research_council/persistence.py`
- Test: `tests/research_council/test_branch_deliberation.py`

**Work:**
- [x] Compose six canonical public TOT branch summaries:
  - `momentum_leadership`
  - `minervini_stage2`
  - `sector_rotation`
  - `earnings_catalyst`
  - `fno_positioning`
  - `defensive_no_trade`
- [x] Include supporting agents, dissenting agents, candidates, risks, and required next step.
- [x] Persist to `recommendation_reports.branch_summaries`.

**Acceptance Criteria:**
- Branch summaries are deterministic from fixture findings.
- No private chain-of-thought is persisted.

### RC-4.2 Tool Registry Adapter Layer

**Status:** DONE  
**Priority:** P0  
**Suggested owner:** Tooling assistant  
**Dependencies:** RC-0.3, RC-1.1  
**Files:**
- Modify: `terminal/research_council/tool_registry.py`
- Create: `terminal/research_council/tool_adapters.py`
- Test: `tests/research_council/test_tool_registry.py`

**Work:**
- [x] Implement `ToolRegistry` class rather than a naked dict.
- [x] Add logical tools from artifact §7.2 only where actual callables/adapters exist.
- [x] Return structured missing-tool errors for unmapped tools.
- [x] Add adapters for high-value first-slice tools:
  - regime summary
  - breadth summary
  - sector ranking
  - stage2 screen
  - high RS screen
  - FII/DII flow summary
  - F&O buildup summary
  - latest results summary
- [x] Keep the registry lazy-imported.

**Acceptance Criteria:**
- Registry import succeeds without importing heavy dependencies.
- Every registered tool resolves to a callable.
- Missing tool returns a controlled error.

### RC-4.3 Plan Compiler

**Status:** DONE  
**Priority:** P0  
**Suggested owner:** Plan assistant  
**Dependencies:** RC-4.2  
**Files:**
- Modify: `terminal/research_council/plan_compiler.py`
- Test: `tests/research_council/test_plan_compiler.py`

**Work:**
- [x] Validate every `PlanStep.tool_calls` entry against `ToolRegistry`.
- [x] Convert missing tools to `failed_terminal` plan step metadata.
- [x] Validate dependencies form a DAG.
- [x] Validate structured success criteria.

**Acceptance Criteria:**
- Cyclic plan fails validation.
- Unknown tool is captured as terminal failure, not an import error.
- Structured success criteria compile without `eval`.

### RC-4.4 Plan Executor

**Status:** DONE  
**Priority:** P0  
**Suggested owner:** Executor assistant  
**Dependencies:** RC-4.3  
**Files:**
- Modify: `terminal/research_council/plan_executor.py`
- Modify: `terminal/research_council/states/plan_execute.py`
- Modify: `terminal/research_council/persistence.py`
- Test: `tests/research_council/test_plan_executor.py`

**Work:**
- [x] Implement topological execution by dependency level.
- [x] Run independent steps in parallel with a small `max_parallel` default.
- [x] Retry retryable failures once.
- [x] Persist `ExecutionResult` rows.
- [x] Evaluate structured success criteria.
- [x] Keep raw tool output compact or referenced when large.

**Acceptance Criteria:**
- Parallel independent steps run.
- Dependent steps wait for dependencies.
- Retryable failure test passes.
- Execution result persistence roundtrip passes.

### RC-4.5 Deterministic Chair Plan Build And Review

**Status:** DONE  
**Priority:** P0  
**Suggested owner:** Chair/planning assistant  
**Dependencies:** RC-4.1, RC-4.4  
**Files:**
- Create: `terminal/research_council/agents/hedge_fund_owner.py`
- Modify: `terminal/research_council/states/plan_build.py`
- Modify: `terminal/research_council/states/plan_review.py`
- Test: `tests/research_council/test_plan_loop.py`

**Work:**
- [x] Implement deterministic plan builder for Market Council.
- [x] Typical first plan should ask:
  - Is regime supportive?
  - Which sectors lead?
  - Which stocks are Stage 2/RS leaders?
  - Which candidates fail liquidity/risk?
  - Which candidates need F&O/fundamental confirmation?
- [x] Implement plan review with:
  - `advance`
  - `new_questions`
  - `new_plan_steps`
  - degraded-mode handling
- [x] Enforce plan loop caps.

**Acceptance Criteria:**
- `/council today` produces a plan and execution results on fixture data.
- Plan loop converges under cap.

---

## Epic RC-5: Synthesis, Decision Math, Markdown Report

### RC-5.1 Decision Math

**Status:** DONE  
**Priority:** P1  
**Suggested owner:** Quant assistant  
**Dependencies:** RC-1.2  
**Files:**
- Modify: `terminal/research_council/decision_math.py`
- Test: `tests/research_council/test_decision_math.py`

**Work:**
- [x] Add ATR-based stop helper.
- [x] Add target helper using recent swing/ATR multiples.
- [x] Add hypothetical research-book sizing helper with hard disclaimer.
- [x] Never output live order instructions.

**Acceptance Criteria:**
- Deterministic tests for stop/target calculations pass.
- Missing ATR/price data returns unavailable, not guessed values.

### RC-5.2 Deterministic Synthesis

**Status:** DONE  
**Priority:** P1  
**Suggested owner:** Synthesis assistant  
**Dependencies:** RC-4.5, RC-5.1  
**Files:**
- Modify: `terminal/research_council/agents/hedge_fund_owner.py`
- Modify: `terminal/research_council/states/synthesis.py`
- Test: `tests/research_council/test_synthesis.py`

**Work:**
- [x] Implement final label policy:
  - `WATCHLIST`
  - `RESEARCH_LONG`
  - `WAIT_FOR_CONFIRMATION`
  - `AVOID_FRESH_ENTRY`
  - `REVIEW_MANUALLY`
  - `NO_TRADE`
  - `HEDGE_REQUIRED`
- [x] Enforce no `RESEARCH_LONG` when critic blocks exist.
- [x] Downgrade if plan loop cap was hit.
- [x] Preserve dissent log.
- [x] Include confidence and source-trail references.

**Acceptance Criteria:**
- Label selection edge-case tests pass.
- Final decision cannot include unsupported F&O/fundamental/catalyst claims.

### RC-5.3 Markdown Renderer

**Status:** DONE  
**Priority:** P1  
**Suggested owner:** Reporting assistant  
**Dependencies:** RC-5.2  
**Files:**
- Create: `terminal/research_council/reports/markdown_renderer.py`
- Create: `terminal/research_council/reports/templates/council_report.md.j2`
- Modify: `terminal/research_council/states/render_html.py` or split into `render_report.py`
- Test: `tests/research_council/test_markdown_render.py`

**Work:**
- [x] Render markdown first before HTML.
- [x] Include sections:
  - objective and mode
  - data freshness
  - market state
  - sector view
  - candidate table
  - agent findings
  - public POT/TOT summaries
  - plan steps
  - execution results
  - critic review
  - final research plan
  - invalidation and next actions
  - missing evidence
  - research-only disclaimer
- [x] Write to `reports/research_council/<run_id>.md`.

**Acceptance Criteria:**
- Fixture council run renders all required sections.
- Report contains disclaimer in header and footer.

### RC-5.4 End-To-End Market Council MVP

**Status:** DONE  
**Priority:** P1  
**Suggested owner:** Integration assistant  
**Dependencies:** RC-2.3, RC-3.5, RC-4.5, RC-5.3  
**Files:**
- Modify: `terminal/research_council/engine.py`
- Test: `tests/research_council/test_engine_e2e.py`

**Work:**
- [x] Wire intake through persistence for Market Council.
- [x] Use deterministic agents only.
- [x] Persist run metadata in `recommendation_reports.runs`.
- [x] Persist evidence, findings, branches, plan, execution results, and decision.
- [x] Produce markdown report.

**Acceptance Criteria:**
- End-to-end fixture test passes.
- Real-data smoke command completes:
  - `python -m terminal.research_council.engine --objective "/council today --horizon swing --risk moderate" --format md`

---

## Epic RC-6: Remaining Specialists And Critics

### RC-6.1 Macro / Regime Agent

**Status:** DONE  
**Priority:** P1  
**Suggested owner:** Macro assistant  
**Dependencies:** RC-3.1  
**Files:**
- Create: `terminal/research_council/agents/macro_regime.py`
- Test: `tests/research_council/test_specialists/test_macro_regime.py`

**Work:**
- [x] Classify regime from existing regime/breadth/flow evidence.
- [x] Output risk-on/risk-off/risk-mixed.
- [x] Identify sector macro tailwinds/headwinds.

**Acceptance Criteria:**
- Breadth deterioration downgrades risk stance.
- One-day FII/DII flow spike does not override 5-day context.

### RC-6.2 Minervini Agent

**Status:** DONE  
**Priority:** P1  
**Suggested owner:** Minervini assistant  
**Dependencies:** RC-3.1  
**Files:**
- Create: `terminal/research_council/agents/minervini.py`
- Test: `tests/research_council/test_specialists/test_minervini.py`

**Work:**
- [x] Enforce strict Stage 2, RS, MA, 52W proximity, volume, and tightness checks.
- [x] Reject extended or late-stage candidates.
- [x] Mark VCP/tightness as required next step when not available.

**Acceptance Criteria:**
- Many candidates are rejected by design.
- Fixture extended breakout is downgraded.

### RC-6.3 F&O / Risk Agent

**Status:** DONE  
**Priority:** P1  
**Suggested owner:** Derivatives assistant  
**Dependencies:** RC-3.1, RC-2.2  
**Files:**
- Create: `terminal/research_council/agents/fno_risk.py`
- Test: `tests/research_council/test_specialists/test_fno_risk.py`

**Work:**
- [x] Read futures buildup, PCR, OI, IV, and option-chain evidence when present.
- [x] Do not emit options claims when options evidence is missing.
- [x] Flag crowded positioning and hedge-needed conditions.

**Acceptance Criteria:**
- Missing option-chain fixture returns missing evidence rather than a strategy.
- F&O setup is clearly separated from cash-equity setup.

### RC-6.4 Catalyst Agent

**Status:** DONE  
**Priority:** P1  
**Suggested owner:** Catalyst assistant  
**Dependencies:** RC-3.1, RC-2.2  
**Files:**
- Create: `terminal/research_council/agents/catalyst.py`
- Test: `tests/research_council/test_specialists/test_catalyst.py`

**Work:**
- [x] Read results, corporate events, filings, concall summaries, and broker/news evidence where available.
- [x] Classify catalysts as verified, stale, absent, or unstructured.
- [x] Label high-impact events in the next 5 trading days.

**Acceptance Criteria:**
- Event-risk fixture causes `WAIT_FOR_CONFIRMATION` recommendation pressure.
- No catalyst claims appear without source trail entries.

### RC-6.5 Critic Base And Deterministic Critics

**Status:** DONE  
**Priority:** P1  
**Suggested owner:** Critics assistant  
**Dependencies:** RC-5.4  
**Files:**
- Create: `terminal/research_council/critics/base.py`
- Create: `terminal/research_council/critics/data_quality.py`
- Create: `terminal/research_council/critics/leakage.py`
- Create: `terminal/research_council/critics/overfit.py`
- Create: `terminal/research_council/critics/risk.py`
- Create: `terminal/research_council/critics/evidence.py`
- Modify: `terminal/research_council/states/critic_review.py`
- Test: `tests/research_council/test_critics/test_data_quality.py`
- Test: `tests/research_council/test_critics/test_leakage.py`
- Test: `tests/research_council/test_critics/test_overfit.py`
- Test: `tests/research_council/test_critics/test_risk.py`
- Test: `tests/research_council/test_critics/test_evidence.py`

**Work:**
- [x] Implement shared `CriticReview` validation.
- [x] Data Quality Critic blocks stale or source-missing claims.
- [x] Leakage Critic blocks test-split contamination and latest-fundamentals historical use.
- [x] Overfit Critic blocks low trade count, excessive parameters, poor validation, regime concentration.
- [x] Risk Critic blocks or warns on liquidity, drawdown, concentration, event risk.
- [x] Evidence Critic blocks unsupported F&O/fundamental/catalyst claims.
- [x] Run critics in parallel.
- [x] Persist to `recommendation_reports.critic_reviews`.

**Acceptance Criteria:**
- Each critic has fixture tests for info/warn/block.
- Synthesis refuses `RESEARCH_LONG` when any block remains unresolved.

### RC-6.6 Revision And Convergence

**Status:** DONE  
**Priority:** P1  
**Suggested owner:** Engine/critics assistant  
**Dependencies:** RC-6.5  
**Files:**
- Modify: `terminal/research_council/states/revision.py`
- Test: `tests/research_council/test_convergence.py`

**Work:**
- [x] Implement convergence rules:
  - every block resolved by new evidence, withdrawn claim, or branch demotion
  - max confidence shift below threshold
  - no new testable hypothesis
- [x] Enforce revision caps from mode profile.
- [x] Escalate or downgrade when cap is hit.

**Acceptance Criteria:**
- Tests cover converged in one round, cap hit with blocks, cap hit without blocks, and new hypothesis introduced.

---

## Epic RC-7: HTML Report And Terminal UX

### RC-7.1 HTML Renderer

**Status:** DONE  
**Priority:** P2  
**Suggested owner:** Report/UI assistant  
**Dependencies:** RC-5.3, RC-6.6  
**Files:**
- Create: `terminal/research_council/reports/html_renderer.py`
- Create: `terminal/research_council/reports/templates/council_report.html.j2`
- Test: `tests/research_council/test_html_render.py`

**Work:**
- [x] Render self-contained HTML to `reports/research_council/<run_id>.html`.
- [x] Use static embedded data. No runtime external API calls.
- [x] Include all 12 artifact sections:
  - header
  - executive summary
  - market state snapshot
  - council deliberation
  - TOT branches
  - plan
  - execution results
  - critic review
  - final recommendation
  - source trail
  - what to watch next
  - footer
- [x] Start with plain HTML/CSS. Add Chart.js/Mermaid only after static report tests pass.

**Acceptance Criteria:**
- Fixture HTML contains all required sections.
- HTML includes embedded JSON dump or link to JSON artifact.
- No external API calls at render time.

### RC-7.2 `/council` Terminal Commands

**Status:** DONE (2026-05-27)  
**Priority:** P1  
**Suggested owner:** Terminal/router assistant  
**Dependencies:** RC-5.4  
**Files:**
- Modify: `nse_agent.py`
- Modify: `terminal/router/providers.py`
- Modify: `terminal/tools.py`
- Modify: `terminal/research_council/commands.py`
- Modify: `terminal/help.py`
- Modify: `docs/AGENT_ADDA_HELPFILE.md`
- Test: `tests/research_council/test_terminal_commands.py`
- Test: `tests/test_unified_router.py`

**Work:**
- [x] Add command parsing for:
  - `/council today --horizon swing --risk moderate`
  - `/council sector --date latest`
  - `/council stock MODISONLTD --horizon swing`
  - `/council compare APOLLO BEL HAL --horizon positional`
  - `/council strategy "Stage 2 breakout with volume confirmation" --family stage2_breakout`
  - `/council intraday --scan vwap-reclaim`
  - `/council review --run latest`
  - `/council report --run latest --format html`
  - `/council resume --run <id>`
  - `/council steward`
  - `/council debug --run <id>`
  - `/council export --run <id> --format json`
- [x] Wire commands to tool wrappers from RC-7.3.
- [x] Update help/autocomplete surfaces.

**Acceptance Criteria:**
- Helpfile lists all `/council` commands.
- Router tests prove `/council` commands do not fall through to stock symbol analysis.
- Verification: `214 passed` across `tests/research_council`, `tests/test_unified_router.py`, `tests/test_tool_catalog.py`, and `tests/test_terminal_tools_registry.py`.
- Dry-run smoke: `/council today --horizon swing --risk moderate --dry-run` reaches `persistence`.

### RC-7.3 Public Tool Surface

**Status:** DONE (2026-05-27)  
**Priority:** P1  
**Suggested owner:** Tools assistant  
**Dependencies:** RC-5.4  
**Files:**
- Modify: `terminal/tools.py`
- Test: `tests/research_council/test_tool_surface.py`

**Work:**
- [x] Add public tool wrappers:
  - `build_research_evidence_pack`
  - `run_research_council`
  - `run_data_steward_check`
  - `compose_plan`
  - `execute_plan`
  - `review_plan_execution`
  - `run_critic_review`
  - `apply_revision_round`
  - `synthesize_council_decision`
  - `render_research_council_report`
  - `persist_research_council_run`
  - `resume_council_run`
- [x] Ensure wrappers return compact dicts appropriate for Agent Adda rendering.

**Acceptance Criteria:**
- Each tool wrapper has a smoke test.
- Tool failures return structured errors with source trail where available.
- Verification: `tests/research_council/test_tool_surface.py`, catalog sync, and `tests/test_terminal_tools_registry.py` pass.

### RC-7.4 Report Review Mode

**Status:** DONE (2026-05-27)  
**Priority:** P2  
**Suggested owner:** Report QA assistant  
**Dependencies:** RC-7.2, RC-6.5  
**Files:**
- Modify: `terminal/research_council/mode_profiles.py`
- Modify: `terminal/research_council/states/market_state.py`
- Modify: `terminal/research_council/states/critic_review.py`
- Modify: `terminal/research_council/states/specialist_pass.py`
- Modify: `terminal/research_council/states/branch_deliberation.py`
- Create: `terminal/research_council/report_review.py`
- Test: `tests/research_council/test_report_review_mode.py`

**Work:**
- [x] Route report file/path review requests to `report_review`.
- [x] Use Data Quality and Evidence critics only.
- [x] No plan loop.
- [x] Return file/line findings and remediation.

**Acceptance Criteria:**
- A report containing `REQUIRED TOOL VALIDATION FAILED` is flagged with missing evidence and source trail.
- `/council review --file <path>` runs report-review mode and renders a review report.
- Verification: `219 passed` across `tests/research_council`, `tests/test_unified_router.py`, `tests/test_tool_catalog.py`, and `tests/test_terminal_tools_registry.py`.

---

## Epic RC-8: Coder / Quant And Strategy Build

### RC-8.1 Coder Sandbox

**Status:** DONE (2026-05-27)  
**Priority:** P1  
**Suggested owner:** Quant/coder assistant  
**Dependencies:** RC-5.4  
**Files:**
- Create: `terminal/research_council/coder_sandbox.py`
- Create: `terminal/research_council/features/__init__.py`
- Create: `terminal/research_council/strategies/__init__.py`
- Test: `tests/research_council/test_coder_sandbox.py`

**Work:**
- [x] Restrict generated feature writes to `terminal/research_council/features/`.
- [x] Restrict generated strategy specs to `terminal/research_council/strategies/`.
- [x] Block destructive SQL and file operations.
- [x] Block live-order/broker functions.
- [x] Require tests before generated code can be used in council output.

**Acceptance Criteria:**
- Attempts to write outside sandbox fail.
- `DROP`, `DELETE`, `UPDATE` without explicit approval are blocked.
- Test scaffold is created for generated feature code.
- Feature readiness requires both feature file and matching test scaffold.
- Verification: `155 passed` in `tests/research_council`.

### RC-8.2 Strategy Build Agent

**Status:** DONE (2026-05-27)  
**Priority:** P1  
**Suggested owner:** Strategy assistant  
**Dependencies:** RC-8.1  
**Files:**
- Create: `terminal/research_council/agents/coder_quant.py`
- Test: `tests/research_council/test_specialists/test_coder_quant.py`

**Work:**
- [x] Convert viable branch theses into `StrategyBuildRequest`.
- [x] Whitelist initial strategy families:
  - `stage2_breakout`
  - `supertrend_continuation`
  - `rsi_pullback_stage2`
  - `fifty_two_week_high`
  - `vcp_breakout`
  - `earnings_momentum`
- [x] Generate `StrategyBuildResult` with train/validation results only in first pass.
- [x] Do not expose test split until strategy lock.
- [x] Add AI-driven strategy proposal layer with injectable LLM call boundary.
- [x] Keep AI confined to strategy design; deterministic compiler/backtester owns validation and metrics.

**Acceptance Criteria:**
- Out-of-whitelist family escalates instead of running.
- Strategy build returns assumptions, limitations, trade count, metrics, and verdict.
- AI proposal requests for held-out test data are blocked before compilation.
- Unsafe/free-form executable rules from AI are rejected by the strategy DSL compiler.
- Verification: `8 passed` in `tests/research_council/test_specialists/test_coder_quant.py`; `169 passed` in `tests/research_council`.

### RC-8.3 Strategy Council Integration

**Status:** DONE (2026-05-27)  
**Priority:** P1  
**Suggested owner:** Backtesting assistant  
**Dependencies:** RC-8.2  
**Files:**
- Modify: `terminal/research_council/agents/coder_quant.py`
- Modify: `terminal/research_council/tool_adapters.py`
- Test: `tests/research_council/test_strategy_build_mode.py`

**Work:**
- [x] Reuse `backtesting.strategy_council` where possible.
- [x] Map `StrategyBuildRequest` to existing `StrategySpec` or safe DSL proposal.
- [x] Persist to `recommendation_reports.strategy_specs`.
- [x] Persist train/validation backtests to `recommendation_reports.backtest_results`.
- [x] Add leakage guard for test split.
- [x] Make the user-facing `strategy.build` adapter require the AI proposal layer before spec/backtest execution.

**Acceptance Criteria:**
- `/council strategy "Stage 2 breakout with volume confirmation"` produces a validated spec and train/validation backtest results.
- Test split is not queried before lock.
- LLM unavailable is reported as a structured `llm_unavailable` error instead of silently falling back for the user-facing strategy workflow.
- Verification: `16 passed` in AI Coder Quant + strategy build focused tests; `171 passed` in `tests/research_council`; `py_compile` passed for changed Research Council modules.

### RC-8.4 Multi-Route Strategy Option Sweep

**Status:** DONE (2026-05-27)  
**Priority:** P1  
**Suggested owner:** Strategy assistant  
**Dependencies:** RC-8.3  
**Files:**
- Modify: `terminal/research_council/agents/coder_quant.py`
- Modify: `terminal/research_council/tool_adapters.py`
- Test: `tests/research_council/test_specialists/test_coder_quant.py`
- Test: `tests/research_council/test_strategy_build_mode.py`

**Work:**
- [x] Run a matrix of whitelisted strategy families and allowed horizons over the same real EOD frame.
- [x] Keep each candidate compiled through the safe Strategy Council DSL.
- [x] Execute train/validation only; never query held-out test split.
- [x] Rank options by validation quality, validation trade count, total trade count, and verdict.
- [x] Return rejected/ambiguous routes with limitations instead of dropping them silently.

**Acceptance Criteria:**
- A single Coder Quant call can compare multiple route options.
- Unsupported families are recorded as `UNTESTABLE`, not executed.
- Ranking never includes test-split metrics.
- Real-data smoke can explain why the top route won or why all routes remain ambiguous/refuted.
- Verification: `16 passed` in Coder Quant/strategy-build focused tests; `177 passed` in `tests/research_council`; real RELIANCE PostgreSQL EOD sweep ran 9 routes over 2021-05-17 to 2026-05-26 and kept all routes `AMBIGUOUS` due to low/no validation evidence.

---

## Epic RC-9: LLM Phase 2, Resume, Refresh, Email

### RC-9.1 Lazy LLM Client And JSON Validation

**Status:** DONE (2026-05-31; Ollama cascade, deterministic fallback, @pytest.mark.llm added)  
**Priority:** P2  
**Suggested owner:** LLM assistant  
**Dependencies:** RC-5.4, RC-6.6  
**Files:**
- Modify: `terminal/research_council/llm_client.py`
- Modify: `terminal/research_council/agents/base.py`
- Modify: `terminal/research_council/critics/base.py`
- Test: `tests/research_council/test_llm_fallback.py`

**Work:**
- [x] Lazy-initialize provider clients. No `OPENAI_API_KEY` required at import time.
- [x] Add OpenAI JSON-object provider boundary for Coder Quant strategy proposals.
- [x] Default Research Council AI strategy-design calls to `gpt-5.5`, overrideable via `RESEARCH_COUNCIL_LLM_MODEL`.
- [x] Load `.env` lazily for Research Council LLM calls when process env is not already populated.
- [x] Omit non-default temperature for GPT-5/o-series models that reject custom temperature.
- [ ] Reuse Agent Adda's OpenAI/Ollama cascade where possible.
- [x] Validate JSON parsing and return structured provider-unavailable errors.
- [x] Retry once with validator error for schema-invalid JSON.
- [ ] Fall back to deterministic for non-strategy-build overlays.
- [ ] Mark LLM tests with `@pytest.mark.llm`.

**Acceptance Criteria:**
- Import works without API key.
- Coder Quant user-facing strategy build requires an AI proposal and reports `llm_unavailable` rather than silently using deterministic strategy design.
- Remaining: OpenAI/Ollama cascade and deterministic fallback policy for non-strategy-build overlays.
- Verification: `6 passed` in `tests/research_council/test_llm_client.py`; covered by `175 passed` in `tests/research_council`. Live `strategy.build` smoke reached GPT-5.5, produced `ai_coder_quant` `stage2` spec, and stopped at `requires_eod_data_for_backtest` when no EOD frame was supplied.

### RC-9.2 LLM Agent Overlays

**Status:** DEFERRED  
**Priority:** P2  
**Suggested owner:** LLM/persona assistant  
**Dependencies:** RC-9.1  
**Files:**
- Modify: `terminal/research_council/agents/prompts.py`
- Modify: selected agent modules
- Test: `tests/research_council/test_llm_agents.py`

**Work:**
- [ ] Enable LLM overlays only for selected agents first:
  - Chair
  - Catalyst
  - F&O/Risk
  - Evidence Critic
- [ ] Store prompts as atomic fragments or named constants with version IDs.
- [ ] Never expose private chain-of-thought.

**Acceptance Criteria:**
- LLM outputs validate to the same schemas as deterministic outputs.
- Deterministic fallback remains default in CI.

### RC-9.3 Resume And Export

**Status:** DONE (2026-05-31)  
**Priority:** P2  
**Suggested owner:** Persistence assistant  
**Dependencies:** RC-5.4  
**Files:**
- Modify: `terminal/research_council/persistence.py`
- Modify: `terminal/research_council/engine.py`
- Test: `tests/research_council/test_resume_export.py`

**Work:**
- [ ] Implement `resume_council_run(council_run_id)`.
- [ ] Export full council state as JSON.
- [ ] Load prior evidence pack, findings, plan, results, critics, and decision.

**Acceptance Criteria:**
- `/council resume --run <id>` reconstructs the state.
- `/council export --run <id> --format json` writes a valid JSON artifact.

### RC-9.4 Daily Refresh Integration

**Status:** DEFERRED  
**Priority:** P2  
**Suggested owner:** Refresh assistant  
**Dependencies:** RC-7.2, RC-7.3, RC-5.4  
**Files:**
- Modify: `daily_refresh.py`
- Test: `tests/research_council/test_daily_refresh_integration.py`

**Work:**
- [ ] Do not add automatic full council runs immediately.
- [ ] First add optional flag/env:
  - `AGENT_ADDA_RUN_RESEARCH_COUNCIL=1`
  - or CLI `--run-research-council`
- [ ] Start with one market council run, not both swing and positional.
- [ ] Log run ID, status, final label, and report path.

**Acceptance Criteria:**
- Daily refresh remains unchanged by default.
- With flag enabled, refresh triggers one council run after data load.

### RC-9.5 Email Digest Integration

**Status:** DEFERRED  
**Priority:** P2  
**Suggested owner:** Email/reporting assistant  
**Dependencies:** RC-7.1, RC-9.4  
**Files:**
- Modify: `terminal/email_dispatcher.py`
- Modify: existing daily email script if separate
- Test: `tests/research_council/test_email_digest_integration.py`

**Work:**
- [ ] Attach or link latest council HTML report.
- [ ] Include executive summary in email preamble.
- [ ] Skip attachment if report generation failed.

**Acceptance Criteria:**
- Dummy SMTP test confirms council report can be included.
- Email body clearly says research-only.

### RC-9.6 Council Intelligence Query Expansion

**Status:** DONE (2026-05-27)  
**Priority:** P1  
**Suggested owner:** Routing/intelligence assistant  
**Dependencies:** RC-5.4, RC-8.4  
**Files:**
- Modify: `terminal/research_council/engine.py`
- Modify: `terminal/research_council/states/route.py`
- Modify: `terminal/research_council/mode_profiles.py`
- Modify: `terminal/research_council/commands.py`
- Modify: `terminal/research_council/schemas.py`
- Test: `tests/research_council/test_intelligence_routing.py`

**Work:**
- [x] Add first-class `sector_opportunity` Council mode.
- [x] Infer sector-opportunity mode from natural language objectives such as "Analyze NIFTY AUTO and identify best potential stocks".
- [x] Expand the user objective into auditable sub-questions.
- [x] Select the agent route for sector opportunity work.
- [x] Gate Coder Quant behind shortlist creation using `coder_quant_policy = shortlist_only`.
- [x] Route `/council sector ...` into `sector_opportunity`.

**Acceptance Criteria:**
- User does not need to manually specify sector scan, shortlist, and quant sweep steps.
- `state.route_decision` records workflow, sector, expanded objective, sub-questions, selected agents, and execution order.
- Strategy-build requests still route Coder Quant as the primary agent.
- Verification: `20 passed` in route/mode/command focused tests.

---

## Epic RC-10: Comprehensive Verification

### RC-10.1 Test Pyramid Completion

**Status:** READY  
**Priority:** P1  
**Suggested owner:** QA assistant  
**Dependencies:** RC-5.4, RC-6.6, RC-7.1  
**Files:**
- Tests under `tests/research_council/`

**Work:**
- [ ] Add unit tests for every deterministic persona.
- [ ] Add schema tests for every output contract.
- [ ] Add state integration tests for all state handlers.
- [ ] Add convergence tests.
- [ ] Add persistence tests with transaction rollback.
- [ ] Add markdown and HTML render tests.
- [ ] Add one fixture end-to-end market council test.
- [ ] Add one real-data smoke test guarded by marker.

**Acceptance Criteria:**
- `pytest -q tests/research_council` passes.
- Full suite still passes after integration.

### RC-10.2 Performance And Budget Checks

**Status:** DONE (2026-05-31)  
**Priority:** P2  
**Suggested owner:** Performance assistant  
**Dependencies:** RC-5.4  
**Files:**
- Create: `tests/research_council/test_budget_limits.py`
- Modify: `terminal/research_council/engine.py`

**Work:**
- [ ] Track wall-clock budget in `CouncilState.budgets`.
- [ ] Track approximate payload size or token budget once LLM overlays exist.
- [ ] Abort with `abort_budget` when hard cap is exceeded.
- [ ] Keep Market Council deterministic target under 8 minutes.

**Acceptance Criteria:**
- Budget cap test transitions to `abort_budget`.
- Normal fixture run remains below configured cap.

---

## Recommended Parallel Execution Order

1. RC-0.1, RC-0.2, RC-0.3 can run in parallel.
2. RC-1.1 starts after RC-0.1.
3. RC-1.2 and RC-1.3 start after RC-1.1.
4. RC-2.1, RC-2.2 start after schemas.
5. RC-3.1 starts after schemas and fixture pack.
6. RC-3.2, RC-3.3, RC-3.4 can run in parallel.
7. RC-4.2 can run in parallel after RC-0.3.
8. RC-4.1, RC-4.3, RC-4.4, RC-4.5 proceed sequentially.
9. RC-5.1, RC-5.2, RC-5.3 create the MVP.
10. RC-6 specialist/critic rows can split across assistants.
11. RC-7 terminal/report work can run after MVP.
12. RC-8 and RC-9 are later-phase work.

## First MVP Definition

The first shippable version is:

```bash
/council today --horizon swing --risk moderate
```

It must:

- run Data Steward
- build and persist an Evidence Pack
- run Sector, Technical, and Fundamental agents
- compose branch summaries
- build and execute a deterministic plan
- synthesize a research-only decision
- render markdown
- persist run metadata

It does not need:

- LLM personas
- coder-generated strategies
- automatic daily refresh execution
- email integration
- interactive HTML charts

## Global Definition Of Done

- No unsupported market claim is emitted.
- Every report has a source trail and missing evidence section.
- PostgreSQL migrations are idempotent.
- `/council steward` works independently.
- `/council today --evidence-only` works independently.
- `/council today --horizon swing --risk moderate` completes on fixture data.
- Full deterministic council path passes CI without API keys.
- Research-only disclaimer appears in terminal and report outputs.
