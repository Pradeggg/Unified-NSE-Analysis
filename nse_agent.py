#!/usr/bin/env python3
"""
nse_agent.py — Agent Adda  ·  NSE Market Research Chat

Architecture
────────────
• prompt_toolkit  — input bar with history, arrow-key editing, persistent bottom toolbar
• Rich            — Markdown rendering of full agent responses (no truncation)
• Colorama        — banner, prompt colouring, section separators
• Normal terminal scroll — messages print above the prompt; no fixed-height panel clipping

Usage
─────
  python nse_agent.py                   # interactive chat
  python nse_agent.py -q "RELIANCE"     # single query, print and exit
  python nse_agent.py --trace           # show tool-call trace

Mode commands (in chat):
  /live  or /l   → force Live / Intraday mode  (always calls NSE live API)
  /eod   or /h   → force EOD  / Historical mode (CSV + DB snapshot)
  /auto  or /a   → auto-detect from query keywords  (default)
  /clear         → clear screen
  /help  or ?    → show this help
  1 / 2 / 3      → pick a suggested follow-up question
  exit / quit    → exit
"""

from __future__ import annotations

import argparse
import html
import itertools
import os
import re
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import colorama
from colorama import Fore, Style

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text
from rich import box

from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.formatted_text import ANSI
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.styles import Style as PTStyle

colorama.init(autoreset=True)

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass

# ── Rich console — force_terminal so ANSI codes always work ──────────────────
console = Console(highlight=False, force_terminal=True)

# ── Global chat state ─────────────────────────────────────────────────────────
_mode             = "auto"   # "auto" | "intraday" | "historical"
_followups: list[str] = []   # current follow-up suggestions (up to 3)

# ── Background monitor (lazy import to avoid startup cost) ────────────────────
from terminal.monitor import get_monitor, STRATEGIES as MONITOR_STRATEGIES


# ─────────────────────────────────────────────────────────────────────────────
# Prompt Library  — curated, ready-to-run research prompts
# ─────────────────────────────────────────────────────────────────────────────

PROMPT_LIBRARY = [
    # ── 1. Market Overview ────────────────────────────────────────────────────
    {
        "cat": "📊 Market Overview",
        "key": "market",
        "color": "cyan",
        "prompts": [
            ("Market Pulse",         "Give me a full live market overview — NIFTY 50, BANK, IT, MID, SMALL indices with breadth, FII/DII flow, and stage distribution."),
            ("Breadth Snapshot",     "Show current market breadth: advance/decline ratio, RS distribution by percentile, stage 1-4 stock counts, and what it signals."),
            ("FII vs DII Flow",      "Compare today's FII and DII activity in crores. Who is buying, who is selling, and what does the institutional flow tell us?"),
            ("Top Movers Today",     "Top 5 gainers and top 5 losers in NIFTY 50 today with % change, volume context, and possible reasons."),
            ("Most Active Stocks",   "Which stocks have the highest trading volume and value today? Show most active by value from NIFTY 500."),
            ("52-Week Extremes",     "List stocks nearest to their 52-week high in NIFTY 500 — these are the strongest trending names right now."),
        ],
    },
    # ── 2. Intraday Trading ───────────────────────────────────────────────────
    {
        "cat": "⚡ Intraday Trading",
        "key": "intraday",
        "color": "red",
        "prompts": [
            ("Bank Nifty Scan",      "Scan NIFTY BANK for intraday research setups using all strategies on 15m charts. Show technical target zones, invalidation levels, and risk context."),
            ("Nifty 50 Scan",        "Scan NIFTY 50 for the best intraday setups right now — momentum, breakouts, and mean-reversion on 15m candles."),
            ("Nifty IT Scan",        "Scan NIFTY IT index for intraday signals. Focus on MACD and EMA crossovers."),
            ("RELIANCE Intraday",    "Intraday research setup for RELIANCE on 15m — setup label, technical target zones, invalidation level, pivot levels, and key indicators."),
            ("VCP Pattern Hunt",     "Scan NIFTY 500 for VCP (Volatility Contraction Pattern) stocks ready for intraday breakout on 15m."),
            ("Volume Spike Alert",   "Which NIFTY 50 or BANK NIFTY stocks are showing 2x+ volume spikes with price confirmation right now?"),
            ("Supertrend Setups",    "Scan NIFTY MIDCAP 100 for stocks with active Supertrend research setups on 15m with clear invalidation levels."),
        ],
    },
    # ── 3. Technical Analysis ─────────────────────────────────────────────────
    {
        "cat": "📈 Technical Analysis",
        "key": "technical",
        "color": "green",
        "prompts": [
            ("Stage 2 Breakouts",    "Show me stocks currently in Weinstein Stage 2 with recent breakouts — RS rank high, volume expanding."),
            ("Supertrend BUY Sweep", "Run the supertrend_buy screener and show the top 10 names with stage, RSI, RS%, and 1-month returns."),
            ("Strong Buy Signals",   "Which stocks have strong_buy signals right now? Show technicals: stage, RSI, ADX, MACD, RS rank."),
            ("ADX Trend Leaders",    "Find stocks with ADX > 30 (strong trend) and positive DI+ vs DI−. These are the trending names to watch."),
            ("NIFTY 50 Technicals",  "Full technical setup for NIFTY 50 index — RSI, MACD, Supertrend, key support/resistance, 50/200 MA position."),
            ("BANK NIFTY Setup",     "Technical setup for BANK NIFTY — current trend, key levels, indicators, and what to expect next."),
            ("52W High Breakouts",   "List stocks that are within 5% of their 52-week high from NIFTY 500 — potential breakout candidates."),
        ],
    },
    # ── 4. Sector Analysis ────────────────────────────────────────────────────
    {
        "cat": "🏭 Sector Analysis",
        "key": "sector",
        "color": "magenta",
        "prompts": [
            ("IT Sector Health",     "Analyse the IT sector — breadth, stage distribution, RS vs Nifty, leaders and laggards, and key themes."),
            ("Banking Sector",       "Banking sector deep dive — BANK NIFTY trend, top PSU vs private banks, NPA concerns vs growth stocks."),
            ("Pharma Sector",        "Pharma sector analysis — sector trend, stage distribution, top performers, USFDA/regulatory watch."),
            ("Auto Sector",          "Auto sector outlook — EV transition stocks, two-wheelers vs passenger vehicles, volumes data context."),
            ("FMCG vs Consumer",     "Compare FMCG sector vs Consumer Discretionary — which is showing more Stage 2 stocks and better RS?"),
            ("Top Sector Today",     "Which sectors are leading the market today? Show sector-wise performance and breadth right now."),
            ("Sector Rotation",      "Where is smart money rotating? Analyse sector RS trends over last 1 month — which sectors are gaining/losing momentum?"),
        ],
    },
    # ── 5. Screeners & Filters ───────────────────────────────────────────────
    {
        "cat": "🔬 Screeners",
        "key": "screener",
        "color": "yellow",
        "prompts": [
            ("Stage 2 Universe",     "Show all stocks currently in Weinstein Stage 2 (advancing). Filter by RS > 60 and sort by 1-month returns."),
            ("Breakout Candidates",  "Run the breakouts screener — stocks with price near pivot, high RS rank, volume build-up, in Stage 2."),
            ("High RS Stocks",       "List the top 20 stocks by Relative Strength percentage rank vs NIFTY 50. These are the market leaders."),
            ("Investment Grade",     "Which stocks have the highest investment scores combining fundamentals + technicals? Top 15 names."),
            ("Recovery Plays",       "Show stocks transitioning from Stage 1 (basing) to Stage 2 (advancing) — early movers with rising RS."),
            ("Momentum Movers",      "Top 10 stocks with the best 1-week and 1-month returns with RSI still below 75 — not yet overbought."),
        ],
    },
    # ── 6. Fundamentals & Valuation ──────────────────────────────────────────
    {
        "cat": "🏦 Fundamentals",
        "key": "fundamentals",
        "color": "blue",
        "prompts": [
            ("TCS Full Analysis",    "Full fundamental analysis of TCS — P/E, P/B, ROE, ROCE, revenue growth, debt, pros/cons from screener.in."),
            ("HDFC Bank Valuation",  "HDFC Bank valuation deep dive — P/B vs peers, NIM trend, ROE, capital adequacy, screener.in fundamentals."),
            ("IT Sector P/E Compare","Compare P/E, ROE, ROCE, and revenue growth of TCS vs INFY vs WIPRO vs HCL TECH vs LTIM."),
            ("High ROE Low PE",      "Find NSE stocks with ROE > 20% and P/E < 25 — quality at reasonable price (GARP) screen."),
            ("Debt-Free Companies",  "Show debt-free or near-zero debt companies in NIFTY 500 with ROE > 15% and earnings growth."),
            ("Concall Summary",      "Get the latest concall transcript and key management commentary for RELIANCE from screener.in."),
            ("Peer Comparison",      "Compare RELIANCE vs ONGC vs BPCL — P/E, EV/EBITDA, ROE, dividend yield, and technical stage."),
        ],
    },
    # ── 7. Stock Deep Dive ────────────────────────────────────────────────────
    {
        "cat": "🔍 Stock Deep Dive",
        "key": "stock",
        "color": "green",
        "prompts": [
            ("RELIANCE Full View",   "Everything on RELIANCE — live price, technical setup, fundamentals from screener.in, recent news, sector context, and intraday levels."),
            ("INFOSYS Analysis",     "Full analysis of INFOSYS — stage, technicals, P/E vs peers, recent quarterly results, and trading setup."),
            ("ADANI ENTERPRISES",    "Research ADANI ENTERPRISES — technical stage, RS rank, fundamentals, FII/DII holding changes, latest news."),
            ("ZOMATO Setup",         "ZOMATO current setup — Stage analysis, RSI, MACD, support/resistance, fundamental burn rate and path to profitability."),
            ("TATA MOTORS View",     "TATA MOTORS — JLR performance, EV segment, technical setup, sector context, valuation vs global peers."),
            ("SBI Deep Dive",        "SBI complete analysis — NPA trend, ROE, P/B vs HDFC, technical stage, FII holding, and key catalysts."),
        ],
    },
    # ── 8. News & Catalysts ───────────────────────────────────────────────────
    {
        "cat": "📰 News & Catalysts",
        "key": "news",
        "color": "cyan",
        "prompts": [
            ("Today's Top News",     "What are the top market-moving news stories today? Search moneycontrol, ET, NSE announcements."),
            ("Results Calendar",     "Which companies are announcing quarterly results this week? What are the expected earnings and market reaction?"),
            ("FII Bulk Deals Today", "Show today's bulk deals and block deals — who is buying, who is selling, and what sizes?"),
            ("Macro Events Week",    "What are the key macro events this week — RBI, Fed, CPI data, F&O expiry — and how should traders position?"),
            ("Nifty News Flow",      "Latest news and catalysts affecting NIFTY 50 — policy updates, global cues, sector rotation triggers."),
        ],
    },
    # ── 9. Portfolio ──────────────────────────────────────────────────────────
    {
        "cat": "📋 Portfolio",
        "key": "portfolio",
        "color": "magenta",
        "prompts": [
            ("Portfolio Exposure",   "Show my portfolio sector distribution and concentration. Which sectors am I overweight or underweight?"),
            ("Portfolio vs Stage2",  "Which of my portfolio holdings are in Weinstein Stage 2? Which are in Stage 3 or 4 and need review?"),
            ("Portfolio vs Screen",  "Which of my holdings match the current strong_buy screener? Are my best performers the ones with best signals?"),
            ("Holdings Health",      "Evaluate my portfolio holdings — stage, RSI, RS rank, and 1-month returns for each position."),
        ],
    },
    # ── 10. Global & Macro ────────────────────────────────────────────────────
    {
        "cat": "🌍 Global & Macro",
        "key": "global",
        "color": "yellow",
        "prompts": [
            ("Global Market Check",  "What happened in US, Asian, and European markets overnight? SGX Nifty cues for India's open."),
            ("USD/INR Impact",       "How is USD/INR moving today and what is the impact on IT exporters, importers, and metal stocks?"),
            ("Crude Oil Effect",     "Current crude oil price and its impact on OMCs, aviation stocks, paint sector, and tyre companies."),
            ("FII Net Position",     "FII net activity this month — cumulative buying/selling, which sectors saw inflows, and what it implies for Nifty."),
            ("India vs Emerging",    "How is India performing vs other emerging markets (China, Brazil, Korea) this month? Relative outperformance?"),
        ],
    },
]

