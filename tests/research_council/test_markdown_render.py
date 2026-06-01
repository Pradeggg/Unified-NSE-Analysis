from datetime import date, datetime

from terminal.research_council.reports.markdown_renderer import render_markdown, write_markdown_report
from terminal.research_council.reports.html_renderer import render_html as render_html_document
from terminal.research_council.schemas import (
    AgentFinding,
    BranchSummary,
    CouncilState,
    CriticFinding,
    CriticReview,
    Decision,
    EvidencePack,
    ExecutionResult,
    MissingEvidence,
    Plan,
    PlanReview,
    PlanStep,
    SourceTrailEntry,
    ToolCall,
)
from terminal.research_council.states import render_html


def _state():
    pack = EvidencePack(
        pack_id="pack_1",
        as_of=date(2026, 5, 27),
        mode="market_council",
        universe_filter="liquid",
        symbols=["AAA"],
        sections={
            "market": {"regime": "RISK_ON", "breadth": "healthy"},
            "sectors": {"items": [{"sector": "Capital Goods", "rs_1m": 12, "breadth_pct_above_50dma": 70}]},
        },
        source_trail=[SourceTrailEntry(source="pg.eod", rows=100, latest_date="2026-05-27", freshness="fresh")],
        missing_evidence=[MissingEvidence(scope="derivatives", subject="AAA", field="fno_positioning")],
    )
    plan = Plan(
        plan_id="plan_1",
        run_id="research_1",
        iteration=0,
        central_question="Find actionable leaders",
        steps=[
            PlanStep(
                step_id="regime",
                sequence=1,
                question="Is regime supportive?",
                tool_calls=[ToolCall("regime.detect")],
            )
        ],
    )
    return CouncilState(
        run_id="research_1",
        session_id="s1",
        created_at=datetime(2026, 5, 27, 10, 0),
        mode="market_council",
        stage="render_html",
        objective="/council today",
        horizon="swing",
        risk_budget="moderate",
        universe_filter="liquid",
        evidence_pack=pack,
        evidence_pack_id=pack.pack_id,
        specialist_findings={
            "technical": AgentFinding(
                finding_id="af_1",
                agent="technical",
                stance="constructive",
                confidence=0.7,
                thesis="AAA is actionable",
                candidates=["AAA"],
            )
        },
        branch_summaries=[
            BranchSummary(
                summary_id="bs_1",
                branch="momentum_leadership",
                stance="constructive",
                candidates=["AAA"],
                risks=["extension"],
            )
        ],
        plans=[plan],
        execution_results={"plan_1": {"regime": ExecutionResult("er_1", "regime", "success", [{"ok": True}])}},
        plan_reviews=[PlanReview(plan_id="plan_1", advance=True, advance_rationale="All executed plan steps passed.")],
        decision=Decision(
            final_label="WAIT_FOR_CONFIRMATION",
            confidence=0.7,
            rationale="Needs F&O confirmation.",
            candidates=[{"symbol": "AAA", "supporting_branch": "momentum_leadership"}],
            dissent_log=["extension"],
            missing_evidence=pack.missing_evidence,
        ),
    )


def test_markdown_renderer_includes_required_sections_and_disclaimers():
    markdown = render_markdown(_state())

    for heading in [
        "# Research Council Report",
        "## Objective And Mode",
        "## Data Freshness",
        "## Market State",
        "## Sector View",
        "## Candidate Table",
        "## Candidate Score Drivers",
        "## Agent Findings",
        "## Public POT/TOT Summaries",
        "## Plan Steps",
        "## Execution Results",
        "## Plan Review",
        "## Critic Review",
        "## Final Research Plan",
        "## Invalidation And Next Actions",
        "## Missing Evidence",
    ]:
        assert heading in markdown
    assert markdown.count("Not investment advice. For research and learning only.") >= 2
    assert "AAA" in markdown
    assert "WAIT_FOR_CONFIRMATION" in markdown


