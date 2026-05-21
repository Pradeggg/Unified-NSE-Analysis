# Grounded Recommendation Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `/report recommendation` as a grounded EOD market, sector, stock, and portfolio/watchlist recommendation report with auditable technical and fundamental evidence.

**Architecture:** Add a focused `terminal/recommendation_report.py` module that owns evidence-pack dataclasses, technical metrics, scoring policy, rendering, persistence, and command parsing. Wire it into the existing `/report` branch in `nse_agent.py` as a data-direct preset report, similar to `sector-rotation` and `stage2`, while keeping existing report generation unchanged.

**Tech Stack:** Python 3, pandas, psycopg2, existing PostgreSQL schemas (`market`, `scores`, `screener`), existing `terminal.reports.generate_report`, pytest.

---

## File Structure

- Create `terminal/recommendation_report.py`
  - Owns dataclasses, metric calculations, evidence-pack building, recommendation policy, Markdown/HTML report rendering, JSON fallback persistence, PostgreSQL persistence, and `/report recommendation` argument parsing.
- Modify `nse_agent.py`
  - Adds `recommendation` to direct preset reports and dispatches to `terminal.recommendation_report.generate_recommendation_report`.
- Modify `terminal/help.py`
  - Adds `/report recommendation` examples to report help.
- Create `tests/test_recommendation_report.py`
  - Unit tests for metrics, evidence pack, policy, rendering, persistence fallback, and parser.
- Modify `tests/test_terminal_reports.py` or `tests/test_terminal_agent_market_prompt.py`
  - Adds CLI integration coverage for the `/report recommendation` branch if an existing report-command test file is a cleaner fit.

---

### Task 1: Core Types And Technical Metrics

**Files:**
- Create: `terminal/recommendation_report.py`
- Test: `tests/test_recommendation_report.py`

- [ ] **Step 1: Write failing tests for technical metrics**

Add this to `tests/test_recommendation_report.py`:

```python
import pandas as pd

from terminal.recommendation_report import (
    TechnicalProfile,
    build_technical_profile,
    pct_change_from_lookback,
)


def test_pct_change_from_lookback_uses_nearest_prior_bar():
    frame = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "close": 100.0},
            {"trade_date": "2026-01-08", "close": 110.0},
            {"trade_date": "2026-02-01", "close": 121.0},
        ]
    )

    assert pct_change_from_lookback(frame, "2026-02-01", days=7) == 10.0


def test_build_technical_profile_computes_grounded_fields():
    rows = []
    for idx in range(240):
        close = 100.0 + idx
        rows.append(
            {
                "trade_date": pd.Timestamp("2025-09-01") + pd.Timedelta(days=idx),
                "open": close - 1,
                "high": close + 2,
                "low": close - 2,
                "close": close,
                "volume": 1000 + idx,
            }
        )
    frame = pd.DataFrame(rows)

    profile = build_technical_profile("AAA", frame, benchmark_frame=frame)

    assert isinstance(profile, TechnicalProfile)
    assert profile.subject == "AAA"
    assert profile.latest_close == 339.0
    assert profile.sma20 is not None
    assert profile.sma50 is not None
    assert profile.sma200 is not None
    assert profile.price_above_sma20 is True
    assert profile.price_above_sma50 is True
    assert profile.price_above_sma200 is True
    assert profile.rsi14 is not None
    assert profile.macd_hist is not None
    assert profile.trend_label in {"bullish", "constructive"}
    assert profile.missing_evidence == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
.venv/bin/python -m pytest tests/test_recommendation_report.py::test_pct_change_from_lookback_uses_nearest_prior_bar tests/test_recommendation_report.py::test_build_technical_profile_computes_grounded_fields -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'terminal.recommendation_report'`.

- [ ] **Step 3: Implement core types and metrics**

Create `terminal/recommendation_report.py` with:

```python
"""Grounded EOD recommendation report generation."""

from __future__ import annotations

import json
import math
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd


ROOT = Path(__file__).resolve().parent.parent
REPORT_DIR = ROOT / "reports" / "recommendations"
PG_DSN = os.environ.get("AGENT_ADDA_PG_DSN") or os.environ.get("PG_DSN") or "dbname=nse_market user=nse_admin host=/tmp"


@dataclass
class TechnicalProfile:
    subject: str
    latest_date: str = ""
    latest_close: float | None = None
    ret_1w: float | None = None
    ret_1m: float | None = None
    ret_3m: float | None = None
    ret_6m: float | None = None
    rs_1m: float | None = None
    rs_3m: float | None = None
    sma20: float | None = None
    sma50: float | None = None
    sma200: float | None = None
    price_above_sma20: bool | None = None
    price_above_sma50: bool | None = None
    price_above_sma200: bool | None = None
    rsi14: float | None = None
    macd: float | None = None
    macd_signal: float | None = None
    macd_hist: float | None = None
    volume_ratio_20d: float | None = None
    high_52w: float | None = None
    low_52w: float | None = None
    drawdown_from_52w_high_pct: float | None = None
    support: float | None = None
    resistance: float | None = None
    trend_label: str = "neutral"
    conflicts: list[str] = field(default_factory=list)
    missing_evidence: list[str] = field(default_factory=list)


def _num(value: Any) -> float | None:
    try:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return None
        return float(value)
    except Exception:
        return None


def _round(value: float | None, digits: int = 2) -> float | None:
    return None if value is None else round(float(value), digits)


def _prep_ohlcv(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame()
    df = frame.copy()
    df.columns = [str(c).lower() for c in df.columns]
    if "timestamp" in df.columns and "trade_date" not in df.columns:
        df = df.rename(columns={"timestamp": "trade_date"})
    if "date" in df.columns and "trade_date" not in df.columns:
        df = df.rename(columns={"date": "trade_date"})
    required = {"trade_date", "close"}
    if not required.issubset(df.columns):
        return pd.DataFrame()
    df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce")
    for col in ("open", "high", "low", "close", "volume"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["trade_date", "close"]).sort_values("trade_date")
    return df.reset_index(drop=True)


def pct_change_from_lookback(frame: pd.DataFrame, latest_date: str | pd.Timestamp, *, days: int) -> float | None:
    df = _prep_ohlcv(frame)
    if df.empty:
        return None
    latest_ts = pd.to_datetime(latest_date)
    latest_rows = df[df["trade_date"] <= latest_ts]
    if latest_rows.empty:
        return None
    latest = latest_rows.iloc[-1]
    prior_rows = df[df["trade_date"] <= latest_ts - pd.Timedelta(days=days)]
    if prior_rows.empty:
        return None
    prior = prior_rows.iloc[-1]
    prior_close = _num(prior.get("close"))
    latest_close = _num(latest.get("close"))
    if prior_close in (None, 0) or latest_close is None:
        return None
    return _round(((latest_close / prior_close) - 1.0) * 100.0)


def _rsi(close: pd.Series, period: int = 14) -> float | None:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, pd.NA)
    value = 100 - (100 / (1 + rs.iloc[-1])) if len(rs) else None
    return _round(_num(value))


def _macd(close: pd.Series) -> tuple[float | None, float | None, float | None]:
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    hist = macd - signal
    return _round(_num(macd.iloc[-1])), _round(_num(signal.iloc[-1])), _round(_num(hist.iloc[-1]))


def _trend_label(latest: float | None, sma20: float | None, sma50: float | None, sma200: float | None, rsi14: float | None, macd_hist: float | None) -> str:
    if latest is None:
        return "neutral"
    positives = 0
    positives += int(sma20 is not None and latest > sma20)
    positives += int(sma50 is not None and latest > sma50)
    positives += int(sma200 is not None and latest > sma200)
    positives += int(rsi14 is not None and rsi14 >= 55)
    positives += int(macd_hist is not None and macd_hist > 0)
    if positives >= 4:
        return "bullish"
    if positives == 3:
        return "constructive"
    if positives == 2:
        return "neutral"
    if positives == 1:
        return "weak"
    return "bearish"


def build_technical_profile(subject: str, frame: pd.DataFrame, benchmark_frame: pd.DataFrame | None = None) -> TechnicalProfile:
    df = _prep_ohlcv(frame)
    missing: list[str] = []
    if df.empty:
        return TechnicalProfile(subject=subject.upper(), missing_evidence=["eod_price_history"])
    latest = df.iloc[-1]
    latest_close = _num(latest.get("close"))
    latest_date = str(latest["trade_date"].date())
    close = df["close"]
    sma20 = _round(_num(close.tail(20).mean())) if len(close) >= 20 else None
    sma50 = _round(_num(close.tail(50).mean())) if len(close) >= 50 else None
    sma200 = _round(_num(close.tail(200).mean())) if len(close) >= 200 else None
    if sma20 is None:
        missing.append("sma20_history")
    if sma50 is None:
        missing.append("sma50_history")
    if sma200 is None:
        missing.append("sma200_history")
    rsi14 = _rsi(close) if len(close) >= 15 else None
    if rsi14 is None:
        missing.append("rsi14_history")
    macd, macd_signal, macd_hist = _macd(close) if len(close) >= 35 else (None, None, None)
    if macd_hist is None:
        missing.append("macd_history")
    high_52w = _round(_num(df["high"].tail(252).max())) if "high" in df.columns else _round(_num(close.tail(252).max()))
    low_52w = _round(_num(df["low"].tail(252).min())) if "low" in df.columns else _round(_num(close.tail(252).min()))
    drawdown = _round(((latest_close / high_52w) - 1.0) * 100.0) if latest_close and high_52w else None
    volume_ratio = None
    if "volume" in df.columns and len(df) >= 20:
        avg_volume = _num(df["volume"].tail(20).mean())
        latest_volume = _num(latest.get("volume"))
        volume_ratio = _round(latest_volume / avg_volume) if latest_volume is not None and avg_volume not in (None, 0) else None
    else:
        missing.append("volume_ratio")
    benchmark = _prep_ohlcv(benchmark_frame) if benchmark_frame is not None else pd.DataFrame()
    ret_1m = pct_change_from_lookback(df, latest["trade_date"], days=30)
    ret_3m = pct_change_from_lookback(df, latest["trade_date"], days=90)
    b_ret_1m = pct_change_from_lookback(benchmark, latest["trade_date"], days=30) if not benchmark.empty else None
    b_ret_3m = pct_change_from_lookback(benchmark, latest["trade_date"], days=90) if not benchmark.empty else None
    conflicts: list[str] = []
    if rsi14 is not None and rsi14 >= 75 and sma50 is not None and latest_close is not None and latest_close > sma50:
        conflicts.append("trend constructive but RSI extended")
    if ret_1m is not None and ret_3m is not None and ret_1m < 0 < ret_3m:
        conflicts.append("short-term momentum weak against medium-term trend")
    return TechnicalProfile(
        subject=subject.upper(),
        latest_date=latest_date,
        latest_close=_round(latest_close),
        ret_1w=pct_change_from_lookback(df, latest["trade_date"], days=7),
        ret_1m=ret_1m,
        ret_3m=ret_3m,
        ret_6m=pct_change_from_lookback(df, latest["trade_date"], days=180),
        rs_1m=_round(ret_1m - b_ret_1m) if ret_1m is not None and b_ret_1m is not None else None,
        rs_3m=_round(ret_3m - b_ret_3m) if ret_3m is not None and b_ret_3m is not None else None,
        sma20=sma20,
        sma50=sma50,
        sma200=sma200,
        price_above_sma20=latest_close > sma20 if latest_close is not None and sma20 is not None else None,
        price_above_sma50=latest_close > sma50 if latest_close is not None and sma50 is not None else None,
        price_above_sma200=latest_close > sma200 if latest_close is not None and sma200 is not None else None,
        rsi14=rsi14,
        macd=macd,
        macd_signal=macd_signal,
        macd_hist=macd_hist,
        volume_ratio_20d=volume_ratio,
        high_52w=high_52w,
        low_52w=low_52w,
        drawdown_from_52w_high_pct=drawdown,
        support=_round(_num(df["low"].tail(20).min())) if "low" in df.columns else None,
        resistance=_round(_num(df["high"].tail(20).max())) if "high" in df.columns else None,
        trend_label=_trend_label(latest_close, sma20, sma50, sma200, rsi14, macd_hist),
        conflicts=conflicts,
        missing_evidence=missing,
    )
```

