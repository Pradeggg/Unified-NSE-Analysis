# NSE Analysis Platform — Feature Backlog
**Version:** 2.0  
**Date:** 2026-05-19
**Owner:** Pradeep Gorai  
**Scope:** Unified-NSE-Analysis — futuristic market intelligence system roadmap

---

## 0. HOW TO USE THIS DOCUMENT

This backlog is written for a coding assistant. Each item contains:
- **What exists** — exact file names and functions already built
- **What to build** — precise spec with inputs, outputs, algorithm
- **Files to create / modify** — exact paths
- **Dependencies** — what must exist before this item can be built
- **Acceptance criteria** — how to verify it works

Items are grouped into **Phases** (P0 = foundation, P1 = core intelligence, P2 = advanced, P3 = futuristic).  
Each item has a **size estimate**: S (< 4h), M (4–16h), L (1–3 days), XL (3–7 days).

### Data Sources — Master Registry

Every external and internal data source the platform uses or will use. Items marked **NEW** are required by backlog items but are not fully implemented, fully wired, or fully consumed by all dependent workflows unless a later status row explicitly says otherwise.

#### A. Price & Volume Data (Already Built)

| Source | URL / Method | Frequency | Local Cache | Used By |
|---|---|---|---|---|
| NSE EOD Bhavcopy (equities) | `https://nsearchives.nseindia.com/archives/equities/bhavcopy/pr/PR{DDMMYY}.zip` | Daily | `data/nse_sec_full_data.csv`, `data/nse_stock_cache.RData` | All analysis |
| NSE Index Data | `https://www.nseindia.com/api/allIndices`, `https://www.nseindia.com/api/equity-stockIndices?index={INDEX}` | Daily | `data/nse_index_data.csv`, `data/nse_index_cache.RData` | Regime detector, RS calc |
| NSE Index–Stock Mapping | NSE allIndices API | On-demand | `data/index_stock_mapping.csv`, `data/nse_indices_catalog.csv` | Sector classification |

#### B. Fundamental Data (Already Built)

| Source | URL / Method | Frequency | Local Cache | Used By |
|---|---|---|---|---|
| Screener.in Company Page | `https://www.screener.in/company/{SYMBOL}/` — HTML scrape via R (`rvest`) | On-demand (cache 30d) | `data/_sector_rotation_fund_cache.csv` | Fundamental scores, LLM narratives |
| Screener.in Quarterly Screen | `https://www.screener.in/screens/325075/all-latest-quarterly-results/` | On-demand | Transient | Quarterly results scan |

#### C. F&O / Derivatives Data (NEW — P1-2)

| Source | URL / Method | Frequency | Local Cache | Used By |
|---|---|---|---|---|
| NSE FO Bhavcopy | `https://nsearchives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_{DDMMYYYY}_F_0000.csv.zip` | Daily | `data/_fno_signals.csv` | P1-2: OI, PCR, max pain |
| NSE Participant-wise OI | `https://archives.nseindia.com/content/nsccl/fao_participant_oi_{DATE}.csv` | Daily | `data/_fno_participant_oi.csv` | P1-2: FII net long/short |

#### D. Institutional Flow Data (NEW — P1-3)

| Source | URL / Method | Frequency | Local Cache | Used By |
|---|---|---|---|---|
| NSE FII/DII Trade Activity | `https://www.nseindia.com/api/fiidiiTradeReact` | Daily | `data/fii_dii_flows.csv` | P1-3: flow signals |
| NSDL Sector-wise FII Holdings | `https://www.fpi.nsdl.co.in/web/Reports/ReportDetail.aspx` (quarterly) | Quarterly | `data/_fii_sector_holdings.csv` | P1-3: sector-level FII preference |

#### E. Insider / Promoter Data (NEW — P1-4)

| Source | URL / Method | Frequency | Local Cache | Used By |
|---|---|---|---|---|
| NSE Bulk Deals | `https://archives.nseindia.com/content/equities/bulk.csv` | Daily | `data/_bulk_deals.csv` | P1-4: bulk deal alerts |
| BSE Bulk Deals | `https://api.bseindia.com/BseIndiaAPI/api/BulkDealDownload/w` | Daily | `data/_bulk_deals.csv` | P1-4: bulk deal alerts |
| NSE Promoter Pledging | `https://archives.nseindia.com/content/equities/pledge.csv` | Quarterly | `data/_promoter_pledging.csv` | P1-4: pledging alerts |
| SEBI Insider Trading Disclosures | BSE corporate filings / SEBI SAST | Event-driven | `data/_insider_alerts.csv` | P1-4: insider buy/sell |

#### F. Macro-Economic Proxy Data (NEW — P1-6)

| Source | URL / Method | Frequency | Local Cache | Used By |
|---|---|---|---|---|
| S&P Global / IHS Markit PMI | Public press release scrape | Monthly | `data/macro_proxy_signals.csv` | P1-6: PMI trend |
| MoSPI IIP (Industrial Production) | `https://mospi.gov.in/iip` CSV download | Monthly | `data/macro_proxy_signals.csv` | P1-6: industrial activity |
| GST Collections | MoF press release / PIB | Monthly | `data/macro_proxy_signals.csv` | P1-6: consumption proxy |
| CEA Power Generation | `https://cea.nic.in/dashboard/` daily reports | Daily | `data/macro_proxy_signals.csv` | P1-6: industrial demand proxy |
| FADA Auto Sales | FADA website monthly release | Monthly | `data/macro_proxy_signals.csv` | P1-6: auto sector signal |

#### G. Earnings Call / Concall Data (NEW — P2-5)

| Source | URL / Method | Frequency | Local Cache | Used By |
|---|---|---|---|---|
| BSE Corporate Filings | `https://www.bseindia.com/corporates/ann.html` — search for outcome/transcript | Quarterly | `data/concall_transcripts/{SYMBOL}_{QTR}.txt` | P2-5: concall sentiment |
| Trendlyne Concall Summaries | `https://trendlyne.com/` (free tier, limited) | Quarterly | `data/concall_transcripts/{SYMBOL}_{QTR}.txt` | P2-5: fallback source |
| Company IR Pages | Varies per company | Quarterly | `data/concall_transcripts/{SYMBOL}_{QTR}.txt` | P2-5: direct transcript |

#### H. Knowledge Graph Data (NEW — P2-1)

| Source | URL / Method | Frequency | Local Cache | Used By |
|---|---|---|---|---|
| Screener.in Peer Comparison | `https://www.screener.in/company/{SYMBOL}/` → peers section | On-demand | `data/nse_graph.json` | P2-1: supply chain edges |
| Screener.in Company Description | Same page → about section | On-demand | `data/nse_graph.json` | P2-1: sector/promoter nodes |
| NSE Promoter Holding | Quarterly shareholding pattern | Quarterly | `data/nse_graph.json` | P2-1: promoter group edges |

#### I. LLM / AI Services (Already Built)

| Source | URL / Method | Frequency | Local Cache | Used By |
|---|---|---|---|---|
| OpenAI API | `https://api.openai.com/v1/chat/completions` (model: `gpt-4o` or env override) | Per report run | None (transient) | LLM narratives, concall NLP |
| Ollama (local) | `http://localhost:11434` (model: `granite4:latest`) | Per report run | None (transient) | Fallback LLM |

#### J. Distribution / Output (Already Built)

| Source | URL / Method | Frequency | Local Cache | Used By |
|---|---|---|---|---|
| Office 365 SMTP | `smtp.office365.com:587` | On-demand | None | Email reports |

#### K. Market Breadth Data (NEW — Phase 4 Branch C)

| Source | URL / Method | Frequency | Local Cache | Used By |
|---|---|---|---|---|
| NSE Advance/Decline | `https://www.nseindia.com/api/equity-stockIndices?index=NIFTY%20500` — count advances/declines from constituent data | Daily | `data/breadth_history.csv` | C1: McClellan, C2: TRIN |
| NSE Volume by Stock | Already in `data/nse_sec_full_data.csv` — up-volume/down-volume computed from price direction | Daily | `data/breadth_history.csv` | C2: TRIN/Arms Index |
| NSE New 52W High/Low | Derived from `data/nse_sec_full_data.csv` — tag stocks at/near 52W extremes | Daily | `data/breadth_history.csv` | C1: HL breadth line |

#### L. Global Index / FX Data (NEW — Phase 4 Branch B)

| Source | URL / Method | Frequency | Local Cache | Used By |
|---|---|---|---|---|
| Yahoo Finance Global Indices | `yfinance` or `curl` to Yahoo Finance API for SPX, FTSE, HSI, N225, DXY, USDINR | Daily | `data/global_indices.csv` | B2: Global correlation |
| Gold / Oil / Copper (commodities) | `yfinance` for GC=F, CL=F, HG=F | Daily | `data/global_indices.csv` | B2: commodity correlation |
| USDINR rate | `https://finance.yahoo.com/quote/USDINR%3DX/` or RBI API | Daily | `data/global_indices.csv` | B2, D3: FX exposure screening |

#### M. Corporate Events Data (NEW — Phase 4 Branch E)

| Source | URL / Method | Frequency | Local Cache | Used By |
|---|---|---|---|---|
| BSE Corporate Actions Calendar | `https://api.bseindia.com/BseIndiaAPI/api/CorpactionbulkSearch/w` | Daily | `data/corporate_events.csv` | E4: Event-driven alerts |
| NSE Corporate Actions | `https://www.nseindia.com/api/corporates-corporateActions?index=equities` | Daily | `data/corporate_events.csv` | E4: Dividends, splits, bonus |
| BSE Board Meeting Announcements | `https://api.bseindia.com/BseIndiaAPI/api/AnnualResultSearch/w` (search by announcement type) | Daily | `data/corporate_events.csv` | E4: Result date alerts |
| NSE Earnings Calendar | `https://www.nseindia.com/api/event-calendar` | Weekly | `data/corporate_events.csv` | E4: Result announcement dates |

#### N. Screener.in Peers & Deep Fundamentals (NEW — Phase 4 Branch D/E)

| Source | URL / Method | Frequency | Local Cache | Used By |
|---|---|---|---|---|
| Screener.in Peers Table | `https://www.screener.in/company/{SYMBOL}/` → `#peers` table (HTML scrape) | On-demand (cache 30d) | `data/peer_comparisons.csv` | E2: Peer comparison, D6: Moat |
| Screener.in Cash Flow Statement | Same page → `#cash-flow` table | On-demand (cache 30d) | `data/_sector_rotation_fund_cache.csv` | D2: Earnings quality (CFO data) |
| Screener.in 5-Year P&L | Same page → `#profit-loss` (5-year trend) | On-demand (cache 30d) | `data/_sector_rotation_fund_cache.csv` | D1: DuPont, A7: Quality compounder |

#### O. US / Global Market Intelligence Data (NEW — Phase 4 Branch G)

| Source | URL / Method | Frequency | Local Cache | Used By |
|---|---|---|---|---|
| Yahoo Finance US Indices | `yfinance` for `^GSPC`, `^IXIC`, `^NDX`, `^DJI`, `^RUT`, `^VIX` | Daily | `data/global_market/prices.csv` | G1-G7: US index technicals and risk regime |
| Yahoo Finance US ETFs | `yfinance` for SPY/QQQ/DIA/IWM, sector ETFs, SMH/SOXX, TLT/HYG/LQD, GLD/USO/UUP | Daily | `data/global_market/prices.csv` | G2-G5: ETF rotation, risk-on/off, India read-through |
| Yahoo Finance US Stocks | `yfinance` for starter liquid universe: MAG7, semis, financials, energy, defense, consumer, cloud/software | Daily | `data/global_market/prices.csv` | G2-G6: US screeners, stock deep dives, terminal commands |
| Global / US Universe Config | Local curated symbol registry | On change | `data/global_market/universe.json` | G1: reproducible universe metadata and India read-through tags |

#### Access Notes

1. **NSE APIs require browser-like headers**: `User-Agent: Mozilla/5.0`, `Referer: https://www.nseindia.com`. Always use `curl` subprocess or `requests` with timeout + retry (macOS hang issue).
2. **Rate limiting**: 2-second sleep between NSE API calls. Screener.in: 5-second sleep.
3. **All sources are free / public**. No Bloomberg, Reuters, or paid data subscriptions required.
4. **Cache TTL defaults**: daily data = 24h, fundamental data = 30d, quarterly data = 100d, macro data = 45d.
5. **Missing data is not a runtime crash condition**: if a source is unavailable, the corresponding field fills with `None` / `missing_evidence` and the report may still generate.
6. **Missing evidence is a claim blocker**: recommendations, broker/concall/catalyst claims, F&O claims, forensic claims, and Strategy Council trade research must not be stated as facts unless the corresponding source-backed tool returned evidence.

---

### Status Legend
| Icon | Meaning |
|---|---|
| 🔒 IN PROGRESS | Currently being implemented — do not start, check with owner |
| 🧩 PARTIAL | Foundation exists, but integration/tests/coverage are incomplete |
| ✅ DONE | Implemented, tested, and wired for the stated scope |
| 🔜 READY | Spec complete, not yet started — free to pick up |
| ⏳ BLOCKED | Waiting on a dependency item |
| 💤 DEFERRED | Intentionally deferred to a later sprint |

### Research Council Parallel Build Backlog — 2026-05-26

Agent Adda Research Council is the planned multi-agent research workflow that freezes an evidence pack, runs specialist agents, builds and executes empirical plans, lets a coder/quant validate strategy ideas, applies critic gates, and renders research-only reports.

Canonical references:

- Design spec: `docs/superpowers/specs/2026-05-26-agent-adda-research-council-design.md`
- Implementation artifact: `docs/RESEARCH_COUNCIL_IMPLEMENTATION_ARTIFACT.md`
- Parallel implementation backlog: `docs/superpowers/plans/2026-05-26-agent-adda-research-council-backlog.md`

Coordination rules:

- Use the implementation backlog as the source of task ownership.
- Claim one `RC-*` row at a time.
- Start with `RC-0.*` correction/audit work before coding the state machine.
- Keep the first MVP deterministic and API-key-free.
- Do not wire Research Council into `daily_refresh.py` by default until the manual `/council today` path is stable.

| Item | Status | Priority | Suggested Owner | Files | Design / Implementation | Dependencies | Acceptance Criteria |
|---|---|---|---|---|---|---|---|
| RC-MVP Research Council Foundation | 🧩 PARTIAL (foundation implemented; command-smoke closure remains) | P0 | Multiple assistants by `RC-*` row | `terminal/research_council/`, `tests/research_council/`, `postgres/migrations/20260526_research_council.sql`, `nse_agent.py`, `terminal/tools.py`, `terminal/helpfile.py` | Foundation package, state machine, data steward, evidence packs, sector opportunity workflow, deterministic Coder Quant sweep, synthesis, markdown/HTML reports, persistence metadata, CLI flags, terminal command routing, report printing, LLM summary, and candidate-specific confirmation worklists have been implemented through RC-10.4. Remaining MVP closure is no longer "build the whole council"; it is command-smoke hardening and evidence-specialist completion captured in RC-11 and RC-12 below. | RC-0.1 docs alignment, RC-0.2 idempotent migration, RC-0.3 tool mapping audit, RC-9.6 through RC-10.4. | Completed scope has regression coverage in `tests/research_council` and live NIFTY AUTO report smokes. Remaining MVP acceptance is split: `/council steward`, `/council today --evidence-only`, `/council today --horizon swing --risk moderate`, and `/council sector NIFTY AUTO --horizon swing` must all be terminal-smoked without API keys or unsupported claims. |
| RC-9.6 Council Intelligence Query Expansion | ✅ DONE (slices 1-8) | P0 | Council orchestration assistant | `terminal/research_council/engine.py`, `terminal/research_council/states/route.py`, `terminal/research_council/states/market_state.py`, `terminal/research_council/states/plan_build.py`, `terminal/research_council/evidence_pack_builder.py`, `terminal/research_council/tool_adapters.py`, `terminal/research_council/agents/sector_rotation.py`, `terminal/research_council/agents/coder_quant.py`, `terminal/research_council/agents/hedge_fund_owner.py`, `terminal/research_council/reports/markdown_renderer.py`, `terminal/research_council/reports/html_renderer.py`, `terminal/research_council/mode_profiles.py`, `terminal/research_council/commands.py`, `terminal/research_council/schemas.py`, `terminal/router/providers.py`, `terminal/help.py`, `nse_agent.py`, `docs/AGENT_ADDA_HELPFILE.md`, `backtesting/strategy_council/runner.py`, `backtesting/engine.py`, `tests/research_council/test_intelligence_routing.py`, `tests/research_council/test_sector_opportunity_workflow.py`, `tests/research_council/test_plan_loop.py`, `tests/research_council/test_strategy_build_mode.py`, `tests/research_council/test_synthesis.py`, `tests/research_council/test_markdown_render.py`, `tests/research_council/test_specialists/test_coder_quant.py`, `tests/research_council/test_terminal_commands.py`, `tests/research_council/test_help_surface.py`, `tests/test_unified_router.py`, `tests/test_strategy_council_runner.py` | Add the first Council-native thinking layer so broad asks like "Analyze NIFTY AUTO and identify best potential stocks" are not treated as a single stock ask or a generic market note. The intake now infers `sector_opportunity`, route expansion extracts the sector, rewrites the objective into an auditable research mandate, creates sub-questions, selects specialist agents, and marks Coder Quant as `shortlist_only` until the shortlist exists. `/council sector` now maps to this workflow. Slice 2 wires the workflow into market-state evidence: `get_sector_context`/`sector.top_stocks` output is normalized into `sector_opportunity`, `sectors.items`, and `stocks.candidates`; source trail captures the sector source; targeted-sector shortlist candidates survive specialist deliberation even when full breadth metrics are unavailable. Slice 3 builds a sector-opportunity quant plan (`coder_quant_shortlist_sweep`), lets `strategy.build` load EOD frames for shortlist symbols, attaches quant sweep summaries to decision candidates, prevents AMBIGUOUS/UNTESTABLE quant from upgrading sector ideas to `RESEARCH_LONG`, and renders quant verdict/route columns in markdown and HTML reports. Slice 4 adds per-symbol attribution: Strategy Council runner emits `symbol_attribution` from real stage2 trades, Coder Quant carries train/validation attribution by route, chair synthesis attaches the matching symbol row to each candidate, and markdown/HTML reports render symbol contribution. Also fixed final-bar exit cash return in `backtesting.engine` so multi-symbol backtests do not starve later symbols of capital. Slice 5 exposes the workflow through `/council sector NIFTY AUTO --horizon swing`: parser captures `sector`, router forwards it to `run_research_council`, route expansion consumes explicit sector flags, and help/autocomplete surfaces document the command. Slice 6 adds deterministic candidate aggregation and research scoring: duplicate branch candidates collapse into one row with supporting agents/branches preserved, score components include sector rank/score, specialist support, quant verdict, validation return, per-symbol attribution, and risk penalty, and markdown/HTML reports render the score column beside quant evidence. Slice 7 adds report auditability polish: markdown and HTML reports now include a Candidate Score Drivers section that exposes the score components per symbol, including sector rank/score, branch/agent support, quant verdict, validation return, symbol contribution, and risk count. Slice 8 adds real-run CLI ergonomics: `terminal.research_council.engine` accepts `--mode`, `--sector`, `--horizon`, `--risk/--risk-budget`, `--symbol`, `--universe`, and `--format {md,html,both}`, derives a sector objective when only `--sector` is supplied, forwards structured flags into `run_council`, and prints status, decision, top candidate scores, and report paths. | RC-8 Coder Quant route sweep and existing Research Council state machine. | Tests prove `sector_opportunity` inference, explicit sector flags, route expansion, agent selection, Coder Quant policy, mode profile declaration, terminal command mapping, sector evidence-pack normalization, market-state route-sector usage, targeted shortlist handling, sector quant plan creation, symbol EOD loading, quant evidence in synthesis, per-symbol attribution, deterministic research scoring, HTML/markdown score columns, candidate score-driver breakdowns, CLI sector flags and run summary output, candidate aggregation, and an end-to-end sector opportunity run that produces a quant-aware WATCHLIST candidate. Live smoke: NIFTY AUTO shortlist loaded 5 EOD histories and reached `strategy.build`; the single route was marked untestable, so no ranked route was overstated. CLI smoke: `/council sector NIFTY AUTO --horizon swing` parses, routes, forwards `sector=NIFTY AUTO`, builds `coder_quant_shortlist_sweep`, and carries shortlist symbols into the quant plan. Next slice: live real-data council run review and any production hardening discovered from that run. |
| RC-9.7 Real-Run Coder Quant Timeout Hardening | ✅ DONE | P0 | Council orchestration assistant | `terminal/research_council/llm_client.py`, `terminal/research_council/agents/coder_quant.py`, `terminal/research_council/states/plan_review.py`, `terminal/research_council/reports/markdown_renderer.py`, `terminal/research_council/reports/html_renderer.py`, `tests/research_council/test_llm_client.py`, `tests/research_council/test_specialists/test_coder_quant.py`, `tests/research_council/test_plan_loop.py`, `tests/research_council/test_markdown_render.py` | Real NIFTY AUTO run exposed an OpenAI SDK read hang inside Coder Quant. Added application-level daemon-thread timeout around LLM JSON calls, configurable via `RESEARCH_COUNCIL_LLM_TIMEOUT_S` with a 20s default. Coder Quant now circuit-breaks the remaining route sweep after the first AI/provider timeout instead of spending one timeout per route. Plan review marks zero-tested quant sweeps as `degraded` rather than advanced. Reports render `n/a` instead of `None`, integer sector ranks, and a Plan Review section with degraded reasons. | RC-9.6 sector workflow. | Regression tests cover provider timeout wrapping, application-level timeout, Coder Quant circuit breaker, zero-tested quant sweep plan-review degradation, report formatting, and report Plan Review rendering. Real smoke: `RESEARCH_COUNCIL_LLM_TIMEOUT_S=2 .venv/bin/python -m terminal.research_council.engine --sector "NIFTY AUTO" --mode sector_opportunity --horizon swing --risk moderate --format both` completed, generated markdown/HTML reports, ranked ATHERENERG, BAJAJ-AUTO, EXIDEIND, SONACOMS, SUPRAJIT as WATCHLIST only, and surfaced `quant sweep produced no testable routes` in the report. |
| RC-9.8 Coder Quant Executability And Split Lookback Fix | ✅ DONE | P0 | Council orchestration assistant | `terminal/research_council/agents/coder_quant.py`, `tests/research_council/test_specialists/test_coder_quant.py` | Real NIFTY AUTO run showed `AMBIGUOUS` quant rows with `n/a` validation because the AI proposed `52w_high`/`vcp` route families that compile but are not executable by `backtesting.strategy_council.runner`, while Stage 2 validation was recomputing SMA/52W features after the time split and losing the historical warmup window. Coder Quant now detects runner `unsupported_strategy` outputs and routes them to `untestable` instead of ranking zero-trade AMBIGUOUS rows. Stage 2 backtests precompute backward-looking features on the full history before train/validation splitting so validation keeps prior lookback without reading the locked test split. | RC-9.6 sector workflow, RC-9.7 live-run hardening. | Regression tests prove unsupported runner routes fail closed as `unsupported_strategy` and Stage 2 validation receives non-null rolling lookback features after splitting. Verification: `pytest tests/research_council/test_specialists/test_coder_quant.py -q` passes, `pytest tests/research_council -q` passes, and live smoke `RESEARCH_COUNCIL_LLM_TIMEOUT_S=20 .venv/bin/python -m terminal.research_council.engine --sector "NIFTY AUTO" --mode sector_opportunity --horizon swing --risk moderate --format both --print-report` generated `reports/research_council/research_20260527_200005.md/html` with best route `stage2_breakout/5d`, quant verdict `REFUTED`, validation return `-9.64`, and per-symbol attribution instead of unsupported `AMBIGUOUS`/`n/a` evidence. |
| RC-9.9 Executable Breakout Routes And Sector Promotion Gate | ✅ DONE | P0 | Council orchestration assistant | `backtesting/strategy_council/runner.py`, `backtesting/engine.py`, `terminal/research_council/agents/hedge_fund_owner.py`, `tests/test_strategy_council_runner.py`, `tests/research_council/test_synthesis.py` | Continue the real-run hardening from RC-9.8. Added executable backtest paths for `52w_high` and `vcp` StrategySpecs using the existing next-open execution model, signal exits, and per-symbol attribution. The shared backtest metric layer now emits `sharpe`, `profit_factor`, and `max_drawdown_pct`, so Coder Quant's validation gate can evaluate risk-adjusted evidence instead of treating missing Sharpe as zero. The sector-opportunity synthesis policy now requires a second confirming branch or non-sector specialist support before upgrading a sector-only shortlist to `RESEARCH_LONG`; supported quant evidence alone keeps the final label at `WATCHLIST`. | RC-9.8. | Regression tests prove `52w_high` and `vcp` execute without `unsupported_strategy`, risk metrics are emitted, and sector-only quant support stays `WATCHLIST`. Verification: `pytest tests/research_council tests/test_strategy_council_runner.py -q` passes with 216 tests. Live smoke `RESEARCH_COUNCIL_LLM_TIMEOUT_S=20 .venv/bin/python -m terminal.research_council.engine --sector "NIFTY AUTO" --mode sector_opportunity --horizon swing --risk moderate --format both --print-report` generated `reports/research_council/research_20260527_214333.md/html`: final decision `WATCHLIST`, quant verdict `SUPPORTED`, best route `stage2_breakout/5d`, validation return `+54.91`, and top candidates MOTHERSON, EXIDEIND, GABRIEL, ATHERENERG, TIINDIA. |
| RC-10 Council Evidence/Risk Review Hardening | ✅ DONE | P0 | Council trust/reporting assistant | `terminal/research_council/states/critic_review.py`, `terminal/research_council/critics/evidence.py`, `terminal/research_council/critics/overfit.py`, `terminal/research_council/agents/hedge_fund_owner.py`, `terminal/research_council/reports/markdown_renderer.py`, `terminal/research_council/reports/html_renderer.py`, `tests/research_council/test_critic_review_state.py`, `tests/research_council/test_critics/test_evidence.py`, `tests/research_council/test_critics/test_overfit.py`, `tests/research_council/test_synthesis.py`, `tests/research_council/test_markdown_render.py` | Harden report trust after real NIFTY AUTO runs. Critic review now passes a provisional chair decision to critics so EvidenceCritic no longer reports "No decision to review" before synthesis. OverfitCritic reads Coder Quant sweep metrics directly from `execution_results` and only blocks low trade count when trade-count evidence is explicit. EvidenceCritic emits warn-level confirmation findings when quant is supported but technical/F&O/fundamental/catalyst gates lack symbol support. Markdown and HTML reports now include structured Evidence Gates and Route Sweep Details sections. Final rationale explains when supported quant remains WATCHLIST because the sector-only thesis lacks a second confirming branch. | RC-9.9. | Regression tests cover provisional critic decision flow, quant-metric overfit review, specialist confirmation warnings, sector-only rationale, Evidence Gates rendering, and Route Sweep Details rendering. Verification: `pytest tests/research_council tests/test_strategy_council_runner.py -q` passes with 221 tests. Live smoke `RESEARCH_COUNCIL_LLM_TIMEOUT_S=20 .venv/bin/python -m terminal.research_council.engine --sector "NIFTY AUTO" --mode sector_opportunity --horizon swing --risk moderate --format both --print-report` generated `reports/research_council/research_20260527_215804.md/html`: final decision `WATCHLIST`, Evidence Gates rendered technical/F&O/fundamental/catalyst as PENDING and sector_rotation as CONFIRMED, Route Sweep Details rendered all nine untestable routes when the LLM provider was unavailable. |
| RC-10.1 Deterministic-First Quant Sweep Recovery | ✅ DONE | P0 | Council trust/reporting assistant | `terminal/research_council/tool_adapters.py`, `terminal/research_council/critics/evidence.py`, `terminal/research_council/agents/hedge_fund_owner.py`, `terminal/research_council/reports/markdown_renderer.py`, `terminal/research_council/reports/html_renderer.py`, `tests/research_council/test_strategy_build_mode.py`, `tests/research_council/test_critics/test_evidence.py`, `tests/research_council/test_synthesis.py`, `tests/research_council/test_markdown_render.py` | Real report review showed the Coder Quant route sweep could become fully dependent on the first LLM call, then render contradictory evidence (`Execution Results: success`, `Missing Evidence: none`) when the provider timed out. Sweep mode is now deterministic-first by default: existing executable route families run without mandatory LLM, and AI-designed route generation is only used when explicitly requested with `ai_design=True`. EvidenceCritic also warns on sector-only candidates even when quant is unavailable, final rationale flags degraded quant sweeps and sector-only evidence gaps, and Markdown/HTML execution sections derive `degraded` display status from zero-tested sweep payloads. Missing Evidence now includes pending specialist gates even when the original evidence pack has no explicit missing-evidence rows. | RC-10. | Regression tests cover deterministic sweep adapter defaults, opt-in AI sweep mode, sector-only evidence warnings without quant support, degraded display for zero-tested quant sweeps, pending gate missing-evidence rendering, and final rationale for degraded quant/sector-only reports. Verification: `.venv/bin/python -m pytest tests/research_council tests/test_strategy_council_runner.py -q` passes with 226 tests. |
| RC-10.2 Candidate-Level Quant Attribution | ✅ DONE | P0 | Council trust/reporting assistant | `terminal/research_council/agents/hedge_fund_owner.py`, `terminal/research_council/reports/markdown_renderer.py`, `terminal/research_council/reports/html_renderer.py`, `tests/research_council/test_synthesis.py`, `tests/research_council/test_markdown_render.py` | Tighten the candidate table so a supported basket route no longer makes every sector shortlist member look individually supported. The chair now preserves the route verdict separately as `route_verdict`, derives the candidate verdict from per-symbol validation attribution, and scores candidates accordingly: positive symbol contribution remains `SUPPORTED`, no validation trade becomes `NO_SYMBOL_TRADE`, and negative symbol contribution becomes `NEGATIVE_CONTRIBUTION`. Score drivers render both the candidate verdict and route verdict when they differ. | RC-10.1. | Regression tests cover route-vs-candidate verdict separation, score ranking across positive/no-trade/negative contribution, and Markdown/HTML report rendering. Verification: `.venv/bin/python -m pytest tests/research_council tests/test_strategy_council_runner.py -q` passes with 228 tests. Live NIFTY AUTO smoke generated `reports/research_council/research_20260528_012112.md/html`: MOTHERSON/EXIDEIND/GABRIEL stayed `SUPPORTED`, ATHERENERG became `NO_SYMBOL_TRADE`, and TIINDIA became `NEGATIVE_CONTRIBUTION` with lower scores. |
| RC-10.3 Research Council HTML Theme And LLM Summary | ✅ DONE | P0 | Council trust/reporting assistant | `terminal/research_council/reports/summary.py`, `terminal/research_council/states/render_html.py`, `terminal/research_council/reports/html_renderer.py`, `tests/research_council/test_html_render.py` | Upgrade the Research Council HTML from a plain light document to the same dark command-center pattern used by market dashboards. Reports now render as a sticky-header dashboard with panel grid, status colors, compact KPI cards, colored decision/verdict badges, responsive mobile layout, and a top-level "LLM Research Summary" generated from a bounded state payload. Summary generation is fail-closed: if the provider is unavailable, the report still renders with a deterministic fallback summary and the error is captured in summary metadata. | RC-10.2. | Regression tests cover dashboard theme markers, summary rendering, state-level summary injection, and self-contained HTML output. Verification: `.venv/bin/python -m pytest tests/research_council tests/test_strategy_council_runner.py -q` passes with 238 tests. Live NIFTY AUTO smoke generated `reports/research_council/research_20260528_100715.html` with LLM summary source `llm`; Playwright desktop/mobile smoke loaded the file, found `main.grid` and `LLM Research Summary`, captured screenshots in `/tmp`, and reported no console errors. |
| RC-10.4 Candidate-Specific Confirmation Worklist | ✅ DONE | P0 | Council trust/reporting assistant | `terminal/research_council/reports/markdown_renderer.py`, `tests/research_council/test_markdown_render.py` | Replace generic missing-evidence rows such as `technical/council: specialist_confirmation` with candidate-specific rows derived from EvidenceCritic findings. When critic findings are present, reports now render actionable confirmation work items like `technical/MOTHERSON: technical_confirmation`, `fno_risk/MOTHERSON: fno_confirmation`, `fundamental/MOTHERSON: fundamental_confirmation`, and `catalyst/MOTHERSON: catalyst_confirmation`. The old council-level fallback remains only for runs that have pending specialist gates but no critic findings. | RC-10.3. | Regression tests cover candidate-specific critic-derived rows and preserve the fallback pending-gate behavior. Verification: `.venv/bin/python -m pytest tests/research_council tests/test_strategy_council_runner.py -q` passes with 239 tests. Re-rendered `reports/research_council/research_20260528_100715.md/html` and `research_20260528_012112.md/html` so the open reports show candidate-specific confirmation worklists. |
| RC-11 Council Command Smoke Closure | 🧩 PARTIAL (`--evidence-only` implemented) | P0 | Council terminal integration assistant | `terminal/research_council/commands.py`, `terminal/research_council/engine.py`, `terminal/router/providers.py`, `terminal/tools.py`, `terminal/help.py`, `docs/AGENT_ADDA_HELPFILE.md`, `tests/research_council/test_terminal_commands.py`, `tests/research_council/test_engine_state_machine.py`, `tests/research_council/test_help_surface.py`, `tests/test_unified_router.py` | Close the remaining MVP command surface gaps now that the council foundation exists. `--evidence-only` is now a first-class flag: the parser/router pass it through, the engine uses a shortened `intake -> route -> data_steward -> market_state -> render_html -> persistence` sequence, terminal output labels the run as evidence-only, and help surfaces list the command. Remaining work is the scripted/live smoke matrix for `/council steward`, `/council today --evidence-only`, `/council today --horizon swing --risk moderate`, and `/council sector NIFTY AUTO --horizon swing`; ensure each command prints useful terminal output and report paths where applicable. | RC-10.4. | Regression coverage added for parser, engine sequence, wrapper output, router passthrough, and help surface. Verification: `.venv/bin/python -m pytest tests/research_council tests/test_strategy_council_runner.py -q` passes with 242 tests. Remaining acceptance: manual or scripted smoke proves the commands do not fall through to stock-symbol analysis, do not require API keys for deterministic fixture paths, and do not emit unsupported conclusions when only evidence is requested. |
| RC-12 Specialist Evidence Completion For Council Promotion | 🔜 READY | P0 | Council evidence assistant | `terminal/research_council/states/specialist_pass.py`, `terminal/research_council/agents/technical.py`, `terminal/research_council/agents/fundamental.py`, `terminal/research_council/agents/fno_risk.py`, `terminal/research_council/agents/catalyst.py`, `terminal/research_council/tool_adapters.py`, `terminal/research_council/evidence_pack_builder.py`, `tests/research_council/test_specialist_pass.py`, `tests/research_council/test_critics/test_evidence.py`, `tests/research_council/test_synthesis.py` | Replace candidate confirmation warnings with actual specialist evidence where cached/PG-backed data exists. Technical should use EOD/intraday setup evidence, fundamental should use Screener/results/financial cache evidence, F&O should use option-chain/futures evidence when available and mark non-F&O symbols explicitly, and catalyst should use filings/results/latest-catalyst evidence. Keep fail-closed behavior: a missing specialist source remains an actionable missing-evidence row and cannot promote a candidate to `RESEARCH_LONG`. | RC-11 for command surface, RC-10.4 for candidate-specific worklist. | A NIFTY AUTO sector report shows attempted specialist evidence per candidate, with each gate marked confirmed/pending/not-applicable and sourced. `RESEARCH_LONG` requires quant support plus at least one non-sector specialist confirmation; otherwise final label stays `WATCHLIST` with clear missing evidence. |
| RC-13 Council Report Registry And Follow-Up Context | 🔜 READY | P1 | Context memory assistant | `terminal/agent.py`, `terminal/research_council/commands.py`, report registry/context files, `tests/test_report_context_memory.py`, `tests/research_council/test_terminal_commands.py` | Persist the latest Research Council report metadata so follow-ups like "open the report", "review the report", and "based on this council output" bind to the exact latest council artifact instead of relying on generic report search. Store run id, markdown path, HTML path, mode, sector/symbol scope, generated_at, and final label. | RC-11 command smoke closure, R8 report open/context memory. | After any `/council ...` run, a follow-up "open the report" opens or summarizes that exact Research Council report. Context survives a terminal restart if the latest report registry file exists. |

