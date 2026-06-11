from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import pandas as pd


DEFAULT_DSN = (
    os.environ.get("AGENT_ADDA_PG_DSN")
    or os.environ.get("PG_DSN")
    or "dbname=nse_market user=nse_admin host=/tmp"
)


@dataclass(frozen=True)
class PostgresReplayData:
    features: pd.DataFrame
    benchmark: pd.DataFrame
    latest_eod_date: str


def default_dsn() -> str:
    return os.environ.get("AGENT_ADDA_PG_DSN") or os.environ.get("PG_DSN") or DEFAULT_DSN


def load_postgres_replay_data(
    *,
    dsn: str,
    start_date: str,
    lookback_date: str,
    end_date: str | None,
    top_n: int,
    benchmark_id: str = "Nifty 500",
) -> PostgresReplayData:
    """Load NSE EOD replay features using scores.stage_snapshots as stage source."""

    import psycopg2

    with psycopg2.connect(dsn) as conn:
        latest_eod_date = _latest_eod_date(conn, end_date=end_date)
        top_symbols = _top_liquid_symbols(conn, latest_eod_date=latest_eod_date, top_n=top_n)
        eod = _load_eod(conn, lookback_date=lookback_date, end_date=end_date, symbols=top_symbols)
        stage = _load_stage_snapshots(conn, lookback_date=lookback_date, end_date=end_date, symbols=top_symbols)
        vcp_picks = _load_vcp_picks(conn, lookback_date=lookback_date, end_date=end_date, symbols=top_symbols)
        fundamentals = _load_fundamentals(conn, symbols=top_symbols)
        benchmark = _load_benchmark(conn, start_date=start_date, end_date=end_date, benchmark_id=benchmark_id)

    features = prepare_replay_frame(
        eod,
        stage,
        vcp_picks=vcp_picks,
        fundamentals=fundamentals,
        start_date=start_date,
    )
    return PostgresReplayData(
        features=features,
        benchmark=benchmark,
        latest_eod_date=str(latest_eod_date),
    )


