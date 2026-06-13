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


def markdown_table_cell(value: Any) -> str:
    return " ".join(str(value or "").replace("|", "/").split())


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
                title=markdown_table_cell(fact.get("report_title") or ""),
                fact_type=fact.get("fact_type") or "",
                fact_value=markdown_table_cell(fact.get("fact_value") or ""),
                page=fact.get("page_number") or "",
                url=fact.get("pdf_url") or "",
            )
        )
    return "\n".join(lines) + "\n"


def _inline_html(text: str) -> str:
    escaped = html.escape(text)
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)


def _markdown_to_html(markdown: str) -> str:
    body_lines: list[str] = []
    in_table = False
    in_list = False
    in_ordered_list = False

    def close_blocks() -> None:
        nonlocal in_table, in_list, in_ordered_list
        if in_table:
            body_lines.append("</tbody></table>")
            in_table = False
        if in_list:
            body_lines.append("</ul>")
            in_list = False
        if in_ordered_list:
            body_lines.append("</ol>")
            in_ordered_list = False

    for raw in markdown.splitlines():
        line = raw.rstrip()
        if line.startswith("|"):
            if in_list:
                body_lines.append("</ul>")
                in_list = False
            if in_ordered_list:
                body_lines.append("</ol>")
                in_ordered_list = False
            if re.match(r"^\|[-:| ]+\|$", line):
                continue
            cells = [html.escape(cell.strip()) for cell in line.strip("|").split("|")]
            tag = "th" if not in_table else "td"
            if not in_table:
                body_lines.append("<table><tbody>")
                in_table = True
            body_lines.append("<tr>" + "".join(f"<{tag}>{cell}</{tag}>" for cell in cells) + "</tr>")
            continue
        if line.strip() in {"---", "***"}:
            close_blocks()
            body_lines.append("<hr>")
            continue
        if in_table:
            body_lines.append("</tbody></table>")
            in_table = False
        if line.startswith("# "):
            close_blocks()
            body_lines.append(f"<h1>{_inline_html(line[2:])}</h1>")
        elif line.startswith("## "):
            close_blocks()
            body_lines.append(f"<h2>{_inline_html(line[3:])}</h2>")
        elif line.startswith("### "):
            close_blocks()
            body_lines.append(f"<h3>{_inline_html(line[4:])}</h3>")
        elif line.startswith("#### "):
            close_blocks()
            body_lines.append(f"<h4>{_inline_html(line[5:])}</h4>")
        elif line.startswith("- "):
            if in_ordered_list:
                body_lines.append("</ol>")
                in_ordered_list = False
            if not in_list:
                body_lines.append("<ul>")
                in_list = True
            body_lines.append(f"<li>{_inline_html(line[2:])}</li>")
        elif (numbered := re.match(r"^(\d+)\.\s+(.+)", line)):
            if in_list:
                body_lines.append("</ul>")
                in_list = False
            if not in_ordered_list:
                body_lines.append(f"<ol start=\"{html.escape(numbered.group(1))}\">")
                in_ordered_list = True
            body_lines.append(f"<li>{_inline_html(numbered.group(2))}</li>")
        elif line:
            close_blocks()
            body_lines.append(f"<p>{_inline_html(line)}</p>")
        else:
            if in_list:
                body_lines.append("</ul>")
                in_list = False
    close_blocks()
    return "\n".join(body_lines)


def render_broker_research_html(markdown: str) -> str:
    title_match = re.search(r"^#\s+(.+)$", markdown, re.M)
    title = html.escape(title_match.group(1).strip() if title_match else "Broker Research")
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>{title}</title>
  <style>
    :root {{ color-scheme: light; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      margin: 0;
      padding: 32px;
      color: #111827;
      background: #f8fafc;
      line-height: 1.58;
    }}
    body > * {{ max-width: 1120px; margin-left: auto; margin-right: auto; }}
    h1, h2, h3, h4 {{ color: #0f172a; line-height: 1.2; letter-spacing: 0; }}
    h1 {{ font-size: 34px; margin: 0 auto 18px; }}
    h2 {{ font-size: 24px; margin-top: 32px; border-top: 1px solid #dbe3ef; padding-top: 20px; }}
    h3 {{ font-size: 19px; margin-top: 24px; }}
    h4 {{ font-size: 16px; margin-top: 20px; }}
    hr {{ border: 0; border-top: 1px solid #dbe3ef; margin: 28px auto; }}
    p, li {{ font-size: 15px; }}
    ul {{ padding-left: 22px; }}
    .numbered {{ margin-left: 0; }}
    table {{
      border-collapse: collapse;
      width: 100%;
      margin: 18px auto;
      background: #ffffff;
      table-layout: fixed;
    }}
    th, td {{
      border: 1px solid #d1d5db;
      padding: 9px 10px;
      text-align: left;
      vertical-align: top;
      overflow-wrap: anywhere;
      font-size: 13px;
      line-height: 1.45;
    }}
    th {{ background: #eef2f7; color: #0f172a; }}
    strong {{ font-weight: 700; }}
    @media (max-width: 700px) {{
      body {{ padding: 18px; }}
      h1 {{ font-size: 26px; }}
      h2 {{ font-size: 20px; }}
      table {{ display: block; overflow-x: auto; table-layout: auto; }}
      th, td {{ min-width: 120px; }}
    }}
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
