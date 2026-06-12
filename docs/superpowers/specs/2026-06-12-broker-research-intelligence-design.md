# Broker Research Intelligence Design

Date: 2026-06-12
Owner: Agent Adda / Codex
Status: design-only
Primary output: PostgreSQL-backed broker research ingestion, extraction, comparison, and published deep research reports

## Goal

Build a Deep Broker Research Intelligence capability for Agent Adda.

The user can provide broker research index pages, direct PDF links, or a stock symbol. Agent Adda discovers relevant public broker reports, stores source metadata and PDFs, parses report content, extracts structured research facts, compares broker assumptions, and publishes a grounded deep research report with source citations.

The first user-facing workflow should be single-stock:

```text
/broker-index BEL
/broker-research BEL
/deep-research BEL --brokers public
/report broker BEL html
```

Market-wide scheduled crawling is explicitly deferred to Phase 6 after the single-stock flow is reliable.

## Core Product Principle

Never store only an LLM summary.

Every broker report workflow must store:

- broker source registry rows
- index page fetch runs
- discovered report URLs
- raw PDF metadata and content hash
- local PDF path or object-store key
- parse status
- page-level text chunks
- table fragments when detected
- extracted structured facts
- LLM interpretation separately from evidence
- generated report metadata
- source trail down to broker, URL, report date, and page number when available

LLM output is interpretation. Broker PDFs and extracted facts are evidence.

## Source Registry

The initial registry should seed public Indian broker research sources from the curated links supplied by the user.

### Public Direct Sources

These are the first implementation target because they are mostly direct-access and do not require login:

- ICICI Direct
  - Master index: `https://www.icicidirect.com/mailcontent/co_reports.html`
  - PDF pattern: `https://www.icicidirect.com/mailcontent/idirect_{ticker}_{type}_{period}.pdf`
- HDFC Securities / HSIE
  - Master index: `https://www.hdfcsec.com/research/equity/stock-research-institutional-reports`
  - PDFs under `https://www.hdfcsec.com/hsl.docs/...`
- Axis Direct
  - Fundamental index: `https://simplehai.axisdirect.in/app/index.php/insights/reports/fundamental`
  - Trading index: `https://simplehai.axisdirect.in/research/research-reports/trading-reports`
  - PDFs under `simplehai.axisdirect.in/images/...` and downloadReport routes
- Sharekhan / Mirae Asset Sharekhan
  - Latest newsletters:
    - `https://www.sharekhan.com/MediaGalary/Newsletter/Investoreye.pdf`
    - `https://www.sharekhan.com/MediaGalary/Newsletter/Eagleeye_e.pdf`
    - `https://www.sharekhan.com/MediaGalary/Newsletter/DerivativeEye.pdf`
  - Dated PDFs under `https://www.sharekhan.com/MediaGalary/docs/...`

### Discovery-Only Sources

These may be supported after the direct sources:

- Trendlyne research reports index: `https://trendlyne.com/research-reports/`
- Trendlyne broker pages for Motilal Oswal, Kotak Securities, and other brokers
- Motilal Oswal pages where registration or non-guessable URLs require discovery
- Kotak public upload PDFs and Trendlyne discovery

### Excluded Sources

- Zerodha and Groww research are excluded because the supplied source notes they do not publish broker research.
- Login-only downloads are not fetched automatically. The system may store a blocked source row with reason `login_required`.

## PostgreSQL Storage

All broker research data must live in PostgreSQL. The existing `company_intel` schema is the canonical home for company/web intelligence. Broker-specific tables should be added under the same schema unless the table becomes market-wide enough to justify a new schema.

Recommended tables:

### `company_intel.broker_sources`

- `source_id`
- `broker_code`
- `broker_name`
- `source_kind`: `index_page`, `fixed_pdf`, `trendlyne_broker`, `url_pattern`
- `source_url`
- `access_mode`: `public`, `partial`, `login_required`
- `url_pattern`
- `is_active`
- `notes`
- `created_at`
- `updated_at`

### `company_intel.broker_index_runs`

- `index_run_id`
- `source_id`
- `started_at`
- `completed_at`
- `status`
- `http_status`
- `reports_found`
- `reports_new`
- `failure_reason`

### `company_intel.broker_reports`

