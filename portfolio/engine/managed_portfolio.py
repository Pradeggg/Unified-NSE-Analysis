from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class ManagedPortfolioPolicy:
    start_date: str = "2025-01-01"
    initial_capital: float = 1_000_000.0
    max_gross_exposure_pct: float = 95.0
    max_single_stock_pct: float = 10.0
    max_sector_pct: float = 25.0
    risk_per_new_position_pct: float = 1.0
    risk_per_add_pct: float = 0.5
    max_portfolio_open_risk_pct: float = 8.0
    max_positions: int = 15
    initial_entry_pct_of_target: float = 50.0
    first_add_pct_of_target: float = 25.0
    second_add_pct_of_target: float = 25.0
    trim_when_position_pct_above: float = 12.0
    trim_to_position_pct: float = 8.0
    stop_method: str = "atr"
    target_method: str = "reward_risk"
    default_reward_risk: float = 2.0

    def __post_init__(self) -> None:
        positive_fields = (
            "initial_capital",
            "max_gross_exposure_pct",
            "max_single_stock_pct",
            "max_sector_pct",
            "risk_per_new_position_pct",
            "risk_per_add_pct",
            "max_portfolio_open_risk_pct",
            "max_positions",
            "initial_entry_pct_of_target",
            "default_reward_risk",
        )
        for name in positive_fields:
            value = getattr(self, name)
            if float(value) <= 0:
                raise ValueError(f"{name} must be positive")
        if self.trim_to_position_pct >= self.trim_when_position_pct_above:
            raise ValueError("trim_to_position_pct must be below trim_when_position_pct_above")
        if self.stop_method != "atr":
            raise ValueError("stop_method must be atr")
        if self.target_method != "reward_risk":
            raise ValueError("target_method must be reward_risk")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def checksum(self) -> str:
        payload = json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def load_policy(path: Path | None = None) -> ManagedPortfolioPolicy:
    if path is None:
        return ManagedPortfolioPolicy()
    raw = path.read_text(encoding="utf-8")
    data = _parse_simple_yaml(raw)
    return ManagedPortfolioPolicy(**data)


def _parse_simple_yaml(raw: str) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in stripped:
            raise ValueError(f"invalid policy line: {line}")
        key, value = stripped.split(":", 1)
        data[key.strip()] = _coerce_policy_value(value.strip())
    return data


def _coerce_policy_value(value: str) -> Any:
    if value == "":
        return ""
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value.strip("\"'")


@dataclass
class ManagedLot:
    lot_id: str
    symbol: str
    quantity: int
    entry_price: float
    stop_price: float
    target_price: float
    risk_per_share: float
    entry_date: str
    source_order_id: str


@dataclass
class ManagedPosition:
    symbol: str
    sector: str
    quantity: int = 0
    avg_cost: float = 0.0
    lots: list[ManagedLot] = field(default_factory=list)

    def market_value(self, price: float) -> float:
        return round(self.quantity * price, 6)

    def open_risk(self) -> float:
        total = 0.0
        for lot in self.lots:
            total += max(0.0, lot.entry_price - lot.stop_price) * lot.quantity
        return round(total, 6)


def build_managed_portfolio(
    *,
    output_dir: Path,
    run_id: str,
    selected_strategy_id: str,
    selected_strategy_name: str,
    features: pd.DataFrame,
    strategy_orders: list[dict[str, Any]],
    policy: ManagedPortfolioPolicy,
    llm_council: str = "off",
) -> dict[str, Any]:
    _ = output_dir
    manager = _ManagedPortfolioBuilder(
        run_id=run_id,
        selected_strategy_id=selected_strategy_id,
        selected_strategy_name=selected_strategy_name,
        features=features,
        strategy_orders=strategy_orders,
        policy=policy,
        llm_council=llm_council,
    )
    return manager.run()


