# Strategy Council Simulation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a first-class Strategy Council simulation loop where a strategist LLM proposes stock-specific EOD trading strategies, deterministic tools backtest them, two critic LLMs challenge the results, the strategist revises for 2-3 iterations, and the system presents a research-only final recommendation with full evidence, test discipline, and audit trail.

**Architecture:** Add a focused `backtesting/strategy_council/` package above the existing deterministic `backtesting/` engine. The council layer collects evidence, builds candidate strategy specs, compiles them into a constrained DSL, runs train/validation/test backtests, captures critic feedback, iterates, and renders a Markdown/terminal report. LLM calls must be injected behind small interfaces so tests use deterministic fakes and production can use OpenAI/Ollama.

**Tech Stack:** Python 3.10+, pandas, existing `backtesting.engine`, `backtesting.strategy_registry`, `terminal.tools`, `terminal/backtest.py`, PostgreSQL persistence where available, unittest, Markdown report output under `reports/strategy_council/`.

---

## Product Contract

### Command Surface

```text
/strategy-council DMART
/strategy-council DMART --horizon 1w,2w,4w --iterations 3
/strategy-council DMART --from 2022-01-01 --validation-from 2025-01-01 --test-from 2026-01-01
/strategy-council DMART --strategies stage2,supertrend_continuation,rsi_pullback_stage2,vcp
/assess DMART --with-strategy-council
```

### Output Contract

Every response must include:

1. Evidence pack summary with freshness labels.
2. Iteration-by-iteration candidate strategies.
3. Backtest metrics for train and validation before final lock.
4. Critic feedback from:
   - data/leakage critic
   - market/risk critic
5. Strategist revision notes.
6. Final locked strategy.
7. One-shot test metrics after the final strategy is locked.
8. Best horizon among 1w, 2w, and 4w.
9. Recommendation: `TRADE_RESEARCH`, `WAIT`, or `NO_TRADE`.
10. Research-only disclaimer and missing-data/source trail.

### Guardrails

- Test-period data must not be visible to the strategist or critics before final lock.
- Strategy search budget is capped: default 5 candidates per iteration, 3 iterations.
- If train/validation trade count is too low, the result is marked `LOW_CONFIDENCE`.
- Missing fundamentals/news/breadth must be explicit, not inferred.
- The deterministic backtester, not the LLM, calculates returns and metrics.
- The final answer must not present investment advice; it is research and decision support only.

---

## File Structure

| Path | Responsibility |
|---|---|
| `backtesting/strategy_council/__init__.py` | Public package exports |
| `backtesting/strategy_council/types.py` | Dataclasses for evidence, strategy specs, critique, iteration, final result |
| `backtesting/strategy_council/evidence.py` | Build a point-in-time evidence pack from existing data/tools |
| `backtesting/strategy_council/dsl.py` | Constrained strategy DSL and compiler from strategist proposal to executable spec |
| `backtesting/strategy_council/splits.py` | Time-based train/validation/test split builder |
| `backtesting/strategy_council/runner.py` | Deterministic horizon backtest runner for strategy specs |
| `backtesting/strategy_council/llm.py` | LLM interfaces plus rule-based fallback strategist/critics |
| `backtesting/strategy_council/council.py` | Iterative strategist -> backtest -> critics -> revise orchestration |
| `backtesting/strategy_council/report.py` | Markdown report renderer and report writer |
| `terminal/strategy_council.py` | Slash-command parser/handler |
| `nse_agent.py` | Route `/strategy-council` before generic LLM handling |
| `tests/test_strategy_council_types.py` | Dataclass and DSL contract tests |
| `tests/test_strategy_council_evidence.py` | Evidence-pack tests |
| `tests/test_strategy_council_runner.py` | Split and backtest runner tests |
| `tests/test_strategy_council_loop.py` | Iterative council tests using fake LLMs |
| `tests/test_nse_agent_strategy_council.py` | Terminal command integration tests |
| `docs/AGENT_ADDA_CAPABILITIES.md` | Add command reference |

---

## Phase 1: Core Contracts

### Task 1: Strategy Council Types

**Files:**
- Create: `backtesting/strategy_council/__init__.py`
- Create: `backtesting/strategy_council/types.py`
- Test: `tests/test_strategy_council_types.py`

- [ ] **Step 1: Write the failing tests**

```python
import unittest

from backtesting.strategy_council.types import (
    CouncilConfig,
    Critique,
    EvidencePack,
    StrategySpec,
)


class StrategyCouncilTypesTests(unittest.TestCase):
    def test_council_config_defaults_to_three_horizons_and_three_iterations(self):
        cfg = CouncilConfig(symbol="DMART")

        self.assertEqual(cfg.symbol, "DMART")
        self.assertEqual(cfg.horizons, (5, 10, 20))
        self.assertEqual(cfg.iterations, 3)
        self.assertEqual(cfg.max_candidates, 5)
        self.assertEqual(cfg.recommendation_threshold, "validation_then_test")

    def test_strategy_spec_has_audit_fields(self):
        spec = StrategySpec(
            strategy_id="stage2",
            horizon_days=10,
            entry_rules=("stage == Stage 2",),
            exit_rules=("close < sma_50",),
            risk_rules=("max_position_pct=10",),
            thesis="Stage 2 continuation with RS support.",
        )

        self.assertEqual(spec.strategy_id, "stage2")
        self.assertEqual(spec.horizon_days, 10)
        self.assertIn("Stage 2", spec.entry_rules[0])
        self.assertEqual(spec.status, "candidate")

    def test_evidence_pack_exposes_missing_data(self):
        pack = EvidencePack(symbol="DMART", as_of="2026-05-14", freshness={"eod": "fresh"})
        pack.missing.append("news")

        self.assertIn("news", pack.missing)
        self.assertEqual(pack.freshness["eod"], "fresh")

    def test_critique_blocks_data_leakage(self):
        critique = Critique(
            critic="data_leakage",
            verdict="reject",
            issues=("test-period metric used before final lock",),
            required_changes=("remove test metric from strategist context",),
        )

        self.assertEqual(critique.verdict, "reject")
        self.assertIn("test-period", critique.issues[0])
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python3 -m unittest tests.test_strategy_council_types -v
```

