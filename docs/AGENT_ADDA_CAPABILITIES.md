# NSE Agent Adda — Complete Command & Feature Reference

## OVERVIEW
**Agent Adda** is an interactive NSE market research terminal with 150+ slash commands across market research, screening, search, portfolio, voice, company intelligence, and EOD strategy backtesting modules. It supports 3 operating modes and features background monitoring, deep search, forensic analysis, options chains, RIC investigations, report generation, company website indexing, PostgreSQL-backed Strategy Lab persistence, and more.

---

## DELIBERATION ENGINE

`terminal/deliberation/` separates agent reasoning into testable components:

| Module | Role |
|--------|------|
| `planner.py` | Plan-of-thought conversion from user query to executable tool tasks |
| `hypothesis.py` | Tree-of-thought competing market or symbol hypotheses |
| `evaluator.py` | Evidence scoring, freshness labeling, and missing-data capture |
| `simulator.py` | Scenario and strategy implication simulation |
| `memory.py` | In-session watchlist and thesis memory primitives |
| `renderer.py` | Persona-specific final answer rendering from plans and evidence |

Placeholder requests such as `/assess SYMBOL` now stop safely and ask for a real NSE symbol instead of fabricating a market brief from missing evidence.

---

## I. OPERATING MODES (Global State)

### Mode Commands
| Command | Alias | Description | Backend |
|---------|-------|-------------|---------|
| `/live` | `/l`, `/intraday` | Force LIVE mode — real-time NSE API | Live market data |
| `/eod` | `/h`, `/historical` | Force EOD mode — historical CSV + DB snapshot | Database + CSV |
| `/auto` | `/a` | AUTO mode (default) — keyword-based detection | Hybrid |

**Mode Tag Display**: Shown in bottom prompt bar
- `[LIVE🔴]` = Intraday (red, bright)
- `[EOD📚]` = Historical (blue, bright)
- `[AUTO]` = Auto-detect (white, dim)

---

## II. MAIN COMMAND CATEGORIES & SLASH COMMANDS

### A. PROMPT LIBRARY 📋 (60+ Curated Research Prompts)
**Shorthand**: `/prompts`, `/p`

| Command | Arguments | What It Does |
|---------|-----------|------------|
| `/prompts` | (none) | Browse all 60 prompts in 10 categories |
| `/prompts market` | market | Filter to Market Overview prompts (NIFTY, breadth, FII/DII) |
| `/prompts intraday` | intraday | Intraday Trading prompts (ORB, gap-go, MACD, RSI, VCP, momentum) |
| `/prompts technical` | technical | Technical Analysis (Stage 2, supertrend, ADX, high RS, 52W breakouts) |
| `/prompts sector` | sector | Sector Analysis (IT, Banking, Pharma, rotation, RS) |
| `/prompts screener` | screener | Screener & Filters (Stage2, breakouts, high RS, momentum, recovery) |
| `/prompts fundamentals` | fundamentals | Fundamentals & Valuation (P/E, P/B, ROE, ROCE, concalls, peer comp) |
| `/prompts stock` | stock | Stock Deep Dive (RELIANCE, INFOSYS, ZOMATO, SBI analysis) |
| `/prompts news` | news | News & Catalysts (top news, results, FII deals, macro events) |
| `/prompts portfolio` | portfolio | Portfolio (exposure, stage distribution, holdings health) |
| `/prompts global` | global | Global & Macro (US markets, USD/INR, crude, FII position, emerging mkts) |
| `p<number>` | 1–60 | Quick shortcut to run a specific prompt (e.g., `p7`, `p42`) |

**Library Structure**: 60 prompts across 10 categories, each with (title, query description). Organized in flat index for O(1) lookup.

---

### A2. CURRENT MARKET DASHBOARD 📊 (`/dashboard`)

Stock-market-TV dashboard that consolidates live NSE tape, animated ticker, sharp rise/fall alerts, sectoral heatmap, F&O positioning, RS screener leaders, intraday view, preset alert/screen ideas, top gainers/losers, FII/DII flows, global read-through, catalyst headlines, and an LLM narrative with deterministic fallback. In the terminal it opens as a compact full-screen live view: ticker/pulse animates every second, live data refreshes every 60 seconds, and `Ctrl+C` exits.

| Command | Alias | What It Shows |
|---------|-------|---------------|
| `/dashboard` | `/dash` | Auto-refreshing stock-market-TV dashboard + narrative |
| `/dashboard banks` | `/dash banks` | Same live dashboard with a user-specified focus note |

Dashboard sections: Live Ticker, Market Tape, Sharp Moves, Sectoral Heatmap, Breadth/Flows/Global, Index Leadership, Top Gainers/Top Losers, F&O, RS Screener, Intraday View, Preset Alerts/Screens, News Now, and LLM Narrative.

---

### B. RIC LIBRARY — Recursive Investigative Conversations 🔬 (8 Multi-Step Recipes)

**Shorthand**: `/ric [name] [SYMBOL|SECTOR|INDEX]`

RICs are pre-built multi-step analysis flows where each step feeds context to the next.

| RIC Name | Command | Steps | Arguments | Example |
|----------|---------|-------|-----------|---------|
| **Sherlock** | `/ric sherlock` | 5 | SYMBOL | `/ric sherlock RELIANCE` |
| **Sector X-Ray** | `/ric sector-xray` | 4 | SECTOR or INDEX | `/ric sector-xray IT` |
| **Breakout Hunter** | `/ric breakout-hunter` | 5 | (none) | `/ric breakout-hunter` |
| **Earnings Playbook** | `/ric earnings-playbook` | 5 | SYMBOL | `/ric earnings-playbook TCS` |
| **Index Pulse** | `/ric index-pulse` | 4 | INDEX | `/ric index-pulse NIFTY BANK` |
| **Peer Battle** | `/ric peer-battle` | 4 | SYMBOLS (comma-sep) | `/ric peer-battle TCS,INFY,WIPRO` |
| **Risk Radar** | `/ric risk-radar` | 4 | (none) | `/ric risk-radar` |
| **Morning Intel** | `/ric morning-intel` | 5 | (none) | `/ric morning-intel` |

**RIC Step Details**:

1. **Sherlock** (5 steps):
   - Live Quote → Technical Setup → Fundamentals → News & Catalysts → Trade Setup

2. **Sector X-Ray** (4 steps):
   - Sector Overview → Leaders → Laggards & Risks → Entry Opportunities

3. **Breakout Hunter** (5 steps):
   - Market Conditions → Stage 2 Universe → High RS Leaders → VCP Scan → Final Picks

4. **Earnings Playbook** (5 steps):
   - Latest Results → Financial Ratios → Peer Comparison → Management Commentary → Post-Earnings Setup

5. **Index Pulse** (4 steps):
   - Index Technicals → Breadth & Flow → Top Stocks → Intraday Levels

6. **Peer Battle** (4 steps):
   - Fundamental Battle → Technical Battle → News & Sentiment → Verdict

7. **Risk Radar** (4 steps):
   - Macro Environment → Institutional Flow → Breadth Extremes → Vulnerable Stocks

8. **Morning Intel** (5 steps):
   - Global Overnight → Yesterday Recap → Current Breadth → FII/DII Today → Today's Watchlist

---

### C. INTRADAY SCANNER ⚡ (`/scan` & `/scan` aliases)

**Shorthand**: `/scan [INDEX|STRATEGY]`

Scans NIFTY 50 or specified index for intraday signals on 15m charts.

