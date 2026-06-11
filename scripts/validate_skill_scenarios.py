#!/usr/bin/env python3
"""Validate generated Agent Adda Skill Store scenario cards."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terminal.skills.scenario_validation import DEFAULT_VALIDATED_DIR, validate_skill_scenarios


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate generated Skill Store scenario cards.")
    parser.add_argument("--input-jsonl", required=True)
    parser.add_argument("--output-dir", default=str(DEFAULT_VALIDATED_DIR))
    parser.add_argument("--max-attempts", type=int, default=3)
    args = parser.parse_args(argv)

    result = validate_skill_scenarios(
        Path(args.input_jsonl),
        output_dir=Path(args.output_dir),
        max_attempts=args.max_attempts,
    )
    print(f"total={result.total}")
    for status, count in sorted(result.status_counts.items()):
        print(f"{status}={count}")
    print(f"jsonl={result.jsonl_path}")
    print(f"report={result.report_path}")
    return 0 if result.failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