Expected: fail with `ModuleNotFoundError: No module named 'backtesting.strategy_council'`.

- [ ] **Step 3: Implement minimal types**

Create `backtesting/strategy_council/__init__.py`:

```python
"""Iterative Strategy Council simulation for EOD strategy research."""
```

Create `backtesting/strategy_council/types.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


Recommendation = Literal["TRADE_RESEARCH", "WAIT", "NO_TRADE"]


@dataclass(frozen=True)
class CouncilConfig:
    symbol: str
    horizons: tuple[int, ...] = (5, 10, 20)
    iterations: int = 3
    max_candidates: int = 5
    initial_capital: float = 100000.0
    from_date: str | None = None
    validation_from: str | None = None
    test_from: str | None = None
    allowed_strategies: tuple[str, ...] = (
        "stage2",
        "supertrend_continuation",
        "rsi_pullback_stage2",
        "52w_high",
        "vcp",
    )
    recommendation_threshold: str = "validation_then_test"


@dataclass
class EvidencePack:
    symbol: str
    as_of: str
    technical: dict[str, Any] = field(default_factory=dict)
    fundamental: dict[str, Any] = field(default_factory=dict)
    market: dict[str, Any] = field(default_factory=dict)
    news: list[dict[str, Any]] = field(default_factory=list)
    freshness: dict[str, str] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)
    source_trail: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class StrategySpec:
    strategy_id: str
    horizon_days: int
    entry_rules: tuple[str, ...]
    exit_rules: tuple[str, ...]
    risk_rules: tuple[str, ...]
    thesis: str
    params: dict[str, Any] = field(default_factory=dict)
    status: str = "candidate"


@dataclass(frozen=True)
class BacktestSliceResult:
    split: str
    strategy_id: str
    horizon_days: int
    metrics: dict[str, Any]
    trade_count: int


@dataclass(frozen=True)
class Critique:
    critic: str
    verdict: str
    issues: tuple[str, ...] = ()
    required_changes: tuple[str, ...] = ()
    confidence_delta: float = 0.0


@dataclass(frozen=True)
class CouncilIteration:
    index: int
    candidates: tuple[StrategySpec, ...]
    train_results: tuple[BacktestSliceResult, ...]
    validation_results: tuple[BacktestSliceResult, ...]
    critiques: tuple[Critique, ...]
    strategist_revision: str


@dataclass(frozen=True)
class CouncilResult:
    config: CouncilConfig
    evidence: EvidencePack
    iterations: tuple[CouncilIteration, ...]
    locked_strategy: StrategySpec | None
    test_results: tuple[BacktestSliceResult, ...]
    recommendation: Recommendation
    rationale: str
    report_path: str | None = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
python3 -m unittest tests.test_strategy_council_types -v
```

Expected: all tests pass.

---

## Phase 2: Evidence Pack

### Task 2: Evidence Builder with Explicit Missing Data

**Files:**
- Create: `backtesting/strategy_council/evidence.py`
- Test: `tests/test_strategy_council_evidence.py`

- [ ] **Step 1: Write the failing tests**

```python
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from backtesting.strategy_council.evidence import build_evidence_pack


class StrategyCouncilEvidenceTests(unittest.TestCase):
    def test_build_evidence_pack_reads_latest_symbol_eod_and_marks_missing_optional_sources(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "data").mkdir()
            pd.DataFrame(
                [
                    {"SYMBOL": "DMART", "TIMESTAMP": "2026-05-10", "OPEN": 100, "HIGH": 110, "LOW": 95, "CLOSE": 105, "TOTTRDQTY": 1000},
                    {"SYMBOL": "DMART", "TIMESTAMP": "2026-05-11", "OPEN": 105, "HIGH": 112, "LOW": 101, "CLOSE": 111, "TOTTRDQTY": 1200},
                    {"SYMBOL": "TCS", "TIMESTAMP": "2026-05-11", "OPEN": 200, "HIGH": 205, "LOW": 198, "CLOSE": 202, "TOTTRDQTY": 900},
                ]
            ).to_csv(root / "data" / "nse_sec_full_data.csv", index=False)

            pack = build_evidence_pack("DMART", project_root=root)

        self.assertEqual(pack.symbol, "DMART")
        self.assertEqual(pack.as_of, "2026-05-11")
        self.assertEqual(pack.technical["close"], 111.0)
        self.assertEqual(pack.technical["volume"], 1200.0)
        self.assertIn("fundamentals", pack.missing)
        self.assertIn("news", pack.missing)
        self.assertIn("data/nse_sec_full_data.csv", " ".join(pack.source_trail))
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python3 -m unittest tests.test_strategy_council_evidence -v
```

Expected: fail because `backtesting.strategy_council.evidence` does not exist.

- [ ] **Step 3: Implement minimal evidence builder**

Create `backtesting/strategy_council/evidence.py`:

```python
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from backtesting.strategy_council.types import EvidencePack


def _project_root(project_root: Path | None) -> Path:
    return Path(project_root) if project_root is not None else Path.cwd()


def _normalize_eod(df: pd.DataFrame) -> pd.DataFrame:
    out = df.rename(columns={c: c.strip().lower() for c in df.columns}).copy()
    if "timestamp" in out.columns and "date" not in out.columns:
        out = out.rename(columns={"timestamp": "date"})
    if "tottrdqty" in out.columns and "volume" not in out.columns:
        out = out.rename(columns={"tottrdqty": "volume"})
    out["symbol"] = out["symbol"].astype(str).str.upper()
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    for col in ("open", "high", "low", "close", "volume"):
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    return out.dropna(subset=["symbol", "date", "close"]).sort_values(["symbol", "date"])


def build_evidence_pack(symbol: str, *, project_root: Path | None = None) -> EvidencePack:
    root = _project_root(project_root)
    sym = symbol.strip().upper()
    eod_path = root / "data" / "nse_sec_full_data.csv"
    pack = EvidencePack(symbol=sym, as_of=date.today().isoformat())

    if not eod_path.exists():
        pack.missing.append("eod")
        pack.source_trail.append(f"{eod_path}: missing")
        return pack

    df = _normalize_eod(pd.read_csv(eod_path))
    sdf = df[df["symbol"] == sym]
    if sdf.empty:
        pack.missing.append("eod_symbol")
        pack.source_trail.append(f"data/nse_sec_full_data.csv: {sym} not found")
        return pack

    latest = sdf.iloc[-1]
    pack.as_of = latest["date"].date().isoformat()
    pack.technical.update(
        {
            "open": float(latest["open"]) if "open" in latest else None,
            "high": float(latest["high"]) if "high" in latest else None,
            "low": float(latest["low"]) if "low" in latest else None,
            "close": float(latest["close"]),
            "volume": float(latest["volume"]) if "volume" in latest and pd.notna(latest["volume"]) else None,
            "bars": int(len(sdf)),
        }
    )
    pack.freshness["eod"] = "available"
    pack.source_trail.append("data/nse_sec_full_data.csv: ok")

    for optional in ("fundamentals", "market_breadth", "news", "sentiment", "latest_results"):
        pack.missing.append(optional)
    return pack
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
python3 -m unittest tests.test_strategy_council_evidence -v
```

