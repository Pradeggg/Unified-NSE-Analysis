# Agent Adda Research Council Design

Date: 2026-05-26
Scope: Agent Adda market-wide, sector, stock, and strategy research workflow
Status: design-only
Stance: research and learning only; not investment advice

Implementation references:

- Build blueprint: `docs/RESEARCH_COUNCIL_IMPLEMENTATION_ARTIFACT.md`
- Parallel backlog: `docs/superpowers/plans/2026-05-26-agent-adda-research-council-backlog.md`
- Main coordination pointer: `docs/BACKLOG.md`

## Purpose

Agent Adda already has market data, PostgreSQL-backed evidence, daily refresh jobs, screeners, reports, and an EOD Strategy Council. The next step is to make the research workflow more explicit: a council of specialized agents should deliberate over a shared evidence pack, explore different analytical routes, let a first-class coder/quant implement testable strategy ideas, critique the results, and then produce a grounded research plan.

This design intentionally excludes cross-developer or team-memory collaboration. The focus is a single Agent Adda session running a disciplined research desk workflow.

## Goals

- Create a first-class multi-agent research workflow for market, sector, stock, and strategy analysis.
- Use a shared Evidence Pack so every agent reasons from the same source trail.
- Separate routing, evidence validation, specialist analysis, quant implementation, critique, and final synthesis.
- Let a coder/quant agent write code when a strategy idea needs a new feature, rule, backtest, or report artifact.
- Preserve deterministic data discipline: missing evidence blocks claims, stale data is labeled, and every conclusion has a source trail.
- Support POT/TOT-style deliberation as public structured summaries, without exposing private chain-of-thought.
- Produce durable artifacts: council run records, markdown/html reports, strategy specs, backtest results, and implementation tasks.

## Non-Goals

- No live order execution.
- No broker integration.
- No investment advice or unmanaged buy/sell recommendations.
- No cross-developer shared session memory.
- No copying vendor prompt text from Claude Code or other tools.
- No hidden chain-of-thought exposure. Deliberation is represented as structured public summaries.
- No requirement that the workflow only use existing tools. If the coder/quant agent needs a new tool or feature builder, it should propose and implement it under guardrails.

## Relationship To Existing Systems

This design extends three existing project directions:

- `docs/STRATEGY_COUNCIL_DESIGN.md`: existing EOD strategy council for a single symbol.
- `docs/superpowers/specs/2026-05-22-grounded-recommendation-report-design.md`: evidence-first daily recommendation reporting.
- `docs/superpowers/specs/2026-05-25-agent-adda-claude-harness-inheritance-design.md`: explicit context, typed blocks, prompt fragments, reminders, JSONL sessions, and replayable LLM loops.

The Research Council should not replace those systems. It should orchestrate them.

## High-Level Architecture

```text
User objective
   |
   v
Route Planner
   |
   v
Data Steward + Evidence Pack Builder
   |
   v
Specialist Agents
   |        |          |            |             |
   v        v          v            v             v
Macro   Sector PM   Technical   Fundamental   F&O/Risk
Agent   Agent       Analyst     Analyst       Agent
   \        |          |            |             /
    \       |          |            |            /
     v      v          v            v           v
          Deliberation Board
                 |
                 v
        Coder / Quant Engineer
                 |
                 v
        Backtests + Feature Builds
                 |
                 v
       Critics + Revision Round
                 |
                 v
        Chair / Final Synthesizer
                 |
                 v
   Report + Source Trail + Next Actions
```

## Runtime Modes

### 1. Market Council

Use when the user asks about today, sectors, the broad market, watchlists, or trade candidates.

Example prompts:

- "What sectors should we look at today?"
- "Find stocks for swing trading after daily refresh."
- "Give me a hedge-fund owner view of the market."

Primary output:

- market regime
- sector allocation view
- long candidate shortlist
- avoid/watch list
- hedge/risk notes
- evidence gaps

### 2. Stock Deep Dive Council

Use when the user asks about one symbol or a small set of symbols.

Example prompts:

- "Review MODISONLTD."
- "Is PERSISTENT a valid swing setup?"
- "Compare APOLLO, BEL, and HAL."

Primary output:

