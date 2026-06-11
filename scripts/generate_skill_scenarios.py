#!/usr/bin/env python3
"""Generate offline Agent Adda Skill Store scenario cards."""
from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from skill_store.config import load_generation_config, normalize_model_name
from terminal.skills.generator import DEFAULT_GENERATED_DIR, available_domains, generate_skill_scenarios


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate Agent Adda Skill Store scenario cards.")
    parser.add_argument("--domain", choices=available_domains(), default=None)
    parser.add_argument("--count", type=int, default=None)
    parser.add_argument("--target-count", type=int, default=None)
    parser.add_argument("--output-dir", default=str(DEFAULT_GENERATED_DIR))
    parser.add_argument("--batch-size", type=int, default=15)
    parser.add_argument("--parallelism", type=int, default=10)
    parser.add_argument("--model", default=None, help="Model override. Alias gpt-40 maps to gpt-4o.")
    parser.add_argument("--dry-run", action="store_true", help="Generate deterministic seed cards without OpenAI.")
    parser.add_argument(
        "--review-heal",
        action="store_true",
        help="Run local review/heal gates; passing cards become review_pending, not runtime eligible.",
    )
    args = parser.parse_args(argv)

    cfg = load_generation_config()
    if args.model:
        cfg = replace(cfg, model=normalize_model_name(args.model))

    result = generate_skill_scenarios(
        domain=args.domain,
        count=args.count,
        target_count=args.target_count,
        dry_run=args.dry_run,
        output_dir=Path(args.output_dir),
        batch_size=args.batch_size,
        parallelism=args.parallelism,
        config=cfg,
        review_heal=args.review_heal,
    )
    print(f"domain={args.domain or 'all'}")
    print(f"target_count={args.target_count}")
    print(f"batch_size={args.batch_size}")
    print(f"parallelism={args.parallelism}")
    print(f"generated={result.generated}")
    print(f"model={result.model}")
    print(f"dry_run={result.dry_run}")
    print(f"jsonl={result.jsonl_path}")
    for path in result.yaml_paths:
        print(f"yaml={path}")
    if result.errors:
        print("errors:")
        for error in result.errors:
            print(f"- {error}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
