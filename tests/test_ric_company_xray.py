import unittest

import nse_agent


class RicCompanyXrayTests(unittest.TestCase):
    def test_company_xray_ric_recipe_exists(self):
        recipe = nse_agent.RIC_LIBRARY["company-xray"]

        self.assertEqual(recipe["arg"], "symbol")
        self.assertEqual(recipe["example"], "/ric company-xray DMART")
        self.assertGreaterEqual(len(recipe["steps"]), 8)
        labels = [step["label"] for step in recipe["steps"]]
        self.assertEqual(labels[0], "Resolve Identity")
        self.assertIn("Final Report", labels)
        self.assertTrue(any("/company-index {symbol}" in step["prompt"] for step in recipe["steps"]))
        self.assertTrue(any("/company-xray {symbol}" in step["prompt"] for step in recipe["steps"]))


if __name__ == "__main__":
    unittest.main()
