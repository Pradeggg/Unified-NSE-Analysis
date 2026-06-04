# Agent Adda Copilot Superpowers Implementation Backlog

> For agentic workers: this backlog is implementation-ready. Claim one task row at a time, read the listed context first, keep edits scoped to the named files, and run the task-specific verification before handing off.

**Goal:** Make Agent Adda behave like a transparent research copilot: explicit intent understanding, deterministic plans, visible execution steps, evidence-backed outputs, verification footers, user-tunable tone/verbosity, task memory, and market-native "superpower" workflows.

**Primary outcome:** Agent Adda should not just answer market questions. It should show what it understood, what it plans to run, which tools executed, what passed or failed, how results were filtered/ranked, what evidence is missing, and what the next useful commands are.

**Architecture principle:** Do not make this only a larger LLM prompt. Build a deterministic interaction layer:

```text
user query
  -> router / command parser
  -> interaction profile
  -> workflow plan object
  -> tool execution with step events
  -> renderer shows trace / table / verification
  -> LLM summarizes, critiques, and narrates where useful
```

**Tech stack:** Python 3.10+, existing Rich terminal UI, existing `terminal.tools` registry, PostgreSQL-first market data, existing `nse_agent.py` command layer, pytest/unittest tests. No broker integration. No paid data dependency.

---

## Coordination Rules

- Do not edit generated reports/data unless a task explicitly asks for report regeneration.
- Prefer focused modules over expanding `nse_agent.py` and `terminal/tools.py`.
- Keep every workflow research-only. Do not introduce trading execution or advice language.
- Never expose raw hidden model reasoning. Show operational trace, assumptions, evidence, filters, and verification instead.
- Missing data must be visible as `missing`, `pending`, or `not_applicable`; do not infer it.
- Existing command behavior must remain backward compatible unless this backlog explicitly changes it.
- Use `.venv/bin/python -m pytest`, not bare `pytest`.
- If the worktree is dirty, stage only the files required for the claimed row.

## Canonical Context To Read

- `nse_agent.py`
- `terminal/agent.py`
- `terminal/tools.py`
- `terminal/help.py`
- `terminal/router/providers.py`
- `terminal/situation_assessment.py`
- `docs/superpowers/plans/2026-05-17-agent-adda-tooling-expansion-backlog.md`
- `docs/superpowers/plans/2026-05-12-agent-adda-deliberation-assess-backlog.md`
- `docs/superpowers/plans/2026-05-26-agent-adda-research-council-backlog.md`
- `docs/superpowers/specs/2026-05-25-agent-adda-claude-harness-inheritance-design.md`

## Status Legend

| Status | Meaning |
|---|---|
| READY | Can be picked up now |
| BLOCKED | Needs a dependency or decision first |
| PARTIAL | Some code exists but integration/tests are incomplete |
| DONE | Implemented, tested, and wired |
| DEFERRED | Intentionally later |

## Work Lanes

| Lane | Owns | Can Run In Parallel With |
|---|---|---|
| Interaction Profile | style, verbosity, step settings, persistence | Composite screener after API stabilizes |
| Execution Trail | step events, trace renderer, verification footer | Help/autocomplete, report verification |
| Composite Screeners | quality breakout scanner, TradingView export | Interaction profile once renderer contract exists |
| Superpower Commands | `/brainstorm`, `/plan`, `/debug`, `/verify`, `/review` | Task memory after profile exists |
| Task Memory | `/status`, recent artifacts, active objective | Verification/report registry |
| Workflow Planner | reusable deterministic plan objects | Per-command adoption |
| Verification | report/link/data validation | Task memory and debug workflow |
| Portfolio Copilot | portfolio-aware plan/trace/action rationale | After execution trail and task memory |

---

## Epic AA-COP-0: Product Contract And Guardrails

### AA-COP-0.1 Define Copilot Product Contract

**Status:** READY  
**Priority:** P0  
**Suggested owner:** Product/spec assistant  
**Files:**
- Create: `docs/superpowers/specs/2026-06-04-agent-adda-copilot-superpowers-design.md`
- Optionally modify: this backlog with any accepted decisions

**Work:**
- [ ] Define the user-facing contract for Agent Adda copilot behavior:
  - understood intent
  - assumptions
  - plan
  - progress
  - result
  - verification
  - next commands
- [ ] Define what may be shown:
  - operational trace
  - tool calls
  - filters
  - counts
  - source trail
  - evidence gaps
