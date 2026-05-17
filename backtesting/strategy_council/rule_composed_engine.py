"""Executable backtest path for ``rule_composed`` strategies.

The Strategy Council's :mod:`backtesting.strategy_council.strategy_generator`
module produces :class:`StrategySpec` objects whose ``params`` contain a list of
*atom ids* drawn from the registry. This module turns those atoms into a real
EOD backtest by:

* Pre-computing the indicator columns each atom needs (EMA, RSI, MACD,
  volume-SMA).
* AND-combining the entry atoms into a single per-bar signal.
* Evaluating exit atoms (``profit_target``, ``stop_loss``, ``time_stop``,
  ``trailing_stop``) against the open position.
* Following the same next-open execution model and capital sizing as the
  ``stage2`` engine path so iteration results remain comparable.

Atoms with unknown ids are silently skipped, so the runner can tolerate
LLM-injected ``StrategySpec.params`` that happen to reference atoms outside
this module's registry.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from backtesting.engine import BacktestConfig, BacktestResult, Trade, _metrics, _normalize_frame
from backtesting.portfolio import size_position
from backtesting.strategy_council.types import StrategySpec


def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False, min_periods=period).mean()


def _rsi(series: pd.Series, period: int) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0.0, float("nan"))
    return 100.0 - (100.0 / (1.0 + rs))


def _macd(series: pd.Series, fast: int, slow: int, signal: int) -> tuple[pd.Series, pd.Series]:
    fast_ema = series.ewm(span=fast, adjust=False, min_periods=fast).mean()
    slow_ema = series.ewm(span=slow, adjust=False, min_periods=slow).mean()
    macd_line = fast_ema - slow_ema
    signal_line = macd_line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    return macd_line, signal_line


def _enrich_with_indicators(df: pd.DataFrame, spec: StrategySpec) -> pd.DataFrame:
    out = df.copy()
    entry_params = dict(spec.params.get("entry_atom_params") or {})
    entry_atoms = list(spec.params.get("entry_atoms") or [])

    for atom in entry_atoms:
        params = entry_params.get(atom, {})
        if atom == "ema_bullish":
            period = int(params.get("period", 20))
            out[f"_ema_{period}"] = _ema(out["close"], period)
        elif atom == "rsi_oversold":
            period = int(params.get("period", 14))
            out[f"_rsi_{period}"] = _rsi(out["close"], period)
        elif atom == "volume_spike":
            period = int(params.get("period", 20))
            out[f"_volsma_{period}"] = out["volume"].rolling(window=period, min_periods=period).mean()
        elif atom == "macd_cross":
            fast = int(params.get("fast", 12))
            slow = int(params.get("slow", 26))
            signal = int(params.get("signal", 9))
            macd_line, signal_line = _macd(out["close"], fast, slow, signal)
            out[f"_macd_line_{fast}_{slow}"] = macd_line
            out[f"_macd_signal_{fast}_{slow}_{signal}"] = signal_line
    return out


@dataclass
class _EntryEval:
    entry_atoms: list[str]
    entry_params: dict[str, dict[str, Any]]

    def is_entry(self, row: pd.Series) -> bool:
        if not self.entry_atoms:
            return False
        for atom in self.entry_atoms:
            params = self.entry_params.get(atom, {})
            if not _atom_entry_true(atom, params, row):
                return False
        return True


def _atom_entry_true(atom: str, params: dict[str, Any], row: pd.Series) -> bool:
    close = row.get("close")
    if pd.isna(close):
        return False
    if atom == "ema_bullish":
        period = int(params.get("period", 20))
        ema = row.get(f"_ema_{period}")
        return bool(pd.notna(ema) and close > ema)
    if atom == "rsi_oversold":
        period = int(params.get("period", 14))
        threshold = float(params.get("threshold", 30))
        rsi = row.get(f"_rsi_{period}")
        return bool(pd.notna(rsi) and rsi < threshold)
    if atom == "volume_spike":
        period = int(params.get("period", 20))
        multiplier = float(params.get("multiplier", 1.5))
        volsma = row.get(f"_volsma_{period}")
        volume = row.get("volume")
        return bool(pd.notna(volsma) and pd.notna(volume) and volume > volsma * multiplier)
    if atom == "macd_cross":
        fast = int(params.get("fast", 12))
        slow = int(params.get("slow", 26))
        signal = int(params.get("signal", 9))
        macd_line = row.get(f"_macd_line_{fast}_{slow}")
        signal_line = row.get(f"_macd_signal_{fast}_{slow}_{signal}")
        return bool(pd.notna(macd_line) and pd.notna(signal_line) and macd_line > signal_line)
    return False


@dataclass
class _ExitEval:
    exit_atoms: list[str]
    exit_params: dict[str, dict[str, Any]]

    def should_exit(
        self,
        *,
        current_close: float,
        entry_price: float,
        bars_held: int,
        running_high: float,
    ) -> str | None:
        for atom in self.exit_atoms:
            params = self.exit_params.get(atom, {})
            reason = _atom_exit_reason(
                atom,
                params,
                current_close=current_close,
                entry_price=entry_price,
                bars_held=bars_held,
                running_high=running_high,
            )
            if reason:
                return reason
        return None


def _atom_exit_reason(
    atom: str,
    params: dict[str, Any],
    *,
    current_close: float,
    entry_price: float,
    bars_held: int,
    running_high: float,
) -> str | None:
    if entry_price <= 0:
        return None
    ret_pct = ((current_close / entry_price) - 1.0) * 100.0
    if atom == "profit_target":
        pct = float(params.get("pct", 2.0))
        if ret_pct >= pct:
            return f"profit_target_{pct}pct"
    elif atom == "stop_loss":
        pct = float(params.get("pct", 1.0))
        if ret_pct <= -pct:
            return f"stop_loss_{pct}pct"
    elif atom == "time_stop":
        days = int(params.get("days", 5))
        if bars_held >= days:
            return f"time_stop_{days}d"
    elif atom == "trailing_stop":
        pct = float(params.get("pct", 1.5))
        if running_high > 0 and ((current_close / running_high) - 1.0) * 100.0 <= -pct:
            return f"trailing_stop_{pct}pct"
    return None


def run_rule_composed_backtest(df: pd.DataFrame, spec: StrategySpec, config: BacktestConfig) -> BacktestResult:
    data = _normalize_frame(df)
    data = _enrich_with_indicators(data, spec)

    entry_eval = _EntryEval(
        entry_atoms=list(spec.params.get("entry_atoms") or []),
        entry_params=dict(spec.params.get("entry_atom_params") or {}),
    )
    exit_eval = _ExitEval(
        exit_atoms=list(spec.params.get("exit_atoms") or []),
        exit_params=dict(spec.params.get("exit_atom_params") or {}),
    )

    cash = float(config.initial_capital)
    trades: list[Trade] = []
    skipped: list[dict[str, Any]] = []

    for symbol, sdf in data.groupby("symbol", sort=True):
        rows = list(sdf.reset_index(drop=True).iterrows())
        position: dict[str, Any] | None = None
        pending_entry = False
        pending_exit_reason: str | None = None
        running_high = 0.0

        for idx, row in rows:
            current = row
            current_date = current["date"].date()

            if pending_exit_reason and position is not None:
                exit_price = float(current["open"])
                pnl = round((exit_price - position["entry_price"]) * position["quantity"], 6)
                cash += position["quantity"] * exit_price
                trades.append(
                    Trade(
                        symbol=symbol,
                        entry_date=position["entry_date"],
                        entry_price=position["entry_price"],
                        exit_date=current_date,
                        exit_price=exit_price,
                        quantity=position["quantity"],
                        pnl=pnl,
                        return_pct=round(((exit_price / position["entry_price"]) - 1) * 100, 6),
                        entry_reason="rule_composed_entry_next_open",
                        exit_reason=f"{pending_exit_reason}_next_open",
                    )
                )
                position = None
                pending_exit_reason = None
                running_high = 0.0

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
                    running_high = entry_price
                pending_entry = False

            if position is not None:
                position["bars_held"] += 1
                close_today = float(current["close"]) if pd.notna(current["close"]) else position["entry_price"]
                if close_today > running_high:
                    running_high = close_today
                reason = exit_eval.should_exit(
                    current_close=close_today,
                    entry_price=position["entry_price"],
                    bars_held=position["bars_held"],
                    running_high=running_high,
                )
                is_last = idx == len(rows) - 1
                if reason and is_last:
                    exit_price = close_today
                    pnl = round((exit_price - position["entry_price"]) * position["quantity"], 6)
                    trades.append(
                        Trade(
                            symbol=symbol,
                            entry_date=position["entry_date"],
                            entry_price=position["entry_price"],
                            exit_date=current_date,
                            exit_price=exit_price,
                            quantity=position["quantity"],
                            pnl=pnl,
                            return_pct=round(((exit_price / position["entry_price"]) - 1) * 100, 6),
                            entry_reason="rule_composed_entry_next_open",
                            exit_reason=f"{reason}_close_final_bar",
                        )
                    )
                    position = None
                elif reason:
                    pending_exit_reason = reason
            elif not pending_entry and entry_eval.is_entry(current) and idx != len(rows) - 1:
                pending_entry = True

        if position is not None:
            final = sdf.iloc[-1]
            exit_price = float(final["close"])
            pnl = round((exit_price - position["entry_price"]) * position["quantity"], 6)
            trades.append(
                Trade(
                    symbol=symbol,
                    entry_date=position["entry_date"],
                    entry_price=position["entry_price"],
                    exit_date=final["date"].date(),
                    exit_price=exit_price,
                    quantity=position["quantity"],
                    pnl=pnl,
                    return_pct=round(((exit_price / position["entry_price"]) - 1) * 100, 6),
                    entry_reason="rule_composed_entry_next_open",
                    exit_reason="final_bar_close",
                )
            )

    return BacktestResult(
        strategy_id=spec.strategy_id,
        trades=trades,
        metrics=_metrics(trades, float(config.initial_capital)),
        skipped=skipped,
    )


__all__ = ["run_rule_composed_backtest"]
