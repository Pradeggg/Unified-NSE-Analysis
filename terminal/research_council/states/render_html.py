"""Render Research Council reports."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from terminal.research_council.reports.html_renderer import write_html_report
from terminal.research_council.reports.markdown_renderer import write_markdown_report
from terminal.research_council.reports.summary import build_report_summary

REPORT_DIR = Path("reports/research_council")


def run(state):
    if state.flags.get("dry_run"):
        return state
    flags = dict(state.flags)
    if "llm_report_summary" not in flags:
        flags["llm_report_summary"] = build_report_summary(state)
    state = replace(state, flags=flags)
    path = write_markdown_report(state, output_dir=REPORT_DIR)
    html_path = write_html_report(state, output_dir=REPORT_DIR)
    flags["markdown_report_path"] = str(path)
    flags["html_report_path"] = str(html_path)
    return replace(state, flags=flags)