# flat list for O(1) lookup: prompt_number → (category, title, query)
_PROMPT_INDEX: dict[int, tuple[str, str, str]] = {}
_n = 1
for _cat in PROMPT_LIBRARY:
    for _title, _query in _cat["prompts"]:
        _PROMPT_INDEX[_n] = (_cat["cat"], _title, _query)
        _n += 1


def _print_prompts_library(filter_key: str = "") -> None:
    """Render the prompt library as a rich table. filter_key narrows to one category."""
    fk = filter_key.lower().strip()
    total = 0
    n = 1

    for cat_data in PROMPT_LIBRARY:
        if fk and fk not in cat_data["key"] and fk not in cat_data["cat"].lower():
            n += len(cat_data["prompts"])
            continue

        color  = cat_data["color"]
        table  = Table(
            show_header=True,
            header_style=f"bold {color}",
            box=box.SIMPLE_HEAD,
            padding=(0, 1),
            expand=True,
        )
        table.add_column("#",     style="bold white", width=4, no_wrap=True)
        table.add_column("Prompt", style=f"bold {color}", min_width=22, no_wrap=True)
        table.add_column("What it does", style="dim white")

        for title, query in cat_data["prompts"]:
            table.add_row(f"p{n}", title, query[:90] + ("…" if len(query) > 90 else ""))
            n += 1
            total += 1

        console.print()
        console.print(Panel(
            table,
            title=f"[bold {color}]{cat_data['cat']}[/bold {color}]",
            border_style=color,
            padding=(0, 1),
        ))

    console.print()
    console.print(
        f"[dim]  {total} prompts shown  ·  Type [bold white]p<number>[/bold white] to run  ·  "
        f"/prompts [bold]market|intraday|technical|sector|screener|fundamentals|"
        f"stock|news|portfolio|global[/bold] to filter[/dim]"
    )
    console.print()



_BANNER = [
    (Fore.CYAN  + Style.BRIGHT, r"   _   ___ ___ _  _ _____      _   ___  ___   _   "),
    (Fore.CYAN  + Style.BRIGHT, r"  /_\ / __| __| \| |_   _|    /_\ |   \|   \ /_\  "),
    (Fore.GREEN + Style.BRIGHT, r" / _ \ (_ | _|| .` | | |     / _ \| |) | |) / _ \ "),
    (Fore.YELLOW+ Style.BRIGHT, r"/_/ \_\___|___|_|\_| |_|    /_/ \_\___/|___/_/ \_|"),
]


def _separator(title: str = "") -> None:
    """Thin horizontal rule, optional centred title."""
    console.rule(title, style="dim")


# ─────────────────────────────────────────────────────────────────────────────
# Input autocomplete
# ─────────────────────────────────────────────────────────────────────────────

# All slash commands with a brief hint shown in the completion menu
_SLASH_COMMANDS: list[tuple[str, str]] = [
    ("/prompts",          "Browse 60 curated research prompts"),
    ("/prompts market",   "Market overview prompts"),
    ("/prompts intraday", "Intraday trading prompts"),
    ("/prompts technical","Technical analysis prompts"),
    ("/prompts sector",   "Sector analysis prompts"),
    ("/prompts screener", "Screener prompts"),
    ("/prompts fundamentals", "Fundamentals & valuation prompts"),
    ("/prompts stock",    "Stock deep-dive prompts"),
    ("/prompts news",     "News & catalysts prompts"),
    ("/prompts portfolio","Portfolio prompts"),
    ("/prompts global",   "Global & macro prompts"),
    ("/ric",              "Show RIC library (8 investigative recipes)"),
    ("/ric sherlock",           "5-step: quote→technicals→fundamentals→news→trade  [SYMBOL]"),
    ("/ric sector-xray",        "4-step: sector breadth→leaders→laggards→entries  [SECTOR]"),
    ("/ric breakout-hunter",    "5-step: breadth→stage2→RS→VCP→final picks"),
    ("/ric earnings-playbook",  "5-step: results→ratios→peers→concall→setup  [SYMBOL]"),
    ("/ric index-pulse",        "4-step: technicals→breadth→top stocks→intraday  [INDEX]"),
    ("/ric peer-battle",        "4-step: fundamentals→technicals→news→verdict  [SYM,SYM,…]"),
    ("/ric risk-radar",         "4-step: macro→FII→breadth extremes→vulnerable stocks"),
    ("/ric morning-intel",      "5-step: global→yesterday→breadth→FII→watchlist"),
    ("/scan",             "Scan NIFTY 50 for intraday signals"),
    ("/scan NIFTY BANK",  "Scan Bank Nifty for intraday signals"),
    ("/scan NIFTY IT",    "Scan Nifty IT for intraday signals"),
    ("/scan NIFTY MIDCAP 100", "Scan Nifty Midcap 100"),
    ("/scan NIFTY PHARMA","Scan Nifty Pharma"),
    # Intraday screener types
    ("/scan orb",         "Opening Range Breakout — first 15-30m range break + volume"),
    ("/scan gap",         "Gap & Go — gapping stocks with volume + MACD continuation"),
    ("/scan macd",        "MACD Crossover — fresh MACD signal line cross"),
    ("/scan rsi",         "RSI Divergence — RSI extreme + Bollinger mean-reversion"),
    ("/scan bb",          "Bollinger Squeeze — low-volatility squeeze breakout"),
    ("/scan vwap",        "VWAP Reclaim — price reclaiming/losing VWAP proxy"),
    ("/scan vcp",         "VCP — Volatility Contraction Pattern intraday"),
    ("/scan momentum",    "Momentum — MACD + RSI + Supertrend aligned"),
    # EOD screener shortcuts
    ("/screen stage2",    "Stage 2 uptrend stocks (Weinstein)"),
    ("/screen momentum",  "Near-52W-high momentum leaders (RS ≥ 1.0)"),
    ("/screen highrs",    "Top RS ≥ 1.15 market leaders"),
    ("/screen turnaround","Turnaround recovery setups"),
    ("/screen base",      "Stage 1 basing/coiling stocks"),
    ("/screen tight",     "Tight weekly range VCP-like consolidations"),
    ("/screen dip",       "Oversold bounce — RSI < 40 dip in Stage 2"),
    ("/monitor",          "Show active background alert monitors"),
    ("/monitor list",     "List all available monitor strategies"),
    ("/monitor status",   "Show status of all running monitors"),
    ("/monitor start",    "Start a background monitor (e.g. /monitor start breakout NIFTY 500 15 buy)"),
    ("/monitor start breakout",   "Start breakout alert monitor (EMA+volume) — default 15m, NIFTY 500"),
    ("/monitor start volume_surge","Start volume surge alert monitor"),
    ("/monitor start reversal",   "Start RSI/Bollinger reversal alert monitor"),
    ("/monitor start momentum",   "Start MACD+RSI momentum alert monitor"),
    ("/monitor start supertrend", "Start Supertrend flip alert monitor"),
    ("/monitor start vcp",        "Start VCP contraction pattern alert monitor"),
    ("/monitor start all",        "Start ALL strategy alerts combined"),
    ("/monitor stop",    "Stop a monitor (e.g. /monitor stop breakout)"),
    ("/monitor stop all","Stop ALL active monitors"),
    ("/live",             "Switch to LIVE mode (real-time NSE API)"),
    ("/eod",              "Switch to EOD mode (historical CSV/DB)"),
    ("/auto",             "Switch to AUTO mode (keyword detect)"),
    ("/global",           "Global market assessment + India read-through"),
    ("/context",          "Show conversation history & context budget"),
    ("/new",              "Start a fresh session (clear history)"),
    ("/reset",            "Start a fresh session (clear history)"),
    ("/clear",            "Clear the screen"),
    ("/help",             "Show all commands"),
]

