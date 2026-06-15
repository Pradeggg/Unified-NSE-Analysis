# Breakout Retest Strategy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the approved EOD breakout-retest strategy family across PostgreSQL replay features, strategy lab, paper trading risk outputs, Agent Adda queries, and reports.

**Architecture:** Add a focused feature module that derives point-in-time `br_*` evidence from daily OHLCV plus existing technical and fundamental columns. Strategy definitions consume those stable fields through the existing schema/compiler, while stop/risk/report/Agent Adda layers read the same evidence instead of re-detecting the pattern.

**Tech Stack:** Python 3.13, pandas, PostgreSQL replay data, existing `portfolio` strategy engine, Agent Adda terminal modules, pytest.

---

## File Map

- Create `portfolio/features/__init__.py`: feature package export boundary.
- Create `portfolio/features/breakout_retest.py`: no-lookahead breakout, retest, confirmation, score, and risk-flag derivation.
- Modify `portfolio/data_sources/postgres.py`: call `add_breakout_retest_features()` in `prepare_replay_frame()` and include `br_*` columns in `_FEATURE_COLUMNS`.
- Modify `portfolio/engine/strategy_schema.py`: allow numeric `br_*` strategy indicators and a structure-aware initial stop type.
- Modify `portfolio/engine/strategy_library.py`: add the six built-in breakout-retest variants.
- Modify `portfolio/engine/strategy_compiler.py`: calculate structure-aware stop prices for strategies that request them.
- Modify `portfolio/engine/event_loop.py`: size entries and gap-risk checks from the structure-aware stop distance.
- Modify `portfolio/engine/paper_portfolio.py`: expose pivot/retest/stop/target/risk flags in paper-trading position, order, and fill rows.
- Modify `portfolio/cli.py`: ensure strategy-lab output includes the new variants and candidate evidence columns.
- Modify `terminal/reports.py` and `terminal/swing_playbook.py`: add breakout-retest report sections using the derived fields.
- Create `terminal/breakout_retest.py`: Agent Adda query helper for latest breakout-retest candidates and variant comparison.
- Modify Agent Adda routing files after locating the active intent/situation hooks with `rg -n "situation|intent|prompt library|quality-breakouts|screen" terminal nse_agent.py`: route breakout-retest NLP prompts to `terminal.breakout_retest`.
- Add tests under `tests/portfolio/` and `tests/` to lock feature derivation, schema/library behavior, stop handling, reports, and Agent Adda response shape.

## Task 1: Derived Feature Layer

**Files:**
- Create: `portfolio/features/__init__.py`
- Create: `portfolio/features/breakout_retest.py`
- Modify: `portfolio/data_sources/postgres.py`
- Test: `tests/portfolio/test_breakout_retest_features.py`
- Test: `tests/portfolio/test_postgres_strategy_lab.py`

- [ ] **Step 1: Write failing unit tests for no-lookahead feature derivation**

Add `tests/portfolio/test_breakout_retest_features.py`:

```python
from __future__ import annotations

import pandas as pd

from portfolio.features.breakout_retest import add_breakout_retest_features


def _frame(closes: list[float], *, lows: list[float] | None = None, highs: list[float] | None = None) -> pd.DataFrame:
    rows = []
    lows = lows or [price * 0.99 for price in closes]
    highs = highs or [price * 1.01 for price in closes]
    for idx, close in enumerate(closes):
        rows.append(
            {
                "date": pd.Timestamp("2026-01-01") + pd.Timedelta(days=idx),
                "symbol": "ABC",
                "open": close * 0.99,
                "high": highs[idx],
                "low": lows[idx],
                "close": close,
                "volume": 100_000 + idx,
                "volume_ratio_20d": 1.0,
                "stage": "STAGE_2",
                "sma_20": 100.0,
                "sma_50": 95.0,
                "sma_200": 80.0,
                "relative_strength": 75.0,
                "atr_14": 3.0,
                "latest_result_age_days": 120.0,
                "sales_growth_pct": 12.0,
                "pat_growth_pct": 14.0,
                "eps_growth_pct": 15.0,
                "opm_yoy_delta": 1.0,
                "debt_to_equity": 0.4,
                "roe_pct": 14.0,
                "roce_pct": 17.0,
            }
        )
    return pd.DataFrame(rows)


def test_pivot_uses_prior_20_day_high_and_excludes_current_bar():
    frame = _frame([100.0] * 20 + [130.0])
    result = add_breakout_retest_features(frame)

    last = result.iloc[-1]
    assert last["br_pivot_20d"] == 101.0
    assert last["br_breakout_signal"] == 1
    assert last["br_breakout_close_pct"] > 20.0


def test_retest_hold_allows_two_percent_intraday_dip_and_close_above_pivot():
    closes = [100.0] * 20 + [105.0, 101.5]
    highs = [101.0] * 20 + [106.0, 103.0]
    lows = [99.0] * 20 + [103.0, 98.5]
    result = add_breakout_retest_features(_frame(closes, highs=highs, lows=lows))

    retest = result.iloc[-1]
    assert retest["br_retest_hold"] == 1
    assert retest["br_retest_date"] == str(pd.Timestamp("2026-01-22").date())
    assert retest["br_retest_high"] == 103.0
    assert retest["br_retest_depth_pct"] < 0


def test_confirmation_requires_a_prior_retest_bar():
    closes = [100.0] * 20 + [105.0, 101.5, 104.0]
    highs = [101.0] * 20 + [106.0, 103.0, 104.5]
    lows = [99.0] * 20 + [103.0, 98.5, 102.0]
    result = add_breakout_retest_features(_frame(closes, highs=highs, lows=lows))

    assert result.iloc[-2]["br_confirm_after_retest"] == 0
    assert result.iloc[-1]["br_confirm_after_retest"] == 1


def test_failed_breakout_triggers_after_close_more_than_two_percent_below_pivot():
    closes = [100.0] * 20 + [105.0, 97.5]
    highs = [101.0] * 20 + [106.0, 100.0]
    lows = [99.0] * 20 + [103.0, 96.0]
    result = add_breakout_retest_features(_frame(closes, highs=highs, lows=lows))

    assert result.iloc[-1]["br_failed"] == 1
    assert "failed_breakout" in result.iloc[-1]["br_risk_flags"]


def test_missing_fundamentals_reduce_score_without_disqualifying_setup():
    frame = _frame([100.0] * 20 + [105.0, 101.5])
    frame[["sales_growth_pct", "pat_growth_pct", "eps_growth_pct", "roe_pct", "roce_pct"]] = 0.0
    frame["latest_result_age_days"] = 9999.0

    result = add_breakout_retest_features(frame)

    assert result.iloc[-1]["br_retest_hold"] == 1
    assert result.iloc[-1]["br_setup_score"] < 70
    assert "missing_fundamentals" in result.iloc[-1]["br_risk_flags"]
```

