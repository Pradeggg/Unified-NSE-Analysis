# Agent Adda Commands And Prompts Helpfile

Generated from `nse_agent.py` command and prompt registries on 2026-05-24.

## Quick Start

- Start interactive terminal: `.venv/bin/python nse_agent.py`
- Run one command non-interactively: `.venv/bin/python nse_agent.py -q "/help"`
- Browse commands inside Agent Adda: `/commands`
- Search commands inside Agent Adda: `/commands fno`, `/commands email`, `/commands report`
- Browse curated prompts: `/prompts`
- Run prompt shortcut: `p<number>`, for example `p1` or `p71`
- Get detailed help: `/help`, `/help fno`, `/help email`, `/help refresh`

## Command Discovery

| Command | Use |
|---|---|
| `/help` | Table of contents for curated help sections. |
| `/help <section>` | Opens a section such as `charts`, `screens`, `scan`, `fno`, `search`, `forensic`, `monitors`, `ric`, `refresh`, `appearance`, or `macro`. |
| `/help <keyword>` | Searches help entries and command descriptions. |
| `/commands` | Browse every registered slash command grouped by family. |
| `/commands <keyword>` | Filter the command catalog by keyword, such as `pdf`, `email`, `fno`, `monitor`, or `results`. |
| `/prompts` | Browse all curated prompts. |
| `/prompts <category>` | Filter prompts by `market`, `intraday`, `technical`, `sector`, `screener`, `fundamentals`, `stock`, `news`, `portfolio`, `global`, or `email`. |

## Email Piping: Detailed Usage

The pipe form lets you run an Agent Adda command or natural-language prompt, capture its rendered terminal output, and hand that captured output to `/email`.

```text
<upstream command or prompt> | /email --to recipient@example.com [email flags]
```

How it works:

1. Agent Adda detects the trailing `| /email ...` segment.
2. It strips the email segment and runs the upstream command normally.
3. It records the Rich terminal output from the upstream command.
4. It writes the captured output under `reports/generated/piped_<slug>_<timestamp>.md` or `.html`.
5. It invokes `/email <captured_file> ...` with your email flags.
6. `/email` drafts or sends through Microsoft Outlook on macOS, using an LLM-generated subject and HTML body when available, with deterministic fallback text if the LLM is unavailable.

Common email flags:

| Flag | Meaning |
|---|---|
| `--to a@x.com` | Required recipient list. Multiple recipients can be comma, semicolon, or whitespace separated. |
| `--bcc b@y.com,c@z.com` | Optional BCC recipients. |
| `--as body` | Put the LLM-rendered summary/body inline, with no attachment. |
| `--as attachment` | Send the captured/report file as an attachment. |
| `--as both` | Use both inline body and attachment; this is the default for many report aliases. |
| `--send` | Send immediately instead of opening an Outlook draft for review. |
| `--dry-run` | Render preview HTML under `logs/` without touching Outlook. |
| `--note "..."` | Add context for the email composer. |

Reliable pipe patterns:

```text
/ric sherlock DMART | /email --to a@x.com
/ric company-xray DMART | /email --to a@x.com --as both
/mtf RELIANCE | /email --to a@x.com --note "MTF confluence panel"
/screen stage2 | /email --to a@x.com --as body
/scan NIFTY BANK momentum | /email --to a@x.com --dry-run
/data-coverage NIFTY500 --details | /email --to a@x.com
/strategy-council DMART --iterations 3 | /email --to a@x.com
Show current sector breadth snapshot -- leaders and laggards | /email --to a@x.com
Show the top 12 F&O signals today with PCR, buildup, and direction | /email --to a@x.com
```

Direct `/email` report aliases do not need a pipe:

```text
/email sector --to a@x.com
/email stage2 --to a@x.com --send
/email dashboard --to "a@x.com;b@y.com"
/email reports/latest/sector_rotation.html --to a@x.com --as attachment
```

Use `--dry-run` first when testing recipients, body mode, or a new upstream command:

```text
/ric morning-intel | /email --to a@x.com --dry-run
/email sector --to a@x.com --dry-run
```

Operational notes:

- The pipe separator must be a literal `|` followed by `/email` near the end of the input.
- The upstream side can be a slash command or natural-language prompt.
- The right side must include valid `/email` arguments, usually at least `--to` unless you are checking usage.
- If upstream output is empty or the command fails, the email step can fail or produce a thin preview.
- For immediate sending, use `--send`; otherwise Outlook draft review is safer.
- Screenshots use `/screenshot`, not pipe capture, because they attach a PNG.

## CLI Arguments

```text
.venv/bin/python nse_agent.py [OPTIONS]

Options:
  -q, --query TEXT             Single query or slash command, non-interactive
  -t, --trace                  Show tool execution trace
  --mode {auto,live,eod}       Default data mode
  --no-briefing                Skip startup market briefing
  --theme THEME                dark, dracula, solarized, high-contrast, nord
  --scale SCALE                compact, normal, large
  --skip-readiness             Skip startup DB readiness checks
```

## All Slash Commands

Total registered entries: 280.

### Research Prompts

| Command | Description |
|---|---|
| `/prompts` | Browse 60 curated research prompts |
| `/prompts market` | Market overview prompts |
| `/prompts intraday` | Intraday trading prompts |
| `/prompts technical` | Technical analysis prompts |
| `/prompts sector` | Sector analysis prompts |
| `/prompts screener` | Screener prompts |
| `/prompts fundamentals` | Fundamentals & valuation prompts |
| `/prompts stock` | Stock deep-dive prompts |
| `/prompts news` | News & catalysts prompts |
| `/prompts portfolio` | Portfolio prompts |
| `/prompts global` | Global & macro prompts |
| `/prompts email` | Email-pipe prompts — chain any command to /email |

