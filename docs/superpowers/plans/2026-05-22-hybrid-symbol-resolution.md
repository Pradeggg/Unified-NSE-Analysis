# Hybrid Symbol Resolution — Implementation Backlog

Date: 2026-05-22
Companion design: `docs/superpowers/specs/2026-05-22-hybrid-symbol-resolution-design.md`

This document is the implementation plan — concrete file paths, SQL, code skeletons, function signatures, test fixtures, rollback steps. The design doc explains *why*; this doc tells the engineer *exactly what to write*.

---

## Context: What's in `terminal/tools.py` today (the code we're replacing)

The resolver lives at `terminal/tools.py:689-820`. Key entry points:

| Function | Lines | Behaviour |
|---|---|---|
| `_lookup_key(s)` | ~671 | Lower-case, strip non-alphanumerics. `"HDFC Bank"` → `"hdfcbank"` |
| `_all_symbols_map()` | ~642-688 | Builds in-memory `{normalized_text: symbol}` dict from CSV master + manual aliases + sector-hint aliases. Cached on first call |
| `_resolve_local_symbol(query)` | 689-820 | The 5-tier lexical resolver — replaced wholesale |
| `resolve_symbol(query)` | 821-960 | Public entry — concept-token guard, then local, then NSE live API |
| `_SYMBOL_CONTEXT_TOKENS` | ~535 | Set of words that, when present, downgrade fuzzy matches |
| `_GENERIC_NAME_TOKENS` | ~545 | Words like "energy", "invest" that must never auto-substring-match |

`_all_symbols_map()` is the **source of truth for what gets indexed**. Phase 1 reuses it verbatim.

---

## Phase 1 — Trigram retriever (v1) — 2-3 days

### 1.1  Postgres migration

**File:** `postgres/migrations/20260523_symbol_resolution.sql` *(new)*

```sql
BEGIN;

CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS market.symbol_aliases (
    symbol      TEXT        NOT NULL,
    name        TEXT        NOT NULL,
    kind        TEXT        NOT NULL CHECK (kind IN (
                    'symbol','official','short','alias','sector_hint','manual'
                )),
    weight      REAL        NOT NULL DEFAULT 1.0,
    source      TEXT        NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (symbol, name, kind)
);

CREATE INDEX IF NOT EXISTS idx_symbol_aliases_name_trgm
    ON market.symbol_aliases USING gin (lower(name) gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_symbol_aliases_symbol
    ON market.symbol_aliases (symbol);

COMMENT ON TABLE  market.symbol_aliases  IS
    'Alias→symbol map for hybrid resolver. See plans/2026-05-22-hybrid-symbol-resolution.md';

COMMIT;
```

**Verification commands (in psql):**
```sql
\dx pg_trgm
\d market.symbol_aliases
SELECT indexname FROM pg_indexes WHERE tablename = 'symbol_aliases';
SELECT similarity('intraday signals', 'gna');          -- expect ~0.0–0.05
SELECT similarity('reliance', 'reliance industries');  -- expect ≥ 0.45
```

**Rollback:** `DROP TABLE market.symbol_aliases; DROP EXTENSION IF EXISTS pg_trgm;` — `pg_trgm` is safe to leave behind.

### 1.2  Bootstrap script

**File:** `scripts/seed_symbol_aliases.py` *(new)*

