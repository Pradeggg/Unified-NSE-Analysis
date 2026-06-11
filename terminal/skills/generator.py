"""Compatibility wrapper for offline Skill Store scenario generation."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

from skill_store.config import GenerationConfig
from skill_store.generator import GenerationResult, generate_skill_cards
from skill_store.schema_catalog import SchemaCatalog
from skill_store.seeds import SeedBrief, default_seed_briefs, expanded_seed_briefs


DEFAULT_GENERATED_DIR = Path("data") / "skill_store" / "generated"


def generate_skill_scenarios(
    *,
    domain: str | None = None,
    count: int | None = None,
    target_count: int | None = None,
    dry_run: bool = False,
    output_dir: Path | str = DEFAULT_GENERATED_DIR,
    batch_size: int = 15,
    parallelism: int = 10,
    config: GenerationConfig | None = None,
    schema_catalog: SchemaCatalog | None = None,
    review_heal: bool = False,
) -> GenerationResult:
    """Generate untrusted candidate skill cards for offline review.

    This keeps the backlog's `terminal.skills.generator` surface stable while
    delegating the actual schema-aware generation to the top-level
    `skill_store` package.
    """
    seed_briefs = _seed_briefs_for_domain(domain, count=count, target_count=target_count)
    effective_count = len(seed_briefs) if seed_briefs is not None else count
    return generate_skill_cards(
        seed_briefs=seed_briefs,
        output_dir=output_dir,
        dry_run=dry_run,
        count=effective_count,
        target_count=None if seed_briefs is not None else target_count,
        batch_size=batch_size,
        parallelism=parallelism,
        config=config,
        schema_catalog=schema_catalog,
        review_heal=review_heal,
    )


def available_domains() -> tuple[str, ...]:
    return tuple(sorted({seed.domain for seed in default_seed_briefs()}))


def _seed_briefs_for_domain(
    domain: str | None,
    *,
    count: int | None,
    target_count: int | None,
) -> list[SeedBrief] | None:
    if not domain:
        return None
    normalized = domain.strip()
    domains = set(available_domains())
    if normalized not in domains:
        raise ValueError(f"unknown domain '{normalized}'. Available domains: {', '.join(sorted(domains))}")

    requested = count if count is not None else target_count
    if requested is None:
        return [seed for seed in default_seed_briefs() if seed.domain == normalized]
    if requested <= 0:
        return []

    return _expanded_domain_seeds(normalized, requested)


def _expanded_domain_seeds(domain: str, requested: int) -> list[SeedBrief]:
    selected: list[SeedBrief] = []
    search_size = max(50, requested * max(1, len(default_seed_briefs())) * 2)
    while len(selected) < requested:
        selected = [seed for seed in expanded_seed_briefs(search_size) if seed.domain == domain]
        search_size *= 2
    return selected[:requested]
