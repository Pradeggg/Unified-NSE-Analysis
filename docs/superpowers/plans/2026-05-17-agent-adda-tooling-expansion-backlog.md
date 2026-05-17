# Agent Adda Tooling Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add and wire a comprehensive PostgreSQL-first, evidence-gated tool layer for data health, latest results, report context, situation assessment, entity resolution, Strategy Council evidence, F&O overviews, company evidence audit, and final answer validation.

**Architecture:** Keep `terminal/tools.py` as the OpenAI-compatible registry, but move new implementation families into focused modules and register thin wrappers. Add pre-routing situation assessment before keyword routing, then enforce required-tool, requested-symbol, and evidence-matrix validation before final rendering.

**Tech Stack:** Python 3.10+, PostgreSQL via existing project DSN, pandas where already used, existing `terminal.tools` registry, existing `nse_agent.py` command layer, pytest/unittest tests, no new paid data dependencies.

**Implementation status (2026-05-17):** Implemented on branch `agent-adda-tooling-expansion` through Phase 9. Covered PostgreSQL doctor tools, report context, entity resolution, situation assessment v2, latest-results composite, evidence gate, Strategy Council enrichment, F&O composite overview, company evidence audit tools, and scenario regressions. Final verification: `619 passed, 40 subtests passed`; `py_compile` passed for the modified runtime modules; `/doctor` smoke passed in single-query mode.

---

## Source Design

Read first:

- `docs/superpowers/specs/2026-05-17-agent-adda-tooling-expansion-design.md`
- `docs/BACKLOG.md`, section `Backlog Reconciliation — 2026-05-17`
- `terminal/tools.py`
- `terminal/agent.py`
- `terminal/situation_assessment.py`
- `nse_agent.py`

## File Structure

Create focused modules:

- `terminal/postgres_tools.py`
  - PostgreSQL health, schema assurance, coverage audit, source manifest.
- `terminal/report_context.py`
  - Report listing, last-report state, report reading, report summaries.
- `terminal/entity_resolution.py`
  - Canonical entity/symbol/index resolution helpers.
- `terminal/evidence_gate.py`
  - Required-tool and claim/evidence matrix validation.
- `terminal/results_tools.py`
  - Latest-results composite evidence pack over filing discovery/parsing.
- `terminal/fno_composite.py`
  - Composite F&O overview and recommendation evidence pack.
- `terminal/company_evidence_tools.py`
  - Company search audit and PostgreSQL evidence promotion.

Modify existing files:

- `terminal/tools.py`
  - Register new tool wrappers.
- `terminal/agent.py`
  - Wire situation assessment, entity context, evidence planning, and final validation.
- `terminal/situation_assessment.py`
  - Upgrade deterministic assessment to v2 contract.
- `nse_agent.py`
  - Add or update slash commands such as `/doctor`, `/report latest`, `/results`, `/fno`.
- `terminal/data_readiness.py`
  - Include PostgreSQL doctor/coverage output.
- `backtesting/strategy_council/evidence.py`
  - Enrich Strategy Council evidence packs.

Add tests:

- `tests/test_postgres_tools.py`
- `tests/test_report_context_tools.py`
- `tests/test_entity_resolution.py`
- `tests/test_evidence_gate.py`
- `tests/test_results_tools.py`
- `tests/test_fno_composite.py`
- `tests/test_company_evidence_tools.py`
- Extend `tests/test_situation_assessment.py`
- Extend `tests/test_terminal_agent_market_prompt.py`
- Extend Strategy Council tests around enriched evidence.

---

## Phase 0: Tool Registry Hygiene

### Task 0.1: Add Registry Introspection Tests

**Files:**
- Modify: `tests/test_terminal_tools_registry.py` or create it if absent.
- Modify: `terminal/tools.py`

- [ ] **Step 1: Write failing registry test**

Add a test that imports `terminal.tools.TOOL_REGISTRY` and asserts every registered tool has a callable, non-empty description, and JSON-schema-like params.

Run:

