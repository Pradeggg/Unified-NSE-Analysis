from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


class AuditLogError(ValueError):
    """Raised when an audit log cannot be read deterministically."""


@dataclass(frozen=True)
class AuditRecord:
    timestamp: str
    date: str
    agent: str
    action: str
    strategy_id: str | None = None
    symbol: str | None = None
    reason: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class AuditLog:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def append(
        self,
        *,
        timestamp: str,
        date: str,
        agent: str,
        action: str,
        strategy_id: str | None = None,
        symbol: str | None = None,
        reason: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        record = AuditRecord(
            timestamp=timestamp,
            date=date,
            agent=agent,
            action=action,
            strategy_id=strategy_id,
            symbol=symbol.upper() if symbol else None,
            reason=reason,
            payload={} if payload is None else payload,
        )
        return write_audit_record(self.path, record)

    def read(self) -> list[dict[str, Any]]:
        return read_audit_log(self.path)


def write_audit_record(path: str | Path, record: AuditRecord | dict[str, Any]) -> dict[str, Any]:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    row = record.as_dict() if isinstance(record, AuditRecord) else dict(record)
    row.setdefault("payload", {})
    normalized = _json_normalized(row)
    with destination.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(normalized, sort_keys=True, separators=(",", ":")))
        handle.write("\n")
    return normalized


def read_audit_log(path: str | Path) -> list[dict[str, Any]]:
    source = Path(path)
    if not source.exists():
        return []
    rows: list[dict[str, Any]] = []
    with source.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if stripped:
                try:
                    row = json.loads(stripped)
                except json.JSONDecodeError as exc:
                    raise AuditLogError(
                        f"malformed audit log JSON at {source}:{line_number}"
                    ) from exc
                if not isinstance(row, dict):
                    raise AuditLogError(
                        f"audit log record must be an object at {source}:{line_number}"
                    )
                rows.append(row)
    return rows


def _json_normalized(row: dict[str, Any]) -> dict[str, Any]:
    encoded = json.dumps(row, sort_keys=True, separators=(",", ":"), default=str)
    return json.loads(encoded)
