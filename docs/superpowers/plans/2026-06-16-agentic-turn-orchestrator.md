# Agentic Turn Orchestrator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a runtime-gated Agentic Turn Orchestrator that binds follow-up confirmations, remembers generated artifacts, and appends grounded next actions to Agent Adda research answers.

**Architecture:** Implement V1 as a small pure-Python orchestration module wired around the existing pipeline. The orchestrator will not replace situation assessment, semantic intent, tools, or renderers; it will persist compact turn state, resolve bound follow-ups before generic routing, and add one grounded next-action block after successful tool-backed answers.

**Tech Stack:** Python dataclasses, existing `terminal.agent.Agent` pipeline, `terminal.conversation_memory.ConversationMemory`, `terminal.tools.TOOL_REGISTRY`, pytest.

---

## File Structure

- Create `terminal/agentic_orchestrator.py`
  - Owns dataclasses (`ArtifactRef`, `BoundNextAction`, `AgenticTurnState`) and pure functions for runtime flag checks, confirmation detection, artifact extraction, next-action inference, state serialization, and bound-action resolution.
- Modify `terminal/conversation_memory.py`
  - Adds `agentic_state` to session snapshots so the latest orchestrator state survives PostgreSQL reloads.
- Modify `terminal/agent.py`
  - Hydrates latest agentic state in `Agent.__init__`.
  - Adds `_stage_agentic_bound_action` after clarification binding and before unified router.
  - Updates `_remember_interaction` to refresh and persist `AgenticTurnState` after tool-backed answers.
  - Appends a concise `▶ NEXT ACTION` block when the orchestrator binds a follow-up.
- Create `tests/test_agentic_orchestrator.py`
  - Unit tests for pure resolution, serialization, artifact extraction, and next-action inference.
- Modify `tests/test_conversation_memory.py`
  - Regression test for snapshot round-trip of `agentic_state`.
- Create `tests/test_agentic_turn_flow.py`
  - Pipeline-level smoke test for `"sure go ahead"` resolving to the bound action without falling into generic routing.

## Task 1: Pure Orchestrator Models And Resolution

**Files:**
- Create: `terminal/agentic_orchestrator.py`
- Test: `tests/test_agentic_orchestrator.py`

- [ ] **Step 1: Write failing tests for confirmation, artifacts, next actions, and serialization**

```python
from terminal.agentic_orchestrator import (
    AgenticTurnState,
    BoundNextAction,
    action_from_confirmation,
    agentic_orchestrator_enabled,
    build_agentic_turn_state,
    extract_artifacts,
)


def test_enabled_flag_accepts_truthy_values(monkeypatch):
    monkeypatch.setenv("AGENT_ADDA_AGENTIC_ORCHESTRATOR", "1")
    assert agentic_orchestrator_enabled() is True


def test_confirmation_resolves_latest_bound_action():
    state = AgenticTurnState(
        user_goal="find market leaders",
        workflow="market_scan",
        next_actions=[
            BoundNextAction(
                id="next_ric_top4",
                label="Run RIC Sherlock for top 4",
                description="Run RIC Sherlock for VBL, CEMPRO, ASTRAMICRO, RATEGAIN",
                action_type="tool_plan",
                tool_plan=[("run_portfolio_ric_sherlock", {"symbols": ["VBL", "CEMPRO", "ASTRAMICRO", "RATEGAIN"]})],
                entities=["VBL", "CEMPRO", "ASTRAMICRO", "RATEGAIN"],
            )
        ],
    )
    action = action_from_confirmation("sure go ahead", state)
    assert action is not None
    assert action.id == "next_ric_top4"


def test_extract_artifacts_from_report_tool_result():
    artifacts = extract_artifacts([
        {
            "tool": "run_portfolio_ric_sherlock",
            "result": {
                "html_path": "reports/portfolio/latest_portfolio_ric_sherlock.html",
                "json_path": "reports/portfolio/latest_portfolio_ric_sherlock.json",
                "symbols": ["VBL", "CEMPRO"],
            },
        }
    ])
    assert [a.kind for a in artifacts] == ["html_report", "json_evidence"]
    assert artifacts[0].path.endswith(".html")


def test_build_market_scan_binds_ric_action_from_screen_result():
    state = build_agentic_turn_state(
        user_input="what is the market state and stocks to look at",
        intent="market_swing_candidates",
        tool_results=[
            {
                "tool": "run_quality_breakout_screener",
                "result": {
                    "items": [
                        {"symbol": "VBL"},
                        {"symbol": "CEMPRO"},
                        {"symbol": "ASTRAMICRO"},
                        {"symbol": "RATEGAIN"},
                    ]
                },
            }
        ],
        answer="Watch VBL, CEMPRO, ASTRAMICRO, RATEGAIN.",
    )
    assert state.workflow == "market_scan"
    assert state.next_actions
    assert state.next_actions[0].entities == ["VBL", "CEMPRO", "ASTRAMICRO", "RATEGAIN"]
    assert "RIC Sherlock" in state.next_actions[0].label


def test_state_round_trip_preserves_bound_action():
    state = AgenticTurnState(
        user_goal="email the latest report",
        workflow="email_dispatch",
        next_actions=[
            BoundNextAction(
                id="email_latest",
                label="Email latest report",
                description="Email latest HTML report",
                action_type="tool_plan",
                tool_plan=[("get_last_report", {})],
            )
        ],
    )
    restored = AgenticTurnState.from_dict(state.to_dict())
    assert restored.next_actions[0].tool_plan == [("get_last_report", {})]
```

