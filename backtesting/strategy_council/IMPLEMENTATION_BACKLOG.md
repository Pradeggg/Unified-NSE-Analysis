# Strategy Council Implementation Backlog

**Purpose:** Canonical actionable backlog of Strategy Council enhancements that are **not yet fully implemented**.
**Source:** `ENHANCEMENT_ROADMAP.md`, reconciled against the current tree on 2026-05-19.
**Guardrail:** All items remain research-only and must preserve point-in-time evidence, source trails, and missing-evidence disclosure.

---

## Already Implemented or Partially Implemented

These items should not be duplicated:

| Capability | Status | Current Files |
|---|---|---|
| Basic council contracts/orchestration | Implemented | `types.py`, `council.py` |
| Point-in-time EOD evidence pack | Implemented | `evidence.py` |
| Regime/factor/microstructure enrichment | Implemented, expandable | `evidence_enrichment.py` |
| Rule composition and composite strategist | Implemented | `strategy_generator.py`, `rule_composed_engine.py`, `runner.py` |
| Data leakage and base risk critics | Implemented | `llm.py` |
| Drawdown/correlation/factor/regime critics | Implemented | `critics_advanced.py` |
| Markdown report | Implemented | `report.py` |
| Basic HTML dashboard | Implemented, expandable | `dashboard_generator.py` |
| PostgreSQL persistence | Implemented | `postgres_storage.py` |
| Latest-results feed and forthcoming-results feed | Implemented in Agent tooling, not fully consumed by Council evidence | `terminal/tools.py`, `terminal/agent.py` |
| Latest-results / filing tool foundations | Partially implemented, not fully consumed by Council evidence | `terminal/results_tools.py`, `backtesting/strategy_council/evidence_filings.py`, `tool_router.py` |
| Company evidence and F&O composite tool foundations | Partially implemented, not fully consumed by Council evidence | `terminal/company_evidence_tools.py`, `terminal/fno_composite.py` |

---

## P0 — Evidence Completeness, Safety, and Recommendation Gating

### SC-GATE1 Validation-Based Recommendation Gate

- **Status:** Ready
- **Priority:** P0
- **Files:** `backtesting/strategy_council/council.py`, `backtesting/strategy_council/llm.py`, `backtesting/strategy_council/report.py`, tests
- **Build:** Add a hard policy over validation returns, validation trade count, blocking critic verdicts, and one-shot test results. A positive one-shot test must not override negative/empty validation by itself.
- **Acceptance:** Recent report patterns such as negative validation with positive test are labeled `WAIT` or `RESEARCH_ANOMALY`; `TRADE_RESEARCH` requires positive validation, enough validation trades, and no blocking critic verdicts.

### SC-GATE2 Source-Backed Strategy Claim Gate

- **Status:** Ready
- **Priority:** P0
- **Files:** `backtesting/strategy_council/council.py`, `report.py`, `dashboard_generator.py`, tests
- **Build:** Require every recommendation rationale clause to map to evidence fields or critic/test outputs. Unsupported mentions of fundamentals, sentiment, F&O, filings, catalysts, or intraday context are omitted or labeled unavailable.
- **Acceptance:** Reports cannot mention sentiment, filing facts, F&O, event risk, or intraday alignment unless those evidence sections are present with source trails.

### SC-E1 Multi-Timeframe Evidence Pack

- **Status:** Partially implemented
- **Priority:** P0
- **Files:** `backtesting/strategy_council/evidence_enrichment.py`, `terminal/intraday_storage.py`, tests
- **Build:** Add daily, weekly, and intraday evidence fields: trend alignment, timeframe conflict, latest intraday direction, and freshness. Report rendering has an intraday evidence section; remaining work is to populate it consistently from the evidence pack and enforce freshness/missing-data policy.
- **Acceptance:** A Strategy Council report can state whether daily/weekly/intraday evidence agrees, conflicts, or is unavailable. Missing intraday data is labeled, not inferred.

### SC-E2 Latest Results and Event Evidence

