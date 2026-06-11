from terminal.skills.registry import get_skill, list_skills


def test_registry_contains_core_agent_adda_skills():
    skill_ids = {skill.id for skill in list_skills()}

    assert "market_readiness" in skill_ids
    assert "evidence_grounding" in skill_ids
    assert "fundamental_driver_diagnosis" in skill_ids
    assert "valuation_analysis" in skill_ids
    assert "forensic_accounting" in skill_ids
    assert "portfolio_risk_review" in skill_ids
    assert "swing_trade_playbook" in skill_ids
    assert "report_qa" in skill_ids


def test_fundamental_driver_skill_contract_is_explicit():
    skill = get_skill("fundamental_driver_diagnosis")

    assert skill.name == "Fundamental Driver Diagnosis"
    assert "symbol" in skill.entities_required
    assert "financial_statements" in skill.evidence_required
    assert "short_answer" in skill.output_contract
    assert "metric_bridge" in skill.output_contract
    assert any("eps" in trigger for trigger in skill.triggers)
    assert any("roce" in trigger for trigger in skill.triggers)
