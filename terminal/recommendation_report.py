"""Grounded EOD recommendation report generation."""

from __future__ import annotations

import json
import math
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
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
    payload JSONB NOT NULL,
    PRIMARY KEY (run_id, subject, scope)
);

CREATE INDEX IF NOT EXISTS idx_recommendation_reports_runs_generated_at
    ON recommendation_reports.runs (generated_at DESC);

CREATE INDEX IF NOT EXISTS idx_recommendation_reports_recommendations_label
    ON recommendation_reports.recommendations (label);
"""


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
class RecommendationReportOptions:
    output_format: str = "html"
    top_n: int = 25
    include_portfolio: bool = False
    watchlist: list[str] = field(default_factory=list)
    output_dir: Path | None = None


def _normalize_report_format(output_format: str) -> str:
    fmt = str(output_format or "").lower().strip()
    if fmt == "markdown":
        return "md"
    if fmt in {"html", "pdf", "md"}:
        return fmt
    return "html"


def parse_recommendation_report_args(args: list[str]) -> RecommendationReportOptions:
    tokens = list(args or [])
    if tokens and tokens[0].lower().strip() == "recommendation":
        tokens = tokens[1:]

    options = RecommendationReportOptions()
    idx = 0
    while idx < len(tokens):
        token = str(tokens[idx]).strip()
        lower = token.lower()

        if lower in {"html", "pdf", "md", "markdown"}:
            options.output_format = _normalize_report_format(lower)
        elif lower == "--portfolio":
            options.include_portfolio = True
        elif lower == "--format" and idx + 1 < len(tokens):
            idx += 1
            options.output_format = _normalize_report_format(tokens[idx])
        elif lower.startswith("--format="):
            options.output_format = _normalize_report_format(token.split("=", 1)[1])
        elif lower == "--top" and idx + 1 < len(tokens):
            idx += 1
            try:
                options.top_n = int(tokens[idx])
            except (TypeError, ValueError):
                pass
        elif lower.startswith("--top="):
            try:
                options.top_n = int(token.split("=", 1)[1])
            except (TypeError, ValueError):
                pass
        elif lower == "--watchlist" and idx + 1 < len(tokens):
            idx += 1
            options.watchlist = [
                symbol.upper().strip()
                for symbol in str(tokens[idx]).split(",")
                if symbol.strip()
            ]
        elif lower.startswith("--watchlist="):
            options.watchlist = [
                symbol.upper().strip()
                for symbol in token.split("=", 1)[1].split(",")
                if symbol.strip()
            ]
        idx += 1

    options.output_format = _normalize_report_format(options.output_format)
    return options


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
        return value.isoformat()
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


def _jsonable(value: Any) -> Any:
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return _jsonable(value.to_dict())
    if hasattr(value, "__dataclass_fields__"):
        return {key: _jsonable(val) for key, val in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _jsonable(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if hasattr(value, "item") and callable(value.item):
        try:
            item = value.item()
        except (TypeError, ValueError):
            item = value
        if item is not value:
            return _jsonable(item)
    return value


def build_recommendations(pack: RecommendationEvidencePack) -> list[GroundedRecommendation]:
    recommendations: list[GroundedRecommendation] = []
    for _symbol, evidence in pack.stocks.items():
        sector = pack.sectors.get(evidence.sector or "Unknown", {})
        recommendations.append(make_recommendation(evidence, market_regime=pack.market_regime, sector=sector))
    for symbol, evidence in pack.portfolio.items():
        if symbol in pack.stocks:
            continue
        sector = pack.sectors.get(evidence.sector or "Unknown", {})
        recommendations.append(make_recommendation(evidence, market_regime=pack.market_regime, sector=sector))

    label_rank = {
        RecommendationLabel.ADD_ON_CONFIRMATION: 0,
        RecommendationLabel.HOLD: 1,
        RecommendationLabel.WATCHLIST: 2,
        RecommendationLabel.AVOID_FRESH_ENTRY: 3,
        RecommendationLabel.TRIM_INTO_STRENGTH: 4,
        RecommendationLabel.REVIEW_MANUALLY: 5,
    }
    confidence_rank = {"high": 0, "medium": 1, "low": 2}
    return sorted(
        recommendations,
        key=lambda rec: (
            label_rank.get(rec.label, 99),
            confidence_rank.get(rec.confidence, 99),
            -rec.score,
            rec.subject,
        ),
    )


def _md_table(headers: list[str], rows: list[list[Any]]) -> str:
    def cell(value: Any) -> str:
        text = "" if value is None else str(value)
        return text.replace("\n", " ").replace("|", "\\|")

    lines = [
        "| " + " | ".join(cell(header) for header in headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(cell(item) for item in row) + " |")
    return "\n".join(lines)


def _joined(items: list[str]) -> str:
    return "; ".join(items) if items else ""


def _combined_subjects(pack: RecommendationEvidencePack) -> dict[str, SubjectEvidence]:
    subjects = dict(pack.stocks)
    for symbol, evidence in pack.portfolio.items():
        subjects.setdefault(symbol, evidence)
    return subjects


def render_recommendation_markdown(
    pack: RecommendationEvidencePack,
    recommendations: list[GroundedRecommendation],
) -> str:
    label_counts: dict[str, int] = {}
    for rec in recommendations:
        label_counts[rec.label] = label_counts.get(rec.label, 0) + 1
    label_summary = ", ".join(f"{label}: {count}" for label, count in sorted(label_counts.items())) or "none"
    subject_missing = {
        symbol: evidence.missing_evidence
        for symbol, evidence in sorted(_combined_subjects(pack).items())
        if evidence.missing_evidence
    }

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
    lines.append(f"- Recommendation labels: {label_summary}.")
    lines.append(
        "- Missing evidence scopes: "
        + (", ".join(sorted(pack.missing_evidence)) if pack.missing_evidence else "none")
        + "."
    )
    conflict_count = sum(1 for rec in recommendations if rec.conflicts)
    lines.append(f"- Recommendations with conflicts: {conflict_count}.")
    lines.append("")
    lines.append("## Market Regime")
    lines.append("")
    index_rows = []
    for subject, evidence in sorted(pack.indices.items()):
        technical = evidence.technical
        index_rows.append(
            [
                subject,
                technical.latest_close if technical else "",
                technical.trend_label if technical else "",
                technical.ret_1m if technical else "",
                technical.rsi14 if technical else "",
                _joined(evidence.missing_evidence),
            ]
        )
    lines.append(
        _md_table(
            ["Index", "Close", "Trend", "1M %", "RSI", "Missing"],
            index_rows or [["No index evidence", "", "", "", "", "index data missing"]],
        )
    )
    lines.append("")
    lines.append("## Sector Rotation")
    lines.append("")
    sector_rows = [
        [
            name,
            row.get("rotation_label"),
            row.get("stage2_count"),
            row.get("buy_signal_count"),
            row.get("avg_relative_strength"),
            ", ".join(row.get("top_symbols") or []),
        ]
        for name, row in sorted(pack.sectors.items())
    ]
    lines.append(
        _md_table(
            ["Sector", "Rotation", "Stage2", "Buy", "Avg RS", "Top Symbols"],
            sector_rows or [["No sector evidence", "", "", "", "", ""]],
        )
    )
    lines.append("")
    lines.append("## Stock Opportunity Map")
    lines.append("")
    rec_rows = [
        [
            rec.subject,
            rec.scope,
            rec.label,
            rec.confidence,
            rec.score,
            rec.why,
            rec.trigger,
            rec.invalidation,
            rec.risk,
            _joined(rec.conflicts),
            _joined(rec.missing_evidence),
        ]
        for rec in recommendations
    ]
    lines.append(
        _md_table(
            [
                "Subject",
                "Scope",
                "Label",
                "Confidence",
                "Score",
                "Why",
                "Trigger",
                "Invalidation",
                "Risk",
                "Conflicts",
                "Missing",
            ],
            rec_rows or [["No recommendations", "", "", "", "", "", "", "", "", "", ""]],
        )
    )
    lines.append("")
    lines.append("## Technical Detail Appendix")
    lines.append("")
    tech_rows = []
    for symbol, evidence in sorted(_combined_subjects(pack).items()):
        technical = evidence.technical
        tech_rows.append(
            [
                symbol,
                evidence.scope,
                technical.trend_label if technical else "",
                technical.ret_1w if technical else "",
                technical.ret_1m if technical else "",
                technical.ret_3m if technical else "",
                technical.rsi14 if technical else "",
                technical.macd_hist if technical else "",
                _joined(technical.conflicts if technical else []),
                _joined(technical.missing_evidence if technical else []),
            ]
        )
    lines.append(
        _md_table(
            ["Symbol", "Scope", "Trend", "1W %", "1M %", "3M %", "RSI", "MACD Hist", "Conflicts", "Missing"],
            tech_rows or [["No stock technicals", "", "", "", "", "", "", "", "", ""]],
        )
    )
    lines.append("")
    lines.append("## Fundamental Detail Appendix")
    lines.append("")
    fund_rows = [
        [
            symbol,
            evidence.scope,
            classify_fundamentals(evidence.fundamentals),
            _joined(_fundamental_evidence(evidence.fundamentals)),
            _joined(evidence.missing_evidence),
        ]
        for symbol, evidence in sorted(_combined_subjects(pack).items())
    ]
    lines.append(
        _md_table(
            ["Symbol", "Scope", "Quality", "Evidence", "Missing"],
            fund_rows or [["No fundamentals", "", "", "", "fundamentals missing"]],
        )
    )
    lines.append("")
    lines.append("## Grounding & Audit Trail")
    lines.append("")
    lines.append("### Source Trail")
    lines.append("")
    source_rows = [
        [
            name,
            row.get("source"),
            row.get("rows"),
            row.get("latest"),
            row.get("status"),
            ", ".join(row.get("missing_columns") or []),
        ]
        for name, row in sorted(pack.source_trail.items())
    ]
    lines.append(_md_table(["Source", "Label", "Rows", "Latest", "Status", "Missing Columns"], source_rows))
    lines.append("")
    lines.append("### Missing Evidence")
    lines.append("")
    if pack.missing_evidence:
        for scope, fields in sorted(pack.missing_evidence.items()):
            lines.append(f"- `{scope}`: {', '.join(fields)}")
    if not pack.missing_evidence and not subject_missing:
        lines.append("- none")
    for symbol, fields in subject_missing.items():
        lines.append(f"- `{symbol}`: {', '.join(fields)}")
    lines.append("")
    lines.append("### Conflicts")
    lines.append("")
    conflict_rows = [[rec.subject, rec.label, _joined(rec.conflicts)] for rec in recommendations if rec.conflicts]
    lines.append(_md_table(["Subject", "Label", "Conflicts"], conflict_rows or [["No conflicts", "", ""]]))
    return "\n".join(lines)


def _connect_pg():
    import psycopg2

    return psycopg2.connect(PG_DSN)


def _load_postgres_frame(sql: str) -> pd.DataFrame:
    conn = None
    try:
        from psycopg2.extras import RealDictCursor

        conn = _connect_pg()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql)
            rows = cur.fetchall()
        return pd.DataFrame(rows)
    except Exception:
        return pd.DataFrame()
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def _read_csv_frame(path: Path) -> pd.DataFrame:
    try:
        if path.exists():
            return pd.read_csv(path)
    except Exception:
        pass
    return pd.DataFrame()


def _has_history_columns(frame: pd.DataFrame) -> bool:
    if frame is None or frame.empty:
        return False
    columns = set(_normalize_columns(frame).columns)
    return "symbol" in columns and "close" in columns and bool({"trade_date", "timestamp", "date"} & columns)


def _has_usable_history_depth(frame: pd.DataFrame, minimum_dates: int = 60) -> bool:
    if not _has_history_columns(frame):
        return False

    df = _normalize_columns(frame)
    date_col = next((col for col in ("trade_date", "timestamp", "date") if col in df.columns), None)
    if date_col is None:
        return False

    dates = pd.to_datetime(df[date_col], errors="coerce")
    if dates.dropna().dt.normalize().nunique() >= minimum_dates:
        return True

    if "symbol" not in df.columns:
        return False
    depth = (
        df.assign(_history_date=dates.dt.normalize())
        .dropna(subset=["_history_date"])
        .groupby("symbol")["_history_date"]
        .nunique()
    )
    return bool(not depth.empty and int(depth.max()) >= minimum_dates)


def _normalize_index_history_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame()
    df = frame.copy()
    normalized_columns = _normalize_columns(df).columns
    rename_map = {
        original: normalized
        for original, normalized in zip(df.columns, normalized_columns, strict=False)
        if normalized == "index_symbol"
    }
    if rename_map and "symbol" not in set(normalized_columns):
        df = df.rename(columns={next(iter(rename_map)): "symbol"})
    return df


def load_recommendation_input_data(options: RecommendationReportOptions) -> RecommendationInputData:
    index_history = _load_postgres_frame(
        """
        SELECT index_symbol, trade_date, open, high, low, close, volume
        FROM market.index_eod
        ORDER BY trade_date
        """
    )
    if index_history.empty:
        index_history = _read_csv_frame(ROOT / "data" / "nse_index_data.csv")
    index_history = _normalize_index_history_frame(index_history)

    equity_history = _load_postgres_frame(
        """
        SELECT symbol, trade_date, open, high, low, close, volume
        FROM market.equity_eod
        ORDER BY symbol, trade_date
        """
    )
    if equity_history.empty:
        equity_history = _read_csv_frame(ROOT / "data" / "nse_sec_full_data.csv")
    if not _has_usable_history_depth(equity_history):
        universe_history = _read_csv_frame(ROOT / "data" / "nse_universe_stock_data.csv")
        equity_history = universe_history if _has_usable_history_depth(universe_history) else pd.DataFrame()

    snapshots = _load_postgres_frame("SELECT * FROM scores.mv_latest_snapshot")
    fundamentals = _load_postgres_frame("SELECT * FROM scores.fundamentals")
    if fundamentals.empty:
        fundamentals = _load_postgres_frame("SELECT * FROM scores.mv_latest_fundamentals")

    portfolio = pd.DataFrame()
    if options.include_portfolio:
        portfolio = _load_postgres_frame("SELECT * FROM portfolio.holdings")
        if portfolio.empty:
            portfolio = _read_csv_frame(ROOT / "data" / "holdings.csv")

    return RecommendationInputData(
        index_history=index_history,
        equity_history=equity_history,
        snapshots=snapshots,
        fundamentals=fundamentals,
        portfolio=portfolio,
        watchlist=list(options.watchlist),
    )


def persist_recommendation_run(
    pack: RecommendationEvidencePack,
    recommendations: list[GroundedRecommendation],
    report_path: str | Path,
    evidence_path: str | Path,
) -> dict[str, str]:
    conn = None
    try:
        from psycopg2.extras import Json

        conn = _connect_pg()
        with conn.cursor() as cur:
            cur.execute(SCHEMA_SQL)
            cur.execute(
                """
                INSERT INTO recommendation_reports.runs (
                    run_id,
                    generated_at,
                    as_of,
                    report_path,
                    evidence_path,
                    recommendation_count,
                    market_regime,
                    source_trail,
                    missing_evidence
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (run_id) DO UPDATE SET
                    generated_at = EXCLUDED.generated_at,
                    as_of = EXCLUDED.as_of,
                    report_path = EXCLUDED.report_path,
                    evidence_path = EXCLUDED.evidence_path,
                    recommendation_count = EXCLUDED.recommendation_count,
                    market_regime = EXCLUDED.market_regime,
                    source_trail = EXCLUDED.source_trail,
                    missing_evidence = EXCLUDED.missing_evidence
                """,
                (
                    pack.run_id,
                    pack.generated_at,
                    pack.as_of,
                    str(report_path),
                    str(evidence_path),
                    len(recommendations),
                    Json(_jsonable(pack.market_regime)),
                    Json(_jsonable(pack.source_trail)),
                    Json(_jsonable(pack.missing_evidence)),
                ),
            )
            cur.execute(
                "DELETE FROM recommendation_reports.recommendations WHERE run_id=%s",
                (pack.run_id,),
            )
            cur.execute(
                "DELETE FROM recommendation_reports.evidence WHERE run_id=%s",
                (pack.run_id,),
            )

            evidence_rows: list[tuple[str, str, Any]] = []
            evidence_rows.extend(("index", subject, evidence) for subject, evidence in pack.indices.items())
            evidence_rows.extend(("stock", subject, evidence) for subject, evidence in pack.stocks.items())
            evidence_rows.extend(("portfolio", subject, evidence) for subject, evidence in pack.portfolio.items())
            evidence_rows.extend(("sector", subject, evidence) for subject, evidence in pack.sectors.items())
            for scope, subject, evidence in evidence_rows:
                cur.execute(
                    """
                    INSERT INTO recommendation_reports.evidence (run_id, scope, subject, evidence)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (run_id, scope, subject) DO UPDATE SET
                        evidence = EXCLUDED.evidence
                    """,
                    (pack.run_id, scope, subject, Json(_jsonable(evidence))),
                )

            for rec in recommendations:
                cur.execute(
                    """
                    INSERT INTO recommendation_reports.recommendations (
                        run_id,
                        subject,
                        scope,
                        label,
                        confidence,
                        score,
                        payload
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (run_id, subject, scope) DO UPDATE SET
                        label = EXCLUDED.label,
                        confidence = EXCLUDED.confidence,
                        score = EXCLUDED.score,
                        payload = EXCLUDED.payload
                    """,
                    (
                        pack.run_id,
                        rec.subject,
                        rec.scope,
                        rec.label,
                        rec.confidence,
                        _jsonable(rec.score),
                        Json(_jsonable(rec)),
                    ),
                )

        conn.commit()
        return {"status": "postgres", "schema": "recommendation_reports", "run_id": pack.run_id}
    except Exception as exc:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass
        return {
            "status": "fallback_json",
            "run_id": pack.run_id,
            "evidence_path": str(evidence_path),
            "error": str(exc),
        }
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def save_evidence_json(
    pack: RecommendationEvidencePack,
    recommendations: list[GroundedRecommendation],
    *,
    output_dir: Path | None = None,
) -> Path:
    target_dir = output_dir or REPORT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"recommendation_evidence_{pack.run_id}.json"
    payload = {"pack": _jsonable(pack), "recommendations": _jsonable(recommendations)}
    path.write_text(json.dumps(payload, indent=2, allow_nan=False))
    return path


def _recommendation_report_warnings(
    pack: RecommendationEvidencePack,
    recommendations: list[GroundedRecommendation],
) -> list[str]:
    warnings: list[str] = []
    index_status = str(pack.source_trail.get("index_history", {}).get("status") or "")
    equity_status = str(pack.source_trail.get("equity_history", {}).get("status") or "")
    weak_statuses = {"missing", "degraded"}

    if index_status in weak_statuses and equity_status in weak_statuses:
        warnings.append(
            "critical_data_warning: index_history and equity_history are missing or degraded"
        )
    if not recommendations and (not pack.indices or not pack.stocks):
        warnings.append(
            "critical_data_warning: no recommendations produced because market or equity evidence is missing"
        )
    return warnings


def generate_recommendation_report(
    options: RecommendationReportOptions | None = None,
    input_data: RecommendationInputData | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    opts = options or RecommendationReportOptions()
    opts.output_format = _normalize_report_format(opts.output_format)
    data = input_data or load_recommendation_input_data(opts)
    pack = build_recommendation_evidence_pack(data, top_n=opts.top_n)
    recommendations = build_recommendations(pack)
    markdown = render_recommendation_markdown(pack, recommendations)
    title = "Grounded EOD Recommendation Report"
    warnings = _recommendation_report_warnings(pack, recommendations)

    from terminal.reports import generate_report

    report_result = generate_report(
        markdown,
        report_type="research",
        symbol="Market",
        output_format=opts.output_format,
        title=title,
        filename=f"grounded_recommendation_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{pack.run_id[:8]}",
    )
    evidence_path = save_evidence_json(pack, recommendations, output_dir=opts.output_dir)
    report_path = report_result.get("path", "")
    persistence = (
        persist_recommendation_run(pack, recommendations, report_path, evidence_path)
        if persist
        else {"status": "skipped", "reason": "persistence disabled"}
    )

    return {
        **report_result,
        "success": bool(report_result.get("success")),
        "path": report_path,
        "format": report_result.get("format", opts.output_format),
        "title": report_result.get("title", title),
        "evidence_path": str(evidence_path),
        "recommendation_count": len(recommendations),
        "run_id": pack.run_id,
        "persistence": persistence,
        "warnings": warnings,
    }


__all__ = [
    "GroundedRecommendation",
    "PG_DSN",
    "REPORT_DIR",
    "RecommendationEvidencePack",
    "RecommendationInputData",
    "RecommendationLabel",
    "RecommendationReportOptions",
    "ROOT",
    "SubjectEvidence",
    "TechnicalProfile",
    "build_recommendations",
    "build_technical_profile",
    "build_recommendation_evidence_pack",
    "classify_fundamentals",
    "generate_recommendation_report",
    "load_recommendation_input_data",
    "make_recommendation",
    "parse_recommendation_report_args",
    "pct_change_from_lookback",
    "persist_recommendation_run",
    "render_recommendation_markdown",
    "save_evidence_json",
]
