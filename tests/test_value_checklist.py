from terminal.value_checklist import (
    CHECKLIST_DIMENSIONS,
    ValueChecklistEvidence,
    build_checklist_result,
    collect_value_checklist_evidence,
    compare_checklist_results,
    parse_investment_checklist_symbols,
)


def _evidence(
    symbol: str,
    *,
    sector: str = "Information Technology",
    fundamentals: dict | None = None,
    valuation: dict | None = None,
    governance: dict | None = None,
    technical: dict | None = None,
    missing_evidence: tuple[str, ...] = (),
) -> ValueChecklistEvidence:
    return ValueChecklistEvidence(
        symbol=symbol,
        company_name=f"{symbol} Ltd",
        sector=sector,
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


def test_unusable_fundamentals_returns_insufficient_evidence():
    result = build_checklist_result(
        _evidence(
            "BADFUND",
            fundamentals={
                "roe": None,
                "roce": None,
                "opm_pct": "n/a",
                "free_cash_flow_positive": None,
                "debt_to_equity": None,
                "enhanced_fund_score": None,
            },
        )
    )

    assert result.verdict == "INSUFFICIENT_EVIDENCE"
    assert result.total_score == 0
    assert "fundamentals" in result.missing_evidence
    assert result.mirror_test_passed is False
    assert not any("ROE 0.0" in item for item in result.mirror_test)


def test_fund_score_only_mirror_claim_does_not_fabricate_ratios():
    result = build_checklist_result(
        _evidence("FUNDSCORE", fundamentals={"enhanced_fund_score": 82.0})
    )

    assert not any("ROE 0.0" in item for item in result.mirror_test)
    assert not any("ROCE 0.0" in item for item in result.mirror_test)
    assert any(
        "Agent Adda fundamental score 82.0" in item
        for item in result.mirror_test
    )


def test_missing_sector_fails_mirror_test():
    result = build_checklist_result(_evidence("NOSECTOR", sector=""))

    assert "sector" in result.missing_evidence
    assert result.mirror_test_passed is False
    assert result.verdict in {"CONDITIONAL", "WATCH", "AVOID", "INSUFFICIENT_EVIDENCE"}
    assert any(
        "sector" in item.lower() or "business context" in item.lower()
        for item in result.mirror_test
    )
    assert not any("an identified NSE sector" in item for item in result.mirror_test)


def test_missing_governance_cap_text_matches_watch_verdict():
    result = build_checklist_result(_evidence("NOGOVCAP", governance={}))

    assert result.verdict == "WATCH"
    assert any(
        "missing governance" in cap.lower() and "watch" in cap.lower()
        for cap in result.hard_caps
    )
    assert not any(
        "missing governance" in cap.lower() and "conditional" in cap.lower()
        for cap in result.hard_caps
    )


def test_growth_only_fundamentals_appear_in_quality_mirror_claim():
    result = build_checklist_result(
        _evidence(
            "GROWTH",
            fundamentals={"sales_growth": 12.0, "profit_growth": 14.0},
        )
    )

    assert any("sales growth 12.0%" in item for item in result.mirror_test)
    assert any("profit growth 14.0%" in item for item in result.mirror_test)
    assert "Quality evidence: ." not in result.mirror_test


def test_placeholder_sector_is_not_used_as_identified_sector():
    result = build_checklist_result(_evidence("PLACESECTOR", sector="N/A"))

    assert "sector" in result.missing_evidence
    assert result.mirror_test_passed is False
    assert not any(
        "Sector identified as N/A" in reason
        for score in result.dimension_scores
        for reason in score.reasons
    )
    assert not any("N/A" in item for item in result.mirror_test)


def test_parse_investment_checklist_symbols_accepts_commas_spaces_and_dedupes():
    assert parse_investment_checklist_symbols("/investment-checklist TCS, INFY HDFCBANK TCS") == [
        "TCS",
        "INFY",
        "HDFCBANK",
    ]


def test_parse_investment_checklist_symbols_limits_to_ten():
    text = "/investment-checklist " + " ".join(f"S{i}" for i in range(12))

    assert parse_investment_checklist_symbols(text) == [f"S{i}" for i in range(10)]


def test_collect_evidence_uses_stage_snapshot_and_cached_screener(monkeypatch):
    def fake_snapshot(symbol):
        return {
            "symbol": symbol,
            "company_name": f"{symbol} Ltd",
            "sector": "IT",
            "stage": "STAGE_2",
            "relative_strength": 1.2,
            "rsi": 62,
            "technical_score": 81,
            "trend_signal": "BULLISH",
            "trading_signal": "BUY",
            "enhanced_fund_score": 84,
            "fundamental_score": 78,
            "earnings_quality": 82,
            "sales_growth": 13,
            "financial_strength": 88,
            "data_source": "scores.stage_snapshots",
            "snapshot_date": "2026-06-26",
            "missing_evidence": [],
        }

    def fake_cache(symbol, max_age_hours=None):
        return {
            "ratios": {"Stock P/E": "24", "ROE": "24%", "ROCE": "31%", "Debt to equity": "0.05"},
            "annual_pl": {"OPM %": ["22%", "24%", "26%"], "_headers": ["Mar 2024", "Mar 2025", "Mar 2026"]},
            "cash_flow": {"Free Cash Flow": ["1200", "1500", "1800"], "_headers": ["Mar 2024", "Mar 2025", "Mar 2026"]},
            "_cache_age_hours": 2.5,
        }

    monkeypatch.setattr("terminal.tools.get_symbol_snapshot", fake_snapshot)
    monkeypatch.setattr("terminal.financials_cache.screener_payload_from_cache", fake_cache)

    evidence = collect_value_checklist_evidence(["TCS"])[0]

    assert evidence.symbol == "TCS"
    assert evidence.company_name == "TCS Ltd"
    assert evidence.fundamentals["roe"] == 24.0
    assert evidence.valuation["pe"] == 24.0
    assert evidence.technical["stage"] == "STAGE_2"
    assert evidence.missing_evidence == ()
    assert any(item["name"] == "scores.stage_snapshots" for item in evidence.source_trail)


def test_collect_evidence_marks_missing_fundamentals(monkeypatch):
    monkeypatch.setattr(
        "terminal.tools.get_symbol_snapshot",
        lambda symbol: {"symbol": symbol, "error": "not found", "missing_evidence": ["stage_snapshot"]},
    )
    monkeypatch.setattr("terminal.financials_cache.screener_payload_from_cache", lambda symbol, max_age_hours=None: None)

    evidence = collect_value_checklist_evidence(["NOPE"])[0]

    assert evidence.symbol == "NOPE"
    assert "fundamentals" in evidence.missing_evidence
    assert "stage_snapshot" in evidence.missing_evidence


def test_collect_sparse_real_cache_shape_does_not_fabricate_clean_evidence(monkeypatch):
    def fake_snapshot(symbol):
        return {
            "symbol": symbol,
            "company_name": f"{symbol} Ltd",
            "sector": "IT",
            "stage": "STAGE_2",
            "snapshot_date": "2026-06-26",
            "missing_evidence": [],
        }

    def fake_cache(symbol, max_age_hours=None):
        return {
            "ratios": {},
            "shareholding": {},
            "cash_flow": {"Net Cash Flow": ["10", "15", "20"]},
            "_cache_age_hours": 1,
        }

    monkeypatch.setattr("terminal.tools.get_symbol_snapshot", fake_snapshot)
    monkeypatch.setattr("terminal.financials_cache.screener_payload_from_cache", fake_cache)

    evidence = collect_value_checklist_evidence(["SPARSE"])[0]
    result = build_checklist_result(evidence)

    assert evidence.fundamentals == {}
    assert evidence.governance == {}
    assert "fundamentals" in result.missing_evidence
    assert "governance" in result.missing_evidence
    assert result.verdict == "INSUFFICIENT_EVIDENCE"


def test_collect_evidence_omits_invalid_snapshot_score_strings(monkeypatch):
    def fake_snapshot(symbol):
        return {
            "symbol": symbol,
            "company_name": f"{symbol} Ltd",
            "sector": "IT",
            "enhanced_fund_score": "bad",
            "sales_growth": "bad",
            "snapshot_date": "2026-06-26",
            "missing_evidence": [],
        }

    monkeypatch.setattr("terminal.tools.get_symbol_snapshot", fake_snapshot)
    monkeypatch.setattr("terminal.financials_cache.screener_payload_from_cache", lambda symbol, max_age_hours=None: None)

    evidence = collect_value_checklist_evidence(["BADSTR"])[0]

    assert "enhanced_fund_score" not in evidence.fundamentals
    assert "sales_growth" not in evidence.fundamentals


def test_collect_evidence_treats_negative_pe_as_missing_valuation(monkeypatch):
    def fake_snapshot(symbol):
        return {
            "symbol": symbol,
            "company_name": f"{symbol} Ltd",
            "sector": "IT",
            "enhanced_fund_score": 82,
            "snapshot_date": "2026-06-26",
            "missing_evidence": [],
        }

    def fake_cache(symbol, max_age_hours=None):
        return {
            "ratios": {"Stock P/E": "-12"},
            "shareholding": {"Pledged": "0"},
            "_cache_age_hours": 1,
        }

    monkeypatch.setattr("terminal.tools.get_symbol_snapshot", fake_snapshot)
    monkeypatch.setattr("terminal.financials_cache.screener_payload_from_cache", fake_cache)

    evidence = collect_value_checklist_evidence(["NEGPE"])[0]
    result = build_checklist_result(evidence)

    assert evidence.valuation == {}
    assert evidence.valuation.get("valuation_signal") != "reasonable"
    assert "valuation" in result.missing_evidence


def test_collect_evidence_propagates_snapshot_missing_evidence_without_error(monkeypatch):
    monkeypatch.setattr(
        "terminal.tools.get_symbol_snapshot",
        lambda symbol: {
            "symbol": symbol,
            "company_name": f"{symbol} Ltd",
            "sector": "IT",
            "enhanced_fund_score": 82,
            "snapshot_date": "2026-06-26",
            "missing_evidence": ["technical"],
        },
    )
    monkeypatch.setattr(
        "terminal.financials_cache.screener_payload_from_cache",
        lambda symbol, max_age_hours=None: {
            "ratios": {"Stock P/E": "24"},
            "shareholding": {"Pledged": "0"},
            "_cache_age_hours": 1,
        },
    )

    evidence = collect_value_checklist_evidence(["PARTIAL"])[0]
    result = build_checklist_result(evidence)

    assert "technical" in evidence.missing_evidence
    assert "technical" in result.missing_evidence


def test_collect_evidence_marks_fundamentals_freshness_missing_without_screener(monkeypatch):
    monkeypatch.setattr(
        "terminal.tools.get_symbol_snapshot",
        lambda symbol: {
            "symbol": symbol,
            "company_name": f"{symbol} Ltd",
            "sector": "IT",
            "snapshot_date": "2026-06-26",
            "missing_evidence": [],
        },
    )
    monkeypatch.setattr("terminal.financials_cache.screener_payload_from_cache", lambda symbol, max_age_hours=None: None)

    evidence = collect_value_checklist_evidence(["NOCACHE"])[0]

    assert evidence.freshness["fundamentals"] in {"missing", "unknown"}
