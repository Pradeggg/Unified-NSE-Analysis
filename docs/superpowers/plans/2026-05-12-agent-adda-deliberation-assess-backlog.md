# Agent Adda Deliberation + `/assess` Intelligence Backlog

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Agent Adda into a multi-persona Market Intelligence OS with a flagship `/assess` command powered by Plan-of-Thought execution, Tree-of-Thought hypothesis branching, evidence scoring, simulations, and persona-aware rendering.

**Architecture:** Add a focused `terminal/deliberation/` package that separates target resolution, planning, evidence collection, hypothesis generation, simulation, scoring, memory, and rendering. Integrate it into `terminal/agent.py` and `nse_agent.py` as an additive deterministic workflow before falling back to the general LLM path.

**Tech Stack:** Python 3.10+, existing Agent Adda terminal/Rich UI, PostgreSQL market data, existing `terminal.tools` functions, unittest/pytest-compatible tests, optional OpenAI/Ollama narrative layer.

---

## Product Contract

### User-Facing Command

```text
/assess DMART
/assess NIFTY
/assess NIFTY BANK
/assess IT sector
/assess my portfolio
/assess watchlist
```

### Supported Target Types

| Target Type | Example | MVP Depth |
|---|---|---|
| Stock | `/assess DMART` | Deep |
| Index | `/assess NIFTY 50` | Medium |
| Sector | `/assess banking sector` | Medium |
| Portfolio | `/assess my portfolio` | Basic initially |
| Watchlist | `/assess watchlist` | Basic initially |

### Output Contract

Every assessment must include:

1. Executive read
2. Target classification
3. Data freshness
4. Evidence collected
5. Competing hypotheses
6. Scenario/simulation view
7. Confidence score
8. Risks and invalidation
9. What to monitor next
10. Follow-up questions

### Non-Negotiable Guardrails

- Missing data must be shown as missing, not inferred.
- Tool errors must be visible in source trail.
- EOD/fallback data must not be described as live intraday.
- The answer must distinguish research output from investment advice.
- The final response should expose an audit trail, not raw hidden reasoning.

---

## Phase 0: Existing Prototype Review

### AAI-0.1: Review Current Untracked Deliberation Prototype

**Files:**
- Read: `terminal/deliberation/__init__.py`
- Read: `terminal/deliberation/planner.py`
- Read: `terminal/deliberation/hypothesis.py`
- Read: `terminal/deliberation/evaluator.py`
- Read: `terminal/deliberation/simulator.py`
- Read: `terminal/deliberation/memory.py`
- Read: `terminal/deliberation/renderer.py`

- [ ] **Step 1: Inspect prototype boundaries**

Run:

```bash
find terminal/deliberation -maxdepth 1 -type f -name "*.py" -print -exec sed -n '1,220p' {} \;
```

Expected: identify whether the current untracked prototype should be adopted, replaced, or split.

- [ ] **Step 2: Record adoption decision**

Add a short implementation note to this backlog under this task:

```text
Prototype decision:
- Adopt:
- Replace:
- Split:
- Reason:
```

Expected: no ambiguous ownership before implementation starts.

---

## Phase 1: Target Resolution + Assessment Request

### AAI-1.1: Define Assessment Request Contract

**Files:**
- Create or modify: `terminal/deliberation/types.py`
- Test: `tests/test_deliberation_assess.py`

- [ ] **Step 1: Write failing tests for request types**

Create tests:

```python
from terminal.deliberation.types import AssessmentRequest


def test_assessment_request_defaults():
    req = AssessmentRequest(raw_query="/assess DMART", target="DMART", target_type="stock")
    assert req.persona == "hybrid"
    assert req.horizon == "auto"
    assert req.mode == "auto"
    assert req.target == "DMART"
```

Run:

```bash
.venv/bin/python -m unittest tests.test_deliberation_assess
```

Expected: fails because `types.py` or `AssessmentRequest` does not exist.

- [ ] **Step 2: Implement dataclasses**

Implement:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AssessmentRequest:
    raw_query: str
    target: str
    target_type: str
    persona: str = "hybrid"
    horizon: str = "auto"
    mode: str = "auto"
    options: dict[str, Any] = field(default_factory=dict)
```

- [ ] **Step 3: Run tests**

Run:

```bash
.venv/bin/python -m unittest tests.test_deliberation_assess
```

Expected: request contract test passes.

### AAI-1.2: Resolve `/assess` Target Type

**Files:**
- Create or modify: `terminal/deliberation/resolver.py`
- Test: `tests/test_deliberation_assess.py`

- [ ] **Step 1: Write target resolver tests**

Add tests:

```python
from terminal.deliberation.resolver import resolve_assessment_request


