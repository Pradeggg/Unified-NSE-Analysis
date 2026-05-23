# Hybrid Symbol Resolution — Design

Date: 2026-05-22
Scope: `terminal/tools.py::resolve_symbol`, `terminal/entity_resolution.py`, `terminal/agent.py::_primary_symbol_query`, new `terminal/symbol_search/` package, Postgres extensions.

## Goal

Replace the current purely-lexical symbol resolver with a **hybrid retriever** that combines exact dictionary lookup, Postgres trigram similarity, optional sentence-embedding cosine similarity, and confidence-aware result selection. The new resolver should eliminate the class of "mid-word coincidence" false positives (e.g. `"intraday signals" → GNA`) and the brittle Ratcliff-Obershelp ratios that today's `difflib.SequenceMatcher` produces, while preserving sub-100ms latency on the happy path. The v1 rollout introduces no new external services: PostgreSQL remains the only runtime dependency, and the resolver degrades to dict-only if the trigram table or extension is unavailable.

## Current Baseline (2026-05-22)

### Resolution stack (top to bottom)
1. **Concept-token guard** in `resolve_symbol()` — a hand-curated `_CONCEPT_TOKENS` set rejecting screener words ("RSI", "PE", "FII", …) as non-tickers.
2. **`_resolve_local_symbol()`** — five tiers, all lexical:
   1. Exact dict lookup against `_all_symbols_map()` (symbol → symbol, name → symbol, alias → symbol).
   2. Normalised exact (lowercase, strip non-alphanumerics) — `_lookup_key()`.
   3. **Substring containment** in either direction (`q ⊂ key` OR `key ⊂ q`). Patched 2026-05-22 to require whole-word match for short keys (<6 chars) to prevent `"signals" → GNA`.
   4. `difflib.SequenceMatcher` ratio ≥ 0.84, with a stricter prefix-anchored typo branch (ratio ≥ 0.94, prefix-8 match) for short ticker inputs.
   5. Returns `{"symbol", "confidence" ∈ {exact, fuzzy, none}, "candidates"}`.
3. **NSE live search API** — `nseindia.com/api/search/autocomplete` — as a network fallback.
4. **`_primary_symbol_query()`** in `terminal/agent.py` (called from the keyword router) — picks one canonical symbol from the (candidates, symbol_candidates, raw_query) triple. Today: leading-company-phrase → post-preposition phrase → uppercase-run extraction → first candidate. Patched 2026-05-22 to stop returning a raw post-preposition phrase when a better explicit candidate exists.

### Where the lexical-only approach fails

| Failure mode | Example | Why lexical can't fix it cleanly |
|---|---|---|
| Mid-word substring | `"intraday signals" → GNA` | `"GNA"` is a real substring of `"intradaySIGNAls"`; only whole-word guards or semantic dissimilarity rejects it |
| Out-of-vocab paraphrase | `"the bank that owns ICICI Lombard" → ?` | No alias in the map; SequenceMatcher score is 0 |
| Sector-by-description | `"largest two-wheeler maker" → BAJAJ-AUTO` | No lexical overlap with company name |
| Phonetic typo | `"Wokhardt" → WOCKPHARMA` | SequenceMatcher ratio < 0.84; not in alias list |
| Tokenisation drift | `"Larsen & Toubro" vs "Larsen and Toubro" vs "L&T"` | Each requires a hand-curated alias today |
| Co-occurring ticker words | `"scan SBIN intraday signals"` | Today: ambiguity between `SBIN` (explicit) and the post-preposition phrase. Patched today, but the underlying brittleness remains |

### Bugs fixed reactively in the past 30 days
- `"Premier Energies" → PREMEXPLN` (single-word prefix collision)
- `"State Bank of India" → INDIA` (preposition-phrase extractor)
- `"NIFTY MIDCAP 100" → MIDCPNIFTY` validation gate
- `"intraday signals" → GNA` (this session)
- `"market action" → FMNL` (this session, discovered, partially mitigated)

The pattern is clear: each fix tightens a hand-rule. None addresses the underlying lack of semantic discrimination.

## Desired Behavior

`symbol_search.resolve(query)` returns the rich v1+ contract:

```python
{
    "symbol": "TRENT" | None,
    "legacy_confidence": "exact" | "fuzzy" | "none",               # legacy projection for callers
    "confidence_band": "exact" | "high" | "medium" | "low" | "none",
    "score": 0.0–1.0,                                              # normalized confidence
    "raw_score": 0.0,                                              # raw method score or RRF score
    "query": original_query,
    "candidates": [                                                # NEW: top-N with per-method scores
        {"symbol": "TRENT", "score": 0.97, "raw_score": 0.047, "methods": ["dict", "trgm"]},
        {"symbol": "TRENTLIMITED", "score": 0.41, "raw_score": 0.020, "methods": ["trgm"]},
    ],
    "method": "dict" | "trigram" | "embedding" | "hybrid" | "live_api",
    "matched": "TRENT (TATA Group retail)",                        # NEW: human-readable match label
}
```

`tools.resolve_symbol(query)` keeps the legacy public shape and projects the rich result back to:

```python
{
    "symbol": "TRENT" | None,
    "confidence": "exact" | "fuzzy" | "none",
    "score": 0.0-1.0,
    "confidence_band": "exact" | "high" | "medium" | "low" | "none",
    "query": original_query,
    "candidates": [{"symbol": "TRENT", "score": 0.97, "methods": ["dict", "trgm"]}],
    "method": "dict" | "trigram" | "embedding" | "hybrid" | "live_api",
}
```

Behaviour by tier:

- **Tier 0 (always on)** — concept-token guard, dict exact, normalized exact. Sub-1ms.
- **Tier 1 (rollout v1)** — Postgres trigram (`pg_trgm`) over `market.symbol_aliases.name`. ~30-80ms. Replaces today's `_resolve_local_symbol` contains-match + SequenceMatcher tiers.
- **Tier 2 (rollout v2)** — sentence-embedding cosine over a precomputed `market.symbol_embeddings(symbol, vector)` table using `pgvector`. ~80-150ms.
- **Tier 3 (rollout v2)** — Reciprocal-rank fusion (RRF) of dict + trigram + embedding result sets. Optional cross-encoder rerank reserved for v3.
- **NSE live API** — preserved as a final network fallback, but rarely hit because Tier 1/2 cover the long tail.

Confidence-aware behaviour:
- `score ≥ 0.85` → return immediately, mark `confidence_band="high"` or `"exact"` and legacy `confidence="exact"` for exact tier or `"fuzzy"` for high non-exact tier.
- `0.60 ≤ score < 0.85` → return with `confidence_band="medium"` and legacy `confidence="fuzzy"`. The caller can show a "did you mean?" hint via the existing `terminal/confidence.py` clarification panel.
- `score < 0.60` → return `symbol=None`, `confidence_band="low"` or `"none"`, and legacy `confidence="none"` with `candidates` populated so the caller can disambiguate or fall back to live search.

## Detailed Architecture

### Module layout

```
terminal/
├── symbol_search/
│   ├── __init__.py           # public: resolve(query, top_n=10) → ResolveResult
│   ├── alias_source.py       # neutral alias loader; avoids importing terminal.tools
│   ├── dict_index.py         # tier 0: in-memory alias dict from alias_source
│   ├── trigram_index.py      # tier 1: Postgres pg_trgm queries
│   ├── embedding_index.py    # tier 2: pgvector queries + on-demand encoder
│   ├── fusion.py             # tier 3: RRF fusion + confidence calibration
│   ├── live_fallback.py      # NSE search API client (moved from tools.py)
│   └── schema.py             # dataclasses: ResolveCandidate, ResolveResult
├── tools.py                  # resolve_symbol(query) becomes a thin wrapper
└── entity_resolution.py      # validate_requested_symbols() uses new resolver too
```

`tools.resolve_symbol(query)` keeps its existing signature and return shape (back-compat) — it delegates to `symbol_search.resolve()` and projects the rich result back to the legacy dict. `symbol_search` must not import `terminal.tools`; shared alias construction moves to `terminal/symbol_search/alias_source.py` so `tools.py`, seed scripts, and tests all depend on the neutral module.

### Postgres schema additions

v1 migration:

```sql
-- migration: postgres/migrations/20260523_symbol_resolution_trgm.sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS market.symbol_aliases (
    symbol      TEXT NOT NULL,
    name        TEXT NOT NULL,                  -- alias / company-name / variant
    kind        TEXT NOT NULL CHECK (kind IN ('symbol','official','short','alias','sector_hint','manual')),
    weight      REAL NOT NULL DEFAULT 1.0,      -- per-alias confidence boost
    source      TEXT NOT NULL,                  -- 'nse_master', 'bse_master', 'manual', 'screener_eod', …
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (symbol, name, kind)
);

CREATE INDEX idx_symbol_aliases_name_trgm
    ON market.symbol_aliases USING gin (lower(name) gin_trgm_ops);
```

v2 migration:

```sql
-- migration: postgres/migrations/20260524_symbol_resolution_pgvector.sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS market.symbol_embeddings (
    symbol      TEXT PRIMARY KEY,
    embedding   vector(384)  NOT NULL,          -- all-MiniLM-L6-v2 dimensionality
    text_used   TEXT         NOT NULL,          -- the encoded canonical string
    model       TEXT         NOT NULL,
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX idx_symbol_embeddings_hnsw
    ON market.symbol_embeddings USING hnsw (embedding vector_cosine_ops);
```

### Tier 1 — Trigram retrieval (v1, lands first)

```sql
SELECT symbol,
       name,
       kind,
       weight,
       similarity(lower(name), lower($1)) AS raw_score,
       similarity(lower(name), lower($1)) * weight AS weighted_score
FROM market.symbol_aliases
WHERE  lower(name) % lower($1)            -- pg_trgm similarity above threshold
ORDER BY weighted_score DESC, raw_score DESC, kind ASC, symbol ASC
LIMIT  $2;
```

- `pg_trgm` threshold tuned via `SET pg_trgm.similarity_threshold = 0.3` per session (default 0.3 catches typos but rejects mid-word noise — `"siGNAls" ⨯ "GNA"` scores 0.15).
- The `kind` column lets us boost canonical names over generic aliases (e.g. `weight=1.0` for `official`, `0.6` for `sector_hint`).
- Bulk-loaded from `terminal/symbol_search/alias_source.py` plus NSE / BSE masters on first run.

### Tier 2 — Embedding retrieval (v2, deferred)

Encoding strategy (run offline + on master refresh):

```python
def canonical_text(row) -> str:
    return f"{row.symbol} — {row.official_name} ({row.sector or 'general'}); aliases: {', '.join(row.aliases)}"

model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
embeddings = model.encode([canonical_text(r) for r in master_rows], normalize_embeddings=True)
```

Query path:

```python
q_emb = model.encode(query, normalize_embeddings=True)
# pgvector cosine distance (smaller is closer)
SELECT symbol, 1 - (embedding <=> %s::vector) AS score
FROM market.symbol_embeddings ORDER BY embedding <=> %s::vector LIMIT 10;
```

Encoder hosting decision: **in-process via `sentence-transformers` package**. The all-MiniLM-L6-v2 model is 80MB, loads in 2-3s at startup, encodes a single query in 5-15ms on CPU. No HTTP service. No remote dependency. The model is cached under `~/.cache/huggingface/` after first download.

Fall-back if `sentence-transformers` is not installed → Tier 2 disabled gracefully, system continues with Tier 0+1.

### Tier 3 — Hybrid fusion (Reciprocal Rank Fusion)

```python
def rrf(candidate_lists: list[list[Candidate]], k: int = 60) -> list[Candidate]:
    """
    Reciprocal Rank Fusion: per candidate, sum 1/(k+rank_in_each_list).
    Robust to score-scale mismatch between dict/trigram/embedding.
    """
    scores: dict[str, float] = {}
    for lst in candidate_lists:
        for rank, cand in enumerate(lst, start=1):
            scores[cand.symbol] = scores.get(cand.symbol, 0.0) + 1.0 / (k + rank)
    return sorted_by(scores.items(), descending=True)
```

`k=60` is the Cormack-Clarke-Buettcher default; tunable in config. Per-tier results are deduped by symbol (best score wins) before fusion. The fused RRF value is stored as `raw_score`; `score` is a normalized confidence value in the 0.0-1.0 range for callers and UX.

### Confidence calibration

Map fused RRF score → normalized `score` and 5-band `confidence_band` using a held-out eval set (300 (query, expected_symbol) pairs):