```python
"""Bulk-load `market.symbol_aliases` from the in-memory alias map.

Idempotent: ON CONFLICT DO UPDATE on (symbol, name, kind). Re-run any time
the in-memory map changes.

    python scripts/seed_symbol_aliases.py              # full reload
    python scripts/seed_symbol_aliases.py --dry-run    # print counts
"""
from __future__ import annotations

import argparse
import logging
from typing import Iterable

from terminal.postgres_tools import get_connection
from terminal.tools import _all_symbols_map, _lookup_key

log = logging.getLogger(__name__)

UPSERT = """
INSERT INTO market.symbol_aliases(symbol, name, kind, weight, source)
VALUES (%s, %s, %s, %s, %s)
ON CONFLICT (symbol, name, kind) DO UPDATE
SET weight = EXCLUDED.weight,
    source = EXCLUDED.source,
    updated_at = now()
"""

KIND_WEIGHTS = {
    "symbol":      0.95,
    "official":    1.00,
    "short":       0.85,
    "alias":       0.70,
    "sector_hint": 0.60,
    "manual":      0.90,
}


def _classify(name: str, symbol: str) -> str:
    if _lookup_key(name) == _lookup_key(symbol):
        return "symbol"
    if len(name.split()) >= 3:
        return "official"
    if len(name.split()) == 2:
        return "short"
    return "alias"


def iter_aliases() -> Iterable[tuple[str, str, str, float, str]]:
    seen: set[tuple[str, str, str]] = set()
    for name, symbol in _all_symbols_map().items():
        if not symbol or not name:
            continue
        kind = _classify(name, symbol)
        key = (symbol, name, kind)
        if key in seen:
            continue
        seen.add(key)
        yield symbol, name, kind, KIND_WEIGHTS[kind], "legacy_bootstrap"


def main(dry_run: bool = False) -> None:
    rows = list(iter_aliases())
    log.info("Prepared %d alias rows for upsert", len(rows))
    if dry_run:
        print(f"Would upsert {len(rows)} rows. Sample:")
        for r in rows[:5]:
            print(" ", r)
        return
    with get_connection() as conn, conn.cursor() as cur:
        cur.executemany(UPSERT, rows)
        conn.commit()
    log.info("Upserted %d aliases", len(rows))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    main(dry_run=p.parse_args().dry_run)
```

**Run order:**
```bash
psql $NSE_PG_URL -f postgres/migrations/20260523_symbol_resolution.sql
python scripts/seed_symbol_aliases.py --dry-run
python scripts/seed_symbol_aliases.py
```

Expected row count: ~4,000–6,000 (2,461 symbols × ~2 aliases avg).

### 1.3  Package skeleton

```
terminal/symbol_search/
├── __init__.py         # public: resolve(query, top_n=10) → ResolveResult
├── schema.py           # ResolveCandidate, ResolveResult, Confidence
├── dict_index.py       # tier-0 exact / normalized-exact (wraps _all_symbols_map)
├── trigram_index.py    # tier-1 pg_trgm query
├── fusion.py           # RRF + confidence bands
└── live_fallback.py    # NSE search API (moved from tools.py)
```

#### 1.3.1  `terminal/symbol_search/schema.py`

```python
"""Dataclasses shared by retrievers and fusion layer."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Confidence = Literal["exact", "high", "medium", "low", "none"]
Method     = Literal["dict", "trigram", "embedding", "live_api", "hybrid"]


@dataclass(frozen=True)
class ResolveCandidate:
    symbol:  str
    name:    str
    score:   float
    methods: tuple[Method, ...] = ()

    def merged_with(self, other: "ResolveCandidate") -> "ResolveCandidate":
        return ResolveCandidate(
            symbol=self.symbol,
            name=self.name if len(self.name) >= len(other.name) else other.name,
            score=max(self.score, other.score),
            methods=tuple(sorted(set(self.methods) | set(other.methods))),
        )


@dataclass
class ResolveResult:
    query:      str
    symbol:     str | None
    confidence: Confidence
    score:      float
    candidates: list[ResolveCandidate] = field(default_factory=list)
    method:     Method = "hybrid"
    matched:    str | None = None
    latency_ms: int = 0

    @property
    def needs_clarification(self) -> bool:
        return self.confidence in ("medium", "low")

    def to_legacy_dict(self) -> dict:
        legacy_confidence = {
            "exact":  "exact",
            "high":   "exact",
            "medium": "fuzzy",
            "low":    "fuzzy",
            "none":   "none",
        }[self.confidence]
        return {
            "symbol":     self.symbol,
            "confidence": legacy_confidence,
            "score":      self.score,
            "query":      self.query,
            "candidates": [c.symbol for c in self.candidates[:5]],
            "method":     self.method,
            "matched":    self.matched,
        }
```

#### 1.3.2  `terminal/symbol_search/dict_index.py`

