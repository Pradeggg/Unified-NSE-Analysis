-- Migration: bootstrap all schemas and tables from schema.sql + screener_schema.sql
-- Run this once on a fresh DB or after a data-corrupt recovery.
-- Safe to re-run (all statements use IF NOT EXISTS / OR REPLACE).
--
-- Steps:
--   1. psql -U nse_admin -h /tmp -d nse_market -f postgres/schema.sql
--   2. psql -U nse_admin -h /tmp -d nse_market -f postgres/screener_schema.sql
--   3. python postgres/loader.py   (or the steps below for targeted loads)
--
-- If loader.py fails mid-run (market.* tables newly created), re-run once more.

-- Infer Weinstein stage from technical signals when stage = 'UNKNOWN'
-- (Run after load_stage_snapshots populates the table)
UPDATE scores.stage_snapshots
SET stage = CASE
    WHEN supertrend_state = 'BULLISH' AND trend_signal IN ('BULLISH','STRONG_BULLISH') THEN 'STAGE_2'
    WHEN supertrend_state = 'BEARISH' AND trend_signal IN ('BEARISH','STRONG_BEARISH') THEN 'STAGE_4'
    WHEN supertrend_state = 'BULLISH'                                                   THEN 'STAGE_1'
    WHEN supertrend_state = 'BEARISH'                                                   THEN 'STAGE_3'
    ELSE stage
END
WHERE stage = 'UNKNOWN';

-- Refresh sector_top_stocks from stage_snapshots
INSERT INTO scores.sector_top_stocks (
    score_date, sector_name, sector_strength, total_stocks, rank,
    symbol, company_name, market_cap_cat, current_price,
    change_1d_pct, change_1w_pct, change_1m_pct,
    technical_score, rsi, relative_strength,
    can_slim_score, minervini_score, enhanced_fund_score,
    trend_signal, trading_signal
)
SELECT
    snapshot_date,
    COALESCE(sector, 'Other'),
    AVG(technical_score) OVER (PARTITION BY snapshot_date, sector),
    COUNT(*)             OVER (PARTITION BY snapshot_date, sector),
    ROW_NUMBER()         OVER (PARTITION BY snapshot_date, sector ORDER BY investment_score DESC NULLS LAST),
    symbol, company_name, market_cap_cat,
    COALESCE(live_price, price),
    change_1d_pct, change_1w_pct, change_1m_pct,
    technical_score, rsi, relative_strength,
    can_slim_score, minervini_score, enhanced_fund_score,
    trend_signal, trading_signal
FROM scores.stage_snapshots
ON CONFLICT (score_date, sector_name, symbol) DO NOTHING;