# Well-known NSE symbols & index names for stock query completion
_KNOWN_SYMBOLS: list[str] = [
    "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "SBIN", "AXISBANK",
    "KOTAKBANK", "INDUSINDBK", "BAJFINANCE", "BAJAJFINSV", "HINDUNILVR",
    "NESTLEIND", "ITC", "TITAN", "ASIANPAINT", "MARUTI", "TATAMOTORS",
    "TATASTEEL", "ONGC", "NTPC", "POWERGRID", "COALINDIA", "ADANIENT",
    "ADANIPORTS", "ADANIGREEN", "WIPRO", "HCLTECH", "TECHM", "LTIM",
    "SUNPHARMA", "DRREDDY", "CIPLA", "DIVISLAB", "APOLLOHOSP",
    "TRENT", "ZOMATO", "NYKAA", "PAYTM", "DMART",  "COFORGE",
    "PERSISTENT", "MPHASIS", "LTTS", "KPIT",
    "NIFTY 50", "NIFTY BANK", "NIFTY IT", "NIFTY PHARMA",
    "NIFTY MIDCAP 100", "NIFTY SMALLCAP 100", "NIFTY AUTO",
    "NIFTY FMCG", "NIFTY METAL", "NIFTY REALTY", "NIFTY INFRA",
]

# Prompt-starter phrases (for when the user types a word, not a /)
_STARTER_PHRASES: list[tuple[str, str]] = [
    ("market overview",    "Live indices, breadth, FII/DII"),
    ("intraday setup for", "Research setup, target zones, invalidation"),
    ("scan",               "Intraday screener (then add index name)"),
    ("top gainers",        "Live top gainers in NIFTY 50"),
    ("top losers",         "Live top losers in NIFTY 50"),
    ("technical setup for","Full technicals for a stock"),
    ("compare",            "Side-by-side stock comparison"),
    ("sector analysis",    "Sector breadth and leaders"),
    ("morning briefing",   "Full morning market briefing"),
    ("stage 2 breakouts",  "Weinstein Stage 2 screener"),
    ("momentum leaders",   "Near-52W-high stocks with RS ≥ 1.0"),
    ("high RS stocks",     "Top relative strength market leaders"),
    ("turnaround stocks",  "Recovery dip setups"),
    ("basing stocks",      "Stage 1 coiling stocks pre-breakout"),
    ("opening range breakout","ORB — first 15-30min range + volume"),
    ("gap and go",         "Gapping stocks with MACD continuation"),
    ("VWAP reclaim",       "Stocks reclaiming VWAP proxy"),
    ("Bollinger squeeze",  "BB squeeze before volatility expansion"),
    ("FII DII activity",   "Today's FII vs DII flow"),
    ("52 week high",       "Stocks near 52-week highs"),
    ("concall transcript", "Management commentary from screener.in"),
    ("global markets",     "Overnight US/Asian/SGX context"),
]


class _AgentCompleter(Completer):
    """Three-tier completion:
      /…       → slash commands
      p<digit> → prompt library entries
      word     → starter phrases + known stock symbols
    """

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor

        # ── Tier 1: slash commands ──────────────────────────────────────
        if text.startswith("/"):
            for cmd, hint in _SLASH_COMMANDS:
                if cmd.lower().startswith(text.lower()):
                    yield Completion(
                        cmd[len(text):],
                        start_position=0,
                        display=cmd,
                        display_meta=hint,
                    )
            return

        # ── Tier 2: p<n> prompt library shortcuts ───────────────────────
        if re.match(r"^p\d{0,3}$", text.lower()):
            prefix_n = text[1:] if len(text) > 1 else ""
            for n, (cat, title, _query) in _PROMPT_INDEX.items():
                if str(n).startswith(prefix_n):
                    yield Completion(
                        f"p{n}"[len(text):],
                        start_position=0,
                        display=f"p{n}  {title}",
                        display_meta=cat,
                    )
            return

        # ── Tier 3: starter phrases + known symbols ──────────────────────
        word = text.lower().strip()
        if len(word) >= 2:
            for phrase, hint in _STARTER_PHRASES:
                if phrase.lower().startswith(word):
                    yield Completion(
                        phrase[len(text.strip()):],
                        start_position=0,
                        display=phrase,
                        display_meta=hint,
                    )
            for sym in _KNOWN_SYMBOLS:
                if sym.lower().startswith(word):
                    yield Completion(
                        sym[len(text.strip()):],
                        start_position=0,
                        display=sym,
                        display_meta="NSE symbol / index",
                    )


# prompt_toolkit style for the completion menu
_COMPLETER_STYLE = PTStyle.from_dict({
    "completion-menu.completion":         "bg:#1a1a2e fg:#c0c0e0",
    "completion-menu.completion.current": "bg:#16213e fg:#00d4ff bold",
    "completion-menu.meta.completion":    "bg:#0f0f1a fg:#607080",
    "completion-menu.meta.completion.current": "bg:#16213e fg:#80c0ff",
    "scrollbar.background":               "bg:#1a1a2e",
    "scrollbar.button":                   "bg:#00d4ff",
})


# ─────────────────────────────────────────────────────────────────────────────
# RIC — Recursive Investigative Conversations
# Pre-built multi-step analysis recipes that chain queries automatically
# ─────────────────────────────────────────────────────────────────────────────

# Each RIC is a list of step dicts:
#   label    : short display name shown before the step runs
#   prompt   : the query sent to the agent ({symbol}, {sector}, {index} are substituted)
#   required : whether a symbol/sector/index arg is needed

RIC_LIBRARY: dict[str, dict] = {
    "sherlock": {
        "name":    "🔍 Stock Sherlock",
        "desc":    "Complete 5-step stock investigation: live quote → technicals → fundamentals → news → intraday trade setup",
        "arg":     "symbol",
        "example": "/ric sherlock RELIANCE",
        "steps": [
            {"label": "Live Quote",      "prompt": "Live price and quote for {symbol} — current price, % change, volume, day high/low vs 52-week range."},
            {"label": "Technical Setup", "prompt": "Full technical setup for {symbol} — Weinstein stage, RSI, ADX, MACD, supertrend direction, position vs 20/50/200 MA, RS rank vs Nifty 50."},
            {"label": "Fundamentals",    "prompt": "Fundamental analysis of {symbol} from screener.in — P/E, P/B, ROE, ROCE, debt/equity, revenue growth, pros and cons."},
            {"label": "News & Catalysts","prompt": "Latest news and catalysts for {symbol} — recent announcements, results, management commentary, analyst views."},
            {"label": "Trade Setup",     "prompt": "Intraday trading setup for {symbol} on 15m — entry price, target, stoploss, R:R ratio, key support/resistance levels, recommended strategy."},
        ],
    },
    "sector-xray": {
        "name":    "🏭 Sector X-Ray",
        "desc":    "4-step sector deep dive: breadth → leaders → laggards → entry opportunities",
        "arg":     "sector",
        "example": "/ric sector-xray IT",
        "steps": [
            {"label": "Sector Overview",  "prompt": "Sector overview for {sector} — breadth, stage distribution, RS vs Nifty 50, overall trend and health."},
            {"label": "Leaders",          "prompt": "Top 5 performing stocks in {sector} right now — stage, RSI, RS rank, 1-month returns and what's driving them."},
            {"label": "Laggards & Risks", "prompt": "Weakest stocks in {sector} sector — Stage 3/4 names, high RSI divergences, names to avoid or watch for reversal."},
            {"label": "Entry Opportunities", "prompt": "Best entry opportunities in {sector} sector right now — stocks with Supertrend BUY, high RS, Stage 2, near support. Give specific setups."},
        ],
    },
    "breakout-hunter": {
        "name":    "🎯 Breakout Hunter",
        "desc":    "5-step hunt for imminent breakouts: breadth → stage2 screener → high RS → VCP scan → final picks",
        "arg":     None,
        "example": "/ric breakout-hunter",
        "steps": [
            {"label": "Market Conditions", "prompt": "Current market breadth and conditions — is this a good environment for breakout trades? Advance/decline, stage distribution, FII flow."},
            {"label": "Stage 2 Universe",  "prompt": "Run the Stage 2 screener — show top 15 stocks in advancing stage with strongest RS rank and technical scores."},
            {"label": "High RS Leaders",   "prompt": "Top 10 stocks by Relative Strength percentage vs Nifty 50. These are the market leaders — show their current technical stage."},
            {"label": "VCP Scan",          "prompt": "Scan NIFTY 500 for VCP (Volatility Contraction Pattern) on 15m — stocks showing tight range contraction near pivot with volume drying up."},
            {"label": "Final Picks",       "prompt": "Based on the breakout analysis above, give your top 3 breakout candidates with specific entry triggers, targets, and stoploss levels."},
        ],
    },
    "earnings-playbook": {
        "name":    "📋 Earnings Playbook",
        "desc":    "5-step earnings analysis: results → ratios → peers → management commentary → trade setup",
        "arg":     "symbol",
        "example": "/ric earnings-playbook TCS",
        "steps": [
            {"label": "Latest Results",     "prompt": "Latest quarterly results for {symbol} — revenue, PAT, margins, YoY and QoQ growth. Were they above or below estimates?"},
            {"label": "Financial Ratios",   "prompt": "Key financial ratios for {symbol} — P/E, EV/EBITDA, ROE, ROCE, operating margin trend over last 4 quarters."},
            {"label": "Peer Comparison",    "prompt": "Compare {symbol} with its top 3 sector peers on P/E, ROE, ROCE, revenue growth, and margin. Who has the best fundamentals?"},
            {"label": "Management Commentary", "prompt": "Management guidance and commentary for {symbol} — get the concall transcript highlights from screener.in. What did management say about growth outlook?"},
            {"label": "Post-Earnings Setup","prompt": "Post-earnings trade setup for {symbol} — technical reaction to results, current stage, intraday levels for entry/target/SL if trading the move."},
        ],
    },
    "index-pulse": {
        "name":    "📊 Index Pulse",
        "desc":    "4-step index analysis: technicals → breadth → top stocks → intraday levels",
        "arg":     "index",
        "example": "/ric index-pulse NIFTY BANK",
        "steps": [
            {"label": "Index Technicals",  "prompt": "Full technical setup for {index} — RSI, MACD, supertrend, key support/resistance, position vs 20/50/200 MA, ADX trend strength."},
            {"label": "Breadth & Flow",    "prompt": "Market breadth and FII/DII flow for {index} — advance/decline, stage distribution, institutional buying/selling today."},
            {"label": "Top Stocks",        "prompt": "Top 5 performing and bottom 5 performing stocks in {index} today — what's driving the index move?"},
            {"label": "Intraday Levels",   "prompt": "Intraday scan of {index} on 15m — scan for buy/sell signals, pivot levels, key support/resistance, expected range for today."},
        ],
    },
    "peer-battle": {
        "name":    "⚔️  Peer Battle",
        "desc":    "4-step head-to-head comparison: fundamentals → technicals → news → verdict",
        "arg":     "symbols (comma-separated)",
        "example": "/ric peer-battle TCS,INFY,WIPRO",
        "steps": [
            {"label": "Fundamental Battle", "prompt": "Compare {symbol} on fundamentals — P/E, P/B, ROE, ROCE, revenue growth, debt. Show as a table. Who wins on value and quality?"},
            {"label": "Technical Battle",   "prompt": "Compare {symbol} on technicals — Weinstein stage, RSI, RS rank, 1-month/1-week returns, ADX. Show as a table. Who has the best chart?"},
            {"label": "News & Sentiment",   "prompt": "Compare {symbol} — recent news, analyst ratings, management tone. Any recent positive or negative surprises?"},
            {"label": "Verdict",            "prompt": "Final verdict on {symbol} — given all the above, which stock is the best buy right now and why? Give a ranked order with brief rationale for each."},
        ],
    },
    "risk-radar": {
        "name":    "⚠️  Risk Radar",
        "desc":    "4-step risk assessment: macro → institutional flow → breadth extremes → vulnerable stocks",
        "arg":     None,
        "example": "/ric risk-radar",
        "steps": [
            {"label": "Macro Environment",  "prompt": "Current macro risk environment — global cues, RBI stance, FII trend, USD/INR, crude. Is the market in risk-on or risk-off mode?"},
            {"label": "Institutional Flow", "prompt": "FII and DII activity this week — net buying/selling, which sectors saw outflows, bulk/block deals showing exits."},
            {"label": "Breadth Extremes",   "prompt": "Market breadth extremes — stocks near 52-week lows, Stage 4 stock count, RSI < 30 names, advance/decline at extremes? Any divergences?"},
            {"label": "Vulnerable Stocks",  "prompt": "Top 10 most vulnerable stocks right now — Stage 3/4, negative RS, high short interest, approaching 52W lows. Names to avoid or watch for shorts."},
        ],
    },
    "morning-intel": {
        "name":    "☀️  Morning Intel",
        "desc":    "5-step pre-market intelligence: global → previous day → current breadth → FII → watchlist",
        "arg":     None,
        "example": "/ric morning-intel",
        "steps": [
            {"label": "Global Overnight",   "prompt": "Global market context for today — US markets close, Asian markets open, SGX Nifty, key macro news overnight. What's the cue for India?"},
            {"label": "Yesterday Recap",    "prompt": "NSE previous day recap — how did NIFTY 50 and BANK NIFTY close? Top 3 gainers, top 3 losers, sectors that moved."},
            {"label": "Current Breadth",    "prompt": "Current live market breadth — NIFTY 50/BANK/IT/MID/SMALL levels right now, advance/decline ratio, stage distribution update."},
            {"label": "FII/DII Today",      "prompt": "FII and DII activity today so far — buying/selling in crores, net flow, which sectors, and what it signals for market direction."},
            {"label": "Today's Watchlist",  "prompt": "Give me 5 stocks to watch today — based on technical setups, news catalysts, FII flow, and intraday signal quality. For each: why watch it and key levels."},
        ],
    },
}