| Command | Argument | Screen Type | What It Scans |
|---------|----------|------------|---------------|
| `/scan` | (none) | all strategies | NIFTY 50 on 15m (all strategies) |
| `/scan NIFTY BANK` | index name | all strategies | NIFTY BANK on 15m |
| `/scan NIFTY IT` | index name | all strategies | NIFTY IT on 15m |
| `/scan NIFTY MIDCAP 100` | index name | all strategies | NIFTY MIDCAP 100 on 15m |
| `/scan NIFTY PHARMA` | index name | all strategies | NIFTY PHARMA on 15m |
| `/scan orb` | orb | Opening Range Breakout | First 15–30m range + volume + continuation |
| `/scan gap` | gap | Gap & Go | Gapping stocks with MACD continuation |
| `/scan macd` | macd | MACD Crossover | Fresh MACD signal line cross |
| `/scan rsi` | rsi | RSI Divergence | RSI extreme + Bollinger mean-reversion |
| `/scan bb` | bb | Bollinger Squeeze | Low-volatility squeeze breakout |
| `/scan vwap` | vwap | VWAP Reclaim | Price reclaiming/losing VWAP proxy |
| `/scan vcp` | vcp | VCP | Volatility Contraction Pattern intraday |
| `/scan momentum` | momentum | Momentum | MACD + RSI + Supertrend aligned |

---

### D. EOD SCREENERS 🔍 (`/screen` shortcuts)

**Shorthand**: `/screen [SCREENER_TYPE]`

Runs daily EOD/historical screeners with Weinstein stage analysis.

| Command | Screener | Criteria | Output |
|---------|----------|----------|--------|
| `/screen stage2` | stage2 | Stage 2 uptrend stocks | Advancing, RS ≥ 0.8, technical score high |
| `/screen newhighs` | new_highs | Companies creating new highs | Latest close within 5% of computed 52-week high |
| `/screen momentum` | momentum_52w | Near-52W-high momentum leaders | RS ≥ 1.0, within 5% of 52W high |
| `/screen highrs` | high_rs | Top RS ≥ 1.15 market leaders | Strongest relative strength |
| `/screen turnaround` | turnaround | Turnaround recovery setups | Stage 1→2 transition, dip reversals |
| `/screen base` | stage1_base | Stage 1 basing/coiling stocks | Low volatility consolidation, building RS |
| `/screen tight` | tight_range | Tight weekly range (VCP-like) | Weekly consolidation patterns |
| `/screen dip` | oversold_bounce | Oversold bounce in Stage 2 | RSI < 40, Stage 2 context |
| `/screen supertrend` | supertrend_buy | Supertrend BUY state | Active Supertrend buy signals |
| `/screen strong` | strong_buy | STRONG_BUY trading signals | Highest-conviction signals |
| `/screen new` | new_entrants | New Stage 2 entrants (14d) | Recent Stage 2 breakouts (14-day window) |

---

### E. EOD STRATEGY LAB + BACKTESTING 🧪 (`/backtest`, `/strategy-lab`)

**Shorthand**: `/backtest [list|run|report]`, `/strategy-lab validate`

EOD Strategy Lab is the deterministic backtesting layer for research and learning. It validates local EOD data freshness, runs bounded strategy simulations, computes next-open entries and exits, and can persist completed runs to PostgreSQL for later reporting.

| Command | Status | What It Does |
|---------|--------|--------------|
| `/backtest list` | Available | Lists registered EOD strategies, families, status, and descriptions |
| `/strategy-lab validate` | Available | Checks EOD data readiness, latest date, symbol count, blockers, warnings, and available modes |
| `/backtest run stage2 --data data.csv --capital 100000` | Available | Runs Stage 2 on a supplied CSV fixture or custom EOD dataset |
| `/backtest run stage2 --symbol DMART --from 2024-01-01 --capital 100000` | Available | Runs Stage 2 on real `data/nse_sec_full_data.csv` for one symbol |
| `/backtest run stage2 --symbol DMART --from 2024-01-01 --capital 100000 --persist` | Available | Runs Stage 2 and persists run, trades, and metrics to PostgreSQL |
| `/backtest run stage2 --max-symbols 25 --from 2024-01-01` | Available | Runs a bounded multi-symbol EOD simulation |
| `/backtest report latest` | Available | Reads the latest persisted PostgreSQL run and renders summary metrics plus trades |
| `/backtest run stage2` | Guarded | Refuses unbounded all-universe execution unless `--symbol` or `--max-symbols` is supplied |

#### Registered Strategies

| Strategy ID | Family | Execution Status | Notes |
|-------------|--------|------------------|-------|
| `stage2` | Trend / Weinstein | Executable | Uses SMA50/SMA150/SMA200, 52-week context, relative-strength proxy, next-open execution |
| `canslim` | Growth / CANSLIM | Registered | Planned composite of earnings, sales, RS, leadership, sponsorship, and market direction |
| `minervini` | Trend Template | Registered | Planned Minervini trend-template implementation |
| `supertrend_continuation` | Trend Following | Registered | Planned Supertrend continuation backtest |
| `rsi_pullback_stage2` | Pullback | Registered | Planned RSI pullback strategy inside Stage 2 context |
| `52w_high` | Momentum Breakout | Registered | Planned 52-week high breakout strategy |
| `vcp` | Pattern / Minervini | Registered, detector foundation available | VCP feature detection exists; strategy execution still needs full signal policy |
| `darvas` | Box Breakout | Registered | Planned Darvas box strategy |
| `bollinger_squeeze` | Volatility Breakout | Registered | Planned squeeze breakout strategy |
| `head_shoulders` | Chart Pattern | Experimental | Pattern research backlog |
| `inverse_head_shoulders` | Chart Pattern | Experimental | Pattern research backlog |
| `cup_handle` | Chart Pattern | Experimental | Pattern research backlog |

#### Data, Execution, and Storage Model

- **Primary EOD source**: `data/nse_sec_full_data.csv`
- **Readiness check**: `backtesting.data.inspect_backtest_data()` scans the full file for latest EOD date, symbol count, required columns, blockers, warnings, and modes such as `technical-only`, `technical`, and `fundamental-aware`.
- **Feature engineering**: `backtesting.engine.compute_stage2_features()` normalizes NSE columns such as `TIMESTAMP` → `date` and `TOTTRDQTY` → `volume`, then computes SMA50/SMA150/SMA200, 52-week high, relative-strength proxy, and Stage 2 state.
- **Execution policy**: deterministic EOD simulation with next-open entries/exits and no-lookahead tests.
- **Portfolio sizing**: allocation-based sizing through `backtesting.portfolio.size_position()`.
- **PostgreSQL persistence**: `backtesting.storage` creates and writes to the `backtesting` schema with `strategy_definitions`, `backtest_runs`, `backtest_trades`, `backtest_metrics`, and `backtest_skipped_candidates`.
- **Connection string**: uses `AGENT_ADDA_PG_DSN`, then `PG_DSN`, then default `dbname=nse_market user=nse_admin host=/tmp`.

#### Current Smoke-Test Baseline

The Stage 2 implementation has been smoke-tested against DMART using real EOD data:

| Test Command | Result |
|--------------|--------|
| `/backtest run stage2 --symbol DMART --from 2024-01-01 --capital 100000` | 1 trade, 4.83% total return, ₹4,830 total P&L |
| `/backtest run stage2 --symbol DMART --from 2024-01-01 --capital 100000 --persist` | Persisted to PostgreSQL run id `2` in local test environment |
| `/backtest report latest` | Rendered persisted run summary and trade table from PostgreSQL |

**Important**: Strategy Lab output is for research, testing, and learning. It is not investment advice and should not be used without independent validation of data freshness, survivorship bias, slippage, liquidity, transaction costs, and corporate actions.

