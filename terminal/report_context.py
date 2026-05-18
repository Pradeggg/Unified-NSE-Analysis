"""Report artifact discovery and context helpers."""

from __future__ import annotations

import re
import subprocess
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


REPORT_DIRS = (
    "reports/generated",
    "reports/latest",
    "reports/strategy_council",
    "reports/sector_rotation",
    "reports/global",
)
REPORT_SUFFIXES = {".html", ".md", ".pdf", ".csv", ".json"}


def _root(project_root: str | Path | None = None) -> Path:
    return Path(project_root or Path.cwd()).resolve()


def _metadata(path: Path, root: Path) -> dict[str, Any]:
    name = path.name
    report_type = "report"
    symbol = ""
    if name.startswith("strategy_council_"):
        report_type = "strategy_council"
        parts = name.split("_")
        symbol = parts[2] if len(parts) > 2 else ""
    elif "_research_" in name:
        report_type = "research"
        symbol = name.split("_research_", 1)[0]
    elif "sector_rotation" in str(path).lower():
        report_type = "sector_rotation"
    elif "us_market" in name.lower():
        report_type = "global"

    stat = path.stat()
    return {
        "name": name,
        "path": str(path if path.is_absolute() else path.relative_to(root)),
        "absolute_path": str(path.resolve()),
        "report_type": report_type,
        "symbol": symbol.upper(),
        "suffix": path.suffix.lower(),
        "size_kb": round(stat.st_size / 1024, 1),
        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
    }


def list_generated_reports(project_root: str | Path | None = None, report_type: str = "any", limit: int = 20) -> dict[str, Any]:
    root = _root(project_root)
    rows: list[dict[str, Any]] = []
    for rel in REPORT_DIRS:
        directory = root / rel
        if not directory.exists():
            continue
        for path in directory.rglob("*"):
            if path.is_file() and path.suffix.lower() in REPORT_SUFFIXES:
                meta = _metadata(path, root)
                if report_type == "any" or report_type.lower() in meta["report_type"].lower() or report_type.lower() in meta["name"].lower():
                    rows.append(meta)
    rows.sort(key=lambda row: (row["modified"], row["name"]), reverse=True)
    return {"status": "ok", "count": len(rows), "reports": rows[:limit]}


def get_last_report(last_report_path: str | Path | None = None, project_root: str | Path | None = None) -> dict[str, Any]:
    if not last_report_path:
        return {"status": "needs_clarification", "message": "No report has been generated in this session yet."}
    path = Path(last_report_path).expanduser()
    if not path.is_absolute():
        path = _root(project_root) / path
    if not path.exists():
        return {"status": "missing", "message": f"Last report path is no longer available: {path}", "path": str(path)}
    return {"status": "ok", "report": _metadata(path, _root(project_root))}


def open_report(path: str, project_root: str | Path | None = None) -> dict[str, Any]:
    resolved = Path(path).expanduser()
    if not resolved.is_absolute():
        resolved = _root(project_root) / resolved
    if not resolved.exists():
        return {"status": "missing", "message": f"Report path is not available: {resolved}", "path": str(resolved)}
    subprocess.Popen(["open", str(resolved)])
    return {"status": "ok", "message": f"Opening report: {resolved}", "path": str(resolved)}


def read_report(path: str, project_root: str | Path | None = None, max_chars: int = 12000) -> dict[str, Any]:
    root = _root(project_root)
    resolved = Path(path).expanduser()
    if not resolved.is_absolute():
        resolved = root / resolved
    if not resolved.exists():
        return {"status": "missing", "message": f"Report path is not available: {resolved}", "path": str(resolved)}
    meta = _metadata(resolved, root)
    if resolved.suffix.lower() == ".pdf":
        return {**meta, "status": "unsupported", "content": "", "message": "PDF report text extraction is not enabled in report context."}
    content = resolved.read_text(encoding="utf-8", errors="replace")
    return {**meta, "status": "ok", "content": content[:max_chars], "truncated": len(content) > max_chars}


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip = False

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() in {"script", "style"}:
            self._skip = True

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style"}:
            self._skip = False

    def handle_data(self, data: str) -> None:
        if not self._skip and data.strip():
            self.parts.append(data.strip())


def _visible_text(content: str, suffix: str = "") -> str:
    if suffix.lower() not in {".html", ".htm"}:
        return content or ""
    parser = _VisibleTextParser()
    parser.feed(content or "")
    return "\n".join(parser.parts)


def _extract_recommendation(content: str) -> str:
    match = re.search(r"(?im)^\s*Recommendation\s*:\s*([A-Z_ -]+)\s*$", content or "")
    return match.group(1).strip() if match else ""


def summarize_report(path: str, project_root: str | Path | None = None) -> dict[str, Any]:
    report = read_report(path, project_root=project_root)
    if report.get("status") != "ok":
        return report
    content = _visible_text(report.get("content", ""), report.get("suffix", ""))
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    heading = next((line.lstrip("# ").strip() for line in lines if line.startswith("#")), report.get("name", "Report"))
    recommendation = _extract_recommendation(content)
    evidence_line = next((line for line in lines if "Evidence" in line), "")
    summary_parts = [heading]
    if recommendation:
        summary_parts.append(f"Recommendation: {recommendation}")
    if evidence_line:
        summary_parts.append(evidence_line)
    return {
        "status": "ok",
        "path": report["path"],
        "symbol": report.get("symbol", ""),
        "report_type": report.get("report_type", ""),
        "summary": "\n".join(summary_parts),
        "recommendation": recommendation,
    }


def compare_reports(first_path: str, second_path: str, project_root: str | Path | None = None) -> dict[str, Any]:
    first = read_report(first_path, project_root=project_root)
    second = read_report(second_path, project_root=project_root)
    if first.get("status") != "ok" or second.get("status") != "ok":
        return {"status": "missing", "first": first, "second": second}
    first_rec = _extract_recommendation(first.get("content", ""))
    second_rec = _extract_recommendation(second.get("content", ""))
    return {
        "status": "ok",
        "first_path": first["path"],
        "second_path": second["path"],
        "first_recommendation": first_rec,
        "second_recommendation": second_rec,
        "changed": first_rec != second_rec,
    }
