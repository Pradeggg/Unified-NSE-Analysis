import sys
import unittest
from io import StringIO
from pathlib import Path

from rich.console import Console

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import nse_agent


class NseAgentLinkRenderingTests(unittest.TestCase):
    def test_html_anchor_is_converted_to_visible_url_text(self):
        text = 'Read <a href="https://example.com/report.html">the report</a> today.'

        linked = nse_agent._linkify_markdown(text)

        self.assertIn("the report (https://example.com/report.html)", linked)
        self.assertNotIn("<a href", linked)

    def test_plain_text_renderer_keeps_bare_url_visible(self):
        console = Console(force_terminal=True, record=True, highlight=False, file=StringIO())

        console.print(nse_agent._text_with_links("URL: https://example.com/report.html"), style="white")
        rendered = console.export_text(styles=False)

        self.assertIn("https://example.com/report.html", rendered)

    def test_plain_text_renderer_expands_html_anchor_to_visible_url(self):
        console = Console(force_terminal=True, record=True, highlight=False, file=StringIO())

        console.print(nse_agent._text_with_links('Open <a href="https://example.com">Example</a>'), style="white")
        rendered = console.export_text(styles=False)

        self.assertIn("Example", rendered)
        self.assertIn("https://example.com", rendered)

    def test_markdown_linkifier_does_not_hide_bare_url_behind_osc8(self):
        linked = nse_agent._linkify_markdown("See https://example.com/raw")

        self.assertEqual(linked, "See https://example.com/raw")
        self.assertNotIn("[https://example.com/raw](https://example.com/raw)", linked)


if __name__ == "__main__":
    unittest.main()
