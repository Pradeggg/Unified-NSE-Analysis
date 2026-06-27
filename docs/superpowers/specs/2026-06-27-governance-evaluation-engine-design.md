# Governance Evaluation Engine Design

## Purpose

Build a comprehensive governance evaluation engine for NSE-listed companies. The engine should extract, normalize, score, and explain governance evidence from NSE-first sources, with explicit source trails and missing-evidence disclosure. LLM usage is limited to producing an opinion from structured evidence; raw facts, scores, and flags remain deterministic.

This is a research and learning feature. It must not produce investment advice, trading instructions, or unsupported claims.

## Current Context

The root `governance/` directory currently contains only `files.zip`, with four prototype files:

- `governance_fetcher.py`: combines live fetches, parsers, scoring, flags, and CLI behavior.
- `governance_ar_parser.py`: parses annual-report PDFs for audit signals.
- `nse_endpoint_map.py`: documents candidate NSE/BSE/Screener endpoints.
- `test_governance.py`: mock demo for clean and risky companies.

The prototype has useful domain coverage, but it is not ready to integrate directly because it is packaged as a zip, mixes unrelated responsibilities, has date-comparison bugs in insider scoring, has fragile audit-section detection, and treats missing evidence as partial credit without enough confidence metadata.

The existing repo already has stronger patterns to reuse:

- `fetch_insider_alerts.py` handles NSE PIT, bulk deal, and block deal fetching and local CSV cache output.
- `terminal/search_engine.py` has NSE announcement, corporate action, PIT, and Screener shareholding wrappers.
- `terminal/research_council/llm_client.py` provides OpenAI/Ollama JSON calls with deterministic fallback controls.
- `terminal/research_council/evidence_pack_builder.py` shows the preferred evidence-pack shape: sections, source trails, missing evidence, and graceful degradation.
- `postgres/schema.sql` already stores `signals.insider_alerts`, `signals.bulk_block_deals`, `signals.corporate_events`, and financial-result analysis tables.

## Goals

1. Create a first-class Python package at `terminal/governance/`.
2. Evaluate one NSE symbol at a time in v1.
3. Prefer NSE-derived evidence when available, and clearly label any fallback evidence.
4. Generate deterministic governance scores and flags before any LLM call.
5. Produce JSON-serializable output and a Markdown summary.
6. Use an LLM only to turn structured evidence into a bounded governance opinion.
7. Make all normal tests deterministic and fixture-based, with no live network dependency.
8. Leave batch universe scanning and full Research Council integration for later phases, while designing clean interfaces for both.

## Non-Goals For V1

- No daily all-symbol batch ranking.
- No automatic trading decisions or recommendations.
- No guarantee that every NSE endpoint is live or stable.
- No OCR for scanned annual reports.
- No new database migrations unless the implementation finds a small, clearly necessary persistence need. The first version can run read-through from live/cache and return JSON.
- No changes to existing unrelated reporting, intraday, FNO, or portfolio flows.

## User-Facing V1 Behavior

The primary API will be:

```python
from terminal.governance.engine import evaluate_governance

report = evaluate_governance("INFY", use_llm=False)
```

The CLI entry point can be a lightweight script or command wrapper after the package works:

```bash
python -m terminal.governance.engine INFY --json
python -m terminal.governance.engine INFY --llm --markdown
```

The returned report will include:

- `symbol`
- `as_of`
- `score`
- `rating`
- `component_scores`
- `flags`
- `evidence`
- `source_trail`
- `missing_evidence`
- `confidence`
- `llm_opinion` when requested and available

## Rating Model

V1 will use a 0 to 100 score because it is easier to read and compose than the prototype's 0 to 15 score. Component weights:

- Promoter pledge and promoter holding stability: 20
- Insider and promoter transactions: 15
- Institutional ownership trend: 10
- Audit and annual-report quality: 20
- Board, governance filings, and adverse announcements: 10
- Investor complaints and regulatory risk: 10
- Capital allocation and dilution proxies: 15

Ratings:

- `STRONG`: score >= 80 and no red flags.
- `WATCH`: score >= 65 and fewer than two amber flags.
- `CONCERN`: score >= 45 or any red flag that is not severe.
- `HIGH_RISK`: score < 45, severe red flag, or materially incomplete evidence with negative indicators.
- `INSUFFICIENT_EVIDENCE`: core evidence is missing and no defensible rating can be assigned.

Missing evidence does not automatically become a positive score. Each component must distinguish:

- observed positive evidence,
- observed negative evidence,
- unavailable evidence,
- stale evidence,
- fallback evidence.

## Evidence Sources

### NSE-First Sources

The package will define source adapters for:

- Shareholding pattern and pledge data, using NSE endpoints where stable and fallback parsing where needed.
- PIT/SAST insider disclosures.
- Bulk and block deals.
- Corporate announcements and governance-related filings.
- Corporate actions where relevant to dilution and capital allocation.
- Corporate governance report endpoint if reachable.
- Investor complaints endpoint if reachable.

