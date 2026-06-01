"""Backfill deterministic historical Weinstein stage snapshots from NSE EOD data."""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from typing import Any, Iterable

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values


DEFAULT_DSN = (
    os.environ.get("AGENT_ADDA_PG_DSN")
    or os.environ.get("PG_DSN")
    or "dbname=nse_market user=nse_admin host=/tmp"
)
SOURCE_TAG = "historical_stage_backfill:market.equity_eod"


@dataclass(frozen=True)
class BackfillSummary:
    start_date: str
    end_date: str
    row_count: int
    symbol_count: int
    stage_counts: dict[str, int]
    change_count: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "start_date": self.start_date,
            "end_date": self.end_date,
            "row_count": self.row_count,
            "symbol_count": self.symbol_count,
            "stage_counts": dict(self.stage_counts),
            "change_count": self.change_count,
        }


def compute_historical_stage_features(
    data: pd.DataFrame,
    *,
    start_date: str | pd.Timestamp,
) -> pd.DataFrame:
    """Compute deterministic daily stage features using only prior/current EOD bars."""

    frame = _normalize_eod(data)
    if frame.empty:
        return _empty_features()

    pieces: list[pd.DataFrame] = []
    for _, symbol_frame in frame.groupby("symbol", sort=True):
        out = symbol_frame.copy()
        close = out["close"]
        high = out["high"]
        low = out["low"]
        prev_close = close.shift(1)
        true_range = pd.concat(
            [
                high - low,
                (high - prev_close).abs(),
                (low - prev_close).abs(),
            ],
            axis=1,
        ).max(axis=1)
        out["sma_20"] = close.rolling(20, min_periods=20).mean()
        out["sma_50"] = close.rolling(50, min_periods=50).mean()
        out["sma_100"] = close.rolling(100, min_periods=100).mean()
        out["sma_150"] = close.rolling(150, min_periods=150).mean()
        out["sma_200"] = close.rolling(200, min_periods=200).mean()
        out["ema_20"] = close.ewm(span=20, adjust=False, min_periods=20).mean()
        out["ema_50"] = close.ewm(span=50, adjust=False, min_periods=50).mean()
        out["atr_14"] = true_range.rolling(14, min_periods=14).mean()
        out["high_52w"] = high.rolling(252, min_periods=50).max()
        out["low_52w"] = low.rolling(252, min_periods=50).min()
        out["return_63d"] = close.pct_change(63)
        out["change_1d_pct"] = close.pct_change(1).mul(100)
        out["change_1w_pct"] = close.pct_change(5).mul(100)
        out["change_1m_pct"] = close.pct_change(21).mul(100)
        out["rsi"] = _rsi(close)
        out["volume_ratio_20d"] = out["volume"] / out["volume"].rolling(20, min_periods=20).mean()
        pieces.append(out)

    enriched = pd.concat(pieces, ignore_index=True).sort_values(["date", "symbol"]).reset_index(drop=True)
    enriched["relative_strength"] = (
        enriched.groupby("date")["return_63d"].rank(pct=True, method="average").mul(100).fillna(50.0)
    )
    enriched["stage"] = _classify_stage(enriched)
    enriched["stage_score"] = _stage_score(enriched)
    enriched["technical_score"] = _technical_score(enriched)
    enriched["trend_signal"] = enriched["stage"].map(
        {
            "STAGE_2": "BULLISH",
            "STAGE_4": "BEARISH",
            "STAGE_3": "WEAKENING",
            "STAGE_1": "NEUTRAL",
        }
    )
    enriched["trading_signal"] = enriched["stage"].map(
        {
            "STAGE_2": "BUY",
            "STAGE_4": "SELL",
            "STAGE_3": "HOLD",
            "STAGE_1": "HOLD",
        }
    )
    enriched["stance"] = enriched["stage"].map(
        {
            "STAGE_2": "BULLISH",
            "STAGE_4": "BEARISH",
            "STAGE_3": "NEUTRAL",
            "STAGE_1": "NEUTRAL",
        }
    )
    enriched["investment_score"] = (
        enriched["technical_score"].fillna(0) * 0.7
        + enriched["relative_strength"].fillna(50) * 0.3
    ).clip(0, 100)
    enriched["narrative"] = enriched.apply(_narrative, axis=1)

    start = pd.to_datetime(start_date)
    filtered = enriched[enriched["date"] >= start].copy()
    return filtered.sort_values(["date", "symbol"]).reset_index(drop=True)


