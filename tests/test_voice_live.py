import unittest

from voice_live import is_stop_phrase, run_voice_live_session


class VoiceLiveTests(unittest.TestCase):
    def test_is_stop_phrase_accepts_common_exit_words(self):
        self.assertTrue(is_stop_phrase("stop"))
        self.assertTrue(is_stop_phrase("exit voice mode"))
        self.assertTrue(is_stop_phrase("quit"))
        self.assertFalse(is_stop_phrase("what is the market mood"))

    def test_run_voice_live_session_runs_multiple_turns_until_stop(self):
        events = []
        calls = []
        responses = [
            {
                "status": "ok",
                "transcript": "hello",
                "normalized_query": "Answer this spoken market question: hello",
                "answer": "Hello. What would you like to check?",
                "spoken_summary": "I am the Market Intelligence Assistant from Agent Adda.",
                "synthesis": {"audio_path": "turn1.mp3"},
                "playback": {"status": "ok"},
                "session_dir": "session1",
            },
            {
                "status": "ok",
                "transcript": "stop",
                "normalized_query": "",
                "answer": "",
                "spoken_summary": "",
                "synthesis": {},
                "playback": {"status": "skipped"},
                "session_dir": "session2",
            },
        ]

        result = run_voice_live_session(
            agent_runner=lambda query: {"answer": "unused"},
            turns=5,
            seconds=4,
            voice_query_runner=lambda **kwargs: calls.append(kwargs) or responses.pop(0),
            event_callback=lambda event, payload: events.append((event, payload)),
        )

        self.assertEqual(result["status"], "stopped")
        self.assertEqual(result["turns_completed"], 1)
        self.assertEqual(len(calls), 2)
        self.assertIn(("session_started", {"turns": 5, "seconds": 4, "voice": "cedar"}), events)
        self.assertEqual(events[-1][0], "session_stopped")


if __name__ == "__main__":
    unittest.main()
