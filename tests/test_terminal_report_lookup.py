from pathlib import Path

from terminal import tools


def test_find_latest_report_includes_strategy_council_markdown(tmp_path, monkeypatch):
    root = tmp_path
    reports = root / "reports"
    strategy_dir = reports / "strategy_council"
    strategy_dir.mkdir(parents=True)
    report = strategy_dir / "strategy_council_KIRLOSENG_20260515_142320.md"
    report.write_text("# Strategy Council", encoding="utf-8")

    monkeypatch.setattr(tools, "ROOT", root)
    monkeypatch.setattr(tools, "REPORTS", reports)

    result = tools.find_latest_report("strategy_council")

    assert result["count"] == 1
    assert result["files"][0]["path"] == "reports/strategy_council/strategy_council_KIRLOSENG_20260515_142320.md"
