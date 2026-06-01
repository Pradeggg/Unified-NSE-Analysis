"""Deterministic Strategy Council candidate runner."""

from __future__ import annotations

import pandas as pd

from backtesting.engine import BacktestConfig, BacktestResult, Trade, _metrics, _normalize_frame, run_backtest
from backtesting.patterns import compute_pattern_features, detect_vcp
from backtesting.portfolio import size_position
from backtesting.strategy_council.rule_composed_engine import run_rule_composed_backtest
from backtesting.strategy_council.strategy_generator import COMPOSED_STRATEGY_ID
from backtesting.strategy_council.types import BacktestSliceResult, StrategySpec


def run_strategy_spec_on_split(
    df: pd.DataFrame,
    spec: StrategySpec,
    *,
    split_name: str,
    initial_capital: float,
) -> BacktestSliceResult:
    if spec.strategy_id == COMPOSED_STRATEGY_ID:
        result = run_rule_composed_backtest(
            df,
            spec,
            BacktestConfig(strategy_id=spec.strategy_id, initial_capital=initial_capital),
        )
        metrics = dict(result.metrics)
        metrics["symbol_attribution"] = _symbol_attribution_from_trades(result.trades, initial_capital=initial_capital)
        return BacktestSliceResult(
            split=split_name,
            strategy_id=spec.strategy_id,
            horizon_days=spec.horizon_days,
            metrics=metrics,
            trade_count=int(metrics.get("trade_count") or 0),
        )

    if spec.strategy_id in {"52w_high", "vcp"}:
        result = _run_signal_backtest(
            df,
            spec,
            BacktestConfig(strategy_id=spec.strategy_id, initial_capital=initial_capital),
        )
        metrics = dict(result.metrics)
        metrics["symbol_attribution"] = _symbol_attribution_from_trades(result.trades, initial_capital=initial_capital)
        return BacktestSliceResult(
            split=split_name,
            strategy_id=spec.strategy_id,
            horizon_days=spec.horizon_days,
            metrics=metrics,
            trade_count=int(metrics.get("trade_count") or 0),
        )

    if spec.strategy_id != "stage2":
        metrics = {
            "trade_count": 0,
            "total_return_pct": None,
            "total_pnl": 0,
            "unsupported_strategy": spec.strategy_id,
        }
        return BacktestSliceResult(
            split=split_name,
            strategy_id=spec.strategy_id,
            horizon_days=spec.horizon_days,
            metrics=metrics,
            trade_count=0,
        )

    result = run_backtest(
        df,
        BacktestConfig(strategy_id=spec.strategy_id, initial_capital=initial_capital),
    )
    metrics = dict(result.metrics)
    metrics["symbol_attribution"] = _symbol_attribution_from_trades(result.trades, initial_capital=initial_capital)
    return BacktestSliceResult(
        split=split_name,
        strategy_id=spec.strategy_id,
        horizon_days=spec.horizon_days,
        metrics=metrics,
        trade_count=int(result.metrics.get("trade_count") or 0),
    )


