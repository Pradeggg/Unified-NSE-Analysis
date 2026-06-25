# Named Strategy Modules Design

**Date:** 2026-06-25  
**Project:** Agent Adda / Unified NSE Analysis  
**Status:** Design approved for planning review  

## Purpose

Agent Adda already has strong strategy ingredients: Weinstein Stage 2 scans, CAN SLIM prompts, VCP and Darvas-style setup labels, forensic/fundamental scoring, signal-effectiveness backtests, regime cross-walks, and intraday decision gates. The next step is to formalize these ingredients into named strategy modules that can be backtested, compared, reported, and used consistently in EOD and live workflows.

The goal is not to claim exact replication of any author or trader. The goal is to create auditable Agent Adda interpretations of well-known frameworks, with explicit rules, historical evidence, no-trade filters, and current candidate lists.

## Scope

This feature will create a first-class strategy module layer for EOD research.

It will:

- Define named strategy modules with stable IDs, display names, source inspiration, rule descriptions, setup mappings, and gating logic.
- Reuse the existing EOD signal-effectiveness pipeline instead of building a parallel backtester.
- Produce module-level backtest summaries, current candidates, and comprehensive Markdown/HTML reports.
- Preserve the existing signal-effectiveness reports and CSV outputs.
- Add tests for module registry integrity, setup-to-module mapping, aggregation behavior, and report generation.

It will not:

- Execute live trades.
- Add broker integration.
- Claim SEBI research-adviser status or investment advice.
- Build a complete intrinsic valuation engine.
- Build a production-grade portfolio optimizer.
- Fully reproduce proprietary or subjective parts of O'Neil, Minervini, Wyckoff, Graham, Fisher, Lynch, or Dorsey methodologies.

## Strategy Modules

### 1. O'Neil-Inspired CAN SLIM Growth Breakout

**Module ID:** `oneil_canslim_growth_breakout`

**Purpose:** Identify growth stocks where earnings/fundamental strength, relative strength, market direction, Stage 2 structure, breakout behavior, and volume confirmation align.

**Primary inputs:**

- CAN SLIM score or available CAN SLIM components.
- Stage 2 / trend state.
- Relative strength versus Nifty 500.
- 20-day or 50-day breakout with volume.
- Market regime and breadth.
- Fundamental score, sales/PAT growth, ROE/ROCE, institutional/promoter context when available.

**Mapped setup families:**

- `relative_strength_breakout`
- `breakout_20_volume`
- `breakout_50_volume`
- `combo_rs_volume_sector`
- `combo_momentum_quality`
- `combo_risk_filtered_breakout`

**Decision preference:** Trade candidate only when growth/quality, RS, volume, breadth, and cost profile are supportive.

### 2. Weinstein Stage 2 Leader

**Module ID:** `weinstein_stage2_leader`

**Purpose:** Promote stocks in Weinstein Stage 2 uptrends with rising moving averages, relative strength, sector leadership, and breakout or pullback-reclaim behavior.

**Primary inputs:**

- Stage classification.
- EMA/SMA stack and slope.
- Relative strength.
- Sector rotation rank.
- Supertrend / trend confirmation.
- Breakout or pullback-reclaim setup.

**Mapped setup families:**

- `stage2_supertrend_volume`
- `combo_stage2_supertrend_breakout`
- `ema20_pullback_reclaim`
- `combo_ema_reclaim_regime`
- `relative_strength_breakout`
- `combo_rs_volume_sector`

**Decision preference:** Prefer Stage 2 leaders with broad-positive breadth, clean liquidity, and retest/hold confirmation.

### 3. Minervini-Style SEPA / VCP

**Module ID:** `minervini_sepa_vcp`

**Purpose:** Capture high relative-strength trend-template stocks forming volatility contraction or tight-range breakouts.

**Primary inputs:**

- Stage 2 / trend template proxy.
- VCP/tight-range proxy from `scores.stage2_vcp_picks` or labelled setup data.
- Relative strength.
- Volume contraction/expansion where available.
- ADR and liquidity floors.
- Sector confirmation.

**Mapped setup families:**

- `vcp_breakout_proxy`
- `combo_vcp_volume_sector`
- `relative_strength_breakout`
- `combo_momentum_quality`

**Decision preference:** Require clean contraction plus breakout/retest confirmation. Downgrade generic VCP proxies without enough contraction evidence.

### 4. Darvas Box Breakout

**Module ID:** `darvas_box_breakout`

**Purpose:** Identify compact box breakouts where price clears a recent range with volume and enough forward reward relative to risk.

**Primary inputs:**

- Compact 20-day or configurable box range.
- Breakout above box high.
- Volume confirmation.
- ATR/ADR adequacy.
- Stop below box or recent swing support.

**Mapped setup families:**

