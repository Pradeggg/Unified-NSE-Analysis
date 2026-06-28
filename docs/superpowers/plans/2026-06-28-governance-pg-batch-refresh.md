# Governance PostgreSQL Batch Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist governance engine outputs and section-by-section annual-report reviews in PostgreSQL, run change-aware batch refreshes for top picks and NIFTY 500 symbols, and expose stored governance context to reports.

**Architecture:** Add an idempotent `governance` PostgreSQL schema, a pure storage layer under `terminal/governance/storage.py`, and orchestration under `terminal/governance/batch.py`. A CLI script runs explicit-symbol, top-picks, or index batches with bounded worker threads; reports read `governance.latest_company_reviews` and never call live NSE or LLM paths during rendering.

**Tech Stack:** Python 3.10+ stdlib, `psycopg2`, `psycopg2.extras.Json`, existing `terminal.governance.engine.evaluate_governance`, existing `GovernanceReport.to_dict()`, PostgreSQL JSONB, pytest with fake connections/repositories.

---

## Scope Check

This plan implements the approved design in `docs/superpowers/specs/2026-06-27-governance-pg-batch-refresh-design.md`. It includes schema, storage, batch refresh, top-picks report read integration, and an optional daily-refresh hook. It deliberately does not run a full NIFTY 500 live/LLM batch during tests and does not redesign reports.

## File Structure

- Create `postgres/migrations/20260627_governance_reviews.sql`
  - Idempotent schema, tables, indexes, and latest view.

- Create `terminal/governance/storage.py`
  - DSN helper, schema init, stable source hashing, row extraction from `GovernanceReport`, DB upsert helpers, latest context reader.

- Create `terminal/governance/batch.py`
  - Symbol resolution, refresh-decision logic, threaded batch orchestration, run summary dataclasses.

- Create `scripts/backfill_governance_reviews.py`
  - CLI wrapper around `terminal.governance.batch.run_governance_batch()`.

- Modify `daily_refresh.py`
  - Add optional `--governance-top-picks` step that invokes the new script for top picks only.

- Modify `top_picks_report.py`
  - Add a compact governance context reader and render one governance risk line per stock when stored PG rows exist.

- Create tests:
  - `tests/test_governance_pg_migration.py`
  - `tests/test_governance_storage.py`
  - `tests/test_governance_batch.py`
  - Extend `tests/test_terminal_reports.py` or create focused `tests/test_top_picks_governance_context.py`
  - Extend `tests/test_refresh_failure_handling.py` or create focused `tests/test_daily_refresh_governance.py`

## Task 1: PostgreSQL Migration

**Files:**
- Create: `postgres/migrations/20260627_governance_reviews.sql`
- Create: `tests/test_governance_pg_migration.py`

- [ ] **Step 1: Write the failing migration tests**

Create `tests/test_governance_pg_migration.py`:

```python
from pathlib import Path


MIGRATION = Path("postgres/migrations/20260627_governance_reviews.sql")


def test_governance_review_migration_exists_and_is_idempotent():
    sql = MIGRATION.read_text(encoding="utf-8")

    assert "CREATE SCHEMA IF NOT EXISTS governance" in sql
    assert "CREATE TABLE IF NOT EXISTS governance.review_runs" in sql
    assert "CREATE TABLE IF NOT EXISTS governance.company_reviews" in sql
    assert "CREATE TABLE IF NOT EXISTS governance.company_review_sections" in sql
    assert "CREATE OR REPLACE VIEW governance.latest_company_reviews" in sql
    assert "CREATE INDEX IF NOT EXISTS" in sql
    assert "CREATE UNIQUE INDEX IF NOT EXISTS" in sql

    assert "CREATE SCHEMA governance" not in sql
    assert "CREATE TABLE governance.review_runs" not in sql
    assert "CREATE INDEX governance_" not in sql


def test_governance_review_migration_defines_report_facing_columns():
    sql = MIGRATION.read_text(encoding="utf-8")

    required_columns = [
        "source_hash TEXT NOT NULL",
        "annual_report_hash TEXT",
        "annual_report_selected_pages INTEGER[]",
        "engine_score NUMERIC(6,2)",
        "engine_rating TEXT",
        "annual_review_label TEXT",
        "audit_opinion TEXT",
        "section_counts JSONB",
        "full_payload JSONB NOT NULL",
    ]
    for column in required_columns:
        assert column in sql


def test_governance_latest_view_filters_successful_rows():
    sql = MIGRATION.read_text(encoding="utf-8")

    assert "ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY created_at DESC, review_id DESC)" in sql
    assert "WHERE status = 'ok'" in sql
    assert "WHERE rn = 1" in sql
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
./.venv/bin/python -m pytest -q tests/test_governance_pg_migration.py
```

Expected: failure because `postgres/migrations/20260627_governance_reviews.sql` does not exist.

- [ ] **Step 3: Add the migration**

Create `postgres/migrations/20260627_governance_reviews.sql`:

