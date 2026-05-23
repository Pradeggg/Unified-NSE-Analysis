from pathlib import Path
import json

import pandas as pd

from terminal.visual_scan.chart_renderer import render_visual_scan_charts
from terminal.visual_scan.models import ChartAnnotation


def test_render_visual_scan_charts_writes_daily_and_weekly_html_assets(tmp_path):
    daily = pd.DataFrame(
        {
            "trade_date": pd.date_range("2026-01-01", periods=80, freq="B"),
            "open": [100] * 80,
            "high": [103] * 80,
            "low": [97] * 80,
            "close": [100 + i * 0.5 for i in range(80)],
            "volume": [100_000] * 80,
        }
    )
    weekly = daily.iloc[::5].copy()
    paths = render_visual_scan_charts(
        symbol="DMART",
        run_id="run1",
        daily=daily,
        weekly=weekly,
        annotations=[ChartAnnotation(kind="pivot", label="Pivot", price=130.0)],
        output_dir=tmp_path,
    )

    assert Path(paths["daily"]).exists()
    assert Path(paths["weekly"]).exists()
    assert Path(paths["daily"]).suffix == ".html"
    assert "DMART" in Path(paths["daily"]).read_text()


def test_render_visual_scan_charts_sanitizes_asset_filenames(tmp_path):
    daily = pd.DataFrame(
        {
            "trade_date": pd.date_range("2026-01-01", periods=5, freq="B"),
            "close": [100, 101, 102, 101, 103],
        }
    )

    paths = render_visual_scan_charts(
        symbol="../DMART<script>",
        run_id="run/1",
        daily=daily,
        weekly=daily,
        annotations=[ChartAnnotation(kind="pivot", label="<Pivot>", price=102.0, color="#0f766e")],
        output_dir=tmp_path,
    )

    for path in paths.values():
        asset_path = Path(path)
        assert asset_path.exists()
        assert asset_path.parent == tmp_path
        assert ".." not in asset_path.name
        assert "/" not in asset_path.name
    assert "<Pivot>" not in Path(paths["daily"]).read_text()


def test_render_visual_scan_charts_handles_empty_frames(tmp_path):
    paths = render_visual_scan_charts(
        symbol="DMART",
        run_id="run1",
        daily=pd.DataFrame(),
        weekly=pd.DataFrame(),
        annotations=[],
        output_dir=tmp_path,
    )

    assert "No usable OHLC data available" in Path(paths["daily"]).read_text()


from terminal.visual_scan.tradingview import build_tradingview_url, capture_tradingview_screenshot


def test_build_tradingview_url_uses_nse_prefix():
    assert build_tradingview_url("DMART") == "https://www.tradingview.com/chart/?symbol=NSE%3ADMART"


def test_capture_tradingview_screenshot_fail_open_when_playwright_unavailable(tmp_path, monkeypatch):
    import builtins

    real_import = builtins.__import__
    monkeypatch.setattr(
        builtins,
        "__import__",
        lambda name, *args, **kwargs: (_ for _ in ()).throw(ModuleNotFoundError("playwright"))
        if name == "playwright.sync_api"
        else real_import(name, *args, **kwargs),
    )

    result = capture_tradingview_screenshot("DMART", output_dir=tmp_path, run_id="run1", timeout_ms=100)

    assert result["status"] == "unavailable"
    assert "TradingView screenshot unavailable" in result["message"]
    assert result["url"].endswith("NSE%3ADMART")


def test_capture_tradingview_screenshot_uses_safe_path_when_capture_succeeds(tmp_path, monkeypatch):
    import sys
    import types

    class FakePage:
        def goto(self, *_args, **_kwargs):
            return None

        def screenshot(self, *, path, full_page):
            Path(path).write_bytes(b"png")

    class FakeBrowser:
        def new_page(self, *, viewport):
            return FakePage()

        def close(self):
            return None

    class FakeChromium:
        def launch(self, *, headless):
            return FakeBrowser()

    class FakePlaywright:
        chromium = FakeChromium()

    class FakeSyncPlaywright:
        def __enter__(self):
            return FakePlaywright()

        def __exit__(self, *_args):
            return None

    fake_package = types.ModuleType("playwright")
    fake_package.__path__ = []
    fake_module = types.ModuleType("playwright.sync_api")
    fake_module.sync_playwright = lambda: FakeSyncPlaywright()
    monkeypatch.setitem(sys.modules, "playwright", fake_package)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", fake_module)

    result = capture_tradingview_screenshot("../DMART<script>", output_dir=tmp_path, run_id="run/1", timeout_ms=100)

    assert result["status"] == "captured"
    shot_path = Path(result["path"])
    assert shot_path.exists()
    assert shot_path.parent == tmp_path
    assert ".." not in shot_path.name
    assert "/" not in shot_path.name


from terminal.visual_scan.models import PatternEvidence, PatternStatus, VisualScanPack, VisualScanVerdict, Zones
from terminal.visual_scan.report import render_visual_scan_markdown, save_visual_scan_outputs


def test_render_visual_scan_markdown_contains_balanced_sections():
    pack = VisualScanPack(
        run_id="run1",
        symbol="DMART",
        as_of="2026-05-22",
        verdict=VisualScanVerdict(
            stance="Watchlist / base building",
            score=68,
            confidence="medium",
            trigger="Daily close above pivot with volume confirmation.",
            invalidation="Close below support.",
            targets=["Target 1 near 4550."],
            summary="Constructive base, breakout not confirmed.",
        ),
        patterns=[
            PatternEvidence("VCP", PatternStatus.CANDIDATE, 0.72, evidence=["Range contracted."], zones=Zones(pivot=4210)),
        ],
        chart_paths={"daily": "assets/daily.html", "weekly": "assets/weekly.html"},
        tradingview={"status": "unavailable", "message": "TradingView screenshot unavailable; report generated from local OHLCV evidence."},
        source_trail={"daily": {"status": "loaded", "rows": 240}},
    )

    markdown = render_visual_scan_markdown(pack)

    assert "# DMART Visual Scan" in markdown
    assert "## Verdict" in markdown
    assert "## Annotated Charts" in markdown
    assert "## Decision Panel" in markdown
    assert "## Pattern Evidence" in markdown
    assert "## TradingView Corroboration" in markdown
    assert "## Source & Audit Trail" in markdown
    assert "## Missing Evidence" in markdown
    assert "Watchlist / base building" in markdown
    assert "TradingView screenshot unavailable" in markdown


def test_save_visual_scan_outputs_writes_html_and_json(tmp_path):
    pack = VisualScanPack(
        run_id="run/1",
        symbol="../DMART<script>",
        as_of="2026-05-22",
        verdict=VisualScanVerdict("Manual review", 10, "low", "Collect data.", "No action.", summary="Missing data."),
    )

    result = save_visual_scan_outputs(pack, output_dir=tmp_path)

    assert result["success"] is True
    assert result["html_path"].endswith(".html")
    assert result["json_path"].endswith(".json")
    html_path = Path(result["html_path"])
    json_path = Path(result["json_path"])
    assert html_path.exists()
    assert json_path.exists()
    assert html_path.parent == tmp_path.resolve()
    assert json_path.parent == tmp_path.resolve()
    assert ".." not in html_path.name
    assert "/" not in html_path.name
    html_text = html_path.read_text()
    assert 'data-agent-theme="sector-rotation-standard"' in html_text
    payload = json.loads(json_path.read_text())
    assert payload["run_id"] == "run/1"
    assert payload["symbol"] == "../DMART<script>"
    assert payload["verdict"]["stance"] == "Manual review"