- [ ] **Step 2: Run tests and confirm they fail**

Run: `pytest tests/test_agentic_orchestrator.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'terminal.agentic_orchestrator'`.

- [ ] **Step 3: Implement `terminal/agentic_orchestrator.py`**

Key implementation signatures:

```python
def agentic_orchestrator_enabled() -> bool: ...
def is_confirmation(text: str) -> bool: ...
def action_from_confirmation(text: str, state: AgenticTurnState | None) -> BoundNextAction | None: ...
def extract_artifacts(tool_results: list[dict[str, Any]]) -> list[ArtifactRef]: ...
def build_agentic_turn_state(... ) -> AgenticTurnState | None: ...
def append_next_action_block(answer: str, state: AgenticTurnState | None) -> str: ...
```

The implementation must keep behavior deterministic and return `None` when no grounded action can be bound.

- [ ] **Step 4: Run tests and confirm they pass**

Run: `pytest tests/test_agentic_orchestrator.py -q`

Expected: PASS.

## Task 2: Persist Agentic State In Conversation Memory

**Files:**
- Modify: `terminal/conversation_memory.py`
- Modify: `tests/test_conversation_memory.py`

- [ ] **Step 1: Add failing round-trip test**

Add a test that sets `memory.agentic_state = {"workflow": "market_scan", "next_actions": [{"id": "next_ric_top4"}]}`, round-trips through `to_snapshot()` and `from_snapshot()`, and asserts the restored value is identical.

- [ ] **Step 2: Run the focused test**

Run: `pytest tests/test_conversation_memory.py -q`

Expected: FAIL because `agentic_state` is not serialized.

- [ ] **Step 3: Add `agentic_state` field and snapshot wiring**

Add this field to `ConversationMemory`:

```python
agentic_state: dict[str, Any] = field(default_factory=dict)
```

Add `"agentic_state": dict(self.agentic_state),` to `to_snapshot()`.

Add this to `from_snapshot()`:

```python
memory.agentic_state = dict(data.get("agentic_state") or {})
```

- [ ] **Step 4: Run memory tests**

Run: `pytest tests/test_conversation_memory.py -q`

Expected: PASS.

## Task 3: Wire Bound Follow-Up Stage Into Agent

**Files:**
- Modify: `terminal/agent.py`
- Test: `tests/test_agentic_turn_flow.py`

- [ ] **Step 1: Add failing pipeline smoke test**

Create a test that constructs an `Agent`, injects `_agentic_turn_state` with a bound action for `get_last_report`, enables `AGENT_ADDA_AGENTIC_ORCHESTRATOR=1`, monkeypatches `_execute_plan` to capture the plan, calls `_query_single("sure go ahead")`, and asserts the captured plan came from the bound action.

- [ ] **Step 2: Run the failing smoke test**

Run: `pytest tests/test_agentic_turn_flow.py -q`

Expected: FAIL because `_stage_agentic_bound_action` does not exist.

- [ ] **Step 3: Import orchestrator helpers and hydrate state**

Add imports near the existing situation-assessment imports:

```python
from .agentic_orchestrator import (
    AgenticTurnState,
    action_from_confirmation,
    agentic_orchestrator_enabled,
    append_next_action_block,
    build_agentic_turn_state,
)
```

