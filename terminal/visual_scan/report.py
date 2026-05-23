"""Report rendering for visual scan outputs."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from terminal.reports import generate_report

from .models import VisualScanPack


def _table(headers: list[str], rows: list[list[object]]) -> str:
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        out.append("| " + " | ".join(_cell(value) for value in row) + " |")
    return "\n".join(out)


def _cell(value: object) -> str:
    if value is None:
        return ""
    return str(value).replace("\n", " ").replace("|", "\\|")


def _safe_stem(symbol: str, run_id: str) -> str:
    safe_symbol = re.sub(r"[^A-Za-z0-9_-]+", "_", symbol.upper()).strip("_") or "visual_scan"
    safe_run = re.sub(r"[^A-Za-z0-9_-]+", "_", run_id).strip("_")[:8] or "run"
    return f"{safe_symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{safe_run}"


def _source_rows(source_trail: dict[str, Any]) -> list[list[object]]:
    rows: list[list[object]] = []
    for name, item in source_trail.items():
        if isinstance(item, dict):
            rows.append([name, item.get("status", ""), item.get("rows", ""), item.get("latest", "")])
        else:
            rows.append([name, item, "", ""])
    return rows


def render_visual_scan_markdown(pack: VisualScanPack) -> str:
    """Render a balanced visual scan report body as Markdown."""
    verdict = pack.verdict
    lines = [
        f"# {pack.symbol} Visual Scan",
        "",
        "Research and learning only. Not investment advice.",
        "",
        "## Verdict",
        "",
        f"**{verdict.stance}** | Score: **{verdict.score}** | Confidence: **{verdict.confidence.title()}**",
        "",
        verdict.summary,
        "",
        f"- Trigger: {verdict.trigger}",
        f"- Invalidation: {verdict.invalidation}",
    ]
    lines.extend(f"- Target: {target}" for target in verdict.targets)
    if verdict.caveats:
        lines.extend(["", "Caveats:"])
        lines.extend(f"- {item}" for item in verdict.caveats)

    lines.extend(["", "## Annotated Charts", ""])
    if pack.chart_paths:
        lines.extend(f"- {label.title()}: `{path}`" for label, path in pack.chart_paths.items())
    else:
        lines.append("- Chart assets unavailable.")

    lines.extend(["", "## Decision Panel", ""])
    lines.append(
        _table(
            ["Item", "Value"],
            [
                ["Trigger", verdict.trigger],
                ["Invalidation", verdict.invalidation],
                ["Confidence", verdict.confidence],
                ["Score", verdict.score],
            ],
        )
    )

    lines.extend(["", "## Pattern Evidence", ""])
    pattern_rows = [
        [
            pattern.pattern,
            pattern.status,
            pattern.confidence,
            "; ".join(pattern.evidence),
            "; ".join(pattern.caveats),
        ]
        for pattern in pack.patterns
    ]
    lines.append(_table(["Pattern", "Status", "Confidence", "Evidence", "Caveats"], pattern_rows or [["No detector evidence", "", "", "", ""]]))

    lines.extend(["", "## TradingView Corroboration", ""])
    tradingview = pack.tradingview or {}
    lines.append(f"- Status: {tradingview.get('status', 'not_attempted')}")
    if tradingview.get("path"):
        lines.append(f"- Screenshot: `{tradingview.get('path')}`")
    if tradingview.get("message"):
        lines.append(f"- Note: {tradingview.get('message')}")
    if tradingview.get("url"):
        lines.append(f"- URL: `{tradingview.get('url')}`")

    lines.extend(["", "## Source & Audit Trail", ""])
    source_rows = _source_rows(pack.source_trail)
    lines.append(_table(["Source", "Status", "Rows", "Latest"], source_rows or [["No source trail", "", "", ""]]))

    lines.extend(["", "## Missing Evidence", ""])
    if pack.missing_evidence:
        lines.extend(f"- {item}" for item in pack.missing_evidence)
    else:
        lines.append("- none")

    return "\n".join(lines)


def save_visual_scan_outputs(pack: VisualScanPack, output_dir: str | Path = "reports/visual_scan") -> dict[str, Any]:
    """Save the themed HTML report and replayable JSON evidence pack."""
    target = Path(output_dir).expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    stem = _safe_stem(pack.symbol, pack.run_id)
    markdown = render_visual_scan_markdown(pack)

    report_result = generate_report(
        markdown,
        report_type="research",
        symbol=pack.symbol,
        output_format="html",
        title=f"{pack.symbol} Visual Scan",
        filename=str(target / stem),
    )
    html_path = report_result.get("path") or str(target / f"{stem}.html")
    json_path = target / f"{stem}.json"
    json_path.write_text(json.dumps(pack.to_dict(), indent=2, default=str), encoding="utf-8")

    return {
        "success": bool(report_result.get("success")),
        "html_path": str(html_path),
        "json_path": str(json_path),
        "markdown": markdown,
        "report": report_result,
    }


__all__ = ["render_visual_scan_markdown", "save_visual_scan_outputs"]
