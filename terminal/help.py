"""
terminal/help.py — First-class help system for Agent Adda
  /help             → compact TOC
  /help <section>   → full section detail
  /help <keyword>   → search across all commands + descriptions
"""
from __future__ import annotations
from typing import NamedTuple
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box

# ─────────────────────────────────────────────────────────────────────────────
# Help data model
# ─────────────────────────────────────────────────────────────────────────────

class HelpEntry(NamedTuple):
    cmd: str          # e.g. "/chart RELIANCE 6mo"
    desc: str         # short description
    section: str      # section key


_HELPFILE_SECTION_ALIASES = {
    "all": "all slash commands",
    "helpfile": "all slash commands",
    "pipe": "email piping: detailed usage",
    "piping": "email piping: detailed usage",
    "email pipe": "email piping: detailed usage",
    "email piping": "email piping: detailed usage",
    "prompt library": "full prompt library",
    "full prompts": "full prompt library",
    "slash commands": "all slash commands",
    "commands": "all slash commands",
}


# ─────────────────────────────────────────────────────────────────────────────
# All help entries — one source of truth
# ─────────────────────────────────────────────────────────────────────────────

SECTIONS: dict[str, dict] = {
    "modes": {
        "title":  "Mode Commands",
        "icon":   "🔀",
        "color":  "cyan",
        "aliases": ["mode", "modes", "live", "eod", "auto"],
        "entries": [
            ("/live  or  /l",       "Live / Intraday  (real-time NSE API)"),
            ("/eod  or  /e",        "EOD / Historical (CSV + DB snapshot)"),
            ("/auto  or  /a",       "Auto-detect from query keywords"),
        ],
    },
    "screens": {
        "title":  "EOD Screeners",
        "icon":   "🔎",
        "color":  "cyan",
        "aliases": ["screen", "screener", "screeners", "stage2", "momentum", "rs"],
        "entries": [
            ("/screen stage2",      "Stage 2 uptrend stocks (William O'Neil buy zone)"),
            ("/screen momentum",    "Near-52W-high momentum leaders"),
            ("/screen highrs",      "High RS + change_1m > 8% market leaders"),
            ("/screen turnaround",  "Dip recovery setups — RSI 40–65, rising"),
            ("/screen base",        "Stage 1 basing/coiling — pre-breakout"),
            ("/screen tight",       "Tight weekly range (VCP-like consolidation)"),
            ("/screen dip",         "Oversold bounce in Stage 2 — RSI < 40"),
            ("/screen quality-breakouts", "New highs + VCP-like + breakouts with fundamental quality overlay"),
            ("/screen quality-breakouts --explain --tv", "Show filter trail and TradingView-ready symbols"),
            ("/screen supertrend",  "Supertrend BULLISH state + Stage 1/2"),
            ("/screen strong",      "HOLD/BUY + Stage 2 + BULLISH supertrend"),
            ("/screen new",         "New Stage 2 entrants (last 14 days)"),
        ],
    },
    "mtf": {
        "title":  "Multi-Timeframe (MTF) Confluence",
        "icon":   "📐",
        "color":  "cyan",
        "aliases": ["mtf", "multi-timeframe", "multitimeframe", "confluence", "timeframe"],
        "entries": [
            ("/mtf RELIANCE",                     "MTF panel: verdict + score across M/W/D/60m/15m"),
            ("/mtf RELIANCE --report",            "MTF panel + markdown report to reports/mtf/"),
            ("/mtf scan NIFTY50 bullish",         "Rank Nifty 50 by bullish MTF confluence (top 10)"),
            ("/mtf scan NIFTY50 bearish",         "Rank Nifty 50 by bearish MTF confluence"),
            ("/mtf scan NIFTY500 bullish --min-score 80", "Universe scan with custom min-score"),
            ("/mtf scan BANKNIFTY bullish",       "Sector/index scan (BANKNIFTY, FINNIFTY, MIDCAP100…)"),
            ("/mtf RELIANCE | /email --to a@x.com", "Email the rendered panel as HTML attachment"),
        ],
    },
    "scan": {
        "title":  "Intraday Scanner",
        "icon":   "⚡",
        "color":  "green",
        "aliases": ["scan", "intraday", "orb", "vwap", "gap", "macd", "vcp"],
        "entries": [
            ("/scan",                       "Scan NIFTY 50 — all strategies, 15m candles"),
            ("/scan NIFTY BANK",            "Scan any index (NIFTY IT, PHARMA, MIDCAP…)"),
            ("/scan orb",                   "Opening Range Breakout"),
            ("/scan gap",                   "Gap & Go continuation"),
            ("/scan macd",                  "MACD Crossover"),
            ("/scan rsi",                   "RSI Divergence + Bollinger"),
            ("/scan bb",                    "Bollinger Band Squeeze"),
            ("/scan vwap",                  "VWAP Reclaim/Loss"),
            ("/scan vcp",                   "VCP Contraction Pattern"),
            ("/scan momentum",              "MACD + RSI + Supertrend aligned"),
        ],
    },
    "charts": {
        "title":  "Charts",
        "icon":   "📈",
        "color":  "green",
        "aliases": ["chart", "charts", "html", "ascii", "candle", "visual-scan"],
        "entries": [
            ("/chart RELIANCE",             "ASCII candlestick (3mo, volume + RSI)"),
            ("/chart NIFTY 6mo rsi macd",   "Custom timeframe + indicators"),
            ("/chart RELIANCE --html",       "Interactive HTML chart → browser"),
            ("/chart NIFTY 1y --html",       "1-year interactive HTML chart"),
            ("",                            "Timeframes: 1d · 5d · 1mo · 3mo · 6mo · 1y · 2y"),
            ("",                            "Indicators: volume · rsi · macd"),
        ],
    },
    "fno": {
        "title":  "F&O / Options",
        "icon":   "📊",
        "color":  "yellow",
        "aliases": ["fno", "options", "chain", "oi", "pcr", "straddle", "greeks"],
        "entries": [
            ("/options NIFTY",                      "Live options chain (PCR, max pain, IV)"),
            ("/options BANKNIFTY",                  "BANKNIFTY options chain (nearest expiry)"),
            ("/options NIFTY 1",                    "NIFTY next expiry (index 1)"),
            ("/chain NIFTY",                        "Full chain: OI, greeks, PCR, max pain"),
            ("/oi NIFTY",                           "OI analysis (support/resistance, PCR)"),
            ("/fno NIFTY",                          "Full F&O overview (chain + futures + strategy)"),
            ("/strategy NIFTY long_straddle",       "Build a specific options strategy"),
            ("/strategy NIFTY bull_call_spread",    "Bull call spread with pricing"),
            ("",                                    "Strategies: long_call · long_put · bull_call_spread · bear_put_spread · long_straddle · long_strangle · iron_condor · covered_call · protective_put · calendar_spread"),
        ],
    },
    "search": {
        "title":  "Deep Search Engine",
        "icon":   "🔍",
        "color":  "magenta",
        "aliases": ["search", "deep", "news", "insider", "analyst", "broker", "mf", "concall", "social", "shareholding", "results", "latest results", "results-feed", "latest-results"],
        "entries": [
            ("/search RELIANCE",                "Full deep-dive (11 parallel verticals)"),
            ("/results RELIANCE",               "Latest quarterly results, filings, concalls, catalysts"),
            ("/results-feed",                   "Market-wide latest quarterly results filings, default last 2 weeks"),
            ("/results-feed --weeks 4",         "Market-wide latest results filings over the last 4 weeks"),
            ("/latest-results 2",               "Alias for latest quarterly results feed over N weeks"),
            ("/search RELIANCE dividend",       "Dividends, splits, bonuses (NSE live)"),
            ("/search RELIANCE insider",        "Insider/promoter trade disclosures"),
            ("/search RELIANCE shareholding",   "Promoter/FII/DII/pledge trend"),
            ("/search RELIANCE analyst",        "Analyst targets + broker reports"),
            ("/search RELIANCE broker",         "Broker house research & price targets"),
            ("/search RELIANCE mf",             "Mutual fund & institutional holdings"),
            ("/search RELIANCE concall",        "Concall transcripts & mgmt commentary"),
            ("/search RELIANCE news",           "6-portal sector news pulse"),
            ("/search RELIANCE social",         "Reddit, Valuepickr, Traderji buzz"),
        ],
    },
    "learn": {
        "title":  "Market Knowledge",
        "icon":   "📚",
        "color":  "cyan",
        "aliases": ["learn", "define", "education", "investopedia", "wikipedia", "pe", "roe", "roce", "minervini"],
        "entries": [
            ("/learn PE ratio",                 "Explain a market concept using Investopedia + Wikipedia"),
            ("/define ROCE",                    "Define a finance/accounting ratio with source URLs"),
            ("/compare ROCE ROE",               "Compare two market concepts with source-backed context"),
            ("/learn Minervini trading strategy", "Explain a trading framework with evidence-first caveats"),
            ("what is PE?",                     "Natural-language education questions route here automatically"),
            ("How is ROCE different from ROE?", "Concept comparisons route here automatically"),
        ],
    },
    "youtube": {
        "title":  "YouTube Market Intelligence",
        "icon":   "▶️",
        "color":  "red",
        "aliases": ["youtube", "video", "channels", "transcript", "transcribe"],
        "entries": [
            ("/youtube",             "List preset YouTube market channels"),
            ("/youtube 1",           "Fetch latest video for channel #1 and analyze available captions"),
            ("/youtube <channel>",   "Select a preset channel by name/id and analyze latest video"),
            ("/youtube <url>",       "Analyze a YouTube market video from available captions/metadata"),
            ("/youtube transcribe 1", "Explicitly run local speech-to-text for channel #1 latest video if captions are unavailable"),
            ("/youtube transcribe <url> --backend local|auto", "Explicitly run local audio speech-to-text if captions are unavailable"),
            ("/youtube channels",    "List preset YouTube market channels"),
            ("",                     "Default mode does not download audio/video; transcribe mode uses temporary audio and never stores full transcripts"),
        ],
    },
    "forensic": {
        "title":  "Forensic Accounting",
        "icon":   "🧪",
        "color":  "red",
        "aliases": ["forensic", "beneish", "piotroski", "altman", "fraud", "quality", "strength", "canslim"],
        "entries": [
            ("/forensic RELIANCE",          "Beneish M-score + Piotroski F-score + Altman Z'"),
            ("/forensic TCS INFY WIPRO",    "Forensic screen across multiple stocks"),
            ("/canslim RELIANCE",           "William O'Neil CANSLIM growth-quality framework"),
            ("/strength MANINDS THERMAX",   "Validate CANSLIM + RS + fundamentals + Piotroski without assumptions"),
            ("",                            "Beneish M > -1.78 = manipulation risk"),
            ("",                            "Piotroski F: 7+ = strong, 0–3 = weak"),
            ("",                            "Altman Z' < 1.1 = distress zone"),
        ],
    },
    "email": {
        "title":  "Report Mailer",
        "icon":   "✉️",
        "color":  "blue",
        "aliases": ["email", "mail", "send", "bcc", "report-mail", "<cmd>"],
        "entries": [
            ("/email sector --to a@x.com",                      "LLM-drafted email · attaches sector_rotation.html"),
            ("/email dashboard --to a@x.com",                   "Auto-picks newest market dashboard (alias: market | pulse)"),
            ("/email stage2 --to a@x.com --bcc b@y.com --send", "Send Stage 2 tracker immediately (no draft review)"),
            ("/email sector --to \"a@x.com;b@y.com\"",          "Multi-recipient — comma, semicolon or whitespace"),
            ("/email sector --to a@x.com --as body",            "Inline HTML body only — no attachment"),
            ("/email <path> --to a@x.com --dry-run",            "Preview HTML in logs/ without opening Outlook"),
            ("<cmd> | /email --to a@x.com",                     "Pipe upstream output as email body (e.g. `/ric sherlock DMART | /email --to a@x.com`)"),
            ("",                                                "Aliases: sector | stage2 | index | portfolio | seasonal | us | dashboard | market | pulse"),
            ("",                                                "Modes: --as body | attachment | both (default)"),
            ("",                                                "Pipe: captured terminal output → `reports/generated/piped_*.md` → /email"),
            ("",                                                "Sends via Microsoft Outlook (macOS) AppleScript"),
        ],
    },
    "screenshot": {
        "title":  "Screen Capture Mailer",
        "icon":   "📸",
        "color":  "blue",
        "aliases": ["screenshot", "snap", "capture", "screencap"],
        "entries": [
            ("/screenshot --to a@x.com",                          "Default: drag a selection box (Esc cancels), then mail PNG"),
            ("/screenshot --mode window --to a@x.com",            "Click a window to capture it, then mail"),
            ("/screenshot --mode full --to a@x.com --send",       "Full screen capture, send immediately (skip Outlook draft)"),
            ("/screenshot --mode delayed --to a@x.com",           "5-second timer before capturing full screen"),
            ("/screenshot --to \"a@x.com;b@y.com\" --bcc c@z.com", "Multi-recipient; same separator rules as /email"),
            ("/screenshot --no-email --out ~/Desktop/shot.png",   "Capture only — save to disk, no email"),
            ("/screenshot --to a@x.com --note \"Stage 2 chart\"",  "Add context for the LLM cover-note composer"),
            ("/screenshot --to a@x.com --dry-run",                "Preview HTML body in logs/ without opening Outlook"),
            ("",                                                  "Default save location: reports/screenshots/screenshot_<mode>_<ts>.png"),
            ("",                                                  "Email is sent as an attachment with an LLM-drafted cover note"),
        ],
    },
    "events": {
        "title":  "Event Calendar",
        "icon":   "📅",
        "color":  "yellow",
        "aliases": ["events", "calendar", "dividends", "results", "agm", "board"],
        "entries": [
            ("/events",                 "Upcoming events for NIFTY 50 (next 14 days)"),
            ("/events NIFTY 50",        "Dividends, splits, results, AGMs, board meetings"),
            ("/events RELIANCE",        "Upcoming events for a specific stock"),
            ("/events NIFTY 50 30",     "Extend window to 30 days"),
        ],
    },
    "macro": {
        "title":  "Seasonal & Macro",
        "icon":   "🌡",
        "color":  "blue",
        "aliases": ["heat", "cycle", "scenario", "narrative", "voice", "macro", "seasonal", "concall", "global", "dashboard", "dash", "us"],
        "entries": [
            ("/dashboard",              "Auto-refreshing stock-market-TV dashboard + LLM narrative, heatmap, news, movers"),
            ("/dash",                   "Alias for /dashboard"),
            ("/recap",                  "Last 15-minute intraday market recap from PostgreSQL snapshots"),
            ("/recap 30",               "Custom-window intraday market recap, e.g. last 30 minutes"),
            ("/heat",                   "Sector seasonal heatmap (current month)"),
            ("/heat 3",                 "Seasonal signals for March"),
            ("/cycle",                  "Economic cycle phase + sector positioning"),
            ("/scenario TCS",           "What-if price scenarios for TCS"),
            ("/narrative",              "Portfolio investment narratives"),
            ("/narrative TCS INFY",     "Narratives for specific stocks"),
            ("/voice",                  "Generate daily voice briefing (MP3)"),
            ("/voice script",           "Print daily voice briefing script only"),
            ("/voice-mode on",          "Speak every typed Agent Adda answer"),
            ("/voice-live",             "Live voice assistant loop: listen, answer, speak, repeat"),
            ("/ask-voice",              "Record a spoken question and speak the answer"),
            ("/concall TCS",            "Concall NLP: sentiment + themes + guidance"),
            ("/global",                 "Global risk regime and India read-through"),
            ("/us",                     "US/global market summary + report"),
            ("/us indices",             "US index tape: SPY, QQQ, Nasdaq, Dow, Russell, VIX"),
            ("/us sectors",             "US sector ETF rotation"),
            ("/us stage2",              "US Stage 2 leaders"),
            ("/us vcp",                 "US VCP setups"),
            ("/us stock NVDA",          "US stock technical context with report link"),
        ],
    },
    "monitors": {
        "title":  "Background Monitors",
        "icon":   "🔔",
        "color":  "magenta",
        "aliases": ["monitor", "monitors", "alert", "alerts", "background", "notification", "live-intraday", "live_intraday_alert", "ive_intraday_alerts"],
        "entries": [
            ("/monitor",                            "Show active monitors + latest scan results"),
            ("/monitor list",                       "Show available strategies"),
            ("/monitor status",                     "Show active monitors"),
            ("/monitor start breakout",             "Start breakout alert every 15m"),
            ("/monitor start all 15 buy",           "All strategies, 15m, BUY only"),
            ("/monitor start momentum NIFTY BANK 10", "Custom index + interval"),
            ("/monitor stop breakout",              "Stop a specific monitor"),
            ("/monitor stop all",                   "Stop all monitors"),
            ("/alert add RELIANCE price > 1500",    "Add watchlist price alert"),
            ("/alert list",                         "Show all active alerts"),
            ("/alert monitor",                      "Start background alert polling"),
            ("/intraday-alerts",                    "Live intraday F&O commentary with trigger email alerts"),
            ("/live-intraday",                      "Alias for /intraday-alerts"),
            ("/live_intraday_alert",                "Alias for /intraday-alerts"),
            ("/live_intraday_alerts",               "Alias for /intraday-alerts"),
        ],
    },
    "ric": {
        "title":  "RIC — Recursive Investigations",
        "icon":   "🕵",
        "color":  "yellow",
        "aliases": ["ric", "recursive", "investigation", "sherlock", "xray", "earnings"],
        "entries": [
            ("/ric",                                "Show all 8 prebuilt RICs"),
            ("/ric sherlock RELIANCE",              "5-step stock investigation"),
            ("/ric sector-xray IT",                 "4-step sector deep dive"),
            ("/ric earnings-playbook TCS",          "5-step earnings analysis"),
            ("/ric breakout-hunter",                "5-step breakout scan"),
            ("/ric morning-intel",                  "5-step morning briefing"),
            ("/ric risk-radar",                     "4-step risk assessment"),
            ("/ric index-pulse NIFTY BANK",         "4-step index analysis"),
            ("/ric peer-battle TCS,INFY,WIPRO",     "4-step peer comparison"),
        ],
    },
    "portfolio": {
        "title":  "Portfolio & P&L",
        "icon":   "💼",
        "color":  "green",
        "aliases": ["pnl", "portfolio", "holdings", "profit", "loss", "my-portfolio", "fund", "smallcap", "midcap", "agent-adda-small-cap-fund", "agent-adda-mid-cap-fund"],
        "entries": [
            ("/my-portfolio",               "Open the first-class portfolio ledger: status, positions, transactions, P&L, alerts"),
            ("/my-portfolio intraday",      "Live intraday P&L + multi-strategy signals (auto-refreshes every 60s during market hours)"),
            ("/my-portfolio eod",           "Force full EOD comprehensive analysis (CANSLIM · Minervini · Fundamental · Value · RSI)"),
            ("/my-portfolio buy",           "Show only BUY / STRONG BUY stocks from your portfolio"),
            ("/my-portfolio sell",          "Show only SELL candidates — prioritised by loss depth"),
            ("/my-portfolio hold",          "Show only HOLD stocks — useful for monitoring"),
            ("/agent-adda-small-cap-fund",  "Daily Small Cap Portfolio command: buy/sell/add/trim/stop/target/news review"),
            ("/agent-adda-mid-cap-fund",    "Daily Mid Cap Portfolio command: buy/sell/add/trim/stop/target/news review"),
            ("/agent-adda-small-cap-fund --skip-run", "Summarize the latest generated smallcap monitor without refreshing"),
            ("/agent-adda-mid-cap-fund --skip-history", "Run midcap monitor using score-file technical proxy when live history refresh is unavailable"),
            ("",                            "Portfolio CSV: docs/my_portfolio.csv.csv (broker export format)"),
            ("",                            "EOD report auto-generates at 16:15 IST via daily_refresh.py"),
            ("",                            "Default HTML report: reports/latest/portfolio_analysis.html; intraday: portfolio_intraday.html"),
            ("/pnl",                        "Legacy: live portfolio P&L from data/holdings.csv"),
        ],
    },
    "company": {
        "title":  "Company Intelligence",
        "icon":   "🏢",
        "color":  "cyan",
        "aliases": ["company", "company-index", "company-xray", "xray", "website", "investor"],
        "entries": [
            ("/company-index DMART",              "Index company website + official investor documents"),
            ("/company-index DMART --include-documents", "Download discovered official investor documents"),
            ("/company-index DMART --max-pages 10 --document-limit 5", "Bounded company website/document index run"),
            ("/company-xray DMART",               "Company + Sector X-Ray from indexed evidence"),
            ("/company-xray DMART --strict",      "Run X-Ray with strict evidence coverage"),
            ("/diagnose DMART eps",               "Explain financial metric drivers such as EPS, ROCE, margins, debt, and cash flow"),
            ("/ric company-xray DMART",           "9-step company intelligence workflow"),
        ],
    },
    "governance": {
        "title":  "Governance Evaluation",
        "icon":   "🛡️",
        "color":  "cyan",
        "aliases": ["governance", "gov", "forensic-governance", "annual-report"],
        "entries": [
            ("/governance INFY",              "Governance evaluation from cached evidence"),
            ("/gov INFY",                     "Alias for /governance"),
            ("/governance INFY --live",       "Refresh NSE/Screener/annual-report evidence into data/governance/{SYMBOL}/"),
            ("/governance INFY --llm",        "Attach an LLM governance opinion"),
            ("/governance INFY --llm-read",   "Attach a page-referenced annual-report LLM review"),
            ("/governance INFY --live --llm", "Refresh evidence and attach an LLM governance opinion"),
            ("/governance INFY --live --llm-read", "Refresh evidence and attach an annual-report LLM review"),
            ("/governance INFY --json",       "Print machine-readable governance report JSON"),
        ],
    },
    "financial-rigor": {
        "title":  "Financial Rigor & Report Audit",
        "icon":   "🔎",
        "color":  "cyan",
        "aliases": ["financial-rigor", "valuation-check", "audit-report", "report-audit", "data-audit"],
        "entries": [
            ("/audit-report reports/latest/investment_checklist.md", "Extract auditable numeric claims from a generated Markdown report"),
            ("/audit-report reports/latest/top_picks.md --ratio 0.2 --seed 42", "Sample a reproducible claim-audit checklist"),
            ("/audit-report reports/latest/investment_checklist.md --json", "Print machine-readable audit sample JSON"),
            ("/financial-rigor INFY", "Exact valuation math from cached Screener evidence"),
            ("/financial-rigor INFY --json", "Print machine-readable valuation snapshot JSON"),
            ("/valuation-check INFY TCS HDFCBANK", "Compare valuation metrics from cached Screener evidence"),
            ("/valuation-check INFY TCS --json", "Print machine-readable multi-symbol valuation JSON"),
        ],
    },
    "skills": {
        "title":  "Skill Store",
        "icon":   "🧠",
        "color":  "cyan",
        "aliases": ["skills", "skillstore", "skill store", "skill-store", "runtime skills"],
        "entries": [
            ("/skills", "Show Skill Store status counts and runtime-eligible cards"),
            ("/skills search VCP fundamentals", "Search only validated/production Skill Store cards"),
            ("/skills show market_3m_rotation_swing_v1", "Show card contract, evidence requirements, and validation rules"),
            ("/skills recent", "Show recent retrieval logs and execution logs"),
        ],
    },
    "analyze": {
        "title":  "Research, Documents & Broker Notes",
        "icon":   "📄",
        "color":  "magenta",
        "aliases": ["research", "analyze", "assess-report", "document", "pdf", "docx", "webpage", "360", "broker"],
        "entries": [
            ("/research RELIANCE",                "Comprehensive 360° stock report: overview, fundamentals, technicals, chart, narrative"),
            ("/research RELIANCE pdf",            "Comprehensive stock report as PDF"),
            ("/broker-sources",                  "List PostgreSQL-backed broker research sources"),
            ("/broker-index BEL",                "Discover public broker reports for a symbol"),
            ("/broker-index BEL --broker icici", "Discover reports from one broker source"),
            ("/broker-fetch BEL --limit 10",     "Download and parse discovered broker PDFs"),
            ("/broker-crawl BEL --max-sources 4", "Bounded scheduled crawl of public broker indexes"),
            ("/broker-research BEL",             "Generate broker consensus report from stored facts"),
            ("/financial-research BEL --broker icici", "Generate financial analyst POV from stored broker evidence"),
            ("/investment-checklist TCS INFY HDFCBANK", "Compare NSE stocks using deterministic value checklist scoring"),
            ("/research-reports BEL",            "List dated cataloged research reports"),
            ("/open-research BEL",               "Open the latest financial research report"),
            ("/deep-research BEL --brokers public", "Publish deep broker research report"),
            ("/report broker BEL html",          "Render broker research report as HTML"),
            ("/analyze RELIANCE",                 "Broker-note ingest + internal DB critique"),
            ("/analyze report.pdf",               "Read and summarize a local PDF document"),
            ("/analyze annual_report.docx",       "Extract and summarize a Word document"),
            ("/analyze https://example.com",      "Scrape and analyze a web page"),
            ("/analyze ~/Downloads/concall.pdf",  "Analyze a concall transcript PDF"),
            ("/assess-report report.html RELIANCE", "Read an existing generated report and write an assessment sidecar"),
        ],
    },
    "reports": {
        "title":  "Reports",
        "icon":   "📝",
        "color":  "green",
        "aliases": ["report", "reports", "markdown", "html", "research-report"],
        "entries": [
            ("/report",                    "Generate a formatted report: HTML, Markdown, or PDF"),
            ("/report sector NIFTY DEFENCE", "Focused sector-specific report with candidates, technical notes, and editor view"),
            ("/report sector-rotation",    "Instant sector rotation dashboard from DB"),
            ("/report stage2",             "Stage 2 universe tracker: leaders and new entrants"),
            ("/report strategy-lab",       "Portfolio paper strategy leaderboard and risk diagnostics"),
            ("/report recommendation", "Grounded EOD recommendation report: market, sectors, stocks, portfolio/watchlist"),
            ("/report recommendation --watchlist RELIANCE,TCS --format md", "Grounded recommendation report for a watchlist"),
            ("/report technical RELIANCE", "Technical analysis report"),
            ("/report fundamental TCS pdf", "Fundamental report in PDF format"),
            ("/report forensic INFY md",   "Forensic accounting report in Markdown"),
            ("/report research HDFCBANK",  "Comprehensive 360° research report"),
            ("/report intraday SBIN",      "Intraday analysis report"),
            ("/report canslim TATAMOTORS", "CANSLIM quality report"),
            ("/report ric ADANIENT pdf",   "RIC investigation report in PDF"),
            ("/report sector IT",          "Focused sector-specific sector report"),
            ("/swing-playbook",            "Generate the swing trading playbook report"),
        ],
    },
    "strategy_lab": {
        "title":  "Strategy Lab & Council",
        "icon":   "🧪",
        "color":  "yellow",
        "aliases": ["backtest", "strategy lab", "strategy-lab", "strategy council", "strategy-council", "council", "simulation", "intraday-indicator-study"],
        "entries": [
            ("/backtest list",             "List EOD Strategy Lab strategies"),
            ("/strategy-lab validate",     "Validate EOD backtesting data readiness"),
            ("/strategy-lab run",          "Run portfolio replay, DB persistence, and HTML report"),
            ("/intraday-indicator-study --universe fno --timeframes 5m,15m", "Historical intraday F&O indicator leaderboard + report"),
            ("/strategy-council DMART",    "Iterative strategist + critic EOD simulation"),
            ("/strategy-council DMART --iterations 3 --horizon 1w,2w,4w", "Run with explicit iterations and horizons"),
            ("/strategy-council DMART --llm", "Use configured LLM strategist and critics with deterministic fallback"),
            ("/council today --horizon swing --risk moderate", "Research Council market scan with data steward, specialists, plan execution, critics, and report"),
            ("/council today --evidence-only --horizon swing", "Research Council evidence-pack and missing-evidence report without specialist deliberation"),
            ("/council sector NIFTY AUTO --horizon swing", "Research Council sector opportunity review with shortlist and quant sweep"),
            ("/council stock MODISONLTD --horizon swing", "Research Council stock deep dive"),
            ("/council compare APOLLO BEL HAL --horizon positional", "Compare stocks through the Research Council"),
            ("/council strategy \"Stage 2 breakout with volume confirmation\" --family stage2_breakout", "Strategy-build council with hypothesis and family"),
            ("/council intraday --scan vwap-reclaim", "Intraday tactical council scan"),
            ("/council steward", "Run Research Council data-readiness checks"),
            ("/council report --run latest --format html", "Open or render the latest Research Council report"),
            ("/council resume --run <id>", "Resume compact metadata for a persisted council run"),
        ],
    },
    "data": {
        "title":  "Data Operations",
        "icon":   "⚙️",
        "color":  "green",
        "aliases": ["refresh", "pipeline", "data", "snapshot", "bhavcopy", "doctor", "data status", "data-status", "refresh data", "refresh-data", "data coverage", "data-coverage", "load", "postgres", "postgresql"],
        "entries": [
            ("/data-status",             "Check technical/fundamental DB readiness"),
            ("/doctor",                 "Check PostgreSQL process, DSN, socket, schemas, tables, and row counts"),
            ("/doctor --repair",        "Create/repair core PostgreSQL schemas and rerun doctor checks"),
            ("/refresh-data --check",   "Show readiness refresh plan without running it"),
            ("/refresh-data",           "Run readiness refresh if DB is stale or partial"),
            ("/data-coverage NIFTY500", "Audit EOD history coverage for an index"),
            ("/data-coverage NIFTY500 --backfill", "Audit and yfinance-backfill symbols below threshold"),
            ("/data-coverage NIFTY500 --details", "List worst-covered symbols"),
            ("/refresh",                "Fast snapshot refresh (stage DB, ~1–2 min)"),
            ("/refresh live",           "Live prices only (~30s)"),
            ("/refresh full",           "Full pipeline: R bhavcopy → analysis → snapshot"),
            ("/refresh analysis",       "Analysis + snapshot (skips aux fetch)"),
            ("/refresh status",         "Check if refresh is running"),
            ("/refresh stop",           "Cancel a running refresh"),
        ],
    },
    "prompts": {
        "title":  "Prompt Library",
        "icon":   "📚",
        "color":  "yellow",
        "aliases": ["prompts", "prompt", "library", "p7", "p23", "market prompts", "intraday prompts", "technical prompts"],
        "entries": [
            ("/prompts",                "Browse 60 curated prompts"),
            ("/prompts market",         "Market overview prompts"),
            ("/prompts intraday",       "Filter by category"),
            ("/prompts technical",      "Technical analysis prompts"),
            ("/prompts sector",         "Sector analysis prompts"),
            ("/prompts screener",       "Screener prompts"),
            ("/prompts fundamentals",   "Fundamentals & valuation prompts"),
            ("/prompts stock",          "Stock deep-dive prompts"),
            ("/prompts news",           "News & catalysts prompts"),
            ("/prompts portfolio",      "Portfolio prompts"),
            ("/prompts global",         "Global & macro prompts"),
            ("/prompts email",          "Email-pipe prompts"),
            ("p<number>",               "Run prompt by number  (e.g. p7, p23)"),
        ],
    },
    "commands": {
        "title":  "Command Catalog",
        "icon":   "❓",
        "color":  "cyan",
        "aliases": ["command", "commands", "catalog", "all commands"],
        "entries": [
            ("/commands",               "Browse every registered slash command by category"),
            ("/commands alert",         "Filter the exhaustive command catalog by keyword"),
            ("/help <section>",         "Open curated details for a command family"),
            ("/help <keyword>",         "Search curated help plus the full slash-command catalog"),
        ],
    },
    "copilot": {
        "title":  "Copilot Workflows",
        "icon":   "🧠",
        "color":  "magenta",
        "aliases": ["copilot", "brainstorm", "plan", "debug", "review", "verify", "superpowers"],
        "entries": [
            ("/brainstorm <topic>",      "Structure design discussion with assumptions, approaches, recommendation, approval gate"),
            ("/plan <objective>",        "Create an implementation-ready task plan without executing it"),
            ("/plan <objective> --write", "Write the plan under docs/superpowers/plans/ without overwriting"),
            ("/debug <issue>",           "Create a systematic investigation plan; no files modified by default"),
            ("/review <path|target>",    "Findings-first review of an artifact or workflow"),
            ("/status",                  "Show current copilot task memory, latest artifacts, issues, and next actions"),
            ("/status clear",            "Clear local copilot task memory"),
            ("/verify reports",          "Check latest report artifacts and show pass/warn status"),
            ("/verify data",             "Check key data readiness artifacts"),
            ("/verify portfolio",        "Check portfolio source and latest portfolio reports"),
            ("/verify screen quality-breakouts", "Show quality-breakout verification checks"),
        ],
    },
    "export": {
        "title":  "Session Export",
        "icon":   "📤",
        "color":  "cyan",
        "aliases": ["export", "pdf", "html", "save", "session"],
        "entries": [
            ("/export",                 "Export session to HTML (dark-theme)"),
            ("/export pdf",             "Export session to PDF"),
            ("/export html RELIANCE",   "Tag export with a symbol name"),
        ],
    },
    "appearance": {
        "title":  "Appearance",
        "icon":   "🎨",
        "color":  "magenta",
        "aliases": ["theme", "scale", "appearance", "color", "font", "size", "dracula", "nord", "solarized", "style", "verbosity", "steps"],
        "entries": [
            ("/theme",              "Browse & switch color themes"),
            ("/theme dracula",      "Switch to Dracula theme"),
            ("/theme dark",         "Dark (default)"),
            ("/theme solarized",    "Solarized"),
            ("/theme high-contrast","High contrast"),
            ("/theme nord",         "Nord"),
            ("/scale",              "Browse & switch layout scale"),
            ("/scale compact",      "Compact: 80×16 columns"),
            ("/scale normal",       "Normal: 100×20 columns (default)"),
            ("/scale large",        "Large: 120×28 — wide charts, spacious tables"),
            ("/style",              "Show Agent Adda interaction style"),
            ("/style codex",        "Direct copilot style: assumptions, steps, verification, next actions"),
            ("/verbosity concise",  "Use shorter responses"),
            ("/verbosity normal",   "Use normal response depth"),
            ("/verbosity deep",     "Use deeper explanations where useful"),
            ("/steps on",           "Always show execution steps for supported workflows"),
            ("/steps auto",         "Show steps for composite/deep workflows"),
            ("/steps off",          "Hide execution-step trail"),
        ],
    },
    "permissions": {
        "title":  "Permission Mode",
        "icon":   "🛡️",
        "color":  "cyan",
        "aliases": ["permission", "permissions", "permission mode", "permissionmode", "plan mode", "bypass", "approve", "approvals", "dontask"],
        "entries": [
            ("/mode",                   "Show the current permission mode"),
            ("/mode help",              "List every supported mode + meaning"),
            ("/mode default",           "Default: prompt for tool approvals"),
            ("/mode auto",              "Auto-approve safe tools, prompt for risky ones"),
            ("/mode dontAsk",           "Never prompt; run any whitelisted tool"),
            ("/mode plan",              "Plan mode: render the plan, do NOT execute"),
            ("/mode bypassPermissions", "Bypass all permission checks (use with care)"),
            ("--permission-mode plan",  "CLI flag — start a session in plan mode"),
            ("--mode auto",             "CLI flag alias — start in auto-approve mode"),
        ],
    },
    "session": {
        "title":  "Session & Context",
        "icon":   "💬",
        "color":  "cyan",
        "aliases": ["context", "new", "reset", "session", "clear", "history", "model", "mode", "permission", "commands", "help"],
        "entries": [
            ("/commands",           "Browse all slash commands by category"),
            ("/commands alert",     "Filter commands by keyword, e.g. /commands alert"),
            ("/help",               "Show this help table of contents"),
            ("/help charts",        "Open a detailed help section"),
            ("/help rsi",           "Search help by keyword"),
            ("/mode",               "Show / change runtime permission mode (plan, auto, …) — see /help permissions"),
            ("/model",              "Show active main chat model/backend"),
            ("/model gpt-4o",       "Switch main chat backend to OpenAI gpt-4o"),
            ("/model ollama",       "Switch main chat backend to Ollama default model"),
            ("/model keyword",      "Disable LLM backend and use deterministic keyword/tool routing"),
            ("/style codex",        "Switch to direct research-copilot communication style"),
            ("/verbosity",          "Show / change response depth"),
            ("/steps",              "Show / change execution-step visibility"),
            ("/context",            "Show conversation history + token budget"),
            ("/new  or  /reset",    "Fresh session (clears history)"),
            ("/clear  or  cls",     "Clear terminal screen"),
            ("1 / 2 / 3",          "Ask the numbered follow-up question"),
            ("exit / quit",         "Exit Agent Adda"),
        ],
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# Flat entry list for search
# ─────────────────────────────────────────────────────────────────────────────

def _all_entries() -> list[HelpEntry]:
    entries = []
    for key, sec in SECTIONS.items():
        for cmd, desc in sec["entries"]:
            entries.append(HelpEntry(cmd=cmd, desc=desc, section=key))
    try:
        import nse_agent

        known = {(entry.cmd, entry.desc) for entry in entries}
        for cmd, desc in nse_agent._SLASH_COMMANDS:
            item = (cmd, desc)
            if item not in known:
                entries.append(HelpEntry(cmd=cmd, desc=desc, section="commands"))
    except Exception:
        pass
    try:
        from terminal.helpfile import load_helpfile_catalog

        known = {(entry.cmd, entry.desc) for entry in entries}
        catalog = load_helpfile_catalog()
        for row in catalog.commands:
            item = (row.command, row.description)
            if item not in known:
                entries.append(HelpEntry(cmd=row.command, desc=row.description, section="commands"))
                known.add(item)
        for row in catalog.prompts:
            cmd = row.shortcut
            desc = f"{row.title}: {row.prompt}"
            item = (cmd, desc)
            if item not in known:
                entries.append(HelpEntry(cmd=cmd, desc=desc, section="commands"))
                known.add(item)
    except Exception:
        pass
    return entries


# ─────────────────────────────────────────────────────────────────────────────
# Renderers
# ─────────────────────────────────────────────────────────────────────────────

def _section_key(query: str) -> str | None:
    """Return matching section key for query, or None."""
    q = query.lower().strip().lstrip("/")
    for key, sec in SECTIONS.items():
        if q == key or q in sec.get("aliases", []):
            return key
    return None


def _render_toc(console: Console) -> None:
    """Print the compact table-of-contents overview."""
    table = Table(
        box=box.SIMPLE_HEAD,
        show_header=True,
        header_style="bold cyan",
        padding=(0, 2),
        expand=False,
    )
    table.add_column("Section", style="bold", min_width=18)
    table.add_column("Command", style="dim", min_width=22)
    table.add_column("What it does", min_width=44)

    for key, sec in SECTIONS.items():
        first_cmd, first_desc = "", ""
        for cmd, desc in sec["entries"]:
            if cmd:
                first_cmd, first_desc = cmd, desc
                break
        icon = sec.get("icon", "")
        color = sec.get("color", "white")
        section_label = f"[{color}]{icon} {sec['title']}[/{color}]"
        table.add_row(section_label, first_cmd, first_desc)

    panel_text = (
        "[bold cyan]Agent Adda Help[/bold cyan]\n\n"
        "[dim]Usage:[/dim]  "
        "[green]/help <section>[/green]  to expand a section   "
        "[yellow]/help <keyword>[/yellow]  to search\n\n"
        "[dim]Examples:[/dim]  "
        "[green]/help charts[/green]   "
        "[green]/help fno[/green]   "
        "[green]/help refresh[/green]   "
        "[yellow]/help rsi[/yellow]   "
        "[yellow]/help macd[/yellow]   "
        "[yellow]/help straddle[/yellow]\n"
    )
    console.print()
    console.print(Panel(panel_text, border_style="cyan", padding=(0, 2)))
    console.print(table)
    console.print()


def _render_section(console: Console, key: str) -> None:
    """Print full detail for one section."""
    sec = SECTIONS[key]
    color = sec.get("color", "white")
    icon  = sec.get("icon", "")
    title = f"{icon}  {sec['title']}"

    table = Table(
        box=box.SIMPLE,
        show_header=False,
        padding=(0, 2),
        expand=False,
    )
    table.add_column("Command", style=f"bold {color}", min_width=40)
    table.add_column("Description", style="white", min_width=50)

    for cmd, desc in sec["entries"]:
        if not cmd:
            table.add_row(f"[dim]{desc}[/dim]", "")
        else:
            table.add_row(cmd, desc)

    console.print()
    console.print(Panel(table, title=f"[bold {color}]{title}[/bold {color}]",
                        border_style=color, padding=(0, 1)))
    console.print(
        f"  [dim]Type [bold]/help[/bold] for the full table of contents, "
        f"or [bold]/help <keyword>[/bold] to search.[/dim]\n"
    )


def _render_search(console: Console, query: str) -> None:
    """Search all entries for keyword, print matches."""
    q = query.lower()
    hits: list[tuple[HelpEntry, int]] = []

    for entry in _all_entries():
        score = 0
        cmd_l  = entry.cmd.lower()
        desc_l = entry.desc.lower()
        sec_l  = entry.section.lower()
        aliases = " ".join(SECTIONS.get(entry.section, {}).get("aliases", []))

        if q in cmd_l:
            score += 3
        if q in desc_l:
            score += 2
        if q in sec_l or q in aliases:
            score += 1
        if score:
            hits.append((entry, score))

    hits.sort(key=lambda x: -x[1])

    console.print()
    if not hits:
        console.print(f"  [yellow]No commands found matching '[bold]{query}[/bold]'.[/yellow]")
        console.print("  [dim]Try: /help   or   /help <section name>[/dim]\n")
        return

    table = Table(
        box=box.SIMPLE_HEAD,
        show_header=True,
        header_style="bold cyan",
        padding=(0, 2),
    )
    table.add_column("Command", style="bold green", min_width=40)
    table.add_column("Section", style="dim", min_width=18)
    table.add_column("Description", min_width=44)

    seen: set[str] = set()
    for entry, _ in hits:
        if not entry.cmd or entry.cmd in seen:
            continue
        seen.add(entry.cmd)
        sec_title = SECTIONS.get(entry.section, {}).get("title", entry.section.title())
        # Highlight the matched part in description
        desc = entry.desc
        idx = desc.lower().find(q)
        if idx >= 0:
            desc = desc[:idx] + f"[bold yellow]{desc[idx:idx+len(q)]}[/bold yellow]" + desc[idx+len(q):]
        table.add_row(entry.cmd, sec_title, desc)

    console.print(Panel(
        table,
        title=f"[bold cyan]Search: '{query}'[/bold cyan]  [dim]({len(seen)} matches)[/dim]",
        border_style="cyan",
        padding=(0, 1),
    ))
    console.print(
        f"  [dim]Showing commands matching '[bold]{query}[/bold]'. "
        f"Type [bold]/help <section>[/bold] for full details.[/dim]\n"
    )


def _render_helpfile_section(console: Console, section_name: str) -> bool:
    try:
        from terminal.helpfile import load_helpfile_catalog
    except Exception:
        return False
    catalog = load_helpfile_catalog()
    text = catalog.section_text(section_name)
    if not text:
        return False
    console.print()
    console.print(Panel(
        text,
        title=f"[bold cyan]{section_name.title()}[/bold cyan]",
        border_style="cyan",
        padding=(0, 1),
    ))
    console.print(f"  [dim]Full helpfile: [bold]{catalog.path}[/bold][/dim]\n")
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────

def print_help(console: Console, args: str = "") -> None:
    """
    Main help dispatcher.
      args=""          → TOC
      args="charts"    → section detail
      args="rsi"       → search
    """
    query = args.strip().lower().lstrip("/")

    if not query:
        _render_toc(console)
        return

    helpfile_section = _HELPFILE_SECTION_ALIASES.get(query)
    if helpfile_section and _render_helpfile_section(console, helpfile_section):
        return

    key = _section_key(query)
    if key:
        _render_section(console, key)
    else:
        # Try search — fall back to a polite "not found"
        _render_search(console, query)