class _ManagedPortfolioBuilder:
    def __init__(
        self,
        *,
        run_id: str,
        selected_strategy_id: str,
        selected_strategy_name: str,
        features: pd.DataFrame,
        strategy_orders: list[dict[str, Any]],
        policy: ManagedPortfolioPolicy,
        llm_council: str,
    ) -> None:
        self.run_id = run_id
        self.selected_strategy_id = selected_strategy_id
        self.selected_strategy_name = selected_strategy_name
        self.features = _normalize_features(features)
        self.orders = sorted(
            strategy_orders,
            key=lambda row: (str(row.get("submitted_at") or ""), str(row.get("order_id") or "")),
        )
        self.policy = policy
        self.llm_council = llm_council
        self.cash = float(policy.initial_capital)
        self.positions: dict[str, ManagedPosition] = {}
        self.decisions: list[dict[str, Any]] = []
        self.managed_orders: list[dict[str, Any]] = []
        self.daily_pnl: list[dict[str, Any]] = []
        self.realized_pnl = 0.0
        self.lot_seq = 0

    def run(self) -> dict[str, Any]:
        orders_by_date: dict[str, list[dict[str, Any]]] = {}
        for order in self.orders:
            orders_by_date.setdefault(str(order.get("submitted_at") or "")[:10], []).append(order)

        feature_days = {str(date)[:10]: day for date, day in self.features.groupby("date", sort=True)}
        for date_str in sorted(set(feature_days) | set(orders_by_date)):
            day = feature_days.get(date_str)
            if day is None:
                for order in orders_by_date.get(date_str, []):
                    self._decision(date_str, order, "SKIP", 0, None, None, None, 0.0, ["MISSING_FEATURE_DATE"])
                continue

            marks = {str(row["symbol"]).upper(): float(row["close"]) for _, row in day.iterrows()}
            for order in orders_by_date.get(date_str, []):
                row = self._feature_row(date_str, str(order.get("symbol") or ""))
                if row is None:
                    self._decision(date_str, order, "SKIP", 0, None, None, None, 0.0, ["MISSING_PRICE"])
                    continue
                side = str(order.get("side") or "").upper()
                if side == "BUY":
                    self._handle_buy(date_str, order, row)
                elif side == "SELL":
                    self._handle_sell(date_str, order, row)
                else:
                    self._decision(date_str, order, "SKIP", 0, None, None, None, 0.0, ["UNSUPPORTED_SIDE"])
            self._mark_day(date_str, marks)

        state = self._state()
        return {
            "state": state,
            "positions": list(state["positions"].values()),
            "decisions": self.decisions,
            "orders": self.managed_orders,
            "daily_pnl": self.daily_pnl,
            "llm_reviews": self._llm_reviews(),
        }

    def _handle_buy(self, date_str: str, order: dict[str, Any], row: pd.Series) -> None:
        symbol = str(order.get("symbol") or "").upper()
        price = _positive(row.get("close"))
        atr = _positive(row.get("atr_14"))
        if price is None or atr is None:
            self._decision(date_str, order, "SKIP", 0, price, None, None, 0.0, ["INVALID_RISK_INPUT"])
            return

        stop = round(price - atr * 2.0, 6)
        if stop <= 0 or stop >= price:
            self._decision(date_str, order, "SKIP", 0, price, stop, None, 0.0, ["INVALID_STOP"])
            return

        target = round(price + (price - stop) * self.policy.default_reward_risk, 6)
        action = "ADD" if symbol in self.positions else "ENTER"
        quantity, risk_amount, reasons = self._size_order(symbol, row, price, stop, action)
        if quantity <= 0 or reasons:
            self._decision(date_str, order, "SKIP", 0, price, stop, target, risk_amount, reasons or ["ZERO_QUANTITY"])
            return

        self._apply_buy(date_str, order, row, quantity, price, stop, target)
        self._decision(date_str, order, action, quantity, price, stop, target, risk_amount, ["POLICY_OK"])

    def _handle_sell(self, date_str: str, order: dict[str, Any], row: pd.Series) -> None:
        symbol = str(order.get("symbol") or "").upper()
        position = self.positions.get(symbol)
        price = _positive(row.get("close"))
        if position is None or position.quantity <= 0:
            self._decision(date_str, order, "SKIP", 0, price, None, None, 0.0, ["NO_POSITION"])
            return
        if price is None:
            self._decision(date_str, order, "SKIP", 0, None, None, None, 0.0, ["MISSING_PRICE"])
            return

        quantity = position.quantity
        proceeds = quantity * price
        cost = quantity * position.avg_cost
        self.cash += proceeds
        self.realized_pnl += proceeds - cost
        self.positions.pop(symbol, None)
        self._decision(date_str, order, "EXIT", quantity, price, None, None, 0.0, ["STRATEGY_EXIT"])

    def _size_order(
        self,
        symbol: str,
        row: pd.Series,
        price: float,
        stop: float,
        action: str,
    ) -> tuple[int, float, list[str]]:
        nav = self._nav({symbol: price})
        risk_pct = self.policy.risk_per_add_pct if action == "ADD" else self.policy.risk_per_new_position_pct
        stage_pct = self.policy.first_add_pct_of_target if action == "ADD" else self.policy.initial_entry_pct_of_target
        risk_per_share = price - stop
        risk_budget = nav * risk_pct / 100.0 * stage_pct / 100.0
        quantity = int(risk_budget // risk_per_share)
        value = quantity * price
        risk_amount = quantity * risk_per_share
        reasons: list[str] = []

        if quantity <= 0:
            reasons.append("ZERO_QUANTITY")
        if value > self.cash:
            quantity = int(self.cash // price)
            value = quantity * price
            risk_amount = quantity * risk_per_share
        current_position = self.positions.get(symbol)
        current_value = current_position.quantity * price if current_position is not None else 0.0
        if current_value + value > nav * self.policy.max_single_stock_pct / 100.0:
            reasons.append("STOCK_CAP")
        if self._sector_value(str(row.get("sector") or "Unknown")) + value > nav * self.policy.max_sector_pct / 100.0:
            reasons.append("SECTOR_CAP")
        if self._gross_exposure({symbol: price}) + value > nav * self.policy.max_gross_exposure_pct / 100.0:
            reasons.append("GROSS_EXPOSURE_CAP")
        if symbol not in self.positions and len(self.positions) >= self.policy.max_positions:
            reasons.append("MAX_POSITIONS")
        if self._open_risk() + risk_amount > nav * self.policy.max_portfolio_open_risk_pct / 100.0:
            reasons.append("OPEN_RISK_CAP")

        return quantity, round(risk_amount, 6), reasons

    def _apply_buy(
        self,
        date_str: str,
        order: dict[str, Any],
        row: pd.Series,
        quantity: int,
        price: float,
        stop: float,
        target: float,
    ) -> None:
        symbol = str(order.get("symbol") or "").upper()
        sector = str(row.get("sector") or "Unknown")
        self.cash -= quantity * price
        self.lot_seq += 1
        lot = ManagedLot(
            lot_id=f"lot_{self.lot_seq:06d}",
            symbol=symbol,
            quantity=quantity,
            entry_price=price,
            stop_price=stop,
            target_price=target,
            risk_per_share=price - stop,
            entry_date=date_str,
            source_order_id=str(order.get("order_id") or ""),
        )
        position = self.positions.get(symbol)
        if position is None:
            position = ManagedPosition(symbol=symbol, sector=sector)
            self.positions[symbol] = position
        total_cost = position.avg_cost * position.quantity + quantity * price
        position.quantity += quantity
        position.avg_cost = total_cost / position.quantity
        position.lots.append(lot)

    def _feature_row(self, date_str: str, symbol: str) -> pd.Series | None:
        match = self.features[(self.features["date"] == date_str) & (self.features["symbol"] == symbol.upper())]
        return None if match.empty else match.iloc[-1]

    def _decision(
        self,
        date_str: str,
        order: dict[str, Any],
        action: str,
        quantity: int,
        price: float | None,
        stop: float | None,
        target: float | None,
        risk: float,
        reasons: list[str],
    ) -> None:
        symbol = str(order.get("symbol") or "").upper()
        marks = {symbol: price} if price is not None else {}
        nav = self._nav(marks)
        row = {
            "date": date_str,
            "decision_id": f"dec_{len(self.decisions) + 1:06d}",
            "symbol": symbol,
            "action": action,
            "quantity": int(quantity),
            "price_reference": _round(price),
            "stop_price": _round(stop),
            "target_price": _round(target),
            "risk_amount": _round(risk),
            "position_value_after": _round(self._position_value(symbol, marks)),
            "sector_exposure_after_pct": _round(self._sector_exposure_pct(symbol, marks, nav)),
            "portfolio_open_risk_after_pct": _round((self._open_risk() / nav * 100.0) if nav else 0.0),
            "reason_codes": "|".join(reasons),
            "source_strategy_order_id": str(order.get("order_id") or ""),
        }
        self.decisions.append(row)
        if action in {"ENTER", "ADD", "TRIM", "EXIT"}:
            self.managed_orders.append(row)

    def _mark_day(self, date_str: str, marks: dict[str, float]) -> None:
        nav = self._nav(marks)
        market_value = self._market_value(marks)
        previous = self.daily_pnl[-1]["nav"] if self.daily_pnl else self.policy.initial_capital
        self.daily_pnl.append(
            {
                "date": date_str,
                "cash": _round(self.cash),
                "market_value": _round(market_value),
                "nav": _round(nav),
                "daily_pnl": _round(nav - previous),
                "daily_return_pct": _round(((nav - previous) / previous * 100.0) if previous else 0.0),
                "open_positions": len(self.positions),
            }
        )

    def _state(self) -> dict[str, Any]:
        latest = self.daily_pnl[-1] if self.daily_pnl else {}
        return {
            "run_id": self.run_id,
            "as_of": latest.get("date", self.policy.start_date),
            "selected_strategy_id": self.selected_strategy_id,
            "selected_strategy_name": self.selected_strategy_name,
            "policy": self.policy.as_dict(),
            "policy_checksum": self.policy.checksum(),
            "cash": _round(self.cash),
            "nav": latest.get("nav", self.policy.initial_capital),
            "realized_pnl": _round(self.realized_pnl),
            "positions": {symbol: _position_dict(position) for symbol, position in sorted(self.positions.items())},
        }

    def _market_value(self, marks: dict[str, float]) -> float:
        total = 0.0
        for symbol, position in self.positions.items():
            mark = marks.get(symbol, position.avg_cost)
            total += position.quantity * mark
        return total

    def _position_value(self, symbol: str, marks: dict[str, float]) -> float:
        position = self.positions.get(symbol)
        if position is None:
            return 0.0
        return position.quantity * marks.get(symbol, position.avg_cost)

    def _sector_exposure_pct(self, symbol: str, marks: dict[str, float], nav: float) -> float:
        position = self.positions.get(symbol)
        if position is None or nav <= 0:
            return 0.0
        total = 0.0
        for held_symbol, held_position in self.positions.items():
            if held_position.sector == position.sector:
                total += held_position.quantity * marks.get(held_symbol, held_position.avg_cost)
        return total / nav * 100.0

    def _nav(self, marks: dict[str, float]) -> float:
        return self.cash + self._market_value(marks)

    def _gross_exposure(self, marks: dict[str, float]) -> float:
        return self._market_value(marks)

    def _sector_value(self, sector: str) -> float:
        total = 0.0
        for position in self.positions.values():
            if position.sector == sector:
                total += position.quantity * position.avg_cost
        return total

    def _open_risk(self) -> float:
        return sum(position.open_risk() for position in self.positions.values())

    def _llm_reviews(self) -> list[dict[str, Any]]:
        if self.llm_council in {"", "off", "none"}:
            return []
        return [
            {
                "severity": "info",
                "concern": "LLM council not configured",
                "suggested_change": "none",
                "evidence": "deterministic manager completed",
            }
        ]


def _normalize_features(features: pd.DataFrame) -> pd.DataFrame:
    out = features.copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    out["symbol"] = out["symbol"].astype(str).str.upper().str.strip()
    for column in ("open", "high", "low", "close", "atr_14"):
        if column in out.columns:
            out[column] = pd.to_numeric(out[column], errors="coerce")
    if "sector" not in out.columns:
        out["sector"] = "Unknown"
    return out.dropna(subset=["date", "symbol", "close"]).sort_values(["date", "symbol"], kind="mergesort")


def _position_dict(position: ManagedPosition) -> dict[str, Any]:
    return {
        "symbol": position.symbol,
        "sector": position.sector,
        "quantity": position.quantity,
        "avg_cost": _round(position.avg_cost),
        "open_risk": _round(position.open_risk()),
        "lots": [asdict(lot) for lot in position.lots],
    }


def _positive(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not pd.notna(parsed) or parsed <= 0:
        return None
    return parsed


def _round(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not pd.notna(parsed):
        return 0.0
    return round(parsed, 6)