In `Agent.__init__`, hydrate:

```python
self._agentic_turn_state = AgenticTurnState.from_dict(self._memory.agentic_state) if self._memory.agentic_state else None
```

- [ ] **Step 4: Add `_stage_agentic_bound_action`**

Add the stage after `_stage_clarification_binding` and before `_stage_unified_router`. If enabled and a confirmation resolves, execute the bound `tool_plan`, synthesize the result using `_synthesize_and_narrate`, build turn context, remember interaction, and return intent `agentic_bound_action`.

- [ ] **Step 5: Update `_query_single` order**

Insert:

```python
or self._stage_agentic_bound_action(ctx)
```

between clarification binding and unified router.

- [ ] **Step 6: Run the smoke test**

Run: `pytest tests/test_agentic_turn_flow.py -q`

Expected: PASS.

## Task 4: Refresh State And Append Next Action Blocks

**Files:**
- Modify: `terminal/agent.py`
- Test: `tests/test_agentic_turn_flow.py`

- [ ] **Step 1: Add test for answer next-action block**

Use a market-scan-like `tool_results` with `run_quality_breakout_screener` and call `_remember_interaction()` through a test helper or direct invocation. Assert `Agent._agentic_turn_state.next_actions[0].entities` contains the screen symbols.

- [ ] **Step 2: Run the failing test**

Run: `pytest tests/test_agentic_turn_flow.py -q`

Expected: FAIL until `_remember_interaction` refreshes orchestrator state.

- [ ] **Step 3: Update `_remember_interaction`**

When `agentic_orchestrator_enabled()` is true and the turn has tool results or a `TurnContext`, call `build_agentic_turn_state(...)`. If it returns a state, assign `self._agentic_turn_state`, persist `self._memory.agentic_state = state.to_dict()`, and save with the existing PostgreSQL persistence path.

- [ ] **Step 4: Append next-action block in deterministic stages**

Before readiness metadata in tool-backed stages, call `append_next_action_block(answer_body + ctx.mode_suffix, self._agentic_turn_state)` only after state has been built. Keep V1 scoped to deterministic tool-backed answers; do not mutate pure LLM text without tool evidence.

- [ ] **Step 5: Run flow tests**

Run: `pytest tests/test_agentic_turn_flow.py tests/test_agentic_orchestrator.py -q`

Expected: PASS.

## Task 5: Regression Suite

**Files:**
- No additional code unless tests reveal a regression.

- [ ] **Step 1: Run situation and routing regressions**

Run:

```bash
pytest \
  tests/test_situation_assessment.py \
  tests/test_situation_assessment_scenarios.py \
  tests/test_llm_situation_assessment.py \
  tests/test_nse_agent_report_context.py \
  tests/test_routing_smoke.py \
  -q
```

Expected: PASS.

- [ ] **Step 2: Run focused full set**

Run:

```bash
pytest \
  tests/test_agentic_orchestrator.py \
  tests/test_agentic_turn_flow.py \
  tests/test_conversation_memory.py \
  tests/test_terminal_agent_market_prompt.py \
  tests/test_agent_tooling_expansion_scenarios.py \
  -q
```

Expected: PASS.

- [ ] **Step 3: Manual terminal validation**

Run with the feature enabled:

```bash
AGENT_ADDA_AGENTIC_ORCHESTRATOR=1 python -m terminal.agent
```

Manual scenario:

```text
what is the current state of the market, which sectors or indices are showing strength any specific stock that we should look at
sure go ahead
email it
```

Expected:
- First response proposes one RIC Sherlock/report next action with concrete symbols.
- `"sure go ahead"` executes the bound action, not generic NIFTY fallback.
- `"email it"` resolves to the latest report artifact or asks a specific report clarification if no report artifact exists.

## Self-Review

- Spec coverage: V1 covers bound next actions, compact state persistence, artifact extraction, follow-up confirmation, next-action final answer block, and regression tests. Full LLM prompt augmentation is intentionally deferred because V1 should stabilize deterministic orchestration first.
- Placeholder scan: No implementation step uses unresolved placeholders; each code change has exact files, signatures, and commands.
- Type consistency: `AgenticTurnState`, `BoundNextAction`, and `ArtifactRef` are defined in Task 1 and reused consistently in later tasks.
