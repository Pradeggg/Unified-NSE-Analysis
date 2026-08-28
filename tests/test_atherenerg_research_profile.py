"""Regression tests for the curated ATHERENERG deep-research profile."""


def test_atherenerg_profile_contains_evidence_and_explicit_gaps():
    from scripts.generate_research_report import _atherenerg_evidence

    evidence = _atherenerg_evidence()

    assert "electric two-wheeler" in evidence["overview"]
    assert "₹3,672 Cr" in evidence["investment"]
    assert "No broker facts were available" in evidence["disclosure"]
    assert "no like-for-like same-date peer valuation ranking" in evidence["sector_table"].lower()
    assert any("broker_research_facts" in source for source in evidence["sources"])


def test_atherenerg_overrides_generic_placeholders():
    from scripts.generate_research_report import _build_placeholders_generic

    placeholders = _build_placeholders_generic(
        symbol="ATHERENERG",
        sc={"ratios": {"Name": "Ather Energy Limited"}},
        tech={},
        snap={},
        web={},
    )

    assert "Ather Energy is a growth-stage EV" in placeholders["ONE_LINE_THESIS"]
    assert "No defensible earnings-multiple valuation" in placeholders["VALUATION_NOTE"]
    assert "Profitability and cash burn" in placeholders["RISK_TABLE"]
    assert "Screener financials" in placeholders["EVIDENCE_TRAIL"]
    assert "</li></li>" not in placeholders["EVIDENCE_TRAIL"]


def test_report_financial_payload_prefers_persisted_pg_sections():
    from scripts.generate_research_report import _merge_pg_financial_cache

    live = {
        "quarterly": {"_headers": ["Jun 2026"]},
        "annual_pl": {"_headers": ["Mar 2026"]},
    }
    cached = {
        "quarterly": {"_headers": ["Mar 2024", "Jun 2026"]},
        "annual_pl": {"_headers": ["Mar 2023", "Mar 2026", "TTM"]},
        "balance_sheet": {"_headers": ["Mar 2022", "Mar 2026"]},
        "cash_flow": {"_headers": ["Mar 2022", "Mar 2026"]},
    }

    merged = _merge_pg_financial_cache(live, cached)

    assert merged["annual_pl"]["_headers"] == ["Mar 2023", "Mar 2026", "TTM"]
    assert merged["balance_sheet"]["_headers"] == ["Mar 2022", "Mar 2026"]
    assert merged["cash_flow"]["_headers"] == ["Mar 2022", "Mar 2026"]


def test_atherenerg_technical_read_explains_conflicting_signals():
    from scripts.generate_research_report import _build_placeholders_generic

    placeholders = _build_placeholders_generic(
        symbol="ATHERENERG",
        sc={"ratios": {"Name": "Ather Energy Limited"}},
        tech={"sma20": "1458.55", "sma50": "1281.34", "sma200": "901.72", "adx": "37.0", "supertrend": "SELL"},
        snap={"institutional_bias": 76},
        web={},
    )

    narrative = placeholders["TECHNICAL_NARRATIVE"]
    assert "ADX" in narrative and "does not identify whether the direction is up or down" in narrative
    assert "positive trend with incomplete confirmation" in narrative
    assert "PAT growth" in narrative and "negative" in narrative
