from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


ACTIVE_KEEP = {
    "nse_agent.py",
    "sector_rotation_report.py",
    "sector_rotation_tracker.py",
    "daily_refresh.py",
    "fixed_nse_universe_analysis.py",
    "load_latest_nse_data_comprehensive.R",
    "terminal",
    "agent_adda",
    "tests",
    "docs",
    "scripts",
    "data/sector_rotation_tracker.db",
    "data/nse_sec_full_data.csv",
    "data/nse_index_data.csv",
    "reports/latest",
    ".git",
    ".venv",
    "venv",
    "env",
}

ROOT_ARCHIVE_FILES = {
    "run_demo.R",
    "production_demo.R",
    "final_complete_demo.R",
    "simple_test.R",
    "test_system.R",
    "final_data_merge.R",
    "merge_all_data.R",
    "september_final_merge.R",
    "truncate_and_replace_data.R",
    "real_nse_analysis.R",
    "real_nse_analysis_fixed.R",
    "comprehensive_real_nse_analysis.R",
}

SKIP_SCAN_DIRS = {".git", ".venv", "venv", "env", "archive/repo-cleanup-20260511"}


@dataclass(frozen=True)
class CleanupDecision:
    path: str
    action: str
    reason: str


def _norm(path: Path) -> str:
    text = path.as_posix()
    if text.startswith("./"):
        return text[2:]
    return text


def archive_destination(path: Path, run_id: str) -> Path:
    return Path("archive") / f"repo-cleanup-{run_id}" / _norm(path)


def classify_path(path: Path) -> CleanupDecision:
    p = _norm(path)
    name = path.name

    if name == ".DS_Store":
        return CleanupDecision(p, "delete", "macOS metadata")
    if name == "__pycache__" or p.endswith("/__pycache__"):
        return CleanupDecision(p, "delete", "Python bytecode cache")
    if name in {".pytest_cache", ".mypy_cache", ".ruff_cache"}:
        return CleanupDecision(p, "delete", "tool cache")
    if p in {"reports/temp", "tmp/visual-qa"} or p.startswith("reports/temp/"):
        return CleanupDecision(p, "delete", "temporary generated artifacts")

    if p in ACTIVE_KEEP or any(p.startswith(k + "/") for k in ACTIVE_KEEP if not k.endswith((".py", ".R", ".csv", ".db"))):
        return CleanupDecision(p, "keep", "active runtime or protected project path")

    if p in {"organized", "output"} or p.startswith("organized/") or p.startswith("output/"):
        return CleanupDecision(p, "archive", "legacy generated output tree")
    if p in ROOT_ARCHIVE_FILES:
        return CleanupDecision(p, "archive", "legacy demo or merge script")
    if len(path.parts) == 1 and name.startswith("PR") and name.endswith(".zip"):
        return CleanupDecision(p, "archive", "raw NSE archive download at repo root")
    if len(path.parts) == 1 and name.endswith(("29102025.csv", "29102025.txt")):
        return CleanupDecision(p, "archive", "dated NSE source artifact at repo root")

    return CleanupDecision(p, "review", "not classified automatically")


def render_manifest(decisions: list[CleanupDecision], run_id: str) -> str:
    grouped: dict[str, list[CleanupDecision]] = {}
    for decision in decisions:
        grouped.setdefault(decision.action, []).append(decision)

    lines = [
        f"# Repo Cleanup Manifest - {run_id}",
        "",
        "This manifest records cleanup decisions before any archive or delete operation.",
        "",
    ]
    for action in ("keep", "archive", "delete", "review"):
        title = action.title()
        items = sorted(grouped.get(action, []), key=lambda d: d.path)
        lines.append(f"## {title}")
        lines.append("")
        if not items:
            lines.append("- None")
        for item in items:
            lines.append(f"- `{item.path}` - {item.reason}")
        lines.append("")
    return "\n".join(lines)


def _should_skip_scan(path: Path) -> bool:
    p = _norm(path)
    return p in SKIP_SCAN_DIRS or p.startswith(".git/") or p.startswith(".venv/")


def scan_root(root: Path) -> list[CleanupDecision]:
    decisions: list[CleanupDecision] = []
    for path in sorted(root.rglob("*"), key=lambda p: p.as_posix()):
        rel = path.relative_to(root)
        if _should_skip_scan(rel):
            if len(rel.parts) == 1:
                decisions.append(classify_path(rel))
            continue
        decision = classify_path(rel)
        decisions.append(decision)
        if path.is_dir() and decision.action in {"archive", "delete"}:
            # The parent directory action covers its children in execution.
            continue
    return _dedupe_parent_covered(decisions)


def _dedupe_parent_covered(decisions: list[CleanupDecision]) -> list[CleanupDecision]:
    covering = [
        d.path
        for d in decisions
        if d.action in {"archive", "delete"}
    ]
    result: list[CleanupDecision] = []
    for decision in decisions:
        if any(decision.path != parent and decision.path.startswith(parent + "/") for parent in covering):
            continue
        result.append(decision)
    return result


def execute_decisions(
    root: Path,
    decisions: list[CleanupDecision],
    dry_run: bool = True,
    run_id: str = "20260511",
) -> dict:
    import shutil

    result = {"deleted": [], "would_delete": [], "archived": [], "would_archive": []}
    for decision in decisions:
        src = root / decision.path
        if decision.action == "delete":
            if dry_run:
                result["would_delete"].append(decision.path)
            elif src.exists():
                if src.is_dir():
                    shutil.rmtree(src)
                else:
                    src.unlink()
                result["deleted"].append(decision.path)
        elif decision.action == "archive":
            if dry_run:
                result["would_archive"].append(decision.path)
            elif src.exists():
                dst = root / archive_destination(Path(decision.path), run_id)
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dst))
                result["archived"].append(decision.path)
    return result


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Manifest-first repository cleanup")
    parser.add_argument("--run-id", default="20260511")
    parser.add_argument("--write-manifest", action="store_true")
    parser.add_argument("--safe-delete", action="store_true")
    parser.add_argument("--archive", action="store_true")
    parser.add_argument("--apply", action="store_true", help="Apply safe delete or archive actions")
    args = parser.parse_args()

    decisions = scan_root(Path("."))
    text = render_manifest(decisions, args.run_id)
    if args.write_manifest:
        out = Path("docs") / f"repo-cleanup-manifest-{args.run_id[:4]}-{args.run_id[4:6]}-{args.run_id[6:]}.md"
        out.write_text(text + "\n", encoding="utf-8")
        print(out)
    elif not args.safe_delete and not args.archive:
        print(text)

    if args.safe_delete:
        delete_decisions = [d for d in decisions if d.action == "delete"]
        result = execute_decisions(Path("."), delete_decisions, dry_run=not args.apply, run_id=args.run_id)
        print(result)

    if args.archive:
        archive_decisions = [d for d in decisions if d.action == "archive"]
        result = execute_decisions(Path("."), archive_decisions, dry_run=not args.apply, run_id=args.run_id)
        print(result)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
