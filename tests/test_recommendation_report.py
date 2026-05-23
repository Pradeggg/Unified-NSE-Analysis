import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pandas as pd

import terminal.recommendation_report as recommendation_report
from terminal.recommendation_report import (
    GroundedRecommendation,
    RecommendationReportOptions,
    RecommendationLabel,
    RecommendationInputData,
    SubjectEvidence,
    TechnicalProfile,
    build_recommendations,
    build_recommendation_evidence_pack,
    build_technical_profile,
    classify_fundamentals,
    generate_recommendation_report,
    load_recommendation_input_data,
    make_recommendation,
    parse_recommendation_report_args,
    pct_change_from_lookback,
    persist_recommendation_run,
    render_recommendation_markdown,
    save_evidence_json,
)


def test_pct_change_from_lookback_uses_nearest_prior_bar():
    frame = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "close": 100.0},
            {"trade_date": "2026-01-08", "close": 110.0},
            {"trade_date": "2026-02-01", "close": 121.0},
        ]
    )

    assert pct_change_from_lookback(frame, "2026-02-01", days=7) == 10.0


def test_build_technical_profile_computes_grounded_fields():
    rows = []
    for idx in range(240):
        close = 100.0 + idx
        rows.append(
            {
                "trade_date": pd.Timestamp("2025-09-01") + pd.Timedelta(days=idx),
                "open": close - 1,
                "high": close + 2,
                "low": close - 2,
                "close": close,
                "volume": 1000 + idx,
            }
        )
    frame = pd.DataFrame(rows)

    profile = build_technical_profile("AAA", frame, benchmark_frame=frame)

    assert isinstance(profile, TechnicalProfile)
    assert profile.subject == "AAA"
    assert profile.latest_close == 339.0
    assert profile.sma20 is not None
    assert profile.sma50 is not None
    assert profile.sma200 is not None
    assert profile.price_above_sma20 is True
    assert profile.price_above_sma50 is True
    assert profile.price_above_sma200 is True
    assert profile.rsi14 is not None
    assert profile.macd_hist is not None
    assert profile.trend_label in {"bullish", "constructive"}
    assert profile.missing_evidence == []


def test_parse_recommendation_report_args_supports_format_watchlist_and_top():
    opts = parse_recommendation_report_args(
        ["recommendation", "--watchlist", "AAA,BBB", "--top", "12", "--format", "md"]
    )

    assert opts.output_format == "md"
    assert opts.watchlist == ["AAA", "BBB"]
    assert opts.top_n == 12


def test_parse_recommendation_report_args_supports_symbol_index_and_sector_filters():
    opts = parse_recommendation_report_args(
        [
            "recommendation",
            "--symbols",
            "AAA,BBB",
            "--index",
            "NIFTY BANK",
            "--sectors",
            "Capital Goods,Chemicals",
        ]
    )

    assert opts.symbols == ["AAA", "BBB"]
    assert opts.indices == ["NIFTY BANK"]
    assert opts.sectors == ["Capital Goods", "Chemicals"]


def _history(symbol: str, start: float = 100.0, rows: int = 240) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "symbol": symbol,
                "trade_date": pd.Timestamp("2025-09-01") + pd.Timedelta(days=idx),
                "open": start + idx - 1,
                "high": start + idx + 2,
                "low": start + idx - 2,
                "close": start + idx,
                "volume": 1000 + idx,
            }
            for idx in range(rows)
        ]
    )


def test_generate_recommendation_report_with_injected_data_writes_report_and_evidence(tmp_path):
    data = RecommendationInputData(
        index_history=_history("NIFTY 50"),
        equity_history=_history("AAA"),
        snapshots=pd.DataFrame(
            [
                {
                    "symbol": "AAA",
                    "sector": "Capital Goods",
                    "stage": "STAGE_2",
                    "technical_score": 88,
                    "relative_strength": 32,
                    "trading_signal": "BUY",
                    "investment_score": 82,
                }
            ]
        ),
        fundamentals=pd.DataFrame(
            [{"symbol": "AAA", "roe": 18, "roce": 24, "stock_pe": 22, "interest_coverage": 9}]
        ),
    )
    opts = RecommendationReportOptions(output_format="md", output_dir=tmp_path)

    result = generate_recommendation_report(options=opts, input_data=data, persist=False)

    assert result["success"] is True
    assert result["format"] == "md"
    assert Path(result["path"]).exists()
    assert Path(result["evidence_path"]).exists()
    assert result["recommendation_count"] >= 1
    assert "# Grounded EOD Recommendation Report" in result["markdown"]
    assert "## Stock Opportunity Map" in result["markdown"]