---

### E2. STRATEGY COUNCIL SIMULATION 🧠🧪 (`/strategy-council`)

The Strategy Council is an iterative EOD research simulator. A strategist proposes stock-specific strategies, deterministic tools backtest train/validation data, two critics challenge data leakage and risk, the strategist revises for 2-3 iterations, and a final locked strategy is tested once on the held-out test split.

| Command | What It Does |
|---|---|
| `/strategy-council DMART` | Run default 1w/2w/4w Strategy Council simulation |
| `/strategy-council DMART --iterations 3` | Run three strategist/critic revision loops |
| `/strategy-council DMART --horizon 1w,2w,4w` | Explicit horizons |
| `/strategy-council DMART --from 2022-01-01 --test-from 2026-01-01` | Explicit time split |
| `/strategy-council DMART --strategies stage2,vcp` | Restrict candidate strategy families |
| `/strategy-council DMART --llm` | Use configured LLM strategist and critic adapters, with deterministic fallback if unavailable |
| `/strategy-council DMART --persist` | Store the run, iterations, candidates, critiques, split results, final recommendation, and report path in PostgreSQL |

#### Strategy Council Loop

1. Evidence pack: latest EOD technical context and explicit missing-data labels.
2. Strategist: proposes bounded strategy candidates.
3. POT compiler: converts candidates into constrained `StrategySpec` rules.
4. Deterministic runner: backtests train and validation slices.
5. Critics: data/leakage critic plus market/risk critic challenge the results.
6. Revision: strategist receives critic feedback and reruns for the configured iteration count.
7. Final lock: best validation candidate is locked, then tested once on held-out test data.
8. Report: Markdown audit trail is written under `reports/strategy_council/`.
9. Optional persistence: `--persist` writes the audit trail to the PostgreSQL `strategy_council` schema.

Guardrails:
- Test data is hidden until the final strategy is locked.
- LLM adapters can propose and critique with `--llm`; deterministic tools always calculate metrics.
- Missing evidence is shown explicitly.
- Output is research-only and not investment advice.

---

### F. BACKGROUND MONITORS 👁️ (`/monitor` command suite)

**Shorthand**: `/monitor [sub] [strategy] [index] [interval] [direction]`

Auto-running background alert workers that scan at regular intervals and queue alerts.

#### Monitor Subcommands

| Subcommand | Syntax | What It Does |
|-----------|--------|------------|
| `/monitor` | `/monitor` or `/monitor results` | Show active monitors plus queued/recent scan results |
| `/monitor list` | `/monitor list` | Show all 14 available strategies |
| `/monitor status` | `/monitor status` | Show status of all running monitors |
| `/monitor start` | `/monitor start STRATEGY [INDEX] [INTERVAL_MIN] [buy\|sell\|all]` | Start a background monitor |
| `/monitor STRATEGY` | `/monitor STRATEGY [INDEX] [INTERVAL_MIN] [buy\|sell\|all]` | Shorthand for `/monitor start STRATEGY ...` |
| `/monitor stop` | `/monitor stop STRATEGY` or `/monitor stop all` | Stop one or all monitors |

#### Available Monitor Strategies (14 Total)

| Strategy | Scan Type | What It Detects |
|----------|-----------|-----------------|
| `breakout` | EMA + volume | Price breakout with volume confirmation |
| `volume_surge` | Volume spike | 2x+ volume spikes with price confirmation |
| `reversal` | RSI + Bollinger | RSI/Bollinger reversal signals |
| `momentum` | MACD + RSI | MACD + RSI momentum alignment |
| `supertrend` | Supertrend | Supertrend flip (buy/sell crossover) |
| `vcp` | Contraction | VCP (Volatility Contraction Pattern) |
| `orb` | Opening Range | Opening Range Breakout (5m bars) |
| `gap_go` | Gap + MACD | Gap and Go with MACD continuation |
| `vwap` | VWAP | VWAP reclaim/loss alerts |
| `engulfing` | Candle pattern | Engulfing candlestick patterns |
| `ema_ribbon` | EMA alignment | EMA Ribbon alignment (all bullish/bearish) |
| `multi_confirm` | Confluence | 3/4 indicators agree |
| `rsi_divergence` | RSI divergence | RSI divergence signals |
| `all` | All 13 combined | Run all strategies in parallel |

#### Monitor Usage Examples
```
/monitor start breakout NIFTY 500 15 buy        # Breakout on NIFTY 500, 15m, BUY only
/monitor                                        # Show status + latest monitor results
/monitor vcp                                    # VCP on NIFTY 500, 15m, all directions
/monitor start momentum NIFTY BANK 10            # Momentum on NIFTY BANK, 10m, all directions
/monitor start all 5 sell                        # All strategies, 5m, SELL only
/monitor stop breakout                           # Stop breakout monitor
/monitor stop all                                # Stop all monitors
```

**Auto-Display**: Alerts auto-render in terminal every 3s via background thread.

---

### G. WATCHLIST ALERTS 🔔 (`/alert` command suite)

**Shorthand**: `/alert [sub] [args]`

Manual price and RSI alerts for specific symbols. Supports natural language parsing via OpenAI.

| Subcommand | Syntax | What It Does |
|-----------|--------|------------|
| `/alert list` | `/alert list` | Show all alerts with ID, symbol, trigger, value, timeframe |
| `/alert add` | `/alert add SYMBOL TRIGGER [VALUE] [NOTE]` | Add new alert (natural language or positional) |
| `/alert del` | `/alert del ID` | Delete alert by ID |
| `/alert check` | `/alert check` | Check all alerts against live prices now |
| `/alert monitor` | `/alert monitor` | Toggle background alert monitor (polls every 5m, market hours) |

#### Alert Types

| Trigger Type | Examples | Natural Language Support |
|------------|----------|-------------------------|
| Price above | `price_above 1500` | "RELIANCE price above 1500" |
| Price below | `price_below 1400` | "RELIANCE price below 1400" |
| RSI above | `rsi_above 70` | "NIFTY rsi above 70 in 15min" |
| RSI below | `rsi_below 30` | "TCS rsi below 30" |
| Breakout above | `breakout_above 1580` | "RELIANCE breakout above 1580" |
| Breakout below | `breakout_below 1550` | "RELIANCE breakout below 1550" |
| Intraday breakout | `intraday_breakout` | "RELIANCE breakout" or "TCS ORB" |

**LLM Parser**: Uses OpenAI to parse natural language alerts with fallback to positional parsing.

**Timeframes**: `1d` (default), `15m`, `5m`, `1h`, `30m`, etc.

---

### H. F&O / OPTIONS CHAIN 📊 (`/options`, `/chain`, `/oi`, `/fno`, `/strategy`)

**Shorthand**: `/options [SYMBOL] [EXPIRY_INDEX]`

Live options chain rendering with PCR, max pain, Greeks, IV, OI analysis.

| Command | Syntax | What It Shows |
|---------|--------|--------------|
| `/options` | `/options [SYMBOL] [EXPIRY]` | Live options chain — Calls\|Strike\|Puts table |
| `/options NIFTY` | `/options NIFTY` | NIFTY options nearest expiry |
| `/options BANKNIFTY` | `/options BANKNIFTY` | BANKNIFTY options nearest expiry |
| `/options NIFTY 1` | `/options NIFTY 1` | NIFTY options next expiry (expiry index 1) |
| `/chain NIFTY` | `/chain NIFTY [EXPIRY]` | Live option chain (PCR, max pain, OI, Greeks) |
| `/oi NIFTY` | `/oi SYMBOL` | Open Interest analysis (support/resistance from OI) |
| `/fno NIFTY` | `/fno SYMBOL` | Comprehensive F&O overview (chain + futures + strategy) |
| `/strategy NIFTY long_straddle` | `/strategy SYMBOL STRATEGY_NAME` | Build specific options strategy with pricing |
| `/strategy BANKNIFTY iron_condor` | `/strategy SYMBOL iron_condor` | Iron condor on BANKNIFTY |
| `/strategy NIFTY bull_call_spread` | `/strategy SYMBOL bull_call_spread` | Bull call spread with legs and Greeks |

