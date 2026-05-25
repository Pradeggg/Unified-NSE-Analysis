# Backlog Archive

Auto-extracted **completed (✅ DONE)** items from `docs/BACKLOG.md`.
Items are grouped by the section they originated from. See git history
for chronological context. Generated: 2026-05-25 11:05.

---

## 0. HOW TO USE THIS DOCUMENT / Agent Adda Routing & Resolution Backlog — 2026-05-22

<details><summary>11 archived table rows</summary>

| Item |
|---|
| AA-HSR-1 Symbol Resolver Contracts • ✅ DONE • P0 • Codex • `terminal/symbol_search/schema.py`, `terminal/symbol_search/__init__.py`, `tests/test_hybrid_symbol_resolution.py` • Added `ResolveCandidate` and `ResolveResult` dataclasses with rich fields: `symbol`, `legacy_confidence`, `confidence_band`, normalized `score`, `raw_score`, `query`, `candidates`, `method`, `matched`, `needs_clarification`. Added projection helper so `terminal.tools.resolve_symbol()` can keep legacy `confidence` values, including the existing `near-match` compatibility path. Implementation commit: `f286b7a` on branch `aa-hsr-1-symbol-contracts`. • Hybrid symbol-resolution design approved. • Contract tests and existing symbol-resolution tests pass; legacy projection remains backward compatible; no current caller is forced to read `confidence_band`. |
| AA-HSR-2 Alias Source + Seed Flow • ✅ DONE • P0 • Copilot CLI • `terminal/symbol_search/alias_source.py`, `scripts/seed_symbol_aliases.py`, `tests/test_hybrid_symbol_resolution.py` • Added `terminal/symbol_search/alias_source.py` as a neutral module (no `terminal.tools` import — verified by `test_alias_source_does_not_import_terminal_tools`). Constants (`_FO_INDEX_ALIASES`, `_MANUAL_STOCK_ALIASES`, `_GENERIC_NAME_TOKENS`, sector hints) are duplicated here so the resolver can seed without a cycle; `terminal/tools.py` keeps its own copies until AA-HSR-4 collapses them. Weights match backlog: official 1.0 / symbol 0.9 / short 0.7 / alias 0.6 / sector_hint 0.5 / manual 0.9. `AliasRecord` dataclass validates kind/weight bounds. `iter_aliases()` dedupes on `(symbol, name, kind)` and rejects single-token generic names. Postgres source is `ref.instruments UNION ALL scores.mv_latest_snapshot` via `terminal.postgres_tools._connect()`; degrades gracefully when PG is unreachable. `scripts/seed_symbol_aliases.py` upserts with `ON CONFLICT (symbol, name, kind) DO UPDATE` (idempotent), supports `--dry-run`, `--skip-pg`, `--json`, and emits a per-kind/per-source summary. Exit codes: 0 success, 2 table missing (run AA-HSR-3 migration), 3 empty source, 4 db error. Branch `aa-hsr-2-alias-source`. • AA-HSR-1 contracts. • 14 new tests cover: no `terminal.tools` import cycle, locked kind weights, `classify_alias` heuristic, `AliasRecord` validation, manual+index+sector emission without PG, dedup, generic-token rejection, build_alias_map normalization, summary grouping, seed dry-run does not touch DB, empty-source exit code, missing-table exit code, happy-path upsert with ON CONFLICT, idempotency invariant on the SQL. |
| AA-HSR-3 Trigram Retriever v1 • ✅ DONE • P0 • Copilot CLI • `postgres/migrations/20260523_symbol_resolution_trgm.sql`, `terminal/symbol_search/trigram_index.py`, `tests/test_hybrid_symbol_resolution.py` • Added migration that creates `pg_trgm` extension, `market.symbol_aliases` table (PK `(symbol, name, kind)`, weight range CHECK, `kind` CHECK), GIN trigram index on `lower(name)`, and a btree on `symbol`. All objects use `IF NOT EXISTS` so the migration is idempotent. Added `terminal/symbol_search/trigram_index.py::lookup()` issuing a CTE-based parameterised query with locked ordering `weighted_score DESC, raw_score DESC, kind ASC, symbol ASC` (exported as `ORDER_BY_CLAUSE` constant). `MID_WORD_REJECT_BELOW = 0.25` filter rejects the mid-word coincidences that caused the GNA bug. Degrades silently to `[]` on: empty query, psycopg2 unavailable, `_connect()` failure, SQLSTATE 42883 / 42P01 / 42704 (missing extension / table / object), or empty result. Dedupes on `symbol`, keeping the highest-ranked alias name as `matched`. `benchmark()` helper returns p50/p95/max latency summary used by AA-HSR-5. Branch `aa-hsr-3-trigram-retriever`. • AA-HSR-2 alias source. • 13 new tests cover: blank query, PG unavailable, missing pg_trgm (42883), missing table (42P01), empty table, happy path with dedup on symbol, parameterised SQL (no string interpolation — verified with `'); DROP TABLE` payload), locked ORDER BY clause, negative top_n rejected, score clamped to [0,1], benchmark degraded summary, benchmark empty input, migration idempotency (every CREATE uses IF NOT EXISTS, GIN trgm_ops, matching PK). |
| AA-HSR-4 Resolver Integration Shim • ✅ DONE • P0 • Codex • `terminal/symbol_search/resolver.py`, `terminal/tools.py`, `terminal/agent.py`, `terminal/entity_resolution.py`, `tests/test_hybrid_symbol_resolution.py`, `tests/test_terminal_symbol_resolution.py`, `tests/test_terminal_agent_market_prompt.py` • Added the network-free `symbol_search.resolve()` entrypoint for dict, isolated typo/contraction, and trigram tiers. Rewrote `tools.resolve_symbol()` / `_resolve_local_symbol()` as projections over the hybrid resolver while preserving NSE live search and quote fallback. Removed the old broad contains-match and broad `SequenceMatcher` canonicalization path from `terminal/tools.py`. Added score / confidence-band propagation through legacy tool and entity-resolution payloads. Updated `_primary_symbol_query` to trust `score >= 0.85` or `confidence_band in {"exact","high"}` and to recover explicit ticker tokens from noisy preposition phrases. Added DIXON TECH / DIXON TECHNOLOGIES aliases for the observed F&O + intraday compound prompt. • AA-HSR-1 through AA-HSR-3. • Existing symbol-resolution tests pass unchanged; new HSR-4 coverage verifies hybrid projection fields and low-confidence prose matches are not promoted; routing tests confirm the DIXON F&O + 5m intraday prompt routes to DIXON, not NIFTY. |
| AA-HSR-5 Resolver Eval + Telemetry • ✅ DONE • P0 • Codex • `tests/fixtures/symbol_resolution/in_vocab.jsonl`, `tests/fixtures/symbol_resolution/adversarial.jsonl`, `tests/test_hybrid_symbol_resolution.py`, `terminal/symbol_search/telemetry.py`, `terminal/symbol_search/resolver.py` • Added checked-in JSONL eval fixtures with 200+ in-vocab cases and 50 adversarial cases. Added deterministic eval tests that run with trigram disabled and `include_pg=False`, enforcing top-1 recall >= 98% and adversarial false-symbol rate <= 2%. Added structured telemetry emission to `logs/symbol_resolution.jsonl` with query, winner, method, score, raw score, confidence band, legacy confidence, candidates, latency, fallback reason, and clarification flag. Telemetry is enabled at runtime by default, can be disabled with `NSE_SYMBOL_RESOLUTION_TELEMETRY=0`, and is disabled under pytest unless explicitly enabled with a temp path. • AA-HSR-4 integration. • In-vocab fixture eval passes; adversarial eval passes; telemetry unit and resolver-integration tests pass without polluting repo logs. |
| AA-UR-1 Route Decision Contracts • ✅ DONE • P0 • Codex • `terminal/router/schema.py`, `terminal/router/__init__.py`, `tests/test_unified_router.py` • Added typed route objects: `RouteDecision`, `RouteCandidate`, `ContextBinding`, `EvidenceRequirement`, `ToolCallSpec`, `NextOption`, `SourcePolicy`, `RouteReasoningSummary`, `RouteValidation`. Route types: `direct_tool_plan`, `contextual_answer`, `clarification`, `compound_plan`, `fallback_llm`, `blocked_ungrounded`. Implementation commit: `4144e30` on branch `aa-ur-1-route-decision-contracts`. • Unified router design approved. • Contract tests prove serialization/debug trace, route type validation, next-option binding shape, and tool-plan representation. |
| AA-UR-2 Context Pack + PostgreSQL Memory • ✅ DONE • P0 • Memory assistant • `terminal/router/context.py`, `terminal/conversation_memory.py`, `postgres/migrations/20260525_agent_context.sql`, `tests/test_conversation_memory.py`, `tests/test_unified_router.py` • Added `ContextPack` dataclass with recent turns (depth 5), `active_symbols`, `active_indices`, `active_sectors`, `active_reports` (path/type/symbol), `active_workflow` (multi-step), `pending_options`, `source_trails`, and `freshness`. Extended `ConversationMemory` with `register_report`, `start_workflow` / `append_workflow_step` / `close_workflow`, `register_pending_options` / `consume_pending_option`, `record_source_trail`, and `build_context_pack(depth=5)`. Snapshot persists every structured field; new `agent_context` schema in `postgres/migrations/20260525_agent_context.sql` provides queryable tables for `active_workflows`, `active_reports`, `pending_options`, and `source_trails`. Branch: `aa-ur-1-and-2-cherry-pick`. • Existing `terminal/conversation_memory.py` foundations. • All four acceptance criteria covered by tests: five-step Sherlock workflow stores structured per-step evidence; reports are addressable by path/type/symbol via `ContextPack.report_for(...)`; snapshot round-trip restores workflows, reports, pending options, and trails; workflow evidence carries explicit `fact`/`value`/`source_label` keys independent of any prose summary. 23/23 new + carry-over router tests green; full target suite (`test_unified_router.py` + `test_conversation_memory.py` + `test_terminal_agent_market_prompt.py`) 129/129. |
| AA-UR-3 Unified Router Wrapper • ✅ DONE • P0 • Router assistant • `terminal/router/router.py`, `terminal/router/providers.py`, `terminal/router/__init__.py`, `tests/test_unified_router.py` • Added `UnifiedRouter.route(user_input, context_pack) -> RouteDecision` as a side-effect-free additive shim. Implemented all seven providers as the `RouteProvider` Protocol: `PendingOptionProvider`, `ContextualFollowupProvider`, `EntityTopicProvider`, `ReportProvider`, `VisualScanProvider`, `MarketSituationProvider`, `DirectIntentProvider`. Router runs every provider, sorts candidates by `(score DESC, registration_index ASC)`, isolates provider exceptions into rejected-branch entries, projects the winner into a `RouteDecision` with a `ContextBinding` derived from the `ContextPack` and a `RouteReasoningSummary` carrying the selected branch + rejected branches. `terminal/situation_assessment.py` and `terminal/agent.py` are deliberately untouched — wiring lands in AA-UR-4..7. Branch: `aa-ur-3-router-wrapper`. • AA-UR-1, AA-UR-2. • Existing routing tests untouched (situation_assessment + market prompt + memory: 206/206 green). Route trace returns provider, score, context binding, and winning reason via `RouteDecision.to_debug_trace`. Pending option replies execute bound actions without symbol re-resolution: a label like `A` resolves directly to the prior `bound_action.tool_plan` with the original symbols, validated by `test_pending_option_provider_short_circuits_without_symbol_resolution`. |
| AA-UR-4 Compound Stock Provider • ✅ DONE • P0 • Router assistant • `terminal/router/compound_stock.py`, `terminal/router/providers.py`, `terminal/router/router.py`, `terminal/router/__init__.py`, `tests/test_unified_router.py` • Added `CompoundStockProvider` that detects compound single-stock asks (>=2 of live-quote / F&O / intraday facets), resolves the target symbol via the hybrid resolver (`terminal.symbol_search.resolve`) with sliding 3→2→1 token windows over content tokens (stop-tokens stripped), and emits a `compound_plan` `RouteCandidate` (score 0.95) with the five-tool plan `resolve_symbol`, `get_live_quote`, `get_fno_overview`, `explain_intraday_setup`, `get_intraday_analysis`. `get_fno_overview` is flagged `optional=True` so F&O unavailability never strips live/intraday evidence. Index tickers (NIFTY/BANKNIFTY/etc.) are explicitly down-ranked vs. stock matches so the router never falls back to NIFTY. Wired into `DEFAULT_PROVIDERS` after PendingOption and ContextualFollowup. Router now merges any `symbol` arg from the winning tool plan into `ContextBinding.symbols` so the binding reflects the resolved subject even when the pack started empty. `terminal/agent.py` untouched — execution-time F&O availability check lands with AA-UR-5. Branch: `aa-ur-4-compound-stock-provider`. • AA-HSR-4 for robust symbol resolution; AA-UR-3 wrapper. • Target prompt `live pricies for dixon tech and the analysis of the F&O data and intraday tradesetup in 5 mins` routes to DIXON (`test_compound_dixon_prompt_routes_to_dixon_not_nifty`); F&O is kept optional and never strips other evidence (`test_compound_provider_marks_fno_as_optional_evidence`); a stock match beats NIFTY when both appear (`test_compound_provider_prefers_stock_over_nifty_when_both_match`); when no symbol resolves the provider returns a `clarification` candidate rather than defaulting to NIFTY. 216/216 in target suite. |
| AA-UR-5 Route Validation + Executable NEXT OPTIONS • ✅ DONE • P0 • Router/QA assistant • `terminal/router/validation.py`, `terminal/router/router.py`, `terminal/router/providers.py`, `terminal/router/__init__.py`, `tests/test_unified_router.py` • Added `terminal/router/validation.py` with `validate_decision`, `enforce_validation`, `filter_invalid_options`, and `match_option_reply`. `validate_decision` checks: (a) every tool exists in `terminal.tools.TOOL_REGISTRY`, (b) all `required` args from each tool's JSON schema are present and non-empty, (c) direct/compound routes have a non-empty tool plan, (d) symbols never bind only to indices (catches silent NIFTY fallback at validation time, complementing AA-UR-4), (e) every non-optional `EvidenceRequirement` on a compound route is covered by at least one tool in the plan, (f) report paths on report-recall routes exist on disk, (g) every NEXT OPTION's `bound_action` carries either an intent or a tool_plan referencing only known tools with all required args. `enforce_validation` strips broken NEXT OPTIONS (appending drop reasons to `reasoning_summary.rejected_branches`) and rewrites still-invalid direct/compound routes to `blocked_ungrounded` (clearing tool_plan, dropping confidence to `low`, preserving the original selected_branch so the audit trail survives). `match_option_reply` matches user replies against label (case-insensitive, accepts `A`/`A.`/`A)`/`1`) and full option text. Router (`terminal/router/router.py`) now calls `enforce_validation` on every decision before returning, so unknown tools and missing args are caught before any user-visible output. Providers from AA-UR-3 (`EntityTopic`, `VisualScan`, `MarketSituation`, `DirectIntent`) updated to bind real TOOL_REGISTRY entries (`search_yahoo_finance`, `get_technical_setup`, `analyze_mtf`, `get_live_quote`, `run_visual_scan`, `scan_intraday_market`) so default routes now pass validation; `DirectIntentProvider` emits a clarification when the requested topic has no symbol context, rather than executing with missing args. Branch: `aa-ur-5-route-validation`. • AA-UR-1 through AA-UR-4. • All four acceptance points covered by tests: unknown tools + missing args caught before display (`test_validate_decision_flags_unknown_tool`, `..._missing_required_arg`, `..._empty_string_required_arg`); invalid options suppressed or route rewritten to `blocked_ungrounded` (`test_enforce_validation_rewrites_invalid_direct_route_to_blocked_ungrounded`, `..._strips_broken_next_options_and_keeps_route`); `A` / `A.` / `A)` / `1` / full text execute the prior bound route (`test_match_option_reply_handles_label_and_text_and_punctuation`); compound coverage gap caught at validation time (`test_validate_compound_evidence_coverage`). 230/230 in full target suite. |
| AA-UR-7 Sherlock / Multi-Step Workflow Binding • ✅ DONE • P0 • Workflow assistant • `nse_agent.py`, `terminal/router/providers.py`, `terminal/router/router.py`, `tests/test_unified_router.py` • Wired the Sherlock-style RIC runs into the structured workflow context: `_remember_ric_sequence_interaction` in `nse_agent.py` now calls `memory.start_workflow(...)`, appends one `WorkflowStep` per RIC step with structured evidence (explicit `fact` / `value` / `symbol` / `source_label` / `freshness` / `tools` keys — never sourced only from prose), and calls `close_workflow(...)`. `ContextualFollowupProvider` (`terminal/router/providers.py`) detects `ContextPack.active_workflow` and binds follow-ups to the **full** workflow rather than the most recent turn: route intent switches to `contextual_followup_workflow`, route reasons enumerate every step kind and the workflow's symbol set, optional `EvidenceRequirement` entries are emitted per unique step kind so synthesis can audit per-facet coverage, freshness divergence across steps is surfaced, and conflicting `stance` values across step evidence are flagged. `_binding_from_pack` in `terminal/router/router.py` merges `ActiveWorkflow.symbols` into the route binding so follow-ups against a workflow always carry the full subject set, even when `last_focus_symbols` only retained the final step. Workflow registration is best-effort (wrapped in try/except) so a memory-snapshot failure never breaks the RIC user experience. Branch: `aa-ur-7-sherlock-workflow-binding`. • AA-UR-2 context pack. • MANINDS-style Sherlock follow-up sees live quote, technicals, fundamentals, news, and trade-setup evidence (`test_ur7_contextual_followup_binds_to_full_workflow`); workflow symbols flow into the route binding even when the pack started empty (`test_ur7_router_binding_includes_workflow_symbols`); freshness divergence across steps is surfaced in route reasons (`test_ur7_followup_flags_freshness_divergence`); contradicting bullish/bearish stances are reported back to the user (`test_ur7_followup_flags_conflicting_stances`); when no workflow is active, the legacy followup path is preserved (`test_ur7_followup_falls_back_when_no_workflow`). 433/433 in full e2e regression suite. |

