# Midcap Leaders Portfolio Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an Agent Adda midcap leaders research and monitor workflow using Stage 2, growth, high EPS/earnings quality, YoY sales increase, sector theme, and government-investment alignment.

**Architecture:** Add a builder under `Mutual Funds/working/` that scores midcap index constituents and writes CSV, Markdown, and HTML artifacts. Add a daily monitor under `tools/` that summarizes the latest generated CSV and keeps paper-order approval gated.

**Tech Stack:** Python, CSV, pandas/yfinance daily history, local Agent Adda index mapping and generated score CSVs, pytest.

---

### Task 1: Scoring Contract

**Files:**
- Create: `tests/test_midcap_leaders.py`
- Create: `Mutual Funds/working/build_midcap_leaders.py`

- [x] **Step 1: Write failing tests for the mandate gates**

Tests must prove that Stage 2, growth, high EPS, YoY sales, sector theme, and government-investment alignment are explicit gates.

- [x] **Step 2: Implement `score_candidate`**

`score_candidate(row)` returns component scores, gate labels, `decision_bucket`, `trigger_state`, and `blockers`.

- [x] **Step 3: Verify the scoring tests**

Run: `.venv/bin/python -m pytest tests/test_midcap_leaders.py -q`

Expected: `3 passed`.

### Task 2: Midcap Builder

**Files:**
- Create: `Mutual Funds/working/build_midcap_leaders.py`
- Create: `docs/fund_policies/2026-08-08-midcap-leaders-portfolio-policy.md`

- [x] **Step 1: Load the midcap universe**

Use `data/index_stock_mapping.csv` and include `NIFTY MIDCAP 50`, `NIFTY MIDCAP 100`, `NIFTY MIDCAP 150`, and `NIFTY MIDCAP SELECT`.

- [x] **Step 2: Load score evidence**

Use `reports/generated_csv/2026/comprehensive_nse_enhanced_20260428.csv` for initial CANSLIM, Minervini, enhanced fundamental, earnings-quality, sales-growth, and trading-value scores.

- [x] **Step 3: Compute current Stage 2 where possible**

Use yfinance daily history to classify Stage 2, Stage 1, Stage 4, RSI, SMA50/SMA200, 6-month return, and 1-year return. Fall back to a clearly labeled technical-score proxy when history is unavailable.

- [x] **Step 4: Write CSV, Markdown, and HTML**

Outputs:
- `Mutual Funds/extracted/agent_adda_midcap_leaders_preselection_YYYYMMDD.csv`
- `docs/fund_policies/research_updates/YYYY-MM-DD-midcap-leaders-portfolio-research-update.md`
- `Mutual Funds/reports/agent_adda_midcap_leaders_report_YYYYMMDD.html`

### Task 3: Daily Monitor

**Files:**
- Create: `tools/midcap_daily_monitor.py`
- Test: `tests/test_midcap_leaders.py`

- [x] **Step 1: Add CSV summary parsing**

`build_monitor_summary(rows)` returns top score names, Stage 2 pass names, growth pass names, high EPS names, YoY sales names, government-aligned names, and order status.

- [x] **Step 2: Keep paper-order gate closed**

Paper orders are allowed only when `TRIGGER_READY_REVIEW` exists and there are no blocked triggers. The first version reports `NO` because official financial refresh remains mandatory.

### Task 4: Verification

**Files:**
- Test: `tests/test_midcap_leaders.py`
- Generated artifacts under `Mutual Funds/` and `docs/fund_policies/research_updates/`

- [x] **Step 1: Run focused tests**

Run: `.venv/bin/python -m pytest tests/test_midcap_leaders.py -q`

- [x] **Step 2: Generate full artifacts**

Run: `.venv/bin/python 'Mutual Funds/working/build_midcap_leaders.py' --run-date 20260808`

- [x] **Step 3: Check monitor summary**

Run: `.venv/bin/python tools/midcap_daily_monitor.py --skip-run --json --run-date 20260808`
