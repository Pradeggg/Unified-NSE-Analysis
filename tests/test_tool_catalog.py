"""AA-CC-9: tests for the tool-catalog dump + hallucinated-tool guard.

Verifies:
* The on-disk ``terminal/tools.schema.json`` is in sync with the live
  ``TOOL_REGISTRY`` (CI sync check).
* The catalog payload has the expected shape and a non-trivial tool count.
* Every catalog tool name appears in ``TOOL_REGISTRY`` and vice-versa.
* A handful of well-known tools (spot check) carry the right description
  / parameters / signature data.
* The ``--check`` mode of the dump script exits 0 against the synced
  artifact and non-zero after a forced drift.
* A small ``is_hallucinated_tool`` helper rejects unknown names.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.maintenance.dump_tool_catalog import (  # noqa: E402
    build_catalog,
    render_catalog,
)
from terminal.tools import TOOL_REGISTRY  # noqa: E402


CATALOG_PATH = ROOT / "terminal" / "tools.schema.json"


def is_hallucinated_tool(name: str) -> bool:
    """Return True if ``name`` is not a registered tool.

    A tiny helper so tests (and the future evidence-gate) can reject
    LLM-emitted tool calls that don't exist in the registry.
    """
    return name not in TOOL_REGISTRY


class TestCatalogShape:
    def test_catalog_payload_has_expected_top_level_keys(self) -> None:
        catalog = build_catalog()
        assert catalog.keys() == {"schema_version", "tool_count", "tools"}
        assert catalog["schema_version"] == 1
        assert catalog["tool_count"] == len(catalog["tools"])

    def test_catalog_lists_every_registered_tool(self) -> None:
        catalog = build_catalog()
        names_in_catalog = {tool["name"] for tool in catalog["tools"]}
        assert names_in_catalog == set(TOOL_REGISTRY.keys())

    def test_catalog_has_nontrivial_tool_count(self) -> None:
        catalog = build_catalog()
        # Sanity floor — if this drops the registry has lost ground.
        assert catalog["tool_count"] >= 100

    def test_catalog_tools_carry_required_fields(self) -> None:
        catalog = build_catalog()
        required = {"name", "description", "parameters", "signature",
                    "return", "doc_summary", "source"}
        for entry in catalog["tools"]:
            assert required.issubset(entry.keys()), entry["name"]
            assert isinstance(entry["description"], str) and entry["description"]
            assert isinstance(entry["parameters"], dict)


class TestCatalogSpotChecks:
    def test_get_live_quote_entry(self) -> None:
        catalog = build_catalog()
        by_name = {t["name"]: t for t in catalog["tools"]}
        assert "get_live_quote" in by_name
        entry = by_name["get_live_quote"]
        assert "symbol" in entry["parameters"].get("properties", {})
        assert "symbol" in entry["parameters"].get("required", [])
        assert entry["source"].startswith("terminal/")

    def test_resolve_symbol_entry(self) -> None:
        catalog = build_catalog()
        by_name = {t["name"]: t for t in catalog["tools"]}
        assert "resolve_symbol" in by_name
        entry = by_name["resolve_symbol"]
        # Always returns a dict per the registry contract.
        assert entry["signature"]


class TestCatalogOnDisk:
    def test_catalog_file_exists(self) -> None:
        assert CATALOG_PATH.exists(), (
            "terminal/tools.schema.json missing — run "
            "scripts/maintenance/dump_tool_catalog.py to regenerate."
        )

    def test_on_disk_matches_live_registry(self) -> None:
        """Sync check — fails when the artifact drifts from TOOL_REGISTRY."""
        expected = render_catalog(build_catalog())
        actual = CATALOG_PATH.read_text(encoding="utf-8")
        assert actual == expected, (
            "terminal/tools.schema.json is out of date — re-run "
            "scripts/maintenance/dump_tool_catalog.py and commit."
        )

    def test_on_disk_is_valid_json(self) -> None:
        payload = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        assert isinstance(payload, dict)
        assert payload["schema_version"] == 1
        assert isinstance(payload["tools"], list)


class TestDumpScriptCli:
    def test_check_mode_succeeds_on_synced_artifact(self) -> None:
        proc = subprocess.run(
            [sys.executable, "scripts/maintenance/dump_tool_catalog.py",
             "--check"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert proc.returncode == 0, proc.stderr or proc.stdout

    def test_check_mode_fails_on_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            drifted = Path(tmpdir) / "tools.schema.json"
            drifted.write_text(
                json.dumps({"schema_version": 1, "tool_count": 0, "tools": []}),
                encoding="utf-8",
            )
            proc = subprocess.run(
                [sys.executable, "scripts/maintenance/dump_tool_catalog.py",
                 "--check", "--out", str(drifted)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=120,
            )
            assert proc.returncode == 1
            assert "out of sync" in proc.stderr.lower()

    def test_check_mode_reports_missing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            missing = Path(tmpdir) / "does_not_exist.json"
            proc = subprocess.run(
                [sys.executable, "scripts/maintenance/dump_tool_catalog.py",
                 "--check", "--out", str(missing)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=120,
            )
            assert proc.returncode == 2
            assert "missing" in proc.stderr.lower()


class TestHallucinatedToolGuard:
    def test_known_tools_are_not_hallucinated(self) -> None:
        for name in ("get_live_quote", "resolve_symbol",
                     "get_market_breadth"):
            assert not is_hallucinated_tool(name)

    def test_unknown_tool_names_are_flagged(self) -> None:
        # The exact example from the AA-CC-9 backlog spec.
        assert is_hallucinated_tool("get_tomorrow_close")
        assert is_hallucinated_tool("predict_nifty")
        assert is_hallucinated_tool("")
        assert is_hallucinated_tool("RESOLVE_SYMBOL")  # case-sensitive


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