#### Options Chain Display
- **Format**: Side-by-side table (Calls | Strike | Puts)
- **Columns**: OI, IV%, LTP for calls; LTP, IV%, OI for puts
- **ATM Highlight**: ► Strike ◄ for at-the-money strike
- **Color Coding**: ITM strikes (calls < spot, puts > spot) bolded in green/red
- **Metadata**: PCR, Max Pain, Total Call OI, Total Put OI, Expiry date

#### Strategy Types (10)
- `long_call`, `long_put`, `bull_call_spread`, `bear_put_spread`
- `long_straddle`, `long_strangle`, `iron_condor`, `covered_call`
- `protective_put`, `calendar_spread`

---

### I. CHARTS 📈 (`/chart` command)

**Shorthand**: `/chart SYMBOL [TIMEFRAME] [--html] [INDICATORS]`

ASCII candlestick charts with volume/RSI/MACD, or interactive HTML charts.

| Command | Timeframe | Indicators | Output |
|---------|-----------|-----------|--------|
| `/chart RELIANCE` | 3mo (default) | volume, rsi | ASCII chart (terminal) |
| `/chart NIFTY 1y` | 1-year | volume, rsi | 1-year ASCII chart |
| `/chart NIFTY 6mo rsi macd` | 6mo | rsi, macd | 6-month with RSI + MACD panels |
| `/chart RELIANCE --html` | 3mo | full | Interactive HTML chart (opens browser) |
| `/chart NIFTY 1y --html` | 1-year | full | 1-year interactive HTML (opens browser) |
| `/chart BANKNIFTY 6mo --html` | 6mo | full | BANKNIFTY interactive chart |

**ASCII Indicators**: `volume`, `rsi`, `macd` (default: volume + rsi)

**HTML Features**: Candlesticks + EMA (20, 50, 200) + Bollinger Bands + volume + RSI + MACD

**Timeframes Supported**: `1d`, `5d`, `1mo`, `3mo`, `6mo`, `1y`, `2y`

---

### J. DEEP SEARCH ENGINE 🌐 (`/search` command)

**Shorthand**: `/search SYMBOL [VERTICAL|CONTEXT]`

Parallel 11-vertical deep search (NSE + BSE + web). Auto-detects vertical or forces specific ones.

#### 11 Search Verticals

| Vertical | Data Source | What It Searches |
|----------|------------|-----------------|
| `announcements` | NSE live | Corporate announcements, board meeting notices |
| `corporate_actions` | NSE live | Dividends, splits, bonuses, rights, ex-dates |
| `insider_trades` | NSE live | Insider/promoter trading disclosures |
| `shareholding` | NSE live | Shareholding pattern, FII/DII, pledges, trend |
| `analyst_coverage` | Web | Analyst targets, brokerage research reports |
| `broker_research` | Web | Broker house research, price targets, ratings |
| `mf_holdings` | Web | Mutual fund & institutional holdings |
| `concalls` | Web + screener.in | Concall transcripts, management commentary |
| `sector_news` | 6 portals | Sector news from moneycontrol, ET, ET Markets, etc. |
| `social_buzz` | Reddit, Valuepickr, Traderji | Retail investor sentiment |
| `bse_filings` | BSE | Board meeting notices, regulatory filings |

#### Search Commands

| Command | Vertical Forced | Examples |
|---------|-----------------|----------|
| `/search RELIANCE` | (none) | Full 11-vertical search |
| `/search RELIANCE dividend` | corporate_actions | Dividends, splits, bonuses |
| `/search RELIANCE insider` | insider_trades | Insider disclosures |
| `/search RELIANCE shareholding` | shareholding | Shareholding + FII/DII trend |
| `/search RELIANCE analyst` | analyst_coverage | Analyst targets + ratings |
| `/search RELIANCE broker` | broker_research | Broker research reports |
| `/search RELIANCE mf` | mf_holdings | Mutual fund holdings |
| `/search RELIANCE concall` | concalls | Concall transcripts |
| `/search RELIANCE news` | sector_news | Sector news |
| `/search RELIANCE social` | social_buzz | Reddit, Valuepickr, Traderji buzz |
| `/search TATACONSUM deep` | all 11 | Full deep search |

---

### K. DOCUMENT ANALYSIS 📄 (`/analyze` command)

**Shorthand**: `/analyze <FILE.pdf | FILE.docx | https://... | SYMBOL>`

Auto-detects input type: URL → scrape web page; .pdf/.docx → read local file; SYMBOL → full 360° stock analysis.

#### Document Analysis
- **Inputs**: PDF, DOCX, XLSX, TXT, CSV, MD files or web URLs
- **Output Format**:
  - Document Summary (topics covered)
  - Key Findings (data points, numbers, conclusions)
  - Critical Details (financials, dates, targets, risks)
  - Analysis & Opinion (expert interpretation)

#### Stock 360° Deep Analysis (when input is a symbol like `RELIANCE`)
1. **get_technical_setup** → trend, RSI, MACD, support/resistance, stage
2. **comprehensive_stock_research** → fundamentals, valuations, peer comparison
3. **run_forensic_analysis** → Beneish M-score, Piotroski F-score, Altman Z'-score
4. **search_latest_catalysts** → latest news, sentiment
5. **get_sector_context** → sector rotation, relative strength
6. **deep_search** (shareholding, insider, analyst verticals) → institutional & insider activity

**Output**: Unified report with Executive Summary, Technical, Fundamental, Forensic, News, Risk Factors, Investment Verdict.

---

### L. CANSLIM ANALYSIS 📐 (`/canslim` command)

**Shorthand**: `/canslim SYMBOL`

William O'Neil's 7-point growth stock quality evaluation framework.

#### CANSLIM Criteria

| Criterion | What It Evaluates | Grade |
|-----------|-------------------|-------|
| **C** — Current Quarterly Earnings | EPS growth ≥ 25% YoY, revenue confirmation | ✅/🟡/❌ |
| **A** — Annual Earnings Growth | EPS ≥ 25% for 3+ years, ROE ≥ 17%, stable margins | ✅/🟡/❌ |
| **N** — New Products/Management/Highs | New launches, management changes, 52W high proximity | ✅/🟡/❌ |
| **S** — Supply & Demand | Shares outstanding, volume patterns, float | ✅/🟡/❌ |
| **L** — Leader or Laggard | RS rank, sector outperformance, Stage 2 status | ✅/🟡/❌ |
| **I** — Institutional Sponsorship | FII/DII/MF stakes increasing, bulk deals | ✅/🟡/❌ |
| **M** — Market Direction | Bull/bear/correction regime, follow-through | ✅/🟡/❌ |

**Final CANSLIM Score**: X/7 (✅=1, 🟡=0.5, ❌=0)
- **STRONG BUY** (≥6)
- **BUY** (5–5.5)
- **HOLD** (4–4.5)
- **AVOID** (<4)

---

### M. FORENSIC ACCOUNTING 🧪 (`/forensic` command)

**Shorthand**: `/forensic SYMBOL [SYMBOL2 ...]`

Financial health & manipulation risk screening using 3 forensic models.

