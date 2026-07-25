# Edge Knowledge Phase 0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist intraday F&O research findings as queryable, versioned Edge Knowledge Nodes with confidence, lineage, refresh history, and optional command-line persistence.

**Architecture:** Add a focused `terminal.edge_knowledge` module that converts existing intraday study outputs into deterministic node records and persists them to PostgreSQL under a new `research` schema. The intraday study remains the source of metrics; persistence is opt-in via `--persist-edges` so existing report behavior stays unchanged.

**Tech Stack:** Python, pandas, psycopg2/PostgreSQL, pytest/unittest, existing `terminal.intraday_indicator_study` outputs.

---

### Task 1: Edge Knowledge Domain Model

**Files:**
- Create: `terminal/edge_knowledge.py`
- Test: `tests/test_edge_knowledge.py`

- [ ] **Step 1: Write failing tests**

```python
def test_claim_id_is_stable_for_same_condition():
    node = build_edge_node(...)
    assert node.claim_id == build_edge_node(...).claim_id

def test_confidence_rewards_walk_forward_and_sample_size():
    weak = score_edge_confidence(trades_n=4, expectancy_r=0.02, profit_factor=1.02, wf_status="unconfirmed", wf_positive_rate=0, persistence_count=0)
    strong = score_edge_confidence(trades_n=40, expectancy_r=0.18, profit_factor=1.7, wf_status="confirmed", wf_positive_rate=75, persistence_count=3)
    assert strong > weak
```

- [ ] **Step 2: Run red tests**

Run: `.venv/bin/python -m pytest tests/test_edge_knowledge.py -q`
Expected: import failure for `terminal.edge_knowledge`.

- [ ] **Step 3: Implement minimal domain model**

Add dataclasses:
- `EdgeKnowledgeNode`
- `EdgeRefreshRun`

Add functions:
- `make_claim_id`
- `score_edge_confidence`
- `classify_edge_status`
- `build_edge_nodes`

- [ ] **Step 4: Run green tests**

Run: `.venv/bin/python -m pytest tests/test_edge_knowledge.py -q`
Expected: all tests pass.

### Task 2: PostgreSQL Persistence

**Files:**
- Modify: `terminal/edge_knowledge.py`
- Test: `tests/test_edge_knowledge.py`

- [ ] **Step 1: Write failing test with fake cursor**

```python
def test_persist_edge_nodes_creates_schema_and_upserts_rows():
    conn = FakeConnection()
    result = persist_edge_nodes(conn, refresh_run, [node])
    assert result["nodes"] == 1
    assert any("CREATE SCHEMA IF NOT EXISTS research" in sql for sql, _ in conn.statements)
    assert any("edge_knowledge_nodes" in sql for sql, _ in conn.statements)
```

- [ ] **Step 2: Run red test**

Run: `.venv/bin/python -m pytest tests/test_edge_knowledge.py::test_persist_edge_nodes_creates_schema_and_upserts_rows -q`
Expected: missing function failure.

- [ ] **Step 3: Implement schema and persistence**

Create tables:
- `research.edge_refresh_runs`
- `research.edge_knowledge_nodes`
- `research.edge_refresh_history`

Use deterministic `claim_id` as upsert key and append refresh history every run.

- [ ] **Step 4: Run green tests**

Run: `.venv/bin/python -m pytest tests/test_edge_knowledge.py -q`
Expected: all tests pass.

### Task 3: Intraday Study Integration

**Files:**
- Modify: `terminal/intraday_indicator_study.py`
- Modify: `terminal/backtest.py`
- Test: `tests/test_intraday_indicator_study.py`

- [ ] **Step 1: Write failing command test**

Add a test that runs `/intraday-indicator-study ... --persist-edges` with CSV input and patches persistence to assert that nodes are built and persistence is invoked.

- [ ] **Step 2: Run red test**

Run: `.venv/bin/python -m pytest tests/test_intraday_indicator_study.py::TestIntradayIndicatorStudy::test_command_can_persist_edge_nodes -q`
Expected: unknown `--persist-edges` or missing persistence output.

- [ ] **Step 3: Wire opt-in persistence**

Add `persist_edges: bool = False` to `StudyConfig`; in `run_intraday_indicator_study`, after report generation build/persist nodes when enabled. Add CLI flag `--persist-edges` in `terminal/backtest.py` and include persistence counts in terminal output.

- [ ] **Step 4: Run focused tests**

Run: `.venv/bin/python -m pytest tests/test_edge_knowledge.py tests/test_intraday_indicator_study.py -q`
Expected: all tests pass.

### Task 4: Verification

**Files:**
- No additional files.

- [ ] **Step 1: Compile touched Python files**

Run: `.venv/bin/python -m py_compile terminal/edge_knowledge.py terminal/intraday_indicator_study.py terminal/backtest.py`
Expected: exit code 0.

- [ ] **Step 2: Run focused tests**

Run: `.venv/bin/python -m pytest tests/test_edge_knowledge.py tests/test_intraday_indicator_study.py -q`
Expected: all tests pass.

- [ ] **Step 3: Run a dry command path without persistence**

Run existing CSV command path from the tests or a small fixture to confirm default behavior remains non-persistent.

Expected: report writes continue to work and persistence is not invoked unless `--persist-edges` is supplied.