def test_load_recommendation_input_data_loads_portfolio_from_postgres_first(monkeypatch):
    postgres_portfolio = pd.DataFrame([{"symbol": "PGHOLD", "qty": 7, "avg_cost": 123.45}])
    postgres_queries = []

    def fake_load_postgres_frame(sql: str) -> pd.DataFrame:
        postgres_queries.append(sql)
        if "holding" in sql.lower() or "portfolio" in sql.lower():
            return postgres_portfolio
        return pd.DataFrame()

    def fake_read_csv_frame(path: Path) -> pd.DataFrame:
        if path.name == "holdings.csv":
            raise AssertionError("portfolio CSV fallback should not be used when PostgreSQL has holdings")
        return pd.DataFrame()

    monkeypatch.setattr(recommendation_report, "_load_postgres_frame", fake_load_postgres_frame)
    monkeypatch.setattr(recommendation_report, "_read_csv_frame", fake_read_csv_frame)

    data = load_recommendation_input_data(RecommendationReportOptions(include_portfolio=True))

    assert data.portfolio.to_dict("records") == [{"symbol": "PGHOLD", "qty": 7, "avg_cost": 123.45}]
    assert any("holding" in sql.lower() or "portfolio" in sql.lower() for sql in postgres_queries)


def test_load_recommendation_input_data_skips_shallow_primary_equity_csv(monkeypatch):
    shallow = _history("SHALLOW", rows=5)
    deep = _history("DEEP", rows=80)
    csv_reads = []

    monkeypatch.setattr(recommendation_report, "_load_postgres_frame", lambda sql: pd.DataFrame())

    def fake_read_csv_frame(path: Path) -> pd.DataFrame:
        csv_reads.append(path.name)
        if path.name == "nse_sec_full_data.csv":
            return shallow
        if path.name == "nse_universe_stock_data.csv":
            return deep
        return pd.DataFrame()

    monkeypatch.setattr(recommendation_report, "_read_csv_frame", fake_read_csv_frame)

    data = load_recommendation_input_data(RecommendationReportOptions())

    assert data.equity_history["symbol"].unique().tolist() == ["DEEP"]
    assert "nse_sec_full_data.csv" in csv_reads
    assert "nse_universe_stock_data.csv" in csv_reads


def test_generate_recommendation_report_with_empty_data_returns_evidence_warning(tmp_path):
    opts = RecommendationReportOptions(output_format="md", output_dir=tmp_path)

    result = generate_recommendation_report(
        options=opts,
        input_data=RecommendationInputData(),
        persist=False,
    )

    assert result["success"] is True
    assert result["warnings"]
    assert any("critical" in warning.lower() or "missing" in warning.lower() for warning in result["warnings"])


def test_generate_recommendation_report_filename_includes_run_id(tmp_path):
    data = RecommendationInputData(
        index_history=_history("NIFTY 50"),
        equity_history=_history("AAA"),
        snapshots=pd.DataFrame([{"symbol": "AAA"}]),
    )
    opts = RecommendationReportOptions(output_format="md", output_dir=tmp_path)

    result = generate_recommendation_report(options=opts, input_data=data, persist=False)

    assert result["run_id"][:8] in Path(result["path"]).name


def test_build_evidence_pack_contains_indices_sectors_stocks_and_portfolio():
    data = RecommendationInputData(
        index_history=pd.concat([_history("NIFTY 50"), _history("NIFTY BANK", 120.0)]),
        equity_history=pd.concat([_history("AAA"), _history("BBB", 80.0)]),
        snapshots=pd.DataFrame(
            [
                {
                    "symbol": "AAA",
                    "sector": "Capital Goods",
                    "stage": "STAGE_2",
                    "technical_score": 82,
                    "relative_strength": 24,
                    "trading_signal": "BUY",
                    "investment_score": 76,
                },
                {
                    "symbol": "BBB",
                    "sector": "Chemicals",
                    "stage": "STAGE_4",
                    "technical_score": 18,
                    "relative_strength": -12,
                    "trading_signal": "SELL",
                    "investment_score": 30,
                },
            ]
        ),
        fundamentals=pd.DataFrame(
            [
                {"symbol": "AAA", "roe": 18, "roce": 22, "stock_pe": 24, "interest_coverage": 8},
                {"symbol": "BBB", "roe": 5, "roce": 7, "stock_pe": 55, "interest_coverage": 1.2},
            ]
        ),
        portfolio=pd.DataFrame([{"symbol": "AAA", "qty": 10, "avg_cost": 150.0}]),
        watchlist=["BBB"],
    )

    pack = build_recommendation_evidence_pack(data, top_n=10)

    assert pack.as_of
    assert "NIFTY 50" in pack.indices
    assert "Capital Goods" in pack.sectors
    assert "AAA" in pack.stocks
    assert "BBB" in pack.stocks
    assert "AAA" in pack.portfolio
    assert "BBB" in pack.portfolio
    assert pack.source_trail["equity_history"]["rows"] == 480
    assert pack.missing_evidence == {}


