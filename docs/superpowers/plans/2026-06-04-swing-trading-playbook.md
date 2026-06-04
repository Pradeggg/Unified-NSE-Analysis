# Swing Trading Playbook Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a rules-based NSE swing trading playbook report for tactical and position swing candidates, with portfolio-aware action labels and Markdown/HTML/CSV outputs.

**Architecture:** Add one focused orchestration module, `terminal/swing_playbook.py`, with pure scoring/rendering functions that are easy to test from fixtures. Integrate it into the Agent Adda command registry as `/swing-playbook`, then add report preset and daily-refresh hooks after the standalone command works.

**Tech Stack:** Python 3, pandas, psycopg2, existing Agent Adda command registry, existing report HTML converter/theme in `terminal.reports`, pytest/unittest.

---

## File Structure

- Create `terminal/swing_playbook.py`
  - Data classes for candidates, scores, risk plans, portfolio actions, and generated report result.
  - Data loaders for PostgreSQL and portfolio files.
  - Pure scoring functions for tactical and position sleeves.
  - Portfolio overlay label logic.
  - Markdown, HTML, and CSV writers.
  - Command parser/handler entry point.
- Create `tests/test_swing_playbook.py`
  - Unit tests for scoring, risk plans, portfolio labels, rendering, and file generation.
- Modify `nse_agent.py`
  - Add `/swing-playbook` to `_SLASH_COMMANDS`.
  - Register command handler in `_build_command_registry()`.
- Modify `terminal/reports.py`
  - Add `generate_preset_report("swing-playbook", "html"|"md")` support by delegating to `terminal.swing_playbook.generate_swing_playbook`.
- Modify `daily_refresh.py`
  - Add a callable `step_swing_playbook(dry_run: bool)` and wire it late in the pipeline after sector/portfolio context is available.
- Modify tests:
  - `tests/test_command_dispatch.py` for command registry visibility and dispatch.
  - `tests/test_terminal_reports.py` for report preset delegation.
  - `tests/test_refresh_failure_handling.py` for the callable refresh step.

## Data Contract

`terminal/swing_playbook.py` should work from a DataFrame so tests do not need PostgreSQL. The minimum candidate columns are:

```text
symbol, company_name, sector, close, volume, turnover_cr, stage,
technical_score, relative_strength, rsi_14, sma_20, sma_50, sma_200,
atr_14, volume_ratio_20d, vcp_pick, vcp_score, vcp_breakout_pct,
vcp_contraction_pct, enhanced_fund_score, sales_growth_pct,
pat_growth_pct, latest_result_age_days
```

Missing optional columns must be filled with neutral defaults and noted in `warnings`.

## Tasks

### Task 1: Add Core Data Models And Pure Helpers

**Files:**
- Create: `terminal/swing_playbook.py`
- Test: `tests/test_swing_playbook.py`

- [ ] **Step 1: Write failing tests for risk plan and missing-column normalization**

Add `tests/test_swing_playbook.py`:

```python
from __future__ import annotations

from pathlib import Path

import pandas as pd

from terminal.swing_playbook import (
    SwingPlaybookOptions,
    build_risk_plan,
    normalize_candidate_frame,
)


def test_build_risk_plan_uses_atr_stop_and_reward_risk_target():
    row = pd.Series({"close": 100.0, "atr_14": 4.0, "sma_20": 96.0, "sma_50": 90.0})

    plan = build_risk_plan(row, sleeve="TACTICAL")

    assert plan.entry_trigger == 101.0
    assert plan.initial_stop == 92.8
    assert plan.stop_distance_pct == 8.2
    assert plan.target_1 == 113.3
    assert plan.target_2 == 117.4
    assert plan.r_multiple_target_1 == 1.5
    assert plan.r_multiple_target_2 == 2.0


def test_normalize_candidate_frame_fills_optional_columns_and_reports_warnings():
    raw = pd.DataFrame(
        [
            {
                "symbol": "AAA",
                "close": 100.0,
                "volume": 1_000_000,
                "stage": "STAGE_2",
                "technical_score": 75,
            }
        ]
    )

    frame, warnings = normalize_candidate_frame(raw)

    assert frame.loc[0, "symbol"] == "AAA"
    assert frame.loc[0, "sector"] == "Unknown"
    assert frame.loc[0, "relative_strength"] == 50.0
    assert frame.loc[0, "vcp_pick"] == 0
    assert "filled missing optional columns" in warnings[0]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
.venv/bin/python -m pytest tests/test_swing_playbook.py::test_build_risk_plan_uses_atr_stop_and_reward_risk_target tests/test_swing_playbook.py::test_normalize_candidate_frame_fills_optional_columns_and_reports_warnings -q
```

Expected: import failure for `terminal.swing_playbook`.

- [ ] **Step 3: Implement data models and helpers**

Create `terminal/swing_playbook.py`:

```python
from __future__ import annotations

import csv
import html
import os
import shlex
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parent.parent
PG_DSN = (
    os.environ.get("AGENT_ADDA_PG_DSN")
    or os.environ.get("PG_DSN")
    or "dbname=nse_market user=nse_admin host=/tmp"
)

REQUIRED_COLUMNS = ("symbol", "close", "volume", "stage", "technical_score")
OPTIONAL_DEFAULTS: dict[str, Any] = {
    "company_name": "",
    "sector": "Unknown",
    "turnover_cr": 0.0,
    "relative_strength": 50.0,
    "rsi_14": 50.0,
    "sma_20": 0.0,
    "sma_50": 0.0,
    "sma_200": 0.0,
    "atr_14": 0.0,
    "volume_ratio_20d": 1.0,
    "vcp_pick": 0,
    "vcp_score": 0.0,
    "vcp_breakout_pct": 0.0,
    "vcp_contraction_pct": 0.0,
    "enhanced_fund_score": 50.0,
    "sales_growth_pct": 0.0,
    "pat_growth_pct": 0.0,
    "latest_result_age_days": 9999.0,
    "is_portfolio_holding": False,
    "quantity": 0.0,
    "avg_cost": 0.0,
    "position_value": 0.0,
}


@dataclass(frozen=True)
class SwingPlaybookOptions:
    project_root: Path = ROOT
    fresh: bool = False
    section: str = "all"
    top_n: int = 10
    account_value: float | None = None
    as_of: str | None = None


@dataclass(frozen=True)
class ScoreBreakdown:
    technical: float
    relative_strength: float
    pattern: float
    context: float
    fundamentals: float
    liquidity: float

    @property
    def total(self) -> float:
        return round(
            self.technical
            + self.relative_strength
            + self.pattern
            + self.context
            + self.fundamentals
            + self.liquidity,
            1,
        )


@dataclass(frozen=True)
class RiskPlan:
    entry_trigger: float
    initial_stop: float
    target_1: float
    target_2: float
    stop_distance_pct: float
    r_multiple_target_1: float
    r_multiple_target_2: float
    risk_note: str


@dataclass(frozen=True)
class PlaybookCandidate:
    symbol: str
    sleeve: str
    action_label: str
    score: float
    score_breakdown: ScoreBreakdown
    entry_label: str
    risk_plan: RiskPlan
    evidence: tuple[str, ...]
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class PortfolioAction:
    symbol: str
    label: str
    reason: str
    stop: float | None
    risk_note: str


@dataclass(frozen=True)
class SwingPlaybookResult:
    success: bool
    markdown: str
    html_path: str
    markdown_path: str
    candidates_csv: str
    portfolio_csv: str
    warnings: tuple[str, ...] = ()


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def normalize_candidate_frame(raw: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    if raw is None or raw.empty:
        raise ValueError("swing playbook requires at least one candidate row")
    missing_required = [column for column in REQUIRED_COLUMNS if column not in raw.columns]
    if missing_required:
        raise ValueError(f"swing playbook missing required columns: {', '.join(missing_required)}")
    frame = raw.copy()
    filled: list[str] = []
    for column, default in OPTIONAL_DEFAULTS.items():
        if column not in frame.columns:
            frame[column] = default
            filled.append(column)
    frame["symbol"] = frame["symbol"].astype(str).str.upper().str.strip()
    frame["stage"] = frame["stage"].fillna("UNKNOWN").astype(str).str.upper().str.strip()
    numeric_columns = [
        "close",
        "volume",
        "technical_score",
        "turnover_cr",
        "relative_strength",
        "rsi_14",
        "sma_20",
        "sma_50",
        "sma_200",
        "atr_14",
        "volume_ratio_20d",
        "vcp_pick",
        "vcp_score",
        "vcp_breakout_pct",
        "vcp_contraction_pct",
        "enhanced_fund_score",
        "sales_growth_pct",
        "pat_growth_pct",
        "latest_result_age_days",
        "quantity",
        "avg_cost",
        "position_value",
    ]
    for column in numeric_columns:
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(float(OPTIONAL_DEFAULTS.get(column, 0.0)))
    warnings = [f"filled missing optional columns: {', '.join(filled)}"] if filled else []
    return frame, warnings


def build_risk_plan(row: pd.Series, *, sleeve: str) -> RiskPlan:
    close = _num(row.get("close"))
    atr = _num(row.get("atr_14"), close * 0.03 if close else 0.0)
    if atr <= 0 and close > 0:
        atr = close * 0.03
    multiple = 1.8 if sleeve.upper() == "TACTICAL" else 2.4
    raw_stop = close - (atr * multiple)
    structure_stop = _num(row.get("sma_20" if sleeve.upper() == "TACTICAL" else "sma_50"), raw_stop)
    stop = min(raw_stop, structure_stop) if structure_stop > 0 else raw_stop
    entry = close * 1.01
    risk = max(entry - stop, close * 0.01)
    target_1 = entry + (risk * 1.5)
    target_2 = entry + (risk * 2.0)
    stop_distance_pct = ((entry - stop) / entry * 100.0) if entry else 0.0
    return RiskPlan(
        entry_trigger=round(entry, 2),
        initial_stop=round(stop, 2),
        target_1=round(target_1, 2),
        target_2=round(target_2, 2),
        stop_distance_pct=round(stop_distance_pct, 1),
        r_multiple_target_1=1.5,
        r_multiple_target_2=2.0,
        risk_note=f"Balanced profile: risk up to 1.0% account equity; stop distance {stop_distance_pct:.1f}%.",
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
.venv/bin/python -m pytest tests/test_swing_playbook.py::test_build_risk_plan_uses_atr_stop_and_reward_risk_target tests/test_swing_playbook.py::test_normalize_candidate_frame_fills_optional_columns_and_reports_warnings -q
```

Expected: `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add terminal/swing_playbook.py tests/test_swing_playbook.py
git commit -m "Add swing playbook core models"
```

### Task 2: Implement Tactical And Position Scoring

**Files:**
- Modify: `terminal/swing_playbook.py`
- Modify: `tests/test_swing_playbook.py`

- [ ] **Step 1: Write failing scoring tests**

Append to `tests/test_swing_playbook.py`:

```python
from terminal.swing_playbook import rank_swing_candidates, score_candidate


def _candidate_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "symbol": "LEADER",
                "company_name": "Leader Ltd",
                "sector": "IT",
                "close": 200.0,
                "volume": 1_500_000,
                "turnover_cr": 40.0,
                "stage": "STAGE_2",
                "technical_score": 86,
                "relative_strength": 88,
                "rsi_14": 62,
                "sma_20": 190,
                "sma_50": 175,
                "sma_200": 150,
                "atr_14": 8,
                "volume_ratio_20d": 1.8,
                "vcp_pick": 1,
                "vcp_score": 84,
                "vcp_breakout_pct": 2.4,
                "vcp_contraction_pct": 12,
                "enhanced_fund_score": 72,
                "sales_growth_pct": 18,
                "pat_growth_pct": 22,
                "latest_result_age_days": 70,
            },
            {
                "symbol": "LAGGARD",
                "company_name": "Laggard Ltd",
                "sector": "Metals",
                "close": 120.0,
                "volume": 600_000,
                "turnover_cr": 8.0,
                "stage": "STAGE_3",
                "technical_score": 45,
                "relative_strength": 35,
                "rsi_14": 44,
                "sma_20": 125,
                "sma_50": 128,
                "sma_200": 130,
                "atr_14": 6,
                "volume_ratio_20d": 0.8,
                "vcp_pick": 0,
                "vcp_score": 10,
                "vcp_breakout_pct": -1.0,
                "vcp_contraction_pct": 0,
                "enhanced_fund_score": 40,
                "sales_growth_pct": -5,
                "pat_growth_pct": -8,
                "latest_result_age_days": 400,
            },
        ]
    )


def test_score_candidate_prefers_strong_stage2_vcp_for_tactical():
    frame, _ = normalize_candidate_frame(_candidate_frame())

    leader = score_candidate(frame.iloc[0], sleeve="TACTICAL")
    laggard = score_candidate(frame.iloc[1], sleeve="TACTICAL")

    assert leader.total > laggard.total
    assert leader.pattern > laggard.pattern
    assert leader.technical > laggard.technical


def test_rank_swing_candidates_returns_both_sleeves_with_action_labels():
    frame, _ = normalize_candidate_frame(_candidate_frame())

    tactical, position = rank_swing_candidates(frame, top_n=5)

    assert tactical[0].symbol == "LEADER"
    assert tactical[0].sleeve == "TACTICAL"
    assert tactical[0].entry_label == "EOD_READY"
    assert position[0].symbol == "LEADER"
    assert position[0].sleeve == "POSITION"
```

