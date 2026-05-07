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
from rich.style import Style as RichStyle
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



# ASCII art generated with pyfiglet 'big' font (hardcoded for portability)
_BANNER = [
    (Fore.CYAN   + Style.BRIGHT, r"          _____ ______ _   _ _______             _____  _____"),
    (Fore.CYAN   + Style.BRIGHT, r"    /\   / ____|  ____| \ | |__   __|      /\   |  __ \|  __ \   /\ "),
    (Fore.GREEN  + Style.BRIGHT, r"   /  \ | |  __| |__  |  \| |  | |        /  \  | |  | | |  | | /  \ "),
    (Fore.GREEN  + Style.BRIGHT, r"  / /\ \| | |_ |  __| | . ` |  | |       / /\ \ | |  | | |  | |/ /\ \ "),
    (Fore.YELLOW + Style.BRIGHT, r" / ____ \ |__| | |____| |\  |  | |      / ____ \| |__| | |__| / ____ \ "),
    (Fore.YELLOW + Style.BRIGHT, r"/_/    \_\_____|______|_| \_|  |_|     /_/    \_\_____/|_____/_/    \_\ "),
]

# Box dimensions: art width = 71, box_w = 71, total visible = 75
_BOX_W = 71
_BOX_MID = _BOX_W - 4  # usable interior (after 2-space left + 2-space right margins)


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
    ("/monitor start breakout",      "Start breakout alert monitor (EMA+volume) — default 15m, NIFTY 500"),
    ("/monitor start volume_surge",  "Start volume surge alert monitor"),
    ("/monitor start reversal",      "Start RSI/Bollinger reversal alert monitor"),
    ("/monitor start momentum",      "Start MACD+RSI momentum alert monitor"),
    ("/monitor start supertrend",    "Start Supertrend flip alert monitor"),
    ("/monitor start vcp",           "Start VCP contraction pattern alert monitor"),
    ("/monitor start orb",           "Start Opening Range Breakout alert monitor (5m bars)"),
    ("/monitor start gap_go",        "Start Gap and Go continuation alert monitor"),
    ("/monitor start vwap",          "Start VWAP reclaim/loss alert monitor"),
    ("/monitor start engulfing",     "Start Engulfing candlestick pattern alert monitor"),
    ("/monitor start ema_ribbon",    "Start EMA Ribbon alignment alert monitor"),
    ("/monitor start multi_confirm", "Start Multi-signal confluence alert (3/4 indicators agree)"),
    ("/monitor start rsi_divergence","Start RSI divergence alert monitor"),
    ("/monitor start all",           "Start ALL strategy alerts combined"),
    ("/monitor stop",    "Stop a monitor (e.g. /monitor stop breakout)"),
    ("/monitor stop all","Stop ALL active monitors"),
    # ── F&O / Options commands ─────────────────────────────────────────────
    ("/chain",            "Live option chain (PCR, max pain, OI, greeks)"),
    ("/chain NIFTY",      "NIFTY option chain — nearest expiry"),
    ("/chain BANKNIFTY",  "BANKNIFTY option chain — nearest expiry"),
    ("/chain FINNIFTY",   "FINNIFTY option chain"),
    ("/oi",               "Open Interest analysis (PCR, max pain, support/resistance)"),
    ("/oi NIFTY",         "NIFTY OI analysis"),
    ("/oi BANKNIFTY",     "BANKNIFTY OI analysis"),
    ("/fno",              "Comprehensive F&O overview: chain + futures + strategy"),
    ("/fno NIFTY",        "NIFTY F&O overview"),
    ("/fno BANKNIFTY",    "BANKNIFTY F&O overview"),
    ("/strategy",         "Build a specific options strategy with live pricing"),
    ("/strategy NIFTY long_straddle",    "Long straddle on NIFTY"),
    ("/strategy NIFTY bull_call_spread", "Bull call spread on NIFTY"),
    ("/strategy BANKNIFTY iron_condor",  "Iron condor on BANKNIFTY"),
    # ── Chart commands ─────────────────────────────────────────────────────
    ("/chart",                  "ASCII candlestick chart (candles + volume + RSI)"),
    ("/chart NIFTY",            "NIFTY 3-month ASCII chart"),
    ("/chart BANKNIFTY",        "BANKNIFTY 3-month ASCII chart"),
    ("/chart RELIANCE",         "RELIANCE 3-month ASCII chart"),
    ("/chart HDFCBANK",         "HDFCBANK 3-month ASCII chart"),
    ("/chart NIFTY 1y",         "NIFTY 1-year chart"),
    ("/chart NIFTY 6mo",        "NIFTY 6-month chart"),
    ("/chart NIFTY 1mo rsi",    "NIFTY 1-month with RSI panel"),
    ("/chart RELIANCE 3mo rsi macd", "RELIANCE with RSI + MACD panels"),
    ("/chart RELIANCE --html",  "RELIANCE interactive HTML chart (opens in browser)"),
    ("/chart NIFTY --html",     "NIFTY interactive HTML chart (opens in browser)"),
    ("/chart NIFTY 1y --html",  "NIFTY 1-year interactive HTML chart"),
    ("/chart BANKNIFTY 6mo --html", "BANKNIFTY 6-month HTML chart"),
    # ── Deep Search commands ────────────────────────────────────────────────
    ("/search",                           "Deep search — 11 parallel verticals (NSE+BSE+web)"),
    ("/search RELIANCE",                  "Full deep search on RELIANCE"),
    ("/search RELIANCE announcements",    "NSE corporate announcements for RELIANCE"),
    ("/search RELIANCE dividend",         "Dividend / corporate actions for RELIANCE"),
    ("/search RELIANCE insider",          "Insider trade disclosures for RELIANCE"),
    ("/search RELIANCE shareholding",     "Shareholding pattern & FII/DII trend"),
    ("/search RELIANCE analyst",          "Analyst targets & brokerage recommendations"),
    ("/search RELIANCE broker",           "Broker house research reports & price targets"),
    ("/search RELIANCE mf",               "Mutual fund & institutional holdings"),
    ("/search RELIANCE concall",          "Concall transcripts & management commentary"),
    ("/search RELIANCE news",             "Sector news from 6 portals"),
    ("/search RELIANCE social",           "Retail investor buzz: Reddit, Valuepickr, Traderji"),
    ("/search TATACONSUM deep",           "Full 11-vertical deep search"),
    # ── Forensic commands ───────────────────────────────────────────────────
    ("/forensic",                         "D5 Forensic analysis — Beneish M-score, Piotroski F-score, Altman Z'-score"),
    ("/forensic RELIANCE",                "Forensic accounting analysis for RELIANCE"),
    ("/forensic TCS INFY WIPRO",          "Forensic screening across multiple stocks"),
    # ── Event calendar commands ─────────────────────────────────────────────
    ("/events",                           "E4 Upcoming corporate events — dividends, splits, results, AGMs"),
    ("/events NIFTY 50",                  "Event calendar for NIFTY 50 stocks (next 14 days)"),
    ("/events RELIANCE",                  "Upcoming events for a specific stock"),
    # ── Seasonal / macro / new commands ─────────────────────────────────────
    ("/heat",                             "B3 Sector seasonal heatmap — current-month TAILWIND/HEADWIND"),
    ("/heat 5",                           "Sector heat calendar for May"),
    ("/cycle",                            "B5 Economic cycle phase + preferred/avoid sectors"),
    ("/scenario RELIANCE",                "P2-2 What-if price scenarios for RELIANCE"),
    ("/narrative",                        "P2-4 Portfolio narratives — bull/bear thesis per stock"),
    ("/narrative TCS INFY",               "Investment narratives for specific stocks"),
    ("/voice",                            "P3-2 Generate daily voice briefing (MP3, needs OpenAI key)"),
    ("/concall TCS",                      "D4 Concall NLP — sentiment, themes, risk flags"),
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


