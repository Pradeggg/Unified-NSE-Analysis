from datetime import date, datetime

from terminal.research_council.schemas import (
    BranchSummary,
    CouncilState,
    CriticFinding,
    CriticReview,
    EvidencePack,
    MissingEvidence,
    Plan,
    PlanReview,
)
from terminal.research_council.states import synthesis


def _state(**overrides):
    pack = EvidencePack(
        pack_id="pack_1",
        as_of=date(2026, 5, 27),
        mode="market_council",
        source_trail=[],
    )
    base = {
        "run_id": "research_20260527_001",
        "session_id": "s1",
        "created_at": datetime(2026, 5, 27, 10, 0),
        "mode": "market_council",
        "stage": "synthesis",
        "objective": "today",
        "horizon": "swing",
        "risk_budget": "moderate",
        "universe_filter": "liquid",
        "evidence_pack": pack,
        "branch_summaries": [
            BranchSummary(
                summary_id="b1",
                branch="momentum_leadership",
                stance="constructive",
                supporting_agents=["technical", "sector_rotation"],
                dissenting_agents=["fundamental"],
                candidates=["AAA"],
                risks=["extended setup"],
            )
        ],
        "plans": [Plan(plan_id="plan_1", run_id="run_1", iteration=0, central_question="test")],
        "plan_reviews": [PlanReview(plan_id="plan_1", advance=True, advance_rationale="ok")],
    }
    base.update(overrides)
    return CouncilState(**base)


def test_synthesis_selects_research_long_when_evidence_passes():
    updated = synthesis.run(_state())

    assert updated.decision.final_label == "RESEARCH_LONG"
    assert updated.decision.candidates[0]["symbol"] == "AAA"
    assert updated.decision.dissent_log == ["fundamental dissented on momentum_leadership", "extended setup"]


def test_synthesis_never_research_long_with_blocking_critic():
    critic = CriticReview(
        review_id="cr_1",
        critic="risk",
        run_id="research_20260527_001",
        iteration=0,
        severity_max="block",
        findings=[
            CriticFinding(
                finding_id="cf_1",
                severity="block",
                target={"kind": "decision", "id": "candidate"},
                description="unsupported claim",
                recommendation="downgrade",
            )
        ],
    )

    updated = synthesis.run(_state(critic_reviews=[[critic]]))

    assert updated.decision.final_label == "REVIEW_MANUALLY"
    assert updated.decision.confidence < 0.7


def test_synthesis_downgrades_when_plan_loop_cap_hit():
    updated = synthesis.run(_state(flags={"plan_loop_cap_hit": True}))

    assert updated.decision.final_label == "REVIEW_MANUALLY"
    assert "plan loop cap" in updated.decision.rationale


def test_synthesis_waits_for_confirmation_when_evidence_is_missing():
    pack = EvidencePack(
        pack_id="pack_1",
        as_of=date(2026, 5, 27),
        mode="market_council",
        missing_evidence=[
            MissingEvidence(scope="derivatives", subject="AAA", field="fno_positioning", severity="warn")
        ],
    )

    updated = synthesis.run(_state(evidence_pack=pack))

    assert updated.decision.final_label == "WAIT_FOR_CONFIRMATION"
    assert updated.decision.missing_evidence == pack.missing_evidence
    assert "fno" not in updated.decision.candidates[0]


def test_synthesis_attaches_sector_quant_sweep_to_candidates():
    state = _state(
        mode="sector_opportunity",
        execution_results={
            "plan_1": {
                "coder_quant_shortlist_sweep": {
                    "result_id": "plan_1:coder_quant_shortlist_sweep",
                    "step_id": "coder_quant_shortlist_sweep",
                    "status": "success",
                    "outputs": [
                        {
                            "ok": True,
                            "best": {
                                "request": {"strategy_family": "stage2_breakout", "allowed_horizons": [10]},
                                "result": {
                                    "verdict": "SUPPORTED",
                                    "metrics": {
                                        "splits": {
                                            "validation": {
                                                "return_pct": 8.5,
                                                "sharpe": 0.9,
                                                "trade_count": 35,
                                            }
                                        }
                                    },
                                },
                                "rank_score": 81.2,
                                "symbol_attribution": {
                                    "AAA": {
                                        "validation_return_pct": 8.5,
                                        "validation_trade_count": 7,
                                        "total_trade_count": 19,
                                    }
                                },
                            },
                            "ranked_options": [{"rank_score": 81.2}, {"rank_score": 62.5}],
                            "symbols": ["AAA"],
                        }
                    ],
                }
            }
        },
    )

    updated = synthesis.run(state)

    quant = updated.decision.candidates[0]["quant_sweep"]
    assert quant["verdict"] == "SUPPORTED"
    assert quant["strategy_family"] == "stage2_breakout"
    assert quant["horizon_days"] == 10
    assert quant["validation_return_pct"] == 8.5
    assert quant["routes_ranked"] == 2
    assert quant["symbol_attribution"]["validation_trade_count"] == 7


