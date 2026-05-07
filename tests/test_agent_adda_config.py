import tempfile
import unittest
from pathlib import Path

from agent_adda.config.settings import AppConfig, default_config, load_config, save_config


class AgentAddaConfigTests(unittest.TestCase):
    def test_default_config_uses_agent_adda_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = default_config(Path(tmp))
            self.assertEqual(cfg.home_dir, Path(tmp))
            self.assertEqual(cfg.data_dir, Path(tmp) / "data")
            self.assertEqual(cfg.reports_dir, Path(tmp) / "reports")
            self.assertEqual(cfg.database_path, Path(tmp) / "data" / "market_data.sqlite")
            self.assertEqual(cfg.model_mode, "rules")
            self.assertFalse(cfg.disclaimer_acknowledged)

    def test_save_and_load_config_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.toml"
            cfg = AppConfig(
                home_dir=Path(tmp),
                data_dir=Path(tmp) / "data",
                reports_dir=Path(tmp) / "reports",
                database_path=Path(tmp) / "data" / "market_data.sqlite",
                model_mode="hybrid",
                openai_api_key_env="OPENAI_API_KEY",
                ollama_model="llama3.1",
                disclaimer_acknowledged=True,
            )
            save_config(cfg, path)
            loaded = load_config(path)
            self.assertEqual(loaded.model_mode, "hybrid")
            self.assertEqual(loaded.ollama_model, "llama3.1")
            self.assertTrue(loaded.disclaimer_acknowledged)


if __name__ == "__main__":
    unittest.main()
