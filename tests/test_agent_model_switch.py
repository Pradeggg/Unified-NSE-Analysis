import unittest
from unittest.mock import patch

import nse_agent
import terminal.agent as agent_mod


class FakeOpenAIBackend:
    def __init__(self, model=None, api_key=None):
        self.model = model or "gpt-4o"


class FakeOllamaBackend:
    def __init__(self, model=None, host=None):
        self.model = model or "granite4:latest"
        self.host = host or "http://localhost:11434"


class AgentModelSwitchTests(unittest.TestCase):
    def _agent(self):
        agent = agent_mod.Agent.__new__(agent_mod.Agent)
        agent.backend = None
        agent.backend_name = "Keyword (no LLM)"
        agent.tool_schemas = []
        agent._history = []
        return agent

    def test_switches_main_backend_to_gpt_4o(self):
        agent = self._agent()
        with patch.object(agent_mod, "_OpenAIBackend", FakeOpenAIBackend):
            result = agent.set_model_backend("gpt-4o")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["provider"], "openai")
        self.assertEqual(result["model"], "gpt-4o")
        self.assertEqual(agent.backend_name, "OpenAI (gpt-4o)")

    def test_accepts_user_typo_got_40_for_gpt_4o(self):
        agent = self._agent()
        with patch.object(agent_mod, "_OpenAIBackend", FakeOpenAIBackend):
            result = agent.set_model_backend("got-40")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["provider"], "openai")
        self.assertEqual(result["model"], "gpt-4o")

    def test_switches_main_backend_to_named_ollama_model(self):
        agent = self._agent()
        with patch.object(agent_mod, "_OllamaBackend", FakeOllamaBackend):
            result = agent.set_model_backend("ollama", "granite4:latest")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["provider"], "ollama")
        self.assertEqual(result["model"], "granite4:latest")
        self.assertEqual(agent.backend_name, "Ollama (granite4:latest)")

    def test_can_switch_to_keyword_routing(self):
        agent = self._agent()
        result = agent.set_model_backend("keyword")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["provider"], "keyword")
        self.assertIsNone(result["model"])
        self.assertEqual(agent.backend_name, "Keyword (no LLM)")

    def test_nse_agent_model_command_status(self):
        agent = self._agent()
        result = nse_agent._handle_model_command(agent, "/model")

        self.assertTrue(result["handled"])
        self.assertEqual(result["action"], "status")
        self.assertEqual(result["provider"], "keyword")

    def test_nse_agent_model_command_switch(self):
        agent = self._agent()
        with patch.object(agent_mod, "_OllamaBackend", FakeOllamaBackend):
            result = nse_agent._handle_model_command(agent, "/model ollama qwen3:latest")

        self.assertTrue(result["handled"])
        self.assertEqual(result["action"], "switch")
        self.assertEqual(result["provider"], "ollama")
        self.assertEqual(result["model"], "qwen3:latest")


if __name__ == "__main__":
    unittest.main()
