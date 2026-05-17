import subprocess
import unittest
from unittest.mock import patch

import nse_agent
from terminal.agent import Agent, _keyword_intent
from terminal.youtube import _run_checked, analyze_youtube_video, parse_youtube_url


PLAYER_HTML = """
<html><script>
var ytInitialPlayerResponse = {
  "videoDetails": {
    "videoId": "0Hnffbj5pgE",
    "title": "Market setup today",
    "author": "Sample Market Channel",
    "channelId": "UC123",
    "lengthSeconds": "600"
  },
  "microformat": {"playerMicroformatRenderer": {"publishDate": "2026-05-17"}},
  "captions": {"playerCaptionsTracklistRenderer": {"captionTracks": [
    {"baseUrl": "https://example.test/captions", "languageCode": "en", "name": {"simpleText": "English"}}
  ]}}
};
</script></html>
"""

TRANSCRIPT_XML = """
<transcript>
  <text start="108.0" dur="5.0">NIFTY is near resistance and banking stocks need confirmation.</text>
  <text start="140.0" dur="6.0">Pharma sector demand and earnings margin are improving.</text>
</transcript>
"""


class YouTubeIngestionTests(unittest.TestCase):
    def test_parse_youtube_url_normalizes_watch_url_and_start_time(self):
        ref = parse_youtube_url("https://www.youtube.com/watch?v=0Hnffbj5pgE&t=108s")

        self.assertEqual(ref.video_id, "0Hnffbj5pgE")
        self.assertEqual(ref.canonical_url, "https://www.youtube.com/watch?v=0Hnffbj5pgE")
        self.assertEqual(ref.start_seconds, 108)

    def test_youtube_command_routes_to_video_analysis_tool(self):
        routed = _keyword_intent("/youtube https://www.youtube.com/watch?v=0Hnffbj5pgE&t=108s")

        self.assertEqual(routed["intent"], "youtube_video_analysis")
        self.assertEqual(routed["plan"][0][0], "analyze_youtube_video")

    def test_youtube_transcribe_routes_with_explicit_opt_in(self):
        routed = _keyword_intent("/youtube transcribe https://www.youtube.com/watch?v=0Hnffbj5pgE")

        self.assertEqual(routed["intent"], "youtube_video_transcription")
        self.assertTrue(routed["plan"][0][1]["transcribe"])

    def test_interactive_terminal_exposes_youtube_command(self):
        slash_commands = [cmd for cmd, _desc in nse_agent._SLASH_COMMANDS]

        self.assertIn("/youtube", slash_commands)
        self.assertIn("/youtube", nse_agent._CMD_CATEGORIES)

    def test_analyze_youtube_video_uses_captions_without_full_transcript(self):
        def fake_get(url, timeout=20):
            return TRANSCRIPT_XML if "captions" in url else PLAYER_HTML

        with patch("terminal.youtube._http_get", side_effect=fake_get):
            result = analyze_youtube_video("https://www.youtube.com/watch?v=0Hnffbj5pgE&t=108s", persist=False)

        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["transcript"]["available"])
        self.assertFalse(result["transcript"]["stored_full_text"])
        self.assertTrue(result["market_insights"])
        self.assertTrue(result["suggested_followups"])
        self.assertNotIn("full_text", result)

    def test_agent_renders_youtube_analysis_without_llm(self):
        agent = Agent()
        agent.backend = object()
        agent.backend_name = "TestBackend"
        tool_result = {
            "status": "ok",
            "title": "Market setup today",
            "channel": "Sample Market Channel",
            "published_at": "2026-05-17",
            "url": "https://www.youtube.com/watch?v=0Hnffbj5pgE",
            "transcript": {"available": True, "segment_count": 2, "stored_full_text": False},
            "transcription": {"requested": False},
            "market_relevance": "HIGH",
            "market_topic_counts": {"indices": 1, "sectors": 1},
            "market_segments": [{"timestamp": "01:48", "excerpt": "NIFTY is near resistance.", "symbols": []}],
            "market_insights": ["NIFTY needs confirmation near resistance."],
            "suggested_followups": [{"prompt": "Check NIFTY intraday setup", "why": "Validate resistance behavior."}],
            "source_policy": "Transcript-derived summary only; video/audio not downloaded and full transcript not stored.",
        }

        with patch("terminal.agent._execute_plan") as execute_plan:
            execute_plan.return_value = [
                {"tool": "analyze_youtube_video", "args": {"source": "https://www.youtube.com/watch?v=0Hnffbj5pgE"}, "result": tool_result},
                {"tool": "list_youtube_channels", "args": {}, "result": {"channels": []}},
            ]
            result = agent.query("/youtube https://www.youtube.com/watch?v=0Hnffbj5pgE")

        self.assertEqual(result["intent"], "youtube_video_analysis")
        self.assertIn("YOUTUBE MARKET INTELLIGENCE", result["answer"])
        self.assertIn("MARKET INSIGHTS", result["answer"])
        self.assertIn("FOLLOW-UP QUESTIONS", result["answer"])

    def test_members_only_youtube_download_error_is_human_readable(self):
        error = subprocess.CalledProcessError(
            1,
            ["yt-dlp"],
            stderr="ERROR: Join this channel to get access to members-only content like this video",
        )

        with patch("terminal.youtube.subprocess.run", side_effect=error):
            with self.assertRaisesRegex(RuntimeError, "members-only"):
                _run_checked(["yt-dlp"], timeout=1)


if __name__ == "__main__":
    unittest.main()
