from datetime import date, datetime

from terminal.research_council.evidence_pack_builder import build_sector_opportunity_evidence_pack
from terminal.research_council import tool_adapters
from terminal.research_council.schemas import CouncilState, StewardVerdict
from terminal.research_council.states import market_state


def _snapshot():
    return {
        "eod_latest": date(2026, 5, 26),
        "stage_latest": date(2026, 5, 26),
        "financials_latest": date(2026, 5, 26),
        "total_symbols": 2465,
        "liquid_symbols": 982,
        "analyzed_symbols": 968,
    }


def _sector_context():
    return {
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
                "company_name": "Bajaj Auto Ltd",
                "stage": "STAGE_2",
                "investment_score": 91,
                "relative_strength": 84,
                "change_1m_pct": 12.5,
                "rsi": 63,
                "trading_signal": "BUY",
            },
            {
                "symbol": "EXIDEIND",
                "company_name": "Exide Industries Ltd",
                "stage": "STAGE_1",
                "investment_score": 86,
                "relative_strength": 71,
                "change_1m_pct": 6.2,
                "rsi": 58,
                "trading_signal": "HOLD",
            },
        ],
        "weakest_3": [{"symbol": "HEROMOTOCO", "investment_score": 42}],
        "data_source": "PostgreSQL scores.stage_snapshots",
    }


def test_sector_opportunity_evidence_pack_normalizes_sector_context():
    pack = build_sector_opportunity_evidence_pack(
        sector="NIFTY AUTO",
        as_of=date(2026, 5, 26),
        steward_verdict=StewardVerdict(as_of=date(2026, 5, 26), data_status="usable"),
        snapshot_loader=_snapshot,
        sector_context_loader=lambda sector: _sector_context(),
    )

    assert pack.mode == "sector_opportunity"
    assert pack.sections["sector_opportunity"]["requested_sector"] == "NIFTY AUTO"
    assert pack.sections["sector_opportunity"]["resolved_sector"] == "EV & Auto Ancillaries"
    assert pack.sections["sectors"]["items"][0]["sector"] == "EV & Auto Ancillaries"
    assert pack.sections["stocks"]["count"] == 2
    assert pack.sections["stocks"]["candidates"][0]["symbol"] == "BAJAJ-AUTO"
    assert pack.sections["stocks"]["candidates"][0]["rs"] == 84
    assert pack.sections["stocks"]["candidates"][0]["rank"] == 1
    assert pack.source_trail[-1].source == "sector.top_stocks"
    assert pack.source_trail[-1].metadata["requested_sector"] == "NIFTY AUTO"


def test_sector_opportunity_market_state_uses_route_sector(monkeypatch):
    state = CouncilState(
        run_id="research_20260527_001",
        session_id="s1",
        created_at=datetime(2026, 5, 27, 10, 0),
        mode="sector_opportunity",
        stage="market_state",
        objective="Analyze NIFTY AUTO and identify best potential stocks",
        horizon="swing",
        risk_budget="moderate",
        universe_filter="liquid",
        steward_verdict=StewardVerdict(as_of=date(2026, 5, 26), data_status="usable"),
        route_decision={"sector": "NIFTY AUTO"},
    )
    called = {}

    def fake_builder(**kwargs):
        called.update(kwargs)
        return build_sector_opportunity_evidence_pack(
            sector=kwargs["sector"],
            as_of=kwargs["as_of"],
            steward_verdict=kwargs["steward_verdict"],
            snapshot_loader=_snapshot,
            sector_context_loader=lambda sector: _sector_context(),
        )

    monkeypatch.setattr(market_state, "build_sector_opportunity_evidence_pack", fake_builder)

    updated = market_state.run(state)

    assert called["sector"] == "NIFTY AUTO"
    assert updated.evidence_pack is not None
    assert updated.evidence_pack.sections["stocks"]["candidates"][0]["symbol"] == "BAJAJ-AUTO"


def test_sector_opportunity_loader_retries_without_nifty_prefix(monkeypatch):
    calls = []

    def fake_sector_top_stocks(**kwargs):
        calls.append(kwargs["sector"])
        if kwargs["sector"] == "NIFTY AUTO":
            return {"error": "PostgreSQL scores.stage_snapshots unavailable"}
        return _sector_context()

    monkeypatch.setattr(tool_adapters, "sector_top_stocks", fake_sector_top_stocks)

    pack = build_sector_opportunity_evidence_pack(
        sector="NIFTY AUTO",
        as_of=date(2026, 5, 26),
        steward_verdict=StewardVerdict(as_of=date(2026, 5, 26), data_status="usable"),
        snapshot_loader=_snapshot,
    )

    assert calls == ["NIFTY AUTO", "AUTO"]
    assert pack.sections["stocks"]["candidates"][0]["symbol"] == "BAJAJ-AUTO"
    assert pack.source_trail[-1].metadata["lookup_sector"] == "AUTO"
