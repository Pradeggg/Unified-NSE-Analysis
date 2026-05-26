#!/usr/bin/env python3
"""AA-CC-9: Emit a JSON Schema inventory of every registered NSE-Agent tool.

Walks :data:`terminal.tools.TOOL_REGISTRY`, augments each entry with the
tool function's call signature, return annotation, source file/line and
docstring summary, and writes the consolidated catalog to
``terminal/tools.schema.json``.

Downstream consumers:

* MCP server exposure (whenever Agent Adda grows an MCP surface).
* Hallucinated-tool detection — the agent / tests can load the catalog
  to verify any LLM-emitted ``tool_use`` name is in the registry.
* Audit of what the LLM can see vs. internal helpers.

Usage::

    # Regenerate the catalog (writes terminal/tools.schema.json):
    python scripts/maintenance/dump_tool_catalog.py

    # CI check: fail if the on-disk catalog is stale:
    python scripts/maintenance/dump_tool_catalog.py --check

    # Write to a custom path / stdout:
    python scripts/maintenance/dump_tool_catalog.py --out -
"""
from __future__ import annotations

import argparse
import inspect
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terminal.tools import TOOL_REGISTRY  # noqa: E402


DEFAULT_OUT = ROOT / "terminal" / "tools.schema.json"


def _docstring_summary(fn: Any) -> str:
    """Return the first paragraph of a callable's docstring, trimmed."""
    doc = inspect.getdoc(fn) or ""
    if not doc:
        return ""
    # Stop at the first blank line so multi-paragraph docstrings don't
    # leak args/returns blocks into the catalog summary.
    summary = doc.split("\n\n", 1)[0].strip()
    return " ".join(summary.split())


def _signature_repr(fn: Any) -> str:
    try:
        return str(inspect.signature(fn))
    except (TypeError, ValueError):
        return ""


def _return_annotation(fn: Any) -> str:
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return ""
    ann = sig.return_annotation
    if ann is inspect.Signature.empty:
        return ""
    return getattr(ann, "__name__", repr(ann))


def _source_location(fn: Any) -> str:
    """Return ``relative/path.py:LINE`` for the callable, or ''."""
    try:
        path = Path(inspect.getsourcefile(fn) or "")
        line = inspect.getsourcelines(fn)[1]
    except (TypeError, OSError):
        return ""
    try:
        rel = path.relative_to(ROOT)
    except ValueError:
        rel = path
    return f"{rel.as_posix()}:{line}"


def build_catalog() -> dict:
    """Build the catalog payload from the live TOOL_REGISTRY."""
    tools: list[dict] = []
    for name in sorted(TOOL_REGISTRY.keys()):
        entry = TOOL_REGISTRY[name]
        fn, description, params = entry[0], entry[1], entry[2]
        tools.append({
            "name": name,
            "description": description,
            "parameters": params,
            "signature": _signature_repr(fn),
            "return": _return_annotation(fn),
            "doc_summary": _docstring_summary(fn),
            "source": _source_location(fn),
        })
    return {
        "schema_version": 1,
        "tool_count": len(tools),
        "tools": tools,
    }


def render_catalog(catalog: dict) -> str:
    """Render the catalog as deterministic JSON for diffing."""
    return json.dumps(catalog, indent=2, sort_keys=False, ensure_ascii=False) + "\n"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Emit / verify the Agent Adda tool catalog (AA-CC-9).",
    )
    parser.add_argument(
        "--out",
        default=str(DEFAULT_OUT),
        help=(
            "Output path for the catalog JSON. Use '-' for stdout. "
            f"Defaults to {DEFAULT_OUT.relative_to(ROOT)}."
        ),
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help=(
            "Exit non-zero if the on-disk catalog at --out differs from "
            "what would be generated. Used in CI to keep the artifact in sync."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    catalog = build_catalog()
    rendered = render_catalog(catalog)

    if args.out == "-":
        sys.stdout.write(rendered)
        return 0

    out_path = Path(args.out)
    if args.check:
        if not out_path.exists():
            sys.stderr.write(
                f"ERROR: catalog file is missing at {out_path}. "
                "Run dump_tool_catalog.py to regenerate.\n"
            )
            return 2
        on_disk = out_path.read_text(encoding="utf-8")
        if on_disk != rendered:
            sys.stderr.write(
                f"ERROR: {out_path} is out of sync with TOOL_REGISTRY. "
                "Re-run scripts/maintenance/dump_tool_catalog.py and commit "
                "the result.\n"
            )
            return 1
        sys.stdout.write(
            f"OK: {out_path.relative_to(ROOT)} matches the live registry "
            f"({catalog['tool_count']} tools).\n"
        )
        return 0

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(rendered, encoding="utf-8")
    sys.stdout.write(
        f"Wrote {out_path.relative_to(ROOT)} "
        f"({catalog['tool_count']} tools).\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
