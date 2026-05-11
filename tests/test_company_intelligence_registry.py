import json
import unittest
from pathlib import Path


class CompanyIntelligenceRegistryTests(unittest.TestCase):
    def test_source_registry_has_required_tiers_and_document_types(self):
        registry_path = Path("data/company_intelligence/source_registry.json")
        registry = json.loads(registry_path.read_text())

        self.assertEqual(registry["official_exchange"]["tier"], 1)
        self.assertEqual(registry["official_policy"]["tier"], 1)
        self.assertEqual(registry["company_ir"]["tier"], 1)
        self.assertEqual(registry["structured_internal"]["tier"], 2)
        self.assertEqual(registry["external_context"]["tier"], 3)
        self.assertIn("concall_transcript", registry["official_exchange"]["allowed_document_types"])
        self.assertIn("policy_statement", registry["official_policy"]["allowed_document_types"])
        self.assertIn("broker_research_landing_pages", registry["external_context"]["sources"])


if __name__ == "__main__":
    unittest.main()