- `darvas_box_breakout`
- `breakout_20_volume`
- `breakout_50_volume`

**Decision preference:** Promote only when box range is meaningful, liquidity is sufficient, and cost-adjusted expectancy is acceptable.

### 5. Graham Quality Value With Technical Confirmation

**Module ID:** `graham_quality_value_confirmation`

**Purpose:** Identify financially strong, lower-risk names that also have a technical confirmation layer before entering.

**Primary inputs:**

- Valuation proxies where available.
- Debt/equity, cash-flow quality, Piotroski, Altman, Beneish.
- Stable profitability and earnings quality.
- Stage 1-to-Stage 2 transition or EMA reclaim.
- Avoidance of distress and forensic flags.

**Mapped setup families:**

- `ema20_pullback_reclaim`
- `combo_ema_reclaim_regime`
- `combo_momentum_quality`
- `combo_risk_filtered_breakout`

**Decision preference:** Report as conservative watch/trade candidate only when valuation/fundamental quality is clean and technical confirmation exists.

### 6. Fisher Quality Growth

**Module ID:** `fisher_quality_growth`

**Purpose:** Identify higher-quality growth names with strong sales/PAT trends, margins, ROE/ROCE, cash-flow quality, and constructive technical structure.

**Primary inputs:**

- Revenue and PAT growth.
- Margin trend and profitability.
- ROE/ROCE.
- Cash-flow quality.
- Promoter/institutional context.
- Stage 2 / relative strength / sector confirmation.

**Mapped setup families:**

- `combo_momentum_quality`
- `combo_rs_volume_sector`
- `relative_strength_breakout`
- `ema20_pullback_reclaim`

**Decision preference:** Prefer quality-growth names with controlled valuation/risk flags and confirmed trend behavior.

### 7. Wyckoff Accumulation / Breakout Proxy

**Module ID:** `wyckoff_accumulation_breakout_proxy`

**Purpose:** Convert available base-building, support/resistance, volume, and RS evidence into a practical accumulation-to-breakout proxy.

**Primary inputs:**

- Base-building or tight-range state.
- Support/resistance structure.
- Volume behavior.
- RS improvement.
- Stage 1-to-Stage 2 transition or breakout from base.

**Mapped setup families:**

- `vcp_breakout_proxy`
- `darvas_box_breakout`
- `relative_strength_breakout`
- `combo_vcp_volume_sector`

**Decision preference:** Treat as watch/retest first unless breakout and volume confirmation are strong.

### 8. Agent Adda Composite Edge

**Module ID:** `agent_adda_composite_edge`

**Purpose:** Combine the historically strongest Agent Adda evidence into a pragmatic decision-engine module.

**Primary inputs:**

- Best setup families by gross and net expectancy.
- Regime, breadth, VIX, liquidity, cost profile, and F&O gates.
- Current candidate queue and strategy lab context.
- Current no-trade filters.

**Mapped setup families:**

- `combo_rs_volume_sector`
- `combo_momentum_quality`
- `ema20_pullback_reclaim`
- `relative_strength_breakout`
- `combo_risk_filtered_breakout`
- `combo_vcp_volume_sector`

**Decision preference:** Prefer fewer candidates with survivable net expectancy, broad-positive breadth, acceptable cost, and clean liquidity.

## Architecture

### New Module Registry

Create `terminal/strategy_modules.py`.

Responsibilities:

- Define `StrategyModule` dataclass.
- Provide `STRATEGY_MODULES`.
- Validate unique IDs and setup mappings.
- Map labelled setup events to one or more modules.
- Aggregate setup summaries into module summaries.
- Build current candidate tables by module.

The registry will contain rule metadata. It will not read PostgreSQL directly and will not render reports. This keeps it testable.

### Research Pipeline Integration

Modify `scripts/research_signal_effectiveness.py`.

Responsibilities:

- Import the module registry.
- After existing setup and combo summaries are generated, aggregate module-level metrics.
- Attach module IDs to labelled events when their setup family maps to a module.
- Emit module-level CSV outputs.
- Generate Markdown and HTML report sections for named strategy modules.
- Preserve all existing outputs and command-line behavior.

### Report Builder

Create `scripts/build_named_strategy_modules_report.py` only if the existing research script becomes too large. The preferred first implementation is to extend the existing research script minimally, then extract report rendering only if needed.

Output paths:

- `reports/strategy_modules/named_strategy_modules_<stamp>.md`
- `reports/strategy_modules/named_strategy_modules_<stamp>.html`
- `reports/strategy_modules/module_summary_<stamp>.csv`
- `reports/strategy_modules/module_candidates_<stamp>.csv`
- `reports/latest/named_strategy_modules.md`
- `reports/latest/named_strategy_modules.html`
- `reports/latest/named_strategy_module_summary.csv`
- `reports/latest/named_strategy_module_candidates.csv`

