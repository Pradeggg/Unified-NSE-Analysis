from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class ManagedPortfolioPolicy:
    start_date: str = "2025-01-01"
    initial_capital: float = 1_000_000.0
    max_gross_exposure_pct: float = 95.0
    max_single_stock_pct: float = 10.0
    max_sector_pct: float = 25.0
    risk_per_new_position_pct: float = 1.0
    risk_per_add_pct: float = 0.5
    max_portfolio_open_risk_pct: float = 8.0
    max_positions: int = 15
    initial_entry_pct_of_target: float = 50.0
    first_add_pct_of_target: float = 25.0
    second_add_pct_of_target: float = 25.0
    trim_when_position_pct_above: float = 12.0
    trim_to_position_pct: float = 8.0
    stop_method: str = "atr"
    target_method: str = "reward_risk"
    default_reward_risk: float = 2.0

    def __post_init__(self) -> None:
        positive_fields = (
            "initial_capital",
            "max_gross_exposure_pct",
            "max_single_stock_pct",
            "max_sector_pct",
            "risk_per_new_position_pct",
            "risk_per_add_pct",
            "max_portfolio_open_risk_pct",
            "max_positions",
            "initial_entry_pct_of_target",
            "default_reward_risk",
        )
        for name in positive_fields:
            value = getattr(self, name)
            if float(value) <= 0:
                raise ValueError(f"{name} must be positive")
        if self.trim_to_position_pct >= self.trim_when_position_pct_above:
            raise ValueError("trim_to_position_pct must be below trim_when_position_pct_above")
        if self.stop_method != "atr":
            raise ValueError("stop_method must be atr")
        if self.target_method != "reward_risk":
            raise ValueError("target_method must be reward_risk")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def checksum(self) -> str:
        payload = json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def load_policy(path: Path | None = None) -> ManagedPortfolioPolicy:
    if path is None:
        return ManagedPortfolioPolicy()
    raw = path.read_text(encoding="utf-8")
    data = _parse_simple_yaml(raw)
    return ManagedPortfolioPolicy(**data)


def _parse_simple_yaml(raw: str) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in stripped:
            raise ValueError(f"invalid policy line: {line}")
        key, value = stripped.split(":", 1)
        data[key.strip()] = _coerce_policy_value(value.strip())
    return data


def _coerce_policy_value(value: str) -> Any:
    if value == "":
        return ""
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value.strip("\"'")
