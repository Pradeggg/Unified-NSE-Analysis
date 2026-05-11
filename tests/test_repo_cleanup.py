import tempfile
import unittest
from pathlib import Path

from scripts.maintenance.repo_cleanup import (
    CleanupDecision,
    archive_destination,
    classify_path,
    execute_decisions,
    render_manifest,
)


class RepoCleanupTests(unittest.TestCase):
    def test_classifies_safe_delete_generated_junk(self):
        ds_store = classify_path(Path(".DS_Store"))
        self.assertEqual(ds_store.action, "delete")
        self.assertEqual(ds_store.path, ".DS_Store")
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
        self.assertEqual(classify_path(Path(".venv")).action, "keep")
        self.assertEqual(classify_path(Path("terminal/tools.py")).action, "keep")
        self.assertEqual(classify_path(Path("data/sector_rotation_tracker.db")).action, "keep")
        self.assertEqual(classify_path(Path("reports/latest/sector_rotation.html")).action, "keep")

    def test_nested_raw_archives_are_review_not_first_pass_archive(self):
        decision = classify_path(Path("data/nse-raw/PR110526.zip"))
        self.assertEqual(decision.action, "review")

    def test_archive_destination_preserves_relative_path(self):
        dest = archive_destination(Path("reports/nse_analysis/old.html"), "20260511")
        self.assertEqual(dest, Path("archive/repo-cleanup-20260511/reports/nse_analysis/old.html"))

    def test_cleanup_decision_has_reason(self):
        decision = classify_path(Path("PR110526.zip"))
        self.assertIsInstance(decision, CleanupDecision)
        self.assertTrue(decision.reason)


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


class RepoCleanupExecutionTests(unittest.TestCase):
    def test_execute_delete_removes_safe_file(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            target = root / ".DS_Store"
            target.write_text("junk", encoding="utf-8")
            result = execute_decisions(
                root,
                [CleanupDecision(".DS_Store", "delete", "metadata")],
                dry_run=False,
            )
            self.assertFalse(target.exists())
            self.assertEqual(result["deleted"], [".DS_Store"])

    def test_dry_run_does_not_remove_file(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            target = root / ".DS_Store"
            target.write_text("junk", encoding="utf-8")
            result = execute_decisions(
                root,
                [CleanupDecision(".DS_Store", "delete", "metadata")],
                dry_run=True,
            )
            self.assertTrue(target.exists())
            self.assertEqual(result["would_delete"], [".DS_Store"])


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


if __name__ == "__main__":
    unittest.main()
