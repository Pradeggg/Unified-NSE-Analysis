import json
import unittest

from company_website_adapters import DmartInvestorAdapter, get_company_site_adapter


class CompanyWebsiteAdaptersTests(unittest.TestCase):
    def test_get_company_site_adapter_returns_dmart_adapter_for_symbol_or_domain(self):
        self.assertIsInstance(get_company_site_adapter("DMART", ""), DmartInvestorAdapter)
        self.assertIsInstance(get_company_site_adapter("OTHER", "https://www.dmartindia.com"), DmartInvestorAdapter)
        self.assertIsNone(get_company_site_adapter("OTHER", "https://www.example.com"))

    def test_dmart_adapter_extracts_official_investor_documents_from_api_json(self):
        payload = [
            {
                "contentId": "2",
                "placeholder": "InvestorRelations_Details",
                "content": {
                    "investorCategoryName": "Investor Updates",
                    "subMenus": [
                        {
                            "name": "2026-2027",
                            "subCategories": [
                                {
                                    "name": "2026-2027",
                                    "files": [
                                        {
                                            "fileId": "uGXCA17YYrPHtr7KDQfC7cWD1777724005",
                                            "fileName": "Investor Presentation for the year ended 31st March, 2026",
                                            "fileType": "application/pdf",
                                            "isPublished": True,
                                        },
                                        {
                                            "fileId": "R2aWBiIpiuD39xgfm4wrqQKc1777723315",
                                            "fileName": "Press release dated 2nd May, 2026",
                                            "fileType": "application/pdf",
                                            "isPublished": True,
                                        },
                                        {
                                            "fileId": "hidden",
                                            "fileName": "Unpublished document",
                                            "fileType": "application/pdf",
                                            "isPublished": False,
                                        },
                                    ],
                                }
                            ],
                        }
                    ],
                },
            }
        ]

        def fetcher(url):
            self.assertIn("contentPlaceholder=InvestorRelations_Details", url)
            return {
                "url": url,
                "status": "ok",
                "status_code": 200,
                "content_type": "application/json",
                "text": json.dumps(payload),
            }

        docs = DmartInvestorAdapter().discover_documents(fetcher=fetcher, limit=10)

        self.assertEqual(len(docs), 2)
        self.assertEqual(docs[0]["title"], "Investor Presentation for the year ended 31st March, 2026")
        self.assertEqual(docs[0]["document_type"], "investor_presentation")
        self.assertEqual(docs[0]["category"], "Investor Updates")
        self.assertEqual(docs[0]["period"], "2026-2027")
        self.assertIn("/corporate/content/file/v1/2/uGXCA17YYrPHtr7KDQfC7cWD1777724005/", docs[0]["url"])
        self.assertIn("Investor%20Presentation%20for%20the%20year%20ended", docs[0]["url"])
        self.assertEqual(docs[1]["document_type"], "press_release")


if __name__ == "__main__":
    unittest.main()