def test_watchlist_only_symbol_reports_missing_snapshot_and_fundamentals():
    data = RecommendationInputData(
        index_history=_history("NIFTY 50"),
        equity_history=_history("ZZZ"),
        watchlist=["ZZZ"],
    )

    pack = build_recommendation_evidence_pack(data)

    assert "ZZZ" in pack.portfolio
    assert "snapshot" in pack.portfolio["ZZZ"].missing_evidence
    assert "fundamentals" in pack.portfolio["ZZZ"].missing_evidence
    assert pack.source_trail["watchlist"]["rows"] == 1
    assert pack.source_trail["watchlist"]["status"] == "primary"


def test_malformed_snapshot_source_is_not_reported_as_primary():
    data = RecommendationInputData(
        index_history=_history("NIFTY 50"),
        equity_history=_history("AAA"),
        snapshots=pd.DataFrame([{"ticker": "AAA", "technical_score": 82}]),
        fundamentals=pd.DataFrame([{"symbol": "AAA", "roe": 18}]),
    )

    pack = build_recommendation_evidence_pack(data)

    assert pack.source_trail["snapshots"]["rows"] == 1
    assert pack.source_trail["snapshots"]["status"] == "degraded"
    assert pack.source_trail["snapshots"]["missing_columns"] == ["symbol"]
    assert pack.missing_evidence["snapshots"] == ["source_degraded"]


def test_portfolio_symbol_outside_top_n_uses_stock_missing_evidence_rules():
    data = RecommendationInputData(
        index_history=_history("NIFTY 50"),
        equity_history=pd.concat([_history("AAA"), _history("BBB", 80.0)]),
        snapshots=pd.DataFrame(
            [
                {"symbol": "AAA", "technical_score": 90, "investment_score": 80},
                {"symbol": "BBB", "technical_score": 10, "investment_score": 5},
            ]
        ),
        fundamentals=pd.DataFrame([{"symbol": "AAA", "roe": 18}]),
        portfolio=pd.DataFrame([{"symbol": "BBB", "qty": 3, "avg_cost": 75.0}]),
    )

    pack = build_recommendation_evidence_pack(data, top_n=1)

    assert "AAA" in pack.stocks
    assert "BBB" not in pack.stocks
    assert "BBB" in pack.portfolio
    assert "fundamentals" in pack.portfolio["BBB"].missing_evidence
    assert "snapshot" not in pack.portfolio["BBB"].missing_evidence


def test_sector_rollup_uses_full_universe_even_when_stock_recommendations_are_limited():
    data = RecommendationInputData(
        index_history=_history("NIFTY 50"),
        equity_history=pd.concat([_history("LEADER"), _history("LAGGARD", 80.0)]),
        snapshots=pd.DataFrame(
            [
                {
                    "symbol": "LEADER",
                    "sector": "Capital Goods",
                    "technical_score": 95,
                    "investment_score": 80,
                    "relative_strength": 30,
                    "stage": "STAGE_2",
                    "trading_signal": "BUY",
                },
                {
                    "symbol": "LAGGARD",
                    "sector": "Chemicals",
                    "technical_score": 10,
                    "investment_score": 20,
                    "relative_strength": -25,
                    "stage": "STAGE_4",
                    "trading_signal": "SELL",
                },
            ]
        ),
        fundamentals=pd.DataFrame(
            [
                {"symbol": "LEADER", "roe": 18, "roce": 24, "interest_coverage": 8},
                {"symbol": "LAGGARD", "roe": 4, "roce": 6, "interest_coverage": 1.1},
            ]
        ),
    )

    pack = build_recommendation_evidence_pack(data, top_n=1)

    assert list(pack.stocks) == ["LEADER"]
    assert "Capital Goods" in pack.sectors
    assert "Chemicals" in pack.sectors
    assert pack.sectors["Chemicals"]["rotation_label"] == "laggard"


def test_evidence_pack_filters_recommendations_by_symbols_indices_and_sectors():
    data = RecommendationInputData(
        index_history=pd.concat([_history("NIFTY 50"), _history("NIFTY BANK", 120.0)]),
        equity_history=pd.concat([_history("AAA"), _history("BBB", 80.0), _history("CCC", 60.0)]),
        snapshots=pd.DataFrame(
            [
                {"symbol": "AAA", "sector": "Capital Goods", "technical_score": 90, "investment_score": 80},
                {"symbol": "BBB", "sector": "Chemicals", "technical_score": 85, "investment_score": 75},
                {"symbol": "CCC", "sector": "IT", "technical_score": 70, "investment_score": 65},
            ]
        ),
        fundamentals=pd.DataFrame(
            [
                {"symbol": "AAA", "roe": 18, "roce": 24, "interest_coverage": 8},
                {"symbol": "BBB", "roe": 16, "roce": 20, "interest_coverage": 7},
                {"symbol": "CCC", "roe": 15, "roce": 19, "interest_coverage": 6},
            ]
        ),
    )

    pack = build_recommendation_evidence_pack(
        data,
        top_n=10,
        symbols=["AAA", "CCC"],
        indices=["NIFTY BANK"],
        sectors=["Capital Goods"],
    )

    assert list(pack.indices) == ["NIFTY BANK"]
    assert list(pack.stocks) == ["AAA"]
    assert list(pack.sectors) == ["Capital Goods"]
    assert pack.filters == {
        "symbols": ["AAA", "CCC"],
        "indices": ["NIFTY BANK"],
        "sectors": ["Capital Goods"],
    }


