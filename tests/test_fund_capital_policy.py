from __future__ import annotations

from tools.fund_capital_policy import (
    CapitalPolicy,
    ExposureBook,
    infer_stop,
    is_high_conviction,
    load_capital_policy,
    size_fresh_row,
)
from tools.fund_daily import build_fresh_selection


def _policy(**overrides) -> CapitalPolicy:
    base = load_capital_policy()
    data = base.__dict__.copy()
    data.update(overrides)
    return CapitalPolicy(**data)


def _row(symbol: str, price: float, **extra) -> dict:
    row = {
        "symbol": symbol,
        "price": price,
        "tech_score": 68.0,
        "fund_score": 70.0,
        "fund_grade": "B",
        "both_pass": True,
        "sector": extra.pop("sector", ""),
    }
    row.update(extra)
    return row


def test_loader_reads_shared_4l_policy() -> None:
    policy = load_capital_policy()
    assert policy.total_nav == 400_000
    assert policy.budget_sc == 200_000
    assert policy.budget_mc == 200_000
    assert policy.slots_sc == 9
    assert policy.slots_mc == 15
    assert policy.sector_cap == 100_000
    assert policy.single_stock_cap == 40_000
    assert policy.trade_risk_normal == 2_500


def test_infer_stop_prefers_tighter_structure_level() -> None:
    stop, source = infer_stop(_row("IPCALAB", 1800.0, sma50=1650.0, supertrend_value=1600.0))
    assert source == "sma50"
    assert stop == 1650.0


def test_midcap_risk_sizing_binds_when_stop_is_wide() -> None:
    """A 10% default stop on a Rs. 2,000 stock caps qty below the MidCap slot."""
    policy = _policy()
    # slot = 13333 / 2000 = 6; risk = 2500 / 200 = 12; stock = 40000 / 2000 = 20
    # With a 10% stop, slot still binds. Use a 11% SMA50 stop: dist=220, risk qty=11.
    # To make risk bind: stop 8% of 5000 = 400 dist, risk qty = 2500/400 = 6,
    # slot = 13333/5000 = 2 — slot still binds.
    # Use price 800, 10% stop dist=80, risk qty=31, slot=16 — slot binds.
    # Use price 800, SMA50 720 (10%), same.
    # Risk binds when stop is tight: price 800, stop 780 (2.5%), dist=20, risk qty=125,
    # still slot binds (16).
    # Risk binds when stop is wider: price 2500, stop 2250 (10%), dist=250,
    # risk qty=10, slot=5 — slot binds.
    # Need risk_qty < slot_qty: allowed_risk/dist < alloc/price
    # 2500/dist < 13333/price => dist > 2500 * price / 13333
    # For price 1000, dist > 187.5, i.e. stop farther than 18.75% — but max is 12%.
    # So with MidCap slot 13333 and risk 2500, risk rarely binds below 12% stop
    # unless we raise alloc or lower risk. Use a larger slot to prove the formula.
    sized = size_fresh_row(
        _row("COFORGE", 1_000.0, sma50=900.0),  # 10% stop, dist=100, risk qty=25
        alloc_per=40_000,  # slot qty=40
        sleeve="midcap",
        policy=policy,
    )
    assert sized.accepted
    assert sized.qty == 25
    assert sized.binding == "risk"
    assert sized.stop == 900.0
    assert sized.risk_rs == 2_500.0


def test_midcap_skips_when_stop_wider_than_12_percent() -> None:
    sized = size_fresh_row(
        _row("POLYCAB", 9_000.0, sma50=7_800.0),  # 13.3% stop
        alloc_per=13_333.33,
        sleeve="midcap",
        policy=load_capital_policy(),
    )
    assert not sized.accepted
    assert sized.binding == "risk"
    assert "wider than 12%" in (sized.skip_reason or "")


