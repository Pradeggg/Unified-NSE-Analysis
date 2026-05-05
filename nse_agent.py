#!/usr/bin/env python3
"""
nse_agent.py — Agent Adda Chat Terminal

A standalone Rich + colorama chat interface for the NSE market research agent.
Run this in a second terminal alongside nse_terminal.py.

Usage:
  python nse_agent.py                        # interactive chat UI
  python nse_agent.py --query "show me RELIANCE"   # single query, no UI
  python nse_agent.py --trace                # show tool execution trace

Controls (in chat mode):
  Type your question + Enter to send
  Ctrl-C or type 'exit' / 'quit' to close

Environment:
  OPENAI_API_KEY  — enables OpenAI GPT-4o-mini backend
  OPENAI_MODEL    — override model (default: gpt-4o-mini)
"""

from __future__ import annotations

import argparse
import sys
import time
import threading
from datetime import datetime
from pathlib import Path

import colorama
from colorama import Fore, Back, Style

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text
from rich import box

colorama.init(autoreset=True)

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass

console = Console()

# ── ASCII art banner (colorama-coloured, printed before the TUI starts) ───────

_BANNER_LINES = [
    (Fore.CYAN  + Style.BRIGHT, r"   ___                     _      _       _     _      "),
    (Fore.CYAN  + Style.BRIGHT, r"  / _ \   __ _   ___  _ __ | |_   / \   __| | __| | __ _ "),
    (Fore.GREEN + Style.BRIGHT, r" / /_\ \ / _` | / _ \| '_ \| __| / _ \ / _` |/ _` |/ _` |"),
    (Fore.GREEN + Style.BRIGHT, r"/ /   \ \ (_| ||  __/| | | | |_ / ___ \ (_| | (_| | (_| |"),
    (Fore.YELLOW+ Style.BRIGHT, r"\/     \/ \__, | \___||_| |_|\__/_/   \_\__,_|\__,_|\__,_|"),
    (Fore.YELLOW+ Style.BRIGHT, r"          |___/                                            "),
]

_TAGLINE = [
    Fore.WHITE  + Style.BRIGHT + "  ┌" + "─" * 54 + "┐",
    Fore.CYAN   + Style.BRIGHT + "  │" +
        Fore.YELLOW + "  🏛  NSE Market Research  " +
        Fore.WHITE  + "│  " +
        Fore.GREEN  + "AI-powered analysis" +
        Fore.WHITE  + Style.BRIGHT + "  │",
    Fore.WHITE  + Style.BRIGHT + "  │" +
        Fore.CYAN   + "  Ask: stocks · sectors · signals · health " +
        Fore.WHITE  + Style.BRIGHT + "│",
    Fore.WHITE  + Style.BRIGHT + "  │" +
        Fore.MAGENTA + "  Type  exit  or  Ctrl-C  to quit          " +
        Fore.WHITE  + Style.BRIGHT + "│",
    Fore.WHITE  + Style.BRIGHT + "  └" + "─" * 54 + "┘",
]

_EXAMPLES = [
    ("  💡 ", Fore.CYAN,   "How is the market today?"),
    ("  💡 ", Fore.GREEN,  "Show me Stage 2 breakout stocks"),
    ("  💡 ", Fore.YELLOW, "RELIANCE technical setup"),
    ("  💡 ", Fore.MAGENTA,"Sector rotation — which sectors are leading?"),
    ("  💡 ", Fore.CYAN,   "What are the strongest Supertrend buy signals?"),
]


