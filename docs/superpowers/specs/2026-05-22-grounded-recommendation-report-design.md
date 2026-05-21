# Grounded Recommendation Report Design

Date: 2026-05-22
Scope: EOD market-wide plus portfolio/watchlist recommendation report

## Goal

Create a first-class daily recommendation report that combines today’s EOD data for indices, sectors, stocks, portfolio/watchlist names, multi-timeframe technical analysis, and fundamental overlays.

The report is for research and learning only. It must not make unsupported buy/sell calls. Every recommendation label must be grounded in explicit evidence, data freshness, and source trail.

## Approved Direction

Use an **Evidence Pack + Scoring + Report** architecture.

The report generator first builds a structured evidence pack, then applies deterministic scoring and recommendation policy, then renders HTML/Markdown/PDF. The evidence pack is the source of truth for all narrative and action labels.

Approved output style:

- Market-wide regime first.
- Sector rotation and breadth second.
- Stock opportunity map third.
- Portfolio/watchlist action section fourth.
- Grounding and audit trail at the end.

Approved command shape:

- `/report recommendation`
- `/report recommendation md`
- `/report recommendation pdf`
- `/report recommendation --portfolio`
- `/report recommendation --watchlist RELIANCE,TCS,MANINDS`
- `/report recommendation --top 25 --format html`

## Alternatives Considered

### A. Evidence Pack + Scoring + Report

Build a new structured report pipeline with auditable input data and deterministic recommendation policy. This is the approved approach because it keeps recommendations grounded, replayable, and testable.

### B. Extend Sector Rotation Report

Add portfolio/action sections into `sector_rotation_report.py`. This is faster, but the existing sector rotation report is already broad and large. Recommendation policy, portfolio actions, and auditability deserve clearer boundaries.

### C. RIC-Style Multi-Step Workflow

Create `/ric daily-recommendation` that runs index, sector, stock, portfolio, and final-verdict steps. This is useful terminal UX, but a persistent report needs a structured evidence pack underneath. It can be added later as a wrapper around this pipeline.

## Data Sources

Primary sources should be local and auditable:

- PostgreSQL `market.index_eod` for index EOD OHLC history.
- PostgreSQL `market.equity_eod` for stock EOD OHLCV history.
- PostgreSQL latest snapshot/materialized score views where available.
- Existing sector rotation data and sector breadth caches.
- Existing fundamentals cache and Screener-derived fields where available.
- Portfolio/watchlist sources already used by the terminal, where available.

Fallback sources:

- Existing CSV snapshots already used by the app.
- Existing generated report artifacts only for report lookup context, not for fresh scoring.

The report must label each source as `primary`, `fallback`, or `missing`.

## Evidence Pack

Create a structured `RecommendationEvidencePack` with these top-level sections:

- `as_of`: latest EOD date and generation time.
- `indices`: one record per approved index.
- `sectors`: sector/index rotation records.
- `stocks`: ranked stock candidate records.
- `portfolio`: holdings/watchlist records when available.
- `market_regime`: derived broad-market state.
- `source_trail`: source names, row counts, freshness, fallback flags.
- `missing_evidence`: explicit missing fields by scope and symbol.

Index evidence fields:

- Close, latest trade date, 1D/1W/1M/3M/6M returns.
- Relative strength versus Nifty 50.
- SMA 20/50/200 and price position against each.
- RSI 14.
- MACD 12/26/9 and histogram direction.
- Supertrend when available.
- Recent support/resistance from swing windows.
- 52-week high/low proximity.
- Trend label: `bullish`, `constructive`, `neutral`, `weak`, or `bearish`.

Sector evidence fields:

- Sector/index return profile across 1D/1W/1M/3M/6M.
- Relative strength versus Nifty 50 and Nifty 500 where available.
- Breadth: advances, declines, Stage 2 count, buy/sell signal count.
- Rotation label: `leader`, `improving`, `neutral`, `weakening`, or `laggard`.
- Top stock contributors when available.

Stock evidence fields:

- Price, latest EOD date, volume ratio, turnover when available.
- Stage, stage score, technical score, RS, investment score.
- RSI, MACD, Supertrend, SMA 20/50/200 alignment.
- 1W/1M/3M/6M returns and RS trend.
- 52-week high/low proximity and drawdown.
- Fundamental overlay: PE, PB, ROE, ROCE, margins, debt/interest coverage, earnings trend, screener pros/cons where available.
- Catalyst overlay when already available from cached/search tools.
- Missing-evidence list.

Portfolio/watchlist evidence fields:

- Symbol, quantity and cost basis if portfolio data is available.
- Current EOD price and unrealized P&L where available.
- Same technical/fundamental fields as stock evidence.
- Existing recommendation state if present.
- New grounded action label.

## Technical Analysis Policy

Technical analysis is a first-class scoring layer, not narrative decoration.

Per index, sector, and stock, compute a multi-timeframe technical profile:

- Daily trend: price versus SMA 20/50/200.
- Momentum: RSI regime and MACD direction.
- Relative strength: 1M and 3M versus benchmark.
- Multi-timeframe return stack: 1W/1M/3M/6M.
- Volume confirmation: latest volume versus 20-day average where available.
- 52-week context: proximity to high and drawdown from high.
- Volatility/contraction context where existing code supports it.

Conflicts must be surfaced explicitly:

- EOD Stage 2 but RSI overheated.
- Strong sector but weak stock RS.
- Strong technicals but weak fundamentals.
- Bullish daily trend but deteriorating short-term momentum.
- Fresh breakout but missing volume confirmation.

No action label may hide conflicts.

## Fundamental Overlay Policy

Fundamentals should modify conviction, not replace technical evidence.

Use available fields from existing fundamentals caches and Screener-derived data:

- ROE, ROCE, PE, PB, dividend yield.
- Sales, operating profit, margin, net profit, EPS trends where available.
- Debt and interest coverage.
- Debtor days and working-capital warnings.
- Screener pros/cons.
- Promoter/FII/DII shareholding where available.

Fundamental classification:

- `quality_supportive`: profitability and balance-sheet evidence supports the technical setup.
- `quality_mixed`: some support, but clear weaknesses exist.
- `quality_weak`: weak profitability, leverage, margin pressure, or missing key data.
- `quality_unknown`: insufficient data.

## Recommendation Policy

Recommendation labels are research actions, not investment advice.

Allowed labels:

- `ADD_ON_CONFIRMATION`
- `HOLD`
- `TRIM_INTO_STRENGTH`
- `AVOID_FRESH_ENTRY`
- `WATCHLIST`
- `REVIEW_MANUALLY`

Each label must include:

- `why`: concise evidence summary.
- `technical_evidence`: exact signals that drove the label.
- `fundamental_evidence`: exact support or warning.
- `trigger`: what evidence would confirm the action.
- `invalidation`: what evidence would negate the action.
- `risk`: key risk or conflict.
- `missing_evidence`: gaps that lower confidence.
- `confidence`: `high`, `medium`, or `low`.

Policy examples:

- Strong Stage 2, high RS, constructive sector, volume confirmation, and supportive fundamentals can become `ADD_ON_CONFIRMATION`.
- Strong existing position with extended RSI or near 52-week high exhaustion can become `HOLD` or `TRIM_INTO_STRENGTH`.
- Stage 4, SELL signal, weak RS, or deteriorating fundamentals becomes `AVOID_FRESH_ENTRY`.
- Mixed technical/fundamental evidence becomes `WATCHLIST` or `REVIEW_MANUALLY`.

## Scoring Model

Use deterministic component scoring so output can be tested.

Suggested weights:

- Market regime: 15%.
- Sector rotation: 15%.
- Stock technicals: 35%.
- Fundamentals: 20%.
- Catalyst/news support: 5%.
- Risk and data quality: 10%.

Data-quality penalties:

- Missing EOD price history: hard block for ranked recommendations.
- Missing fundamentals: lower confidence, not a hard block.
- Stale data: lower confidence and label the row.
- Conflicting signals: lower confidence unless the report explicitly frames the conflict.

Scores are explanatory. The final label must come from policy rules, not a black-box score threshold alone.

## Report Layout

### 1. Executive Summary

- Market regime.
- Top sector rotation signal.
- Best grounded opportunities.
- Key risks and missing-data warnings.
- Portfolio/watchlist action summary.

### 2. Market Regime

- Index table and narrative.
- Nifty 50, Bank Nifty, Next 50, Midcap 100, Smallcap 100, and major sector indices.
- Breadth and trend alignment.
- Risk-on/risk-off framing.

### 3. Sector Rotation

- Sector leaders and laggards.
- Improving and weakening sectors.
- Multi-timeframe sector matrix.
- Sector-to-stock drilldown where available.

### 4. Stock Opportunity Map

- Ranked candidate table.
- Action label, confidence, score, technical state, fundamentals state, sector context.
- Evidence snippet and suggested follow-up command.

### 5. Portfolio / Watchlist Actions

- Holding/watchlist table.
- Current grounded action.
- Trigger, invalidation, risk, missing evidence.
- P&L context only when portfolio cost basis is available.

### 6. Technical Detail Appendix

- Multi-timeframe technical matrix.
- Indicator conflicts.
- 52-week proximity and drawdown table.
- Volume confirmation table.

### 7. Fundamental Detail Appendix

- Quality overlay table.
- Earnings/margin/debt warnings.
- Missing fundamentals list.

### 8. Grounding & Audit Trail

- Data date.
- Source tables/files.
- Row counts.
- Tool/source trail.
- Fallback usage.
- Missing evidence.
- Report generation timestamp.

## Storage

Persist the generated evidence pack and report metadata.

Preferred storage:

- PostgreSQL schema: `recommendation_reports`.
- Table `recommendation_reports.runs`: run metadata, as-of date, report paths, top labels, source trail.
- Table `recommendation_reports.evidence`: run id, scope, symbol/index/sector, evidence JSONB.
- Table `recommendation_reports.recommendations`: run id, subject, label, confidence, score, policy reasons JSONB.

If PostgreSQL is unavailable, write the evidence pack as JSON beside the report and mark persistence as fallback.

## Error Handling

The report must degrade gracefully:

- If portfolio data is unavailable, render market-wide and stock sections and mark portfolio missing.
- If fundamentals are unavailable for a symbol, keep technical evidence but lower confidence.
- If index EOD data is missing, block market-regime scoring and show a data-quality failure.
- If a sector source is stale, label it and avoid high-confidence sector calls.
- If report rendering fails for PDF, keep HTML/Markdown output.

## Testing

Add unit tests for:

- Evidence pack construction from synthetic index, sector, stock, and portfolio data.
- Multi-timeframe technical metrics.
- Recommendation label policy for bullish, bearish, mixed, and missing-data cases.
- Fundamental overlay classification.
- Missing evidence and stale-data confidence penalties.
- HTML/Markdown report includes audit trail and source freshness.
- `/report recommendation` command parsing.
- PostgreSQL persistence with fallback behavior.

Add integration tests for:

- End-to-end report generation with local fixture data.
- No recommendation label without evidence fields.
- Conflicting signals are rendered in the report.

## Out Of Scope For First Version

- Intraday/live trading calls.
- Automated order placement.
- Personalized financial advice.
- Broker-style target prices.
- LLM-only recommendations without deterministic evidence.
- Manual portfolio optimization beyond action labels.
- New external data vendors.

## Success Criteria

- The report can be generated from local EOD data without network dependency.
- Every recommendation row has evidence, trigger, invalidation, risk, confidence, and source trail.
- Missing data is visible and lowers confidence.
- Multi-timeframe technical analysis appears in both scoring and report sections.
- The generated report is replayable from the saved evidence pack.
- Tests cover scoring, policy, rendering, and persistence fallback.
