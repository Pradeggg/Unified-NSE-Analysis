from pathlib import Path

from broker_research.report import render_broker_research_html, render_broker_research_markdown, write_broker_research_report


def test_render_broker_research_markdown_includes_consensus_and_source_appendix():
    markdown = render_broker_research_markdown(
        symbol="BEL",
        consensus={
            "symbol": "BEL",
            "broker_count": 2,
            "brokers": ["hdfc_hsie", "icici"],
            "ratings": {"ADD": 1, "BUY": 1},
            "target_price": {"min": 475.0, "max": 520.0, "average": 497.5, "spread": 45.0},
            "recurring_risks": [{"value": "risks include execution delay", "count": 2}],
            "recurring_catalysts": [{"value": "catalysts include defence order wins", "count": 2}],
            "disagreements": ["rating_disagreement", "target_price_spread"],
        },
        facts=[
            {
                "broker_code": "icici",
                "report_title": "Bharat Electronics Q3FY26",
                "pdf_url": "https://example.com/bel.pdf",
                "fact_type": "rating",
                "fact_value": "BUY",
                "page_number": 1,
            }
        ],
    )

    assert "Not investment advice" in markdown
    assert "## Broker Coverage Map" in markdown
    assert "## Rating And Target-Price Consensus" in markdown
    assert "rating_disagreement" in markdown
    assert "## Missing Evidence" in markdown
    assert "## Source Appendix" in markdown
    assert "https://example.com/bel.pdf" in markdown


def test_render_broker_research_html_wraps_markdown_content():
    html = render_broker_research_html("# Broker Research: BEL\n\nNot investment advice.")

    assert "<!doctype html>" in html
    assert "Broker Research: BEL" in html
    assert "Not investment advice." in html


def test_write_broker_research_report_writes_markdown_html_and_latest(tmp_path):
    result = write_broker_research_report(
        symbol="BEL",
        markdown="# Broker Research: BEL\n",
        output_dir=tmp_path / "broker_research",
        latest_dir=tmp_path / "latest",
    )

    assert Path(result["markdown_path"]).exists()
    assert Path(result["html_path"]).exists()
    assert Path(result["latest_markdown_path"]).exists()
    assert Path(result["latest_html_path"]).exists()
    assert Path(result["latest_html_path"]).read_text(encoding="utf-8").startswith("<!doctype html>")
