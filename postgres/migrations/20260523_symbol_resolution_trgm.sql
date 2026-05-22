-- AA-HSR-3: Hybrid Symbol Resolution — trigram retriever
--
-- Creates the alias table seeded by scripts/seed_symbol_aliases.py and the
-- GIN trigram index used by terminal/symbol_search/trigram_index.py.
--
-- Idempotent: every CREATE uses IF NOT EXISTS; safe to re-run.

CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE SCHEMA IF NOT EXISTS market;

CREATE TABLE IF NOT EXISTS market.symbol_aliases (
    symbol     TEXT        NOT NULL,
    name       TEXT        NOT NULL,
    kind       TEXT        NOT NULL CHECK (kind IN (
                  'symbol','official','short','alias','sector_hint','manual'
              )),
    weight     REAL        NOT NULL DEFAULT 1.0 CHECK (weight >= 0.0 AND weight <= 1.0),
    source     TEXT        NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (symbol, name, kind)
);

CREATE INDEX IF NOT EXISTS idx_symbol_aliases_name_trgm
    ON market.symbol_aliases USING gin (lower(name) gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_symbol_aliases_symbol
    ON market.symbol_aliases (symbol);

COMMENT ON TABLE market.symbol_aliases IS
    'Alias -> symbol map for hybrid symbol resolution (AA-HSR-2/3). Seeded by scripts/seed_symbol_aliases.py.';
