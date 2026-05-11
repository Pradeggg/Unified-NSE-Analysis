# Agent Adda Voice Copilot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a push-to-talk voice copilot that records or accepts spoken questions, transcribes them, routes them through Agent Adda, produces a concise experienced-trader spoken response, and saves the voice session for audit.

**Architecture:** Add a thin voice IO layer around existing Agent Adda intelligence. Keep capture, transcription, persona shaping, synthesis, and orchestration in separate modules. Start with deterministic file-based tests and provider stubs, then wire the terminal commands.

**Tech Stack:** Python 3, existing Agent Adda terminal, OpenAI `gpt-4o-transcribe` / `gpt-4o-mini-transcribe` speech-to-text, OpenAI GPT TTS via `gpt-4o-mini-tts`, macOS `say` fallback, local filesystem session storage, unittest.

---

## Phase V0: Product Contract and Backlog

### V0.1: Voice Copilot Design Doc

**Files:**
- Create: `docs/superpowers/specs/2026-05-10-agent-adda-voice-copilot-design.md`
- Modify: `docs/BACKLOG.md`

- [x] **Step 1: Write design spec**

Spec covers:

```text
goal
user flow
persona
architecture
commands
storage
provider strategy
safety guardrails
success criteria
```

- [x] **Step 2: Verify spec exists**

Run:

```bash
test -f docs/superpowers/specs/2026-05-10-agent-adda-voice-copilot-design.md
```

Expected: exit code 0.

### V0.2: Register Voice Copilot Backlog

**Files:**
- Modify: `docs/BACKLOG.md`
- Modify: `docs/AGENT_ADDA_CAPABILITIES.md`

- [x] **Step 1: Add Branch I backlog entries**

Add:

```text
I0 Voice Copilot Design + Backlog
I1 Voice Session Store
I2 Audio Capture / Audio File Input
I3 Speech-to-Text Provider
I4 Query Normalization + Voice Persona
I5 Agent Execution Orchestrator
I6 GPT Text-to-Speech Provider
I7 /ask-voice Terminal Command
I8 Error Handling + Privacy + Audit
I9 Realtime /voice-live Prototype
```

- [x] **Step 2: Add capability summary**

Add to `docs/AGENT_ADDA_CAPABILITIES.md`:

```text
Voice Copilot
- /ask-voice
- /ask-voice --audio-file
- /ask-voice --confirm
- /ask-voice --no-audio
- /voice-live planned
Default TTS model: gpt-4o-mini-tts
Default TTS voice: cedar
```

- [x] **Step 3: Verify docs**

Run:

```bash
rg -n "Voice Copilot|/ask-voice|/voice-live" docs/BACKLOG.md docs/AGENT_ADDA_CAPABILITIES.md
```

Expected: all three phrases appear.

---

## Phase V1: Session Store

### V1.1: Voice Session Manifest

**Files:**
- Create: `voice_session.py`
- Test: `tests/test_voice_session.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_voice_session.py`:

```python
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from voice_session import create_voice_session, write_voice_manifest


class VoiceSessionTests(unittest.TestCase):
    def test_create_voice_session_creates_expected_paths(self):
        with TemporaryDirectory() as td:
            session = create_voice_session(root_dir=Path(td), clock=lambda: "2026-05-10T10:15:32+05:30")

            self.assertTrue(Path(session["session_dir"]).exists())
            self.assertEqual(Path(session["input_audio_path"]).name, "input.wav")
            self.assertEqual(Path(session["transcript_path"]).name, "transcript.txt")
            self.assertEqual(Path(session["spoken_summary_path"]).name, "spoken_summary.txt")
            self.assertEqual(Path(session["manifest_path"]).name, "manifest.json")

    def test_write_voice_manifest_persists_json(self):
        with TemporaryDirectory() as td:
            session = create_voice_session(root_dir=Path(td), clock=lambda: "2026-05-10T10:15:32+05:30")
            manifest_path = write_voice_manifest(session, transcript="read DMART", normalized_query="Analyze DMART", status="ok")

            data = json.loads(Path(manifest_path).read_text())
            self.assertEqual(data["transcript"], "read DMART")
            self.assertEqual(data["normalized_query"], "Analyze DMART")
            self.assertEqual(data["status"], "ok")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run failing test**

Run:

```bash
./.venv/bin/python -m unittest tests.test_voice_session -v
```

Expected: fails with `ModuleNotFoundError: No module named 'voice_session'`.

- [ ] **Step 3: Implement session store**

Create `voice_session.py`:

```python
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
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return str(path)


