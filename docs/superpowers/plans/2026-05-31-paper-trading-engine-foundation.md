# Paper Trading Engine Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the deterministic Phase 1 foundation for the paper-trading strategy lab: strategy schema validation, event contracts, paper account, paper broker, metrics, audit logs, Markdown report, and a CLI replay over fixture data.

**Architecture:** Add a new local `portfolio` package that is independent of the existing `portfolio-analyzer/` folder. Phase 1 intentionally avoids LLM calls and PostgreSQL integration: it uses static strategy specs and fixture data so the engine core is deterministic and testable before agents are added.

**Tech Stack:** Python 3.13-compatible standard library, `pandas`, `pytest`, existing repo `.venv`, CSV/JSON/JSONL file outputs.

---

## File Structure

Create:

- `portfolio/__init__.py`: package marker and version string.
- `portfolio/config.yaml`: default local config used by CLI.
- `portfolio/engine/__init__.py`: engine package marker.
- `portfolio/engine/strategy_schema.py`: dataclasses and validation for strategy specs.
- `portfolio/engine/strategy_compiler.py`: converts strategy specs into deterministic predicates and clamps risk.
- `portfolio/engine/events.py`: event dataclasses emitted by replay.
- `portfolio/engine/event_loop.py`: deterministic EOD replay loop.
- `portfolio/engine/order_types.py`: paper order and fill contracts.
- `portfolio/engine/execution_models.py`: next-open fill model with fees/slippage hooks.
- `portfolio/engine/portfolio_account.py`: cash, positions, orders, fills, NAV.
- `portfolio/engine/metrics.py`: portfolio/trade/strategy metrics.
- `portfolio/engine/audit_log.py`: JSONL action logger.
- `portfolio/agents/__init__.py`: agents package marker.
- `portfolio/agents/report_agent.py`: Markdown daily report writer.
- `portfolio/cli.py`: `replay`, `status`, and `report` commands.
- `tests/portfolio/__init__.py`: test package marker.
- `tests/portfolio/fixtures.py`: tiny deterministic OHLCV fixture and valid strategy fixture.
- `tests/portfolio/test_strategy_schema.py`: schema and compiler tests.
- `tests/portfolio/test_paper_broker.py`: paper execution and account tests.
- `tests/portfolio/test_event_loop.py`: event-order and deterministic replay tests.
- `tests/portfolio/test_metrics_report.py`: metrics and report tests.
- `tests/portfolio/test_cli.py`: CLI smoke test.

Do not modify existing `backtesting/` behavior in Phase 1.

## Task 1: Scaffold Package And Fixtures

**Files:**
- Create: `portfolio/__init__.py`
- Create: `portfolio/config.yaml`
- Create: `portfolio/engine/__init__.py`
- Create: `portfolio/agents/__init__.py`
- Create: `tests/portfolio/__init__.py`
- Create: `tests/portfolio/fixtures.py`

- [ ] **Step 1: Write the fixture module**

Create `tests/portfolio/fixtures.py`:

```python
from __future__ import annotations

import pandas as pd


def sample_ohlcv() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.to_datetime(
                [
                    "2025-01-01",
                    "2025-01-02",
                    "2025-01-03",
                    "2025-01-06",
                    "2025-01-07",
                    "2025-01-08",
                ]
            ),
            "symbol": ["AAA", "AAA", "AAA", "AAA", "AAA", "AAA"],
            "open": [100.0, 102.0, 105.0, 109.0, 111.0, 106.0],
            "high": [103.0, 106.0, 110.0, 113.0, 112.0, 108.0],
            "low": [99.0, 101.0, 104.0, 108.0, 105.0, 100.0],
            "close": [102.0, 105.0, 109.0, 111.0, 106.0, 101.0],
            "volume": [100000, 120000, 150000, 160000, 170000, 180000],
            "stage": ["STAGE_1", "STAGE_2", "STAGE_2", "STAGE_2", "STAGE_2", "STAGE_3"],
            "rsi_14": [45.0, 56.0, 61.0, 65.0, 48.0, 38.0],
            "sma_50": [98.0, 99.0, 100.0, 101.0, 102.0, 103.0],
            "atr_14": [4.0, 4.0, 4.5, 5.0, 5.0, 5.0],
            "volume_ratio_20d": [0.9, 1.2, 1.3, 1.1, 0.8, 1.4],
        }
    )


def valid_strategy_spec() -> dict:
    return {
        "strategy_id": "stage2_fixture_v1",
        "name": "Stage 2 Fixture Strategy",
        "universe": {"stage": "STAGE_2", "min_price": 50},
        "entry": {
            "all": [
                {"indicator": "stage", "operator": "eq", "value": "STAGE_2"},
                {"indicator": "close", "operator": "above", "value": "sma_50"},
                {"indicator": "rsi_14", "operator": "between", "value": [45, 70]},
            ]
        },
        "risk": {
            "initial_stop": {"type": "atr", "multiple": 2.0},
            "risk_per_trade_pct": 1.0,
            "max_position_pct": 10.0,
        },
        "add_rules": [],
        "exit": {
            "any": [
                {"indicator": "stage", "operator": "in", "value": ["STAGE_3", "STAGE_4"]},
                {"indicator": "close", "operator": "below", "value": "sma_50"},
            ]
        },
    }
```

