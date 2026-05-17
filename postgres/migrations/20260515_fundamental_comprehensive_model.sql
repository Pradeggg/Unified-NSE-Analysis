-- 2026-05-15
-- Comprehensive Screener fundamental model extension:
-- add cash flow + investor summaries and normalized section snapshots.

BEGIN;

ALTER TABLE scores.fundamentals
    ADD COLUMN IF NOT EXISTS cash_flow_summary TEXT,
    ADD COLUMN IF NOT EXISTS investor_summary TEXT;

ALTER TABLE scores.fundamental_snapshots
    ADD COLUMN IF NOT EXISTS cash_flow_summary TEXT,
    ADD COLUMN IF NOT EXISTS investor_summary TEXT;

CREATE TABLE IF NOT EXISTS scores.fundamental_section_snapshots (
    snapshot_date   DATE        NOT NULL,
    symbol          TEXT        NOT NULL,
    section_name    TEXT        NOT NULL,
    section_summary TEXT,
    source_file     TEXT,
    loaded_at       TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (snapshot_date, symbol, section_name)
);

CREATE INDEX IF NOT EXISTS idx_fund_section_symbol_date
    ON scores.fundamental_section_snapshots (symbol, snapshot_date DESC);

COMMIT;
