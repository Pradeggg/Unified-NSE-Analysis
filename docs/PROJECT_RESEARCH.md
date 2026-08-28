# Agent Adda — Project Research Reference

> **Auto-generated** by `scripts/build_project_research.py` on **2026-08-28**.
> Rebuilt automatically at the end of every daily pipeline run.
> Edit the generator, not this file — manual edits will be overwritten.

---

## 1 · What It Is

**Agent Adda** (`Unified-NSE-Analysis/`) is a research-grade, end-to-end Indian equities + derivatives analysis platform for NSE. It combines:

- A rules-based screener engine (40 screens across 7 categories)
- A daily 7-phase ETL pipeline into PostgreSQL (`nse_market`)
- An LLM-driven interactive REPL (`nse_agent.py`)
- Multi-modal output: HTML reports, voice briefings, email, WhatsApp
- A 3-layer Knowledge Base (BM25 + ChromaDB + web) shared by the outer (Claude Code) and inner (REPL) loops
- A Talk 2 Stocks web chat MVP (FastAPI)

**Strictly educational — not investment advice.**

---

## 2 · Scale & Scope (Live as of 2026-08-28)

| Dimension | Value |
|---|---|
| KB total entries | **174** |
| KB 7-day token savings | Est. savings:      4632.4K tokens  (≈ $11.5811 if gpt-4o) |
| PostgreSQL tables (`nse_market`) | 137 |
| `market.equity_eod` rows (approx) | 1,208,710 |
| Most recent report | 2026-08-28 22:34 IST |
| Production skill cards | 6 |
| Claude Code project skills | 9 |
| Screeners | 40 PG + ~15 EOD/intraday |
| Scripts | 54 |
| Test files | 297 |

### KB Categories

| Category | Entries |
|---|---|
| — | — |

---

## 3 · Architecture — Two Loops

```
┌─────────────────────────────────────────────────────────────┐
│  OUTER LOOP (Claude Code / Codex)                            │
│  → Queries KB for CLI + ordering rules                       │
│  → Executes via shell, validates output                      │
└───────────────────┬─────────────────────────────────────────┘
                    │  shared KB (BM25 + ChromaDB + web)
┌───────────────────▼─────────────────────────────────────────┐
│  INNER LOOP (AgentAdda REPL — nse_agent.py)                  │
│  → UnifiedRouter: 9-provider cascade                         │
│  → Routes to direct_tool_plan / compound_plan / fallback_llm │
│  → Writes turn state to agent_memory.turn_events (5-turn ctx)│
│  → Learning cycle: pattern → proposal → validate → promote   │
└─────────────────────────────────────────────────────────────┘
```

### Runtime Data Flow

```
NSE / FRED / yfinance / Screener.in / BSE / SEBI
  → fetch_*.py fetchers  (18–24 h TTL disk cache)
    → PostgreSQL nse_market  (primary store — single source of truth)
      → Scoring engines (universe scoring, stage tracker, 40 screeners)
        → HTML reports, voice briefings, email, WhatsApp
          → agentadda.in  (Next.js publish pipeline)
```

---

## 4 · Daily Pipeline — 7 Phases

Run after NSE close (~16:00 IST). Wall-clock: **25–35 min**.

| Phase | Steps | What |
|---|---|---|
| **1 · Data Ingestion** (~3–5 min) | 0, 0B, 1, 1B | Bhavcopy R loader → PG equity/index EOD → FII/DII, F&O, corp events, macro → PG F&O EOD |
| **2 · Scoring** (~5–8 min) | 2, 2B ⚠️, 3A, 2C | Universe analysis → `scores.daily_scores`; fundamentals → `scores.fundamental_scores`; stage backfill; VCP materialiser |
| **3 · Strategy Lab** (~3–5 min) | 3B | Portfolio strategy lab HTML (best strategy + VCP tabs) |
| **4 · Stage & Sector** (~5–8 min) | 4B ⚠️, 7, 4B.5, 4A, 4C, 4E | Stage tracker snapshot; all 40 screeners; UNKNOWN-row repair; sector rotation report; Stage-2 HTML; RRG breadth |
| **5 · Picks & Market** (~3–5 min) | 5A, 5A.5, 5C, 5D | Screener.in refresh for today's picks; corp events refresh; top picks report; EOD market report |
| **6 · Portfolio & Fund** (~3–5 min) | 6, 6B, 6C | Portfolio EOD report; swing playbook HTML; fund dashboard HTML |
| **7 · Distribution** (~5–10 min) | 5D, 7A, 7b, 7c, 8, 8Z | Email top picks; voice briefing; results feed refresh; LLM analyst notes; weekly fundamentals backfill; cleanup + www publish |