### RIC Investigations

| Command | Description |
|---|---|
| `/ric` | Show RIC library (8 investigative recipes) |
| `/ric sherlock` | 5-step: quote→technicals→fundamentals→news→trade  [SYMBOL] |
| `/ric sector-xray` | 4-step: sector breadth→leaders→laggards→entries  [SECTOR] |
| `/ric breakout-hunter` | 5-step: breadth→stage2→RS→VCP→final picks |
| `/ric earnings-playbook` | 5-step: results→ratios→peers→concall→setup  [SYMBOL] |
| `/ric index-pulse` | 4-step: technicals→breadth→top stocks→intraday  [INDEX] |
| `/ric peer-battle` | 4-step: fundamentals→technicals→news→verdict  [SYM,SYM,…] |
| `/ric risk-radar` | 4-step: macro→FII→breadth extremes→vulnerable stocks |
| `/ric morning-intel` | 5-step: global→yesterday→breadth→FII→watchlist |
| `/ric company-xray` | 9-step company intelligence workflow [SYMBOL] |
| `/ric sherlock DMART \| /email --to a@x.com --send` | Example: capture RIC output and send immediately |

### Intraday Scanner

| Command | Description |
|---|---|
| `/scan` | Scan NIFTY 50 for intraday signals |
| `/scan NIFTY BANK` | Scan Bank Nifty for intraday signals |
| `/scan NIFTY IT` | Scan Nifty IT for intraday signals |
| `/scan NIFTY MIDCAP 100` | Scan Nifty Midcap 100 |
| `/scan NIFTY PHARMA` | Scan Nifty Pharma |
| `/scan orb` | Opening Range Breakout — first 15-30m range break + volume |
| `/scan gap` | Gap & Go — gapping stocks with volume + MACD continuation |
| `/scan macd` | MACD Crossover — fresh MACD signal line cross |
| `/scan rsi` | RSI Divergence — RSI extreme + Bollinger mean-reversion |
| `/scan bb` | Bollinger Squeeze — low-volatility squeeze breakout |
| `/scan vwap` | VWAP Reclaim — price reclaiming/losing VWAP proxy |
| `/scan vcp` | VCP — Volatility Contraction Pattern intraday |
| `/scan momentum` | Momentum — MACD + RSI + Supertrend aligned |

### Market Dashboard

| Command | Description |
|---|---|
| `/dashboard` | Auto-refreshing stock-market-TV dashboard + ticker, heatmap, news |
| `/dash` | Alias: current-market dashboard + narrative |

### EOD Screeners

| Command | Description |
|---|---|
| `/screen stage2` | Stage 2 uptrend stocks (Weinstein) |
| `/screen momentum` | Near-52W-high momentum leaders (RS ≥ 1.0) |
| `/screen highrs` | Top RS ≥ 1.15 market leaders |
| `/screen turnaround` | Turnaround recovery setups |
| `/screen base` | Stage 1 basing/coiling stocks |
| `/screen tight` | Tight weekly range VCP-like consolidations |
| `/screen dip` | Oversold bounce — RSI < 40 dip in Stage 2 |

### Background Monitors

| Command | Description |
|---|---|
| `/monitor` | Show active background alert monitors |
| `/monitor list` | List all available monitor strategies |
| `/monitor status` | Show status of all running monitors |
| `/monitor start` | Start a background monitor (e.g. /monitor start breakout NIFTY 500 15 buy) |
| `/monitor start breakout` | Start breakout alert monitor (EMA+volume) — default 15m, NIFTY 500 |
| `/monitor start volume_surge` | Start volume surge alert monitor |
| `/monitor start reversal` | Start RSI/Bollinger reversal alert monitor |
| `/monitor start momentum` | Start MACD+RSI momentum alert monitor |
| `/monitor start supertrend` | Start Supertrend flip alert monitor |
| `/monitor start vcp` | Start VCP contraction pattern alert monitor |
| `/monitor start orb` | Start Opening Range Breakout alert monitor (5m bars) |
| `/monitor start gap_go` | Start Gap and Go continuation alert monitor |
| `/monitor start vwap` | Start VWAP reclaim/loss alert monitor |
| `/monitor start engulfing` | Start Engulfing candlestick pattern alert monitor |
| `/monitor start ema_ribbon` | Start EMA Ribbon alignment alert monitor |
| `/monitor start multi_confirm` | Start Multi-signal confluence alert (3/4 indicators agree) |
| `/monitor start rsi_divergence` | Start RSI divergence alert monitor |
| `/monitor start all` | Start ALL strategy alerts combined |
| `/monitor stop` | Stop a monitor (e.g. /monitor stop breakout) |
| `/monitor stop all` | Stop ALL active monitors |

### Watchlist Alerts

| Command | Description |
|---|---|
| `/alert list` | List all price/RSI alerts (shows timeframe column) |
| `/alert add` | Add alert (natural language): /alert add NIFTY rsi above 70 in 15min  \|  /alert add RELIANCE breakout |
| `/alert del` | Delete an alert by ID: /alert del 1 |
| `/alert check` | Check all alerts against live prices/RSI now |
| `/alert monitor` | Toggle background alert monitor (polls every 5 min, market hours) |

### F&O / Options