def build_stage_snapshot_rows(features: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in features.itertuples(index=False):
        snapshot_date = _date(getattr(row, "date"))
        symbol = str(getattr(row, "symbol")).upper()
        rows.append(
            {
                "snapshot_date": snapshot_date,
                "symbol": symbol,
                "company_name": _text(getattr(row, "company_name", None)) or symbol,
                "sector": _text(getattr(row, "sector", None)),
                "market_cap_cat": _text(getattr(row, "market_cap_cat", None)),
                "price": _money(getattr(row, "close", None)),
                "live_price": _money(getattr(row, "close", None)),
                "price_date": snapshot_date,
                "change_1d_pct": _metric(getattr(row, "change_1d_pct", None), 4),
                "change_1w_pct": _metric(getattr(row, "change_1w_pct", None), 4),
                "change_1m_pct": _metric(getattr(row, "change_1m_pct", None), 4),
                "stage": _text(getattr(row, "stage", None)),
                "stage_score": _metric(getattr(row, "stage_score", None), 2),
                "technical_score": _metric(getattr(row, "technical_score", None), 2),
                "rsi": _metric(getattr(row, "rsi", None), 2),
                "trend_signal": _text(getattr(row, "trend_signal", None)),
                "trading_signal": _text(getattr(row, "trading_signal", None)),
                "relative_strength": _metric(getattr(row, "relative_strength", None), 4),
                "supertrend_state": None,
                "supertrend_value": None,
                "can_slim_score": _metric(getattr(row, "can_slim_score", None), 2),
                "minervini_score": _metric(getattr(row, "minervini_score", None), 2),
                "fundamental_score": _metric(getattr(row, "fundamental_score", None), 2),
                "enhanced_fund_score": _metric(getattr(row, "enhanced_fund_score", None), 2),
                "earnings_quality": _metric(getattr(row, "earnings_quality", None), 2),
                "sales_growth": _metric(getattr(row, "sales_growth", None), 2),
                "financial_strength": _metric(getattr(row, "financial_strength", None), 2),
                "institutional_backing": _metric(getattr(row, "institutional_backing", None), 2),
                "investment_score": _metric(getattr(row, "investment_score", None), 2),
                "stance": _text(getattr(row, "stance", None)),
                "narrative": _text(getattr(row, "narrative", None)),
                "fund_details": None,
                "source_csv": SOURCE_TAG,
            }
        )
    return rows


def build_stage_change_rows(features: pd.DataFrame) -> list[dict[str, Any]]:
    if features.empty:
        return []
    frame = features.sort_values(["symbol", "date"]).copy()
    frame["prev_date"] = frame.groupby("symbol")["date"].shift(1)
    frame["prev_stage"] = frame.groupby("symbol")["stage"].shift(1)
    frame["prev_close"] = frame.groupby("symbol")["close"].shift(1)
    frame["prev_stage_score"] = frame.groupby("symbol")["stage_score"].shift(1)
    changed = frame[frame["prev_stage"].notna() & (frame["stage"] != frame["prev_stage"])]
    rows: list[dict[str, Any]] = []
    for row in changed.itertuples(index=False):
        stage_now = str(getattr(row, "stage"))
        stage_prev = str(getattr(row, "prev_stage"))
        price_now = _float(getattr(row, "close", None))
        price_prev = _float(getattr(row, "prev_close", None))
        rows.append(
            {
                "change_date": _date(getattr(row, "date")),
                "compare_date": _date(getattr(row, "prev_date")),
                "symbol": str(getattr(row, "symbol")).upper(),
                "company_name": _text(getattr(row, "company_name", None)) or str(getattr(row, "symbol")).upper(),
                "stage_now": stage_now,
                "stage_prev": stage_prev,
                "stage_changed": True,
                "change_type": _change_type(stage_prev, stage_now),
                "price_now": _money(price_now),
                "price_prev": _money(price_prev),
                "price_chg_pct": _pct_change(price_prev, price_now),
                "live_price": _money(price_now),
                "live_vs_prev_pct": _pct_change(price_prev, price_now),
                "stage_score_now": _metric(getattr(row, "stage_score", None), 2),
                "stage_score_prev": _metric(getattr(row, "prev_stage_score", None), 2),
                "trading_signal": _text(getattr(row, "trading_signal", None)),
            }
        )
    return rows


def run_backfill(
    *,
    dsn: str,
    start_date: str,
    lookback_date: str,
    end_date: str | None = None,
    commit: bool = True,
    replace_existing: bool = False,
) -> BackfillSummary:
    with psycopg2.connect(dsn) as conn:
        eod = _load_eod(conn, lookback_date=lookback_date, end_date=end_date)
        scores = _load_daily_scores(conn, lookback_date=lookback_date, end_date=end_date)
        fundamentals = _load_fundamental_scores(conn)
        features = compute_historical_stage_features(eod, start_date=start_date)
        features = _merge_optional_scores(features, scores, fundamentals)
        snapshots = build_stage_snapshot_rows(features)
        changes = build_stage_change_rows(features)
        if commit:
            with conn.cursor() as cur:
                _upsert_snapshot_rows(cur, snapshots, replace_existing=replace_existing)
                _upsert_change_rows(cur, changes, replace_existing=replace_existing)
            conn.commit()
        else:
            conn.rollback()

    if features.empty:
        return BackfillSummary(start_date=start_date, end_date=end_date or start_date, row_count=0, symbol_count=0, stage_counts={}, change_count=0)
    return BackfillSummary(
        start_date=str(features["date"].min().date()),
        end_date=str(features["date"].max().date()),
        row_count=int(len(features)),
        symbol_count=int(features["symbol"].nunique()),
        stage_counts={str(k): int(v) for k, v in features["stage"].value_counts().sort_index().to_dict().items()},
        change_count=len(changes),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill scores.stage_snapshots from market.equity_eod")
    parser.add_argument("--start", default="2025-01-01", help="First snapshot date to write")
    parser.add_argument("--lookback", default="2024-01-01", help="First EOD date to load for rolling indicators")
    parser.add_argument("--end", default=None, help="Optional last EOD date to load")
    parser.add_argument("--dsn", default=os.environ.get("AGENT_ADDA_PG_DSN") or os.environ.get("PG_DSN") or DEFAULT_DSN)
    parser.add_argument("--dry-run", action="store_true", help="Compute rows without writing PostgreSQL")
    parser.add_argument(
        "--replace-existing",
        action="store_true",
        help="Overwrite existing stage snapshot/change rows. Default preserves existing richer snapshots.",
    )
    args = parser.parse_args(argv)
    summary = run_backfill(
        dsn=args.dsn,
        start_date=args.start,
        lookback_date=args.lookback,
        end_date=args.end,
        commit=not args.dry_run,
        replace_existing=args.replace_existing,
    )
    print(summary.as_dict())
    return 0


def _normalize_eod(data: pd.DataFrame) -> pd.DataFrame:
    out = data.rename(columns={column: column.strip().lower() for column in data.columns}).copy()
    out = out.rename(columns={"trade_date": "date", "last_price": "close"})
    required = {"date", "symbol", "open", "high", "low", "close", "volume"}
    missing = required - set(out.columns)
    if missing:
        raise ValueError(f"EOD data missing required columns: {', '.join(sorted(missing))}")
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out["symbol"] = out["symbol"].astype(str).str.strip().str.upper()
    for column in ("open", "high", "low", "close", "volume"):
        out[column] = pd.to_numeric(out[column], errors="coerce")
    for column in ("company_name", "sector", "market_cap_cat"):
        if column not in out.columns:
            out[column] = None
    return (
        out.dropna(subset=["date", "symbol", "open", "high", "low", "close", "volume"])
        .query("symbol != '' and open > 0 and high > 0 and low > 0 and close > 0 and volume > 0")
        .sort_values(["symbol", "date"])
        .reset_index(drop=True)
    )


def _empty_features() -> pd.DataFrame:
    return pd.DataFrame(columns=["date", "symbol", "stage", "stage_score"])


def _rsi(close: pd.Series) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14, min_periods=14).mean()
    loss = (-delta.clip(upper=0)).rolling(14, min_periods=14).mean()
    rs = gain / loss.replace(0, pd.NA)
    return (100 - (100 / (1 + rs))).fillna(50).clip(0, 100)


def _classify_stage(frame: pd.DataFrame) -> pd.Series:
    close = frame["close"]
    stage = pd.Series("STAGE_1", index=frame.index)
    stage2 = (
        (close > frame["sma_50"])
        & (frame["sma_50"] > frame["sma_150"])
        & (frame["sma_150"] > frame["sma_200"])
        & (frame["high_52w"].isna() | (close >= frame["high_52w"] * 0.75))
    )
    stage4 = (
        (close < frame["sma_50"])
        & (frame["sma_50"] < frame["sma_150"])
        & (frame["sma_150"] < frame["sma_200"])
    )
    stage3 = (close < frame["sma_50"]) | (frame["sma_50"] < frame["sma_150"])
    stage.loc[stage2] = "STAGE_2"
    stage.loc[stage3 & ~stage4] = "STAGE_3"
    stage.loc[stage4] = "STAGE_4"
    return stage


def _stage_score(frame: pd.DataFrame) -> pd.Series:
    trend = (
        (frame["close"] > frame["sma_50"]).astype(float) * 20
        + (frame["sma_50"] > frame["sma_150"]).astype(float) * 20
        + (frame["sma_150"] > frame["sma_200"]).astype(float) * 20
    )
    rs = frame["relative_strength"].fillna(50).clip(0, 100) * 0.25
    high_proximity = (frame["close"] / frame["high_52w"].replace(0, pd.NA) * 100).clip(0, 100).fillna(50) * 0.15
    return (trend + rs + high_proximity).clip(0, 100)


def _technical_score(frame: pd.DataFrame) -> pd.Series:
    rsi_score = (100 - (frame["rsi"].fillna(50) - 60).abs() * 2).clip(0, 100) * 0.25
    return (frame["stage_score"].fillna(0) * 0.75 + rsi_score).clip(0, 100)


def _narrative(row: pd.Series) -> str:
    return (
        f"{row['stage']} from historical EOD: close={row['close']:.2f}, "
        f"SMA50={_fmt(row.get('sma_50'))}, SMA150={_fmt(row.get('sma_150'))}, "
        f"SMA200={_fmt(row.get('sma_200'))}, RS={_fmt(row.get('relative_strength'))}."
    )


def _merge_optional_scores(features: pd.DataFrame, scores: pd.DataFrame, fundamentals: pd.DataFrame) -> pd.DataFrame:
    out = features.copy()
    if not scores.empty:
        out = out.merge(scores, on=["date", "symbol"], how="left", suffixes=("", "_score"))
        for column in ("company_name", "sector", "market_cap_cat"):
            score_column = f"{column}_score"
            if score_column in out.columns:
                out[column] = out[column].where(out[column].notna(), out[score_column])
                out = out.drop(columns=[score_column])
    if not fundamentals.empty:
        out = out.merge(fundamentals, on="symbol", how="left", suffixes=("", "_fund"))
        for column in (
            "enhanced_fund_score",
            "earnings_quality",
            "sales_growth",
            "financial_strength",
            "institutional_backing",
        ):
            fund_column = f"{column}_fund"
            if fund_column in out.columns:
                out[column] = out[column].where(out[column].notna(), out[fund_column])
                out = out.drop(columns=[fund_column])
    for column in (
        "can_slim_score",
        "minervini_score",
        "fundamental_score",
        "enhanced_fund_score",
        "earnings_quality",
        "sales_growth",
        "financial_strength",
        "institutional_backing",
    ):
        if column not in out.columns:
            out[column] = None
    return out


def _load_eod(conn: Any, *, lookback_date: str, end_date: str | None) -> pd.DataFrame:
    end_clause = "AND e.trade_date <= %(end_date)s" if end_date else ""
    query = f"""
        SELECT
            e.trade_date AS date,
            e.symbol,
            COALESCE(i.company_name, ds.company_name, e.symbol) AS company_name,
            COALESCE(i.sector, ds.sector) AS sector,
            ds.market_cap_cat,
            e.open,
            e.high,
            e.low,
            e.close,
            e.volume
        FROM market.equity_eod e
        LEFT JOIN ref.instruments i ON upper(i.symbol) = upper(e.symbol)
        LEFT JOIN scores.daily_scores ds ON ds.symbol = e.symbol AND ds.score_date = e.trade_date
        WHERE e.series = 'EQ'
          AND e.trade_date >= %(lookback_date)s
          {end_clause}
        ORDER BY e.symbol, e.trade_date
    """
    return pd.read_sql_query(query, conn, params={"lookback_date": lookback_date, "end_date": end_date})


def _load_daily_scores(conn: Any, *, lookback_date: str, end_date: str | None) -> pd.DataFrame:
    end_clause = "AND score_date <= %(end_date)s" if end_date else ""
    query = f"""
        SELECT
            score_date AS date,
            symbol,
            company_name,
            sector,
            market_cap_cat,
            can_slim_score,
            minervini_score,
            fundamental_score,
            enhanced_fund_score,
            earnings_quality,
            sales_growth,
            financial_strength,
            institutional_backing
        FROM scores.daily_scores
        WHERE score_date >= %(lookback_date)s
          {end_clause}
    """
    rows = pd.read_sql_query(query, conn, params={"lookback_date": lookback_date, "end_date": end_date})
    if rows.empty:
        return rows
    rows["date"] = pd.to_datetime(rows["date"], errors="coerce")
    rows["symbol"] = rows["symbol"].astype(str).str.upper()
    return rows


def _load_fundamental_scores(conn: Any) -> pd.DataFrame:
    query = """
        SELECT DISTINCT ON (symbol)
            symbol,
            enhanced_fund_score,
            earnings_quality,
            sales_growth,
            financial_strength,
            institutional_backing
        FROM scores.fundamental_scores
        ORDER BY symbol, score_date DESC
    """
    rows = pd.read_sql_query(query, conn)
    if rows.empty:
        return rows
    rows["symbol"] = rows["symbol"].astype(str).str.upper()
    return rows


def _upsert_snapshot_rows(cur: Any, rows: list[dict[str, Any]], *, replace_existing: bool) -> None:
    if not rows:
        return
    columns = list(rows[0])
    conflict = "DO NOTHING"
    if replace_existing:
        assignments = ", ".join(f"{column}=EXCLUDED.{column}" for column in columns if column not in {"snapshot_date", "symbol"})
        conflict = f"DO UPDATE SET {assignments}"
    sql = f"""
        INSERT INTO scores.stage_snapshots ({", ".join(columns)})
        VALUES %s
        ON CONFLICT (snapshot_date, symbol) {conflict}
    """
    execute_values(cur, sql, [[row[column] for column in columns] for row in rows], page_size=5000)


def _upsert_change_rows(cur: Any, rows: list[dict[str, Any]], *, replace_existing: bool) -> None:
    if not rows:
        return
    columns = list(rows[0])
    conflict = "DO NOTHING"
    if replace_existing:
        assignments = ", ".join(
            f"{column}=EXCLUDED.{column}" for column in columns if column not in {"change_date", "compare_date", "symbol"}
        )
        conflict = f"DO UPDATE SET {assignments}"
    sql = f"""
        INSERT INTO scores.stage_changes ({", ".join(columns)})
        VALUES %s
        ON CONFLICT (change_date, compare_date, symbol) {conflict}
    """
    execute_values(cur, sql, [[row[column] for column in columns] for row in rows], page_size=5000)


def _change_type(prev: str, now: str) -> str:
    if now == "STAGE_2" and prev != "STAGE_2":
        return "ENTER_STAGE2"
    if prev == "STAGE_2" and now != "STAGE_2":
        return "EXIT_STAGE2"
    order = {"STAGE_1": 1, "STAGE_2": 2, "STAGE_3": 3, "STAGE_4": 4}
    if order.get(now, 0) > order.get(prev, 0):
        return "DOWNGRADE"
    return "UPGRADE"


def _date(value: Any) -> Any:
    if pd.isna(value):
        return None
    return pd.to_datetime(value).date()


def _float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(parsed):
        return None
    return parsed


def _metric(value: Any, places: int) -> float | None:
    parsed = _float(value)
    return None if parsed is None else round(parsed, places)


def _money(value: Any) -> float | None:
    return _metric(value, 2)


def _pct_change(previous: float | None, current: float | None) -> float | None:
    if previous in {None, 0} or current is None:
        return None
    return round((current - previous) / previous * 100, 4)


def _text(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def _fmt(value: Any) -> str:
    parsed = _float(value)
    return "n/a" if parsed is None else f"{parsed:.2f}"


if __name__ == "__main__":
    raise SystemExit(main())