def _print_ric_library() -> None:
    """Show all available RICs in a formatted panel."""
    table = Table(
        show_header=True, header_style="bold yellow",
        box=box.SIMPLE_HEAD, padding=(0, 1), expand=True,
    )
    table.add_column("Command",  style="bold yellow", no_wrap=True, min_width=28)
    table.add_column("RIC Name", style="bold white",  min_width=22, no_wrap=True)
    table.add_column("Steps", style="dim white", width=6, no_wrap=True)
    table.add_column("What it does", style="dim white")
    for key, ric in RIC_LIBRARY.items():
        table.add_row(
            ric["example"],
            ric["name"],
            str(len(ric["steps"])),
            ric["desc"],
        )
    console.print()
    console.print(Panel(
        table,
        title="[bold yellow] 🔁  RIC Library — Recursive Investigative Conversations [/bold yellow]",
        border_style="yellow",
        padding=(0, 1),
    ))
    console.print(
        "[dim]  Usage: [bold white]/ric <name>[/bold white] or "
        "[bold white]/ric <name> SYMBOL[/bold white]  ·  "
        "Each step runs automatically and builds on the previous[/dim]"
    )
    console.print()


def _run_ric(agent, key: str, arg: str, show_trace: bool) -> None:
    """Execute a named RIC step by step, each result feeding context."""
    ric = RIC_LIBRARY.get(key)
    if not ric:
        console.print(f"[red]  ✗  Unknown RIC '{key}'. Type /ric to see the library.[/red]")
        return

    # Validate arg requirement
    if ric["arg"] and not arg:
        console.print(
            f"[yellow]  ⚠  {ric['name']} needs a {ric['arg'].upper()}.  "
            f"Example: [bold]{ric['example']}[/bold][/yellow]"
        )
        return

    symbol = arg.strip().upper() if arg else ""
    n_steps = len(ric["steps"])

    console.print()
    console.rule(
        f"[bold yellow] 🔁  {ric['name']} [/bold yellow]"
        f"[dim]  {symbol or ''}  ·  {n_steps} steps [/dim]",
        style="yellow",
    )
    console.print(f"[dim]  {ric['desc']}[/dim]")
    console.print()

    for i, step in enumerate(ric["steps"], 1):
        label  = step["label"]
        prompt = step["prompt"].replace("{symbol}", symbol)\
                               .replace("{sector}", symbol)\
                               .replace("{index}",  symbol)

        console.print(
            f"[bold yellow]  Step {i}/{n_steps}[/bold yellow]"
            f"[dim]  {label}[/dim]"
        )
        console.print("[dim cyan]  ⏳  Running…[/dim cyan]")

        try:
            result = agent.query(prompt, show_trace=show_trace)
            _print_response(result)
        except Exception as e:
            console.print(f"[red]  ✗  Step {i} failed: {e}[/red]")
            console.print()

    console.rule(
        f"[bold yellow] ✅  {ric['name']} complete [/bold yellow]"
        f"[dim]  {symbol or ''}  ·  all {n_steps} steps done [/dim]",
        style="yellow",
    )
    console.print()


def print_banner() -> None:
    """Colorama ASCII banner printed to stdout before chat starts."""
    print()
    for colour, line in _BANNER:
        print(colour + line)
    print()
    box_w = 58
    print(Fore.WHITE + Style.BRIGHT + "  ╔" + "═" * box_w + "╗")
    print(Fore.WHITE + Style.BRIGHT + "  ║" +
          Fore.YELLOW + Style.BRIGHT + "  🏛  NSE Market Research  " +
          Fore.WHITE + "│  " + Fore.GREEN + "AI-powered analysis" +
          " " * 3 + Fore.WHITE + Style.BRIGHT + "  ║")
    print(Fore.WHITE + Style.BRIGHT + "  ║" +
          Fore.CYAN + "  stocks · sectors · signals · screeners · health" +
          " " * 5 + Fore.WHITE + Style.BRIGHT + "  ║")
    print(Fore.WHITE + Style.BRIGHT + "  ╚" + "═" * box_w + "╝")
    print()
    for icon, colour, text in [
        ("💡", Fore.CYAN,    "How is the market today?"),
        ("💡", Fore.GREEN,   "Show me Stage 2 breakout stocks"),
        ("💡", Fore.YELLOW,  "RELIANCE technical setup"),
        ("💡", Fore.MAGENTA, "Which sectors are leading right now?"),
        ("💡", Fore.BLUE,    "Global market assessment for India"),
    ]:
        print(f"  {icon}  {colour}{Style.BRIGHT}{text}{Style.RESET_ALL}")
    print()
    print(Fore.WHITE + Style.DIM +
          "  /live  /eod  /auto  │  /global  │  /prompts  │  p<n> = run prompt  │  1 2 3 = follow-ups  │  /help  │  exit")
    print()
    _separator()
    print()


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _parse_followups(text: str) -> tuple[str, list[str]]:
    """Strip the '## 💬 …' follow-up block; return (clean_text, [q1, q2, q3])."""
    pattern = re.compile(
        r"##\s*💬[^\n]*\n((?:\d+\..+\n?)+)",
        re.IGNORECASE | re.MULTILINE,
    )
    m = pattern.search(text)
    if not m:
        return text, []
    questions = re.findall(r"\d+\.\s*(.+)", m.group(1))
    clean = text[:m.start()].rstrip()
    return clean, [q.strip() for q in questions[:3]]


def _mode_tag() -> str:
    tags = {
        "auto":       Fore.WHITE  + Style.DIM    + "[AUTO]"  + Style.RESET_ALL,
        "intraday":   Fore.RED    + Style.BRIGHT + "[LIVE🔴]" + Style.RESET_ALL,
        "historical": Fore.BLUE   + Style.BRIGHT + "[EOD📚]"  + Style.RESET_ALL,
    }
    return tags[_mode]


def _build_prompt(agent=None) -> ANSI:
    tag = {
        "auto":       "\x1b[2m[AUTO]\x1b[0m",
        "intraday":   "\x1b[1;31m[LIVE🔴]\x1b[0m",
        "historical": "\x1b[1;34m[EOD📚]\x1b[0m",
    }[_mode]
    fup   = (f"  \x1b[33m(follow-ups: 1·2·3)\x1b[0m" if _followups else "")
    turns = (f"  \x1b[2mt{agent.turn_count}\x1b[0m" if agent and agent.turn_count > 0 else "")
    return ANSI(f"  {tag}{fup}{turns}\x1b[1;36m ❯ \x1b[0m")


# ─────────────────────────────────────────────────────────────────────────────
# Display helpers  (all print to stdout; terminal scrolls naturally)
# ─────────────────────────────────────────────────────────────────────────────

_URL_RE = re.compile(r'(https?://[^\s\)\]>,"\']+)')
_HTML_LINK_RE = re.compile(
    r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)


def _strip_html_tags(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text)


def _html_links_to_visible_urls(text: str) -> str:
    """Convert HTML anchors into visible labels plus raw URLs.

    Raw URLs are intentionally visible because some terminal apps do not support
    OSC-8 hyperlinks but do auto-detect plain https:// text.
    """
    def _replace(match: re.Match) -> str:
        url = html.unescape(match.group(1).strip())
        label = html.unescape(_strip_html_tags(match.group(2))).strip() or url
        return url if label == url else f"{label} ({url})"

    return _HTML_LINK_RE.sub(_replace, text)


