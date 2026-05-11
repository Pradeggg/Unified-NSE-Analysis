# Agent Adda Voice Copilot Design

Date: 2026-05-10
Owner: Agent Adda / Codex
Audience: Agent Adda product and implementation workers
Primary output: voice-enabled market assistant for spoken questions, text analysis, and spoken responses

## Goal

Build a voice-enabled Agent Adda assistant that feels like a personal market copilot: the user asks a question in spoken English, Agent Adda transcribes it, expands and routes it through the existing research/tool stack, generates a concise experienced-trader response, and speaks the answer back.

The first user-facing workflow should be:

```text
/ask-voice
/ask-voice --confirm
/ask-voice --no-audio
/voice-live
```

The first production target is **push-to-talk terminal voice**. Realtime Siri-style voice should be a later phase after the text-to-audio loop is reliable.

## Product Principle

Voice is not just text read aloud.

The spoken answer must be:

- shorter than the full research answer
- structured for listening
- clear about uncertainty
- risk-first
- aware of India + global market context
- explicit when evidence is missing
- research-only, not an investment instruction

## User Experience

### MVP Flow: `/ask-voice`

1. User types `/ask-voice`.
2. Agent Adda records microphone audio for a bounded duration, default 20 seconds.
3. Audio is saved locally under `data/voice_sessions/YYYY-MM-DD/`.
4. Speech-to-text converts audio into a transcript.
5. Transcript is shown in the terminal.
6. If `--confirm` is used, user can approve or edit the transcript before execution.
7. Transcript is routed through the existing Agent Adda query system.
8. The full text result is saved in the voice session folder.
9. A short spoken summary is generated from the result.
10. GPT TTS creates an MP3 response using `gpt-4o-mini-tts`; macOS `say` creates AIFF only as a no-API-key fallback.
11. Agent Adda prints the text answer, spoken summary, audio path, and play command.

### Realtime Flow: `/voice-live`

Later phase:

1. User starts a live voice session.
2. Voice activity detection detects speech turns.
3. User can interrupt the assistant while it is speaking.
4. The assistant can ask clarifying questions.
5. Tool calls happen through the existing Agent Adda tool layer.
6. Audio and text transcripts are saved for audit.

## Persona

The voice persona is an experienced market operator, not a generic chatbot.

Traits:

- speaks like a senior trader/strategist
- understands global markets, Indian indices, sectors, FII/DII, RBI, Budget, options, earnings, and stock behavior
- concise, calm, direct
- separates fact, inference, and action watchpoints
- uses phrases like "my read", "what I would watch", "the risk is", "I would not chase unless"
- avoids hype, blind calls, and certainty theater

Mandatory disclaimer style:

```text
This is research-only, not investment advice. Verify against official data and your own risk plan.
```

## Existing Capabilities to Reuse

The repo already has:

- `nse_agent.py` interactive terminal and slash-command routing
- `terminal/agent.py` NLP/tool orchestration
- `terminal/tools.py::generate_voice_briefing()` one-way OpenAI/GPT TTS helper
- `generate_voice_briefing.py` richer daily-briefing GPT TTS with macOS `say` fallback
- `/voice` daily briefing command
- `/company-index`, `/company-xray`, `/ric company-xray`
- deep search, live quote, options, sector, global, macro, and report tools

The new work should not duplicate market intelligence. It should add a voice IO layer and spoken-response renderer around existing intelligence.

## Architecture

```text
Microphone / audio file
        |
        v
voice_capture.py
        |
        v
voice_transcribe.py
        |
        v
voice_copilot.py
        |-- transcript normalization
        |-- query expansion
        |-- Agent Adda query execution
        |-- spoken summary shaping
        |
        v
voice_synth.py
        |
        v
audio response + transcript + session manifest
```

### Core Modules

| Module | Responsibility |
|--------|----------------|
| `voice_capture.py` | Local microphone capture and audio-file validation |
| `voice_transcribe.py` | Speech-to-text provider abstraction |
| `voice_persona.py` | Spoken response prompt and compression rules |
| `voice_synth.py` | Text-to-speech provider abstraction and macOS fallback |
| `voice_copilot.py` | End-to-end command orchestration |
| `company/market tool layer` | Existing Agent Adda query and slash-command execution |
| `nse_agent.py` | Thin `/ask-voice` and `/voice-live` routes |

### Storage