#### Three Forensic Scores

| Score | Model | What It Measures | Red Flag |
|-------|-------|-----------------|----------|
| **Beneish M-Score** | 8-variable probit | Earnings manipulation risk | M > -1.78 = manipulation risk |
| **Piotroski F-Score** | 9-signal model | Financial health & accruals | 0–3 = weak, 7–9 = strong |
| **Altman Z'-Score** | Emerging market version | Distress/bankruptcy risk | Z' < 1.1 = distress zone |

**Usage**:
- Single stock: `/forensic RELIANCE` → detailed report on all 3 scores
- Multiple stocks: `/forensic TCS INFY WIPRO` → comparative screening, ranked by risk

---

### N. EVENT CALENDAR 📅 (`/events` command)

**Shorthand**: `/events [INDEX|SYMBOL] [DAYS]`

Upcoming corporate events: dividends, results, splits, AGMs, board meetings.

| Command | Scope | Window | Output |
|---------|-------|--------|--------|
| `/events` | NIFTY 50 | 14 days | NIFTY 50 stocks' events (default) |
| `/events NIFTY 50` | NIFTY 50 | 14 days | NIFTY 50 events |
| `/events RELIANCE` | Single stock | 14 days | RELIANCE-specific events |
| `/events NIFTY 50 30` | NIFTY 50 | 30 days | Extend to 30 days |

**Grouped By Type**: Dividend, Results, Bonus, Split, AGM, Board Meeting with ex-date countdowns.

---

### O. GLOBAL & MACRO MARKETS 🌍

#### Global Commands

| Command | What It Does |
|---------|------------|
| `/global` | Global risk regime + India read-through |
| `/global readthrough` | US signals mapped to NSE sector implications |
| `/us` | US market summary (indices + sectors) |
| `/us indices` | SPY, QQQ, NDX, Dow, Russell, VIX tape |
| `/us sectors` | US sector ETF rotation (XLK, XLF, XLE, etc.) |
| `/us stage2` | US Stage 2 leaders |
| `/us vcp` | US VCP setups |
| `/us stock NVDA` | US stock technical context |

#### Seasonal & Cycle

| Command | What It Does |
|---------|------------|
| `/heat` | Sector seasonal heatmap — current-month signals |
| `/heat 5` | Sector heat calendar for May (by month number) |
| `/cycle` | Economic cycle phase + preferred/avoid sectors |

#### Scenario & Narratives

| Command | What It Does |
|---------|------------|
| `/scenario RELIANCE` | What-if price scenarios for RELIANCE |
| `/narrative` | Portfolio investment narratives (all holdings) |
| `/narrative TCS INFY` | Narratives for specific stocks |

#### Voice & Concall

| Command | What It Does |
|---------|------------|
| `/voice` | Generate daily voice briefing script + GPT TTS audio and auto-play it |
| `/voice script` | Print the daily voice briefing script without generating audio |
| `/voice 2026-05-09 --no-play` | Generate a historical daily briefing without auto-playing audio |
| `/voice-mode on` | Speak every normal typed Agent Adda answer until disabled |
| `/voice-mode off` | Disable automatic spoken responses for typed answers |
| `/ask-voice` | Push-to-talk voice question: record, transcribe, analyze, summarize, speak response, and print transcript |
| `/ask-voice --audio-file question.wav` | File-based voice copilot path for deterministic testing and saved questions |
| `/ask-voice --confirm --no-audio` | Transcript confirmation with text-only response, useful when audio playback is not desired |
| `/voice-live` | Live voice assistant loop: listen, transcribe, print transcript, answer, speak, and repeat |
| `/voice-live --turns 3 --seconds 8 --no-play` | Bounded live session for testing or quiet environments |
| `/concall TCS` | Concall NLP — sentiment, themes, risk flags |

Voice Copilot design notes:
- `/voice` is for daily market briefing audio. It does not listen to the microphone.
- `/voice-mode` is for typed questions with spoken answers. It does not listen to the microphone.
- `/ask-voice` records a spoken question, then prints the transcript after transcription completes.
- `/voice-live` repeats the `/ask-voice` flow across multiple turns and exits when the user says `stop`, `quit`, or `exit`.
- `/ask-voice` saves local sessions under `data/voice_sessions/` with input audio, transcript, normalized query, full answer, spoken summary, response audio, and `manifest.json`.
- Voice synthesis should use GPT TTS with `gpt-4o-mini-tts`, default voice `cedar`, and persona `instructions` for a calm senior Indian-market operator tone.
- Spoken answers should be concise, risk-aware, and framed as research-only output, not investment advice.
- Voice output is AI-generated. Voice sessions are stored locally unless deleted by the user.

---

### P. REPORT GENERATION 📝 (`/report` command)

**Shorthand**: `/report [TYPE] SYMBOL [FORMAT]`

Generate formatted research reports in multiple formats.

#### Report Types

| Type | What It Analyzes | Typical Sections |
|------|-----------------|-----------------|
| `technical` | Chart setup, trends, levels | Technicals, key levels, stage, signals |
| `fundamental` | Earnings, ratios, growth | P/E, ROE, ROCE, growth, valuations |
| `forensic` | M-score, F-score, Z'-score | Manipulation risk, financial health, distress |
| `research` | 360° comprehensive | Technical, fundamental, forensic, news, catalysts |
| `intraday` | 15m setups, entry/target/SL | Entry zones, targets, stoploss, R:R |
| `canslim` | CANSLIM 7-point quality | C, A, N, S, L, I, M score card + verdict |
| `ric` | RIC investigation output | 5–8 step analysis (auto-formatted from RIC run) |
| `sector` | Sector deep dive | Breadth, leaders, laggards, rotation |

#### Report Formats

| Format | Output | Usage |
|--------|--------|-------|
| `html` (default) | HTML file (opens in browser) | `/report technical RELIANCE html` |
| `pdf` | PDF file | `/report fundamental TCS pdf` |
| `md` | Markdown file | `/report forensic INFY md` |

#### Report Commands

```
/report                                  # Show usage help
/report technical RELIANCE               # HTML format (default)
/report fundamental TCS pdf              # PDF format
/report forensic INFY md                 # Markdown
/report research HDFCBANK                # 360° comprehensive report (HTML)
/report intraday SBIN                    # Intraday setup report
/report canslim TATAMOTORS               # CANSLIM scorecard
/report ric ADANIENT pdf                 # RIC investigation as PDF
/report sector IT                        # Sector analysis for IT
/report RELIANCE                         # Defaults: research type + HTML format
```

---

### Q. PORTFOLIO 💼 (`/pnl` command)

**Shorthand**: `/pnl`

Live portfolio P&L dashboard from `holdings.csv` with live prices.

**Display**:
- Table: Symbol | Qty | Avg Cost | LTP | Current Value | P&L (₹) | P&L% | Day%
- Totals: Invested, Current, Total P&L, Day P&L
- Color coding: Profit (green), Loss (red)

---

### R. SESSION & CONTEXT 💾

| Command | What It Does |
|---------|------------|
| `/context` | Show conversation history summary + context budget |
| `/session` | Alias for `/context` |
| `/history` | Alias for `/context` |
| `/new` | Start fresh session (clear history) |
| `/reset` | Alias for `/new` |
| `/fresh` | Alias for `/new` |

**Context Budget**: Tracks character usage for LLM history (up to ~64K chars, max 32 turns).

---

### S. DATA REFRESH ⚙️ (`/refresh` command)

**Shorthand**: `/refresh [MODE]`

Run daily data refresh pipeline (async background process).