def _looks_like_index_arg(arg: str) -> bool:
    arg_up = arg.strip().upper()
    if not arg_up:
        return False
    return (
        arg_up.startswith("NIFTY")
        or "MIDCAP" in arg_up
        or "SMALLCAP" in arg_up
        or "BANK" in arg_up
        or "SENSEX" in arg_up
        or "INDEX" in arg_up
    )


def _run_ric(agent, key: str, arg: str, show_trace: bool) -> None:
    """Execute a named RIC step by step, each result feeding context."""
    if key == "sector-xray" and _looks_like_index_arg(arg):
        # User entered an index basket, not a sector. Route to the index workflow.
        console.print(
            f"[yellow]  ↺  '{arg.strip()}' looks like an index, so routing to "
            f"[bold]/ric index-pulse {arg.strip()}[/bold] instead of sector-xray.[/yellow]"
        )
        key = "index-pulse"

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


def _box_row(mid_text: str, colour: str = "", reset: str = Style.RESET_ALL) -> str:
    """Build a perfectly padded box row: '  ║  <mid_text><pad>  ║'."""
    padding = " " * max(0, _BOX_MID - len(mid_text))
    W = Fore.WHITE + Style.BRIGHT
    return W + "  ║  " + colour + mid_text + padding + W + "  ║" + reset


def print_banner() -> None:
    """Colorama ASCII banner printed to stdout before chat starts."""
    print()
    for colour, line in _BANNER:
        print(colour + line)
    print()
    W = Fore.WHITE + Style.BRIGHT
    print(W + "  ╔" + "═" * _BOX_W + "╗")
    print(_box_row("NSE Market Research Terminal  ·  AI-powered · Real-time",
                   Fore.YELLOW + Style.BRIGHT))
    print(_box_row("stocks · sectors · signals · screeners · intraday · RICs",
                   Fore.CYAN))
    print(W + "  ╚" + "═" * _BOX_W + "╝")
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
          "  /live  /eod  /auto  │  /global  │  /heat  /cycle  /scenario  /narrative  │  /prompts  │  /help  │  exit")
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


def _print_followup_line(num: int, question: str) -> None:
    """
    Render a follow-up question line with the command hint highlighted.

    Handles two formats the LLM produces:
      • "`/command ARG` — description text"       (backtick-quoted slash command)
      • "`natural language prompt` — description" (backtick-quoted phrase)
      • "plain question with no command hint"      (fallback)

    Output:  [1]  /command ARG  —  description text
                  ^^^^^^^^^^^      ^^^^^^^^^^^^^^^^
                  bold cyan        white
    """
    # Extract backtick-quoted command hint at the start
    m = re.match(r"`([^`]+)`\s*[-–—]\s*(.+)", question)
    if m:
        cmd_hint = m.group(1).strip()
        desc     = m.group(2).strip()
        # Colour the command hint: slash commands bright cyan, natural prompts dim cyan
        if cmd_hint.startswith("/"):
            cmd_rich = f"[bold cyan]{cmd_hint}[/bold cyan]"
        else:
            cmd_rich = f'[dim cyan]"{cmd_hint}"[/dim cyan]'
        console.print(f"  [bold yellow]{num}[/bold yellow]  {cmd_rich}  [dim]—[/dim]  {desc}")
    else:
        # No command hint — render as plain text
        console.print(f"  [bold yellow]{num}[/bold yellow]  {question}")


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


def _osc8(label: str, url: str, color: str = "cyan") -> Text:
    """Return a Rich Text span as OSC-8 link (iTerm2/WezTerm) + plain label (Terminal.app)."""
    t = Text()
    t.append(label, style=RichStyle(link=url, color=color, underline=True))
    return t


