from __future__ import annotations

import datetime as dt


def _step(step_id: str, *, name: str, step_type: str = "sql_template", required: bool = True, optional: bool = False, metadata=None):
    from terminal.skills.execution_plan import SkillExecutionStep

    return SkillExecutionStep(
        step_id=step_id,
        step_type=step_type,
        skill_id="market_3m_rotation_swing_v1",
        skill_version=1,
        name=name,
        target=name,
        params={},
        metadata={"required": required, "optional": optional, **(metadata or {})},
    )


def test_missing_required_result_set_fails():
    from terminal.skills.evidence_validator import validate_skill_evidence
    from terminal.skills.execution_plan import SkillExecutionPlan

    plan = SkillExecutionPlan(
        skill_ids=("market_3m_rotation_swing_v1",),
        skill_versions={"market_3m_rotation_swing_v1": 1},
        review_decision="select",
        steps=(_step("s1", name="index_returns"),),
    )

    validation = validate_skill_evidence(
        plan,
        evidence={},
        output_contract=["index_returns"],
        today=dt.date(2026, 6, 6),
    )

    assert validation.passed is False
    assert "missing required result set: index_returns" in validation.errors
    assert validation.missing_evidence == ("index_returns",)


def test_required_output_keys_must_be_present():
    from terminal.skills.evidence_validator import validate_skill_evidence

    validation = validate_skill_evidence(
        [_step("s1", name="index_returns")],
        evidence={"index_returns": {"rows": [{"index_symbol": "NIFTY 50"}], "row_count": 1, "as_of_date": "2026-06-05"}},
        output_contract=["index_returns", "risks"],
        today=dt.date(2026, 6, 6),
    )

    assert validation.passed is False
    assert "missing required output key: risks" in validation.errors


def test_future_dates_fail():
    from terminal.skills.evidence_validator import validate_skill_evidence

    validation = validate_skill_evidence(
        [_step("s1", name="index_returns")],
        evidence={"index_returns": {"rows": [{"trade_date": "2026-06-07"}], "row_count": 1, "as_of_date": "2026-06-07"}},
        output_contract=["index_returns"],
        today=dt.date(2026, 6, 6),
    )

    assert validation.passed is False
    assert "future date in index_returns: 2026-06-07" in validation.errors


def test_stale_data_warns_or_fails_based_on_requirement():
    from terminal.skills.evidence_validator import validate_skill_evidence

    warning_validation = validate_skill_evidence(
        [_step("s1", name="index_returns")],
        evidence={"index_returns": {"rows": [{"trade_date": "2026-06-01"}], "row_count": 1, "as_of_date": "2026-06-01"}},
        output_contract=["index_returns"],
        freshness={"max_age_days": 3, "stale_is_error": False},
        today=dt.date(2026, 6, 6),
    )
    failing_validation = validate_skill_evidence(
        [_step("s1", name="index_returns")],
        evidence={"index_returns": {"rows": [{"trade_date": "2026-06-01"}], "row_count": 1, "as_of_date": "2026-06-01"}},
        output_contract=["index_returns"],
        freshness={"max_age_days": 3, "stale_is_error": True},
        today=dt.date(2026, 6, 6),
    )

    assert warning_validation.passed is True
    assert "stale evidence in index_returns: 5 days old" in warning_validation.warnings
    assert failing_validation.passed is False
    assert "stale evidence in index_returns: 5 days old" in failing_validation.errors


def test_empty_optional_vcp_overlap_does_not_fail_market_analysis():
    from terminal.skills.evidence_validator import validate_skill_evidence

    validation = validate_skill_evidence(
        [_step("s1", name="vcp_overlap", metadata={"optional": True})],
        evidence={"vcp_overlap": {"rows": [], "row_count": 0, "as_of_date": "2026-06-05"}},
        output_contract=["vcp_overlap"],
        today=dt.date(2026, 6, 6),
    )

    assert validation.passed is True
    assert validation.errors == ()
    assert "optional result set empty: vcp_overlap" in validation.warnings


def test_row_count_mismatch_and_large_row_count_warn():
    from terminal.skills.evidence_validator import validate_skill_evidence

    validation = validate_skill_evidence(
        [_step("s1", name="index_returns")],
        evidence={
            "index_returns": {
                "rows": [{"trade_date": "2026-06-05"}],
                "row_count": 5000,
                "as_of_date": "2026-06-05",
            }
        },
        output_contract=["index_returns"],
        max_rows=1000,
        today=dt.date(2026, 6, 6),
    )

    assert validation.passed is True
    assert "row_count mismatch in index_returns: declared 5000, actual 1" in validation.warnings
    assert "row_count exceeds max_rows in index_returns: 5000 > 1000" in validation.warnings


def test_candidate_filter_not_applied_fails():
    from terminal.skills.evidence_validator import validate_skill_evidence

    validation = validate_skill_evidence(
        [_step("s1", name="candidates", metadata={"required_filters": {"stage": "STAGE_2"}})],
        evidence={
            "candidates": {
                "rows": [{"symbol": "ABC", "stage": "STAGE_1"}],
                "row_count": 1,
                "as_of_date": "2026-06-05",
            }
        },
        output_contract=["candidates"],
        today=dt.date(2026, 6, 6),
    )

    assert validation.passed is False
    assert "required filter not applied in candidates: stage=STAGE_2" in validation.errors


def test_validation_result_serializes_to_plain_dict():
    from terminal.skills.evidence_validator import SkillEvidenceValidation

    validation = SkillEvidenceValidation(
        passed=False,
        errors=("missing required result set: index_returns",),
        warnings=("stale",),
        missing_evidence=("index_returns",),
        metadata={"checked": 1},
    )

    assert validation.to_dict() == {
        "passed": False,
        "errors": ["missing required result set: index_returns"],
        "warnings": ["stale"],
        "missing_evidence": ["index_returns"],
        "metadata": {"checked": 1},
    }
