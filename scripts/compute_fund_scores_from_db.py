#!/usr/bin/env python3
"""
compute_fund_scores_from_db.py
==============================
Derive and persist scores.fundamental_scores for the fund universe by reading
raw financial data already stored in the structured PG tables
(scores.annual_results, quarterly_results, balance_sheet, cash_flow,
scores.fundamentals) rather than re-scraping screener.in.

This is typically run after backfill_screener_fundamentals.py has populated
the raw tables, when you want to recompute the scored layer without hitting
screener.in again.

Usage:
    python -m scripts.compute_fund_scores_from_db
    python -m scripts.compute_fund_scores_from_db --symbols BLSE,RATNAVEER
    python -m scripts.compute_fund_scores_from_db --universe sc   # SC only
    python -m scripts.compute_fund_scores_from_db --universe mc   # MC only
    python -m scripts.compute_fund_scores_from_db --universe all  # SC + MC (default)
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any

BASE = Path(__file__).resolve().parent.parent
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

import psycopg2
import psycopg2.extras

from terminal.fund_score_derivation import derive_fund_scores

INDEX_CSV = BASE / "data" / "index_stock_mapping.csv"
DSN = "dbname=nse_market user=pgorai host=localhost"


# ── Universe loaders ─────────────────────────────────────────────────────────

def load_sc_symbols(conn) -> list[str]:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT DISTINCT symbol FROM scores.stage_snapshots
            WHERE market_cap_cat = 'SMALL_CAP'
              AND snapshot_date = (SELECT MAX(snapshot_date) FROM scores.stage_snapshots)
            ORDER BY symbol
        """)
        return [r[0] for r in cur.fetchall()]


def load_mc_symbols() -> list[str]:
    if not INDEX_CSV.exists():
        return []
    syms = []
    with INDEX_CSV.open() as f:
        for row in csv.DictReader(f):
            if "MIDCAP 150" in row.get("INDEX_NAME", ""):
                syms.append(row["STOCK_SYMBOL"].strip())
    return syms


# ── Payload reconstruction from structured DB tables ─────────────────────────

def _series_from_rows(rows: list[dict], col: str) -> list:
    """Return values ordered by period_end ascending, skipping nulls."""
    ordered = sorted(rows, key=lambda r: r.get("period_end") or date.min)
    return [r[col] for r in ordered if r.get(col) is not None]


def _parse_ratio(text: str | None, *keys: str) -> float | None:
    """Parse a value from a ratios_summary text like 'ROCE: 22.2; ROE: 17.8'."""
    if not text:
        return None
    for key in keys:
        m = re.search(rf"{re.escape(key)}\s*:\s*([\d.]+)", text, re.IGNORECASE)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                pass
    return None


def _parse_holding(text: str | None, key: str) -> float | None:
    """Parse a % from investor_summary text like 'Promoters 52.1% | FII 12.3%'."""
    if not text:
        return None
    m = re.search(rf"{re.escape(key)}\s+([\d.]+)%?", text, re.IGNORECASE)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass
    return None


