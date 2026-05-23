import pandas as pd
from pathlib import Path

import terminal.visual_scan.data_loader as data_loader
from terminal.visual_scan.data_loader import VisualScanInput, load_visual_scan_input, resample_weekly


def test_resample_weekly_produces_ohlcv_weeks():
    dates = pd.date_range("2026-01-01", periods=20, freq="B")
    daily = pd.DataFrame(
        {
            "trade_date": dates,
            "open": range(20),
            "high": [value + 1 for value in range(20)],
            "low": [value - 1 for value in range(20)],
            "close": range(20),
            "volume": [1000] * 20,
        }
    )

    weekly = resample_weekly(daily)

    assert not weekly.empty
    assert {"trade_date", "open", "high", "low", "close", "volume"}.issubset(weekly.columns)
    assert weekly["volume"].iloc[0] >= 1000


def test_load_visual_scan_input_uses_injected_frames_without_database():
    daily = pd.DataFrame(
        {
            "trade_date": pd.date_range("2026-01-01", periods=60, freq="B"),
            "open": [100] * 60,
            "high": [102] * 60,
            "low": [98] * 60,
            "close": [100 + i * 0.2 for i in range(60)],
            "volume": [100_000] * 60,
        }
    )

    data = load_visual_scan_input("DMART", input_data=VisualScanInput(daily=daily))

    assert data.symbol == "DMART"
    assert len(data.daily) == 60
    assert not data.weekly.empty
    assert data.source_trail["daily"]["status"] == "injected"


def test_load_visual_scan_input_uses_recommendation_loader_for_market_history(monkeypatch):
    daily = pd.DataFrame(
        {
            "symbol": ["DMART"] * 60 + ["OTHER"] * 60,
            "trade_date": list(pd.date_range("2026-01-01", periods=60, freq="B")) * 2,
            "open": [100] * 120,
            "high": [102] * 120,
            "low": [98] * 120,
            "close": [100 + i * 0.2 for i in range(60)] + [50] * 60,
            "volume": [100_000] * 120,
        }
    )

    class FakeRecommendationData:
        equity_history = daily

    calls = []

    def fake_loader(options):
        calls.append(options)
        return FakeRecommendationData()

    monkeypatch.setattr(data_loader, "load_recommendation_input_data", fake_loader)

    data = load_visual_scan_input("DMART")

    assert calls
    assert data.symbol == "DMART"
    assert len(data.daily) == 60
    assert data.daily["close"].max() > 100
    assert data.source_trail["daily"]["status"] == "loaded"


def test_resample_weekly_handles_close_only_history_without_crashing():
    daily = pd.DataFrame(
        {
            "trade_date": pd.date_range("2026-01-01", periods=20, freq="B"),
            "close": range(20),
        }
    )

    weekly = resample_weekly(daily)

    assert not weekly.empty
    assert {"trade_date", "open", "high", "low", "close", "volume"}.issubset(weekly.columns)
    assert weekly["close"].iloc[-1] >= weekly["close"].iloc[0]


def test_load_visual_scan_input_marks_unusable_injected_daily_as_degraded():
    bad_daily = pd.DataFrame(
        {
            "trade_date": pd.date_range("2026-01-01", periods=5, freq="B"),
            "note": ["missing close"] * 5,
        }
    )

    data = load_visual_scan_input("DMART", input_data=VisualScanInput(daily=bad_daily))

    assert data.daily.empty
    assert "daily_history" in data.missing_evidence
    assert data.source_trail["daily"]["status"] == "degraded"


def test_load_visual_scan_input_uses_close_only_market_history(monkeypatch):
    daily = pd.DataFrame(
        {
            "symbol": ["DMART"] * 60,
            "trade_date": pd.date_range("2026-01-01", periods=60, freq="B"),
            "close": [100 + i * 0.2 for i in range(60)],
        }
    )

    class FakeRecommendationData:
        equity_history = daily

    monkeypatch.setattr(data_loader, "load_recommendation_input_data", lambda options: FakeRecommendationData())

    data = load_visual_scan_input("DMART")

    assert len(data.daily) == 60
    assert not data.weekly.empty
    assert data.source_trail["daily"]["status"] == "loaded"


