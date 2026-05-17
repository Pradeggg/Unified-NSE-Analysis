#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# package_data_seed.sh
#
# Build a redistributable PostgreSQL seed bundle of Agent Adda's historical
# market data so recipients don't need to wait months for daily_refresh.py to
# populate equity_eod / scores from scratch.
#
# Output:
#   dist/agent-adda-data-<version>.tar.gz       (compressed pg_dump)
#   dist/agent-adda-data-<version>.sha256
#
# Schemas included:  market.* + scores.* + report.* + intraday.*
# (intraday.* is small and only retains 120 min of live ticks anyway — kept for
# schema completeness; recipients regenerate live ticks once their daemon runs.)
#
# Usage:
#   ./installer/package_data_seed.sh
#   ./installer/package_data_seed.sh --version 1.0.0
#   ./installer/package_data_seed.sh --schemas-only      # structure only, no data
#   ./installer/package_data_seed.sh --no-intraday       # skip volatile intraday tables
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# Resolve PG_DSN: env var wins, then .env, then default.
if [[ -z "${PG_DSN:-}" && -f .env ]]; then
    PG_DSN="$(grep -E '^PG_DSN=' .env | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'")"
fi
PG_DSN="${PG_DSN:-dbname=nse_market user=nse_admin host=/tmp}"

VERSION="$(date +%Y.%m.%d)"
SCHEMAS_ONLY=0
INCLUDE_INTRADAY=1
while [[ $# -gt 0 ]]; do
    case "$1" in
        --version)        VERSION="$2"; shift 2 ;;
        --schemas-only)   SCHEMAS_ONLY=1; shift ;;
        --no-intraday)    INCLUDE_INTRADAY=0; shift ;;
        -h|--help)
            sed -n '2,21p' "${BASH_SOURCE[0]}" | sed 's/^# \?//'; exit 0 ;;
        *) echo "Unknown arg: $1" >&2; exit 1 ;;
    esac
done

DIST_DIR="$ROOT/dist"
NAME="agent-adda-data-${VERSION}"
DUMP_FILE="$DIST_DIR/${NAME}.dump"          # custom-format (best for selective restore)
TARBALL="$DIST_DIR/${NAME}.tar.gz"
mkdir -p "$DIST_DIR"

echo "── Building $NAME ──"
echo "  PG DSN: $PG_DSN"

command -v pg_dump >/dev/null || { echo "  ✗ pg_dump not found on PATH"; exit 1; }

# Verify connectivity first
if ! psql "$PG_DSN" -c "SELECT 1" >/dev/null 2>&1; then
    echo "  ✗ Cannot connect to: $PG_DSN"; exit 1
fi
echo "  ✓ connected"

# Schemas to dump
SCHEMAS=(market scores report)
[[ $INCLUDE_INTRADAY -eq 1 ]] && SCHEMAS+=(intraday)

DUMP_ARGS=(--format=custom --no-owner --no-privileges --compress=9)
[[ $SCHEMAS_ONLY -eq 1 ]] && DUMP_ARGS+=(--schema-only)
for s in "${SCHEMAS[@]}"; do DUMP_ARGS+=(--schema="$s"); done

echo "  schemas: ${SCHEMAS[*]}"
[[ $SCHEMAS_ONLY -eq 1 ]] && echo "  mode: SCHEMA-ONLY (no row data)"

echo "  running pg_dump (this may take 1–3 minutes for ~600 MB)…"
pg_dump "$PG_DSN" "${DUMP_ARGS[@]}" --file="$DUMP_FILE"

DUMP_SIZE=$(du -h "$DUMP_FILE" | cut -f1)
echo "  ✓ dump: $DUMP_FILE ($DUMP_SIZE)"

# Build a small companion README + restore script inside the tarball
WORK_DIR="$DIST_DIR/.stage_data/${NAME}"
rm -rf "$DIST_DIR/.stage_data"
mkdir -p "$WORK_DIR"
mv "$DUMP_FILE" "$WORK_DIR/seed.dump"

cat > "$WORK_DIR/RESTORE.md" <<EOF
# Agent Adda — Historical Data Seed

Generated: $(date -u +%Y-%m-%dT%H:%M:%SZ)
Schemas:   ${SCHEMAS[*]}
Format:    PostgreSQL custom-format (pg_restore compatible)
Mode:      $([ $SCHEMAS_ONLY -eq 1 ] && echo "schema-only" || echo "schema + data")

## Restore (one command)

From the project root:

\`\`\`bash
./installer/restore_data_seed.sh path/to/agent-adda-data-*.tar.gz
\`\`\`

Or manually:

\`\`\`bash
tar -xzf agent-adda-data-*.tar.gz
pg_restore -d nse_market --no-owner --no-privileges --clean --if-exists ${NAME}/seed.dump
\`\`\`

## Notes

- Restore is **idempotent** thanks to \`--clean --if-exists\`; safe to run multiple times.
- Existing rows are wiped per table before reload — make a backup first if you have local-only data:
  \`\`\`bash
  pg_dump dbname=nse_market > my_local_backup.sql
  \`\`\`
- After restore, run \`make -C installer doctor\` to verify row counts.
- To bring data current after restore: \`.venv/bin/python daily_refresh.py\`
EOF

# Manifest
( cd "$DIST_DIR/.stage_data" && find "$NAME" -type f -exec ls -la {} \; ) > "$DIST_DIR/${NAME}.MANIFEST"

# Tarball
( cd "$DIST_DIR/.stage_data" && tar -czf "$TARBALL" "$NAME" )
TAR_SIZE=$(du -h "$TARBALL" | cut -f1)
echo "  ✓ tarball: $TARBALL ($TAR_SIZE)"

# Checksum
( cd "$DIST_DIR" && shasum -a 256 "${NAME}.tar.gz" > "${NAME}.sha256" )
echo "  ✓ sha256:  $(cat "$DIST_DIR/${NAME}.sha256")"

# Cleanup
rm -rf "$DIST_DIR/.stage_data"

cat <<EOF

Data seed ready.

  Tarball:   dist/${NAME}.tar.gz  ($TAR_SIZE)
  Checksum:  dist/${NAME}.sha256

Recipients restore with:
  ./installer/restore_data_seed.sh ${NAME}.tar.gz

EOF