def test_portfolio_recommendation_is_retained_when_symbol_also_has_stock_recommendation():
    data = RecommendationInputData(
        index_history=_history("NIFTY 50"),
        equity_history=_history("AAA"),
        snapshots=pd.DataFrame(
            [
                {
                    "symbol": "AAA",
                    "sector": "Capital Goods",
                    "stage": "STAGE_2",
                    "technical_score": 88,
                    "relative_strength": 32,
                    "trading_signal": "BUY",
                    "investment_score": 82,
                }
            ]
        ),
        fundamentals=pd.DataFrame(
            [{"symbol": "AAA", "roe": 18, "roce": 24, "stock_pe": 22, "interest_coverage": 9}]
        ),
        portfolio=pd.DataFrame([{"symbol": "AAA", "qty": 10, "avg_cost": 150.0}]),
        watchlist=["AAA"],
    )
    pack = build_recommendation_evidence_pack(data)

    recommendations = build_recommendations(pack)

    assert [rec.scope for rec in recommendations if rec.subject == "AAA"].count("stock") == 1
    assert [rec.scope for rec in recommendations if rec.subject == "AAA"].count("portfolio") == 1


def test_policy_assigns_add_on_confirmation_for_grounded_strength():
    evidence = SubjectEvidence(
        subject="AAA",
        scope="stock",
        sector="Capital Goods",
        technical=TechnicalProfile(subject="AAA", trend_label="constructive"),
        snapshot={
            "symbol": "AAA",
            "sector": "Capital Goods",
            "stage": "STAGE_2",
            "technical_score": 88,
            "relative_strength": 32,
            "trading_signal": "BUY",
            "investment_score": 82,
        },
        fundamentals={"symbol": "AAA", "roe": 18, "roce": 24, "stock_pe": 22, "interest_coverage": 9},
    )

    rec = make_recommendation(
        evidence,
        market_regime={"label": "risk_on"},
        sector={"rotation_label": "leader"},
    )

    assert rec.label == RecommendationLabel.ADD_ON_CONFIRMATION
    assert rec.confidence in {"high", "medium"}
    assert rec.technical_evidence
    assert rec.fundamental_evidence
    assert rec.trigger
    assert rec.invalidation
    assert rec.risk


def test_policy_uses_screener_ratio_summary_when_numeric_fundamental_fields_are_null():
    evidence = SubjectEvidence(
        subject="SHAILY",
        scope="stock",
        sector="Capital Goods",
        technical=TechnicalProfile(subject="SHAILY", trend_label="bullish"),
        snapshot={
            "symbol": "SHAILY",
            "sector": "Capital Goods",
            "stage": "STAGE_2",
            "technical_score": 77.3,
            "relative_strength": 44.46,
            "trading_signal": "BUY",
            "investment_score": 70,
        },
        fundamentals={
            "symbol": "SHAILY",
            "roe": None,
            "roce": None,
            "ratios_summary": "ROCE: 17%; EPS: 34.45; NPM: 16.26%",
        },
    )

    rec = make_recommendation(
        evidence,
        market_regime={"label": "risk_off"},
        sector={"rotation_label": "leader"},
    )

    assert classify_fundamentals(evidence.fundamentals) == "quality_mixed"
    assert rec.label == RecommendationLabel.ADD_ON_CONFIRMATION
    assert "ROCE 17.0" in rec.fundamental_evidence


def test_policy_assigns_watchlist_when_strong_setup_has_conflict():
    evidence = SubjectEvidence(
        subject="AAA",
        scope="stock",
        sector="Capital Goods",
        technical=TechnicalProfile(
            subject="AAA",
            trend_label="constructive",
            conflicts=["trend constructive but RSI extended"],
        ),
        snapshot={
            "symbol": "AAA",
            "sector": "Capital Goods",
            "stage": "STAGE_2",
            "technical_score": 88,
            "relative_strength": 32,
            "trading_signal": "BUY",
            "investment_score": 82,
        },
        fundamentals={"symbol": "AAA", "roe": 18, "roce": 24, "stock_pe": 22, "interest_coverage": 9},
    )

    rec = make_recommendation(
        evidence,
        market_regime={"label": "risk_on"},
        sector={"rotation_label": "leader"},
    )

    assert rec.label == RecommendationLabel.WATCHLIST
    assert rec.why == "Signals are mixed, so keep it on the watchlist until the listed conflicts resolve."


