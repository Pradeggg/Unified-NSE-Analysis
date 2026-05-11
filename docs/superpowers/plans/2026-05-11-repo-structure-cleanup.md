# Repo Structure Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Clean up and reorganize the repository with an auditable archive-first process that preserves Agent Adda terminal behavior.

**Architecture:** Use a manifest-driven cleanup tool and staged moves. Phase 1 deletes only deterministic generated junk and archives unused artifacts. Later phases move root modules into packages with compatibility shims and update imports only after tests prove behavior is preserved.

**Tech Stack:** Python 3.13, pathlib, shutil, subprocess, unittest, existing `nse_agent.py`, `terminal/`, `company_intelligence_*`, and `voice_*` modules.

---

## File Structure

Create or modify these files:

- Create `scripts/maintenance/repo_cleanup.py`: manifest builder, safe delete, archive move, and dry-run executor.
- Create `tests/test_repo_cleanup.py`: unit tests for classification, archive path generation, and dry-run behavior.
- Create `docs/repo-cleanup-manifest-2026-05-11.md`: generated/auditable manifest for the current cleanup run.
- Create packages later:
  - `company_intelligence/`
  - `voice/`
- Modify later:
  - root `company_*.py` files into compatibility shims
  - root `voice_*.py` files into compatibility shims
  - imports in `nse_agent.py`, `terminal/tools.py`, tests, and command modules
  - `.gitignore` for generated reports/data patterns

---

### Task 1: Add Cleanup Classification Utility

**Files:**
- Create: `scripts/maintenance/repo_cleanup.py`
- Create: `tests/test_repo_cleanup.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_repo_cleanup.py` with:

```python
import unittest
from pathlib import Path

from scripts.maintenance.repo_cleanup import (
    classify_path,
    archive_destination,
    CleanupDecision,
)


class RepoCleanupTests(unittest.TestCase):
    def test_classifies_safe_delete_generated_junk(self):
        self.assertEqual(classify_path(Path(".DS_Store")).action, "delete")
        self.assertEqual(classify_path(Path("__pycache__")).action, "delete")
        self.assertEqual(classify_path(Path("terminal/__pycache__")).action, "delete")
        self.assertEqual(classify_path(Path("reports/temp")).action, "delete")

    def test_classifies_archive_candidates(self):
        self.assertEqual(classify_path(Path("PR110526.zip")).action, "archive")
        self.assertEqual(classify_path(Path("pr29102025.csv")).action, "archive")
        self.assertEqual(classify_path(Path("organized")).action, "archive")
        self.assertEqual(classify_path(Path("output")).action, "archive")
        self.assertEqual(classify_path(Path("run_demo.R")).action, "archive")

    def test_keeps_active_runtime_files(self):
        self.assertEqual(classify_path(Path("nse_agent.py")).action, "keep")
        self.assertEqual(classify_path(Path("terminal/tools.py")).action, "keep")
        self.assertEqual(classify_path(Path("data/sector_rotation_tracker.db")).action, "keep")
        self.assertEqual(classify_path(Path("reports/latest/sector_rotation.html")).action, "keep")

    def test_archive_destination_preserves_relative_path(self):
        dest = archive_destination(Path("reports/nse_analysis/old.html"), "20260511")
        self.assertEqual(dest, Path("archive/repo-cleanup-20260511/reports/nse_analysis/old.html"))

    def test_cleanup_decision_has_reason(self):
        decision = classify_path(Path("PR110526.zip"))
        self.assertIsInstance(decision, CleanupDecision)
        self.assertTrue(decision.reason)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
./.venv/bin/python -m unittest tests.test_repo_cleanup -v
```

Expected: fail with `ModuleNotFoundError: No module named 'scripts.maintenance.repo_cleanup'`.

- [ ] **Step 3: Add utility implementation**

Create `scripts/maintenance/repo_cleanup.py`:

```python
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
    "data/sector_rotation_tracker.db",
    "data/nse_sec_full_data.csv",
    "data/nse_index_data.csv",
    "reports/latest",
    ".git",
    ".venv",
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


@dataclass(frozen=True)
class CleanupDecision:
    path: str
    action: str
    reason: str


def _norm(path: Path) -> str:
    return path.as_posix().lstrip("./")


def archive_destination(path: Path, run_id: str) -> Path:
    return Path("archive") / f"repo-cleanup-{run_id}" / _norm(path)


def classify_path(path: Path) -> CleanupDecision:
    p = _norm(path)
    name = path.name

    if name == ".DS_Store":
        return CleanupDecision(p, "delete", "macOS metadata")
    if name == "__pycache__" or p.endswith("/__pycache__"):
        return CleanupDecision(p, "delete", "Python bytecode cache")
    if p in {"reports/temp", "tmp/visual-qa"} or p.startswith("reports/temp/"):
        return CleanupDecision(p, "delete", "temporary generated artifacts")

    if p in ACTIVE_KEEP or any(p.startswith(k + "/") for k in ACTIVE_KEEP if not k.endswith(".py")):
        return CleanupDecision(p, "keep", "active runtime or protected project path")

    if p in {"organized", "output"} or p.startswith("organized/") or p.startswith("output/"):
        return CleanupDecision(p, "archive", "legacy generated output tree")
    if p in ROOT_ARCHIVE_FILES:
        return CleanupDecision(p, "archive", "legacy demo or merge script")
    if name.startswith("PR") and name.endswith(".zip"):
        return CleanupDecision(p, "archive", "raw NSE archive download at repo root")
    if name.endswith(("29102025.csv", "29102025.txt")):
        return CleanupDecision(p, "archive", "dated NSE source artifact at repo root")

    return CleanupDecision(p, "review", "not classified automatically")
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
./.venv/bin/python -m unittest tests.test_repo_cleanup -v
```

Expected: all tests pass.

---

### Task 2: Generate Cleanup Manifest Without Moving Files

**Files:**
- Modify: `scripts/maintenance/repo_cleanup.py`
- Create: `docs/repo-cleanup-manifest-2026-05-11.md`
- Test: `tests/test_repo_cleanup.py`

- [ ] **Step 1: Add failing test for manifest rendering**

Append to `tests/test_repo_cleanup.py`:

```python
from scripts.maintenance.repo_cleanup import render_manifest


class RepoCleanupManifestTests(unittest.TestCase):
    def test_render_manifest_groups_actions(self):
        decisions = [
            CleanupDecision("nse_agent.py", "keep", "active"),
            CleanupDecision("PR110526.zip", "archive", "download"),
            CleanupDecision(".DS_Store", "delete", "metadata"),
        ]
        text = render_manifest(decisions, run_id="20260511")
        self.assertIn("# Repo Cleanup Manifest - 20260511", text)
        self.assertIn("## Archive", text)
        self.assertIn("PR110526.zip", text)
        self.assertIn("## Delete", text)
        self.assertIn(".DS_Store", text)
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
./.venv/bin/python -m unittest tests.test_repo_cleanup -v
```

Expected: fail because `render_manifest` is not defined.

- [ ] **Step 3: Implement manifest rendering**

Add to `scripts/maintenance/repo_cleanup.py`:

```python
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
```

- [ ] **Step 4: Add CLI dry-run manifest command**

Add to `scripts/maintenance/repo_cleanup.py`:

```python
def scan_root(root: Path) -> list[CleanupDecision]:
    decisions: list[CleanupDecision] = []
    for path in sorted(root.iterdir(), key=lambda p: p.as_posix()):
        if path.name in {".git", ".venv"}:
            decisions.append(classify_path(Path(path.name)))
            continue
        decisions.append(classify_path(Path(path.name)))
    return decisions


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Manifest-first repository cleanup")
    parser.add_argument("--run-id", default="20260511")
    parser.add_argument("--write-manifest", action="store_true")
    args = parser.parse_args()

    decisions = scan_root(Path("."))
    text = render_manifest(decisions, args.run_id)
    if args.write_manifest:
        out = Path("docs") / f"repo-cleanup-manifest-{args.run_id[:4]}-{args.run_id[4:6]}-{args.run_id[6:]}.md"
        out.write_text(text + "\n", encoding="utf-8")
        print(out)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Run tests and generate manifest**

Run:

```bash
./.venv/bin/python -m unittest tests.test_repo_cleanup -v
./.venv/bin/python scripts/maintenance/repo_cleanup.py --run-id 20260511 --write-manifest
```

Expected: tests pass and `docs/repo-cleanup-manifest-2026-05-11.md` is created.

---

### Task 3: Execute Safe Delete Only

**Files:**
- Modify: `scripts/maintenance/repo_cleanup.py`
- Test: `tests/test_repo_cleanup.py`

- [ ] **Step 1: Add tests for dry-run and delete execution**

Append to `tests/test_repo_cleanup.py`:

```python
import tempfile
from scripts.maintenance.repo_cleanup import execute_decisions


