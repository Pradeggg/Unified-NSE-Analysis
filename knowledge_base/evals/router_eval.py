"""Router evaluation on synthetic datasets.

Evaluates a baseline router using the existing BM25 `SkillsRegistry.search`.

Datasets supported (JSONL, one object per line):
- "classification" style: {query, expected_id, ...}
- "rank" style: additionally contains `candidates` (list of {id,is_correct,...})

This is offline-safe (no LLM, no network).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..skills_registry import get_registry


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if isinstance(obj, dict):
                out.append(obj)
    return out


def _mrr(rank: int | None) -> float:
    return 0.0 if not rank else 1.0 / float(rank)


@dataclass(frozen=True)
class EvalResult:
    n: int
    top1_acc: float
    top3_acc: float
    top5_acc: float
    mrr: float
    restricted_top1_acc: float
    restricted_mrr: float
    by_label_source: dict[str, dict[str, float]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "n": self.n,
            "top1_acc": self.top1_acc,
            "top3_acc": self.top3_acc,
            "top5_acc": self.top5_acc,
            "mrr": self.mrr,
            "restricted_top1_acc": self.restricted_top1_acc,
            "restricted_mrr": self.restricted_mrr,
            "by_label_source": self.by_label_source,
        }


def eval_router_bm25(
    dataset_path: Path,
    *,
    k: int = 20,
) -> EvalResult:
    reg = get_registry()
    rows = _read_jsonl(dataset_path)

    n = 0
    top1 = top3 = top5 = 0
    mrr_sum = 0.0

    r_top1 = 0
    r_mrr_sum = 0.0
    r_n = 0

    # label_source -> counters
    per: dict[str, dict[str, float]] = {}

    for row in rows:
        q = str(row.get("query") or "").strip()
        exp = str(row.get("expected_id") or "").strip()
        if not q or not exp:
            continue

        n += 1
        label_source = str(row.get("label_source") or "unknown")
        p = per.setdefault(label_source, {"n": 0.0, "top1": 0.0, "mrr": 0.0})
        p["n"] += 1.0

        hits = reg.search(q, k=k)
        ranked_ids = [str(h.get("entry", {}).get("id") or "") for h in hits]

        rank = None
        for i, rid in enumerate(ranked_ids, start=1):
            if rid == exp:
                rank = i
                break

        if rank == 1:
            top1 += 1
            p["top1"] += 1.0
        if rank is not None and rank <= 3:
            top3 += 1
        if rank is not None and rank <= 5:
            top5 += 1
        mrr_sum += _mrr(rank)
        p["mrr"] += _mrr(rank)

        # Restricted evaluation when we have candidates
        cands = row.get("candidates")
        if isinstance(cands, list) and cands:
            ids = [str(c.get("id") or "") for c in cands if isinstance(c, dict)]
            ids = [x for x in ids if x]
            if exp in ids and ids:
                r_n += 1
                # Use full-search ranking to score restricted candidate set.
                pos: dict[str, int] = {}
                for i, rid in enumerate(ranked_ids, start=1):
                    if rid in ids:
                        pos[rid] = i
                # Candidate not in top-k => treat as missing rank.
                restricted_ranked = sorted(ids, key=lambda cid: pos.get(cid, 10_000))
                r_rank = 1 + restricted_ranked.index(exp) if exp in restricted_ranked else None
                if r_rank == 1:
                    r_top1 += 1
                r_mrr_sum += _mrr(r_rank)

    def rate(x: float, denom: float) -> float:
        return 0.0 if denom <= 0 else round(x / denom, 4)

    by_label_source: dict[str, dict[str, float]] = {}
    for src, c in per.items():
        denom = float(c.get("n", 0.0))
        by_label_source[src] = {
            "n": int(denom),
            "top1_acc": rate(float(c.get("top1", 0.0)), denom),
            "mrr": rate(float(c.get("mrr", 0.0)), denom),
        }

    return EvalResult(
        n=n,
        top1_acc=rate(float(top1), float(n)),
        top3_acc=rate(float(top3), float(n)),
        top5_acc=rate(float(top5), float(n)),
        mrr=rate(float(mrr_sum), float(n)),
        restricted_top1_acc=rate(float(r_top1), float(r_n)),
        restricted_mrr=rate(float(r_mrr_sum), float(r_n)),
        by_label_source=by_label_source,
    )


def format_eval_text(result: EvalResult) -> str:
    lines: list[str] = []
    lines.append("Router Eval (BM25 baseline)")
    lines.append(f"  n={result.n}")
    lines.append(f"  top1={result.top1_acc}  top3={result.top3_acc}  top5={result.top5_acc}  mrr={result.mrr}")
    if result.restricted_top1_acc or result.restricted_mrr:
        lines.append(
            f"  restricted_top1={result.restricted_top1_acc}  restricted_mrr={result.restricted_mrr}"
        )
    if result.by_label_source:
        lines.append("  by_label_source:")
        for src, d in sorted(result.by_label_source.items(), key=lambda kv: kv[0]):
            lines.append(f"    - {src}: n={d.get('n')} top1={d.get('top1_acc')} mrr={d.get('mrr')}")
    return "\n".join(lines)


__all__ = ["eval_router_bm25", "format_eval_text", "EvalResult"]

