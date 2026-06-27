from terminal.value_checklist import (
    CHECKLIST_DIMENSIONS,
    ValueChecklistEvidence,
    build_checklist_result,
    compare_checklist_results,
)


def _evidence(
    symbol: str,
    *,
    fundamentals: dict | None = None,
    valuation: dict | None = None,
    governance: dict | None = None,
    technical: dict | None = None,
    missing_evidence: tuple[str, ...] = (),
) -> ValueChecklistEvidence:
    return ValueChecklistEvidence(
        symbol=symbol,
        company_name=f"{symbol} Ltd",
        sector="Information Technology",
        fundamentals={
            "roe": 24.0,
            "roce": 31.0,
            "opm_pct": 26.0,
            "free_cash_flow_positive": True,
            "debt_to_equity": 0.05,
            "sales_growth": 12.0,
            "profit_growth": 14.0,
            "enhanced_fund_score": 82.0,
        }
        if fundamentals is None
        else fundamentals,
        valuation={
            "pe": 24.0,
            "pb": 5.5,
            "earnings_yield_pct": 4.2,
            "valuation_signal": "reasonable",
        }
        if valuation is None
        else valuation,
        governance={
            "promoter_pledge_pct": 0.0,
            "forensic_risk": "low",
            "insider_signal": "neutral",
        }
        if governance is None
        else governance,
        technical={
            "stage": "STAGE_2",
            "relative_strength": 1.18,
            "rsi": 61.0,
            "technical_score": 78.0,
            "trend_signal": "BULLISH",
            "trading_signal": "BUY",
        }
        if technical is None
        else technical,
        latest_results={"status": "ok", "sales_yoy_pct": 10.0, "pat_yoy_pct": 13.0},
        source_trail=(
            {"name": "scores.stage_snapshots", "status": "ok"},
            {"name": "screener_cache", "status": "ok"},
        ),
        missing_evidence=missing_evidence,
        freshness={"stage_snapshot": "2026-06-26", "fundamentals": "cached"},
    )


def test_checklist_weights_sum_to_100():
    assert sum(item.weight for item in CHECKLIST_DIMENSIONS) == 100


def test_missing_fundamentals_returns_insufficient_evidence():
    result = build_checklist_result(
        _evidence("MISS", fundamentals={}, missing_evidence=("fundamentals",))
    )

    assert result.verdict == "INSUFFICIENT_EVIDENCE"
    assert result.total_score == 0
    assert "fundamentals" in result.missing_evidence
    assert "Missing fundamentals" in " ".join(result.hard_caps)


def test_governance_red_flag_caps_verdict():
    result = build_checklist_result(
        _evidence(
            "PLEDGE",
            governance={
                "promoter_pledge_pct": 28.0,
                "forensic_risk": "high",
                "insider_signal": "negative",
            },
        )
    )

    assert result.verdict in {"WATCH", "AVOID"}
    assert any("governance" in cap.lower() for cap in result.hard_caps)


def test_stage4_caps_verdict_at_watch():
    result = build_checklist_result(
        _evidence(
            "WEAKTECH",
            technical={
                "stage": "STAGE_4",
                "relative_strength": 0.72,
                "rsi": 38.0,
                "technical_score": 22.0,
                "trend_signal": "BEARISH",
                "trading_signal": "SELL",
            },
        )
    )

    assert result.verdict in {"WATCH", "AVOID"}
    assert any("Stage 4" in cap for cap in result.hard_caps)


def test_strong_quality_reasonable_valuation_outranks_weak_expensive_name():
    strong = build_checklist_result(_evidence("STRONG"))
    weak = build_checklist_result(
        _evidence(
            "EXPENSIVE",
            fundamentals={
                "roe": 8.0,
                "roce": 10.0,
                "opm_pct": 8.0,
                "free_cash_flow_positive": False,
                "debt_to_equity": 1.4,
                "sales_growth": 2.0,
                "profit_growth": -3.0,
                "enhanced_fund_score": 35.0,
            },
            valuation={
                "pe": 88.0,
                "pb": 14.0,
                "earnings_yield_pct": 1.1,
                "valuation_signal": "expensive",
            },
            technical={
                "stage": "STAGE_3",
                "relative_strength": 0.88,
                "rsi": 49.0,
                "technical_score": 42.0,
                "trend_signal": "MIXED",
                "trading_signal": "HOLD",
            },
        )
    )

    ranked = compare_checklist_results([weak, strong])

    assert ranked[0].symbol == "STRONG"
    assert ranked[0].total_score > ranked[1].total_score


def test_mirror_test_fails_when_core_claims_are_missing():
    result = build_checklist_result(_evidence("THIN", valuation={}))

    assert result.mirror_test_passed is False
    assert "valuation" in result.missing_evidence
    assert result.verdict != "PASS"
    decision_score = next(
        score
        for score in result.dimension_scores
        if score.name == "Decision Discipline"
    )
    assert "valuation" in decision_score.missing_evidence
    assert any("valuation" in item.lower() for item in result.mirror_test)


