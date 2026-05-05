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
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.formatted_text import ANSI

colorama.init(autoreset=True)

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass

# ── Rich console (force colour even in redirected environments) ───────────────
console = Console(highlight=False)

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


def _separator() -> None:
    console.print(Rule(style="dim cyan"))


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
    console.print(f"[bold cyan] ❯  [/bold cyan][bold white]{query}[/bold white]"
                  f"[dim]  [{_ts()}][/dim]")


def _print_response(result: dict) -> None:
    global _followups
    answer  = result.get("answer", "(no answer)")
    backend = result.get("backend", "?")

    # Strip follow-ups from answer body
    clean, _followups = _parse_followups(answer)

    # ── Agent header ──────────────────────────────────────────────────────
    console.print()
    console.print(f"[bold green] 🤖  Agent Adda[/bold green]"
                  f"[dim]  [{_ts()}]  backend: {backend}[/dim]")
    _separator()

    # ── Body — Rich Markdown rendered to full terminal width ───────────────
    has_markup = any(c in clean for c in ["**", "##", "- ", "* ", "```", "\n"])
    if has_markup:
        console.print(Markdown(clean))
    else:
        console.print(Text(clean, style="white"))

    # ── Follow-up suggestions ─────────────────────────────────────────────
    if _followups:
        console.print()
        console.print("[bold yellow] 💬  What to explore next:[/bold yellow]")
        for i, q in enumerate(_followups, 1):
            console.print(f"[yellow]   {i}.[/yellow] [white]{q}[/white]")
        console.print("[dim]   → Type 1, 2 or 3 to ask, or your own question[/dim]")

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
            "[bold cyan]FOLLOW-UPS[/bold cyan]\n"
            "  [yellow]1 / 2 / 3[/yellow]          — Ask the numbered follow-up question\n\n"
            "[bold cyan]OTHER[/bold cyan]\n"
            "  [dim]/clear[/dim]             — Clear screen\n"
            "  [dim]exit / quit[/dim]        — Exit Agent Adda\n"
            "  [dim]Ctrl-C[/dim]             — Exit (same as quit)\n"
        ),
        title="[bold cyan]Agent Adda Help[/bold cyan]",
        border_style="cyan",
    ))


# ─────────────────────────────────────────────────────────────────────────────
# Spinner (runs while agent is querying)
# ─────────────────────────────────────────────────────────────────────────────

def _run_with_spinner(agent, query: str, show_trace: bool, animated: bool = True) -> dict:
    """Run agent query with a spinner. animated=True for single-query mode (real TTY,
    no patch_stdout); animated=False inside the chat loop (patch_stdout active)."""
    result: dict = {}
    exc: list    = []

    if not animated:
        # Inside patch_stdout — static status via Rich (no raw ANSI)
        console.print("[cyan]  ⏳  Agent Adda is thinking…[/cyan]")
        try:
            result = agent.query(query, show_trace=show_trace)
        except Exception as e:
            raise e
        return result

    # Animated braille spinner (for single-query / non-patch_stdout context)
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

    with patch_stdout():
        while True:
            try:
                raw = session.prompt(_build_prompt())
            except KeyboardInterrupt:
                print()
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
