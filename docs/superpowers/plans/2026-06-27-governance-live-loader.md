# Governance Live Loader Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a live, cache-backed governance evidence loader and wire it into the governance CLI through `--refresh-live`.

**Architecture:** Create `terminal/governance/live_sources.py` for live fetching, normalization, annual-report text extraction, and cache writing. Extend `cache_sources.py` to read the new parsed governance cache before falling back to legacy cache files. Extend `engine.py` with a `refresh_live` option and CLI flag.

**Tech Stack:** Python stdlib `json`, `re`, `io`, `pathlib`, `datetime`; existing `NSEJsonClient`; existing `terminal.search_engine` and `terminal.web_research`; optional `requests` and `fitz` only inside annual-report extraction; pytest with injected fakes.

---

## File Structure

- Create `terminal/governance/live_sources.py`
  - `refresh_live_sources(symbol, data_dir="data", ...) -> GovernanceRawSources`
  - `extract_annual_report_text_from_pdf_bytes(pdf_bytes, pages_after_heading=20) -> tuple[str, dict]`
  - small normalization helpers for Screener shareholding, announcements, and source trail.

- Modify `terminal/governance/cache_sources.py`
  - Read `data/governance/{SYMBOL}/parsed/raw_sources.json` when present.
  - Deserialize JSON-safe dicts into `GovernanceRawSources`, `GovernanceSource`, and `GovernanceMissingEvidence`.

- Modify `terminal/governance/engine.py`
  - Add `refresh_live=False` parameter to `evaluate_governance()`.
  - Add `--refresh-live` CLI flag.
  - When refreshing, call `refresh_live_sources()` and pass the raw sources to scoring.

- Create `tests/test_governance_live_sources.py`
  - Deterministic live-loader tests using fake functions and fake PDF bytes.

- Extend `tests/test_governance_sources.py`
  - Confirm governance cache is preferred over legacy cache.

- Extend `tests/test_governance_engine.py`
  - Confirm CLI and evaluator pass `refresh_live=True` correctly.

## Task 1: Live Source Loader Tests and Implementation

**Files:**
- Create: `tests/test_governance_live_sources.py`
- Create: `terminal/governance/live_sources.py`

- [ ] **Step 1: Write failing tests**

Add tests that inject fake PIT, fake announcements/actions, fake Screener payload, and fake annual-report text. Assert that `refresh_live_sources("INFY", data_dir=tmp_path, ...)` returns populated `GovernanceRawSources` and writes cache files.

- [ ] **Step 2: Run tests and confirm failure**

Run:

```bash
../../.venv/bin/python -m pytest -q tests/test_governance_live_sources.py
```

Expected: import failure because `terminal.governance.live_sources` does not exist.

- [ ] **Step 3: Implement `live_sources.py`**

Implement the live loader with injected callables:

```python
refresh_live_sources(
    symbol,
    data_dir="data",
    nse_client=None,
    announcements_fetcher=None,
    corporate_actions_fetcher=None,
    screener_fetcher=None,
    pdf_fetcher=None,
)
```

The function writes `raw/*.json`, `raw/annual_report_text.txt`, `parsed/raw_sources.json`, and `manifest.json`.

- [ ] **Step 4: Run live-source tests**

Run:

```bash
../../.venv/bin/python -m pytest -q tests/test_governance_live_sources.py
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

Commit message:

```bash
git commit -m "feat: add governance live source loader"
```

## Task 2: Governance Cache Reader

**Files:**
- Modify: `terminal/governance/cache_sources.py`
- Modify: `tests/test_governance_sources.py`

- [ ] **Step 1: Write failing cache-reader test**

Add a test that writes `data/governance/INFY/parsed/raw_sources.json` and asserts `load_cached_sources("INFY", data_dir=tmp_path)` returns that evidence rather than legacy empty caches.

- [ ] **Step 2: Run targeted test and confirm failure**

Run:

```bash
../../.venv/bin/python -m pytest -q tests/test_governance_sources.py::test_load_cached_sources_prefers_governance_raw_sources_cache
```

Expected: failure because the cache reader ignores the governance cache.

- [ ] **Step 3: Implement governance cache deserialization**

Add helper functions to rebuild `GovernanceSource` and `GovernanceMissingEvidence` instances from JSON-safe dicts.

- [ ] **Step 4: Run source tests**

Run:

```bash
../../.venv/bin/python -m pytest -q tests/test_governance_sources.py
```

Expected: all source tests pass.

- [ ] **Step 5: Commit**

Commit message:

```bash
git commit -m "feat: read cached governance raw sources"
```

## Task 3: Engine and CLI Integration

**Files:**
- Modify: `terminal/governance/engine.py`
- Modify: `tests/test_governance_engine.py`

- [ ] **Step 1: Write failing engine tests**

Add tests for:

- `evaluate_governance("INFY", refresh_live=True, live_source_loader=fake_loader)`
- `main(["INFY", "--refresh-live", "--json"], evaluator=fake_evaluator)` passes `refresh_live=True`.

- [ ] **Step 2: Run targeted tests and confirm failure**

Run:

```bash
../../.venv/bin/python -m pytest -q tests/test_governance_engine.py
```

Expected: failure because the evaluator and CLI do not accept `refresh_live`.

- [ ] **Step 3: Implement integration**

Add `refresh_live` and `live_source_loader` parameters to `evaluate_governance()`. Add `--refresh-live` to the CLI parser and pass it into the evaluator.

- [ ] **Step 4: Run governance tests**

Run:

```bash
../../.venv/bin/python -m pytest -q tests/test_governance_models.py tests/test_governance_parsers.py tests/test_governance_audit_parser.py tests/test_governance_sources.py tests/test_governance_scorer.py tests/test_governance_opinion.py tests/test_governance_engine.py tests/test_governance_live_sources.py
```

Expected: all governance tests pass.

- [ ] **Step 5: Commit**

Commit message:

```bash
git commit -m "feat: wire governance live refresh into CLI"
```

## Task 4: Verification

**Files:**
- No planned code edits.

- [ ] **Step 1: Run focused governance suite**

```bash
../../.venv/bin/python -m pytest -q tests/test_governance_models.py tests/test_governance_parsers.py tests/test_governance_audit_parser.py tests/test_governance_sources.py tests/test_governance_scorer.py tests/test_governance_opinion.py tests/test_governance_engine.py tests/test_governance_live_sources.py
```

- [ ] **Step 2: Run nearby regression tests**

```bash
../../.venv/bin/python -m pytest -q tests/research_council/test_llm_client.py tests/test_results_tools.py tests/test_financial_filing_agent.py
```

- [ ] **Step 3: Run live INFY smoke**

```bash
../../.venv/bin/python -m terminal.governance.engine INFY --refresh-live --json
```

Expected: JSON report includes live source trail entries and materially populated evidence. If a live source is unavailable, the report must disclose the failure in source trail and missing evidence.

- [ ] **Step 4: Confirm worktree status**

```bash
git status --short
```

Expected: clean.