- [ ] **Step 2: Add package markers and config**

Create `portfolio/__init__.py`:

```python
"""Paper trading strategy lab package."""

__version__ = "0.1.0"
```

Create `portfolio/engine/__init__.py`:

```python
"""Deterministic paper trading engine components."""
```

Create `portfolio/agents/__init__.py`:

```python
"""Paper trading agent facades."""
```

Create `tests/portfolio/__init__.py`:

```python
"""Portfolio engine tests."""
```

Create `portfolio/config.yaml`:

```yaml
simulation:
  start_date: "2025-01-01"
  initial_capital: 1000000.0
  fill_policy: "next_open"

risk_rails:
  max_risk_per_trade_pct: 2.0
  max_position_pct: 15.0
  max_portfolio_exposure_pct: 95.0
  max_open_positions: 20

costs:
  brokerage_bps: 0.0
  slippage_bps: 0.0

paths:
  state_dir: "portfolio/data/state"
  logs_dir: "portfolio/data/logs"
  reports_dir: "portfolio/data/reports"
```

- [ ] **Step 3: Run fixture import check**

Run:

```bash
.venv/bin/python - <<'PY'
from tests.portfolio.fixtures import sample_ohlcv, valid_strategy_spec
print(sample_ohlcv().shape)
print(valid_strategy_spec()["strategy_id"])
PY
```

Expected: prints `(6, 12)` and `stage2_fixture_v1`.

- [ ] **Step 4: Commit scaffold**

```bash
git add portfolio/__init__.py portfolio/config.yaml portfolio/engine/__init__.py portfolio/agents/__init__.py tests/portfolio/__init__.py tests/portfolio/fixtures.py
git commit -m "feat: scaffold paper trading package"
```

## Task 2: Strategy Schema And Compiler

**Files:**
- Create: `portfolio/engine/strategy_schema.py`
- Create: `portfolio/engine/strategy_compiler.py`
- Test: `tests/portfolio/test_strategy_schema.py`

- [ ] **Step 1: Write failing schema tests**

Create `tests/portfolio/test_strategy_schema.py`:

```python
from __future__ import annotations

import pytest

from portfolio.engine.strategy_compiler import compile_strategy
from portfolio.engine.strategy_schema import StrategyValidationError, validate_strategy_spec
from tests.portfolio.fixtures import valid_strategy_spec


def test_valid_strategy_spec_is_accepted():
    spec = validate_strategy_spec(valid_strategy_spec())

    assert spec.strategy_id == "stage2_fixture_v1"
    assert spec.risk.risk_per_trade_pct == 1.0
    assert spec.risk.max_position_pct == 10.0
    assert spec.risk.initial_stop["type"] == "atr"


def test_unknown_indicator_is_rejected():
    raw = valid_strategy_spec()
    raw["entry"]["all"][0]["indicator"] = "future_alpha"

    with pytest.raises(StrategyValidationError, match="unknown indicator"):
        validate_strategy_spec(raw)


def test_missing_stop_rule_is_rejected():
    raw = valid_strategy_spec()
    raw["risk"].pop("initial_stop")

    with pytest.raises(StrategyValidationError, match="initial_stop"):
        validate_strategy_spec(raw)


def test_compiler_clamps_risk_to_hard_rails():
    raw = valid_strategy_spec()
    raw["risk"]["risk_per_trade_pct"] = 9.0
    raw["risk"]["max_position_pct"] = 80.0

    compiled = compile_strategy(raw)

    assert compiled.spec.risk.risk_per_trade_pct == 2.0
    assert compiled.spec.risk.max_position_pct == 15.0
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/portfolio/test_strategy_schema.py -q
```

Expected: FAIL with `ModuleNotFoundError` or missing `portfolio.engine.strategy_schema`.

- [ ] **Step 3: Implement schema**

