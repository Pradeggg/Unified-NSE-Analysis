"""Load financial_sources_registry.json and iterate flat (source, hub) tuples."""
from __future__ import annotations

import json
from typing import Iterator

from ._common import REGISTRY_PATH


def load_registry() -> dict:
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def iter_sources(
    categories: list[str] | None = None,
    tiers: list[int] | None = None,
    source_ids: list[str] | None = None,
) -> Iterator[dict]:
    """Yield flat hub records ready for the fetcher.

    Each yielded dict:
        {
            "category": "credit_rating_agencies",
            "tier": 2,
            "source_id": "CRISIL",
            "source_name": "CRISIL Ratings (S&P Global)",
            "hub_label": "Rating Rationales (search)" | "landing",
            "url": "https://...",
            "doc_types": ["pdf"],
        }
    """
    reg = load_registry()
    cat_filter = set(categories) if categories else None
    src_filter = set(s.upper() for s in source_ids) if source_ids else None

    for cat, body in reg.items():
        if cat.startswith("_"):
            continue
        if cat_filter and cat not in cat_filter:
            continue
        tier = body.get("tier")
        if tiers and tier not in tiers:
            continue
        for src in body.get("sources", []):
            sid = (src.get("id") or "").upper()
            if src_filter and sid not in src_filter:
                continue
            doc_types = src.get("doc_types") or ["html"]
            base = {
                "category":    cat,
                "tier":        tier,
                "source_id":   sid,
                "source_name": src.get("name", sid),
                "doc_types":   doc_types,
            }
            # Always include the landing page first.
            if src.get("landing"):
                yield {**base, "hub_label": "landing", "url": src["landing"]}
            for hub in src.get("key_pdf_hubs", []) or []:
                yield {**base, "hub_label": hub.get("label", "hub"), "url": hub["url"]}
