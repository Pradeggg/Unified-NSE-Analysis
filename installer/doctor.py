#!/usr/bin/env python3
"""Agent Adda — Doctor.

Runs read-only health checks across every layer the agent depends on:
  • Python version + venv
  • Required & optional pip packages
  • Required & optional system binaries (psql, ffmpeg, R, ollama)
  • PostgreSQL connectivity + critical schemas/tables
  • Background capture daemon module imports + insertable
  • API keys configured (which integrations will actually work)
  • Background services registered (launchd/systemd)
  • Disk + log directories
  • Built HTML reports present

Exit codes:
  0 — all checks pass
  1 — at least one REQUIRED check failed
"""
from __future__ import annotations

import importlib
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"

# load .env without requiring python-dotenv
def _load_env() -> dict[str, str]:
    out: dict[str, str] = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            k, _, v = s.partition("=")
            out[k.strip()] = v.strip().strip('"').strip("'")
    out.update({k: v for k, v in os.environ.items() if k not in out})
    return out

_TTY = sys.stdout.isatty()
def _c(code, s): return f"\033[{code}m{s}\033[0m" if _TTY else s
GRN  = lambda s: _c("32", s)
RED  = lambda s: _c("31", s)
YEL  = lambda s: _c("33", s)
DIM  = lambda s: _c("2",  s)
CYN  = lambda s: _c("36", s)
BOLD = lambda s: _c("1",  s)

PASS, FAIL, WARN = 0, 0, 0
def _pass(label: str, detail: str = "") -> None:
    global PASS; PASS += 1
    print(f"  {GRN('✓')} {label}" + (f"  {DIM('— ' + detail)}" if detail else ""))
def _fail(label: str, detail: str = "") -> None:
    global FAIL; FAIL += 1
    print(f"  {RED('✗')} {label}" + (f"  {RED('— ' + detail)}" if detail else ""))
def _warn(label: str, detail: str = "") -> None:
    global WARN; WARN += 1
    print(f"  {YEL('⚠')} {label}" + (f"  {DIM('— ' + detail)}" if detail else ""))
def _section(t: str) -> None:
    print(f"\n{BOLD('── ' + t + ' ──')}")


# ─────────────────────────────────────────────────────────────────────────────
ENV = _load_env()


def check_python() -> None:
    _section("Python runtime")
    v = sys.version_info
    if (v.major, v.minor) >= (3, 11):
        _pass(f"Python {v.major}.{v.minor}.{v.micro}")
    else:
        _fail(f"Python {v.major}.{v.minor} (need 3.11+)")
    venv = ROOT / ".venv"
    if venv.exists():
        _pass(f"venv: {venv}")
    else:
        _fail(f"venv missing at {venv}", "run installer/install.sh")
    in_venv = sys.prefix != sys.base_prefix
    if in_venv:
        _pass(f"running inside venv: {sys.prefix}")
    else:
        _warn(f"not in venv  ({sys.prefix})", "use .venv/bin/python")


REQUIRED_PIP = [
    ("psycopg2",   "psycopg2-binary"),
    ("pandas",     "pandas"),
    ("numpy",      "numpy"),
    ("requests",   "requests"),
    ("rich",       "rich"),
    ("prompt_toolkit", "prompt_toolkit"),
    ("openai",     "openai"),
]
OPTIONAL_PIP = [
    ("ollama",     "ollama"),
    ("yfinance",   "yfinance"),
    ("playwright", "playwright"),
    ("pymupdf",    "pymupdf"),
    ("pandas_ta",  "pandas-ta"),
    ("dotenv",     "python-dotenv"),
]

def check_pip_packages() -> None:
    _section("Python packages")
    for mod, pkg in REQUIRED_PIP:
        try:
            importlib.import_module(mod)
            _pass(f"{pkg}")
        except ImportError as e:
            _fail(f"{pkg}", str(e))
    for mod, pkg in OPTIONAL_PIP:
        try:
            importlib.import_module(mod)
            _pass(f"{pkg}  (optional)")
        except ImportError:
            _warn(f"{pkg}  (optional, missing)")


def check_system_bins() -> None:
    _section("System binaries")
    for name, required in [
        ("psql",     True),
        ("postgres", False),
        ("ffmpeg",   False),
        ("Rscript",  False),
        ("ollama",   False),
        ("git",      False),
    ]:
        path = shutil.which(name)
        if path:
            _pass(f"{name}", path)
        elif required:
            _fail(f"{name}", "missing — required")
        else:
            _warn(f"{name}", "not found (optional)")


def check_postgres() -> None:
    _section("PostgreSQL")
    dsn = ENV.get("PG_DSN", "").strip()
    if not dsn:
        _fail("PG_DSN missing in .env"); return
    try:
        import psycopg2
    except ImportError:
        _fail("psycopg2 not installed"); return
    try:
        conn = psycopg2.connect(dsn, connect_timeout=5)
    except Exception as e:
        _fail("connect failed", str(e).splitlines()[0]); return
    _pass(f"connected: {dsn}")

    REQUIRED_TABLES = [
        ("market",   "equity_eod"),
        ("market",   "index_eod"),
        ("intraday", "quote_snapshots"),
        ("scores",   "fundamental_scores"),
        ("scores",   "v_latest_fundamental_scores"),
        ("report",   "enhanced_runs"),
        ("report",   "enhanced_filtered_stocks"),
        ("report",   "enhanced_indices"),
    ]
    with conn.cursor() as cur:
        for schema, tbl in REQUIRED_TABLES:
            cur.execute("SELECT to_regclass(%s)", (f"{schema}.{tbl}",))
            ok = cur.fetchone()[0] is not None
            if ok:
                cur.execute(f"SELECT COUNT(*) FROM {schema}.{tbl}")
                n = cur.fetchone()[0]
                _pass(f"{schema}.{tbl}", f"{n:,} rows")
            else:
                _fail(f"{schema}.{tbl}", "missing — run migrations")
    conn.close()