- [ ] Define what must not be shown:
  - hidden chain-of-thought
  - unsupported conclusions
  - fabricated source details
  - advice/execution language
- [ ] Define defaults:
  - style: existing Agent Adda style unless user sets `/style codex`
  - steps: `auto`
  - verbosity: `normal`
  - verification footer: enabled for generated artifacts and composite workflows

**Acceptance Criteria:**
- Spec has no `TODO`, `TBD`, or ambiguous defaults.
- Spec includes example output for `/screen quality-breakouts --explain --tv`.
- Spec states that LLM narration is optional and downstream of deterministic evidence.

**Verification:**

```bash
rg -n "TODO|TBD|chain.of.thought|investment advice" docs/superpowers/specs/2026-06-04-agent-adda-copilot-superpowers-design.md
```

Expected: only intentional guardrail references, no unfinished placeholders.

---

## Epic AA-COP-1: Interaction Profiles

### AA-COP-1.1 Add Interaction Profile Model

**Status:** READY  
**Priority:** P0  
**Suggested owner:** Interaction profile assistant  
**Dependencies:** AA-COP-0.1  
**Files:**
- Create: `terminal/interaction_profile.py`
- Test: `tests/test_interaction_profile.py`

**Work:**
- [ ] Create dataclasses or TypedDicts for:
  - `InteractionProfile`
  - `StepVisibility`
  - `VerbosityLevel`
  - `ToneStyle`
- [ ] Support styles:
  - `default`
  - `codex`
  - `institutional`
  - `teacher`
  - `trader`
- [ ] Support verbosity:
  - `concise`
  - `normal`
  - `deep`
- [ ] Support steps:
  - `off`
  - `auto`
  - `on`
- [ ] Add pure functions:
  - `default_profile()`
  - `profile_for_style(style: str)`
  - `merge_profile(base, overrides)`
  - `should_show_steps(profile, workflow_kind)`

**Acceptance Criteria:**
- Unknown styles fail closed to `default` with a warning object, not an exception.
- `codex` profile enables concise step updates, assumptions, verification, and next actions.
- No runtime dependency on OpenAI or terminal Rich rendering.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_interaction_profile.py -q
```

### AA-COP-1.2 Persist Session Interaction Preferences

**Status:** READY  
**Priority:** P0  
**Suggested owner:** Session state assistant  
**Dependencies:** AA-COP-1.1  
**Files:**
- Create: `terminal/session_preferences.py`
- Modify: `nse_agent.py`
- Test: `tests/test_session_preferences.py`

**Work:**
- [ ] Store preferences in a small JSON file under a project-local or user-local Agent Adda state path.
- [ ] Persist:
  - style
  - verbosity
  - steps
  - verification
- [ ] Add load/save functions with corrupted-file recovery.
- [ ] Keep preferences optional; Agent Adda must run if the preference file is missing.

**Acceptance Criteria:**
- Preferences survive a new Python process.
- Corrupted JSON is renamed or ignored with a clear warning and default profile.
- No credentials or sensitive data are stored.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_session_preferences.py -q
```

### AA-COP-1.3 Add `/style`, `/verbosity`, And `/steps` Commands

**Status:** READY  
**Priority:** P0  
**Suggested owner:** Command surface assistant  
**Dependencies:** AA-COP-1.1, AA-COP-1.2  
**Files:**
- Modify: `nse_agent.py`
- Modify: `terminal/help.py`
- Test: `tests/test_nse_agent_interaction_commands.py`

**Work:**
- [ ] Add commands:
  - `/style`
  - `/style codex`
  - `/verbosity`
  - `/verbosity concise|normal|deep`
  - `/steps`
  - `/steps on|off|auto`
- [ ] Show current preference when called without args.
- [ ] Validate unknown values and print valid options.
- [ ] Update help and command catalog.

