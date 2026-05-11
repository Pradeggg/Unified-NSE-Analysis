from __future__ import annotations

from pathlib import Path

from voice_capture import prepare_audio_input, record_microphone
from voice_persona import (
    build_spoken_summary,
    normalize_spoken_query,
    validate_actionable_spoken_query,
    validate_supported_spoken_language,
)
from voice_session import create_voice_session, write_voice_manifest
from voice_synth import play_audio, synthesize_speech
from voice_transcribe import transcribe_audio


def run_voice_query(
    audio_file=None,
    seconds: int = 20,
    root_dir: str | Path = "data/voice_sessions",
    transcriber=None,
    agent_runner=None,
    synthesizer=None,
    player=None,
    want_audio: bool = True,
    auto_play: bool = True,
    voice: str = "cedar",
    confirm_callback=None,
    pre_agent_callback=None,
) -> dict:
    session = create_voice_session(root_dir=root_dir)
    audio_result = prepare_audio_input(audio_file, session["input_audio_path"]) if audio_file else record_microphone(session["input_audio_path"], seconds=seconds)
    if audio_result.get("status") != "ok":
        manifest_path = write_voice_manifest(session, status="error", error=audio_result.get("error", "audio capture failed"))
        return {**session, **audio_result, "manifest_path": manifest_path}

    actual_audio_path = audio_result["audio_path"]
    tx = transcriber(Path(actual_audio_path)) if transcriber else transcribe_audio(actual_audio_path)
    if tx.get("status") != "ok":
        manifest_path = write_voice_manifest(session, status="error", error=tx.get("error", "transcription failed"), audio=audio_result)
        return {**session, "status": "error", "error": tx.get("error", "transcription failed"), "manifest_path": manifest_path}

    transcript = tx.get("text", "")
    language_check = validate_supported_spoken_language(transcript)
    if not language_check.get("ok"):
        Path(session["transcript_path"]).write_text(transcript, encoding="utf-8")
        manifest_path = write_voice_manifest(
            session,
            status="unsupported_language",
            audio=audio_result,
            transcription=tx,
            transcript=transcript,
            error=language_check.get("error"),
            supported_languages="English,Hindi",
        )
        return {
            **session,
            "status": "unsupported_language",
            "error": language_check.get("error"),
            "transcript": transcript,
            "manifest_path": manifest_path,
        }

    actionable_check = validate_actionable_spoken_query(transcript)
    if not actionable_check.get("ok"):
        Path(session["transcript_path"]).write_text(transcript, encoding="utf-8")
        manifest_path = write_voice_manifest(
            session,
            status="unclear_transcript",
            audio=audio_result,
            transcription=tx,
            transcript=transcript,
            error=actionable_check.get("error"),
        )
        return {
            **session,
            "status": "unclear_transcript",
            "error": actionable_check.get("error"),
            "transcript": transcript,
            "manifest_path": manifest_path,
        }

    normalized = normalize_spoken_query(transcript)
    Path(session["transcript_path"]).write_text(transcript, encoding="utf-8")
    Path(session["normalized_query_path"]).write_text(normalized, encoding="utf-8")

    if confirm_callback:
        decision = confirm_callback(transcript, normalized)
        if not decision.get("ok"):
            manifest_path = write_voice_manifest(
                session,
                status="cancelled",
                transcript=transcript,
                normalized_query=normalized,
                reason=decision.get("reason", "not confirmed"),
            )
            return {
                **session,
                "status": "cancelled",
                "transcript": transcript,
                "normalized_query": normalized,
                "manifest_path": manifest_path,
                "reason": decision.get("reason", "not confirmed"),
            }
        normalized = decision.get("normalized_query") or normalized
        Path(session["normalized_query_path"]).write_text(normalized, encoding="utf-8")

    if pre_agent_callback:
        decision = pre_agent_callback(transcript, normalized) or {}
        if decision.get("stop"):
            manifest_path = write_voice_manifest(
                session,
                status="stopped",
                transcript=transcript,
                normalized_query=normalized,
                reason=decision.get("reason", "stopped by voice command"),
            )
            return {
                **session,
                "status": "stopped",
                "transcript": transcript,
                "normalized_query": normalized,
                "manifest_path": manifest_path,
                "reason": decision.get("reason", "stopped by voice command"),
            }

    if not agent_runner:
        manifest_path = write_voice_manifest(session, status="needs_agent_runner", transcript=transcript, normalized_query=normalized)
        return {**session, "status": "needs_agent_runner", "transcript": transcript, "normalized_query": normalized, "manifest_path": manifest_path}

    try:
        answer_result = agent_runner(normalized)
        answer = answer_result.get("answer", str(answer_result)) if isinstance(answer_result, dict) else str(answer_result)
    except Exception as exc:
        manifest_path = write_voice_manifest(session, status="error", transcript=transcript, normalized_query=normalized, error=str(exc))
        return {**session, "status": "error", "error": str(exc), "transcript": transcript, "normalized_query": normalized, "manifest_path": manifest_path}

    Path(session["full_answer_path"]).write_text(answer, encoding="utf-8")
    spoken = build_spoken_summary(normalized, answer)
    Path(session["spoken_summary_path"]).write_text(spoken, encoding="utf-8")

    synth_result = {"status": "skipped"}
    play_result = {"status": "skipped"}
    if want_audio:
        synth_result = synthesizer(spoken, Path(session["response_audio_path"])) if synthesizer else synthesize_speech(spoken, session["response_audio_path"], voice=voice)
        if auto_play and synth_result.get("status") == "ok" and synth_result.get("audio_path"):
            play_result = play_audio(synth_result["audio_path"], player=player)

    manifest_path = write_voice_manifest(
        session,
        status="ok",
        audio=audio_result,
        transcription=tx,
        transcript=transcript,
        normalized_query=normalized,
        spoken_summary=spoken,
        synthesis=synth_result,
        playback=play_result,
    )
    return {
        **session,
        "status": "ok",
        "transcript": transcript,
        "normalized_query": normalized,
        "answer": answer,
        "spoken_summary": spoken,
        "synthesis": synth_result,
        "playback": play_result,
        "manifest_path": manifest_path,
    }
