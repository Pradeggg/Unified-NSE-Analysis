# SQLite to Postgres Full Cutover Design

## Context

The repository currently has a mixed persistence model. PostgreSQL already stores a large part of the market platform through schemas such as `ref`, `market`, `derivatives`, `scores`, `signals`, `breadth`, `macro`, and `portfolio`. SQLite is still present in active runtime paths and migration sources.

Active SQLite files identified during discovery:

- `data/sector_rotation_tracker.db`
- `data/fno/fno_eod.db`
- `data/nse_analysis.db`
- `nse_analysis.db`
- `data/nse_eod.db` and `data/stage_tracker.db`, which appear empty and should be treated as retirement candidates after an audit

Active code still imports or connects to SQLite in these areas:

- Market and reporting runtime: `terminal/tools.py`, `terminal/reports.py`, `terminal/data_readiness.py`, `terminal/fno_data.py`, `terminal/portfolio_monitor.py`
- Migration/runtime bridge: `postgres/migrate.py`
- Agent Adda historical cache and doctor: `agent_adda/data/historical.py`, `agent_adda/doctor.py`, `agent_adda/config/settings.py`
- Company intelligence: `company_intelligence_db.py`, `company_intelligence_extract.py`, `company_intelligence_search.py`, `company_intelligence_promote.py`, `company_intelligence_policy.py`, `company_intelligence.py`
- Tests that currently construct temporary SQLite databases for the above modules

The user wants all SQLite tables and data migrated to PostgreSQL and associated code refactored to point to PostgreSQL.

## Goals

- Migrate all active SQLite-backed data into PostgreSQL.
- Refactor active runtime code to use PostgreSQL as the only production database.
- Preserve existing behavior for portfolio monitoring, sector reports, F&O analytics, company intelligence, and Agent Adda historical data.
- Provide auditable migration tooling that can be re-run safely.
- Retire SQLite databases from runtime use after verification.

## Non-Goals

- Do not rewrite unrelated report generation, strategy logic, or portfolio algorithms.
- Do not change CSV and JSON file-based artifacts unless they are directly tied to SQLite retirement.
- Do not refactor archived or generated report files just because they contain historical text mentioning SQLite.
- Do not delete SQLite files until migration parity and runtime smoke tests pass.

## Recommended Approach

Use a staged full cutover with compatibility tests.

This is safer than a big-bang migration because the codebase has multiple independent SQLite subsystems and several are already partially PostgreSQL-backed. Each stage should leave the system runnable and verifiable before moving to the next stage.

## Data Model Design

Existing PostgreSQL tables should remain the canonical targets where they already exist:

- `scores.stage_snapshots` for `data/sector_rotation_tracker.db:stage_snapshots`
- `scores.stage_changes` for `data/sector_rotation_tracker.db:stage_changes`
- `derivatives.fno_eod` for `data/fno/fno_eod.db:fno_eod`
- `market.index_eod` for `nse_analysis.db:index_analysis`
- `breadth.market_daily` and related breadth tables for `nse_analysis.db:market_breadth`

New PostgreSQL tables are needed for SQLite-only subsystems.

Company intelligence should move into a dedicated schema, recommended as `intelligence`, with tables corresponding to current SQLite structures:

- `intelligence.companies`
- `intelligence.company_aliases`
- `intelligence.source_documents`
- `intelligence.search_runs`
- `intelligence.search_attempts`
- `intelligence.evidence_chunks`
- `intelligence.structured_facts`
- `intelligence.sector_entities`
- `intelligence.macro_policy_events`
- `intelligence.impact_assessments`
- `intelligence.analysis_runs`
- `intelligence.website_crawl_runs`
- `intelligence.website_pages`
- `intelligence.website_links`
- `intelligence.website_page_chunks`

SQLite FTS should be replaced with PostgreSQL-native search:

- Add generated or maintained `tsvector` columns for searchable website chunks.
- Add GIN indexes for full-text search.
- Use `pg_trgm` for fuzzy alias/company matching where helpful.

Agent Adda historical CSV loads should move into a dedicated PostgreSQL table, recommended as `market.historical_loads` or a small `agent_adda` schema if the data is not market-wide. The table should preserve the current historical loader's row identity, source CSV lineage, load timestamp, and OHLCV values.

