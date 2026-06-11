import nse_agent


def test_parse_quality_breakouts_command_defaults():
    parsed = nse_agent._parse_quality_breakouts_command("/screen quality-breakouts")

    assert parsed == {
        "matched": True,
        "mode": "balanced",
        "top_n": 15,
        "explain": False,
        "tv": False,
    }


def test_parse_quality_breakouts_command_aliases_and_flags():
    parsed = nse_agent._parse_quality_breakouts_command("/screen qb --strict --top 7 --explain --tv")

    assert parsed["matched"] is True
    assert parsed["mode"] == "strict"
    assert parsed["top_n"] == 7
    assert parsed["explain"] is True
    assert parsed["tv"] is True


def test_render_quality_breakouts_result_includes_tv_and_explain():
    result = {
        "snapshot_date": "2026-06-03",
        "source_counts": {"new_highs": 2, "momentum_52w": 1, "tight_range": 2, "breakouts": 2},
        "merged_count": 5,
        "passed_count": 3,
        "tradingview_symbols": ["NSE:AAA", "NSE:BBB"],
        "results": [
            {
                "symbol": "AAA",
                "price": 100,
                "stage": "STAGE_2",
                "trading_signal": "BUY",
                "rs": 90,
                "rsi": 64,
                "composite_score": 91,
                "enhanced_fund_score": 88,
                "investment_score": 68,
                "sector": "Capital Goods",
                "setup_tags": ["breakout", "new_high"],
                "reason_tags": ["Breakout", "Stage 2"],
                "risk_flags": [],
            }
        ],
    }

    text = nse_agent._render_quality_breakouts_result(result, explain=True, tv=True)

    assert "QUALITY BREAKOUTS" in text
    assert "new_highs: 2" in text
    assert "AAA" in text
    assert "Breakout" in text
    assert "NSE:AAA" in text


def test_symbol_emphasis_skips_fenced_code_blocks():
    text = "AAA is strong\n```text\nNSE:AAA\n```\nAAA remains in focus"

    rendered = nse_agent._emphasize_symbols_outside_code(text, ["AAA"])

    assert "**AAA** is strong" in rendered
    assert "NSE:AAA" in rendered
    assert "NSE:**AAA**" not in rendered
    assert "**AAA** remains in focus" in rendered