```sql
CREATE SCHEMA IF NOT EXISTS governance;

CREATE TABLE IF NOT EXISTS governance.review_runs (
    run_id TEXT PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    mode TEXT NOT NULL,
    universe TEXT,
    requested_symbols TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    worker_count INTEGER NOT NULL DEFAULT 1,
    refresh_policy TEXT NOT NULL DEFAULT 'hybrid',
    status TEXT NOT NULL DEFAULT 'running',
    attempted INTEGER NOT NULL DEFAULT 0,
    succeeded INTEGER NOT NULL DEFAULT 0,
    failed INTEGER NOT NULL DEFAULT 0,
    skipped_fresh INTEGER NOT NULL DEFAULT 0,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS governance.company_reviews (
    review_id TEXT PRIMARY KEY,
    run_id TEXT REFERENCES governance.review_runs(run_id) ON DELETE SET NULL,
    symbol TEXT NOT NULL,
    as_of DATE NOT NULL,
    source_hash TEXT NOT NULL,
    annual_report_hash TEXT,
    annual_report_selected_pages INTEGER[],
    engine_score NUMERIC(6,2),
    engine_rating TEXT,
    engine_confidence TEXT,
    annual_review_status TEXT,
    annual_review_label TEXT,
    audit_opinion TEXT,
    auditor TEXT,
    section_counts JSONB NOT NULL DEFAULT '{}'::jsonb,
    key_findings_count INTEGER NOT NULL DEFAULT 0,
    parser_mismatches_count INTEGER NOT NULL DEFAULT 0,
    human_review_count INTEGER NOT NULL DEFAULT 0,
    flags JSONB NOT NULL DEFAULT '[]'::jsonb,
    missing_evidence JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_trail JSONB NOT NULL DEFAULT '[]'::jsonb,
    full_payload JSONB NOT NULL,
    status TEXT NOT NULL,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS governance.company_review_sections (
    review_id TEXT NOT NULL REFERENCES governance.company_reviews(review_id) ON DELETE CASCADE,
    symbol TEXT NOT NULL,
    section_id TEXT NOT NULL,
    risk_label TEXT,
    status TEXT,
    summary TEXT,
    findings JSONB NOT NULL DEFAULT '[]'::jsonb,
    red_flags JSONB NOT NULL DEFAULT '[]'::jsonb,
    page_evidence JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (review_id, section_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS governance_company_reviews_symbol_source_hash_uidx
    ON governance.company_reviews(symbol, source_hash);

CREATE INDEX IF NOT EXISTS governance_company_reviews_symbol_created_idx
    ON governance.company_reviews(symbol, created_at DESC);

CREATE INDEX IF NOT EXISTS governance_company_reviews_label_created_idx
    ON governance.company_reviews(annual_review_label, created_at DESC);

CREATE INDEX IF NOT EXISTS governance_company_reviews_engine_rating_created_idx
    ON governance.company_reviews(engine_rating, created_at DESC);

CREATE INDEX IF NOT EXISTS governance_company_review_sections_symbol_section_created_idx
    ON governance.company_review_sections(symbol, section_id, created_at DESC);

CREATE INDEX IF NOT EXISTS governance_company_review_sections_risk_created_idx
    ON governance.company_review_sections(risk_label, created_at DESC);

CREATE OR REPLACE VIEW governance.latest_company_reviews AS
WITH ranked AS (
    SELECT
        company_reviews.*,
        ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY created_at DESC, review_id DESC) AS rn
    FROM governance.company_reviews
    WHERE status = 'ok'
)
SELECT *
FROM ranked
WHERE rn = 1;
```

- [ ] **Step 4: Run migration tests**

Run:

```bash
./.venv/bin/python -m pytest -q tests/test_governance_pg_migration.py
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add postgres/migrations/20260627_governance_reviews.sql tests/test_governance_pg_migration.py
git commit -m "feat: add governance review postgres schema"
```

## Task 2: Storage Pure Helpers

**Files:**
- Create: `terminal/governance/storage.py`
- Create: `tests/test_governance_storage.py`

- [ ] **Step 1: Write failing tests for hashes and row extraction**

Create `tests/test_governance_storage.py`:

```python
from datetime import date

from terminal.governance.models import ComponentScore, GovernanceEvidence, GovernanceReport
from terminal.governance.storage import (
    GOVERNANCE_REVIEW_SCHEMA_VERSION,
    build_review_records,
    compute_source_hash,
    section_risk_counts,
)


def _report(review=None):
    return GovernanceReport(
        symbol="INFY",
        as_of=date(2026, 6, 28),
        score=82.0,
        rating="WATCH",
        confidence="High",
        component_scores=[ComponentScore("audit_quality", 14, 20, "amber", ["watch"], ["annual_report"])],
        flags=["Audit watch"],
        evidence=GovernanceEvidence(symbol="INFY", as_of=date(2026, 6, 28)),
        source_trail=[],
        missing_evidence=[],
        llm_status="not_requested",
        annual_report_review_status="ok" if review else "not_requested",
        annual_report_review=review,
    )


def test_compute_source_hash_is_stable_and_ignores_key_order():
    left = {"symbol": "INFY", "annual_report_text": "abc", "source_trail": [{"name": "nse", "rows": 1}]}
    right = {"source_trail": [{"rows": 1, "name": "nse"}], "annual_report_text": "abc", "symbol": "INFY"}

    assert compute_source_hash(left) == compute_source_hash(right)


def test_compute_source_hash_changes_when_schema_version_changes():
    payload = {"symbol": "INFY", "annual_report_text": "abc"}

    base = compute_source_hash(payload, schema_version="v1")
    changed = compute_source_hash(payload, schema_version="v2")

    assert base != changed
    assert GOVERNANCE_REVIEW_SCHEMA_VERSION


def test_section_risk_counts_normalizes_known_labels():
    sections = [
        {"section_id": "auditor_opinion", "risk_label": "Clean"},
        {"section_id": "key_audit_matters", "risk_label": "Watch"},
        {"section_id": "related_party", "risk_label": "Concern"},
        {"section_id": "caro_and_fraud", "risk_label": "High Risk"},
        {"section_id": "corporate_governance", "risk_label": "Red Flag"},
        {"section_id": "internal_financial_controls", "risk_label": "Insufficient Evidence"},
    ]

    assert section_risk_counts(sections) == {
        "clean": 1,
        "watch": 1,
        "concern": 1,
        "high_risk": 1,
        "red_flag": 1,
        "insufficient_evidence": 1,
        "unknown": 0,
    }


def test_build_review_records_extracts_normalized_columns_and_sections():
    review = {
        "review_label": "Watch",
        "audit_opinion": "Clean",
        "auditor": "S R B C & CO LLP",
        "key_findings": ["clean opinion"],
        "parser_mismatches": ["missing CARO"],
        "human_review_checklist": ["review CARO"],
        "page_evidence": [{"page": 10, "finding": "audit opinion"}],
        "section_reviews": [
            {
                "section_id": "auditor_opinion",
                "risk_label": "Clean",
                "status": "ok",
                "summary": "Clean opinion.",
                "findings": ["true and fair"],
                "red_flags": [],
                "page_evidence": [{"page": 10}],
            }
        ],
    }

    row, sections = build_review_records(
        run_id="run_1",
        review_id="review_1",
        source_hash="hash_1",
        annual_report_hash="ar_hash",
        annual_report_selected_pages=[10, 11],
        report=_report(review),
    )

    assert row["symbol"] == "INFY"
    assert row["engine_score"] == 82.0
    assert row["engine_rating"] == "WATCH"
    assert row["annual_review_label"] == "Watch"
    assert row["audit_opinion"] == "Clean"
    assert row["auditor"] == "S R B C & CO LLP"
    assert row["key_findings_count"] == 1
    assert row["parser_mismatches_count"] == 1
    assert row["human_review_count"] == 1
    assert row["section_counts"]["clean"] == 1
    assert row["annual_report_selected_pages"] == [10, 11]
    assert row["full_payload"]["annual_report_review"]["review_label"] == "Watch"
    assert sections[0]["section_id"] == "auditor_opinion"
    assert sections[0]["risk_label"] == "Clean"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
./.venv/bin/python -m pytest -q tests/test_governance_storage.py
```

