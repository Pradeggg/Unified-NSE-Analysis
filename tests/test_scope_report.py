from pathlib import Path
import re

import pandas as pd

from terminal.scope_report import (
    ScopeInputData,
    ScopeReportOptions,
    build_scope_report_markdown,
    generate_scope_report,
    parse_scope_report_args,
)


def _sample_scope_data() -> ScopeInputData:
    snapshots = pd.DataFrame(
        [
            {
                "symbol": "AAA",
                "company_name": "AAA Pharma",
                "sector": "Pharma & Healthcare",
                "price": 100,
                "change_1d_pct": 1.2,
                "change_1w_pct": 4.5,
                "change_1m_pct": 11.0,
                "stage": "STAGE_2",
                "technical_score": 82,
                "rsi": 64,
                "trading_signal": "BUY",
                "relative_strength": 33,
                "enhanced_fund_score": 71,
                "investment_score": 79,
            },
            {
                "symbol": "BBB",
                "company_name": "BBB Labs",
                "sector": "Pharma & Healthcare",
                "price": 220,
                "change_1d_pct": -0.5,
                "change_1w_pct": 1.1,
                "change_1m_pct": 8.0,
                "stage": "STAGE_2",
                "technical_score": 63,
                "rsi": 77,
                "trading_signal": "HOLD",
                "relative_strength": 12,
                "enhanced_fund_score": 68,
                "investment_score": 66,
            },
            {
                "symbol": "CCC",
                "company_name": "CCC Health",
                "sector": "Pharma & Healthcare",
                "price": 55,
                "change_1d_pct": -2.1,
                "change_1w_pct": -6.0,
                "change_1m_pct": -9.0,
                "stage": "STAGE_1",
                "technical_score": 28,
                "rsi": 38,
                "trading_signal": "SELL",
                "relative_strength": -22,
                "enhanced_fund_score": 44,
                "investment_score": 35,
            },
        ]
    )
    index_history = pd.DataFrame(
        [
            {
                "index_symbol": "NIFTY PHARMA",
                "trade_date": f"2026-05-{day:02d}",
                "close": 24000 + day * 20,
                "change_pct": 0.2,
                "high": 24100 + day * 20,
                "low": 23900 + day * 20,
                "technical_score": 62,
                "rsi": 58,
                "trading_signal": "BUY",
            }
            for day in range(1, 23)
        ]
    )
    quarterly = pd.DataFrame(
        [
            {
                "symbol": "AAA",
                "period_label": "Mar 2026",
                "revenue": 1000,
                "opm_pct": 18,
                "pat": 120,
                "eps": 4.2,
            }
        ]
    )
    fundamentals = pd.DataFrame(
        [
            {
                "symbol": "AAA",
                "forensic_risk": "LOW",
                "roe": 18,
                "roce": 24,
                "debt_to_equity": 0.3,
                "altman_z_score": 4.1,
                "beneish_m_score": -2.8,
                "piotroski_score": 7,
            }
        ]
    )
    return ScopeInputData(
        snapshots=snapshots,
        index_history=index_history,
        quarterly_results=quarterly,
        fundamentals=fundamentals,
        snapshot_date="2026-05-22",
        eod_date="2026-05-22",
    )


def test_parse_scope_report_args_supports_sector_index_and_enrichment_flags():
    opts = parse_scope_report_args(
        [
            "--scope",
            "sector",
            "--name",
            "Pharma & Healthcare",
            "--with-web",
            "--with-charts",
            "--llm",
            "--top",
            "12",
            "--format",
            "md",
        ]
    )

    assert opts.scope == "sector"
    assert opts.name == "Pharma & Healthcare"
    assert opts.with_web is True
    assert opts.with_charts is True
    assert opts.with_llm is True
    assert opts.top_n == 12
    assert opts.output_format == "md"


