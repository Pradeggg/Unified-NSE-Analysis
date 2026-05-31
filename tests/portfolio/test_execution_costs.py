from __future__ import annotations

import pandas as pd
import pytest

from portfolio.engine.execution_models import CostModel, NextOpenExecutionModel
from portfolio.engine.order_types import Order, OrderSide, OrderType


def _order(order_type: OrderType, side: OrderSide = OrderSide.BUY, **kwargs) -> Order:
    quantity = kwargs.pop("quantity", 10)
    return Order(
        order_id="o1",
        symbol="AAA",
        side=side,
        quantity=quantity,
        order_type=order_type,
        submitted_at="2025-01-01",
        strategy_id="s1",
        reason="test",
        **kwargs,
    )


def _bar() -> pd.Series:
    return pd.Series(
        {
            "date": "2025-01-02",
            "open": 100.0,
            "high": 110.0,
            "low": 95.0,
            "close": 108.0,
            "volume": 1000,
        }
    )


def test_cost_model_combines_slippage_fees_and_tax():
    model = NextOpenExecutionModel(
        cost_model=CostModel(
            brokerage_bps=10.0,
            transaction_tax_bps=5.0,
            slippage_bps=20.0,
            fixed_fee=2.0,
        )
    )

    fill = model.try_fill(_order(OrderType.MARKET_NEXT_OPEN), _bar())

    assert fill is not None
    assert fill.price == 100.2
    assert fill.fees == 3.503
    assert fill.slippage == 2.0


def test_market_on_close_fills_at_close_with_sell_slippage():
    model = NextOpenExecutionModel(cost_model=CostModel(slippage_bps=10.0))

    fill = model.try_fill(_order(OrderType.MARKET_ON_CLOSE, OrderSide.SELL), _bar())

    assert fill is not None
    assert fill.price == 107.892


def test_limit_order_requires_price_touch():
    model = NextOpenExecutionModel()

    assert model.try_fill(_order(OrderType.LIMIT, limit_price=94.0), _bar()) is None
    fill = model.try_fill(_order(OrderType.LIMIT, limit_price=96.0), _bar())

    assert fill is not None
    assert fill.price == 96.0


def test_stop_limit_requires_stop_and_limit_touch():
    model = NextOpenExecutionModel()

    fill = model.try_fill(
        _order(OrderType.STOP_LIMIT, stop_price=106.0, limit_price=107.0),
        _bar(),
    )

    assert fill is not None
    assert fill.price == 107.0


def test_legacy_constructor_keeps_brokerage_and_slippage_behavior():
    model = NextOpenExecutionModel(brokerage_bps=5.0, slippage_bps=10.0)

    fill = model.try_fill(_order(OrderType.MARKET_NEXT_OPEN), _bar())

    assert fill is not None
    assert fill.price == 100.1
    assert fill.fees == 0.5005
    assert fill.slippage == 1.0


def test_stop_order_sell_requires_stop_touch():
    model = NextOpenExecutionModel()

    assert model.try_fill(_order(OrderType.STOP, OrderSide.SELL, stop_price=94.0), _bar()) is None
    fill = model.try_fill(_order(OrderType.STOP, OrderSide.SELL, stop_price=96.0), _bar())

    assert fill is not None
    assert fill.price == 96.0


@pytest.mark.parametrize(
    "order_type",
    [OrderType.TRAILING_STOP, OrderType.BRACKET, OrderType.CANCEL_REPLACE],
)
def test_pt1_unsupported_order_types_do_not_fill(order_type: OrderType):
    assert NextOpenExecutionModel().try_fill(_order(order_type), _bar()) is None


def test_max_participation_pct_rejects_oversized_order():
    order = _order(OrderType.MARKET_NEXT_OPEN, quantity=101)
    model = NextOpenExecutionModel(cost_model=CostModel(max_participation_pct=10.0))

    assert model.try_fill(order, _bar()) is None


def test_fixed_slippage_applies_per_share_by_side():
    model = NextOpenExecutionModel(cost_model=CostModel(fixed_slippage=0.25))

    buy = model.try_fill(_order(OrderType.MARKET_NEXT_OPEN), _bar())
    sell = model.try_fill(_order(OrderType.MARKET_NEXT_OPEN, OrderSide.SELL), _bar())

    assert buy is not None
    assert sell is not None
    assert buy.price == 100.25
    assert sell.price == 99.75
    assert buy.slippage == 2.5
    assert sell.slippage == 2.5