Expected: all tests pass.

---

## Phase 3: Strategy DSL and Split Discipline

### Task 3: Constrained Strategy DSL Compiler

**Files:**
- Create: `backtesting/strategy_council/dsl.py`
- Modify: `tests/test_strategy_council_types.py`

- [ ] **Step 1: Add failing DSL tests**

Append to `tests/test_strategy_council_types.py`:

```python
from backtesting.strategy_council.dsl import compile_strategy_proposal


class StrategyCouncilDSLTests(unittest.TestCase):
    def test_compile_strategy_proposal_accepts_registered_strategy_and_horizon(self):
        spec = compile_strategy_proposal(
            {
                "strategy_id": "stage2",
                "horizon_days": 10,
                "entry_rules": ["stage == Stage 2"],
                "exit_rules": ["close < sma_50"],
                "risk_rules": ["max_position_pct=10"],
                "thesis": "Stage 2 continuation.",
            },
            allowed_strategies=("stage2", "vcp"),
            allowed_horizons=(5, 10, 20),
        )

        self.assertEqual(spec.strategy_id, "stage2")
        self.assertEqual(spec.horizon_days, 10)

    def test_compile_strategy_proposal_rejects_unregistered_strategy(self):
        with self.assertRaisesRegex(ValueError, "not allowed"):
            compile_strategy_proposal(
                {
                    "strategy_id": "unsafe_python",
                    "horizon_days": 10,
                    "entry_rules": ["eval(user_code)"],
                    "exit_rules": ["close < sma_50"],
                    "risk_rules": ["max_position_pct=10"],
                    "thesis": "Unsafe.",
                },
                allowed_strategies=("stage2",),
                allowed_horizons=(5, 10, 20),
            )
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python3 -m unittest tests.test_strategy_council_types -v
```

Expected: fail because `compile_strategy_proposal` does not exist.

- [ ] **Step 3: Implement DSL compiler**

Create `backtesting/strategy_council/dsl.py`:

```python
from __future__ import annotations

from typing import Any

from backtesting.strategy_council.types import StrategySpec


_FORBIDDEN_TOKENS = ("eval", "exec", "__", "import", "open(", "subprocess", "os.", "sys.")


def _clean_rules(value: Any, field: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or not value:
        raise ValueError(f"{field} must be a non-empty list")
    rules = tuple(str(item).strip() for item in value if str(item).strip())
    if not rules:
        raise ValueError(f"{field} must contain at least one rule")
    lowered = " ".join(rules).lower()
    if any(token in lowered for token in _FORBIDDEN_TOKENS):
        raise ValueError(f"{field} contains forbidden executable content")
    return rules


def compile_strategy_proposal(
    proposal: dict[str, Any],
    *,
    allowed_strategies: tuple[str, ...],
    allowed_horizons: tuple[int, ...],
) -> StrategySpec:
    strategy_id = str(proposal.get("strategy_id", "")).strip().lower().replace("-", "_")
    if strategy_id not in allowed_strategies:
        raise ValueError(f"Strategy '{strategy_id}' is not allowed")
    horizon = int(proposal.get("horizon_days", 0))
    if horizon not in allowed_horizons:
        raise ValueError(f"Horizon '{horizon}' is not allowed")
    thesis = str(proposal.get("thesis", "")).strip()
    if not thesis:
        raise ValueError("thesis is required")
    return StrategySpec(
        strategy_id=strategy_id,
        horizon_days=horizon,
        entry_rules=_clean_rules(proposal.get("entry_rules"), "entry_rules"),
        exit_rules=_clean_rules(proposal.get("exit_rules"), "exit_rules"),
        risk_rules=_clean_rules(proposal.get("risk_rules"), "risk_rules"),
        thesis=thesis,
        params=dict(proposal.get("params") or {}),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
python3 -m unittest tests.test_strategy_council_types -v
```

Expected: all tests pass.

### Task 4: Train/Validation/Test Split Builder

**Files:**
- Create: `backtesting/strategy_council/splits.py`
- Test: `tests/test_strategy_council_runner.py`

- [ ] **Step 1: Write failing split tests**

```python
import unittest

import pandas as pd

from backtesting.strategy_council.splits import build_time_splits


class StrategyCouncilRunnerTests(unittest.TestCase):
    def test_build_time_splits_keeps_test_data_separate(self):
        df = pd.DataFrame(
            {
                "date": pd.date_range("2024-01-01", periods=500, freq="D"),
                "symbol": ["DMART"] * 500,
                "open": range(500),
                "high": range(1, 501),
                "low": range(500),
                "close": range(1, 501),
                "volume": [1000] * 500,
            }
        )

        splits = build_time_splits(df, validation_from="2025-01-01", test_from="2025-06-01")

        self.assertLess(splits["train"]["date"].max(), pd.Timestamp("2025-01-01"))
        self.assertLess(splits["validation"]["date"].max(), pd.Timestamp("2025-06-01"))
        self.assertGreaterEqual(splits["test"]["date"].min(), pd.Timestamp("2025-06-01"))
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python3 -m unittest tests.test_strategy_council_runner -v
```

Expected: fail because `build_time_splits` does not exist.

- [ ] **Step 3: Implement split builder**

Create `backtesting/strategy_council/splits.py`:

```python
from __future__ import annotations

import pandas as pd


def build_time_splits(
    df: pd.DataFrame,
    *,
    validation_from: str | None = None,
    test_from: str | None = None,
) -> dict[str, pd.DataFrame]:
    data = df.copy()
    if "timestamp" in data.columns and "date" not in data.columns:
        data = data.rename(columns={"timestamp": "date"})
    data["date"] = pd.to_datetime(data["date"], errors="coerce")
    data = data.dropna(subset=["date"]).sort_values("date")

    if data.empty:
        return {"train": data.copy(), "validation": data.copy(), "test": data.copy()}

    min_date = data["date"].min()
    max_date = data["date"].max()
    validation_cut = pd.Timestamp(validation_from) if validation_from else min_date + (max_date - min_date) * 0.60
    test_cut = pd.Timestamp(test_from) if test_from else min_date + (max_date - min_date) * 0.80

    return {
        "train": data[data["date"] < validation_cut].copy(),
        "validation": data[(data["date"] >= validation_cut) & (data["date"] < test_cut)].copy(),
        "test": data[data["date"] >= test_cut].copy(),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
python3 -m unittest tests.test_strategy_council_runner -v
```

Expected: all current runner tests pass.

---

## Phase 4: Deterministic Horizon Runner

### Task 5: Candidate Backtest Runner

**Files:**
- Create: `backtesting/strategy_council/runner.py`
- Modify: `tests/test_strategy_council_runner.py`

- [ ] **Step 1: Add failing runner tests**

Append to `tests/test_strategy_council_runner.py`:

```python
from backtesting.strategy_council.runner import run_strategy_spec_on_split
from backtesting.strategy_council.types import StrategySpec


class StrategyCouncilSpecRunnerTests(unittest.TestCase):
    def test_run_strategy_spec_returns_metrics_without_exposing_test_when_split_is_train(self):
        df = pd.DataFrame(
            {
                "date": pd.date_range("2024-01-01", periods=260, freq="D"),
                "symbol": ["DMART"] * 260,
                "open": [100 + i for i in range(260)],
                "high": [102 + i for i in range(260)],
                "low": [99 + i for i in range(260)],
                "close": [101 + i for i in range(260)],
                "volume": [1000] * 260,
            }
        )
        spec = StrategySpec(
            strategy_id="stage2",
            horizon_days=10,
            entry_rules=("stage == Stage 2",),
            exit_rules=("close < sma_50",),
            risk_rules=("max_position_pct=10",),
            thesis="Stage 2 continuation.",
        )

        result = run_strategy_spec_on_split(df, spec, split_name="train", initial_capital=100000)

        self.assertEqual(result.split, "train")
        self.assertEqual(result.strategy_id, "stage2")
        self.assertIn("total_return_pct", result.metrics)
        self.assertEqual(result.horizon_days, 10)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python3 -m unittest tests.test_strategy_council_runner -v
```

Expected: fail because `runner.py` does not exist.

- [ ] **Step 3: Implement minimal strategy runner**

Create `backtesting/strategy_council/runner.py`:

```python
from __future__ import annotations

import pandas as pd

from backtesting.engine import BacktestConfig, run_backtest
from backtesting.strategy_council.types import BacktestSliceResult, StrategySpec


def run_strategy_spec_on_split(
    df: pd.DataFrame,
    spec: StrategySpec,
    *,
    split_name: str,
    initial_capital: float,
) -> BacktestSliceResult:
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
    return BacktestSliceResult(
        split=split_name,
        strategy_id=spec.strategy_id,
        horizon_days=spec.horizon_days,
        metrics=result.metrics,
        trade_count=int(result.metrics.get("trade_count") or 0),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
python3 -m unittest tests.test_strategy_council_runner -v
```

Expected: all runner tests pass.

---

## Phase 5: Strategist and Critics

### Task 6: LLM Interfaces with Rule-Based Fallbacks

**Files:**
- Create: `backtesting/strategy_council/llm.py`
- Test: `tests/test_strategy_council_loop.py`

- [ ] **Step 1: Write failing interface tests**

```python
import unittest

from backtesting.strategy_council.llm import RuleBasedRiskCritic, RuleBasedStrategist
from backtesting.strategy_council.types import BacktestSliceResult, CouncilConfig, EvidencePack


class StrategyCouncilLoopTests(unittest.TestCase):
    def test_rule_based_strategist_returns_bounded_candidates(self):
        strategist = RuleBasedStrategist()
        config = CouncilConfig(symbol="DMART", max_candidates=2)
        evidence = EvidencePack(symbol="DMART", as_of="2026-05-14", technical={"close": 100, "bars": 260})

        candidates = strategist.propose(evidence=evidence, config=config, prior_feedback=())

        self.assertLessEqual(len(candidates), 2)
        self.assertTrue(all(c.strategy_id in config.allowed_strategies for c in candidates))

    def test_rule_based_risk_critic_rejects_zero_trade_results(self):
        critic = RuleBasedRiskCritic()
        critique = critic.critique(
            candidates=(),
            train_results=(
                BacktestSliceResult("train", "stage2", 10, {"total_return_pct": 0}, 0),
            ),
            validation_results=(),
        )

        self.assertEqual(critique.verdict, "revise")
        self.assertIn("trade count", " ".join(critique.issues).lower())
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python3 -m unittest tests.test_strategy_council_loop -v
```

Expected: fail because `llm.py` does not exist.

- [ ] **Step 3: Implement strategist and critics**

Create `backtesting/strategy_council/llm.py`:

```python
from __future__ import annotations

from typing import Protocol

from backtesting.strategy_council.types import (
    BacktestSliceResult,
    CouncilConfig,
    Critique,
    EvidencePack,
    StrategySpec,
)


class Strategist(Protocol):
    def propose(
        self,
        *,
        evidence: EvidencePack,
        config: CouncilConfig,
        prior_feedback: tuple[Critique, ...],
    ) -> tuple[StrategySpec, ...]:
        ...


class Critic(Protocol):
    def critique(
        self,
        *,
        candidates: tuple[StrategySpec, ...],
        train_results: tuple[BacktestSliceResult, ...],
        validation_results: tuple[BacktestSliceResult, ...],
    ) -> Critique:
        ...


class RuleBasedStrategist:
    def propose(
        self,
        *,
        evidence: EvidencePack,
        config: CouncilConfig,
        prior_feedback: tuple[Critique, ...],
    ) -> tuple[StrategySpec, ...]:
        proposals: list[StrategySpec] = []
        for strategy_id in config.allowed_strategies:
            for horizon in config.horizons:
                proposals.append(
                    StrategySpec(
                        strategy_id=strategy_id,
                        horizon_days=horizon,
                        entry_rules=(f"{strategy_id} entry confirmation",),
                        exit_rules=(f"{strategy_id} exit or horizon {horizon} days",),
                        risk_rules=("max_position_pct=10", "next_open_execution", "research_only"),
                        thesis=f"{strategy_id} candidate for {config.symbol} over {horizon} trading days.",
                    )
                )
                if len(proposals) >= config.max_candidates:
                    return tuple(proposals)
        return tuple(proposals)


class RuleBasedDataLeakageCritic:
    def critique(
        self,
        *,
        candidates: tuple[StrategySpec, ...],
        train_results: tuple[BacktestSliceResult, ...],
        validation_results: tuple[BacktestSliceResult, ...],
    ) -> Critique:
        issues: list[str] = []
        if not candidates:
            issues.append("No candidate strategies were proposed.")
        if any(result.split == "test" for result in train_results + validation_results):
            issues.append("Test split appeared before final lock.")
        verdict = "revise" if issues else "accept"
        return Critique(
            critic="data_leakage",
            verdict=verdict,
            issues=tuple(issues),
            required_changes=("hide test metrics until final lock",) if issues else (),
        )


class RuleBasedRiskCritic:
    def critique(
        self,
        *,
        candidates: tuple[StrategySpec, ...],
        train_results: tuple[BacktestSliceResult, ...],
        validation_results: tuple[BacktestSliceResult, ...],
    ) -> Critique:
        all_results = train_results + validation_results
        issues: list[str] = []
        if not all_results or all(result.trade_count == 0 for result in all_results):
            issues.append("Trade count is too low for a reliable conclusion.")
        validation_returns = [
            result.metrics.get("total_return_pct")
            for result in validation_results
            if isinstance(result.metrics.get("total_return_pct"), (int, float))
        ]
        if validation_returns and max(validation_returns) < 0:
            issues.append("All validation returns are negative.")
        verdict = "revise" if issues else "accept"
        return Critique(
            critic="market_risk",
            verdict=verdict,
            issues=tuple(issues),
            required_changes=("tighten filters or return NO_TRADE",) if issues else (),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
python3 -m unittest tests.test_strategy_council_loop -v
```

Expected: all current loop tests pass.

---

## Phase 6: Iterative Council Orchestration

### Task 7: Council Loop with 2 Critics and Final Test Lock

**Files:**
- Create: `backtesting/strategy_council/council.py`
- Modify: `tests/test_strategy_council_loop.py`

- [ ] **Step 1: Add failing orchestration tests**

Append to `tests/test_strategy_council_loop.py`:

```python
import pandas as pd

from backtesting.strategy_council.council import run_strategy_council


class StrategyCouncilOrchestrationTests(unittest.TestCase):
    def test_council_runs_iterations_then_only_runs_test_after_lock(self):
        df = pd.DataFrame(
            {
                "date": pd.date_range("2024-01-01", periods=520, freq="D"),
                "symbol": ["DMART"] * 520,
                "open": [100 + i * 0.2 for i in range(520)],
                "high": [101 + i * 0.2 for i in range(520)],
                "low": [99 + i * 0.2 for i in range(520)],
                "close": [100.5 + i * 0.2 for i in range(520)],
                "volume": [1000] * 520,
            }
        )
        config = CouncilConfig(symbol="DMART", iterations=2, max_candidates=2)
        evidence = EvidencePack(symbol="DMART", as_of="2026-05-14", technical={"close": 200, "bars": 520})

        result = run_strategy_council(df, evidence=evidence, config=config)

        self.assertEqual(len(result.iterations), 2)
        self.assertIsNotNone(result.locked_strategy)
        self.assertTrue(result.test_results)
        self.assertTrue(all(r.split == "test" for r in result.test_results))
        self.assertIn(result.recommendation, {"TRADE_RESEARCH", "WAIT", "NO_TRADE"})
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python3 -m unittest tests.test_strategy_council_loop -v
```

Expected: fail because `run_strategy_council` does not exist.

- [ ] **Step 3: Implement council loop**

Create `backtesting/strategy_council/council.py`:

```python
from __future__ import annotations

import pandas as pd

from backtesting.strategy_council.llm import (
    RuleBasedDataLeakageCritic,
    RuleBasedRiskCritic,
    RuleBasedStrategist,
)
from backtesting.strategy_council.runner import run_strategy_spec_on_split
from backtesting.strategy_council.splits import build_time_splits
from backtesting.strategy_council.types import (
    CouncilConfig,
    CouncilIteration,
    CouncilResult,
    Critique,
    EvidencePack,
    Recommendation,
    StrategySpec,
)


def _score_result(result) -> float:
    ret = result.metrics.get("total_return_pct")
    trades = result.trade_count
    if not isinstance(ret, (int, float)):
        return -999.0
    trade_penalty = 10.0 if trades == 0 else 0.0
    return float(ret) - trade_penalty


def _select_best(
    candidates: tuple[StrategySpec, ...],
    validation_results: tuple,
) -> StrategySpec | None:
    if not candidates or not validation_results:
        return candidates[0] if candidates else None
    best_result = max(validation_results, key=_score_result)
    for candidate in candidates:
        if candidate.strategy_id == best_result.strategy_id and candidate.horizon_days == best_result.horizon_days:
            return candidate
    return candidates[0]


def _recommend(test_results: tuple) -> Recommendation:
    if not test_results:
        return "NO_TRADE"
    best = max(test_results, key=_score_result)
    ret = best.metrics.get("total_return_pct")
    if not isinstance(ret, (int, float)) or best.trade_count == 0:
        return "NO_TRADE"
    if ret > 2:
        return "TRADE_RESEARCH"
    return "WAIT"


def run_strategy_council(
    eod_data: pd.DataFrame,
    *,
    evidence: EvidencePack,
    config: CouncilConfig,
    strategist=None,
    critics=None,
) -> CouncilResult:
    strategist = strategist or RuleBasedStrategist()
    critics = critics or (RuleBasedDataLeakageCritic(), RuleBasedRiskCritic())
    splits = build_time_splits(
        eod_data,
        validation_from=config.validation_from,
        test_from=config.test_from,
    )

    iterations: list[CouncilIteration] = []
    prior_feedback: tuple[Critique, ...] = ()
    last_candidates: tuple[StrategySpec, ...] = ()
    last_validation_results: tuple = ()

    for idx in range(1, config.iterations + 1):
        candidates = strategist.propose(evidence=evidence, config=config, prior_feedback=prior_feedback)
        train_results = tuple(
            run_strategy_spec_on_split(splits["train"], spec, split_name="train", initial_capital=config.initial_capital)
            for spec in candidates
        )
        validation_results = tuple(
            run_strategy_spec_on_split(splits["validation"], spec, split_name="validation", initial_capital=config.initial_capital)
            for spec in candidates
        )
        critiques = tuple(
            critic.critique(
                candidates=candidates,
                train_results=train_results,
                validation_results=validation_results,
            )
            for critic in critics
        )
        revision = "; ".join(
            change for critique in critiques for change in critique.required_changes
        ) or "No forced revision; continue with strongest validation candidate."
        iterations.append(
            CouncilIteration(
                index=idx,
                candidates=candidates,
                train_results=train_results,
                validation_results=validation_results,
                critiques=critiques,
                strategist_revision=revision,
            )
        )
        prior_feedback = critiques
        last_candidates = candidates
        last_validation_results = validation_results

    locked = _select_best(last_candidates, last_validation_results)
    test_results = ()
    if locked is not None:
        test_results = (
            run_strategy_spec_on_split(
                splits["test"],
                locked,
                split_name="test",
                initial_capital=config.initial_capital,
            ),
        )

    recommendation = _recommend(test_results)
    rationale = (
        "Final recommendation is based on validation-selected strategy and one-shot test results. "
        "This is research-only output, not investment advice."
    )
    return CouncilResult(
        config=config,
        evidence=evidence,
        iterations=tuple(iterations),
        locked_strategy=locked,
        test_results=test_results,
        recommendation=recommendation,
        rationale=rationale,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
python3 -m unittest tests.test_strategy_council_loop -v
```

Expected: all loop tests pass.

---

## Phase 7: Report Renderer

### Task 8: Markdown Report Writer

**Files:**
- Create: `backtesting/strategy_council/report.py`
- Test: `tests/test_strategy_council_report.py`

- [ ] **Step 1: Write failing report tests**

```python
import tempfile
import unittest
from pathlib import Path

from backtesting.strategy_council.report import render_council_markdown, write_council_report
from backtesting.strategy_council.types import CouncilConfig, CouncilResult, EvidencePack, StrategySpec


class StrategyCouncilReportTests(unittest.TestCase):
    def test_render_council_markdown_includes_guardrails_and_recommendation(self):
        result = CouncilResult(
            config=CouncilConfig(symbol="DMART"),
            evidence=EvidencePack(symbol="DMART", as_of="2026-05-14", missing=["news"]),
            iterations=(),
            locked_strategy=StrategySpec("stage2", 10, ("entry",), ("exit",), ("risk",), "thesis"),
            test_results=(),
            recommendation="WAIT",
            rationale="Research-only.",
        )

        md = render_council_markdown(result)

        self.assertIn("Strategy Council", md)
        self.assertIn("DMART", md)
        self.assertIn("WAIT", md)
        self.assertIn("Missing Data", md)
        self.assertIn("not investment advice", md.lower())

    def test_write_council_report_creates_markdown_file(self):
        result = CouncilResult(
            config=CouncilConfig(symbol="DMART"),
            evidence=EvidencePack(symbol="DMART", as_of="2026-05-14"),
            iterations=(),
            locked_strategy=None,
            test_results=(),
            recommendation="NO_TRADE",
            rationale="No valid strategy.",
        )
        with tempfile.TemporaryDirectory() as td:
            path = write_council_report(result, output_dir=Path(td))

        self.assertTrue(path.exists())
        self.assertIn("DMART", path.read_text())
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python3 -m unittest tests.test_strategy_council_report -v
```

Expected: fail because report module does not exist.

- [ ] **Step 3: Implement report renderer**

Create `backtesting/strategy_council/report.py`:

```python
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from backtesting.strategy_council.types import CouncilResult


def _metrics_table(results) -> list[str]:
    lines = ["| Split | Strategy | Horizon | Trades | Return % | P&L |", "|---|---|---:|---:|---:|---:|"]
    for result in results:
        lines.append(
            "| {split} | {strategy} | {horizon} | {trades} | {ret} | {pnl} |".format(
                split=result.split,
                strategy=result.strategy_id,
                horizon=result.horizon_days,
                trades=result.trade_count,
                ret=result.metrics.get("total_return_pct"),
                pnl=result.metrics.get("total_pnl"),
            )
        )
    return lines


def render_council_markdown(result: CouncilResult) -> str:
    lines = [
        f"# Strategy Council — {result.config.symbol}",
        "",
        f"Generated: {datetime.now().isoformat(timespec='seconds')}",
        f"Evidence as of: {result.evidence.as_of}",
        f"Recommendation: **{result.recommendation}**",
        "",
        "## Evidence Pack",
        f"- Symbol: `{result.evidence.symbol}`",
        f"- Technical: `{result.evidence.technical}`",
        f"- Freshness: `{result.evidence.freshness}`",
        "",
        "## Missing Data",
    ]
    if result.evidence.missing:
        lines.extend(f"- {item}" for item in result.evidence.missing)
    else:
        lines.append("- None reported")

    lines.extend(["", "## Iterations"])
    if not result.iterations:
        lines.append("- No iterations captured.")
    for iteration in result.iterations:
        lines.append(f"### Iteration {iteration.index}")
        lines.append(f"- Candidates: {len(iteration.candidates)}")
        lines.append(f"- Strategist revision: {iteration.strategist_revision}")
        lines.extend(_metrics_table(iteration.train_results + iteration.validation_results))
        lines.append("")
        for critique in iteration.critiques:
            lines.append(f"- Critic `{critique.critic}`: {critique.verdict}; issues={list(critique.issues)}")

    lines.extend(["", "## Locked Strategy"])
    if result.locked_strategy:
        lines.append(f"- Strategy: `{result.locked_strategy.strategy_id}`")
        lines.append(f"- Horizon: {result.locked_strategy.horizon_days} trading days")
        lines.append(f"- Thesis: {result.locked_strategy.thesis}")
    else:
        lines.append("- No strategy locked.")

    lines.extend(["", "## Final One-Shot Test"])
    lines.extend(_metrics_table(result.test_results) if result.test_results else ["- No test result."])
    lines.extend(
        [
            "",
            "## Rationale",
            result.rationale,
            "",
            "## Disclaimer",
            "This is AI-assisted research and deterministic backtesting output, not investment advice.",
        ]
    )
    return "\n".join(lines)


def write_council_report(result: CouncilResult, *, output_dir: Path | None = None) -> Path:
    out_dir = output_dir or Path("reports") / "strategy_council"
    out_dir.mkdir(parents=True, exist_ok=True)
    suffix = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = out_dir / f"strategy_council_{result.config.symbol}_{suffix}.md"
    path.write_text(render_council_markdown(result), encoding="utf-8")
    return path
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
python3 -m unittest tests.test_strategy_council_report -v
```

