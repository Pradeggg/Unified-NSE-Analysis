-- ============================================================================
-- report schema for Enhanced Comprehensive Analysis
-- PG-report: Migrated from legacy R script nse_enhanced_comprehensive_analysis.R
-- Each /reports run inserts one row into report.enhanced_runs and N rows into
-- report.enhanced_filtered_stocks / report.enhanced_indices for that run_id.
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS report;

-- Run header — one row per execution
CREATE TABLE IF NOT EXISTS report.enhanced_runs (
    run_id                 BIGSERIAL PRIMARY KEY,
    run_ts                 TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    analysis_date          DATE        NOT NULL,
    universe_size          INTEGER     NOT NULL,
    stocks_analyzed        INTEGER     NOT NULL,
    stocks_filtered        INTEGER     NOT NULL,
    indices_analyzed       INTEGER     NOT NULL,
    market_composite_score NUMERIC(6,2),
    market_sentiment       TEXT,
    notes                  TEXT
);

-- Filtered stock universe (Volume > 100k AND Price > ₹100)
CREATE TABLE IF NOT EXISTS report.enhanced_filtered_stocks (
    run_id           BIGINT  NOT NULL REFERENCES report.enhanced_runs(run_id) ON DELETE CASCADE,
    rank             INTEGER NOT NULL,
    symbol           TEXT    NOT NULL,
    score            NUMERIC(6,2),
    recommendation   TEXT,
    current_price    NUMERIC(14,2),
    open_price       NUMERIC(14,2),
    high_price       NUMERIC(14,2),
    low_price        NUMERIC(14,2),
    volume           BIGINT,
    trading_value_cr NUMERIC(16,2),
    weekly_signal    TEXT,
    daily_signal     TEXT,
    day_change_pct   NUMERIC(8,2),
    rsi              NUMERIC(6,2),
    above_50dma      BOOLEAN,
    above_200dma     BOOLEAN,
    -- PG-report-v2: legacy R sub-scores
    tech_score       NUMERIC(6,2),   -- 0..60 — technical composite (7 indicators)
    fund_score       NUMERIC(6,2),   -- 0..25 — scaled enhanced_fund_score
    rs_score         NUMERIC(6,2),   -- 0..15 — relative strength vs Nifty 500
    macd_signal      TEXT,           -- 'BULLISH' | 'BEARISH' | 'NEUTRAL'
    week52_position  NUMERIC(6,2),   -- 0..100 — % position within 52-week range
    volume_ratio     NUMERIC(8,2),   -- volume / 20-day VEMA
    rs_vs_nifty500   TEXT,           -- 'OUTPERFORMING' | 'IN_LINE' | 'UNDERPERFORMING'
    PRIMARY KEY (run_id, symbol)
);

-- PG-report-v2: idempotent migration for pre-existing tables
ALTER TABLE report.enhanced_filtered_stocks
    ADD COLUMN IF NOT EXISTS tech_score      NUMERIC(6,2),
    ADD COLUMN IF NOT EXISTS fund_score      NUMERIC(6,2),
    ADD COLUMN IF NOT EXISTS rs_score        NUMERIC(6,2),
    ADD COLUMN IF NOT EXISTS macd_signal     TEXT,
    ADD COLUMN IF NOT EXISTS week52_position NUMERIC(6,2),
    ADD COLUMN IF NOT EXISTS volume_ratio    NUMERIC(8,2),
    ADD COLUMN IF NOT EXISTS rs_vs_nifty500  TEXT;

-- Major index analysis
CREATE TABLE IF NOT EXISTS report.enhanced_indices (
    run_id          BIGINT  NOT NULL REFERENCES report.enhanced_runs(run_id) ON DELETE CASCADE,
    index_name      TEXT    NOT NULL,
    score           NUMERIC(6,2),
    recommendation  TEXT,
    current_value   NUMERIC(14,2),
    weekly_signal   TEXT,
    daily_signal    TEXT,
    day_change_pct  NUMERIC(8,2),
    rsi             NUMERIC(6,2),
    momentum_50d    NUMERIC(8,2),
    relative_strength NUMERIC(8,2),
    trend_signal    TEXT,
    trading_signal  TEXT,
    PRIMARY KEY (run_id, index_name)
);

CREATE INDEX IF NOT EXISTS ix_report_filtered_run        ON report.enhanced_filtered_stocks (run_id);
CREATE INDEX IF NOT EXISTS ix_report_filtered_score      ON report.enhanced_filtered_stocks (run_id, score DESC);
CREATE INDEX IF NOT EXISTS ix_report_indices_run         ON report.enhanced_indices         (run_id);

-- Convenience view: latest run details
CREATE OR REPLACE VIEW report.v_latest_run AS
SELECT * FROM report.enhanced_runs ORDER BY run_id DESC LIMIT 1;

CREATE OR REPLACE VIEW report.v_latest_filtered_stocks AS
SELECT fs.*
FROM   report.enhanced_filtered_stocks fs
JOIN   report.v_latest_run lr ON lr.run_id = fs.run_id
ORDER  BY fs.score DESC NULLS LAST, fs.rank;

CREATE OR REPLACE VIEW report.v_latest_indices AS
SELECT i.*
FROM   report.enhanced_indices i
JOIN   report.v_latest_run lr ON lr.run_id = i.run_id
ORDER  BY i.score DESC NULLS LAST, i.index_name;