- [ ] **Step 4: Run tests to verify pass**

Run:

```bash
.venv/bin/python -m pytest tests/test_recommendation_report.py::test_pct_change_from_lookback_uses_nearest_prior_bar tests/test_recommendation_report.py::test_build_technical_profile_computes_grounded_fields -q
```

Expected: `2 passed`.

- [ ] **Step 5: Commit**

Run:

```bash
git add terminal/recommendation_report.py tests/test_recommendation_report.py
git commit -m "feat: add recommendation report technical profiles"
```

---

### Task 2: Evidence Pack Builder

**Files:**
- Modify: `terminal/recommendation_report.py`
- Test: `tests/test_recommendation_report.py`

- [ ] **Step 1: Write failing tests for structured evidence pack**

Append to `tests/test_recommendation_report.py`:

```python
from terminal.recommendation_report import (
    RecommendationInputData,
    build_recommendation_evidence_pack,
)


def _history(symbol: str, start: float = 100.0, rows: int = 240) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "symbol": symbol,
                "trade_date": pd.Timestamp("2025-09-01") + pd.Timedelta(days=idx),
                "open": start + idx - 1,
                "high": start + idx + 2,
                "low": start + idx - 2,
                "close": start + idx,
                "volume": 1000 + idx,
            }
            for idx in range(rows)
        ]
    )


def test_build_evidence_pack_contains_indices_sectors_stocks_and_portfolio():
    data = RecommendationInputData(
        index_history=pd.concat([_history("NIFTY 50"), _history("NIFTY BANK", 120.0)]),
        equity_history=pd.concat([_history("AAA"), _history("BBB", 80.0)]),
        snapshots=pd.DataFrame(
            [
                {"symbol": "AAA", "sector": "Capital Goods", "stage": "STAGE_2", "technical_score": 82, "relative_strength": 24, "trading_signal": "BUY", "investment_score": 76},
                {"symbol": "BBB", "sector": "Chemicals", "stage": "STAGE_4", "technical_score": 18, "relative_strength": -12, "trading_signal": "SELL", "investment_score": 30},
            ]
        ),
        fundamentals=pd.DataFrame(
            [
                {"symbol": "AAA", "roe": 18, "roce": 22, "stock_pe": 24, "interest_coverage": 8},
                {"symbol": "BBB", "roe": 5, "roce": 7, "stock_pe": 55, "interest_coverage": 1.2},
            ]
        ),
        portfolio=pd.DataFrame([{"symbol": "AAA", "qty": 10, "avg_cost": 150.0}]),
        watchlist=["BBB"],
    )

    pack = build_recommendation_evidence_pack(data, top_n=10)

    assert pack.as_of
    assert "NIFTY 50" in pack.indices
    assert "Capital Goods" in pack.sectors
    assert "AAA" in pack.stocks
    assert "BBB" in pack.stocks
    assert "AAA" in pack.portfolio
    assert "BBB" in pack.portfolio
    assert pack.source_trail["equity_history"]["rows"] == 480
    assert pack.missing_evidence == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
.venv/bin/python -m pytest tests/test_recommendation_report.py::test_build_evidence_pack_contains_indices_sectors_stocks_and_portfolio -q
```

Expected: FAIL because `RecommendationInputData` and `build_recommendation_evidence_pack` are not defined.

- [ ] **Step 3: Implement evidence pack dataclasses and builder**

Append to `terminal/recommendation_report.py`:

```python
@dataclass
class SubjectEvidence:
    subject: str
    scope: str
    sector: str = ""
    technical: TechnicalProfile | None = None
    snapshot: dict[str, Any] = field(default_factory=dict)
    fundamentals: dict[str, Any] = field(default_factory=dict)
    portfolio: dict[str, Any] = field(default_factory=dict)
    missing_evidence: list[str] = field(default_factory=list)


@dataclass
class RecommendationInputData:
    index_history: pd.DataFrame = field(default_factory=pd.DataFrame)
    equity_history: pd.DataFrame = field(default_factory=pd.DataFrame)
    snapshots: pd.DataFrame = field(default_factory=pd.DataFrame)
    fundamentals: pd.DataFrame = field(default_factory=pd.DataFrame)
    portfolio: pd.DataFrame = field(default_factory=pd.DataFrame)
    watchlist: list[str] = field(default_factory=list)


@dataclass
class RecommendationEvidencePack:
    run_id: str
    as_of: str
    generated_at: str
    indices: dict[str, SubjectEvidence] = field(default_factory=dict)
    sectors: dict[str, dict[str, Any]] = field(default_factory=dict)
    stocks: dict[str, SubjectEvidence] = field(default_factory=dict)
    portfolio: dict[str, SubjectEvidence] = field(default_factory=dict)
    market_regime: dict[str, Any] = field(default_factory=dict)
    source_trail: dict[str, dict[str, Any]] = field(default_factory=dict)
    missing_evidence: dict[str, list[str]] = field(default_factory=dict)


def _records_by_symbol(frame: pd.DataFrame) -> dict[str, dict[str, Any]]:
    if frame is None or frame.empty or "symbol" not in {str(c).lower() for c in frame.columns}:
        return {}
    df = frame.copy()
    df.columns = [str(c).lower() for c in df.columns]
    out: dict[str, dict[str, Any]] = {}
    for row in df.to_dict("records"):
        sym = str(row.get("symbol") or "").upper().strip()
        if sym:
            out[sym] = {str(k): v for k, v in row.items()}
    return out


def _history_groups(frame: pd.DataFrame, symbol_col: str = "symbol") -> dict[str, pd.DataFrame]:
    if frame is None or frame.empty:
        return {}
    df = frame.copy()
    df.columns = [str(c).lower() for c in df.columns]
    if symbol_col not in df.columns:
        return {}
    return {str(symbol).upper(): grp.copy() for symbol, grp in df.groupby(symbol_col)}


def _source_entry(name: str, frame: pd.DataFrame, source: str) -> dict[str, Any]:
    rows = 0 if frame is None else int(len(frame))
    latest = ""
    if frame is not None and not frame.empty:
        cols = {str(c).lower(): c for c in frame.columns}
        date_col = cols.get("trade_date") or cols.get("timestamp") or cols.get("date")
        if date_col:
            values = pd.to_datetime(frame[date_col], errors="coerce").dropna()
            if not values.empty:
                latest = str(values.max().date())
    return {"name": name, "source": source, "rows": rows, "latest": latest, "status": "primary" if rows else "missing"}


def _sector_rollup(stocks: dict[str, SubjectEvidence]) -> dict[str, dict[str, Any]]:
    sectors: dict[str, list[SubjectEvidence]] = {}
    for evidence in stocks.values():
        sector = evidence.sector or "Unknown"
        sectors.setdefault(sector, []).append(evidence)
    out: dict[str, dict[str, Any]] = {}
    for sector, items in sectors.items():
        stage2 = sum(1 for item in items if str(item.snapshot.get("stage")).upper() == "STAGE_2")
        buy = sum(1 for item in items if str(item.snapshot.get("trading_signal")).upper() == "BUY")
        rs_values = [_num(item.snapshot.get("relative_strength")) for item in items]
        rs_values = [v for v in rs_values if v is not None]
        out[sector] = {
            "stock_count": len(items),
            "stage2_count": stage2,
            "buy_signal_count": buy,
            "avg_relative_strength": _round(sum(rs_values) / len(rs_values)) if rs_values else None,
            "rotation_label": "leader" if stage2 and buy else "neutral",
            "top_symbols": [item.subject for item in sorted(items, key=lambda x: _num(x.snapshot.get("technical_score")) or 0, reverse=True)[:5]],
        }
    return out


def _market_regime(indices: dict[str, SubjectEvidence]) -> dict[str, Any]:
    trends = [item.technical.trend_label for item in indices.values() if item.technical is not None]
    bullish = sum(1 for trend in trends if trend in {"bullish", "constructive"})
    weak = sum(1 for trend in trends if trend in {"weak", "bearish"})
    label = "risk_on" if bullish > weak else "risk_off" if weak > bullish else "neutral"
    return {"label": label, "constructive_count": bullish, "weak_count": weak, "index_count": len(trends)}


def build_recommendation_evidence_pack(data: RecommendationInputData, *, top_n: int = 25) -> RecommendationEvidencePack:
    index_groups = _history_groups(data.index_history)
    equity_groups = _history_groups(data.equity_history)
    snapshots = _records_by_symbol(data.snapshots)
    fundamentals = _records_by_symbol(data.fundamentals)
    benchmark = index_groups.get("NIFTY 50") or next(iter(index_groups.values()), pd.DataFrame())
    indices: dict[str, SubjectEvidence] = {}
    for symbol, frame in index_groups.items():
        profile = build_technical_profile(symbol, frame, benchmark_frame=benchmark)
        indices[symbol] = SubjectEvidence(subject=symbol, scope="index", technical=profile, missing_evidence=list(profile.missing_evidence))
    stocks: dict[str, SubjectEvidence] = {}
    candidate_symbols = sorted(set(equity_groups) | set(snapshots) | set(fundamentals))
    for symbol in candidate_symbols[: max(top_n, len(candidate_symbols))]:
        profile = build_technical_profile(symbol, equity_groups.get(symbol, pd.DataFrame()), benchmark_frame=benchmark)
        snapshot = snapshots.get(symbol, {})
        fund = fundamentals.get(symbol, {})
        missing = list(dict.fromkeys(profile.missing_evidence + ([] if fund else ["fundamentals"])))
        stocks[symbol] = SubjectEvidence(
            subject=symbol,
            scope="stock",
            sector=str(snapshot.get("sector") or fund.get("sector") or ""),
            technical=profile,
            snapshot=snapshot,
            fundamentals=fund,
            missing_evidence=missing,
        )
    portfolio_records = _records_by_symbol(data.portfolio)
    portfolio_symbols = sorted(set(portfolio_records) | {str(s).upper() for s in data.watchlist})
    portfolio: dict[str, SubjectEvidence] = {}
    for symbol in portfolio_symbols:
        source = stocks.get(symbol)
        if source is None:
            profile = build_technical_profile(symbol, equity_groups.get(symbol, pd.DataFrame()), benchmark_frame=benchmark)
            source = SubjectEvidence(subject=symbol, scope="portfolio", technical=profile, missing_evidence=list(profile.missing_evidence))
        portfolio[symbol] = SubjectEvidence(
            subject=symbol,
            scope="portfolio",
            sector=source.sector,
            technical=source.technical,
            snapshot=dict(source.snapshot),
            fundamentals=dict(source.fundamentals),
            portfolio=portfolio_records.get(symbol, {"symbol": symbol, "watchlist": True}),
            missing_evidence=list(source.missing_evidence),
        )
    source_trail = {
        "index_history": _source_entry("index_history", data.index_history, "PostgreSQL market.index_eod / CSV fallback"),
        "equity_history": _source_entry("equity_history", data.equity_history, "PostgreSQL market.equity_eod / CSV fallback"),
        "snapshots": _source_entry("snapshots", data.snapshots, "scores.mv_latest_snapshot / CSV fallback"),
        "fundamentals": _source_entry("fundamentals", data.fundamentals, "scores.v_latest_fundamentals / cache fallback"),
        "portfolio": _source_entry("portfolio", data.portfolio, "data/holdings.csv / portfolio source"),
    }
    missing = {
        key: [field for field, entry in value.items() if field == "status" and entry == "missing"]
        for key, value in source_trail.items()
    }
    missing = {key: ["source_missing"] for key, value in missing.items() if value}
    pack_as_of = source_trail["equity_history"].get("latest") or source_trail["index_history"].get("latest") or ""
    return RecommendationEvidencePack(
        run_id=str(uuid4()),
        as_of=pack_as_of,
        generated_at=datetime.now().isoformat(timespec="seconds"),
        indices=indices,
        sectors=_sector_rollup(stocks),
        stocks=stocks,
        portfolio=portfolio,
        market_regime=_market_regime(indices),
        source_trail=source_trail,
        missing_evidence=missing,
    )
```

- [ ] **Step 4: Run tests to verify pass**

Run:

```bash
.venv/bin/python -m pytest tests/test_recommendation_report.py::test_build_evidence_pack_contains_indices_sectors_stocks_and_portfolio -q
```

Expected: `1 passed`.

- [ ] **Step 5: Commit**

Run:

```bash
git add terminal/recommendation_report.py tests/test_recommendation_report.py
git commit -m "feat: build recommendation evidence pack"
```

---

### Task 3: Recommendation Policy And Scoring

**Files:**
- Modify: `terminal/recommendation_report.py`
- Test: `tests/test_recommendation_report.py`

- [ ] **Step 1: Write failing tests for label policy**

Append to `tests/test_recommendation_report.py`:

```python
from terminal.recommendation_report import RecommendationLabel, classify_fundamentals, make_recommendation


def test_policy_assigns_add_on_confirmation_for_grounded_strength():
    data = RecommendationInputData(
        index_history=_history("NIFTY 50"),
        equity_history=_history("AAA"),
        snapshots=pd.DataFrame([{"symbol": "AAA", "sector": "Capital Goods", "stage": "STAGE_2", "technical_score": 88, "relative_strength": 32, "trading_signal": "BUY", "investment_score": 82}]),
        fundamentals=pd.DataFrame([{"symbol": "AAA", "roe": 18, "roce": 24, "stock_pe": 22, "interest_coverage": 9}]),
    )
    pack = build_recommendation_evidence_pack(data)

    rec = make_recommendation(pack.stocks["AAA"], market_regime=pack.market_regime, sector=pack.sectors["Capital Goods"])

    assert rec.label == RecommendationLabel.ADD_ON_CONFIRMATION
    assert rec.confidence in {"high", "medium"}
    assert rec.technical_evidence
    assert rec.fundamental_evidence
    assert rec.trigger
    assert rec.invalidation
    assert rec.risk


def test_policy_assigns_avoid_for_weak_stage_and_fundamentals():
    data = RecommendationInputData(
        index_history=_history("NIFTY 50"),
        equity_history=_history("BBB", start=300.0).assign(close=lambda df: list(reversed(df["close"].tolist()))),
        snapshots=pd.DataFrame([{"symbol": "BBB", "sector": "Chemicals", "stage": "STAGE_4", "technical_score": 18, "relative_strength": -20, "trading_signal": "SELL", "investment_score": 25}]),
        fundamentals=pd.DataFrame([{"symbol": "BBB", "roe": 4, "roce": 6, "stock_pe": 60, "interest_coverage": 1.1}]),
    )
    pack = build_recommendation_evidence_pack(data)

    rec = make_recommendation(pack.stocks["BBB"], market_regime=pack.market_regime, sector=pack.sectors["Chemicals"])

    assert rec.label == RecommendationLabel.AVOID_FRESH_ENTRY
    assert "STAGE_4" in " ".join(rec.technical_evidence)
    assert rec.confidence in {"medium", "high"}


def test_fundamental_classification_marks_missing_as_unknown():
    assert classify_fundamentals({}) == "quality_unknown"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
.venv/bin/python -m pytest tests/test_recommendation_report.py::test_policy_assigns_add_on_confirmation_for_grounded_strength tests/test_recommendation_report.py::test_policy_assigns_avoid_for_weak_stage_and_fundamentals tests/test_recommendation_report.py::test_fundamental_classification_marks_missing_as_unknown -q
```

Expected: FAIL because `RecommendationLabel`, `classify_fundamentals`, and `make_recommendation` are not defined.

- [ ] **Step 3: Implement labels, score, and policy**

Append to `terminal/recommendation_report.py`:

```python
class RecommendationLabel:
    ADD_ON_CONFIRMATION = "ADD_ON_CONFIRMATION"
    HOLD = "HOLD"
    TRIM_INTO_STRENGTH = "TRIM_INTO_STRENGTH"
    AVOID_FRESH_ENTRY = "AVOID_FRESH_ENTRY"
    WATCHLIST = "WATCHLIST"
    REVIEW_MANUALLY = "REVIEW_MANUALLY"


@dataclass
class GroundedRecommendation:
    subject: str
    scope: str
    label: str
    confidence: str
    score: float
    why: str
    technical_evidence: list[str]
    fundamental_evidence: list[str]
    trigger: str
    invalidation: str
    risk: str
    missing_evidence: list[str]
    conflicts: list[str] = field(default_factory=list)


def classify_fundamentals(fundamentals: dict[str, Any]) -> str:
    if not fundamentals:
        return "quality_unknown"
    roe = _num(fundamentals.get("roe") or fundamentals.get("return_on_equity"))
    roce = _num(fundamentals.get("roce") or fundamentals.get("return_on_capital_employed"))
    interest = _num(fundamentals.get("interest_coverage") or fundamentals.get("interest_coverage_ratio"))
    positives = int(roe is not None and roe >= 15) + int(roce is not None and roce >= 15) + int(interest is not None and interest >= 3)
    negatives = int(roe is not None and roe < 8) + int(roce is not None and roce < 8) + int(interest is not None and interest < 2)
    if positives >= 2 and negatives == 0:
        return "quality_supportive"
    if negatives >= 2:
        return "quality_weak"
    return "quality_mixed"


def _technical_evidence(evidence: SubjectEvidence) -> list[str]:
    tech = evidence.technical
    snapshot = evidence.snapshot
    lines: list[str] = []
    if snapshot.get("stage"):
        lines.append(f"Stage {snapshot.get('stage')}")
    if snapshot.get("trading_signal"):
        lines.append(f"Signal {snapshot.get('trading_signal')}")
    if snapshot.get("technical_score") is not None:
        lines.append(f"Technical score {snapshot.get('technical_score')}")
    if snapshot.get("relative_strength") is not None:
        lines.append(f"RS {snapshot.get('relative_strength')}")
    if tech:
        lines.append(f"Trend {tech.trend_label}")
        if tech.rsi14 is not None:
            lines.append(f"RSI {tech.rsi14}")
        if tech.price_above_sma50 is not None:
            lines.append(f"{'Above' if tech.price_above_sma50 else 'Below'} SMA50")
        if tech.volume_ratio_20d is not None:
            lines.append(f"Volume {tech.volume_ratio_20d}x 20D")
    return lines


def _fundamental_evidence(fundamentals: dict[str, Any]) -> list[str]:
    if not fundamentals:
        return ["Fundamentals unavailable"]
    lines: list[str] = []
    for key, label in (("roe", "ROE"), ("roce", "ROCE"), ("stock_pe", "PE"), ("interest_coverage", "Interest coverage")):
        if fundamentals.get(key) is not None:
            lines.append(f"{label} {fundamentals.get(key)}")
    return lines or ["Fundamental fields present but not scoreable"]


def _score(evidence: SubjectEvidence, market_regime: dict[str, Any], sector: dict[str, Any]) -> float:
    tech = evidence.technical
    snapshot = evidence.snapshot
    score = 0.0
    score += 10 if market_regime.get("label") == "risk_on" else 4 if market_regime.get("label") == "neutral" else 0
    score += 10 if sector.get("rotation_label") == "leader" else 5
    score += min(max((_num(snapshot.get("technical_score")) or 0), 0), 100) * 0.35
    score += 10 if str(snapshot.get("stage")).upper() == "STAGE_2" else -10 if str(snapshot.get("stage")).upper() == "STAGE_4" else 0
    score += 8 if str(snapshot.get("trading_signal")).upper() == "BUY" else -8 if str(snapshot.get("trading_signal")).upper() == "SELL" else 0
    if tech and tech.trend_label in {"bullish", "constructive"}:
        score += 12
    if classify_fundamentals(evidence.fundamentals) == "quality_supportive":
        score += 15
    elif classify_fundamentals(evidence.fundamentals) == "quality_weak":
        score -= 12
    score -= len(evidence.missing_evidence) * 3
    score -= len(tech.conflicts if tech else []) * 4
    return round(max(0.0, min(100.0, score)), 2)


def make_recommendation(evidence: SubjectEvidence, *, market_regime: dict[str, Any], sector: dict[str, Any]) -> GroundedRecommendation:
    tech = evidence.technical
    snapshot = evidence.snapshot
    quality = classify_fundamentals(evidence.fundamentals)
    score = _score(evidence, market_regime, sector)
    stage = str(snapshot.get("stage") or "").upper()
    signal = str(snapshot.get("trading_signal") or "").upper()
    trend = tech.trend_label if tech else "neutral"
    missing = list(evidence.missing_evidence)
    conflicts = list(tech.conflicts if tech else [])
    if "eod_price_history" in missing:
        label = RecommendationLabel.REVIEW_MANUALLY
    elif stage == "STAGE_4" or signal == "SELL" or trend == "bearish" or quality == "quality_weak":
        label = RecommendationLabel.AVOID_FRESH_ENTRY
    elif stage == "STAGE_2" and signal == "BUY" and trend in {"bullish", "constructive"} and quality in {"quality_supportive", "quality_mixed"} and score >= 60:
        label = RecommendationLabel.ADD_ON_CONFIRMATION
    elif conflicts:
        label = RecommendationLabel.WATCHLIST
    else:
        label = RecommendationLabel.HOLD if evidence.scope == "portfolio" else RecommendationLabel.WATCHLIST
    confidence = "high" if score >= 75 and not missing and not conflicts else "medium" if score >= 45 else "low"
    if missing:
        confidence = "medium" if confidence == "high" else "low"
    trigger = "Require next EOD close to preserve trend and volume/RS confirmation."
    invalidation = "Invalidate if price closes below SMA50 or signal/stage deteriorates."
    if label == RecommendationLabel.AVOID_FRESH_ENTRY:
        trigger = "Review only after stage, RS, and signal repair."
        invalidation = "Avoidance view weakens if price reclaims SMA50 with improving RS and fundamentals stop deteriorating."
    risk = "; ".join(conflicts) if conflicts else "No major technical conflict detected from available evidence."
    why = f"{evidence.subject}: {label} from score {score}, trend {trend}, quality {quality}."
    return GroundedRecommendation(
        subject=evidence.subject,
        scope=evidence.scope,
        label=label,
        confidence=confidence,
        score=score,
        why=why,
        technical_evidence=_technical_evidence(evidence),
        fundamental_evidence=_fundamental_evidence(evidence.fundamentals),
        trigger=trigger,
        invalidation=invalidation,
        risk=risk,
        missing_evidence=missing,
        conflicts=conflicts,
    )
```