def _run_signal_backtest(df: pd.DataFrame, spec: StrategySpec, config: BacktestConfig) -> BacktestResult:
    data = _prepare_signal_features(df, spec)
    cash = float(config.initial_capital)
    trades: list[Trade] = []
    skipped: list[dict[str, object]] = []

    for symbol, sdf in data.groupby("symbol", sort=True):
        rows = list(sdf.reset_index(drop=True).iterrows())
        position: dict[str, object] | None = None
        pending_entry = False

        for idx, row in rows:
            current = row
            current_date = current["date"].date()

            if pending_entry and position is None:
                entry_price = float(current["open"])
                sized = size_position(cash=cash, price=entry_price, allocation_pct=config.allocation_pct)
                if sized.quantity <= 0:
                    skipped.append(
                        {
                            "symbol": symbol,
                            "date": current_date.isoformat(),
                            "reason": "insufficient_cash_for_position",
                        }
                    )
                else:
                    cash = sized.remaining_cash
                    position = {
                        "entry_date": current_date,
                        "entry_price": entry_price,
                        "quantity": sized.quantity,
                        "bars_held": 0,
                    }
                pending_entry = False

            is_last = idx == len(rows) - 1
            if position is not None:
                position["bars_held"] = int(position["bars_held"]) + 1
                close_today = float(current["close"])
                if _should_exit_signal_strategy(current, spec, position["entry_price"], int(position["bars_held"])) or is_last:
                    exit_price = close_today if is_last else float(current["open"])
                    pnl = round((exit_price - float(position["entry_price"])) * int(position["quantity"]), 6)
                    cash += int(position["quantity"]) * exit_price
                    trades.append(
                        Trade(
                            symbol=symbol,
                            entry_date=position["entry_date"],
                            entry_price=float(position["entry_price"]),
                            exit_date=current_date,
                            exit_price=exit_price,
                            quantity=int(position["quantity"]),
                            pnl=pnl,
                            return_pct=round(((exit_price / float(position["entry_price"])) - 1) * 100, 6),
                            entry_reason=f"{spec.strategy_id}_entry_next_open",
                            exit_reason="signal_exit" if not is_last else "final_bar_close",
                        )
                    )
                    position = None
            elif not pending_entry and not is_last and _is_signal_entry(sdf, idx, current, spec):
                pending_entry = True

    return BacktestResult(
        strategy_id=spec.strategy_id,
        trades=trades,
        metrics=_metrics(trades, float(config.initial_capital)),
        skipped=skipped,
    )


def _prepare_signal_features(df: pd.DataFrame, spec: StrategySpec) -> pd.DataFrame:
    data = _normalize_frame(df)
    pieces: list[pd.DataFrame] = []
    for _, sdf in data.groupby("symbol", sort=True):
        features = compute_pattern_features(sdf)
        features["symbol"] = sdf["symbol"].iloc[0]
        pieces.append(features)
    if not pieces:
        return data
    return pd.concat(pieces, ignore_index=True).sort_values(["symbol", "date"]).reset_index(drop=True)


def _is_signal_entry(symbol_frame: pd.DataFrame, idx: int, row: pd.Series, spec: StrategySpec) -> bool:
    if spec.strategy_id == "52w_high":
        high_52w = row.get("high_52w")
        rel_volume = row.get("rel_volume")
        close = row.get("close")
        return bool(
            pd.notna(high_52w)
            and pd.notna(close)
            and float(close) >= float(high_52w) * 0.98
            and float(rel_volume or 0) >= 1.1
        )
    if spec.strategy_id == "vcp":
        signal = detect_vcp(symbol_frame.iloc[: idx + 1], symbol=str(row.get("symbol") or ""), min_confidence=70)[0]
        return signal.direction == "bullish" and float(signal.confidence) >= 70
    return False


def _should_exit_signal_strategy(row: pd.Series, spec: StrategySpec, entry_price: object, bars_held: int) -> bool:
    if bars_held >= int(spec.horizon_days):
        return True
    close = float(row.get("close") or 0)
    if float(entry_price or 0) <= 0:
        return False
    if spec.strategy_id == "52w_high":
        high_52w = row.get("high_52w")
        return bool(pd.notna(high_52w) and close < float(high_52w) * 0.95)
    if spec.strategy_id == "vcp":
        return close < float(entry_price) * 0.94
    return False


def _symbol_attribution_from_trades(trades: list, *, initial_capital: float) -> dict[str, dict[str, float | int | None]]:
    by_symbol: dict[str, list] = {}
    for trade in trades:
        by_symbol.setdefault(str(trade.symbol).upper(), []).append(trade)
    attribution: dict[str, dict[str, float | int | None]] = {}
    for symbol, symbol_trades in by_symbol.items():
        pnl = sum(float(trade.pnl) for trade in symbol_trades)
        wins = [trade for trade in symbol_trades if float(trade.pnl) > 0]
        attribution[symbol] = {
            "trade_count": len(symbol_trades),
            "pnl": round(pnl, 4),
            "return_pct": round((pnl / initial_capital) * 100, 4) if initial_capital else None,
            "win_rate": round(len(wins) / len(symbol_trades), 4) if symbol_trades else None,
        }
    return attribution
