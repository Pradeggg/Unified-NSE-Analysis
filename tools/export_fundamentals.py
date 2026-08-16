#!/usr/bin/env python3
"""
export_fundamentals.py — Export fundamental data from nse_market DB to CSV / JSON.

Tables exported:
  scores.fundamental_scores  — composite scored history (Aug 2025 → today)
  scores.fundamentals        — Piotroski / Beneish / Altman Z + ratio snapshots
  scores.quarterly_results   — quarterly P&L (2005 → latest)
  scores.annual_results      — annual P&L rollup
  scores.balance_sheet       — annual balance sheet
  scores.cash_flow           — annual cash flow

Usage:
  python tools/export_fundamentals.py                   # CSV to data/exports/fundamentals/
  python tools/export_fundamentals.py --format json     # JSON (one file per table)
  python tools/export_fundamentals.py --format both     # CSV + JSON
  python tools/export_fundamentals.py --out /tmp/fund   # custom output dir
  python tools/export_fundamentals.py --tables fundamental_scores fundamentals
  python tools/export_fundamentals.py --symbol BLSE RATNAVEER  # single-symbol slice
"""

import argparse
import csv
import json
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import psycopg2
import psycopg2.extras

ROOT    = Path(__file__).parent.parent
DEFAULT_OUT = ROOT / "data" / "exports" / "fundamentals"

DB_PARAMS = dict(dbname="nse_market", user="pgorai", host="localhost",
                 options="-c statement_timeout=60000")

# ── Table definitions ──────────────────────────────────────────────────────────

TABLES = {
    "fundamental_scores": dict(
        schema="scores",
        query="""
            SELECT score_date, symbol,
                   enhanced_fund_score, earnings_quality, sales_growth,
                   financial_strength, institutional_backing,
                   processed_date, source_file
            FROM scores.fundamental_scores
            ORDER BY symbol, score_date
        """,
        description="Composite fundamental score history (Aug 2025 → today)",
    ),
    "fundamentals": dict(
        schema="scores",
        query="""
            SELECT symbol,
                   piotroski_score, beneish_m_score, altman_z_score,
                   forensic_risk,
                   revenue_growth_3y, pat_growth_3y,
                   roe, roce, debt_to_equity, promoter_holding,
                   pnl_summary, quarterly_summary, balance_sheet_summary,
                   cash_flow_summary, ratios_summary,
                   updated_at::date AS updated_date
            FROM scores.fundamentals
            ORDER BY symbol
        """,
        description="Per-symbol forensic scores, ratios and text summaries",
    ),
    "quarterly_results": dict(
        schema="scores",
        query="""
            SELECT symbol, period_label, period_end, period_type,
                   revenue, expenses, operating_profit, opm_pct,
                   other_income, interest, depreciation,
                   pbt, tax_pct, pat, eps, source
            FROM scores.quarterly_results
            ORDER BY symbol, period_end
        """,
        description="Quarterly P&L (2005 → Jun 2026)",
    ),
    "annual_results": dict(
        schema="scores",
        query="""
            SELECT symbol, period_label, period_end, period_type,
                   revenue, expenses, operating_profit, opm_pct,
                   other_income, interest, depreciation,
                   pbt, tax_pct, pat, eps, dividend_payout_pct, source
            FROM scores.annual_results
            ORDER BY symbol, period_end
        """,
        description="Annual P&L rollup",
    ),
    "balance_sheet": dict(
        schema="scores",
        query="""
            SELECT symbol, period_label, period_end, period_type,
                   equity_capital, reserves, borrowings,
                   other_liabilities, total_liabilities,
                   fixed_assets, cwip, investments,
                   other_assets, total_assets, net_debt, source
            FROM scores.balance_sheet
            ORDER BY symbol, period_end
        """,
        description="Annual balance sheet (2002 → Jun 2026)",
    ),
    "cash_flow": dict(
        schema="scores",
        query="""
            SELECT symbol, period_label, period_end, period_type,
                   operating_cf, investing_cf, financing_cf,
                   net_cf, source
            FROM scores.cash_flow
            ORDER BY symbol, period_end
        """,
        description="Annual cash flow statement",
    ),
}

