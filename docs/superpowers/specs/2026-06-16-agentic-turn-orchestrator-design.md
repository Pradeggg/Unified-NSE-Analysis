# Agent Adda Agentic Turn Orchestrator Design

Date: 2026-06-16

## Purpose

Agent Adda already has strong market tools, situation assessment, deterministic renderers, evidence gates, and LLM synthesis. The missing product capability is the analyst-like interaction loop: explaining the working path, preserving follow-up intent, binding next actions, registering artifacts, and producing grounded next steps.

This design adds a first-class `Agentic Turn Orchestrator` around the existing Agent Adda pipeline. It does not replace tool routing, evidence tools, renderers, or final synthesis. It coordinates them so Agent Adda behaves like a competent market research analyst across multi-turn workflows.

The first implementation slice targets the workflow demonstrated on 2026-06-16:

```text
market state -> sector strength -> quality shortlist -> user asks deep dive
-> RIC Sherlock batch report -> user asks email it
```

## Current Gap

The current pipeline is effectively:

```text
query -> classify intent -> execute tools -> render answer
```

This produces useful data, but the user experience can feel abrupt or disconnected because:

- Follow-ups such as "yes", "go ahead", "email it", "open the report", and "deep dive these" must be re-inferred instead of being bound to a prior proposed action.
- The system does not consistently expose what it is checking and why.
- Generated reports and artifacts are not consistently registered as conversation objects.
- Final synthesis answers do not always include a specific next action or caveat.
- Tone and behavior are spread across prompts, renderers, and ad hoc handlers rather than expressed as one runtime policy.

## Target Experience

Agent Adda should operate each meaningful turn as:

```text
query -> assess goal -> explain working path -> execute grounded evidence
-> audit evidence and gaps -> synthesize direct answer -> propose next action
-> bind the next action and artifacts for follow-up turns
```

Example:

```text
User: what is the current state of the market, sectors showing strength, any stocks to look at

Agent:
  I’ll check live market breadth and sector strength first, then filter
  for Stage 2 / quality breakout names.

  [runs tools]

  Market is mildly positive; breadth is constructive; Realty/FMCG/IT lead.
  Watch VBL, CEMPRO, ASTRAMICRO, RATEGAIN...

  Next logical action: run RIC Sherlock + chart report for the top 4.
```

If the user replies:

```text
sure go ahead
```

Agent Adda executes the bound `ric_sherlock_batch` action with the stored symbols. It does not reroute from the phrase alone.

## Architecture

Add a new orchestration layer around the existing pipeline:

```text
User Query
  -> LLM Situation Assessment
  -> Agentic Turn Orchestrator
  -> Tool Plan + Progress Updates
  -> Evidence Auditor
  -> Structured Renderer
  -> Final Synthesizer
  -> Next Action Binder
  -> Conversation Memory
```

The orchestrator owns the turn-level operating model. It decides how the agent should work through the turn, while existing components still decide how to fetch evidence and render domain output.

## Core Runtime Objects

### AgenticTurnState

```python
@dataclass
class AgenticTurnState:
    turn_id: str
    user_goal: str
    workflow: str
    expanded_query: str
    resolved_entities: list[str]
    evidence_plan: list[EvidenceStep]
    evidence_status: list[EvidenceStatus]
    artifacts: list[ArtifactRef]
    final_takeaway: str
    caveats: list[str]
    next_actions: list[BoundNextAction]
    created_at: str
```

This state is written after each meaningful turn and compacted into conversation memory. It gives future turns a structured source of truth instead of depending only on natural-language summaries.

### BoundNextAction

```python
@dataclass
class BoundNextAction:
    id: str
    label: str
    description: str
    action_type: str
    tool_plan: list[tuple[str, dict]]
    entities: list[str]
    artifact_targets: list[str]
    requires_confirmation: bool = True
```

Examples:

```json
{
  "id": "next_ric_top4",
  "label": "Run RIC Sherlock for top 4",
  "description": "Run RIC Sherlock + chart report for VBL, CEMPRO, ASTRAMICRO, RATEGAIN",
  "action_type": "ric_sherlock_batch",
  "entities": ["VBL", "CEMPRO", "ASTRAMICRO", "RATEGAIN"],
  "artifact_targets": ["html_report", "json_evidence"],
  "requires_confirmation": true
}
```