| Command | Mode | What It Does | Typical Duration |
|---------|------|------------|------------------|
| `/refresh` | snapshot (default) | Fast snapshot: stage DB update only | ~1–2 min |
| `/refresh snapshot` | snapshot | Explicit snapshot mode | ~1–2 min |
| `/refresh live` | live_only | Live prices only (fastest) | ~30s |
| `/refresh full` | full | R bhavcopy + analysis + snapshot | ~10–15 min |
| `/refresh analysis` | analysis | Analysis + snapshot (skips aux fetch) | ~5–10 min |
| `/refresh status` | status | Check if refresh is running | Instant |
| `/refresh stop` | stop | Cancel a running refresh | Instant |

**Implementation**: Runs `daily_refresh.py` as subprocess, logs to `data/refresh.log`.

---

### T. APPEARANCE & SETTINGS ⚙️

#### Theme Command
**Shorthand**: `/theme [NAME]`

| Theme | Color Scheme |
|-------|------------|
| `dark` (default) | Dark background, cyan/green highlights |
| `dracula` | Dracula theme (purple/pink) |
| `solarized` | Solarized Dark (warm tones) |
| `high-contrast` | High contrast (bright colors) |
| `nord` | Nord theme (cool tones) |

#### Scale Command
**Shorthand**: `/scale [NAME]`

| Scale | Description | Chart Size |
|-------|------------|-----------|
| `compact` | Fits small terminals | 60×15 |
| `normal` (default) | Balanced layout | 80×20 |
| `large` | Wide terminals / big screens | 120×30 |

---

### U. HELP & DISCOVERY ❓

| Command | What It Shows |
|---------|------------|
| `/help` or `?` | Full command help (giant table) |
| `/help charts` | Help section: charts |
| `/help screens` | Help section: EOD screeners |
| `/help scan` | Help section: intraday scanner |
| `/help fno` | Help section: F&O / options |
| `/help search` | Help section: deep search engine |
| `/help forensic` | Help section: forensic accounting |
| `/help monitors` | Help section: background monitors & alerts |
| `/help ric` | Help section: recursive investigations |
| `/help refresh` | Help section: data refresh |
| `/help appearance` | Help section: themes & scale |
| `/help macro` | Help section: seasonal & macro |
| `/commands` | Browse all commands by category (compact table) |
| `/commands KEYWORD` | Filter commands by keyword (e.g., `/commands pdf`) |

---

### V. UTILITY COMMANDS

| Command | What It Does |
|---------|------------|
| `/clear` or `clear` or `cls` | Clear screen (and reset follow-ups) |
| `/export` | Export session to HTML (opens in browser) |
| `/export html` | Explicit HTML export |
| `/export pdf` | PDF export (requires weasyprint or pdfkit) |
| `1 / 2 / 3` | Select numbered follow-up question |
| `exit` or `quit` or `:q` | Exit Agent Adda |

---

## III. COMMAND DISPATCH LOGIC (`_chat_loop` function)

The main interactive chat loop handles:

1. **Input capture** via `prompt_toolkit.PromptSession`
2. **Command detection** (prefix matching on `/` or `p<digit>`)
3. **Command dispatch** (if-elif handlers)
4. **Mode switching** (applies `/intraday` or `/historical` prefix if needed)
5. **LLM query** via `agent.query()`
6. **Response rendering** with formatting, follow-ups, news

### Dispatch Order (Priority)
1. Exit: `exit`, `quit`, `q`, `:q`
2. Mode commands: `/live`, `/eod`, `/auto`
3. Help: `/help`, `?`, `/commands`
4. Utility: `/clear`, `/new`, `/reset`
5. US/Global: `/global`, `/us` (deterministic direct render)
6. Monitor: `/monitor [start|stop|status|list]`
7. Alerts: `/alert [list|add|del|check|monitor]`
8. RIC: `/ric [name] [arg]`
9. Context: `/context`, `/session`, `/history`
10. Refresh: `/refresh [mode]` (async subprocess)
11. Export: `/export [format]`
12. Prompts: `/prompts [filter]`
13. Scan: `/scan [index|strategy]`
14. Screen: `/screen [type]`
15. Chart: `/chart [symbol] [tf] [--html] [indicators]`
16. Search: `/search [symbol] [vertical]`
17. Report: `/report [type] [symbol] [format]`
18. Analyze: `/analyze [source]`
19. CANSLIM: `/canslim [symbol]`
20. Forensic: `/forensic [symbols]`
21. Events: `/events [index|symbol] [days]`
22. Heat: `/heat [month]`
23. Cycle: `/cycle`
24. Scenario: `/scenario [symbol] [prices]`
25. Narrative: `/narrative [symbols]`
26. Voice: `/voice [script|YYYY-MM-DD]`, `/voice-mode`, `/ask-voice`
27. Concall: `/concall [symbol]`
28. PnL: `/pnl`
29. Backtest: `/backtest [list|run|report]`
30. Strategy Lab: `/strategy-lab validate`
31. Options: `/options [symbol] [expiry]`
32. Chain: `/chain [symbol]`
33. OI: `/oi [symbol]`
34. FNO: `/fno [symbol]`
35. Strategy: `/strategy [symbol] [strat_name]`
36. Theme: `/theme [name]`
37. Scale: `/scale [name]`
38. Prompt shortcut: `p<number>`
39. Follow-up shortcut: `1`, `2`, `3`
40. **Default**: send as natural language query to agent

---

## IV. HELPER FUNCTIONS & UTILITIES

### Command Parsing
| Function | Purpose |
|----------|---------|
| `_rewrite_scan_command()` | Convert `/scan STRATEGY` to agent query |
| `_parse_monitor_start_args()` | Parse monitor start arguments |
| `_parse_us_global_command()` | Parse US/global command variants |
| `_parse_alert_with_llm()` | Use OpenAI to parse natural-language alerts |
| `_looks_like_index_arg()` | Detect if arg is an index (not sector) |
| `handle_backtest_command()` | Dispatch `/backtest` and `/strategy-lab` terminal flows |

### Rendering
| Function | Purpose |
|----------|---------|
| `_print_prompts_library()` | Render 60 prompts in rich panel tables |
| `_print_ric_library()` | Render 8 RICs in table |
| `_print_commands()` | Render all commands by category (searchable) |
| `_print_help()` | Render giant help panel (all sections) |
| `_print_response()` | Render agent response + follow-ups + news |
| `_print_user()` | Render user query with timestamp |
| `_print_monitor_status()` | Show active monitor workers status |
| `_render_monitor_event_live()` | Render alert batch in terminal |
| `_render_comparison_table()` | Stock comparison side-by-side table |
| `_render_alert_batch()` | Render monitor alerts with confidence |

### UI Utilities
| Function | Purpose |
|----------|---------|
| `_separator()` | Thin horizontal rule |
| `_mode_tag()` | Return colored mode indicator |
| `_build_prompt()` | Build bottom-prompt ANSI text with mode + follow-ups + turn count |
| `_ts()` | Return current time as HH:MM:SS string |
| `_run_with_spinner()` | Run agent query with optional braille spinner |
| `_mcon()` | Return Console writing to sys.__stdout__ |
| `_live_con()` | Console through patch_stdout (safe for monitor output) |

### Startup
| Function | Purpose |
|----------|---------|
| `print_banner()` | Print ASCII art banner (colorama) |
| `_greeting()` | Return "Good Morning/Afternoon/Evening" |
| `_run_startup_briefing()` | Run pre-market briefing on launch |

