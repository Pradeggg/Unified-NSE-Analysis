# Market Dashboard Command Center Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade `/dashboard` and `/dash` into an action-driven terminal and HTML market command center with reactions, opportunities, F&O depth, and top-index stock drilldowns.

**Architecture:** Keep the implementation in `nse_agent.py` because the existing dashboard helpers and command loop already live there. Add pure helper functions for reactions, actions, opportunities, F&O details, drilldown rows, and HTML rendering, then compose them inside the existing Rich renderer and dashboard command path.

**Tech Stack:** Python, Rich terminal UI, existing `terminal.tools.call_tool`, unittest/pytest, static inline HTML/CSS/JavaScript.

---

## File Structure

- Modify `nse_agent.py`: dashboard data fetch, deterministic helper functions, terminal renderable, HTML writer, command flag parsing, optional Enter drilldown toggle.
- Modify `tests/test_market_dashboard_view.py`: helper-level and render-level tests for reactions, opportunity radar, F&O details, drilldown, and HTML.
- Modify `tests/test_nse_agent_monitor_scan.py`: dashboard command parsing/live-loop tests for `--once`, `--html`, and `--drilldown`.
- Maintain `docs/superpowers/specs/2026-05-19-market-dashboard-command-center-design.md`: accepted design reference.

## Task 1: Deterministic Reaction, Action, And Opportunity Helpers

**Files:**
- Modify: `tests/test_market_dashboard_view.py`
- Modify: `nse_agent.py`

- [ ] **Step 1: Write failing helper tests**

Add tests that call:

```python
reactions = nse_agent._dashboard_reactions(_dashboard_snapshot())
actions = nse_agent._dashboard_action_cards(_dashboard_snapshot(), reactions)
opportunities = nse_agent._dashboard_opportunity_radar(_dashboard_snapshot())
```

Assert:

```python
self.assertTrue(any(r["label"] == "Risk-on confirmation" for r in reactions))
self.assertTrue(any(a["command"] == "/scan momentum" for a in actions))
self.assertTrue(any(o["label"] == "Pocket of Strength" for o in opportunities))
self.assertTrue(any("VCP" in o["setup_tags"] for o in opportunities))
self.assertFalse(any("confirmed" in o["evidence"].lower() and "VCP" in o["setup_tags"] for o in opportunities))
```

- [ ] **Step 2: Run red tests**

Run: `.venv/bin/python -m pytest -q tests/test_market_dashboard_view.py`

Expected: FAIL because `_dashboard_reactions`, `_dashboard_action_cards`, and `_dashboard_opportunity_radar` are missing.

- [ ] **Step 3: Implement minimal helpers**

Add pure functions in `nse_agent.py` near existing dashboard helpers:

```python
def _dashboard_reactions(snapshot: dict) -> list[dict]:
    ...

def _dashboard_action_cards(snapshot: dict, reactions: list[dict] | None = None) -> list[dict]:
    ...

def _dashboard_opportunity_radar(snapshot: dict, limit: int = 6) -> list[dict]:
    ...
```

Use only snapshot fields. Include research commands such as `/scan momentum`, `/scan vcp`, `/scan supertrend`, `/scan vwap`, `/analyze SYMBOL`, `/intraday SYMBOL`, and `/strategy-council SYMBOL`.

- [ ] **Step 4: Run green tests**

Run: `.venv/bin/python -m pytest -q tests/test_market_dashboard_view.py`

Expected: PASS for new helper tests and existing dashboard tests.

## Task 2: F&O Detail And Top-Index Drilldown Data

**Files:**
- Modify: `tests/test_market_dashboard_view.py`
- Modify: `nse_agent.py`

- [ ] **Step 1: Write failing data tests**

Add tests that call:

```python
fno = nse_agent._dashboard_fno_details(_dashboard_snapshot())
indices = nse_agent._dashboard_top_index_drilldown(_dashboard_snapshot())
```

Assert:

```python
self.assertIn("NIFTY", fno)
self.assertIn("BANKNIFTY", fno)
self.assertIn("support", fno["NIFTY"])
self.assertEqual(indices[0]["index"], "NIFTY METAL")
self.assertTrue(indices[0]["stocks"])
self.assertIn("/analyze", indices[0]["stocks"][0]["actions"][0])
```

- [ ] **Step 2: Run red tests**

Run: `.venv/bin/python -m pytest -q tests/test_market_dashboard_view.py`

Expected: FAIL because F&O detail and drilldown helper functions are missing.

- [ ] **Step 3: Implement minimal data helpers**

Add:

```python
def _dashboard_fno_details(snapshot: dict) -> dict[str, dict]:
    ...

def _dashboard_top_index_drilldown(snapshot: dict, limit: int = 3, stocks_per_index: int = 5) -> list[dict]:
    ...
```

For BANKNIFTY, read `get_options_chain_BANKNIFTY` and `get_futures_analysis_BANKNIFTY` if present; otherwise return status `unavailable`. For top stocks, use per-index keys like `get_top_gainers_losers_NIFTY_METAL` when present and fall back to current NIFTY 500 movers with a labeled source.

- [ ] **Step 4: Run green tests**

Run: `.venv/bin/python -m pytest -q tests/test_market_dashboard_view.py`

Expected: PASS.

## Task 3: Terminal Renderable And Dashboard Flags