Expected: import failure because `terminal.governance.storage` does not exist.

- [ ] **Step 3: Implement pure storage helpers**

Create `terminal/governance/storage.py` with:

```python
from __future__ import annotations

import hashlib
import json
import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from terminal.governance.models import GovernanceReport

ROOT = Path(__file__).resolve().parents[2]
MIGRATION_PATH = ROOT / "postgres" / "migrations" / "20260627_governance_reviews.sql"
DEFAULT_DSN = os.environ.get("AGENT_ADDA_PG_DSN") or os.environ.get("PG_DSN") or "dbname=nse_market user=nse_admin host=/tmp"
GOVERNANCE_REVIEW_SCHEMA_VERSION = "governance-review-v1"


def _json_default(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=_json_default)


def compute_source_hash(payload: dict[str, Any], *, schema_version: str = GOVERNANCE_REVIEW_SCHEMA_VERSION) -> str:
    body = {"schema_version": schema_version, "payload": payload}
    return hashlib.sha256(stable_json(body).encode("utf-8")).hexdigest()


def compute_text_hash(text: str | None) -> str | None:
    if not text:
        return None
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def section_risk_counts(sections: list[dict[str, Any]]) -> dict[str, int]:
    counts = {
        "clean": 0,
        "watch": 0,
        "concern": 0,
        "high_risk": 0,
        "red_flag": 0,
        "insufficient_evidence": 0,
        "unknown": 0,
    }
    mapping = {
        "clean": "clean",
        "watch": "watch",
        "concern": "concern",
        "high risk": "high_risk",
        "red flag": "red_flag",
        "insufficient evidence": "insufficient_evidence",
    }
    for section in sections:
        label = str(section.get("risk_label") or "").strip().lower()
        counts[mapping.get(label, "unknown")] += 1
    return counts


def _selected_pages_from_review(review: dict[str, Any]) -> list[int]:
    pages: list[int] = []
    for item in review.get("page_evidence") or []:
        raw = item.get("page") if isinstance(item, dict) else None
        try:
            page = int(raw)
        except (TypeError, ValueError):
            continue
        if page not in pages:
            pages.append(page)
    return pages


def build_review_records(
    *,
    run_id: str,
    review_id: str,
    source_hash: str,
    annual_report_hash: str | None,
    annual_report_selected_pages: list[int] | None,
    report: GovernanceReport,
    status: str = "ok",
    error: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    payload = report.to_dict()
    review = report.annual_report_review or {}
    sections = list(review.get("section_reviews") or [])
    selected_pages = annual_report_selected_pages or _selected_pages_from_review(review)
    row = {
        "review_id": review_id,
        "run_id": run_id,
        "symbol": report.symbol,
        "as_of": report.as_of,
        "source_hash": source_hash,
        "annual_report_hash": annual_report_hash,
        "annual_report_selected_pages": selected_pages,
        "engine_score": float(report.score),
        "engine_rating": report.rating,
        "engine_confidence": report.confidence,
        "annual_review_status": report.annual_report_review_status,
        "annual_review_label": review.get("review_label"),
        "audit_opinion": review.get("audit_opinion"),
        "auditor": review.get("auditor"),
        "section_counts": section_risk_counts(sections),
        "key_findings_count": len(review.get("key_findings") or []),
        "parser_mismatches_count": len(review.get("parser_mismatches") or []),
        "human_review_count": len(review.get("human_review_checklist") or []),
        "flags": payload.get("flags") or [],
        "missing_evidence": payload.get("missing_evidence") or [],
        "source_trail": payload.get("source_trail") or [],
        "full_payload": payload,
        "status": status,
        "error": error,
    }
    section_rows = []
    for section in sections:
        section_rows.append(
            {
                "review_id": review_id,
                "symbol": report.symbol,
                "section_id": section.get("section_id"),
                "risk_label": section.get("risk_label"),
                "status": section.get("status"),
                "summary": section.get("summary"),
                "findings": section.get("findings") or [],
                "red_flags": section.get("red_flags") or [],
                "page_evidence": section.get("page_evidence") or [],
            }
        )
    return row, section_rows
```

- [ ] **Step 4: Run storage helper tests**

Run:

```bash
./.venv/bin/python -m pytest -q tests/test_governance_storage.py
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add terminal/governance/storage.py tests/test_governance_storage.py
git commit -m "feat: add governance review storage helpers"
```

## Task 3: Storage Repository Upserts And Reads

**Files:**
- Modify: `terminal/governance/storage.py`
- Modify: `tests/test_governance_storage.py`

- [ ] **Step 1: Add failing fake-connection repository tests**

Append to `tests/test_governance_storage.py`:

```python
from terminal.governance.storage import GovernanceReviewStore


class FakeCursor:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.executed = []
        self.fetchone_calls = 0

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchone(self):
        if self.fetchone_calls < len(self.rows):
            row = self.rows[self.fetchone_calls]
            self.fetchone_calls += 1
            return row
        return None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeConn:
    def __init__(self, rows=None):
        self.cursor_obj = FakeCursor(rows)
        self.commits = 0
        self.rollbacks = 0

    def cursor(self, *args, **kwargs):
        return self.cursor_obj

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def test_store_creates_run_and_marks_completion():
    conn = FakeConn()
    store = GovernanceReviewStore(conn=conn)

    store.start_run(
        run_id="run_1",
        mode="top_picks",
        universe="top_picks",
        requested_symbols=["INFY", "TCS"],
        worker_count=2,
        refresh_policy="hybrid",
    )
    store.finish_run(run_id="run_1", status="ok", attempted=2, succeeded=1, failed=0, skipped_fresh=1)

    sql_text = "\n".join(sql for sql, _ in conn.cursor_obj.executed)
    assert "INSERT INTO governance.review_runs" in sql_text
    assert "UPDATE governance.review_runs" in sql_text
    assert conn.commits == 2


def test_store_upserts_review_and_sections():
    conn = FakeConn()
    store = GovernanceReviewStore(conn=conn)
    review = {
        "review_label": "Watch",
        "audit_opinion": "Clean",
        "section_reviews": [{"section_id": "auditor_opinion", "risk_label": "Clean"}],
    }
    row, sections = build_review_records(
        run_id="run_1",
        review_id="review_1",
        source_hash="hash_1",
        annual_report_hash=None,
        annual_report_selected_pages=[],
        report=_report(review),
    )

    store.upsert_review(row, sections)

    sql_text = "\n".join(sql for sql, _ in conn.cursor_obj.executed)
    assert "INSERT INTO governance.company_reviews" in sql_text
    assert "ON CONFLICT (symbol, source_hash) DO UPDATE SET" in sql_text
    assert "INSERT INTO governance.company_review_sections" in sql_text
    assert conn.commits == 1


def test_store_fetches_latest_review_metadata():
    conn = FakeConn(rows=[("hash_1", "ok", date(2026, 6, 28))])
    store = GovernanceReviewStore(conn=conn)

    latest = store.latest_review_meta("INFY")

    assert latest == {"source_hash": "hash_1", "status": "ok", "created_at": date(2026, 6, 28)}
    assert "FROM governance.company_reviews" in conn.cursor_obj.executed[0][0]
```

