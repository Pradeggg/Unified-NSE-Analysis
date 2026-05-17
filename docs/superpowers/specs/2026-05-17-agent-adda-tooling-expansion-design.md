# Agent Adda Tooling Expansion Design

Date: 2026-05-17
Owner: Agent Adda / Codex
Audience: implementation workers maintaining `terminal/tools.py`, `terminal/agent.py`, `nse_agent.py`, data loaders, reports, and tests
Primary output: a PostgreSQL-first, evidence-gated tool layer that improves routing, context handling, reports, latest-results analysis, Strategy Council evidence, and F&O workflows

## Goal

Agent Adda already has a broad tool registry, but live terminal testing exposed gaps in how tools are selected, validated, and reused across workflows. The next tooling phase should add missing first-class tools and wire them into the agent so answers do not fall back to unrelated symbols, stale data, generic market overviews, or unsupported conclusions.

This design covers the additional tools that should be included and how they should be wired.

## Problems To Solve

1. PostgreSQL is the intended primary data store, but failures can still appear as missing SQLite tables, yfinance fallback, or partial report evidence.
2. Latest results and filing intelligence are not consistently reusable across `/results`, Strategy Council, forensic analysis, Stock Sherlock, and reports.
3. Follow-up prompts such as `open the report`, `based on the report`, or `were these from last 30 mins` need explicit context tools before routing.
4. Symbol and entity resolution still allows wrong substitutions in some conversational paths.
5. F&O prompts that ask for option-chain, PCR, max pain, futures basis, and strategy can route to generic market overview when required F&O evidence is absent.
6. Final answer validation is improving, but evidence gating is not yet universal across every market conclusion.

## Design Principles

- PostgreSQL is primary for market data, intraday bars, evidence manifests, historical EOD, report metadata, and durable analysis state.
- SQLite may remain only for local FTS/cache features when PostgreSQL FTS is not yet available; every such boundary must be explicit.
- Tool output is evidence. LLM output is interpretation.
- Every conclusion must be traceable to executed tool evidence or rendered as missing evidence.
- If the situation assessment is unclear, ask one clarification question instead of guessing.
- Composite user workflows should call composite tools. Do not rely on the LLM to manually assemble low-level tool chains for F&O, latest results, Strategy Council, or report context.

## Tool Families

### 1. PostgreSQL Operations Tools

Add these tools first because they unblock all other reliability work:

| Tool | Purpose | Primary Consumers |
|---|---|---|
| `get_postgres_health` | Check process, DSN, socket, schemas, required tables, and row counts. | `/doctor`, `/data-status`, startup readiness |
| `ensure_postgres_schema` | Idempotently create or repair expected schemas and tables. | `/doctor --repair`, loader commands, tests |
| `audit_postgres_coverage` | Report historical EOD/intraday/fundamental/report coverage by table and symbol count. | `/data-status`, Strategy Council, data loaders |
| `load_historical_eod_to_postgres` | Load available historical EOD rows into `market.equity_eod`. | `/load historical`, setup/bootstrap |
| `load_intraday_ohlcv_to_postgres` | Load or seed intraday OHLCV bars into `intraday.ohlcv_bars`. | intraday routes, `/load intraday` |
| `get_data_source_manifest` | Return active data sources, freshness, fallbacks, and disabled legacy paths. | all report footers, evidence gating |

### 2. Latest Results And Filing Tools

Latest results should become a reusable evidence capability:

| Tool | Purpose | Primary Consumers |
|---|---|---|
| `discover_financial_filings` | Find latest NSE/BSE/company IR result filings. | `/results`, filing intelligence |
| `ingest_financial_filing` | Download/register filing artifacts with manifest metadata. | `/results`, `/filing`, reports |
| `parse_financial_filing` | Dispatch PDF/XBRL/iXBRL parsing. | latest-results pipeline |
| `parse_xbrl_filing` | Extract canonical tagged financial facts. | latest-results pipeline |
| `parse_pdf_filing` | Extract text/table evidence from PDFs. | latest-results pipeline |
| `reconcile_filing_facts` | Compare XBRL/PDF facts and mark verified/partial/conflict. | report generation |
| `get_latest_results` | Composite tool returning latest result evidence pack for one symbol. | `/results`, Strategy Council, Sherlock |
| `summarize_latest_results` | Render evidence-backed result summary without unsupported claims. | `/results`, reports |