Create `portfolio/engine/strategy_schema.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


ALLOWED_INDICATORS = {
    "stage",
    "close",
    "open",
    "high",
    "low",
    "rsi_14",
    "sma_20",
    "sma_50",
    "sma_100",
    "sma_200",
    "ema_20",
    "ema_50",
    "atr_14",
    "volume_ratio_20d",
    "relative_strength",
    "trailing_stop",
}
ALLOWED_OPERATORS = {"eq", "in", "above", "below", "gte", "lte", "between"}


class StrategyValidationError(ValueError):
    """Raised when an LLM strategy proposal is outside the allowed grammar."""


@dataclass(frozen=True)
class Rule:
    indicator: str
    operator: str
    value: Any


@dataclass(frozen=True)
class RiskSpec:
    initial_stop: dict[str, Any]
    risk_per_trade_pct: float
    max_position_pct: float


@dataclass(frozen=True)
class StrategySpec:
    strategy_id: str
    name: str
    universe: dict[str, Any]
    entry_all: tuple[Rule, ...]
    exit_any: tuple[Rule, ...]
    risk: RiskSpec
    add_rules: tuple[dict[str, Any], ...]
    raw: dict[str, Any]


def validate_strategy_spec(raw: dict[str, Any]) -> StrategySpec:
    if not isinstance(raw, dict):
        raise StrategyValidationError("strategy spec must be a dict")
    strategy_id = _required_str(raw, "strategy_id")
    name = _required_str(raw, "name")
    entry = raw.get("entry") or {}
    exit_spec = raw.get("exit") or {}
    risk = raw.get("risk") or {}
    entry_rules = tuple(_parse_rule(rule) for rule in entry.get("all") or [])
    exit_rules = tuple(_parse_rule(rule) for rule in exit_spec.get("any") or [])
    if not entry_rules:
        raise StrategyValidationError("entry.all must include at least one rule")
    if not exit_rules:
        raise StrategyValidationError("exit.any must include at least one rule")
    if "initial_stop" not in risk:
        raise StrategyValidationError("risk.initial_stop is required")
    return StrategySpec(
        strategy_id=strategy_id,
        name=name,
        universe=dict(raw.get("universe") or {}),
        entry_all=entry_rules,
        exit_any=exit_rules,
        risk=RiskSpec(
            initial_stop=dict(risk["initial_stop"]),
            risk_per_trade_pct=float(risk.get("risk_per_trade_pct", 1.0)),
            max_position_pct=float(risk.get("max_position_pct", 10.0)),
        ),
        add_rules=tuple(dict(rule) for rule in raw.get("add_rules") or []),
        raw=dict(raw),
    )


def _required_str(raw: dict[str, Any], key: str) -> str:
    value = str(raw.get(key) or "").strip()
    if not value:
        raise StrategyValidationError(f"{key} is required")
    return value


def _parse_rule(raw: dict[str, Any]) -> Rule:
    indicator = str(raw.get("indicator") or "").strip()
    operator = str(raw.get("operator") or "").strip()
    if indicator not in ALLOWED_INDICATORS:
        raise StrategyValidationError(f"unknown indicator: {indicator}")
    if operator not in ALLOWED_OPERATORS:
        raise StrategyValidationError(f"unknown operator: {operator}")
    if "value" not in raw:
        raise StrategyValidationError(f"rule value is required for {indicator}")
    return Rule(indicator=indicator, operator=operator, value=raw["value"])
```

- [ ] **Step 4: Implement compiler**

Create `portfolio/engine/strategy_compiler.py`:

```python
from __future__ import annotations

from dataclasses import replace
from typing import Any

import pandas as pd

from portfolio.engine.strategy_schema import RiskSpec, Rule, StrategySpec, validate_strategy_spec


MAX_RISK_PER_TRADE_PCT = 2.0
MAX_POSITION_PCT = 15.0


class CompiledStrategy:
    def __init__(self, spec: StrategySpec):
        self.spec = spec

    def should_enter(self, row: pd.Series) -> bool:
        return all(_eval_rule(rule, row) for rule in self.spec.entry_all)

    def should_exit(self, row: pd.Series) -> bool:
        return any(_eval_rule(rule, row) for rule in self.spec.exit_any)


def compile_strategy(raw: dict[str, Any]) -> CompiledStrategy:
    spec = validate_strategy_spec(raw)
    risk = replace(
        spec.risk,
        risk_per_trade_pct=min(spec.risk.risk_per_trade_pct, MAX_RISK_PER_TRADE_PCT),
        max_position_pct=min(spec.risk.max_position_pct, MAX_POSITION_PCT),
    )
    return CompiledStrategy(replace(spec, risk=risk))


def _eval_rule(rule: Rule, row: pd.Series) -> bool:
    left = row.get(rule.indicator)
    right = row.get(rule.value) if isinstance(rule.value, str) and rule.value in row else rule.value
    if rule.operator == "eq":
        return str(left).upper() == str(right).upper()
    if rule.operator == "in":
        return str(left).upper() in {str(item).upper() for item in (right or [])}
    if rule.operator == "above":
        return _float(left) > _float(right)
    if rule.operator == "below":
        return _float(left) < _float(right)
    if rule.operator == "gte":
        return _float(left) >= _float(right)
    if rule.operator == "lte":
        return _float(left) <= _float(right)
    if rule.operator == "between":
        low, high = list(right)
        value = _float(left)
        return _float(low) <= value <= _float(high)
    return False


def _float(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0
```

- [ ] **Step 5: Run tests to verify GREEN**

Run:

```bash
.venv/bin/python -m pytest tests/portfolio/test_strategy_schema.py -q
```

Expected: `4 passed`.

- [ ] **Step 6: Commit schema and compiler**

```bash
git add portfolio/engine/strategy_schema.py portfolio/engine/strategy_compiler.py tests/portfolio/test_strategy_schema.py
git commit -m "feat: add paper strategy schema compiler"
```

## Task 3: Order Types, Execution Model, And Account

**Files:**
- Create: `portfolio/engine/order_types.py`
- Create: `portfolio/engine/execution_models.py`
- Create: `portfolio/engine/portfolio_account.py`
- Test: `tests/portfolio/test_paper_broker.py`

- [ ] **Step 1: Write failing execution/account tests**

