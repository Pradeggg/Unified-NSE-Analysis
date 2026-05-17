# Full Integration Guide

Complete walkthrough of integrating all four enhancement layers into `council.py`:

1. Evidence Enrichment
2. Advanced Critics
3. Strategy Generation
4. Dashboard Reporting

Shows data flow, code patterns, and configuration.

> See also: [`../../docs/STRATEGY_COUNCIL_DESIGN.md`](../../docs/STRATEGY_COUNCIL_DESIGN.md) for the current implementation baseline and [`../../docs/STRATEGY_COUNCIL_ENHANCEMENTS.md`](../../docs/STRATEGY_COUNCIL_ENHANCEMENTS.md) for the enhancement specification this guide operationalises.

---

## 1. Integration Architecture

Complete data flow (Enhanced Council):

```
Input: symbol, eod_data, config
     ↓
┌────────────────────────────────────────┐
│ 1. EVIDENCE LAYER                      │
├────────────────────────────────────────┤
│ build_evidence_pack()                  │
│   → Technical (OHLCV, stats)           │
│   → Enrichment (if enabled):           │
│       • Fundamentals (P/E, ROE, etc)   │
│       • Sentiment (news, social, VIX)  │
│       • Regime (bull/bear/sideways)    │
│       • Microstructure (spread, depth) │
│       • Factor exposure (momentum...)  │
│   → Missing tracking + source trail    │
└────────────────────────────────────────┘
     ↓ evidence_pack
┌────────────────────────────────────────┐
│ 2. COUNCIL ITERATION LOOP              │
├────────────────────────────────────────┤
│ For each iteration (1..N):             │
│   a) Strategist proposes candidates    │
│      (LLM + rule-based generator)      │
│   b) Backtest on train/val splits      │
│   c) Critics evaluate:                 │
│      • RuleBasedDataLeakageCritic      │
│      • RuleBasedRiskCritic             │
│      • DrawdownCritic (NEW)            │
│      • CorrelationCritic (NEW)         │
│      • FactorBasedCritic (NEW)         │
│      • RegimeConditionalCritic (NEW)   │
│   d) Merge critique feedback           │
│   e) Lock best candidate by val score  │
│      (penalized by confidence_delta)   │
└────────────────────────────────────────┘
     ↓ result
┌────────────────────────────────────────┐
│ 3. REPORTING & DASHBOARDS              │
├────────────────────────────────────────┤
│ Generate outputs:                      │
│   • Markdown report (iteration summary)│
│   • HTML dashboard (interactive viz)   │
│   • Postgres persistence (audit trail) │
└────────────────────────────────────────┘
     ↓
Output: recommendation (TRADE_RESEARCH | WAIT | NO_TRADE)
```

---

## 2. Modified `council.py` Structure

### Old structure

```
run_strategy_council(eod_data, evidence=None, config=..., strategist=None)
    ├─ build_evidence_pack()  [basic]
    ├─ strategist.propose()   [LLM only]
    ├─ iterate:
    │   ├─ Run backtest
    │   ├─ Critics (2 base critics)
    │   └─ Merge feedback
    └─ Return result
```

### New structure

```
run_strategy_council(eod_data, evidence=None, config=..., strategist=None, critics=None)
    ├─ build_evidence_pack(include_enrichment=True)  [enriched]
    ├─ strategist (hybrid: LLM + rules)
    ├─ critics (6 critics: 2 base + 4 advanced)
    ├─ iterate:
    │   ├─ CompositeStrategist.propose()
    │   │   ├─ LLM proposals (40% by default)
    │   │   └─ RuleComposer proposals (60%)
    │   ├─ Run backtest
    │   ├─ Critics.critique() [all 6]
    │   └─ Merge feedback (aggregated)
    ├─ Lock best candidate
    ├─ One-shot test
    ├─ Generate dashboard
    └─ Return result + dashboard_path
```

---

## 3. Code Integration Patterns

### Pattern 1 — Import all enhancements

```python
# At top of council.py
from backtesting.strategy_council.evidence_enrichment import (
    build_enriched_evidence_pack,
)
from backtesting.strategy_council.critics_advanced import (
    build_advanced_critics,
    merge_critique_issues,
)
from backtesting.strategy_council.strategy_generator import (
    generate_candidates_via_rules,
    CompositeStrategist,
)
from backtesting.strategy_council.dashboard_generator import (
    write_dashboard,
)
```