def _linkify_markdown(text: str) -> str:
    """Make HTML anchors visible while leaving raw URLs as plain text.

    We intentionally avoid Markdown `[label](url)` conversion here because
    Rich renders that as OSC-8 metadata, which is not clickable in every
    terminal. Plain visible URLs are more widely auto-detected.
    """
    return _html_links_to_visible_urls(text)


def _append_bare_url_links(target: Text, text: str) -> None:
    """Append text while keeping raw URLs visible and contiguous."""
    pos = 0
    for match in _URL_RE.finditer(text):
        if match.start() > pos:
            target.append(text[pos:match.start()])
        raw = match.group(1)
        url = raw.rstrip(".,;)")
        trailing = raw[len(url):]
        target.append(url)
        if trailing:
            target.append(trailing)
        pos = match.end()
    if pos < len(text):
        target.append(text[pos:])


def _text_with_links(text: str) -> Text:
    """Create Rich Text that preserves line breaks and exposes raw URLs."""
    out = Text()
    pos = 0
    for match in _HTML_LINK_RE.finditer(text):
        if match.start() > pos:
            _append_bare_url_links(out, text[pos:match.start()])
        url = html.unescape(match.group(1).strip())
        label = html.unescape(_strip_html_tags(match.group(2))).strip() or url
        out.append(url if label == url else f"{label} ({url})")
        pos = match.end()
    if pos < len(text):
        _append_bare_url_links(out, text[pos:])
    return out


def _render_news_item(r: dict, cap: int = 140) -> None:
    """Render one news/research item with an OSC-8 clickable title + dim snippet."""
    title   = r.get("title") or r.get("name") or ""
    url     = r.get("url")   or r.get("link") or ""
    snippet = r.get("snippet") or r.get("body") or ""
    source  = r.get("source", "")

    # Source badge
    if source:
        console.print(f"  [dim cyan][{source}][/dim cyan]")

    # Title is visible text; URL is printed plainly below for terminal auto-detect.
    if title:
        console.print(f"  [bold]{title}[/bold]")

    # URL as raw visible text. Avoid OSC-8-only links for terminal compatibility.
    if url:
        console.print(f"  {url}")

    # Snippet
    if snippet:
        body = snippet[:cap] + "…" if len(snippet) > cap else snippet
        console.print(f"  [dim]{body}[/dim]")
    console.print()


def _print_user(query: str) -> None:
    console.print()
    console.rule(f"[bold cyan]❯[/bold cyan]  [bold]{query}[/bold]  [dim]{_ts()}[/dim]",
                 style="dim cyan", align="left")


def _print_response(result: dict) -> None:
    global _followups
    answer  = result.get("answer", "(no answer)")
    backend = result.get("backend", "?")

    # Strip follow-ups from answer body
    clean, _followups = _parse_followups(answer)

    # ── Agent header (rule with centred title) ────────────────────────────
    console.print()
    console.rule(
        f"[bold green] 🤖  Agent Adda [/bold green][dim] {_ts()}  ·  {backend} [/dim]",
        style="green dim",
    )
    console.print()

    # ── Comparison table (rendered before narrative for immediate context) ─
    comp = result.get("comparison")
    if comp and comp.get("stock_details"):
        _render_comparison_table(comp)

    # ── Body — Rich Markdown rendered to full terminal width ───────────────
    has_markup = backend != "Keyword (no LLM)" and any(c in clean for c in ["**", "##", "- ", "* ", "```"])
    if has_markup:
        console.print(Markdown(_linkify_markdown(clean)))
    else:
        console.print(_text_with_links(clean), style="white")

    # ── Direct catalysts / news render (bypasses LLM formatting) ─────────
    cats = result.get("catalysts")
    if cats:
        items = cats.get("results") or cats.get("items") or cats.get("news_articles") or []
        # multi_source_web_search returns {"source": [list]} — flatten to list
        if isinstance(items, dict):
            flat = []
            for source, hits in items.items():
                if isinstance(hits, list):
                    for h in hits:
                        if isinstance(h, dict):
                            h = dict(h)
                            h.setdefault("source", source)
                            flat.append(h)
            items = flat
        # filter to only proper dicts with at least a title or url
        items = [r for r in items if isinstance(r, dict) and (r.get("title") or r.get("url"))]
        if items:
            console.print()
            console.rule("[bold cyan] 📰  News & Catalysts [/bold cyan]", style="dim cyan")
            for r in items:
                _render_news_item(r)

    # ── Follow-up suggestions ─────────────────────────────────────────────
    if _followups:
        console.print()
        console.rule("[bold yellow] 💬  What to explore next [/bold yellow]",
                     style="dim yellow")
        for i, q in enumerate(_followups, 1):
            console.print(f"  [bold yellow]{i}[/bold yellow]  {q}")
        console.print("[dim]  Reply 1 · 2 · 3 or ask your own question[/dim]")

    console.print()
    _separator()


def _print_trace(trace: list[dict]) -> None:
    if not trace:
        return
    tbl = Table(box=box.SIMPLE, header_style="bold dim", expand=True)
    tbl.add_column("Tool",   style="cyan",  width=26)
    tbl.add_column("Args",   style="dim",   width=30)
    tbl.add_column("Result", style="white", width=40)
    for t in trace:
        res = t.get("result", {})
        err = res.get("error", "")
        s = f"ERROR: {err[:40]}" if err else f"ok — {', '.join(list(res)[:4])}"
        tbl.add_row(t.get("tool", "—"), str(t.get("args", {}))[:40], s)
    console.print(Panel(tbl, title="[bold dim]Tool Trace[/bold dim]",
                        border_style="dim"))


def _render_comparison_table(comp: dict) -> None:
    """Render a side-by-side comparison table from compare_stocks() result."""
    symbols = comp.get("symbols", [])
    details = {d["symbol"]: d for d in comp.get("stock_details", [])}
    aspects = comp.get("aspects", ["both"])
    fetch_fund = any(a in ("fundamental", "both") for a in aspects)
    fetch_tech = any(a in ("technical", "both") for a in aspects)

    if not symbols:
        return

    def _v(val, suffix="", na="—") -> str:
        if val is None or val == "":
            return na
        return f"{val}{suffix}"

    def _pct(val, na="—") -> str:
        if val is None:
            return na
        try:
            return f"{float(val):.1f}%"
        except (TypeError, ValueError):
            return str(val)

    def _sig_style(sig: str | None) -> str:
        if not sig:
            return "dim"
        s = sig.upper()
        if "STRONG_BUY" in s:
            return "bold green"
        if "BUY" in s:
            return "green"
        if "STRONG_SELL" in s or "SELL" in s:
            return "red"
        if "HOLD" in s:
            return "yellow"
        return "dim"

    def _stage_style(stage: str | None) -> str:
        if not stage:
            return "dim"
        s = stage.upper()
        if "2" in s:
            return "bold green"
        if "1" in s:
            return "cyan"
        if "3" in s:
            return "yellow"
        if "4" in s:
            return "red"
        return "dim"

    tbl = Table(
        box=box.SIMPLE_HEAD,
        header_style="bold cyan",
        show_lines=True,
        expand=True,
    )
    tbl.add_column("Metric", style="bold white", min_width=22, no_wrap=True)
    for sym in symbols:
        name = (details.get(sym) or {}).get("company", sym)
        short = name[:18] + "…" if len(name) > 20 else name
        tbl.add_column(f"{sym}\n[dim]{short}[/dim]", justify="right", min_width=14)

    def _row(label: str, extractor, style_fn=None):
        cells = [label]
        for sym in symbols:
            d = details.get(sym) or {}
            raw = extractor(d)
            txt = raw if isinstance(raw, str) else _v(raw)
            if style_fn:
                st = style_fn(raw)
                cells.append(Text(txt, style=st))
            else:
                cells.append(txt)
        tbl.add_row(*cells)

    # ── Fundamental section ──────────────────────────────────────────────
    if fetch_fund:
        tbl.add_section()
        tbl.add_row("[bold cyan]── Fundamental ──[/bold cyan]", *["" for _ in symbols])
        _row("Market Cap (Cr)",   lambda d: d.get("market_cap_cr"))
        _row("Current Price (₹)", lambda d: d.get("current_price") or d.get("db_price"))
        _row("P/E",               lambda d: d.get("pe"))
        _row("P/B",               lambda d: d.get("pb"))
        _row("Book Value (₹)",    lambda d: d.get("book_value"))
        _row("ROE",               lambda d: _pct(d.get("roe")))
        _row("ROCE",              lambda d: _pct(d.get("roce")))
        _row("Div Yield",         lambda d: _pct(d.get("div_yield")))
        _row("52W High/Low",      lambda d: d.get("high_low_52w") or "—")

    # ── Technical section ────────────────────────────────────────────────
    if fetch_tech:
        tbl.add_section()
        tbl.add_row("[bold cyan]── Technical ──[/bold cyan]", *["" for _ in symbols])
        _row("Stage",            lambda d: d.get("stage") or "—",       _stage_style)
        _row("Trading Signal",   lambda d: d.get("trading_signal") or "—", _sig_style)
        _row("Supertrend",       lambda d: d.get("supertrend") or "—",
             lambda v: "bold green" if v == "BUY" else ("bold red" if v == "SELL" else "dim"))
        _row("RSI",              lambda d: _v(d.get("rsi")))
        _row("RS %tile",         lambda d: _v(d.get("rs_pct"), "%"))
        _row("Tech Score",       lambda d: _v(d.get("technical_score")))
        _row("Invest Score",     lambda d: _v(d.get("investment_score")))
        _row("Chg 1D",           lambda d: _pct(d.get("change_1d_pct")))
        _row("Chg 1W",           lambda d: _pct(d.get("change_1w_pct")))
        _row("Chg 1M",           lambda d: _pct(d.get("change_1m_pct")))

    # ── Screener.in links ────────────────────────────────────────────────
    tbl.add_section()
    tbl.add_row("[bold cyan]── Links ──[/bold cyan]", *["" for _ in symbols])
    links = []
    for sym in symbols:
        d = details.get(sym) or {}
        url = d.get("screener_url") or f"https://www.screener.in/company/{sym}/"
        links.append(url)
    tbl.add_row("Screener.in", *links)

    title_syms = " vs ".join(symbols)
    console.print()
    console.rule(f"[bold cyan] 📊  Comparison: {title_syms} [/bold cyan]", style="cyan dim")
    console.print(tbl)

    # ── Pros / Cons digest ───────────────────────────────────────────────
    for sym in symbols:
        d = details.get(sym) or {}
        pros = d.get("pros", [])
        cons = d.get("cons", [])
        if pros or cons:
            console.print(f"\n  [bold cyan]{sym}[/bold cyan]")
            for p in pros[:3]:
                console.print(f"    [green]✔[/green] {p}")
            for c in cons[:2]:
                console.print(f"    [red]✘[/red] {c}")
    console.print()