def test_policy_review_manually_for_missing_eod_caps_score_and_confidence():
    evidence = SubjectEvidence(
        subject="AAA",
        scope="stock",
        sector="Capital Goods",
        technical=TechnicalProfile(subject="AAA", trend_label="constructive"),
        snapshot={
            "symbol": "AAA",
            "sector": "Capital Goods",
            "stage": "STAGE_2",
            "technical_score": 95,
            "relative_strength": 40,
            "trading_signal": "BUY",
            "investment_score": 90,
        },
        fundamentals={"symbol": "AAA", "roe": 20, "roce": 26, "stock_pe": 22, "interest_coverage": 10},
        missing_evidence=["eod_price_history"],
    )

    rec = make_recommendation(
        evidence,
        market_regime={"label": "risk_on"},
        sector={"rotation_label": "leader"},
    )

    assert rec.label == RecommendationLabel.REVIEW_MANUALLY
    assert rec.confidence == "low"
    assert rec.score <= 40


def test_policy_watchlist_why_explains_non_actionable_setup_without_incomplete_jargon():
    evidence = SubjectEvidence(
        subject="AAA",
        scope="stock",
        sector="Capital Goods",
        technical=TechnicalProfile(subject="AAA", trend_label="neutral"),
        snapshot={
            "symbol": "AAA",
            "sector": "Capital Goods",
            "stage": "STAGE_1",
            "technical_score": 52,
            "relative_strength": 3,
            "trading_signal": "HOLD",
            "investment_score": 55,
        },
        fundamentals={"symbol": "AAA", "roe": 10, "roce": 12, "interest_coverage": 4},
    )

    rec = make_recommendation(
        evidence,
        market_regime={"label": "neutral"},
        sector={"rotation_label": "neutral"},
    )

    assert rec.label == RecommendationLabel.WATCHLIST
    assert rec.why == "No actionable entry case yet; wait for clearer technical and fundamental confirmation."
    assert "incomplete" not in rec.why.lower()


def test_policy_missing_ordinary_evidence_prevents_high_confidence():
    evidence = SubjectEvidence(
        subject="BBB",
        scope="stock",
        sector="Chemicals",
        technical=TechnicalProfile(subject="BBB", trend_label="bearish"),
        snapshot={
            "symbol": "BBB",
            "sector": "Chemicals",
            "stage": "STAGE_4",
            "technical_score": 12,
            "relative_strength": -25,
            "trading_signal": "SELL",
            "investment_score": 18,
        },
        fundamentals={},
        missing_evidence=["fundamentals"],
    )

    rec = make_recommendation(
        evidence,
        market_regime={"label": "risk_off"},
        sector={"rotation_label": "laggard"},
    )

    assert rec.label == RecommendationLabel.AVOID_FRESH_ENTRY
    assert rec.confidence != "high"


def test_policy_assigns_avoid_for_weak_technical_trend():
    evidence = SubjectEvidence(
        subject="CCC",
        scope="stock",
        sector="Industrials",
        technical=TechnicalProfile(subject="CCC", trend_label="weak"),
        snapshot={
            "symbol": "CCC",
            "sector": "Industrials",
            "stage": "STAGE_1",
            "technical_score": 48,
            "relative_strength": -5,
            "trading_signal": "HOLD",
            "investment_score": 60,
        },
        fundamentals={"symbol": "CCC", "roe": 15, "roce": 18, "interest_coverage": 5},
    )

    rec = make_recommendation(
        evidence,
        market_regime={"label": "neutral"},
        sector={"rotation_label": "neutral"},
    )

    assert rec.label == RecommendationLabel.AVOID_FRESH_ENTRY


def test_policy_assigns_avoid_for_weak_stage_and_fundamentals():
    data = RecommendationInputData(
        index_history=_history("NIFTY 50"),
        equity_history=_history("BBB", start=300.0).assign(
            close=lambda df: list(reversed(df["close"].tolist()))
        ),
        snapshots=pd.DataFrame(
            [
                {
                    "symbol": "BBB",
                    "sector": "Chemicals",
                    "stage": "STAGE_4",
                    "technical_score": 18,
                    "relative_strength": -20,
                    "trading_signal": "SELL",
                    "investment_score": 25,
                }
            ]
        ),
        fundamentals=pd.DataFrame(
            [{"symbol": "BBB", "roe": 4, "roce": 6, "stock_pe": 60, "interest_coverage": 1.1}]
        ),
    )
    pack = build_recommendation_evidence_pack(data)

    rec = make_recommendation(
        pack.stocks["BBB"],
        market_regime=pack.market_regime,
        sector=pack.sectors["Chemicals"],
    )

    assert rec.label == RecommendationLabel.AVOID_FRESH_ENTRY
    assert "STAGE_4" in " ".join(rec.technical_evidence)
    assert rec.confidence in {"medium", "high"}


def test_fundamental_classification_marks_missing_as_unknown():
    assert classify_fundamentals({}) == "quality_unknown"


def test_fundamental_classification_marks_unscoreable_fields_as_unknown():
    assert classify_fundamentals({"symbol": "AAA", "company_name": "AAA Ltd"}) == "quality_unknown"


