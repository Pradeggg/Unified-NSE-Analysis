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
PG_DSN = (
    os.environ.get("AGENT_ADDA_PG_DSN")
    or os.environ.get("PG_DSN")
    or "dbname=nse_market user=nse_admin host=/tmp"
)


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
        if value is None or pd.isna(value):
            return None
        number = float(value)
        return None if math.isnan(number) else number
    except Exception:
        return None


def _round(value: float | None, digits: int = 2) -> float | None:
    return None if value is None else round(float(value), digits)


def _prep_ohlcv(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame()

    df = frame.copy()
    df.columns = [
        re.sub(r"_+", "_", re.sub(r"[^0-9a-zA-Z]+", "_", str(col).strip().lower())).strip("_")
        for col in df.columns
    ]
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


def pct_change_from_lookback(
    frame: pd.DataFrame,
    latest_date: str | pd.Timestamp,
    *,
    days: int,
) -> float | None:
    df = _prep_ohlcv(frame)
    if df.empty:
        return None

    latest_ts = pd.to_datetime(latest_date)
    latest_rows = df[df["trade_date"] <= latest_ts]
    if latest_rows.empty:
        return None

    latest = latest_rows.iloc[-1]
    target_ts = latest_ts - pd.Timedelta(days=days)
    prior_rows = df[df["trade_date"] <= target_ts]
    if prior_rows.empty:
        return None

    prior = prior_rows.iloc[-1]
    prior_close = _num(prior.get("close"))
    latest_close = _num(latest.get("close"))
    if prior_close in (None, 0) or latest_close is None:
        return None

    return _round(((latest_close / prior_close) - 1.0) * 100.0)


def _rsi(close: pd.Series, period: int = 14) -> float | None:
    if len(close) <= period:
        return None

    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    latest_gain = _num(gain.iloc[-1])
    latest_loss = _num(loss.iloc[-1])
    if latest_gain is None or latest_loss is None:
        return None
    if latest_loss == 0:
        return 100.0 if latest_gain > 0 else 50.0

    rs = latest_gain / latest_loss
    return _round(100 - (100 / (1 + rs)))


def _macd(close: pd.Series) -> tuple[float | None, float | None, float | None]:
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    hist = macd - signal
    return _round(_num(macd.iloc[-1])), _round(_num(signal.iloc[-1])), _round(_num(hist.iloc[-1]))


def _trend_label(
    latest: float | None,
    sma20: float | None,
    sma50: float | None,
    sma200: float | None,
    rsi14: float | None,
    macd_hist: float | None,
) -> str:
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


def build_technical_profile(
    subject: str,
    frame: pd.DataFrame,
    benchmark_frame: pd.DataFrame | None = None,
) -> TechnicalProfile:
    df = _prep_ohlcv(frame)
    if df.empty:
        return TechnicalProfile(subject=subject.upper(), missing_evidence=["eod_price_history"])

    missing: list[str] = []
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

    high_52w = (
        _round(_num(df["high"].tail(252).max()))
        if "high" in df.columns
        else _round(_num(close.tail(252).max()))
    )
    low_52w = (
        _round(_num(df["low"].tail(252).min()))
        if "low" in df.columns
        else _round(_num(close.tail(252).min()))
    )
    drawdown = _round(((latest_close / high_52w) - 1.0) * 100.0) if latest_close and high_52w else None

    volume_ratio = None
    if "volume" in df.columns and len(df) >= 20:
        avg_volume = _num(df["volume"].tail(20).mean())
        latest_volume = _num(latest.get("volume"))
        volume_ratio = (
            _round(latest_volume / avg_volume)
            if latest_volume is not None and avg_volume not in (None, 0)
            else None
        )
    else:
        missing.append("volume_ratio")

    benchmark = _prep_ohlcv(benchmark_frame) if benchmark_frame is not None else pd.DataFrame()
    ret_1m = pct_change_from_lookback(df, latest["trade_date"], days=30)
    ret_3m = pct_change_from_lookback(df, latest["trade_date"], days=90)
    b_ret_1m = (
        pct_change_from_lookback(benchmark, latest["trade_date"], days=30)
        if not benchmark.empty
        else None
    )
    b_ret_3m = (
        pct_change_from_lookback(benchmark, latest["trade_date"], days=90)
        if not benchmark.empty
        else None
    )

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


def _normalize_columns(frame: pd.DataFrame) -> pd.DataFrame:
    df = frame.copy()
    df.columns = [
        re.sub(r"_+", "_", re.sub(r"[^0-9a-zA-Z]+", "_", str(col).strip().lower())).strip("_")
        for col in df.columns
    ]
    return df


def _record_value(value: Any) -> Any:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, pd.Timestamp):
        return str(value.date())
    return value


