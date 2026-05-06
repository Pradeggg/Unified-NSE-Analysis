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
            ("Bank Nifty Scan",      "Scan NIFTY BANK for intraday buy and sell signals using all strategies on 15m charts. Show entry, target, SL and R:R."),
            ("Nifty 50 Scan",        "Scan NIFTY 50 for the best intraday setups right now — momentum, breakouts, and mean-reversion on 15m candles."),
            ("Nifty IT Scan",        "Scan NIFTY IT index for intraday signals. Focus on MACD and EMA crossovers."),
            ("RELIANCE Intraday",    "Intraday trading setup for RELIANCE on 15m — entry, target, stoploss, R:R, pivot levels, and key indicators."),
            ("VCP Pattern Hunt",     "Scan NIFTY 500 for VCP (Volatility Contraction Pattern) stocks ready for intraday breakout on 15m."),
            ("Volume Spike Alert",   "Which NIFTY 50 or BANK NIFTY stocks are showing 2x+ volume spikes with price confirmation right now?"),
            ("Supertrend BUY List",  "Scan NIFTY MIDCAP 100 for stocks with active Supertrend BUY signals on 15m with R:R above 1.5."),
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
    ]:
        print(f"  {icon}  {colour}{Style.BRIGHT}{text}{Style.RESET_ALL}")
    print()
    print(Fore.WHITE + Style.DIM +
          "  /live  /eod  /auto  │  /prompts  │  p<n> = run prompt  │  1 2 3 = follow-ups  │  /help  │  exit")
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


def _build_prompt() -> ANSI:
    tag = {
        "auto":       "\x1b[2m[AUTO]\x1b[0m",
        "intraday":   "\x1b[1;31m[LIVE🔴]\x1b[0m",
        "historical": "\x1b[1;34m[EOD📚]\x1b[0m",
    }[_mode]
    fup = (f"  \x1b[33m(follow-ups: 1·2·3)\x1b[0m" if _followups else "")
    return ANSI(f"  {tag}{fup}\x1b[1;36m ❯ \x1b[0m")


# ─────────────────────────────────────────────────────────────────────────────
# Display helpers  (all print to stdout; terminal scrolls naturally)
# ─────────────────────────────────────────────────────────────────────────────

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

    # ── Body — Rich Markdown rendered to full terminal width ───────────────
    has_markup = any(c in clean for c in ["**", "##", "- ", "* ", "```", "\n"])
    if has_markup:
        console.print(Markdown(clean))
    else:
        console.print(clean, style="white")

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
                title   = r.get("title") or r.get("name") or ""
                url     = r.get("url")   or r.get("link") or ""
                snippet = r.get("snippet") or r.get("body") or ""
                source  = r.get("source", "")
                if source:
                    console.print(f"[dim cyan]  [{source}][/dim cyan]", end=" ")
                if title:
                    console.print(f"  [bold]{title}[/bold]")
                if url:
                    console.print(f"  [dim cyan]{url}[/dim cyan]")
                if snippet:
                    console.print(f"  [dim]{snippet[:140]}…[/dim]" if len(snippet) > 140
                                  else f"  [dim]{snippet}[/dim]")
                console.print()

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


def _print_help() -> None:
    print()
    console.print(Panel(
        Text.from_markup(
            "[bold cyan]MODE COMMANDS[/bold cyan]\n"
            "  [red]/live[/red]  or  [red]/l[/red]        — Live / Intraday  (real-time NSE API)\n"
            "  [blue]/eod[/blue]   or  [blue]/h[/blue]        — EOD / Historical (CSV + DB snapshot)\n"
            "  [white]/auto[/white]  or  [white]/a[/white]        — Auto-detect from query keywords\n\n"
            "[bold cyan]INTRADAY SCREENER[/bold cyan]\n"
            "  [green]/scan[/green]                   — Scan NIFTY 50 for intraday signals\n"
            "  [green]/scan NIFTY BANK[/green]        — Scan any index (NIFTY IT, PHARMA…)\n\n"
            "[bold cyan]PROMPT LIBRARY[/bold cyan]\n"
            "  [yellow]/prompts[/yellow]               — Browse all 50+ curated research prompts\n"
            "  [yellow]/prompts intraday[/yellow]      — Filter by category (market/technical/sector…)\n"
            "  [yellow]p<number>[/yellow]              — Run prompt by number  (e.g. p5, p23, p41)\n\n"
            "[bold cyan]FOLLOW-UPS[/bold cyan]\n"
            "  [yellow]1 / 2 / 3[/yellow]              — Ask the numbered follow-up question\n\n"
            "[bold cyan]OTHER[/bold cyan]\n"
            "  [dim]/clear[/dim]                  — Clear screen\n"
            "  [dim]exit / quit[/dim]             — Exit Agent Adda\n"
            "  [dim]Ctrl-C[/dim]                  — Exit (same as quit)\n"
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
        console.print(Markdown(clean))
    else:
        console.print(clean, style="white")

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
                title   = r.get("title") or r.get("name") or ""
                url     = r.get("url")   or r.get("link") or ""
                snippet = r.get("snippet") or r.get("body") or ""
                source  = r.get("source", "")
                if source:
                    console.print(f"[dim cyan]  [{source}][/dim cyan]", end=" ")
                if title:
                    console.print(f"  [bold]{title}[/bold]")
                if url:
                    console.print(f"  [dim cyan]{url}[/dim cyan]")
                if snippet:
                    console.print(f"  [dim]{snippet[:120]}…[/dim]" if len(snippet) > 120
                                  else f"  [dim]{snippet}[/dim]")
                console.print()

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

    session = PromptSession(history=InMemoryHistory())

    console.print("[bold green]  ✓ Agent Adda ready[/bold green] — type your question and press Enter")
    console.print("[dim]  Tip: /live  /eod  /auto  │  1·2·3 = follow-ups  │  /help  │  exit[/dim]")
    console.print()

    while True:
        try:
            raw = session.prompt(_build_prompt())
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

        # ── /prompts library ───────────────────────────────────────────
        if text.lower().startswith("/prompts") or text.lower() == "/p":
            parts = text.split(maxsplit=1)
            fkey  = parts[1].strip() if len(parts) > 1 else ""
            _print_prompts_library(fkey)
            continue

        # ── /scan shortcut: run intraday screener ──────────────────────
        if text.lower().startswith("/scan"):
            parts = text.split(maxsplit=1)
            idx   = parts[1].upper() if len(parts) > 1 else "NIFTY 50"
            text  = f"Scan {idx} for intraday buy and sell signals using all strategies on 15m charts"
            console.print(f"[dim]  → Intraday scan: {idx}[/dim]")

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