Expected: all report tests pass.

---

## Phase 8: Terminal Command Integration

### Task 9: `/strategy-council` Command Handler

**Files:**
- Create: `terminal/strategy_council.py`
- Modify: `nse_agent.py`
- Test: `tests/test_nse_agent_strategy_council.py`

- [ ] **Step 1: Write failing terminal tests**

```python
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from terminal.strategy_council import handle_strategy_council_command, parse_strategy_council_command


class NSEAgentStrategyCouncilTests(unittest.TestCase):
    def test_parse_strategy_council_command_defaults(self):
        cfg = parse_strategy_council_command("/strategy-council DMART")

        self.assertEqual(cfg.symbol, "DMART")
        self.assertEqual(cfg.horizons, (5, 10, 20))
        self.assertEqual(cfg.iterations, 3)

    def test_handle_strategy_council_command_runs_and_writes_report(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "data").mkdir()
            pd.DataFrame(
                {
                    "SYMBOL": ["DMART"] * 520,
                    "TIMESTAMP": pd.date_range("2024-01-01", periods=520, freq="D"),
                    "OPEN": [100 + i * 0.2 for i in range(520)],
                    "HIGH": [101 + i * 0.2 for i in range(520)],
                    "LOW": [99 + i * 0.2 for i in range(520)],
                    "CLOSE": [100.5 + i * 0.2 for i in range(520)],
                    "TOTTRDQTY": [1000] * 520,
                }
            ).to_csv(root / "data" / "nse_sec_full_data.csv", index=False)

            output = handle_strategy_council_command("/strategy-council DMART --iterations 1", project_root=root)

        self.assertIn("Strategy Council", output)
        self.assertIn("DMART", output)
        self.assertIn("Recommendation", output)
        self.assertIn("Report:", output)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python3 -m unittest tests.test_nse_agent_strategy_council -v
```

Expected: fail because `terminal.strategy_council` does not exist.

- [ ] **Step 3: Implement command handler**

Create `terminal/strategy_council.py`:

```python
from __future__ import annotations

import shlex
from pathlib import Path

import pandas as pd

from backtesting.strategy_council.council import run_strategy_council
from backtesting.strategy_council.evidence import build_evidence_pack
from backtesting.strategy_council.report import write_council_report
from backtesting.strategy_council.types import CouncilConfig


def _parse_horizons(raw: str | None) -> tuple[int, ...]:
    if not raw:
        return (5, 10, 20)
    mapping = {"1w": 5, "2w": 10, "4w": 20}
    values: list[int] = []
    for part in raw.split(","):
        item = part.strip().lower()
        values.append(mapping.get(item, int(item) if item.isdigit() else 0))
    cleaned = tuple(v for v in values if v > 0)
    return cleaned or (5, 10, 20)


def _arg(parts: list[str], name: str, default: str | None = None) -> str | None:
    if name not in parts:
        return default
    idx = parts.index(name)
    if idx + 1 >= len(parts):
        raise ValueError(f"Missing value for {name}")
    return parts[idx + 1]


def parse_strategy_council_command(text: str) -> CouncilConfig:
    parts = shlex.split(text)
    if len(parts) < 2:
        raise ValueError("Usage: /strategy-council SYMBOL [--horizon 1w,2w,4w] [--iterations 3]")
    symbol = parts[1].upper()
    strategies = _arg(parts, "--strategies")
    return CouncilConfig(
        symbol=symbol,
        horizons=_parse_horizons(_arg(parts, "--horizon")),
        iterations=int(_arg(parts, "--iterations", "3") or "3"),
        max_candidates=int(_arg(parts, "--max-candidates", "5") or "5"),
        from_date=_arg(parts, "--from"),
        validation_from=_arg(parts, "--validation-from"),
        test_from=_arg(parts, "--test-from"),
        allowed_strategies=tuple(s.strip().lower().replace("-", "_") for s in strategies.split(",")) if strategies else CouncilConfig(symbol=symbol).allowed_strategies,
    )


def _load_symbol_eod(symbol: str, root: Path, from_date: str | None) -> pd.DataFrame:
    path = root / "data" / "nse_sec_full_data.csv"
    df = pd.read_csv(path)
    df = df.rename(columns={c: c.strip().lower() for c in df.columns})
    if "timestamp" in df.columns and "date" not in df.columns:
        df = df.rename(columns={"timestamp": "date"})
    if "tottrdqty" in df.columns and "volume" not in df.columns:
        df = df.rename(columns={"tottrdqty": "volume"})
    df["symbol"] = df["symbol"].astype(str).str.upper()
    df = df[df["symbol"] == symbol.upper()].copy()
    if from_date:
        df = df[pd.to_datetime(df["date"], errors="coerce") >= pd.Timestamp(from_date)]
    return df


def handle_strategy_council_command(text: str, *, project_root: Path | None = None) -> str:
    root = Path(project_root or Path.cwd())
    try:
        config = parse_strategy_council_command(text)
        evidence = build_evidence_pack(config.symbol, project_root=root)
        eod = _load_symbol_eod(config.symbol, root, config.from_date)
        result = run_strategy_council(eod, evidence=evidence, config=config)
        report = write_council_report(result, output_dir=root / "reports" / "strategy_council")
    except Exception as exc:
        return f"Strategy Council failed: {exc}"

    return "\n".join(
        [
            f"Strategy Council — {config.symbol}",
            f"Recommendation: {result.recommendation}",
            f"Locked strategy: {result.locked_strategy.strategy_id if result.locked_strategy else 'none'}",
            f"Iterations: {len(result.iterations)}",
            f"Report: {report}",
            "Mode: EOD Strategy Council simulation; research-only, not investment advice.",
        ]
    )
```