def test_resolve_stock_assessment():
    req = resolve_assessment_request("/assess DMART")
    assert req.target == "DMART"
    assert req.target_type == "stock"


def test_resolve_index_assessment():
    req = resolve_assessment_request("/assess NIFTY BANK")
    assert req.target == "NIFTY BANK"
    assert req.target_type == "index"


def test_resolve_sector_assessment():
    req = resolve_assessment_request("/assess banking sector")
    assert req.target == "banking"
    assert req.target_type == "sector"


def test_resolve_portfolio_assessment():
    req = resolve_assessment_request("/assess my portfolio")
    assert req.target == "portfolio"
    assert req.target_type == "portfolio"
```

- [ ] **Step 2: Implement resolver**

Rules:

- `my portfolio`, `portfolio` -> `portfolio`
- `watchlist` -> `watchlist`
- `sector` suffix -> `sector`
- known index aliases: `NIFTY`, `NIFTY 50`, `NIFTY BANK`, `BANKNIFTY`, `NIFTY IT`, `NIFTY MIDCAP 100`
- otherwise uppercase single token -> `stock`

- [ ] **Step 3: Run tests**

Run:

```bash
.venv/bin/python -m unittest tests.test_deliberation_assess
```

Expected: target resolution tests pass.

---

## Phase 2: Plan-of-Thought Planner

### AAI-2.1: Build Common Planner Contract

**Files:**
- Modify: `terminal/deliberation/planner.py`
- Test: `tests/test_deliberation_planner.py`

- [ ] **Step 1: Write planner tests**

Test that stock, index, sector, and portfolio requests produce explicit executable tasks.

Expected stock tools:

```text
resolve_symbol
get_symbol_snapshot
get_technical_setup
get_sector_context
get_company_intelligence_summary
get_market_breadth
```

Expected index tools:

```text
get_live_market_overview
get_intraday_index_technicals
get_market_breadth
get_fii_dii_activity
get_global_market_assessment
```

Expected sector tools:

```text
get_sector_context
get_market_breadth
get_top_gainers_losers
search_latest_catalysts
```

Expected portfolio tools:

```text
get_portfolio_pnl
get_market_breadth
get_global_market_assessment
```

- [ ] **Step 2: Implement `build_assessment_plan(request)`**

Return a structured plan with:

```python
PlanTask(
    id="technicals",
    question="What is the latest technical setup?",
    tool="get_technical_setup",
    args={"symbol": "DMART"},
    required=True,
    fallback="Show missing technicals and do not infer RSI/MACD.",
)
```

- [ ] **Step 3: Verify no placeholder execution**

Add tests that `/assess SYMBOL`, `/assess TICKER`, and `/assess company` return a clarification plan and do not call `resolve_symbol`.

---

## Phase 3: Tool Execution + Evidence Ledger

### AAI-3.1: Execute Assessment Plans Safely

**Files:**
- Create or modify: `terminal/deliberation/executor.py`
- Test: `tests/test_deliberation_executor.py`

- [ ] **Step 1: Write executor tests with fake tool registry**

Test:

- successful tools produce `EvidenceItem(status="ok")`
- failed tools produce `EvidenceItem(status="error")`
- missing tools produce `EvidenceItem(status="missing_tool")`
- execution continues after a failure

- [ ] **Step 2: Implement executor**

Implement:

```python
def execute_assessment_plan(plan, *, tool_caller) -> list[EvidenceItem]:
    items: list[EvidenceItem] = []
    for task in plan.tasks:
        if not task.tool:
            items.append(EvidenceItem(task_id=task.id, tool="", status="manual", result={}, error=""))
            continue
        try:
            result = tool_caller(task.tool, dict(task.args))
        except Exception as exc:
            items.append(EvidenceItem(task_id=task.id, tool=task.tool, status="error", result={}, error=str(exc)))
            continue
        if isinstance(result, dict) and result.get("error"):
            items.append(EvidenceItem(task_id=task.id, tool=task.tool, status="error", result=result, error=str(result["error"])))
        else:
            items.append(EvidenceItem(task_id=task.id, tool=task.tool, status="ok", result=result if isinstance(result, dict) else {"value": result}, error=""))
    return items
