from terminal.composite_screeners import run_quality_breakout_screener


def _source_rows():
    return {
        "new_highs": [
            {"symbol": "AAA", "price": 100, "stage": "STAGE_2", "trading_signal": "BUY", "relative_strength": 90, "rsi": 64, "investment_score": 68},
            {"symbol": "WEAK", "price": 50, "stage": "STAGE_2", "trading_signal": "BUY", "relative_strength": 80, "rsi": 78, "investment_score": 30},
        ],
        "momentum_52w": [
            {"symbol": "BBB", "price": 200, "stage": "STAGE_2", "trading_signal": "HOLD", "relative_strength": 70, "rsi": 62, "investment_score": 61},
        ],
        "tight_range": [
            {"symbol": "AAA", "price": 101, "stage": "STAGE_2", "trading_signal": "BUY", "relative_strength": 91, "rsi": 63, "investment_score": 68},
            {"symbol": "CCC", "price": 300, "stage": "STAGE_2", "trading_signal": "BUY", "relative_strength": 55, "rsi": 58, "investment_score": 59},
        ],
        "breakouts": [
            {"symbol": "AAA", "price": 102, "stage": "STAGE_2", "trading_signal": "BUY", "relative_strength": 92, "rsi": 65, "investment_score": 68},
            {"symbol": "DDD", "price": 400, "stage": "STAGE_1", "trading_signal": "BUY", "relative_strength": 95, "rsi": 66, "investment_score": 70},
        ],
    }


def test_quality_breakout_screener_merges_tags_filters_and_exports_tv():
    sources = _source_rows()

    def runner(screen_type: str, top_n: int):
        return {"snapshot_date": "2026-06-03", "results": sources[screen_type][:top_n]}

    def snapshot(symbols):
        return {
            "AAA": {"symbol": "AAA", "company_name": "AAA Ltd", "sector": "Capital Goods", "enhanced_fund_score": 88, "technical_score": 70, "financial_strength": 80},
            "BBB": {"symbol": "BBB", "company_name": "BBB Ltd", "sector": "Pharma", "enhanced_fund_score": 62, "technical_score": 55, "financial_strength": 65},
            "CCC": {"symbol": "CCC", "company_name": "CCC Ltd", "sector": "IT", "enhanced_fund_score": 59, "technical_score": 60, "financial_strength": 70},
            "DDD": {"symbol": "DDD", "company_name": "DDD Ltd", "sector": "Banks", "enhanced_fund_score": 75, "technical_score": 50, "financial_strength": 80},
            "WEAK": {"symbol": "WEAK", "company_name": "Weak Ltd", "sector": "Other", "enhanced_fund_score": 20, "technical_score": 70, "financial_strength": 30},
        }

    result = run_quality_breakout_screener(top_n=10, mode="balanced", screener_runner=runner, snapshot_loader=snapshot)

    assert result["snapshot_date"] == "2026-06-03"
    assert result["source_counts"] == {"new_highs": 2, "momentum_52w": 1, "tight_range": 2, "breakouts": 2}
    assert result["merged_count"] == 5
    assert result["passed_count"] == 3
    assert [row["symbol"] for row in result["results"]] == ["AAA", "DDD", "BBB"]
    assert result["results"][0]["setup_tags"] == ["breakout", "new_high", "vcp_like"]
    assert "Stage 2" in result["results"][0]["reason_tags"]
    assert "NSE:AAA" in result["tradingview_symbols"]


def test_quality_breakout_broad_keeps_weak_names_with_risk_flag():
    sources = _source_rows()

    def runner(screen_type: str, top_n: int):
        return {"snapshot_date": "2026-06-03", "results": sources[screen_type][:top_n]}

    result = run_quality_breakout_screener(
        top_n=10,
        mode="broad",
        screener_runner=runner,
        snapshot_loader=lambda symbols: {},
    )

    weak = next(row for row in result["results"] if row["symbol"] == "WEAK")
    assert "weak_fundamentals" in weak["risk_flags"]
    assert result["passed_count"] == 5