- [ ] **Step 4: Route command in `nse_agent.py`**

Find the direct command block where `/backtest` and `/strategy-lab` are routed. Add:

```python
if query.strip().lower().startswith("/strategy-council"):
    from terminal.strategy_council import handle_strategy_council_command

    console.print(Markdown(handle_strategy_council_command(query)))
    return
```

Also add the same routing in the interactive loop branch where typed commands are handled:

```python
if text.lower().startswith("/strategy-council"):
    from terminal.strategy_council import handle_strategy_council_command

    console.print(Markdown(handle_strategy_council_command(text)))
    continue
```

- [ ] **Step 5: Run tests to verify they pass**

Run:

```bash
python3 -m unittest tests.test_nse_agent_strategy_council -v
```

Expected: all terminal tests pass.

---

## Phase 9: Capabilities Documentation

### Task 10: Update Agent Adda Capabilities

**Files:**
- Modify: `docs/AGENT_ADDA_CAPABILITIES.md`

- [ ] **Step 1: Add the Strategy Council section**

Insert after the EOD Strategy Lab section:

```markdown
### E2. STRATEGY COUNCIL SIMULATION 🧠🧪 (`/strategy-council`)

The Strategy Council is an iterative research simulator. A strategist proposes stock-specific EOD strategies, deterministic tools backtest train/validation data, two critics challenge data leakage and risk, the strategist revises for 2-3 iterations, and a final locked strategy is tested once on the held-out test split.

| Command | What It Does |
|---|---|
| `/strategy-council DMART` | Run default 1w/2w/4w Strategy Council simulation |
| `/strategy-council DMART --iterations 3` | Run three strategist/critic revision loops |
| `/strategy-council DMART --horizon 1w,2w,4w` | Explicit horizons |
| `/strategy-council DMART --from 2022-01-01 --test-from 2026-01-01` | Explicit time split |

Guardrails:
- Test data is hidden until the final strategy is locked.
- LLMs propose and critique; deterministic tools calculate metrics.
- Missing evidence is shown explicitly.
- Output is research-only and not investment advice.
```

- [ ] **Step 2: Verify docs contain command**

Run:

```bash
rg -n "/strategy-council|STRATEGY COUNCIL" docs/AGENT_ADDA_CAPABILITIES.md
```

Expected: at least five matches.

---

## Phase 10: Comprehensive Verification

### Task 11: Focused Test Suite

**Files:**
- No production edits.

- [ ] **Step 1: Compile changed files**

Run:

```bash
python3 -m py_compile \
  backtesting/strategy_council/types.py \
  backtesting/strategy_council/evidence.py \
  backtesting/strategy_council/dsl.py \
  backtesting/strategy_council/splits.py \
  backtesting/strategy_council/runner.py \
  backtesting/strategy_council/llm.py \
  backtesting/strategy_council/council.py \
  backtesting/strategy_council/report.py \
  terminal/strategy_council.py \
  nse_agent.py
```

Expected: exit code 0.

- [ ] **Step 2: Run all Strategy Council tests**

Run:

```bash
python3 -m unittest \
  tests.test_strategy_council_types \
  tests.test_strategy_council_evidence \
  tests.test_strategy_council_runner \
  tests.test_strategy_council_loop \
  tests.test_strategy_council_report \
  tests.test_nse_agent_strategy_council \
  -v
```

Expected: all tests pass.

- [ ] **Step 3: Run existing backtesting regression**

Run:

```bash
python3 -m unittest \
  tests.test_backtesting_data \
  tests.test_backtesting_engine \
  tests.test_backtesting_portfolio \
  tests.test_backtesting_strategy_registry \
  tests.test_backtesting_patterns \
  tests.test_nse_agent_backtest \
  -v
```

Expected: all tests pass.

- [ ] **Step 4: Run a real local smoke test**

Run:

```bash
python3 nse_agent.py --query "/strategy-council DMART --iterations 1 --horizon 2w"
```

Expected:
- Output contains `Strategy Council — DMART`.
- Output contains `Recommendation:`.
- Output contains `Report: reports/strategy_council/...`.
- No answer claims investment advice.

- [ ] **Step 5: Inspect generated report**

Run:

```bash
ls -t reports/strategy_council/*.md | head -1 | xargs sed -n '1,220p'
```

Expected:
- Includes evidence pack.
- Includes iteration section.
- Includes locked strategy.
- Includes final one-shot test.
- Includes disclaimer.

---

## Future Extensions After MVP

| Extension | Description | Dependency |
|---|---|---|
| Executable `supertrend_continuation` | Implement true Supertrend strategy in deterministic engine | MVP command flow stable |
| Executable `rsi_pullback_stage2` | Add RSI pullback entry/exit rules | Feature library maturity |
| Executable `vcp` | Use existing VCP detector as backtest entry policy | VCP detector accuracy review |
| Monte Carlo equity curve | Bootstrap trade list to estimate confidence intervals | More trades per strategy |
| Regime-conditioned scoring | Show performance by risk-on/risk-off, breadth, sector regime | Regime history depth |
| PostgreSQL council persistence | Completed: `/strategy-council ... --persist` stores runs, iterations, candidates, critiques, split results, final recommendation, and report path in the `strategy_council` PostgreSQL schema | `backtesting/strategy_council/postgres_storage.py` |
| HTML report | Add visual dashboard with iteration timeline and metrics tables | Markdown report accepted |
| Portfolio mode | Run council over watchlist/portfolio and rank best opportunities | Single-symbol MVP stable |
| Intraday council | Add 15m data support and stricter execution modeling | Intraday data pipeline stable |
