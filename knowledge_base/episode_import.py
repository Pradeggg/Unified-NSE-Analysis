"""Import external assistant traces into "episodes".

This is intentionally metadata-first (safe-by-default):
- Claude Code: reads ~/.claude/history.jsonl and aggregates events into sessions.
- Cursor: reads Cursor's conversation-search.db and extracts conversation metadata.

By default we do NOT import message text (display/pastedContents) to avoid
accidentally persisting sensitive content. This can be extended later with
explicit redaction + user opt-in.
"""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from ._common import DATA_DIR, safe_filename


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_utc_from_ms(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, timezone.utc).isoformat().replace("+00:00", "Z")


def _read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except Exception:
                continue


def _append_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
            n += 1
    return n


@dataclass(frozen=True)
class ImportSummary:
    ok: bool
    source: str
    out_path: str
    episodes_written: int
    started_utc: str
    ended_utc: str
    details: dict[str, Any]


def import_claude_history(
    *,
    days: int = 60,
    project_path: str | None = None,
    out_path: Path | None = None,
) -> ImportSummary:
    """Import Claude Code metadata episodes from ~/.claude/history.jsonl."""
    hist = Path.home() / ".claude" / "history.jsonl"
    if not hist.exists():
        return ImportSummary(
            ok=False,
            source="claude",
            out_path=str(out_path or ""),
            episodes_written=0,
            started_utc="",
            ended_utc="",
            details={"error": f"missing file: {hist}"},
        )

    cutoff_ms = int((_utc_now() - timedelta(days=days)).timestamp() * 1000)

    sessions: dict[str, dict[str, Any]] = {}
    total_events = 0

    for ev in _read_jsonl(hist):
        ts = ev.get("timestamp")
        if not isinstance(ts, int) or ts < cutoff_ms:
            continue
        proj = str(ev.get("project") or "").strip()
        if project_path and proj != project_path:
            continue

        sid = str(ev.get("sessionId") or "").strip()
        if not sid:
            continue

        rec = sessions.get(sid)
        if rec is None:
            rec = {
                "min_ts": ts,
                "max_ts": ts,
                "events": 0,
                "project": proj,
                "types": {},
            }
            sessions[sid] = rec

        rec["min_ts"] = min(int(rec["min_ts"]), ts)
        rec["max_ts"] = max(int(rec["max_ts"]), ts)
        rec["events"] = int(rec["events"]) + 1
        t = str(ev.get("type") or "").strip() or "(none)"
        rec["types"][t] = int(rec["types"].get(t, 0)) + 1
        total_events += 1

    if out_path is None:
        label = safe_filename(project_path or "all_projects")
        out_path = DATA_DIR / "knowledge_base" / f"episodes_imported_claude_{label}.jsonl"

    rows: list[dict[str, Any]] = []
    started_utc = ended_utc = ""
    if sessions:
        min_all = min(v["min_ts"] for v in sessions.values())
        max_all = max(v["max_ts"] for v in sessions.values())
        started_utc = _iso_utc_from_ms(int(min_all))
        ended_utc = _iso_utc_from_ms(int(max_all))

    for sid, rec in sorted(sessions.items(), key=lambda kv: int(kv[1]["max_ts"]), reverse=True):
        rows.append(
            {
                "episode_id": f"claude:{sid}",
                "source": "claude_history",
                "project": rec.get("project") or "",
                "session_id": sid,
                "started_at_utc": _iso_utc_from_ms(int(rec["min_ts"])),
                "ended_at_utc": _iso_utc_from_ms(int(rec["max_ts"])),
                "event_count": int(rec["events"]),
                "event_types": rec.get("types") or {},
                "imported_at_utc": _iso_utc_from_ms(int(_utc_now().timestamp() * 1000)),
                "notes": "metadata_only",
            }
        )

    written = _append_jsonl(out_path, rows)
    return ImportSummary(
        ok=True,
        source="claude",
        out_path=str(out_path),
        episodes_written=written,
        started_utc=started_utc,
        ended_utc=ended_utc,
        details={
            "days": days,
            "project_path": project_path or "",
            "sessions": len(sessions),
            "events_in_scope": total_events,
            "input_path": str(hist),
        },
    )


