from scripts.build_eod_market_report import build_deterministic_commentary, build_html, build_markdown, enrich_data


def test_build_markdown_handles_empty_hourly_intraday_data():
    markdown = build_markdown(
        {
            "report_date": "2026-07-14",
            "llm_commentary": {"text": "No hourly intraday data was available."},
            "index_daily": [
                {"symbol": "NIFTY", "day_close": 24052.05, "day_pct": -0.66},
                {"symbol": "BANKNIFTY", "day_close": 57462.30, "day_pct": -1.15},
            ],
            "hourly": [],
            "events": [],
            "top_gainers": [],
            "top_losers": [],
        }
    )

    assert "# End Of Day Market Report - 2026-07-14" in markdown
    assert "No hourly intraday data was available." in markdown
    assert "Best breadth hour: n/a" in markdown


def test_eod_only_data_still_generates_market_commentary_and_movers(monkeypatch):
    monkeypatch.setenv("EOD_REPORT_LLM", "0")

    data = enrich_data(
        {
            "report_date": "2026-07-14",
            "source_mode": "eod_only",
            "index_daily": [
                {"symbol": "NIFTY", "day_close": 24052.05, "day_pct": -0.66},
                {"symbol": "BANKNIFTY", "day_close": 57462.30, "day_pct": -1.15},
            ],
            "hourly": [],
            "symbol_day": [
                {"symbol": "JUSTDIAL", "sector": "Services", "day_pct": 16.74, "volume": 1000},
                {"symbol": "HARDWYN", "sector": "Consumer Durables", "day_pct": -19.32, "volume": 2000},
            ],
            "hourly_leaders": [],
            "intraday_path": [],
        }
    )

    commentary = build_deterministic_commentary(data)
    markdown = build_markdown(data)

    assert "EOD-only session report" in commentary
    assert "NIFTY closed -0.66%" in commentary
    assert "JUSTDIAL: +16.74%" in markdown
    assert "HARDWYN: -19.32%" in markdown
    assert "NSE EOD close data" in markdown
    html = build_html(data)
    assert "EOD Close" in html
    assert "No hourly intraday data available" in html
