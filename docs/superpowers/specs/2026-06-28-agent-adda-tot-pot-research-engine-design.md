# Agent Adda ToT/PoT Research Engine Design

**Date:** 2026-06-28  
**Project:** Agent Adda / Unified NSE Analysis  
**Status:** Design approved for review  

## Purpose

Agent Adda should continue its research journey with a structured opinion-building workflow. The goal is not to read more books, papers, blogs, and GitHub repositories for general inspiration. The goal is to convert outside research into testable views about what Agent Adda should build, reject, watch, or study further.

This design defines a Tree of Thoughts and Program of Thoughts research engine for Agent Adda. It will compare competing research tracks, force explicit counterarguments, translate promising ideas into measurable tests, and produce an auditable opinion ledger.

## Core Thesis

The next edge is not more signals. The edge is a disciplined research loop:

`Read -> Branch -> Challenge -> Quantify -> Test -> Decide -> Track`

Tree of Thoughts is used to explore competing branches before forming a view. Program of Thoughts is used to turn those views into structured scoring, reproducible checks, and backtest-ready artifacts. Agent Adda's final opinion should come from evidence, critic gates, and implementation fit, not from a single narrative.

## Scope

This feature is a research methodology and future implementation target. It covers how Agent Adda should evaluate broad research ideas and strategy families before implementation.

It will:

- Evaluate research tracks using a repeatable ToT/PoT workflow.
- Compare trader-book systems, academic research, open-source quant platforms, practitioner blogs, and Agent Adda local capability fit.
- Produce an opinion ledger with explicit decisions: `BUILD_NOW`, `PROTOTYPE`, `RESEARCH_MORE`, `WATCH`, or `REJECT`.
- Require every strategy candidate to define universe, timeframe, entry, confirmation, stop, exit, sizing, liquidity, gap-risk, and no-trade rules before backtesting.
- Add critic gates for data leakage, overfit, regime fragility, execution cost, portfolio risk, evidence quality, and Agent Adda executability.
- Prefer deterministic tests and local data over LLM-only conclusions.

It will not:

- Execute live trades.
- Produce investment advice.
- Treat LLM output as executable strategy logic.
- Replace the existing Research Council, Strategy Council, paper-trading engine, or Strategy Lab.
- Implement new code until this design is reviewed and an implementation plan is approved.
- Claim exact replication of proprietary or discretionary trader methodologies.

## Research Tracks

The first opinion sprint compares seven research tracks.

### 1. Breakout-Retest Variants

**Question:** Should Agent Adda build breakout-retest as the first fully benchmarked trader-style strategy family?

**Why it matters:** Local backlog already has breakout-retest feature rows for no-lookahead derived fields, six variants, structure-aware stops, leaderboard reporting, query support, and latest-data validation.

**Required evidence:**

- Prior pivot excludes current bar.
- Breakout clears a meaningful level.
- Retest holds the breakout level or support zone.
- Entry variants compare retest-close against confirmation-entry.
- Stops use pivot, retest low, and ATR fallback.
- Results survive cost, liquidity, gap-risk, and stricter retest filters.

### 2. Minervini / SEPA / VCP

**Question:** Should Agent Adda prioritize a Minervini-style trend-template and volatility-contraction module?

**Why it matters:** Agent Adda already has Stage 2, RS, VCP labels, and registered strategy surfaces. The research challenge is distinguishing true contraction from generic tightness labels.

**Required evidence:**

- Stage 2 or trend-template alignment.
- Relative strength leadership.
- Volatility/range contraction across multiple legs.
- Volume contraction before breakout and expansion on breakout where data is available.
- Sector confirmation.
- Exit behavior under failed breakouts.

### 3. Darvas Box

**Question:** Should box breakouts become a first-class strategy module?

**Why it matters:** Darvas rules are naturally auditable: define a box, require breakout, set invalidation under the box, and measure forward reward versus risk.

**Required evidence:**