```python
"""Tier-0 exact / normalized-exact lookup. Wraps terminal/tools._all_symbols_map."""
from __future__ import annotations

import re
from functools import lru_cache

from .schema import ResolveCandidate

_NORM_RE = re.compile(r"[^a-z0-9]+")


def _norm(s: str) -> str:
    return _NORM_RE.sub("", s.lower())


@lru_cache(maxsize=1)
def _index() -> dict[str, tuple[str, str]]:
    from terminal.tools import _all_symbols_map
    out: dict[str, tuple[str, str]] = {}
    for display, symbol in _all_symbols_map().items():
        k = _norm(display)
        if k and k not in out:
            out[k] = (display, symbol)
    return out


def lookup(query: str) -> list[ResolveCandidate]:
    k = _norm(query)
    if not k:
        return []
    hit = _index().get(k)
    if not hit:
        return []
    display, symbol = hit
    return [ResolveCandidate(symbol=symbol, name=display, score=1.0, methods=("dict",))]
```

#### 1.3.3  `terminal/symbol_search/trigram_index.py`

```python
"""Tier-1 Postgres pg_trgm retriever."""
from __future__ import annotations

import logging
from contextlib import contextmanager

from terminal.postgres_tools import get_connection
from .schema import ResolveCandidate

log = logging.getLogger(__name__)

SIMILARITY_THRESHOLD  = 0.30
MID_WORD_REJECT_BELOW = 0.25

QUERY = """
WITH s AS (
    SELECT  symbol, name, kind, weight,
            similarity(lower(name), lower(%(q)s)) AS sim
    FROM    market.symbol_aliases
    WHERE   lower(name) %% lower(%(q)s)
)
SELECT symbol, name, kind, weight, sim
FROM   s
WHERE  sim >= %(threshold)s
ORDER  BY sim * weight DESC, length(name) ASC
LIMIT  %(limit)s
"""


def lookup(query: str, top_n: int = 10) -> list[ResolveCandidate]:
    if not query or not query.strip():
        return []
    try:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(QUERY, dict(q=query, threshold=MID_WORD_REJECT_BELOW, limit=top_n))
            rows = cur.fetchall()
    except Exception as exc:
        log.warning("trigram lookup failed for %r: %s", query, exc)
        return []

    by_symbol: dict[str, ResolveCandidate] = {}
    for symbol, name, _kind, weight, sim in rows:
        score = float(sim) * float(weight)
        cand = ResolveCandidate(symbol=symbol, name=name, score=score, methods=("trigram",))
        if symbol in by_symbol:
            by_symbol[symbol] = by_symbol[symbol].merged_with(cand)
        else:
            by_symbol[symbol] = cand
    return sorted(by_symbol.values(), key=lambda c: c.score, reverse=True)[:top_n]


@contextmanager
def session_threshold(value: float):
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SET pg_trgm.similarity_threshold = %s", (value,))
        try:
            yield
        finally:
            cur.execute("RESET pg_trgm.similarity_threshold")
```

#### 1.3.4  `terminal/symbol_search/fusion.py`

```python
"""Reciprocal-rank fusion + confidence bands."""
from __future__ import annotations

from collections import defaultdict

from .schema import ResolveCandidate, Confidence

RRF_K = 60

BAND_HIGH   = 0.045
BAND_MEDIUM = 0.025
BAND_LOW    = 0.010


def reciprocal_rank_fusion(lists: list[list[ResolveCandidate]]) -> list[ResolveCandidate]:
    scores:  defaultdict[str, float]     = defaultdict(float)
    best:    dict[str, ResolveCandidate] = {}
    for lst in lists:
        for rank, cand in enumerate(lst, start=1):
            scores[cand.symbol] += 1.0 / (RRF_K + rank)
            if cand.symbol not in best or cand.score > best[cand.symbol].score:
                best[cand.symbol] = cand

    fused: list[ResolveCandidate] = []
    for sym, s in scores.items():
        b = best[sym]
        methods = set(b.methods)
        for lst in lists:
            for c in lst:
                if c.symbol == sym:
                    methods.update(c.methods)
        fused.append(ResolveCandidate(
            symbol=sym, name=b.name, score=s, methods=tuple(sorted(methods))))
    return sorted(fused, key=lambda c: c.score, reverse=True)


def confidence_band(score: float, dict_hit: bool) -> Confidence:
    if dict_hit:
        return "exact"
    if score >= BAND_HIGH:
        return "high"
    if score >= BAND_MEDIUM:
        return "medium"
    if score >= BAND_LOW:
        return "low"
    return "none"
```