### ⚠️ Critical Ordering Rules

| Rule | If violated |
|---|---|
| **PG-FUND-ORDER** — `--fundamentals-only` (Step 2B) **before** `--snapshot` (Step 4B) | Stage-2 HTML cards render NULL for all 4 fundamental sub-scores |
| **VCP-PICKS-ORDER** — `--snapshot` → `materialize_vcp_picks.py` → `top_picks_report.py` | No `vcp+sector` tag on any pick; report validator flags HIGH finding |
| **CSV-200-ORDER** — Tracker auto-falls-back to PG when CSV < 200 days | All stages show UNKNOWN if yfinance backfill has not run |
| **PostgreSQL must be running** before any pipeline step | `./postgres/start_pg.sh start` |
| **Always use `.venv/bin/python`** | System Python misses package deps |

---

## 5 · UnifiedRouter — 9-Provider Cascade

Every REPL turn passes through all 9 providers; highest score wins.

| # | Provider | Catches |
|---|---|---|
| 1 | `PendingOption` | Pending follow-ups from prior turn |
| 2 | `ContextualFollowup` | Continuation phrases ("tell me more", "the above stocks") |
| 3 | `EntityTopic` | Ticker / company / index name detected |
| 4 | `Report` | Reference to a generated report |
| 5 | `VisualScan` | Chart or visual scan request |
| 6 | `MarketSituation` | Market overview / breadth query |
| 7 | `TopMovers` | Gainers, losers, most active |
| 8 | `CompoundStock` | Multi-symbol compound queries |
| 9 | `DirectIntent` | Keyword intents: `stock_brief`, `screener_inquiry`, `intraday_scan`, etc. |

Pattern library: `config/routing_patterns.yml` (centralised 2026-08).

---

## 6 · Database — PostgreSQL `nse_market`

**Connection:** socket `/tmp`, user `nse_admin`, no password, database `nse_market`.

| Schema | Key Tables |
|---|---|
| `ref` | instruments, indices, index_compositions, sector_taxonomy |
| `market` | equity_eod, index_eod, intraday_snapshots, global_prices, market_cap_history |
| `derivatives` | fno_eod (monthly partitioned), fno_signals (PCR, OI buildup class) |
| `scores` | daily_scores, stage_snapshots, stage_changes, stage2_vcp_picks, fundamental_scores, quarterly_results, balance_sheet, cash_flow |
| `signals` | signal_log, fii_dii_flows, regime_history, bulk_block_deals, corporate_events, insider_alerts |
| `breadth` | market_daily (A/D, McClellan, TRIN, % above SMA50/200), sector_daily |
| `macro` | fred_series, indicators, global_correlations, sector_tailwinds, seasonal_returns |
| `screener` | screen_definitions (40), screen_results, stock_screen_summary, mv_latest_results |
| `portfolio` | holdings, transactions, pnl_snapshots, stage2_vcp_picks |
| `agent_skills` | skill_cards, skill_embeddings, skill_tests, skill_execution_logs |
| `agent_learning` | interaction_events, patterns, proposals, promotion_runs |
| `recommendation_reports` | Full strategy council workflow lifecycle |
| `intraday` | ohlcv_bars (5-min/15-min) |
| `agent_memory` | Session snapshots, turn events (5-turn context window) |

All writes: **idempotent upserts** on natural composite keys.

---

## 7 · Scoring System

### Weinstein Stage (1–4)
`SMA50/200 slopes` + `52w-high distance` + `volume ratio` + `ATR expansion`

### Technical Score (0–100)
```
RSI(14) × 30%  +  MACD signal × 25%  +  SMA alignment × 20%
+  Trend momentum × 15%  +  ATR ratio × 10%
+  Pattern overlays: consolidation breakout, Supertrend(10,3), VCP
```

