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
  /model         → show/switch main chat model backend (OpenAI/Ollama/keyword)
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
import shutil
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import colorama
import pandas as pd
from colorama import Fore, Style

from rich.console import Console, Group
from rich.live import Live
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
from prompt_toolkit.patch_stdout import patch_stdout as _pt_patch_stdout
from terminal.renderer import (
    render_trace_tables, set_console as _renderer_set_console,
    pre_render_plan, apply_render_plan, get_bold_symbols,
)
from terminal.market_calendar import format_session_clock, market_session_status

colorama.init(autoreset=True)

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass

# ── Rich console — force_terminal so ANSI codes always work ──────────────────
console = Console(highlight=False, force_terminal=True)
_renderer_set_console(console)  # share the same console with the renderer module

# ── Direct console — writes to sys.__stdout__ bypassing prompt_toolkit's
#    patched sys.stdout. Use for monitor/alert output rendered during the
#    chat loop to prevent Rich+prompt_toolkit cursor conflict.
def _mcon() -> Console:
    """Return a Console writing directly to sys.__stdout__."""
    return Console(highlight=False, force_terminal=True,
                   file=sys.__stdout__ or sys.stdout)


# ── LLM alert parser ──────────────────────────────────────────────────────────

def _parse_alert_with_llm(raw: str) -> dict | None:
    """Use OpenAI to parse a natural-language alert description into structured fields.

    Returns dict with keys: symbol, trigger, value, tf, note.
    Returns None on API error or missing key — caller falls back to positional parse.

    Examples:
      "NIFTY rsi above 70 in 15min"
        → {symbol: NIFTY, trigger: rsi_above, value: 70.0, tf: 15m, note: ""}
      "RELIANCE breakout"
        → {symbol: RELIANCE, trigger: intraday_breakout, value: 0.0, tf: 1d, note: ""}
      "TCS price above 3500 near earnings"
        → {symbol: TCS, trigger: price_above, value: 3500.0, tf: 1d, note: "near earnings"}
    """
    import json as _json
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        return None
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        system = (
            "You parse stock alert commands into structured JSON. "
            "Extract these fields:\n"
            "  symbol   — uppercase NSE ticker or index (NIFTY, BANKNIFTY, RELIANCE, TCS…)\n"
            "  trigger  — one of: price_above, price_below, rsi_above, rsi_below, "
            "breakout_above, breakout_below, intraday_breakout\n"
            "  value    — float threshold (0.0 for intraday_breakout when not given)\n"
            "  tf       — timeframe string: '1d' for daily/default, '15m', '5m', '1h', "
            "'30m' etc. for intraday (parse from phrases like 'in 15 min', '15-minute', '5m timeframe')\n"
            "  note     — remaining free-text after extraction (empty string if none)\n"
            "Aliases: 'breakout'/'orb' → intraday_breakout; 'above' alone → breakout_above; "
            "'below' alone → breakout_below; 'rsi above' → rsi_above; 'rsi below' → rsi_below.\n"
            "Respond with ONLY valid JSON: "
            '{"symbol":"","trigger":"","value":0.0,"tf":"1d","note":""}'
        )
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": raw},
            ],
            max_tokens=120,
            temperature=0,
        )
        parsed = _json.loads(resp.choices[0].message.content)
        # Basic sanity — must have symbol and trigger
        if parsed.get("symbol") and parsed.get("trigger"):
            return parsed
        return None
    except Exception:
        return None

# ── Global chat state ─────────────────────────────────────────────────────────
_mode             = "auto"   # "auto" | "intraday" | "historical"
_followups: list[str] = []   # current follow-up suggestions (up to 3)
_market_toolbar_cache: dict = {"ts": 0.0, "data": None}

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
    ("/ric company-xray",       "9-step company intelligence workflow [SYMBOL]"),
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
    ("/dashboard",        "Auto-refreshing current-market dashboard + narrative"),
    ("/dash",             "Alias: current-market dashboard + narrative"),
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
    # ── Watchlist alert commands ───────────────────────────────────────────
    ("/alert list",       "List all price/RSI alerts (shows timeframe column)"),
    ("/alert add ",       "Add alert (natural language): /alert add NIFTY rsi above 70 in 15min  |  /alert add RELIANCE breakout"),
    ("/alert del ",       "Delete an alert by ID: /alert del 1"),
    ("/alert check",      "Check all alerts against live prices/RSI now"),
    ("/alert monitor",    "Toggle background alert monitor (polls every 5 min, market hours)"),
    # ── F&O / Options commands ─────────────────────────────────────────────
    ("/options",          "Live options chain — Rich table (Calls|Strike|Puts) with PCR, max pain, IV"),
    ("/options NIFTY",    "NIFTY options chain — nearest expiry"),
    ("/options BANKNIFTY","BANKNIFTY options chain — nearest expiry"),
    ("/options NIFTY 1",  "NIFTY options chain — next expiry"),
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
    # ── Market education commands ───────────────────────────────────────────
    ("/learn PE ratio",                   "Source-backed concept explainer from Investopedia + Wikipedia"),
    ("/define ROCE",                      "Define a market or accounting concept with source URLs"),
    ("/compare ROCE ROE",                 "Compare market concepts using Investopedia + Wikipedia evidence"),
    ("/learn Minervini trading strategy", "Explain a trading framework with source-backed context"),
    # ── Company intelligence index commands ────────────────────────────────
    ("/company-index",                    "Index company website + official investor documents"),
    ("/company-index DMART",              "Index DMart investor site using crawler + adapter auto-detect"),
    ("/company-index DMART --include-documents", "Download discovered official investor documents"),
    ("/company-index DMART --max-pages 10 --document-limit 5", "Bounded company website/document index run"),
    ("/company-xray",                    "Company + Sector X-Ray report from indexed evidence"),
    ("/company-xray DMART",              "Run Company X-Ray for DMart"),
    ("/company-xray DMART --strict",     "Run Company X-Ray with strict evidence coverage"),
    # ── Analyze / document commands ─────────────────────────────────────────
    ("/analyze",                          "Analyze a PDF, DOCX, web page, or stock — auto-detects input type"),
    ("/analyze report.pdf",               "Read and summarize a local PDF document"),
    ("/analyze https://example.com",      "Scrape and analyze a web page"),
    ("/analyze annual_report.docx",       "Extract and summarize a Word document"),
    ("/analyze RELIANCE",                 "Deep 360° stock analysis — technical, fundamental, forensic, news, sentiment"),
    ("/analyze ~/Downloads/concall.pdf",  "Read and analyze a concall transcript PDF"),
    # ── CANSLIM commands ────────────────────────────────────────────────────
    ("/canslim",                          "CANSLIM analysis — William O'Neil's 7-point stock quality framework"),
    ("/canslim RELIANCE",                 "Full CANSLIM evaluation for RELIANCE"),
    ("/canslim TCS",                      "CANSLIM growth + institutional quality check for TCS"),
    ("/strength MANINDS THERMAX",         "Validate CANSLIM + RS + fundamentals + Piotroski without assumptions"),
    # ── Forensic commands ───────────────────────────────────────────────────
    ("/forensic",                         "D5 Forensic analysis — Beneish M-score, Piotroski F-score, Altman Z'-score"),
    ("/forensic RELIANCE",                "Forensic accounting analysis for RELIANCE"),
    ("/forensic TCS INFY WIPRO",          "Forensic screening across multiple stocks"),
    # ── Intraday market recap ──────────────────────────────────────────────
    # PG-recap-slash: bare `/recap` had no handler → was falling through to the
    # symbol planner and getting resolved to a random ticker (e.g. AVONMORE).
    ("/recap",                            "Last 15-minute intraday market recap (PG intraday.quote_snapshots)"),
    ("/recap 30",                         "Custom-window recap, e.g. last 30 minutes"),
    # ── Voice briefing (P3-2) ───────────────────────────────────────────────
    ("/voice-mode on",                    "Speak every normal Agent Adda answer until disabled"),
    ("/voice-mode off",                   "Disable automatic spoken responses"),
    ("/voice-mode status",                "Show whether automatic spoken responses are enabled"),
    ("/voice",                            "P3-2 60-second daily audio briefing — regime, flows, top picks (MP3/AIFF)"),
    ("/voice script",                     "Print the voice briefing script (no audio synthesis)"),
    ("/voice 2026-05-09",                 "Generate briefing for a specific historical signal date"),
    ("/voice-live",                       "Live voice assistant loop: listen, transcribe, answer, speak, repeat"),
    ("/voice-live --turns 3 --seconds 8", "Run a bounded live voice assistant session"),
    ("/ask-voice",                        "Record a spoken question, transcribe it, run Agent Adda, speak the response"),
    ("/ask-voice --audio-file question.wav", "Use an existing audio file as the spoken question"),
    ("/ask-voice --no-play",              "Generate response audio but do not auto-play it"),
    # ── Event calendar commands ─────────────────────────────────────────────
    ("/events",                           "E4 Upcoming corporate events — dividends, splits, results, AGMs"),
    ("/events NIFTY 50",                  "Event calendar for NIFTY 50 stocks (next 14 days)"),
    ("/events RELIANCE",                  "Upcoming events for a specific stock"),
    # ── Seasonal / macro / new commands ─────────────────────────────────────
    ("/us",                               "US/global market summary + report"),
    ("/us indices",                       "US index tape: SPY, QQQ, Nasdaq, Dow, Russell, VIX"),
    ("/us sectors",                       "US sector ETF rotation"),
    ("/us stage2",                        "US Stage 2 leaders"),
    ("/us vcp",                           "US VCP setups"),
    ("/us stock NVDA",                    "US stock technical context with report link"),
    ("/global readthrough",               "US/global signals mapped to NSE sector implications"),
    ("/heat",                             "B3 Sector seasonal heatmap — current-month TAILWIND/HEADWIND"),
    ("/heat 5",                           "Sector heat calendar for May"),
    ("/cycle",                            "B5 Economic cycle phase + preferred/avoid sectors"),
    ("/scenario RELIANCE",                "P2-2 What-if price scenarios for RELIANCE"),
    ("/narrative",                        "P2-4 Portfolio narratives — bull/bear thesis per stock"),
    ("/narrative TCS INFY",               "Investment narratives for specific stocks"),
    ("/concall TCS",                      "D4 Concall NLP — sentiment, themes, risk flags"),
    # ── Report generation commands ─────────────────────────────────────────
    ("/report",                           "Generate a formatted report — PDF, HTML, or Markdown"),
    ("/report sector-rotation",           "⚡ Instant sector rotation dashboard from DB (no LLM)"),
    ("/report sector-rotation pdf",       "⚡ Sector rotation report as PDF"),
    ("/report stage2",                    "⚡ Stage 2 universe tracker — top 30 leaders + new entrants (instant)"),
    ("/report stage2 md",                 "⚡ Stage 2 tracker as Markdown"),
    ("/report technical RELIANCE",        "Technical analysis report for RELIANCE"),
    ("/report fundamental TCS pdf",       "Fundamental report for TCS in PDF format"),
    ("/report forensic INFY md",          "Forensic accounting report in Markdown"),
    ("/report research HDFCBANK",         "Comprehensive 360° research report"),
    ("/report intraday SBIN",             "Intraday analysis report"),
    ("/report canslim TATAMOTORS",        "CANSLIM quality report"),
    ("/report ric ADANIENT pdf",          "RIC investigation report in PDF"),
    ("/report sector IT",                 "Sector analysis report for IT sector"),
    ("/report RELIANCE",                  "Quick research report (default type: research, format: html)"),
    ("/backtest list",    "List EOD Strategy Lab strategies"),
    ("/strategy-lab validate", "Validate EOD backtesting data readiness"),
    ("/pnl",              "💼 Live portfolio P&L — unrealised gains/losses from holdings.csv"),
    ("/live",             "Switch to LIVE mode (real-time NSE API)"),
    ("/eod",              "Switch to EOD mode (historical CSV/DB)"),
    ("/auto",             "Switch to AUTO mode (keyword detect)"),
    ("/model",            "Show active main chat model/backend"),
    ("/model gpt-4o",     "Switch main chat backend to OpenAI gpt-4o"),
    ("/model ollama",     "Switch main chat backend to Ollama default model"),
    ("/model ollama granite4:latest", "Switch main chat backend to a specific Ollama model"),
    ("/model keyword",    "Disable LLM backend and use deterministic keyword/tool routing"),
    ("/global",           "Global market assessment + India read-through"),
    ("/context",          "Show conversation history & context budget"),
    ("/new",              "Start a fresh session (clear history)"),
    ("/reset",            "Start a fresh session (clear history)"),
    ("/clear",            "Clear the screen"),
    ("/export",           "Export session to HTML report"),
    ("/export html",      "Export session to HTML file (opens in browser)"),
    ("/export pdf",       "Export session to PDF (requires weasyprint or pdfkit)"),
    ("/help",             "Show all commands (table of contents)"),
    ("/help charts",      "Help: charts section"),
    ("/help screens",     "Help: EOD screeners"),
    ("/help scan",        "Help: intraday scanner"),
    ("/help fno",         "Help: F&O / options"),
    ("/help search",      "Help: deep search engine"),
    ("/help forensic",    "Help: forensic accounting"),
    ("/help monitors",    "Help: background monitors & alerts"),
    ("/help ric",         "Help: recursive investigations"),
    ("/help refresh",     "Help: data refresh"),
    ("/help appearance",  "Help: themes & scale"),
    ("/help macro",       "Help: seasonal & macro"),
    # ── Theme / scale commands ─────────────────────────────────────────────
    ("/theme ",           "Show available color themes"),
    ("/theme dark",       "Switch to Dark theme (default)"),
    ("/theme dracula",    "Switch to Dracula theme"),
    ("/theme solarized",  "Switch to Solarized Dark theme"),
    ("/theme high-contrast", "Switch to High Contrast theme"),
    ("/theme nord",       "Switch to Nord theme"),
    ("/scale ",           "Show layout scale options"),
    ("/scale compact",    "Compact layout — fits small terminals"),
    ("/scale normal",     "Normal layout — default balanced layout"),
    ("/scale large",      "Large layout — wide terminals / big screens"),
    ("/refresh",          "Run data refresh pipeline (snapshot mode)"),
    ("/refresh snapshot", "Fast snapshot: skip analysis, just update stage DB"),
    ("/refresh live",     "Live prices only — fastest (~30s)"),
    ("/refresh full",     "Full pipeline: R bhavcopy + analysis + snapshot"),
    ("/refresh analysis", "Analysis + snapshot (skips aux data fetch)"),
    ("/refresh status",   "Check if refresh is running"),
    ("/refresh stop",     "Stop a running refresh"),
    # ── Command discovery ──────────────────────────────────────────────────
    ("/commands",         "Browse all slash commands by category"),
    ("/commands alert",   "Filter commands by keyword, e.g. /commands pdf"),
]

# ─────────────────────────────────────────────────────────────────────────────
# /commands — searchable command browser
# ─────────────────────────────────────────────────────────────────────────────

# Maps the first token of a slash command to a category label and icon
_CMD_CATEGORIES: dict[str, tuple[str, str]] = {
    "/prompts":  ("Research Prompts",    "📋"),
    "/ric":      ("RIC Investigations",  "🔬"),
    "/scan":     ("Intraday Scanner",    "⚡"),
    "/dashboard":("Market Dashboard",     "📊"),
    "/dash":     ("Market Dashboard",     "📊"),
    "/screen":   ("EOD Screeners",       "🔍"),
    "/monitor":  ("Background Monitors", "👁️"),
    "/alert":    ("Watchlist Alerts",    "🔔"),
    "/options":  ("F&O / Options",       "📊"),
    "/chain":    ("F&O / Options",       "📊"),
    "/oi":       ("F&O / Options",       "📊"),
    "/fno":      ("F&O / Options",       "📊"),
    "/strategy": ("F&O / Options",       "📊"),
    "/chart":    ("Charts",              "📈"),
    "/search":   ("Deep Search",         "🌐"),
    "/learn":    ("Market Knowledge",    "📚"),
    "/define":   ("Market Knowledge",    "📚"),
    "/compare":  ("Market Knowledge",    "📚"),
    "/company-index": ("Company Intelligence", "🏢"),
    "/company-xray": ("Company Intelligence", "🏢"),
    "/analyze":  ("Document Analysis",   "📄"),
    "/canslim":  ("CANSLIM Analysis",    "📐"),
    "/strength": ("CANSLIM Analysis",    "📐"),
    "/report":   ("Report Generation",   "📝"),
    "/backtest": ("Strategy Lab",         "🧪"),
    "/strategy-lab": ("Strategy Lab",     "🧪"),
    "/forensic": ("Forensic",            "🧪"),
    "/voice-mode": ("Voice Briefing",    "🎙️"),
    "/events":   ("Events Calendar",     "📅"),
    "/us":       ("Macro & Global",      "🌍"),
    "/global":   ("Macro & Global",      "🌍"),
    "/heat":     ("Macro & Global",      "🌍"),
    "/cycle":    ("Macro & Global",      "🌍"),
    "/scenario": ("Analysis Tools",      "🎯"),
    "/narrative":("Analysis Tools",      "🎯"),
    "/concall":  ("Analysis Tools",      "🎯"),
    "/pnl":      ("Portfolio",           "💼"),
    "/export":   ("Session",             "💾"),
    "/live":     ("Session",             "💾"),
    "/eod":      ("Session",             "💾"),
    "/auto":     ("Session",             "💾"),
    "/model":    ("Settings & Data",     "⚙️"),
    "/context":  ("Session",             "💾"),
    "/new":      ("Session",             "💾"),
    "/reset":    ("Session",             "💾"),
    "/clear":    ("Session",             "💾"),
    "/help":     ("Help",                "❓"),
    "/theme":    ("Settings & Data",     "⚙️"),
    "/scale":    ("Settings & Data",     "⚙️"),
    "/refresh":  ("Settings & Data",     "⚙️"),
    "/commands": ("Help",                "❓"),
}


