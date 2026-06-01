"""Renderer for report_lookup intent."""

from terminal.renderers._base import _get, _source_trail_lines, FOOTER


def render(tool_results: list[dict]) -> str:
    """Render the report_lookup intent."""
    opened_report = _get(tool_results, "open_report")
    report_summary = _get(tool_results, "summarize_report")
    read_report_result = _get(tool_results, "read_report")
    last_report = _get(tool_results, "get_last_report")
    listed_reports = _get(tool_results, "list_generated_reports")
    latest_report = _get(tool_results, "find_latest_report")

    report_payload = (
        opened_report
        or report_summary
        or read_report_result
        or last_report
        or listed_reports
        or latest_report
        or {}
    )
    status = report_payload.get("status") or ("ok" if report_payload else "unknown")

    lines: list[str] = []
    lines.append("▶ REPORT CONTEXT")

    if opened_report:
        lines.append(f"  Status: {status}")
        lines.append(f"  Path:   {opened_report.get('path') or 'N/A'}")
        if opened_report.get("message"):
            lines.append(f"  Note:   {opened_report.get('message')}")
    elif report_summary:
        lines.append(f"  Status:         {status}")
        lines.append(f"  Path:           {report_summary.get('path') or 'N/A'}")
        if report_summary.get("symbol"):
            lines.append(f"  Symbol:         {report_summary.get('symbol')}")
        if report_summary.get("recommendation"):
            lines.append(f"  Recommendation: {report_summary.get('recommendation')}")
        if report_summary.get("summary"):
            lines.append("")
            lines.append("▶ SUMMARY")
            for line in str(report_summary.get("summary")).splitlines()[:12]:
                lines.append(f"  {line}")
    elif read_report_result:
        lines.append(f"  Status: {status}")
        lines.append(f"  Path:   {read_report_result.get('path') or 'N/A'}")
        content = str(read_report_result.get("content") or "").strip()
        if content:
            lines.append("")
            lines.append("▶ PREVIEW")
            for line in content.splitlines()[:12]:
                if line.strip():
                    lines.append(f"  {line[:140]}")
    elif last_report and last_report.get("report"):
        report = last_report.get("report") or {}
        lines.append(f"  Status: {status}")
        lines.append(f"  Path:   {report.get('path') or report.get('absolute_path') or 'N/A'}")
        lines.append(f"  Type:   {report.get('report_type') or 'report'}")
    elif listed_reports:
        reports = listed_reports.get("reports") or []
        lines.append(f"  Status: {status}")
        lines.append(f"  Count:  {listed_reports.get('count', len(reports))}")
        for row in reports[:10]:
            lines.append(f"  - {row.get('name')} | {row.get('report_type')} | {row.get('path')}")
    elif latest_report:
        files = latest_report.get("files") or []
        lines.append(f"  Count: {latest_report.get('count', len(files))}")
        for row in files[:10]:
            lines.append(f"  - {row.get('name')} | {row.get('path')}")
    else:
        lines.append("  No report context was available.")

    lines.append("")
    lines.append("▶ SOURCE TRAIL")
    lines.extend(_source_trail_lines(tool_results))
    lines.append(f"\n{FOOTER}")
    return "\n".join(lines)