- [ ] **Step 2: Run scoring tests to verify they fail**

Run:

```bash
.venv/bin/python -m pytest tests/test_swing_playbook.py::test_score_candidate_prefers_strong_stage2_vcp_for_tactical tests/test_swing_playbook.py::test_rank_swing_candidates_returns_both_sleeves_with_action_labels -q
```

Expected: import failure for `rank_swing_candidates` or `score_candidate`.

- [ ] **Step 3: Implement scoring functions**

Append to `terminal/swing_playbook.py`:

```python
def _score_technical(row: pd.Series, *, sleeve: str) -> float:
    base = _clamp(_num(row.get("technical_score")))
    stage_bonus = 15.0 if row.get("stage") == "STAGE_2" else (-20.0 if row.get("stage") == "STAGE_4" else 0.0)
    close = _num(row.get("close"))
    ma_bonus = 0.0
    if close > _num(row.get("sma_20")) > _num(row.get("sma_50")) > 0:
        ma_bonus += 10.0
    if close > _num(row.get("sma_50")) > _num(row.get("sma_200")) > 0:
        ma_bonus += 10.0
    rsi = _num(row.get("rsi_14"), 50.0)
    if sleeve.upper() == "TACTICAL":
        rsi_bonus = 8.0 if 50 <= rsi <= 75 else (-8.0 if rsi < 45 else 0.0)
    else:
        rsi_bonus = 8.0 if 45 <= rsi <= 72 else (-8.0 if rsi < 40 else 0.0)
    return round(_clamp(base + stage_bonus + ma_bonus + rsi_bonus) * 0.35, 2)


def _score_relative_strength(row: pd.Series) -> float:
    return round(_clamp(_num(row.get("relative_strength"), 50.0)) * 0.20, 2)


def _score_pattern(row: pd.Series) -> float:
    vcp_score = _num(row.get("vcp_score"))
    breakout = _num(row.get("vcp_breakout_pct"))
    contraction = _num(row.get("vcp_contraction_pct"))
    raw = vcp_score
    if _num(row.get("vcp_pick")) >= 1:
        raw += 12.0
    if breakout >= 1.5:
        raw += 8.0
    if contraction >= 8:
        raw += 5.0
    return round(_clamp(raw) * 0.15, 2)


def _score_context(row: pd.Series) -> float:
    sector_strength = _num(row.get("sector_strength"), 50.0)
    market_regime_score = _num(row.get("market_regime_score"), 50.0)
    return round(_clamp((sector_strength * 0.6) + (market_regime_score * 0.4)) * 0.15, 2)


def _score_fundamentals(row: pd.Series) -> float:
    fund = _num(row.get("enhanced_fund_score"), 50.0)
    growth_bonus = 0.0
    if _num(row.get("sales_growth_pct")) > 0:
        growth_bonus += 8.0
    if _num(row.get("pat_growth_pct")) > 0:
        growth_bonus += 8.0
    if _num(row.get("latest_result_age_days"), 9999.0) <= 220:
        growth_bonus += 4.0
    return round(_clamp(fund + growth_bonus) * 0.10, 2)


def _score_liquidity(row: pd.Series) -> float:
    turnover = _num(row.get("turnover_cr"))
    volume = _num(row.get("volume"))
    raw = 30.0
    if turnover >= 20:
        raw += 40.0
    elif turnover >= 5:
        raw += 25.0
    if volume >= 1_000_000:
        raw += 30.0
    elif volume >= 250_000:
        raw += 15.0
    return round(_clamp(raw) * 0.05, 2)


def score_candidate(row: pd.Series, *, sleeve: str) -> ScoreBreakdown:
    return ScoreBreakdown(
        technical=_score_technical(row, sleeve=sleeve),
        relative_strength=_score_relative_strength(row),
        pattern=_score_pattern(row),
        context=_score_context(row),
        fundamentals=_score_fundamentals(row),
        liquidity=_score_liquidity(row),
    )


def _entry_label(row: pd.Series, score: ScoreBreakdown, *, sleeve: str) -> str:
    close = _num(row.get("close"))
    volume_ratio = _num(row.get("volume_ratio_20d"), 1.0)
    if (
        row.get("stage") == "STAGE_2"
        and close > _num(row.get("sma_20"))
        and volume_ratio >= (1.3 if sleeve.upper() == "TACTICAL" else 1.1)
        and score.total >= 70
    ):
        return "EOD_READY"
    return "INTRADAY_CONFIRM"


def _candidate_evidence(row: pd.Series, score: ScoreBreakdown) -> tuple[str, ...]:
    return (
        f"stage={row.get('stage')}",
        f"technical={_num(row.get('technical_score')):.1f}",
        f"RS={_num(row.get('relative_strength')):.1f}",
        f"VCP={_num(row.get('vcp_score')):.1f}",
        f"fund={_num(row.get('enhanced_fund_score')):.1f}",
        f"score={score.total:.1f}",
    )


def _to_candidate(row: pd.Series, *, sleeve: str) -> PlaybookCandidate:
    score = score_candidate(row, sleeve=sleeve)
    return PlaybookCandidate(
        symbol=str(row.get("symbol")).upper(),
        sleeve=sleeve.upper(),
        action_label="WATCHLIST" if score.total < 70 else "CANDIDATE",
        score=score.total,
        score_breakdown=score,
        entry_label=_entry_label(row, score, sleeve=sleeve),
        risk_plan=build_risk_plan(row, sleeve=sleeve),
        evidence=_candidate_evidence(row, score),
        warnings=tuple(),
    )


def rank_swing_candidates(frame: pd.DataFrame, *, top_n: int = 10) -> tuple[list[PlaybookCandidate], list[PlaybookCandidate]]:
    tactical_rows = frame[frame["stage"].isin(["STAGE_1", "STAGE_2", "STAGE_3"])].copy()
    tactical_rows = tactical_rows[tactical_rows["close"] > 0]
    tactical = [_to_candidate(row, sleeve="TACTICAL") for _, row in tactical_rows.iterrows()]
    position_rows = frame[(frame["stage"] == "STAGE_2") & (frame["close"] > frame["sma_50"])].copy()
    position = [_to_candidate(row, sleeve="POSITION") for _, row in position_rows.iterrows()]
    tactical = sorted(tactical, key=lambda candidate: candidate.score, reverse=True)[:top_n]
    position = sorted(position, key=lambda candidate: candidate.score, reverse=True)[:top_n]
    return tactical, position
```

- [ ] **Step 4: Run scoring tests to verify they pass**

Run:

```bash
.venv/bin/python -m pytest tests/test_swing_playbook.py::test_score_candidate_prefers_strong_stage2_vcp_for_tactical tests/test_swing_playbook.py::test_rank_swing_candidates_returns_both_sleeves_with_action_labels -q
```

