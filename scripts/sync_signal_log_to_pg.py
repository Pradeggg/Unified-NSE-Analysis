"""sync_signal_log_to_pg.py
Sync data/signal_log.csv → signals.signal_log (PostgreSQL).

Upsert key: (date_issued, symbol).
Run after sector_rotation_report.py produces a fresh CSV.

Usage:
    python scripts/sync_signal_log_to_pg.py                   # full backfill
    python scripts/sync_signal_log_to_pg.py --days-back 7     # last 7 days only
    python scripts/sync_signal_log_to_pg.py --resolve          # also resolve open signals
"""
from __future__ import annotations

import argparse
import math
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import psycopg2
import psycopg2.extras

ROOT = Path(__file__).resolve().parent.parent
SIGNAL_LOG_CSV = ROOT / "data" / "signal_log.csv"

# CSV col → PG col (identity mapping where names match; only exceptions listed)
_COL_REMAP: dict[str, str] = {}

# PG columns that can be null / have defaults — not required from CSV
_PG_OPTIONAL = {"council_run_id", "disclaimer_version", "id"}

# Numeric columns that may contain NaN → convert to None
_NUMERIC_COLS = {
    "investment_score", "technical_score", "rsi",
    "price_at_issue", "entry_low", "entry_high", "stop_loss", "target_1", "target_2",
    "fno_pcr", "fno_oi_change_5d", "insider_score",
    "price_at_resolution", "return_pct",
}

# Boolean columns stored as string in CSV
_BOOL_COLS = {"hit_target", "hit_stop"}

# Date columns stored as string
_DATE_COLS = {"date_issued", "date_resolved"}


def _clean(row: dict) -> dict:
    out: dict = {}
    for k, v in row.items():
        pg_col = _COL_REMAP.get(k, k)
        if k in _NUMERIC_COLS:
            try:
                fv = float(v)
                out[pg_col] = None if math.isnan(fv) else fv
            except (TypeError, ValueError):
                out[pg_col] = None
        elif k in _BOOL_COLS:
            if pd.isna(v) or v == "":
                out[pg_col] = None
            elif str(v).strip().upper() in ("TRUE", "1", "YES"):
                out[pg_col] = True
            elif str(v).strip().upper() in ("FALSE", "0", "NO"):
                out[pg_col] = False
            else:
                out[pg_col] = None
        elif k in _DATE_COLS:
            if pd.isna(v) or str(v).strip() == "":
                out[pg_col] = None
            else:
                try:
                    out[pg_col] = datetime.strptime(str(v).strip(), "%Y-%m-%d").date()
                except ValueError:
                    out[pg_col] = None
        else:
            out[pg_col] = None if (pd.isna(v) if not isinstance(v, str) else False) else str(v) if not pd.isna(v) else None
    return out


def _resolve_open_signals(conn, cur) -> int:
    """
    For each open signal (date_resolved IS NULL) in the PG table, look up the
    most recent close price from market.equity_eod and compute return_pct.
    Also sets hit_target / hit_stop based on target_1 / stop_loss.
    Returns number of rows updated.
    """
    cur.execute("""
        SELECT sl.id, sl.symbol, sl.price_at_issue, sl.stop_loss, sl.target_1,
               e.close, e.trade_date
        FROM signals.signal_log sl
        JOIN LATERAL (
            SELECT close, trade_date
            FROM market.equity_eod
            WHERE symbol = sl.symbol
            ORDER BY trade_date DESC
            LIMIT 1
        ) e ON true
        WHERE sl.date_resolved IS NULL
          AND sl.price_at_issue IS NOT NULL
          AND sl.price_at_issue > 0
    """)
    rows = cur.fetchall()
    if not rows:
        return 0

    updated = 0
    for row_id, symbol, entry, sl_price, t1, current, tdate in rows:
        if current is None or entry is None or entry == 0:
            continue
        ret = (current - entry) / entry * 100
        hit_t = bool(t1 and current >= t1)
        hit_s = bool(sl_price and current <= sl_price)
        resolved = tdate if (hit_t or hit_s) else None
        cur.execute("""
            UPDATE signals.signal_log
            SET price_at_resolution = %s,
                return_pct          = %s,
                hit_target          = %s,
                hit_stop            = %s,
                date_resolved       = %s
            WHERE id = %s
        """, (float(current), round(ret, 4), hit_t, hit_s, resolved, row_id))
        updated += 1

    conn.commit()
    return updated


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync signal_log.csv → signals.signal_log (PG)")
    parser.add_argument("--days-back", type=int, default=None,
                        help="Only sync rows issued in the last N days (default: all)")
    parser.add_argument("--resolve", action="store_true",
                        help="Also resolve open signals against latest market prices")
    parser.add_argument("--csv", default=str(SIGNAL_LOG_CSV),
                        help=f"Path to signal_log CSV (default: {SIGNAL_LOG_CSV})")
    args = parser.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.exists():
        print(f"  ❌ CSV not found: {csv_path}", file=sys.stderr)
        sys.exit(1)

    df = pd.read_csv(csv_path)
    print(f"  Loaded {len(df)} rows from {csv_path.name}")

    if args.days_back:
        cutoff = (date.today() - timedelta(days=args.days_back)).isoformat()
        df = df[df["date_issued"] >= cutoff]
        print(f"  Filtered to last {args.days_back} days: {len(df)} rows")

    if df.empty:
        print("  Nothing to sync.")
        return

    conn = psycopg2.connect(host="/tmp", dbname="nse_market", user="nse_admin")
    cur = conn.cursor()

    # Build list of PG columns (exclude auto/optional)
    pg_cols = [c for c in df.columns if c not in _PG_OPTIONAL]

    rows_to_upsert = [_clean(r) for _, r in df[pg_cols].iterrows()]

    # Upsert in batches of 500
    BATCH = 500
    total_upserted = 0
    for i in range(0, len(rows_to_upsert), BATCH):
        batch = rows_to_upsert[i : i + BATCH]
        cols = list(batch[0].keys())
        placeholders = ", ".join(["%s"] * len(cols))
        col_names = ", ".join(cols)
        updates = ", ".join(
            f"{c} = EXCLUDED.{c}"
            for c in cols
            if c not in ("date_issued", "symbol")
        )
        sql = f"""
            INSERT INTO signals.signal_log ({col_names})
            VALUES ({placeholders})
            ON CONFLICT (date_issued, symbol) DO UPDATE SET {updates}
        """
        values = [tuple(r[c] for c in cols) for r in batch]
        psycopg2.extras.execute_batch(cur, sql, values, page_size=BATCH)
        total_upserted += len(batch)

    conn.commit()
    print(f"  ✅ Upserted {total_upserted} rows → signals.signal_log")

    if args.resolve:
        resolved = _resolve_open_signals(conn, cur)
        print(f"  ✅ Resolved {resolved} open signals with current prices")

    # Verify
    cur.execute("SELECT COUNT(*), MAX(date_issued) FROM signals.signal_log")
    total, latest = cur.fetchone()
    print(f"  Table now: {total} rows, latest date = {latest}")

    conn.close()


if __name__ == "__main__":
    main()
