"""Synthetic router dataset generation (query -> expected tool/workflow).

Design goals:
- Deterministic, no-LLM, safe-by-default.
- Uses curated workflow input_patterns as gold labels when available.
- Optionally uses recent real KB queries + current BM25 top-1 hit as a weak label.
- Adds hard negatives (BM25 near-misses) and parameterized variants (SYMBOL/date).
"""

from __future__ import annotations

import json
import random
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import yaml

from ._common import DATA_DIR, ROOT, safe_filename
from .skills_registry import get_registry


WORKFLOWS_YAML = ROOT / "knowledge_base" / "entries" / "workflows.yaml"
QUERY_LOG_DB = DATA_DIR / "knowledge_base" / "query_log.db"
DEFAULT_SYMBOLS = ["RELIANCE", "HDFCBANK", "TCS", "INFY", "SBIN"]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_utc_now() -> str:
    return _utc_now().isoformat().replace("+00:00", "Z")


def _read_workflows() -> list[dict[str, Any]]:
    if not WORKFLOWS_YAML.exists():
        return []
    docs = list(yaml.safe_load_all(WORKFLOWS_YAML.read_text(encoding="utf-8", errors="ignore")))
    out: list[dict[str, Any]] = []
    for d in docs:
        if isinstance(d, list):
            out.extend([x for x in d if isinstance(x, dict)])
        elif isinstance(d, dict):
            out.append(d)
    # only entries that look like workflows
    return [w for w in out if w.get("id") and (w.get("cli") or w.get("input_patterns"))]