```bash
.venv/bin/python -m pytest tests/test_terminal_tools_registry.py -q
```

Expected: fail if the file does not exist or any registry entry is malformed.

- [ ] **Step 2: Fix registry issues only**

Do not add new tools in this task. Repair malformed existing entries if the test exposes them.

- [ ] **Step 3: Verify**

Run:

```bash
.venv/bin/python -m pytest tests/test_terminal_tools_registry.py -q
```

Expected: pass.

---

## Phase 1: PostgreSQL Operations Tools

### Task 1.1: Implement `terminal/postgres_tools.py`

**Files:**
- Create: `terminal/postgres_tools.py`
- Test: `tests/test_postgres_tools.py`
- Modify: `terminal/tools.py`

**Tools:**

- `get_postgres_health`
- `ensure_postgres_schema`
- `audit_postgres_coverage`
- `load_historical_eod_to_postgres`
- `load_intraday_ohlcv_to_postgres`
- `get_data_source_manifest`

- [ ] **Step 1: Write tests for health and manifest**

Cover:

- healthy socket connection
- connection failure
- missing schema
- missing required table
- `/tmp` socket DSN reported separately from `localhost`
- source manifest labels PostgreSQL as primary and SQLite as legacy/cache only

Run:

```bash
.venv/bin/python -m pytest tests/test_postgres_tools.py -q
```

Expected: fail because module does not exist.

- [ ] **Step 2: Implement health and manifest**

Use existing environment/DSN conventions. Do not hardcode user-specific paths except the project-relative defaults already used by the repo.

- [ ] **Step 3: Register wrappers**

Register the new tools in `terminal/tools.py` using `TOOL_REGISTRY.update`.

- [ ] **Step 4: Wire readiness**

Modify `terminal/data_readiness.py` so `/data-status` can include PostgreSQL health and coverage.

- [ ] **Step 5: Verify**

Run:

```bash
.venv/bin/python -m pytest tests/test_postgres_tools.py tests/test_data_readiness.py -q
```

Expected: pass.

### Task 1.2: Add `/doctor`

**Files:**
- Modify: `nse_agent.py`
- Modify: `terminal/help.py`
- Test: `tests/test_nse_agent_data_readiness.py`

- [ ] **Step 1: Add failing terminal command tests**

Cover:

- `/doctor` prints PostgreSQL health.
- `/doctor --repair` calls schema assurance through an injectable function.
- failure prints actionable next step instead of a traceback.

- [ ] **Step 2: Implement command route**

Wire `/doctor` before generic agent routing.

- [ ] **Step 3: Verify**

Run:

```bash
.venv/bin/python -m pytest tests/test_nse_agent_data_readiness.py tests/test_postgres_tools.py -q
```

Expected: pass.

---

## Phase 2: Report Context Tools

### Task 2.1: Implement Report Context Module

**Files:**
- Create: `terminal/report_context.py`
- Test: `tests/test_report_context_tools.py`
- Modify: `terminal/tools.py`
- Modify: `nse_agent.py`

**Tools:**

- `list_generated_reports`
- `get_last_report`
- `open_report`
- `read_report`
- `summarize_report`
- `compare_reports`

- [ ] **Step 1: Write tests**

Cover:

- listing generated reports by newest first
- extracting symbol/type/date from known report filenames
- reading markdown and HTML reports
- summarizing without changing symbol context
- returning `needs_clarification` when no last report exists

- [ ] **Step 2: Implement module**

Use `reports/generated`, `reports/strategy_council`, and any existing generated report paths. Keep output JSON-serializable.

- [ ] **Step 3: Wire terminal memory**

Replace ad hoc report memory in `nse_agent.py` with `terminal.report_context` functions where practical. Preserve existing behavior.

- [ ] **Step 4: Register tools**

Add registry entries in `terminal/tools.py`.

- [ ] **Step 5: Verify**

Run:

```bash
.venv/bin/python -m pytest tests/test_report_context_tools.py tests/test_terminal_agent_market_prompt.py -q
```

Expected: pass.

---

