-- News + Research Evidence Engine (P0)
-- Adds curated research source registry + FTS over evidence chunks.

CREATE TABLE IF NOT EXISTS company_intel.research_sources (
    source_id BIGSERIAL PRIMARY KEY,
    source_name TEXT NOT NULL,
    source_kind TEXT NOT NULL,
    source_url TEXT NOT NULL,
    symbol TEXT NOT NULL DEFAULT '',
    document_type TEXT NOT NULL DEFAULT 'news_rss',
    source_tier INTEGER NOT NULL,
    tags JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    notes TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (source_kind, source_url)
);

CREATE INDEX IF NOT EXISTS idx_company_intel_research_sources_active
    ON company_intel.research_sources (is_active, source_kind, source_tier);

CREATE INDEX IF NOT EXISTS idx_company_intel_research_sources_symbol
    ON company_intel.research_sources (symbol, is_active);

-- Phase 1 search: lexical GIN over evidence chunk text.
CREATE INDEX IF NOT EXISTS idx_company_intel_evidence_chunks_search
    ON company_intel.evidence_chunks
    USING GIN (to_tsvector('english', coalesce(text, '')));

-- Evidence pack audit log (reproducible retrieval)
CREATE TABLE IF NOT EXISTS company_intel.evidence_pack_runs (
    run_id BIGSERIAL PRIMARY KEY,
    symbol TEXT NOT NULL DEFAULT '',
    sector_overlay TEXT NOT NULL DEFAULT '',
    dimensions JSONB NOT NULL DEFAULT '[]'::jsonb,
    searches_run JSONB NOT NULL DEFAULT '[]'::jsonb,
    result_chunk_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    result_counts JSONB NOT NULL DEFAULT '{}'::jsonb,
    dimension_counts JSONB NOT NULL DEFAULT '{}'::jsonb,
    params JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_company_intel_evidence_pack_runs_symbol
    ON company_intel.evidence_pack_runs (symbol, created_at DESC);