Create `tests/portfolio/test_paper_broker.py`:

```python
from __future__ import annotations

import pandas as pd

from portfolio.engine.execution_models import NextOpenExecutionModel
from portfolio.engine.order_types import Order, OrderSide, OrderType
from portfolio.engine.portfolio_account import PortfolioAccount


def test_next_open_execution_model_fills_market_order_on_next_bar_open():
    model = NextOpenExecutionModel(slippage_bps=10.0, brokerage_bps=5.0)
    order = Order(
        order_id="o1",
        strategy_id="s1",
        symbol="AAA",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET_NEXT_OPEN,
        quantity=10,
        created_date="2025-01-01",
    )
    next_bar = pd.Series({"date": pd.Timestamp("2025-01-02"), "open": 100.0, "high": 105.0, "low": 99.0, "close": 104.0})

    fill = model.try_fill(order, next_bar)

    assert fill is not None
    assert fill.fill_price == 100.1
    assert fill.fees == 0.5
    assert fill.degraded is False


def test_account_applies_buy_fill_and_marks_nav():
    account = PortfolioAccount(initial_capital=10000.0)
    fill = {
        "order_id": "o1",
        "strategy_id": "s1",
        "symbol": "AAA",
        "side": "BUY",
        "quantity": 10,
        "fill_price": 100.0,
        "fees": 1.0,
        "fill_date": "2025-01-02",
    }

    account.apply_fill(fill)
    nav = account.mark_to_market({"AAA": 105.0}, "2025-01-02")

    assert account.cash == 8999.0
    assert account.positions["AAA"].quantity == 10
    assert nav["nav"] == 10049.0
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/portfolio/test_paper_broker.py -q
```

Expected: FAIL because the modules do not exist.

- [ ] **Step 3: Implement order contracts**

Create `portfolio/engine/order_types.py`:

```python
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum


class OrderSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(StrEnum):
    MARKET_NEXT_OPEN = "MARKET_NEXT_OPEN"
    MARKET_ON_CLOSE = "MARKET_ON_CLOSE"
    STOP = "STOP"
    LIMIT = "LIMIT"
    TRAILING_STOP = "TRAILING_STOP"
    BRACKET = "BRACKET"


@dataclass(frozen=True)
class Order:
    order_id: str
    strategy_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: int
    created_date: str
    stop_price: float | None = None
    limit_price: float | None = None

    def as_dict(self) -> dict:
        row = asdict(self)
        row["side"] = self.side.value
        row["order_type"] = self.order_type.value
        return row


@dataclass(frozen=True)
class Fill:
    order_id: str
    strategy_id: str
    symbol: str
    side: OrderSide
    quantity: int
    fill_price: float
    fees: float
    fill_date: str
    degraded: bool = False

    def as_dict(self) -> dict:
        row = asdict(self)
        row["side"] = self.side.value
        return row
```

- [ ] **Step 4: Implement execution model**

Create `portfolio/engine/execution_models.py`:

```python
from __future__ import annotations

from typing import Any

import pandas as pd

from portfolio.engine.order_types import Fill, Order, OrderSide, OrderType


class NextOpenExecutionModel:
    def __init__(self, *, slippage_bps: float = 0.0, brokerage_bps: float = 0.0):
        self.slippage_bps = float(slippage_bps)
        self.brokerage_bps = float(brokerage_bps)

    def try_fill(self, order: Order, bar: pd.Series) -> Fill | None:
        if int(order.quantity) <= 0:
            return None
        if order.order_type == OrderType.MARKET_NEXT_OPEN:
            raw_price = _float(bar.get("open"))
            degraded = False
            if raw_price <= 0:
                raw_price = _float(bar.get("close"))
                degraded = True
            if raw_price <= 0:
                return None
            fill_price = self._apply_slippage(raw_price, order.side)
            fees = round(fill_price * int(order.quantity) * self.brokerage_bps / 10000.0, 6)
            return Fill(
                order_id=order.order_id,
                strategy_id=order.strategy_id,
                symbol=order.symbol,
                side=order.side,
                quantity=int(order.quantity),
                fill_price=round(fill_price, 6),
                fees=fees,
                fill_date=str(pd.to_datetime(bar.get("date")).date()),
                degraded=degraded,
            )
        return None

    def _apply_slippage(self, price: float, side: OrderSide) -> float:
        sign = 1.0 if side == OrderSide.BUY else -1.0
        return price * (1.0 + sign * self.slippage_bps / 10000.0)


def _float(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0
```

- [ ] **Step 5: Implement portfolio account**

Create `portfolio/engine/portfolio_account.py`:

```python
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class Position:
    symbol: str
    quantity: int
    avg_price: float
    strategy_ids: tuple[str, ...]


class PortfolioAccount:
    def __init__(self, *, initial_capital: float):
        self.initial_capital = round(float(initial_capital), 6)
        self.cash = round(float(initial_capital), 6)
        self.positions: dict[str, Position] = {}
        self.fills: list[dict[str, Any]] = []
        self.nav_history: list[dict[str, Any]] = []

    def apply_fill(self, fill: dict[str, Any]) -> None:
        side = str(fill["side"]).upper()
        symbol = str(fill["symbol"]).upper()
        qty = int(fill["quantity"])
        price = float(fill["fill_price"])
        fees = float(fill.get("fees") or 0.0)
        if side == "BUY":
            self.cash = round(self.cash - qty * price - fees, 6)
            current = self.positions.get(symbol)
            if current is None:
                self.positions[symbol] = Position(symbol, qty, price, (str(fill["strategy_id"]),))
            else:
                new_qty = current.quantity + qty
                avg = ((current.quantity * current.avg_price) + (qty * price)) / new_qty
                strategies = tuple(sorted(set(current.strategy_ids + (str(fill["strategy_id"]),))))
                self.positions[symbol] = Position(symbol, new_qty, round(avg, 6), strategies)
        elif side == "SELL":
            current = self.positions.get(symbol)
            if current is None:
                return
            sell_qty = min(qty, current.quantity)
            self.cash = round(self.cash + sell_qty * price - fees, 6)
            remaining = current.quantity - sell_qty
            if remaining <= 0:
                self.positions.pop(symbol, None)
            else:
                self.positions[symbol] = Position(symbol, remaining, current.avg_price, current.strategy_ids)
        self.fills.append(dict(fill))

    def mark_to_market(self, prices: dict[str, float], as_of: str) -> dict[str, Any]:
        market_value = 0.0
        for symbol, position in self.positions.items():
            market_value += position.quantity * float(prices.get(symbol, position.avg_price))
        nav = round(self.cash + market_value, 6)
        row = {
            "date": as_of,
            "cash": round(self.cash, 6),
            "market_value": round(market_value, 6),
            "nav": nav,
            "open_positions": len(self.positions),
        }
        self.nav_history.append(row)
        return row

    def positions_as_dicts(self) -> list[dict[str, Any]]:
        return [asdict(position) for position in self.positions.values()]
```

- [ ] **Step 6: Run tests to verify GREEN**

Run:

```bash
.venv/bin/python -m pytest tests/portfolio/test_paper_broker.py -q
```

Expected: `2 passed`.

- [ ] **Step 7: Commit execution/account**

```bash
git add portfolio/engine/order_types.py portfolio/engine/execution_models.py portfolio/engine/portfolio_account.py tests/portfolio/test_paper_broker.py
git commit -m "feat: add paper execution account"
```

## Task 4: Events And Deterministic Replay Loop

**Files:**
- Create: `portfolio/engine/events.py`
- Create: `portfolio/engine/event_loop.py`
- Test: `tests/portfolio/test_event_loop.py`

- [ ] **Step 1: Write failing event loop tests**

Create `tests/portfolio/test_event_loop.py`:

```python
from __future__ import annotations

from portfolio.engine.event_loop import ReplayConfig, run_replay
from tests.portfolio.fixtures import sample_ohlcv, valid_strategy_spec


def test_replay_emits_events_in_documented_order_and_records_nav():
    result = run_replay(
        sample_ohlcv(),
        [valid_strategy_spec()],
        ReplayConfig(initial_capital=100000.0),
    )

    assert result.events[:5] == [
        "MarketDataEvent",
        "SignalEvent",
        "PortfolioTargetEvent",
        "RiskCheckEvent",
        "OrderEvent",
    ]
    assert result.nav_history
    assert result.trade_ledger


def test_replay_is_deterministic_for_same_inputs():
    first = run_replay(sample_ohlcv(), [valid_strategy_spec()], ReplayConfig(initial_capital=100000.0))
    second = run_replay(sample_ohlcv(), [valid_strategy_spec()], ReplayConfig(initial_capital=100000.0))

    assert first.trade_ledger == second.trade_ledger
    assert first.nav_history == second.nav_history
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/portfolio/test_event_loop.py -q
```

Expected: FAIL because `portfolio.engine.event_loop` does not exist.

- [ ] **Step 3: Implement event contracts**

Create `portfolio/engine/events.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EngineEvent:
    event_type: str
    as_of: str
    payload: dict[str, Any]
```

- [ ] **Step 4: Implement minimal replay loop**