def test_markdown_candidate_table_includes_quant_sweep_summary():
    state = _state()
    data = state.to_dict()
    data["decision"]["candidates"][0]["quant_sweep"] = {
        "verdict": "SUPPORTED",
        "strategy_family": "stage2_breakout",
        "horizon_days": 10,
        "validation_return_pct": 8.5,
        "symbol_attribution": {"validation_return_pct": 4.2, "validation_trade_count": 7},
    }
    data["decision"]["candidates"][0]["research_score"] = 86.4
    markdown = render_markdown(CouncilState.from_dict(data))

    assert "| Symbol | Score | Label | Supporting Branch | Quant Verdict | Best Route | Validation Return | Symbol Contribution |" in markdown
    assert "| AAA | 86.4 | WAIT_FOR_CONFIRMATION | momentum_leadership | SUPPORTED | stage2_breakout/10d | 8.5 | 4.2 / 7 trades |" in markdown


def test_candidate_report_uses_candidate_quant_verdict_not_route_verdict():
    state = _state()
    data = state.to_dict()
    data["decision"]["candidates"] = [
        {
            "symbol": "AAA",
            "supporting_branch": "sector_rotation",
            "research_score": 80,
            "quant_sweep": {
                "route_verdict": "SUPPORTED",
                "verdict": "NO_SYMBOL_TRADE",
                "strategy_family": "stage2_breakout",
                "horizon_days": 5,
                "validation_return_pct": 12.0,
            },
            "score_components": {
                "quant_route_verdict": "SUPPORTED",
                "quant_verdict": "NO_SYMBOL_TRADE",
                "quant_validation_return": 12.0,
            },
        }
    ]
    state = CouncilState.from_dict(data)

    markdown = render_markdown(state)
    html = render_html_document(state)

    assert "| AAA | 80 | WAIT_FOR_CONFIRMATION | sector_rotation | NO_SYMBOL_TRADE | stage2_breakout/5d | 12 | n/a |" in markdown
    assert "quant NO_SYMBOL_TRADE" in markdown
    assert "route SUPPORTED" in markdown
    assert "NO_SYMBOL_TRADE" in html
    assert "route SUPPORTED" in html


def test_html_report_includes_quant_sweep_candidate_table():
    state = _state()
    data = state.to_dict()
    data["decision"]["candidates"][0]["quant_sweep"] = {
        "verdict": "SUPPORTED",
        "strategy_family": "stage2_breakout",
        "horizon_days": 10,
        "validation_return_pct": 8.5,
        "symbol_attribution": {"validation_return_pct": 4.2, "validation_trade_count": 7},
    }
    data["decision"]["candidates"][0]["research_score"] = 86.4
    html = render_html_document(CouncilState.from_dict(data))

    assert "Candidate Ranking" in html
    assert "86.4" in html
    assert "stage2_breakout/10d" in html
    assert "SUPPORTED" in html
    assert "4.2 / 7 trades" in html


def test_reports_include_candidate_score_drivers():
    state = _state()
    data = state.to_dict()
    data["decision"]["candidates"][0]["research_score"] = 86.4
    data["decision"]["candidates"][0]["score_components"] = {
        "sector_rank": 1,
        "sector_score": 80,
        "supporting_agents": 2,
        "supporting_branches": 1,
        "quant_verdict": "SUPPORTED",
        "quant_validation_return": 8.5,
        "quant_symbol_return": 4.2,
        "risk_count": 1,
    }
    state = CouncilState.from_dict(data)

    markdown = render_markdown(state)
    html = render_html_document(state)

    assert "## Candidate Score Drivers" in markdown
    assert "AAA: sector rank #1, sector score 80, agents 2, branches 1, quant SUPPORTED, validation +8.5%, symbol +4.2%, risks 1" in markdown
    assert "Candidate Score Drivers" in html
    assert "sector rank #1, sector score 80, agents 2, branches 1, quant SUPPORTED, validation +8.5%, symbol +4.2%, risks 1" in html


def test_candidate_report_formatting_uses_na_and_integer_rank():
    state = _state()
    data = state.to_dict()
    data["decision"]["candidates"][0]["quant_sweep"] = {
        "verdict": None,
        "validation_return_pct": None,
    }
    data["decision"]["candidates"][0]["score_components"] = {
        "sector_rank": 1.0,
        "sector_score": 67.0,
        "supporting_agents": 1,
        "supporting_branches": 1,
        "risk_count": 1,
    }
    markdown = render_markdown(CouncilState.from_dict(data))

    assert "| AAA | n/a | WAIT_FOR_CONFIRMATION | momentum_leadership | n/a | n/a | n/a | n/a |" in markdown
    assert "AAA: sector rank #1, sector score 67, agents 1, branches 1, risks 1" in markdown