- stock 360 view
- technical/fundamental/catalyst/F&O debate
- setup quality
- invalidation level
- missing evidence
- whether the name should move to Strategy Council

### 3. Strategy Build Council

Use when the user asks to build, test, refine, or validate a strategy.

Example prompts:

- "Build a Minervini breakout strategy."
- "Test Stage 2 pullbacks with volume dry-up."
- "Convert this thesis into code and backtest it."

Primary output:

- strategy specs
- generated or modified strategy code
- train/validation/test backtests
- critic review
- final research status: `TRADE_RESEARCH`, `WAIT`, or `NO_TRADE`

### 4. Intraday Tactical Council

Use when the user asks for current market action, live quotes, or intraday trading setup.

Example prompts:

- "What is setting up intraday now?"
- "Scan for VWAP reclaim candidates."
- "Check live options positioning for CE."

Primary output:

- intraday evidence freshness
- live/intraday setup map
- degraded-mode flags when NSE or PG intraday sources are missing
- no-trade triggers when evidence is stale

### 5. Report Review Council

Use when the user asks to review a generated report or diagnose missing sections.

Example prompts:

- "Review this report file."
- "Why did the report only show REQUIRED TOOL VALIDATION FAILED?"
- "Check whether this report is institutional-grade."

Primary output:

- report quality findings
- missing tool/evidence list
- line/file references
- remediation steps

## Agent Roles

### Route Planner

Decides which council mode to run. It should classify the user objective by:

- scope: market, sector, symbol, strategy, report, data repair
- horizon: intraday, swing, positional, long-term
- output: brief, report, code, backtest, watchlist
- data requirements: EOD, intraday, fundamentals, F&O, news, results

It should return a route object:

```json
{
  "route": "market_council",
  "horizon": "swing",
  "requires_code": false,
  "requires_refresh_check": true,
  "required_evidence": ["eod", "stage", "sector", "fii_dii", "fno", "fundamentals"]
}
```

### Data Steward

Runs before every serious council analysis. It protects the council from stale or incomplete evidence.

Responsibilities:

- identify latest EOD date
- check PostgreSQL availability
- check row counts and source freshness
- explain universe filters, such as price and liquidity screens
- classify missing evidence as blocking or non-blocking
- decide whether degraded mode is acceptable

Example output:

```json
{
  "as_of": "2026-05-26",
  "data_status": "usable",
  "blocking_gaps": [],
  "non_blocking_gaps": ["fno_latest_date_lag"],
  "universe": {
    "total_symbols": 2465,
    "liquid_symbols": 982,
    "analyzed_symbols": 968,
    "filters": ["close > 100", "volume > 100000", "at least 50 bars"]
  }
}
```

### Evidence Pack Builder

Builds the shared evidence object used by every agent. This is the source of truth for all downstream analysis.

Evidence sections:

- `market`: index trend, breadth, volatility, regime, FII/DII
- `sectors`: sector rotation, Stage 2 counts, RS, breadth, macro tailwinds
- `stocks`: prices, stage, RS, scores, volume, fundamentals, catalysts
- `derivatives`: futures buildup, PCR, OI, IV, option-chain evidence
- `fundamentals`: Screener-derived metrics, quarterly results, annual trends
- `events`: results, filings, corporate actions, concalls
- `reports`: latest sector rotation, stage tracker, recommendation reports
- `source_trail`: table names, files, row counts, freshness, fallback flags
- `missing_evidence`: explicit missing fields by scope and symbol

The pack should be serializable to JSON so it can be stored and replayed.

### Hedge Fund Owner / Portfolio Manager

Thinks like the owner of risk capital.

Focus:

- where to allocate attention and capital
- sector concentration
- liquidity
- drawdown risk
- correlation risk
- market regime
- whether cash is a valid position

Typical stance:

- overweight, neutral, underweight, avoid
- "watch but do not chase"
- "wait for confirmation"
- "setup is attractive but liquidity/risk is unacceptable"

### Macro / Regime Agent

Focus:

- Nifty/Broader market trend
- volatility regime
- FII/DII flows
- macro proxies
- global risk read-through
- breadth thrust or deterioration

It should answer:

- Is the market supportive for risk?
- Is this a stock-picker tape or index-driven tape?
- Which sectors have macro tailwinds or headwinds?

### Sector Rotation Agent

Focus:

- sector leaders, improvers, laggards, and weakening groups
- Stage 2 density
- RS versus Nifty 50 and Nifty 500
- breadth inside sectors
- top stocks within strong sectors

It should produce:

- sector shortlist
- sector avoid list
- internal divergence alerts
- candidate clusters

### Technical Analyst

Focus:

- Stage 1/2/3/4
- RS
- moving average stack
- RSI/MACD/ADX/Supertrend
- 52-week high proximity
- volume confirmation
- support/resistance
- breakout or pullback structure

It should distinguish:

- actionable setup
- extended setup
- damaged setup
- no-trade chop

### Minervini Agent

Focus:

- Stage 2 requirement
- RS leadership
- price above key moving averages
- proximity to 52-week high
- volume contraction and expansion
- VCP or tightness
- breakout quality
- avoiding late, extended, or obvious entries

It should be strict. Many candidates should fail.

### Fundamental Analyst

Focus:

- sales and profit growth
- margins
- ROE/ROCE
- balance sheet risk
- valuation
- promoter pledge
- working-capital issues
- quarterly result trend

It should classify fundamentals as:

- `quality_supportive`
- `quality_mixed`
- `quality_weak`
- `quality_unknown`

### F&O / Risk Agent

Focus:

- futures buildup
- long/short covering or unwinding
- PCR
- IV
- option-chain support/resistance
- hedge considerations
- crowded positioning

It should not create an options strategy unless option-chain evidence is present.

### Catalyst Agent

Focus:

- earnings calendar
- recent results
- concall transcripts
- management commentary
- BSE/NSE filings
- broker research
- news and regulatory events

It should separate verified catalysts from rumors or missing evidence.

### Coder / Quant Engineer

This is the main enhancement over ordinary analyst agents.

The coder/quant agent can:

- inspect data schemas and sample rows
- create feature builders
- implement strategy specs
- modify strategy sandbox code
- add tests
- run backtests
- compare variants
- return empirical evidence to the council

Guardrails:

- no live order execution
- no destructive data mutation unless the user explicitly approves
- no strategy code outside approved strategy/research modules
- no optimizing on the final test split
- no test split visibility until a strategy is locked
- every generated strategy must include assumptions, risk rules, and failure modes

The coder/quant does not make the final recommendation. It provides evidence.

### Critic Agents

Critics challenge the proposed plan before the final synthesis.

Required critics:

- `DataQualityCritic`: stale data, missing rows, bad joins, source mismatch
- `LeakageCritic`: future data, split contamination, test-set overuse
- `OverfitCritic`: too many parameters, low trade count, regime dependence
- `RiskCritic`: liquidity, gap risk, concentration, downside, options risk
- `EvidenceCritic`: unsupported claims, missing source trail, non-blocking gaps mislabeled as facts

### Chair / Final Synthesizer

Combines the council output into the final response.

Responsibilities:

- resolve disagreements
- preserve minority objections when important
- produce ranked outputs
- label confidence and evidence quality
- state invalidation conditions
- state what should be done next
- write the report artifact

## Deliberation Model

The council should expose public structured reasoning, not hidden chain-of-thought.

### POT: Plan of Thought

This is the public planning frame.

Fields:

- objective
- horizon
- eligible universe
- risk budget
- required evidence
- blocker checks
- candidate routes
- success criteria
- rejection criteria

Example:

```json
{
  "objective": "Find swing-trading candidates after latest daily refresh",
  "horizon": "5-20 trading days",
  "universe": "liquid EOD universe",
  "risk_budget": "moderate",
  "required_evidence": ["eod", "stage", "sector", "fundamentals", "fno"],
  "rejection_criteria": ["stale EOD", "missing price history", "Stage 4", "thin liquidity"]
}
```

### TOT: Tree of Thought Summary

This is the public branch summary. It should not include private scratch reasoning.

Branches:

- momentum leadership route
- Minervini Stage 2 route
- sector rotation route
- earnings/catalyst route
- F&O positioning route
- defensive/no-trade route