### ArtifactRef

```python
@dataclass
class ArtifactRef:
    id: str
    kind: str
    title: str
    path: str
    symbols: list[str]
    created_by_workflow: str
    created_at: str
```

Examples include HTML reports, JSON evidence packs, generated charts, CSV watchlists, screenshots, and email previews. Artifact references make "open it", "email the report", "summarize this", and "rerun with more history" deterministic.

### ProgressUpdate

```python
@dataclass
class ProgressUpdate:
    stage: str
    message: str
    evidence_dependency: str | None = None
    emit_policy: str = "if_slow"
```

Progress messages are not freeform hallucinated commentary. They are grounded to workflow stage and should not make claims before evidence has run.

## Workflow Profiles

The orchestrator classifies each turn into a bounded workflow profile:

```text
direct_answer
market_scan
stock_deep_dive
multi_stock_comparison
ric_sherlock_batch
portfolio_or_paper_trading
report_generation
email_dispatch
debug_or_system_review
clarification_needed
```

Each `WorkflowProfile` defines:

- required or recommended evidence
- progress update templates
- final answer shape
- caveat policy
- next-action policy
- artifact policy
- follow-up binding rules

V1 should implement the profiles needed for the research flow:

- `market_scan`
- `stock_deep_dive`
- `ric_sherlock_batch`
- `report_generation`
- `email_dispatch`

## Follow-Up Resolution Order

The follow-up router should use this priority:

```text
1. Explicit slash command
2. Bound next action confirmation
3. Artifact reference: it / report / this file / latest report
4. Entity set reference: these / above stocks / shortlisted names
5. LLM situation assessment
6. Semantic intent
7. Deterministic fallback
```

This prevents generic routing from misreading continuation phrases. It also avoids silent NIFTY fallback or accidental stock misbinding when the previous turn already contains a stronger structured reference.

## Progress Narration Policy

Progress narration is a product feature, not decorative text. It builds trust by showing the analysis path.

Rules:

- Emit progress only for multi-step workflows or slow operations.
- Use short, factual messages.
- Do not claim results before tools run.
- Prefer templates selected by workflow profile.
- Include why the next step is being run when useful.
- Avoid repetitive "thinking" text.

Examples:

```text
I’ll check live market breadth and sector strength first, then filter for quality breakout candidates.
```

```text
The market snapshot is available. I’m ranking the shortlist by Stage 2, RS, fundamentals, and sector alignment.
```

```text
The report generated successfully. I’m verifying the artifact and chart coverage before opening it.
```

## Final Answer Behavior

The final answer should answer four questions:

1. What did we find?
2. Why does it matter?
3. What caveat changes interpretation?
4. What is the next logical action?

The synthesizer should receive the `AgenticTurnState` in addition to tool evidence and structured render. It should not invent next actions; it should present actions that the orchestrator bound.

Tone contract:

- concise but transparent
- evidence-first
- pragmatic and direct
- specific numbers when available
- explicit caveats
- one logical next step when appropriate
- no generic financial filler
- no unsupported conviction

## Evidence Auditor

After tools run, the orchestrator should summarize:

- which evidence completed
- which evidence failed or was missing
- whether the answer can still be grounded
- which caveats should be elevated to the final answer

Example caveat from the RIC flow:

```text
PostgreSQL currently has only 25 EOD bars for these symbols, so charts are current but not true six-month charts until EOD backfill is completed.
```

This caveat belongs in the final answer, report body, and email note.

## Artifact And Action Examples

### Market Scan Turn

Evidence:

- `get_live_market_overview`
- `get_market_breadth`
- `run_quality_breakout_screener`

Bound next action:

```json
{
  "action_type": "ric_sherlock_batch",
  "entities": ["VBL", "CEMPRO", "ASTRAMICRO", "RATEGAIN"],
  "artifact_targets": ["html_report", "json_evidence"]
}
```

### RIC Sherlock Batch Turn

Evidence:

- symbol snapshot
- technical setup
- sector context
- Screener fundamentals
- recent announcements
- PG EOD chart history

Artifacts:

- latest HTML report
- timestamped HTML report
- JSON evidence pack
- CSV watchlist

