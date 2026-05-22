# Unified Router Refactor Design

Date: 2026-05-22

## Problem

Agent Adda's routing intelligence is currently split across several paths:

- `terminal.situation_assessment` handles contextual follow-ups.
- `terminal.agent._keyword_intent` handles most direct natural-language requests.
- `nse_agent.py` handles several terminal/slash-command shortcuts before the agent path.
- `terminal.assessment_llm` acts as an optional LLM fallback for ambiguous follow-ups.
- Tool execution and response synthesis are coupled to whichever route branch won.

This fragmentation causes inconsistent behavior:

- A direct compound query can be routed by a narrow branch before the system understands the whole ask.
- Follow-ups can bind only to the last step of a multi-step workflow instead of the whole workflow.
- Contextual replies such as `1`, `A`, `yes`, `open it`, or `based on the above` require special handling in multiple places.
- NEXT OPTIONS are improving, but not every option is guaranteed to be executable.
- Data-grounded asks can still fall through to generic prose unless every route family enforces grounding.

The target is a single unified router that produces one validated route decision before any answer or tool execution happens.

## Goals

- Route every user input through one first-class route-decision contract.
- Support both direct asks and contextual follow-ups.
- Correctly handle compound requests, such as live price plus F&O plus intraday setup.
- Bind multi-turn follow-ups to the right context: prior symbol, report, workflow, result list, or pending option.
- Make NEXT OPTIONS executable and validated before display.
- Keep deterministic routing as the default for reliability.
- Use GPT-5.5 high-reasoning assessment only for ambiguity resolution and context reflection, not as an unchecked executor.
- Persist lossless structured context to PostgreSQL and use summaries only as routing aids.
- Expose route traces for debugging and test assertions.

## Non-Goals

- Do not rewrite all route logic in one change.
- Do not make the LLM the primary router for every request.
- Do not remove existing tools or response renderers during the first migration step.
- Do not answer market/data-grounded requests from compressed prose summaries alone.
- Do not introduce an embedding classifier until the unified route contract and validation layer are stable.

## Recommended Approach

Use a unified deterministic router with candidate scoring and optional LLM-assisted ambiguity resolution.

Every query enters the same pipeline:

```text
User input
  -> ConversationContextStore
  -> UnifiedRouter
      -> pending option binder
      -> candidate providers
      -> context binder
      -> route scorer
      -> optional GPT-5.5 ambiguity resolver
      -> route validator
      -> executable RouteDecision
  -> AgentExecutor
  -> Synthesizer
  -> ContextCompressor/MemoryWriter
  -> Response with validated NEXT OPTIONS
```

The agent must not execute a tool plan or answer from context unless a `RouteDecision` says the response is grounded, valid, and bound to the right context.

## Route Decision Contract

Introduce typed route objects in a new router module.

```python
@dataclass
class RouteDecision:
    decision_id: str
    intent: str
    route_type: RouteType
    confidence: Confidence
    user_is_asking: str
    context_binding: ContextBinding
    evidence_requirements: list[EvidenceRequirement]
    tool_plan: list[ToolCallSpec]
    next_options: list[NextOption]
    source_policy: SourcePolicy
    reasoning_summary: RouteReasoningSummary
    validation: RouteValidation
```

Route types:

- `direct_tool_plan`
- `contextual_answer`
- `clarification`
- `compound_plan`
- `fallback_llm`
- `blocked_ungrounded`

The same object should represent direct routes, follow-up routes, pending option replies, report actions, recommendation report actions, visual scans, and market-situation routes.

## Router Pipeline

`UnifiedRouter.route(user_input, context_pack) -> RouteDecision`

Pipeline stages:

1. Normalize input for routing.
   Fix common typos such as `pricies`, `recommendataion`, and `mins`, while preserving the original user text for display.

2. Bind pending options first.
   If the user replies with `A`, `B`, `1`, or option text, return the stored bound action directly. Do not re-resolve symbols from the reply.

3. Classify context shape.
   Identify whether the input is a new direct ask, prior-result follow-up, report follow-up, workflow continuation, clarification reply, or unrelated query.

4. Generate candidates.
   Candidate providers propose possible routes without executing tools.

5. Bind context.
   Attach prior symbols, indices, sectors, report paths, workflow outputs, source trail, freshness, and result groups.

6. Score candidates.
   Prefer routes that cover all requested tasks, bind explicit entities, satisfy evidence requirements, and avoid unsupported assumptions.

7. Validate winning route.
   Ensure tools exist, args are valid, symbols are canonical, reports exist, evidence requirements are covered, and NEXT OPTIONS are executable.

