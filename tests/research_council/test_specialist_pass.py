from datetime import date, datetime

from terminal.research_council.schemas import CouncilState, EvidencePack
from terminal.research_council.states import specialist_pass


def _state():
    pack = EvidencePack(
        pack_id="pack_1",
        as_of=date(2026, 5, 27),
        mode="market_council",
        sections={
            "sectors": {
                "items": [
                    {
                        "sector": "Capital Goods",
                        "rs_1m": 14,
                        "rs_3m": 20,
                        "breadth_pct_above_50dma": 72,
                        "stage2_count": 10,
                        "top_stocks": ["AAA"],
                    }
                ]
            },
            "stocks": {
                "candidates": [
                    {
                        "symbol": "AAA",
                        "stage": "STAGE_2",
                        "rs": 82,
                        "price_above_sma20": True,
                        "price_above_sma50": True,
                        "price_above_sma200": True,
                        "rsi": 64,
                        "macd": "bullish",
                        "supertrend": "BUY",
                        "volume_ratio": 1.4,
                        "from_52w_high_pct": -4,
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
                        "debt_to_equity": 0.3,
                        "promoter_pledge": 0,
                        "opm": 20,
                    }
                ]
            },
        },
    )
    return CouncilState(
        run_id="research_20260527_001",
        session_id="s1",
        created_at=datetime(2026, 5, 27, 10, 0),
        mode="market_council",
        stage="specialist_pass",
        objective="today",
        horizon="swing",
        risk_budget="moderate",
        universe_filter="liquid",
        evidence_pack=pack,
        evidence_pack_id=pack.pack_id,
    )


def test_specialist_pass_runs_three_agents_and_persists(monkeypatch):
    saved = []
    monkeypatch.setattr(specialist_pass, "save_agent_findings", lambda findings, **_: saved.extend(findings))

    updated = specialist_pass.run(_state())

    assert set(updated.specialist_findings) == {
        "macro_regime",
        "sector_rotation",
        "technical",
        "minervini",
        "fundamental",
        "fno_risk",
        "catalyst",
    }
    assert len(saved) == 7
    assert updated.specialist_findings["technical"].candidates == ["AAA"]


def test_specialist_pass_skips_work_in_dry_run(monkeypatch):
    state = _state()
    data = state.to_dict()
    data["flags"] = {"dry_run": True}
    dry_state = CouncilState.from_dict(data)
    monkeypatch.setattr(specialist_pass, "save_agent_findings", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("called")))

    assert specialist_pass.run(dry_state) == dry_state


def test_specialist_pass_records_agent_failure_without_crashing(monkeypatch):
    class BrokenAgent:
        name = "broken"

        def run(self, *_args, **_kwargs):
            raise RuntimeError("boom")

    monkeypatch.setattr(specialist_pass, "DEFAULT_AGENTS", (BrokenAgent(),))
    monkeypatch.setattr(specialist_pass, "save_agent_findings", lambda *_args, **_kwargs: None)

    updated = specialist_pass.run(_state())

    assert updated.flags["specialist_failures"][0]["agent"] == "broken"
    assert updated.specialist_findings == {}