def _records_by_symbol(frame: pd.DataFrame) -> dict[str, dict[str, Any]]:
    if frame is None or frame.empty:
        return {}

    df = _normalize_columns(frame)
    if "symbol" not in df.columns:
        return {}

    records: dict[str, dict[str, Any]] = {}
    for row in df.to_dict("records"):
        symbol = str(row.get("symbol") or "").upper().strip()
        if symbol:
            records[symbol] = {str(key): _record_value(value) for key, value in row.items()}
    return records


def _history_groups(frame: pd.DataFrame, symbol_col: str = "symbol") -> dict[str, pd.DataFrame]:
    if frame is None or frame.empty:
        return {}

    df = _normalize_columns(frame)
    normalized_symbol_col = re.sub(
        r"_+",
        "_",
        re.sub(r"[^0-9a-zA-Z]+", "_", str(symbol_col).strip().lower()),
    ).strip("_")
    if normalized_symbol_col not in df.columns:
        return {}

    groups: dict[str, pd.DataFrame] = {}
    for symbol, group in df.groupby(normalized_symbol_col, dropna=True):
        normalized_symbol = str(symbol).upper().strip()
        if normalized_symbol:
            groups[normalized_symbol] = group.copy().reset_index(drop=True)
    return groups


def _source_entry(
    name: str,
    frame: pd.DataFrame,
    source: str,
    *,
    required_columns: tuple[str, ...] = (),
) -> dict[str, Any]:
    rows = 0 if frame is None else int(len(frame))
    latest = ""
    missing_columns: list[str] = []

    if frame is not None and not frame.empty:
        df = _normalize_columns(frame)
        normalized_required = {
            re.sub(r"_+", "_", re.sub(r"[^0-9a-zA-Z]+", "_", col.strip().lower())).strip("_")
            for col in required_columns
        }
        missing_columns = sorted(normalized_required - set(df.columns))
        date_col = next(
            (col for col in ("trade_date", "timestamp", "date", "as_of", "updated_at") if col in df.columns),
            None,
        )
        if date_col is not None:
            dates = pd.to_datetime(df[date_col], errors="coerce").dropna()
            if not dates.empty:
                latest = str(dates.max().date())

    status = "missing"
    if rows and missing_columns:
        status = "degraded"
    elif rows:
        status = "primary"

    return {
        "name": name,
        "source": source,
        "rows": rows,
        "latest": latest,
        "status": status,
        "missing_columns": missing_columns,
    }


def _watchlist_source_entry(watchlist: list[str]) -> dict[str, Any]:
    symbols = sorted({str(symbol).upper().strip() for symbol in watchlist if str(symbol).strip()})
    return {
        "name": "watchlist",
        "source": "command-provided watchlist symbols",
        "rows": len(symbols),
        "latest": "",
        "status": "primary" if symbols else "missing",
        "missing_columns": [],
        "symbols": symbols,
    }


def _sector_rollup(stocks: dict[str, SubjectEvidence]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[SubjectEvidence]] = {}
    for evidence in stocks.values():
        sector = evidence.sector or "Unknown"
        grouped.setdefault(sector, []).append(evidence)

    sectors: dict[str, dict[str, Any]] = {}
    for sector, members in grouped.items():
        rs_values = [_num(member.snapshot.get("relative_strength")) for member in members]
        rs_values = [value for value in rs_values if value is not None]
        stage2_count = sum(1 for member in members if str(member.snapshot.get("stage") or "").upper() == "STAGE_2")
        buy_signal_count = sum(
            1 for member in members if str(member.snapshot.get("trading_signal") or "").upper() == "BUY"
        )
        avg_relative_strength = _round(sum(rs_values) / len(rs_values)) if rs_values else None
        if avg_relative_strength is not None and avg_relative_strength >= 10 and buy_signal_count:
            rotation_label = "leader"
        elif avg_relative_strength is not None and avg_relative_strength <= -10:
            rotation_label = "laggard"
        else:
            rotation_label = "neutral"

        sectors[sector] = {
            "stock_count": len(members),
            "stage2_count": stage2_count,
            "buy_signal_count": buy_signal_count,
            "avg_relative_strength": avg_relative_strength,
            "rotation_label": rotation_label,
            "top_symbols": [
                member.subject
                for member in sorted(
                    members,
                    key=lambda member: (
                        _num(member.snapshot.get("technical_score")) or 0,
                        _num(member.snapshot.get("investment_score")) or 0,
                        _num(member.snapshot.get("relative_strength")) or 0,
                    ),
                    reverse=True,
                )[:5]
            ],
        }
    return sectors