- **Status:** Partially implemented
- **Priority:** P0
- **Files:** `backtesting/strategy_council/evidence.py`, `backtesting/strategy_council/evidence_filings.py`, `backtesting/strategy_council/tool_router.py`, `terminal/results_tools.py`, `terminal/tools.py`, tests
- **Build:** Add latest-results pack, forthcoming-results date, corporate action window, filing summary, and event-risk flag into `EvidencePack`. Foundations exist in terminal/results and filing summary helpers; remaining work is first-class Council integration and missing-data reconciliation.
- **Acceptance:** For symbols with recent/forthcoming results, reports include the filing/event source trail. Missing results no longer appear as missing when the tool has evidence.

### SC-E3 Source-Gated News Sentiment

- **Status:** Partially implemented
- **Priority:** P0
- **Files:** `backtesting/strategy_council/evidence_enrichment.py`, `terminal/company_evidence_tools.py`, tests
- **Build:** Extract company/news sentiment as `sentiment_score`, `impact_score`, `source_count`, `top_events`, and `freshness`. Company evidence tool foundations exist; remaining work is Council-specific source gating and report/dashboard rendering.
- **Acceptance:** Council output may mention sentiment only when source-backed sentiment evidence is present.

### SC-E4 F&O Evidence Contract

- **Status:** Partially implemented
- **Priority:** P0
- **Files:** `backtesting/strategy_council/evidence_enrichment.py`, `terminal/fno_composite.py`, tests
- **Build:** Add option-chain summary, PCR, max pain, top OI strikes, futures basis, and cost of carry when symbol/index supports F&O. Composite F&O tooling exists; remaining work is Council integration and recommendation gating.
- **Acceptance:** F&O-derived strategy comments are blocked unless F&O evidence was fetched and included.

### SC-E5 Liquidity and Tradability Evidence

- **Status:** Ready
- **Priority:** P0
- **Files:** `backtesting/strategy_council/evidence_enrichment.py`, tests
- **Build:** Add turnover, average traded value, volume percentile, spread proxy, and liquidity bucket.
- **Acceptance:** Low-liquidity symbols are flagged before strategy selection.

---

## P1 — Critic Expansion

### SC-C1 Liquidity Critic

- **Status:** Ready
- **Priority:** P1
- **Files:** `backtesting/strategy_council/critics_advanced.py`, tests
- **Build:** Compare proposed exposure against average traded value and volume percentile.
- **Acceptance:** Candidate receives revise/reject when implied position exceeds configurable liquidity limits.

### SC-C2 Execution Cost Critic

- **Status:** Ready
- **Priority:** P1
- **Files:** `backtesting/strategy_council/critics_advanced.py`, tests
- **Build:** Estimate brokerage/slippage/STT/taxes and compare average trade edge against cost.
- **Acceptance:** Strategies with average edge below `2x` estimated cost are revised or rejected.

### SC-C3 Volatility Regime Critic

- **Status:** Ready
- **Priority:** P1
- **Files:** `backtesting/strategy_council/critics_advanced.py`, tests
- **Build:** Bucket validation periods by ATR/VIX/realized volatility and compare performance by bucket.
- **Acceptance:** Strategy is flagged when it works only in a narrow volatility regime.

### SC-C4 Calendar and Event Critic

- **Status:** Ready
- **Priority:** P1
- **Files:** `backtesting/strategy_council/critics_advanced.py`, tests
- **Build:** Detect result-day, expiry-week, holiday, corporate-action, and macro-event sensitivity.
- **Acceptance:** Event-sensitive strategies must add event filters or risk reductions.

### SC-C5 Stress Test Critic

- **Status:** Ready
- **Priority:** P1
- **Files:** `backtesting/strategy_council/critics_advanced.py`, tests
- **Build:** Run or score candidates across known stress windows where data exists.
- **Acceptance:** Reports include stress-window pass/fail with reasons.

### SC-C6 Walk-Forward Critic