| Command | Description |
|---|---|
| `/options` | Live options chain — Rich table (Calls\|Strike\|Puts) with PCR, max pain, IV |
| `/options NIFTY` | NIFTY options chain — nearest expiry |
| `/options BANKNIFTY` | BANKNIFTY options chain — nearest expiry |
| `/options NIFTY 1` | NIFTY options chain — next expiry |
| `/chain` | Live option chain (PCR, max pain, OI, greeks) |
| `/chain NIFTY` | NIFTY option chain — nearest expiry |
| `/chain BANKNIFTY` | BANKNIFTY option chain — nearest expiry |
| `/chain FINNIFTY` | FINNIFTY option chain |
| `/oi` | Open Interest analysis (PCR, max pain, support/resistance) |
| `/oi NIFTY` | NIFTY OI analysis |
| `/oi BANKNIFTY` | BANKNIFTY OI analysis |
| `/fno` | Comprehensive F&O overview: chain + futures + strategy |
| `/fno NIFTY` | NIFTY F&O overview |
| `/fno BANKNIFTY` | BANKNIFTY F&O overview |
| `/strategy` | Build a specific options strategy with live pricing |
| `/strategy NIFTY long_straddle` | Long straddle on NIFTY |
| `/strategy NIFTY bull_call_spread` | Bull call spread on NIFTY |
| `/strategy BANKNIFTY iron_condor` | Iron condor on BANKNIFTY |

### Charts

| Command | Description |
|---|---|
| `/chart` | ASCII candlestick chart (candles + volume + RSI) |
| `/chart NIFTY` | NIFTY 3-month ASCII chart |
| `/chart BANKNIFTY` | BANKNIFTY 3-month ASCII chart |
| `/chart RELIANCE` | RELIANCE 3-month ASCII chart |
| `/chart HDFCBANK` | HDFCBANK 3-month ASCII chart |
| `/chart NIFTY 1y` | NIFTY 1-year chart |
| `/chart NIFTY 6mo` | NIFTY 6-month chart |
| `/chart NIFTY 1mo rsi` | NIFTY 1-month with RSI panel |
| `/chart RELIANCE 3mo rsi macd` | RELIANCE with RSI + MACD panels |
| `/chart RELIANCE --html` | RELIANCE interactive HTML chart (opens in browser) |
| `/chart NIFTY --html` | NIFTY interactive HTML chart (opens in browser) |
| `/chart NIFTY 1y --html` | NIFTY 1-year interactive HTML chart |
| `/chart BANKNIFTY 6mo --html` | BANKNIFTY 6-month HTML chart |
| `/visual-scan` | Grounded swing/EOD visual scan report with annotated charts and pattern evidence |
| `/visual-scan DMART` | Balanced visual scan report: trend, VCP, cup-handle, breakout, volume, MTF |

### Deep Search

| Command | Description |
|---|---|
| `/search` | Deep search — 11 parallel verticals (NSE+BSE+web) |
| `/search RELIANCE` | Full deep search on RELIANCE |
| `/search RELIANCE announcements` | NSE corporate announcements for RELIANCE |
| `/search RELIANCE dividend` | Dividend / corporate actions for RELIANCE |
| `/search RELIANCE insider` | Insider trade disclosures for RELIANCE |
| `/search RELIANCE shareholding` | Shareholding pattern & FII/DII trend |
| `/search RELIANCE analyst` | Analyst targets & brokerage recommendations |
| `/search RELIANCE broker` | Broker house research reports & price targets |
| `/search RELIANCE mf` | Mutual fund & institutional holdings |
| `/search RELIANCE concall` | Concall transcripts & management commentary |
| `/search RELIANCE news` | Sector news from 6 portals |
| `/search RELIANCE social` | Retail investor buzz: Reddit, Valuepickr, Traderji |
| `/search TATACONSUM deep` | Full 11-vertical deep search |

### Latest Results

| Command | Description |
|---|---|
| `/results RELIANCE` | Latest quarterly results, filings, concalls, and catalysts |
| `/results-feed` | Latest quarterly results filings — default last 2 weeks |
| `/results-feed 2` | Latest quarterly results filings in last N weeks |
| `/results-feed --weeks 4` | Latest quarterly results filings in last 4 weeks |
| `/latest-results 2` | Alias: quarterly results filings in last N weeks |

### YouTube Intelligence

| Command | Description |
|---|---|
| `/youtube` | List preset YouTube market channels |
| `/youtube 1` | Analyze latest video from channel #1 |
| `/youtube Trade With Trend` | Analyze latest video from preset channel by name |
| `/youtube channels` | List configured YouTube channels |
| `/youtube transcribe 1` | Explicitly transcribe latest video from channel #1 if captions are unavailable |
| `/youtube transcribe <url>` | Explicitly transcribe a YouTube video if captions are unavailable |
| `/youtube https://www.youtube.com/watch?v=...` | Analyze a direct YouTube market video URL |

### Market Knowledge

| Command | Description |
|---|---|
| `/learn PE ratio` | Source-backed concept explainer from Investopedia + Wikipedia |
| `/define ROCE` | Define a market or accounting concept with source URLs |
| `/compare ROCE ROE` | Compare market concepts using Investopedia + Wikipedia evidence |
| `/learn Minervini trading strategy` | Explain a trading framework with source-backed context |

### Company Intelligence

