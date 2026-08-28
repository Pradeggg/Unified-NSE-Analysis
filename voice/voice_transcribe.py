from __future__ import annotations

import os
from pathlib import Path


DEFAULT_TRANSCRIBE_MODEL = os.environ.get("OPENAI_TRANSCRIBE_MODEL", "gpt-4o-transcribe")
DEFAULT_TRANSCRIBE_PROMPT = (
    "The speaker will ask a market or stock question in English or Hindi only. "
    "Transcribe exactly in the same language. Do not translate. "
    "If background noise is unclear, prefer an empty or uncertain English transcript over another language."
)


def transcribe_audio(
    audio_path: str | Path,
    provider=None,
    model: str = DEFAULT_TRANSCRIBE_MODEL,
    prompt: str = DEFAULT_TRANSCRIBE_PROMPT,
    api_key: str | None = None,
) -> dict:
    path = Path(audio_path)
    if not path.exists():
        return {"status": "error", "error": f"audio file not found: {path}"}
    if provider:
        return provider(path, model)
    key = api_key if api_key is not None else os.environ.get("OPENAI_API_KEY") or os.environ.get("SHUNYAAI_OPENAI_API_KEY", "")
    if not key:
        return {"status": "error", "error": "OPENAI_API_KEY not set; cannot transcribe audio", "model": model}
    try:
        from openai import OpenAI

        client = OpenAI(api_key=key)
        with path.open("rb") as audio_file:
            transcript = client.audio.transcriptions.create(model=model, file=audio_file, prompt=prompt)
        return {"status": "ok", "text": getattr(transcript, "text", ""), "model": model, "provider": "openai_stt"}
    except Exception as exc:
        return {"status": "error", "error": str(exc), "model": model, "provider": "openai_stt"}
