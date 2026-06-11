from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path

from .config import load_generation_config, normalize_model_name
from .generator import generate_skill_cards
from .healer import llm_heal_card
from .healing_pass import heal_failed_jsonl
from .importer import import_skill_cards_jsonl
from .reaudit import reaudit_jsonl
from .seeds import selected_seed_examples


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate Agent Adda skill-store candidate cards.")
    parser.add_argument("--output-dir", default=str(Path("skill_store") / "generated"))
    parser.add_argument("--heal-failed-jsonl", default=None, help="Run LLM healing pass for test_failed cards in this JSONL.")
    parser.add_argument("--reaudit-jsonl", default=None, help="Quarantine and re-audit an existing generated/stored JSONL corpus.")
    parser.add_argument("--import-jsonl", default=None, help="Import generated skill cards from JSONL into agent_skills tables and embeddings.")
    parser.add_argument("--source-status", default="review_pending", help="Comma-separated statuses to import from --import-jsonl.")
    parser.add_argument("--target-status", default="validated", help="Status to assign before importing runtime-ready cards.")
    parser.add_argument("--embedding-provider", default="sentence-transformer", help="Embedding provider: sentence-transformer or fake.")
    parser.add_argument("--dsn", default=None, help="PostgreSQL DSN override for skill-store import.")
    parser.add_argument("--count", type=int, default=None)
    parser.add_argument("--target-count", type=int, default=None)
    parser.add_argument("--seed-ids", default=None, help="Comma-separated seed ids to generate instead of the default/expanded set.")
    parser.add_argument("--examples-per-seed", type=int, default=1, help="Number of deterministic seed variants to create for each --seed-ids entry.")
    parser.add_argument("--batch-size", type=int, default=15)
    parser.add_argument("--parallelism", type=int, default=10)
    parser.add_argument("--checkpoint-size", type=int, default=50)
    parser.add_argument("--model", default=None, help="Model override, e.g. gpt-4o. Alias gpt-40 maps to gpt-4o.")
    parser.add_argument("--dry-run", action="store_true", help="Use deterministic seed cards without calling OpenAI.")
    parser.add_argument(
        "--review-heal",
        action="store_true",
        help="Run generated cards through the local review gate; passing cards become review_pending, not runtime eligible.",
    )
    args = parser.parse_args(argv)
    cfg = load_generation_config()
    if args.model:
        cfg = replace(cfg, model=normalize_model_name(args.model))

    if args.heal_failed_jsonl:
        result = heal_failed_jsonl(
            Path(args.heal_failed_jsonl),
            Path(args.output_dir),
            healer=lambda card, findings: llm_heal_card(card, findings, config=cfg),
            max_attempts=3,
            parallelism=args.parallelism,
            checkpoint_size=args.checkpoint_size,
        )
        print(f"heal_source={args.heal_failed_jsonl}")
        print(f"model={cfg.model}")
        print(f"parallelism={args.parallelism}")
        print(f"total={result.total}")
        print(f"attempted={result.attempted}")
        print(f"healed={result.healed}")
        print(f"before_status_counts={dict(result.before_status_counts)}")
        print(f"after_status_counts={dict(result.after_status_counts)}")
        print(f"jsonl={result.jsonl_path}")
        return 0 if result.after_status_counts.get("test_failed", 0) == 0 else 2

    if args.reaudit_jsonl:
        result = reaudit_jsonl(
            Path(args.reaudit_jsonl),
            Path(args.output_dir),
            checkpoint_size=args.checkpoint_size,
        )
        print(f"reaudit_source={args.reaudit_jsonl}")
        print(f"total={result.total}")
        print(f"before_status_counts={dict(result.before_status_counts)}")
        print(f"after_status_counts={dict(result.after_status_counts)}")
        print(f"jsonl={result.jsonl_path}")
        return 0 if result.after_status_counts.get("test_failed", 0) == 0 else 2

    if args.import_jsonl:
        source_statuses = [status.strip() for status in args.source_status.split(",") if status.strip()]
        result = import_skill_cards_jsonl(
            Path(args.import_jsonl),
            source_statuses=source_statuses,
            target_status=args.target_status,
            dry_run=args.dry_run,
            dsn=args.dsn,
            embedding_provider_name=args.embedding_provider,
            batch_size=args.batch_size,
        )
        print(f"import_source={args.import_jsonl}")
        print(f"dry_run={result.dry_run}")
        print(f"source_status_counts={dict(result.source_status_counts)}")
        print(f"target_status={args.target_status}")
        print(f"selected={result.selected}")
        print(f"imported={result.imported}")
        print(f"skipped={result.skipped}")
        print(f"embedding_model={result.embedding_model}")
        if result.errors:
            print("errors:")
            for error in result.errors:
                print(f"- {error}")
        return 0 if not result.errors else 2

    generation_healer = None
    if args.review_heal and not args.dry_run:
        generation_healer = lambda card, findings: llm_heal_card(card, findings, config=cfg)
    seed_briefs = None
    if args.seed_ids:
        seed_ids = [seed_id.strip() for seed_id in args.seed_ids.split(",") if seed_id.strip()]
        seed_briefs = selected_seed_examples(seed_ids, args.examples_per_seed)

    result = generate_skill_cards(
        seed_briefs=seed_briefs,
        output_dir=Path(args.output_dir),
        dry_run=args.dry_run,
        count=args.count if seed_briefs is None else len(seed_briefs),
        target_count=args.target_count,
        batch_size=args.batch_size,
        parallelism=args.parallelism,
        config=cfg,
        review_heal=args.review_heal,
        healer=generation_healer,
    )
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
