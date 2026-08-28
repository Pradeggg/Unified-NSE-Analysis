# News + Research Evidence Engine (FTS-only, curated feeds) — Design

## Goal
Build a research-first intelligence layer that:
- Ingests curated sources (RSS/Atom + official docs + company calls).
- Stores auditable evidence (passages with timestamps + source tier).
- Enables fast lexical search (PostgreSQL FTS; no embeddings in Phase 1).
- Powers on-demand deep research reports via “evidence packs”.

Non-goals (Phase 1):
- No site-wide crawling of news sites.
- No semantic/vector search.
- No automated investment advice.

---

## Source tiers (authority)
- **Tier 1 (Primary):** exchange filings, annual report, investor presentation, concall transcripts/PDFs.
- **Tier 2 (Semi-primary):** rating agency releases, regulator/government notifications.
- **Tier 3 (Secondary):** reputed news feeds (curated).
- **Tier 4 (Opinion):** broker research/opinionated sources.

Tier is stored on every document and evidence chunk and should be used as a ranking prior.

---

## Data model (PostgreSQL, `company_intel`)
The canonical store is `nse_market` PostgreSQL under schema `company_intel` (see `postgres/migrations/20260612_company_intel.sql`).

### Existing (reused)
- `company_intel.source_documents` — document registry (URL/hash/metadata).
- `company_intel.evidence_chunks` — auditable passages (text + tier + confidence + evidence_date).
- `company_intel.structured_facts` — extracted facts (always linked to an evidence chunk).

### New (Phase 1)
`company_intel.research_sources` — curated registry for RSS/Atom and other “feed-like” sources.

Intended usage:
- YAML file in repo is the source of truth.
- A sync tool upserts YAML into `company_intel.research_sources`.
- Ingest tools query only `is_active = true` sources.

---

## Curated source registry (repo file)
File: `config/research_sources.yml`

Schema (v1):
- `version`: integer
- `sources[]`:
  - `source_name` (string, required)
  - `source_kind` (string, required; e.g. `rss`)
  - `source_url` (string, required; feed URL)
  - `source_tier` (int, required; 1–4)
  - `document_type` (string, optional; default `news_rss`)
  - `symbol` (string, optional; empty = market-wide)
  - `tags` (object, optional; stored into JSONB metadata)
  - `is_active` (bool, optional; default true)
  - `notes` (string, optional)

---

## Ingestion pipeline (RSS/Atom)
Tool: `tools/ingest_news_feeds.py`

Steps:
1) Load `config/research_sources.yml`.
2) Sync into `company_intel.research_sources` (upsert by `(source_kind, source_url)`).
3) Fetch active RSS/Atom feeds.
4) For each feed entry:
   - Create a deterministic `document_id` from the entry URL/guid.
   - Insert into `company_intel.source_documents` (idempotent).
   - Insert 1+ evidence chunks into `company_intel.evidence_chunks` (idempotent at document level).
5) Resulting evidence is searchable immediately via FTS.

Notes:
- RSS items are a snapshot, not “live tape”. Store `fetched_at` and `published_at`.
- Only store short excerpts/snippets appropriate for evidence; avoid copying long copyrighted text.

---

## Search (Phase 1)
Add a GIN index for lexical search over `company_intel.evidence_chunks.text`.

Search query shape:
- `q` (text query)
- filters:
  - `symbol` (optional; include empty-symbol “market-wide” evidence when desired)
  - `source_tier_max` (optional)
  - `category` (optional)
  - `date_from/date_to` (optional; uses `evidence_date` where present)

Outputs:
- “Evidence Pack”: top passages with `(chunk_id, document_id, url, tier, dates)` + gaps.