### Pattern 2 — Evidence enrichment

```python
def run_strategy_council(..., include_enrichment=True, ...):
    # Old:
    # evidence = build_evidence_pack(symbol, eod_data)

    # New:
    if include_enrichment:
        evidence = build_enriched_evidence_pack(
            symbol,
            eod_data,
            conn=postgres_conn,        # Optional; for fundamentals
            csv_fallback_dir=None,
            use_sentiment=True,
            use_factor_model=True,
        )
    else:
        evidence = build_evidence_pack(symbol, eod_data)

    logger.info(f"Evidence freshness: {evidence.freshness}")
    logger.info(f"Missing fields: {evidence.missing}")
```

### Pattern 3 — Advanced critics

```python
def run_strategy_council(..., use_advanced_critics=True, ...):
    critics = (
        RuleBasedDataLeakageCritic(),
        RuleBasedRiskCritic(),
    )

    if use_advanced_critics:
        advanced = build_advanced_critics(
            eod_df=eod_data,
            max_drawdown_threshold_pct=config.max_drawdown_threshold_pct,
            train_val_corr_threshold=config.train_val_corr_threshold,
            factor_r_squared_threshold=config.factor_r_squared_threshold,
            regime_performance_spread_threshold=config.regime_performance_spread_threshold,
        )
        critics = critics + advanced

    logger.info(f"Initialized {len(critics)} critics")
    return critics
```

### Pattern 4 — Hybrid strategy generation

```python
def run_strategy_council(...):
    if strategist is None:
        strategist = CompositeStrategist(
            llm_strategist=JSONLLMStrategist(model="gpt-4o"),
            use_rules=True,
            rule_method="sampled",
            llm_ratio=config.llm_ratio,        # Default 0.4
            use_ranking=True,
            ranking_model_path=config.ranking_model_path,
        )

    return strategist
```

### Pattern 5 — Iteration loop (modified)

```python
for iteration_num in range(config.iterations):
    # Propose candidates
    candidates = strategist.propose(
        evidence=evidence,
        config=config,
        prior_feedback=prior_feedback,
    )

    # Backtest (unchanged)
    train_results, val_results = backtest_candidates(...)

    # Critics evaluate (now includes advanced)
    critiques = []
    for critic in critics:
        critique = critic.critique(
            candidates=candidates,
            train_results=train_results,
            validation_results=val_results,
        )
        critiques.append(critique)

    # Merge feedback (aggregated verdicts + required_changes)
    prior_feedback = merge_critique_issues(critiques)
    logger.info(f"Iteration {iteration_num}: {prior_feedback}")

    # Lock best candidate
    best_idx = select_best_candidate(val_results, critiques)
    locked_strategy = candidates[best_idx]
```

### Pattern 6 — Dashboard generation

```python
# After council completes
result = CouncilResult(
    symbol=config.symbol,
    recommendation=recommendation,
    locked_strategy=locked_strategy,
    iterations=iteration_history,
    test_results=test_results,
    evidence=evidence,
    rationale=rationale,
)

dashboard_path = write_dashboard(
    result,
    eod_data,
    output_dir=Path("reports/dashboards"),
)

logger.info(f"Dashboard: {dashboard_path}")
return result, dashboard_path
```

### Pattern 7 — Configuration

```python
@dataclass(frozen=True)
class CouncilConfig:
    # Existing fields
    symbol: str
    horizons: Tuple[int, ...] = (5, 10, 20)
    iterations: int = 3
    max_candidates: int = 5

    # NEW: Enhancement flags
    include_enrichment: bool = True
    use_advanced_critics: bool = True
    use_rule_composition: bool = True
    use_strategy_ranking: bool = True

    # NEW: Thresholds for critics
    max_drawdown_threshold_pct: float = 15.0
    train_val_corr_threshold: float = 0.3
    factor_r_squared_threshold: float = 0.8
    regime_performance_spread_threshold: float = 15.0

    # NEW: Strategy generation
    rule_generation_method: str = "sampled"   # or "exhaustive"
    rule_llm_ratio: float = 0.4               # 40% LLM, 60% rules
    ranking_model_path: Optional[Path] = None
```

---