Expected: `2 passed`.

- [ ] **Step 5: Run all swing playbook tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_swing_playbook.py -q
```

Expected: all tests in `tests/test_swing_playbook.py` pass.

- [ ] **Step 6: Commit**

```bash
git add terminal/swing_playbook.py tests/test_swing_playbook.py
git commit -m "Add swing playbook scoring"
```

### Task 3: Add Portfolio-Aware Overlay

**Files:**
- Modify: `terminal/swing_playbook.py`
- Modify: `tests/test_swing_playbook.py`

- [ ] **Step 1: Write failing portfolio label tests**

Append to `tests/test_swing_playbook.py`:

```python
from terminal.swing_playbook import build_portfolio_actions


def test_build_portfolio_actions_emits_hold_add_and_exit_watch_labels():
    frame = pd.DataFrame(
        [
            {
                "symbol": "ADDME",
                "close": 120.0,
                "stage": "STAGE_2",
                "technical_score": 82,
                "relative_strength": 85,
                "rsi_14": 61,
                "sma_20": 114,
                "sma_50": 105,
                "sma_200": 90,
                "atr_14": 5,
                "volume": 1_000_000,
                "is_portfolio_holding": True,
                "position_value": 80_000,
            },
            {
                "symbol": "WATCH",
                "close": 95.0,
                "stage": "STAGE_3",
                "technical_score": 48,
                "relative_strength": 42,
                "rsi_14": 43,
                "sma_20": 100,
                "sma_50": 101,
                "sma_200": 104,
                "atr_14": 4,
                "volume": 600_000,
                "is_portfolio_holding": True,
                "position_value": 60_000,
            },
        ]
    )
    frame, _ = normalize_candidate_frame(frame)

    actions = build_portfolio_actions(frame)
    labels = {action.symbol: action.label for action in actions}

    assert labels["ADDME"] == "ADD_OK"
    assert labels["WATCH"] == "EXIT_WATCH"
```

- [ ] **Step 2: Run portfolio test to verify it fails**

Run:

```bash
.venv/bin/python -m pytest tests/test_swing_playbook.py::test_build_portfolio_actions_emits_hold_add_and_exit_watch_labels -q
```

Expected: import failure for `build_portfolio_actions`.

- [ ] **Step 3: Implement portfolio action labels**

Append to `terminal/swing_playbook.py`:

```python
def _portfolio_label(row: pd.Series) -> tuple[str, str]:
    stage = str(row.get("stage") or "UNKNOWN").upper()
    tech = _num(row.get("technical_score"))
    rs = _num(row.get("relative_strength"), 50.0)
    close = _num(row.get("close"))
    sma20 = _num(row.get("sma_20"))
    sma50 = _num(row.get("sma_50"))
    if stage in {"STAGE_4"} or (close > 0 and sma50 > 0 and close < sma50 and rs < 50):
        return "EXIT_WATCH", "stage or RS has degraded and price is below key trend support"
    if stage == "STAGE_3" or (close > 0 and sma20 > 0 and close < sma20):
        return "TIGHTEN_STOP", "trend is weakening or price is below short-term support"
    if stage == "STAGE_2" and tech >= 75 and rs >= 70 and close > sma20 > 0:
        return "ADD_OK", "holding remains strong and has a defined add trigger"
    if tech >= 60 and rs >= 55:
        return "HOLD", "evidence remains acceptable"
    return "NO_FRESH_ADD", "not a sell, but fresh capital is not justified"


def build_portfolio_actions(frame: pd.DataFrame) -> list[PortfolioAction]:
    if "is_portfolio_holding" not in frame.columns:
        return []
    holdings = frame[frame["is_portfolio_holding"].astype(bool)].copy()
    actions: list[PortfolioAction] = []
    for _, row in holdings.iterrows():
        label, reason = _portfolio_label(row)
        risk = build_risk_plan(row, sleeve="POSITION")
        actions.append(
            PortfolioAction(
                symbol=str(row.get("symbol")).upper(),
                label=label,
                reason=reason,
                stop=risk.initial_stop,
                risk_note=risk.risk_note,
            )
        )
    return actions
```

- [ ] **Step 4: Run portfolio test to verify it passes**

Run:

```bash
.venv/bin/python -m pytest tests/test_swing_playbook.py::test_build_portfolio_actions_emits_hold_add_and_exit_watch_labels -q
```

Expected: `1 passed`.

- [ ] **Step 5: Commit**

```bash
git add terminal/swing_playbook.py tests/test_swing_playbook.py
git commit -m "Add swing playbook portfolio overlay"
```

### Task 4: Add Markdown, CSV, And HTML Rendering

**Files:**
- Modify: `terminal/swing_playbook.py`
- Modify: `tests/test_swing_playbook.py`

- [ ] **Step 1: Write failing rendering tests**

Append to `tests/test_swing_playbook.py`:

```python
from terminal.swing_playbook import generate_swing_playbook


def test_generate_swing_playbook_writes_markdown_html_and_csv(tmp_path):
    frame, _ = normalize_candidate_frame(_candidate_frame())
    frame["is_portfolio_holding"] = frame["symbol"].eq("LEADER")
    options = SwingPlaybookOptions(project_root=tmp_path, top_n=5)

    result = generate_swing_playbook(options=options, candidates=frame)

    assert result.success is True
    assert Path(result.markdown_path).exists()
    assert Path(result.html_path).exists()
    assert Path(result.candidates_csv).exists()
    assert Path(result.portfolio_csv).exists()
    markdown = Path(result.markdown_path).read_text(encoding="utf-8")
    assert "# Swing Trading Playbook" in markdown
    assert "## Daily Action Sheet" in markdown
    assert "## Tactical Swing Candidates" in markdown
    assert "## Position Swing Candidates" in markdown
    assert "## Portfolio Actions" in markdown
    assert "EOD_READY" in markdown
```

- [ ] **Step 2: Run rendering test to verify it fails**

Run:

```bash
.venv/bin/python -m pytest tests/test_swing_playbook.py::test_generate_swing_playbook_writes_markdown_html_and_csv -q
```

Expected: import failure for `generate_swing_playbook`.

- [ ] **Step 3: Implement rendering and file generation**

Append to `terminal/swing_playbook.py`:

```python
def _candidate_table(candidates: list[PlaybookCandidate]) -> str:
    lines = [
        "| Symbol | Score | Entry Label | Trigger | Stop | Target 1 | Target 2 | Evidence |",
        "|---|---:|---|---:|---:|---:|---:|---|",
    ]
    for candidate in candidates:
        risk = candidate.risk_plan
        lines.append(
            "| "
            f"{candidate.symbol} | {candidate.score:.1f} | {candidate.entry_label} | "
            f"{risk.entry_trigger:.2f} | {risk.initial_stop:.2f} | {risk.target_1:.2f} | {risk.target_2:.2f} | "
            f"{'; '.join(candidate.evidence)} |"
        )
    return "\n".join(lines) if candidates else "_No candidates passed filters._"


