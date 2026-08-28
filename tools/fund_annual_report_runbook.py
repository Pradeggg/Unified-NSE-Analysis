#!/usr/bin/env python3
"""
fund_annual_report_runbook.py — Step-by-step annual report workflow for fund holdings

This is a *runner* that orchestrates the long process in safe, resumable steps.

Steps:
  A) Fetch + cache latest Annual Report PDFs (NSE API) and index them into KB:
       .venv/bin/python scripts/fetch_annual_reports.py --fund all --years 1
  B) For each symbol, run page-by-page deep dive (extract + relevant-page QA + synthesis):
       .venv/bin/python tools/annual_report_deep_dive.py SYMBOL

This script reads symbols from data/fund_holdings.json (source of truth for the dashboard).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
VENV_PYTHON = ROOT / ".venv" / "bin" / "python"
HOLDINGS_FILE = ROOT / "data" / "fund_holdings.json"
DEFAULT_PDF_DIR = ROOT / "data" / "annual_reports" / "_inbox"


def _symbols_from_fund_holdings(*, fund: str) -> list[str]:
    payload = json.loads(HOLDINGS_FILE.read_text(encoding="utf-8"))
    symbols: set[str] = set()
    fund_norm = (fund or "all").strip().lower()
    if fund_norm in ("sc", "smallcap", "small_cap"):
        books = ("smallcap",)
    elif fund_norm in ("mc", "midcap", "mid_cap"):
        books = ("midcap",)
    else:
        books = ("smallcap", "midcap")
    for book in books:
        for sym in (payload.get(book) or {}).keys():
            if str(sym).startswith("_"):
                continue
            symbols.add(str(sym).strip().upper())
    return sorted(symbols)


def _pick_pdf_for_symbol(pdf_dir: Path, symbol: str) -> Path | None:
    sym = str(symbol).strip().upper()
    if not pdf_dir.exists():
        return None
    hits = []
    for p in pdf_dir.rglob("*.pdf"):
        name = p.name.upper()
        if sym in name:
            hits.append(p)
    if not hits:
        return None
    return sorted(hits, key=lambda p: p.stat().st_mtime, reverse=True)[0]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fund", choices=["SC", "MC", "all"], default="all", help="Which fund book to process")
    ap.add_argument("--days", type=int, default=14, help="(Reserved) Lookback window for filings; not used yet.")
    ap.add_argument("--fetch", action="store_true", help="Run annual report fetch/index for fund holdings")
    ap.add_argument("--deep-dive", action="store_true", help="Run deep dive for each symbol")
    ap.add_argument(
        "--pdf-dir",
        default="",
        help="If set, use local PDFs from this folder instead of NSE fetch. "
        f"PDF filenames should include the symbol (default if unset: {DEFAULT_PDF_DIR}).",
    )
    ap.add_argument(
        "--use-inbox",
        action="store_true",
        help=f"Shortcut for --pdf-dir {DEFAULT_PDF_DIR} (local PDFs).",
    )
    ap.add_argument("--max-symbols", type=int, default=0, help="Limit how many symbols to process (0 = all)")
    ap.add_argument("--continue-on-error", action="store_true", help="Continue to next symbol if a step fails")
    ap.add_argument("--no-llm", action="store_true", help="Pass --no-llm to annual_report_deep_dive.py")
    ap.add_argument("--vision-fallback", action="store_true", help="Pass --vision-fallback to annual_report_deep_dive.py (expensive)")
    ap.add_argument("--max-relevant-pages", type=int, default=40, help="Deep dive cap per symbol (default 40)")
    ap.add_argument("--max-pages", type=int, default=220, help="Deep dive read cap per symbol (default 220)")
    args = ap.parse_args(argv)

    if not VENV_PYTHON.exists():
        raise SystemExit(f"Missing venv python: {VENV_PYTHON}")

    symbols = _symbols_from_fund_holdings(fund=args.fund)
    if args.max_symbols and int(args.max_symbols) > 0:
        symbols = symbols[: int(args.max_symbols)]

    pdf_dir = None
    if args.use_inbox:
        pdf_dir = DEFAULT_PDF_DIR
    elif args.pdf_dir:
        pdf_dir = Path(args.pdf_dir).expanduser()

    if not args.fetch and not args.deep_dive:
        print("Nothing to do. Use --fetch and/or --deep-dive.")
        print(f"Fund symbols: {len(symbols)}")
        return 2

    if args.fetch:
        if pdf_dir is not None:
            print(f"Skipping NSE fetch because --pdf-dir is set: {pdf_dir}")
        else:
            cmd = [str(VENV_PYTHON), "scripts/fetch_annual_reports.py", "--fund", str(args.fund), "--years", "1"]
            print("Running:", " ".join(cmd))
            r = subprocess.run(cmd, cwd=str(ROOT))
            if r.returncode != 0:
                return r.returncode

    if args.deep_dive:
        failures: list[tuple[str, int]] = []
        for i, sym in enumerate(symbols, 1):
            cmd = [
                str(VENV_PYTHON),
                "tools/annual_report_deep_dive.py",
                sym,
                "--max-pages",
                str(int(args.max_pages)),
                "--max-relevant-pages",
                str(int(args.max_relevant_pages)),
            ]
            if pdf_dir is not None:
                picked = _pick_pdf_for_symbol(pdf_dir, sym)
                if not picked:
                    failures.append((sym, 2))
                    print(f"[{i}/{len(symbols)}] Missing PDF for {sym} in {pdf_dir}")
                    if not args.continue_on_error:
                        print("Stopped (use --continue-on-error to keep going).")
                        return 2
                    continue
                cmd.extend(["--pdf-path", str(picked)])
            if args.no_llm:
                cmd.append("--no-llm")
            if args.vision_fallback:
                cmd.append("--vision-fallback")
            print(f"[{i}/{len(symbols)}] Running:", " ".join(cmd))
            r = subprocess.run(cmd, cwd=str(ROOT))
            if r.returncode != 0:
                failures.append((sym, int(r.returncode)))
                print(f"Failed: {sym} (exit={r.returncode})")
                if not args.continue_on_error:
                    print("Stopped (use --continue-on-error to keep going).")
                    return r.returncode

        if failures:
            print(f"\nFailures: {len(failures)} symbols")
            for sym, rc in failures[:25]:
                print(f"- {sym}: exit={rc}")
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
