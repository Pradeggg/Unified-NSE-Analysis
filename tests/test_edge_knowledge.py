from datetime import datetime, timezone

import pandas as pd

from terminal.edge_knowledge import (
    EdgeRefreshRun,
    build_edge_nodes,
    classify_edge_status,
    fetch_persistence_counts,
    make_claim_id,
    render_edge_memory_html,
    render_edge_memory_markdown,
    summarize_edge_memory,
    write_edge_memory_report,
    persist_edge_nodes,
    score_edge_confidence,
)


class FakeCursor:
    def __init__(self, statements):
        self.statements = statements
        self.results = []

    def execute(self, sql, params=None):
        self.statements.append((sql, params))

    def fetchone(self):
        return self.results.pop(0) if self.results else None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeConnection:
    def __init__(self):
        self.statements = []
        self.committed = False

    def cursor(self):
        return FakeCursor(self.statements)

    def commit(self):
        self.committed = True


class FailingSelectConnection:
    def __init__(self):
        self.rolled_back = False

    def cursor(self):
        connection = self

        class Cursor:
            def execute(self, sql, params=None):
                raise RuntimeError("relation research.edge_knowledge_nodes does not exist")

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        return Cursor()

    def rollback(self):
        self.rolled_back = True


def test_claim_id_is_stable_for_same_condition():
    first = make_claim_id(
        setup="ORB + VWAP",
        direction="LONG",
        timeframe="15m",
        symbol="MIDCPNIFTY",
        session_bucket="opening_drive",
        vol_regime="normal",
        pcr_regime="put-heavy",
    )
    second = make_claim_id(
        setup="ORB + VWAP",
        direction="long",
        timeframe="15M",
        symbol="midcpnifty",
        session_bucket="opening_drive",
        vol_regime="normal",
        pcr_regime="put-heavy",
    )

    assert first == second
    assert first.startswith("edge_")


def test_confidence_rewards_walk_forward_sample_size_and_persistence():
    weak = score_edge_confidence(
        trades_n=4,
        expectancy_r=0.02,
        profit_factor=1.02,
        wf_status="unconfirmed",
        wf_positive_rate=0,
        wf_worst_r=-0.8,
        persistence_count=0,
    )
    strong = score_edge_confidence(
        trades_n=40,
        expectancy_r=0.18,
        profit_factor=1.7,
        wf_status="confirmed",
        wf_positive_rate=75,
        wf_worst_r=-0.16,
        persistence_count=3,
    )

    assert 0 <= weak < strong <= 1
    assert strong >= 0.75


def test_classify_edge_status_transitions_from_candidate_to_promoted_and_retired():
    assert classify_edge_status(confidence=0.86, wf_status="confirmed", edge_role="core_carrier", persistence_count=2) == "promoted"
    assert classify_edge_status(confidence=0.62, wf_status="confirmed", edge_role="core_carrier", persistence_count=0) == "candidate"
    assert classify_edge_status(confidence=0.72, wf_status="rejected_out_of_sample", edge_role="core_carrier", persistence_count=4) == "decaying"
    assert classify_edge_status(confidence=0.18, wf_status="confirmed", edge_role="edge_diluter", persistence_count=0) == "retired"


def test_build_edge_nodes_combines_symbol_drilldown_with_walk_forward_lineage():
    drilldown = pd.DataFrame(
        [
            {
                "symbol": "MIDCPNIFTY",
                "symbol_edge_status": "core_carrier",
                "setup": "ORB + VWAP",
                "timeframe": "15m",
                "direction": "LONG",
                "trades": 25,
                "win_rate": 64.0,
                "expectancy_r": 0.26,
                "profit_factor": 2.22,
                "best_volatility_regime": "normal",
                "best_pcr_regime": "put-heavy",
            }
        ]
    )
    walk_forward = pd.DataFrame(
        [
            {
                "setup": "ORB + VWAP",
                "timeframe": "15m",
                "direction": "LONG",
                "walk_forward_status": "confirmed",
                "folds_tested": 4,
                "validation_positive_fold_rate": 75.0,
                "worst_validation_r": -0.16,
            }
        ]
    )
    nodes = build_edge_nodes(
        confirmed_symbol_drilldown=drilldown,
        walk_forward=walk_forward,
        evidence_set_id="seed-20260621",
        bar_count=14748,
        code_version="abc123",
        generated_at=datetime(2026, 6, 21, tzinfo=timezone.utc),
        persistence_counts={"MIDCPNIFTY|ORB + VWAP|15m|LONG|opening_drive|normal|put-heavy": 2},
    )

    assert len(nodes) == 1
    node = nodes[0]
    assert node.symbol == "MIDCPNIFTY"
    assert node.edge_role == "core_carrier"
    assert node.wf_status == "confirmed"
    assert node.status == "promoted"
    assert node.confidence >= 0.75
    assert node.lineage["evidence_set_id"] == "seed-20260621"
    assert node.lineage["bar_count"] == 14748