**Acceptance Criteria:**
- Commands are handled before general LLM routing.
- Preferences are persisted.
- Help includes examples.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_nse_agent_interaction_commands.py tests/run_help_catalog_smoke.py -q
```

---

## Epic AA-COP-2: Execution Trail System

### AA-COP-2.1 Define Step Event Contract

**Status:** READY  
**Priority:** P0  
**Suggested owner:** Execution trace assistant  
**Dependencies:** AA-COP-0.1  
**Files:**
- Create: `terminal/execution_trace.py`
- Test: `tests/test_execution_trace.py`

**Work:**
- [ ] Define event types:
  - `workflow_started`
  - `step_started`
  - `tool_started`
  - `tool_succeeded`
  - `tool_failed`
  - `filter_applied`
  - `artifact_written`
  - `verification`
  - `workflow_completed`
- [ ] Define `ExecutionTrace` container with:
  - workflow id
  - command/query
  - profile snapshot
  - started_at/completed_at
  - events list
  - source trail
- [ ] Add helper methods:
  - `add_step`
  - `add_tool_result`
  - `add_filter_count`
  - `add_artifact`
  - `add_verification`
  - `summary_counts`

**Acceptance Criteria:**
- Events serialize to JSON.
- Tool failures are represented as data, not raised by the trace layer.
- Trace supports both concise and expanded rendering.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_execution_trace.py -q
```

### AA-COP-2.2 Add Rich Renderer For Execution Trails

**Status:** READY  
**Priority:** P0  
**Suggested owner:** Renderer assistant  
**Dependencies:** AA-COP-2.1, AA-COP-1.1  
**Files:**
- Create: `terminal/renderers/execution_trace.py`
- Modify: `terminal/renderers/__init__.py` if needed
- Test: `tests/test_execution_trace_renderer.py`

**Work:**
- [ ] Render concise trace:
  - one line per major step
  - counts
  - failures
  - artifact paths
- [ ] Render expanded trace:
  - step rationale
  - tool name
  - key args
  - row counts
  - filter pass/fail counts
- [ ] Render verification footer.
- [ ] Avoid showing raw hidden reasoning.

**Acceptance Criteria:**
- Snapshot-style tests prove key labels render.
- Empty trace renders a useful fallback.
- Failure trace visibly shows error and next action.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_execution_trace_renderer.py -q
```

### AA-COP-2.3 Wire Trace To Direct Slash Commands

**Status:** READY  
**Priority:** P1  
**Suggested owner:** Terminal integration assistant  
**Dependencies:** AA-COP-2.1, AA-COP-2.2, AA-COP-1.3  
**Files:**
- Modify: `nse_agent.py`
- Test: `tests/test_nse_agent_trace_integration.py`

**Work:**
- [ ] Add trace creation for direct deterministic commands where useful:
  - `/screen`
  - `/scan`
  - `/research`
  - `/analyze`
  - `/report`
- [ ] Start with `/screen` only if scope needs to be reduced.
- [ ] Respect `/steps off|auto|on`.

**Acceptance Criteria:**
- `/steps on` visibly prints trace for `/screen stage2`.
- `/steps off` preserves existing terse behavior.
- Existing command outputs still render the core result.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_nse_agent_trace_integration.py -q
```

---

## Epic AA-COP-3: First Composite Screener - Quality Breakouts

### AA-COP-3.1 Add Composite Screener Tool

**Status:** READY  
**Priority:** P0  
**Suggested owner:** Screener assistant  
**Dependencies:** AA-COP-2.1 recommended, but can start with pure function tests  
**Files:**
- Create: `terminal/composite_screeners.py`
- Modify: `terminal/tools.py`
- Test: `tests/test_composite_screeners.py`

**Work:**
- [ ] Implement `run_quality_breakout_screener(top_n=15, mode="balanced")`.
- [ ] Candidate sources:
  - `new_highs`
  - `momentum_52w`
  - `tight_range`
  - `breakouts`
- [ ] Merge and deduplicate symbols.
- [ ] Enrich from `scores.stage_snapshots`:
  - company_name
  - sector
  - price
  - stage
  - trading_signal
  - relative_strength
  - rsi
  - technical_score
  - investment_score
  - enhanced_fund_score
  - earnings_quality
  - sales_growth
  - financial_strength
  - institutional_backing
- [ ] Add setup tags:
  - `new_high`
  - `momentum_52w`
  - `vcp_like`
  - `breakout`
- [ ] Add quality modes:
  - `strict`: enhanced_fund_score >= 70 or investment_score >= 65
  - `balanced`: enhanced_fund_score >= 60 or investment_score >= 60
  - `broad`: no hard quality filter, but weak fundamentals are flagged
- [ ] Rank by composite score:
  - setup confluence
  - Stage 2
  - BUY/STRONG_BUY
  - RS strength
  - RSI quality band
  - technical_score
  - enhanced_fund_score
  - investment_score
  - financial_strength
- [ ] Return structured payload with:
  - snapshot_date
  - source_counts
  - merged_count
  - passed_count
  - results
  - tradingview_symbols
  - source_trail