</details>

## 0. HOW TO USE THIS DOCUMENT / Sprint 1 Status (2026-05-02)

<details><summary>14 archived table rows</summary>

| Item |
|---|
| P0-1 Signal Performance Logger • ✅ DONE • Claude • `_log_signals()` in `sector_rotation_report.py`; `resolve_signals.py` |
| P0-2 A+ Setup Classification • ✅ DONE • Claude • `_classify_setup()`, `SETUP_CLASS` column + badge in HTML |
| P0-3 Entry/Stop/Target Levels • ✅ DONE • Claude • `_compute_entry_levels()`, `ENTRY_LOW/HIGH/STOP_LOSS/TARGET_1/TARGET_2` |
| P0-4 Consolidate Data Sources • ✅ DONE • Optimus • Single cache `_sector_rotation_fund_cache.csv`; legacy sources removed; `scripts/migrate_fund_cache.py` |
| P1-1 Market Regime Detector • ✅ DONE • Claude • `regime_detector.py`; regime banner in HTML; signal log records regime |
| P1-2 F&O OI + PCR Signals • ✅ DONE • Optimus • `fetch_fno_data.py`; PCR/OI/MaxPain/Buildup/Composite signal; F&O badge in HTML |
| P1-3 FII/DII Flow Signals • ✅ DONE • Optimus • `fetch_fii_dii_flows.py`; flow banner in HTML; LLM narrative context; signal log |
| P1-4 Promoter/Insider Alerts • ✅ DONE • Optimus • `fetch_insider_alerts.py`; bulk/block/PIT/pledge alerts; insider badge in HTML; LLM narrative context; signal log |
| P1-5 Enhanced HTML Dashboard • ✅ DONE • Optimus • Paired-row sort, localStorage state, narrative search, heatmap toggle, print/PDF, 15-col mobile responsive |
| P1-6 Macro-Economic Proxy Signals • ✅ DONE • Optimus • `fetch_macro_proxies.py`; FRED+NSE data (9 indicators); z-score signals; 23-sector tailwind scoring; macro banner + rotation table Macro column in HTML; LLM narrative context |
| P2-1 NSE Knowledge Graph • ✅ DONE • Optimus • `knowledge_graph.py`; 1574 nodes, 8.4K edges; promoter groups (23), sector peers, supply chain; BFS shock propagation; GRAPH_SIGNAL column (BENEFICIARY/AT_RISK/WATCH); graph badge in signals popup; LLM cross-impact context |
| P2-4 Portfolio-Aware Narratives • ✅ DONE • Optimus • `_load_portfolio()` from CAS holdings; Portfolio tab (sector concentration, held-in-rotation table); "📁 Held" badge on candidates; LLM prompt enriched with holdings context + portfolio-specific instructions |
| P3-2 Voice Briefing • ✅ DONE • Optimus • `generate_voice_briefing.py`; GPT TTS MP3 path should use `gpt-4o-mini-tts` with macOS `say` AIFF fallback; reads signal_log + regime + flows; `/voice` slash command in nse_agent.py |
| P3-5 Intraday Single-Stock Fallback • ✅ DONE • Codex • `/intraday <stock>` now resolves the actual stock symbol, reads PostgreSQL `intraday.ohlcv_bars` first, seeds PostgreSQL from yfinance when bars are absent, then clearly labels Yahoo Finance candle history as fallback context; fallback is research-only |