Create `portfolio/engine/event_loop.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from portfolio.engine.execution_models import NextOpenExecutionModel
from portfolio.engine.order_types import Order, OrderSide, OrderType
from portfolio.engine.portfolio_account import PortfolioAccount
from portfolio.engine.strategy_compiler import compile_strategy


@dataclass(frozen=True)
class ReplayConfig:
    initial_capital: float = 1000000.0
    max_position_pct: float = 15.0
    slippage_bps: float = 0.0
    brokerage_bps: float = 0.0


@dataclass
class ReplayResult:
    events: list[str] = field(default_factory=list)
    trade_ledger: list[dict[str, Any]] = field(default_factory=list)
    nav_history: list[dict[str, Any]] = field(default_factory=list)
    positions: list[dict[str, Any]] = field(default_factory=list)


def run_replay(df: pd.DataFrame, strategy_specs: list[dict[str, Any]], config: ReplayConfig) -> ReplayResult:
    data = _normalize(df)
    strategies = [compile_strategy(raw) for raw in strategy_specs]
    account = PortfolioAccount(initial_capital=config.initial_capital)
    execution = NextOpenExecutionModel(slippage_bps=config.slippage_bps, brokerage_bps=config.brokerage_bps)
    result = ReplayResult()
    pending_orders: list[Order] = []
    order_seq = 0

    for as_of, day in data.groupby("date", sort=True):
        date_str = str(pd.to_datetime(as_of).date())
        result.events.append("MarketDataEvent")

        for order in list(pending_orders):
            bar = day[day["symbol"] == order.symbol]
            if bar.empty:
                continue
            fill = execution.try_fill(order, bar.iloc[0])
            if fill:
                account.apply_fill(fill.as_dict())
                result.trade_ledger.append(fill.as_dict())
                pending_orders.remove(order)

        result.events.append("SignalEvent")
        signals: list[tuple[str, str]] = []
        for _, row in day.iterrows():
            for strategy in strategies:
                symbol = str(row["symbol"]).upper()
                if symbol not in account.positions and strategy.should_enter(row):
                    signals.append((strategy.spec.strategy_id, symbol))
                elif symbol in account.positions and strategy.should_exit(row):
                    position = account.positions[symbol]
                    order_seq += 1
                    pending_orders.append(
                        Order(
                            order_id=f"ord_{order_seq}",
                            strategy_id=strategy.spec.strategy_id,
                            symbol=symbol,
                            side=OrderSide.SELL,
                            order_type=OrderType.MARKET_NEXT_OPEN,
                            quantity=position.quantity,
                            created_date=date_str,
                        )
                    )

        result.events.append("PortfolioTargetEvent")
        result.events.append("RiskCheckEvent")
        result.events.append("OrderEvent")
        for strategy_id, symbol in signals:
            if symbol in account.positions:
                continue
            row = day[day["symbol"] == symbol].iloc[0]
            price = float(row["close"])
            budget = account.cash * (config.max_position_pct / 100.0)
            quantity = int(budget // price)
            if quantity <= 0:
                continue
            order_seq += 1
            pending_orders.append(
                Order(
                    order_id=f"ord_{order_seq}",
                    strategy_id=strategy_id,
                    symbol=symbol,
                    side=OrderSide.BUY,
                    order_type=OrderType.MARKET_NEXT_OPEN,
                    quantity=quantity,
                    created_date=date_str,
                )
            )

        result.events.extend(["FillEvent", "StopEvent", "ExitEvent", "AddEvent", "AccountingEvent"])
        prices = {str(row["symbol"]).upper(): float(row["close"]) for _, row in day.iterrows()}
        account.mark_to_market(prices, date_str)
        result.events.append("ReportEvent")

    result.nav_history = list(account.nav_history)
    result.positions = account.positions_as_dicts()
    return result


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    out = df.rename(columns={col: col.strip().lower() for col in df.columns}).copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out["symbol"] = out["symbol"].astype(str).str.upper()
    for col in ("open", "high", "low", "close"):
        out[col] = pd.to_numeric(out[col], errors="coerce")
    return out.dropna(subset=["date", "symbol", "open", "high", "low", "close"]).sort_values(["date", "symbol"])
```

- [ ] **Step 5: Run tests to verify GREEN**

Run:

```bash
.venv/bin/python -m pytest tests/portfolio/test_event_loop.py -q
```

Expected: `2 passed`.

- [ ] **Step 6: Commit event loop**

```bash
git add portfolio/engine/events.py portfolio/engine/event_loop.py tests/portfolio/test_event_loop.py
git commit -m "feat: add deterministic paper replay loop"
```

## Task 5: Metrics, Audit Log, And Report Agent

**Files:**
- Create: `portfolio/engine/metrics.py`
- Create: `portfolio/engine/audit_log.py`
- Create: `portfolio/agents/report_agent.py`
- Test: `tests/portfolio/test_metrics_report.py`

- [ ] **Step 1: Write failing metrics/report tests**

Create `tests/portfolio/test_metrics_report.py`:

```python
from __future__ import annotations

import json

from portfolio.agents.report_agent import write_daily_report
from portfolio.engine.audit_log import append_agent_action
from portfolio.engine.metrics import compute_nav_metrics


def test_compute_nav_metrics_returns_total_return_and_drawdown():
    rows = [
        {"date": "2025-01-01", "nav": 100000.0},
        {"date": "2025-01-02", "nav": 105000.0},
        {"date": "2025-01-03", "nav": 102000.0},
    ]

    metrics = compute_nav_metrics(rows)

    assert metrics["total_return_pct"] == 2.0
    assert metrics["max_drawdown_pct"] == -2.8571


def test_audit_log_writes_jsonl(tmp_path):
    path = tmp_path / "agent_actions.jsonl"

    append_agent_action(path, agent="report_agent", run_id="r1", decision="write_report", rationale="test", outputs={"ok": True})

    row = json.loads(path.read_text().strip())
    assert row["agent"] == "report_agent"
    assert row["status"] == "accepted"


def test_report_agent_writes_required_sections(tmp_path):
    path = write_daily_report(
        output_dir=tmp_path,
        report_date="2025-01-03",
        nav_metrics={"total_return_pct": 2.0, "max_drawdown_pct": -2.8571},
        replay_summary={"trades": 1, "open_positions": 1},
    )

    text = path.read_text()
    assert "# Paper Portfolio Daily Report - 2025-01-03" in text
    assert "## Portfolio NAV And P&L" in text
    assert "## Agent Action Log Summary" in text
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/portfolio/test_metrics_report.py -q
```