def test_sector_synthesis_ranks_candidates_by_specialist_quant_and_sector_evidence():
    pack = EvidencePack(
        pack_id="pack_sector",
        as_of=date(2026, 5, 27),
        mode="sector_opportunity",
        sections={
            "stocks": {
                "candidates": [
                    {"symbol": "AAA", "rank": 1, "score": 80},
                    {"symbol": "BBB", "rank": 2, "score": 92},
                ]
            }
        },
    )
    state = _state(
        mode="sector_opportunity",
        evidence_pack=pack,
        branch_summaries=[
            BranchSummary(
                summary_id="b_sector",
                branch="sector_rotation",
                stance="targeted_shortlist",
                supporting_agents=["sector_rotation"],
                candidates=["AAA", "BBB"],
                risks=[],
            ),
            BranchSummary(
                summary_id="b_momentum",
                branch="momentum_leadership",
                stance="constructive",
                supporting_agents=["technical", "minervini"],
                candidates=["BBB"],
                risks=[],
            ),
        ],
        execution_results={
            "plan_1": {
                "coder_quant_shortlist_sweep": {
                    "result_id": "plan_1:coder_quant_shortlist_sweep",
                    "step_id": "coder_quant_shortlist_sweep",
                    "status": "success",
                    "outputs": [
                        {
                            "ok": True,
                            "best": {
                                "request": {"strategy_family": "stage2_breakout", "allowed_horizons": [10]},
                                "result": {
                                    "verdict": "SUPPORTED",
                                    "metrics": {"splits": {"validation": {"return_pct": 5.0, "sharpe": 0.8, "trade_count": 20}}},
                                },
                                "rank_score": 70,
                                "symbol_attribution": {
                                    "AAA": {"validation_return_pct": 1.0, "validation_trade_count": 3},
                                    "BBB": {"validation_return_pct": 6.5, "validation_trade_count": 9},
                                },
                            },
                            "ranked_options": [{"rank_score": 70}],
                            "symbols": ["AAA", "BBB"],
                        }
                    ],
                }
            }
        },
    )

    updated = synthesis.run(state)

    assert [row["symbol"] for row in updated.decision.candidates] == ["BBB", "AAA"]
    leader = updated.decision.candidates[0]
    assert leader["research_score"] > updated.decision.candidates[1]["research_score"]
    assert leader["supporting_branches"] == ["sector_rotation", "momentum_leadership"]
    assert leader["score_components"]["quant_symbol_return"] == 6.5
    assert leader["score_components"]["sector_score"] == 92


def test_sector_synthesis_separates_route_verdict_from_candidate_quant_contribution():
    pack = EvidencePack(
        pack_id="pack_sector",
        as_of=date(2026, 5, 28),
        mode="sector_opportunity",
        sections={
            "stocks": {
                "candidates": [
                    {"symbol": "AAA", "rank": 1, "score": 80},
                    {"symbol": "BBB", "rank": 2, "score": 80},
                    {"symbol": "CCC", "rank": 3, "score": 80},
                ]
            }
        },
    )
    state = _state(
        mode="sector_opportunity",
        evidence_pack=pack,
        branch_summaries=[
            BranchSummary(
                summary_id="b_sector",
                branch="sector_rotation",
                stance="targeted_shortlist",
                supporting_agents=["sector_rotation"],
                candidates=["AAA", "BBB", "CCC"],
                risks=[],
            )
        ],
        execution_results={
            "plan_1": {
                "coder_quant_shortlist_sweep": {
                    "result_id": "plan_1:coder_quant_shortlist_sweep",
                    "step_id": "coder_quant_shortlist_sweep",
                    "status": "success",
                    "outputs": [
                        {
                            "ok": True,
                            "best": {
                                "request": {"strategy_family": "stage2_breakout", "allowed_horizons": [5]},
                                "result": {
                                    "verdict": "SUPPORTED",
                                    "metrics": {"splits": {"validation": {"return_pct": 12.0, "sharpe": 1.1, "trade_count": 20}}},
                                },
                                "rank_score": 100,
                                "symbol_attribution": {
                                    "AAA": {"validation_return_pct": 8.0, "validation_trade_count": 3},
                                    "BBB": {"validation_return_pct": -5.0, "validation_trade_count": 2},
                                },
                            },
                            "ranked_options": [{"rank_score": 100}],
                            "symbols": ["AAA", "BBB", "CCC"],
                        }
                    ],
                }
            }
        },
    )

    updated = synthesis.run(state)
    rows = {row["symbol"]: row for row in updated.decision.candidates}

    assert rows["AAA"]["quant_sweep"]["route_verdict"] == "SUPPORTED"
    assert rows["AAA"]["quant_sweep"]["verdict"] == "SUPPORTED"
    assert rows["BBB"]["quant_sweep"]["route_verdict"] == "SUPPORTED"
    assert rows["BBB"]["quant_sweep"]["verdict"] == "NEGATIVE_CONTRIBUTION"
    assert rows["CCC"]["quant_sweep"]["route_verdict"] == "SUPPORTED"
    assert rows["CCC"]["quant_sweep"]["verdict"] == "NO_SYMBOL_TRADE"
    assert rows["AAA"]["research_score"] > rows["CCC"]["research_score"] > rows["BBB"]["research_score"]