## 4. Complete Integration Example

Minimal complete example (wired together):

```python
from backtesting.strategy_council import run_strategy_council
from backtesting.strategy_council.types import CouncilConfig
import pandas as pd

# Load data
eod_data = pd.read_csv("infy_eod.csv", index_col="date", parse_dates=True)

# Configure with all enhancements
config = CouncilConfig(
    symbol="INFY",
    include_enrichment=True,          # ✓ Evidence enrichment
    use_advanced_critics=True,        # ✓ 4 advanced critics
    use_rule_composition=True,        # ✓ Rule-based generation
    use_strategy_ranking=True,        # ✓ ML ranking (optional)
    rule_generation_method="sampled",
    rule_llm_ratio=0.4,
    iterations=3,
    max_candidates=5,
)

# Run council
result, dashboard_path = run_strategy_council(
    eod_data,
    config=config,
)

# Outputs
print(f"Recommendation: {result.recommendation}")
print(f"Dashboard: {dashboard_path}")

# Open dashboard in browser
import webbrowser
webbrowser.open(str(dashboard_path))

# Verify all enhancements
assert result.evidence.regime is not None          # ✓ Enrichment
assert len(result.iterations[0].critiques) >= 6    # ✓ Critics
assert "rule_composer" in str(result.iterations)   # ✓ Generator
# Dashboard file exists
```

---

## 5. Execution Trace

Expected console output for a full integration run:

```
[2024-01-15 14:30:00] INFO: Starting council run for INFY

[2024-01-15 14:30:01] INFO: Building enriched evidence pack
[2024-01-15 14:30:02] INFO: Evidence freshness: {'eod': True, 'regime': True, 'sentiment': True, 'fundamental': False}
[2024-01-15 14:30:02] INFO: Missing fields: ['fundamental', 'microstructure']

[2024-01-15 14:30:03] INFO: Initialized 6 critics (2 base + 4 advanced)

[2024-01-15 14:30:03] INFO: Starting iteration 1/3
[2024-01-15 14:30:04] INFO: Strategist proposed 5 candidates (2 LLM, 3 rules)
[2024-01-15 14:30:15] INFO: Backtest complete (5 specs × 3 splits = 15 backtests)
[2024-01-15 14:30:16] INFO: Critics evaluating:
[2024-01-15 14:30:16] INFO:   ✓ DataLeakageCritic: 5 ACCEPT
[2024-01-15 14:30:16] INFO:   ✓ RiskCritic: 5 ACCEPT
[2024-01-15 14:30:17] INFO:   ✓ DrawdownCritic: 4 ACCEPT, 1 REVISE (threshold 15%)
[2024-01-15 14:30:17] INFO:   ✓ CorrelationCritic: 5 ACCEPT (train/val corr > 0.3)
[2024-01-15 14:30:18] INFO:   ✓ FactorBasedCritic: 3 ACCEPT, 2 REVISE (R² > 0.8)
[2024-01-15 14:30:19] INFO:   ✓ RegimeConditionalCritic: 4 ACCEPT, 1 REVISE
[2024-01-15 14:30:19] INFO: Merged feedback: verdicts=[accept, accept, revise, accept, accept]
[2024-01-15 14:30:19] INFO: Issues: ["High drawdown on spec_2", "Factor-dependent on spec_4"]
[2024-01-15 14:30:19] INFO: Best candidate: spec_3 (val_return: 7.2%)

[2024-01-15 14:30:19] INFO: Starting iteration 2/3
[2024-01-15 14:30:20] INFO: Strategist proposed 5 candidates (incorporating feedback)
[2024-01-15 14:30:31] INFO: Critics evaluating...
[2024-01-15 14:30:33] INFO: Best candidate: spec_8 (val_return: 7.5%)

[2024-01-15 14:30:33] INFO: Starting iteration 3/3
[2024-01-15 14:30:34] INFO: Strategist proposed 5 candidates
[2024-01-15 14:30:45] INFO: Critics evaluating...
[2024-01-15 14:30:47] INFO: Best candidate: spec_12 (val_return: 7.8%)

[2024-01-15 14:30:47] INFO: Locked strategy: spec_12 (momentum_value_blend)
[2024-01-15 14:30:48] INFO: One-shot test: +6.8% return, 70% win rate

[2024-01-15 14:30:48] INFO: Generating dashboard...
[2024-01-15 14:30:49] INFO: Wrote dashboard to reports/dashboards/dashboard_INFY_20240115_143049.html

[2024-01-15 14:30:50] INFO: Council complete
✅ TRADE_RESEARCH
```