8. Return one `RouteDecision`.
   The executor consumes this object. It should not repeat hidden routing logic.

## Context And Memory Model

Replace last-turn-only behavior with a structured context pack.

```python
@dataclass
class ContextPack:
    current_user_input: str
    recent_turns: list[TurnContext]
    active_symbols: list[str]
    active_indices: list[str]
    active_sectors: list[str]
    active_reports: list[ReportArtifact]
    active_workflow: WorkflowContext | None
    pending_options: list[NextOption]
    source_trails: list[SourceTrail]
    freshness: FreshnessSummary
```

The context store should retain at least the last five turns, but active workflows and reports should remain addressable beyond that short window while the session is active.

### Workflow Context

Multi-step workflows such as Stock Sherlock need a first-class context object.

```python
WorkflowContext(
    workflow_type="stock_sherlock",
    subject="MANINDS",
    steps=[
        {"id": "live_quote", "tools": ["get_live_quote"], "symbols": ["MANINDS"]},
        {"id": "technical_setup", "tools": ["get_technical_setup"], "symbols": ["MANINDS"]},
        {"id": "fundamentals", "tools": ["scrape_screener_in", "get_latest_results"], "symbols": ["MANINDS"]},
        {"id": "catalysts", "tools": ["search_latest_catalysts"], "symbols": ["MANINDS"]},
        {"id": "trade_setup", "tools": ["explain_intraday_setup", "get_intraday_analysis"], "symbols": ["MANINDS"]},
    ],
    consolidated_evidence={"symbols": ["MANINDS"], "result_type": "stock_sherlock"}
)
```

When the user asks "Based on the above what would be your recommendation", the router should bind to the full workflow, not only the final step.

### Report Artifacts

Generated reports should be stored as structured artifacts.

```python
ReportArtifact(
    path="/Users/pgorai/Documents/Projects/Unified-NSE-Analysis/reports/generated/example.html",
    report_type="grounded_recommendation",
    symbols=["DIXON", "DMART"],
    indices=["NIFTY 50"],
    sectors=["Consumer Durables"],
    generated_at="2026-05-22T14:30:00+05:30",
    evidence_json_path="/Users/pgorai/Documents/Projects/Unified-NSE-Analysis/reports/generated/example_evidence.json",
    title="Grounded Recommendation Report"
)
```

This supports follow-ups such as:

- "open it"
- "review the contents"
- "why is MTF insufficient"
- "summarize the recommendations"
- "rerun with these stocks"

## Context Compression

Use two layers:

1. Lossless structured facts.
   Store symbols, tools, args, source trails, report paths, result groups, freshness, workflow step outputs, selected options, and generated artifacts as PostgreSQL rows.

2. Intelligent summary.
   Generate compact summaries for LLM routing and display. Summaries can be lossy because they are not the source of truth.

Principle: compress prose, not evidence.

## Candidate Providers

Each provider proposes route candidates. No provider executes tools directly.

```python
class CandidateProvider(Protocol):
    name: str

    def propose(self, user_input: str, context: ContextPack) -> list[RouteCandidate]:
        """Return zero or more route candidates without executing tools."""
```

Initial providers:

- `PendingOptionProvider`
  Handles `A`, `B`, `1`, option text. Highest priority if matched.

- `EntityTopicProvider`
  Wraps `assess_entity_topic_request()`.

- `ContextualFollowupProvider`
  Wraps most of `assess_followup()`.

- `DirectIntentProvider`
  Wraps `_keyword_intent()`.

- `CompoundStockProvider`
  Handles direct compound symbol requests.

- `ReportProvider`
  Handles open/read/summarize/report follow-ups.

- `RecommendationProvider`
  Handles symbol, index, and sector recommendation reports.

- `VisualScanProvider`
  Handles visual scan requests.

- `MarketSituationProvider`
  Wraps `_build_market_situation_assessment_plan()`.

- `LLMAmbiguityProvider`
  Runs only when top deterministic candidates are close or low-confidence.

## Candidate Scoring

Score candidates explicitly.

Positive signals:

- Explicit entity match.
- Prior context binding match.
- Covers all requested tasks.
- Required tools are available.
- Evidence freshness matches the request.
- Direct command match.
- Bound option match.

Negative signals:

- Unresolved symbol.
- Missing required evidence.
- Ungrounded answer risk.
- Partial compound coverage.
- Needs stale data for a live request.
- Requires a report path that does not exist.

The route trace should include the winning candidate, losing candidates, and the main scoring reasons.

## Compound Query Handling

Example:

```text
live prices for dixon tech and the analysis of the F&O data and intraday tradesetup in 5 mins
```

