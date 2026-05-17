# Strategy Council Enhancement Roadmap

**Scope:** `backtesting/strategy_council`  
**Purpose:** Long-form roadmap for extending Strategy Council from a research/backtest loop into a richer decision-intelligence stack.  
**Status basis:** Current tree already includes rule composition, enriched evidence, advanced critics, and a basic HTML dashboard.

---

## Current Capability Baseline

The Strategy Council currently has these foundations:

- **Contracts and orchestration:** `types.py`, `council.py`
- **Evidence pack builder:** `evidence.py`
- **Evidence enrichment:** `evidence_enrichment.py`
  - Market regime
  - Factor exposure stub/beta when benchmark is supplied
  - EOD-derived microstructure such as ATR%, high-low spread, and average traded value
- **Strategy generation:** `strategy_generator.py`
  - Atomic rule registry
  - Rule composer
  - Deterministic sampled/exhaustive candidate generation
  - `CompositeStrategist`
- **Execution:** `runner.py`, `rule_composed_engine.py`
  - `stage2`
  - `rule_composed`
- **Critics:** `llm.py`, `critics_advanced.py`
  - Data leakage critic
  - Risk critic
  - Drawdown critic
  - Train/validation correlation critic
  - Factor exposure critic
  - Regime conditional critic
- **Reporting:** `report.py`, `dashboard_generator.py`
  - Markdown report
  - Basic standalone HTML dashboard
- **Persistence:** `postgres_storage.py`

This roadmap focuses on what should come next.

---

## 1. Evidence Enhancements

### High ROI / Medium Effort

1. **Multi-Timeframe Evidence**
   - Merge daily, weekly, and intraday signals into one point-in-time evidence view.
   - Detect conflicts such as daily bullish trend with intraday reversal.
   - Expected impact: high. This is likely the most useful next evidence upgrade.
   - Estimated effort: medium.

2. **Event and Results Context**
   - Add result dates, upcoming earnings, latest results, corporate actions, and major filings to evidence packs.
   - Change strategy parameters around event risk.
   - Expected impact: high for Indian equities because results dates and corporate actions materially affect short-horizon trades.
   - Estimated effort: medium.

3. **News Sentiment NLP**
   - Parse market/company news into sentiment, impact, entity, and source-confidence fields.
   - Surface catalyst direction and freshness.
   - Expected impact: high, but only if evidence is source-gated.
   - Estimated effort: medium to high.

4. **Order Flow and Liquidity Evidence**
   - Add delivery volume, turnover, bid/ask imbalance if available, and abnormal participation.
   - Expected impact: medium to high for short-horizon setups.
   - Estimated effort: medium, depending on data availability.

5. **Volatility and Derivatives Evidence**
   - Add option-chain PCR, max pain, OI concentration, IV skew/smile, futures basis, and cost of carry.
   - Expected impact: high for F&O names and indices.
   - Estimated effort: medium.

6. **Macro and Calendar Exposure**
   - Add RBI/Fed dates, CPI, crude, USDINR, India VIX, and global index context.
   - Expected impact: medium to high for regime filtering.
   - Estimated effort: medium.

7. **Advanced Technical Library**
   - Add Ichimoku, ADX expansion, RSI divergence, MACD histogram, Donchian channels, VWAP distance, and volatility compression.
   - Expected impact: medium.
   - Estimated effort: low to medium.

### Medium ROI / Medium Effort

8. **Sector and Peer Relative Strength**
   - Compare symbol returns against sector, peer basket, and broad index.
   - Detect laggards/leaders and relative underperformance.

9. **Correlation Clustering**
   - Build dynamic correlation clusters for risk and regime context.
   - Detect crowding and diversification breakdown.

10. **Seasonality and Calendar Anomalies**
   - Add day-of-week, month-of-year, expiry week, holiday, and earnings-season effects.

---

## 2. Critic Enhancements

### High ROI / Low to Medium Effort

1. **Sentiment Critic**
   - Flags candidates that depend on trading against strong sentiment.
   - Warns when strategy performance is fragile to sentiment reversals.

2. **Liquidity Critic**
   - Checks strategy position size against ADV/turnover.
   - Flags trades that are too large relative to liquidity.

3. **Execution Cost Critic**
   - Estimates brokerage, slippage, STT, exchange fees, and taxes.
   - Rejects candidates whose average profit is too small relative to estimated cost.

4. **Volatility Regime Critic**
   - Tests performance under low, medium, and high volatility regimes.
   - Flags strategies that only work in one volatility bucket.

### Medium ROI / Medium Effort

5. **Calendar Critic**
   - Tests result days, expiry week, holidays, RBI/Fed/CPI days, and corporate action windows.

6. **Causality / Redundancy Critic**
   - Flags redundant indicators such as highly correlated momentum signals.
   - Separates signal diversity from repeated versions of the same signal.

7. **Stress Test Critic**
   - Replays crisis windows and sharp drawdown periods.
   - Flags strategies that collapse during known stress regimes.

8. **Walk-Forward Critic**
   - Runs rolling train/validation windows and detects performance decay.
   - High value for overfitting control.

---

## 3. Strategy Generation Enhancements

### High ROI / Medium Effort

1. **Rule Interaction Graph**
   - Learn which entry/exit/risk atoms work well together.
   - Bias generation toward historically synergistic combinations.