**Acceptance Criteria:**
- Function does not call an LLM.
- Missing fundamentals do not crash the scan.
- Each result has `reason_tags`, `risk_flags`, and `tradingview_symbol`.
- PostgreSQL is the source of truth; SQLite fallback is optional and explicit.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_composite_screeners.py -q
```

### AA-COP-3.2 Wire `/screen quality-breakouts`

**Status:** READY  
**Priority:** P0  
**Suggested owner:** Command surface assistant  
**Dependencies:** AA-COP-3.1  
**Files:**
- Modify: `nse_agent.py`
- Modify: `terminal/help.py`
- Test: `tests/test_nse_agent_quality_breakouts_command.py`

**Work:**
- [ ] Add aliases:
  - `/screen quality-breakouts`
  - `/screen qb`
  - `/screen leaders`
  - `/screen vcp-breakouts`
- [ ] Add flags:
  - `--strict`
  - `--balanced`
  - `--broad`
  - `--top N`
  - `--explain`
  - `--tv`
  - `--report` (can be stubbed as not implemented if deferred)
- [ ] Render normal table by default.
- [ ] Render copy-friendly TradingView list with `--tv`.
- [ ] Render execution trail and reason details with `--explain`.

**Acceptance Criteria:**
- Command is handled before generic LLM routing.
- `--tv` can be copied directly into TradingView.
- `--explain` shows source counts, merge counts, quality filter counts, and reason tags.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_nse_agent_quality_breakouts_command.py tests/run_help_catalog_smoke.py -q
```

### AA-COP-3.3 Add Natural Language Routing

**Status:** READY  
**Priority:** P1  
**Suggested owner:** Router assistant  
**Dependencies:** AA-COP-3.1  
**Files:**
- Modify: `terminal/agent.py`
- Modify: `terminal/router/providers.py` if provider routing needs a dedicated provider
- Test: `tests/test_quality_breakouts_routing.py`

**Work:**
- [ ] Route these patterns to the composite screener:
  - `stocks creating new highs or VCP or breakouts with good fundamentals`
  - `quality breakout candidates`
  - `new highs with good fundamentals`
  - `VCP stocks with good fundamentals`
  - `breakouts with fundamental quality`
- [ ] Avoid hijacking single-stock research prompts.
- [ ] Keep deterministic path; do not ask the LLM to invent candidates.

**Acceptance Criteria:**
- Query routes to `run_quality_breakout_screener`.
- Single stock queries like `RELIANCE breakout` still route to stock/intraday setup as before.
- Tests cover mixed-case and typo-tolerant phrases where reasonable.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_quality_breakouts_routing.py tests/test_terminal_agent_market_prompt.py tests/test_unified_router.py -q
```

### AA-COP-3.4 Add Optional HTML/Markdown Report

**Status:** READY  
**Priority:** P2  
**Suggested owner:** Report assistant  
**Dependencies:** AA-COP-3.1, AA-COP-3.2  
**Files:**
- Create: `terminal/reports/quality_breakouts.py` or focused equivalent
- Modify: `terminal/reports.py` only if project pattern requires it
- Test: `tests/test_quality_breakouts_report.py`

**Work:**
- [ ] Render:
  - methodology
  - data freshness
  - source counts
  - filter waterfall
  - ranked candidates
  - reason tags
  - risk flags
  - TradingView export block
  - verification footer
- [ ] Save under `reports/screeners/`.
- [ ] Update `reports/latest/quality_breakouts.html` and `.md`.

**Acceptance Criteria:**
- Report is self-contained.
- Links and tables render with non-empty data when candidates exist.
- Missing fundamentals show as missing, not blank conclusions.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_quality_breakouts_report.py -q
```

---

## Epic AA-COP-4: Market-Native Superpower Commands

### AA-COP-4.1 Add `/brainstorm` Command

**Status:** READY  
**Priority:** P1  
**Suggested owner:** Superpower command assistant  
**Dependencies:** AA-COP-1.3  
**Files:**
- Create: `terminal/copilot_workflows/brainstorm.py`
- Modify: `nse_agent.py`
- Modify: `terminal/help.py`
- Test: `tests/test_copilot_brainstorm_command.py`

**Work:**
- [ ] Implement `/brainstorm <topic>`.
- [ ] Purpose: structure design discussion before implementation or strategy changes.
- [ ] Output:
  - understood topic
  - known context
  - assumptions
  - 2-3 approaches
  - recommendation
  - approval gate
