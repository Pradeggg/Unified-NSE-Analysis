"""Historical intraday indicator study for F&O and broad-market universes.

The study is intentionally research-first: it builds repeatable indicator
features from intraday OHLCV bars, replays a small registry of setup families,
and writes a leaderboard report that can be used to tune live Agent Adda
intraday monitors.
"""

from __future__ import annotations

import html
import json
import math
import shutil
import warnings
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from terminal.intraday import compute_all, compute_vwap
from terminal.intraday_storage import PG_DSN
from terminal.edge_knowledge import (
    build_edge_nodes,
    fetch_persistence_counts,
    get_code_version,
    make_refresh_run,
    persist_edge_nodes,
)


IST = timezone(timedelta(hours=5, minutes=30))


@dataclass(frozen=True)
class StudyConfig:
    universe: str = "fno"
    symbols: tuple[str, ...] = ()
    timeframes: tuple[str, ...] = ("5m", "15m")
    start: str | None = None
    end: str | None = None
    max_symbols: int = 75
    max_hold_bars: int = 12
    slippage_bps: float = 3.0
    brokerage_bps: float = 2.0
    min_bars: int = 80
    data_path: Path | None = None
    output_dir: Path = Path("reports/research")
    include_fno_context: bool = True
    promote_min_trades: int = 10
    promote_min_expectancy_r: float = 0.05
    promote_min_profit_factor: float = 1.10
    watch_min_trades: int = 5
    watch_min_expectancy_r: float = 0.0
    persist_edges: bool = False


@dataclass(frozen=True)
class SetupSignal:
    setup: str
    direction: str
    entry: float
    stop: float
    target: float
    note: str


def _num(value: Any) -> float | None:
    try:
        if value is None:
            return None
        out = float(value)
        return None if math.isnan(out) else out
    except (TypeError, ValueError):
        return None


def _fmt(value: Any, digits: int = 2) -> str:
    number = _num(value)
    if number is None:
        return "-"
    return f"{number:.{digits}f}"


def _safe_pct(value: Any) -> str:
    number = _num(value)
    if number is None:
        return "-"
    return f"{number:.1f}%"


def _normalise_ohlcv(frame: pd.DataFrame) -> pd.DataFrame:
    col_map: dict[str, str] = {}
    for col in frame.columns:
        key = str(col).strip().lower()
        if key in {"timestamp", "datetime", "date", "time"}:
            col_map[col] = "timestamp"
        elif key == "symbol":
            col_map[col] = "symbol"
        elif key == "timeframe":
            col_map[col] = "timeframe"
        elif key in {"open", "open_price"}:
            col_map[col] = "Open"
        elif key in {"high", "high_price"}:
            col_map[col] = "High"
        elif key in {"low", "low_price"}:
            col_map[col] = "Low"
        elif key in {"close", "last", "last_price"}:
            col_map[col] = "Close"
        elif key in {"volume", "tottrdqty", "qty"}:
            col_map[col] = "Volume"
    out = frame.rename(columns=col_map).copy()
    required = {"timestamp", "symbol", "Open", "High", "Low", "Close"}
    missing = required - set(out.columns)
    if missing:
        raise ValueError("OHLCV data missing required columns: " + ", ".join(sorted(missing)))
    if "timeframe" not in out.columns:
        out["timeframe"] = "15m"
    if "Volume" not in out.columns:
        out["Volume"] = 0
    out["timestamp"] = pd.to_datetime(out["timestamp"], errors="coerce")
    out["symbol"] = out["symbol"].astype(str).str.strip().str.upper()
    out["timeframe"] = out["timeframe"].astype(str).str.strip().str.lower()
    for col in ("Open", "High", "Low", "Close", "Volume"):
        out[col] = pd.to_numeric(out[col], errors="coerce")
    return out.dropna(subset=["timestamp", "symbol", "Open", "High", "Low", "Close"]).sort_values(
        ["symbol", "timeframe", "timestamp"]
    )


def _connect_pg(dsn: str | None = None):
    import psycopg2

    return psycopg2.connect(dsn or PG_DSN)


def resolve_universe_symbols(config: StudyConfig, *, dsn: str | None = None) -> tuple[list[str], list[str]]:
    if config.symbols:
        return [s.strip().upper() for s in config.symbols if s.strip()], ["explicit symbols"]

    notes: list[str] = []
    universe_key = config.universe.lower().replace("&", "and").replace(" ", "")
    if universe_key in {"fno", "fo", "fando", "derivatives"}:
        sql = """
            WITH latest_fno AS (
                SELECT DISTINCT symbol
                FROM derivatives.fno_eod
                WHERE trade_date = (SELECT max(trade_date) FROM derivatives.fno_eod)
                  AND instrument IN ('STF','IDF','FUTSTK','FUTIDX')
            ),
            intraday_coverage AS (
                SELECT symbol, COUNT(*) AS bars, MAX(timestamp) AS latest_bar
                FROM intraday.ohlcv_bars
                WHERE timeframe = ANY(%s)
                GROUP BY symbol
            )
            SELECT f.symbol
            FROM latest_fno f
            LEFT JOIN intraday_coverage i USING (symbol)
            ORDER BY COALESCE(i.bars, 0) DESC, i.latest_bar DESC NULLS LAST, f.symbol
        """
        try:
            with _connect_pg(dsn) as conn:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", UserWarning)
                    frame = pd.read_sql_query(sql, conn, params=(list(config.timeframes),))
            symbols = frame["symbol"].astype(str).str.upper().tolist()
            if symbols:
                notes.append("derivatives.fno_eod latest futures universe ordered by intraday coverage")
                return symbols[: config.max_symbols], notes
        except Exception as exc:
            notes.append(f"PostgreSQL F&O universe unavailable: {type(exc).__name__}: {exc}")

        fallback = Path("data/fno_signals.csv")
        if fallback.exists():
            frame = pd.read_csv(fallback)
            if "symbol" in frame.columns:
                symbols = sorted(set(frame["symbol"].astype(str).str.upper()))
            else:
                symbols = sorted(set(frame.iloc[:, 0].astype(str).str.upper()))
            notes.append("fallback data/fno_signals.csv universe")
            return symbols[: config.max_symbols], notes

    mapping = Path("data/index_stock_mapping.csv")
    if mapping.exists():
        frame = pd.read_csv(mapping)
        index_col = next((c for c in frame.columns if c.upper() == "INDEX_NAME"), None)
        sym_col = next((c for c in frame.columns if c.upper() == "STOCK_SYMBOL"), None)
        if index_col and sym_col:
            wanted = config.universe.upper().replace("_", " ")
            subset = frame[frame[index_col].astype(str).str.upper() == wanted]
            symbols = sorted(set(subset[sym_col].astype(str).str.upper()))
            if symbols:
                notes.append(f"index_stock_mapping.csv universe: {config.universe}")
                return symbols[: config.max_symbols], notes

    default_symbols = ["NIFTY", "BANKNIFTY", "RELIANCE", "HDFCBANK", "ICICIBANK"]
    notes.append("fallback liquid symbols; requested universe was not resolvable")
    return default_symbols[: config.max_symbols], notes


def load_intraday_bars(config: StudyConfig, *, dsn: str | None = None) -> tuple[pd.DataFrame, list[str]]:
    if config.data_path:
        frame = _normalise_ohlcv(pd.read_csv(config.data_path))
        return frame, [f"CSV: {config.data_path}"]

    symbols, notes = resolve_universe_symbols(config, dsn=dsn)
    if not symbols:
        return pd.DataFrame(), notes + ["no symbols resolved"]

    params: list[Any] = [list(symbols), list(config.timeframes)]
    where = ["symbol = ANY(%s)", "timeframe = ANY(%s)"]
    if config.start:
        where.append("timestamp >= %s")
        params.append(config.start)
    if config.end:
        where.append("timestamp <= %s")
        params.append(config.end)
    sql = f"""
        SELECT symbol, timeframe, timestamp, open, high, low, close, volume
        FROM intraday.ohlcv_bars
        WHERE {' AND '.join(where)}
        ORDER BY symbol, timeframe, timestamp
    """
    try:
        with _connect_pg(dsn) as conn:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                frame = pd.read_sql_query(sql, conn, params=tuple(params))
        if frame.empty:
            return frame, notes + ["intraday.ohlcv_bars returned no rows"]
        return _normalise_ohlcv(frame), notes + ["PostgreSQL intraday.ohlcv_bars"]
    except Exception as exc:
        return pd.DataFrame(), notes + [f"PostgreSQL intraday bars unavailable: {type(exc).__name__}: {exc}"]


def _date_for_join(series: pd.Series) -> pd.Series:
    ts = pd.to_datetime(series, errors="coerce")
    try:
        if getattr(ts.dt, "tz", None) is not None:
            ts = ts.dt.tz_convert("Asia/Kolkata")
    except (TypeError, AttributeError):
        pass
    return ts.dt.date.astype(str)


