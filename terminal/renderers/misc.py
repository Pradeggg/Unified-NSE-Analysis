"""Miscellaneous renderer functions for simple intents."""

from terminal.renderers._base import _get, _source_trail_lines, FOOTER


def render_visual_scan(tool_results: list[dict]) -> str:
    """Render the visual_scan intent."""
    visual_scan = _get(tool_results, "run_visual_scan") or {}
    lines: list[str] = []
    lines.append(f"━━━ {visual_scan.get('symbol', '—')} — Visual Scan ━━━")
    lines.append(visual_scan.get("summary", "Visual scan completed."))
    if visual_scan.get("html_path"):
        lines.append(f"Report: {visual_scan.get('html_path')}")
    if visual_scan.get("json_path"):
        lines.append(f"Evidence: {visual_scan.get('json_path')}")
    lines.append("\n▶ SOURCE TRAIL")
    lines.extend(_source_trail_lines(tool_results))
    lines.append(FOOTER)
    return "\n".join(line for line in lines if str(line).strip())


def render_greeting() -> str:
    """Render the greeting intent."""
    lines: list[str] = []
    lines.append("Hello — Agent Adda is ready.")
    lines.append(
        "Try `/live` for current market status, `/global` for global cues, "
        "`/heat` for breadth/sector heat, or ask about a specific NSE symbol."
    )
    lines.append(f"\n{FOOTER}")
    return "\n".join(lines)


def render_placeholder_symbol_request(tool_results: list[dict]) -> str:
    """Render the placeholder_symbol_request intent."""
    lines: list[str] = []
    lines.append("▶ NEED A REAL NSE SYMBOL")
    lines.append("  Replace the placeholder with an actual NSE symbol or company name.")
    lines.append("")
    lines.append("▶ EXAMPLES")
    lines.append("  /assess RELIANCE")
    lines.append("  /assess TCS")
    lines.append("  RELIANCE technical setup")
    lines.append("")
    lines.append("▶ WHY")
    lines.append(
        "  `SYMBOL`, `TICKER`, and similar placeholders are templates, not tradable NSE symbols. "
        "No market, technical, sector, or catalyst conclusion was inferred from placeholder input."
    )
    lines.append(f"\n{FOOTER}")
    return "\n".join(lines)


def render_document_link_help(tool_results: list[dict]) -> str:
    """Render the document_link_help intent."""
    lines: list[str] = []
    lines.append("▶ DOCUMENT LINK FOLLOW-UP")
    lines.append("  This looks like a document/PDF follow-up, not a stock-symbol query.")
    lines.append("")
    lines.append("▶ WHAT TO DO")
    lines.append(
        "  Re-run `/analyze <URL>` with the document URL. "
        "Wrapped/pasted URLs are normalized before PDF extraction."
    )
    lines.append(
        "  If the URL still fails, paste the source page URL or use a company/results search prompt "
        "with the company name and period."
    )
    lines.append("")
    lines.append("▶ EXAMPLES")
    lines.append("  /analyze https://www.diageoindia.com/pdf-viewer.aspx?...src=...pdf")
    lines.append("  find United Spirits FY26 audited results PDF")
    lines.append("")
    lines.append("▶ SOURCE TRAIL")
    lines.append("  No equity symbol was resolved; no market conclusion was inferred.")
    lines.append(f"\n{FOOTER}")
    return "\n".join(lines)