| Command | Description |
|---|---|
| `/company-index` | Index company website + official investor documents |
| `/company-index DMART` | Index DMart investor site using crawler + adapter auto-detect |
| `/company-index DMART --include-documents` | Download discovered official investor documents |
| `/company-index DMART --max-pages 10 --document-limit 5` | Bounded company website/document index run |
| `/company-xray` | Company + Sector X-Ray report from indexed evidence |
| `/company-xray DMART` | Run Company X-Ray for DMart |
| `/company-xray DMART --strict` | Run Company X-Ray with strict evidence coverage |

### Document Analysis

| Command | Description |
|---|---|
| `/analyze` | Analyze a PDF, DOCX, web page, or stock — auto-detects input type |
| `/analyze report.pdf` | Read and summarize a local PDF document |
| `/analyze https://example.com` | Scrape and analyze a web page |
| `/analyze annual_report.docx` | Extract and summarize a Word document |
| `/analyze RELIANCE` | Deep 360° stock analysis — technical, fundamental, forensic, news, sentiment |
| `/analyze ~/Downloads/concall.pdf` | Read and analyze a concall transcript PDF |

### CANSLIM Analysis

| Command | Description |
|---|---|
| `/canslim` | CANSLIM analysis — William O'Neil's 7-point stock quality framework |
| `/canslim RELIANCE` | Full CANSLIM evaluation for RELIANCE |
| `/canslim TCS` | CANSLIM growth + institutional quality check for TCS |
| `/strength MANINDS THERMAX` | Validate CANSLIM + RS + fundamentals + Piotroski without assumptions |

### Forensic

| Command | Description |
|---|---|
| `/forensic` | D5 Forensic analysis — Beneish M-score, Piotroski F-score, Altman Z'-score |
| `/forensic RELIANCE` | Forensic accounting analysis for RELIANCE |
| `/forensic TCS INFY WIPRO` | Forensic screening across multiple stocks |

### Report Mailer

| Command | Description |
|---|---|
| `/email` | Mail an Agent Adda report — LLM-drafted subject + HTML body via Outlook |
| `/email dashboard --to a@x.com` | Mail newest market dashboard (alias: market \| pulse) |
| `/email sector --to a@x.com` | Mail sector rotation report (default: attachment + exec summary) |
| `/email stage2 --to a@x.com --send` | Send Stage 2 tracker immediately (skip Outlook draft) |
| `/email sector --to "a@x.com;b@y.com"` | Multiple recipients — comma, semicolon or whitespace separated |
| `/email sector --to a@x.com --bcc b@y.com,c@z.com --as body` | Inline LLM-rendered body, no attachment |
| `/email <path> --to a@x.com --dry-run` | Render to logs/ preview without touching Outlook |
| `<cmd> \| /email --to a@x.com` | Pipe ANY upstream command's output as the email body (PG 2026-05-20) |

### Screen Capture Mailer

| Command | Description |
|---|---|
| `/screenshot --to a@x.com` | Drag a selection box, then mail PNG with LLM cover note |
| `/screenshot --mode window --to a@x.com` | Click a window to capture and mail |
| `/screenshot --mode full --to a@x.com --send` | Full screen, send immediately (no draft review) |
| `/screenshot --no-email --out ~/Desktop/shot.png` | Capture only — save to disk, don't email |

### Other

| Command | Description |
|---|---|
| `/recap` | Last 15-minute intraday market recap (PG intraday.quote_snapshots) |
| `/recap 30` | Custom-window recap, e.g. last 30 minutes |
| `/voice` | P3-2 60-second daily audio briefing — regime, flows, top picks (MP3/AIFF) |
| `/voice script` | Print the voice briefing script (no audio synthesis) |
| `/voice 2026-05-09` | Generate briefing for a specific historical signal date |
| `/voice-live` | Live voice assistant loop: listen, transcribe, answer, speak, repeat |
| `/voice-live --turns 3 --seconds 8` | Run a bounded live voice assistant session |
| `/ask-voice` | Record a spoken question, transcribe it, run Agent Adda, speak the response |
| `/ask-voice --audio-file question.wav` | Use an existing audio file as the spoken question |
| `/ask-voice --no-play` | Generate response audio but do not auto-play it |
| `/mtf` | 📐 Multi-timeframe confluence — verdict + score across M/W/D/60m/15m |
| `/mtf RELIANCE` | MTF panel for a single symbol (M/W/D/60m/15m verdict + score) |
| `/mtf RELIANCE --report` | MTF panel + write markdown report to reports/mtf/ |
| `/mtf scan NIFTY50 bullish` | Rank NIFTY 50 by bullish MTF confluence (top-10, score ≥ 70) |
| `/mtf scan NIFTY50 bearish` | Rank NIFTY 50 by bearish MTF confluence |
| `/mtf scan NIFTY500 bullish --min-score 80` | Universe scan with custom min-score |
| `/mtf scan BANKNIFTY bullish` | MTF scan on Bank Nifty constituents |
| `/mtf RELIANCE \| /email --to a@x.com` | Email the rendered MTF panel as HTML |

### Voice Briefing

| Command | Description |
|---|---|
| `/voice-mode on` | Speak every normal Agent Adda answer until disabled |
| `/voice-mode off` | Disable automatic spoken responses |
| `/voice-mode status` | Show whether automatic spoken responses are enabled |

### Events Calendar

| Command | Description |
|---|---|
| `/events` | E4 Upcoming corporate events — dividends, splits, results, AGMs |
| `/events NIFTY 50` | Event calendar for NIFTY 50 stocks (next 14 days) |
| `/events RELIANCE` | Upcoming events for a specific stock |

### Macro & Global