- [ ] **Step 2: Run the feature tests and verify they fail because the module does not exist**

Run:

```bash
.venv/bin/python -m pytest tests/portfolio/test_breakout_retest_features.py -q
```

Expected:

```text
ModuleNotFoundError: No module named 'portfolio.features'
```

- [ ] **Step 3: Add the feature package and implementation**

Add `portfolio/features/__init__.py`:

```python
"""Portfolio feature derivation helpers."""
```

Add `portfolio/features/breakout_retest.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class BreakoutRetestConfig:
    pivot_lookback: int = 20
    retest_tolerance_pct: float = 2.0
    failure_pct: float = 2.0
    breakout_volume_preferred: float = 1.2


BR_COLUMNS = (
    "br_pivot_20d",
    "br_breakout_signal",
    "br_breakout_date",
    "br_days_since_breakout",
    "br_retest_low_pct",
    "br_retest_hold",
    "br_retest_date",
    "br_retest_high",
    "br_retest_low",
    "br_confirm_after_retest",
    "br_failed",
    "br_volume_quality",
    "br_setup_score",
    "br_risk_flags",
    "br_pivot_distance_pct",
    "br_breakout_volume_ratio",
    "br_retest_volume_ratio",
    "br_breakout_close_pct",
    "br_retest_depth_pct",
)


def add_breakout_retest_features(
    frame: pd.DataFrame,
    *,
    config: BreakoutRetestConfig | None = None,
) -> pd.DataFrame:
    cfg = config or BreakoutRetestConfig()
    if frame.empty:
        result = frame.copy()
        for column in BR_COLUMNS:
            result[column] = "" if column in {"br_breakout_date", "br_retest_date", "br_risk_flags"} else 0.0
        return result

    required = {"date", "symbol", "high", "low", "close"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"breakout retest features require columns: {sorted(missing)}")

    result = frame.copy()
    result["date"] = pd.to_datetime(result["date"], errors="coerce")
    result = result.sort_values(["symbol", "date"]).reset_index(drop=True)

    pieces = [_derive_symbol(group, cfg) for _, group in result.groupby("symbol", group_keys=False)]
    return pd.concat(pieces, ignore_index=True).sort_values(["symbol", "date"]).reset_index(drop=True)


def _derive_symbol(group: pd.DataFrame, cfg: BreakoutRetestConfig) -> pd.DataFrame:
    out = group.copy().reset_index(drop=True)
    out["br_pivot_20d"] = out["high"].rolling(cfg.pivot_lookback, min_periods=cfg.pivot_lookback).max().shift(1)
    out["br_pivot_distance_pct"] = _pct(out["close"], out["br_pivot_20d"])
    out["br_breakout_signal"] = ((out["close"] > out["br_pivot_20d"]) & out["br_pivot_20d"].notna()).astype(int)
    out["br_breakout_date"] = ""
    out["br_days_since_breakout"] = 0
    out["br_retest_low_pct"] = 0.0
    out["br_retest_hold"] = 0
    out["br_retest_date"] = ""
    out["br_retest_high"] = 0.0
    out["br_retest_low"] = 0.0
    out["br_confirm_after_retest"] = 0
    out["br_failed"] = 0
    out["br_breakout_volume_ratio"] = 0.0
    out["br_retest_volume_ratio"] = 0.0
    out["br_breakout_close_pct"] = 0.0
    out["br_retest_depth_pct"] = 0.0
    out["br_volume_quality"] = 0.0
    out["br_setup_score"] = 0.0
    out["br_risk_flags"] = ""

    active_breakout_date = ""
    active_pivot = 0.0
    active_breakout_volume = 0.0
    active_retest_date = ""
    active_retest_high = 0.0
    active_retest_low = 0.0
    active_failed = False

    for idx, row in out.iterrows():
        pivot = _number(row.get("br_pivot_20d"))
        close = _number(row.get("close"))
        high = _number(row.get("high"))
        low = _number(row.get("low"))
        volume_ratio = _number(row.get("volume_ratio_20d")) or 0.0
        date = _date_string(row.get("date"))

        if pivot is not None and close is not None and close > pivot:
            if int(row.get("br_breakout_signal") or 0) == 1 and not active_retest_date:
                active_breakout_date = date
                active_pivot = pivot
                active_breakout_volume = volume_ratio
                active_retest_date = ""
                active_retest_high = 0.0
                active_retest_low = 0.0
                active_failed = False

        if active_breakout_date and active_pivot > 0:
            breakout_date = pd.to_datetime(active_breakout_date)
            current_date = pd.to_datetime(date)
            days_since = max(0, int((current_date - breakout_date).days))
            out.at[idx, "br_breakout_date"] = active_breakout_date
            out.at[idx, "br_days_since_breakout"] = days_since
            out.at[idx, "br_breakout_volume_ratio"] = active_breakout_volume
            if close is not None:
                out.at[idx, "br_breakout_close_pct"] = (close - active_pivot) / active_pivot * 100.0

            if close is not None and close < active_pivot * (1.0 - cfg.failure_pct / 100.0):
                active_failed = True

            retest_depth = (low - active_pivot) / active_pivot * 100.0 if low is not None else 0.0
            out.at[idx, "br_retest_low_pct"] = retest_depth
            out.at[idx, "br_retest_depth_pct"] = retest_depth
            is_after_breakout = date != active_breakout_date
            if (
                is_after_breakout
                and not active_failed
                and low is not None
                and close is not None
                and low >= active_pivot * (1.0 - cfg.retest_tolerance_pct / 100.0)
                and close >= active_pivot
                and low <= active_pivot * (1.0 + cfg.retest_tolerance_pct / 100.0)
            ):
                active_retest_date = date
                active_retest_high = high or 0.0
                active_retest_low = low
                out.at[idx, "br_retest_hold"] = 1
                out.at[idx, "br_retest_volume_ratio"] = volume_ratio

            if active_retest_date:
                out.at[idx, "br_retest_date"] = active_retest_date
                out.at[idx, "br_retest_high"] = active_retest_high
                out.at[idx, "br_retest_low"] = active_retest_low
                if date != active_retest_date and high is not None and close is not None:
                    out.at[idx, "br_confirm_after_retest"] = int(high > active_retest_high and close >= active_pivot)

            out.at[idx, "br_failed"] = int(active_failed)
            score, flags = _score(row, volume_ratio=volume_ratio, active_failed=active_failed, config=cfg)
            out.at[idx, "br_volume_quality"] = _volume_quality(active_breakout_volume, volume_ratio, cfg)
            out.at[idx, "br_setup_score"] = score
            out.at[idx, "br_risk_flags"] = "|".join(flags)
            if active_failed:
                active_breakout_date = ""
                active_retest_date = ""
                active_pivot = 0.0

    return out


def _pct(value: pd.Series, reference: pd.Series) -> pd.Series:
    return ((value - reference) / reference.replace(0, pd.NA) * 100.0).fillna(0.0)


def _date_string(value: Any) -> str:
    parsed = pd.to_datetime(value, errors="coerce")
    return "" if pd.isna(parsed) else str(parsed.date())


def _number(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if pd.notna(parsed) else None


def _volume_quality(breakout_volume: float, retest_volume: float, cfg: BreakoutRetestConfig) -> float:
    score = 50.0
    if breakout_volume >= cfg.breakout_volume_preferred:
        score += 25.0
    if retest_volume <= max(breakout_volume, cfg.breakout_volume_preferred):
        score += 25.0
    return min(100.0, score)


def _score(
    row: pd.Series,
    *,
    volume_ratio: float,
    active_failed: bool,
    config: BreakoutRetestConfig,
) -> tuple[float, list[str]]:
    score = 50.0
    flags: list[str] = []
    if str(row.get("stage") or "") == "STAGE_2":
        score += 10.0
    else:
        flags.append("not_stage_2")
        score -= 10.0
    if _number(row.get("relative_strength")) is not None and float(row.get("relative_strength")) >= 65:
        score += 10.0
    else:
        flags.append("weak_relative_strength")
        score -= 8.0
    if _number(row.get("close")) and _number(row.get("sma_50")) and float(row["close"]) > float(row["sma_50"]):
        score += 6.0
    if _number(row.get("sma_50")) and _number(row.get("sma_200")) and float(row["sma_50"]) > float(row["sma_200"]):
        score += 6.0
    if volume_ratio >= config.breakout_volume_preferred:
        score += 6.0
    else:
        flags.append("weak_volume")
        score -= 4.0

    fundamentals_present = any((_number(row.get(column)) or 0.0) != 0.0 for column in ("sales_growth_pct", "pat_growth_pct", "eps_growth_pct", "roe_pct", "roce_pct"))
    if not fundamentals_present or (_number(row.get("latest_result_age_days")) or 9999.0) >= 9999.0:
        flags.append("missing_fundamentals")
        score -= 12.0
    else:
        if (_number(row.get("latest_result_age_days")) or 9999.0) > 220:
            flags.append("stale_results")
            score -= 6.0
        for column, flag in (
            ("sales_growth_pct", "weak_sales_growth"),
            ("pat_growth_pct", "weak_pat_growth"),
            ("eps_growth_pct", "weak_eps_growth"),
        ):
            if (_number(row.get(column)) or 0.0) >= 10.0:
                score += 3.0
            else:
                flags.append(flag)
                score -= 3.0
        if (_number(row.get("debt_to_equity")) or 0.0) > 1.5:
            flags.append("high_debt")
            score -= 5.0
    if active_failed:
        flags.append("failed_breakout")
        score = min(score, 20.0)
    return max(0.0, min(100.0, score)), flags
```