- **Status:** Ready
- **Priority:** P1
- **Files:** `backtesting/strategy_council/critics_advanced.py`, `runner.py`, tests
- **Build:** Run rolling train/validation windows and detect performance decay.
- **Acceptance:** Candidate is flagged if recent rolling windows degrade materially from early windows.

### SC-C7 Redundancy / Causality Critic

- **Status:** Ready
- **Priority:** P2
- **Files:** `backtesting/strategy_council/critics_advanced.py`, `strategy_generator.py`, tests
- **Build:** Flag highly correlated/redundant rule atoms in a candidate spec.
- **Acceptance:** Candidate using multiple near-duplicate momentum rules receives a revise verdict.

---

## P1 — Dashboard and Reporting

### SC-D1 Performance Attribution Dashboard

- **Status:** Ready
- **Priority:** P1
- **Files:** `backtesting/strategy_council/dashboard_generator.py`, `report.py`, tests
- **Build:** Add rule-level attribution: trades, hit rate, average return, P&L, drawdown contribution.
- **Acceptance:** Dashboard shows which rules contributed to performance.

### SC-D2 Rule Correlation Heatmap

- **Status:** Ready
- **Priority:** P1
- **Files:** `dashboard_generator.py`, `rule_composed_engine.py`, tests
- **Build:** Compute rule activation correlations and render a heatmap/table.
- **Acceptance:** Dashboard identifies redundant rules visually.

### SC-D3 Walk-Forward Visualization

- **Status:** Ready
- **Priority:** P1
- **Files:** `dashboard_generator.py`, `critics_advanced.py`, tests
- **Build:** Add rolling return, rolling Sharpe, drawdown, and trade-count charts.
- **Acceptance:** Dashboard shows whether strategy performance degrades over time.

### SC-D4 Strategy Comparison Dashboard

- **Status:** Ready
- **Priority:** P1
- **Files:** `dashboard_generator.py`, new comparison helper, tests
- **Build:** Compare candidates or saved council runs side-by-side.
- **Acceptance:** User can compare return, drawdown, trade count, hit rate, and critic verdicts for at least two strategies.

### SC-D5 Export to Excel/PDF

- **Status:** Ready
- **Priority:** P2
- **Files:** `dashboard_generator.py`, report export helpers, tests
- **Build:** Export evidence, metrics, trades, critiques, and dashboard summary to `.xlsx` and/or `.pdf`.
- **Acceptance:** Exported files are created with deterministic names and source metadata.

### SC-D6 Monte Carlo Outcome View

- **Status:** Ready
- **Priority:** P2
- **Files:** `dashboard_generator.py`, new simulation helper, tests
- **Build:** Bootstrap trade returns and show confidence intervals.
- **Acceptance:** Dashboard includes distribution bands and probability of loss.

---

## P2 — Strategy Generation Intelligence

### SC-G1 Rule Interaction Graph

- **Status:** Ready
- **Priority:** P2
- **Files:** `strategy_generator.py`, `postgres_storage.py`, tests
- **Build:** Mine historical council runs to learn rule combinations that perform well together.
- **Acceptance:** Candidate generation can bias toward historically synergistic rule pairs.

### SC-G2 Rule Feature Importance Ranking

- **Status:** Ready
- **Priority:** P2
- **Files:** `strategy_generator.py`, analysis helper, tests
- **Build:** Rank entry/exit/risk atoms by contribution to returns, drawdown, and stability.
- **Acceptance:** Strategy generation report includes top/bottom rule atoms.

### SC-G3 Constraint Satisfaction Generator

- **Status:** Ready
- **Priority:** P2
- **Files:** `strategy_generator.py`, tests
- **Build:** Generate candidates under explicit constraints such as trend + volume + risk-control requirements.
- **Acceptance:** Generated candidates always satisfy declared constraints.

### SC-G4 Genetic Rule Optimizer

- **Status:** Deferred
- **Priority:** P3
- **Files:** new `optimizer.py`, `strategy_generator.py`, tests
- **Build:** Evolve rule combinations using validation score as fitness.
- **Acceptance:** Optimizer produces reproducible candidate sets and never touches test data during optimization.

