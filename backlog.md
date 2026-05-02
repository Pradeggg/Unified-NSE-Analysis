# Sector Rotation Report Backlog

This backlog captures enhancement ideas for the NSE sector-rotation report and dashboard. The goal is to move the report from a ranked research output toward an actionable sector-leadership workflow with clearer setup labels, risk levels, and interactive review.

## 1. A+ Setup Classification

**Feature**

Classify every stock into an explicit setup type so users can quickly distinguish leaders from watchlist names.

Suggested setup labels:

- `LEADER_BREAKOUT`: near/above 52-week high, strong RS, bullish Supertrend, confirmed breakout/volume.
- `FAST_RECOVERY`: strong recovery from 52-week low with improving trend, but not necessarily at breakout.
- `BASE_NEAR_HIGH`: tight consolidation within 5-10% of 52-week high.
- `SECTOR_LEADER`: top RS stock inside a rotating sector, even if no breakout yet.
- `PULLBACK_TO_SUPPORT`: bullish trend, currently near Supertrend/support after prior strength.
- `EXTENDED_RISK`: strong stock but stretched from base or overheated by RSI/price extension.
- `AVOID_WEAK_RS`: sector is rotating, but stock is not confirming with RS or trend.

**Design**

Add a pure classification function in `sector_rotation_report.py` that consumes existing columns:

- `DRAWDOWN_FROM_52W_HIGH_PCT`
- `RECOVERY_FROM_52W_LOW_PCT`
- `RELATIVE_STRENGTH`
- `RS_RANK_SCORE`
- `SUPERTREND_STATE`
- `PATTERN`
- `VOLUME_RATIO`
- `RSI`
- `TECHNICAL_SCORE`

The function should produce:

- `SETUP_TYPE`
- `SETUP_GRADE`
- `SETUP_REASON`

**User Experience**

Show setup labels in the main candidate table and peak-resilience table. Add a summary table at the top:

| Setup | Count | Top Stocks |
|---|---:|---|
| Leader Breakout | 5 | COALINDIA, ONGC, ... |
| Base Near High | 8 | MTARTECH, DATAPATTNS, ... |

**Build**

- Add unit tests for each setup label.
- Keep classification rules deterministic and visible in methodology.
- Avoid hard-coding symbols; rely only on metrics.

## 2. Action Buckets

**Feature**

Convert raw rankings into user-facing action buckets:

- `BUY_WATCH`: actionable setup with strong trend and acceptable risk.
- `BREAKOUT_WATCH`: near resistance or base high; wait for breakout confirmation.
- `WAIT_FOR_PULLBACK`: high-quality stock but extended.
- `HOLD_TRAIL`: already strong; use trailing stop.
- `AVOID`: weak trend, poor RS, or too much drawdown.

**Design**

Action bucket should be derived after setup classification. The logic should blend:

- setup type
- Supertrend state
- distance from 52-week high
- volume confirmation
- RSI
- technical score
- fundamental score
- sector rotation rank

**User Experience**

Add an “Action Summary” section before stock tables:

| Action | Stock | Sector | Trigger | Invalidation |
|---|---|---|---|---|
| BUY WATCH | COALINDIA | Metals | Close above 52W high | Close below support |
| WAIT FOR PULLBACK | MTARTECH | Defence | Pullback near 20DMA/Supertrend | Close below base |

**Build**

- Add `ACTION_BUCKET`, `ACTION_REASON`.
- Sort final report by action priority first, score second.
- Add tests for bucket priority and edge cases.

## 3. Entry, Stop, and Invalidation Levels

**Feature**

Add risk-planning levels for each candidate:

- Entry zone
- Breakout trigger
- Stop level
- Invalidation level
- Risk percentage

**Design**

Use existing technical levels:

- breakout trigger: resistance or 52-week high
- support: 20-session base support
- Supertrend value
- stop: max of logical support/Supertrend depending on setup type
- invalidation: close below base support or Supertrend flip

Suggested outputs:

- `ENTRY_TRIGGER`
- `ENTRY_ZONE_LOW`
- `ENTRY_ZONE_HIGH`
- `STOP_LEVEL`
- `INVALIDATION_LEVEL`
- `RISK_PCT`

**User Experience**

In deep stock notes, show a compact plan:

```text
Plan: Breakout above 476.00
Entry Zone: 467.00-476.00
Stop: 436.70
Risk: 6.5%
Invalidation: Close below Supertrend/support
```

**Build**

- Add pure function `calculate_trade_plan(row)`.
- Add tests for breakout, pullback, and avoid setups.
- Use clear “research only” language; do not frame as personalized advice.

## 4. Relative Strength Trend and RS Line

**Feature**

Move from a single RS value to RS trend analysis.

Add:

- RS vs Nifty 500 over 1M, 3M, 6M
- RS vs sector index
- RS slope
- RS acceleration
- RS new-high flag

**Design**

Use stock and index history from the local OHLC cache:

- calculate stock return over multiple windows
- subtract Nifty 500 return
- subtract sector index return
- compare current RS line to recent max

Suggested columns:

- `RS_1M`
- `RS_3M`
- `RS_6M`
- `RS_SLOPE_20D`
- `RS_ACCELERATION`
- `RS_NEW_HIGH`
- `RS_VS_SECTOR_1M`

**User Experience**

Show RS trend as labels:

- `RS_LEADER`
- `RS_IMPROVING`
- `RS_FLAT`
- `RS_FADING`

Add small language to stock notes:

```text
RS Trend: Improving; stock is outperforming both Nifty 500 and its sector index over 1M.
```

**Build**

- Add sector-index mapping to compute sector-relative RS.
- Add tests using small synthetic stock/index time series.

## 5. Stage Analysis

**Feature**

Classify every stock into market stage:

- Stage 1: base building
- Stage 2: advancing trend
- Stage 3: topping/distribution
- Stage 4: decline

**Design**

Use:

- 50DMA
- 150DMA
- 200DMA
- 52-week high/low position
- price above/below moving averages
- moving average slope

Suggested rules:

- Stage 2: price above 50/150/200DMA, 50DMA > 150DMA > 200DMA, 200DMA rising.
- Stage 1: price basing around 200DMA with flat long-term average.
- Stage 3: price near highs but moving averages flattening and failed breakouts.
- Stage 4: price below 200DMA or long-term averages falling.

**User Experience**

Add `STAGE` and `STAGE_REASON` to tables and deep notes. Prioritize Stage 2 and early Stage 2 in action buckets.

**Build**

- Add moving-average calculation from stock history.
- Add tests for each stage.
- Do not overfit; keep rules transparent.

## 6. Volume Accumulation and Breakout Quality

**Feature**

Improve breakout confidence by measuring volume behavior.

Add:

- volume dry-up in base
- breakout volume ratio
- up-volume vs down-volume
- accumulation/distribution score
- OBV trend

**Design**

Use `TOTTRDQTY`, price direction, and recent base windows.

Suggested columns:

- `VOLUME_DRY_UP`
- `BREAKOUT_VOLUME_RATIO`
- `UP_DOWN_VOLUME_RATIO`
- `OBV_SLOPE`
- `ACCUMULATION_SCORE`

**User Experience**

In tables, show volume quality as:

- `CONFIRMED`
- `EARLY`
- `WEAK`
- `DISTRIBUTION_RISK`

**Build**

- Add tests for simple up-volume/down-volume scenarios.
- Use volume as confirmation, not as the sole reason to rank a stock.

## 7. Fundamental Quality Layer

**Feature**

Turn numerical fundamental scores into clearer business-quality labels.

Suggested labels:

- `QUALITY_COMPOUNDER`
- `CYCLICAL_LEADER`
- `TURNAROUND`
- `SPECULATIVE_MOMENTUM`
- `BALANCE_SHEET_RISK`

**Design**

Use refreshed Screener data and existing score columns:

- `ENHANCED_FUND_SCORE`
- `EARNINGS_QUALITY`
- `SALES_GROWTH`
- `FINANCIAL_STRENGTH`
- `INSTITUTIONAL_BACKING`
- optional Screener summaries: ROCE, debt, EPS, NPM, YoY sales/profit.

**User Experience**

Add business-quality label next to technical setup. A stock could be:

```text
Setup: LEADER_BREAKOUT
Business Quality: CYCLICAL_LEADER
Risk: commodity cycle sensitivity
```

**Build**

- Parse Screener ratio summaries when available.
- Keep missing-data states explicit.
- Add tests for score-to-label rules.

## 8. Sector Breadth Confirmation

