# Agent Adda — Web Charting Workbench Design Spec
**Version:** 1.0 — 2026-06-11
**Status:** Draft — ready for user review
**Backlog:** `docs/BACKLOG.md` § Agent Adda Web Charting Workbench Backlog — AA-WEB-1 through AA-WEB-17

---

## 1. Product Goal

Build a first-class browser application for NSE/BSE market analysis with:
- Native OHLCV candlestick charting (no TradingView iframe dependency)
- Configurable technical indicators (EMA, Supertrend, RSI, MACD, VWAP, etc.)
- LLM chart reader grounded in structured Agent Adda evidence (PG + live API)
- Browser plugin: user opens any chart manually, then captures it for Agent Adda analysis
- Deterministic pattern detection from the K13/K15 engine injected into LLM evidence
- Conversational chart memory — follow-up questions bound to the active capture

The browser UI is a **client** of Agent Adda's existing intelligence stack.  
No business logic, pattern detection, or market data is duplicated in the frontend.

The first production workflow is the browser side panel/plugin. The native chart workbench is built on the same local Agent Adda API so it becomes the long-term first-class charting surface without blocking the TradingView companion workflow.

---

## 2. User Workflows

### 2.1 Native Chart Workflow (Web App)
```
User opens web app → searches symbol (BANKNIFTY) →
selects timeframe (5m) →
chart renders from PG/live data →
indicators overlay (EMA, Supertrend, RSI) →
asks chatbot "EMA compression + RSI recovery — what's the setup?" →
LLM reader cites visible levels + PG evidence + K13 patterns →
follow-up: "what's my stop if I go long?" →
answer bound to active chart context
```

### 2.2 Browser Plugin Workflow (TradingView / External Chart)
```
User opens TradingView manually in browser →
opens Agent Adda side panel (plugin icon) →
sets symbol + timeframe in side panel (or auto-detected from page title) →
clicks "Capture Chart" (explicit user action — not automatic) →
plugin screenshots visible tab →
sends {image, symbol, timeframe, indicators} to local Agent Adda API →
LLM chart reader returns: key levels, EMA status, pattern, setup, stop →
user asks follow-up "simulate bear case" →
answer binds to captured chart context
```

Important product boundary:

- Agent Adda does **not** open TradingView.
- Agent Adda does **not** control, click, scrape, or navigate TradingView.
- The user owns the chart tab and initiates every capture.
- The plugin is a permissioned companion side panel, not a TradingView automation agent.

### 2.3 Pattern-Grounded Analysis
```
User asks "does this look like a cup and handle?" →
K13 engine queried for symbol + timeframe →
if confirmed: returns neckline, breakout level, target, K15 win rate →
if not confirmed: "Visual observation — not confirmed by pattern engine"
```

---

## 3. Architecture Decision

### 3.1 Stack Selection

| Option | Pros | Cons | Decision |
|--------|------|------|----------|
| **React/Vite + FastAPI** | Fast chart libs (lightweight-charts), clean API split, easy plugin bridge | Two repos / build steps | ✅ **Selected** |
| FastAPI/Jinja (server-rendered) | Single Python repo | No reactive chart interactivity | ❌ |
| Next.js + FastAPI | SSR + React | Overkill for local-first tool | ❌ |

