"""Renderer for market context plus EOD swing candidate scans."""
from __future__ import annotations


def _results(tool_results: list[dict], tool_name: str) -> list[dict]:
    return [
        trace.get("result") or {}
        for trace in tool_results or []
        if trace.get("tool") == tool_name and isinstance(trace.get("result"), dict)
    ]


def _one(tool_results: list[dict], tool_name: str) -> dict:
    rows = _results(tool_results, tool_name)
    return rows[0] if rows else {}


def _fmt_pct(value) -> str:
    return f"{float(value):+.2f}%" if isinstance(value, (int, float)) else "n/a"


def render(tool_results: list[dict]) -> str:
    lines: list[str] = ["MARKET + SWING CANDIDATES"]

    index_rows = [row for row in _results(tool_results, "get_index_snapshot") if not row.get("error")]
    if index_rows:
        lines.append("")
        lines.append("Market Context")
        lines.append("| Index | As of | Close | 1D | 10D |")
        lines.append("|---|---:|---:|---:|---:|")
        for row in index_rows:
            trend = row.get("trend_10d") or {}
            close = row.get("close")
            close_txt = f"{float(close):,.2f}" if isinstance(close, (int, float)) else "n/a"
            lines.append(
                f"| {row.get('index', '—')} | {row.get('as_of', '—')} | "
                f"{close_txt} | {_fmt_pct(row.get('chg_pct'))} | {_fmt_pct(trend.get('chg_pct'))} |"
            )

    breadth = _one(tool_results, "get_market_breadth")
    if breadth:
        lines.append("")
        lines.append("Breadth")
        if breadth.get("error"):
            lines.append(f"- Error: {breadth.get('error')}")
        else:
            stage_dist = breadth.get("stage_distribution") or {}
            lines.append(
                f"- Snapshot: {breadth.get('snapshot_date', 'unknown')} | "
                f"Advances: {breadth.get('advances', '—')} | "
                f"Declines: {breadth.get('declines', '—')} | "
                f"A/D: {breadth.get('ad_ratio', '—')} | "
                f"Avg RS: {_fmt_pct(breadth.get('avg_rs_pct'))} | "
                f"Stage 2: {stage_dist.get('STAGE_2', stage_dist.get('stage_2', '—'))}"
            )

    from . import quality_breakouts

    lines.append("")
    lines.append(quality_breakouts.render(tool_results))
    return "\n".join(lines)