- [ ] **Step 4: Wire the feature module into PostgreSQL replay preparation**

Modify `portfolio/data_sources/postgres.py`:

```python
from portfolio.features.breakout_retest import BR_COLUMNS, add_breakout_retest_features
```

In `prepare_replay_frame()`, after `raw["trailing_stop"] = 0`, add:

```python
    raw = add_breakout_retest_features(raw)
```

In `_FEATURE_COLUMNS`, append:

```python
    "br_pivot_20d",
    "br_breakout_signal",
    "br_breakout_date",
    "br_days_since_breakout",
    "br_retest_low_pct",
    "br_retest_hold",
    "br_retest_date",
    "br_retest_high",
    "br_retest_low",
    "br_confirm_after_retest",
    "br_failed",
    "br_volume_quality",
    "br_setup_score",
    "br_risk_flags",
    "br_pivot_distance_pct",
    "br_breakout_volume_ratio",
    "br_retest_volume_ratio",
    "br_breakout_close_pct",
    "br_retest_depth_pct",
```

- [ ] **Step 5: Add replay-frame integration assertions**

In `tests/portfolio/test_postgres_strategy_lab.py`, extend `test_prepare_replay_frame_uses_stage_snapshots_and_computes_strategy_columns()`:

```python
    for column in (
        "br_pivot_20d",
        "br_breakout_signal",
        "br_retest_hold",
        "br_confirm_after_retest",
        "br_setup_score",
        "br_risk_flags",
    ):
        assert column in features.columns
```

- [ ] **Step 6: Run focused feature tests**

Run:

```bash
.venv/bin/python -m pytest tests/portfolio/test_breakout_retest_features.py tests/portfolio/test_postgres_strategy_lab.py::test_prepare_replay_frame_uses_stage_snapshots_and_computes_strategy_columns -q
```

Expected:

```text
6 passed
```

- [ ] **Step 7: Commit derived features**

Run:

```bash
git add portfolio/features/__init__.py portfolio/features/breakout_retest.py portfolio/data_sources/postgres.py tests/portfolio/test_breakout_retest_features.py tests/portfolio/test_postgres_strategy_lab.py
git commit -m "feat: derive breakout retest replay features"
```

Expected:

```text
[main <hash>] feat: derive breakout retest replay features
```

## Task 2: Strategy Schema And Six Built-In Variants

**Files:**
- Modify: `portfolio/engine/strategy_schema.py`
- Modify: `portfolio/engine/strategy_library.py`
- Test: `tests/portfolio/test_strategy_schema.py`
- Test: `tests/portfolio/test_benchmark_strategy_library.py`

- [ ] **Step 1: Write failing schema tests for `br_*` indicators and structure stops**

Append to `tests/portfolio/test_strategy_schema.py`:

```python
def test_breakout_retest_indicators_validate_in_strategy_rules():
    raw = _valid_strategy()
    raw["entry"]["all"] = [
        {"indicator": "br_retest_hold", "operator": "eq", "value": 1},
        {"indicator": "br_days_since_breakout", "operator": "between", "value": [1, 10]},
        {"indicator": "br_setup_score", "operator": "gte", "value": 60},
        {"indicator": "br_failed", "operator": "eq", "value": 0},
    ]

    spec = validate_strategy_spec(raw)

    assert [rule.indicator for rule in spec.entry_all] == [
        "br_retest_hold",
        "br_days_since_breakout",
        "br_setup_score",
        "br_failed",
    ]


def test_structure_breakout_retest_stop_validates():
    raw = _valid_strategy()
    raw["risk"]["initial_stop"] = {
        "type": "breakout_retest_structure",
        "atr_indicator": "atr_14",
        "pivot_indicator": "br_pivot_20d",
        "retest_low_indicator": "br_retest_low",
        "pivot_buffer_pct": 2.0,
        "retest_atr_buffer": 0.5,
        "atr_fallback_multiple": 2.0,
    }

    spec = validate_strategy_spec(raw)

    assert spec.risk.initial_stop.type == "breakout_retest_structure"
    assert spec.risk.initial_stop.indicator == "atr_14"
    assert spec.risk.initial_stop.percent == 2.0
```

