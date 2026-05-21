-- =============================================================================
-- NSE Market Intelligence Platform — PostgreSQL Schema v1.0
-- Industry-grade data model covering all data sources
--
-- Schemas:
--   ref          → Master / reference data (instruments, indices, sectors)
--   market       → OHLCV price data (equity EOD, index EOD, intraday, global)
--   derivatives  → F&O bhavcopy + derived signals
--   scores       → Pre-computed KPI snapshots (tech, fundamental, composite)
--   signals      → Trading signals, FII/DII, bulk/block deals, events, alerts
--   breadth      → Market and sector breadth indicators
--   macro        → FRED series, global correlations, seasonal, tailwinds
--   portfolio    → Holdings, transactions
-- =============================================================================

-- Extensions
CREATE EXTENSION IF NOT EXISTS pg_trgm;           -- fuzzy symbol/name search
CREATE EXTENSION IF NOT EXISTS btree_gist;        -- range index support

-- =============================================================================
-- SCHEMAS
-- =============================================================================
CREATE SCHEMA IF NOT EXISTS ref;
CREATE SCHEMA IF NOT EXISTS market;
CREATE SCHEMA IF NOT EXISTS derivatives;
CREATE SCHEMA IF NOT EXISTS scores;
CREATE SCHEMA IF NOT EXISTS signals;
CREATE SCHEMA IF NOT EXISTS breadth;
CREATE SCHEMA IF NOT EXISTS macro;
CREATE SCHEMA IF NOT EXISTS portfolio;

-- =============================================================================
-- 1. REF — Master / Reference Data
-- =============================================================================

