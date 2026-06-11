from __future__ import annotations

import datetime as dt
from pathlib import Path

import yaml


SEED_PATH = Path("terminal/skills/seed_cards/portfolio_incremental_add_trim_v1.yml")
REQUIRED_SQL_TEMPLATES = {
    "portfolio_current_state",
    "sector_exposure_warnings",
    "add_candidates",
    "trim_candidates",
    "hold_candidates",
    "target_allocation_caveats",
}


def _load_seed():
    return yaml.safe_load(SEED_PATH.read_text())


def test_portfolio_incremental_seed_card_contract_and_required_templates():
    from terminal.skills.store_schema import skill_card_from_dict

    payload = _load_seed()
    card = skill_card_from_dict(payload)

    assert card.id == "portfolio_incremental_add_trim_v1"
    assert card.status == "validated"
    assert card.domain == "portfolio_review"
    assert card.runtime_eligible is True
    assert set(card.output_contract) == REQUIRED_SQL_TEMPLATES
    assert {template.name for template in card.sql_templates} == REQUIRED_SQL_TEMPLATES
    assert card.evidence_required.tables == (
        "portfolio.holdings",
        "scores.stage_snapshots",
    )
    assert {"portfolio", "incremental_add", "trim", "sector_exposure", "position_sizing"}.issubset(set(card.tags))


def test_portfolio_incremental_sql_templates_are_safe_bounded_and_parameterized():
    from terminal.skills.sql_safety import validate_sql_template

    payload = _load_seed()
    params = {
        "account": "DEFAULT",
        "max_sector_weight_pct": 25,
        "max_position_weight_pct": 12,
        "min_position_weight_pct": 2,
        "min_investment_score": 65,
        "min_add_score": 72,
        "limit": 25,
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


def test_portfolio_incremental_plan_is_state_aware_and_warns_on_missing_targets():
    from terminal.skills.evidence_validator import validate_skill_evidence
    from terminal.skills.execution_plan import build_skill_execution_plan
    from terminal.skills.reviewer import ReviewDecision

    payload = _load_seed()
    decision = ReviewDecision(
        decision="select",
        selected_skill_id="portfolio_incremental_add_trim_v1",
        selected_version=1,
        candidate_ids=("portfolio_incremental_add_trim_v1",),
        confidence=0.9,
    )
    params = {
        "account": "DEFAULT",
        "max_sector_weight_pct": 25,
        "max_position_weight_pct": 12,
        "min_position_weight_pct": 2,
        "min_investment_score": 65,
        "min_add_score": 72,
        "limit": 25,
    }

    plan = build_skill_execution_plan(decision, skill_cards=[payload], params=params)

    assert [step.name for step in plan.steps] == [
        "portfolio_current_state",
        "sector_exposure_warnings",
        "add_candidates",
        "trim_candidates",
        "hold_candidates",
        "target_allocation_caveats",
    ]
    assert all(step.params["account"] == "DEFAULT" for step in plan.steps if "account" in step.params)
    trim_step = next(step for step in plan.steps if step.name == "trim_candidates")
    assert trim_step.metadata["required_filters"] == {"holding_state": "EXISTING_HOLDING"}

    evidence = {
        "portfolio_current_state": {
            "rows": [{"as_of_date": "2026-06-05", "symbol": "ABC", "holding_state": "EXISTING_HOLDING"}],
            "row_count": 1,
        },
        "sector_exposure_warnings": {
            "rows": [{"as_of_date": "2026-06-05", "sector": "Capital Goods", "sector_weight_pct": 31}],
            "row_count": 1,
        },
        "add_candidates": {
            "rows": [{"as_of_date": "2026-06-05", "symbol": "XYZ", "action_bucket": "ADD_INCREMENTALLY"}],
            "row_count": 1,
        },
        "trim_candidates": {
            "rows": [{"as_of_date": "2026-06-05", "symbol": "ABC", "holding_state": "EXISTING_HOLDING"}],
            "row_count": 1,
        },
        "hold_candidates": {
            "rows": [{"as_of_date": "2026-06-05", "symbol": "DEF", "holding_state": "EXISTING_HOLDING"}],
            "row_count": 1,
        },
        "target_allocation_caveats": {
            "rows": [{"as_of_date": "2026-06-05", "caveat": "missing_target_allocation"}],
            "row_count": 1,
        },
    }
    validation = validate_skill_evidence(
        plan,
        evidence=evidence,
        output_contract=payload["output_contract"],
        freshness=payload["evidence_required"]["freshness"],
        today=dt.date(2026, 6, 6),
    )

    assert validation.passed is True


def test_portfolio_incremental_guidance_rejects_greenfield_recommendations():
    payload = _load_seed()

    assert "Do not treat the portfolio as a greenfield portfolio" in payload["synthesis_guidance"]
    assert "incremental add" in payload["synthesis_guidance"]
    assert "missing target allocation" in payload["synthesis_guidance"]
