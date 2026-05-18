from pathlib import Path


def test_list_generated_reports_sorts_newest_first(tmp_path):
    from terminal.report_context import list_generated_reports

    reports = tmp_path / "reports"
    generated = reports / "generated"
    strategy = reports / "strategy_council"
    generated.mkdir(parents=True)
    strategy.mkdir(parents=True)
    old = generated / "DMART_research_20260514_101010.html"
    new = strategy / "strategy_council_KIRLOSENG_20260515_142320.md"
    old.write_text("<h1>Old</h1>", encoding="utf-8")
    new.write_text("# New", encoding="utf-8")

    result = list_generated_reports(project_root=tmp_path)

    assert result["count"] == 2
    assert result["reports"][0]["path"].endswith("strategy_council_KIRLOSENG_20260515_142320.md")
    assert result["reports"][0]["symbol"] == "KIRLOSENG"
    assert result["reports"][0]["report_type"] == "strategy_council"


def test_read_and_summarize_report_preserves_symbol_and_heading(tmp_path):
    from terminal.report_context import read_report, summarize_report

    report = tmp_path / "reports" / "strategy_council" / "strategy_council_DMART_20260515_142320.md"
    report.parent.mkdir(parents=True)
    report.write_text(
        "# Strategy Council — DMART\n\nRecommendation: WAIT\n\nEvidence Pack\n- Technical bars: 831\n",
        encoding="utf-8",
    )

    read = read_report(str(report), project_root=tmp_path)
    summary = summarize_report(str(report), project_root=tmp_path)

    assert read["status"] == "ok"
    assert read["symbol"] == "DMART"
    assert "Recommendation: WAIT" in read["content"]
    assert summary["status"] == "ok"
    assert summary["symbol"] == "DMART"
    assert "Strategy Council" in summary["summary"]
    assert "Recommendation: WAIT" in summary["summary"]


def test_summarize_html_report_uses_visible_text(tmp_path):
    from terminal.report_context import summarize_report

    report = tmp_path / "reports" / "generated" / "SCHAEFFLER_research_20260517_220217.html"
    report.parent.mkdir(parents=True)
    report.write_text(
        """
        <html><head><style>.x{}</style></head><body>
          <h1>SCHAEFFLER — Comprehensive Research Report</h1>
          <p>Recommendation: HOLD</p>
          <p>Evidence Pack: Screener + EOD snapshot</p>
          <script>Recommendation: BUY</script>
        </body></html>
        """,
        encoding="utf-8",
    )

    summary = summarize_report(str(report), project_root=tmp_path)

    assert summary["status"] == "ok"
    assert summary["symbol"] == "SCHAEFFLER"
    assert summary["recommendation"] == "HOLD"
    assert "Screener + EOD snapshot" in summary["summary"]
    assert "BUY" not in summary["summary"]


def test_get_last_report_returns_clarification_when_missing():
    from terminal.report_context import get_last_report

    result = get_last_report(None)

    assert result["status"] == "needs_clarification"
    assert "No report has been generated" in result["message"]


def test_compare_reports_highlights_recommendation_changes(tmp_path):
    from terminal.report_context import compare_reports

    first = tmp_path / "reports" / "strategy_council" / "strategy_council_DMART_20260514_101010.md"
    second = tmp_path / "reports" / "strategy_council" / "strategy_council_DMART_20260515_101010.md"
    first.parent.mkdir(parents=True)
    first.write_text("# Strategy Council\nRecommendation: WAIT\n", encoding="utf-8")
    second.write_text("# Strategy Council\nRecommendation: NO_TRADE\n", encoding="utf-8")

    result = compare_reports(str(first), str(second), project_root=tmp_path)

    assert result["status"] == "ok"
    assert result["changed"] is True
    assert result["first_recommendation"] == "WAIT"
    assert result["second_recommendation"] == "NO_TRADE"