- Box high/low are derived without lookahead.
- Box width is neither too narrow to be noise nor too wide for risk control.
- Entry is above box high.
- Initial stop is below box low or structure support.
- Trade survives liquidity, slippage, and gap filters.

### 4. CAN SLIM / Growth Breakout

**Question:** Should Agent Adda formalize a CAN SLIM-inspired growth-breakout module before or after technical playbooks?

**Why it matters:** CAN SLIM can combine fundamentals, leadership, institutional context, and market direction. The difficulty is data completeness and avoiding a narrative score that cannot be tested.

**Required evidence:**

- Quarterly earnings and sales growth coverage.
- Annual growth and quality metrics.
- New high, new product, or catalyst proxy if available.
- Relative strength and sector leadership.
- Market direction and breadth confirmation.
- Missing-data handling that blocks unsupported claims.

### 5. Breadth / Regime Science

**Question:** Should breadth and regime become the next primary research layer rather than another entry strategy?

**Why it matters:** Research Council already treats market state, breadth, flows, sectors, and regime as first-order evidence. Strategy Council enhancements also identify regime-conditional performance as a key critic.

**Required evidence:**

- Percent above 50/200 DMA.
- Advance/decline and up-volume/down-volume.
- TRIN/Arms, McClellan, and breadth divergence.
- Sector breadth versus sector relative strength.
- Regime labels used as scoring gates, not arbitrary hard filters.
- Strategy performance sliced by regime and breadth bucket.

### 6. Graph / Lead-Lag Research

**Question:** Should Agent Adda build relational market models for sectors, stocks, and leadership diffusion?

**Why it matters:** Modern scientific work increasingly treats markets as relational systems. Agent Adda has sector taxonomy, sector rotation, correlation, breadth, and candidate data that can support graph research.

**Required evidence:**

- Stable sector-stock mapping.
- Rolling correlations and leadership rotation.
- Lead-lag candidates tested out of sample.
- Graph features improve decision quality versus simpler sector rank baselines.
- Results remain interpretable enough for research reports.

### 7. LLM Research Agents

**Question:** Should Agent Adda invest more in LLM agents that propose, debate, and critique strategy ideas?

**Why it matters:** Research Council and Strategy Council already use an agentic frame. Outside LLM-trading work is useful architecturally, but the evidence remains fragile unless paired with deterministic execution and realistic benchmarks.

**Required evidence:**

- LLM outputs compile only to approved structured strategy specs.
- Unsupported strategies fail closed.
- Locked-test results are hidden until strategy freeze.
- Critics can block weak evidence, overfit, regime concentration, and unexecutable claims.
- Reports distinguish hypothesis, evidence, and deterministic result.

## Reasoning Workflow

Each research item passes through five stages.

### Stage 1: Evidence Intake

Inputs can include:

- Trader books and method summaries.
- Academic papers and benchmarks.
- Practitioner blogs.
- GitHub repositories and open-source quant frameworks.
- Local Agent Adda docs, backlog, reports, backtest results, and database evidence.

The intake output is a short source card:

```text
source_id
source_type
main_claim
supporting_evidence
implementation_pattern
risk_or_limitation
agent_adda_relevance
```

### Stage 2: Tree of Thoughts Branching

Each idea is evaluated through at least five branches:

- **Bull case:** Why this idea could improve Agent Adda.
- **Bear case:** Why this idea could be weak, overfit, untestable, or distracting.
- **Data case:** What data is required and whether Agent Adda has it.
- **Execution case:** Whether the idea can become deterministic, auditable logic.
- **Portfolio case:** Whether it improves portfolio decisions rather than only single-stock narratives.

Each branch produces:

```text
thesis
counter_thesis
required_evidence
failure_modes
agent_adda_fit
confidence
```

### Stage 3: Program of Thoughts Scoring

The qualitative branches are converted into a numeric scorecard. Scores use a 0-5 scale.

