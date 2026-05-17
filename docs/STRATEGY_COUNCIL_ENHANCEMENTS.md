# Strategy Council Enhancement Specification

> Extends: `backtesting/strategy_council/`  
> Focus: Critic sophistication, evidence richness, strategy generation, reporting & visualization  
> Status: Design (implementation-ready)  
> Stance: Research-only; no investment advice. All enhancements preserve data leakage prevention and auditability.

---

## Executive Summary

The enhanced Strategy Council adds four interconnected capabilities:

1. **Evidence Enrichment** — Fundamentals, sentiment, regime classification, and market microstructure fed into the orchestration loop and evidence pack.
2. **Advanced Critics** — Drawdown-centric, correlation-aware, factor-based, and regime-conditional critiques that flag overfitting and market-regime mismatches.
3. **Strategy Generation** — Whitelist expansion, combinatorial rule composition, and optional ML-assisted candidate discovery.
4. **Reporting & Dashboards** — Attribution-rich Markdown, interactive HTML dashboards with trade-by-trade drill-down, and regime-conditional performance slicing.

All new evidence is surfaced as **optional** slots in `EvidencePack` with explicit `missing` tracking. Critics consume only what's available. The core iteration loop remains deterministic and auditable.

---

## 1. Evidence Enrichment (`evidence_enrichment.py`)

Extends `EvidencePack` with new data sources while preserving the "fail gracefully, record attempts" pattern.

### 1.1 Extended `EvidencePack` Schema

```python
@dataclass
class EvidencePack:
    # Original fields
    symbol: str
    as_of: datetime
    technical: dict[str, Any]
    fundamental: dict[str, Any]
    market: dict[str, Any]
    news: dict[str, Any]
    freshness: dict[str, bool]
    missing: list[str]
    source_trail: list[dict[str, str]]
    
    # New enrichment fields
    sentiment: dict[str, Any] = field(default_factory=dict)
    regime: dict[str, Any] = field(default_factory=dict)
    microstructure: dict[str, Any] = field(default_factory=dict)
    factor_exposure: dict[str, Any] = field(default_factory=dict)
```

Each new slot includes:

- **`sentiment`** — multi-source sentiment scores (news, social, VIX proxy), confidence, last update.
- **`regime`** — detected market regime (bull/bear/sideways), volatility regime (high/low), trend strength, lookback window.
- **`microstructure`** — bid-ask spread, order book depth, volume profile, intraday volatility.
- **`factor_exposure`** — momentum, value, growth, volatility scores for the symbol and sector peers.

### 1.2 Enrichment Functions

#### `load_fundamental_snapshot(symbol, as_of=None, conn=None)`

- Query: `fundamental_metrics` table (latest quarterly, point-in-time as of `as_of`).
- Fetch: P/E, P/B, ROE, debt/equity, free cash flow, dividend yield, growth rate.
- Output: `{"pe": ..., "pb": ..., "roe": ..., ...}` or `{}` if unavailable.
- Record: Attempt in `source_trail` regardless of success.

#### `detect_market_regime(eod_df, lookback=252)`

- Compute: 60-day exponential moving average (trend), Bollinger Band width (volatility), RSI.
- Classify regime:
  - Bull: close > EMA60 *and* BB width > median BB (high trend conviction).
  - Bear: close < EMA60 *and* BB width > median BB.
  - Sideways: close oscillating within BB; width < median BB.
- Output: `{"regime": "bull"|"bear"|"sideways", "volatility_regime": "high"|"low", "trend_strength": 0.0..1.0, "lookback_days": 252}`.

#### `compute_sentiment_score(symbol, as_of=None)`

- Multi-source aggregation:
  - **News sentiment** — parse recent headlines, compute weighted sentiment (decay by recency).
  - **Social sentiment** — fetch mentions/sentiment from curated social/forum sources (or stub if unavailable).
  - **VIX-proxy** — if symbol is index or large-cap, use sector VIX or realized vol as proxy for fear.
- Output: `{"news": 0.5, "social": 0.3, "fear_proxy": 0.6, "composite": 0.45, "sources_live": 2, "as_of_utc": "..."}`.
- Fallback: If all sources fail, return `{}` and record in `source_trail`.

#### `compute_intraday_microstructure(symbol, as_of=None, tick_data_path=None)`

Optional tick-level data:

- Bid-ask spread (median, 99th percentile).
- Volume profile (VWAP, standard deviation of VWAP).
- Intraday volatility (close-to-close vs. open-to-close).
- Order imbalance (if order book available).
- Output: `{"spread_bps": ..., "volume_profile_std": ..., "intraday_vol": ..., ...}`.
- If tick data unavailable, return `{}` (recorded in `source_trail`).

#### `compute_factor_exposure(symbol, sector, as_of=None)`

