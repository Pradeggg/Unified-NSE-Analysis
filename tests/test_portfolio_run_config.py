from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]
PORTFOLIO_ANALYZER = ROOT / "portfolio-analyzer"


def _load_run_portfolio():
    spec = importlib.util.spec_from_file_location(
        "run_portfolio", PORTFOLIO_ANALYZER / "run_portfolio.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_apply_runtime_config_redirects_inputs_and_outputs(tmp_path):
    sys.path.insert(0, str(PORTFOLIO_ANALYZER))
    try:
        run_portfolio = _load_run_portfolio()
        import config

        pnl = tmp_path / "friend_EQProfitLossDetails.csv"
        cas = tmp_path / "friend_CAS.pdf"
        holdings = tmp_path / "friend_holdings.csv"
        out = tmp_path / "runs" / "friend"
        for path in (pnl, cas, holdings):
            path.write_text("placeholder", encoding="utf-8")

        run_portfolio.apply_runtime_config(
            config,
            pnl_csv=pnl,
            cas_pdf=cas,
            holdings_csv=holdings,
            output_dir=out,
        )

        assert config.PNL_CSV == pnl
        assert config.CAS_PDF == cas
        assert config.HOLDINGS_CSV == holdings
        assert config.OUTPUT_DIR == out
        assert config.HOLDINGS_CSV_OUT == out / "holdings.csv"
        assert config.CLOSED_PNL_CSV == out / "closed_pnl.csv"
        assert config.REPORT_HTML == out / "portfolio_comprehensive_report.html"
        assert out.exists()
    finally:
        sys.path = [p for p in sys.path if p != str(PORTFOLIO_ANALYZER)]


def test_default_output_dir_uses_portfolio_name(tmp_path):
    run_portfolio = _load_run_portfolio()

    out = run_portfolio.default_output_dir("Friend Amit")

    assert out == PORTFOLIO_ANALYZER / "runs" / "friend_amit"


def test_parse_args_supports_llm_stock_views():
    run_portfolio = _load_run_portfolio()

    args = run_portfolio.parse_args(
        ["--name", "Friend Amit", "--holdings", "holdings.csv", "--llm-stock-views"]
    )

    assert args.llm_stock_views is True
    assert args.stock_view_model == "gpt-4o"


def test_load_holdings_csv_normalizes_portfolio_summary(tmp_path):
    sys.path.insert(0, str(PORTFOLIO_ANALYZER))
    try:
        from phase0_ingest import load_holdings_csv

        holdings_csv = tmp_path / "PortFolioEqtSummary.csv"
        holdings_csv.write_text(
            "\n".join(
                [
                    "Stock Symbol,Company Name,ISIN Code,Qty,Average Cost Price,Current Market Price,Value At Market Price,Unrealized Profit/Loss",
                    "AVESUP,AVENUE SUPERMARTS LTD DMART,INE192R01011,23,3022.87,4144.20,95316.60,25790.59",
                ]
            ),
            encoding="utf-8",
        )

        df = load_holdings_csv(holdings_csv)

        assert list(df[["symbol", "isin", "quantity", "value_rs"]].iloc[0]) == [
            "DMART",
            "INE192R01011",
            23,
            95316.60,
        ]
        assert df["broker_symbol"].iloc[0] == "AVESUP"
        assert df["symbol_mapping_method"].iloc[0] == "company_name"
    finally:
        sys.path = [p for p in sys.path if p != str(PORTFOLIO_ANALYZER)]


def test_symbol_mapper_handles_broker_aliases_without_false_technology_match():
    sys.path.insert(0, str(PORTFOLIO_ANALYZER))
    try:
        import portfolio_symbol_mapper as mapper

        index = mapper.build_symbol_index(
            [
                ("DIXON", "DIXON TECHNO (INDIA) LTD", "test"),
                ("KFINTECH", "KFIN TECHNOLOGIES LIMITED", "test"),
            ]
        )

        match = mapper.resolve_symbol(
            broker_symbol="DIXTEC",
            company_name="DIXON TECHNOLOGIES INDIA LTD",
            index=index,
        )

        assert match.symbol == "DIXON"
        assert match.method == "company_name"
        assert match.score >= 0.9
    finally:
        sys.path = [p for p in sys.path if p != str(PORTFOLIO_ANALYZER)]


def test_llm_mapping_uses_only_candidate_symbols():
    sys.path.insert(0, str(PORTFOLIO_ANALYZER))
    try:
        import portfolio_symbol_mapper as mapper

        class _FakeResponses:
            def create(self, **kwargs):
                assert kwargs["model"] == "gpt-4o"
                text = kwargs["text"]["format"]
                assert text["type"] == "json_schema"
                return type(
                    "Response",
                    (),
                    {
                        "output_text": (
                            '{"symbol":"DIVISLAB","confidence":"high",'
                            '"rationale":"Company name matches Divi S Laboratories."}'
                        )
                    },
                )()

        class _FakeClient:
            responses = _FakeResponses()

        index = mapper.build_symbol_index(
            [
                ("DIVISLAB", "DIVI S LABORATORIES LTD", "test"),
                ("DPEL", "DIVINE POWER ENERGY LTD", "test"),
            ]
        )

        match = mapper.resolve_symbol_with_llm(
            broker_symbol="DIVLAB",
            company_name="DIVIS LABORATORIES LIMITED",
            index=index,
            client=_FakeClient(),
            model="gpt-4o",
        )

        assert match.symbol == "DIVISLAB"
        assert match.method == "llm"
        assert match.score == 0.95
    finally:
        sys.path = [p for p in sys.path if p != str(PORTFOLIO_ANALYZER)]


def test_manual_mapping_overrides_cover_recent_and_bse_only_holdings():
    sys.path.insert(0, str(PORTFOLIO_ANALYZER))
    try:
        import portfolio_symbol_mapper as mapper

        kwil = mapper.resolve_symbol(
            broker_symbol="KWAWAL",
            company_name="KWALITY WALLS INDIA LIMITED",
            index=[],
        )
        sanpar = mapper.resolve_symbol(
            broker_symbol="SANPAR",
            company_name="SANJIVANI PARANTERAL LTD",
            index=[],
        )
        tmcv = mapper.resolve_symbol(
            broker_symbol="TATCOV",
            company_name="TATA MOTORS LIMITED",
            index=[],
        )
        tmpv = mapper.resolve_symbol(
            broker_symbol="TATMOT",
            company_name="TATA MOTORS PAX VEHICLES LTD",
            index=[],
        )

        assert kwil.symbol == "KWIL"
        assert kwil.method == "manual"
        assert sanpar.symbol == "SANPAR"
        assert sanpar.method == "bse_only"
        assert "531569" in sanpar.matched_name
        assert tmcv.symbol == "TMCV"
        assert tmpv.symbol == "TMPV"
    finally:
        sys.path = [p for p in sys.path if p != str(PORTFOLIO_ANALYZER)]


def test_report_html_contains_heatmap_canvas_and_static_chart_fallback(tmp_path, monkeypatch):
    sys.path.insert(0, str(PORTFOLIO_ANALYZER))
    try:
        import phase6_report

        out = tmp_path / "out"
        out.mkdir()
        (out / "portfolio_summary.json").write_text(
            '{"holdings_count":2,"closed_trades_count":0,"total_realized_pnl":0,'
            '"pnl_by_tenure":{},"account_name":"Test","data_as_of":null}',
            encoding="utf-8",
        )
        (out / "pnl_summary.md").write_text("# PnL summary\n", encoding="utf-8")
        (out / "holdings.csv").write_text(
            "symbol,quantity,value_rs\nDMART,1,100000\nKWIL,2,50000\n",
            encoding="utf-8",
        )
        (out / "technical_by_stock.csv").write_text(
            "symbol,value_rs,technical_score,recommendation,enhanced_fund_score,current_price\n"
            "DMART,100000,70,ADD,65,4000\nKWIL,50000,45,HOLD,50,30\n",
            encoding="utf-8",
        )
        for name in [
            "risk_metrics.json",
            "scenario_narrative.md",
            "market_sentiment.md",
            "sector_assessment.md",
            "fundamental_by_stock.csv",
            "stock_narratives.json",
        ]:
            (out / name).write_text("{}" if name.endswith(".json") else "", encoding="utf-8")

        monkeypatch.setattr(phase6_report, "OUTPUT_DIR", out)
        monkeypatch.setattr(phase6_report, "PORTFOLIO_SUMMARY_JSON", out / "portfolio_summary.json")
        monkeypatch.setattr(phase6_report, "PNL_SUMMARY_MD", out / "pnl_summary.md")
        monkeypatch.setattr(phase6_report, "HOLDINGS_CSV", out / "holdings.csv")
        monkeypatch.setattr(phase6_report, "TECHNICAL_BY_STOCK_CSV", out / "technical_by_stock.csv")
        monkeypatch.setattr(phase6_report, "RISK_METRICS_JSON", out / "risk_metrics.json")
        monkeypatch.setattr(phase6_report, "SCENARIO_NARRATIVE_MD", out / "scenario_narrative.md")
        monkeypatch.setattr(phase6_report, "MARKET_SENTIMENT_MD", out / "market_sentiment.md")
        monkeypatch.setattr(phase6_report, "SECTOR_ASSESSMENT_MD", out / "sector_assessment.md")
        monkeypatch.setattr(phase6_report, "FUNDAMENTAL_BY_STOCK_CSV", out / "fundamental_by_stock.csv")
        monkeypatch.setattr(phase6_report, "STOCK_NARRATIVES_JSON", out / "stock_narratives.json")

        html = phase6_report.build_report_html_structured()

        assert "Holdings heatmap" in html
        assert '<canvas id="chart-dec"' in html
        assert "static-chart-fallback" in html
        assert "Decision Distribution" in html
        assert "Top 15 Holdings by Value" in html
    finally:
        sys.path = [p for p in sys.path if p != str(PORTFOLIO_ANALYZER)]


def test_run_phase0_allows_holdings_only_input(tmp_path, monkeypatch):
    sys.path.insert(0, str(PORTFOLIO_ANALYZER))
    try:
        import config
        import phase0_ingest

        out = tmp_path / "out"
        holdings_csv = tmp_path / "holdings.csv"
        holdings_csv.write_text(
            "Stock Symbol,ISIN Code,Qty,Value At Market Price\nDMART,INE192R01011,2,8000\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(phase0_ingest, "OUTPUT_DIR", out)
        monkeypatch.setattr(phase0_ingest, "HOLDINGS_CSV_OUT", out / "holdings.csv")
        monkeypatch.setattr(phase0_ingest, "CLOSED_PNL_CSV", out / "closed_pnl.csv")
        monkeypatch.setattr(
            phase0_ingest, "PORTFOLIO_SUMMARY_JSON", out / "portfolio_summary.json"
        )
        monkeypatch.setattr(config, "OUTPUT_DIR", out)

        closed, holdings, summary = phase0_ingest.run_phase0(
            pnl_csv=None,
            holdings_csv=holdings_csv,
            require_pnl=False,
        )

        assert closed.empty
        assert holdings is not None
        assert summary["closed_trades_count"] == 0
        assert summary["holdings_count"] == 1
        assert (out / "holdings.csv").exists()
        assert (out / "closed_pnl.csv").exists()
    finally:
        sys.path = [p for p in sys.path if p != str(PORTFOLIO_ANALYZER)]


def test_phase7_uses_value_rs_and_aggregates_duplicate_symbol_weights(tmp_path, monkeypatch):
    sys.path.insert(0, str(PORTFOLIO_ANALYZER))
    try:
        import phase7_risk

        out = tmp_path / "out"
        out.mkdir()
        holdings_csv = out / "holdings.csv"
        holdings_csv.write_text(
            "symbol,quantity,value_rs\n"
            "TMPV,10,1000\n"
            "TMPV,5,500\n"
            "TMCV,7,1500\n",
            encoding="utf-8",
        )

        monkeypatch.setattr(phase7_risk, "HOLDINGS_CSV_OUT", holdings_csv)
        holdings, meta = phase7_risk.load_holdings_weights()

        assert meta["portfolio_value_rs"] == 3000
        assert holdings["weight"].sum() == 1

        dates = pd.date_range("2026-01-01", periods=3)
        stock_returns = pd.DataFrame(
            {"TMPV": [0.01, 0.02, 0.03], "TMCV": [0.02, 0.00, -0.01]},
            index=dates,
        )
        returns = phase7_risk.portfolio_returns(
            holdings[["symbol", "weight"]],
            stock_returns,
        )

        assert len(returns) == 3
        assert returns.iloc[0] == pytest.approx(0.015)
        grouped_weights = holdings.groupby("symbol", as_index=True)["weight"].sum()
        assert float(grouped_weights.get("TMPV")) == pytest.approx(0.5)
    finally:
        sys.path = [p for p in sys.path if p != str(PORTFOLIO_ANALYZER)]