def check_capture_daemon() -> None:
    _section("Intraday capture daemon")
    try:
        sys.path.insert(0, str(ROOT))
        from terminal import intraday_capture as cap
        _pass("module imports", f"interval={cap.CAPTURE_INTERVAL_SEC}s, retain={cap.RETENTION_MINUTES}min")
        # Don't call _capture_once here (it would insert a row); just verify hooks exist.
        for fn in ("start_background_capture", "_capture_once", "_prune_once"):
            if hasattr(cap, fn):
                _pass(f"hook: {fn}()")
            else:
                _fail(f"hook missing: {fn}()")
    except Exception as e:
        _fail("import failed", str(e))


def check_api_keys() -> None:
    _section("API keys / integrations")
    integrations = [
        ("OPENAI_API_KEY",    "OpenAI (LLM agent backend)",            True),
        ("OLLAMA_HOST",       "Ollama (local LLM)",                    False),
        ("SERPAPI_API_KEY",   "SerpAPI (web search)",                  False),
        ("ANTHROPIC_API_KEY", "Anthropic Claude (sector narratives)",  False),
        ("SMTP_HOST",         "Email reports",                         False),
    ]
    has_llm = bool(ENV.get("OPENAI_API_KEY")) or bool(ENV.get("OLLAMA_HOST"))
    if not has_llm:
        _fail("No LLM backend configured", "set OPENAI_API_KEY or OLLAMA_HOST")
    for key, label, _ in integrations:
        if ENV.get(key):
            _pass(f"{label}", f"({key} set)")
        else:
            _warn(f"{label} disabled", f"({key} not set)")


def check_services() -> None:
    _section("Background services")
    sysname = platform.system()
    if sysname == "Darwin":
        try:
            r = subprocess.run(
                ["launchctl", "list"],
                capture_output=True, text=True, timeout=5,
            )
            registered = [
                line.split("\t")[-1] for line in r.stdout.splitlines()
                if "agentadda" in line
            ]
            for unit in ("com.agentadda.daily_refresh", "com.agentadda.intraday_capture"):
                if unit in registered:
                    _pass(f"launchd: {unit}", "loaded")
                else:
                    _warn(f"launchd: {unit}", "not loaded (optional)")
        except Exception as e:
            _warn("launchctl probe failed", str(e))
    elif sysname == "Linux":
        if shutil.which("systemctl"):
            for unit in ("agentadda-daily-refresh.service", "agentadda-intraday-capture.service"):
                r = subprocess.run(
                    ["systemctl", "is-enabled", unit],
                    capture_output=True, text=True,
                )
                if r.returncode == 0:
                    _pass(f"systemd: {unit}", r.stdout.strip())
                else:
                    _warn(f"systemd: {unit}", "not enabled (optional)")
        else:
            _warn("systemctl not found", "service install skipped")
    else:
        _warn(f"{sysname}: no service-manager check")


def check_assets() -> None:
    _section("Assets & data")
    logo = ROOT / "docs" / "Agent-adda-logo.jpg"
    if logo.exists():
        kb = logo.stat().st_size // 1024
        _pass(f"branding logo present", f"{kb} KB")
    else:
        _warn("branding logo missing", str(logo.relative_to(ROOT)))
    reports_dir = ROOT / "reports"
    if reports_dir.is_dir():
        htmls = list(reports_dir.glob("Enhanced_Comprehensive_Analysis_*.html"))
        if htmls:
            latest = max(htmls, key=lambda p: p.stat().st_mtime)
            _pass(f"latest report: {latest.name}", f"{latest.stat().st_size // 1024} KB")
        else:
            _warn("no Enhanced_Comprehensive_Analysis_*.html yet",
                  "run: python -m reports.enhanced_comprehensive_analysis both")
    else:
        _warn("reports/ directory missing")


def main() -> int:
    print(f"\n{BOLD('Agent Adda — Doctor')}  {DIM('(read-only health check)')}")
    print(f"{DIM('Project root:')} {ROOT}\n")

    check_python()
    check_pip_packages()
    check_system_bins()
    check_postgres()
    check_capture_daemon()
    check_api_keys()
    check_services()
    check_assets()

    print(f"\n{BOLD('Summary')}  "
          f"{GRN(f'PASS:{PASS}')}  "
          f"{YEL(f'WARN:{WARN}')}  "
          f"{RED(f'FAIL:{FAIL}')}\n")

    if FAIL:
        print(f"  {RED('Status: needs attention')} — fix the items above, then re-run.\n")
        return 1
    if WARN:
        print(f"  {YEL('Status: ok with warnings')} — agent will run; some features disabled.\n")
        return 0
    print(f"  {GRN('Status: all green')} — agent is fully configured.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