def test_scope_report_markdown_contains_charts_narrative_research_and_no_prompt_options():
    opts = ScopeReportOptions(
        scope="sector",
        name="Pharma & Healthcare",
        output_format="md",
        with_charts=True,
        with_web=True,
        with_llm=True,
    )

    def fake_web_search(subject: str, scope: str):
        return {
            "broker_research": [
                {
                    "source": "Example Broker",
                    "title": "Pharma sector upgrade",
                    "url": "https://example.com/pharma-report",
                    "take": "Selective margin recovery watch.",
                }
            ],
            "credit_ratings": [
                {
                    "source": "Example Ratings",
                    "title": "Stable pharma credit outlook",
                    "url": "https://example.com/credit",
                    "take": "Balance sheets broadly stable.",
                }
            ],
            "news": [],
        }

    def fake_llm(prompt: str) -> str:
        assert "AAA" in prompt
        return "LLM analyst narrative: breadth is selective; watch execution risk."

    markdown = build_scope_report_markdown(
        opts,
        _sample_scope_data(),
        web_search_fn=fake_web_search,
        llm_narrative_fn=fake_llm,
    )

    assert "# Pharma & Healthcare Sector Research Report" in markdown
    assert "Situation Assessment" not in markdown
    assert "Top LLM Summary" not in markdown
    assert "## Executive Summary" in markdown
    assert "## Summary Cards" in markdown
    assert "## Technical Dashboard" in markdown
    assert "### Benchmark Trend" in markdown
    assert "### Breadth And Participation" in markdown
    assert "### Leadership And Rotation" in markdown
    assert "<svg" in markdown
    assert "Index Candlestick + EMA" in markdown
    assert "Volume Distribution" in markdown
    assert "RSI Distribution" in markdown
    assert "Supertrend Breadth" in markdown
    assert "Index Trend - NIFTY PHARMA" in markdown
    assert "LLM analyst narrative" in markdown
    assert markdown.index("## Executive Summary") < markdown.index("## Summary Cards")
    assert markdown.index("### Benchmark Trend") < markdown.index("### Breadth And Participation")
    assert markdown.index("### Breadth And Participation") < markdown.index("### Leadership And Rotation")
    assert markdown.index("Index Candlestick + EMA") < markdown.index("Stage Distribution")
    assert markdown.index("RSI Distribution") < markdown.index("Top Relative Strength Leaders")
    assert "## Broker And Research Report Scan" in markdown
    assert "Example Broker" in markdown
    assert "## Credit And Balance Sheet Risk Lens" in markdown
    assert "Example Ratings" in markdown
    assert "Recommended Next Options" not in markdown
    assert "Recommended Prompts" not in markdown


def test_generate_scope_report_writes_html_with_standard_theme(tmp_path):
    opts = ScopeReportOptions(
        scope="sector",
        name="Pharma & Healthcare",
        output_format="html",
        output_dir=tmp_path,
        with_charts=True,
        with_web=False,
        with_llm=False,
    )

    result = generate_scope_report(options=opts, input_data=_sample_scope_data())

    assert result["success"] is True
    assert result["format"] == "html"
    assert Path(result["path"]).exists()
    html = Path(result["path"]).read_text(encoding="utf-8")
    assert "sector-rotation-standard" in html
    assert "Technical Dashboard" in html
    assert "Summary Cards" in html
    assert "scope-card" in html
    assert "empty-chart" in html
    assert "&lt;div class=&#x27;empty-chart&#x27;" not in html
    assert "width:calc(50%" in html
    assert re.search(r"\bNA\b", html) is None
    assert "Action Checklist" in html
    assert "Situation Assessment" not in html
    assert "Top LLM Summary" not in html
    assert "Recommended Next Options" not in html


def test_index_scope_uses_mapped_stock_universe_not_full_snapshot():
    data = _sample_scope_data()
    extra = data.snapshots.copy()
    extra["sector"] = "IT & Technology"
    extra["symbol"] = ["ITAAA", "ITBBB", "ITCCC"]
    data.snapshots = pd.concat([data.snapshots, extra], ignore_index=True)
    data.index_history["index_symbol"] = "Nifty IT"
    opts = ScopeReportOptions(scope="index", name="Nifty IT", output_format="md", with_charts=False)

    markdown = build_scope_report_markdown(opts, data)

    assert "Universe | 3 |" in markdown
    assert "ITAAA" in markdown
    assert "AAA Pharma" not in markdown


def test_scope_report_loads_project_dotenv_before_llm_lookup(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr("terminal.scope_report.ROOT", tmp_path)
    (tmp_path / ".env").write_text("OPENAI_API_KEY=test-dotenv-key\n", encoding="utf-8")

    from terminal.scope_report import _load_project_env

    _load_project_env()

    assert "OPENAI_API_KEY" in __import__("os").environ