- [ ] **Step 2: Run targeted tests to verify they fail**

Run:

```bash
./.venv/bin/python -m pytest -q tests/test_governance_storage.py
```

Expected: failures because `GovernanceReviewStore` does not exist.

- [ ] **Step 3: Implement repository methods**

Extend `terminal/governance/storage.py`:

```python
def connect(dsn: str | None = None):
    import psycopg2

    return psycopg2.connect(dsn or DEFAULT_DSN)


class GovernanceReviewStore:
    def __init__(self, *, conn: Any | None = None, dsn: str | None = None):
        self.conn = conn or connect(dsn)
        self._owns_conn = conn is None

    def close(self) -> None:
        if self._owns_conn:
            self.conn.close()

    def init_schema(self) -> None:
        with self.conn.cursor() as cur:
            cur.execute(MIGRATION_PATH.read_text(encoding="utf-8"))
        self.conn.commit()

    def start_run(
        self,
        *,
        run_id: str,
        mode: str,
        universe: str | None,
        requested_symbols: list[str],
        worker_count: int,
        refresh_policy: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        from psycopg2.extras import Json

        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO governance.review_runs
                    (run_id, mode, universe, requested_symbols, worker_count, refresh_policy, status, metadata)
                VALUES (%s, %s, %s, %s, %s, %s, 'running', %s)
                ON CONFLICT (run_id) DO UPDATE SET
                    mode = EXCLUDED.mode,
                    universe = EXCLUDED.universe,
                    requested_symbols = EXCLUDED.requested_symbols,
                    worker_count = EXCLUDED.worker_count,
                    refresh_policy = EXCLUDED.refresh_policy,
                    status = 'running',
                    metadata = EXCLUDED.metadata
                """,
                (run_id, mode, universe, requested_symbols, worker_count, refresh_policy, Json(metadata or {})),
            )
        self.conn.commit()

    def finish_run(self, *, run_id: str, status: str, attempted: int, succeeded: int, failed: int, skipped_fresh: int) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE governance.review_runs
                SET completed_at = NOW(),
                    status = %s,
                    attempted = %s,
                    succeeded = %s,
                    failed = %s,
                    skipped_fresh = %s
                WHERE run_id = %s
                """,
                (status, attempted, succeeded, failed, skipped_fresh, run_id),
            )
        self.conn.commit()

    def latest_review_meta(self, symbol: str) -> dict[str, Any] | None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT source_hash, status, created_at
                FROM governance.company_reviews
                WHERE symbol = %s
                ORDER BY created_at DESC, review_id DESC
                LIMIT 1
                """,
                (symbol.upper(),),
            )
            row = cur.fetchone()
        if not row:
            return None
        return {"source_hash": row[0], "status": row[1], "created_at": row[2]}
```

Also implement `upsert_review()`. Use `Json(...)` for JSONB fields and delete/reinsert sections for the chosen `review_id`:

```python
    def upsert_review(self, row: dict[str, Any], section_rows: list[dict[str, Any]]) -> None:
        from psycopg2.extras import Json, execute_values

        json_fields = {"section_counts", "flags", "missing_evidence", "source_trail", "full_payload"}
        values = dict(row)
        for field in json_fields:
            values[field] = Json(values.get(field))
        cols = list(values)
        assignments = ", ".join(
            f"{col} = EXCLUDED.{col}"
            for col in cols
            if col not in {"review_id", "symbol", "source_hash"}
        )
        with self.conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO governance.company_reviews ({", ".join(cols)})
                VALUES ({", ".join(["%s"] * len(cols))})
                ON CONFLICT (symbol, source_hash) DO UPDATE SET {assignments}
                """,
                tuple(values[col] for col in cols),
            )
            cur.execute("DELETE FROM governance.company_review_sections WHERE review_id = %s", (row["review_id"],))
            if section_rows:
                section_cols = list(section_rows[0])
                section_values = []
                for item in section_rows:
                    section_values.append(
                        [
                            Json(item[col]) if col in {"findings", "red_flags", "page_evidence"} else item[col]
                            for col in section_cols
                        ]
                    )
                execute_values(
                    cur,
                    f"""
                    INSERT INTO governance.company_review_sections ({", ".join(section_cols)})
                    VALUES %s
                    ON CONFLICT (review_id, section_id) DO UPDATE SET
                        risk_label = EXCLUDED.risk_label,
                        status = EXCLUDED.status,
                        summary = EXCLUDED.summary,
                        findings = EXCLUDED.findings,
                        red_flags = EXCLUDED.red_flags,
                        page_evidence = EXCLUDED.page_evidence
                    """,
                    section_values,
                )
        self.conn.commit()
```

- [ ] **Step 4: Run storage tests**

Run:

```bash
./.venv/bin/python -m pytest -q tests/test_governance_storage.py
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add terminal/governance/storage.py tests/test_governance_storage.py
git commit -m "feat: persist governance reviews to postgres"
```

## Task 4: Batch Symbol Resolution And Refresh Decisions

**Files:**
- Create: `terminal/governance/batch.py`
- Create: `tests/test_governance_batch.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_governance_batch.py`:

