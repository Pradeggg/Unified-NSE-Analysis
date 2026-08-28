from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Final

from terminal.ui.disclaimers import render_disclaimer_block_html
from terminal.ui.html_theme import agent_adda_dark_css


ROOT = Path(__file__).resolve().parent.parent

_MAIN_RE: Final = re.compile(r"<main[^>]*>(?P<main>.*?)</main>", re.DOTALL | re.IGNORECASE)
_TITLE_RE: Final = re.compile(r"<title>(?P<title>.*?)</title>", re.DOTALL | re.IGNORECASE)


def _extract_main(html_text: str) -> str:
    m = _MAIN_RE.search(html_text or "")
    if not m:
        raise ValueError("Could not find <main>...</main> in input HTML.")
    return m.group("main").strip()


def _extract_title(html_text: str, fallback: str) -> str:
    m = _TITLE_RE.search(html_text or "")
    if not m:
        return fallback
    title = re.sub(r"\s+", " ", m.group("title") or "").strip()
    return title or fallback


def render_combined_html(*, title: str, left_main: str, right_main: str, subtitle: str) -> str:
    extra_css = """
.split { display:grid; grid-template-columns: 1.3fr 0.7fr; gap:12px; padding:16px; }
.panel { background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:14px; min-width:0; overflow:auto; }
.wide { grid-column:span 2; }
@media (max-width: 900px) { .split { grid-template-columns:1fr; } .wide { grid-column:span 1; } }
"""
    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="en">',
            "<head>",
            '<meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            f"<title>{title}</title>",
            "<style>",
            agent_adda_dark_css(),
            extra_css,
            "</style>",
            "</head>",
            "<body>",
            "<header>",
            f"<h1>{title}</h1>",
            f'<div class="sub">{subtitle}</div>',
            "</header>",
            '<main class="split">',
            f'<section class="panel wide"><h2>Company Story</h2>{left_main}</section>',
            f'<section class="panel wide"><h2>Growth & Ratios Snapshot</h2>{right_main}</section>',
            f'<section class="panel wide"><h2>Disclaimers</h2>{render_disclaimer_block_html()}</section>',
            "</main>",
            "<footer>Not investment advice. For research and learning only.</footer>",
            "</body>",
            "</html>",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Combine two Agent Adda HTML reports into one themed report.")
    p.add_argument("--a", required=True, help="First HTML path (relative to repo root).")
    p.add_argument("--b", required=True, help="Second HTML path (relative to repo root).")
    p.add_argument("--out", required=True, help="Output HTML path (relative to repo root).")
    p.add_argument("--title", default="", help="Override combined report title.")
    p.add_argument("--subtitle", default="Combined view", help="Subtitle line under title.")
    args = p.parse_args(argv)

    a_path = ROOT / args.a
    b_path = ROOT / args.b
    out_path = ROOT / args.out

    a_html = a_path.read_text(encoding="utf-8", errors="ignore")
    b_html = b_path.read_text(encoding="utf-8", errors="ignore")

    title_a = _extract_title(a_html, a_path.name)
    title_b = _extract_title(b_html, b_path.name)
    title = args.title.strip() or f"{title_a} + {title_b}"

    combined = render_combined_html(
        title=title,
        subtitle=args.subtitle,
        left_main=_extract_main(a_html),
        right_main=_extract_main(b_html),
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(combined, encoding="utf-8")
    print(str(out_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