def _markdown_section(markdown: str, heading: str) -> str:
    start = markdown.index(heading)
    next_heading = markdown.find("\n##", start + len(heading))
    if next_heading == -1:
        next_heading = len(markdown)
    return markdown[start:next_heading]


def test_markdown_report_contains_required_sections_grounding_and_actual_label_counts(tmp_path):
    pack = build_recommendation_evidence_pack(
        RecommendationInputData(
            index_history=_history("NIFTY 50"),
            equity_history=_history("AAA"),
            snapshots=pd.DataFrame([{"symbol": "AAA", "sector": "Capital Goods"}]),
            fundamentals=pd.DataFrame([{"symbol": "AAA", "roe": 18}]),
        )
    )
    recommendations = [
        GroundedRecommendation(
            subject="AAA",
            scope="stock",
            label=RecommendationLabel.ADD_ON_CONFIRMATION,
            confidence="high",
            score=82,
            why="Constructive setup.",
            technical_evidence=["Stage STAGE_2"],
            fundamental_evidence=["ROE 18"],
            trigger="Confirm above resistance.",
            invalidation="Lose support.",
            risk="Size for regime.",
            missing_evidence=[],
        ),
        GroundedRecommendation(
            subject="BBB",
            scope="stock",
            label=RecommendationLabel.WATCHLIST,
            confidence="low",
            score=61,
            why="Evidence conflict.",
            technical_evidence=["Trend constructive"],
            fundamental_evidence=["ROE 12"],
            trigger="Wait for conflict to clear.",
            invalidation="Lose support.",
            risk="Conflict risk.",
            missing_evidence=[],
            conflicts=["trend constructive but RSI extended"],
        ),
    ]

    markdown = render_recommendation_markdown(pack, recommendations)

    assert "# Grounded EOD Recommendation Report" in markdown
    assert "## Executive Summary" in markdown
    assert "## Market Regime" in markdown
    assert "## Sector Rotation" in markdown
    assert "## Stock Opportunity Map" in markdown
    assert "## Technical Detail Appendix" in markdown
    assert "## Fundamental Detail Appendix" in markdown
    assert "## Grounding & Audit Trail" in markdown
    assert "### Source Trail" in markdown
    assert "### Missing Evidence" in markdown
    assert "ADD_ON_CONFIRMATION: 1" in markdown
    assert "WATCHLIST: 1" in markdown
    assert "trend constructive but RSI extended" in markdown


def test_markdown_report_uses_reader_friendly_language_for_placeholders_unknowns_and_labels():
    pack = build_recommendation_evidence_pack(
        RecommendationInputData(
            index_history=_history("NIFTY 50"),
            equity_history=_history("AAA"),
            snapshots=pd.DataFrame([{"symbol": "AAA", "sector": "Unknown"}]),
        )
    )
    pack.stocks["AAA"].missing_evidence = ["fundamentals"]
    recommendations = [
        GroundedRecommendation(
            subject="AAA",
            scope="stock",
            label=RecommendationLabel.WATCHLIST,
            confidence="medium",
            score=59,
            why="Evidence is not aligned enough for action.",
            technical_evidence=["Trend constructive"],
            fundamental_evidence=["Fundamental quality quality_unknown"],
            trigger="Wait for confirmation.",
            invalidation="Lose support.",
            risk="Missing fundamentals.",
            missing_evidence=["fundamentals"],
            conflicts=["trend constructive but RSI extended"],
        )
    ]

    markdown = render_recommendation_markdown(pack, recommendations)

    assert "## How to Read This Report" in markdown
    assert "## Data Quality Notice" in markdown
    assert "`AAA` looks like a placeholder/test ticker" in markdown
    assert "Symbol | Universe | View | Confidence" in markdown
    assert "Watchlist / wait for confirmation" in markdown
    assert "Sector unavailable" in markdown
    assert "Fundamentals unavailable" in markdown
    assert "missing fundamentals" in markdown
    assert "quality_unknown" not in markdown
    assert "source_missing" not in markdown
    assert "| AAA | stock | WATCHLIST |" not in markdown


def test_missing_evidence_section_does_not_print_none_when_subject_missing_exists():
    pack = build_recommendation_evidence_pack(
        RecommendationInputData(index_history=_history("NIFTY 50"), equity_history=_history("AAA"))
    )
    pack.missing_evidence = {}
    pack.stocks["AAA"].missing_evidence = ["fundamentals"]

    markdown = render_recommendation_markdown(pack, [])
    missing_section = _markdown_section(markdown, "### Missing Evidence")

    assert "- none" not in missing_section
    assert "`AAA`: missing fundamentals" in missing_section


def test_save_evidence_json_writes_replayable_payload(tmp_path):
    pack = build_recommendation_evidence_pack(RecommendationInputData(index_history=_history("NIFTY 50")))

    path = save_evidence_json(pack, [], output_dir=tmp_path)

    assert path.exists()
    payload = json.loads(path.read_text())
    assert payload["pack"]["run_id"] == pack.run_id
    assert payload["recommendations"] == []


