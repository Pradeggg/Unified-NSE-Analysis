#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# package_distribution.sh
#
# Build a clean, redistributable tarball of Agent Adda that:
#   • Excludes secrets (.env, *.local) — recipients use installer/.env.template
#   • Excludes generated/built artefacts (.venv, data/, reports/, logs/, .app)
#   • Excludes the developer-only OneDrive workspace copy
#   • Includes everything needed for `./installer/install.sh` to work end-to-end
#
# Output:
#   dist/agent-adda-<version>.tar.gz       (≈ 3–5 MB)
#   dist/agent-adda-<version>.sha256       (checksum)
#   dist/agent-adda-<version>.MANIFEST     (full file list)
#
# Usage:
#   ./installer/package_distribution.sh                # version=YYYY.MM.DD
#   ./installer/package_distribution.sh --version 1.0.0
#   ./installer/package_distribution.sh --dry-run     # show what would be packed
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

VERSION="$(date +%Y.%m.%d)"
DRY_RUN=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --version) VERSION="$2"; shift 2 ;;
        --dry-run) DRY_RUN=1; shift ;;
        -h|--help)
            sed -n '2,18p' "${BASH_SOURCE[0]}" | sed 's/^# \?//'; exit 0 ;;
        *) echo "Unknown arg: $1" >&2; exit 1 ;;
    esac
done

NAME="agent-adda-${VERSION}"
DIST_DIR="$ROOT/dist"
STAGE_DIR="$DIST_DIR/.stage/$NAME"
TARBALL="$DIST_DIR/$NAME.tar.gz"

echo "── Packaging $NAME ──"
mkdir -p "$DIST_DIR"
rm -rf "$STAGE_DIR" "$DIST_DIR/.stage"
mkdir -p "$STAGE_DIR"

# ── Inclusion list — what ships ─────────────────────────────────────────────
# Top-level paths to copy (rsync preserves their structure).
INCLUDE_PATHS=(
    # Top-level scripts (filtered by EXCLUDE below)
    "core" "terminal" "knowledge_base" "reports" "portfolio-analyzer"
    "scripts" "tests" "working-sector" "postgres" "docs" "installer"
)
# Top-level files (explicit so we don't sweep date-stamped artefacts)
INCLUDE_FILES=(
    "*.py" "Makefile" "Makefile.*" "config.R"
    "README.md" "SETUP.md" "EMAIL_REPORTS_README.md"
    "backlog.md" "AI_Platform_Ways_of_Working_Diagram.md"
    "AI_Platform_Ways_of_Working_Dashboard.html"
    "BACKTESTING_ENGINE_ANALYSIS.md" "BACKTESTING_INTEGRATION_SUMMARY.md"
    "HTML_DASHBOARD_INTEGRATION_NEEDED.md"
    "requirements.txt" "requirements-dev.txt"
    ".gitignore" "readme.txt"
)

EXCLUDE_PATTERNS=(
    # Secrets / per-user state — be SURGICAL: don't match .env.template / .env.example
    ".env" ".env.local" ".env.development.local" ".env.production.local"
    ".env.staging.local" ".env.test.local"
    "config.local.*"
    # Generated output
    ".venv/" "venv/" "__pycache__/" "*.pyc" ".pytest_cache/"
    "*.log" "logs/" "tmp/"
    # User-specific data — recipients regenerate via daily_refresh.py
    "data/" "output/" "organized/" "archive/"
    # Generated HTML/PDF/CSV reports — bulky, regenerated on first run
    "*.html" "*.pdf"
    "reports/_*" "reports/temp/" "reports/generated/" "reports/generated_csv/"
    "reports/voice_briefings/" "reports/sector_rotation/"
    "reports/model_benchmarks/" "reports/email_archive/"
    "reports/talk_2_stocks/" "reports/nse_analysis/" "reports/latest/"
    "reports/deliberation/"
    # Bulky CSV/parquet/zip dumps
    "*.csv" "*.parquet" "*.zip"
    # Built artefacts
    "installer/macos/Agent Adda.app/" "installer/macos/"
    "installer/launchd/com.agentadda.*.plist"
    # NOTE: installer/.env.template SHIPS (it's the source of truth for .env keys)
    # VCS / OS / IDE
    ".git/" ".DS_Store" ".vscode/" ".idea/" "dist/"
    # Daily exchange download artefacts (date-stamped at root)
    "*[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9].csv"
    "*[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9].txt"
    "PR*.zip"
    # Knowledge-base artifacts (large, regenerated on first ingest)
    "knowledge_base/data/" "knowledge_base/cache/"
    "*.faiss" "*.index" "*.npz" "*.pkl"
    # Test fixtures left on disk (we ship the .py tests, not their outputs)
    "tests/fixtures/large_*"
)

