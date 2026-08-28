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
    assert "**JUSTDIAL**: +16.74%" in markdown
    assert "**HARDWYN**: -19.32%" in markdown
    assert "NSE EOD close data" in markdown
    html = build_html(data)
    assert "EOD Close" in html
    assert "No hourly intraday data available" in html


def test_eod_html_renders_commentary_markdown_and_share_safe_report_links(monkeypatch):
    monkeypatch.setenv("EOD_REPORT_LLM", "0")

    data = enrich_data(
        {
            "report_date": "2026-08-21",
            "source_mode": "eod_only",
            "index_daily": [
                {"symbol": "NIFTY", "day_close": 24252.00, "day_pct": 0.08},
                {"symbol": "BANKNIFTY", "day_close": 57761.95, "day_pct": 0.46},
            ],
            "hourly": [],
            "symbol_day": [],
            "hourly_leaders": [],
            "intraday_path": [],
        }
    )
    data["llm_commentary"] = {
        "text": "**Day Character**\n\nNIFTY held flat.\n\n**Next Session Watch**\n\nWatch breadth.",
    }

    html = build_html(data)

    assert "<strong>Day Character</strong>" in html
    assert "<strong>Next Session Watch</strong>" in html
    assert "**Day Character**" not in html
    assert "file://" not in html
    assert "href='/stocks/reports/sector-rotation-2026-08-21'" in html
    assert "href='/stocks/reports/stage2-tracker-2026-08-21'" in html
    assert "href='/stocks/reports/top-picks-2026-08-21'" in html
    assert "href='/stocks/reports/swing-playbook-2026-08-21'" in html
    assert "portfolio_strategy_lab.html" not in html


def test_eod_html_uses_shrink_safe_layout_for_embedded_site_pages(monkeypatch):
    monkeypatch.setenv("EOD_REPORT_LLM", "0")

    data = enrich_data(
        {
            "report_date": "2026-08-24",
            "source_mode": "eod_only",
            "index_daily": [
                {"symbol": "NIFTY", "day_close": 24178.05, "day_pct": -0.44},
                {"symbol": "BANKNIFTY", "day_close": 57383.75, "day_pct": -0.77},
            ],
            "hourly": [],
            "symbol_day": [
                {"symbol": "AKUMS", "sector": "Pharmaceuticals & Biotechnology", "day_pct": 4.33, "volume": 440000},
                {"symbol": "AEGISLOG", "sector": "Gas", "day_pct": -5.82, "volume": 860000},
            ],
            "hourly_leaders": [],
            "intraday_path": [],
        }
    )

    html = build_html(data)

    assert ".grid>*{min-width:0}" in html
    assert ".two{grid-template-columns:minmax(0,1.18fr) minmax(0,.82fr)}" in html
    assert ".halves{grid-template-columns:repeat(2,minmax(0,1fr))}" in html
    assert ".card{min-width:0;" in html
    assert ".table-scroll{width:100%;max-width:100%;overflow-x:auto;" in html
