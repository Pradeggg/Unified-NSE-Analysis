# Portfolio-Aware Strategy Lab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic portfolio manager that turns the selected strategy lab replay into a stateful, risk-first managed paper portfolio from `2025-01-01`.

**Architecture:** Keep the existing strategy lab replay and leaderboard intact. Add a new `portfolio.engine.managed_portfolio` module that reads selected-strategy orders/fills/features, applies a validated policy, writes managed artifacts, and returns a summary that `portfolio.cli` and the strategy-lab HTML report can display.

**Tech Stack:** Python 3.13, pandas, PyYAML when available with a JSON-compatible fallback, pytest, existing `portfolio.cli`, existing `terminal.reports` report generator.

---

## File Structure

- Create `portfolio/config/portfolio_policy.yaml`: default risk, exposure, and staged add policy.
- Create `portfolio/engine/managed_portfolio.py`: policy parser, sizing engine, replay manager, artifact writer, and optional LLM review rows that are advisory only.
- Modify `portfolio/cli.py`: add `--managed-portfolio`, `--policy`, and `--llm-council`; call the manager after `publish_daily_paper_portfolio`.
- Modify `terminal/reports.py`: include managed portfolio artifacts in the strategy-lab HTML report.
- Create `tests/portfolio/test_managed_portfolio.py`: focused unit tests for sizing, caps, actions, stops/targets, and artifact generation.
- Modify `tests/portfolio/test_postgres_strategy_lab.py`: one CLI integration test proving managed artifacts are written when enabled.

## Task 1: Default Policy And Policy Parser

**Files:**
- Create: `portfolio/config/portfolio_policy.yaml`
- Create: `portfolio/engine/managed_portfolio.py`
- Test: `tests/portfolio/test_managed_portfolio.py`

- [ ] **Step 1: Write failing policy tests**

Add this to `tests/portfolio/test_managed_portfolio.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest

from portfolio.engine.managed_portfolio import ManagedPortfolioPolicy, load_policy


def test_load_policy_reads_default_yaml():
    policy = load_policy(Path("portfolio/config/portfolio_policy.yaml"))

    assert policy.start_date == "2025-01-01"
    assert policy.initial_capital == 1_000_000
    assert policy.max_single_stock_pct == 10
    assert policy.max_sector_pct == 25
    assert policy.risk_per_new_position_pct == 1.0
    assert policy.max_portfolio_open_risk_pct == 8


def test_policy_validation_rejects_invalid_risk():
    with pytest.raises(ValueError, match="risk_per_new_position_pct"):
        ManagedPortfolioPolicy(risk_per_new_position_pct=0)
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
.venv/bin/python -m pytest -q tests/portfolio/test_managed_portfolio.py::test_load_policy_reads_default_yaml tests/portfolio/test_managed_portfolio.py::test_policy_validation_rejects_invalid_risk
```

Expected: FAIL with `ModuleNotFoundError: No module named 'portfolio.engine.managed_portfolio'`.

- [ ] **Step 3: Add default policy file**

Create `portfolio/config/portfolio_policy.yaml`:

```yaml
start_date: 2025-01-01
initial_capital: 1000000
max_gross_exposure_pct: 95
max_single_stock_pct: 10
max_sector_pct: 25
risk_per_new_position_pct: 1.0
risk_per_add_pct: 0.5
max_portfolio_open_risk_pct: 8
max_positions: 15
initial_entry_pct_of_target: 50
first_add_pct_of_target: 25
second_add_pct_of_target: 25
trim_when_position_pct_above: 12
trim_to_position_pct: 8
stop_method: atr
target_method: reward_risk
default_reward_risk: 2.0
```

- [ ] **Step 4: Implement policy parser**

Create the top of `portfolio/engine/managed_portfolio.py`:

```python
from __future__ import annotations

import csv
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
```

- [ ] **Step 5: Run tests**

Run:

```bash
.venv/bin/python -m pytest -q tests/portfolio/test_managed_portfolio.py::test_load_policy_reads_default_yaml tests/portfolio/test_managed_portfolio.py::test_policy_validation_rejects_invalid_risk
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add portfolio/config/portfolio_policy.yaml portfolio/engine/managed_portfolio.py tests/portfolio/test_managed_portfolio.py
git commit -m "feat(portfolio): add managed portfolio policy"
```

## Task 2: Managed Portfolio Sizing And Decision Engine

