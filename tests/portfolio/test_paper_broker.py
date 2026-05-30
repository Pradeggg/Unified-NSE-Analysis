from __future__ import annotations

import pandas as pd
import pytest

from portfolio.engine.execution_models import NextOpenExecutionModel
from portfolio.engine.order_types import Order, OrderSide, OrderStatus, OrderType
from portfolio.engine.portfolio_account import PortfolioAccount, PortfolioAccountError


def _order(
    *,
    order_id: str = "o1",
    side: OrderSide = OrderSide.BUY,
    quantity: int = 10,
    submitted_at: str = "2025-01-01",
) -> Order:
    return Order(
        order_id=order_id,
        symbol="AAA",
        side=side,
        quantity=quantity,
        order_type=OrderType.MARKET_NEXT_OPEN,
        submitted_at=submitted_at,
        strategy_id="s1",
        reason="fixture signal",
    )


def _bar(open_price: float = 100.0) -> pd.Series:
    return pd.Series(
        {
            "date": pd.Timestamp("2025-01-02"),
            "open": open_price,
            "high": 105.0,
            "low": 99.0,
            "close": 104.0,
        }
    )


def test_buy_fill_updates_cash_position_and_order_status():
    account = PortfolioAccount(initial_capital=10_000.0)
    order = _order(quantity=10)
    fill = NextOpenExecutionModel().try_fill(order, _bar(100.0))

    assert fill is not None
    account.submit_order(order)
    account.apply_fill(fill)

    assert account.cash == 9_000.0
    assert account.positions["AAA"].quantity == 10
    assert account.positions["AAA"].avg_price == 100.0
    assert account.orders["o1"].status == OrderStatus.FILLED
    assert account.fills == [fill]


def test_sell_fill_updates_cash_position_and_realized_pnl():
    account = PortfolioAccount(initial_capital=10_000.0)
    buy = _order(order_id="buy", quantity=10)
    sell = _order(order_id="sell", side=OrderSide.SELL, quantity=4)

    account.submit_order(buy)
    account.apply_fill(NextOpenExecutionModel().try_fill(buy, _bar(100.0)))
    account.submit_order(sell)
    account.apply_fill(NextOpenExecutionModel().try_fill(sell, _bar(110.0)))

    assert account.cash == 9_440.0
    assert account.positions["AAA"].quantity == 6
    assert account.positions["AAA"].avg_price == 100.0
    assert account.realized_pnl == 40.0


def test_insufficient_cash_rejects_buy_order_cleanly():
    account = PortfolioAccount(initial_capital=500.0)
    order = _order(quantity=10)
    fill = NextOpenExecutionModel().try_fill(order, _bar(100.0))

    account.submit_order(order)
    with pytest.raises(PortfolioAccountError, match="insufficient cash"):
        account.apply_fill(fill)

    assert account.cash == 500.0
    assert account.positions == {}
    assert account.orders["o1"].status == OrderStatus.REJECTED


def test_oversell_rejects_sell_order_cleanly():
    account = PortfolioAccount(initial_capital=10_000.0)
    order = _order(side=OrderSide.SELL, quantity=1)
    fill = NextOpenExecutionModel().try_fill(order, _bar(100.0))

    account.submit_order(order)
    with pytest.raises(PortfolioAccountError, match="cannot sell more than held"):
        account.apply_fill(fill)

    assert account.cash == 10_000.0
    assert account.positions == {}
    assert account.orders["o1"].status == OrderStatus.REJECTED


def test_non_positive_quantity_is_rejected_before_account_mutation():
    account = PortfolioAccount(initial_capital=10_000.0)
    order = _order(quantity=0)

    with pytest.raises(PortfolioAccountError, match="quantity must be positive"):
        account.submit_order(order)

    assert account.orders == {}
    assert NextOpenExecutionModel().try_fill(order, _bar(100.0)) is None


@pytest.mark.parametrize("price", [0.0, -1.0, float("nan")])
def test_missing_or_invalid_fill_price_is_rejected(price: float):
    account = PortfolioAccount(initial_capital=10_000.0)
    order = _order()
    fill = NextOpenExecutionModel().try_fill(order, _bar(100.0))
    assert fill is not None
    bad_fill = fill.with_price(price)

    account.submit_order(order)
    with pytest.raises(PortfolioAccountError, match="fill price must be positive"):
        account.apply_fill(bad_fill)

    assert account.cash == 10_000.0
    assert account.positions == {}
    assert account.orders["o1"].status == OrderStatus.REJECTED


def test_missing_fill_price_is_rejected_cleanly():
    account = PortfolioAccount(initial_capital=10_000.0)
    order = _order()
    fill = NextOpenExecutionModel().try_fill(order, _bar(100.0))
    assert fill is not None
    raw_fill = fill.as_dict()
    raw_fill.pop("price")
    raw_fill.pop("fill_price")

    account.submit_order(order)
    with pytest.raises(PortfolioAccountError, match="fill price must be positive"):
        account.apply_fill(raw_fill)

    assert account.cash == 10_000.0
    assert account.positions == {}
    assert account.orders["o1"].status == OrderStatus.REJECTED


def test_slippage_and_fees_are_deterministic_by_side():
    model = NextOpenExecutionModel(slippage_bps=10.0, brokerage_bps=5.0)

    buy_fill = model.try_fill(_order(side=OrderSide.BUY, quantity=10), _bar(100.0))
    sell_fill = model.try_fill(_order(order_id="o2", side=OrderSide.SELL, quantity=10), _bar(100.0))

    assert buy_fill is not None
    assert sell_fill is not None
    assert buy_fill.price == 100.1
    assert buy_fill.slippage == 1.0
    assert buy_fill.fees == 0.5005
    assert sell_fill.price == 99.9
    assert sell_fill.slippage == 1.0
    assert sell_fill.fees == 0.4995


def test_nav_marks_positions_against_provided_prices():
    account = PortfolioAccount(initial_capital=10_000.0)
    order = _order(quantity=10)

    account.submit_order(order)
    account.apply_fill(NextOpenExecutionModel().try_fill(order, _bar(100.0)))
    nav = account.mark_to_market({"AAA": 105.0}, as_of="2025-01-02")

    assert nav == {
        "timestamp": "2025-01-02",
        "cash": 9_000.0,
        "market_value": 1_050.0,
        "nav": 10_050.0,
        "realized_pnl": 0.0,
        "open_positions": 1,
    }
    assert account.equity({"AAA": 105.0}) == 10_050.0