### Misc
| Function | Purpose |
|----------|---------|
| `_parse_followups()` | Extract 3 follow-up questions from LLM response |
| `_print_followup_line()` | Render one follow-up with optional command hint |
| `_check_monitor_alerts()` | Drain and display queued monitor alerts |
| `_start_alert_autodisplay()` | Start background thread for auto-display |
| `_text_with_links()` | Create Rich Text with OSC-8 links + visible URLs |
| `_append_bare_url_links()` | Append URLs with link styling |
| `_render_news_item()` | Render one news/research item |
| `_print_context_summary()` | Show conversation history + budget |

---

## V. PROMPT LIBRARY STRUCTURE

### 10 Categories, 60+ Total Prompts

1. **📊 Market Overview** (6 prompts)
   - Market Pulse, Breadth Snapshot, FII/DII Flow, Top Movers, Most Active, 52W Extremes

2. **⚡ Intraday Trading** (7 prompts)
   - Bank Nifty Scan, Nifty 50 Scan, Nifty IT, RELIANCE Intraday, VCP Pattern Hunt, Volume Spike, Supertrend Setups

3. **📈 Technical Analysis** (7 prompts)
   - Stage 2 Breakouts, Supertrend BUY Sweep, Strong Buy Signals, ADX Leaders, NIFTY 50 Technicals, BANK NIFTY Setup, 52W High Breakouts

4. **🏭 Sector Analysis** (7 prompts)
   - IT Health, Banking, Pharma, Auto, FMCG vs Consumer, Top Sector Today, Sector Rotation

5. **🔬 Screeners** (6 prompts)
   - Stage 2 Universe, Breakout Candidates, High RS, Investment Grade, Recovery Plays, Momentum Movers

6. **🏦 Fundamentals** (7 prompts)
   - TCS Analysis, HDFC Bank Valuation, IT P/E Compare, High ROE Low PE, Debt-Free, Concall Summary, Peer Comparison

7. **🔍 Stock Deep Dive** (6 prompts)
   - RELIANCE Full View, INFOSYS Analysis, ADANI ENTERPRISES, ZOMATO, TATA MOTORS, SBI Deep Dive

8. **📰 News & Catalysts** (5 prompts)
   - Top News, Results Calendar, FII Bulk Deals, Macro Events, Nifty News Flow

9. **📋 Portfolio** (4 prompts)
   - Exposure, vs Stage2, vs Screen, Holdings Health

10. **🌍 Global & Macro** (5 prompts)
    - Global Market, USD/INR Impact, Crude Oil, FII Position, Emerging Markets Comparison

---

## VI. KEY DATA STRUCTURES

### Global State Variables
```python
_mode             = "auto"       # "auto" | "intraday" | "historical"
_followups: list[str] = []       # Current 3 follow-up suggestions
_ALERT_DIR_STYLE  = {"BUY": "bold green", "SELL": "bold red", "WATCH": "bold yellow"}
_CONF_COLOURS     = {"high": "green", "medium": "yellow", "low": "dim white"}
```

### Main Data Structures

| Structure | Type | Purpose |
|-----------|------|---------|
| `_SLASH_COMMANDS` | `list[tuple[str, str]]` | All 150+ slash commands with hints |
| `_CMD_CATEGORIES` | `dict[str, tuple[str, str]]` | Maps root `/cmd` → (category_label, icon) |
| `_PROMPT_INDEX` | `dict[int, tuple]` | Maps prompt number 1–60 → (cat, title, query) |
| `PROMPT_LIBRARY` | `list[dict]` | 10 categories with prompts |
| `RIC_LIBRARY` | `dict[str, dict]` | 8 RICs with steps |
| `MONITOR_STRATEGIES` | `dict` | 14 monitor strategies |
| `StrategyDefinition` | `dataclass` | Registry metadata for EOD Strategy Lab strategies |
| `BacktestConfig` | `dataclass` | Strategy, capital, allocation, and execution-policy config |
| `BacktestResult` | `dataclass` | Backtest trades, metrics, and skipped candidate details |
| `SCHEMA_SQL` | `str` | PostgreSQL DDL for the `backtesting` schema |
| `_KNOWN_SYMBOLS` | `list[str]` | 40+ NSE symbols for completion |
| `_STARTER_PHRASES` | `list[tuple]` | Natural language phrase starters for completion |
| `_SCAN_ALIASES` | `dict` | Shorthand → (screener_key, label) |
| `_VALID_MONITOR_INTERVALS` | `set` | {1, 3, 5, 10, 15, 30, 60} minutes |

---

## VII. AUTO-DISPLAY & BACKGROUND FEATURES

### Alert Auto-Display Thread
- **Thread**: `_start_alert_autodisplay()` daemon thread
- **Frequency**: Drains alert queue every 3 seconds
- **Output**: Uses `sys.__stdout__` to avoid Rich cursor conflicts
- **Lifecycle**: Started at chat loop beginning, stopped during processing, restarted per iteration

### Monitor Alert Rendering
- **Render Function**: `_render_monitor_event_live()` or `_render_alert_batch()`
- **Output**: Rich table with Symbol | Signal | Direction | Entry | Target | SL | R:R | Confidence
- **Styling**: Color-coded direction (BUY=green, SELL=red, WATCH=yellow)

### Data Refresh Background Process
- **Command**: `/refresh [MODE]` → launches `daily_refresh.py` as subprocess
- **Modes**: `snapshot` (1–2m), `live` (30s), `full` (10–15m), `analysis` (5–10m)
- **Logging**: `data/refresh.log`
- **Monitoring**: `/refresh status` checks PID and exit code

---

## VIII. COMPLETION & INPUT HANDLING

### Three-Tier Autocomplete
1. **Tier 1** (`/`): Slash commands from `_SLASH_COMMANDS`
2. **Tier 2** (`p`): Prompt library shortcuts (`p1`–`p60`)
3. **Tier 3** (word): Starter phrases + known symbols

**Class**: `_AgentCompleter` extends `prompt_toolkit.completion.Completer`

**Styling**: Custom `_COMPLETER_STYLE` (dark background, cyan completion, bright current)

---

## IX. STARTUP FLOW

1. **Print banner** (`print_banner()`)
2. **Initialize global state** (`_mode`, `_followups`)
3. **Parse CLI args** (`--query`, `--trace`, `--mode`, `--theme`, `--scale`, `--no-briefing`)
4. **Create Agent Adda instance** (LLM + tools)
5. **If interactive**: Run startup briefing (`_run_startup_briefing()`)
6. **Enter chat loop** (`_chat_loop()`)
7. **If `--query`**: Run single query mode (`_single_query()`)

---

## X. COMMAND COUNTS & STATS

| Category | Count |
|----------|-------|
| Prompts (shortcuts) | 60 |
| RIC shortcuts | 8 |
| Scan (strategies) | 9 |
| Screen (types) | 10 |
| Strategy Lab / Backtest | 5+ |
| Monitor (strategies) | 14 |
| Alert (sub-commands) | 5 |
| Options/Chain/OI/FNO/Strategy | 18 |
| Charts | 10 |
| Search (verticals) | 11 |
| Analyze (modes) | 2 |
| CANSLIM | 1 |
| Forensic | 2 |
| Events | 4 |
| Global/US/Heat/Cycle/Scenario/Narrative/Voice/Concall | 14 |
| Report (types) | 8 |
| Refresh | 6 |
| Theme/Scale | 6 |
| Help/Commands/Utility | 10 |
| **TOTAL** | **~150+** |

---

## XI. KEY SHORTCUTS & ALIASES

| Input | Expands To |
|-------|----------|
| `/l` | `/live` |
| `/h` | `/eod` |
| `/a` | `/auto` |
| `?` | `/help` |
| `p7` | Run prompt #7 |
| `1 / 2 / 3` | Select follow-up 1/2/3 |
| `/p` | `/prompts` |
| `cls` or `clear` | `/clear` |
| `:q` | `exit` |
| `q` | `quit` |

