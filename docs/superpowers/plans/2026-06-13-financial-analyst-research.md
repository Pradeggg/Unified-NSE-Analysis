# Financial Analyst Research Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an end-to-end LLM-backed financial analyst research workflow that indexes broker reports, extracts evidence, publishes dated reports, and lets users list/open those reports from Agent Adda slash commands.

**Architecture:** Keep broker discovery/fetch/parsing in `broker_research.commands`, add a focused analyst report builder in `broker_research.financial_view`, and reuse `company_intel.broker_research_runs` as the PostgreSQL catalog. The first pass uses deterministic, page-grounded sections with an optional LLM synthesis hook, while preserving evidence appendices and no-investment-advice framing.

**Tech Stack:** Python, PostgreSQL/psycopg2, existing Agent Adda command registry, pytest, Rich Markdown rendering, local HTML/Markdown report files.

---

### Task 1: Auto-Extract Facts During Fetch

**Files:**
- Modify: `broker_research/commands.py`
- Test: `tests/test_broker_research_commands.py`

- [ ] Add a failing test proving `/broker-fetch` stores extracted facts after parsing pages.
- [ ] Run `./.venv/bin/python -m pytest -q tests/test_broker_research_commands.py`.
- [ ] Import `extract_and_store_facts_from_pages` and call it after successful parse.
- [ ] Run `./.venv/bin/python -m pytest -q tests/test_broker_research_commands.py`.

### Task 2: Build Financial Analyst Report

**Files:**
- Create: `broker_research/financial_view.py`
- Test: `tests/test_broker_research_financial_view.py`

- [ ] Add failing tests for a page-grounded analyst markdown report containing investment view, broker thesis, valuation, forecasts, risks, evidence, and analyst checks.
- [ ] Implement `build_financial_analyst_markdown(symbol, facts, pages, consensus)` with deterministic evidence-grounded output.
- [ ] Implement `write_financial_analyst_report(symbol, markdown, output_dir, latest_dir)`.
- [ ] Run `./.venv/bin/python -m pytest -q tests/test_broker_research_financial_view.py`.

### Task 3: Catalog And View Reports

**Files:**
- Modify: `broker_research/storage.py`
- Modify: `broker_research/commands.py`
- Test: `tests/test_broker_research_commands.py`

- [ ] Add failing tests for `/financial-research BEL`, `/research-reports BEL`, and `/open-research BEL`.
- [ ] Add storage helpers to list latest `broker_research_runs` by symbol/objective.
- [ ] Add command handlers to generate, catalog, list, and open reports.
- [ ] Run `./.venv/bin/python -m pytest -q tests/test_broker_research_commands.py`.

### Task 4: CLI Wiring

**Files:**
- Modify: `nse_agent.py`
- Modify: `terminal/help.py`
- Test: `tests/test_broker_research_command_registry.py`

- [ ] Add catalog/report slash commands to the command registry and help catalog.
- [ ] Add tests proving the new slash commands are registered and handled without falling through.
- [ ] Run `./.venv/bin/python -m pytest -q tests/test_broker_research_command_registry.py`.

### Task 5: Verification And Commit

**Files:**
- All touched files.

- [ ] Run the broker research test slice.
- [ ] Run `./.venv/bin/python -m py_compile nse_agent.py broker_research/*.py`.
- [ ] Smoke test `/financial-research BEL --broker icici` against local PostgreSQL when available.
- [ ] Commit code and plan with message `feat: add financial analyst research reports`.
