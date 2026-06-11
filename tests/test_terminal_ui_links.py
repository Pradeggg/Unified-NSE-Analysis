from terminal.ui.links import linkify_markdown, text_with_links


def test_linkify_markdown_wraps_bare_urls_and_preserves_existing_links():
    text = "Read https://example.com/report and [keep](https://example.com/keep)."

    result = linkify_markdown(text)

    assert "<https://example.com/report>" in result
    assert "[keep](https://example.com/keep)" in result


def test_linkify_markdown_does_not_rewrite_code_blocks():
    text = "Use `https://example.com/code`.\n\n```\nhttps://example.com/fenced\n```"

    result = linkify_markdown(text)

    assert "`https://example.com/code`" in result
    assert "```\nhttps://example.com/fenced\n```" in result


def test_text_with_links_keeps_label_and_visible_url():
    result = text_with_links("Read [Docs](https://example.com/docs)")

    assert "Docs https://example.com/docs" in result.plain

