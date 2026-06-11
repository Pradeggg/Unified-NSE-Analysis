"""Markdown and Rich link helpers for terminal output."""

from __future__ import annotations

import html
import os
import re
from urllib.parse import quote

from rich.style import Style as RichStyle
from rich.text import Text

_URL_RE = re.compile(r'(https?://[^\s\)\]>,"\']+)')
_HTML_LINK_RE = re.compile(
    r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
_MD_LINK_RE = re.compile(r'\[([^\]]+)\]\(((?:https?|file)://[^\s\)]+)\)')
# Used by text_with_links: HTTP only. The local-paths-as-file-links pathway
# would produce noisy "[label](file://...)" labels in plain-text views.
_MD_HTTP_LINK_RE = re.compile(r'\[([^\]]+)\]\((https?://[^\s\)]+)\)')

_BARE_URL_LINKIFY_RE = re.compile(
    r"""(?<![\(<\[\"'`/=])
        (https?://
            (?:
                [^\s<>\)\]\"'`(]+
                |   \([^\s<>\)\]\"'`]*\)
            )+
        )
        (?<![,.;:!?])
    """,
    flags=re.IGNORECASE | re.VERBOSE,
)
_BACKTICK_PATH_RE = re.compile(
    r"`(/[^`\n]+|[A-Za-z]:\\[^`\n]+|~[^`\n]*|\./[^`\n]+|\.\./[^`\n]+|[A-Za-z0-9_.\-]+/[^`\n]+)`"
)
_BARE_LOCAL_PATH_RE = re.compile(
    r"(?<![\w/.])(/[A-Za-z0-9_.\-][A-Za-z0-9_./\-]*\.(?:md|html|htm|pdf|json|csv|txt|log|yaml|yml|toml|ini|sh|py))(?![\w/])"
)


def _strip_html_tags(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text)


def _html_links_to_visible_urls(text: str) -> str:
    def _replace(match: re.Match) -> str:
        url = html.unescape(match.group(1).strip())
        label = html.unescape(_strip_html_tags(match.group(2))).strip() or url
        if label == url:
            return f"<{url}>"
        return f"[{label}]({url})"

    return _HTML_LINK_RE.sub(_replace, text)


def _wrap_bare_urls(segment: str) -> str:
    return _BARE_URL_LINKIFY_RE.sub(lambda m: f"<{m.group(1)}>", segment)


def _path_to_file_uri(path: str) -> str:
    try:
        raw = path
        if raw.startswith("~"):
            raw = os.path.expanduser(raw)
        if not os.path.isabs(raw):
            raw = os.path.abspath(raw)
        return "file://" + quote(raw, safe="/")
    except Exception:
        return path


def _backtick_path_wrap(m: re.Match) -> str:
    path = m.group(1)
    uri = _path_to_file_uri(path)
    if uri == path:
        return m.group(0)
    return f"[`{path}`]({uri})"


def _wrap_backticked_paths_outside_code(text: str) -> str:
    fence_re = re.compile(r"```.*?```", flags=re.DOTALL)

    def _wrap_in_segment(seg: str) -> str:
        out: list[str] = []
        last = 0
        for lm in _MD_LINK_RE.finditer(seg):
            out.append(_BACKTICK_PATH_RE.sub(_backtick_path_wrap, seg[last:lm.start()]))
            out.append(lm.group(0))
            last = lm.end()
        out.append(_BACKTICK_PATH_RE.sub(_backtick_path_wrap, seg[last:]))
        return "".join(out)

    out: list[str] = []
    cursor = 0
    for m in fence_re.finditer(text):
        out.append(_wrap_in_segment(text[cursor:m.start()]))
        out.append(m.group(0))
        cursor = m.end()
    out.append(_wrap_in_segment(text[cursor:]))
    return "".join(out)


def _wrap_local_paths(segment: str) -> str:
    def _wrap_bare(m: re.Match) -> str:
        path = m.group(1)
        uri = _path_to_file_uri(path)
        if uri == path:
            return m.group(0)
        return f"[{path}]({uri})"

    segment = _BACKTICK_PATH_RE.sub(_backtick_path_wrap, segment)
    segment = _BARE_LOCAL_PATH_RE.sub(_wrap_bare, segment)
    return segment


def _protect_existing_md_links(segment: str) -> str:
    out: list[str] = []
    last = 0
    for m in _MD_LINK_RE.finditer(segment):
        between = segment[last:m.start()]
        between = _wrap_local_paths(_wrap_bare_urls(between))
        out.append(between)
        out.append(m.group(0))
        last = m.end()
    tail = _wrap_local_paths(_wrap_bare_urls(segment[last:]))
    out.append(tail)
    return "".join(out)


def linkify_markdown(text: str) -> str:
    """Make URLs and local paths clickable when text is rendered as Markdown."""
    if not text:
        return text
    text = _html_links_to_visible_urls(text)
    text = _wrap_backticked_paths_outside_code(text)
    code_re = re.compile(r"```.*?```|`[^`\n]+`", flags=re.DOTALL)
    parts: list[str] = []
    cursor = 0
    for m in code_re.finditer(text):
        parts.append(_linkify_non_code_segment(text[cursor:m.start()]))
        parts.append(m.group(0))
        cursor = m.end()
    parts.append(_linkify_non_code_segment(text[cursor:]))
    return "".join(parts)


def _linkify_non_code_segment(segment: str) -> str:
    if not segment:
        return segment
    out_lines: list[str] = []
    for line in segment.splitlines(keepends=True):
        stripped = line.lstrip("\n\r")
        leading = line[: len(line) - len(stripped)]
        body = stripped
        if re.match(r"(?: {4,}|\t)", body):
            out_lines.append(line)
            continue
        out_lines.append(leading + _protect_existing_md_links(body))
    return "".join(out_lines)


def _append_bare_url_links(target: Text, text: str) -> None:
    pos = 0
    for match in _URL_RE.finditer(text):
        if match.start() > pos:
            target.append(text[pos:match.start()])
        raw = match.group(1)
        url = raw.rstrip(".,;)")
        trailing = raw[len(url):]
        target.append(url, style=RichStyle(link=url, color="cyan"))
        if trailing:
            target.append(trailing)
        pos = match.end()
    if pos < len(text):
        target.append(text[pos:])


def text_with_links(text: str) -> Text:
    """Create Rich Text with visible labels and raw URLs for terminal compatibility."""
    text = _MD_HTTP_LINK_RE.sub(r'<a href="\2">\1</a>', text)

    out = Text()
    pos = 0
    for match in _HTML_LINK_RE.finditer(text):
        if match.start() > pos:
            _append_bare_url_links(out, text[pos:match.start()])
        url = html.unescape(match.group(1).strip())
        label = html.unescape(_strip_html_tags(match.group(2))).strip() or url
        out.append(label, style=RichStyle(link=url, color="cyan", underline=True))
        if label != url:
            out.append(f" {url}", style=RichStyle(color="cyan", dim=True))
        pos = match.end()
    if pos < len(text):
        _append_bare_url_links(out, text[pos:])
    return out


__all__ = ["linkify_markdown", "text_with_links"]