def build_payload_from_db(sym: str, conn) -> dict[str, Any]:
    """Reconstruct a derive_fund_scores-compatible payload from structured DB tables."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        # Annual results (last 5 periods)
        cur.execute("""
            SELECT period_label, period_end, revenue, opm_pct, pat, eps
            FROM scores.annual_results
            WHERE symbol = %s AND period_type = 'annual'
            ORDER BY period_end ASC NULLS LAST
            LIMIT 6
        """, (sym,))
        ann = cur.fetchall()

        # Quarterly results (last 8)
        cur.execute("""
            SELECT period_label, period_end, revenue, opm_pct, pat, eps
            FROM scores.quarterly_results
            WHERE symbol = %s AND period_type = 'quarterly'
            ORDER BY period_end ASC NULLS LAST
            LIMIT 8
        """, (sym,))
        qtrs = cur.fetchall()

        # Balance sheet (last 3)
        cur.execute("""
            SELECT period_label, period_end, borrowings, equity_capital, reserves
            FROM scores.balance_sheet
            WHERE symbol = %s
            ORDER BY period_end ASC NULLS LAST
            LIMIT 4
        """, (sym,))
        bs = cur.fetchall()

        # Cash flow (last 4)
        cur.execute("""
            SELECT period_label, period_end, operating_cf
            FROM scores.cash_flow
            WHERE symbol = %s
            ORDER BY period_end ASC NULLS LAST
            LIMIT 4
        """, (sym,))
        cf = cur.fetchall()

        # Ratios and shareholding text from fundamentals table
        cur.execute("""
            SELECT ratios_summary, investor_summary
            FROM scores.fundamentals
            WHERE symbol = %s
        """, (sym,))
        fund_row = cur.fetchone()
        ratios_text   = fund_row["ratios_summary"]   if fund_row else None
        investor_text = fund_row["investor_summary"]  if fund_row else None

    # Build annual_pl section (derive_fund_scores keys)
    annual_pl = {
        "Sales+":       _series_from_rows(ann, "revenue"),
        "Net Profit+":  _series_from_rows(ann, "pat"),
        "EPS in Rs":    _series_from_rows(ann, "eps"),
        "OPM %":        _series_from_rows(ann, "opm_pct"),
    }

    # Build quarterly section
    quarterly = {
        "Sales+":       _series_from_rows(qtrs, "revenue"),
        "Net Profit+":  _series_from_rows(qtrs, "pat"),
        "OPM %":        _series_from_rows(qtrs, "opm_pct"),
    }

    # Build balance_sheet section
    balance_sheet = {
        "Borrowings+":   _series_from_rows(bs, "borrowings"),
        "Equity Capital": _series_from_rows(bs, "equity_capital"),
        "Reserves":       _series_from_rows(bs, "reserves"),
    }

    # Build cash_flow section — CFO/OP not directly stored; use raw operating_cf
    # as a proxy (derive_fund_scores falls back to 55 default if key missing)
    cash_flow = {
        "Cash from Operations": _series_from_rows(cf, "operating_cf"),
    }

    # Parse ROCE / ROE from ratios text
    ratios = {}
    roce = _parse_ratio(ratios_text, "ROCE")
    roe  = _parse_ratio(ratios_text, "ROE", "Return on Equity")
    if roce is not None:
        ratios["ROCE"] = str(roce)
    if roe is not None:
        ratios["ROE"] = str(roe)

    # Parse shareholding from investor text
    shareholding = {}
    prom = _parse_holding(investor_text, "Promoters")
    fii  = _parse_holding(investor_text, "FII")
    dii  = _parse_holding(investor_text, "DII")
    if prom is not None:
        shareholding["Promoters"] = str(prom)
    if fii is not None:
        shareholding["FIIs"] = str(fii)
    if dii is not None:
        shareholding["DIIs"] = str(dii)

    return {
        "annual_pl":    annual_pl,
        "quarterly":    quarterly,
        "balance_sheet": balance_sheet,
        "cash_flow":    cash_flow,
        "ratios":       ratios,
        "shareholding": shareholding,
    }


# ── Score upsert ─────────────────────────────────────────────────────────────

def upsert_scores(cur, sym: str, scores: dict) -> None:
    cur.execute(
        """
        INSERT INTO scores.fundamental_scores
          (score_date, symbol, enhanced_fund_score,
           earnings_quality, sales_growth, financial_strength,
           institutional_backing, processed_date, source_file)
        VALUES
          (CURRENT_DATE, %s, %s, %s, %s, %s, %s, CURRENT_DATE, 'compute_fund_scores_from_db')
        ON CONFLICT (score_date, symbol) DO UPDATE SET
          enhanced_fund_score   = EXCLUDED.enhanced_fund_score,
          earnings_quality      = EXCLUDED.earnings_quality,
          sales_growth          = EXCLUDED.sales_growth,
          financial_strength    = EXCLUDED.financial_strength,
          institutional_backing = EXCLUDED.institutional_backing,
          processed_date        = EXCLUDED.processed_date,
          source_file           = EXCLUDED.source_file,
          loaded_at             = now()
        """,
        (
            sym,
            scores.get("enhanced_fund_score"),
            scores.get("earnings_quality"),
            scores.get("sales_growth"),
            scores.get("financial_strength"),
            scores.get("institutional_backing"),
        ),
    )


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols", help="Comma-separated symbol list (overrides --universe)")
    parser.add_argument("--universe", choices=["sc", "mc", "all"], default="all",
                        help="Which universe to score (default: all)")
    parser.add_argument("--batch-commit", type=int, default=20, metavar="N",
                        help="Commit every N symbols (default 20)")
    args = parser.parse_args()

    conn = psycopg2.connect(DSN, connect_timeout=15, options="-c statement_timeout=30000")
    conn.autocommit = False

    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    else:
        sc_syms = load_sc_symbols(conn) if args.universe in ("sc", "all") else []
        mc_syms = load_mc_symbols()     if args.universe in ("mc", "all") else []
        symbols = sorted(set(sc_syms) | set(mc_syms))

    total = len(symbols)
    print(f"[compute-fund-scores] {total} symbols  universe={args.universe}  date={date.today()}")

    ok = err = skip = 0
    with conn.cursor() as cur:
        for i, sym in enumerate(symbols, 1):
            try:
                payload = build_payload_from_db(sym, conn)

                # Skip if no meaningful financial data available
                has_data = any([
                    payload["annual_pl"]["Sales+"],
                    payload["annual_pl"]["Net Profit+"],
                    payload["quarterly"]["Sales+"],
                ])
                if not has_data:
                    skip += 1
                    if i % 50 == 0 or i <= 5:
                        print(f"  [{i}/{total}] {sym:15s} SKIP (no structured data)")
                    continue

                scores = derive_fund_scores(payload)
                upsert_scores(cur, sym, scores)
                ok += 1

                if i % args.batch_commit == 0:
                    conn.commit()

                # Progress every 25 or on first 5
                if i % 25 == 0 or i <= 5:
                    print(f"  [{i}/{total}] {sym:15s}  "
                          f"fund={scores['enhanced_fund_score']:5.1f}  "
                          f"EQ={scores['earnings_quality']:5.1f}  "
                          f"SG={scores['sales_growth']:5.1f}  "
                          f"FS={scores['financial_strength']:5.1f}  "
                          f"IB={scores['institutional_backing']:5.1f}")

            except Exception as e:
                conn.rollback()
                err += 1
                print(f"  [{i}/{total}] {sym:15s} ERROR {e}")

    conn.commit()
    conn.close()
    print(f"\n[compute-fund-scores] done  ok={ok}  skipped={skip}  errors={err}")
    return 0 if err == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
