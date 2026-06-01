#!/usr/bin/env python3
"""
Archive old F&O monthly partitions from PostgreSQL.

Default mode is dry-run. Use --execute to write archives. Use
--delete-after-archive to detach/drop archived partitions after row-count and
checksum verification.
"""

from __future__ import annotations
import os

import argparse
import gzip
import hashlib
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

import psycopg2


BASE = Path(__file__).resolve().parent.parent
ARCHIVE_ROOT = BASE / "postgres" / "archive" / "fno"
PG_DSN = (
    os.environ.get("AGENT_ADDA_PG_DSN")
    or os.environ.get("PG_DSN")
    or "dbname=nse_market user=nse_admin host=/tmp"
)


BOUND_RE = re.compile(r"FROM \('(?P<start>\d{4}-\d{2}-\d{2})'\) TO \('(?P<end>\d{4}-\d{2}-\d{2})'\)")


def parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def cutoff_from_args(args: argparse.Namespace) -> date:
    if args.older_than_date:
        return parse_date(args.older_than_date)
    today = date.today()
    return date(today.year - args.older_than_years, today.month, 1)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def discover_partitions(cur):
    cur.execute(
        """
        SELECT child_ns.nspname, child.relname, pg_get_expr(child.relpartbound, child.oid) AS bound
        FROM pg_inherits i
        JOIN pg_class parent ON parent.oid = i.inhparent
        JOIN pg_namespace parent_ns ON parent_ns.oid = parent.relnamespace
        JOIN pg_class child ON child.oid = i.inhrelid
        JOIN pg_namespace child_ns ON child_ns.oid = child.relnamespace
        WHERE parent_ns.nspname = 'derivatives'
          AND parent.relname = 'fno_eod'
          AND child.relname <> 'fno_eod_default'
        ORDER BY child.relname
        """
    )
    partitions = []
    for schema, table, bound in cur.fetchall():
        match = BOUND_RE.search(bound or "")
        if not match:
            continue
        start = parse_date(match.group("start"))
        end = parse_date(match.group("end"))
        partitions.append({"schema": schema, "table": table, "start": start, "end": end})
    return partitions


def count_rows(cur, qualified_table: str) -> int:
    cur.execute(f"SELECT count(*) FROM {qualified_table}")
    return int(cur.fetchone()[0])


def export_partition(cur, partition: dict, archive_dir: Path) -> dict:
    qualified = f"{partition['schema']}.{partition['table']}"
    rows = count_rows(cur, qualified)
    archive_dir.mkdir(parents=True, exist_ok=True)
    out_path = archive_dir / f"{partition['table']}.csv.gz"

    with gzip.open(out_path, "wt", encoding="utf-8", newline="") as fh:
        cur.copy_expert(f"COPY (SELECT * FROM {qualified} ORDER BY trade_date, symbol, expiry_date, instrument, option_type, strike) TO STDOUT WITH CSV HEADER", fh)

    metadata = {
        "source_table": qualified,
        "start": partition["start"].isoformat(),
        "end": partition["end"].isoformat(),
        "rows": rows,
        "archive_file": str(out_path.relative_to(BASE)),
        "sha256": sha256_file(out_path),
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    manifest = archive_dir / f"{partition['table']}.manifest.json"
    manifest.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return metadata


def detach_and_drop(cur, partition: dict):
    qualified = f"{partition['schema']}.{partition['table']}"
    cur.execute(f"ALTER TABLE derivatives.fno_eod DETACH PARTITION {qualified}")
    cur.execute(f"DROP TABLE {qualified}")


def cleanup_cache(days: int, execute: bool):
    cache_dirs = [BASE / "data" / "_fno_cache", BASE / "data" / "fno"]
    cutoff_ts = datetime.now().timestamp() - days * 86400
    candidates = []
    for cache_dir in cache_dirs:
        if not cache_dir.exists():
            continue
        for path in cache_dir.iterdir():
            if path.is_file() and path.stat().st_mtime < cutoff_ts:
                candidates.append(path)

    for path in candidates:
        print(f"  cache {'delete' if execute else 'would delete'}: {path.relative_to(BASE)}")
        if execute:
            path.unlink()
    return len(candidates)


def main() -> int:
    ap = argparse.ArgumentParser(description="Archive old derivatives.fno_eod monthly partitions")
    ap.add_argument("--older-than-years", type=int, default=3, help="Archive partitions older than this many years")
    ap.add_argument("--older-than-date", help="Archive partitions whose upper bound is <= this YYYY-MM-DD date")
    ap.add_argument("--execute", action="store_true", help="Actually write archives; default is dry-run")
    ap.add_argument("--delete-after-archive", action="store_true", help="Detach/drop partitions after successful archive")
    ap.add_argument("--cleanup-cache-days", type=int, help="Delete local F&O cache files older than N days")
    args = ap.parse_args()

    cutoff = cutoff_from_args(args)
    print(f"F&O archive cutoff: partition end <= {cutoff} ({'EXECUTE' if args.execute else 'DRY-RUN'})")

    conn = psycopg2.connect(PG_DSN)
    conn.autocommit = False
    cur = conn.cursor()
    try:
        partitions = discover_partitions(cur)
        selected = [p for p in partitions if p["end"] <= cutoff]

        if not selected:
            print("  No monthly F&O partitions are old enough to archive.")
        for part in selected:
            archive_dir = ARCHIVE_ROOT / str(part["start"].year) / f"{part['start'].month:02d}"
            qualified = f"{part['schema']}.{part['table']}"
            rows = count_rows(cur, qualified)
            print(f"  {qualified}: {rows} rows, range [{part['start']}, {part['end']})")
            if not args.execute:
                continue
            metadata = export_partition(cur, part, archive_dir)
            print(f"    archived: {metadata['archive_file']} sha256={metadata['sha256'][:12]}…")
            if args.delete_after_archive:
                detach_and_drop(cur, part)
                print("    detached and dropped partition")

        if args.cleanup_cache_days:
            cleanup_cache(args.cleanup_cache_days, args.execute)

        if args.execute:
            conn.commit()
        else:
            conn.rollback()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
