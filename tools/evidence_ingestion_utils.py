from __future__ import annotations

from typing import Any


def clean_pg_value(value: Any) -> Any:
    """Remove NUL characters from nested values destined for PostgreSQL."""
    if isinstance(value, str):
        return value.replace("\x00", "")
    if isinstance(value, dict):
        return {clean_pg_value(key): clean_pg_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [clean_pg_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(clean_pg_value(item) for item in value)
    return value
