#!/usr/bin/env python3
"""Publish Agent Adda report artifacts to a dedicated Git branch.

The source branch intentionally ignores generated reports. This script builds a
small static catalog from the latest report artifacts and commits it to a
separate branch, suitable for GitHub Pages or a website ingestion job.

Default target:
  remote: agentadda
  branch: agentadda-reports
  worktree: .worktrees/agentadda-reports-publish
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import shutil
import subprocess
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_WORKTREE = ROOT / ".worktrees" / "agentadda-reports-publish"


@dataclass(frozen=True)
class ReportSpec:
    category: str
    name: str
    source: str
    target: str
    required: bool = False


@dataclass
class PublishedReport:
    category: str
    name: str
    source: str
    path: str
    bytes: int
    sha256: str
    modified_at: str


REPORT_SPECS: tuple[ReportSpec, ...] = (
    ReportSpec("daily/eod-market", "EOD Market Report HTML", "reports/latest/eod_market_report.html", "daily/eod-market/eod_market_report.html", True),
    ReportSpec("daily/eod-market", "EOD Market Report Markdown", "reports/latest/eod_market_report.md", "daily/eod-market/eod_market_report.md"),
    ReportSpec("daily/sector-rotation", "Sector Rotation HTML", "reports/latest/sector_rotation.html", "daily/sector-rotation/sector_rotation.html", True),
    ReportSpec("daily/sector-rotation", "Sector Rotation Markdown", "reports/latest/sector_rotation.md", "daily/sector-rotation/sector_rotation.md"),
    ReportSpec("daily/sector-rotation", "Sector Rotation PDF", "reports/latest/sector_rotation.pdf", "daily/sector-rotation/sector_rotation.pdf"),
    ReportSpec("daily/top-picks", "Top Investment Picks HTML", "reports/latest/top_picks.html", "daily/top-picks/top_picks.html", True),
    ReportSpec("daily/top-picks", "Top Investment Picks Markdown", "reports/latest/top_picks.md", "daily/top-picks/top_picks.md"),
    ReportSpec("daily/stage2", "Stage 2 Tracker HTML", "reports/latest/stage2_tracker.html", "daily/stage2/stage2_tracker.html", True),
    ReportSpec("daily/stage2", "Stage 2 TradingView Export", "reports/latest/stage2_buy_tradingview.txt", "daily/stage2/stage2_buy_tradingview.txt"),
    ReportSpec("daily/strategy-lab", "Portfolio Strategy Lab HTML", "reports/latest/portfolio_strategy_lab.html", "daily/strategy-lab/portfolio_strategy_lab.html", True),
    ReportSpec("daily/paper-trading", "Paper Trading Performance HTML", "reports/latest/paper_trading_performance.html", "daily/paper-trading/paper_trading_performance.html"),
    ReportSpec("daily/paper-trading", "Paper Trading Performance Markdown", "reports/latest/paper_trading_performance.md", "daily/paper-trading/paper_trading_performance.md"),
    ReportSpec("daily/portfolio", "Portfolio Analysis HTML", "reports/latest/portfolio_analysis.html", "daily/portfolio/portfolio_analysis.html"),
    ReportSpec("daily/results", "Results Analysis HTML", "reports/latest/results_analysis.html", "daily/results/results_analysis.html"),
    ReportSpec("daily/global", "US / Global Market Report HTML", "reports/latest/us_market_report.html", "daily/global/us_market_report.html"),
    ReportSpec("intraday/alerts", "Intraday F&O Alert Latest", "logs/intraday_alerts_latest.md", "intraday/alerts/intraday_alerts_latest.md"),
    ReportSpec("intraday/monitor", "3-Minute Intraday Monitor Latest", "logs/intraday_monitor_3min_latest.md", "intraday/monitor/intraday_monitor_3min_latest.md"),
    ReportSpec("intraday/patterns", "VCP / Breakout / Retest Monitor Latest", "logs/intraday_pattern_monitor_latest.md", "intraday/patterns/intraday_pattern_monitor_latest.md"),
)


def run(cmd: list[str], *, cwd: Path = ROOT, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, check=check, text=True, capture_output=True)


def git_output(args: list[str], *, cwd: Path = ROOT, check: bool = True) -> str:
    try:
        result = run(["git", *args], cwd=cwd, check=check)
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        stdout = (exc.stdout or "").strip()
        detail = "\n".join(part for part in (stdout, stderr) if part)
        if detail:
            raise RuntimeError(f"git {' '.join(args)} failed:\n{detail}") from exc
        raise
    return result.stdout.strip()


def remote_branch_exists(remote: str, branch: str) -> bool:
    result = run(["git", "ls-remote", "--heads", remote, branch], cwd=ROOT, check=False)
    return bool(result.stdout.strip())


def ensure_publish_worktree(worktree: Path, remote: str, branch: str) -> None:
    worktree.parent.mkdir(parents=True, exist_ok=True)
    if (worktree / ".git").exists():
        git_output(["fetch", remote], cwd=worktree, check=False)
        return

    if remote_branch_exists(remote, branch):
        git_output(["fetch", remote, branch])
        git_output(["worktree", "add", "-B", branch, str(worktree), f"{remote}/{branch}"])
        return

    git_output(["worktree", "add", str(worktree), "HEAD"])
    git_output(["switch", "--orphan", branch], cwd=worktree)
    for child in worktree.iterdir():
        if child.name == ".git":
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()
    (worktree / ".gitignore").write_text(".DS_Store\n", encoding="utf-8")
    git_output(["add", ".gitignore"], cwd=worktree)
    git_output(["commit", "-m", "Initialize Agent Adda report publishing branch"], cwd=worktree)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def clean_publish_area(worktree: Path) -> None:
    for name in ("daily", "intraday", "manifest.json", "index.html", "README.md"):
        target = worktree / name
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()


def copy_reports(worktree: Path) -> tuple[list[PublishedReport], list[str]]:
    published: list[PublishedReport] = []
    missing: list[str] = []
    for spec in REPORT_SPECS:
        source = ROOT / spec.source
        if not source.exists():
            msg = f"{spec.source} ({spec.name})"
            missing.append(msg)
            continue
        target = worktree / spec.target
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        stat = source.stat()
        published.append(
            PublishedReport(
                category=spec.category,
                name=spec.name,
                source=spec.source,
                path=spec.target,
                bytes=stat.st_size,
                sha256=sha256(source),
                modified_at=datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
            )
        )
    required_missing = {m for m in missing if any(spec.required and m.startswith(spec.source) for spec in REPORT_SPECS)}
    if required_missing:
        raise FileNotFoundError("Required report(s) missing: " + ", ".join(sorted(required_missing)))
    return published, missing


def render_index(worktree: Path, published: list[PublishedReport], missing: list[str]) -> None:
    generated_at = datetime.now().isoformat(timespec="seconds")
    grouped: dict[str, list[PublishedReport]] = {}
    for item in published:
        grouped.setdefault(item.category, []).append(item)

    rows: list[str] = []
    for category, items in sorted(grouped.items()):
        rows.append(f"<h2>{html.escape(category)}</h2>")
        rows.append("<table><thead><tr><th>Report</th><th>Artifact</th><th>Size</th><th>Modified</th></tr></thead><tbody>")
        for item in sorted(items, key=lambda x: x.name):
            rows.append(
                "<tr>"
                f"<td>{html.escape(item.name)}</td>"
                f"<td><a href='{html.escape(item.path)}'>{html.escape(item.path)}</a></td>"
                f"<td>{item.bytes:,}</td>"
                f"<td>{html.escape(item.modified_at)}</td>"
                "</tr>"
            )
        rows.append("</tbody></table>")

    missing_html = ""
    if missing:
        missing_html = "<h2>Missing Optional Artifacts</h2><ul>" + "".join(
            f"<li>{html.escape(item)}</li>" for item in missing
        ) + "</ul>"

    index = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Agent Adda Reports</title>
  <style>
    body {{ font-family: Arial, Helvetica, sans-serif; margin: 32px; color: #172033; background: #f7f9fc; }}
    main {{ max-width: 1180px; margin: 0 auto; background: #fff; border: 1px solid #d9e1ee; border-radius: 8px; padding: 24px; }}
    h1 {{ margin-top: 0; }}
    h2 {{ margin-top: 28px; color: #102033; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
    th, td {{ border: 1px solid #d9e1ee; padding: 8px 10px; text-align: left; vertical-align: top; }}
    th {{ background: #e9eef7; }}
    a {{ color: #1d4ed8; text-decoration: none; }}
    .meta {{ color: #64748b; }}
  </style>
</head>
<body>
<main>
  <h1>Agent Adda Report Catalog</h1>
  <p class="meta">Generated at {html.escape(generated_at)} from the Unified-NSE-Analysis workspace.</p>
  <p>Research only. Not investment advice.</p>
  {''.join(rows)}
  {missing_html}
</main>
</body>
</html>
"""
    (worktree / "index.html").write_text(index, encoding="utf-8")
    (worktree / "README.md").write_text(
        "# Agent Adda Report Catalog\n\n"
        f"Generated at {generated_at}.\n\n"
        "This branch is generated by `scripts/publish_reports_to_github.py` from the local report artifacts.\n",
        encoding="utf-8",
    )
    manifest = {
        "generated_at": generated_at,
        "source_repository": git_output(["rev-parse", "--show-toplevel"], check=False),
        "source_commit": git_output(["rev-parse", "HEAD"], check=False),
        "reports": [asdict(item) for item in published],
        "missing_optional": missing,
    }
    (worktree / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def publish(remote: str, branch: str, worktree: Path, *, push: bool) -> None:
    git_output(["add", "."], cwd=worktree)
    status = git_output(["status", "--short"], cwd=worktree)
    if not status:
        print("No report publishing changes to commit.")
        if push:
            git_output(["push", remote, branch], cwd=worktree)
            print(f"Pushed existing {branch} to {remote}.")
        return
    git_output(["commit", "-m", f"Publish Agent Adda reports {datetime.now():%Y-%m-%d %H:%M}"], cwd=worktree)
    print(f"Committed report catalog on branch {branch}.")
    if push:
        git_output(["push", "-u", remote, branch], cwd=worktree)
        print(f"Pushed report catalog to {remote}/{branch}.")
    else:
        print("Push skipped. Re-run with --push to publish to GitHub.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish latest Agent Adda reports to a GitHub branch.")
    parser.add_argument("--remote", default="agentadda", help="Git remote to push to.")
    parser.add_argument("--branch", default="agentadda-reports", help="Publishing branch.")
    parser.add_argument("--worktree", default=str(DEFAULT_WORKTREE), help="Local worktree used for publishing.")
    parser.add_argument("--push", action="store_true", help="Push the publishing branch to the remote.")
    args = parser.parse_args()

    worktree = Path(args.worktree).expanduser()
    if not worktree.is_absolute():
        worktree = (ROOT / worktree).resolve()

    ensure_publish_worktree(worktree, args.remote, args.branch)
    clean_publish_area(worktree)
    published, missing = copy_reports(worktree)
    render_index(worktree, published, missing)
    publish(args.remote, args.branch, worktree, push=args.push)
    print(f"Published files: {len(published)}")
    print(f"Worktree: {worktree}")
    if missing:
        print("Missing optional artifacts:")
        for item in missing:
            print(f"  - {item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