</details>

## 0. HOW TO USE THIS DOCUMENT / Backlog Reconciliation — 2026-05-17

<details><summary>6 archived table rows</summary>

| Item |
|---|
| R1 PostgreSQL Operations Doctor • ✅ DONE • P0 • `terminal/postgres_tools.py`, `terminal/data_readiness.py`, `nse_agent.py`, `tests/test_postgres_tools.py`, `tests/test_data_readiness.py` • Added first-class PostgreSQL health checks for DSN, host/socket path, socket existence, `pg_isready`, required schemas, required tables, row counts, migration status, and actionable repair commands. `/doctor --repair` runs idempotent core schema repair before rechecking health. • `/doctor` reports PostgreSQL running/stopped, `/tmp` socket readiness, schema/table readiness, row counts, migration status, and next action without silently falling back to SQLite. Focused tests pass and local smoke output reports required schemas/tables ready. |
| R6.1 resolve_symbol NSE quote-equity fallback • ✅ DONE • P0 • `terminal/tools.py` • When NSE `/api/search` returns 5xx (frequent) for ticker-shaped queries, fall back to `/api/quote-equity` for direct resolution; remove premature early-return so VALUEIND/BLUEBLENDS/AIFL-class small-caps not in local DB still resolve; extend `_CONCEPT_TOKENS` with calendar/event tokens (DUE, TOMORROW, REPORTING, UPCOMING, EARNINGS, etc.) so they aren't treated as tickers. • Tickers absent from local DB resolve cleanly via `confidence=nse-quote`; concept tokens are rejected; 74/74 prompt-routing regression tests pass. |
| R10 Market-wide latest results feed • ✅ DONE • P0 • `terminal/tools.py`, `terminal/agent.py` • `get_latest_results_feed()` backed by NSE `corporates-financial-results` JSON (cached 30 min) with screener.in `/results/latest` fallback and window-fallback note when no recent filings. New `results_feed` intent + routing block (placed before symbol-routing) for "latest results", "who reported", "companies that announced results", etc.; corresponding render branch produces a tabular feed with XBRL filing links. Tool registered in `TOOL_REGISTRY`. • "who reported results this week", "latest results", "companies that announced results" render the market-wide feed with source trail; symbol-specific queries ("latest INFY results") still route to stock_results. 74/74 routing tests pass. |
| R11 Forthcoming-results event calendar • ✅ DONE • P1 • `terminal/tools.py`, `terminal/agent.py` • New `get_forthcoming_results(days_ahead, limit)` tool backed by NSE `/api/event-calendar?index=equities` (cached 30 min), filtered to purposes containing "Financial Results", sorted earliest-first with in-window vs upcoming-total counts and window-fallback note. New `forthcoming_results` intent + routing block (placed before generic event_calendar) catches "results due", "who is reporting", "forthcoming results", "upcoming earnings", etc.; dedicated render branch produces a results-only table with date / symbol / company / purpose. Tool registered in `TOOL_REGISTRY`. • "results due this week" / "who has results tomorrow" / "upcoming results" return company-level forthcoming-results table (NSE feed: 402 in next 7 days, 551 upcoming total) with source trail; generic event_calendar prompts still route to `get_event_calendar_summary`. 75/75 routing tests pass. |
| R12 Strategy Council Enhancement Backlog • ✅ DONE • P0 • `backtesting/strategy_council/ENHANCEMENT_ROADMAP.md`, `backtesting/strategy_council/IMPLEMENTATION_BACKLOG.md`, `docs/BACKLOG.md` • Added a current-state Strategy Council roadmap plus an actionable backlog of items that are not yet fully implemented. The roadmap separates implemented foundation from remaining evidence, critic, dashboard, strategy-generation, analysis, scale, and operations work. • Central backlog links to the detailed roadmap/backlog and the Strategy Council section below no longer treats already-wired enhancement foundations as future-only work. |
| R9 Agent Adda Tooling Expansion Backlog • ✅ DONE • P0 • `docs/superpowers/specs/2026-05-17-agent-adda-tooling-expansion-design.md`, `docs/superpowers/plans/2026-05-17-agent-adda-tooling-expansion-backlog.md` • Comprehensive design and implementation backlog for PostgreSQL operations tools, latest-results tools, report context tools, situation assessment v2, entity resolution, Strategy Council evidence enrichment, composite F&O tools, company evidence audit, and universal evidence gates. • Spec and backlog exist, list tool families, wiring points, file ownership, phased implementation tasks, tests, and end-to-end scenarios. |

