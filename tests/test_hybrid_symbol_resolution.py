from terminal.symbol_search import (
    ResolveCandidate,
    ResolveResult,
    project_legacy_result,
)


def test_resolve_result_projects_exact_legacy_shape():
    result = ResolveResult(
        symbol="TRENT",
        legacy_confidence="exact",
        confidence_band="exact",
        score=1.0,
        raw_score=1.0,
        query="TRENT",
        candidates=(
            ResolveCandidate(
                symbol="TRENT",
                score=1.0,
                raw_score=1.0,
                methods=("dict",),
                matched="TRENT",
            ),
        ),
        method="dict",
        matched="TRENT",
    )

    assert result.needs_clarification is False
    assert result.to_dict() == {
        "symbol": "TRENT",
        "legacy_confidence": "exact",
        "confidence_band": "exact",
        "score": 1.0,
        "raw_score": 1.0,
        "query": "TRENT",
        "candidates": [
            {
                "symbol": "TRENT",
                "score": 1.0,
                "raw_score": 1.0,
                "methods": ["dict"],
                "matched": "TRENT",
            }
        ],
        "method": "dict",
        "matched": "TRENT",
        "needs_clarification": False,
    }
    assert project_legacy_result(result) == {
        "symbol": "TRENT",
        "confidence": "exact",
        "score": 1.0,
        "confidence_band": "exact",
        "query": "TRENT",
        "candidates": ["TRENT"],
        "method": "dict",
        "matched": "TRENT",
    }


def test_medium_result_keeps_legacy_fuzzy_and_sets_clarification_flag():
    result = ResolveResult(
        symbol="TRENT",
        legacy_confidence="fuzzy",
        confidence_band="medium",
        score=0.72,
        raw_score=0.031,
        query="trent ltd",
        candidates=(
            ResolveCandidate(
                symbol="TRENT",
                score=0.72,
                raw_score=0.031,
                methods=("trigram",),
                matched="Trent Limited",
            ),
        ),
        method="trigram",
        matched="Trent Limited",
    )

    assert result.needs_clarification is True
    assert project_legacy_result(result)["confidence"] == "fuzzy"
    assert project_legacy_result(result)["confidence_band"] == "medium"


def test_low_result_projects_none_symbol_and_candidate_list():
    result = ResolveResult(
        symbol=None,
        legacy_confidence="none",
        confidence_band="low",
        score=0.42,
        raw_score=0.018,
        query="market action",
        candidates=(
            ResolveCandidate(
                symbol="FMNL",
                score=0.42,
                raw_score=0.018,
                methods=("trigram",),
                matched="Future Market Networks Limited",
            ),
        ),
        method="trigram",
        matched="",
    )

    projected = project_legacy_result(result)

    assert result.needs_clarification is True
    assert projected["symbol"] is None
    assert projected["confidence"] == "none"
    assert projected["candidates"] == ["FMNL"]


def test_result_validates_confidence_values_and_score_bounds():
    try:
        ResolveResult(
            symbol="TRENT",
            legacy_confidence="high",
            confidence_band="high",
            score=1.2,
            raw_score=0.05,
            query="TRENT",
            candidates=(),
            method="dict",
        )
    except ValueError as exc:
        assert "legacy_confidence" in str(exc)
    else:
        raise AssertionError("ResolveResult accepted invalid confidence/score values")
