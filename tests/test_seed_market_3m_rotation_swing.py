from __future__ import annotations

import datetime as dt
from pathlib import Path

import yaml


SEED_PATH = Path("terminal/skills/seed_cards/market_3m_rotation_swing_v1.yml")
REQUIRED_SQL_TEMPLATES = {
    "index_returns_lookback",
    "stage_distribution_change",
    "sector_returns_lookback",
    "stage2_liquid_candidates",
    "vcp_latest_candidates",
}


def _load_seed():
    return yaml.safe_load(SEED_PATH.read_text())


def test_market_3m_rotation_seed_card_contract_and_required_templates():
    from terminal.skills.store_schema import skill_card_from_dict

    payload = _load_seed()
    card = skill_card_from_dict(payload)

    assert card.id == "market_3m_rotation_swing_v1"
    assert card.status == "validated"
    assert card.domain == "market_analysis"
    assert card.runtime_eligible is True
    assert set(card.output_contract) == REQUIRED_SQL_TEMPLATES
    assert {template.name for template in card.sql_templates} == REQUIRED_SQL_TEMPLATES
    assert card.evidence_required.tables == (
        "market.index_eod",
        "scores.stage_snapshots",
        "scores.stage2_vcp_picks",
    )


def test_market_3m_rotation_sql_templates_are_safe_and_parameterized():
    from terminal.skills.sql_safety import validate_sql_template

    payload = _load_seed()
    for template in payload["sql_templates"]:
        result = validate_sql_template(
            template["sql"],
            required_params=template.get("required_params"),
            params={"lookback_days": 90, "limit": 25, "min_price": 50, "min_investment_score": 60},
        )
        assert result.passed, f"{template['name']}: {result.errors}"
        assert template["safety_status"] == "passed"
        assert template["row_limit"] <= 500


def test_market_3m_rotation_execution_plan_preserves_all_outputs_and_optional_vcp():
    from terminal.skills.evidence_validator import validate_skill_evidence
    from terminal.skills.execution_plan import build_skill_execution_plan
    from terminal.skills.reviewer import ReviewDecision

    payload = _load_seed()
    decision = ReviewDecision(
        decision="select",
        selected_skill_id="market_3m_rotation_swing_v1",
        selected_version=1,
        candidate_ids=("market_3m_rotation_swing_v1",),
        confidence=0.9,
    )

    plan = build_skill_execution_plan(
        decision,
        skill_cards=[payload],
        params={"lookback_days": 90, "limit": 25, "min_price": 50, "min_investment_score": 60},
    )

    assert [step.name for step in plan.steps] == [
        "index_returns_lookback",
        "stage_distribution_change",
        "sector_returns_lookback",
        "stage2_liquid_candidates",
        "vcp_latest_candidates",
    ]
    vcp_step = next(step for step in plan.steps if step.name == "vcp_latest_candidates")
    assert vcp_step.metadata["optional"] is True

    evidence = {
        "index_returns_lookback": {"rows": [{"as_of_date": "2026-06-05", "index_symbol": "NIFTY 50"}], "row_count": 1},
        "stage_distribution_change": {"rows": [{"as_of_date": "2026-06-05", "stage": "STAGE_2"}], "row_count": 1},
        "sector_returns_lookback": {"rows": [{"as_of_date": "2026-06-05", "sector": "Capital Goods"}], "row_count": 1},
        "stage2_liquid_candidates": {"rows": [{"as_of_date": "2026-06-05", "symbol": "ABC", "stage": "STAGE_2"}], "row_count": 1},
        "vcp_latest_candidates": {"rows": [], "row_count": 0, "as_of_date": "2026-06-05"},
    }
    validation = validate_skill_evidence(
        plan,
        evidence=evidence,
        output_contract=payload["output_contract"],
        freshness=payload["evidence_required"]["freshness"],
        today=dt.date(2026, 6, 6),
    )

    assert validation.passed is True
    assert "optional result set empty: vcp_latest_candidates" in validation.warnings
