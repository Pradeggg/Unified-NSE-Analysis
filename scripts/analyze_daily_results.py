#!/usr/bin/env python3
"""
analyze_daily_results.py
========================
For every NSE company that filed quarterly results in the last N days
(``get_latest_results_feed``), this script:

  1. Ensures the structured financials cache is fresh (defers to
     ``scripts.refresh_results_feed`` to do the actual scraping).
  2. Calls ``terminal.results_tools.get_latest_results`` to discover the
     filing PDF, ingest it, and reconcile parsed facts.
  3. Builds a deterministic evidence pack from PG +
     ``scrape_screener_in`` (ratios, shareholding, announcements).
  4. Calls the Research-Council LLM (JSON mode, strict schema) to produce
     a structured analyst note.
  5. Persists into ``scores.results_analysis`` and renders a per-stock
     HTML report. At the end, writes an index.html.

Usage:
  python -m scripts.analyze_daily_results
  python -m scripts.analyze_daily_results --days-back 1 --limit 100
  python -m scripts.analyze_daily_results --skip-llm   # evidence-only dry-run
  python -m scripts.analyze_daily_results --out-dir reports/results_analysis
"""

from __future__ import annotations

import argparse
import datetime as _dt
import os
import posixpath
import sys
import time
import traceback
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

import psycopg2  # noqa: E402

from terminal.financials_cache import DEFAULT_DSN, log_refresh_run  # noqa: E402
from terminal.results_analysis import (  # noqa: E402
    build_evidence_pack,
    analyze_with_llm,
    analysis_has_placeholders,
    deterministic_financial_analysis,
    has_structured_financials,
    insufficient_data_analysis,
    persist_analysis,
    render_stock_html,
    render_index_html,
)
from terminal.tools import get_latest_results_feed  # noqa: E402


JOB_NAME = "analyze_daily_results"


def _safe_get_latest_results(symbol: str) -> dict:
    """Best-effort PDF discovery + parse. Never raises."""
    try:
        from terminal.results_tools import get_latest_results
        return get_latest_results(symbol, period="latest", ingest=True)
    except Exception as exc:  # noqa: BLE001
        return {"status": f"error:{exc}", "candidates": [], "facts": {}, "source_trail": {}}


def _safe_screener(symbol: str) -> dict:
    """Live screener scrape with TTL-cache fallback (mirrors results_tools)."""
    try:
        from terminal.results_tools import _resolve_screener_data  # type: ignore
        data, _status = _resolve_screener_data(symbol)
        return data or {}
    except Exception:
        return {}


def _date_dirs(out_root: Path, run_date: _dt.date) -> Path:
    """``reports/results_analysis/<YYYY>/<YYYYMMDD>/``."""
    p = out_root / str(run_date.year) / run_date.strftime("%Y%m%d")
    p.mkdir(parents=True, exist_ok=True)
    return p


def _latest_index_items(index_items: list[dict], *, out_dir: Path, latest_dir: Path) -> list[dict]:
    """Rewrite per-stock links so the stable reports/latest copy can resolve them."""
    rel_prefix = Path(os.path.relpath(out_dir, latest_dir)).as_posix()
    latest_items: list[dict] = []
    for item in index_items:
        copy = dict(item)
        report_path = str(copy.get("report_path") or "").strip()
        if report_path and report_path != "#" and not report_path.startswith(("http://", "https://", "/", "file:")):
            copy["report_path"] = posixpath.join(rel_prefix, report_path)
        latest_items.append(copy)
    return latest_items