- Fetch: 252-day rolling factor loadings (momentum, value, quality, volatility) via rolling regression against sector index.
- Compare: symbol factor scores vs. sector median.
- Output: `{"momentum": 0.7, "value": -0.3, "quality": 0.5, "volatility": 0.2, "sector_median": {...}, "relative_to_sector": {...}}`.

### 1.3 Integration into `build_evidence_pack(symbol, ...)`

```python
def build_evidence_pack(symbol, as_of=None, include_enrichment=True):
    # Existing: load technical, news, market.
    pack = EvidencePack(...)
    
    if include_enrichment:
        # New: enrichment is optional and failure-tolerant.
        try:
            pack.fundamental = load_fundamental_snapshot(symbol, as_of)
        except Exception as e:
            pack.source_trail.append({...error...})
            pack.missing.append("fundamental")
        
        try:
            pack.sentiment = compute_sentiment_score(symbol, as_of)
        except Exception as e:
            pack.source_trail.append({...error...})
            pack.missing.append("sentiment")
        
        try:
            pack.regime = detect_market_regime(eod_df, lookback=252)
        except Exception as e:
            pack.source_trail.append({...error...})
            pack.missing.append("regime")
        
        try:
            pack.microstructure = compute_intraday_microstructure(symbol, as_of)
        except Exception as e:
            pack.source_trail.append({...error...})
            pack.missing.append("microstructure")
        
        try:
            pack.factor_exposure = compute_factor_exposure(symbol, sector, as_of)
        except Exception as e:
            pack.source_trail.append({...error...})
            pack.missing.append("factor_exposure")
    
    return pack
```

**Key principle:** Every failed attempt is recorded; missing enrichments are tracked explicitly. Critics consume only what's available.

---

## 2. Advanced Critics (`critics_advanced.py`)

New critic implementations that consume the enriched evidence and flag systemic risks invisible to simple return-based scoring.

### 2.1 `DrawdownCritic`

Flags strategies prone to deep underwater excursions, which may be technically profitable but psychologically or operationally unsafe.

```python
class DrawdownCritic:
    def critique(
        self,
        candidates: tuple[StrategySpec, ...],
        train_results: dict[str, BacktestSliceResult],
        validation_results: dict[str, BacktestSliceResult],
    ) -> Critique:
        """
        Scan validation results for max drawdown.
        Flag if max_dd > threshold (e.g., 15%).
        """
        issues = []
        for cand_id, val_result in validation_results.items():
            if val_result.metrics.get("max_drawdown_pct", 0) > 15.0:
                issues.append(
                    f"Candidate {cand_id} shows max drawdown {val_result.metrics['max_drawdown_pct']:.1f}% "
                    f"on validation; risk of extended underwater periods."
                )
        
        if issues:
            return Critique(
                critic="drawdown",
                verdict="revise",
                issues=issues,
                required_changes=[
                    "Tighten stop-loss or exit rules to limit max drawdown to <10%.",
                    "Consider regime filtering: avoid trading in bear regimes.",
                ],
                confidence_delta=-0.2,  # Penalize high-drawdown candidates
            )
        return Critique(
            critic="drawdown",
            verdict="accept",
            issues=[],
            required_changes=[],
            confidence_delta=0.0,
        )
```

### 2.2 `CorrelationCritic`

Flags overfitting: strategies that work on validation but may be curve-fit to historical noise rather than capturing true regime dynamics.

```python
class CorrelationCritic:
    def critique(
        self,
        candidates: tuple[StrategySpec, ...],
        train_results: dict[str, BacktestSliceResult],
        validation_results: dict[str, BacktestSliceResult],
        evidence: EvidencePack,
    ) -> Critique:
        """
        Compare train vs. validation performance correlation.
        High correlation = consistent alpha; low = potential overfitting.
        """
        issues = []
        
        train_returns = [r.metrics.get("total_return_pct", 0) for r in train_results.values()]
        val_returns = [r.metrics.get("total_return_pct", 0) for r in validation_results.values()]
        
        if train_returns and val_returns:
            corr = np.corrcoef(train_returns, val_returns)[0, 1]
            if corr < 0.3:  # Low correlation suggests overfitting
                issues.append(
                    f"Train/validation return correlation is {corr:.2f}; "
                    f"suggests potential overfitting to historical patterns."
                )
        
        # Additional check: regime-specific performance
        if evidence.regime.get("regime"):
            # If training was mostly in bull regime, does validation hold in the detected regime?
            # This requires regime labels on train/val splits.
            pass
        
        if issues:
            return Critique(
                critic="correlation",
                verdict="revise",
                issues=issues,
                required_changes=[
                    "Simplify entry/exit rules; reduce rule count to avoid overfitting.",
                    "Add regime filters or multi-timeframe confirmation.",
                ],
                confidence_delta=-0.15,
            )
        return Critique(
            critic="correlation",
            verdict="accept",
            issues=[],
            required_changes=[],
            confidence_delta=0.0,
        )
```