def _market_regime(indices: dict[str, SubjectEvidence]) -> dict[str, Any]:
    trends = [
        evidence.technical.trend_label
        for evidence in indices.values()
        if evidence.technical is not None and evidence.technical.trend_label
    ]
    constructive_count = sum(1 for trend in trends if trend in {"bullish", "constructive"})
    weak_count = sum(1 for trend in trends if trend in {"weak", "bearish"})

    if constructive_count > weak_count:
        label = "risk_on"
    elif weak_count > constructive_count:
        label = "risk_off"
    else:
        label = "neutral"

    return {
        "label": label,
        "constructive_count": constructive_count,
        "weak_count": weak_count,
        "index_count": len(trends),
        "trend_labels": trends,
    }


def _stock_sort_key(symbol: str, snapshots: dict[str, dict[str, Any]]) -> tuple[float, float, float, str]:
    snapshot = snapshots.get(symbol, {})
    return (
        _num(snapshot.get("technical_score")) or 0.0,
        _num(snapshot.get("investment_score")) or 0.0,
        _num(snapshot.get("relative_strength")) or 0.0,
        symbol,
    )


def _build_stock_evidence(
    symbol: str,
    equity_groups: dict[str, pd.DataFrame],
    snapshots: dict[str, dict[str, Any]],
    fundamentals: dict[str, dict[str, Any]],
    benchmark: pd.DataFrame,
) -> SubjectEvidence:
    frame = equity_groups.get(symbol, pd.DataFrame())
    technical = build_technical_profile(symbol, frame, benchmark_frame=benchmark)
    snapshot = snapshots.get(symbol, {})
    stock_fundamentals = fundamentals.get(symbol, {})
    missing = list(technical.missing_evidence)
    if not snapshot:
        missing.append("snapshot")
    if not stock_fundamentals:
        missing.append("fundamentals")

    return SubjectEvidence(
        subject=symbol,
        scope="stock",
        sector=str(snapshot.get("sector") or stock_fundamentals.get("sector") or ""),
        technical=technical,
        snapshot=dict(snapshot),
        fundamentals=dict(stock_fundamentals),
        missing_evidence=list(dict.fromkeys(missing)),
    )