---

## XII. IMPORTANT NOTES

1. **LLM Alert Parser**: Uses OpenAI GPT-4o-mini to parse natural-language alerts (fallback to positional parsing).

2. **Auto-Routing**: Sector X-ray auto-routes to Index Pulse if arg looks like an index (contains "NIFTY", "MIDCAP", "SMALLCAP", "BANK", etc.).

3. **Prompt Toolkit Integration**:
   - History: `InMemoryHistory()` persists across chat loop
   - Auto-suggest: `AutoSuggestFromHistory()`
   - Completer: `_AgentCompleter()` for slash commands, prompts, phrases
   - Patch stdout: prevents cursor conflicts with background monitors

4. **Direct Renders**: Some commands skip the agent and render directly:
   - `/heat`, `/cycle`, `/scenario`, `/narrative`, `/voice`, `/concall`, `/pnl`
   - `/options`, `/chain`, `/oi`, `/fno`, `/strategy`, `/backtest`, `/strategy-lab`

5. **Follow-ups**: Auto-extracted from agent response. User can reply `1`, `2`, or `3` to explore suggested next steps.

6. **Context Budget**: ~64K chars max, 32 turns — prevents LLM context explosion. Use `/new` to reset.

7. **Monitor Interval Validation**: Only {1, 3, 5, 10, 15, 30, 60} minutes are allowed.

---

## QUICK REFERENCE TABLE (All Commands Alphabetically)

| Command | Category | Use Case |
|---------|----------|----------|
| `/alert list` | Watchlist | List all price/RSI alerts |
| `/alert add` | Watchlist | Add new alert (natural language or positional) |
| `/alert del` | Watchlist | Delete alert by ID |
| `/alert check` | Watchlist | Check all alerts against live prices |
| `/alert monitor` | Watchlist | Toggle background alert monitor |
| `/analyze` | Document Analysis | Read PDF/DOCX or run 360° stock analysis |
| `/backtest` | Strategy Lab | List strategies, run EOD backtests, persist runs, and render latest report |
| `/canslim` | Stock Quality | CANSLIM 7-point evaluation |
| `/chain` | Options | Live option chain (PCR, max pain, Greeks) |
| `/chart` | Charts | ASCII or HTML candlestick chart |
| `/clear` | Session | Clear screen |
| `/commands` | Discovery | Browse commands by category |
| `/company-index` | Company Intelligence | Crawl/index company website pages and official investor documents |
| `/company-xray` | Company Intelligence | Company + Sector X-Ray with evidence coverage and search audit |
| `/concall` | Analysis | Concall NLP (sentiment, themes, risk flags) |
| `/context` | Session | Show conversation history + budget |
| `/cycle` | Macro | Economic cycle phase + sector positioning |
| `/events` | Calendar | Upcoming corporate events (14/30 days) |
| `/export` | Session | Export conversation to HTML/PDF |
| `/fno` | Options | F&O overview (chain + futures + strategy) |
| `/forensic` | Forensics | Beneish + Piotroski + Altman scores |
| `/global` | Macro | Global risk regime + India read-through |
| `/heat` | Macro | Sector seasonal heatmap |
| `/help` | Discovery | Show full help (all sections) |
| `/monitor` | Monitors | Start/stop/status/list background monitors |
| `/narrative` | Analysis | Portfolio investment narratives |
| `/new` | Session | Start fresh session (clear history) |
| `/oi` | Options | Open Interest analysis (support/resistance) |
| `/options` | Options | Live options chain |
| `/pnl` | Portfolio | Live portfolio P&L dashboard |
| `/prompts` | Discovery | Browse 60 curated research prompts |
| `/refresh` | Settings | Run data refresh pipeline |
| `/report` | Reports | Generate formatted reports (HTML/PDF/MD) |
| `/ric` | Investigations | Run multi-step recursive investigation |
| `/scale` | Settings | Change layout scale |
| `/scan` | Intraday | Intraday screener |
| `/scenario` | Analysis | What-if price scenarios |
| `/screen` | EOD | EOD screener |
| `/search` | Search | Deep 11-vertical search |
| `/strategy` | Options | Build options strategy with pricing |
| `/strategy-lab` | Strategy Lab | Validate EOD data readiness before backtesting |
| `/theme` | Settings | Switch color theme |
| `/us` | Global | US market summary |
| `/voice` | Analysis | Generate voice briefing (MP3) |
| `/auto` / `/a` | Mode | Switch to AUTO mode |
| `/eod` / `/h` | Mode | Switch to EOD mode |
| `/live` / `/l` | Mode | Switch to LIVE mode |

---

**Total Slash Commands**: ~150+ including subcommands and aliases

---

## COMPANY + SECTOR X-RAY 🧭

**Shorthand**: `/company-xray SYMBOL`

Company + Sector X-Ray is a company-first, sector-expanded intelligence workflow. It builds a reusable company knowledge base, records source coverage, categorizes evidence, maps sector and competitor context, evaluates RBI/Budget sensitivity, and produces an analyst-style memo for research and learning.

| Command | Arguments | What It Does |
|---------|-----------|--------------|
| `/company-index DMART` | SYMBOL | Index company website pages into the website FTS store |
| `/company-index DMART --include-documents --document-limit 5` | SYMBOL + bounds | Download a bounded set of official investor documents into `source_documents` |
| `/company-index DMART --seed-sitemap --respect-robots` | crawl flags | Use sitemap discovery and robots-aware crawling where supported |
| `/company-index DMART --adapter auto` | adapter flag | Auto-use company-specific adapters for SPA/API-backed investor sites such as DMart |
| `/company-xray DMART` | SYMBOL | Run permissive Company + Sector X-Ray and generate a memo with visible evidence gaps |
| `/company-xray DMART --strict` | SYMBOL + strict flag | Require minimum official evidence before a full memo is produced |
| `/company-xray DMART --refresh` | SYMBOL + refresh flag | Refresh source searches and evidence cache before analysis |
| `/ric company-xray DMART` | SYMBOL | Run the multi-step RIC workflow: identity, evidence, business model, sector, competition, policy impact, deliberation, report |

The direct `/company-xray` route prints evidence coverage, report paths, known gaps, strict-mode gaps, and a research-only disclaimer. The `/ric company-xray` recipe adds a guided 9-step investigation around the same evidence store.

### Evidence Model

The workflow separates evidence from interpretation:

- **Official evidence**: NSE/BSE filings, annual reports, investor presentations, concalls, RBI, Union Budget, ministry releases, and company IR pages.
- **Structured internal data**: Agent Adda fundamentals, technicals, sector rotation, macro proxies, FII/DII, global read-through, and knowledge graph data.
- **External context**: news, industry articles, rating commentary, analyst coverage pages, and public broker-research landing pages.
- **LLM interpretation**: generated synthesis that must be traceable to stored evidence chunks where possible.

### Search Audit and Evidence Coverage

Every Company X-Ray run stores a search audit:

- aliases used
- verticals requested
- indexed company website chunks promoted into evidence
- downloaded investor documents parsed into evidence where the PDF parser is available
- stale company indexes can be refreshed in bounded backend batches without stopping on one failed symbol
- query strings
- source groups attempted
- result counts
- URLs found
- parse status
- failure reasons
- evidence chunks created

The report includes an **evidence coverage** section showing which areas are strong, weak, unavailable, or derived. This prevents DMART-style no-result searches from turning into generic unsupported prose.

*Generated: 11 May 2026*
