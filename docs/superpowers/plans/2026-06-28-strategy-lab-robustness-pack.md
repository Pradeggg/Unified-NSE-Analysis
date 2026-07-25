# Strategy Lab Robustness Pack Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic robustness layer to the existing Agent Adda Strategy Lab: robustness pack -> cost sensitivity -> benchmark comparison -> critic verdict -> report section.

**Architecture:** Keep the Strategy Lab replay engine unchanged. Add `portfolio.engine.robustness` as a pure evaluator over existing leaderboard, benchmark, and cost fields; wire its output into `portfolio.cli strategy-lab`, the summary JSON, a CSV artifact, the Markdown report, and the Strategy Lab HTML source Markdown renderer.

**Tech Stack:** Python, pandas, pytest, existing `portfolio.cli`, existing `terminal.reports` Strategy Lab renderer.

---

### Task 1: Robustness Evaluator

**Files:**
- Create: `portfolio/engine/robustness.py`
- Test: `tests/test_strategy_lab_robustness.py`

- [ ] **Step 1: Write the failing tests**

```python
from portfolio.engine.robustness import evaluate_strategy_robustness


def test_cost_stress_erodes_high_turnover_strategy_and_warns():
    result = evaluate_strategy_robustness(
        {
            "strategy_id": "churn_v1",
            "total_return_pct": 12.0,
            "excess_return_pct": 4.0,
            "max_drawdown_pct": 11.0,
            "profit_factor": 1.3,
            "turnover_pct": 8000.0,
            "cost_drag_pct": 6.0,
            "fills": 250,
            "closed_trades": 80,
        },
        base_slippage_bps=5.0,
        base_brokerage_bps=3.0,
    )

    assert result["cost_scenarios"]["stress"]["adjusted_excess_return_pct"] < 0
    assert result["critic_verdict"] == "WARN"
    assert any("stress" in issue.lower() for issue in result["critic_issues"])


def test_inactive_strategy_is_blocked():
    result = evaluate_strategy_robustness(
        {
            "strategy_id": "inactive_v1",
            "total_return_pct": 0.0,
            "excess_return_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "profit_factor": 0.0,
            "turnover_pct": 0.0,
            "cost_drag_pct": 0.0,
            "fills": 0,
            "closed_trades": 0,
        },
        base_slippage_bps=5.0,
        base_brokerage_bps=3.0,
    )

    assert result["critic_verdict"] == "BLOCK"
    assert result["robustness_score"] < 50
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_strategy_lab_robustness.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'portfolio.engine.robustness'`.

- [ ] **Step 3: Implement the evaluator**

Create dataclass-backed scenario helpers and a public `evaluate_strategy_robustness(row, base_slippage_bps, base_brokerage_bps)` function. The function returns JSON-safe fields:

```python
{
    "strategy_id": "...",
    "robustness_score": 0.0,
    "critic_verdict": "PASS|WARN|BLOCK",
    "critic_issues": ["..."],
    "cost_scenarios": {
        "base": {"total_cost_bps": 8.0, "adjusted_return_pct": 12.0, "adjusted_excess_return_pct": 4.0},
        "stress": {"total_cost_bps": 23.0, "adjusted_return_pct": 0.0, "adjusted_excess_return_pct": -8.0},
        "severe": {"total_cost_bps": 38.0, "adjusted_return_pct": -12.0, "adjusted_excess_return_pct": -20.0},
    },
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_strategy_lab_robustness.py -q`

Expected: PASS.

### Task 2: Strategy Lab Artifact Integration

**Files:**
- Modify: `portfolio/cli.py`
- Test: `tests/test_strategy_lab_robustness.py`

- [ ] **Step 1: Write the failing test**

Add a test that calls `_attach_strategy_lab_robustness(summary, leaderboard)` and asserts:

- `summary["robustness"]["rows"]` exists.
- The leaderboard row receives `robustness_score`, `critic_verdict`, and `cost_stress_excess_return_pct`.
- The returned robustness CSV frame has one row per strategy.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_strategy_lab_robustness.py -q`

Expected: FAIL with missing `_attach_strategy_lab_robustness` or missing fields.

- [ ] **Step 3: Implement the integration**

Import `build_strategy_lab_robustness_frame` from `portfolio.engine.robustness`, call it before `paper_portfolio` publication, write `reports/strategy_robustness.csv`, and include `summary["robustness"]`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_strategy_lab_robustness.py -q`

Expected: PASS.

### Task 3: Report Sections

**Files:**
- Modify: `portfolio/cli.py`
- Modify: `terminal/reports.py`
- Test: `tests/test_strategy_lab_robustness.py`

- [ ] **Step 1: Write the failing tests**

Add tests that assert:

- `_write_strategy_lab_report(path, summary)` includes `## Robustness Pack`, cost stress, and critic verdict rows.
- `terminal.reports._strategy_lab_robustness_markdown(summary)` renders a Markdown section with verdict and stress-adjusted excess return.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_strategy_lab_robustness.py -q`

Expected: FAIL because the section/helper does not exist yet.

- [ ] **Step 3: Implement report rendering**

Append a deterministic `## Robustness Pack` section in `portfolio.cli._write_strategy_lab_report` and a richer Strategy Lab section in `terminal.reports`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_strategy_lab_robustness.py -q`

Expected: PASS.

### Task 4: Verification

**Files:**
- No new production files beyond Tasks 1-3.

- [ ] **Step 1: Run focused tests**

Run: `.venv/bin/python -m pytest tests/test_strategy_lab_robustness.py tests/test_nse_agent_backtest.py -q`

Expected: PASS.

- [ ] **Step 2: Inspect changed files**

Run: `git diff -- portfolio/engine/robustness.py portfolio/cli.py terminal/reports.py tests/test_strategy_lab_robustness.py docs/superpowers/plans/2026-06-28-strategy-lab-robustness-pack.md`

Expected: Diff only contains robustness pack implementation, tests, and plan.