Each branch returns:

```json
{
  "branch": "minervini_stage2",
  "stance": "selective",
  "candidates": ["SYMBOL1", "SYMBOL2"],
  "rejects": ["SYMBOL3"],
  "evidence": ["Stage 2", "RS top decile", "near 52-week high"],
  "risks": ["extended RSI", "weak market breadth"],
  "next_step": "run VCP/tightness feature and backtest breakout variant"
}
```

## Plan Lifecycle

### Step 1: Intake

Parse user objective, horizon, mode, and desired artifact.

### Step 2: Route

Choose one or more council modes.

### Step 3: Refresh Check

Data Steward checks whether the latest available data is sufficient.

### Step 4: Evidence Pack

Build or load the shared Evidence Pack.

### Step 5: Specialist Pass

Run relevant agents in parallel where possible. Each agent returns structured findings.

### Step 6: Branch Deliberation

Construct the public TOT branch summary. Identify promising routes and rejected routes.

### Step 7: Coder / Quant Work

If any route needs empirical validation, the coder/quant:

- creates or selects a strategy spec
- writes missing feature code if required
- runs tests
- runs train/validation backtests
- returns results and limitations

### Step 8: Critic Review

Critics attack the evidence, strategy, and recommendation quality.

### Step 9: Revision

Agents revise their stance based on critic findings and backtest evidence.

### Step 10: Final Synthesis

Chair produces the final research-only plan:

- market view
- sector view
- candidate table
- rejected candidates
- strategy/backtest evidence
- risks
- invalidation triggers
- next actions

### Step 11: Persistence

Persist the council run, evidence metadata, agent outputs, strategy specs, backtests, critic reviews, and report paths.

## Tool Strategy

The workflow should use existing tools first, then let the coder/quant propose new tools when the current surface is insufficient.

### Existing Tool Families To Reuse

- daily refresh and PostgreSQL loader
- sector rotation report
- stage tracker
- EOD screeners
- recommendation report
- stock 360 report
- Strategy Council
- backtesting engine
- F&O analytics
- options and futures tools
- fundamentals and Screener cache
- latest results feed
- corporate events and filings
- intraday quote/snapshot tools

### New First-Class Tools To Add

```text
build_research_evidence_pack(date, mode, universe, symbols=None)
run_research_council(objective, horizon, risk_budget, mode="auto")
rank_sector_candidates(evidence_pack_id)
rank_stock_candidates(evidence_pack_id)
generate_strategy_specs_from_theses(council_run_id)
code_strategy_candidate(strategy_spec_id)
backtest_strategy_candidate(strategy_spec_id, split_policy)
review_council_run(council_run_id)
render_research_council_report(council_run_id, format)
persist_research_council_run(council_run)
```

### Command UX

Proposed terminal commands:

```bash
/council today --horizon swing --risk moderate
/council sector --date latest
/council stock MODISONLTD --horizon swing
/council strategy "Stage 2 breakout with volume confirmation"
/council intraday --scan vwap-reclaim
/council review --run latest
/council report --run latest --format html
```

## Data Contracts

### ResearchCouncilRun

```json
{
  "run_id": "research_20260526_001",
  "created_at": "2026-05-26T21:30:00+05:30",
  "mode": "market_council",
  "objective": "Find swing-trading candidates after daily refresh",
  "horizon": "swing",
  "risk_budget": "moderate",
  "evidence_pack_id": "evidence_20260526_001",
  "data_status": "usable",
  "agent_outputs": [],
  "branch_summaries": [],
  "strategy_specs": [],
  "backtest_results": [],
  "critic_reviews": [],
  "final_recommendations": [],
  "report_paths": []
}
```

### AgentFinding

```json
{
  "agent": "minervini",
  "stance": "bullish",
  "confidence": 0.72,
  "thesis": "Stage 2 leadership candidate with constructive RS.",
  "evidence": ["Stage 2", "price above SMA20/50/200", "RS positive"],
  "candidates": ["SYMBOL"],
  "rejects": [],
  "risks": ["RSI extended"],
  "required_next_steps": ["check VCP tightness", "validate volume breakout"],
  "veto_reason": null
}
```

### StrategyBuildRequest

