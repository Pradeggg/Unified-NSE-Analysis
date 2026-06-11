# NSE Agent Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce `nse_agent.py` from a monolithic terminal application into a thin compatibility entrypoint while preserving all current Agent Adda behavior.

**Architecture:** Refactor by extraction, not rewrite. First lock behavior with command inventory and smoke tests, then move pure UI helpers, prompt/session code, command dispatch, dashboards, and workflow families into focused modules. Keep `nse_agent.py` compatibility wrappers until tests and terminal smokes prove each move.

**Tech Stack:** Python 3.13, pytest, Rich, PromptToolkit, existing Agent Adda terminal modules.

---

## Status

- [x] AA-AR-13 first slice: command inventory created at `docs/refactor/nse_agent_command_inventory.md`.
- [x] AA-AR-13 first slice: `CommandRegistry.snapshot()` added and covered by `tests/test_command_registry_inventory.py`.
- [x] AA-AR-14 first slice: link helpers extracted to `terminal/ui/links.py`.
- [x] AA-AR-14 first slice: link-helper tests added at `tests/test_terminal_ui_links.py`.
- [ ] Remaining AA-AR-13: expand smoke tests for startup readiness, report open/export, dashboard, and paper-trading/backtest.
- [ ] Remaining AA-AR-14: extract Markdown subclass, Rich table rendering, `_print_response`, source/footer rendering, and console setup.
- [ ] AA-AR-15: extract prompt session, completer, toolbar, and UI preferences.
- [ ] AA-AR-16: convert remaining interactive slash branches to registry-backed dispatch.
- [ ] AA-AR-17: extract market dashboard runtime.
- [ ] AA-AR-18: extract report, scan, monitor, and RIC workflow modules.
- [ ] AA-AR-19: thin `nse_agent.py` to an entrypoint shim.
- [ ] AA-AR-20: split `terminal/agent.py` pipeline internals after CLI shell is stable.

---

### Task 1: Complete Refactor Safety Harness

**Files:**
- Modify: `tests/test_command_registry_inventory.py`
- Modify: `tests/test_nse_agent_interaction_commands.py`
- Modify: `tests/test_nse_agent_monitor_scan.py`
- Create or modify: `tests/test_nse_agent_refactor_smoke.py`
- Modify: `docs/refactor/nse_agent_command_inventory.md`

- [ ] **Step 1: Add smoke tests for high-risk commands**

Add tests or subprocess smokes for:

```bash
.venv/bin/python nse_agent.py --no-briefing --skip-readiness -q "/help"
.venv/bin/python nse_agent.py --no-briefing --skip-readiness -q "/commands report"
.venv/bin/python nse_agent.py --no-briefing --skip-readiness -q "how does NIFTY500 look like"
.venv/bin/python nse_agent.py --no-briefing --skip-readiness -q "/data-coverage"
.venv/bin/python nse_agent.py --no-briefing --skip-readiness -q "/backtest list"
```

- [ ] **Step 2: Run safety harness**

Run:

```bash
.venv/bin/python -m pytest tests/test_command_registry_inventory.py tests/test_nse_agent_interaction_commands.py tests/test_nse_agent_monitor_scan.py tests/test_nse_agent_refactor_smoke.py -q
```

Expected: all tests pass before any further extraction.

---

### Task 2: Extract Markdown And Response Rendering

**Files:**
- Create: `terminal/ui/markdown.py`
- Create: `terminal/ui/response.py`
- Modify: `nse_agent.py`
- Modify: `tests/test_terminal_ui_links.py`
- Create or modify: `tests/test_terminal_ui_response.py`
- Modify: `tests/test_renderers.py`

- [ ] **Step 1: Write tests for Markdown file-link support**

Test that `terminal.ui.markdown.Markdown` preserves `file://` links and still renders standard Markdown tables.

- [ ] **Step 2: Move Markdown subclass**

Move the local `Markdown` subclass from `nse_agent.py` to `terminal/ui/markdown.py`.

Keep in `nse_agent.py`:

```python
from terminal.ui.markdown import Markdown
```

- [ ] **Step 3: Extract `_print_response` dependencies gradually**

Move pure helpers first:

- `_render_md_table_as_rich`
- `_print_md_with_rich_tables`
- `_normalise_plain_agent_brief`
- `_emphasize_symbols_outside_code`

Keep compatibility wrappers in `nse_agent.py` until callers are migrated.

- [ ] **Step 4: Verify response rendering**

Run:

```bash
.venv/bin/python -m pytest tests/test_renderers.py tests/test_terminal_renderer_guards.py tests/test_terminal_ui_links.py tests/test_terminal_ui_response.py -q
.venv/bin/python -m py_compile nse_agent.py terminal/ui/markdown.py terminal/ui/response.py
```

Expected: no output regression in renderer tests.

---

### Task 3: Extract Prompt Session And Completer

**Files:**
- Create: `terminal/ui/prompt.py`
- Create: `terminal/ui/toolbar.py`
- Modify: `nse_agent.py`
- Modify: `tests/test_nse_agent_interaction_commands.py`
- Create: `tests/test_terminal_ui_prompt.py`

- [ ] **Step 1: Test completer command coverage**

Assert common commands appear in completion candidates: `/help`, `/scan`, `/monitor`, `/report`, `/skills`, `/my-portfolio`.

- [ ] **Step 2: Move `_AgentCompleter` and prompt style constants**

Move completer and prompt styling to `terminal/ui/prompt.py`.

- [ ] **Step 3: Move toolbar rendering helpers**

Move session clock/toolbar rendering to `terminal/ui/toolbar.py` where possible.