- [ ] Use LLM optionally for wording, but deterministic skeleton must exist.

**Acceptance Criteria:**
- `/brainstorm portfolio strategy lab` does not immediately run tools or modify files.
- Output asks for approval before implementation.
- Works without LLM by producing a deterministic scaffold.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_copilot_brainstorm_command.py -q
```

### AA-COP-4.2 Add `/plan` Command

**Status:** READY  
**Priority:** P1  
**Suggested owner:** Planning workflow assistant  
**Dependencies:** AA-COP-4.1  
**Files:**
- Create: `terminal/copilot_workflows/plan.py`
- Modify: `nse_agent.py`
- Modify: `terminal/help.py`
- Test: `tests/test_copilot_plan_command.py`

**Work:**
- [ ] Implement `/plan <objective>`.
- [ ] Output implementation-ready task list:
  - files to inspect
  - files to modify/create
  - tests to add
  - verification commands
  - risk/rollback notes
- [ ] Add option `--write` to save a plan under `docs/superpowers/plans/`; default should not write files.

**Acceptance Criteria:**
- `/plan` produces a plan without executing it.
- `--write` writes one deterministic markdown file.
- Existing docs are not overwritten without explicit flag.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_copilot_plan_command.py -q
```

### AA-COP-4.3 Add `/debug` Command

**Status:** READY  
**Priority:** P1  
**Suggested owner:** Debug workflow assistant  
**Dependencies:** AA-COP-2.1  
**Files:**
- Create: `terminal/copilot_workflows/debug.py`
- Modify: `nse_agent.py`
- Modify: `terminal/help.py`
- Test: `tests/test_copilot_debug_command.py`

**Work:**
- [ ] Implement `/debug <issue>`.
- [ ] For report/link/data issues, create a deterministic investigation plan:
  - reproduce
  - inspect artifacts
  - inspect data source
  - isolate root cause
  - propose fix
  - verify
- [ ] Do not modify files by default.
- [ ] Add future-compatible `--apply` flag but keep it disabled unless explicitly implemented.

**Acceptance Criteria:**
- `/debug results_analysis links not working` produces a focused report debugging plan.
- It lists candidate files and commands.
- It does not claim a fix without running verification.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_copilot_debug_command.py -q
```

### AA-COP-4.4 Add `/review` Command

**Status:** READY  
**Priority:** P1  
**Suggested owner:** Review workflow assistant  
**Dependencies:** AA-COP-2.1  
**Files:**
- Create: `terminal/copilot_workflows/review.py`
- Modify: `nse_agent.py`
- Modify: `terminal/help.py`
- Test: `tests/test_copilot_review_command.py`

**Work:**
- [ ] Implement `/review <report|portfolio|strategy|symbol>`.
- [ ] Review stance:
  - findings first
  - evidence gaps
  - unsupported claims
  - data freshness
  - risks
  - suggested next checks
- [ ] For local report paths, load and inspect the artifact where safe.

**Acceptance Criteria:**
- Review does not summarize before findings.
- Missing data and unsupported claims are called out.
- Works for latest report references once AA-COP-5 exists; before that, direct file path is enough.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_copilot_review_command.py -q
```

### AA-COP-4.5 Add `/verify` Command

**Status:** READY  
**Priority:** P1  
**Suggested owner:** Verification workflow assistant  
**Dependencies:** AA-COP-2.1  
**Files:**
- Create: `terminal/copilot_workflows/verify.py`
- Modify: `nse_agent.py`
- Modify: `terminal/help.py`
- Test: `tests/test_copilot_verify_command.py`

**Work:**
- [ ] Implement `/verify <target>`.
- [ ] Initial targets:
  - `reports`
  - `data`
  - `screen quality-breakouts`
  - `portfolio`
- [ ] Output:
  - checks run
  - pass/fail/warn
  - artifact paths
  - next action

**Acceptance Criteria:**
- `/verify reports` can run without LLM.
- Failures are actionable.
- No false "complete" claim when checks fail.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_copilot_verify_command.py -q
```

---

## Epic AA-COP-5: Task Memory And Status

### AA-COP-5.1 Add Task Memory Store

**Status:** READY  
**Priority:** P1  
**Suggested owner:** Memory assistant  
**Dependencies:** AA-COP-1.2  
**Files:**
- Create: `terminal/task_memory.py`
- Test: `tests/test_task_memory.py`

**Work:**
- [ ] Persist:
  - current objective
  - recent commands
  - recent artifacts
  - open issues
  - latest screener exports
  - latest reports
- [ ] Store as JSON with schema version.
- [ ] Add safe recovery for corrupted state.
- [ ] Keep memory local and non-sensitive.

**Acceptance Criteria:**
- Memory can be updated by workflows without importing Rich or LLM clients.
- State survives process restart.
- Missing file returns empty memory.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_task_memory.py -q
```