def test_load_visual_scan_input_uses_index_history_for_nifty_bank(monkeypatch):
    index_history = pd.DataFrame(
        {
            "index_symbol": ["NIFTY BANK"] * 80,
            "trade_date": pd.date_range("2026-01-01", periods=80, freq="B"),
            "open": [50000 + i for i in range(80)],
            "high": [50100 + i for i in range(80)],
            "low": [49900 + i for i in range(80)],
            "close": [50000 + i for i in range(80)],
            "volume": [0] * 80,
        }
    )

    class FakeRecommendationData:
        pass

    fake_data = FakeRecommendationData()
    fake_data.equity_history = pd.DataFrame()
    fake_data.index_history = index_history

    monkeypatch.setattr(data_loader, "load_recommendation_input_data", lambda options: fake_data)

    data = load_visual_scan_input("NIFTY BANK")

    assert len(data.daily) == 80
    assert not data.weekly.empty
    assert data.source_trail["daily"]["status"] == "loaded"
    assert "daily_history" not in data.missing_evidence


from terminal.visual_scan.command import run_visual_scan


def test_run_visual_scan_with_injected_data_returns_report_paths(tmp_path):
    daily = pd.DataFrame(
        {
            "trade_date": pd.date_range("2026-01-01", periods=260, freq="B"),
            "open": [100 + i * 0.2 for i in range(260)],
            "high": [102 + i * 0.2 for i in range(260)],
            "low": [98 + i * 0.2 for i in range(260)],
            "close": [100 + i * 0.2 for i in range(260)],
            "volume": [100_000] * 260,
        }
    )

    result = run_visual_scan(
        "DMART",
        input_data=VisualScanInput(daily=daily),
        output_dir=tmp_path,
        capture_tradingview=False,
    )

    assert result["success"] is True
    assert result["symbol"] == "DMART"
    assert result["html_path"].endswith(".html")
    assert Path(result["html_path"]).exists()
    assert Path(result["json_path"]).exists()
    assert Path(result["html_path"]).parent == tmp_path.resolve()
    assert Path(result["json_path"]).parent == tmp_path.resolve()
    assert "Visual Scan" in result["summary"]
    assert result["pack"]["tradingview"]["status"] == "not_attempted"
    assert result["pack"]["chart_paths"]["daily"].endswith(".html")


def test_run_visual_scan_derives_mtf_from_loaded_daily_history(tmp_path):
    daily = pd.DataFrame(
        {
            "trade_date": pd.date_range("2024-01-01", periods=520, freq="B"),
            "open": [100 + i * 0.4 for i in range(520)],
            "high": [101 + i * 0.4 for i in range(520)],
            "low": [99 + i * 0.4 for i in range(520)],
            "close": [100 + i * 0.4 for i in range(520)],
            "volume": [100_000] * 520,
        }
    )

    result = run_visual_scan(
        "DMART",
        input_data=VisualScanInput(daily=daily),
        output_dir=tmp_path,
        capture_tradingview=False,
    )

    mtf = next(pattern for pattern in result["pack"]["patterns"] if pattern["pattern"] == "MTF Alignment")

    assert mtf["status"] != "insufficient_data"
    assert mtf["metrics"]["timeframes"] == ["monthly", "weekly", "daily"]
    assert result["pack"]["source_trail"]["mtf"]["status"] == "derived"


def test_run_visual_scan_with_missing_data_keeps_insufficient_evidence_explicit(tmp_path):
    result = run_visual_scan(
        "DMART",
        input_data=VisualScanInput(daily=pd.DataFrame()),
        output_dir=tmp_path,
        capture_tradingview=False,
    )

    assert result["success"] is True
    assert result["pack"]["verdict"]["stance"] == "Insufficient evidence"
    assert result["pack"]["missing_evidence"]
    assert result["pack"]["verdict"]["targets"] == []
    assert "not available" in result["pack"]["verdict"]["trigger"].lower()
    assert result["pack"]["annotations"] == []


def test_run_visual_scan_does_not_annotate_absent_pattern_targets(tmp_path):
    daily = pd.DataFrame(
        {
            "trade_date": pd.date_range("2026-01-01", periods=260, freq="B"),
            "open": [100] * 260,
            "high": [102] * 260,
            "low": [98] * 260,
            "close": [100] * 260,
            "volume": [100_000] * 260,
        }
    )

    result = run_visual_scan(
        "DMART",
        input_data=VisualScanInput(daily=daily),
        output_dir=tmp_path,
        capture_tradingview=False,
    )

    assert result["pack"]["verdict"]["targets"] == []
    assert all(annotation["kind"] != "target" for annotation in result["pack"]["annotations"])
    absent_patterns = {
        pattern["pattern"]
        for pattern in result["pack"]["patterns"]
        if pattern["status"] == "absent"
    }
    assert all(
        not any(pattern_name in annotation["label"] for pattern_name in absent_patterns)
        for annotation in result["pack"]["annotations"]
    )


def test_slash_command_list_includes_visual_scan():
    import nse_agent

    labels = [label for label, _description in nse_agent._SLASH_COMMANDS]

    assert "/visual-scan" in labels