2. **Feature Importance Ranking**
   - Score rules by contribution to returns, drawdown, hit rate, and robustness.
   - Feed the ranking back into generation.

3. **Constraint Satisfaction Generator**
   - Generate strategies under explicit constraints.
   - Example: at least one trend signal, one volume confirmation, one risk control.

4. **Genetic Algorithm Optimizer**
   - Evolve rule combinations over multiple generations using validation score as fitness.

5. **Meta-Strategy / Ensemble Synthesis**
   - Combine multiple strategies through voting or confidence weighting.

### High Effort / Later

6. **Neural Strategy Performance Predictor**
   - Predict expected performance from strategy features before backtesting.

7. **Reinforcement Learning Composer**
   - Learn rule composition through reward feedback.

8. **Transfer Learning Across Symbols**
   - Reuse learned rule preferences across similar stocks/sectors.

---

## 4. Dashboard and Reporting Enhancements

### High ROI / Low to Medium Effort

1. **Performance Attribution Dashboard**
   - Show which rules contributed to P&L, hit rate, and drawdown.

2. **Rule Correlation Heatmap**
   - Visualize redundancy between rules and signals.

3. **Walk-Forward Visualization**
   - Plot rolling returns, Sharpe, drawdown, and trade count.

4. **Monte Carlo Simulation View**
   - Bootstrap trades and show confidence intervals around outcomes.

5. **Strategy Comparison Dashboard**
   - Compare two or more strategies side-by-side.

6. **Excel/PDF Export**
   - Export evidence, metrics, trades, critiques, and dashboard summaries.

7. **Annotated Charts**
   - Add earnings, results, RBI/Fed events, and corporate actions to performance charts.

### Medium ROI / Higher Effort

8. **Real-Time Monitoring Dashboard**
   - Track live signals, open positions, and exits.

9. **Multi-Symbol Comparison**
   - Compare the same strategy across a symbol universe.

10. **Custom Report Builder**
   - User-selected sections, metrics, and report templates.

---

## 5. Operational Enhancements

The platform should remain research-only until Strategy Council robustness is proven.

1. **Live Signal Generation**
   - Generate today’s candidate entry/exit signals from current data.

2. **Position Management**
   - Track hypothetical or paper positions and emit exit/rebalance signals.

3. **Risk Limits Engine**
   - Enforce max position risk, max portfolio drawdown, and max open signals.

4. **Multi-Symbol Orchestration**
   - Coordinate strategy council outputs across a universe.

5. **Execution Engine**
   - Defer until research outputs are stable and paper-trading validation exists.

6. **Compliance and Audit Trail**
   - Store decisions, evidence, source trail, strategy spec, critic verdicts, and user-visible rationale.

---

## 6. Analysis and Insight Enhancements

1. **Evidence Feature Importance**
   - Determine which evidence dimensions explain returns and risk.

2. **Sensitivity Analysis**
   - Vary parameters and measure robustness.

3. **Regime Decomposition**
   - Deepen existing regime enrichment into per-regime performance tables.

4. **Causality Analysis**
   - Identify which rules plausibly add independent signal versus correlation.

5. **Macro Factor Exposure**
   - Regress strategy returns against rates, crude, USDINR, VIX, and index returns.

6. **Transaction Cost Analysis**
   - Detailed cost breakdown by trade and strategy.

7. **Drawdown Attribution**
   - Identify trades and regimes responsible for worst drawdowns.

---

## 7. Advanced ML / AI

These should follow once historical council runs are persisted and enough observations exist.

1. **LLM Narrative Generation**
   - Generate human-readable strategy explanations from validated evidence only.

2. **Anomaly Detection**
   - Detect unusual evidence regimes where historical backtests may not apply.

3. **Reinforcement Learning Rule Composer**
   - Long-term research item.

4. **Transfer Learning**
   - Learn patterns across sectors and similar stocks.

5. **Causal Discovery**
   - Explore automated causal graph discovery for signals.

6. **Transformer Strategy Synthesis**
   - Defer until enough labeled strategy-run history exists.

---

## 8. Infrastructure and Scale

1. **Parallel Backtesting**
   - Run many specs/symbols concurrently.

2. **Distributed Council**
   - Separate evidence, backtest, critic, and report workers.

3. **Streaming Data Pipeline**
   - Incremental live evidence updates.

4. **Data Warehouse Schema**
   - Scale from local PostgreSQL to partitioned long-horizon storage.

5. **CI/CD for Strategies**
   - Test, backtest, dashboard, and approval pipeline for new rules.

6. **A/B Testing Framework**
   - Formal comparison of strategy changes over time.

7. **Backtesting Result Cache**
   - Avoid recomputing identical symbol/spec/date-window runs.

---

## Recommended Build Order

### Phase A — Quick Wins

1. Performance attribution dashboard
2. Liquidity critic
3. Execution cost critic
4. Walk-forward visualization
5. Multi-timeframe evidence

### Phase B — Robustness

1. Walk-forward critic
2. Stress test critic
3. Sensitivity analysis
4. Volatility regime critic
5. Drawdown attribution

### Phase C — Scale

1. Multi-symbol comparison
2. Parallel backtesting
3. Backtesting cache
4. Strategy comparison dashboard
5. Data warehouse schema

### Phase D — Advanced IP

1. Rule interaction graph
2. Feature importance ranking
3. Genetic optimizer
4. LLM evidence-gated narratives
5. Transfer learning / RL research