### AA-COP-5.2 Add `/status`

**Status:** READY  
**Priority:** P1  
**Suggested owner:** Status command assistant  
**Dependencies:** AA-COP-5.1  
**Files:**
- Modify: `nse_agent.py`
- Modify: `terminal/help.py`
- Test: `tests/test_status_command.py`

**Work:**
- [ ] Implement `/status`.
- [ ] Show:
  - current objective
  - latest data snapshot
  - latest generated reports
  - latest quality-breakouts watchlist
  - open issues
  - next useful commands
- [ ] Add `/status clear` with confirmation text or safe explicit behavior.

**Acceptance Criteria:**
- `/status` never calls LLM.
- Empty status prints useful startup instructions.
- After a quality-breakouts run, status includes the watchlist artifact or latest symbols.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_status_command.py -q
```

---

## Epic AA-COP-6: Workflow Planner Objects

### AA-COP-6.1 Define Workflow Plan Contract

**Status:** READY  
**Priority:** P1  
**Suggested owner:** Workflow architecture assistant  
**Dependencies:** AA-COP-2.1  
**Files:**
- Create: `terminal/workflow_plan.py`
- Test: `tests/test_workflow_plan.py`

**Work:**
- [ ] Define:
  - `WorkflowPlan`
  - `WorkflowStep`
  - `ToolCallSpec`
  - `WorkflowResult`
- [ ] Support deterministic plan preview before execution.
- [ ] Support execution trace integration.
- [ ] Keep it generic enough for:
  - screeners
  - RIC
  - research
  - portfolio lab
  - report verification

**Acceptance Criteria:**
- Plans serialize to JSON.
- Plan has a stable `workflow_kind`.
- Failed steps can be represented without aborting the whole workflow unless marked required.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_workflow_plan.py -q
```

### AA-COP-6.2 Adopt Workflow Plan For Quality Breakouts

**Status:** READY  
**Priority:** P1  
**Suggested owner:** Composite screener integration assistant  
**Dependencies:** AA-COP-3.1, AA-COP-6.1  
**Files:**
- Modify: `terminal/composite_screeners.py`
- Test: `tests/test_quality_breakouts_workflow_plan.py`

**Work:**
- [ ] Express quality-breakouts as a workflow plan:
  - run new_highs
  - run momentum_52w
  - run tight_range
  - run breakouts
  - merge
  - quality filter
  - rank
  - TradingView export
- [ ] Emit trace events from each step.

**Acceptance Criteria:**
- `--explain` output is generated from plan/trace data, not hand-written duplicate strings.
- Tests prove counts match the returned payload.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_quality_breakouts_workflow_plan.py tests/test_composite_screeners.py -q
```

---

## Epic AA-COP-7: Report And Link Verification

### AA-COP-7.1 Implement Report Link Validator

**Status:** READY  
**Priority:** P1  
**Suggested owner:** Report validation assistant  
**Dependencies:** AA-COP-4.5 optional  
**Files:**
- Create or extend: `terminal/report_validation.py`
- Test: `tests/test_report_validation_links.py`

**Work:**
- [ ] Validate a local HTML report:
  - internal file links exist
  - linked HTML files have non-empty core content
  - anchor references resolve where feasible
  - stock detail pages contain expected data table or narrative markers
- [ ] Return structured checks.
- [ ] Do not mutate the report.

**Acceptance Criteria:**
- Can validate `reports/latest/results_analysis.html`.
- Broken links are reported with source href and resolved path.
- Empty stock pages are reported separately from missing files.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_report_validation_links.py -q
```

### AA-COP-7.2 Wire `/verify reports`

**Status:** READY  
**Priority:** P1  
**Suggested owner:** Verification integration assistant  
**Dependencies:** AA-COP-7.1, AA-COP-4.5  
**Files:**
- Modify: `terminal/copilot_workflows/verify.py`
- Modify: `nse_agent.py`
- Test: `tests/test_verify_reports_command.py`

**Work:**
- [ ] `/verify reports` validates:
  - `reports/latest/results_analysis.html`
  - `reports/latest/stage2_tracker.html`
  - `reports/latest/top_picks.html`
  - configurable latest report list