Expected winning route:

```text
intent: compound_stock_intraday_fno
route_type: compound_plan
subject: DIXON
```

Expected tool plan:

```text
1. resolve_symbol("dixon tech")
2. get_live_quote("DIXON")
3. get_fno_overview("DIXON")
4. explain_intraday_setup("DIXON", timeframe="5m")
5. get_intraday_analysis("DIXON", interval="5m")
```

If the symbol is not F&O eligible, the route should still return live quote and intraday setup, while marking F&O unavailable. It must not silently fall back to NIFTY.

## Validation Gate

Before execution, validate:

- All tools exist in `TOOL_REGISTRY`.
- Tool args match function signatures.
- Required args are present.
- Symbols are canonical or explicitly unresolved.
- Report paths exist.
- A route does not silently drop requested tasks.
- Compound routes include a coverage map.
- Data-grounded asks have tool-backed evidence.
- NEXT OPTIONS have executable bound actions.

Validation failures should produce either a corrected lower-scope route or a `blocked_ungrounded` route with executable options.

## Execution Model

After the router returns a validated `RouteDecision`, the agent path becomes:

```text
decision = router.route(user_input, context_pack)

if decision.route_type == "clarification":
    render NEXT OPTIONS
elif decision.route_type == "contextual_answer":
    render from bound context
elif decision.route_type in {"direct_tool_plan", "compound_plan"}:
    execute tool_plan
    synthesize grounded answer
elif decision.route_type == "blocked_ungrounded":
    explain missing evidence with executable options
else:
    controlled fallback
```

`Agent._query_single()` should gradually shrink to context loading, router invocation, execution, rendering, and context writing.

## Output Requirements

Responses should show a compact situation assessment when useful.

```text
▶ SITUATION ASSESSMENT
User is asking: live price, F&O data, and 5m intraday setup for DIXON
Context: new direct symbol request
Decision: compound_stock_intraday_fno (high)
Evidence: live quote + F&O overview + 5m intraday setup
Coverage: live price ok, F&O ok/unavailable, intraday ok
```

NEXT OPTIONS should be concise, executable, and bound:

```text
▶ NEXT OPTIONS
[A] Run 5m intraday follow-up for top 5 recommendations - Use: A
[B] Open the HTML report - Use: B
[C] Explain why rejected names failed - Use: C
```

The option should not be rendered unless its bound route/tool plan validates.

## Migration Plan

1. Add route contracts.
2. Add `UnifiedRouter` that wraps existing functions without changing behavior.
3. Add route trace and validation.
4. Move pending option binding into the router.
5. Move situation assessment into `ContextualFollowupProvider`.
6. Move `_keyword_intent()` into `DirectIntentProvider`.
7. Add `CompoundStockProvider`.
8. Add `ConversationContextStore`.
9. Add PostgreSQL persistence for lossless context.
10. Update `Agent._query_single()` to consume `RouteDecision`.
11. Add routing regression tests from real failures.
12. Gradually remove old branch logic after parity tests pass.

## Test Plan

Add focused tests for:

- Direct compound route: Dixon live price + F&O + 5m intraday setup.
- F&O unavailable route: symbol-specific partial coverage without NIFTY fallback.
- Sherlock workflow context: recommendation follow-up binds to all five steps.
- Stage 2 follow-up: "last 30 mins" offers executable intraday/EOD options.
- Report follow-up: "open it" opens the exact generated report.
- Report review: "why is MTF insufficient" reads report and evidence JSON.
- Option reply: `1`, `A`, `B.`, and option text execute the prior bound route.
- Grounding guard: data scans cannot produce prose without tool evidence.
- Candidate trace: winning and losing candidates are visible for debugging.
- NEXT OPTIONS validation: unknown tools or missing args suppress invalid options.

## Success Criteria

- The Dixon prompt routes to DIXON, not NIFTY.
- MANINDS "based on above recommendation" binds to the full Sherlock workflow.
- `1`, `A`, `yes`, and option text execute the prior bound option when one exists.
- Report follow-ups open/read/summarize the exact generated report.
- NEXT OPTIONS are only shown if executable.
- Every route has a trace explaining why it won.
- No data-grounded query can be answered without validated evidence.
- Existing direct routes continue to pass through compatibility wrappers during migration.

## Open Decisions

- Exact PostgreSQL schema for lossless conversation context.
- Whether route traces should be always shown, debug-only, or compact-by-default.
- Whether the LLM ambiguity resolver should run synchronously or only after deterministic low-confidence routes.
- How long active workflows should remain addressable after completion.
