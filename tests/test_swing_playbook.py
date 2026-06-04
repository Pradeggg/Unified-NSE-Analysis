from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd

from terminal.swing_playbook import (
    SwingPlaybookOptions,
    SwingPlaybookResult,
    build_portfolio_actions,
    build_risk_plan,
    generate_swing_playbook,
    handle_swing_playbook_command,
    normalize_candidate_frame,
    parse_swing_playbook_args,
    rank_swing_candidates,
    score_candidate,
)


def test_build_risk_plan_uses_atr_stop_and_reward_risk_target():
    row = pd.Series({"close": 100.0, "atr_14": 4.0, "sma_20": 96.0, "sma_50": 90.0})

    plan = build_risk_plan(row, sleeve="TACTICAL")

    assert plan.entry_trigger == 101.0
    assert plan.initial_stop == 92.8
    assert plan.stop_distance_pct == 8.1
    assert plan.target_1 == 113.3
    assert plan.target_2 == 117.4
    assert plan.r_multiple_target_1 == 1.5
    assert plan.r_multiple_target_2 == 2.0


def test_parse_swing_playbook_args_supports_filters_and_fresh():
    options = parse_swing_playbook_args("/swing-playbook --fresh --portfolio --top-n 7")

    assert options.fresh is True
    assert options.section == "portfolio"
    assert options.top_n == 7


def test_handle_swing_playbook_command_includes_report_line_for_registry_memory():
    result = SwingPlaybookResult(
        success=True,
        markdown="# Swing Trading Playbook",
        html_path="/tmp/report.html",
        markdown_path="/tmp/report.md",
        candidates_csv="/tmp/candidates.csv",
        portfolio_csv="/tmp/portfolio.csv",
    )

    with patch("terminal.swing_playbook.generate_swing_playbook", return_value=result):
        output = handle_swing_playbook_command("/swing-playbook --portfolio")

    assert "Report: /tmp/report.html" in output
    assert "Markdown: /tmp/report.md" in output


def test_normalize_candidate_frame_fills_optional_columns_and_reports_warnings():
    raw = pd.DataFrame(
        [
            {
                "symbol": "AAA",
                "close": 100.0,
                "volume": 1_000_000,
                "stage": "STAGE_2",
                "technical_score": 75,
            }
        ]
    )

    frame, warnings = normalize_candidate_frame(raw)

    assert frame.loc[0, "symbol"] == "AAA"
    assert frame.loc[0, "sector"] == "Unknown"
    assert frame.loc[0, "relative_strength"] == 50.0
    assert frame.loc[0, "vcp_pick"] == 0
    assert "filled missing optional columns" in warnings[0]


def test_normalize_candidate_frame_coerces_portfolio_holding_strings_to_bool():
    raw = pd.DataFrame(
        [
            {
                "symbol": "AAA",
                "close": 100.0,
                "volume": 1_000_000,
                "stage": "STAGE_2",
                "technical_score": 75,
                "is_portfolio_holding": "False",
            },
            {
                "symbol": "BBB",
                "close": 200.0,
                "volume": 2_000_000,
                "stage": "STAGE_2",
                "technical_score": 80,
                "is_portfolio_holding": "0",
            },
            {
                "symbol": "CCC",
                "close": 300.0,
                "volume": 3_000_000,
                "stage": "STAGE_2",
                "technical_score": 85,
                "is_portfolio_holding": "yes",
            },
        ]
    )

    frame, _ = normalize_candidate_frame(raw)

    assert frame["is_portfolio_holding"].tolist() == [False, False, True]


def test_relative_strength_ratio_values_are_normalized_to_percent_scale():
    raw = pd.DataFrame(
        [
            {
                "symbol": "RATIO",
                "close": 100,
                "volume": 1_000_000,
                "stage": "STAGE_2",
                "technical_score": 80,
                "relative_strength": 0.88,
            },
            {
                "symbol": "PCT",
                "close": 100,
                "volume": 1_000_000,
                "stage": "STAGE_2",
                "technical_score": 80,
                "relative_strength": 88.0,
            },
        ]
    )

    frame, _ = normalize_candidate_frame(raw)

    ratio = frame.loc[frame["symbol"] == "RATIO", "relative_strength"].iloc[0]
    assert ratio == 88.0
    assert score_candidate(frame.iloc[0], sleeve="TACTICAL").relative_strength == score_candidate(
        frame.iloc[1], sleeve="TACTICAL"
    ).relative_strength