- [ ] Print concise status table.
- [ ] Optionally write `reports/latest/report_validation.md`.

**Acceptance Criteria:**
- Command finds broken links without traceback.
- Report path is printed when validation markdown is written.
- Task memory records the validation artifact if AA-COP-5 is present.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_verify_reports_command.py tests/test_report_validation_links.py -q
```

---

## Epic AA-COP-8: Portfolio Copilot Behavior

### AA-COP-8.1 Add Portfolio-Aware Action Rationale Contract

**Status:** READY  
**Priority:** P2  
**Suggested owner:** Portfolio copilot assistant  
**Dependencies:** Existing portfolio-aware strategy lab, AA-COP-2.1  
**Files:**
- Modify: `portfolio/engine/strategy_schema.py`
- Modify: `portfolio/agents/report_agent.py`
- Test: `tests/portfolio/test_action_rationale_contract.py`

**Work:**
- [ ] Ensure every portfolio action can carry:
  - action: add/reduce/hold/avoid/watch
  - current weight
  - target weight
  - sector exposure
  - risk budget impact
  - reason tags
  - invalidation
  - staged action note
- [ ] Keep this as data, not prose-only.

**Acceptance Criteria:**
- Report renderer can show why an action was chosen.
- Missing current holdings prevent add/reduce claims and become warnings.

**Verification:**

```bash
.venv/bin/python -m pytest tests/portfolio/test_action_rationale_contract.py -q
```

### AA-COP-8.2 Add Portfolio Strategy Execution Trail

**Status:** READY  
**Priority:** P2  
**Suggested owner:** Portfolio integration assistant  
**Dependencies:** AA-COP-2.1, AA-COP-8.1  
**Files:**
- Modify: `portfolio/cli.py`
- Modify: `portfolio/engine/`
- Test: `tests/portfolio/test_strategy_lab_trace.py`

**Work:**
- [ ] Emit trace events for:
  - load capital/risk config
  - load current holdings
  - load target exposure rules
  - generate candidates
  - compare current vs target
  - propose staged actions
  - verify report artifacts
- [ ] Surface the trail in CLI output and HTML/Markdown reports.

**Acceptance Criteria:**
- Portfolio lab explains add/reduce/hold decisions using current state.
- No action is presented without exposure/risk context.

**Verification:**

```bash
.venv/bin/python -m pytest tests/portfolio/test_strategy_lab_trace.py tests/portfolio -q
```

---

## Epic AA-COP-9: Prompt And Persona Harness

### AA-COP-9.1 Add Prompt Fragments For Agent Adda Copilot Modes

**Status:** READY  
**Priority:** P2  
**Suggested owner:** Prompt harness assistant  
**Dependencies:** AA-COP-1.1  
**Files:**
- Create: `terminal/prompt_profiles.py`
- Modify: `terminal/agent.py`
- Test: `tests/test_prompt_profiles.py`

**Work:**
- [ ] Create prompt fragments for:
  - `codex`
  - `institutional`
  - `teacher`
  - `trader`
- [ ] Fragments should adjust style only, not data claims.
- [ ] Add explicit rules:
  - show assumptions
  - do not fabricate evidence
  - cite source trail from tools
  - keep research-only language
  - separate result from verification
- [ ] Make prompt assembly deterministic and testable.

**Acceptance Criteria:**
- Prompt fragments can be unit-tested without invoking LLM.
- `codex` style uses direct, concise, evidence-first communication.
- Profile changes do not change the tool plan by themselves.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_prompt_profiles.py tests/test_terminal_agent_market_prompt.py -q
```

---

## Epic AA-COP-10: Help, Autocomplete, And Documentation

### AA-COP-10.1 Update Help And Command Catalog

**Status:** READY  
**Priority:** P0 when any command is implemented  
**Suggested owner:** Help surface assistant  
**Dependencies:** Any command task  
**Files:**
- Modify: `terminal/help.py`
- Modify: `nse_agent.py`
- Modify: `docs/AGENT_ADDA_HELPFILE.md` if generated manually in this repo
- Test: `tests/run_help_catalog_smoke.py`

**Work:**
- [ ] Add help entries for:
  - `/style`
  - `/verbosity`
  - `/steps`
  - `/screen quality-breakouts`
  - `/brainstorm`
  - `/plan`
  - `/debug`
  - `/verify`
  - `/review`
  - `/status`