---

## 6. Backward Compatibility

All enhancements are **optional** and backward-compatible:

```python
# Disable enrichment (use old minimal evidence)
config.include_enrichment = False

# Use only base critics (skip advanced)
config.use_advanced_critics = False

# Use only LLM proposals (skip rules)
config.use_rule_composition = False

# Disable dashboard (no HTML output)
config.skip_dashboard = True

# Old code continues to work unchanged
result = run_strategy_council(eod_data, config=old_config)
```

---

## 7. Testing Checklist

**Evidence Layer**

- [ ] Enriched evidence pack builds without errors
- [ ] Optional fields (regime, sentiment, etc.) populate correctly
- [ ] Missing fields tracked in `pack.missing`
- [ ] Source trail recorded for each enrichment

**Critics Layer**

- [ ] All 6 critics initialize successfully
- [ ] Each critic produces `Critique` with verdict + issues
- [ ] `confidence_delta` applied to best-candidate selection
- [ ] Feedback merged correctly

**Generator Layer**

- [ ] `RuleComposer` generates valid specs
- [ ] `CombinatorialExplorer` produces diverse combinations
- [ ] All generated specs pass DSL validation
- [ ] Specs integrate into iteration loop

**Dashboard Layer**

- [ ] Dashboard data extracted from result
- [ ] HTML renders without errors
- [ ] File written to `output_dir`
- [ ] Opens successfully in browser

**Full Integration**

- [ ] Council runs with all enhancements enabled
- [ ] All iterations complete successfully
- [ ] Result contains evidence, iterations, locked strategy
- [ ] Dashboard generated and linked
- [ ] Postgres persistence (if applicable)
- [ ] Metrics match expected ranges

**Backward Compatibility**

- [ ] Old code runs without changes (if enhancements disabled)
- [ ] Disabling features works correctly
- [ ] Error handling is graceful

---

## 8. Deployment Readiness

**Code quality**

- [ ] All imports present in `council.py`
- [ ] No circular dependencies
- [ ] Type hints for new functions
- [ ] Docstrings for public APIs
- [ ] Error handling for all external calls

**Performance**

- [ ] Evidence enrichment: < 500 ms
- [ ] Critics total: < 2 s
- [ ] Strategy generation: < 100 ms per iteration
- [ ] Dashboard generation: < 100 ms
- [ ] Full council run: < 30 s (3 iterations, 5 candidates)

**Monitoring**

- [ ] Logging at INFO level for key steps
- [ ] DEBUG logging for data flow
- [ ] Error logs with context
- [ ] Metrics exported (iteration count, run time, etc.)

**Documentation**

- [ ] Integration guide completed
- [ ] API reference for new modules
- [ ] Configuration examples
- [ ] Troubleshooting guide

**Testing**

- [ ] Unit tests for each layer
- [ ] Integration test for full flow
- [ ] Edge cases (missing data, failures)
- [ ] Performance tests

**Deployment**

- [ ] Staging environment tested
- [ ] Production config ready
- [ ] Rollback procedure documented
- [ ] Monitoring dashboards set up

---

## 9. Next Steps After Integration

**Phase 1 — Validation (Week 1)**

- Run integration tests on production data
- Verify all metrics match expectations
- Check dashboard rendering in various browsers
- Performance profiling

**Phase 2 — Staging (Week 2)**

- Deploy to staging environment
- Run multiple council rounds
- Gather performance metrics
- Gather user feedback

**Phase 3 — Production Canary (Week 3)**

- Enable for 10% of council runs
- Monitor for errors and performance degradation
- Collect metrics and logs
- Gradual rollout: 10% → 50% → 100%

**Phase 4 — Full Production (Week 4)**

- 100% of council runs use all enhancements
- Dashboard gallery/archive
- Feedback loops for improvements
- Optimization based on real usage

**Phase 5 — Enhancements (Ongoing)**

- New atomic rules
- ML-based ranking
- More critics (sentiment-based, drawdown types)
- Advanced dashboard features (export, sharing, ML)