#### 1.3.5  `terminal/symbol_search/live_fallback.py`

Extract the existing `requests.get("https://nseindia.com/api/search/autocomplete...")` block from `tools.py::resolve_symbol` into a standalone module. Behaviour unchanged. Signature:

```python
def lookup_nse_live(query: str, timeout: float = 4.0) -> list[ResolveCandidate]: ...
```

#### 1.3.6  `terminal/symbol_search/__init__.py`

```python
"""Hybrid symbol resolver — Phase 1: dict + trigram + live fallback."""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from . import dict_index, trigram_index, live_fallback
from .fusion import reciprocal_rank_fusion, confidence_band
from .schema import ResolveResult, ResolveCandidate

log = logging.getLogger(__name__)
TELEMETRY_PATH = Path("logs/symbol_resolution.jsonl")


def resolve(query: str, top_n: int = 10, use_live: bool = True) -> ResolveResult:
    t0 = time.perf_counter()
    q = (query or "").strip()
    if not q:
        return ResolveResult(query=query, symbol=None, confidence="none", score=0.0)

    dict_hits    = dict_index.lookup(q)
    trigram_hits = trigram_index.lookup(q, top_n=top_n)

    fused = reciprocal_rank_fusion([dict_hits, trigram_hits])
    dict_hit = bool(dict_hits)

    if not fused and use_live:
        live = live_fallback.lookup_nse_live(q)
        if live:
            fused = reciprocal_rank_fusion([live])

    if not fused:
        result = ResolveResult(
            query=query, symbol=None, confidence="none", score=0.0,
            candidates=[], method="hybrid",
            latency_ms=int((time.perf_counter() - t0) * 1000),
        )
    else:
        top  = fused[0]
        conf = confidence_band(top.score, dict_hit)
        result = ResolveResult(
            query=query,
            symbol=top.symbol if conf != "none" else None,
            confidence=conf,
            score=top.score,
            candidates=fused[:top_n],
            method=("dict" if dict_hit and len(top.methods) == 1 else "hybrid"),
            matched=f"{top.symbol} — {top.name}",
            latency_ms=int((time.perf_counter() - t0) * 1000),
        )

    _emit_telemetry(result)
    return result


def _emit_telemetry(r: ResolveResult) -> None:
    try:
        TELEMETRY_PATH.parent.mkdir(parents=True, exist_ok=True)
        with TELEMETRY_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps({
                "query":      r.query,
                "winner":     r.symbol,
                "method":     r.method,
                "score":      round(r.score, 4),
                "confidence": r.confidence,
                "candidates": [
                    {"sym": c.symbol, "score": round(c.score, 4), "methods": list(c.methods)}
                    for c in r.candidates[:5]
                ],
                "latency_ms": r.latency_ms,
            }) + "\n")
    except Exception:
        pass     # never let telemetry break resolution
```

### 1.4  Wire into existing callers

**Patch:** `terminal/tools.py::resolve_symbol`

Replace the body from line ~862 (`local = _resolve_local_symbol(q)` onward) with:

```python
    from .symbol_search import resolve as _hybrid_resolve
    result = _hybrid_resolve(query, use_live=True)
    return result.to_legacy_dict()
```

The concept-token guard block ABOVE this point stays — those tokens should be rejected before the hybrid resolver is invoked.

**Patch:** `terminal/tools.py::_resolve_local_symbol`

Delete the contains-match block (lines ~722–734) and the dual SequenceMatcher tier (lines ~736–770). Keep the empty-query guard, the `_GENERIC_NAME_TOKENS` rejection, and the `_SYMBOL_CONTEXT_TOKENS` rejection.

**Patch:** `terminal/agent.py::_primary_symbol_query`

Replace the two `confidence in {"exact", "near-match"}` checks with a score gate:

```python
phrase = _leading_company_phrase(raw_query)
if phrase:
    try:
        resolved = resolve_symbol(phrase)
        if resolved.get("symbol") and float(resolved.get("score") or 0) >= 0.85:
            return resolved["symbol"]
    except Exception:
        pass
```

### 1.5  Test fixtures

**File:** `tests/fixtures/symbol_resolution/in_vocab.jsonl` *(new)*

