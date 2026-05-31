from __future__ import annotations

import hashlib
import json
import math
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

try:
    import numpy as np
except ImportError:  # pragma: no cover - pandas normally provides numpy in this project
    np = None


@dataclass(frozen=True)
class RunManifest:
    run_id: str
    generated_at: str
    git_commit: str | None
    checksums: dict[str, str]
    artifacts: dict[str, str]
    strategy_count: int
    data: dict[str, int]

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "generated_at": self.generated_at,
            "git_commit": self.git_commit,
            "checksums": dict(self.checksums),
            "artifacts": dict(self.artifacts),
            "strategy_count": self.strategy_count,
            "data": dict(self.data),
        }


def checksum_payload(payload: Any) -> str:
    normalized = _json_safe(payload)
    encoded = json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_run_manifest(
    run_id: str,
    config: dict[str, Any],
    strategy_specs: list[dict[str, Any]],
    data: pd.DataFrame,
    artifacts: dict[str, Path | str],
    *,
    generated_at: str | None = None,
) -> RunManifest:
    artifact_paths = {key: str(Path(value)) for key, value in sorted(artifacts.items())}
    row_count = int(len(data))
    symbol_count = int(data["symbol"].dropna().nunique()) if "symbol" in data.columns else 0

    return RunManifest(
        run_id=str(run_id),
        generated_at=generated_at or datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        git_commit=_git_commit(),
        checksums={
            "config": checksum_payload(config),
            "strategies": checksum_payload(strategy_specs),
            "data": checksum_payload(data),
            "artifacts": checksum_payload(artifact_paths),
        },
        artifacts=artifact_paths,
        strategy_count=int(len(strategy_specs)),
        data={"row_count": row_count, "symbol_count": symbol_count},
    )


def _git_commit() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    commit = result.stdout.strip()
    return commit or None


def _json_safe(value: Any) -> Any:
    if np is not None and isinstance(value, np.generic):
        return _json_safe(value.item())
    if isinstance(value, pd.DataFrame):
        ordered = value.sort_index(axis=1)
        return [_json_safe(row) for row in ordered.to_dict(orient="records")]
    if isinstance(value, pd.Series):
        return _json_safe(value.to_dict())
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, str) or value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if math.isnan(value):
            return "nan"
        if math.isinf(value):
            return "inf" if value > 0 else "-inf"
        return value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, Sequence):
        return [_json_safe(item) for item in value]
    if pd.isna(value):
        return None
    return str(value)
