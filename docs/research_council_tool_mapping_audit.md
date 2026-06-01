# Research Council Tool Mapping Audit

Date: 2026-05-26
Scope: RC-0.3 audit for `docs/RESEARCH_COUNCIL_IMPLEMENTATION_ARTIFACT.md`
Status: initial mapping complete; adapters required before registry implementation

## Purpose

The implementation artifact defines logical Research Council tool names such as `screen.stage2`, `fno.buildup`, and `backtest.run`. Several artifact targets point to functions that do not currently exist under those exact module paths. This audit records the safe implementation path: use existing callables where they exist, write thin adapters where the logical tool is useful but the exact target is absent, and defer tools that require new data/model work.

Future agents should implement `terminal/research_council/tool_registry.py` from this audit, not directly from speculative artifact imports.

## Mapping Table

| logical_tool | artifact_target | actual_callable | adapter_needed | status | notes |
|---|---|---|---|---|---|
| `regime.detect` | `regime_detector.detect_current_regime` | `terminal.tools.get_index_snapshot`, `terminal.tools.get_market_breadth`, `terminal.tools.get_economic_cycle_assessment`, `signals.regime_history` SQL | yes | READY | No standalone `regime_detector.py` found. Adapter should summarize latest regime/breadth/economic-cycle evidence. |
| `breadth.summarize` | `market_breadth.summarize_breadth` | `terminal.tools.get_market_breadth`, `breadth.market_daily` SQL | yes | READY | Use existing tool or direct SQL summary for windows. |
| `flows.fii_dii_5d` | `postgres.loader.get_fii_dii_5d` | `terminal.tools.get_fii_dii_activity`, `fetch_fii_dii_flows.compute_flow_signals`, `signals.fii_dii_flows` SQL | yes | READY | Adapter should return latest and rolling 5-day values. |
| `global.correlation_30d` | `global_correlation.compute_correlations` | `terminal.tools.get_global_market_assessment`, `macro.global_correlations` SQL | yes | PARTIAL | Use cached/global assessment first; exact 30D correlation may require direct SQL. |
| `macro.proxy_signals` | `fetch_macro_proxies.compute_proxy_signals` | `fetch_macro_proxies.compute_indicator_signals`, `fetch_macro_proxies.generate_macro_signals` | yes | READY | Artifact function name differs. |
| `sector.rotation_report` | `sector_rotation_report.compute_rotation` | `sector_rotation_report.generate_report`, latest `reports/latest/sector_rotation.*`, `scores.stage_snapshots` SQL | yes | READY | Avoid regenerating full report inside every council step; adapter should read current report/PG summary where possible. |
| `sector.rs_ranking` | `sector_rotation_tracker.rank_sectors_by_rs` | `sector_rotation_report.build_index_metrics`, `scores.index_strength` SQL, `breadth.sector_daily` SQL | yes | READY | No exact callable found. |
| `sector.breadth_health` | `market_breadth.sector_breadth` | `breadth.sector_daily` SQL, `data/sector_breadth.csv` | yes | READY | Adapter should return sector-level breadth/stage density. |
| `sector.top_stocks` | `postgres.loader.get_sector_top_stocks` | `scores.sector_top_stocks` SQL, `terminal.tools.get_sector_context` | yes | READY | Direct SQL likely cleaner than terminal narrative tool. |
| `screen.stage2` | `postgres.loader.run_stage2_screen` | `terminal.tools.run_screener_query(screen_type="stage2")`, `scores.daily_scores` SQL | yes | READY | Adapter should call existing screener or query scores. |
| `screen.breakouts` | `postgres.loader.run_breakouts_screen` | `terminal.tools.run_screener_query(screen_type=...)` | yes | NEEDS_SCREEN_NAME | Need confirm exact `screen_type` accepted for breakouts. |
| `screen.supertrend_buy` | `postgres.loader.run_supertrend_buy_screen` | `terminal.tools.run_screener_query(screen_type=...)`, `scores.daily_scores` SQL | yes | NEEDS_SCREEN_NAME | Need confirm current screener name. |
| `screen.momentum_52w` | `postgres.loader.run_momentum_52w_screen` | `terminal.tools.run_screener_query(screen_type=...)`, `market.week52_extremes`, `scores.daily_scores` SQL | yes | READY | Can query 52W proximity directly if no named screener. |
| `screen.high_rs` | `postgres.loader.run_high_rs_screen` | `terminal.tools.run_screener_query(screen_type=...)`, `scores.daily_scores.relative_strength` SQL | yes | READY | Direct SQL can support first version. |
| `screen.vcp_tightness` | `postgres.loader.run_vcp_tightness_screen` | no exact callable found | yes | PARTIAL | Implement later from EOD volatility contraction features or mark missing in MVP. |
| `screen.pullback_recovery` | `pullback_recovery_screener.run_screen` | no exact callable found | yes | DEFERRED | Not required for MVP. |
| `fno.buildup` | `fetch_fno_data.compute_buildup` | `fetch_fno_data.compute_oi_change`, `fetch_fno_data.compute_fno_composite_signal`, `terminal.tools.get_fno_analytics`, `derivatives.fno_signals` SQL | yes | READY | Artifact function does not exist. Adapter should use current F&O analytics/signals. |
| `fno.pcr_history` | `postgres.loader.get_pcr_history` | `fetch_fno_data.compute_pcr`, `terminal.tools.get_fno_analytics`, `derivatives.fno_eod` SQL | yes | READY | Historical PCR can be derived from FO EOD. |
| `fno.option_chain_support_resistance` | `fetch_fno_data.option_chain_sr` | `terminal.tools.get_options_chain`, `terminal.tools.get_oi_analysis` | yes | READY | Requires PostgreSQL EOD options data or live source; must return missing evidence if absent. |
| `fno.max_pain` | `fetch_fno_data.compute_max_pain` | `fetch_fno_data.compute_max_pain`, `terminal.tools.get_fno_analytics` | yes | READY | Existing function expects FO dataframe; adapter should load data first. |
| `fno.iv_percentile` | `fetch_fno_data.iv_percentile` | no exact callable found | yes | DEFERRED | Defer unless IV history exists in derivatives tables. |
| `fund.quality_classify` | `scripts.refresh_results_feed.classify_quality` | `terminal.recommendation_report.build_recommendations`, `scores.fundamental_scores` SQL, `scores.fundamental_snapshots` SQL | yes | READY | No exact classifier found; deterministic agent can classify from fields. |
| `fund.peer_compare` | `postgres.loader.peer_compare` | `terminal.tools.scrape_screener_in` if available in tool registry, `terminal.tools.get_sector_context`, Screener cache tables | yes | PARTIAL | Need verify exposed `scrape_screener_in` wrapper; peer table may require web/cache. |
| `fund.results_trend` | `postgres.loader.results_trend` | `terminal.tools.get_latest_results_feed`, `scores.quarterly_results`, `scores.annual_results` SQL | yes | READY | Direct SQL preferred for candidate symbols. |
| `fund.balance_sheet_health` | `postgres.loader.bs_health` | `scores.balance_sheet`, `scores.cash_flow`, `scores.fundamental_scores` SQL | yes | READY | Adapter should classify leverage/cash-flow health. |
| `events.upcoming` | `fetch_corporate_events.upcoming_for_symbols` | `terminal.tools.get_upcoming_events`, `terminal.tools.get_forthcoming_results`, `signals.corporate_events` SQL | yes | READY | Existing source supports upcoming events. |
| `events.recent_results` | `postgres.loader.recent_results` | `terminal.tools.get_latest_results_feed`, `scores.quarterly_results` SQL | yes | READY | Direct SQL for symbol subset. |
| `events.insider_filter` | `fetch_insider_alerts.insider_for_symbols` | `fetch_insider_alerts.generate_insider_alerts`, `terminal.tools.get_bulk_block_deals`, `signals.insider_alerts` SQL | yes | READY | Existing function name differs. |
| `events.bulk_block` | `fetch_insider_alerts.bulk_block_for_symbols` | `fetch_insider_alerts.fetch_bulk_deals`, `fetch_insider_alerts.fetch_block_deals`, `signals.bulk_block_deals` SQL | yes | READY | Adapter can filter by symbols. |
| `backtest.run` | `backtesting.engine.run_strategy` | `backtesting.strategy_council.runner.run_strategy_spec_on_split`, `backtesting.strategy_council.council.run_strategy_council` | yes | READY | Use Strategy Council DSL/spec runner, not nonexistent `backtesting.engine.run_strategy`. |
| `backtest.regime_conditional` | `backtesting.engine.regime_conditional_metrics` | `backtesting.strategy_council.critics_advanced.RegimeConditionalCritic`, custom adapter over backtest trades | yes | PARTIAL | Use existing critic if available; may need adapter once strategy result shape is known. |
| `decision_math.compute_atr_stop` | `terminal.research_council.decision_math.atr_stop` | new `terminal.research_council.decision_math` | yes | READY_AFTER_RC_5.1 | New module planned. |
| `decision_math.compute_targets` | `terminal.research_council.decision_math.compute_targets` | new `terminal.research_council.decision_math` | yes | READY_AFTER_RC_5.1 | New module planned. |
| `intraday.scan_signals` | `postgres.loader.get_scan_signals` | `terminal.tools.run_intraday_screener` | yes | READY | Use existing intraday scanner. |
| `intraday.vwap_reclaim` | `postgres.loader.get_vwap_reclaim_signals` | `terminal.tools.run_intraday_screener(pattern="vwap_reclaim" or equivalent)` | yes | NEEDS_ARG_AUDIT | Need inspect accepted scanner pattern names before wiring. |

