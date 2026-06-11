import unittest
from unittest.mock import Mock, patch

from terminal.agent import _keyword_intent, _synthesize_no_llm
from terminal.tools import search_market_knowledge


class MarketKnowledgeTests(unittest.TestCase):
    def _mock_get(self, url, params=None, **kwargs):
        response = Mock()
        response.status_code = 200
        response.raise_for_status = Mock()

        if "w/api.php" in url:
            response.json.return_value = {
                "query": {
                    "search": [
                        {
                            "title": "Price-earnings ratio",
                            "snippet": "The price-earnings ratio compares share price with earnings per share.",
                        }
                    ]
                }
            }
            response.text = ""
            return response

        if "/api/rest_v1/page/summary/" in url:
            if "Return%20on%20capital%20employed" in url:
                response.json.return_value = {
                    "title": "Return on capital employed",
                    "extract": "Return on capital employed compares operating profit to capital employed.",
                    "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Return_on_capital_employed"}},
                }
                response.text = ""
                return response
            if "Return%20on%20equity" in url:
                response.json.return_value = {
                    "title": "Return on equity",
                    "extract": "Return on equity measures profitability in relation to shareholders' equity.",
                    "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Return_on_equity"}},
                }
                response.text = ""
                return response
            if "Relative%20strength%20index" in url:
                response.json.return_value = {
                    "title": "Relative strength index",
                    "extract": "The relative strength index is a technical indicator used in financial market analysis.",
                    "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Relative_strength_index"}},
                }
                response.text = ""
                return response
            response.json.return_value = {
                "title": "Price-earnings ratio",
                "extract": "The price-earnings ratio is the ratio of a company's share price to the company's earnings per share.",
                "content_urls": {
                    "desktop": {"page": "https://en.wikipedia.org/wiki/Price%E2%80%93earnings_ratio"}
                },
            }
            response.text = ""
            return response

        if "duckduckgo.com" in url:
            response.text = """
            <html><body>
              <a class="result__a" href="/l/?uddg=https%3A%2F%2Fwww.investopedia.com%2Fterms%2Fp%2Fprice-earningsratio.asp">
                P/E Ratio Definition
              </a>
            </body></html>
            """
            response.json.side_effect = ValueError("not json")
            return response

        if "investopedia.com" in url:
            response.text = """
            <html><body><article>
              <h1>Price-to-Earnings Ratio</h1>
              <p>The price-to-earnings ratio measures a company's share price relative to its earnings per share.</p>
              <p>It is commonly used to assess valuation against peers and growth expectations.</p>
            </article></body></html>
            """
            response.json.side_effect = ValueError("not json")
            return response

        raise AssertionError(f"Unexpected URL: {url}")

    @patch("requests.get")
    def test_market_knowledge_search_uses_wikipedia_and_investopedia_sources(self, mock_get):
        mock_get.side_effect = self._mock_get

        result = search_market_knowledge("what is a PE ratio")

        self.assertEqual(result["query"], "what is a PE ratio")
        self.assertGreaterEqual(result["source_count"], 2)
        self.assertIn("Wikipedia", {src["source"] for src in result["sources"]})
        self.assertIn("Investopedia", {src["source"] for src in result["sources"]})
        self.assertIn("Source-backed market education", result["answer_markdown"])
        self.assertIn("P/E", result["answer_markdown"])
        self.assertIn("https://", result["answer_markdown"])
        wiki_summary_call = next(
            call for call in mock_get.call_args_list if "/api/rest_v1/page/summary/" in call.args[0]
        )
        self.assertIn("Price", wiki_summary_call.args[0])
        self.assertFalse(any("w/api.php" in call.args[0] for call in mock_get.call_args_list))

    @patch("requests.get")
    def test_market_knowledge_comparison_fetches_exact_wikipedia_pages_for_both_terms(self, mock_get):
        mock_get.side_effect = self._mock_get

        result = search_market_knowledge("How is ROCE different from ROE", sources=["wikipedia"])

        titles = {source["title"] for source in result["sources"]}
        self.assertIn("Return on capital employed", titles)
        self.assertIn("Return on equity", titles)
        self.assertFalse(any("w/api.php" in call.args[0] for call in mock_get.call_args_list))

    @patch("requests.get")
    def test_market_knowledge_rsi_uses_relative_strength_index_exact_page(self, mock_get):
        mock_get.side_effect = self._mock_get

        result = search_market_knowledge("What is RSI and how is it used?", sources=["wikipedia"])

        self.assertEqual(result["sources"][0]["title"], "Relative strength index")
        self.assertIn("technical indicator", result["answer_markdown"])
        self.assertFalse(any("w/api.php" in call.args[0] for call in mock_get.call_args_list))

    @patch("requests.get")
    def test_market_knowledge_skips_empty_investopedia_snippet(self, mock_get):
        def _mock_empty_investopedia(url, params=None, **kwargs):
            response = Mock()
            response.status_code = 200
            response.raise_for_status = Mock()
            response.json.side_effect = ValueError("not json")
            if "/api/rest_v1/page/summary/" in url:
                response.json.side_effect = None
                response.json.return_value = {
                    "title": "Return on capital employed",
                    "extract": "Return on capital employed compares operating profit to capital employed.",
                    "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Return_on_capital_employed"}},
                }
                response.text = ""
                return response
            if "duckduckgo.com" in url:
                response.text = """
                <html><body>
                  <a class="result__a" href="/l/?uddg=https%3A%2F%2Fwww.investopedia.com%2Fterms%2Fr%2Froce.asp">
                    ROCE Definition
                  </a>
                </body></html>
                """
                return response
            if "investopedia.com" in url:
                response.text = "<html><body><article>\u200b</article></body></html>"
                return response
            raise AssertionError(f"Unexpected URL: {url}")

        mock_get.side_effect = _mock_empty_investopedia

        result = search_market_knowledge("explain ROCE")

        self.assertEqual({src["source"] for src in result["sources"]}, {"Wikipedia"})
        self.assertNotIn("- Investopedia: \u200b", result["answer_markdown"])
        self.assertNotIn("Investopedia - ROCE Definition", result["answer_markdown"])
        self.assertIn("ROCE = operating profit", result["answer_markdown"])

    def test_keyword_router_detects_market_education_questions(self):
        examples = [
            "what is a PE",
            "explain Minervini's trading strategy",
            "How is ROCE different from ROE",
            "/learn PE ratio",
            "/define ROCE",
            "/compare ROCE ROE",
        ]

        for query in examples:
            with self.subTest(query=query):
                routed = _keyword_intent(query)
                self.assertEqual(routed["intent"], "market_knowledge")
                self.assertEqual(routed["plan"][0][0], "search_market_knowledge")
                self.assertTrue(routed["plan"][0][1]["query"])

    def test_no_llm_synthesis_does_not_invent_when_sources_are_missing(self):
        answer = _synthesize_no_llm(
            "market_knowledge",
            [
                {
                    "tool": "search_market_knowledge",
                    "args": {"query": "obscure concept"},
                    "result": {
                        "query": "obscure concept",
                        "source_count": 0,
                        "sources": [],
                        "answer_markdown": "No reliable Investopedia or Wikipedia source was found for obscure concept.",
                    },
                }
            ],
        )

        self.assertIn("No reliable Investopedia or Wikipedia source was found", answer)


if __name__ == "__main__":
    unittest.main()