- `broker_report_id`
- `broker_code`
- `symbol`
- `company_name`
- `report_title`
- `report_type`: `result_update`, `initiation`, `sector`, `strategy`, `technical`, `newsletter`, `unknown`
- `report_date`
- `source_url`
- `pdf_url`
- `pdf_hash`
- `local_path`
- `fetch_status`
- `parse_status`
- `discovered_via`
- `created_at`
- `updated_at`

### `company_intel.broker_report_pages`

- `page_id`
- `broker_report_id`
- `page_number`
- `text`
- `char_count`
- `search_vector`

### `company_intel.broker_report_tables`

- `table_id`
- `broker_report_id`
- `page_number`
- `table_index`
- `table_json`
- `caption`

### `company_intel.broker_research_facts`

- `fact_id`
- `broker_report_id`
- `symbol`
- `fact_type`: `rating`, `target_price`, `valuation_method`, `estimate`, `thesis`, `risk`, `catalyst`, `margin_driver`, `order_book`, `sector_view`
- `fact_name`
- `fact_value`
- `unit`
- `period`
- `page_number`
- `confidence`
- `extractor`: `deterministic`, `llm`, `hybrid`
- `created_at`

### `company_intel.broker_research_runs`

- `research_run_id`
- `symbol`
- `objective`
- `broker_filter`
- `as_of`
- `status`
- `report_markdown_path`
- `report_html_path`
- `report_pdf_path`
- `coverage_json`
- `created_at`

## Ingestion Flow

### 1. Source Registry Seed

Seed the broker sources from a checked-in YAML or SQL fixture. The registry should include the source URLs and access mode, not hard-code sources in crawler logic.

### 2. Discovery

For a symbol such as `BEL`, the system should:

1. resolve the symbol and company aliases
2. fetch each active public index page
3. parse PDF links and surrounding title/date text
4. score whether a report matches the requested symbol or company alias
5. insert or update `broker_reports`
6. mark blocked sources explicitly when login or anti-bot behavior prevents fetch

### 3. Fetch

For each selected PDF:

1. download with bounded timeout and max size
2. calculate SHA-256 hash
3. skip duplicate PDFs
4. write a durable local file under `data/company_intelligence/broker_reports/{broker_code}/{symbol}/`
5. store fetch metadata in PostgreSQL

### 4. Parse

The parser should extract:

- page text
- page count
- visible title/date if detectable
- table-like text blocks where feasible

The first parser can reuse the existing PDF parser used by filing/company intelligence. Later versions can add `camelot`, `tabula`, or layout-aware parsing if needed.

### 5. Extract Facts

Extraction should be hybrid:

- deterministic regex/table extraction for target price, rating, dates, revenue/PAT/EPS numbers, and valuation multiples
- LLM extraction for thesis, risks, catalysts, and assumptions
- all LLM facts must include page references from supplied chunks

## LLM Skills

The system needs specialized LLM skills, not a generic summarizer.

### Report Classifier

Classifies each PDF by report type, symbol coverage, broker, date, and confidence.

### Thesis Extractor

Extracts the broker's core argument:

- why the broker is positive/negative/neutral
- key operating drivers
- management commentary interpretation
- sector backdrop

### Valuation Extractor

Extracts:

- rating
- target price
- current market price used by broker
- upside/downside
- valuation method
- multiple and base year
- sum-of-the-parts components where present

### Estimate Extractor

Extracts forecast tables:

- revenue
- EBITDA
- PAT
- EPS
- margins
- ROE/ROCE
- debt/cash when available
- periods such as FY26E/FY27E/FY28E

### Risk Extractor

Extracts downside risks, sensitivity assumptions, and explicit broker caveats.

### Catalyst Extractor

Extracts order wins, margin triggers, policy triggers, product launches, capex, results, management guidance, and event timelines.

### Consensus Comparator

Compares all broker reports for the same symbol:

- rating spread
- target price range
- valuation multiple spread
- earnings estimate spread
- recurring catalysts
- recurring risks
- disagreements and contradictions

### Freshness Judge

Classifies reports as:

- current: latest result cycle or within configured freshness window
- stale but useful: older initiation/sector thesis still relevant
- superseded: newer report from same broker exists

### Evidence Grounder

Checks every synthesized claim against stored facts or page chunks. Unsupported claims must be removed or labeled as inference.

### Research Writer

