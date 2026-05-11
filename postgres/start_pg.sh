#!/usr/bin/env bash
# postgres/start_pg.sh — Start the local NSE PostgreSQL cluster
# Usage: ./postgres/start_pg.sh [start|stop|status|restart]

set -euo pipefail

export PATH="/opt/homebrew/opt/postgresql@16/bin:$PATH"
PG_DATA="$(cd "$(dirname "$0")" && pwd)/data"
PG_LOG="$(cd "$(dirname "$0")" && pwd)/postgres.log"

cmd="${1:-start}"

case "$cmd" in
  start)
    if pg_ctl -D "$PG_DATA" status &>/dev/null; then
      echo "✅ PostgreSQL already running"
    else
      echo "Starting PostgreSQL…"
      pg_ctl -D "$PG_DATA" -l "$PG_LOG" start
      echo "✅ PostgreSQL started  (log: $PG_LOG)"
    fi
    ;;
  stop)
    pg_ctl -D "$PG_DATA" stop -m fast
    echo "✅ PostgreSQL stopped"
    ;;
  restart)
    pg_ctl -D "$PG_DATA" stop -m fast 2>/dev/null || true
    pg_ctl -D "$PG_DATA" -l "$PG_LOG" start
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