def run(args: argparse.Namespace) -> int:
    feed = get_latest_results_feed(days_back=args.days_back, limit=args.limit)
    rows = feed.get("results") or []
    if not rows:
        print(f"[results-analysis] no filings in window (days_back={args.days_back})")
        log_refresh_run(JOB_NAME, symbols_attempted=0, symbols_loaded=0,
                         rows_upserted=0, errors=0,
                         notes=f"empty feed days_back={args.days_back}")
        return 0

    # Dedupe by symbol (NSE feed can repeat for the same company across periods)
    seen: set[str] = set()
    filers: list[dict] = []
    for r in rows:
        sym = str((r or {}).get("symbol") or "").strip().upper()
        if not sym or sym in seen:
            continue
        seen.add(sym)
        filers.append({**r, "symbol": sym})

    print(f"[results-analysis] candidates={len(filers)}  days_back={args.days_back}  "
          f"skip_llm={args.skip_llm}")

    out_dir = _date_dirs(Path(args.out_dir), _dt.date.today())
    conn = psycopg2.connect(args.dsn)
    conn.autocommit = True  # reads + single-statement upserts are safe under autocommit

    attempted = persisted = errors = 0
    error_log: list[tuple[str, str]] = []
    index_items: list[dict] = []

    try:
        for i, row in enumerate(filers, 1):
            sym = row["symbol"]
            attempted += 1
            t0 = time.time()
            try:
                screener_data = _safe_screener(sym)
                results_pack = _safe_get_latest_results(sym) if not args.skip_filing else {}
                pack = build_evidence_pack(
                    conn,
                    symbol=sym,
                    feed_row=row,
                    results_pack=results_pack,
                    screener_data=screener_data,
                )

                if not has_structured_financials(pack):
                    analysis = insufficient_data_analysis(pack)
                    model_used = "deterministic:insufficient_data"
                elif args.skip_llm:
                    analysis = _stub_analysis(pack)
                    model_used = "stub:no_llm"
                else:
                    analysis = analyze_with_llm(pack, model=args.model)
                    model_used = args.model or os.environ.get("OPENAI_MODEL") or "default"
                    if analysis_has_placeholders(analysis):
                        analysis = deterministic_financial_analysis(pack, reason="llm_placeholder_output")
                        model_used = "deterministic:llm_placeholder_output"

                # Render HTML first so we can persist its path.
                html_path = out_dir / f"{sym}.html"
                html = render_stock_html(pack, {**analysis, "_llm_model": model_used})
                html_path.write_text(html, encoding="utf-8")

                rel_path = str(html_path.resolve().relative_to(BASE))
                period_end = persist_analysis(
                    conn,
                    pack=pack,
                    analysis=analysis,
                    report_path=rel_path,
                    llm_model=model_used,
                )

                if period_end:
                    persisted += 1
                index_items.append({
                    "symbol": sym,
                    "company_name": pack.get("company_name"),
                    "period_label": pack.get("period_label"),
                    "verdict": analysis.get("verdict"),
                    "score": analysis.get("score"),
                    "yoy_revenue_pct": (pack.get("growth") or {}).get("yoy_revenue_pct"),
                    "yoy_pat_pct": (pack.get("growth") or {}).get("yoy_pat_pct"),
                    "report_path": html_path.name,
                })
                print(f"[{i}/{len(filers)}] {sym:<14} ok  "
                      f"verdict={analysis.get('verdict')}  "
                      f"score={analysis.get('score')}  "
                      f"{time.time()-t0:.1f}s")
            except Exception as exc:  # noqa: BLE001
                errors += 1
                error_log.append((sym, str(exc)[:160]))
                print(f"[{i}/{len(filers)}] {sym:<14} ERROR  {exc}")
                if args.verbose:
                    traceback.print_exc()
    finally:
        conn.close()

    # Index page
    if index_items:
        idx_path = out_dir / "index.html"
        idx_path.write_text(
            render_index_html(_dt.date.today().isoformat(), index_items),
            encoding="utf-8",
        )
        # Also drop a stable copy under reports/latest/ for the daily dashboard.
        latest_dir = BASE / "reports" / "latest"
        latest_dir.mkdir(parents=True, exist_ok=True)
        (latest_dir / "results_analysis.html").write_text(
            render_index_html(
                _dt.date.today().isoformat(),
                _latest_index_items(index_items, out_dir=out_dir, latest_dir=latest_dir),
            ),
            encoding="utf-8",
        )
        print(f"[results-analysis] index → {idx_path}")
        print(f"[results-analysis] latest → {latest_dir / 'results_analysis.html'}")

    notes = f"days_back={args.days_back};errors={len(error_log)}"
    if error_log:
        notes += ";first_err=" + ",".join(s for s, _ in error_log[:3])
    log_refresh_run(
        JOB_NAME,
        symbols_attempted=attempted,
        symbols_loaded=persisted,
        rows_upserted=persisted,
        errors=errors,
        notes=notes,
    )
    print(f"\n[results-analysis] done  attempted={attempted}  persisted={persisted}  errors={errors}")
    return 0


def _stub_analysis(pack: dict) -> dict:
    """Deterministic placeholder used when --skip-llm is set."""
    growth = pack.get("growth") or {}
    return {
        "business_summary": (
            f"{pack.get('company_name') or pack.get('symbol')} filed quarterly results "
            f"for {pack.get('period_label') or 'the latest period'}."
        ),
        "pl_commentary": f"YoY revenue: {growth.get('yoy_revenue_pct')}%; YoY PAT: {growth.get('yoy_pat_pct')}%.",
        "bs_commentary": "(skipped: --skip-llm)",
        "cf_commentary": "(skipped: --skip-llm)",
        "key_strengths": [],
        "key_risks": [],
        "verdict": "unknown",
        "score": None,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--days-back", type=int, default=1,
                    help="Calendar days of results-feed window (default 1)")
    p.add_argument("--limit", type=int, default=200,
                    help="Max symbols to consider from the feed")
    p.add_argument("--skip-llm", action="store_true",
                    help="Skip the LLM call (use deterministic stub) — useful for dry runs")
    p.add_argument("--skip-filing", action="store_true",
                    help="Skip PDF discovery/ingest; rely on PG + screener payload only")
    p.add_argument("--model", default=None,
                    help="Override LLM model (else RESEARCH_COUNCIL_LLM_MODEL / OPENAI_MODEL)")
    p.add_argument("--out-dir", default="reports/results_analysis",
                    help="Output root for per-stock HTML reports")
    p.add_argument("--verbose", "-v", action="store_true")
    p.add_argument("--dsn", default=DEFAULT_DSN)
    args = p.parse_args()
    sys.exit(run(args))


if __name__ == "__main__":
    main()