| Command | Description |
|---|---|
| `/us` | US/global market summary + report |
| `/us indices` | US index tape: SPY, QQQ, Nasdaq, Dow, Russell, VIX |
| `/us sectors` | US sector ETF rotation |
| `/us stage2` | US Stage 2 leaders |
| `/us vcp` | US VCP setups |
| `/us stock NVDA` | US stock technical context with report link |
| `/global readthrough` | US/global signals mapped to NSE sector implications |
| `/heat` | B3 Sector seasonal heatmap — current-month TAILWIND/HEADWIND |
| `/heat 5` | Sector heat calendar for May |
| `/cycle` | B5 Economic cycle phase + preferred/avoid sectors |
| `/global` | Global market assessment + India read-through |

### Analysis Tools

| Command | Description |
|---|---|
| `/scenario RELIANCE` | P2-2 What-if price scenarios for RELIANCE |
| `/narrative` | P2-4 Portfolio narratives — bull/bear thesis per stock |
| `/narrative TCS INFY` | Investment narratives for specific stocks |
| `/concall TCS` | D4 Concall NLP — sentiment, themes, risk flags |

### Report Generation

| Command | Description |
|---|---|
| `/report` | Generate a formatted report — PDF, HTML, or Markdown |
| `/report sector-rotation` | ⚡ Instant sector rotation dashboard from DB (no LLM) |
| `/report sector-rotation pdf` | ⚡ Sector rotation report as PDF |
| `/report stage2` | ⚡ Stage 2 universe tracker — top 30 leaders + new entrants (instant) |
| `/report stage2 md` | ⚡ Stage 2 tracker as Markdown |
| `/report recommendation` | Grounded EOD recommendation report — indices, sectors, stocks, portfolio/watchlist |
| `/report technical RELIANCE` | Technical analysis report for RELIANCE |
| `/report fundamental TCS pdf` | Fundamental report for TCS in PDF format |
| `/report forensic INFY md` | Forensic accounting report in Markdown |
| `/report research HDFCBANK` | Comprehensive 360° research report |
| `/report intraday SBIN` | Intraday analysis report |
| `/report canslim TATAMOTORS` | CANSLIM quality report |
| `/report ric ADANIENT pdf` | RIC investigation report in PDF |
| `/report sector IT` | Sector analysis report for IT sector |
| `/report RELIANCE` | Quick research report (default type: research, format: html) |

### Strategy Lab

| Command | Description |
|---|---|
| `/backtest list` | List EOD Strategy Lab strategies |
| `/strategy-lab validate` | Validate EOD backtesting data readiness |

### Strategy Council

| Command | Description |
|---|---|
| `/strategy-council DMART` | Iterative strategist + critic EOD simulation with train/validation/test discipline |
| `/strategy-council DMART --iterations 3 --horizon 1w,2w,4w` | Run Strategy Council with explicit horizons |
| `/strategy-council DMART --llm` | Use configured LLM strategist and critics, with deterministic fallback if unavailable |

### Research Council

| Command | Description |
|---|---|
| `/council today --horizon swing --risk moderate` | Full market Research Council: data steward, specialists, plan execution, critics, decision, report |
| `/council today --evidence-only --horizon swing` | Evidence-pack and missing-evidence Research Council report without specialist deliberation or final recommendation |
| `/council sector NIFTY AUTO --horizon swing` | Sector opportunity Research Council with shortlist, Coder Quant sweep, and ranked report |
| `/council stock MODISONLTD --horizon swing` | Stock deep-dive Research Council for a single symbol |
| `/council compare APOLLO BEL HAL --horizon positional` | Comparative Research Council across multiple symbols |
| `/council strategy "Stage 2 breakout with volume confirmation" --family stage2_breakout` | Strategy-build council for a hypothesis and strategy family |
| `/council intraday --scan vwap-reclaim` | Intraday tactical Research Council scan |
| `/council review --run latest` | Review the latest persisted council run |
| `/council report --run latest --format html` | Open or render the latest council report as HTML |
| `/council resume --run <id>` | Resume compact metadata for a persisted council run |
| `/council steward` | Run the Research Council data-readiness checks independently |
| `/council debug --run <id>` | Inspect debug metadata for a persisted council run |
| `/council export --run <id> --format json` | Export compact council run metadata as JSON |

### Data Coverage

| Command | Description |
|---|---|
| `/data-coverage NIFTY500` | 📊 Audit EOD history coverage for an index (default 5-year threshold) |
| `/data-coverage NIFTY500 --backfill` | Audit and yfinance-backfill any symbols below the 5-year threshold |
| `/data-coverage NIFTY500 --details` | Audit and list the worst-covered symbols |

### Portfolio

| Command | Description |
|---|---|
| `/pnl` | 💼 Live portfolio P&L — unrealised gains/losses from holdings.csv |
| `/agent-adda-small-cap-fund` | Daily Small Cap Portfolio command: buy/sell/add/trim/stop/target/news review |
| `/agent-adda-mid-cap-fund` | Daily Mid Cap Portfolio command: buy/sell/add/trim/stop/target/news review |

### Session

| Command | Description |
|---|---|
| `/live` | Switch to LIVE mode (real-time NSE API) |
| `/eod` | Switch to EOD mode (historical CSV/DB) |
| `/auto` | Switch to AUTO mode (keyword detect) |
| `/context` | Show conversation history & context budget |
| `/new` | Start a fresh session (clear history) |
| `/reset` | Start a fresh session (clear history) |
| `/clear` | Clear the screen |
| `/export` | Export session to HTML report |
| `/export html` | Export session to HTML file (opens in browser) |
| `/export pdf` | Export session to PDF (requires weasyprint or pdfkit) |