class RepoCleanupExecutionTests(unittest.TestCase):
    def test_execute_delete_removes_safe_file(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            target = root / ".DS_Store"
            target.write_text("junk", encoding="utf-8")
            result = execute_decisions(root, [CleanupDecision(".DS_Store", "delete", "metadata")], dry_run=False)
            self.assertFalse(target.exists())
            self.assertEqual(result["deleted"], [".DS_Store"])

    def test_dry_run_does_not_remove_file(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            target = root / ".DS_Store"
            target.write_text("junk", encoding="utf-8")
            result = execute_decisions(root, [CleanupDecision(".DS_Store", "delete", "metadata")], dry_run=True)
            self.assertTrue(target.exists())
            self.assertEqual(result["would_delete"], [".DS_Store"])
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
./.venv/bin/python -m unittest tests.test_repo_cleanup -v
```

Expected: fail because `execute_decisions` is not defined.

- [ ] **Step 3: Implement safe delete execution**

Add to `scripts/maintenance/repo_cleanup.py`:

```python
def execute_decisions(root: Path, decisions: list[CleanupDecision], dry_run: bool = True) -> dict:
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
    return result
```

- [ ] **Step 4: Wire CLI flags**

Extend `main()` in `scripts/maintenance/repo_cleanup.py`:

```python
    parser.add_argument("--safe-delete", action="store_true")
    parser.add_argument("--dry-run", action="store_true", default=True)
```

After manifest rendering:

```python
    if args.safe_delete:
        result = execute_decisions(Path("."), decisions, dry_run=args.dry_run)
        print(result)
```

Use a separate edit to make `--apply` explicit rather than relying on `--dry-run=False`:

```python
    parser.add_argument("--apply", action="store_true", help="Apply safe delete actions")
```

Then call:

```python
        result = execute_decisions(Path("."), decisions, dry_run=not args.apply)
```

- [ ] **Step 5: Run dry run, then apply safe delete**

Run:

```bash
./.venv/bin/python -m unittest tests.test_repo_cleanup -v
./.venv/bin/python scripts/maintenance/repo_cleanup.py --run-id 20260511 --safe-delete
./.venv/bin/python scripts/maintenance/repo_cleanup.py --run-id 20260511 --safe-delete --apply
```

Expected: only `.DS_Store`, root/project `__pycache__`, and configured temp paths are removed. Nothing in `.venv` is touched.

---

### Task 4: Archive Root Artifacts And Legacy Output Trees

**Files:**
- Modify: `scripts/maintenance/repo_cleanup.py`
- Update: `docs/repo-cleanup-manifest-2026-05-11.md`
- Test: `tests/test_repo_cleanup.py`

- [ ] **Step 1: Add archive execution test**

Append to `tests/test_repo_cleanup.py`:

```python
class RepoCleanupArchiveTests(unittest.TestCase):
    def test_execute_archive_moves_file_preserving_path(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            target = root / "PR110526.zip"
            target.write_text("zip", encoding="utf-8")
            result = execute_decisions(
                root,
                [CleanupDecision("PR110526.zip", "archive", "download")],
                dry_run=False,
                run_id="20260511",
            )
            self.assertFalse(target.exists())
            archived = root / "archive/repo-cleanup-20260511/PR110526.zip"
            self.assertTrue(archived.exists())
            self.assertEqual(result["archived"], ["PR110526.zip"])
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
./.venv/bin/python -m unittest tests.test_repo_cleanup -v
```

Expected: fail because `execute_decisions` does not accept `run_id` or move archive files.

- [ ] **Step 3: Implement archive execution**

Change `execute_decisions` signature:

```python
def execute_decisions(
    root: Path,
    decisions: list[CleanupDecision],
    dry_run: bool = True,
    run_id: str = "20260511",
) -> dict:
```

Add inside the loop:

```python
        if decision.action == "archive":
            if dry_run:
                result["would_archive"].append(decision.path)
            elif src.exists():
                dst = root / archive_destination(Path(decision.path), run_id)
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dst))
                result["archived"].append(decision.path)
```

- [ ] **Step 4: Wire CLI archive flags**

Add:

```python
    parser.add_argument("--archive", action="store_true")
```

Call:

```python
    if args.archive:
        archive_decisions = [d for d in decisions if d.action == "archive"]
        result = execute_decisions(Path("."), archive_decisions, dry_run=not args.apply, run_id=args.run_id)
        print(result)
```

- [ ] **Step 5: Archive first-pass candidates**

Run:

```bash
./.venv/bin/python -m unittest tests.test_repo_cleanup -v
./.venv/bin/python scripts/maintenance/repo_cleanup.py --run-id 20260511 --archive
./.venv/bin/python scripts/maintenance/repo_cleanup.py --run-id 20260511 --archive --apply
```

Expected: root dated artifacts, root demo/merge R scripts, `organized/`, and `output/` move under `archive/repo-cleanup-20260511/`.

---

### Task 5: Package Company Intelligence With Compatibility Shims

**Files:**
- Create: `company_intelligence/`
- Move/copy logic from root `company_*.py`
- Modify root `company_*.py` into compatibility shims
- Test: existing `tests/test_company_*.py`

- [ ] **Step 1: Create package layout**

Create:

```text
company_intelligence/__init__.py
company_intelligence/search.py
company_intelligence/db.py
company_intelligence/website_indexer.py
company_intelligence/website_adapters.py
company_intelligence/command.py
company_intelligence/job.py
company_intelligence/xray_command.py
company_intelligence/analyze.py
company_intelligence/extract.py
company_intelligence/policy.py
company_intelligence/promote.py
company_intelligence/report.py
```

- [ ] **Step 2: Move code one module at a time**

For each root source:

```text
company_intelligence_search.py -> company_intelligence/search.py
company_intelligence_db.py -> company_intelligence/db.py
company_website_indexer.py -> company_intelligence/website_indexer.py
company_website_adapters.py -> company_intelligence/website_adapters.py
company_index_command.py -> company_intelligence/command.py
company_index_job.py -> company_intelligence/job.py
company_xray_command.py -> company_intelligence/xray_command.py
company_intelligence_analyze.py -> company_intelligence/analyze.py
company_intelligence_extract.py -> company_intelligence/extract.py
company_intelligence_policy.py -> company_intelligence/policy.py
company_intelligence_promote.py -> company_intelligence/promote.py
company_intelligence_report.py -> company_intelligence/report.py
```

- [ ] **Step 3: Replace root files with shims**

Example shim for `company_intelligence_search.py`:

```python
from company_intelligence.search import *  # noqa: F401,F403
```

Repeat for every moved root module.

- [ ] **Step 4: Update internal imports**

Search:

```bash
rg "company_intelligence_|company_website_|company_index_|company_xray_" .
```

Update package-internal imports to use `company_intelligence.<module>`. Keep external root shims intact until tests pass.

- [ ] **Step 5: Verify**

Run:

```bash
./.venv/bin/python -m unittest tests.test_company_intelligence_search tests.test_company_index_command tests.test_company_index_job tests.test_company_xray_command tests.test_company_website_indexer tests.test_company_website_adapters -v
```

Expected: all tests pass.

---

### Task 6: Package Voice Modules With Compatibility Shims

**Files:**
- Create: `voice/`
- Move/copy logic from root `voice_*.py`
- Modify root `voice_*.py` into compatibility shims
- Test: existing `tests/test_voice_*.py`

- [ ] **Step 1: Create package layout**

Create:

```text
voice/__init__.py
voice/capture.py
voice/command.py
voice/copilot.py
voice/live.py
voice/mode.py
voice/persona.py
voice/session.py
voice/synth.py
voice/transcribe.py
```

- [ ] **Step 2: Move code one module at a time**

Use this mapping:

```text
voice_capture.py -> voice/capture.py
voice_command.py -> voice/command.py
voice_copilot.py -> voice/copilot.py
voice_live.py -> voice/live.py
voice_mode.py -> voice/mode.py
voice_persona.py -> voice/persona.py
voice_session.py -> voice/session.py
voice_synth.py -> voice/synth.py
voice_transcribe.py -> voice/transcribe.py
```

- [ ] **Step 3: Replace root files with shims**

Example shim for `voice_synth.py`:

```python
from voice.synth import *  # noqa: F401,F403
```

- [ ] **Step 4: Update imports in runtime files**

Search:

```bash
rg "from voice_|import voice_" .
```

Update imports in `nse_agent.py` and related modules to the package path where safe. Leave shims so older tests still pass.

- [ ] **Step 5: Verify**

Run:

```bash
./.venv/bin/python -m unittest tests.test_voice_command tests.test_voice_copilot tests.test_voice_live tests.test_voice_mode tests.test_voice_synth -v
```

Expected: all tests pass.

---

### Task 7: Tighten Generated Artifact Ignore Rules

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Add generated artifact patterns**

Append:

```gitignore
# Generated report archives and local report outputs
reports/generated/
reports/generated_csv/
reports/temp/
reports/voice_briefings/
reports/**/latest_tmp/

# Local runtime caches
data/_nse_cookies.txt
data/_fno_cache/
data/_fii_dii_cache/
data/_insider_cache/
data/_macro_cache/
data/voice_sessions/
data/charts/
tmp/

# Root exchange download artifacts
PR*.zip
*29102025.csv
*29102025.txt
```

- [ ] **Step 2: Verify git status is cleaner**

Run:

```bash
git status --short
```

Expected: generated report/cache artifacts disappear from untracked output, while source files and docs remain visible.

---

### Task 8: Final Verification And Cleanup Report

**Files:**
- Create or update: `docs/repo-cleanup-manifest-2026-05-11.md`

- [ ] **Step 1: Run syntax checks**

Run:

```bash
./.venv/bin/python -m py_compile nse_agent.py terminal/agent.py terminal/tools.py terminal/reports.py
```

Expected: exit code 0.

- [ ] **Step 2: Run focused regression tests**

Run:

```bash
./.venv/bin/python -m unittest tests.test_strength_validation tests.test_terminal_intraday_fallback tests.test_voice_synth tests.test_repo_cleanup -v
```

Expected: all tests pass.

- [ ] **Step 3: Run package-specific tests if Tasks 5 and 6 were executed**

Run:

```bash
./.venv/bin/python -m unittest tests.test_company_intelligence_search tests.test_company_index_command tests.test_company_xray_command -v
./.venv/bin/python -m unittest tests.test_voice_command tests.test_voice_mode tests.test_voice_live tests.test_voice_synth -v
```

Expected: all tests pass.

- [ ] **Step 4: Run terminal smoke test**

Run:

```bash
./.venv/bin/python nse_agent.py --no-briefing --skip-readiness -q "/strength MANINDS THERMAX"
```

Expected: command prints a validated strength table and exits successfully.

- [ ] **Step 5: Update manifest with final result**

Append a final section to `docs/repo-cleanup-manifest-2026-05-11.md`:

```markdown
## Verification

- Syntax checks: passed
- Focused tests: passed
- Terminal smoke test: passed

## Notes

- First pass was archive-first.
- No domain data was permanently deleted.
- Compatibility shims remain for moved package modules.
```

---

## Execution Order

1. Task 1
2. Task 2
3. Task 3
4. Task 4
5. Stop and review `git status --short`
6. Task 5 only after archive-only cleanup is stable
7. Task 6 only after company package move is stable
8. Task 7
9. Task 8

Do not execute Tasks 5 and 6 in the same commit. They touch independent import surfaces and should be reviewed separately.