Voice sessions should be stored locally:

```text
data/voice_sessions/
  2026-05-10/
    session_20260510_101532/
      input.wav
      transcript.txt
      normalized_query.txt
      full_answer.md
      spoken_summary.txt
      response.mp3
      manifest.json
```

Manifest shape:

```json
{
  "session_id": "voice_20260510_101532",
  "started_at": "2026-05-10T10:15:32+05:30",
  "input_audio_path": "data/voice_sessions/2026-05-10/session_20260510_101532/input.wav",
  "transcript": "what is your read on DMART after results",
  "normalized_query": "Analyze DMART after latest results. Include business model, sector, risks, and trading watchpoints.",
  "response_audio_path": "data/voice_sessions/2026-05-10/session_20260510_101532/response.mp3",
  "status": "ok",
  "provider": {
    "stt": "gpt-4o-transcribe",
    "tts": "gpt-4o-mini-tts",
    "tts_voice": "cedar"
  }
}
```

## Provider Strategy

### MVP Providers

- STT: OpenAI speech-to-text if `OPENAI_API_KEY` is available. Default to `gpt-4o-transcribe` for ticker/company-name accuracy; allow `OPENAI_TRANSCRIBE_MODEL=gpt-4o-mini-transcribe` when cost/latency matters more than accuracy.
- TTS: GPT TTS via `gpt-4o-mini-tts` is the primary synthesis path. Do not default to legacy `tts-1` or `tts-1-hd`.
- TTS voice: default to `cedar` for a grounded assistant tone; allow `--voice` override for supported voices.
- TTS instructions: every synthesis call should pass an `instructions` string that enforces the Agent Adda persona: senior Indian-market operator, calm, concise, risk-first, no hype, research-only.
- Fallback TTS: macOS `say` where possible, only when GPT TTS is unavailable.
- Fallback STT: no automatic fallback in MVP; return a clear error and allow `--audio-file` input.

### Later Providers

- Realtime speech-to-speech using OpenAI Realtime API.
- Browser/WebRTC local UI.
- Wake-word or always-listening mode only after explicit privacy design.

## Command Design

### `/ask-voice`

```text
/ask-voice
/ask-voice --seconds 20
/ask-voice --confirm
/ask-voice --no-audio
/ask-voice --audio-file ~/Downloads/question.wav
/ask-voice --voice cedar
```

### `/voice-live`

```text
/voice-live
/voice-live --dry-run
/voice-live --text-audit
```

`/voice-live` should initially print "planned/not enabled" until the MVP loop is stable.

## Spoken Response Shape

Every spoken answer should use this structure:

```text
1. One-line read
2. Evidence behind the read
3. Risk or invalidation
4. What to watch next
5. Research-only disclaimer
```

Example:

```text
My read on DMART is constructive but not chase-worthy yet.
The official evidence still supports a disciplined value-retail model, but the market will care most about same-store sales, gross margin, store expansion, and quick-commerce pressure.
If margins weaken or store additions slow, the thesis gets less attractive.
I would watch management commentary and the next quarter's demand trend before getting aggressive.
Research-only, not investment advice.
```

## Safety and Guardrails

The assistant must:

- distinguish investment research from advice
- avoid guaranteed return language
- avoid "buy now" or "sell now" without context
- include risk and invalidation
- surface stale/missing data
- never hide evidence gaps in a confident voice
- save transcript and summary for audit
- disclose AI-generated voice output

## Non-Goals for MVP

- Always-on wake word
- Mobile app
- Browser WebRTC UI
- Interruptible speech
- Voice biometrics
- Hindi/multilingual routing
- Trade execution
- Broker integration

## Success Criteria

MVP is successful when:

- `/ask-voice --audio-file sample.wav --no-audio` transcribes and runs a query in tests
- `/ask-voice` records audio on macOS when microphone tooling exists
- spoken summary is concise and risk-aware
- audio output is created when TTS provider is available
- no API key produces a clear structured error, not a crash
- session manifest contains input, transcript, query, answer, summary, and audio path

## Open Questions

1. Should the first MVP require confirmation before executing every transcript, or only when confidence is low?
2. Should voice answers auto-play or only print the path and play command?
3. Should the default spoken persona be "experienced trader", "portfolio strategist", or "calm personal assistant"?
4. Should `/voice-live` be terminal-only first or browser/WebRTC first?
