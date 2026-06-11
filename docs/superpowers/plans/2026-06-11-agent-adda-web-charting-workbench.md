# Agent Adda — Web Charting Workbench Implementation Plan
**Version:** 1.0 — 2026-06-11
**Spec:** `docs/superpowers/specs/2026-06-11-agent-adda-web-charting-workbench-design.md`
**Backlog:** `docs/BACKLOG.md` § AA-WEB-1 → AA-WEB-17

---

## Phase 0 — Design Gate (WEB-1, WEB-16)
**Gate condition:** both items below must be approved before Phase 1 starts.

- [ ] WEB-1: Architecture spec approved (this document + design spec)
- [ ] WEB-16: API surface contract ratified — `agent_adda/web_api/schemas.py` defines all shared types before WEB-2/3/6 begin

**Open questions to resolve in Phase 0:** Q1–Q5 in design spec §11.

---

## Phase 1 — Data & Evidence Foundation (WEB-3, WEB-12)

### WEB-3: PostgreSQL Market Data API
- [ ] FastAPI app scaffold at `agent_adda/web_api/`
- [ ] Symbol search endpoint: `/api/symbols/search?q=BANKNIFTY&exchange=NSE`
- [ ] OHLCV endpoint: `/api/chart/ohlcv?symbol=BANKNIFTY&exchange=NSE&timeframe=5m&from=&to=`
- [ ] Technical snapshot endpoint: `/api/chart/technicals?symbol=&timeframe=`
- [ ] Market breadth endpoint: `/api/market/breadth`
- [ ] Index snapshot endpoint: `/api/market/indices`
- [ ] Stale/missing data responses: `{"status": "stale", "as_of": "...", "data": ...}`
- [ ] Tests: valid symbol, alias, unknown symbol, PG unavailable, stale data

### WEB-12: Chart Capture Evidence Contract
- [ ] `ChartCapturePayload` Pydantic schema in `agent_adda/web_api/schemas.py`
- [ ] `ActiveChartContext` schema
- [ ] Evidence validator: blocks LLM output with prices not in `pg_evidence`
- [ ] Conflict detection: `screenshot_level vs pg_level` → warn if diff > 0.5%
- [ ] Regression fixtures: screenshot-only, screenshot+PG, conflicting data
- [ ] Tests: visual observation labeling, PG mismatch warning, pattern label enforcement

---

## Phase 2 — Native Chart Surface (WEB-2, WEB-4)

### WEB-2: Candlestick Chart Workspace
- [ ] React/Vite scaffold at `web_app/`
- [ ] `lightweight-charts` integration with OHLCV + volume
- [ ] Crosshair, zoom/pan, range selector
- [ ] Right-side price axis with key level markers
- [ ] Drawing/annotation layer (horizontal lines, trend lines)
- [ ] Persistent workspace state (localStorage)
- [ ] Responsive: desktop + mobile breakpoints

### WEB-4: Indicator Engine
- [ ] EMA 20/50/100/200 overlays
- [ ] Supertrend (configurable period/multiplier)
- [ ] RSI panel (configurable period)
- [ ] MACD panel
- [ ] VWAP overlay (intraday)
- [ ] Volume profile
- [ ] Weinstein stage markers
- [ ] VCP/compression detection markers
- [ ] High-volume flush detection markers
- [ ] Add/remove indicator without chart reload
- [ ] Indicator values match `terminal/tools.py` calculations within 0.1% tolerance

---

## Phase 3 — Chart Intelligence (WEB-6, WEB-13, WEB-17)

### WEB-6: LLM Chart Reader + Technical Analysis Chatbot
- [ ] `/api/analysis/chart` POST endpoint (accepts `ChartCapturePayload`)
- [ ] LLM prompt contract (see design spec §5.3)
- [ ] System prompt with market-specific sections: KEY LEVELS, EMA STATUS, PATTERN, SETUP, STOP/INVALIDATION, BULL/BEAR SCENARIOS, R/R
- [ ] Screenshot + PG evidence path
- [ ] Structured-evidence-only path (no screenshot)
- [ ] Evidence guardrail: reject LLM output with invented levels
- [ ] Chat UI component in `web_app/src/components/ChatPanel/`
- [ ] Follow-up binding to `ActiveChartContext`
- [ ] Tests: image-only, PG-only, both paths; guardrail rejection; stop/target extraction

### WEB-13: Conversational Chart Memory
- [ ] `ActiveChartContext` store in `web_app/src/store/`
- [ ] Context binding: follow-up turns use active context
- [ ] Context reset triggers: symbol change, timeframe change, "New Capture"
- [ ] "Compare with previous capture" diff view
- [ ] Side panel shows: symbol, timeframe, captured_at, key levels, pattern findings
- [ ] Tests: binding persistence, context reset, follow-up resolution, multi-symbol isolation

