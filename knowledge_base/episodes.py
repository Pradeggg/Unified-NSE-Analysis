"""Episode views for Agent Adda KB.

This is a lightweight bridge toward the full "Layer 4 Episodes" design:
it can *derive* session-like episodes from the existing KB query log
(`data/knowledge_base/query_log.db`) so you can inspect real usage now,
even before we start logging full tool-run traces.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from ._common import DATA_DIR

QUERY_LOG_DB = DATA_DIR / "knowledge_base" / "query_log.db"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(ts: str) -> datetime:
    # token_tracker uses UTC ISO like: 2026-08-25T10:49:33Z
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    return datetime.fromisoformat(ts)


def _sha1(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8", errors="ignore")).hexdigest()


@dataclass(frozen=True)
class DerivedEpisode:
    episode_id: str
    caller: str
    session_id: str
    started_at: str
    ended_at: str
    steps: int
    queries: list[str]
    tokens_in: int
    tokens_out: int
    estimated_savings: int
    methods: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "episode_id": self.episode_id,
            "caller": self.caller,
            "session_id": self.session_id,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "steps": self.steps,
            "queries": self.queries,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "estimated_savings": self.estimated_savings,
            "methods": self.methods,
            "source": "kb_query_log_derived",
        }


def derive_episodes_from_query_log(
    *,
    hours: int = 24,
    gap_minutes: int = 20,
    max_queries_per_episode: int = 20,
) -> list[DerivedEpisode]:
    """Group recent KB queries into episode-like clusters.

    Grouping rules (deterministic):
    - If session_id is set: group by (caller, session_id), but split if time gap > gap_minutes.
    - If session_id is empty: group by caller only, split if time gap > gap_minutes.
    """
    if not QUERY_LOG_DB.exists():
        return []

    since = _utc_now() - timedelta(hours=hours)
    since_iso = since.isoformat(timespec="seconds").replace("+00:00", "Z")

    conn = sqlite3.connect(str(QUERY_LOG_DB))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT id, ts, query, search_method, tokens_in, tokens_out, estimated_savings, caller, session_id
            FROM query_log
            WHERE ts >= ?
            ORDER BY ts ASC, id ASC
            """,
            (since_iso,),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return []

    episodes: list[DerivedEpisode] = []

    cur_key: tuple[str, str] | None = None
    cur_rows: list[sqlite3.Row] = []
    cur_start: datetime | None = None
    cur_end: datetime | None = None

    def flush() -> None:
        nonlocal cur_key, cur_rows, cur_start, cur_end
        if not cur_rows or not cur_key or not cur_start or not cur_end:
            cur_key = None
            cur_rows = []
            cur_start = None
            cur_end = None
            return

        caller, sess = cur_key
        qs = [str(r["query"]) for r in cur_rows][-max_queries_per_episode:]
        tin = int(sum(int(r["tokens_in"] or 0) for r in cur_rows))
        tout = int(sum(int(r["tokens_out"] or 0) for r in cur_rows))
        sav = int(sum(int(r["estimated_savings"] or 0) for r in cur_rows))
        methods = sorted({str(r["search_method"]) for r in cur_rows if r["search_method"]})

        stable = f"{caller}|{sess}|{cur_start.isoformat()}|{cur_end.isoformat()}|{qs[0] if qs else ''}"
        eid = _sha1(stable)[:12]

        episodes.append(
            DerivedEpisode(
                episode_id=eid,
                caller=caller,
                session_id=sess,
                started_at=cur_start.isoformat().replace("+00:00", "Z"),
                ended_at=cur_end.isoformat().replace("+00:00", "Z"),
                steps=len(cur_rows),
                queries=qs,
                tokens_in=tin,
                tokens_out=tout,
                estimated_savings=sav,
                methods=methods,
            )
        )

        cur_key = None
        cur_rows = []
        cur_start = None
        cur_end = None

    gap = timedelta(minutes=gap_minutes)

    for r in rows:
        caller = str(r["caller"] or "").strip() or "unknown"
        sess = str(r["session_id"] or "").strip() or ""
        sess_key = sess if sess else "__auto__"
        key = (caller, sess_key)
        ts = _parse_ts(str(r["ts"]))

        if cur_key is None:
            cur_key = key
            cur_rows = [r]
            cur_start = ts
            cur_end = ts
            continue

        assert cur_end is not None
        if key != cur_key or (ts - cur_end) > gap:
            flush()
            cur_key = key
            cur_rows = [r]
            cur_start = ts
            cur_end = ts
            continue

        cur_rows.append(r)
        cur_end = ts

    flush()

    return sorted(episodes, key=lambda e: e.started_at, reverse=True)


def format_episodes_text(episodes: list[DerivedEpisode]) -> str:
    if not episodes:
        return "No derived episodes found."
    lines: list[str] = []
    for e in episodes:
        sess = "" if e.session_id == "__auto__" else e.session_id
        lines.append(
            f"- {e.episode_id}  {e.started_at} → {e.ended_at}  "
            f"caller={e.caller}{(' session=' + sess) if sess else ''}  "
            f"steps={e.steps}  methods={','.join(e.methods) or '-'}  "
            f"tout={e.tokens_out}  sav={e.estimated_savings}"
        )
        for q in e.queries[:5]:
            q1 = q.strip().replace("\n", " ")
            lines.append(f"    • {q1[:140]}")
        if len(e.queries) > 5:
            lines.append(f"    • … (+{len(e.queries) - 5} more)")
    return "\n".join(lines)


def format_episodes_json(episodes: list[DerivedEpisode]) -> str:
    return json.dumps(
        {"count": len(episodes), "episodes": [e.to_dict() for e in episodes]},
        indent=2,
        ensure_ascii=False,
    )


__all__ = [
    "DerivedEpisode",
    "derive_episodes_from_query_log",
    "format_episodes_text",
    "format_episodes_json",
]