CREATE TABLE ref.instruments (
    symbol              TEXT        PRIMARY KEY,
    isin                TEXT        UNIQUE,
    company_name        TEXT        NOT NULL,
    series              TEXT        DEFAULT 'EQ',
    face_value          NUMERIC(10,2),
    issue_size          BIGINT,
    listing_date        DATE,
    sector              TEXT,
    industry            TEXT,
    market_cap_cat      TEXT,       -- LARGE_CAP / MID_CAP / SMALL_CAP / MICRO_CAP
    is_fno              BOOLEAN     DEFAULT FALSE,
    is_sme              BOOLEAN     DEFAULT FALSE,
    is_etf              BOOLEAN     DEFAULT FALSE,
    is_nifty50          BOOLEAN     DEFAULT FALSE,
    is_nifty500         BOOLEAN     DEFAULT FALSE,
    status              TEXT        DEFAULT 'ACTIVE',  -- ACTIVE / SUSPENDED / DELISTED
    updated_at          TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE ref.indices (
    index_symbol        TEXT        PRIMARY KEY,   -- e.g. "NIFTY 50"
    display_name        TEXT,
    category_code       TEXT,
    category_label      TEXT,
    nse_group_raw       TEXT,
    is_thematic         BOOLEAN     DEFAULT FALSE,
    is_derivatives      BOOLEAN     DEFAULT FALSE,
    last_close          NUMERIC(12,2),
    pe                  NUMERIC(8,2),
    pb                  NUMERIC(8,2),
    year_high           NUMERIC(12,2),
    year_low            NUMERIC(12,2),
    updated_at          TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE ref.index_compositions (
    index_symbol        TEXT        NOT NULL REFERENCES ref.indices(index_symbol),
    symbol              TEXT        NOT NULL REFERENCES ref.instruments(symbol),
    weight_pct          NUMERIC(8,4),
    as_of_date          DATE        NOT NULL DEFAULT CURRENT_DATE,
    PRIMARY KEY (index_symbol, symbol)
);

CREATE TABLE ref.sector_taxonomy (
    sector              TEXT        PRIMARY KEY,
    parent_category     TEXT,
    nse_index_name      TEXT,
    description         TEXT
);

-- =============================================================================
-- 2. MARKET — OHLCV Price Data
-- =============================================================================

-- Equity EOD bhavcopy (from NSE bhavcopy + nse_sec_full_data.csv)
CREATE TABLE market.equity_eod (
    trade_date          DATE        NOT NULL,
    symbol              TEXT        NOT NULL,
    series              TEXT        DEFAULT 'EQ',
    open                NUMERIC(12,2),
    high                NUMERIC(12,2),
    low                 NUMERIC(12,2),
    close               NUMERIC(12,2) NOT NULL,
    last_price          NUMERIC(12,2),
    prev_close          NUMERIC(12,2),
    change_abs          NUMERIC(12,4),
    change_pct          NUMERIC(8,4),
    volume              BIGINT,
    turnover_cr         NUMERIC(16,4),
    total_trades        INTEGER,
    delivery_qty        BIGINT,
    delivery_pct        NUMERIC(6,2),
    week52_high         NUMERIC(12,2),
    week52_low          NUMERIC(12,2),
    market_cap_cr       NUMERIC(18,4),
    PRIMARY KEY (trade_date, symbol, series)
);

-- Index EOD (from pr29102025.csv + index_analysis in nse_analysis.db)
CREATE TABLE market.index_eod (
    trade_date          DATE        NOT NULL,
    index_symbol        TEXT        NOT NULL,
    open                NUMERIC(12,2),
    high                NUMERIC(12,2),
    low                 NUMERIC(12,2),
    close               NUMERIC(12,2) NOT NULL,
    prev_close          NUMERIC(12,2),
    change_pct          NUMERIC(8,4),
    volume              BIGINT,
    turnover_cr         NUMERIC(16,4),
    total_trades        INTEGER,
    week52_high         NUMERIC(12,2),
    week52_low          NUMERIC(12,2),
    -- Derived technical (populated by daily_refresh.py)
    technical_score     NUMERIC(6,2),
    rsi                 NUMERIC(6,2),
    momentum_50d        NUMERIC(8,4),
    relative_strength   NUMERIC(8,4),
    trend_signal        TEXT,
    trading_signal      TEXT,
    PRIMARY KEY (trade_date, index_symbol)
);

-- 52-week high/low daily snapshot (from hl29102025.csv pattern)
CREATE TABLE market.week52_extremes (
    snapshot_date       DATE        NOT NULL,
    symbol              TEXT        NOT NULL,
    new_high            NUMERIC(12,2),
    prev_high           NUMERIC(12,2),
    new_low             NUMERIC(12,2),
    prev_low            NUMERIC(12,2),
    status              TEXT,       -- H (new high) / L (new low) / N (neutral)
    PRIMARY KEY (snapshot_date, symbol)
);

-- Intraday technical snapshots (from terminal/intraday.py)
CREATE TABLE market.intraday_snapshots (
    snapshot_ts         TIMESTAMPTZ NOT NULL,
    trade_date          DATE        NOT NULL,
    symbol              TEXT        NOT NULL,
    current_price       NUMERIC(12,2),
    price_change        NUMERIC(12,4),
    change_pct          NUMERIC(8,4),
    technical_score     NUMERIC(6,2),
    trend_score         NUMERIC(6,2),
    momentum_score      NUMERIC(6,2),
    volume_score        NUMERIC(6,2),
    support_resistance_score NUMERIC(6,2),
    volatility_score    NUMERIC(6,2),
    data_points         INTEGER,
    PRIMARY KEY (snapshot_ts, symbol)
);

-- Global equity / ETF / commodity prices (from data/global_market/)
CREATE TABLE market.global_prices (
    trade_date          DATE        NOT NULL,
    symbol              TEXT        NOT NULL,   -- AAPL, SPY, ^GSPC, GC=F, etc.
    open                NUMERIC(14,4),
    high                NUMERIC(14,4),
    low                 NUMERIC(14,4),
    close               NUMERIC(14,4) NOT NULL,
    volume              BIGINT,
    source              TEXT        DEFAULT 'yfinance',
    PRIMARY KEY (trade_date, symbol)
);

-- Global benchmark indices daily (from data/global_indices.csv)
CREATE TABLE market.global_index_levels (
    trade_date          DATE        NOT NULL,
    index_name          TEXT        NOT NULL,   -- S&P 500, Nasdaq, Nikkei, etc.
    close               NUMERIC(14,4),
    change_pct          NUMERIC(8,4),
    PRIMARY KEY (trade_date, index_name)
);

-- Market cap history (from mcap bhavcopy files)
CREATE TABLE market.market_cap_history (
    snapshot_date       DATE        NOT NULL,
    symbol              TEXT        NOT NULL,
    series              TEXT        DEFAULT 'EQ',
    face_value          NUMERIC(10,2),
    issue_size          BIGINT,
    close_price         NUMERIC(12,2),
    market_cap_cr       NUMERIC(18,4),
    PRIMARY KEY (snapshot_date, symbol, series)
);

-- =============================================================================
-- 3. DERIVATIVES — F&O Data
-- =============================================================================

-- F&O EOD bhavcopy (from data/fno/fno_eod.db + data/_fno_cache/*.csv)
CREATE TABLE derivatives.fno_eod (
    trade_date          DATE        NOT NULL,
    symbol              TEXT        NOT NULL,
    expiry_date         DATE        NOT NULL,
    instrument          TEXT        NOT NULL,   -- STF/STO/IDF/IDO or legacy FUT*/OPT*
    option_type         TEXT        NOT NULL,   -- CE / PE / FUT for futures
    strike              NUMERIC(12,2) NOT NULL DEFAULT 0,
    open                NUMERIC(12,2),
    high                NUMERIC(12,2),
    low                 NUMERIC(12,2),
    close               NUMERIC(12,2),
    last_price          NUMERIC(12,2),
    prev_close          NUMERIC(12,2),
    underlying_price    NUMERIC(12,2),
    settle_price        NUMERIC(12,2),
    open_interest       BIGINT,
    oi_change           BIGINT,
    volume              BIGINT,
    turnover_cr         NUMERIC(16,4),
    total_trades        INTEGER,
    lot_size            INTEGER,
    strike_key          NUMERIC(12,2) GENERATED ALWAYS AS (COALESCE(strike, 0)) STORED,
    PRIMARY KEY (trade_date, symbol, expiry_date, instrument, option_type, strike_key)
) PARTITION BY RANGE (trade_date);

CREATE TABLE derivatives.fno_eod_default PARTITION OF derivatives.fno_eod DEFAULT;

CREATE OR REPLACE FUNCTION derivatives.ensure_fno_monthly_partition(p_trade_date DATE)
RETURNS TEXT
LANGUAGE plpgsql
AS $$
DECLARE
    v_start DATE;
    v_end DATE;
    v_part TEXT;
BEGIN
    IF p_trade_date IS NULL THEN
        RAISE EXCEPTION 'p_trade_date cannot be null';
    END IF;

    v_start := date_trunc('month', p_trade_date)::date;
    v_end := (v_start + INTERVAL '1 month')::date;
    v_part := format('fno_eod_y%sm%s', to_char(v_start, 'YYYY'), to_char(v_start, 'MM'));

    EXECUTE format(
        'CREATE TABLE IF NOT EXISTS derivatives.%I PARTITION OF derivatives.fno_eod FOR VALUES FROM (%L) TO (%L)',
        v_part,
        v_start,
        v_end
    );

    RETURN 'derivatives.' || v_part;
END;
$$;

-- Derived F&O signals per symbol per day (from data/fno_signals.csv)
CREATE TABLE derivatives.fno_signals (
    snapshot_date       DATE        NOT NULL,
    symbol              TEXT        NOT NULL,
    pcr                 NUMERIC(8,4),           -- Put/Call Ratio
    oi_change_5d        NUMERIC(8,4),
    price_change        NUMERIC(8,4),
    buildup             TEXT,   -- LONG_BUILDUP / SHORT_BUILDUP / LONG_UNWINDING / SHORT_COVERING
    max_pain            NUMERIC(12,2),
    fno_signal          TEXT,   -- BULLISH / BEARISH / NEUTRAL
    PRIMARY KEY (snapshot_date, symbol)
);

-- =============================================================================
-- 4. SCORES — Pre-Computed KPI Snapshots
-- =============================================================================

-- Comprehensive daily scores per stock (from comprehensive_nse_enhanced_*.csv)
-- This is the primary KPI table — one row per stock per date
CREATE TABLE scores.daily_scores (
    score_date          DATE        NOT NULL,
    symbol              TEXT        NOT NULL,
    company_name        TEXT,
    sector              TEXT,
    market_cap_cat      TEXT,
    -- Price context
    current_price       NUMERIC(12,2),
    change_1d_pct       NUMERIC(8,4),
    change_1w_pct       NUMERIC(8,4),
    change_1m_pct       NUMERIC(8,4),
    trading_value       NUMERIC(18,4),
    -- Technical
    technical_score     NUMERIC(6,2),
    rsi                 NUMERIC(6,2),
    relative_strength   NUMERIC(8,4),
    trend_signal        TEXT,
    trading_signal      TEXT,
    -- Score components
    can_slim_score      NUMERIC(6,2),
    minervini_score     NUMERIC(6,2),
    fundamental_score   NUMERIC(6,2),
    enhanced_fund_score NUMERIC(6,2),
    earnings_quality    NUMERIC(6,2),
    sales_growth        NUMERIC(6,2),
    financial_strength  NUMERIC(6,2),
    institutional_backing NUMERIC(6,2),
    PRIMARY KEY (score_date, symbol)
);

-- Weinstein stage + full investment score (from sector_rotation_tracker.db)
CREATE TABLE scores.stage_snapshots (
    snapshot_date       DATE        NOT NULL,
    symbol              TEXT        NOT NULL,
    company_name        TEXT,
    sector              TEXT,
    market_cap_cat      TEXT,
    -- Price
    price               NUMERIC(12,2),
    live_price          NUMERIC(12,2),
    price_date          DATE,
    change_1d_pct       NUMERIC(8,4),
    change_1w_pct       NUMERIC(8,4),
    change_1m_pct       NUMERIC(8,4),
    -- Weinstein Stage
    stage               TEXT,       -- STAGE_1 / STAGE_2 / STAGE_3 / STAGE_4
    stage_score         NUMERIC(6,2),
    -- Technical
    technical_score     NUMERIC(6,2),
    rsi                 NUMERIC(6,2),
    trend_signal        TEXT,
    trading_signal      TEXT,
    relative_strength   NUMERIC(8,4),
    supertrend_state    TEXT,
    supertrend_value    NUMERIC(12,2),
    -- Score components
    can_slim_score      NUMERIC(6,2),
    minervini_score     NUMERIC(6,2),
    fundamental_score   NUMERIC(6,2),
    enhanced_fund_score NUMERIC(6,2),
    earnings_quality    NUMERIC(6,2),
    sales_growth        NUMERIC(6,2),
    financial_strength  NUMERIC(6,2),
    institutional_backing NUMERIC(6,2),
    -- Composite
    investment_score    NUMERIC(6,2),
    stance              TEXT,       -- BULLISH / NEUTRAL / BEARISH
    narrative           TEXT,
    fund_details        JSONB,
    source_csv          TEXT,
    PRIMARY KEY (snapshot_date, symbol)
);

-- Stage transition history (from sector_rotation_tracker.db stage_changes)
CREATE TABLE scores.stage_changes (
    change_date         DATE        NOT NULL,
    compare_date        DATE,
    symbol              TEXT        NOT NULL,
    company_name        TEXT,
    stage_now           TEXT,
    stage_prev          TEXT,
    stage_changed       BOOLEAN,
    change_type         TEXT,       -- UPGRADE / DOWNGRADE / ENTRY / EXIT
    price_now           NUMERIC(12,2),
    price_prev          NUMERIC(12,2),
    price_chg_pct       NUMERIC(8,4),
    live_price          NUMERIC(12,2),
    live_vs_prev_pct    NUMERIC(8,4),
    stage_score_now     NUMERIC(6,2),
    stage_score_prev    NUMERIC(6,2),
    trading_signal      TEXT,
    PRIMARY KEY (change_date, compare_date, symbol)
);

-- Long-term pattern screener results (from long_term_screeners_*.csv)
CREATE TABLE scores.long_term_screeners (
    score_date          DATE        NOT NULL,
    symbol              TEXT        NOT NULL,
    market_cap_cat      TEXT,
    current_price       NUMERIC(12,2),
    monthly_rs          NUMERIC(8,4),
    technical_score     NUMERIC(6,2),
    -- Pattern flags
    consolidation_breakout  BOOLEAN,
    cup_handle          BOOLEAN,
    long_term_uptrend   BOOLEAN,
    momentum_breakout   BOOLEAN,
    support_bounce      BOOLEAN,
    volume_accumulation BOOLEAN,
    earnings_momentum   BOOLEAN,
    week52_high_breakout BOOLEAN,
    pattern_count       INTEGER GENERATED ALWAYS AS (
        (consolidation_breakout::int + cup_handle::int + long_term_uptrend::int +
         momentum_breakout::int + support_bounce::int + volume_accumulation::int +
         earnings_momentum::int + week52_high_breakout::int)
    ) STORED,
    PRIMARY KEY (score_date, symbol)
);

-- Fundamental scores cache (from data/_sector_rotation_fund_cache.csv)
-- Also stores forensic scores when computed live
CREATE TABLE scores.fundamentals (
    symbol              TEXT        PRIMARY KEY,
    pnl_summary         TEXT,
    quarterly_summary   TEXT,
    balance_sheet_summary TEXT,
    cash_flow_summary   TEXT,
    investor_summary    TEXT,
    ratios_summary      TEXT,
    -- Forensic scores (computed on-demand via screener.in scrape)
    piotroski_score     NUMERIC(4,1),
    beneish_m_score     NUMERIC(10,4),
    altman_z_score      NUMERIC(10,4),
    forensic_risk       TEXT,       -- LOW / MODERATE / HIGH
    -- Parsed fundamental KPIs
    revenue_growth_3y   NUMERIC(8,4),
    pat_growth_3y       NUMERIC(8,4),
    roe                 NUMERIC(8,4),
    roce                NUMERIC(8,4),
    debt_to_equity      NUMERIC(8,4),
    promoter_holding    NUMERIC(6,2),
    updated_at          TIMESTAMPTZ DEFAULT now()
);

-- Dated Screener.in fundamental detail snapshots.
-- Keeps the raw summary text fetched by working-sector/fetch_screener_fundamental_details.R.
CREATE TABLE scores.fundamental_snapshots (
    snapshot_date       DATE        NOT NULL,
    symbol              TEXT        NOT NULL,
    pnl_summary         TEXT,
    quarterly_summary   TEXT,
    balance_sheet_summary TEXT,
    cash_flow_summary   TEXT,
    investor_summary    TEXT,
    ratios_summary      TEXT,
    source_file         TEXT,
    loaded_at           TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (snapshot_date, symbol)
);

-- Normalized, section-wise fundamental snapshot store.
-- Keeps each Screener section independently queryable while preserving dated snapshots.
CREATE TABLE scores.fundamental_section_snapshots (
    snapshot_date       DATE        NOT NULL,
    symbol              TEXT        NOT NULL,
    section_name        TEXT        NOT NULL,
    section_summary     TEXT,
    source_file         TEXT,
    loaded_at           TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (snapshot_date, symbol, section_name)
);

CREATE VIEW scores.v_latest_fundamentals AS
SELECT DISTINCT ON (symbol) *
FROM scores.fundamental_snapshots
ORDER BY symbol, snapshot_date DESC, loaded_at DESC;

-- Fundamental score components (from fundamental_scores_database.csv)
-- Dated model score snapshots per symbol; use v_latest_fundamental_scores for latest joins.
CREATE TABLE scores.fundamental_scores (
    score_date              DATE        NOT NULL,
    symbol                  TEXT        NOT NULL,
    enhanced_fund_score     NUMERIC(6,2),
    earnings_quality        NUMERIC(6,2),
    sales_growth            NUMERIC(6,2),
    financial_strength      NUMERIC(6,2),
    institutional_backing   NUMERIC(6,2),
    processed_date          DATE,
    processing_batch        TEXT,
    batch_number            INTEGER,
    source_file             TEXT,
    loaded_at               TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (score_date, symbol)
);

CREATE VIEW scores.v_latest_fundamental_scores AS
SELECT DISTINCT ON (symbol) *
FROM scores.fundamental_scores
ORDER BY symbol, score_date DESC, loaded_at DESC;

-- MA breadth per stock per snapshot (from NIFTY500_Market_Breadth_*.csv)
CREATE TABLE scores.ma_breadth (
    snapshot_date       DATE        NOT NULL,
    symbol              TEXT        NOT NULL,
    current_price       NUMERIC(12,2),
    sma_20              NUMERIC(12,2),
    sma_50              NUMERIC(12,2),
    sma_100             NUMERIC(12,2),
    sma_200             NUMERIC(12,2),
    above_20dma         BOOLEAN,
    above_50dma         BOOLEAN,
    above_100dma        BOOLEAN,
    above_200dma        BOOLEAN,
    ma_count_above      INTEGER GENERATED ALWAYS AS (
        (above_20dma::int + above_50dma::int + above_100dma::int + above_200dma::int)
    ) STORED,
    PRIMARY KEY (snapshot_date, symbol)
);

-- Index strength scores (from all_indexes_top5_analysis_*.csv)
CREATE TABLE scores.index_strength (
    score_date          DATE        NOT NULL,
    index_name          TEXT        NOT NULL,
    index_strength      NUMERIC(6,2),
    rank                INTEGER,
    symbol              TEXT,
    company_name        TEXT,
    market_cap_cat      TEXT,
    current_price       NUMERIC(12,2),
    change_1d_pct       NUMERIC(8,4),
    change_1w_pct       NUMERIC(8,4),
    change_1m_pct       NUMERIC(8,4),
    technical_score     NUMERIC(6,2),
    rsi                 NUMERIC(6,2),
    relative_strength   NUMERIC(8,4),
    can_slim_score      NUMERIC(6,2),
    minervini_score     NUMERIC(6,2),
    enhanced_fund_score NUMERIC(6,2),
    trend_signal        TEXT,
    trading_signal      TEXT,
    trading_value       NUMERIC(18,4),
    PRIMARY KEY (score_date, index_name, symbol)
);

-- Sector top stocks (from all_sectors_top5_analysis_*.csv)
CREATE TABLE scores.sector_top_stocks (
    score_date          DATE        NOT NULL,
    sector_name         TEXT        NOT NULL,
    sector_strength     NUMERIC(6,2),
    total_stocks        INTEGER,
    rank                INTEGER,
    symbol              TEXT        NOT NULL,
    company_name        TEXT,
    market_cap_cat      TEXT,
    current_price       NUMERIC(12,2),
    change_1d_pct       NUMERIC(8,4),
    change_1w_pct       NUMERIC(8,4),
    change_1m_pct       NUMERIC(8,4),
    technical_score     NUMERIC(6,2),
    rsi                 NUMERIC(6,2),
    relative_strength   NUMERIC(8,4),
    can_slim_score      NUMERIC(6,2),
    minervini_score     NUMERIC(6,2),
    enhanced_fund_score NUMERIC(6,2),
    trend_signal        TEXT,
    trading_signal      TEXT,
    trading_value       NUMERIC(18,4),
    PRIMARY KEY (score_date, sector_name, symbol)
);

-- =============================================================================
-- 5. SIGNALS — Trading Signals, Flows, Events, Alerts
-- =============================================================================

-- Full signal log with targets/stops and outcome tracking
CREATE TABLE signals.signal_log (
    id                  BIGSERIAL   PRIMARY KEY,
    date_issued         DATE        NOT NULL,
    symbol              TEXT        NOT NULL,
    sector              TEXT,
    company             TEXT,
    signal              TEXT,           -- BUY / SELL / HOLD / WATCH
    setup_class         TEXT,           -- Stage2_Breakout / Momentum / etc.
    investment_score    NUMERIC(6,2),
    technical_score     NUMERIC(6,2),
    rsi                 NUMERIC(6,2),
    supertrend_state    TEXT,
    price_at_issue      NUMERIC(12,2),
    entry_low           NUMERIC(12,2),
    entry_high          NUMERIC(12,2),
    stop_loss           NUMERIC(12,2),
    target_1            NUMERIC(12,2),
    target_2            NUMERIC(12,2),
    regime_at_issue     TEXT,
    -- F&O context at signal time
    fno_pcr             NUMERIC(8,4),
    fno_oi_change_5d    NUMERIC(8,4),
    fno_buildup         TEXT,
    fno_signal          TEXT,
    -- FII/Insider context
    fii_flow_signal     TEXT,
    insider_alert       TEXT,
    insider_score       NUMERIC(6,2),
    insider_detail      TEXT,
    -- Outcome
    date_resolved       DATE,
    price_at_resolution NUMERIC(12,2),
    return_pct          NUMERIC(8,4),
    hit_target          BOOLEAN,
    hit_stop            BOOLEAN,
    action_bucket       TEXT,
    action_reason       TEXT,
    UNIQUE (date_issued, symbol)
);

-- Daily FII/DII net flows
CREATE TABLE signals.fii_dii_flows (
    trade_date          DATE        PRIMARY KEY,
    fii_net_today       NUMERIC(14,2),   -- crores
    dii_net_today       NUMERIC(14,2),
    fii_net_5d          NUMERIC(14,2),
    dii_net_5d          NUMERIC(14,2),
    flow_signal         TEXT,
    fii_trend           TEXT,
    dii_trend           TEXT,
    days_in_window      INTEGER,
    updated_at          TIMESTAMPTZ DEFAULT now()
);

-- Market regime history
CREATE TABLE signals.regime_history (
    trade_date          DATE        PRIMARY KEY,
    regime              TEXT,           -- BULL / BEAR / CHOP / RECOVERY
    confidence          NUMERIC(5,2),
    days_in_regime      INTEGER,
    updated_at          TIMESTAMPTZ DEFAULT now()
);

-- Bulk and block deals (from data/_insider_cache/)
CREATE TABLE signals.bulk_block_deals (
    id                  BIGSERIAL   PRIMARY KEY,
    deal_date           DATE        NOT NULL,
    symbol              TEXT        NOT NULL,
    security_name       TEXT,
    entity              TEXT,
    side                TEXT,           -- BUY / SELL
    qty                 BIGINT,
    price               NUMERIC(12,4),
    deal_type           TEXT,           -- BULK_DEAL / BLOCK_DEAL
    remarks             TEXT,
    source              TEXT,
    created_at          TIMESTAMPTZ DEFAULT now(),
    UNIQUE (deal_date, symbol, entity, side, deal_type)
);

-- Corporate events (dividends, results, splits, AGM)
CREATE TABLE signals.corporate_events (
    id                  BIGSERIAL   PRIMARY KEY,
    symbol              TEXT        NOT NULL,
    event_type          TEXT        NOT NULL,  -- RESULTS / DIVIDEND / SPLIT / BONUS / AGM
    event_date          DATE,
    purpose_raw         TEXT,
    detail              TEXT,
    source              TEXT,
    created_at          TIMESTAMPTZ DEFAULT now(),
    UNIQUE (symbol, event_type, event_date)
);

-- Aggregated insider/institutional alerts (from data/insider_alerts_agg.csv)
CREATE TABLE signals.insider_alerts (
    id                  BIGSERIAL   PRIMARY KEY,
    alert_date          DATE        NOT NULL DEFAULT CURRENT_DATE,
    symbol              TEXT        NOT NULL,
    alert_type          TEXT,
    entity              TEXT,
    qty                 BIGINT,
    value_cr            NUMERIC(14,4),
    category            TEXT,
    detail              TEXT,
    source              TEXT,
    insider_score       NUMERIC(6,2),
    created_at          TIMESTAMPTZ DEFAULT now(),
    UNIQUE (alert_date, symbol, entity, alert_type)
);

-- System-generated watchlist alerts
CREATE TABLE signals.watchlist_alerts (
    id                  BIGSERIAL   PRIMARY KEY,
    alert_ts            TIMESTAMPTZ DEFAULT now(),
    symbol              TEXT,
    alert_type          TEXT,
    message             TEXT,
    priority            TEXT        DEFAULT 'MEDIUM',  -- HIGH / MEDIUM / LOW
    acknowledged        BOOLEAN     DEFAULT FALSE,
    ack_ts              TIMESTAMPTZ
);

-- =============================================================================
-- 6. BREADTH — Market and Sector Breadth
-- =============================================================================

-- Daily market breadth (from data/breadth_history.csv + market_breadth SQLite)
CREATE TABLE breadth.market_daily (
    trade_date          DATE        PRIMARY KEY,
    -- Advance/Decline
    advances            INTEGER,
    declines            INTEGER,
    unchanged           INTEGER,
    adv_volume          BIGINT,
    dec_volume          BIGINT,
    net_ad              INTEGER,
    ad_oscillator       NUMERIC(12,4),
    ad_summation        NUMERIC(14,4),
    ad_signal           TEXT,
    -- TRIN (Arms Index)
    trin                NUMERIC(8,4),
    trin_5d             NUMERIC(8,4),
    trin_signal         TEXT,
    trin_5d_signal      TEXT,
    divergence          TEXT,
    -- Signal counts
    total_stocks        INTEGER,
    strong_buy_count    INTEGER,
    buy_count           INTEGER,
    hold_count          INTEGER,
    weak_hold_count     INTEGER,
    sell_count          INTEGER,
    bullish_pct         NUMERIC(6,2),
    bearish_pct         NUMERIC(6,2),
    avg_technical_score NUMERIC(6,2),
    market_sentiment    TEXT,
    nifty500_close      NUMERIC(12,2),
    generated_at        TIMESTAMPTZ
);

-- Sector-level breadth (from data/sector_breadth.csv)
CREATE TABLE breadth.sector_daily (
    snapshot_date       DATE        NOT NULL,
    sector              TEXT        NOT NULL,
    index_name          TEXT,
    pct_above_50dma     NUMERIC(6,2),
    change_5d           NUMERIC(6,2),
    breadth_signal      TEXT,
    divergence_alert    TEXT,
    PRIMARY KEY (snapshot_date, sector)
);

-- % stocks above each MA by date (aggregated from scores.ma_breadth)
-- Populated by refresh function — no direct inserts
CREATE TABLE breadth.ma_pct_above (
    snapshot_date       DATE        PRIMARY KEY,
    pct_above_20dma     NUMERIC(6,2),
    pct_above_50dma     NUMERIC(6,2),
    pct_above_100dma    NUMERIC(6,2),
    pct_above_200dma    NUMERIC(6,2),
    stage2_pct          NUMERIC(6,2),   -- % stocks in Stage 2
    updated_at          TIMESTAMPTZ DEFAULT now()
);

-- =============================================================================
-- 7. MACRO — Economic Indicators, Global Correlations, Seasonal
-- =============================================================================

-- Raw FRED series data (from data/_macro_cache/fred_*.csv)
CREATE TABLE macro.fred_series (
    series_id           TEXT        NOT NULL,  -- e.g. DEXINUS, DGS10
    observation_date    DATE        NOT NULL,
    value               NUMERIC(20,6),
    PRIMARY KEY (series_id, observation_date)
);

-- Processed macro indicators (from data/macro_proxy_signals.csv)
CREATE TABLE macro.indicators (
    snapshot_date       DATE        NOT NULL,
    indicator           TEXT        NOT NULL,
    series_id           TEXT,
    frequency           TEXT,
    latest_value        NUMERIC(14,4),
    latest_date         DATE,
    trend               TEXT,
    momentum_1m_pct     NUMERIC(8,4),
    momentum_3m_pct     NUMERIC(8,4),
    z_score             NUMERIC(8,4),
    signal_score        NUMERIC(6,2),
    PRIMARY KEY (snapshot_date, indicator)
);

-- NSE vs global asset correlations (from data/global_correlations.csv)
CREATE TABLE macro.global_correlations (
    snapshot_date       DATE        NOT NULL,
    asset               TEXT        NOT NULL,
    price               NUMERIC(14,4),
    corr_30d            NUMERIC(6,4),
    corr_60d            NUMERIC(6,4),
    change_pct          NUMERIC(8,4),
    alert               TEXT,
    PRIMARY KEY (snapshot_date, asset)
);

-- Macro-driven sector tailwinds (from data/macro_sector_tailwind.csv)
CREATE TABLE macro.sector_tailwinds (
    snapshot_date       DATE        NOT NULL,
    sector_name         TEXT        NOT NULL,
    macro_tailwind      TEXT,
    macro_detail        TEXT,
    PRIMARY KEY (snapshot_date, sector_name)
);

-- Monthly seasonal return patterns (from data/seasonal_monthly_returns.csv)
CREATE TABLE macro.seasonal_returns (
    symbol              TEXT        NOT NULL,
    period              TEXT        NOT NULL,   -- e.g. "2024-01"
    month_num           INTEGER,
    close               NUMERIC(12,2),
    return_pct          NUMERIC(8,4),
    PRIMARY KEY (symbol, period)
);

-- =============================================================================
-- 8. PORTFOLIO — Holdings & Transactions
-- =============================================================================

CREATE TABLE portfolio.holdings (
    id                  BIGSERIAL   PRIMARY KEY,
    symbol              TEXT        NOT NULL,
    qty                 NUMERIC(14,4) NOT NULL,
    avg_cost            NUMERIC(12,4),
    buy_date            DATE,
    account             TEXT        DEFAULT 'DEFAULT',
    notes               TEXT,
    created_at          TIMESTAMPTZ DEFAULT now(),
    updated_at          TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE portfolio.transactions (
    id                  BIGSERIAL   PRIMARY KEY,
    trade_date          DATE        NOT NULL,
    symbol              TEXT        NOT NULL,
    action              TEXT        NOT NULL,   -- BUY / SELL
    qty                 NUMERIC(14,4) NOT NULL,
    price               NUMERIC(12,4) NOT NULL,
    brokerage           NUMERIC(10,4) DEFAULT 0,
    taxes               NUMERIC(10,4) DEFAULT 0,
    account             TEXT        DEFAULT 'DEFAULT',
    notes               TEXT,
    created_at          TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE portfolio.pnl_snapshots (
    snapshot_date       DATE        NOT NULL,
    symbol              TEXT        NOT NULL,
    qty                 NUMERIC(14,4),
    avg_cost            NUMERIC(12,4),
    current_price       NUMERIC(12,4),
    market_value        NUMERIC(16,4),
    unrealised_pnl      NUMERIC(16,4),
    unrealised_pnl_pct  NUMERIC(8,4),
    day_pnl             NUMERIC(16,4),
    PRIMARY KEY (snapshot_date, symbol)
);

-- =============================================================================
-- INDEXES — All performance-critical access patterns
-- =============================================================================

-- market.equity_eod
CREATE INDEX idx_eq_eod_symbol     ON market.equity_eod (symbol, trade_date DESC);
CREATE INDEX idx_eq_eod_date       ON market.equity_eod (trade_date DESC);
CREATE INDEX idx_eq_eod_changepct  ON market.equity_eod (trade_date DESC, change_pct DESC);

-- market.index_eod
CREATE INDEX idx_idx_eod_symbol    ON market.index_eod (index_symbol, trade_date DESC);

-- market.intraday_snapshots
CREATE INDEX idx_intraday_date     ON market.intraday_snapshots (trade_date DESC, symbol);

-- derivatives.fno_eod
CREATE INDEX idx_fno_symbol_date   ON derivatives.fno_eod (symbol, trade_date DESC);
CREATE INDEX idx_fno_date_instr    ON derivatives.fno_eod (trade_date, instrument);
CREATE INDEX idx_fno_expiry        ON derivatives.fno_eod (expiry_date, symbol);

-- scores.daily_scores
CREATE INDEX idx_ds_symbol_date    ON scores.daily_scores (symbol, score_date DESC);
CREATE INDEX idx_ds_date           ON scores.daily_scores (score_date DESC);
CREATE INDEX idx_ds_signal         ON scores.daily_scores (score_date DESC, trading_signal);
CREATE INDEX idx_ds_tech_score     ON scores.daily_scores (score_date DESC, technical_score DESC);
CREATE INDEX idx_ds_sector         ON scores.daily_scores (sector, score_date DESC);

-- scores.stage_snapshots
CREATE INDEX idx_ss_symbol_date    ON scores.stage_snapshots (symbol, snapshot_date DESC);
CREATE INDEX idx_ss_date           ON scores.stage_snapshots (snapshot_date DESC);
CREATE INDEX idx_ss_stage          ON scores.stage_snapshots (stage, snapshot_date DESC);
CREATE INDEX idx_ss_inv_score      ON scores.stage_snapshots (snapshot_date DESC, investment_score DESC);
CREATE INDEX idx_ss_signal         ON scores.stage_snapshots (trading_signal, snapshot_date DESC);
CREATE INDEX idx_ss_sector         ON scores.stage_snapshots (sector, snapshot_date DESC);

-- scores.ma_breadth
CREATE INDEX idx_mab_date          ON scores.ma_breadth (snapshot_date DESC);
CREATE INDEX idx_mab_symbol        ON scores.ma_breadth (symbol, snapshot_date DESC);

-- signals.signal_log
CREATE INDEX idx_sl_date           ON signals.signal_log (date_issued DESC);
CREATE INDEX idx_sl_symbol         ON signals.signal_log (symbol, date_issued DESC);
CREATE INDEX idx_sl_signal         ON signals.signal_log (signal, date_issued DESC);

-- signals.bulk_block_deals
CREATE INDEX idx_bbd_date          ON signals.bulk_block_deals (deal_date DESC);
CREATE INDEX idx_bbd_symbol        ON signals.bulk_block_deals (symbol, deal_date DESC);

-- signals.corporate_events
CREATE INDEX idx_ce_date           ON signals.corporate_events (event_date);
CREATE INDEX idx_ce_symbol         ON signals.corporate_events (symbol);

-- ref.instruments — fuzzy search
CREATE INDEX idx_inst_sym_trgm     ON ref.instruments USING gin (symbol gin_trgm_ops);
CREATE INDEX idx_inst_name_trgm    ON ref.instruments USING gin (company_name gin_trgm_ops);

-- macro.fred_series
CREATE INDEX idx_fred_date         ON macro.fred_series (observation_date DESC);

-- =============================================================================
-- MATERIALIZED VIEWS — Refreshed after each daily_refresh.py run
-- =============================================================================

-- Latest stage snapshot per symbol
CREATE MATERIALIZED VIEW scores.mv_latest_snapshot AS
SELECT DISTINCT ON (symbol) *
FROM scores.stage_snapshots
ORDER BY symbol, snapshot_date DESC;

CREATE UNIQUE INDEX ON scores.mv_latest_snapshot (symbol);
CREATE INDEX ON scores.mv_latest_snapshot (stage);
CREATE INDEX ON scores.mv_latest_snapshot (trading_signal);
CREATE INDEX ON scores.mv_latest_snapshot (investment_score DESC NULLS LAST);
CREATE INDEX ON scores.mv_latest_snapshot (sector);

-- Latest daily scores per symbol
CREATE MATERIALIZED VIEW scores.mv_latest_daily AS
SELECT DISTINCT ON (symbol) *
FROM scores.daily_scores
ORDER BY symbol, score_date DESC;

CREATE UNIQUE INDEX ON scores.mv_latest_daily (symbol);
CREATE INDEX ON scores.mv_latest_daily (technical_score DESC NULLS LAST);
CREATE INDEX ON scores.mv_latest_daily (trading_signal);

-- Stage 2 leaders — current Stage 2 stocks ranked by investment score
CREATE MATERIALIZED VIEW scores.mv_stage2_leaders AS
SELECT
    s.symbol, s.company_name, s.sector, s.market_cap_cat,
    s.price, s.live_price, s.change_1d_pct, s.change_1w_pct,
    s.investment_score, s.technical_score, s.enhanced_fund_score,
    s.can_slim_score, s.minervini_score, s.rsi,
    s.trading_signal, s.trend_signal, s.supertrend_state,
    s.stage_score, s.snapshot_date,
    -- join in long-term patterns
    lt.consolidation_breakout, lt.cup_handle, lt.long_term_uptrend,
    lt.momentum_breakout, lt.pattern_count
FROM scores.mv_latest_snapshot s
LEFT JOIN scores.long_term_screeners lt
    ON lt.symbol = s.symbol AND lt.score_date = s.snapshot_date
WHERE s.stage = 'STAGE_2'
ORDER BY s.investment_score DESC NULLS LAST;

CREATE UNIQUE INDEX ON scores.mv_stage2_leaders (symbol);

-- Sector performance summary
CREATE MATERIALIZED VIEW scores.mv_sector_summary AS
SELECT
    sector,
    snapshot_date,
    COUNT(*)                                                AS total_stocks,
    COUNT(*) FILTER (WHERE stage = 'STAGE_2')              AS stage2_count,
    ROUND(AVG(investment_score)::NUMERIC, 2)               AS avg_inv_score,
    ROUND(AVG(technical_score)::NUMERIC, 2)                AS avg_tech_score,
    ROUND(AVG(rsi)::NUMERIC, 2)                            AS avg_rsi,
    ROUND(AVG(enhanced_fund_score)::NUMERIC, 2)            AS avg_fund_score,
    COUNT(*) FILTER (WHERE trading_signal IN ('BUY','STRONG_BUY'))   AS buy_count,
    COUNT(*) FILTER (WHERE trading_signal IN ('SELL','STRONG_SELL')) AS sell_count,
    COUNT(*) FILTER (WHERE trading_signal = 'HOLD')        AS hold_count,
    ROUND(AVG(change_1d_pct)::NUMERIC, 4)                  AS avg_change_1d,
    ROUND(AVG(change_1w_pct)::NUMERIC, 4)                  AS avg_change_1w,
    ROUND(AVG(change_1m_pct)::NUMERIC, 4)                  AS avg_change_1m
FROM scores.mv_latest_snapshot
WHERE sector IS NOT NULL
GROUP BY sector, snapshot_date
ORDER BY avg_inv_score DESC NULLS LAST;

CREATE UNIQUE INDEX ON scores.mv_sector_summary (sector, snapshot_date);

-- Top movers (gainers + losers from latest daily scores)
CREATE MATERIALIZED VIEW scores.mv_top_movers AS
SELECT
    symbol, company_name, sector, market_cap_cat,
    current_price, change_1d_pct, change_1w_pct,
    technical_score, enhanced_fund_score, trading_signal, rsi,
    score_date,
    RANK() OVER (ORDER BY change_1d_pct DESC NULLS LAST) AS gainer_rank,
    RANK() OVER (ORDER BY change_1d_pct ASC  NULLS LAST) AS loser_rank
FROM scores.mv_latest_daily
WHERE change_1d_pct IS NOT NULL;

CREATE UNIQUE INDEX ON scores.mv_top_movers (symbol);

-- Market pulse: latest breadth + FII/DII + regime in one row
CREATE MATERIALIZED VIEW breadth.mv_market_pulse AS
SELECT
    b.trade_date,
    b.advances, b.declines, b.net_ad,
    b.ad_oscillator, b.trin, b.trin_signal,
    b.market_sentiment, b.bullish_pct, b.avg_technical_score,
    b.strong_buy_count, b.buy_count, b.sell_count,
    b.total_stocks,
    f.fii_net_today, f.dii_net_today,
    f.fii_net_5d, f.dii_net_5d, f.flow_signal,
    r.regime, r.confidence AS regime_confidence, r.days_in_regime,
    ma.pct_above_20dma, ma.pct_above_50dma,
    ma.pct_above_100dma, ma.pct_above_200dma, ma.stage2_pct
FROM breadth.market_daily b
LEFT JOIN signals.fii_dii_flows  f  ON f.trade_date = b.trade_date
LEFT JOIN signals.regime_history  r  ON r.trade_date = b.trade_date
LEFT JOIN breadth.ma_pct_above   ma  ON ma.snapshot_date = b.trade_date
ORDER BY b.trade_date DESC;

CREATE UNIQUE INDEX ON breadth.mv_market_pulse (trade_date);

-- Upcoming corporate events (next 30 days) — regular view, always live
CREATE VIEW signals.v_upcoming_events AS
SELECT symbol, event_type, event_date, detail
FROM signals.corporate_events
WHERE event_date BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '30 days'
ORDER BY event_date;

-- =============================================================================
-- UTILITY FUNCTIONS
-- =============================================================================

-- Refresh all materialized views (call after daily_refresh.py)
CREATE OR REPLACE FUNCTION refresh_all_views()
RETURNS void LANGUAGE plpgsql AS $$
DECLARE t0 TIMESTAMPTZ := clock_timestamp();
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY scores.mv_latest_snapshot;
    REFRESH MATERIALIZED VIEW CONCURRENTLY scores.mv_latest_daily;
    REFRESH MATERIALIZED VIEW CONCURRENTLY scores.mv_stage2_leaders;
    REFRESH MATERIALIZED VIEW CONCURRENTLY scores.mv_sector_summary;
    REFRESH MATERIALIZED VIEW CONCURRENTLY scores.mv_top_movers;
    REFRESH MATERIALIZED VIEW CONCURRENTLY breadth.mv_market_pulse;
    RAISE NOTICE 'All views refreshed in %ms', EXTRACT(EPOCH FROM (clock_timestamp()-t0))*1000;
END;
$$;

-- Populate breadth.ma_pct_above from scores.ma_breadth for a given date
CREATE OR REPLACE FUNCTION breadth.compute_ma_pct(p_date DATE)
RETURNS void LANGUAGE plpgsql AS $$
DECLARE
    v_n INTEGER;
    v_20 NUMERIC; v_50 NUMERIC; v_100 NUMERIC; v_200 NUMERIC;
    v_s2 NUMERIC;
BEGIN
    SELECT COUNT(*), 
           ROUND(100.0*SUM(above_20dma::int)/NULLIF(COUNT(*),0),2),
           ROUND(100.0*SUM(above_50dma::int)/NULLIF(COUNT(*),0),2),
           ROUND(100.0*SUM(above_100dma::int)/NULLIF(COUNT(*),0),2),
           ROUND(100.0*SUM(above_200dma::int)/NULLIF(COUNT(*),0),2)
    INTO v_n, v_20, v_50, v_100, v_200
    FROM scores.ma_breadth WHERE snapshot_date = p_date;

    SELECT ROUND(100.0*COUNT(*)/NULLIF(v_n,0),2)
    INTO v_s2
    FROM scores.stage_snapshots
    WHERE snapshot_date = p_date AND stage = 'STAGE_2';

    INSERT INTO breadth.ma_pct_above
        (snapshot_date, pct_above_20dma, pct_above_50dma, pct_above_100dma,
         pct_above_200dma, stage2_pct, updated_at)
    VALUES (p_date, v_20, v_50, v_100, v_200, v_s2, now())
    ON CONFLICT (snapshot_date) DO UPDATE SET
        pct_above_20dma  = EXCLUDED.pct_above_20dma,
        pct_above_50dma  = EXCLUDED.pct_above_50dma,
        pct_above_100dma = EXCLUDED.pct_above_100dma,
        pct_above_200dma = EXCLUDED.pct_above_200dma,
        stage2_pct       = EXCLUDED.stage2_pct,
        updated_at       = now();
END;
$$;

CREATE SCHEMA IF NOT EXISTS recommendation_reports;

CREATE TABLE IF NOT EXISTS recommendation_reports.runs (
    run_id TEXT PRIMARY KEY,
    generated_at TIMESTAMPTZ NOT NULL,
    as_of TEXT,
    report_path TEXT,
    evidence_path TEXT,
    recommendation_count INTEGER NOT NULL DEFAULT 0,
    market_regime JSONB NOT NULL DEFAULT '{}'::jsonb,
    source_trail JSONB NOT NULL DEFAULT '{}'::jsonb,
    missing_evidence JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS recommendation_reports.evidence (
    run_id TEXT NOT NULL REFERENCES recommendation_reports.runs(run_id) ON DELETE CASCADE,
    scope TEXT NOT NULL,
    subject TEXT NOT NULL,
    evidence JSONB NOT NULL,
    PRIMARY KEY (run_id, scope, subject)
);

CREATE TABLE IF NOT EXISTS recommendation_reports.recommendations (
    run_id TEXT NOT NULL REFERENCES recommendation_reports.runs(run_id) ON DELETE CASCADE,
    subject TEXT NOT NULL,
    scope TEXT NOT NULL,
    label TEXT NOT NULL,
    confidence TEXT NOT NULL,
    score NUMERIC,
    payload JSONB NOT NULL,
    PRIMARY KEY (run_id, subject, scope)
);

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'recommendation_reports'
          AND table_name = 'recommendations'
          AND column_name = 'policy'
    ) AND NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'recommendation_reports'
          AND table_name = 'recommendations'
          AND column_name = 'payload'
    ) THEN
        ALTER TABLE recommendation_reports.recommendations RENAME COLUMN policy TO payload;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_recommendation_reports_runs_generated_at
    ON recommendation_reports.runs (generated_at DESC);

CREATE INDEX IF NOT EXISTS idx_recommendation_reports_recommendations_label
    ON recommendation_reports.recommendations (label);