### Settings & Data

| Command | Description |
|---|---|
| `/model` | Show active main chat model/backend |
| `/model gpt-4o` | Switch main chat backend to OpenAI gpt-4o |
| `/model ollama` | Switch main chat backend to Ollama default model |
| `/model ollama granite4:latest` | Switch main chat backend to a specific Ollama model |
| `/model keyword` | Disable LLM backend and use deterministic keyword/tool routing |
| `/theme` | Show available color themes |
| `/theme dark` | Switch to Dark theme (default) |
| `/theme dracula` | Switch to Dracula theme |
| `/theme solarized` | Switch to Solarized Dark theme |
| `/theme high-contrast` | Switch to High Contrast theme |
| `/theme nord` | Switch to Nord theme |
| `/scale` | Show layout scale options |
| `/scale compact` | Compact layout — fits small terminals |
| `/scale normal` | Normal layout — default balanced layout |
| `/scale large` | Large layout — wide terminals / big screens |
| `/refresh` | Run data refresh pipeline (snapshot mode) |
| `/refresh snapshot` | Fast snapshot: skip analysis, just update stage DB |
| `/refresh live` | Live prices only — fastest (~30s) |
| `/refresh full` | Full pipeline: R bhavcopy + analysis + snapshot |
| `/refresh analysis` | Analysis + snapshot (skips aux data fetch) |
| `/refresh status` | Check if refresh is running |
| `/refresh stop` | Stop a running refresh |
| `/data-status` | Check technical/fundamental DB readiness |
| `/doctor` | Check PostgreSQL process, DSN, schemas, tables, and source readiness |
| `/doctor --repair` | Create/repair core PostgreSQL schemas and then rerun doctor checks |
| `/refresh-data` | Run readiness refresh if DB is stale or partial |
| `/refresh-data --check` | Show the refresh plan without running it |

### Help

| Command | Description |
|---|---|
| `/help` | Show all commands (table of contents) |
| `/help charts` | Help: charts section |
| `/help screens` | Help: EOD screeners |
| `/help scan` | Help: intraday scanner |
| `/help fno` | Help: F&O / options |
| `/help search` | Help: deep search engine |
| `/help forensic` | Help: forensic accounting |
| `/help monitors` | Help: background monitors & alerts |
| `/help ric` | Help: recursive investigations |
| `/help refresh` | Help: data refresh |
| `/help appearance` | Help: themes & scale |
| `/help macro` | Help: seasonal & macro |
| `/commands` | Browse all slash commands by category |
| `/commands alert` | Filter commands by keyword, e.g. /commands pdf |

## Full Prompt Library

Run any prompt with `p<number>`. Use `/prompts <category>` to filter inside Agent Adda.

### 📊 Market Overview

| Shortcut | Title | Prompt text |
|---|---|---|
| `p1` | Market Pulse | Give me a full live market overview — NIFTY 50, BANK, IT, MID, SMALL indices with breadth, FII/DII flow, and stage distribution. |
| `p2` | Breadth Snapshot | Show current market breadth: advance/decline ratio, RS distribution by percentile, stage 1-4 stock counts, and what it signals. |
| `p3` | FII vs DII Flow | Compare today's FII and DII activity in crores. Who is buying, who is selling, and what does the institutional flow tell us? |
| `p4` | Top Movers Today | Top 5 gainers and top 5 losers in NIFTY 50 today with % change, volume context, and possible reasons. |
| `p5` | Most Active Stocks | Which stocks have the highest trading volume and value today? Show most active by value from NIFTY 500. |
| `p6` | 52-Week Extremes | List stocks nearest to their 52-week high in NIFTY 500 — these are the strongest trending names right now. |

### ⚡ Intraday Trading

| Shortcut | Title | Prompt text |
|---|---|---|
| `p7` | Bank Nifty Scan | Scan NIFTY BANK for intraday research setups using all strategies on 15m charts. Show technical target zones, invalidation levels, and risk context. |
| `p8` | Nifty 50 Scan | Scan NIFTY 50 for the best intraday setups right now — momentum, breakouts, and mean-reversion on 15m candles. |
| `p9` | Nifty IT Scan | Scan NIFTY IT index for intraday signals. Focus on MACD and EMA crossovers. |
| `p10` | RELIANCE Intraday | Intraday research setup for RELIANCE on 15m — setup label, technical target zones, invalidation level, pivot levels, and key indicators. |
| `p11` | VCP Pattern Hunt | Scan NIFTY 500 for VCP (Volatility Contraction Pattern) stocks ready for intraday breakout on 15m. |
| `p12` | Volume Spike Alert | Which NIFTY 50 or BANK NIFTY stocks are showing 2x+ volume spikes with price confirmation right now? |
| `p13` | Supertrend Setups | Scan NIFTY MIDCAP 100 for stocks with active Supertrend research setups on 15m with clear invalidation levels. |

### 📈 Technical Analysis

