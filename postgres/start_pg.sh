#!/usr/bin/env bash
# postgres/start_pg.sh — Start the local NSE PostgreSQL cluster
# Usage: ./postgres/start_pg.sh [start|stop|status|restart]

set -euo pipefail

export PATH="/opt/homebrew/opt/postgresql@16/bin:$PATH"
PG_DATA="$(cd "$(dirname "$0")" && pwd)/data"
PG_LOG="$(cd "$(dirname "$0")" && pwd)/postgres.log"

cmd="${1:-start}"

PG_SERVER_OPTS="${PG_SERVER_OPTS:-}"
if [[ -z "$PG_SERVER_OPTS" ]]; then
  # In managed/sandboxed environments, SysV shared memory may be blocked and
  # PostgreSQL can fail to boot with "could not create shared memory segment".
  # Use mmap/posix shared memory to keep local dev usable.
  PG_SERVER_OPTS="-c shared_memory_type=mmap -c dynamic_shared_memory_type=posix"
fi

case "$cmd" in
  start)
    if pg_ctl -D "$PG_DATA" status &>/dev/null; then
      echo "✅ PostgreSQL already running"
    else
      chmod 700 "$PG_DATA" 2>/dev/null || true
      rm -f "$PG_DATA/postmaster.pid"
      echo "Starting PostgreSQL…"
      if ! pg_ctl -D "$PG_DATA" -l "$PG_LOG" -o "$PG_SERVER_OPTS" start; then
        echo "❌ PostgreSQL failed to start. Last log lines:"
        tail -40 "$PG_LOG" 2>/dev/null || true
        exit 1
      fi
      echo "✅ PostgreSQL started  (log: $PG_LOG)"
    fi
    ;;
  stop)
    pg_ctl -D "$PG_DATA" stop -m fast
    echo "✅ PostgreSQL stopped"
    ;;
  restart)
    pg_ctl -D "$PG_DATA" stop -m fast 2>/dev/null || true
    pg_ctl -D "$PG_DATA" -l "$PG_LOG" -o "$PG_SERVER_OPTS" start
    echo "✅ PostgreSQL restarted"
    ;;
  status)
    pg_ctl -D "$PG_DATA" status
    ;;
  *)
    echo "Usage: $0 {start|stop|status|restart}"
    exit 1
    ;;
esac
