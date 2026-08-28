from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


SUPPORTED_AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".webm", ".mp4", ".mpeg", ".mpga", ".aiff", ".aif"}
TRANSCRIPTION_READY_EXTENSIONS = {".wav", ".mp3", ".m4a", ".webm", ".mp4", ".mpeg", ".mpga"}


def prepare_audio_input(audio_file: str | Path, target_path: str | Path) -> dict:
    source = Path(audio_file).expanduser()
    target = Path(target_path)
    if not source.exists():
        return {"status": "error", "error": f"audio file not found: {source}"}
    if source.suffix.lower() not in SUPPORTED_AUDIO_EXTENSIONS:
        return {"status": "error", "error": f"unsupported audio extension: {source.suffix}"}
    if source.suffix.lower() in {".aiff", ".aif"}:
        return _convert_aiff_to_wav(source, target.with_suffix(".wav"))
    target = target.with_suffix(source.suffix.lower()) if source.suffix else target
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    return {"status": "ok", "audio_path": str(target), "source_path": str(source)}


def _convert_aiff_to_wav(source: Path, target: Path) -> dict:
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16", str(source), str(target)], check=True, capture_output=True)
    except Exception as exc:
        return {"status": "error", "error": f"failed to convert AIFF to WAV for transcription: {exc}"}
    if not target.exists() or target.stat().st_size == 0:
        return {"status": "error", "error": "AIFF to WAV conversion produced no audio"}
    return {"status": "ok", "audio_path": str(target), "source_path": str(source), "converted_from": source.suffix.lower()}


def record_microphone(target_path: str | Path, seconds: int = 20, recorder=None) -> dict:
    target = Path(target_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if recorder:
        return recorder(target, seconds)
    return _record_with_afrecord_or_sox(target, seconds)


def _record_with_afrecord_or_sox(target: Path, seconds: int) -> dict:
    swift_recorder = Path(__file__).resolve().parent / "scripts" / "record_macos_microphone.swift"
    commands = [
        ["afrecord", "-d", str(seconds), "-f", "WAVE", str(target)],
        ["rec", "-q", str(target), "trim", "0", str(seconds)],
        ["swift", str(swift_recorder), str(target), str(seconds)],
    ]
    errors: list[str] = []
    for cmd in commands:
        if cmd[0] == "swift" and not swift_recorder.exists():
            errors.append("swift: scripts/record_macos_microphone.swift not found")
            continue
        try:
            subprocess.run(cmd, check=True, capture_output=True)
            if target.exists() and target.stat().st_size > 0:
                return {"status": "ok", "audio_path": str(target), "command": cmd[0]}
            errors.append(f"{cmd[0]}: command produced no audio")
        except FileNotFoundError:
            errors.append(f"{cmd[0]}: command not found")
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or exc.stdout or b"").decode("utf-8", errors="ignore").strip()
            errors.append(f"{cmd[0]}: {detail or exc}")
        except Exception as exc:
            errors.append(f"{cmd[0]}: {exc}")
    return {
        "status": "error",
        "error": "microphone recording failed; grant microphone permission in System Settings, install sox/ffmpeg, or use --audio-file",
        "details": errors,
    }
