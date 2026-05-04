#!/usr/bin/env python3
"""
nse_agent.py — Agent Adda CLI

Usage:
  python nse_agent.py                        # interactive REPL
  python nse_agent.py --query "show me RELIANCE"
  python nse_agent.py --query "stage 2 stocks" --trace
  python nse_agent.py --query "how is market today"
  python nse_agent.py --query "Tata Motors news" --trace

Environment:
  OPENAI_API_KEY  — enables OpenAI GPT-4o-mini backend
  OPENAI_MODEL    — override model (default: gpt-4o-mini)
  OLLAMA_HOST     — Ollama server URL (default: http://localhost:11434)
  OLLAMA_MODEL    — Ollama model (default: granite4:latest)
"""

from __future__ import annotations

import argparse
import sys

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich import box
from rich.text import Text

console = Console()

WELCOME = """
┌─────────────────────────────────────────────────────┐
│  🏛  Agent Adda — NSE Market Research Assistant      │
│                                                     │
│  Ask me about stocks, sectors, market breadth,      │
│  screeners, data health, and latest catalysts.      │
│                                                     │
│  Examples:                                          │
│    show me the latest on RELIANCE                   │
│    what stage 2 stocks are there?                   │
│    how is the market today?                         │
│    Tata Motors technical setup                      │
│    strong buy signals right now                     │
│    sector context for pharma                        │
│    data health                                      │
│                                                     │
│  Type 'exit' or Ctrl+C to quit.                     │
│  Add --trace to see tool execution trace.           │
└─────────────────────────────────────────────────────┘
"""


def _print_trace(trace: list[dict]) -> None:
    tbl = Table(box=box.SIMPLE, header_style="bold dim", expand=True)
    tbl.add_column("Tool",   style="cyan",  width=26)
    tbl.add_column("Args",   style="dim",   width=30)
    tbl.add_column("Status", style="white", width=30)

    for t in trace:
        tool   = t.get("tool", "—")
        args   = str(t.get("args", {}))[:40]
        result = t.get("result", {})
        err    = result.get("error", "")
        if err:
            status = Text(f"ERROR: {err[:40]}", style="red")
        else:
            # Show a brief summary of result
            keys = [k for k in result if k not in ("error",)]
            status = Text(f"ok — {', '.join(keys[:4])}", style="green")
        tbl.add_row(tool, args, status)

    console.print(Panel(tbl, title="[bold dim]Tool Trace[/bold dim]", border_style="dim"))


def run_query(agent, query: str, show_trace: bool) -> None:
    with console.status(f"[bold cyan]Agent Adda thinking…[/bold cyan]"):
        result = agent.query(query, show_trace=show_trace)

    console.print()
    console.print(Rule(f"[dim]{result['backend']}[/dim]", style="dim"))

    answer = result.get("answer", "")
    # If it looks like markdown, render it; otherwise plain
    if any(c in answer for c in ["**", "##", "- ", "* ", "```"]):
        console.print(Markdown(answer))
    else:
        console.print(answer)

    if show_trace and result.get("trace"):
        _print_trace(result["trace"])

    console.print()


def main():
    parser = argparse.ArgumentParser(description="Agent Adda — NSE Market Research CLI")
    parser.add_argument("--query",  "-q", type=str, default="",
                        help="Single query (non-interactive mode)")
    parser.add_argument("--trace",  "-t", action="store_true",
                        help="Show tool execution trace")
    args = parser.parse_args()

    # Lazy import agent so startup is fast
    console.print("[dim]Loading Agent Adda…[/dim]", end="\r")
    from terminal.agent import Agent
    agent = Agent()
    console.print(f"[bold cyan]Agent Adda ready[/bold cyan]  "
                  f"[dim]backend: {agent.backend_name}[/dim]" + " " * 20)

    if args.query:
        run_query(agent, args.query, args.trace)
        return

    # Interactive REPL
    console.print(WELCOME, style="bold blue")

    while True:
        try:
            user_input = console.input("[bold cyan]❯ [/bold cyan]").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[bold cyan]Agent Adda closed. Goodbye![/bold cyan]")
            sys.exit(0)

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit", "q", ":q"):
            console.print("[bold cyan]Agent Adda closed. Goodbye![/bold cyan]")
            break

        # Allow inline --trace flag in REPL
        show_trace = args.trace or user_input.endswith(" --trace")
        query = user_input.removesuffix(" --trace").strip()

        try:
            run_query(agent, query, show_trace)
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")


if __name__ == "__main__":
    main()
