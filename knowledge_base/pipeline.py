"""End-to-end orchestrator: fetch → chunk → qa → embed → index → query."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from ._common import CHUNKS_PATH, MANIFEST_PATH, QA_PATH, now_iso
from .chunker import chunk_document
from .fetcher import fetch_all
from .qa_generator import generate_qa_for_chunk
from .vector_store import KBVectorStore


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def _append_jsonl(path: Path, rows: Iterable[dict]) -> None:
    with path.open("a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def _existing_chunk_ids() -> set[str]:
    return {r["chunk_id"] for r in _read_jsonl(CHUNKS_PATH) if "chunk_id" in r}


def _existing_qa_ids() -> set[str]:
    return {r["qa_id"] for r in _read_jsonl(QA_PATH) if "qa_id" in r}


def run_pipeline(
    *,
    categories: list[str] | None = None,
    tiers: list[int] | None = None,
    source_ids: list[str] | None = None,
    max_pdfs_per_hub: int = 3,
    do_fetch: bool = True,
    do_chunk: bool = True,
    do_qa: bool = True,
    do_index: bool = True,
) -> dict:
    """Run the full pipeline. Each stage is independently skippable."""
    summary = {"started": now_iso(), "fetch": 0, "chunk": 0, "qa": 0, "indexed_chunks": 0, "indexed_qa": 0}

    # ── 1. fetch ───────────────────────────────────────────────────────
    if do_fetch:
        fetched = fetch_all(
            categories=categories, tiers=tiers, source_ids=source_ids,
            max_pdfs_per_hub=max_pdfs_per_hub,
        )
        summary["fetch"] = sum(1 for r in fetched if r.get("status") == "ok")
        print(f"  fetched {summary['fetch']} artefacts")

    # ── 2. chunk ───────────────────────────────────────────────────────
    new_chunks: list[dict] = []
    if do_chunk:
        seen = _existing_chunk_ids()
        manifest_rows = _read_jsonl(MANIFEST_PATH)
        # Optional source filter
        if source_ids:
            sids = {s.upper() for s in source_ids}
            manifest_rows = [r for r in manifest_rows if (r.get("source_id") or "").upper() in sids]
        for row in manifest_rows:
            if row.get("status") != "ok":
                continue
            for ch in chunk_document(row):
                if ch["chunk_id"] in seen:
                    continue
                seen.add(ch["chunk_id"])
                new_chunks.append(ch)
        _append_jsonl(CHUNKS_PATH, new_chunks)
        summary["chunk"] = len(new_chunks)
        print(f"  chunked {summary['chunk']} new chunks")

    # ── 3. Q&A generation ─────────────────────────────────────────────
    new_qa: list[dict] = []
    if do_qa:
        chunks_to_qa = new_chunks if new_chunks else _read_jsonl(CHUNKS_PATH)
        seen_qa = _existing_qa_ids()
        for ch in chunks_to_qa:
            for pair in generate_qa_for_chunk(ch):
                if pair["qa_id"] in seen_qa:
                    continue
                seen_qa.add(pair["qa_id"])
                new_qa.append(pair)
        _append_jsonl(QA_PATH, new_qa)
        summary["qa"] = len(new_qa)
        print(f"  generated {summary['qa']} QA pairs")

    # ── 4. embed + index ──────────────────────────────────────────────
    if do_index:
        store = KBVectorStore()
        chunks_to_embed = new_chunks if new_chunks else _read_jsonl(CHUNKS_PATH)
        qa_to_embed     = new_qa if new_qa else _read_jsonl(QA_PATH)
        summary["indexed_chunks"] = store.upsert_chunks(chunks_to_embed)
        summary["indexed_qa"]     = store.upsert_qa(qa_to_embed)
        summary["totals"]         = store.stats()
        print(f"  indexed {summary['indexed_chunks']} chunks + {summary['indexed_qa']} QA — totals: {summary['totals']}")

    summary["finished"] = now_iso()
    return summary


def query_kb(query: str, *, k: int = 6, collection: str = "qa") -> list[dict]:
    """Semantic search the KB."""
    store = KBVectorStore()
    return store.query(query, k=k, collection=collection)
