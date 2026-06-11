from __future__ import annotations

import pytest


def _canonical_card_dict():
    return {
        "id": "market_3m_rotation_swing_v1",
        "version": 1,
        "status": "review_pending",
        "domain": "market_analysis",
        "title": "3M Market Rotation Swing Assessment",
        "description": "Analyze market regime and swing candidates.",
        "input_patterns": ["last 3 months market analysis"],
        "tags": ["market_regime", "swing_trading"],
        "evidence_required": {
            "tables": ["market.index_eod", "scores.stage_snapshots"],
            "freshness": {"max_eod_age_days": 3},
        },
        "tool_plan_template": [
            {
                "name": "fetch_market_context",
                "tool_name": "get_live_market_overview",
                "params": {"mode": "eod"},
                "required": True,
            }
        ],
        "sql_templates": [
            {
                "name": "latest_index",
                "sql": "SELECT trade_date, index_symbol, close FROM market.index_eod LIMIT :limit",
                "required_params": ["limit"],
                "expected_columns": ["trade_date", "index_symbol", "close"],
                "row_limit": 100,
                "safety_status": "passed",
                "safety_findings": [],
            }
        ],
        "output_contract": ["as_of_date", "index_returns", "risks"],
        "validation_rules": [
            {"name": "required_tables_exist", "severity": "error", "config": {}},
            {"name": "sql_is_read_only", "severity": "error", "config": {"allow_with": True}},
        ],
        "synthesis_guidance": "Summarize only validated evidence.",
        "generation_model": "gpt-4o",
        "created_by": "test",
        "metadata": {"source": "unit-test"},
    }


def _minimal_card_dict():
    return {
        "id": "minimal_v1",
        "version": 1,
        "status": "generated",
        "domain": "market_analysis",
        "title": "Minimal",
        "description": "Minimal valid skill.",
        "input_patterns": [],
        "tags": [],
        "evidence_required": {},
        "output_contract": ["summary"],
        "validation_rules": ["required_tables_exist"],
    }


def test_skill_card_serializes_and_deserializes_losslessly():
    from terminal.skills.store_schema import skill_card_from_dict, skill_card_to_dict

    payload = _canonical_card_dict()

    card = skill_card_from_dict(payload)
    serialized = skill_card_to_dict(card)
    reparsed = skill_card_from_dict(serialized)

    assert serialized == payload
    assert skill_card_to_dict(reparsed) == payload
    assert card.runtime_eligible is False


def test_minimal_skill_card_serializes_with_intentional_defaults():
    from terminal.skills.store_schema import skill_card_from_dict, skill_card_to_dict

    card = skill_card_from_dict(_minimal_card_dict())

    assert skill_card_to_dict(card) == {
        "id": "minimal_v1",
        "version": 1,
        "status": "generated",
        "domain": "market_analysis",
        "title": "Minimal",
        "description": "Minimal valid skill.",
        "input_patterns": [],
        "tags": [],
        "evidence_required": {"tables": []},
        "tool_plan_template": [],
        "sql_templates": [],
        "output_contract": ["summary"],
        "validation_rules": [{"name": "required_tables_exist", "severity": "error", "config": {}}],
        "synthesis_guidance": None,
        "generation_model": None,
        "created_by": None,
        "metadata": {},
    }


@pytest.mark.parametrize("field_name", ["id", "domain", "status", "output_contract"])
def test_skill_card_contract_rejects_missing_required_fields(field_name):
    from terminal.skills.store_schema import validate_skill_card_contract

    payload = _canonical_card_dict()
    payload[field_name] = [] if field_name == "output_contract" else ""

    assert f"{field_name} is required" in validate_skill_card_contract(payload)


def test_skill_card_from_dict_rejects_invalid_status():
    from terminal.skills.store_schema import skill_card_from_dict

    payload = _canonical_card_dict()
    payload["status"] = "approved"

    with pytest.raises(ValueError, match="status must be one of"):
        skill_card_from_dict(payload)