Expected: FAIL because modules do not exist.

- [ ] **Step 3: Implement metrics**

Create `portfolio/engine/metrics.py`:

```python
from __future__ import annotations

from typing import Any


def compute_nav_metrics(nav_rows: list[dict[str, Any]]) -> dict[str, float | int | None]:
    if not nav_rows:
        return {"observations": 0, "total_return_pct": None, "max_drawdown_pct": None}
    navs = [float(row["nav"]) for row in nav_rows]
    start = navs[0]
    end = navs[-1]
    peak = navs[0]
    max_drawdown = 0.0
    for nav in navs:
        peak = max(peak, nav)
        if peak:
            max_drawdown = min(max_drawdown, (nav / peak - 1.0) * 100.0)
    return {
        "observations": len(navs),
        "total_return_pct": round((end / start - 1.0) * 100.0, 4) if start else None,
        "max_drawdown_pct": round(max_drawdown, 4),
    }
```

- [ ] **Step 4: Implement audit log**

Create `portfolio/engine/audit_log.py`:

```python
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


def append_agent_action(
    path: str | Path,
    *,
    agent: str,
    run_id: str,
    decision: str,
    rationale: str,
    outputs: dict[str, Any],
    status: str = "accepted",
    input_refs: list[str] | None = None,
) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "timestamp": datetime.now(ZoneInfo("Asia/Kolkata")).isoformat(),
        "agent": agent,
        "run_id": run_id,
        "input_refs": input_refs or [],
        "decision": decision,
        "rationale": rationale,
        "outputs": outputs,
        "status": status,
    }
    with target.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")
```

- [ ] **Step 5: Implement report agent**

Create `portfolio/agents/report_agent.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any


def write_daily_report(
    *,
    output_dir: str | Path,
    report_date: str,
    nav_metrics: dict[str, Any],
    replay_summary: dict[str, Any],
) -> Path:
    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"paper_portfolio_daily_{report_date}.md"
    body = f"""# Paper Portfolio Daily Report - {report_date}

## Executive Summary

Paper replay generated {int(replay_summary.get("trades") or 0)} fills and has {int(replay_summary.get("open_positions") or 0)} open positions.

## Portfolio NAV And P&L

- Total return: {nav_metrics.get("total_return_pct")}%
- Max drawdown: {nav_metrics.get("max_drawdown_pct")}%

## Active Strategies And Allocation

Strategy allocation detail is emitted by the portfolio manager in later phases.

## New Paper Trades

See `trade_ledger.csv` for fill-level detail.

## Open Risk

Open risk checks are emitted by the monitoring agent in later phases.

## Strategy Leaderboard

Strategy leaderboard is emitted in later phases after multi-strategy replay is enabled.

## Stage 2 Signal Performance

Stage 2 attribution is emitted in later phases after PostgreSQL signal history is connected.

## Agent Action Log Summary

Agent action details are stored in `agent_actions.jsonl`.

## Next-Day Watchlist And Plan

Next-day watchlist is emitted by the report agent after live data integration.
"""
    path.write_text(body, encoding="utf-8")
    return path
```

- [ ] **Step 6: Run tests to verify GREEN**

Run:

```bash
.venv/bin/python -m pytest tests/portfolio/test_metrics_report.py -q
```

Expected: `3 passed`.

- [ ] **Step 7: Commit metrics/report**

```bash
git add portfolio/engine/metrics.py portfolio/engine/audit_log.py portfolio/agents/report_agent.py tests/portfolio/test_metrics_report.py
git commit -m "feat: add paper metrics audit report"
```

## Task 6: CLI Replay

**Files:**
- Create: `portfolio/cli.py`
- Test: `tests/portfolio/test_cli.py`

- [ ] **Step 1: Write failing CLI smoke test**

Create `tests/portfolio/test_cli.py`:

```python
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

from tests.portfolio.fixtures import sample_ohlcv, valid_strategy_spec


def test_cli_replay_writes_outputs(tmp_path):
    data_path = tmp_path / "ohlcv.csv"
    strategy_path = tmp_path / "strategy.json"
    output_dir = tmp_path / "out"
    sample_ohlcv().to_csv(data_path, index=False)
    strategy_path.write_text(json.dumps(valid_strategy_spec()), encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "portfolio.cli",
            "replay",
            "--data",
            str(data_path),
            "--strategy",
            str(strategy_path),
            "--output-dir",
            str(output_dir),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    assert (output_dir / "logs" / "daily_nav.csv").exists()
    assert (output_dir / "logs" / "trade_ledger.csv").exists()
    assert list((output_dir / "reports" / "daily").glob("paper_portfolio_daily_*.md"))
```

