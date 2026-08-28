#!/usr/bin/env python3
"""Generate and publish a scheduled market report when NSE is open."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WWW_REPO = Path.home() / "Documents" / "Projects" / "agentadda-www"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terminal.market_calendar import market_session_status  # noqa: E402


def _run(cmd: list[str], *, env: dict[str, str]) -> None:
    print("+ " + " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=ROOT, env=env, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run an Agent Adda market workflow only when the NSE "
            "cash market is on a trading day and open."
        )
    )
    parser.add_argument(
        "--variant",
        choices=("morning", "midday"),
        default="morning",
        help="Report variant to generate (default: morning).",
    )
    parser.add_argument(
        "--force-market",
        action="store_true",
        help="Bypass the market-open guard for manual testing.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Check the guard and print intended actions without generating or publishing.",
    )
    parser.add_argument(
        "--skip-publish",
        action="store_true",
        help="Generate the HTML but do not post it to agentadda.in.",
    )
    parser.add_argument(
        "--no-push",
        action="store_true",
        help="Update the website repo locally but do not push to GitHub.",
    )
    parser.add_argument(
        "--no-notify",
        action="store_true",
        help="Do not send the Morning Market email notification after publishing.",
    )
    parser.add_argument(
        "--force-publish",
        action="store_true",
        help="Pass --force to the website publisher quality gate.",
    )
    parser.add_argument(
        "--www-repo",
        type=Path,
        default=Path(os.environ.get("AGENTADDA_WWW_REPO", str(DEFAULT_WWW_REPO))),
        help="Path to the agentadda/www repo.",
    )
    parser.add_argument(
        "--date",
        help="Report date override in YYYY-MM-DD format. Defaults to today's IST date.",
    )
    args = parser.parse_args()

    status = market_session_status()
    date_iso = args.date or status.now_ist.strftime("%Y-%m-%d")

    print(f"[market] {status.clock_label}", flush=True)
    print(f"[market] {status.status_label}", flush=True)
    if not args.force_market and (not status.is_trading_day or not status.is_open):
        print(
            f"[skip] {args.variant.title()} Market not generated because NSE is not in regular trading session.",
            flush=True,
        )
        return 0

    www_repo = args.www_repo.expanduser().resolve()
    print(f"[date] {date_iso}", flush=True)
    print(f"[www] {www_repo}", flush=True)

    if args.dry_run:
        print(f"[dry-run] would generate reports/latest/{args.variant}_market.html", flush=True)
        if args.skip_publish:
            print("[dry-run] publishing is disabled by --skip-publish", flush=True)
        else:
            action = "update website repo locally" if args.no_push else "commit and push to GitHub"
            print(f"[dry-run] would publish {args.variant}-market preset and {action}", flush=True)
        if args.no_notify:
            print("[dry-run] notification disabled by --no-notify", flush=True)
        elif args.skip_publish:
            print("[dry-run] notification would be skipped because publishing is disabled", flush=True)
        else:
            print(f"[dry-run] would email {args.variant}_market notification to configured recipients", flush=True)
        return 0

    from scripts.build_morning_market_report import build_report  # noqa: E402

    html_doc, latest, dated = build_report(args.variant)
    print(f"[report] latest={latest}", flush=True)
    print(f"[report] archive={dated}", flush=True)
    print(f"[report] bytes={len(html_doc):,}", flush=True)

    validation_cmd = [
        sys.executable,
        str(ROOT / "report_validation.py"),
        "--checkpoint",
        f"{args.variant}_market",
        "--skip-llm",
        "--fail-on-high",
    ]
    _run(validation_cmd, env=os.environ.copy())

    if args.skip_publish:
        print("[publish] skipped by --skip-publish", flush=True)
        return 0

    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env["AGENTADDA_WWW_REPO"] = str(www_repo)

    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "push_to_www.py"),
        "--preset",
        f"{args.variant}_market",
        "--date",
        date_iso,
    ]
    if not args.no_push:
        cmd.append("--push")
    if args.no_notify:
        cmd.append("--no-notify")
    if args.force_publish:
        cmd.append("--force")
    _run(cmd, env=env)

    if args.no_push:
        print("[notify] skipped because --no-push was used", flush=True)
    elif args.no_notify:
        print("[notify] skipped by --no-notify", flush=True)
    else:
        print("[notify] handled by scripts/push_to_www.py", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
