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


def test_limit_gap_through_uses_open_when_more_conservative():
    buy_bar = _bar()
    buy_bar["open"] = 90.0
    buy_bar["high"] = 101.0
    buy_bar["low"] = 89.0
    buy_bar["close"] = 95.0
    sell_bar = _bar()
    sell_bar["open"] = 110.0
    sell_bar["high"] = 112.0
    sell_bar["low"] = 99.0
    sell_bar["close"] = 105.0
    model = NextOpenExecutionModel()

    buy = model.try_fill(_order(OrderType.LIMIT, limit_price=100.0), buy_bar)
    sell = model.try_fill(_order(OrderType.LIMIT, OrderSide.SELL, limit_price=100.0), sell_bar)

    assert buy is not None
    assert sell is not None
    assert buy.price == 90.0
    assert sell.price == 110.0


def test_stop_limit_requires_stop_and_limit_touch():
    model = NextOpenExecutionModel()

    fill = model.try_fill(
        _order(OrderType.STOP_LIMIT, stop_price=106.0, limit_price=107.0),
        _bar(),
    )

    assert fill is not None
    assert fill.price == 107.0


def test_stop_limit_gap_through_uses_open_when_stop_active_at_open():
    buy_bar = _bar()
    buy_bar["open"] = 110.0
    buy_bar["high"] = 115.0
    buy_bar["low"] = 105.0
    buy_bar["close"] = 112.0
    sell_bar = _bar()
    sell_bar["open"] = 90.0
    sell_bar["high"] = 95.0
    sell_bar["low"] = 85.0
    sell_bar["close"] = 88.0
    model = NextOpenExecutionModel()

    buy = model.try_fill(_order(OrderType.STOP_LIMIT, stop_price=100.0, limit_price=112.0), buy_bar)
    sell = model.try_fill(
        _order(OrderType.STOP_LIMIT, OrderSide.SELL, stop_price=100.0, limit_price=88.0),
        sell_bar,
    )

    assert buy is not None
    assert sell is not None
    assert buy.price == 110.0
    assert sell.price == 90.0


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


def test_sell_stop_gap_down_fills_at_open_with_slippage_not_stop_price():
    bar = _bar()
    bar["open"] = 90.0
    bar["high"] = 95.0
    bar["low"] = 85.0
    bar["close"] = 88.0
    model = NextOpenExecutionModel(cost_model=CostModel(slippage_bps=10.0))

    fill = model.try_fill(_order(OrderType.STOP, OrderSide.SELL, stop_price=100.0), bar)

    assert fill is not None
    assert fill.price == 89.91


def test_buy_stop_gap_up_fills_at_open_not_stop_price():
    bar = _bar()
    bar["open"] = 110.0
    bar["high"] = 115.0
    bar["low"] = 108.0
    bar["close"] = 112.0

    fill = NextOpenExecutionModel().try_fill(_order(OrderType.STOP, stop_price=100.0), bar)

    assert fill is not None
    assert fill.price == 110.0


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


def test_full_participation_cap_rejects_quantity_greater_than_volume():
    order = _order(OrderType.MARKET_NEXT_OPEN, quantity=1001)
    model = NextOpenExecutionModel(cost_model=CostModel(max_participation_pct=100.0))

    assert model.try_fill(order, _bar()) is None


def test_full_participation_cap_rejects_zero_volume():
    bar = _bar()
    bar["volume"] = 0
    model = NextOpenExecutionModel(cost_model=CostModel(max_participation_pct=100.0))

    assert model.try_fill(_order(OrderType.MARKET_NEXT_OPEN), bar) is None


def test_negative_infinity_participation_cap_is_invalid():
    model = NextOpenExecutionModel(
        cost_model=CostModel(max_participation_pct=float("-inf"))
    )

    assert model.try_fill(_order(OrderType.MARKET_NEXT_OPEN), _bar()) is None


def test_invalid_ohlc_bar_does_not_fill_market_order():
    bar = _bar()
    bar["high"] = 99.0

    assert NextOpenExecutionModel().try_fill(_order(OrderType.MARKET_NEXT_OPEN), bar) is None


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