## Migration Tooling

`postgres/migrate.py` should remain the primary entrypoint, but the work should be split into focused functions or helper modules so each data family can be tested independently.

Required migration behavior:

- Idempotent inserts and upserts.
- `--section` support for each cutover area.
- `--dry-run` support that validates source readability and target schema.
- Row-count reporting for each SQLite source table and PostgreSQL target table.
- A final parity summary showing exact matches, acceptable transformations, and skipped obsolete/empty tables.
- Clear error messages for missing PostgreSQL schema, missing source DBs, and malformed rows.

The migration should treat empty DBs as audit items, not failures, unless code still depends on them.

## Runtime Refactor

Runtime code should use PostgreSQL through shared connection helpers and DSN resolution:

- Prefer `AGENT_ADDA_PG_DSN`.
- Fall back to `PG_DSN`.
- Fall back to the current local default: `dbname=nse_market user=nse_admin host=/tmp`.

Production code should stop opening SQLite connections. Temporary SQLite use should remain only in migration/import tools until the cutover is complete.

Refactor order:

1. Market/stage/F&O readers that already have PostgreSQL targets.
2. Portfolio monitor and report generation paths.
3. Data readiness and terminal tools source-health paths.
4. Company intelligence storage, extraction, search, and promotion paths.
5. Agent Adda historical loader and doctor paths.

Any user-facing source labels should be updated from SQLite-specific wording to PostgreSQL-backed source names after the runtime path is actually switched.

## Testing Design

Tests should be updated in the same stage as the code they cover.

Migration tests:

- Build small source SQLite fixtures for each source family.
- Run the relevant migrator into isolated PostgreSQL test tables or schemas.
- Assert row counts and representative field mappings.
- Assert idempotency by running the same migration twice.

Runtime tests:

- Portfolio monitor reads stage snapshots from PostgreSQL.
- Terminal reports read sector/stage data from PostgreSQL.
- F&O analytics read and write `derivatives.fno_eod`.
- Data readiness reports PostgreSQL health and coverage without SQLite fallback.
- Company intelligence CRUD, search, evidence promotion, and website chunk search work against PostgreSQL.
- Agent Adda historical loading writes to PostgreSQL and doctor checks PostgreSQL.

Smoke tests:

- Generate portfolio monitor report.
- Generate sector rotation report or equivalent report preset.
- Query an F&O overview using PostgreSQL EOD data.
- Run a company intelligence indexing/search/promote flow on a small fixture.

## Rollout Plan

1. Audit all SQLite source DBs and active call sites.
2. Add missing PostgreSQL schemas and indexes.
3. Extend migration tooling and run dry-run audits.
4. Migrate existing data into PostgreSQL.
5. Refactor runtime modules slice by slice.
6. Update tests slice by slice.
7. Run parity checks and smoke tests.
8. Remove production SQLite fallback flags and stale source labels.
9. Mark old SQLite DB files as retired after verification.

## Risks and Mitigations

- Risk: SQLite FTS behavior differs from PostgreSQL full-text search.
  Mitigation: Add focused search ranking tests and keep query behavior simple at first.

- Risk: Existing tests rely heavily on SQLite temporary fixtures.
  Mitigation: Convert tests by subsystem rather than all at once, using isolated PostgreSQL schemas or monkeypatched connection helpers.

- Risk: Migration row counts can differ due to deduplication or type normalization.
  Mitigation: Report explicit transformation counts and document intentional differences.

- Risk: User worktree has many existing modified files.
  Mitigation: Keep changes scoped, inspect touched files before editing, and avoid reverting unrelated changes.

## Acceptance Criteria

- `rg "sqlite3|sqlite|\\.db"` in active source code shows only migration/import utilities, archived code, tests that intentionally create migration fixtures, or documentation.
- All active SQLite source tables have PostgreSQL targets or are explicitly documented as empty/retired.
- Migration tooling reports source and target counts for every migrated table.
- Portfolio monitor, terminal reports, F&O analytics, company intelligence, and Agent Adda historical flows run without production SQLite connections.
- Relevant tests pass after being updated to PostgreSQL-backed behavior.
- Existing SQLite DB files are no longer required for runtime behavior.
