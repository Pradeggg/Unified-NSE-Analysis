from rrg_report import _rotation_narrative, generate_html


def test_rotation_narrative_uses_current_sector_rrg_for_current_leaders():
    timeline = {
        "25 JUN 2026": [
            {"sym": "Nifty Auto", "label": "Auto", "x": 80, "y": 80},
            {"sym": "Nifty Realty", "label": "Realty", "x": 20, "y": 20},
        ],
    }
    current_sector_rrg = [
        {"sym": "Nifty Realty", "label": "REALTY", "x": 6.04, "y": 3.24, "quadrant": "LEADING"},
        {"sym": "Nifty Auto", "label": "AUTO", "x": -0.19, "y": -0.03, "quadrant": "LAGGING"},
    ]

    narrative = _rotation_narrative(timeline, current_sector_rrg)

    assert "Current sector leaders:" in narrative
    assert "REALTY" in narrative
    assert "Leading now:" not in narrative


def test_breadth_table_headers_distinguish_count_from_composite_score():
    html = generate_html(
        rrg_results=[],
        sector_rrg=[],
        thematic_rrg=[],
        timeline={},
        breadth_results=[],
        as_of="17 Jul 2026",
    )

    assert '<th style="color:#475569;font-weight:500">Count</th>' in html
    assert "<th>Composite</th>" in html
    assert html.count("<th>COMP</th>") == 0
