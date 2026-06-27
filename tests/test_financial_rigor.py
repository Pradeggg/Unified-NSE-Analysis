import json
from decimal import Decimal


def test_extract_report_data_points_from_markdown_tables_and_key_values():
    from terminal.financial_rigor import extract_report_data_points

    markdown = """
# Sample Report

Revenue: Rs 1,200 cr
ROE: 24%

| Metric | FY26 | FY25 |
| --- | ---: | ---: |
| Net Profit | 300 cr | 250 cr |
| Stock P/E | 24.5x | 22x |
"""

    points = extract_report_data_points(markdown)
    by_label = {point.label: point for point in points}

    assert by_label["Revenue"].reported_value == Decimal("1200")
    assert by_label["Revenue"].unit == "cr"
    assert by_label["ROE"].reported_value == Decimal("24")
    assert by_label["ROE"].unit == "%"
    assert by_label["Net Profit - FY26"].reported_value == Decimal("300")
    assert by_label["Stock P/E - FY26"].unit == "x"


def test_sample_report_data_points_is_deterministic_with_seed():
    from terminal.financial_rigor import extract_report_data_points, sample_report_data_points

    markdown = "\n".join(f"Metric {idx}: {idx}%" for idx in range(1, 21))
    points = extract_report_data_points(markdown)

    first = sample_report_data_points(points, ratio=0.2, seed=7)
    second = sample_report_data_points(points, ratio=0.2, seed=7)

    assert [point.id for point in first] == [point.id for point in second]
    assert len(first) == 4


def test_verify_valuation_metrics_uses_exact_decimal_arithmetic():
    from terminal.financial_rigor import verify_valuation_metrics

    metrics = verify_valuation_metrics(
        price=Decimal("2400"),
        eps=Decimal("100"),
        book_value_per_share=Decimal("300"),
        fcf_per_share=Decimal("80"),
        dividend_per_share=Decimal("24"),
    )

    assert metrics["pe"] == Decimal("24.00")
    assert metrics["pb"] == Decimal("8.00")
    assert metrics["earnings_yield_pct"] == Decimal("4.17")
    assert metrics["fcf_yield_pct"] == Decimal("3.33")
    assert metrics["dividend_yield_pct"] == Decimal("1.00")


def test_build_valuation_snapshot_from_cached_screener_payload():
    from terminal.financial_rigor import build_valuation_snapshot

    def fake_cache(symbol, max_age_hours=None):
        assert symbol == "INFY"
        return {
            "ratios": {
                "Current Price": "2,400",
                "Stock P/E": "24",
                "Price to book value": "8",
                "Book Value": "300",
                "EPS": "100",
                "Dividend Yield": "1%",
                "Market Cap": "720000",
            },
            "_cache_age_hours": 3.5,
        }

    snapshot = build_valuation_snapshot("INFY", cache_loader=fake_cache)

    assert snapshot.symbol == "INFY"
    assert snapshot.status == "ok"
    assert snapshot.metrics["pe"] == Decimal("24.00")
    assert snapshot.metrics["pb"] == Decimal("8.00")
    assert snapshot.metrics["earnings_yield_pct"] == Decimal("4.17")
    assert snapshot.source == "screener_cache"
    assert snapshot.cache_age_hours == 3.5


def test_valuation_snapshot_marks_missing_cache_without_fabricating_metrics():
    from terminal.financial_rigor import build_valuation_snapshot

    snapshot = build_valuation_snapshot("NOPE", cache_loader=lambda symbol, max_age_hours=None: None)

    assert snapshot.status == "missing"
    assert snapshot.metrics == {}


def test_render_report_audit_json_payload(tmp_path):
    from terminal.financial_rigor import render_report_audit_json

    report = tmp_path / "report.md"
    report.write_text("Revenue: Rs 1,200 cr\nROE: 24%\nPE: 20x\n", encoding="utf-8")

    payload = json.loads(render_report_audit_json(str(report), ratio=1.0, seed=1))

    assert payload["report_path"] == str(report)
    assert payload["total_points"] == 3
    assert payload["sample_count"] == 3
    assert {item["label"] for item in payload["sample"]} == {"Revenue", "ROE", "PE"}
