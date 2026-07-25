from pathlib import Path

from terminal.backtest import handle_backtest_command
from terminal.intraday_editorial_report import (
    build_editorial_evidence,
    build_editorial_narrative,
    build_editorial_report,
    build_detailed_research_paper,
    write_detailed_research_paper,
    write_editorial_report,
)


SAMPLE_REPORT = """# Agent Adda Intraday F&O Indicator Study

- Generated: 2026-06-21 13:23:26 IST
- Universe: fno
- Timeframes: 15m

## Data Readiness

- Bars loaded: 14748
- Symbols with bars: 85
- Trade candidates tested: 2946
- Daily F&O context rows: 3145

## Indicator Leaderboard

| setup | timeframe | direction | trades | win_rate | expectancy_r | profit_factor |
| --- | --- | --- | --- | --- | --- | --- |
| ORB + VWAP | 15m | LONG | 219 | 54.8% | 0.14 | 1.54 |

## Walk-Forward Validation

| setup | timeframe | direction | walk_forward_status | folds_tested | promoted_folds | validation_trades | train_expectancy_r | train_profit_factor | validation_expectancy_r | validation_win_rate | validation_profit_factor | validation_positive_fold_rate | worst_validation_r |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ORB + VWAP | 15m | LONG | confirmed | 4 | 4 | 175 | 0.15 | 1.56 | 0.17 | 55.55 | 2.61 | 75.00 | -0.16 |

## Confirmed Setup Symbol Drilldown

| symbol | symbol_edge_status | setup | timeframe | direction | trades | win_rate | expectancy_r | profit_factor | avg_mfe_r | avg_mae_r | best_volatility_regime | best_pcr_regime |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| NIFTYNXT50 | core_carrier | ORB + VWAP | 15m | LONG | 21 | 71.4% | 0.30 | 2.41 | 0.98 | 0.61 | low | - |
| NIFTY | edge_diluter | ORB + VWAP | 15m | LONG | 22 | 36.4% | -0.25 | 0.54 | 0.77 | 0.87 | low | - |

## Confirmed Setup Time-of-Day Filter

| setup | timeframe | direction | time_bucket | trades | win_rate | expectancy_r | profit_factor |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ORB + VWAP | 15m | LONG | opening_drive | 219 | 54.8% | 0.14 | 1.54 |

## Volatility Regime Read-Through

| setup | timeframe | direction | volatility_regime | trades | win_rate | expectancy_r | profit_factor |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ORB + VWAP | 15m | LONG | normal | 75 | 57.3% | 0.18 | 1.70 |
"""


def test_build_editorial_evidence_extracts_report_facts():
    evidence = build_editorial_evidence(SAMPLE_REPORT)

    assert evidence["generated"] == "2026-06-21 13:23:26 IST"
    assert evidence["bars_loaded"] == "14748"
    assert evidence["top_setup"]["setup"] == "ORB + VWAP"
    assert evidence["walk_forward"]["walk_forward_status"] == "confirmed"
    assert evidence["core_carriers"][0]["symbol"] == "NIFTYNXT50"
    assert evidence["edge_diluters"][0]["symbol"] == "NIFTY"
    assert evidence["time_filter"]["time_bucket"] == "opening_drive"


def test_build_editorial_narrative_fallback_is_evidence_bound():
    evidence = build_editorial_evidence(SAMPLE_REPORT)

    narrative, meta = build_editorial_narrative(evidence, allow_llm=False)

    assert meta["source"] == "deterministic"
    assert "ORB + VWAP" in narrative["executive_summary"]
    assert "NIFTYNXT50" in " ".join(narrative["key_findings"])
    assert "not investment advice" in narrative["disclaimer"].lower()


def test_build_editorial_narrative_uses_llm_when_supplied():
    evidence = build_editorial_evidence(SAMPLE_REPORT)
    calls = {}

    def fake_llm(*, system, user, schema):
        calls["user"] = user
        return {
            "headline": "Opening Range + VWAP in Indian F&O",
            "executive_summary": "The confirmed result is ORB + VWAP long on 15m, backed by walk-forward validation.",
            "research_question": "Can opening-drive continuation survive unseen validation?",
            "methodology": ["Use intraday F&O bars.", "Apply transaction costs."],
            "key_findings": ["ORB + VWAP long on 15m was confirmed.", "NIFTYNXT50 carried the edge."],
            "failed_hypotheses": ["Broad short-side setups failed."],
            "risk_limits": ["Short history remains a limitation."],
            "monitoring_rules": ["Use opening-drive only for ORB + VWAP long on 15m."],
            "linkedin_post": "A concise LinkedIn post.",
            "disclaimer": "Research only; not investment advice.",
        }

    narrative, meta = build_editorial_narrative(evidence, llm_call=fake_llm)

    assert meta["source"] == "LLM"
    assert "evidence_json" in calls["user"]
    assert narrative["headline"] == "Opening Range + VWAP in Indian F&O"


