-- 2026-05-19
-- Structured numeric financials cache for Strategy Council / /analyze
-- read-through caching. Mirrors screener.in's P&L / quarterly / balance-sheet /
-- cash-flow tables in queryable form alongside the existing text-summary
-- tables in scores.fundamentals*.
--
-- Period semantics:
--   period_label  -- text from source, e.g. 'Mar 2026', 'FY26', 'TTM'
--   period_type   -- 'quarter' | 'annual' | 'ttm'
--   period_end    -- best-effort ISO date for the period end (NULL when unknown)
--
-- Source policy: screener primary, yfinance fallback. The same row may be
-- overwritten on refresh — we keep the latest scraped values per (symbol,
-- period_label) keyed PRIMARY KEY.

BEGIN;

CREATE TABLE IF NOT EXISTS scores.quarterly_results (
    symbol          TEXT        NOT NULL,
    period_label    TEXT        NOT NULL,
    period_end      DATE,
    period_type     TEXT        DEFAULT 'quarter',
    revenue         NUMERIC(20,4),
    expenses        NUMERIC(20,4),
    operating_profit NUMERIC(20,4),
    opm_pct         NUMERIC(12,4),
    other_income    NUMERIC(20,4),
    interest        NUMERIC(20,4),
    depreciation    NUMERIC(20,4),
    pbt             NUMERIC(20,4),
    tax_pct         NUMERIC(12,4),
    pat             NUMERIC(20,4),
    eps             NUMERIC(20,4),
    source          TEXT        NOT NULL DEFAULT 'screener',
    source_url      TEXT,
    raw_json        JSONB,
    fetched_at      TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (symbol, period_label)
);
CREATE INDEX IF NOT EXISTS idx_quarterly_results_symbol_end
    ON scores.quarterly_results (symbol, period_end DESC NULLS LAST);

CREATE TABLE IF NOT EXISTS scores.annual_results (
    symbol          TEXT        NOT NULL,
    period_label    TEXT        NOT NULL,
    period_end      DATE,
    period_type     TEXT        DEFAULT 'annual',
    revenue         NUMERIC(20,4),
    expenses        NUMERIC(20,4),
    operating_profit NUMERIC(20,4),
    opm_pct         NUMERIC(12,4),
    other_income    NUMERIC(20,4),
    interest        NUMERIC(20,4),
    depreciation    NUMERIC(20,4),
    pbt             NUMERIC(20,4),
    tax_pct         NUMERIC(12,4),
    pat             NUMERIC(20,4),
    eps             NUMERIC(20,4),
    dividend_payout_pct NUMERIC(12,4),
    source          TEXT        NOT NULL DEFAULT 'screener',
    source_url      TEXT,
    raw_json        JSONB,
    fetched_at      TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (symbol, period_label)
);
CREATE INDEX IF NOT EXISTS idx_annual_results_symbol_end
    ON scores.annual_results (symbol, period_end DESC NULLS LAST);

CREATE TABLE IF NOT EXISTS scores.balance_sheet (
    symbol          TEXT        NOT NULL,
    period_label    TEXT        NOT NULL,
    period_end      DATE,
    period_type     TEXT        DEFAULT 'annual',
    equity_capital  NUMERIC(20,4),
    reserves        NUMERIC(20,4),
    borrowings      NUMERIC(20,4),
    other_liabilities NUMERIC(20,4),
    total_liabilities NUMERIC(20,4),
    fixed_assets    NUMERIC(20,4),
    cwip            NUMERIC(20,4),
    investments     NUMERIC(20,4),
    other_assets    NUMERIC(20,4),
    total_assets    NUMERIC(20,4),
    net_debt        NUMERIC(20,4),
    source          TEXT        NOT NULL DEFAULT 'screener',
    source_url      TEXT,
    raw_json        JSONB,
    fetched_at      TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (symbol, period_label)
);
CREATE INDEX IF NOT EXISTS idx_balance_sheet_symbol_end
    ON scores.balance_sheet (symbol, period_end DESC NULLS LAST);

CREATE TABLE IF NOT EXISTS scores.cash_flow (
    symbol          TEXT        NOT NULL,
    period_label    TEXT        NOT NULL,
    period_end      DATE,
    period_type     TEXT        DEFAULT 'annual',
    operating_cf    NUMERIC(20,4),
    investing_cf    NUMERIC(20,4),
    financing_cf    NUMERIC(20,4),
    net_cf          NUMERIC(20,4),
    free_cash_flow  NUMERIC(20,4),
    source          TEXT        NOT NULL DEFAULT 'screener',
    source_url      TEXT,
    raw_json        JSONB,
    fetched_at      TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (symbol, period_label)
);
CREATE INDEX IF NOT EXISTS idx_cash_flow_symbol_end
    ON scores.cash_flow (symbol, period_end DESC NULLS LAST);

-- Audit table for the daily results-refresh job (which symbols were
-- re-scraped today, how many rows landed, any errors).
CREATE TABLE IF NOT EXISTS scores.financials_refresh_log (
    run_id          TEXT        PRIMARY KEY,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at     TIMESTAMPTZ,
    job_name        TEXT        NOT NULL,
    symbols_attempted INTEGER   DEFAULT 0,
    symbols_loaded  INTEGER     DEFAULT 0,
    rows_upserted   INTEGER     DEFAULT 0,
    errors          INTEGER     DEFAULT 0,
    notes           TEXT
);

-- Convenience views: latest period per symbol
CREATE OR REPLACE VIEW scores.v_latest_quarterly AS
SELECT DISTINCT ON (symbol) *
FROM scores.quarterly_results
ORDER BY symbol, period_end DESC NULLS LAST, fetched_at DESC;

CREATE OR REPLACE VIEW scores.v_latest_annual AS
SELECT DISTINCT ON (symbol) *
FROM scores.annual_results
ORDER BY symbol, period_end DESC NULLS LAST, fetched_at DESC;

CREATE OR REPLACE VIEW scores.v_latest_balance_sheet AS
SELECT DISTINCT ON (symbol) *
FROM scores.balance_sheet
ORDER BY symbol, period_end DESC NULLS LAST, fetched_at DESC;

CREATE OR REPLACE VIEW scores.v_latest_cash_flow AS
SELECT DISTINCT ON (symbol) *
FROM scores.cash_flow
ORDER BY symbol, period_end DESC NULLS LAST, fetched_at DESC;

COMMIT;
