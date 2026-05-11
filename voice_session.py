from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


DEFAULT_VOICE_SESSION_ROOT = Path("data/voice_sessions")


def create_voice_session(root_dir: str | Path = DEFAULT_VOICE_SESSION_ROOT, clock=None) -> dict:
    now = _now(clock)
    date_part = now[:10]
    stamp = now.replace("-", "").replace(":", "").replace("+", "_").replace("T", "_")[:15]
    session_id = f"voice_{stamp}"
    session_dir = Path(root_dir) / date_part / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    return {
        "session_id": session_id,
        "started_at": now,
        "session_dir": str(session_dir),
        "input_audio_path": str(session_dir / "input.wav"),
        "transcript_path": str(session_dir / "transcript.txt"),
        "normalized_query_path": str(session_dir / "normalized_query.txt"),
        "full_answer_path": str(session_dir / "full_answer.md"),
        "spoken_summary_path": str(session_dir / "spoken_summary.txt"),
        "response_audio_path": str(session_dir / "response.mp3"),
        "manifest_path": str(session_dir / "manifest.json"),
    }


def write_voice_manifest(session: dict, **updates) -> str:
    manifest = dict(session)
    manifest.update(updates)
    path = Path(session["manifest_path"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return str(path)


def _now(clock=None) -> str:
    if clock:
        return str(clock())
    return datetime.now().astimezone().isoformat(timespec="seconds")
