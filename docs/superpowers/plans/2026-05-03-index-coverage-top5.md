# Index Coverage And Top 5 Stocks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add index coverage and top five sectoral/thematic stock tables to the Index Intelligence dashboard.

**Architecture:** Keep the feature in `index_intelligence.py`. Add pure data builders for catalog normalization, coverage status, and top-five ranking, then extend the existing HTML renderer and report writer.

**Tech Stack:** Python 3, pandas, unittest, static HTML/CSS generated from local CSV data.

---

### Task 1: Tests For Coverage And Top Five Builders

**Files:**
- Modify: `tests/test_index_intelligence.py`

- [ ] **Step 1: Add failing tests**

Add tests that import `build_index_coverage`, `build_top5_index_stocks`, and assert:
- coverage marks mapped indices as `Available`
- coverage marks fallback-populated indices as `Inferred`
- coverage marks absent indices as `Missing`
- top-five output includes only sectoral/thematic indices and caps each index at five rows

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests/test_index_intelligence.py -v`

Expected: import failure for the new builder functions.

### Task 2: Implement Data Builders

**Files:**
- Modify: `index_intelligence.py`

- [ ] **Step 1: Add catalog normalization**

Create `load_index_catalog()` and normalize columns to `INDEX_NAME`, `CATEGORY`, and `API_SYMBOL`.

- [ ] **Step 2: Add coverage builder**

Create `build_index_coverage(index_catalog, constituents, index_data, target_indices)` returning one row per catalog index.

- [ ] **Step 3: Add top-five builder**

Create `build_top5_index_stocks(index_catalog, index_constituent_data, top_n=5)` ranking symbols by local technical strength.

- [ ] **Step 4: Run tests**

Run: `python3 -m unittest tests/test_index_intelligence.py -v`

Expected: all index intelligence tests pass.

### Task 3: Render And Write Outputs

**Files:**
- Modify: `index_intelligence.py`
- Generate: `reports/latest/index_intelligence.html`
- Generate: `reports/latest/index_coverage.csv`
- Generate: `reports/latest/index_top5_stocks.csv`

- [ ] **Step 1: Extend report paths**

Add latest CSV output paths for coverage and top-five stock files.

- [ ] **Step 2: Extend HTML renderer**

Render coverage and top-five tables below the breadth table.

- [ ] **Step 3: Regenerate report**

Run: `python3 index_intelligence.py`

Expected: latest HTML and three latest CSV files are written.

### Task 4: Verification

**Files:**
- Verify: `index_intelligence.py`
- Verify: `reports/latest/index_intelligence.html`

- [ ] **Step 1: Run tests and compile**

Run:
`python3 -m unittest tests/test_index_intelligence.py tests/test_sector_rotation_report.py -v`
`python3 -m py_compile index_intelligence.py tests/test_index_intelligence.py`

- [ ] **Step 2: Browser QA**

Open `reports/latest/index_intelligence.html` with Playwright and verify:
- page is nonblank
- Index Coverage section is visible
- Top 5 Investment Stocks section is visible
- no page-level horizontal overflow on desktop or mobile

- [ ] **Step 3: Commit scoped files**

Stage only `index_intelligence.py`, `tests/test_index_intelligence.py`, the spec/plan, and latest index intelligence outputs.