**Files:**
- Modify: `tests/test_market_dashboard_view.py`
- Modify: `tests/test_nse_agent_monitor_scan.py`
- Modify: `nse_agent.py`

- [ ] **Step 1: Write failing render and command tests**

Add render tests for:

```python
text = _render_text(nse_agent._market_dashboard_renderable(_dashboard_snapshot(), width=160, height=44, drilldown=True))
self.assertIn("Reaction Engine", text)
self.assertIn("Action Board", text)
self.assertIn("Opportunity Radar", text)
self.assertIn("Top Stocks in Top Indices", text)
```

Add command parser tests for a helper:

```python
parsed = nse_agent._parse_dashboard_command("/dashboard banks --once --html --drilldown")
self.assertEqual(parsed["focus"], "banks")
self.assertTrue(parsed["once"])
self.assertTrue(parsed["html"])
self.assertTrue(parsed["drilldown"])
```

- [ ] **Step 2: Run red tests**

Run: `.venv/bin/python -m pytest -q tests/test_market_dashboard_view.py tests/test_nse_agent_monitor_scan.py`

Expected: FAIL because renderable keyword and parser helper are missing.

- [ ] **Step 3: Implement terminal panels and parser**

Update:

```python
def _market_dashboard_renderable(snapshot: dict, *, width: int | None = None, height: int | None = None, drilldown: bool = False):
    ...

def _parse_dashboard_command(text: str) -> dict:
    ...

def _run_market_dashboard_live(focus: str = "", llm_backend=None, *, once: bool = False, drilldown: bool = False):
    ...
```

Add Rich tables/panels for Reaction Engine, Action Board, Opportunity Radar, F&O Control, and Top Stocks in Top Indices. Preserve default live behavior.

- [ ] **Step 4: Run green tests**

Run: `.venv/bin/python -m pytest -q tests/test_market_dashboard_view.py tests/test_nse_agent_monitor_scan.py`

Expected: PASS.

## Task 4: HTML Dashboard Writer

**Files:**
- Modify: `tests/test_market_dashboard_view.py`
- Modify: `nse_agent.py`

- [ ] **Step 1: Write failing HTML tests**

Add tests:

```python
html = nse_agent._render_market_dashboard_html(_dashboard_snapshot(), drilldown=True)
self.assertIn("Reaction Engine", html)
self.assertIn("Opportunity Radar", html)
self.assertIn("F&O Control", html)
self.assertIn("Top Stocks in Top Indices", html)
self.assertIn("data-index-card", html)
self.assertIn("/scan vcp", html)
```

- [ ] **Step 2: Run red tests**

Run: `.venv/bin/python -m pytest -q tests/test_market_dashboard_view.py`

Expected: FAIL because `_render_market_dashboard_html` is missing.

- [ ] **Step 3: Implement static HTML renderer and writer**

Add:

```python
def _render_market_dashboard_html(snapshot: dict, *, drilldown: bool = False) -> str:
    ...

def _write_market_dashboard_html(snapshot: dict, *, drilldown: bool = False, open_browser: bool = False) -> Path:
    ...
```

Write under `reports/dashboards/`, escape dynamic text with `html.escape`, and include inline JavaScript for index card expand/collapse.

- [ ] **Step 4: Run green tests**

Run: `.venv/bin/python -m pytest -q tests/test_market_dashboard_view.py`

Expected: PASS.

## Task 5: Snapshot Fetch Expansion And Final Verification

**Files:**
- Modify: `tests/test_nse_agent_monitor_scan.py`
- Modify: `nse_agent.py`

- [ ] **Step 1: Write failing fetch-plan test**

Assert `_fetch_market_dashboard_snapshot` calls existing tools for BANKNIFTY F&O and setup scans:

```python
self.assertIn(("get_options_chain", {"symbol": "BANKNIFTY", "expiry_index": 0}), calls)
self.assertIn(("get_futures_analysis", {"symbol": "BANKNIFTY"}), calls)
self.assertIn(("run_intraday_screener", {"screen_type": "vcp", "timeframe": "15m", "top_n": 5}), calls)
self.assertIn(("run_intraday_screener", {"screen_type": "supertrend", "timeframe": "15m", "top_n": 5}), calls)
```

- [ ] **Step 2: Run red tests**

Run: `.venv/bin/python -m pytest -q tests/test_nse_agent_monitor_scan.py`

Expected: FAIL until fetch expansion is implemented.

- [ ] **Step 3: Expand fetch plan with aliased result keys**

Call BANKNIFTY F&O and selected setup screeners. Store duplicate tool calls under stable keys such as `get_options_chain_BANKNIFTY`, `get_futures_analysis_BANKNIFTY`, `run_intraday_screener_vcp`, and `run_intraday_screener_supertrend`.

- [ ] **Step 4: Run focused verification**

Run: `.venv/bin/python -m pytest -q tests/test_market_dashboard_view.py tests/test_nse_agent_monitor_scan.py`

Expected: PASS.

- [ ] **Step 5: Run broader smoke verification**

Run: `.venv/bin/python -m pytest -q tests/test_terminal_agent_market_prompt.py tests/test_market_dashboard_view.py tests/test_nse_agent_monitor_scan.py`

Expected: PASS or document unrelated failures with exact failing tests.