### Paper Trading Strategy Lab Backlog — 2026-05-31

Paper Trading Strategy Lab is the planned local research engine for assessing trading strategies from zero positions starting `2025-01-01`. It is paper-only: LLM agents may propose and compare strategy definitions, but deterministic validated engine components compile, replay, execute, track, and report the results.

Canonical references:

- Design spec: `docs/superpowers/specs/2026-05-31-paper-trading-strategy-lab-design.md`
- Phase 1 implementation plan: `docs/superpowers/plans/2026-05-31-paper-trading-engine-foundation.md`

Coordination rules:

- Keep the engine paper-only unless a later design explicitly adds broker integration.
- Do not allow LLM narrative to execute or mutate trades directly.
- Build deterministic engine contracts before LLM strategy generation.
- Preserve existing `backtesting/` behavior while the new `portfolio/` package is introduced.
- Every agent decision must be logged to JSONL with inputs, rationale, outputs, and status.

| Item | Status | Priority | Suggested Owner | Files | Design / Implementation | Dependencies | Acceptance Criteria |
|---|---|---|---|---|---|---|---|
| PT-0 Paper Trading Engine Foundation | 🔜 READY | P0 | Paper engine assistant | `portfolio/`, `tests/portfolio/`, `docs/superpowers/plans/2026-05-31-paper-trading-engine-foundation.md` | Build the deterministic foundation: package scaffold, static strategy schema, compiler with hard-rail risk clamping, order/fill contracts, next-open execution model, portfolio account, event replay loop, NAV/trade logs, JSONL audit log, Markdown daily report, and CLI fixture replay. | Approved design spec and implementation plan. | `.venv/bin/python -m pytest tests/portfolio -q` passes. CLI replay writes `daily_nav.csv`, `trade_ledger.csv`, `agent_actions.jsonl`, and a daily Markdown report. No LLM or PostgreSQL dependency in Phase 1. |
| PT-1 Platform-Grade Backtest Core | 🔜 READY | P0 | Paper engine assistant | `portfolio/engine/order_types.py`, `portfolio/engine/execution_models.py`, `portfolio/engine/validation.py`, `portfolio/engine/run_manifest.py`, `portfolio/engine/strategy_library.py`, `tests/portfolio/` | Add richer order types, fees/slippage, data-quality gates, benchmark comparison, run manifests, and built-in strategy templates for Stage 2, Donchian/Turtle, moving-average trend, momentum rotation, VCP, Darvas, mean reversion in uptrend, and Minervini-style trend templates. | PT-0. | Strategy fixtures can run with costs, benchmark comparison, data-quality warnings, and reproducibility manifest. Tests prove slippage/fees and malformed bars change outputs predictably. |
| PT-2 LLM Strategy Proposal Agent | 🔜 READY | P1 | Strategy agent assistant | `portfolio/agents/strategy_agent.py`, `portfolio/engine/strategy_schema.py`, `portfolio/engine/strategy_compiler.py`, `portfolio/data/state/strategy_registry.json`, `tests/portfolio/` | Add LLM strategy proposal as structured JSON only. Validate every proposal against allowed grammar, store accepted/rejected specs, and compare multiple strategies in replay. | PT-1. | Invalid LLM proposals are rejected with machine-readable reasons. Accepted proposals are deterministic and replayable. No free-form strategy text is executable. |
| PT-3 Walk-Forward Portfolio Manager | 🔜 READY | P1 | Portfolio manager assistant | `portfolio/agents/portfolio_manager.py`, `portfolio/engine/risk_models.py`, `portfolio/engine/event_loop.py`, `tests/portfolio/` | Add train/validation/locked-test workflow, walk-forward strategy selection, multi-strategy portfolio allocation, conflict resolution for duplicate symbols, and portfolio-level risk rails. | PT-1, PT-2. | Agent can only use prior metrics to choose active strategies. Locked test results are inaccessible until strategy freeze. Combined portfolio replay produces per-strategy and per-symbol attribution. |
| PT-4 Comprehensive Report Agent | 🔜 READY | P1 | Report agent assistant | `portfolio/agents/report_agent.py`, `portfolio/data/reports/`, `tests/portfolio/` | Upgrade reports to comprehensive Markdown/HTML: P&L, NAV, drawdown, strategy leaderboard, trade journal, open risk, benchmark comparison, cost sensitivity, data integrity, and reproducibility manifest. | PT-0 for Markdown, PT-1/PT-3 for full analytics. | Daily report renders all required sections and links to logs/artifacts. Strategy leaderboard includes reliability warnings and benchmark-relative performance. |
| PT-5 EOD Monitoring Agent | 🔜 READY | P2 | Monitoring assistant | `portfolio/agents/monitoring_agent.py`, `terminal/monitor.py`, `tests/portfolio/` | Add EOD monitoring of open paper positions for stops, add triggers, exit triggers, gap risk, and technical deterioration. Intraday monitoring remains alert-only until separately designed. | PT-3. | Monitoring run emits alerts and paper action recommendations without bypassing the paper broker. All monitoring actions are logged to JSONL. |

### Agent Adda Routing & Resolution Backlog — 2026-05-22

This section is the central coordination point for AI assistants working on Agent Adda routing, context binding, symbol/entity resolution, and executable follow-up options. Detailed specs live under `docs/superpowers/specs/`; this backlog owns implementation sequencing and write-scope boundaries.

Canonical design references:

- Hybrid symbol resolution design: `docs/superpowers/specs/2026-05-22-hybrid-symbol-resolution-design.md`
- Hybrid symbol resolution implementation backlog: `docs/superpowers/plans/2026-05-22-hybrid-symbol-resolution.md`
- Unified router refactor design: `docs/superpowers/specs/2026-05-22-unified-router-refactor-design.md`

Ownership rules:

- Claim one row at a time.
- Do not overlap write scopes with another active row unless explicitly coordinating.
- Preserve existing deterministic behavior until parity tests prove the replacement path.
- Do not answer data-grounded asks from prose summaries; route through validated evidence.
- NEXT OPTIONS must only be displayed when their bound actions validate.

| Item | Status | Priority | Suggested Owner | Files | Design / Implementation | Dependencies | Acceptance Criteria |
|---|---|---|---|---|---|---|
| AA-HSR-6 Embedding Retriever v2 | 💤 DEFERRED | P1 | Resolver/ML assistant | `postgres/migrations/20260524_symbol_resolution_pgvector.sql`, `terminal/symbol_search/embedding_index.py`, `scripts/refresh_symbol_embeddings.py`, `tests/test_hybrid_symbol_resolution.py` | Add optional `pgvector` table and HNSW index. Use `sentence-transformers/all-MiniLM-L6-v2` as a soft dependency. Lazy-load encoder only when enabled. Fuse dict, trigram, and embedding results with RRF. | AA-HSR-1 through AA-HSR-5 stable in production. | Out-of-vocab top-1 recall improves by >= 5 percentage points; no regression on v1 fixtures; memory increase <= 120MB. |
| AA-UR-6 Agent Execution Refactor | ✅ DONE (Phase 2/3 — Phase 3 deferred) | P1 | Agent integration assistant | `terminal/agent.py`, `tests/test_terminal_agent_market_prompt.py`, `tests/test_agent_entity_topic_commands.py` | **Phase 1**: wired `UnifiedRouter` into `Agent._query_single()` as an additive shim owning CompoundStockProvider and PendingOptionProvider paths. **Phase 2 (done)**: widened `_execute_route` to own `direct_tool_plan` routes from EntityTopicProvider (synthesis=`stock_brief`), VisualScanProvider (`visual_scan`), MarketSituationProvider (tool-result-derived intent, market overview tools added to `_PLAN_TOOL_TO_SYNTHESIS_INTENT`), and DirectIntentProvider. Synthesis intent is derived from actual tool results (not planned tools) for non-entity providers to stay consistent with mocked and real executions. `contextual_answer` routes (ContextualFollowupProvider, ReportProvider) still fall through — they have no tool plan and require context-synthesis logic not yet wired into `_execute_route`. **Phase 3 (deferred to AA-AR-2)**: delete legacy fallback branches and make `blocked_ungrounded` terminal; blocked on AA-AR-2 Named Pipeline Stages. | AA-UR-5 validation. | Full suite green: 1250/1250. `result["intent"]` reflects router-canonical intent (`"market_situation"`, `"entity_topic_technicals"`, etc.) rather than legacy keyword intent. Tests updated for new Phase 2 router-owned intents. |
| AA-UR-8 LLM Ambiguity Resolver | 💤 DEFERRED | P1 | Router/LLM assistant | `terminal/assessment_llm.py`, `terminal/router/llm_resolver.py`, `tests/test_unified_router.py` | Reuse GPT-5.5 high reasoning only when deterministic top candidates are close or low confidence. LLM returns candidate selection or clarification options, not unchecked tool execution. Preserve grounding checks and symbol/path validation. | AA-UR-5 validation stable. | Ambiguous follow-ups use prior context, produce POT/TOT-safe public reasoning summaries, and cannot introduce symbols or paths absent from context unless routed as a new direct ask. |

### Claude Code 2.x Inheritance Backlog — 2026-05-25