- [ ] **Step 4: Run tests to verify pass**

Run:

```bash
.venv/bin/python -m pytest tests/test_recommendation_report.py::test_policy_assigns_add_on_confirmation_for_grounded_strength tests/test_recommendation_report.py::test_policy_assigns_avoid_for_weak_stage_and_fundamentals tests/test_recommendation_report.py::test_fundamental_classification_marks_missing_as_unknown -q
```

Expected: `3 passed`.

- [ ] **Step 5: Commit**

Run:

```bash
git add terminal/recommendation_report.py tests/test_recommendation_report.py
git commit -m "feat: add grounded recommendation policy"
```

---

### Task 4: Report Rendering And JSON Fallback Persistence

**Files:**
- Modify: `terminal/recommendation_report.py`
- Test: `tests/test_recommendation_report.py`

- [ ] **Step 1: Write failing rendering tests**

Append to `tests/test_recommendation_report.py`:

```python
from terminal.recommendation_report import (
    build_recommendations,
    render_recommendation_markdown,
    save_evidence_json,
)


def test_markdown_report_contains_grounding_and_conflicts(tmp_path):
    data = RecommendationInputData(
        index_history=_history("NIFTY 50"),
        equity_history=_history("AAA"),
        snapshots=pd.DataFrame([{"symbol": "AAA", "sector": "Capital Goods", "stage": "STAGE_2", "technical_score": 88, "relative_strength": 32, "trading_signal": "BUY", "investment_score": 82}]),
        fundamentals=pd.DataFrame([{"symbol": "AAA", "roe": 18, "roce": 24, "stock_pe": 22, "interest_coverage": 9}]),
    )
    pack = build_recommendation_evidence_pack(data)
    recommendations = build_recommendations(pack)

    markdown = render_recommendation_markdown(pack, recommendations)

    assert "# Grounded EOD Recommendation Report" in markdown
    assert "Market Regime" in markdown
    assert "Stock Opportunity Map" in markdown
    assert "Grounding & Audit Trail" in markdown
    assert "ADD_ON_CONFIRMATION" in markdown
    assert "Source Trail" in markdown


def test_save_evidence_json_writes_replayable_payload(tmp_path):
    pack = build_recommendation_evidence_pack(RecommendationInputData(index_history=_history("NIFTY 50")))

    path = save_evidence_json(pack, [], output_dir=tmp_path)

    assert path.exists()
    payload = json.loads(path.read_text())
    assert payload["pack"]["run_id"] == pack.run_id
    assert payload["recommendations"] == []
```

- [ ] **Step 2: Run tests to verify fail**

Run:

```bash
.venv/bin/python -m pytest tests/test_recommendation_report.py::test_markdown_report_contains_grounding_and_conflicts tests/test_recommendation_report.py::test_save_evidence_json_writes_replayable_payload -q
```

Expected: FAIL because rendering and JSON persistence functions are not defined.

- [ ] **Step 3: Implement recommendation list, Markdown rendering, and JSON save**

Append to `terminal/recommendation_report.py`:

```python
def _jsonable(value: Any) -> Any:
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return _jsonable(value.to_dict())
    if hasattr(value, "__dataclass_fields__"):
        return {key: _jsonable(val) for key, val in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _jsonable(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def build_recommendations(pack: RecommendationEvidencePack) -> list[GroundedRecommendation]:
    recommendations: list[GroundedRecommendation] = []
    for symbol, evidence in pack.stocks.items():
        sector = pack.sectors.get(evidence.sector or "Unknown", {})
        recommendations.append(make_recommendation(evidence, market_regime=pack.market_regime, sector=sector))
    for symbol, evidence in pack.portfolio.items():
        if symbol in pack.stocks:
            continue
        sector = pack.sectors.get(evidence.sector or "Unknown", {})
        recommendations.append(make_recommendation(evidence, market_regime=pack.market_regime, sector=sector))
    return sorted(recommendations, key=lambda rec: rec.score, reverse=True)


def _md_table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str("" if cell is None else cell).replace("\n", " ") for cell in row) + " |")
    return "\n".join(lines)


def render_recommendation_markdown(pack: RecommendationEvidencePack, recommendations: list[GroundedRecommendation]) -> str:
    lines: list[str] = []
    lines.append("# Grounded EOD Recommendation Report")
    lines.append("")
    lines.append(f"Generated: {pack.generated_at}")
    lines.append(f"As of: {pack.as_of or 'unavailable'}")
    lines.append(f"Run ID: `{pack.run_id}`")
    lines.append("")
    lines.append("Research and learning only. Not investment advice.")
    lines.append("")
    lines.append("## Executive Summary")
    lines.append("")
    lines.append(f"- Market regime: `{pack.market_regime.get('label', 'unknown')}`.")
    lines.append(f"- Recommendations generated: {len(recommendations)}.")
    lines.append(f"- Missing evidence scopes: {', '.join(pack.missing_evidence) if pack.missing_evidence else 'none'}.")
    lines.append("")
    lines.append("## Market Regime")
    lines.append("")
    index_rows = []
    for subject, evidence in pack.indices.items():
        tech = evidence.technical
        index_rows.append([subject, tech.latest_close if tech else "", tech.trend_label if tech else "", tech.ret_1m if tech else "", tech.rsi14 if tech else "", ", ".join(evidence.missing_evidence)])
    lines.append(_md_table(["Index", "Close", "Trend", "1M %", "RSI", "Missing"], index_rows or [["No index evidence", "", "", "", "", "index data missing"]]))
    lines.append("")
    lines.append("## Sector Rotation")
    lines.append("")
    sector_rows = [[name, row.get("rotation_label"), row.get("stage2_count"), row.get("buy_signal_count"), row.get("avg_relative_strength"), ", ".join(row.get("top_symbols") or [])] for name, row in pack.sectors.items()]
    lines.append(_md_table(["Sector", "Rotation", "Stage2", "Buy", "Avg RS", "Top Symbols"], sector_rows or [["No sector evidence", "", "", "", "", ""]]))
    lines.append("")
    lines.append("## Stock Opportunity Map")
    lines.append("")
    rec_rows = [[rec.subject, rec.label, rec.confidence, rec.score, rec.why, rec.trigger, rec.invalidation, rec.risk] for rec in recommendations]
    lines.append(_md_table(["Subject", "Label", "Confidence", "Score", "Why", "Trigger", "Invalidation", "Risk"], rec_rows or [["No recommendations", "", "", "", "", "", "", ""]]))
    lines.append("")
    lines.append("## Technical Detail Appendix")
    lines.append("")
    tech_rows = []
    for symbol, evidence in pack.stocks.items():
        tech = evidence.technical
        tech_rows.append([symbol, tech.trend_label if tech else "", tech.ret_1w if tech else "", tech.ret_1m if tech else "", tech.ret_3m if tech else "", tech.rsi14 if tech else "", tech.macd_hist if tech else "", "; ".join(tech.conflicts if tech else [])])
    lines.append(_md_table(["Symbol", "Trend", "1W %", "1M %", "3M %", "RSI", "MACD Hist", "Conflicts"], tech_rows or [["No stock technicals", "", "", "", "", "", "", ""]]))
    lines.append("")
    lines.append("## Fundamental Detail Appendix")
    lines.append("")
    fund_rows = [[symbol, classify_fundamentals(evidence.fundamentals), "; ".join(_fundamental_evidence(evidence.fundamentals)), ", ".join(evidence.missing_evidence)] for symbol, evidence in pack.stocks.items()]
    lines.append(_md_table(["Symbol", "Quality", "Evidence", "Missing"], fund_rows or [["No fundamentals", "", "", "fundamentals missing"]]))
    lines.append("")
    lines.append("## Grounding & Audit Trail")
    lines.append("")
    lines.append("### Source Trail")
    lines.append("")
    source_rows = [[name, row.get("source"), row.get("rows"), row.get("latest"), row.get("status")] for name, row in pack.source_trail.items()]
    lines.append(_md_table(["Source", "Label", "Rows", "Latest", "Status"], source_rows))
    lines.append("")
    lines.append("### Missing Evidence")
    lines.append("")
    if pack.missing_evidence:
        for scope, fields in pack.missing_evidence.items():
            lines.append(f"- `{scope}`: {', '.join(fields)}")
    else:
        lines.append("- none")
    return "\n".join(lines)


def save_evidence_json(pack: RecommendationEvidencePack, recommendations: list[GroundedRecommendation], *, output_dir: Path | None = None) -> Path:
    target_dir = output_dir or REPORT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"recommendation_evidence_{pack.run_id}.json"
    payload = {"pack": _jsonable(pack), "recommendations": _jsonable(recommendations)}
    path.write_text(json.dumps(payload, indent=2, default=str))
    return path
```