def _now(clock=None) -> str:
    if clock:
        return str(clock())
    return datetime.now().astimezone().isoformat(timespec="seconds")
```

- [ ] **Step 4: Run passing test**

Run:

```bash
./.venv/bin/python -m unittest tests.test_voice_session -v
```

Expected: 2 tests pass.

---

## Phase V2: Audio Input

### V2.1: Audio File Validation

**Files:**
- Create: `voice_capture.py`
- Test: `tests/test_voice_capture.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_voice_capture.py`:

```python
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from voice_capture import prepare_audio_input


class VoiceCaptureTests(unittest.TestCase):
    def test_prepare_audio_input_copies_audio_file_to_session(self):
        with TemporaryDirectory() as td:
            source = Path(td) / "question.wav"
            target = Path(td) / "session" / "input.wav"
            source.write_bytes(b"RIFF fake wav bytes")

            result = prepare_audio_input(audio_file=source, target_path=target)

            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["audio_path"], str(target))
            self.assertEqual(target.read_bytes(), b"RIFF fake wav bytes")

    def test_prepare_audio_input_rejects_missing_file(self):
        with TemporaryDirectory() as td:
            result = prepare_audio_input(audio_file=Path(td) / "missing.wav", target_path=Path(td) / "input.wav")

            self.assertEqual(result["status"], "error")
            self.assertIn("not found", result["error"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run failing test**

Run:

```bash
./.venv/bin/python -m unittest tests.test_voice_capture -v
```

Expected: fails with missing module.

- [ ] **Step 3: Implement audio file input**

Create `voice_capture.py`:

```python
from __future__ import annotations

import shutil
from pathlib import Path


SUPPORTED_AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".webm", ".mp4", ".mpeg", ".mpga"}


def prepare_audio_input(audio_file: str | Path, target_path: str | Path) -> dict:
    source = Path(audio_file).expanduser()
    target = Path(target_path)
    if not source.exists():
        return {"status": "error", "error": f"audio file not found: {source}"}
    if source.suffix.lower() not in SUPPORTED_AUDIO_EXTENSIONS:
        return {"status": "error", "error": f"unsupported audio extension: {source.suffix}"}
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    return {"status": "ok", "audio_path": str(target), "source_path": str(source)}
```

- [ ] **Step 4: Run passing test**

Run:

```bash
./.venv/bin/python -m unittest tests.test_voice_capture -v
```

Expected: 2 tests pass.

### V2.2: Microphone Capture Shell Wrapper

**Files:**
- Modify: `voice_capture.py`
- Test: `tests/test_voice_capture.py`

- [ ] **Step 1: Add tests for command construction**

Append:

```python
from voice_capture import record_microphone


def test_record_microphone_uses_injected_recorder(self):
    calls = []
    def recorder(target_path, seconds):
        calls.append((str(target_path), seconds))
        Path(target_path).write_bytes(b"RIFF recorded")
        return {"status": "ok", "audio_path": str(target_path)}

    with TemporaryDirectory() as td:
        target = Path(td) / "input.wav"
        result = record_microphone(target, seconds=3, recorder=recorder)

    assert result["status"] == "ok"
    assert calls[0][1] == 3
```

- [ ] **Step 2: Implement injectable recorder**

Add:

```python
import subprocess


def record_microphone(target_path: str | Path, seconds: int = 20, recorder=None) -> dict:
    target = Path(target_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if recorder:
        return recorder(target, seconds)
    return _record_with_sox_or_afrecord(target, seconds)


def _record_with_sox_or_afrecord(target: Path, seconds: int) -> dict:
    commands = [
        ["rec", "-q", str(target), "trim", "0", str(seconds)],
        ["afrecord", "-d", str(seconds), "-f", "WAVE", str(target)],
    ]
    errors = []
    for cmd in commands:
        try:
            subprocess.run(cmd, check=True, capture_output=True)
            return {"status": "ok", "audio_path": str(target), "command": cmd[0]}
        except Exception as exc:
            errors.append(f"{cmd[0]}: {exc}")
    return {"status": "error", "error": "microphone recording failed; install sox or use --audio-file", "details": errors}
```

- [ ] **Step 3: Run tests**

Run:

```bash
./.venv/bin/python -m unittest tests.test_voice_capture -v
```

Expected: tests pass without requiring a microphone.

---

## Phase V3: Speech-to-Text

### V3.1: Transcription Provider Abstraction

**Files:**
- Create: `voice_transcribe.py`
- Test: `tests/test_voice_transcribe.py`

- [ ] **Step 1: Write failing tests**

Create:

```python
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from voice_transcribe import transcribe_audio


class VoiceTranscribeTests(unittest.TestCase):
    def test_transcribe_audio_uses_injected_provider(self):
        def provider(path, model):
            return {"status": "ok", "text": "what is your read on DMART", "model": model}

        with TemporaryDirectory() as td:
            audio = Path(td) / "input.wav"
            audio.write_bytes(b"RIFF")
            result = transcribe_audio(audio, provider=provider, model="fake-transcribe")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["text"], "what is your read on DMART")
        self.assertEqual(result["model"], "fake-transcribe")

    def test_transcribe_audio_returns_clear_error_without_api_key(self):
        with TemporaryDirectory() as td:
            audio = Path(td) / "input.wav"
            audio.write_bytes(b"RIFF")
            result = transcribe_audio(audio, api_key="", provider=None)

        self.assertEqual(result["status"], "error")
        self.assertIn("OPENAI_API_KEY", result["error"])
```

- [ ] **Step 2: Implement transcription**

Create `voice_transcribe.py`:

```python
from __future__ import annotations

import os
from pathlib import Path


DEFAULT_TRANSCRIBE_MODEL = os.environ.get("OPENAI_TRANSCRIBE_MODEL", "gpt-4o-transcribe")


def transcribe_audio(audio_path: str | Path, provider=None, model: str = DEFAULT_TRANSCRIBE_MODEL, api_key: str | None = None) -> dict:
    path = Path(audio_path)
    if not path.exists():
        return {"status": "error", "error": f"audio file not found: {path}"}
    if provider:
        return provider(path, model)
    key = api_key if api_key is not None else os.environ.get("OPENAI_API_KEY", "")
    if not key:
        return {"status": "error", "error": "OPENAI_API_KEY not set; cannot transcribe audio"}
    try:
        from openai import OpenAI
        client = OpenAI(api_key=key)
        with path.open("rb") as audio_file:
            transcript = client.audio.transcriptions.create(model=model, file=audio_file)
        return {"status": "ok", "text": getattr(transcript, "text", ""), "model": model}
    except Exception as exc:
        return {"status": "error", "error": str(exc), "model": model}
```

- [ ] **Step 3: Run tests**

Run:

```bash
./.venv/bin/python -m unittest tests.test_voice_transcribe -v
```

Expected: 2 tests pass.

---

## Phase V4: Voice Persona and Query Normalization

### V4.1: Normalize Spoken Query

**Files:**
- Create: `voice_persona.py`
- Test: `tests/test_voice_persona.py`

- [ ] **Step 1: Write tests**

Create:

```python
import unittest

from voice_persona import normalize_spoken_query, build_spoken_summary


class VoicePersonaTests(unittest.TestCase):
    def test_normalize_spoken_query_maps_market_language(self):
        result = normalize_spoken_query("what's your read on d mart after results")

        self.assertIn("DMART", result)
        self.assertIn("results", result.lower())
        self.assertIn("risk", result.lower())

    def test_build_spoken_summary_is_concise_and_risk_first(self):
        answer = "DMART has a value retail business model. " * 80
        result = build_spoken_summary("DMART", "Analyze DMART", answer)

        self.assertLessEqual(len(result.split()), 180)
        self.assertIn("Research-only", result)
```

- [ ] **Step 2: Implement deterministic persona helpers**

Create `voice_persona.py`:

```python
from __future__ import annotations

import re


ALIASES = {
    "d mart": "DMART",
    "dmart": "DMART",
    "avenue supermarts": "DMART",
}


def normalize_spoken_query(transcript: str) -> str:
    text = re.sub(r"\s+", " ", transcript or "").strip()
    lowered = text.lower()
    for alias, symbol in ALIASES.items():
        if alias in lowered:
            text = re.sub(alias, symbol, text, flags=re.I)
    if "read on" in lowered or "view on" in lowered:
        return f"Analyze {text}. Include evidence, risks, market context, and what to watch next."
    if "after results" in lowered:
        return f"Analyze {text}. Include latest results, margin drivers, risks, and trading watchpoints."
    return text


def build_spoken_summary(symbol: str, query: str, answer: str, max_words: int = 170) -> str:
    clean = re.sub(r"\s+", " ", answer or "").strip()
    words = clean.split()
    excerpt = " ".join(words[: max(40, max_words - 45)])
    return (
        f"My read on {symbol or 'this'}: {excerpt} "
        "The key is to separate evidence from inference, and watch the risk or invalidation. "
        "Research-only, not investment advice. Verify against official data and your own risk plan."
    )
```

- [ ] **Step 3: Run tests**

Run:

```bash
./.venv/bin/python -m unittest tests.test_voice_persona -v
```

Expected: tests pass.

---

## Phase V5: GPT Text-to-Speech

### V5.1: GPT TTS Voice Synthesis Provider

**Files:**
- Create: `voice_synth.py`
- Test: `tests/test_voice_synth.py`

- [ ] **Step 1: Write provider tests**

Create:

```python
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from voice_synth import synthesize_speech


class VoiceSynthTests(unittest.TestCase):
    def test_synthesize_speech_uses_injected_provider(self):
        def provider(text, out_path, voice, model, instructions):
            Path(out_path).write_bytes(b"audio")
            return {"status": "ok", "audio_path": str(out_path), "voice": voice, "model": model, "instructions": instructions}

        with TemporaryDirectory() as td:
            result = synthesize_speech("hello", Path(td) / "response.mp3", provider=provider, voice="cedar")

        self.assertEqual(result["status"], "ok")
        self.assertTrue(Path(result["audio_path"]).exists())
        self.assertEqual(result["voice"], "cedar")
        self.assertIn("senior Indian-market operator", result["instructions"])

    def test_synthesize_speech_returns_error_without_api_key_when_no_provider(self):
        with TemporaryDirectory() as td:
            result = synthesize_speech("hello", Path(td) / "response.mp3", api_key="", provider=None, mac_fallback=False)

        self.assertEqual(result["status"], "error")
        self.assertIn("OPENAI_API_KEY", result["error"])
```

- [ ] **Step 2: Implement synthesis**

Create `voice_synth.py`:

```python
from __future__ import annotations

import os
import subprocess
from pathlib import Path


DEFAULT_TTS_MODEL = os.environ.get("OPENAI_TTS_MODEL", "gpt-4o-mini-tts")
DEFAULT_TTS_VOICE = os.environ.get("OPENAI_TTS_VOICE", "cedar")
DEFAULT_TTS_INSTRUCTIONS = (
    "Speak like a senior Indian-market operator: calm, concise, risk-first, "
    "evidence-aware, no hype, no guaranteed returns. Make it sound like a "
    "personal market assistant, not a generic narrator."
)


def synthesize_speech(text: str, out_path: str | Path, provider=None, voice: str = DEFAULT_TTS_VOICE, model: str = DEFAULT_TTS_MODEL, instructions: str = DEFAULT_TTS_INSTRUCTIONS, api_key: str | None = None, mac_fallback: bool = True) -> dict:
    target = Path(out_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if provider:
        return provider(text, target, voice, model, instructions)
    key = api_key if api_key is not None else os.environ.get("OPENAI_API_KEY", "")
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
            return {"status": "error", "error": str(exc), "provider": "openai_gpt_tts"}
    if mac_fallback:
        aiff = target.with_suffix(".aiff")
        try:
            subprocess.run(["say", "-o", str(aiff), text], check=True, capture_output=True)
            return {"status": "ok", "audio_path": str(aiff), "voice": "macos", "provider": "say"}
        except Exception as exc:
            return {"status": "error", "error": f"OPENAI_API_KEY not set and macOS say failed: {exc}"}
    return {"status": "error", "error": "OPENAI_API_KEY not set; cannot synthesize speech"}
```

- [ ] **Step 3: Run tests**

Run:

```bash
./.venv/bin/python -m unittest tests.test_voice_synth -v
```

Expected: tests pass.

---

## Phase V6: End-to-End Copilot Orchestration

### V6.1: Orchestrate File-Based Voice Query

**Files:**
- Create: `voice_copilot.py`
- Test: `tests/test_voice_copilot.py`

- [ ] **Step 1: Write orchestration test**

Create:

```python
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from voice_copilot import run_voice_query


class VoiceCopilotTests(unittest.TestCase):
    def test_run_voice_query_transcribes_executes_summarizes_and_writes_manifest(self):
        with TemporaryDirectory() as td:
            audio = Path(td) / "question.wav"
            audio.write_bytes(b"RIFF")

            result = run_voice_query(
                audio_file=audio,
                root_dir=Path(td) / "sessions",
                transcriber=lambda path: {"status": "ok", "text": "what is your read on d mart after results"},
                agent_runner=lambda query: {"answer": "DMART operates a value retail model. Risk is quick commerce pressure."},
                synthesizer=lambda text, path: {"status": "ok", "audio_path": str(path)},
            )

            self.assertEqual(result["status"], "ok")
            self.assertIn("DMART", result["normalized_query"])
            self.assertTrue(Path(result["manifest_path"]).exists())
            self.assertTrue(Path(result["spoken_summary_path"]).exists())
```

- [ ] **Step 2: Implement orchestrator**

Create `voice_copilot.py`:

```python
from __future__ import annotations

from pathlib import Path

from voice_capture import prepare_audio_input, record_microphone
from voice_persona import build_spoken_summary, normalize_spoken_query
from voice_session import create_voice_session, write_voice_manifest
from voice_synth import synthesize_speech
from voice_transcribe import transcribe_audio


def run_voice_query(audio_file=None, seconds: int = 20, root_dir="data/voice_sessions", transcriber=None, agent_runner=None, synthesizer=None, want_audio: bool = True) -> dict:
    session = create_voice_session(root_dir=root_dir)
    if audio_file:
        audio_result = prepare_audio_input(audio_file, session["input_audio_path"])
    else:
        audio_result = record_microphone(session["input_audio_path"], seconds=seconds)
    if audio_result.get("status") != "ok":
        write_voice_manifest(session, status="error", error=audio_result.get("error", "audio capture failed"))
        return {**session, **audio_result}

    tx = transcriber(Path(session["input_audio_path"])) if transcriber else transcribe_audio(session["input_audio_path"])
    if tx.get("status") != "ok":
        write_voice_manifest(session, status="error", error=tx.get("error", "transcription failed"))
        return {**session, "status": "error", "error": tx.get("error", "transcription failed")}

    transcript = tx.get("text", "")
    normalized = normalize_spoken_query(transcript)
    Path(session["transcript_path"]).write_text(transcript)
    Path(session["normalized_query_path"]).write_text(normalized)

    if not agent_runner:
        return {**session, "status": "needs_agent_runner", "transcript": transcript, "normalized_query": normalized}
    answer_result = agent_runner(normalized)
    answer = answer_result.get("answer", str(answer_result))
    Path(session["full_answer_path"]).write_text(answer)

    symbol = _guess_symbol(normalized)
    spoken = build_spoken_summary(symbol, normalized, answer)
    Path(session["spoken_summary_path"]).write_text(spoken)

    synth_result = {"status": "skipped"}
    if want_audio:
        synth_result = synthesizer(spoken, Path(session["response_audio_path"])) if synthesizer else synthesize_speech(spoken, session["response_audio_path"])

    manifest_path = write_voice_manifest(
        session,
        transcript=transcript,
        normalized_query=normalized,
        spoken_summary=spoken,
        status="ok",
        synthesis=synth_result,
    )
    return {
        **session,
        "status": "ok",
        "transcript": transcript,
        "normalized_query": normalized,
        "answer": answer,
        "spoken_summary": spoken,
        "synthesis": synth_result,
        "manifest_path": manifest_path,
    }


def _guess_symbol(query: str) -> str:
    for token in query.split():
        if token.isupper() and 2 <= len(token) <= 12:
            return token
    return ""
```

- [ ] **Step 3: Run tests**

Run:

```bash
./.venv/bin/python -m unittest tests.test_voice_copilot -v
```

Expected: tests pass.

---

## Phase V7: Terminal Command

### V7.1: `/ask-voice` Backend Command

**Files:**
- Create: `voice_command.py`
- Test: `tests/test_voice_command.py`

- [ ] **Step 1: Write command parsing tests**

Create:

```python
import unittest

from voice_command import parse_ask_voice_args


class VoiceCommandTests(unittest.TestCase):
    def test_parse_ask_voice_args(self):
        args = parse_ask_voice_args("--audio-file question.wav --seconds 12 --no-audio --confirm --voice nova")

        self.assertEqual(args.audio_file, "question.wav")
        self.assertEqual(args.seconds, 12)
        self.assertFalse(args.want_audio)
        self.assertTrue(args.confirm)
        self.assertEqual(args.voice, "nova")
```

- [ ] **Step 2: Implement parser**

Create `voice_command.py`:

```python
from __future__ import annotations

import argparse
import shlex


def parse_ask_voice_args(command_args: str | list[str]) -> argparse.Namespace:
    tokens = shlex.split(command_args) if isinstance(command_args, str) else list(command_args)
    parser = argparse.ArgumentParser(prog="/ask-voice", add_help=False)
    parser.add_argument("--audio-file", default="")
    parser.add_argument("--seconds", type=int, default=20)
    parser.add_argument("--confirm", action="store_true")
    parser.add_argument("--no-audio", dest="want_audio", action="store_false")
    parser.add_argument("--voice", default="cedar")
    parser.set_defaults(want_audio=True)
    return parser.parse_args(tokens)
```

- [ ] **Step 3: Run tests**

Run:

```bash
./.venv/bin/python -m unittest tests.test_voice_command -v
```

Expected: tests pass.

### V7.2: `nse_agent.py` Route

**Files:**
- Modify: `nse_agent.py`
- Test: `tests/test_voice_command.py`

- [ ] **Step 1: Add slash command entries**

Add to `_SLASH_COMMANDS`:

```python
("/ask-voice", "Push-to-talk voice question: record, transcribe, analyze, speak"),
("/ask-voice --audio-file question.wav", "Run voice copilot from an existing audio file"),
("/voice-live", "Realtime voice assistant mode (planned)"),
```

- [ ] **Step 2: Add route**

Add route near other direct commands:

```python
if text.lower().startswith("/ask-voice"):
    from voice_command import parse_ask_voice_args
    from voice_copilot import run_voice_query
    args = parse_ask_voice_args(text[len("/ask-voice"):].strip())
    result = run_voice_query(
        audio_file=args.audio_file or None,
        seconds=args.seconds,
        agent_runner=lambda query: agent.query(query, show_trace=show_trace),
        want_audio=args.want_audio,
    )
    console.print(f"[green]Transcript:[/green] {result.get('transcript', '')}")
    console.print(f"[green]Query:[/green] {result.get('normalized_query', '')}")
    console.print(f"[green]Spoken summary:[/green] {result.get('spoken_summary', '')}")
    if result.get("synthesis", {}).get("audio_path"):
        console.print(f"[green]Audio:[/green] {result['synthesis']['audio_path']}")
    continue
```

- [ ] **Step 3: Add `/voice-live` placeholder**

Add:

```python
if text.lower().startswith("/voice-live"):
    console.print("[yellow]/voice-live is planned for the Realtime phase. Use /ask-voice first.[/yellow]")
    continue
```

- [ ] **Step 4: Compile**

Run:

```bash
./.venv/bin/python -m py_compile nse_agent.py voice_command.py voice_copilot.py
```

Expected: exit code 0.

---

## Phase V8: Quality, Safety, and Audit

### V8.1: Voice Error Matrix

**Files:**
- Modify: `tests/test_voice_copilot.py`
- Modify: `voice_copilot.py`

- [ ] **Step 1: Add error tests**

Test:

```text
missing audio file -> structured error
transcription failure -> manifest status error
agent failure -> manifest status error
TTS failure -> text answer still returned
```

- [ ] **Step 2: Implement missing branches**

Ensure every error returns:

```python
{
  "status": "error",
  "error": "...",
  "manifest_path": "..."
}
```

- [ ] **Step 3: Run tests**

Run:

```bash
./.venv/bin/python -m unittest tests.test_voice_copilot -v
```

Expected: all error tests pass.

### V8.2: Privacy and Disclosure

**Files:**
- Modify: `docs/AGENT_ADDA_CAPABILITIES.md`
- Modify: `voice_persona.py`

- [ ] **Step 1: Add disclosure to docs**

Add:

```text
Voice output is AI-generated. Voice sessions are stored locally under data/voice_sessions unless deleted by the user.
```

- [ ] **Step 2: Ensure spoken summary includes disclosure**

Update `build_spoken_summary()` so every generated spoken answer ends with:

```text
This is AI-generated research-only audio, not investment advice.
```

- [ ] **Step 3: Test disclosure**

Add assertion to `tests/test_voice_persona.py`:

```python
self.assertIn("AI-generated research-only audio", result)
```

---

## Phase V9: Realtime Voice Planning

### V9.1: `/voice-live` Technical Spike

**Files:**
- Create: `docs/superpowers/specs/2026-05-10-agent-adda-realtime-voice-spike.md`

- [ ] **Step 1: Document realtime options**

Cover:

```text
OpenAI Realtime API
WebRTC browser UI
WebSocket terminal/server prototype
turn detection
interruptions
tool calling
session audit
latency targets
```

- [ ] **Step 2: Decide implementation path**

Recommendation:

```text
Browser/WebRTC for polished realtime voice UI after /ask-voice is stable.
Terminal WebSocket only for a short engineering spike.
```

---

## Phase V10: End-to-End Verification

### V10.1: Focused Test Suite

**Files:**
- Read: all voice modules and tests

- [ ] **Step 1: Run voice suite**

Run:

```bash
./.venv/bin/python -m unittest \
  tests.test_voice_session \
  tests.test_voice_capture \
  tests.test_voice_transcribe \
  tests.test_voice_persona \
  tests.test_voice_synth \
  tests.test_voice_copilot \
  tests.test_voice_command -v
```

Expected: all tests pass.

- [ ] **Step 2: Compile**

Run:

```bash
./.venv/bin/python -m py_compile \
  voice_session.py voice_capture.py voice_transcribe.py voice_persona.py \
  voice_synth.py voice_copilot.py voice_command.py nse_agent.py
```

Expected: exit code 0.

- [ ] **Step 3: Manual dry run**

Run:

```bash
./.venv/bin/python - <<'PY'
from pathlib import Path
from tempfile import TemporaryDirectory
from voice_copilot import run_voice_query

with TemporaryDirectory() as td:
    audio = Path(td) / "q.wav"
    audio.write_bytes(b"RIFF")
    result = run_voice_query(
        audio_file=audio,
        root_dir=Path(td) / "sessions",
        transcriber=lambda path: {"status": "ok", "text": "what is your read on d mart after results"},
        agent_runner=lambda query: {"answer": "DMART operates a value retail model. Risk is quick commerce pressure."},
        synthesizer=lambda text, path: {"status": "ok", "audio_path": str(path)},
    )
    print(result["status"])
    print(result["normalized_query"])
    print(result["spoken_summary"])
PY
```

Expected:

```text
ok
Analyze ... DMART ...
... Research-only ...
```

---

## Execution Notes

- Keep the first implementation terminal-first.
- Do not build wake-word or always-listening behavior in MVP.
- Do not call live microphone tools in unit tests.
- Use provider injection for STT, TTS, and agent execution.
- Keep voice response under 180 words by default.
- Always save transcript and spoken summary.
- Always include research-only disclaimer.

## Execution Options

1. **Subagent-Driven (recommended):** one worker per phase, review between phases.
2. **Inline Execution:** implement V1-V7 in this session with TDD checkpoints.
