#!/usr/bin/env python3
"""
Generate LLM narratives into SQLite (llm_narratives) as part of the analysis pipeline.

Runs after fixed_nse_universe_analysis.py so stocks_analysis / index_analysis exist.
The HTML dashboard generator then embeds these rows for shareable offline HTML.

Environment:
  NARRATIVE_SKIP=1          — exit immediately without calling Ollama
  NARRATIVE_MARKET_ONLY=1   — only market narrative (skip per-stock)
  NARRATIVE_TOP_STOCKS=20   — top technical-score stocks to narrate (default 20; increase for more embeds)
  NARRATIVE_FAIL_PIPELINE=1 — sys.exit(1) if market narrative fails (default: warn and continue)
  OLLAMA_BASE, OLLAMA_MODEL — same as narrative_llm_server
"""

from __future__ import annotations

import argparse
import os
import sys

from narrative_db import DEFAULT_DB_PATH, connect_db, get_latest_analysis_date, upsert_narrative
from narrative_llm_core import synthesize_market_narrative, synthesize_stock_narrative


def _top_symbols_by_technical(conn, analysis_date: str, limit: int) -> list[str]:
    cur = conn.execute(
        """
        SELECT UPPER(TRIM(symbol)) AS s
        FROM stocks_analysis
        WHERE analysis_date = ? AND symbol IS NOT NULL AND TRIM(symbol) != ''
        ORDER BY COALESCE(technical_score, -1) DESC
        LIMIT ?
        """,
        (analysis_date, limit),
    )
    return [str(r[0]) for r in cur.fetchall() if r[0]]


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Ollama narratives into nse_analysis.db")
    parser.add_argument(
        "--top-stocks",
        type=int,
        default=int(os.environ.get("NARRATIVE_TOP_STOCKS", "20")),
        help="Number of top technical-score stocks to narrate (0 = none)",
    )
    parser.add_argument("--market-only", action="store_true", help="Skip stock narratives")
    parser.add_argument("--skip", action="store_true", help="Do nothing (same as NARRATIVE_SKIP=1)")
    args = parser.parse_args()

    if args.skip or os.environ.get("NARRATIVE_SKIP", "").strip() in ("1", "true", "yes"):
        print("narrative_pipeline_runner: skipped (NARRATIVE_SKIP or --skip).")
        return 0

    from pathlib import Path

    db_path = os.environ.get("NSE_DB_PATH", str(DEFAULT_DB_PATH))
    ollama_base = os.environ.get("OLLAMA_BASE", "http://127.0.0.1:11434").rstrip("/")
    ollama_model = os.environ.get("OLLAMA_MODEL", "granite4")
    fail_hard = os.environ.get("NARRATIVE_FAIL_PIPELINE", "").strip() in ("1", "true", "yes")
    market_only = args.market_only or os.environ.get("NARRATIVE_MARKET_ONLY", "").strip() in ("1", "true", "yes")

    conn = connect_db(Path(db_path))
    try:
        ad = get_latest_analysis_date(conn)
        if not ad:
            print("narrative_pipeline_runner: no analysis_date in stocks_analysis; skipping.")
            return 0

        print(f"narrative_pipeline_runner: analysis_date={ad} model={ollama_model} base={ollama_base}")

        # --- Market ---
        try:
            text, ctx = synthesize_market_narrative(conn, ad, ollama_base=ollama_base, ollama_model=ollama_model)
            upsert_narrative(conn, "market", ad, "", ollama_model, text, context_obj=ctx)
            print(f"  ✓ Market narrative saved ({len(text)} chars)")
        except RuntimeError as e:
            print(f"  ✗ Market narrative failed: {e}")
            if fail_hard:
                return 1

        if market_only:
            print("  (stock narratives skipped: --market-only or NARRATIVE_MARKET_ONLY)")
            return 0

        n = max(0, args.top_stocks)
        if n == 0:
            print("  (stock narratives skipped: --top-stocks 0)")
            return 0

        symbols = _top_symbols_by_technical(conn, ad, n)
        print(f"  Generating stock narratives for top {len(symbols)} symbols…")
        ok = 0
        for i, sym in enumerate(symbols, 1):
            try:
                text, store_ctx = synthesize_stock_narrative(
                    conn, ad, sym, ollama_base=ollama_base, ollama_model=ollama_model
                )
                upsert_narrative(conn, "stock", ad, sym, ollama_model, text, context_obj=store_ctx)
                ok += 1
                if i % 10 == 0 or i == len(symbols):
                    print(f"    … {i}/{len(symbols)} ({ok} ok)")
            except RuntimeError as e:
                print(f"    ! {sym}: {e}")
        print(f"  ✓ Stock narratives finished: {ok}/{len(symbols)} saved")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