def build_recommendation_evidence_pack(
    data: RecommendationInputData,
    *,
    top_n: int = 25,
) -> RecommendationEvidencePack:
    index_groups = _history_groups(data.index_history)
    equity_groups = _history_groups(data.equity_history)
    snapshots = _records_by_symbol(data.snapshots)
    fundamentals = _records_by_symbol(data.fundamentals)
    portfolio_records = _records_by_symbol(data.portfolio)

    if "NIFTY 50" in index_groups:
        benchmark = index_groups["NIFTY 50"]
    elif index_groups:
        benchmark = next(iter(index_groups.values()))
    else:
        benchmark = pd.DataFrame()

    indices: dict[str, SubjectEvidence] = {}
    for symbol, frame in index_groups.items():
        technical = build_technical_profile(symbol, frame, benchmark_frame=benchmark)
        indices[symbol] = SubjectEvidence(
            subject=symbol,
            scope="index",
            technical=technical,
            missing_evidence=list(technical.missing_evidence),
        )

    candidate_symbols = set(equity_groups) | set(snapshots) | set(fundamentals)
    ordered_symbols = sorted(candidate_symbols, key=lambda symbol: _stock_sort_key(symbol, snapshots), reverse=True)
    if top_n > 0:
        ordered_symbols = ordered_symbols[:top_n]

    stocks: dict[str, SubjectEvidence] = {}
    for symbol in ordered_symbols:
        stocks[symbol] = _build_stock_evidence(symbol, equity_groups, snapshots, fundamentals, benchmark)

    watchlist_symbols = {str(symbol).upper().strip() for symbol in data.watchlist if str(symbol).strip()}
    portfolio_symbols = sorted(set(portfolio_records) | watchlist_symbols)
    portfolio: dict[str, SubjectEvidence] = {}
    for symbol in portfolio_symbols:
        source = stocks.get(symbol)
        if source is None:
            source = _build_stock_evidence(symbol, equity_groups, snapshots, fundamentals, benchmark)

        portfolio_record = dict(portfolio_records.get(symbol, {}))
        if not portfolio_record:
            portfolio_record = {"symbol": symbol, "watchlist": True}
        elif symbol in watchlist_symbols:
            portfolio_record["watchlist"] = True

        portfolio[symbol] = SubjectEvidence(
            subject=symbol,
            scope="portfolio",
            sector=source.sector,
            technical=source.technical,
            snapshot=dict(source.snapshot),
            fundamentals=dict(source.fundamentals),
            portfolio=portfolio_record,
            missing_evidence=list(source.missing_evidence),
        )

    source_trail = {
        "index_history": _source_entry(
            "index_history",
            data.index_history,
            "PostgreSQL market index history or CSV fallback",
            required_columns=("symbol", "trade_date", "close"),
        ),
        "equity_history": _source_entry(
            "equity_history",
            data.equity_history,
            "PostgreSQL market equity history or CSV fallback",
            required_columns=("symbol", "trade_date", "close"),
        ),
        "snapshots": _source_entry(
            "snapshots",
            data.snapshots,
            "scores latest snapshot or CSV fallback",
            required_columns=("symbol",),
        ),
        "fundamentals": _source_entry(
            "fundamentals",
            data.fundamentals,
            "screener fundamentals or cache fallback",
            required_columns=("symbol",),
        ),
        "portfolio": _source_entry(
            "portfolio",
            data.portfolio,
            "portfolio holdings source",
            required_columns=("symbol",),
        ),
        "watchlist": _watchlist_source_entry(data.watchlist),
    }
    missing_evidence = {
        name: [f"source_{entry['status']}"]
        for name, entry in source_trail.items()
        if entry.get("status") in {"missing", "degraded"}
    }
    as_of = str(source_trail["equity_history"].get("latest") or source_trail["index_history"].get("latest") or "")

    return RecommendationEvidencePack(
        run_id=str(uuid4()),
        as_of=as_of,
        generated_at=datetime.now().isoformat(timespec="seconds"),
        indices=indices,
        sectors=_sector_rollup(stocks),
        stocks=stocks,
        portfolio=portfolio,
        market_regime=_market_regime(indices),
        source_trail=source_trail,
        missing_evidence=missing_evidence,
    )


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


_FUNDAMENTAL_ALIASES = {
    "roe": ("roe", "return_on_equity", "return_on_equity_pct"),
    "roce": ("roce", "return_on_capital_employed", "return_on_capital_employed_pct"),
    "interest_coverage": ("interest_coverage", "interest_coverage_ratio", "interest_cover"),
}


def _aliased_num(record: dict[str, Any], field_name: str) -> float | None:
    for alias in _FUNDAMENTAL_ALIASES[field_name]:
        value = _num(record.get(alias))
        if value is not None:
            return value
    return None


def classify_fundamentals(fundamentals: dict[str, Any]) -> str:
    roe = _aliased_num(fundamentals, "roe")
    roce = _aliased_num(fundamentals, "roce")
    interest_coverage = _aliased_num(fundamentals, "interest_coverage")
    scoreable = [value for value in (roe, roce, interest_coverage) if value is not None]
    if not scoreable:
        return "quality_unknown"

    supportive = 0
    supportive += int(roe is not None and roe >= 12)
    supportive += int(roce is not None and roce >= 15)
    supportive += int(interest_coverage is not None and interest_coverage >= 3)

    weak = 0
    weak += int(roe is not None and roe < 8)
    weak += int(roce is not None and roce < 10)
    weak += int(interest_coverage is not None and interest_coverage < 1.5)

    if weak >= 2:
        return "quality_weak"
    if supportive >= 2 and weak == 0:
        return "quality_supportive"
    return "quality_mixed"


def _technical_evidence(evidence: SubjectEvidence) -> list[str]:
    snapshot = evidence.snapshot or {}
    technical = evidence.technical
    items: list[str] = []

    stage = str(snapshot.get("stage") or "").upper().strip()
    if stage:
        items.append(f"Stage {stage}")
    signal = str(snapshot.get("trading_signal") or "").upper().strip()
    if signal:
        items.append(f"Signal {signal}")

    technical_score = _num(snapshot.get("technical_score"))
    if technical_score is not None:
        items.append(f"Technical score {_round(technical_score)}")
    relative_strength = _num(snapshot.get("relative_strength"))
    if relative_strength is not None:
        items.append(f"Relative strength {_round(relative_strength)}")

    if technical is not None:
        if technical.trend_label:
            items.append(f"Trend {technical.trend_label}")
        if technical.latest_close is not None:
            items.append(f"Close {_round(technical.latest_close)}")
        if technical.price_above_sma20 is not None:
            items.append(f"Above SMA20 {technical.price_above_sma20}")
        if technical.price_above_sma50 is not None:
            items.append(f"Above SMA50 {technical.price_above_sma50}")
        if technical.price_above_sma200 is not None:
            items.append(f"Above SMA200 {technical.price_above_sma200}")
        if technical.rsi14 is not None:
            items.append(f"RSI14 {_round(technical.rsi14)}")

    return items or ["Technical evidence unavailable"]