def test_runtime_eligibility_is_restricted_to_validated_and_production():
    from terminal.skills.store_schema import (
        is_runtime_eligible_card,
        is_runtime_eligible_status,
        skill_card_from_dict,
        validate_skill_card_contract,
    )

    generated = skill_card_from_dict({**_canonical_card_dict(), "status": "generated"})
    validated = skill_card_from_dict({**_canonical_card_dict(), "status": "validated"})
    production = skill_card_from_dict({**_canonical_card_dict(), "status": "production"})

    assert generated.runtime_eligible is False
    assert validated.runtime_eligible is True
    assert production.runtime_eligible is True
    assert is_runtime_eligible_status("review_pending") is False
    assert is_runtime_eligible_status("validated") is True
    assert is_runtime_eligible_card(validated) is True
    assert is_runtime_eligible_card({**_canonical_card_dict(), "status": "validated"}) is True
    assert "runtime-eligible cards must not include validation_errors" in validate_skill_card_contract(
        {**_canonical_card_dict(), "status": "validated", "validation_errors": ["old failure"]}
    )


def test_runtime_status_alone_is_not_full_runtime_eligibility():
    from terminal.skills.store_schema import is_runtime_eligible_card, is_runtime_eligible_status

    unsafe = {
        **_canonical_card_dict(),
        "status": "validated",
        "sql_templates": [
            {
                "name": "unsafe",
                "sql": "SELECT 1",
                "safety_status": "failed",
                "safety_findings": ["not approved"],
            }
        ],
    }
    no_rules = {**_minimal_card_dict(), "status": "validated", "validation_rules": []}

    assert is_runtime_eligible_status("validated") is True
    assert is_runtime_eligible_card(unsafe) is False
    assert is_runtime_eligible_card(no_rules) is False


def test_validate_skill_card_contract_rejects_malformed_nested_payloads():
    from terminal.skills.store_schema import validate_skill_card_contract

    malformed_sql = {**_canonical_card_dict(), "sql_templates": [{"name": "missing_sql"}]}
    malformed_tool = {**_canonical_card_dict(), "tool_plan_template": [{"name": "missing_tool"}]}
    malformed_rule = {**_canonical_card_dict(), "validation_rules": [{"severity": "error"}]}

    assert "sql template sql is required" in validate_skill_card_contract(malformed_sql)
    assert "tool template tool_name is required" in validate_skill_card_contract(malformed_tool)
    assert "validation rule name is required" in validate_skill_card_contract(malformed_rule)


def test_skill_nested_contracts_validate_required_fields():
    from terminal.skills.store_schema import (
        SkillEvidenceRequirement,
        SkillReviewerDecision,
        SkillSQLTemplate,
        SkillToolTemplate,
        SkillValidationRule,
    )

    assert SkillEvidenceRequirement.from_dict({"tables": ["market.index_eod"]}).tables == ("market.index_eod",)
    assert SkillEvidenceRequirement(tables=["market.index_eod"]).tables == ("market.index_eod",)
    assert SkillSQLTemplate.from_dict({"name": "q", "sql": "SELECT 1"}).row_limit == 500
    assert SkillSQLTemplate(name="q", sql="SELECT 1", required_params=["symbol"]).required_params == ("symbol",)
    assert SkillToolTemplate.from_dict({"name": "tool", "tool_name": "get_market"}).required is True
    assert SkillToolTemplate(name="tool", tool_name="get_market", params={"x": 1}).params == {"x": 1}
    assert SkillValidationRule.from_value("sql_is_read_only").name == "sql_is_read_only"
    assert SkillReviewerDecision(status="pass", findings=["ok"]).findings == ("ok",)

    with pytest.raises(ValueError, match="sql template sql is required"):
        SkillSQLTemplate.from_dict({"name": "missing_sql"})
    with pytest.raises(ValueError, match="tool template tool_name is required"):
        SkillToolTemplate.from_dict({"name": "missing_tool"})
    with pytest.raises(ValueError, match="reviewer status"):
        SkillReviewerDecision(status="maybe")  # type: ignore[arg-type]


def test_skill_retrieval_candidate_contract():
    from terminal.skills.store_schema import SkillRetrievalCandidate

    candidate = SkillRetrievalCandidate(
        skill_id="market_3m_rotation_swing_v1",
        version=1,
        score=0.91,
        status="validated",
        domain="market_analysis",
        reason="semantic match",
    )

    assert candidate.to_dict()["status"] == "validated"
    with pytest.raises(ValueError, match="version"):
        SkillRetrievalCandidate(
            skill_id="bad",
            version=0,
            score=0.1,
            status="validated",
            domain="market_analysis",
        )