</details>

## 0. HOW TO USE THIS DOCUMENT / Backlog Reconciliation — 2026-05-19

<details><summary>2 archived table rows</summary>

| Item |
|---|
| R0.1 Central Status Semantics • ✅ DONE • P0 • `docs/BACKLOG.md` • Updated the status legend so `DONE` is no longer sector-report-specific and added `PARTIAL` for foundations that exist but are not fully wired. Updated the missing-data rule to distinguish graceful report generation from claim blocking. • Future backlog rows can represent non-sector features accurately, and missing evidence cannot be treated as permission to make unsupported claims. |
| SC-CANON Strategy Council Backlog Ownership • ✅ DONE • P0 • `docs/BACKLOG.md`, `backtesting/strategy_council/IMPLEMENTATION_BACKLOG.md` • Central backlog keeps only summary rows and links to the dedicated Strategy Council implementation backlog as the canonical source for detailed SC work. • New Strategy Council implementation work is tracked in `backtesting/strategy_council/IMPLEMENTATION_BACKLOG.md`; central rows only summarize priority and dependency posture. |

</details>

## 0. HOW TO USE THIS DOCUMENT / Agent Model Benchmark Remediation Backlog — 2026-05-12

<details><summary>2 archived table rows</summary>

| Item |
|---|
| L1 Symbol extraction guardrail • ✅ DONE • P0 • `terminal/agent.py`, `terminal/tools.py`, `tests/test_terminal_agent_market_prompt.py`, `tests/test_terminal_symbol_resolution.py` • Prefer explicit NSE-like uppercase tickers over prose labels; never route common task words like `Teach`, `Peer`, `End-to-end`, `Earnings`, `Answer`, or `Overview` as symbols; block fuzzy substitution for exact ticker-looking queries when no exact local symbol exists. • Benchmark cases for `TCS`, `THERMAX`, `NAVABUPA`, `DMART/TRENT/VBL`, and market education route to the intended tools and never substitute unrelated tickers. |
| L4 Multi-turn entity memory • ✅ DONE • P0 • `terminal/agent.py`, `tests/test_terminal_agent_market_prompt.py` • Store the last resolved symbols from deterministic and LLM tool traces. Resolve follow-up pronouns such as `it`, `this stock`, and `that stock` before intent routing. • After `Analyze WELCORP`, `compare it with NAVABUPA` routes to `compare_stocks(["WELCORP", "NAVABUPA"])` and does not treat `it` as a symbol. |