def _html_links_to_visible_urls(text: str) -> str:
    """Convert HTML anchors <a href="url">label</a> → visible 'label → url'.

    Plain visible URLs are required for macOS Terminal.app Cmd+click detection.
    We also emit Markdown [label](url) so Rich Markdown generates OSC-8 for
    terminals that support it (iTerm2, WezTerm, VS Code terminal).
    """
    def _replace(match: re.Match) -> str:
        url   = html.unescape(match.group(1).strip())
        label = html.unescape(_strip_html_tags(match.group(2))).strip() or url
        if label == url:
            return url
        return f"[{label}]({url})"

    return _HTML_LINK_RE.sub(_replace, text)


def _linkify_markdown(text: str) -> str:
    """Convert HTML anchors to Markdown links; leave [label](url) intact for Rich Markdown."""
    return _html_links_to_visible_urls(text)


def _append_bare_url_links(target: Text, text: str) -> None:
    """Append text; bare URLs rendered as cyan OSC-8 links AND visible text (dual compat)."""
    pos = 0
    for match in _URL_RE.finditer(text):
        if match.start() > pos:
            target.append(text[pos:match.start()])
        raw = match.group(1)
        url = raw.rstrip(".,;)")
        trailing = raw[len(url):]
        # Visible cyan URL — Cmd+click in Terminal.app; OSC-8 in iTerm2/WezTerm
        target.append(url, style=RichStyle(link=url, color="cyan"))
        if trailing:
            target.append(trailing)
        pos = match.end()
    if pos < len(text):
        target.append(text[pos:])


def _text_with_links(text: str) -> Text:
    """Create Rich Text; HTML anchors → OSC-8 with visible label; bare URLs → visible cyan."""
    out = Text()
    pos = 0
    for match in _HTML_LINK_RE.finditer(text):
        if match.start() > pos:
            _append_bare_url_links(out, text[pos:match.start()])
        url   = html.unescape(match.group(1).strip())
        label = html.unescape(_strip_html_tags(match.group(2))).strip() or url
        out.append(label, style=RichStyle(link=url, color="cyan", underline=True))
        # Show raw URL on same line so Terminal.app can Cmd+click it
        if label != url:
            out.append(f" {url}", style=RichStyle(color="cyan dim"))
        pos = match.end()
    if pos < len(text):
        _append_bare_url_links(out, text[pos:])
    return out


