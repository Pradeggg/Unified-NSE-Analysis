import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from voice.voice_copilot import run_voice_query


class VoiceCopilotTests(unittest.TestCase):
    def test_run_voice_query_transcribes_executes_summarizes_synthesizes_and_plays(self):
        with TemporaryDirectory() as td:
            audio = Path(td) / "question.wav"
            audio.write_bytes(b"RIFF fake audio")

            played = []

            result = run_voice_query(
                audio_file=audio,
                root_dir=Path(td) / "sessions",
                transcriber=lambda path: {"status": "ok", "text": "what is your read on d mart after results"},
                agent_runner=lambda query: {"answer": "DMART is a value retail model. The risk is quick commerce pressure."},
                synthesizer=lambda text, path: _fake_synth(text, path),
                player=lambda path: played.append(str(path)) or {"status": "ok", "audio_path": str(path)},
            )

            self.assertEqual(result["status"], "ok")
            self.assertIn("DMART", result["normalized_query"])
            self.assertTrue(Path(result["manifest_path"]).exists())
            self.assertTrue(Path(result["spoken_summary_path"]).exists())
            self.assertTrue(Path(result["synthesis"]["audio_path"]).exists())
            self.assertEqual(played, [result["synthesis"]["audio_path"]])

            manifest = json.loads(Path(result["manifest_path"]).read_text())
            self.assertEqual(manifest["status"], "ok")
            self.assertIn("Market Intelligence Assistant from Agent Adda", manifest["spoken_summary"])
            self.assertIn("Would you like me to go deeper", manifest["spoken_summary"])
            self.assertIn("AI-generated research-only audio", manifest["spoken_summary"])

    def test_run_voice_query_returns_clear_error_for_missing_audio(self):
        with TemporaryDirectory() as td:
            result = run_voice_query(audio_file=Path(td) / "missing.wav", root_dir=Path(td) / "sessions")

            self.assertEqual(result["status"], "error")
            self.assertIn("not found", result["error"])
            self.assertTrue(Path(result["manifest_path"]).exists())

    def test_run_voice_query_rejects_unsupported_audio(self):
        with TemporaryDirectory() as td:
            source = Path(td) / "question.txt"
            source.write_text("not audio")

            result = run_voice_query(audio_file=source, root_dir=Path(td) / "sessions")

            self.assertEqual(result["status"], "error")
            self.assertIn("unsupported audio extension", result["error"])

    def test_run_voice_query_can_cancel_after_transcription_confirmation(self):
        with TemporaryDirectory() as td:
            audio = Path(td) / "question.wav"
            audio.write_bytes(b"RIFF fake audio")

            result = run_voice_query(
                audio_file=audio,
                root_dir=Path(td) / "sessions",
                transcriber=lambda path: {"status": "ok", "text": "bad transcript"},
                agent_runner=lambda query: self.fail("agent should not run when confirmation is cancelled"),
                confirm_callback=lambda transcript, query: {"ok": False, "reason": "bad transcript"},
            )

            self.assertEqual(result["status"], "cancelled")
            self.assertEqual(result["reason"], "bad transcript")

    def test_run_voice_query_can_stop_before_agent_execution(self):
        with TemporaryDirectory() as td:
            audio = Path(td) / "question.wav"
            audio.write_bytes(b"RIFF fake audio")

            result = run_voice_query(
                audio_file=audio,
                root_dir=Path(td) / "sessions",
                transcriber=lambda path: {"status": "ok", "text": "stop"},
                agent_runner=lambda query: self.fail("agent should not run when live stop is detected"),
                pre_agent_callback=lambda transcript, query: {"stop": transcript.lower() == "stop", "reason": "voice stop"},
            )

            self.assertEqual(result["status"], "stopped")
            self.assertEqual(result["reason"], "voice stop")

    def test_run_voice_query_rejects_low_information_answer_transcript(self):
        with TemporaryDirectory() as td:
            audio = Path(td) / "question.wav"
            audio.write_bytes(b"RIFF fake audio")

            result = run_voice_query(
                audio_file=audio,
                root_dir=Path(td) / "sessions",
                transcriber=lambda path: {"status": "ok", "text": "Answer"},
                agent_runner=lambda query: self.fail("agent should not run for low-information transcript"),
            )

            self.assertEqual(result["status"], "unclear_transcript")
            self.assertIn("clear market question", result["error"])

    def test_run_voice_query_rejects_non_english_hindi_transcript(self):
        with TemporaryDirectory() as td:
            audio = Path(td) / "question.wav"
            audio.write_bytes(b"RIFF fake audio")

            result = run_voice_query(
                audio_file=audio,
                root_dir=Path(td) / "sessions",
                transcriber=lambda path: {"status": "ok", "text": "巨人が見える"},
                agent_runner=lambda query: self.fail("agent should not run for unsupported language"),
            )

            self.assertEqual(result["status"], "unsupported_language")
            self.assertIn("English or Hindi", result["error"])

    def test_run_voice_query_allows_devanagari_hindi(self):
        with TemporaryDirectory() as td:
            audio = Path(td) / "question.wav"
            audio.write_bytes(b"RIFF fake audio")

            result = run_voice_query(
                audio_file=audio,
                root_dir=Path(td) / "sessions",
                transcriber=lambda path: {"status": "ok", "text": "आज बाजार का मूड कैसा है"},
                agent_runner=lambda query: {"answer": "बाजार का मूड मिला-जुला है।"},
                synthesizer=lambda text, path: _fake_synth(text, path),
                player=lambda path: {"status": "ok", "audio_path": str(path)},
            )

            self.assertEqual(result["status"], "ok")
            self.assertIn("आज बाजार", result["normalized_query"])


def _fake_synth(text, path):
    Path(path).write_bytes(b"audio")
    return {"status": "ok", "audio_path": str(path), "provider": "fake"}


if __name__ == "__main__":
    unittest.main()
