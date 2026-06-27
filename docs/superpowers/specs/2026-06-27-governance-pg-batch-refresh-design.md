# Governance PostgreSQL Batch Refresh Design

## Purpose

Persist governance evaluation and annual-report review results in PostgreSQL so Agent Adda reports can use governance context without rerunning expensive LLM reads every time. The system should support one-off symbol refreshes, parallel NIFTY 500 batch refreshes, and weekly change-aware updates.

The output remains research-only. The persisted data is an evidence cache and report input, not an investment recommendation.

## Current Context

The governance engine now supports:

- deterministic governance scoring through `terminal/governance/engine.py`;
- live/cache evidence loading through `terminal/governance/live_sources.py` and `terminal/governance/cache_sources.py`;
- section-by-section annual-report LLM review through `terminal/governance/annual_report_review.py`;
- terminal usage through `/governance SYMBOL --live --llm-read`.

The repo already has useful PostgreSQL and batch patterns:

- migrations live under `postgres/migrations/` and are idempotent;
- `postgres/loader.py` centralizes DSN/env loading and bulk upsert helpers;
- NIFTY 500 constituents are available through `ref.index_compositions`;
- weekly backfills use skip-fresh logic, for example `scripts/backfill_screener_fundamentals.py`;
- reports such as `top_picks_report.py` and `sector_rotation_report.py` already read PostgreSQL with `psycopg2`.

## Goals

1. Add a persistent governance schema in PostgreSQL.
2. Store both normalized report fields and the full governance payload.
3. Keep historical runs so governance findings can be audited over time.
4. Provide a latest-by-symbol view for fast report joins.
5. Add a batch runner for NIFTY 500 and explicit symbol lists.
6. Support parallel worker threads with bounded concurrency.
7. Use a hybrid refresh policy:
   - always refresh current top picks/watchlist symbols weekly;
   - refresh the broader NIFTY 500 only when source evidence changes or existing rows become stale.
8. Track source hashes, annual-report hashes, LLM metadata, failures, and skipped symbols.
9. Expose stored governance context to reports without requiring live NSE or LLM calls.
10. Keep tests deterministic and avoid live network/LLM requirements in normal test runs.

## Non-Goals

- No intraday governance refresh.
- No automatic trade blocking or portfolio action.
- No OCR for scanned annual reports.
- No mandatory LLM call during normal daily report rendering.
- No report-wide redesign in this phase.
- No attempt to guarantee NSE/Screener endpoint stability beyond recording failures and retry eligibility.

## Storage Design

Create `postgres/migrations/20260627_governance_reviews.sql`. The migration should be idempotent and create a `governance` PostgreSQL schema with three tables and one view.

### `governance.review_runs`

One row per batch invocation.

Important columns:

- `run_id TEXT PRIMARY KEY`
- `started_at TIMESTAMPTZ`
- `completed_at TIMESTAMPTZ`
- `mode TEXT` such as `symbol`, `symbols`, `index`, `top_picks`
- `universe TEXT`
- `requested_symbols TEXT[]`
- `worker_count INTEGER`
- `refresh_policy TEXT`
- `status TEXT`
- `attempted INTEGER`
- `succeeded INTEGER`
- `failed INTEGER`
- `skipped_fresh INTEGER`
- `metadata JSONB`

### `governance.company_reviews`

One row per symbol per source snapshot/review result. This is the audit table.

Important columns:

- `review_id TEXT PRIMARY KEY`
- `run_id TEXT REFERENCES governance.review_runs(run_id)`
- `symbol TEXT NOT NULL`
- `as_of DATE NOT NULL`
- `source_hash TEXT NOT NULL`
- `annual_report_hash TEXT`
- `annual_report_selected_pages INTEGER[]`
- `engine_score NUMERIC(6,2)`
- `engine_rating TEXT`
- `engine_confidence TEXT`
- `annual_review_status TEXT`
- `annual_review_label TEXT`
- `audit_opinion TEXT`
- `auditor TEXT`
- `section_counts JSONB`
- `key_findings_count INTEGER`
- `parser_mismatches_count INTEGER`
- `human_review_count INTEGER`
- `flags JSONB`
- `missing_evidence JSONB`
- `source_trail JSONB`
- `full_payload JSONB NOT NULL`
- `status TEXT NOT NULL`
- `error TEXT`
- `created_at TIMESTAMPTZ`

Use a uniqueness constraint on `(symbol, source_hash)` so identical source evidence is not reviewed repeatedly.

Indexes:

- `(symbol, created_at DESC)` for latest lookup;
- `(symbol, source_hash)` unique constraint for de-duplication;
- `(annual_review_label, created_at DESC)` for report filtering;
- `(engine_rating, created_at DESC)` for risk rollups.

### `governance.company_review_sections`

One row per section review, linked to `company_reviews`.

Important columns:

- `review_id TEXT REFERENCES governance.company_reviews(review_id) ON DELETE CASCADE`
- `symbol TEXT NOT NULL`
- `section_id TEXT NOT NULL`
- `risk_label TEXT`
- `status TEXT`
- `summary TEXT`
- `findings JSONB`
- `red_flags JSONB`
- `page_evidence JSONB`
- `created_at TIMESTAMPTZ`

Primary key: `(review_id, section_id)`.

Indexes:

- `(symbol, section_id, created_at DESC)` for section-specific report diagnostics;
- `(risk_label, created_at DESC)` for governance risk summaries.

### `governance.latest_company_reviews`

A view selecting the latest successful row for each symbol by `created_at DESC`.

Reports should use this view for simple joins. Historical analysis can query `company_reviews` directly.

## Source Change Detection

The batch runner computes a deterministic `source_hash` before deciding whether to call the annual-report LLM. The hash includes:

- `GovernanceRawSources.to_dict()` with stable JSON sorting;
- annual report extracted text;
- source trail metadata that affects evidence meaning;
- governance parser version;
- annual-report review prompt/schema version.

The hash intentionally excludes transient values such as run timestamp.

If the latest stored row for a symbol has the same `source_hash` and is not stale, the batch runner skips the symbol and records it as `skipped_fresh`.

## Refresh Policy

The default policy is `hybrid`.

### Top Picks And Watchlists

When symbols are passed explicitly or resolved from the latest top-picks report, refresh them if:

- no stored review exists;
- the stored review is older than 7 days;
- source hash changed;
- the last stored status is `error`;
- the user passes `--force`.

### NIFTY 500

For broad NIFTY 500 runs, refresh a symbol if:

- no stored review exists;
- source hash changed;
- the stored review is older than 30 days;
- the last stored status is `error` and the retry cooldown has elapsed;
- the user passes `--force`.

This keeps the full universe current without paying for repeated identical annual-report reads every week.

## Batch Runner

Add `scripts/backfill_governance_reviews.py`.

Supported usage:

```bash
python -m scripts.backfill_governance_reviews --index "NIFTY 500"
python -m scripts.backfill_governance_reviews --symbols INFY,TCS,POLYCAB
python -m scripts.backfill_governance_reviews --top-picks
python -m scripts.backfill_governance_reviews --limit 25 --workers 2
python -m scripts.backfill_governance_reviews --force --refresh-live
```

Default behavior:

- `--index "NIFTY 500"`
- `--workers 2`
- `--policy hybrid`
- cached evidence first;
- `--refresh-live` optional;
- `--llm-read` enabled by default because persistence is intended to store the annual-report review;
- commit after each symbol so a long batch can be interrupted safely.

Each worker should open its own PostgreSQL connection. The LLM and live-source paths should stay bounded because annual-report review already makes several LLM calls per symbol.

## Python Modules

Add focused persistence modules under `terminal/governance/`:

```text
terminal/governance/
  storage.py
  batch.py
```

### `storage.py`

Responsibilities:

- connect to PostgreSQL;
- initialize schema from the migration when requested;
- compute stable source hashes;
- fetch latest stored review metadata;
- upsert review rows and section rows;
- read latest governance rows for report integration.

It should not fetch live data or call LLMs.

### `batch.py`

Responsibilities:

- resolve symbols from explicit list, top-picks files, or `ref.index_compositions`;
- decide skip versus refresh using `storage.py`;
- call `evaluate_governance()`;
- persist successful and failed symbol outcomes;
- return a structured batch summary.

It should not render reports directly.

## Report Integration

Reports should consume `governance.latest_company_reviews`.

Initial report usage:

- top-picks report: add a compact governance line per stock and use governance rating/annual label as a risk modifier;
- sector rotation report: optionally show governance risk distribution for shortlisted names;
- company research reports: show latest audit opinion, annual review label, and top parser mismatch/manual-review notes.

Report rendering must not call the LLM. If no stored governance row exists, the report should show missing governance evidence rather than doing live work.

## Daily Refresh Integration

Add an optional daily-refresh step:

```bash
python daily_refresh.py --governance-top-picks
```

The first integration should run only `--top-picks` with the hybrid weekly policy. Full NIFTY 500 refresh should remain a separate manual or scheduled job because it is slow and LLM-costly.

## Error Handling

Per-symbol failures do not fail the whole batch. Store failed outcomes with:

- `status='error'`;
- `error` text truncated to a safe length;
- `source_hash` when available;
- full exception type in metadata.

Interrupted runs should leave completed symbols committed and mark the run as `interrupted` when possible.

## Testing

Tests should cover:

1. migration file is idempotent and creates schema, tables, indexes, and latest view;
2. source hashing is stable and changes when annual-report text or parser version changes;
3. storage upsert writes one company review and multiple section rows;
4. latest review selection returns the newest successful review;
5. batch skip logic skips unchanged fresh symbols;
6. batch refresh logic reruns stale, changed, failed, or forced symbols;
7. symbol resolution supports explicit symbols, top-picks file, and mocked NIFTY 500 query;
8. report helper returns compact governance context without invoking LLM/live fetch.

Normal tests must use fake connections or fake repositories and must not require PostgreSQL, NSE, Screener, or OpenAI access.

## Acceptance Criteria

- A migration creates `governance.review_runs`, `governance.company_reviews`, `governance.company_review_sections`, and `governance.latest_company_reviews`.
- `python -m scripts.backfill_governance_reviews --symbols INFY --workers 1` persists one latest review when local evidence and LLM are available.
- `python -m scripts.backfill_governance_reviews --top-picks --workers 2` processes latest top-pick symbols and stores reusable rows.
- A repeated run skips unchanged fresh symbols unless `--force` is passed.
- Reports can read latest governance labels from PostgreSQL without running the governance engine.
- Governance and command-dispatch tests remain green.