def test_sector_synthesis_stays_watchlist_when_quant_is_only_confirming_branch():
    pack = EvidencePack(
        pack_id="pack_sector",
        as_of=date(2026, 5, 27),
        mode="sector_opportunity",
        sections={"stocks": {"candidates": [{"symbol": "AAA", "rank": 1, "score": 90}]}},
    )
    state = _state(
        mode="sector_opportunity",
        evidence_pack=pack,
        branch_summaries=[
            BranchSummary(
                summary_id="b_sector",
                branch="sector_rotation",
                stance="targeted_shortlist",
                supporting_agents=["sector_rotation"],
                candidates=["AAA"],
                risks=["insufficient technical evidence"],
            )
        ],
        execution_results={
            "plan_1": {
                "coder_quant_shortlist_sweep": {
                    "result_id": "plan_1:coder_quant_shortlist_sweep",
                    "step_id": "coder_quant_shortlist_sweep",
                    "status": "success",
                    "outputs": [
                        {
                            "ok": True,
                            "best": {
                                "request": {"strategy_family": "stage2_breakout", "allowed_horizons": [5]},
                                "result": {
                                    "verdict": "SUPPORTED",
                                    "metrics": {"splits": {"validation": {"return_pct": 10.0, "sharpe": 1.0, "trade_count": 40}}},
                                },
                                "rank_score": 100,
                                "symbol_attribution": {"AAA": {"validation_return_pct": 10.0, "validation_trade_count": 5}},
                            },
                            "ranked_options": [{"rank_score": 100}],
                            "symbols": ["AAA"],
                        }
                    ],
                }
            }
        },
    )

    updated = synthesis.run(state)

    assert updated.decision.final_label == "WATCHLIST"
    assert "Quant route is supported, but sector-only evidence needs another confirming branch" in updated.decision.rationale


def test_sector_synthesis_rationale_flags_degraded_quant_and_sector_only_evidence():
    pack = EvidencePack(
        pack_id="pack_sector",
        as_of=date(2026, 5, 27),
        mode="sector_opportunity",
        sections={"stocks": {"candidates": [{"symbol": "AAA", "rank": 1, "score": 90}]}},
    )
    state = _state(
        mode="sector_opportunity",
        evidence_pack=pack,
        branch_summaries=[
            BranchSummary(
                summary_id="b_sector",
                branch="sector_rotation",
                stance="targeted_shortlist",
                supporting_agents=["sector_rotation"],
                candidates=["AAA"],
                risks=[],
            )
        ],
        plan_reviews=[
            PlanReview(
                plan_id="plan_1",
                advance=False,
                advance_rationale="One or more evidence steps failed.",
                step_verdicts=[
                    {
                        "step_id": "coder_quant_shortlist_sweep",
                        "status": "degraded",
                        "error": "quant sweep produced no testable routes",
                    }
                ],
            )
        ],
    )

    updated = synthesis.run(state)

    assert updated.decision.final_label == "WATCHLIST"
    assert "Quant route sweep was degraded" in updated.decision.rationale
    assert "Sector-only evidence needs another confirming branch" in updated.decision.rationale