def load_fno_daily_context(
    symbols: list[str] | tuple[str, ...],
    *,
    start: str | None = None,
    end: str | None = None,
    dsn: str | None = None,
) -> tuple[pd.DataFrame, list[str]]:
    """Load historical daily option-chain context for symbols from derivatives.fno_eod.

    This is daily EOD options evidence, not intraday option-chain snapshots. It is
    still useful for validating whether an intraday rule behaved differently
    under put-heavy, balanced, or call-heavy positioning regimes.
    """
    syms = sorted({str(s).strip().upper() for s in symbols if str(s).strip()})
    if not syms:
        return pd.DataFrame(), ["F&O context skipped: no symbols"]
    params: list[Any] = [syms]
    filters = ["e.symbol = ANY(%s)", "e.option_type IN ('CE','PE')", "e.expiry_date >= e.trade_date"]
    if start:
        filters.append("e.trade_date >= %s")
        params.append(start)
    if end:
        filters.append("e.trade_date <= %s")
        params.append(end)
    sql = f"""
        WITH nearest AS (
            SELECT e.symbol, e.trade_date, min(e.expiry_date) AS expiry_date
            FROM derivatives.fno_eod e
            WHERE {' AND '.join(filters)}
            GROUP BY e.symbol, e.trade_date
        )
        SELECT
            e.trade_date::text AS trade_date,
            e.symbol,
            e.expiry_date::text AS expiry_date,
            e.option_type,
            e.strike,
            e.underlying_price,
            e.open_interest,
            e.oi_change,
            e.volume
        FROM derivatives.fno_eod e
        JOIN nearest n
          ON n.symbol = e.symbol
         AND n.trade_date = e.trade_date
         AND n.expiry_date = e.expiry_date
        WHERE e.option_type IN ('CE','PE')
        ORDER BY e.symbol, e.trade_date, e.expiry_date, e.strike
    """
    try:
        with _connect_pg(dsn) as conn:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                raw = pd.read_sql_query(sql, conn, params=tuple(params))
    except Exception as exc:
        return pd.DataFrame(), [f"F&O context unavailable: {type(exc).__name__}: {exc}"]
    if raw.empty:
        return pd.DataFrame(), ["F&O context unavailable: derivatives.fno_eod returned no option rows"]

    rows: list[dict[str, Any]] = []
    for (symbol, trade_date, expiry), grp in raw.groupby(["symbol", "trade_date", "expiry_date"], sort=False):
        calls = grp[grp["option_type"] == "CE"].copy()
        puts = grp[grp["option_type"] == "PE"].copy()
        total_ce = float(pd.to_numeric(calls["open_interest"], errors="coerce").fillna(0).sum())
        total_pe = float(pd.to_numeric(puts["open_interest"], errors="coerce").fillna(0).sum())
        pcr = total_pe / total_ce if total_ce else None
        ce_wall = None
        pe_floor = None
        if not calls.empty:
            ce_wall = float(calls.sort_values("open_interest", ascending=False).iloc[0]["strike"])
        if not puts.empty:
            pe_floor = float(puts.sort_values("open_interest", ascending=False).iloc[0]["strike"])
        strikes = sorted(set(pd.to_numeric(grp["strike"], errors="coerce").dropna().astype(float).tolist()))
        ce_map = dict(zip(pd.to_numeric(calls["strike"], errors="coerce").astype(float), pd.to_numeric(calls["open_interest"], errors="coerce").fillna(0).astype(float)))
        pe_map = dict(zip(pd.to_numeric(puts["strike"], errors="coerce").astype(float), pd.to_numeric(puts["open_interest"], errors="coerce").fillna(0).astype(float)))
        max_pain = None
        min_pain = float("inf")
        for settlement in strikes:
            pain = sum(ce_map.get(k, 0.0) * max(0.0, settlement - k) for k in strikes)
            pain += sum(pe_map.get(k, 0.0) * max(0.0, k - settlement) for k in strikes)
            if pain < min_pain:
                min_pain = pain
                max_pain = settlement
        underlying_vals = pd.to_numeric(grp["underlying_price"], errors="coerce").dropna()
        underlying = float(underlying_vals.iloc[-1]) if not underlying_vals.empty else None
        if pcr is None:
            regime = "unknown"
        elif pcr >= 1.15:
            regime = "put-heavy"
        elif pcr < 0.80:
            regime = "call-heavy"
        else:
            regime = "balanced"
        rows.append(
            {
                "symbol": symbol,
                "trade_date": str(trade_date),
                "expiry_date": str(expiry),
                "pcr": pcr,
                "pcr_regime": regime,
                "max_pain": max_pain,
                "underlying": underlying,
                "max_pain_distance_pct": ((underlying - max_pain) / underlying * 100) if underlying and max_pain else None,
                "ce_wall": ce_wall,
                "pe_floor": pe_floor,
                "total_ce_oi": total_ce,
                "total_pe_oi": total_pe,
            }
        )
    return pd.DataFrame(rows), ["derivatives.fno_eod nearest-expiry daily options context"]


def _add_adx(frame: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    out = frame.copy()
    high = out["High"]
    low = out["Low"]
    close = out["Close"]
    plus_dm = (high.diff()).where(lambda s: (s > -low.diff()) & (s > 0), 0.0)
    minus_dm = (-low.diff()).where(lambda s: (s > high.diff()) & (s > 0), 0.0)
    tr = pd.concat(
        [(high - low), (high - close.shift()).abs(), (low - close.shift()).abs()],
        axis=1,
    ).max(axis=1)
    atr = tr.ewm(alpha=1 / period, adjust=False).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr.replace(0, float("nan"))
    minus_di = 100 * minus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr.replace(0, float("nan"))
    dx = ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, float("nan"))) * 100
    out["ADX"] = dx.ewm(alpha=1 / period, adjust=False).mean()
    return out


def prepare_features(frame: pd.DataFrame) -> pd.DataFrame:
    frame = _normalise_ohlcv(frame)
    parts: list[pd.DataFrame] = []
    for (_, _), grp in frame.groupby(["symbol", "timeframe"], sort=False):
        g = grp.sort_values("timestamp").copy()
        g = g.set_index("timestamp", drop=False)
        g = compute_all(g)
        g = compute_vwap(g)
        g = _add_adx(g)
        g["volume_sma20"] = g["Volume"].rolling(20).mean()
        g["session"] = pd.to_datetime(g["timestamp"]).dt.date
        g["bar_in_session"] = g.groupby("session").cumcount()
        orb = g[g["bar_in_session"] < 3].groupby("session").agg(orb_high=("High", "max"), orb_low=("Low", "min"))
        g = g.join(orb, on="session")
        parts.append(g.reset_index(drop=True))
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def _risk_targets(row: pd.Series, direction: str, risk_mult: float = 1.0, reward_mult: float = 1.8) -> tuple[float, float]:
    entry = float(row["Close"])
    atr = _num(row.get("ATR")) or max(entry * 0.003, 0.05)
    risk = max(atr * risk_mult, entry * 0.0015)
    if direction == "LONG":
        return entry - risk, entry + risk * reward_mult
    return entry + risk, entry - risk * reward_mult


def _signal_ema_supertrend(row: pd.Series, prev: pd.Series | None) -> SetupSignal | None:
    close = _num(row.get("Close"))
    if close is None:
        return None
    e21, e50 = _num(row.get("EMA21")), _num(row.get("EMA50"))
    st_dir, rsi, adx = _num(row.get("Supertrend_dir")), _num(row.get("RSI")), _num(row.get("ADX"))
    if e21 and e50 and st_dir == 1 and close > e21 > e50 and (rsi or 0) >= 45 and (adx or 0) >= 18:
        stop, target = _risk_targets(row, "LONG", 1.1, 1.9)
        return SetupSignal("EMA + Supertrend", "LONG", close, stop, target, "EMA stack, Supertrend and ADX agree")
    if e21 and e50 and st_dir == -1 and close < e21 < e50 and (rsi or 100) <= 55 and (adx or 0) >= 18:
        stop, target = _risk_targets(row, "SHORT", 1.1, 1.9)
        return SetupSignal("EMA + Supertrend", "SHORT", close, stop, target, "EMA stack, Supertrend and ADX agree")
    return None


def _signal_macd_momentum(row: pd.Series, prev: pd.Series | None) -> SetupSignal | None:
    if prev is None:
        return None
    close = _num(row.get("Close"))
    macd, sig, hist = _num(row.get("MACD")), _num(row.get("MACD_signal")), _num(row.get("MACD_hist"))
    prev_hist = _num(prev.get("MACD_hist"))
    vol = _num(row.get("Volume")) or 0
    vol_avg = _num(row.get("volume_sma20")) or 0
    if close is None or macd is None or sig is None or hist is None or prev_hist is None:
        return None
    if macd > sig and hist > 0 and prev_hist <= hist and vol_avg and vol >= vol_avg * 1.05 and close > (_num(row.get("EMA21")) or close):
        stop, target = _risk_targets(row, "LONG", 1.0, 1.7)
        return SetupSignal("MACD + Volume Momentum", "LONG", close, stop, target, "MACD histogram rising with relative volume")
    if macd < sig and hist < 0 and prev_hist >= hist and vol_avg and vol >= vol_avg * 1.05 and close < (_num(row.get("EMA21")) or close):
        stop, target = _risk_targets(row, "SHORT", 1.0, 1.7)
        return SetupSignal("MACD + Volume Momentum", "SHORT", close, stop, target, "MACD histogram falling with relative volume")
    return None


def _signal_vwap_reclaim(row: pd.Series, prev: pd.Series | None) -> SetupSignal | None:
    if prev is None:
        return None
    close, prev_close = _num(row.get("Close")), _num(prev.get("Close"))
    vwap, prev_vwap = _num(row.get("VWAP")), _num(prev.get("VWAP"))
    rsi = _num(row.get("RSI")) or 50
    if None in {close, prev_close, vwap, prev_vwap}:
        return None
    if prev_close <= prev_vwap and close > vwap and 40 <= rsi <= 70:
        stop, target = _risk_targets(row, "LONG", 0.9, 1.6)
        return SetupSignal("VWAP Reclaim", "LONG", close, stop, target, "Price reclaimed rolling VWAP with RSI confirmation")
    if prev_close >= prev_vwap and close < vwap and 30 <= rsi <= 60:
        stop, target = _risk_targets(row, "SHORT", 0.9, 1.6)
        return SetupSignal("VWAP Loss", "SHORT", close, stop, target, "Price lost rolling VWAP with RSI confirmation")
    return None


def _signal_rsi_reversion(row: pd.Series, prev: pd.Series | None) -> SetupSignal | None:
    close = _num(row.get("Close"))
    rsi = _num(row.get("RSI"))
    lower, upper = _num(row.get("BB_lower")), _num(row.get("BB_upper"))
    if close is None or rsi is None:
        return None
    if lower and close <= lower and rsi < 32:
        stop, target = _risk_targets(row, "LONG", 0.9, 1.25)
        return SetupSignal("RSI / Bollinger Reversion", "LONG", close, stop, target, "Oversold extension into lower Bollinger band")
    if upper and close >= upper and rsi > 68:
        stop, target = _risk_targets(row, "SHORT", 0.9, 1.25)
        return SetupSignal("RSI / Bollinger Reversion", "SHORT", close, stop, target, "Overbought extension into upper Bollinger band")
    return None


def _signal_orb_vwap(row: pd.Series, prev: pd.Series | None) -> SetupSignal | None:
    if prev is None or int(row.get("bar_in_session") or 0) <= 3:
        return None
    close, prev_close = _num(row.get("Close")), _num(prev.get("Close"))
    orb_high, orb_low, vwap = _num(row.get("orb_high")), _num(row.get("orb_low")), _num(row.get("VWAP"))
    if None in {close, prev_close, orb_high, orb_low, vwap}:
        return None
    if prev_close <= orb_high < close and close > vwap:
        stop = orb_low
        target = close + max((orb_high - orb_low) * 1.5, close - stop)
        if stop < close < target:
            return SetupSignal("ORB + VWAP", "LONG", close, stop, target, "Opening range breakout above VWAP")
    if prev_close >= orb_low > close and close < vwap:
        stop = orb_high
        target = close - max((orb_high - orb_low) * 1.5, stop - close)
        if target < close < stop:
            return SetupSignal("ORB + VWAP", "SHORT", close, stop, target, "Opening range breakdown below VWAP")
    return None