## Phase 3: Entity Resolution And Situation Assessment v2

### Task 3.1: Implement Entity Resolution Module

**Files:**
- Create: `terminal/entity_resolution.py`
- Test: `tests/test_entity_resolution.py`
- Modify: `terminal/agent.py`
- Modify: `terminal/tools.py`

**Tools:**

- `resolve_stock_entity`
- `resolve_company_alias`
- `validate_requested_symbols`
- `detect_non_symbol_terms`
- `resolve_index_or_stock`

- [ ] **Step 1: Write regression tests**

Cover:

- `USL` resolves to United Spirits / canonical NSE symbol, not `AURIGROW`.
- `ADX`, `MA`, `RSI`, and `MACD` are technical terms, not requested symbols.
- `NIFTY`, `NIFTY 50`, and `BANKNIFTY` resolve as index/derivative underlyings, not equity symbols.
- exact uppercase symbols win over fuzzy matches.
- unresolved exact ticker-looking input returns explicit unresolved status.

- [ ] **Step 2: Implement module**

Use existing local symbol maps first. Add a small term blocklist for common technical indicators, topics, and command nouns.

- [ ] **Step 3: Wire into agent extraction**

Use entity resolution before keyword intent routing and before final symbol validation.

- [ ] **Step 4: Verify**

Run:

```bash
.venv/bin/python -m pytest tests/test_entity_resolution.py tests/test_terminal_agent_market_prompt.py -q
```

Expected: pass.

### Task 3.2: Upgrade Situation Assessment v2

**Files:**
- Modify: `terminal/situation_assessment.py`
- Modify: `terminal/agent.py`
- Test: `tests/test_situation_assessment.py`

**Tools:**

- `assess_user_situation`
- `resolve_conversation_reference`
- `resolve_entity_context`
- `validate_intent_evidence_plan`
- `request_clarification`

- [ ] **Step 1: Add tests for ambiguous follow-ups**

Cover:

- `open the report` after Strategy Council resolves to that report.
- `based on the report how has been the results` uses the last report context.
- `were these pulled from last 30mins` answers from prior screener context or requests clarification.
- `search USL growth strategy` treats USL as entity and growth strategy as topic.

- [ ] **Step 2: Implement v2 assessment outputs**

Return a compact object with:

- `applies`
- `user_is_asking`
- `context_found`
- `resolved_entities`
- `evidence_plan`
- `decision`
- `clarification_question`

- [ ] **Step 3: Wire before routing**

Call situation assessment before keyword routing in `terminal/agent.py`. If confidence is low and context matters, return clarification.

- [ ] **Step 4: Verify**

Run:

```bash
.venv/bin/python -m pytest tests/test_situation_assessment.py tests/test_terminal_agent_market_prompt.py -q
```

Expected: pass.

---

## Phase 4: Latest Results And Filing Tools

### Task 4.1: Implement Latest Results Composite

**Files:**
- Create: `terminal/results_tools.py`
- Modify: `financial_filing_agent.py`
- Modify: `terminal/tools.py`
- Modify: `terminal/agent.py`
- Test: `tests/test_results_tools.py`

**Tools:**

- `discover_financial_filings`
- `ingest_financial_filing`
- `parse_financial_filing`
- `parse_xbrl_filing`
- `parse_pdf_filing`
- `reconcile_filing_facts`
- `get_latest_results`
- `summarize_latest_results`

- [ ] **Step 1: Write tests using fixtures/mocks**

Cover:

- result discovery returns ranked filing candidates
- direct URL ingestion remains supported
- PDF-only filings are marked partial if OCR is needed
- latest-results summary never invents revenue/PAT/EPS if parsing did not return them
- source trail includes discovery, ingestion, parse, and reconciliation status

- [ ] **Step 2: Implement composite wrapper**

Reuse existing `financial_filing_agent.py` ingestion/parsing where available. Keep `get_latest_results` as the single high-level evidence pack used by agent flows.

- [ ] **Step 3: Wire `/results` and natural prompts**