def _candidate_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "symbol": "LEADER",
                "company_name": "Leader Ltd",
                "sector": "IT",
                "close": 200.0,
                "volume": 1_500_000,
                "turnover_cr": 40.0,
                "stage": "STAGE_2",
                "technical_score": 86,
                "relative_strength": 88,
                "rsi_14": 62,
                "sma_20": 190,
                "sma_50": 175,
                "sma_200": 150,
                "atr_14": 8,
                "volume_ratio_20d": 1.8,
                "vcp_pick": 1,
                "vcp_score": 84,
                "vcp_breakout_pct": 2.4,
                "vcp_contraction_pct": 12,
                "enhanced_fund_score": 72,
                "sales_growth_pct": 18,
                "pat_growth_pct": 22,
                "latest_result_age_days": 70,
            },
            {
                "symbol": "LAGGARD",
                "company_name": "Laggard Ltd",
                "sector": "Metals",
                "close": 120.0,
                "volume": 600_000,
                "turnover_cr": 8.0,
                "stage": "STAGE_3",
                "technical_score": 45,
                "relative_strength": 35,
                "rsi_14": 44,
                "sma_20": 125,
                "sma_50": 128,
                "sma_200": 130,
                "atr_14": 6,
                "volume_ratio_20d": 0.8,
                "vcp_pick": 0,
                "vcp_score": 10,
                "vcp_breakout_pct": -1.0,
                "vcp_contraction_pct": 0,
                "enhanced_fund_score": 40,
                "sales_growth_pct": -5,
                "pat_growth_pct": -8,
                "latest_result_age_days": 400,
            },
        ]
    )


def test_score_candidate_prefers_strong_stage2_vcp_for_tactical():
    frame, _ = normalize_candidate_frame(_candidate_frame())

    leader = score_candidate(frame.iloc[0], sleeve="TACTICAL")
    laggard = score_candidate(frame.iloc[1], sleeve="TACTICAL")

    assert leader.total > laggard.total
    assert leader.pattern > laggard.pattern
    assert leader.technical > laggard.technical


def test_rank_swing_candidates_returns_both_sleeves_with_action_labels():
    frame, _ = normalize_candidate_frame(_candidate_frame())

    tactical, position = rank_swing_candidates(frame, top_n=5)

    assert tactical[0].symbol == "LEADER"
    assert tactical[0].sleeve == "TACTICAL"
    assert tactical[0].entry_label == "EOD_READY"
    assert position[0].symbol == "LEADER"
    assert position[0].sleeve == "POSITION"


def test_load_candidates_from_postgres_returns_required_columns(monkeypatch):
    import terminal.swing_playbook as sp

    expected = _candidate_frame()

    def fake_read_sql_query(query, conn, params=None):
        assert "scores.stage_snapshots" in query
        assert "market.equity_eod" in query
        return expected

    fake_conn = MagicMock()
    fake_connect = MagicMock()
    fake_connect.return_value.__enter__.return_value = fake_conn
    monkeypatch.setattr(sp, "_pg_table_exists", lambda conn, qualified_name: True)
    monkeypatch.setattr(sp.pd, "read_sql_query", fake_read_sql_query)
    with patch.dict("sys.modules", {"psycopg2": MagicMock(connect=fake_connect)}):
        loaded = sp.load_candidates_from_postgres(SwingPlaybookOptions(top_n=2))

    assert {"symbol", "close", "volume", "stage", "technical_score"}.issubset(loaded.columns)
    assert loaded["symbol"].tolist() == ["LEADER", "LAGGARD"]


def test_load_candidates_from_postgres_omits_vcp_join_when_table_absent(monkeypatch):
    import terminal.swing_playbook as sp

    captured: dict[str, str] = {}

    def fake_table_exists(conn, qualified_name):
        return qualified_name != "scores.stage2_vcp_picks"

    def fake_read_sql_query(query, conn, params=None):
        captured["query"] = query
        return _candidate_frame()

    fake_connect = MagicMock()
    fake_connect.return_value.__enter__.return_value = MagicMock()
    monkeypatch.setattr(sp, "_pg_table_exists", fake_table_exists)
    monkeypatch.setattr(sp.pd, "read_sql_query", fake_read_sql_query)
    with patch.dict("sys.modules", {"psycopg2": MagicMock(connect=fake_connect)}):
        sp.load_candidates_from_postgres(SwingPlaybookOptions(top_n=2))

    assert "scores.stage2_vcp_picks" not in captured["query"]