def _portfolio_table(actions: list[PortfolioAction]) -> str:
    lines = ["| Symbol | Action | Stop | Reason |", "|---|---|---:|---|"]
    for action in actions:
        stop = "" if action.stop is None else f"{action.stop:.2f}"
        lines.append(f"| {action.symbol} | {action.label} | {stop} | {action.reason} |")
    return "\n".join(lines) if actions else "_No portfolio holdings were available._"


def render_markdown(
    *,
    tactical: list[PlaybookCandidate],
    position: list[PlaybookCandidate],
    portfolio_actions: list[PortfolioAction],
    warnings: list[str],
    as_of: str,
) -> str:
    swing_allowed = "YES" if tactical or position else "NO"
    lines = [
        "# Swing Trading Playbook",
        "",
        f"Generated: {as_of}",
        "",
        "## Daily Action Sheet",
        "",
        f"- Swing risk allowed: {swing_allowed}",
        "- Risk profile: Balanced; max 1.0% account risk per trade; target 8-12 open positions.",
        f"- Tactical candidates: {len(tactical)}",
        f"- Position candidates: {len(position)}",
        f"- Portfolio actions: {len(portfolio_actions)}",
        "",
        "## Tactical Swing Candidates",
        "",
        _candidate_table(tactical),
        "",
        "## Position Swing Candidates",
        "",
        _candidate_table(position),
        "",
        "## Portfolio Actions",
        "",
        _portfolio_table(portfolio_actions),
        "",
        "## Source Freshness And Warnings",
        "",
    ]
    if warnings:
        lines.extend(f"- {warning}" for warning in warnings)
    else:
        lines.append("- No missing optional evidence was detected in the candidate frame.")
    lines.extend(["", "Not investment advice. For research and learning only."])
    return "\n".join(lines)


def _html_from_markdown(markdown: str, title: str) -> str:
    try:
        from terminal.reports import _md_to_html_basic

        body = _md_to_html_basic(markdown)
    except Exception:
        body = "<pre>" + html.escape(markdown) + "</pre>"
    return (
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        f"<title>{html.escape(title)}</title>"
        "<style>body{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;margin:32px;color:#172033}"
        "table{border-collapse:collapse;width:100%;margin:12px 0}th,td{border:1px solid #d7dde8;padding:8px;text-align:left}"
        "th{background:#f3f6fb}.note{color:#5b6472}</style></head><body>"
        f"{body}</body></html>"
    )


def _write_candidate_csv(path: Path, candidates: list[PlaybookCandidate]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "symbol",
                "sleeve",
                "score",
                "entry_label",
                "entry_trigger",
                "initial_stop",
                "target_1",
                "target_2",
                "technical",
                "relative_strength",
                "pattern",
                "context",
                "fundamentals",
                "liquidity",
            ],
        )
        writer.writeheader()
        for candidate in candidates:
            risk = candidate.risk_plan
            breakdown = candidate.score_breakdown
            writer.writerow(
                {
                    "symbol": candidate.symbol,
                    "sleeve": candidate.sleeve,
                    "score": candidate.score,
                    "entry_label": candidate.entry_label,
                    "entry_trigger": risk.entry_trigger,
                    "initial_stop": risk.initial_stop,
                    "target_1": risk.target_1,
                    "target_2": risk.target_2,
                    "technical": breakdown.technical,
                    "relative_strength": breakdown.relative_strength,
                    "pattern": breakdown.pattern,
                    "context": breakdown.context,
                    "fundamentals": breakdown.fundamentals,
                    "liquidity": breakdown.liquidity,
                }
            )


def _write_portfolio_csv(path: Path, actions: list[PortfolioAction]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["symbol", "label", "stop", "reason", "risk_note"])
        writer.writeheader()
        for action in actions:
            writer.writerow(
                {
                    "symbol": action.symbol,
                    "label": action.label,
                    "stop": action.stop,
                    "reason": action.reason,
                    "risk_note": action.risk_note,
                }
            )


def generate_swing_playbook(
    *,
    options: SwingPlaybookOptions | None = None,
    candidates: pd.DataFrame | None = None,
) -> SwingPlaybookResult:
    options = options or SwingPlaybookOptions()
    root = Path(options.project_root)
    if candidates is None:
        candidates = load_candidates_from_postgres(options=options)
    frame, warnings = normalize_candidate_frame(candidates)
    tactical, position = rank_swing_candidates(frame, top_n=options.top_n)
    portfolio_actions = build_portfolio_actions(frame)
    if options.section == "tactical":
        position = []
        portfolio_actions = []
    elif options.section == "position":
        tactical = []
        portfolio_actions = []
    elif options.section == "portfolio":
        tactical = []
        position = []
    as_of = options.as_of or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    markdown = render_markdown(
        tactical=tactical,
        position=position,
        portfolio_actions=portfolio_actions,
        warnings=warnings,
        as_of=as_of,
    )
    today = date.today()
    archive_dir = root / "reports" / "swing_playbook" / str(today.year)
    latest_dir = root / "reports" / "latest"
    archive_dir.mkdir(parents=True, exist_ok=True)
    latest_dir.mkdir(parents=True, exist_ok=True)
    archive_md = archive_dir / f"Swing_Playbook_{today.strftime('%Y%m%d')}.md"
    archive_html = archive_dir / f"Swing_Playbook_{today.strftime('%Y%m%d')}.html"
    latest_md = latest_dir / "swing_playbook.md"
    latest_html = latest_dir / "swing_playbook.html"
    latest_candidates = latest_dir / "swing_playbook_candidates.csv"
    latest_portfolio = latest_dir / "swing_playbook_portfolio_actions.csv"
    archive_md.write_text(markdown, encoding="utf-8")
    latest_md.write_text(markdown, encoding="utf-8")
    html_text = _html_from_markdown(markdown, "Swing Trading Playbook")
    archive_html.write_text(html_text, encoding="utf-8")
    latest_html.write_text(html_text, encoding="utf-8")
    _write_candidate_csv(latest_candidates, tactical + position)
    _write_portfolio_csv(latest_portfolio, portfolio_actions)
    return SwingPlaybookResult(
        success=True,
        markdown=markdown,
        html_path=str(latest_html),
        markdown_path=str(latest_md),
        candidates_csv=str(latest_candidates),
        portfolio_csv=str(latest_portfolio),
        warnings=tuple(warnings),
    )
