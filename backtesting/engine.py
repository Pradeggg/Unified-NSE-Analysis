"""Deterministic EOD backtest engine foundation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

import pandas as pd

from backtesting.portfolio import size_position
from backtesting.strategy_registry import get_strategy


@dataclass(frozen=True)
class BacktestConfig:
    strategy_id: str
    initial_capital: float = 100000.0
    allocation_pct: float = 1.0
    entry_policy: str = "next_open"
    exit_policy: str = "next_open"


@dataclass(frozen=True)
class Trade:
    symbol: str
    entry_date: date
    entry_price: float
    exit_date: date
    exit_price: float
    quantity: int
    pnl: float
    return_pct: float
    entry_reason: str
    exit_reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "entry_date": self.entry_date.isoformat(),
            "entry_price": self.entry_price,
            "exit_date": self.exit_date.isoformat(),
            "exit_price": self.exit_price,
            "quantity": self.quantity,
            "pnl": self.pnl,
            "return_pct": self.return_pct,
            "entry_reason": self.entry_reason,
            "exit_reason": self.exit_reason,
        }


@dataclass(frozen=True)
class BacktestResult:
    strategy_id: str
    trades: list[Trade] = field(default_factory=list)
    metrics: dict[str, float | int | None] = field(default_factory=dict)
    skipped: list[dict[str, Any]] = field(default_factory=list)


def _normalize_frame(df: pd.DataFrame) -> pd.DataFrame:
    out = df.rename(columns={col: col.strip().lower() for col in df.columns}).copy()
    aliases = {
        "timestamp": "date",
        "tottrdqty": "volume",
    }
    out = out.rename(columns={src: dst for src, dst in aliases.items() if src in out.columns})
    required = {"date", "symbol", "open", "high", "low", "close"}
    missing = sorted(required - set(out.columns))
    if missing:
        raise ValueError(f"Backtest data missing required columns: {', '.join(missing)}")
    if "volume" not in out.columns:
        out["volume"] = 0
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out = out[out["date"].notna()].copy()
    for col in ("open", "high", "low", "close", "volume"):
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out = out.dropna(subset=["symbol", "open", "high", "low", "close"])
    out["symbol"] = out["symbol"].astype(str).str.upper()
    return out.sort_values(["symbol", "date"]).reset_index(drop=True)


def compute_stage2_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute Stage 2 inputs from raw EOD OHLCV without lookahead.

    The first rule set is intentionally transparent:
    - SMA50/150/200 from each symbol's own historical closes.
    - 52-week high from rolling historical highs.
    - Relative strength as percentile rank of 63-session return on each date.
    - Stage 2 when close > SMA50 > SMA150 > SMA200 and close is within 25% of 52W high.
    """
    data = _normalize_frame(df)
    pieces: list[pd.DataFrame] = []
    for _, sdf in data.groupby("symbol", sort=True):
        out = sdf.copy()
        close = out["close"]
        high = out["high"]
        out["sma_50"] = close.rolling(window=50, min_periods=50).mean()
        out["sma_150"] = close.rolling(window=150, min_periods=150).mean()
        out["sma_200"] = close.rolling(window=200, min_periods=200).mean()
        out["high_52w"] = high.rolling(window=252, min_periods=50).max()
        out["return_63d"] = close.pct_change(63)
        pieces.append(out)

    if not pieces:
        return data

    enriched = pd.concat(pieces, ignore_index=True).sort_values(["date", "symbol"]).reset_index(drop=True)
    enriched["relative_strength"] = (
        enriched.groupby("date")["return_63d"]
        .rank(pct=True, method="average")
        .mul(100)
    )
    # Single-symbol backtests would otherwise always rank at 100 after enough
    # history; before 63D return exists, use a neutral score.
    enriched["relative_strength"] = enriched["relative_strength"].fillna(50)

    close = enriched["close"]
    stage2_mask = (
        enriched["sma_50"].notna()
        & enriched["sma_150"].notna()
        & enriched["sma_200"].notna()
        & (close > enriched["sma_50"])
        & (enriched["sma_50"] > enriched["sma_150"])
        & (enriched["sma_150"] > enriched["sma_200"])
        & (
            enriched["high_52w"].isna()
            | (close >= enriched["high_52w"] * 0.75)
        )
        & (enriched["relative_strength"] >= 70)
    )
    enriched["stage"] = "Stage 1"
    enriched.loc[stage2_mask, "stage"] = "Stage 2"
    return enriched.sort_values(["symbol", "date"]).reset_index(drop=True)