- [ ] Add examples and aliases.
- [ ] Keep generated help and runtime help aligned.

**Acceptance Criteria:**
- `/help` and `/commands quality` surface the new capability.
- Existing help smoke passes.

**Verification:**

```bash
.venv/bin/python -m pytest tests/run_help_catalog_smoke.py -q
```

---

## Recommended Implementation Sequence

### Slice 1: Visible Interaction Foundation

Implement:
- AA-COP-1.1
- AA-COP-1.2
- AA-COP-1.3
- AA-COP-2.1
- AA-COP-2.2
- AA-COP-10.1 for these commands

Exit criteria:

```bash
.venv/bin/python -m pytest tests/test_interaction_profile.py tests/test_session_preferences.py tests/test_nse_agent_interaction_commands.py tests/test_execution_trace.py tests/test_execution_trace_renderer.py tests/run_help_catalog_smoke.py -q
```

### Slice 2: Quality Breakout First-Class Capability

Implement:
- AA-COP-3.1
- AA-COP-3.2
- AA-COP-3.3
- AA-COP-10.1 for `/screen quality-breakouts`

Exit criteria:

```bash
.venv/bin/python -m pytest tests/test_composite_screeners.py tests/test_nse_agent_quality_breakouts_command.py tests/test_quality_breakouts_routing.py tests/test_terminal_agent_market_prompt.py tests/test_unified_router.py tests/run_help_catalog_smoke.py -q
```

Manual smoke:

```bash
.venv/bin/python nse_agent.py --no-briefing --skip-readiness --query "/screen quality-breakouts --explain --tv"
```

Expected:
- source counts are visible
- merged/pass counts are visible
- ranked candidates render
- TradingView list is copy-friendly
- no LLM fabrication required

### Slice 3: Copilot Commands MVP

Implement:
- AA-COP-4.1
- AA-COP-4.2
- AA-COP-4.3
- AA-COP-4.4
- AA-COP-4.5
- AA-COP-10.1 for these commands

Exit criteria:

```bash
.venv/bin/python -m pytest tests/test_copilot_brainstorm_command.py tests/test_copilot_plan_command.py tests/test_copilot_debug_command.py tests/test_copilot_review_command.py tests/test_copilot_verify_command.py tests/run_help_catalog_smoke.py -q
```

### Slice 4: Memory And Verification

Implement:
- AA-COP-5.1
- AA-COP-5.2
- AA-COP-7.1
- AA-COP-7.2

Exit criteria:

```bash
.venv/bin/python -m pytest tests/test_task_memory.py tests/test_status_command.py tests/test_report_validation_links.py tests/test_verify_reports_command.py -q
```

### Slice 5: Workflow Plan Adoption

Implement:
- AA-COP-6.1
- AA-COP-6.2

Exit criteria:

```bash
.venv/bin/python -m pytest tests/test_workflow_plan.py tests/test_quality_breakouts_workflow_plan.py tests/test_composite_screeners.py -q
```

### Slice 6: Portfolio Copilot Trace

Implement:
- AA-COP-8.1
- AA-COP-8.2

Exit criteria:

```bash
.venv/bin/python -m pytest tests/portfolio/test_action_rationale_contract.py tests/portfolio/test_strategy_lab_trace.py tests/portfolio -q
```

---

## MVP Definition

The first useful MVP is complete when:

- `/style codex` works and persists.
- `/steps on|off|auto` works and persists.
- `/screen quality-breakouts --explain --tv` runs deterministically.
- Natural language "stocks creating new highs or VCP or breakouts with good fundamentals" routes to the composite screener.
- Output shows source counts, merge counts, quality filter counts, reason tags, risk flags, and TradingView symbols.
- `/status` can show the latest watchlist or clearly say none exists.
- Verification commands pass.

MVP verification:

```bash
.venv/bin/python -m pytest \
  tests/test_interaction_profile.py \
  tests/test_session_preferences.py \
  tests/test_nse_agent_interaction_commands.py \
  tests/test_execution_trace.py \
  tests/test_execution_trace_renderer.py \
  tests/test_composite_screeners.py \
  tests/test_nse_agent_quality_breakouts_command.py \
  tests/test_quality_breakouts_routing.py \
  tests/test_terminal_agent_market_prompt.py \
  tests/test_unified_router.py \
  tests/run_help_catalog_smoke.py \
  -q

.venv/bin/python nse_agent.py --no-briefing --skip-readiness --query "/screen quality-breakouts --explain --tv"
```