# Build rsync exclude args
RSYNC_EXCL=()
for pat in "${EXCLUDE_PATTERNS[@]}"; do RSYNC_EXCL+=(--exclude="$pat"); done

if [[ $DRY_RUN -eq 1 ]]; then
    echo "  Would copy these top-level paths (with the exclusion list applied):"
    for p in "${INCLUDE_PATHS[@]}"; do [[ -e "$p" ]] && echo "    + $p/"; done
    for pat in "${INCLUDE_FILES[@]}"; do
        compgen -G "$pat" >/dev/null 2>&1 && for f in $(compgen -G "$pat"); do echo "    + $f"; done
    done
    echo
    echo "  Excluding patterns:"
    for pat in "${EXCLUDE_PATTERNS[@]}"; do echo "    - $pat"; done
    echo
    echo "  Sample of files that would ship:"
    rsync -a --dry-run --itemize-changes "${RSYNC_EXCL[@]}" \
        "${INCLUDE_PATHS[@]}" "$STAGE_DIR/" 2>/dev/null | head -30
    rm -rf "$DIST_DIR/.stage"
    exit 0
fi

# Stage — single rsync call preserves top-level directory structure
EXISTING_PATHS=()
for p in "${INCLUDE_PATHS[@]}"; do [[ -e "$p" ]] && EXISTING_PATHS+=("$p"); done
rsync -a "${RSYNC_EXCL[@]}" "${EXISTING_PATHS[@]}" "$STAGE_DIR/"

# Top-level files
for pat in "${INCLUDE_FILES[@]}"; do
    if compgen -G "$pat" >/dev/null 2>&1; then
        cp $(compgen -G "$pat") "$STAGE_DIR/" 2>/dev/null || true
    fi
done
echo "  ✓ staged sources at $STAGE_DIR"

# Inject a VERSION file the installer can read
cat > "$STAGE_DIR/VERSION" <<EOF
agent-adda
version=$VERSION
build_date=$(date -u +%Y-%m-%dT%H:%M:%SZ)
build_host=$(hostname)
EOF

# Inject a fresh .env from template so recipients can edit before running wizard
cp "$STAGE_DIR/installer/.env.template" "$STAGE_DIR/.env.example" 2>/dev/null || true

# Promote the distribution README to the top level so recipients see it first
if [[ -f "$STAGE_DIR/installer/DISTRIBUTION_README.md" ]]; then
    cp "$STAGE_DIR/installer/DISTRIBUTION_README.md" "$STAGE_DIR/README_FIRST.md"
fi

# Sanity: make sure no secrets leaked
LEAKS=$(find "$STAGE_DIR" -name ".env" -o -name "*.local" 2>/dev/null | head)
if [[ -n "$LEAKS" ]]; then
    echo "  ✗ ABORT — secrets leaked into stage:"
    echo "$LEAKS"
    exit 1
fi
echo "  ✓ no secrets in stage"

# Manifest
( cd "$DIST_DIR/.stage" && find "$NAME" -type f | sort ) > "$DIST_DIR/$NAME.MANIFEST"
echo "  ✓ manifest: $(wc -l < "$DIST_DIR/$NAME.MANIFEST") files"

# Tarball
( cd "$DIST_DIR/.stage" && tar -czf "$TARBALL" "$NAME" )
SIZE=$(du -h "$TARBALL" | cut -f1)
echo "  ✓ tarball: $TARBALL ($SIZE)"

# Checksum
( cd "$DIST_DIR" && shasum -a 256 "$NAME.tar.gz" > "$NAME.sha256" )
echo "  ✓ sha256:  $(cat "$DIST_DIR/$NAME.sha256")"

# Cleanup stage
rm -rf "$DIST_DIR/.stage"

cat <<EOF

Distribution ready.

  Tarball:   dist/$NAME.tar.gz  ($SIZE)
  Manifest:  dist/$NAME.MANIFEST
  Checksum:  dist/$NAME.sha256

To verify on a recipient's machine:
  shasum -a 256 -c $NAME.sha256
  tar -xzf $NAME.tar.gz
  cd $NAME
  ./installer/install.sh

EOF
