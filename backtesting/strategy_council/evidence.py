"""Point-in-time evidence pack builder for Strategy Council runs."""

from __future__ import annotations

from datetime import date
import os
from pathlib import Path

import pandas as pd

from backtesting.strategy_council.types import EvidencePack


STOCK_HISTORY_FALLBACK_CSVS = (
    Path("data") / "nse_sec_full_data.csv",
    Path("data") / "nse-raw" / "nse_sec_full_data.csv",
    Path("data") / "data" / "nse-raw" / "nse_sec_full_data.csv",
    Path("data") / "data" / "nse_sec_full_data.csv",
)


def _project_root(project_root: Path | None) -> Path:
    return Path(project_root) if project_root is not None else Path.cwd()


def _normalize_eod(df: pd.DataFrame) -> pd.DataFrame:
    out = df.rename(columns={c: c.strip().lower() for c in df.columns}).copy()
    if "timestamp" in out.columns and "date" not in out.columns:
        out = out.rename(columns={"timestamp": "date"})
    if "tottrdqty" in out.columns and "volume" not in out.columns:
        out = out.rename(columns={"tottrdqty": "volume"})
    if "symbol" not in out.columns:
        return pd.DataFrame(columns=["symbol", "date", "open", "high", "low", "close", "volume"])
    out["symbol"] = out["symbol"].astype(str).str.upper()
    out["date"] = pd.to_datetime(out.get("date"), errors="coerce")
    for col in ("open", "high", "low", "close", "volume"):
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    return out.dropna(subset=["symbol", "date", "close"]).sort_values(["symbol", "date"])


def _load_symbol_eod_from_postgres(symbol: str) -> tuple[pd.DataFrame, str]:
    sym = symbol.strip().upper()
    dsn = os.environ.get("AGENT_ADDA_PG_DSN") or "dbname=nse_market user=nse_admin host=/tmp"
    try:
        import psycopg2

        with psycopg2.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT symbol,
                       trade_date AS date,
                       open,
                       high,
                       low,
                       close,
                       volume
                FROM market.equity_eod
                WHERE upper(symbol) = %s
                ORDER BY trade_date
                """,
                (sym,),
            )
            rows = cur.fetchall()
            df = pd.DataFrame(
                rows,
                columns=["symbol", "date", "open", "high", "low", "close", "volume"],
            )
    except Exception as exc:
        return pd.DataFrame(columns=["symbol", "date", "open", "high", "low", "close", "volume"]), (
            f"PostgreSQL market.equity_eod: error {type(exc).__name__}"
        )

    history = _normalize_eod(df)
    if history.empty:
        return history, f"PostgreSQL market.equity_eod: {sym} not found"
    return history, f"PostgreSQL market.equity_eod: ok ({len(history)} rows)"


def load_symbol_eod_history(
    symbol: str,
    *,
    project_root: Path | None = None,
    from_date: str | None = None,
) -> tuple[pd.DataFrame, list[str]]:
    root = _project_root(project_root)
    sym = symbol.strip().upper()
    frames: list[pd.DataFrame] = []
    trail: list[str] = []

    pg_history, pg_trail = _load_symbol_eod_from_postgres(sym)
    trail.append(pg_trail)
    if not pg_history.empty:
        history = pg_history.sort_values(["symbol", "date"])
        history = history.drop_duplicates(["symbol", "date"], keep="last")
        if from_date:
            history = history[history["date"] >= pd.Timestamp(from_date)]
        return history.reset_index(drop=True), trail

    for rel_path in STOCK_HISTORY_FALLBACK_CSVS:
        path = root / rel_path
        if not path.exists():
            continue
        try:
            df = _normalize_eod(pd.read_csv(path))
        except Exception as exc:
            trail.append(f"{rel_path}: error {type(exc).__name__}")
            continue
        sdf = df[df["symbol"] == sym]
        if sdf.empty:
            trail.append(f"{rel_path}: {sym} not found")
            continue
        frames.append(sdf)
        trail.append(f"{rel_path}: ok")

    if not frames:
        return pd.DataFrame(columns=["symbol", "date", "open", "high", "low", "close", "volume"]), trail

    history = pd.concat(frames, ignore_index=True)
    history = history.sort_values(["symbol", "date"])
    history = history.drop_duplicates(["symbol", "date"], keep="last")
    if from_date:
        history = history[history["date"] >= pd.Timestamp(from_date)]
    return history.reset_index(drop=True), trail


def build_evidence_pack(symbol: str, *, project_root: Path | None = None) -> EvidencePack:
    root = _project_root(project_root)
    sym = symbol.strip().upper()
    eod_path = root / "data" / "nse_sec_full_data.csv"
    pack = EvidencePack(symbol=sym, as_of=date.today().isoformat())

    if not eod_path.exists() and not any((root / p).exists() for p in STOCK_HISTORY_FALLBACK_CSVS):
        pack.missing.append("eod")
        pack.source_trail.append(f"{eod_path}: missing")
        return pack

    sdf, trail = load_symbol_eod_history(sym, project_root=root)
    pack.source_trail.extend(trail)
    if sdf.empty:
        pack.missing.append("eod_symbol")
        pack.source_trail.append(f"data/nse_sec_full_data.csv: {sym} not found")
        return pack

    latest = sdf.iloc[-1]
    pack.as_of = latest["date"].date().isoformat()
    pack.technical.update(
        {
            "open": float(latest["open"]) if "open" in latest and pd.notna(latest["open"]) else None,
            "high": float(latest["high"]) if "high" in latest and pd.notna(latest["high"]) else None,
            "low": float(latest["low"]) if "low" in latest and pd.notna(latest["low"]) else None,
            "close": float(latest["close"]),
            "volume": float(latest["volume"]) if "volume" in latest and pd.notna(latest["volume"]) else None,
            "bars": int(len(sdf)),
        }
    )
    pack.freshness["eod"] = "available"

    for optional in ("fundamentals", "market_breadth", "news", "sentiment", "latest_results"):
        pack.missing.append(optional)
    return pack
