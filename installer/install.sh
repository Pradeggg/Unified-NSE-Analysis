#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Agent Adda — One-Shot Installer (macOS / Linux)
# ─────────────────────────────────────────────────────────────────────────────
# What it does (idempotent — safe to re-run):
#   1. Detects OS + arch and verifies prerequisites
#   2. Installs system packages (Python 3.11+, PostgreSQL, ffmpeg, optional R)
#      via Homebrew (macOS) or apt (Debian/Ubuntu)
#   3. Creates / refreshes a Python 3 virtualenv at .venv
#   4. Installs pinned pip dependencies
#   5. Hands off to setup_wizard.py for API keys, DB, schemas, smoke tests
#
# Usage:
#   ./installer/install.sh                # full install
#   ./installer/install.sh --skip-system  # skip brew/apt steps (CI / no sudo)
#   ./installer/install.sh --skip-wizard  # build env only, do not run wizard
#   ./installer/install.sh --check        # only check what's missing
#   ./installer/install.sh --with-dev     # also install requirements-dev.txt (pytest)
#
# Exit codes:
#   0  success
#   1  prerequisite missing the user must install manually
#   2  user aborted
#   3  pip install failed
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

# ── colours / glyphs ─────────────────────────────────────────────────────────
if [[ -t 1 ]]; then
    BOLD=$'\033[1m'; DIM=$'\033[2m'; RED=$'\033[31m'; GRN=$'\033[32m'
    YEL=$'\033[33m'; BLU=$'\033[34m'; CYN=$'\033[36m'; OFF=$'\033[0m'
else
    BOLD=""; DIM=""; RED=""; GRN=""; YEL=""; BLU=""; CYN=""; OFF=""
fi
ok()    { printf "  %s✓%s %s\n" "$GRN" "$OFF" "$1"; }
info()  { printf "  %s•%s %s\n" "$CYN" "$OFF" "$1"; }
warn()  { printf "  %s⚠%s %s\n" "$YEL" "$OFF" "$1"; }
err()   { printf "  %s✗%s %s\n" "$RED" "$OFF" "$1" >&2; }
step()  { printf "\n%s── %s ──%s\n" "$BOLD" "$1" "$OFF"; }

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# ── parse args ───────────────────────────────────────────────────────────────
SKIP_SYSTEM=0
SKIP_WIZARD=0
CHECK_ONLY=0
WITH_DEV=0
for arg in "$@"; do
    case "$arg" in
        --skip-system) SKIP_SYSTEM=1 ;;
        --skip-wizard) SKIP_WIZARD=1 ;;
        --check)       CHECK_ONLY=1 ;;
        --with-dev)    WITH_DEV=1 ;;
        -h|--help)
            sed -n '2,25p' "${BASH_SOURCE[0]}" | sed 's/^# \?//'
            exit 0 ;;
        *) err "Unknown arg: $arg"; exit 1 ;;
    esac
done

# ── banner ───────────────────────────────────────────────────────────────────
cat <<'EOF'

   ╔══════════════════════════════════════════════════════════════════╗
   ║         Agent Adda — Market Intelligence Agent Installer         ║
   ╚══════════════════════════════════════════════════════════════════╝

EOF
info "Project root: $ROOT_DIR"

# ── 1. detect OS ─────────────────────────────────────────────────────────────
step "Step 1/5  ·  Detect operating system"
OS_KIND=""; PKG_MGR=""; INSTALL_CMD=""
case "$(uname -s)" in
    Darwin)
        OS_KIND="macos"
        if ! command -v brew >/dev/null 2>&1; then
            err "Homebrew not found. Install it first:"
            echo '       /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
            exit 1
        fi
        PKG_MGR="brew"
        INSTALL_CMD="brew install"
        ok "macOS detected — using Homebrew"
        ;;
    Linux)
        OS_KIND="linux"
        if command -v apt-get >/dev/null 2>&1; then
            PKG_MGR="apt"
            INSTALL_CMD="sudo apt-get install -y"
            ok "Debian/Ubuntu detected — using apt"
        elif command -v dnf >/dev/null 2>&1; then
            PKG_MGR="dnf"; INSTALL_CMD="sudo dnf install -y"
            ok "Fedora/RHEL detected — using dnf"
        else
            err "Unsupported Linux distribution. Install Python 3.11+, PostgreSQL 14+, ffmpeg manually."
            exit 1
        fi
        ;;
    *)
        err "Unsupported OS: $(uname -s). Use WSL on Windows."
        exit 1 ;;
esac

# ── 2. verify / install system deps ──────────────────────────────────────────
step "Step 2/5  ·  System packages"
need_install=()
check_cmd() {
    local cmd="$1" pkg="$2" min="${3:-}"
    if command -v "$cmd" >/dev/null 2>&1; then
        ok "$cmd found ($(command -v "$cmd"))"
    else
        warn "$cmd missing — will install '$pkg'"
        need_install+=("$pkg")
    fi
}