### 2.3 `FactorBasedCritic`

Flags strategies whose returns correlate too tightly to known factors (momentum, mean-reversion, volatility), suggesting they may not capture idiosyncratic alpha.

```python
class FactorBasedCritic:
    def critique(
        self,
        candidates: tuple[StrategySpec, ...],
        validation_results: dict[str, BacktestSliceResult],
        evidence: EvidencePack,
    ) -> Critique:
        """
        Check if strategy returns are explained by factor loadings.
        If R² > 0.8 to known factors, strategy is largely factor-driven (not idiosyncratic alpha).
        """
        issues = []
        
        if not evidence.factor_exposure:
            return Critique(
                critic="factor_based",
                verdict="accept",
                issues=["Factor exposure data unavailable; skipping factor critique."],
                required_changes=[],
                confidence_delta=0.0,
            )
        
        # For each candidate, estimate factor exposure via rolling window regression.
        for cand_id, val_result in validation_results.items():
            trade_returns = val_result.metrics.get("trade_returns", [])
            if not trade_returns:
                continue
            
            # Regress trade returns against factor proxies.
            # If R² > 0.8, most return is from known factors.
            r_squared = estimate_factor_r_squared(trade_returns, evidence.factor_exposure)
            if r_squared > 0.8:
                issues.append(
                    f"Candidate {cand_id}: {(r_squared * 100):.0f}% of returns "
                    f"explained by known factors (momentum, value, vol); low idiosyncratic alpha."
                )
        
        if issues:
            return Critique(
                critic="factor_based",
                verdict="revise",
                issues=issues,
                required_changes=[
                    "Add idiosyncratic filters (e.g., sector rotation, earnings surprises, technical anomalies).",
                ],
                confidence_delta=-0.1,
            )
        return Critique(
            critic="factor_based",
            verdict="accept",
            issues=[],
            required_changes=[],
            confidence_delta=0.0,
        )
```

### 2.4 `RegimeConditionalCritic`

Flags strategies that perform well in-sample but break down in certain market regimes (e.g., a bull-biased strategy failing in bear markets).

```python
class RegimeConditionalCritic:
    def critique(
        self,
        candidates: tuple[StrategySpec, ...],
        validation_results: dict[str, BacktestSliceResult],
        eod_df: pd.DataFrame,  # To infer regime labels on validation split
        evidence: EvidencePack,
    ) -> Critique:
        """
        Slice validation performance by detected regime.
        If performance is highly regime-dependent, flag for regime filtering.
        """
        issues = []
        
        if not evidence.regime or "regime" not in evidence.regime:
            return Critique(
                critic="regime_conditional",
                verdict="accept",
                issues=["Regime detection unavailable; skipping regime critique."],
                required_changes=[],
                confidence_delta=0.0,
            )
        
        # Label validation split rows with regime (using detect_market_regime on rolling window).
        val_regime_labels = label_validation_regime(eod_df, evidence.regime)
        
        for cand_id, val_result in validation_results.items():
            perf_by_regime = compute_performance_by_regime(val_result, val_regime_labels)
            
            # If performance spread is high (e.g., +15% in bull, -5% in bear), flag.
            if perf_by_regime:
                regime_spread = max(perf_by_regime.values()) - min(perf_by_regime.values())
                if regime_spread > 15:
                    issues.append(
                        f"Candidate {cand_id} shows high regime dependence ({regime_spread:.1f}% spread); "
                        f"performance varies: {perf_by_regime}."
                    )
        
        if issues:
            return Critique(
                critic="regime_conditional",
                verdict="revise",
                issues=issues,
                required_changes=[
                    "Add explicit regime gates (e.g., 'only trade if regime == bull and vol < median').",
                    "Consider separate strategies per regime.",
                ],
                confidence_delta=-0.15,
            )
        return Critique(
            critic="regime_conditional",
            verdict="accept",
            issues=[],
            required_changes=[],
            confidence_delta=0.0,
        )
```

### 2.5 Critic Integration into `run_strategy_council`

```python
def run_strategy_council(
    eod_data: pd.DataFrame,
    *,
    evidence: EvidencePack,
    config: CouncilConfig,
    strategist=None,
    critics=None,
    use_advanced_critics=True,  # NEW
) -> CouncilResult:
    ...
    
    if use_advanced_critics and critics is None:
        critics = (
            RuleBasedDataLeakageCritic(),
            RuleBasedRiskCritic(),
            DrawdownCritic(),
            CorrelationCritic(),
            FactorBasedCritic(eod_df),
            RegimeConditionalCritic(eod_df),
        )
    
    # Each critic is called in sequence; issues and required_changes are merged
    # into strategist_revision for the next iteration.
    ...
```

