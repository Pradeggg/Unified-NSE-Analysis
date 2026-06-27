from __future__ import annotations

import argparse
import json
import re
import shlex

from terminal.governance.engine import evaluate_governance
from terminal.governance.markdown import render_markdown


USAGE = """## Governance Evaluation

Usage: `/governance INFY`

Examples:
- `/governance INFY`
- `/gov INFY`
- `/governance INFY --live`
- `/governance INFY --llm`
- `/governance INFY --live --llm`
- `/governance INFY --json`

Research only. Not investment advice."""


def handle_governance_command(text: str) -> str:
    args = _parse_args(text)
    if args is None:
        return USAGE

    report = evaluate_governance(
        args.symbol.upper(),
        use_llm=bool(args.llm),
        refresh_live=bool(args.live),
    )
    if args.json:
        return json.dumps(report.to_dict(), indent=2, sort_keys=True)
    return render_markdown(report)


def _parse_args(text: str) -> argparse.Namespace | None:
    raw = re.sub(
        r"^\s*/(?:governance|gov)\b",
        "",
        text or "",
        flags=re.IGNORECASE,
    ).strip()
    try:
        tokens = shlex.split(raw)
    except ValueError:
        return None
    if not tokens or not any(not token.startswith("-") for token in tokens):
        return None

    parser = argparse.ArgumentParser(prog="/governance", add_help=False)
    parser.add_argument("symbol")
    parser.add_argument("--live", "--refresh-live", dest="live", action="store_true")
    parser.add_argument("--llm", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("-h", "--help", action="store_true")
    try:
        args = parser.parse_args(tokens)
    except SystemExit:
        return None
    if getattr(args, "help", False):
        return None
    return args