def test_load_candidates_from_postgres_derives_indicator_fallbacks_for_zero_values(monkeypatch):
    import terminal.swing_playbook as sp

    expected = _candidate_frame()
    zero_columns = ["sma_20", "sma_50", "sma_200", "atr_14", "volume_ratio_20d"]
    expected.loc[:, zero_columns] = 0.0

    def fake_read_sql_query(query, conn, params=None):
        return expected

    fake_connect = MagicMock()
    fake_connect.return_value.__enter__.return_value = MagicMock()
    monkeypatch.setattr(sp, "_pg_table_exists", lambda conn, qualified_name: False)
    monkeypatch.setattr(sp.pd, "read_sql_query", fake_read_sql_query)
    with patch.dict("sys.modules", {"psycopg2": MagicMock(connect=fake_connect)}):
        loaded = sp.load_candidates_from_postgres(SwingPlaybookOptions(top_n=2))

    for column in zero_columns:
        assert (loaded[column] > 0).all()


def test_build_portfolio_actions_emits_all_portfolio_labels():
    frame = pd.DataFrame(
        [
            {
                "symbol": "ADDME",
                "close": 120.0,
                "stage": "STAGE_2",
                "technical_score": 82,
                "relative_strength": 85,
                "rsi_14": 61,
                "sma_20": 114,
                "sma_50": 105,
                "sma_200": 90,
                "atr_14": 5,
                "volume": 1_000_000,
                "is_portfolio_holding": True,
                "position_value": 80_000,
            },
            {
                "symbol": "WATCH",
                "close": 95.0,
                "stage": "STAGE_3",
                "technical_score": 48,
                "relative_strength": 42,
                "rsi_14": 43,
                "sma_20": 100,
                "sma_50": 101,
                "sma_200": 104,
                "atr_14": 4,
                "volume": 600_000,
                "is_portfolio_holding": True,
                "position_value": 60_000,
            },
            {
                "symbol": "HOLDME",
                "close": 100.0,
                "stage": "STAGE_1",
                "technical_score": 65,
                "relative_strength": 60,
                "rsi_14": 55,
                "sma_20": 96,
                "sma_50": 90,
                "sma_200": 80,
                "atr_14": 3,
                "volume": 500_000,
                "is_portfolio_holding": True,
                "position_value": 50_000,
            },
            {
                "symbol": "TIGHTEN",
                "close": 105.0,
                "stage": "STAGE_3",
                "technical_score": 62,
                "relative_strength": 52,
                "rsi_14": 49,
                "sma_20": 110,
                "sma_50": 100,
                "sma_200": 95,
                "atr_14": 4,
                "volume": 700_000,
                "is_portfolio_holding": True,
                "position_value": 55_000,
            },
            {
                "symbol": "NOADD",
                "close": 110.0,
                "stage": "STAGE_2",
                "technical_score": 55,
                "relative_strength": 54,
                "rsi_14": 50,
                "sma_20": 100,
                "sma_50": 92,
                "sma_200": 86,
                "atr_14": 4,
                "volume": 450_000,
                "is_portfolio_holding": True,
                "position_value": 45_000,
            },
        ]
    )
    frame, _ = normalize_candidate_frame(frame)

    actions = build_portfolio_actions(frame)
    labels = {action.symbol: action.label for action in actions}

    assert labels["ADDME"] == "ADD_OK"
    assert labels["WATCH"] == "EXIT_WATCH"
    assert labels["HOLDME"] == "HOLD"
    assert labels["TIGHTEN"] == "TIGHTEN_STOP"
    assert labels["NOADD"] == "NO_FRESH_ADD"


def test_generate_swing_playbook_writes_markdown_html_and_csv(tmp_path):
    frame, _ = normalize_candidate_frame(_candidate_frame())
    frame["is_portfolio_holding"] = frame["symbol"].eq("LEADER")
    options = SwingPlaybookOptions(project_root=tmp_path, top_n=5)

    result = generate_swing_playbook(options=options, candidates=frame)

    assert result.success is True
    assert Path(result.markdown_path).exists()
    assert Path(result.html_path).exists()
    assert Path(result.candidates_csv).exists()
    assert Path(result.portfolio_csv).exists()
    candidates_header = Path(result.candidates_csv).read_text(encoding="utf-8").splitlines()[0]
    assert "action_label" in candidates_header
    markdown = Path(result.markdown_path).read_text(encoding="utf-8")
    assert "# Swing Trading Playbook" in markdown
    assert "## Daily Action Sheet" in markdown
    assert "## Tactical Swing Candidates" in markdown
    assert "## Position Swing Candidates" in markdown
    assert "## Portfolio Actions" in markdown
    assert "EOD_READY" in markdown