def test_build_editorial_narrative_rejects_llm_when_it_conflicts_with_evidence():
    evidence = build_editorial_evidence(SAMPLE_REPORT)

    def bad_llm(*, system, user, schema):
        return {
            "headline": "Early 5-Minute MACD Momentum Study",
            "executive_summary": "MACD on 5m was the strongest result.",
            "research_question": "x",
            "methodology": ["x", "y"],
            "key_findings": ["MACD was best.", "5m worked."],
            "failed_hypotheses": ["x"],
            "risk_limits": ["x"],
            "monitoring_rules": ["x"],
            "linkedin_post": "x",
            "disclaimer": "Research only; not investment advice.",
        }

    narrative, meta = build_editorial_narrative(evidence, llm_call=bad_llm)

    assert meta["source"] == "deterministic"
    assert "validation_error" in meta
    assert "ORB + VWAP" in narrative["executive_summary"]


def test_build_and_write_editorial_report_outputs_markdown_and_html(tmp_path):
    source = tmp_path / "intraday_fno_indicator_study.md"
    source.write_text(SAMPLE_REPORT, encoding="utf-8")
    out_dir = tmp_path / "reports" / "latest"

    report = build_editorial_report(source, allow_llm=False)
    paths = write_editorial_report(report, output_dir=out_dir)

    assert "Editorial Quantitative F&O Analysis" in report.markdown
    assert Path(paths["markdown"]).exists()
    assert Path(paths["html"]).exists()
    assert "Opening Range" in Path(paths["markdown"]).read_text(encoding="utf-8")


def test_build_detailed_research_paper_explains_methodology_metrics_and_findings():
    evidence = build_editorial_evidence(SAMPLE_REPORT)
    narrative, meta = build_editorial_narrative(evidence, allow_llm=False)

    paper = build_detailed_research_paper(evidence, narrative, meta)

    assert "Detailed Research Report" in paper.markdown
    assert "What ORB + VWAP Means" in paper.markdown
    assert "Metric Glossary" in paper.markdown
    assert "Walk-Forward Validation" in paper.markdown
    assert "Research-Grade Conclusion" in paper.markdown
    assert "ORB + VWAP" in paper.markdown
    assert paper.metadata["report_type"] == "detailed_research_paper"


def test_write_detailed_research_paper_outputs_latest_markdown_html_and_json(tmp_path):
    evidence = build_editorial_evidence(SAMPLE_REPORT)
    narrative, meta = build_editorial_narrative(evidence, allow_llm=False)
    paper = build_detailed_research_paper(evidence, narrative, meta)

    paths = write_detailed_research_paper(paper, output_dir=tmp_path / "reports" / "latest")

    assert Path(paths["markdown"]).exists()
    assert Path(paths["html"]).exists()
    assert Path(paths["json"]).exists()
    assert "Detailed Research Report" in Path(paths["markdown"]).read_text(encoding="utf-8")


def test_intraday_editorial_report_command_writes_latest_outputs(tmp_path):
    source = tmp_path / "source.md"
    source.write_text(SAMPLE_REPORT, encoding="utf-8")

    output = handle_backtest_command(
        f"/intraday-editorial-report --source {source} --no-llm",
        project_root=tmp_path,
    )

    assert "Intraday F&O Editorial Report: OK" in output
    assert "Narrative source: deterministic" in output
    assert (tmp_path / "reports" / "latest" / "intraday_fno_editorial_research.html").exists()


def test_intraday_editorial_report_command_can_write_detailed_paper(tmp_path):
    source = tmp_path / "source.md"
    source.write_text(SAMPLE_REPORT, encoding="utf-8")

    output = handle_backtest_command(
        f"/intraday-editorial-report --source {source} --no-llm --detailed",
        project_root=tmp_path,
    )

    assert "Detailed paper:" in output
    assert (tmp_path / "reports" / "latest" / "intraday_fno_detailed_research_paper.html").exists()
