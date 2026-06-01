from datetime import date, datetime

from terminal.research_council.critics.data_quality import DataQualityCritic
from terminal.research_council.schemas import CouncilState, Decision, EvidencePack, MissingEvidence, SourceTrailEntry


def _state(pack):
    return CouncilState(
        run_id="run_1",
        session_id="s1",
        created_at=datetime(2026, 5, 27, 10, 0),
        mode="market_council",
        stage="critic_review",
        objective="today",
        horizon="swing",
        risk_budget="moderate",
        universe_filter="liquid",
        evidence_pack=pack,
        decision=Decision(final_label="RESEARCH_LONG", confidence=0.8, rationale="ok", candidates=[{"symbol": "AAA"}]),
    )


def test_data_quality_blocks_blocking_missing_evidence():
    pack = EvidencePack(
        pack_id="pack_1",
        as_of=date(2026, 5, 27),
        mode="market_council",
        missing_evidence=[MissingEvidence(scope="data", subject="run", field="eod_stale", severity="block")],
    )

    review = DataQualityCritic().review(_state(pack))

    assert review.severity_max == "block"
    assert review.findings[0].severity == "block"
    assert "eod_stale" in review.findings[0].description


def test_data_quality_warns_on_nonblocking_missing_evidence():
    pack = EvidencePack(
        pack_id="pack_1",
        as_of=date(2026, 5, 27),
        mode="market_council",
        missing_evidence=[MissingEvidence(scope="derivatives", subject="run", field="fno_stale", severity="warn")],
        source_trail=[SourceTrailEntry(source="market.equity_eod")],
    )

    review = DataQualityCritic().review(_state(pack))

    assert review.severity_max == "warn"


def test_data_quality_blocks_source_missing_decision_claim():
    pack = EvidencePack(pack_id="pack_1", as_of=date(2026, 5, 27), mode="market_council", source_trail=[])

    review = DataQualityCritic().review(_state(pack))

    assert review.severity_max == "block"
    assert review.findings[0].target == {"kind": "decision", "id": "source_trail"}
