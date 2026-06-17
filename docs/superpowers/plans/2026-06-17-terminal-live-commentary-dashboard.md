# Terminal Live Commentary Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a terminal-only `/dashboard --live-commentary` mode that continuously tracks live market setups, detects meaningful changes, and renders model-style tracker commentary.

**Architecture:** Add a focused `terminal.live_dashboard` module for state, event detection, compact prompting, and Rich rendering. Keep `nse_agent.py` responsible for command parsing and dispatch only. Reuse existing tools such as `get_live_market_overview`, `get_top_gainers_losers`, `get_nse_quotes`, and `scan_symbols_intraday`.

**Tech Stack:** Python 3.13, Rich, existing Agent Adda tool registry, pytest, OpenAI-compatible backend interface.

---

### Task 1: Command Parsing

**Files:**
- Modify: `nse_agent.py`
- Test: `tests/test_command_dispatch.py`

- [ ] **Step 1: Write parser tests**

Add tests that call `nse_agent._parse_dashboard_command` with:

```python
parsed = nse_agent._parse_dashboard_command("/dashboard --live-commentary --symbols TRENT,DIXON --interval 30 --cycles 2 --no-llm")
assert parsed["live_commentary"] is True
assert parsed["symbols"] == ["TRENT", "DIXON"]
assert parsed["refresh_secs"] == 30
assert parsed["cycles"] == 2
assert parsed["use_llm"] is False
```

- [ ] **Step 2: Implement parsing**

Extend `_parse_dashboard_command` to return `live_commentary`, `symbols`, `refresh_secs`, `cycles`, and `use_llm`.

- [ ] **Step 3: Run parser tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_command_dispatch.py::TestCommandRegistry -q
```

Expected: PASS.

### Task 2: Live Dashboard State Module

**Files:**
- Create: `terminal/live_dashboard.py`
- Test: `tests/test_live_dashboard.py`

- [ ] **Step 1: Write state tests**

Tests verify:

- first cycle marks symbols as initialized
- second cycle emits a change event when status changes
- deterministic commentary contains `Current read from the tracker`
- stale freshness is surfaced in source health

- [ ] **Step 2: Implement dataclasses and state transition**

Create dataclasses:

```python
LiveDashboardConfig
TrackedSymbolState
LiveDashboardEvent
LiveDashboardState
```

Implement:

```python
build_tracked_symbol(...)
update_live_dashboard_state(...)
deterministic_commentary(...)
```

- [ ] **Step 3: Run state tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_live_dashboard.py -q
```

Expected: PASS.

### Task 3: Tool Collection and Rendering

**Files:**
- Modify: `terminal/live_dashboard.py`
- Test: `tests/test_live_dashboard.py`

- [ ] **Step 1: Write fetch/render tests with monkeypatched tools**

Use monkeypatches for `terminal.live_dashboard.get_live_market_overview`, `get_nse_quotes`, and `scan_symbols_intraday`.

- [ ] **Step 2: Implement bounded tool collector**

Implement:

```python
fetch_live_dashboard_cycle(config: LiveDashboardConfig) -> dict
render_live_dashboard(state: LiveDashboardState)
```

The collector must call bounded tools only and must capture errors into `source_health`.

- [ ] **Step 3: Run live dashboard tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_live_dashboard.py -q
```

Expected: PASS.

### Task 4: Model Commentary Loop

**Files:**
- Modify: `terminal/live_dashboard.py`
- Test: `tests/test_live_dashboard.py`

- [ ] **Step 1: Write model prompt tests**

Tests verify the prompt contains compact tracked symbol facts and does not include raw large payload keys.

- [ ] **Step 2: Implement prompt and model fallback**

Implement:

```python
build_live_commentary_prompt(state)
generate_live_commentary(state, backend, use_llm=True)
```

If backend fails or `use_llm=False`, return deterministic commentary.

- [ ] **Step 3: Run commentary tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_live_dashboard.py -q
```

Expected: PASS.

### Task 5: Wire Into `/dashboard`

**Files:**
- Modify: `nse_agent.py`
- Test: `tests/test_command_dispatch.py`

- [ ] **Step 1: Write routing test**

Patch `nse_agent.run_live_commentary_dashboard` and assert `/dashboard --live-commentary --cycles 1` calls it with parsed config.

- [ ] **Step 2: Implement dispatch**

If parsed `live_commentary` is true, call the live commentary runner instead of `_run_market_dashboard_live`.

- [ ] **Step 3: Run command tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_command_dispatch.py::TestCommandRegistry -q
```

Expected: PASS.

### Task 6: Smoke Run and Regression

**Files:**
- Modify only if smoke run exposes defects.

- [ ] **Step 1: Run bounded terminal smoke**

Run:

```bash
.venv/bin/python nse_agent.py -q "/dashboard --live-commentary --symbols TRENT,DIXON,INDUSINDBK --interval 1 --cycles 1 --no-llm"
```

Expected: exits after one cycle and prints tracker table/commentary.

- [ ] **Step 2: Run focused regression tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_live_dashboard.py tests/test_command_dispatch.py::TestCommandRegistry tests/test_e2e_routing_comprehensive.py::TestRegistrySlashCommands -q
```

Expected: PASS.

- [ ] **Step 3: Check whitespace**

Run:

```bash
git diff --check -- nse_agent.py terminal/live_dashboard.py tests/test_live_dashboard.py tests/test_command_dispatch.py
```

Expected: no output.