### Existing Local Cache And Postgres Sources

The engine should use local data when present:

- `data/insider_alerts.csv`
- `data/insider_alerts_agg.csv`
- `data/_insider_cache/*.csv`
- `data/_insider_cache/pit_*.json`
- `data/corporate_events.csv`
- `data/filings/<SYMBOL>/**/manifest.json`
- Postgres tables if a DSN is available and the query path is already established.

### Fallback Sources

Fallbacks must be clearly labeled:

- Screener shareholding and financial data.
- BSE filing links discovered through existing search helpers.
- Parsed annual-report PDFs from local filing manifests.

Fallback evidence can improve confidence only if the source trail is explicit.

## Package Structure

```text
terminal/governance/
  __init__.py
  models.py
  nse_client.py
  cache_sources.py
  parsers.py
  audit_parser.py
  scorer.py
  opinion.py
  engine.py
  markdown.py
```

### `models.py`

Defines immutable or low-mutation dataclasses for normalized records:

- `GovernanceSource`
- `GovernanceMissingEvidence`
- `ShareholdingSnapshot`
- `InsiderDisclosure`
- `DealEvent`
- `GovernanceAnnouncement`
- `AuditSignal`
- `ComplaintSignal`
- `CapitalAllocationSignal`
- `GovernanceEvidence`
- `ComponentScore`
- `GovernanceReport`

Every normalized evidence object should carry source metadata or contribute to a `source_trail` entry.

### `nse_client.py`

Responsible only for NSE HTTP access:

- browser-like headers,
- session warm-up,
- request timeouts,
- small retry policy,
- JSON decoding,
- graceful error objects.

It must not score, parse domain semantics, or call LLMs.

### `cache_sources.py`

Reads local cache and optional Postgres evidence:

- recent PIT cache JSON,
- insider alerts CSV,
- bulk/block deal CSVs,
- corporate events CSV,
- filing manifests,
- optional Postgres records.

It returns raw records with source metadata. Tests will use this module with temp directories and fixture files.

### `parsers.py`

Normalizes raw source payloads into stable dataclasses. This includes:

- shareholding percentages and quarter parsing,
- pledge percentages,
- insider transaction date parsing,
- transaction type normalization,
- value in INR crore normalization,
- corporate announcement categorization,
- complaint count normalization,
- capital allocation proxy normalization.

Date parsing must use real date objects and never lexicographic string comparisons.

### `audit_parser.py`

Reworks the prototype annual-report parser into a safer optional parser:

- extracts text from a local PDF when dependencies are available,
- detects the independent auditor report section,
- classifies auditor tier,
- detects clean, qualified, adverse, or disclaimer opinion,
- detects emphasis of matter,
- counts key audit matters where possible,
- extracts related-party transaction amount only when revenue is provided.

Known prototype fix: section slicing must use `start is not None`, not truthiness, so a section at character zero is valid.

### `scorer.py`

Contains deterministic scoring only. It accepts `GovernanceEvidence` and returns component scores, flags, total score, rating, confidence, and missing-evidence notes.

Core rules:

- Promoter pledge above 25 percent is a red flag.
- Promoter pledge between 10 and 25 percent is amber.
- Promoter holding decline greater than 2 percentage points over four quarters is amber.
- Heavy promoter/insider selling over the last 12 months is amber or red depending on value and net direction.
- Qualified, adverse, or disclaimer audit opinion is red.
- High related-party transaction exposure is amber or red depending on percentage of revenue.
- Persistent unresolved complaints are amber or red.
- Weak free-cash-flow conversion, high dilution, and goodwill impairment are capital-allocation flags.
- Missing evidence reduces confidence and produces explicit gaps, not silent positive scoring.

### `opinion.py`

Generates a bounded governance opinion from the structured report. It uses `terminal.research_council.llm_client.call_llm_json`.

The prompt contract requires JSON output:

```json
{
  "opinion_label": "Strong | Watch | Concern | High Risk | Insufficient Evidence",
  "summary": "short paragraph",
  "strengths": ["..."],
  "concerns": ["..."],
  "data_gaps": ["..."],
  "watch_items": ["..."],
  "research_only_disclaimer": "..."
}
```

The system prompt must prohibit:

- unsupported facts,
- investment advice,
- price targets,
- trading instructions,
- hiding missing data.

If no LLM provider is available, the engine returns the deterministic report and records `llm_status: unavailable`.

### `engine.py`

Coordinates:

1. resolve and normalize symbol,
2. fetch/read raw evidence,
3. parse normalized evidence,
4. compute score,
5. optionally call LLM opinion,
6. render JSON or Markdown.

It must support dependency injection for tests:

```python
evaluate_governance(
    symbol: str,
    use_llm: bool = False,
    raw_sources: GovernanceRawSources | None = None,
    llm_client: Callable[..., dict] | None = None,
) -> GovernanceReport
```

### `markdown.py`

Renders a concise report:

- heading and as-of date,
- score/rating/confidence,
- component score table,
- red/amber flags,
- evidence summary,
- missing evidence,
- LLM opinion if present.

## Data Flow

```text
symbol
  -> raw NSE/cache/fallback source reads
  -> normalized governance evidence
  -> deterministic component scoring
  -> report JSON
  -> optional LLM opinion JSON
  -> optional Markdown rendering
```

The LLM receives only normalized evidence, component scores, flags, and source gaps. It never receives a blank prompt asking it to infer governance facts.

## Error Handling

- Network failures produce source-trail errors and missing-evidence entries.
- Parser failures are isolated to the source and do not crash the full report unless all core evidence is unavailable.
- Missing audit PDF produces an audit data gap, not a parser exception.
- Missing optional packages for PDF parsing produce an audit data gap with dependency detail.
- LLM failure does not fail deterministic evaluation.
- Every error visible to users should be phrased as source availability or parsing limitation, not as an internal stack trace.

## Confidence Model

Confidence is separate from score:

- `High`: core shareholding, insider, announcements, and at least one audit or complaints/capital-allocation source are available and fresh.
- `Medium`: at least two core governance sources are available, but one major area is missing or fallback-only.
- `Low`: only one core source is available, evidence is stale, or most data is fallback-only.

The report can have a good score and low confidence. The LLM opinion must mention low confidence when present.

## Testing Strategy

Tests are written before implementation. Normal tests must not call live NSE, BSE, Screener, OpenAI, or Ollama.

Required test groups:

- `tests/test_governance_parsers.py`
  - parses NSE shareholding payloads with quarter ordering,
  - parses PIT disclosures using date objects,
  - normalizes buy, sell, pledge, and revoke transactions,
  - handles missing numeric fields.
- `tests/test_governance_scorer.py`
  - scores zero pledge positively,
  - flags high pledge,
  - flags promoter holding decline over four quarters,
  - treats stale or missing insider data as a confidence gap,
  - detects recent insider selling with parsed dates,
  - handles audit red flags,
  - handles missing evidence without granting full credit.
- `tests/test_governance_audit_parser.py`
  - confirms auditor section at character zero is detected,
  - classifies auditor tiers,
  - detects clean and qualified opinions,
  - handles no extracted text.
- `tests/test_governance_engine.py`
  - builds a full report from injected raw fixture sources,
  - returns deterministic report when LLM is disabled,
  - records LLM unavailable without failing,
  - includes source trails and missing evidence.
- `tests/test_governance_opinion.py`
  - sends only structured evidence to the injected LLM client,
  - validates required opinion fields,
  - rejects unsupported labels.

Live smoke tests can be added later under a marker such as `live_nse`, but they are not required for v1 completion.

## Migration From Prototype Zip

The prototype should be treated as reference material, not copied wholesale.

Reusable ideas:

- data classes,
- component categories,
- scoring thresholds,
- annual-report parsing patterns,
- endpoint list.

Required corrections:

- parse dates before comparison,
- do not hardcode stale fixture dates,
- separate fetching, parsing, scoring, and opinion generation,
- use source trails,
- handle missing evidence as confidence impact,
- remove non-ASCII status icons from core data structures,
- keep Markdown rendering responsible for presentation.

## Future Phases

### Phase 2: Research Council Integration

Add a `governance` evidence section and optional `GovernanceAgent` specialist. The agent should consume the deterministic report and contribute risks, candidates, rejects, and required next steps.

### Phase 3: Persistence

Add optional Postgres tables for governance snapshots if repeated scoring and trend history become necessary:

- `signals.governance_snapshots`
- `signals.governance_component_scores`
- `signals.governance_source_trail`

### Phase 4: Batch Scanner

Score a universe daily, cache results, and rank:

- high-risk governance flags,
- improving governance,
- missing-data watchlist,
- promoter pledge monitor,
- insider sell monitor.

## Acceptance Criteria

1. `evaluate_governance("INFY", use_llm=False)` returns a JSON-serializable `GovernanceReport`.
2. A fixture-backed risky company receives red/amber flags for high pledge, promoter selling, audit issue, or complaint issue as applicable.
3. A fixture-backed clean company receives a high score with no red flags when evidence is complete.
4. Missing evidence lowers confidence and appears in `missing_evidence`.
5. Insider date filtering works against the current date using parsed date objects.
6. The audit parser recognizes an auditor section starting at character zero.
7. Optional LLM opinion succeeds with an injected fake LLM client in tests.
8. Optional LLM failure degrades gracefully.
9. Markdown output includes score, rating, flags, missing evidence, source trail, and disclaimer.
10. No normal test performs a live network or live LLM call.

## Fixed V1 Decisions

The following decisions are fixed for v1:

- Single-stock evaluation is the first deliverable.
- Scoring is deterministic and LLM opinion is optional.
- Source trails and missing evidence are first-class output fields.
- Batch scanner, persistence, and full Research Council integration are later phases.

The v1 scope is complete and ready for implementation planning after review.