- [ ] **Step 2: Run test to verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/portfolio/test_cli.py -q
```

Expected: FAIL because `portfolio.cli` does not exist.

- [ ] **Step 3: Implement CLI**

Create `portfolio/cli.py`:

```python
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from portfolio.agents.report_agent import write_daily_report
from portfolio.engine.audit_log import append_agent_action
from portfolio.engine.event_loop import ReplayConfig, run_replay
from portfolio.engine.metrics import compute_nav_metrics


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="portfolio")
    sub = parser.add_subparsers(dest="command", required=True)
    replay = sub.add_parser("replay")
    replay.add_argument("--data", required=True)
    replay.add_argument("--strategy", required=True)
    replay.add_argument("--output-dir", default="portfolio/data")
    replay.add_argument("--initial-capital", type=float, default=1000000.0)
    args = parser.parse_args(argv)
    if args.command == "replay":
        return _cmd_replay(args)
    return 2


def _cmd_replay(args: argparse.Namespace) -> int:
    output_dir = Path(args.output_dir)
    logs_dir = output_dir / "logs"
    reports_dir = output_dir / "reports" / "daily"
    logs_dir.mkdir(parents=True, exist_ok=True)
    data = pd.read_csv(args.data)
    strategy = json.loads(Path(args.strategy).read_text(encoding="utf-8"))
    result = run_replay(data, [strategy], ReplayConfig(initial_capital=args.initial_capital))
    nav_df = pd.DataFrame(result.nav_history)
    trade_df = pd.DataFrame(result.trade_ledger)
    nav_df.to_csv(logs_dir / "daily_nav.csv", index=False)
    trade_df.to_csv(logs_dir / "trade_ledger.csv", index=False)
    metrics = compute_nav_metrics(result.nav_history)
    report_date = str(nav_df["date"].iloc[-1]) if not nav_df.empty else "no_data"
    write_daily_report(
        output_dir=reports_dir,
        report_date=report_date,
        nav_metrics=metrics,
        replay_summary={"trades": len(result.trade_ledger), "open_positions": len(result.positions)},
    )
    append_agent_action(
        logs_dir / "agent_actions.jsonl",
        agent="report_agent",
        run_id=f"replay_{report_date}",
        decision="write_replay_outputs",
        rationale="CLI replay completed deterministic paper run.",
        outputs={"nav_rows": len(result.nav_history), "fills": len(result.trade_ledger)},
    )
    print(f"Replay complete: {output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run CLI test to verify GREEN**

Run:

```bash
.venv/bin/python -m pytest tests/portfolio/test_cli.py -q
```

Expected: `1 passed`.

- [ ] **Step 5: Run full Phase 1 test set**

Run:

```bash
.venv/bin/python -m pytest tests/portfolio -q
```

Expected: all Phase 1 portfolio tests pass.

- [ ] **Step 6: Commit CLI**

```bash
git add portfolio/cli.py tests/portfolio/test_cli.py
git commit -m "feat: add paper replay cli"
```

## Task 7: Documentation And Verification

**Files:**
- Create: `portfolio/README.md`
- Modify: none outside `portfolio/` and `tests/portfolio/`

- [ ] **Step 1: Write README**

Create `portfolio/README.md`:

```markdown
# Paper Trading Strategy Lab

This package contains Agent Adda's local paper-trading strategy lab.

Phase 1 is deterministic and does not call an LLM. It validates structured strategy specs, replays EOD fixture data, simulates next-open paper fills, writes trade/NAV logs, and generates a Markdown daily report.

## Run A Fixture Replay

```bash
.venv/bin/python -m portfolio.cli replay \
  --data /path/to/ohlcv.csv \
  --strategy /path/to/strategy.json \
  --output-dir /tmp/paper-run
```

Outputs:

- `logs/daily_nav.csv`
- `logs/trade_ledger.csv`
- `logs/agent_actions.jsonl`
- `reports/daily/paper_portfolio_daily_<date>.md`

## Current Limits

- Paper trading only.
- EOD replay only.
- Market-next-open order fills only in Phase 1.
- Static strategy specs only in Phase 1.
- No broker integration.
```

- [ ] **Step 2: Run verification**

Run:

```bash
.venv/bin/python -m pytest tests/portfolio -q
```

Expected: all tests pass.

- [ ] **Step 3: Check git status for touched files**

Run:

```bash
git status --short portfolio tests/portfolio docs/superpowers/plans/2026-05-31-paper-trading-engine-foundation.md
```

Expected: only intended files are modified or untracked.

- [ ] **Step 4: Commit README**

```bash
git add portfolio/README.md
git commit -m "docs: document paper trading foundation"
```

## Plan Coverage Checklist

- Strategy schema and risk clamping: Task 2.
- Deterministic paper orders and fills: Task 3.
- Account and NAV tracking: Task 3.
- Event replay order: Task 4.
- Metrics and report output: Task 5.
- JSONL agent action logging: Task 5.
- CLI replay path: Task 6.
- Documentation: Task 7.

This plan intentionally defers PostgreSQL data access, LLM strategy proposal, parameter sweeps, walk-forward validation, multi-order simulation, HTML reports, and monitoring to follow-up plans after the deterministic core is green.