### Fundamental Score — 5 Sub-Scores (0–100, percentile-normalised within sector/size cohort)
```
enhanced_fund_score = 0.30 × earnings_quality  +  0.25 × sales_growth
                    + 0.25 × financial_strength +  0.20 × institutional_backing
```

### Signal Rules
- Stage 2 + tech ≥ 55 + fund ≥ 50 → **BUY**
- Consolidation breakout + vol > 1.4× + RSI 55–72 → **STRONG_BUY**
- Regime overlay (4-state Gaussian HMM) adjusts all thresholds

### Regime (HMM)
`BULL_TREND` / `ROTATION` / `CHOP` / `BEAR_TREND` — derived from Nifty500 return, 10d realised vol, 20d ROC, vol ratio. 6-hour disk cache at `data/_regime_cache.json`.

---

## 8 · The 40 Screeners

### TECHNICAL (12)
Stage2 Breakout · Minervini VCP · RSI Momentum (55–70) · RSI Recovery · Golden Cross · Triple MA Alignment · 52W High Breakout · Supertrend Buy · Volume Surge · Tech Score Elite (≥75) · Stage4 Distribution (bearish) · Range Contraction

### CANSLIM (6)
CAN SLIM Elite (≥18/25) · CAN SLIM Strong (14–17) · Market Leaders · New High + Institutional Vol · Earnings Momentum · Supply & Demand Breakout

### FUNDAMENTAL (6)
Quality Growth (Fund ≥70) · Value+Momentum Blend · High Earnings Quality (≥70) · Strong Balance Sheet (FS ≥70) · Institutional Favourites (IB ≥65) · Improving Fundamentals (50–65, early re-rating)

### GROWTH (5)
Sales Growth Leaders · Earnings Acceleration · Small Cap Gems · Mid Cap Momentum · Sector Rotation Leaders (top 3 from top 5 sectors)

### PIOTROSKI (3)
F-Score ≥7 · Piotroski High + Technical Buy · Low F-Score Avoid (bearish)

### MACRO (4)
FII Net Buying + Stage2 · Sector Macro Tailwind · Global Correlation Outperformers · Insider Accumulation

### COMPOSITE (4)
High Conviction (all factors aligned: IS≥75 + Stage2 + BUY + CAN SLIM≥15 + Fund≥60) · Turnaround Candidates · Defensive Quality · Momentum Beast

---

## 9 · Production Skill Cards (6)

| Skill | Key Trigger | What it produces |
|---|---|---|
| `company_story_v1` | "company story SYMBOL" | 15-dim research (6 DB + 6 Screener + 5 web dims) → HTML |
| `comprehensive_stock_research_v1` | "deep research SYMBOL" | Full Agent Adda dark-theme HTML (51 template placeholders) |
| `equity_chart_v1` | "chart SYMBOL" | SMA20/50/200, EMA9, RSI14, Supertrend, S/R pivots, RS tab |
| `swing_playbook_report_v1` | "swing playbook" | Ranked setups with entry/stop/target |
| `intraday_fno_alert_scan_v1` | "intraday scan" | 6 strategies, R:R ≥ 2.0 gate, email alert |
| `publish_intelligence_report_v1` | "publish report SYMBOL" | Validate → push agentadda-www → verify live → notify recipients |

### Claude Code Project Skills (9)
`daily-pipeline` · `fundamental-analyze` · `tradingview-chart` · `swing-playbook-report` · `live-prices` · `intraday-alerts` · `agent-adda-portfolio-assessment` · `agent-adda-publish-intelligence-report` · `refresh-fund-dashboard`

---

## 10 · External Integrations

| Service | Use |
|---|---|
| **NSE APIs** | Bhavcopy (equity, index, HL, mcap, F&O), FII/DII, corporate events, bulk/block, PIT filings |
| **yfinance** | Live prices (5-min, ~15-min delay), historical EOD backfill |
| **Screener.in** | Fundamentals scraping — full Nifty500 weekly + targeted daily refresh (2.5s delay + jitter) |
| **FRED** | USD/INR, Brent, US 10Y, Copper, India CPI |
| **OpenAI** | GPT-4o (narratives), GPT-5-nano (router + synthesis), TTS, text-embedding-3-small |
| **Anthropic** | Sector rotation narrative generation |
| **Ollama** | Local fallback — Granite4 recommended; nomic-embed-text for local embeddings |
| **BSE** | Filings, XBRL/PDF ingestion |
| **Office365 SMTP** | Daily reports, top picks, intraday alert emails |
| **WhatsApp API** | Alert dispatch (`config/whatsapp.yml`) |
| **DuckDuckGo** | Layer 3 web search fallback (`ddgs`) |
| **GitHub + Cloudflare** | agentadda.in publish pipeline (Next.js) |
| **ChromaDB + pgvector** | Vector store for KB Layer 2 + skill embeddings |
| **FastAPI + Uvicorn** | Talk 2 Stocks web chat MVP (`agent_adda/web_api/`) |
| **macOS launchd** | 5 scheduled jobs (daily, intraday, midday, morning, weekend) |