# Python 3.11+
PY_BIN=""
for cand in python3.13 python3.12 python3.11 python3; do
    if command -v "$cand" >/dev/null 2>&1; then
        v=$("$cand" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
        major=${v%%.*}; minor=${v##*.}
        if [[ "$major" -eq 3 && "$minor" -ge 11 ]]; then
            PY_BIN="$cand"; ok "$cand found (v$v)"; break
        fi
    fi
done
if [[ -z "$PY_BIN" ]]; then
    warn "Python 3.11+ not found — will install"
    if [[ "$OS_KIND" == "macos" ]]; then need_install+=("python@3.13"); else need_install+=("python3.11" "python3.11-venv"); fi
fi

# PostgreSQL client + server
check_cmd psql       "postgresql@16"
check_cmd pg_ctl     "postgresql@16"
# Audio / media
check_cmd ffmpeg     "ffmpeg"
# Optional: R (only required by EOD pipeline)
if [[ "$OS_KIND" == "macos" ]]; then
    if command -v Rscript >/dev/null 2>&1; then ok "Rscript found"; else
        warn "Rscript missing — only needed for the R EOD pipeline; skipping (install with: brew install r)"
    fi
fi

if [[ "$CHECK_ONLY" -eq 1 ]]; then
    if [[ ${#need_install[@]} -eq 0 ]]; then
        ok "All system deps satisfied."
    else
        warn "Missing: ${need_install[*]}"
    fi
    exit 0
fi

if [[ ${#need_install[@]} -gt 0 && "$SKIP_SYSTEM" -eq 0 ]]; then
    info "Installing: ${need_install[*]}"
    # shellcheck disable=SC2086
    $INSTALL_CMD "${need_install[@]}"
    # Refresh PY_BIN
    for cand in python3.13 python3.12 python3.11 python3; do
        if command -v "$cand" >/dev/null 2>&1; then PY_BIN="$cand"; break; fi
    done
elif [[ "$SKIP_SYSTEM" -eq 1 ]]; then
    info "--skip-system set, skipping package installation"
fi

[[ -z "$PY_BIN" ]] && { err "No Python 3.11+ available after install. Aborting."; exit 1; }

# ── 3. create / refresh venv ─────────────────────────────────────────────────
step "Step 3/5  ·  Python virtualenv (.venv)"
if [[ -d ".venv" ]]; then
    info ".venv already exists — re-using"
else
    "$PY_BIN" -m venv .venv
    ok "Created .venv with $PY_BIN"
fi
# shellcheck disable=SC1091
source .venv/bin/activate
ok "Activated venv: $(which python) ($(python -V))"

# ── 4. install pip deps ──────────────────────────────────────────────────────
step "Step 4/5  ·  Python packages"
python -m pip install --quiet --upgrade pip wheel setuptools
if ! python -m pip install --quiet -r requirements.txt; then
    err "pip install failed. Re-run with: .venv/bin/pip install -r requirements.txt"
    exit 3
fi
ok "Installed $(python -m pip freeze 2>/dev/null | wc -l | tr -d ' ') packages"

# Optional: dev dependencies (pytest etc.) — opt-in via --with-dev
if [[ "$WITH_DEV" -eq 1 && -f "requirements-dev.txt" ]]; then
    info "Installing dev dependencies (requirements-dev.txt)…"
    python -m pip install --quiet -r requirements-dev.txt && ok "Dev deps installed"
fi

# Optional: install Playwright Chromium for HTML→PDF report export
if python -c "import playwright" 2>/dev/null; then
    if ! python -c "from playwright.sync_api import sync_playwright; sync_playwright().__enter__().chromium.executable_path" 2>/dev/null; then
        info "Installing Playwright Chromium (for PDF export of HTML reports)…"
        python -m playwright install --with-deps chromium >/dev/null 2>&1 || warn "Playwright chromium install failed (PDF export disabled)"
    fi
fi

# ── 5. hand off to setup wizard ──────────────────────────────────────────────
if [[ "$SKIP_WIZARD" -eq 1 ]]; then
    step "Step 5/5  ·  Skipped wizard (--skip-wizard)"
    info "Run interactively later with: .venv/bin/python installer/setup_wizard.py"
else
    step "Step 5/5  ·  Interactive setup wizard"
    python installer/setup_wizard.py "$@"
fi

cat <<EOF

${BOLD}${GRN}Done.${OFF}  Next steps:
  ${CYN}.venv/bin/python nse_agent.py${OFF}                  — launch Agent Adda
  ${CYN}.venv/bin/python installer/doctor.py${OFF}           — re-check health any time
  ${CYN}make -C installer help${OFF}                         — show all install commands

EOF
