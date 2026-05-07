# Financial Filing Intelligence Design

## Goal

Build an auditable Agent Adda capability that can analyze a company quarterly or annual financial filing from a direct PDF/XBRL/iXBRL link first, then later from NSE/BSE symbol discovery, and produce Markdown/HTML research reports grounded in extracted evidence.

## Scope

The first implementation is link-driven: the user provides a URL, optional symbol, and optional period. The system downloads and registers the filing, detects its type, stores a manifest, and creates stable interfaces for later PDF/XBRL parsing and LLM analysis. NSE/BSE auto-discovery, full parsing, and report generation are planned follow-on tasks but share the same storage and schemas.

Out of scope for the first slice:
- Bulk Nifty 500 earnings analysis.
- OCR for scanned documents.
- Paid data APIs.
- Investment recommendations or trading advice.

## Architecture

The feature is centered on `financial_filing_agent.py`, a focused module with deterministic functions:
- `detect_document_type()` classifies PDF, XBRL/XML, iXBRL/HTML, ZIP, or unknown artifacts.
- `ingest_filing_url()` downloads and registers a direct filing URL.
- `write_manifest()` persists an auditable manifest beside the raw file.
- Future parser functions consume the manifest and produce canonical facts and evidence maps.

The terminal agent and LLM layer should call these deterministic tools rather than reading arbitrary URLs directly. LLMs are only allowed to interpret canonical extracted facts plus evidence references.

## Storage Layout

All artifacts live under:

```text
data/filings/{SYMBOL_OR_UNKNOWN}/{PERIOD_OR_UNKNOWN}/
  raw/
    original filing files
  parsed/
    canonical_facts.json
    evidence.json
  analysis/
    analysis.json
    report.md
    report.html
  manifest.json
```

The manifest contains:
- symbol
- period
- source_url
- local_path
- sha256
- content_type
- document_type
- fetched_at
- status
- error

## Source Rules

Use XBRL/iXBRL as the source of truth for numeric facts when available. Use PDF extraction for human-readable notes, auditor language, management commentary, segment/product commentary, and page-level evidence. PDF-only facts are allowed but must be marked lower confidence until reconciled.

Every material number used in the final narrative must have a source reference:
- XBRL tag/context/unit, or
- PDF page/table/row/column.

If evidence is missing, the report must label the metric as unverified rather than silently promoting it to fact.

## Parser Strategy

XBRL/iXBRL parser:
- parse XML namespaces and inline facts
- preserve raw tags, context ids, units, decimals, period start/end
- map common labels to canonical fields

PDF parser:
- extract page text and tables
- keep page/table references
- return structured warnings if PDF extraction dependencies are unavailable
- defer OCR until a later task

## Analysis Strategy

The LLM analysis layer is decomposed into narrow roles:
- Numbers Analyst: QoQ/YoY/FY growth, margins, EPS.
- Balance Sheet Analyst: debt, cash, receivables, inventory, working capital.
- Cash Flow Analyst: PAT vs CFO, capex, FCF, cash conversion.
- Segment/Product Analyst: business segments, products, order book, commentary.
- Risk Analyst: auditor qualifications, exceptional items, contingencies, related-party items.
- Narrative Writer: final report using only verified facts and evidence references.

## Report Output

Reports should be generated under `reports/filings/` and include:
- executive summary
- financial snapshot table
- growth and margin analysis
- balance sheet quality
- cash flow quality
- segment/product commentary
- risks and watch items
- extracted evidence table
- source trail
- "Not investment advice. For research and learning only." disclaimer

## Testing

The feature is test-first. The initial tests should not hit the network; they mock downloader responses and assert classification, path safety, manifest shape, structured errors, and idempotency. Later parser tests use local fixtures for XBRL/iXBRL and PDF samples.

## Success Criteria

- A direct Blue Star financial-result PDF link can be ingested into the filing registry.
- Bad URLs and unsupported file types return structured errors.
- The first slice creates no dependency on LLMs, NSE sessions, or PDF parsing libraries.
- Future XBRL/PDF/LLM/report tasks can build on the same manifest and folder layout without changing public function signatures.
