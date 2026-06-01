"""Interactive CLI for the stock email agent."""
from __future__ import annotations

import argparse
import logging
import sys
from typing import List, Optional

from .analyzer import AnalysisResult, analyze_email, chat_followup
from .classifier import classify
from .config import load_config
from .email_client import EmailMessage, FetchOptions, GmailIMAPClient
from .llm_client import LLMClient

try:
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich.prompt import IntPrompt, Prompt
    from rich.table import Table
    _HAS_RICH = True
except ImportError:
    _HAS_RICH = False


def _print(console, obj):
    if _HAS_RICH:
        console.print(obj)
    else:
        print(obj)


def _build_fetch_options(args: argparse.Namespace) -> FetchOptions:
    opts = FetchOptions(
        last_n=args.last_n,
        since_days=args.since_days,
        unread_only=args.unread,
        senders=args.sender or None,
        keywords=args.keyword or None,
    )
    return opts


def _interactive_scope(console) -> FetchOptions:
    _print(console, "[bold]Choose scan scope[/bold]" if _HAS_RICH else "Choose scan scope")
    _print(console, "  1) Last N emails")
    _print(console, "  2) Emails from last X days (recommended)")
    _print(console, "  3) All unread stock-related emails")
    _print(console, "  4) Custom combination")
    choice = Prompt.ask("Selection", choices=["1", "2", "3", "4"], default="2") if _HAS_RICH else input("Selection [2]: ") or "2"
    opts = FetchOptions()
    if choice == "1":
        n = IntPrompt.ask("How many recent emails to scan?", default=50) if _HAS_RICH else int(input("N [50]: ") or 50)
        opts.last_n = n
    elif choice == "2":
        d = IntPrompt.ask("Days back", default=7) if _HAS_RICH else int(input("Days [7]: ") or 7)
        opts.since_days = d
    elif choice == "3":
        opts.unread_only = True
    else:
        opts.last_n = IntPrompt.ask("Cap on emails (0 = no cap)", default=200) if _HAS_RICH else int(input("Cap [200]: ") or 200)
        if opts.last_n == 0:
            opts.last_n = None
        opts.since_days = IntPrompt.ask("Days back (0 = ignore)", default=14) if _HAS_RICH else int(input("Days [14]: ") or 14)
        if opts.since_days == 0:
            opts.since_days = None
        unread = Prompt.ask("Unread only?", choices=["y", "n"], default="n") if _HAS_RICH else input("Unread only? [n]: ") or "n"
        opts.unread_only = unread.lower().startswith("y")
    return opts


def _render_inbox(console, msgs: List[EmailMessage]) -> None:
    if _HAS_RICH:
        table = Table(title=f"{len(msgs)} stock-related emails", show_lines=False)
        table.add_column("#", justify="right", style="cyan")
        table.add_column("Date")
        table.add_column("From", overflow="fold")
        table.add_column("Subject", overflow="fold")
        table.add_column("Categories")
        for i, m in enumerate(msgs, 1):
            c = classify(m)
            table.add_row(str(i), m.short_date, m.sender[:40], m.subject[:80], ",".join(c.categories) or "-")
        console.print(table)
    else:
        for i, m in enumerate(msgs, 1):
            c = classify(m)
            print(f"{i:>3} | {m.short_date} | {m.sender[:40]:40s} | {m.subject[:80]} | {','.join(c.categories) or '-'}")


def _render_analysis(console, result: AnalysisResult) -> None:
    header = f"{result.email.subject}\n{result.email.sender} — {result.email.short_date}"
    if _HAS_RICH:
        console.print(Panel.fit(header, style="bold magenta"))
        if result.docs:
            console.print(f"[dim]Fetched {len(result.docs)} linked document(s)[/dim]")
        if result.error:
            console.print(f"[red]LLM error: {result.error}[/red]")
        else:
            console.print(Markdown(result.summary_markdown))
    else:
        print("=" * 80)
        print(header)
        if result.docs:
            print(f"Fetched {len(result.docs)} linked docs")
        if result.error:
            print(f"LLM error: {result.error}")
        else:
            print(result.summary_markdown)
        print("=" * 80)