| Dimension | Meaning |
| --- | --- |
| Evidence strength | External and local support for the idea |
| Data readiness | Whether Agent Adda has the required clean inputs |
| Backtestability | Whether rules can be tested without lookahead |
| Implementation fit | How naturally it fits existing modules |
| Robustness priority | Whether it reduces false positives or overfit |
| Report value | Whether outputs improve daily/EOD research reports |
| Portfolio value | Whether it improves allocation, risk, or position management |
| Complexity cost | Higher score means lower implementation complexity |

The first-pass total is:

```text
weighted_score =
  evidence_strength * 1.0 +
  data_readiness * 1.2 +
  backtestability * 1.5 +
  implementation_fit * 1.3 +
  robustness_priority * 1.5 +
  report_value * 0.8 +
  portfolio_value * 1.0 +
  complexity_cost * 0.7
```

The weights intentionally favor backtestability, robustness, and local fit over novelty.

### Stage 4: Critic Debate

Every item is challenged by critics before a decision is assigned.

| Critic | Blocks When |
| --- | --- |
| Data quality | Required source data is stale, missing, or too sparse |
| Leakage | Feature construction can see future bars or future membership |
| Overfit | Rules are too specific, trade count is too low, or validation collapses |
| Regime | Performance is concentrated in one regime without clear labeling |
| Cost/execution | Edge disappears after slippage, taxes, fees, or gap assumptions |
| Portfolio risk | Strategy creates concentration, duplicate exposure, or unstable sizing |
| Evidence | Claims cannot be traced to source cards or local tool output |
| Executability | Strategy cannot compile into approved Agent Adda grammar |

Critics return:

```text
verdict: pass | warn | block
issues
required_changes
confidence_delta
```

### Stage 5: Opinion Ledger Decision

Each idea receives one decision.

| Decision | Meaning |
| --- | --- |
| `BUILD_NOW` | Strong evidence, high local fit, immediate implementation path |
| `PROTOTYPE` | Promising but needs a small bounded experiment first |
| `RESEARCH_MORE` | Interesting, but missing data, unclear rules, or weak validation path |
| `WATCH` | Useful context, but not worth active build now |
| `REJECT` | Low evidence, poor fit, high overfit risk, or non-executable |

The ledger row shape is:

```text
idea_id
title
research_track
thesis
counter_thesis
score
critic_verdicts
decision
why_now_or_not
required_next_artifact
source_trail
```

## First Opinion Sprint

The first sprint should evaluate:

1. Breakout-retest variants.
2. Minervini / SEPA / VCP.
3. Darvas box.
4. CAN SLIM / growth breakout.
5. Breadth/regime gate.
6. Graph/lead-lag model.
7. LLM strategy proposal agent.

Expected initial stance:

| Track | Expected Decision | Rationale |
| --- | --- | --- |
| Breakout-retest | `BUILD_NOW` | Best local fit; backlog already has no-lookahead features and variants |
| Robustness layer | `BUILD_NOW` | Needed before trusting any strategy family |
| Minervini / VCP | `PROTOTYPE` | Strong fit, but contraction quality needs stricter evidence |
| Darvas box | `PROTOTYPE` | Auditable and testable, but box quality thresholds need calibration |
| CAN SLIM | `RESEARCH_MORE` | High value, but fundamentals coverage and claim gates must be measured |
| Breadth/regime | `BUILD_NOW` | Improves every strategy by reducing context-free signals |
| Graph/lead-lag | `WATCH` | Promising science, but should follow simpler sector/rank baselines |
| LLM research agents | `PROTOTYPE` | Useful for hypothesis and critique, not direct execution |

The expected combined recommendation is:

```text
BUILD_NOW: breakout-retest + robustness/breadth-regime gates
PROTOTYPE: Minervini/VCP, Darvas, LLM structured strategy proposal
RESEARCH_MORE: CAN SLIM data coverage and claim gating
WATCH: graph/lead-lag until sector baseline reports mature
```

## Integration Points

The implementation should reuse existing Agent Adda surfaces:

- Research Council evidence packs, specialist findings, critic reviews, and Markdown/HTML reporting.
- Strategy Council train/validation/locked-test flow and unsupported-strategy fail-closed behavior.
- Portfolio/paper-trading strategy schema, compiler, event replay, cost model, and run manifests.
- Existing EOD reports: sector rotation, market breadth, Stage 2, top picks, and strategy module reports.
- Backlog items for breakout-retest, Strategy Lab leaderboard, walk-forward portfolio manager, and LLM structured strategy proposal.

The new engine should not create a separate research universe. It should be an orchestration and reporting layer over existing Agent Adda data, tools, and report conventions.

## Data Flow

```text
Research source
  -> source card
  -> ToT branches
  -> PoT scorecard
  -> critic debate
  -> opinion ledger
  -> recommended artifact
  -> optional implementation plan
```

For a strategy family, the recommended artifact can be:

- strategy card,
- feature coverage report,
- backtest spec,
- report template,
- critic checklist,
- implementation plan.

For a non-strategy research idea, the recommended artifact can be:

- benchmark memo,
- data coverage audit,
- prototype experiment design,
- watchlist entry,
- rejection note.

## Output Reports

The first version should produce Markdown. HTML can follow once the report shape stabilizes.

Required sections:

- Executive opinion.
- Source cards.
- ToT branch summaries.
- PoT score table.
- Critic verdicts.
- Opinion ledger.
- Recommended build order.
- Missing evidence.
- Research-only disclaimer.

The report must distinguish:

- external research claim,
- local Agent Adda evidence,
- inference,
- hypothesis,
- deterministic backtest result.

## No-Trade and No-Build Conditions

An idea must not be promoted to `BUILD_NOW` when:

- Its core rule cannot be stated precisely.
- Required data is unavailable or stale.
- It cannot be tested without lookahead.
- It depends on LLM free text for execution.
- It cannot survive transaction-cost assumptions.
- It has no clear failure mode or invalidation rule.
- It duplicates an existing module without improving evidence, reporting, or risk control.

A strategy must not be promoted to paper-trading selection when:

- Trade count is too low for the tested horizon.
- Validation return collapses relative to train return.
- Performance is concentrated in one unlabeled regime.
- Drawdown or gap risk exceeds configured rails.
- Liquidity or spread filters reject most real candidates.
- The report lacks source trail and explicit caveats.

## Testing Strategy

Design validation before implementation:

- Review this spec for ambiguity and scope.
- Confirm the first sprint decision labels are acceptable.
- Confirm whether the first report should be standalone or embedded in Research Council.

Implementation validation later:

- Unit-test score calculation and decision thresholds.
- Unit-test critic verdict aggregation.
- Fixture-test ledger decisions for pass, warn, and block cases.
- Snapshot-test Markdown report rendering.
- Smoke-run the first opinion sprint against static source cards.
- Verify no implementation path can execute LLM-generated free text as a strategy.

## Rollout

### Phase 1: Manual Research Ledger

Create a manually curated first opinion report for the seven tracks. This proves the report shape and reasoning discipline before code.

### Phase 2: Structured Ledger Generator

Add a small deterministic generator that accepts source cards and track definitions, computes scores, applies critic results, and renders Markdown.

### Phase 3: Research Council Integration

Expose the workflow as a Research Council mode for broad research questions such as:

```text
Which strategy family should Agent Adda build next?
Should we prioritize Minervini/VCP or breakout-retest?
Which external research ideas deserve implementation?
```

### Phase 4: Strategy Lab Bridge

For `BUILD_NOW` and `PROTOTYPE` strategy ideas, generate strategy cards and backtest specs that can be handed to Strategy Lab or the portfolio replay engine.

## Success Criteria

The design is successful when Agent Adda can answer research-direction questions with:

- a ranked opinion,
- explicit reasoning branches,
- numeric scoring,
- critic challenges,
- source trail,
- local implementation fit,
- recommended next artifact,
- and clear no-build conditions.

The system should make it harder to chase fashionable research and easier to select the next useful Agent Adda build.

