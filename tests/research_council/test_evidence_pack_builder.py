from datetime import date, datetime

from terminal.research_council.evidence_pack_builder import build_research_evidence_pack
from terminal.research_council.schemas import CouncilState, EvidencePack, StewardVerdict
from terminal.research_council.states import market_state


def _snapshot():
    return {
        "eod_latest": date(2026, 5, 26),
        "stage_latest": date(2026, 5, 26),
        "fno_latest": date(2026, 5, 22),
        "financials_latest": date(2026, 5, 26),
        "total_symbols": 2465,
        "liquid_symbols": 982,
        "analyzed_symbols": 968,
        "filters": ["close > 100", "volume > 100000", "at least 50 bars"],
    }


def _sections():
    return {
        "market": {"regime": "CHOP", "breadth": {"pct_above_50dma": 48}},
        "sectors": {"leaders": ["Nifty Metal", "Nifty Pharma"]},
        "stocks": {
            "count": 3,
            "candidates": [
                {"symbol": "AAA", "score": 91},
                {"symbol": "BBB", "score": 88},
                {"symbol": "CCC", "score": 84},
            ],
        },
        "derivatives": {"latest_date": "2026-05-22"},
        "fundamentals": {"latest_date": "2026-05-26"},
        "events": {"upcoming_count": 12},
        "reports": {"sector_rotation": "reports/latest/sector_rotation.html"},
    }


def test_build_evidence_pack_contains_required_sections_and_source_trail():
    pack = build_research_evidence_pack(
        mode="market_council",
        as_of=date(2026, 5, 26),
        universe_filter="liquid",
        snapshot_loader=_snapshot,
        section_loader=_sections,
    )

    assert isinstance(pack, EvidencePack)
    assert pack.mode == "market_council"
    assert pack.as_of == date(2026, 5, 26)
    assert set(pack.sections) == {
        "market",
        "sectors",
        "stocks",
        "derivatives",
        "fundamentals",
        "events",
        "reports",
    }
    assert {entry.source for entry in pack.source_trail} >= {
        "market.equity_eod",
        "scores.stage_snapshots",
        "derivatives.fno_eod",
        "scores.financials_refresh_log",
    }
    assert pack.missing_evidence[0].field == "fno_stale"


def test_build_evidence_pack_limits_stock_candidates_for_agent_context():
    def many_stocks():
        sections = _sections()
        sections["stocks"] = {
            "count": 100,
            "candidates": [{"symbol": f"SYM{i:03d}", "score": i} for i in range(100)],
        }
        return sections

    pack = build_research_evidence_pack(
        mode="market_council",
        as_of=date(2026, 5, 26),
        snapshot_loader=_snapshot,
        section_loader=many_stocks,
        max_stock_candidates=10,
    )

    assert pack.sections["stocks"]["count"] == 100
    assert len(pack.sections["stocks"]["candidates"]) == 10
    assert pack.sections["stocks"]["truncated"] is True


def test_evidence_pack_roundtrip_from_builder():
    pack = build_research_evidence_pack(
        mode="market_council",
        as_of=date(2026, 5, 26),
        snapshot_loader=_snapshot,
        section_loader=_sections,
    )

    assert EvidencePack.from_dict(pack.to_dict()) == pack


def test_market_state_handler_attaches_pack_when_not_dry_run(monkeypatch):
    state = CouncilState(
        run_id="research_20260526_001",
        session_id="s1",
        created_at=datetime(2026, 5, 26, 10, 0),
        mode="market_council",
        stage="market_state",
        objective="today",
        horizon="swing",
        risk_budget="moderate",
        universe_filter="liquid",
        steward_verdict=StewardVerdict(as_of=date(2026, 5, 26), data_status="degraded"),
    )
    pack = build_research_evidence_pack(
        mode="market_council",
        as_of=date(2026, 5, 26),
        snapshot_loader=_snapshot,
        section_loader=_sections,
    )
    monkeypatch.setattr(market_state, "build_research_evidence_pack", lambda **_: pack)

    updated = market_state.run(state)

    assert updated.evidence_pack == pack
    assert updated.evidence_pack_id == pack.pack_id


def test_market_state_handler_skips_pack_in_dry_run(monkeypatch):
    state = CouncilState(
        run_id="research_20260526_001",
        session_id="s1",
        created_at=datetime(2026, 5, 26, 10, 0),
        mode="market_council",
        stage="market_state",
        objective="today",
        horizon="swing",
        risk_budget="moderate",
        universe_filter="liquid",
        flags={"dry_run": True},
    )
    monkeypatch.setattr(market_state, "build_research_evidence_pack", lambda **_: (_ for _ in ()).throw(AssertionError("called")))

    assert market_state.run(state) == state
