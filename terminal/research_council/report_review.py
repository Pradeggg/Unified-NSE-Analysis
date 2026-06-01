"""Evidence builder for Research Council report-review mode."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any

from terminal.research_council.schemas import EvidencePack, MissingEvidence, SourceTrailEntry


REQUIRED_TOOL_FAILURE = "REQUIRED TOOL VALIDATION FAILED"


def build_report_review_evidence_pack(
    *,
    report_path: str,
    as_of: date | None = None,
) -> EvidencePack:
    """Build a report-review evidence pack from a generated report file."""
    path = Path(report_path).expanduser()
    content = path.read_text(encoding="utf-8", errors="replace")
    lines = content.splitlines()
    findings = _find_report_failures(lines)
    missing_tools = _missing_required_tools(lines)
    status = "blocked" if any(item["severity"] == "block" for item in findings) else "usable"
    symbol = _infer_symbol(path)
    missing = _missing_evidence(path=path, findings=findings, missing_tools=missing_tools)
    pack_id = f"report_review_{path.stem}"
    return EvidencePack(
        pack_id=pack_id,
        as_of=as_of or date.today(),
        mode="report_review",
        universe_filter="report",
        symbols=[symbol] if symbol else [],
        sections={
            "report_review": {
                "path": str(path),
                "status": status,
                "line_count": len(lines),
                "findings": findings,
                "missing_required_tools": missing_tools,
                "remediation": _remediation(findings),
            }
        },
        source_trail=[
            SourceTrailEntry(
                source=str(path),
                rows=len(lines),
                freshness="file_snapshot",
                metadata={
                    "suffix": path.suffix.lower(),
                    "required_tool_failure": bool(missing_tools),
                },
            )
        ],
        missing_evidence=missing,
    )


def _find_report_failures(lines: list[str]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for idx, line in enumerate(lines, start=1):
        if REQUIRED_TOOL_FAILURE in line:
            findings.append(
                {
                    "line": idx,
                    "severity": "block",
                    "code": "required_tool_validation_failed",
                    "message": REQUIRED_TOOL_FAILURE,
                    "remediation": "Rerun with mandatory evidence plan before rendering a market conclusion.",
                }
            )
    missing_line = _missing_tools_line(lines)
    if missing_line:
        findings.append(
            {
                "line": missing_line[0],
                "severity": "block",
                "code": "missing_required_tools",
                "message": missing_line[1].strip(),
                "missing_tools": _parse_tools_from_line(missing_line[1]),
                "remediation": "Execute missing tools and regenerate the report before drawing conclusions.",
            }
        )
    return findings


def _missing_required_tools(lines: list[str]) -> list[str]:
    missing_line = _missing_tools_line(lines)
    return _parse_tools_from_line(missing_line[1]) if missing_line else []


def _missing_tools_line(lines: list[str]) -> tuple[int, str] | None:
    for idx, line in enumerate(lines, start=1):
        if "Missing required tool(s):" in line:
            return idx, line
    return None


def _parse_tools_from_line(line: str) -> list[str]:
    _, _, tail = line.partition(":")
    return [item.strip() for item in tail.split(",") if item.strip()]


def _missing_evidence(
    *,
    path: Path,
    findings: list[dict[str, Any]],
    missing_tools: list[str],
) -> list[MissingEvidence]:
    missing: list[MissingEvidence] = []
    if any(item["code"] == "required_tool_validation_failed" for item in findings):
        missing.append(
            MissingEvidence(
                scope="report",
                subject=str(path),
                field="required_tool_validation_failed",
                severity="block",
                reason="Report was rendered after mandatory evidence validation failed.",
            )
        )
    if missing_tools:
        missing.append(
            MissingEvidence(
                scope="report",
                subject=str(path),
                field="missing_required_tools",
                severity="block",
                reason=", ".join(missing_tools),
            )
        )
    return missing


def _remediation(findings: list[dict[str, Any]]) -> list[str]:
    return [str(item["remediation"]) for item in findings if item.get("remediation")]


def _infer_symbol(path: Path) -> str:
    name = path.name
    if "_research_" in name:
        return name.split("_research_", 1)[0].upper()
    token = re.split(r"[_\.-]", path.stem, maxsplit=1)[0]
    return token.upper() if token.isalpha() else ""