</details>

## 0. HOW TO USE THIS DOCUMENT / Strategy Council Simulation Backlog — 2026-05-14

<details><summary>49 archived table rows</summary>

| Item |
|---|
| SC0 Strategy Council Design + Implementation Backlog • ✅ DONE • P0 • `docs/superpowers/plans/2026-05-14-strategy-council-simulation-backlog.md` • Defines the iterative strategist → deterministic backtest → data/leakage critic → market/risk critic → strategist revision loop for single-stock EOD strategy research across 1w/2w/4w horizons. • Backlog contains product contract, guardrails, package layout, TDD tasks, command integration, report generation, docs update, and verification steps. |
| SC1 Strategy Council Contracts • ✅ DONE • P0 • `backtesting/strategy_council/types.py`, `tests/test_strategy_council_types.py` • Added dataclasses for council config, evidence pack, constrained strategy specs, critiques, iterations, slice results, and final council result. • Unit tests prove default horizons, iteration count, audit fields, missing-data capture, and critique structure. |
| SC2 Evidence Pack Builder • ✅ DONE • P0 • `backtesting/strategy_council/evidence.py`, `tests/test_strategy_council_evidence.py` • Built point-in-time stock evidence from local EOD data, including archived EOD fallback history; explicitly marks missing fundamentals, news, sentiment, market breadth, and latest results. • Evidence pack returns latest close/volume/as-of date, bar count, source trail, and missing optional evidence. |
| SC3 Strategy DSL + Split Discipline • ✅ DONE • P0 • `backtesting/strategy_council/dsl.py`, `splits.py`, tests • Compiles strategist proposals into constrained, non-executable strategy specs and enforces time-based train/validation/test splits. • Unsafe/free-form code is rejected; test split is kept separate from train/validation. |
| SC4 Deterministic Candidate Runner • ✅ DONE • P0 • `backtesting/strategy_council/runner.py`, `tests/test_strategy_council_runner.py` • Runs strategy specs against train/validation/test slices using deterministic EOD backtest tools; executes `stage2` and marks unsupported registered strategies explicitly. • Results include split, strategy, horizon, metrics, and trade count; no LLM-calculated returns. |
| SC5 Strategist + Critic Interfaces • ✅ DONE • P0 • `backtesting/strategy_council/llm.py`, `tests/test_strategy_council_loop.py` • Added injectable strategist and critic interfaces, deterministic rule-based fallbacks, and structured JSON LLM adapters for strategist plus two critics. • Tests use deterministic fakes/fallbacks; critics detect low trade count and premature test exposure. |
| SC6 Iterative Council Orchestrator • ✅ DONE • P0 • `backtesting/strategy_council/council.py`, loop tests • Runs iterations where strategist proposes, train/validation backtests run, critics challenge, strategist receives revision instructions, then a final locked strategy is tested once on held-out test data. • Tests prove iteration count, final lock, one-shot test, and valid recommendation values. |
| SC7 Report + Terminal Command • ✅ DONE • P1 • `backtesting/strategy_council/report.py`, `terminal/strategy_council.py`, `nse_agent.py`, tests • Exposes `/strategy-council SYMBOL` and writes Markdown reports under `reports/strategy_council/`; supports `--llm` for configured LLM strategist/critics. • Terminal output includes recommendation, locked strategy, iteration count, report path, and research-only language. |
| SC8 Capabilities Documentation • ✅ DONE • P2 • `docs/AGENT_ADDA_CAPABILITIES.md` • Added command reference and guardrails for Strategy Council Simulation. • Documentation includes `/strategy-council` examples, loop explanation, and non-advice guardrails. |
| SC9 PostgreSQL Council Persistence • ✅ DONE • P1 • `backtesting/strategy_council/postgres_storage.py`, `terminal/strategy_council.py`, `tests/test_strategy_council_postgres_storage.py`, `tests/test_nse_agent_strategy_council.py` • Added optional `/strategy-council ... --persist` support that creates the `strategy_council` PostgreSQL schema and stores council runs, iterations, candidates, critiques, split results, final recommendation, and report path. • Tests prove schema creation, normalized row fan-out, and terminal persistence output. |
| SC10 Evidence Pack Enrichment Foundation • ✅ DONE • P0 • `backtesting/strategy_council/evidence_enrichment.py`, `backtesting/strategy_council/evidence.py`, `backtesting/strategy_council/council.py`, tests • Adds optional enrichment layers for market regime, relative/factor exposure, and microstructure context while preserving point-in-time evidence and explicit missing-data accounting. • Council runs can include enriched regime/factor/microstructure fields without fabricating missing fundamentals, news, sentiment, or latest-results evidence. |
| SC11 Strategy Council Enhancement Roadmap + Implementation Backlog • ✅ DONE • P0 • `backtesting/strategy_council/ENHANCEMENT_ROADMAP.md`, `backtesting/strategy_council/IMPLEMENTATION_BACKLOG.md` • Documents 50+ possible improvements, filters them into an actionable not-yet-implemented backlog, and records implementation patterns for new evidence dimensions, critics, and dashboard sections. • Roadmap identifies current baseline, prioritizes next work, and provides concrete backlog items with scope, files, and acceptance criteria. |
| SC12 Rule Composition + Composite Strategist • ✅ DONE • P1 • `backtesting/strategy_council/strategy_generator.py`, `backtesting/strategy_council/rule_composed_engine.py`, `backtesting/strategy_council/runner.py`, `backtesting/strategy_council/types.py`, tests • Adds rule-composed strategy generation and deterministic execution so the council can test more than a single hard-coded strategy family. • Council candidates can include composed rule strategies and runner output remains deterministic, auditable, and split-aware. |
| SC13 Advanced Critics Foundation • ✅ DONE • P1 • `backtesting/strategy_council/critics_advanced.py`, `backtesting/strategy_council/council.py`, tests • Adds configurable advanced critics for robustness beyond the base data/leakage and market/risk checks. • Advanced critic verdicts appear in council iterations when enabled and do not replace required base critique guardrails. |
| SC14 Strategy Council HTML Dashboard Foundation • ✅ DONE • P1 • `backtesting/strategy_council/dashboard_generator.py`, `backtesting/strategy_council/council.py`, `reports/dashboards/`, tests • Generates richer HTML dashboards for council runs, including strategy results and enhanced review sections. • `/strategy-council` can produce a dashboard artifact alongside the Markdown report without weakening the research-only framing. |
| B1 Cross-Index Breadth Dashboard • ✅ DONE • Codex • `index_intelligence.py`; standalone HTML/CSV; breadth strip in sector report |
| F0 Filing Intelligence Design + Implementation Plan • ✅ DONE • Codex • Design spec + implementation plan created for XBRL-first, evidence-grounded filing analysis |
| F1 Filing Registry + Direct Link Ingestion • ✅ DONE • Codex • `financial_filing_agent.py`; direct URL ingestion, document type detection, manifest, idempotency, Blue Star PDF smoke tested |
| F4 Multi-Page PDF Extractor + Evidence Map • ✅ DONE • Codex • PyMuPDF page text + detected table extraction with page/table/cell evidence trail; Blue Star PDF parsed |
| G0 US/Global Market Intelligence Design • ✅ DONE • Codex • Design spec created for phased US indices, ETFs, stocks, screeners, India read-through, terminal/report integration |
| G1 US Universe + yfinance Cache • ✅ DONE • Codex • `global_market_intelligence.py`; curated US/global universe, yfinance-compatible OHLCV normalization, daily cache, latest snapshot |
| G2 US Technical Engine + RS • ✅ DONE • Codex • `compute_technical_metrics()`; returns, SMA, RSI, MACD, 52W distance, support/resistance, VCP, Stage 2, RS vs SPY/QQQ |
| G3 US Screeners • ✅ DONE • Codex • Stage 2 leaders, VCP setups, sector ETF rotation, risk dashboard built on `compute_technical_metrics()` |
| G4 India Read-Through Engine • ✅ DONE • Codex • `build_india_readthrough()` maps Nasdaq, semis, crude, DXY, VIX/credit/Russell and financials/gold signals to NSE sector implications |
| G5 US/Global HTML Report • ✅ DONE • Codex • `render_us_market_report()` writes dated/latest HTML with summary, screeners, read-through, freshness, disclaimer |
| G6 Terminal + NLP Integration • ✅ DONE • Codex • `/us`, `/us indices`, `/us sectors`, `/us stage2`, `/us vcp`, `/us stock`, `/global readthrough` direct terminal routes |
| G7 Sector Report Global Tab • ✅ DONE • Codex • Global / US tab in sector report links latest standalone report and summarizes cache-only regime, ETF rotation, Stage 2, VCP, and India read-through |
| H0 Company + Sector X-Ray Design + Backlog • ✅ DONE • Codex • Company-first, sector-expanded evidence DB and RIC design. See `docs/superpowers/specs/2026-05-10-company-sector-xray-intelligence-design.md` and `docs/superpowers/plans/2026-05-10-company-sector-xray-intelligence-backlog.md` |
| H8 `/company-xray` + `/ric company-xray` Integration • ✅ DONE • Codex • Added `/company-xray` backend/terminal route, coverage/report summary, research disclaimer, and 9-step `/ric company-xray` workflow |
| H10 Company Website Index Schema + FTS • ✅ DONE • Codex • Added website crawl/index tables and SQLite FTS5 search foundation in `company_intelligence_db.py`; fixture tests pass |
| H11 Company Website Crawler Foundation • ✅ DONE • Codex • Added same-domain crawl, relative URL normalization, document-link discovery, HTML text chunking, and FTS search in `company_website_indexer.py` |
| H12 Broadened Search Verticals • ✅ DONE • Codex • Expanded `company_intelligence_search.py` with website/IR, annual report, presentation, transcript, customer, market share, competitor, RBI, and Budget query plans |
| H13 Real Website Fetcher + Crawl Safety • ✅ DONE • Codex • Added timeout/max-byte protected fetcher, structured network errors, robots.txt checks, sitemap URL discovery, and opt-in crawl seeding/robots enforcement |
| H14 Linked Document Download + Parsing • ✅ DONE • Codex • Added idempotent linked document download into `source_documents`, optional crawl-time persistence, and PDF parse promotion via the filing parser |
| H15 `/company-index` Backend Command • ✅ DONE • Codex • Added backend runner, terminal route, command parsing, bounded document download, and DMart SPA/API adapter for official investor files |
| H16 Website Index to Evidence Promotion • ✅ DONE • Codex • Added indexed website/source-document promotion into `evidence_chunks` and wired `/company-xray` to consume promoted official evidence |
| H17 Scheduled/Stale Company Index Job • ✅ DONE • Codex • Added backend stale-index job with stale/fresh selection, max-company limit, refresh override, failure recording, and continuation across symbols |
| I0 Voice Copilot Design + Implementation Backlog • ✅ DONE • Codex • Push-to-talk first, realtime later. See `docs/superpowers/specs/2026-05-10-agent-adda-voice-copilot-design.md` and `docs/superpowers/plans/2026-05-10-agent-adda-voice-copilot-backlog.md` |
| I9 `/voice-live` Terminal Assistant Loop • ✅ DONE • Codex • Added live terminal loop with repeated listen/transcribe/answer/speak turns, transcript printing, `--turns`, `--seconds`, `--no-audio`, `--no-play`, `--voice`, and spoken stop handling |
| J0 Startup Data Readiness Design + Backlog • ✅ DONE • Codex • Backlog design added here for validating technical/fundamental DB freshness at agent load and preventing assumed data in answers |
| J1 Data Readiness Service • ✅ DONE • Codex • Added `terminal/data_readiness.py` to inspect `data/sector_rotation_tracker.db`, latest `stage_snapshots`, technical/fundamental coverage, and stale/missing status |
| J2 Refresh Planner + Executor • ✅ DONE • Codex • Added refresh planning and injectable execution for `daily_refresh.py --skip-aux` when DB, technical, or fundamental coverage is missing/stale/partial |
| J3 Startup Terminal Integration • ✅ DONE • Codex • Wired readiness gate into `nse_agent.py` before “Agent Adda ready”; prints readiness panel and supports `--skip-readiness` / `--readiness-no-refresh` |
| J4 Agent Metadata + Answer Guardrails • ✅ DONE • Codex • Historical responses append data freshness metadata and explicitly label missing technical/fundamental DB evidence |
| J5 `/data-status` and `/refresh-data` Commands • ✅ DONE • Codex • Added deterministic terminal commands for checking readiness, showing refresh plan, and forcing readiness refresh |
| J6 Data Readiness Regression Tests • ✅ DONE • Codex • Added `tests/test_data_readiness.py` covering fresh/stale/missing DBs, refresh plan/execution, command rendering, and no-assumption metadata |
| K0 EOD Strategy Lab Design + Backlog • ✅ DONE • Codex • Backlog design added here for first-class EOD equity strategy testing, portfolio simulation, and terminal backtest commands |
| K1 Backtesting Data Contract + Readiness Gate • ✅ DONE • Codex • Added `backtesting/data.py` with full-file EOD readiness scan, latest date, symbol count, blockers, warnings, and technical/fundamental mode labels |
| K2 Strategy Registry • ✅ DONE • Codex • Added `backtesting/strategy_registry.py` with core, compression, and experimental chart-pattern strategy definitions |