```json
{
  "source_branch": "minervini_stage2",
  "strategy_family": "stage2_breakout",
  "hypothesis": "Stage 2 stocks near 52-week highs with volume expansion outperform over 5-20 days.",
  "required_features": ["stage", "rs_percentile", "volume_ratio", "52w_high_proximity"],
  "allowed_horizons": [5, 10, 20],
  "split_policy": "train_validation_test_time_ordered"
}
```

## Evidence And Claim Discipline

The council must follow these rules:

- Missing evidence is a claim blocker.
- Stale data must be labeled in the final output.
- A stock can be recommended only as research action, not investment advice.
- F&O and options claims require F&O/options evidence.
- Fundamental claims require fundamentals evidence.
- Catalyst claims require filing, results, concall, news, or event evidence.
- Backtest claims require split labels, trade count, period, and source data.
- A no-trade outcome is a valid final answer.

Allowed final labels:

- `WATCHLIST`
- `RESEARCH_LONG`
- `WAIT_FOR_CONFIRMATION`
- `AVOID_FRESH_ENTRY`
- `REVIEW_MANUALLY`
- `NO_TRADE`
- `HEDGE_REQUIRED`

## Report Output

The Research Council report should contain:

1. Objective and mode
2. Data freshness and source trail
3. Market regime
4. Sector rotation view
5. Candidate table
6. Agent findings
7. Public POT/TOT summaries
8. Strategy specs and backtest summaries
9. Critic review
10. Final research plan
11. Invalidations and next actions
12. Missing evidence
13. Research-only disclaimer

## Implementation Slices

### Slice 1: Design And Backlog

- Save this design document.
- Add backlog items for the Research Council foundation.
- Define implementation boundaries with the existing Strategy Council.

### Slice 2: Evidence Pack Foundation

- Create `ResearchEvidencePack`.
- Build from PostgreSQL-first sources.
- Include freshness, row counts, source trail, and missing evidence.
- Add tests for stale/missing data behavior.

### Slice 3: Council Run Schema

- Create `ResearchCouncilRun`, `AgentFinding`, `BranchSummary`, and `CriticReview` types.
- Add persistence to PostgreSQL or JSONL-first storage.
- Add replay support.

### Slice 4: Specialist Agents

- Implement deterministic versions first.
- Add LLM adapters only after deterministic outputs are stable.
- Use structured JSON outputs.

### Slice 5: Coder / Quant Sandbox

- Define where generated strategy code can live.
- Add tests before generated strategy execution.
- Connect strategy build requests to the existing Strategy Council/backtesting engine.

### Slice 6: Deliberation And Critics

- Add public POT/TOT summary generation.
- Add critic review and revision round.
- Add claim-blocking policy.

### Slice 7: Reports And Terminal Commands

- Add `/council` terminal command family.
- Render Markdown and HTML reports.
- Add report review route.

### Slice 8: Comprehensive Tests

- Route classification tests.
- Evidence pack freshness tests.
- Agent output schema tests.
- Strategy build guardrail tests.
- Backtest split leakage tests.
- Report rendering tests.
- End-to-end council smoke test on a small fixture universe.

## Open Questions

- Should the first implementation persist council runs in PostgreSQL immediately, or start with JSON files under `reports/research_council/`?
- Should `/council today` default to the liquid universe filter currently used by the daily technical analysis, or expose `--universe full|liquid|stage2|watchlist` from day one?
- Should the coder/quant be allowed to create new strategy families immediately, or only combine existing whitelisted Strategy Council rules in the first slice?
- Should the final report include position sizing examples, or avoid that entirely to keep outputs clearly research-only?

## Recommended First Build

Start with the smallest useful vertical slice:

```text
/council today --horizon swing --risk moderate
```

This should:

1. Check latest refresh status.
2. Build a market/sector/stock evidence pack from PostgreSQL and latest reports.
3. Run deterministic specialist agents.
4. Produce public POT/TOT summaries.
5. Rank sectors and stock candidates.
6. Run critics.
7. Render a markdown report.
8. Persist the run metadata.

Do not start with free-form strategy code generation. Add the coder/quant after the deterministic council loop is stable and testable.