def _fundamental_evidence(fundamentals: dict[str, Any]) -> list[str]:
    classification = classify_fundamentals(fundamentals)
    items = [f"Fundamental quality {classification}"]

    roe = _aliased_num(fundamentals, "roe")
    roce = _aliased_num(fundamentals, "roce")
    interest_coverage = _aliased_num(fundamentals, "interest_coverage")
    stock_pe = _num(fundamentals.get("stock_pe") or fundamentals.get("pe") or fundamentals.get("price_to_earnings"))

    if roe is not None:
        items.append(f"ROE {_round(roe)}")
    if roce is not None:
        items.append(f"ROCE {_round(roce)}")
    if interest_coverage is not None:
        items.append(f"Interest coverage {_round(interest_coverage)}")
    if stock_pe is not None:
        items.append(f"Stock PE {_round(stock_pe)}")

    return items


def _score(evidence: SubjectEvidence, market_regime: dict[str, Any], sector: dict[str, Any]) -> float:
    snapshot = evidence.snapshot or {}
    technical = evidence.technical
    quality = classify_fundamentals(evidence.fundamentals or {})

    score = 50.0
    technical_score = _num(snapshot.get("technical_score"))
    if technical_score is not None:
        score += (technical_score - 50.0) * 0.35

    investment_score = _num(snapshot.get("investment_score"))
    if investment_score is not None:
        score += (investment_score - 50.0) * 0.20

    relative_strength = _num(snapshot.get("relative_strength"))
    if relative_strength is not None:
        score += max(-15.0, min(15.0, relative_strength * 0.35))

    stage = str(snapshot.get("stage") or "").upper()
    score += {"STAGE_2": 8.0, "STAGE_1": 3.0, "STAGE_3": -6.0, "STAGE_4": -14.0}.get(stage, 0.0)

    signal = str(snapshot.get("trading_signal") or "").upper()
    score += {"BUY": 7.0, "HOLD": 0.0, "SELL": -12.0}.get(signal, 0.0)

    trend = technical.trend_label if technical is not None else ""
    score += {"bullish": 8.0, "constructive": 5.0, "neutral": 0.0, "weak": -7.0, "bearish": -12.0}.get(
        trend,
        0.0,
    )

    score += {
        "quality_supportive": 8.0,
        "quality_mixed": 2.0,
        "quality_unknown": -3.0,
        "quality_weak": -12.0,
    }[quality]

    score += {"risk_on": 4.0, "neutral": 0.0, "risk_off": -7.0}.get(str(market_regime.get("label") or ""), 0.0)
    score += {"leader": 4.0, "neutral": 0.0, "laggard": -5.0}.get(str(sector.get("rotation_label") or ""), 0.0)

    score = max(0.0, min(100.0, score))
    if "eod_price_history" in evidence.missing_evidence:
        score = min(score, 40.0)
    return _round(score)


def _policy_conflicts(evidence: SubjectEvidence, quality: str) -> list[str]:
    snapshot = evidence.snapshot or {}
    technical = evidence.technical
    conflicts = list(technical.conflicts if technical is not None else [])
    signal = str(snapshot.get("trading_signal") or "").upper()
    stage = str(snapshot.get("stage") or "").upper()
    trend = technical.trend_label if technical is not None else ""

    if signal == "BUY" and trend in {"weak", "bearish"}:
        conflicts.append("BUY signal conflicts with weak technical trend")
    if signal == "SELL" and trend in {"bullish", "constructive"}:
        conflicts.append("SELL signal conflicts with constructive technical trend")
    if stage == "STAGE_2" and quality == "quality_weak":
        conflicts.append("Stage 2 setup conflicts with weak fundamentals")

    return list(dict.fromkeys(conflicts))