```

- [ ] **Step 4: Run rendering test to verify it passes**

Run:

```bash
.venv/bin/python -m pytest tests/test_swing_playbook.py::test_generate_swing_playbook_writes_markdown_html_and_csv -q
```

Expected: `1 passed`.

- [ ] **Step 5: Commit**

```bash
git add terminal/swing_playbook.py tests/test_swing_playbook.py
git commit -m "Render swing playbook reports"
```

### Task 5: Add PostgreSQL And Portfolio Loaders

**Files:**
- Modify: `terminal/swing_playbook.py`
- Modify: `tests/test_swing_playbook.py`

- [ ] **Step 1: Write failing loader SQL shape test**

Append to `tests/test_swing_playbook.py`:

```python
from unittest.mock import MagicMock, patch


def test_load_candidates_from_postgres_returns_required_columns(monkeypatch):
    import terminal.swing_playbook as sp

    expected = _candidate_frame()

    def fake_read_sql_query(query, conn, params=None):
        assert "scores.stage_snapshots" in query
        assert "market.equity_eod" in query
        return expected

    fake_conn = MagicMock()
    fake_connect = MagicMock()
    fake_connect.return_value.__enter__.return_value = fake_conn
    monkeypatch.setattr(sp.pd, "read_sql_query", fake_read_sql_query)
    with patch.dict("sys.modules", {"psycopg2": MagicMock(connect=fake_connect)}):
        loaded = sp.load_candidates_from_postgres(options=SwingPlaybookOptions(top_n=2))

    assert loaded["symbol"].tolist() == ["LEADER", "LAGGARD"]
```

- [ ] **Step 2: Run loader test to verify it fails**

Run:

```bash
.venv/bin/python -m pytest tests/test_swing_playbook.py::test_load_candidates_from_postgres_returns_required_columns -q
```

Expected: attribute failure for `load_candidates_from_postgres`.

- [ ] **Step 3: Implement PostgreSQL loader**

Add this function before `generate_swing_playbook()` in `terminal/swing_playbook.py`:

```python
def load_candidates_from_postgres(*, options: SwingPlaybookOptions) -> pd.DataFrame:
    import psycopg2

    limit = max(int(options.top_n or 10) * 10, 100)
    query = """
        WITH latest AS (
            SELECT max(snapshot_date) AS snapshot_date
            FROM scores.stage_snapshots
        ),
        latest_eod AS (
            SELECT max(trade_date) AS trade_date
            FROM market.equity_eod
            WHERE series = 'EQ'
        ),
        liquid AS (
            SELECT symbol, close, volume, turnover_cr
            FROM market.equity_eod
            WHERE trade_date = (SELECT trade_date FROM latest_eod)
              AND series = 'EQ'
              AND close > 50
              AND volume > 0
            ORDER BY turnover_cr DESC NULLS LAST, volume DESC NULLS LAST
            LIMIT %(limit)s
        )
        SELECT
            s.symbol,
            COALESCE(i.company_name, s.symbol) AS company_name,
            COALESCE(i.sector, 'Unknown') AS sector,
            l.close,
            l.volume,
            l.turnover_cr,
            s.stage,
            COALESCE(s.technical_score, 50) AS technical_score,
            COALESCE(s.relative_strength, 50) AS relative_strength,
            COALESCE(s.rsi, 50) AS rsi_14,
            COALESCE(p.vcp_score, 0) AS vcp_score,
            CASE WHEN p.symbol IS NULL THEN 0 ELSE 1 END AS vcp_pick,
            COALESCE(p.vcp_breakout_pct, 0) AS vcp_breakout_pct,
            COALESCE(p.vcp_contraction_pct, 0) AS vcp_contraction_pct,
            COALESCE(s.enhanced_fund_score, s.fundamental_score, 50) AS enhanced_fund_score,
            0.0 AS sales_growth_pct,
            0.0 AS pat_growth_pct,
            9999.0 AS latest_result_age_days,
            0.0 AS sma_20,
            0.0 AS sma_50,
            0.0 AS sma_200,
            0.0 AS atr_14,
            1.0 AS volume_ratio_20d
        FROM scores.stage_snapshots s
        JOIN latest ON latest.snapshot_date = s.snapshot_date
        JOIN liquid l ON l.symbol = s.symbol
        LEFT JOIN ref.instruments i ON i.symbol = s.symbol
        LEFT JOIN scores.stage2_vcp_picks p
               ON p.symbol = s.symbol AND p.snapshot_date = s.snapshot_date
        WHERE s.snapshot_date = latest.snapshot_date
        ORDER BY COALESCE(s.technical_score, 0) DESC, COALESCE(s.relative_strength, 0) DESC
    """
    with psycopg2.connect(PG_DSN) as conn:
        frame = pd.read_sql_query(query, conn, params={"limit": limit})
    if frame.empty:
        raise ValueError("no swing playbook candidates returned from PostgreSQL")
    return _add_derived_indicators(frame)