```python
from datetime import datetime, timedelta, timezone
from pathlib import Path

from terminal.governance.batch import (
    RefreshDecision,
    resolve_symbols_from_top_picks,
    should_refresh_symbol,
)


def test_resolve_symbols_from_top_picks_lines_file(tmp_path):
    latest = tmp_path / "reports" / "latest"
    latest.mkdir(parents=True)
    (latest / "top_picks_tradingview_lines.txt").write_text("NSE:POLYCAB\nNSE:INFY\nNSE:POLYCAB\n", encoding="utf-8")

    assert resolve_symbols_from_top_picks(base_dir=tmp_path) == ["POLYCAB", "INFY"]


def test_resolve_symbols_from_top_picks_markdown_fallback(tmp_path):
    latest = tmp_path / "reports" / "latest"
    latest.mkdir(parents=True)
    (latest / "top_picks.md").write_text(
        "| # | Symbol |\n|---|---|\n| 1 | **POLYCAB** |\n| 2 | **PARAS** |\n",
        encoding="utf-8",
    )

    assert resolve_symbols_from_top_picks(base_dir=tmp_path) == ["POLYCAB", "PARAS"]


def test_should_refresh_new_changed_failed_stale_and_forced_symbols():
    now = datetime(2026, 6, 28, tzinfo=timezone.utc)
    fresh = now - timedelta(days=1)
    stale = now - timedelta(days=31)

    assert should_refresh_symbol(None, source_hash="h1", now=now).reason == "missing"
    assert should_refresh_symbol({"source_hash": "old", "status": "ok", "created_at": fresh}, source_hash="new", now=now).reason == "changed"
    assert should_refresh_symbol({"source_hash": "h1", "status": "error", "created_at": fresh}, source_hash="h1", now=now).reason == "previous_error"
    assert should_refresh_symbol({"source_hash": "h1", "status": "ok", "created_at": stale}, source_hash="h1", now=now, stale_days=30).reason == "stale"
    assert should_refresh_symbol({"source_hash": "h1", "status": "ok", "created_at": fresh}, source_hash="h1", now=now, force=True).reason == "forced"


def test_should_skip_unchanged_fresh_symbol():
    now = datetime(2026, 6, 28, tzinfo=timezone.utc)
    fresh = now - timedelta(days=1)

    decision = should_refresh_symbol({"source_hash": "h1", "status": "ok", "created_at": fresh}, source_hash="h1", now=now)

    assert decision == RefreshDecision(refresh=False, reason="fresh")
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
./.venv/bin/python -m pytest -q tests/test_governance_batch.py
```

Expected: import failure because `terminal.governance.batch` does not exist.

- [ ] **Step 3: Implement batch pure helpers**

Create `terminal/governance/batch.py`:

```python
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class RefreshDecision:
    refresh: bool
    reason: str


def _normalize_symbol(value: str) -> str:
    cleaned = str(value or "").strip().upper()
    cleaned = cleaned.removeprefix("NSE:")
    return re.sub(r"[^A-Z0-9&-]", "", cleaned)


def _dedupe(symbols: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in symbols:
        sym = _normalize_symbol(item)
        if sym and sym not in seen:
            seen.add(sym)
            out.append(sym)
    return out


def resolve_symbols_from_top_picks(*, base_dir: Path = ROOT) -> list[str]:
    lines_path = base_dir / "reports" / "latest" / "top_picks_tradingview_lines.txt"
    if lines_path.exists():
        return _dedupe(lines_path.read_text(encoding="utf-8").splitlines())

    md_path = base_dir / "reports" / "latest" / "top_picks.md"
    if not md_path.exists():
        return []
    symbols: list[str] = []
    for line in md_path.read_text(encoding="utf-8").splitlines():
        match = re.search(r"\|\s*\d+\s*\|\s*\*\*([A-Z0-9&-]+)\*\*", line)
        if match:
            symbols.append(match.group(1))
    return _dedupe(symbols)


def _coerce_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def should_refresh_symbol(
    latest: dict[str, Any] | None,
    *,
    source_hash: str,
    now: datetime | None = None,
    stale_days: int = 30,
    force: bool = False,
) -> RefreshDecision:
    if force:
        return RefreshDecision(True, "forced")
    if not latest:
        return RefreshDecision(True, "missing")
    if latest.get("source_hash") != source_hash:
        return RefreshDecision(True, "changed")
    if latest.get("status") == "error":
        return RefreshDecision(True, "previous_error")
    created_at = _coerce_datetime(latest.get("created_at"))
    if created_at is None:
        return RefreshDecision(True, "unknown_age")
    current = now or datetime.now(timezone.utc)
    if (current - created_at).days >= stale_days:
        return RefreshDecision(True, "stale")
    return RefreshDecision(False, "fresh")
```

- [ ] **Step 4: Run batch helper tests**

Run:

```bash
./.venv/bin/python -m pytest -q tests/test_governance_batch.py
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add terminal/governance/batch.py tests/test_governance_batch.py
git commit -m "feat: add governance batch refresh decisions"
```

## Task 5: Batch Orchestration And CLI Script

**Files:**
- Modify: `terminal/governance/batch.py`
- Create: `scripts/backfill_governance_reviews.py`
- Modify: `tests/test_governance_batch.py`

- [ ] **Step 1: Add failing orchestration tests**

Append to `tests/test_governance_batch.py`:

```python
from datetime import date

from terminal.governance.batch import run_governance_batch
from terminal.governance.models import GovernanceEvidence, GovernanceReport


class FakeStore:
    def __init__(self, latest=None):
        self.latest = latest or {}
        self.started = None
        self.finished = None
        self.upserts = []

    def start_run(self, **kwargs):
        self.started = kwargs

    def finish_run(self, **kwargs):
        self.finished = kwargs

    def latest_review_meta(self, symbol):
        return self.latest.get(symbol)

    def upsert_review(self, row, sections):
        self.upserts.append((row, sections))

    def close(self):
        pass


def _batch_report(symbol):
    return GovernanceReport(
        symbol=symbol,
        as_of=date(2026, 6, 28),
        score=80,
        rating="WATCH",
        confidence="High",
        component_scores=[],
        flags=[],
        evidence=GovernanceEvidence(symbol=symbol, as_of=date(2026, 6, 28)),
        source_trail=[],
        missing_evidence=[],
        llm_status="not_requested",
        annual_report_review_status="ok",
        annual_report_review={
            "review_label": "Watch",
            "audit_opinion": "Clean",
            "section_reviews": [{"section_id": "auditor_opinion", "risk_label": "Clean"}],
        },
    )


def test_run_governance_batch_persists_refreshed_symbols_and_skips_fresh():
    store = FakeStore(
        latest={
            "TCS": {
                "source_hash": "known",
                "status": "ok",
                "created_at": datetime(2026, 6, 28, tzinfo=timezone.utc),
            }
        }
    )
    calls = []

    def evaluator(symbol, **kwargs):
        calls.append((symbol, kwargs))
        return _batch_report(symbol)

    def raw_loader(symbol):
        return {"symbol": symbol, "annual_report_text": "known" if symbol == "TCS" else symbol}

    result = run_governance_batch(
        symbols=["INFY", "TCS"],
        store=store,
        evaluator=evaluator,
        raw_loader=raw_loader,
        workers=1,
        now=datetime(2026, 6, 28, tzinfo=timezone.utc),
    )

    assert [item[0] for item in calls] == ["INFY"]
    assert result.attempted == 1
    assert result.succeeded == 1
    assert result.skipped_fresh == 1
    assert store.started["requested_symbols"] == ["INFY", "TCS"]
    assert store.finished["status"] == "ok"
    assert store.upserts[0][0]["symbol"] == "INFY"


def test_run_governance_batch_records_symbol_errors_without_stopping():
    store = FakeStore()

    def evaluator(symbol, **kwargs):
        if symbol == "BAD":
            raise RuntimeError("boom")
        return _batch_report(symbol)

    result = run_governance_batch(
        symbols=["BAD", "INFY"],
        store=store,
        evaluator=evaluator,
        raw_loader=lambda symbol: {"symbol": symbol},
        workers=1,
        now=datetime(2026, 6, 28, tzinfo=timezone.utc),
    )

    assert result.attempted == 2
    assert result.succeeded == 1
    assert result.failed == 1
    assert result.symbols["BAD"].status == "error"
    assert result.symbols["INFY"].status == "ok"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
./.venv/bin/python -m pytest -q tests/test_governance_batch.py
```

