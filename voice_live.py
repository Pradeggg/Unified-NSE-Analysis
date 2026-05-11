from __future__ import annotations

from voice_copilot import run_voice_query


STOP_PHRASES = {
    "stop",
    "exit",
    "quit",
    "goodbye",
    "bye",
    "exit voice mode",
    "stop voice mode",
    "stop listening",
}


def is_stop_phrase(transcript: str) -> bool:
    text = " ".join((transcript or "").strip().lower().split())
    if not text:
        return False
    return text in STOP_PHRASES or text.startswith("stop voice") or text.startswith("exit voice")


def run_voice_live_session(
    agent_runner,
    turns: int = 5,
    seconds: int = 12,
    want_audio: bool = True,
    auto_play: bool = True,
    voice: str = "cedar",
    confirm_callback=None,
    voice_query_runner=None,
    event_callback=None,
) -> dict:
    runner = voice_query_runner or run_voice_query
    emit = event_callback or (lambda event, payload: None)
    max_turns = max(1, int(turns or 1))
    turn_seconds = max(1, int(seconds or 1))
    completed = 0
    history = []

    emit("session_started", {"turns": max_turns, "seconds": turn_seconds, "voice": voice})
    for turn in range(1, max_turns + 1):
        emit("turn_listening", {"turn": turn, "seconds": turn_seconds})
        result = runner(
            seconds=turn_seconds,
            agent_runner=agent_runner,
            want_audio=want_audio,
            auto_play=auto_play,
            voice=voice,
            confirm_callback=confirm_callback,
            pre_agent_callback=lambda transcript, normalized: {
                "stop": is_stop_phrase(transcript),
                "reason": "voice live stop command",
            },
        )
        history.append(result)

        if result.get("status") == "stopped":
            emit("session_stopped", {"turn": turn, "transcript": result.get("transcript", "")})
            return {"status": "stopped", "turns_completed": completed, "history": history}

        if result.get("status") != "ok":
            emit("turn_error", {"turn": turn, "error": result.get("error", result.get("status", "unknown error")), "result": result})
            return {"status": "error", "turns_completed": completed, "history": history, "error": result.get("error", result.get("status"))}

        transcript = result.get("transcript", "")
        emit("turn_transcript", {"turn": turn, "transcript": transcript, "normalized_query": result.get("normalized_query", "")})
        if is_stop_phrase(transcript):
            emit("session_stopped", {"turn": turn, "transcript": transcript})
            return {"status": "stopped", "turns_completed": completed, "history": history}

        completed += 1
        emit(
            "turn_answer",
            {
                "turn": turn,
                "answer": result.get("answer", ""),
                "spoken_summary": result.get("spoken_summary", ""),
                "synthesis": result.get("synthesis", {}),
                "playback": result.get("playback", {}),
                "session_dir": result.get("session_dir", ""),
            },
        )

    emit("session_complete", {"turns_completed": completed})
    return {"status": "complete", "turns_completed": completed, "history": history}