def test_persist_recommendation_run_falls_back_when_postgres_unavailable(tmp_path):
    pack = build_recommendation_evidence_pack(RecommendationInputData(index_history=_history("NIFTY 50")))
    evidence_path = save_evidence_json(pack, [], output_dir=tmp_path)

    with patch("terminal.recommendation_report._connect_pg", side_effect=RuntimeError("pg down")):
        result = persist_recommendation_run(pack, [], "/tmp/report.md", str(evidence_path))

    assert result["status"] == "fallback_json"
    assert result["evidence_path"] == str(evidence_path)


def test_persist_recommendation_run_replaces_child_rows_and_uses_payload_column():
    class FakeCursor:
        def __init__(self):
            self.executed = []

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, sql, params=None):
            self.executed.append((str(sql), params))

    class FakeConnection:
        def __init__(self, cursor):
            self.cursor_instance = cursor
            self.committed = False
            self.closed = False

        def cursor(self):
            return self.cursor_instance

        def commit(self):
            self.committed = True

        def rollback(self):
            raise AssertionError("success path should not roll back")

        def close(self):
            self.closed = True

    cursor = FakeCursor()
    conn = FakeConnection(cursor)
    pack = build_recommendation_evidence_pack(
        RecommendationInputData(
            index_history=_history("NIFTY 50"),
            equity_history=_history("AAA"),
            snapshots=pd.DataFrame([{"symbol": "AAA", "sector": "Capital Goods"}]),
        )
    )
    recommendation = GroundedRecommendation(
        subject="AAA",
        scope="stock",
        label=RecommendationLabel.HOLD,
        confidence="medium",
        score=55,
        why="Evidence is balanced.",
        technical_evidence=["Trend constructive"],
        fundamental_evidence=[],
        trigger="Wait for confirmation.",
        invalidation="Lose support.",
        risk="Position size conservatively.",
        missing_evidence=[],
    )

    with patch("terminal.recommendation_report._connect_pg", return_value=conn):
        result = persist_recommendation_run(pack, [recommendation], "/tmp/report.md", "/tmp/evidence.json")

    normalized_sql = [" ".join(sql.split()).lower() for sql, _params in cursor.executed]
    joined_sql = "\n".join(normalized_sql)
    recommendation_delete_idx = next(
        idx
        for idx, sql in enumerate(normalized_sql)
        if "delete from recommendation_reports.recommendations where run_id=%s" in sql
    )
    evidence_delete_idx = next(
        idx
        for idx, sql in enumerate(normalized_sql)
        if "delete from recommendation_reports.evidence where run_id=%s" in sql
    )
    recommendation_insert_idx = next(
        idx
        for idx, sql in enumerate(normalized_sql)
        if "insert into recommendation_reports.recommendations" in sql
    )
    evidence_insert_idx = next(
        idx
        for idx, sql in enumerate(normalized_sql)
        if "insert into recommendation_reports.evidence" in sql
    )

    assert result == {"status": "postgres", "schema": "recommendation_reports", "run_id": pack.run_id}
    assert conn.committed is True
    assert conn.closed is True
    assert evidence_delete_idx < evidence_insert_idx
    assert recommendation_delete_idx < recommendation_insert_idx
    recommendation_insert_sql = normalized_sql[recommendation_insert_idx]
    assert "recommendation_reports.recommendations ( run_id, subject, scope, label, confidence, score, payload )" in joined_sql
    assert "payload" in recommendation_insert_sql
    assert "policy" not in recommendation_insert_sql


def test_schema_sql_upgrades_legacy_policy_column_to_payload():
    normalized_schema_sql = " ".join(recommendation_report.SCHEMA_SQL.split()).lower()

    assert "information_schema.columns" in normalized_schema_sql
    assert "column_name = 'policy'" in normalized_schema_sql
    assert "column_name = 'payload'" in normalized_schema_sql
    assert "alter table recommendation_reports.recommendations rename column policy to payload" in normalized_schema_sql
    assert "insert into recommendation_reports.recommendations" not in normalized_schema_sql