SIGNAL_REGISTRY: tuple[Callable[[pd.Series, pd.Series | None], SetupSignal | None], ...] = (
    _signal_ema_supertrend,
    _signal_macd_momentum,
    _signal_vwap_reclaim,
    _signal_rsi_reversion,
    _signal_orb_vwap,
)


def _exit_trade(rows: pd.DataFrame, start_idx: int, signal: SetupSignal, max_hold_bars: int) -> dict[str, Any]:
    side = 1 if signal.direction == "LONG" else -1
    last_idx = min(start_idx + max_hold_bars, len(rows) - 1)
    exit_price = signal.entry
    exit_ts = rows.iloc[start_idx]["timestamp"]
    reason = "max_hold"
    mfe = 0.0
    mae = 0.0
    for j in range(start_idx + 1, last_idx + 1):
        row = rows.iloc[j]
        high = float(row["High"])
        low = float(row["Low"])
        favorable = (high - signal.entry) if side == 1 else (signal.entry - low)
        adverse = (signal.entry - low) if side == 1 else (high - signal.entry)
        mfe = max(mfe, favorable)
        mae = max(mae, adverse)
        if signal.direction == "LONG":
            if low <= signal.stop:
                exit_price, exit_ts, reason = signal.stop, row["timestamp"], "stop"
                break
            if high >= signal.target:
                exit_price, exit_ts, reason = signal.target, row["timestamp"], "target"
                break
        else:
            if high >= signal.stop:
                exit_price, exit_ts, reason = signal.stop, row["timestamp"], "stop"
                break
            if low <= signal.target:
                exit_price, exit_ts, reason = signal.target, row["timestamp"], "target"
                break
        exit_price, exit_ts = float(row["Close"]), row["timestamp"]

    risk = abs(signal.entry - signal.stop)
    pnl = side * (exit_price - signal.entry)
    return {
        "exit_ts": exit_ts,
        "exit_price": exit_price,
        "exit_reason": reason,
        "pnl": pnl,
        "r_multiple_raw": pnl / risk if risk else 0.0,
        "mfe_r": mfe / risk if risk else 0.0,
        "mae_r": mae / risk if risk else 0.0,
        "hold_bars": max(1, min(last_idx, j if "j" in locals() else last_idx) - start_idx),
    }


def run_indicator_backtest(features: pd.DataFrame, config: StudyConfig) -> tuple[pd.DataFrame, pd.DataFrame]:
    trades: list[dict[str, Any]] = []
    total_cost_bps = config.slippage_bps * 2 + config.brokerage_bps * 2
    for (symbol, timeframe), grp in features.groupby(["symbol", "timeframe"], sort=False):
        rows = grp.sort_values("timestamp").reset_index(drop=True)
        if len(rows) < config.min_bars:
            continue
        cooldown_until: dict[str, int] = {}
        for i in range(55, len(rows) - 1):
            prev = rows.iloc[i - 1] if i > 0 else None
            row = rows.iloc[i]
            for signal_fn in SIGNAL_REGISTRY:
                signal = signal_fn(row, prev)
                if signal is None:
                    continue
                key = f"{signal.setup}:{signal.direction}"
                if i <= cooldown_until.get(key, -1):
                    continue
                result = _exit_trade(rows, i, signal, config.max_hold_bars)
                cost_r = (signal.entry * total_cost_bps / 10000) / max(abs(signal.entry - signal.stop), 1e-9)
                r_after_cost = result["r_multiple_raw"] - cost_r
                trades.append(
                    {
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "setup": signal.setup,
                        "direction": signal.direction,
                        "entry_ts": row["timestamp"],
                        "entry": signal.entry,
                        "stop": signal.stop,
                        "target": signal.target,
                        "exit_ts": result["exit_ts"],
                        "exit": result["exit_price"],
                        "exit_reason": result["exit_reason"],
                        "r": r_after_cost,
                        "r_raw": result["r_multiple_raw"],
                        "mfe_r": result["mfe_r"],
                        "mae_r": result["mae_r"],
                        "hold_bars": result["hold_bars"],
                        "note": signal.note,
                    }
                )
                cooldown_until[key] = i + result["hold_bars"]

    trades_df = pd.DataFrame(trades)
    if trades_df.empty:
        return trades_df, pd.DataFrame()
    leaderboard = (
        trades_df.groupby(["setup", "timeframe", "direction"], dropna=False)
        .agg(
            trades=("r", "count"),
            win_rate=("r", lambda s: float((s > 0).mean() * 100)),
            expectancy_r=("r", "mean"),
            avg_win_r=("r", lambda s: float(s[s > 0].mean()) if (s > 0).any() else 0.0),
            avg_loss_r=("r", lambda s: float(s[s <= 0].mean()) if (s <= 0).any() else 0.0),
            profit_factor=("r", lambda s: float(s[s > 0].sum() / abs(s[s < 0].sum())) if (s < 0).any() and abs(s[s < 0].sum()) > 0 else float("inf")),
            avg_mfe_r=("mfe_r", "mean"),
            avg_mae_r=("mae_r", "mean"),
            avg_hold_bars=("hold_bars", "mean"),
        )
        .reset_index()
        .sort_values(["expectancy_r", "trades"], ascending=[False, False])
    )
    return trades_df, leaderboard


def enrich_trades_with_fno_context(trades: pd.DataFrame, fno_context: pd.DataFrame) -> pd.DataFrame:
    if trades.empty or fno_context.empty:
        return trades
    out = trades.copy()
    out["trade_date"] = _date_for_join(out["entry_ts"])
    context_cols = [
        "symbol",
        "trade_date",
        "expiry_date",
        "pcr",
        "pcr_regime",
        "max_pain",
        "max_pain_distance_pct",
        "ce_wall",
        "pe_floor",
    ]
    ctx = fno_context[[c for c in context_cols if c in fno_context.columns]].copy()
    return out.merge(ctx, on=["symbol", "trade_date"], how="left")


