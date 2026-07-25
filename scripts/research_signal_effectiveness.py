#!/usr/bin/env python3
"""Research which technical setup works best per NSE stock using PostgreSQL EOD data.

This is an offline research layer, not a live signal generator.  It reads
`market.equity_eod` and `scores.stage_snapshots`, generates deterministic setup
events, labels their forward outcomes, and optionally trains a time-split ML
classifier to estimate setup quality.
"""

from __future__ import annotations

import argparse
import html
import math
import os
import sys
import warnings
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terminal.strategy_modules import (
    STRATEGY_MODULES,
    aggregate_module_summary,
    attach_modules_to_events,
    build_module_candidates,
)


REPORT_DIR = ROOT / "reports" / "signal_effectiveness"
MODULE_REPORT_DIR = ROOT / "reports" / "strategy_modules"
LATEST_DIR = ROOT / "reports" / "latest"
DEFAULT_DSN = os.environ.get("AGENT_ADDA_PG_DSN") or os.environ.get("PG_DSN") or "dbname=nse_market user=nse_admin host=/tmp"
warnings.filterwarnings("ignore", message="pandas only supports SQLAlchemy.*", category=UserWarning)

DELIVERY_STATUTORY_COST_PCT = 0.23
EXECUTION_COST_PCT_BY_PROFILE = {
    "liquid": 0.38,
    "mid": 0.63,
    "illiquid_spike": 1.10,
}


@dataclass(frozen=True)
class ModelResult:
    enabled: bool
    train_rows: int = 0
    test_rows: int = 0
    accuracy: float | None = None
    roc_auc: float | None = None
    reason: str = ""


def _load_dotenv() -> None:
    for envfile in (ROOT / ".env", ROOT / ".env.local"):
        if not envfile.exists():
            continue
        for line in envfile.read_text(encoding="utf-8", errors="ignore").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _dsn() -> str:
    _load_dotenv()
    return os.environ.get("AGENT_ADDA_PG_DSN") or os.environ.get("PG_DSN") or DEFAULT_DSN


def _connect(dsn: str):
    import psycopg2

    return psycopg2.connect(dsn)