Expected: failure because `run_governance_batch` does not exist.

- [ ] **Step 3: Implement orchestration**

Extend `terminal/governance/batch.py` with dataclasses and runner:

```python
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

from terminal.governance.cache_sources import load_cached_sources
from terminal.governance.engine import evaluate_governance
from terminal.governance.storage import (
    GovernanceReviewStore,
    build_review_records,
    compute_source_hash,
    compute_text_hash,
)


@dataclass(frozen=True)
class SymbolBatchResult:
    symbol: str
    status: str
    reason: str
    review_id: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class GovernanceBatchResult:
    run_id: str
    attempted: int
    succeeded: int
    failed: int
    skipped_fresh: int
    symbols: dict[str, SymbolBatchResult]
```

Implement `run_governance_batch()`:

```python
def _raw_payload_for_hash(symbol: str, raw_loader) -> dict[str, Any]:
    raw = raw_loader(symbol)
    if hasattr(raw, "to_dict"):
        return raw.to_dict()
    return dict(raw)


def run_governance_batch(
    *,
    symbols: list[str],
    store: Any | None = None,
    evaluator=evaluate_governance,
    raw_loader=None,
    workers: int = 2,
    mode: str = "symbols",
    universe: str | None = None,
    policy: str = "hybrid",
    force: bool = False,
    refresh_live: bool = False,
    stale_days: int = 30,
    now: datetime | None = None,
) -> GovernanceBatchResult:
    selected = _dedupe(symbols)
    run_id = f"gov_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    owns_store = store is None
    db = store or GovernanceReviewStore()
    current = now or datetime.now(timezone.utc)
    raw_fn = raw_loader or (lambda symbol: load_cached_sources(symbol).to_dict())
    results: dict[str, SymbolBatchResult] = {}
    attempted = succeeded = failed = skipped = 0
    db.start_run(
        run_id=run_id,
        mode=mode,
        universe=universe,
        requested_symbols=selected,
        worker_count=max(1, workers),
        refresh_policy=policy,
        metadata={"force": force, "refresh_live": refresh_live},
    )

    def process(symbol: str) -> SymbolBatchResult:
        raw_payload = _raw_payload_for_hash(symbol, raw_fn)
        source_hash = compute_source_hash(raw_payload)
        decision = should_refresh_symbol(
            db.latest_review_meta(symbol),
            source_hash=source_hash,
            now=current,
            stale_days=stale_days,
            force=force,
        )
        if not decision.refresh:
            return SymbolBatchResult(symbol=symbol, status="skipped", reason=decision.reason)
        report = evaluator(symbol, refresh_live=refresh_live, use_annual_report_llm=True, use_llm=False)
        review_id = f"{symbol}_{source_hash[:16]}"
        row, sections = build_review_records(
            run_id=run_id,
            review_id=review_id,
            source_hash=source_hash,
            annual_report_hash=compute_text_hash(raw_payload.get("annual_report_text")),
            annual_report_selected_pages=(raw_payload.get("source_trail") or [{}])[-1].get("metadata", {}).get("selected_pages"),
            report=report,
        )
        db.upsert_review(row, sections)
        return SymbolBatchResult(symbol=symbol, status="ok", reason=decision.reason, review_id=review_id)
```

Use `ThreadPoolExecutor(max_workers=max(1, workers))`, collect results, convert exceptions into `SymbolBatchResult(status="error")`, and call `finish_run()` with `status="ok"` when `failed == 0` else `partial`.

- [ ] **Step 4: Add CLI script**

Create `scripts/backfill_governance_reviews.py`:

```python
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from terminal.governance.batch import resolve_symbols_from_top_picks, run_governance_batch


def _symbols_from_args(args) -> list[str]:
    if args.symbols:
        return [item.strip().upper() for item in args.symbols.split(",") if item.strip()]
    if args.top_picks:
        return resolve_symbols_from_top_picks(base_dir=Path.cwd())
    raise SystemExit("--symbols or --top-picks is required in this task; Task 6 adds --index support")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Persist governance annual-report reviews to PostgreSQL.")
    parser.add_argument("--symbols")
    parser.add_argument("--top-picks", action="store_true")
    parser.add_argument("--index", default="NIFTY 500")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--policy", default="hybrid")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--refresh-live", action="store_true")
    args = parser.parse_args(argv)

    symbols = _symbols_from_args(args)
    if args.limit:
        symbols = symbols[: args.limit]
    if not symbols:
        print("[governance] no symbols selected")
        return 1
    result = run_governance_batch(
        symbols=symbols,
        workers=args.workers,
        mode="top_picks" if args.top_picks else "symbols",
        universe="top_picks" if args.top_picks else args.index,
        policy=args.policy,
        force=args.force,
        refresh_live=args.refresh_live,
        stale_days=7 if args.top_picks else 30,
    )
    print(
        f"[governance] run={result.run_id} attempted={result.attempted} "
        f"succeeded={result.succeeded} failed={result.failed} skipped_fresh={result.skipped_fresh}"
    )
    for symbol, item in result.symbols.items():
        print(f"[governance] {symbol:<14} {item.status:<8} {item.reason}")
    return 0 if result.failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Run batch tests**

Run:

```bash
./.venv/bin/python -m pytest -q tests/test_governance_batch.py
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add terminal/governance/batch.py scripts/backfill_governance_reviews.py tests/test_governance_batch.py
git commit -m "feat: add governance review batch runner"
```

## Task 6: NIFTY 500 Symbol Resolution From PostgreSQL

**Files:**
- Modify: `terminal/governance/batch.py`
- Modify: `scripts/backfill_governance_reviews.py`
- Modify: `tests/test_governance_batch.py`

- [ ] **Step 1: Add failing test for index resolution**

Append to `tests/test_governance_batch.py`:

```python
from terminal.governance.batch import resolve_symbols_from_index