### 3. Report Context Tools

Reports should be first-class artifacts, not incidental file paths:

| Tool | Purpose | Primary Consumers |
|---|---|---|
| `list_generated_reports` | List report paths, types, symbols, timestamps, and source workflow. | `/report`, context memory |
| `get_last_report` | Return the last generated report remembered by session state. | `open the report`, `based on the report` |
| `open_report` | Open or print a path to a generated report. | terminal command layer |
| `read_report` | Load markdown/html text and metadata from a report. | report follow-ups |
| `summarize_report` | Summarize an existing report with source and symbol preserved. | `based on the report` |
| `compare_reports` | Compare two reports for recommendation/evidence changes. | Strategy Council iteration review |

### 4. Situation Assessment Tools

The agent needs a pre-routing assessment layer:

| Tool | Purpose | Primary Consumers |
|---|---|---|
| `assess_user_situation` | Decide what the user is asking, whether context applies, and what plan is needed. | `terminal/agent.py` before normal routing |
| `resolve_conversation_reference` | Resolve `it`, `these`, `the report`, `same stock`, and numbered follow-ups. | follow-up routing |
| `resolve_entity_context` | Resolve current symbol/report/screener/F&O context. | all multi-turn prompts |
| `validate_intent_evidence_plan` | Check required tools before execution. | required-tool validation |
| `request_clarification` | Return one focused clarification question when confidence is low. | ambiguous prompts |

### 5. Symbol And Entity Resolution Tools

Wrong-symbol substitutions are a P0 defect:

| Tool | Purpose | Primary Consumers |
|---|---|---|
| `resolve_stock_entity` | Resolve exact NSE symbol, company name, alias, and prior-context entity. | all stock workflows |
| `resolve_company_alias` | Map names such as `United Spirits`, `USL`, and company display names to canonical symbols. | search/results/company workflows |
| `validate_requested_symbols` | Compare requested symbols against executed evidence. | final answer validator |
| `detect_non_symbol_terms` | Prevent indicators/topics such as `ADX`, `MA`, `RSI`, `results`, or `growth strategy` from becoming stock symbols. | symbol extraction |
| `resolve_index_or_stock` | Distinguish indices, derivatives underlyings, and equities. | `/fno`, `/index`, `/stock` |

### 6. Strategy Council Evidence Tools

The Strategy Council should not list available data as missing:

| Tool | Purpose | Primary Consumers |
|---|---|---|
| `build_strategy_council_evidence_pack` | Build the base point-in-time technical/eod evidence. | `/strategy-council` |
| `enrich_strategy_council_evidence` | Add fundamentals, market breadth, latest results, news/catalysts, sentiment. | `/strategy-council` |
| `validate_strategy_council_evidence` | Mark missing/partial/stale evidence with attempted sources. | report renderer |
| `score_strategy_data_readiness` | Produce a readiness score before LLM strategy proposal. | Strategy Council loop |

### 7. Composite F&O Tools

F&O user prompts require a composite evidence path:

| Tool | Purpose | Primary Consumers |
|---|---|---|
| `get_fno_overview` | Composite chain/futures/strategy evidence pack. | `/fno SYMBOL`, natural prompts |
| `get_option_chain_summary` | PCR, IV, top OI, OI change, volume, expiry metadata. | F&O overview |
| `get_max_pain` | Compute max pain from option-chain OI. | F&O overview |
| `get_pcr_summary` | Separate OI PCR, volume PCR, and change-in-OI PCR. | F&O overview |
| `get_top_oi_strikes` | Top call/put OI and build-up strikes. | F&O overview |
| `get_futures_basis` | Futures price, spot, basis, premium/discount. | F&O overview |
| `get_cost_of_carry` | Annualized cost-of-carry with expiry. | F&O overview |
| `recommend_options_strategy` | Recommend strategy only when required evidence exists. | final F&O answer |