**Frontend:** React + Vite + TypeScript  
**Chart library:** `lightweight-charts` (TradingView's open-source library — not the widget)  
**Backend API:** FastAPI (Python) served locally at `localhost:8765`  
**Browser extension:** Manifest V3 Chrome/Edge extension with side panel API

V1 implementation priority:

1. Local Agent Adda API and capability bridge.
2. Browser side panel plugin with explicit chart capture.
3. Technical-analysis chat over captured chart context.
4. Native chart workbench using the same APIs and contracts.

### 3.2 Repository Layout
```
agent_adda/
  web_api/           ← FastAPI app, routes, capability bridge
    routes/
      chart.py       ← OHLCV, indicators, symbol search
      analysis.py    ← LLM chart reader endpoint
      patterns.py    ← K13 pattern query endpoint
      portfolio.py   ← Portfolio chart view
    schemas.py       ← Pydantic models (shared contracts)
    evidence.py      ← PG evidence fetcher (wraps terminal/tools.py)
    cost.py          ← Token/cost telemetry

web_app/             ← React/Vite frontend
  src/
    components/
      Chart/         ← candlestick + volume + overlays
      Indicators/    ← EMA, Supertrend, RSI panels
      ChatPanel/     ← LLM chatbot + context binding
      HeatMap/       ← sector / watchlist heat maps
      Search/        ← symbol search + watchlists
    hooks/
    services/        ← API client (wraps agent_adda/web_api)
    store/           ← chart context, capture context, session state

browser_plugin/      ← Manifest V3 extension
  manifest.json
  side_panel/        ← React side panel UI
  content/           ← content script (read-only page metadata)
  capture/           ← screenshot service (tab capture with permission)
  bridge/            ← local Agent Adda API client
```

### 3.3 Agent Adda Capability Inheritance (AA-WEB-16)

The web app and plugin must inherit existing Agent Adda capabilities through stable local API contracts. They must not duplicate routing, symbol logic, evidence collection, technical calculations, report generation, strategy execution, or guardrails.

Inherited capabilities:

- Symbol/entity resolution from `terminal/entity_resolution.py`
- Situation assessment and semantic intent from the terminal agent pipeline
- Skill Store runtime retrieval and validated execution plans
- PostgreSQL market data, snapshots, breadth, and technical evidence from existing tools
- NSE/BSE/Screener evidence access through existing adapters and source trails
- Technical setup: Weinstein stage, EMA/SMA stack, RSI, ADX, MACD, Supertrend, support/resistance, pivots, 52-week levels
- Market context: breadth, sector context, index/sector leadership, top movers
- RIC Sherlock / company x-ray / Research Council workflows where chart context calls for deeper research
- Backtesting, paper trading, and strategy lab for deterministic simulations and strategy checks
- Report generation, HTML/Markdown export, email handoff, source trail, cost telemetry, and missing-evidence rendering

Browser-specific code is responsible only for:

- side panel / workbench UI
- explicit screenshot capture
- local API calls
- local browser session state
- rendering chat, levels, charts, heat maps, and reports

The local API is responsible for enforcing the same evidence and symbol-validation rules that terminal Agent Adda uses.

---

## 4. Data Architecture

### 4.1 Data Sources (priority order)
1. **PostgreSQL** — OHLCV EOD, intraday bars, technical snapshots, breadth → primary source for all numeric claims
2. **NSE live API** — live quotes, option chain, breadth → intraday supplement
3. **Screenshot / image** — visual observations from browser plugin → secondary, must be confirmed by PG

### 4.2 Data Freshness Policy
| Data type | Max staleness | Fallback |
|-----------|--------------|----------|
| OHLCV daily | 1 trading day | Show stale badge |
| Intraday bars | 5 minutes | Show timestamp |
| Market breadth | 5 minutes | EOD fallback |
| LLM chart analysis | Per capture | Show captured_at |

### 4.3 Symbol Resolution
- Delegate entirely to `terminal/entity_resolution.py`
- No symbol lookup logic in the frontend
- NSE / BSE collisions return explicit disambiguation

---

## 5. LLM Chart Reader — Evidence Contract (AA-WEB-12)

### 5.1 Capture Payload Schema
```python
class ChartCapturePayload(BaseModel):
    image: str | None               # base64 screenshot (optional for native chart)
    source_url: str | None          # page URL (plugin only)
    page_title: str | None          # for auto-detection hints
    user_symbol: str                # user-supplied or auto-detected
    exchange: str                   # "NSE" | "BSE"
    timeframe: str                  # "5m" | "15m" | "1h" | "1D" | "1W"
    visible_indicators: list[str]   # ["EMA20", "EMA50", "Supertrend", "RSI14"]
    user_question: str
    pg_evidence: dict               # from agent_adda/web_api/evidence.py
    conflict_policy: str            # "prefer_pg" | "show_mismatch"
```

### 5.2 Evidence Grounding Rules
- Visual observations from screenshot are labeled: **"[visual observation — unconfirmed]"**
- Numeric levels (support, resistance, EMA values, Supertrend) use PG values, not screenshot readings
- If screenshot and PG disagree on a level by > 0.5%, surface: **"⚠️ Visual shows ~X, PG data shows Y — using PG"**
- Pattern claims without K13 confirmation are labeled: **"[visual pattern guess — not confirmed by pattern engine]"**
- LLM cannot output exact prices not present in PG evidence or capture payload
- Stop loss, targets, risk/reward, position sizing, and scenario levels come from deterministic calculators when available. The LLM may explain them but does not invent them.
- If the capture does not include a confirmed symbol/timeframe, ask for clarification before generating technical claims.

### 5.3 LLM Chart Analysis System Prompt Contract
The system prompt must:
1. Identify the user's question type (setup / support / target / stop / scenario / pattern / follow-up)
2. Cite specific indicator values from the capture payload
3. Use `pg_evidence` for all numeric claims
4. Label screenshot-only observations as unconfirmed
5. Include: key levels, EMA status, pattern (confirmed/visual), setup, stop/invalidation, bull/bear scenarios, R/R estimate
6. End with: "Research only — not investment advice"

### 5.4 Supported Chat Intents

The side-panel chat must treat technical analysis as a first-class workflow. Supported intents include:

- `chart_insights`: summarize trend, momentum, volume, visible patterns, and risk
- `support_resistance`: compute and explain support/resistance levels
- `targets_and_stop`: generate target zones, stop loss, invalidation, and risk/reward
- `bull_bear_scenario`: simulate bullish and bearish paths from current levels
- `indicator_explain`: interpret EMA/SMA, RSI, MACD, Supertrend, VWAP, ATR, ADX, and volume profile
- `strategy_fit`: map the chart to approved Agent Adda strategy playbooks
- `backtest_request`: invoke deterministic backtesting/paper-trading bridge
- `follow_up`: answer using the active chart context without re-resolving the wrong symbol
- `report_export`: promote a chart read into an HTML/Markdown report

All intents return a source/evidence envelope. Missing evidence blocks unsupported claims instead of producing a polished but ungrounded answer.

---

## 6. Conversational Chart Memory (AA-WEB-13)

### 6.1 Active Chart Context Schema
```python
class ActiveChartContext:
    capture_id: str
    symbol: str
    exchange: str
    timeframe: str
    captured_at: datetime
    visible_indicators: list[str]
    computed_levels: dict           # support, resistance, EMA values from PG
    user_drawings: list[dict]       # user-added annotations
    llm_conclusions: list[str]      # key outputs from LLM turns
    pg_evidence_version: str        # timestamp of PG snapshot
    pattern_findings: list[dict]    # K13 confirmed patterns
```

### 6.2 Context Binding Rules
- Follow-up turns bind to `ActiveChartContext` until user explicitly:
  - Changes symbol, timeframe, or exchange
  - Clicks "New Capture"
  - Clicks "Clear Context"
- "What is support?" → answers from `computed_levels.support` in active context
- "What changed since the last capture?" → diffs `computed_levels` and `pg_evidence_version`
- "Give targets and stop" → uses active symbol/timeframe, deterministic levels, and current risk model
- "Simulate the bear case" → uses active chart levels and scenario calculators
- "Backtest this setup" → converts active chart context to a validated strategy request

### 6.3 Context Reset And Ambiguity Policy

The side panel must make context state visible. If the user captures a different chart, changes symbol/timeframe, or asks about another symbol, the UI creates a new active context. If the screenshot metadata and user-entered symbol disagree, the panel must ask for confirmation before analysis.

---

## 7. Chart Pattern Intelligence Bridge (AA-WEB-17)

### 7.1 Pattern Query Flow
```
Chart reader receives symbol + timeframe →
calls agent_adda/web_api/patterns.py →
queries K13 detector for symbol + timeframe →
returns: {pattern_type, status, neckline, breakout_level, target, stop,
          win_rate, avg_move, sample_size, detected_at}
→ injected into LLM evidence payload under "pattern_evidence"
```

### 7.2 Pattern Status Labels
| K13 status | LLM label |
|------------|-----------|
| `confirmed` | Pattern confirmed by engine — levels are deterministic |
| `forming` | Pattern forming — levels provisional |
| `none` | No pattern detected by engine |
| `error` | Engine unavailable — visual observation only |

---

## 8. Browser Plugin Architecture (AA-WEB-11)

### 8.1 Captured-First Enforcement
- **No analysis runs without an explicit user capture action**
- The "Capture Chart" button is the only trigger — there is no automatic/background capture
- The extension manifest declares `activeTab` permission (not `tabs` or `history`)
- Content script is read-only: reads page title, URL, symbol from DOM metadata only — no interaction
- Agent Adda API receives the screenshot payload; the extension never sends page DOM or cookies
- The extension never opens TradingView, changes the chart, clicks page controls, or attempts to bypass access/login restrictions

### 8.2 Side Panel Components
```
┌─ Agent Adda Side Panel ──────────────────────┐
│  Symbol: [BANKNIFTY  ▾]  TF: [5m ▾]  [NSE]  │
│  ┌─────────────────────────────────────────┐ │
│  │  [📷 Capture Chart]   [🔄 Refresh PG]  │ │
│  └─────────────────────────────────────────┘ │
│  Captured: BANKNIFTY 5m — 11 Jun 12:22       │
│  ─────────────────────────────────────────── │
│  💬 Chat                                      │
│  > support, resistance, target, stop?         │
│  ─────────────────────────────────────────── │
│  🔍 Key Levels (from PG)                     │
│  Support: 55,048 | Resistance: 55,449        │
│  EMA cluster: 55,273–55,276                  │
│  Supertrend: 55,126 (green)                  │
│  ─────────────────────────────────────────── │
│  📐 Pattern Engine                            │
│  No pattern confirmed for BANKNIFTY 5m       │
└──────────────────────────────────────────────┘
```

### 8.3 Side Panel Interaction Model

Primary actions:

- Capture visible chart
- Confirm symbol/timeframe
- Ask chart question
- Refresh Agent Adda evidence
- Simulate bull/bear scenario
- Run approved strategy/backtest
- Export chart read to report

The side panel should show compact always-visible state:

- active symbol/timeframe/exchange
- captured_at
- data freshness
- support/resistance
- stop/invalidation
- current target zone
- source/evidence status

---

## 9. Security & Evidence Guardrails (AA-WEB-9)

- **Local-only first version:** API bound to `127.0.0.1:8765`, no public exposure
- **Request auth:** shared local token in `~/.agent_adda/web_api_token`
- **Prompt injection controls:** user-supplied text (symbol names, annotations, chart labels) is HTML-escaped and length-limited before injection into LLM prompts
- **Model/cost telemetry:** every LLM call returns `{model, input_tokens, output_tokens, cost_usd}` in the response envelope
- **Evidence validator:** blocks LLM output containing prices or levels not traceable to `pg_evidence` or `capture_payload`
- **Rate limits:** max 10 LLM chart reads per minute (local token bucket)
- **No external data exfiltration by default:** screenshot and metadata are sent only to the local Agent Adda API; any external LLM call is made by Agent Adda with explicit telemetry and model configuration
- **Research-only stance:** every strategy, target, and stop is presented as research/education, not financial advice or an execution instruction

---

## 10. Technical Scenario Simulation And Strategy Bridge (AA-WEB-14 / AA-WEB-15)

The LLM can request simulation or strategy evaluation, but deterministic services own the calculations.

### 10.1 Scenario Simulation

Supported deterministic scenarios:

- breakout above resistance
- failed breakout and reversal
- breakdown below support
- pullback to EMA20/EMA50/VWAP
- Supertrend flip
- RSI recovery or RSI failure below 50
- ATR trailing stop
- gap-up/gap-down handling
- position sizing for a given risk amount or account percentage

Output contract:

```json
{
  "scenario": "breakout",
  "assumptions": ["price holds above 55276", "volume above 20-bar average"],
  "entry_zone": [55276, 55320],
  "targets": [55449, 55572],
  "stop": 55048,
  "risk_reward": 1.8,
  "invalidation": "close below 55048",
  "evidence": ["pg_levels", "atr14", "ema_cluster", "supertrend"]
}
```

### 10.2 Strategy Bridge

Supported first strategy families:

- Weinstein Stage 2 continuation
- VCP breakout
- Darvas box breakout
- pullback to 20/50 EMA in uptrend
- Supertrend trend following
- RSI recovery after oversold flush
- VWAP reclaim
- opening range breakout

The browser chat may ask "which strategy fits this chart?" The backend maps the chart context to approved strategy templates, validates required inputs, and runs only deterministic backtest/paper-trading paths. LLM output may explain the selected strategy and caveats but cannot execute arbitrary strategy logic.

---

## 11. Regression & QA Plan (AA-WEB-10)

| Test type | Tool | Coverage |
|-----------|------|----------|
| API unit tests | pytest + httpx | All chart/analysis/pattern routes |
| Frontend unit tests | Vitest | Chart rendering, indicator calculation, chat state |
| Browser E2E | Playwright | Chart load, search, capture, chat, export |
| Visual regression | Playwright screenshots | Blank chart, missing data, mobile layout |
| Plugin smoke | Chrome headless + Playwright | Capture flow, side panel render, API bridge |
| Evidence contract tests | pytest | Screenshot-only caveated, PG mismatch warning, pattern label enforcement |
| Capability inheritance tests | pytest | Browser API calls reuse Agent Adda symbol, evidence, source trail, and strategy contracts |
| Chat follow-up tests | pytest + component tests | Active chart binding, symbol switch, ambiguous screenshot handling, context reset |

---

## 12. Open Questions (Phase 0 gate items)

| # | Question | Decision needed by |
|---|----------|-------------------|
| Q1 | Confirm same-repo layout: `agent_adda/web_api/`, `web_app/`, and `browser_plugin/`. | WEB-1 approval |
| Q2 | Confirm FastAPI starts as a standalone optional local service before any later Agent Adda startup integration. | WEB-1 approval |
| Q3 | Confirm `lightweight-charts` for the native chart surface unless implementation testing exposes a blocker. | WEB-2 start |
| Q4 | Confirm Chrome/Edge MV3 only for v1, then Firefox later if needed. | WEB-11 start |
| Q5 | Decide whether simulations/backtests ship in plugin v1 or as immediate v1.1 after capture + chart chat. | WEB-1 approval |
| Q6 | Decide whether plugin capture history stores locally only, or also syncs to Agent Adda session memory/PostgreSQL. | WEB-13 start |

---

*Research and analysis only — not investment advice.*
