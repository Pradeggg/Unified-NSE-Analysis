from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(".agents/skills/tradingview-chart")


def _module():
    path = ROOT / "scripts/open_tradingview_chart.py"
    spec = importlib.util.spec_from_file_location("open_tradingview_chart", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_tradingview_symbol_maps_nse_equities_and_indices():
    chart = _module()
    assert chart.tradingview_symbol("elgiequip") == "NSE:ELGIEQUIP"
    assert chart.tradingview_symbol("BANKNIFTY") == "NSE:BANKNIFTY"
    assert chart.tradingview_symbol("BSE:SENSEX") == "BSE:SENSEX"


def test_html_embeds_agent_adda_studies(tmp_path):
    chart = _module()
    result = chart.write_chart("ELGIEQUIP", interval="D", output_path=tmp_path / "elgi.html", include_snapshot=False)
    html = Path(result["path"]).read_text(encoding="utf-8")

    assert result["success"] is True
    assert result["tradingview_symbol"] == "NSE:ELGIEQUIP"
    assert "lightweight-charts" in html
    assert "embed-widget-advanced-chart.js" not in html
    assert "SMA 20" in html
    assert "RSI 14" in html
    assert "MACD" in html
    assert "Supertrend 10" in html
    assert "data-chart-type=\"candles\"" in html
    assert "data-indicator=\"sma20\"" in html
    assert "data-tool=\"hline\"" in html
    assert "data-range=\"1M\"" in html
    assert "only available on TradingView" in html or "blocked on TradingView" in html


def test_payload_includes_indicator_series():
    chart = _module()
    closes = [100 + i * 0.4 + (i % 5) for i in range(80)]
    bars = [
        {"time": f"2026-01-{(i % 28) + 1:02d}", "open": c - 0.2, "high": c + 0.5, "low": c - 0.6, "close": c, "volume": 1000 + i}
        for i, c in enumerate(closes)
    ]
    # Unique dates so the chart library can plot.
    bars = [
        {**row, "time": f"2026-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}"}
        for i, row in enumerate(bars)
    ]
    payload = chart.build_payload(bars)
    assert len(payload["candles"]) == 80
    assert payload["sma20"]
    assert payload["rsi"]
    assert payload["macd"]
    assert payload["supertrend"]


def test_rejects_unknown_interval():
    chart = _module()
    try:
        chart.write_chart("ELGIEQUIP", interval="Q", include_snapshot=False)
    except ValueError as exc:
        assert "interval" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_canvas_tsx_uses_linechart_not_svg_candles(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "build_chart_canvas",
        ROOT / "scripts/build_chart_canvas.py",
    )
    assert spec and spec.loader
    canvas = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(canvas)
    packs = [
        {
            "symbol": "HAL",
            "tv": "NSE:HAL",
            "url": "https://www.tradingview.com/chart/?symbol=NSE:HAL&interval=D",
            "price": 5100.0,
            "rsi": 55.0,
            "supertrend": "BUY",
            "sma20": 5000.0,
            "sma50": 4900.0,
            "sma200": 4500.0,
            "as_of": "2026-08-14",
            "categories": ["08-13", "08-14"],
            "close": [5000.0, 5100.0],
            "sma20_line": [4980.0, 4990.0],
            "sma50_line": [4900.0, 4910.0],
            "sma200_line": [4500.0, 4510.0],
            "bar_count": 2,
            "error": None,
            "url_5m": "https://www.tradingview.com/chart/?symbol=NSE:HAL&interval=5",
            "intra_interval": "5m",
            "intra_t": ["09:15", "09:20", "09:25"],
            "intra_c": [5080.0, 5095.0, 5100.0],
            "intra_h": [5085.0, 5105.0, 5110.0],
            "intra_l": [5070.0, 5088.0, 5090.0],
            "intra_high": 5110.0,
            "intra_low": 5070.0,
            "intra_last": 5100.0,
            "from_open": 0.39,
        }
    ]
    tsx = canvas.render_canvas_tsx(packs)
    out = tmp_path / "hal-chart.canvas.tsx"
    out.write_text(tsx, encoding="utf-8")
    assert 'from "cursor/canvas"' in tsx
    assert "LineChart" in tsx
    assert "SMA 20" in tsx
    assert "IntradayChart" in tsx
    assert "intra_interval" in tsx
    assert "stock.intra_t.length" in tsx
    assert "<svg" not in tsx
    assert "key=" not in tsx
    assert canvas.cursor_canvas_dir().name == "canvases"
    assert "Unified-NSE-Analysis" in str(canvas.cursor_canvas_dir())


def test_yahoo_ticker_maps_indices_and_equities():
    chart = _module()
    assert chart.yahoo_ticker("HAL") == "HAL.NS"
    assert chart.yahoo_ticker("NIFTY") == "^NSEI"
    assert chart.yahoo_ticker("BANKNIFTY") == "^NSEBANK"
    assert chart.yahoo_ticker("SENSEX") == "^BSESN"


def test_skill_wrappers_share_the_canonical_description():
    canonical = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    description = canonical.split("description: ", 1)[1].split("\n---", 1)[0].strip()
    for path in (
        Path(".claude/skills/tradingview-chart/SKILL.md"),
        Path(".cursor/skills/tradingview-chart/SKILL.md"),
    ):
        wrapper = path.read_text(encoding="utf-8")
        assert description in wrapper
        assert "../../../.agents/skills/tradingview-chart/SKILL.md" in wrapper