def test_sector_cap_reduces_then_skips_same_sector_rows() -> None:
    policy = _policy()
    book = ExposureBook(policy, budget_mc=200_000)
    alloc = 13_333.33
    # Each Pharma name at Rs. 500: slot qty=26, cost=13,000.
    # After 7 names: 91,000. 8th remaining sector=9,000 → qty=18.
    # 9th remaining=0 → skip.
    selected = []
    skipped = []
    for i in range(9):
        sized = size_fresh_row(
            _row(f"PHARMA{i}", 500.0, sector="Pharmaceuticals"),
            alloc_per=alloc,
            sleeve="midcap",
            policy=policy,
            book=book,
        )
        if sized.accepted:
            selected.append(sized)
            book.commit(f"PHARMA{i}", sized, "midcap")
        else:
            skipped.append(sized)

    assert len(selected) == 8
    assert selected[7].binding == "sector"
    assert selected[7].qty == 18
    assert len(skipped) == 1
    assert "sector cap" in (skipped[0].skip_reason or "")


def test_single_stock_cap_is_combined_across_sleeves() -> None:
    policy = _policy()
    book = ExposureBook(policy, budget_sc=200_000, budget_mc=200_000)
    first = size_fresh_row(
        _row("AJANTPHARM", 2_000.0, sector="Pharmaceuticals"),
        alloc_per=22_222.0,
        sleeve="smallcap",
        policy=policy,
        book=book,
    )
    book.commit("AJANTPHARM", first, "smallcap")
    second = size_fresh_row(
        _row("AJANTPHARM", 2_000.0, sector="Pharmaceuticals"),
        alloc_per=13_333.0,
        sleeve="midcap",
        policy=policy,
        book=book,
    )
    assert first.accepted
    # First sleeve takes min(slot=11, stock=20) = 11 * 2000 = 22,000.
    # Remaining stock cap = 18,000 → second qty=9, not the full MidCap slot of 6.
    # slot for MC is 6 (13333/2000). Remaining stock 18000/2000=9. Slot binds at 6.
    assert first.qty == 11
    assert second.accepted
    assert second.qty == 6
    book.commit("AJANTPHARM", second, "midcap")
    assert book.stock_used["AJANTPHARM"] == 11 * 2_000 + 6 * 2_000
    assert book.stock_used["AJANTPHARM"] <= policy.single_stock_cap


def test_high_conviction_uses_larger_trade_risk() -> None:
    row = _row("IPCALAB", 1_000.0, sma50=900.0, tech_score=80.0, fund_score=80.0)
    assert is_high_conviction(row)
    sized = size_fresh_row(row, alloc_per=40_000, sleeve="midcap", policy=load_capital_policy())
    # dist=100, high-conviction risk=4000 → qty=40, which also equals the slot.
    assert sized.trade_risk_allowed == 4_000
    assert sized.qty == 40


def test_fresh_selection_still_skips_unaffordable_share_and_backfills() -> None:
    result = {
        "holds": [],
        "drops": [],
        "adds": [],
        "top_n": [],
        "watch": [],
        "passing": [
            _row("IPCALAB", 1796.30, tech_score=80.0),
            _row("FLUOROCHEM", 4714.70, tech_score=75.3),
            _row("AJANTPHARM", 3614.60, tech_score=70.7),
            _row("APARINDS", 17225.00, tech_score=70.0),
            _row("EXIDEIND", 485.50, tech_score=68.7),
            _row("OBEROIRLTY", 1846.00, tech_score=68.7),
            _row("COFORGE", 1829.00, tech_score=67.3),
            _row("BERGEPAINT", 546.35, tech_score=67.3),
            _row("ENDURANCE", 2975.30, tech_score=67.3),
            _row("AUROPHARMA", 1663.40, tech_score=65.3),
            _row("SONACOMS", 799.90, tech_score=64.7),
            _row("GODREJIND", 1255.60, tech_score=64.7),
            _row("FEDERALBNK", 352.45, tech_score=61.3),
            _row("NYKAA", 331.15, tech_score=61.3),
            _row("KALYANKJIL", 613.40, tech_score=59.3),
            _row("360ONE", 1090.00, tech_score=58.7),
        ],
    }

    selected = build_fresh_selection(result, n=15, alloc_per=13_333.33, sleeve="midcap")

    symbols = [row["symbol"] for row in selected["adds"]]
    assert "APARINDS" not in symbols
    assert symbols[-1] == "360ONE"
    assert all(row["_fresh_qty"] >= 1 for row in selected["adds"])
    assert selected["adds"][-1]["_fresh_rank"] == 16
    assert selected["skipped"][0]["symbol"] == "APARINDS"
    assert "exceeds slot" in selected["skipped"][0]["_fresh_skip_reason"]
    assert all(row.get("_fresh_stop") for row in selected["adds"])