def test_reports_include_plan_review_degraded_reason():
    state = _state()
    data = state.to_dict()
    data["plan_reviews"][0]["advance"] = False
    data["plan_reviews"][0]["step_verdicts"] = [
        {
            "step_id": "coder_quant_shortlist_sweep",
            "status": "degraded",
            "error": "quant sweep produced no testable routes",
        }
    ]
    data["plan_reviews"][0]["advance_rationale"] = "One or more evidence steps failed."
    state = CouncilState.from_dict(data)

    markdown = render_markdown(state)
    html = render_html_document(state)

    assert "## Plan Review" in markdown
    assert "- Advance: False" in markdown
    assert "coder_quant_shortlist_sweep: degraded; error=quant sweep produced no testable routes" in markdown
    assert "Plan Review" in html
    assert "quant sweep produced no testable routes" in html


def test_reports_include_route_sweep_details():
    state = _state()
    data = state.to_dict()
    data["execution_results"]["plan_1"]["coder_quant_shortlist_sweep"] = ExecutionResult(
        "er_quant",
        "coder_quant_shortlist_sweep",
        "success",
        [
            {
                "ok": True,
                "ranked_options": [
                    {
                        "request": {"strategy_family": "stage2_breakout", "allowed_horizons": [5]},
                        "result": {
                            "verdict": "SUPPORTED",
                            "metrics": {"splits": {"validation": {"return_pct": 12.3, "sharpe": 1.1, "trade_count": 42}}},
                        },
                        "rank_score": 123.4,
                    },
                    {
                        "request": {"strategy_family": "vcp_breakout", "allowed_horizons": [10]},
                        "result": {
                            "verdict": "AMBIGUOUS",
                            "metrics": {"splits": {"validation": {"return_pct": 1.2, "sharpe": 0.2, "trade_count": 4}}},
                        },
                        "rank_score": 30,
                    },
                ],
                "untestable": [{"request": {"strategy_family": "supertrend_continuation", "allowed_horizons": [5]}, "error": "unsupported_strategy"}],
            }
        ],
    ).to_dict()
    state = CouncilState.from_dict(data)

    markdown = render_markdown(state)
    html = render_html_document(state)

    assert "## Route Sweep Details" in markdown
    assert "| stage2_breakout/5d | SUPPORTED | 12.3 | 1.1 | 42 | 123.4 |" in markdown
    assert "| supertrend_continuation/5d | UNTESTABLE | n/a | n/a | n/a | unsupported_strategy |" in markdown
    assert "Route Sweep Details" in html
    assert "stage2_breakout/5d" in html
    assert "unsupported_strategy" in html


def test_reports_mark_quant_sweep_success_as_degraded_when_no_routes_tested():
    state = _state()
    data = state.to_dict()
    data["execution_results"]["plan_1"]["coder_quant_shortlist_sweep"] = ExecutionResult(
        "er_quant",
        "coder_quant_shortlist_sweep",
        "success",
        [
            {
                "ok": True,
                "routes_tested": 0,
                "routes_untestable": 9,
                "ranked_options": [],
                "untestable": [{"request": {"strategy_family": "stage2_breakout", "allowed_horizons": [5]}, "error": "llm_unavailable"}],
            }
        ],
    ).to_dict()
    state = CouncilState.from_dict(data)

    markdown = render_markdown(state)
    html = render_html_document(state)

    assert "coder_quant_shortlist_sweep: degraded; error=quant sweep produced no testable routes" in markdown
    assert "coder_quant_shortlist_sweep: degraded - quant sweep produced no testable routes" in html