**Files:**
- Modify: `portfolio/engine/managed_portfolio.py`
- Test: `tests/portfolio/test_managed_portfolio.py`

- [ ] **Step 1: Write failing sizing and decision tests**

Append to `tests/portfolio/test_managed_portfolio.py`:

```python
import pandas as pd

from portfolio.engine.managed_portfolio import build_managed_portfolio


def _features() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "date": "2025-01-02",
                "symbol": "AAA",
                "open": 101.0,
                "high": 103.0,
                "low": 99.0,
                "close": 100.0,
                "atr_14": 10.0,
                "sector": "Industrials",
                "stage": "STAGE_2",
                "relative_strength": 80.0,
                "rsi_14": 60.0,
            },
            {
                "date": "2025-01-03",
                "symbol": "AAA",
                "open": 111.0,
                "high": 113.0,
                "low": 108.0,
                "close": 110.0,
                "atr_14": 10.0,
                "sector": "Industrials",
                "stage": "STAGE_2",
                "relative_strength": 82.0,
                "rsi_14": 62.0,
            },
            {
                "date": "2025-01-04",
                "symbol": "AAA",
                "open": 89.0,
                "high": 91.0,
                "low": 86.0,
                "close": 88.0,
                "atr_14": 10.0,
                "sector": "Industrials",
                "stage": "STAGE_2",
                "relative_strength": 50.0,
                "rsi_14": 40.0,
            },
        ]
    )


def test_managed_portfolio_enters_with_risk_based_half_target(tmp_path):
    policy = ManagedPortfolioPolicy(initial_capital=100_000, max_single_stock_pct=20)
    orders = [
        {
            "order_id": "ord1",
            "strategy_id": "s1",
            "symbol": "AAA",
            "side": "BUY",
            "quantity": 999,
            "submitted_at": "2025-01-02",
            "reason": "entry rule matched",
        }
    ]

    result = build_managed_portfolio(
        output_dir=tmp_path,
        run_id="RUN1",
        selected_strategy_id="s1",
        selected_strategy_name="Strategy One",
        features=_features(),
        strategy_orders=orders,
        policy=policy,
        llm_council="off",
    )

    enter = [row for row in result["decisions"] if row["action"] == "ENTER"][0]
    assert enter["quantity"] == 25
    assert enter["stop_price"] == 80.0
    assert enter["target_price"] == 140.0
    assert enter["risk_amount"] == 500.0
    assert result["state"]["cash"] == 97_500.0


def test_managed_portfolio_skips_when_sector_cap_exceeded(tmp_path):
    policy = ManagedPortfolioPolicy(initial_capital=100_000, max_sector_pct=1, max_single_stock_pct=20)
    orders = [
        {
            "order_id": "ord1",
            "strategy_id": "s1",
            "symbol": "AAA",
            "side": "BUY",
            "quantity": 999,
            "submitted_at": "2025-01-02",
            "reason": "entry rule matched",
        }
    ]

    result = build_managed_portfolio(
        output_dir=tmp_path,
        run_id="RUN1",
        selected_strategy_id="s1",
        selected_strategy_name="Strategy One",
        features=_features(),
        strategy_orders=orders,
        policy=policy,
        llm_council="off",
    )

    skip = [row for row in result["decisions"] if row["action"] == "SKIP"][0]
    assert "SECTOR_CAP" in skip["reason_codes"]
    assert result["state"]["positions"] == {}


def test_managed_portfolio_exits_on_strategy_sell(tmp_path):
    policy = ManagedPortfolioPolicy(initial_capital=100_000, max_single_stock_pct=20)
    orders = [
        {"order_id": "ord1", "strategy_id": "s1", "symbol": "AAA", "side": "BUY", "quantity": 999, "submitted_at": "2025-01-02", "reason": "entry rule matched"},
        {"order_id": "ord2", "strategy_id": "s1", "symbol": "AAA", "side": "SELL", "quantity": 999, "submitted_at": "2025-01-04", "reason": "exit rule matched"},
    ]

    result = build_managed_portfolio(
        output_dir=tmp_path,
        run_id="RUN1",
        selected_strategy_id="s1",
        selected_strategy_name="Strategy One",
        features=_features(),
        strategy_orders=orders,
        policy=policy,
        llm_council="off",
    )

    actions = [row["action"] for row in result["decisions"]]
    assert "ENTER" in actions
    assert "EXIT" in actions
    assert result["state"]["positions"] == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
.venv/bin/python -m pytest -q tests/portfolio/test_managed_portfolio.py
```

