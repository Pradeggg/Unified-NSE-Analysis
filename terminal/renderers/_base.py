"""Shared utilities for all renderer modules."""
from __future__ import annotations

FOOTER = "\n━━━ Not investment advice. For research and learning only. ━━━"


def _get(tool_results: list[dict], name: str) -> dict | None:
    """Return the result dict of the first tool_result matching *name*, or None."""
    for tr in tool_results or []:
        if tr.get("tool") == name:
            result = tr.get("result")
            return result if isinstance(result, dict) else None
    return None


def _source_trail_lines(tool_results: list[dict]) -> list[str]:
    lines: list[str] = []
    for tr in tool_results or []:
        result = tr.get("result") if isinstance(tr.get("result"), dict) else {}
        err = result.get("error")
        status = f"ERROR: {err}" if err else "ok"
        lines.append(f"  {tr.get('tool')}: {status}")
        if err and tr.get("tool") == "resolve_symbol":
            candidates = result.get("candidates") or []
            if candidates:
                lines.append(f"    Suggestions: {', '.join(str(c) for c in candidates[:5])}")
    return lines


def trail_and_footer(tool_results: list[dict]) -> str:
    """Return the standard source-trail + footer block as a string."""
    lines = ["\n▶ SOURCE TRAIL"]
    lines.extend(_source_trail_lines(tool_results))
    lines.append(FOOTER)
    return "\n".join(lines)