def test_reports_include_structured_evidence_gates():
    state = _state()
    data = state.to_dict()
    data["specialist_findings"] = {
        "technical": {
            "finding_id": "technical_1",
            "agent": "technical",
            "stance": "neutral",
            "confidence": 0.3,
            "thesis": "0 actionable technical setups identified.",
            "candidates": [],
        },
        "fno_risk": {
            "finding_id": "fno_1",
            "agent": "fno_risk",
            "stance": "unavailable",
            "confidence": 0.2,
            "thesis": "F&O evidence is unavailable.",
            "candidates": [],
        },
        "fundamental": {
            "finding_id": "fund_1",
            "agent": "fundamental",
            "stance": "neutral",
            "confidence": 0.3,
            "thesis": "0 candidates have supportive quality evidence.",
            "candidates": [],
        },
        "catalyst": {
            "finding_id": "cat_1",
            "agent": "catalyst",
            "stance": "absent",
            "confidence": 0.25,
            "thesis": "No catalyst evidence available.",
            "candidates": [],
        },
    }
    state = CouncilState.from_dict(data)

    markdown = render_markdown(state)
    html = render_html_document(state)

    assert "## Evidence Gates" in markdown
    assert "| technical | PENDING | neutral | 0 actionable technical setups identified. |" in markdown
    assert "| fno_risk | PENDING | unavailable | F&O evidence is unavailable. |" in markdown
    assert "Evidence Gates" in html
    assert "PENDING" in html


def test_reports_derive_missing_evidence_from_pending_specialist_gates():
    state = _state()
    data = state.to_dict()
    data["evidence_pack"]["missing_evidence"] = []
    data["decision"]["missing_evidence"] = []
    data["specialist_findings"] = {
        "technical": {
            "finding_id": "technical_1",
            "agent": "technical",
            "stance": "neutral",
            "confidence": 0.3,
            "thesis": "0 actionable technical setups identified.",
            "candidates": [],
        },
        "fno_risk": {
            "finding_id": "fno_1",
            "agent": "fno_risk",
            "stance": "unavailable",
            "confidence": 0.2,
            "thesis": "F&O evidence is unavailable.",
            "candidates": [],
        },
    }
    state = CouncilState.from_dict(data)

    markdown = render_markdown(state)
    html = render_html_document(state)

    assert "technical/council: specialist_confirmation (warn)" in markdown
    assert "fno_risk/council: specialist_confirmation (warn)" in markdown
    assert "technical/council: specialist_confirmation" in html
    assert "fno_risk/council: specialist_confirmation" in html


def test_reports_prefer_candidate_specific_missing_evidence_from_critic_findings():
    state = _state()
    data = state.to_dict()
    data["evidence_pack"]["missing_evidence"] = []
    data["decision"]["missing_evidence"] = []
    data["decision"]["candidates"] = [{"symbol": "AAA", "supporting_branch": "sector_rotation"}]
    data["critic_reviews"] = [
        [
            CriticReview(
                review_id="evidence_1",
                critic="evidence",
                run_id="research_1",
                iteration=0,
                severity_max="warn",
                summary="2 evidence findings.",
                findings=[
                    CriticFinding(
                        finding_id="evidence_technical_confirmation_AAA",
                        severity="warn",
                        target={"kind": "candidate", "id": "AAA"},
                        description="Quant is supported, but technical confirmation is not yet source-backed for AAA.",
                        recommendation="Keep as WATCHLIST until technical setup evidence confirms.",
                    ),
                    CriticFinding(
                        finding_id="evidence_fno_confirmation_AAA",
                        severity="warn",
                        target={"kind": "candidate", "id": "AAA"},
                        description="Quant is supported, but F&O confirmation is not yet source-backed for AAA.",
                        recommendation="Keep as WATCHLIST until derivatives positioning evidence confirms.",
                    ),
                ],
            ).to_dict()
        ]
    ]
    state = CouncilState.from_dict(data)

    markdown = render_markdown(state)
    html = render_html_document(state)

    assert "technical/AAA: technical_confirmation (warn)" in markdown
    assert "fno_risk/AAA: fno_confirmation (warn)" in markdown
    assert "technical/council: specialist_confirmation" not in markdown
    assert "technical/AAA: technical_confirmation" in html
    assert "fno_risk/AAA: fno_confirmation" in html


def test_write_markdown_report_creates_research_council_report(tmp_path):
    path = write_markdown_report(_state(), output_dir=tmp_path)

    assert path.name == "research_1.md"
    assert path.read_text().startswith("# Research Council Report")


def test_render_state_writes_markdown_path_into_flags(tmp_path, monkeypatch):
    monkeypatch.setattr(render_html, "REPORT_DIR", tmp_path)

    updated = render_html.run(_state())

    assert updated.flags["markdown_report_path"] == str(tmp_path / "research_1.md")
    assert (tmp_path / "research_1.md").exists()
