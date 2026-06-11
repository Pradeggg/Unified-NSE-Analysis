from __future__ import annotations


def test_agent_query_executes_selected_skill_store_plan(monkeypatch):
    import terminal.agent as agent_mod
    from terminal.agent import Agent
    from terminal.skills.runtime_assessment import SkillStoreRuntimeAssessment

    monkeypatch.setenv("AGENT_ADDA_MEMORY_PG", "0")
    monkeypatch.setenv("AGENT_ADDA_SKILL_STORE", "1")

    agent = Agent()
    agent.backend = None
    agent._stage_clarification_binding = lambda ctx: None
    agent._stage_unified_router = lambda ctx: None
    agent._stage_entity_topic = lambda ctx, entity_assessment=None: None
    agent._stage_situation_assessment = lambda ctx: None
    agent._stage_keyword_and_llm = lambda ctx: {
        "answer": "fallback",
        "trace": ctx.trace,
        "backend": agent.backend_name,
        "intent": "fallback",
    }

    assessment = SkillStoreRuntimeAssessment(
        applies=True,
        decision="select",
        selected_skill_id="market_skill_v1",
        selected_version=1,
        confidence=0.91,
        trace={
            "retrieval_id": 55,
            "reviewer_decision": {
                "decision": "select",
                "selected_skill_id": "market_skill_v1",
                "selected_version": 1,
                "candidate_ids": ["market_skill_v1"],
                "confidence": 0.91,
                "reason": "matched validated workflow",
                "findings": ["selected"],
            },
            "retrieved_candidates": [
                {
                    "skill_id": "market_skill_v1",
                    "metadata": {"output_contract": ["market_context"]},
                }
            ],
        },
    )

    card = {
        "id": "market_skill_v1",
        "version": 1,
        "status": "validated",
        "domain": "market_analysis",
        "title": "Market Skill",
        "tool_plan_template": [
            {"name": "market_context", "tool_name": "get_market_breadth", "params": {}}
        ],
        "sql_templates": [],
        "output_contract": ["market_context"],
        "metadata": {},
    }

    class Repo:
        def get_skill_card(self, skill_id, version=None):
            assert skill_id == "market_skill_v1"
            return card

        def log_execution(self, event):
            return 99

    agent._skill_store_repository = Repo()
    monkeypatch.setattr(agent_mod, "_stage_skill_store_assessment", lambda query, **kwargs: assessment)
    monkeypatch.setattr(
        agent_mod,
        "call_tool",
        lambda name, params: {"rows": [{"breadth": "ok"}], "row_count": 1, "as_of_date": "2026-06-05"},
    )

    result = agent._query_single("last 3 months market analysis and swing candidates")

    assert result["intent"] == "skill_store"
    assert "Skill Store selected `market_skill_v1`" in result["answer"]
    assert "market_context" in result["answer"]
    assert any(item.get("step") == "skill_store_assessment" for item in result["trace"])
    assert any(item.get("tool") == "skill_store.execute" for item in result["trace"])


def test_skill_store_execution_uses_final_narrative_layer(monkeypatch):
    import terminal.agent as agent_mod
    from terminal.agent import Agent
    from terminal.skills.runtime_assessment import SkillStoreRuntimeAssessment

    monkeypatch.setenv("AGENT_ADDA_MEMORY_PG", "0")
    monkeypatch.setenv("AGENT_ADDA_SKILL_STORE", "1")

    class Backend:
        def chat(self, messages, tools=None, max_tokens=None):
            assert max_tokens == 160
            return {"content": "The skill evidence points to a selective swing-trading tape."}

    agent = Agent()
    agent.backend = Backend()
    agent.backend_name = "Fake"
    agent._stage_clarification_binding = lambda ctx: None
    agent._stage_unified_router = lambda ctx: None
    agent._stage_entity_topic = lambda ctx, entity_assessment=None: None
    agent._stage_situation_assessment = lambda ctx: None
    agent._stage_keyword_and_llm = lambda ctx: {
        "answer": "fallback",
        "trace": ctx.trace,
        "backend": agent.backend_name,
        "intent": "fallback",
    }

    assessment = SkillStoreRuntimeAssessment(
        applies=True,
        decision="select",
        selected_skill_id="swing_skill_v1",
        selected_version=1,
        confidence=0.93,
        trace={
            "reviewer_decision": {
                "decision": "select",
                "selected_skill_id": "swing_skill_v1",
                "selected_version": 1,
                "candidate_ids": ["swing_skill_v1"],
                "confidence": 0.93,
            },
            "retrieved_candidates": [
                {"skill_id": "swing_skill_v1", "metadata": {"output_contract": ["swing_candidates"]}}
            ],
        },
    )
    card = {
        "id": "swing_skill_v1",
        "version": 1,
        "status": "validated",
        "domain": "market_analysis",
        "title": "Swing Skill",
        "tool_plan_template": [
            {"name": "swing_candidates", "tool_name": "get_market_breadth", "params": {}}
        ],
        "sql_templates": [],
        "output_contract": ["swing_candidates"],
        "metadata": {},
    }

    class Repo:
        def get_skill_card(self, skill_id, version=None):
            return card

    agent._skill_store_repository = Repo()
    monkeypatch.setattr(agent_mod, "_stage_skill_store_assessment", lambda query, **kwargs: assessment)
    monkeypatch.setattr(
        agent_mod,
        "call_tool",
        lambda name, params: {"rows": [{"symbol": "ABC", "score": 91}], "row_count": 1},
    )

    result = agent._query_single("find swing candidates")

    assert result["intent"] == "skill_store"
    assert "▶ INTERPRETATION" in result["answer"]
    assert "selective swing-trading tape" in result["answer"]