**Feature**

Show whether sector rotation is broad or narrow.

Metrics:

- % stocks above 20DMA/50DMA/200DMA
- % stocks within 20% of 52-week high
- % stocks with bullish Supertrend
- number of stocks making 52-week highs
- median RS within sector
- top contributors by RS

**Design**

Compute breadth for each rotating sector from the full sector universe, not only top candidates.

Suggested outputs:

- `SECTOR_BREADTH_SCORE`
- `BREADTH_TREND`
- `BREADTH_CONFIRMATION`

**User Experience**

Add sector cards:

```text
Defence: Strong rotation, broad participation
80% bullish Supertrend, 45% near 52W high, median RS +18%
```

**Build**

- Add full sector universe enrichment from OHLC cache.
- Use breadth as a sector-level filter.
- Add tests with synthetic sector universes.

## 9. Backtest and Forward Validation

**Feature**

Validate each setup type historically.

Backtest outputs:

- 1M, 3M, 6M forward returns
- hit rate
- average return
- median return
- max drawdown
- benchmark excess return
- sector-level performance

**Design**

Start with price-only backtests to avoid point-in-time fundamental bias. Later, add fundamentals only if point-in-time snapshots are available.

Backtest setup examples:

- peak-resilience stocks near high
- consolidation breakouts
- RS leaders in rotating sectors
- Stage 2 leaders

**User Experience**

Add confidence notes:

```text
Historical setup performance: 3M hit rate 62%, median excess +4.1%.
```

**Build**

- Reuse `working-sector/phase4_backtest.py` concepts.
- Add a separate `sector_rotation_backtest.py`.
- Keep assumptions and data limitations visible.

## 10. Interactive HTML Dashboard

**Feature**

Upgrade the HTML from static Markdown rendering to an interactive dashboard.

Features:

- sortable tables
- filters by sector, setup, action bucket, stage, Supertrend, near-high flag
- summary cards
- collapsible deep stock notes
- color-coded scores
- links to Screener/NSE
- downloadable CSV

**Design**

Use static HTML with embedded CSS and JavaScript so it can open locally without a server.

Page sections:

1. Executive summary
2. Sector rotation cards
3. Action bucket table
4. Peak resilience table
5. Stock deep-dive accordion
6. Methodology

**User Experience**

The first screen should answer:

- Which sectors are rotating?
- Which stocks are actionable?
- Which setups are cleanest?
- What is the risk/invalidation?

**Build**

- Add `render_interactive_html()` separately from Markdown rendering.
- Keep data embedded as JSON.
- Add basic smoke test that generated HTML contains required JS data and sections.

## 11. Output Files and Data Export

**Feature**

Produce machine-readable outputs alongside Markdown/HTML.

Outputs:

- `Sector_Rotation_Report_<timestamp>.md`
- `Sector_Rotation_Report_<timestamp>.html`
- `Sector_Rotation_Candidates_<timestamp>.csv`
- `Sector_Rotation_Peak_Resilience_<timestamp>.csv`
- `Sector_Rotation_Sector_Breadth_<timestamp>.csv`

**Design**

Use the same enriched dataframes that feed the report.

**User Experience**

CSV exports allow quick review in Excel or further filtering.

**Build**

- Add `ReportPaths` fields for CSV files.
- Add tests that generated CSVs have expected columns.

## 12. Daily Run and Report Index

**Feature**

Make it easy to run daily and compare outputs over time.

Add:

- `reports/latest_sector_rotation.md`
- `reports/latest_sector_rotation.html`
- report index file listing historical runs
- optional email attachment integration

**Design**

After each report generation, copy or write latest aliases.

**User Experience**

Users can always open:

```text
reports/latest_sector_rotation.html
```

without searching for timestamped files.

**Build**

- Add latest-file writing to `generate_report()`.
- Add index update function.
- Avoid deleting historical reports.

## Recommended Build Order

1. **A+ Setup Classification**
2. **Action Buckets**
3. **Entry, Stop, and Invalidation Levels**
4. **RS Trend and Stage Analysis**
5. **Sector Breadth Confirmation**
6. **Interactive HTML Dashboard**
7. **CSV Exports and Latest Aliases**
8. **Backtest and Forward Validation**

This order gives the fastest improvement in decision quality while keeping each change testable and reversible.