---

## 3. Strategy Generation Expansion (`strategy_generator.py`)

### 3.1 Whitelist Expansion

Extend `CouncilConfig.allowed_strategies` to include new strategy families:

```python
# Original whitelist
("stage2", "supertrend_continuation", "rsi_pullback_stage2", "52w_high", "vcp")

# Enhanced whitelist (backward-compatible)
(
    # Original
    "stage2", "supertrend_continuation", "rsi_pullback_stage2", "52w_high", "vcp",
    
    # New: regime-conditional variants
    "stage2_bull_only", "stage2_bear_only",
    "supertrend_low_vol_only", "supertrend_high_vol_only",
    
    # New: multi-factor composites
    "momentum_value_blend", "quality_growth_pivot",
    
    # New: microstructure-informed
    "microstructure_mean_reversion", "order_flow_continuation",
    
    # New: sentiment-conditional
    "sentiment_confirmation_stage2", "sentiment_reversal",
)
```

Each new strategy id is wired into `backtesting.engine.run_backtest` with its own entry/exit/risk logic. The DSL compiler allows any whitelist member; unsupported strategies return zero-trade slices (visible in reports but never inflating metrics).

### 3.2 Combinatorial Rule Composition (`RuleComposer`)

Instead of proposing fixed specs, a rule composer generates specs by combining primitive rules.

```python
@dataclass(frozen=True)
class AtomicRule:
    rule_id: str  # e.g., "ema_bullish", "rsi_oversold", "volume_spike"
    parameters: dict[str, Any]  # e.g., {"period": 20, "threshold": 30}
    description: str

class RuleComposer:
    """
    Combines atomic rules into full entry/exit/risk specs.
    """
    
    ENTRY_RULES = {
        "ema_bullish": AtomicRule("ema_bullish", {"period": 20}, "close > EMA(20)"),
        "rsi_oversold": AtomicRule("rsi_oversold", {"period": 14, "threshold": 30}, "RSI(14) < 30"),
        "volume_spike": AtomicRule("volume_spike", {"period": 20, "multiplier": 1.5}, "Vol > 1.5 * SMA(20)"),
        "macd_cross": AtomicRule("macd_cross", {"fast": 12, "slow": 26, "signal": 9}, "MACD > Signal"),
    }
    
    EXIT_RULES = {
        "profit_target": AtomicRule("profit_target", {"pct": 2.0}, "Exit if +2% profit"),
        "stop_loss": AtomicRule("stop_loss", {"pct": 1.0}, "Exit if -1% loss"),
        "time_stop": AtomicRule("time_stop", {"days": 5}, "Exit after 5 days"),
        "trailing_stop": AtomicRule("trailing_stop", {"pct": 1.5}, "Exit if -1.5% from high"),
    }
    
    RISK_RULES = {
        "position_size": AtomicRule("position_size", {"pct_capital": 2.0}, "Risk 2% per trade"),
        "max_open": AtomicRule("max_open", {"count": 3}, "Max 3 open positions"),
        "correlate_filter": AtomicRule("correlate_filter", {"threshold": 0.7}, "Avoid correlated positions"),
    }
    
    def compose(
        self,
        entry_atoms: list[str],
        exit_atoms: list[str],
        risk_atoms: list[str],
        strategy_id: str,
        horizon_days: int,
        thesis: str,
    ) -> StrategySpec:
        """
        Combine atoms into a spec.
        """
        entry_rules = [self.ENTRY_RULES[a].description for a in entry_atoms if a in self.ENTRY_RULES]
        exit_rules = [self.EXIT_RULES[a].description for a in exit_atoms if a in self.EXIT_RULES]
        risk_rules = [self.RISK_RULES[a].description for a in risk_atoms if a in self.RISK_RULES]
        
        return StrategySpec(
            strategy_id=strategy_id,
            horizon_days=horizon_days,
            entry_rules=entry_rules,
            exit_rules=exit_rules,
            risk_rules=risk_rules,
            thesis=thesis,
            params={
                "entry_atoms": entry_atoms,
                "exit_atoms": exit_atoms,
                "risk_atoms": risk_atoms,
            },
            status="composed",
            origin="rule_composer",
        )
```

### 3.3 ML-Assisted Candidate Discovery (Optional)

For exploration: use a lightweight ML model to rank combinations of atomic rules by historical performance, surfacing the top K combinations as candidates.

