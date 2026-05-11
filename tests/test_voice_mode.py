import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from voice_mode import VoiceModeState, handle_voice_mode_command, speak_answer_when_enabled


class VoiceModeTests(unittest.TestCase):
    def test_handle_voice_mode_command_toggles_and_reports_status(self):
        state = VoiceModeState()

        enabled = handle_voice_mode_command("/voice-mode on", state)
        self.assertTrue(state.enabled)
        self.assertEqual(enabled["status"], "enabled")
        self.assertIn("Type your question", enabled["cue"])
        self.assertIn("/ask-voice", enabled["cue"])

        status = handle_voice_mode_command("/voice-mode status", state)
        self.assertEqual(status["status"], "enabled")
        self.assertTrue(status["enabled"])
        self.assertIn("Type your question", status["cue"])

        disabled = handle_voice_mode_command("/voice-mode off", state)
        self.assertFalse(state.enabled)
        self.assertEqual(disabled["status"], "disabled")
        self.assertIn("Voice mode is off", disabled["cue"])

    def test_speak_answer_when_enabled_synthesizes_and_plays_normal_answer(self):
        with TemporaryDirectory() as td:
            state = VoiceModeState(enabled=True)
            played = []

            result = speak_answer_when_enabled(
                "Analyze DMART",
                {"answer": "DMART remains a disciplined retailer, but quick commerce pressure is rising."},
                state,
                root_dir=Path(td) / "sessions",
                synthesizer=lambda text, path: _fake_synth(text, path),
                player=lambda path: played.append(str(path)) or {"status": "ok", "audio_path": str(path)},
            )

            self.assertEqual(result["status"], "ok")
            self.assertTrue(Path(result["synthesis"]["audio_path"]).exists())
            self.assertEqual(played, [result["synthesis"]["audio_path"]])

            manifest = json.loads(Path(result["manifest_path"]).read_text())
            self.assertIn("Market Intelligence Assistant from Agent Adda", manifest["spoken_summary"])
            self.assertEqual(manifest["voice_mode"], "enabled")

    def test_speak_answer_when_disabled_skips_work(self):
        result = speak_answer_when_enabled(
            "Analyze NIFTY",
            {"answer": "NIFTY is range-bound."},
            VoiceModeState(enabled=False),
            synthesizer=lambda text, path: self.fail("should not synthesize when disabled"),
        )

        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["reason"], "voice mode disabled")


def _fake_synth(text, path):
    Path(path).write_bytes(b"audio")
    return {"status": "ok", "audio_path": str(path), "provider": "fake"}


if __name__ == "__main__":
    unittest.main()