</details>

## Phase 4 — Branch F: Financial Filing Intelligence Agent / F0 — Filing Intelligence Design + Implementation Plan

#### F0 — Filing Intelligence Design + Implementation Plan
**Size:** S | **Priority:** Critical | **Status:** ✅ DONE | **Owner:** Codex

**What to build:**
- Write a design spec for an auditable filing-analysis pipeline.
- Write an implementation plan with small TDD tasks.
- Define canonical storage, parsed schema, report schema, evidence trail, and failure modes.

**Files to create/modify:**
- `docs/superpowers/specs/2026-05-07-financial-filing-intelligence-design.md`
- `docs/superpowers/plans/2026-05-07-financial-filing-intelligence.md`
- `docs/BACKLOG.md`

**Acceptance criteria:**
- Spec names the boundary between deterministic extraction and LLM interpretation.
- Plan covers XBRL/iXBRL, PDF, direct-link ingestion, NSE auto-discovery, HTML/MD output, and tests.
- Every later F-item maps back to a task in the plan.


## Phase 4 — Branch F: Financial Filing Intelligence Agent / F1 — Filing Registry + Direct Link Ingestion

#### F1 — Filing Registry + Direct Link Ingestion
**Size:** M | **Priority:** Critical | **Status:** ✅ DONE | **Owner:** Codex