Writes the final Deep Broker Research report with:

- source trail
- page citations
- broker comparison tables
- clear research-only disclaimer
- missing evidence section

## Deep Research Output

For `/deep-research BEL --brokers public`, the report should include:

1. Executive summary
2. Broker coverage map
3. Rating and target-price consensus
4. Valuation method comparison
5. Earnings estimate comparison
6. Key bull thesis points
7. Key bear thesis points
8. Catalysts and timeline
9. Risk map
10. Where brokers disagree
11. Agent Adda cross-check
    - latest technical setup
    - sector rotation
    - fundamentals cache
    - latest results
    - price/volume context
12. Evidence quality and freshness
13. Full source appendix

The report must not produce buy/sell advice. It should say what broker research indicates, what evidence supports it, and what remains uncertain.

## Commands

### `/broker-sources`

List active broker source registry rows and access status.

### `/broker-index SYMBOL`

Discover and index available public broker reports for one symbol.

Options:

```text
/broker-index BEL --broker icici
/broker-index BEL --all-public
/broker-index BEL --refresh
```

### `/broker-fetch SYMBOL`

Download and parse discovered reports.

Options:

```text
/broker-fetch BEL --limit 10
/broker-fetch BEL --broker hdfc
```

### `/broker-research SYMBOL`

Run extraction and broker comparison over stored reports.

### `/deep-research SYMBOL --brokers public`

Run full synthesis and publish markdown/html reports.

### `/report broker SYMBOL html`

Render the latest broker research run as an HTML report.

## Error Handling

- `login_required`: store blocked source; do not retry automatically.
- `http_error`: store status code and URL.
- `pdf_too_large`: skip and store size.
- `duplicate_pdf`: link existing report by hash.
- `parse_failed`: keep metadata and PDF path; report parse gap.
- `no_symbol_match`: keep discovered report only if broker/source metadata is useful.
- `llm_extract_failed`: keep deterministic facts and mark LLM extraction missing.
- `unsupported_claim`: block or remove claim from final report.

## Testing Strategy

Tests should avoid live broker network calls. Use fixtures.

Required tests:

- source registry seed creates expected rows
- ICICI index fixture extracts direct PDF links
- HDFC fixture extracts timestamped PDF links
- Axis fixture extracts downloadReport and image PDF links
- Sharekhan fixed newsletter sources are seeded
- duplicate PDF hash does not duplicate reports
- parser stores page chunks with page numbers
- deterministic target price/rating extractor works on fixture text
- LLM extractor prompt receives page-bounded chunks and returns source-grounded JSON
- consensus comparator identifies target-price spread and broker disagreement
- report writer includes source appendix and research-only disclaimer
- command router maps `/broker-index`, `/broker-research`, and `/deep-research`

## Phased Delivery

### Phase 1: PostgreSQL Registry and Discovery

Create broker source and report metadata tables. Seed ICICI, HDFC, Axis, Sharekhan, Trendlyne discovery sources. Implement fixture-backed discovery for one symbol.

### Phase 2: PDF Fetch and Parse

Download, hash, store, parse, and index PDFs into PostgreSQL page chunks.

### Phase 3: Structured Extraction

Implement deterministic and LLM extraction for rating, target price, valuation, estimates, thesis, risks, and catalysts.

### Phase 4: Broker Consensus

Compare broker reports for one symbol and store the comparison result.

### Phase 5: Deep Research Report

Publish markdown/html reports under `reports/broker_research/` and latest links under `reports/latest/`.

### Phase 6: Scheduled Market-Wide Crawl

Only after the single-stock path is stable, add scheduled crawling for public index pages and daily new-report ingestion.

## Non-Goals

- No login bypassing.
- No paid research scraping.
- No live trading advice.
- No hidden chain-of-thought.
- No LLM-only reports without stored evidence.
- No market-wide crawler in v1.

## Open Implementation Notes

- The existing `company_intel` PostgreSQL schema should be extended rather than creating another standalone SQLite database.
- The earlier Company X-Ray SQLite helpers are legacy and should be migrated before broker research uses them.
- Trendlyne should be treated as discovery metadata, not as the primary evidence source when a direct broker PDF is available.
- Broker report pages should be searchable through PostgreSQL full-text search.
- All final report claims should point back to `broker_report_pages` or `broker_research_facts`.
