from __future__ import annotations

import csv
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


REQUIRED_DAILY_COLUMNS = {"SYMBOL", "DATE", "OPEN", "HIGH", "LOW", "CLOSE", "VOLUME"}


@dataclass(frozen=True)
class BootstrapResult:
    database_path: Path
    files_scanned: int
    rows_loaded: int
    rows_skipped: int


def _create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        create table if not exists daily_prices (
            symbol text not null,
            trade_date text not null,
            open real,
            high real,
            low real,
            close real,
            volume integer,
            source_file text not null,
            loaded_at text not null,
            primary key (symbol, trade_date, source_file)
        );

        create table if not exists data_refresh_log (
            id integer primary key autoincrement,
            source text not null,
            source_path text not null,
            rows_loaded integer not null,
            rows_skipped integer not null,
            loaded_at text not null
        );
        """
    )


def _candidate_files(source_paths: Iterable[Path]) -> list[Path]:
    files: list[Path] = []
    for source in source_paths:
        source = source.expanduser()
        if source.is_file() and source.suffix.lower() == ".csv":
            files.append(source)
        elif source.is_dir():
            files.extend(sorted(path for path in source.rglob("*.csv") if path.is_file()))
    return files


def _float_value(row: dict[str, str], key: str) -> float | None:
    value = row.get(key, "").replace(",", "").strip()
    return float(value) if value else None


def _int_value(row: dict[str, str], key: str) -> int | None:
    value = row.get(key, "").replace(",", "").strip()
    return int(float(value)) if value else None


def _load_file(conn: sqlite3.Connection, csv_path: Path, loaded_at: str) -> tuple[int, int]:
    loaded = 0
    skipped = 0
    with csv_path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        columns = {name.upper() for name in (reader.fieldnames or [])}
        if not REQUIRED_DAILY_COLUMNS.issubset(columns):
            return 0, 0
        for raw_row in reader:
            row = {key.upper(): value for key, value in raw_row.items()}
            symbol = row.get("SYMBOL", "").strip().upper()
            trade_date = row.get("DATE", "").strip()
            if not symbol or not trade_date:
                skipped += 1
                continue
            try:
                conn.execute(
                    """
                    insert or replace into daily_prices (
                        symbol, trade_date, open, high, low, close, volume, source_file, loaded_at
                    ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        symbol,
                        trade_date,
                        _float_value(row, "OPEN"),
                        _float_value(row, "HIGH"),
                        _float_value(row, "LOW"),
                        _float_value(row, "CLOSE"),
                        _int_value(row, "VOLUME"),
                        str(csv_path),
                        loaded_at,
                    ),
                )
                loaded += 1
            except (TypeError, ValueError, sqlite3.Error):
                skipped += 1
    return loaded, skipped


def bootstrap_historical_store(
    database_path: Path,
    source_paths: Iterable[Path],
) -> BootstrapResult:
    database_path = database_path.expanduser()
    database_path.parent.mkdir(parents=True, exist_ok=True)
    files = _candidate_files(source_paths)
    total_loaded = 0
    total_skipped = 0
    loaded_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with closing(sqlite3.connect(database_path)) as conn:
        _create_schema(conn)
        for csv_path in files:
            loaded, skipped = _load_file(conn, csv_path, loaded_at)
            total_loaded += loaded
            total_skipped += skipped
            conn.execute(
                """
                insert into data_refresh_log (
                    source, source_path, rows_loaded, rows_skipped, loaded_at
                ) values (?, ?, ?, ?, ?)
                """,
                ("historical_csv", str(csv_path), loaded, skipped, loaded_at),
            )
        conn.commit()
    return BootstrapResult(
        database_path=database_path,
        files_scanned=len(files),
        rows_loaded=total_loaded,
        rows_skipped=total_skipped,
    )