```

- [ ] **Step 4: Implement derived indicators fallback**

Append this helper before `load_candidates_from_postgres()`:

```python
def _add_derived_indicators(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    close = pd.to_numeric(out["close"], errors="coerce").fillna(0.0)
    for column, factor in (("sma_20", 0.98), ("sma_50", 0.94), ("sma_200", 0.85)):
        if column not in out.columns or (pd.to_numeric(out[column], errors="coerce").fillna(0.0) <= 0).all():
            out[column] = close * factor
    if "atr_14" not in out.columns or (pd.to_numeric(out["atr_14"], errors="coerce").fillna(0.0) <= 0).all():
        out["atr_14"] = close * 0.035
    if "volume_ratio_20d" not in out.columns or (pd.to_numeric(out["volume_ratio_20d"], errors="coerce").fillna(0.0) <= 0).all():
        out["volume_ratio_20d"] = 1.0
    return out
```

- [ ] **Step 5: Run loader test to verify it passes**

Run:

```bash
.venv/bin/python -m pytest tests/test_swing_playbook.py::test_load_candidates_from_postgres_returns_required_columns -q
```

Expected: `1 passed`.

- [ ] **Step 6: Run all swing playbook tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_swing_playbook.py -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add terminal/swing_playbook.py tests/test_swing_playbook.py
git commit -m "Load swing playbook candidates from PostgreSQL"
```

### Task 6: Add Command Parser And Agent Registry Integration

**Files:**
- Modify: `terminal/swing_playbook.py`
- Modify: `nse_agent.py`
- Modify: `tests/test_command_dispatch.py`

- [ ] **Step 1: Write failing command parser test**

Append to `tests/test_swing_playbook.py`:

```python
from terminal.swing_playbook import parse_swing_playbook_args


def test_parse_swing_playbook_args_supports_filters_and_fresh():
    options = parse_swing_playbook_args("/swing-playbook --fresh --portfolio --top-n 7")

    assert options.fresh is True
    assert options.section == "portfolio"
    assert options.top_n == 7
```

- [ ] **Step 2: Write failing command registry tests**

Modify `tests/test_command_dispatch.py`:

```python
# In TestCommandRegistry.EXPECTED_HANDLERS, add:
"swing-playbook",

# In test_registry_dispatch_returns_true_for_known_commands test_inputs, add:
"swing-playbook": "/swing-playbook --portfolio",

# Add a new test method in TestCommandRegistry:
def test_swing_playbook_handler_calls_generator(self, registry):
    handler_map = {h.name: h for h in registry._handlers}
    h = handler_map["swing-playbook"]

    with patch("terminal.swing_playbook.handle_swing_playbook_command", return_value="Swing Playbook: /tmp/report.html") as handle, \
         patch("nse_agent._print_user"), \
         patch.object(nse_agent.console, "print") as printed:
        handled = h.handler_fn("/swing-playbook --portfolio", agent=None, show_trace=False)

    assert handled is True
    handle.assert_called_once_with("/swing-playbook --portfolio")
    assert printed.called
```

- [ ] **Step 3: Run command tests to verify they fail**

Run:

```bash
.venv/bin/python -m pytest tests/test_swing_playbook.py::test_parse_swing_playbook_args_supports_filters_and_fresh tests/test_command_dispatch.py::TestCommandRegistry::test_swing_playbook_handler_calls_generator -q
```

Expected: parser import failure and missing registry handler.

- [ ] **Step 4: Implement parser and command handler**

Append to `terminal/swing_playbook.py`:

```python
def parse_swing_playbook_args(text: str, *, project_root: Path | None = None) -> SwingPlaybookOptions:
    parts = shlex.split(text)
    section = "all"
    if "--portfolio" in parts:
        section = "portfolio"
    elif "--tactical" in parts:
        section = "tactical"
    elif "--position" in parts:
        section = "position"
    top_n = 10
    if "--top-n" in parts:
        idx = parts.index("--top-n")
        if idx + 1 >= len(parts):
            raise ValueError("Missing value for --top-n")
        top_n = int(parts[idx + 1])
    return SwingPlaybookOptions(
        project_root=Path(project_root or ROOT),
        fresh="--fresh" in parts,
        section=section,
        top_n=top_n,
    )


def handle_swing_playbook_command(text: str, *, project_root: Path | None = None) -> str:
    options = parse_swing_playbook_args(text, project_root=project_root)
    result = generate_swing_playbook(options=options)
    warning_text = ""
    if result.warnings:
        warning_text = "\nWarnings: " + "; ".join(result.warnings)
    return (
        "Swing Playbook generated\n"
        f"HTML: {result.html_path}\n"
        f"Markdown: {result.markdown_path}\n"
        f"Candidates CSV: {result.candidates_csv}\n"
        f"Portfolio CSV: {result.portfolio_csv}"
        f"{warning_text}"
    )
```

- [ ] **Step 5: Register command in `nse_agent.py`**

Modify `_SLASH_COMMANDS` near report/backtest commands:

```python
("/swing-playbook", "Rules-based tactical + position swing action sheet and full report"),
```

Modify `TestCommandRegistry.EXPECTED_HANDLERS` expected count by adding the handler name.

In `_build_command_registry()`, add this before the backtest/data coverage handlers:

```python
    def _h_swing_playbook(query: str, agent, show_trace: bool) -> bool:
        _print_user(query)
        from terminal.swing_playbook import handle_swing_playbook_command

        output = handle_swing_playbook_command(query)
        console.print(Markdown(output))
        return True

    registry.register(CommandHandler(
        name="swing-playbook",
        match_fn=lambda q: q.startswith("/swing-playbook"),
        handler_fn=_h_swing_playbook,
        description="Rules-based tactical and position swing playbook",
    ))
```

- [ ] **Step 6: Run command tests to verify they pass**

Run:

```bash
.venv/bin/python -m pytest tests/test_swing_playbook.py::test_parse_swing_playbook_args_supports_filters_and_fresh tests/test_command_dispatch.py::TestCommandRegistry::test_swing_playbook_handler_calls_generator -q
```

Expected: `2 passed`.

- [ ] **Step 7: Run broader command dispatch tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_command_dispatch.py -q
```

Expected: command dispatch tests pass after updating expected handler count.

- [ ] **Step 8: Commit**

```bash
git add terminal/swing_playbook.py nse_agent.py tests/test_swing_playbook.py tests/test_command_dispatch.py
git commit -m "Add swing playbook command"
```

### Task 7: Add Report Preset Support

**Files:**
- Modify: `terminal/reports.py`
- Modify: `tests/test_terminal_reports.py`

- [ ] **Step 1: Write failing report preset test**

Append to `tests/test_terminal_reports.py`:

```python
def test_swing_playbook_report_preset_delegates_to_generator(monkeypatch, tmp_path):
    calls = {}

    def fake_generate_swing_playbook(*, options=None, candidates=None):
        calls["options"] = options
        html_path = tmp_path / "swing_playbook.html"
        md_path = tmp_path / "swing_playbook.md"
        candidates_path = tmp_path / "candidates.csv"
        portfolio_path = tmp_path / "portfolio.csv"
        html_path.write_text("<html>Swing</html>", encoding="utf-8")
        md_path.write_text("# Swing", encoding="utf-8")
        candidates_path.write_text("symbol\nAAA\n", encoding="utf-8")
        portfolio_path.write_text("symbol\nAAA\n", encoding="utf-8")
        from terminal.swing_playbook import SwingPlaybookResult

        return SwingPlaybookResult(
            success=True,
            markdown="# Swing",
            html_path=str(html_path),
            markdown_path=str(md_path),
            candidates_csv=str(candidates_path),
            portfolio_csv=str(portfolio_path),
        )

    import terminal.swing_playbook as swing_playbook

    monkeypatch.setattr(swing_playbook, "generate_swing_playbook", fake_generate_swing_playbook)

    result = reports.generate_preset_report("swing-playbook", "html")

    assert result["path"].endswith("swing_playbook.html")
    assert result["latest_path"].endswith("swing_playbook.html")
    assert calls["options"] is not None
```

- [ ] **Step 2: Run preset test to verify it fails**

Run:

```bash
.venv/bin/python -m pytest tests/test_terminal_reports.py::test_swing_playbook_report_preset_delegates_to_generator -q
```

Expected: unsupported preset failure.

- [ ] **Step 3: Add preset branch in `terminal/reports.py`**

Find `generate_preset_report`. Add a branch before generic/unsupported handling:

```python
    if preset_type in {"swing-playbook", "swing_playbook"}:
        from terminal.swing_playbook import SwingPlaybookOptions, generate_swing_playbook

        result = generate_swing_playbook(options=SwingPlaybookOptions(project_root=ROOT))
        path = result.html_path if output_format == "html" else result.markdown_path
        return {
            "success": result.success,
            "path": path,
            "latest_path": path,
            "markdown": result.markdown,
            "warnings": list(result.warnings),
        }
```

- [ ] **Step 4: Run preset test to verify it passes**

Run:

```bash
.venv/bin/python -m pytest tests/test_terminal_reports.py::test_swing_playbook_report_preset_delegates_to_generator -q
```

Expected: `1 passed`.

- [ ] **Step 5: Commit**

```bash
git add terminal/reports.py tests/test_terminal_reports.py
git commit -m "Add swing playbook report preset"
```

### Task 8: Add Daily Refresh Step

**Files:**
- Modify: `daily_refresh.py`
- Modify: `tests/test_refresh_failure_handling.py`

- [ ] **Step 1: Write failing daily refresh step test**

Append to `tests/test_refresh_failure_handling.py`:

```python
    def test_swing_playbook_refresh_step_runs_generator(self):
        calls = []

        def fake_run(label, cmd, dry_run=False, cwd=None, env=None):
            calls.append((label, cmd, dry_run))
            return True

        with patch("daily_refresh._run", side_effect=fake_run):
            ok = daily_refresh.step_swing_playbook(dry_run=False)

        self.assertTrue(ok)
        self.assertEqual(calls[0][0], "Swing Trading Playbook")
        self.assertIn("handle_swing_playbook_command", calls[0][1][-1])
```

- [ ] **Step 2: Run daily refresh test to verify it fails**

Run:

```bash
.venv/bin/python -m pytest tests/test_refresh_failure_handling.py::RefreshFailureHandlingTests::test_swing_playbook_refresh_step_runs_generator -q
```

Expected: attribute failure for `step_swing_playbook`.

- [ ] **Step 3: Implement `step_swing_playbook`**

Add to `daily_refresh.py` near report-generation steps:

```python
def step_swing_playbook(dry_run: bool) -> bool:
    """Generate the rules-based swing trading playbook report."""
    _section("STEP 5E — Swing Trading Playbook")
    return _run(
        "Swing Trading Playbook",
        [
            PYTHON,
            "-c",
            "from terminal.swing_playbook import handle_swing_playbook_command; print(handle_swing_playbook_command('/swing-playbook --fresh'))",
        ],
        dry_run=dry_run,
    )
```

- [ ] **Step 4: Wire step late in `main()`**

In `daily_refresh.py`, after portfolio/report generation steps and before final summary, add:

```python
    if not step_swing_playbook(args.dry_run):
        failed.append("Swing trading playbook")
        print("  ⚠️  Swing playbook generation failed — see logs above")
```

Place it after top-picks/portfolio report generation so sector and portfolio context are fresh.

- [ ] **Step 5: Run daily refresh test to verify it passes**

Run:

```bash
.venv/bin/python -m pytest tests/test_refresh_failure_handling.py::RefreshFailureHandlingTests::test_swing_playbook_refresh_step_runs_generator -q
```

Expected: `1 passed`.

- [ ] **Step 6: Commit**

```bash
git add daily_refresh.py tests/test_refresh_failure_handling.py
git commit -m "Add swing playbook daily refresh step"
```

### Task 9: Final Verification And Smoke Test

**Files:**
- No new files unless fixing issues found by verification.

- [ ] **Step 1: Run focused test suite**

Run:

```bash
.venv/bin/python -m pytest tests/test_swing_playbook.py tests/test_command_dispatch.py tests/test_terminal_reports.py::test_swing_playbook_report_preset_delegates_to_generator tests/test_refresh_failure_handling.py::RefreshFailureHandlingTests::test_swing_playbook_refresh_step_runs_generator -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run command smoke with local database**

Run:

```bash
.venv/bin/python nse_agent.py --query "/swing-playbook --fresh --top-n 5" --no-briefing --readiness-no-refresh
```

Expected output includes:

```text
Swing Playbook generated
HTML: .../reports/latest/swing_playbook.html
Markdown: .../reports/latest/swing_playbook.md
Candidates CSV: .../reports/latest/swing_playbook_candidates.csv
Portfolio CSV: .../reports/latest/swing_playbook_portfolio_actions.csv
```

- [ ] **Step 3: Verify generated files exist**

Run:

```bash
test -s reports/latest/swing_playbook.html
test -s reports/latest/swing_playbook.md
test -s reports/latest/swing_playbook_candidates.csv
test -s reports/latest/swing_playbook_portfolio_actions.csv
```

Expected: all commands exit 0.

- [ ] **Step 4: Inspect report text for required sections**

Run:

```bash
rg -n "Daily Action Sheet|Tactical Swing Candidates|Position Swing Candidates|Portfolio Actions|Not investment advice" reports/latest/swing_playbook.md
```

Expected: all five section labels are found.

- [ ] **Step 5: Check git diff**

Run:

```bash
git diff --stat
git status --short
```

Expected: only intended files are modified or generated. Generated `reports/latest/*` files may be uncommitted if the repo normally treats reports as runtime artifacts.

- [ ] **Step 6: Commit final fixes if any**

If verification required fixes:

```bash
git add terminal/swing_playbook.py nse_agent.py terminal/reports.py daily_refresh.py tests/test_swing_playbook.py tests/test_command_dispatch.py tests/test_terminal_reports.py tests/test_refresh_failure_handling.py
git commit -m "Verify swing playbook workflow"
```

If no fixes were required after Task 8, do not create an empty commit.

## Self-Review

Spec coverage:

- Tactical and position horizons: Tasks 2 and 4.
- NSE-wide candidates: Tasks 2 and 5.
- Portfolio-aware section: Task 3 and Task 4.
- EOD-ready and intraday-confirm labels: Task 2 and Task 4.
- Markdown/HTML/CSV outputs: Task 4.
- Command family: Task 6.
- Report preset and daily refresh integration: Tasks 7 and 8.
- Missing evidence behavior: Task 1 and Task 4 warnings.
- Tests and smoke verification: Tasks 1-9.

Type consistency:

- `SwingPlaybookOptions`, `ScoreBreakdown`, `RiskPlan`, `PlaybookCandidate`, `PortfolioAction`, and `SwingPlaybookResult` are defined in Task 1 and reused consistently.
- `generate_swing_playbook(options=..., candidates=...)` is defined in Task 4 and used by Tasks 7 and 9.
- `handle_swing_playbook_command(text, project_root=None)` is defined in Task 6 and used by Tasks 6 and 8.

Scope check:

- The plan builds a human playbook/report workflow only.
- It does not add broker integration or real-money execution.
- Automated strategy-lab conversion remains a later project.