| Shortcut | Title | Prompt text |
|---|---|---|
| `p14` | Stage 2 Breakouts | Show me stocks currently in Weinstein Stage 2 with recent breakouts — RS rank high, volume expanding. |
| `p15` | Supertrend BUY Sweep | Run the supertrend_buy screener and show the top 10 names with stage, RSI, RS%, and 1-month returns. |
| `p16` | Strong Buy Signals | Which stocks have strong_buy signals right now? Show technicals: stage, RSI, ADX, MACD, RS rank. |
| `p17` | ADX Trend Leaders | Find stocks with ADX > 30 (strong trend) and positive DI+ vs DI−. These are the trending names to watch. |
| `p18` | NIFTY 50 Technicals | Full technical setup for NIFTY 50 index — RSI, MACD, Supertrend, key support/resistance, 50/200 MA position. |
| `p19` | BANK NIFTY Setup | Technical setup for BANK NIFTY — current trend, key levels, indicators, and what to expect next. |
| `p20` | 52W High Breakouts | List stocks that are within 5% of their 52-week high from NIFTY 500 — potential breakout candidates. |

### 🏭 Sector Analysis

| Shortcut | Title | Prompt text |
|---|---|---|
| `p21` | IT Sector Health | Analyse the IT sector — breadth, stage distribution, RS vs Nifty, leaders and laggards, and key themes. |
| `p22` | Banking Sector | Banking sector deep dive — BANK NIFTY trend, top PSU vs private banks, NPA concerns vs growth stocks. |
| `p23` | Pharma Sector | Pharma sector analysis — sector trend, stage distribution, top performers, USFDA/regulatory watch. |
| `p24` | Auto Sector | Auto sector outlook — EV transition stocks, two-wheelers vs passenger vehicles, volumes data context. |
| `p25` | FMCG vs Consumer | Compare FMCG sector vs Consumer Discretionary — which is showing more Stage 2 stocks and better RS? |
| `p26` | Top Sector Today | Which sectors are leading the market today? Show sector-wise performance and breadth right now. |
| `p27` | Sector Rotation | Where is smart money rotating? Analyse sector RS trends over last 1 month — which sectors are gaining/losing momentum? |

### 🔬 Screeners

| Shortcut | Title | Prompt text |
|---|---|---|
| `p28` | Stage 2 Universe | Show all stocks currently in Weinstein Stage 2 (advancing). Filter by RS > 60 and sort by 1-month returns. |
| `p29` | Breakout Candidates | Run the breakouts screener — stocks with price near pivot, high RS rank, volume build-up, in Stage 2. |
| `p30` | High RS Stocks | List the top 20 stocks by Relative Strength percentage rank vs NIFTY 50. These are the market leaders. |
| `p31` | Investment Grade | Which stocks have the highest investment scores combining fundamentals + technicals? Top 15 names. |
| `p32` | Recovery Plays | Show stocks transitioning from Stage 1 (basing) to Stage 2 (advancing) — early movers with rising RS. |
| `p33` | Momentum Movers | Top 10 stocks with the best 1-week and 1-month returns with RSI still below 75 — not yet overbought. |

### 🏦 Fundamentals

| Shortcut | Title | Prompt text |
|---|---|---|
| `p34` | TCS Full Analysis | Full fundamental analysis of TCS — P/E, P/B, ROE, ROCE, revenue growth, debt, pros/cons from screener.in. |
| `p35` | HDFC Bank Valuation | HDFC Bank valuation deep dive — P/B vs peers, NIM trend, ROE, capital adequacy, screener.in fundamentals. |
| `p36` | IT Sector P/E Compare | Compare P/E, ROE, ROCE, and revenue growth of TCS vs INFY vs WIPRO vs HCL TECH vs LTIM. |
| `p37` | High ROE Low PE | Find NSE stocks with ROE > 20% and P/E < 25 — quality at reasonable price (GARP) screen. |
| `p38` | Debt-Free Companies | Show debt-free or near-zero debt companies in NIFTY 500 with ROE > 15% and earnings growth. |
| `p39` | Concall Summary | Get the latest concall transcript and key management commentary for RELIANCE from screener.in. |
| `p40` | Peer Comparison | Compare RELIANCE vs ONGC vs BPCL — P/E, EV/EBITDA, ROE, dividend yield, and technical stage. |

### 🔍 Stock Deep Dive

| Shortcut | Title | Prompt text |
|---|---|---|
| `p41` | RELIANCE Full View | Everything on RELIANCE — live price, technical setup, fundamentals from screener.in, recent news, sector context, and intraday levels. |
| `p42` | INFOSYS Analysis | Full analysis of INFOSYS — stage, technicals, P/E vs peers, recent quarterly results, and trading setup. |
| `p43` | ADANI ENTERPRISES | Research ADANI ENTERPRISES — technical stage, RS rank, fundamentals, FII/DII holding changes, latest news. |
| `p44` | ZOMATO Setup | ZOMATO current setup — Stage analysis, RSI, MACD, support/resistance, fundamental burn rate and path to profitability. |
| `p45` | TATA MOTORS View | TATA MOTORS — JLR performance, EV segment, technical setup, sector context, valuation vs global peers. |
| `p46` | SBI Deep Dive | SBI complete analysis — NPA trend, ROE, P/B vs HDFC, technical stage, FII holding, and key catalysts. |

### 📰 News & Catalysts

| Shortcut | Title | Prompt text |
|---|---|---|
| `p47` | Today's Top News | What are the top market-moving news stories today? Search moneycontrol, ET, NSE announcements. |
| `p48` | Results Calendar | Which companies are announcing quarterly results this week? What are the expected earnings and market reaction? |
| `p49` | FII Bulk Deals Today | Show today's bulk deals and block deals — who is buying, who is selling, and what sizes? |
| `p50` | Macro Events Week | What are the key macro events this week — RBI, Fed, CPI data, F&O expiry — and how should traders position? |
| `p51` | Nifty News Flow | Latest news and catalysts affecting NIFTY 50 — policy updates, global cues, sector rotation triggers. |