- [ ] **Step 4: Run rendering tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_recommendation_report.py::test_markdown_report_contains_grounding_and_conflicts tests/test_recommendation_report.py::test_save_evidence_json_writes_replayable_payload -q
```

Expected: `2 passed`.

- [ ] **Step 5: Commit**

Run:

```bash
git add terminal/recommendation_report.py tests/test_recommendation_report.py
git commit -m "feat: render grounded recommendation report"
```

---

### Task 5: Local Data Loading And Report Generation Entry Point

**Files:**
- Modify: `terminal/recommendation_report.py`
- Test: `tests/test_recommendation_report.py`

- [ ] **Step 1: Write failing tests for command options and report generation with injected data**

Append to `tests/test_recommendation_report.py`:

```python
from terminal.recommendation_report import RecommendationReportOptions, generate_recommendation_report, parse_recommendation_report_args


def test_parse_recommendation_report_args_supports_format_watchlist_and_top():
    opts = parse_recommendation_report_args(["recommendation", "--watchlist", "AAA,BBB", "--top", "12", "--format", "md"])

    assert opts.output_format == "md"
    assert opts.watchlist == ["AAA", "BBB"]
    assert opts.top_n == 12


def test_generate_recommendation_report_with_injected_data_writes_report_and_evidence(tmp_path):
    data = RecommendationInputData(
        index_history=_history("NIFTY 50"),
        equity_history=_history("AAA"),
        snapshots=pd.DataFrame([{"symbol": "AAA", "sector": "Capital Goods", "stage": "STAGE_2", "technical_score": 88, "relative_strength": 32, "trading_signal": "BUY", "investment_score": 82}]),
        fundamentals=pd.DataFrame([{"symbol": "AAA", "roe": 18, "roce": 24, "stock_pe": 22, "interest_coverage": 9}]),
    )
    opts = RecommendationReportOptions(output_format="md", output_dir=tmp_path)

    result = generate_recommendation_report(options=opts, input_data=data, persist=False)

    assert result["success"] is True
    assert result["format"] == "md"
    assert Path(result["path"]).exists()
    assert Path(result["evidence_path"]).exists()
    assert result["recommendation_count"] >= 1
```

- [ ] **Step 2: Run tests to verify fail**

Run:

```bash
.venv/bin/python -m pytest tests/test_recommendation_report.py::test_parse_recommendation_report_args_supports_format_watchlist_and_top tests/test_recommendation_report.py::test_generate_recommendation_report_with_injected_data_writes_report_and_evidence -q
```

Expected: FAIL because options, parser, and entry point are not defined.

- [ ] **Step 3: Implement options, local loaders, and generator**

Append to `terminal/recommendation_report.py`:

```python
@dataclass
class RecommendationReportOptions:
    output_format: str = "html"
    top_n: int = 25
    include_portfolio: bool = False
    watchlist: list[str] = field(default_factory=list)
    output_dir: Path | None = None


def parse_recommendation_report_args(args: list[str]) -> RecommendationReportOptions:
    parts = list(args)
    if parts and parts[0].lower() == "recommendation":
        parts = parts[1:]
    output_format = "html"
    top_n = 25
    include_portfolio = False
    watchlist: list[str] = []
    idx = 0
    while idx < len(parts):
        part = parts[idx].lower()
        if part in {"html", "pdf", "md", "markdown"}:
            output_format = "md" if part == "markdown" else part
            idx += 1
        elif part == "--format" and idx + 1 < len(parts):
            fmt = parts[idx + 1].lower()
            output_format = "md" if fmt == "markdown" else fmt
            idx += 2
        elif part == "--top" and idx + 1 < len(parts):
            top_n = max(1, int(parts[idx + 1]))
            idx += 2
        elif part == "--portfolio":
            include_portfolio = True
            idx += 1
        elif part == "--watchlist" and idx + 1 < len(parts):
            watchlist = [item.strip().upper() for item in parts[idx + 1].split(",") if item.strip()]
            idx += 2
        else:
            idx += 1
    if output_format not in {"html", "pdf", "md"}:
        output_format = "html"
    return RecommendationReportOptions(output_format=output_format, top_n=top_n, include_portfolio=include_portfolio, watchlist=watchlist)


def _load_postgres_frame(sql: str) -> pd.DataFrame:
    import psycopg2

    conn = psycopg2.connect(PG_DSN)
    try:
        return pd.read_sql_query(sql, conn)
    finally:
        conn.close()


def load_recommendation_input_data(options: RecommendationReportOptions) -> RecommendationInputData:
    index_history = pd.DataFrame()
    equity_history = pd.DataFrame()
    snapshots = pd.DataFrame()
    fundamentals = pd.DataFrame()
    try:
        index_history = _load_postgres_frame("SELECT index_symbol AS symbol, trade_date, open, high, low, close, volume FROM market.index_eod ORDER BY index_symbol, trade_date")
    except Exception:
        index_csv = ROOT / "data" / "nse_index_data.csv"
        index_history = pd.read_csv(index_csv) if index_csv.exists() else pd.DataFrame()
    try:
        equity_history = _load_postgres_frame("SELECT symbol, trade_date, open, high, low, close, volume FROM market.equity_eod ORDER BY symbol, trade_date")
    except Exception:
        stock_csv = ROOT / "data" / "nse_sec_full_data.csv"
        equity_history = pd.read_csv(stock_csv) if stock_csv.exists() else pd.DataFrame()
    try:
        snapshots = _load_postgres_frame("SELECT * FROM scores.mv_latest_snapshot")
    except Exception:
        snapshots = pd.DataFrame()
    try:
        fundamentals = _load_postgres_frame("SELECT * FROM scores.v_latest_fundamentals")
    except Exception:
        fundamentals = pd.DataFrame()
    portfolio = pd.DataFrame()
    holdings = ROOT / "data" / "holdings.csv"
    if options.include_portfolio and holdings.exists():
        portfolio = pd.read_csv(holdings)
    return RecommendationInputData(
        index_history=index_history,
        equity_history=equity_history,
        snapshots=snapshots,
        fundamentals=fundamentals,
        portfolio=portfolio,
        watchlist=options.watchlist,
    )