- [ ] **Step 4: Verify interactive-adjacent tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_terminal_ui_prompt.py tests/test_nse_agent_interaction_commands.py -q
.venv/bin/python -m py_compile nse_agent.py terminal/ui/prompt.py terminal/ui/toolbar.py
```

Expected: completion and interaction profile behavior unchanged.

---

### Task 4: Registry-Back Remaining Slash Commands

**Files:**
- Create: `terminal/commands/dispatcher.py`
- Create: `terminal/commands/session.py`
- Create: `terminal/commands/reports.py`
- Create: `terminal/commands/monitor.py`
- Create: `terminal/commands/screeners.py`
- Modify: `nse_agent.py`
- Modify: `terminal/command_registry.py`
- Modify: `tests/test_command_registry_inventory.py`
- Modify: `tests/test_nse_agent_monitor_scan.py`

- [ ] **Step 1: Add inventory tests for interactive-only branches**

Lock the command families listed in `docs/refactor/nse_agent_command_inventory.md`.

- [ ] **Step 2: Add dispatcher without moving handlers**

Create `terminal/commands/dispatcher.py` that delegates to the existing shared `CommandRegistry`.

- [ ] **Step 3: Register one low-risk family**

Move help/session commands first. Keep wrappers in `nse_agent.py`.

- [ ] **Step 4: Move scan and monitor after tests pass**

Move command-family parsing and rendering one family at a time.

- [ ] **Step 5: Verify each family before moving the next**

Run after each family:

```bash
.venv/bin/python -m pytest tests/test_command_registry_inventory.py tests/test_nse_agent_monitor_scan.py tests/test_nse_agent_interaction_commands.py -q
.venv/bin/python nse_agent.py --no-briefing --skip-readiness -q "/help"
.venv/bin/python nse_agent.py --no-briefing --skip-readiness -q "/commands monitor"
```

Expected: command output remains available and no slash command falls into the LLM path unexpectedly.

---

### Task 5: Extract Dashboard Runtime

**Files:**
- Create: `terminal/dashboard/data.py`
- Create: `terminal/dashboard/render.py`
- Create: `terminal/dashboard/live.py`
- Create: `terminal/dashboard/html.py`
- Modify: `nse_agent.py`
- Create or modify: `tests/test_dashboard_runtime.py`

- [ ] **Step 1: Test dashboard HTML generation from fixture snapshot**

Assert generated HTML contains core dashboard sections and source freshness.

- [ ] **Step 2: Move HTML renderer**

Move `_render_market_dashboard_html` to `terminal/dashboard/html.py`.

- [ ] **Step 3: Move live runtime**

Move `_run_market_dashboard_live` and supporting fetch/render functions.

- [ ] **Step 4: Verify dashboard commands**

Run:

```bash
.venv/bin/python -m pytest tests/test_dashboard_runtime.py tests/test_renderers.py -q
.venv/bin/python -m py_compile nse_agent.py terminal/dashboard/data.py terminal/dashboard/render.py terminal/dashboard/live.py terminal/dashboard/html.py
```

Expected: dashboard module can be tested without entering `_chat_loop`.

---

### Task 6: Thin `nse_agent.py`

**Files:**
- Modify: `agent_adda/cli.py`
- Create: `agent_adda/app.py`
- Modify: `nse_agent.py`
- Modify: `tests/test_nse_agent_interaction_commands.py`
- Modify: `tests/test_ric_company_xray.py`

- [ ] **Step 1: Move app lifecycle to `agent_adda/app.py`**

Move startup readiness, briefing, single-query execution, and chat-loop orchestration behind explicit app functions.

- [ ] **Step 2: Keep `nse_agent.py` as compatibility entrypoint**

Target shape:

```python
#!/usr/bin/env python3
from agent_adda.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Verify CLI behavior**

Run:

```bash
.venv/bin/python nse_agent.py --no-briefing --skip-readiness -q "/help"
.venv/bin/python nse_agent.py --no-briefing --skip-readiness -q "how does NIFTY500 look like"
.venv/bin/python -m pytest tests/test_nse_agent_interaction_commands.py tests/test_ric_company_xray.py tests/test_terminal_agent_market_prompt.py -q
```

Expected: `python nse_agent.py ...` remains supported, and `nse_agent.py` is under 200 lines.

---

### Task 7: Split Agent Pipeline Internals

**Files:**
- Create: `terminal/pipeline/context.py`
- Create: `terminal/pipeline/clarification.py`
- Create: `terminal/pipeline/router_stage.py`
- Create: `terminal/pipeline/entity_topic.py`
- Create: `terminal/pipeline/situation.py`
- Create: `terminal/pipeline/semantic_intent.py`
- Create: `terminal/pipeline/synthesis.py`
- Modify: `terminal/agent.py`
- Modify: `tests/test_terminal_agent_market_prompt.py`
- Modify: `tests/test_semantic_intent.py`
- Modify: `tests/test_skill_store_runtime_assessment.py`

- [ ] **Step 1: Preserve AA-AR-2 stage order**

Keep the current named stage order:

```text
clarification binding
unified router
entity/topic assessment
situation assessment
semantic/LLM intent
keyword safe fallback
```

- [ ] **Step 2: Move one stage per commit**

Move one stage into `terminal/pipeline/` and run tests before moving the next.

- [ ] **Step 3: Verify final synthesis contract**

Confirm final synthesis still receives:

- expanded user query
- context
- tool results
- structured deterministic render
- backend information

- [ ] **Step 4: Verify agent pipeline**

Run:

```bash
.venv/bin/python -m pytest tests/test_terminal_agent_market_prompt.py tests/test_semantic_intent.py tests/test_skill_store_runtime_assessment.py tests/test_on_demand_stock_data.py -q
```

Expected: semantic/LLM intent remains first-class before keyword fallback.