- [ ] **Step 2: Run schema tests and verify the new cases fail**

Run:

```bash
.venv/bin/python -m pytest tests/portfolio/test_strategy_schema.py::test_breakout_retest_indicators_validate_in_strategy_rules tests/portfolio/test_strategy_schema.py::test_structure_breakout_retest_stop_validates -q
```

Expected:

```text
FAILED tests/portfolio/test_strategy_schema.py::test_breakout_retest_indicators_validate_in_strategy_rules
FAILED tests/portfolio/test_strategy_schema.py::test_structure_breakout_retest_stop_validates
```

- [ ] **Step 3: Extend the strategy schema**

Modify `portfolio/engine/strategy_schema.py`:

```python
ALLOWED_INDICATORS = {
    ...
    "br_pivot_20d",
    "br_breakout_signal",
    "br_days_since_breakout",
    "br_retest_low_pct",
    "br_retest_hold",
    "br_retest_high",
    "br_retest_low",
    "br_confirm_after_retest",
    "br_failed",
    "br_volume_quality",
    "br_setup_score",
    "br_pivot_distance_pct",
    "br_breakout_volume_ratio",
    "br_retest_volume_ratio",
    "br_breakout_close_pct",
    "br_retest_depth_pct",
}
ALLOWED_STOP_TYPES = {"atr", "breakout_retest_structure"}
ALLOWED_STRUCTURE_STOP_KEYS = {
    "type",
    "atr_indicator",
    "pivot_indicator",
    "retest_low_indicator",
    "pivot_buffer_pct",
    "retest_atr_buffer",
    "atr_fallback_multiple",
}
```

Update `_parse_initial_stop()`:

```python
    if stop_type == "breakout_retest_structure":
        unknown = set(raw) - ALLOWED_STRUCTURE_STOP_KEYS
        if unknown:
            raise StrategyValidationError(f"risk.initial_stop includes unsupported field: {sorted(unknown)[0]}")
        atr_indicator = str(raw.get("atr_indicator") or "atr_14").strip()
        if atr_indicator not in ALLOWED_ATR_STOP_INDICATORS:
            raise StrategyValidationError(f"unsupported ATR indicator: {atr_indicator}")
        pivot_indicator = str(raw.get("pivot_indicator") or "br_pivot_20d").strip()
        retest_low_indicator = str(raw.get("retest_low_indicator") or "br_retest_low").strip()
        if pivot_indicator != "br_pivot_20d":
            raise StrategyValidationError("structure stop pivot_indicator must be br_pivot_20d")
        if retest_low_indicator != "br_retest_low":
            raise StrategyValidationError("structure stop retest_low_indicator must be br_retest_low")
        return InitialStopSpec(
            type=stop_type,
            multiple=_positive_float(raw.get("atr_fallback_multiple", 2.0), "risk.initial_stop.atr_fallback_multiple"),
            percent=_positive_float(raw.get("pivot_buffer_pct", 2.0), "risk.initial_stop.pivot_buffer_pct"),
            indicator=atr_indicator,
        )
```

- [ ] **Step 4: Add tests for the six built-in strategy IDs**

Append to `tests/portfolio/test_benchmark_strategy_library.py`:

```python
def test_breakout_retest_builtin_strategy_family_exists_and_validates():
    specs = {spec["strategy_id"]: spec for spec in built_in_strategy_specs()}
    expected = {
        "breakout_retest_tight_close_v1",
        "breakout_retest_tight_confirm_v1",
        "breakout_retest_balanced_close_v1",
        "breakout_retest_balanced_confirm_v1",
        "breakout_retest_wide_close_v1",
        "breakout_retest_wide_confirm_v1",
    }

    assert expected.issubset(specs)
    for strategy_id in expected:
        validated = validate_strategy_spec(specs[strategy_id])
        assert validated.risk.initial_stop.type == "breakout_retest_structure"


def test_breakout_retest_close_and_confirm_variants_have_distinct_entry_triggers():
    specs = {spec["strategy_id"]: spec for spec in built_in_strategy_specs()}
    close_rules = specs["breakout_retest_balanced_close_v1"]["entry"]["all"]
    confirm_rules = specs["breakout_retest_balanced_confirm_v1"]["entry"]["all"]

    assert {"indicator": "br_retest_hold", "operator": "eq", "value": 1} in close_rules
    assert {"indicator": "br_confirm_after_retest", "operator": "eq", "value": 1} in confirm_rules
```

- [ ] **Step 5: Add the six strategy templates**

In `portfolio/engine/strategy_library.py`, add helpers before `_BUILT_IN_STRATEGY_SPECS`:

```python
def _breakout_retest_risk() -> dict[str, Any]:
    return {
        "initial_stop": {
            "type": "breakout_retest_structure",
            "atr_indicator": "atr_14",
            "pivot_indicator": "br_pivot_20d",
            "retest_low_indicator": "br_retest_low",
            "pivot_buffer_pct": 2.0,
            "retest_atr_buffer": 0.5,
            "atr_fallback_multiple": 2.0,
        },
        "risk_per_trade_pct": 0.75,
        "max_position_pct": 8.0,
    }


def _breakout_retest_strategy(strategy_id: str, name: str, *, max_days: int, confirm: bool) -> dict[str, Any]:
    trigger = "br_confirm_after_retest" if confirm else "br_retest_hold"
    return {
        "strategy_id": strategy_id,
        "name": name,
        "universe": {"stage": "STAGE_2", "min_price": 50, "pattern": "breakout_retest"},
        "entry": {
            "all": [
                _rule(trigger, "eq", 1),
                _rule("br_days_since_breakout", "between", [1, max_days]),
                _rule("br_failed", "eq", 0),
                _rule("br_setup_score", "gte", 55),
                _rule("stage", "eq", "STAGE_2"),
                _rule("close", "above", "sma_50"),
                _rule("sma_50", "above", "sma_200"),
                _rule("relative_strength", "gte", 65),
            ]
        },
        "breakouts": {
            "timeframe": "daily",
            "all": [
                _rule("br_breakout_signal", "gte", 0),
                _rule("br_days_since_breakout", "between", [1, max_days]),
            ],
        },
        "pullbacks": {"timeframe": "daily", "all": [_rule("br_retest_depth_pct", "gte", -2.0)]},
        "volume": {"timeframe": "daily", "all": [_rule("br_volume_quality", "gte", 50)]},
        "fundamentals": {
            "any": [
                _rule("sales_growth_pct", "gte", 10),
                _rule("pat_growth_pct", "gte", 10),
                _rule("eps_growth_pct", "gte", 10),
                _rule("roe_pct", "gte", 1),
                _rule("roce_pct", "gte", 1),
            ]
        },
        "risk": _breakout_retest_risk(),
        "add_rules": [],
        "exit": {
            "any": [
                _rule("br_failed", "eq", 1),
                _rule("stage", "in", ["STAGE_3", "STAGE_4"]),
                _rule("close", "below", "sma_20"),
                _rule("close", "below", "sma_50"),
                _rule("relative_strength", "below", 60),
            ]
        },
    }
```