def test_missing_debt_to_equity_does_not_add_low_leverage_credit():
    result = build_checklist_result(
        _evidence(
            "NODEBT",
            fundamentals={
                "roe": 24.0,
                "roce": 31.0,
                "opm_pct": 26.0,
                "free_cash_flow_positive": True,
                "sales_growth": 12.0,
                "profit_growth": 14.0,
                "enhanced_fund_score": 82.0,
            },
        )
    )

    quality_score = next(
        score
        for score in result.dimension_scores
        if score.name == "Business Quality"
    )
    assert "Low leverage." not in quality_score.reasons


def test_empty_governance_does_not_claim_clean_governance():
    result = build_checklist_result(_evidence("NOGOV", governance={}))

    governance_score = next(
        score
        for score in result.dimension_scores
        if score.name == "Management / Governance"
    )
    assert not any(
        "no severe governance issue" in reason.lower()
        for reason in governance_score.reasons
    )


def test_zero_technical_score_remains_zero_not_neutral():
    result = build_checklist_result(
        _evidence("ZEROTECH", technical={"technical_score": 0.0})
    )

    technical_score = next(
        score
        for score in result.dimension_scores
        if score.name == "Technical Confirmation"
    )
    assert technical_score.raw_score == 0.0


def test_unusable_valuation_evidence_is_treated_as_missing():
    result = build_checklist_result(
        _evidence(
            "BADVAL",
            valuation={"pe": None, "pb": "n/a", "earnings_yield_pct": None},
        )
    )

    assert "valuation" in result.missing_evidence
    assert result.mirror_test_passed is False
    assert result.verdict in {"WATCH", "AVOID", "INSUFFICIENT_EVIDENCE"}
    assert any("valuation" in item.lower() for item in result.mirror_test)
    assert not any("PE 0.0" in item for item in result.mirror_test)


def test_empty_governance_evidence_fails_mirror_test():
    result = build_checklist_result(_evidence("NOGOV", governance={}))

    assert "governance" in result.missing_evidence
    assert result.verdict != "PASS"
    assert result.mirror_test_passed is False
    assert any("governance" in item.lower() for item in result.mirror_test)
    assert not any(
        "governance evidence does not force" in item.lower()
        for item in result.mirror_test
    )


def test_missing_evidence_labels_are_normalized():
    result = build_checklist_result(
        _evidence(
            "LABELS",
            missing_evidence=(
                " Valuation ",
                "",
                "valuation",
                " GOVERNANCE ",
                "governance",
            ),
        )
    )

    assert result.missing_evidence == ("valuation", "governance")


def test_zero_valuation_metric_is_treated_as_missing():
    result = build_checklist_result(_evidence("ZEROVAL", valuation={"pe": 0.0}))

    assert "valuation" in result.missing_evidence
    assert result.mirror_test_passed is False
    assert result.verdict in {"WATCH", "AVOID", "INSUFFICIENT_EVIDENCE"}
    assert any("valuation" in item.lower() for item in result.mirror_test)
    assert not any("PE 0.0" in item for item in result.mirror_test)


def test_negative_valuation_metrics_are_treated_as_missing():
    result = build_checklist_result(
        _evidence(
            "NEGVAL",
            valuation={"pe": -8.0, "pb": -2.0, "earnings_yield_pct": -1.5},
        )
    )

    assert "valuation" in result.missing_evidence
    assert result.mirror_test_passed is False
    assert result.verdict in {"WATCH", "AVOID", "INSUFFICIENT_EVIDENCE"}
    assert any("valuation" in item.lower() for item in result.mirror_test)


def test_whitespace_padded_forensic_red_flag_caps_governance():
    result = build_checklist_result(
        _evidence(
            "PADGOV",
            governance={
                "promoter_pledge_pct": 0.0,
                "forensic_risk": " high ",
                "insider_signal": "neutral",
            },
        )
    )

    governance_score = next(
        score
        for score in result.dimension_scores
        if score.name == "Management / Governance"
    )
    assert result.verdict in {"WATCH", "AVOID"}
    assert any("governance" in cap.lower() for cap in result.hard_caps)
    assert not any(
        "no severe governance issue" in reason.lower()
        for reason in governance_score.reasons
    )


def test_whitespace_padded_expensive_signal_caps_valuation():
    result = build_checklist_result(
        _evidence(
            "PADVAL",
            valuation={
                "pe": 24.0,
                "pb": 5.5,
                "earnings_yield_pct": 4.2,
                "valuation_signal": " expensive ",
            },
        )
    )

    assert result.verdict in {"WATCH", "AVOID"}
    assert any("valuation" in cap.lower() for cap in result.hard_caps)


def test_pb_only_valuation_appears_in_mirror_test():
    result = build_checklist_result(_evidence("PBONLY", valuation={"pb": 4.2}))

    assert "valuation" not in result.missing_evidence
    assert any("PB 4.2" in item for item in result.mirror_test)
    assert "Valuation evidence: ." not in result.mirror_test


def test_severe_governance_reason_is_not_contradictory():
    result = build_checklist_result(
        _evidence(
            "SEVERE",
            governance={
                "promoter_pledge_pct": 0.0,
                "forensic_risk": "severe",
                "insider_signal": "neutral",
            },
        )
    )

    governance_score = next(
        score
        for score in result.dimension_scores
        if score.name == "Management / Governance"
    )
    assert any("forensic risk is high" in reason.lower() for reason in governance_score.reasons)
    assert not any(
        "no severe governance issue" in reason.lower()
        for reason in governance_score.reasons
    )
