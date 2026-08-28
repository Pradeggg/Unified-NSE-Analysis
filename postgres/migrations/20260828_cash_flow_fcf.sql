-- 2026-08-28
-- Preserve Screener's reported Free Cash Flow in the structured PG cache.
ALTER TABLE IF EXISTS scores.cash_flow
    ADD COLUMN IF NOT EXISTS free_cash_flow NUMERIC(20,4);