| Band | Raw RRF range | Normalized score | Behaviour | Latency budget |
|---|---|---|---|---|
| `exact` | dict tier hit, full normalised match | 1.00 | Return immediately | 1ms |
| `high` | RRF ≥ 0.045 | 0.85-0.99 | Return, no clarification | 50ms |
| `medium` | 0.025 ≤ RRF < 0.045 | 0.60-0.84 | Return + flag `needs_clarification=True` | 100ms |
| `low` | 0.010 ≤ RRF < 0.025 | 0.30-0.59 | Return symbol=None, expose top-3 candidates | 150ms |
| `none` | RRF < 0.010 | 0.00-0.29 | Return symbol=None; trigger NSE live fallback | 150ms + network |

Thresholds will be recalibrated after the first 2 weeks of production traffic — telemetry is part of the rollout (see Observability).

### Integration with existing confidence scaffold

`terminal/confidence.py::score_intent()` already inspects symbol extraction during MTF routing. The new resolver returns a continuous score; intent scoring multiplies in `(1 - 0.3 × (1 - symbol_score))` when a symbol is required, so low-confidence resolution naturally drives intent confidence below the 0.65 CLARIFY threshold and pops the existing clarification panel. No new UX surface.

## Rollout Plan

### v1 — Trigram + cleanup (2-3 days)
1. Add migration `20260523_symbol_resolution_trgm.sql` (just `pg_trgm` + `market.symbol_aliases` + trigram GIN index).
2. Move alias-map construction into `terminal/symbol_search/alias_source.py`; bulk-load `symbol_aliases` from that neutral source at startup or via script (idempotent UPSERT).
3. Create `terminal/symbol_search/{alias_source,dict_index,trigram_index,fusion,schema}.py` (no embedding module yet).
4. Rewrite `_resolve_local_symbol` to delegate to `symbol_search.resolve()` with `methods=['dict','trigram']`.
5. Delete the contains-match block and the broad SequenceMatcher tier from `tools.py`; keep the prefix-8 typo branch as an isolated tier-0.5 provider with telemetry until eval proves it is unused.
6. Migrate `_primary_symbol_query`'s `confidence in {"exact","near-match"}` gate to `score >= 0.85` or `confidence_band in {"exact","high"}`.
7. Telemetry: structured log line per resolve (`query`, `winning_method`, `score`, `candidates`).

Exit criteria for v1:
- All 47 existing tests in `tests/test_terminal_symbol_resolution.py` pass unchanged.
- 5 new tests covering the regressions called out above (mid-word substring, single-word prefix, preposition phrase, NIFTY index phrase, "Premier"/"HDFC"/"Bharat" prefix collisions).
- Fallback tests pass for PostgreSQL unavailable, `pg_trgm` extension missing, and empty `market.symbol_aliases`.
- Latency p95 ≤ 80ms for in-vocab queries (measured against a 200-query benchmark).
- No new flake in the broader test suite.

### v2 — Embeddings (additional 3-4 days, deferred until v1 is stable)
1. Add migration `20260524_symbol_resolution_pgvector.sql` with `vector` extension + `market.symbol_embeddings` table + HNSW index.
2. Add `scripts/refresh_symbol_embeddings.py` (idempotent: encode all symbols if model/text changes).
3. Add `terminal/symbol_search/embedding_index.py` + integration in fusion.
4. Run encoder at startup (lazy-load); gate on `sentence-transformers` package presence.
5. Recalibrate confidence bands on the new fused score distribution.

Exit criteria for v2:
- Top-1 recall improves by ≥ 5 pp on a 100-query out-of-vocab eval (paraphrase / sector-description style queries).
- No regression on the in-vocab benchmark.
- Memory footprint ≤ +120MB at process steady state.

### v3 — Cross-encoder rerank (optional, future)
Reserved for if/when ambiguity rates remain high after v2. Would add `cross-encoder/ms-marco-MiniLM-L-6-v2` over the top-10 fused candidates. ~50ms extra latency; only invoked when fused top-1 and top-2 are within 0.005 RRF.

## Eval Strategy

Two benchmark sets, both checked in under `tests/fixtures/symbol_resolution/`:

1. **`in_vocab.jsonl`** — 200 known-good (query, expected_symbol) pairs scraped from past session logs and the prompt library. Must achieve top-1 ≥ 98%.
2. **`adversarial.jsonl`** — 50 pathological inputs:
   - Mid-word coincidences (the GNA bug + 10 more)
   - Single-word prefix traps ("Premier", "HDFC", "Bharat", "State", "Tata", "Bajaj", "Adani", "Mahindra")
   - Preposition phrases ("of India", "for intraday", "in pharma")
   - Index phrases pretending to be tickers ("NIFTY 50", "MIDCPNIFTY")
   - Pure prose ("intraday signals", "market action", "buy candidates")
   Must achieve top-1 precision ≥ 95% with **explicit `symbol=None`** on the prose / preposition cases — false-symbol rate ≤ 2%.

CI gate: both benchmarks run on every PR touching `terminal/symbol_search/` or `terminal/tools.py::resolve_symbol`.

## Observability

Each resolve emits a structured log line to `logs/symbol_resolution.jsonl`:

```json
{"ts":"2026-05-23T09:14:23Z","query":"scan TRENT for intraday signals",
 "winner":"TRENT","method":"hybrid","score":0.91,
 "candidates":[{"sym":"TRENT","score":0.91,"methods":["dict","trgm"]},
               {"sym":"TRENTLIMITED","score":0.42,"methods":["trgm"]}],
 "latency_ms":47,"clarification_emitted":false}
```

Daily aggregation surfaces:
- p50/p95/p99 latency
- Distribution by winning method
- `clarification_emitted` rate (proxy for ambiguity)
- Top-10 unresolved queries (for alias backlog)

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Trigram threshold misses NSE truncations (DATAPATTERNS → DATAPATTNS) | Keep the existing prefix-8 typo branch as a tier-0.5 supplement in v1; emit telemetry on its hits to decide later removal |
| `pg_trgm` not installed on a target Postgres | Migration is feature-flagged; resolver gracefully degrades to dict-only when extension absent |
| `pgvector` model drift when we upgrade encoder | `text_used` + `model` columns let us detect drift; a CHECK on model name during query forces recompute |
| Latency regression from network Postgres | Connection pool + prepared statements; benchmark gates rollout |
| Live NSE API rate-limit pressure increases as we add a 5th tier | We're *reducing* live-API calls — Tier 1/2 absorb most queries that used to fall through |
| Lossy bulk-load from legacy alias maps | Idempotent UPSERT with source-of-truth tracking; aliases from the neutral `alias_source.py` loader carry `source='legacy_bootstrap'` so we can audit |

## Non-Goals

- **No new UX surface.** Clarification UX reuses `terminal/confidence.py::render_clarification`. No new prompt panels.
- **No model fine-tuning in v1/v2.** A frozen sentence-transformer is enough until we have telemetry showing top-1 < 95% on a meaningful slice. Fine-tuning is v3+.
- **No LLM call in the resolution hot path.** The whole point is sub-100ms deterministic resolution. LLM-routed clarification happens only when score < 0.65, and only at the *intent* level, not inside `resolve_symbol`.
- **No replacement of the keyword router.** This document is scoped to symbol resolution; the broader LLM-routing question (Phase 1 from the routing review) is tracked separately.

## Open Questions

1. **Where does `weight` come from for aliases?** v1 default: 1.0 for `official`, 0.9 for `symbol`, 0.7 for `short`, 0.6 for `alias`, 0.5 for `sector_hint`; recalibrate from telemetry.
2. **Cold-start before `symbol_aliases` is populated?** The migration ships a `seed_symbol_aliases()` script that loads from `terminal/symbol_search/alias_source.py`; need a startup health check that fails loudly if the table is empty.
3. **Should we tier the live NSE API behind embedding fallback or after it?** Today: hit live API on `none`. Proposal: same — live API is for *brand-new symbols* not yet in our master, and the embedding tier won't help with those.
4. **Backwards compatibility for `confidence in {"exact","fuzzy","none"}`?** Resolved for v1: `tools.resolve_symbol()` keeps legacy `confidence`; rich callers use `confidence_band` and `score`. Renaming legacy fields is v2+ only with a release note.

## Companion Backlog Item

`docs/superpowers/plans/2026-05-22-hybrid-symbol-resolution.md` tracks the phased work items.