def fno_regime_leaderboard(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty or "pcr_regime" not in trades.columns:
        return pd.DataFrame()
    subset = trades[trades["pcr_regime"].notna()].copy()
    if subset.empty:
        return pd.DataFrame()
    return (
        subset.groupby(["setup", "timeframe", "direction", "pcr_regime"], dropna=False)
        .agg(
            trades=("r", "count"),
            win_rate=("r", lambda s: float((s > 0).mean() * 100)),
            expectancy_r=("r", "mean"),
            profit_factor=("r", lambda s: float(s[s > 0].sum() / abs(s[s < 0].sum())) if (s < 0).any() and abs(s[s < 0].sum()) > 0 else float("inf")),
        )
        .reset_index()
        .sort_values(["expectancy_r", "trades"], ascending=[False, False])
    )


def build_volatility_context(features: pd.DataFrame, *, span: int = 20) -> pd.DataFrame:
    if features.empty:
        return pd.DataFrame()
    required = {"symbol", "timeframe", "timestamp", "Close"}
    if not required.issubset(features.columns):
        return pd.DataFrame()
    parts: list[pd.DataFrame] = []
    for (_, _), grp in features.groupby(["symbol", "timeframe"], sort=False):
        g = grp.sort_values("timestamp").copy()
        returns = pd.to_numeric(g["Close"], errors="coerce").pct_change()
        ewma_vol = returns.ewm(span=span, adjust=False, min_periods=max(5, span // 4)).std()
        valid = ewma_vol.dropna()
        if valid.empty:
            regime = pd.Series(["normal"] * len(g), index=g.index, dtype="object")
        else:
            low_cut = float(valid.quantile(0.33))
            high_cut = float(valid.quantile(0.67))
            regime = pd.Series("normal", index=g.index, dtype="object")
            regime.loc[ewma_vol <= low_cut] = "low"
            regime.loc[ewma_vol >= high_cut] = "high"
            regime.loc[ewma_vol.isna()] = "normal"
        parts.append(
            pd.DataFrame(
                {
                    "symbol": g["symbol"].astype(str).str.upper(),
                    "timeframe": g["timeframe"].astype(str).str.lower(),
                    "timestamp": pd.to_datetime(g["timestamp"], errors="coerce"),
                    "bar_return": returns,
                    "ewma_volatility": ewma_vol,
                    "volatility_regime": regime,
                }
            )
        )
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def enrich_trades_with_quant_context(trades: pd.DataFrame, volatility_context: pd.DataFrame) -> pd.DataFrame:
    if trades.empty or volatility_context.empty:
        return trades
    out = trades.copy()
    out["symbol"] = out["symbol"].astype(str).str.upper()
    out["timeframe"] = out["timeframe"].astype(str).str.lower()
    out["entry_ts"] = pd.to_datetime(out["entry_ts"], errors="coerce")
    ctx = volatility_context.copy()
    ctx["symbol"] = ctx["symbol"].astype(str).str.upper()
    ctx["timeframe"] = ctx["timeframe"].astype(str).str.lower()
    ctx["timestamp"] = pd.to_datetime(ctx["timestamp"], errors="coerce")
    cols = ["symbol", "timeframe", "timestamp", "bar_return", "ewma_volatility", "volatility_regime"]
    ctx = ctx[[c for c in cols if c in ctx.columns]].dropna(subset=["timestamp"])
    merged = out.merge(
        ctx,
        left_on=["symbol", "timeframe", "entry_ts"],
        right_on=["symbol", "timeframe", "timestamp"],
        how="left",
    )
    return merged.drop(columns=["timestamp"], errors="ignore")


def volatility_regime_leaderboard(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty or "volatility_regime" not in trades.columns:
        return pd.DataFrame()
    subset = trades[trades["volatility_regime"].notna()].copy()
    if subset.empty:
        return pd.DataFrame()
    return (
        subset.groupby(["setup", "timeframe", "direction", "volatility_regime"], dropna=False)
        .agg(
            trades=("r", "count"),
            win_rate=("r", lambda s: float((s > 0).mean() * 100)),
            expectancy_r=("r", "mean"),
            profit_factor=("r", lambda s: float(s[s > 0].sum() / abs(s[s < 0].sum())) if (s < 0).any() and abs(s[s < 0].sum()) > 0 else float("inf")),
        )
        .reset_index()
        .sort_values(["expectancy_r", "trades"], ascending=[False, False])
    )


def rolling_window_stability(trades: pd.DataFrame, *, windows: int = 5, min_trades: int = 5) -> pd.DataFrame:
    if trades.empty or "entry_ts" not in trades.columns:
        return pd.DataFrame()
    out = trades.copy()
    out["entry_ts"] = pd.to_datetime(out["entry_ts"], errors="coerce")
    out = out.dropna(subset=["entry_ts"]).sort_values("entry_ts")
    if out.empty:
        return pd.DataFrame()
    window_count = max(1, min(int(windows), len(out)))
    out["_window"] = pd.cut(
        range(len(out)),
        bins=window_count,
        labels=[f"W{i + 1}" for i in range(window_count)],
        include_lowest=True,
    )
    window_stats = (
        out.groupby(["setup", "timeframe", "direction", "_window"], observed=True, dropna=False)
        .agg(
            window_start=("entry_ts", "min"),
            window_end=("entry_ts", "max"),
            trades=("r", "count"),
            win_rate=("r", lambda s: float((s > 0).mean() * 100)),
            expectancy_r=("r", "mean"),
            profit_factor=("r", lambda s: float(s[s > 0].sum() / abs(s[s < 0].sum())) if (s < 0).any() and abs(s[s < 0].sum()) > 0 else float("inf")),
        )
        .reset_index()
    )
    window_stats = window_stats[window_stats["trades"] >= min_trades]
    if window_stats.empty:
        return pd.DataFrame()
    return (
        window_stats.groupby(["setup", "timeframe", "direction"], dropna=False)
        .agg(
            windows=("expectancy_r", "count"),
            total_trades=("trades", "sum"),
            avg_expectancy_r=("expectancy_r", "mean"),
            std_expectancy_r=("expectancy_r", lambda s: float(s.std(ddof=0))),
            positive_window_rate=("expectancy_r", lambda s: float((s > 0).mean() * 100)),
            worst_window_r=("expectancy_r", "min"),
            best_window_r=("expectancy_r", "max"),
            first_window_start=("window_start", "min"),
            last_window_end=("window_end", "max"),
        )
        .reset_index()
        .assign(stability_score=lambda df: df["avg_expectancy_r"] - df["std_expectancy_r"])
        .sort_values(["stability_score", "positive_window_rate", "total_trades"], ascending=[False, False, False])
    )


def _profit_factor(series: pd.Series) -> float:
    gains = float(series[series > 0].sum())
    losses = float(abs(series[series < 0].sum()))
    if losses <= 0:
        return float("inf") if gains > 0 else 0.0
    return gains / losses


def walk_forward_validation(
    trades: pd.DataFrame,
    *,
    windows: int = 5,
    min_train_trades: int = 20,
    min_validation_trades: int = 5,
    min_train_expectancy_r: float = 0.0,
    min_train_profit_factor: float = 1.10,
) -> pd.DataFrame:
    if trades.empty or "entry_ts" not in trades.columns:
        return pd.DataFrame()
    out = trades.copy()
    out["entry_ts"] = pd.to_datetime(out["entry_ts"], errors="coerce")
    out = out.dropna(subset=["entry_ts", "r"]).sort_values("entry_ts")
    if out.empty:
        return pd.DataFrame()

    fold_rows: list[dict[str, Any]] = []
    for (setup, timeframe, direction), grp in out.groupby(["setup", "timeframe", "direction"], dropna=False):
        g = grp.sort_values("entry_ts").reset_index(drop=True)
        window_count = max(2, min(int(windows), len(g)))
        if len(g) < min_train_trades + min_validation_trades or window_count < 2:
            continue
        g["_wf_window"] = pd.cut(
            range(len(g)),
            bins=window_count,
            labels=list(range(window_count)),
            include_lowest=True,
        ).astype(int)
        for validation_window in range(1, window_count):
            train = g[g["_wf_window"] < validation_window]
            validation = g[g["_wf_window"] == validation_window]
            if len(train) < min_train_trades or len(validation) < min_validation_trades:
                continue
            train_expectancy = float(train["r"].mean())
            train_pf = _profit_factor(train["r"])
            promoted = train_expectancy > min_train_expectancy_r and train_pf >= min_train_profit_factor
            validation_expectancy = float(validation["r"].mean())
            fold_rows.append(
                {
                    "setup": str(setup),
                    "timeframe": str(timeframe),
                    "direction": str(direction),
                    "fold": validation_window,
                    "train_trades": int(len(train)),
                    "validation_trades": int(len(validation)),
                    "train_expectancy_r": train_expectancy,
                    "train_profit_factor": train_pf,
                    "train_promoted": bool(promoted),
                    "validation_expectancy_r": validation_expectancy,
                    "validation_win_rate": float((validation["r"] > 0).mean() * 100),
                    "validation_profit_factor": _profit_factor(validation["r"]),
                    "validation_positive": bool(validation_expectancy > 0),
                    "validation_start": validation["entry_ts"].min(),
                    "validation_end": validation["entry_ts"].max(),
                }
            )
    folds = pd.DataFrame(fold_rows)
    if folds.empty:
        return pd.DataFrame()
    promoted = folds[folds["train_promoted"]].copy()
    if promoted.empty:
        grouped = folds.groupby(["setup", "timeframe", "direction"], dropna=False).agg(
            folds_tested=("fold", "count"),
            promoted_folds=("train_promoted", "sum"),
            validation_trades=("validation_trades", "sum"),
        ).reset_index()
        grouped["train_expectancy_r"] = None
        grouped["validation_expectancy_r"] = None
        grouped["validation_win_rate"] = None
        grouped["validation_profit_factor"] = None
        grouped["validation_positive_fold_rate"] = 0.0
        grouped["worst_validation_r"] = None
        grouped["walk_forward_status"] = "rejected_in_training"
        return grouped

    summary = (
        promoted.groupby(["setup", "timeframe", "direction"], dropna=False)
        .agg(
            folds_tested=("fold", "count"),
            promoted_folds=("train_promoted", "sum"),
            validation_trades=("validation_trades", "sum"),
            train_expectancy_r=("train_expectancy_r", "mean"),
            train_profit_factor=("train_profit_factor", "mean"),
            validation_expectancy_r=("validation_expectancy_r", "mean"),
            validation_win_rate=("validation_win_rate", "mean"),
            validation_profit_factor=("validation_profit_factor", "mean"),
            validation_positive_fold_rate=("validation_positive", lambda s: float(s.mean() * 100)),
            worst_validation_r=("validation_expectancy_r", "min"),
            validation_start=("validation_start", "min"),
            validation_end=("validation_end", "max"),
        )
        .reset_index()
    )

    def _status(row: pd.Series) -> str:
        val_exp = float(row.get("validation_expectancy_r") or 0.0)
        pos_rate = float(row.get("validation_positive_fold_rate") or 0.0)
        pf = float(row.get("validation_profit_factor") or 0.0)
        folds_tested = int(row.get("folds_tested") or 0)
        if folds_tested <= 0:
            return "insufficient"
        if val_exp > 0 and pos_rate >= 60 and pf >= 1.05:
            return "confirmed"
        if val_exp > 0 and pos_rate >= 50:
            return "conditional"
        return "rejected_out_of_sample"

    summary["walk_forward_status"] = summary.apply(_status, axis=1)
    status_rank = {"confirmed": 0, "conditional": 1, "rejected_out_of_sample": 2, "insufficient": 3}
    summary["_status_rank"] = summary["walk_forward_status"].map(status_rank).fillna(9)
    return (
        summary.sort_values(
            ["_status_rank", "validation_expectancy_r", "validation_positive_fold_rate", "validation_trades"],
            ascending=[True, False, False, False],
        )
        .drop(columns=["_status_rank"])
        .reset_index(drop=True)
    )


def _confirmed_setup_subset(
    trades: pd.DataFrame,
    *,
    setup: str = "ORB + VWAP",
    direction: str = "LONG",
    timeframe: str | None = None,
) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()
    subset = trades[
        (trades["setup"].astype(str) == setup)
        & (trades["direction"].astype(str) == direction)
    ].copy()
    if timeframe:
        subset = subset[subset["timeframe"].astype(str) == timeframe]
    return subset


def _best_regime_label(frame: pd.DataFrame, column: str) -> str:
    if frame.empty or column not in frame.columns:
        return "-"
    subset = frame[frame[column].notna()].copy()
    if subset.empty:
        return "-"
    ranked = (
        subset.groupby(column, dropna=False)
        .agg(trades=("r", "count"), expectancy_r=("r", "mean"))
        .reset_index()
        .sort_values(["expectancy_r", "trades"], ascending=[False, False])
    )
    return str(ranked.iloc[0][column]) if not ranked.empty else "-"


def confirmed_setup_symbol_drilldown(
    trades: pd.DataFrame,
    *,
    setup: str = "ORB + VWAP",
    direction: str = "LONG",
    timeframe: str | None = None,
    min_trades: int = 5,
) -> pd.DataFrame:
    subset = _confirmed_setup_subset(trades, setup=setup, direction=direction, timeframe=timeframe)
    if subset.empty:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    for symbol, grp in subset.groupby("symbol", dropna=False):
        if len(grp) < min_trades:
            continue
        expectancy = float(grp["r"].mean())
        pf = _profit_factor(grp["r"])
        win_rate = float((grp["r"] > 0).mean() * 100)
        if expectancy > 0 and pf >= 1.10 and win_rate >= 50:
            status = "core_carrier"
        elif expectancy > 0 and pf >= 1.0:
            status = "watch_carrier"
        else:
            status = "edge_diluter"
        rows.append(
            {
                "symbol": str(symbol),
                "symbol_edge_status": status,
                "setup": setup,
                "timeframe": timeframe or str(grp["timeframe"].mode().iloc[0]) if "timeframe" in grp.columns and not grp["timeframe"].mode().empty else "-",
                "direction": direction,
                "trades": int(len(grp)),
                "win_rate": win_rate,
                "expectancy_r": expectancy,
                "profit_factor": pf,
                "avg_mfe_r": float(grp["mfe_r"].mean()) if "mfe_r" in grp.columns else None,
                "avg_mae_r": float(grp["mae_r"].mean()) if "mae_r" in grp.columns else None,
                "best_volatility_regime": _best_regime_label(grp, "volatility_regime"),
                "best_pcr_regime": _best_regime_label(grp, "pcr_regime"),
            }
        )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    status_rank = {"core_carrier": 0, "watch_carrier": 1, "edge_diluter": 2}
    frame["_status_rank"] = frame["symbol_edge_status"].map(status_rank).fillna(9)
    return (
        frame.sort_values(["_status_rank", "expectancy_r", "trades"], ascending=[True, False, False])
        .drop(columns=["_status_rank"])
        .reset_index(drop=True)
    )


def _time_bucket(value: Any) -> str:
    ts = pd.to_datetime(value, errors="coerce")
    if pd.isna(ts):
        return "unknown"
    # Intraday bars in this project are exchange-clock timestamps; preserve the
    # displayed clock even when pandas marks them timezone-aware.
    minute = int(ts.hour) * 60 + int(ts.minute)
    if minute < 10 * 60 + 15:
        return "opening_drive"
    if minute < 12 * 60:
        return "late_morning"
    if minute < 14 * 60:
        return "mid_session"
    return "closing_drive"


def time_of_day_leaderboard(
    trades: pd.DataFrame,
    *,
    setup: str = "ORB + VWAP",
    direction: str = "LONG",
    timeframe: str | None = None,
    min_trades: int = 5,
) -> pd.DataFrame:
    subset = _confirmed_setup_subset(trades, setup=setup, direction=direction, timeframe=timeframe)
    if subset.empty or "entry_ts" not in subset.columns:
        return pd.DataFrame()
    subset = subset.copy()
    subset["time_bucket"] = subset["entry_ts"].map(_time_bucket)
    grouped = (
        subset.groupby(["setup", "timeframe", "direction", "time_bucket"], dropna=False)
        .agg(
            trades=("r", "count"),
            win_rate=("r", lambda s: float((s > 0).mean() * 100)),
            expectancy_r=("r", "mean"),
            profit_factor=("r", _profit_factor),
            avg_mfe_r=("mfe_r", "mean") if "mfe_r" in subset.columns else ("r", "mean"),
            avg_mae_r=("mae_r", "mean") if "mae_r" in subset.columns else ("r", "mean"),
        )
        .reset_index()
    )
    grouped = grouped[grouped["trades"] >= min_trades]
    if grouped.empty:
        return grouped
    return grouped.sort_values(["expectancy_r", "trades"], ascending=[False, False]).reset_index(drop=True)


def build_quant_research_thesis(
    leaderboard: pd.DataFrame,
    rolling_stability: pd.DataFrame,
    volatility_regimes: pd.DataFrame,
    fno_regimes: pd.DataFrame,
) -> pd.DataFrame:
    if leaderboard.empty:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    vol_key = ["setup", "timeframe", "direction"]
    for _, row in leaderboard.head(30).iterrows():
        setup = str(row.get("setup"))
        timeframe = str(row.get("timeframe"))
        direction = str(row.get("direction"))
        key_filter = (
            (rolling_stability["setup"] == setup)
            & (rolling_stability["timeframe"] == timeframe)
            & (rolling_stability["direction"] == direction)
        ) if not rolling_stability.empty else pd.Series(dtype=bool)
        stability = rolling_stability[key_filter].head(1) if not rolling_stability.empty else pd.DataFrame()
        vol_subset = volatility_regimes[
            (volatility_regimes["setup"] == setup)
            & (volatility_regimes["timeframe"] == timeframe)
            & (volatility_regimes["direction"] == direction)
        ] if not volatility_regimes.empty and set(vol_key).issubset(volatility_regimes.columns) else pd.DataFrame()
        fno_subset = fno_regimes[
            (fno_regimes["setup"] == setup)
            & (fno_regimes["timeframe"] == timeframe)
            & (fno_regimes["direction"] == direction)
        ] if not fno_regimes.empty and set(vol_key).issubset(fno_regimes.columns) else pd.DataFrame()

        expectancy = float(row.get("expectancy_r") or 0.0)
        trades = int(row.get("trades") or 0)
        profit_factor = float(row.get("profit_factor") or 0.0)
        positive_window_rate = float(stability.iloc[0].get("positive_window_rate") or 0.0) if not stability.empty else 0.0
        stability_score = float(stability.iloc[0].get("stability_score") or 0.0) if not stability.empty else 0.0
        best_vol = (
            vol_subset.sort_values(["expectancy_r", "trades"], ascending=[False, False]).head(1)
            if not vol_subset.empty and {"expectancy_r", "trades"}.issubset(vol_subset.columns)
            else pd.DataFrame()
        )
        best_fno = (
            fno_subset.sort_values(["expectancy_r", "trades"], ascending=[False, False]).head(1)
            if not fno_subset.empty and {"expectancy_r", "trades"}.issubset(fno_subset.columns)
            else pd.DataFrame()
        )
        vol_label = str(best_vol.iloc[0].get("volatility_regime")) if not best_vol.empty else "unclassified"
        fno_label = str(best_fno.iloc[0].get("pcr_regime")) if not best_fno.empty else "unclassified"
        if trades >= 20 and expectancy > 0 and profit_factor >= 1.1 and positive_window_rate >= 60:
            thesis = "candidate_core"
            action = "Promote for paper/live alert research with regime gates."
        elif expectancy > 0 and (not best_vol.empty or not best_fno.empty):
            thesis = "conditional_regime_edge"
            action = "Use only when volatility or F&O regime matches the tested edge."
        elif expectancy > 0:
            thesis = "watch_more_history"
            action = "Keep in research watchlist until stability sample improves."
        else:
            thesis = "reject_global_edge"
            action = "Do not promote globally; test symbol-specific variants only."
        rows.append(
            {
                "setup": setup,
                "timeframe": timeframe,
                "direction": direction,
                "thesis": thesis,
                "trades": trades,
                "expectancy_r": expectancy,
                "profit_factor": profit_factor,
                "positive_window_rate": positive_window_rate,
                "stability_score": stability_score,
                "best_volatility_regime": vol_label,
                "best_pcr_regime": fno_label,
                "research_action": action,
            }
        )
    return pd.DataFrame(rows).sort_values(
        ["thesis", "stability_score", "expectancy_r", "trades"],
        ascending=[True, False, False, False],
    )


def _return_series(grp: pd.DataFrame) -> pd.Series:
    close = pd.to_numeric(grp.sort_values("timestamp")["Close"], errors="coerce")
    returns = close.pct_change().replace([float("inf"), float("-inf")], pd.NA).dropna()
    return returns.astype(float)


def _ar1_ols_metrics(returns: pd.Series) -> dict[str, float | None]:
    y = returns.iloc[1:].reset_index(drop=True)
    x = returns.shift(1).iloc[1:].reset_index(drop=True)
    valid = pd.DataFrame({"x": x, "y": y}).dropna()
    if len(valid) < 3:
        return {"persistence": None, "t_stat": None, "r_squared": None}
    x = valid["x"]
    y = valid["y"]
    x_mean = float(x.mean())
    y_mean = float(y.mean())
    x_var = float(((x - x_mean) ** 2).sum())
    if x_var <= 0:
        return {"persistence": 0.0, "t_stat": None, "r_squared": 0.0}
    beta = float(((x - x_mean) * (y - y_mean)).sum() / x_var)
    alpha = y_mean - beta * x_mean
    resid = y - (alpha + beta * x)
    rss = float((resid**2).sum())
    tss = float(((y - y_mean) ** 2).sum())
    dof = max(len(valid) - 2, 1)
    sigma2 = rss / dof
    se_beta = math.sqrt(sigma2 / x_var) if x_var > 0 else None
    t_stat = beta / se_beta if se_beta and se_beta > 0 else None
    r_squared = 1 - rss / tss if tss > 0 else 0.0
    return {"persistence": beta, "t_stat": t_stat, "r_squared": r_squared}


def _diagnostic_bias(persistence: float | None, drift_t_stat: float | None, vol_clustering: float | None) -> str:
    if persistence is not None and persistence >= 0.05 and (drift_t_stat or 0.0) > 0:
        return "trend_following"
    if persistence is not None and persistence <= -0.05:
        return "mean_reversion"
    if vol_clustering is not None and vol_clustering >= 0.10:
        return "volatility_clustered"
    return "noise_or_mixed"


def build_statistical_model_diagnostics(
    features: pd.DataFrame,
    *,
    max_symbols: int = 12,
    min_returns: int = 80,
) -> pd.DataFrame:
    if features.empty or not {"symbol", "timeframe", "timestamp", "Close"}.issubset(features.columns):
        return pd.DataFrame()
    groups: list[tuple[tuple[str, str], pd.DataFrame, int]] = []
    for key, grp in features.groupby(["symbol", "timeframe"], sort=False):
        groups.append((key, grp, len(_return_series(grp))))
    groups.sort(key=lambda item: item[2], reverse=True)

    rows: list[dict[str, Any]] = []
    for (symbol, timeframe), grp, observations in groups[: max(1, int(max_symbols))]:
        returns = _return_series(grp)
        ret_pct = returns * 100
        mean_return = float(ret_pct.mean()) if not ret_pct.empty else None
        volatility = float(ret_pct.std(ddof=0)) if len(ret_pct) > 1 else None
        drift_t_stat = None
        if volatility and volatility > 0 and observations > 1:
            drift_t_stat = float((mean_return or 0.0) / volatility * math.sqrt(observations))
        vol_clustering = float((returns**2).autocorr(lag=1)) if observations > 3 else None

        if observations < min_returns:
            rows.append(
                {
                    "symbol": str(symbol),
                    "timeframe": str(timeframe),
                    "model_type": "ar1_ols",
                    "status": "insufficient_data",
                    "observations": observations,
                    "mean_return_bps": None,
                    "volatility_bps": None,
                    "persistence": None,
                    "t_stat": None,
                    "r_squared": None,
                    "forecast_vol_pct": None,
                    "volatility_clustering": None,
                    "aic": None,
                    "bic": None,
                    "bias": "insufficient_data",
                    "note": f"needs at least {min_returns} returns",
                }
            )
        else:
            ar1 = _ar1_ols_metrics(returns)
            rows.append(
                {
                    "symbol": str(symbol),
                    "timeframe": str(timeframe),
                    "model_type": "ar1_ols",
                    "status": "fitted",
                    "observations": observations,
                    "mean_return_bps": (mean_return or 0.0) * 100,
                    "volatility_bps": (volatility or 0.0) * 100,
                    "persistence": ar1["persistence"],
                    "t_stat": ar1["t_stat"],
                    "r_squared": ar1["r_squared"],
                    "forecast_vol_pct": None,
                    "volatility_clustering": vol_clustering,
                    "aic": None,
                    "bic": None,
                    "bias": _diagnostic_bias(ar1["persistence"], drift_t_stat, vol_clustering),
                    "note": "dependency-free AR(1) return persistence diagnostic",
                }
            )

        try:
            from statsmodels.tsa.ar_model import AutoReg  # type: ignore

            if observations >= min_returns:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    model = AutoReg(ret_pct.reset_index(drop=True), lags=1, old_names=False).fit()
                    ar_param = next((float(v) for k, v in model.params.items() if str(k).endswith(".L1")), None)
                    aic = float(model.aic)
                    bic = float(model.bic)
                rows.append(
                    {
                        "symbol": str(symbol),
                        "timeframe": str(timeframe),
                        "model_type": "statsmodels_autoreg_1",
                        "status": "fitted",
                        "observations": observations,
                        "mean_return_bps": (mean_return or 0.0) * 100,
                        "volatility_bps": (volatility or 0.0) * 100,
                        "persistence": ar_param,
                        "t_stat": None,
                        "r_squared": None,
                        "forecast_vol_pct": None,
                        "volatility_clustering": vol_clustering,
                        "aic": aic,
                        "bic": bic,
                        "bias": _diagnostic_bias(ar_param, drift_t_stat, vol_clustering),
                        "note": "statsmodels AutoReg(1) fitted on intraday returns",
                    }
                )
        except ModuleNotFoundError:
            rows.append(
                {
                    "symbol": str(symbol),
                    "timeframe": str(timeframe),
                    "model_type": "statsmodels_autoreg_1",
                    "status": "unavailable",
                    "observations": observations,
                    "mean_return_bps": None,
                    "volatility_bps": None,
                    "persistence": None,
                    "t_stat": None,
                    "r_squared": None,
                    "forecast_vol_pct": None,
                    "volatility_clustering": None,
                    "aic": None,
                    "bic": None,
                    "bias": "dependency_missing",
                    "note": "install statsmodels to fit AutoReg/ARIMA diagnostics",
                }
            )
        except Exception as exc:
            rows.append(
                {
                    "symbol": str(symbol),
                    "timeframe": str(timeframe),
                    "model_type": "statsmodels_autoreg_1",
                    "status": "error",
                    "observations": observations,
                    "mean_return_bps": None,
                    "volatility_bps": None,
                    "persistence": None,
                    "t_stat": None,
                    "r_squared": None,
                    "forecast_vol_pct": None,
                    "volatility_clustering": None,
                    "aic": None,
                    "bic": None,
                    "bias": "fit_error",
                    "note": f"{type(exc).__name__}: {exc}",
                }
            )

        try:
            from arch import arch_model  # type: ignore

            if observations >= min_returns:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    model = arch_model(ret_pct, mean="Zero", vol="GARCH", p=1, q=1, rescale=False)
                    fitted = model.fit(disp="off", show_warning=False)
                    forecast_var = float(fitted.forecast(horizon=1).variance.iloc[-1, 0])
                params = fitted.params
                alpha = float(params.get("alpha[1]", 0.0))
                beta = float(params.get("beta[1]", 0.0))
                rows.append(
                    {
                        "symbol": str(symbol),
                        "timeframe": str(timeframe),
                        "model_type": "garch_11",
                        "status": "fitted",
                        "observations": observations,
                        "mean_return_bps": (mean_return or 0.0) * 100,
                        "volatility_bps": (volatility or 0.0) * 100,
                        "persistence": alpha + beta,
                        "t_stat": None,
                        "r_squared": None,
                        "forecast_vol_pct": math.sqrt(max(forecast_var, 0.0)),
                        "volatility_clustering": vol_clustering,
                        "aic": float(fitted.aic),
                        "bic": float(fitted.bic),
                        "bias": "high_vol_persistence" if alpha + beta >= 0.85 else "low_vol_persistence",
                        "note": "GARCH(1,1) fitted on percent intraday returns",
                    }
                )
        except ModuleNotFoundError:
            rows.append(
                {
                    "symbol": str(symbol),
                    "timeframe": str(timeframe),
                    "model_type": "garch_11",
                    "status": "unavailable",
                    "observations": observations,
                    "mean_return_bps": None,
                    "volatility_bps": None,
                    "persistence": None,
                    "t_stat": None,
                    "r_squared": None,
                    "forecast_vol_pct": None,
                    "volatility_clustering": None,
                    "aic": None,
                    "bic": None,
                    "bias": "dependency_missing",
                    "note": "install arch to fit GARCH(1,1) volatility diagnostics",
                }
            )
        except Exception as exc:
            rows.append(
                {
                    "symbol": str(symbol),
                    "timeframe": str(timeframe),
                    "model_type": "garch_11",
                    "status": "error",
                    "observations": observations,
                    "mean_return_bps": None,
                    "volatility_bps": None,
                    "persistence": None,
                    "t_stat": None,
                    "r_squared": None,
                    "forecast_vol_pct": None,
                    "volatility_clustering": None,
                    "aic": None,
                    "bic": None,
                    "bias": "fit_error",
                    "note": f"{type(exc).__name__}: {exc}",
                }
            )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    status_rank = {"fitted": 0, "error": 1, "unavailable": 2, "insufficient_data": 3}
    frame["_status_rank"] = frame["status"].map(status_rank).fillna(9)
    return frame.sort_values(["_status_rank", "symbol", "model_type"]).drop(columns=["_status_rank"]).reset_index(drop=True)


def symbol_setup_leaderboard(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()
    return (
        trades.groupby(["symbol", "setup", "timeframe", "direction"], dropna=False)
        .agg(
            trades=("r", "count"),
            win_rate=("r", lambda s: float((s > 0).mean() * 100)),
            expectancy_r=("r", "mean"),
            avg_win_r=("r", lambda s: float(s[s > 0].mean()) if (s > 0).any() else 0.0),
            avg_loss_r=("r", lambda s: float(s[s <= 0].mean()) if (s <= 0).any() else 0.0),
            profit_factor=("r", lambda s: float(s[s > 0].sum() / abs(s[s < 0].sum())) if (s < 0).any() and abs(s[s < 0].sum()) > 0 else float("inf")),
            avg_mfe_r=("mfe_r", "mean"),
            avg_mae_r=("mae_r", "mean"),
            avg_hold_bars=("hold_bars", "mean"),
        )
        .reset_index()
        .sort_values(["symbol", "expectancy_r", "trades"], ascending=[True, False, False])
    )


def _setup_status(row: pd.Series, config: StudyConfig) -> str:
    trades = int(row.get("trades") or 0)
    expectancy = float(row.get("expectancy_r") or 0.0)
    pf = float(row.get("profit_factor") or 0.0)
    if (
        trades >= config.promote_min_trades
        and expectancy >= config.promote_min_expectancy_r
        and pf >= config.promote_min_profit_factor
    ):
        return "promoted"
    if trades >= config.watch_min_trades and expectancy >= config.watch_min_expectancy_r:
        return "watch_candidate"
    return "avoid"


def build_strategy_map(
    trades: pd.DataFrame,
    symbols: list[str] | tuple[str, ...],
    config: StudyConfig,
) -> dict[str, Any]:
    leaderboard = symbol_setup_leaderboard(trades)
    generated_at = datetime.now(IST).isoformat(timespec="seconds")
    payload: dict[str, Any] = {
        "schema_version": 1,
        "generated_at": generated_at,
        "universe": config.universe,
        "timeframes": list(config.timeframes),
        "criteria": {
            "promoted": {
                "min_trades": config.promote_min_trades,
                "min_expectancy_r": config.promote_min_expectancy_r,
                "min_profit_factor": config.promote_min_profit_factor,
            },
            "watch_candidate": {
                "min_trades": config.watch_min_trades,
                "min_expectancy_r": config.watch_min_expectancy_r,
            },
            "costs": {
                "slippage_bps_per_side": config.slippage_bps,
                "brokerage_bps_per_side": config.brokerage_bps,
            },
        },
        "symbols": {},
    }
    requested = [str(symbol).strip().upper() for symbol in symbols if str(symbol).strip()]
    for symbol in requested:
        subset = leaderboard[leaderboard["symbol"] == symbol] if not leaderboard.empty else pd.DataFrame()
        entries: list[dict[str, Any]] = []
        if not subset.empty:
            for _, row in subset.iterrows():
                status = _setup_status(row, config)
                entries.append(
                    {
                        "setup": str(row.get("setup")),
                        "timeframe": str(row.get("timeframe")),
                        "direction": str(row.get("direction")),
                        "status": status,
                        "trades": int(row.get("trades") or 0),
                        "win_rate": round(float(row.get("win_rate") or 0.0), 2),
                        "expectancy_r": round(float(row.get("expectancy_r") or 0.0), 4),
                        "profit_factor": None if math.isinf(float(row.get("profit_factor") or 0.0)) else round(float(row.get("profit_factor") or 0.0), 4),
                        "avg_mfe_r": round(float(row.get("avg_mfe_r") or 0.0), 4),
                        "avg_mae_r": round(float(row.get("avg_mae_r") or 0.0), 4),
                        "avg_hold_bars": round(float(row.get("avg_hold_bars") or 0.0), 2),
                    }
                )
        status_rank = {
            "promoted": 0,
            "watch_candidate": 1,
            "avoid": 2,
            "insufficient_data": 3,
        }
        entries = sorted(
            entries,
            key=lambda entry: (
                status_rank.get(str(entry.get("status")), 99),
                -float(entry.get("expectancy_r") or 0.0),
                -int(entry.get("trades") or 0),
            ),
        )
        top = entries[0] if entries else None
        promoted = [entry for entry in entries if entry["status"] == "promoted"]
        watch = [entry for entry in entries if entry["status"] == "watch_candidate"]
        if promoted:
            symbol_status = "promoted"
        elif watch:
            symbol_status = "watch_candidate"
        elif entries:
            symbol_status = "avoid"
        else:
            symbol_status = "insufficient_data"
        payload["symbols"][symbol] = {
            "status": symbol_status,
            "top_setup": top,
            "setups": entries[:12],
        }
    return payload


def strategy_map_frame(strategy_map: dict[str, Any]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for symbol, payload in (strategy_map.get("symbols") or {}).items():
        top = payload.get("top_setup") or {}
        rows.append(
            {
                "symbol": symbol,
                "status": payload.get("status"),
                "setup": top.get("setup") or "-",
                "timeframe": top.get("timeframe") or "-",
                "direction": top.get("direction") or "-",
                "trades": top.get("trades") or 0,
                "win_rate": top.get("win_rate") or 0.0,
                "expectancy_r": top.get("expectancy_r") or 0.0,
                "profit_factor": top.get("profit_factor"),
            }
        )
    status_rank = {
        "promoted": 0,
        "watch_candidate": 1,
        "avoid": 2,
        "insufficient_data": 3,
    }
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    frame["_status_rank"] = frame["status"].map(status_rank).fillna(99)
    return (
        frame.sort_values(
            ["_status_rank", "expectancy_r", "trades"],
            ascending=[True, False, False],
        )
        .drop(columns=["_status_rank"])
        .reset_index(drop=True)
    )


def _table_md(frame: pd.DataFrame, cols: list[str], limit: int = 20) -> str:
    if frame.empty:
        return "_No rows._"
    rows = frame.head(limit)
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for _, row in rows.iterrows():
        vals = []
        for col in cols:
            value = row.get(col)
            if value is None or (isinstance(value, float) and math.isnan(value)):
                vals.append("-")
                continue
            if isinstance(value, float):
                if col == "win_rate":
                    vals.append(_safe_pct(value))
                else:
                    vals.append(_fmt(value, 2))
            else:
                vals.append(str(value))
        lines.append("| " + " | ".join(vals) + " |")
    return "\n".join(lines)


def _markdown_to_html(markdown: str) -> str:
    body_lines: list[str] = []
    in_table = False
    for raw in markdown.splitlines():
        line = raw.rstrip()
        if line.startswith("| ") and line.endswith(" |"):
            cells = [html.escape(c.strip()) for c in line.strip("|").split("|")]
            if set(cells) == {"---"}:
                continue
            if not in_table:
                body_lines.append("<table>")
                in_table = True
                body_lines.append("<tr>" + "".join(f"<th>{c}</th>" for c in cells) + "</tr>")
            else:
                body_lines.append("<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
            continue
        if in_table:
            body_lines.append("</table>")
            in_table = False
        if line.startswith("# "):
            body_lines.append(f"<h1>{html.escape(line[2:])}</h1>")
        elif line.startswith("## "):
            body_lines.append(f"<h2>{html.escape(line[3:])}</h2>")
        elif line.startswith("- "):
            body_lines.append(f"<p class='bullet'>{html.escape(line)}</p>")
        elif line:
            body_lines.append(f"<p>{html.escape(line)}</p>")
        else:
            body_lines.append("")
    if in_table:
        body_lines.append("</table>")
    css = """
    body{font-family:Inter,Arial,sans-serif;background:#f6f8fb;color:#142323;margin:0;padding:28px}
    .wrap{max-width:1180px;margin:auto;background:#fff;border:1px solid #d9e4e4;border-radius:10px;padding:28px}
    h1{margin:0 0 8px;color:#0f5b55} h2{margin-top:28px;color:#174743}
    p{line-height:1.5} .bullet{margin:4px 0;color:#334155}
    table{border-collapse:collapse;width:100%;margin:12px 0 22px;font-size:13px}
    th{background:#0f5b55;color:white;text-align:left;padding:9px;border:1px solid #d6e2e2}
    td{padding:8px;border:1px solid #d6e2e2;vertical-align:top}
    tr:nth-child(even){background:#f7fbfb}
    .disc{margin-top:28px;padding:12px;border-left:4px solid #f59e0b;background:#fffbeb}
    """
    return f"<!doctype html><html><head><meta charset='utf-8'><style>{css}</style></head><body><div class='wrap'>{''.join(body_lines)}</div></body></html>"


def build_report(
    config: StudyConfig,
    source_notes: list[str],
    bars: pd.DataFrame,
    trades: pd.DataFrame,
    leaderboard: pd.DataFrame,
    fno_context: pd.DataFrame | None = None,
    fno_regimes: pd.DataFrame | None = None,
    strategy_map_df: pd.DataFrame | None = None,
    rolling_stability: pd.DataFrame | None = None,
    walk_forward: pd.DataFrame | None = None,
    confirmed_symbol_drilldown: pd.DataFrame | None = None,
    confirmed_time_of_day: pd.DataFrame | None = None,
    volatility_regimes: pd.DataFrame | None = None,
    quant_thesis: pd.DataFrame | None = None,
    statistical_models: pd.DataFrame | None = None,
    *,
    generated_at: datetime | None = None,
) -> str:
    generated_at = generated_at or datetime.now(IST)
    lines = [
        "# Agent Adda Intraday F&O Indicator Study",
        "",
        f"- Generated: {generated_at.strftime('%Y-%m-%d %H:%M:%S IST')}",
        f"- Universe: {config.universe}",
        f"- Timeframes: {', '.join(config.timeframes)}",
        f"- Costs: slippage {config.slippage_bps} bps per side, brokerage {config.brokerage_bps} bps per side",
        f"- Max hold: {config.max_hold_bars} bars",
        f"- Source trail: {'; '.join(source_notes) if source_notes else 'not reported'}",
        "",
        "## Data Readiness",
        "",
        f"- Bars loaded: {len(bars)}",
        f"- Symbols with bars: {bars['symbol'].nunique() if not bars.empty else 0}",
        f"- Trade candidates tested: {len(trades)}",
        f"- Daily F&O context rows: {len(fno_context) if fno_context is not None else 0}",
    ]
    if bars.empty:
        lines += [
            "",
            "No intraday bars were available for this study. Start or backfill `intraday.ohlcv_bars`, or rerun with `--data <csv>`.",
        ]
    lines += [
        "",
        "## Indicator Leaderboard",
        "",
        _table_md(
            leaderboard,
            ["setup", "timeframe", "direction", "trades", "win_rate", "expectancy_r", "profit_factor", "avg_mfe_r", "avg_mae_r", "avg_hold_bars"],
            30,
        ),
        "",
        "## Best Current Interpretation",
        "",
    ]
    if leaderboard.empty:
        lines.append("No setup produced enough historical trades after filters. This is a data-coverage or rule-strictness problem, not proof that indicators do not work.")
    else:
        top = leaderboard.iloc[0]
        lines.append(
            f"The strongest tested combination was **{top['setup']}** on **{top['timeframe']}** for **{top['direction']}**, "
            f"with {int(top['trades'])} trades, {top['win_rate']:.1f}% win rate, and {top['expectancy_r']:.2f}R average expectancy after costs."
        )
        lines.append(
        "Use this as a candidate live-monitor rule, then validate it by market regime, time-of-day, symbol liquidity, and option-chain context before promoting it."
        )
    lines += [
        "",
        "## Quant Research Thesis",
        "",
    ]
    if quant_thesis is None or quant_thesis.empty:
        lines.append(
            "No quantitative thesis rows could be produced. This usually means the study needs more trades or wider historical coverage before a stability claim is defensible."
        )
    else:
        lines.append(
            _table_md(
                quant_thesis,
                [
                    "setup",
                    "timeframe",
                    "direction",
                    "thesis",
                    "trades",
                    "expectancy_r",
                    "profit_factor",
                    "positive_window_rate",
                    "stability_score",
                    "best_volatility_regime",
                    "best_pcr_regime",
                    "research_action",
                ],
                20,
            )
        )
        lines += [
            "",
            "### Thesis Interpretation",
            "",
            "- Candidate core: the setup has positive expectancy, acceptable profit factor, and rolling-window support.",
            "- Conditional regime edge: the setup needs volatility or F&O positioning filters before promotion.",
            "- Watch more history: promising but not yet stable enough for a global rule.",
            "- Reject global edge: avoid broad alerts; only symbol-specific research can revive it.",
        ]
    lines += [
        "",
        "## Rolling Window Stability",
        "",
    ]
    if rolling_stability is None or rolling_stability.empty:
        lines.append("Rolling stability was unavailable or the per-window sample was too small.")
    else:
        lines.append(
            _table_md(
                rolling_stability,
                [
                    "setup",
                    "timeframe",
                    "direction",
                    "windows",
                    "total_trades",
                    "avg_expectancy_r",
                    "std_expectancy_r",
                    "positive_window_rate",
                    "worst_window_r",
                    "best_window_r",
                    "stability_score",
                ],
                25,
            )
        )
    lines += [
        "",
        "## Walk-Forward Validation",
        "",
    ]
    if walk_forward is None or walk_forward.empty:
        lines.append(
            "Walk-forward validation was unavailable. This usually means the setup did not have enough chronological train/validation trades after filters."
        )
    else:
        lines.append(
            _table_md(
                walk_forward,
                [
                    "setup",
                    "timeframe",
                    "direction",
                    "walk_forward_status",
                    "folds_tested",
                    "promoted_folds",
                    "validation_trades",
                    "train_expectancy_r",
                    "train_profit_factor",
                    "validation_expectancy_r",
                    "validation_win_rate",
                    "validation_profit_factor",
                    "validation_positive_fold_rate",
                    "worst_validation_r",
                ],
                25,
            )
        )
        lines += [
            "",
            "Model note: each validation fold is unseen by the training gate. Confirmed setups survived prior-window promotion and positive next-window validation.",
        ]
    lines += [
        "",
        "## Confirmed Setup Symbol Drilldown",
        "",
    ]
    if confirmed_symbol_drilldown is None or confirmed_symbol_drilldown.empty:
        lines.append(
            "No symbol-level carrier table was available for the confirmed setup. Increase history or lower the minimum symbol-trade threshold for exploratory research."
        )
    else:
        lines.append(
            _table_md(
                confirmed_symbol_drilldown,
                [
                    "symbol",
                    "symbol_edge_status",
                    "setup",
                    "timeframe",
                    "direction",
                    "trades",
                    "win_rate",
                    "expectancy_r",
                    "profit_factor",
                    "avg_mfe_r",
                    "avg_mae_r",
                    "best_volatility_regime",
                    "best_pcr_regime",
                ],
                40,
            )
        )
        lines += [
            "",
            "Interpretation: core carriers are the symbols most responsible for the confirmed aggregate edge; edge diluters should be blocked or require stronger live confluence.",
        ]
    lines += [
        "",
        "## Confirmed Setup Time-of-Day Filter",
        "",
    ]
    if confirmed_time_of_day is None or confirmed_time_of_day.empty:
        lines.append("No time-of-day table was available for the confirmed setup.")
    else:
        lines.append(
            _table_md(
                confirmed_time_of_day,
                ["setup", "timeframe", "direction", "time_bucket", "trades", "win_rate", "expectancy_r", "profit_factor", "avg_mfe_r", "avg_mae_r"],
                12,
            )
        )
        lines += [
            "",
            "Interpretation: use the strongest positive time bucket as the first live-alert window; suppress weak buckets unless another live catalyst is present.",
        ]
    lines += [
        "",
        "## Volatility Regime Read-Through",
        "",
    ]
    if volatility_regimes is None or volatility_regimes.empty:
        lines.append(
            "Volatility regime analysis was unavailable. The first-pass model uses EWMA intraday return volatility; true GARCH can be added after this scaffold proves useful."
        )
    else:
        lines.append(
            _table_md(
                volatility_regimes,
                ["setup", "timeframe", "direction", "volatility_regime", "trades", "win_rate", "expectancy_r", "profit_factor"],
                30,
            )
        )
        lines += [
            "",
            "Model note: volatility regimes are EWMA-return buckets (`low`, `normal`, `high`), not a fitted GARCH forecast. Treat them as a robust proxy for this first research pass.",
        ]
    lines += [
        "",
        "## Statistical Model Diagnostics",
        "",
    ]
    if statistical_models is None or statistical_models.empty:
        lines.append(
            "Statistical model diagnostics were unavailable. Add enough intraday history and optional packages (`statsmodels`, `arch`) for AutoReg/ARIMA and GARCH model fits."
        )
    else:
        lines.append(
            _table_md(
                statistical_models,
                [
                    "symbol",
                    "timeframe",
                    "model_type",
                    "status",
                    "observations",
                    "mean_return_bps",
                    "volatility_bps",
                    "persistence",
                    "t_stat",
                    "forecast_vol_pct",
                    "volatility_clustering",
                    "bias",
                    "note",
                ],
                36,
            )
        )
        lines += [
            "",
            "Model note: `ar1_ols` is a dependency-free return-persistence diagnostic. `statsmodels_autoreg_1` and `garch_11` are fitted only when optional packages are installed.",
        ]
    lines += [
        "",
        "## Symbol Strategy Map",
        "",
    ]
    if strategy_map_df is None or strategy_map_df.empty:
        lines.append(
            "No per-symbol strategy map could be produced. This usually means no trades survived the historical filters or the symbol had insufficient intraday bars."
        )
    else:
        lines.append(
            _table_md(
                strategy_map_df,
                ["symbol", "status", "setup", "timeframe", "direction", "trades", "win_rate", "expectancy_r", "profit_factor"],
                80,
            )
        )
        lines += [
            "",
            "### How To Use The Map",
            "",
            "- Promoted: eligible for live intraday alerts when live price, volume, liquidity, and F&O context still agree.",
            "- Watch candidate: monitor, but require stronger live confirmation or smaller sizing.",
            "- Avoid: suppress routine alerts unless there is an exceptional live catalyst or regime shift.",
            "- Insufficient data: do not infer a symbol-specific edge; use only live confluence and manual validation.",
        ]
    lines += [
        "",
        "## F&O Context Read-Through",
        "",
    ]
    if fno_context is None or fno_context.empty:
        lines.append("Historical daily F&O context was not available for the tested symbols. This run remains a price-action-only intraday validation.")
    else:
        latest = fno_context.sort_values("trade_date").groupby("symbol", as_index=False).tail(1)
        lines.append(
            _table_md(
                latest,
                ["symbol", "trade_date", "expiry_date", "pcr", "pcr_regime", "max_pain", "max_pain_distance_pct", "ce_wall", "pe_floor"],
                20,
            )
        )
        if fno_regimes is not None and not fno_regimes.empty:
            lines += [
                "",
                "### Setup Performance By PCR Regime",
                "",
                _table_md(
                    fno_regimes,
                    ["setup", "timeframe", "direction", "pcr_regime", "trades", "win_rate", "expectancy_r", "profit_factor"],
                    30,
                ),
            ]
    lines += [
        "",
        "## Recent Sample Trades",
        "",
        _table_md(
            trades.sort_values("entry_ts", ascending=False) if not trades.empty else trades,
            ["symbol", "timeframe", "setup", "direction", "entry_ts", "entry", "stop", "target", "exit_reason", "r", "pcr_regime", "max_pain", "note"],
            25,
        ),
        "",
        "## Research Notes",
        "",
        "- True options-context conclusions require historical option-chain snapshots. Without those, this report measures F&O-eligible price-action setups, not full options payoff behavior.",
        "- Compare results by trend/range regime before using any single indicator globally.",
        "- The symbol map is a soft gate for live alerts. It should be refreshed after each data backfill and reviewed when market regime changes.",
        "- Promote only setups that survive stricter liquidity, spread, slippage, max-loss, and time-of-day assumptions.",
        "",
        '<div class="disc">Research only. Not investment advice. Historical backtests are not a guarantee of future outcomes. Validate liquidity, spreads, execution, and risk before acting.</div>',
    ]
    return "\n".join(lines)


def write_report(markdown: str, output_dir: Path | str, strategy_map: dict[str, Any] | None = None) -> dict[str, str]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(IST).strftime("%Y%m%d_%H%M%S")
    md_path = out_dir / f"intraday_fno_indicator_study_{stamp}.md"
    html_path = out_dir / f"intraday_fno_indicator_study_{stamp}.html"
    map_path = out_dir / f"intraday_fno_strategy_map_{stamp}.json"
    md_path.write_text(markdown, encoding="utf-8")
    html_path.write_text(_markdown_to_html(markdown), encoding="utf-8")
    if strategy_map is not None:
        map_path.write_text(json.dumps(strategy_map, indent=2, sort_keys=True), encoding="utf-8")
    latest_dir = Path("reports/latest")
    latest_dir.mkdir(parents=True, exist_ok=True)
    latest_md = latest_dir / "intraday_fno_indicator_study.md"
    latest_html = latest_dir / "intraday_fno_indicator_study.html"
    latest_map = latest_dir / "intraday_fno_strategy_map.json"
    try:
        shutil.copyfile(md_path, latest_md)
        shutil.copyfile(html_path, latest_html)
        if strategy_map is not None:
            shutil.copyfile(map_path, latest_map)
    except OSError:
        pass
    paths = {
        "markdown": str(md_path),
        "html": str(html_path),
        "latest_markdown": str(latest_md),
        "latest_html": str(latest_html),
    }
    if strategy_map is not None:
        paths["strategy_map"] = str(map_path)
        paths["latest_strategy_map"] = str(latest_map)
    return paths


def persist_intraday_edge_nodes(
    *,
    config: StudyConfig,
    confirmed_symbol_drilldown: pd.DataFrame,
    walk_forward: pd.DataFrame,
    report_paths: dict[str, str],
    bars_count: int,
    symbol_count: int,
    trade_count: int,
    dsn: str | None = None,
) -> dict[str, Any]:
    generated_at = datetime.now(IST)
    evidence_set_id = f"intraday_fno:{generated_at:%Y%m%d_%H%M%S}"
    source_report = report_paths.get("html") or report_paths.get("latest_html") or ""
    code_version = get_code_version(Path.cwd())
    with _connect_pg(dsn) as conn:
        persistence_counts = fetch_persistence_counts(conn)
        nodes = build_edge_nodes(
            confirmed_symbol_drilldown=confirmed_symbol_drilldown,
            walk_forward=walk_forward,
            evidence_set_id=evidence_set_id,
            bar_count=bars_count,
            code_version=code_version,
            generated_at=generated_at,
            persistence_counts=persistence_counts,
        )
        refresh = make_refresh_run(
            evidence_set_id=evidence_set_id,
            source_report=source_report,
            bar_count=bars_count,
            symbol_count=symbol_count,
            trade_count=trade_count,
            code_version=code_version,
            generated_at=generated_at,
        )
        result = persist_edge_nodes(conn, refresh, nodes)
    result["source_report"] = source_report
    return result


def run_intraday_indicator_study(config: StudyConfig, *, dsn: str | None = None) -> dict[str, Any]:
    bars, notes = load_intraday_bars(config, dsn=dsn)
    features = prepare_features(bars) if not bars.empty else pd.DataFrame()
    trades, leaderboard = run_indicator_backtest(features, config) if not features.empty else (pd.DataFrame(), pd.DataFrame())
    volatility_context = build_volatility_context(features) if not features.empty else pd.DataFrame()
    trades = enrich_trades_with_quant_context(trades, volatility_context)
    volatility_regimes = volatility_regime_leaderboard(trades)
    rolling_stability = rolling_window_stability(trades)
    walk_forward = walk_forward_validation(trades)
    confirmed_symbol_drilldown = confirmed_setup_symbol_drilldown(trades)
    confirmed_time_of_day = time_of_day_leaderboard(trades)
    statistical_models = build_statistical_model_diagnostics(features) if not features.empty else pd.DataFrame()
    fno_context = pd.DataFrame()
    fno_regimes = pd.DataFrame()
    if config.include_fno_context and not bars.empty:
        start = config.start or str(pd.to_datetime(bars["timestamp"]).min().date())
        end = config.end or str(pd.to_datetime(bars["timestamp"]).max().date())
        fno_context, fno_notes = load_fno_daily_context(
            sorted(bars["symbol"].dropna().astype(str).str.upper().unique().tolist()),
            start=start,
            end=end,
            dsn=dsn,
        )
        notes.extend(fno_notes)
        trades = enrich_trades_with_fno_context(trades, fno_context)
        fno_regimes = fno_regime_leaderboard(trades)
    quant_thesis = build_quant_research_thesis(leaderboard, rolling_stability, volatility_regimes, fno_regimes)
    loaded_symbols = set(bars["symbol"].dropna().astype(str).str.upper().unique().tolist()) if not bars.empty else set()
    requested_symbols = {str(symbol).strip().upper() for symbol in config.symbols if str(symbol).strip()}
    map_symbols = sorted(loaded_symbols | requested_symbols)
    strategy_map = build_strategy_map(trades, map_symbols, config)
    strategy_frame = strategy_map_frame(strategy_map)
    markdown = build_report(
        config,
        notes,
        bars,
        trades,
        leaderboard,
        fno_context,
        fno_regimes,
        strategy_frame,
        rolling_stability,
        walk_forward,
        confirmed_symbol_drilldown,
        confirmed_time_of_day,
        volatility_regimes,
        quant_thesis,
        statistical_models,
    )
    paths = write_report(markdown, config.output_dir, strategy_map)
    edge_persistence = None
    if config.persist_edges:
        edge_persistence = persist_intraday_edge_nodes(
            config=config,
            confirmed_symbol_drilldown=confirmed_symbol_drilldown,
            walk_forward=walk_forward,
            report_paths=paths,
            bars_count=len(bars),
            symbol_count=int(bars["symbol"].nunique()) if not bars.empty else 0,
            trade_count=len(trades),
            dsn=dsn,
        )
    return {
        "ok": not bars.empty,
        "bars": len(bars),
        "symbols": int(bars["symbol"].nunique()) if not bars.empty else 0,
        "trades": len(trades),
        "leaderboard": leaderboard,
        "strategy_map": strategy_map,
        "strategy_map_frame": strategy_frame,
        "fno_context": fno_context,
        "fno_regime_leaderboard": fno_regimes,
        "volatility_context": volatility_context,
        "volatility_regime_leaderboard": volatility_regimes,
        "rolling_stability": rolling_stability,
        "walk_forward_validation": walk_forward,
        "confirmed_symbol_drilldown": confirmed_symbol_drilldown,
        "confirmed_time_of_day": confirmed_time_of_day,
        "quant_thesis": quant_thesis,
        "statistical_model_diagnostics": statistical_models,
        "trade_log": trades,
        "source_notes": notes,
        "report": paths,
        "edge_persistence": edge_persistence,
        "markdown": markdown,
    }