# ── helpers ───────────────────────────────────────────────────────────────────

def _serialisable(v):
    """Convert Decimal / date / datetime to JSON-safe Python types."""
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return v


def export_table(cur, name: str, defn: dict, out_dir: Path,
                 fmt: str, symbol_filter: list[str] | None) -> int:
    """Run the query, optionally filter by symbol, write CSV and/or JSON."""
    query = defn["query"]
    if symbol_filter:
        syms = "','".join(symbol_filter)
        # inject WHERE / AND clause before ORDER BY
        if "WHERE" in query.upper():
            query = query.replace("ORDER BY", f"AND symbol IN ('{syms}')\n            ORDER BY")
        else:
            query = query.replace("ORDER BY", f"WHERE symbol IN ('{syms}')\n            ORDER BY")

    cur.execute(query)
    cols = [d.name for d in cur.description]
    rows = cur.fetchall()
    n    = len(rows)

    if fmt in ("csv", "both"):
        csv_path = out_dir / f"{name}.csv"
        with open(csv_path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(cols)
            for row in rows:
                w.writerow([_serialisable(v) for v in row])
        print(f"  ✓  {name}.csv          {n:>6,} rows   ({csv_path})")

    if fmt in ("json", "both"):
        json_path = out_dir / f"{name}.json"
        data = {
            "table":       name,
            "description": defn["description"],
            "exported_at": date.today().isoformat(),
            "columns":     cols,
            "rows":        [[_serialisable(v) for v in row] for row in rows],
        }
        with open(json_path, "w") as f:
            json.dump(data, f, separators=(",", ":"))
        size_kb = json_path.stat().st_size // 1024
        print(f"  ✓  {name}.json         {n:>6,} rows   {size_kb} KB")

    return n


def write_manifest(out_dir: Path, tables: list[str], fmt: str,
                   symbol_filter: list[str] | None, totals: dict):
    manifest = {
        "exported_at":    date.today().isoformat(),
        "format":         fmt,
        "symbol_filter":  symbol_filter or "all",
        "source_db":      "nse_market (local PostgreSQL)",
        "tables":         {
            t: {"rows": totals[t], "description": TABLES[t]["description"]}
            for t in tables
        },
    }
    path = out_dir / "manifest.json"
    with open(path, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"\n  manifest → {path}")


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Export fundamental DB tables to CSV/JSON")
    ap.add_argument("--format", choices=["csv", "json", "both"], default="csv",
                    help="Output format (default: csv)")
    ap.add_argument("--out", default=str(DEFAULT_OUT), metavar="DIR",
                    help=f"Output directory (default: {DEFAULT_OUT})")
    ap.add_argument("--tables", nargs="+", choices=list(TABLES), metavar="TABLE",
                    help="Subset of tables to export (default: all)")
    ap.add_argument("--symbol", nargs="+", metavar="SYM",
                    help="Filter to specific symbols only (e.g. --symbol BLSE RATNAVEER)")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    tables = args.tables or list(TABLES)
    fmt    = args.format
    syms   = [s.upper() for s in args.symbol] if args.symbol else None

    print(f"\nExporting {len(tables)} table(s) → {out_dir}")
    if syms:
        print(f"  Symbol filter: {', '.join(syms)}")
    print()

    try:
        conn = psycopg2.connect(**DB_PARAMS)
        cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    except Exception as e:
        sys.exit(f"DB connection failed: {e}")

    totals = {}
    for name in tables:
        defn = TABLES[name]
        # RealDictCursor returns dicts; switch to plain cursor for fast row access
        plain_cur = conn.cursor()
        try:
            n = export_table(plain_cur, name, defn, out_dir, fmt, syms)
            totals[name] = n
        except Exception as e:
            print(f"  ✗  {name}: {e}", file=sys.stderr)
            totals[name] = 0
        plain_cur.close()

    conn.close()
    write_manifest(out_dir, tables, fmt, syms, totals)

    total_rows = sum(totals.values())
    print(f"\n  Done — {total_rows:,} rows across {len(tables)} tables\n")


if __name__ == "__main__":
    main()