def test_agent_skill_store_failure_fails_open_to_keyword_stage(monkeypatch):
    import terminal.agent as agent_mod
    from terminal.agent import Agent

    monkeypatch.setenv("AGENT_ADDA_MEMORY_PG", "0")
    monkeypatch.setenv("AGENT_ADDA_SKILL_STORE", "1")

    agent = Agent()
    agent._stage_clarification_binding = lambda ctx: None
    agent._stage_unified_router = lambda ctx: None
    agent._stage_entity_topic = lambda ctx, entity_assessment=None: None
    agent._stage_situation_assessment = lambda ctx: None
    agent._stage_keyword_and_llm = lambda ctx: {
        "answer": "fallback still works",
        "trace": ctx.trace,
        "backend": agent.backend_name,
        "intent": "fallback",
    }

    def broken_stage(query, **kwargs):
        raise RuntimeError("repo down")

    monkeypatch.setattr(agent_mod, "_stage_skill_store_assessment", broken_stage)

    result = agent._query_single("last 3 months market analysis")

    assert result["intent"] == "fallback"
    assert result["answer"] == "fallback still works"
    assert any(item.get("step") == "skill_store_assessment" and item.get("error") for item in result["trace"])


def test_agent_initializes_skill_store_repository_with_project_dsn(monkeypatch):
    import terminal.agent as agent_mod
    from terminal.agent import Agent

    monkeypatch.setenv("AGENT_ADDA_MEMORY_PG", "0")
    monkeypatch.setenv("AGENT_ADDA_SKILL_STORE", "1")
    monkeypatch.setenv("AGENT_ADDA_PG_DSN", "dbname=agent_adda_test")

    seen = {}

    class Repo:
        def __init__(self, dsn=None):
            seen["dsn"] = dsn

    monkeypatch.setattr(agent_mod, "SkillStoreRepository", Repo)

    agent = Agent()

    assert agent._skill_store_repository is not None
    assert seen["dsn"] == "dbname=agent_adda_test"


def test_agent_passes_deterministic_keyword_intent_to_skill_store_assessment(monkeypatch):
    import terminal.agent as agent_mod
    from terminal.agent import Agent

    monkeypatch.setenv("AGENT_ADDA_MEMORY_PG", "0")
    monkeypatch.setenv("AGENT_ADDA_SKILL_STORE", "1")

    agent = Agent()
    agent._stage_clarification_binding = lambda ctx: None
    agent._stage_unified_router = lambda ctx: None
    agent._stage_entity_topic = lambda ctx, entity_assessment=None: None
    agent._stage_situation_assessment = lambda ctx: None
    agent._stage_keyword_and_llm = lambda ctx: {
        "answer": "keyword wins",
        "trace": ctx.trace,
        "backend": agent.backend_name,
        "intent": "symbol_quick_analysis",
    }

    captured = {}

    def fake_stage(query, **kwargs):
        captured.update(kwargs)
        return None

    monkeypatch.setattr(agent_mod, "_stage_skill_store_assessment", fake_stage)

    result = agent._query_single("RELIANCE")

    assert result["intent"] == "symbol_quick_analysis"
    assert captured["deterministic_intent"] == "symbol_quick_analysis"
    assert captured["deterministic_confidence"] >= 0.9


