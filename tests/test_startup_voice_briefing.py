import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import nse_agent


class StartupVoiceBriefingTests(unittest.TestCase):
    def test_startup_briefing_does_not_auto_run_voice_panel(self):
        agent = Mock()
        args = SimpleNamespace(no_briefing=False, trace=False)

        with patch.object(nse_agent, "_run_startup_briefing") as startup, patch.object(
            nse_agent, "_run_voice_briefing_panel"
        ) as voice:
            nse_agent._run_optional_startup_briefing(agent, args)

        startup.assert_called_once_with(agent, False)
        voice.assert_not_called()

    def test_no_briefing_skips_startup_briefing(self):
        agent = Mock()
        args = SimpleNamespace(no_briefing=True, trace=False)

        with patch.object(nse_agent, "_run_startup_briefing") as startup, patch.object(
            nse_agent, "_run_voice_briefing_panel"
        ) as voice:
            nse_agent._run_optional_startup_briefing(agent, args)

        startup.assert_not_called()
        voice.assert_not_called()


if __name__ == "__main__":
    unittest.main()