```python
def ml_discover_candidates(
    eod_df: pd.DataFrame,
    allowed_strategies: tuple[str, ...],
    horizons: tuple[int, ...],
    top_k: int = 5,
    model_path: str | None = None,
) -> tuple[StrategySpec, ...]:
    """
    Train or load a lightweight ranking model (XGBoost on historical rule + horizon combinations).
    Return top-K candidates by predicted Sharpe ratio or info ratio.
    
    Model inputs: atomic rule ids, horizon, market regime, volatility regime.
    Model outputs: predicted Sharpe, predicted max drawdown, predicted trade frequency.
    
    Filter: only return candidates that do not violate forbidden tokens.
    Rank by info ratio (predicted return / predicted vol).
    """
    
    if model_path and Path(model_path).exists():
        model = load_model(model_path)
    else:
        # Build lightweight model on historical backtest runs
        # (sourced from strategy_council.split_results in Postgres)
        model = train_ranking_model(eod_df, allowed_strategies, horizons)
    
    candidates_ranked = model.predict_and_rank(
        allowed_strategies=allowed_strategies,
        horizons=horizons,
        features={
            "regime": detect_market_regime(eod_df),
            "volatility": compute_volatility(eod_df),
        },
    )
    
    return candidates_ranked[:top_k]
```

Integrate into `JSONLLMStrategist`:

```python
class JSONLLMStrategist:
    def propose(self, *, evidence, config, prior_feedback, use_ml_discovery=False):
        if use_ml_discovery:
            ml_candidates = ml_discover_candidates(
                eod_df, config.allowed_strategies, config.horizons, top_k=3
            )
            return ml_candidates + super().propose(...)
        else:
            return super().propose(...)
```

---

## 4. Enhanced Reporting & Visualization

### 4.1 Attribution-Rich Markdown

Extend `report.py::render_council_markdown` to include:

#### Trade-by-Trade Attribution

```markdown
## Trade-Level Attribution (Validation)

| Trade ID | Entry Date | Exit Date | Entry Price | Exit Price | Return % | Regime | Holding Days | Win/Loss |
|---|---|---|---|---|---|---|---|---|
| 1 | 2024-01-15 | 2024-01-18 | 100.0 | 102.3 | +2.3 | Bull | 3 | Win |
| 2 | 2024-01-22 | 2024-01-25 | 105.0 | 104.2 | -0.8 | Sideways | 3 | Loss |
| ... | ... | ... | ... | ... | ... | ... | ... | ... |

**Summary**: 42 trades total; 28 wins (67% win rate); avg win +1.8%; avg loss -0.9%; profit factor 2.1
```

#### Regime-Conditional Performance

```markdown
## Performance by Market Regime

| Regime | Trade Count | Total Return % | Avg Trade Return % | Max Drawdown % | Sharpe Ratio |
|---|---|---|---|---|---|
| Bull | 18 | +8.2 | +0.46 | -3.1 | 1.2 |
| Sideways | 15 | +2.1 | +0.14 | -5.2 | 0.3 |
| Bear | 9 | -1.5 | -0.17 | -7.8 | -0.5 |

**Interpretation**: Strategy excels in bull regimes, struggles in bear. Recommendation: apply regime gate.
```

#### Evidence & Enrichment Snapshot

```markdown
## Evidence Quality

| Source | Value | Freshness | Notes |
|---|---|---|---|
| **Technical** | Available | EOD | Latest close: 105.23 |
| **Regime** | Bull (trend: 0.78) | 1d old | 60-day EMA bullish; BB expanding |
| **Sentiment** | Composite 0.58 | 2h old | News +0.6, Social +0.5, Fear -0.1 |
| **Fundamentals** | P/E 22.3, ROE 15% | 30d old | Last quarterly report |
| **Factors** | Momentum +0.7 (vs sector +0.3) | 1d old | Momentum leader; value lagging |
| **Microstructure** | Spread 5 bps, Depth 2M | 1h old | Liquid; good execution profile |

**Missing**: Intraday order flow data; accumulation/distribution not available.
```

#### Critic Verdicts & Remediation Trace

```markdown
## Iteration 2: Critic Feedback → Strategy Revision

**Candidates proposed**: 5  
**Strategist note**: *"Incorporated feedback on regime filtering and drawdown control."*

| Critic | Verdict | Key Issues | Required Changes Applied |
|---|---|---|---|
| **Data Leakage** | ✅ Accept | None detected | N/A |
| **Risk** | ⚠️ Revise | Max DD 18% on candidate 3 | Tightened stop-loss from 2% to 1% |
| **Drawdown** | ⚠️ Revise | 3/5 candidates show DD > 12% | Added time-stop (5 days max) |
| **Correlation** | ✅ Accept | Train/val correlation 0.68 | N/A |
| **Factor-Based** | ⚠️ Revise | 80% return from momentum factor | Added value + quality filters |
| **Regime-Conditional** | ⚠️ Revise | 15% performance drop in bear | Applied regime gate: "Bull or Sideways only" |
```

### 4.2 Interactive HTML Dashboard