### Current Candidates

Use the existing latest candidate table from signal-effectiveness research and map rows to modules through setup families.

Current candidate report columns:

- module ID
- module name
- symbol
- setup
- entry variant
- latest close
- trigger context
- stop context
- target context
- gross expectancy
- net expectancy
- cost profile
- regime read
- decision gate
- missing evidence

### Decision Gates

Each module report must surface gates, not only scores:

- `BLOCK`
- `WATCH`
- `WAIT_RETEST`
- `HALF_SIZE_CANDIDATE`
- `TRADE_CANDIDATE`

Gate rules will initially be deterministic:

- Block if net expectancy is materially negative and no favorable regime bucket exists.
- Watch if gross expectancy is positive but net expectancy is weak.
- Wait retest if retest variant is materially better or setup is breakout-sensitive.
- Half size if module has favorable regime/cost bucket but aggregate net edge is marginal.
- Trade candidate if module and current candidate both have positive net/regime evidence and no missing critical evidence.

Exact numeric thresholds will be defined in implementation tests using the existing signal-effectiveness columns:

- positive net expectancy: `net_expectancy_r > 0`
- marginal net expectancy: `-0.05 <= net_expectancy_r <= 0`
- weak net expectancy: `net_expectancy_r < -0.05`
- positive net profit factor: `net_profit_factor > 1.0`
- minimum evidence quality: `sample_quality in {"higher", "medium"}` unless explicitly shown as provisional.

## Data Flow

1. Load labelled setup events through the existing signal-effectiveness pipeline.
2. Label each event with one or more module IDs based on setup family and available evidence.
3. Aggregate events by module ID.
4. Join setup-level, regime-level, cost-level, execution-variant, and current-candidate summaries.
5. Compute module decision gates.
6. Write CSV outputs.
7. Render Markdown and HTML reports.
8. Copy latest outputs to `reports/latest`.

## Error Handling

- Missing optional fields should produce `missing_evidence`, not crashes.
- Missing module mappings should leave the event unmapped and count it in an unmapped summary.
- Empty current candidates should still produce module summaries.
- Missing F&O data should downgrade F&O-specific gates but not block non-F&O modules.
- Unknown setup names should be reported in a diagnostics section.

## Testing

Tests will be focused and data-light:

- Registry has unique module IDs.
- Each module has display name, inspiration, mapped setups, rules, and gate notes.
- Known setup families map to expected modules.
- Unknown setup family returns no module and does not crash.
- Synthetic setup summaries aggregate correctly by module.
- Gate classification handles positive, marginal, weak, and provisional evidence.
- Report rendering includes all module names, key metrics, current candidates, and disclaimers.
- Existing signal-effectiveness tests continue to pass.

## Report Quality Bar

Each module report section must include:

- Strategy inspiration and honest interpretation caveat.
- Rule specification.
- What evidence Agent Adda actually has.
- What evidence is missing.
- Backtest metrics.
- Regime and cost survivability.
- Current candidates.
- Failure modes.
- No-trade conditions.
- Research-only disclaimer.

## Open Implementation Choices

These choices are fixed for the first implementation:

- Start with EOD strategy modules, not intraday modules.
- Use the current `research_signal_effectiveness.py` dataset and assumptions.
- Use existing 10-session, 2R, ATR/recent-low stop framework.
- Produce Markdown and HTML reports.
- Keep named modules as Agent Adda interpretations of public frameworks.

Later phases can add:

- Intraday named modules.
- Walk-forward optimization.
- Portfolio allocation by module.
- Richer valuation workflows for Graham/Fisher/Dorsey-style analysis.
- A first-class Wyckoff phase detector.
- A production-grade SEPA trend-template detector.

## Success Criteria

The first version is successful when:

- Running the signal-effectiveness pipeline produces named module outputs.
- Every module has a backtest summary and decision gate.
- Current candidates are grouped by module.
- The Markdown and HTML reports are written to `reports/latest`.
- Tests prove registry, mapping, gating, and report rendering behavior.
- Existing EOD strategy reports remain intact.

## Source Trail

Existing evidence used for this design:

- `scripts/research_signal_effectiveness.py`
- `reports/latest/signal_effectiveness.md`
- `reports/latest/agent_adda_eod_signal_effectiveness_research_paper_20260622.md`
- `reports/latest/stage2_tracker.html`
- `reports/latest/top_picks.html`
- `terminal/forensics.py`
- `scripts/materialize_stage2_vcp_picks.py`
- `terminal/live_intraday_alerts.py`

## Disclaimer

This design is for research and learning only. It does not create investment advice, trading advice, portfolio advice, or a recommendation to buy, sell, hold, short, or transact in any security or derivative. Agent Adda is not SEBI registered.
