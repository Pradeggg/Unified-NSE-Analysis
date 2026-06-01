#!/usr/bin/env python3
"""
PG-HELPSMOKE: Comprehensive smoke test for every command in terminal/help.py.

Drives the agent via the existing non-interactive entry point
``python nse_agent.py --query "<cmd>" --no-briefing --skip-readiness``.
This is far cleaner than pexpect-driving a prompt_toolkit REPL.

Verification per command (the "exit cleanly + non-empty + no traceback"
contract the user picked):
  1. subprocess exits within timeout
  2. stdout/stderr is non-trivial (>40 bytes after stripping ANSI)
  3. no ``Traceback (most recent call last):`` anywhere in output

Two phases:
  A. INDIVIDUAL — one representative command per help section
     (with a curated safe-list — no /email send, no /screenshot,
     no /monitor start, no /refresh full, no /voice-mode on, etc.)
  B. COMBOS — multi-step pipelines (pipes, --dry-run mails, follow-ups
     within a single --query string when the agent supports it).

Run:
    cd /Users/pgorai/Documents/Projects/Unified-NSE-Analysis
    source .venv/bin/activate
    python tests/run_help_catalog_smoke.py            # all sections
    python tests/run_help_catalog_smoke.py --section charts
    python tests/run_help_catalog_smoke.py --only-combos
    python tests/run_help_catalog_smoke.py --timeout 180
    python tests/run_help_catalog_smoke.py --json results.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parent.parent
AGENT = ROOT / "nse_agent.py"
VENV_PY = ROOT / ".venv" / "bin" / "python"
PYTHON = str(VENV_PY) if VENV_PY.exists() else sys.executable

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
TRACEBACK_TOKEN = "Traceback (most recent call last)"

# ─────────────────────────────────────────────────────────────────────────────
# PG-HELPSMOKE: Safe representative command per section.
#   - one or two commands per section (breadth, not depth)
#   - no destructive / long-running / network-mutating commands
#   - --dry-run for /email so Outlook never opens
#   - skip /screenshot, /voice-mode on, /monitor start, /refresh full,
#     /ask-voice, /alert add (mutates state), /youtube transcribe (downloads),
#     /export pdf (slow), /refresh-data (mutates DB)
# ─────────────────────────────────────────────────────────────────────────────
INDIVIDUAL: list[tuple[str, str]] = [
    # section,                  command
    ("modes",                   "/auto"),
    ("modes",                   "/eod"),
    ("screens",                 "/screen stage2"),
    ("screens",                 "/screen momentum"),
    ("mtf",                     "/mtf RELIANCE"),
    ("scan",                    "/scan orb"),
    ("charts",                  "/chart RELIANCE 3mo"),
    ("fno",                     "/options NIFTY"),
    ("fno",                     "/oi NIFTY"),
    ("search",                  "/search RELIANCE news"),
    ("search",                  "/results-feed --weeks 2"),
    ("learn",                   "/learn PE ratio"),
    ("learn",                   "/define ROCE"),
    ("youtube",                 "/youtube channels"),
    ("forensic",                "/forensic RELIANCE"),
    ("forensic",                "/canslim RELIANCE"),
    ("email",                   "/email sector --to test@example.com --dry-run"),
    ("events",                  "/events RELIANCE"),
    ("macro",                   "/heat"),
    ("macro",                   "/cycle"),
    ("macro",                   "/dashboard"),
    ("macro",                   "/voice script"),
    ("macro",                   "/us indices"),
    ("monitors",                "/monitor status"),
    ("monitors",                "/monitor list"),
    ("monitors",                "/alert list"),
    ("ric",                     "/ric"),
    ("ric",                     "/ric sherlock RELIANCE"),
    ("portfolio",               "/pnl"),
    ("company",                 "/company-xray DMART"),
    ("analyze",                 "/analyze RELIANCE"),
    ("reports",                 "/report sector-rotation"),
    ("reports",                 "/report technical RELIANCE"),
    ("strategy_lab",            "/backtest list"),
    ("strategy_lab",            "/strategy-lab validate"),
    ("data",                    "/data-status"),
    ("data",                    "/doctor"),
    ("data",                    "/refresh status"),
    ("data",                    "/refresh-data --check"),
    ("data",                    "/data-coverage NIFTY500"),
    ("prompts",                 "/prompts"),
    ("prompts",                 "/prompts intraday"),
    ("commands",                "/commands"),
    ("commands",                "/commands alert"),
    ("export",                  "/export html"),
    ("appearance",              "/theme"),
    ("appearance",              "/scale"),
    ("session",                 "/help"),
    ("session",                 "/help charts"),
    ("session",                 "/help rsi"),
    ("session",                 "/model"),
    ("session",                 "/context"),
]

# Logical combinations.  Each combo is a list of commands run sequentially
# (each as its own --query, since the REPL session is per-process).
# For true single-process pipelines we use the agent's native `|` syntax.
COMBOS: list[tuple[str, list[str]]] = [
    ("resolve_then_chart_then_forensic", [
        "/chart RELIANCE 3mo",
        "/forensic RELIANCE",
        "/search RELIANCE news",
    ]),
    ("ric_sherlock_then_report", [
        "/ric sherlock TCS",
        "/report technical TCS",
    ]),
    ("mtf_then_dryrun_email_pipe", [
        # Native | pipe inside a single --query
        '/mtf RELIANCE | /email --to test@example.com --dry-run',
    ]),
    ("scan_then_screen_then_dashboard", [
        "/scan momentum",
        "/screen highrs",
        "/dashboard",
    ]),
    ("company_index_then_xray", [
        # No --include-documents — keep it bounded and read-only.
        "/company-index DMART --max-pages 3 --document-limit 0",
        "/company-xray DMART",
    ]),
    ("learn_then_compare", [
        "/learn PE ratio",
        "/compare ROCE ROE",
    ]),
    ("events_then_results_feed", [
        "/events NIFTY 50",
        "/results-feed --weeks 2",
    ]),
    ("doctor_then_refresh_status", [
        "/doctor",
        "/refresh status",
        "/data-status",
    ]),
]


# ─────────────────────────────────────────────────────────────────────────────
# Runner
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class TestResult:
    section: str
    command: str
    exit_code: int
    duration_s: float
    bytes_out: int
    passed: bool
    failure_reason: str = ""
    stdout_tail: str = field(default="", repr=False)

    @property
    def status(self) -> str:
        return "PASS" if self.passed else "FAIL"


def _strip_ansi(s: str) -> str:
    return ANSI_RE.sub("", s)


def run_command(cmd: str, *, section: str, timeout: int) -> TestResult:
    """Spawn the agent with ``--query cmd`` and grade the result."""
    env = os.environ.copy()
    # Quiet down: skip readiness + briefing; disable any voice/screenshot side
    # effects that might pop GUI prompts.
    env.setdefault("AGENT_ADDA_DISABLE_VOICE", "1")
    env.setdefault("AGENT_ADDA_NO_OUTLOOK", "1")

    argv = [
        PYTHON, str(AGENT),
        "--no-briefing",
        "--skip-readiness",
        "--query", cmd,
    ]
    t0 = time.monotonic()
    try:
        # PG-HELPSMOKE: stdin=DEVNULL — without this, after ~24 subprocesses
        # the parent's fd 0 ends up closed (one of the agent subprocesses
        # closes it) and every subsequent child dies with
        # "OSError: [Errno 9] Bad file descriptor" during init_sys_streams.
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(ROOT),
            env=env,
            stdin=subprocess.DEVNULL,
        )
        rc = proc.returncode
        out = (proc.stdout or "") + (proc.stderr or "")
    except subprocess.TimeoutExpired as ex:
        out = (ex.stdout or "") + (ex.stderr or "")
        rc = -1
        return TestResult(
            section=section, command=cmd, exit_code=rc,
            duration_s=round(time.monotonic() - t0, 2),
            bytes_out=len(out or ""), passed=False,
            failure_reason=f"timeout after {timeout}s",
            stdout_tail=_strip_ansi(out)[-400:] if out else "",
        )

    dur = round(time.monotonic() - t0, 2)
    clean = _strip_ansi(out)
    bytes_out = len(clean.strip())
    reasons: list[str] = []
    if rc != 0:
        reasons.append(f"exit={rc}")
    if bytes_out < 40:
        reasons.append(f"output too small ({bytes_out} bytes)")
    if TRACEBACK_TOKEN in clean:
        reasons.append("traceback detected")
    passed = not reasons
    return TestResult(
        section=section, command=cmd, exit_code=rc, duration_s=dur,
        bytes_out=bytes_out, passed=passed,
        failure_reason="; ".join(reasons),
        stdout_tail=clean[-400:] if not passed else "",
    )


def _filter(cases: list[tuple[str, str]], section: str | None) -> list[tuple[str, str]]:
    if not section:
        return cases
    return [c for c in cases if c[0] == section]


def _print_row(r: TestResult) -> None:
    mark = "\033[32m✓\033[0m" if r.passed else "\033[31m✗\033[0m"
    # PG-HELPSMOKE: flush=True so progress streams through pipes/tee
    print(f"  {mark} [{r.section:14s}] {r.command:48s}  "
          f"{r.duration_s:6.2f}s  rc={r.exit_code:>3}  bytes={r.bytes_out:>6}"
          + (f"  ← {r.failure_reason}" if not r.passed else ""),
          flush=True)


def run_individual(section: str | None, timeout: int, sink) -> list[TestResult]:
    cases = _filter(INDIVIDUAL, section)
    print(f"\n══ Phase A — INDIVIDUAL  ({len(cases)} cases, timeout={timeout}s) ══", flush=True)
    results: list[TestResult] = []
    for sec, cmd in cases:
        r = run_command(cmd, section=sec, timeout=timeout)
        _print_row(r)
        results.append(r)
        if sink is not None:
            sink.write(json.dumps(asdict(r)) + "\n")
            sink.flush()
    return results


def run_combos(timeout: int, sink) -> list[TestResult]:
    print(f"\n══ Phase B — COMBOS  ({len(COMBOS)} chains, timeout={timeout}s/step) ══", flush=True)
    results: list[TestResult] = []
    for name, steps in COMBOS:
        print(f"  ▸ combo: {name}", flush=True)
        chain_failed = False
        for i, cmd in enumerate(steps, 1):
            r = run_command(cmd, section=f"combo:{name}#{i}", timeout=timeout)
            _print_row(r)
            results.append(r)
            if sink is not None:
                sink.write(json.dumps(asdict(r)) + "\n")
                sink.flush()
            if not r.passed:
                chain_failed = True
        if chain_failed:
            print(f"     \033[33m⚠ chain '{name}' had failures\033[0m", flush=True)
    return results


def summarize(results: list[TestResult]) -> dict:
    passed = sum(1 for r in results if r.passed)
    failed = [r for r in results if not r.passed]
    print(f"\n══ Summary ══  total={len(results)}  passed={passed}  failed={len(failed)}")
    if failed:
        print("Failures:")
        for r in failed:
            print(f"  - [{r.section}] {r.command}  ({r.failure_reason})")
    return {
        "total": len(results),
        "passed": passed,
        "failed": len(failed),
        "results": [asdict(r) for r in results],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="PG-HELPSMOKE comprehensive help-catalog smoke")
    ap.add_argument("--section", help="Run only one section's commands")
    ap.add_argument("--only-combos", action="store_true", help="Skip Phase A")
    ap.add_argument("--only-individual", action="store_true", help="Skip Phase B")
    ap.add_argument("--timeout", type=int, default=120, help="Per-command timeout in seconds")
    ap.add_argument("--json", dest="json_path", help="Write full results to JSON file")
    args = ap.parse_args()

    if not AGENT.exists():
        print(f"ERROR: cannot find {AGENT}", file=sys.stderr)
        return 2

    results: list[TestResult] = []
    # PG-HELPSMOKE: incremental JSONL sink so partial progress is preserved
    # even if the run is killed/timed out.
    sink_path = Path(args.json_path).with_suffix(".jsonl") if args.json_path else Path("tests/_help_smoke_results.jsonl")
    sink_path.parent.mkdir(parents=True, exist_ok=True)
    with open(sink_path, "w") as sink:
        if not args.only_combos:
            results.extend(run_individual(args.section, args.timeout, sink))
        if not args.only_individual and not args.section:
            results.extend(run_combos(args.timeout, sink))

    summary = summarize(results)
    if args.json_path:
        Path(args.json_path).write_text(json.dumps(summary, indent=2))
        print(f"\nWrote JSON results → {args.json_path}")
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