def _print_context_summary(agent) -> None:
    """Show current session conversation history summary."""
    history = agent._history
    turns   = agent.turn_count
    chars   = sum(len(m.get("content") or "") for m in history)
    budget  = agent._HISTORY_CHAR_BUDGET

    if turns == 0:
        console.print("[dim]  No conversation history yet in this session.[/dim]")
        console.print()
        return

    tbl = Table(box=box.SIMPLE_HEAD, header_style="bold cyan", expand=True)
    tbl.add_column("Turn", style="bold white", width=5, no_wrap=True)
    tbl.add_column("You asked",     style="cyan",  min_width=30)
    tbl.add_column("Agent replied", style="dim white")

    user_turns = [(m["content"] for m in history if m["role"] == "user")]
    asst_turns = [(m["content"] for m in history if m["role"] == "assistant")]

    user_msgs = [m["content"] for m in history if m["role"] == "user"]
    asst_msgs = [m["content"] for m in history if m["role"] == "assistant"]

    for i, (u, a) in enumerate(zip(user_msgs, asst_msgs), 1):
        u_short = u[:60] + "…" if len(u) > 60 else u
        a_short = a[:70] + "…" if len(a) > 70 else a
        tbl.add_row(str(i), u_short, a_short)

    bar_filled = int(30 * chars / budget)
    bar = "█" * bar_filled + "░" * (30 - bar_filled)
    pct = min(100, int(100 * chars / budget))

    console.print()
    console.print(Panel(
        tbl,
        title=f"[bold cyan] 🧠  Session Context — {turns} turn{'s' if turns != 1 else ''} [/bold cyan]",
        border_style="cyan",
    ))
    console.print(
        f"  [dim]Context budget: [cyan]{bar}[/cyan] {pct}%  "
        f"({chars:,} / {budget:,} chars)  ·  "
        f"[bold]/new[/bold] to clear  ·  max {agent._HISTORY_MAX_TURNS} turns[/dim]"
    )
    console.print()


# ─────────────────────────────────────────────────────────────────────────────
# Background monitor — alert rendering + queue drain
# ─────────────────────────────────────────────────────────────────────────────

_ALERT_DIR_STYLE = {"BUY": "bold green", "SELL": "bold red", "WATCH": "bold yellow"}
_CONF_COLOURS    = {"high": "green", "medium": "yellow", "low": "dim white"}


def _render_alert_batch(event: dict) -> None:
    """Render a batch of alerts from a background monitor worker."""
    from terminal.monitor import Alert
    alerts: list[Alert] = event.get("alerts", [])
    strategy = event["strategy"].upper()
    index    = event["index"]
    as_of    = event["as_of"]
    run_n    = event.get("run_n", "?")

    # Build table
    tbl = Table(
        box=box.SIMPLE_HEAD,
        show_header=True,
        header_style="bold cyan",
        expand=False,
        padding=(0, 1),
    )
    tbl.add_column("",        width=2)
    tbl.add_column("Symbol",  style="bold white", min_width=12)
    tbl.add_column("Signal",  style="cyan",       min_width=20)
    tbl.add_column("Dir",     min_width=5)
    tbl.add_column("Entry",   justify="right",    min_width=8)
    tbl.add_column("Target",  justify="right",    min_width=8)
    tbl.add_column("SL",      justify="right",    min_width=8)
    tbl.add_column("R:R",     justify="right",    min_width=4)
    tbl.add_column("Conf",    min_width=5)

    for a in alerts[:10]:
        dir_style  = _ALERT_DIR_STYLE.get(a.direction, "white")
        conf_style = _CONF_COLOURS.get(a.confidence, "white")
        tbl.add_row(
            a.emoji,
            a.symbol,
            a.signal[:22],
            f"[{dir_style}]{a.direction}[/{dir_style}]",
            f"₹{a.entry:.1f}"   if a.entry    else "—",
            f"₹{a.target:.1f}"  if a.target   else "—",
            f"₹{a.stoploss:.1f}" if a.stoploss else "—",
            f"[{conf_style}]{a.rr:.1f}[/{conf_style}]" if a.rr else "—",
            f"[{conf_style}]{a.confidence_bar}[/{conf_style}]",
        )

    console.print()
    console.print(Rule(
        f"[bold magenta]🔔 MONITOR ALERT  [{strategy}]  {index}  ·  {as_of}  ·  scan #{run_n}[/bold magenta]",
        style="magenta",
    ))
    console.print(tbl)
    console.print("[dim]  ━ Not investment advice. Research only. ━[/dim]")
    console.print()


def _render_monitor_heartbeat(event: dict) -> None:
    """Print a quiet heartbeat line (no signals found this cycle)."""
    strategy = event["strategy"]
    index    = event["index"]
    as_of    = event["as_of"]
    run_n    = event.get("run_n", "?")
    console.print(
        f"[dim]  ⏱  Monitor [{strategy}] — scan #{run_n} complete, no new signals  "
        f"({index} @ {as_of})[/dim]"
    )


def _check_monitor_alerts() -> None:
    """Drain and render any queued monitor alerts. Called in the chat loop."""
    mon = get_monitor()
    if not mon.any_active():
        return
    events = mon.drain_alerts()
    for ev in events:
        if ev.get("type") == "alerts":
            _render_alert_batch(ev)
        elif ev.get("type") == "heartbeat":
            _render_monitor_heartbeat(ev)
        elif ev.get("type") == "error":
            console.print(
                f"[dim red]  ⚠  Monitor [{ev.get('strategy')}] error: {ev.get('message')}[/dim red]"
            )


def _print_monitor_status() -> None:
    """Show status table for all running monitors."""
    mon = get_monitor()
    workers = mon.status()
    if not workers:
        console.print("[dim]  No monitors active. Use /monitor start [strategy] to activate.[/dim]")
        return

    tbl = Table(box=box.SIMPLE_HEAD, header_style="bold cyan", expand=False)
    tbl.add_column("Strategy",  style="bold white")
    tbl.add_column("Index",     style="cyan")
    tbl.add_column("Interval")
    tbl.add_column("Status")
    tbl.add_column("Last Run",  style="dim")
    tbl.add_column("Scans",     justify="right")
    tbl.add_column("Signals",   justify="right")
    tbl.add_column("Errors",    justify="right")

    for w in workers:
        status_str = "[bold green]● LIVE[/bold green]" if w["running"] else "[dim]○ stopped[/dim]"
        tbl.add_row(
            w["strategy"], w["index"], w["interval"],
            status_str, w["last_run"],
            str(w["run_count"]), str(w["last_count"]), str(w["errors"]),
        )

    console.print()
    console.print(Panel(tbl, title="[bold magenta]🔔 Background Monitors[/bold magenta]", expand=False))
    console.print()


def _handle_monitor_command(parts: list[str]) -> None:
    """Handle /monitor [start|stop|status|list] [strategy] [index]."""
    mon = get_monitor()
    sub = parts[1].lower() if len(parts) > 1 else "status"

    if sub == "list":
        tbl = Table(box=box.SIMPLE_HEAD, header_style="bold cyan", expand=False)
        tbl.add_column("Strategy", style="bold white", min_width=12)
        tbl.add_column("Description", style="dim")
        for k, v in MONITOR_STRATEGIES.items():
            tbl.add_row(k, v["description"])
        console.print()
        console.print(Panel(tbl, title="[bold cyan]Available Monitor Strategies[/bold cyan]", expand=False))
        console.print("[dim]  Usage: /monitor start breakout [NIFTY 500] [15] [buy|sell|all][/dim]")
        console.print()
        return

    if sub == "status":
        _print_monitor_status()
        return

    if sub == "stop":
        strategy = parts[2].lower() if len(parts) > 2 else "all"
        index    = " ".join(parts[3:]).upper() if len(parts) > 3 else None
        msg      = mon.stop(strategy, index)
        console.print(f"  {msg}")
        return

    if sub == "start":
        strategy     = parts[2].lower()  if len(parts) > 2 else "all"
        # Parse: /monitor start [strategy] [index] [interval_min] [direction]
        # Example: /monitor start breakout NIFTY 500 15 buy
        idx_parts = []
        interval  = 15
        direction = "all"

        # Consume remaining args: digits → interval, buy/sell/all → direction, rest → index
        remaining = parts[3:] if len(parts) > 3 else []
        for tok in remaining:
            if tok.isdigit():
                interval = int(tok)
            elif tok.lower() in ("buy", "sell", "all"):
                direction = tok.lower()
            else:
                idx_parts.append(tok.upper())
        index = " ".join(idx_parts) if idx_parts else "NIFTY 500"

        msg = mon.start(
            strategy     = strategy,
            index        = index,
            interval_min = interval,
            direction    = direction,
        )
        console.print()
        console.print(f"  {msg}")
        console.print(f"  [dim]Scanning: {index}  ·  Interval: {interval}m  ·  Direction: {direction}[/dim]")
        console.print()
        return

    # Unknown subcommand
    console.print(
        "[dim]  Usage: /monitor [start|stop|status|list]  strategy  [index]  [interval_min]  [buy|sell|all][/dim]\n"
        "[dim]  Example: /monitor start breakout NIFTY 500 15 buy[/dim]"
    )