def test_save_evidence_json_converts_non_finite_numbers_and_timestamps(tmp_path):
    pack = build_recommendation_evidence_pack(RecommendationInputData(index_history=_history("NIFTY 50")))
    pack.market_regime["inf"] = float("inf")
    pack.market_regime["neg_inf"] = float("-inf")
    pack.market_regime["nan"] = float("nan")
    pack.market_regime["timestamp"] = pd.Timestamp("2026-05-22 09:15:00")
    recommendation = GroundedRecommendation(
        subject="AAA",
        scope="stock",
        label=RecommendationLabel.REVIEW_MANUALLY,
        confidence="low",
        score=float("inf"),
        why="Replay edge case.",
        technical_evidence=[pd.Timestamp("2026-05-22")],
        fundamental_evidence=[],
        trigger="Collect evidence.",
        invalidation="Missing evidence remains.",
        risk="Manual review.",
        missing_evidence=["eod_price_history"],
    )

    path = save_evidence_json(pack, [recommendation], output_dir=tmp_path)

    assert path.name == f"recommendation_evidence_{pack.run_id}.json"
    payload = json.loads(path.read_text())
    assert payload["pack"]["market_regime"]["inf"] is None
    assert payload["pack"]["market_regime"]["neg_inf"] is None
    assert payload["pack"]["market_regime"]["nan"] is None
    assert payload["pack"]["market_regime"]["timestamp"] == "2026-05-22T09:15:00"
    assert payload["recommendations"][0]["score"] is None
    assert payload["recommendations"][0]["technical_evidence"] == ["2026-05-22T00:00:00"]


def test_save_evidence_json_serializes_python_dates_from_fundamentals(tmp_path):
    pack = build_recommendation_evidence_pack(
        RecommendationInputData(
            index_history=_history("NIFTY 50"),
            equity_history=_history("AAA"),
            fundamentals=pd.DataFrame(
                [
                    {
                        "symbol": "AAA",
                        "roe": 18,
                        "report_date": date(2026, 5, 22),
                        "updated_at": datetime(2026, 5, 22, 15, 30),
                    }
                ]
            ),
        )
    )
    pack.stocks["AAA"].fundamentals["manual_date"] = date(2026, 5, 23)
    pack.stocks["AAA"].fundamentals["manual_datetime"] = datetime(2026, 5, 23, 15, 30)

    path = save_evidence_json(pack, [], output_dir=tmp_path)

    payload = json.loads(path.read_text())
    fundamentals = payload["pack"]["stocks"]["AAA"]["fundamentals"]
    assert fundamentals["report_date"] == "2026-05-22"
    assert fundamentals["updated_at"] == "2026-05-22T15:30:00"
    assert fundamentals["manual_date"] == "2026-05-23"
    assert fundamentals["manual_datetime"] == "2026-05-23T15:30:00"


def test_save_evidence_json_serializes_pandas_nat_as_null(tmp_path):
    pack = build_recommendation_evidence_pack(
        RecommendationInputData(index_history=_history("NIFTY 50"), equity_history=_history("AAA"))
    )
    pack.stocks["AAA"].fundamentals["missing_date"] = pd.NaT
    pack.market_regime["missing_timestamp"] = pd.NaT

    path = save_evidence_json(pack, [], output_dir=tmp_path)

    payload = json.loads(path.read_text())
    assert payload["pack"]["stocks"]["AAA"]["fundamentals"]["missing_date"] is None
    assert payload["pack"]["market_regime"]["missing_timestamp"] is None


def test_save_evidence_json_serializes_decimal_values(tmp_path):
    pack = build_recommendation_evidence_pack(
        RecommendationInputData(index_history=_history("NIFTY 50"), equity_history=_history("AAA"))
    )
    pack.stocks["AAA"].fundamentals["decimal_pe"] = Decimal("22.5")
    pack.market_regime["decimal_nan"] = Decimal("NaN")

    path = save_evidence_json(pack, [], output_dir=tmp_path)

    payload = json.loads(path.read_text())
    assert payload["pack"]["stocks"]["AAA"]["fundamentals"]["decimal_pe"] == 22.5
    assert payload["pack"]["market_regime"]["decimal_nan"] is None


def test_every_recommendation_has_required_grounding_fields():
    data = RecommendationInputData(
        index_history=_history("NIFTY 50"),
        equity_history=pd.concat([_history("AAA"), _history("BBB", 80.0)]),
        snapshots=pd.DataFrame(
            [
                {
                    "symbol": "AAA",
                    "sector": "Capital Goods",
                    "stage": "STAGE_2",
                    "technical_score": 88,
                    "relative_strength": 32,
                    "trading_signal": "BUY",
                    "investment_score": 82,
                },
                {
                    "symbol": "BBB",
                    "sector": "Chemicals",
                    "stage": "STAGE_4",
                    "technical_score": 18,
                    "relative_strength": -20,
                    "trading_signal": "SELL",
                    "investment_score": 25,
                },
            ]
        ),
        fundamentals=pd.DataFrame(
            [
                {"symbol": "AAA", "roe": 18, "roce": 24, "stock_pe": 22, "interest_coverage": 9},
                {"symbol": "BBB", "roe": 4, "roce": 6, "stock_pe": 60, "interest_coverage": 1.1},
            ]
        ),
    )
    pack = build_recommendation_evidence_pack(data)
    recommendations = build_recommendations(pack)

    assert recommendations
    for recommendation in recommendations:
        assert recommendation.why
        assert recommendation.technical_evidence
        assert recommendation.fundamental_evidence
        assert recommendation.trigger
        assert recommendation.invalidation
        assert recommendation.risk
        assert recommendation.confidence in {"high", "medium", "low"}