def prepare_replay_frame(
    eod: pd.DataFrame,
    stage_snapshots: pd.DataFrame,
    *,
    vcp_picks: pd.DataFrame | None = None,
    fundamentals: pd.DataFrame | None = None,
    start_date: str,
) -> pd.DataFrame:
    """Build portfolio-engine replay columns from EOD + historical stage snapshots."""

    raw = _normalize_eod(eod)
    if raw.empty:
        return _empty_replay_frame()
    stages = _normalize_stage_snapshots(stage_snapshots)
    if not stages.empty:
        raw = raw.merge(stages, on=["date", "symbol"], how="left")
    else:
        raw["stage"] = None
    raw = _merge_vcp_picks(raw, vcp_picks)
    raw = _merge_fundamentals(raw, fundamentals)
    raw = raw.sort_values(["symbol", "date"]).reset_index(drop=True)

    grouped = raw.groupby("symbol", group_keys=False)
    raw["sma_20"] = grouped["close"].transform(lambda series: series.rolling(20, min_periods=20).mean())
    raw["sma_50"] = grouped["close"].transform(lambda series: series.rolling(50, min_periods=50).mean())
    raw["sma_100"] = grouped["close"].transform(lambda series: series.rolling(100, min_periods=100).mean())
    raw["sma_200"] = grouped["close"].transform(lambda series: series.rolling(200, min_periods=200).mean())
    raw["ema_20"] = grouped["close"].transform(lambda series: series.ewm(span=20, adjust=False, min_periods=20).mean())
    raw["ema_50"] = grouped["close"].transform(lambda series: series.ewm(span=50, adjust=False, min_periods=50).mean())

    previous_close = grouped["close"].shift(1)
    true_range = pd.concat(
        [
            raw["high"] - raw["low"],
            (raw["high"] - previous_close).abs(),
            (raw["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    raw["atr_14"] = true_range.groupby(raw["symbol"]).transform(lambda series: series.rolling(14, min_periods=14).mean())
    raw["rsi_14"] = raw.get("snapshot_rsi", pd.Series(index=raw.index, dtype="float64")).fillna(_rsi(raw))
    volume_average = grouped["volume"].transform(lambda series: series.rolling(20, min_periods=20).mean())
    raw["volume_ratio_20d"] = (raw["volume"] / volume_average.replace(0, pd.NA)).fillna(0)
    raw["return_63d"] = grouped["close"].pct_change(63)
    computed_rs = raw.groupby("date")["return_63d"].rank(pct=True).mul(100).fillna(50)
    raw["relative_strength"] = raw.get(
        "snapshot_relative_strength",
        pd.Series(index=raw.index, dtype="float64"),
    ).fillna(computed_rs)
    raw["weekly_stage"] = raw["stage"]
    raw["trailing_stop"] = 0

    for column in (
        "sales_growth_pct",
        "pat_growth_pct",
        "eps_growth_pct",
        "revenue_qoq_pct",
        "pat_qoq_pct",
        "eps_qoq_pct",
        "opm_pct",
        "opm_yoy_delta",
        "roe_pct",
        "roce_pct",
        "debt_to_equity",
        "annual_sales_growth_pct",
        "annual_pat_growth_pct",
    ):
        if column not in raw.columns:
            raw[column] = 0.0
        raw[column] = pd.to_numeric(raw[column], errors="coerce").fillna(0.0)
    if "latest_result_age_days" not in raw.columns:
        raw["latest_result_age_days"] = 9999.0
    raw["latest_result_age_days"] = pd.to_numeric(raw["latest_result_age_days"], errors="coerce").fillna(9999.0)
    if "latest_result_period" not in raw.columns:
        raw["latest_result_period"] = ""
    raw["latest_result_period"] = raw["latest_result_period"].fillna("").astype(str)

    features = raw.loc[pd.to_datetime(raw["date"]) >= pd.to_datetime(start_date), _FEATURE_COLUMNS].copy()
    features = features.dropna(subset=["stage", "sma_20", "sma_50", "sma_100", "sma_200", "atr_14"])
    features = features.sort_values(["date", "symbol"]).reset_index(drop=True)
    features["date"] = pd.to_datetime(features["date"]).dt.strftime("%Y-%m-%d")
    return features


def _latest_eod_date(conn: Any, *, end_date: str | None) -> Any:
    if end_date:
        return pd.to_datetime(end_date).date()
    row = pd.read_sql_query(
        "SELECT max(trade_date) AS trade_date FROM market.equity_eod WHERE series='EQ'",
        conn,
    ).iloc[0]
    return row["trade_date"]


def _top_liquid_symbols(conn: Any, *, latest_eod_date: Any, top_n: int) -> list[str]:
    rows = pd.read_sql_query(
        """
        SELECT symbol
        FROM market.equity_eod
        WHERE trade_date = %s AND series = 'EQ' AND close > 50 AND volume > 0
        ORDER BY turnover_cr DESC NULLS LAST, volume DESC NULLS LAST
        LIMIT %s
        """,
        conn,
        params=[latest_eod_date, int(top_n)],
    )
    return rows["symbol"].astype(str).str.upper().tolist()


def _load_eod(conn: Any, *, lookback_date: str, end_date: str | None, symbols: list[str]) -> pd.DataFrame:
    end_clause = "AND trade_date <= %(end_date)s" if end_date else ""
    return pd.read_sql_query(
        f"""
        SELECT trade_date AS date, symbol, open, high, low, close, volume, turnover_cr
        FROM market.equity_eod
        WHERE series = 'EQ'
          AND trade_date >= %(lookback_date)s
          AND symbol = ANY(%(symbols)s)
          AND open > 0 AND high > 0 AND low > 0 AND close > 0 AND volume > 0
          {end_clause}
        ORDER BY trade_date, symbol
        """,
        conn,
        params={"lookback_date": lookback_date, "end_date": end_date, "symbols": symbols},
    )


def _load_stage_snapshots(conn: Any, *, lookback_date: str, end_date: str | None, symbols: list[str]) -> pd.DataFrame:
    end_clause = "AND snapshot_date <= %(end_date)s" if end_date else ""
    return pd.read_sql_query(
        f"""
        SELECT
            snapshot_date AS date,
            symbol,
            stage,
            relative_strength AS snapshot_relative_strength,
            rsi AS snapshot_rsi
        FROM scores.stage_snapshots
        WHERE snapshot_date >= %(lookback_date)s
          AND symbol = ANY(%(symbols)s)
          {end_clause}
        """,
        conn,
        params={"lookback_date": lookback_date, "end_date": end_date, "symbols": symbols},
    )


def _load_vcp_picks(conn: Any, *, lookback_date: str, end_date: str | None, symbols: list[str]) -> pd.DataFrame:
    end_clause = "AND snapshot_date <= %(end_date)s" if end_date else ""
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('scores.stage2_vcp_picks')")
            if cur.fetchone()[0] is None:
                return pd.DataFrame()
    except Exception:
        return pd.DataFrame()
    return pd.read_sql_query(
        f"""
        SELECT
            snapshot_date AS date,
            symbol,
            rank AS vcp_rank,
            vcp_score,
            vcp_breakout_pct,
            vcp_contraction_pct
        FROM scores.stage2_vcp_picks
        WHERE snapshot_date >= %(lookback_date)s
          AND symbol = ANY(%(symbols)s)
          {end_clause}
        """,
        conn,
        params={"lookback_date": lookback_date, "end_date": end_date, "symbols": symbols},
    )


def _load_fundamentals(conn: Any, *, symbols: list[str]) -> pd.DataFrame:
    quarterly = pd.read_sql_query(
        """
        SELECT
            symbol,
            period_end,
            revenue,
            pat,
            eps,
            opm_pct
        FROM scores.quarterly_results
        WHERE symbol = ANY(%s)
          AND period_end IS NOT NULL
        """,
        conn,
        params=[symbols],
    )
    static = pd.read_sql_query(
        """
        SELECT
            symbol,
            revenue_growth_3y AS annual_sales_growth_pct,
            pat_growth_3y AS annual_pat_growth_pct,
            roe AS roe_pct,
            roce AS roce_pct,
            debt_to_equity
        FROM scores.fundamentals
        WHERE symbol = ANY(%s)
        """,
        conn,
        params=[symbols],
    )
    if quarterly.empty:
        return static
    if static.empty:
        return quarterly
    quarterly["symbol"] = quarterly["symbol"].astype(str).str.upper().str.strip()
    static["symbol"] = static["symbol"].astype(str).str.upper().str.strip()
    return quarterly.merge(static, on="symbol", how="left")


def _load_benchmark(conn: Any, *, start_date: str, end_date: str | None, benchmark_id: str) -> pd.DataFrame:
    end_clause = "AND trade_date <= %(end_date)s" if end_date else ""
    rows = pd.read_sql_query(
        f"""
        SELECT trade_date AS date, close
        FROM market.index_eod
        WHERE index_symbol = %(benchmark_id)s
          AND trade_date >= %(start_date)s
          {end_clause}
        ORDER BY trade_date
        """,
        conn,
        params={"benchmark_id": benchmark_id, "start_date": start_date, "end_date": end_date},
    )
    if not rows.empty:
        rows["date"] = pd.to_datetime(rows["date"])
    return rows


def _normalize_eod(eod: pd.DataFrame) -> pd.DataFrame:
    out = eod.rename(columns={column: column.strip().lower() for column in eod.columns}).copy()
    out = out.rename(columns={"trade_date": "date"})
    for column in ("date", "symbol", "open", "high", "low", "close", "volume"):
        if column not in out.columns:
            raise ValueError(f"PostgreSQL EOD data missing required column: {column}")
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out["symbol"] = out["symbol"].astype(str).str.upper().str.strip()
    for column in ("open", "high", "low", "close", "volume", "turnover_cr"):
        if column not in out.columns:
            out[column] = 0.0
        out[column] = pd.to_numeric(out[column], errors="coerce")
    return out.dropna(subset=["date", "symbol", "open", "high", "low", "close", "volume"])


def _normalize_stage_snapshots(stage_snapshots: pd.DataFrame) -> pd.DataFrame:
    if stage_snapshots.empty:
        return pd.DataFrame(columns=["date", "symbol", "stage"])
    out = stage_snapshots.rename(columns={column: column.strip().lower() for column in stage_snapshots.columns}).copy()
    out = out.rename(columns={"snapshot_date": "date", "relative_strength": "snapshot_relative_strength", "rsi": "snapshot_rsi"})
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out["symbol"] = out["symbol"].astype(str).str.upper().str.strip()
    out["stage"] = out["stage"].astype(str).str.upper().str.strip()
    for column in ("snapshot_relative_strength", "snapshot_rsi"):
        if column not in out.columns:
            out[column] = pd.NA
        out[column] = pd.to_numeric(out[column], errors="coerce")
    return out.dropna(subset=["date", "symbol", "stage"]).loc[
        :, ["date", "symbol", "stage", "snapshot_relative_strength", "snapshot_rsi"]
    ]


def _merge_fundamentals(raw: pd.DataFrame, fundamentals: pd.DataFrame | None) -> pd.DataFrame:
    if fundamentals is None or fundamentals.empty:
        return raw
    fund = fundamentals.rename(columns={column: column.strip().lower() for column in fundamentals.columns}).copy()
    fund["symbol"] = fund["symbol"].astype(str).str.upper().str.strip()
    if "period_end" in fund.columns:
        return _merge_quarterly_fundamentals(raw, fund)
    return raw.merge(fund, on="symbol", how="left")


def _merge_vcp_picks(raw: pd.DataFrame, vcp_picks: pd.DataFrame | None) -> pd.DataFrame:
    out = raw.copy()
    metric_columns = ["vcp_rank", "vcp_score", "vcp_breakout_pct", "vcp_contraction_pct"]
    if vcp_picks is None or vcp_picks.empty:
        out["vcp_pick"] = 0
        for column in metric_columns:
            out[column] = 0.0
        return out

    picks = vcp_picks.rename(columns={column: column.strip().lower() for column in vcp_picks.columns}).copy()
    picks = picks.rename(columns={"snapshot_date": "date", "rank": "vcp_rank"})
    picks["date"] = pd.to_datetime(picks["date"], errors="coerce")
    picks["symbol"] = picks["symbol"].astype(str).str.upper().str.strip()
    for column in metric_columns:
        if column not in picks.columns:
            picks[column] = 0.0
        picks[column] = pd.to_numeric(picks[column], errors="coerce").fillna(0.0)
    picks = picks.dropna(subset=["date", "symbol"]).loc[:, ["date", "symbol", *metric_columns]]
    picks = picks.drop_duplicates(subset=["date", "symbol"], keep="last")
    picks["vcp_pick"] = 1

    out = out.merge(picks, on=["date", "symbol"], how="left")
    out["vcp_pick"] = pd.to_numeric(out["vcp_pick"], errors="coerce").fillna(0).astype(int)
    for column in metric_columns:
        out[column] = pd.to_numeric(out[column], errors="coerce").fillna(0.0)
    return out


def _merge_quarterly_fundamentals(raw: pd.DataFrame, fund: pd.DataFrame) -> pd.DataFrame:
    fund["period_end"] = pd.to_datetime(fund["period_end"], errors="coerce").astype("datetime64[ns]")
    fund = fund.dropna(subset=["symbol", "period_end"]).copy()
    if fund.empty:
        return raw
    for column in (
        "revenue",
        "pat",
        "eps",
        "opm_pct",
        "roe_pct",
        "roce_pct",
        "debt_to_equity",
        "annual_sales_growth_pct",
        "annual_pat_growth_pct",
    ):
        if column not in fund.columns:
            fund[column] = pd.NA
        fund[column] = pd.to_numeric(fund[column], errors="coerce")
    if "availability_date" not in fund.columns:
        fund["availability_date"] = fund["period_end"] + pd.Timedelta(days=45)
    else:
        fund["availability_date"] = pd.to_datetime(fund["availability_date"], errors="coerce")
    fund["availability_date"] = fund["availability_date"].astype("datetime64[ns]")
    fund = fund.dropna(subset=["availability_date"]).sort_values(["symbol", "period_end"])

    grouped = fund.groupby("symbol", group_keys=False)
    fund["sales_growth_pct"] = grouped["revenue"].transform(lambda series: _pct_change_series(series, 4))
    fund["pat_growth_pct"] = grouped["pat"].transform(lambda series: _pct_change_series(series, 4))
    fund["eps_growth_pct"] = grouped["eps"].transform(lambda series: _pct_change_series(series, 4))
    fund["revenue_qoq_pct"] = grouped["revenue"].transform(lambda series: _pct_change_series(series, 1))
    fund["pat_qoq_pct"] = grouped["pat"].transform(lambda series: _pct_change_series(series, 1))
    fund["eps_qoq_pct"] = grouped["eps"].transform(lambda series: _pct_change_series(series, 1))
    fund["opm_yoy_delta"] = grouped["opm_pct"].transform(lambda series: (series - series.shift(4)).round(4))
    fund["latest_result_period"] = fund["period_end"].dt.strftime("%Y-%m-%d")

    merge_columns = [
        "availability_date",
        "latest_result_period",
        "sales_growth_pct",
        "pat_growth_pct",
        "eps_growth_pct",
        "revenue_qoq_pct",
        "pat_qoq_pct",
        "eps_qoq_pct",
        "opm_pct",
        "opm_yoy_delta",
        "roe_pct",
        "roce_pct",
        "debt_to_equity",
        "annual_sales_growth_pct",
        "annual_pat_growth_pct",
    ]
    merged = []
    for symbol, symbol_raw in raw.sort_values(["symbol", "date"]).groupby("symbol", sort=False):
        symbol_raw = symbol_raw.copy()
        symbol_raw["date"] = pd.to_datetime(symbol_raw["date"], errors="coerce").astype("datetime64[ns]")
        symbol_fund = fund.loc[fund["symbol"] == symbol, merge_columns].sort_values("availability_date")
        if symbol_fund.empty:
            merged.append(symbol_raw.copy())
            continue
        joined = pd.merge_asof(
            symbol_raw.sort_values("date"),
            symbol_fund,
            left_on="date",
            right_on="availability_date",
            direction="backward",
        )
        merged.append(joined)
    out = pd.concat(merged, ignore_index=True) if merged else raw
    out["latest_result_age_days"] = (out["date"] - out["availability_date"]).dt.days
    return out.drop(columns=["availability_date"], errors="ignore")


def _pct_change_series(series: pd.Series, periods: int) -> pd.Series:
    previous = series.shift(periods)
    out = ((series - previous) / previous.abs() * 100.0).where(previous.notna() & (previous != 0))
    return out.round(4)


def _rsi(raw: pd.DataFrame) -> pd.Series:
    delta = raw.groupby("symbol")["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.groupby(raw["symbol"]).transform(lambda series: series.rolling(14, min_periods=14).mean())
    avg_loss = loss.groupby(raw["symbol"]).transform(lambda series: series.rolling(14, min_periods=14).mean())
    rs = avg_gain / avg_loss.replace(0, pd.NA)
    return (100 - (100 / (1 + rs))).fillna(50).clip(0, 100)


def _empty_replay_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=_FEATURE_COLUMNS)


_FEATURE_COLUMNS = [
    "date",
    "symbol",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "stage",
    "weekly_stage",
    "sma_20",
    "sma_50",
    "sma_100",
    "sma_200",
    "ema_20",
    "ema_50",
    "rsi_14",
    "atr_14",
    "volume_ratio_20d",
    "relative_strength",
    "trailing_stop",
    "sales_growth_pct",
    "pat_growth_pct",
    "eps_growth_pct",
    "revenue_qoq_pct",
    "pat_qoq_pct",
    "eps_qoq_pct",
    "opm_pct",
    "opm_yoy_delta",
    "roe_pct",
    "roce_pct",
    "debt_to_equity",
    "annual_sales_growth_pct",
    "annual_pat_growth_pct",
    "latest_result_age_days",
    "latest_result_period",
    "turnover_cr",
    "vcp_pick",
    "vcp_rank",
    "vcp_score",
    "vcp_breakout_pct",
    "vcp_contraction_pct",
]