def _print_help() -> None:
    print()
    console.print(Panel(
        Text.from_markup(
            "[bold cyan]MODE COMMANDS[/bold cyan]\n"
            "  [red]/live[/red]  or  [red]/l[/red]        — Live / Intraday  (real-time NSE API)\n"
            "  [blue]/eod[/blue]   or  [blue]/h[/blue]        — EOD / Historical (CSV + DB snapshot)\n"
            "  [white]/auto[/white]  or  [white]/a[/white]        — Auto-detect from query keywords\n\n"
            "[bold cyan]INTRADAY SCREENER[/bold cyan]\n"
            "  [green]/scan[/green]                   — Scan NIFTY 50 (all strategies, 15m)\n"
            "  [green]/scan NIFTY BANK[/green]        — Scan any index (NIFTY IT, PHARMA…)\n"
            "  [green]/scan orb[/green]               — Opening Range Breakout\n"
            "  [green]/scan gap[/green]               — Gap & Go continuation\n"
            "  [green]/scan macd[/green]              — MACD Crossover only\n"
            "  [green]/scan rsi[/green]               — RSI Divergence + Bollinger\n"
            "  [green]/scan bb[/green]                — Bollinger Band Squeeze\n"
            "  [green]/scan vwap[/green]              — VWAP Reclaim/Loss\n"
            "  [green]/scan vcp[/green]               — VCP Contraction Pattern\n"
            "  [green]/scan momentum[/green]          — MACD + RSI + Supertrend aligned\n\n"
            "[bold cyan]EOD SCREENER[/bold cyan]\n"
            "  [cyan]/screen stage2[/cyan]            — Stage 2 uptrend stocks\n"
            "  [cyan]/screen momentum[/cyan]          — Near-52W-high momentum leaders\n"
            "  [cyan]/screen highrs[/cyan]            — Top RS ≥ 1.15 market leaders\n"
            "  [cyan]/screen turnaround[/cyan]        — Dip recovery setups\n"
            "  [cyan]/screen base[/cyan]              — Stage 1 basing/coiling\n"
            "  [cyan]/screen tight[/cyan]             — Tight weekly range (VCP-like)\n"
            "  [cyan]/screen dip[/cyan]               — Oversold bounce in Stage 2\n"
            "  [cyan]/screen supertrend[/cyan]        — Supertrend BUY state\n"
            "  [cyan]/screen strong[/cyan]            — STRONG_BUY signals\n"
            "  [cyan]/screen new[/cyan]               — New Stage 2 entrants (14d)\n\n"
            "[bold magenta]BACKGROUND MONITORS 🔔[/bold magenta]\n"
            "  [magenta]/monitor list[/magenta]          — Show available strategies\n"
            "  [magenta]/monitor status[/magenta]        — Show active monitors\n"
            "  [magenta]/monitor start breakout[/magenta] — Start breakout alert every 15m\n"
            "  [magenta]/monitor start all 15 buy[/magenta] — All strategies, 15m, BUY only\n"
            "  [magenta]/monitor start momentum NIFTY BANK 10[/magenta] — Custom index + interval\n"
            "  [magenta]/monitor stop breakout[/magenta] — Stop a specific monitor\n"
            "  [magenta]/monitor stop all[/magenta]      — Stop all monitors\n"
            "  [dim]Strategies: breakout · volume_surge · reversal · momentum · supertrend · vcp · all[/dim]\n\n"
            "[bold cyan]GLOBAL MARKET[/bold cyan]\n"
            "  [green]/global[/green]                 — Global risk regime and India read-through\n\n"
            "[bold cyan]PROMPT LIBRARY[/bold cyan]\n"
            "  [yellow]/prompts[/yellow]               — Browse 60 curated prompts\n"
            "  [yellow]/prompts intraday[/yellow]      — Filter by category\n"
            "  [yellow]p<number>[/yellow]              — Run prompt by number  (e.g. p7, p23)\n\n"
            "[bold cyan]RIC — RECURSIVE INVESTIGATIONS[/bold cyan]\n"
            "  [bold yellow]/ric[/bold yellow]                    — Show all 8 prebuilt RICs\n"
            "  [bold yellow]/ric sherlock RELIANCE[/bold yellow]  — 5-step stock investigation\n"
            "  [bold yellow]/ric sector-xray IT[/bold yellow]     — 4-step sector deep dive\n"
            "  [bold yellow]/ric earnings-playbook TCS[/bold yellow] — 5-step earnings analysis\n"
            "  [bold yellow]/ric breakout-hunter[/bold yellow]    — 5-step breakout scan\n"
            "  [bold yellow]/ric morning-intel[/bold yellow]      — 5-step morning briefing\n"
            "  [bold yellow]/ric risk-radar[/bold yellow]         — 4-step risk assessment\n"
            "  [bold yellow]/ric index-pulse NIFTY BANK[/bold yellow] — 4-step index analysis\n"
            "  [bold yellow]/ric peer-battle TCS,INFY,WIPRO[/bold yellow] — 4-step comparison\n\n"
            "[bold cyan]SESSION & CONTEXT[/bold cyan]\n"
            "  [magenta]/context[/magenta]               — Show conversation history + budget\n"
            "  [magenta]/new[/magenta]  or  [magenta]/reset[/magenta]      — Fresh session (clears history)\n\n"
            "[bold cyan]FOLLOW-UPS[/bold cyan]\n"
            "  [yellow]1 / 2 / 3[/yellow]              — Ask the numbered follow-up question\n\n"
            "[bold cyan]OTHER[/bold cyan]\n"
            "  [dim]/clear[/dim]  [dim]exit / quit[/dim]  [dim]Ctrl-C[/dim]\n"
        ),
        title="[bold cyan]Agent Adda Help[/bold cyan]",
        border_style="cyan",
    ))


# ─────────────────────────────────────────────────────────────────────────────
# Spinner (runs while agent is querying)
# ─────────────────────────────────────────────────────────────────────────────

def _run_with_spinner(agent, query: str, show_trace: bool, animated: bool = True) -> dict:
    """Run agent query. animated=True: braille spinner for --query mode.
    animated=False: static status line for the interactive chat loop."""
    result: dict = {}
    exc: list    = []

    if not animated:
        # Chat loop — print static status, then block synchronously
        console.print("[cyan]  ⏳  Agent Adda is thinking…[/cyan]")
        try:
            result = agent.query(query, show_trace=show_trace)
        except Exception as e:
            raise e
        return result

    # Animated braille spinner (--query / single-shot mode)
    done = threading.Event()

    def _worker():
        try:
            result.update(agent.query(query, show_trace=show_trace))
        except Exception as e:
            exc.append(e)
        finally:
            done.set()

    threading.Thread(target=_worker, daemon=True).start()

    frames = itertools.cycle("⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏")
    while not done.wait(0.08):
        f = next(frames)
        sys.stdout.write(f"\r  \x1b[36m{f}\x1b[0m  \x1b[37mAgent Adda is thinking…\x1b[0m  ")
        sys.stdout.flush()
    sys.stdout.write("\r" + " " * 60 + "\r")
    sys.stdout.flush()

    if exc:
        raise exc[0]
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Startup briefing  (runs once on interactive launch)
# ─────────────────────────────────────────────────────────────────────────────

def _greeting() -> str:
    h = datetime.now().hour
    if h < 12:
        return "Good Morning"
    elif h < 17:
        return "Good Afternoon"
    return "Good Evening"


def _run_startup_briefing(agent, show_trace: bool) -> None:
    """Investigative morning/session briefing printed before the chat loop starts."""
    now  = datetime.now()
    hour = now.hour
    date_str = now.strftime("%A, %d %B %Y")
    time_str = now.strftime("%H:%M IST")

    # Determine session context
    if hour < 9:
        session_ctx = "pre-market"
    elif hour < 15 or (hour == 15 and now.minute < 31):
        session_ctx = "live market"
    else:
        session_ctx = "post-market"

    greeting = _greeting()

    console.print()
    console.rule(
        f"[bold yellow] ☀️  Morning Briefing  [/bold yellow]"
        f"[dim]  {date_str}  ·  {time_str} [/dim]",
        style="yellow",
    )
    console.print(
        f"[bold yellow]  {greeting}![/bold yellow]"
        f"[dim]  Loading your market intelligence… ({session_ctx})[/dim]"
    )
    console.print()

    briefing_prompt = f"""
You are starting a new trading session on {date_str} at {time_str} ({session_ctx}).
Give a comprehensive, investigative morning briefing in this EXACT order:

## {greeting} — Market Intelligence Briefing  ({date_str})

### 🌍 Global Overnight Context
- US markets: what happened in the last session (S&P500, NASDAQ, Dow direction + % change if known)
- Asian markets: Nikkei, Hang Seng, Shanghai status
- SGX Nifty / GIFT Nifty: pre-open cue for India
- Key macro events or news overnight that affect Indian markets
- USD/INR direction, crude oil price
(use multi_source_web_search or search_latest_catalysts to get current global data)

### 📅 Previous Trading Day Recap (NSE)
- How did NIFTY 50 and NIFTY BANK close yesterday — gain/loss, % change
- Top 3 gainers and top 3 losers from NIFTY 50 yesterday
- Key sectors that outperformed / underperformed
- Any significant corporate news or events from yesterday
(use get_live_market_overview and any EOD tools available)

### 📊 Current Market Status ({time_str})
- Live NIFTY 50 and NIFTY BANK levels with change
- Market breadth: advances vs declines
- FII/DII activity today
- Top gainers and losers so far today
(use get_live_market_overview, get_top_gainers_losers, get_fii_dii_activity)

### 🎯 Today's Watchlist & Themes
- 3–4 stocks or sectors to watch based on technicals and news flow
- Any important events today: RBI announcements, earnings results, F&O expiry
- Key support/resistance levels for NIFTY 50 intraday

### 🔬 Analyst's Take
- One paragraph synthesis: overall market bias (bullish/bearish/neutral) and recommended approach for today

End with 3 sharp follow-up questions the user might want to explore next.
"""

    console.print("[dim cyan]  ⏳  Compiling briefing…[/dim cyan]")
    try:
        result = agent.query(briefing_prompt, show_trace=show_trace)
        _print_briefing_response(result)
    except Exception as e:
        console.print(f"[dim red]  ⚠️  Briefing skipped: {e}[/dim red]")
        console.print()


def _print_briefing_response(result: dict) -> None:
    """Print startup briefing with special styling (wider rule, no 'Agent Adda' header)."""
    global _followups
    answer  = result.get("answer", "")
    if not answer:
        return

    clean, _followups = _parse_followups(answer)

    console.print()
    has_markup = any(c in clean for c in ["**", "##", "- ", "* ", "```", "\n"])
    if has_markup:
        console.print(Markdown(_linkify_markdown(clean)))
    else:
        console.print(_text_with_links(clean), style="white")

    # Inline news/catalysts
    cats = result.get("catalysts")
    if cats:
        items = cats.get("results") or cats.get("items") or cats.get("news_articles") or []
        if isinstance(items, dict):
            flat = []
            for source, hits in items.items():
                if isinstance(hits, list):
                    for h in hits:
                        if isinstance(h, dict):
                            h = dict(h)
                            h.setdefault("source", source)
                            flat.append(h)
            items = flat
        items = [r for r in items if isinstance(r, dict) and (r.get("title") or r.get("url"))]
        if items:
            console.print()
            console.rule("[bold cyan] 📰  News & Catalysts [/bold cyan]", style="dim cyan")
            for r in items[:6]:  # cap to 6 on startup
                _render_news_item(r, cap=120)

    # Follow-up suggestions
    if _followups:
        console.print()
        console.rule("[bold yellow] 💬  Start your session [/bold yellow]",
                     style="dim yellow")
        for i, q in enumerate(_followups, 1):
            console.print(f"  [bold yellow]{i}[/bold yellow]  {q}")
        console.print("[dim]  Reply 1 · 2 · 3 or ask your own question[/dim]")

    console.print()
    _separator()