def _print_commands(filter_kw: str = "") -> None:
    """Print a compact, searchable command browser.

    No filter  → one row per top-level command (no sub-variants), grouped by category.
    filter_kw  → show all entries whose command or description contains the keyword.
    """
    from rich.table import Table as _Table

    kw = filter_kw.strip().lower()

    if kw:
        # ── Filtered view: all matching entries ────────────────────────────
        matches = [
            (cmd, desc) for cmd, desc in _SLASH_COMMANDS
            if kw in cmd.lower() or kw in desc.lower()
        ]
        if not matches:
            console.print(f"[dim]  No commands matching '[bold]{kw}[/bold]'[/dim]")
            return

        tbl = _Table(
            title=f"Commands matching '{kw}'",
            show_header=True,
            header_style="bold cyan",
            box=box.SIMPLE_HEAD,
            pad_edge=False,
        )
        tbl.add_column("Command",     style="bold green",  no_wrap=True)
        tbl.add_column("Description", style="dim")
        for cmd, desc in matches:
            tbl.add_row(cmd.rstrip(), desc)
        console.print(tbl)
        console.print(f"[dim]  {len(matches)} match(es) · /commands <keyword> to filter further[/dim]\n")

    else:
        # ── Category view: one representative per root command ─────────────
        # Collect one entry per unique root token (first word of command)
        seen_roots: set[str] = set()
        # Group: {category_label → [(cmd, desc), ...]}
        groups: dict[str, list[tuple[str, str]]] = {}

        for cmd, desc in _SLASH_COMMANDS:
            root = cmd.split()[0].rstrip()      # e.g. "/chart"
            if root in seen_roots:
                continue
            seen_roots.add(root)
            cat_label, _ = _CMD_CATEGORIES.get(root, ("Other", "•"))
            groups.setdefault(cat_label, []).append((root, desc))

        # Ordered category list preserving first-seen order
        cat_order: list[str] = []
        for cmd, _ in _SLASH_COMMANDS:
            root = cmd.split()[0].rstrip()
            cat_label, _ = _CMD_CATEGORIES.get(root, ("Other", "•"))
            if cat_label not in cat_order:
                cat_order.append(cat_label)

        console.print()
        console.rule("[bold cyan]  Slash Commands[/bold cyan]  [dim](/commands <keyword> to filter)[/dim]")
        console.print()

        for cat in cat_order:
            entries = groups.get(cat, [])
            if not entries:
                continue
            _, icon = _CMD_CATEGORIES.get(entries[0][0], ("Other", "•"))
            tbl = _Table(
                title=f"{icon}  {cat}",
                show_header=False,
                box=box.SIMPLE,
                pad_edge=False,
                show_edge=False,
                title_style="bold yellow",
                min_width=60,
            )
            tbl.add_column("Command",     style="bold green",  no_wrap=True, min_width=18)
            tbl.add_column("Description", style="dim")
            for cmd, desc in entries:
                tbl.add_row(cmd, desc)
            console.print(tbl)

        total = len(seen_roots)
        console.print(f"[dim]  {total} commands · type /commands <keyword> to filter · /help for full usage[/dim]\n")
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
    "company-xray": {
        "name":    "🏢 Company + Sector X-Ray",
        "desc":    "9-step company-first intelligence workflow: identity → indexed evidence → business model → sector → competitors → policy impact → deliberation → report",
        "arg":     "symbol",
        "example": "/ric company-xray DMART",
        "steps": [
            {"label": "Resolve Identity", "prompt": "Resolve {symbol} to its company identity, aliases, sector, industry, and official website. Keep the answer evidence-first."},
            {"label": "Build Evidence", "prompt": "/company-index {symbol} --include-documents --document-limit 5 --max-pages 10 --seed-sitemap --respect-robots"},
            {"label": "Business Model", "prompt": "Using indexed official evidence for {symbol}, explain business model, revenue drivers, customer base, and operating model. Flag evidence gaps explicitly."},
            {"label": "Sector Expansion", "prompt": "Build sector context for {symbol}: sector structure, demand drivers, value chain, and where the company sits."},
            {"label": "Competitive Map", "prompt": "Map competitors and peers for {symbol}; compare competitive advantage, risks, and market-share evidence."},
            {"label": "Financial and Market Behavior", "prompt": "Connect {symbol}'s fundamentals, technical behavior, ownership, and recent filings into a concise evidence-backed view."},
            {"label": "RBI/Budget Impact", "prompt": "Assess RBI monetary policy and Union Budget sensitivity for {symbol}, separating direct evidence from inference."},
            {"label": "Deliberation", "prompt": "Build bull, bear, and base cases for {symbol}; include disconfirming evidence and open research questions."},
            {"label": "Final Report", "prompt": "/company-xray {symbol} --refresh"},
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


def _auto_export_report(content: str, report_type: str, symbol: str, fmt: str) -> None:
    """Save agent response content as a styled report file and open it."""
    try:
        from terminal.reports import generate_report
        res = generate_report(content, report_type=report_type, symbol=symbol, output_format=fmt)
        fpath  = res.get("path", "")
        actual = res.get("format", fmt).upper()
        note   = res.get("note", "")
        console.print(f"\n  [bold green]📄 Report saved ({actual}):[/bold green] [cyan]{fpath}[/cyan]")
        if note:
            console.print(f"  [dim]{note}[/dim]")
        try:
            import subprocess as _sp
            _sp.run(["open", fpath], check=False)
        except Exception:
            pass
    except Exception as _e:
        console.print(f"  [bold red]  ❌ Report export error: {_e}[/bold red]")


def _run_ric(agent, key: str, arg: str, show_trace: bool, output_format: str = "") -> None:
    """Execute a named RIC step by step, each result feeding context.

    output_format: if 'html'/'pdf'/'md', combine all step answers and save as report.
    """
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

    symbol  = arg.strip().upper() if arg else ""
    n_steps = len(ric["steps"])
    collected_parts: list[str] = []  # accumulate step answers for report export

    console.print()
    console.rule(
        f"[bold yellow] 🔁  {ric['name']} [/bold yellow]"
        f"[dim]  {symbol or ''}  ·  {n_steps} steps [/dim]",
        style="yellow",
    )
    console.print(f"[dim]  {ric['desc']}[/dim]")
    if output_format:
        console.print(f"[dim]  → Will save {output_format.upper()} report after all steps complete[/dim]")
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
            # Collect clean answer for report
            answer, _ = _parse_followups(result.get("answer", ""))
            collected_parts.append(f"## Step {i}: {label}\n\n{answer}")
        except Exception as e:
            console.print(f"[red]  ✗  Step {i} failed: {e}[/red]")
            console.print()

    console.rule(
        f"[bold yellow] ✅  {ric['name']} complete [/bold yellow]"
        f"[dim]  {symbol or ''}  ·  all {n_steps} steps done [/dim]",
        style="yellow",
    )
    console.print()

    # Auto-export report if format was requested
    if output_format and collected_parts:
        ric_name = ric["name"].replace("🔍", "").replace("🏭", "").replace("🎯", "")\
                              .replace("📋", "").replace("📊", "").replace("⚔️", "")\
                              .replace("⚠️", "").replace("☀️", "").strip()
        heading = f"# {ric_name} — {symbol or 'Market'}\n\n*{ric['desc']}*\n\n---\n\n"
        combined = heading + "\n\n---\n\n".join(collected_parts)
        _auto_export_report(combined, report_type="ric", symbol=symbol, fmt=output_format)


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
    _print_market_toolbar()
    W = Fore.WHITE + Style.BRIGHT
    print(W + "  ╔" + "═" * _BOX_W + "╗")
    print(_box_row("NSE Market Research Terminal  ·  AI-powered · Real-time",
                   Fore.YELLOW + Style.BRIGHT))
    print(_box_row(f"As of {_session_clock_label()}",
                   Fore.WHITE + Style.BRIGHT))
    print(_box_row(market_session_status().compact_label,
                   Fore.GREEN + Style.BRIGHT))
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
          "  /live  /eod  /auto  │  /model  │  /global  │  /heat  /cycle  /scenario  /narrative  │  /prompts  │  /help  │  exit")
    print()
    _separator()
    print()


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

_IST = ZoneInfo("Asia/Kolkata")


def _session_now(now: datetime | None = None) -> datetime:
    """Return the current Agent Adda session time in IST."""
    if now is None:
        return datetime.now(_IST)
    if now.tzinfo is None:
        return now
    return now.astimezone(_IST)


def _session_clock_label(now: datetime | None = None) -> str:
    """Human-readable latest session clock used in all terminal headers."""
    return format_session_clock(_session_now(now))


def _bottom_toolbar_text(now_factory=None) -> str:
    """Live prompt toolbar text; prompt_toolkit refreshes this while waiting."""
    factory = now_factory or _session_now
    now = factory()
    data = _get_cached_market_toolbar_data()
    if data:
        return _bottom_toolbar_ticker(data, now)
    return (
        f"  {_session_clock_label(now)}  |  {market_session_status(now).compact_label}"
        f"  |  mode: {_mode.upper()}  |  Agent Adda"
    )


def _fmt_index_price(value) -> str:
    try:
        if value is None or pd.isna(value):
            return "—"
        return f"{float(value):,.2f}"
    except (TypeError, ValueError):
        return "—"


def _fmt_index_pct(value) -> str:
    try:
        if value is None or pd.isna(value):
            return "—"
        fv = float(value)
        sign = "+" if fv > 0 else ""
        return f"{sign}{fv:.2f}%"
    except (TypeError, ValueError):
        return "—"


def _bottom_toolbar_index_label(name: str) -> str:
    upper = (name or "").upper()
    if "BANK" in upper:
        return "BANK"
    if "MID" in upper:
        return "MIDCP"
    if "NIFTY 50" in upper:
        return "NIFTY 50"
    return upper[:10] or "INDEX"


def _bottom_toolbar_short_index_label(name: str) -> str:
    upper = (name or "").upper()
    if "BANK" in upper:
        return "BNK"
    if "MID" in upper:
        return "MID"
    if "NIFTY 50" in upper:
        return "N50"
    return (upper[:3] or "IDX")


def _fmt_index_price_compact(value) -> str:
    try:
        if value is None or pd.isna(value):
            return "—"
        return f"{float(value):,.0f}"
    except (TypeError, ValueError):
        return "—"


def _compact_market_status(now: datetime) -> str:
    label = market_session_status(now).compact_label
    if "OPEN" in label:
        return "OPEN"
    if "CLOSED" in label:
        return "CLOSED"
    return label.replace("NSE: ", "")


def _get_cached_market_toolbar_data(max_age_seconds: int = 180) -> dict | None:
    """Return cached live toolbar data without performing network I/O."""
    data = _market_toolbar_cache.get("data")
    ts = float(_market_toolbar_cache.get("ts") or 0)
    if not data or ts <= 0:
        return None
    if time.time() - ts > max_age_seconds:
        return None
    return data


def _bottom_toolbar_ticker(data: dict, now: datetime) -> str:
    width = max(40, shutil.get_terminal_size((120, 24)).columns)
    indices = data.get("indices") or []
    clock_short = _session_now(now).strftime("%H:%M")
    clock_full = _session_now(now).strftime("%H:%M:%S IST")
    status_short = _compact_market_status(now)

    short_parts = []
    for item in indices[:2]:
        short_parts.append(
            f"{_bottom_toolbar_short_index_label(item.get('name', ''))} "
            f"{_fmt_index_price_compact(item.get('last'))} {_fmt_index_pct(item.get('pct_change'))}"
        )
    short_parts.extend([status_short, clock_short, _mode.upper()])
    short_ticker = "  " + " | ".join(short_parts)
    if width < 110:
        return short_ticker[:width]

    medium_parts = []
    for item in indices[:3]:
        medium_parts.append(
            f"{_bottom_toolbar_short_index_label(item.get('name', ''))} "
            f"{_fmt_index_price_compact(item.get('last'))} {_fmt_index_pct(item.get('pct_change'))}"
        )
    adv_dec = data.get("adv_dec") or {}
    adv = adv_dec.get("advances")
    dec = adv_dec.get("declines")
    if adv is not None and dec is not None:
        medium_parts.append(f"{adv}A/{dec}D")
    medium_parts.extend([status_short, clock_short, _mode.upper()])
    medium_ticker = "  " + " | ".join(medium_parts)
    if width < 150:
        return medium_ticker if len(medium_ticker) <= width else short_ticker[:width]

    parts = []
    for item in indices[:3]:
        label = _bottom_toolbar_index_label(item.get("name", ""))
        parts.append(
            f"{label} {_fmt_index_price(item.get('last'))} {_fmt_index_pct(item.get('pct_change'))}"
        )
    if adv is not None and dec is not None:
        parts.append(f"Breadth {adv}A/{dec}D")
    parts.append(market_session_status(now).compact_label)
    parts.append(clock_full)
    parts.append(_mode.upper())
    full_ticker = "  " + "  |  ".join(parts)
    return full_ticker if len(full_ticker) <= width else medium_ticker[:width]


def _index_pct_style(value) -> str:
    try:
        fv = float(value or 0)
    except (TypeError, ValueError):
        fv = 0
    return "bold green" if fv > 0 else ("bold red" if fv < 0 else "bold yellow")


def _normalise_toolbar_index(name: str, row: dict | None) -> dict:
    row = row or {}
    return {
        "name": name,
        "last": row.get("last", row.get("close")),
        "pct_change": row.get("pct_change", row.get("chg_pct")),
        "day_high": row.get("day_high", row.get("high")),
        "day_low": row.get("day_low", row.get("low")),
    }


def _toolbar_narrative(indices: list[dict], adv_dec: dict | None = None, source: str = "") -> str:
    pct_values = [float(i.get("pct_change") or 0) for i in indices if i.get("pct_change") is not None]
    avg_pct = sum(pct_values) / len(pct_values) if pct_values else 0
    bullish = sum(1 for v in pct_values if v > 0.05)
    bearish = sum(1 for v in pct_values if v < -0.05)
    bank_pct = next((float(i.get("pct_change") or 0) for i in indices if "BANK" in i["name"]), 0)
    mid_pct = next((float(i.get("pct_change") or 0) for i in indices if "MID" in i["name"]), 0)

    if bullish >= 2 and avg_pct > 0.15:
        tone = "risk-on"
    elif bearish >= 2 and avg_pct < -0.15:
        tone = "risk-off"
    else:
        tone = "mixed/range-bound"

    breadth = ""
    if adv_dec:
        adv = int(adv_dec.get("advances") or 0)
        dec = int(adv_dec.get("declines") or 0)
        if adv or dec:
            breadth_tone = "positive" if adv > dec else ("negative" if dec > adv else "flat")
            breadth = f" Breadth {breadth_tone} ({adv}A/{dec}D)."

    leadership = "Banks leading" if bank_pct > max(0.05, mid_pct) else (
        "Midcaps leading" if mid_pct > max(0.05, bank_pct) else "No clear leadership"
    )
    return f"Intraday narrative: {tone}; {leadership}.{breadth} Source: {source or 'market tape'}."


def _dashboard_fmt_pct(value) -> str:
    try:
        fv = float(value)
    except (TypeError, ValueError):
        return "n/a"
    return f"{fv:+.2f}%"


def _dashboard_fmt_num(value, decimals: int = 2) -> str:
    try:
        fv = float(value)
    except (TypeError, ValueError):
        return "n/a"
    return f"{fv:,.{decimals}f}"


def _dashboard_pct_style(value) -> str:
    try:
        fv = float(value)
    except (TypeError, ValueError):
        return "white"
    return "bold green" if fv > 0 else ("bold red" if fv < 0 else "bold yellow")


def _fetch_market_dashboard_snapshot(focus: str = "") -> dict:
    """Fetch one live dashboard snapshot from existing tools."""
    from terminal.tools import call_tool

    plan = [
        ("get_live_market_overview", {}),
        ("get_market_breadth", {}),
        ("get_top_gainers_losers", {"index": "NIFTY 500", "top_n": 5, "direction": "both"}),
        ("get_fii_dii_activity", {}),
        ("get_global_market_assessment", {}),
        ("search_latest_catalysts", {"symbol": "NIFTY India market today"}),
    ]
    out: dict[str, dict] = {"focus": focus, "fetched_at": datetime.now(_IST).strftime("%Y-%m-%d %H:%M:%S")}
    for name, args in plan:
        try:
            out[name] = call_tool(name, args)
        except Exception as exc:
            out[name] = {"error": str(exc)}
    return out


def _compact_dashboard_narrative(snapshot: dict) -> str:
    live = snapshot.get("get_live_market_overview") or {}
    glob = snapshot.get("get_global_market_assessment") or {}
    indices = live.get("indices") or {}
    n50 = indices.get("NIFTY 50") or {}
    adv_dec = live.get("adv_dec") or {}
    n50_pct = n50.get("pct_change", n50.get("chg_pct"))
    adv, dec = adv_dec.get("advances"), adv_dec.get("declines")
    breadth_bias = "mixed"
    if isinstance(adv, (int, float)) and isinstance(dec, (int, float)):
        breadth_bias = "positive" if adv > dec else ("negative" if dec > adv else "flat")
    tape_bias = "bullish" if isinstance(n50_pct, (int, float)) and n50_pct > 0.25 else (
        "bearish" if isinstance(n50_pct, (int, float)) and n50_pct < -0.25 else "range-bound"
    )
    regime = glob.get("risk_regime", "mixed")
    if tape_bias == "bearish" and breadth_bias == "negative":
        stance = "defensive / risk-off"
    elif tape_bias == "bullish" and breadth_bias != "negative":
        stance = "constructive but selective"
    else:
        stance = "mixed and confirmation-led"
    return f"{stance}: NIFTY tape {tape_bias}, breadth {breadth_bias}, global regime {regime}. Confirm sector leadership and invalidation before acting."


def _market_dashboard_renderable(snapshot: dict, *, width: int | None = None, height: int | None = None):
    """Return a screen-fitting Rich renderable for the live market dashboard."""
    size = shutil.get_terminal_size((120, 34))
    width = width or size.columns
    height = height or size.lines
    compact = width < 110 or height < 32
    ultra_compact = width < 100 or height < 30
    row_limit = 3 if compact else 5

    live = snapshot.get("get_live_market_overview") or {}
    brd = snapshot.get("get_market_breadth") or {}
    movers = snapshot.get("get_top_gainers_losers") or {}
    fii = snapshot.get("get_fii_dii_activity") or {}
    glob = snapshot.get("get_global_market_assessment") or {}
    cat = snapshot.get("search_latest_catalysts") or {}

    indices = live.get("indices") or {}
    adv_dec = live.get("adv_dec") or {}
    focus = snapshot.get("focus") or "whole market"
    fetched_at = snapshot.get("fetched_at") or datetime.now(_IST).strftime("%Y-%m-%d %H:%M:%S")

    title = (
        f"📊 Market Dashboard  ·  {fetched_at}  ·  focus: {focus}  ·  "
        f"refresh: 60s  ·  Ctrl+C to exit"
    )

    tape = Table(box=box.SIMPLE_HEAD, expand=True, show_lines=False, padding=(0, 1))
    tape.add_column("Metric", style="bold cyan", no_wrap=True)
    tape.add_column("Last", justify="right")
    tape.add_column("Chg%", justify="right")
    for label, row in (
        ("NIFTY 50", indices.get("NIFTY 50") or {}),
        ("NIFTY BANK", indices.get("NIFTY BANK") or {}),
        ("MIDCAP", indices.get("NIFTY MIDCAP SELECT") or indices.get("NIFTY MIDCAP 50") or indices.get("NIFTY MIDCAP 100") or {}),
        ("SMALLCAP", indices.get("NIFTY SMALLCAP 100") or indices.get("NIFTY SMALLCAP 250") or {}),
        ("INDIA VIX", indices.get("INDIA VIX") or {}),
    ):
        pct = row.get("pct_change", row.get("chg_pct"))
        tape.add_row(label, _dashboard_fmt_num(row.get("last", row.get("close"))), f"[{_dashboard_pct_style(pct)}]{_dashboard_fmt_pct(pct)}[/]")
    if adv_dec:
        tape.add_row("Live Breadth", f"{adv_dec.get('advances', '—')}A", f"{adv_dec.get('declines', '—')}D")

    index_rows = []
    for name, row in indices.items():
        if name.upper() == "INDIA VIX":
            continue
        pct = row.get("pct_change", row.get("chg_pct"))
        if isinstance(pct, (int, float)):
            index_rows.append((name, pct))
    leaders = sorted(index_rows, key=lambda item: item[1], reverse=True)[:row_limit]
    laggards = sorted(index_rows, key=lambda item: item[1])[:row_limit]

    if ultra_compact:
        def _idx_line(label: str, row: dict) -> str:
            last = _dashboard_fmt_num(row.get("last", row.get("close")), 0)
            pct = _dashboard_fmt_pct(row.get("pct_change", row.get("chg_pct")))
            return f"{label} {last} {pct}"

        def _short(text: str, max_len: int) -> str:
            text = str(text)
            return text if len(text) <= max_len else text[: max(0, max_len - 1)] + "…"

        value_width = max(24, width - 28)
        n50 = indices.get("NIFTY 50") or {}
        bank = indices.get("NIFTY BANK") or {}
        vix = indices.get("INDIA VIX") or {}
        gainers = movers.get("gainers") or []
        losers = movers.get("losers") or []
        flows = []
        for row in (fii.get("data") or [])[:2]:
            net = row.get("net_crore")
            net_txt = f"{net:+,.0f}Cr" if isinstance(net, (int, float)) else "n/a"
            flows.append(f"{row.get('category', 'Flow')} {net_txt}")

        rows = Table(box=box.SIMPLE_HEAD, expand=True, padding=(0, 1))
        rows.add_column("Section", style="bold cyan", no_wrap=True, width=24)
        rows.add_column("Live Snapshot", overflow="ellipsis", no_wrap=True)
        rows.add_row("Market Tape", _short(" | ".join([
            _idx_line("N50", n50),
            _idx_line("BANK", bank),
            _idx_line("INDIA VIX", vix),
        ]), value_width))
        rows.add_row(
            "Breadth / Flows / Global",
            _short(
                f"Live {adv_dec.get('advances', '—')}A/{adv_dec.get('declines', '—')}D | "
                f"DB {brd.get('advances', '—')}A/{brd.get('declines', '—')}D | "
                f"{' | '.join(flows) or 'Flows n/a'} | {glob.get('risk_regime', 'mixed')}",
                value_width,
            ),
        )
        rows.add_row(
            "Index Leadership",
            _short(
                (f"Lead {leaders[0][0]} {_dashboard_fmt_pct(leaders[0][1])}" if leaders else "Lead n/a")
                + " | "
                + (f"Weak {laggards[0][0]} {_dashboard_fmt_pct(laggards[0][1])}" if laggards else "Weak n/a"),
                value_width,
            ),
        )
        rows.add_row(
            "Stock Movers",
            _short(
                (f"G {gainers[0].get('symbol', '—')} {_dashboard_fmt_pct(gainers[0].get('pct_change'))}" if gainers else "G n/a")
                + " | "
                + (f"L {losers[0].get('symbol', '—')} {_dashboard_fmt_pct(losers[0].get('pct_change'))}" if losers else "L n/a"),
                value_width,
            ),
        )
        rows.add_row("Narrative", _short(_compact_dashboard_narrative(snapshot), value_width))
        rows.add_row("Ctrl+C to exit", "refresh 60s")
        return Panel(
            rows,
            title=f"📊 Market Dashboard · {fetched_at} · focus: {focus}"[: max(40, width - 4)],
            border_style="bold white",
            expand=True,
        )

    leadership = Table(box=box.SIMPLE_HEAD, expand=True, padding=(0, 1))
    leadership.add_column("Leaders", style="green")
    leadership.add_column("Laggards", style="red")
    for i in range(max(len(leaders), len(laggards), 1)):
        l = f"{leaders[i][0]} {_dashboard_fmt_pct(leaders[i][1])}" if i < len(leaders) else ""
        r = f"{laggards[i][0]} {_dashboard_fmt_pct(laggards[i][1])}" if i < len(laggards) else ""
        leadership.add_row(l, r)

    health = Table(box=box.SIMPLE, expand=True, padding=(0, 1), show_header=False)
    health.add_column("Label", style="bold")
    health.add_column("Value")
    if brd and not brd.get("error"):
        health.add_row("DB Breadth", f"{brd.get('advances', '—')}A / {brd.get('declines', '—')}D  A/D {brd.get('ad_ratio', '—')}")
        if brd.get("avg_rs_pct") is not None:
            health.add_row("Avg RS", f"{brd.get('avg_rs_pct'):+.1f}%")
        sd = brd.get("stage_distribution") or {}
        if sd:
            health.add_row("Stages", " | ".join(
                f"S{i}:{int(sd.get(f'STAGE_{i}', sd.get(f'stage_{i}', 0)) or 0)}" for i in range(1, 5)
            ))
    flows = []
    for row in (fii.get("data") or [])[:3]:
        net = row.get("net_crore")
        net_txt = f"{net:+,.0f} Cr" if isinstance(net, (int, float)) else "n/a"
        flows.append(f"{row.get('category', 'Flow')} {net_txt}")
    if flows:
        health.add_row("Flows", " | ".join(flows))
    health.add_row("Global", str(glob.get("risk_regime", "mixed")))

    move_tbl = Table(box=box.SIMPLE_HEAD, expand=True, padding=(0, 1))
    move_tbl.add_column("Gainers", style="green")
    move_tbl.add_column("Losers", style="red")
    gainers = movers.get("gainers") or []
    losers = movers.get("losers") or []
    for i in range(row_limit):
        g = gainers[i] if i < len(gainers) else {}
        lo = losers[i] if i < len(losers) else {}
        move_tbl.add_row(
            f"{g.get('symbol', '')} {_dashboard_fmt_pct(g.get('pct_change'))}" if g else "",
            f"{lo.get('symbol', '')} {_dashboard_fmt_pct(lo.get('pct_change'))}" if lo else "",
        )

    bottom = Table.grid(expand=True)
    bottom.add_column(ratio=1)
    bottom.add_column(ratio=1)
    bottom.add_row(Panel(health, title="Breadth / Flows / Global", border_style="blue"), Panel(move_tbl, title="Stock Movers", border_style="magenta"))

    top = Table.grid(expand=True)
    top.add_column(ratio=1)
    top.add_column(ratio=1)
    top.add_row(Panel(tape, title="Market Tape", border_style="cyan"), Panel(leadership, title="Index Leadership", border_style="green"))

    narrative = _compact_dashboard_narrative(snapshot)
    catalyst_titles = [str(r.get("title", ""))[:90] for r in (cat.get("results") or [])[:2] if r.get("title")]
    narrative_text = narrative
    if catalyst_titles and not compact:
        narrative_text += "\n" + " | ".join(catalyst_titles)

    return Panel(
        Group(top, bottom, Panel(narrative_text, title="Narrative", border_style="yellow")),
        title=title[: max(40, width - 4)],
        border_style="bold white",
        expand=True,
    )


def _run_market_dashboard_live(focus: str = "", *, refresh_secs: int = 60, max_cycles: int | None = None) -> None:
    """Run the auto-refreshing compact dashboard until Ctrl+C."""
    con = _mcon()
    snapshot = _fetch_market_dashboard_snapshot(focus)
    cycles = 0
    with Live(
        _market_dashboard_renderable(snapshot),
        console=con,
        screen=True,
        auto_refresh=False,
        transient=False,
    ) as live:
        while True:
            live.update(_market_dashboard_renderable(snapshot), refresh=True)
            cycles += 1
            if max_cycles is not None and cycles >= max_cycles:
                return
            try:
                time.sleep(refresh_secs)
                snapshot = _fetch_market_dashboard_snapshot(focus)
            except KeyboardInterrupt:
                return


def _get_market_toolbar_data(force: bool = False) -> dict | None:
    now = time.time()
    if not force and _market_toolbar_cache["data"] and now - _market_toolbar_cache["ts"] < 60:
        return _market_toolbar_cache["data"]

    data = None
    try:
        from terminal.tools import get_live_market_overview

        overview = get_live_market_overview()
        if not overview.get("error"):
            all_indices = overview.get("indices") or {}
            mid_name = next(
                (
                    name for name in (
                        "NIFTY MIDCAP SELECT",
                        "NIFTY MIDCAP 50",
                        "NIFTY MIDCAP 100",
                    )
                    if name in all_indices
                ),
                "NIFTY MIDCAP SELECT",
            )
            indices = [
                _normalise_toolbar_index("NIFTY 50", all_indices.get("NIFTY 50")),
                _normalise_toolbar_index("NIFTY BANK", all_indices.get("NIFTY BANK")),
                _normalise_toolbar_index("MIDCPNIFTY", all_indices.get(mid_name)),
            ]
            if any(i.get("last") is not None for i in indices):
                data = {
                    "indices": indices,
                    "adv_dec": overview.get("adv_dec") or {},
                    "as_of": overview.get("as_of"),
                    "source": overview.get("source", "NSE live API"),
                }
    except Exception:
        data = None

    if data is None:
        try:
            from terminal.tools import get_index_snapshot

            indices = [
                _normalise_toolbar_index("NIFTY 50", get_index_snapshot("NIFTY 50")),
                _normalise_toolbar_index("NIFTY BANK", get_index_snapshot("NIFTY BANK")),
                _normalise_toolbar_index("MIDCPNIFTY", get_index_snapshot("NIFTY MIDCAP 50")),
            ]
            if any(i.get("last") is not None for i in indices):
                data = {
                    "indices": indices,
                    "adv_dec": {},
                    "as_of": indices[0].get("as_of"),
                    "source": "EOD index snapshot",
                }
        except Exception:
            data = None

    _market_toolbar_cache.update({"ts": now, "data": data})
    return data


def _print_market_toolbar() -> None:
    data = _get_market_toolbar_data()
    if not data:
        return

    indices = data.get("indices") or []
    table = Table(
        title="📊 Intraday Market Toolbar",
        box=box.SIMPLE_HEAVY,
        show_header=True,
        header_style="bold cyan",
        expand=True,
    )
    table.add_column("Index", style="bold white", no_wrap=True)
    table.add_column("Last", justify="right")
    table.add_column("% Chg", justify="right")
    table.add_column("Day Range", justify="right")
    for item in indices:
        pct = item.get("pct_change")
        table.add_row(
            item["name"],
            _fmt_index_price(item.get("last")),
            f"[{_index_pct_style(pct)}]{_fmt_index_pct(pct)}[/]",
            f"{_fmt_index_price(item.get('day_low'))} – {_fmt_index_price(item.get('day_high'))}",
        )
    narrative = _toolbar_narrative(indices, data.get("adv_dec"), data.get("source"))
    console.print(table)
    console.print(Panel(narrative, title="Short Market Narrative", border_style="cyan", expand=True))
    console.print(f"[dim]  Toolbar as of: {data.get('as_of') or _session_clock_label()}[/dim]")
    console.print()


def _ts() -> str:
    return _session_clock_label()


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
        cmd_hint = m.group(1).strip().strip('"').strip("'")  # remove any LLM-added quotes
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
    clock = f"  \x1b[2m{_session_clock_label()}\x1b[0m"
    return ANSI(f"  {tag}{clock}{fup}{turns}\x1b[1;36m ❯ \x1b[0m")


def _handle_model_command(agent, text: str) -> dict:
    """Parse and execute `/model` for the main Agent Adda chat backend only."""
    parts = text.strip().split()
    if not parts or parts[0].lower() != "/model":
        return {"handled": False}
    if len(parts) == 1 or parts[1].lower() in {"status", "current", "show"}:
        status = agent.model_status()
        return {"handled": True, "status": "ok", "action": "status", **status}

    provider = parts[1].lower()
    model = " ".join(parts[2:]).strip() or None
    result = agent.set_model_backend(provider, model=model)
    return {"handled": True, "action": "switch", **result}


def _print_model_command_result(result: dict) -> None:
    if result.get("status") != "ok":
        console.print(f"[red]  ✗ {result.get('error', 'model switch failed')}[/red]")
        return

    action = result.get("action")
    provider = str(result.get("provider") or "keyword")
    model = result.get("model") or "no LLM"
    backend = result.get("backend") or provider
    if action == "status":
        console.print(
            f"[green]  ✓ Main model:[/green] [bold]{backend}[/bold]"
            f"[dim]  · provider: {provider}  · voice STT/TTS unchanged[/dim]"
        )
    else:
        console.print(
            f"[green]  ✓ Main model switched:[/green] [bold]{backend}[/bold]"
            f"[dim]  · model: {model}  · voice STT/TTS unchanged[/dim]"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Display helpers  (all print to stdout; terminal scrolls naturally)
# ─────────────────────────────────────────────────────────────────────────────

_URL_RE = re.compile(r'(https?://[^\s\)\]>,"\']+)')
_HTML_LINK_RE = re.compile(
    r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
_MD_LINK_RE = re.compile(r'\[([^\]]+)\]\((https?://[^\s\)]+)\)')


def _strip_html_tags(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text)


def _html_links_to_visible_urls(text: str) -> str:
    """Convert HTML anchors <a href="url">label</a> → visible 'label (url)'.

    Plain visible URLs are required for macOS Terminal.app Cmd+click detection.
    """
    def _replace(match: re.Match) -> str:
        url   = html.unescape(match.group(1).strip())
        label = html.unescape(_strip_html_tags(match.group(2))).strip() or url
        if label == url:
            return url
        return f"{label} ({url})"

    return _HTML_LINK_RE.sub(_replace, text)


def _markdown_links_to_visible_urls(text: str) -> str:
    """Convert Markdown links [label](url) → visible 'label (url)'."""
    def _replace(match: re.Match) -> str:
        label = match.group(1).strip()
        url = match.group(2).strip()
        if label == url:
            return url
        return f"{label} ({url})"

    return _MD_LINK_RE.sub(_replace, text)


def _linkify_markdown(text: str) -> str:
    """Normalize links so markdown output always contains visible raw URLs."""
    text = _html_links_to_visible_urls(text)
    text = _markdown_links_to_visible_urls(text)
    return text


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
    """Create Rich Text; HTML/Markdown links → visible label + raw URL; bare URLs → cyan."""
    # Pre-process: convert markdown [label](url) → HTML anchors so the
    # single HTML-anchor loop handles both formats uniformly.
    text = _MD_LINK_RE.sub(r'<a href="\2">\1</a>', text)

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
            out.append(f" {url}", style=RichStyle(color="cyan", dim=True))
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


# ── Markdown table interceptor ────────────────────────────────────────────────
# Rich's Markdown renderer has no concept of per-cell colour.  We parse any
# markdown table blocks out of the LLM answer, render them as proper Rich Table
# objects with colour coding for %, signals, stages, etc., then render the
# surrounding prose via normal Markdown().

import re as _re_mod

_MD_TABLE_RE = _re_mod.compile(
    r"(?m)(?:^[ \t]*\|.+\|\s*\n){2,}",   # 2+ consecutive pipe-table lines
)


def _cell_style(value: str) -> str | None:
    """Return a Rich style for a table cell value, or None for plain white."""
    v = value.strip()

    # Percentage values — +3.11% green, -0.96% red
    m = _re_mod.match(r"^([+\-])(\d[\d.,]*)\s*%$", v)
    if m:
        return "bold bright_green" if m.group(1) == "+" else "bold bright_red"

    # Plain numeric % like "3.11%" (no sign) — neutral
    if _re_mod.match(r"^\d[\d.,]*\s*%$", v):
        return "dim"

    # Trading signals
    upper = v.upper().replace(" ", "_")
    _SIG = {
        "STRONG_BUY": "bold bright_green",
        "BUY":        "green",
        "ACCUMULATE": "green",
        "HOLD":       "yellow",
        "WEAK_HOLD":  "dim yellow",
        "WEAK_SELL":  "dim red",
        "SELL":       "red",
        "STRONG_SELL":"bold bright_red",
        "AVOID":      "bold red",
    }
    if upper in _SIG:
        return _SIG[upper]

    # Stage labels
    _STG = {
        "STAGE_1": "cyan",   "STAGE 1": "cyan",   "1": "cyan",
        "STAGE_2": "bold green", "STAGE 2": "bold green", "2": "bold green",
        "STAGE_3": "yellow", "STAGE 3": "yellow", "3": "yellow",
        "STAGE_4": "red",    "STAGE 4": "red",    "4": "red",
    }
    if v.upper() in _STG:
        return _STG[v.upper()]

    # ₹ price — white
    if v.startswith("₹"):
        return "white"

    return None  # default — let Rich decide


def _render_md_table_as_rich(md_block: str) -> None:
    """Parse a raw markdown table string and render it as a Rich Table."""
    lines = [ln.strip() for ln in md_block.strip().splitlines() if ln.strip()]

    # Pull header, skip separator, collect rows
    if len(lines) < 2:
        console.print(Markdown(md_block))
        return

    def _parse_row(line: str) -> list[str]:
        """Split a markdown pipe row into clean cell values."""
        cells = line.strip().strip("|").split("|")
        return [c.strip() for c in cells]

    headers = _parse_row(lines[0])
    data_lines = [ln for ln in lines[2:] if not _re_mod.match(r"^[\|\-\s:]+$", ln)]

    tbl = Table(
        box=box.SIMPLE_HEAD,
        header_style="bold cyan",
        show_header=True,
        expand=False,
        padding=(0, 1),
    )
    for h in headers:
        tbl.add_column(h)

    for ln in data_lines:
        cells = _parse_row(ln)
        # Pad or trim to match header count
        while len(cells) < len(headers):
            cells.append("")
        cells = cells[: len(headers)]

        rich_cells: list[Text | str] = []
        for cell in cells:
            st = _cell_style(cell)
            rich_cells.append(Text(cell, style=st) if st else cell)
        tbl.add_row(*rich_cells)

    console.print(tbl)


def _print_md_with_rich_tables(text: str) -> None:
    """
    Split *text* at markdown table blocks, rendering each table via Rich Table
    (with colour-coded cells) and all surrounding prose via Rich Markdown.
    """
    last = 0
    for m in _MD_TABLE_RE.finditer(text):
        prose = text[last : m.start()]
        if prose.strip():
            console.print(Markdown(_linkify_markdown(prose)))
        _render_md_table_as_rich(m.group())
        last = m.end()
    tail = text[last:]
    if tail.strip():
        console.print(Markdown(_linkify_markdown(tail)))


def _is_plain_agent_brief(text: str) -> bool:
    """Detect structured no-LLM Agent Adda briefs that must preserve newlines."""
    return "━━━" in (text or "") and "\n▶ " in (text or "")


def _normalise_plain_agent_brief(text: str) -> str:
    """Remove Markdown-only wrapper markers before plain-text rendering."""
    text = re.sub(r"(?m)^_(Mode:\s+.+)_$", r"\1", text or "")
    text = re.sub(r"\*\*([^*\n]+)\*\*", r"\1", text)
    return text


def _print_response(result: dict) -> None:
    global _followups
    answer  = result.get("answer", "(no answer)")
    backend = result.get("backend", "?")

    # Strip follow-ups from answer body
    clean, _followups = _parse_followups(answer)

    # ── Pre-render LLM plan — fast gpt-4o-mini call to decide layout ─────
    trace = result.get("trace") or []
    plan  = pre_render_plan(clean, trace)

    # ── Agent header — colour driven by plan sentiment / alert level ──────
    header_style = plan.get("_header_style", "green dim")  # overridden by apply below
    console.print()
    console.rule(
        f"[bold green] 🤖  Agent Adda [/bold green][dim] {_ts()}  ·  {backend} [/dim]",
        style="green dim",
    )
    console.print()

    # ── Summary strip + get recommended render mode from plan ─────────────
    render_mode = plan.get("render_mode", "tables_first")
    apply_render_plan(plan)      # prints summary strip if show_summary_strip=True

    # ── Comparison table (always first — user explicitly asked to compare) ─
    comp = result.get("comparison")
    if comp and comp.get("stock_details"):
        _render_comparison_table(comp)

    # ── Structured financial tables — order respects render_mode ──────────
    if render_mode != "narrative_only":
        render_trace_tables(trace, plan=plan)

    # ── Body — Rich Markdown with colour-coded tables ─────────────────────
    if render_mode != "tables_only":
        # Emphasise bold_symbols from plan in the narrative text
        bold_syms = get_bold_symbols(plan)
        display = clean
        if bold_syms:
            for sym in bold_syms:
                display = _re_mod.sub(
                    rf"(?<!\[)\b{_re_mod.escape(sym)}\b(?!\])",
                    f"**{sym}**",
                    display,
                )

        has_markup = backend != "Keyword (no LLM)" and any(
            c in display for c in ["**", "##", "- ", "* ", "```", "|"]
        )
        if _is_plain_agent_brief(display):
            console.print(_text_with_links(_normalise_plain_agent_brief(display)), style="white")
        elif has_markup:
            # Use table-intercepting renderer — colours % / signals / stages
            _print_md_with_rich_tables(display)
        else:
            console.print(_text_with_links(display), style="white")

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


_US_INDEX_SYMBOLS = ["^GSPC", "^IXIC", "^NDX", "^DJI", "^RUT", "^VIX", "SPY", "QQQ", "DIA", "IWM"]
_US_SECTOR_SYMBOLS = ["SPY", "QQQ", "XLK", "XLF", "XLE", "XLY", "XLI", "XLU", "XLV", "XLP", "XLB", "XLRE", "SMH", "SOXX", "ARKK"]


def _parse_us_global_command(text: str) -> dict | None:
    """Parse direct US/global slash commands into a deterministic request."""
    raw = (text or "").strip()
    parts = raw.split()
    if not parts:
        return None
    cmd = parts[0].lower()

    if cmd == "/global" and len(parts) >= 2 and parts[1].lower() == "readthrough":
        return {"view": "readthrough", "label": "Global India Read-Through", "symbols": None, "stock": None}

    if cmd != "/us":
        return None

    view = parts[1].lower() if len(parts) >= 2 else "summary"
    if view == "indices":
        return {"view": "indices", "label": "US Indices", "symbols": _US_INDEX_SYMBOLS, "stock": None}
    if view in ("sectors", "sector"):
        return {"view": "sectors", "label": "US Sector Rotation", "symbols": _US_SECTOR_SYMBOLS, "stock": None}
    if view == "stage2":
        return {"view": "stage2", "label": "US Stage 2 Leaders", "symbols": None, "stock": None}
    if view == "vcp":
        return {"view": "vcp", "label": "US VCP Setups", "symbols": None, "stock": None}
    if view == "stock" and len(parts) >= 3:
        stock = parts[2].upper()
        return {"view": "stock", "label": f"US Stock: {stock}", "symbols": ["SPY", "QQQ", stock], "stock": stock}
    return {"view": "summary", "label": "US Market Summary", "symbols": None, "stock": None}


def _is_non_empty_df(value) -> bool:
    return value is not None and hasattr(value, "empty") and not value.empty


def _fmt_us_value(value, digits: int = 2, suffix: str = "") -> str:
    if value is None:
        return "-"
    try:
        if pd.isna(value):
            return "-"
    except (TypeError, ValueError):
        pass
    if isinstance(value, str):
        return value or "-"
    try:
        return f"{float(value):,.{digits}f}{suffix}"
    except (TypeError, ValueError):
        return str(value) or "-"


def _markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return ""
    header = "| " + " | ".join(headers) + " |"
    separator = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(str(cell) if str(cell) else "-" for cell in row) + " |" for row in rows]
    return "\n".join([header, separator, *body])


def _metrics_for_symbols(metrics, symbols: list[str] | None = None):
    if not _is_non_empty_df(metrics) or "SYMBOL" not in metrics.columns:
        return pd.DataFrame()
    df = metrics.copy()
    df["SYMBOL"] = df["SYMBOL"].astype(str)
    if symbols:
        order = {str(symbol): idx for idx, symbol in enumerate(symbols)}
        df = df[df["SYMBOL"].isin(order)].copy()
        if df.empty:
            return df
        df["_ORDER"] = df["SYMBOL"].map(order)
        df = df.sort_values("_ORDER").drop(columns=["_ORDER"])
    return df.reset_index(drop=True)


def _format_us_metric_table(metrics, symbols: list[str] | None = None, limit: int = 10) -> str:
    df = _metrics_for_symbols(metrics, symbols).head(limit)
    rows: list[list[str]] = []
    for _, row in df.iterrows():
        rows.append(
            [
                _fmt_us_value(row.get("SYMBOL"), 0),
                _fmt_us_value(row.get("CLOSE"), 2),
                _fmt_us_value(row.get("RET_1D"), 2, "%"),
                _fmt_us_value(row.get("RET_1M"), 2, "%"),
                _fmt_us_value(row.get("RSI_14"), 1),
                _fmt_us_value(row.get("SMA_ALIGNMENT"), 0),
                _fmt_us_value(row.get("MACD_SIGNAL"), 0),
                _fmt_us_value(row.get("STAGE"), 0),
                _fmt_us_value(row.get("DIST_52W_HIGH_PCT"), 2, "%"),
            ]
        )
    return _markdown_table(["Symbol", "Close", "1D", "1M", "RSI", "SMA", "MACD", "Stage", "52W%"], rows)


def _format_us_sector_table(sectors, limit: int = 8) -> str:
    if not _is_non_empty_df(sectors):
        return ""
    rows: list[list[str]] = []
    for _, row in sectors.head(limit).iterrows():
        rows.append(
            [
                _fmt_us_value(row.get("SYMBOL"), 0),
                _fmt_us_value(row.get("RET_1M"), 2, "%"),
                _fmt_us_value(row.get("RET_3M"), 2, "%"),
                _fmt_us_value(row.get("RS_SPY_3M"), 2),
                _fmt_us_value(row.get("ROTATION_SCORE"), 1),
                _fmt_us_value(row.get("SMA_ALIGNMENT"), 0),
                _fmt_us_value(row.get("MACD_SIGNAL"), 0),
            ]
        )
    return _markdown_table(["Symbol", "1M", "3M", "RS/SPY", "Score", "SMA", "MACD"], rows)


def _format_us_screener_table(frame, limit: int = 8) -> str:
    if not _is_non_empty_df(frame):
        return ""
    rows: list[list[str]] = []
    for _, row in frame.head(limit).iterrows():
        rows.append(
            [
                _fmt_us_value(row.get("SYMBOL"), 0),
                _fmt_us_value(row.get("RET_1M"), 2, "%"),
                _fmt_us_value(row.get("RS_SPY_3M"), 2),
                _fmt_us_value(row.get("RSI_14"), 1),
                _fmt_us_value(row.get("SMA_ALIGNMENT"), 0),
                _fmt_us_value(row.get("MACD_SIGNAL"), 0),
                _fmt_us_value(row.get("SCREENER_SCORE"), 1),
            ]
        )
    return _markdown_table(["Symbol", "1M", "RS/SPY", "RSI", "SMA", "MACD", "Score"], rows)


def _format_us_vcp_table(frame, limit: int = 8) -> str:
    if not _is_non_empty_df(frame):
        return ""
    rows: list[list[str]] = []
    for _, row in frame.head(limit).iterrows():
        rows.append(
            [
                _fmt_us_value(row.get("SYMBOL"), 0),
                _fmt_us_value(row.get("RET_1M"), 2, "%"),
                _fmt_us_value(row.get("RS_SPY_3M"), 2),
                _fmt_us_value(row.get("DIST_52W_HIGH_PCT"), 2, "%"),
                _fmt_us_value(row.get("SETUP"), 0),
                _fmt_us_value(row.get("SCREENER_SCORE"), 1),
            ]
        )
    return _markdown_table(["Symbol", "1M", "RS/SPY", "52W%", "Setup", "Score"], rows)


def _format_us_technical_takeaways(metrics, symbols: list[str] | None = None) -> list[str]:
    df = _metrics_for_symbols(metrics, symbols)
    if df.empty:
        return ["- No index tape was available for technical takeaways."]

    risk_df = df[~df["SYMBOL"].isin(["^VIX"])].copy()
    if risk_df.empty:
        risk_df = df.copy()

    takeaways: list[str] = []
    if "RET_1M" in risk_df.columns:
        ret_1m = pd.to_numeric(risk_df["RET_1M"], errors="coerce").dropna()
        strongest = risk_df.loc[ret_1m.idxmax()] if not ret_1m.empty else None
    else:
        strongest = None
    if strongest is not None:
        takeaways.append(
            f"- **Strongest 1M index**: {strongest.get('SYMBOL', '-')} at "
            f"{_fmt_us_value(strongest.get('RET_1M'), 2, '%')}."
        )

    total = len(risk_df)
    if total:
        sma_bullish = risk_df.get("SMA_ALIGNMENT", pd.Series([], dtype=str)).astype(str).str.upper().eq("BULLISH").sum()
        macd_bullish = risk_df.get("MACD_SIGNAL", pd.Series([], dtype=str)).astype(str).str.upper().eq("BULLISH").sum()
        takeaways.append(
            f"- **Trend confirmation**: {int(sma_bullish)}/{total} symbols have bullish SMA alignment; "
            f"{int(macd_bullish)}/{total} have bullish MACD."
        )

    if "RSI_14" in risk_df.columns:
        rsi = pd.to_numeric(risk_df["RSI_14"], errors="coerce")
        stretched = risk_df.loc[rsi >= 70, "SYMBOL"].astype(str).head(4).tolist()
        if stretched:
            takeaways.append(f"- **Momentum stretch**: {', '.join(stretched)} have RSI above 70, so follow-through needs confirmation.")

    vix_row = df[df["SYMBOL"].eq("^VIX")]
    if not vix_row.empty:
        vix = vix_row.iloc[0]
        takeaways.append(
            f"- **Volatility read**: ^VIX is at {_fmt_us_value(vix.get('CLOSE'), 2)} with "
            f"{_fmt_us_value(vix.get('RET_1M'), 2, '%')} over 1M."
        )

    return takeaways or ["- Technical breadth is mixed; use the linked report for the full chart table."]


def _format_us_global_terminal_summary(request: dict, bundle: dict, report_result: dict) -> str:
    """Create a detailed Markdown summary for direct terminal output."""
    readthrough = bundle.get("india_readthrough", {}) or {}
    risk = bundle.get("risk_dashboard", {}) or {}
    metrics = bundle.get("metrics")
    stage2 = bundle.get("stage2")
    sectors = bundle.get("sector_rotation")
    vcp = bundle.get("vcp")
    view = request.get("view", "summary")
    symbols = request.get("symbols")
    regime = readthrough.get("global_regime") or risk.get("regime", "unavailable")

    lines = [
        f"### {request.get('label', 'US / Global Market')}",
        "",
        "#### Executive Read",
        f"- **Regime**: {regime}",
        f"- **Report**: `{report_result.get('report_path', '-')}`",
    ]
    if risk.get("score") is not None:
        lines.append(f"- **Risk score**: {_fmt_us_value(risk.get('score'), 0)}")

    if stage2 is not None and not stage2.empty:
        top = ", ".join(str(x) for x in stage2.get("SYMBOL", []).head(5).tolist())
        if top:
            lines.append(f"- **Stage 2 leaders**: {top}")
    if sectors is not None and not sectors.empty:
        top = ", ".join(str(x) for x in sectors.get("SYMBOL", []).head(5).tolist())
        if top:
            lines.append(f"- **Sector ETF leaders**: {top}")
    if vcp is not None and not vcp.empty:
        top = ", ".join(str(x) for x in vcp.get("SYMBOL", []).head(5).tolist())
        if top:
            lines.append(f"- **VCP setups**: {top}")

    if view in {"indices", "stock", "summary", "readthrough"}:
        metric_table = _format_us_metric_table(metrics, symbols=symbols if view in {"indices", "stock"} else _US_INDEX_SYMBOLS)
        if metric_table:
            lines.extend(["", "#### US Index Tape", metric_table])

    if view in {"sectors", "summary", "readthrough"}:
        sector_table = _format_us_sector_table(sectors)
        if sector_table:
            lines.extend(["", "#### Sector Rotation Snapshot", sector_table])

    if view in {"stage2", "summary"}:
        stage2_table = _format_us_screener_table(stage2)
        if stage2_table:
            lines.extend(["", "#### Stage 2 Leaders", stage2_table])

    if view in {"vcp", "indices", "summary"}:
        vcp_table = _format_us_vcp_table(vcp)
        if vcp_table:
            lines.extend(["", "#### VCP Setups", vcp_table])

    risk_signals = risk.get("signals") or []
    if risk_signals:
        lines.extend(["", "#### Risk / Regime Signals"])
        for signal in risk_signals[:6]:
            lines.append(f"- {signal}")

    if view in {"indices", "stock", "summary"}:
        lines.extend(["", "#### Technical Takeaways"])
        lines.extend(_format_us_technical_takeaways(metrics, symbols=symbols if view in {"indices", "stock"} else _US_INDEX_SYMBOLS))

    implications = readthrough.get("india_sector_implications", [])
    if implications:
        lines.extend(["", "#### India Read-Through"])
        for item in implications[:5]:
            symbols = ", ".join(item.get("symbols", []))
            lines.append(
                f"- **{item.get('stance', 'watch').upper()}**: "
                f"{item.get('nse_sector', '-')} via {symbols or '-'} "
                f"({item.get('confidence', '-')})"
            )

    warnings = bundle.get("warnings") or []
    if warnings:
        lines.extend(["", "#### Warnings", "- " + "\n- ".join(str(w) for w in warnings[:3])])

    return "\n".join(lines)


def _handle_us_global_command(text: str) -> bool:
    """Run direct US/global command. Returns True when text was handled."""
    request = _parse_us_global_command(text)
    if not request:
        return False

    console.print(f"[dim]  → {request['label']}[/dim]")
    try:
        from global_market_intelligence import (
            GlobalMarketDataLoader,
            build_us_market_bundle,
            render_us_market_report,
        )

        loader = GlobalMarketDataLoader()
        result = loader.load(symbols=request.get("symbols"), force=False, lookback_days=365)
        if result.get("status") not in {"ok", "empty"}:
            warning = "; ".join(result.get("warnings", [])) or "US/global data unavailable."
            console.print(f"[bold red]  ❌  {warning}[/bold red]")
            return True

        bundle = build_us_market_bundle(result["prices"], warnings=result.get("warnings", []))
        report_bundle = bundle
        if request.get("symbols"):
            full_result = loader.load(symbols=None, force=False, lookback_days=365)
            if full_result.get("status") in {"ok", "empty"}:
                full_prices = full_result.get("prices")
                if full_prices is not None and not getattr(full_prices, "empty", False):
                    report_bundle = build_us_market_bundle(full_prices, warnings=full_result.get("warnings", []))
        report_result = render_us_market_report(report_bundle)
        console.print(Markdown(_format_us_global_terminal_summary(request, bundle, report_result)))
    except Exception as exc:
        console.print(f"[bold red]  ❌  US/global command failed: {exc}[/bold red]")
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Background monitor — alert rendering + queue drain
# ─────────────────────────────────────────────────────────────────────────────

_ALERT_DIR_STYLE = {"BUY": "bold green", "SELL": "bold red", "WATCH": "bold yellow"}
_CONF_COLOURS    = {"high": "green", "medium": "yellow", "low": "dim white"}


def _live_con() -> Console:
    """Console that writes to sys.stdout — goes through prompt_toolkit's
    patch_stdout proxy so output appears above the active input line."""
    return Console(highlight=False, force_terminal=True, file=sys.stdout)


def _render_monitor_event_live(ev: dict) -> None:
    """Render one monitor event through sys.stdout (patch_stdout safe).
    Called by the auto-display thread while user is idle at the prompt."""
    con = _live_con()
    kind = ev.get("type")
    if kind == "alerts":
        from terminal.monitor import Alert
        alerts: list[Alert] = ev.get("alerts", [])
        strategy = ev["strategy"].upper()
        index    = ev["index"]
        as_of    = ev["as_of"]
        run_n    = ev.get("run_n", "?")
        tbl = Table(box=box.SIMPLE_HEAD, show_header=True,
                    header_style="bold cyan", expand=False, padding=(0, 1))
        tbl.add_column("",  width=2)
        tbl.add_column("Symbol",  style="bold white", min_width=12)
        tbl.add_column("Signal",  style="cyan",       min_width=20)
        tbl.add_column("Dir",     min_width=5)
        tbl.add_column("Entry",   justify="right", min_width=8)
        tbl.add_column("Target",  justify="right", min_width=8)
        tbl.add_column("SL",      justify="right", min_width=8)
        tbl.add_column("R:R",     justify="right", min_width=4)
        for a in alerts[:10]:
            ds = _ALERT_DIR_STYLE.get(a.direction, "white")
            cs = _CONF_COLOURS.get(a.confidence, "white")
            tbl.add_row(
                a.emoji, a.symbol, a.signal[:22],
                f"[{ds}]{a.direction}[/{ds}]",
                f"₹{a.entry:.1f}"    if a.entry    else "—",
                f"₹{a.target:.1f}"   if a.target   else "—",
                f"₹{a.stoploss:.1f}" if a.stoploss else "—",
                f"[{cs}]{a.rr:.1f}[/{cs}]" if a.rr else "—",
            )
        con.print()
        con.print(Rule(
            f"[bold magenta]🔔 MONITOR ALERT  [{strategy}]  {index}  ·  {as_of}  ·  scan #{run_n}[/bold magenta]",
            style="magenta",
        ))
        con.print(tbl)
        con.print("[dim]  ━ Not investment advice. Research only. ━[/dim]")
        con.print()
    elif kind == "heartbeat":
        strategy = ev["strategy"]
        index    = ev["index"]
        as_of    = ev["as_of"]
        run_n    = ev.get("run_n", "?")
        con.print(
            f"  ⏱  Monitor '{strategy}' — scan #{run_n} complete, no signals  ({index} @ {as_of})",
            style="dim",
        )
    elif kind == "error":
        con.print(
            f"  ⚠  Monitor '{ev.get('strategy')}' error: {ev.get('message')}",
            style="dim red", markup=False,
        )


# ── Auto-display thread — drains the alert queue every 3s while user is idle ──
_alert_autodisplay_stop = threading.Event()
_alert_autodisplay_thread: threading.Thread | None = None


def _should_auto_render_monitor_event(ev: dict) -> bool:
    """Only interrupt the prompt for actionable monitor output.

    Heartbeats are still retained by MonitorManager.recent_events() and shown
    from the explicit `/monitor` view, but they should not redraw the active
    prompt or interleave with an answer.
    """
    return ev.get("type") in {"alerts", "error"}


def _start_alert_autodisplay() -> threading.Thread:
    """Start background thread that auto-prints monitor alerts via patch_stdout."""
    global _alert_autodisplay_thread
    if _alert_autodisplay_thread is not None and _alert_autodisplay_thread.is_alive():
        return _alert_autodisplay_thread
    _alert_autodisplay_stop.clear()

    def _loop():
        while not _alert_autodisplay_stop.is_set():
            _alert_autodisplay_stop.wait(timeout=3)
            if _alert_autodisplay_stop.is_set():
                break
            try:
                mon = get_monitor()
                events = mon.drain_alerts()
                for ev in events:
                    if _should_auto_render_monitor_event(ev):
                        _render_monitor_event_live(ev)
            except Exception:
                pass

    _alert_autodisplay_thread = threading.Thread(target=_loop, daemon=True, name="alert-autodisplay")
    _alert_autodisplay_thread.start()
    return _alert_autodisplay_thread


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

    mc = _mcon()
    mc.print()
    mc.print(Rule(
        f"[bold magenta]🔔 MONITOR ALERT  [{strategy}]  {index}  ·  {as_of}  ·  scan #{run_n}[/bold magenta]",
        style="magenta",
    ))
    mc.print(tbl)
    mc.print("[dim]  ━ Not investment advice. Research only. ━[/dim]")
    mc.print()


def _render_monitor_heartbeat(event: dict) -> None:
    """Print a quiet heartbeat line (no signals found this cycle)."""
    strategy = event["strategy"]
    index    = event["index"]
    as_of    = event["as_of"]
    run_n    = event.get("run_n", "?")
    _mcon().print(
        f"  ⏱  Monitor '{strategy}' — scan #{run_n} complete, no new signals"
        f"  ({index} @ {as_of})",
        style="dim",
    )


def _check_monitor_alerts() -> None:
    """Drain and render any queued monitor alerts. Called in the chat loop."""
    mon = get_monitor()
    if not mon.any_active():
        return
    for ev in mon.drain_alerts():
        if _should_auto_render_monitor_event(ev):
            _render_monitor_event_live(ev)


def _render_monitor_event_console(ev: dict) -> None:
    """Render one monitor event in response to an explicit /monitor command."""
    kind = ev.get("type")
    if kind == "alerts":
        _render_alert_batch(ev)
    elif kind == "heartbeat":
        _render_monitor_heartbeat(ev)
    elif kind == "error":
        _mcon().print(
            f"  ⚠  Monitor '{ev.get('strategy')}' error: {ev.get('message')}",
            style="dim red", markup=False,
        )


def _print_monitor_results() -> None:
    """Show monitor status plus queued/recent scan results."""
    mon = get_monitor()
    _print_monitor_status()

    queued_events = mon.drain_alerts()
    events = queued_events or (mon.recent_events() if hasattr(mon, "recent_events") else [])
    mc = _mcon()
    if not events:
        mc.print("[dim]  No monitor scan results yet. The first real scan runs after the worker warm-up delay.[/dim]")
        return

    if not queued_events:
        mc.print("[dim]  Showing recently displayed monitor results.[/dim]")
    for ev in events[-10:]:
        _render_monitor_event_console(ev)


def _print_monitor_status() -> None:
    """Show status table for all running monitors."""
    mon = get_monitor()
    workers = mon.status()
    mc = _mcon()
    if not workers:
        mc.print("[dim]  No monitors active. Use /monitor start [strategy] to activate.[/dim]")
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

    mc.print()
    mc.print(Panel(tbl, title="[bold magenta]🔔 Background Monitors[/bold magenta]", expand=False))
    mc.print()


_VALID_MONITOR_INTERVALS = {1, 3, 5, 10, 15, 30, 60}


def _parse_monitor_start_args(parts: list[str]) -> dict[str, object]:
    """Parse `/monitor start` arguments without treating `NIFTY 50` as interval."""
    strategy = parts[2].lower() if len(parts) > 2 else "all"
    idx_parts: list[str] = []
    interval = 15
    direction = "all"

    remaining = parts[3:] if len(parts) > 3 else []
    for tok in remaining:
        if tok.isdigit() and int(tok) in _VALID_MONITOR_INTERVALS:
            interval = int(tok)
        elif tok.lower() in ("buy", "sell", "all"):
            direction = tok.lower()
        else:
            idx_parts.append(tok.upper())

    return {
        "strategy": strategy,
        "index": " ".join(idx_parts) if idx_parts else "NIFTY 500",
        "interval": interval,
        "direction": direction,
    }


def _handle_monitor_command(parts: list[str]) -> None:
    """Handle /monitor [start|stop|status|list] [strategy] [index]."""
    mon = get_monitor()
    sub = parts[1].lower() if len(parts) > 1 else "results"

    if sub in MONITOR_STRATEGIES or sub == "all":
        parts = [parts[0], "start", *parts[1:]]
        sub = "start"

    if sub in ("results", "result", "alerts", "show"):
        _print_monitor_results()
        return

    if sub == "list":
        mc = _mcon()
        tbl = Table(box=box.SIMPLE_HEAD, header_style="bold cyan", expand=False)
        tbl.add_column("Strategy", style="bold white", min_width=12)
        tbl.add_column("Description", style="dim")
        for k, v in MONITOR_STRATEGIES.items():
            tbl.add_row(k, v["description"])
        mc.print()
        mc.print(Panel(tbl, title="[bold cyan]Available Monitor Strategies[/bold cyan]", expand=False))
        mc.print("[dim]  Usage: /monitor start breakout [NIFTY 500] [15] [buy|sell|all][/dim]")
        mc.print()
        return

    if sub == "status":
        _print_monitor_status()
        return

    if sub == "stop":
        strategy = parts[2].lower() if len(parts) > 2 else "all"
        index    = " ".join(parts[3:]).upper() if len(parts) > 3 else None
        msg      = mon.stop(strategy, index)
        _mcon().print(f"  {msg}", markup=False)
        return

    if sub == "start":
        parsed = _parse_monitor_start_args(parts)
        strategy = str(parsed["strategy"])
        index = str(parsed["index"])
        interval = int(parsed["interval"])
        direction = str(parsed["direction"])

        if strategy not in MONITOR_STRATEGIES:
            _out = sys.__stdout__ or sys.stdout
            _out.write(
                f"\n  Unknown strategy '{strategy}'. "
                f"Available: {', '.join(MONITOR_STRATEGIES)}\n\n"
            )
            _out.flush()
            return

        msg = mon.start(
            strategy     = strategy,
            index        = index,
            interval_min = interval,
            direction    = direction,
        )
        # Use sys.__stdout__ directly — Rich+prompt_toolkit cursor conflict can swallow console.print()
        _out = sys.__stdout__ or sys.stdout
        _out.write(f"\n  {msg}\n")
        if "started" in msg.lower():
            _out.write(f"  Scanning: {index}  ·  Interval: {interval}m  ·  Direction: {direction}\n")
        _out.write("\n")
        _out.flush()
        return

    # Unknown subcommand
    _mcon().print(
        "[dim]  Usage: /monitor [start|stop|status|list]  strategy  [index]  [interval_min]  [buy|sell|all][/dim]\n"
        "[dim]  Example: /monitor start breakout NIFTY 500 15 buy[/dim]"
    )


_SCAN_ALIASES = {
    "orb":      ("opening_range_breakout", "Opening Range Breakout"),
    "gap":      ("gap_and_go",             "Gap & Go"),
    "macd":     ("macd_crossover",         "MACD Crossover"),
    "rsi":      ("rsi_divergence",         "RSI Divergence"),
    "bb":       ("bb_squeeze",             "Bollinger Squeeze"),
    "vwap":     ("vwap_reclaim",           "VWAP Reclaim"),
    "vcp":      ("vcp",                    "VCP"),
    "momentum": ("momentum",               "Momentum"),
}


def _rewrite_scan_command(text: str) -> tuple[str, str]:
    """Return the agent query and status label for a `/scan` shortcut."""
    parts = text.split(maxsplit=1)
    arg = parts[1].strip() if len(parts) > 1 else ""
    alias_key = arg.lower()

    if alias_key in _SCAN_ALIASES:
        screen_type, label = _SCAN_ALIASES[alias_key]
        return (
            f"Run intraday screener {screen_type} on NIFTY 500 on 15m charts",
            f"Intraday screener: {label}",
        )

    index = arg.upper() if arg else "NIFTY 50"
    return (
        f"Scan {index} for intraday research setups using all strategies on 15m charts",
        f"Intraday scan: {index}",
    )


def _print_help() -> None:
    print()
    console.print(Panel(
        Text.from_markup(
            "[bold cyan]MODE COMMANDS[/bold cyan]\n"
            "  [red]/live[/red]  or  [red]/l[/red]        — Live / Intraday  (real-time NSE API)\n"
            "  [blue]/eod[/blue]   or  [blue]/h[/blue]        — EOD / Historical (CSV + DB snapshot)\n"
            "  [white]/auto[/white]  or  [white]/a[/white]        — Auto-detect from query keywords\n\n"
            "[bold cyan]MODEL COMMANDS[/bold cyan]\n"
            "  [magenta]/model[/magenta]                 — Show active main chat model\n"
            "  [magenta]/model gpt-4o[/magenta]          — Switch main chat backend to OpenAI gpt-4o\n"
            "  [magenta]/model ollama[/magenta]          — Switch main chat backend to Ollama default\n"
            "  [magenta]/model ollama granite4:latest[/magenta] — Switch to a specific Ollama model\n"
            "  [magenta]/model keyword[/magenta]         — Disable LLM and use deterministic tool routing\n\n"
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
            "  [yellow]/options NIFTY[/yellow]         — Live options chain: Calls|Strike|Puts table (PCR, max pain, IV)\n"
            "  [yellow]/options BANKNIFTY[/yellow]     — BANKNIFTY options chain (nearest expiry)\n"
            "  [yellow]/options NIFTY 1[/yellow]       — NIFTY options chain (next expiry, index 1)\n"
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
            "  [red]/strength MANINDS THERMAX[/red]     — Validate CANSLIM + RS + fundamentals + Piotroski\n"
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
            "  [blue]/voice-mode on[/blue]            — Auto-speak every normal Agent Adda answer\n"
            "  [blue]/voice-mode off[/blue]           — Disable auto-spoken answers\n"
            "  [blue]/voice-live[/blue]               — Live voice assistant: listen, answer, speak, repeat\n"
            "  [blue]/voice[/blue]                   — Generate daily voice briefing (MP3)\n"
            "  [blue]/concall TCS[/blue]              — Concall NLP: sentiment + themes + guidance\n\n"
            "[bold cyan]GLOBAL MARKET[/bold cyan]\n"
            "  [green]/global[/green]                 — Global risk regime and India read-through\n"
            "  [green]/dashboard[/green]              — Current market dashboard + narrative\n"
            "  [green]/dash[/green]                   — Alias for /dashboard\n\n"
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
            "[bold cyan]DATA REFRESH[/bold cyan]\n"
            "  [green]/refresh[/green]               — Fast snapshot refresh (stage DB, ~1–2 min)\n"
            "  [green]/refresh live[/green]           — Live prices only (~30s)\n"
            "  [green]/refresh full[/green]           — Full pipeline: R bhavcopy → analysis → snapshot\n"
            "  [green]/refresh analysis[/green]       — Analysis + snapshot (skips aux fetch)\n"
            "  [green]/refresh status[/green]         — Check if refresh is running\n"
            "  [green]/refresh stop[/green]           — Cancel a running refresh\n\n"
            "[bold cyan]APPEARANCE[/bold cyan]\n"
            "  [magenta]/theme[/magenta]                  — Browse & switch color themes\n"
            "  [magenta]/theme dracula[/magenta]          — Switch to Dracula theme\n"
            "  [magenta]/scale[/magenta]                  — Browse & switch layout scale\n"
            "  [magenta]/scale large[/magenta]            — Wide charts, spacious tables\n\n"
            "[bold cyan]FOLLOW-UPS[/bold cyan]\n"
            "  [yellow]1 / 2 / 3[/yellow]              — Ask the numbered follow-up question\n\n"
            "[bold cyan]OTHER[/bold cyan]\n"
            "  [dim]/clear  cls  clear[/dim]    — Clear screen\n"
            "  [dim]exit / quit / Ctrl-C[/dim]  — Exit\n"
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


def _is_plain_greeting(text: str) -> bool:
    cleaned = re.sub(r"[^\w\s]", " ", text or "").strip().lower()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned in {
        "hello", "hi", "hey", "hey there", "hi there", "hello there",
        "good morning", "good afternoon", "good evening",
    }


def _print_greeting_response() -> None:
    console.print("[bold cyan]  Hello — Agent Adda is ready.[/bold cyan]")
    console.print(
        "[dim]  Try /live for current market status, /global for global cues, "
        "/heat for breadth/sector heat, or ask about a specific NSE symbol.[/dim]"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Startup briefing  (runs once on interactive launch)
# ─────────────────────────────────────────────────────────────────────────────

def _greeting() -> str:
    h = _session_now().hour
    if h < 12:
        return "Good Morning"
    elif h < 17:
        return "Good Afternoon"
    return "Good Evening"


def _run_startup_briefing(agent, show_trace: bool) -> None:
    """Investigative morning/session briefing printed before the chat loop starts."""
    now  = _session_now()
    market_status = market_session_status(now)
    date_str = now.strftime("%A, %d %B %Y")
    time_str = now.strftime("%H:%M IST")

    # Determine session context
    if market_status.is_open:
        session_ctx = "live market"
    elif market_status.phase in {"pre_market", "pre_open"}:
        session_ctx = "pre-market"
    else:
        session_ctx = "market closed"

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
    console.print(f"[dim]  {market_status.status_label}[/dim]")
    console.print()

    briefing_prompt = f"""
You are starting a new trading session on {date_str} at {time_str} ({session_ctx}).
{market_status.status_label}
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


def _run_voice_briefing_panel() -> None:
    """Auto-generate (if needed) and display today's data-driven voice briefing.

    Reads from signal_log.csv + regime_detector + FII flows — no LLM call needed.
    Fast (< 1 second). Shown after the LLM startup briefing as a compact data panel.
    """
    try:
        from generate_voice_briefing import generate_briefing

        # Always regenerate — it's instant (reads CSVs, no LLM), idempotent
        result = generate_briefing(date_str=None, want_tts=False)
        script = result.get("script", "").strip()
        word_count = result.get("word_count", 0)
        date_label = result.get("date", datetime.now().strftime("%Y-%m-%d"))

        if not script:
            return

        console.print()
        console.rule(
            f"[bold cyan] 🎙  Voice Briefing  [/bold cyan]"
            f"[dim]  {date_label}  ·  {word_count} words [/dim]",
            style="cyan",
        )
        console.print()
        for para in script.split("\n\n"):
            para = para.strip()
            if para:
                console.print(f"  [white]{para}[/white]")
                console.print()
        console.rule(style="dim")
        console.print(
            f"  [dim]Tip: [/dim][blue]/voice[/blue][dim] to regenerate with audio  ·  "
            f"[/dim][blue]/voice script[/blue][dim] to view script[/dim]"
        )
        console.print()
    except Exception as exc:
        console.print(f"  [dim]  🎙  Voice briefing unavailable: {exc}[/dim]")
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
    if query.strip().lower().startswith(("/backtest", "/strategy-lab")):
        from terminal.backtest import handle_backtest_command
        _print_user(query)
        console.print(Markdown(handle_backtest_command(query)))
        return

    if query.strip().lower().startswith("/strength"):
        parts = query.strip().split()[1:]
        symbols = [re.sub(r"[^A-Za-z0-9&-]", "", p).upper() for p in parts]
        symbols = [s for s in symbols if s]
        _print_user(query)
        if not symbols:
            console.print("[dim]  Usage: /strength MANINDS THERMAX BAJAJCON[/dim]")
            return
        from terminal.tools import validate_strength_watchlist
        _print_strength_validation(validate_strength_watchlist(symbols))
        return

    _print_user(query)
    result = _run_with_spinner(agent, query, show_trace)
    _print_response(result)
    if show_trace:
        _print_trace(result.get("trace", []))


def _confirm_voice_query(transcript: str, normalized_query: str) -> dict:
    console.print(f"[yellow]  Transcript:[/yellow] {transcript}")
    console.print(f"[yellow]  Query:[/yellow] {normalized_query}")
    console.print("[dim]  Press Enter/y to continue, type edited query to replace, or n to cancel.[/dim]")
    reply = input("  Confirm voice query? ").strip()
    if reply.lower() in ("n", "no", "cancel", "q", "quit"):
        return {"ok": False, "reason": "cancelled by user"}
    if reply and reply.lower() not in ("y", "yes"):
        return {"ok": True, "normalized_query": reply}
    return {"ok": True, "normalized_query": normalized_query}


def _print_strength_validation(result: dict) -> None:
    """Render the no-assumption strength validator as a deterministic table."""
    if result.get("error"):
        console.print(f"[bold red]  ✗ {result['error']}[/bold red]")
        return

    console.print()
    console.rule("[bold cyan]Validated Multi-Factor Strength[/bold cyan]", style="dim cyan")
    console.print(f"[dim]Snapshot: {result.get('snapshot_date') or 'N/A'}[/dim]")
    console.print(f"[dim]{result.get('validation_rule', 'Missing evidence is not inferred.')}[/dim]")

    tbl = Table(box=box.SIMPLE_HEAD, header_style="bold cyan", expand=True)
    tbl.add_column("Symbol", style="bold white", no_wrap=True)
    tbl.add_column("Score", justify="right")
    tbl.add_column("CANSLIM", justify="right")
    tbl.add_column("RS%", justify="right")
    tbl.add_column("Fund", justify="right")
    tbl.add_column("Piotroski", justify="right")
    tbl.add_column("Risk")
    tbl.add_column("Verdict")
    tbl.add_column("Missing Evidence")

    for row in result.get("results", [])[:20]:
        score = row.get("strength_score")
        piot = row.get("piotroski_score")
        missing = row.get("missing_evidence") or []
        tbl.add_row(
            str(row.get("symbol") or "—"),
            f"{score:.1f}" if isinstance(score, (int, float)) else "—",
            str(row.get("can_slim_score") if row.get("can_slim_score") is not None else "—"),
            f"{row.get('rs_pct'):.2f}" if isinstance(row.get("rs_pct"), (int, float)) else "—",
            str(row.get("enhanced_fund_score") if row.get("enhanced_fund_score") is not None else "—"),
            f"{piot}/{row.get('piotroski_max')}" if piot is not None else "—",
            str(row.get("overall_forensic_risk") or "unknown"),
            str(row.get("verdict") or "—"),
            ", ".join(missing) if missing else "—",
        )

    console.print(tbl)
    console.print("[dim]  ━ Not investment advice. Research and learning only. ━[/dim]")
    console.print()


# ─────────────────────────────────────────────────────────────────────────────
# Interactive chat loop
# ─────────────────────────────────────────────────────────────────────────────

def _chat_loop(agent, show_trace: bool) -> None:
    global _mode, _followups

    from terminal.theme import get_theme, get_scale
    from voice_mode import VoiceModeState, handle_voice_mode_command, speak_answer_when_enabled
    _theme = get_theme()
    _scale = get_scale()
    voice_mode = VoiceModeState()

    session = PromptSession(
        history=InMemoryHistory(),
        completer=_AgentCompleter(),
        complete_while_typing=True,
        auto_suggest=AutoSuggestFromHistory(),
        style=_COMPLETER_STYLE,
    )

    console.print(f"[bold green]  ✓ Agent Adda ready[/bold green] [dim]{_session_clock_label()}[/dim] — type your question and press Enter")
    console.print("[dim]  Tip: /live  /eod  /auto  │  /model  │  /prompts  │  /ric  │  1·2·3 = follow-ups  │  /new  │  /help  │  exit[/dim]")
    console.print()

    # Start background alert auto-display thread.
    # Uses patch_stdout so alerts print above the active input line automatically.
    _start_alert_autodisplay()

    while True:
        # ── Restart auto-display + drain any queued alerts before prompt ─
        _start_alert_autodisplay()
        _check_monitor_alerts()

        # Per-iteration report-after flags (set by /analyze and /search)
        _analyze_report_after = None
        _search_report_after  = None

        try:
            with _pt_patch_stdout(raw=True):
                raw = session.prompt(
                    _build_prompt(agent),
                    bottom_toolbar=_bottom_toolbar_text,
                    refresh_interval=1,
                )
        except KeyboardInterrupt:
            console.print()
            continue
        except EOFError:
            break

        text = raw.strip()
        if not text:
            continue

        # Stop auto-display thread while processing (avoids interleaved output)
        _alert_autodisplay_stop.set()

        # ── Exit ──────────────────────────────────────────────────────
        if text.lower() in ("exit", "quit", "q", ":q"):
            break

        if _is_plain_greeting(text):
            _print_user(text)
            _print_greeting_response()
            continue

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

        if text.lower() == "/model" or text.lower().startswith("/model "):
            _print_model_command_result(_handle_model_command(agent, text))
            continue

        # ── Utility commands ───────────────────────────────────────────
        if text.lower() in ("/help", "?", "/h") or text.lower().startswith("/help "):
            from terminal.help import print_help as _ph
            _ph(console, text[5:].strip() if text.lower().startswith("/help ") else "")
            continue

        if text.lower() == "/commands" or text.lower().startswith("/commands "):
            _kw = text[9:].strip() if text.lower().startswith("/commands ") else ""
            _print_commands(_kw)
            continue
        if text.lower() in ("/clear", "clear", "cls"):
            _followups = []
            os.system("clear")
            print_banner()
            continue

        if text.lower().startswith("/strength"):
            parts = text.split()[1:]
            symbols = [re.sub(r"[^A-Za-z0-9&-]", "", p).upper() for p in parts]
            symbols = [s for s in symbols if s]
            if not symbols:
                console.print("[dim]  Usage: /strength MANINDS THERMAX BAJAJCON[/dim]")
                continue
            from terminal.tools import validate_strength_watchlist
            _print_user(text)
            result = validate_strength_watchlist(symbols)
            _print_strength_validation(result)
            _separator()
            continue

        if text.lower().startswith(("/backtest", "/strategy-lab")):
            from terminal.backtest import handle_backtest_command
            _print_user(text)
            console.print(Markdown(handle_backtest_command(text)))
            _separator()
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

        # ── /us and /global readthrough: deterministic US/global layer ─
        if _handle_us_global_command(text):
            _separator()
            continue

        # ── /dashboard: comprehensive current-market dashboard + narrative ─
        if text.lower() in ("/dashboard", "/dash") or text.lower().startswith(("/dashboard ", "/dash ")):
            topic = text.split(maxsplit=1)[1].strip() if len(text.split(maxsplit=1)) > 1 else ""
            try:
                _run_market_dashboard_live(topic)
            finally:
                console.print("[dim]  Dashboard closed.[/dim]")
            continue

        # ── /monitor-report: export monitor status + recent alerts as a report ──
        if text.lower().startswith("/monitor-report"):
            parts    = text.split()
            _mon_fmt = parts[1].lower() if len(parts) > 1 and parts[1].lower() in ("html", "pdf", "md") else "html"
            try:
                from terminal.monitor import get_monitor as _get_mon
                _mon      = _get_mon()
                _workers  = _mon.status()
                _events   = _mon.drain_alerts() if hasattr(_mon, "drain_alerts") else []
            except Exception as _me:
                _workers, _events = [], []

            _mon_lines = ["# Monitor Status Report\n"]
            if _workers:
                _mon_lines.append("## Active Monitors\n")
                _mon_lines.append("| Strategy | Symbol | TF | Status | Triggered |\n")
                _mon_lines.append("|---|---|---|---|---|\n")
                for _w in _workers:
                    _mon_lines.append(
                        f"| {_w.get('strategy','?')} | {_w.get('symbol','?')} | "
                        f"{_w.get('tf','?')} | {_w.get('status','?')} | "
                        f"{_w.get('triggered',0)} |\n"
                    )
            else:
                _mon_lines.append("*No active monitors.*\n")

            if _events:
                _mon_lines.append("\n## Recent Alerts\n")
                for _ev in _events[-50:]:
                    _ts  = _ev.get("timestamp", "")[:19]
                    _sym = _ev.get("symbol", "?")
                    _sig = _ev.get("signal", "?")
                    _pr  = _ev.get("price", "")
                    _mon_lines.append(f"- **{_ts}** `{_sym}` — {_sig}" + (f" @ {_pr}" if _pr else "") + "\n")
            else:
                _mon_lines.append("\n*No recent alerts.*\n")

            _mon_md = "".join(_mon_lines)
            _auto_export_report(_mon_md, "research", "MONITOR", _mon_fmt)
            continue

        # ── /monitor: background alert workers ────────────────────────
        if text.lower().startswith("/monitor"):
            parts = text.split()
            _handle_monitor_command(parts)
            continue

        # ── /alert: watchlist price/RSI alerts ────────────────────────
        if text.lower().startswith("/alert"):
            parts = text.split()
            sub = parts[1].lower() if len(parts) > 1 else "list"

            if sub == "list":
                from terminal.alerts import list_alerts
                from rich.table import Table as _Table
                alerts = list_alerts()
                if not alerts:
                    console.print("[dim]  No alerts set. Try: /alert add NIFTY rsi above 70 in 15min[/dim]")
                else:
                    tbl = _Table(title="🔔 Watchlist Alerts", show_header=True, header_style=_theme["header"])
                    tbl.add_column("ID",      style="dim",         width=4)
                    tbl.add_column("Symbol",  style="bold yellow")
                    tbl.add_column("Trigger", style="cyan")
                    tbl.add_column("Value",   style="green",       justify="right")
                    tbl.add_column("TF",      style="magenta",     width=6)
                    tbl.add_column("Note",    style="dim")
                    for a in alerts:
                        tbl.add_row(
                            str(a["id"]), a["symbol"], a["trigger"],
                            str(a["value"]) if a.get("value") else "—",
                            a.get("tf", "1d"),
                            a.get("note", ""),
                        )
                    console.print(tbl)
                continue

            elif sub == "add" and len(parts) >= 3:
                # Use LLM to parse natural language; fall back to positional parse.
                # Examples:
                #   /alert add NIFTY rsi above 70 in 15min
                #   /alert add RELIANCE breakout
                #   /alert add TCS price above 3500
                raw_input = " ".join(parts[2:])   # everything after "/alert add"

                console.print("[dim]  Parsing alert…[/dim]", end="\r")
                parsed = _parse_alert_with_llm(raw_input)

                if parsed:
                    sym     = parsed["symbol"].upper()
                    trigger = parsed["trigger"]
                    val     = float(parsed.get("value") or 0.0)
                    tf      = parsed.get("tf") or "1d"
                    note    = parsed.get("note") or ""
                else:
                    # Positional fallback: SYMBOL trigger [value] [note…]
                    sym     = parts[2].upper()
                    trigger = parts[3].lower() if len(parts) > 3 else ""
                    _no_val = {"breakout", "orb", "intraday", "intraday_breakout"}
                    if not trigger:
                        console.print("[red]  Usage: /alert add SYMBOL trigger [value][/red]")
                        continue
                    if trigger in _no_val:
                        val, tf, note = 0.0, "1d", " ".join(parts[4:]) if len(parts) > 4 else ""
                    elif len(parts) >= 5:
                        try:
                            val = float(parts[4])
                        except ValueError:
                            console.print(f"[red]  Value must be a number for '{trigger}'[/red]")
                            continue
                        tf   = "1d"
                        note = " ".join(parts[5:]) if len(parts) > 5 else ""
                    else:
                        console.print(f"[red]  Missing value for trigger '{trigger}'[/red]")
                        continue

                from terminal.alerts import add_alert
                try:
                    alert   = add_alert(sym, trigger, val, note, tf)
                    tf_str  = f" [{alert['tf']}]" if alert.get("tf") and alert["tf"] != "1d" else ""
                    val_str = f" {alert['value']}" if alert["value"] else ""
                    console.print(
                        f"[green]  ✅ Alert #{alert['id']} added: "
                        f"{sym} {alert['trigger']}{val_str}{tf_str}[/green]"
                    )
                    if parsed:
                        console.print(f"[dim]  (parsed via LLM — tf={alert['tf']}, note='{note}')[/dim]")
                except ValueError as e:
                    console.print(f"[red]  {e}[/red]")
                continue

            elif sub == "del" and len(parts) >= 3:
                try:
                    aid = int(parts[2])
                except ValueError:
                    console.print("[red]  Alert ID must be an integer[/red]")
                    continue
                from terminal.alerts import delete_alert
                ok = delete_alert(aid)
                if ok:
                    console.print(f"[green]  ✅ Alert #{aid} deleted[/green]")
                else:
                    console.print(f"[red]  Alert #{aid} not found[/red]")
                continue

            elif sub == "check":
                console.print("[dim]  Checking alerts against live prices...[/dim]")
                from terminal.alerts import check_alerts
                triggered = check_alerts()
                if not triggered:
                    console.print("[dim]  No alerts triggered.[/dim]")
                else:
                    for t in triggered:
                        console.print(f"[bold yellow]  🔔 {t['symbol']} — {t['trigger']} {t['value']} (current: {t.get('triggered_value','?')})[/bold yellow]")
                continue

            elif sub == "monitor":
                import threading
                import time as _time
                import types as _types
                if not hasattr(_chat_loop, "_ns"):
                    _chat_loop._ns = _types.SimpleNamespace()
                _ns = _chat_loop._ns
                _stop_monitor = getattr(_ns, "_alert_monitor_stop", None)
                if _stop_monitor is not None and not _stop_monitor.is_set():
                    _stop_monitor.set()
                    _ns._alert_monitor_stop = None
                    console.print("[dim]  🔕 Alert monitor stopped.[/dim]")
                else:
                    stop_evt = threading.Event()
                    _ns._alert_monitor_stop = stop_evt

                    def _monitor_loop(stop):
                        from terminal.alerts import check_alerts as _ca
                        import datetime as _dt
                        while not stop.is_set():
                            now = _dt.datetime.now()
                            if now.weekday() < 5 and _dt.time(9, 15) <= now.time() <= _dt.time(15, 30):
                                _ca()
                            stop.wait(300)  # poll every 5 min

                    t = threading.Thread(target=_monitor_loop, args=(stop_evt,), daemon=True)
                    t.start()
                    console.print("[green]  🔔 Alert monitor started (polling every 5 min, market hours).[/green]")
                continue

            else:
                console.print(
                    "[dim]  Usage:[/dim]\n"
                    "  [cyan]/alert list[/cyan]\n"
                    "  [cyan]/alert add SYMBOL breakout[/cyan]           [dim]← 15m ORB auto-detect[/dim]\n"
                    "  [cyan]/alert add SYMBOL price_above 1500[/cyan]   [dim]← price trigger[/dim]\n"
                    "  [cyan]/alert add SYMBOL breakout_above 1580[/cyan][dim]← 15m break above level[/dim]\n"
                    "  [cyan]/alert add SYMBOL rsi_above 70[/cyan]       [dim]← RSI trigger[/dim]\n"
                    "  [cyan]/alert del ID | /alert check | /alert monitor[/cyan]"
                )
                continue


        if text.lower().startswith("/ric"):
            parts = text.split(maxsplit=2)
            if len(parts) == 1:
                _print_ric_library()
            else:
                ric_key  = parts[1].lower()
                ric_arg  = parts[2] if len(parts) > 2 else ""
                # Optional format suffix: /ric sherlock RELIANCE pdf
                _ric_fmt = ""
                _arg_toks = ric_arg.split()
                if _arg_toks and _arg_toks[-1].lower() in ("html", "pdf", "md"):
                    _ric_fmt = _arg_toks[-1].lower()
                    ric_arg  = " ".join(_arg_toks[:-1])
                _run_ric(agent, ric_key, ric_arg, show_trace, output_format=_ric_fmt)
            continue

        # ── /context: show session summary ────────────────────────────
        if text.lower() in ("/context", "/session", "/history"):
            _print_context_summary(agent)
            continue

        # ── /refresh — run daily data refresh pipeline async ──────────────
        if text.lower().startswith("/refresh"):
            import subprocess as _sp, threading as _thr, os as _os
            parts = text.split()
            sub   = parts[1].lower() if len(parts) > 1 else "snapshot"

            _refresh_proc = getattr(_chat_loop, "_refresh_proc", None)

            if sub == "status":
                if _refresh_proc and _refresh_proc.poll() is None:
                    console.print(f"  [yellow]⏳ Refresh running (PID {_refresh_proc.pid})…[/yellow]")
                elif _refresh_proc:
                    rc = _refresh_proc.returncode
                    icon = "✅" if rc == 0 else "❌"
                    console.print(f"  {icon} Last refresh exited with code {rc}")
                else:
                    console.print("  [dim]No refresh has been run this session.[/dim]")
                continue

            if sub == "stop":
                if _refresh_proc and _refresh_proc.poll() is None:
                    _refresh_proc.terminate()
                    console.print("  [yellow]⏹ Refresh process terminated.[/yellow]")
                else:
                    console.print("  [dim]No refresh process running.[/dim]")
                continue

            # Already running?
            if _refresh_proc and _refresh_proc.poll() is None:
                console.print(f"  [yellow]⏳ Refresh already running (PID {_refresh_proc.pid}). Use /refresh status or /refresh stop.[/yellow]")
                continue

            # Build command
            _py = str(__import__('pathlib').Path(__file__).resolve().parent / ".venv" / "bin" / "python3")
            _script = str(__import__('pathlib').Path(__file__).resolve().parent / "daily_refresh.py")
            if sub in ("snapshot", "snap"):
                cmd = [_py, _script, "--skip-analysis", "--skip-aux"]
                mode_label = "snapshot only (fast ~1–2 min)"
            elif sub == "live":
                cmd = [_py, _script, "--live-only"]
                mode_label = "live prices only (~30s)"
            elif sub == "full":
                cmd = [_py, _script]
                mode_label = "full pipeline (R + analysis + snapshot, ~10–15 min)"
            elif sub == "analysis":
                cmd = [_py, _script, "--skip-aux"]
                mode_label = "analysis + snapshot (skips aux fetch)"
            else:
                console.print(f"  [red]Unknown refresh mode '{sub}'. Use: snapshot · live · full · analysis · status · stop[/red]")
                continue

            _env = {**_os.environ, "PROJECT_ROOT": str(__import__('pathlib').Path(__file__).resolve().parent)}
            log_path = __import__('pathlib').Path(__file__).resolve().parent / "data" / "refresh.log"

            console.print(f"\n  [bold cyan]🔄 Starting refresh[/bold cyan] — {mode_label}")
            console.print(f"  [dim]Log: {log_path}[/dim]")
            console.print(f"  [dim]Use /refresh status to check · /refresh stop to cancel[/dim]\n")

            _log_file = open(log_path, "w")
            proc = _sp.Popen(cmd, stdout=_log_file, stderr=_sp.STDOUT, env=_env)
            _chat_loop._refresh_proc = proc

            # Background thread — use sys.__stdout__ directly (avoid Rich console threading issues)
            def _watch(p, lf, label, lp):
                try:
                    p.wait()
                finally:
                    try:
                        lf.close()
                    except Exception:
                        pass
                rc = p.returncode
                icon = "✅" if rc == 0 else "❌"
                msg = f"\n  {icon} Refresh complete ({label}) — exit code {rc}\n  Log: {lp}\n"
                try:
                    import sys as _sys
                    (_sys.__stdout__ or _sys.stdout).write(msg)
                    (_sys.__stdout__ or _sys.stdout).flush()
                except Exception:
                    pass
            _thr.Thread(target=_watch, args=(proc, _log_file, mode_label, str(log_path)), daemon=True).start()
            continue

        # ── /export — export session to HTML/PDF ──────────────────────
        if text.lower().startswith("/export"):
            parts = text.split()
            fmt = parts[1].lower() if len(parts) > 1 and parts[1].lower() in ("html", "pdf") else "html"
            sym = parts[2].upper() if len(parts) > 2 and parts[2].lower() not in ("html", "pdf") else ""
            # If first arg is a symbol (not html/pdf), shift
            if len(parts) > 1 and parts[1].lower() not in ("html", "pdf"):
                sym = parts[1].upper()
                fmt = "html"

            console.print(f"[dim]  Exporting session as {fmt.upper()}...[/dim]")
            try:
                from terminal.export import export_session_html, export_session_pdf
                export_msgs = list(agent._history)

                if fmt == "pdf":
                    fpath = export_session_pdf(export_msgs, symbol=sym)
                else:
                    fpath = export_session_html(export_msgs, symbol=sym)

                console.print(f"[green]  ✅ Session exported:[/green] {fpath}")
                try:
                    import subprocess as _sp
                    _sp.run(["open", fpath], check=False)
                except Exception:
                    pass
            except Exception as _e:
                console.print(f"[bold red]  ❌ Export error: {_e}[/bold red]")
                import traceback; traceback.print_exc()
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
            text, status = _rewrite_scan_command(text)
            console.print(f"[dim]  → {status}[/dim]")

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
                    chart_out = render_chart(sym, tf, indicators, width=_scale["chart_width"], height=_scale["chart_height"])
                    import sys as _sys
                    _sys.stdout.write("\n" + chart_out + "\n")
                    _sys.stdout.flush()
                except Exception as _e:
                    console.print(f"[bold red]  ❌  Chart error: {_e}[/bold red]")
                text = (
                    f"Give a brief technical summary for {sym} chart ({tf}): "
                    f"trend direction, key support/resistance levels, RSI reading, "
                    f"MACD status, and what to watch for next."
                )

        # ── /company-index <symbol> [options] — company website/document index ──────
        if text.lower().startswith("/company-index"):
            args_text = text[len("/company-index"):].strip()
            if not args_text:
                console.print(
                    "[dim]  Usage: /company-index SYMBOL [--include-documents] [--max-pages N] "
                    "[--document-limit N] [--seed-sitemap] [--respect-robots] [--adapter auto|none|dmart][/dim]"
                )
                continue
            try:
                from company_index_command import run_company_index_from_args

                console.print(f"[dim]  → Company Index: /company-index {args_text}[/dim]")
                index_result = run_company_index_from_args(args_text)
                crawl = index_result.get("crawl", {})
                console.print(
                    "[green]  ✅ Company index completed[/green]\n"
                    f"[dim]    Symbol: {index_result.get('symbol')}[/dim]\n"
                    f"[dim]    Website: {index_result.get('website')}[/dim]\n"
                    f"[dim]    Pages indexed: {crawl.get('pages_indexed', 0)} / seen {crawl.get('pages_seen', 0)}[/dim]\n"
                    f"[dim]    HTML documents found: {crawl.get('documents_found', 0)}[/dim]\n"
                    f"[dim]    Adapter: {index_result.get('adapter') or 'none'}[/dim]\n"
                    f"[dim]    Adapter documents found: {index_result.get('adapter_documents_found', 0)}[/dim]\n"
                    f"[dim]    Downloaded: {index_result.get('documents_downloaded', 0)}  "
                    f"Cached: {index_result.get('documents_cached', 0)}  "
                    f"Errors: {len(index_result.get('document_errors', []))}[/dim]\n"
                    f"[dim]    DB: {index_result.get('db_path')}[/dim]\n"
                    f"[dim]    Next: /company-xray {index_result.get('symbol')}[/dim]"
                )
            except Exception as exc:
                console.print(f"[bold red]  ❌ Company index failed: {exc}[/bold red]")
            continue

        # ── /company-xray <symbol> [--strict] [--refresh] — Company + Sector X-Ray ──────
        if text.lower().startswith("/company-xray"):
            args_text = text[len("/company-xray"):].strip()
            if not args_text:
                console.print("[dim]  Usage: /company-xray SYMBOL [--strict] [--refresh][/dim]")
                continue
            try:
                from company_xray_command import run_company_xray_from_args

                console.print(f"[dim]  → Company X-Ray: /company-xray {args_text}[/dim]")
                xray_result = run_company_xray_from_args(args_text)
                coverage = xray_result.get("coverage_summary", {})
                gaps = xray_result.get("known_gaps", [])
                strict_failures = xray_result.get("strict_failures", [])
                console.print(
                    f"[green]  ✅ Company X-Ray {xray_result.get('status')}[/green]\n"
                    f"[dim]    Symbol: {xray_result.get('symbol')}[/dim]\n"
                    f"[dim]    Official evidence: {coverage.get('official_evidence', 'n/a')}[/dim]\n"
                    f"[dim]    Business model: {coverage.get('business_model', 'n/a')}[/dim]\n"
                    f"[dim]    Sector data: {coverage.get('sector_data', 'n/a')}[/dim]\n"
                    f"[dim]    Market share: {coverage.get('market_share', 'n/a')}[/dim]\n"
                    f"[dim]    Markdown: {xray_result.get('report_markdown_path')}[/dim]\n"
                    f"[dim]    HTML: {xray_result.get('report_html_path')}[/dim]\n"
                    f"[dim]    Known gaps: {', '.join(gaps) if gaps else 'none'}[/dim]\n"
                    f"[dim]    Strict gaps: {', '.join(strict_failures) if strict_failures else 'none'}[/dim]\n"
                    f"[dim]    {xray_result.get('disclaimer')}[/dim]"
                )
            except Exception as exc:
                console.print(f"[bold red]  ❌ Company X-Ray failed: {exc}[/bold red]")
            continue

        # ── /search <symbol> [vertical/context] [pdf|html|md] — deep search engine ──────
        if text.lower().startswith("/search"):
            parts   = text.split()
            sym     = parts[1].upper() if len(parts) > 1 else "RELIANCE"

            # Parse optional trailing format: /search RELIANCE pdf
            _search_fmt = ""
            _remaining_parts = parts[2:]
            if _remaining_parts and _remaining_parts[-1].lower() in ("html", "pdf", "md"):
                _search_fmt = _remaining_parts[-1].lower()
                _remaining_parts = _remaining_parts[:-1]
            context = " ".join(_remaining_parts) if _remaining_parts else ""

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

            _eff_search_fmt = _search_fmt or "html"
            _search_fmt_note = f" → saving {_search_fmt.upper()} report" if _search_fmt else " → saving HTML report"
            if forced_verts:
                vert_str = ", ".join(forced_verts)
                console.print(f"[dim]  → Deep Search: [bold]{sym}[/bold] — verticals: {vert_str}{_search_fmt_note}[/dim]")
                text = (
                    f"Run deep_search for {sym} using verticals {forced_verts} with context '{ctx_desc}'. "
                    f"Present all results clearly — include dates, URLs, and key insights for each vertical."
                )
            else:
                console.print(f"[dim]  → Deep Search: [bold]{sym}[/bold] — all verticals{_search_fmt_note}[/dim]")
                text = (
                    f"Run a comprehensive deep search for {sym}. "
                    f"Use deep_search with all default verticals. "
                    f"Context: '{ctx_desc or 'full overview'}'. "
                    f"Present results section-by-section: "
                    f"NSE announcements, corporate actions, insider trades, "
                    f"shareholding, analyst targets, concalls, sector news. "
                    f"Include dates, real URLs, and actionable insights."
                )
            # Mark for post-response export — default to html when no format given
            _search_report_after = (sym, "research", _eff_search_fmt)

        # ── /report — first-class report generation ──────────────────────
        # PG: Generates PDF, HTML, or Markdown reports from prebuilt analysis types.
        #     sector-rotation and stage2 are DATA-DIRECT (no LLM, instant from DB).
        elif text.lower().startswith("/report"):
            parts = text.split()
            # Parse: /report [type] [symbol] [format]
            # Examples: /report technical RELIANCE pdf
            #           /report sector-rotation html
            #           /report stage2
            _preset_types  = {"sector-rotation", "stage2"}
            _report_types  = {"technical", "fundamental", "forensic", "research",
                              "intraday", "canslim", "ric", "sector"} | _preset_types

            if len(parts) == 1:
                console.print(
                    "[dim]  Usage: /report <type> [symbol] [format][/dim]\n"
                    "[dim]  ─── Stock Reports (LLM-generated) ──────────────────────────────[/dim]\n"
                    "[dim]  Types:  technical | fundamental | forensic | research[/dim]\n"
                    "[dim]          intraday | canslim | ric | sector[/dim]\n"
                    "[dim]  ─── Market Reports (Instant — direct from DB) ────────────────[/dim]\n"
                    "[dim]  Types:  sector-rotation   → Full sector breadth & rotation dashboard[/dim]\n"
                    "[dim]          stage2            → Stage 2 universe tracker (top 30 + new entrants)[/dim]\n"
                    "[dim]  ─── Format ──────────────────────────────────────────────────────[/dim]\n"
                    "[dim]  Format: html (default) | pdf | md[/dim]\n"
                    "[dim]  ─── Examples ────────────────────────────────────────────────────[/dim]\n"
                    "[dim]    /report sector-rotation           → HTML (instant)[/dim]\n"
                    "[dim]    /report sector-rotation pdf       → PDF  (instant)[/dim]\n"
                    "[dim]    /report stage2                    → HTML (instant)[/dim]\n"
                    "[dim]    /report stage2 md                 → Markdown[/dim]\n"
                    "[dim]    /report technical RELIANCE        → LLM analysis → HTML[/dim]\n"
                    "[dim]    /report fundamental TCS pdf       → LLM analysis → PDF[/dim]\n"
                    "[dim]    /report forensic INFY md[/dim]\n"
                    "[dim]    /report research HDFCBANK[/dim]\n"
                    "[dim]    /report canslim TATAMOTORS html[/dim]\n"
                    "[dim]    /report ric ADANIENT pdf[/dim]\n"
                    "[dim]    /report RELIANCE              (shortcut: research + html)[/dim]"
                )
                continue

            # Parse arguments
            rpt_type = "research"
            rpt_sym  = ""
            rpt_fmt  = "html"

            if parts[1].lower() in _report_types:
                rpt_type = parts[1].lower()
                remaining = parts[2:]
                # For preset types, remaining is just [format]; for others [symbol] [format]
                if rpt_type in _preset_types:
                    if remaining and remaining[0].lower() in ("html", "pdf", "md"):
                        rpt_fmt = remaining[0].lower()
                else:
                    if remaining:
                        rpt_sym = remaining[0].upper()
                    if len(remaining) > 1 and remaining[1].lower() in ("html", "pdf", "md"):
                        rpt_fmt = remaining[1].lower()
            else:
                # parts[1] is the symbol (default type = research)
                rpt_sym = parts[1].upper()
                if len(parts) > 2 and parts[2].lower() in ("html", "pdf", "md"):
                    rpt_fmt = parts[2].lower()
                elif len(parts) > 2 and parts[2].lower() in _report_types:
                    rpt_type = parts[2].lower()
                    if len(parts) > 3 and parts[3].lower() in ("html", "pdf", "md"):
                        rpt_fmt = parts[3].lower()

            # ── Preset reports: data-direct (no LLM) ─────────────────────
            if rpt_type in _preset_types:
                console.print(
                    f"[dim]  → [bold]{rpt_type.upper()}[/bold] Report — "
                    f"pulling from DB snapshot... (no LLM needed)[/dim]"
                )
                try:
                    from terminal.reports import generate_preset_report as _gen_preset
                    _r = _gen_preset(rpt_type, rpt_fmt)
                    if _r.get("success"):
                        console.print(
                            f"  [bold green]✅  Report saved![/bold green]  "
                            f"[cyan]{_r['path']}[/cyan]"
                        )
                        console.print(f"  [dim]{_r.get('note','')}[/dim]")
                        import subprocess
                        subprocess.Popen(["open", _r["path"]])
                    else:
                        console.print(f"  [bold red]❌  {_r.get('note','Failed')}[/bold red]")
                except Exception as _e:
                    console.print(f"  [bold red]❌  Preset report error: {_e}[/bold red]")
                _separator()
                continue  # done — no LLM call needed

            # ── LLM-assisted stock reports ────────────────────────────────
            if not rpt_sym:
                console.print("[bold red]  ❌ Please specify a symbol: /report {type} SYMBOL [format][/bold red]")
                continue

            console.print(
                f"[dim]  → Generating [bold]{rpt_type.upper()}[/bold] report for "
                f"[bold]{rpt_sym}[/bold] as {rpt_fmt.upper()}[/dim]"
            )

            from terminal.reports import get_report_prompt
            text = get_report_prompt(rpt_type, rpt_sym, rpt_fmt)
            # Direct export after LLM responds — bypasses fragile tool-call path
            _analyze_report_after = (rpt_sym, rpt_type, rpt_fmt)

        # ── /analyze <source> [pdf|html|md] — document analysis or deep stock 360° ──────
        # PG: First-class document + stock analysis. Auto-detects input type:
        #     URL → scrape web page / PDF;  .pdf/.docx → read local file;
        #     stock symbol → full 360° analysis (technical + fundamental + forensic + news + sentiment)
        #     Optional format suffix: /analyze RELIANCE pdf  → run analysis AND save report
        elif text.lower().startswith("/analyze"):
            parts = text.split(maxsplit=1)
            arg   = parts[1].strip() if len(parts) > 1 else ""

            # Parse optional trailing format: /analyze RELIANCE pdf
            _analyze_fmt = ""
            _arg_toks = arg.split()
            if _arg_toks and _arg_toks[-1].lower() in ("html", "pdf", "md"):
                _analyze_fmt = _arg_toks[-1].lower()
                arg = " ".join(_arg_toks[:-1]).strip()

            if not arg:
                console.print(
                    "[dim]  Usage: /analyze <file.pdf | file.docx | https://... | SYMBOL> [html|pdf|md][/dim]\n"
                    "[dim]  Examples:[/dim]\n"
                    "[dim]    /analyze ~/Downloads/annual_report.pdf[/dim]\n"
                    "[dim]    /analyze https://www.bseindia.com/results/2026.pdf[/dim]\n"
                    "[dim]    /analyze concall_transcript.docx[/dim]\n"
                    "[dim]    /analyze RELIANCE[/dim]\n"
                    "[dim]    /analyze RELIANCE pdf       ← run AND save as PDF report[/dim]"
                )
                continue

            _arg_lower = arg.lower()
            _is_url  = _arg_lower.startswith(("http://", "https://"))
            _is_file = any(_arg_lower.endswith(ext) for ext in
                          (".pdf", ".docx", ".doc", ".txt", ".csv", ".md", ".xlsx"))
            _has_path = ("/" in arg or "\\" in arg or "~" in arg)

            if _is_url or _is_file or _has_path:
                # ── Document analysis mode ────────────────────────────────
                source_label = arg if len(arg) < 60 else arg[:57] + "..."
                _doc_export_note = f" → saving {_analyze_fmt.upper()} report" if _analyze_fmt else ""
                console.print(f"[dim]  → Document Analysis: [bold]{source_label}[/bold]{_doc_export_note}[/dim]")
                _analyze_sym = Path(arg).stem.split(".")[0][:20] if not _is_url else "document"
                text = (
                    f"Use the analyze_document tool with source='{arg}'. "
                    f"Read the full document and provide:\n"
                    f"1. **Document Summary** — what is this document about? Key topics covered.\n"
                    f"2. **Key Findings** — the most important data points, numbers, and conclusions.\n"
                    f"3. **Critical Details** — any financial figures, dates, targets, risks, or action items.\n"
                    f"4. **Analysis & Opinion** — your expert interpretation of the document's implications.\n"
                    f"If this is a financial document (annual report, concall transcript, results), "
                    f"also evaluate: revenue/profit trends, management commentary, guidance changes, "
                    f"risk factors, and investment implications.\n"
                    f"Present the analysis in a well-structured format with clear section headers."
                )
                # Documents: export only if explicit format given
                _analyze_report_after = (_analyze_sym, "research", _analyze_fmt) if _analyze_fmt else None
            else:
                # ── Stock deep 360° analysis mode ─────────────────────────
                _analyze_sym = arg.upper().split()[0]
                _eff_fmt = _analyze_fmt or "html"  # default to html for stock analysis
                _fmt_note = f" → saving {_analyze_fmt.upper()} report" if _analyze_fmt else " → saving HTML report"
                console.print(f"[dim]  → 360° Deep Analysis: [bold]{_analyze_sym}[/bold] "
                               f"(technical + fundamental + forensic + news + sentiment){_fmt_note}[/dim]")
                text = (
                    f"Perform a comprehensive 360° analysis of {_analyze_sym}. Execute these tools IN ORDER:\n\n"
                    f"1. **get_technical_setup** for {_analyze_sym} — trend, RSI, MACD, support/resistance, stage\n"
                    f"2. **comprehensive_stock_research** for {_analyze_sym} — fundamentals, valuations, peer comparison\n"
                    f"3. **run_forensic_analysis** for {_analyze_sym} — Beneish M-score, Piotroski F-score, Altman Z'-score\n"
                    f"4. **search_latest_catalysts** for {_analyze_sym} — latest news, read top 2 articles for sentiment\n"
                    f"5. **get_sector_context** for {_analyze_sym} — sector rotation status and relative strength\n"
                    f"6. **deep_search** for {_analyze_sym} verticals=['shareholding','insider_trades','analyst_targets'] — institutional & insider activity\n\n"
                    f"Then synthesize ALL results into a unified report with these sections:\n"
                    f"• **Executive Summary** — 3-line bull/bear verdict with conviction level\n"
                    f"• **Technical Position** — trend, key levels, stage, momentum signals\n"
                    f"• **Fundamental Quality** — revenue/profit growth, margins, ROE, debt, valuations\n"
                    f"• **Financial Health** — forensic scores (Beneish, Piotroski, Altman) with flags\n"
                    f"• **Institutional & Insider Activity** — FII/DII changes, promoter moves, bulk deals\n"
                    f"• **News & Sentiment** — recent catalysts, management commentary, market sentiment\n"
                    f"• **Risk Factors** — top 3-5 risks specific to this stock\n"
                    f"• **Investment Verdict** — BUY/HOLD/AVOID with entry zone, target, stop-loss, timeframe\n\n"
                    f"Use data from ALL tool calls. Be specific with numbers, dates, and levels."
                )
                # Stock analysis: always export HTML (or specified format)
                _analyze_report_after = (_analyze_sym, "research", _eff_fmt)

        # ── /canslim <symbol> — William O'Neil CANSLIM analysis ──────────
        # PG: First-class CANSLIM growth quality evaluation framework.
        #     Uses existing tools to evaluate all 7 CANSLIM criteria.
        elif text.lower().startswith("/canslim"):
            parts = text.split()
            sym   = parts[1].upper() if len(parts) > 1 else ""

            if not sym:
                console.print(
                    "[dim]  Usage: /canslim <SYMBOL>[/dim]\n"
                    "[dim]  William O'Neil's 7-point growth stock quality framework:[/dim]\n"
                    "[dim]    C = Current quarterly earnings (acceleration)[/dim]\n"
                    "[dim]    A = Annual earnings growth (25%+ for 3-5 years)[/dim]\n"
                    "[dim]    N = New product/management/price high (catalyst)[/dim]\n"
                    "[dim]    S = Supply & demand (shares outstanding, volume)[/dim]\n"
                    "[dim]    L = Leader or laggard? (relative strength vs market)[/dim]\n"
                    "[dim]    I = Institutional sponsorship (FII/DII/MF ownership quality)[/dim]\n"
                    "[dim]    M = Market direction (bull/bear/correction regime)[/dim]"
                )
                continue

            console.print(f"[dim]  → CANSLIM Analysis: [bold]{sym}[/bold] (William O'Neil 7-point framework)[/dim]")
            text = (
                f"Perform a comprehensive CANSLIM analysis for {sym}. Call these tools:\n\n"
                f"1. **comprehensive_stock_research** for {sym} — quarterly/annual earnings, revenue trends, margins\n"
                f"2. **get_technical_setup** for {sym} — relative strength, price action, stage, 52W high proximity\n"
                f"3. **search_latest_catalysts** for {sym} — new products, management changes, recent catalysts\n"
                f"4. **deep_search** for {sym} verticals=['shareholding','insider_trades','mutual_fund_holdings'] — institutional ownership\n"
                f"5. **get_sector_context** for {sym} — market regime and sector rotation status\n\n"
                f"Then evaluate EACH of the 7 CANSLIM criteria with a PASS ✅ / PARTIAL 🟡 / FAIL ❌ rating:\n\n"
                f"**C — Current Quarterly Earnings:**\n"
                f"  - Is latest quarter EPS growth ≥ 25% YoY? Accelerating vs prior quarters?\n"
                f"  - Revenue growth accompanying earnings growth? (top-line confirmation)\n\n"
                f"**A — Annual Earnings Growth:**\n"
                f"  - Is annual EPS growth ≥ 25% for at least 3 consecutive years?\n"
                f"  - Is ROE ≥ 17%? Stable or improving margins?\n\n"
                f"**N — New Products/Management/Price Highs:**\n"
                f"  - Any new product launches, business pivots, or management changes?\n"
                f"  - Is the stock near or making new 52-week/all-time highs?\n\n"
                f"**S — Supply & Demand:**\n"
                f"  - Shares outstanding (prefer < 500 Cr for mid/small caps)?\n"
                f"  - Volume pattern: is volume expanding on up-days vs down-days?\n"
                f"  - Float tightness (promoter holding > 50% = positive)\n\n"
                f"**L — Leader or Laggard:**\n"
                f"  - Relative Strength ranking vs Nifty 500 (top 20% = leader)\n"
                f"  - Is the stock outperforming its sector and the market?\n"
                f"  - Stage analysis: is it in Stage 2 uptrend?\n\n"
                f"**I — Institutional Sponsorship:**\n"
                f"  - Are quality FIIs/DIIs/MFs increasing their stakes (last 2-3 quarters)?\n"
                f"  - Number of institutional holders growing?\n"
                f"  - Any recent bulk/block deals?\n\n"
                f"**M — Market Direction:**\n"
                f"  - Current market regime (BULL/ROTATION/CHOP/BEAR)?\n"
                f"  - Is this a good time to buy growth stocks? (follow-through day, distribution days)\n"
                f"  - Nifty 50 trend and breadth status\n\n"
                f"**Final Output Format:**\n"
                f"1. Score card: each criterion with ✅/🟡/❌ and one-line evidence\n"
                f"2. Overall CANSLIM Score: X/7 (count ✅ as 1, 🟡 as 0.5, ❌ as 0)\n"
                f"3. Verdict: STRONG BUY (≥6) / BUY (5-5.5) / HOLD (4-4.5) / AVOID (<4)\n"
                f"4. Key strengths and weaknesses\n"
                f"5. If BUY: suggested entry zone, target (using resistance levels), and stop-loss\n"
                f"Use REAL data from the tool calls. Do NOT fabricate numbers."
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

        # ── /voice-mode — persistent spoken responses for normal answers ──
        elif text.lower().startswith("/voice-mode"):
            vm = handle_voice_mode_command(text, voice_mode)
            if vm.get("status") == "error":
                console.print(f"[red]  ✗ {vm.get('error')}[/red]")
            else:
                label = "enabled" if vm.get("enabled") else "disabled"
                play = "auto-play on" if vm.get("auto_play") else "auto-play off"
                console.print(f"[green]  ✓ Voice mode {label}[/green][dim]  ·  voice: {vm.get('voice')}  ·  {play}[/dim]")
                console.print(f"[dim]  {vm.get('cue', '')}[/dim]")
            continue

        # ── /voice-live — repeated voice assistant turns ──────────────────
        elif text.lower().startswith("/voice-live"):
            try:
                from voice_command import parse_voice_live_args
                from voice_live import run_voice_live_session

                args = parse_voice_live_args(text[len("/voice-live"):].strip())

                def _voice_live_event(event: str, payload: dict) -> None:
                    if event == "session_started":
                        console.print(
                            "[green]  ✓ Voice live started[/green]"
                            f"[dim]  ·  turns: {payload['turns']}  ·  listen: {payload['seconds']}s  ·  voice: {payload['voice']}[/dim]"
                        )
                        console.print("[dim]  I am the Market Intelligence Assistant from Agent Adda. Start speaking. Say 'stop' to exit.[/dim]")
                    elif event == "turn_listening":
                        console.print(f"[cyan]  🎙  Listening turn {payload['turn']} for {payload['seconds']}s...[/cyan]")
                    elif event == "turn_transcript":
                        console.print(f"[green]  ✓ Transcript:[/green] {payload.get('transcript', '')}")
                        console.print(f"[green]  ✓ Query:[/green] {payload.get('normalized_query', '')}")
                    elif event == "turn_answer":
                        _print_response({"answer": payload.get("answer", ""), "backend": "Voice Live"})
                        if payload.get("spoken_summary"):
                            console.print(f"[bold]Spoken summary:[/bold] {payload.get('spoken_summary', '')}")
                        synth = payload.get("synthesis", {})
                        if synth.get("audio_path"):
                            console.print(f"[green]  ✓ Response audio:[/green] {synth['audio_path']}")
                        if payload.get("playback", {}).get("status") == "ok":
                            console.print("[green]  ✓ Playing response audio now.[/green]")
                        console.print("[dim]  Ask your next question, or say 'stop'.[/dim]")
                    elif event == "session_stopped":
                        console.print("[yellow]  · Voice live stopped.[/yellow]")
                    elif event == "session_complete":
                        console.print(f"[green]  ✓ Voice live complete[/green][dim]  ·  turns: {payload.get('turns_completed')}[/dim]")
                    elif event == "turn_error":
                        console.print(f"[red]  ✗ Voice live failed:[/red] {payload.get('error')}")

                result = run_voice_live_session(
                    agent_runner=lambda query: agent.query(query, show_trace=show_trace),
                    turns=args.turns,
                    seconds=args.seconds,
                    want_audio=args.want_audio,
                    auto_play=args.auto_play,
                    voice=args.voice,
                    confirm_callback=_confirm_voice_query if args.confirm else None,
                    event_callback=_voice_live_event,
                )
                if result.get("status") == "error":
                    console.print(f"[red]  ✗ Voice live ended with error:[/red] {result.get('error')}")
                continue
            except SystemExit:
                console.print("[red]  ✗ Usage:[/red] /voice-live [--turns 5] [--seconds 12] [--confirm] [--no-audio] [--no-play] [--voice cedar]")
                continue
            except Exception as exc:
                console.print(f"[red]  ✗ Voice live failed:[/red] {exc}")
                continue

        # ── /kb — Knowledge base (RAG) build / ask / stats ────────────────
        # PG-kb: RAG over financial sources registry (regulators, CRAs, brokers, AMCs).
        # Pipeline: fetch PDFs/HTML → chunk → LLM Q&A → embed → ChromaDB.
        # Usage:  /kb stats                                   → collection counts
        #         /kb ask <question>                          → semantic search
        #         /kb build --tier 1 --max-pdfs 3             → fetch+index tier-1 sources
        #         /kb build --source SEBI RBI                 → fetch+index specific sources
        elif text.lower().startswith("/kb"):
            try:
                import shlex
                from knowledge_base.__main__ import main as kb_main
                argv = shlex.split(text[len("/kb"):].strip()) or ["stats"]
                console.print(f"[dim]  → /kb {' '.join(argv)}[/dim]")
                kb_main(argv)
                continue
            except SystemExit:
                console.print("[red]  ✗ Usage:[/red] /kb [stats|ask <q>|build --tier N --max-pdfs N --source SID...]")
                continue
            except Exception as exc:
                console.print(f"[red]  ✗ /kb failed:[/red] {exc}")
                continue

        # ── /reports — Enhanced Comprehensive Analysis (Postgres-backed) ──
        # PG-report: Migrated from legacy R script. Computes via SQL on
        # market.equity_eod / market.index_eod, persists to report.* tables,
        # then renders HTML by SELECT.
        # Usage:  /reports                       → run + render HTML (default)
        #         /reports run                   → compute + persist only
        #         /reports html [--run-id N]     → render HTML for run (default: latest)
        elif text.lower().startswith("/reports"):
            try:
                import shlex
                from reports.enhanced_comprehensive_analysis import main as rpt_main
                argv = shlex.split(text[len("/reports"):].strip()) or ["both"]
                console.print(f"[dim]  → /reports {' '.join(argv)}[/dim]")
                rpt_main(argv)
                continue
            except SystemExit:
                console.print("[red]  ✗ Usage:[/red] /reports [run|html|both] [--run-id N]")
                continue
            except Exception as exc:
                console.print(f"[red]  ✗ /reports failed:[/red] {exc}")
                continue

        # ── /voice — P3-2 60-second daily audio briefing ─────────────────
        # PG-voice: Generates a market briefing script + audio (OpenAI TTS or macOS `say`).
        # Sources: signal_log.csv (today's BUY signals), regime_detector, fetch_fii_dii_flows.
        # Usage:  /voice              → today's briefing with audio
        #         /voice script       → script only (no audio)
        #         /voice 2026-05-09   → historical date
        elif text.lower().startswith("/voice"):
            try:
                from voice_command import parse_voice_briefing_args
                from generate_voice_briefing import generate_briefing
                from voice_synth import play_audio

                args = parse_voice_briefing_args(text[len("/voice"):].strip())
                console.print(f"[dim]  → Generating voice briefing{' (script only)' if not args.want_tts else ''}...[/dim]")
                result = generate_briefing(date_str=args.date, want_tts=args.want_tts)
                console.print(f"[green]  ✓ Script:[/green] {result['script_path']}")
                if result.get("audio_path"):
                    console.print(f"[green]  ✓ Audio:[/green]  {result['audio_path']}")
                    if args.auto_play:
                        playback = play_audio(result["audio_path"])
                        if playback.get("status") == "ok":
                            console.print("[green]  ✓ Playing audio now.[/green]")
                        else:
                            console.print(f"[yellow]  · Auto-play failed:[/yellow] {playback.get('error')}")
                elif not args.want_tts:
                    console.print(f"[yellow]  · Audio skipped (script-only mode).[/yellow]")
                else:
                    console.print(f"[yellow]  · Audio skipped (no OPENAI_API_KEY and no macOS `say`).[/yellow]")
                console.print()
                console.print(f"[bold]Briefing ({result['date']}, {result['word_count']} words):[/bold]")
                console.print(result["script"])
                # Skip LLM round-trip — this is a self-contained pipeline.
                continue
            except SystemExit:
                console.print("[red]  ✗ Usage:[/red] /voice [script|YYYY-MM-DD] [--no-tts] [--no-play]")
                continue
            except Exception as exc:
                console.print(f"[red]  ✗ Voice briefing failed:[/red] {exc}")
                continue

        # ── /ask-voice — speech → text → Agent Adda → speech ──────────────
        elif text.lower().startswith("/ask-voice"):
            try:
                from voice_command import parse_ask_voice_args
                from voice_copilot import run_voice_query

                args = parse_ask_voice_args(text[len("/ask-voice"):].strip())
                console.print(
                    f"[dim]  → Listening for {args.seconds}s..."
                    if not args.audio_file
                    else f"[dim]  → Reading voice question from {args.audio_file}..."
                )
                result = run_voice_query(
                    audio_file=args.audio_file or None,
                    seconds=args.seconds,
                    agent_runner=lambda query: agent.query(query, show_trace=show_trace),
                    want_audio=args.want_audio,
                    auto_play=args.auto_play,
                    voice=args.voice,
                    confirm_callback=_confirm_voice_query if args.confirm else None,
                )
                if result.get("status") != "ok":
                    console.print(f"[red]  ✗ Voice query failed:[/red] {result.get('error', result.get('status'))}")
                    console.print(f"[dim]  Session: {result.get('session_dir', '')}[/dim]")
                    continue

                console.print(f"[green]  ✓ Transcript:[/green] {result.get('transcript', '')}")
                console.print(f"[green]  ✓ Query:[/green] {result.get('normalized_query', '')}")
                console.print(f"[dim]  Session: {result.get('session_dir', '')}[/dim]")
                console.print()
                _print_response({"answer": result.get("answer", ""), "backend": "Voice Copilot"})
                console.print()
                console.print(f"[bold]Spoken summary:[/bold] {result.get('spoken_summary', '')}")
                synth = result.get("synthesis", {})
                if synth.get("audio_path"):
                    console.print(f"[green]  ✓ Response audio:[/green] {synth['audio_path']}")
                    if result.get("playback", {}).get("status") == "ok":
                        console.print("[green]  ✓ Playing response audio now.[/green]")
                continue
            except SystemExit:
                console.print("[red]  ✗ Usage:[/red] /ask-voice [--seconds 20] [--audio-file path] [--no-audio] [--no-play] [--voice cedar]")
                continue
            except Exception as exc:
                console.print(f"[red]  ✗ Voice query failed:[/red] {exc}")
                continue

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
                    # PG-heat-routing-fix: previous behaviour rewrote `text`
                    # and let it fall back into agent.query() — but the
                    # follow-up phrase contained "current market environment",
                    # which `_build_market_situation_assessment_plan` matched
                    # via "market"+"current". The planner then ran
                    # get_live_market_overview + get_market_breadth and dumped
                    # 90+ index rows that had nothing to do with seasonality.
                    # New: call backend.chat() directly with the heat data and
                    # `continue` to skip the broken routing path.
                    try:
                        _hm_lines = []
                        for sec in sorted(heat.get("heatmap", {}).keys()):
                            cells = heat["heatmap"][sec]
                            _hm_lines.append(
                                f"  {sec}: " + ", ".join(
                                    f"{m}={cells.get(m, 0):+.1f}%"
                                    for m in ["Jan","Feb","Mar","Apr","May","Jun",
                                              "Jul","Aug","Sep","Oct","Nov","Dec"]
                                )
                            )
                        sys_msg = (
                            "You are Agent Adda, an Indian-equities seasonality "
                            "commentator. The user has just been shown a sector "
                            "seasonality heatmap. Your job is to write 3-4 short "
                            "actionable bullets reasoning ONLY from the seasonal "
                            "numbers provided. Do NOT mention live prices, today's "
                            "moves, or any data not present below. Do NOT call "
                            "any tools."
                        )
                        usr_msg = (
                            f"Month under review: {_mn}\n"
                            f"TAILWIND sectors (>= +5% historical avg): {heat['tailwinds']}\n"
                            f"NEUTRAL sectors: {heat['neutral']}\n"
                            f"HEADWIND sectors: {heat.get('headwinds', [])}\n\n"
                            f"12-month historical avg returns:\n"
                            + "\n".join(_hm_lines)
                            + "\n\nWrite 3-4 short bullets:\n"
                            "  • Which 1-2 sectors to overweight this month and why "
                            "(cite the historical avg).\n"
                            "  • Which 1-2 sectors to underweight or avoid and why.\n"
                            "  • One rotation idea: a likely leadership handoff "
                            "from this month to next month based on the table.\n"
                            "  • One caveat about reading too much into seasonality.\n"
                            "End with: '━━━ Not investment advice. For research and learning only. ━━━'"
                        )
                        _resp = agent.backend.chat([
                            {"role": "system", "content": sys_msg},
                            {"role": "user",   "content": usr_msg},
                        ])
                        _commentary = (_resp or {}).get("content", "").strip()
                        if _commentary:
                            console.print()
                            console.print(_commentary)
                            console.print()
                    except Exception as _llm_err:
                        console.print(f"[dim yellow]  ⚠  LLM commentary skipped: {_llm_err}[/dim yellow]")
                    continue
            except Exception as _e:
                console.print(f"[bold red]  ❌  Heat calendar error: {_e}[/bold red]")
                continue

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

        # ── /pnl — live portfolio P&L dashboard ───────────────────────
        elif text.lower().startswith("/pnl"):
            console.print("[dim]  Fetching live prices for portfolio...[/dim]")
            try:
                from terminal.portfolio_pnl import compute_pnl
                result = compute_pnl()

                from rich.table import Table
                import rich.box as _box

                tbl = Table(
                    title="💼 Portfolio — Unrealised P&L",
                    show_header=True,
                    header_style=_theme["header"],
                    box=_box.SIMPLE_HEAVY,
                    padding=(0,1)
                )
                tbl.add_column("Symbol",   style="bold yellow", width=12)
                tbl.add_column("Qty",      justify="right", width=6)
                tbl.add_column("Avg Cost", justify="right", style="dim", width=10)
                tbl.add_column("LTP",      justify="right", width=10)
                tbl.add_column("Value",    justify="right", width=12)
                tbl.add_column("P&L",      justify="right", width=12)
                tbl.add_column("P&L%",     justify="right", width=8)
                tbl.add_column("Day%",     justify="right", width=8)

                for r in result["rows"]:
                    pnl_color = _theme["profit"] if r["pnl"] >= 0 else _theme["loss"]
                    day_color = _theme["profit"] if r["day_chg_pct"] >= 0 else _theme["loss"]
                    pnl_sign  = "+" if r["pnl"] >= 0 else ""
                    day_sign  = "+" if r["day_chg_pct"] >= 0 else ""
                    tbl.add_row(
                        r["symbol"],
                        str(r["qty"]),
                        f"₹{r['avg_cost']:,.2f}",
                        f"₹{r['ltp']:,.2f}",
                        f"₹{r['current']:,.0f}",
                        f"[{pnl_color}]{pnl_sign}₹{r['pnl']:,.0f}[/]",
                        f"[{pnl_color}]{pnl_sign}{r['pnl_pct']:.1f}%[/]",
                        f"[{day_color}]{day_sign}{r['day_chg_pct']:.1f}%[/]",
                    )

                console.print(tbl)

                # Totals footer
                tot_color = _theme["profit"] if result["total_pnl"] >= 0 else _theme["loss"]
                tot_sign  = "+" if result["total_pnl"] >= 0 else ""
                day_color = _theme["profit"] if result["total_day_pnl"] >= 0 else _theme["loss"]
                console.print(f"  [bold]Invested:[/bold]  ₹{result['total_invested']:,.0f}")
                console.print(f"  [bold]Current:[/bold]   ₹{result['total_current']:,.0f}")
                console.print(f"  [bold]Total P&L:[/bold] [{tot_color}]{tot_sign}₹{result['total_pnl']:,.0f}  ({tot_sign}{result['total_pnl_pct']:.1f}%)[/]")
                console.print(f"  [bold]Day P&L:[/bold]   [{day_color}]{'+' if result['total_day_pnl']>=0 else ''}₹{result['total_day_pnl']:,.0f}[/]\n")

                text = (
                    f"Portfolio P&L summary: invested ₹{result['total_invested']:,.0f}, "
                    f"current ₹{result['total_current']:,.0f}, total P&L {result['total_pnl_pct']:.1f}%. "
                    f"Top gainers and losers: {', '.join(r['symbol'] for r in result['rows'][:3])}. "
                    f"Give a brief portfolio health commentary and any rebalancing suggestions."
                )
            except Exception as _e:
                console.print(f"[bold red]  ❌ P&L error: {_e}[/bold red]")
                import traceback; traceback.print_exc()
                continue

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

        # ── /options — live options chain (Rich side-by-side table) ──────
        if text.startswith("/options"):
            parts = text.split()
            sym = parts[1].upper() if len(parts) > 1 else "NIFTY"
            expiry_idx = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
            console.print(f"[dim]  Fetching options chain for {sym} (expiry #{expiry_idx})...[/dim]")
            try:
                from terminal.tools import call_tool
                oc = call_tool("get_options_chain", {"symbol": sym, "expiry_index": expiry_idx})
                if "error" in oc:
                    console.print(f"[red]  ❌ {oc['error']}[/red]")
                    continue

                from rich.table import Table
                import rich.box as _box

                console.print(f"\n[bold cyan]  Options Chain: {oc['symbol']}[/bold cyan]  [dim]Expiry: {oc['expiry']}  |  Spot: ₹{oc['underlying']:,.1f}  |  ATM: {oc['atm']}[/dim]")
                console.print(f"  [yellow]PCR: {oc['pcr']}[/yellow]  [dim]|[/dim]  [cyan]Max Pain: {oc['max_pain']}[/cyan]  [dim]|  Call OI: {oc['total_call_oi']:,}  |  Put OI: {oc['total_put_oi']:,}[/dim]")

                if oc.get("expiry_dates"):
                    exp_str = "  ".join(f"[{'bold green' if i == expiry_idx else 'dim'}]{i}:{d}[/]" for i, d in enumerate(oc["expiry_dates"]))
                    console.print(f"  Expiries: {exp_str}\n")

                atm = oc["atm"]
                all_strikes = sorted(set(c["strike"] for c in oc["calls"]) | set(p["strike"] for p in oc["puts"]))
                atm_idx_pos = all_strikes.index(atm) if atm in all_strikes else len(all_strikes) // 2
                show_strikes = set(all_strikes[max(0, atm_idx_pos - 10):atm_idx_pos + 11])

                call_map = {c["strike"]: c for c in oc["calls"]}
                put_map = {p["strike"]: p for p in oc["puts"]}

                tbl = Table(show_header=True, header_style="bold", box=_box.SIMPLE_HEAVY, padding=(0, 1))
                tbl.add_column("C.OI", style="dim", justify="right", width=10)
                tbl.add_column("C.IV%", justify="right", width=6)
                tbl.add_column("C.LTP", style="green", justify="right", width=8)
                tbl.add_column("STRIKE", style="bold white", justify="center", width=8)
                tbl.add_column("P.LTP", style="red", justify="right", width=8)
                tbl.add_column("P.IV%", justify="right", width=6)
                tbl.add_column("P.OI", style="dim", justify="right", width=10)

                for strike in sorted(show_strikes):
                    c = call_map.get(strike, {})
                    p = put_map.get(strike, {})
                    is_atm = (strike == atm)
                    strike_str = f"[bold yellow]► {strike} ◄[/bold yellow]" if is_atm else str(strike)
                    c_style = "bold green" if strike < oc["underlying"] else ""
                    p_style = "bold red" if strike > oc["underlying"] else ""
                    tbl.add_row(
                        f"[{c_style}]{c.get('oi', 0):,}[/]" if c else "-",
                        f"{c.get('iv', 0):.1f}" if c else "-",
                        f"[{c_style}]{c.get('ltp', 0):.2f}[/]" if c else "-",
                        strike_str,
                        f"[{p_style}]{p.get('ltp', 0):.2f}[/]" if p else "-",
                        f"{p.get('iv', 0):.1f}" if p else "-",
                        f"[{p_style}]{p.get('oi', 0):,}[/]" if p else "-",
                    )

                console.print(tbl)

                pcr = oc["pcr"]
                if pcr > 1.2:
                    pcr_msg = "[green]Bullish (heavy put writing)[/green]"
                elif pcr < 0.8:
                    pcr_msg = "[red]Bearish (heavy call writing)[/red]"
                else:
                    pcr_msg = "[yellow]Neutral[/yellow]"
                console.print(f"  PCR Interpretation: {pcr_msg}\n")

                text = (
                    f"Options chain for {sym} (expiry {oc['expiry']}): spot {oc['underlying']}, "
                    f"ATM {atm}, PCR {pcr}, max pain {oc['max_pain']}. "
                    f"Give a brief F&O analysis: key support/resistance from OI buildup, "
                    f"IV skew interpretation, and trading outlook."
                )
            except Exception as _e:
                console.print(f"[bold red]  ❌ Options error: {_e}[/bold red]")
                import traceback; traceback.print_exc()
                continue

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

        # ── /recap — intraday market recap (PG intraday.quote_snapshots) ─
        # PG-recap-slash: rewrite `/recap [minutes]` into a phrase that the
        # planner's `intraday_market_recap` keyword rule accepts. Without this
        # the bare token `/recap` fell through to the symbol planner and was
        # resolved to a random ticker.
        elif text.lower().startswith("/recap"):
            parts = text.split()
            try:
                minutes = int(parts[1]) if len(parts) > 1 else 15
            except (ValueError, IndexError):
                minutes = 15
            text = f"what happened in the market in the last {minutes} minutes"
            console.print(f"[dim]  → Intraday recap: last {minutes} min[/dim]")

        # ── /theme — select color theme ────────────────────────────────────
        if text.lower().startswith("/theme"):
            from terminal.theme import get_theme_name, set_theme, list_themes, THEMES
            parts = text.split()
            if len(parts) == 1:
                current = get_theme_name()
                console.print(f"\n  [bold]Available Themes[/bold]  [dim](current: {current})[/dim]\n")
                for tname, tdef in THEMES.items():
                    marker = "▶" if tname == current else " "
                    swatch = ""
                    for label, color in tdef["preview"]:
                        swatch += f"[{color}]{label}[/{color}]"
                    console.print(f"  {marker} [bold {'cyan' if tname==current else 'white'}]{tname:<15}[/]  {swatch}")
                console.print(f"\n  Usage: [dim]/theme dracula[/dim]  |  [dim]/theme dark[/dim]  |  [dim]/theme nord[/dim]\n")
            else:
                tname = parts[1].lower()
                try:
                    tdef = set_theme(tname)
                    _theme = tdef
                    console.print(f"  [bold]Theme set:[/bold] [{_theme['accent']}]{tdef['name']}[/{_theme['accent']}] ✅")
                    for label, color in tdef["preview"]:
                        console.print(f"    [{color}]{label}[/{color}]")
                except ValueError as e:
                    console.print(f"  [red]{e}[/red]")
            continue

        # ── /scale — layout density ────────────────────────────────────────
        if text.lower().startswith("/scale"):
            from terminal.theme import get_scale_name, set_scale, SCALES
            parts = text.split()
            if len(parts) == 1:
                current = get_scale_name()
                console.print(f"\n  [bold]Layout Scale[/bold]  [dim](current: {current})[/dim]\n")
                for sname, sdef in SCALES.items():
                    marker = "▶" if sname == current else " "
                    console.print(f"  {marker} [bold {'cyan' if sname==current else 'white'}]{sname:<10}[/]  [dim]{sdef['description']}[/dim]  [dim]chart {sdef['chart_width']}×{sdef['chart_height']}[/dim]")
                console.print(f"\n  Usage: [dim]/scale compact[/dim]  |  [dim]/scale normal[/dim]  |  [dim]/scale large[/dim]")
                console.print(f"  [dim]Tip: To change actual font size, use your terminal's Cmd+= / Ctrl+= shortcut.[/dim]\n")
            else:
                sname = parts[1].lower()
                try:
                    sdef = set_scale(sname)
                    _scale = sdef
                    console.print(f"  [bold]Scale set:[/bold] [cyan]{sdef['name']}[/cyan] — {sdef['description']} ✅")
                    console.print(f"  [dim]Charts will render at {sdef['chart_width']}×{sdef['chart_height']}. Restart not required.[/dim]")
                except ValueError as e:
                    console.print(f"  [red]{e}[/red]")
            continue

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
            voice_result = speak_answer_when_enabled(text, result, voice_mode)
            if voice_result.get("status") == "ok":
                synth = voice_result.get("synthesis", {})
                console.print(f"[green]  ✓ Voice mode response:[/green] {synth.get('audio_path', '')}")
                if voice_result.get("playback", {}).get("status") == "ok":
                    console.print("[green]  ✓ Playing voice mode response now.[/green]")
            elif voice_result.get("status") == "error":
                console.print(f"[yellow]  · Voice mode failed:[/yellow] {voice_result.get('synthesis', {}).get('error', 'unknown error')}")
            if show_trace:
                _print_trace(result.get("trace", []))

            # ── Auto-export after /analyze, /search ───────────────────────
            _clean_ans, _ = _parse_followups(result.get("answer", ""))
            if _clean_ans.strip():
                if _analyze_report_after:
                    _auto_export_report(_clean_ans, _analyze_report_after[1],
                                        _analyze_report_after[0], _analyze_report_after[2])
                elif _search_report_after:
                    _auto_export_report(_clean_ans, _search_report_after[1],
                                        _search_report_after[0], _search_report_after[2])
            _analyze_report_after = None
            _search_report_after  = None
        except Exception as e:
            console.print(f"[bold red]  ❌  Error: {e}[/bold red]")
            _separator()
            _analyze_report_after = None
            _search_report_after  = None

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
    parser.add_argument("--theme", default=None,
                        help="Color theme: dark, dracula, solarized, high-contrast, nord")
    parser.add_argument("--scale", default=None,
                        help="Layout scale: compact, normal, large")
    args = parser.parse_args()

    global _mode
    _mode = args.mode

    if args.theme:
        from terminal.theme import set_theme
        set_theme(args.theme)
    if args.scale:
        from terminal.theme import set_scale
        set_scale(args.scale)

    print_banner()

    sys.stdout.write("\x1b[36m  Loading Agent Adda…\x1b[0m\r")
    sys.stdout.flush()
    from terminal.agent import Agent
    agent = Agent()
    console.print(f"[bold green]  ✓ Agent Adda ready[/bold green]"
                  f"[dim]  │  backend: {agent.backend_name}"
                  f"  │  mode: {_mode}"
                  f"  │  {_session_clock_label()}[/dim]")

    # PG-intraday-capture: spawn daemon thread that polls the NSE live tape
    # every minute (during market hours) and prunes rows older than 2 hours.
    # Runs silently — never raises into the chat loop.
    try:
        from terminal.intraday_capture import (
            start_background_capture, CAPTURE_INTERVAL_SEC, RETENTION_MINUTES,
        )
        if start_background_capture():
            console.print(
                f"[dim]  │  intraday capture: every {CAPTURE_INTERVAL_SEC}s · "
                f"retain {RETENTION_MINUTES} min[/dim]"
            )
    except Exception as _e:
        console.print(f"[dim red]  │  intraday capture disabled ({_e})[/dim red]")
    console.print()

    if args.query:
        _single_query(agent, args.query, args.trace)
        return

    # ── Startup briefing (skip with --no-briefing or -nb) ─────────────────
    if not args.no_briefing:
        _run_startup_briefing(agent, args.trace)
        _run_voice_briefing_panel()

    _chat_loop(agent, args.trace)


if __name__ == "__main__":
    main()
