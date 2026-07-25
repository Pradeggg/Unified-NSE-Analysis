# Strategy Lab Risk Governance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add risk governance to the Strategy Lab replay path.

**Architecture:** Extend `ReplayConfig` with a `ReplayRiskPolicy`, enforce policy inside `portfolio.engine.event_loop` before entry/add orders, and expose policy events/counters through replay output. Keep signal rules unchanged.

**Tech Stack:** Python, pandas, pytest, existing portfolio engine dataclasses.

---

### Task 1: Replay Risk Policy Tests

**Files:**
- Modify: `tests/portfolio/test_event_loop.py`

- [ ] **Step 1: Write failing tests**

Add tests that assert buys are blocked by gross exposure, single-stock cap, sector cap, drawdown pause, turnover cap, Stage 1 drift add blocking, and that trim sell orders are generated for overweight positions.

- [ ] **Step 2: Run tests to verify failure**

Run: `.venv/bin/python -m pytest tests/portfolio/test_event_loop.py -q`

Expected: new tests fail because `ReplayRiskPolicy` does not exist.

### Task 2: Replay Risk Policy Implementation

**Files:**
- Modify: `portfolio/engine/event_loop.py`

- [ ] **Step 1: Add dataclass**

Create `ReplayRiskPolicy` with defaults for gross exposure, single-stock cap, sector cap, drawdown pause, turnover cap, max positions, trim threshold, trim target, and Stage 1 drift add blocking.

- [ ] **Step 2: Enforce before buy/add**

Route entry/add order creation through a policy gate that uses current prices, current account positions, pending reservations, latest snapshot, and filled notional.

- [ ] **Step 3: Add trim order generation**

Before evaluating new buy/add signals for a held symbol, submit a sell order when position weight exceeds the trim threshold.

- [ ] **Step 4: Run focused tests**

Run: `.venv/bin/python -m pytest tests/portfolio/test_event_loop.py -q`

Expected: all event-loop tests pass.

### Task 3: CLI Wiring And Report Surface

**Files:**
- Modify: `portfolio/cli.py`
- Modify: `portfolio/engine/event_loop.py`

- [ ] **Step 1: Add config to Strategy Lab state**

Include risk policy defaults and replay risk counters in Strategy Lab state/config payload.

- [ ] **Step 2: Run focused CLI tests**

Run: `.venv/bin/python -m pytest tests/portfolio/test_cli.py tests/portfolio/test_postgres_strategy_lab.py -q`

Expected: focused CLI and Strategy Lab tests pass.

### Task 4: Verification

- [ ] **Step 1: Run portfolio test subset**

Run: `.venv/bin/python -m pytest tests/portfolio -q`

Expected: portfolio tests pass.

- [ ] **Step 2: Regenerate Strategy Lab report if local PostgreSQL is available**

Run the existing Strategy Lab command with the local DSN and verify `reports/latest/portfolio_strategy_lab.html` shows risk governance counters.