def test_failed_skill_execution_falls_open_to_keyword_stage(monkeypatch):
    import terminal.agent as agent_mod
    from terminal.agent import Agent
    from terminal.skills.runtime_assessment import SkillStoreRuntimeAssessment

    monkeypatch.setenv("AGENT_ADDA_MEMORY_PG", "0")
    monkeypatch.setenv("AGENT_ADDA_SKILL_STORE", "1")

    agent = Agent()
    agent._stage_clarification_binding = lambda ctx: None
    agent._stage_unified_router = lambda ctx: None
    agent._stage_entity_topic = lambda ctx, entity_assessment=None: None
    agent._stage_situation_assessment = lambda ctx: None
    agent._stage_keyword_and_llm = lambda ctx: {
        "answer": "fallback after failed skill",
        "trace": ctx.trace,
        "backend": agent.backend_name,
        "intent": "fallback",
    }

    assessment = SkillStoreRuntimeAssessment(
        applies=True,
        decision="select",
        selected_skill_id="bad_skill_v1",
        selected_version=1,
        confidence=0.9,
        trace={
            "reviewer_decision": {
                "decision": "select",
                "selected_skill_id": "bad_skill_v1",
                "selected_version": 1,
                "candidate_ids": ["bad_skill_v1"],
                "confidence": 0.9,
            }
        },
    )
    card = {
        "id": "bad_skill_v1",
        "version": 1,
        "status": "validated",
        "domain": "market_analysis",
        "title": "Bad Skill",
        "tool_plan_template": [
            {"name": "broken", "tool_name": "get_market_breadth", "params": {}}
        ],
        "sql_templates": [],
        "output_contract": ["broken"],
        "metadata": {},
    }

    class Repo:
        def get_skill_card(self, skill_id, version=None):
            return card

    agent._skill_store_repository = Repo()
    monkeypatch.setattr(agent_mod, "_stage_skill_store_assessment", lambda query, **kwargs: assessment)
    monkeypatch.setattr(agent_mod, "call_tool", lambda name, params: {"error": "boom"})

    result = agent._query_single("market swing candidates")

    assert result["intent"] == "fallback"
    assert result["answer"] == "fallback after failed skill"
    assert any(item.get("tool") == "skill_store.execute" for item in result["trace"])


def test_skill_store_plan_mode_records_interaction(monkeypatch):
    import terminal.agent as agent_mod
    from terminal.agent import Agent
    from terminal.permission_mode import PermissionMode
    from terminal.skills.runtime_assessment import SkillStoreRuntimeAssessment

    monkeypatch.setenv("AGENT_ADDA_MEMORY_PG", "0")
    monkeypatch.setenv("AGENT_ADDA_SKILL_STORE", "1")

    agent = Agent()
    agent.set_permission_mode(PermissionMode.PLAN)
    agent._stage_clarification_binding = lambda ctx: None
    agent._stage_unified_router = lambda ctx: None
    agent._stage_entity_topic = lambda ctx, entity_assessment=None: None
    agent._stage_situation_assessment = lambda ctx: None

    remembered = {}
    agent._remember_interaction = lambda user_input, answer, tool_results, turn_context=None: remembered.update(
        {"user_input": user_input, "answer": answer, "tool_results": tool_results, "turn_context": turn_context}
    )
    monkeypatch.setattr(
        agent_mod,
        "_stage_skill_store_assessment",
        lambda query, **kwargs: SkillStoreRuntimeAssessment(
            applies=True,
            decision="select",
            selected_skill_id="plan_skill_v1",
            selected_version=1,
            confidence=0.9,
            plan_preview=("step one", "step two"),
            trace={"reviewer_decision": {"decision": "select", "selected_skill_id": "plan_skill_v1"}},
        ),
    )

    result = agent._query_single("market workflow")

    assert result["intent"] == "skill_store_plan"
    assert remembered["user_input"] == "market workflow"
    assert "SKILL STORE PLAN" in remembered["answer"]