class IndexCursor(FakeCursor):
    def __init__(self):
        super().__init__()
        self._rows = [("INFY",), ("TCS",), ("INFY",)]

    def fetchall(self):
        return self._rows


class IndexConn(FakeConn):
    def __init__(self):
        self.cursor_obj = IndexCursor()
        self.commits = 0
        self.rollbacks = 0


def test_resolve_symbols_from_index_uses_ref_index_compositions():
    conn = IndexConn()

    symbols = resolve_symbols_from_index("NIFTY 500", conn=conn)

    assert symbols == ["INFY", "TCS"]
    assert "FROM ref.index_compositions" in conn.cursor_obj.executed[0][0]
```

- [ ] **Step 2: Run targeted test and confirm failure**

Run:

```bash
./.venv/bin/python -m pytest -q tests/test_governance_batch.py::test_resolve_symbols_from_index_uses_ref_index_compositions
```

Expected: import failure for `resolve_symbols_from_index`.

- [ ] **Step 3: Implement index resolution**

Add to `terminal/governance/batch.py`:

```python
def resolve_symbols_from_index(index_name: str = "NIFTY 500", *, conn: Any | None = None, dsn: str | None = None) -> list[str]:
    owns_conn = conn is None
    db = conn
    if db is None:
        from terminal.governance.storage import connect
        db = connect(dsn)
    try:
        with db.cursor() as cur:
            cur.execute(
                """
                SELECT symbol
                FROM ref.index_compositions
                WHERE UPPER(index_symbol) = UPPER(%s)
                ORDER BY symbol
                """,
                (index_name,),
            )
            rows = cur.fetchall()
        return _dedupe([row[0] for row in rows])
    finally:
        if owns_conn:
            db.close()
```

Update `scripts/backfill_governance_reviews.py` so `--index` is used when neither `--symbols` nor `--top-picks` is supplied:

```python
from terminal.governance.batch import resolve_symbols_from_index, resolve_symbols_from_top_picks, run_governance_batch


def _symbols_from_args(args) -> list[str]:
    if args.symbols:
        return [item.strip().upper() for item in args.symbols.split(",") if item.strip()]
    if args.top_picks:
        return resolve_symbols_from_top_picks(base_dir=Path.cwd())
    return resolve_symbols_from_index(args.index)
```

- [ ] **Step 4: Run batch tests**

Run:

```bash
./.venv/bin/python -m pytest -q tests/test_governance_batch.py
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add terminal/governance/batch.py scripts/backfill_governance_reviews.py tests/test_governance_batch.py
git commit -m "feat: resolve governance batch index universe"
```

## Task 7: Top Picks Report Reads Stored Governance Context

**Files:**
- Modify: `top_picks_report.py`
- Create: `tests/test_top_picks_governance_context.py`

- [ ] **Step 1: Write failing report helper tests**

Create `tests/test_top_picks_governance_context.py`:

```python
import top_picks_report as tpr


class GovCursor:
    def __init__(self):
        self.executed = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchall(self):
        return [
            {
                "symbol": "POLYCAB",
                "engine_rating": "HIGH_RISK",
                "engine_score": 67.0,
                "annual_review_label": "High Risk",
                "audit_opinion": "Qualified",
                "parser_mismatches_count": 4,
                "human_review_count": 9,
            }
        ]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class GovConn:
    def __init__(self):
        self.cursor_obj = GovCursor()

    def cursor(self, *args, **kwargs):
        return self.cursor_obj


def test_get_governance_contexts_reads_latest_pg_view():
    conn = GovConn()

    contexts = tpr.get_governance_contexts(conn, ["POLYCAB", "INFY"])

    assert contexts["POLYCAB"]["annual_review_label"] == "High Risk"
    assert contexts["POLYCAB"]["audit_opinion"] == "Qualified"
    assert "governance.latest_company_reviews" in conn.cursor_obj.executed[0][0]


def test_format_governance_context_line_handles_missing_context():
    assert tpr.format_governance_context_line(None) == "Governance: not yet reviewed"


def test_format_governance_context_line_renders_compact_context():
    line = tpr.format_governance_context_line(
        {
            "engine_rating": "HIGH_RISK",
            "engine_score": 67.0,
            "annual_review_label": "High Risk",
            "audit_opinion": "Qualified",
            "parser_mismatches_count": 4,
            "human_review_count": 9,
        }
    )

    assert line == "Governance: High Risk annual review; engine HIGH_RISK 67.0; audit Qualified; 4 parser mismatches; 9 manual checks"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
./.venv/bin/python -m pytest -q tests/test_top_picks_governance_context.py
```

Expected: failure because helper functions do not exist.

- [ ] **Step 3: Add report helper functions**

Add near the data-access helpers in `top_picks_report.py`:

```python
def get_governance_contexts(conn, symbols: list[str]) -> dict[str, dict]:
    wanted = [str(symbol).strip().upper() for symbol in symbols if str(symbol).strip()]
    if not wanted:
        return {}
    try:
        rows = _fetchall(
            conn,
            """
            SELECT symbol, engine_rating, engine_score, annual_review_label,
                   audit_opinion, parser_mismatches_count, human_review_count,
                   created_at
            FROM governance.latest_company_reviews
            WHERE symbol = ANY(%s)
            """,
            (wanted,),
        )
    except Exception:
        return {}
    return {str(row.get("symbol") or "").upper(): dict(row) for row in rows}


def format_governance_context_line(context: dict | None) -> str:
    if not context:
        return "Governance: not yet reviewed"
    label = context.get("annual_review_label") or "Unknown"
    rating = context.get("engine_rating") or "UNKNOWN"
    score = context.get("engine_score")
    audit = context.get("audit_opinion") or "Unknown"
    mismatches = int(context.get("parser_mismatches_count") or 0)
    checks = int(context.get("human_review_count") or 0)
    score_text = f"{float(score):.1f}" if score is not None else "-"
    return (
        f"Governance: {label} annual review; engine {rating} {score_text}; "
        f"audit {audit}; {mismatches} parser mismatches; {checks} manual checks"
    )
