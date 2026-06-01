from datetime import date

from terminal.research_council import engine
from terminal.research_council.evidence_pack_builder import build_research_evidence_pack, build_sector_opportunity_evidence_pack
from terminal.research_council.schemas import StewardVerdict
from terminal.research_council.states import branch_deliberation, critic_review, data_steward, market_state, persistence, plan_execute, render_html, specialist_pass
from terminal.research_council.tool_registry import ToolRegistry


def _registry_for_default_plan():
    registry = ToolRegistry()
    for name in [
        "regime.detect",
        "breadth.summarize",
        "flows.fii_dii_5d",
        "macro.proxy_signals",
        "sector.rs_ranking",
        "sector.breadth_health",
        "sector.top_stocks",
        "screen.stage2",
        "screen.high_rs",
        "screen.momentum_52w",
        "fno.buildup",
        "fund.results_trend",
        "events.upcoming",
        "fund.balance_sheet_health",
    ]:
        registry.register(name, lambda **_: {"ok": True, "items": []})
    return registry


def test_market_council_engine_e2e_fixture(monkeypatch, tmp_path):
    persisted = {"runs": [], "evidence": [], "plans": [], "initial_runs": []}
    verdict = StewardVerdict(
        as_of=date(2026, 5, 27),
        data_status="usable",
        universe={"total_symbols": 100, "liquid_symbols": 50, "analyzed_symbols": 40},
    )
    pack = build_research_evidence_pack(
        mode="market_council",
        as_of=verdict.as_of,
        steward_verdict=verdict,
        snapshot_loader=lambda: {
            "eod_latest": verdict.as_of,
            "stage_latest": verdict.as_of,
            "fno_latest": verdict.as_of,
            "financials_latest": verdict.as_of,
            "total_symbols": 100,
            "liquid_symbols": 50,
            "analyzed_symbols": 40,
        },
        section_loader=lambda: {
            "market": {"regime": "RISK_ON"},
            "sectors": {
                "items": [
                    {
                        "sector": "Capital Goods",
                        "rs_1m": 12,
                        "breadth_pct_above_50dma": 70,
                        "stage2_count": 5,
                        "top_stocks": ["AAA"],
                    }
                ]
            },
            "stocks": {
                "candidates": [
                    {
                        "symbol": "AAA",
                        "stage": "STAGE_2",
                        "rs": 85,
                        "price_above_sma20": True,
                        "price_above_sma50": True,
                        "price_above_sma200": True,
                        "rsi": 62,
                        "macd": "bullish",
                        "supertrend": "BUY",
                        "volume_ratio": 1.5,
                        "from_52w_high_pct": -5,
                        "close": 100,
                        "atr": 4,
                    }
                ]
            },
            "fundamentals": {
                "items": [
                    {
                        "symbol": "AAA",
                        "sales_growth": 20,
                        "profit_growth": 25,
                        "roe": 18,
                        "roce": 22,
                        "debt_to_equity": 0.2,
                        "promoter_pledge": 0,
                        "opm": 20,
                    }
                ]
            },
            "derivatives": {},
            "events": {},
            "reports": {},
        },
    )
    monkeypatch.setattr(data_steward, "run_check", lambda mode: verdict)
    monkeypatch.setattr(market_state, "build_research_evidence_pack", lambda **_: pack)
    monkeypatch.setattr(specialist_pass, "save_agent_findings", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(branch_deliberation, "save_branch_summaries", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(critic_review, "save_critic_reviews", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(plan_execute, "DEFAULT_REGISTRY", _registry_for_default_plan())
    monkeypatch.setattr(plan_execute, "save_execution_results", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(plan_execute, "save_council_plans", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(render_html, "REPORT_DIR", tmp_path)
    monkeypatch.setattr(engine, "persist_run_metadata", lambda state, **_: persisted["initial_runs"].append(state.run_id))
    monkeypatch.setattr(persistence, "save_evidence_pack", lambda evidence_pack, **_: persisted["evidence"].append(evidence_pack.pack_id))
    monkeypatch.setattr(persistence, "save_council_plans", lambda plans, **_: persisted["plans"].extend(plan.plan_id for plan in plans))
    monkeypatch.setattr(persistence, "save_council_run_metadata", lambda state, **_: persisted["runs"].append(state.run_id))

    state = engine.run_council("/council today --horizon swing --risk moderate")

    assert state.stage == "persistence"
    assert state.decision is not None
    assert state.decision.final_label == "RESEARCH_LONG"
    assert state.flags["markdown_report_path"] == str(tmp_path / f"{state.run_id}.md")
    assert (tmp_path / f"{state.run_id}.md").exists()
    assert persisted["initial_runs"] == [state.run_id]
    assert persisted["runs"] == [state.run_id]
    assert persisted["evidence"] == [pack.pack_id]
    assert persisted["plans"] == [state.plans[-1].plan_id]


def test_sector_opportunity_engine_e2e_shortlists_from_sector_context(monkeypatch, tmp_path):
    persisted = {"runs": [], "evidence": [], "plans": [], "initial_runs": []}
    verdict = StewardVerdict(
        as_of=date(2026, 5, 26),
        data_status="usable",
        universe={"total_symbols": 100, "liquid_symbols": 50, "analyzed_symbols": 40},
    )

    def sector_pack(**kwargs):
        return build_sector_opportunity_evidence_pack(
            sector=kwargs["sector"],
            as_of=kwargs["as_of"],
            steward_verdict=kwargs["steward_verdict"],
            snapshot_loader=lambda: {
                "eod_latest": verdict.as_of,
                "stage_latest": verdict.as_of,
                "financials_latest": verdict.as_of,
                "total_symbols": 100,
                "liquid_symbols": 50,
                "analyzed_symbols": 40,
            },
            sector_context_loader=lambda sector: {
                "sector": "EV & Auto Ancillaries",
                "snapshot_date": "2026-05-26",
                "total_stocks": 22,
                "stage2_count": 6,
                "buy_signals": 4,
                "avg_rs_pct": 3.0,
                "avg_1m_pct": 1.84,
                "top5_by_score": [
                    {
                        "symbol": "BAJAJ-AUTO",
                        "stage": "STAGE_2",
                        "investment_score": 91,
                        "relative_strength": 84,
                        "change_1m_pct": 12.5,
                        "rsi": 63,
                        "trading_signal": "BUY",
                    }
                ],
                "data_source": "PostgreSQL scores.stage_snapshots",
            },
        )

    monkeypatch.setattr(data_steward, "run_check", lambda mode: verdict)
    monkeypatch.setattr(market_state, "build_sector_opportunity_evidence_pack", sector_pack)
    monkeypatch.setattr(specialist_pass, "save_agent_findings", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(branch_deliberation, "save_branch_summaries", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(critic_review, "save_critic_reviews", lambda *_args, **_kwargs: None)
    registry = ToolRegistry()
    registry.register(
        "strategy.build",
        lambda **_: {
            "ok": True,
            "best": {
                "request": {"strategy_family": "stage2_breakout", "allowed_horizons": [10]},
                "result": {"verdict": "AMBIGUOUS", "metrics": {"splits": {"validation": {"return_pct": 3.0}}}},
                "rank_score": 50,
            },
            "ranked_options": [{"rank_score": 50}],
            "symbols": ["BAJAJ-AUTO"],
        },
    )
    monkeypatch.setattr(plan_execute, "DEFAULT_REGISTRY", registry)
    monkeypatch.setattr(plan_execute, "save_execution_results", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(plan_execute, "save_council_plans", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(render_html, "REPORT_DIR", tmp_path)
    monkeypatch.setattr(engine, "persist_run_metadata", lambda state, **_: persisted["initial_runs"].append(state.run_id))
    monkeypatch.setattr(persistence, "save_evidence_pack", lambda evidence_pack, **_: persisted["evidence"].append(evidence_pack.pack_id))
    monkeypatch.setattr(persistence, "save_council_plans", lambda plans, **_: persisted["plans"].extend(plan.plan_id for plan in plans))
    monkeypatch.setattr(persistence, "save_council_run_metadata", lambda state, **_: persisted["runs"].append(state.run_id))

    state = engine.run_council("Analyze NIFTY AUTO and identify best potential stocks")

    assert state.mode == "sector_opportunity"
    assert state.evidence_pack.sections["sector_opportunity"]["requested_sector"] == "NIFTY AUTO"
    assert state.specialist_findings["sector_rotation"].candidates == ["BAJAJ-AUTO"]
    assert state.decision.final_label == "WATCHLIST"
    assert state.decision.candidates[0]["symbol"] == "BAJAJ-AUTO"
    assert persisted["initial_runs"] == [state.run_id]
    assert persisted["runs"] == [state.run_id]
    assert persisted["evidence"] == [state.evidence_pack.pack_id]