Expected: FAIL because `build_managed_portfolio` is missing.

- [ ] **Step 3: Implement managed state and replay**

Append to `portfolio/engine/managed_portfolio.py`:

```python
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
    manager = _ManagedPortfolioBuilder(
        run_id=run_id,
        selected_strategy_id=selected_strategy_id,
        selected_strategy_name=selected_strategy_name,
        features=features,
        strategy_orders=strategy_orders,
        policy=policy,
        llm_council=llm_council,
    )
    result = manager.run()
    _write_managed_artifacts(output_dir, policy, result)
    return result


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
        self.orders = sorted(strategy_orders, key=lambda row: (str(row.get("submitted_at") or ""), str(row.get("order_id") or "")))
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
        for date, day in self.features.groupby("date", sort=True):
            date_str = str(date)[:10]
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

    def _size_order(self, symbol: str, row: pd.Series, price: float, stop: float, action: str) -> tuple[int, float, list[str]]:
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
        if value > nav * self.policy.max_single_stock_pct / 100.0:
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

    def _apply_buy(self, date_str: str, order: dict[str, Any], row: pd.Series, quantity: int, price: float, stop: float, target: float) -> None:
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

    def _decision(self, date_str: str, order: dict[str, Any], action: str, quantity: int, price: float | None, stop: float | None, target: float | None, risk: float, reasons: list[str]) -> None:
        symbol = str(order.get("symbol") or "").upper()
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
            "position_value_after": _round((self.positions.get(symbol).quantity * price) if symbol in self.positions and price else 0.0),
            "sector_exposure_after_pct": 0.0,
            "portfolio_open_risk_after_pct": 0.0,
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
        return [{"severity": "info", "concern": "LLM council not configured", "suggested_change": "none", "evidence": "deterministic manager completed"}]
```

- [ ] **Step 4: Add helper functions**

Append to `portfolio/engine/managed_portfolio.py`:

```python
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
```

- [ ] **Step 5: Run tests**

Run:

```bash
.venv/bin/python -m pytest -q tests/portfolio/test_managed_portfolio.py
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add portfolio/engine/managed_portfolio.py tests/portfolio/test_managed_portfolio.py
git commit -m "feat(portfolio): add managed portfolio engine"
```

## Task 3: Managed Artifact Writer

**Files:**
- Modify: `portfolio/engine/managed_portfolio.py`
- Test: `tests/portfolio/test_managed_portfolio.py`

- [ ] **Step 1: Write failing artifact test**

Append to `tests/portfolio/test_managed_portfolio.py`:

```python
def test_managed_portfolio_writes_artifacts(tmp_path):
    policy = ManagedPortfolioPolicy(initial_capital=100_000, max_single_stock_pct=20)
    orders = [{"order_id": "ord1", "strategy_id": "s1", "symbol": "AAA", "side": "BUY", "quantity": 999, "submitted_at": "2025-01-02", "reason": "entry rule matched"}]

    result = build_managed_portfolio(
        output_dir=tmp_path,
        run_id="RUN1",
        selected_strategy_id="s1",
        selected_strategy_name="Strategy One",
        features=_features(),
        strategy_orders=orders,
        policy=policy,
        llm_council="optional",
    )

    managed_dir = tmp_path / "managed"
    assert (managed_dir / "portfolio_policy.yaml").exists()
    assert (managed_dir / "managed_portfolio_state.json").exists()
    assert (managed_dir / "managed_positions.csv").exists()
    assert (managed_dir / "managed_orders.csv").exists()
    assert (managed_dir / "managed_decisions.csv").exists()
    assert (managed_dir / "managed_daily_pnl.csv").exists()
    assert (managed_dir / "llm_council_review.jsonl").exists()
    assert result["artifacts"]["state"].endswith("managed_portfolio_state.json")
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
.venv/bin/python -m pytest -q tests/portfolio/test_managed_portfolio.py::test_managed_portfolio_writes_artifacts
```

Expected: FAIL because artifact paths are not returned or all files are not written.

- [ ] **Step 3: Implement artifact writer**

Append to `portfolio/engine/managed_portfolio.py`:

```python
def _write_managed_artifacts(output_dir: Path, policy: ManagedPortfolioPolicy, result: dict[str, Any]) -> None:
    managed_dir = output_dir / "managed"
    managed_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "policy": managed_dir / "portfolio_policy.yaml",
        "state": managed_dir / "managed_portfolio_state.json",
        "positions": managed_dir / "managed_positions.csv",
        "orders": managed_dir / "managed_orders.csv",
        "decisions": managed_dir / "managed_decisions.csv",
        "daily_pnl": managed_dir / "managed_daily_pnl.csv",
        "llm_reviews": managed_dir / "llm_council_review.jsonl",
    }
    paths["policy"].write_text(_policy_yaml(policy), encoding="utf-8")
    state = dict(result["state"])
    state["artifacts"] = {name: str(path) for name, path in paths.items()}
    paths["state"].write_text(json.dumps(_json_safe(state), indent=2, sort_keys=True), encoding="utf-8")
    _write_csv(paths["positions"], list(state.get("positions", {}).values()))
    _write_csv(paths["orders"], result.get("orders", []))
    _write_csv(paths["decisions"], result.get("decisions", []))
    _write_csv(paths["daily_pnl"], result.get("daily_pnl", []))
    reviews = result.get("llm_reviews", [])
    paths["llm_reviews"].write_text("\n".join(json.dumps(_json_safe(row), sort_keys=True) for row in reviews) + ("\n" if reviews else ""), encoding="utf-8")
    result["state"] = state
    result["artifacts"] = {name: str(path) for name, path in paths.items()}


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    keys: list[str] = []
    for row in rows:
        for key in row.keys():
            if key not in keys:
                keys.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _csv_value(row.get(key)) for key in keys})


def _csv_value(value: Any) -> Any:
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(_json_safe(value), sort_keys=True)
    return value


def _policy_yaml(policy: ManagedPortfolioPolicy) -> str:
    return "\n".join(f"{key}: {value}" for key, value in policy.as_dict().items()) + "\n"


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if hasattr(value, "item"):
        return value.item()
    return value
```

- [ ] **Step 4: Run test**

Run:

```bash
.venv/bin/python -m pytest -q tests/portfolio/test_managed_portfolio.py::test_managed_portfolio_writes_artifacts
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add portfolio/engine/managed_portfolio.py tests/portfolio/test_managed_portfolio.py
git commit -m "feat(portfolio): write managed portfolio artifacts"
```

## Task 4: CLI Integration

**Files:**
- Modify: `portfolio/cli.py`
- Modify: `tests/portfolio/test_postgres_strategy_lab.py`

- [ ] **Step 1: Write failing CLI integration test**

Add this near the existing `test_strategy_lab_command_writes_leaderboard_from_postgres_adapter` in `tests/portfolio/test_postgres_strategy_lab.py`:

```python
def test_strategy_lab_command_writes_managed_portfolio_when_enabled(monkeypatch, tmp_path):
    eod = pd.DataFrame(_eod_rows("AAA", 100.0))
    stage = pd.DataFrame(
        {
            "date": eod["date"],
            "symbol": ["AAA"] * len(eod),
            "stage": ["STAGE_2"] * len(eod),
            "snapshot_relative_strength": [85.0] * len(eod),
            "snapshot_rsi": [62.0] * len(eod),
        }
    )
    features = prepare_replay_frame(eod, stage, start_date="2024-09-01")
    benchmark = pd.DataFrame({"date": pd.to_datetime(features["date"].unique()), "close": range(100, 100 + features["date"].nunique())})

    def fake_load_postgres_replay_data(**kwargs):
        return SimpleNamespace(features=features, benchmark=benchmark, latest_eod_date="2024-09-16")

    monkeypatch.setattr(cli, "load_postgres_replay_data", fake_load_postgres_replay_data)

    code = cli.main(
        [
            "strategy-lab",
            "--output-dir",
            str(tmp_path),
            "--top-n",
            "1",
            "--no-db-persist",
            "--managed-portfolio",
            "--llm-council",
            "off",
        ]
    )

    summary = json.loads((tmp_path / "reports" / "strategy_comparison_summary.json").read_text())
    assert code == 0
    assert "managed_portfolio" in summary
    assert (tmp_path / "managed" / "managed_portfolio_state.json").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
.venv/bin/python -m pytest -q tests/portfolio/test_postgres_strategy_lab.py::test_strategy_lab_command_writes_managed_portfolio_when_enabled
```

Expected: FAIL because CLI flags are not recognized.

