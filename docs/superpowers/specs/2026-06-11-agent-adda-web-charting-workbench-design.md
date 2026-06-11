# Agent Adda — Web Charting Workbench Design Spec
**Version:** 1.0 — 2026-06-11
**Status:** Draft — pending Phase 0 approval
**Backlog:** `docs/BACKLOG.md` § Agent Adda Web Charting Workbench Backlog — AA-WEB-1

---

## 1. Product Goal

Build a first-class browser application for NSE/BSE market analysis with:
- Native OHLCV candlestick charting (no TradingView iframe dependency)
- Configurable technical indicators (EMA, Supertrend, RSI, MACD, VWAP, etc.)
- LLM chart reader grounded in structured Agent Adda evidence (PG + live API)
- Browser plugin: capture any chart (TradingView or other) → Agent Adda analysis
- Deterministic pattern detection from the K13/K15 engine injected into LLM evidence
- Conversational chart memory — follow-up questions bound to the active capture

The browser UI is a **client** of Agent Adda's existing intelligence stack.  
No business logic, pattern detection, or market data is duplicated in the frontend.

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

### 5.3 LLM Chart Analysis System Prompt Contract
The system prompt must:
1. Identify the user's question type (setup / support / target / stop / scenario / pattern / follow-up)
2. Cite specific indicator values from the capture payload
3. Use `pg_evidence` for all numeric claims
4. Label screenshot-only observations as unconfirmed
5. Include: key levels, EMA status, pattern (confirmed/visual), setup, stop/invalidation, bull/bear scenarios, R/R estimate
6. End with: "Research only — not investment advice"

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
│  > which sectors are leading?                 │
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

---

## 9. Security & Evidence Guardrails (AA-WEB-9)

- **Local-only first version:** API bound to `127.0.0.1:8765`, no public exposure
- **Request auth:** shared local token in `~/.agent_adda/web_api_token`
- **Prompt injection controls:** user-supplied text (symbol names, annotations, chart labels) is HTML-escaped and length-limited before injection into LLM prompts
- **Model/cost telemetry:** every LLM call returns `{model, input_tokens, output_tokens, cost_usd}` in the response envelope
- **Evidence validator:** blocks LLM output containing prices or levels not traceable to `pg_evidence` or `capture_payload`
- **Rate limits:** max 10 LLM chart reads per minute (local token bucket)

---

## 10. Regression & QA Plan (AA-WEB-10)

| Test type | Tool | Coverage |
|-----------|------|----------|
| API unit tests | pytest + httpx | All chart/analysis/pattern routes |
| Frontend unit tests | Vitest | Chart rendering, indicator calculation, chat state |
| Browser E2E | Playwright | Chart load, search, capture, chat, export |
| Visual regression | Playwright screenshots | Blank chart, missing data, mobile layout |
| Plugin smoke | Chrome headless + Playwright | Capture flow, side panel render, API bridge |
| Evidence contract tests | pytest | Screenshot-only caveated, PG mismatch warning, pattern label enforcement |

---

## 11. Open Questions (Phase 0 gate items)

| # | Question | Decision needed by |
|---|----------|-------------------|
| Q1 | Does the web app live in this repo (`web_app/`) or a separate frontend repo? | WEB-1 approval |
| Q2 | FastAPI server: standalone process or embedded in `nse_agent.py` startup? | WEB-1 approval |
| Q3 | `lightweight-charts` vs `Apache ECharts` vs `D3` for the chart surface? | WEB-2 start |
| Q4 | Should the plugin target Chrome only (MV3) or also Firefox (MV3 compatible)? | WEB-11 start |
| Q5 | Is WEB-14 (scenario simulation) in scope for v1 or strictly v2? | WEB-1 approval |

---

*Research and analysis only — not investment advice.*