def _followup_loop(console, base: AnalysisResult, llm: LLMClient) -> None:
    history: List[dict] = []
    _print(console, "\n[dim]Ask follow-up questions about this email. Type :back, :next, or :quit.[/dim]" if _HAS_RICH else
                    "\nFollow-up Q&A. Commands: :back :next :quit")
    while True:
        try:
            q = Prompt.ask("You") if _HAS_RICH else input("You> ")
        except (EOFError, KeyboardInterrupt):
            return
        if not q.strip():
            continue
        cmd = q.strip().lower()
        if cmd in (":back", ":next", ":quit", ":q"):
            raise _CtrlFlow(cmd)
        answer = chat_followup(base, q, history, llm)
        history.append({"role": "user", "content": q})
        history.append({"role": "assistant", "content": answer})
        if _HAS_RICH:
            console.print(Panel(Markdown(answer), title="Assistant", border_style="green"))
        else:
            print(f"Assistant>\n{answer}\n")


class _CtrlFlow(Exception):
    def __init__(self, cmd: str):
        self.cmd = cmd


def run(args: argparse.Namespace) -> int:
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = load_config()
    console = Console() if _HAS_RICH else None

    if args.interactive_scope or not any([args.last_n, args.since_days, args.unread]):
        opts = _interactive_scope(console)
    else:
        opts = _build_fetch_options(args)

    _print(console, f"[bold]Connecting to {cfg.email.host} as {cfg.email.user or '(missing user)'}…[/bold]"
           if _HAS_RICH else f"Connecting to {cfg.email.host}…")
    try:
        with GmailIMAPClient(cfg.email) as gm:
            msgs = gm.fetch(opts)
    except Exception as exc:
        _print(console, f"[red]Email fetch failed: {exc}[/red]" if _HAS_RICH else f"Email fetch failed: {exc}")
        return 2

    if not msgs:
        _print(console, "No matching emails found.")
        return 0

    _render_inbox(console, msgs)

    llm = LLMClient(cfg.llm)
    _print(console, f"\n[dim]LLM provider: {cfg.llm.provider}[/dim]" if _HAS_RICH else f"LLM provider: {cfg.llm.provider}")

    if args.summarize_all:
        for m in msgs:
            cls = classify(m)
            res = analyze_email(m, cls, cfg, llm, fetch_links=not args.no_fetch_links)
            _render_analysis(console, res)
        return 0

    # Interactive selection loop
    idx = 0
    while True:
        try:
            sel = Prompt.ask("\nEnter email # to analyse (or 'q' to quit, 'a' for all)") if _HAS_RICH else \
                  input("\nEmail # ('q' quit, 'a' all)> ")
        except (EOFError, KeyboardInterrupt):
            return 0
        sel = sel.strip().lower()
        if sel in ("q", "quit", ":q"):
            return 0
        if sel in ("a", "all"):
            for m in msgs:
                cls = classify(m)
                res = analyze_email(m, cls, cfg, llm, fetch_links=not args.no_fetch_links)
                _render_analysis(console, res)
            continue
        try:
            idx = int(sel) - 1
            if not (0 <= idx < len(msgs)):
                raise ValueError
        except ValueError:
            _print(console, "Invalid selection.")
            continue
        m = msgs[idx]
        cls = classify(m)
        res = analyze_email(m, cls, cfg, llm, fetch_links=not args.no_fetch_links)
        _render_analysis(console, res)
        try:
            _followup_loop(console, res, llm)
        except _CtrlFlow as cf:
            if cf.cmd in (":quit", ":q"):
                return 0
            if cf.cmd == ":next" and idx + 1 < len(msgs):
                idx += 1
                # fall through to analyse next on next iteration via direct call
                m = msgs[idx]
                cls = classify(m)
                res = analyze_email(m, cls, cfg, llm, fetch_links=not args.no_fetch_links)
                _render_analysis(console, res)
                try:
                    _followup_loop(console, res, llm)
                except _CtrlFlow as cf2:
                    if cf2.cmd in (":quit", ":q"):
                        return 0
            # :back -> just loop to selection prompt


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="stock-email-agent",
        description="Scan Gmail for stock-related emails, summarise with an LLM, and chat.",
    )
    p.add_argument("--last-n", type=int, help="Scan the last N emails (newest first)")
    p.add_argument("--since-days", type=int, help="Scan emails from the last X days")
    p.add_argument("--unread", action="store_true", help="Only unread emails")
    p.add_argument("--sender", action="append", help="Add a sender filter (repeatable)")
    p.add_argument("--keyword", action="append", help="Override keyword filter (repeatable)")
    p.add_argument("--summarize-all", action="store_true", help="Auto-summarise every matched email")
    p.add_argument("--no-fetch-links", action="store_true", help="Skip fetching linked filings")
    p.add_argument("--interactive-scope", action="store_true", help="Force interactive scope picker")
    p.add_argument("--log-level", default="WARNING", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return run(args)
    except KeyboardInterrupt:
        print("\nInterrupted.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
