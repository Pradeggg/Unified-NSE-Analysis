import datetime as _real_dt
from dataclasses import replace
from pathlib import Path

import terminal.value_checklist as value_checklist
from terminal.value_checklist import (
    ValueChecklistEvidence,
    build_checklist_result,
    build_value_checklist_markdown,
    render_value_checklist_html,
    write_value_checklist_report,
)


def _result(symbol: str):
    evidence = ValueChecklistEvidence(
        symbol=symbol,
        company_name=f"{symbol} Ltd",
        sector="IT",
        fundamentals={
            "roe": 24.0,
            "roce": 31.0,
            "opm_pct": 26.0,
            "free_cash_flow_positive": True,
            "debt_to_equity": 0.05,
            "enhanced_fund_score": 82.0,
        },
        valuation={"pe": 24.0, "pb": 5.5, "earnings_yield_pct": 4.2, "valuation_signal": "reasonable"},
        governance={"promoter_pledge_pct": 0.0, "forensic_risk": "low", "insider_signal": "neutral"},
        technical={
            "stage": "STAGE_2",
            "relative_strength": 1.18,
            "rsi": 61.0,
            "technical_score": 78.0,
            "trend_signal": "BULLISH",
            "trading_signal": "BUY",
        },
        latest_results={"status": "ok"},
        source_trail=({"name": "scores.stage_snapshots", "status": "ok"},),
        missing_evidence=(),
        freshness={"stage_snapshot": "2026-06-26"},
    )
    return build_checklist_result(evidence)


def test_value_checklist_markdown_contains_comparison_sections():
    markdown = build_value_checklist_markdown([_result("TCS"), _result("INFY")])

    assert "# NSE Investment Checklist Comparison" in markdown
    assert "## Ranked Comparison" in markdown
    assert "| Rank | Symbol | Verdict | Score | Evidence | Key Strength | Key Risk |" in markdown
    assert "## TCS" in markdown
    assert "## INFY" in markdown
    assert "Mirror Test" in markdown
    assert "Research only. Not investment advice." in markdown
    assert "scores.stage_snapshots" in markdown


def test_comparison_readout_describes_actual_ranking_comparator():
    markdown = build_value_checklist_markdown([_result("TCS"), _result("INFY")])
    readout = markdown.split("## Comparison Readout", 1)[1].split("\n## ", 1)[0]

    assert "- Ranking sorts by verdict, total score, evidence quality, and symbol." in readout
    assert "governance safety" not in readout
    assert "valuation reasonableness" not in readout
    assert "technical confirmation" not in readout


def test_value_checklist_html_renders_tables_without_raw_markdown_separator():
    html = render_value_checklist_html(build_value_checklist_markdown([_result("TCS"), _result("INFY")]))

    assert "<table" in html
    assert "NSE Investment Checklist Comparison" in html
    assert "| ---" not in html


def test_write_value_checklist_report_uses_unique_paths_within_same_second(tmp_path, monkeypatch):
    class SameSecondDatetime(_real_dt.datetime):
        calls = 0

        @classmethod
        def now(cls, tz=None):
            cls.calls += 1
            value = cls(2026, 6, 27, 10, 0, 0, cls.calls)
            return value if tz is None else value.replace(tzinfo=tz)

    monkeypatch.setattr(value_checklist._dt, "datetime", SameSecondDatetime)

    first = write_value_checklist_report([_result("TCS")], tmp_path)
    second = write_value_checklist_report([_result("TCS")], tmp_path)

    assert first.markdown_path != second.markdown_path
    assert first.html_path != second.html_path
    assert first.summary_csv_path != second.summary_csv_path
    for path in (
        first.markdown_path,
        first.html_path,
        first.summary_csv_path,
        second.markdown_path,
        second.html_path,
        second.summary_csv_path,
    ):
        assert Path(path).exists()


def test_ranked_table_sanitizes_pipe_characters_inside_cells():
    result = replace(_result("PIPE"), top_strengths=("A | B",), top_risks=("Risk is contained",))

    markdown = build_value_checklist_markdown([result])
    html = render_value_checklist_html(markdown)
    lines = markdown.splitlines()
    header_index = lines.index("| Rank | Symbol | Verdict | Score | Evidence | Key Strength | Key Risk |")
    ranked_table = lines[header_index : header_index + 3]
    expected_pipes = ranked_table[0].count("|")

    assert "A / B" in markdown
    assert "A / B" in html
    assert all(line.count("|") == expected_pipes for line in ranked_table)
    assert "A \\| B" not in markdown
    assert "A \\</td><td>B" not in html


def test_write_value_checklist_report_writes_timestamped_and_latest_outputs(tmp_path):
    report = write_value_checklist_report([_result("TCS"), _result("INFY")], project_root=tmp_path)

    assert Path(report.markdown_path).exists()
    assert Path(report.html_path).exists()
    assert Path(report.summary_csv_path).exists()
    assert Path(report.latest_markdown_path).exists()
    assert Path(report.latest_html_path).exists()
    assert Path(report.latest_summary_csv_path).exists()
    assert Path(report.latest_summary_csv_path).read_text(encoding="utf-8").startswith("rank,symbol,company_name")


def test_write_value_checklist_report_accepts_positional_project_root(tmp_path):
    report = write_value_checklist_report([_result("TCS")], tmp_path)

    latest_markdown = tmp_path / "reports" / "latest" / "investment_checklist.md"
    latest_html = tmp_path / "reports" / "latest" / "investment_checklist.html"
    latest_csv = tmp_path / "reports" / "latest" / "investment_checklist_summary.csv"

    assert Path(report.latest_markdown_path) == latest_markdown
    assert Path(report.latest_html_path) == latest_html
    assert Path(report.latest_summary_csv_path) == latest_csv
    assert latest_markdown.exists()
    assert latest_html.exists()
    assert latest_csv.exists()