Append the six specs to `_BUILT_IN_STRATEGY_SPECS`:

```python
    _breakout_retest_strategy("breakout_retest_tight_close_v1", "Breakout Retest Tight Close", max_days=5, confirm=False),
    _breakout_retest_strategy("breakout_retest_tight_confirm_v1", "Breakout Retest Tight Confirm", max_days=5, confirm=True),
    _breakout_retest_strategy("breakout_retest_balanced_close_v1", "Breakout Retest Balanced Close", max_days=10, confirm=False),
    _breakout_retest_strategy("breakout_retest_balanced_confirm_v1", "Breakout Retest Balanced Confirm", max_days=10, confirm=True),
    _breakout_retest_strategy("breakout_retest_wide_close_v1", "Breakout Retest Wide Close", max_days=20, confirm=False),
    _breakout_retest_strategy("breakout_retest_wide_confirm_v1", "Breakout Retest Wide Confirm", max_days=20, confirm=True),
```

- [ ] **Step 6: Run schema and strategy-library tests**

Run:

```bash
.venv/bin/python -m pytest tests/portfolio/test_strategy_schema.py tests/portfolio/test_benchmark_strategy_library.py -q
```

Expected:

```text
passed
```

- [ ] **Step 7: Commit schema and variants**

Run:

```bash
git add portfolio/engine/strategy_schema.py portfolio/engine/strategy_library.py tests/portfolio/test_strategy_schema.py tests/portfolio/test_benchmark_strategy_library.py
git commit -m "feat: add breakout retest strategy variants"
```

Expected:

```text
[main <hash>] feat: add breakout retest strategy variants
```

## Task 3: Structure-Aware Stops And Paper-Trading Risk Outputs

**Files:**
- Modify: `portfolio/engine/strategy_compiler.py`
- Modify: `portfolio/engine/event_loop.py`
- Modify: `portfolio/engine/paper_portfolio.py`
- Test: `tests/portfolio/test_strategy_schema.py`
- Test: `tests/portfolio/test_event_loop.py`
- Test: `tests/portfolio/test_paper_portfolio.py`

- [ ] **Step 1: Write failing stop calculation tests**

Append to `tests/portfolio/test_strategy_schema.py`:

```python
def test_structure_stop_uses_tightest_valid_stop_candidate():
    raw = _valid_strategy()
    raw["risk"]["initial_stop"] = {
        "type": "breakout_retest_structure",
        "atr_indicator": "atr_14",
        "pivot_indicator": "br_pivot_20d",
        "retest_low_indicator": "br_retest_low",
        "pivot_buffer_pct": 2.0,
        "retest_atr_buffer": 0.5,
        "atr_fallback_multiple": 2.0,
    }
    compiled = compile_strategy(validate_strategy_spec(raw))
    row = pd.Series({"close": 120.0, "atr_14": 4.0, "br_pivot_20d": 112.0, "br_retest_low": 110.0})

    assert compiled.initial_stop(entry_price=120.0, row=row) == 108.0


def test_structure_stop_falls_back_to_atr_when_pattern_data_missing():
    raw = _valid_strategy()
    raw["risk"]["initial_stop"] = {
        "type": "breakout_retest_structure",
        "atr_indicator": "atr_14",
        "pivot_indicator": "br_pivot_20d",
        "retest_low_indicator": "br_retest_low",
        "pivot_buffer_pct": 2.0,
        "retest_atr_buffer": 0.5,
        "atr_fallback_multiple": 2.0,
    }
    compiled = compile_strategy(validate_strategy_spec(raw))
    row = pd.Series({"close": 120.0, "atr_14": 4.0})

    assert compiled.initial_stop(entry_price=120.0, row=row) == 112.0
```

- [ ] **Step 2: Implement structure-aware stop in the compiler**

Modify `portfolio/engine/strategy_compiler.py`:

```python
    def initial_stop(self, entry_price: float, row: pd.Series) -> float | None:
        stop = self.spec.risk.initial_stop
        if stop.type == "breakout_retest_structure":
            return _breakout_retest_structure_stop(entry_price, row, stop)
        if stop.type != "atr":
            return None
        multiple = _positive_float(stop.multiple)
        atr = _positive_float(row.get(stop.indicator))
        if multiple is None or atr is None:
            return None
        return max(0.0, float(entry_price) - multiple * atr)
```

Add helper functions:

```python
def _breakout_retest_structure_stop(entry_price: float, row: pd.Series, stop: InitialStopSpec) -> float | None:
    entry = _positive_float(entry_price)
    atr = _positive_float(row.get(stop.indicator))
    if entry is None or atr is None:
        return None
    candidates: list[float] = []
    pivot = _positive_float(row.get("br_pivot_20d"))
    retest_low = _positive_float(row.get("br_retest_low"))
    if pivot is not None:
        buffer_pct = stop.percent or 2.0
        candidates.append(pivot * (1.0 - buffer_pct / 100.0))
    if retest_low is not None:
        candidates.append(retest_low - 0.5 * atr)
    candidates.append(entry - (stop.multiple or 2.0) * atr)
    valid = [price for price in candidates if price > 0 and price < entry]
    return max(valid) if valid else None
```

- [ ] **Step 3: Align event-loop risk sizing with compiler stop price**

Modify `portfolio/engine/event_loop.py`:

```python
def _initial_stop_distance(strategy: CompiledStrategy, row: pd.Series) -> float | None:
    close = _positive_float(row.get("close"))
    if close is None:
        return None
    stop_price = strategy.initial_stop(close, row)
    if stop_price is None:
        return None
    distance = close - stop_price
    return distance if distance > 0 else None
```

Keep `_entry_context()` unchanged except that it now receives structure-aware distance through `_initial_stop_distance()`.

- [ ] **Step 4: Expand paper feature marks and risk rows**

Modify `_latest_feature_marks()` and `_feature_marks_by_date()` in `portfolio/engine/paper_portfolio.py` to add:

```python
            "br_pivot_20d": _number(row.get("br_pivot_20d")),
            "br_retest_low": _number(row.get("br_retest_low")),
            "br_retest_high": _number(row.get("br_retest_high")),
            "br_breakout_date": row.get("br_breakout_date"),
            "br_retest_date": row.get("br_retest_date"),
            "br_days_since_breakout": _number(row.get("br_days_since_breakout")),
            "br_setup_score": _number(row.get("br_setup_score")),
            "br_risk_flags": row.get("br_risk_flags"),
```

Add helper near `_strategy_spec()`:

```python
def _structure_stop(reference_price: float | None, mark: dict[str, Any], spec: dict[str, Any]) -> float | None:
    if reference_price is None:
        return None
    initial_stop = (spec.get("risk") or {}).get("initial_stop") or {}
    atr = _number(mark.get("atr_14"))
    if initial_stop.get("type") != "breakout_retest_structure":
        multiple = _number(initial_stop.get("multiple")) or 2.0
        return max(0.0, reference_price - multiple * atr) if atr and atr > 0 else None
    if not atr or atr <= 0:
        return None
    candidates = []
    pivot = _number(mark.get("br_pivot_20d"))
    retest_low = _number(mark.get("br_retest_low"))
    if pivot and pivot > 0:
        candidates.append(pivot * 0.98)
    if retest_low and retest_low > 0:
        candidates.append(retest_low - 0.5 * atr)
    candidates.append(reference_price - 2.0 * atr)
    valid = [price for price in candidates if 0 < price < reference_price]
    return max(valid) if valid else None
```

Replace ATR-only stop calculations in `_position_rows()`, `_next_order_rows()`, and `_trade_rows()` with `_structure_stop(...)`.

- [ ] **Step 5: Add paper output assertions**

In `tests/portfolio/test_paper_portfolio.py`, add:

```python
def test_breakout_retest_marks_surface_in_paper_rows():
    features = pd.DataFrame(
        [
            {
                "date": "2026-06-12",
                "symbol": "ABC",
                "close": 120.0,
                "atr_14": 4.0,
                "stage": "STAGE_2",
                "rsi_14": 61.0,
                "relative_strength": 78.0,
                "br_pivot_20d": 112.0,
                "br_retest_low": 110.0,
                "br_retest_high": 116.0,
                "br_breakout_date": "2026-06-09",
                "br_retest_date": "2026-06-11",
                "br_days_since_breakout": 3,
                "br_setup_score": 74.0,
                "br_risk_flags": "weak_volume",
            }
        ]
    )

    marks = _latest_feature_marks(features)

    assert marks["ABC"]["br_pivot_20d"] == 112.0
    assert marks["ABC"]["br_retest_date"] == "2026-06-11"
    assert marks["ABC"]["br_risk_flags"] == "weak_volume"
```

- [ ] **Step 6: Run stop and paper tests**

Run:

```bash
.venv/bin/python -m pytest tests/portfolio/test_strategy_schema.py tests/portfolio/test_event_loop.py tests/portfolio/test_paper_portfolio.py -q
```

Expected:

```text
passed
```

- [ ] **Step 7: Commit stop and risk plumbing**

Run:

```bash
git add portfolio/engine/strategy_compiler.py portfolio/engine/event_loop.py portfolio/engine/paper_portfolio.py tests/portfolio/test_strategy_schema.py tests/portfolio/test_event_loop.py tests/portfolio/test_paper_portfolio.py
git commit -m "feat: add breakout retest structure stops"
```

Expected:

```text
[main <hash>] feat: add breakout retest structure stops
```

## Task 4: Strategy-Lab And Report Surfaces

**Files:**
- Modify: `portfolio/cli.py`
- Modify: `terminal/reports.py`
- Modify: `terminal/swing_playbook.py`
- Test: `tests/portfolio/test_postgres_strategy_lab.py`
- Test: `tests/test_swing_playbook.py`

- [ ] **Step 1: Write failing report-column tests**

Add to `tests/portfolio/test_postgres_strategy_lab.py`:

```python
def test_strategy_lab_breakout_retest_columns_are_available_for_reports():
    eod = _eod_rows(symbol="ABC", closes=[100.0] * 220 + [106.0, 102.0, 104.0])
    stage = _stage_rows(symbol="ABC", rows=len(eod), stage="STAGE_2")
    features = prepare_replay_frame(eod, stage, start_date="2026-01-01")

    latest = features[features["symbol"] == "ABC"].tail(1).iloc[0]

    assert latest["br_breakout_date"]
    assert latest["br_retest_date"]
    assert latest["br_confirm_after_retest"] == 1
    assert latest["br_setup_score"] >= 0
```

- [ ] **Step 2: Add candidate evidence rows to report builders**

In report code that serializes strategy-lab candidate rows, add this column list:

```python
BREAKOUT_RETEST_REPORT_COLUMNS = [
    "symbol",
    "date",
    "strategy_id",
    "br_pivot_20d",
    "br_breakout_date",
    "br_retest_date",
    "br_retest_low",
    "br_retest_high",
    "br_days_since_breakout",
    "br_retest_depth_pct",
    "br_breakout_volume_ratio",
    "br_retest_volume_ratio",
    "br_setup_score",
    "br_risk_flags",
]
```

Use the list in CSV/HTML/Markdown candidate sections when `strategy_id.startswith("breakout_retest_")`.

- [ ] **Step 3: Add swing playbook explanatory section**

In `terminal/swing_playbook.py`, add a section titled `Breakout Retest Watchlist` that renders:

```text
Symbol | Variant | Pivot | Breakout | Retest | Entry Mode | Stop | Target | Score | Risk Flags
```

For empty candidates, render:

```text
No active breakout-retest candidates met the EOD filters in this run.
```

- [ ] **Step 4: Run focused report tests**

Run:

```bash
.venv/bin/python -m pytest tests/portfolio/test_postgres_strategy_lab.py::test_strategy_lab_breakout_retest_columns_are_available_for_reports tests/test_swing_playbook.py -q
```

Expected:

```text
passed
```

- [ ] **Step 5: Run a small strategy-lab smoke**

Run:

```bash
.venv/bin/python -m portfolio.cli strategy-lab --data-source postgres --top-n 50 --start-date 2026-01-01 --end-date 2026-06-12 --output-dir portfolio/data/nse_pg_strategy_lab/breakout_retest_smoke
```

Expected:

```text
Strategy lab complete
```

Verify:

```bash
rg -n "breakout_retest_(tight|balanced|wide)_(close|confirm)_v1" portfolio/data/nse_pg_strategy_lab/breakout_retest_smoke
```

Expected: at least six matches.

- [ ] **Step 6: Commit reports**

Run:

```bash
git add portfolio/cli.py terminal/reports.py terminal/swing_playbook.py tests/portfolio/test_postgres_strategy_lab.py tests/test_swing_playbook.py
git commit -m "feat: report breakout retest strategy evidence"
```

Expected:

```text
[main <hash>] feat: report breakout retest strategy evidence
```

