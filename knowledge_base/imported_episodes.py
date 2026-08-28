"""View and search imported episodes (Cursor + Claude metadata).

These episodes are produced by `python -m knowledge_base import-episodes ...`
and stored as JSONL under `data/knowledge_base/`.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from ._common import DATA_DIR


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(ts: str) -> datetime | None:
    if not ts:
        return None
    try:
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        return datetime.fromisoformat(ts).astimezone(timezone.utc)
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


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9_./-]+", (text or "").lower())


@dataclass(frozen=True)
class ImportedEpisodeHit:
    score: float
    episode: dict[str, Any]


def imported_episode_paths(*, project_label: str | None = None) -> dict[str, Path]:
    base = DATA_DIR / "knowledge_base"
    paths: dict[str, Path] = {
        "cursor": base / "episodes_imported_cursor.jsonl",
    }
    if project_label:
        paths["claude"] = base / f"episodes_imported_claude_{project_label}.jsonl"
    else:
        # Fallback: pick the newest imported_claude file if present.
        claude_files = sorted(base.glob("episodes_imported_claude_*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
        if claude_files:
            paths["claude"] = claude_files[0]
    return paths


def load_imported_episodes(
    *,
    days: int = 60,
    sources: list[str] | None = None,
    project_label: str | None = None,
) -> list[dict[str, Any]]:
    """Load imported episodes within the last `days` window."""
    srcs = set((sources or ["claude", "cursor"]))
    paths = imported_episode_paths(project_label=project_label)
    cutoff = _utc_now() - timedelta(days=days)

    out: list[dict[str, Any]] = []
    for src, path in paths.items():
        if src not in srcs:
            continue
        for ep in _read_jsonl(path):
            ts = ep.get("ended_at_utc") or ep.get("updated_at_utc") or ep.get("imported_at_utc") or ""
            dt = _parse_iso(str(ts))
            if dt and dt < cutoff:
                continue
            ep2 = dict(ep)
            ep2["_import_path"] = str(path)
            out.append(ep2)

    def sort_key(e: dict[str, Any]) -> str:
        ts = e.get("ended_at_utc") or e.get("updated_at_utc") or e.get("imported_at_utc") or ""
        return str(ts)

    return sorted(out, key=sort_key, reverse=True)


def search_imported_episodes(
    episodes: list[dict[str, Any]],
    query: str,
    *,
    k: int = 20,
) -> list[ImportedEpisodeHit]:
    """Very lightweight search over metadata fields (no embeddings)."""
    q = (query or "").strip()
    if not q:
        return [ImportedEpisodeHit(score=1.0, episode=e) for e in episodes[:k]]

    q_tokens = set(_tokenize(q))
    q_lower = q.lower()

    hits: list[ImportedEpisodeHit] = []
    for ep in episodes:
        hay = " ".join(
            str(ep.get(f) or "")
            for f in (
                "episode_id",
                "conversation_id",
                "session_id",
                "title",
                "project",
                "source",
                "scope",
            )
        ).strip()
        hay_lower = hay.lower()
        hay_tokens = set(_tokenize(hay))

        overlap = len(q_tokens & hay_tokens)
        substr = 1 if (q_lower and q_lower in hay_lower) else 0

        score = overlap * 2.0 + substr * 3.0
        if score <= 0:
            continue
        hits.append(ImportedEpisodeHit(score=score, episode=ep))

    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[:k]


def format_imported_hits_text(hits: list[ImportedEpisodeHit]) -> str:
    if not hits:
        return "No imported episodes found."
    lines: list[str] = []
    for h in hits:
        e = h.episode
        title = str(e.get("title") or "").strip()
        src = str(e.get("source") or "").strip()
        eid = str(e.get("episode_id") or "").strip()
        ts = e.get("ended_at_utc") or e.get("updated_at_utc") or ""
        extra = ""
        if src == "claude_history":
            extra = f" events={e.get('event_count')}"
        lines.append(f"- score={h.score:.1f}  {eid}  {ts}  src={src}{extra}")
        if title:
            lines.append(f"    • {title[:160]}")
        proj = str(e.get("project") or "").strip()
        if proj:
            lines.append(f"    • project: {proj}")
    return "\n".join(lines)


def format_imported_hits_json(hits: list[ImportedEpisodeHit]) -> str:
    return json.dumps(
        {
            "count": len(hits),
            "results": [{"score": h.score, "episode": h.episode} for h in hits],
        },
        indent=2,
        ensure_ascii=False,
    )


__all__ = [
    "ImportedEpisodeHit",
    "imported_episode_paths",
    "load_imported_episodes",
    "search_imported_episodes",
    "format_imported_hits_text",
    "format_imported_hits_json",
]