A production-grade React dashboard rendering the full Council result with drill-down capabilities.

#### Design Direction: **Industrial Data Precision**

- **Typography**: IBM Plex Mono (code), Archivo Narrow (labels), clean sans for body. Dark background with amber/teal accents (regime and sentiment signals).
- **Color scheme**: Deep charcoal background; amber for bull signals, teal for bear, gray for sideways. Red for drawdown; green for win trades.
- **Layout**: Asymmetric grid; left column (iteration timeline), center (metrics + performance charts), right column (regime slicing + evidence quality).
- **Interaction**: Hover trade rows to highlight entry/exit on price chart; click regime bars to filter trades; expand iterations to see raw critique text.

```html
<!-- Pseudo-code structure for dashboard.html -->
<dashboard>
  <header>
    <h1>Strategy Council: {SYMBOL}</h1>
    <recommendation-badge>{RECOMMENDATION}</recommendation-badge>
    <timestamp>{as_of_utc}</timestamp>
  </header>
  
  <grid>
    <left-panel>
      <!-- Iteration timeline -->
      <iteration-timeline iterations={iterations} />
      <!-- Evidence quality checklist -->
      <evidence-snapshot evidence={evidence} />
    </left-panel>
    
    <center-panel>
      <!-- Main performance chart: price + trades -->
      <performance-chart eod_data={eod_df} trades={locked_trades} />
      
      <!-- Metrics cards -->
      <metrics-row>
        <metric name="Total Return %" value={test_return} delta={train_vs_test} />
        <metric name="Max Drawdown %" value={max_dd} regime="critical|warning|ok" />
        <metric name="Win Rate %" value={win_rate} />
        <metric name="Profit Factor" value={pf} />
      </metrics-row>
      
      <!-- Iteration history table -->
      <iteration-table iterations={iterations} />
    </center-panel>
    
    <right-panel>
      <!-- Regime performance slice -->
      <regime-slicer performance_by_regime={perf_by_regime} />
      
      <!-- Trade attribution scatter -->
      <trade-scatter trades={trades_with_regime} color_by="regime" size_by="return_pct" />
      
      <!-- Critic verdicts heatmap -->
      <critic-heatmap iterations={iterations} critics={critics} />
    </right-panel>
  </grid>
  
  <footer>
    <!-- Disclaimer + audit trail link -->
    <disclaimer />
    <audit-link url={postgres_run_id} />
  </footer>
</dashboard>
```

#### Key Dashboard Components

**A. Performance Chart with Trade Overlay**

```javascript
// Plot EOD close as candlestick; overlay win/loss trades as markers
// Hover trade → tooltip: entry/exit price, return %, holding days, regime
// Click regime button to filter chart to specific regime
```

**B. Iteration Timeline**

```javascript
// Vertical swimlane showing iteration 1, 2, 3, ...
// Each iteration shows: candidates count, top-performing spec, critic verdicts
// Click iteration → expand to show all critics' issues and required_changes
```

**C. Regime Performance Heatmap**

```javascript
// Rows: Bull / Sideways / Bear
// Columns: Return %, Max DD %, Trade Count, Avg Trade Return, Win Rate
// Cell color: green (strong), yellow (marginal), red (weak)
// Helps visualize regime dependence at a glance
```

**D. Critic Verdict Timeline**

```javascript
// One row per critic per iteration
// Verdict badge: green (accept), yellow (revise), red (reject)
// Hover badge → tooltip: issues + required_changes (sourced from Critique.issues, Critique.required_changes)
```

**E. Candidate Proposal Scatter**

```javascript
// X-axis: Total Return %
// Y-axis: Max Drawdown %
// Point color: Train vs. Validation (teal = train, amber = validation)
// Point size: Trade Count (larger = more active)
// Iteration number as label; hover → full StrategySpec details
// Red dashed line at "rejection threshold" (e.g., DD > 15%)
```

### 4.3 Dashboard Generation

```python
def render_council_dashboard(
    result: CouncilResult,
    eod_data: pd.DataFrame,
    output_dir: Path | None = None,
) -> Path:
    """
    Render an interactive HTML dashboard from a CouncilResult.
    
    Returns path to the saved .html file.
    """
    
    dashboard_html = _build_dashboard_html(
        result=result,
        eod_data=eod_data,
        theme="industrial_dark",
    )
    
    output_path = (output_dir or Path("reports/strategy_council")) / f"dashboard_{result.symbol}_{result.as_of.strftime('%Y%m%d_%H%M%S')}.html"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(dashboard_html)
    
    return output_path
```

### 4.4 Postgres Storage Extension

Add new tables to persist rich reporting artifacts:

```sql
CREATE TABLE strategy_council.dashboards (
    dashboard_id UUID PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES strategy_council.runs(run_id),
    html_content TEXT NOT NULL,
    regime_slices JSONB,  -- {regime: {return_pct, max_dd, trade_count, ...}, ...}
    trade_attribution JSONB,  -- [{trade_id, entry_date, exit_date, return_pct, regime}, ...]
    created_at TIMESTAMPTZ DEFAULT now(),
    FOREIGN KEY (run_id) REFERENCES strategy_council.runs(run_id)
);

CREATE TABLE strategy_council.trade_detail (
    trade_id UUID PRIMARY KEY,
    run_id UUID NOT NULL,
    strategy_id VARCHAR,
    entry_date DATE,
    exit_date DATE,
    entry_price NUMERIC,
    exit_price NUMERIC,
    return_pct NUMERIC,
    regime VARCHAR,
    holding_days INT,
    created_at TIMESTAMPTZ DEFAULT now(),
    FOREIGN KEY (run_id) REFERENCES strategy_council.runs(run_id)
);
```

---

## 5. Updated Data Flow

```
                    build_evidence_pack (enriched)
                            │
                  ┌─────────────────────────────┐
                  ▼                             ▼
            [optional: Fundamentals,      [time-ordered]
             Sentiment, Regime,             Splits
             Microstructure,             (train/val/test)
             Factor Exposure]                │
                  │                          │
                  └──────────┬───────────────┘
                             ▼
                  Iteration Loop (1..N):
           ┌────────────────────────────────────────┐
           │ 1. Strategist propose (uses evidence)  │
           │ 2. Run candidates on train + val       │
           │ 3. Advanced Critics evaluate           │
           │    - Drawdown, Correlation,            │
           │      Factor-Based, Regime-Conditional  │
           │ 4. Merge critic issues → revision      │
           │ 5. Store CouncilIteration              │
           └────────────────────────────────────────┘
                             │
                  Lock best validation candidate
                             │
                  ┌──────────┴──────────┐
                  ▼                     ▼
         One-shot test on          Dashboard + Markdown
         test split                 render + persist
                  │                     │
                  └──────────┬──────────┘
                             ▼
          [Recommendation + Full Audit Trail]
          - Postgres: runs, iterations, candidates,
            critiques, split_results, dashboards, trade_detail
          - Markdown report
          - Interactive HTML dashboard
```

---

## 6. Configuration & Tuning

New fields in `CouncilConfig`:

```python
@dataclass(frozen=True)
class CouncilConfig:
    # Original fields
    symbol: str
    horizons: tuple[int, ...]
    iterations: int
    max_candidates: int
    initial_capital: float
    from_date: str | None = None
    validation_from: str | None = None
    test_from: str | None = None
    allowed_strategies: tuple[str, ...] = field(
        default=(
            "stage2", "supertrend_continuation", "rsi_pullback_stage2", "52w_high", "vcp",
            "stage2_bull_only", "stage2_bear_only",
            "momentum_value_blend", "quality_growth_pivot",
        )
    )
    recommendation_threshold: str = "validation_then_test"
    
    # NEW: Enhanced features
    include_enrichment: bool = True  # Fetch fundamentals, sentiment, regime, etc.
    use_advanced_critics: bool = True  # Use drawdown, correlation, factor, regime critics
    use_rule_composer: bool = True  # Enable combinatorial rule composition
    use_ml_discovery: bool = False  # (Experimental) ML-assisted candidate ranking
    render_dashboard: bool = True  # Generate interactive HTML dashboard
    
    # Critic thresholds
    max_drawdown_threshold_pct: float = 15.0
    train_val_corr_threshold: float = 0.3
    factor_r_squared_threshold: float = 0.8
    regime_performance_spread_threshold: float = 15.0
```

---

## 7. Backward Compatibility

All enhancements are **opt-in** via `CouncilConfig` flags:

- `include_enrichment=False` → no evidence enrichment; evidence pack remains minimal.
- `use_advanced_critics=False` → only rule-based data-leakage and risk critics run.
- `use_rule_composer=False` → deterministic strategist proposes fixed specs as before.
- `render_dashboard=False` → only Markdown report generated.

Existing code that calls `run_strategy_council` with default config continues to work unchanged. The system gracefully degrades if enrichment sources unavailable.

---

## 8. Testing & Validation

### 8.1 New Test Suites

- `test_evidence_enrichment.py` — Fundamental/sentiment/regime/factor loads; fallback handling.
- `test_critics_advanced.py` — Each critic verdict logic; interaction with evidence; scoring consistency.
- `test_strategy_generator.py` — Rule composer; atomic rule combination; ML discovery ranking (mock).
- `test_dashboard_render.py` — HTML structure, required sections, interactive JS logic.

### 8.2 Scenario Testing