def import_cursor_conversations(
    *,
    days: int = 60,
    out_path: Path | None = None,
) -> ImportSummary:
    """Import Cursor conversation metadata from conversation-search.db."""
    db = (
        Path.home()
        / "Library"
        / "Application Support"
        / "Cursor"
        / "User"
        / "globalStorage"
        / "conversation-search.db"
    )
    if not db.exists():
        return ImportSummary(
            ok=False,
            source="cursor",
            out_path=str(out_path or ""),
            episodes_written=0,
            started_utc="",
            ended_utc="",
            details={"error": f"missing file: {db}"},
        )

    cutoff_ms = int((_utc_now() - timedelta(days=days)).timestamp() * 1000)

    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT source, scope, id, title, branches, updated_at, is_archived,
                   root_fingerprint, cache_fingerprint
            FROM conversations
            WHERE updated_at >= ?
            ORDER BY updated_at DESC
            """,
            (cutoff_ms,),
        ).fetchall()
    finally:
        conn.close()

    if out_path is None:
        out_path = DATA_DIR / "knowledge_base" / "episodes_imported_cursor.jsonl"

    def branches_meta(branches_text: str) -> dict[str, Any]:
        s = (branches_text or "").strip()
        if not s:
            return {"branches_present": False}
        # Avoid storing potentially sensitive branch content; keep only shape.
        return {"branches_present": True, "branches_chars": len(s)}

    out_rows: list[dict[str, Any]] = []
    started_utc = ended_utc = ""
    if rows:
        started_utc = _iso_utc_from_ms(int(min(int(r["updated_at"]) for r in rows)))
        ended_utc = _iso_utc_from_ms(int(max(int(r["updated_at"]) for r in rows)))

    for r in rows:
        cid = str(r["id"] or "").strip()
        out_rows.append(
            {
                "episode_id": f"cursor:{cid}",
                "source": "cursor_conversation_search",
                "conversation_id": cid,
                "title": str(r["title"] or "").strip(),
                "updated_at_utc": _iso_utc_from_ms(int(r["updated_at"])),
                "scope": str(r["scope"] or "").strip(),
                "cursor_source": str(r["source"] or "").strip(),
                "is_archived": int(r["is_archived"] or 0),
                "fingerprints": {
                    "root": str(r["root_fingerprint"] or ""),
                    "cache": str(r["cache_fingerprint"] or ""),
                },
                "branches_meta": branches_meta(str(r["branches"] or "")),
                "imported_at_utc": _iso_utc_from_ms(int(_utc_now().timestamp() * 1000)),
                "notes": "metadata_only",
            }
        )

    written = _append_jsonl(out_path, out_rows)
    return ImportSummary(
        ok=True,
        source="cursor",
        out_path=str(out_path),
        episodes_written=written,
        started_utc=started_utc,
        ended_utc=ended_utc,
        details={
            "days": days,
            "conversations": len(rows),
            "input_path": str(db),
        },
    )


def import_all_metadata(
    *,
    days: int = 60,
    claude_project_path: str | None = None,
) -> dict[str, Any]:
    """Convenience wrapper: imports Claude + Cursor metadata episodes."""
    claude = import_claude_history(days=days, project_path=claude_project_path)
    cursor = import_cursor_conversations(days=days)
    ok = bool(claude.ok and cursor.ok)
    return {
        "ok": ok,
        "days": days,
        "claude": claude.__dict__,
        "cursor": cursor.__dict__,
    }


__all__ = [
    "ImportSummary",
    "import_claude_history",
    "import_cursor_conversations",
    "import_all_metadata",
]

