#!/usr/bin/env python3
"""LLM-assisted report validation and conservative auto-fix gate.

The validator is designed for daily_refresh checkpoints. It runs deterministic
checks first, applies only whitelisted artifact fixes, then asks an LLM for a
structured review. The LLM is intentionally not allowed to edit source code.
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
MAIN_WORKTREE_BASE = ROOT.parent.parent if ROOT.parent.name == ".worktrees" else ROOT
REPORTS_DIR = ROOT / "reports"
LATEST_DIR = REPORTS_DIR / "latest"
VALIDATION_DIR = REPORTS_DIR / "report_validation"
PYTHON = sys.executable
DEFAULT_MODEL = os.environ.get("REPORT_VALIDATION_MODEL") or os.environ.get("OPENAI_MODEL") or "gpt-4o-mini"


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    try:
        from dotenv import load_dotenv  # type: ignore

        load_dotenv(path, override=False)
        return
    except Exception:
        pass
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip().strip('"').strip("'")


_load_dotenv(ROOT / ".env")
if MAIN_WORKTREE_BASE != ROOT:
    _load_dotenv(MAIN_WORKTREE_BASE / ".env")


def _today_ist() -> str:
    # Avoid adding a third-party timezone dependency.
    return datetime.fromtimestamp(time.time() + 5.5 * 3600, tz=timezone.utc).strftime("%Y-%m-%d")


def _now_ist() -> str:
    return datetime.fromtimestamp(time.time() + 5.5 * 3600, tz=timezone.utc).strftime("%Y-%m-%d %H:%M IST")


@dataclass(frozen=True)
class ReportSpec:
    key: str
    title: str
    paths: tuple[Path, ...]
    min_bytes: int
    required_terms: tuple[str, ...] = ()
    fix_command: tuple[str, ...] | None = None


@dataclass
class Finding:
    report: str
    severity: str
    issue: str
    evidence: str = ""
    fix_status: str = "not_needed"


@dataclass
class ValidationResult:
    checkpoint: str
    generated_at: str
    mode: str
    findings: list[Finding] = field(default_factory=list)
    fixes_applied: list[str] = field(default_factory=list)
    llm_review: dict[str, Any] | None = None


REPORT_SPECS: dict[str, ReportSpec] = {
    "portfolio_strategy_lab": ReportSpec(
        key="portfolio_strategy_lab",
        title="Portfolio Strategy Lab",
        paths=(LATEST_DIR / "portfolio_strategy_lab.html",),
        min_bytes=25_000,
        required_terms=("Portfolio Strategy", "Strategy", "VCP"),
        fix_command=(PYTHON, "-m", "portfolio.cli", "strategy-lab", "--report"),
    ),
    "sector_rotation": ReportSpec(
        key="sector_rotation",
        title="Sector Rotation",
        paths=(LATEST_DIR / "sector_rotation.html", LATEST_DIR / "sector_rotation.md"),
        min_bytes=10_000,
        required_terms=("Sector Rotation", "Investment Candidates", "Market Brief"),
        fix_command=(PYTHON, "sector_rotation_report.py"),
    ),
    "stage2_tracker": ReportSpec(
        key="stage2_tracker",
        title="Stage 2 Tracker",
        paths=(LATEST_DIR / "stage2_tracker.html",),
        min_bytes=25_000,
        required_terms=("Stage 2 Tracker", "How to Read", "VCP", "Best Strategy"),
        fix_command=(PYTHON, "sector_rotation_tracker.py", "--report", "--html"),
    ),
    "top_picks": ReportSpec(
        key="top_picks",
        title="Top Investment Picks",
        paths=(LATEST_DIR / "top_picks.html", LATEST_DIR / "top_picks.md"),
        min_bytes=20_000,
        required_terms=("Top Investment Picks", "Executive Summary", "Pick Summary", "vcp+sector"),
        fix_command=(PYTHON, "top_picks_report.py"),
    ),
    "portfolio_eod": ReportSpec(
        key="portfolio_eod",
        title="My Portfolio EOD",
        paths=(LATEST_DIR / "portfolio_analysis.html",),
        min_bytes=20_000,
        required_terms=("Portfolio", "holdings", "Market Value", "Unrealised P&L"),
        fix_command=(PYTHON, "-c", "from terminal.portfolio_monitor import run_eod_report; raise SystemExit(0 if run_eod_report().get('success') else 1)"),
    ),
}

CHECKPOINT_REPORTS: dict[str, tuple[str, ...]] = {
    "portfolio_strategy_lab": ("portfolio_strategy_lab",),
    "sector_rotation": ("portfolio_strategy_lab", "sector_rotation"),
    "stage2_tracker": ("portfolio_strategy_lab", "sector_rotation", "stage2_tracker"),
    "top_picks": ("portfolio_strategy_lab", "sector_rotation", "stage2_tracker", "top_picks"),
    "portfolio_eod": ("portfolio_strategy_lab", "sector_rotation", "stage2_tracker", "top_picks", "portfolio_eod"),
    "final": tuple(REPORT_SPECS),
}


def _read_text(path: Path, max_chars: int | None = None) -> str:
    text = path.read_text(encoding="utf-8", errors="ignore")
    return text if max_chars is None else text[:max_chars]


def _required_term_present(text: str, term: str) -> bool:
    """Match required report terms the way a reader sees them."""
    haystack = re.sub(r"\s+", " ", (text or "").lower())
    needle = re.sub(r"\s+", " ", (term or "").lower()).strip()
    if not needle:
        return True
    if needle in haystack:
        return True
    return re.sub(r"\s+", "", needle) in re.sub(r"\s+", "", haystack)


def _path_status(path: Path, min_bytes: int) -> Finding | None:
    if not path.exists():
        return Finding(path.name, "high", "Report artifact is missing.", str(path), "pending")
    size = path.stat().st_size
    if size < min_bytes:
        return Finding(path.name, "high", "Report artifact is unexpectedly small.", f"{size} bytes < {min_bytes}", "pending")
    return None


def _sanitize_nan_artifacts(spec: ReportSpec, result: ValidationResult) -> None:
    patterns = {
        "+nan%": "N/A",
        "-nan%": "N/A",
        "nan%": "N/A",
        ">nan<": ">N/A<",
        ">NaN<": ">N/A<",
    }
    for path in spec.paths:
        if not path.exists() or path.suffix.lower() not in {".html", ".md"}:
            continue
        text = _read_text(path)
        updated = text
        for old, new in patterns.items():
            updated = updated.replace(old, new)
        if updated != text:
            path.write_text(updated, encoding="utf-8")
            result.fixes_applied.append(f"{spec.key}: replaced NaN display artifacts in {path.relative_to(ROOT)}")


def _portfolio_csv_count() -> int | None:
    candidates = [
        Path(os.environ.get("AGENT_ADDA_PORTFOLIO_CSV", "")) if os.environ.get("AGENT_ADDA_PORTFOLIO_CSV") else None,
        MAIN_WORKTREE_BASE / "docs" / "my_portfolio.csv.csv",
        ROOT / "docs" / "my_portfolio.csv.csv",
        ROOT / "data" / "holdings.csv",
    ]
    for path in candidates:
        if not path or not path.exists():
            continue
        with path.open(newline="", encoding="utf-8", errors="ignore") as f:
            return sum(1 for row in csv.DictReader(f) if any((v or "").strip() for v in row.values()))
    return None


def _validate_portfolio_report(result: ValidationResult) -> None:
    path = LATEST_DIR / "portfolio_analysis.html"
    if not path.exists():
        return
    text = _read_text(path, max_chars=20_000)
    expected = _portfolio_csv_count()
    match = re.search(r"(\d+)\s+holdings", text, flags=re.I)
    actual = int(match.group(1)) if match else None
    if expected and actual and actual != expected:
        result.findings.append(Finding(
            "portfolio_eod",
            "high",
            "Portfolio report holding count does not match the configured portfolio CSV.",
            f"report={actual}, csv={expected}",
            "pending",
        ))
    if re.search(r"\b5\s+holdings\b", text, flags=re.I) and expected and expected > 50:
        result.findings.append(Finding(
            "portfolio_eod",
            "high",
            "Portfolio report appears to use the sample holdings file instead of broker CSV.",
            f"broker_csv_rows={expected}",
            "pending",
        ))


def _extract_top_pick_symbols() -> list[str]:
    path = LATEST_DIR / "top_picks.md"
    if not path.exists():
        return []
    symbols: list[str] = []
    in_table = False
    for raw in _read_text(path).splitlines():
        line = raw.strip()
        if line.startswith("| # | Symbol |"):
            in_table = True
            continue
        if in_table and line.startswith("|---"):
            continue
        if in_table and not line.startswith("|"):
            break
        if in_table:
            parts = [p.strip() for p in line.strip("|").split("|")]
            if len(parts) >= 2:
                sym = re.sub(r"[*`]", "", parts[1]).strip()
                if sym and sym.lower() != "symbol":
                    symbols.append(sym)
    return symbols[:10]


def _expected_top_picks() -> list[str]:
    try:
        import top_picks_report as t

        with t._connect() as conn:  # type: ignore[attr-defined]
            snap_date = t._resolve_snapshot_date(conn, None)  # type: ignore[attr-defined]
            return [p.symbol for p in t.build_pick_list(conn, snap_date)]  # type: ignore[attr-defined]
    except Exception:
        return []


def _validate_top_picks(result: ValidationResult) -> None:
    md = LATEST_DIR / "top_picks.md"
    if not md.exists():
        return
    text = _read_text(md, max_chars=30_000)
    if "OPENAI_API_KEY not set" in text or "rule-based narrative" in text:
        result.findings.append(Finding(
            "top_picks",
            "medium",
            "Top Picks report appears to have skipped LLM narration.",
            "OPENAI_API_KEY/rule-based marker present",
            "pending",
        ))
    actual = _extract_top_pick_symbols()
    expected = _expected_top_picks()
    if expected and actual and actual != expected[: len(actual)]:
        result.findings.append(Finding(
            "top_picks",
            "high",
            "Top Picks symbols do not match the current selection engine output.",
            f"report={actual}; engine={expected[:len(actual)]}",
            "pending",
        ))


def _run_fix(spec: ReportSpec, reason: str, result: ValidationResult, dry_run: bool) -> None:
    if not spec.fix_command:
        return
    if dry_run:
        result.fixes_applied.append(f"DRY RUN: would regenerate {spec.key} because {reason}")
        return
    proc = subprocess.run(
        list(spec.fix_command),
        cwd=str(ROOT),
        env=os.environ.copy(),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=int(os.environ.get("REPORT_VALIDATION_FIX_TIMEOUT", "900")),
    )
    if proc.returncode == 0:
        result.fixes_applied.append(f"{spec.key}: regenerated via {' '.join(spec.fix_command)}")
    else:
        result.findings.append(Finding(
            spec.key,
            "high",
            "Whitelisted regeneration command failed.",
            proc.stdout[-1200:],
            "failed",
        ))


def _deterministic_validate(checkpoint: str, dry_run: bool) -> ValidationResult:
    result = ValidationResult(checkpoint=checkpoint, generated_at=_now_ist(), mode="rules+llm")
    report_keys = CHECKPOINT_REPORTS.get(checkpoint, (checkpoint,))
    for key in report_keys:
        spec = REPORT_SPECS[key]
        before_count = len(result.findings)
        combined_text = ""
        for path in spec.paths:
            finding = _path_status(path, spec.min_bytes)
            if finding:
                finding.report = spec.key
                result.findings.append(finding)
                continue
            text = _read_text(path, max_chars=100_000)
            combined_text += "\n" + text
        _sanitize_nan_artifacts(spec, result)
        combined_text = ""
        for path in spec.paths:
            if path.exists() and path.suffix.lower() in {".html", ".md"}:
                combined_text += "\n" + _read_text(path, max_chars=100_000)
        for term in spec.required_terms:
            if not _required_term_present(combined_text, term):
                result.findings.append(Finding(
                    spec.key,
                    "medium",
                    f"Required report section/term is missing: {term}",
                    ", ".join(str(p.relative_to(ROOT)) for p in spec.paths),
                    "pending",
                ))
        if re.search(r"(?i)(\+nan%|-nan%|\bnan%)", combined_text):
            result.findings.append(Finding(
                spec.key,
                "medium",
                "Report contains visible NaN percentage artifacts.",
                ", ".join(str(p.relative_to(ROOT)) for p in spec.paths),
                "pending",
            ))
        added = result.findings[before_count:]
        needs_regen = any(f.severity == "high" and f.fix_status == "pending" for f in added)
        if needs_regen:
            _run_fix(spec, "high-severity artifact validation failure", result, dry_run)
    if "portfolio_eod" in report_keys:
        _validate_portfolio_report(result)
    if "top_picks" in report_keys:
        _validate_top_picks(result)
    return result


def _collect_report_context(report_keys: tuple[str, ...]) -> dict[str, Any]:
    context: dict[str, Any] = {}
    context["report_purposes"] = {
        "portfolio_strategy_lab": "Paper strategy replay and strategy ranking; not a current holdings recommendation report.",
        "sector_rotation": "Market/sector breadth and sector candidate report.",
        "stage2_tracker": "Weinstein Stage 2 universe tracker and VCP/watchlist surface.",
        "top_picks": "Independent investment-picks report selected from current strategy/sector/stage signals.",
        "portfolio_eod": "Personal holdings EOD monitor; signals apply to currently held positions only.",
    }
    for key in report_keys:
        spec = REPORT_SPECS[key]
        entries = []
        for path in spec.paths:
            entry = {
                "path": str(path.relative_to(ROOT)),
                "exists": path.exists(),
                "bytes": path.stat().st_size if path.exists() else 0,
                "excerpt": "",
            }
            if path.exists() and path.suffix.lower() in {".md", ".html"}:
                text = _read_text(path, max_chars=80_000)
                clean = re.sub(r"<script\b.*?</script>", " ", text, flags=re.I | re.S)
                clean = re.sub(r"<style\b.*?</style>", " ", clean, flags=re.I | re.S)
                clean = re.sub(r"<[^>]+>", " ", clean)
                clean = html.unescape(re.sub(r"\s+", " ", clean)).strip()
                entry["excerpt"] = clean[:6000]
            entries.append(entry)
        context[key] = entries
    context["top_pick_symbols_report"] = _extract_top_pick_symbols()
    context["top_pick_symbols_engine"] = _expected_top_picks()
    context["portfolio_csv_rows"] = _portfolio_csv_count()
    return context


def _llm_call(system_msg: str, user_msg: str, *, model: str, timeout: int = 180) -> dict[str, Any]:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return {"status": "skipped", "reason": "OPENAI_API_KEY not set"}
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
        "max_completion_tokens": 4096,
        "response_format": {"type": "json_object"},
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as tf:
        json.dump(body, tf)
        payload_path = tf.name
    try:
        proc = subprocess.run(
            [
                "curl",
                "-s",
                "--max-time",
                str(timeout - 10),
                "https://api.openai.com/v1/chat/completions",
                "-H",
                f"Authorization: Bearer {api_key}",
                "-H",
                "Content-Type: application/json",
                "-d",
                f"@{payload_path}",
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    finally:
        try:
            os.unlink(payload_path)
        except OSError:
            pass
    if proc.returncode != 0:
        return {"status": "failed", "reason": proc.stderr[-500:]}
    try:
        data = json.loads(proc.stdout)
        if "error" in data:
            return {"status": "failed", "reason": data["error"]}
        content = data["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        parsed.setdefault("status", "ok")
        return parsed
    except Exception as exc:
        return {"status": "failed", "reason": f"{exc}; raw={proc.stdout[:500]}"}


def _run_llm_review(result: ValidationResult, model: str, skip_llm: bool) -> None:
    if skip_llm:
        result.llm_review = {"status": "skipped", "reason": "--skip-llm"}
        return
    report_keys = CHECKPOINT_REPORTS.get(result.checkpoint, (result.checkpoint,))
    context = _collect_report_context(report_keys)
    findings = [f.__dict__ for f in result.findings]
    system_msg = (
        "You are Agent Adda's report QA reviewer. Use Plan-of-Thought and "
        "Tree-of-Thought internally to compare hypotheses, but do not reveal "
        "private reasoning. Return strict JSON only. You may recommend fixes, "
        "but executable fixes must be limited to regenerating report artifacts, "
        "cleaning display-only NaN artifacts, refreshing source data, or filing "
        "a logic-fix recommendation. Do not invent market facts. Do not treat "
        "absence from a truncated excerpt as missing data. A report dated today "
        "is not stale merely because there is no later date. Do not compare a "
        "personal portfolio signal count with a separate market-universe report "
        "as if they must match. Do not call independent top-picks and personal "
        "portfolio signals conflicting unless the same symbol has contradictory "
        "data for the same snapshot and metric."
    )
    user_msg = json.dumps(
        {
            "task": "Review generated daily market reports for correctness, consistency, stale data, missing sections, unsupported claims, and cross-report contradictions.",
            "checkpoint": result.checkpoint,
            "generated_at": result.generated_at,
            "deterministic_findings": findings,
            "report_context": context,
            "required_output_schema": {
                "status": "ok|warning|failed",
                "overall_verdict": "short verdict",
                "confidence": "low|medium|high",
                "issues": [
                    {
                        "severity": "low|medium|high",
                        "report": "report key",
                        "issue": "specific issue",
                        "evidence": "grounded evidence from context",
                        "recommended_fix": "specific action",
                        "fix_type": "artifact_regeneration|data_refresh|display_sanitization|logic_fix|manual_review",
                    }
                ],
                "cross_report_checks": ["short checks performed"],
                "report_reviews": [
                    {
                        "report": "report key",
                        "verdict": "short report-specific verdict",
                        "coverage": ["what was reviewed"],
                        "data_quality": ["specific data freshness/completeness checks"],
                        "consistency": ["cross-report or internal consistency checks"],
                        "fixes_needed": ["actionable fixes, or empty list"],
                        "residual_risks": ["remaining risks or manual checks"],
                    }
                ],
                "logic_fix_recommendations": ["source-code or ranking-logic changes to consider"],
            },
        },
        ensure_ascii=False,
    )
    result.llm_review = _ground_llm_review(_llm_call(system_msg, user_msg, model=model), result)


def _ground_llm_review(review: dict[str, Any], result: ValidationResult) -> dict[str, Any]:
    """Drop weak LLM claims that are not grounded enough for an audit report."""
    if not isinstance(review, dict) or review.get("status") in {"skipped", "failed"}:
        return review
    deterministic_reports = {f.report for f in result.findings}
    today = _today_ist()
    grounded: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    weak_markers = (
        "excerpt",
        "without recent updates after this date",
        "no later date",
        "holding 0 stocks",
        "holdings 0 stocks",
    )
    for issue in review.get("issues") or []:
        evidence = str(issue.get("evidence") or "").lower()
        report = str(issue.get("report") or "")
        if report in deterministic_reports:
            grounded.append(issue)
            continue
        issue_text = str(issue.get("issue") or "").lower()
        if "conflict" in issue_text and ("recommendation" in issue_text or "stock" in issue_text):
            dropped.append(issue)
            continue
        if today in evidence and ("stale" in str(issue.get("issue") or "").lower() or "after this date" in evidence):
            dropped.append(issue)
            continue
        if any(marker in evidence for marker in weak_markers):
            dropped.append(issue)
            continue
        if len(evidence) >= 30 and not any(marker in evidence for marker in weak_markers):
            grounded.append(issue)
        else:
            dropped.append(issue)
    review["issues"] = grounded
    if dropped:
        review["dropped_ungrounded_issues"] = dropped
    if not grounded and not result.findings:
        review["status"] = "ok"
        review["overall_verdict"] = "No grounded report issues found."
        review["confidence"] = review.get("confidence") or "medium"
        review["logic_fix_recommendations"] = []
    return review


def _report_keys_for_checkpoint(checkpoint: str) -> tuple[str, ...]:
    return CHECKPOINT_REPORTS.get(checkpoint, (checkpoint,))


def _artifact_summary(spec: ReportSpec) -> list[dict[str, Any]]:
    artifacts = []
    for path in spec.paths:
        artifacts.append({
            "path": str(path.relative_to(ROOT)),
            "exists": path.exists(),
            "bytes": path.stat().st_size if path.exists() else 0,
            "min_bytes": spec.min_bytes,
        })
    return artifacts


def _combined_report_text(spec: ReportSpec, max_chars_per_file: int = 100_000) -> str:
    chunks = []
    for path in spec.paths:
        if path.exists() and path.suffix.lower() in {".html", ".md"}:
            chunks.append(_read_text(path, max_chars=max_chars_per_file))
    return "\n".join(chunks)


def _deterministic_report_checks(key: str, spec: ReportSpec) -> list[str]:
    text = _combined_report_text(spec)
    checks: list[str] = []
    for art in _artifact_summary(spec):
        if art["exists"] and art["bytes"] >= art["min_bytes"]:
            checks.append(f"artifact ok: {art['path']} ({art['bytes']} bytes)")
        elif art["exists"]:
            checks.append(f"artifact small: {art['path']} ({art['bytes']} bytes < {art['min_bytes']})")
        else:
            checks.append(f"artifact missing: {art['path']}")
    for term in spec.required_terms:
        checks.append(f"required term {'present' if _required_term_present(text, term) else 'missing'}: {term}")
    checks.append("visible NaN percentage artifacts absent" if not re.search(r"(?i)(\+nan%|-nan%|\bnan%)", text) else "visible NaN percentage artifacts present")
    if key == "top_picks":
        actual = _extract_top_pick_symbols()
        expected = _expected_top_picks()
        if expected and actual:
            checks.append("top-pick symbols match selection engine" if actual == expected[:len(actual)] else f"top-pick symbol mismatch: report={actual}, engine={expected[:len(actual)]}")
        checks.append(f"top-pick symbols reviewed: {', '.join(actual) if actual else 'none found'}")
    if key == "portfolio_eod":
        expected_rows = _portfolio_csv_count()
        match = re.search(r"(\d+)\s+holdings", text, flags=re.I)
        report_rows = int(match.group(1)) if match else None
        checks.append(f"portfolio CSV rows: {expected_rows if expected_rows is not None else 'unknown'}")
        checks.append(f"portfolio report holdings: {report_rows if report_rows is not None else 'not found'}")
        if expected_rows and report_rows:
            checks.append("portfolio holdings count matches CSV" if expected_rows == report_rows else "portfolio holdings count differs from CSV")
    return checks


def _build_report_reviews(result: ValidationResult) -> dict[str, dict[str, Any]]:
    llm = result.llm_review or {}
    llm_issues = llm.get("issues") or []
    llm_reviews = {
        str(item.get("report")): item
        for item in (llm.get("report_reviews") or [])
        if isinstance(item, dict) and item.get("report")
    }
    report_keys = _report_keys_for_checkpoint(result.checkpoint)
    reviews: dict[str, dict[str, Any]] = {}
    for key in report_keys:
        spec = REPORT_SPECS[key]
        findings = [f.__dict__ for f in result.findings if f.report == key]
        fixes = [f for f in result.fixes_applied if f.startswith(f"{key}:") or f" {key}" in f]
        issues = [
            issue for issue in llm_issues
            if str(issue.get("report") or "").strip() in {key, spec.title, spec.paths[0].name}
        ]
        llm_report = llm_reviews.get(key) or llm_reviews.get(spec.title) or {}
        issue_fixes = [
            issue.get("recommended_fix") for issue in issues
            if issue.get("recommended_fix")
        ]
        report_fixes = [
            item for item in (llm_report.get("fixes_needed") or [])
            if str(item).strip().lower() not in {"manual_review", "logic_fix", "data_refresh", "artifact_regeneration"}
        ]
        deterministic_checks = _deterministic_report_checks(key, spec)
        artifact_ok = all(a["exists"] and a["bytes"] >= a["min_bytes"] for a in _artifact_summary(spec))
        combined = _combined_report_text(spec)
        required_ok = all(_required_term_present(combined, term) for term in spec.required_terms)
        has_high = any((f.get("severity") == "high") for f in findings) or any((i.get("severity") == "high") for i in issues)
        status = "pass" if artifact_ok and required_ok and not findings and not issues else "review"
        if has_high:
            status = "attention"
        reviews[key] = {
            "title": spec.title,
            "status": status,
            "artifacts": _artifact_summary(spec),
            "deterministic_checks": deterministic_checks,
            "findings": findings,
            "llm_issues": issues,
            "fixes_applied": fixes,
            "llm_verdict": llm_report.get("verdict"),
            "coverage": llm_report.get("coverage") or [
                "artifact presence and size",
                "required report sections",
                "visible data-quality artifacts",
                "report-specific source alignment",
            ],
            "data_quality": llm_report.get("data_quality") or [
                check for check in deterministic_checks
                if "NaN" in check or "rows" in check or "symbols" in check or "holdings" in check
            ],
            "consistency": llm_report.get("consistency") or [
                "checked against deterministic source contracts and generated artifacts"
            ],
            "fixes_needed": report_fixes or issue_fixes,
            "residual_risks": llm_report.get("residual_risks") or [
                "LLM review is advisory; deterministic checks remain the execution gate."
            ],
        }
    return reviews


def _write_outputs(result: ValidationResult) -> tuple[Path, Path]:
    VALIDATION_DIR.mkdir(parents=True, exist_ok=True)
    stamp = _today_ist().replace("-", "")
    jsonl_path = VALIDATION_DIR / f"report_validation_{stamp}.jsonl"
    md_path = VALIDATION_DIR / f"report_validation_{stamp}.md"
    latest_md = LATEST_DIR / "report_validation.md"
    report_reviews = _build_report_reviews(result)
    payload = {
        "checkpoint": result.checkpoint,
        "generated_at": result.generated_at,
        "mode": result.mode,
        "findings": [f.__dict__ for f in result.findings],
        "fixes_applied": result.fixes_applied,
        "llm_review": result.llm_review,
        "report_reviews": report_reviews,
    }
    with jsonl_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    records = []
    for line in jsonl_path.read_text(encoding="utf-8").splitlines():
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    lines = [
        f"# Daily Report Validation — {_today_ist()}",
        "",
        f"Generated: {_now_ist()}",
        "",
        "## Checkpoints",
        "",
    ]
    for rec in records:
        llm = rec.get("llm_review") or {}
        verdict = llm.get("overall_verdict") or llm.get("status") or "not reviewed"
        lines.extend([
            f"### {rec.get('checkpoint')}",
            "",
            f"- Generated: {rec.get('generated_at')}",
            f"- Verdict: {verdict}",
            f"- Findings: {len(rec.get('findings') or [])}",
            f"- Fixes applied: {len(rec.get('fixes_applied') or [])}",
            "",
        ])
        for fix in rec.get("fixes_applied") or []:
            lines.append(f"- Fix: {fix}")
        for finding in rec.get("findings") or []:
            lines.append(
                f"- {finding.get('severity', 'unknown').upper()} {finding.get('report')}: "
                f"{finding.get('issue')} ({finding.get('evidence', '')})"
            )
        for issue in (llm.get("issues") or [])[:8]:
            lines.append(
                f"- LLM {issue.get('severity', 'unknown').upper()} {issue.get('report')}: "
                f"{issue.get('issue')} -> {issue.get('recommended_fix')}"
            )
        reviews = rec.get("report_reviews") or {}
        if reviews:
            lines.append("")
            lines.append("Per-Report Reviews:")
            lines.append("")
            for key, review in reviews.items():
                lines.append(f"#### {review.get('title') or key}")
                lines.append("")
                lines.append(f"- Status: {review.get('status')}")
                if review.get("llm_verdict"):
                    lines.append(f"- LLM verdict: {review.get('llm_verdict')}")
                lines.append("- Artifacts:")
                for artifact in review.get("artifacts") or []:
                    exists = "present" if artifact.get("exists") else "missing"
                    lines.append(
                        f"  - {artifact.get('path')}: {exists}, "
                        f"{artifact.get('bytes')} bytes"
                    )
                lines.append("- Deterministic checks:")
                for check in (review.get("deterministic_checks") or [])[:12]:
                    lines.append(f"  - {check}")
                if review.get("coverage"):
                    lines.append("- Review coverage:")
                    for item in (review.get("coverage") or [])[:8]:
                        lines.append(f"  - {item}")
                if review.get("data_quality"):
                    lines.append("- Data quality:")
                    for item in (review.get("data_quality") or [])[:8]:
                        lines.append(f"  - {item}")
                if review.get("consistency"):
                    lines.append("- Consistency:")
                    for item in (review.get("consistency") or [])[:8]:
                        lines.append(f"  - {item}")
                if review.get("findings"):
                    lines.append("- Rule findings:")
                    for item in review.get("findings") or []:
                        lines.append(f"  - {item.get('severity', 'unknown').upper()}: {item.get('issue')}")
                if review.get("llm_issues"):
                    lines.append("- LLM findings:")
                    for item in review.get("llm_issues") or []:
                        lines.append(f"  - {item.get('severity', 'unknown').upper()}: {item.get('issue')} -> {item.get('recommended_fix')}")
                if review.get("fixes_applied"):
                    lines.append("- Fixes applied:")
                    for item in review.get("fixes_applied") or []:
                        lines.append(f"  - {item}")
                fixes_needed = review.get("fixes_needed") or []
                lines.append("- Fixes needed:")
                if fixes_needed:
                    for item in fixes_needed[:8]:
                        lines.append(f"  - {item}")
                else:
                    lines.append("  - None from grounded validation.")
                if review.get("residual_risks"):
                    lines.append("- Residual risks:")
                    for item in (review.get("residual_risks") or [])[:6]:
                        lines.append(f"  - {item}")
                lines.append("")
        logic = llm.get("logic_fix_recommendations") or []
        if logic:
            lines.append("")
            lines.append("Logic Fix Recommendations:")
            for item in logic[:8]:
                lines.append(f"- {item}")
        lines.append("")
    md_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    latest_md.write_text(md_path.read_text(encoding="utf-8"), encoding="utf-8")
    return jsonl_path, md_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate generated reports with deterministic checks plus LLM review.")
    parser.add_argument("--checkpoint", default="final", choices=sorted(CHECKPOINT_REPORTS), help="Logical pipeline checkpoint to validate")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="OpenAI model for LLM review")
    parser.add_argument("--skip-llm", action="store_true", help="Run deterministic validation only")
    parser.add_argument("--dry-run", action="store_true", help="Do not run whitelisted regeneration fixes")
    parser.add_argument("--fail-on-high", action="store_true", help="Exit non-zero when high severity findings remain")
    args = parser.parse_args()

    result = _deterministic_validate(args.checkpoint, dry_run=args.dry_run)
    _run_llm_review(result, model=args.model, skip_llm=args.skip_llm)
    jsonl_path, md_path = _write_outputs(result)
    high = sum(1 for f in result.findings if f.severity == "high")
    print(f"Report validation checkpoint={args.checkpoint} findings={len(result.findings)} high={high}")
    print(f"Review report: {md_path}")
    print(f"Audit log: {jsonl_path}")
    return 1 if args.fail_on_high and high else 0


if __name__ == "__main__":
    raise SystemExit(main())