def _parse_symbols(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [part.strip().upper() for part in raw.replace("\n", ",").split(",") if part.strip()]


def _latest_trade_date(conn: Any, end: str | None) -> str:
    if end:
        return str(pd.to_datetime(end).date())
    row = pd.read_sql_query(
        "SELECT max(trade_date)::text AS trade_date FROM market.equity_eod WHERE series='EQ'",
        conn,
    ).iloc[0]
    return str(row["trade_date"])


def _select_symbols(
    conn: Any,
    *,
    symbols: list[str],
    latest_date: str,
    top_n: int,
    min_price: float,
    min_turnover_cr: float,
) -> list[str]:
    if symbols:
        rows = pd.read_sql_query(
            """
            SELECT DISTINCT upper(symbol) AS symbol
            FROM market.equity_eod
            WHERE series='EQ' AND upper(symbol) = ANY(%s)
            ORDER BY symbol
            """,
            conn,
            params=[symbols],
        )
        return rows["symbol"].astype(str).str.upper().tolist()

    rows = pd.read_sql_query(
        """
        SELECT upper(symbol) AS symbol
        FROM market.equity_eod
        WHERE trade_date = %s
          AND series = 'EQ'
          AND close >= %s
          AND coalesce(turnover_cr, 0) >= %s
          AND volume > 0
        ORDER BY turnover_cr DESC NULLS LAST, volume DESC NULLS LAST
        LIMIT %s
        """,
        conn,
        params=[latest_date, min_price, min_turnover_cr, int(top_n)],
    )
    return rows["symbol"].astype(str).str.upper().tolist()


def load_pg_data(
    *,
    dsn: str,
    symbols: list[str],
    start: str,
    lookback: str,
    end: str | None,
    top_n: int,
    min_price: float,
    min_turnover_cr: float,
) -> tuple[pd.DataFrame, str, list[str]]:
    with _connect(dsn) as conn:
        latest_date = _latest_trade_date(conn, end)
        selected = _select_symbols(
            conn,
            symbols=symbols,
            latest_date=latest_date,
            top_n=top_n,
            min_price=min_price,
            min_turnover_cr=min_turnover_cr,
        )
        if not selected:
            return pd.DataFrame(), latest_date, []
        market_regime = _load_market_regime(conn, lookback=lookback, end=end)
        fno_context = _load_fno_context(conn, lookback=lookback, end=end, symbols=selected)
        end_clause = "AND trade_date <= %(end)s" if end else ""
        eod = pd.read_sql_query(
            f"""
            SELECT
                trade_date AS date,
                upper(symbol) AS symbol,
                open,
                high,
                low,
                close,
                volume,
                turnover_cr,
                delivery_pct
            FROM market.equity_eod
            WHERE series='EQ'
              AND trade_date >= %(lookback)s
              AND upper(symbol) = ANY(%(symbols)s)
              AND open > 0 AND high > 0 AND low > 0 AND close > 0 AND volume > 0
              {end_clause}
            ORDER BY symbol, trade_date
            """,
            conn,
            params={"lookback": lookback, "end": end, "symbols": selected},
        )
        stage = pd.read_sql_query(
            f"""
            SELECT
                snapshot_date AS date,
                upper(symbol) AS symbol,
                sector,
                stage,
                technical_score,
                investment_score,
                rsi AS snapshot_rsi,
                trend_signal,
                trading_signal,
                relative_strength,
                supertrend_state,
                supertrend_value
            FROM scores.stage_snapshots
            WHERE snapshot_date >= %(lookback)s
              AND upper(symbol) = ANY(%(symbols)s)
              {"AND snapshot_date <= %(end)s" if end else ""}
            """,
            conn,
            params={"lookback": lookback, "end": end, "symbols": selected},
        )
    if eod.empty:
        return pd.DataFrame(), latest_date, selected
    data = normalize_and_merge(eod, stage)
    data = merge_market_regime(data, market_regime)
    data = merge_fno_context(data, fno_context)
    data = data[pd.to_datetime(data["date"]) >= pd.to_datetime(lookback)].copy()
    return data, latest_date, selected


def _load_market_regime(conn: Any, *, lookback: str, end: str | None) -> pd.DataFrame:
    end_clause = "AND trade_date <= %(end)s" if end else ""
    rows = pd.read_sql_query(
        f"""
        SELECT trade_date AS date, index_symbol, close, change_pct
        FROM market.index_eod
        WHERE lower(index_symbol) IN ('nifty 50', 'nifty bank', 'india vix')
          AND trade_date >= %(lookback)s
          {end_clause}
        ORDER BY index_symbol, trade_date
        """,
        conn,
        params={"lookback": lookback, "end": end},
    )
    if rows.empty:
        return rows
    rows["date"] = pd.to_datetime(rows["date"])
    rows["index_key"] = rows["index_symbol"].astype(str).str.upper().str.replace(" ", "_", regex=False)
    rows["close"] = pd.to_numeric(rows["close"], errors="coerce")
    rows["change_pct"] = pd.to_numeric(rows["change_pct"], errors="coerce")
    grouped = rows.groupby("index_key", group_keys=False)
    rows["index_ema20"] = grouped["close"].transform(lambda s: s.ewm(span=20, adjust=False, min_periods=20).mean())
    rows["index_ema50"] = grouped["close"].transform(lambda s: s.ewm(span=50, adjust=False, min_periods=50).mean())
    rows["index_return_5d"] = grouped["close"].pct_change(5).mul(100)
    rows["above_ema20"] = (rows["close"] > rows["index_ema20"]).astype(float)
    rows["above_ema50"] = (rows["close"] > rows["index_ema50"]).astype(float)
    pieces = []
    for key, prefix in [("NIFTY_50", "nifty"), ("NIFTY_BANK", "banknifty"), ("INDIA_VIX", "vix")]:
        part = rows.loc[rows["index_key"] == key, ["date", "close", "change_pct", "index_return_5d", "above_ema20", "above_ema50"]].copy()
        if part.empty:
            continue
        part = part.rename(
            columns={
                "close": f"{prefix}_close",
                "change_pct": f"{prefix}_change_pct",
                "index_return_5d": f"{prefix}_return_5d",
                "above_ema20": f"{prefix}_above_ema20",
                "above_ema50": f"{prefix}_above_ema50",
            }
        )
        pieces.append(part)
    if not pieces:
        return pd.DataFrame()
    out = pieces[0]
    for part in pieces[1:]:
        out = out.merge(part, on="date", how="outer")
    out = out.sort_values("date").reset_index(drop=True)
    out["market_regime"] = out.apply(_market_regime_label, axis=1)
    return out


def _market_regime_label(row: pd.Series) -> str:
    nifty_change = _num(row.get("nifty_change_pct"))
    nifty_above20 = _num(row.get("nifty_above_ema20"))
    bank_above20 = _num(row.get("banknifty_above_ema20"))
    vix_close = _num(row.get("vix_close"))
    vix_change = _num(row.get("vix_change_pct"))
    if vix_close >= 18 or vix_change >= 5 or (nifty_above20 == 0 and nifty_change <= -0.7):
        return "risk_off"
    if nifty_above20 == 1 and bank_above20 == 1 and (not math.isfinite(vix_change) or vix_change <= 2):
        return "expansion"
    return "confirmation"


def _load_fno_context(conn: Any, *, lookback: str, end: str | None, symbols: list[str]) -> pd.DataFrame:
    end_clause_eod = "AND trade_date <= %(end)s" if end else ""
    end_clause_sig = "AND snapshot_date <= %(end)s" if end else ""
    fno_eod = pd.read_sql_query(
        f"""
        WITH fut AS (
            SELECT
                trade_date AS date,
                upper(symbol) AS symbol,
                sum(coalesce(oi_change, 0)) AS futures_oi_change,
                sum(coalesce(open_interest, 0)) AS futures_open_interest,
                sum(coalesce(volume, 0)) AS futures_volume,
                avg((coalesce(last_price, close) - underlying_price) / nullif(underlying_price, 0) * 100.0) AS futures_basis_pct
            FROM derivatives.fno_eod
            WHERE trade_date >= %(lookback)s
              AND upper(symbol) = ANY(%(symbols)s)
              AND option_type = 'FUT'
              {end_clause_eod}
            GROUP BY trade_date, upper(symbol)
        ),
        opt AS (
            SELECT
                trade_date AS date,
                upper(symbol) AS symbol,
                sum(CASE WHEN option_type='CE' THEN coalesce(open_interest, 0) ELSE 0 END) AS call_oi,
                sum(CASE WHEN option_type='PE' THEN coalesce(open_interest, 0) ELSE 0 END) AS put_oi,
                sum(CASE WHEN option_type='CE' THEN coalesce(volume, 0) ELSE 0 END) AS call_volume,
                sum(CASE WHEN option_type='PE' THEN coalesce(volume, 0) ELSE 0 END) AS put_volume
            FROM derivatives.fno_eod
            WHERE trade_date >= %(lookback)s
              AND upper(symbol) = ANY(%(symbols)s)
              AND option_type IN ('CE', 'PE')
              {end_clause_eod}
            GROUP BY trade_date, upper(symbol)
        )
        SELECT
            coalesce(fut.date, opt.date) AS date,
            coalesce(fut.symbol, opt.symbol) AS symbol,
            futures_oi_change,
            futures_open_interest,
            futures_volume,
            futures_basis_pct,
            call_oi,
            put_oi,
            call_volume,
            put_volume,
            put_oi / nullif(call_oi, 0)::numeric AS fno_pcr
        FROM fut
        FULL OUTER JOIN opt ON fut.date = opt.date AND fut.symbol = opt.symbol
        """,
        conn,
        params={"lookback": lookback, "end": end, "symbols": symbols},
    )
    fno_signals = pd.read_sql_query(
        f"""
        SELECT
            snapshot_date AS date,
            upper(symbol) AS symbol,
            pcr AS signal_pcr,
            oi_change_5d AS signal_oi_change_5d,
            price_change AS signal_price_change,
            buildup AS signal_buildup,
            max_pain,
            fno_signal
        FROM derivatives.fno_signals
        WHERE snapshot_date >= %(lookback)s
          AND upper(symbol) = ANY(%(symbols)s)
          {end_clause_sig}
        """,
        conn,
        params={"lookback": lookback, "end": end, "symbols": symbols},
    )
    if fno_eod.empty and fno_signals.empty:
        return pd.DataFrame()
    for frame in (fno_eod, fno_signals):
        if not frame.empty:
            frame["date"] = pd.to_datetime(frame["date"])
            frame["symbol"] = frame["symbol"].astype(str).str.upper().str.strip()
    if fno_eod.empty:
        return fno_signals
    if fno_signals.empty:
        return fno_eod
    return fno_eod.merge(fno_signals, on=["date", "symbol"], how="outer")


def merge_market_regime(data: pd.DataFrame, market_regime: pd.DataFrame) -> pd.DataFrame:
    out = data.copy()
    if market_regime.empty:
        out["market_regime"] = "unknown"
        return out
    return out.merge(market_regime, on="date", how="left")


def merge_fno_context(data: pd.DataFrame, fno_context: pd.DataFrame) -> pd.DataFrame:
    out = data.copy()
    if fno_context.empty:
        out["fno_available"] = 0
        return out
    out = out.merge(fno_context, on=["date", "symbol"], how="left")
    out["fno_available"] = out[["futures_oi_change", "fno_pcr", "signal_pcr"]].notna().any(axis=1).astype(int)
    return out


def normalize_and_merge(eod: pd.DataFrame, stage: pd.DataFrame) -> pd.DataFrame:
    eod = eod.copy()
    eod["date"] = pd.to_datetime(eod["date"])
    eod["symbol"] = eod["symbol"].astype(str).str.upper().str.strip()
    for column in ["open", "high", "low", "close", "volume", "turnover_cr", "delivery_pct"]:
        if column not in eod.columns:
            eod[column] = np.nan
        eod[column] = pd.to_numeric(eod[column], errors="coerce")
    eod = eod.dropna(subset=["date", "symbol", "open", "high", "low", "close", "volume"])
    eod = eod.sort_values(["symbol", "date"]).drop_duplicates(["date", "symbol"], keep="last")

    if not stage.empty:
        stage = stage.copy()
        stage["date"] = pd.to_datetime(stage["date"])
        stage["symbol"] = stage["symbol"].astype(str).str.upper().str.strip()
        for column in ["technical_score", "investment_score", "snapshot_rsi", "relative_strength", "supertrend_value"]:
            stage[column] = pd.to_numeric(stage.get(column), errors="coerce")
        for column in ["sector", "stage", "trend_signal", "trading_signal", "supertrend_state"]:
            stage[column] = stage.get(column, "").fillna("").astype(str).str.upper().str.strip()
        sector_map = (
            stage.loc[stage["sector"].ne(""), ["symbol", "date", "sector"]]
            .sort_values(["symbol", "date"])
            .drop_duplicates("symbol", keep="last")
            .set_index("symbol")["sector"]
            .to_dict()
        )
        stage = stage.drop_duplicates(["date", "symbol"], keep="last")
        eod = eod.merge(stage, on=["date", "symbol"], how="left")
        eod["sector"] = eod["sector"].replace("", np.nan).fillna(eod["symbol"].map(sector_map)).fillna("")
    else:
        for column in [
            "sector",
            "stage",
            "technical_score",
            "investment_score",
            "snapshot_rsi",
            "trend_signal",
            "trading_signal",
            "relative_strength",
            "supertrend_state",
            "supertrend_value",
        ]:
            eod[column] = np.nan
    return eod.sort_values(["symbol", "date"]).reset_index(drop=True)


def add_indicators(data: pd.DataFrame) -> pd.DataFrame:
    out = data.sort_values(["symbol", "date"]).copy()
    grouped = out.groupby("symbol", group_keys=False)
    out["daily_return_pct"] = grouped["close"].pct_change().mul(100)
    for span in (10, 20, 50, 100, 200):
        out[f"ema_{span}"] = grouped["close"].transform(lambda s, span=span: s.ewm(span=span, adjust=False, min_periods=span).mean())
        out[f"sma_{span}"] = grouped["close"].transform(lambda s, span=span: s.rolling(span, min_periods=span).mean())

    prev_close = grouped["close"].shift(1)
    tr = pd.concat(
        [
            out["high"] - out["low"],
            (out["high"] - prev_close).abs(),
            (out["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    out["atr_14"] = tr.groupby(out["symbol"]).transform(lambda s: s.rolling(14, min_periods=14).mean())
    out["adr_pct_20"] = ((out["high"] - out["low"]) / out["close"]).groupby(out["symbol"]).transform(
        lambda s: s.rolling(20, min_periods=20).mean()
    ) * 100.0
    volume_ma = grouped["volume"].transform(lambda s: s.rolling(20, min_periods=20).mean())
    out["volume_ratio_20d"] = out["volume"] / volume_ma.replace(0, np.nan)
    out["turnover_cr_20d"] = grouped["turnover_cr"].transform(lambda s: s.rolling(20, min_periods=10).mean())
    out["return_63d"] = grouped["close"].pct_change(63)
    out["rs_rank_63d"] = out.groupby("date")["return_63d"].rank(pct=True).mul(100)
    out["relative_strength"] = pd.to_numeric(out["relative_strength"], errors="coerce").fillna(out["rs_rank_63d"]).fillna(50)
    out["breadth_positive_pct"] = out.groupby("date")["daily_return_pct"].transform(lambda s: float((s > 0).mean() * 100.0))
    out["sector_return_1d_pct"] = out.groupby(["date", "sector"], dropna=False)["daily_return_pct"].transform("mean")
    out["sector_rank_1d"] = out.groupby("date")["sector_return_1d_pct"].rank(pct=True).mul(100)

    out["rsi_14_calc"] = _rsi(out)
    out["rsi_14"] = pd.to_numeric(out["snapshot_rsi"], errors="coerce").fillna(out["rsi_14_calc"]).fillna(50)
    for window in (10, 20, 50):
        out[f"prev_high_{window}"] = grouped["high"].transform(lambda s, window=window: s.shift(1).rolling(window, min_periods=window).max())
        out[f"prev_low_{window}"] = grouped["low"].transform(lambda s, window=window: s.shift(1).rolling(window, min_periods=window).min())
    out["range_5_pct"] = _rolling_range_pct(out, 5)
    out["range_20_pct"] = _rolling_range_pct(out, 20)
    out["range_50_pct"] = _rolling_range_pct(out, 50)
    out["vcp_contraction"] = (
        (out["range_5_pct"] < out["range_20_pct"] * 0.70)
        & (out["range_20_pct"] < out["range_50_pct"] * 0.85)
    )
    out["box_high_20"] = out["prev_high_20"]
    out["box_low_20"] = out["prev_low_20"]
    out["box_width_pct_20"] = (out["box_high_20"] - out["box_low_20"]) / out["close"] * 100.0
    out["trend_stack"] = (out["close"] > out["ema_20"]) & (out["ema_20"] > out["ema_50"]) & (out["ema_50"] > out["ema_100"])
    out["supertrend_bullish"] = out["supertrend_state"].fillna("").astype(str).str.upper().isin({"BUY", "BULLISH", "GREEN"})
    for column in ["signal_pcr", "fno_pcr", "signal_oi_change_5d", "futures_oi_change", "signal_buildup"]:
        if column not in out.columns:
            out[column] = np.nan
    out["fno_pcr_final"] = pd.to_numeric(out["signal_pcr"], errors="coerce").fillna(pd.to_numeric(out["fno_pcr"], errors="coerce"))
    out["fno_oi_change_final"] = pd.to_numeric(out.get("signal_oi_change_5d"), errors="coerce").fillna(
        pd.to_numeric(out.get("futures_oi_change"), errors="coerce")
    )
    out["fno_buildup_final"] = out["signal_buildup"].fillna("").astype(str).str.upper().str.strip()
    missing_buildup = out["fno_buildup_final"].eq("") | out["fno_buildup_final"].eq("NAN")
    out.loc[missing_buildup, "fno_buildup_final"] = np.select(
        [
            (out.loc[missing_buildup, "daily_return_pct"] > 0) & (out.loc[missing_buildup, "fno_oi_change_final"] > 0),
            (out.loc[missing_buildup, "daily_return_pct"] < 0) & (out.loc[missing_buildup, "fno_oi_change_final"] > 0),
            (out.loc[missing_buildup, "daily_return_pct"] > 0) & (out.loc[missing_buildup, "fno_oi_change_final"] < 0),
            (out.loc[missing_buildup, "daily_return_pct"] < 0) & (out.loc[missing_buildup, "fno_oi_change_final"] < 0),
        ],
        ["LONG_BUILDUP", "SHORT_BUILDUP", "SHORT_COVERING", "LONG_UNWINDING"],
        default="UNKNOWN",
    )
    out["fno_bias_score"] = out["fno_buildup_final"].map(
        {
            "LONG_BUILDUP": 1.0,
            "SHORT_COVERING": 0.5,
            "NEUTRAL": 0.0,
            "UNKNOWN": 0.0,
            "LONG_UNWINDING": -0.5,
            "SHORT_BUILDUP": -1.0,
        }
    ).fillna(0.0)
    out.loc[out["fno_pcr_final"] >= 1.1, "fno_bias_score"] += 0.25
    out.loc[out["fno_pcr_final"] <= 0.7, "fno_bias_score"] -= 0.25
    return out


def _rsi(data: pd.DataFrame) -> pd.Series:
    delta = data.groupby("symbol")["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.groupby(data["symbol"]).transform(lambda s: s.rolling(14, min_periods=14).mean())
    avg_loss = loss.groupby(data["symbol"]).transform(lambda s: s.rolling(14, min_periods=14).mean())
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return (100 - (100 / (1 + rs))).clip(0, 100)


def _rolling_range_pct(data: pd.DataFrame, window: int) -> pd.Series:
    grouped = data.groupby("symbol", group_keys=False)
    high = grouped["high"].transform(lambda s, window=window: s.rolling(window, min_periods=window).max())
    low = grouped["low"].transform(lambda s, window=window: s.rolling(window, min_periods=window).min())
    close = data["close"].replace(0, np.nan)
    return (high - low) / close * 100.0


def generate_signal_events(
    data: pd.DataFrame,
    *,
    start: str,
    min_volume_ratio: float,
    max_darvas_width_pct: float,
    min_adr_pct: float,
    min_turnover_cr: float,
) -> pd.DataFrame:
    events: list[dict[str, Any]] = []
    filtered = data[pd.to_datetime(data["date"]) >= pd.to_datetime(start)].copy()
    for row in filtered.itertuples(index=False):
        flags = _signal_flags(row, min_volume_ratio=min_volume_ratio, max_darvas_width_pct=max_darvas_width_pct)
        if not flags:
            continue
        combo_flags = _combo_signal_flags(row, flags)
        adr = _num(getattr(row, "adr_pct_20", np.nan))
        turnover = _num(getattr(row, "turnover_cr_20d", np.nan))
        if adr < min_adr_pct or turnover < min_turnover_cr:
            continue
        base = {
            "date": getattr(row, "date"),
            "symbol": getattr(row, "symbol"),
            "sector": getattr(row, "sector", "") or "",
            "close": _num(getattr(row, "close")),
            "high": _num(getattr(row, "high")),
            "low": _num(getattr(row, "low")),
            "volume": _num(getattr(row, "volume")),
            "turnover_cr_20d": turnover,
            "stage": getattr(row, "stage", "") or "",
            "market_regime": getattr(row, "market_regime", "") or "",
            "trading_signal": getattr(row, "trading_signal", "") or "",
            "trend_signal": getattr(row, "trend_signal", "") or "",
            "supertrend_state": getattr(row, "supertrend_state", "") or "",
            "technical_score": _num(getattr(row, "technical_score", np.nan)),
            "investment_score": _num(getattr(row, "investment_score", np.nan)),
            "relative_strength": _num(getattr(row, "relative_strength", np.nan)),
            "rsi_14": _num(getattr(row, "rsi_14", np.nan)),
            "atr_14": _num(getattr(row, "atr_14", np.nan)),
            "adr_pct_20": adr,
            "volume_ratio_20d": _num(getattr(row, "volume_ratio_20d", np.nan)),
            "box_width_pct_20": _num(getattr(row, "box_width_pct_20", np.nan)),
            "range_5_pct": _num(getattr(row, "range_5_pct", np.nan)),
            "range_20_pct": _num(getattr(row, "range_20_pct", np.nan)),
            "return_63d": _num(getattr(row, "return_63d", np.nan)),
            "daily_return_pct": _num(getattr(row, "daily_return_pct", np.nan)),
            "breadth_positive_pct": _num(getattr(row, "breadth_positive_pct", np.nan)),
            "sector_return_1d_pct": _num(getattr(row, "sector_return_1d_pct", np.nan)),
            "sector_rank_1d": _num(getattr(row, "sector_rank_1d", np.nan)),
            "nifty_change_pct": _num(getattr(row, "nifty_change_pct", np.nan)),
            "nifty_above_ema20": _num(getattr(row, "nifty_above_ema20", np.nan)),
            "banknifty_change_pct": _num(getattr(row, "banknifty_change_pct", np.nan)),
            "vix_close": _num(getattr(row, "vix_close", np.nan)),
            "vix_change_pct": _num(getattr(row, "vix_change_pct", np.nan)),
            "fno_available": _num(getattr(row, "fno_available", 0)),
            "fno_pcr": _num(getattr(row, "fno_pcr_final", np.nan)),
            "fno_oi_change": _num(getattr(row, "fno_oi_change_final", np.nan)),
            "fno_buildup": getattr(row, "fno_buildup_final", "") or "",
            "fno_bias_score": _num(getattr(row, "fno_bias_score", np.nan)),
            "futures_basis_pct": _num(getattr(row, "futures_basis_pct", np.nan)),
            "max_pain": _num(getattr(row, "max_pain", np.nan)),
            "ema20_distance_pct": (_num(getattr(row, "close")) / _num(getattr(row, "ema_20", np.nan)) - 1.0) * 100.0,
            "ema50_distance_pct": (_num(getattr(row, "close")) / _num(getattr(row, "ema_50", np.nan)) - 1.0) * 100.0,
            "prev_high_20": _num(getattr(row, "prev_high_20", np.nan)),
            "prev_high_50": _num(getattr(row, "prev_high_50", np.nan)),
            "prev_low_10": _num(getattr(row, "prev_low_10", np.nan)),
        }
        for setup_name, reason in flags:
            entry = dict(base)
            entry["setup"] = setup_name
            entry["setup_type"] = "standalone"
            entry["setup_reason"] = reason
            events.append(entry)
        for setup_name, reason in combo_flags:
            entry = dict(base)
            entry["setup"] = setup_name
            entry["setup_type"] = "combo"
            entry["setup_reason"] = reason
            events.append(entry)
    out = pd.DataFrame(events)
    if not out.empty:
        out["date"] = pd.to_datetime(out["date"])
        out = out.sort_values(["date", "symbol", "setup"]).reset_index(drop=True)
    return out


def _signal_flags(row: Any, *, min_volume_ratio: float, max_darvas_width_pct: float) -> list[tuple[str, str]]:
    close = _num(getattr(row, "close", np.nan))
    volume_ratio = _num(getattr(row, "volume_ratio_20d", np.nan))
    rsi = _num(getattr(row, "rsi_14", np.nan))
    if close <= 0 or volume_ratio < min_volume_ratio:
        return []

    flags: list[tuple[str, str]] = []
    trend_stack = bool(getattr(row, "trend_stack", False))
    supertrend = bool(getattr(row, "supertrend_bullish", False))
    stage = str(getattr(row, "stage", "") or "").upper()
    rs = _num(getattr(row, "relative_strength", np.nan))
    prev_high_10 = _num(getattr(row, "prev_high_10", np.nan))
    prev_high_20 = _num(getattr(row, "prev_high_20", np.nan))
    prev_high_50 = _num(getattr(row, "prev_high_50", np.nan))
    box_width = _num(getattr(row, "box_width_pct_20", np.nan))
    low = _num(getattr(row, "low", np.nan))
    ema20 = _num(getattr(row, "ema_20", np.nan))
    ema50 = _num(getattr(row, "ema_50", np.nan))

    if close > prev_high_20 and close > ema20:
        flags.append(("breakout_20_volume", "Close cleared prior 20-day high with required volume."))
    if close > prev_high_50 and close > ema50:
        flags.append(("breakout_50_volume", "Close cleared prior 50-day high with required volume."))
    if close > prev_high_20 and 0 < box_width <= max_darvas_width_pct:
        flags.append(("darvas_box_breakout", "Breakout from a compact 20-day box with required volume."))
    if bool(getattr(row, "vcp_contraction", False)) and close > prev_high_20:
        flags.append(("vcp_breakout_proxy", "Range contraction followed by 20-day breakout with required volume."))
    if stage == "STAGE_2" and trend_stack and supertrend and rs >= 55:
        flags.append(("stage2_supertrend_volume", "Stage 2, bullish Supertrend, trend stack, and volume confirmation."))
    if supertrend and close > prev_high_10 and trend_stack:
        flags.append(("supertrend_10d_breakout", "Bullish Supertrend plus 10-day breakout and trend stack."))
    if trend_stack and low <= ema20 <= close and 50 <= rsi <= 70:
        flags.append(("ema20_pullback_reclaim", "Trend stack with same-day EMA20 support reclaim and controlled RSI."))
    if rs >= 70 and close > prev_high_20:
        flags.append(("relative_strength_breakout", "High relative strength plus 20-day breakout with required volume."))
    return flags


def _combo_signal_flags(row: Any, base_flags: list[tuple[str, str]]) -> list[tuple[str, str]]:
    base_setups = {name for name, _reason in base_flags}
    close = _num(getattr(row, "close", np.nan))
    volume_ratio = _num(getattr(row, "volume_ratio_20d", np.nan))
    adr = _num(getattr(row, "adr_pct_20", np.nan))
    rs = _num(getattr(row, "relative_strength", np.nan))
    sector_rank = _num(getattr(row, "sector_rank_1d", np.nan))
    breadth = _num(getattr(row, "breadth_positive_pct", np.nan))
    vix_change = _num(getattr(row, "vix_change_pct", np.nan))
    fno_bias = _num(getattr(row, "fno_bias_score", np.nan))
    fno_available = _num(getattr(row, "fno_available", 0))
    market_regime = str(getattr(row, "market_regime", "") or "").lower()
    stage = str(getattr(row, "stage", "") or "").upper()
    trend_stack = bool(getattr(row, "trend_stack", False))
    supertrend = bool(getattr(row, "supertrend_bullish", False))
    breakout_present = bool(base_setups & {"breakout_20_volume", "breakout_50_volume", "relative_strength_breakout"})
    flags: list[tuple[str, str]] = []

    if "relative_strength_breakout" in base_setups and volume_ratio >= 2.0 and sector_rank >= 60:
        flags.append(
            (
                "combo_rs_volume_sector",
                "Relative-strength breakout with 2x volume and sector participation in the top 40%.",
            )
        )
    if "breakout_20_volume" in base_setups and stage == "STAGE_2" and supertrend and trend_stack:
        flags.append(
            (
                "combo_stage2_supertrend_breakout",
                "20-day breakout aligned with Stage 2, bullish Supertrend, and EMA trend stack.",
            )
        )
    if "vcp_breakout_proxy" in base_setups and volume_ratio >= 1.5 and adr >= 3.0 and sector_rank >= 60:
        flags.append(
            (
                "combo_vcp_volume_sector",
                "VCP proxy breakout with elevated volume, ADR expansion, and sector confirmation.",
            )
        )
    if breakout_present and fno_available == 1 and fno_bias > 0:
        flags.append(
            (
                "combo_fno_confirmed_breakout",
                "Breakout with positive F&O bias from buildup/PCR/futures context.",
            )
        )
    if breakout_present and market_regime != "risk_off" and breadth >= 50 and (not math.isfinite(vix_change) or vix_change < 4):
        flags.append(
            (
                "combo_risk_filtered_breakout",
                "Breakout allowed only when tape is not risk-off, breadth is positive, and VIX is not spiking.",
            )
        )
    if "ema20_pullback_reclaim" in base_setups and market_regime in {"expansion", "confirmation"} and breadth >= 50:
        flags.append(
            (
                "combo_ema_reclaim_regime",
                "EMA20 reclaim in an acceptable market regime with positive breadth.",
            )
        )
    if breakout_present and rs >= 70 and volume_ratio >= 1.5 and adr >= 3.0 and close > 0:
        flags.append(
            (
                "combo_momentum_quality",
                "Breakout with high relative strength, volume expansion, and enough ADR to travel.",
            )
        )
    return flags


def label_outcomes(
    events: pd.DataFrame,
    data: pd.DataFrame,
    *,
    horizon_days: int,
    stop_atr: float,
    target_r: float,
    include_open_outcomes: bool,
) -> pd.DataFrame:
    if events.empty:
        return events
    by_symbol = {sym: frame.reset_index(drop=True) for sym, frame in data.groupby("symbol", sort=False)}
    labelled: list[dict[str, Any]] = []
    for event in events.to_dict(orient="records"):
        symbol = str(event["symbol"])
        frame = by_symbol.get(symbol)
        if frame is None or frame.empty:
            continue
        date = pd.to_datetime(event["date"])
        matches = frame.index[frame["date"] == date].tolist()
        if not matches:
            continue
        idx = int(matches[-1])
        entry_variant = str(event.get("entry_variant") or "close_breakout")
        entry_idx = idx
        entry = float(event["close"])
        if entry_variant == "next_day_confirmation":
            if idx + 1 >= len(frame):
                continue
            confirm = frame.iloc[idx + 1]
            if float(confirm["high"]) <= float(event["high"]) or float(confirm["close"]) <= float(event["close"]):
                continue
            entry_idx = idx + 1
            entry = float(confirm["close"])
        elif entry_variant == "breakout_retest_hold":
            pivot = float(event.get("prev_high_20") or event.get("prev_high_50") or np.nan)
            if not math.isfinite(pivot) or pivot <= 0:
                continue
            retest = frame.iloc[idx + 1 : idx + 6]
            found_idx: int | None = None
            for candidate_idx, candidate in retest.iterrows():
                if float(candidate["low"]) <= pivot * 1.005 and float(candidate["close"]) >= pivot:
                    found_idx = int(candidate_idx)
                    break
            if found_idx is None:
                continue
            entry_idx = found_idx
            entry = float(frame.iloc[entry_idx]["close"])
        future = frame.iloc[entry_idx + 1 : entry_idx + 1 + horizon_days]
        if future.empty:
            continue
        if len(future) < horizon_days and not include_open_outcomes:
            continue
        atr = float(event.get("atr_14") or 0.0)
        prev_low = float(event.get("prev_low_10") or np.nan)
        stop_candidates = [entry - atr * stop_atr] if atr > 0 else []
        if math.isfinite(prev_low) and prev_low > 0 and prev_low < entry:
            stop_candidates.append(prev_low)
        stop = max(stop_candidates) if stop_candidates else entry * 0.97
        min_risk = max(entry * 0.005, atr * 0.50 if atr > 0 else 0.0)
        if entry - stop < min_risk:
            stop = entry - min_risk
        risk = entry - stop
        if risk <= 0:
            continue
        target = entry + risk * target_r
        outcome = "timeout"
        exit_price = float(future.iloc[-1]["close"])
        exit_date = pd.to_datetime(future.iloc[-1]["date"])
        bars_held = int(len(future))
        mfe_r = (float(future["high"].max()) - entry) / risk
        mae_r = (float(future["low"].min()) - entry) / risk
        for offset, row in enumerate(future.itertuples(index=False), start=1):
            low = float(getattr(row, "low"))
            high = float(getattr(row, "high"))
            if low <= stop and high >= target:
                outcome = "loss"
                exit_price = stop
                exit_date = pd.to_datetime(getattr(row, "date"))
                bars_held = offset
                break
            if low <= stop:
                outcome = "loss"
                exit_price = stop
                exit_date = pd.to_datetime(getattr(row, "date"))
                bars_held = offset
                break
            if high >= target:
                outcome = "target"
                exit_price = target
                exit_date = pd.to_datetime(getattr(row, "date"))
                bars_held = offset
                break
        realized_r = (exit_price - entry) / risk
        labelled_event = dict(event)
        labelled_event.update(
            {
                "entry_variant": entry_variant,
                "entry": entry,
                "stop": stop,
                "target": target,
                "exit_date": exit_date,
                "exit_price": exit_price,
                "bars_held": bars_held,
                "outcome": outcome,
                "target_hit": int(outcome == "target"),
                "r_multiple": realized_r,
                "mfe_r": mfe_r,
                "mae_r": mae_r,
            }
        )
        labelled.append(labelled_event)
    out = pd.DataFrame(labelled)
    if not out.empty:
        out["date"] = pd.to_datetime(out["date"])
        out["exit_date"] = pd.to_datetime(out["exit_date"])
    return out


def build_execution_variant_events(events: pd.DataFrame) -> pd.DataFrame:
    if events.empty:
        return events
    rows: list[pd.DataFrame] = []
    close_events = events.copy()
    close_events["entry_variant"] = "close_breakout"
    rows.append(close_events)
    next_day = events.copy()
    next_day["entry_variant"] = "next_day_confirmation"
    rows.append(next_day)
    retest = events.loc[events["setup"].astype(str).str.contains("breakout|darvas|vcp", case=False, regex=True)].copy()
    if not retest.empty:
        retest["entry_variant"] = "breakout_retest_hold"
        rows.append(retest)
    return pd.concat(rows, ignore_index=True)


def train_model(events: pd.DataFrame) -> tuple[pd.DataFrame, ModelResult]:
    if events.empty:
        return events, ModelResult(False, reason="No labelled signal events.")
    try:
        from sklearn.compose import ColumnTransformer
        from sklearn.ensemble import HistGradientBoostingClassifier
        from sklearn.impute import SimpleImputer
        from sklearn.metrics import accuracy_score, roc_auc_score
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import OneHotEncoder
    except Exception as exc:  # pragma: no cover - depends on local environment
        return events, ModelResult(False, reason=f"scikit-learn unavailable: {exc}")

    data = events.copy().sort_values("date").reset_index(drop=True)
    if len(data) < 200 or data["target_hit"].nunique() < 2:
        return data, ModelResult(False, reason="Need at least 200 labelled events and both outcome classes.")

    numeric_features = [
        "close",
        "turnover_cr_20d",
        "technical_score",
        "investment_score",
        "relative_strength",
        "rsi_14",
        "atr_14",
        "adr_pct_20",
        "volume_ratio_20d",
        "box_width_pct_20",
        "range_5_pct",
        "range_20_pct",
        "return_63d",
        "daily_return_pct",
        "breadth_positive_pct",
        "sector_return_1d_pct",
        "sector_rank_1d",
        "nifty_change_pct",
        "nifty_above_ema20",
        "banknifty_change_pct",
        "vix_close",
        "vix_change_pct",
        "fno_available",
        "fno_pcr",
        "fno_oi_change",
        "fno_bias_score",
        "futures_basis_pct",
        "ema20_distance_pct",
        "ema50_distance_pct",
    ]
    categorical_features = [
        "symbol",
        "sector",
        "stage",
        "setup",
        "setup_type",
        "market_regime",
        "trading_signal",
        "trend_signal",
        "supertrend_state",
        "fno_buildup",
    ]
    split_idx = max(1, int(len(data) * 0.75))
    train = data.iloc[:split_idx].copy()
    test = data.iloc[split_idx:].copy()
    if test.empty or train["target_hit"].nunique() < 2 or test["target_hit"].nunique() < 2:
        return data, ModelResult(False, reason="Time split did not contain both classes in train/test.")

    preprocessor = ColumnTransformer(
        transformers=[
            ("num", SimpleImputer(strategy="median"), numeric_features),
            (
                "cat",
                Pipeline(
                    steps=[
                        ("imputer", SimpleImputer(strategy="most_frequent")),
                        ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False, max_categories=80)),
                    ]
                ),
                categorical_features,
            ),
        ],
        remainder="drop",
    )
    model = Pipeline(
        steps=[
            ("prep", preprocessor),
            ("clf", HistGradientBoostingClassifier(max_iter=180, learning_rate=0.05, max_leaf_nodes=16, random_state=42)),
        ]
    )
    x_train = train[numeric_features + categorical_features]
    y_train = train["target_hit"].astype(int)
    x_test = test[numeric_features + categorical_features]
    y_test = test["target_hit"].astype(int)
    model.fit(x_train, y_train)
    proba_test = model.predict_proba(x_test)[:, 1]
    pred_test = (proba_test >= 0.5).astype(int)
    accuracy = float(accuracy_score(y_test, pred_test))
    try:
        roc_auc = float(roc_auc_score(y_test, proba_test))
    except Exception:
        roc_auc = None
    data["model_target_prob"] = model.predict_proba(data[numeric_features + categorical_features])[:, 1]
    data["model_split"] = np.where(data.index < split_idx, "train", "test")
    return data, ModelResult(True, len(train), len(test), accuracy, roc_auc, reason="Time-split model trained.")


def summarize(events: pd.DataFrame, *, min_trades: int) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if events.empty:
        empty = pd.DataFrame()
        return empty, empty, empty, empty, empty
    sort_metric = "net_expectancy_r" if "net_r_multiple" in events.columns else "expectancy_r"
    grouped = events.groupby(["setup"], dropna=False)
    setup_summary = _agg_group(grouped).sort_values([sort_metric, "win_rate_pct", "trades"], ascending=[False, False, False])
    combo_summary = _agg_group(events.loc[events.get("setup_type", "") == "combo"].groupby(["setup"], dropna=False)).sort_values(
        [sort_metric, "win_rate_pct", "trades"], ascending=[False, False, False]
    ) if "setup_type" in events.columns and (events["setup_type"] == "combo").any() else pd.DataFrame()
    sector_setup_summary = _agg_group(events.groupby(["sector", "setup"], dropna=False)).sort_values(
        [sort_metric, "win_rate_pct", "trades"], ascending=[False, False, False]
    )
    stock_setup = _agg_group(events.groupby(["symbol", "setup"], dropna=False))
    stock_setup = stock_setup[stock_setup["trades"] >= min_trades].sort_values(
        ["symbol", sort_metric, "win_rate_pct", "trades"],
        ascending=[True, False, False, False],
    )
    best_by_stock = stock_setup.groupby("symbol", as_index=False).head(1).reset_index(drop=True)
    latest_date = events["date"].max()
    latest = events[events["date"] == latest_date].copy()
    if "model_target_prob" not in latest.columns:
        latest["model_target_prob"] = np.nan
    latest = latest.sort_values(["model_target_prob", "relative_strength", "volume_ratio_20d"], ascending=[False, False, False])
    return setup_summary, combo_summary, sector_setup_summary, best_by_stock, latest


def build_regime_conditional_edge_map(events: pd.DataFrame, *, min_trades: int = 50) -> dict[str, pd.DataFrame]:
    """Build setup edge tables across market, volatility, breadth, VIX, and F&O contexts.

    This is deliberately computed from the labelled event frame so it can be
    regenerated from CSV artifacts without reconnecting to PostgreSQL.
    """
    keys = [
        "market_regime",
        "volatility",
        "breadth",
        "calendar_year",
        "theme_rs_year_breadth",
        "vix_change",
        "fno_postmortem",
        "live_gate",
    ]
    if events is None or events.empty:
        return {key: pd.DataFrame() for key in keys}

    work = events.copy()
    if "setup" not in work.columns:
        work["setup"] = "unknown"
    work["setup"] = work["setup"].fillna("unknown").astype(str).replace("", "unknown")
    if "market_regime" not in work.columns:
        work["market_regime"] = "unknown"
    work["market_regime"] = work["market_regime"].fillna("unknown").astype(str).replace("", "unknown")
    if "sector" not in work.columns:
        work["sector"] = "unknown"
    work["sector"] = work["sector"].fillna("unknown").astype(str).replace("", "unknown")
    work["calendar_year"] = _calendar_year_label(work.get("date", pd.Series(index=work.index, dtype=object)))
    work["volatility_regime"] = work.apply(_event_volatility_bucket, axis=1)
    work["breadth_bucket"] = work.get("breadth_positive_pct", pd.Series(index=work.index, dtype=float)).map(_breadth_bucket)
    work["vix_change_bucket"] = work.get("vix_change_pct", pd.Series(index=work.index, dtype=float)).map(_vix_change_bucket)
    work["pcr_bucket"] = work.apply(_pcr_bucket, axis=1)
    if "fno_buildup" in work.columns:
        work["fno_buildup"] = work["fno_buildup"].fillna("UNKNOWN").astype(str).replace("", "UNKNOWN")
    else:
        work["fno_buildup"] = "UNKNOWN"

    min_trades = max(1, int(min_trades))
    fno_min_trades = max(2, min(20, min_trades // 2 or 2))
    theme_min_trades = max(3, min(15, min_trades // 4 or 3))
    fno_available = pd.to_numeric(
        work["fno_available"] if "fno_available" in work.columns else pd.Series(0, index=work.index),
        errors="coerce",
    ).fillna(0)
    fno_pcr = work["fno_pcr"] if "fno_pcr" in work.columns else pd.Series(index=work.index, dtype=float)
    fno_mask = (
        (fno_available == 1)
        | fno_pcr.notna()
        | (work["setup"] == "combo_fno_confirmed_breakout")
    )
    theme_rs_mask = (
        work["sector"].str.contains("RAILWAYS|PSU", case=False, na=False)
        & (work["setup"] == "relative_strength_breakout")
    )

    maps = {
        "market_regime": _conditional_edge_summary(work, ["setup", "market_regime"], min_trades=min_trades),
        "volatility": _conditional_edge_summary(work, ["setup", "volatility_regime"], min_trades=min_trades),
        "breadth": _conditional_edge_summary(work, ["setup", "breadth_bucket"], min_trades=min_trades),
        "calendar_year": _conditional_edge_summary(work, ["setup", "calendar_year"], min_trades=min_trades),
        "theme_rs_year_breadth": _conditional_edge_summary(
            work.loc[theme_rs_mask],
            ["sector", "setup", "calendar_year", "breadth_bucket"],
            min_trades=theme_min_trades,
        ),
        "vix_change": _conditional_edge_summary(work, ["setup", "vix_change_bucket"], min_trades=min_trades),
        "fno_postmortem": _conditional_edge_summary(
            work.loc[fno_mask],
            ["setup", "pcr_bucket", "fno_buildup"],
            min_trades=fno_min_trades,
        ),
    }
    maps["live_gate"] = _build_live_gate_recommendations(work, maps, min_trades=min_trades)
    return maps


def add_execution_costs(events: pd.DataFrame, *, stop_atr: float = 1.5) -> pd.DataFrame:
    """Attach realistic delivery cost estimates and net R outcome columns.

    Costs are expressed first as percent of entry price, then converted into R
    by dividing by the trade's stop distance. This makes tight stops carry a
    larger cost penalty, which matches how live execution behaves.
    """
    if events is None or events.empty:
        return pd.DataFrame() if events is None else events.copy()
    out = events.copy()
    generated_columns = [
        "estimated_entry",
        "estimated_stop",
        "risk_pct",
        "cost_profile",
        "volume_spike_bucket",
        "estimated_cost_pct",
        "estimated_cost_r",
        "net_r_multiple",
        "net_positive",
    ]
    out = out.drop(columns=[column for column in generated_columns if column in out.columns])
    cost_rows = out.apply(lambda row: _execution_cost_fields(row, stop_atr=stop_atr), axis=1, result_type="expand")
    out = pd.concat([out.reset_index(drop=True), cost_rows.reset_index(drop=True)], axis=1)
    gross_r = pd.to_numeric(out.get("r_multiple"), errors="coerce")
    cost_r = pd.to_numeric(out.get("estimated_cost_r"), errors="coerce")
    out["net_r_multiple"] = gross_r - cost_r
    out["net_positive"] = (out["net_r_multiple"] > 0).astype(int)
    return out


def build_cost_adjusted_edge_map(events: pd.DataFrame, *, min_trades: int = 50) -> dict[str, pd.DataFrame]:
    """Build net-expectancy tables by setup, liquidity profile, and volume spike."""
    keys = ["setup_net", "cost_profile", "volume_spike"]
    if events is None or events.empty:
        return {key: pd.DataFrame() for key in keys}
    work = add_execution_costs(events)
    if "setup" not in work.columns:
        work["setup"] = "unknown"
    work["setup"] = work["setup"].fillna("unknown").astype(str).replace("", "unknown")
    min_trades = max(1, int(min_trades))

    def summarize_cost(columns: list[str]) -> pd.DataFrame:
        if any(column not in work.columns for column in columns):
            return pd.DataFrame()
        frame = _edge_agg_group(work.groupby(columns, dropna=False))
        if frame.empty:
            return frame
        frame = frame[frame["trades"] >= min_trades].copy()
        sort_metric = "net_expectancy_r" if "net_expectancy_r" in frame.columns else "expectancy_r"
        return frame.sort_values([sort_metric, "profit_factor", "trades"], ascending=[False, False, False]).reset_index(drop=True)

    return {
        "setup_net": summarize_cost(["setup"]),
        "cost_profile": summarize_cost(["setup", "cost_profile"]),
        "volume_spike": summarize_cost(["setup", "volume_spike_bucket"]),
    }


def render_cost_adjusted_edge_markdown(cost_maps: dict[str, pd.DataFrame]) -> str:
    if not cost_maps:
        return ""

    def pick(name: str, columns: list[str], limit: int = 30) -> pd.DataFrame:
        frame = cost_maps.get(name, pd.DataFrame())
        if frame is None or frame.empty:
            return pd.DataFrame()
        return frame.loc[:, [column for column in columns if column in frame.columns]].head(limit)

    setup_net = pick(
        "setup_net",
        [
            "setup",
            "trades",
            "expectancy_r",
            "net_expectancy_r",
            "avg_cost_r",
            "avg_cost_pct",
            "positive_r_pct",
            "positive_net_r_pct",
            "profit_factor",
            "net_profit_factor",
            "max_drawdown_r",
            "net_max_drawdown_r",
        ],
        30,
    )
    cost_profile = pick(
        "cost_profile",
        [
            "setup",
            "cost_profile",
            "trades",
            "expectancy_r",
            "net_expectancy_r",
            "avg_cost_r",
            "positive_net_r_pct",
            "net_profit_factor",
            "net_max_drawdown_r",
        ],
        40,
    )
    volume_spike = pick(
        "volume_spike",
        [
            "setup",
            "volume_spike_bucket",
            "trades",
            "expectancy_r",
            "net_expectancy_r",
            "avg_cost_r",
            "positive_net_r_pct",
            "net_profit_factor",
            "net_max_drawdown_r",
        ],
        40,
    )
    return "\n".join(
        [
            "## Cost-Adjusted Edge / Liquidity Read",
            "",
            "- Gross expectancy is converted to net expectancy using delivery/statutory cost plus a turnover/price/volume-spike execution profile.",
            "- Cost is divided by stop distance, so tight-stop trades are penalized more heavily in R terms.",
            "- `volume_spike_bucket` treats volume above roughly 6x average as impact risk, not additional confirmation.",
            "",
            "### Net Setup Leaderboard",
            "",
            _table(setup_net),
            "",
            "### Setup / Cost Profile Cross-Walk",
            "",
            _table(cost_profile),
            "",
            "### Setup / Volume Spike Cross-Walk",
            "",
            _table(volume_spike),
            "",
        ]
    )


def _execution_cost_fields(row: pd.Series, *, stop_atr: float) -> dict[str, Any]:
    entry = _num(row.get("entry"))
    close = _num(row.get("close"))
    if not math.isfinite(entry) or entry <= 0:
        entry = close
    stop = _num(row.get("stop"))
    if not math.isfinite(stop) or not math.isfinite(entry) or entry <= 0 or stop >= entry:
        stop = _estimate_stop_from_signal(row, entry=entry, stop_atr=stop_atr)
    risk_pct = (entry - stop) / entry * 100.0 if math.isfinite(entry) and entry > 0 and math.isfinite(stop) else float("nan")
    profile = _execution_cost_profile(row, entry=entry)
    cost_pct = EXECUTION_COST_PCT_BY_PROFILE.get(profile, EXECUTION_COST_PCT_BY_PROFILE["mid"])
    cost_r = cost_pct / risk_pct if math.isfinite(risk_pct) and risk_pct > 0 else float("nan")
    return {
        "estimated_entry": round(entry, 4) if math.isfinite(entry) else np.nan,
        "estimated_stop": round(stop, 4) if math.isfinite(stop) else np.nan,
        "risk_pct": round(float(risk_pct), 3) if math.isfinite(risk_pct) else np.nan,
        "cost_profile": profile,
        "volume_spike_bucket": _volume_spike_bucket(row.get("volume_ratio_20d")),
        "estimated_cost_pct": round(float(cost_pct), 3),
        "estimated_cost_r": round(float(cost_r), 3) if math.isfinite(cost_r) else np.nan,
    }


def _estimate_stop_from_signal(row: pd.Series, *, entry: float, stop_atr: float) -> float:
    if not math.isfinite(entry) or entry <= 0:
        return float("nan")
    atr = _num(row.get("atr_14"))
    prev_low = _num(row.get("prev_low_10"))
    stop_candidates: list[float] = []
    if math.isfinite(atr) and atr > 0:
        stop_candidates.append(entry - atr * stop_atr)
    if math.isfinite(prev_low) and 0 < prev_low < entry:
        stop_candidates.append(prev_low)
    stop = max(stop_candidates) if stop_candidates else entry * 0.945
    min_risk = max(entry * 0.005, atr * 0.50 if math.isfinite(atr) and atr > 0 else 0.0)
    if entry - stop < min_risk:
        stop = entry - min_risk
    return stop


def _execution_cost_profile(row: pd.Series, *, entry: float) -> str:
    price = _num(row.get("close"))
    if not math.isfinite(price) or price <= 0:
        price = entry
    turnover = _num(row.get("turnover_cr_20d"))
    volume_ratio = _num(row.get("volume_ratio_20d"))
    if (
        (math.isfinite(volume_ratio) and volume_ratio > 6.0)
        or (math.isfinite(price) and price < 50.0)
        or (math.isfinite(turnover) and turnover < 25.0)
    ):
        return "illiquid_spike"
    if (
        math.isfinite(turnover)
        and turnover >= 100.0
        and math.isfinite(price)
        and price >= 100.0
        and (not math.isfinite(volume_ratio) or volume_ratio <= 3.5)
    ):
        return "liquid"
    return "mid"


def _volume_spike_bucket(value: Any) -> str:
    volume_ratio = _num(value)
    if not math.isfinite(volume_ratio):
        return "unknown"
    if volume_ratio < 1.2:
        return "low_confirmation"
    if volume_ratio <= 3.0:
        return "confirmed_volume"
    if volume_ratio <= 5.0:
        return "elevated_volume"
    if volume_ratio <= 6.0:
        return "impact_warning"
    return "high_impact_spike"


def render_regime_edge_markdown(regime_maps: dict[str, pd.DataFrame]) -> str:
    """Render the regime edge-map frames as Markdown sections."""
    if not regime_maps:
        return ""

    def pick(name: str, columns: list[str], limit: int = 30) -> pd.DataFrame:
        frame = regime_maps.get(name, pd.DataFrame())
        if frame is None or frame.empty:
            return pd.DataFrame()
        return frame.loc[:, [column for column in columns if column in frame.columns]].head(limit)

    market = pick(
        "market_regime",
        [
            "setup",
            "market_regime",
            "trades",
            "win_rate_pct",
            "positive_r_pct",
            "expectancy_r",
            "net_expectancy_r",
            "avg_cost_r",
            "median_r",
            "profit_factor",
            "net_profit_factor",
            "max_drawdown_r",
            "net_max_drawdown_r",
        ],
        40,
    )
    volatility = pick(
        "volatility",
        ["setup", "volatility_regime", "trades", "win_rate_pct", "positive_r_pct", "expectancy_r", "net_expectancy_r", "avg_cost_r", "profit_factor", "net_profit_factor", "max_drawdown_r", "net_max_drawdown_r"],
        30,
    )
    breadth = pick(
        "breadth",
        ["setup", "breadth_bucket", "trades", "win_rate_pct", "positive_r_pct", "expectancy_r", "net_expectancy_r", "avg_cost_r", "profit_factor", "net_profit_factor", "max_drawdown_r", "net_max_drawdown_r"],
        30,
    )
    calendar_year = pick(
        "calendar_year",
        ["setup", "calendar_year", "trades", "win_rate_pct", "positive_r_pct", "expectancy_r", "net_expectancy_r", "avg_cost_r", "profit_factor", "net_profit_factor", "max_drawdown_r", "net_max_drawdown_r"],
        40,
    )
    theme_rs_year_breadth = pick(
        "theme_rs_year_breadth",
        ["sector", "setup", "calendar_year", "breadth_bucket", "trades", "win_rate_pct", "positive_r_pct", "expectancy_r", "net_expectancy_r", "avg_cost_r", "profit_factor", "net_profit_factor", "max_drawdown_r", "net_max_drawdown_r"],
        30,
    )
    vix = pick(
        "vix_change",
        ["setup", "vix_change_bucket", "trades", "win_rate_pct", "positive_r_pct", "expectancy_r", "net_expectancy_r", "avg_cost_r", "profit_factor", "net_profit_factor", "max_drawdown_r", "net_max_drawdown_r"],
        30,
    )
    fno = pick(
        "fno_postmortem",
        ["setup", "pcr_bucket", "fno_buildup", "trades", "win_rate_pct", "positive_r_pct", "expectancy_r", "net_expectancy_r", "avg_cost_r", "profit_factor", "net_profit_factor", "max_drawdown_r", "net_max_drawdown_r"],
        40,
    )
    gates = pick(
        "live_gate",
        [
            "setup",
            "gate_action",
            "trades",
            "overall_expectancy_r",
            "overall_net_expectancy_r",
            "best_market_regime",
            "best_market_expectancy_r",
            "best_market_net_expectancy_r",
            "worst_market_regime",
            "worst_market_expectancy_r",
            "worst_market_net_expectancy_r",
            "best_volatility_regime",
            "best_breadth_bucket",
            "best_vix_change_bucket",
            "gate_reason",
        ],
        30,
    )

    lines = [
        "## Regime-Conditional Edge Map",
        "",
        "- This section tests whether headline setup expectancy survives different market, volatility, breadth, and VIX contexts.",
        "- `risk_off` is not automatically a no-trade label here; it is a historical bucket that must be interpreted by actual expectancy and drawdown.",
        "- Volatility is an ADR-based EOD proxy in this report; the PDF research layer also computes an EWMA volatility read-through.",
        "",
        "### Market Regime / Setup Cross-Walk",
        "",
        _table(market),
        "",
        "### ADR Volatility / Setup Cross-Walk",
        "",
        _table(volatility),
        "",
        "### Breadth / Setup Cross-Walk",
        "",
        _table(breadth),
        "",
        "### Calendar-Year / Setup Cross-Walk",
        "",
        _table(calendar_year),
        "",
        "### Railways/PSU RS Breakout Year/Breadth Stress Test",
        "",
        _table(theme_rs_year_breadth),
        "",
        "### VIX-Change / Setup Cross-Walk",
        "",
        _table(vix),
        "",
        "### F&O Failure Post-Mortem",
        "",
        _table(fno),
        "",
        "### Live Gate Recommendations",
        "",
        _table(gates),
        "",
    ]
    return "\n".join(lines)


def _conditional_edge_summary(events: pd.DataFrame, columns: list[str], *, min_trades: int) -> pd.DataFrame:
    if events is None or events.empty or any(column not in events.columns for column in columns):
        return pd.DataFrame()
    summary = _edge_agg_group(events.groupby(columns, dropna=False))
    if summary.empty:
        return summary
    summary = summary[summary["trades"] >= int(min_trades)].copy()
    sort_metric = "net_expectancy_r" if "net_expectancy_r" in summary.columns else "expectancy_r"
    return summary.sort_values([sort_metric, "profit_factor", "trades"], ascending=[False, False, False]).reset_index(drop=True)


def _calendar_year_label(values: pd.Series) -> pd.Series:
    years = pd.to_datetime(values, errors="coerce").dt.year.astype("Int64").astype(str)
    return years.replace("<NA>", "unknown")


def _edge_agg_group(grouped: Any) -> pd.DataFrame:
    aggregations = {
        "trades": ("r_multiple", "size"),
        "target_hits": ("target_hit", "sum"),
        "win_rate_pct": ("target_hit", lambda s: round(float(pd.to_numeric(s, errors="coerce").fillna(0).mean() * 100.0), 2)),
        "positive_r_pct": ("r_multiple", lambda s: round(float((pd.to_numeric(s, errors="coerce") > 0).mean() * 100.0), 2)),
        "expectancy_r": ("r_multiple", lambda s: round(float(pd.to_numeric(s, errors="coerce").mean()), 3)),
        "median_r": ("r_multiple", lambda s: round(float(pd.to_numeric(s, errors="coerce").median()), 3)),
        "avg_win_r": ("r_multiple", lambda s: _mean_or_nan(pd.to_numeric(s, errors="coerce")[pd.to_numeric(s, errors="coerce") > 0])),
        "avg_loss_r": ("r_multiple", lambda s: _mean_or_nan(pd.to_numeric(s, errors="coerce")[pd.to_numeric(s, errors="coerce") < 0])),
        "profit_factor": ("r_multiple", _profit_factor),
        "max_drawdown_r": ("r_multiple", _max_drawdown_r),
    }
    if "net_r_multiple" in grouped.obj.columns:
        aggregations.update(
            {
                "net_expectancy_r": ("net_r_multiple", lambda s: round(float(pd.to_numeric(s, errors="coerce").mean()), 3)),
                "positive_net_r_pct": ("net_r_multiple", lambda s: round(float((pd.to_numeric(s, errors="coerce") > 0).mean() * 100.0), 2)),
                "net_profit_factor": ("net_r_multiple", _profit_factor),
                "net_max_drawdown_r": ("net_r_multiple", _max_drawdown_r),
                "avg_cost_r": ("estimated_cost_r", lambda s: round(float(pd.to_numeric(s, errors="coerce").mean()), 3)),
                "avg_cost_pct": ("estimated_cost_pct", lambda s: round(float(pd.to_numeric(s, errors="coerce").mean()), 3)),
            }
        )
    rows = grouped.agg(**aggregations).reset_index()
    rows["target_hits"] = rows["target_hits"].fillna(0).astype(int)
    return rows


def _profit_factor(series: pd.Series) -> float:
    values = pd.to_numeric(series, errors="coerce").fillna(0.0)
    gross_win = float(values[values > 0].sum())
    gross_loss = float(-values[values < 0].sum())
    if gross_loss == 0:
        return float("nan") if gross_win == 0 else float("inf")
    return round(gross_win / gross_loss, 2)


def _event_volatility_bucket(row: pd.Series) -> str:
    adr = _num(row.get("adr_pct_20"))
    if not math.isfinite(adr):
        atr = _num(row.get("atr_14"))
        close = _num(row.get("close"))
        adr = atr / close * 100.0 if math.isfinite(atr) and math.isfinite(close) and close > 0 else float("nan")
    if not math.isfinite(adr):
        return "unknown"
    if adr < 2.0:
        return "low_vol"
    if adr < 4.0:
        return "normal_vol"
    return "high_vol"


def _breadth_bucket(value: Any) -> str:
    breadth = _num(value)
    if not math.isfinite(breadth):
        return "unknown"
    if breadth >= 60:
        return "broad_positive"
    if breadth >= 50:
        return "constructive"
    if breadth >= 45:
        return "mixed"
    return "weak"


def _vix_change_bucket(value: Any) -> str:
    change = _num(value)
    if not math.isfinite(change):
        return "unknown"
    if change >= 5:
        return "vix_spike"
    if change >= 2:
        return "vix_rising"
    if change <= -2:
        return "vix_easing"
    return "vix_calm"


def _pcr_bucket(row: pd.Series) -> str:
    pcr = _num(row.get("fno_pcr"))
    if not math.isfinite(pcr):
        return "missing"
    if pcr >= 1.10:
        return "put_heavy"
    if pcr <= 0.80:
        return "call_heavy"
    return "balanced"


def _build_live_gate_recommendations(
    events: pd.DataFrame,
    regime_maps: dict[str, pd.DataFrame],
    *,
    min_trades: int,
) -> pd.DataFrame:
    overall = _edge_agg_group(events.groupby(["setup"], dropna=False))
    sort_metric = "net_expectancy_r" if "net_expectancy_r" in overall.columns else "expectancy_r"
    overall = overall.sort_values([sort_metric, "profit_factor", "trades"], ascending=[False, False, False])
    rows: list[dict[str, Any]] = []
    for row in overall.to_dict("records"):
        setup = str(row.get("setup") or "unknown")
        market = _best_worst_context(regime_maps.get("market_regime"), setup, "market_regime")
        volatility = _best_worst_context(regime_maps.get("volatility"), setup, "volatility_regime")
        breadth = _best_worst_context(regime_maps.get("breadth"), setup, "breadth_bucket")
        vix = _best_worst_context(regime_maps.get("vix_change"), setup, "vix_change_bucket")
        gate_overall_expectancy = _num(row.get("net_expectancy_r"))
        if not math.isfinite(gate_overall_expectancy):
            gate_overall_expectancy = _num(row.get("expectancy_r"))
        gate_best_market_expectancy = _num(market.get("best_net_expectancy_r"))
        if not math.isfinite(gate_best_market_expectancy):
            gate_best_market_expectancy = _num(market.get("best_expectancy_r"))
        gate_worst_market_expectancy = _num(market.get("worst_net_expectancy_r"))
        if not math.isfinite(gate_worst_market_expectancy):
            gate_worst_market_expectancy = _num(market.get("worst_expectancy_r"))
        action, reason = _gate_action(
            setup=setup,
            trades=int(row.get("trades") or 0),
            overall_expectancy=gate_overall_expectancy,
            overall_profit_factor=_num(row.get("profit_factor")),
            best_market_expectancy=gate_best_market_expectancy,
            best_market_trades=int(market.get("best_trades") or 0),
            worst_market_expectancy=gate_worst_market_expectancy,
            min_trades=min_trades,
        )
        rows.append(
            {
                "setup": setup,
                "gate_action": action,
                "trades": int(row.get("trades") or 0),
                "overall_expectancy_r": row.get("expectancy_r"),
                "overall_net_expectancy_r": row.get("net_expectancy_r", np.nan),
                "overall_profit_factor": row.get("profit_factor"),
                "best_market_regime": market.get("best_label", ""),
                "best_market_expectancy_r": market.get("best_expectancy_r", np.nan),
                "best_market_net_expectancy_r": market.get("best_net_expectancy_r", np.nan),
                "best_market_trades": market.get("best_trades", np.nan),
                "worst_market_regime": market.get("worst_label", ""),
                "worst_market_expectancy_r": market.get("worst_expectancy_r", np.nan),
                "worst_market_net_expectancy_r": market.get("worst_net_expectancy_r", np.nan),
                "best_volatility_regime": volatility.get("best_label", ""),
                "best_volatility_expectancy_r": volatility.get("best_expectancy_r", np.nan),
                "best_volatility_net_expectancy_r": volatility.get("best_net_expectancy_r", np.nan),
                "best_breadth_bucket": breadth.get("best_label", ""),
                "best_breadth_expectancy_r": breadth.get("best_expectancy_r", np.nan),
                "best_breadth_net_expectancy_r": breadth.get("best_net_expectancy_r", np.nan),
                "best_vix_change_bucket": vix.get("best_label", ""),
                "best_vix_change_expectancy_r": vix.get("best_expectancy_r", np.nan),
                "best_vix_change_net_expectancy_r": vix.get("best_net_expectancy_r", np.nan),
                "gate_reason": reason,
            }
        )
    return pd.DataFrame(rows).sort_values(
        ["gate_action", "overall_expectancy_r", "trades"],
        ascending=[True, False, False],
    ).reset_index(drop=True)


def _best_worst_context(frame: pd.DataFrame | None, setup: str, label_column: str) -> dict[str, Any]:
    if frame is None or frame.empty or label_column not in frame.columns:
        return {}
    subset = frame[frame["setup"].astype(str) == setup].copy()
    if subset.empty:
        return {}
    sort_metric = "net_expectancy_r" if "net_expectancy_r" in subset.columns else "expectancy_r"
    subset = subset.sort_values([sort_metric, "profit_factor", "trades"], ascending=[False, False, False])
    best = subset.iloc[0]
    worst = subset.sort_values([sort_metric, "profit_factor", "trades"], ascending=[True, True, False]).iloc[0]
    return {
        "best_label": best.get(label_column),
        "best_expectancy_r": best.get("expectancy_r"),
        "best_net_expectancy_r": best.get("net_expectancy_r", np.nan),
        "best_trades": best.get("trades"),
        "worst_label": worst.get(label_column),
        "worst_expectancy_r": worst.get("expectancy_r"),
        "worst_net_expectancy_r": worst.get("net_expectancy_r", np.nan),
        "worst_trades": worst.get("trades"),
    }


def _gate_action(
    *,
    setup: str,
    trades: int,
    overall_expectancy: float,
    overall_profit_factor: float,
    best_market_expectancy: float,
    best_market_trades: int,
    worst_market_expectancy: float,
    min_trades: int,
) -> tuple[str, str]:
    if setup == "combo_fno_confirmed_breakout":
        return "block_rebuild", "F&O-confirmed breakout is negative in aggregate; rebuild before use."
    if trades < min_trades:
        return "wait_retest", "Sample is below the regime-map threshold; require price confirmation."
    if math.isfinite(overall_expectancy) and overall_expectancy < -0.05 and (
        not math.isfinite(best_market_expectancy) or best_market_expectancy <= 0.05
    ):
        return "block_rebuild", "No reliable positive context found."
    if math.isfinite(best_market_expectancy) and best_market_expectancy >= 0.15 and best_market_trades >= min_trades:
        if math.isfinite(worst_market_expectancy) and worst_market_expectancy < -0.10:
            return "half_size_best_regime", "Edge is regime-specific; use half-size outside confirmed context."
        return "promote_best_regime", "Best regime bucket has strong positive expectancy and enough trades."
    if math.isfinite(overall_expectancy) and overall_expectancy > 0.05 and math.isfinite(overall_profit_factor) and overall_profit_factor >= 1.10:
        return "half_size_best_regime", "Positive aggregate edge, but wait for context alignment."
    return "wait_retest", "Require retest or additional confirmation before promotion."


def build_current_decision_queue(
    *,
    data: pd.DataFrame,
    setup_summary: pd.DataFrame,
    best_by_stock: pd.DataFrame,
    min_volume_ratio: float,
    max_darvas_width_pct: float,
    min_adr_pct: float,
    min_turnover_cr: float,
    stop_atr: float = 1.5,
) -> pd.DataFrame:
    if data.empty:
        return pd.DataFrame()
    latest_date = data["date"].max()
    current_events = generate_signal_events(
        data.loc[data["date"] == latest_date],
        start=str(latest_date.date()),
        min_volume_ratio=min_volume_ratio,
        max_darvas_width_pct=max_darvas_width_pct,
        min_adr_pct=min_adr_pct,
        min_turnover_cr=min_turnover_cr,
    )
    if current_events.empty:
        return current_events
    setup_cols = [
        "setup",
        "trades",
        "win_rate_pct",
        "expectancy_r",
        "net_expectancy_r",
        "avg_cost_r",
        "sample_quality",
        "avg_model_target_prob",
    ]
    setup_ref = setup_summary.loc[:, [column for column in setup_cols if column in setup_summary.columns]].rename(
        columns={
            "trades": "setup_trades",
            "win_rate_pct": "setup_win_rate_pct",
            "expectancy_r": "setup_expectancy_r",
            "net_expectancy_r": "setup_net_expectancy_r",
            "avg_cost_r": "setup_avg_cost_r",
            "sample_quality": "setup_sample_quality",
            "avg_model_target_prob": "setup_model_prob",
        }
    )
    stock_ref = best_by_stock.loc[:, ["symbol", "setup", "expectancy_r", "win_rate_pct", "trades"]].rename(
        columns={
            "setup": "best_historical_setup",
            "expectancy_r": "stock_best_expectancy_r",
            "win_rate_pct": "stock_best_win_rate_pct",
            "trades": "stock_best_trades",
        }
    )
    out = current_events.merge(setup_ref, on="setup", how="left").merge(stock_ref, on="symbol", how="left")
    out = add_execution_costs(out, stop_atr=stop_atr)
    out["matches_stock_best_setup"] = (out["setup"] == out["best_historical_setup"]).astype(int)
    out["gross_decision_score"] = out.apply(_gross_decision_score_row, axis=1)
    out["decision_score"] = out.apply(_decision_score_row, axis=1)
    out["net_decision_score"] = out["decision_score"]
    out["action"] = out.apply(_decision_action_row, axis=1)
    out["instrument_read"] = out.apply(_instrument_read_row, axis=1)
    out["decision_reasons"] = out.apply(_decision_reasons_row, axis=1)
    sort_cols = ["net_decision_score", "setup_net_expectancy_r", "setup_expectancy_r", "relative_strength"]
    return out.sort_values(sort_cols, ascending=[False, False, False, False]).reset_index(drop=True)


def _gross_decision_score_row(row: pd.Series) -> float:
    score = 45.0
    expectancy = _num(row.get("setup_expectancy_r"))
    if math.isfinite(expectancy):
        score += max(-15, min(18, expectancy * 35))
    setup_trades = _num(row.get("setup_trades"))
    if setup_trades >= 100:
        score += 8
    elif setup_trades >= 20:
        score += 4
    elif setup_trades and setup_trades < 8:
        score -= 8
    if _num(row.get("matches_stock_best_setup")) == 1:
        score += 7
    volume_ratio = _num(row.get("volume_ratio_20d"))
    if volume_ratio >= 2:
        score += 8
    elif volume_ratio >= 1.5:
        score += 4
    rs = _num(row.get("relative_strength"))
    if rs >= 70:
        score += 6
    elif rs < 35:
        score -= 5
    breadth = _num(row.get("breadth_positive_pct"))
    if breadth >= 55:
        score += 5
    elif breadth < 45:
        score -= 6
    sector_rank = _num(row.get("sector_rank_1d"))
    if sector_rank >= 65:
        score += 5
    elif sector_rank < 35:
        score -= 4
    regime = str(row.get("market_regime") or "").lower()
    if regime == "expansion":
        score += 8
    elif regime == "risk_off":
        score -= 15
    vix_change = _num(row.get("vix_change_pct"))
    if vix_change >= 4:
        score -= 8
    fno_bias = _num(row.get("fno_bias_score"))
    if math.isfinite(fno_bias):
        score += max(-10, min(10, fno_bias * 8))
    return round(max(0.0, min(100.0, score)), 1)


def _decision_score_row(row: pd.Series) -> float:
    score = _gross_decision_score_row(row)
    gross_expectancy = _num(row.get("setup_expectancy_r"))
    net_expectancy = _num(row.get("setup_net_expectancy_r"))
    if math.isfinite(net_expectancy):
        gross_component = max(-15, min(18, gross_expectancy * 35)) if math.isfinite(gross_expectancy) else 0
        net_component = max(-18, min(12, net_expectancy * 45))
        score += net_component - gross_component
        if net_expectancy < 0:
            score -= 8

    volume_ratio = _num(row.get("volume_ratio_20d"))
    # The gross score treats high volume as confirmation. Above roughly 5-6x,
    # it becomes an impact/slippage warning, so remove the confirmation benefit
    # and add an explicit penalty.
    if math.isfinite(volume_ratio):
        if volume_ratio > 10:
            score -= 22
        elif volume_ratio > 6:
            score -= 14
        elif volume_ratio > 5:
            score -= 6

    cost_r = _num(row.get("estimated_cost_r"))
    if math.isfinite(cost_r):
        if cost_r >= 0.18:
            score -= 12
        elif cost_r >= 0.11:
            score -= 7
        elif cost_r >= 0.07:
            score -= 3

    cost_profile = str(row.get("cost_profile") or "").lower()
    if cost_profile == "illiquid_spike":
        score -= 10
    elif cost_profile == "mid":
        score -= 3

    breadth = _num(row.get("breadth_positive_pct"))
    if math.isfinite(breadth) and breadth < 50:
        score -= 5

    return round(max(0.0, min(100.0, score)), 1)


def _decision_action_row(row: pd.Series) -> str:
    score = _num(row.get("decision_score"))
    regime = str(row.get("market_regime") or "").lower()
    if score >= 72 and regime != "risk_off":
        return "BEST CANDIDATE"
    if score >= 58:
        return "WAIT FOR TRIGGER/RETEST"
    if score >= 45:
        return "WATCH ONLY"
    return "NO TRADE"


def _instrument_read_row(row: pd.Series) -> str:
    score = _num(row.get("decision_score"))
    fno_available = _num(row.get("fno_available")) == 1
    vix_change = _num(row.get("vix_change_pct"))
    fno_bias = _num(row.get("fno_bias_score"))
    if not fno_available:
        return "Cash only / F&O unavailable"
    if score < 55:
        return "Avoid options; setup not strong enough"
    if vix_change >= 4:
        return "Prefer spreads or futures; avoid naked option buys"
    if fno_bias < 0:
        return "F&O conflicts; prefer cash or skip"
    return "Futures/cash preferred; options only if liquid"


def _decision_reasons_row(row: pd.Series) -> str:
    reasons: list[str] = []
    if _num(row.get("setup_net_expectancy_r")) > 0:
        reasons.append(f"net setup expectancy {float(row.get('setup_net_expectancy_r')):.2f}R")
    elif _num(row.get("setup_expectancy_r")) > 0:
        reasons.append(f"gross setup expectancy {float(row.get('setup_expectancy_r')):.2f}R")
    if _num(row.get("matches_stock_best_setup")) == 1:
        reasons.append("matches stock best setup")
    if _num(row.get("volume_ratio_20d")) > 6:
        reasons.append(f"volume spike/slippage risk {float(row.get('volume_ratio_20d')):.1f}x")
    elif _num(row.get("volume_ratio_20d")) >= 1.5:
        reasons.append(f"volume {float(row.get('volume_ratio_20d')):.1f}x")
    if _num(row.get("estimated_cost_r")) >= 0.11:
        reasons.append(f"cost drag {float(row.get('estimated_cost_r')):.2f}R")
    if str(row.get("market_regime") or "").lower() == "risk_off":
        reasons.append("risk-off market penalty")
    elif str(row.get("market_regime") or "").lower() == "expansion":
        reasons.append("expansion regime")
    if _num(row.get("fno_available")) == 1:
        reasons.append(f"F&O {row.get('fno_buildup') or 'available'}")
    return "; ".join(reasons[:6])


def _agg_group(grouped: Any) -> pd.DataFrame:
    aggregations = {
        "trades": ("target_hit", "size"),
        "target_hits": ("target_hit", "sum"),
        "win_rate_pct": ("target_hit", lambda s: round(float(s.mean() * 100.0), 2)),
        "expectancy_r": ("r_multiple", lambda s: round(float(s.mean()), 3)),
        "median_r": ("r_multiple", lambda s: round(float(s.median()), 3)),
        "avg_win_r": ("r_multiple", lambda s: _mean_or_nan(s[s > 0])),
        "avg_loss_r": ("r_multiple", lambda s: _mean_or_nan(s[s < 0])),
        "max_drawdown_r": ("r_multiple", _max_drawdown_r),
        "avg_mfe_r": ("mfe_r", lambda s: round(float(s.mean()), 3)),
        "avg_mae_r": ("mae_r", lambda s: round(float(s.mean()), 3)),
        "avg_bars_held": ("bars_held", lambda s: round(float(s.mean()), 2)),
        "avg_volume_ratio": ("volume_ratio_20d", lambda s: round(float(s.mean()), 2)),
        "avg_adr_pct": ("adr_pct_20", lambda s: round(float(s.mean()), 2)),
    }
    if "net_r_multiple" in grouped.obj.columns:
        aggregations.update(
            {
                "net_expectancy_r": ("net_r_multiple", lambda s: round(float(pd.to_numeric(s, errors="coerce").mean()), 3)),
                "positive_net_r_pct": ("net_r_multiple", lambda s: round(float((pd.to_numeric(s, errors="coerce") > 0).mean() * 100.0), 2)),
                "net_profit_factor": ("net_r_multiple", _profit_factor),
                "net_max_drawdown_r": ("net_r_multiple", _max_drawdown_r),
                "avg_cost_r": ("estimated_cost_r", lambda s: round(float(pd.to_numeric(s, errors="coerce").mean()), 3)),
                "avg_cost_pct": ("estimated_cost_pct", lambda s: round(float(pd.to_numeric(s, errors="coerce").mean()), 3)),
            }
        )
    rows = grouped.agg(**aggregations).reset_index()
    rows["sample_quality"] = np.select(
        [rows["trades"] >= 20, rows["trades"] >= 8],
        ["higher", "medium"],
        default="provisional",
    )
    if "model_target_prob" in grouped.obj.columns:
        model_probs = grouped["model_target_prob"].mean().reset_index(name="avg_model_target_prob")
        aggregate_columns = set(aggregations) | {"sample_quality"}
        group_columns = [column for column in rows.columns if column not in aggregate_columns]
        rows = rows.merge(model_probs, on=group_columns, how="left")
        rows["avg_model_target_prob"] = rows["avg_model_target_prob"].round(3)
    return rows


def _mean_or_nan(series: pd.Series) -> float:
    if series.empty:
        return float("nan")
    return round(float(series.mean()), 3)


def _max_drawdown_r(series: pd.Series) -> float:
    if series.empty:
        return 0.0
    cumulative = pd.to_numeric(series, errors="coerce").fillna(0).cumsum()
    drawdown = cumulative - cumulative.cummax()
    return round(float(drawdown.min()), 3)


def write_outputs(
    *,
    events: pd.DataFrame,
    setup_summary: pd.DataFrame,
    combo_summary: pd.DataFrame,
    sector_setup_summary: pd.DataFrame,
    best_by_stock: pd.DataFrame,
    variant_summary: pd.DataFrame,
    current_decision_queue: pd.DataFrame,
    latest: pd.DataFrame,
    model_result: ModelResult,
    latest_trade_date: str,
    selected_symbols: list[str],
    args: argparse.Namespace,
) -> dict[str, Path]:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    MODULE_REPORT_DIR.mkdir(parents=True, exist_ok=True)
    LATEST_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    events = attach_modules_to_events(events)
    regime_maps = build_regime_conditional_edge_map(events, min_trades=args.min_regime_trades)
    cost_maps = build_cost_adjusted_edge_map(events, min_trades=args.min_regime_trades)
    module_summary = aggregate_module_summary(setup_summary)
    module_candidates = build_module_candidates(current_decision_queue, setup_summary)
    paths = {
        "events": REPORT_DIR / f"signal_events_{stamp}.csv",
        "setup_summary": REPORT_DIR / f"setup_leaderboard_{stamp}.csv",
        "combo_summary": REPORT_DIR / f"combo_setup_leaderboard_{stamp}.csv",
        "sector_setup_summary": REPORT_DIR / f"sector_setup_leaderboard_{stamp}.csv",
        "best_by_stock": REPORT_DIR / f"stock_best_setups_{stamp}.csv",
        "variant_summary": REPORT_DIR / f"execution_variant_leaderboard_{stamp}.csv",
        "cost_setup": REPORT_DIR / f"cost_adjusted_setup_leaderboard_{stamp}.csv",
        "cost_profile": REPORT_DIR / f"cost_profile_leaderboard_{stamp}.csv",
        "cost_volume_spike": REPORT_DIR / f"cost_volume_spike_leaderboard_{stamp}.csv",
        "regime_market": REPORT_DIR / f"regime_market_leaderboard_{stamp}.csv",
        "regime_volatility": REPORT_DIR / f"regime_volatility_leaderboard_{stamp}.csv",
        "regime_breadth": REPORT_DIR / f"regime_breadth_leaderboard_{stamp}.csv",
        "regime_year": REPORT_DIR / f"regime_year_leaderboard_{stamp}.csv",
        "theme_rs_year_breadth": REPORT_DIR / f"theme_rs_year_breadth_{stamp}.csv",
        "regime_vix": REPORT_DIR / f"regime_vix_leaderboard_{stamp}.csv",
        "fno_postmortem": REPORT_DIR / f"fno_postmortem_{stamp}.csv",
        "live_gate": REPORT_DIR / f"live_gate_recommendations_{stamp}.csv",
        "current_decision_queue": REPORT_DIR / f"current_decision_queue_{stamp}.csv",
        "latest": REPORT_DIR / f"latest_signal_candidates_{stamp}.csv",
        "md": REPORT_DIR / f"signal_effectiveness_{stamp}.md",
        "html": REPORT_DIR / f"signal_effectiveness_{stamp}.html",
        "module_summary": MODULE_REPORT_DIR / f"module_summary_{stamp}.csv",
        "module_candidates": MODULE_REPORT_DIR / f"module_candidates_{stamp}.csv",
        "named_modules_md": MODULE_REPORT_DIR / f"named_strategy_modules_{stamp}.md",
        "named_modules_html": MODULE_REPORT_DIR / f"named_strategy_modules_{stamp}.html",
    }
    events.to_csv(paths["events"], index=False)
    setup_summary.to_csv(paths["setup_summary"], index=False)
    combo_summary.to_csv(paths["combo_summary"], index=False)
    sector_setup_summary.to_csv(paths["sector_setup_summary"], index=False)
    best_by_stock.to_csv(paths["best_by_stock"], index=False)
    variant_summary.to_csv(paths["variant_summary"], index=False)
    cost_maps["setup_net"].to_csv(paths["cost_setup"], index=False)
    cost_maps["cost_profile"].to_csv(paths["cost_profile"], index=False)
    cost_maps["volume_spike"].to_csv(paths["cost_volume_spike"], index=False)
    regime_maps["market_regime"].to_csv(paths["regime_market"], index=False)
    regime_maps["volatility"].to_csv(paths["regime_volatility"], index=False)
    regime_maps["breadth"].to_csv(paths["regime_breadth"], index=False)
    regime_maps["calendar_year"].to_csv(paths["regime_year"], index=False)
    regime_maps["theme_rs_year_breadth"].to_csv(paths["theme_rs_year_breadth"], index=False)
    regime_maps["vix_change"].to_csv(paths["regime_vix"], index=False)
    regime_maps["fno_postmortem"].to_csv(paths["fno_postmortem"], index=False)
    regime_maps["live_gate"].to_csv(paths["live_gate"], index=False)
    current_decision_queue.to_csv(paths["current_decision_queue"], index=False)
    latest.to_csv(paths["latest"], index=False)
    module_summary.to_csv(paths["module_summary"], index=False)
    module_candidates.to_csv(paths["module_candidates"], index=False)
    md = build_markdown(
        events=events,
        setup_summary=setup_summary,
        combo_summary=combo_summary,
        sector_setup_summary=sector_setup_summary,
        best_by_stock=best_by_stock,
        variant_summary=variant_summary,
        module_summary=module_summary,
        cost_maps=cost_maps,
        regime_maps=regime_maps,
        current_decision_queue=current_decision_queue,
        latest=latest,
        model_result=model_result,
        latest_trade_date=latest_trade_date,
        selected_symbols=selected_symbols,
        args=args,
        paths=paths,
    )
    named_modules_md = build_named_strategy_modules_markdown(
        module_summary=module_summary,
        module_candidates=module_candidates,
        latest_trade_date=latest_trade_date,
        selected_symbols=selected_symbols,
        args=args,
        paths=paths,
    )
    paths["md"].write_text(md, encoding="utf-8")
    paths["html"].write_text(markdown_to_html(md), encoding="utf-8")
    paths["named_modules_md"].write_text(named_modules_md, encoding="utf-8")
    paths["named_modules_html"].write_text(markdown_to_html(named_modules_md), encoding="utf-8")
    (LATEST_DIR / "signal_effectiveness.md").write_text(md, encoding="utf-8")
    (LATEST_DIR / "signal_effectiveness.html").write_text(markdown_to_html(md), encoding="utf-8")
    (LATEST_DIR / "named_strategy_modules.md").write_text(named_modules_md, encoding="utf-8")
    (LATEST_DIR / "named_strategy_modules.html").write_text(markdown_to_html(named_modules_md), encoding="utf-8")
    setup_summary.to_csv(LATEST_DIR / "signal_effectiveness_setup_leaderboard.csv", index=False)
    combo_summary.to_csv(LATEST_DIR / "signal_effectiveness_combo_leaderboard.csv", index=False)
    best_by_stock.to_csv(LATEST_DIR / "signal_effectiveness_stock_best_setups.csv", index=False)
    variant_summary.to_csv(LATEST_DIR / "signal_effectiveness_execution_variants.csv", index=False)
    cost_maps["setup_net"].to_csv(LATEST_DIR / "signal_effectiveness_cost_adjusted_setup.csv", index=False)
    cost_maps["cost_profile"].to_csv(LATEST_DIR / "signal_effectiveness_cost_profile.csv", index=False)
    cost_maps["volume_spike"].to_csv(LATEST_DIR / "signal_effectiveness_cost_volume_spike.csv", index=False)
    regime_maps["market_regime"].to_csv(LATEST_DIR / "signal_effectiveness_regime_market.csv", index=False)
    regime_maps["volatility"].to_csv(LATEST_DIR / "signal_effectiveness_regime_volatility.csv", index=False)
    regime_maps["breadth"].to_csv(LATEST_DIR / "signal_effectiveness_regime_breadth.csv", index=False)
    regime_maps["calendar_year"].to_csv(LATEST_DIR / "signal_effectiveness_regime_year.csv", index=False)
    regime_maps["theme_rs_year_breadth"].to_csv(LATEST_DIR / "signal_effectiveness_theme_rs_year_breadth.csv", index=False)
    regime_maps["vix_change"].to_csv(LATEST_DIR / "signal_effectiveness_regime_vix.csv", index=False)
    regime_maps["fno_postmortem"].to_csv(LATEST_DIR / "signal_effectiveness_fno_postmortem.csv", index=False)
    regime_maps["live_gate"].to_csv(LATEST_DIR / "signal_effectiveness_live_gate.csv", index=False)
    current_decision_queue.to_csv(LATEST_DIR / "signal_effectiveness_current_decision_queue.csv", index=False)
    latest.to_csv(LATEST_DIR / "signal_effectiveness_latest_candidates.csv", index=False)
    module_summary.to_csv(LATEST_DIR / "named_strategy_module_summary.csv", index=False)
    module_candidates.to_csv(LATEST_DIR / "named_strategy_module_candidates.csv", index=False)
    return paths


def build_markdown(
    *,
    events: pd.DataFrame,
    setup_summary: pd.DataFrame,
    combo_summary: pd.DataFrame,
    sector_setup_summary: pd.DataFrame,
    best_by_stock: pd.DataFrame,
    variant_summary: pd.DataFrame,
    module_summary: pd.DataFrame,
    cost_maps: dict[str, pd.DataFrame],
    regime_maps: dict[str, pd.DataFrame],
    current_decision_queue: pd.DataFrame,
    latest: pd.DataFrame,
    model_result: ModelResult,
    latest_trade_date: str,
    selected_symbols: list[str],
    args: argparse.Namespace,
    paths: dict[str, Path],
) -> str:
    date_min = events["date"].min().strftime("%Y-%m-%d") if not events.empty else "n/a"
    date_max = events["date"].max().strftime("%Y-%m-%d") if not events.empty else "n/a"
    explicit_universe = getattr(args, "universe_label", "") or "explicit symbols"
    universe_description = explicit_universe if args.symbols else f"top {args.top_n} liquid EQ symbols by latest turnover from PostgreSQL"
    universe_suffix = "; EOD/setup history from PostgreSQL." if args.symbols else "."
    lines = [
        "# Agent Adda Signal Effectiveness Research",
        "",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Latest PG EOD date: {latest_trade_date}",
        f"Universe: {len(selected_symbols)} symbols; labelled signal events: {len(events)}.",
        f"Signal window: {date_min} to {date_max}.",
        "",
        "## Strategy Spec",
        "",
        f"- Universe: {universe_description}{universe_suffix}",
        "- Timeframe: daily EOD signals; forward outcome measured on next trading sessions.",
        f"- Confirmation: setup must pass volume ratio >= {args.min_volume_ratio}, ADR >= {args.min_adr_pct}%, and turnover filter.",
        f"- Entry: signal-day close; stop: tighter of ATR({args.stop_atr}x) and recent 10-day low with a minimum risk floor.",
        f"- Target/exit: {args.target_r}R target, stop, or timeout after {args.horizon_days} sessions.",
        "- Regime context: Nifty, BankNifty, India VIX, breadth, and sector day-rank are joined from PostgreSQL.",
        "- F&O context: futures OI/basis and option PCR are joined from `derivatives.fno_eod`; current PCR/max-pain/buildup is joined from `derivatives.fno_signals` when available.",
        "- Combination setups are explicit named stacks, not hidden model interactions.",
        f"- Costs: net expectancy deducts estimated delivery/statutory cost plus liquidity/slippage profile converted into R by stop distance.",
        "- No-trade filters: low turnover, low ADR/volatility, weak volume confirmation, insufficient future bars.",
        "",
        "## Model Read",
        "",
    ]
    if model_result.enabled:
        auc = "n/a" if model_result.roc_auc is None else f"{model_result.roc_auc:.3f}"
        lines.extend(
            [
                f"- ML classifier: enabled, time split only. Train rows: {model_result.train_rows}; test rows: {model_result.test_rows}.",
                f"- Test accuracy: {model_result.accuracy:.3f}; ROC AUC: {auc}.",
                "- Use the model score as a ranking aid only; the historical setup stats remain the primary evidence.",
            ]
        )
    else:
        lines.append(f"- ML classifier: skipped. Reason: {model_result.reason}")
    lines.extend(
        [
            "",
            "## Setup Leaderboard",
            "",
            _table(setup_summary.head(20)),
            "",
            "## Combination Setup Leaderboard",
            "",
            _table(combo_summary.head(30)),
            "",
            "## Execution Variant Leaderboard",
            "",
            _table(variant_summary.head(30)),
            "",
            "## Named Strategy Modules",
            "",
            _table(
                module_summary.loc[
                    :,
                    [
                        column
                        for column in [
                            "module_name",
                            "module_gate",
                            "trades",
                            "win_rate_pct",
                            "expectancy_r",
                            "net_expectancy_r",
                            "net_profit_factor",
                            "sample_quality",
                            "source_setups",
                            "gate_reason",
                        ]
                        if column in module_summary.columns
                    ]
                ].head(20)
            ),
            "",
            f"- Standalone named strategy module report: `{paths.get('named_modules_html', '')}`",
            f"- Module summary CSV: `{paths.get('module_summary', '')}`",
            f"- Module candidates CSV: `{paths.get('module_candidates', '')}`",
            "",
            "## Best Setup Per Stock",
            "",
            _table(best_by_stock.head(60)),
            "",
            "## Sector Setup Read",
            "",
            _table(sector_setup_summary.head(40)),
            "",
            render_cost_adjusted_edge_markdown(cost_maps),
            "",
            render_regime_edge_markdown(regime_maps),
            "",
            "## Current Decision Queue",
            "",
            _table(
                current_decision_queue.loc[
                    :,
                    [
                        column
                        for column in [
                            "date",
                            "symbol",
                            "sector",
                            "setup",
                            "setup_type",
                            "action",
                            "decision_score",
                            "gross_decision_score",
                            "net_decision_score",
                            "instrument_read",
                            "close",
                            "cost_profile",
                            "estimated_cost_r",
                            "estimated_cost_pct",
                            "risk_pct",
                            "volume_ratio_20d",
                            "adr_pct_20",
                            "market_regime",
                            "breadth_positive_pct",
                            "sector_rank_1d",
                            "fno_pcr",
                            "fno_buildup",
                            "setup_expectancy_r",
                            "setup_net_expectancy_r",
                            "setup_avg_cost_r",
                            "setup_win_rate_pct",
                            "decision_reasons",
                        ]
                        if column in current_decision_queue.columns
                    ]
                ].head(40)
            ),
            "",
            "## Latest Signal Candidates",
            "",
            _table(
                latest.loc[
                    :,
                    [
                        column
                        for column in [
                            "date",
                            "symbol",
                            "sector",
                            "setup",
                            "setup_type",
                            "close",
                            "volume_ratio_20d",
                            "adr_pct_20",
                            "relative_strength",
                            "rsi_14",
                            "stage",
                            "market_regime",
                            "breadth_positive_pct",
                            "sector_rank_1d",
                            "cost_profile",
                            "estimated_cost_r",
                            "estimated_cost_pct",
                            "risk_pct",
                            "fno_pcr",
                            "fno_buildup",
                            "supertrend_state",
                            "model_target_prob",
                            "entry",
                            "stop",
                            "target",
                            "outcome",
                            "r_multiple",
                            "net_r_multiple",
                        ]
                        if column in latest.columns
                    ]
                ].head(40)
            ),
            "",
            "## Interpretation",
            "",
            "- The best stock/setup pairs are historical tendencies, not current buy calls.",
            "- The current decision queue ranks latest EOD candidates by net setup quality, estimated cost drag, sample size, market regime, breadth, sector participation, controlled volume confirmation, and F&O alignment.",
            "- Volume ratio is treated as a confirmation floor, not an unlimited positive. Above roughly 5-6x it becomes impact/slippage risk and reduces the net decision score.",
            "- Combo setups should be preferred only when they improve expectancy with enough trade count; small-sample combo rows remain provisional.",
            "- A setup is more credible when it has enough trades, positive net expectancy, controlled volume confirmation, and similar recent market context.",
            "- A high win rate with low trade count should be treated as provisional; use the sample-quality column before ranking ideas.",
            "- For live use, combine this with F&O liquidity, PCR/OI, broader market/VIX regime, and the intraday state machine.",
            "",
            "## Source Trail",
            "",
            "- PostgreSQL `market.equity_eod`: OHLCV, turnover, delivery.",
            "- PostgreSQL `scores.stage_snapshots`: sector, Stage, Supertrend, RSI, scores, relative strength.",
            "- PostgreSQL `market.index_eod`: Nifty, BankNifty, India VIX regime context.",
            "- PostgreSQL `derivatives.fno_eod` and `derivatives.fno_signals`: futures OI/basis, option PCR, max pain, buildup when available.",
            f"- Event CSV: `{paths['events']}`",
            f"- Setup leaderboard CSV: `{paths['setup_summary']}`",
            f"- Combination setup leaderboard CSV: `{paths['combo_summary']}`",
            f"- Stock best setups CSV: `{paths['best_by_stock']}`",
            f"- Execution variants CSV: `{paths['variant_summary']}`",
            f"- Named strategy modules report: `{paths.get('named_modules_html', '')}`",
            f"- Named strategy module summary CSV: `{paths.get('module_summary', '')}`",
            f"- Named strategy module candidates CSV: `{paths.get('module_candidates', '')}`",
            f"- Cost-adjusted setup CSV: `{paths['cost_setup']}`",
            f"- Cost profile CSV: `{paths['cost_profile']}`",
            f"- Volume spike cost CSV: `{paths['cost_volume_spike']}`",
            f"- Regime market leaderboard CSV: `{paths['regime_market']}`",
            f"- Regime volatility leaderboard CSV: `{paths['regime_volatility']}`",
            f"- Regime breadth leaderboard CSV: `{paths['regime_breadth']}`",
            f"- Regime calendar-year leaderboard CSV: `{paths['regime_year']}`",
            f"- Railways/PSU RS year/breadth CSV: `{paths['theme_rs_year_breadth']}`",
            f"- Regime VIX-change leaderboard CSV: `{paths['regime_vix']}`",
            f"- F&O post-mortem CSV: `{paths['fno_postmortem']}`",
            f"- Live gate recommendations CSV: `{paths['live_gate']}`",
            f"- Current decision queue CSV: `{paths['current_decision_queue']}`",
            "",
            "Research only. Not investment advice. Validate liquidity, spread, option premium, gap risk, and current market regime before acting.",
        ]
    )
    return "\n".join(lines) + "\n"


def build_named_strategy_modules_markdown(
    *,
    module_summary: pd.DataFrame,
    module_candidates: pd.DataFrame,
    latest_trade_date: str,
    selected_symbols: list[str],
    args: argparse.Namespace,
    paths: dict[str, Path],
) -> str:
    explicit_universe = getattr(args, "universe_label", "") or "explicit symbols"
    universe_description = explicit_universe if getattr(args, "symbols", None) else f"top {getattr(args, 'top_n', 'n/a')} liquid EQ symbols"
    lines = [
        "# Agent Adda Named Strategy Modules",
        "",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Latest PG EOD date: {latest_trade_date}",
        f"Universe: {len(selected_symbols)} symbols; {universe_description}.",
        f"Signal window starts: {getattr(args, 'start', 'n/a')}.",
        f"Outcome framework: {getattr(args, 'target_r', 'n/a')}R target, stop, or timeout after {getattr(args, 'horizon_days', 'n/a')} sessions.",
        "",
        "## Research Thesis",
        "",
        "- These modules are Agent Adda interpretations of public strategy frameworks, not exact reproductions.",
        "- Each module maps existing labelled setup families into a named research lens, then ranks evidence by historical net expectancy, sample quality, costs, and current candidate context.",
        "- The module gate is a research control: it can block, watch, wait for retest, allow half size, or mark a trade candidate when evidence is strong enough.",
        "",
        "## Module Leaderboard",
        "",
        _table(
            module_summary.loc[
                :,
                [
                    column
                    for column in [
                        "module_name",
                        "module_gate",
                        "trades",
                        "win_rate_pct",
                        "expectancy_r",
                        "net_expectancy_r",
                        "net_profit_factor",
                        "avg_cost_r",
                        "sample_quality",
                        "source_setups",
                        "gate_reason",
                    ]
                    if column in module_summary.columns
                ]
            ]
        ),
        "",
    ]

    summary_by_id = (
        {str(row["module_id"]): row for _, row in module_summary.iterrows()}
        if not module_summary.empty and "module_id" in module_summary.columns
        else {}
    )
    for module in STRATEGY_MODULES:
        row = summary_by_id.get(module.module_id)
        lines.extend(
            [
                f"## {module.name}",
                "",
                f"- Module ID: `{module.module_id}`",
                f"- Inspiration: {module.inspiration}",
                f"- Purpose: {module.purpose}",
                f"- Mapped setup families: {', '.join(module.mapped_setups)}",
                "",
                "### Entry Rules",
                "",
            ]
        )
        lines.extend(f"- {rule}" for rule in module.entry_rules)
        lines.extend(["", "### No-Trade Conditions", ""])
        lines.extend(f"- {rule}" for rule in module.no_trade_rules)
        lines.extend(["", "### Failure Modes", ""])
        lines.extend(f"- {mode}" for mode in module.failure_modes)
        lines.extend(["", "### Backtest Evidence", ""])
        if row is None:
            lines.append("_No mapped historical setup rows were available for this module in this run._")
        else:
            evidence = pd.DataFrame([row]).loc[
                :,
                [
                    column
                    for column in [
                        "module_gate",
                        "trades",
                        "win_rate_pct",
                        "expectancy_r",
                        "net_expectancy_r",
                        "net_profit_factor",
                        "avg_cost_r",
                        "sample_quality",
                        "source_setups",
                        "gate_reason",
                    ]
                    if column in pd.DataFrame([row]).columns
                ],
            ]
            lines.append(_table(evidence))
        lines.append("")

    candidate_columns = [
        column
        for column in [
            "module_name",
            "module_gate",
            "symbol",
            "sector",
            "setup",
            "action",
            "decision_score",
            "close",
            "cost_profile",
            "estimated_cost_r",
            "market_regime",
            "breadth_positive_pct",
            "fno_pcr",
            "fno_buildup",
            "setup_net_expectancy_r",
            "setup_win_rate_pct",
            "gate_reason",
            "decision_reasons",
        ]
        if column in module_candidates.columns
    ]
    lines.extend(
        [
            "## Current Module Candidates",
            "",
            _table(module_candidates.loc[:, candidate_columns].head(80) if candidate_columns else module_candidates),
            "",
            "## Diagnostics",
            "",
        ]
    )
    if module_candidates.empty:
        lines.append("- No current module candidates were available in this run.")
    else:
        lines.append(f"- Current module candidate rows: {len(module_candidates)}.")
    if module_summary.empty:
        lines.append("- No module summary rows were produced; check setup mappings and signal-event coverage.")
    else:
        lines.append(f"- Module summary rows: {len(module_summary)}.")
    lines.extend(
        [
            "",
            "## Source Trail",
            "",
            f"- Module summary CSV: `{paths.get('module_summary', '')}`",
            f"- Module candidates CSV: `{paths.get('module_candidates', '')}`",
            "- Base evidence comes from the Agent Adda EOD signal-effectiveness research pipeline.",
            "- Strategy definitions come from `terminal/strategy_modules.py`.",
            "",
            "Research only. Not investment advice. Validate liquidity, spread, option premium, gap risk, and current market regime before acting. Agent Adda is not SEBI registered.",
        ]
    )
    return "\n".join(lines) + "\n"


def markdown_to_html(markdown: str) -> str:
    body_lines: list[str] = []
    in_table = False
    for line in markdown.splitlines():
        if line.startswith("# "):
            if in_table:
                body_lines.append("</table>")
                in_table = False
            body_lines.append(f"<h1>{html.escape(line[2:])}</h1>")
        elif line.startswith("## "):
            if in_table:
                body_lines.append("</table>")
                in_table = False
            body_lines.append(f"<h2>{html.escape(line[3:])}</h2>")
        elif line.startswith("### "):
            if in_table:
                body_lines.append("</table>")
                in_table = False
            body_lines.append(f"<h3>{html.escape(line[4:])}</h3>")
        elif line.startswith("- "):
            if in_table:
                body_lines.append("</table>")
                in_table = False
            body_lines.append(f"<p class='bullet'>- {html.escape(line[2:])}</p>")
        elif line.startswith("|") and line.endswith("|"):
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if set("".join(cells)) <= {"-", ":"}:
                continue
            tag = "th" if not in_table else "td"
            if not in_table:
                body_lines.append("<table>")
                in_table = True
            body_lines.append("<tr>" + "".join(f"<{tag}>{html.escape(cell)}</{tag}>" for cell in cells) + "</tr>")
        elif line.strip():
            if in_table:
                body_lines.append("</table>")
                in_table = False
            body_lines.append(f"<p>{html.escape(line)}</p>")
        else:
            if in_table:
                body_lines.append("</table>")
                in_table = False
    if in_table:
        body_lines.append("</table>")
    return """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Agent Adda Signal Effectiveness Research</title>
<style>
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;margin:0;background:#f6f8fb;color:#14213d}
main{max-width:1320px;margin:0 auto;padding:28px}
h1{font-size:30px;margin:0 0 16px} h2{font-size:20px;margin:30px 0 12px} h3{font-size:15px;margin:22px 0 8px;color:#24415f}
p{line-height:1.45;margin:8px 0}.bullet{margin-left:14px}
table{border-collapse:collapse;width:100%;font-size:12px;background:#fff;border:1px solid #d8dee9;margin:10px 0 22px}
th,td{padding:8px 10px;border-bottom:1px solid #e6ebf2;text-align:left;vertical-align:top;white-space:nowrap}
th{background:#10233f;color:#fff;font-weight:700;position:sticky;top:0}
tr:nth-child(even) td{background:#f9fbfd}
code{background:#edf2f7;padding:2px 4px;border-radius:4px}
</style>
</head>
<body><main>
""" + "\n".join(body_lines) + "\n</main></body></html>\n"


def _table(frame: pd.DataFrame) -> str:
    if frame is None or frame.empty:
        return "_No rows._"
    out = frame.copy()
    for column in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[column]):
            out[column] = out[column].dt.strftime("%Y-%m-%d")
        elif pd.api.types.is_float_dtype(out[column]):
            out[column] = out[column].map(lambda value: "" if pd.isna(value) else f"{float(value):.3f}".rstrip("0").rstrip("."))
        else:
            out[column] = out[column].map(lambda value: "" if pd.isna(value) else str(value))
    columns = [str(column) for column in out.columns]
    lines = [
        "| " + " | ".join(_md_cell(column) for column in columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in out.itertuples(index=False):
        lines.append("| " + " | ".join(_md_cell(value) for value in row) + " |")
    return "\n".join(lines)


def _md_cell(value: Any) -> str:
    text = "" if pd.isna(value) else str(value)
    return text.replace("|", "/").replace("\n", " ").strip()


def _num(value: Any) -> float:
    try:
        out = float(value)
        return out if math.isfinite(out) else float("nan")
    except Exception:
        return float("nan")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Research setup effectiveness per stock from Agent Adda PostgreSQL EOD data.")
    parser.add_argument("--dsn", default=None, help="PostgreSQL DSN. Defaults to AGENT_ADDA_PG_DSN/PG_DSN.")
    parser.add_argument("--symbols", default=None, help="Comma-separated symbols. Default uses latest liquid universe.")
    parser.add_argument("--universe-label", default="", help="Human-readable label for explicit --symbols report metadata.")
    parser.add_argument("--top-n", type=int, default=300, help="Top liquid symbols when --symbols is omitted.")
    parser.add_argument("--start", default="2025-11-15", help="First signal date.")
    parser.add_argument("--lookback", default="2025-10-13", help="Indicator lookback date.")
    parser.add_argument("--end", default=None, help="Optional last EOD date.")
    parser.add_argument("--horizon-days", type=int, default=10)
    parser.add_argument("--stop-atr", type=float, default=1.5)
    parser.add_argument("--target-r", type=float, default=2.0)
    parser.add_argument("--min-volume-ratio", type=float, default=1.2)
    parser.add_argument("--min-adr-pct", type=float, default=1.2)
    parser.add_argument("--min-turnover-cr", type=float, default=5.0)
    parser.add_argument("--min-price", type=float, default=20.0)
    parser.add_argument("--max-darvas-width-pct", type=float, default=12.0)
    parser.add_argument("--min-trades", type=int, default=3)
    parser.add_argument("--min-regime-trades", type=int, default=50, help="Minimum trades per regime/bucket row in edge-map tables.")
    parser.add_argument(
        "--include-open-outcomes",
        action="store_true",
        help="Include signals without a full forward horizon. Default excludes them from stats/model training.",
    )
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    dsn = args.dsn or _dsn()
    requested = _parse_symbols(args.symbols)
    data, latest_trade_date, selected_symbols = load_pg_data(
        dsn=dsn,
        symbols=requested,
        start=args.start,
        lookback=args.lookback,
        end=args.end,
        top_n=args.top_n,
        min_price=args.min_price,
        min_turnover_cr=args.min_turnover_cr,
    )
    if data.empty:
        raise SystemExit("No PostgreSQL EOD data loaded for requested universe.")
    data = add_indicators(data)
    events = generate_signal_events(
        data,
        start=args.start,
        min_volume_ratio=args.min_volume_ratio,
        max_darvas_width_pct=args.max_darvas_width_pct,
        min_adr_pct=args.min_adr_pct,
        min_turnover_cr=args.min_turnover_cr,
    )
    labelled = label_outcomes(
        events,
        data,
        horizon_days=args.horizon_days,
        stop_atr=args.stop_atr,
        target_r=args.target_r,
        include_open_outcomes=args.include_open_outcomes,
    )
    labelled = add_execution_costs(labelled, stop_atr=args.stop_atr)
    variant_events = build_execution_variant_events(events)
    variant_labelled = label_outcomes(
        variant_events,
        data,
        horizon_days=args.horizon_days,
        stop_atr=args.stop_atr,
        target_r=args.target_r,
        include_open_outcomes=args.include_open_outcomes,
    )
    variant_labelled = add_execution_costs(variant_labelled, stop_atr=args.stop_atr)
    labelled, model_result = train_model(labelled)
    setup_summary, combo_summary, sector_setup_summary, best_by_stock, latest = summarize(labelled, min_trades=args.min_trades)
    variant_summary = (
        _agg_group(variant_labelled.groupby(["setup", "entry_variant"], dropna=False)).sort_values(
            [
                "net_expectancy_r" if "net_r_multiple" in variant_labelled.columns else "expectancy_r",
                "win_rate_pct",
                "trades",
            ],
            ascending=[False, False, False],
        )
        if not variant_labelled.empty
        else pd.DataFrame()
    )
    current_decision_queue = build_current_decision_queue(
        data=data,
        setup_summary=setup_summary,
        best_by_stock=best_by_stock,
        min_volume_ratio=args.min_volume_ratio,
        max_darvas_width_pct=args.max_darvas_width_pct,
        min_adr_pct=args.min_adr_pct,
        min_turnover_cr=args.min_turnover_cr,
        stop_atr=args.stop_atr,
    )
    paths = write_outputs(
        events=labelled,
        setup_summary=setup_summary,
        combo_summary=combo_summary,
        sector_setup_summary=sector_setup_summary,
        best_by_stock=best_by_stock,
        variant_summary=variant_summary,
        current_decision_queue=current_decision_queue,
        latest=latest,
        model_result=model_result,
        latest_trade_date=latest_trade_date,
        selected_symbols=selected_symbols,
        args=args,
    )
    print("Signal effectiveness research complete")
    print(f"Symbols: {len(selected_symbols)}")
    print(f"Labelled events: {len(labelled)}")
    print(f"Markdown: {paths['md']}")
    print(f"HTML: {paths['html']}")
    print(f"Named modules: {paths['named_modules_html']}")
    print(f"Latest: {LATEST_DIR / 'signal_effectiveness.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
