# Governance Live Evidence Loader Design

## Purpose

Phase 1 built a deterministic governance evaluation engine, but it only scored evidence already present in local caches. Phase 2 adds a live evidence loader that fetches NSE/Screener/BSE-derived governance evidence for one NSE symbol, persists the raw and parsed payloads under `data/governance/{SYMBOL}/`, and lets the existing engine score from that cache.

The report remains research-only. The LLM is still optional and only summarizes the deterministic report.

## Goals

1. Add `terminal/governance/live_sources.py`.
2. Add `--refresh-live` to `python -m terminal.governance.engine SYMBOL`.
3. Fetch live evidence for a single symbol:
   - NSE PIT disclosures through `NSEJsonClient`.
   - NSE corporate actions through existing `search_corporate_actions`.
   - Screener/BSE announcement links through existing `search_nse_announcements`.
   - Screener company payload through existing `scrape_screener_in`.
   - Latest annual report PDF from Screener, with page scanning for the actual Independent Auditor's Report.
4. Persist a reproducible cache:
   - `data/governance/{SYMBOL}/manifest.json`
   - `data/governance/{SYMBOL}/raw/*.json`
   - `data/governance/{SYMBOL}/raw/annual_report_text.txt`
   - `data/governance/{SYMBOL}/parsed/raw_sources.json`
5. Read the new cache through `load_cached_sources()` so reports run offline after refresh.
6. Keep all normal tests deterministic and network-free through dependency injection.

## Non-Goals

- No batch universe refresh.
- No Selenium/browser automation.
- No OCR fallback in the governance loader.
- No database migrations.
- No trading or investment advice.
- No automatic LLM call unless `--llm` is explicitly requested.

## Architecture

`live_sources.py` owns live fetching and cache writing. It returns `GovernanceRawSources`, the same raw source object accepted by `evaluate_governance()`. `cache_sources.py` gains a reader for `data/governance/{SYMBOL}/parsed/raw_sources.json`, falling back to the older PIT/bulk/block/corporate-event caches when the governance cache is absent.

The engine flow becomes:

```text
CLI --refresh-live
  -> refresh_live_sources(symbol)
  -> write data/governance/{SYMBOL}/...
  -> evaluate_governance(symbol, raw_sources=refreshed_raw)

CLI without --refresh-live
  -> load_cached_sources(symbol)
  -> use data/governance/{SYMBOL}/parsed/raw_sources.json if present
  -> fall back to existing local caches if absent
```

## Cache Shape

```text
data/governance/INFY/
  manifest.json
  raw/
    nse_pit.json
    announcements.json
    corporate_actions.json
    screener.json
    annual_report_text.txt
  parsed/
    raw_sources.json
```

`raw_sources.json` stores the JSON-safe `GovernanceRawSources.to_dict()` output. Dates in source trails are serialized as ISO strings by the existing model serializer.

## Annual Report Extraction

Screener annual-report links often include a `#page=N` fragment that may not match the physical PDF page index. The loader must not assume the fragment is exact. It downloads the PDF bytes, scans pages for `Independent Auditor... Report`, extracts a fixed window from the first matching page, and passes the text to the existing audit parser.

If PDF download or extraction fails, the loader records source status `error`, omits `annual_report_text`, and lets the scorer disclose missing audit evidence.

## Error Handling

Every live source contributes a `GovernanceSource` entry:

- `status="ok"` when useful data was fetched.
- `status="error"` when the call failed.
- `status="missing"` when a call succeeded but no useful evidence was present.

Errors do not abort the report unless all live sources fail and no prior cache exists. The engine still returns an evidence-gated report with missing evidence.

## Testing

Tests use injected fake fetchers and fake PDF bytes. They verify:

1. Live refresh returns `GovernanceRawSources` with shareholding, PIT, announcements, annual report text, and Screener payload.
2. Refresh writes `manifest.json`, raw files, annual report text, and parsed raw sources.
3. `load_cached_sources()` reads the governance cache before falling back to old caches.
4. CLI `--refresh-live` calls the live loader and passes refreshed raw sources into the evaluator.
5. No test requires live network access.

## Acceptance Criteria

- `python -m terminal.governance.engine INFY --refresh-live` produces a governance report using live evidence when network access is available.
- A second run without `--refresh-live` can use `data/governance/INFY/parsed/raw_sources.json`.
- Existing governance tests and nearby tests pass.
- Live INFY smoke test produces materially filled evidence and does not classify the annual report as qualified from incidental prose.
