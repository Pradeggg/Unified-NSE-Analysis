#!/usr/bin/env python3
"""Build and publish the weekend broader market review."""
from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable


def run(cmd: list[str]) -> None:
    print("$", " ".join(cmd))
    subprocess.run(cmd, cwd=ROOT, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build and publish the weekend market review.")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"), help="Report date in YYYY-MM-DD format.")
    parser.add_argument("--dry-run", action="store_true", help="Build only; skip publish.")
    args = parser.parse_args()

    date_iso = args.date
    date_dash = date_iso
    date_stamp = date_iso.replace("-", "")

    build_cmd = [PYTHON, "scripts/build_broader_market_analysis.py"]
    run(build_cmd)

    if args.dry_run:
        print("[dry-run] skipping publish step")
        return 0

    html_path = ROOT / "reports" / "latest" / f"broader_market_analysis_{date_stamp}.html"
    publish_cmd = [
        PYTHON,
        "scripts/push_to_www.py",
        "--html",
        str(html_path),
        "--slug",
        f"broader-market-analysis-{date_dash}",
        "--title",
        f"Weekend Market Review — India & Global — {datetime.strptime(date_iso, '%Y-%m-%d').strftime('%d %b %Y')}",
        "--excerpt",
        "Weekend recap of domestic breadth, global cues, sector leadership, flows, results, and the main risks to watch into next week.",
        "--type",
        "deep-research",
        "--tickers",
        "NIFTY50,BANKNIFTY,NIFTYIT,NIFTYAUTO,NIFTYREALTY",
        "--sector",
        "All Sectors,Indices",
        "--tags",
        "Weekend Review,Market Overview,Global,Domestic,Breadth,Flows,Results",
        "--read-time",
        "8 min read",
        "--date",
        date_iso,
        "--push",
    ]
    run(publish_cmd)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
