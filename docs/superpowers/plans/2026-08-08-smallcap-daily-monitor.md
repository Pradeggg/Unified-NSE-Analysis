# Smallcap Daily Monitor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a reusable daily monitor for the Agent Adda Small Cap Portfolio and a Codex skill that runs it consistently.

**Architecture:** Keep the existing smallcap research builder as the report generator. Add a thin CLI tool in `tools/` that invokes the builder, loads the generated CSV, summarizes trigger/blocker state, and prints artifact paths. Add a local Codex skill that routes future daily-monitor prompts to this tool.

**Tech Stack:** Python standard library, pytest, existing Agent Adda report builder, Codex local skill files.

---

### Task 1: Monitor Summary Tool

**Files:**
- Create: `tools/smallcap_daily_monitor.py`
- Test: `tests/test_smallcap_daily_monitor.py`

- [x] **Step 1: Write the failing test**

```python
def test_monitor_summary_flags_blocked_trigger_and_no_order() -> None:
    csv_text = "symbol,..."
    rows = parse_rows(csv_text)
    summary = build_monitor_summary(rows)
    assert summary["paper_order_allowed"] is False
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_smallcap_daily_monitor.py -q`

Expected: fail with `ModuleNotFoundError: No module named 'tools.smallcap_daily_monitor'`.

- [x] **Step 3: Write minimal implementation**

Create `parse_rows`, `build_monitor_summary`, `run_builder`, `render_summary`, and `main`.

- [x] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_smallcap_daily_monitor.py -q`

Expected: `2 passed`.

### Task 2: Skill Wiring

**Files:**
- Create: `/Users/pgorai/.codex/skills/agent-adda-smallcap-daily-monitor/SKILL.md`

- [x] **Step 1: Initialize the skill**

Run:

```bash
python3 /Users/pgorai/.codex/skills/.system/skill-creator/scripts/init_skill.py agent-adda-smallcap-daily-monitor --path /Users/pgorai/.codex/skills
```

- [x] **Step 2: Replace template instructions**

Add workflow commands for:

```bash
.venv/bin/python tools/smallcap_daily_monitor.py
.venv/bin/python tools/smallcap_daily_monitor.py --skip-run
.venv/bin/python tools/smallcap_daily_monitor.py --json
```

### Task 3: Verification

**Files:**
- Verify: `tools/smallcap_daily_monitor.py`
- Verify: `tests/test_smallcap_daily_monitor.py`
- Verify: `/Users/pgorai/.codex/skills/agent-adda-smallcap-daily-monitor/SKILL.md`

- [x] **Step 1: Run focused tests**

```bash
.venv/bin/python -m pytest tests/test_smallcap_daily_monitor.py -q
```

- [x] **Step 2: Run tool from current artifacts**

```bash
.venv/bin/python tools/smallcap_daily_monitor.py --skip-run
```

- [x] **Step 3: Validate skill**

```bash
python3 /Users/pgorai/.codex/skills/.system/skill-creator/scripts/quick_validate.py /Users/pgorai/.codex/skills/agent-adda-smallcap-daily-monitor
```

- [x] **Step 4: Compile Python files**

```bash
.venv/bin/python -m py_compile tools/smallcap_daily_monitor.py 'Mutual Funds/working/build_smallcap_research_update.py'
```
