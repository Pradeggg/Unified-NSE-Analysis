from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


DEFAULT_TTS_MODEL = os.environ.get("OPENAI_TTS_MODEL", "gpt-4o-mini-tts")
DEFAULT_TTS_VOICE = os.environ.get("OPENAI_TTS_VOICE") or os.environ.get("VOICE", "cedar")
DEFAULT_TTS_INSTRUCTIONS = (
    "Speak like a calm senior Indian-market operator. Be concise, risk-first, "
    "evidence-aware, and avoid hype. This is AI-generated research-only audio, "
    "not investment advice."
)


def synthesize_speech(
    text: str,
    out_path: str | Path,
    provider=None,
    voice: str = DEFAULT_TTS_VOICE,
    model: str = DEFAULT_TTS_MODEL,
    instructions: str = DEFAULT_TTS_INSTRUCTIONS,
    api_key: str | None = None,
    mac_fallback: bool = True,
) -> dict:
    target = Path(out_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if provider:
        return provider(text, target, voice, model, instructions)
    key = api_key if api_key is not None else os.environ.get("OPENAI_API_KEY") or os.environ.get("SHUNYAAI_OPENAI_API_KEY", "")
    if key:
        try:
            from openai import OpenAI

            client = OpenAI(api_key=key)
            with client.audio.speech.with_streaming_response.create(
                model=model,
                voice=voice,
                input=text,
                instructions=instructions,
            ) as response:
                response.stream_to_file(target)
            return {"status": "ok", "audio_path": str(target), "voice": voice, "model": model, "provider": "openai_gpt_tts"}
        except Exception as exc:
            return {"status": "error", "error": str(exc), "provider": "openai_gpt_tts", "model": model}
    if mac_fallback:
        aiff = target.with_suffix(".aiff")
        try:
            subprocess.run(["say", "-o", str(aiff), text], check=True, capture_output=True)
            return {"status": "ok", "audio_path": str(aiff), "voice": "macos", "model": "say", "provider": "macos_say"}
        except Exception as exc:
            return {"status": "error", "error": f"OPENAI_API_KEY not set and macOS say failed: {exc}", "model": model}
    return {"status": "error", "error": "OPENAI_API_KEY not set; cannot synthesize speech", "model": model}


def play_audio(audio_path: str | Path, player=None) -> dict:
    path = Path(audio_path)
    if not path.exists():
        return {"status": "error", "error": f"audio file not found: {path}"}
    if player:
        return player(path)
    try:
        afplay = shutil.which("afplay")
        if afplay:
            subprocess.Popen([afplay, str(path)])
            return {"status": "ok", "audio_path": str(path), "player": "afplay"}
        subprocess.Popen(["open", str(path)])
        return {"status": "ok", "audio_path": str(path), "player": "open"}
    except Exception as exc:
        return {"status": "error", "error": str(exc), "audio_path": str(path)}