Features lifted from `@anthropic-ai/claude-code@2.1.150` (per the package's `sdk-tools.d.ts` — 32-tool surface). Ranked by ROI in the NSE-research domain. **Anti-inherits** (explicitly out of scope, for clarity to future contributors): worktrees, Bash sandbox, JS REPL with persistent state, NotebookEdit, native-binary packaging, and multi-agent `team_name`/addressable `SendMessage`. Those solve coding-agent problems Agent Adda does not have.

Canonical reference: the Claude Code package tarball can be re-fetched via `npm pack @anthropic-ai/claude-code`; the `sdk-tools.d.ts` and the postinstall scripts are the readable surface (the runtime is a ~500 MB native binary, not analysable from source).

| Item | Status | Priority | Suggested Owner | Files | Design / Implementation | Dependencies | Acceptance Criteria |
|---|---|---|---|---|---|---|---|
| AA-CC-1 AskUserQuestion Contract | 🔜 READY | P0 | Router assistant | `terminal/clarify.py` (NEW), `terminal/agent.py`, `terminal/renderer.py`, `tests/test_clarify.py` (NEW) | Replace the freeform `pending_clarification` string round-trip in `Agent._query_single` with a structured request mirroring Claude Code's `AskUserQuestionInput`: 1–4 questions, each with 2–4 options `{label (1–5 words), description, preview?}`, optional `multiSelect`. Auto-inject an "Other" option in the renderer; the agent must not include it. Domain-fit previews show a mini-snapshot per option (price, RS, stage) — use the existing snapshot helpers in `terminal/tools.py`. Output shape: `{answers: {questionText: answer}, annotations?: {questionText: {preview?, notes?}}}`. | None. | New `ClarifyTests` cover: symbol disambiguation (GLOBAL → Global Health vs. Globe Civil vs. GlobalSpace), mode selection (intraday vs. EOD), multi-select sector picker. Existing `pending_clarification` regression tests still pass — old-style asks are accepted as a single-question/two-option clarification under the hood. |
| AA-CC-2 Permission Mode Enum | 🔜 READY | P0 | Agent integration assistant | `terminal/agent.py`, `terminal/evidence_gate.py`, `nse_agent.py`, `tests/test_terminal_agent_market_prompt.py` | Promote `Agent.__init__(auto_mode: bool)` to `mode: Literal["default", "auto", "dontAsk", "plan", "bypassPermissions"]`. Map current `[AUTO]` to `auto`. New `dontAsk` is headless-CI (skip every interactive confirmation, including destructive ones). `plan` produces a plan and stops — wires to the same renderer as `ExitPlanMode`. `evidence_gate.py` consults `Agent.mode` instead of `auto_mode` when deciding whether to escalate ungrounded asks. Backward compat: `--auto` CLI flag maps to `auto`; new `--mode {…}` flag added. | None. | Existing CLI behavior preserved when only `--auto` or no flag is passed. New `PermissionModeTests` cover: `plan` mode never executes a tool; `dontAsk` mode does not prompt on any clarification; `default` mode escalates on ungrounded asks unchanged. |
| AA-CC-3 Source Trail Token + Cost Telemetry | ✅ DONE | P0 | Telemetry assistant | `terminal/agent.py`, `terminal/renderer.py`, `tests/test_terminal_renderer_guards.py` | Capture OpenAI `usage` (and Anthropic `usage` if/when added) from every `_query_single` LLM call. Render a new `▶ COST` block below the existing `▶ SOURCE TRAIL`, mirroring Claude Code's `AgentOutput.usage`: `input_tokens`, `output_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`, plus `toolStats: {readCount, searchCount, bashCount, editFileCount}`. Aggregate across a compound plan. Persist alongside the trace JSON so the silent-failure class (`get_top_gainers_losers` regression: zero output tokens + tool error) is detectable post-hoc. | None. | New `CostTrailTests` cover: usage captured on direct ask, accumulated across compound plans, missing-usage degrades gracefully (no exception). Existing renderer tests unaffected. |
| AA-CC-4 Dependency-Aware Task Graph | 🔜 READY | P1 | Router assistant | `terminal/router/compound_stock.py`, `terminal/situation_assessment.py`, `tests/test_compound_stock.py` (NEW or extend) | Extend `CompoundStockProvider` to emit a multi-task plan with explicit dependencies, mirroring Claude Code's `TaskCreate { addBlocks, addBlockedBy, activeForm }`. Reuse the in-session SQL schema (`todos`, `todo_deps`) that already exists in coding-assistant runs — promote it to a first-class agent-side persistence layer at `.agentadda/session_tasks.sqlite`. Compile prompts like _"give me VCP setups, then their fundamentals, then valuation vs peers"_ into three tasks where #2/#3 block on #1's symbol list. Spinner shows `activeForm` per in-progress task. | AA-UR-6 Phase 2 stable (compound provider owns its execution path). | New `TaskGraphTests`: 3-stage research pipeline produces 3 tasks with correct dep edges; status updates as each step completes; blocked tasks do not run; cancellation marks downstream `deleted`. |
| AA-CC-5 Cron + ScheduleWakeup Primitives | 🔜 READY | P1 | Scheduler assistant | `terminal/scheduler.py` (NEW), `nse_agent.py` (slash commands `/cron`, `/wakeup`), `.agentadda/scheduled_tasks.json` (runtime), `tests/test_scheduler.py` (NEW) | Add two REPL primitives mirroring `CronCreateInput` and `ScheduleWakeupInput`. `/cron "M H DoM Mon DoW" <prompt> [--durable] [--once]` enqueues a recurring or one-shot prompt. `/wakeup <delaySeconds> <reason> <prompt>` fires once after `delaySeconds ∈ [60, 3600]`. `durable=true` persists to `.agentadda/scheduled_tasks.json` and survives REPL restarts (loaded by `nse_agent.py:9350+` boot block alongside intraday_capture). Polling thread runs alongside existing capture daemons. Domain examples: `/cron "55 8 * * 1-5" "/briefing pre-open" --durable`, `/wakeup 300 "5 min before bell" "/briefing pre-open"`. | None (uses existing background-thread infrastructure). | New `SchedulerTests`: 5-field cron parser accepts the documented examples; durable tasks reload after restart; one-shot tasks auto-delete after firing; wakeup clamped to [60, 3600]; idempotent vs. duplicate cron expressions. Manual smoke: schedule a `/briefing` for next minute, verify it fires. |
| AA-CC-6 WatchTrigger (specialised Monitor) | 🔜 READY | P1 | Live-data assistant | `terminal/watch_trigger.py` (NEW), `nse_agent.py`, `tests/test_watch_trigger.py` (NEW) | Specialise Claude Code's `MonitorInput` for the market-data domain: instead of a raw shell command, accept a Postgres condition query over `intraday.quote_snapshots` / `intraday.futures_snapshots` (already populated by `intraday_capture.py`) plus an `action` prompt. Each row returned by the query is an event that fires an LLM follow-up turn. Slash command `/watch "RELIANCE crosses 2800" "/explain trigger"`. `persistent=true` keeps the watch for the session lifetime; otherwise honors `timeout_ms` (max 1 h). Stop via `/watch stop <id>` (mirrors `TaskStop`). | AA-CC-5 scheduler infrastructure (shares the polling thread). | New `WatchTriggerTests`: threshold cross fires exactly once until reset; `persistent` watches survive idle turns; `timeout_ms` enforced; bogus SQL falls back gracefully without crashing the REPL. |
| AA-CC-7 Workflow DSL with Resumable Cache | 🔜 READY | P2 | Orchestration assistant | `agent_adda/workflows/__init__.py` (NEW), `agent_adda/workflows/pre_open_briefing.py` (NEW), `agent_adda/workflows/stock_deep_dive.py` (NEW), `terminal/workflow_runner.py` (NEW), `tests/test_workflow_runner.py` (NEW) | Port Claude Code's `Workflow` tool with `agent() / parallel() / pipeline() / phase()` primitives. Each `agent()` call wraps an `Agent._query_single` invocation; results are memoised by `(prompt, opts)` hash and persisted under `.agentadda/workflow_runs/<runId>/`. `resumeFromRunId` re-runs only edited/new calls. Predefined workflows: `pre_open_briefing` (parallel global_macro + sgx_nifty + fii_dii + upcoming_results, then synthesize), `stock_deep_dive(SYMBOL)` (pipeline technical → fundamentals → peers → filings → entry_levels). | AA-CC-4 task graph, AA-CC-3 cost telemetry (workflow runs need aggregated cost reporting). | New `WorkflowRunnerTests`: pipeline preserves stage order; parallel stages launch concurrently; resume re-uses cached `agent()` outputs; edited stage invalidates only downstream cache. End-to-end: `pre_open_briefing` produces a single synthesized briefing in <30 s on warm cache. |
| AA-CC-8 ExitPlanMode Semantic Permissions | 🔜 READY | P2 | Permissions assistant | `terminal/evidence_gate.py`, `terminal/agent.py`, `tests/test_evidence_gate.py` | Extend the plan-mode exit contract to accept `allowedPrompts: [{tool, prompt}]` — semantic permission categories rather than per-tool grants. Domain examples: `{tool: "Postgres", prompt: "read intraday tables"}`, `{tool: "NSE-Fetch", prompt: "live API quotes"}`, `{tool: "Filesystem", prompt: "write reports under reports/"}`. `evidence_gate` matches incoming tool calls against the approved categories using the existing intent-classifier surface. Reduces approval fatigue when a plan needs many calls of the same category. | AA-CC-2 mode enum (`plan` mode produces the plan that this approves). | New `SemanticPermissionTests`: category grant authorises N matching tool calls without re-prompting; mismatched category re-prompts; revocation works mid-plan. Existing per-tool grants still accepted as a degenerate case. |
| AA-CC-9 Tool Schema Catalog | 💤 DEFERRED | P2 | Tooling assistant | `scripts/maintenance/dump_tool_catalog.py` (NEW), `terminal/tools.schema.json` (GENERATED), `tests/test_tool_catalog.py` (NEW) | Auto-generate a single JSON Schema inventory of every registered tool function in `terminal/tools.py` (currently 9k+ lines, no single inventory). Mirrors Claude Code's shipped `sdk-tools.d.ts`. Drives: (a) downstream MCP exposure if/when we add MCP server support, (b) hallucinated-tool detection (compare LLM-emitted tool names against the catalog), (c) audit of what the LLM can actually see vs. internal helpers. Generator walks the tool registry, inspects signatures + docstrings, emits JSON Schema per the `ToolInputSchemas` union convention. | None. | Generated catalog stays in sync (CI check). `HallucinatedToolGuardTests` rejects an LLM-emitted `get_tomorrow_close()` (not in catalog). Hand-spot 5 random tools to verify schema correctness. |
| AA-CC-10 Background Sub-Agent + Push | 💤 DEFERRED | P2 | Sub-agent assistant | `terminal/subagent.py` (NEW), `terminal/agent.py`, `tests/test_subagent.py` (NEW) | Port Claude Code's `AgentInput` with `run_in_background: true`. A sub-agent runs in a worker thread; the parent gets an `agentId` immediately and keeps chatting. On completion, the parent posts a chat notification (and optionally fires `PushNotification` to the voice/SMS channel if configured). Translate `model: "sonnet"|"opus"|"haiku"` → backend selector (`gpt-4o` / `gpt-4o-mini` / `claude-haiku`). Skip `isolation: "worktree"` (Agent Adda is not a coding agent). Skip `team_name`/addressable `name`/`SendMessage` for now — revisit only if multi-agent coordination becomes a real need. | AA-CC-1 AskUserQuestion (sub-agents may need to clarify), AA-CC-4 task graph (durable task records). | New `SubAgentTests`: background launch returns immediately with `agentId`; result available via a `TaskGet`-style fetch; backend selector routes correctly; failure in sub-agent does not crash parent REPL. |
| AA-CC-11 Parallel Tool Dispatch | ✅ DONE | P0 | Agent integration assistant | `terminal/agent.py` (`_query_single`, `_call_tool` loop), `terminal/tools.py` (purity audit), `tests/test_parallel_tool_dispatch.py` (NEW) | Today `_query_single` dispatches LLM-emitted `tool_calls` sequentially — a compound ask like _"top gainers + market breadth + advance/decline"_ pays full latency three times even though the three tools are independent. Mirror Claude Code's behaviour: when a single assistant message contains multiple `tool_use` blocks, dispatch them concurrently via a bounded `ThreadPoolExecutor` (size 4–8) and resume the model only after **all** `tool_result` blocks are back, preserving the original tool-call order in the message thread. Audit `terminal/tools.py` for hidden ordering deps (shared NSE cookie jar, intraday DB writers); serialise calls that touch the same resource via a per-resource `Lock` registry. Tools that mutate state (`/scan` cache writers, screener cache fills) stay on the serial path via an explicit `@serial_tool` decorator. | None (purely additive). | New `ParallelDispatchTests`: 3 independent read-only tools complete in roughly max-of-three latency, not sum-of-three; serialised tools run in declaration order; one tool's failure does not block the others' results from reaching the model; cookie-jar contention test passes 100× without flake. Existing tool tests unaffected. |
| AA-CC-12 In-Session Auto-Compaction | 🔜 READY | P1 | Context management assistant | `terminal/context_manager.py` (NEW), `terminal/agent.py`, `terminal/checkpoint.py` (if exists, else NEW), `tests/test_context_manager.py` (NEW) | Long sessions (post-market briefing → multiple stock deep-dives → screener loops) currently grow monotonically until they hit the model window. Port Claude Code's auto-compaction: when transcript token estimate crosses `0.75 × window`, collapse the oldest contiguous block of completed turns into a single summary "system" message via a dedicated cheap-model call (`gpt-4o-mini`), while re-injecting anchors verbatim: (a) most-recent user turn, (b) currently-open `pending_clarification`, (c) latest data-freshness header, (d) plan.md head if loaded, (e) last 3 SOURCE TRAIL blocks. Expose `/compact` (manual) and `/clear` (full reset, keeps anchors only). Persist the pre-compaction transcript to `.agentadda/session_archives/<session>.jsonl` for replay. | AA-CC-3 cost telemetry (compaction needs token counts to trigger). | New `CompactionTests`: trigger fires at threshold; anchors preserved; summary captures key facts (verify by replaying a 50-turn fixture and asking a question that needs early-turn context); manual `/compact` works mid-session; archive jsonl loads back into a fresh session via `/resume`. |

### Sprint 1 Status (2026-05-02)
| Item | Status | Assignee | Notes |
|---|---|---|---|
| P2-2 Counterfactual Scenarios | 🔜 READY | — | Independent. `scenario_engine.py`. |
| P2-3 Learning Loop | ⏳ BLOCKED | — | Needs P0-1 signal log to accumulate 90+ days of data |
| P3-1 Causal Inference Model | ⏳ BLOCKED | — | Needs 6+ months of P0-1 signal data |
| P3-3 Real-Time Mode | 💤 DEFERRED | — | Needs live NSE data subscription |
| P3-4 Installable Agent Adda CLI | 🔒 IN PROGRESS | Codex | `pyproject.toml`; `agent_adda` package; `agent-adda setup`, `doctor`, `data bootstrap --historical`; local config + SQLite historical bootstrap foundation |

### Backlog Reconciliation — 2026-05-17

This review reconciles the backlog against the current Agent Adda behavior observed during live terminal testing on 2026-05-15 to 2026-05-17. The active risk is no longer just feature coverage; it is evidence discipline, PostgreSQL operational reliability, entity/context resolution, and stale backlog status.

| Item | Status | Priority | Files | Design / Implementation | Acceptance Criteria |
|---|---|---|---|---|---|
| R0 Backlog Status Reconciliation | 🔒 IN PROGRESS | P0 | `docs/BACKLOG.md`, `docs/superpowers/plans/*` | Review items marked `READY`/`IN PROGRESS` that are now partly implemented: symbol validation, required-tool plans, situation assessment, PostgreSQL intraday storage, `/results`, Strategy Council, and startup readiness. Split partially complete items into done scope plus remaining work. | Backlog shows current truth: completed work is not left as `READY`, and remaining work has concrete files, tests, and acceptance criteria. |
| R0.3 Research Council Status Reconciliation | ✅ DONE | P0 | `docs/BACKLOG.md` | Reconciled the stale Research Council MVP row after RC-9.6 through RC-10.4 implementation. The foundation is now marked partial instead of ready, completed scope is listed, and remaining gaps are split into RC-11 command-smoke closure, RC-12 specialist evidence completion, and RC-13 report-context memory. | The Research Council section no longer presents already-built foundation work as `READY`; remaining work has concrete files, dependencies, and acceptance criteria for parallel assistants. |
| R2 PostgreSQL Migration + Historical Load Assurance | 🔜 READY | P0 | `postgres/*.sql`, `terminal/intraday_storage.py`, `postgres/loader.py`, loader tests | Make schema creation idempotent for `intraday`, `report`, `scores`, `market`, and Strategy Council tables. Add a load audit proving historical EOD and intraday bars exist in PostgreSQL for the available stock universe. | A single command can verify/create schemas and report coverage by table; missing historical data is listed by symbol/date range, not discovered only at answer time. |
| R3 `/results` Evidence Integration | 🔒 IN PROGRESS | P0 | `terminal/agent.py`, `terminal/tools.py`, `financial_filing_agent.py`, report generators | Treat latest results as a reusable evidence capability, not only a terminal command. Strategy Council, Stock Sherlock, forensic, and research report flows should call the same latest-results evidence path when asked or when result freshness is relevant. Market-wide latest-results feed (R10) and per-symbol path both exist; remaining work is to wire shared evidence into Strategy Council and research reports. | "latest results for DMART", Strategy Council evidence packs, and stock research reports share the same source trail and do not route to unrelated symbols or generic search prose. |
| R4 Universal Source-Backed Claim Gating | 🔜 READY | P0 | `terminal/agent.py`, `terminal/tools.py`, renderers, report generators | Extend required-tool validation into a universal evidence matrix. Every technical, fundamental, catalyst, forensic, sector, F&O, and results conclusion must map to executed tool evidence or be labeled unavailable. | Answers never state broker targets, concall comments, forensic scores, latest results, sector claims, option-chain metrics, or recommendations unless the corresponding tool returned evidence. |
| R5 First-Class Situation Assessment v2 | 🔜 READY | P0 | `terminal/situation_assessment.py`, `terminal/agent.py`, `tests/test_situation_assessment.py`, `tests/test_terminal_agent_market_prompt.py` | Upgrade from deterministic follow-up assessment to a first-class LLM/deterministic hybrid that states what the user is asking, resolves prior-context references, identifies ambiguity, selects POT/TOT planning when needed, and asks clarification instead of guessing. | Multi-step conversations such as "open the report", "based on the report", "were these from last 30 minutes", and "search USL growth strategy" resolve the intended context or request clarification before routing. |
| R6 Symbol + Entity Resolution Regression Hardening | 🔒 IN PROGRESS | P0 | `terminal/agent.py`, `terminal/symbols.py`, `company_intelligence_search.py`, tests | Fix wrong-symbol regressions by prioritizing exact tickers, aliases, previous conversation entities, and command-specific expected entity types. Block fallback to unrelated symbols when a company/topic query is unresolved. | USL does not resolve to AURIGROW, ADX/MA are not treated as requested stock symbols, and follow-up commands reuse the prior report/symbol unless the user changes context. |
| R7 F&O Recommendation Evidence Contract | 🔜 READY | P0 | `terminal/tools.py`, `terminal/agent.py`, F&O tests | F&O overview/recommendation prompts must require option chain, PCR, max pain, top OI strikes, futures basis, cost of carry, expiry, and risk framing. If any required data is missing, render missing evidence instead of a generic market overview. | "Give a comprehensive F&O overview for NIFTY" returns F&O-specific evidence or a required-tool validation failure naming the missing F&O tools. |
| R8 Report Open/Context Memory | 🔜 READY | P1 | `terminal/agent.py`, report registry, tests | Remember the most recent generated report path/type/symbol and route "open the report" or "based on the report" to that artifact rather than unrelated screener/search context. | After `/strategy-council KIRLOSENG llm`, "open the report" opens or summarizes that exact Strategy Council report path. |

### Backlog Reconciliation — 2026-05-19

This pass reconciles the central backlog with the current dirty tree and the Strategy Council report review from 2026-05-18. The highest risk is no longer feature count; it is evidence-backed claim discipline, duplicated backlog sources, and Strategy Council validation/test mismatch.

| Item | Status | Priority | Files | Design / Implementation | Acceptance Criteria |
|---|---|---|---|---|---|
| R0.2 Worktree-Aware Status Audit | 🧩 PARTIAL | P0 | `docs/BACKLOG.md`, `backtesting/strategy_council/IMPLEMENTATION_BACKLOG.md` | Current tree includes partially implemented foundations not fully reflected by old `READY` rows: `terminal/results_tools.py`, `terminal/company_evidence_tools.py`, `terminal/fno_composite.py`, `terminal/financials_cache.py`, `backtesting/strategy_council/evidence_filings.py`, and `backtesting/strategy_council/tool_router.py`. | Each affected backlog item is split into foundation-done versus remaining integration/tests before new work starts. |
| R4.1 Unified Claim and Recommendation Gate | 🔜 READY | P0 | `terminal/agent.py`, `terminal/tools.py`, report renderers, `backtesting/strategy_council/council.py`, tests | Merge the intent-level required-tool checks, final-answer symbol validator, source-backed claim gating, and Strategy Council recommendation gating into one evidence contract. | Answers and reports do not emit unsupported claims; Strategy Council cannot return `TRADE_RESEARCH` from a positive one-shot test when validation is negative, zero-trade, or rejected by required critics unless explicitly labeled as a research anomaly. |

### Dashboard Data Integrity & Live-Source Fallback — 2026-05-25

Source: Investigation of `reports/dashboards/market_dashboard_20260519_101523.html` (now quarantined to `reports/dashboards/_quarantine_fixture/`). That HTML matched `tests/test_market_dashboard_view.py::_dashboard_snapshot()` byte-for-byte (NIFTY 50 23,600, NIFTY METAL 13,000 +1.10%, AAA +6.10%, ZZZ −5.40%, TATASTEEL +3.20%), while real 2026-05-19 NSE data had NIFTY IT leading at +3.23%, NIFTY METAL at −0.05%, and NIFTY AUTO at +0.29%. Root cause: a one-off REPL/dev invocation of `_write_market_dashboard_html(<fixture>)` dropped a test fixture into the production reports directory; the writer had no source-verification gate, and `/dashboard` had no fallback when NSE allIndices was unreachable. Tag: `PG-DASHLIVE`.

| Item | Status | Priority | Files | Design / Implementation | Acceptance Criteria |
|---|---|---|---|---|---|
| DASH1 Dashboard Provenance Watermark | ✅ DONE | P0 | `nse_agent.py` (`_fetch_market_dashboard_snapshot`, `_render_market_dashboard_html`) | Stamp every dashboard snapshot with `data_source`, `degraded`, and `source_chain` fields; render them in both the HTML header (`[LIVE]` / `[DEGRADED — yfinance fallback]` badge) and the Source/Freshness Audit panel. Emit an HTML comment `<!-- PG-DASHLIVE provenance: ... -->` for grep-based detection. | Every generated dashboard HTML shows its data source in the header line and in the audit panel; a fixture-driven render would still show a source string instead of looking like a live NSE pull. |
| DASH2 Refuse-to-Write Empty Dashboard | ✅ DONE | P0 | `nse_agent.py` (`_write_market_dashboard_html`, `_live_overview_is_usable`) | Before writing the HTML, verify the snapshot's `get_live_market_overview` has at least 3 `NIFTY *` indices and no `error` key. Raise `RuntimeError` with the source chain instead of writing a sparse/fixture file. | Calling `_write_market_dashboard_html({"get_live_market_overview": {"error": ...}})` raises and writes nothing; verified via `python -c` smoke test on 2026-05-25. |
| DASH3 yfinance Index Fallback for /dashboard | ✅ DONE | P0 | `nse_agent.py` (`_fetch_indices_via_yfinance`, `_DASHBOARD_YF_INDEX_TICKERS`, `_fetch_market_dashboard_snapshot`) | When NSE allIndices returns `{"error":...}` or fewer than 3 NIFTY indices, fall back to yfinance using `^NSEI`, `^NSEBANK`, `^CNXIT`, `^CNXAUTO`, `^CNXFMCG`, `^CNXMETAL`, `^CNXPHARMA`, `^CNXREALTY`, `^CNXENERGY`, `^CNXINFRA`, `^CNXMEDIA`, `^CNXPSUBANK`, `^CNXFIN`, `^INDIAVIX`. Prefer `yf.Ticker.fast_info` (single HTTP hit) and fall back to 5-day history. Return same shape as NSE so renderer needs no special-casing. | Verified live on 2026-05-25: simulated NSE failure produced 13 fully-populated indices via yfinance (NIFTY 50 = 23,986 etc.), `data_source = "yfinance fallback"`, `degraded = True`, `source_chain = ["NSE live API failed (...)", "yfinance fallback"]`. |
| DASH4 Quarantine Existing Fixture HTML | ✅ DONE | P0 | `reports/dashboards/_quarantine_fixture/` | Move the misleading 2026-05-19 HTML out of the live reports directory so it cannot be re-shared/emailed as live analysis. | `reports/dashboards/market_dashboard_20260519_101523.html` no longer exists in the live dir; quarantine folder contains the file for forensic reference. |
| DASH5 Fixture-Detector Sweep Script | 🔜 READY | P2 | new `scripts/maintenance/purge_fixture_dashboards.py` | Add a maintenance script that scans `reports/dashboards/` for fixture signatures: presence of `AAA`, `BBB`, `ZZZ`, `"last":13000.0` with `pct_change":1.1`, or absence of the new `PG-DASHLIVE provenance` HTML comment. Move suspect files to `_quarantine_fixture/` and write a summary to `logs/dashboard_quarantine.log`. | Script run against today's `reports/dashboards/` reports 0 hits (since fixture is already quarantined and new writes carry the provenance comment); a planted fixture file is detected and moved on next run. |
| DASH6 Regenerate Historical 2026-05-19 Dashboard | 🔜 READY | P2 | `nse_agent.py`, optional `tools/replay_dashboard.py` | Add a `/dashboard --as-of YYYY-MM-DD` flag (or a dedicated replay script) that rebuilds a historical dashboard from `data/nse_index_data.csv` so we have a truthful 2026-05-19 record (NIFTY IT leader at +3.23%, METAL −0.05%, AUTO +0.29%). | `/dashboard --as-of 2026-05-19 --html` produces a dashboard whose Market Pulse leader matches `data/nse_index_data.csv` for that date. |
| DASH7 Help-Smoke Coverage for Provenance | 🔜 READY | P2 | `tests/run_help_catalog_smoke.py`, new `tests/help_smoke_expectations.py` | Add a check that `/dashboard --html --once` output contains the `PG-DASHLIVE provenance` marker and a recognizable `[LIVE]` or `[DEGRADED ...]` badge. | Smoke test fails if a future change strips the provenance comment or the source badge from rendered dashboards. |
| DASH8 Promote yfinance Fallback into get_live_market_overview | 🔜 READY | P1 | `terminal/tools.py` (`get_live_market_overview`, `_intraday_market_overview_from_pg`, `_yfinance_snapshot_from_intraday_candles`) | Audit the existing index-level vs stock-level fallback chains. Today, `get_intraday_market_recap` already falls back to PG (`_intraday_market_overview_from_pg`); `get_live_market_overview` itself does not yet have a yfinance fallback inside the tool — the new dashboard caller (DASH3) re-implements it. Promote DASH3's fallback into `get_live_market_overview` so every consumer benefits. | All callers of `get_live_market_overview` produce a populated `indices` map when NSE is blocked, without each caller reimplementing the fallback; existing tests still pass. |

### Agent Model Benchmark Remediation Backlog — 2026-05-12

Derived from:
- `reports/model_benchmarks/agent_model_benchmark_20260512_032630.md` — 52-scenario OpenAI/Ollama comparison.
- `reports/model_benchmarks/agent_model_benchmark_20260512_102408.md` — 30 complex multi-step workflow comparison.

| Item | Status | Priority | Files | Design / Implementation | Acceptance Criteria |
|---|---|---|---|---|---|
| L2 Final answer symbol validator | 🔜 READY | P0 | `terminal/agent.py`, `nse_agent.py` | Before rendering any agent response, compare requested symbols with symbols in tool traces and final text. If required symbols are missing or unrequested symbols appear, replace the answer with a validation failure that lists missing evidence and the source trail. | Responses for explicit symbol prompts contain every requested symbol and no forbidden substitutes such as `TALBROAUTO`, `QGOLDHALF`, `VERANDA`, or `NIVABUPA`. |
| L3 Deterministic multi-symbol workflows | 🔜 READY | P0 | `terminal/agent.py`, `terminal/tools.py`, `nse_agent.py` | Route compare, portfolio, peer battle, and watchlist prompts to deterministic multi-symbol tools. For each requested symbol, resolve or explicitly mark unresolved; never let the LLM pick replacement peers. | `DMART/TRENT/VBL`, `RELIANCE/TCS/HDFCBANK`, and `WELCORP/JINDALSAW` comparisons return table rows for all requested symbols or explicit missing rows. |
| L5 Required-tool intent plans | 🔒 IN PROGRESS | P0 | `terminal/agent.py`, `terminal/tools.py`, benchmark harness | Define mandatory tools per intent: Stage 2 -> `run_screener_query`; intraday -> NSE snapshot first then yfinance fallback; options -> option chain + futures + strategy when asked; catalysts -> catalyst/search tools; forensic -> forensic score sources. | Benchmark required-tool checks pass for screeners, intraday, options, catalysts, forensic, and report flows. |
| L6 Source-backed claim gating | 🔜 READY | P1 | `terminal/agent.py`, `terminal/tools.py`, `company_intelligence_search.py` | Add a missing-evidence matrix to every market answer. Broker targets, concalls, catalysts, forensic red flags, and sector conclusions must cite a tool/source result or be labeled unavailable. | No answer claims broker/concall/catalyst/forensic detail when the corresponding tool returns no data. |
| L7 Sector, macro, and policy workflow routing | 🔜 READY | P1 | `terminal/agent.py`, `terminal/tools.py`, company KB loaders | Route sector analysis, RBI/Budget impact, and policy questions to dedicated workflows instead of stock brief fallback. Include impacted sectors, companies, data freshness, and missing sources. | IT sector, RBI policy, Budget impact, HDFCBANK/SBIN policy prompts include requested terms and source trail. |
| L8 Ollama safety policy | 🔜 READY | P1 | `terminal/agent.py`, `/model` docs, benchmark harness | Keep Ollama available, but prefer deterministic routes and short prompts. Add timeout/fallback guidance: when Ollama times out or omits required tools, fall back to deterministic/OpenAI execution where configured. | Ollama benchmark has fewer timeouts and does not emit raw/pseudo tool JSON as final answers. |
| L9 Benchmark harness realism | 🔜 READY | P2 | `scripts/maintenance/benchmark_agent_models.py`, `nse_agent.py` | Add strict `/ric` execution tests, real index-universe scan tests for NIFTY BANK/MIDCAP 100, and code-assimilation tests that pass file excerpts rather than only conceptual prompts. | Rerun produces a report that separates model failure from harness limitations. |
| L10 Report metadata and evidence coverage | 🔜 READY | P2 | `terminal/reports.py`, report generators | Add DB snapshot timestamp, row counts, missing field counts, and source manifest to deterministic reports. Keep LLM narratives constrained to verified report data. | Generated Markdown/HTML reports show freshness and missing-data coverage without relying on LLM inference. |

### Strategy Council Simulation Backlog — 2026-05-14

| Item | Status | Priority | Files | Design / Implementation | Acceptance Criteria |
|---|---|---|---|---|---|
| SC10.1 Results, Filing, News, and Sentiment Evidence Completion | 🧩 PARTIAL | P0 | `backtesting/strategy_council/evidence.py`, `backtesting/strategy_council/evidence_enrichment.py`, `backtesting/strategy_council/evidence_filings.py`, `backtesting/strategy_council/tool_router.py`, `terminal/results_tools.py`, `terminal/company_evidence_tools.py`, tests | Foundations exist for latest-results, filing summaries, company evidence, and tool routing. Remaining work is to wire them consistently into `EvidencePack`, missing-data accounting, Markdown, dashboard, and recommendation gates. | Reports for symbols with available PostgreSQL fundamentals/results/filings no longer list those fields as missing; missing optional evidence includes attempted source, freshness, and failure reason. |
| SC14.1 Validation-Based Recommendation Gate | 🔜 READY | P0 | `backtesting/strategy_council/council.py`, `backtesting/strategy_council/llm.py`, `backtesting/strategy_council/report.py`, tests | Add a hard recommendation policy over validation results, critic verdicts, trade count, and one-shot test. A positive test cannot override negative/empty validation by itself. | Runs like recent `DMART`/`GESHIP` reports are labeled `WAIT` or `RESEARCH_ANOMALY` when validation is negative but test is positive; `TRADE_RESEARCH` requires positive validation, sufficient trades, and no blocking critic verdicts. |
| SC15 Multi-Timeframe Evidence Pack | 🔜 READY | P0 | `backtesting/strategy_council/evidence.py`, `terminal/intraday_storage.py`, `backtesting/strategy_council/evidence_enrichment.py`, tests | Merge daily, weekly, and intraday evidence so the council can detect alignment or conflict between EOD strategy context and current intraday tape. | Evidence pack reports timeframe coverage, freshness, conflicts, and missing bars; recommendations can distinguish "daily bullish, intraday weak" from fully aligned setups. |
| SC16 Liquidity + Execution Cost Critics | 🔜 READY | P0 | `backtesting/strategy_council/critics_advanced.py`, `backtesting/strategy_council/runner.py`, tests | Estimate ADV participation, spread/slippage assumptions, and transaction-cost drag; reject or resize strategies whose edge disappears after realistic execution costs. | Candidate critique flags low-liquidity symbols, high turnover, and profit less than 2x estimated execution cost. |
| SC17 Performance Attribution + Walk-Forward Dashboard | 🔜 READY | P1 | `backtesting/strategy_council/dashboard_generator.py`, `backtesting/strategy_council/runner.py`, tests | Add rule-level P&L attribution, rolling metrics, drawdown segments, and walk-forward degradation charts to dashboards. | Dashboard shows which rules generated trades/P&L and whether validation/test performance degrades over time. |
| SC18 Rule Interaction Graph + Feature Importance | 🔜 READY | P2 | `backtesting/strategy_council/strategy_generator.py`, `backtesting/strategy_council/postgres_storage.py`, analytics tests | Mine persisted council history for rule co-occurrence, redundancy, and contribution to returns; bias future generation toward historically useful combinations. | Generator can rank rule families by historical contribution and avoid highly redundant rule bundles. |
| SC19 Robustness Analysis Suite | 🔜 READY | P2 | `backtesting/strategy_council/critics_advanced.py`, `backtesting/strategy_council/runner.py`, `backtesting/strategy_council/dashboard_generator.py`, tests | Add stress-period slicing, sensitivity analysis, Monte Carlo resampling, drawdown attribution, and regime decomposition beyond the current baseline. | Reports include robustness sections and critics can block strategies that only work in narrow or lucky slices. |
| SC20 Multi-Symbol Scale-Out + Cache + Audit | 🔜 READY | P3 | `backtesting/strategy_council/postgres_storage.py`, `backtesting/strategy_council/council.py`, CLI/terminal tests | Add multi-symbol orchestration, reusable backtest cache, portfolio-level run summaries, and an audit trail suitable for repeated research runs. | Batch council runs avoid duplicate work, persist all evidence/config hashes, and produce a symbol-by-symbol summary with failures isolated. |
| **Phase 4 — Branch A: Advanced Screeners** | | | |
| A1 Stage Analysis Screener | 🔜 READY | — | William O'Neil 4-stage classification; Stage 2 only buy zone |
| A2 Darvas Box Breakout | 🔜 READY | — | Box top/bottom detection; breakout + volume confirmation |
| A3 52W High Momentum | 🔜 READY | — | Near-high + rising RS; simpler variant of stage analysis |
| A4 Earnings Acceleration | ⏳ BLOCKED | — | Needs quarterly EPS series from Screener.in cash flow scrape |
| A5 Institutional Accumulation | ⏳ BLOCKED | — | Needs P1-2 (F&O OI buildup) + price analysis |
| A6 Turnaround Detector | 🔜 READY | — | Deep-dip + recovery pattern; uses existing indicators |
| A7 Quality Compounder | ⏳ BLOCKED | — | Needs 5-year P&L trend from Screener.in (source N) |
| A8 Hidden Champions | ⏳ BLOCKED | — | Needs A7 fundamentals + small-cap filter |
| **Phase 4 — Branch B: Index Reports** | | | |
| B2 Global Correlation Monitor | 🔜 READY | — | yfinance for SPX/HSI/Gold/Oil; rolling 30d correlation |
| B3 Sectoral Heat Calendar | 🔜 READY | — | 12×N_sectors heatmap of avg monthly returns |
| B4 FII/DII Flow Battle Tracker | ⏳ BLOCKED | — | Needs P1-3 (FII/DII flows) fully running |
| B5 Economic Cycle Tracker | 🔜 READY | — | P1-6 macro proxies ✅ + P1-1 regime detector ✅ |
| **Phase 4 — Branch C: Market Breadth** | | | |
| C1 McClellan Oscillator | 🔜 READY | — | Derives from Nifty500 constituent advance/decline data |
| C2 TRIN / Arms Index | 🔜 READY | — | Volume-weighted breadth; derives from existing OHLCV |
| C3 Sector Breadth Divergence | 🔜 READY | — | Sector-level % above 50/200DMA; divergence alerts |
| C4 Smart Money Flow Index | ⏳ BLOCKED | — | Needs P1-2 F&O + block deal data |
| **Phase 4 — Branch D: Deep Fundamentals** | | | |
| D1 DuPont Decomposition Engine | ⏳ BLOCKED | — | Needs 5-year P&L + balance sheet from Screener.in |
| D2 Earnings Quality Score | ⏳ BLOCKED | — | Needs CFO data from Screener.in cash flow scrape |
| D3 Business Cycle Positioning | 🔜 READY | — | P1-6 macro proxies ✅ |
| D4 Concall Sentiment NLP | 🔜 READY | — | Same as P2-5; BSE filings + LLM extraction |
| D5 Forensic Accounting Suite | ⏳ BLOCKED | — | Needs Screener.in 5-year P&L + balance sheet (source N) |
| D6 Competitive Moat Score | ⏳ BLOCKED | — | Needs D1 + D2 data; peer comparison data (source N) |
| **Phase 4 — Branch E: Company Analysis** | | | |
| E1 360° Company Dashboard | ⏳ BLOCKED | — | Needs D1–D6 data; E2 peer data; E4 events |
| E2 Peer Comparison Engine | ⏳ BLOCKED | — | Needs Screener.in peers scrape (source N) |
| E3 Management Quality Score | ⏳ BLOCKED | — | Needs P1-4 insider data + concall history (D4) |
| E4 Event-Driven Alert Engine | 🔜 READY | — | BSE/NSE corporate actions API (source M) |
| **Phase 4 — Branch F: Financial Filing Intelligence** | | | |
| F2 NSE/BSE Filing Discovery | 🔜 READY | — | Auto-discover latest financial-results filings by symbol/quarter; prefer Integrated Filing XBRL/iXBRL |
| F3 XBRL/iXBRL Parser + Canonical Facts | 🔜 READY | — | Parse structured tags into canonical financial facts with contexts/units |
| F4a Image-Only Filing OCR Fallback | 🔜 READY | — | HDFC Bank FY26 Q4 official results PDF is image-only; add OCR or alternate filing-source fallback before LLM analysis |
| F5 Reconciliation + Verification Agent | 🔜 READY | — | Reconcile XBRL facts against PDF tables; mark verified/partial/conflict |
| F6 LLM-Based Filing Analysis Agents | 🔜 READY | — | Numbers, balance sheet, cash flow, segment, risk, narrative agents over canonical evidence |
| F7 HTML + Markdown Filing Report Generator | 🔜 READY | — | Self-contained reports with evidence-backed metrics and disclaimer |
| F8 Terminal / Agent Adda Integration | 🔜 READY | — | `/filing` commands and NLP routes for direct-link and symbol-driven analysis |
| F9 Batch Earnings Intelligence | 💤 DEFERRED | — | Portfolio/watchlist/Nifty500 batch filing analysis after F2-F7 |
| **Phase 4 — Branch G: US / Global Market Intelligence** | | | |
| G8 Intraday US Extension | 💤 DEFERRED | — | Add US intraday scanning after daily US/global layer is stable |
| **Phase 4 — Branch H: Company + Sector X-Ray Intelligence** | | | |
| H1 Company Intelligence PostgreSQL Store | 🔜 READY | — | Create or migrate company, alias, source document, search run, evidence chunk, structured fact, sector entity, policy event, impact, and analysis-run tables in PostgreSQL. SQLite may remain only as a local FTS/cache layer with a clear boundary. |
| H2 Search Audit + Alias-Aware Query Builder | 🔜 READY | — | Store all queries, aliases, result counts, URLs, parse status, and failure reasons; fixes DMART-style no-result ambiguity and wrong-entity fallbacks such as USL resolving to an unrelated stock |
| H3 Evidence Classification + Knowledge Categories | 🔜 READY | — | Categorize evidence into business model, customer base, market share, competitors, operating model, RBI/Budget sensitivity, risks, and open questions |
| H4 Official/Internal/External Source Connectors | 🔜 READY | — | Tiered source collection: official evidence first, internal structured datasets second, external context third |
| H5 RBI + Budget Impact Mapping | 🔜 READY | — | Store policy events and map them to company sensitivities such as borrowing cost, demand, capex, FX, imports, exports, and commodity inputs |
| H6 Company X-Ray Deliberation Engine | 🔜 READY | — | Build bull/base/bear cases, disconfirming evidence, open questions, and strict/permissive evidence coverage logic |
| H7 Company X-Ray Markdown/HTML Reports | 🔜 READY | — | Analyst memo with evidence coverage, source table, business model, sector, competitors, market share, policy impact, and disclaimer |
| H9 DMART No-Result Regression Suite | 🔜 READY | — | Test failed broker/concall searches produce auditable gaps instead of generic unsupported prose |
| **Phase 4 — Branch I: Voice Copilot** | | | |
| I1 Voice Session Store + Manifest | 🔜 READY | — | Create local `data/voice_sessions/YYYY-MM-DD/voice_*` session folders with input audio, transcript, normalized query, full answer, spoken summary, response audio, and manifest |
| I2 Audio Capture + Audio File Input | 🔜 READY | — | Add microphone capture wrapper plus `--audio-file` validation/copy path; tests must use injected recorders and not require live microphone access |
| I3 Speech-to-Text Provider Abstraction | 🔜 READY | — | Add OpenAI transcription provider with injectable fake provider, clear no-API-key errors, and deterministic unit tests |
| I4 Query Normalization + Voice Persona | 🔜 READY | — | Convert spoken market questions into analysis-ready queries and produce concise risk-aware experienced-trader summaries for listening |
| I5 Agent Execution Orchestrator | 🔜 READY | — | Build `voice_copilot.py` to run capture, STT, Agent Adda query execution, spoken summary generation, TTS, and manifest persistence |
| I6 GPT Text-to-Speech Provider + Playback Path | 🔜 READY | — | Add `gpt-4o-mini-tts` wrapper with persona `instructions`, `cedar` default voice, macOS `say` fallback, and provider injection for tests; print response audio path and play command |
| I7 `/ask-voice` Terminal Command | 🔜 READY | — | Add parser and terminal route for `/ask-voice`, `--seconds`, `--audio-file`, `--confirm`, `--no-audio`, and `--voice` |
| I8 Voice Error Handling + Privacy Audit | 🔜 READY | — | Ensure missing mic, missing API key, STT failure, agent failure, and TTS failure return structured errors and save local audit artifacts |
| I10 OpenAI Realtime Speech-to-Speech Mode | 🔜 READY | — | Upgrade `/voice-live` from sequential STT→Agent→TTS to low-latency Realtime API speech-to-speech with transcript events, VAD/turn detection, interruption handling, and tool-call routing |
| I11 Voice Assistant Human Interaction Polish | 🔜 READY | — | Add richer conversational memory, interruption phrases, greeting/closing variants, follow-up intent capture, timeout reprompts, and clearer terminal status transitions |
| **Phase 4 — Branch J: Startup Data Readiness + No-Assumption Guardrails** | | | |
| J7 `/load` Command Catalog + Script Mapping | 🔜 READY | — | Add a static catalog of vetted ETL jobs mapped to existing Python/R scripts; avoid runtime `--help` introspection because several scripts execute work on import/argument parse |
| J8 `/load` Terminal Orchestrator | 🔜 READY | — | Add `/load prompts`, `/load dry-run`, `/load incremental`, `/load full`, `/load status`, and `/load stop` with async execution, log paths, and deterministic terminal output |
| J9 Source-Specific `/load` Jobs | 🔜 READY | — | Map NSE, FII/DII, F&O, events, insiders, macro, global, index, breadth, reports, screeners, and PostgreSQL views to their existing loaders |
| J10 Fundamental + Screener Score Loading | 🔜 READY | — | Wire Screener R loaders, canonical symbols files, canonical output paths, comprehensive score rebuild, and score coverage reporting |
| J11 Company KB Loading Adapter | 🔜 READY | — | Expose stale-only and symbol-specific company website/IR indexing through `/load kb`; add CLI/API adapter where backend modules are not directly executable |
| J12 Load-Aware Agent Impact Guardrails | 🔜 READY | — | Connect `/load` outcomes to answer freshness, voice confirmations, no-assumption behavior, and agent workstream dependencies |
| **Phase 4 — Branch K: EOD Strategy Lab + Backtesting Engine** | | | |
| K3 Vectorized EOD Backtest Engine | 🔒 IN PROGRESS | Codex | Added deterministic Stage 2 next-open engine, no-lookahead tests, trade records, skipped records, computed Stage 2 features from raw NSE OHLCV, and real-symbol runs; remaining strategies/stops/targets pending |
| K4 Portfolio Simulator + Risk Controls | 🔒 IN PROGRESS | Codex | Added initial cash/allocation position sizing with non-negative cash tests; max positions, sector caps, and drawdown tracking pending |
| K5 Metrics + Attribution Layer | 🔒 IN PROGRESS | Codex | Added basic metrics in the Stage 2 engine: trade count, total P&L, ending capital, total return, win rate, average winner/loser; advanced CAGR/drawdown/attribution pending |
| K6 Backtest PostgreSQL Store | 🔒 IN PROGRESS | Codex | Added `backtesting/storage.py`, Postgres schema creation, run/trade/metric/skipped persistence, latest-run report reader, mocked tests, and real local `--persist` + report smoke tests; daily equity persistence pending |
| K7 Backtest Reports | 🔜 READY | — | Generate Markdown/HTML reports with summary, equity curve, drawdown, trade table, skipped-data audit, and strategy explanation |
| K8 Terminal Commands | 🔒 IN PROGRESS | Codex | Added `/backtest list`, `/strategy-lab validate`, `/backtest run stage2 --data <csv>`, `/backtest run stage2 --symbol <SYMBOL>`, full-universe guardrail, `--persist`, and `/backtest report latest`; stock/compare/HTML report commands still pending |
| K9 Existing Script Adapters | 🔜 READY | — | Register existing R/Python backtest scripts as reference/adaptor jobs without making them the primary engine |
| K10 Regression + Golden Backtests | 🔜 READY | — | Add fixture data, known-trade golden tests, metrics tests, terminal command tests, and no-assumption skipped-data tests |
| K11 Technical Pattern Feature Library | 🔒 IN PROGRESS | Codex | Added `backtesting/patterns.py` with `PatternSignal`, SMA/ATR/RSI/range/volume features, and initial auditable VCP detector; remaining pattern families pending |
| K12 VCP / Darvas / Squeeze Strategy Pack | 🔜 READY | — | Add volatility contraction, Darvas box, tight base, Bollinger squeeze, NR7, and inside-bar compression strategies with confidence scoring |
| K13 Chart Pattern Strategy Pack | 🔜 READY | — | Add head-and-shoulders, inverse head-and-shoulders, cup-and-handle, double top/bottom, triangle, flag, and pennant detectors with strict audit output |
| K14 Exit Strategy Lab | 🔜 READY | — | Backtest exit-only rules including Supertrend trailing exit, ATR trailing stop, SMA50 break, Stage 2 exit, time stop, and partial profit rules |
| K15 Pattern Backtest QA + Visual Evidence | 🔜 READY | — | Add golden fixtures, synthetic-pattern tests, false-positive tests, and optional chart snapshots showing detected pattern windows |

### Agent Pipeline Architecture Refactor Backlog — 2026-05-25

Source: end-to-end code review of `nse_agent.py` / `terminal/agent.py` Stages 0–7, followed by a critical validation pass against the actual code. All line numbers refer to the current main branch. Tag: `AA-AR`.

**Coordination note:** AA-AR-2 (named pipeline stages) touches the same `_query_single` function body as AA-UR-6 Phase 2/3 (route migration). AA-UR-6 Phase 2 is now ✅ DONE — AA-AR-2 is unblocked.

| Item | Status | Priority | Files | Design / Implementation | Acceptance Criteria |
|---|---|---|---|---|---|
| AA-AR-1 Central CommandRegistry | ✅ DONE | P0 | `nse_agent.py`, `terminal/command_registry.py` | `CommandHandler` dataclass + `CommandRegistry` in `terminal/command_registry.py`. Registry built lazily in `nse_agent._build_command_registry()` and shared via `_get_shared_registry()`. `_single_query` dispatches through registry (12 handlers: help, commands, scan, strategy-council, backtest, data-coverage, visual-scan, doctor, mtf, strength, email, open-last-report). `_pending_email_pipe` state machine remains in `_chat_loop`. | `_single_query` dispatches 12 shared commands through registry; duplicate imperative branches removed; adding a new shared command requires one `registry.register()` call. |
| AA-AR-2 Named Pipeline Stages in `_query_single` | ✅ DONE | P0 | `terminal/agent.py` | Added `_PipelineCtx` dataclass (mutable per-turn state: `clean_input`, `mode`, `source_label`, `mode_suffix`, `trace`, etc.). `_query_single` is now a 20-line pipeline dispatcher calling five named stage methods: `_stage_clarification_binding`, `_stage_unified_router`, `_stage_entity_topic`, `_stage_situation_assessment`, `_stage_keyword_and_llm`. Each stage returns `dict \| None`; the first non-None result wins. Added `_build_pipeline_ctx` (mode detection, mode_context, mode_suffix) and `_with_readiness_metadata` (replaces the former inner function). The legacy body is preserved as `_query_single_LEGACY` for reference until AA-UR-6 Phase 3 removes it. | 1250/1250. Zero behavior change — pure structural refactor. |
| AA-AR-3 Grounded-Scan Intent Registry + Guard Contract | ✅ DONE | P0 | `terminal/agent.py` | `_GROUNDED_SCAN_INTENTS: frozenset[str]` extracted as module-level constant. Hallucination guard uses `_GROUNDED_SCAN_INTENTS`; keyword-path gate set remains separate (covers `greeting`, `youtube_*`, `stock_brief`, etc.). Two sets serve distinct roles and are not merged. | `_GROUNDED_SCAN_INTENTS` is module-level; hallucination guard and keyword-path gate reference their respective sets; no routing behaviour changed. |
| AA-AR-4 Fix Double Symbol Resolution on Entity-Topic Queries | ✅ DONE | P0 | `nse_agent.py`, `terminal/agent.py` | `entity_assessment=None` optional kwarg added to `Agent.query()` and `Agent._query_single()`. `_query_single` skips `assess_entity_topic_request(clean_input)` when kwarg is provided. `_run_with_spinner` forwards kwarg; REPL loop initialises `_entity_assessment = None` and passes it through. | `assess_entity_topic_request` called once per entity-topic turn (not twice); no regression in entity-topic routing. |
| AA-AR-5a Structured Logging — `terminal/agent.py` | ✅ DONE | P1 | `terminal/agent.py` | `import logging` + `logger = logging.getLogger(__name__)`. Silent exceptions in `_build_context_pack`, `_remember_interaction`, `_with_readiness_metadata`, `classify_grounded_intent`, and hallucination guard replaced with `logger.debug("...", exc_info=True)`. | DEBUG log on PG failure in `_build_context_pack`; no bare `except: pass` without paired logger call. |
| AA-AR-5b Structured Logging — `nse_agent.py` | ✅ DONE | P1 | `nse_agent.py` | `import logging` + `logger = logging.getLogger(__name__)`. Key silent exceptions replaced: entity assessment REPL block, `_remember_terminal_interaction`, `_remember_ric_sequence_interaction`, alert autodisplay thread, console export. | No silent exception swallowing in key pipeline paths; exceptions produce DEBUG/WARNING log entries. |
| AA-AR-5c Structured Logging — router and memory modules | ✅ DONE | P1 | `terminal/router/router.py`, `terminal/conversation_memory.py`, `terminal/situation_assessment.py` | `logger = logging.getLogger(__name__)` added to all three modules. Router provider exception isolation logs at DEBUG level. Memory persistence failures log at WARNING level. | Router provider exceptions visible in DEBUG log; memory failures at WARNING; behaviour unchanged. |
| AA-AR-6a Clarification Reply Typo Re-prompt | ✅ DONE | P1 | `terminal/agent.py` | Re-prompt path added: if `_pending_clarification` is active and input is ≤ 3 chars with no space (typo-like), `render_assessment_block(pending_clarification)` is re-rendered and returned with `include_in_history=False`. Multi-word input clears state and routes normally. | Short tokens re-render clarification options; full questions clear state and route. |
| AA-AR-6b Clarification Reply Bookkeeping Extraction | ✅ DONE | P1 | `terminal/agent.py` | `_finalize_clarification_turn(answer, tool_results_, turn_context_=None, include_in_history=True)` inner helper extracted. All three clarification-reply branches and re-prompt path call it. | Single helper for all clarification bookkeeping; adding a new decision branch requires one call to `_finalize_clarification_turn`. |
| AA-AR-7 `mode_suffix` Static-Override Dict | ✅ DONE | P2 | `terminal/agent.py` | `_INTENT_SOURCE_LABEL_OVERRIDES: dict[str, str]` and `_INTENT_MODE_LABEL_OVERRIDES: dict[str, str]` module-level constants cover 7 static overrides. Single dict lookup replaces 7 non-elif if blocks. Runtime recalculations at intraday keyword-path (depends on `tool_results`) preserved and commented. | One dict lookup for 7 static overrides; runtime recalculations intact; no behaviour change. |
| AA-AR-8 Exclude Refused Turns from LLM History | ✅ DONE | P2 | `terminal/agent.py` | `include_in_history: bool = True` parameter added to `_remember_interaction`. Hallucination-guard return site passes `include_in_history=False`. PG audit persistence unaffected. | Refused turns absent from `self._history`; PG persistence fires; normal turns unaffected. |
| AA-AR-9 Verify Primary Symbol Extraction Path Applies Finance-Term Exclusions | ✅ DONE (audit) | P2 | `terminal/entity_resolution.py` | Code audit confirmed: `_requested_symbol_tokens()` at line 376 already applies `TECHNICAL_NON_SYMBOL_TERMS` (RSI, EBITDA, ATR, etc.) and `CONTEXT_NON_SYMBOL_TERMS` in the primary path. No code change required; primary path already correct. | Primary path confirmed correct via code audit; EBITDA/ROE/ATR/PE already excluded before `validate_requested_symbols` returns. |
| AA-AR-10 Compound Query Context Isolation | ✅ DONE | P2 | `terminal/agent.py` | Snapshot `_pre_symbols = list(self._last_symbols)` and `_pre_context = self._last_turn_context` before compound loop. Restore both before each sub-query call so each sub-query sees pre-compound state for pronoun resolution and situation assessment. | Each sub-query in a compound prompt sees the pre-compound context snapshot; no context contamination across sub-queries. |
| AA-AR-11 Replace `"Mode:"` Substring Search with Structured Flag | ✅ DONE | P2 | `terminal/agent.py` | `_llm_query()` returns `has_source_trail: bool` in result dict (True when `_Mode:` or `Mode: ` appears in last 300 chars). `_query_single` checks `result.get("has_source_trail", False)` instead of substring scan on last 600 chars. | `mode_suffix` never double-appended; responses >600 chars with early `Mode:` receive exactly one suffix append. |

### Claude Code–Inspired Enhancement Backlog — 2026-05-25

The AA-CM series (items AA-CM-1 through AA-CM-22 in the routing backlog above) directly mirrors Claude Code session management capabilities. Now that AA-HSR (symbol resolution) and AA-UR (unified router) are largely complete, these are the recommended next enhancements. Recommended pick-up sequence based on declared dependencies:

| Priority | Item | Why this is next | Unlocks |
|---|---|---|---|
| 1 | AA-CM-16 First-Class Tool Call Blocks | Normalises tool call/result format across backends — prerequisite for transcript replay and evidence ledger | AA-CM-14, AA-CM-20 |
| 2 | AA-CM-1 Canonical LLM Context Builder | Wires `ConversationMemory` + `ContextPack` into every backend call — closes the PG memory gap after restarts | AA-CM-2, AA-CM-3, AA-CM-5, AA-CM-7, AA-CM-8 |
| 3 | AA-CM-14 Full Typed Session Transcript Log | Append-only JSONL session log — replay/audit substrate for everything downstream | AA-CM-15, AA-CM-20 |
| 4 | AA-CM-22 Prompt Fragment Registry + System Reminders | Replaces monolithic system prompt with named fragments + runtime injections (stale data, low-confidence resolution, F&O missing evidence) — mirrors Claude Code `<system-reminder>` pattern | AA-CM-17, AA-CM-18 |
| 5 | AA-CM-2 Rolling Conversation Compaction | Durable rolling summary so long sessions retain context after history trim | AA-CM-9 |
| 6 | AA-CM-3 Cross-Turn Tool Evidence Ledger | Compact evidence records from prior tool results injected into LLM context — closes the "tool results visible only within one `_llm_query` loop" gap | AA-CM-6 |
| 7 | AA-CM-4 Active Task State | Persists context for non-market workflows (email pipe, data load, implementation sessions) across restarts | AA-CM-9, AA-CM-10 |
| 8 | AA-CM-7 Workspace Rules + Memory Index | Claude Code–style behavioral rules file + typed memory index for operator preferences | — |

Items AA-CM-5, AA-CM-8, AA-CM-9 through AA-CM-15, and AA-CM-17 through AA-CM-21 follow naturally from the above spine and are individually self-contained once their stated dependencies land. Start with AA-CM-16 → AA-CM-1 → AA-CM-14 as the critical path.

---

## 0.1 BRANCH J DETAILED DESIGN — STARTUP DATA READINESS

### Problem Statement

Agent Adda currently answers from `data/sector_rotation_tracker.db` and related cached files, but startup does not explicitly verify that the latest technical and fundamental data is present before the agent is marked ready. This can lead to stale or partial data being used silently, or the LLM filling gaps with assumed values.

### Design Goals

1. **Validate before ready:** On `nse_agent.py` startup, inspect the database and print the latest available technical/fundamental snapshot before normal chat begins.
2. **Load missing data first:** If the DB is missing, stale, or has insufficient coverage, run the existing refresh pipeline before answering user queries.
3. **Never assume missing fields:** If refresh cannot populate a field, responses must show `not found in DB` / `missing_evidence` rather than inferring technical, CANSLIM, or fundamental values.
4. **Bounded startup cost:** Startup refresh must use existing refresh commands with clear progress and failure reporting. If refresh fails, the agent still opens with a warning and stale-data banner.
5. **Testable without live NSE calls:** Readiness detection and refresh planning must be unit-testable with temporary SQLite DBs and mocked subprocess calls.

### Data Readiness Checks

Primary DB: `data/sector_rotation_tracker.db`

Primary table: `stage_snapshots`

Required columns:
- technical: `stage`, `stage_score`, `technical_score`, `rsi`, `relative_strength`, `trading_signal`, `supertrend_state`, `price`, `price_date`
- fundamental: `enhanced_fund_score`, `earnings_quality`, `sales_growth`, `financial_strength`, `institutional_backing`, `can_slim_score`, `investment_score`
- audit: `snapshot_date`, `symbol`, `company_name`, `source_csv`

Freshness policy:
- `latest_snapshot_date` must be the latest available trading snapshot in DB.
- If current local date is a market holiday/weekend and the latest trading snapshot is within 3 calendar days, classify as `fresh_trading_day`.
- If latest snapshot is older than 3 calendar days, classify as `stale`.
- If no rows exist, classify as `missing`.
- Fundamental coverage is separate from technical freshness. A technically fresh DB with low fundamental coverage is `partial_fundamentals`, not `fresh`.

Coverage thresholds:
- technical coverage: at least 95% of latest snapshot rows must have non-null `technical_score`, `rsi`, `relative_strength`, and `trading_signal`
- fundamental coverage: at least 30% of latest snapshot rows must have non-null `enhanced_fund_score`, `financial_strength`, and `can_slim_score` initially, because current DB coverage is partial; raise this threshold after full-universe fundamentals are stable
- exact counts must be printed, for example: `Fundamentals: 356/1018 stocks with enhanced score`

### Refresh Behavior

Readiness service returns a plan, not just a boolean:

| Condition | Action |
|---|---|
| DB file missing | run `python daily_refresh.py --skip-aux` |
| `stage_snapshots` empty | run `python daily_refresh.py --skip-aux` |
| latest snapshot stale | run `python daily_refresh.py --skip-aux` |
| technical coverage below threshold | run `python daily_refresh.py --skip-aux` |
| fundamental coverage below threshold | run `python daily_refresh.py --skip-aux` because `fixed_nse_universe_analysis.py` feeds tracker fundamentals |
| refresh command fails | continue startup, mark readiness `degraded`, print failure command + exit code |

Startup controls:
- default: readiness check enabled
- `--skip-readiness`: skip startup validation for fast local debugging
- `--readiness-no-refresh`: check and print status, but do not run refresh
- environment override: `AGENT_ADDA_SKIP_READINESS=1`

### User-Facing Startup Output

At startup, before `✓ Agent Adda ready`, print a compact panel:

```text
Data Readiness
Technical DB: 2026-05-08 · 1018 stocks · 100% technical coverage
Fundamental DB: 2026-05-08 · 356/1018 enhanced fundamentals · partial
Status: fresh_trading_day / partial_fundamentals
Action: no refresh needed
```

If refresh runs:

```text
Data Readiness
Status: stale snapshot 2026-05-03
Action: running python daily_refresh.py --skip-aux
Result: refreshed to 2026-05-08 · 1018 stocks
```

If refresh fails:

```text
Data Readiness
Status: degraded
Action failed: python daily_refresh.py --skip-aux exited 1
Agent will answer with stale-data warnings and missing fields will not be inferred.
```

### Answer Guardrails

When a response depends on data from `stage_snapshots`, tools must include freshness metadata:

```python
{
  "data_readiness": {
    "status": "fresh_trading_day",
    "latest_snapshot_date": "2026-05-08",
    "technical_coverage_pct": 100.0,
    "fundamental_coverage_pct": 35.0,
    "warnings": ["partial_fundamentals"]
  }
}
```

Rules for agent responses:
- If `data_readiness.status` is `stale`, `missing`, or `degraded`, the first paragraph must mention it.
- If a requested metric is null, print `not found in DB`.
- If a ranking uses partial fundamentals, label the ranking as `technical-first with partial fundamentals`.
- CANSLIM, Piotroski, forensic, and fundamental scores must only be shown when returned by tools. They must not be generated by LLM prose.

---

## 0.2 BRANCH J IMPLEMENTATION STEPS

### J1 — Data Readiness Service

**Files to create / modify**
- Create: `terminal/data_readiness.py`
- Test: `tests/test_data_readiness.py`

**Implementation**
- Add `DataReadinessStatus` dataclass with fields:
  - `db_path`
  - `latest_snapshot_date`
  - `latest_price_date`
  - `total_rows`
  - `technical_complete_rows`
  - `fundamental_complete_rows`
  - `technical_coverage_pct`
  - `fundamental_coverage_pct`
  - `status`
  - `warnings`
  - `refresh_recommended`
  - `refresh_reason`
- Add `inspect_data_readiness(db_path: Path = DB_PATH, today: date | None = None) -> DataReadinessStatus`.
- Use SQLite queries against only the latest `snapshot_date`.
- Treat missing DB/table/rows as structured statuses, not exceptions.

**Acceptance criteria**
- A fresh fixture DB returns `status in ("fresh", "fresh_trading_day", "partial_fundamentals")`.
- A missing DB returns `status="missing"` and `refresh_recommended=True`.
- A stale DB returns `status="stale"` and `refresh_recommended=True`.
- A DB with missing fundamental columns returns `partial_fundamentals` and exact missing coverage counts.

### J2 — Refresh Planner + Executor

**Files to create / modify**
- Modify: `terminal/data_readiness.py`
- Test: `tests/test_data_readiness.py`

**Implementation**
- Add `build_refresh_plan(status: DataReadinessStatus) -> list[list[str]]`.
- Add `execute_refresh_plan(plan: list[list[str]], timeout_sec: int = 1800) -> dict`.
- Default command for stale/missing data:
  - `python daily_refresh.py --skip-aux`
- Use `sys.executable` instead of hardcoded `python`.
- Capture return code and elapsed seconds.
- Do not hide refresh failures; return structured `{"ok": False, "command": ..., "returncode": ...}`.

**Acceptance criteria**
- Missing DB produces one refresh command.
- Fresh DB produces empty refresh plan.
- Mocked successful subprocess returns `ok=True`.
- Mocked failed subprocess returns `ok=False` without raising.

### J3 — Startup Terminal Integration

**Files to create / modify**
- Modify: `nse_agent.py`
- Test: `tests/test_nse_agent_data_readiness.py`

**Implementation**
- Add CLI flags:
  - `--skip-readiness`
  - `--readiness-no-refresh`
- Before printing `✓ Agent Adda ready`, call `inspect_data_readiness()`.
- If refresh is recommended and refresh is not disabled, call `execute_refresh_plan()`, then re-inspect readiness.
- Render a compact Rich panel with latest snapshot date, row count, technical coverage, fundamental coverage, status, and action.
- Respect `AGENT_ADDA_SKIP_READINESS=1`.

**Acceptance criteria**
- `python nse_agent.py --no-briefing --skip-readiness -q "/strength MANINDS"` does not run readiness.
- With mocked stale readiness, startup calls refresh executor before agent ready.
- With mocked refresh failure, startup prints degraded warning and still initializes.

### J4 — Agent Metadata + No-Assumption Guardrails

**Files to create / modify**
- Modify: `terminal/tools.py`
- Modify: `terminal/agent.py`
- Test: `tests/test_agent_data_guardrails.py`

**Implementation**
- Add a helper in `terminal/tools.py`: `attach_data_readiness(result: dict) -> dict`.
- Apply it to tools that read `stage_snapshots`, including:
  - `get_symbol_snapshot`
  - `get_technical_setup`
  - `run_screener_query`
  - `validate_strength_watchlist`
  - `compare_stocks`
- Update `SYSTEM_PROMPT` in `terminal/agent.py`:
  - If tool result contains stale/degraded readiness, disclose it.
  - If requested metric is null/missing, say `not found in DB`.
  - Do not invent fundamental/CANSLIM/Piotroski values.
- Extend no-LLM synthesis paths to include readiness warnings.

**Acceptance criteria**
- Screener output includes `data_readiness`.
- Strength validation still reports `missing_evidence` for missing fundamentals.
- A mocked missing `enhanced_fund_score` appears as `not found in DB`, not as an invented score.

### J5 — `/data-status` and `/refresh-data` Commands

**Files to create / modify**
- Modify: `nse_agent.py`
- Test: `tests/test_nse_agent_data_readiness.py`

**Implementation**
- Add slash commands:
  - `/data-status`: print readiness panel only
  - `/refresh-data`: run refresh plan regardless of stale status, then print post-refresh status
  - `/refresh-data --no-aux`: run `daily_refresh.py --skip-aux`
- Add command browser entries and help text.
- Keep deterministic: these commands do not call the LLM.

**Acceptance criteria**
- `/data-status` prints latest DB date and coverage.
- `/refresh-data` calls refresh executor and re-inspects DB.
- Failed refresh prints command and return code.

### J6 — End-to-End Regression Suite

**Files to create / modify**
- Create: `tests/test_data_readiness_end_to_end.py`

**Implementation**
- Use temporary SQLite DBs with minimal `stage_snapshots` schema.
- Test startup readiness in single-query mode by monkeypatching readiness functions.
- Test a stale readiness warning appears in a no-LLM answer.
- Test `/strength` still refuses to infer missing fundamental evidence.

### J7-J12 — `/load` Model, ETL Catalog, and Cross-Agent Impact

**Objective**

Create a first-class terminal loading mode in `nse_agent.py` so users can discover and run vetted ETL jobs without remembering Python/R script names. The `/load` layer should orchestrate existing loaders; it must not duplicate ETL logic or silently invent data when a loader cannot populate a field.

**User-facing command family**

| Command | Purpose | Primary mapping |
|---|---|---|
| `/load prompts` | Show available loading prompts/jobs grouped by domain | Static in-code catalog |
| `/load dry-run` | Validate the daily refresh plan without writing data | `python3 daily_refresh.py --dry-run` |
| `/load incremental` | Run default incremental market refresh | `python3 daily_refresh.py` |
| `/load full` | Run comprehensive refresh including full analysis path | `python3 daily_refresh.py --comprehensive` |
| `/load live` | Refresh live-only prices and derived live state | `python3 daily_refresh.py --live-only` |
| `/load nse` or `/load bhavcopy` | Load latest NSE OHLCV/bhavcopy universe | `Rscript load_latest_nse_data_comprehensive.R` |
| `/load aux` | Run all auxiliary market loaders | FII/DII, F&O, events, insiders, macro scripts |
| `/load fii-dii` | Refresh institutional flow data | `python3 fetch_fii_dii_flows.py --force` |
| `/load fno` | Refresh futures/options data | `python3 fetch_fno_data.py --force` |
| `/load events` | Refresh corporate events | `python3 fetch_corporate_events.py --force` |
| `/load insiders` | Refresh insider/promoter alerts | `python3 fetch_insider_alerts.py --force` |
| `/load macro` | Refresh macro proxy data | `python3 fetch_macro_proxies.py --refresh` |
| `/load global` | Refresh US/global market intelligence and reports | `python3 global_market_intelligence.py --force --report` |
| `/load fundamentals` | Fetch Screener fundamental score dataset | `Rscript working-sector/fetch_screener_fundamentals.R <symbols_file> data/fundamental_scores_database.csv` |
| `/load fundamental-details` | Fetch detailed Screener fundamentals | `Rscript working-sector/fetch_screener_fundamental_details.R <symbols_file> working-sector/output/fundamental_details.csv` |
| `/load fundamentals-5yr` | Fetch 5-year Screener fundamentals | `Rscript working-sector/fetch_screener_5yr_fundamentals.R data/nifty500_symbols.txt` |
| `/load scores` or `/load comprehensive` | Rebuild comprehensive NSE scores/screens | `python3 fixed_nse_universe_analysis.py` |
| `/load snapshot` | Build current sector rotation snapshot | `python3 sector_rotation_tracker.py --snapshot` |
| `/load live-prices` | Update live prices for tracker | `python3 sector_rotation_tracker.py --update-live` |
| `/load reports` | Build HTML/Python reports | `python3 sector_rotation_tracker.py --report --html` and `python3 sector_rotation_report.py` |
| `/load index` | Build index intelligence report/cache | `python3 index_intelligence.py` |
| `/load breadth` | Build market breadth data/report | `python3 market_breadth.py` |
| `/load r-reports` | Build R index and sector reports | `Rscript analyze_all_indexes.R` and `Rscript analyze_all_sectors.R` |
| `/load screeners` or `/load views` | Refresh PostgreSQL screeners/materialized views | `python3 postgres/loader.py` initially; add flags later for views-only/screeners-only |
| `/load kb` | Refresh stale company website/IR knowledge base index | Backend company index job with `--stale-only --include-documents --seed-sitemap --respect-robots` semantics |
| `/load kb DMART` | Refresh one company website/IR knowledge base index | Backend company index command/API with `DMART --refresh --include-documents --seed-sitemap --respect-robots` semantics |
| `/load status` | Show active job, last run, latest logs, and exit code | Local run registry |
| `/load stop` | Stop the active background load job | Async process runner |

**Implementation notes**

- Use a static `LoadJob` catalog with repo-root-relative script paths, command arguments, job group, expected outputs, estimated runtime, write scope, and safety level.
- Do not discover commands by calling `--help` on unknown scripts. Some scripts, including full-universe analysis paths, may start processing when invoked with unexpected arguments.
- Use `sys.executable` for Python jobs and `Rscript` for R jobs. Validate missing scripts and missing `Rscript` before starting.
- Composite jobs should expand to a visible sequence before execution. `/load dry-run` must print the planned sequence and expected writes.
- Long-running jobs should run asynchronously with captured stdout/stderr under `logs/load_jobs/` or a similar project-local folder. `/load status` and `/load stop` should work without LLM calls.
- `/load fundamentals` must pass `data/fundamental_scores_database.csv` explicitly so the canonical score database remains under `data/`, aligned with the comprehensive NSE analysis code.
- `/load views` initially maps to `postgres/loader.py`; a follow-up should add `--views-only`, `--screeners-only`, and `--skip-data` flags if the loader currently refreshes more than requested.
- `/load kb` should call the existing company indexing backend through a stable adapter. If current modules are not direct CLI entrypoints, add a small CLI wrapper instead of relying on incidental module behavior.

**Cross-agent impact analysis**

| Workstream / agent capability | Impact of `/load` model | Required guardrail |
|---|---|---|
| Startup data readiness | `/load` becomes the operational mechanism behind manual and automatic refresh actions | Readiness can recommend a load job, but answers must still label stale/degraded data if the job fails |
| Strength validation / CANSLIM / Piotroski / fundamentals | Scores become reproducible because fundamentals and comprehensive score rebuilds have explicit commands | Never show CANSLIM, Piotroski, forensic, or fundamental values unless the DB/tool returns them |
| Company + Sector X-Ray / KB | `/load kb` provides the scheduled/stale indexing entrypoint for company websites, IR pages, filings, transcripts, and official docs | Keep crawls bounded by max pages, robots policy, document limit, and explicit refresh/stale-only controls |
| Voice Copilot | Voice can ask "load fundamentals" or "what is load status" and receive spoken progress summaries | Require confirmation before starting long-running or write-heavy loads from voice mode |
| US / Global market intelligence | `/load global` makes global data refresh explicit before global reports and cross-market answers | Surface cache timestamp and fail gracefully when yfinance/network calls fail |
| Financial filing intelligence | Future `/load filings` can reuse the same catalog pattern for annual reports, BSE filings, and document parsing | Avoid duplicate document stores; promote parsed evidence into the existing source/evidence schema |
| Market education / `/learn` commands | Education answers are mostly web/evidence driven, but examples may reference local metrics | If examples use live/local market values, attach freshness metadata |
| PostgreSQL materialized views | `/load views` gives a single terminal path to rebuild screeners and materialized views | Check database availability and dependency errors before running destructive or expensive operations |
| Repo cleanup / reorganization | Centralized catalog reduces future path breakage when scripts move | Store paths in one catalog and test every mapping after refactors |

**Acceptance criteria**

- `/load prompts` lists every command above with group, description, mapped script, expected output, and safety level.
- `/load dry-run` prints the exact command sequence and does not modify files.
- `/load status` reports no active job, running job, completed job, failed job, log path, and exit code.
- `/load stop` terminates only the active load job started by Agent Adda.
- Missing scripts, missing `Rscript`, missing PostgreSQL, and failed subprocesses produce actionable terminal errors.
- Unit tests cover catalog mappings, dry-run expansion, async status, stop behavior, and refusal to call unsafe discovery commands.

**Branch J regression acceptance criteria**
- Run:
  - `./.venv/bin/python -m unittest tests.test_data_readiness tests.test_nse_agent_data_readiness tests.test_agent_data_guardrails tests.test_strength_validation -v`
- Expected: all tests pass.
- Run:
  - `./.venv/bin/python -m py_compile terminal/data_readiness.py terminal/tools.py terminal/agent.py nse_agent.py`
- Expected: exit code 0.

---

## 0.3 BRANCH K DETAILED DESIGN — EOD STRATEGY LAB + BACKTESTING ENGINE

### Problem Statement

Agent Adda has strong EOD market data, signal generation, stage snapshots, fundamentals, regime context, and older backtesting scripts, but it does not yet have a first-class, queryable backtesting layer. Users need to test whether Stage 2, CANSLIM, Minervini, Supertrend, and pullback strategies actually worked across market regimes, sectors, and portfolios before trusting them in live monitoring or paper trading.

### V1 Scope

V1 is **EOD Indian equity backtesting only**. Intraday and F&O/options backtesting are explicitly out of scope for Branch K and should be added later after the EOD engine is stable.

Supported V1 strategies:
- Stage 2 uptrend breakout.
- CANSLIM quality + momentum filter.
- Minervini trend template.
- Supertrend continuation.
- RSI pullback inside Stage 2.
- 52-week high breakout.

Supported V1.5 technical strategies:
- VCP / volatility contraction breakout.
- Darvas box breakout.
- Tight base breakout.
- Bollinger Band squeeze breakout.
- NR7 / inside-bar compression breakout.
- Pullback to 20 DMA / 50 DMA inside an uptrend.

Supported V2 technical chart-pattern strategies:
- Head-and-shoulders breakdown.
- Inverse head-and-shoulders breakout.
- Cup-and-handle breakout.
- Double top breakdown.
- Double bottom breakout.
- Ascending / descending / symmetrical triangle breakout or breakdown.
- Flag / pennant continuation.

Supported exit-rule studies:
- Supertrend trailing exit.
- ATR trailing stop.
- SMA50 breakdown exit.
- Stage 2 exit.
- Time stop.
- Partial profit at R multiples.

Supported V1 commands:

```text
/backtest list
/backtest run stage2 --universe nifty500 --from 2022-01-01 --to today
/backtest run canslim --universe nifty500 --from 2022-01-01 --risk 1 --max-positions 20
/backtest run minervini --universe nifty500 --from 2022-01-01
/backtest run vcp --universe nifty500 --from 2022-01-01 --min-confidence 70
/backtest run darvas --universe nifty500 --from 2022-01-01
/backtest run supertrend-continuation --universe nifty500 --from 2022-01-01
/backtest stock DMART --strategy stage2 --from 2022-01-01
/backtest compare stage2 canslim minervini --universe nifty500 --from 2022-01-01
/backtest pattern DMART --pattern vcp --from 2022-01-01
/backtest exits stage2 --exit-rule supertrend-trailing --from 2022-01-01
/backtest report latest
/strategy-lab validate
```

### Architecture

Create a Python-first backtesting package so Agent Adda can run, store, compare, explain, and later speak backtest results.

Proposed files:
- `backtesting/data.py` — load EOD OHLCV, index data, stage snapshots, fundamentals, regime, and optional flow/macro data.
- `backtesting/strategy_registry.py` — registry of strategy definitions and rule metadata.
- `backtesting/patterns.py` — reusable EOD technical-pattern feature detectors.
- `backtesting/engine.py` — deterministic EOD simulator.
- `backtesting/portfolio.py` — capital allocation, position sizing, sector caps, rebalance, cash, and portfolio-level drawdown.
- `backtesting/metrics.py` — return/risk/expectancy/regime attribution metrics.
- `backtesting/storage.py` — SQLite persistence.
- `backtesting/report.py` — Markdown/HTML report generation.
- `backtesting/charts.py` — optional chart snapshots for detected pattern windows.
- `terminal/backtest.py` — terminal command parser and renderer.
- `tests/test_backtesting_*.py` — fixture, engine, metrics, storage, report, and terminal tests.

Existing scripts become adapters/reference implementations:
- `run_comprehensive_backtesting_all_stocks.R`
- `working-sector/phase4_backtest.py`
- archived historical backtesting scripts under `archive/`

Do not make the old R scripts the primary engine. They can be exposed through `/backtest legacy` later if needed.

### Data Contract

Required:
- EOD OHLCV: `data/nse_sec_full_data.csv`
- Index data: `data/nse_index_data.csv`
- Stage snapshots: `data/sector_rotation_tracker.db` / `stage_snapshots`
- Trading calendar inferred from available EOD dates.

Optional but strategy-dependent:
- Fundamental scores: `data/fundamental_scores_database.csv`, `data/_sector_rotation_fund_cache.csv`, or `stage_snapshots` fundamental columns.
- Regime: `regime_detector.py` outputs or signal log regime fields.
- FII/DII: `data/fii_dii_flows.csv`
- F&O: `data/fno_signals.csv`
- Macro: `data/macro_proxy_signals.csv`, `data/macro_sector_tailwind.csv`
- Signal outcomes: `data/signal_log.csv`, `resolve_signals.py`

No-assumption rules:
- If a strategy requires a missing metric, skip that symbol/date with a structured reason.
- If optional context is missing, run in the correct labeled mode, for example `technical-only`, `no-fundamental-filter`, or `no-regime-attribution`.
- CANSLIM, Piotroski, forensic, and fundamental fields must come from loaded data only.

### Strategy Definition Contract

Each strategy should define:
- `id`, `name`, `description`, `timeframe="EOD"`.
- Required fields.
- Universe eligibility rules.
- Entry condition.
- Exit condition.
- Stop rule.
- Target/trailing rule.
- Position sizing compatibility.
- Explainability labels, for example `entered_stage2`, `rs_above_threshold`, `price_above_sma200`.

Initial rule sketches:

| Strategy | Entry | Exit / risk |
|---|---|---|
| Stage 2 breakout | Stage 2, RS strong, price above key moving averages, breakout/near high | Exit on Stage 2 exit, Supertrend sell, stop loss, or trailing stop |
| CANSLIM | Stage 2 + earnings/sales/fundamental quality + RS | Exit on technical failure, fundamental filter deterioration, stop, or target/trail |
| Minervini | Price above SMA50/150/200, SMA trends aligned, near 52W high, RS strong | Exit on SMA50 break, stop, or trailing rule |
| Supertrend continuation | Supertrend buy, trend strength, volume confirmation | Exit on Supertrend sell or volatility stop |
| RSI pullback in Stage 2 | Stage 2, RS strong, RSI pullback then recovery | Exit on failed recovery, stop, target, or trend break |
| 52-week high breakout | Price breaks or closes near 52-week high with RS/volume confirmation | Exit on failed breakout, ATR stop, or trailing rule |
| VCP breakout | Higher lows, tightening ranges, contracting volume, breakout above pivot | Exit on failed pivot retest, ATR stop, or trailing rule |
| Darvas box breakout | Well-defined box high/low after consolidation, breakout above box high | Exit below box low, ATR stop, or trailing rule |
| Bollinger squeeze breakout | Bandwidth compression followed by close above upper band and volume expansion | Exit on close back inside range, ATR stop, or trailing rule |
| Head-and-shoulders breakdown | Left shoulder/head/right shoulder pivots, neckline break, volume confirmation | Exit on neckline reclaim, ATR stop, or measured-move target |
| Inverse head-and-shoulders breakout | Inverse pivot structure, neckline break, improving RS | Exit on neckline failure, ATR stop, or measured-move target |
| Cup-and-handle breakout | Rounded base, handle pullback, breakout above handle pivot | Exit on failed handle pivot, ATR stop, or trailing rule |

### Technical Pattern Catalog

Pattern detectors must be deterministic and auditable. Every detector returns a `PatternSignal` object, not a bare boolean.

```python
@dataclass
class PatternSignal:
    symbol: str
    pattern_id: str
    signal_date: date
    direction: Literal["bullish", "bearish", "neutral"]
    confidence: float
    entry_price: float | None
    stop_price: float | None
    target_price: float | None
    pivot_price: float | None
    start_date: date | None
    end_date: date | None
    evidence: dict[str, Any]
    rejection_reasons: list[str]
```

Required detector families:

| Family | Pattern IDs | Required features |
|---|---|---|
| Trend/momentum | `stage2`, `minervini`, `52w_high`, `ma_alignment`, `rs_leader` | SMA20/50/150/200, 52-week high/low, relative strength, volume trend |
| Supertrend | `supertrend_continuation`, `supertrend_reversal`, `supertrend_trailing_exit` | Supertrend state/value, ATR, close relation to band |
| Volatility contraction | `vcp`, `tight_base`, `darvas`, `bollinger_squeeze`, `nr7`, `inside_bar_compression` | ATR/range contraction, pivot highs/lows, volume contraction, breakout candle |
| Chart patterns | `head_shoulders`, `inverse_head_shoulders`, `cup_handle`, `double_top`, `double_bottom`, `ascending_triangle`, `descending_triangle`, `sym_triangle`, `flag`, `pennant` | Swing pivots, neckline/trendline, symmetry, depth, duration, breakout confirmation |
| Pullback / mean reversion | `rsi_pullback_stage2`, `dma20_pullback`, `dma50_pullback`, `bollinger_mean_reversion` | RSI, SMA distance, Stage 2 state, trend filter |
| Exit studies | `atr_trailing`, `sma50_break`, `stage2_exit`, `time_stop`, `partial_profit_r` | Stop distance, R multiple, holding period, trend state |

Confidence scoring:
- `0-49`: weak/no trade, report only if explicitly requested.
- `50-69`: watchlist-quality setup.
- `70-84`: tradable setup if liquidity/risk filters pass.
- `85-100`: high-quality setup; still requires backtest validation.

Pattern detectors must include rejection reasons, for example:
- `insufficient_history`
- `missing_volume`
- `range_not_contracting`
- `pivot_not_confirmed`
- `breakout_without_volume`
- `lookahead_required_rejected`
- `neckline_not_broken`
- `pattern_too_short`
- `pattern_too_deep`

### Simulation Rules

V1 simulator should be deterministic:
- Use next-session open or close-based entry policy, configurable per strategy.
- Default slippage: configurable basis points.
- Brokerage/fees: configurable flat or bps model.
- Position sizing:
  - fixed allocation,
  - equal weight,
  - fixed risk per trade using stop distance.
- Enforce:
  - max open positions,
  - max sector exposure,
  - minimum liquidity/volume,
  - no duplicate position in same symbol,
  - optional cooldown after stop-out.
- Record every skipped trade candidate with reason.

### Storage Schema

Use SQLite, either in a dedicated `data/backtesting.db` or namespaced tables in the main analytics DB.

Tables:
- `strategy_definitions`
- `backtest_runs`
- `backtest_run_config`
- `backtest_trades`
- `backtest_daily_equity`
- `backtest_drawdowns`
- `backtest_metrics`
- `backtest_skipped_candidates`
- `backtest_data_readiness`

Every run must store:
- code/config version,
- strategy id and parameters,
- data freshness metadata,
- universe,
- date range,
- created timestamp,
- status and failure reason if failed.

### Reports

Every run should produce:
- summary metrics,
- equity curve,
- drawdown curve,
- monthly/yearly return table,
- trade table,
- best/worst trades,
- sector attribution,
- market-regime attribution when available,
- skipped-data audit,
- strategy explanation.

Outputs:
- `reports/backtesting/YYYY/backtest_<strategy>_<timestamp>.md`
- `reports/backtesting/YYYY/backtest_<strategy>_<timestamp>.html`
- `reports/backtesting/latest/backtest_latest.html`

### Terminal Experience

Terminal output must be concise and deterministic:

```text
Backtest: stage2 · NIFTY500 · 2022-01-01 to 2026-05-08
Data: EOD fresh to 2026-05-08 · fundamentals partial · regime available
Result: CAGR 18.4% · Max DD -13.2% · Win rate 47% · Expectancy 1.34R · Trades 286
Report: reports/backtesting/latest/backtest_latest.html
```

For missing data:

```text
Backtest ran in technical-only mode.
Fundamental fields missing for 412/1018 symbols; CANSLIM filters were not applied to those rows.
Skipped candidates: 1286. See skipped-data audit in report.
```

### Cross-Agent Impact Analysis

| Workstream / agent capability | Impact of Strategy Lab | Required guardrail |
|---|---|---|
| `/load` orchestration | Backtests depend on `/load nse`, `/load fundamentals`, `/load scores`, and `/load views` being current | Backtest startup should call/read readiness, not silently use stale data |
| Startup readiness | Adds another consumer of technical/fundamental freshness metadata | Report data freshness in every run |
| Voice Copilot | Users can ask "Backtest Stage 2 on Nifty 500" and hear summary metrics | Require confirmation before long-running all-universe runs |
| Strategy monitors | Live monitors can be backed by historically tested strategies | Do not promote a monitor strategy unless a recent backtest exists or user overrides |
| Portfolio analyzer | Portfolio holdings can be tested against strategy rules and historical exits | Separate portfolio backtest from actual realized P&L |
| Company X-Ray / fundamentals | Fundamental filters become reusable in strategy rules | If company fundamentals are missing, skip or label technical-only |
| Learning loop | Backtest and resolved signal outcomes provide evidence for strategy ranking | Avoid overfitting; use walk-forward and out-of-sample validation before ranking strategies |

### Implementation Steps

#### K1 — Backtesting Data Contract + Readiness Gate

**Files to create / modify**
- Create: `backtesting/data.py`
- Create: `tests/test_backtesting_data.py`

**Implementation**
- Load EOD OHLCV, stage snapshots, index data, and optional fundamentals/regime/flow files.
- Add `BacktestDataReadiness` with latest dates, coverage counts, stale flags, and warnings.
- Reuse Branch J readiness concepts where possible.

**Acceptance criteria**
- Missing EOD data returns a structured blocking error.
- Missing fundamentals returns a warning and strategy-dependent skip behavior.
- Fixture data loads deterministically.

#### K2 — Strategy Registry

**Files to create / modify**
- Create: `backtesting/strategy_registry.py`
- Test: `tests/test_backtesting_strategy_registry.py`

**Implementation**
- Define `StrategyDefinition`.
- Register Stage 2, CANSLIM, Minervini, Supertrend continuation, and RSI pullback.
- Expose `list_strategies()` and `get_strategy(strategy_id)`.

**Acceptance criteria**
- `/backtest list` can render all registered strategies.
- Unknown strategy returns a clear error and available choices.

#### K3 — Vectorized EOD Backtest Engine

**Files to create / modify**
- Create: `backtesting/engine.py`
- Test: `tests/test_backtesting_engine.py`

**Implementation**
- Simulate daily entries/exits with deterministic ordering.
- Support next-open/next-close entry policy, stop loss, target, trailing stop, and max holding period.
- Store trade reasons and skipped-candidate reasons.

**Acceptance criteria**
- Golden fixture produces expected entries, exits, and P&L.
- No lookahead: signals from day T can only enter using day T+1 policy.
- Missing required fields skip trades instead of fabricating values.

#### K4 — Portfolio Simulator + Risk Controls

**Files to create / modify**
- Create: `backtesting/portfolio.py`
- Test: `tests/test_backtesting_portfolio.py`

**Implementation**
- Add capital, fixed allocation, equal weight, fixed-risk sizing, max positions, sector caps, and cash tracking.
- Track daily equity and drawdown.

**Acceptance criteria**
- Position count and sector caps are enforced.
- Cash never goes negative unless explicitly configured.
- Drawdown series matches fixture expectations.

#### K5 — Metrics + Attribution Layer

**Files to create / modify**
- Create: `backtesting/metrics.py`
- Test: `tests/test_backtesting_metrics.py`

**Implementation**
- Compute total return, CAGR, max drawdown, win rate, avg winner/loser, expectancy, Sharpe-like ratio, trade count, holding period, turnover, best/worst trades, sector attribution, and regime attribution.

**Acceptance criteria**
- Metrics match hand-calculated fixture results.
- Empty-trade runs return structured zero/NA metrics, not crashes.

#### K6 — Backtest SQLite Store

**Files to create / modify**
- Create: `backtesting/storage.py`
- Test: `tests/test_backtesting_storage.py`

**Implementation**
- Create SQLite schema and idempotent migrations.
- Persist run config, readiness metadata, trades, equity, drawdowns, skipped candidates, and metrics.

**Acceptance criteria**
- A run can be saved and loaded by run id.
- Latest run lookup works.
- Schema migration is idempotent.

#### K7 — Backtest Reports

**Files to create / modify**
- Create: `backtesting/report.py`
- Test: `tests/test_backtesting_report.py`

**Implementation**
- Generate Markdown and HTML reports.
- Include summary, curves, trades, attribution, skipped-data audit, and strategy explanation.

**Acceptance criteria**
- Report is created under `reports/backtesting/`.
- Latest alias is updated.
- Missing optional sections render as warnings, not broken HTML.

#### K8 — Terminal Commands

**Files to create / modify**
- Modify: `nse_agent.py`
- Create: `terminal/backtest.py`
- Test: `tests/test_nse_agent_backtest.py`

**Implementation**
- Add deterministic command routing for:
  - `/backtest list`
  - `/backtest run`
  - `/backtest stock`
  - `/backtest compare`
  - `/backtest report latest`
  - `/strategy-lab validate`
- Keep backtest commands non-LLM by default.

**Acceptance criteria**
- Single-query terminal mode can run list/validate against fixtures.
- Invalid args produce helpful usage.
- Long-running runs display log/report path.

#### K9 — Existing Script Adapters

**Files to create / modify**
- Create: `backtesting/legacy_adapters.py`
- Test: `tests/test_backtesting_legacy_adapters.py`

**Implementation**
- Register existing scripts as reference jobs:
  - `run_comprehensive_backtesting_all_stocks.R`
  - `working-sector/phase4_backtest.py`
- Make adapters explicit and optional.

**Acceptance criteria**
- Adapter registry lists existing scripts and missing-script status.
- No adapter executes during import or test discovery.

#### K10 — Regression + Golden Backtests

**Files to create / modify**
- Create fixture CSVs under `tests/fixtures/backtesting/`
- Create: `tests/test_backtesting_end_to_end.py`

**Implementation**
- Add small known OHLCV universe with deterministic expected trades.
- Test Stage 2 and RSI pullback end-to-end.
- Test no-assumption behavior for missing fundamentals.

**Acceptance criteria**
- Run:
  - `./.venv/bin/python -m unittest tests.test_backtesting_data tests.test_backtesting_strategy_registry tests.test_backtesting_engine tests.test_backtesting_portfolio tests.test_backtesting_metrics tests.test_backtesting_storage tests.test_backtesting_report tests.test_nse_agent_backtest tests.test_backtesting_end_to_end -v`
- Expected: all tests pass.

#### K11 — Technical Pattern Feature Library

**Files to create / modify**
- Create: `backtesting/patterns.py`
- Create: `tests/test_backtesting_patterns.py`

**Implementation**
- Add common indicator helpers:
  - SMA20/50/150/200
  - EMA optional later
  - ATR14
  - RSI14
  - rolling 52-week high/low
  - rolling average volume
  - relative volume
  - Bollinger bandwidth
  - rolling range compression
  - swing high / swing low pivot detection
- Add `PatternSignal` dataclass and detector interface:
  - `detect_<pattern_id>(df: pd.DataFrame, *, as_of: date | None = None, config: PatternConfig | None = None) -> list[PatternSignal]`
- All detectors must use only current and historical bars. No centered rolling windows that require future candles in backtest mode.
- Include `rejection_reasons` for every candidate that nearly qualifies.

**Acceptance criteria**
- Synthetic OHLCV fixture returns expected SMA/ATR/RSI/pivot values.
- Pivot detection does not use lookahead in backtest mode.
- Missing columns return structured errors or rejection reasons, not stack traces.
- Pattern detector output is JSON-serializable for storage/reporting.

#### K12 — VCP / Darvas / Squeeze Strategy Pack

**Files to create / modify**
- Modify: `backtesting/patterns.py`
- Modify: `backtesting/strategy_registry.py`
- Test: `tests/test_backtesting_vcp_darvas_squeeze.py`

**Implementation**
- Add strategy IDs:
  - `vcp`
  - `darvas`
  - `tight_base`
  - `bollinger_squeeze`
  - `nr7_breakout`
  - `inside_bar_compression`
- VCP detector:
  - detect at least two contraction legs,
  - require lower volatility/range in later legs,
  - prefer volume contraction,
  - require pivot breakout for entry.
- Darvas detector:
  - identify box high/low after a consolidation period,
  - entry above box high,
  - stop below box low or ATR stop.
- Bollinger squeeze detector:
  - bandwidth below rolling percentile threshold,
  - breakout close above upper band for bullish setup or below lower band for bearish setup.
- NR7 / inside-bar detector:
  - detect narrowest range in seven sessions,
  - optional inside-bar stack,
  - entry on next breakout beyond compression range.

**Acceptance criteria**
- Synthetic VCP fixture produces one bullish signal with confidence >= 70.
- Synthetic failed VCP fixture returns rejection reason `range_not_contracting`.
- Darvas fixture identifies box high, box low, entry, and stop.
- Bollinger squeeze fixture does not fire before compression threshold is met.
- Engine can run `/backtest run vcp` against fixture data and produce deterministic trades.

#### K13 — Chart Pattern Strategy Pack

**Files to create / modify**
- Modify: `backtesting/patterns.py`
- Modify: `backtesting/strategy_registry.py`
- Test: `tests/test_backtesting_chart_patterns.py`

**Implementation**
- Add strategy IDs:
  - `head_shoulders`
  - `inverse_head_shoulders`
  - `cup_handle`
  - `double_top`
  - `double_bottom`
  - `ascending_triangle`
  - `descending_triangle`
  - `sym_triangle`
  - `flag`
  - `pennant`
- Head-and-shoulders detector:
  - identify left shoulder, head, right shoulder using swing pivots,
  - validate head exceeds shoulders,
  - compute neckline,
  - confirm breakdown below neckline,
  - reject if neckline break is not present.
- Inverse head-and-shoulders detector:
  - mirror the structure,
  - confirm breakout above neckline.
- Cup-and-handle detector:
  - require rounded base duration,
  - reject overly deep cups,
  - detect handle pullback near prior high,
  - confirm breakout above handle pivot.
- Triangle detectors:
  - fit/approximate support/resistance lines from pivots,
  - require converging or flat boundary structure,
  - confirm breakout direction.
- Flag/pennant:
  - require prior impulse move,
  - short consolidation,
  - breakout in impulse direction.

**Acceptance criteria**
- Each pattern has at least one positive synthetic fixture and one false-positive fixture.
- Head-and-shoulders does not fire without neckline break.
- Cup-and-handle rejects V-shaped rebounds and overly deep cups.
- Triangle detector labels direction and confidence.
- All chart-pattern strategies appear in `/backtest list` with status `experimental` until enough real-market validation exists.

#### K14 — Exit Strategy Lab

**Files to create / modify**
- Create: `backtesting/exits.py`
- Modify: `backtesting/engine.py`
- Test: `tests/test_backtesting_exits.py`

**Implementation**
- Add exit-rule IDs:
  - `supertrend_trailing`
  - `atr_trailing`
  - `sma50_break`
  - `stage2_exit`
  - `time_stop`
  - `partial_profit_r`
  - `target_then_trail`
- Allow `/backtest exits <entry_strategy> --exit-rule <rule>` to reuse the same entries and compare exit behavior.
- Persist exit rule in `backtest_run_config`.
- Report exit attribution:
  - stopped out,
  - target hit,
  - trend exit,
  - time exit,
  - partial profit.

**Acceptance criteria**
- Same entry fixture can be run with two exit rules and produces different deterministic trade outcomes.
- Partial profit rule records multiple trade legs or a structured leg summary.
- Exit comparison report ranks exit rules by CAGR, max drawdown, expectancy, and average holding period.

#### K15 — Pattern Backtest QA + Visual Evidence

**Files to create / modify**
- Create: `backtesting/charts.py`
- Create fixtures under `tests/fixtures/backtesting/patterns/`
- Test: `tests/test_backtesting_pattern_visuals.py`

**Implementation**
- Add synthetic fixtures for:
  - clean VCP,
  - failed VCP,
  - Darvas box,
  - Bollinger squeeze,
  - head-and-shoulders,
  - inverse head-and-shoulders,
  - cup-and-handle,
  - triangle,
  - false-positive random walk.
- Add optional chart snapshot generation for a detected pattern window:
  - price candles or OHLC line,
  - pivot/pattern points,
  - entry, stop, target,
  - confidence and rejection reasons.
- Visuals are optional in CI. Unit tests should validate returned file paths and metadata with a non-interactive backend.

**Acceptance criteria**
- All synthetic fixtures produce expected detector outcomes.
- Random-walk false-positive fixture produces no high-confidence signal.
- Chart snapshot generation works with `matplotlib` non-interactive backend when dependency is available.
- If chart dependency is missing, reports still render without visual evidence and include an actionable warning.

---

## 1. CURRENT STATE ASSESSMENT

### 1.1 What Is Already Built (Do Not Rebuild)

| Capability | File(s) | Status | Quality |
|---|---|---|---|
| NSE OHLCV data load (all stocks) | `load_latest_nse_data_comprehensive.R`, `data/nse_sec_full_data.csv` | ✅ Done | Production |
| NSE index data load | `data/nse_index_data.csv`, `data/nse_index_cache.RData` | ✅ Done | Production |
| Sector rotation ranking (RS vs Nifty500) | `sector_rotation_report.py` → `_build_sector_rank()` | ✅ Done | Production |
| Investment candidate screening (37 stocks) | `sector_rotation_report.py` → `screen_candidates()` | ✅ Done | Production |
| Technical indicators: RSI, Supertrend, Volume, Patterns | `sector_rotation_report.py`, `core/technical_analysis_engine.R` | ✅ Done | Production |
| LLM narratives (gpt-5.5 via OpenAI, two-phase) | `sector_rotation_report.py` → `_generate_llm_narratives()` | ✅ Done | Production |
| Fundamental data fetch (Screener.in via R) | `working-sector/fetch_screener_fundamental_details.R` | ✅ Done | Production |
| Persistent fundamental cache | `data/_sector_rotation_fund_cache.csv` | ✅ Done | Production |
| HTML report (sector pills, table, narratives) | `sector_rotation_report.py` → `_build_html()` | ✅ Done | Production |
| CAN-SLIM scoring | `apex_resilience_full_report.py` | ✅ Done | Good |
| Minervini score | `apex_resilience_full_report.py` | ✅ Done | Good |
| Portfolio analyzer (7-phase) | `portfolio-analyzer/run_pipeline.py` | ✅ Done | Good |
| Market breadth (DMA breakouts) | `analyze_comprehensive_market_breadth.R` | ✅ Done | Good |
| Backtesting framework | `run_comprehensive_backtesting_all_stocks.R`, `working-sector/phase4_backtest.py` | ✅ Done | Good |
| Email distribution | `email_nse_reports.py` | ✅ Done | Good |
| SQLite results database | `nse_analysis.db` | ✅ Done | Partial |

### 1.2 What Is Partially Built (Needs Completion)

| Capability | File(s) | Gap |
|---|---|---|
| Signal performance tracking | `backlog.md` (planned), no impl | No outcome tracking; signals never measured |
| A+ setup classification | `backlog.md` (specified), no impl | Current: generic BUY/HOLD/SELL signals |
| Entry / stop / target levels | `sector_rotation_report.py` (resistance/support exist) | No formal entry zones, only raw levels |
| F&O open interest integration | Not started | F&O data not fetched or used |
| Regime detection | Not started | All signals applied uniformly regardless of market regime |
| Portfolio-aware narrative | Not started | Narratives are generic, not portfolio-context-aware |

### 1.3 What Does Not Exist Yet (New Build Required)

- Market regime detector (HMM / changepoint)
- F&O OI + PCR signals
- FII/DII institutional flow signals
- Knowledge graph (supply chain + promoter linkages)
- Causal inference model
- Counterfactual scenario engine
- Promoter pledging / insider activity alerts
- Learning loop (signal outcome tracking + weight recalibration)
- Macro-economic proxy signals (GST e-way bills, PMI, IIP, power generation)
- Earnings call NLP / concall sentiment scoring
- Voice / WhatsApp briefing output
- Real-time / streaming mode

---

## 2. BACKLOG — PHASE 0: FOUNDATIONS (No New Features, Fix & Standardise)

### P0-1 — Signal Performance Logger
**Size:** M  
**Priority:** Critical (feeds the learning loop in P2)

**What exists:** Signals are generated in `sector_rotation_report.py` but never persisted for outcome measurement.

**What to build:**
```
File to create: data/signal_log.csv
Columns: date_issued, symbol, sector, signal (BUY/HOLD/SELL), 
         investment_score, price_at_issue, target_price (resistance),
         stop_price (supertrend_value), horizon_days (5/22/66),
         date_resolved, price_at_resolution, hit_target (bool),
         hit_stop (bool), return_pct, regime_at_issue
```

**Implementation in `sector_rotation_report.py`:**
1. After `screen_candidates()` finishes, call `_log_signals(candidates, date)`.
2. `_log_signals()`: for each candidate row, append one row to `data/signal_log.csv` if not already logged for that date+symbol.
3. Separately, a weekly job `resolve_signals.py` reads the log, checks current prices, marks `hit_target`/`hit_stop`, computes `return_pct`.

**Acceptance criteria:**
- `data/signal_log.csv` grows by ~37 rows each time `sector_rotation_report.py` runs.
- Re-running on the same date does not duplicate rows.
- `resolve_signals.py --days 5` marks all 5-day-old signals as resolved.

---

### P0-2 — A+ Setup Classification
**Size:** M  
**Priority:** High

**What exists:** `sector_rotation_report.py` has `TRADING_SIGNAL` (BUY/HOLD/SELL/WEAK_SELL) and `PATTERN` (CONSOLIDATION_BREAKOUT etc). The existing `backlog.md` has a spec.

**What to build:**  
Add a new column `SETUP_CLASS` to candidates with these values (in priority order):

| Setup Class | Conditions | Meaning |
|---|---|---|
| `LEADER_BREAKOUT` | PATTERN=CONSOLIDATION_BREAKOUT AND VOL_RATIO>1.5 AND RSI 55-72 AND SUPERTREND=BULLISH | High-conviction institutional breakout |
| `FAST_RECOVERY` | ret_5d > +3% AND ret_1m > +8% AND was below 50DMA 10 days ago | Post-correction momentum recovery |
| `BASE_NEAR_HIGH` | price within 5% of 52-week high AND RSI 50-65 AND vol_ratio < 1.2 | Quiet accumulation near highs |
| `PULLBACK_IN_UPTREND` | SUPERTREND=BULLISH AND RSI 38-52 AND ret_5d < -2% | Buy-the-dip in established uptrend |
| `MOMENTUM_EXTENDED` | RSI > 72 AND ret_1m > +15% | Overbought — reduce/trail only |
| `WEAK_TREND` | SUPERTREND=BEARISH OR ret_1m < -5% | Avoid / exit |
| `NEUTRAL` | Everything else | Monitor |

**Files to modify:**
- `sector_rotation_report.py` → `screen_candidates()` — add `SETUP_CLASS` column using `pd.cut` / `np.select` logic after all indicators are computed.
- HTML template — add `SETUP_CLASS` as a color-coded badge next to the signal badge.

**Acceptance criteria:**
- Every candidate row has a non-null `SETUP_CLASS`.
- `LEADER_BREAKOUT` and `FAST_RECOVERY` appear prominently in the HTML with distinct badge colors.

---

### P0-3 — Formal Entry / Stop / Target Levels
**Size:** S  
**Priority:** High

**What exists:** `RESISTANCE`, `SUPPORT`, `SUPERTREND_VALUE` are already computed and shown in the table.

**What to build:**  
Compute three new columns using existing values:

```python
# Entry zone
ENTRY_LOW  = current_price * 0.99          # 1% below current (limit order zone)
ENTRY_HIGH = min(resistance * 0.995, current_price * 1.02)  # just below resistance

# Stop loss (tightest of: Supertrend level, 2% below support, 6% below entry)
STOP_LOSS = max(supertrend_value, support * 0.98, entry_low * 0.94)

# Target (first resistance, then 1.5x risk-reward above entry)
RISK = entry_low - STOP_LOSS
TARGET_1 = resistance
TARGET_2 = entry_low + (RISK * 2.5)        # 2.5:1 risk-reward
```

**Files to modify:**  
`sector_rotation_report.py` → add computation after existing indicator calc → include in HTML table and LLM prompt.

---

### P0-4 — Deduplicate and Consolidate Data Sources
**Size:** S  
**Priority:** Medium

**What exists:** Fundamental data comes from 3 overlapping sources:
- `reports/Apex_Resilience_screener_fundamentals_20260428.csv`
- `working-sector/output/fundamental_details.csv`
- `data/_sector_rotation_fund_cache.csv` (now primary)

**What to build:**  
- Remove the two legacy sources from `_load_fundamental_details()` — use only `_sector_rotation_fund_cache.csv`.
- Add a one-time migration script `scripts/migrate_fund_cache.py` that merges all three into the cache (already done manually; formalise it).
- Delete `data/_sector_rotation_fund_tmp.csv` after each successful merge.

---

## 3. BACKLOG — PHASE 1: CORE INTELLIGENCE (High ROI, Buildable Now)

### P1-1 — Market Regime Detector
**Size:** L  
**Priority:** Critical — gates all signal weighting in P1-2 onward

**What exists:** Nothing. All signals applied uniformly regardless of market state.

**What to build:**  
**File to create:** `regime_detector.py`

**Algorithm:**  
Use a 4-state Hidden Markov Model (HMM) on daily Nifty500 returns + volatility:

```python
# Input features (daily, last 252 trading days):
features = [
    nifty500_daily_return,      # % change
    rolling_20d_volatility,     # std of daily returns
    advance_decline_ratio,      # from analyze_comprehensive_market_breadth.R output
    pct_stocks_above_200dma,    # from breadth analysis
]

# States (4):
BULL_TREND    = 0  # sustained uptrend, low vol, broad participation
ROTATION      = 1  # mixed returns, sector divergence, churning
CHOP          = 2  # low directional movement, high noise
BEAR_TREND    = 3  # sustained downtrend, high vol, narrow breadth

# Library: hmmlearn (pip install hmmlearn)
from hmmlearn.hmm import GaussianHMM
model = GaussianHMM(n_components=4, covariance_type="full", n_iter=200)
```

**Signal weight multipliers by regime:**

| Signal Type | BULL_TREND | ROTATION | CHOP | BEAR_TREND |
|---|---|---|---|---|
| Momentum (RSI>60, breakout) | 1.5x | 1.2x | 0.4x | 0.2x |
| Sector RS | 1.0x | 2.0x | 0.8x | 0.5x |
| Mean reversion (pullback) | 0.5x | 0.8x | 1.5x | 1.0x |
| Fundamental quality | 1.0x | 1.5x | 2.0x | 2.5x |
| Defensive sectors | 0.5x | 0.8x | 1.5x | 3.0x |

**Output:**
```python
{
  "current_regime": "ROTATION",
  "confidence": 0.81,
  "regime_duration_days": 12,
  "previous_regime": "BULL_TREND",
  "regime_history": [...],  # last 90 days
}
```

**Integration into `sector_rotation_report.py`:**
1. Call `detect_regime()` at start of `generate_report()`.
2. Pass `regime` into `screen_candidates()` → multiply `INVESTMENT_SCORE` by regime weights.
3. Add regime badge to HTML header: `🔄 ROTATION (confidence: 81%)`.
4. Pass regime to LLM prompt: "Current market regime: ROTATION (12 days). Weight sector RS signals heavily."

**Dependencies:** `hmmlearn`, breadth CSV output from `analyze_comprehensive_market_breadth.R`  
**Acceptance criteria:**
- Regime output is deterministic for the same input date.
- Regime changes are logged in `data/regime_history.csv`.
- HTML report shows current regime badge.

---

### P1-2 — F&O Open Interest + Put-Call Ratio Signals
**Size:** L  
**Priority:** High

**What exists:** Nothing. Price/volume data only.

**What to build:**  
**File to create:** `fetch_fno_data.py`

**Data source:** NSE FO bhavcopy (free, daily)
```
URL pattern: https://nsearchives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_{DDMMYYYY}_F_0000.csv.zip
Headers required: {"User-Agent": "Mozilla/5.0", "Referer": "https://www.nseindia.com"}
```

**Signals to compute per symbol (where F&O data exists):**

```python
# 1. Put-Call Ratio (PCR) — by Open Interest
PCR = sum(put_OI) / sum(call_OI)
# PCR > 1.2: bullish (more puts = fear, contrarian positive)
# PCR < 0.7: bearish (complacency, too many calls)
# PCR 0.9-1.1: neutral

# 2. OI Change % (5-day rolling)
OI_CHANGE_5D = (current_oi - oi_5d_ago) / oi_5d_ago * 100
# OI_CHANGE > +20% with price up: strong bull conviction
# OI_CHANGE > +20% with price down: strong bear conviction (short buildup)

# 3. Max Pain (price where maximum options expire worthless)
# Compute for each expiry: sum of pain for all strikes
MAX_PAIN = argmin(sum(strike_pain for all_strikes))

# 4. COT-style: net institutional positioning
# From participant-wise OI: FII vs Client positions
FII_NET_LONG = fii_long_oi - fii_short_oi
```

**Output:** `data/fno_signals.csv` with columns: `date, symbol, pcr, oi_change_5d, max_pain, fii_net_long, signal (BULL/BEAR/NEUTRAL)`

**Integration:**  
- Merge `fno_signals.csv` into `screen_candidates()` on `SYMBOL`.
- Add `FNO_SIGNAL` column to candidates.
- Add `FNO_SIGNAL` to LLM prompt data and HTML table.

**Acceptance criteria:**
- `fetch_fno_data.py --date 2026-05-02` downloads and processes FO bhavcopy.
- PCR and OI change computed for all F&O-eligible symbols.
- Missing for non-F&O stocks: fill with `None`.

---

### P1-3 — FII / DII Daily Flow Signals
**Size:** M  
**Priority:** High

**What exists:** Nothing.

**What to build:**  
**File to create:** `fetch_fii_dii_flows.py`

**Data source:** NSE institutional activity report (free)
```
URL: https://www.nseindia.com/api/fiidiiTradeReact
Fallback URL: https://archives.nseindia.com/content/nsccl/fao_participant_oi_{date}.csv
```

**Signals:**
```python
# Rolling 5-day FII net buy/sell
FII_NET_5D = sum(fii_net_daily for last 5 days)  # crores
DII_NET_5D = sum(dii_net_daily for last 5 days)

# Signal rules:
if FII_NET_5D > 3000:  signal = "FII_BUYING" 
if FII_NET_5D < -3000: signal = "FII_SELLING"
if DII_NET_5D > 2000 and FII_NET_5D > 0: signal = "BOTH_BUYING"  # strongest
if DII_NET_5D > 2000 and FII_NET_5D < 0: signal = "DII_ABSORBING"  # support

# Sector-level FII preference (from sector FII holdings data - quarterly)
# Use NSDL sector-wise FII holding % change as sector-level signal
```

**Output:** `data/fii_dii_flows.csv` — daily: `date, fii_net, dii_net, fii_net_5d, dii_net_5d, flow_signal`

**Integration into `sector_rotation_report.py`:**
- Compute `FII_FLOW_SIGNAL` and append to sector rank table.
- In sector narrative prompt: "FII net last 5 days: +₹4,230 Cr (BUYING)"
- Regime detector: use `FII_NET_5D` as one of the features.

---

### P1-4 — Promoter Pledging & Insider Activity Alerts
**Size:** M  
**Priority:** Medium

**What exists:** Nothing.

**What to build:**  
**File to create:** `fetch_insider_alerts.py`

**Data source:** BSE/NSE bulk/block deal files + SEBI insider trading disclosures
```
BSE bulk deals: https://api.bseindia.com/BseIndiaAPI/api/BulkDealDownload/w
NSE bulk deals: https://archives.nseindia.com/content/equities/bulk.csv (daily)
Promoter pledging: https://archives.nseindia.com/content/equities/pledge.csv (quarterly)
```

**Signals:**
```python
# Alert types:
PROMOTER_PLEDGING_INCREASE  # pledged % rose > 5pp in last quarter → RED FLAG
PROMOTER_BUYING             # promoter acquired open market shares → POSITIVE
BULK_DEAL_BUY               # large investor bought > 0.5% in single session → POSITIVE  
BULK_DEAL_SELL              # large investor sold > 0.5% → NEGATIVE
INSIDER_BUY                 # director/officer bought → MODERATE POSITIVE
```

**Output:** `data/insider_alerts.csv` — `date, symbol, alert_type, qty, value_cr, entity`

**Integration:**
- Merge alerts into candidates (last 30 days).
- Add `INSIDER_ALERT` badge in HTML table.
- Include in LLM prompt: "Promoter bought 0.3% last week — insider conviction signal."

---

### P1-5 — Enhanced HTML Dashboard (UX Pass)
**Size:** M  
**Priority:** Medium

**What exists:** `sector_rotation_report.py` HTML is functional. Pills slide, table has fixed layout.

**What to add:**

1. **Regime banner at top of page**: colored stripe (green=BULL, amber=ROTATION, grey=CHOP, red=BEAR) with regime name, confidence %, duration days.

2. **Sortable table columns**: add `data-sort` attributes; JS click handler sorts by that column ascending/descending.

3. **Persistent sort/filter state**: store in `localStorage` so refreshing page keeps user's selected sector + sort.

4. **Heatmap view toggle**: button switches table to a 10-column heatmap (investment score → red/amber/green cells) for quick visual scanning.

5. **Narrative search**: text box filters stocks whose narratives contain the typed keyword.

6. **Print / PDF export**: `window.print()` with `@media print` CSS hiding nav/controls.

**Files to modify:** `sector_rotation_report.py` → `_build_html()` CSS and JS sections.

---

### P1-6 — Macro-Economic Proxy Signals
**Size:** L  
**Priority:** Medium

**What exists:** Nothing. No macro data ingested; all signals are price/volume-only.

**What to build:**  
**File to create:** `fetch_macro_proxies.py`

**Data sources (all free / public):**

| Indicator | Source | Frequency | URL / Method |
|---|---|---|---|
| GST e-way bills | GST portal monthly release | Monthly | Parse press releases or MoF dashboard CSV |
| Manufacturing PMI | IHS Markit / S&P Global | Monthly | Scrape headline PMI from public release |
| IIP (Index of Industrial Production) | MoSPI | Monthly | `https://mospi.gov.in/iip` CSV download |
| Power generation (thermal + renewables) | CEA daily reports | Daily | `https://cea.nic.in/dashboard/` |
| Cement dispatches | CMA monthly | Monthly | Manual / press release |
| Auto sales (SIAM / FADA) | FADA website | Monthly | Parse FADA monthly release |

**Signals to compute:**
```python
# 1. PMI trend
PMI_TREND = "EXPANDING" if pmi > 50 and pmi > pmi_prev else "CONTRACTING"

# 2. Power generation momentum (proxy for industrial activity)
POWER_GEN_MOM = (power_gen_this_month - power_gen_same_month_last_year) / power_gen_same_month_last_year * 100

# 3. GST collection growth (proxy for consumption + economic activity)
GST_GROWTH = (gst_current - gst_same_month_ly) / gst_same_month_ly * 100

# 4. Sector mapping:
# High PMI + rising power → boost Industrials, Capital Goods, Metals
# Rising GST + auto sales → boost Consumer Discretionary, Auto
# Falling PMI + falling power → boost Defensives (FMCG, Pharma, IT)

SECTOR_MACRO_BOOST = {
    "Capital Goods": pmi_score * 0.4 + power_score * 0.3 + iip_score * 0.3,
    "Metals & Mining": pmi_score * 0.3 + power_score * 0.4 + iip_score * 0.3,
    "Auto": auto_sales_score * 0.5 + gst_score * 0.3 + pmi_score * 0.2,
    "FMCG": gst_score * 0.5 + (-pmi_score) * 0.2,  # inverse: benefits from defensive rotation
    # ... other sectors
}
```

**Output:** `data/macro_proxy_signals.csv` — monthly: `date, indicator, value, yoy_change_pct, trend, sector_impact`

**Integration into `sector_rotation_report.py`:**
- Load latest macro signals at start of `generate_report()`.
- Add `MACRO_TAILWIND` score to sector rank table (sum of sector-mapped macro boosts).
- Pass macro context to LLM prompt: "Macro backdrop: PMI 56.2 (expanding), power generation +8% YoY, GST collections +12% YoY — supportive for industrials."
- Regime detector (P1-1): use macro scores as additional HMM features for regime classification.

**Dependencies:** None (standalone data ingestion)  
**Acceptance criteria:**
- `fetch_macro_proxies.py --refresh` downloads and caches latest available data.
- Stale data (>45 days) triggers a warning but does not block report generation.
- `data/macro_proxy_signals.csv` has at least PMI + power generation rows.
- Sector rank table includes `MACRO_TAILWIND` column.

---

## 4. BACKLOG — PHASE 2: ADVANCED INTELLIGENCE

### P2-1 — NSE Knowledge Graph
**Size:** XL  
**Priority:** High (structural edge, hard to replicate)

**What exists:** `data/index_stock_mapping.csv` has stock↔index membership. Company descriptions exist via Screener.in.

**What to build:**  
**Files to create:** `knowledge_graph.py`, `data/nse_graph.json`

**Graph schema:**
```python
Nodes: {
  "COCHINSHIP": {
    "type": "stock",
    "sector": "Defence & Shipbuilding",
    "market_cap_cr": 45000,
    "promoter_name": "Cochin Shipyard Ltd (Govt of India)",
    "promoter_holding_pct": 72.86,
  }
}

Edges: [
  # Supply chain (from screener.in 'peers' + sector classification)
  {"from": "ONGC", "to": "WELCORP", "type": "supply_chain", "weight": 0.6, "note": "steel pipes for oil & gas"},
  {"from": "ONGC", "to": "BHEL", "type": "supply_chain", "weight": 0.5, "note": "equipment"},
  
  # Promoter group (same promoter entity)
  {"from": "TATASTEEL", "to": "TATAPOWER", "type": "promoter_group", "weight": 1.0, "note": "Tata Sons"},
  
  # Sector peers (high correlation in returns)
  {"from": "COCHINSHIP", "to": "MAZDOCK", "type": "sector_peer", "weight": 0.85},
  
  # Debt exposure (same lender)
  {"from": "ADANIPORTS", "to": "ADANIGREEN", "type": "group_debt", "weight": 0.9},
]
```

**Build process:**
1. `build_graph.py` — one-time script: parse company descriptions, sector tags, promoter data from `data/_sector_rotation_fund_cache.csv` and Screener.in JSON → build `data/nse_graph.json`.
2. `knowledge_graph.py` — runtime module: load graph, expose `get_downstream_impact(symbol, shock_magnitude)`.

**Shock propagation algorithm:**
```python
def propagate_shock(graph, source_symbol, shock_pct, depth=2):
    """
    If ONGC gets SELL signal (-8%), compute impact on connected nodes.
    Returns: dict of {symbol: estimated_impact_pct}
    """
    visited = {source_symbol: shock_pct}
    queue = [(source_symbol, shock_pct)]
    for _ in range(depth):
        next_queue = []
        for node, impact in queue:
            for edge in graph.edges(node):
                if edge.type in ["supply_chain", "promoter_group"]:
                    child_impact = impact * edge.weight * 0.4  # 40% propagation
                    if abs(child_impact) > 1.0:  # only meaningful impacts
                        visited[edge.to] = child_impact
                        next_queue.append((edge.to, child_impact))
        queue = next_queue
    return visited
```

**Integration:** Call `propagate_shock()` in `sector_rotation_report.py`; add `GRAPH_SIGNAL` column (upstream shock warning / beneficiary).

---

### P2-2 — Counterfactual Scenario Engine
**Size:** L  
**Priority:** Medium

**What exists:** Single deterministic run. No scenario analysis.

**What to build:**  
**File to create:** `scenario_engine.py`

**Design:**
```python
SCENARIOS = [
    {
        "name": "RBI Rate Cut -25bps",
        "macro_shocks": {"rate_sensitive_sectors": +0.06},  # 6% boost to rate-sensitive
        "sector_adjustments": {
            "Real Estate": +8, "Banking": +5, "Energy": +3, "IT": -2
        },
        "trigger": "rbi_rate_decision_next_week",
    },
    {
        "name": "FII Sell-off ₹5,000 Cr",
        "flow_shock": -5000,
        "sector_adjustments": {
            "Smallcap": -10, "Midcap": -7, "Largecap": -4, "FMCG": +2
        },
    },
    {
        "name": "USDINR crosses ₹85",
        "fx_shock": 85.5,
        "sector_adjustments": {
            "IT": +8, "Pharma": +5, "Metals": -6, "Oil & Gas": -8
        },
    },
    {
        "name": "China slowdown (commodity demand drop)",
        "sector_adjustments": {
            "Metals": -12, "Mining": -10, "Chemical": -5, "Defence": +3
        },
    },
]

def run_scenario(base_candidates, base_sector_rank, scenario) -> dict:
    """Apply macro shocks to base scores, return adjusted rankings."""
    adjusted = base_candidates.copy()
    for sector, delta in scenario["sector_adjustments"].items():
        mask = adjusted["SECTOR_NAME"] == sector
        adjusted.loc[mask, "INVESTMENT_SCORE"] += delta
        adjusted.loc[mask, "SCENARIO_ADJUSTMENT"] = delta
    return adjusted
```

**HTML integration:** Add a "Scenarios" tab to the existing pills bar. Each scenario shows the re-ranked candidates and which sectors benefit/suffer.

---

### P2-3 — Learning Loop (Signal Outcome Tracking)
**Size:** L  
**Priority:** High (requires P0-1 signal logger to exist first)

**What exists:** P0-1 signal logger (to be built). No outcome tracking today.

**What to build:**  
**File to create:** `learning_loop.py`

**Weekly job:**
```python
def analyze_signal_performance(log_path="data/signal_log.csv", lookback_days=90):
    """
    Read resolved signals. Compute hit rates by:
    - signal type (BUY/HOLD/SELL)
    - setup class (LEADER_BREAKOUT / FAST_RECOVERY etc)
    - regime at issue (BULL/ROTATION/CHOP/BEAR)
    - sector
    - horizon (5d / 22d / 66d)
    
    Output:
    - data/signal_performance_summary.csv
    - Calibration adjustments: which setups/regimes outperform
    """
    df = pd.read_csv(log_path)
    resolved = df[df["date_resolved"].notna()]
    
    # Hit rate by setup class + regime
    perf = resolved.groupby(["setup_class", "regime_at_issue", "horizon_days"]).agg(
        hit_rate=("hit_target", "mean"),
        avg_return=("return_pct", "mean"),
        n=("symbol", "count"),
    ).reset_index()
    
    # Output calibration multipliers
    # e.g.: LEADER_BREAKOUT in ROTATION regime, 22d: hit_rate=0.68, avg_return=+9.2%
    # → confidence multiplier = 0.68 / 0.50 (baseline) = 1.36
    perf["calibration_multiplier"] = perf["hit_rate"] / 0.50
    perf.to_csv("data/signal_calibration.csv", index=False)
    return perf
```

**Integration into `sector_rotation_report.py`:**
- Load `data/signal_calibration.csv` at start.
- Apply calibration multipliers to `INVESTMENT_SCORE` before ranking.
- Add to HTML: "Signal calibration: LEADER_BREAKOUT in ROTATION regime → 68% hit rate (last 90 days)"

---

### P2-4 — Portfolio-Aware Personalised Narratives
**Size:** L  
**Priority:** High

**What exists:** `portfolio-analyzer/` has holdings data. LLM narratives are generic.

**What to build:**  
In `sector_rotation_report.py`:

1. **Load portfolio holdings** at start of `generate_report()`:
   ```python
   portfolio = _load_portfolio()  # reads portfolio-analyzer/output/holdings.csv
   # Returns: {symbol: {avg_cost, qty, current_value, unrealised_pnl_pct, weight_pct}}
   ```

2. **Enrich LLM prompt** with portfolio context per stock:
   ```python
   if sym in portfolio:
       p = portfolio[sym]
       stock_line += f"\n    PORTFOLIO: Held {p['qty']} shares @ avg ₹{p['avg_cost']:.2f} "
       stock_line += f"(unrealised: {p['unrealised_pnl_pct']:+.1f}%, weight: {p['weight_pct']:.1f}%)"
   ```

3. **Add portfolio-specific LLM instruction:**
   ```
   - If stock is already held: tailor advice to position management (when to add, when to trail, when to book).
   - If stock is NOT held: tailor advice to entry decision.
   - If concentration > 5% in sector: flag as overweight, recommend trim rather than add.
   ```

**Acceptance criteria:** LLM narrative for a held stock mentions: avg cost, unrealised P&L %, and gives hold/trim/add guidance instead of a generic entry signal.

---

### P2-5 — Earnings Call NLP / Concall Sentiment Scoring
**Size:** L  
**Priority:** Medium

**What exists:** Nothing. No earnings call data ingested; fundamental analysis relies on static ratios from Screener.in.

**What to build:**  
**Files to create:** `fetch_concall_transcripts.py`, `concall_sentiment.py`

**Data sources:**

| Source | Coverage | Access |
|---|---|---|
| BSE corporate filings (outcome / transcript PDFs) | All listed companies | Free — `https://www.bseindia.com/corporates/ann.html` |
| Trendlyne concall summaries | Top 500 | Free tier (limited); API for premium |
| Screener.in annual report PDFs | Top 500 | Free |
| Company investor relations pages | Varies | Free (manual scrape per company) |

**Pipeline:**
```python
# Step 1: Fetch latest earnings call transcript (PDF / text)
def fetch_latest_concall(symbol: str) -> str:
    """
    Try BSE filings first (search for 'outcome' or 'transcript' in recent filings).
    Fallback: Trendlyne concall summary page.
    Return: raw text of the earnings call / management commentary.
    """

# Step 2: Extract sentiment and key signals using LLM
def score_concall_sentiment(transcript_text: str, symbol: str) -> dict:
    """
    Use existing _llm_call() to extract structured signals from concall text.
    
    LLM prompt extracts:
    - management_tone: CONFIDENT | CAUTIOUS | DEFENSIVE | EVASIVE
    - guidance_direction: RAISED | MAINTAINED | LOWERED | WITHDRAWN
    - key_themes: list of 3-5 themes (e.g., 'capacity expansion', 'margin pressure')
    - risk_flags: list of concerns mentioned (e.g., 'raw material cost', 'demand slowdown')
    - capex_signal: EXPANDING | STABLE | CUTTING
    - order_book_trend: GROWING | STABLE | DECLINING (for capital goods / infra)
    - sentiment_score: -1.0 to +1.0 (overall tone)
    
    Returns: dict with all above fields
    """
    prompt = f"""
    Analyse this earnings call transcript for {symbol}.
    Extract:
    1. Management tone (CONFIDENT/CAUTIOUS/DEFENSIVE/EVASIVE)
    2. Guidance direction (RAISED/MAINTAINED/LOWERED/WITHDRAWN)
    3. Top 3-5 key themes discussed
    4. Risk flags or concerns raised
    5. Capex outlook (EXPANDING/STABLE/CUTTING)
    6. Order book trend if applicable (GROWING/STABLE/DECLINING)
    7. Overall sentiment score from -1.0 (very bearish) to +1.0 (very bullish)
    
    Respond as JSON only.
    
    Transcript:
    {transcript_text[:8000]}  # truncate to fit context
    """
    return _llm_call(prompt, parse_json=True)
```

**Output:** `data/concall_sentiment.csv` — per earnings call:
```
symbol, quarter, call_date, management_tone, guidance_direction,
sentiment_score, capex_signal, key_themes, risk_flags, transcript_source
```

**Integration into `sector_rotation_report.py`:**
- Load latest concall sentiment per candidate symbol.
- Add `CONCALL_TONE` and `CONCALL_SENTIMENT` columns to candidates.
- Include in LLM narrative prompt: "Latest concall (Q4FY26): management tone CONFIDENT, guidance RAISED, capex EXPANDING. Key themes: capacity expansion, export order wins."
- Adjust `INVESTMENT_SCORE`: sentiment_score > 0.5 adds +3 to score; sentiment_score < -0.3 subtracts -3.

**Cache strategy:**
- Concall data is quarterly; cache TTL = 100 days.
- Store raw transcript text in `data/concall_transcripts/{symbol}_{quarter}.txt` for audit.
- Re-fetch only when a new quarter's filing is detected.

**Dependencies:** `_llm_call()` from `sector_rotation_report.py`, BSE filing access  
**Acceptance criteria:**
- `fetch_concall_transcripts.py --symbol TATASTEEL` downloads latest available transcript.
- `concall_sentiment.py --symbol TATASTEEL` returns valid JSON with all required fields.
- Missing transcripts result in `CONCALL_TONE = None` (not an error).
- At least 60% of Nifty 500 stocks have concall data within 120 days of latest results.

---

## 5. BACKLOG — PHASE 3: FUTURISTIC (High Complexity, High Impact)

### P3-1 — Causal Inference Model (Replace Technical Indicators)
**Size:** XL  
**Priority:** Medium (requires 2+ years of signal log data from P0-1)

**What to build:**  
Replace RSI/Supertrend scoring with causal model predictions using `econml` or `dowhy`.

**Design:**
```python
# Treatment variable: FII_NET_5D_POSITIVE (binary: >1500cr = 1, else 0)
# Outcome: forward_return_22d
# Confounders: sector_momentum, market_regime, macro_state

from econml.dml import CausalForestDML
model = CausalForestDML(
    model_t=RandomForestClassifier(),
    model_y=RandomForestRegressor(),
    discrete_treatment=True,
    n_estimators=200,
)
model.fit(Y=forward_returns, T=treatment, X=features, W=confounders)
# Effect: heterogeneous treatment effect per stock
effect, lb, ub = model.effect_interval(X_test)
```

**Note:** Requires minimum 500 resolved signals (2–3 years at current pace). Start building signal log (P0-1) immediately.

---

### P3-2 — Voice Briefing (60-Second Daily Audio)
**Size:** M  
**Priority:** Low-medium

**What to build:**  
**File to create:** `generate_voice_briefing.py`

```python
# After report generates, synthesise a 60-second script:
script = f"""
NSE Market Briefing for {today}.
Market regime: {regime['current_regime']} with {regime['confidence']*100:.0f}% confidence.
Top rotating sector: {top_sector['SECTOR_NAME']}, rotation score {top_sector['ROTATION_SCORE']:.1f}.
FII flows: net {fii_net_5d:+,.0f} crores over 5 days — {flow_signal}.
Top investment candidates: {', '.join(top_3_candidates)}.
Watch: {watch_stock} approaching resistance at {resistance:.0f} rupees.
"""

# GPT TTS via OpenAI:
from pathlib import Path
from openai import OpenAI

client = OpenAI()
with client.audio.speech.with_streaming_response.create(
    model="gpt-4o-mini-tts",
    voice="cedar",
    input=script,
    instructions="Speak like a calm senior Indian-market operator. Be concise, risk-first, and avoid hype.",
) as response:
    response.stream_to_file(Path(f"reports/briefing_{today}.mp3"))
```

---

### P3-3 — Real-Time / Intraday Mode
**Size:** XL  
**Priority:** Low (requires live NSE data subscription)

**What exists:** `core/intraday_yahoo.R` has intraday analysis using Yahoo Finance.

**What to build:**  
Replace batch daily run with a streaming mode:
- Intraday price updates every 15 minutes via Yahoo Finance (free, `yfinance`)
- Re-score candidates when any stock crosses resistance or drops below stop
- Push alert to terminal / desktop notification when actionable signal fires

**Note:** Yahoo Finance 15-min data is free but rate-limited. NSE's official EODS data subscription (~₹2,000/month) needed for production intraday.

---

## 6. BACKLOG — PHASE 4: ADVANCED SCREENERS, INDEX INTELLIGENCE & DEEP FUNDAMENTALS

> **Origin:** TOT/POT brainstorm session 2026-05-02. All items are additive — none break existing pipelines.
> Grouped by branch (A–E) from the TOT exploration tree.

---

### BRANCH A — ADVANCED SCREENERS

These screeners complement the existing sector-rotation candidates. Each produces a separate shortlist that can be merged into `candidates` or served as a separate HTML tab.

**Shared architecture pattern:**
```python
# All Branch A screeners follow this pattern in screeners.py:
# Input:  universe DataFrame (all NSE stocks with OHLCV + basic fundamentals)
# Output: filtered + scored DataFrame with SCREENER_CLASS column
# Integration: merged into sector_rotation_report.py candidates at report time
```

**File to create:** `screeners.py` (all Branch A functions)  
**File to modify:** `sector_rotation_report.py` → add "Screeners" tab to HTML

---

#### A1 — William O'Neil Stage Analysis Screener
**Size:** M | **Priority:** High — prevents buying into Stage 3/4 traps

**What exists:** Nothing. RSI + Supertrend approximate stage but do not formally classify.

**What to build:**
```python
def classify_stage(df: pd.DataFrame) -> pd.Series:
    """
    Input columns required per stock: CLOSE, SMA_50, SMA_200, VOL_20D_AVG, RSI, DISTANCE_FROM_52W_HIGH_PCT
    Output: pd.Series of {'STAGE_1', 'STAGE_2', 'STAGE_3', 'STAGE_4', 'UNKNOWN'}

    STAGE 1 — Base Building:
      price ≤ 200DMA ± 5%, SMA_50 flat or declining, volume contracting (vol_20d < vol_200d_avg × 0.8)

    STAGE 2 — Markup (THE BUY ZONE — only entry allowed):
      price > SMA_50 > SMA_200 (golden cross),
      SMA_50 slope positive (10-day pct_change > 0.001),
      SMA_200 slope positive (> 0.0005),
      price within 20% of 52W high,
      RS rank in top 30th percentile

    STAGE 3 — Distribution / Top:
      price near 52W high but SMA_50 flattening (slope < 0.001),
      ATR expanding relative to 3m avg, volume heavy on down-days

    STAGE_4 — Markdown:
      price < SMA_50 < SMA_200 (death cross), SMA_200 slope < -0.001
    """
    close = df["CLOSE"].astype(float)
    sma50 = df["SMA_50"].astype(float)
    sma200 = df["SMA_200"].astype(float)
    sma50_slope = sma50.pct_change(10).fillna(0)
    sma200_slope = sma200.pct_change(10).fillna(0)

    stage_2 = (
        (close > sma50) & (sma50 > sma200) &
        (sma50_slope > 0.001) & (sma200_slope > 0.0005) &
        (df.get("DISTANCE_FROM_52W_HIGH_PCT", pd.Series(0, index=df.index)) > -20)
    )
    stage_4 = (close < sma50) & (sma50 < sma200) & (sma200_slope < -0.001)
    stage_3 = (close > sma200) & (~stage_2) & (sma50_slope < 0.001)
    result = pd.Series("STAGE_1", index=df.index)
    result[stage_4] = "STAGE_4"
    result[stage_3] = "STAGE_3"
    result[stage_2] = "STAGE_2"
    return result

def stage_analysis_screener(universe: pd.DataFrame) -> pd.DataFrame:
    universe["STAGE"] = classify_stage(universe)
    stage2 = universe[universe["STAGE"] == "STAGE_2"].copy()
    stage2["STAGE_SCORE"] = (
        stage2["RS_RANK_PCT"] * 0.4 +
        (1 - stage2["DISTANCE_FROM_52W_HIGH_PCT"].abs() / 20) * 0.3 +
        stage2["VOL_RATIO"].clip(0.5, 3.0) * 0.3
    )
    return stage2.sort_values("STAGE_SCORE", ascending=False)
```

**New columns to add in `sector_rotation_report.py`:**
- `DISTANCE_FROM_52W_HIGH_PCT`: `(close / rolling_252_max - 1) * 100`
- `RS_RANK_PCT`: percentile rank of 66d return vs all NSE stocks
- `SMA_50_SLOPE`, `SMA_200_SLOPE`: 10-day pct_change of respective SMA

**Files to create/modify:**
- `screeners.py` — `classify_stage()`, `stage_analysis_screener()`
- `sector_rotation_report.py` — add `STAGE` column; demote Stage 3/4 in scoring; add stage badge in HTML

**Acceptance criteria:**
- Every candidate has `STAGE` value. Stage 3/4 stocks get -8 `INVESTMENT_SCORE` penalty.
- HTML shows stage badge: green=S2, amber=S1/S3, red=S4.

---

#### A2 — Darvas Box Breakout Screener
**Size:** M | **Priority:** Medium — box top/bottom gives mechanical entry and stop levels

**What exists:** `PATTERN == "CONSOLIDATION_BREAKOUT"` is a rough approximation; no formal box.

**What to build:**
```python
def detect_darvas_box(prices: pd.Series, lookback: int = 52) -> dict | None:
    """
    Darvas Box rules:
    1. Stock makes a new N-week high  → box TOP candidate
    2. Stays below that high for 3+ days (consolidation)
    3. Price fails to make new high for 3 days → box TOP locked
    4. Lowest low during consolidation = box BOTTOM
    5. BREAKOUT: last close > box_top AND volume > 1.5× 20d avg
    6. NEAR_TOP: price within 2% of box top (pre-breakout alert)

    Returns: {box_top, box_bottom, box_width_pct, days_in_box,
              breakout_confirmed, stop_loss (= box_bottom × 0.99)}
    or None if no valid box found.
    """
    recent = prices.tail(lookback)
    box_top = recent.max()
    box_top_idx = recent.idxmax()
    post_high = recent.loc[box_top_idx:]
    if len(post_high) < 3:
        return None
    if post_high.max() > box_top * 1.001:  # new high → box not formed
        return None
    box_bottom = post_high.iloc[1:].min()
    box_width_pct = (box_top - box_bottom) / box_bottom * 100
    if box_width_pct > 25:  # box too wide to be valid
        return None
    return {
        "box_top": round(box_top, 2),
        "box_bottom": round(box_bottom, 2),
        "box_width_pct": round(box_width_pct, 2),
        "days_in_box": len(post_high) - 1,
        "breakout_confirmed": bool(prices.iloc[-1] > box_top),
        "stop_loss": round(box_bottom * 0.99, 2),
    }
```

**Files to create/modify:**
- `screeners.py` — `detect_darvas_box()`, `darvas_screener()`
- Requires `price_history` dict: `{symbol: pd.Series of 52-week closes}` built from `data/nse_sec_full_data.csv`

**Acceptance criteria:**
- Returns 5–30 candidates on a typical day.
- Box top, box bottom, box width %, stop loss shown in HTML output.

---

#### A3 — 52-Week High Momentum Screener
**Size:** S | **Priority:** High — simplest implementation, strong historical hit rate

**What exists:** `DISTANCE_FROM_52W_HIGH_PCT` derivable but not used.

**What to build:**
```python
def momentum_52w_high_screener(universe: pd.DataFrame) -> pd.DataFrame:
    """
    Selection: price within 0–5% below 52W high + Stage 2 + RS top 25% + vol not contracting
    Score: rs_percentile×0.35 + proximity×0.30 + vol_ratio×0.20 + rsi_norm×0.15
    """
    df = universe.copy()
    df["DIST_52W_HIGH"] = (df["CLOSE"] / df["HIGH_52W"] - 1) * 100
    screened = df[
        df["DIST_52W_HIGH"].between(-5, 0.5) &
        (df["SMA_50_SLOPE"] > 0) &
        (df["RS_RANK_PCT"] >= 0.75) &
        (df["VOL_RATIO"] >= 1.0) &
        (df["RSI"].between(50, 80))
    ].copy()
    screened["MOMENTUM_SCORE"] = (
        screened["RS_RANK_PCT"] * 0.35 +
        (1 - screened["DIST_52W_HIGH"].abs() / 5) * 0.30 +
        screened["VOL_RATIO"].clip(0.8, 2.5) / 2.5 * 0.20 +
        ((screened["RSI"] - 50) / 30).clip(0, 1) * 0.15
    )
    return screened.sort_values("MOMENTUM_SCORE", ascending=False)
```

**Files to create/modify:**
- `screeners.py` — `momentum_52w_high_screener()`
- `sector_rotation_report.py` — add `HIGH_52W` column: rolling 252-day max of CLOSE

**Acceptance criteria:** Returns 10–40 candidates. Shown as a "52W High Momentum" screener tab in HTML.

---

#### A4 — Earnings Acceleration Screener
**Size:** M | **Priority:** High — strongest fundamental catalyst for sustained price moves

**What exists:** Latest-quarter EPS in `_sector_rotation_fund_cache.csv`. No multi-quarter series.

**Data enrichment required (R):**
```r
# Extend fetch_screener_fundamental_details.R:
# Scrape quarterly P&L from screener.in/#quarters table
# Extract: Sales, Net Profit, EPS, Operating Margin — last 8 quarters
# Save to: data/quarterly_eps.csv with columns: symbol, quarter_num, revenue, net_profit, eps, op_margin
```

**Screener logic (Python):**
```python
def earnings_acceleration_screener(quarterly_eps: pd.DataFrame) -> pd.DataFrame:
    """
    Acceleration criteria (all required):
    1. EPS growth YoY (Q1 vs Q5): > 25%
    2. EPS growth QoQ (Q1 vs Q2): > 5%
    3. Revenue growth YoY: > 15%
    4. Operating margin not deteriorating vs 4Q average: delta > -1pp

    ACC_SCORE = eps_yoy/100×0.35 + eps_qoq/50×0.20 + rev_yoy/100×0.25 + margin_delta/10×0.20
    """
    pivoted = quarterly_eps.pivot_table(index="symbol", columns="quarter_num",
                                         values=["eps", "revenue", "op_margin"])
    pivoted["EPS_YOY"] = (pivoted["eps"][1] / pivoted["eps"][5].abs() - 1) * 100
    pivoted["EPS_QOQ"] = (pivoted["eps"][1] / pivoted["eps"][2].abs() - 1) * 100
    pivoted["REV_YOY"] = (pivoted["revenue"][1] / pivoted["revenue"][5] - 1) * 100
    pivoted["MARGIN_DELTA"] = pivoted["op_margin"][1] - pivoted["op_margin"][[2,3,4,5]].mean(axis=1)
    accel = pivoted[
        (pivoted["EPS_YOY"] > 25) & (pivoted["EPS_QOQ"] > 5) &
        (pivoted["REV_YOY"] > 15) & (pivoted["MARGIN_DELTA"] > -1)
    ]
    return accel.sort_values("EPS_YOY", ascending=False)
```

**Files to create/modify:**
- `working-sector/fetch_screener_fundamental_details.R` — add quarterly scrape
- `data/quarterly_eps.csv` — new data file
- `screeners.py` — `earnings_acceleration_screener()`

**Dependencies:** Screener.in quarterly table scrape for top 200 Nifty500 stocks

---

#### A5 — Institutional Accumulation Screener
**Size:** M | **Priority:** Medium — requires F&O OI data (P1-2) for full confirmation

**What to build:**
```python
def institutional_accumulation_screener(universe: pd.DataFrame, price_history: dict) -> pd.DataFrame:
    """
    IBD-style Accumulation/Distribution rating based on up-volume vs down-volume.

    For last 65 trading days per stock:
      up_vol = sum(volume on days where close > prev_close)
      down_vol = sum(volume on days where close ≤ prev_close)
      ud_ratio = up_vol / down_vol

    Grades: A+ (>2.0), A (1.5-2.0), B (1.2-1.5), C (0.8-1.2), D (<0.8)
    Only include grade B or better.

    Supplementary confirmation (if P1-2 available):
    OI buildup signal (OI_CHANGE_5D > +15%) adds +0.2 to effective ud_ratio.
    """
    results = []
    for sym, row in universe.iterrows():
        ph = price_history.get(sym)
        if ph is None or len(ph) < 65:
            continue
        recent = ph.tail(65)
        up_mask = recent["CLOSE"] > recent["CLOSE"].shift(1)
        up_vol = recent.loc[up_mask, "VOLUME"].sum()
        down_vol = recent.loc[~up_mask, "VOLUME"].sum()
        ud_ratio = up_vol / max(down_vol, 1)
        if ud_ratio >= 1.2:
            grade = "A+" if ud_ratio > 2.0 else "A" if ud_ratio > 1.5 else "B"
            results.append({**row.to_dict(), "UD_RATIO": round(ud_ratio, 2), "ACCUM_GRADE": grade})
    return pd.DataFrame(results).sort_values("UD_RATIO", ascending=False)
```

**Dependencies:** P1-2 (optional OI confirmation); `price_history` dict with CLOSE + VOLUME (65d)

---

#### A6 — Turnaround Detector
**Size:** S | **Priority:** Medium — finds recovery candidates before institutional attention arrives

**What to build:**
```python
def turnaround_screener(universe: pd.DataFrame, price_history: dict) -> pd.DataFrame:
    """
    Turnaround = deep fall + early recovery signal

    Criteria:
    1. Max drawdown from peak in last 120 days: < -30%  (was in significant downtrend)
    2. Current price > SMA_50 (crossed up recently)
    3. RSI recovering: 35 ≤ RSI ≤ 58
    4. SUPERTREND_STATE in {'BULLISH', 'NEUTRAL'}

    Score: lower RSI (=earlier in recovery) ranked first.
    Shows MAX_DRAWDOWN_PCT so user understands the fall magnitude.
    """
    results = []
    for sym, row in universe.iterrows():
        ph = price_history.get(sym)
        if ph is None or len(ph) < 120:
            continue
        close = ph["CLOSE"].tail(120)
        drawdown = (close / close.cummax() - 1).min() * 100  # most negative
        if drawdown > -30:
            continue
        if (row.get("CLOSE", 0) > row.get("SMA_50", 0) and
            35 <= row.get("RSI", 50) <= 58 and
            row.get("SUPERTREND_STATE", "") in ("BULLISH", "NEUTRAL")):
            results.append({**row.to_dict(), "MAX_DRAWDOWN_PCT": round(drawdown, 1),
                             "TURNAROUND_SIGNAL": "EARLY_RECOVERY"})
    return pd.DataFrame(results).sort_values("RSI", ascending=True)
```

**Acceptance criteria:** Candidates shown with `MAX_DRAWDOWN_PCT`; sorted by RSI ascending (earlier in recovery = lower RSI).

---

#### A7 — Quality Compounder Screener
**Size:** M | **Priority:** High — long-term wealth creation; lowest turnover, highest conviction

**What exists:** Single-year ROE + Debt/Equity in cache. No 5-year trend.

**Data enrichment (R):** Add 5-year P&L and ROCE to `fetch_screener_fundamental_details.R`:
```r
# Scrape #profit-loss table (annual, last 5 years): Revenue, PAT, ROCE
# Compute: REV_CAGR_5Y, PAT_CAGR_5Y, AVG_ROE_5Y, AVG_ROCE_5Y
# Save to: data/quality_fundamentals.csv
```

**Screener logic:**
```python
def quality_compounder_screener(fundamentals: pd.DataFrame) -> pd.DataFrame:
    """
    Criteria (ALL must be met):
    Rev CAGR 5Y > 15%, PAT CAGR 5Y > 18%, avg ROE > 20%, Debt/Equity < 0.3, Promoter > 45%

    QUALITY_SCORE (0-100):
    = rev_cagr/30×20 + pat_cagr/35×20 + avg_roe/30×20 + avg_roce/28×20 + (1-D/E/0.5)×10 + promoter_bonus×10
    """
    df = fundamentals.dropna(subset=["REV_CAGR_5Y", "PAT_CAGR_5Y", "AVG_ROE_5Y", "DEBT_EQUITY"])
    quality = df[
        (df["REV_CAGR_5Y"] > 15) & (df["PAT_CAGR_5Y"] > 18) &
        (df["AVG_ROE_5Y"] > 20) & (df["DEBT_EQUITY"] < 0.3) & (df["PROMOTER_HOLDING"] > 45)
    ].copy()
    quality["QUALITY_SCORE"] = (
        quality["REV_CAGR_5Y"].clip(0, 30) / 30 * 20 +
        quality["PAT_CAGR_5Y"].clip(0, 35) / 35 * 20 +
        quality["AVG_ROE_5Y"].clip(0, 30) / 30 * 20 +
        quality["AVG_ROCE_5Y"].clip(0, 28) / 28 * 20 +
        (1 - quality["DEBT_EQUITY"].clip(0, 0.5) / 0.5) * 10 +
        quality["PROMOTER_HOLDING"].apply(lambda x: 10 if x > 50 else 5)
    )
    return quality.sort_values("QUALITY_SCORE", ascending=False)
```

**Files to create/modify:**
- `working-sector/fetch_screener_fundamental_details.R` — add 5yr P&L + ROCE
- `data/quality_fundamentals.csv` — 5-year fundamentals per symbol
- `screeners.py` — `quality_compounder_screener()`

**Acceptance criteria:** Returns 20–60 quality compounders from Nifty500. `QUALITY_SCORE` shown with component breakdown.

---

#### A8 — Hidden Champions (Small/Mid Cap Niche Leaders)
**Size:** M | **Priority:** Medium — highest alpha potential; requires A7 as input

**What to build:**
```python
def hidden_champions_screener(fundamentals: pd.DataFrame, universe: pd.DataFrame) -> pd.DataFrame:
    """
    Hidden Champion: niche leader with quality fundamentals and low analyst coverage

    Criteria:
    - Market cap: 500–8,000 Cr (small/mid cap)
    - Rev CAGR 3Y > 20%, Operating Margin > 15%, ROE > 18%, D/E < 0.5, Promoter > 50%
    - NOT in Nifty100 (lower coverage = more mispricing opportunity)

    HIDDEN_SCORE = QUALITY_SCORE×0.5 + growth_score×0.3 + niche_bonus×0.2
    niche_bonus: 100 if not in Nifty100, else 30
    """
    small_mid = fundamentals[
        fundamentals["MARKET_CAP_CR"].between(500, 8000) &
        (fundamentals["REV_CAGR_3Y"] > 20) & (fundamentals["OP_MARGIN"] > 15) &
        (fundamentals["ROE"] > 18) & (fundamentals["DEBT_EQUITY"] < 0.5) &
        (fundamentals["PROMOTER_HOLDING"] > 50)
    ].copy()
    nifty100 = _load_index_constituents("Nifty 100")
    small_mid["NICHE_BONUS"] = small_mid["SYMBOL"].apply(lambda s: 100 if s not in nifty100 else 30)
    small_mid["HIDDEN_SCORE"] = (
        small_mid.get("QUALITY_SCORE", 50) * 0.5 +
        (small_mid["REV_CAGR_3Y"].clip(0, 30) / 30 * 50) * 0.3 +
        small_mid["NICHE_BONUS"] * 0.2
    )
    return small_mid.sort_values("HIDDEN_SCORE", ascending=False).head(30)
```

**Dependencies:** A7 quality fundamentals; Nifty100 constituent list from `data/nse_indices_catalog.csv`

---

### BRANCH B — INDEX & INTER-MARKET INTELLIGENCE

**File to create:** `index_intelligence.py`  
**Output:** data embedded in main report HTML + optional standalone `reports/index_intelligence_{date}.html`

---

#### B1 — Cross-Index Breadth Dashboard
**Size:** M | **Priority:** High — shows market-wide health at a glance

**What exists:** `analyze_comprehensive_market_breadth.R` covers Nifty500 only. No multi-index comparison.

**What to build:**
```python
def cross_index_breadth(index_constituent_data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    Input: {index_name: DataFrame with SYMBOL, CLOSE, SMA_50, SMA_200, HIGH_52W, LOW_52W, RET_1D}

    For each index compute:
    - pct_above_200dma:  (CLOSE > SMA_200).mean() × 100
    - pct_above_50dma:   (CLOSE > SMA_50).mean() × 100
    - pct_near_52wh:     (CLOSE / HIGH_52W > 0.95).mean() × 100  (within 5% of 52W high)
    - pct_near_52wl:     (CLOSE / LOW_52W < 1.05).mean() × 100   (within 5% of 52W low)
    - ad_ratio:          advances / max(declines, 1)

    Breadth signal:
    STRONG  : pct_above_200 > 70 AND ad_ratio > 1.8
    HEALTHY : pct_above_200 60–70
    NEUTRAL : pct_above_200 45–60
    WEAK    : pct_above_200 30–45
    BEARISH : pct_above_200 < 30 OR pct_near_52wl > 15

    Indices to cover: Nifty50, Nifty500, MidCap150, SmallCap250,
                      Bank Nifty, IT, Pharma, Auto, FMCG, Metal
    """
```

**Integration:** Breadth signal of Nifty50 + SmallCap divergence → input to regime detector.  
If Nifty50=STRONG but SmallCap=WEAK → selective/ROTATION regime signal.

**Files to create/modify:**
- `index_intelligence.py` — `cross_index_breadth()`
- `sector_rotation_report.py` — import and add breadth row to regime banner HTML

---

#### B2 — Global Correlation Monitor
**Size:** M | **Priority:** Medium — identifies contagion risk and decoupling opportunity

**What to build:**
```python
GLOBAL_TICKERS = {
    "S&P 500": "^GSPC", "Nasdaq": "^IXIC", "Euro Stoxx 50": "^STOXX50E",
    "Hang Seng": "^HSI", "Nikkei 225": "^N225", "Gold": "GC=F",
    "Crude Oil": "CL=F", "Copper": "HG=F", "DXY": "DX-Y.NYB", "USDINR": "USDINR=X",
}

def fetch_global_indices(tickers: dict, lookback_days: int = 120) -> pd.DataFrame:
    """Fetch via yfinance, cache to data/global_indices.csv (TTL: 24h)."""
    import yfinance as yf
    data = {}
    for name, ticker in tickers.items():
        try:
            data[name] = yf.Ticker(ticker).history(period="6mo")["Close"]
        except Exception:
            pass  # missing global index is non-fatal
    return pd.DataFrame(data).dropna(how="all")

def compute_correlations(nifty_series: pd.Series, global_df: pd.DataFrame) -> pd.DataFrame:
    """
    30d and 60d rolling correlation of Nifty500 vs each global asset.

    Alert: DECOUPLING when |corr_30d - corr_60d| > 0.20
    (Decoupling = potential India-specific story forming or unwinding)

    Output: asset, corr_30d, corr_60d, change, alert
    """
```

**Files to create/modify:**
- `index_intelligence.py` — `fetch_global_indices()`, `compute_correlations()`
- `data/global_indices.csv` — new data file

**Dependencies:** `yfinance` (`pip install yfinance` into .venv)  
**Acceptance criteria:** Correlation table in < 30s. Decoupling alert fires when 30d vs 60d diverges > 20pp.

---

#### B3 — Sectoral Heat Calendar
**Size:** M | **Priority:** High — seasonal alpha is one of the most reliable edges in NSE

**What to build:**
```python
def build_seasonal_heat_calendar(sector_monthly_returns: pd.DataFrame, lookback_years: int = 7) -> tuple:
    """
    Input: monthly returns per sector index (from data/nse_index_data.csv, last 7 years)
    Output: (matrix, heat) where matrix = 12-row × N-sector avg monthly return table

    Seasonal signal per sector:
    TAILWIND : avg monthly return > +2% in current month (n ≥ 5 observations)
    HEADWIND : avg monthly return < -1%
    NEUTRAL  : otherwise

    Examples:
    FMCG:     Aug/Sep/Oct strong (festive pre-stocking)
    Metals:   Feb/Mar weak (budget), Apr/May strong (infra season)
    Auto:     Sep/Oct strong (festive), Jan/Feb weak (post-festive)
    IT:       Oct-Dec strong (deal wins), Apr weak (guidance season)
    """
    df = sector_monthly_returns.copy()
    df["month"] = pd.to_datetime(df["date"]).dt.month
    heat = df.groupby(["sector", "month"])["return_pct"].agg(avg="mean", std="std", n="count").reset_index()
    matrix = heat.pivot_table(index="month", columns="sector", values="avg")
    matrix.index = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    return matrix, heat

def render_heat_calendar_html(matrix: pd.DataFrame) -> str:
    """
    Returns HTML table with green/red color gradient per cell.
    Current month column outlined in blue.
    Each cell: avg return % + arrow icon (↑↓→).
    """
```

**Integration:** `SEASONAL_SIGNAL` column in sector rank table; passed to LLM prompt as seasonal context.

**Acceptance criteria:** Calendar renders for 8+ NSE sector indices. Current month highlighted. `SEASONAL_SIGNAL` in sector rank.

---

#### B4 — FII/DII Flow Battle Tracker
**Size:** M | **Priority:** High — who is winning between FII and DII drives medium-term direction

**What to build:**
```python
def fii_dii_battle_tracker(flows: pd.DataFrame, lookback_days: int = 60) -> dict:
    """
    Input: flows DataFrame (from P1-3) with [date, fii_net, dii_net]

    Battle signals:
    FII_DOMINANT  : fii_net_20d > +5,000 Cr AND dii_net_20d < 0
    DII_DEFENDING : dii_net_20d > 3,000 Cr (domestic absorption offsets FII)
    FII_FLEEING   : fii_net_20d < -8,000 Cr (sustained selling)
    BOTH_BUYING   : fii_net_20d > 0 AND dii_net_20d > 2,000 Cr → strongest bull signal
    STANDOFF      : both flows < 1,000 Cr absolute

    Output dict:
    {battle_signal, fii_net_5d, fii_net_20d, dii_net_5d, dii_net_20d,
     narrative, sector_fii_preference (from P1-2 participant OI)}
    """
```

**Dependencies:** P1-3 (FII/DII flows), P1-2 participant OI for sector allocation  
**Acceptance criteria:** Battle signal + 5d/20d flows shown in regime banner HTML.

---

#### B5 — Economic Cycle Tracker
**Size:** L | **Priority:** Medium — strategic positioning framework; maps macro to sector preference

**What to build:**
```python
CYCLE_PHASES = {
    "EARLY_EXPANSION": {
        "definition": "PMI rising from < 50, IIP accelerating, GST growth improving",
        "preferred_sectors": ["Banking", "Consumer Discretionary", "Real Estate", "Auto"],
        "avoid_sectors": ["Utilities", "FMCG"],
    },
    "LATE_EXPANSION": {
        "definition": "PMI > 55, inflation rising, yield curve flattening",
        "preferred_sectors": ["Energy", "Metals", "Capital Goods"],
        "avoid_sectors": ["Rate-sensitive (Banking, NBFC, Real Estate)"],
    },
    "SLOWDOWN": {
        "definition": "PMI falling from peak, IIP decelerating",
        "preferred_sectors": ["FMCG", "Pharma", "IT"],
        "avoid_sectors": ["Metals", "Auto", "Real Estate"],
    },
    "RECOVERY": {
        "definition": "PMI at trough and reversing, fiscal stimulus active",
        "preferred_sectors": ["Banking", "Capital Goods", "Infrastructure", "Cement"],
        "avoid_sectors": ["Defensives (underperform in recovery)"],
    },
}

def detect_economic_cycle_phase(macro_signals: pd.DataFrame, market_regime: str) -> dict:
    """
    Decision tree using PMI, IIP YoY, GST growth from P1-6.
    Cross-check with market regime (P1-1):
    - Cycle EXPANSION but market BEAR → potential opportunity
    - Cycle SLOWDOWN but market BULL → market ahead of fundamentals (be cautious)
    Returns: {cycle_phase, confidence, preferred_sectors, regime_cycle_alignment}
    """
```

**Integration:** Cycle phase adjusts sector scoring: `CYCLE_FAVOURED` → +4, `CYCLE_UNFAVOURED` → -3  
**Dependencies:** P1-6 (macro proxies), P1-1 (regime detector)

---

### BRANCH C — MARKET BREADTH INTELLIGENCE

**File to create:** `market_breadth.py`  
**Output:** `data/breadth_history.csv` (daily cumulative); breadth section in main HTML report

---

#### C1 — McClellan Oscillator & Summation Index
**Size:** M | **Priority:** High — leading indicator for market tops and breadth divergences

**What exists:** `analyze_comprehensive_market_breadth.R` has basic A/D. No McClellan.

**What to build:**
```python
def compute_mcclellan(net_advance_decline: pd.Series) -> pd.DataFrame:
    """
    McClellan Oscillator = EMA_19(net_AD) - EMA_39(net_AD)
    Summation Index = cumulative sum of Oscillator

    Signals:
    > +70  → overbought breadth
    < -70  → oversold breadth (potential bounce)
    Cross zero from below → BULLISH_CROSS
    Cross zero from above → BEARISH_CROSS
    Summation > 0 and rising → bull market breadth
    Summation < 0 and falling → bear market breadth

    Divergence detection:
    BULLISH_DIVERGENCE : price new low but Oscillator higher low → potential reversal
    BEARISH_DIVERGENCE : price new high but Oscillator lower high → distribution
    """
    ema19 = net_advance_decline.ewm(span=19, adjust=False).mean()
    ema39 = net_advance_decline.ewm(span=39, adjust=False).mean()
    oscillator = ema19 - ema39
    summation = oscillator.cumsum()
    signal = pd.Series("NEUTRAL", index=oscillator.index)
    signal[oscillator > 70] = "OVERBOUGHT"
    signal[oscillator < -70] = "OVERSOLD"
    signal[(oscillator > 0) & (oscillator.shift(1) <= 0)] = "BULLISH_CROSS"
    signal[(oscillator < 0) & (oscillator.shift(1) >= 0)] = "BEARISH_CROSS"
    return pd.DataFrame({"oscillator": oscillator.round(1), "summation": summation.round(0), "signal": signal})

def get_advance_decline_series(universe_df: pd.DataFrame) -> pd.Series:
    """Compute daily net A/D from Nifty500 universe (CLOSE > PREV_CLOSE = advance)."""
    daily = universe_df.copy()
    daily["ADV"] = daily["CLOSE"] > daily["CLOSE"].shift(1)
    ad = daily.groupby("DATE").agg(advances=("ADV", "sum"), declines=("ADV", lambda x: (~x).sum()))
    return (ad["advances"] - ad["declines"]).rename("net_ad")
```

**Files to create/modify:**
- `market_breadth.py` — `compute_mcclellan()`, `get_advance_decline_series()`
- `data/breadth_history.csv` — add `oscillator`, `summation`, `signal` columns
- `sector_rotation_report.py` — McClellan value in HTML header badge

**Acceptance criteria:** Oscillator value and signal displayed in HTML. Divergence alerts show when detected.

---

#### C2 — TRIN / Arms Index (Volume Breadth)
**Size:** S | **Priority:** Medium — volume-weighted breadth captures institutional activity better than price A/D

**What to build:**
```python
def compute_trin(universe_df: pd.DataFrame) -> pd.DataFrame:
    """
    TRIN = (Advances / Declines) / (Advancing Volume / Declining Volume)

    < 0.5  → very bullish (volume overwhelmingly on advancing stocks)
    0.5–0.8 → bullish
    0.8–1.2 → neutral
    1.2–2.0 → bearish
    > 2.0  → very bearish / panic selling (contrarian: potential washout low)

    5-day avg TRIN < 0.75 → internally strong despite surface weakness
    5-day avg TRIN > 1.40 → internally weak despite surface strength
    """
    daily = universe_df.copy()
    daily["UP"] = daily["CLOSE"] > daily["CLOSE"].shift(1)
    def trin_for_day(g):
        adv = g["UP"].sum(); dec = (~g["UP"]).sum()
        avol = g.loc[g["UP"], "VOLUME"].sum(); dvol = g.loc[~g["UP"], "VOLUME"].sum()
        return (adv / max(dec, 1)) / (avol / max(dvol, 1))
    trin_series = universe_df.groupby("DATE").apply(trin_for_day)
    df = pd.DataFrame({"trin": trin_series})
    df["trin_5d"] = df["trin"].rolling(5).mean()
    df["signal"] = df["trin"].map(lambda t:
        "VERY_BULLISH" if t < 0.5 else "BULLISH" if t < 0.8 else
        "NEUTRAL" if t < 1.2 else "BEARISH" if t < 2.0 else "PANIC")
    return df
```

**Files to create/modify:** `market_breadth.py` — `compute_trin()`; `data/breadth_history.csv` — add `trin`, `trin_5d`

---

#### C3 — Sector Breadth Divergence Monitor
**Size:** M | **Priority:** High — early warning for sector distribution

**What to build:**
```python
def sector_breadth_divergence(universe_df: pd.DataFrame) -> pd.DataFrame:
    """
    For each sector:
    - pct_above_50dma:  (CLOSE > SMA_50).mean() × 100
    - pct_above_200dma: (CLOSE > SMA_200).mean() × 100
    - change_5d:        compare vs breadth_history 5 days ago

    Divergence alerts:
    BULLISH_DIV  : sector index new low BUT pct_above_50dma higher low → accumulation
    BEARISH_DIV  : sector index new high BUT pct_above_50dma falling → distribution
    INT_WEAKNESS : index flat BUT pct_above_50dma fell > 10pp in 5d (few large caps holding index)

    breadth_signal: HEALTHY (pct50 > 60), NEUTRAL (40–60), WEAK (< 40)
    """
```

**Integration:** `sector_breadth_pct50` column added to sector rank table alongside RS score.  
**Files to create/modify:** `market_breadth.py` — `sector_breadth_divergence()`; `sector_rotation_report.py` — merge into sector rank

---

#### C4 — Smart Money Flow Index
**Size:** M | **Priority:** Medium — tracks institutional vs retail behavior

**What to build:**
```python
def smart_money_flow_index(price_volume_df: pd.DataFrame) -> pd.DataFrame:
    """
    EOD Smart Money approximation:
    SMFI_daily = Close × Volume × ((Close - Open) / (High - Low + 0.01))

    Positive SMFI: closed near high on high volume → buying pressure
    Negative SMFI: closed near low on high volume → selling pressure

    5d SMFI sum vs 20d SMFI sum:
    5d > 20d × 1.05 → ACCUMULATING
    5d < 20d × 0.95 → DISTRIBUTING
    else            → NEUTRAL

    Composite (if P1-2 + P1-4 available):
    SMFI_TREND + block_deal_net + fii_oi_net → ACCUMULATING / DISTRIBUTING / NEUTRAL
    """
    df = price_volume_df.copy()
    price_range = (df["HIGH"] - df["LOW"]).clip(lower=0.01)
    df["SMFI"] = df["CLOSE"] * df["VOLUME"] * ((df["CLOSE"] - df["OPEN"]) / price_range)
    df["SMFI_5D"] = df["SMFI"].rolling(5).sum()
    df["SMFI_20D"] = df["SMFI"].rolling(20).sum()
    df["SMFI_SIGNAL"] = df.apply(
        lambda r: "ACCUMULATING" if r["SMFI_5D"] > r["SMFI_20D"] * 1.05 else
                  "DISTRIBUTING" if r["SMFI_5D"] < r["SMFI_20D"] * 0.95 else "NEUTRAL", axis=1
    )
    return df
```

**Dependencies:** SMFI alone is independent; full composite needs P1-2 + P1-4.

---

### BRANCH D — DEEP FUNDAMENTAL INTELLIGENCE

**File to create:** `deep_fundamentals.py`  
**Data dependency:** Screener.in 5-year P&L + balance sheet + cash flow (source N in registry)

---

#### D1 — DuPont Decomposition Engine
**Size:** M | **Priority:** High — distinguishes real quality from leverage-driven ROE

**What exists:** Single-year ROE in `_sector_rotation_fund_cache.csv`. No decomposition or trend.

**What to build:**
```python
def dupont_decompose(fundamentals_5yr: pd.DataFrame) -> pd.DataFrame:
    """
    3-Factor DuPont:
    ROE = Net Profit Margin × Asset Turnover × Equity Multiplier
        = (NP / Revenue) × (Revenue / Assets) × (Assets / Equity)

    5-Factor extended:
    ROE = Tax Burden × Interest Burden × EBIT Margin × Asset Turnover × Leverage

    YoY ROE change attribution:
    MARGIN_DRIVEN    : margin contribution > turnover + leverage contribution
    EFFICIENCY_DRIVEN: turnover contribution dominates
    LEVERAGE_DRIVEN  : leverage contribution dominates → RED FLAG (quality concern)

    Per stock: compute for each of 5 years, show trend and current year driver.
    """
    result = fundamentals_5yr.copy()
    result["NET_MARGIN"]       = result["NET_PROFIT"] / result["REVENUE"]
    result["ASSET_TURNOVER"]   = result["REVENUE"] / result["TOTAL_ASSETS"]
    result["EQUITY_MULTIPLIER"]= result["TOTAL_ASSETS"] / result["SHAREHOLDERS_EQUITY"]
    result["ROE_DECOMPOSED"]   = result["NET_MARGIN"] * result["ASSET_TURNOVER"] * result["EQUITY_MULTIPLIER"]

    def flag_driver(row):
        margin_delta   = abs(row.get("MARGIN_CONTRIBUTION", 0))
        turnover_delta = abs(row.get("TURNOVER_CONTRIBUTION", 0))
        leverage_delta = abs(row.get("LEVERAGE_CONTRIBUTION", 0))
        if leverage_delta and leverage_delta == max(margin_delta, turnover_delta, leverage_delta):
            return "LEVERAGE_DRIVEN_RED_FLAG"
        return "MARGIN_DRIVEN" if margin_delta >= max(turnover_delta, leverage_delta) else "EFFICIENCY_DRIVEN"

    result["ROE_DRIVER"] = result.apply(flag_driver, axis=1)
    return result
```

**Integration:** `LEVERAGE_DRIVEN_RED_FLAG` stocks get -5 `INVESTMENT_SCORE` penalty; badge in HTML.  
**Files to create/modify:** `deep_fundamentals.py` — `dupont_decompose()`; `data/quality_fundamentals.csv`

---

#### D2 — Earnings Quality Score
**Size:** M | **Priority:** High — single best fraud proxy; cash > accruals = genuine earnings

**Data enrichment (R):**
```r
# Extend fetch_screener_fundamental_details.R:
# Scrape #cash-flow table (last 5 years): CFO, Capex, FCF
# Add to data/_sector_rotation_fund_cache.csv or separate data/cashflow_data.csv
```

**What to build:**
```python
def earnings_quality_score(merged: pd.DataFrame) -> pd.DataFrame:
    """
    4 components:

    1. Cash Conversion Ratio (CCR) = CFO / Net_Profit
       > 1.0 → cash exceeds earnings (high quality)
       < 0.0 → operating cash negative despite profit → RED FLAG

    2. Accruals Ratio (Sloan) = (Net_Profit - CFO) / Avg_Total_Assets
       < 0.0 → CFO > earnings → high quality

    3. FCF Yield = (CFO - Capex) / Market_Cap
       > 5% → attractive

    4. DSO Trend = (Receivables / Revenue × 365) — rising = channel stuffing risk

    EQ_SCORE (0–100):
    = ccr_score×30 + accruals_score×30 + fcf_yield_score×25 + dso_score×15

    CCR < 0 → CCR_CONCERN flag regardless of other scores.
    """
    merged["CCR"] = merged["CFO"] / merged["NET_PROFIT"].replace(0, 0.001)
    merged["ACCRUALS"] = (merged["NET_PROFIT"] - merged["CFO"]) / merged["TOTAL_ASSETS"]
    merged["FCF"] = merged["CFO"] - merged["CAPEX"]
    merged["FCF_YIELD"] = merged["FCF"] / (merged["MARKET_CAP_CR"] * 1e7)
    merged["CCR_CONCERN"] = merged["CCR"] < 0
    merged["EQ_SCORE"] = (
        merged["CCR"].clip(0, 1.5) / 1.5 * 100 * 0.30 +
        (1 - merged["ACCRUALS"].clip(0, 0.05) / 0.05) * 100 * 0.30 +
        merged["FCF_YIELD"].clip(0, 0.08) / 0.08 * 100 * 0.25 +
        # DSO score: approximated as 25 if unavailable
        pd.Series(25, index=merged.index) * 0.15
    ).round(1)
    return merged
```

**Acceptance criteria:** `EQ_SCORE` (0–100) in HTML. `CCR_CONCERN` badge. Score adjusts `INVESTMENT_SCORE` by `(EQ_SCORE - 50) / 20`.

---

#### D3 — Business Cycle Sector Positioning
*Stock-level extension of B5. See B5 spec.*

```python
def map_stocks_to_cycle(universe: pd.DataFrame, cycle_phase: str) -> pd.DataFrame:
    """Tag each stock CYCLE_FAVOURED / CYCLE_NEUTRAL / CYCLE_UNFAVOURED
    based on sector and current cycle phase from B5.
    Adjust INVESTMENT_SCORE: +4 for favoured, -3 for unfavoured."""
    phase = CYCLE_PHASES.get(cycle_phase, {})
    universe["CYCLE_TAG"] = universe["SECTOR"].apply(
        lambda s: "CYCLE_FAVOURED" if any(x.lower() in s.lower() for x in phase.get("preferred_sectors", []))
                  else "CYCLE_UNFAVOURED" if any(x.lower() in s.lower() for x in phase.get("avoid_sectors", []))
                  else "CYCLE_NEUTRAL"
    )
    return universe
```

---

#### D4 — Concall Sentiment NLP
*This is the same as P2-5 in Phase 2 above. Refer to P2-5 spec for full implementation.*  
Branch D cross-references D4 → P2-5. **Do not duplicate implementation.**

---

#### D5 — Forensic Accounting Suite (Beneish + Piotroski + Altman)
**Size:** L | **Priority:** High — prevents buying accounting frauds; saves capital

**What exists:** Nothing. No multi-model scoring.

**What to build:**
```python
def beneish_mscore(fin: dict) -> float:
    """
    Beneish M-Score: detects earnings manipulation via 8 variables.
    M > -1.78 → likely manipulator (RED FLAG)
    M < -2.22 → unlikely manipulator

    Variables:
    DSRI  = (Rec_t/Sales_t) / (Rec_t-1/Sales_t-1)          [receivables inflation]
    GMI   = GrossMargin_t-1 / GrossMargin_t                  [margin deterioration]
    AQI   = (1-(CA+PPE)/TA)_t / (1-(CA+PPE)/TA)_t-1        [asset quality]
    SGI   = Sales_t / Sales_t-1                              [sales growth incentive]
    DEPI  = DepRate_t-1 / DepRate_t                          [depreciation manipulation]
    SGAI  = (SGA/Sales)_t / (SGA/Sales)_t-1                 [overhead bloat]
    LVGI  = Leverage_t / Leverage_t-1                        [covenant pressure]
    TATA  = (ΔWorkingCapital - Depreciation) / TotalAssets   [accruals]

    M = -4.84 + 0.920×DSRI + 0.528×GMI + 0.404×AQI + 0.892×SGI
            + 0.115×DEPI - 0.172×SGAI + 4.679×TATA - 0.327×LVGI
    """

def piotroski_fscore(fin: dict) -> tuple[int, dict]:
    """
    9-point binary scoring system.

    PROFITABILITY (4 pts): ROA>0, CFO>0, ΔROA>0, CFO>Net_Income
    LEVERAGE/LIQUIDITY (3 pts): ΔLeverage<0, ΔCurrentRatio>0, No_new_shares
    EFFICIENCY (2 pts): ΔGrossMargin>0, ΔAssetTurnover>0

    F ≥ 7 → strong (buy candidate)
    F ≤ 2 → weak (avoid or short)
    """

def altman_zscore(fin: dict) -> tuple[float, str]:
    """
    Z = 1.2×X1 + 1.4×X2 + 3.3×X3 + 0.6×X4 + 1.0×X5
    X1=WorkCap/TA, X2=RetainedEarnings/TA, X3=EBIT/TA, X4=MktCap/Debt, X5=Sales/TA

    Z > 2.99 → SAFE | 1.81–2.99 → GREY | < 1.81 → DISTRESS
    """

def forensic_composite_score(symbol: str, fin: dict) -> dict:
    """
    FORENSIC_PASS  : Beneish < -2.22 AND Piotroski ≥ 6 AND Altman SAFE
    FORENSIC_WATCH : any one model in caution range
    FORENSIC_FAIL  : Beneish > -1.78 OR Piotroski ≤ 2 OR Altman DISTRESS

    FORENSIC_FAIL → block BUY recommendation regardless of technical signal
    Penalty: FORENSIC_FAIL → INVESTMENT_SCORE -= 10
    """
```

**Files to create/modify:**
- `deep_fundamentals.py` — all three models + `forensic_composite_score()`
- `data/forensic_scores.csv` — cached results (TTL: 30d)
- `sector_rotation_report.py` — forensic badge in HTML; FORENSIC_FAIL → -10 penalty

**Dependencies:** 2-year P&L + balance sheet + cash flow from Screener.in (source N)  
**Acceptance criteria:**
- Forensic badge in HTML: green=PASS, amber=WATCH, red=FAIL.
- Computed for > 80% of Nifty500.
- FORENSIC_FAIL stocks never appear in BUY recommendations.

---

#### D6 — Competitive Moat Score
**Size:** L | **Priority:** Medium — identifies stocks with durable pricing power

**What to build:**
```python
def competitive_moat_score(fundamentals_5yr: pd.DataFrame, peers: pd.DataFrame) -> pd.DataFrame:
    """
    Moat Score = composite of 5 proxies (0–100)

    1. PRICING POWER (0–25):
       Gross margin stability: avg_GM / 50 × 25 × (1 - min(CV_GM, 0.3)/0.3)
       High stable margin = pricing power moat

    2. SWITCHING COSTS (0–20):
       Revenue retention rate stability + sector bonus (IT, Specialty Chem: auto +5)

    3. COST ADVANTAGE (0–20):
       Operating margin vs peer average: (op_margin - peer_avg) / 20 × 20

    4. NETWORK EFFECT (0–15):
       Revenue growth acceleration + op leverage improvement
       Auto 15 points: Exchange, Payment, Marketplace sectors

    5. EFFICIENT SCALE (0–20):
       Economic profit = ROCE - 12% (hurdle rate)
       (ROCE - 12).clip(0, 20) / 20 × 20

    MOAT_CLASS: WIDE (≥70), NARROW (40–69), NONE (<40)
    WIDE_MOAT → +3 bonus on INVESTMENT_SCORE
    """
```

**Acceptance criteria:** MOAT_CLASS badge in HTML. Score breakdown in tooltip (pricing power %, ROCE vs hurdle).

---

### BRANCH E — COMPANY INTELLIGENCE LAYER

**File to create:** `company_intelligence.py`  
**Output:** `reports/company_{SYMBOL}_{date}.html` (on-demand per company)

---

#### E1 — 360° Company Deep-Dive Dashboard
**Size:** XL | **Priority:** Medium — run on-demand, not in bulk daily batch

**What to build:**
```python
def generate_company_dashboard(symbol: str, force_refresh: bool = False) -> Path:
    """
    Cache: data/company_cache/{SYMBOL}.json  (TTL: 7 days)
    CLI:   python company_intelligence.py --symbol TATASTEEL [--open]

    HTML sections:
    1. IDENTITY: company name, sector, market cap, business description
    2. PRICE & TECHNICAL CANVAS: 12m chart, 50/200DMA, Supertrend, Stage, Darvas box, Entry/Stop/Target
    3. FINANCIAL SCORECARD: 5yr Revenue/PAT/EPS bar chart, DuPont table (D1), EQ Score (D2), Forensic scores (D5)
    4. MOAT & COMPETITIVE POSITION: Moat score (D6) + Peer comparison table (E2)
    5. MANAGEMENT QUALITY: Promoter holding trend, insider events (P1-4), concall sentiment history (D4)
    6. UPCOMING EVENTS: next result date, ex-dividend, AGM, pending approvals (E4)
    7. LLM SYNTHESIS: full analyst-grade narrative integrating all 6 sections, 
                      investment thesis, key risks, valuation range
    """
```

---

#### E2 — Peer Comparison Engine
**Size:** M | **Priority:** High — relative valuation is the most-used technique

**What to build:**
```python
def fetch_peer_comparison(symbol: str) -> pd.DataFrame:
    """
    Scrape #peers table from https://www.screener.in/company/{symbol}/
    Columns: Name, CMP, P/E, Market Cap, Div Yield, NP Qtr, Qtr Profit Var, Sales Qtr, ROCE

    Processing:
    1. Compute percentile rank of target vs peers on each metric
    2. REL_VAL_SCORE = -pe_pct×0.25 + roe_pct×0.25 + growth_pct×0.25 + roce_pct×0.25
       > 0.5 → cheap vs peers on quality-adjusted basis
    3. Highlight: top-25th = green, bottom-25th = red

    Cache: data/peer_comparisons.csv (TTL: 30d)
    Rate limit: 5s sleep after each scrape
    """
```

**Acceptance criteria:** Peer table in company dashboard (E1). Target company row highlighted. Relative percentile shown for PE, ROE, Growth, ROCE.

---

#### E3 — Management Quality Score
**Size:** M | **Priority:** Medium — key differentiator between same-sector stocks

**What to build:**
```python
def management_quality_score(symbol: str, insider_data: pd.DataFrame,
                               concall_history: pd.DataFrame, fundamentals_5yr: pd.DataFrame) -> dict:
    """
    MQS = 4-component score (0–100)

    1. CAPITAL ALLOCATION (0–30):
       Buybacks done (+10), dividend CAGR > 10% (+10), D/E falling 5yr (+5), no dilutive equity raise (+5)

    2. PROMOTER COMMITMENT (0–25):
       Holding > 50% → 15 pts, trend RISING → +10, trend FALLING → -10
       Pledging: zero pledging → +5, pledging > 20% of promoter stake → -15

    3. CONCALL TONE TREND (0–20):
       Avg tone last 4 quarters: CONFIDENT=20, CAUTIOUS=12, DEFENSIVE=5
       Guidance raised → +5 bonus; cut → -5

    4. GOVERNANCE (0–25):
       Related party txn < 5% revenue → 15, ind directors > 33% board → 5,
       Auditor tenure > 5yr → 3, no SEBI action → 7

    MQS_CLASS: EXCELLENT (≥80), GOOD (60–79), ADEQUATE (40–59), POOR (<40)
    POOR management → -5 INVESTMENT_SCORE penalty
    """
```

**Acceptance criteria:** MQS badge in company dashboard + main report. Promoter holding sparkline in HTML.

---

#### E4 — Event-Driven Alert Engine
**Size:** M | **Priority:** High — time-sensitive catalysts are highest-value for active trading

**What to build:**
```python
def fetch_corporate_events(symbols: list[str], lookforward_days: int = 30) -> pd.DataFrame:
    """
    Sources:
    1. NSE: https://www.nseindia.com/api/corporates-corporateActions?index=equities
       Returns: ex-date, record date, purpose (dividend/bonus/rights/split/buyback)
    2. BSE: https://api.bseindia.com/BseIndiaAPI/api/AnnualResultSearch/w
       Returns: result announcement dates

    Event types and trading implications:
    RESULT_ANNOUNCEMENT : high volatility day; setup pre-result if earnings acceleration expected
    EX_DIVIDEND         : price drops by dividend; buy ex-date dip if uptrend intact
    BONUS / SPLIT       : psychological buying before ex-date; consolidation post-split
    BUYBACK             : company floor signal; check buyback_price vs CMP
    AGM                 : watch for guidance, capex, dividend policy changes

    INVESTMENT_SCORE adjustments:
    +3 : buyback above CMP (floor protection)
    +2 : result in 5–14 days + earnings acceleration expected
    -1 : result in next 3 days (uncertainty, reduce position sizing)

    Returns DataFrame: symbol, event_type, event_date, days_until, details
    Cache: data/corporate_events.csv (TTL: 24h)
    """

def generate_event_alerts(candidates: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    """Merge next event per symbol into candidates DataFrame.
    Add columns: NEXT_EVENT, NEXT_EVENT_DATE, NEXT_EVENT_DAYS.
    Generate alert text: 'RESULT in 3d — pre-result setup if RSI dip entry available'"""
```

**Files to create/modify:**
- `company_intelligence.py` — `fetch_corporate_events()`, `generate_event_alerts()`
- `data/corporate_events.csv` — daily cache
- `sector_rotation_report.py` — merge events; show `NEXT_EVENT` badge in HTML

**Acceptance criteria:**
- Events fetched daily and cached.
- Stocks with results in next 7 days flagged with `RESULT_UPCOMING` badge.
- Buyback above CMP shown with ₹target and % premium.
- Missing events = empty field, not error.

---

### Phase 4 — Branch F: Financial Filing Intelligence Agent

This branch builds first-class quarterly/annual filing analysis from NSE/BSE/company IR filings. It is intentionally separate from Screener.in-derived fundamentals because exchange filings are the primary evidence source, while Screener.in remains a convenient comparison layer.

#### F2 — NSE/BSE Filing Discovery
**Size:** L | **Priority:** High | **Status:** 🔜 READY

**What to build:**
```python
def discover_financial_filings(symbol: str, quarter: str | None = None, max_results: int = 10) -> list[dict]:
    """
    Resolve symbol, query NSE financial-results / integrated-filing pages, then BSE/company IR fallback.
    Prefer Integrated Filing - Financial XBRL/iXBRL when available; collect PDF as evidence.

    Return records:
      symbol, company_name, filing_date, reporting_period, filing_type,
      consolidated_or_standalone, xbrl_url, ixbrl_url, pdf_url, source, confidence
    """
```

**Files to create/modify:**
- `financial_filing_agent.py`
- `terminal/tools.py` — add `discover_financial_filings` tool
- `terminal/agent.py` — route "latest quarterly report/results filing" queries
- `tests/test_financial_filing_discovery.py`

**Acceptance criteria:**
- `discover_financial_filings("BLUESTARCO")` returns the latest available filing candidates when network is available.
- Direct URL path remains supported when NSE discovery fails.
- Result ranking prefers XBRL/iXBRL over PDF-only filings.
- All network calls use browser-like headers, timeout, retry, and cache.

#### F3 — XBRL/iXBRL Parser + Canonical Financial Facts
**Size:** L | **Priority:** Critical | **Status:** 🔜 READY

**What to build:**
```python
def parse_xbrl_filing(path: str) -> dict:
    """
    Parse XBRL/iXBRL into canonical facts:
      company metadata, reporting period, standalone/consolidated flag,
      revenue, other income, expenses, EBITDA/operating profit, finance cost,
      PBT, tax, PAT, EPS, assets, liabilities, equity, cash flow, segment data.

    Preserve:
      raw tag, context id, unit, decimals, period start/end, source file, fact confidence.
    """
```

**Files to create/modify:**
- `financial_filing_agent.py`
- `tests/fixtures/filings/sample_integrated_filing_ixbrl.html`
- `tests/test_financial_filing_xbrl.py`

**Acceptance criteria:**
- Parser can read NSE integrated-filing-style iXBRL tables and regular XML.
- Canonical JSON is stable even when tag names differ.
- Unit normalization handles Rs crore/lakh/absolute INR.
- Missing facts are `None` with warnings, never hallucinated.

#### F4a — Image-Only Filing OCR Fallback
**Size:** M | **Priority:** High | **Status:** 🔜 READY

**What to build:**
- Detect image-only financial-result PDFs and route them to OCR.
- Prefer local OCR if available; otherwise allow an LLM vision/OCR provider behind explicit configuration.
- Preserve page evidence and confidence level so extracted figures are not treated as verified facts until reconciled.

**Acceptance criteria:**
- HDFC Bank FY26 Q4 results produces page text evidence instead of only `OCR_REQUIRED`.
- OCR output records page number, text excerpt, backend used, and confidence.
- Pipeline keeps working when OCR backend is absent by returning actionable setup guidance.

#### F5 — Reconciliation + Verification Agent
**Size:** M | **Priority:** Critical | **Status:** 🔜 READY

**What to build:**
```python
def reconcile_filing_facts(xbrl_facts: dict | None, pdf_facts: dict | None) -> dict:
    """
    Compare XBRL facts and PDF extracted facts.
    Detect:
      unit mismatch, standalone/consolidated mismatch, period mismatch,
      total mismatch, missing prior-period columns, rounded-value differences.

    Output verification status:
      VERIFIED, PARTIAL, CONFLICT, UNAVAILABLE
    """
```

**Files to create/modify:**
- `financial_filing_agent.py`
- `tests/test_financial_filing_reconciliation.py`

**Acceptance criteria:**
- XBRL values are source of truth when present.
- PDF-only facts are allowed but marked lower confidence.
- Final narrative cannot use a key metric unless it has source evidence or an explicit unverified label.

#### F6 — LLM-Based Filing Analysis Agents
**Size:** L | **Priority:** High | **Status:** 🔜 READY

**What to build:**
- Add agent prompts for:
  - Numbers Analyst
  - Balance Sheet Analyst
  - Cash Flow Analyst
  - Segment/Product Analyst
  - Risk/Auditor Notes Analyst
  - Narrative Writer
- Inputs must be canonical JSON + evidence map, not raw unbounded PDF text.
- Output must be structured JSON before rendering.

**Files to create/modify:**
- `financial_filing_agent.py`
- `tests/test_financial_filing_analysis.py`
- `terminal/tools.py` — add `analyze_financial_filing`

**Acceptance criteria:**
- LLM output contains executive summary, key financial metrics, growth/margin analysis, balance sheet, cash conversion, segment/product commentary, risks, and source trail.
- Prompt requires "Not investment advice" disclaimer.
- Tests use a fake LLM callback and assert prompt inputs include evidence references.

#### F7 — HTML + Markdown Filing Report Generator
**Size:** M | **Priority:** High | **Status:** 🔜 READY

**What to build:**
```python
def render_filing_report(analysis: dict, output_format: str = "html") -> Path:
    """
    Render reports/filings/{SYMBOL}_{PERIOD}_financial_analysis.html|md
    Sections:
      Executive Summary, Financial Snapshot, Growth & Margins,
      Balance Sheet, Cash Flow, Segment/Product Review,
      Risks & Watch Items, Extracted Tables, Source Evidence, Disclaimer.
    """
```

**Files to create/modify:**
- `financial_filing_agent.py`
- `tests/test_financial_filing_report.py`
- `reports/filings/` generated at runtime only

**Acceptance criteria:**
- HTML report is self-contained and readable offline.
- Markdown report is generated for versioned research notes.
- Every material metric links back to page/table/fact evidence.

#### F8 — Terminal / Agent Adda Integration
**Size:** M | **Priority:** Medium | **Status:** 🔜 READY

**What to build:**
- Add commands:
  - `/filing <symbol>` — discover latest filings.
  - `/filing analyze <url>` — direct-link analysis.
  - `/filing analyze <symbol> <quarter>` — discover + analyze.
- Add NLP route:
  - "analyze latest quarterly report for Blue Star"
  - "read this financial result PDF"
  - "summarize Q4 results with balance sheet and cash flow"

**Files to create/modify:**
- `nse_agent.py`
- `terminal/tools.py`
- `terminal/agent.py`
- `tests/test_terminal_filing_agent.py`

**Acceptance criteria:**
- User-provided PDF link can produce report path from terminal.
- Symbol-driven route uses discovery first and falls back to asking for link.
- Chat response distinguishes extracted facts from LLM interpretation.

#### F9 — Batch Earnings Intelligence
**Size:** XL | **Priority:** Medium | **Status:** 💤 DEFERRED

**What to build:**
- Run filing analysis for watchlist, portfolio holdings, Stage 2 stocks, or Nifty 500 result calendar.
- Produce ranked earnings-quality dashboard:
  - earnings acceleration
  - margin expansion
  - cash conversion
  - debt stress
  - segment momentum
  - management tone

**Files to create/modify:**
- `financial_filing_agent.py`
- `reports/filings/earnings_quality_dashboard.html`
- `tests/test_financial_filing_batch.py`

**Acceptance criteria:**
- Batch mode can skip companies with missing filings and continue.
- Dashboard highlights best/worst filings with source trails.
- Results can feed sector rotation candidate narratives later.

### Phase 4 — Branch G: US / Global Market Intelligence

#### G8 — Intraday US Extension
**Size:** L | **Priority:** Medium | **Status:** 💤 DEFERRED

**What to build later:**
- US intraday OHLCV, intraday screeners, and live terminal views.

**Deferred until:**
- Daily US/global layer is stable and useful.

---

## 7. TECHNICAL DEBT & CLEANUP

| Item | File(s) | Action |
|---|---|---|
| 10 empty R stub files | `config.R`, `main.R`, `*demo.R` etc | Delete |
| `_sector_rotation_fund_tmp.csv` left after cache merge | `data/` | Delete in `_load_fundamental_details()` after successful cache update |
| Duplicate report output files (645+) | `reports/` | Archive anything older than 30 days to `reports/archive/` |
| `nse_analysis.db` schema undocumented | `nse_analysis.db` | Add schema doc to `docs/` |
| Portfolio analyzer phase 1 missing | `portfolio-analyzer/` | `phase1_pnl.py` not in pipeline |
| `.env` has both Anthropic and OpenAI keys; Anthropic unused | `.env` | Remove `ANTHROPIC_API_KEY` from active code |
| `README.md` is empty | `README.md` | Write 2-page project README |

---

## 8. IMPLEMENTATION ROADMAP

```
SPRINT 1 (DONE — 2026-05-02): Foundations
  ✅ P0-1  Signal Performance Logger
  ✅ P0-2  A+ Setup Classification
  ✅ P0-3  Formal Entry/Stop/Target Levels
  ✅ P0-4  Consolidate Data Sources
  ✅ P1-1  Market Regime Detector
  ✅ P1-2  F&O OI + PCR Signals
  ✅ P1-3  FII/DII Flow Signals

SPRINT 2 (READY): Signal Enrichment
  J1    Data Readiness Service           [S] — terminal/data_readiness.py
  J2    Refresh Planner + Executor       [S] — bounded daily_refresh.py invocation
  J3    Startup Terminal Integration     [M] — nse_agent.py readiness panel
  J4    Agent Metadata + Guardrails       [M] — no assumed DB fields in answers
  J5    /data-status + /refresh-data      [S] — deterministic terminal commands
  J6    Data Readiness Regression Tests   [S] — stale/missing/partial coverage fixtures
  J7    /load Command Catalog             [M] — verified Python/R script mappings
  J8    /load Terminal Orchestrator        [M] — async runner, logs, status, stop
  J9    Source-Specific /load Jobs         [M] — NSE, aux, global, views, reports
  J10   Fundamental + Score Loading        [M] — Screener R loaders + score rebuild
  J11   Company KB Loading Adapter         [M] — stale and symbol-specific indexing
  J12   Load-Aware Agent Guardrails        [S] — voice/readiness/no-assumption impact
  K1    Backtesting Data Contract          [M] — EOD readiness + required fields
  K2    Strategy Registry                  [M] — Stage2, CANSLIM, Minervini, Supertrend, RSI pullback
  K3    Vectorized EOD Backtest Engine     [L] — deterministic entries/exits/P&L
  K4    Portfolio Simulator                [M] — capital, sizing, caps, drawdown
  K5    Metrics + Attribution              [M] — CAGR, DD, expectancy, sector/regime
  K6    Backtest SQLite Store              [M] — runs, trades, equity, metrics
  K7    Backtest Reports                   [M] — Markdown/HTML/latest
  K8    Terminal Backtest Commands         [M] — /backtest and /strategy-lab
  K9    Existing Script Adapters           [S] — optional R/Python legacy adapters
  K10   Golden Backtest Regression Suite   [M] — fixtures + no-lookahead tests
  K11   Technical Pattern Feature Library  [M] — pivots, compression, Supertrend, RSI
  K12   VCP/Darvas/Squeeze Strategy Pack   [M] — confidence-scored compression setups
  K13   Chart Pattern Strategy Pack        [L] — H&S, inverse H&S, cup/handle, triangles
  K14   Exit Strategy Lab                  [M] — compare Supertrend/ATR/SMA/stage exits
  K15   Pattern QA + Visual Evidence       [M] — synthetic fixtures + chart snapshots
  P1-4  Promoter/Insider Alerts           [M] — fetch_insider_alerts.py
  P1-5  Enhanced HTML Dashboard           [M] — sortable cols, heatmap
  P2-4  Portfolio-Aware Narratives        [L] — personalized entry/trim guidance

SPRINT 3: Market Intelligence Layer
  B1    Cross-Index Breadth Dashboard     [M] — index_intelligence.py
  B2    Global Correlation Monitor        [M] — yfinance integration
  B3    Sectoral Heat Calendar            [M] — seasonal alpha identification
  C1    McClellan Oscillator              [M] — market_breadth.py
  C2    TRIN / Arms Index                 [S]
  C3    Sector Breadth Divergence         [M]
  E4    Event-Driven Alert Engine         [M] — highest ROI in Branch E

SPRINT 4: Advanced Screeners
  A1    Stage Analysis Screener           [M] — screeners.py
  A2    Darvas Box Breakout               [M]
  A3    52W High Momentum                 [S]
  A6    Turnaround Detector               [S]
  P2-2  Counterfactual Scenarios          [L]

SPRINT 5: Deep Fundamentals (requires Screener.in 5yr scrape prerequisite)
  Prereq: extend fetch_screener_fundamental_details.R for 5-yr P&L + CFO + ROCE
  D5    Forensic Accounting Suite         [L] — deep_fundamentals.py (Beneish + Piotroski + Altman)
  D2    Earnings Quality Score            [M] — CCR, accruals, FCF yield
  D1    DuPont Decomposition              [M] — ROE driver analysis
  A4    Earnings Acceleration             [M] — quarterly EPS series required
  A7    Quality Compounder                [M] — 5yr CAGR screening
  P1-6  Macro-Economic Proxy Signals      [L] — GST, PMI, IIP, power data

SPRINT 6: Deep Fundamentals (cont) + Company Intelligence
  D6    Competitive Moat Score            [L] — pricing power, switching costs
  E2    Peer Comparison Engine            [M] — screener.in peers scrape
  E3    Management Quality Score          [M] — promoter + insider + concall
  P2-5  Concall Sentiment NLP (= D4)      [L] — BSE filings + LLM extraction
  A5    Institutional Accumulation        [M] — up/down volume ratio
  A8    Hidden Champions                  [M] — niche leaders, low coverage

SPRINT 7: Synthesis + Flow Intelligence
  E1    360° Company Dashboard            [XL] — ties together all of D + E
  B4    FII/DII Flow Battle Tracker       [M] — needs P1-3 data
  B5    Economic Cycle Tracker            [L] — needs P1-6 macro data
  D3    Business Cycle Positioning        [S] — extends B5 to stock level
  C4    Smart Money Flow Index            [M]
  P2-1  NSE Knowledge Graph              [XL]

SPRINT 8: Learning + Futuristic
  P2-3  Learning Loop                    [L] — 90 days signal data accumulated by now
  P3-2  Voice Briefing                   [M] — GPT TTS via gpt-4o-mini-tts
  P3-1  Causal Inference Model           [XL] — 6+ months signal data required
  P3-3  Real-Time Mode                   [XL]
```

---

## 9. KEY DESIGN PRINCIPLES FOR CODING ASSISTANTS

1. **Never break existing pipelines.** `sector_rotation_report.py` runs end-to-end today — all additions are additive (new columns, new files, new functions). The existing flow must still work if a new module fails.

2. **All new data files go into `data/` folder.** Prefix with underscore if intermediate: `data/_fno_signals.csv`. Final outputs in `reports/`.

3. **NSE data access pattern:**  
   - Historical OHLCV: read from `data/nse_sec_full_data.csv` (already local)
   - External APIs (NSE, BSE): always use `curl` subprocess or `requests` with NSE headers; do NOT use `requests` directly on macOS without timeout + retry (known hang issue)
   - Rate limiting: 2-second sleep between NSE API calls

4. **All new external fetches must have a local cache with TTL.**  
   Pattern: check cache file age → if older than 24h, re-fetch → save → use.

5. **F&O and FII data is date-specific.** When data for today is not yet available (pre-market), use the previous trading day's data.

6. **LLM calls use `_llm_call()` in `sector_rotation_report.py`.** Do not add new `requests.post()` calls. Use the existing curl-subprocess helper.

7. **Python environment:** `.venv/` at project root. Activate with `source .venv/bin/activate`. R uses system R (Rscript must be in PATH).

8. **Regime detector is a gate, not a filter.** It never blocks signals; it re-weights them. A BEAR regime does not produce zero candidates — it produces candidates with lower scores and narrower setup classes.