### WEB-17: Chart Pattern Intelligence Bridge
- [ ] `/api/patterns/query?symbol=&timeframe=` endpoint wrapping K13 engine
- [ ] Pattern status labels: confirmed / forming / none / engine-unavailable
- [ ] Pattern evidence injected into `ChartCapturePayload.pg_evidence.patterns`
- [ ] LLM prompt receives pattern_type, neckline, breakout, target, stop, win_rate, avg_move, sample_size
- [ ] Visual observation fallback when K13 unavailable
- [ ] Tests: K13 confirmed pattern, forming pattern, no pattern, K13 unavailable

---

## Phase 4 — Browser Plugin (WEB-11, WEB-9)

### WEB-11: Browser Plugin / Side Panel
- [ ] Manifest V3 package at `browser_plugin/`
- [ ] Side panel API (`chrome.sidePanel`)
- [ ] "Capture Chart" button → explicit user action only
- [ ] Tab screenshot via `chrome.tabs.captureVisibleTab` with `activeTab` permission
- [ ] Read-only content script: extracts symbol/timeframe hints from page title/DOM metadata only
- [ ] Local API bridge: `POST localhost:8765/api/analysis/chart`
- [ ] Side panel UI: symbol/TF selector, capture button, PG levels panel, chat, pattern findings
- [ ] Captured-first enforcement: chat disabled until capture is triggered
- [ ] In-extension safeguards: no page navigation, no DOM mutation by Agent Adda code
- [ ] Tests: capture flow, metadata extraction, API bridge, captured-first enforcement, missing symbol clarification

### WEB-9: Security, Cost & Evidence Guardrails
- [ ] API bound to `127.0.0.1:8765`
- [ ] Local auth token: `~/.agent_adda/web_api_token`
- [ ] Prompt injection controls: escape + length-limit user-supplied text
- [ ] Cost telemetry: `{model, input_tokens, output_tokens, cost_usd}` in every LLM response
- [ ] Rate limiter: 10 LLM requests/minute (token bucket)
- [ ] Evidence validator blocking invented prices

---

## Phase 5 — UX & Operations (WEB-5, WEB-7, WEB-8, WEB-10)

### WEB-5: Symbol Search + Watchlists
- [ ] Fast search (debounced, 200ms) for symbol, alias, company name, index
- [ ] NSE/BSE collision disambiguation
- [ ] Watchlists: add/remove, persist to localStorage, one-click open chart
- [ ] Recent symbols history

### WEB-7: Heat Maps & Market Context Panels
- [ ] Sector heat map (% change, colour-coded)
- [ ] Watchlist heat map
- [ ] Top movers panel
- [ ] Market breadth panel (A/D, stage distribution, RS distribution)
- [ ] Collapsible panels (chart stays full-width when panels hidden)
- [ ] Mobile: chart + chat usable; panels accessible via drawer

### WEB-8: Export + Terminal Bridge
- [ ] Export chart snapshot + LLM analysis → HTML/Markdown report
- [ ] Terminal command: `/web BANKNIFTY 5m` → opens web app at that symbol/timeframe
- [ ] Report includes: chart image, indicators, LLM setup, evidence trail, timestamp

### WEB-10: Browser Regression + Visual QA
- [ ] Playwright E2E: chart load, search, indicator toggle, LLM chat, export
- [ ] Playwright visual: blank chart, missing data, clipped labels, mobile layout
- [ ] Plugin smoke: Playwright + Chrome headless, capture flow, side panel
- [ ] API mocks for all tests: no live PG or LLM calls in CI

---

## Phase 6 — Advanced (WEB-14, WEB-15)

### WEB-14: Technical Scenario Simulation Engine
- [ ] Deterministic calculators: breakout target, failed breakout, pullback-to-EMA, ATR stop, trailing stop, position size
- [ ] LLM explains scenarios — deterministic engine owns all level/R/R math
- [ ] "Simulate bull case", "simulate bear case", "risk 1% capital" chat commands

### WEB-15: Strategy Playbook + Backtest Bridge
- [ ] Strategy templates: Weinstein Stage 2, VCP, pullback EMA, Supertrend trend-follow, RSI recovery, ORB/VWAP
- [ ] LLM proposes strategy as structured intent → backend validates + runs
- [ ] Backtest/paper-trade bridge: calls existing `backtesting/` infrastructure

---

## Verification Command (after Phase 4)
```bash
# Start local API
AGENT_ADDA_SKIP_VENV_CHECK=1 .venv/bin/python3 -m agent_adda.web_api.main

# Run all web tests
pytest tests/web_api/ tests/browser_plugin/ -q

# Playwright E2E
cd web_app && npx playwright test
```