## Task 5: Agent Adda Query Capability

**Files:**
- Create: `terminal/breakout_retest.py`
- Modify: active Agent Adda router and renderer files found by `rg -n "situation|intent|screen|quality-breakouts|prompt library" terminal nse_agent.py`
- Test: `tests/test_command_dispatch.py`
- Test: `tests/test_situation_assessment_scenarios.py`

- [ ] **Step 1: Write failing Agent Adda routing tests**

Append to `tests/test_situation_assessment_scenarios.py`:

```python
def test_breakout_retest_prompt_routes_to_breakout_retest_capability():
    assessment = assess_situation("find balanced breakout retest setups with fundamentals")

    assert assessment.intent in {"breakout_retest_screen", "screen"}
    assert "breakout_retest" in " ".join(assessment.capabilities)
```

Append to `tests/test_command_dispatch.py`:

```python
def test_breakout_retest_screen_response_contains_required_evidence(monkeypatch):
    response = dispatch_command("find breakout retest stocks")

    text = str(response)
    assert "BREAKOUT RETEST" in text.upper()
    assert "Pivot" in text
    assert "Breakout" in text
    assert "Retest" in text
    assert "Risk Flags" in text
```

- [ ] **Step 2: Add the query helper**

Create `terminal/breakout_retest.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pandas as pd


@dataclass(frozen=True)
class BreakoutRetestQuery:
    window: str = "balanced"
    entry_mode: str = "both"
    require_fundamentals: bool = False
    limit: int = 15


WINDOW_DAYS = {"tight": 5, "balanced": 10, "wide": 20}


def parse_breakout_retest_query(text: str) -> BreakoutRetestQuery:
    lowered = text.lower()
    window = "tight" if "tight" in lowered else "wide" if "wide" in lowered else "balanced"
    if "confirm" in lowered or "confirmation" in lowered:
        entry_mode = "confirm"
    elif "close" in lowered:
        entry_mode = "close"
    else:
        entry_mode = "both"
    return BreakoutRetestQuery(
        window=window,
        entry_mode=entry_mode,
        require_fundamentals="fundamental" in lowered or "quality" in lowered,
    )


def filter_breakout_retest_candidates(features: pd.DataFrame, query: BreakoutRetestQuery) -> pd.DataFrame:
    if features.empty:
        return features
    max_days = WINDOW_DAYS[query.window]
    frame = features.copy()
    frame = frame[pd.to_numeric(frame["br_days_since_breakout"], errors="coerce").between(1, max_days)]
    frame = frame[pd.to_numeric(frame["br_failed"], errors="coerce").fillna(1).eq(0)]
    if query.entry_mode == "confirm":
        frame = frame[pd.to_numeric(frame["br_confirm_after_retest"], errors="coerce").fillna(0).eq(1)]
    elif query.entry_mode == "close":
        frame = frame[pd.to_numeric(frame["br_retest_hold"], errors="coerce").fillna(0).eq(1)]
    else:
        close_mask = pd.to_numeric(frame["br_retest_hold"], errors="coerce").fillna(0).eq(1)
        confirm_mask = pd.to_numeric(frame["br_confirm_after_retest"], errors="coerce").fillna(0).eq(1)
        frame = frame[close_mask | confirm_mask]
    if query.require_fundamentals:
        frame = frame[~frame["br_risk_flags"].fillna("").str.contains("missing_fundamentals", regex=False)]
    return frame.sort_values(["br_setup_score", "relative_strength"], ascending=[False, False]).head(query.limit)


def render_breakout_retest_answer(candidates: pd.DataFrame, *, query: BreakoutRetestQuery, source: str) -> str:
    lines = [
        "━━━ BREAKOUT RETEST SETUPS ━━━",
        f"Window: {query.window} · Entry: {query.entry_mode} · Source: {source}",
        "",
    ]
    if candidates.empty:
        lines.append("No active breakout-retest candidates met the EOD filters.")
        return "\n".join(lines)
    for _, row in candidates.iterrows():
        lines.extend(
            [
                f"▶ {row.get('symbol')} · Score {float(row.get('br_setup_score') or 0):.1f}",
                f"  Pivot: {_fmt(row.get('br_pivot_20d'))} · Breakout: {row.get('br_breakout_date') or 'n/a'} · Retest: {row.get('br_retest_date') or 'n/a'}",
                f"  Entry evidence: retest_hold={int(row.get('br_retest_hold') or 0)} confirm={int(row.get('br_confirm_after_retest') or 0)} · Days since breakout: {int(row.get('br_days_since_breakout') or 0)}",
                f"  Technical: Stage {row.get('stage')} · RS {_fmt(row.get('relative_strength'))} · RSI {_fmt(row.get('rsi_14'))}",
                f"  Risk Flags: {row.get('br_risk_flags') or 'none'}",
                "",
            ]
        )
    lines.append("Research only - not investment advice.")
    return "\n".join(lines)


def _fmt(value: object) -> str:
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "n/a"
```

- [ ] **Step 3: Register the capability in the active router**

Find active dispatch hooks:

```bash
rg -n "quality-breakouts|screen|situation|intent|capabilities|dispatch_command" terminal nse_agent.py tests
```

In the selected router, add detection for phrases:

```python
BREAKOUT_RETEST_PATTERNS = (
    "breakout retest",
    "broke out and retesting",
    "retest setup",
    "confirm-entry retest",
    "balanced breakout retest",
    "tight retest",
    "wide retest",
)


def is_breakout_retest_query(text: str) -> bool:
    lowered = text.lower()
    return any(pattern in lowered for pattern in BREAKOUT_RETEST_PATTERNS)
```

Route matches to:

```python
query = parse_breakout_retest_query(user_text)
features = load_latest_strategy_features()
candidates = filter_breakout_retest_candidates(features, query)
return render_breakout_retest_answer(candidates, query=query, source="PostgreSQL replay features")
```

