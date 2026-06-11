from __future__ import annotations

import pytest


class FakeSkillRepo:
    def __init__(self, cards):
        self.cards = {(card["id"], card["version"]): card for card in cards}

    def get_skill_card(self, skill_id, version=None):
        if version is None:
            versions = [key_version for key_id, key_version in self.cards if key_id == skill_id]
            if not versions:
                return None
            version = max(versions)
        return self.cards.get((skill_id, version))


def _review_decision(**overrides):
    from terminal.skills.reviewer import ReviewDecision

    value = {
        "decision": "select",
        "selected_skill_id": "market_3m_rotation_swing_v1",
        "selected_version": 1,
        "candidate_ids": ("market_3m_rotation_swing_v1",),
        "reason": "selected",
        "confidence": 0.86,
    }
    value.update(overrides)
    return ReviewDecision(**value)


def _card(**overrides):
    value = {
        "id": "market_3m_rotation_swing_v1",
        "version": 1,
        "status": "validated",
        "domain": "market_analysis",
        "title": "3M Market Rotation Swing",
        "description": "Market rotation workflow",
        "input_patterns": ["3 month market swing candidates"],
        "tags": ["market_regime", "swing"],
        "evidence_required": {"tables": ["market.index_eod"]},
        "output_contract": ["ranked_candidates", "risks"],
        "validation_rules": ["required_tables_exist", "sql_is_read_only"],
        "tool_plan_template": [
            {
                "name": "market_context",
                "tool_name": "get_live_market_overview",
                "params": {"mode": "eod"},
                "required": True,
            }
        ],
        "sql_templates": [
            {
                "name": "index_returns",
                "sql": "SELECT trade_date, index_symbol, close FROM market.index_eod WHERE trade_date >= :start_date LIMIT :limit",
                "required_params": ["start_date", "limit"],
                "expected_columns": ["trade_date", "index_symbol", "close"],
                "row_limit": 100,
                "safety_status": "passed",
            }
        ],
        "metadata": {
            "report_lookup_templates": [
                {
                    "name": "latest_top_picks",
                    "report_name": "top_picks",
                    "params": {"latest": True},
                }
            ]
        },
    }
    metadata = dict(value["metadata"])
    metadata.update(overrides.pop("metadata", {}) or {})
    value.update(overrides)
    value["metadata"] = metadata
    return value


def test_valid_review_decision_becomes_execution_plan():
    from terminal.skills.execution_plan import build_skill_execution_plan

    plan = build_skill_execution_plan(
        _review_decision(),
        repository=FakeSkillRepo([_card()]),
        params={"start_date": "2026-03-01", "limit": 200},
        available_tools={"get_live_market_overview"},
        available_reports={"top_picks"},
    )

    assert plan.skill_ids == ("market_3m_rotation_swing_v1",)
    assert plan.skill_versions == {"market_3m_rotation_swing_v1": 1}
    assert [step.step_type for step in plan.steps] == ["tool_call", "sql_template", "report_lookup"]
    assert plan.steps[0].target == "get_live_market_overview"
    assert plan.steps[0].params == {"mode": "eod"}
    assert plan.steps[1].target == "index_returns"
    assert plan.steps[1].params == {"start_date": "2026-03-01", "limit": 200}
    assert plan.steps[2].target == "top_picks"
    assert plan.to_dict()["steps"][1]["step_type"] == "sql_template"


def test_missing_required_sql_params_fails():
    from terminal.skills.execution_plan import build_skill_execution_plan

    with pytest.raises(ValueError, match="missing required parameter: start_date"):
        build_skill_execution_plan(
            _review_decision(),
            repository=FakeSkillRepo([_card()]),
            params={"limit": 100},
            available_tools={"get_live_market_overview"},
            available_reports={"top_picks"},
        )


def test_unknown_tool_fails():
    from terminal.skills.execution_plan import build_skill_execution_plan

    with pytest.raises(ValueError, match="unknown tool: get_live_market_overview"):
        build_skill_execution_plan(
            _review_decision(),
            repository=FakeSkillRepo([_card()]),
            params={"start_date": "2026-03-01", "limit": 100},
            available_tools={"get_symbol_snapshot"},
            available_reports={"top_picks"},
        )


def test_unknown_sql_template_reference_fails():
    from terminal.skills.execution_plan import build_skill_execution_plan

    card = _card(
        metadata={
            "execution_steps": [
                {"step_type": "sql_template", "name": "missing_sql", "template_name": "missing_sql"},
            ]
        },
        sql_templates=[],
    )

    with pytest.raises(ValueError, match="unknown SQL template: missing_sql"):
        build_skill_execution_plan(
            _review_decision(),
            repository=FakeSkillRepo([card]),
        )


def test_unknown_step_type_fails():
    from terminal.skills.execution_plan import build_skill_execution_plan

    card = _card(metadata={"execution_steps": [{"step_type": "python", "name": "run_code"}]})

    with pytest.raises(ValueError, match="unknown execution step type: python"):
        build_skill_execution_plan(
            _review_decision(),
            repository=FakeSkillRepo([card]),
        )


def test_non_executable_reviewer_decision_fails_closed():
    from terminal.skills.execution_plan import build_skill_execution_plan

    with pytest.raises(ValueError, match="review decision is not executable"):
        build_skill_execution_plan(
            _review_decision(decision="ask_clarification", selected_skill_id=None, selected_version=None),
            repository=FakeSkillRepo([_card()]),
        )


def test_merge_decision_preserves_all_selected_skill_ids():
    from terminal.skills.execution_plan import build_skill_execution_plan

    technical = _card(id="technical_breakout_v1", version=1, tool_plan_template=[], metadata={"report_lookup_templates": []})
    fundamental = _card(
        id="fundamental_quality_v1",
        version=2,
        tool_plan_template=[],
        sql_templates=[],
        metadata={"report_lookup_templates": []},
    )

    plan = build_skill_execution_plan(
        _review_decision(
            decision="merge",
            selected_skill_id=None,
            selected_version=None,
            candidate_ids=("technical_breakout_v1", "fundamental_quality_v1"),
        ),
        repository=FakeSkillRepo([technical, fundamental]),
        params={"start_date": "2026-03-01", "limit": 100},
    )

    assert plan.skill_ids == ("technical_breakout_v1", "fundamental_quality_v1")
    assert plan.skill_versions == {"technical_breakout_v1": 1, "fundamental_quality_v1": 2}