def _recent_kb_queries(*, days: int = 30) -> list[dict[str, Any]]:
    if not QUERY_LOG_DB.exists():
        return []
    since = _utc_now() - timedelta(days=days)
    since_iso = since.isoformat(timespec="seconds").replace("+00:00", "Z")

    conn = sqlite3.connect(str(QUERY_LOG_DB))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT ts, query, caller, session_id
            FROM query_log
            WHERE ts >= ?
            ORDER BY ts DESC
            """,
            (since_iso,),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def _param_variants(base: str, *, symbols: list[str], date_str: str | None) -> list[str]:
    """Expand placeholders like SYMBOL/{SYMBOL}/{symbol} and optional date."""
    b = " ".join((base or "").strip().split())
    if not b:
        return []
    # 1) Placeholder expansion
    expanded: set[str] = {b}
    placeholders = ["SYMBOL", "{SYMBOL}", "{symbol}", "<SYMBOL>"]
    if any(p in b for p in placeholders):
        expanded = set()
        for sym in symbols:
            s = b
            for p in placeholders:
                s = s.replace(p, sym)
            expanded.add(s)

    # 2) Optional date attachment (useful for report-style intents)
    if date_str:
        with_date = set()
        for x in expanded:
            with_date.add(x)
            if any(k in x.lower() for k in ("morning", "midday", "report", "publish", "deploy", "validate")):
                with_date.add(f"{x} {date_str}")
                with_date.add(f"{x} ({date_str})")
        expanded = with_date

    return [s for s in expanded if s and len(s) <= 200]


def _variants(base: str, *, symbols: list[str], date_str: str | None) -> list[str]:
    """Cheap deterministic paraphrase set (rule-based), after parameter expansion."""
    out: set[str] = set()
    for b in _param_variants(base, symbols=symbols, date_str=date_str):
        out |= {
            b,
            b.lower(),
            b.upper() if len(b) < 40 else b,
            f"agent adda {b}",
            f"please {b}",
            f"{b} now",
            f"can you {b}",
            f"{b} (today)",
        }
    # Replace a few common phrases.
    rep = [
        ("run", "execute"),
        ("refresh", "rebuild"),
        ("generate", "build"),
        ("chart", "plot"),
        ("validate", "verify"),
        ("midday", "mid-day"),
        ("eod", "end of day"),
    ]
    for a, c in rep:
        if a in b.lower():
            out.add(re.sub(rf"\\b{re.escape(a)}\\b", c, b, flags=re.IGNORECASE))
    return [s for s in out if s and len(s) <= 200]


@dataclass(frozen=True)
class SynthRow:
    query: str
    expected_id: str
    expected_cli: str
    expected_category: str
    expected_tags: list[str]
    label_source: str
    base: str
    created_at_utc: str
    candidates: list[dict[str, Any]] | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "query": self.query,
            "expected_id": self.expected_id,
            "expected_cli": self.expected_cli,
            "expected_category": self.expected_category,
            "expected_tags": self.expected_tags,
            "label_source": self.label_source,
            "base": self.base,
            "created_at_utc": self.created_at_utc,
        }
        if self.candidates:
            d["task_type"] = "rank"
            d["candidates"] = self.candidates
        return d


def _entry_candidate(e: dict[str, Any], *, is_correct: bool) -> dict[str, Any]:
    return {
        "id": str(e.get("id") or ""),
        "title": str(e.get("title") or e.get("id") or ""),
        "category": str(e.get("category") or ""),
        "cli": str(e.get("cli") or ""),
        "tags": list(e.get("tags") or []),
        "is_correct": bool(is_correct),
    }


def _hard_negatives(
    *,
    reg,
    query: str,
    expected_id: str,
    n: int,
) -> list[dict[str, Any]]:
    """Pick hard negatives as BM25 near-misses for the same query."""
    if n <= 0:
        return []
    hits = reg.search(query, k=max(6, n + 3))
    out: list[dict[str, Any]] = []
    for h in hits:
        e = h.get("entry") or {}
        eid = str(e.get("id") or "")
        if not eid or eid == expected_id:
            continue
        out.append(_entry_candidate(e, is_correct=False))
        if len(out) >= n:
            break
    return out


def generate_synth_dataset(
    *,
    mode: str = "both",
    days: int = 30,
    max_rows: int = 300,
    seed: int = 42,
    symbols: list[str] | None = None,
    date_str: str | None = None,
    hard_negatives: int = 2,
) -> list[dict[str, Any]]:
    """Generate synthetic router examples.

    mode:
      - workflows: only curated workflow patterns (strong labels)
      - querylog: recent KB queries + current BM25 top-1 (weak labels)
      - both: mix of both
    """
    rng = random.Random(seed)
    created = _iso_utc_now()
    rows: list[SynthRow] = []
    syms = symbols or list(DEFAULT_SYMBOLS)

    if mode in ("workflows", "both"):
        reg = get_registry()
        for wf in _read_workflows():
            wid = str(wf.get("id") or "").strip()
            cli = str(wf.get("cli") or "").strip()
            cat = str(wf.get("category") or "workflow").strip()
            tags = list(wf.get("tags") or [])
            pats = wf.get("input_patterns") or []
            for p in pats:
                for v in _variants(str(p), symbols=syms, date_str=date_str):
                    candidates = None
                    if hard_negatives > 0:
                        candidates = [
                            _entry_candidate(
                                {"id": wid, "title": wf.get("title") or wid, "category": cat, "cli": cli, "tags": tags},
                                is_correct=True,
                            ),
                            *_hard_negatives(reg=reg, query=v, expected_id=wid, n=hard_negatives),
                        ]
                    rows.append(
                        SynthRow(
                            query=v,
                            expected_id=wid,
                            expected_cli=cli,
                            expected_category=cat,
                            expected_tags=tags,
                            label_source="workflow_input_patterns",
                            base=str(p),
                            created_at_utc=created,
                            candidates=candidates,
                        )
                    )

    if mode in ("querylog", "both"):
        reg = get_registry()
        for q in _recent_kb_queries(days=days):
            base_q = str(q.get("query") or "").strip()
            if not base_q:
                continue
            hit = (reg.search(base_q, k=1) or [None])[0]
            if not hit:
                continue
            e = hit["entry"]
            exp_id = str(e.get("id") or "").strip()
            exp_cli = str(e.get("cli") or "").strip()
            exp_cat = str(e.get("category") or "").strip()
            exp_tags = list(e.get("tags") or [])
            for v in _variants(base_q, symbols=syms, date_str=date_str):
                candidates = None
                if hard_negatives > 0 and exp_id:
                    candidates = [
                        _entry_candidate(e, is_correct=True),
                        *_hard_negatives(reg=reg, query=v, expected_id=exp_id, n=hard_negatives),
                    ]
                rows.append(
                    SynthRow(
                        query=v,
                        expected_id=exp_id,
                        expected_cli=exp_cli,
                        expected_category=exp_cat,
                        expected_tags=exp_tags,
                        label_source="kb_querylog_bm25_top1",
                        base=base_q,
                        created_at_utc=created,
                        candidates=candidates,
                    )
                )

    # Dedup and sample
    dedup: dict[str, SynthRow] = {}
    for r in rows:
        key = f"{r.query.lower()}|{r.expected_id}"
        dedup.setdefault(key, r)

    unique = list(dedup.values())
    rng.shuffle(unique)
    unique = unique[: max_rows]
    return [r.to_dict() for r in unique]


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
            n += 1
    return n


def default_out_path(
    *,
    mode: str,
    days: int,
    max_rows: int,
    seed: int,
    hard_negatives: int = 0,
    date_str: str | None = None,
) -> Path:
    parts = [mode, f"d{days}", f"n{max_rows}", f"s{seed}"]
    if hard_negatives:
        parts.append(f"hn{hard_negatives}")
    if date_str:
        parts.append(f"dt{date_str}")
    label = safe_filename("_".join(parts))
    return DATA_DIR / "knowledge_base" / f"router_synth_{label}.jsonl"


__all__ = [
    "generate_synth_dataset",
    "write_jsonl",
    "default_out_path",
]