def test_persist_edge_nodes_creates_schema_and_upserts_rows():
    conn = FakeConnection()
    refresh = EdgeRefreshRun(
        refresh_id="refresh_20260621_000000",
        evidence_set_id="seed-20260621",
        generated_at=datetime(2026, 6, 21, tzinfo=timezone.utc),
        source_report="reports/latest/intraday_fno_indicator_study.html",
        bar_count=14748,
        symbol_count=85,
        trade_count=2946,
        code_version="abc123",
    )
    nodes = build_edge_nodes(
        confirmed_symbol_drilldown=pd.DataFrame(
            [
                {
                    "symbol": "360ONE",
                    "symbol_edge_status": "core_carrier",
                    "setup": "ORB + VWAP",
                    "timeframe": "15m",
                    "direction": "LONG",
                    "trades": 16,
                    "win_rate": 62.5,
                    "expectancy_r": 0.27,
                    "profit_factor": 2.41,
                    "best_volatility_regime": "high",
                    "best_pcr_regime": "-",
                }
            ]
        ),
        walk_forward=pd.DataFrame(
            [
                {
                    "setup": "ORB + VWAP",
                    "timeframe": "15m",
                    "direction": "LONG",
                    "walk_forward_status": "confirmed",
                    "folds_tested": 4,
                    "validation_positive_fold_rate": 75.0,
                    "worst_validation_r": -0.16,
                }
            ]
        ),
        evidence_set_id="seed-20260621",
        bar_count=14748,
        code_version="abc123",
        generated_at=refresh.generated_at,
    )

    result = persist_edge_nodes(conn, refresh, nodes)

    assert result["nodes"] == 1
    assert result["refresh_id"] == "refresh_20260621_000000"
    assert conn.committed
    assert any("CREATE SCHEMA IF NOT EXISTS research" in sql for sql, _ in conn.statements)
    assert any("edge_knowledge_nodes" in sql and "ON CONFLICT" in sql for sql, _ in conn.statements)
    assert any("edge_refresh_history" in sql and "INSERT INTO" in sql for sql, _ in conn.statements)


def test_fetch_persistence_counts_rolls_back_when_schema_is_missing():
    conn = FailingSelectConnection()

    counts = fetch_persistence_counts(conn)

    assert counts == {}
    assert conn.rolled_back


def test_edge_memory_summary_and_report_surface_active_and_retired_edges(tmp_path):
    rows = [
        {
            "claim_id": "edge_mid",
            "symbol": "MIDCPNIFTY",
            "setup": "ORB + VWAP",
            "direction": "LONG",
            "timeframe": "15m",
            "session_bucket": "opening_drive",
            "vol_regime": "normal",
            "pcr_regime": "put-heavy",
            "expectancy_r": 0.2616,
            "profit_factor": 2.21,
            "win_rate": 64.0,
            "trades_n": 25,
            "wf_status": "confirmed",
            "wf_folds": 4,
            "wf_positive_rate": 75.0,
            "wf_worst_r": -0.16,
            "edge_role": "core_carrier",
            "confidence": 0.8348,
            "persistence_count": 2,
            "status": "candidate",
            "first_seen": datetime(2026, 6, 20, tzinfo=timezone.utc),
            "last_confirmed": datetime(2026, 6, 21, tzinfo=timezone.utc),
            "updated_at": datetime(2026, 6, 21, tzinfo=timezone.utc),
        },
        {
            "claim_id": "edge_nifty",
            "symbol": "NIFTY",
            "setup": "ORB + VWAP",
            "direction": "LONG",
            "timeframe": "15m",
            "session_bucket": "opening_drive",
            "vol_regime": "-",
            "pcr_regime": "-",
            "expectancy_r": -0.2476,
            "profit_factor": 0.53,
            "win_rate": 41.0,
            "trades_n": 22,
            "wf_status": "confirmed",
            "wf_folds": 4,
            "wf_positive_rate": 75.0,
            "wf_worst_r": -0.16,
            "edge_role": "edge_diluter",
            "confidence": 0.5096,
            "persistence_count": 1,
            "status": "retired",
            "first_seen": datetime(2026, 6, 21, tzinfo=timezone.utc),
            "last_confirmed": None,
            "updated_at": datetime(2026, 6, 21, tzinfo=timezone.utc),
        },
    ]

    summary = summarize_edge_memory(rows)
    markdown = render_edge_memory_markdown(rows, summary=summary, generated_at=datetime(2026, 6, 21, tzinfo=timezone.utc))
    html = render_edge_memory_html(rows, summary=summary, generated_at=datetime(2026, 6, 21, tzinfo=timezone.utc))
    paths = write_edge_memory_report(
        rows,
        output_dir=tmp_path,
        generated_at=datetime(2026, 6, 21, 16, 55, tzinfo=timezone.utc),
    )

    assert summary["total_edges"] == 2
    assert summary["status_counts"]["candidate"] == 1
    assert summary["status_counts"]["retired"] == 1
    assert "MIDCPNIFTY" in markdown
    assert "No-Trade / Retired Edges" in markdown
    assert "Edge Memory Dashboard" in html
    assert "core_carrier" in html
    assert (tmp_path / "edge_knowledge_report.html").exists()
    assert (tmp_path / "edge_knowledge_report.md").exists()
    assert (tmp_path / "edge_knowledge_report.json").exists()
    assert paths["html"].endswith("edge_knowledge_report.html")
