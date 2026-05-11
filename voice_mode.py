from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from voice_persona import build_spoken_summary
from voice_session import create_voice_session, write_voice_manifest
from voice_synth import play_audio, synthesize_speech


@dataclass
class VoiceModeState:
    enabled: bool = False
    auto_play: bool = True
    voice: str = "cedar"


def handle_voice_mode_command(command: str, state: VoiceModeState) -> dict:
    tokens = (command or "").split()
    action = tokens[1].lower() if len(tokens) > 1 else "status"

    if action in ("on", "enable", "enabled"):
        state.enabled = True
        state.auto_play = "--no-play" not in tokens
        return _status("enabled", state)
    if action in ("off", "disable", "disabled"):
        state.enabled = False
        return _status("disabled", state)
    if action in ("status", "state", "?"):
        return _status("enabled" if state.enabled else "disabled", state)
    return {
        **_status("error", state),
        "error": "usage: /voice-mode on|off|status [--no-play]",
    }


def speak_answer_when_enabled(
    query: str,
    result: dict,
    state: VoiceModeState,
    root_dir: str | Path = "data/voice_sessions",
    synthesizer=None,
    player=None,
) -> dict:
    if not state.enabled:
        return {"status": "skipped", "reason": "voice mode disabled"}

    session = create_voice_session(root_dir=root_dir)
    answer = result.get("answer", "") if isinstance(result, dict) else str(result)
    spoken = build_spoken_summary(query, answer)

    Path(session["normalized_query_path"]).write_text(query or "", encoding="utf-8")
    Path(session["full_answer_path"]).write_text(answer, encoding="utf-8")
    Path(session["spoken_summary_path"]).write_text(spoken, encoding="utf-8")

    synth_result = (
        synthesizer(spoken, Path(session["response_audio_path"]))
        if synthesizer
        else synthesize_speech(spoken, session["response_audio_path"], voice=state.voice)
    )
    play_result = {"status": "skipped"}
    if state.auto_play and synth_result.get("status") == "ok" and synth_result.get("audio_path"):
        play_result = play_audio(synth_result["audio_path"], player=player)

    manifest_path = write_voice_manifest(
        session,
        status="ok" if synth_result.get("status") == "ok" else "error",
        voice_mode="enabled",
        normalized_query=query,
        spoken_summary=spoken,
        synthesis=synth_result,
        playback=play_result,
    )
    return {
        **session,
        "status": "ok" if synth_result.get("status") == "ok" else "error",
        "spoken_summary": spoken,
        "synthesis": synth_result,
        "playback": play_result,
        "manifest_path": manifest_path,
    }


def _status(status: str, state: VoiceModeState) -> dict:
    cue = (
        "Voice mode is on. Type your question and I will speak the answer. "
        "To speak your question, use /ask-voice."
        if state.enabled
        else "Voice mode is off. Use /voice-mode on to speak future text answers."
    )
    return {
        "status": status,
        "enabled": state.enabled,
        "auto_play": state.auto_play,
        "voice": state.voice,
        "cue": cue,
    }
