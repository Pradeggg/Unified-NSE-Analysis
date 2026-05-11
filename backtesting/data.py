"""Data readiness checks for EOD backtesting.

This module only inspects local files. It does not fetch market data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd


EOD_FILE = Path("data/nse_sec_full_data.csv")
INDEX_FILE = Path("data/nse_index_data.csv")
STAGE_DB_FILE = Path("data/sector_rotation_tracker.db")
FUNDAMENTAL_FILES = (
    Path("data/fundamental_scores_database.csv"),
    Path("data/_sector_rotation_fund_cache.csv"),
)


@dataclass(frozen=True)
class BacktestDataReadiness:
    project_root: Path
    ok_to_backtest: bool
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    modes: list[str] = field(default_factory=list)
    latest_eod_date: str | None = None
    symbol_count: int = 0
    row_count: int = 0
    files: dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "project_root": str(self.project_root),
            "ok_to_backtest": self.ok_to_backtest,
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "modes": list(self.modes),
            "latest_eod_date": self.latest_eod_date,
            "symbol_count": self.symbol_count,
            "row_count": self.row_count,
            "files": dict(self.files),
        }


def _first_matching_column(columns: list[str], choices: set[str]) -> str | None:
    for col in columns:
        if col.strip().lower() in choices:
            return col
    return None


def inspect_backtest_data(project_root: Path | str | None = None) -> BacktestDataReadiness:
    """Inspect local EOD backtest prerequisites.

    Required for any EOD backtest:
    - `data/nse_sec_full_data.csv` with symbol/date/OHLCV-style columns.

    Missing optional data does not block the engine; it changes the mode labels
    so downstream strategy code cannot pretend fundamentals or regime existed.
    """
    root = Path(project_root or Path.cwd()).resolve()
    eod_path = root / EOD_FILE
    index_path = root / INDEX_FILE
    stage_db_path = root / STAGE_DB_FILE

    blockers: list[str] = []
    warnings: list[str] = []
    modes: list[str] = []
    files: dict[str, str] = {}

    if not eod_path.exists():
        blockers.append("missing_eod_ohlcv")
        return BacktestDataReadiness(
            project_root=root,
            ok_to_backtest=False,
            blockers=blockers,
            warnings=["EOD OHLCV file not found: data/nse_sec_full_data.csv"],
            modes=[],
            files={"eod_ohlcv": str(eod_path)},
        )

    files["eod_ohlcv"] = str(eod_path)

    try:
        sample = pd.read_csv(eod_path, nrows=1000)
    except Exception as exc:
        blockers.append("invalid_eod_ohlcv")
        return BacktestDataReadiness(
            project_root=root,
            ok_to_backtest=False,
            blockers=blockers,
            warnings=[f"Could not read EOD OHLCV file: {exc}"],
            files=files,
        )

    columns = list(sample.columns)
    symbol_col = _first_matching_column(columns, {"symbol", "ticker", "series_symbol"})
    date_col = _first_matching_column(columns, {"date", "timestamp", "trade_date"})
    close_col = _first_matching_column(columns, {"close", "close_price", "close_price_1", "ltp"})

    missing_required = []
    if not symbol_col:
        missing_required.append("symbol")
    if not date_col:
        missing_required.append("date")
    if not close_col:
        missing_required.append("close")
    if missing_required:
        blockers.append("eod_missing_required_columns")
        warnings.append(f"EOD OHLCV missing required columns: {', '.join(missing_required)}")

    latest_eod_date = None
    symbol_count = 0
    row_count = 0
    if not blockers:
        symbols_seen: set[str] = set()
        latest_ts = None
        for chunk in pd.read_csv(eod_path, usecols=[symbol_col, date_col], chunksize=100000):
            row_count += int(len(chunk))
            symbols_seen.update(chunk[symbol_col].dropna().astype(str).unique().tolist())
            parsed_dates = pd.to_datetime(chunk[date_col], errors="coerce")
            if parsed_dates.notna().any():
                chunk_latest = parsed_dates.max()
                if latest_ts is None or chunk_latest > latest_ts:
                    latest_ts = chunk_latest
        if latest_ts is not None:
            latest_eod_date = latest_ts.date().isoformat()
        symbol_count = len(symbols_seen)

    if index_path.exists():
        files["index_data"] = str(index_path)
    else:
        warnings.append("missing_index_data")

    if stage_db_path.exists():
        files["stage_db"] = str(stage_db_path)
    else:
        warnings.append("missing_stage_snapshot_db")

    fundamental_found = [path for path in FUNDAMENTAL_FILES if (root / path).exists()]
    if fundamental_found:
        files["fundamentals"] = ", ".join(str(root / path) for path in fundamental_found)
        modes.append("fundamental-aware")
    else:
        warnings.append("missing_fundamentals")
        modes.append("technical-only")

    if not blockers and "technical-only" not in modes:
        modes.append("technical")

    return BacktestDataReadiness(
        project_root=root,
        ok_to_backtest=not blockers,
        blockers=blockers,
        warnings=warnings,
        modes=modes,
        latest_eod_date=latest_eod_date,
        symbol_count=symbol_count,
        row_count=row_count,
        files=files,
    )
