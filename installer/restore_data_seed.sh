#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# restore_data_seed.sh
#
# Restore a pg_dump seed bundle produced by package_data_seed.sh.
# Idempotent — uses pg_restore --clean --if-exists.
#
# Usage:
#   ./installer/restore_data_seed.sh path/to/agent-adda-data-2026.05.12.tar.gz
#   ./installer/restore_data_seed.sh path/to/seed.dump            # already-extracted
#   ./installer/restore_data_seed.sh path/to/dump --no-clean      # additive (no row wipe)
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Resolve PG_DSN: env var wins, then .env, then default. Lets recipients
# override transparently:  PG_DSN='dbname=…' ./installer/restore_data_seed.sh …
if [[ -z "${PG_DSN:-}" && -f "$ROOT/.env" ]]; then
    PG_DSN="$(grep -E '^PG_DSN=' "$ROOT/.env" | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'")"
fi
PG_DSN="${PG_DSN:-dbname=nse_market user=nse_admin host=/tmp}"

CLEAN_FLAGS=(--clean --if-exists)
SEED_PATH=""
for arg in "$@"; do
    case "$arg" in
        --no-clean) CLEAN_FLAGS=() ;;
        -h|--help)
            sed -n '2,12p' "${BASH_SOURCE[0]}" | sed 's/^# \?//'; exit 0 ;;
        *) SEED_PATH="$arg" ;;
    esac
done

[[ -n "$SEED_PATH" && -e "$SEED_PATH" ]] || {
    echo "Usage: $0 <seed.tar.gz | seed.dump> [--no-clean]" >&2
    exit 1
}

command -v pg_restore >/dev/null || { echo "✗ pg_restore not found"; exit 1; }
psql "$PG_DSN" -c "SELECT 1" >/dev/null 2>&1 || { echo "✗ Cannot connect to: $PG_DSN"; exit 1; }

# Resolve to a .dump file
DUMP_FILE=""
TMP_EXTRACT=""
case "$SEED_PATH" in
    *.tar.gz|*.tgz)
        TMP_EXTRACT="$(mktemp -d)"
        echo "── Extracting seed bundle ──"
        tar -xzf "$SEED_PATH" -C "$TMP_EXTRACT"
        DUMP_FILE="$(find "$TMP_EXTRACT" -name "seed.dump" -o -name "*.dump" | head -1)"
        [[ -n "$DUMP_FILE" ]] || { echo "✗ no .dump found in archive"; exit 1; }
        echo "  ✓ $DUMP_FILE"
        ;;
    *.dump|*.sql|*.bak)
        DUMP_FILE="$SEED_PATH"
        ;;
    *)
        echo "✗ Unrecognised file type: $SEED_PATH" >&2
        echo "  Expected .tar.gz, .tgz, .dump, .sql, or .bak"
        exit 1
        ;;
esac

DUMP_SIZE=$(du -h "$DUMP_FILE" | cut -f1)
echo "── Restoring into: $PG_DSN ──"
echo "  source: $DUMP_FILE  ($DUMP_SIZE)"
[[ ${#CLEAN_FLAGS[@]} -gt 0 ]] && echo "  mode: clean (wipes existing rows in seeded tables)" || echo "  mode: additive (no row wipe)"

# Confirm if interactive
if [[ -t 0 && ${#CLEAN_FLAGS[@]} -gt 0 ]]; then
    read -r -p "  Continue? [y/N] " ans
    [[ "$ans" =~ ^[Yy] ]] || { echo "  aborted"; exit 2; }
fi

START=$(date +%s)
pg_restore -d "$PG_DSN" --no-owner --no-privileges "${CLEAN_FLAGS[@]}" \
           --jobs=4 --verbose "$DUMP_FILE" 2>&1 | tail -20 || {
    echo "  ⚠ pg_restore reported errors (often benign — duplicate role/grant warnings)"
}
ELAPSED=$(( $(date +%s) - START ))
echo "  ✓ restore complete in ${ELAPSED}s"

# Cleanup extract dir
[[ -n "$TMP_EXTRACT" ]] && rm -rf "$TMP_EXTRACT"

# Verify with doctor
if [[ -x "$ROOT/.venv/bin/python" && -f "$ROOT/installer/doctor.py" ]]; then
    echo
    echo "── Verifying with doctor ──"
    "$ROOT/.venv/bin/python" "$ROOT/installer/doctor.py" 2>&1 | grep -A1 "PostgreSQL" | head -20
fi

cat <<EOF

Restore done.

Next:
  .venv/bin/python installer/doctor.py    # full health check
  .venv/bin/python daily_refresh.py        # bring data up to today

EOF
