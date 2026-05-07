# Short-Term Technical View Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a market-first short-term technical view tab to the Sector Rotation HTML report using local NSE EOD index history.

**Architecture:** Keep the feature inside `sector_rotation_report.py` to match the current generated-report architecture. Add pure functions for index technical metrics and rule-based narrative, then render a self-contained HTML tab using existing CSS/table/chart idioms. Wire the tab into `render_html_interactive()` without changing existing report tabs or the `#screeners` route.

**Tech Stack:** Python 3, pandas, unittest, generated HTML/CSS/SVG, existing local `data/nse_index_data.csv`.

---

### Task 1: Technical Metrics

**Files:**
- Modify: `sector_rotation_report.py`
- Test: `tests/test_sector_rotation_report.py`

- [ ] **Step 1: Write failing tests**

Add tests that import `build_short_term_technical_view`, pass synthetic index history, and assert that the result includes RSI, MACD, SMA alignment, support/resistance, VWAP unavailable when volume is absent, and missing-index notes.

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
.venv/bin/python -m unittest tests.test_sector_rotation_report.SectorRotationReportTests -v
```

Expected: failure because `build_short_term_technical_view` does not exist.

- [ ] **Step 3: Implement metrics**

Add constants and pure helpers to `sector_rotation_report.py`:

- `TECHNICAL_VIEW_INDEX_BASKET`
- `_rsi14()`
- `_macd()`
- `_trend_classification()`
- `build_short_term_technical_view(index_history)`

The builder returns:

```python
{
    "metrics": pd.DataFrame(...),
    "missing_indices": [...],
    "narrative": "...",
}
```

- [ ] **Step 4: Run tests and verify GREEN**

Run the same unittest command. Expected: pass.

### Task 2: HTML Tab

**Files:**
- Modify: `sector_rotation_report.py`
- Test: `tests/test_sector_rotation_report.py`

- [ ] **Step 1: Write failing HTML test**

Add a test that calls `render_html_interactive(..., technical_view=...)` and asserts:

- `data-tab="technical-view"`
- `id="tab-technical-view"`
- `Short-Term Technical View`
- `Broader Market Technical Narrative`
- `Nifty 50`
- Existing `data-tab="screeners"` remains.

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
.venv/bin/python -m unittest tests.test_sector_rotation_report.SectorRotationReportTests -v
```

Expected: failure because the render function has no `technical_view` parameter/tab.

- [ ] **Step 3: Implement tab renderer**

Add:

- `build_technical_view_tab_html(technical_view)`
- lightweight SVG/HTML chart helpers
- CSS classes for cards, matrix, and chart bars
- optional `technical_view` parameter to `render_html_interactive()`
- nav button and section for `technical-view`

- [ ] **Step 4: Run tests and verify GREEN**

Run the same unittest command. Expected: pass.

### Task 3: Report Pipeline Integration

**Files:**
- Modify: `sector_rotation_report.py`

- [ ] **Step 1: Locate main report generation path**

Find where `INDEX_DATA_CSV` is read and where `render_html_interactive()` is called.

- [ ] **Step 2: Build technical view from loaded index data**

Pass `technical_view=build_short_term_technical_view(index_data)` into `render_html_interactive()`.

- [ ] **Step 3: Keep failure graceful**

If local index data is missing or insufficient, pass an empty-state technical view so report generation succeeds.

### Task 4: Verification and Regeneration

**Files:**
- Generated: `reports/sector_rotation/2026/Sector_Rotation_Report_20260507.html`
- Generated: `reports/latest/sector_rotation.html`

- [ ] **Step 1: Run focused tests**

```bash
.venv/bin/python -m unittest tests.test_sector_rotation_report -v
```

- [ ] **Step 2: Compile touched modules**

```bash
.venv/bin/python -m py_compile sector_rotation_report.py tests/test_sector_rotation_report.py
```

- [ ] **Step 3: Regenerate report**

```bash
.venv/bin/python sector_rotation_report.py
```

- [ ] **Step 4: Visual smoke check**

Open or inspect the generated HTML and confirm:

- Technical View tab is visible.
- Charts render as non-empty SVG/HTML content.
- Narrative is visible at the top.
- Screeners tab still works.

