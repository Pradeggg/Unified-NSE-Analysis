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
# Banner  (printed once at startup before chat loop)
# ─────────────────────────────────────────────────────────────────────────────

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
          "  /live  /eod  /auto  │  1 2 3 = follow-ups  │  /help  │  exit")
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
            "  [red]/live[/red]  or  [red]/l[/red]   — Live / Intraday  (real-time NSE API)\n"
            "  [blue]/eod[/blue]   or  [blue]/h[/blue]   — EOD / Historical (CSV + DB snapshot)\n"
            "  [white]/auto[/white]  or  [white]/a[/white]   — Auto-detect from query keywords\n\n"
            "[bold cyan]INTRADAY SCREENER[/bold cyan]\n"
            "  [green]/scan[/green]                    — Scan NIFTY 50 for intraday signals\n"
            "  [green]/scan NIFTY BANK[/green]         — Scan any index (NIFTY IT, PHARMA…)\n\n"
            "[bold cyan]FOLLOW-UPS[/bold cyan]\n"
            "  [yellow]1 / 2 / 3[/yellow]              — Ask the numbered follow-up question\n\n"
            "[bold cyan]OTHER[/bold cyan]\n"
            "  [dim]/clear[/dim]                 — Clear screen\n"
            "  [dim]exit / quit[/dim]            — Exit Agent Adda\n"
            "  [dim]Ctrl-C[/dim]                 — Exit (same as quit)\n"
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

        # ── /scan shortcut: run intraday screener ──────────────────────
        if text.lower().startswith("/scan"):
            parts = text.split(maxsplit=1)
            idx   = parts[1].upper() if len(parts) > 1 else "NIFTY 50"
            text  = f"Scan {idx} for intraday buy and sell signals using all strategies on 15m charts"
            console.print(f"[dim]  → Intraday scan: {idx}[/dim]")

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

    _chat_loop(agent, args.trace)


if __name__ == "__main__":
    main()
