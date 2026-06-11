# Agent Adda Skills MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the first Agent Adda skills layer with a deterministic fundamental driver diagnosis workflow.

**Architecture:** Add a small `terminal.skills` package for skill metadata, selection, and execution. Integrate the first executable skill through the existing `CommandRegistry` as `/diagnose SYMBOL METRIC`, leaving natural-language auto-routing as a later gated phase to avoid regressions.

**Tech Stack:** Python dataclasses, existing PostgreSQL financial cache via `terminal.financials_cache.read_financials`, existing `nse_agent.py` command registry, pytest.

---

### Task 1: Skill Registry and Selector

**Files:**
- Create: `terminal/skills/__init__.py`
- Create: `terminal/skills/schema.py`
- Create: `terminal/skills/registry.py`
- Create: `terminal/skills/selector.py`
- Test: `tests/test_skills_registry.py`
- Test: `tests/test_skills_selector.py`

- [ ] Write tests that assert the registry contains the core skill ids and that EPS/ROCE questions select `fundamental_driver_diagnosis`.
- [ ] Run the tests and verify they fail because `terminal.skills` does not exist.
- [ ] Implement dataclasses, registry definitions, and keyword-based selector.
- [ ] Run the tests and verify they pass.

### Task 2: Fundamental Driver Diagnosis Engine

**Files:**
- Create: `terminal/skills/fundamental_driver.py`
- Test: `tests/test_fundamental_driver_diagnosis.py`

- [ ] Write tests for EPS decline caused by margin compression.
- [ ] Write tests for ROCE explained by EBIT growth versus capital employed.
- [ ] Write tests for missing financial evidence producing an insufficient-evidence result.
- [ ] Run the tests and verify they fail because the engine does not exist.
- [ ] Implement deterministic metric bridges for `eps`, `roce`, `margin`, `debt`, and `cashflow`.
- [ ] Run the tests and verify they pass.

### Task 3: `/diagnose` Command Integration

**Files:**
- Create: `terminal/skills/commands.py`
- Modify: `nse_agent.py`
- Test: `tests/test_command_dispatch.py`

- [ ] Write tests that `/diagnose DMART eps` is registered and calls the diagnosis command handler.
- [ ] Write tests that `/diagnosee` is not matched.
- [ ] Run tests and verify they fail before command registration.
- [ ] Register `/diagnose` in `_build_command_registry`, `_SLASH_COMMANDS`, and `_CMD_CATEGORIES`.
- [ ] Run focused command tests and verify they pass.

### Task 4: Verification

**Files:**
- No new files.

- [ ] Run focused suite:
  `pytest tests/test_skills_registry.py tests/test_skills_selector.py tests/test_fundamental_driver_diagnosis.py tests/test_command_dispatch.py -q`
- [ ] Smoke:
  `python nse_agent.py --query "/diagnose DMART eps" --no-briefing --readiness-no-refresh`
- [ ] Confirm output includes `Short Answer`, `Metric Bridge`, `Evidence`, and `What to Watch`.