def test_skill_store_clarification_reply_reenters_skill_store(monkeypatch):
    import terminal.agent as agent_mod
    from terminal.agent import Agent
    from terminal.skills.runtime_assessment import SkillStoreRuntimeAssessment

    monkeypatch.setenv("AGENT_ADDA_MEMORY_PG", "0")
    monkeypatch.setenv("AGENT_ADDA_SKILL_STORE", "1")

    agent = Agent()
    agent._stage_unified_router = lambda ctx: None
    agent._stage_entity_topic = lambda ctx, entity_assessment=None: None
    agent._stage_situation_assessment = lambda ctx: None
    agent._stage_keyword_and_llm = lambda ctx: {
        "answer": "fallback",
        "trace": ctx.trace,
        "backend": agent.backend_name,
        "intent": "fallback",
    }

    calls = []

    def fake_stage(query, **kwargs):
        calls.append(query)
        if len(calls) == 1:
            return SkillStoreRuntimeAssessment(
                applies=True,
                decision="ask_clarification",
                confidence=0.8,
                missing_inputs=("timeframe",),
                clarification_question="What timeframe should I use?",
            )
        return None

    monkeypatch.setattr(agent_mod, "_stage_skill_store_assessment", fake_stage)

    first = agent._query_single("find swing candidates")
    second = agent._query_single("last 3 months")

    assert first["intent"] == "skill_store_clarification"
    assert calls[1] == "find swing candidates last 3 months"
    assert any(item.get("step") == "skill_store_clarification_binding" for item in second["trace"])


def test_skill_store_execution_memory_receives_execution_trace(monkeypatch):
    import terminal.agent as agent_mod
    from terminal.agent import Agent
    from terminal.skills.runtime_assessment import SkillStoreRuntimeAssessment

    monkeypatch.setenv("AGENT_ADDA_MEMORY_PG", "0")
    monkeypatch.setenv("AGENT_ADDA_SKILL_STORE", "1")

    agent = Agent()
    agent._stage_clarification_binding = lambda ctx: None
    agent._stage_unified_router = lambda ctx: None
    agent._stage_entity_topic = lambda ctx, entity_assessment=None: None
    agent._stage_situation_assessment = lambda ctx: None
    remembered = {}
    agent._remember_interaction = lambda user_input, answer, tool_results, turn_context=None: remembered.update(
        {"tool_results": tool_results, "turn_context": turn_context}
    )

    assessment = SkillStoreRuntimeAssessment(
        applies=True,
        decision="select",
        selected_skill_id="memory_skill_v1",
        selected_version=1,
        confidence=0.9,
        trace={
            "reviewer_decision": {
                "decision": "select",
                "selected_skill_id": "memory_skill_v1",
                "selected_version": 1,
                "candidate_ids": ["memory_skill_v1"],
            },
            "retrieved_candidates": [{"skill_id": "memory_skill_v1", "metadata": {"output_contract": ["evidence"]}}],
        },
    )
    card = {
        "id": "memory_skill_v1",
        "version": 1,
        "status": "validated",
        "domain": "market_analysis",
        "title": "Memory Skill",
        "tool_plan_template": [{"name": "evidence", "tool_name": "get_market_breadth", "params": {}}],
        "sql_templates": [],
        "output_contract": ["evidence"],
        "metadata": {},
    }

    class Repo:
        def get_skill_card(self, skill_id, version=None):
            return card

    agent._skill_store_repository = Repo()
    monkeypatch.setattr(agent_mod, "_stage_skill_store_assessment", lambda query, **kwargs: assessment)
    monkeypatch.setattr(agent_mod, "call_tool", lambda name, params: {"rows": [{"x": 1}], "row_count": 1})

    agent._query_single("market memory workflow")

    assert remembered["tool_results"]
    assert remembered["tool_results"][0]["tool"] == "skill_store.execute"


def test_merge_output_contract_uses_union_of_candidate_contracts():
    import terminal.agent as agent_mod
    from terminal.skills.runtime_assessment import SkillStoreRuntimeAssessment

    assessment = SkillStoreRuntimeAssessment(
        applies=True,
        decision="merge",
        confidence=0.9,
        trace={
            "retrieved_candidates": [
                {"skill_id": "a", "metadata": {"output_contract": ["alpha", "shared"]}},
                {"skill_id": "b", "metadata": {"output_contract": ["beta", "shared"]}},
            ]
        },
    )

    assert agent_mod._skill_store_output_contract(assessment) == ["alpha", "shared", "beta"]