**What to build:**
```python
def ingest_filing_url(url: str, symbol: str | None = None, period: str | None = None) -> dict:
    """
    Download a user-provided filing URL and register it under:
    data/filings/{SYMBOL_OR_UNKNOWN}/{PERIOD_OR_UNKNOWN}/raw/

    Detect document type:
      - PDF: .pdf or application/pdf
      - XBRL/XML: .xml, .xbrl, .zip, text/xml, application/xml
      - iXBRL/HTML: .html/.htm with XBRL namespaces

    Return manifest JSON:
      symbol, period, source_url, local_path, sha256, content_type,
      document_type, fetched_at, status, error
    """
```

**Files to create/modify:**
- `financial_filing_agent.py`
- `tests/test_financial_filing_agent.py`
- `data/filings/` generated at runtime only

**Acceptance criteria:**
- Blue Star PDF link can be downloaded and registered without manual file work.
- Existing local files are not re-downloaded if SHA/path already exists unless `force=True`.
- Bad URL returns a structured error, not an exception.
- Unit tests cover PDF, XML/XBRL, iXBRL/HTML, unknown extension, and network failure using mocks.


## Phase 4 — Branch F: Financial Filing Intelligence Agent / F4 — Multi-Page PDF Extractor + Evidence Map

#### F4 — Multi-Page PDF Extractor + Evidence Map
**Size:** L | **Priority:** High | **Status:** ✅ DONE

**What to build:**
```python
def parse_pdf_filing(path: str) -> dict:
    """
    Extract page text and tables from multi-page financial-results PDFs.
    Build evidence map:
      page_number, table_index, row_label, column_label, extracted_value, confidence.

    OCR fallback is optional and disabled by default in first version.
    """
```

**Files to create/modify:**
- `financial_filing_agent.py`
- `tests/fixtures/filings/sample_financial_result.pdf`
- `tests/test_financial_filing_pdf.py`

**Acceptance criteria:**
- Multi-page PDF produces page-level text chunks.
- Tables are extracted into normalized row/column records.
- Page/table references are available to the final report.
- If PDF parser dependency is missing, tool returns actionable install guidance.

**Implementation note (2026-05-07):**
- `financial_filing_agent.py parse <manifest>` writes `parsed/filing_parse.json`.
- PyMuPDF is used for page text and detected tables; dependency is listed in `requirements.txt`.
- Blue Star FY26 Q4 filing smoke parse produced 23 pages, 12 detected tables, and 749 evidence items.
- Additional smoke tests: Reliance FY26 Q4 media release parsed 42 pages / 28 tables / 1227 evidence items; Infosys FY26 Q4 consolidated statements parsed 39 pages / 6 tables / 49 evidence items; HDFC Bank FY26 Q4 results was correctly flagged `partial` + `OCR_REQUIRED` because all 23 pages are image-only.


## Phase 4 — Branch G: US / Global Market Intelligence / G0 — US/Global Market Intelligence Design

#### G0 — US/Global Market Intelligence Design
**Size:** S | **Priority:** High | **Status:** ✅ DONE

**What exists:**
- `docs/superpowers/specs/2026-05-08-us-global-market-intelligence-design.md`

**Acceptance criteria:**
- Design defines phased US/global architecture, data sources, terminal commands, reports, testing, and India read-through.