---

## 11 · MCP Server Tools (10)

`get_market_overview` · `get_stage2_picks` · `get_stock_profile` · `get_swing_candidates` · `get_sector_rotation` · `get_strategy_lab` · `get_fno_signals` · `get_bulk_block_deals` · `get_corporate_events` · `query_kb_tools`

Start server: `python mcp_server.py`

---

## 12 · Key Source Files

| File / Dir | Role |
|---|---|
| `nse_agent.py` | REPL entry point + LLM cascade (569 KB) |
| `daily_refresh.py` | 7-phase pipeline orchestrator |
| `postgres/loader.py` | All PG upserts + 40 screener runs |
| `fixed_nse_universe_analysis.py` | Universe scoring → `scores.daily_scores` |
| `sector_rotation_tracker.py` | Stage snapshots + Stage-2 HTML |
| `sector_rotation_report.py` | Sector rotation report + signal_log.csv |
| `market_breadth.py` | A/D, McClellan, TRIN, breadth metrics |
| `regime_detector.py` | 4-state Gaussian HMM regime classifier |
| `screeners.py` | Weinstein stage classification + EOD screeners |
| `backtesting/engine.py` | Deterministic EOD backtest engine |
| `company_intelligence/` | Company X-Ray orchestrator (11 modules) |
| `terminal/router/` | `UnifiedRouter` + 9-provider cascade + `RouteDecision` schema |
| `terminal/tools.py` | ~40 screener implementations + tool catalogue |
| `terminal/skills/` | Skill Store: generation, embedding, retrieval, execution |
| `mcp_server.py` | MCP server (10 tools) |
| `scripts/company_story.py` | 15-dim Company Story entry point |
| `scripts/generate_research_report.py` | Fill 51-placeholder HTML template |
| `scripts/materialize_stage2_vcp_picks.py` | VCP picks → `portfolio.stage2_vcp_picks` |
| `scripts/backfill_screener_fundamentals.py` | Weekly Screener.in backfill (Nifty500 + MC250) |
| `knowledge_base/` | BM25 + ChromaDB + web search KB |
| `config/routing_patterns.yml` | Centralised router pattern library |
| `config/report_recipients.yml` | Email recipient lists per report type |
| `agent_adda/web_api/` | Talk 2 Stocks FastAPI web chat |

---

## 13 · Test Coverage (297 files)

Key domains:
`agent_adda_cli` · `backtesting` (6 files) · `broker_research` (14) · `company_intelligence` (13) · `fno` (3) · `intraday` (3) · `router + planner` (3) · `research_council` (13+) · `skill_store` (9) · `strategy_council` (10) · `terminal_tools` (12) · `voice` (5)

Run offline-safe suite:
```bash
pytest -m "not llm"
```

Run with LLM tests:
```bash
RESEARCH_COUNCIL_RUN_LLM_TESTS=1 pytest -m llm
```

---

## 14 · Quick-Reference Commands

```bash
# Start PostgreSQL (required before any pipeline step)
./postgres/start_pg.sh start

# Full daily pipeline
python daily_refresh.py

# Interactive REPL
python nse_agent.py

# KB query (query this first for any CLI question)
python -m knowledge_base query "your question here"

# Company deep research
python scripts/company_story.py SYMBOL --open

# Live prices dashboard
python tools/live_prices.py

# Stage-2 snapshot
python sector_rotation_tracker.py --snapshot

# All 40 screeners
python postgres/loader.py

# Fund dashboard
python tools/fund_refresh.py --no-open

# MCP server
python mcp_server.py
```

---

*Last rebuilt: 2026-08-28 · Generator: `scripts/build_project_research.py`*