200 entries seeded from:
- Random sample of 100 symbols from `data/data_summary.json` (query = `symbol.lower()`)
- 50 multi-word company names from `_all_symbols_map()`
- 50 queries from session-store turns (`SELECT user_message FROM turns WHERE user_message ~ '\b(RELIANCE|TCS|HDFC|...)\b' LIMIT 50`)

**File:** `tests/fixtures/symbol_resolution/adversarial.jsonl` *(new)*

50 cases the resolver MUST handle correctly. Sample:

```jsonl
{"query": "intraday signals",      "expected": null,         "note": "GNA bug — mid-word substring"}
{"query": "market action",         "expected": null,         "note": "FMNL bug — mid-word substring"}
{"query": "Premier Energies",      "expected": "PREMIERENE", "note": "single-word prefix collision"}
{"query": "Premier",               "expected": null,         "note": "ambiguous single-word, refuse"}
{"query": "State Bank of India",   "expected": "SBIN",       "note": "preposition phrase"}
{"query": "of India",              "expected": null,         "note": "preposition fragment"}
{"query": "Bharat Petroleum",      "expected": "BPCL",       "note": "prefix collision (Bharat → many)"}
{"query": "NIFTY MIDCAP 100",      "expected": null,         "note": "index phrase, not a ticker"}
{"query": "MIDCPNIFTY",            "expected": "MIDCPNIFTY", "note": "derivative symbol is valid"}
{"query": "HDFC",                  "expected": null,         "note": "ETF/holding-co ambiguity"}
{"query": "HDFC Bank",             "expected": "HDFCBANK",   "note": "disambiguation by suffix"}
{"query": "Mahindra and Mahindra", "expected": "M&M",        "note": "connective in canonical name"}
{"query": "Larsen and Toubro",     "expected": "LT",         "note": "and-vs-&"}
{"query": "Larsen & Toubro",       "expected": "LT",         "note": "and-vs-&"}
{"query": "L&T",                   "expected": "LT",         "note": "short alias"}
```

### 1.6  Test file

**File:** `tests/test_hybrid_symbol_resolution.py` *(new)*

```python
"""Eval-driven tests for the hybrid symbol resolver."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from terminal.symbol_search import resolve

FIXTURES = Path(__file__).parent / "fixtures" / "symbol_resolution"


def _load(name: str) -> list[dict]:
    with (FIXTURES / name).open() as f:
        return [json.loads(line) for line in f if line.strip()]


@pytest.fixture(scope="session")
def in_vocab():
    return _load("in_vocab.jsonl")


@pytest.fixture(scope="session")
def adversarial():
    return _load("adversarial.jsonl")


def test_in_vocab_top1_recall(in_vocab):
    hits = sum(1 for case in in_vocab
               if resolve(case["query"], use_live=False).symbol == case["expected"])
    recall = hits / len(in_vocab)
    assert recall >= 0.98, f"in-vocab top-1 recall {recall:.3f} < 0.98"


def test_adversarial_false_symbol_rate(adversarial):
    negatives = [c for c in adversarial if c["expected"] is None]
    leaks     = [c for c in negatives
                 if resolve(c["query"], use_live=False).symbol is not None]
    leak_rate = len(leaks) / len(negatives)
    assert leak_rate <= 0.02, (
        f"false-symbol leak rate {leak_rate:.3f} > 0.02\nleaks: {leaks[:5]}"
    )


def test_adversarial_positive_cases(adversarial):
    misses = [c for c in adversarial
              if c["expected"] is not None
              and resolve(c["query"], use_live=False).symbol != c["expected"]]
    assert not misses, f"adversarial positive misses:\n{misses[:5]}"


def test_known_regressions():
    assert resolve("intraday signals", use_live=False).symbol is None
    assert resolve("market action",    use_live=False).symbol is None
    assert resolve("Premier Energies", use_live=False).symbol == "PREMIERENE"
    assert resolve("State Bank of India", use_live=False).symbol == "SBIN"
    assert resolve("HDFC Bank", use_live=False).symbol == "HDFCBANK"


def test_latency_p95(in_vocab):
    timings = []
    for case in in_vocab:
        t0 = time.perf_counter()
        resolve(case["query"], use_live=False)
        timings.append((time.perf_counter() - t0) * 1000)
    timings.sort()
    p95 = timings[int(len(timings) * 0.95)]
    assert p95 <= 80.0, f"p95 latency {p95:.1f}ms > 80ms"
```

