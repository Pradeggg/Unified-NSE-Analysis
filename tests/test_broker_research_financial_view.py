from pathlib import Path

from broker_research.financial_view import (
    build_agent_adda_pg_view,
    build_financial_analyst_markdown,
    build_llm_financial_prompt,
    write_financial_analyst_report,
)


AGENT_ADDA_CONTEXT = {
    "available": True,
    "instrument": {"sector": "PSU / CPSE", "industry": "Aerospace & Defense"},
    "latest_eod": {"trade_date": "2026-06-12", "close": 406.50},
    "daily_score": {
        "score_date": "2026-06-12",
        "current_price": 406.50,
        "change_1m_pct": -5.21,
        "technical_score": 26,
        "rsi": 39.2,
        "relative_strength": -6.05,
        "trend_signal": "STRONG_BEARISH",
        "trading_signal": "SELL",
    },
    "fundamental_score": {
        "enhanced_fund_score": 83.73,
        "earnings_quality": 83,
        "sales_growth": 88.33,
        "financial_strength": 82.25,
        "institutional_backing": 80,
    },
    "screener_summary": {
        "conviction_tier": "MINIMAL",
        "screens_passed_total": 2,
        "passed_screens": ["F03_HIGH_EARNINGS_QUALITY", "F04_STRONG_BALANCE_SHEET"],
        "stage": "STAGE_1",
        "trading_signal": "SELL",
    },
    "annual_results": [
        {"period_label": "Mar 2026", "revenue": 27610, "pat": 6062, "eps": 8.29},
    ],
    "quarterly_results": [
        {"period_label": "Mar 2026", "revenue": 10224, "pat": 2226, "eps": 3.04},
    ],
    "sector_context": {
        "score_date": "2026-06-12",
        "sector": "PSU / CPSE",
        "buy_signals": 0,
        "stage2_count": 0,
    },
}


def test_build_financial_analyst_markdown_is_evidence_grounded():
    markdown = build_financial_analyst_markdown(
        symbol="BEL",
        consensus={
            "broker_count": 1,
            "brokers": ["icici"],
            "ratings": {"BUY": 1},
            "target_price": {"average": 530.0, "min": 530.0, "max": 530.0, "spread": 0.0},
        },
        facts=[
            {
                "broker_code": "icici",
                "report_title": "Shubh Nivesh",
                "pdf_url": "https://example.com/bel.pdf",
                "fact_type": "rating",
                "fact_value": "BUY",
                "page_number": 2,
            },
            {
                "broker_code": "icici",
                "report_title": "Shubh Nivesh",
                "pdf_url": "https://example.com/bel.pdf",
                "fact_type": "target_price",
                "fact_value": "530",
                "page_number": 2,
            },
        ],
        pages=[
            {
                "broker_code": "icici",
                "report_title": "Shubh Nivesh",
                "pdf_url": "https://example.com/bel.pdf",
                "page_number": 2,
                "text": (
                    "CMP: ₹ 422 Target: ₹530 (26%) BUY Investment Rationale: "
                    "Company order backlog stands at ₹ 74,000 crore. "
                    "Management guides ~15% revenue CAGR. "
                    "We expect revenue & PAT CAGR at ~17% each over FY25-28E. "
                    "Key risks i) Dependent on govt contracts ii) High working capital requirement."
                ),
            }
        ],
        llm_view="The analyst view is constructive, but execution and working capital need monitoring.",
        agent_adda_context=AGENT_ADDA_CONTEXT,
    )

    assert "## Financial Analyst Point Of View" in markdown
    assert "The analyst view is constructive" in markdown
    assert "## Agent Adda PG-Grounded View" in markdown
    assert "quality business, weak current setup, valuation-sensitive" in markdown
    assert "signal `SELL`" in markdown
    assert "## Valuation And Return Setup" in markdown
    assert "₹530" in markdown
    assert "26%" in markdown
    assert "₹ 74,000 crore" in markdown
    assert "FY25-28E" in markdown
    assert "## Evidence Register" in markdown
    assert "Page 2" in markdown


def test_build_financial_analyst_markdown_preserves_llm_markdown_and_sanitizes_tables():
    markdown = build_financial_analyst_markdown(
        symbol="BEL",
        consensus={
            "broker_count": 1,
            "brokers": ["icici"],
            "ratings": {"BUY": 1},
            "target_price": {"average": 530.0},
        },
        facts=[],
        pages=[
            {
                "broker_code": "icici",
                "report_title": "Shubh Nivesh | Bharat Electronics",
                "pdf_url": "https://example.com/bel.pdf",
                "page_number": 3,
                "text": "ICICI Securities | Retail Research with pipe delimiters",
            }
        ],
        llm_view="## Analyst Memo\n\n### Thesis\n\n- **Backlog** supports visibility.",
    )

    assert "## Analyst Memo" in markdown
    assert "### Thesis" in markdown
    assert "**Backlog** supports visibility" in markdown
    assert "Shubh Nivesh / Bharat Electronics" in markdown
    assert "ICICI Securities / Retail Research" in markdown


def test_build_llm_financial_prompt_contains_page_bounded_evidence():
    prompt = build_llm_financial_prompt(
        symbol="BEL",
        consensus={"ratings": {"BUY": 1}, "target_price": {"average": 530.0}},
        facts=[],
        pages=[
            {
                "broker_code": "icici",
                "report_title": "Shubh Nivesh",
                "page_number": 2,
                "text": "BUY target price ₹530 order backlog ₹74,000 crore",
            }
        ],
        agent_adda_context=AGENT_ADDA_CONTEXT,
    )

    assert "financial analyst" in prompt.lower()
    assert "Agent Adda PG context JSON" in prompt
    assert "quality business, weak current setup, valuation-sensitive" in prompt
    assert "Page 2" in prompt
    assert "order backlog" in prompt
    assert "Do not invent" in prompt


def test_build_agent_adda_pg_view_summarizes_quality_setup_and_valuation():
    view = build_agent_adda_pg_view(
        symbol="BEL",
        context=AGENT_ADDA_CONTEXT,
        consensus={"target_price": {"average": 530.0}},
    )

    assert "quality business, weak current setup, valuation-sensitive" in view
    assert "technical score `26`" in view
    assert "conviction `MINIMAL`" in view
    assert "0 BUY signals" in view


def test_write_financial_analyst_report_writes_markdown_html_and_latest(tmp_path):
    result = write_financial_analyst_report(
        symbol="BEL",
        markdown="# Financial Analyst Research: BEL\n",
        output_dir=tmp_path / "financial_research",
        latest_dir=tmp_path / "latest",
    )

    assert Path(result["markdown_path"]).exists()
    assert Path(result["html_path"]).exists()
    assert Path(result["latest_markdown_path"]).exists()
    assert Path(result["latest_html_path"]).exists()
    assert Path(result["latest_html_path"]).read_text(encoding="utf-8").startswith("<!doctype html>")