Bound next actions:

- open latest report
- email latest report
- backfill 6-month PG EOD history
- rerun report after backfill

### Email Dispatch Turn

Input:

- latest artifact reference
- configured recipients

Output:

- subject
- recipients
- attachment path
- sent/draft status

Bound next actions:

- open sent report
- generate backfill task if chart caveat exists

## Integration Points

### `terminal/llm_situation_assessment.py`

Continue using this for context-aware assessment, but pass its output into the orchestrator instead of treating it as the full turn plan.

### `terminal/situation_assessment.py`

Keep deterministic fallback and clarification binding. Add conversion helpers from `SituationAssessment` to `AgenticTurnState`.

### `terminal/agent.py`

Wire the orchestrator before tool execution:

```text
assessment -> orchestrator.build_turn_plan() -> execute -> orchestrator.finalize_turn()
```

### `terminal/renderers/narrator.py`

Pass `AgenticTurnState` into final synthesis. The final answer should present the orchestrator's bound next actions and caveats.

### `terminal/conversation_memory.py`

Persist compact turn state:

- latest workflow
- latest entities
- latest artifacts
- latest bound next actions
- latest caveats

### `terminal/email_dispatcher.py`

Allow artifact-bound email dispatch so "email it" resolves through `ArtifactRef`, not only through report aliases or explicit paths.

## V1 Scope

Implement only the research workflow slice:

```text
market_scan -> stock_deep_dive -> ric_sherlock_batch -> report_generation -> email_dispatch
```

V1 must support:

- progress update templates for the above profiles
- bound next action creation and confirmation
- artifact registration for generated reports
- artifact-bound open/email follow-ups
- final answer caveat injection
- tests for multi-turn continuation phrases

V1 should not attempt:

- full autonomous planning
- arbitrary multi-agent delegation
- replacing the router
- replacing deterministic renderers
- global behavior changes for every command

## Testing Strategy

Unit tests:

- `BoundNextAction` confirmation detection: yes, sure, go ahead, do it.
- Artifact reference resolution: it, this report, latest report.
- Entity set resolution: these, above stocks, shortlisted names.
- Workflow profile selection for market scan, RIC batch, report generation, email dispatch.
- Caveat propagation into final answer.

Integration tests:

1. User asks current market state.
2. Agent runs market overview, breadth, and quality breakout screen.
3. Agent proposes RIC Sherlock for top candidates and binds action.
4. User says "sure go ahead".
5. Agent runs RIC batch for the bound symbols.
6. Agent registers HTML/JSON artifacts and reports caveats.
7. User says "email the report".
8. Agent emails the bound HTML artifact.

Regression tests:

- No silent NIFTY fallback when a prior stock/entity set exists.
- Existing slash commands still bypass orchestrator binding.
- Existing deterministic renderers still produce structured evidence.
- Final synthesizer does not invent unsupported next actions.

## Rollout Plan

1. Add orchestrator models and pure resolution functions.
2. Add workflow profiles for the V1 research slice.
3. Persist compact turn state in conversation memory.
4. Wire bound next action resolution before generic semantic routing.
5. Register artifacts from RIC/report/email flows.
6. Pass turn state into final synthesizer.
7. Add multi-turn regression scenarios.
8. Enable behind runtime flag:

```text
AGENT_ADDA_AGENTIC_ORCHESTRATOR=1
```

Default can be enabled in development first, then made default after the scenario suite passes.

## Acceptance Criteria

- A market scan can propose a RIC Sherlock batch with bound symbols.
- "sure go ahead" executes the bound batch without reinterpreting the phrase.
- Generated report paths are stored as artifacts.
- "email it" sends the latest bound report, not a random report alias.
- Final answers include evidence-grounded caveats and one logical next action.
- Progress updates are short, factual, and tied to the workflow.
- Existing market, stock, report, and email commands continue to work.

## Self-Review Notes

- No implementation code is included in this spec.
- V1 scope is intentionally limited to research workflows to avoid overengineering.
- Existing routers/renderers remain in place; the orchestrator coordinates them.
- Follow-up resolution order is explicit to avoid ambiguity.
- The chart-history caveat from the observed RIC workflow is captured as an example of evidence auditing.
