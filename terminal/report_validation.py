"""Deterministic local HTML report validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlparse


@dataclass(frozen=True)
class LinkCheck:
    report: str
    href: str
    status: str
    issue: str
    resolved_path: str = ""
    detail: str = ""


@dataclass
class ReportValidation:
    report_path: Path
    checks: list[LinkCheck] = field(default_factory=list)

    def summary(self) -> dict[str, int]:
        counts = {"pass": 0, "warn": 0, "fail": 0}
        for check in self.checks:
            counts[check.status] = counts.get(check.status, 0) + 1
        return counts

    def to_markdown(self) -> str:
        counts = self.summary()
        lines = [
            f"# Report Validation: {self.report_path.name}",
            "",
            f"Summary: {counts.get('pass', 0)} pass, {counts.get('warn', 0)} warn, {counts.get('fail', 0)} fail",
            "",
            "| Status | Issue | Href | Resolved Path | Detail |",
            "|---|---|---|---|---|",
        ]
        for check in self.checks:
            lines.append(
                f"| {check.status.upper()} | {check.issue} | `{check.href}` | `{check.resolved_path}` | {check.detail} |"
            )
        return "\n".join(lines)


class _HTMLLinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []
        self.ids: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {k.lower(): v or "" for k, v in attrs}
        if tag.lower() == "a" and attr.get("href"):
            self.hrefs.append(attr["href"])
        if attr.get("id"):
            self.ids.add(attr["id"])
        if attr.get("name"):
            self.ids.add(attr["name"])


def validate_html_report(path: str | Path, *, min_linked_html_bytes: int = 20) -> ReportValidation:
    report_path = Path(path)
    result = ReportValidation(report_path=report_path)
    if not report_path.exists():
        result.checks.append(LinkCheck(report_path.name, "", "fail", "missing_report", str(report_path)))
        return result

    text = report_path.read_text(encoding="utf-8", errors="replace")
    parser = _HTMLLinkParser()
    parser.feed(text)
    for href in parser.hrefs:
        parsed = urlparse(href)
        if parsed.scheme in {"http", "https", "mailto"}:
            continue
        if href.startswith("#"):
            anchor = unquote(href[1:])
            if anchor and anchor in parser.ids:
                result.checks.append(LinkCheck(report_path.name, href, "pass", "anchor_ok"))
            else:
                result.checks.append(LinkCheck(report_path.name, href, "fail", "missing_anchor", detail=f"anchor={anchor}"))
            continue
        if parsed.path == "":
            continue
        resolved = (report_path.parent / unquote(parsed.path)).resolve()
        if not resolved.exists():
            result.checks.append(LinkCheck(report_path.name, href, "fail", "missing_file", str(resolved)))
            continue
        if resolved.suffix.lower() in {".html", ".htm"}:
            size = resolved.stat().st_size
            body = resolved.read_text(encoding="utf-8", errors="replace").strip()
            if size < min_linked_html_bytes or not body:
                result.checks.append(LinkCheck(report_path.name, href, "warn", "empty_linked_html", str(resolved), f"{size} bytes"))
            elif not _has_core_content(body):
                result.checks.append(LinkCheck(report_path.name, href, "warn", "weak_linked_html_content", str(resolved)))
            else:
                result.checks.append(LinkCheck(report_path.name, href, "pass", "linked_html_ok", str(resolved)))
        else:
            result.checks.append(LinkCheck(report_path.name, href, "pass", "linked_file_ok", str(resolved)))
    return result


def validate_reports(paths: list[str | Path]) -> list[ReportValidation]:
    return [validate_html_report(path) for path in paths]


def write_validation_markdown(results: list[ReportValidation], path: str | Path) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Report Validation", ""]
    total = {"pass": 0, "warn": 0, "fail": 0}
    for result in results:
        summary = result.summary()
        for key, value in summary.items():
            total[key] = total.get(key, 0) + value
    lines.append(f"Summary: {total['pass']} pass, {total['warn']} warn, {total['fail']} fail")
    lines.append("")
    for result in results:
        lines.append(result.to_markdown())
        lines.append("")
    out.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return out


def _has_core_content(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in ("<table", "<section", "<article", "<p", "score", "summary", "analysis"))