- [ ] **Step 4: Run Agent Adda prompt tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_situation_assessment_scenarios.py tests/test_command_dispatch.py -q
```

Expected:

```text
passed
```

- [ ] **Step 5: Smoke test terminal prompts**

Run:

```bash
printf 'find breakout retest stocks\nshow balanced breakout retest setups\nshow confirm-entry retest setups\nexit\n' | .venv/bin/python nse_agent.py --auto
```

Expected output contains:

```text
BREAKOUT RETEST SETUPS
Pivot:
Breakout:
Retest:
Risk Flags:
```

- [ ] **Step 6: Commit Agent Adda query support**

Run:

```bash
git add terminal/breakout_retest.py nse_agent.py terminal tests/test_command_dispatch.py tests/test_situation_assessment_scenarios.py
git commit -m "feat: add agent adda breakout retest queries"
```

Expected:

```text
[main <hash>] feat: add agent adda breakout retest queries
```

## Task 6: End-To-End PostgreSQL Validation

**Files:**
- Create: `reports/validation/breakout_retest_20260615.md`
- Generated: `portfolio/data/nse_pg_strategy_lab/breakout_retest_latest/`
- Generated: latest report files under existing report output folders

- [ ] **Step 1: Run the focused regression suite**

Run:

```bash
.venv/bin/python -m pytest tests/portfolio tests/test_situation_assessment_scenarios.py tests/test_command_dispatch.py tests/test_swing_playbook.py -q
```

Expected:

```text
passed
```

- [ ] **Step 2: Start or verify PostgreSQL availability**

Run:

```bash
/Users/pgorai/Documents/Projects/Unified-NSE-Analysis/postgres/start_pg.sh start
.venv/bin/python - <<'PY'
from portfolio.data_sources.postgres import default_dsn
import psycopg2
with psycopg2.connect(default_dsn()) as conn:
    with conn.cursor() as cur:
        cur.execute("select max(trade_date) from market.equity_eod where series='EQ'")
        print(cur.fetchone()[0])
PY
```

Expected: a current EOD date is printed.

- [ ] **Step 3: Run latest strategy-lab comparison**

Run:

```bash
.venv/bin/python -m portfolio.cli strategy-lab --data-source postgres --top-n 500 --start-date 2025-01-01 --output-dir portfolio/data/nse_pg_strategy_lab/breakout_retest_latest
```

Expected:

```text
Strategy lab complete
```

- [ ] **Step 4: Collect variant metrics**

Run:

```bash
.venv/bin/python - <<'PY'
import json
from pathlib import Path

root = Path("portfolio/data/nse_pg_strategy_lab/breakout_retest_latest")
for path in sorted(root.glob("**/*.json")):
    if "breakout_retest_" not in path.name:
        continue
    data = json.loads(path.read_text())
    print(path.name, data.get("total_return_pct"), data.get("max_drawdown_pct"), data.get("win_rate_pct"), data.get("trade_count"))
PY
```

Expected: one line for each of the six variants.

- [ ] **Step 5: Test interactive-style Agent Adda follow-ups**

Run:

```bash
printf 'find breakout retest stocks\nshow only confirm entry\ncompare tight balanced wide breakout retest variants\nexit\n' | .venv/bin/python nse_agent.py --auto
```

Expected: Agent Adda keeps the breakout-retest topic across follow-ups and returns pivot/retest evidence in each answer.

- [ ] **Step 6: Generate validation report from run artifacts**

Run:

```bash
mkdir -p reports/validation
.venv/bin/python - <<'PY'
import json
from pathlib import Path

root = Path("portfolio/data/nse_pg_strategy_lab/breakout_retest_latest")
out = Path("reports/validation/breakout_retest_20260615.md")
strategy_notes = {
    "breakout_retest_tight_close_v1": "close-entry tight window",
    "breakout_retest_tight_confirm_v1": "confirmation tight window",
    "breakout_retest_balanced_close_v1": "close-entry default window",
    "breakout_retest_balanced_confirm_v1": "confirmation default window",
    "breakout_retest_wide_close_v1": "close-entry wide window",
    "breakout_retest_wide_confirm_v1": "confirmation wide window",
}

rows = []
for strategy_id, note in strategy_notes.items():
    matches = sorted(root.glob(f"**/{strategy_id}.json"))
    data = json.loads(matches[-1].read_text()) if matches else {}
    rows.append(
        {
            "strategy": strategy_id,
            "return_pct": data.get("total_return_pct"),
            "max_drawdown_pct": data.get("max_drawdown_pct"),
            "win_rate_pct": data.get("win_rate_pct"),
            "trade_count": data.get("trade_count"),
            "note": note,
        }
    )

def fmt(value):
    if value is None:
        return "n/a"
    if isinstance(value, (int, float)):
        return f"{value:.2f}"
    return str(value)

best = max(rows, key=lambda row: float(row["return_pct"] or -999999))
lines = [
    "# Breakout Retest Validation - 2026-06-15",
    "",
    "## Data",
    "",
    "- Source: PostgreSQL EOD replay.",
    "- Universe: top 500 liquid EQ symbols.",
    "- Start date: 2025-01-01.",
    "",
    "## Regression",
    "",
    "- `tests/portfolio`: passed.",
    "- Agent Adda prompt routing tests: passed.",
    "- Swing playbook tests: passed.",
    "",
    "## Variant Comparison",
    "",
    "| Strategy | Return % | Max DD % | Win % | Trades | Notes |",
    "|---|---:|---:|---:|---:|---|",
]
for row in rows:
    lines.append(
        "| {strategy} | {return_pct} | {max_drawdown_pct} | {win_rate_pct} | {trade_count} | {note} |".format(
            strategy=row["strategy"],
            return_pct=fmt(row["return_pct"]),
            max_drawdown_pct=fmt(row["max_drawdown_pct"]),
            win_rate_pct=fmt(row["win_rate_pct"]),
            trade_count=fmt(row["trade_count"]),
            note=row["note"],
        )
    )
lines.extend(
    [
        "",
        "## Observations",
        "",
        f"- Best return variant in this run: `{best['strategy']}` at {fmt(best['return_pct'])}%.",
        "- False-positive patterns, missing-fundamental coverage, and paper-trading promotion guidance should be assessed from the generated trade and candidate CSV artifacts in the same output directory.",
        "",
        "## Research Framing",
        "",
        "This is research-only infrastructure and not investment advice.",
    ]
)
out.write_text("\n".join(lines) + "\n")
print(out)
PY
```

Expected: `reports/validation/breakout_retest_20260615.md` is printed and contains one row for each of the six variants.

- [ ] **Step 7: Commit validation report**

Run:

```bash
git add reports/validation/breakout_retest_20260615.md portfolio/data/nse_pg_strategy_lab/breakout_retest_latest
git commit -m "test: validate breakout retest strategies on postgres data"
```

Expected:

```text
[main <hash>] test: validate breakout retest strategies on postgres data
```

## Final Acceptance Checklist

- [ ] `br_*` fields exist in replay features and are computed without lookahead.
- [ ] Six built-in variants compile and appear in strategy-lab output.
- [ ] Close-entry and confirmation-entry variants produce distinct signals.
- [ ] Structure-aware stops use pivot, retest low, and ATR with ATR fallback.
- [ ] Paper-trading risk rails still reject oversized, illiquid, gapped, or discontinuous entries.
- [ ] Reports include pivot, breakout date, retest date, entry mode, stop, target, score, and risk flags.
- [ ] Agent Adda answers breakout-retest NLP prompts with grounded evidence and source freshness.
- [ ] Latest PostgreSQL validation compares all six variants and records promotion guidance.
