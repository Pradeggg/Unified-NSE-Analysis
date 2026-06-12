"""Broker research report rendering."""

from __future__ import annotations

import html
import re
from datetime import datetime
from pathlib import Path
from typing import Any


DISCLAIMER = "Not investment advice. For research and learning only."


def _line_items(items: list[dict[str, Any]], empty: str) -> list[str]:
    if not items:
        return [f"- {empty}"]
    return [f"- {item['value']} ({item['count']} broker mentions)" for item in items]


def render_broker_research_markdown(*, symbol: str, consensus: dict[str, Any], facts: list[dict[str, Any]]) -> str:
    target = consensus.get("target_price") or {}
    lines = [
        f"# Broker Research: {symbol.strip().upper()}",
        "",
        f"━━━ {DISCLAIMER} ━━━",
        "",
        "## Executive Summary",
        "",
        f"- Broker reports covered: {consensus.get('broker_count', 0)}",
        f"- Disagreements: {', '.join(consensus.get('disagreements') or []) or 'None detected from extracted facts'}",
        "",
        "## Broker Coverage Map",
        "",
        "| Broker |",
        "|---|",
    ]
    for broker in consensus.get("brokers") or []:
        lines.append(f"| {broker} |")
    if not consensus.get("brokers"):
        lines.append("| No broker facts available |")
    lines.extend(
        [
            "",
            "## Rating And Target-Price Consensus",
            "",
            f"- Ratings: {consensus.get('ratings') or {}}",
            f"- Target price min: {target.get('min')}",
            f"- Target price max: {target.get('max')}",
            f"- Target price average: {target.get('average')}",
            f"- Target price spread: {target.get('spread')}",
            "",
            "## Recurring Catalysts",
            "",
            *_line_items(consensus.get("recurring_catalysts") or [], "No repeated catalysts extracted yet."),
            "",
            "## Recurring Risks",
            "",
            *_line_items(consensus.get("recurring_risks") or [], "No repeated risks extracted yet."),
            "",
            "## Missing Evidence",
            "",
            "- Earnings estimate comparison remains unavailable until forecast-table extraction is implemented.",
            "- Agent Adda technical/fundamental cross-check remains a follow-up integration.",
            "- Claims without broker fact/page evidence are intentionally omitted.",
            "",
            "## Source Appendix",
            "",
            "| Broker | Report | Fact | Page | URL |",
            "|---|---|---|---:|---|",
        ]
    )
    if not facts:
        lines.append("| - | - | - | - | - |")
    for fact in facts:
        lines.append(
            "| {broker} | {title} | {fact_type}: {fact_value} | {page} | {url} |".format(
                broker=fact.get("broker_code") or "",
                title=fact.get("report_title") or "",
                fact_type=fact.get("fact_type") or "",
                fact_value=fact.get("fact_value") or "",
                page=fact.get("page_number") or "",
                url=fact.get("pdf_url") or "",
            )
        )
    return "\n".join(lines) + "\n"


def _markdown_to_html(markdown: str) -> str:
    body_lines: list[str] = []
    in_table = False
    for raw in markdown.splitlines():
        line = raw.rstrip()
        if line.startswith("|"):
            if re.match(r"^\|[-:| ]+\|$", line):
                continue
            cells = [html.escape(cell.strip()) for cell in line.strip("|").split("|")]
            tag = "th" if not in_table else "td"
            if not in_table:
                body_lines.append("<table><tbody>")
                in_table = True
            body_lines.append("<tr>" + "".join(f"<{tag}>{cell}</{tag}>" for cell in cells) + "</tr>")
            continue
        if in_table:
            body_lines.append("</tbody></table>")
            in_table = False
        if line.startswith("# "):
            body_lines.append(f"<h1>{html.escape(line[2:])}</h1>")
        elif line.startswith("## "):
            body_lines.append(f"<h2>{html.escape(line[3:])}</h2>")
        elif line.startswith("- "):
            body_lines.append(f"<p>{html.escape(line)}</p>")
        elif line:
            body_lines.append(f"<p>{html.escape(line)}</p>")
    if in_table:
        body_lines.append("</tbody></table>")
    return "\n".join(body_lines)


def render_broker_research_html(markdown: str) -> str:
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Broker Research</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif; margin: 32px; color: #111827; }}
    h1, h2 {{ color: #0f172a; }}
    table {{ border-collapse: collapse; width: 100%; margin: 16px 0; }}
    th, td {{ border: 1px solid #d1d5db; padding: 8px; text-align: left; vertical-align: top; }}
    th {{ background: #f3f4f6; }}
  </style>
</head>
<body>
{_markdown_to_html(markdown)}
</body>
</html>
"""


def write_broker_research_report(
    *,
    symbol: str,
    markdown: str,
    output_dir: Path | str = Path("reports/broker_research"),
    latest_dir: Path | str = Path("reports/latest"),
) -> dict[str, str]:
    clean_symbol = symbol.strip().upper()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = Path(output_dir)
    latest = Path(latest_dir)
    out.mkdir(parents=True, exist_ok=True)
    latest.mkdir(parents=True, exist_ok=True)
    markdown_path = out / f"{clean_symbol.lower()}_{stamp}.md"
    html_path = out / f"{clean_symbol.lower()}_{stamp}.html"
    latest_markdown_path = latest / f"broker_research_{clean_symbol.lower()}.md"
    latest_html_path = latest / f"broker_research_{clean_symbol.lower()}.html"
    html_text = render_broker_research_html(markdown)
    markdown_path.write_text(markdown, encoding="utf-8")
    html_path.write_text(html_text, encoding="utf-8")
    latest_markdown_path.write_text(markdown, encoding="utf-8")
    latest_html_path.write_text(html_text, encoding="utf-8")
    return {
        "markdown_path": str(markdown_path),
        "html_path": str(html_path),
        "latest_markdown_path": str(latest_markdown_path),
        "latest_html_path": str(latest_html_path),
    }