Ensure `/results SYMBOL`, `latest results for SYMBOL`, and `SYMBOL quarterly results` all use `get_latest_results`.

- [ ] **Step 4: Verify**

Run:

```bash
.venv/bin/python -m pytest tests/test_results_tools.py tests/test_terminal_agent_market_prompt.py -q
```

Expected: pass.

---

## Phase 5: Evidence Gate

### Task 5.1: Implement Evidence Gate Module

**Files:**
- Create: `terminal/evidence_gate.py`
- Modify: `terminal/agent.py`
- Modify: report renderers as needed
- Test: `tests/test_evidence_gate.py`

**Tools:**

- `build_evidence_matrix`
- `validate_answer_against_evidence`
- `render_missing_evidence_block`
- `validate_required_tools_executed`

- [ ] **Step 1: Write tests**

Cover unsupported claims for:

- broker targets
- concall comments
- latest results
- forensic scores
- sector claims
- F&O recommendation
- Strategy Council recommendation

- [ ] **Step 2: Implement required evidence categories**

Use simple categories first:

- `technical`
- `fundamental`
- `results`
- `filing`
- `catalyst`
- `forensic`
- `sector`
- `fno`
- `strategy`
- `report_context`

- [ ] **Step 3: Wire final rendering**

Before final answer rendering, validate required tools and requested symbols. Render missing evidence instead of unsupported prose.

- [ ] **Step 4: Verify**

Run:

```bash
.venv/bin/python -m pytest tests/test_evidence_gate.py tests/test_terminal_agent_market_prompt.py -q
```

Expected: pass.

---

## Phase 6: Strategy Council Evidence Enrichment

### Task 6.1: Enrich Evidence Pack

**Files:**
- Modify: `backtesting/strategy_council/evidence.py`
- Modify: `backtesting/strategy_council/report.py`
- Test: `tests/test_strategy_council_evidence.py`

**Tools:**

- `build_strategy_council_evidence_pack`
- `enrich_strategy_council_evidence`
- `validate_strategy_council_evidence`
- `score_strategy_data_readiness`

- [ ] **Step 1: Write tests**

Cover:

- fundamentals loaded from PostgreSQL when available
- market breadth included when available
- latest results included through `get_latest_results`
- missing evidence records attempted source and reason
- readiness score drops when mandatory strategy evidence is absent

- [ ] **Step 2: Implement enrichment**

Keep base EOD evidence point-in-time safe. Add optional evidence with explicit freshness and source metadata.

- [ ] **Step 3: Update report**

Show enriched evidence and missing evidence separately.

- [ ] **Step 4: Verify**

Run:

```bash
.venv/bin/python -m pytest tests/test_strategy_council_evidence.py tests/test_strategy_council_loop.py -q
```

Expected: pass.

---

## Phase 7: Composite F&O Tools

### Task 7.1: Implement F&O Composite Overview

**Files:**
- Create: `terminal/fno_composite.py`
- Modify: `terminal/tools.py`
- Modify: `terminal/agent.py`
- Test: `tests/test_fno_composite.py`

**Tools:**

- `get_fno_overview`
- `get_option_chain_summary`
- `get_max_pain`
- `get_pcr_summary`
- `get_top_oi_strikes`
- `get_futures_basis`
- `get_cost_of_carry`
- `recommend_options_strategy`

- [ ] **Step 1: Write tests**

Cover:

- full NIFTY overview requires option chain and futures evidence
- missing chain blocks strategy recommendation
- missing futures blocks basis/carry claim
- recommendation includes conditions, invalidation, max loss/profit where applicable, and research-only framing

- [ ] **Step 2: Implement composites**

Reuse existing F&O low-level tools where available. Keep calculations deterministic.

- [ ] **Step 3: Wire `/fno` and natural prompts**

Route comprehensive F&O prompts to `get_fno_overview` instead of generic market overview.

- [ ] **Step 4: Verify**

Run:

```bash
.venv/bin/python -m pytest tests/test_fno_composite.py tests/test_terminal_agent_market_prompt.py -q
```

