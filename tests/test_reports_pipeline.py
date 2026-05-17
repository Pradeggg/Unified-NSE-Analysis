"""Comprehensive test suite for the /reports pipeline.

PG-report-tests: Validates the full enhanced_comprehensive_analysis flow:
  - CLI subcommands (run / html / both / --run-id)
  - DB invariants (FKs, expected row counts, no orphan rows)
  - HTML structure (key sections, no template placeholders)
  - Idempotency (every invocation creates a new run_id)
  - Error paths (bogus --run-id)
  - Slash-command dispatch (simulates the agent's argv parsing)

Run:  .venv/bin/python -m tests.test_reports_pipeline
"""
from __future__ import annotations

import io
import re
import shlex
import sys
import time
from contextlib import redirect_stdout
from pathlib import Path

import psycopg2
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from reports.enhanced_comprehensive_analysis import (
    PG_DSN, REPORTS_DIR, compute_and_persist_run, main as rpt_main, render_html,
)

PASS = "\033[32m✓\033[0m"
FAIL = "\033[31m✗\033[0m"
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    results.append((name, ok, detail))
    print(f"  {PASS if ok else FAIL} {name}{(' — ' + detail) if detail else ''}")
    return ok


def section(title: str) -> None:
    print(f"\n\033[36m── {title} ──\033[0m")


def pg():
    return psycopg2.connect(PG_DSN)


@pytest.fixture(scope="module")
def run_id() -> int:
    return _cli_run()


@pytest.fixture(scope="module")
def html_path() -> Path:
    return _cli_html_latest()


# ─────────────────────────────────────────────────────────────────────────────
def _cli_run() -> int:
    section("Test 1: CLI 'run' subcommand persists a new run")
    buf = io.StringIO()
    with redirect_stdout(buf):
        rpt_main(["run"])
    out = buf.getvalue()
    m = re.search(r"run_id\s*=\s*(\d+)", out)
    check("stdout reports a run_id", m is not None, out.strip().splitlines()[-1] if out else "no output")
    run_id = int(m.group(1)) if m else -1

    with pg() as c, c.cursor() as cur:
        cur.execute("SELECT 1 FROM report.enhanced_runs WHERE run_id=%s", (run_id,))
        check("row present in report.enhanced_runs", cur.fetchone() is not None, f"run_id={run_id}")
    return run_id


def test_cli_run() -> None:
    assert _cli_run() > 0


def _cli_html_latest() -> Path:
    section("Test 2: CLI 'html' renders the latest run")
    before = set(REPORTS_DIR.glob("Enhanced_Comprehensive_Analysis_*.html"))
    time.sleep(1.1)  # ensure distinct timestamp
    rpt_main(["html"])
    after = set(REPORTS_DIR.glob("Enhanced_Comprehensive_Analysis_*.html"))
    new = sorted(after - before, key=lambda p: p.stat().st_mtime)
    check("a new HTML file was written", bool(new), f"new={[p.name for p in new]}")
    return new[-1] if new else Path("/dev/null")


def test_cli_html_latest() -> None:
    assert _cli_html_latest().exists()


def test_cli_html_explicit(run_id: int) -> None:
    section("Test 3: CLI 'html --run-id' renders a specific run")
    time.sleep(1.1)
    before = set(REPORTS_DIR.glob("Enhanced_Comprehensive_Analysis_*.html"))
    rpt_main(["html", "--run-id", str(run_id)])
    after = set(REPORTS_DIR.glob("Enhanced_Comprehensive_Analysis_*.html"))
    new = sorted(after - before, key=lambda p: p.stat().st_mtime)
    if not new:
        return check("explicit run-id HTML written", False, "no new file") and None
    body = new[-1].read_text(encoding="utf-8")
    check("explicit run-id HTML written",        True,  new[-1].name)
    check("HTML contains the requested run_id",  f"Run #{run_id}" in body, f"looking for 'Run #{run_id}'")