## Phase 4 — Branch G: US / Global Market Intelligence / G1 — US Universe + yfinance Cache

#### G1 — US Universe + yfinance Cache
**Size:** M | **Priority:** High | **Status:** ✅ DONE

**What to build:**
- Create curated US/global universe config covering indices, ETFs, and starter stocks.
- Fetch daily OHLCV through `yfinance`.
- Cache normalized data under `data/global_market/`.
- Support `--force`, cache TTL, missing ticker warnings, and smoke universe.

**Files to create/modify:**
- `global_market_intelligence.py`
- `tests/test_global_market_intelligence.py`
- `data/global_market/` runtime outputs

**Acceptance criteria:**
- `SPY`, `QQQ`, sector ETFs, and starter stocks can be fetched and cached.
- Cache reload works without network.
- Missing tickers do not fail the full pipeline.

**Implementation note (2026-05-08):**
- `global_market_intelligence.py` defines the curated starter universe and `GlobalMarketDataLoader`.
- `prices.csv`, `latest_snapshot.csv`, and `universe.json` are written under `data/global_market/`.
- Tests cover universe records, OHLCV normalization, cache writes, latest snapshot, and fresh-cache reuse.


## Phase 4 — Branch G: US / Global Market Intelligence / G2 — US Technical Engine + RS

#### G2 — US Technical Engine + RS
**Size:** M | **Priority:** High | **Status:** ✅ DONE

**What to build:**
- Compute returns, SMA 20/50/200, RSI, MACD, 52W high distance, support/resistance, VCP, Stage 2, and RS vs `SPY`/`QQQ`.

**Acceptance criteria:**
- Fixture data produces deterministic indicator outputs.
- RS ranking works when benchmark data exists and degrades clearly when missing.
- Stage/VCP outputs are compatible with existing NSE terminology.

**Implementation note (2026-05-08):**
- `compute_technical_metrics()` produces stable daily rows with returns, SMA alignment, RSI, MACD signal, 52W distance, support/resistance, VCP flag, Stage label, and RS vs `SPY`/`QQQ`.
- Tests cover benchmark-available and benchmark-missing paths.


## Phase 4 — Branch G: US / Global Market Intelligence / G3 — US Screeners

#### G3 — US Screeners
**Size:** M | **Priority:** High | **Status:** ✅ DONE

**What to build:**
- US Stage 2 leaders.
- US VCP setups.
- 52-week high momentum.
- Sector ETF rotation.
- Risk-on/risk-off dashboard using QQQ/SPY, IWM/SPY, HYG/LQD, TLT, VIX, UUP, GLD, USO.

**Acceptance criteria:**
- Screeners return ranked tables with evidence columns.
- Empty/unavailable data yields explicit warnings, not crashes.

**Implementation note (2026-05-08):**
- Added `screen_stage2_leaders()`, `screen_vcp_setups()`, `rank_sector_rotation()`, and `build_risk_dashboard()`.
- Tests cover ranking order, VCP filtering, sector ETF filtering, and risk-on/risk-off classification.


## Phase 4 — Branch G: US / Global Market Intelligence / G4 — India Read-Through Engine

#### G4 — India Read-Through Engine
**Size:** M | **Priority:** High | **Status:** ✅ DONE

**What to build:**
- Translate US/global signals into NSE sector implications.
- Map Nasdaq/semis, crude, DXY, yields, VIX, credit, Russell, financials, and gold signals to positive/negative/watch India read-through.

**Acceptance criteria:**
- Each read-through item includes source symbols, metric triggers, affected NSE sectors, and confidence.
- Rules are deterministic and testable before LLM narrative generation.

**Implementation note (2026-05-08):**
- Added `build_india_readthrough()` with deterministic sector implications and source-signal trails.
- Tests cover positive Nasdaq/semiconductor read-through and crude/risk-off negative implications.


## Phase 4 — Branch G: US / Global Market Intelligence / G5 — US/Global HTML Report

#### G5 — US/Global HTML Report
**Size:** M | **Priority:** High | **Status:** ✅ DONE

**What to build:**
- Standalone HTML report:
  - global summary
  - index tape
  - sector ETF rotation
  - US screeners
  - India read-through
  - data freshness
  - disclaimer

**Files to create/modify:**
- `global_market_intelligence.py`
- `reports/global/us_market_report_YYYYMMDD.html`
- `reports/latest/us_market_report.html`

**Acceptance criteria:**
- Report opens locally and contains all core sections.
- Report remains useful when a subset of data is unavailable.

**Implementation note (2026-05-08):**
- Added `build_us_market_bundle()` and `render_us_market_report()`.
- CLI supports `--report` to render the standalone HTML report.
- Tests verify dated and latest HTML outputs plus key report sections and disclaimer.


## Phase 4 — Branch G: US / Global Market Intelligence / G6 — Terminal + NLP Integration

#### G6 — Terminal + NLP Integration
**Size:** M | **Priority:** High | **Status:** ✅ DONE

**What to build:**
- Add terminal commands:
  - `/us`
  - `/us indices`
  - `/us sectors`
  - `/us stage2`
  - `/us vcp`
  - `/us stock NVDA`
  - `/global readthrough`
- Route NLP queries about US market, Nasdaq, NVDA, US sector rotation, and India read-through.

**Files to create/modify:**
- `nse_agent.py`
- `tests/test_nse_agent_global_us.py`

**Acceptance criteria:**
- Existing `/global` behavior is preserved and enriched.
- `/us` commands return concise terminal summaries and report paths.

**Implementation note (2026-05-08):**
- Added deterministic command parsing and terminal summary helpers in `nse_agent.py`.
- Direct commands call the US/global cache, build the report bundle, render HTML, and print concise report-linked summaries.
- Existing `/global <topic>` LLM shortcut remains available; only `/global readthrough` is intercepted.


## Phase 4 — Branch G: US / Global Market Intelligence / G7 — Sector Report Global Tab

#### G7 — Sector Report Global Tab
**Size:** M | **Priority:** Medium | **Status:** ✅ DONE

**What to build:**
- Embed US/global context in `sector_rotation_report.py` as a tab or section.
- Show US risk regime, ETF rotation, and India read-through near the broader market narrative.

**Acceptance criteria:**
- Sector rotation report still generates if US/global module fails.
- Global tab includes freshness and source warnings.

**Implementation note (2026-05-08):**
- Added `build_global_us_context_tab_html()` to render a cache-only Global / US context tab in `sector_rotation_report.py`.
- The tab links to `reports/latest/us_market_report.html` when available and degrades to an unavailable card when the report/cache is missing.
- Summary cards cover US/global regime, sector ETF leader, Stage 2 leaders, VCP watchlist, and India read-through without fetching data during NSE report rendering.


