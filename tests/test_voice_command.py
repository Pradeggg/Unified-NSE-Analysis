import unittest

from voice.voice_command import parse_ask_voice_args, parse_voice_briefing_args, parse_voice_live_args


class VoiceCommandTests(unittest.TestCase):
    def test_parse_voice_briefing_args_defaults_to_tts_and_autoplay(self):
        args = parse_voice_briefing_args("")

        self.assertIsNone(args.date)
        self.assertTrue(args.want_tts)
        self.assertTrue(args.auto_play)

    def test_parse_voice_briefing_args_supports_script_date_and_no_play(self):
        args = parse_voice_briefing_args("script 2026-05-09 --no-play")

        self.assertEqual(args.date, "2026-05-09")
        self.assertFalse(args.want_tts)
        self.assertFalse(args.auto_play)

    def test_parse_ask_voice_args(self):
        args = parse_ask_voice_args("--audio-file question.wav --seconds 12 --no-play --voice cedar")

        self.assertEqual(args.audio_file, "question.wav")
        self.assertEqual(args.seconds, 12)
        self.assertTrue(args.want_audio)
        self.assertFalse(args.auto_play)
        self.assertEqual(args.voice, "cedar")

    def test_parse_voice_live_args(self):
        args = parse_voice_live_args("--turns 2 --seconds 8 --no-play --voice cedar")

        self.assertEqual(args.turns, 2)
        self.assertEqual(args.seconds, 8)
        self.assertFalse(args.auto_play)
        self.assertTrue(args.want_audio)
        self.assertEqual(args.voice, "cedar")


if __name__ == "__main__":
    unittest.main()