- [ ] **Step 3: Add CLI arguments and call manager**

Modify `portfolio/cli.py` imports:

```python
from portfolio.engine.managed_portfolio import build_managed_portfolio, load_policy
```

Add parser args in the `strategy_lab` parser block:

```python
strategy_lab.add_argument("--managed-portfolio", action="store_true")
strategy_lab.add_argument("--policy", type=Path, default=Path("portfolio/config/portfolio_policy.yaml"))
strategy_lab.add_argument("--llm-council", choices=["off", "optional"], default="off")
```

After `summary["paper_portfolio"] = publish_daily_paper_portfolio(...)`, add:

```python
    if getattr(args, "managed_portfolio", False):
        selected_id = str(summary["paper_portfolio"].get("selected_strategy_id") or "")
        selected_name = str(summary["paper_portfolio"].get("selected_strategy_name") or selected_id)
        state_path = output_dir / "runs" / selected_id / "state" / "replay_state.json"
        selected_state = _read_json(state_path) if state_path.exists() else {}
        policy = load_policy(args.policy)
        summary["managed_portfolio"] = build_managed_portfolio(
            output_dir=output_dir,
            run_id=args.run_id,
            selected_strategy_id=selected_id,
            selected_strategy_name=selected_name,
            features=data,
            strategy_orders=selected_state.get("orders", []),
            policy=policy,
            llm_council=args.llm_council,
        )
```

- [ ] **Step 4: Run CLI integration test**

Run:

```bash
.venv/bin/python -m pytest -q tests/portfolio/test_postgres_strategy_lab.py::test_strategy_lab_command_writes_managed_portfolio_when_enabled
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add portfolio/cli.py tests/portfolio/test_postgres_strategy_lab.py
git commit -m "feat(portfolio): wire managed portfolio into strategy lab"
```

## Task 5: Strategy Lab HTML Report Section

**Files:**
- Modify: `terminal/reports.py`
- Test: `tests/test_terminal_reports.py` or `tests/portfolio/test_postgres_strategy_lab.py`

- [ ] **Step 1: Locate report generation function**

Run:

```bash
rg -n "strategy-lab|strategy_lab|portfolio_strategy_lab|strategy_comparison_summary" terminal/reports.py tests/test_terminal_reports.py
```

Expected: find the strategy-lab report builder and existing report tests.

- [ ] **Step 2: Write failing report test**

Add a focused test named `test_strategy_lab_report_includes_managed_portfolio` to the existing terminal reports test file. The test writes a temporary `strategy_comparison_summary.json` with:

```python
"managed_portfolio": {
    "state": {"nav": 1010000, "cash": 500000, "positions": {"AAA": {"symbol": "AAA", "quantity": 25, "avg_cost": 100}}},
    "decisions": [{"date": "2025-01-02", "symbol": "AAA", "action": "ENTER", "quantity": 25, "reason_codes": "POLICY_OK"}],
    "orders": [{"date": "2025-01-02", "symbol": "AAA", "action": "ENTER", "quantity": 25}],
}
```

Assert the generated HTML contains:

```python
assert "Managed Portfolio" in html
assert "POLICY_OK" in html
assert "AAA" in html
```

- [ ] **Step 3: Run test to verify it fails**

Run the exact test selected in Step 2:

```bash
.venv/bin/python -m pytest -q tests/test_terminal_reports.py::test_strategy_lab_report_includes_managed_portfolio
```

Expected: FAIL because managed portfolio details are absent from HTML.

- [ ] **Step 4: Add managed HTML renderer**

In `terminal/reports.py`, near the strategy-lab report builder, add a helper:

```python
def _strategy_lab_managed_portfolio_html(summary: dict) -> str:
    managed = summary.get("managed_portfolio") or {}
    if not managed:
        return ""
    state = managed.get("state") or {}
    positions = (state.get("positions") or {}).values()
    decisions = managed.get("decisions") or []
    rows = "".join(
        f"<tr><td>{_html.escape(str(row.get('symbol', '')))}</td><td>{_html.escape(str(row.get('quantity', '')))}</td><td>{_html.escape(str(row.get('avg_cost', '')))}</td></tr>"
        for row in positions
    )
    decision_rows = "".join(
        f"<tr><td>{_html.escape(str(row.get('date', '')))}</td><td>{_html.escape(str(row.get('symbol', '')))}</td><td>{_html.escape(str(row.get('action', '')))}</td><td>{_html.escape(str(row.get('reason_codes', '')))}</td></tr>"
        for row in decisions[-20:]
    )
    return f"""
    <section class="card">
      <h2>Managed Portfolio</h2>
      <p>NAV: {_html.escape(str(state.get('nav', 'N/A')))} · Cash: {_html.escape(str(state.get('cash', 'N/A')))}</p>
      <h3>Managed Positions</h3>
      <table><thead><tr><th>Symbol</th><th>Qty</th><th>Avg Cost</th></tr></thead><tbody>{rows}</tbody></table>
      <h3>Recent Managed Decisions</h3>
      <table><thead><tr><th>Date</th><th>Symbol</th><th>Action</th><th>Reason</th></tr></thead><tbody>{decision_rows}</tbody></table>
    </section>
    """
```

Call this helper from the strategy-lab HTML assembly immediately after the paper portfolio or leaderboard section:

```python
managed_html = _strategy_lab_managed_portfolio_html(summary)
```

and include `{managed_html}` in the final HTML body.

- [ ] **Step 5: Run report test**

Run:

```bash
.venv/bin/python -m pytest -q tests/test_terminal_reports.py::test_strategy_lab_report_includes_managed_portfolio
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add terminal/reports.py tests/test_terminal_reports.py
git commit -m "feat(reports): show managed portfolio in strategy lab report"
```

## Task 6: End-To-End Verification

**Files:**
- No planned code changes unless tests reveal defects.

- [ ] **Step 1: Run focused test suite**

Run:

```bash
.venv/bin/python -m pytest -q tests/portfolio/test_managed_portfolio.py tests/portfolio/test_postgres_strategy_lab.py tests/test_terminal_reports.py
```

Expected: PASS.

- [ ] **Step 2: Run real strategy lab with managed portfolio enabled**

Run:

```bash
.venv/bin/python -m portfolio.cli strategy-lab \
  --output-dir portfolio/data/nse_pg_strategy_lab/latest \
  --start 2025-01-01 \
  --lookback 2024-01-01 \
  --top-n 200 \
  --slippage-bps 5 \
  --brokerage-bps 3 \
  --run-id NSE-PG-DAILY-STRATEGY-LAB \
  --managed-portfolio \
  --policy portfolio/config/portfolio_policy.yaml \
  --llm-council off
```

Expected: exit code 0 and files under `portfolio/data/nse_pg_strategy_lab/latest/managed/`.

- [ ] **Step 3: Generate latest HTML report**

Run:

```bash
.venv/bin/python - <<'PY'
from terminal.reports import generate_preset_report
print(generate_preset_report("strategy-lab", "html"))
PY
```

Expected: `success: True`, latest report path `reports/latest/portfolio_strategy_lab.html`, and HTML contains `Managed Portfolio`.

- [ ] **Step 4: Inspect managed state**

Run:

```bash
python3 - <<'PY'
import json
from pathlib import Path
state = json.loads(Path("portfolio/data/nse_pg_strategy_lab/latest/managed/managed_portfolio_state.json").read_text())
print("as_of", state["as_of"])
print("nav", state["nav"])
print("cash", state["cash"])
print("positions", len(state["positions"]))
print("policy_checksum", state["policy_checksum"])
PY
```

Expected: prints a non-empty state with `as_of` at latest EOD date.

- [ ] **Step 5: Commit final verification fixes if any**

If Step 1 through Step 4 required fixes, commit them:

```bash
git add portfolio/config/portfolio_policy.yaml portfolio/engine/managed_portfolio.py portfolio/cli.py terminal/reports.py tests/portfolio/test_managed_portfolio.py tests/portfolio/test_postgres_strategy_lab.py tests/test_terminal_reports.py
git commit -m "fix(portfolio): verify managed strategy lab flow"
```

If no fixes were required, do not create an empty commit.

## Self-Review Notes

- Spec coverage: the plan covers policy file, deterministic manager, risk-first sizing, staged entry/add actions, exits, skip reasons, artifacts, CLI integration, report integration, and tests.
- Known v1 reduction: PostgreSQL persistence for managed tables is intentionally not in the first implementation task set because the design allows file artifacts first. Add DB persistence after the file-backed manager is verified.
- LLM council: v1 records no executable LLM changes. This satisfies the deterministic safety requirement and leaves real LLM critique for a follow-up once managed decisions are stable.