```

Use dependency injection for tests. In production, pass `terminal.tools.call_tool`.

- [ ] **Step 3: Run executor tests**

Run:

```bash
.venv/bin/python -m unittest tests.test_deliberation_executor
```

Expected: all executor tests pass.

### AAI-3.2: Evidence Scoring

**Files:**
- Modify: `terminal/deliberation/evaluator.py`
- Test: `tests/test_deliberation_evaluator.py`

- [ ] **Step 1: Add scoring tests**

Score dimensions:

- usable evidence count
- missing required evidence
- tool errors
- source freshness
- contradiction count
- confidence bucket: `high`, `medium`, `low`, `insufficient`

- [ ] **Step 2: Implement scoring**

Rules:

- any missing required technical/fundamental evidence caps stock confidence at `medium`
- no usable evidence -> `insufficient`
- live source + DB breadth + no errors -> `high`
- fallback/EOD source in intraday request -> freshness warning

---

## Phase 4: Tree-of-Thought Hypothesis Branching

### AAI-4.1: Generate Target-Specific Hypotheses

**Files:**
- Modify: `terminal/deliberation/hypothesis.py`
- Test: `tests/test_deliberation_hypothesis.py`

- [ ] **Step 1: Write hypothesis tests**

Expected stock branches:

```text
bullish_continuation
bearish_breakdown
watchlist_wait
quality_but_bad_entry
```

Expected index branches:

```text
risk_on_continuation
range_bound
breakdown_risk
short_covering_bounce
```

Expected sector branches:

```text
sector_leadership
rotation_exhaustion
laggard_catchup
macro_headwind
```

Expected portfolio branches:

```text
concentration_risk
factor_drawdown_risk
rotation_opportunity
cash_or_hedge_needed
```

- [ ] **Step 2: Implement branch builder**

Implement:

```python
def build_hypotheses(request: AssessmentRequest, evidence_score: EvidenceScore) -> list[Hypothesis]:
    if request.target_type == "stock":
        return STOCK_HYPOTHESES
    if request.target_type == "index":
        return INDEX_HYPOTHESES
    if request.target_type == "sector":
        return SECTOR_HYPOTHESES
    if request.target_type in {"portfolio", "watchlist"}:
        return PORTFOLIO_HYPOTHESES
    return [Hypothesis(label="needs_clarification", thesis="Target type is unclear.", supporting_keys=(), disconfirming_keys=(), persona_relevance={})]