| Scenario | Expected Behavior |
|---|---|
| Sentiment unavailable | Stored as `{}` in evidence; critics skip sentiment-based checks; report notes "missing". |
| Regime detection fails | Recorded in `source_trail`; regime-conditional critic skips checks. |
| ML discovery ranking fails | Falls back to deterministic strategist proposals. |
| Dashboard HTML too large | Separate large JSON data into separate `<script>` tag; lazy-load trade detail. |
| All critics reject all candidates | Deterministic strategist fallback ensures iteration continues. |

---

## 9. Deployment & Operations

### 9.1 Environment Variables (New)

| Variable | Default | Purpose |
|---|---|---|
| `AGENT_ADDA_FUNDAMENTAL_DATA_SOURCE` | `"postgres"` | `"postgres"` or `"stubs"` (for dev/test). |
| `AGENT_ADDA_SENTIMENT_SOURCES` | `"news,social,vix_proxy"` | Comma-separated list of enabled sentiment feeds. |
| `AGENT_ADDA_FACTOR_MODEL_PATH` | `None` | Path to pre-trained XGBoost factor loadings model. |
| `AGENT_ADDA_MICROSTRUCTURE_TICK_DIR` | `None` | Directory of tick-level CSV files (optional). |
| `AGENT_ADDA_ML_DISCOVERY_MODEL_PATH` | `None` | Path to strategy ranking model; if absent, random baseline. |
| `AGENT_ADDA_DASHBOARD_THEME` | `"industrial_dark"` | `"industrial_dark"`, `"light_minimal"`, `"maximalist"`. |

### 9.2 Database Schema Migration

```sql
-- Run via schema migration system
-- Adds enriched evidence tables, trade_detail, dashboards
-- Creates indexes on (symbol, created_at), (run_id, phase), (strategy_id, horizon)
```

### 9.3 Sample Run

```python
from strategy_council import run_strategy_council, CouncilConfig, build_evidence_pack

config = CouncilConfig(
    symbol="INFY",
    horizons=(5, 10, 20),
    iterations=3,
    max_candidates=5,
    include_enrichment=True,
    use_advanced_critics=True,
    use_rule_composer=True,
    render_dashboard=True,
)

eod_data = load_eod_data("INFY")
evidence = build_evidence_pack("INFY", include_enrichment=True)

result = run_strategy_council(
    eod_data,
    evidence=evidence,
    config=config,
)

# Artifacts generated:
# - strategy_council_INFY_20240125_143052.md
# - dashboard_INFY_20240125_143052.html
# - Postgres: runs, iterations, candidates, critiques, split_results, trade_detail, dashboards
```

---

## 10. Design Rationale

### Evidence Enrichment

**Why optional?** Enterprise data pipelines often have gaps. Recording misses explicitly (`source_trail`, `missing`) lets critics and reports adapt rather than fail. Critics consume only what's available; reports highlight gaps.

### Advanced Critics

**Why multiple critics?** Different critics catch different failure modes: drawdown catches tail risk, correlation catches overfitting, factor-based catches spurious alpha, regime-conditional catches fragility. Combined, they form a coherent risk management frame.

### Rule Composition

**Why not pure ML generation?** ML-generated rules are opaque and hard to audit. Atomic rules are interpretable; composition is verifiable. ML can *rank* compositions (optional `use_ml_discovery`), but interpretation remains transparent.

### Dashboards

**Why HTML + Postgres?** Markdown is great for static reports; dashboards need interactivity. HTML with embedded JSON (via `<script>`) avoids external API calls. Postgres stores raw metrics for replay and ad-hoc queries by operations teams.

---

## 11. Future Extensions

- **Agent Adda Publication**: Publish council results as structured knowledge objects via CANON.
- **Talk2Data Integration**: Natural language queries on strategy results ("Show me all strategies that beat the market in bull regimes").
- **ShunyaAI Orchestration**: Chain multiple symbols' councils in parallel; aggregate portfolio-level recommendations.
- **Portfolio Council**: Multi-symbol optimization; position sizing across correlated candidates.
- **Live Adaptation**: Re-run council weekly; compare results to actual market performance; feedback loop for model calibration.

---

## 12. Glossary (Additions)

- **Enrichment** — Optional data feeds (fundamentals, sentiment, regime, microstructure, factors) merged into evidence pack.
- **Atomic Rule** — A primitive entry/exit/risk condition (e.g., "EMA bullish", "RSI oversold").
- **Rule Composer** — Combines atomic rules into full StrategySpec candidates.
- **Factor R²** — Fraction of strategy returns explained by known factors (momentum, value, volatility, etc.).
- **Regime-Conditional** — Performance metric sliced by market regime (bull/sideways/bear).
- **Attribution** — Breakdown of strategy performance by trade, regime, or factor.
- **Dashboard** — Interactive HTML visualization of council result with drill-down and filtering.