# ─────────────────────────────────────────────────────────────────────────────
# Single-query mode  (no TUI, just print result and exit)
# ─────────────────────────────────────────────────────────────────────────────

def _single_query(agent, query: str, show_trace: bool) -> None:
    _print_user(query)
    result = _run_with_spinner(agent, query, show_trace)
    _print_response(result)
    if show_trace:
        _print_trace(result.get("trace", []))


# ─────────────────────────────────────────────────────────────────────────────
# Interactive chat loop
# ─────────────────────────────────────────────────────────────────────────────

def _chat_loop(agent, show_trace: bool) -> None:
    global _mode, _followups

    session = PromptSession(
        history=InMemoryHistory(),
        completer=_AgentCompleter(),
        complete_while_typing=True,
        auto_suggest=AutoSuggestFromHistory(),
        style=_COMPLETER_STYLE,
    )

    console.print("[bold green]  ✓ Agent Adda ready[/bold green] — type your question and press Enter")
    console.print("[dim]  Tip: /live  /eod  /auto  │  /prompts  │  /ric  │  1·2·3 = follow-ups  │  /new  │  /help  │  exit[/dim]")
    console.print()

    while True:
        # ── Drain background monitor alerts before each prompt ─────────
        _check_monitor_alerts()

        try:
            raw = session.prompt(_build_prompt(agent))
        except KeyboardInterrupt:
            console.print()
            continue
        except EOFError:
            break

        text = raw.strip()
        if not text:
            continue

        # ── Exit ──────────────────────────────────────────────────────
        if text.lower() in ("exit", "quit", "q", ":q"):
            break

        # ── Mode commands ──────────────────────────────────────────────
        if text.lower() in ("/live", "/intraday", "/l"):
            _mode = "intraday"
            console.print("[bold red]  ● Mode → LIVE  (real-time NSE API)[/bold red]")
            continue
        if text.lower() in ("/eod", "/historical", "/h"):
            _mode = "historical"
            console.print("[bold blue]  ● Mode → EOD  (historical CSV + DB snapshot)[/bold blue]")
            continue
        if text.lower() in ("/auto", "/a"):
            _mode = "auto"
            console.print("[dim]  ● Mode → AUTO  (keyword-based detection)[/dim]")
            continue

        # ── Utility commands ───────────────────────────────────────────
        if text.lower() in ("/help", "?", "/h"):
            _print_help()
            continue
        if text.lower() == "/clear":
            _followups = []
            os.system("clear")
            print_banner()
            continue

        # ── /new: reset conversation context ──────────────────────────
        if text.lower() in ("/new", "/reset", "/fresh"):
            n = agent.turn_count
            agent.reset_history()
            _followups = []
            console.print(
                f"[bold yellow]  🔄  New session started[/bold yellow]"
                f"[dim]  (cleared {n} turn{'s' if n != 1 else ''} of context)[/dim]"
            )
            continue

        # ── /monitor: background alert workers ────────────────────────
        if text.lower().startswith("/monitor"):
            parts = text.split()
            _handle_monitor_command(parts)
            continue

        # ── /ric: recursive investigative conversation ─────────────────
        if text.lower().startswith("/ric"):
            parts = text.split(maxsplit=2)
            if len(parts) == 1:
                _print_ric_library()
            else:
                ric_key = parts[1].lower()
                ric_arg = parts[2] if len(parts) > 2 else ""
                _run_ric(agent, ric_key, ric_arg, show_trace)
            continue

        # ── /context: show session summary ────────────────────────────
        if text.lower() in ("/context", "/session", "/history"):
            _print_context_summary(agent)
            continue

        # ── /global shortcut: run global assessment ───────────────────
        if text.lower().startswith("/global"):
            parts = text.split(maxsplit=1)
            topic = parts[1].strip() if len(parts) > 1 else "market assessment for India"
            text = f"global {topic}"
            console.print(f"[dim]  → Global assessment: {topic}[/dim]")

        # ── /prompts library ───────────────────────────────────────────
        if text.lower().startswith("/prompts") or text.lower() == "/p":
            parts = text.split(maxsplit=1)
            fkey  = parts[1].strip() if len(parts) > 1 else ""
            _print_prompts_library(fkey)
            continue

        # ── /scan shortcut: run intraday screener ──────────────────────
        if text.lower().startswith("/scan"):
            parts = text.split(maxsplit=1)
            arg   = parts[1].strip() if len(parts) > 1 else ""
            # Map short aliases to screener types
            _scan_aliases = {
                "orb":      ("opening_range_breakout", "Opening Range Breakout"),
                "gap":      ("gap_and_go",             "Gap & Go"),
                "macd":     ("macd_crossover",         "MACD Crossover"),
                "rsi":      ("rsi_divergence",         "RSI Divergence"),
                "bb":       ("bb_squeeze",             "Bollinger Squeeze"),
                "vwap":     ("vwap_reclaim",           "VWAP Reclaim"),
                "vcp":      ("vcp",                    "VCP"),
                "momentum": ("momentum",               "Momentum"),
            }
            alias_key = arg.lower()
            if alias_key in _scan_aliases:
                st, st_label = _scan_aliases[alias_key]
                text = f"Run intraday screener {st} on NIFTY 500 on 15m charts"
                console.print(f"[dim]  → Intraday screener: {st_label}[/dim]")
            else:
                idx = arg.upper() if arg else "NIFTY 50"
                text = f"Scan {idx} for intraday research setups using all strategies on 15m charts"
                console.print(f"[dim]  → Intraday scan: {idx}[/dim]")

        # ── /screen shortcut: run EOD screener ────────────────────────
        if text.lower().startswith("/screen"):
            parts = text.split(maxsplit=1)
            arg   = parts[1].strip().lower() if len(parts) > 1 else "stage2"
            _screen_aliases = {
                "stage2":     ("stage2",          "Stage 2 Uptrend"),
                "breakouts":  ("breakouts",       "Stage 2 Breakouts"),
                "supertrend": ("supertrend_buy",  "Supertrend BUY"),
                "strong":     ("strong_buy",      "Strong Buy"),
                "new":        ("new_entrants",    "New Stage 2 Entrants"),
                "momentum":   ("momentum_52w",    "52W High Momentum Leaders"),
                "highrs":     ("high_rs",         "High RS Leaders"),
                "turnaround": ("turnaround",      "Turnaround Recovery"),
                "base":       ("stage1_base",     "Stage 1 Basing"),
                "tight":      ("tight_range",     "Tight Range VCP"),
                "dip":        ("oversold_bounce", "Oversold Bounce"),
            }
            if arg in _screen_aliases:
                st, st_label = _screen_aliases[arg]
                text = f"Run EOD screener {st} and show the top results with technical context"
                console.print(f"[dim]  → EOD screener: {st_label}[/dim]")
            else:
                text = f"Run EOD screener {arg} and show top results"
                console.print(f"[dim]  → EOD screener: {arg}[/dim]")

        # ── p<n> prompt library shortcut ───────────────────────────────
        import re as _re
        _pm = _re.fullmatch(r"p(\d{1,3})", text.lower())
        if _pm:
            pnum = int(_pm.group(1))
            if pnum in _PROMPT_INDEX:
                _cat, _ptitle, _pquery = _PROMPT_INDEX[pnum]
                console.print(f"[dim]  → [bold]{_ptitle}[/bold]  ({_cat})[/dim]")
                text = _pquery
            else:
                console.print(f"[dim red]  ✗  No prompt p{pnum}. Type /prompts to browse.[/dim red]")
                continue

        # ── Follow-up shortcut ─────────────────────────────────────────
        if text in ("1", "2", "3") and _followups:
            idx = int(text) - 1
            if idx < len(_followups):
                text = _followups[idx]
                console.print(f"[dim]  → {text}[/dim]")

        # ── Apply mode prefix ──────────────────────────────────────────
        if _mode == "intraday":
            query = f"/intraday {text}"
        elif _mode == "historical":
            query = f"/historical {text}"
        else:
            query = text

        _print_user(text)

        try:
            result = _run_with_spinner(agent, query, show_trace, animated=False)
            _print_response(result)
            if show_trace:
                _print_trace(result.get("trace", []))
        except Exception as e:
            console.print(f"[bold red]  ❌  Error: {e}[/bold red]")
            _separator()

    console.print()
    console.print("[bold cyan]  Agent Adda closed. Goodbye! 🏛[/bold cyan]")
    console.print()


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Agent Adda — NSE Market Research Chat"
    )
    parser.add_argument("--query", "-q", default="",
                        help="Single query (non-interactive)")
    parser.add_argument("--trace", "-t", action="store_true",
                        help="Show tool execution trace")
    parser.add_argument("--mode",  "-m", default="auto",
                        choices=["auto", "intraday", "historical"],
                        help="Default data mode (default: auto)")
    parser.add_argument("--no-briefing", "-nb", action="store_true",
                        help="Skip the startup market briefing")
    args = parser.parse_args()

    global _mode
    _mode = args.mode

    print_banner()

    sys.stdout.write("\x1b[36m  Loading Agent Adda…\x1b[0m\r")
    sys.stdout.flush()
    from terminal.agent import Agent
    agent = Agent()
    console.print(f"[bold green]  ✓ Agent Adda ready[/bold green]"
                  f"[dim]  │  backend: {agent.backend_name}"
                  f"  │  mode: {_mode}[/dim]")
    console.print()

    if args.query:
        _single_query(agent, args.query, args.trace)
        return

    # ── Startup briefing (skip with --no-briefing or -nb) ─────────────────
    if not args.no_briefing:
        _run_startup_briefing(agent, args.trace)

    _chat_loop(agent, args.trace)


if __name__ == "__main__":
    main()