def print_banner() -> None:
    """Print colorama-coloured ASCII banner to stdout before TUI starts."""
    print()
    for colour, line in _BANNER_LINES:
        print(colour + line)
    print()
    for line in _TAGLINE:
        print(line)
    print()
    print(Fore.WHITE + Style.DIM + "  Example queries:")
    for icon, colour, text in _EXAMPLES:
        print(Fore.WHITE + icon + colour + Style.BRIGHT + text)
    print()
    # Gradient separator
    colors = [Fore.CYAN, Fore.GREEN, Fore.YELLOW, Fore.RED, Fore.MAGENTA]
    bar = ""
    for i, c in enumerate(colors):
        bar += c + Style.BRIGHT + "━" * (console.width // len(colors))
    print(bar + Style.RESET_ALL)
    print()


# ── Chat history ──────────────────────────────────────────────────────────────
# Each entry: {"role": "user"|"agent", "text": str, "ts": str, "thinking": bool}
_history: list[dict] = []
_status  = "Ready — type your question below"


# ── Rendering helpers ─────────────────────────────────────────────────────────

def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _bubble(entry: dict) -> Panel:
    """Render one chat message as a compact styled bubble."""
    role     = entry["role"]
    text     = entry["text"]
    ts       = entry.get("ts", "")
    thinking = entry.get("thinking", False)

    if thinking:
        t = Text()
        t.append(" ⏳ ", style="bold yellow")
        t.append(text, style="yellow")
        return Panel(t, border_style="yellow", padding=(0, 1))

    if role == "user":
        t = Text()
        t.append(" ❯ ", style="bold cyan")
        t.append(text, style="bold white")
        t.append(f" [{ts}]", style="dim")
        return Panel(t, border_style="bright_cyan", padding=(0, 1))
    else:
        if any(c in text for c in ["**", "##", "- ", "* ", "```", "\n"]):
            body = Markdown(text)
        else:
            body = Text(text, style="white")
        return Panel(body, border_style="bright_green",
                     subtitle=Text(f" 🤖  [{ts}]", style="dim green"),
                     padding=(0, 1))


def _welcome_splash() -> Text:
    """Colorful welcome splash shown in the body when no messages yet."""
    t = Text()
    # Rainbow AGENT ADDA title (big block letters via box-drawing)
    lines = [
        "  ╔═╗╔═╗╔═╗╔╗╔╔╦╗   ╔═╗╔╦╗╔╦╗╔═╗",
        "  ╠═╣║ ╦║╣ ║║║ ║    ╠═╣ ║║ ║║╠═╣",
        "  ╩ ╩╚═╝╚═╝╝╚╝ ╩    ╩ ╩═╩╝═╩╝╩ ╩",
    ]
    grad = ["bold cyan", "bold bright_cyan", "bold green",
            "bold bright_green", "bold yellow"]
    for i, line in enumerate(lines):
        t.append(line + "\n", style=grad[i % len(grad)])

    t.append("\n  NSE Market Research  ·  AI-powered analysis\n\n",
             style="bold white")

    examples = [
        ("cyan",    "💡  How is the market today?"),
        ("green",   "💡  Show me Stage 2 breakout stocks"),
        ("yellow",  "💡  RELIANCE technical setup"),
        ("magenta", "💡  Sector rotation — which sectors are leading?"),
        ("red",     "💡  What are the strongest Supertrend buy signals?"),
    ]
    for colour, text in examples:
        t.append(f"  {text}\n", style=colour)

    t.append("\n  Type your question below and press ", style="dim")
    t.append("Enter", style="bold cyan")
    t.append("  ·  Esc = clear  ·  Ctrl-C = exit\n", style="dim")
    return t


def build_chat_layout(input_buf: str) -> Layout:
    """Build the full chat terminal layout."""
    root = Layout()
    root.split_column(
        Layout(name="header", size=3),
        Layout(name="body"),
        Layout(name="status", size=1),
        Layout(name="input",  size=3),
    )

    # ── Header: rainbow AGENT ADDA + topic pills ──────────────────────────────
    hdr = Table.grid(expand=True, padding=(0, 1))
    hdr.add_column()

    title = Text()
    title.append("  🏛  ", style="bold white")
    palette = ["bold cyan", "bold bright_cyan", "bold green", "bold bright_green",
               "bold yellow", "bold bright_yellow", "bold magenta",
               "bold red", "bold bright_red", "bold white"]
    for i, ch in enumerate("AGENT ADDA"):
        title.append(ch, style=palette[i % len(palette)])
    title.append("  │  NSE Market Research", style="dim white")
    hdr.add_row(title)

    pills = Text()
    for label, colour in [("stocks","cyan"),("sectors","green"),("signals","yellow"),
                           ("screeners","magenta"),("health","red")]:
        pills.append(f"  {label}", style=colour)
        pills.append("  ·", style="dim")
    pills.append("  Esc=clear  Ctrl-U=erase  Ctrl-C=exit", style="dim")
    hdr.add_row(pills)

    root["header"].update(Panel(hdr, border_style="cyan",
                                title="[bold cyan]💬 Agent Adda[/bold cyan]",
                                padding=(0, 0)))

    # ── Body: messages (pinned to bottom) or welcome splash ───────────────────
    h = console.size.height
    body_rows = max(4, h - 3 - 1 - 3 - 4)   # terminal_h minus header(3)+status(1)+input(3)+borders(~4)

    visible = _history[-30:] if _history else []
    if not visible:
        root["body"].update(Panel(_welcome_splash(), border_style="dim",
                                  padding=(0, 1),
                                  title="[dim]conversation[/dim]"))
    else:
        # Show last N bubbles that fill the body.
        # Estimate ~4 rows per bubble; show as many as fit.
        max_bubbles = max(1, body_rows // 4)
        shown = visible[-max_bubbles:]

        chat_grid = Table.grid(expand=True, padding=(0, 0))
        chat_grid.add_column()
        # Spacer pushes messages to the bottom
        spacer_rows = max(0, body_rows - len(shown) * 4)
        if spacer_rows > 0:
            chat_grid.add_row(Text("\n" * spacer_rows, style=""))
        for entry in shown:
            chat_grid.add_row(_bubble(entry))

        root["body"].update(Panel(chat_grid, border_style="dim", padding=(0, 0),
                                  title="[dim]conversation[/dim]"))

    # ── Status bar (single line, no Panel border) ─────────────────────────────
    is_thinking = "Thinking" in _status or "⏳" in _status
    st = Text()
    st.append(" ● ", style="bold yellow" if is_thinking else "bold green")
    st.append(_status, style="bold yellow" if is_thinking else "dim white")
    root["status"].update(st)

    # ── Input bar ─────────────────────────────────────────────────────────────
    bar = Text()
    bar.append("  ❯ ", style="bold cyan")
    if input_buf:
        bar.append(input_buf, style="bold white")
        bar.append("▌", style="bold cyan blink")
    else:
        bar.append("Ask your question…  │  Esc=clear  │  Ctrl-U=erase  │  Ctrl-C=exit",
                   style="dim italic")
        bar.append("  ▌", style="bold cyan blink")
    root["input"].update(Panel(bar, border_style="bright_cyan",
                               title="[bold cyan]Query[/bold cyan]", padding=(0, 0)))
    return root


# ── Agent thread ──────────────────────────────────────────────────────────────

def _run_query_async(agent, query: str, show_trace: bool) -> None:
    global _status
    _status = f"⏳  Thinking… [{_ts()}]"
    placeholder = {"role": "agent", "text": "Agent Adda is thinking…",
                   "ts": _ts(), "thinking": True}
    _history.append(placeholder)
    try:
        result = agent.query(query, show_trace=show_trace)
        answer  = result.get("answer", "(no answer)")
        backend = result.get("backend", "")
        if _history and _history[-1].get("thinking"):
            _history.pop()
        _history.append({"role": "agent", "text": answer, "ts": _ts()})
        _status = f"✓  Last answered {_ts()}  │  backend: {backend}"
    except Exception as e:
        if _history and _history[-1].get("thinking"):
            _history.pop()
        _history.append({"role": "agent", "text": f"❌ Error: {e}", "ts": _ts()})
        _status = f"✗  Error at {_ts()}"


# ── Single-query mode ─────────────────────────────────────────────────────────

def _single_query(agent, query: str, show_trace: bool) -> None:
    print(Fore.CYAN + Style.BRIGHT + "\n  ❯ " + Fore.WHITE + query)
    print(Fore.YELLOW + "  " + "─" * 60)
    with console.status("[bold cyan]Thinking…[/bold cyan]"):
        result = agent.query(query, show_trace=show_trace)
    answer  = result.get("answer", "(no answer)")
    backend = result.get("backend", "")
    print(Fore.GREEN + Style.DIM + f"\n  🤖 Agent Adda  [{_ts()}]  backend: {backend}\n")
    if any(c in answer for c in ["**", "##", "- ", "```"]):
        console.print(Markdown(answer))
    else:
        console.print(answer)
    if show_trace and result.get("trace"):
        tbl = Table(box=box.SIMPLE, header_style="bold dim", expand=True)
        tbl.add_column("Tool",   style="cyan",  width=26)
        tbl.add_column("Args",   style="dim",   width=30)
        tbl.add_column("Result", style="white", width=30)
        for t in result["trace"]:
            res = t.get("result", {})
            err = res.get("error", "")
            s   = f"ERROR: {err[:40]}" if err else f"ok — {', '.join(list(res)[:4])}"
            tbl.add_row(t.get("tool", "—"), str(t.get("args", {}))[:40], s)
        console.print(Panel(tbl, title="[bold dim]Tool Trace[/bold dim]", border_style="dim"))


# ── Interactive chat TUI ──────────────────────────────────────────────────────

def _chat_tui(agent, show_trace: bool) -> None:
    global _status

    import os, tty, termios

    input_buf    = ""
    input_lock   = threading.Lock()
    submit_queue: list[str] = []
    _old_settings = None

    fd = sys.stdin.fileno()
    try:
        _old_settings = termios.tcgetattr(fd)
    except Exception:
        _old_settings = None

    def _restore():
        if _old_settings is not None:
            try:
                termios.tcsetattr(fd, termios.TCSADRAIN, _old_settings)
            except Exception:
                pass

    with Live(console=console, screen=True, refresh_per_second=8) as live:
        try:
            tty.setraw(fd, termios.TCSAFLUSH)
        except Exception:
            pass

        def _reader():
            nonlocal input_buf
            try:
                while True:
                    ch = os.read(fd, 1)
                    if not ch:
                        continue
                    c = ch.decode("utf-8", errors="replace")
                    if c in ("\r", "\n"):
                        with input_lock:
                            line = input_buf
                            input_buf = ""
                        if line.strip().lower() in ("exit", "quit", "q", ":q"):
                            submit_queue.append("__EXIT__")
                        elif line.strip():
                            submit_queue.append(line.strip())
                    elif c in ("\x7f", "\x08"):
                        with input_lock:
                            input_buf = input_buf[:-1]
                    elif c == "\x1b":
                        try:
                            nxt = os.read(fd, 3)
                        except Exception:
                            nxt = b""
                        if not nxt or nxt[:1] != b"[":
                            with input_lock:
                                input_buf = ""
                    elif c == "\x03":
                        submit_queue.append("__EXIT__")
                    elif c == "\x15":
                        with input_lock:
                            input_buf = ""
                    elif c >= " ":
                        with input_lock:
                            input_buf += c
            except Exception:
                pass

        threading.Thread(target=_reader, daemon=True).start()

        _pending_thread: threading.Thread | None = None

        while True:
            with input_lock:
                buf = input_buf

            live.update(build_chat_layout(buf))

            if submit_queue:
                cmd = submit_queue.pop(0)
                if cmd == "__EXIT__":
                    break
                if _pending_thread and _pending_thread.is_alive():
                    _status = "⚠  Still thinking — please wait…"
                else:
                    _history.append({"role": "user", "text": cmd, "ts": _ts()})
                    _pending_thread = threading.Thread(
                        target=_run_query_async,
                        args=(agent, cmd, show_trace),
                        daemon=True,
                    )
                    _pending_thread.start()

            time.sleep(0.125)

    _restore()
    print(Fore.CYAN + Style.BRIGHT + "\n  Agent Adda closed. Goodbye!\n")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Agent Adda — NSE Market Research Chat")
    parser.add_argument("--query",  "-q", type=str, default="",
                        help="Single query (non-interactive)")
    parser.add_argument("--trace",  "-t", action="store_true",
                        help="Show tool execution trace")
    args = parser.parse_args()

    # Show colorama banner + load agent on the normal screen
    print_banner()
    print(Fore.CYAN + "  Loading Agent Adda…", end="\r")
    from terminal.agent import Agent
    agent = Agent()
    print(Fore.GREEN + Style.BRIGHT + f"  ✓ Agent Adda ready" +
          Fore.WHITE + Style.DIM   + f"  │  backend: {agent.backend_name}" + " " * 20)
    print()

    if args.query:
        _single_query(agent, args.query, args.trace)
        return

    # Brief pause so user can read the banner, then clear for the TUI
    time.sleep(1.2)
    console.clear()   # clean slate so Live fills the full screen from row 0

    try:
        _chat_tui(agent, args.trace)
    except KeyboardInterrupt:
        print(Fore.CYAN + Style.BRIGHT + "\n  Agent Adda closed.\n")


if __name__ == "__main__":
    main()
