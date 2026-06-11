from __future__ import annotations

import datetime as dt
from pathlib import Path

import yaml


SEED_PATH = Path("terminal/skills/seed_cards/vcp_breakouts_with_fundamentals_v1.yml")
REQUIRED_SQL_TEMPLATES = {
    "vcp_quality_candidates",
    "stage2_new_high_candidates",
    "tradingview_symbol_list",
    "filter_explanation",
    "portfolio_overlap_optional",
}


def _load_seed():
    return yaml.safe_load(SEED_PATH.read_text())


def test_vcp_breakouts_seed_card_contract_and_required_templates():
    from terminal.skills.store_schema import skill_card_from_dict

    payload = _load_seed()
    card = skill_card_from_dict(payload)

    assert card.id == "vcp_breakouts_with_fundamentals_v1"
    assert card.status == "validated"
    assert card.domain == "screening"
    assert card.runtime_eligible is True
    assert set(card.output_contract) == REQUIRED_SQL_TEMPLATES
    assert {template.name for template in card.sql_templates} == REQUIRED_SQL_TEMPLATES
    assert card.evidence_required.tables == (
        "scores.stage2_vcp_picks",
        "scores.stage_snapshots",
    )
    assert {"vcp", "breakout", "fundamentals", "tradingview"}.issubset(set(card.tags))


def test_vcp_breakouts_sql_templates_are_safe_bounded_and_parameterized():
    from terminal.skills.sql_safety import validate_sql_template

    payload = _load_seed()
    params = {
        "limit": 25,
        "min_rs": 20,
        "min_price": 50,
        "min_investment_score": 65,
        "min_fund_score": 65,
        "min_vcp_score": 60,
    }
    for template in payload["sql_templates"]:
        result = validate_sql_template(
            template["sql"],
            required_params=template.get("required_params"),
            params=params,
        )
        assert result.passed, f"{template['name']}: {result.errors}"
        assert template["safety_status"] == "passed"
        assert template["row_limit"] <= 500


def test_vcp_breakouts_execution_plan_filters_and_optional_portfolio_overlap():
    from terminal.skills.evidence_validator import validate_skill_evidence
    from terminal.skills.execution_plan import build_skill_execution_plan
    from terminal.skills.reviewer import ReviewDecision

    payload = _load_seed()
    decision = ReviewDecision(
        decision="select",
        selected_skill_id="vcp_breakouts_with_fundamentals_v1",
        selected_version=1,
        candidate_ids=("vcp_breakouts_with_fundamentals_v1",),
        confidence=0.9,
    )

    plan = build_skill_execution_plan(
        decision,
        skill_cards=[payload],
        params={
            "limit": 25,
            "min_rs": 20,
            "min_price": 50,
            "min_investment_score": 65,
            "min_fund_score": 65,
            "min_vcp_score": 60,
        },
    )

    assert [step.name for step in plan.steps] == [
        "vcp_quality_candidates",
        "stage2_new_high_candidates",
        "tradingview_symbol_list",
        "filter_explanation",
        "portfolio_overlap_optional",
    ]
    vcp_step = next(step for step in plan.steps if step.name == "vcp_quality_candidates")
    assert vcp_step.metadata["required_filters"] == {"stage": "STAGE_2"}
    overlap_step = next(step for step in plan.steps if step.name == "portfolio_overlap_optional")
    assert overlap_step.metadata["optional"] is True

    evidence = {
        "vcp_quality_candidates": {
            "rows": [{"as_of_date": "2026-06-05", "symbol": "ABC", "stage": "STAGE_2"}],
            "row_count": 1,
        },
        "stage2_new_high_candidates": {
            "rows": [{"as_of_date": "2026-06-05", "symbol": "XYZ", "stage": "STAGE_2"}],
            "row_count": 1,
        },
        "tradingview_symbol_list": {
            "rows": [{"as_of_date": "2026-06-05", "tradingview_symbols": "NSE:ABC,NSE:XYZ"}],
            "row_count": 1,
        },
        "filter_explanation": {
            "rows": [{"as_of_date": "2026-06-05", "filter_name": "stage", "filter_value": "STAGE_2"}],
            "row_count": 1,
        },
        "portfolio_overlap_optional": {"rows": [], "row_count": 0, "as_of_date": "2026-06-05"},
    }
    validation = validate_skill_evidence(
        plan,
        evidence=evidence,
        output_contract=payload["output_contract"],
        freshness=payload["evidence_required"]["freshness"],
        today=dt.date(2026, 6, 6),
    )

    assert validation.passed is True
    assert "optional result set empty: portfolio_overlap_optional" in validation.warnings


def test_vcp_breakouts_synthesis_guidance_does_not_invent_vcp_when_missing():
    payload = _load_seed()

    assert "Do not label non-VCP candidates as VCP" in payload["synthesis_guidance"]
    assert "VCP evidence must come from scores.stage2_vcp_picks" in payload["synthesis_guidance"]
