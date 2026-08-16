from __future__ import annotations

from tools.fund_daily import build_fresh_selection


def _row(symbol: str, price: float, tech_score: float) -> dict:
    return {
        "symbol": symbol,
        "price": price,
        "tech_score": tech_score,
        "rs": 10.0,
        "fund_score": 70.0,
        "fund_grade": "B",
        "both_pass": True,
    }


def test_fresh_selection_skips_zero_quantity_and_backfills_from_next_candidate() -> None:
    result = {
        "holds": [],
        "drops": [],
        "adds": [],
        "top_n": [],
        "watch": [],
        "passing": [
            _row("IPCALAB", 1796.30, 80.0),
            _row("FLUOROCHEM", 4714.70, 75.3),
            _row("AJANTPHARM", 3614.60, 70.7),
            _row("APARINDS", 17225.00, 70.0),
            _row("EXIDEIND", 485.50, 68.7),
            _row("OBEROIRLTY", 1846.00, 68.7),
            _row("COFORGE", 1829.00, 67.3),
            _row("BERGEPAINT", 546.35, 67.3),
            _row("ENDURANCE", 2975.30, 67.3),
            _row("AUROPHARMA", 1663.40, 65.3),
            _row("SONACOMS", 799.90, 64.7),
            _row("GODREJIND", 1255.60, 64.7),
            _row("FEDERALBNK", 352.45, 61.3),
            _row("NYKAA", 331.15, 61.3),
            _row("KALYANKJIL", 613.40, 59.3),
            _row("360ONE", 1090.00, 58.7),
        ],
    }

    selected = build_fresh_selection(result, n=15, alloc_per=13_333.33)

    symbols = [row["symbol"] for row in selected["adds"]]
    assert "APARINDS" not in symbols
    assert symbols[-1] == "360ONE"
    assert all(row["_fresh_qty"] >= 1 for row in selected["adds"])
    assert selected["adds"][-1]["_fresh_rank"] == 16
    assert selected["skipped"][0]["symbol"] == "APARINDS"
    assert "exceeds slot" in selected["skipped"][0]["_fresh_skip_reason"]
    assert all(row.get("_fresh_stop") for row in selected["adds"])
    assert all(row.get("_fresh_binding") for row in selected["adds"])
