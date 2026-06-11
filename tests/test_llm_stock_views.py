from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PORTFOLIO_ANALYZER = ROOT / "portfolio-analyzer"


def test_llm_stock_views_writes_structured_verdicts(tmp_path):
    sys.path.insert(0, str(PORTFOLIO_ANALYZER))
    try:
        import llm_stock_views

        narratives = tmp_path / "stock_narratives.json"
        output = tmp_path / "llm_stock_views.json"
        narratives.write_text(
            json.dumps(
                [
                    {
                        "symbol": "DMART",
                        "quantity": 2,
                        "value_rs": 100000,
                        "technical_score": 72,
                        "fund_score": 68,
                        "recommendation": "ADD",
                        "trading_signal": "BUY",
                        "trend_signal": "BULLISH",
                        "change_1m_pct": 8.4,
                        "relative_strength": 12.0,
                        "narrative": "Technical: strong. Fundamental: steady.",
                    }
                ]
            ),
            encoding="utf-8",
        )

        class _FakeResponses:
            def create(self, **kwargs):
                assert kwargs["model"] == "gpt-4o"
                fmt = kwargs["text"]["format"]
                assert fmt["type"] == "json_schema"
                assert fmt["name"] == "portfolio_llm_stock_views"
                assert fmt["strict"] is True
                return type(
                    "Response",
                    (),
                    {
                        "output_text": json.dumps(
                            {
                                "views": [
                                    {
                                        "symbol": "DMART",
                                        "short_term_view": "MUST BUY",
                                        "long_term_view": "HOLD",
                                        "final_verdict": "HOLD",
                                        "confidence": 0.74,
                                        "key_reasons": ["strong trend", "quality compounder"],
                                        "risks_to_view": ["valuation risk"],
                                    }
                                ]
                            }
                        )
                    },
                )()

        class _FakeClient:
            responses = _FakeResponses()

        result = llm_stock_views.run_llm_stock_views(
            narratives_json=narratives,
            output_json=output,
            client=_FakeClient(),
            model="gpt-4o",
        )

        assert result["n_views"] == 1
        saved = json.loads(output.read_text(encoding="utf-8"))
        assert saved["model"] == "gpt-4o"
        assert saved["views"][0]["symbol"] == "DMART"
        assert saved["views"][0]["final_verdict"] == "HOLD"
    finally:
        sys.path = [p for p in sys.path if p != str(PORTFOLIO_ANALYZER)]


def test_llm_stock_views_normalizes_invalid_model_verdicts(tmp_path):
    sys.path.insert(0, str(PORTFOLIO_ANALYZER))
    try:
        import llm_stock_views

        raw = {
            "symbol": " dmart ",
            "short_term_view": "buy",
            "long_term_view": "sell immediately",
            "final_verdict": "",
            "confidence": "1.8",
            "key_reasons": ["ok", ""],
            "risks_to_view": [],
        }

        normalized = llm_stock_views.normalize_view(raw, allowed_symbols={"DMART"})

        assert normalized == {
            "symbol": "DMART",
            "short_term_view": "MUST BUY",
            "long_term_view": "MUST SELL",
            "final_verdict": "HOLD",
            "confidence": 1.0,
            "key_reasons": ["ok"],
            "risks_to_view": [],
            "source": "llm",
        }
    finally:
        sys.path = [p for p in sys.path if p != str(PORTFOLIO_ANALYZER)]


def test_llm_stock_views_fills_missing_symbols_conservatively(tmp_path):
    sys.path.insert(0, str(PORTFOLIO_ANALYZER))
    try:
        import llm_stock_views

        evidence = [{"symbol": "DMART"}, {"symbol": "KWIL"}]
        views = [
            {
                "symbol": "DMART",
                "short_term_view": "MUST BUY",
                "long_term_view": "HOLD",
                "final_verdict": "HOLD",
                "confidence": 0.74,
                "key_reasons": ["strong trend"],
                "risks_to_view": [],
            }
        ]

        complete = llm_stock_views.complete_views(evidence, views)

        assert [row["symbol"] for row in complete] == ["DMART", "KWIL"]
        assert complete[0]["source"] == "llm"
        assert complete[1]["final_verdict"] == "HOLD"
        assert complete[1]["source"] == "fallback"
        assert "omitted" in complete[1]["key_reasons"][0]
    finally:
        sys.path = [p for p in sys.path if p != str(PORTFOLIO_ANALYZER)]


def test_build_evidence_includes_fundamental_analysis_details():
    sys.path.insert(0, str(PORTFOLIO_ANALYZER))
    try:
        import llm_stock_views

        evidence = llm_stock_views.build_evidence(
            [
                {
                    "symbol": "DMART",
                    "fund_score": 68,
                    "fund_earnings_quality": 72,
                    "fund_sales_growth": 64,
                    "fund_financial_strength": 81,
                    "fund_institutional_backing": 55,
                    "pnl_summary": "Revenue and margins remain resilient.",
                    "quarterly_summary": "Latest quarter showed steady sales growth.",
                    "balance_sheet_summary": "Low leverage and healthy liquidity.",
                    "ratios_summary": "Premium valuation versus sector.",
                }
            ]
        )

        fundamental = evidence[0]["fundamental_analysis"]
        assert fundamental["composite_score"] == 68
        assert fundamental["earnings_quality"] == 72
        assert fundamental["sales_growth"] == 64
        assert fundamental["financial_strength"] == 81
        assert fundamental["institutional_backing"] == 55
        assert fundamental["pnl_summary"] == "Revenue and margins remain resilient."
        assert fundamental["quarterly_summary"] == "Latest quarter showed steady sales growth."
        assert fundamental["balance_sheet_summary"] == "Low leverage and healthy liquidity."
        assert fundamental["ratios_summary"] == "Premium valuation versus sector."
    finally:
        sys.path = [p for p in sys.path if p != str(PORTFOLIO_ANALYZER)]
