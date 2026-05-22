"""Seed ``market.symbol_aliases`` from :mod:`terminal.symbol_search.alias_source`.

AA-HSR-2 — idempotent. Run any time the in-process alias map changes:

    python scripts/seed_symbol_aliases.py                # full reload
    python scripts/seed_symbol_aliases.py --dry-run      # no writes, print summary
    python scripts/seed_symbol_aliases.py --skip-pg      # manual + index + sector only

The script:

* Detects a missing ``market.symbol_aliases`` table (AA-HSR-3 migration not
  yet applied) and exits 2 with a clear hint.
* Detects an empty alias source (e.g. Postgres reachable but ``ref.instruments``
  empty) and exits 3.
* Uses ``ON CONFLICT (symbol, name, kind) DO UPDATE`` so reruns do not
  inflate the row count.
* Prints a per-kind / per-source summary so operators can spot regressions
  quickly.

Exit codes:
    0  success
    2  table missing — run AA-HSR-3 migration first
    3  alias source produced zero records
    4  database error
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from terminal.symbol_search.alias_source import (
    AliasRecord,
    alias_summary,
    iter_aliases,
)

log = logging.getLogger(__name__)

UPSERT_SQL = """
INSERT INTO market.symbol_aliases (symbol, name, kind, weight, source, updated_at)
VALUES (%s, %s, %s, %s, %s, now())
ON CONFLICT (symbol, name, kind) DO UPDATE
   SET weight     = EXCLUDED.weight,
       source     = EXCLUDED.source,
       updated_at = now()
"""

TABLE_EXISTS_SQL = """
SELECT EXISTS (
    SELECT 1
    FROM   information_schema.tables
    WHERE  table_schema = 'market'
    AND    table_name   = 'symbol_aliases'
)
"""


def _connect():
    """Lazy psycopg2 connect via the neutral DSN helper."""
    from terminal import postgres_tools as pg
    return pg._connect()


def _table_exists(conn) -> bool:
    with conn.cursor() as cur:
        cur.execute(TABLE_EXISTS_SQL)
        return bool(cur.fetchone()[0])


def _upsert(conn, records: list[AliasRecord]) -> int:
    payload = [
        (r.symbol, r.name, r.kind, r.weight, r.source)
        for r in records
    ]
    with conn.cursor() as cur:
        cur.executemany(UPSERT_SQL, payload)
    conn.commit()
    return len(payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="print the summary without touching the database")
    parser.add_argument("--skip-pg", action="store_true",
                        help="do not pull from ref.instruments / mv_latest_snapshot")
    parser.add_argument("--json", action="store_true",
                        help="emit the summary as JSON instead of text")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    records = list(iter_aliases(include_pg=not args.skip_pg))
    summary = alias_summary(records)

    if args.json:
        print(json.dumps(summary, sort_keys=True, indent=2))
    else:
        print(f"Prepared {summary['total']} alias rows")
        print(f"  by_kind:   {summary['by_kind']}")
        print(f"  by_source: {summary['by_source']}")

    if summary["total"] == 0:
        log.error(
            "Alias source produced zero records. "
            "Postgres unreachable or ref.instruments / mv_latest_snapshot empty?"
        )
        return 3

    if args.dry_run:
        print("(dry-run) no rows written")
        return 0

    try:
        conn = _connect()
    except Exception as exc:
        log.error("Cannot connect to Postgres: %s", exc)
        return 4

    try:
        if not _table_exists(conn):
            log.error(
                "market.symbol_aliases does not exist. "
                "Run the AA-HSR-3 migration first: "
                "postgres/migrations/20260523_symbol_resolution_trgm.sql"
            )
            return 2
        upserted = _upsert(conn, records)
    except Exception as exc:
        log.exception("Upsert failed: %s", exc)
        return 4
    finally:
        try:
            conn.close()
        except Exception:
            pass

    print(f"Upserted {upserted} rows into market.symbol_aliases")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