def _is_stage2_entry(row: pd.Series) -> bool:
    stage = str(row.get("stage", "")).strip().lower()
    stage_ok = stage in {"stage 2", "stage2", "2", "uptrend"}
    rs = row.get("relative_strength")
    try:
        rs_ok = pd.isna(rs) or float(rs) >= 70
    except Exception:
        rs_ok = True
    sma = row.get("sma_50")
    try:
        sma_ok = pd.isna(sma) or float(row["close"]) > float(sma)
    except Exception:
        sma_ok = True
    return stage_ok and rs_ok and sma_ok


def _is_stage2_exit(row: pd.Series) -> bool:
    stage = str(row.get("stage", "")).strip().lower()
    if stage and stage not in {"stage 2", "stage2", "2", "uptrend"}:
        return True
    sma = row.get("sma_50")
    try:
        if pd.notna(sma) and float(row["close"]) < float(sma):
            return True
    except Exception:
        pass
    return False


def _metrics(trades: list[Trade], initial_capital: float) -> dict[str, float | int | None]:
    pnl = sum(trade.pnl for trade in trades)
    wins = [trade for trade in trades if trade.pnl > 0]
    losses = [trade for trade in trades if trade.pnl < 0]
    return {
        "trade_count": len(trades),
        "total_pnl": round(pnl, 4),
        "ending_capital": round(initial_capital + pnl, 4),
        "total_return_pct": round((pnl / initial_capital) * 100, 4) if initial_capital else None,
        "win_rate_pct": round((len(wins) / len(trades)) * 100, 4) if trades else None,
        "avg_winner": round(sum(t.pnl for t in wins) / len(wins), 4) if wins else None,
        "avg_loser": round(sum(t.pnl for t in losses) / len(losses), 4) if losses else None,
    }


def run_backtest(df: pd.DataFrame, config: BacktestConfig) -> BacktestResult:
    strategy = get_strategy(config.strategy_id)
    if strategy.id != "stage2":
        raise ValueError("Only stage2 is executable in the current engine slice")

    data = _normalize_frame(df)
    if strategy.id == "stage2" and (
        "stage" not in data.columns
        or "relative_strength" not in data.columns
        or "sma_50" not in data.columns
    ):
        data = compute_stage2_features(data)
    cash = float(config.initial_capital)
    trades: list[Trade] = []
    skipped: list[dict[str, Any]] = []

    for symbol, sdf in data.groupby("symbol", sort=True):
        rows = list(sdf.reset_index(drop=True).iterrows())
        position: dict[str, Any] | None = None
        pending_entry = False
        pending_exit = False

        for idx, row in rows:
            current = row
            current_date = current["date"].date()

            if pending_exit and position is not None:
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
                        entry_reason="stage2_entry_next_open",
                        exit_reason="stage2_exit_next_open",
                    )
                )
                position = None
                pending_exit = False

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
                    }
                pending_entry = False

            is_last = idx == len(rows) - 1
            if position is not None and _is_stage2_exit(current):
                if is_last:
                    exit_price = float(current["close"])
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
                            entry_reason="stage2_entry_next_open",
                            exit_reason="stage2_exit_close_final_bar",
                        )
                    )
                    position = None
                else:
                    pending_exit = True
            elif position is None and _is_stage2_entry(current) and not is_last:
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
                    entry_reason="stage2_entry_next_open",
                    exit_reason="final_bar_close",
                )
            )

    return BacktestResult(
        strategy_id=strategy.id,
        trades=trades,
        metrics=_metrics(trades, float(config.initial_capital)),
        skipped=skipped,
    )