def generate_recommendation_report(
    *,
    options: RecommendationReportOptions | None = None,
    input_data: RecommendationInputData | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    from terminal.reports import generate_report

    opts = options or RecommendationReportOptions()
    data = input_data or load_recommendation_input_data(opts)
    pack = build_recommendation_evidence_pack(data, top_n=opts.top_n)
    recommendations = build_recommendations(pack)[: opts.top_n]
    markdown = render_recommendation_markdown(pack, recommendations)
    report_result = generate_report(
        markdown,
        report_type="research",
        symbol="Market",
        output_format=opts.output_format,
        title="Grounded EOD Recommendation Report",
        filename=f"grounded_recommendation_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
    )
    evidence_path = save_evidence_json(pack, recommendations, output_dir=opts.output_dir)
    persistence = {"status": "skipped"}
    if persist:
        persistence = persist_recommendation_run(pack, recommendations, report_result.get("path", ""), str(evidence_path))
    return {
        "success": bool(report_result.get("success")),
        "path": report_result.get("path"),
        "format": report_result.get("format"),
        "title": report_result.get("title"),
        "evidence_path": str(evidence_path),
        "recommendation_count": len(recommendations),
        "run_id": pack.run_id,
        "persistence": persistence,
    }
```

- [ ] **Step 4: Add a temporary persistence stub required by the generator**

Append this below `generate_recommendation_report` in `terminal/recommendation_report.py`:

```python
def persist_recommendation_run(pack: RecommendationEvidencePack, recommendations: list[GroundedRecommendation], report_path: str, evidence_path: str) -> dict[str, Any]:
    return {"status": "skipped", "reason": "persistence not configured"}
```

- [ ] **Step 5: Run tests to verify pass**

Run:

```bash
.venv/bin/python -m pytest tests/test_recommendation_report.py::test_parse_recommendation_report_args_supports_format_watchlist_and_top tests/test_recommendation_report.py::test_generate_recommendation_report_with_injected_data_writes_report_and_evidence -q
```

Expected: `2 passed`.

- [ ] **Step 6: Commit**

Run:

```bash
git add terminal/recommendation_report.py tests/test_recommendation_report.py
git commit -m "feat: generate grounded recommendation report"
```

---

### Task 6: PostgreSQL Persistence With JSON Fallback

**Files:**
- Modify: `terminal/recommendation_report.py`
- Test: `tests/test_recommendation_report.py`
- Modify: `postgres/schema.sql`
- Create: `postgres/migrations/20260522_recommendation_reports.sql`

- [ ] **Step 1: Write failing persistence fallback test**

Append to `tests/test_recommendation_report.py`:

```python
from unittest.mock import patch


def test_persist_recommendation_run_falls_back_when_postgres_unavailable(tmp_path):
    pack = build_recommendation_evidence_pack(RecommendationInputData(index_history=_history("NIFTY 50")))
    evidence_path = save_evidence_json(pack, [], output_dir=tmp_path)

    with patch("terminal.recommendation_report._connect_pg", side_effect=RuntimeError("pg down")):
        result = persist_recommendation_run(pack, [], "/tmp/report.md", str(evidence_path))

    assert result["status"] == "fallback_json"
    assert result["evidence_path"] == str(evidence_path)
```

- [ ] **Step 2: Run test to verify fail**

Run:

```bash
.venv/bin/python -m pytest tests/test_recommendation_report.py::test_persist_recommendation_run_falls_back_when_postgres_unavailable -q
```

Expected: FAIL because `_connect_pg` does not exist and persistence currently returns `skipped`.

- [ ] **Step 3: Add migration SQL**

Create `postgres/migrations/20260522_recommendation_reports.sql`:

```sql
CREATE SCHEMA IF NOT EXISTS recommendation_reports;

CREATE TABLE IF NOT EXISTS recommendation_reports.runs (
    run_id TEXT PRIMARY KEY,
    generated_at TIMESTAMPTZ NOT NULL,
    as_of TEXT,
    report_path TEXT,
    evidence_path TEXT,
    recommendation_count INTEGER NOT NULL DEFAULT 0,
    market_regime JSONB NOT NULL DEFAULT '{}'::jsonb,
    source_trail JSONB NOT NULL DEFAULT '{}'::jsonb,
    missing_evidence JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS recommendation_reports.evidence (
    run_id TEXT NOT NULL REFERENCES recommendation_reports.runs(run_id) ON DELETE CASCADE,
    scope TEXT NOT NULL,
    subject TEXT NOT NULL,
    evidence JSONB NOT NULL,
    PRIMARY KEY (run_id, scope, subject)
);

CREATE TABLE IF NOT EXISTS recommendation_reports.recommendations (
    run_id TEXT NOT NULL REFERENCES recommendation_reports.runs(run_id) ON DELETE CASCADE,
    subject TEXT NOT NULL,
    scope TEXT NOT NULL,
    label TEXT NOT NULL,
    confidence TEXT NOT NULL,
    score NUMERIC,
    policy JSONB NOT NULL,
    PRIMARY KEY (run_id, subject, scope)
);

CREATE INDEX IF NOT EXISTS idx_recommendation_reports_runs_generated_at
    ON recommendation_reports.runs (generated_at DESC);

CREATE INDEX IF NOT EXISTS idx_recommendation_reports_recommendations_label
    ON recommendation_reports.recommendations (label);
```

- [ ] **Step 4: Add schema SQL to `postgres/schema.sql`**

Append the same SQL block from Step 3 to `postgres/schema.sql`.

- [ ] **Step 5: Replace persistence stub**

Replace `persist_recommendation_run` in `terminal/recommendation_report.py` with:

```python
SCHEMA_SQL = """
CREATE SCHEMA IF NOT EXISTS recommendation_reports;
CREATE TABLE IF NOT EXISTS recommendation_reports.runs (
    run_id TEXT PRIMARY KEY,
    generated_at TIMESTAMPTZ NOT NULL,
    as_of TEXT,
    report_path TEXT,
    evidence_path TEXT,
    recommendation_count INTEGER NOT NULL DEFAULT 0,
    market_regime JSONB NOT NULL DEFAULT '{}'::jsonb,
    source_trail JSONB NOT NULL DEFAULT '{}'::jsonb,
    missing_evidence JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE IF NOT EXISTS recommendation_reports.evidence (
    run_id TEXT NOT NULL REFERENCES recommendation_reports.runs(run_id) ON DELETE CASCADE,
    scope TEXT NOT NULL,
    subject TEXT NOT NULL,
    evidence JSONB NOT NULL,
    PRIMARY KEY (run_id, scope, subject)
);
CREATE TABLE IF NOT EXISTS recommendation_reports.recommendations (
    run_id TEXT NOT NULL REFERENCES recommendation_reports.runs(run_id) ON DELETE CASCADE,
    subject TEXT NOT NULL,
    scope TEXT NOT NULL,
    label TEXT NOT NULL,
    confidence TEXT NOT NULL,
    score NUMERIC,
    policy JSONB NOT NULL,
    PRIMARY KEY (run_id, subject, scope)
);
CREATE INDEX IF NOT EXISTS idx_recommendation_reports_runs_generated_at
    ON recommendation_reports.runs (generated_at DESC);
CREATE INDEX IF NOT EXISTS idx_recommendation_reports_recommendations_label
    ON recommendation_reports.recommendations (label);
"""


def _connect_pg():
    import psycopg2

    return psycopg2.connect(PG_DSN)


def persist_recommendation_run(pack: RecommendationEvidencePack, recommendations: list[GroundedRecommendation], report_path: str, evidence_path: str) -> dict[str, Any]:
    try:
        from psycopg2.extras import Json

        conn = _connect_pg()
        try:
            with conn.cursor() as cur:
                cur.execute(SCHEMA_SQL)
                cur.execute(
                    """
                    INSERT INTO recommendation_reports.runs (
                        run_id, generated_at, as_of, report_path, evidence_path,
                        recommendation_count, market_regime, source_trail, missing_evidence
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (run_id) DO UPDATE SET
                        report_path=EXCLUDED.report_path,
                        evidence_path=EXCLUDED.evidence_path,
                        recommendation_count=EXCLUDED.recommendation_count,
                        market_regime=EXCLUDED.market_regime,
                        source_trail=EXCLUDED.source_trail,
                        missing_evidence=EXCLUDED.missing_evidence
                    """,
                    (
                        pack.run_id,
                        pack.generated_at,
                        pack.as_of,
                        report_path,
                        evidence_path,
                        len(recommendations),
                        Json(_jsonable(pack.market_regime)),
                        Json(_jsonable(pack.source_trail)),
                        Json(_jsonable(pack.missing_evidence)),
                    ),
                )
                for scope_name, mapping in (("index", pack.indices), ("stock", pack.stocks), ("portfolio", pack.portfolio)):
                    for subject, evidence in mapping.items():
                        cur.execute(
                            """
                            INSERT INTO recommendation_reports.evidence (run_id, scope, subject, evidence)
                            VALUES (%s, %s, %s, %s)
                            ON CONFLICT (run_id, scope, subject) DO UPDATE SET evidence=EXCLUDED.evidence
                            """,
                            (pack.run_id, scope_name, subject, Json(_jsonable(evidence))),
                        )
                for subject, evidence in pack.sectors.items():
                    cur.execute(
                        """
                        INSERT INTO recommendation_reports.evidence (run_id, scope, subject, evidence)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (run_id, scope, subject) DO UPDATE SET evidence=EXCLUDED.evidence
                        """,
                        (pack.run_id, "sector", subject, Json(_jsonable(evidence))),
                    )
                for rec in recommendations:
                    cur.execute(
                        """
                        INSERT INTO recommendation_reports.recommendations (run_id, subject, scope, label, confidence, score, policy)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (run_id, subject, scope) DO UPDATE SET
                            label=EXCLUDED.label,
                            confidence=EXCLUDED.confidence,
                            score=EXCLUDED.score,
                            policy=EXCLUDED.policy
                        """,
                        (pack.run_id, rec.subject, rec.scope, rec.label, rec.confidence, rec.score, Json(_jsonable(rec))),
                    )
            conn.commit()
        finally:
            conn.close()
        return {"status": "postgres", "schema": "recommendation_reports", "run_id": pack.run_id}
    except Exception as exc:
        return {"status": "fallback_json", "run_id": pack.run_id, "evidence_path": evidence_path, "error": str(exc)}
```

- [ ] **Step 6: Run persistence test**

Run:

```bash
.venv/bin/python -m pytest tests/test_recommendation_report.py::test_persist_recommendation_run_falls_back_when_postgres_unavailable -q
```

Expected: `1 passed`.

- [ ] **Step 7: Commit**

Run:

```bash
git add terminal/recommendation_report.py tests/test_recommendation_report.py postgres/schema.sql postgres/migrations/20260522_recommendation_reports.sql
git commit -m "feat: persist recommendation report evidence"
```

---

### Task 7: `/report recommendation` Terminal Integration

**Files:**
- Modify: `nse_agent.py`
- Modify: `terminal/help.py`
- Test: `tests/test_recommendation_report.py`
- Test: `tests/test_terminal_reports.py`

- [ ] **Step 1: Write parser coverage for report command arguments**

The parser test from Task 5 covers module-level parsing. Add this to `tests/test_terminal_reports.py` if the file already imports `nse_agent`; otherwise add to `tests/test_recommendation_report.py`:

```python
def test_report_recommendation_is_recognized_as_preset_type():
    import nse_agent

    assert "recommendation" in nse_agent._REPORT_PRESET_TYPES_FOR_TEST
```

- [ ] **Step 2: Create test seam in `nse_agent.py`**

Near the existing `/report` branch constants or module-level command constants in `nse_agent.py`, add:

```python
_REPORT_PRESET_TYPES_FOR_TEST = {"sector-rotation", "stage2", "recommendation"}
```

Then change the local `_preset_types` assignment inside the `/report` branch from:

```python
_preset_types  = {"sector-rotation", "stage2"}
```

to:

```python
_preset_types  = set(_REPORT_PRESET_TYPES_FOR_TEST)
```

- [ ] **Step 3: Run test to verify it passes**

Run:

```bash
.venv/bin/python -m pytest tests/test_terminal_reports.py::test_report_recommendation_is_recognized_as_preset_type -q
```

Expected: PASS.

- [ ] **Step 4: Wire direct report generation**

In the `/report` preset branch of `nse_agent.py`, before `generate_preset_report` is called, add:

```python
                    if rpt_type == "recommendation":
                        from terminal.recommendation_report import generate_recommendation_report, parse_recommendation_report_args

                        _opts = parse_recommendation_report_args(parts[1:])
                        _r = generate_recommendation_report(options=_opts)
                        if _r.get("success"):
                            console.print(
                                f"  [bold green]✅  Recommendation report saved![/bold green]  "
                                f"[cyan]{_r['path']}[/cyan]"
                            )
                            console.print(f"  [dim]Evidence: {_r.get('evidence_path', '')}[/dim]")
                            console.print(f"  [dim]Recommendations: {_r.get('recommendation_count', 0)} · Run ID: {_r.get('run_id', '')}[/dim]")
                            import subprocess
                            subprocess.Popen(["open", _r["path"]])
                        else:
                            console.print(f"  [bold red]❌  Recommendation report failed[/bold red]")
                        _separator()
                        continue
```

Keep the existing sector-rotation/stage2 path unchanged for other preset types.

- [ ] **Step 5: Update help text**

In `terminal/help.py`, add examples under report help:

```python
("/report recommendation", "Grounded EOD recommendation report: market, sectors, stocks, portfolio/watchlist"),
("/report recommendation --watchlist RELIANCE,TCS --format md", "Grounded recommendation report for a watchlist"),
```

Also add to `nse_agent.py` slash command list:

```python
("/report recommendation", "Grounded EOD recommendation report — indices, sectors, stocks, portfolio/watchlist"),
```

- [ ] **Step 6: Run targeted tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_recommendation_report.py tests/test_terminal_reports.py -q
```

Expected: all selected tests pass.

- [ ] **Step 7: Commit**

Run:

```bash
git add nse_agent.py terminal/help.py terminal/recommendation_report.py tests/test_recommendation_report.py tests/test_terminal_reports.py
git commit -m "feat: wire grounded recommendation report command"
```

---

### Task 8: End-To-End Verification And Guardrails

**Files:**
- Modify: `tests/test_recommendation_report.py`
- Modify: `terminal/recommendation_report.py`

- [ ] **Step 1: Add guardrail test that no recommendation lacks required grounding fields**

Append to `tests/test_recommendation_report.py`:

```python
def test_every_recommendation_has_required_grounding_fields():
    data = RecommendationInputData(
        index_history=_history("NIFTY 50"),
        equity_history=pd.concat([_history("AAA"), _history("BBB", 80.0)]),
        snapshots=pd.DataFrame(
            [
                {"symbol": "AAA", "sector": "Capital Goods", "stage": "STAGE_2", "technical_score": 88, "relative_strength": 32, "trading_signal": "BUY", "investment_score": 82},
                {"symbol": "BBB", "sector": "Chemicals", "stage": "STAGE_4", "technical_score": 18, "relative_strength": -20, "trading_signal": "SELL", "investment_score": 25},
            ]
        ),
        fundamentals=pd.DataFrame(
            [
                {"symbol": "AAA", "roe": 18, "roce": 24, "stock_pe": 22, "interest_coverage": 9},
                {"symbol": "BBB", "roe": 4, "roce": 6, "stock_pe": 60, "interest_coverage": 1.1},
            ]
        ),
    )
    pack = build_recommendation_evidence_pack(data)
    recommendations = build_recommendations(pack)

    assert recommendations
    for rec in recommendations:
        assert rec.why
        assert rec.technical_evidence
        assert rec.fundamental_evidence
        assert rec.trigger
        assert rec.invalidation
        assert rec.risk
        assert rec.confidence in {"high", "medium", "low"}
```

- [ ] **Step 2: Run guardrail test**

Run:

```bash
.venv/bin/python -m pytest tests/test_recommendation_report.py::test_every_recommendation_has_required_grounding_fields -q
```

Expected: PASS.

- [ ] **Step 3: Run compile check**

Run:

```bash
.venv/bin/python -m py_compile terminal/recommendation_report.py nse_agent.py terminal/help.py
```

Expected: exit code 0 with no output.

- [ ] **Step 4: Run focused report tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_recommendation_report.py tests/test_terminal_reports.py -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Run full test suite**

Run:

```bash
.venv/bin/python -m pytest -q
```

Expected: full suite passes.

- [ ] **Step 6: Manual smoke command**

Run:

```bash
.venv/bin/python nse_agent.py --once "/report recommendation --top 5 --format md"
```

If `--once` is not supported by the CLI entrypoint in this repository, run the generator directly:

```bash
.venv/bin/python - <<'PY'
from terminal.recommendation_report import RecommendationReportOptions, generate_recommendation_report
result = generate_recommendation_report(options=RecommendationReportOptions(output_format="md", top_n=5), persist=False)
print(result)
PY
```

Expected: output dict contains `success: True`, a report path, an evidence path, and a non-negative recommendation count.

- [ ] **Step 7: Final commit**

If Task 8 made code or test changes, run:

```bash
git add terminal/recommendation_report.py nse_agent.py terminal/help.py tests/test_recommendation_report.py tests/test_terminal_reports.py
git commit -m "test: add recommendation report grounding guardrails"
```

If Task 8 only verified existing code, do not create an empty commit.

---

## Self-Review Notes

Spec coverage:

- Market-wide regime: Task 2 evidence pack, Task 4 rendering.
- Sector rotation: Task 2 sector rollup, Task 4 rendering.
- Stock opportunity map: Task 3 policy, Task 4 rendering.
- Portfolio/watchlist: Task 2 portfolio evidence, Task 5 command options.
- Technical analysis: Task 1 metrics and Task 4 technical appendix.
- Fundamental overlay: Task 3 classification and Task 4 appendix.
- Grounding/audit: Task 4 source trail, Task 6 persistence, Task 8 guardrail.
- PostgreSQL plus fallback: Task 6.
- `/report recommendation`: Task 7.

Placeholder scan:

- The plan contains no unresolved markers or unspecified code steps.

Type consistency:

- `RecommendationInputData`, `RecommendationEvidencePack`, `SubjectEvidence`, `TechnicalProfile`, `GroundedRecommendation`, and `RecommendationReportOptions` are introduced before use.
- `generate_recommendation_report`, `parse_recommendation_report_args`, and `persist_recommendation_run` signatures remain consistent across tasks.
