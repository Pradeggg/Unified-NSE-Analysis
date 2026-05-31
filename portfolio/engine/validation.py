from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import pandas as pd


REQUIRED_OHLCV_COLUMNS = ("date", "symbol", "open", "high", "low", "close", "volume")


class Severity(StrEnum):
    ERROR = "ERROR"
    WARNING = "WARNING"


@dataclass(frozen=True)
class DataQualityIssue:
    code: str
    severity: Severity
    message: str
    symbol: str | None = None
    timestamp: str | None = None
    row_index: int | str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity.value,
            "message": self.message,
            "symbol": self.symbol,
            "timestamp": self.timestamp,
            "row_index": self.row_index,
        }


@dataclass(frozen=True)
class DataQualityReport:
    row_count: int
    symbol_count: int
    issues: tuple[DataQualityIssue, ...]

    @property
    def error_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == Severity.ERROR)

    @property
    def warning_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == Severity.WARNING)

    @property
    def is_usable(self) -> bool:
        return self.error_count == 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "row_count": self.row_count,
            "symbol_count": self.symbol_count,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "is_usable": self.is_usable,
            "issues": [issue.as_dict() for issue in self.issues],
        }


def validate_ohlcv(data: pd.DataFrame) -> DataQualityReport:
    row_count = int(len(data))
    symbol_count = _symbol_count(data)
    issues: list[DataQualityIssue] = []

    missing_columns = [column for column in REQUIRED_OHLCV_COLUMNS if column not in data.columns]
    for column in missing_columns:
        issues.append(
            DataQualityIssue(
                code="missing_column",
                severity=Severity.ERROR,
                message=f"required OHLCV column is missing: {column}",
            )
        )
    if missing_columns:
        return DataQualityReport(row_count=row_count, symbol_count=symbol_count, issues=tuple(issues))

    invalid_range = (
        (data["high"] < data["open"])
        | (data["high"] < data["close"])
        | (data["high"] < data["low"])
        | (data["low"] > data["open"])
        | (data["low"] > data["close"])
        | (data["low"] > data["high"])
    )
    issue = _first_issue(
        data,
        invalid_range,
        code="invalid_ohlc_range",
        severity=Severity.ERROR,
        message="OHLC range is invalid: high must be at least open/low/close and low must be at most open/high/close",
    )
    if issue is not None:
        issues.append(issue)

    issue = _first_issue(
        data,
        data["volume"] <= 0,
        code="zero_volume",
        severity=Severity.WARNING,
        message="bar volume must be positive",
    )
    if issue is not None:
        issues.append(issue)

    issue = _first_issue(
        data,
        data.duplicated(subset=["date", "symbol"], keep="first"),
        code="duplicate_bar",
        severity=Severity.WARNING,
        message="duplicate date/symbol bar detected",
    )
    if issue is not None:
        issues.append(issue)

    return DataQualityReport(row_count=row_count, symbol_count=symbol_count, issues=tuple(issues))


def _symbol_count(data: pd.DataFrame) -> int:
    if "symbol" not in data.columns:
        return 0
    return int(data["symbol"].dropna().nunique())


def _first_issue(
    data: pd.DataFrame,
    mask: pd.Series,
    *,
    code: str,
    severity: Severity,
    message: str,
) -> DataQualityIssue | None:
    if not bool(mask.any()):
        return None
    row_index = mask[mask].index[0]
    row = data.loc[row_index]
    return DataQualityIssue(
        code=code,
        severity=severity,
        message=message,
        symbol=_json_safe_scalar(row.get("symbol")),
        timestamp=_json_safe_timestamp(row.get("date")),
        row_index=_json_safe_index(row_index),
    )


def _json_safe_scalar(value: Any) -> str | None:
    if pd.isna(value):
        return None
    return str(value)


def _json_safe_timestamp(value: Any) -> str | None:
    if pd.isna(value):
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _json_safe_index(value: Any) -> int | str:
    if isinstance(value, int):
        return value
    return str(value)
