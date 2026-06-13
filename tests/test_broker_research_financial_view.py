from pathlib import Path

from broker_research.financial_view import (
    build_financial_analyst_markdown,
    build_llm_financial_prompt,
    write_financial_analyst_report,
)


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
    )

    assert "## Financial Analyst Point Of View" in markdown
    assert "The analyst view is constructive" in markdown
    assert "## Valuation And Return Setup" in markdown
    assert "₹530" in markdown
    assert "26%" in markdown
    assert "₹ 74,000 crore" in markdown
    assert "FY25-28E" in markdown
    assert "## Evidence Register" in markdown
    assert "Page 2" in markdown


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
    )

    assert "financial analyst" in prompt.lower()
    assert "Page 2" in prompt
    assert "order backlog" in prompt
    assert "Do not invent" in prompt


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