### 8. Company Evidence Audit Tools

Company search must produce auditable gaps:

| Tool | Purpose | Primary Consumers |
|---|---|---|
| `audit_company_search` | Store query, alias, result count, parse status, and failure reason. | search/company workflows |
| `search_company_official_sources` | Search official IR/company/NSE/BSE sources first. | company X-Ray, latest results |
| `search_company_filings` | Find result filings, annual reports, presentations, transcripts. | company X-Ray |
| `promote_company_evidence_to_postgres` | Promote parsed evidence into durable PostgreSQL tables. | company evidence store |
| `get_company_evidence_coverage` | Report official/internal/external evidence coverage by category. | strict/permissive reports |

### 9. Evidence Gate Tools

Final answer safety belongs in a reusable layer:

| Tool | Purpose | Primary Consumers |
|---|---|---|
| `build_evidence_matrix` | Map claims to required evidence categories and executed tools. | answer/report renderers |
| `validate_answer_against_evidence` | Block unsupported claims before rendering. | final answer validator |
| `render_missing_evidence_block` | Standard missing-evidence section with attempted sources. | all market answers |
| `validate_required_tools_executed` | Confirm mandatory tools ran for the detected intent. | routing layer |

## Wiring Architecture

### Pre-Routing

`terminal/agent.py` should run situation assessment before keyword routing:

1. Normalize user input and numbered follow-ups.
2. Resolve prior conversation context.
3. Resolve entity context.
4. Build an evidence plan.
5. Ask clarification if confidence is low.
6. Route to deterministic command/tool flow only after the plan is valid.

### Tool Execution

`terminal/tools.py` can keep the registry, but large new families should live in focused modules:

- `terminal/postgres_tools.py`
- `terminal/results_tools.py`
- `terminal/report_context.py`
- `terminal/entity_resolution.py`
- `terminal/evidence_gate.py`
- `terminal/fno_composite.py`
- `terminal/company_evidence_tools.py`

`terminal/tools.py` should import and register wrappers so existing OpenAI tool schema generation remains stable.

### Final Rendering

Every market answer should pass through:

1. Required-tool validation.
2. Requested-symbol validation.
3. Evidence matrix validation.
4. Missing-evidence rendering when needed.
5. Report/context memory update when a report is generated.

## PostgreSQL Boundary

The new tooling should prefer PostgreSQL schemas:

- `market` for EOD historical price data.
- `intraday` for snapshots, OHLCV bars, futures, and scans.
- `report` for generated report metadata.
- `evidence` or `company_intel` for filings, search runs, documents, chunks, and structured facts.
- `strategy_council` for council runs and evidence references.

SQLite should not be the primary source for new durable evidence. If an existing SQLite FTS index is retained, it must be labeled as local search cache and backed by source metadata that can be promoted to PostgreSQL.

## Implementation Order

1. PostgreSQL operations tools.
2. Report context tools.
3. Situation assessment and entity resolution tools.
4. Latest results and filing tools.
5. Evidence gate tools.
6. Strategy Council evidence enrichment.
7. Composite F&O tools.
8. Company evidence audit tools.

This order fixes root causes before adding more dashboards or strategy features.

## Acceptance Criteria

- `/data-status` or `/doctor` reports PostgreSQL health, schemas, and coverage without silent SQLite fallback.
- `/results SYMBOL` and natural latest-results prompts use the same latest-results evidence pack.
- Strategy Council reports stop listing fundamentals/latest results as missing when those sources exist.
- `open the report` and `based on the report` resolve to the last generated report or ask clarification.
- F&O overview prompts require option-chain, PCR, max pain, futures basis, cost-of-carry, and expiry evidence.
- Wrong-symbol regressions such as `USL` resolving to an unrelated stock are blocked.
- Technical terms such as `ADX` and `MA` are not treated as requested stock symbols.
- Every unsupported technical, fundamental, catalyst, forensic, F&O, or strategy conclusion is blocked or rendered as missing evidence.