def _render_news_item(r: dict, cap: int = 140) -> None:
    """Render one news/research item — title + raw URL + snippet.

    Dual-compatible: OSC-8 metadata for iTerm2/WezTerm; raw visible URL for
    macOS Terminal.app (Cmd+click the cyan https:// URL to open in browser).
    """
    title   = r.get("title") or r.get("name") or ""
    url     = r.get("url")   or r.get("link") or ""
    snippet = r.get("snippet") or r.get("body") or ""
    source  = r.get("source", "")

    if source:
        console.print(f"  [dim cyan][{source}][/dim cyan]")

    # Title — bold with OSC-8 link embedded (works in iTerm2/WezTerm)
    if title:
        if url:
            line = Text("  ")
            line.append(title, style=RichStyle(link=url, bold=True, color="white"))
            console.print(line)
        else:
            console.print(f"  [bold]{title}[/bold]")

    # Raw URL always shown as cyan text — macOS Terminal.app: Cmd+click to open
    if url:
        console.print(f"  [cyan]{url}[/cyan]")

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
            _print_followup_line(i, q)
        console.print("[dim]  Reply 1 · 2 · 3 or type the command directly[/dim]")

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
            "  [dim]Strategies (14): breakout · volume_surge · reversal · momentum · supertrend · vcp[/dim]\n"
            "  [dim]               · orb · gap_go · vwap · engulfing · ema_ribbon · multi_confirm[/dim]\n"
            "  [dim]               · rsi_divergence · all[/dim]\n\n"
            "[bold yellow]F&O / OPTIONS 📊[/bold yellow]\n"
            "  [yellow]/chain NIFTY[/yellow]           — Live option chain (PCR, max pain, OI, greeks)\n"
            "  [yellow]/chain BANKNIFTY[/yellow]       — BANKNIFTY option chain\n"
            "  [yellow]/oi NIFTY[/yellow]              — OI analysis (support/resistance, PCR)\n"
            "  [yellow]/fno NIFTY[/yellow]             — Full F&O overview (chain + futures + strategy)\n"
            "  [yellow]/strategy NIFTY long_straddle[/yellow]    — Build a specific options strategy\n"
            "  [yellow]/strategy NIFTY bull_call_spread[/yellow] — Bull call spread with pricing\n"
            "  [dim]Strategies: long_call · long_put · bull_call_spread · bear_put_spread ·[/dim]\n"
            "  [dim]            long_straddle · long_strangle · iron_condor · covered_call ·[/dim]\n"
            "  [dim]            protective_put · calendar_spread[/dim]\n\n"
            "[bold green]CHARTS 📈[/bold green]\n"
            "  [green]/chart RELIANCE[/green]               — ASCII candlestick (3mo, candles+volume+RSI)\n"
            "  [green]/chart NIFTY 6mo rsi macd[/green]    — Custom timeframe + indicators\n"
            "  [green]/chart RELIANCE --html[/green]        — Interactive HTML chart → opens in browser\n"
            "  [green]/chart NIFTY 1y --html[/green]        — 1-year interactive chart in browser\n"
            "  [dim]Timeframes: 1d · 5d · 1mo · 3mo · 6mo · 1y · 2y[/dim]\n"
            "  [dim]Indicators: volume · rsi · macd  (ASCII default: volume rsi)[/dim]\n"
            "  [dim]HTML chart: candlestick + EMA20/50/200 + Bollinger Bands + volume + RSI + MACD[/dim]\n\n"
            "[bold magenta]DEEP SEARCH ENGINE 🔍[/bold magenta]\n"
            "  [magenta]/search RELIANCE[/magenta]           — Full deep-dive (11 parallel verticals)\n"
            "  [magenta]/search RELIANCE dividend[/magenta]  — Dividends, splits, bonuses (NSE live)\n"
            "  [magenta]/search RELIANCE insider[/magenta]   — Insider/promoter trade disclosures\n"
            "  [magenta]/search RELIANCE shareholding[/magenta] — Promoter/FII/DII/pledge trend\n"
            "  [magenta]/search RELIANCE analyst[/magenta]   — Analyst targets + broker reports\n"
            "  [magenta]/search RELIANCE broker[/magenta]    — Broker house research & price targets\n"
            "  [magenta]/search RELIANCE mf[/magenta]        — Mutual fund & institutional holdings\n"
            "  [magenta]/search RELIANCE concall[/magenta]   — Concall transcripts & mgmt commentary\n"
            "  [magenta]/search RELIANCE news[/magenta]      — 6-portal sector news pulse\n"
            "  [magenta]/search RELIANCE social[/magenta]    — Reddit, Valuepickr, Traderji buzz\n"
            "  [dim]Verticals: announcements · corporate_actions · insider_trades · bse_filings[/dim]\n"
            "  [dim]           shareholding · analyst_coverage · broker_research · mf_holdings[/dim]\n"
            "  [dim]           concalls · sector_news · social_buzz[/dim]\n\n"
            "[bold red]FORENSIC ACCOUNTING 🧪[/bold red]\n"
            "  [red]/forensic RELIANCE[/red]           — Beneish M-score + Piotroski F-score + Altman Z'\n"
            "  [red]/forensic TCS INFY WIPRO[/red]     — Forensic screening across multiple stocks\n"
            "  [dim]Beneish M-score: M > -1.78 = manipulation risk (8-variable probit model)[/dim]\n"
            "  [dim]Piotroski F-score: 0-9 (7+ = strong, 0-3 = weak financial health)[/dim]\n"
            "  [dim]Altman Z'-score: Z' < 1.1 = distress zone (emerging-market version)[/dim]\n\n"
            "[bold yellow]EVENT CALENDAR 📅[/bold yellow]\n"
            "  [yellow]/events[/yellow]                  — Upcoming events for NIFTY 50 (next 14 days)\n"
            "  [yellow]/events NIFTY 50[/yellow]         — Dividends, splits, results, AGMs, board meetings\n"
            "  [yellow]/events RELIANCE[/yellow]         — Upcoming events for a specific stock\n"
            "  [yellow]/events NIFTY 50 30[/yellow]      — Extend window to 30 days\n\n"
            "[bold blue]SEASONAL & MACRO 🌡[/bold blue]\n"
            "  [blue]/heat[/blue]                    — Sector seasonal heatmap (current month signals)\n"
            "  [blue]/heat 3[/blue]                  — Seasonal signals for March\n"
            "  [blue]/cycle[/blue]                   — Economic cycle phase + sector positioning\n"
            "  [blue]/scenario TCS[/blue]             — What-if price scenarios for TCS\n"
            "  [blue]/narrative[/blue]               — Portfolio investment narratives\n"
            "  [blue]/narrative TCS INFY[/blue]       — Narratives for specific stocks\n"
            "  [blue]/voice[/blue]                   — Generate daily voice briefing (MP3)\n"
            "  [blue]/concall TCS[/blue]              — Concall NLP: sentiment + themes + guidance\n\n"
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
            _print_followup_line(i, q)
        console.print("[dim]  Reply 1 · 2 · 3 or type the command directly[/dim]")

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

        # ── /chart <symbol> [tf] [--html] [indicators...] — chart ────
        if text.lower().startswith("/chart"):
            parts = text.split()
            sym   = parts[1].upper() if len(parts) > 1 else "NIFTY"
            _valid_tfs  = {"1d", "5d", "1mo", "3mo", "6mo", "1y", "2y"}
            _valid_inds = {"rsi", "macd", "volume"}
            tf          = "3mo"
            html_mode   = False
            remaining   = []
            for p in parts[2:]:
                pl = p.lower()
                if pl in _valid_tfs:
                    tf = pl
                elif pl in ("--html", "html", "-h"):
                    html_mode = True
                elif pl in _valid_inds:
                    remaining.append(pl)
            indicators = remaining or (["volume", "rsi", "macd"] if html_mode else ["volume", "rsi"])

            if html_mode:
                console.print(f"[dim]  → HTML Chart: {sym} [{tf}] opening in browser…[/dim]")
                try:
                    from terminal.charts import render_html_chart
                    fpath = render_html_chart(sym, tf, indicators, open_browser=True)
                    console.print(f"[bold green]  📊  Chart opened in browser[/bold green]  [dim]{fpath}[/dim]")
                except Exception as _e:
                    console.print(f"[bold red]  ❌  HTML Chart error: {_e}[/bold red]")
                text = (
                    f"Give a technical summary for {sym} ({tf}): trend, "
                    f"key levels, RSI, MACD, and what to watch next."
                )
            else:
                console.print(f"[dim]  → ASCII Chart: {sym} [{tf}] indicators: {', '.join(indicators)}[/dim]")
                try:
                    from terminal.charts import render_chart
                    chart_out = render_chart(sym, tf, indicators)
                    console.print()
                    console.print(chart_out)
                    console.print()
                except Exception as _e:
                    console.print(f"[bold red]  ❌  Chart error: {_e}[/bold red]")
                text = (
                    f"Give a brief technical summary for {sym} chart ({tf}): "
                    f"trend direction, key support/resistance levels, RSI reading, "
                    f"MACD status, and what to watch for next."
                )

        # ── /search <symbol> [vertical/context] — deep search engine ──────
        if text.lower().startswith("/search"):
            parts   = text.split()
            sym     = parts[1].upper() if len(parts) > 1 else "RELIANCE"
            context = " ".join(parts[2:]) if len(parts) > 2 else ""

            # Map shorthand tokens to readable context for the LLM
            _CTX_MAP = {
                "div":          "dividend corporate actions ex-date",
                "dividend":     "dividend corporate actions ex-date",
                "insider":      "insider trades promoter buying selling",
                "holding":      "shareholding promoter FII DII pledge",
                "shareholding": "shareholding promoter FII DII trend",
                "analyst":      "analyst targets brokerage recommendations",
                "concall":      "concall transcript management commentary",
                "news":         "latest news sector news",
                "social":       "social buzz retail investor sentiment",
                "bse":          "BSE filings board meeting",
                "deep":         "",
                "full":         "",
            }
            ctx_key  = context.strip().lower().split()[0] if context else ""
            ctx_desc = _CTX_MAP.get(ctx_key, context)

            # Map context to specific verticals
            _VERT_MAP = {
                "div":          ["corporate_actions", "announcements"],
                "dividend":     ["corporate_actions", "announcements"],
                "insider":      ["insider_trades", "shareholding"],
                "holding":      ["shareholding", "insider_trades"],
                "shareholding": ["shareholding", "insider_trades", "mf_holdings"],
                "analyst":      ["analyst_coverage", "broker_research", "concalls"],
                "broker":       ["broker_research", "analyst_coverage"],
                "mf":           ["mf_holdings", "shareholding"],
                "concall":      ["concalls", "bse_filings"],
                "news":         ["sector_news", "announcements"],
                "social":       ["social_buzz", "analyst_coverage"],
                "bse":          ["bse_filings", "announcements"],
            }
            forced_verts = _VERT_MAP.get(ctx_key)

            if forced_verts:
                vert_str = ", ".join(forced_verts)
                console.print(f"[dim]  → Deep Search: [bold]{sym}[/bold] — verticals: {vert_str}[/dim]")
                text = (
                    f"Run deep_search for {sym} using verticals {forced_verts} with context '{ctx_desc}'. "
                    f"Present all results clearly — include dates, URLs, and key insights for each vertical."
                )
            else:
                console.print(f"[dim]  → Deep Search: [bold]{sym}[/bold] — all verticals[/dim]")
                text = (
                    f"Run a comprehensive deep search for {sym}. "
                    f"Use deep_search with all default verticals. "
                    f"Context: '{ctx_desc or 'full overview'}'. "
                    f"Present results section-by-section: "
                    f"NSE announcements, corporate actions, insider trades, "
                    f"shareholding, analyst targets, concalls, sector news. "
                    f"Include dates, real URLs, and actionable insights."
                )

        # ── /forensic <symbol> [symbol2 ...] — forensic accounting ───────
        elif text.lower().startswith("/forensic"):
            parts = text.split()
            syms  = [p.upper() for p in parts[1:] if p]
            if not syms:
                syms = ["RELIANCE"]

            if len(syms) == 1:
                console.print(f"[dim]  → Forensic Analysis: [bold]{syms[0]}[/bold] (Beneish + Piotroski + Altman)[/dim]")
                text = (
                    f"Run run_forensic_analysis for {syms[0]}. "
                    f"Present all three scores clearly: "
                    f"(1) Beneish M-score — is there earnings manipulation risk? Explain each variable flagged. "
                    f"(2) Piotroski F-score — what is the financial health? Show all 9 signals. "
                    f"(3) Altman Z'-score — what is the distress zone? "
                    f"Conclude with overall risk verdict and actionable insights for the investor."
                )
            else:
                sym_str = ", ".join(syms)
                console.print(f"[dim]  → Forensic Screen: [bold]{sym_str}[/bold][/dim]")
                text = (
                    f"Run screen_forensic_watchlist for symbols {syms}. "
                    f"Rank by overall risk (high → low). "
                    f"For each stock show: Beneish M-score (manipulation risk), "
                    f"Piotroski F-score (financial health), Altman Z'-score (distress risk). "
                    f"Highlight any stocks with high risk and explain the specific flags."
                )

        # ── /events [index or symbol] [days] — corporate event calendar ──
        elif text.lower().startswith("/events"):
            parts = text.split()
            # Determine if it's a specific stock or index
            arg1  = parts[1].upper() if len(parts) > 1 else ""
            arg2  = parts[2].upper() if len(parts) > 2 else ""
            days  = 14

            # Try to detect days_ahead as last numeric arg
            for p in parts[1:]:
                try:
                    days = int(p)
                except ValueError:
                    pass

            # Known index names
            _IDX_WORDS = {"NIFTY", "50", "NEXT", "BANK", "500", "MIDCAP", "SMALLCAP", "IT", "PHARMA"}
            raw_sym = " ".join(p for p in parts[1:] if not p.isdigit()).strip().upper()
            is_index = any(w in raw_sym.split() for w in _IDX_WORDS) or not raw_sym

            if is_index or not raw_sym:
                idx = raw_sym or "NIFTY 50"
                console.print(f"[dim]  → Event Calendar: [bold]{idx}[/bold] — next {days} days[/dim]")
                text = (
                    f"Run get_event_calendar_summary for index '{idx}' with days_ahead={days}. "
                    f"Present events grouped by type (Dividend, Results, Bonus, Split, AGM, Board Meeting). "
                    f"Show upcoming ex-dates with days-until countdown. "
                    f"Highlight events in the next 7 days separately."
                )
            else:
                console.print(f"[dim]  → Events for: [bold]{raw_sym}[/bold][/dim]")
                text = (
                    f"Run get_upcoming_events with symbols=['{raw_sym}'] and days_ahead={days}. "
                    f"List all upcoming corporate events: dividends, results, board meetings, "
                    f"AGMs, splits, bonuses. Include ex-dates and days-until countdown."
                )

        # ── /heat [month] — sector seasonal heatmap (direct render) ─────
        elif text.lower().startswith("/heat"):
            parts = text.split()
            month_arg = None
            for p in parts[1:]:
                try:
                    month_arg = int(p)
                except ValueError:
                    pass
            month_str = f" month={month_arg}" if month_arg else " (current month)"
            console.print(f"[dim]  → Sector Heat Calendar{month_str}[/dim]")
            try:
                from terminal.tools import get_sector_heat_calendar
                from rich.table import Table
                args = {"month": month_arg} if month_arg else {}
                heat = get_sector_heat_calendar(**args)
                if heat.get("error"):
                    console.print(f"[red]  ❌  {heat['error']}[/red]")
                else:
                    _mn = heat["current_month"]
                    _sig = heat["current_month_signals"]
                    _src = heat.get("source", "")
                    # Current-month signal table
                    t = Table(title=f"🌡  Sector Seasonal Signals — {_mn}", box=None, padding=(0, 2))
                    t.add_column("Sector",  style="bold")
                    t.add_column("Signal",  justify="center")
                    t.add_column("Avg Return", justify="right")
                    heat_hm = heat.get("heatmap", {})
                    rows_sig = sorted(_sig.items(), key=lambda x: heat_hm.get(x[0], {}).get(_mn, 0), reverse=True)
                    for sec, sig in rows_sig:
                        avg = heat_hm.get(sec, {}).get(_mn, 0)
                        if sig == "TAILWIND":
                            colour = "bold green"
                            icon   = "🟢 TAILWIND"
                        elif sig == "HEADWIND":
                            colour = "bold red"
                            icon   = "🔴 HEADWIND"
                        else:
                            colour = "dim"
                            icon   = "⚪ NEUTRAL"
                        t.add_row(sec, f"[{colour}]{icon}[/{colour}]", f"[{colour}]{avg:+.1f}%[/{colour}]")
                    console.print()
                    console.print(t)
                    # 12-month heatmap
                    mnths = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
                    t2 = Table(title="📅  12-Month Heatmap (avg monthly return %)", box=None, padding=(0, 1))
                    t2.add_column("Sector", style="bold")
                    for mn in mnths:
                        t2.add_column(mn, justify="right", min_width=5)
                    for sec in sorted(heat_hm.keys()):
                        row_vals = []
                        for mn in mnths:
                            v = heat_hm[sec].get(mn, 0)
                            colour = "green" if v > 2 else ("red" if v < -1 else "")
                            cell = f"[{colour}]{v:+.1f}[/{colour}]" if colour else f"{v:+.1f}"
                            row_vals.append(cell)
                        t2.add_row(sec, *row_vals)
                    console.print()
                    console.print(t2)
                    console.print(f"[dim]  Source: {_src}[/dim]")
                    console.print()
                    # Follow-up LLM narrative
                    text = (
                        f"The sector heat calendar for {_mn} shows: "
                        f"TAILWIND sectors: {heat['tailwinds']}; "
                        f"NEUTRAL: {heat['neutral']}. "
                        f"Data source: {_src}. "
                        f"Give 3-4 bullet actionable insights: which sectors to rotate into, "
                        f"which to underweight, and how this aligns with the current market environment."
                    )
            except Exception as _e:
                console.print(f"[bold red]  ❌  Heat calendar error: {_e}[/bold red]")
                text = f"Sector heat calendar error: {_e}"

        # ── /cycle — economic cycle assessment (direct render) ────────
        elif text.lower().startswith("/cycle"):
            console.print("[dim]  → Economic Cycle Assessment[/dim]")
            try:
                from terminal.tools import get_economic_cycle_assessment, get_sector_heat_calendar
                from rich.table import Table
                cycle = get_economic_cycle_assessment()
                if cycle.get("error"):
                    console.print(f"[red]  ❌  {cycle['error']}[/red]")
                else:
                    phase   = cycle["cycle_phase"]
                    conf    = cycle["confidence"]
                    pref    = cycle["preferred_sectors"]
                    avoid   = cycle["avoid_sectors"]
                    macro   = cycle.get("macro_snapshot", {})
                    defn    = cycle.get("definition", "")
                    _PHASE_COLOUR = {
                        "EARLY_EXPANSION": "green",
                        "LATE_EXPANSION":  "yellow",
                        "SLOWDOWN":        "red",
                        "RECOVERY":        "cyan",
                    }
                    pc = _PHASE_COLOUR.get(phase, "white")
                    console.print()
                    console.print(f"  📊  Economic Cycle Phase: [bold {pc}]{phase}[/bold {pc}]  "
                                  f"[dim](confidence {conf:.0%})[/dim]")
                    console.print(f"  [dim]{defn}[/dim]")
                    console.print()
                    console.print(f"  [bold green]Preferred sectors:[/bold green] {', '.join(pref)}")
                    console.print(f"  [bold red]Avoid sectors:[/bold red]     {', '.join(avoid)}")
                    # Macro table
                    if macro:
                        t = Table(title="🌐  Macro Signal Snapshot", box=None, padding=(0, 2))
                        t.add_column("Indicator", style="bold")
                        t.add_column("Signal",    justify="center")
                        t.add_column("Value",     justify="right")
                        t.add_column("Direction", justify="center")
                        for ind, d in macro.items():
                            sig  = d.get("signal", "")
                            val  = d.get("value", "")
                            dirn = d.get("direction", "")
                            sig_colour = "green" if "bull" in sig.lower() or "low" in sig.lower() else \
                                         "red" if "bear" in sig.lower() or "high" in sig.lower() else ""
                            t.add_row(
                                ind,
                                f"[{sig_colour}]{sig}[/{sig_colour}]" if sig_colour else sig,
                                val, dirn
                            )
                        console.print()
                        console.print(t)
                    console.print()
                    text = (
                        f"Economic cycle is {phase} with {conf:.0%} confidence. "
                        f"Preferred sectors: {pref}. Avoid: {avoid}. "
                        f"Definition: {defn}. "
                        f"Give actionable sector rotation strategy: what to buy, "
                        f"what to trim, and 2 stock ideas in the preferred sectors."
                    )
            except Exception as _e:
                console.print(f"[bold red]  ❌  Cycle assessment error: {_e}[/bold red]")
                text = f"Cycle assessment error: {_e}"

        # ── /scenario <symbol> [prices...] — scenario engine (direct) ─
        elif text.lower().startswith("/scenario"):
            parts = text.split()
            sym   = parts[1].upper() if len(parts) > 1 else ""
            if not sym:
                console.print("[bold red]  Usage: /scenario SYMBOL [price1 price2 ...][/bold red]")
            else:
                prices_raw = []
                for p in parts[2:]:
                    try:
                        prices_raw.append(float(p))
                    except ValueError:
                        pass
                console.print(f"[dim]  → Scenario Analysis: {sym}[/dim]")
                try:
                    from terminal.tools import run_scenario_analysis
                    from rich.table import Table
                    args = {"symbol": sym}
                    if prices_raw:
                        args["price_scenarios"] = prices_raw
                    scen = run_scenario_analysis(**args)
                    if scen.get("error"):
                        console.print(f"[red]  ❌  {scen['error']}[/red]")
                    else:
                        kl = scen["key_levels"]
                        console.print()
                        console.print(f"  [bold]{sym}[/bold]  Current: [bold]₹{scen['current_price']:,.0f}[/bold]  "
                                      f"Stage: [cyan]{scen['current_stage']}[/cyan]  RSI: {scen['current_rsi']:.1f}")
                        console.print(f"  Support ₹{kl['support']:,.0f}  │  Resistance ₹{kl['resistance']:,.0f}  "
                                      f"│  50-DMA ₹{kl['ma50']:,.0f}  │  200-DMA ₹{kl['ma200']:,.0f}")
                        t = Table(title=f"📐  What-If Scenarios — {sym}", box=None, padding=(0, 2))
                        t.add_column("Scenario",  style="bold")
                        t.add_column("Price",     justify="right")
                        t.add_column("% Chg",     justify="right")
                        t.add_column("RSI est.",  justify="right")
                        t.add_column("Stage Implication")
                        t.add_column("Notes", style="dim")
                        for s in scen["scenarios"]:
                            pct = s["pct_change"]
                            pc = "green" if pct > 0 else ("red" if pct < 0 else "")
                            pct_str = f"[{pc}]{pct:+.1f}%[/{pc}]" if pc else f"{pct:+.1f}%"
                            t.add_row(
                                s["label"], f"₹{s['price']:,.0f}", pct_str,
                                f"{s['rsi_estimate']:.0f}",
                                s["stage_implication"], s["notes"],
                            )
                        console.print()
                        console.print(t)
                        console.print()
                        text = (
                            f"{sym} scenario analysis: current ₹{scen['current_price']:,.0f}, "
                            f"stage {scen['current_stage']}, RSI {scen['current_rsi']:.1f}. "
                            f"Key levels: support ₹{kl['support']:,.0f}, resistance ₹{kl['resistance']:,.0f}. "
                            f"Give: (1) where to set a stop-loss, (2) which scenario is most likely "
                            f"given current market conditions, (3) risk/reward at current entry."
                        )
                except Exception as _e:
                    console.print(f"[bold red]  ❌  Scenario error: {_e}[/bold red]")
                    text = f"Scenario analysis error for {sym}: {_e}"

        # ── /narrative [symbol ...] — portfolio narratives (direct) ───
        elif text.lower().startswith("/narrative"):
            parts = text.split()
            syms  = [p.upper() for p in parts[1:] if p.isalpha() and len(p) >= 2]
            lbl   = ", ".join(syms) if syms else "portfolio holdings"
            console.print(f"[dim]  → Portfolio Narratives: {lbl}[/dim]")
            try:
                from terminal.tools import generate_portfolio_narratives
                from rich.table import Table
                args = {"symbols": syms, "top_n": len(syms)} if syms else {}
                narr = generate_portfolio_narratives(**args)
                if narr.get("error"):
                    console.print(f"[red]  ❌  {narr['error']}[/red]")
                else:
                    for n in narr.get("narratives", []):
                        sym_n = n["symbol"]
                        act   = n.get("action_hint", "")
                        act_c = "green" if "Hold" in act or "Add" in act else \
                                ("red" if "Avoid" in act or "Exit" in act else "yellow")
                        console.print()
                        console.print(f"  [bold]{sym_n}[/bold]  "
                                      f"[dim]{n.get('stage','')}  RSI:{n.get('rsi','')}[/dim]  "
                                      f"[bold {act_c}]{act}[/bold {act_c}]")
                        console.print(f"  [green]▲ Bull:[/green] {n.get('thesis','')}")
                        console.print(f"  [red]▼ Bear:[/red] {n.get('bear_case','')}")
                        if n.get("signals"):
                            console.print(f"  [dim]Signals: {', '.join(n['signals'])}[/dim]")
                    console.print()
                    syms_str = ", ".join(n["symbol"] for n in narr.get("narratives", []))
                    text = (
                        f"Portfolio narratives generated for: {syms_str}. "
                        f"Which of these stocks has the best risk/reward right now? "
                        f"Give a 3-sentence portfolio prioritization verdict."
                    )
            except Exception as _e:
                console.print(f"[bold red]  ❌  Narrative error: {_e}[/bold red]")
                text = f"Narrative generation error: {_e}"

        # ── /voice [text...] — voice briefing (direct) ────────────────
        elif text.lower().startswith("/voice"):
            parts = text.split(maxsplit=1)
            custom = parts[1].strip() if len(parts) > 1 else ""
            console.print("[dim]  → Voice Briefing (OpenAI TTS)[/dim]")
            try:
                from terminal.tools import generate_voice_briefing
                args = {"text": custom} if custom else {}
                vb = generate_voice_briefing(**args)
                if vb.get("error"):
                    console.print(f"[bold red]  ❌  {vb['error']}[/bold red]")
                else:
                    console.print(f"  [bold green]🎙  Voice briefing generated![/bold green]")
                    console.print(f"  File: [cyan]{vb['audio_file']}[/cyan]")
                    console.print(f"  Duration: {vb['duration_est']}  │  Voice: {vb['voice']}")
                    console.print(f"  [dim]Play with: open \"{vb['audio_file']}\"[/dim]")
                    console.print()
            except Exception as _e:
                console.print(f"[bold red]  ❌  Voice briefing error: {_e}[/bold red]")
            _separator()
            continue  # self-contained — no LLM follow-up needed

        # ── /concall <symbol> — concall NLP (direct render) ───────────
        elif text.lower().startswith("/concall"):
            parts = text.split()
            sym   = parts[1].upper() if len(parts) > 1 else ""
            if not sym:
                console.print("[bold red]  Usage: /concall SYMBOL[/bold red]")
            else:
                console.print(f"[dim]  → Concall NLP: {sym}[/dim]")
                try:
                    from terminal.tools import analyze_concall_sentiment
                    cc = analyze_concall_sentiment(sym)
                    if cc.get("error"):
                        console.print(f"[bold red]  ❌  {cc['error']}[/bold red]")
                        text = f"Concall NLP for {sym} failed: {cc['error']}"
                    else:
                        sent  = cc.get("sentiment", "Neutral")
                        score = cc.get("tone_score", 0.0)
                        s_c   = "green" if sent == "Bullish" else ("red" if sent == "Bearish" else "yellow")
                        console.print()
                        console.print(f"  [bold]{sym}[/bold] Concall Sentiment: "
                                      f"[bold {s_c}]{sent}[/bold {s_c}]  "
                                      f"[dim]tone score {score:+.2f}[/dim]")
                        if cc.get("guidance"):
                            console.print(f"  [bold]Guidance:[/bold] {cc['guidance']}")
                        if cc.get("themes"):
                            console.print(f"  [bold]Key themes:[/bold]")
                            for th in cc["themes"]:
                                console.print(f"    • {th}")
                        if cc.get("risk_flags"):
                            console.print(f"  [bold red]Risk flags:[/bold red]")
                            for rf in cc["risk_flags"]:
                                console.print(f"    ⚠ {rf}")
                        if cc.get("key_quotes"):
                            console.print(f"  [bold]Key quotes:[/bold]")
                            for q in cc["key_quotes"][:3]:
                                console.print(f"    [italic]\"{q}\"[/italic]")
                        console.print(f"  [dim]Source: {cc.get('transcript_source','N/A')}[/dim]")
                        console.print()
                        text = (
                            f"{sym} concall: {sent} sentiment (tone {score:+.2f}). "
                            f"Themes: {cc.get('themes',[])}. Risks: {cc.get('risk_flags',[])}. "
                            f"Guidance: {cc.get('guidance','')}. "
                            f"Given this tone, what is the trading implication for {sym}?"
                        )
                except Exception as _e:
                    console.print(f"[bold red]  ❌  Concall NLP error: {_e}[/bold red]")
                    text = f"Concall NLP error for {sym}: {_e}"

        # ── /chain <symbol> [expiry] — live option chain ───────────────
        if text.lower().startswith("/chain"):
            parts = text.split()
            sym   = parts[1].upper() if len(parts) > 1 else "NIFTY"
            expiry_part = parts[2] if len(parts) > 2 else ""
            expiry_str  = f" for expiry {expiry_part}" if expiry_part else " for the nearest expiry"
            text = (
                f"Fetch the live option chain for {sym}{expiry_str}. "
                f"Show PCR, max pain, top CE OI (resistance) and PE OI (support) strikes, "
                f"ATM greeks, and OI buildup/unwinding summary."
            )
            console.print(f"[dim]  → Option chain: {sym}[/dim]")

        # ── /oi <symbol> — open interest analysis ─────────────────────
        elif text.lower().startswith("/oi"):
            parts = text.split()
            sym   = parts[1].upper() if len(parts) > 1 else "NIFTY"
            text  = (
                f"Run open interest analysis for {sym}. "
                f"Show PCR, max pain, key CE/PE OI support and resistance levels, "
                f"and where OI is building or unwinding today."
            )
            console.print(f"[dim]  → OI analysis: {sym}[/dim]")

        # ── /fno [symbol] — F&O overview ──────────────────────────────
        elif text.lower().startswith("/fno"):
            parts = text.split()
            sym   = parts[1].upper() if len(parts) > 1 else "NIFTY"
            text  = (
                f"Give a comprehensive F&O overview for {sym}: "
                f"option chain (PCR, max pain, top OI strikes), "
                f"futures basis and cost of carry, and recommend the best options strategy "
                f"based on current conditions."
            )
            console.print(f"[dim]  → F&O overview: {sym}[/dim]")

        # ── /strategy <symbol> <strategy_name> — build options strategy
        elif text.lower().startswith("/strategy"):
            parts = text.split()
            sym   = parts[1].upper() if len(parts) > 1 else "NIFTY"
            strat = parts[2].lower().replace("-", "_") if len(parts) > 2 else "long_straddle"
            text  = (
                f"Build a {strat.replace('_', ' ')} options strategy for {sym}. "
                f"Show legs, strikes, entry cost, max risk, max reward, and breakevens."
            )
            console.print(f"[dim]  → Strategy: {strat} on {sym}[/dim]")

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
                # If the follow-up starts with a `command` — description, extract
                # the slash command and route it directly (e.g. `/forensic RELIANCE`)
                m_cmd = re.match(r"`(/\S+[^`]*)`\s*[-–—]\s*(.+)", text)
                if m_cmd:
                    slash_cmd = m_cmd.group(1).strip()
                    description = m_cmd.group(2).strip()
                    console.print(f"[dim]  → {slash_cmd}  —  {description}[/dim]")
                    text = slash_cmd  # route as slash command
                else:
                    # Strip backtick natural-language prompt if present
                    m_nl = re.match(r"`([^`]+)`\s*[-–—]\s*(.+)", text)
                    if m_nl:
                        text = m_nl.group(1).strip() + " — " + m_nl.group(2).strip()
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
