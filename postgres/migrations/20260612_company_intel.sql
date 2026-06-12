CREATE SCHEMA IF NOT EXISTS company_intel;

CREATE TABLE IF NOT EXISTS company_intel.companies (
    symbol TEXT PRIMARY KEY,
    company_name TEXT NOT NULL DEFAULT '',
    bse_code TEXT NOT NULL DEFAULT '',
    isin TEXT NOT NULL DEFAULT '',
    sector TEXT NOT NULL DEFAULT '',
    industry TEXT NOT NULL DEFAULT '',
    website TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS company_intel.company_aliases (
    symbol TEXT NOT NULL REFERENCES company_intel.companies(symbol) ON DELETE CASCADE,
    alias TEXT NOT NULL,
    alias_type TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'system',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (symbol, alias)
);

CREATE TABLE IF NOT EXISTS company_intel.source_documents (
    document_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL DEFAULT '',
    source_tier INTEGER NOT NULL,
    source_name TEXT NOT NULL,
    source_url TEXT NOT NULL DEFAULT '',
    document_type TEXT NOT NULL DEFAULT '',
    document_date TEXT NOT NULL DEFAULT '',
    local_path TEXT NOT NULL DEFAULT '',
    content_hash TEXT NOT NULL DEFAULT '',
    fetch_status TEXT NOT NULL DEFAULT '',
    parse_status TEXT NOT NULL DEFAULT '',
    failure_reason TEXT NOT NULL DEFAULT '',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS company_intel.search_runs (
    search_run_id BIGSERIAL PRIMARY KEY,
    symbol TEXT NOT NULL,
    verticals JSONB NOT NULL DEFAULT '[]'::jsonb,
    mode TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'running',
    summary TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS company_intel.search_attempts (
    attempt_id BIGSERIAL PRIMARY KEY,
    search_run_id BIGINT NOT NULL REFERENCES company_intel.search_runs(search_run_id) ON DELETE CASCADE,
    source_group TEXT NOT NULL,
    query TEXT NOT NULL,
    alias_used TEXT NOT NULL DEFAULT '',
    result_count INTEGER NOT NULL DEFAULT 0,
    urls_found JSONB NOT NULL DEFAULT '[]'::jsonb,
    status TEXT NOT NULL,
    failure_reason TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS company_intel.evidence_chunks (
    chunk_id BIGSERIAL PRIMARY KEY,
    document_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    category TEXT NOT NULL,
    text TEXT NOT NULL,
    page_number INTEGER,
    table_id TEXT NOT NULL DEFAULT '',
    source_tier INTEGER NOT NULL,
    confidence DOUBLE PRECISION NOT NULL,
    evidence_date TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS company_intel.structured_facts (
    fact_id BIGSERIAL PRIMARY KEY,
    symbol TEXT NOT NULL,
    category TEXT NOT NULL,
    fact_name TEXT NOT NULL,
    fact_value TEXT NOT NULL,
    unit TEXT NOT NULL DEFAULT '',
    period TEXT NOT NULL DEFAULT '',
    evidence_chunk_id BIGINT REFERENCES company_intel.evidence_chunks(chunk_id) ON DELETE SET NULL,
    confidence DOUBLE PRECISION NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS company_intel.sector_entities (
    entity_id BIGSERIAL PRIMARY KEY,
    sector TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_name TEXT NOT NULL,
    symbol TEXT NOT NULL DEFAULT '',
    relationship TEXT NOT NULL DEFAULT '',
    evidence_chunk_id BIGINT REFERENCES company_intel.evidence_chunks(chunk_id) ON DELETE SET NULL,
    confidence DOUBLE PRECISION NOT NULL DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS company_intel.macro_policy_events (
    event_id BIGSERIAL PRIMARY KEY,
    event_type TEXT NOT NULL,
    event_date DATE NOT NULL,
    title TEXT NOT NULL,
    source_url TEXT NOT NULL DEFAULT '',
    summary TEXT NOT NULL DEFAULT '',
    raw_path TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS company_intel.impact_assessments (
    impact_id BIGSERIAL PRIMARY KEY,
    symbol TEXT NOT NULL,
    event_id BIGINT REFERENCES company_intel.macro_policy_events(event_id) ON DELETE SET NULL,
    impact_area TEXT NOT NULL,
    direction TEXT NOT NULL,
    magnitude TEXT NOT NULL,
    rationale TEXT NOT NULL,
    evidence_chunk_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    confidence DOUBLE PRECISION NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS company_intel.analysis_runs (
    analysis_run_id BIGSERIAL PRIMARY KEY,
    symbol TEXT NOT NULL,
    workflow TEXT NOT NULL,
    mode TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'running',
    report_path TEXT NOT NULL DEFAULT '',
    coverage_score DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    known_gaps JSONB NOT NULL DEFAULT '[]'::jsonb
);

CREATE TABLE IF NOT EXISTS company_intel.website_crawl_runs (
    crawl_run_id BIGSERIAL PRIMARY KEY,
    symbol TEXT NOT NULL,
    base_url TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'running',
    pages_seen INTEGER NOT NULL DEFAULT 0,
    pages_indexed INTEGER NOT NULL DEFAULT 0,
    documents_found INTEGER NOT NULL DEFAULT 0,
    failure_reason TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS company_intel.website_pages (
    page_id BIGSERIAL PRIMARY KEY,
    crawl_run_id BIGINT NOT NULL REFERENCES company_intel.website_crawl_runs(crawl_run_id) ON DELETE CASCADE,
    symbol TEXT NOT NULL,
    url TEXT NOT NULL,
    url_hash TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    content_hash TEXT NOT NULL DEFAULT '',
    content_type TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT '',
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    raw_path TEXT NOT NULL DEFAULT '',
    text TEXT NOT NULL DEFAULT '',
    page_type TEXT NOT NULL DEFAULT '',
    UNIQUE(symbol, url_hash)
);

CREATE TABLE IF NOT EXISTS company_intel.website_links (
    link_id BIGSERIAL PRIMARY KEY,
    crawl_run_id BIGINT NOT NULL REFERENCES company_intel.website_crawl_runs(crawl_run_id) ON DELETE CASCADE,
    symbol TEXT NOT NULL,
    from_url TEXT NOT NULL,
    to_url TEXT NOT NULL,
    link_text TEXT NOT NULL DEFAULT '',
    link_type TEXT NOT NULL DEFAULT '',
    is_same_domain BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS company_intel.website_page_chunks (
    chunk_id BIGSERIAL PRIMARY KEY,
    page_id BIGINT NOT NULL REFERENCES company_intel.website_pages(page_id) ON DELETE CASCADE,
    symbol TEXT NOT NULL,
    url TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    chunk_text TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT '',
    search_vector TSVECTOR GENERATED ALWAYS AS (
        to_tsvector('english', coalesce(title, '') || ' ' || coalesce(category, '') || ' ' || coalesce(chunk_text, ''))
    ) STORED,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_company_intel_company_aliases_alias
    ON company_intel.company_aliases (lower(alias));
CREATE INDEX IF NOT EXISTS idx_company_intel_source_documents_symbol
    ON company_intel.source_documents (symbol, document_type, fetch_status);
CREATE INDEX IF NOT EXISTS idx_company_intel_evidence_symbol_category
    ON company_intel.evidence_chunks (symbol, category, source_tier);
CREATE INDEX IF NOT EXISTS idx_company_intel_website_pages_symbol
    ON company_intel.website_pages (symbol, page_type, status);
CREATE INDEX IF NOT EXISTS idx_company_intel_website_chunks_symbol
    ON company_intel.website_page_chunks (symbol, category);
CREATE INDEX IF NOT EXISTS idx_company_intel_website_chunks_search
    ON company_intel.website_page_chunks USING GIN (search_vector);