### SC-G5 Meta-Strategy Ensemble

- **Status:** Ready
- **Priority:** P2
- **Files:** `strategy_generator.py`, `runner.py`, tests
- **Build:** Combine strategies through voting, score weighting, or confirmation thresholds.
- **Acceptance:** Ensemble specs are executable and separately audited.

---

## P2 — Analysis and Robustness

### SC-A1 Sensitivity Analysis

- **Status:** Ready
- **Priority:** P2
- **Files:** new `sensitivity.py`, `dashboard_generator.py`, tests
- **Build:** Perturb parameters and measure outcome stability.
- **Acceptance:** Report lists robust and fragile parameters.

### SC-A2 Drawdown Attribution

- **Status:** Ready
- **Priority:** P2
- **Files:** new `attribution.py`, dashboard/report tests
- **Build:** Identify trades/regimes/rules responsible for maximum drawdown.
- **Acceptance:** Dashboard and Markdown report show top drawdown contributors.

### SC-A3 Transaction Cost Analysis

- **Status:** Ready
- **Priority:** P2
- **Files:** new `costs.py`, `runner.py`, tests
- **Build:** Add detailed cost estimates per trade and aggregate cost drag.
- **Acceptance:** Strategy metrics can be shown gross and net of costs.

### SC-A4 Macro Factor Exposure

- **Status:** Ready
- **Priority:** P2
- **Files:** `evidence_enrichment.py`, new factor helper, tests
- **Build:** Regress strategy returns against market, VIX, crude, USDINR, and sector benchmark where data exists.
- **Acceptance:** Factor exposures are included only when sufficient aligned history exists.

---

## P3 — Scale and Operations

### SC-S1 Parallel Backtesting

- **Status:** Deferred
- **Priority:** P3
- **Files:** new `parallel_runner.py`, tests
- **Build:** Run candidate backtests concurrently with deterministic ordering.
- **Acceptance:** Results match serial runner and reduce runtime for large candidate sets.

### SC-S2 Backtesting Result Cache

- **Status:** Ready
- **Priority:** P2
- **Files:** `postgres_storage.py`, `runner.py`, tests
- **Build:** Cache results by symbol, strategy spec hash, date window, and data fingerprint.
- **Acceptance:** Repeated identical runs reuse cache and report cache-hit status.

### SC-S3 Multi-Symbol Council Orchestration

- **Status:** Ready
- **Priority:** P2
- **Files:** new `multi_symbol.py`, `terminal/strategy_council.py`, tests
- **Build:** Run council across a universe and coordinate ranking, risk limits, and report generation.
- **Acceptance:** User can run a bounded multi-symbol council with deterministic output and per-symbol missing-data disclosures.

### SC-S4 Research-Only Live Signal Preview

- **Status:** Deferred
- **Priority:** P3
- **Files:** new `live_signals.py`, terminal wiring, tests
- **Build:** Run locked strategy specs on current data and show hypothetical signals.
- **Acceptance:** Output is explicitly research-only and never submits orders.

### SC-S5 Compliance and Audit Trail

- **Status:** Ready
- **Priority:** P2
- **Files:** `postgres_storage.py`, reports, tests
- **Build:** Persist evidence hash, strategy spec hash, source trail, critic verdicts, user-visible rationale, and generated report paths.
- **Acceptance:** Every report can be traced back to immutable input/evidence metadata.

---

## Recommended Next Sprint

1. **SC-GATE1 Validation-Based Recommendation Gate**
2. **SC-GATE2 Source-Backed Strategy Claim Gate**
3. **SC-E2 Latest Results and Event Evidence**
4. **SC-C2 Execution Cost Critic**
5. **SC-D3 Walk-Forward Visualization**

These address the highest current risk: reports can show negative/empty validation but positive one-shot tests, and evidence foundations can exist without being consistently consumed by Council recommendations.