def _confidence(label: str, score: float, missing_evidence: list[str], conflicts: list[str]) -> str:
    if "eod_price_history" in missing_evidence:
        return "low"
    if len(missing_evidence) >= 3:
        return "low"
    if missing_evidence:
        return "medium"
    if conflicts:
        return "low"
    if label == RecommendationLabel.ADD_ON_CONFIRMATION and score >= 75:
        return "high"
    if label == RecommendationLabel.AVOID_FRESH_ENTRY and score <= 35:
        return "high"
    return "medium"


def make_recommendation(
    evidence: SubjectEvidence,
    *,
    market_regime: dict[str, Any],
    sector: dict[str, Any],
) -> GroundedRecommendation:
    missing_evidence = list(dict.fromkeys(evidence.missing_evidence))
    technical = evidence.technical
    snapshot = evidence.snapshot or {}
    quality = classify_fundamentals(evidence.fundamentals or {})
    score = _score(evidence, market_regime, sector)
    conflicts = _policy_conflicts(evidence, quality)

    stage = str(snapshot.get("stage") or "").upper()
    signal = str(snapshot.get("trading_signal") or "").upper()
    trend = technical.trend_label if technical is not None else ""

    if "eod_price_history" in missing_evidence:
        label = RecommendationLabel.REVIEW_MANUALLY
        why = "Price history is missing, so the recommendation requires manual review."
    elif stage == "STAGE_4" or signal == "SELL" or trend in {"weak", "bearish"} or quality == "quality_weak":
        label = RecommendationLabel.AVOID_FRESH_ENTRY
        why = "Risk controls block fresh entry because the setup has weak trend, signal, stage, or fundamentals."
    elif conflicts:
        label = RecommendationLabel.WATCHLIST
        why = "Evidence is not aligned enough for action; keep it on watchlist until conflicts resolve."
    elif (
        stage == "STAGE_2"
        and signal == "BUY"
        and trend in {"bullish", "constructive"}
        and quality in {"quality_supportive", "quality_mixed"}
        and score >= 60
    ):
        label = RecommendationLabel.ADD_ON_CONFIRMATION
        why = "Stage 2, BUY signal, constructive trend, and acceptable fundamentals support adding on confirmation."
    elif evidence.scope == "portfolio":
        label = RecommendationLabel.HOLD
        why = "Existing holding has no fresh add or exit trigger from the grounded policy."
    else:
        label = RecommendationLabel.WATCHLIST
        why = "Setup is incomplete for action; monitor for clearer technical and fundamental confirmation."

    technical_evidence = _technical_evidence(evidence)
    fundamental_evidence = _fundamental_evidence(evidence.fundamentals or {})

    trigger = "Wait for price action to confirm above resistance or a fresh BUY/Stage 2 continuation signal."
    if label == RecommendationLabel.AVOID_FRESH_ENTRY:
        trigger = "Reconsider only after trend stabilizes and Stage/SELL/quality weakness clears."
    elif label == RecommendationLabel.REVIEW_MANUALLY:
        trigger = "Collect valid EOD price history before issuing an actionable view."

    invalidation = "Invalidate if price loses key moving averages or the evidence pack adds material conflicts."
    if technical is not None and technical.support is not None:
        invalidation = f"Invalidate on a decisive close below support near {_round(technical.support)}."

    risk = "Position sizing should reflect market regime, sector rotation, and missing evidence."
    if str(market_regime.get("label") or "") == "risk_off":
        risk = "Market regime is risk-off; require smaller sizing and stronger confirmation."
    elif label == RecommendationLabel.AVOID_FRESH_ENTRY:
        risk = "Primary risk is continued downside or opportunity cost from entering a weak setup."

    return GroundedRecommendation(
        subject=evidence.subject,
        scope=evidence.scope,
        label=label,
        confidence=_confidence(label, score, missing_evidence, conflicts),
        score=score,
        why=why,
        technical_evidence=technical_evidence,
        fundamental_evidence=fundamental_evidence,
        trigger=trigger,
        invalidation=invalidation,
        risk=risk,
        missing_evidence=missing_evidence,
        conflicts=conflicts,
    )


__all__ = [
    "GroundedRecommendation",
    "PG_DSN",
    "REPORT_DIR",
    "RecommendationEvidencePack",
    "RecommendationInputData",
    "RecommendationLabel",
    "ROOT",
    "SubjectEvidence",
    "TechnicalProfile",
    "build_technical_profile",
    "build_recommendation_evidence_pack",
    "classify_fundamentals",
    "make_recommendation",
    "pct_change_from_lookback",
]
