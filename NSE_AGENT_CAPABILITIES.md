# `nse_agent.py` — Agent Adda: Capabilities & Functionalities

> **Agent Adda** is an AI-powered, interactive NSE market research terminal.  
> It combines a conversational LLM agent with real-time market tools, curated screeners, and multi-step investigative workflows — all rendered in a rich terminal UI.

---

## Table of Contents

1. [Running the Agent](#1-running-the-agent)
2. [UI & Terminal Features](#2-ui--terminal-features)
3. [Data Modes](#3-data-modes)
4. [Startup Briefing](#4-startup-briefing)
4A. [Current Market Dashboard (`/dashboard`)](#4a-current-market-dashboard-dashboard)
4B. [Deliberation Engine](#4b-deliberation-engine)
5. [Prompt Library](#5-prompt-library)
6. [Intraday Scanner (`/scan`)](#6-intraday-scanner-scan)
7. [EOD Screeners (`/screen`)](#7-eod-screeners-screen)
8. [Background Monitors (`/monitor`)](#8-background-monitors-monitor)
9. [Watchlist Alerts (`/alert`)](#9-watchlist-alerts-alert)
10. [F&O / Options](#10-fo--options)
11. [Charts (`/chart`)](#11-charts-chart)
12. [Deep Search Engine (`/search`)](#12-deep-search-engine-search)
13. [Document & Stock Analysis (`/analyze`)](#13-document--stock-analysis-analyze)
14. [CANSLIM Analysis (`/canslim`)](#14-canslim-analysis-canslim)
15. [Forensic Accounting (`/forensic`)](#15-forensic-accounting-forensic)
16. [Event Calendar (`/events`)](#16-event-calendar-events)
17. [Seasonal Heat Calendar (`/heat`)](#17-seasonal-heat-calendar-heat)
18. [Economic Cycle (`/cycle`)](#18-economic-cycle-cycle)
19. [Scenario Engine (`/scenario`)](#19-scenario-engine-scenario)
20. [Portfolio Narratives (`/narrative`)](#20-portfolio-narratives-narrative)
21. [Concall NLP (`/concall`)](#21-concall-nlp-concall)
22. [Voice Briefing (`/voice`)](#22-voice-briefing-voice)
23. [Portfolio P&L (`/pnl`)](#23-portfolio-pl-pnl)
24. [US / Global Markets (`/us`, `/global`)](#24-us--global-markets-us-global)
25. [Report Generation (`/report`)](#25-report-generation-report)
26. [RIC — Recursive Investigative Conversations (`/ric`)](#26-ric--recursive-investigative-conversations-ric)
27. [Data Refresh (`/refresh`)](#27-data-refresh-refresh)
28. [Session Export (`/export`)](#28-session-export-export)
29. [Appearance (`/theme`, `/scale`)](#29-appearance-theme-scale)
30. [Session Management](#30-session-management)
31. [Follow-up Suggestions](#31-follow-up-suggestions)
32. [Autocomplete & Command Discovery](#32-autocomplete--command-discovery)
33. [CLI Arguments](#33-cli-arguments)
34. [Architecture & Tech Stack](#34-architecture--tech-stack)

## 1. Running the Agent

```bash
python nse_agent.py                   # interactive chat (with startup briefing)
python nse_agent.py -q "RELIANCE"     # single query, print result and exit
python nse_agent.py --trace           # show tool-call trace after every response
python nse_agent.py --no-briefing     # skip the startup market briefing
python nse_agent.py --mode intraday   # start in LIVE mode
python nse_agent.py --theme dracula   # start with a specific color theme
python nse_agent.py --scale large     # start with large layout scale
```

---

## 2. UI & Terminal Features

| Feature | Details |
|---------|---------|
| **Input bar** | `prompt_toolkit` — persistent bar at bottom with arrow-key editing |
| **History** | In-memory; arrow-up cycles previous queries |
| **Auto-suggest** | Suggests prior queries as dim ghost text |
| **Tab completion** | Three-tier: slash commands → prompt library (`p<n>`) → stock symbols + phrases |
| **Rich Markdown** | Full Markdown rendered to terminal width (headers, bold, tables, code blocks) |
| **Clickable URLs** | OSC-8 links (iTerm2/WezTerm) + visible raw URLs (macOS Terminal Cmd+click) |
| **Banner** | ASCII art "AGENT ADDA" rendered with Colorama on startup |
| **Spinner** | Animated braille spinner in single-query mode; static status line in chat loop |
| **Mode tag** | Prompt shows `[AUTO]` / `[LIVE🔴]` / `[EOD📚]` and turn count |
| **Separator rules** | Rich horizontal rules separate each agent response |
| **Follow-up block** | Agent ends responses with 3 suggested follow-up questions (reply `1`/`2`/`3`) |
| **Comparison table** | Side-by-side fundamental + technical table for multi-stock comparisons |
| **Tool trace** | `--trace` flag shows a compact table of every tool called, its args, and result |

---

## 3. Data Modes

Control which data source the agent uses:

| Command | Alias | Mode | Data Source |
|---------|-------|------|------------|
| `/live` | `/l`, `/intraday` | **LIVE 🔴** | Real-time NSE API |
| `/eod` | `/h`, `/historical` | **EOD 📚** | Historical CSV + SQLite DB snapshot |
| `/auto` | `/a` | **AUTO** | Keyword-detected from query (default) |

---

## 4. Startup Briefing

Automatically runs on launch (skip with `--no-briefing`). Generates a full market intelligence briefing structured as:

1. **🌍 Global Overnight Context** — US/Asian/SGX markets, macro news, USD/INR, crude oil  
2. **📅 Previous Trading Day Recap** — NIFTY 50 & BANK NIFTY close, top 3 gainers/losers, sector moves  
3. **📊 Current Market Status** — Live NIFTY levels, breadth, FII/DII, top movers  
4. **🎯 Today's Watchlist & Themes** — 3–4 stocks/sectors to watch, key events, NIFTY levels  
5. **🔬 Analyst's Take** — Overall market bias and recommended approach

Followed by 3 clickable follow-up suggestions to start the session.

---

## 4A. Current Market Dashboard (`/dashboard`)

```
/dashboard        # Auto-refreshing stock-market-TV dashboard + narrative
/dash             # Alias for /dashboard
/dashboard banks  # Same dashboard with a focus note
```

Consolidates live NSE tape, animated ticker, sharp rise/fall alerts, sectoral heatmap, F&O positioning, RS screener leaders, intraday view, preset alert/screen ideas, top gainers/losers, FII/DII flows, global read-through, news, and an LLM narrative with deterministic fallback. In interactive mode it opens a compact full-screen view: ticker/pulse animates every second, data refreshes every 60 seconds, and `Ctrl+C` exits.

---

## 4B. Deliberation Engine

`terminal/deliberation/` provides testable reasoning components: `planner.py` converts queries into executable tool tasks, `hypothesis.py` builds competing branches, `evaluator.py` scores evidence and freshness, `simulator.py` frames scenarios, `memory.py` stores watchlist/thesis context, and `renderer.py` produces persona-specific final answers. Placeholder inputs like `/assess SYMBOL` now ask for a real NSE symbol instead of producing a missing-evidence market brief.

---

## 5. Prompt Library

**60 curated, ready-to-run research prompts** across 10 categories.

```
/prompts                    # Browse all 60 prompts
/prompts market             # Filter: Market Overview (6 prompts)
/prompts intraday           # Filter: Intraday Trading (7 prompts)
/prompts technical          # Filter: Technical Analysis (7 prompts)
/prompts sector             # Filter: Sector Analysis (7 prompts)
/prompts screener           # Filter: Screeners & Filters (6 prompts)
/prompts fundamentals       # Filter: Fundamentals & Valuation (7 prompts)
/prompts stock              # Filter: Stock Deep Dive (6 prompts)
/prompts news               # Filter: News & Catalysts (5 prompts)
/prompts portfolio          # Filter: Portfolio (4 prompts)
/prompts global             # Filter: Global & Macro (5 prompts)

p<number>                   # Run a prompt directly, e.g. p7, p23, p45
```

**Category overview:**

| Category | Examples |
|----------|---------|
| 📊 Market Overview | Market Pulse, Breadth Snapshot, FII vs DII Flow, Top Movers, 52-Week Extremes |
| ⚡ Intraday Trading | Bank Nifty Scan, VCP Pattern Hunt, Volume Spike Alert, Supertrend Setups |
| 📈 Technical Analysis | Stage 2 Breakouts, Strong Buy Signals, ADX Trend Leaders, 52W High Breakouts |
| 🏭 Sector Analysis | IT/Banking/Pharma/Auto deep dives, Sector Rotation, Top Sector Today |
| 🔬 Screeners | Stage 2 Universe, Breakout Candidates, High RS Stocks, Recovery Plays |
| 🏦 Fundamentals | TCS/HDFC valuations, High ROE Low PE, Debt-Free Cos, Concall Summaries |
| 🔍 Stock Deep Dive | Full analysis: RELIANCE, INFOSYS, ZOMATO, TATA MOTORS, SBI |
| 📰 News & Catalysts | Top News, Results Calendar, FII Bulk Deals, Macro Events Week |
| 📋 Portfolio | Exposure check, Stage 2 holdings, Screener match, Holdings Health |
| 🌍 Global & Macro | Global Market Check, USD/INR Impact, Crude Effect, India vs EM |

---

## 6. Intraday Scanner (`/scan`)

Scans NSE indices for intraday signals on 15-minute charts.

```
/scan                       # Scan NIFTY 50 (all strategies)
/scan NIFTY BANK            # Scan any NSE index
/scan NIFTY IT
/scan NIFTY MIDCAP 100
/scan NIFTY PHARMA
```

**Strategy shortcuts:**

| Shortcut | Full Strategy | Description |
|----------|--------------|-------------|
| `/scan orb` | Opening Range Breakout | First 15–30m range break + volume |
| `/scan gap` | Gap & Go | Gapping stocks with MACD continuation |
| `/scan macd` | MACD Crossover | Fresh MACD signal line cross |
| `/scan rsi` | RSI Divergence | RSI extreme + Bollinger mean-reversion |
| `/scan bb` | Bollinger Squeeze | Low-volatility squeeze breakout |
| `/scan vwap` | VWAP Reclaim | Price reclaiming/losing VWAP proxy |
| `/scan vcp` | VCP | Volatility Contraction Pattern |
| `/scan momentum` | Momentum | MACD + RSI + Supertrend aligned |

---

## 7. EOD Screeners (`/screen`)

End-of-day stock screeners using the NSE universe database.

| Command | Screener | Description |
|---------|---------|-------------|
| `/screen stage2` | Stage 2 Uptrend | Weinstein Stage 2 advancing stocks |
| `/screen momentum` | 52W High Momentum | Near-52W-high leaders (RS ≥ 1.0) |
| `/screen highrs` | High RS Leaders | Top RS ≥ 1.15 market leaders |
| `/screen turnaround` | Turnaround Recovery | Dip recovery setups |
| `/screen base` | Stage 1 Basing | Stage 1 coiling/consolidating stocks |
| `/screen tight` | Tight Range VCP | Weekly tight-range consolidations |
| `/screen dip` | Oversold Bounce | RSI < 40 dip in Stage 2 uptrend |
| `/screen supertrend` | Supertrend BUY | Supertrend in BUY state |
| `/screen strong` | Strong Buy | STRONG_BUY signal stocks |
| `/screen new` | New Stage 2 Entrants | Newly entered Stage 2 (last 14 days) |
| `/screen breakouts` | Stage 2 Breakouts | Near-pivot breakout candidates |

---

## 8. Background Monitors (`/monitor`)

Runs **background alert workers** that scan the market on a configured interval and surface alerts above the chat prompt automatically.

```
/monitor                                   # Show active monitors + queued/recent scan results
/monitor list                              # List all 14 available strategies
/monitor status                            # Show all running monitors (strategy, index, interval, scans, signals)
/monitor start breakout                    # Start breakout monitor (default: NIFTY 500, every 15m, all directions)
/monitor vcp                               # Shorthand: start VCP monitor with defaults
/monitor start momentum NIFTY BANK 10 buy # Custom: NIFTY BANK, 10m interval, BUY signals only
/monitor start all 15 buy                  # Start ALL strategies combined
/monitor stop breakout                     # Stop a specific monitor
/monitor stop all                          # Stop all running monitors
```

**14 Available Strategies:**

| Strategy | Description |
|----------|------------|
| `breakout` | EMA + volume breakout |
| `volume_surge` | Abnormal volume surge |
| `reversal` | RSI + Bollinger mean-reversion reversal |
| `momentum` | MACD + RSI momentum alignment |
| `supertrend` | Supertrend direction flip |
| `vcp` | Volatility Contraction Pattern |
| `orb` | Opening Range Breakout (5m bars) |
| `gap_go` | Gap and Go continuation |
| `vwap` | VWAP reclaim or loss |
| `engulfing` | Engulfing candlestick pattern |
| `ema_ribbon` | EMA ribbon alignment |
| `multi_confirm` | 3 of 4 indicators agree (confluence) |
| `rsi_divergence` | RSI divergence signal |
| `all` | All strategies combined |

**Alert table columns:** Symbol · Signal · Direction (BUY/SELL/WATCH) · Entry ₹ · Target ₹ · Stop-Loss ₹ · R:R ratio · Confidence

---

## 9. Watchlist Alerts (`/alert`)

Price and indicator alerts checked against live NSE prices. Supports **natural language** parsing via OpenAI GPT-4o-mini.

```
/alert list                                    # List all alerts (id, symbol, trigger, value, timeframe, note)
/alert add NIFTY rsi above 70 in 15min         # RSI alert on 15m timeframe (LLM-parsed)
/alert add RELIANCE breakout                   # Intraday breakout alert (LLM-parsed)
/alert add TCS price above 3500 near earnings  # Price alert with note (LLM-parsed)
/alert add SYMBOL price_above 1500             # Positional parse fallback
/alert add SYMBOL rsi_below 30
/alert del 3                                   # Delete alert by ID
/alert check                                   # Check all alerts against live prices now
/alert monitor                                 # Toggle background polling every 5 min (market hours only)
```

**Supported trigger types:** `price_above` · `price_below` · `rsi_above` · `rsi_below` · `breakout_above` · `breakout_below` · `intraday_breakout`

**Timeframes:** `1d` (daily, default) · `5m` · `15m` · `30m` · `1h` (intraday)

---

## 10. F&O / Options

Live options chain, open interest analysis, and options strategy builder.

```
/options NIFTY               # Live options chain (nearest expiry) — Calls|Strike|Puts table
/options BANKNIFTY           # BANKNIFTY options chain
/options NIFTY 1             # NIFTY options chain (next expiry, index 1)
/chain NIFTY                 # Option chain: PCR, max pain, OI, greeks
/chain BANKNIFTY
/chain FINNIFTY
/oi NIFTY                    # OI analysis: PCR, max pain, CE/PE support/resistance
/oi BANKNIFTY
/fno NIFTY                   # Full F&O overview: chain + futures basis + strategy recommendation
/fno BANKNIFTY
/strategy NIFTY long_straddle         # Build specific options strategy with pricing
/strategy NIFTY bull_call_spread
/strategy BANKNIFTY iron_condor
```

**Options chain table shows:** Call OI · Call IV · Call LTP · Strike (ATM highlighted) · Put LTP · Put IV · Put OI

**Available options strategies:** `long_call` · `long_put` · `bull_call_spread` · `bear_put_spread` · `long_straddle` · `long_strangle` · `iron_condor` · `covered_call` · `protective_put` · `calendar_spread`

---

## 11. Charts (`/chart`)

ASCII terminal charts and interactive HTML charts with technical indicators.

```
/chart RELIANCE              # ASCII candlestick (3mo, candles + volume + RSI)
/chart NIFTY 1y              # 1-year ASCII chart
/chart NIFTY 6mo rsi macd    # Custom timeframe + indicator selection
/chart RELIANCE --html       # Interactive HTML chart (opens in browser)
/chart NIFTY 1y --html       # 1-year interactive HTML chart
/chart BANKNIFTY 6mo --html
```

**Timeframes:** `1d` · `5d` · `1mo` · `3mo` (default) · `6mo` · `1y` · `2y`

**ASCII indicators:** `volume` · `rsi` · `macd` (default: volume + rsi)

**HTML chart includes:** Candlestick + EMA 20/50/200 + Bollinger Bands + Volume + RSI + MACD panels (interactive, Plotly-based)

After rendering, the agent automatically provides a technical summary of the chart (trend direction, key levels, RSI, MACD status).

---

## 12. Deep Search Engine (`/search`)

Parallel deep research across **11 verticals** — NSE, BSE, web portals, social media.

```
/search RELIANCE              # Full 11-vertical deep dive
/search RELIANCE announcements # NSE corporate announcements
/search RELIANCE dividend      # Dividends / corporate actions / ex-dates
/search RELIANCE insider       # Insider & promoter trade disclosures
/search RELIANCE shareholding  # Promoter/FII/DII/pledge trend
/search RELIANCE analyst       # Analyst targets & brokerage recommendations
/search RELIANCE broker        # Broker research reports & price targets
/search RELIANCE mf            # Mutual fund & institutional holdings
/search RELIANCE concall       # Concall transcripts & management commentary
/search RELIANCE news          # 6-portal sector news pulse
/search RELIANCE social        # Retail buzz: Reddit, Valuepickr, Traderji
/search TATACONSUM deep        # Alias for full 11-vertical search
```

**11 Search Verticals:** `announcements` · `corporate_actions` · `insider_trades` · `bse_filings` · `shareholding` · `analyst_coverage` · `broker_research` · `mf_holdings` · `concalls` · `sector_news` · `social_buzz`

---

## 13. Document & Stock Analysis (`/analyze`)

Auto-detects input type and routes appropriately.

```
/analyze report.pdf                     # Summarize a local PDF
/analyze ~/Downloads/concall.pdf        # Concall transcript PDF analysis
/analyze annual_report.docx             # Extract and summarize a Word document
/analyze https://example.com            # Scrape and analyze a web page
/analyze https://bseindia.com/result.pdf # Read a web-hosted PDF
/analyze RELIANCE                       # Full 360° stock analysis
/analyze TCS                            # 360° analysis: technical + fundamental + forensic + news + sentiment
```

**For documents:** Summary · Key Findings · Critical Details · Analysis & Opinion; for financial docs adds revenue/profit trends, management commentary, guidance, risk factors.

**For stocks (360° analysis):** Executes 6 tools in sequence:
1. `get_technical_setup` — trend, RSI, MACD, support/resistance, stage
2. `comprehensive_stock_research` — fundamentals, valuations, peer comparison
3. `run_forensic_analysis` — Beneish M-score, Piotroski F-score, Altman Z'-score
4. `search_latest_catalysts` — latest news with sentiment
5. `get_sector_context` — sector rotation and relative strength
6. `deep_search` — shareholding, insider trades, analyst targets

**Output sections:** Executive Summary · Technical Position · Fundamental Quality · Financial Health · Institutional & Insider Activity · News & Sentiment · Risk Factors · Investment Verdict (BUY/HOLD/AVOID with entry zone, target, SL, timeframe)

---

## 14. CANSLIM Analysis (`/canslim`)

Full evaluation of William O'Neil's 7-point growth stock quality framework.

```
/canslim RELIANCE
/canslim TCS
/canslim TATAMOTORS
```

**7 Criteria evaluated (each rated ✅ / 🟡 / ❌):**

| Criterion | What's Checked |
|-----------|---------------|
| **C** — Current Quarterly Earnings | Latest quarter EPS growth ≥ 25% YoY, acceleration vs prior quarters, top-line confirmation |
| **A** — Annual Earnings Growth | Annual EPS growth ≥ 25% for 3+ years, ROE ≥ 17%, stable/improving margins |
| **N** — New Products/Management/Highs | New launches, pivots, management changes; proximity to 52W/all-time high |
| **S** — Supply & Demand | Shares outstanding, volume pattern (up-day vs down-day), float tightness (promoter %) |
| **L** — Leader or Laggard | RS rank vs Nifty 500 (top 20% = leader), sector outperformance, Stage 2 |
| **I** — Institutional Sponsorship | FII/DII/MF stake changes over 2–3 quarters, bulk/block deals |
| **M** — Market Direction | Current regime (BULL/ROTATION/CHOP/BEAR), Nifty trend and breadth |

**Output:** Score card → Overall Score (X/7) → Verdict (STRONG BUY ≥ 6 / BUY 5–5.5 / HOLD 4–4.5 / AVOID < 4) → Entry zone, target, stop-loss (if BUY).

---

## 15. Forensic Accounting (`/forensic`)

Quantitative accounting quality screening using three academic models.

```
/forensic RELIANCE              # Single stock forensic analysis
/forensic TCS INFY WIPRO        # Multi-stock forensic screen (ranked by risk)
```

**Three Models:**

| Model | Threshold | What it detects |
|-------|-----------|----------------|
| **Beneish M-score** | M > −1.78 = manipulation risk | 8-variable probit model for earnings manipulation |
| **Piotroski F-score** | 7+ = strong · 0–3 = weak | 9-signal financial health score |
| **Altman Z'-score** | Z' < 1.1 = distress zone | Bankruptcy prediction (emerging-market version) |

**Output:** Per-model score + flag explanation + overall risk verdict + actionable insights.

---

## 16. Event Calendar (`/events`)

Corporate event calendar sourced from NSE.

```
/events                         # NIFTY 50 upcoming events (next 14 days)
/events NIFTY 50                # Index-wide: dividends, splits, results, AGMs, board meetings
/events NIFTY 500 30            # Extend window to 30 days
/events RELIANCE                # Specific stock events
/events HDFCBANK 21             # Specific stock, 21-day window
```

**Event types:** Dividend ex-dates · Quarterly results · Board meetings · AGMs · Bonus issues · Stock splits

Events within the next 7 days are highlighted separately. Includes days-until countdown.

---

## 17. Seasonal Heat Calendar (`/heat`)

Sector seasonal analysis based on historical monthly returns.

```
/heat                   # Current month signals for all sectors
/heat 3                 # Signals for March (month number)
/heat 5                 # Signals for May
```

**Renders two tables:**
1. **Current-month signals table** — each sector rated TAILWIND 🟢 / NEUTRAL ⚪ / HEADWIND 🔴 with avg monthly return
2. **12-Month Heatmap** — all sectors × 12 months with colour-coded avg returns

Followed by LLM narrative: which sectors to rotate into/underweight and alignment with current market environment.

---

## 18. Economic Cycle (`/cycle`)

Identifies the current phase of the economic cycle and generates sector rotation strategy.

```
/cycle
```

**Output:**
- **Cycle Phase:** `EARLY_EXPANSION` / `LATE_EXPANSION` / `SLOWDOWN` / `RECOVERY` (with confidence %)
- **Preferred sectors** (overweight) and **Avoid sectors** (underweight)
- **Macro Snapshot table:** per-indicator signal, value, and direction (GDP, rates, inflation, yield curve, etc.)
- **LLM narrative:** what to buy, what to trim, 2 stock ideas in preferred sectors

---

## 19. Scenario Engine (`/scenario`)

What-if price scenario analysis for any stock.

```
/scenario RELIANCE              # Automatic scenarios (bear / support / neutral / resistance / bull)
/scenario TCS 3200 3500 3800    # Custom price scenarios
```

**Output:**
- Current price · Stage · RSI
- Key levels: Support / Resistance / 50-DMA / 200-DMA
- Scenario table: Label · Price · % Change · RSI estimate · Stage Implication · Notes
- LLM commentary: where to set stop-loss, most likely scenario, risk/reward at current entry

---

## 20. Portfolio Narratives (`/narrative`)

Bull/bear thesis and action hints for portfolio holdings.

```
/narrative                      # All portfolio holdings (from holdings.csv)
/narrative TCS INFY             # Specific stocks
/narrative RELIANCE HDFCBANK SBIN
```

**Per stock output:** Stage · RSI · Action hint (Hold/Add/Avoid/Exit with colour coding) · Bull thesis ▲ · Bear case ▼ · Active signals

---

## 21. Concall NLP (`/concall`)

Natural language processing of earnings call transcripts.

```
/concall TCS
/concall RELIANCE
/concall INFY
```

**Output:**
- **Sentiment:** Bullish / Neutral / Bearish (with tone score)
- **Guidance:** Management forward guidance summary
- **Key themes:** Top discussion topics
- **Risk flags:** ⚠ Red-flag statements
- **Key quotes:** Top 3 verbatim management quotes
- LLM trading implication based on tone

---

## 22. Voice Briefing (`/voice`)

Generates an MP3 audio market briefing using OpenAI Text-to-Speech.

```
/voice                          # Generate daily market briefing audio
/voice "NIFTY technical setup and key levels"   # Custom text to speech
```

**Requires:** `OPENAI_API_KEY` in `.env`  
**Output:** Audio file path · Duration estimate · Voice used · Play command

---

## 23. Portfolio P&L (`/pnl`)

Live unrealised profit/loss dashboard for your portfolio.

```
/pnl
```

**Reads from:** `holdings.csv` (your portfolio positions)

**Table columns:** Symbol · Qty · Avg Cost · LTP (live price) · Current Value · P&L ₹ · P&L% · Day Change%

**Footer:** Total Invested · Total Current · Total P&L (₹ and %) · Day P&L

Profit/loss colour-coded green/red per configured theme. Followed by LLM portfolio health commentary and rebalancing suggestions.

---

## 24. US / Global Markets (`/us`, `/global`)

Deterministic US/global market data with India read-through mapping.

```
/us                             # US market summary (indices + sectors + stage2 + VCP)
/us indices                     # US index tape: SPY, QQQ, Nasdaq, Dow, Russell, VIX
/us sectors                     # US sector ETF rotation (XLK, XLF, XLE, XLY…)
/us stage2                      # US Stage 2 leaders
/us vcp                         # US VCP setups
/us stock NVDA                  # Specific US stock technical context
/global                         # Global risk regime assessment + India read-through
/global readthrough             # US/global signals mapped to NSE sector implications
```

**Output includes:**
- Global regime classification
- Index tape table (Close, 1D%, 1M%, RSI, SMA, MACD, Stage, 52W%)
- Sector rotation snapshot (1M%, 3M%, RS vs SPY, rotation score)
- Stage 2 leaders list
- VCP setups list
- Risk/regime signals
- Technical takeaways (strongest index, SMA/MACD breadth, VIX reading)
- **India Read-Through:** per NSE sector — stance (BUY/WATCH/AVOID) + relevant symbols + confidence

---

## 25. Report Generation (`/report`)

Generates formatted reports in HTML, PDF, or Markdown.

```
/report                             # Show usage
/report RELIANCE                    # Quick research report (default: research, html)
/report technical RELIANCE          # Technical analysis report
/report fundamental TCS pdf         # Fundamental report as PDF
/report forensic INFY md            # Forensic accounting report as Markdown
/report research HDFCBANK           # Comprehensive 360° research report
/report intraday SBIN               # Intraday analysis report
/report canslim TATAMOTORS html     # CANSLIM quality report
/report ric ADANIENT pdf            # RIC investigation report as PDF
/report sector IT                   # Sector analysis report
```

**Report types:** `technical` · `fundamental` · `forensic` · `research` · `intraday` · `canslim` · `ric` · `sector`

**Output formats:** `html` (default, opens in browser) · `pdf` · `md`

---

## 26. RIC — Recursive Investigative Conversations (`/ric`)

**Pre-built multi-step analysis recipes** that chain agent queries automatically, each step building on the previous result.

```
/ric                                    # Show all 8 RICs
/ric sherlock RELIANCE                  # 5-step stock investigation
/ric sector-xray IT                     # 4-step sector deep dive
/ric breakout-hunter                    # 5-step breakout hunt (no symbol needed)
/ric earnings-playbook TCS              # 5-step earnings analysis
/ric index-pulse NIFTY BANK             # 4-step index analysis
/ric peer-battle TCS,INFY,WIPRO         # 4-step head-to-head comparison
/ric risk-radar                         # 4-step risk assessment (no symbol needed)
/ric morning-intel                      # 5-step pre-market intelligence (no symbol needed)
```

**8 Available RICs:**

| RIC | Steps | What it does |
|-----|-------|-------------|
| 🔍 **sherlock** `SYMBOL` | 5 | Live quote → technicals → fundamentals → news → intraday trade setup |
| 🏭 **sector-xray** `SECTOR` | 4 | Sector breadth → leaders → laggards → entry opportunities |
| 🎯 **breakout-hunter** | 5 | Market conditions → Stage 2 screener → high RS → VCP scan → final picks |
| 📋 **earnings-playbook** `SYMBOL` | 5 | Latest results → ratios → peers → concall → post-earnings setup |
| 📊 **index-pulse** `INDEX` | 4 | Index technicals → breadth & flow → top stocks → intraday levels |
| ⚔️ **peer-battle** `SYM,SYM,...` | 4 | Fundamental battle → technical battle → news/sentiment → verdict |
| ⚠️ **risk-radar** | 4 | Macro environment → institutional flow → breadth extremes → vulnerable stocks |
| ☀️ **morning-intel** | 5 | Global overnight → yesterday recap → current breadth → FII/DII → watchlist |

> **Note:** `sector-xray` auto-routes to `index-pulse` if the argument looks like an index (e.g., `NIFTY BANK`).

---

## 27. Data Refresh (`/refresh`)

Triggers the `daily_refresh.py` pipeline as a background subprocess. Logs to `data/refresh.log`.

```
/refresh                    # Fast snapshot (skip analysis, ~1–2 min)
/refresh snapshot           # Same as above (explicit)
/refresh live               # Live prices only (~30s)
/refresh full               # Full pipeline: R bhavcopy + analysis + snapshot (~10–15 min)
/refresh analysis           # Analysis + snapshot (skips aux data fetch)
/refresh status             # Check if refresh is running (shows PID)
/refresh stop               # Terminate a running refresh
```

Background thread monitors completion and prints a `✅`/`❌` notification with exit code.

---

## 28. Session Export (`/export`)

Exports the current conversation session to a file and opens it in the browser.

```
/export                     # Export as HTML (default)
/export html                # Export session as HTML file
/export pdf                 # Export session as PDF (requires weasyprint or pdfkit)
/export RELIANCE html       # Export with a symbol label in the filename
```

---

## 29. Appearance (`/theme`, `/scale`)

### Color Themes

```
/theme                      # List all available themes (with colour swatches)
/theme dark                 # Dark theme (default)
/theme dracula              # Dracula theme
/theme solarized            # Solarized Dark theme
/theme high-contrast        # High Contrast theme
/theme nord                 # Nord theme
```

### Layout Scale

Controls chart dimensions and table density.

```
/scale                      # List available scales
/scale compact              # Compact layout (small terminals)
/scale normal               # Normal layout (default)
/scale large                # Large layout (wide terminals / big screens)
```

---

## 30. Session Management

```
/context                    # Show conversation history table + context budget bar
/new                        # Start a fresh session (clears all history)
/reset                      # Same as /new
/clear                      # Clear screen, re-render banner (keeps history)
cls / clear                 # Same as /clear
exit / quit / q / :q        # Exit Agent Adda
Ctrl-C                      # Skip current input (do not exit)
```

**Context budget:** Visual progress bar showing characters used vs budget. Displays per-turn summary (what you asked / what agent replied). History is auto-trimmed when the budget is full.

---

## 31. Follow-up Suggestions

After every agent response, up to 3 follow-up questions are suggested:

```
1      # Ask follow-up question 1
2      # Ask follow-up question 2
3      # Ask follow-up question 3
```

Follow-ups can be slash commands (e.g. `` `/forensic RELIANCE` — check for manipulation risk ``) or natural language prompts. Typing `1`, `2`, or `3` routes them appropriately.

---

## 32. Autocomplete & Command Discovery

**Three-tier tab completion:**

| Tier | Trigger | Completes |
|------|---------|----------|
| 1 | `/` | All slash commands with inline description hint |
| 2 | `p` + digits | Prompt library entries (e.g. `p7` → `p7  NIFTY 50 Technicals`) |
| 3 | 2+ letters | Starter phrases + known NSE symbols / index names |

**Command browser:**

```
/commands                   # Browse all commands grouped by category
/commands alert             # Filter by keyword (e.g. 'pdf', 'fno', 'monitor')
/help                       # Full help panel (all commands, all sections)
/help charts                # Help: charts section
/help screens               # Help: EOD screeners
/help scan                  # Help: intraday scanner
/help fno                   # Help: F&O / options
/help search                # Help: deep search engine
/help forensic              # Help: forensic accounting
/help monitors              # Help: background monitors & alerts
/help ric                   # Help: recursive investigations
/help refresh               # Help: data refresh
/help appearance            # Help: themes & scale
/help macro                 # Help: seasonal & macro
```

---

## 33. CLI Arguments

```
python nse_agent.py [OPTIONS]

Options:
  -q, --query TEXT       Single query (non-interactive mode)
  -t, --trace            Show tool execution trace after every response
  -m, --mode MODE        Default data mode: auto | intraday | historical (default: auto)
  -nb, --no-briefing     Skip the startup market briefing
  --theme THEME          Start with theme: dark | dracula | solarized | high-contrast | nord
  --scale SCALE          Start with scale: compact | normal | large
```

---

## 34. Architecture & Tech Stack

### UI Layer
| Library | Role |
|---------|------|
| `prompt_toolkit` | Persistent input bar, history, tab completion, auto-suggest |
| `rich` | Markdown rendering, tables, panels, rules, progress bars |
| `colorama` | Banner colouring, ANSI support |

### Agent Backend (`terminal/agent.py`)
- Receives `query` → routes to tools → returns `{answer, backend, catalysts, comparison, trace}`
- Maintains conversation history with configurable character budget and max-turn limit
- Supports multiple backends (OpenAI, Ollama, rule-based keyword fallback)

### Tool Modules (`terminal/`)
| Module | Capabilities |
|--------|-------------|
| `intraday.py` | Live NSE quotes, intraday OHLCV, scanning |
| `alerts.py` | Price/RSI alert CRUD, live checking |
| `monitor.py` | Background strategy workers, alert queue |
| `charts.py` | ASCII chart rendering, HTML chart generation (Plotly) |
| `fno_data.py` | Options chain, OI analysis, strategy builder |
| `forensics.py` | Beneish M-score, Piotroski F-score, Altman Z'-score |
| `search_engine.py` | 11-vertical deep search (NSE/BSE/web/social) |
| `web_research.py` | Web scraping, news aggregation |
| `portfolio_pnl.py` | Holdings CSV → live P&L computation |
| `export.py` | Session → HTML/PDF export |
| `theme.py` | Color theme and layout scale management |
| `help.py` | Modular help sections |
| `tools.py` | Seasonal heat calendar, economic cycle, scenario engine, narratives, concall NLP, voice briefing |

### LLM / AI
| Component | Role |
|-----------|------|
| OpenAI GPT-4o-mini | Alert natural-language parsing |
| OpenAI TTS | Voice briefing generation |
| Agent backend (OpenAI/Ollama) | All research queries, narrative generation |
| `global_market_intelligence.py` | US/global data loader and report builder |

### Data Sources
- **NSE live API** — real-time quotes, options chain, market breadth
- **SQLite DB** (`nse_analysis.db`, `sector_rotation_tracker.db`) — EOD snapshots
- **CSV files** — historical price data, FII/DII flows, screener output
- **screener.in** — fundamentals, concall transcripts
- **Web search** — DuckDuckGo, Google, financial portals (MoneyControl, ET, BSE)
- **Yahoo Finance** — US/global market data