### 1.7  Existing test compatibility

`tests/test_terminal_symbol_resolution.py` has 47 tests asserting against the legacy `{"symbol", "confidence", "query", "candidates"}` shape. The shim `ResolveResult.to_legacy_dict()` preserves all four keys.

```bash
python -m pytest tests/test_terminal_symbol_resolution.py -v
```

All must pass without edits. If a `confidence == "fuzzy"` caller breaks because the new resolver promotes a match to `"high"`/`"exact"`, document the diff and update the test expectations explicitly — do not silently change behaviour.

### 1.8  Telemetry aggregator (optional in v1)

**File:** `scripts/symbol_resolution_summary.py` *(new)*

```python
"""Daily aggregation of the symbol-resolution telemetry."""
import json, statistics
from collections import Counter
from pathlib import Path

p = Path("logs/symbol_resolution.jsonl")
records = [json.loads(line) for line in p.read_text().splitlines() if line.strip()]
latencies = [r["latency_ms"] for r in records]
by_method = Counter(r["method"] for r in records)
by_band   = Counter(r["confidence"] for r in records)
unresolved = Counter(r["query"] for r in records if r["winner"] is None)

print(f"Total resolves: {len(records)}")
print(f"Latency p50/p95/p99: "
      f"{statistics.median(latencies):.0f}/"
      f"{statistics.quantiles(latencies, n=20)[18]:.0f}/"
      f"{max(latencies):.0f} ms")
print(f"By method: {by_method.most_common()}")
print(f"By confidence band: {by_band.most_common()}")
print(f"Top-20 unresolved queries (alias backlog):")
for q, n in unresolved.most_common(20):
    print(f"  {n:4d}  {q!r}")
```

### 1.9  Exit criteria for Phase 1

All must be green before merge:

1. `pytest tests/test_terminal_symbol_resolution.py` — 47/47 pass unchanged.
2. `pytest tests/test_hybrid_symbol_resolution.py` — all 5 tests pass:
   - in-vocab top-1 recall ≥ 0.98
   - adversarial false-symbol leak ≤ 0.02
   - adversarial positive cases all hit
   - 5 known-regression spot checks pass
   - p95 latency ≤ 80ms
3. `pytest tests/test_mtf_intent_router.py tests/test_terminal_agent_market_prompt.py tests/test_confidence.py` — no regression (target: 141/141 from current baseline).
4. Schema migration applied cleanly on a fresh DB; rollback verified.
5. `scripts/seed_symbol_aliases.py` is idempotent — runs twice without errors or row inflation.
6. Live e2e: `python nse_agent.py --query "scan TRENT for intraday signals"` produces TRENT-scoped output.

### 1.10  Rollback procedure

```bash
git revert <merge-commit>                              # restore terminal/tools.py logic
psql $NSE_PG_URL -c "DROP TABLE market.symbol_aliases" # optional cleanup
# pg_trgm extension can stay — no harm if unused
```

The legacy `_resolve_local_symbol` path is preserved in git history at the commit immediately before merge; cherry-picking it back is a clean revert.

---

## Phase 2 — Semantic embeddings (v2) — 3-4 days, deferred

### 2.1  Migration extension

**File:** `postgres/migrations/20260530_symbol_embeddings.sql` *(new)*

```sql
BEGIN;

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS market.symbol_embeddings (
    symbol      TEXT         PRIMARY KEY,
    embedding   vector(384)  NOT NULL,
    text_used   TEXT         NOT NULL,
    model       TEXT         NOT NULL,
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_symbol_embeddings_hnsw
    ON market.symbol_embeddings USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

COMMIT;
```

### 2.2  Encoder script

**File:** `scripts/refresh_symbol_embeddings.py` *(new)*