```

In the main report build, after `stocks`/`picks` are assembled and `conn` exists, compute:

```python
governance_contexts = get_governance_contexts(conn, [p.symbol for p in picks])
```

When rendering each per-stock Markdown section, add:

```python
out.append(f"**{format_governance_context_line(governance_contexts.get(p.symbol))}**\n\n")
```

For HTML cards, add the same text to the facts/risk area using existing HTML escaping helper.

- [ ] **Step 4: Run report helper tests**

Run:

```bash
./.venv/bin/python -m pytest -q tests/test_top_picks_governance_context.py
```

Expected: all tests pass.

- [ ] **Step 5: Run top-picks focused tests**

Run:

```bash
./.venv/bin/python -m pytest -q tests/test_top_picks_research_overlay.py tests/test_top_picks_governance_context.py
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add top_picks_report.py tests/test_top_picks_governance_context.py
git commit -m "feat: show stored governance context in top picks"
```

## Task 8: Daily Refresh Hook

**Files:**
- Modify: `daily_refresh.py`
- Create: `tests/test_daily_refresh_governance.py`

- [ ] **Step 1: Write failing daily-refresh tests**

Create `tests/test_daily_refresh_governance.py`:

```python
import daily_refresh


def test_step_governance_top_picks_invokes_batch_script(monkeypatch):
    calls = []

    monkeypatch.setattr(daily_refresh, "_ensure_postgres_running", lambda dry_run=False: True)
    monkeypatch.setattr(daily_refresh, "_run", lambda label, cmd, dry_run=False: calls.append((label, cmd, dry_run)) or True)

    assert daily_refresh.step_governance_top_picks(dry_run=False, workers=2, skip_fresh_days=7) is True

    label, cmd, dry = calls[0]
    assert "Governance top-picks review" in label
    assert "-m" in cmd
    assert "scripts.backfill_governance_reviews" in cmd
    assert "--top-picks" in cmd
    assert "--workers" in cmd
    assert "2" in cmd


def test_step_governance_top_picks_respects_dry_run(monkeypatch):
    calls = []

    monkeypatch.setattr(daily_refresh, "_ensure_postgres_running", lambda dry_run=False: True)
    monkeypatch.setattr(daily_refresh, "_run", lambda label, cmd, dry_run=False: calls.append(dry_run) or True)

    assert daily_refresh.step_governance_top_picks(dry_run=True) is True
    assert calls == [True]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
./.venv/bin/python -m pytest -q tests/test_daily_refresh_governance.py
```

Expected: failure because `step_governance_top_picks` does not exist.

- [ ] **Step 3: Implement daily-refresh step and CLI flag**

Add to `daily_refresh.py` near other step functions:

```python
def step_governance_top_picks(
    dry_run: bool,
    workers: int = 2,
    skip_fresh_days: int = 7,
) -> bool:
    """Refresh persisted governance reviews for latest top picks.

    This uses stored top-picks symbols and hybrid freshness logic. It does not
    run the full NIFTY 500 governance batch during daily refresh.
    """
    _section("STEP 8b — Governance Top-Picks Review")
    if not _ensure_postgres_running(dry_run=dry_run):
        return False
    cmd = [
        PYTHON,
        "-u",
        "-m",
        "scripts.backfill_governance_reviews",
        "--top-picks",
        "--workers",
        str(workers),
    ]
    return _run("Governance top-picks review", cmd, dry_run=dry_run)
```

Add parser flags:

```python
parser.add_argument("--governance-top-picks", action="store_true", help="Refresh persisted governance reviews for latest top picks")
parser.add_argument("--governance-workers", type=int, default=2, help="Worker count for governance top-picks refresh")
```

In the main daily flow, call:

```python
if args.governance_top_picks:
    ok &= step_governance_top_picks(
        dry_run=args.dry_run,
        workers=args.governance_workers,
    )
```

- [ ] **Step 4: Run daily-refresh tests**

Run:

```bash
./.venv/bin/python -m pytest -q tests/test_daily_refresh_governance.py tests/test_refresh_failure_handling.py
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add daily_refresh.py tests/test_daily_refresh_governance.py
git commit -m "feat: add governance top-picks refresh step"
```

## Task 9: Verification And Smoke

**Files:**
- No planned code edits.

- [ ] **Step 1: Run migration/storage/batch/report tests**

```bash
./.venv/bin/python -m pytest -q tests/test_governance_pg_migration.py tests/test_governance_storage.py tests/test_governance_batch.py tests/test_top_picks_governance_context.py tests/test_daily_refresh_governance.py
```

Expected: all tests pass.

- [ ] **Step 2: Run existing governance and command tests**

```bash
./.venv/bin/python -m pytest -q tests/test_governance_models.py tests/test_governance_parsers.py tests/test_governance_audit_parser.py tests/test_governance_sources.py tests/test_governance_scorer.py tests/test_governance_opinion.py tests/test_governance_annual_report_review.py tests/test_governance_engine.py tests/test_governance_live_sources.py tests/test_terminal_governance_command.py
```

Expected: all tests pass.

```bash
./.venv/bin/python -m pytest -q tests/test_command_dispatch.py
```

Expected: all tests pass.

- [ ] **Step 3: Run a limited top-picks governance batch**

If PostgreSQL is available:

```bash
./.venv/bin/python -m scripts.backfill_governance_reviews --top-picks --workers 1 --limit 1
```

Expected: one symbol is attempted or skipped, and the command prints a batch summary. If PostgreSQL or LLM credentials are unavailable, record the exact failure and do not claim live smoke success.

- [ ] **Step 4: Confirm report helper does not require governance rows**

```bash
./.venv/bin/python -m pytest -q tests/test_top_picks_governance_context.py
```

Expected: helper gracefully returns missing context when no stored rows exist.

- [ ] **Step 5: Confirm git status**

```bash
git status --short
```

Expected: only unrelated pre-existing generated/data files remain dirty; implementation files for this feature are committed.

## Self-Review Checklist

- Spec coverage:
  - PostgreSQL schema and latest view: Task 1.
  - Stable hashes and normalized payload extraction: Task 2.
  - Historical review and section persistence: Task 3.
  - Hybrid refresh decisions and top-picks/NIFTY 500 resolution: Tasks 4 and 6.
  - Parallel batch runner and CLI: Task 5.
  - Reports consume stored context without LLM: Task 7.
  - Daily-refresh top-picks hook: Task 8.
  - Verification: Task 9.

- TDD coverage:
  - Each production component has failing tests before implementation.
  - Normal tests use fake connections/repositories and do not require PostgreSQL, NSE, Screener, or OpenAI.

- Boundaries:
  - `storage.py` does not fetch live data or call LLMs.
  - `batch.py` orchestrates but does not render reports.
  - Reports only read stored PostgreSQL context and degrade to missing evidence.
