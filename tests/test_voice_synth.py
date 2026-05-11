import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from voice_synth import play_audio


class VoiceSynthTests(unittest.TestCase):
    def test_play_audio_uses_afplay_when_available(self):
        with TemporaryDirectory() as td:
            audio = Path(td) / "response.mp3"
            audio.write_bytes(b"fake mp3")

            with patch("voice_synth.shutil.which", return_value="/usr/bin/afplay"), patch("voice_synth.subprocess.Popen") as popen:
                result = play_audio(audio)

            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["player"], "afplay")
            popen.assert_called_once_with(["/usr/bin/afplay", str(audio)])


if __name__ == "__main__":
    unittest.main()