### 📋 Portfolio

| Shortcut | Title | Prompt text |
|---|---|---|
| `p52` | Portfolio Exposure | Show my portfolio sector distribution and concentration. Which sectors am I overweight or underweight? |
| `p53` | Portfolio vs Stage2 | Which of my portfolio holdings are in Weinstein Stage 2? Which are in Stage 3 or 4 and need review? |
| `p54` | Portfolio vs Screen | Which of my holdings match the current strong_buy screener? Are my best performers the ones with best signals? |
| `p55` | Holdings Health | Evaluate my portfolio holdings — stage, RSI, RS rank, and 1-month returns for each position. |

### 🌍 Global & Macro

| Shortcut | Title | Prompt text |
|---|---|---|
| `p56` | Global Market Check | What happened in US, Asian, and European markets overnight? SGX Nifty cues for India's open. |
| `p57` | USD/INR Impact | How is USD/INR moving today and what is the impact on IT exporters, importers, and metal stocks? |
| `p58` | Crude Oil Effect | Current crude oil price and its impact on OMCs, aviation stocks, paint sector, and tyre companies. |
| `p59` | FII Net Position | FII net activity this month — cumulative buying/selling, which sectors saw inflows, and what it implies for Nifty. |
| `p60` | India vs Emerging | How is India performing vs other emerging markets (China, Brazil, Korea) this month? Relative outperformance? |

### 📧 Email Pipe

| Shortcut | Title | Prompt text |
|---|---|---|
| `p61` | Mail FII/DII flows | Compare today's FII and DII activity in crores. Who is buying, who is selling, and what does the institutional flow tell us? \| /email --to pgorai@deloitte.com |
| `p62` | Mail insider alerts | Show the top 15 insider/promoter alerts today with action, score, and symbol. \| /email --to pgorai@deloitte.com |
| `p63` | Mail corporate events | List the next 20 upcoming corporate events — results, board meetings, ex-dividends. \| /email --to pgorai@deloitte.com |
| `p64` | Mail sector breadth | Show current sector breadth snapshot — advance/decline by sector with leaders and laggards. \| /email --to pgorai@deloitte.com |
| `p65` | Mail macro proxies | Macro proxy signals snapshot — USD/INR, crude, bond yields, gold and what they imply for Nifty. \| /email --to pgorai@deloitte.com |
| `p66` | Mail seasonal returns | Show seasonal monthly returns for Nifty and major sectors over the last 10 years. \| /email --to pgorai@deloitte.com |
| `p67` | Mail global indices | What happened in US, Asian, and European markets overnight? SGX Nifty cues. \| /email --to pgorai@deloitte.com |
| `p68` | Mail signal log | Show the 15 most recent trading signals across the universe with stage, RS, and action. \| /email --to pgorai@deloitte.com |
| `p69` | Mail voice briefing | Read out today's voice briefing script (no audio) with the key market call-outs. \| /email --to pgorai@deloitte.com |
| `p70` | Mail sector rotation | /email sector --to pgorai@deloitte.com |
| `p71` | Mail RIC Sherlock DMART | /ric sherlock DMART \| /email --to pgorai@deloitte.com |
| `p72` | Mail Strategy Council | Run Strategy Council on RELIANCE and show the consolidated verdict. \| /email --to pgorai@deloitte.com |
| `p73` | Mail top movers | Top 5 gainers and top 5 losers in NIFTY 50 today with % change and signal label. \| /email --to pgorai@deloitte.com |
| `p74` | Mail Nifty pulse | Full live market overview — NIFTY 50, BANK, IT, Pharma, Metal indices with breadth. \| /email --to pgorai@deloitte.com |
| `p75` | Mail Stage 2 summary | /email stage2 --to pgorai@deloitte.com |
| `p76` | Mail F&O signals | Show the top 12 F&O signals today with PCR, buildup, and direction. \| /email --to pgorai@deloitte.com |
| `p77` | Mail results feed | Companies announcing results in the next 24 hours with event details. \| /email --to pgorai@deloitte.com |
| `p78` | Mail market dashboard | /email dashboard --to pgorai@deloitte.com |
| `p79` | Mail data coverage | Run /data-coverage and summarize EOD history audit + Postgres row counts. \| /email --to pgorai@deloitte.com |
| `p80` | Mail morning intel | /ric morning-intel \| /email --to pgorai@deloitte.com |
| `p81` | Mail breadth history | Show market breadth history for last 10 sessions — advances, declines, A/D ratio. \| /email --to pgorai@deloitte.com |
| `p82` | Mail portfolio P&L | Show my portfolio P&L snapshot — qty, avg cost, LTP, P&L, return per holding. \| /email --to pgorai@deloitte.com |
| `p83` | Mail regime detector | Run regime detection — trend score, breadth thrust, volatility, sector dispersion. \| /email --to pgorai@deloitte.com |
| `p84` | Mail pullback picks | Show pullback recovery candidates — Stage 2 stocks with recent 5-10% drawdowns. \| /email --to pgorai@deloitte.com |
| `p85` | Mail Company Xray DMART | /ric company-xray DMART \| /email --to pgorai@deloitte.com |

## Related Files

- Runtime command registry: `nse_agent.py::_SLASH_COMMANDS`
- Runtime prompt registry: `nse_agent.py::PROMPT_LIBRARY`
- Curated help sections: `terminal/help.py::SECTIONS`
- Email dispatcher: `terminal/email_dispatcher.py`
- Capability overview: `NSE_AGENT_CAPABILITIES.md`