## Public Research Council Tool Surface

These tools do not exist yet and should be implemented as wrappers after the core package exists:

| public_tool | implementation target | status |
|---|---|---|
| `build_research_evidence_pack` | `terminal.research_council.evidence_pack_builder.build_research_evidence_pack` | planned |
| `run_research_council` | `terminal.research_council.engine.run_council` | planned |
| `run_data_steward_check` | `terminal.research_council.states.data_steward.run_check` | planned |
| `compose_plan` | `terminal.research_council.states.plan_build` | planned |
| `execute_plan` | `terminal.research_council.plan_executor.PlanExecutor` | planned |
| `review_plan_execution` | `terminal.research_council.states.plan_review` | planned |
| `run_critic_review` | `terminal.research_council.states.critic_review` | planned |
| `apply_revision_round` | `terminal.research_council.states.revision` | planned |
| `synthesize_council_decision` | `terminal.research_council.states.synthesis` | planned |
| `render_research_council_report` | `terminal.research_council.reports.markdown_renderer` / `html_renderer` | planned |
| `persist_research_council_run` | `terminal.research_council.persistence` | planned |
| `resume_council_run` | `terminal.research_council.persistence` + engine resume helper | planned |

## MVP Registry Recommendation

For the first `/council today --horizon swing --risk moderate` MVP, register only this subset:

- `regime.detect`
- `breadth.summarize`
- `flows.fii_dii_5d`
- `macro.proxy_signals`
- `sector.rs_ranking`
- `sector.breadth_health`
- `sector.top_stocks`
- `screen.stage2`
- `screen.high_rs`
- `screen.momentum_52w`
- `fund.results_trend`
- `fund.balance_sheet_health`
- `events.upcoming`
- `fno.buildup`

Defer intraday, option-chain support/resistance, IV percentile, VCP tightness, pullback recovery, and strategy-build tools until the deterministic Market Council MVP is stable.