```

Each hypothesis must include:

- label
- thesis
- supporting evidence keys
- disconfirming evidence keys
- persona relevance

### AAI-4.2: Rank Hypotheses

**Files:**
- Modify: `terminal/deliberation/hypothesis.py`
- Test: `tests/test_deliberation_hypothesis.py`

- [ ] **Step 1: Write ranking tests**

Given evidence where breadth is weak and index is below key moving averages, `breakdown_risk` should outrank `risk_on_continuation`.

- [ ] **Step 2: Implement ranking**

Use deterministic scoring first:

```text
support_count * 20
- contradiction_count * 15
- missing_required_evidence * 10
+ persona_relevance_bonus
```

Do not use LLM scoring for MVP.

---

## Phase 5: Simulation Layer

### AAI-5.1: Stock and Index Scenario Simulation

**Files:**
- Modify: `terminal/deliberation/simulator.py`
- Test: `tests/test_deliberation_simulator.py`

- [ ] **Step 1: Write simulation tests**

For stock:

```text
base_case
bull_case
bear_case
invalidation_case
```

For index:

```text
risk_on
range
risk_off
gap_down
```

- [ ] **Step 2: Implement deterministic simulations**

Use available levels:

- current price
- support
- resistance
- SMA20/50/200
- day high/low for intraday
- breadth and VIX for index

If levels are missing, render scenario as `not_available` with reason.

### AAI-5.2: Portfolio and Watchlist Simulation

**Files:**
- Modify: `terminal/deliberation/simulator.py`
- Test: `tests/test_deliberation_simulator.py`

- [ ] **Step 1: Write portfolio tests**

Simulate:

- NIFTY -2%
- sector shock
- volatility spike
- single-stock drawdown

- [ ] **Step 2: Implement basic portfolio simulation**

For MVP, use simple exposure math:

```text
estimated_impact = portfolio_weight * shock_pct * beta_proxy
```

If holdings are unavailable, return guided setup:

```text
Portfolio holdings are not configured. Use /pnl or portfolio CSV setup first.
```

---

## Phase 6: Renderer + Persona Workbenches

### AAI-6.1: Persona-Aware Assessment Renderer

**Files:**
- Modify: `terminal/deliberation/renderer.py`
- Test: `tests/test_deliberation_renderer.py`

- [ ] **Step 1: Write renderer tests**

Personas:

- `trader`
- `investor`
- `fund_manager`
- `researcher`
- `hybrid`

Expected differences:

- trader output emphasizes entry, invalidation, timeframe
- investor output emphasizes business quality, valuation, moat, risks
- fund manager output emphasizes exposure, factor risk, liquidity, sizing
- researcher output emphasizes evidence trail, gaps, source quality

- [ ] **Step 2: Implement renderer**

Renderer sections:

```text
━━━ Assessment: TARGET ━━━
Executive Read
Target + Persona
Data Freshness
Evidence Map
Hypothesis Ranking
Scenario View
Risks / Invalidation
Confidence
What To Monitor Next
Source Trail
Research-only Disclaimer
```

### AAI-6.2: Follow-Up Question Generator

**Files:**
- Modify: `terminal/deliberation/renderer.py`
- Test: `tests/test_deliberation_renderer.py`

- [ ] **Step 1: Write follow-up tests**

Stock follow-ups should include:

```text
/technical SYMBOL
/forensic SYMBOL
/search SYMBOL news
```

Index follow-ups should include:

```text
/scan INDEX
/recap 30
/market regime
```

- [ ] **Step 2: Implement deterministic follow-ups**

Return exactly three follow-ups in the existing Agent Adda follow-up format.

---

## Phase 7: Agent Integration

### AAI-7.1: Add `/assess` to Slash Commands and Help

**Files:**
- Modify: `nse_agent.py`
- Modify: `terminal/help.py`
- Modify: `docs/AGENT_ADDA_CAPABILITIES.md`
- Test: `tests/test_nse_agent_assess.py`

- [ ] **Step 1: Write command registration tests**

Assert `/assess` appears in:

- `_SLASH_COMMANDS`
- help search
- capabilities doc

- [ ] **Step 2: Add command entries**

Add:

```text
/assess SYMBOL
/assess NIFTY
/assess sector
/assess portfolio
/assess watchlist
```

### AAI-7.2: Route `/assess` Through Deliberation Engine

**Files:**
- Modify: `nse_agent.py`
- Modify: `terminal/agent.py`
- Test: `tests/test_nse_agent_assess.py`

- [ ] **Step 1: Write route tests**

Given `/assess DMART`, assert:

- no stock-symbol fallback rewrite occurs
- deliberation planner is called
- final answer contains `Hypothesis Ranking`
- source trail includes tool names

- [ ] **Step 2: Implement direct handler**

In `nse_agent.py`, before generic query flow:

```python
if text.lower().startswith("/assess"):
    result = agent.assess(text, mode=_mode)
    _print_user(text)
    _print_response(result)
    continue
```

In `terminal/agent.py`:

```python
def assess(self, text: str, mode: str = "auto") -> dict:
    request = resolve_assessment_request(text, mode=mode)
    plan = build_assessment_plan(request)
    evidence_items = execute_assessment_plan(plan, tool_caller=call_tool)
    evidence_score = evaluate_evidence(evidence_items)
    hypotheses = rank_hypotheses(build_hypotheses(request, evidence_score), evidence_items, request)
    scenarios = simulate_assessment_scenarios(request, evidence_items, hypotheses)
    answer = render_assessment(request, plan, evidence_items, evidence_score, hypotheses, scenarios)
    trace = [{"step": "assessment_plan", "result": plan.to_trace()}] + [item.to_trace() for item in evidence_items]
    self._remember_interaction(text, answer, trace)
    return {"answer": answer, "trace": trace, "backend": self.backend_name, "intent": "assess"}
