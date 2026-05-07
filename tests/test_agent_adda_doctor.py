import tempfile
import unittest
from pathlib import Path

from agent_adda.config.settings import default_config
from agent_adda.doctor import run_doctor


class AgentAddaDoctorTests(unittest.TestCase):
    def test_doctor_reports_missing_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = default_config(Path(tmp))
            result = run_doctor(cfg)
            names = [check.name for check in result.checks]
            self.assertIn("config", names)
            self.assertIn("historical_database", names)
            self.assertFalse(result.ok)


if __name__ == "__main__":
    unittest.main()
