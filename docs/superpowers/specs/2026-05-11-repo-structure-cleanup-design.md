# Repo Structure Cleanup Design

## Goal

Reorganize the Unified-NSE-Analysis repository so active runtime code, generated data, generated reports, archives, and experiments are clearly separated, while preserving existing terminal commands and avoiding accidental loss of business data.

## Current Problems

- The repository root contains 77 Python/R scripts, mixing runtime entrypoints, fetchers, report generators, experiments, demos, and old merge utilities.
- Generated data and reports dominate size: `data/` is about 483 MB, `reports/` about 229 MB, `organized/` about 161 MB, and `postgres/` about 66 MB.
- Root-level dated NSE files such as `pr29102025.csv`, `mcap29102025.csv`, `an29102025.txt`, and `PR110526.zip` look like downloaded artifacts, not source code.
- Active new modules such as `company_intelligence_*.py` and `voice_*.py` are in the root, which makes imports and ownership unclear.
- Older generated reports are spread across `reports/`, `reports/generated_csv/`, `reports/nse_analysis/`, `reports/sector_rotation/`, and `reports/latest/`.
- There are duplicate historical areas: `archive/`, `organized/`, `output/`, and `working-sector/output/`.

## Constraints

- Do not delete domain data in the first pass. Archive first, delete only obvious generated junk such as `__pycache__` and `.DS_Store`.
- Do not break `python nse_agent.py`, slash commands, tests, or existing report generation.
- Do not move large active DB/cache files unless code paths are updated and tested.
- Preserve user-generated reports and terminal captures unless explicitly marked as generated and old.
- Use manifest-driven moves so every moved or deleted path is auditable.

## Target Structure

```text
agent_adda/                  # installable CLI package
terminal/                    # terminal agent runtime, tools, renderer, reports
company_intelligence/        # company xray, indexing, search, DB, policy, report modules
voice/                       # voice capture, transcription, TTS, sessions, live loop
scripts/
  fetchers/                  # fetch_fii_dii, fetch_fno, fetch_macro, fetch_corporate_events
  reports/                   # report generator scripts
  r/                         # R data pipelines and analysis scripts
  maintenance/               # cleanup, backfill, migration utilities
data/
  raw/                       # raw exchange downloads
  cache/                     # transient provider caches
  db/                        # SQLite DB files if path migration is approved later
  exports/                   # user exports
reports/
  latest/                    # stable latest aliases
  generated/                 # current generated reports
  archive/YYYYMMDD/          # report archive by cleanup run date
archive/
  repo-cleanup-YYYYMMDD/     # archived root scripts, legacy dirs, old artifacts
docs/
tests/
```

The first implementation should not move DB paths into `data/db/`; that is a later step because many scripts currently refer to `data/sector_rotation_tracker.db`, `data/nse_eod.db`, and related cache files.

## Cleanup Policy

### Safe Delete

Delete only paths that are deterministic generated junk:

- `.DS_Store`
- `__pycache__/`
- `*/__pycache__/` outside `.venv`
- `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/` if present
- `reports/temp/`
- `tmp/visual-qa/` after visual QA artifacts have been archived or are no longer needed

Do not delete anything inside `.venv`; `.venv` is ignored by git and can be removed manually later if disk space is required.

### Archive First

Move these into `archive/repo-cleanup-YYYYMMDD/` before any deletion:

- Root dated NSE files: `*29102025.csv`, `*29102025.txt`, `PR*.zip`
- Old demo/test R scripts: `run_demo.R`, `production_demo.R`, `final_complete_demo.R`, `simple_test.R`, `test_system.R`
- Old merge/loading experiments: `final_data_merge.R`, `merge_all_data.R`, `september_final_merge.R`, `truncate_and_replace_data.R`, `real_nse_analysis*.R`, `comprehensive_real_nse_analysis.R`
- Legacy output directories: `organized/`, `output/`
- Old report files outside `reports/latest/` and outside currently referenced generated paths

### Keep In Place Initially

Keep these in place during the first pass:

- `nse_agent.py`
- `sector_rotation_report.py`
- `sector_rotation_tracker.py`
- `daily_refresh.py`
- `fixed_nse_universe_analysis.py`
- `load_latest_nse_data_comprehensive.R`
- `terminal/`
- `agent_adda/`
- `tests/`
- `data/sector_rotation_tracker.db`
- `data/nse_sec_full_data.csv`
- `data/nse_index_data.csv`
- `reports/latest/`

## Code Reorganization Policy

Code moves happen only after inventory and archive are complete.

### Company Intelligence

Move root `company_*` modules into a new `company_intelligence/` package:

```text
company_intelligence/
  __init__.py
  command.py
  job.py
  model.py
  analyze.py
  db.py
  extract.py
  policy.py
  promote.py
  report.py
  search.py
  website_adapters.py
  website_indexer.py
  xray_command.py
```

For one release, keep root shim files such as `company_intelligence_search.py` that import and re-export from the new package. This avoids breaking tests and existing commands while imports are migrated.

### Voice

Move root `voice_*` modules into a new `voice/` package:

```text
voice/
  __init__.py
  capture.py
  command.py
  copilot.py
  live.py
  mode.py
  persona.py
  session.py
  synth.py
  transcribe.py
```

Keep root shims for one release.

### Fetchers And Reports

Move operational scripts into `scripts/` only after commands and documentation are updated:

- `fetch_*.py` -> `scripts/fetchers/`
- `generate_voice_briefing.py`, `email_nse_reports.py` -> `scripts/reports/`
- R pipelines -> `scripts/r/`
- backfills and maintenance utilities -> `scripts/maintenance/`

Root command shims can remain for high-use entrypoints.

## Verification Strategy

Every phase must run these checks before the next phase:

```bash
./.venv/bin/python -m py_compile nse_agent.py terminal/agent.py terminal/tools.py terminal/reports.py
./.venv/bin/python -m unittest tests.test_strength_validation tests.test_voice_synth tests.test_terminal_intraday_fallback -v
./.venv/bin/python nse_agent.py --no-briefing --skip-readiness -q "/strength MANINDS THERMAX"
```

For company and voice moves, also run:

```bash
./.venv/bin/python -m unittest tests.test_company_intelligence_search tests.test_company_index_command tests.test_company_xray_command -v
./.venv/bin/python -m unittest tests.test_voice_command tests.test_voice_mode tests.test_voice_live tests.test_voice_synth -v
```

## Rollback Strategy

- Every archived/moved path must be recorded in `docs/repo-cleanup-manifest-YYYY-MM-DD.md`.
- Archive moves must preserve relative source path under `archive/repo-cleanup-YYYYMMDD/`.
- Code moves must use compatibility shims for at least one cleanup cycle.
- If a verification command fails, stop moving files and restore only the paths listed in the manifest for that phase.

## Non-Goals

- Do not redesign the data model in this cleanup.
- Do not migrate SQLite DB locations in the first pass.
- Do not delete old reports permanently in the first pass.
- Do not rewrite large modules such as `nse_agent.py` or `sector_rotation_report.py` beyond path/import updates required by moves.