def test_db_integrity() -> None:
    section("Test 4: DB integrity (FKs / counts / no orphans)")
    with pg() as c, c.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM report.enhanced_runs")
        n_runs = cur.fetchone()[0]
        check("at least one run exists", n_runs >= 1, f"n_runs={n_runs}")

        cur.execute("""SELECT run_id, stocks_filtered, indices_analyzed
                       FROM report.enhanced_runs ORDER BY run_id DESC LIMIT 1""")
        run_id, expected_stocks, expected_idx = cur.fetchone()

        cur.execute("SELECT COUNT(*) FROM report.enhanced_filtered_stocks WHERE run_id=%s", (run_id,))
        n_stocks = cur.fetchone()[0]
        check("filtered_stocks count matches header",
              n_stocks == expected_stocks,
              f"header={expected_stocks} actual={n_stocks}")

        cur.execute("SELECT COUNT(*) FROM report.enhanced_indices WHERE run_id=%s", (run_id,))
        n_idx = cur.fetchone()[0]
        check("indices count matches header",
              n_idx == expected_idx,
              f"header={expected_idx} actual={n_idx}")

        cur.execute("""SELECT COUNT(*) FROM report.enhanced_filtered_stocks fs
                       LEFT JOIN report.enhanced_runs r USING (run_id)
                       WHERE r.run_id IS NULL""")
        check("no orphan filtered_stocks rows", cur.fetchone()[0] == 0)

        cur.execute("""SELECT COUNT(*) FROM report.enhanced_indices i
                       LEFT JOIN report.enhanced_runs r USING (run_id)
                       WHERE r.run_id IS NULL""")
        check("no orphan indices rows", cur.fetchone()[0] == 0)

        cur.execute("""SELECT COUNT(*) FROM report.enhanced_filtered_stocks
                       WHERE run_id=%s AND (current_price IS NULL OR symbol IS NULL)""",
                    (run_id,))
        check("no NULL prices/symbols in filtered_stocks", cur.fetchone()[0] == 0)

        cur.execute("SELECT * FROM report.v_latest_run")
        check("v_latest_run view returns one row", cur.fetchone() is not None)


def test_html_structure(html_path: Path) -> None:
    section("Test 5: HTML structure")
    if not html_path.exists():
        check("HTML file exists", False, str(html_path))
        return
    body = html_path.read_text(encoding="utf-8")
    checks = {
        "has <title>":                  "<title>" in body,
        "has Major indices section":    "Major indices" in body,
        "has top ranked stocks section": "ranked stocks" in body,
        "has Sentiment KPI":            "Sentiment" in body,
        "has Agent Adda branding":      "Agent Adda" in body,
        "has full legal disclaimer":    "Full Disclaimer" in body,
        "has logo data URI":            "data:image/jpeg;base64" in body,
        "no unfilled placeholders":     "{run_id}" not in body and "{sentiment}" not in body,
        "non-trivial size (>5 KB)":     len(body) > 5_000,
    }
    for k, v in checks.items():
        check(k, v, f"{len(body)} bytes" if k.startswith("non-trivial") else "")


def test_idempotency() -> None:
    section("Test 6: Idempotency — back-to-back runs produce distinct run_ids")
    with pg() as c, c.cursor() as cur:
        cur.execute("SELECT MAX(run_id) FROM report.enhanced_runs")
        before = cur.fetchone()[0] or 0
    rid_a = compute_and_persist_run()
    rid_b = compute_and_persist_run()
    check("two new run_ids created", rid_a > before and rid_b > rid_a, f"{before} → {rid_a} → {rid_b}")


def test_slash_command_dispatch() -> None:
    section("Test 7: /reports slash-command dispatch (simulated)")
    # Mirror the agent's argv parsing exactly:
    text = "/reports run"
    argv = shlex.split(text[len("/reports"):].strip()) or ["both"]
    check("argv parsed as ['run']", argv == ["run"], f"argv={argv}")

    text = "/reports html --run-id 1"
    argv = shlex.split(text[len("/reports"):].strip()) or ["both"]
    check("argv parsed for explicit run-id", argv == ["html", "--run-id", "1"], f"argv={argv}")

    # Default (empty args) → ['both']
    text = "/reports"
    argv = shlex.split(text[len("/reports"):].strip()) or ["both"]
    check("empty args default to ['both']", argv == ["both"], f"argv={argv}")


def test_error_path_bogus_run_id() -> None:
    section("Test 8: Error path — bogus --run-id raises SystemExit")
    raised = False
    try:
        render_html(run_id=999_999_999)
    except SystemExit:
        raised = True
    except Exception as e:
        check("bogus run-id raises a clean error", False, f"got {type(e).__name__}: {e}")
        return
    check("bogus run-id raises SystemExit", raised)


# ─────────────────────────────────────────────────────────────────────────────
def main() -> int:
    print(f"\033[1mEnhanced Comprehensive Analysis — Test Suite\033[0m")
    print(f"DSN: {PG_DSN}")
    print(f"Reports dir: {REPORTS_DIR}")

    run_id = _cli_run()
    html   = _cli_html_latest()
    test_cli_html_explicit(run_id)
    test_db_integrity()
    test_html_structure(html)
    test_idempotency()
    test_slash_command_dispatch()
    test_error_path_bogus_run_id()

    section("Summary")
    n_pass = sum(1 for _, ok, _ in results if ok)
    n_fail = sum(1 for _, ok, _ in results if not ok)
    print(f"  PASS: {n_pass}    FAIL: {n_fail}")
    if n_fail:
        print("\nFailures:")
        for n, ok, d in results:
            if not ok:
                print(f"  {FAIL} {n} — {d}")
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