```python
"""Encode and persist embeddings for every symbol. Idempotent.

Re-encodes only rows whose (text_used, model) drifted from the last write.
Run weekly and after every NSE/BSE master refresh.

    python scripts/refresh_symbol_embeddings.py
    python scripts/refresh_symbol_embeddings.py --force-all
"""
from __future__ import annotations

import argparse
import logging

from terminal.postgres_tools import get_connection
from terminal.tools import _all_symbols_map

log = logging.getLogger(__name__)
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


def canonical_text(symbol: str, names: list[str], sector: str | None) -> str:
    aliases = ", ".join(sorted(set(names))[:8])
    sector_part = f" ({sector} sector)" if sector else ""
    return f"{symbol} — {names[0] if names else symbol}{sector_part}; aliases: {aliases}"


def main(force: bool = False) -> None:
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(MODEL_NAME)

    by_symbol: dict[str, list[str]] = {}
    for name, sym in _all_symbols_map().items():
        by_symbol.setdefault(sym, []).append(name)

    with get_connection() as conn, conn.cursor() as cur:
        if not force:
            cur.execute("SELECT symbol, text_used, model FROM market.symbol_embeddings")
            existing = {row[0]: (row[1], row[2]) for row in cur.fetchall()}
        else:
            existing = {}

        to_encode: list[tuple[str, str]] = []
        for sym, names in by_symbol.items():
            text = canonical_text(sym, names, sector=None)        # sector hookup is v2.1
            if existing.get(sym) != (text, MODEL_NAME):
                to_encode.append((sym, text))

        log.info("Encoding %d / %d symbols", len(to_encode), len(by_symbol))
        if not to_encode:
            return

        texts = [t for _, t in to_encode]
        vecs  = model.encode(texts, normalize_embeddings=True, show_progress_bar=True)

        cur.executemany(
            """
            INSERT INTO market.symbol_embeddings(symbol, embedding, text_used, model)
            VALUES (%s, %s::vector, %s, %s)
            ON CONFLICT (symbol) DO UPDATE
            SET embedding  = EXCLUDED.embedding,
                text_used  = EXCLUDED.text_used,
                model      = EXCLUDED.model,
                updated_at = now()
            """,
            [(sym, vec.tolist(), text, MODEL_NAME)
             for (sym, text), vec in zip(to_encode, vecs)],
        )
        conn.commit()
    log.info("Done.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("--force-all", dest="force", action="store_true")
    main(force=p.parse_args().force)
```

### 2.3  Embedding retriever

**File:** `terminal/symbol_search/embedding_index.py` *(new)*

```python
"""Tier-2 pgvector retriever. Lazy-loads the encoder; soft-imports the package."""
from __future__ import annotations

import logging
from functools import lru_cache

from terminal.postgres_tools import get_connection
from .schema import ResolveCandidate

log = logging.getLogger(__name__)
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


@lru_cache(maxsize=1)
def _model():
    try:
        from sentence_transformers import SentenceTransformer
        return SentenceTransformer(MODEL_NAME)
    except Exception as exc:
        log.info("sentence-transformers unavailable, embedding tier disabled: %s", exc)
        return None


QUERY = """
SELECT symbol, text_used, 1 - (embedding <=> %(qvec)s::vector) AS score
FROM   market.symbol_embeddings
ORDER  BY embedding <=> %(qvec)s::vector
LIMIT  %(limit)s
"""


def lookup(query: str, top_n: int = 10) -> list[ResolveCandidate]:
    m = _model()
    if m is None or not query.strip():
        return []
    qvec = m.encode([query], normalize_embeddings=True)[0].tolist()
    try:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(QUERY, dict(qvec=qvec, limit=top_n))
            rows = cur.fetchall()
    except Exception as exc:
        log.warning("embedding lookup failed for %r: %s", query, exc)
        return []
    return [
        ResolveCandidate(symbol=sym, name=text or sym, score=float(score), methods=("embedding",))
        for sym, text, score in rows
        if float(score) >= 0.25     # cosine floor
    ]
```

### 2.4  Wire into resolver

In `terminal/symbol_search/__init__.py`:

```python
from . import embedding_index
...
embedding_hits = embedding_index.lookup(q, top_n=top_n)
fused = reciprocal_rank_fusion([dict_hits, trigram_hits, embedding_hits])
```

### 2.5  Confidence-band recalibration

Re-run the in-vocab + adversarial eval sets after embedding tier lands. Update `BAND_HIGH/MEDIUM/LOW` constants if the fused-score distribution shifts. Pin the calibration with a regression test:

```python
def test_confidence_bands_calibrated():
    from terminal.symbol_search.fusion import BAND_HIGH, BAND_MEDIUM, BAND_LOW
    # Tuned 2026-05-30 against the eval set; bump deliberately if you update.
    assert (BAND_HIGH, BAND_MEDIUM, BAND_LOW) == (0.045, 0.025, 0.010)
```

### 2.6  Exit criteria for Phase 2

1. Out-of-vocab eval (`tests/fixtures/symbol_resolution/out_of_vocab.jsonl`, 100 paraphrase queries) — top-1 recall ≥ v1 + 5pp.
2. In-vocab top-1 ≥ 98% (no regression).
3. Memory at steady state: model load ≤ 100MB additional RSS.
4. Cold start added latency ≤ 3s (one-time encoder warm-up).
5. Soft import works: removing `sentence-transformers` falls back to v1 without errors.

### 2.7  Operational notes for v2

- `sentence-transformers` adds ~250MB of transitive deps (torch CPU). Pin in `requirements.txt` with `--index-url=https://download.pytorch.org/whl/cpu` to avoid CUDA wheels.
- Encoder warmup is lazy on first `resolve()`; consider pre-warming in `nse_agent.py` startup if cold-start latency matters.
- pgvector ≥ 0.5 ships HNSW indexing; on older Postgres, fall back to `ivfflat WITH (lists = 100)`.

---

## Phase 3 — Long tail (optional, no commitment)

Triggered only if v2 telemetry shows:
- top-1 < 95% on a meaningful slice for 4+ consecutive weeks, OR
- clarification-panel rate > 5% sustained.

Work items:
- Cross-encoder rerank (`cross-encoder/ms-marco-MiniLM-L-6-v2`) over fused top-10 when `|top1 − top2| < 0.005`.
- Fine-tune the bi-encoder on (alias, canonical) pairs scraped from telemetry; ship as `nse-mini-l6-v2-ft`.
- Extend `kind` taxonomy with `business_description`, `sector_lead`, `index_proxy` to support paraphrase queries ("largest two-wheeler maker" → BAJAJ-AUTO).

---

## Cross-Phase: How this composes with the routing review

The hybrid resolver returns a continuous `score`. `terminal/confidence.py::score_intent` already gates the clarification panel on intent score; we extend `score_intent` to multiply in `1 - 0.3 × (1 - symbol_score)` whenever a symbol slot is required by the intent (`intraday_setup`, `mtf_single`, `stock_brief`, …). Low-confidence resolutions naturally drive intent confidence below the 0.65 CLARIFY threshold and emit the existing non-blocking clarification panel — no new UX surface.

This is the bridge from the routing-architecture review:

| Routing-review phase | This work's contribution |
|---|---|
| Phase 1 (LLM fallback router) | Hybrid resolver's `low`/`none` confidence is one signal that should escalate to the LLM router. |
| Phase 2 (embedding intent classifier) | Same encoder (`all-MiniLM-L6-v2`) can be reused for intent classification — single model, two tables. |
| Phase 3 (LLM slot-filling) | When the intent classifier picks the intent but the symbol resolver returns `low`, LLM slot-filling owns the disambiguation. |

---

## Glossary

| Term | Meaning in this doc |
|---|---|
| pg_trgm | PostgreSQL trigram-similarity extension. Splits strings into 3-char windows and scores Jaccard overlap. |
| pgvector | PostgreSQL extension storing dense vectors with HNSW / IVFFlat indexes for nearest-neighbour search. |
| RRF | Reciprocal Rank Fusion — combine ranked lists by summing `1/(k + rank)`. Robust to score-scale mismatch. |
| HNSW | Hierarchical Navigable Small World — graph-based ANN index. State of the art for cosine search on a few hundred thousand vectors. |
| Confidence band | Discrete bucket on a continuous score: `exact` / `high` / `medium` / `low` / `none`. Drives UX decisions. |
| `_lookup_key` | The existing `terminal/tools.py` normalizer: lowercase, strip non-alphanumerics. Foundation of the dict tier. |
| `_all_symbols_map` | The existing in-memory `{display_name: symbol}` dict. Stays as the source of truth; we mirror it into Postgres. |