Expected: pass.

---

## Phase 8: Company Evidence Audit Tools

### Task 8.1: Implement Company Evidence Audit

**Files:**
- Create: `terminal/company_evidence_tools.py`
- Modify: company intelligence storage modules
- Modify: `terminal/tools.py`
- Test: `tests/test_company_evidence_tools.py`

**Tools:**

- `audit_company_search`
- `search_company_official_sources`
- `search_company_filings`
- `promote_company_evidence_to_postgres`
- `get_company_evidence_coverage`

- [ ] **Step 1: Write tests**

Cover:

- every search attempt records query, alias, source group, result count, parse status, and failure reason
- official sources are searched before external web sources
- no-result cases produce auditable gaps
- promoted evidence records source URL/path and category

- [ ] **Step 2: Implement PostgreSQL-first audit records**

Use PostgreSQL for durable audit state. Keep existing SQLite FTS only if needed for local cache/search performance.

- [ ] **Step 3: Wire Company X-Ray**

Make `/company-xray` and `/company-index` report evidence coverage from audit records.

- [ ] **Step 4: Verify**

Run:

```bash
.venv/bin/python -m pytest tests/test_company_evidence_tools.py -q
```

Expected: pass.

---

## Phase 9: End-To-End Regression Suite

### Task 9.1: Add Scenario Tests

**Files:**
- Modify: `tests/test_terminal_agent_market_prompt.py`
- Add: `tests/test_agent_tooling_expansion_scenarios.py`

- [ ] **Step 1: Add 30 representative scenarios**

Include:

- `/strategy-council KIRLOSENG llm` then `open the report`
- `Based on the report how has been the results`
- `search USL growth strategy`
- `SAKAR ADX MA setup`
- `Give a comprehensive F&O overview for NIFTY`
- `were these pulled from last 30mins`
- `latest results for DMART`
- `run forensic analysis for TATASTEEL`
- `stage 2 stocks then scan these live`
- `is PostgreSQL running`

- [ ] **Step 2: Assert route and required tools**

Each scenario must assert:

- intended route
- requested symbols
- required tools
- no unrelated symbol substitution
- missing evidence behavior when applicable

- [ ] **Step 3: Run focused suite**

Run:

```bash
.venv/bin/python -m pytest tests/test_agent_tooling_expansion_scenarios.py tests/test_terminal_agent_market_prompt.py -q
```

Expected: pass.

### Task 9.2: Full Verification

- [ ] **Step 1: Run full tests**

Run:

```bash
.venv/bin/python -m pytest -q
```

Expected: pass.

- [ ] **Step 2: Run py_compile**

Run:

```bash
.venv/bin/python -m py_compile terminal/tools.py terminal/agent.py terminal/situation_assessment.py nse_agent.py
```

Expected: exit code 0.

- [ ] **Step 3: Run live-safe smoke commands**

Run non-mutating commands only:

```bash
.venv/bin/python nse_agent.py --query "/data-status"
.venv/bin/python nse_agent.py --query "/doctor"
.venv/bin/python nse_agent.py --query "latest results for DMART"
.venv/bin/python nse_agent.py --query "Give a comprehensive F&O overview for NIFTY"
```

Expected: each command returns source trail or missing-evidence block without traceback.

---

## Backlog Priority Summary

| Priority | Work |
|---|---|
| P0 | PostgreSQL operations tools, entity resolution, situation assessment v2, evidence gate, F&O evidence contract |
| P1 | report context tools, latest-results composite, Strategy Council enrichment |
| P2 | company evidence audit, broad scenario suite, dashboard/report polish |

## Non-Goals

- Do not add new paid market data dependencies.
- Do not reintroduce SQLite as a primary durable evidence store.
- Do not let the LLM calculate financial facts or backtest returns.
- Do not implement new dashboard visuals until evidence/routing tools are stable.

## Execution Handoff

Recommended execution mode: subagent-driven development with one task family per worker because PostgreSQL tools, report context, F&O composite, latest results, and evidence gating have mostly separate write scopes.
