"""Summaries and search over real episode events (EpisodeStore JSONL)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from .episode_store import EVENTS_JSONL


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(ts: str) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    if not path.exists():
        return
    with path.open("r", encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if isinstance(obj, dict):
                yield obj


@dataclass(frozen=True)
class EpisodeSummary:
    episode_id: str
    started_at: str
    ended_at: str
    caller: str
    goal: str
    status: str
    steps: int
    validators_ok: int
    validators_fail: int
    artifacts: int
    tags: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "episode_id": self.episode_id,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "caller": self.caller,
            "goal": self.goal,
            "status": self.status,
            "steps": self.steps,
            "validators_ok": self.validators_ok,
            "validators_fail": self.validators_fail,
            "artifacts": self.artifacts,
            "tags": self.tags,
        }


def summarize_real_episodes(*, days: int = 30, path: Path | None = None) -> list[EpisodeSummary]:
    p = path or EVENTS_JSONL
    cutoff = _utc_now() - timedelta(days=days)

    # episode_id -> aggregate
    agg: dict[str, dict[str, Any]] = {}
    for ev in _read_jsonl(p):
        eid = str(ev.get("episode_id") or "").strip()
        if not eid:
            continue
        ts = _parse_ts(str(ev.get("ts") or ""))
        if ts and ts < cutoff:
            continue

        a = agg.get(eid)
        if a is None:
            a = {
                "episode_id": eid,
                "started_at": "",
                "ended_at": "",
                "caller": "",
                "goal": "",
                "status": "",
                "steps": 0,
                "validators_ok": 0,
                "validators_fail": 0,
                "artifacts": 0,
                "tags": [],
                "_start_dt": None,
                "_end_dt": None,
            }
            agg[eid] = a

        t = str(ev.get("type") or "")
        if t == "episode_start":
            a["caller"] = str(ev.get("caller") or "")
            a["goal"] = str(ev.get("goal") or "")
            a["tags"] = list(ev.get("tags") or [])
            if ts:
                a["_start_dt"] = ts if a["_start_dt"] is None else min(a["_start_dt"], ts)
        elif t == "episode_end":
            a["status"] = str(ev.get("status") or "")
            if ts:
                a["_end_dt"] = ts if a["_end_dt"] is None else max(a["_end_dt"], ts)
        elif t == "step":
            a["steps"] += 1
        elif t == "validator":
            if bool(ev.get("ok")):
                a["validators_ok"] += 1
            else:
                a["validators_fail"] += 1
        elif t == "artifact":
            a["artifacts"] += 1

        if ts:
            a["_start_dt"] = ts if a["_start_dt"] is None else min(a["_start_dt"], ts)
            a["_end_dt"] = ts if a["_end_dt"] is None else max(a["_end_dt"], ts)

    out: list[EpisodeSummary] = []
    for eid, a in agg.items():
        sdt = a.get("_start_dt")
        edt = a.get("_end_dt")
        started_at = sdt.isoformat().replace("+00:00", "Z") if sdt else ""
        ended_at = edt.isoformat().replace("+00:00", "Z") if edt else ""
        out.append(
            EpisodeSummary(
                episode_id=eid,
                started_at=started_at,
                ended_at=ended_at,
                caller=str(a.get("caller") or ""),
                goal=str(a.get("goal") or ""),
                status=str(a.get("status") or ""),
                steps=int(a.get("steps") or 0),
                validators_ok=int(a.get("validators_ok") or 0),
                validators_fail=int(a.get("validators_fail") or 0),
                artifacts=int(a.get("artifacts") or 0),
                tags=list(a.get("tags") or []),
            )
        )

    out.sort(key=lambda e: e.ended_at or e.started_at, reverse=True)
    return out


def search_real_episodes(episodes: list[EpisodeSummary], query: str, *, k: int = 20) -> list[EpisodeSummary]:
    q = (query or "").strip().lower()
    if not q:
        return episodes[:k]
    q_tokens = set(re.findall(r"[a-z0-9_./-]+", q))
    scored: list[tuple[float, EpisodeSummary]] = []
    for e in episodes:
        hay = " ".join([e.goal, e.caller, " ".join(e.tags), e.status]).lower()
        hay_tokens = set(re.findall(r"[a-z0-9_./-]+", hay))
        overlap = len(q_tokens & hay_tokens)
        substr = 1 if q in hay else 0
        score = overlap * 2.0 + substr * 3.0
        if score <= 0:
            continue
        scored.append((score, e))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [e for _, e in scored[:k]]


def format_real_episodes_text(episodes: list[EpisodeSummary]) -> str:
    if not episodes:
        return "No real episodes found."
    lines: list[str] = []
    for e in episodes:
        lines.append(
            f"- {e.episode_id}  {e.started_at} → {e.ended_at}  "
            f"caller={e.caller or '-'}  status={e.status or '-'}  "
            f"steps={e.steps}  val_ok={e.validators_ok} val_fail={e.validators_fail}  art={e.artifacts}"
        )
        if e.goal:
            lines.append(f"    • {e.goal[:160]}")
        if e.tags:
            lines.append(f"    • tags: {', '.join(e.tags[:10])}")
    return "\n".join(lines)


def format_real_episodes_json(episodes: list[EpisodeSummary]) -> str:
    return json.dumps({"count": len(episodes), "episodes": [e.to_dict() for e in episodes]}, indent=2, ensure_ascii=False)


__all__ = [
    "EpisodeSummary",
    "summarize_real_episodes",
    "search_real_episodes",
    "format_real_episodes_text",
    "format_real_episodes_json",
]