```

Return the same shape as `query()`:

```python
{"answer": answer, "trace": trace, "backend": self.backend_name, "intent": "assess"}
```

---

## Phase 8: Market TV Dashboard Intelligence UX

### AAI-8.1: Adaptive Dashboard Layout Modes

**Reason:** Screenshot QA showed the current Stock Market TV view is information-rich but too horizontally dense. Important values are clipped and row labels truncate heavily.

**Files:**
- Modify: `nse_agent.py`
- Test: `tests/test_nse_agent_monitor_scan.py` or create `tests/test_market_dashboard_rendering.py`

- [ ] **Step 1: Write rendering tests for terminal sizes**

Test sizes:

```text
80x24  -> ultra compact, no multi-panel overflow
120x34 -> compact TV table
160x44 -> full cockpit
```

Expected:

- title visible
- NIFTY 50 visible
- Breadth visible
- Narrative visible
- no repeated clipped labels such as `Top Gainer...` when full label could be shown in wider mode

- [ ] **Step 2: Implement layout policy**

Use:

```text
width < 100 or height < 30: vertical key-value TV rows
100-139 width: compact section table
>=140 width and >=38 height: full cockpit panels
```

- [ ] **Step 3: Add manual visual QA checklist**

Run:

```bash
python nse_agent.py --no-briefing
/dashboard
```

Verify:

- no row overwrites prompt
- ticker animates without hiding data
- Ctrl+C returns cleanly
- labels are readable
- the footer does not collide with panel border

---

## Phase 9: Model-Agnostic Deliberation

### AAI-9.1: Keep `/assess` Deterministic Before LLM Narrative

**Files:**
- Modify: `terminal/agent.py`
- Test: `tests/test_nse_agent_assess.py`

- [ ] **Step 1: Write model independence tests**

Run `/assess DMART` with:

```text
backend = None
backend = fake OpenAI
backend = fake Ollama
```

Expected:

- same tools are called
- same evidence score is produced
- only narrative phrasing may differ

- [ ] **Step 2: Implement optional LLM narrative layer**

The deterministic renderer is always the base answer. If LLM is enabled, use it only to rewrite a bounded `narrative_summary` from structured facts.

---

## Phase 10: Regression and Benchmark Suite

### AAI-10.1: Build 40-Scenario `/assess` Regression Pack

**Files:**
- Create: `tests/fixtures/assess_scenarios.json`
- Create: `tests/test_assess_regression_scenarios.py`

- [ ] **Step 1: Create scenario fixture**

Include:

- 10 stock scenarios
- 10 index scenarios
- 8 sector scenarios
- 6 portfolio/watchlist scenarios
- 6 malformed/edge scenarios

- [ ] **Step 2: Write regression runner**

Each scenario asserts:

- target type
- required tools
- no placeholder symbol execution
- answer has confidence
- answer has missing-evidence section when a required tool fails

### AAI-10.2: Add Model Benchmark Extension

**Files:**
- Modify: `reports/enhanced_comprehensive_analysis.py` only if this benchmark hooks into existing reports
- Or create: `reports/model_benchmarks/assess_benchmark_runner.py`
- Output: `reports/model_benchmarks/assess_model_benchmark_<timestamp>.md`

- [ ] **Step 1: Benchmark deterministic vs OpenAI vs Ollama**

Compare:

- factual accuracy
- source trail completeness
- tool-call consistency
- hallucination rate
- missing evidence honesty
- multi-turn context handling
- response usefulness by persona

---

## Acceptance Criteria

- `/assess` supports stocks, indices, sectors, portfolios, and watchlists.
- Stock assessments are deepest; other target types provide useful MVP output.
- Every answer includes evidence, confidence, scenarios, risks, and next checks.
- Missing evidence is explicit and reduces confidence.
- The workflow works with OpenAI, Ollama, or no LLM backend.
- Dashboard rendering has adaptive layouts and passes visual QA.
- Tests cover planner, resolver, executor, evaluator, hypothesis, simulator, renderer, and agent integration.
- Existing Agent Adda commands continue to pass current regression tests.

## Verification Commands

Run before every commit:

```bash
.venv/bin/python -m unittest tests.test_nse_agent_monitor_scan tests.test_market_knowledge tests.test_terminal_agent_market_prompt
.venv/bin/python -m unittest tests.test_deliberation_assess tests.test_deliberation_planner tests.test_deliberation_executor tests.test_deliberation_evaluator tests.test_deliberation_hypothesis tests.test_deliberation_simulator tests.test_deliberation_renderer tests.test_nse_agent_assess
.venv/bin/python -m py_compile nse_agent.py terminal/agent.py terminal/tools.py terminal/deliberation/*.py
git diff --check
```

Expected:

```text
all tests pass
py_compile exits 0
git diff --check exits 0
```

## Commit Strategy

Use small commits:

```text
feat: add assessment request resolver
feat: add deliberation planner
feat: add assessment evidence executor
feat: score assessment evidence confidence
feat: rank assessment hypotheses
feat: add assessment simulations
feat: render persona-aware assessments
feat: wire assess command into Agent Adda
test: add assess regression scenarios
docs: document Agent Adda assess intelligence
```
