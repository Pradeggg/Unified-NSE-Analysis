-- =============================================================================
-- NSE Market Intelligence — Screener Schema
-- 40 pre-computed screens across 7 categories
-- All screens run nightly after EOD data load
--
-- Categories:
--   TECHNICAL    — Price action, moving averages, momentum, patterns (12 screens)
--   CANSLIM      — William O'Neil CAN SLIM framework (6 screens)
--   FUNDAMENTAL  — Valuation, quality, earnings (6 screens)
--   GROWTH       — Revenue/earnings growth, expansion (5 screens)
--   PIOTROSKI    — Piotroski F-Score based screens (3 screens)
--   MACRO        — Sector tailwinds, global linkage, FII flows (4 screens)
--   COMPOSITE    — Multi-factor combined conviction screens (4 screens)
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS screener;

-- =============================================================================
-- SCREEN CATALOG — Metadata for all 40 screens
-- =============================================================================

CREATE TABLE screener.screen_definitions (
    screen_id           TEXT        PRIMARY KEY,
    screen_name         TEXT        NOT NULL,
    category            TEXT        NOT NULL,   -- TECHNICAL/CANSLIM/FUNDAMENTAL/GROWTH/PIOTROSKI/MACRO/COMPOSITE
    subcategory         TEXT,
    description         TEXT        NOT NULL,
    rationale           TEXT,                   -- Why this screen matters
    direction           TEXT        DEFAULT 'BULLISH',  -- BULLISH/BEARISH/NEUTRAL
    min_score           NUMERIC(5,2) DEFAULT 0,
    data_source         TEXT        DEFAULT 'EOD',  -- EOD/LIVE/FUNDAMENTAL
    sort_col            TEXT,                    -- which column to rank by
    sort_dir            TEXT        DEFAULT 'DESC',
    is_active           BOOLEAN     DEFAULT TRUE,
    tags                TEXT[],
    created_at          TIMESTAMPTZ DEFAULT now()
);

-- =============================================================================
-- DAILY SCREEN RESULTS — One row per (run_date, screen_id, symbol)
-- =============================================================================

CREATE TABLE screener.screen_results (
    run_date            DATE        NOT NULL,
    screen_id           TEXT        NOT NULL REFERENCES screener.screen_definitions(screen_id),
    symbol              TEXT        NOT NULL,
    company_name        TEXT,
    sector              TEXT,
    market_cap_cat      TEXT,
    -- Core price context
    price               NUMERIC(12,2),
    change_1d_pct       NUMERIC(8,4),
    change_1w_pct       NUMERIC(8,4),
    change_1m_pct       NUMERIC(8,4),
    -- Screen-specific score (normalised 0-100)
    screen_score        NUMERIC(6,2),
    -- Key indicator values (what triggered this screen)
    indicator_1_name    TEXT,
    indicator_1_value   NUMERIC(12,4),
    indicator_2_name    TEXT,
    indicator_2_value   NUMERIC(12,4),
    indicator_3_name    TEXT,
    indicator_3_value   NUMERIC(12,4),
    -- Standard scores (always populated for cross-screen comparison)
    investment_score    NUMERIC(6,2),
    technical_score     NUMERIC(6,2),
    rsi                 NUMERIC(6,2),
    enhanced_fund_score NUMERIC(6,2),
    can_slim_score      NUMERIC(6,2),
    minervini_score     NUMERIC(6,2),
    stage               TEXT,
    trading_signal      TEXT,
    -- Rank within screen (1 = best)
    rank_in_screen      INTEGER,
    PRIMARY KEY (run_date, screen_id, symbol)
);

CREATE INDEX idx_sr_run_date        ON screener.screen_results (run_date DESC);
CREATE INDEX idx_sr_screen_date     ON screener.screen_results (screen_id, run_date DESC);
CREATE INDEX idx_sr_symbol          ON screener.screen_results (symbol, run_date DESC);
CREATE INDEX idx_sr_score           ON screener.screen_results (run_date DESC, screen_score DESC);
CREATE INDEX idx_sr_sector          ON screener.screen_results (sector, run_date DESC);

-- =============================================================================
-- COMPOSITE SCORE — How many screens each stock passes per day
-- =============================================================================

CREATE TABLE screener.stock_screen_summary (
    run_date            DATE        NOT NULL,
    symbol              TEXT        NOT NULL,
    company_name        TEXT,
    sector              TEXT,
    market_cap_cat      TEXT,
    price               NUMERIC(12,2),
    change_1d_pct       NUMERIC(8,4),
    -- Screen pass counts by category
    screens_passed_total    INTEGER DEFAULT 0,
    screens_technical       INTEGER DEFAULT 0,
    screens_canslim         INTEGER DEFAULT 0,
    screens_fundamental     INTEGER DEFAULT 0,
    screens_growth          INTEGER DEFAULT 0,
    screens_piotroski       INTEGER DEFAULT 0,
    screens_macro           INTEGER DEFAULT 0,
    screens_composite       INTEGER DEFAULT 0,
    -- Aggregate scores
    investment_score    NUMERIC(6,2),
    technical_score     NUMERIC(6,2),
    enhanced_fund_score NUMERIC(6,2),
    can_slim_score      NUMERIC(6,2),
    stage               TEXT,
    trading_signal      TEXT,
    -- The screen IDs this stock passed (for quick display)
    passed_screens      TEXT[],
    -- Conviction tier based on total screens passed
    conviction_tier     TEXT GENERATED ALWAYS AS (
        CASE
            WHEN screens_passed_total >= 15 THEN 'ULTRA_HIGH'
            WHEN screens_passed_total >= 10 THEN 'HIGH'
            WHEN screens_passed_total >= 6  THEN 'MEDIUM'
            WHEN screens_passed_total >= 3  THEN 'LOW'
            ELSE 'MINIMAL'
        END
    ) STORED,
    PRIMARY KEY (run_date, symbol)
);

CREATE INDEX idx_sss_date           ON screener.stock_screen_summary (run_date DESC);
CREATE INDEX idx_sss_total          ON screener.stock_screen_summary (run_date DESC, screens_passed_total DESC);
CREATE INDEX idx_sss_conviction     ON screener.stock_screen_summary (conviction_tier, run_date DESC);
CREATE INDEX idx_sss_sector         ON screener.stock_screen_summary (sector, run_date DESC);

-- =============================================================================
-- SCREEN ALERT LOG — When a stock newly enters/exits a screen
-- =============================================================================

CREATE TABLE screener.screen_alerts (
    id                  BIGSERIAL   PRIMARY KEY,
    alert_date          DATE        NOT NULL DEFAULT CURRENT_DATE,
    screen_id           TEXT        NOT NULL,
    symbol              TEXT        NOT NULL,
    company_name        TEXT,
    event_type          TEXT        NOT NULL,  -- ENTRY / EXIT
    screen_score        NUMERIC(6,2),
    price               NUMERIC(12,2),
    days_in_screen      INTEGER,               -- consecutive days before exit
    created_at          TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_sa_date            ON screener.screen_alerts (alert_date DESC);
CREATE INDEX idx_sa_symbol          ON screener.screen_alerts (symbol, alert_date DESC);
CREATE INDEX idx_sa_screen          ON screener.screen_alerts (screen_id, alert_date DESC);

-- =============================================================================
-- MATERIALIZED VIEW — Latest screen results (today's run)
-- =============================================================================

CREATE MATERIALIZED VIEW screener.mv_latest_results AS
SELECT DISTINCT ON (screen_id, symbol) *
FROM screener.screen_results
ORDER BY screen_id, symbol, run_date DESC;

CREATE UNIQUE INDEX ON screener.mv_latest_results (screen_id, symbol);
CREATE INDEX ON screener.mv_latest_results (screen_id, screen_score DESC);
CREATE INDEX ON screener.mv_latest_results (symbol);

CREATE MATERIALIZED VIEW screener.mv_latest_summary AS
SELECT DISTINCT ON (symbol) *
FROM screener.stock_screen_summary
ORDER BY symbol, run_date DESC;

CREATE UNIQUE INDEX ON screener.mv_latest_summary (symbol);
CREATE INDEX ON screener.mv_latest_summary (screens_passed_total DESC);
CREATE INDEX ON screener.mv_latest_summary (conviction_tier);

-- =============================================================================
-- SEED: 40 SCREEN DEFINITIONS
-- =============================================================================

INSERT INTO screener.screen_definitions
    (screen_id, screen_name, category, subcategory, description, rationale,
     direction, sort_col, tags)
VALUES

-- ─── TECHNICAL (12) ──────────────────────────────────────────────────────────

('T01_STAGE2_BREAKOUT',
 'Stage 2 Breakout Leaders',
 'TECHNICAL', 'Weinstein',
 'Stocks in Weinstein Stage 2 with BUY/STRONG_BUY signal and investment score ≥ 65',
 'Stage 2 is the primary advancing phase. Combining with strong composite score filters noise.',
 'BULLISH', 'investment_score',
 ARRAY['stage2','weinstein','breakout','trending']),

('T02_MINERVINI_VCP',
 'Minervini VCP Setup',
 'TECHNICAL', 'Minervini',
 'Volatility Contraction Pattern — high Minervini score (≥ 14) with price in Stage 2 and low ATR',
 'VCP stocks are coiling for a breakout. High Minervini score signals the contraction is genuine.',
 'BULLISH', 'minervini_score',
 ARRAY['vcp','minervini','coiling','setup']),

('T03_RSI_MOMENTUM',
 'RSI Momentum Zone',
 'TECHNICAL', 'RSI',
 'RSI between 55-70 (momentum zone) with uptrend signal and positive relative strength',
 'Stocks in RSI 55-70 are trending without being overbought — sweet spot for continuation.',
 'BULLISH', 'rsi',
 ARRAY['rsi','momentum','trending']),

('T04_RSI_RECOVERY',
 'RSI Oversold Recovery',
 'TECHNICAL', 'RSI',
 'RSI recovering from oversold (was ≤ 35, now ≥ 42) with Stage 1 or 2 and positive 1-week change',
 'Stocks rebounding from oversold with improving price action — early bounce candidates.',
 'BULLISH', 'change_1w_pct',
 ARRAY['rsi','oversold','recovery','bounce']),

('T05_GOLDEN_CROSS',
 'Golden Cross Stocks',
 'TECHNICAL', 'Moving Average',
 'Stocks where SMA50 has recently crossed above SMA200 — golden cross confirmation',
 'The golden cross is a long-term bullish signal, especially when price is above both MAs.',
 'BULLISH', 'technical_score',
 ARRAY['golden_cross','sma','moving_average']),

('T06_TRIPLE_MA_ALIGNMENT',
 'Triple MA Alignment',
 'TECHNICAL', 'Moving Average',
 'Price > SMA20 > SMA50 > SMA200 — fully aligned bullish trend structure',
 'Triple alignment means all timeframes are in sync — the most reliable trend continuation setup.',
 'BULLISH', 'investment_score',
 ARRAY['triple_ma','alignment','trending','structure']),

('T07_52W_HIGH_BREAKOUT',
 '52-Week High Breakout',
 'TECHNICAL', 'Breakout',
 'Stocks within 3% of their 52-week high with volume confirmation and buy signal',
 'New highs beget new highs. Stocks at 52w highs are showing absolute strength.',
 'BULLISH', 'change_1w_pct',
 ARRAY['52w_high','breakout','strength']),

('T08_SUPERTREND_BUY',
 'Supertrend Buy Signal',
 'TECHNICAL', 'Supertrend',
 'Stocks with active Supertrend BUY state and Stage 2 classification',
 'Supertrend is a trend-following indicator. Combined with Stage 2 it confirms direction.',
 'BULLISH', 'investment_score',
 ARRAY['supertrend','trend','signal']),

('T09_VOLUME_SURGE',
 'Volume Surge Leaders',
 'TECHNICAL', 'Volume',
 'Top stocks by 1-day change with high trading value — unusual volume + price action',
 'Price moves on high volume are more meaningful — institutional participation signal.',
 'BULLISH', 'change_1d_pct',
 ARRAY['volume','surge','breakout','institutional']),

('T10_HIGH_TECH_SCORE',
 'Technical Score Elite',
 'TECHNICAL', 'Composite',
 'Top 50 stocks ranked by technical score (≥ 75) across all sectors',
 'Highest technical scores represent the best price/volume/momentum configuration.',
 'BULLISH', 'technical_score',
 ARRAY['technical','elite','momentum']),

('T11_STAGE4_DISTRIBUTION',
 'Stage 4 Deterioration (Short Watch)',
 'TECHNICAL', 'Weinstein',
 'Stocks entering Stage 4 decline with SELL signal and deteriorating scores',
 'Stage 4 stocks are in confirmed downtrend — avoid long, watch for short opportunities.',
 'BEARISH', 'investment_score',
 ARRAY['stage4','distribution','bearish','short']),

('T12_RANGE_CONTRACTION',
 'Price Range Contraction',
 'TECHNICAL', 'Pattern',
 'Stocks with narrowing price range (low ATR relative to history) — pre-breakout coiling',
 'Range contraction precedes range expansion. These stocks are building energy.',
 'NEUTRAL', 'investment_score',
 ARRAY['contraction','consolidation','coiling','setup']),

-- ─── CANSLIM (6) ─────────────────────────────────────────────────────────────

('C01_CANSLIM_ELITE',
 'CAN SLIM Elite (Score ≥ 18)',
 'CANSLIM', 'Composite',
 'Stocks with CAN SLIM score ≥ 18/25 — top-tier growth with institutional backing',
 'High CANSLIM scores indicate the full O''Neil checklist is firing — most selective screen.',
 'BULLISH', 'can_slim_score',
 ARRAY['canslim','oneil','growth','institutional']),

('C02_CANSLIM_STRONG',
 'CAN SLIM Strong (Score 14-17)',
 'CANSLIM', 'Composite',
 'CANSLIM score 14-17: solid growth characteristics with good institutional activity',
 'Broader CANSLIM universe — quality growth stocks not yet at elite threshold.',
 'BULLISH', 'can_slim_score',
 ARRAY['canslim','growth','quality']),

('C03_MARKET_LEADERS',
 'Market Leaders (High RS)',
 'CANSLIM', 'Relative Strength',
 'Stocks with relative strength ≥ 20% outperformance vs Nifty 500 over 50 days',
 'The L in CANSLIM — buy leaders, not laggards. Top RS stocks drive index performance.',
 'BULLISH', 'relative_strength',
 ARRAY['relative_strength','leader','canslim','momentum']),

('C04_NEW_HIGH_MOMENTUM',
 'New High with Institutional Volume',
 'CANSLIM', 'New Highs',
 'Near 52-week highs with high CANSLIM score and improving institutional backing',
 'N + I in CANSLIM — new highs driven by institutional buying is the strongest setup.',
 'BULLISH', 'can_slim_score',
 ARRAY['new_high','institutional','canslim','breakout']),

('C05_EARNINGS_MOMENTUM',
 'Earnings Momentum Stocks',
 'CANSLIM', 'Earnings',
 'High earnings quality score (≥ 65) with accelerating price momentum and buy signal',
 'C and A in CANSLIM — current and annual earnings are the fundamental drivers.',
 'BULLISH', 'earnings_quality',
 ARRAY['earnings','momentum','canslim','growth']),

('C06_SUPPLY_DEMAND_BREAKOUT',
 'Supply & Demand Breakout',
 'CANSLIM', 'Supply/Demand',
 'Stocks with price > SMA50 > SMA200 + high volume + CANSLIM score ≥ 12',
 'S in CANSLIM — demand overcoming supply, price structure confirms accumulation.',
 'BULLISH', 'can_slim_score',
 ARRAY['supply_demand','accumulation','canslim']),

-- ─── FUNDAMENTAL (6) ─────────────────────────────────────────────────────────

('F01_QUALITY_GROWTH',
 'Quality Growth (Fund ≥ 70)',
 'FUNDAMENTAL', 'Quality',
 'Enhanced fundamental score ≥ 70 with buy signal — highest quality businesses',
 'Stocks with strong fundamentals AND buy signal are the safest long-term holds.',
 'BULLISH', 'enhanced_fund_score',
 ARRAY['quality','fundamental','growth']),

('F02_VALUE_MOMENTUM',
 'Value + Momentum Blend',
 'FUNDAMENTAL', 'Value',
 'Fund score 60-80 AND technical score ≥ 60 — quality at reasonable valuation with momentum',
 'The holy grail: good business + good price action. Reduces timing risk.',
 'BULLISH', 'investment_score',
 ARRAY['value','momentum','blend','quality']),

('F03_HIGH_EARNINGS_QUALITY',
 'High Earnings Quality',
 'FUNDAMENTAL', 'Earnings Quality',
 'Earnings quality score ≥ 70 — clean, sustainable earnings with low accruals risk',
 'High earnings quality means profits are real and repeatable — foundation for compounding.',
 'BULLISH', 'earnings_quality',
 ARRAY['earnings_quality','fundamental','sustainable']),

('F04_STRONG_BALANCE_SHEET',
 'Strong Balance Sheet',
 'FUNDAMENTAL', 'Financial Strength',
 'Financial strength score ≥ 70 with low debt, strong coverage, adequate liquidity',
 'Financially strong companies survive downturns and fund growth from internal cash.',
 'BULLISH', 'financial_strength',
 ARRAY['balance_sheet','financial_strength','low_debt']),

('F05_INSTITUTIONAL_FAVOURITES',
 'Institutional Favourites',
 'FUNDAMENTAL', 'Institutional',
 'Institutional backing score ≥ 65 with buy signal — stocks with strong institutional ownership',
 'Institutional ownership provides a quality floor and signals professional consensus.',
 'BULLISH', 'institutional_backing',
 ARRAY['institutional','ownership','quality']),

('F06_FUNDAMENTAL_IMPROVING',
 'Improving Fundamentals',
 'FUNDAMENTAL', 'Improving',
 'Stocks where fund score is in 50-65 range but all other scores improving — early rerating',
 'Stocks about to be re-rated higher — early entry before institutional discovery.',
 'BULLISH', 'investment_score',
 ARRAY['improving','rerating','fundamental','early']),

-- ─── GROWTH (5) ──────────────────────────────────────────────────────────────

('G01_SALES_GROWTH_LEADERS',
 'Sales Growth Leaders',
 'GROWTH', 'Revenue',
 'Top stocks ranked by sales growth score (≥ 70) with buy signal',
 'Revenue growth is the engine of stock appreciation — early cycle growth leaders.',
 'BULLISH', 'sales_growth',
 ARRAY['sales_growth','revenue','growth','leader']),

('G02_EARNINGS_ACCELERATION',
 'Earnings Acceleration',
 'GROWTH', 'Earnings',
 'Earnings quality ≥ 65 + CANSLIM ≥ 14 + positive price momentum — accelerating earnings',
 'Earnings acceleration is the single most predictive factor for above-market returns.',
 'BULLISH', 'earnings_quality',
 ARRAY['earnings','acceleration','growth','canslim']),

('G03_SMALL_CAP_GROWTH',
 'Small Cap Growth Gems',
 'GROWTH', 'Market Cap',
 'SMALL_CAP or MICRO_CAP stocks with investment score ≥ 60 + CANSLIM ≥ 14 + Stage 2',
 'Small cap stocks offer highest return potential when backed by strong growth metrics.',
 'BULLISH', 'investment_score',
 ARRAY['small_cap','growth','high_potential']),

('G04_MIDCAP_MOMENTUM',
 'Mid Cap Momentum',
 'GROWTH', 'Market Cap',
 'MID_CAP stocks with investment score ≥ 65 + Stage 2 + strong technical',
 'Mid caps balance growth potential with liquidity — often overlooked by large-cap analysts.',
 'BULLISH', 'investment_score',
 ARRAY['mid_cap','momentum','growth']),

('G05_SECTOR_ROTATION_LEADERS',
 'Sector Rotation Leaders',
 'GROWTH', 'Sector',
 'Top 3 stocks from the top 5 strongest sectors by avg investment score',
 'Sector rotation drives 80% of stock moves — being in the right sector matters most.',
 'BULLISH', 'investment_score',
 ARRAY['sector_rotation','leader','momentum']),

-- ─── PIOTROSKI (3) ───────────────────────────────────────────────────────────

('P01_HIGH_PIOTROSKI',
 'High Piotroski F-Score (≥ 7)',
 'PIOTROSKI', 'F-Score',
 'Stocks with Piotroski F-Score ≥ 7/9 — highest financial health across all 9 criteria',
 'F-Score ≥ 7 identifies financially strong, improving businesses. Historical alpha generator.',
 'BULLISH', 'piotroski_score',
 ARRAY['piotroski','fscore','quality','financial_health']),

('P02_PIOTROSKI_MOMENTUM',
 'Piotroski High + Technical Buy',
 'PIOTROSKI', 'Combined',
 'Piotroski ≥ 6 AND investment score ≥ 60 AND buy signal — quality + momentum combo',
 'Combining Piotroski with momentum ensures you buy improving businesses at the right time.',
 'BULLISH', 'investment_score',
 ARRAY['piotroski','momentum','quality','combined']),

('P03_LOW_PIOTROSKI_AVOID',
 'Low Piotroski Risk (Score ≤ 2)',
 'PIOTROSKI', 'Risk',
 'Stocks with Piotroski F-Score ≤ 2 — financially deteriorating, high fundamental risk',
 'F-Score ≤ 2 identifies financially weak companies — avoid or watch for shorts.',
 'BEARISH', 'piotroski_score',
 ARRAY['piotroski','risk','bearish','avoid']),

-- ─── MACRO (4) ───────────────────────────────────────────────────────────────

('M01_FII_BUYING_STAGE2',
 'FII Net Buying + Stage 2',
 'MACRO', 'FII/DII',
 'Stage 2 stocks in sectors with positive FII net flow in last 5 days',
 'Foreign institutional buying is a quality signal — smart money entering Stage 2 sectors.',
 'BULLISH', 'investment_score',
 ARRAY['fii','buying','stage2','institutional']),

('M02_SECTOR_MACRO_TAILWIND',
 'Macro Tailwind Sectors',
 'MACRO', 'Sector Tailwind',
 'Top stocks from sectors with positive macro tailwind signal',
 'Macro tailwinds amplify sector returns — being in a tailwind sector adds alpha.',
 'BULLISH', 'investment_score',
 ARRAY['macro','tailwind','sector','top_down']),

('M03_GLOBAL_OUTPERFORMERS',
 'NSE Global Correlation Outperformers',
 'MACRO', 'Global',
 'Stocks in sectors positively correlated with outperforming global indices',
 'Global markets drive 40%+ of NSE moves. Stocks aligned with global strength outperform.',
 'BULLISH', 'investment_score',
 ARRAY['global','correlation','outperform','macro']),

('M04_INSIDER_ACCUMULATION',
 'Insider / Institutional Accumulation',
 'MACRO', 'Insider',
 'Stocks with recent bulk/block deal BUY activity AND buy trading signal',
 'Insiders and institutions buying in bulk signals high conviction — follow the smart money.',
 'BULLISH', 'investment_score',
 ARRAY['insider','bulk_deal','accumulation','smart_money']),

-- ─── COMPOSITE (4) ───────────────────────────────────────────────────────────

('X01_HIGH_CONVICTION',
 'High Conviction — All Factors Aligned',
 'COMPOSITE', 'Multi-Factor',
 'Investment score ≥ 75 + Stage 2 + BUY signal + CANSLIM ≥ 15 + Fund score ≥ 60',
 'The most selective screen — requires alignment across all major frameworks simultaneously.',
 'BULLISH', 'investment_score',
 ARRAY['high_conviction','composite','multi_factor','elite']),

('X02_TURNAROUND_CANDIDATES',
 'Turnaround Candidates',
 'COMPOSITE', 'Turnaround',
 'Stocks transitioning Stage 1→2, improving scores QoQ, with recent volume pickup',
 'Early turnarounds offer the best risk/reward — catching the inflection before the crowd.',
 'BULLISH', 'investment_score',
 ARRAY['turnaround','stage_change','early','value']),

('X03_DEFENSIVE_QUALITY',
 'Defensive Quality (Bear Market Shield)',
 'COMPOSITE', 'Defensive',
 'Fund score ≥ 65 + Financial strength ≥ 65 + HOLD or better signal + Stage 1/2',
 'When markets turn bearish, these high-quality defensives outperform and preserve capital.',
 'NEUTRAL', 'financial_strength',
 ARRAY['defensive','quality','bear_market','safety']),

('X04_MOMENTUM_BEAST',
 'Momentum Beast — Strongest Momentum',
 'COMPOSITE', 'Momentum',
 'Top 30 stocks: RS ≥ 15% + CANSLIM ≥ 14 + Minervini ≥ 14 + Stage 2 + RSI 55-75',
 'Pure momentum — every momentum factor firing simultaneously. Trend is your friend.',
 'BULLISH', 'investment_score',
 ARRAY['momentum','beast','canslim','minervini','composite']);

-- =============================================================================
-- SCREEN COMPUTATION FUNCTION
-- Main function: run_all_screens(p_date DATE)
-- Reads from scores.stage_snapshots + scores.daily_scores + supporting tables
-- =============================================================================

CREATE OR REPLACE FUNCTION screener.run_all_screens(p_date DATE DEFAULT CURRENT_DATE)
RETURNS TABLE (screen_id TEXT, stocks_found INTEGER) LANGUAGE plpgsql AS $$
DECLARE
    v_snap_date DATE;
    v_count     INTEGER;
BEGIN
    -- Find the latest snapshot_date on or before p_date
    SELECT MAX(snapshot_date) INTO v_snap_date
    FROM scores.stage_snapshots
    WHERE snapshot_date <= p_date;

    IF v_snap_date IS NULL THEN
        RAISE NOTICE 'No snapshot data found for date %', p_date;
        RETURN;
    END IF;

    RAISE NOTICE 'Running screens for run_date=% using snapshot_date=%', p_date, v_snap_date;

    -- Clear previous results for this run_date
    DELETE FROM screener.screen_results WHERE run_date = p_date;
    DELETE FROM screener.stock_screen_summary WHERE run_date = p_date;

    -- ─────────────────────────────────────────────────────────────────────────
    -- T01: Stage 2 Breakout Leaders
    -- ─────────────────────────────────────────────────────────────────────────
    INSERT INTO screener.screen_results
        (run_date, screen_id, symbol, company_name, sector, market_cap_cat,
         price, change_1d_pct, change_1w_pct, change_1m_pct,
         screen_score, indicator_1_name, indicator_1_value,
         indicator_2_name, indicator_2_value, indicator_3_name, indicator_3_value,
         investment_score, technical_score, rsi, enhanced_fund_score,
         can_slim_score, minervini_score, stage, trading_signal, rank_in_screen)
    SELECT
        p_date, 'T01_STAGE2_BREAKOUT',
        symbol, company_name, sector, market_cap_cat,
        COALESCE(live_price, price), change_1d_pct, change_1w_pct, change_1m_pct,
        investment_score,
        'stage_score', stage_score, 'rsi', rsi, 'relative_strength', relative_strength,
        investment_score, technical_score, rsi, enhanced_fund_score,
        can_slim_score, minervini_score, stage, trading_signal,
        RANK() OVER (ORDER BY investment_score DESC NULLS LAST)
    FROM scores.stage_snapshots
    WHERE snapshot_date = v_snap_date
      AND stage = 'STAGE_2'
      AND trading_signal IN ('BUY','STRONG_BUY')
      AND investment_score >= 65;
    GET DIAGNOSTICS v_count = ROW_COUNT;
    screen_id := 'T01_STAGE2_BREAKOUT'; stocks_found := v_count; RETURN NEXT;

    -- ─────────────────────────────────────────────────────────────────────────
    -- T02: Minervini VCP
    -- ─────────────────────────────────────────────────────────────────────────
    INSERT INTO screener.screen_results
        (run_date, screen_id, symbol, company_name, sector, market_cap_cat,
         price, change_1d_pct, change_1w_pct, change_1m_pct, screen_score,
         indicator_1_name, indicator_1_value, indicator_2_name, indicator_2_value,
         investment_score, technical_score, rsi, enhanced_fund_score,
         can_slim_score, minervini_score, stage, trading_signal, rank_in_screen)
    SELECT
        p_date, 'T02_MINERVINI_VCP',
        symbol, company_name, sector, market_cap_cat,
        COALESCE(live_price, price), change_1d_pct, change_1w_pct, change_1m_pct,
        minervini_score,
        'minervini_score', minervini_score, 'stage_score', stage_score,
        investment_score, technical_score, rsi, enhanced_fund_score,
        can_slim_score, minervini_score, stage, trading_signal,
        RANK() OVER (ORDER BY minervini_score DESC NULLS LAST)
    FROM scores.stage_snapshots
    WHERE snapshot_date = v_snap_date
      AND minervini_score >= 14
      AND stage IN ('STAGE_1','STAGE_2')
      AND trading_signal IN ('BUY','STRONG_BUY','HOLD');
    GET DIAGNOSTICS v_count = ROW_COUNT;
    screen_id := 'T02_MINERVINI_VCP'; stocks_found := v_count; RETURN NEXT;

    -- ─────────────────────────────────────────────────────────────────────────
    -- T03: RSI Momentum Zone
    -- ─────────────────────────────────────────────────────────────────────────
    INSERT INTO screener.screen_results
        (run_date, screen_id, symbol, company_name, sector, market_cap_cat,
         price, change_1d_pct, change_1w_pct, change_1m_pct, screen_score,
         indicator_1_name, indicator_1_value, indicator_2_name, indicator_2_value,
         investment_score, technical_score, rsi, enhanced_fund_score,
         can_slim_score, minervini_score, stage, trading_signal, rank_in_screen)
    SELECT
        p_date, 'T03_RSI_MOMENTUM',
        symbol, company_name, sector, market_cap_cat,
        COALESCE(live_price, price), change_1d_pct, change_1w_pct, change_1m_pct,
        rsi,
        'rsi', rsi, 'relative_strength', relative_strength,
        investment_score, technical_score, rsi, enhanced_fund_score,
        can_slim_score, minervini_score, stage, trading_signal,
        RANK() OVER (ORDER BY investment_score DESC NULLS LAST)
    FROM scores.stage_snapshots
    WHERE snapshot_date = v_snap_date
      AND rsi BETWEEN 55 AND 70
      AND trend_signal IN ('BULLISH','STRONG_BULLISH')
      AND relative_strength > 0;
    GET DIAGNOSTICS v_count = ROW_COUNT;
    screen_id := 'T03_RSI_MOMENTUM'; stocks_found := v_count; RETURN NEXT;

    -- ─────────────────────────────────────────────────────────────────────────
    -- T04: RSI Recovery
    -- ─────────────────────────────────────────────────────────────────────────
    INSERT INTO screener.screen_results
        (run_date, screen_id, symbol, company_name, sector, market_cap_cat,
         price, change_1d_pct, change_1w_pct, change_1m_pct, screen_score,
         indicator_1_name, indicator_1_value, indicator_2_name, indicator_2_value,
         investment_score, technical_score, rsi, enhanced_fund_score,
         can_slim_score, minervini_score, stage, trading_signal, rank_in_screen)
    SELECT
        p_date, 'T04_RSI_RECOVERY',
        symbol, company_name, sector, market_cap_cat,
        COALESCE(live_price, price), change_1d_pct, change_1w_pct, change_1m_pct,
        rsi,
        'rsi', rsi, 'change_1w_pct', change_1w_pct,
        investment_score, technical_score, rsi, enhanced_fund_score,
        can_slim_score, minervini_score, stage, trading_signal,
        RANK() OVER (ORDER BY change_1w_pct DESC NULLS LAST)
    FROM scores.stage_snapshots
    WHERE snapshot_date = v_snap_date
      AND rsi BETWEEN 38 AND 50
      AND stage IN ('STAGE_1','STAGE_2')
      AND change_1w_pct > 0;
    GET DIAGNOSTICS v_count = ROW_COUNT;
    screen_id := 'T04_RSI_RECOVERY'; stocks_found := v_count; RETURN NEXT;

    -- ─────────────────────────────────────────────────────────────────────────
    -- T05: Golden Cross (use ma_breadth + stage_snapshots)
    -- ─────────────────────────────────────────────────────────────────────────
    INSERT INTO screener.screen_results
        (run_date, screen_id, symbol, company_name, sector, market_cap_cat,
         price, change_1d_pct, change_1w_pct, change_1m_pct, screen_score,
         indicator_1_name, indicator_1_value, indicator_2_name, indicator_2_value,
         investment_score, technical_score, rsi, enhanced_fund_score,
         can_slim_score, minervini_score, stage, trading_signal, rank_in_screen)
    SELECT
        p_date, 'T05_GOLDEN_CROSS',
        s.symbol, s.company_name, s.sector, s.market_cap_cat,
        COALESCE(s.live_price, s.price), s.change_1d_pct, s.change_1w_pct, s.change_1m_pct,
        s.technical_score,
        'above_50dma', m.above_50dma::int::numeric, 'above_200dma', m.above_200dma::int::numeric,
        s.investment_score, s.technical_score, s.rsi, s.enhanced_fund_score,
        s.can_slim_score, s.minervini_score, s.stage, s.trading_signal,
        RANK() OVER (ORDER BY s.technical_score DESC NULLS LAST)
    FROM scores.stage_snapshots s
    JOIN scores.ma_breadth m
      ON m.symbol = s.symbol AND m.snapshot_date = v_snap_date
    WHERE s.snapshot_date = v_snap_date
      AND m.above_50dma = TRUE
      AND m.above_200dma = TRUE
      AND s.trading_signal IN ('BUY','STRONG_BUY')
      AND s.stage IN ('STAGE_1','STAGE_2');
    GET DIAGNOSTICS v_count = ROW_COUNT;
    screen_id := 'T05_GOLDEN_CROSS'; stocks_found := v_count; RETURN NEXT;

    -- ─────────────────────────────────────────────────────────────────────────
    -- T06: Triple MA Alignment (above all 4 MAs)
    -- ─────────────────────────────────────────────────────────────────────────
    INSERT INTO screener.screen_results
        (run_date, screen_id, symbol, company_name, sector, market_cap_cat,
         price, change_1d_pct, change_1w_pct, change_1m_pct, screen_score,
         indicator_1_name, indicator_1_value,
         investment_score, technical_score, rsi, enhanced_fund_score,
         can_slim_score, minervini_score, stage, trading_signal, rank_in_screen)
    SELECT
        p_date, 'T06_TRIPLE_MA_ALIGNMENT',
        s.symbol, s.company_name, s.sector, s.market_cap_cat,
        COALESCE(s.live_price, s.price), s.change_1d_pct, s.change_1w_pct, s.change_1m_pct,
        s.investment_score,
        'ma_count_above', m.ma_count_above::numeric,
        s.investment_score, s.technical_score, s.rsi, s.enhanced_fund_score,
        s.can_slim_score, s.minervini_score, s.stage, s.trading_signal,
        RANK() OVER (ORDER BY s.investment_score DESC NULLS LAST)
    FROM scores.stage_snapshots s
    JOIN scores.ma_breadth m
      ON m.symbol = s.symbol AND m.snapshot_date = v_snap_date
    WHERE s.snapshot_date = v_snap_date
      AND m.ma_count_above = 4
      AND s.stage IN ('STAGE_1','STAGE_2');
    GET DIAGNOSTICS v_count = ROW_COUNT;
    screen_id := 'T06_TRIPLE_MA_ALIGNMENT'; stocks_found := v_count; RETURN NEXT;

    -- ─────────────────────────────────────────────────────────────────────────
    -- T07: 52-Week High Breakout
    -- ─────────────────────────────────────────────────────────────────────────
    INSERT INTO screener.screen_results
        (run_date, screen_id, symbol, company_name, sector, market_cap_cat,
         price, change_1d_pct, change_1w_pct, change_1m_pct, screen_score,
         indicator_1_name, indicator_1_value, indicator_2_name, indicator_2_value,
         investment_score, technical_score, rsi, enhanced_fund_score,
         can_slim_score, minervini_score, stage, trading_signal, rank_in_screen)
    SELECT
        p_date, 'T07_52W_HIGH_BREAKOUT',
        s.symbol, s.company_name, s.sector, s.market_cap_cat,
        COALESCE(s.live_price, s.price), s.change_1d_pct, s.change_1w_pct, s.change_1m_pct,
        s.change_1w_pct,
        'change_1w_pct', s.change_1w_pct, 'can_slim_score', s.can_slim_score,
        s.investment_score, s.technical_score, s.rsi, s.enhanced_fund_score,
        s.can_slim_score, s.minervini_score, s.stage, s.trading_signal,
        RANK() OVER (ORDER BY s.change_1w_pct DESC NULLS LAST)
    FROM scores.stage_snapshots s
    JOIN market.week52_extremes w
      ON w.symbol = s.symbol
    WHERE s.snapshot_date = v_snap_date
      AND w.snapshot_date = (SELECT MAX(snapshot_date) FROM market.week52_extremes)
      AND w.status = 'H'
      AND s.trading_signal IN ('BUY','STRONG_BUY');
    GET DIAGNOSTICS v_count = ROW_COUNT;
    screen_id := 'T07_52W_HIGH_BREAKOUT'; stocks_found := v_count; RETURN NEXT;

    -- ─────────────────────────────────────────────────────────────────────────
    -- T08: Supertrend Buy
    -- ─────────────────────────────────────────────────────────────────────────
    INSERT INTO screener.screen_results
        (run_date, screen_id, symbol, company_name, sector, market_cap_cat,
         price, change_1d_pct, change_1w_pct, change_1m_pct, screen_score,
         indicator_1_name, indicator_1_value,
         investment_score, technical_score, rsi, enhanced_fund_score,
         can_slim_score, minervini_score, stage, trading_signal, rank_in_screen)
    SELECT
        p_date, 'T08_SUPERTREND_BUY',
        symbol, company_name, sector, market_cap_cat,
        COALESCE(live_price, price), change_1d_pct, change_1w_pct, change_1m_pct,
        investment_score,
        'supertrend_state', CASE WHEN supertrend_state='BUY' THEN 1 ELSE 0 END::numeric,
        investment_score, technical_score, rsi, enhanced_fund_score,
        can_slim_score, minervini_score, stage, trading_signal,
        RANK() OVER (ORDER BY investment_score DESC NULLS LAST)
    FROM scores.stage_snapshots
    WHERE snapshot_date = v_snap_date
      AND supertrend_state = 'BUY'
      AND stage = 'STAGE_2';
    GET DIAGNOSTICS v_count = ROW_COUNT;
    screen_id := 'T08_SUPERTREND_BUY'; stocks_found := v_count; RETURN NEXT;

    -- ─────────────────────────────────────────────────────────────────────────
    -- T09: Volume Surge Leaders
    -- ─────────────────────────────────────────────────────────────────────────
    INSERT INTO screener.screen_results
        (run_date, screen_id, symbol, company_name, sector, market_cap_cat,
         price, change_1d_pct, change_1w_pct, change_1m_pct, screen_score,
         indicator_1_name, indicator_1_value,
         investment_score, technical_score, rsi, enhanced_fund_score,
         can_slim_score, minervini_score, stage, trading_signal, rank_in_screen)
    SELECT
        p_date, 'T09_VOLUME_SURGE',
        d.symbol, d.company_name, s.sector, d.market_cap_cat,
        d.current_price, d.change_1d_pct, d.change_1w_pct, d.change_1m_pct,
        d.change_1d_pct,
        'trading_value', d.trading_value,
        s.investment_score, d.technical_score, d.rsi, d.enhanced_fund_score,
        d.can_slim_score, d.minervini_score, s.stage, d.trading_signal,
        RANK() OVER (ORDER BY d.change_1d_pct DESC NULLS LAST)
    FROM scores.daily_scores d
    LEFT JOIN scores.stage_snapshots s
      ON s.symbol = d.symbol AND s.snapshot_date = v_snap_date
    WHERE d.score_date = v_snap_date
      AND d.change_1d_pct > 2
      AND d.trading_value > 500000000  -- >50Cr turnover
      AND d.trading_signal IN ('BUY','STRONG_BUY');
    GET DIAGNOSTICS v_count = ROW_COUNT;
    screen_id := 'T09_VOLUME_SURGE'; stocks_found := v_count; RETURN NEXT;

    -- ─────────────────────────────────────────────────────────────────────────
    -- T10: Technical Score Elite
    -- ─────────────────────────────────────────────────────────────────────────
    INSERT INTO screener.screen_results
        (run_date, screen_id, symbol, company_name, sector, market_cap_cat,
         price, change_1d_pct, change_1w_pct, change_1m_pct, screen_score,
         indicator_1_name, indicator_1_value,
         investment_score, technical_score, rsi, enhanced_fund_score,
         can_slim_score, minervini_score, stage, trading_signal, rank_in_screen)
    SELECT
        p_date, 'T10_HIGH_TECH_SCORE',
        symbol, company_name, sector, market_cap_cat,
        COALESCE(live_price, price), change_1d_pct, change_1w_pct, change_1m_pct,
        technical_score,
        'technical_score', technical_score,
        investment_score, technical_score, rsi, enhanced_fund_score,
        can_slim_score, minervini_score, stage, trading_signal,
        RANK() OVER (ORDER BY technical_score DESC NULLS LAST)
    FROM scores.stage_snapshots
    WHERE snapshot_date = v_snap_date
      AND technical_score >= 75
    ORDER BY technical_score DESC
    LIMIT 50;
    GET DIAGNOSTICS v_count = ROW_COUNT;
    screen_id := 'T10_HIGH_TECH_SCORE'; stocks_found := v_count; RETURN NEXT;

    -- ─────────────────────────────────────────────────────────────────────────
    -- T11: Stage 4 Distribution
    -- ─────────────────────────────────────────────────────────────────────────
    INSERT INTO screener.screen_results
        (run_date, screen_id, symbol, company_name, sector, market_cap_cat,
         price, change_1d_pct, change_1w_pct, change_1m_pct, screen_score,
         indicator_1_name, indicator_1_value,
         investment_score, technical_score, rsi, enhanced_fund_score,
         can_slim_score, minervini_score, stage, trading_signal, rank_in_screen)
    SELECT
        p_date, 'T11_STAGE4_DISTRIBUTION',
        symbol, company_name, sector, market_cap_cat,
        COALESCE(live_price, price), change_1d_pct, change_1w_pct, change_1m_pct,
        100 - COALESCE(investment_score,50),  -- inverted for bearish
        'stage_score', stage_score,
        investment_score, technical_score, rsi, enhanced_fund_score,
        can_slim_score, minervini_score, stage, trading_signal,
        RANK() OVER (ORDER BY investment_score ASC NULLS LAST)
    FROM scores.stage_snapshots
    WHERE snapshot_date = v_snap_date
      AND stage = 'STAGE_4'
      AND trading_signal IN ('SELL','STRONG_SELL');
    GET DIAGNOSTICS v_count = ROW_COUNT;
    screen_id := 'T11_STAGE4_DISTRIBUTION'; stocks_found := v_count; RETURN NEXT;

    -- ─────────────────────────────────────────────────────────────────────────
    -- T12: Range Contraction
    -- ─────────────────────────────────────────────────────────────────────────
    INSERT INTO screener.screen_results
        (run_date, screen_id, symbol, company_name, sector, market_cap_cat,
         price, change_1d_pct, change_1w_pct, change_1m_pct, screen_score,
         indicator_1_name, indicator_1_value, indicator_2_name, indicator_2_value,
         investment_score, technical_score, rsi, enhanced_fund_score,
         can_slim_score, minervini_score, stage, trading_signal, rank_in_screen)
    SELECT
        p_date, 'T12_RANGE_CONTRACTION',
        s.symbol, s.company_name, s.sector, s.market_cap_cat,
        COALESCE(s.live_price, s.price), s.change_1d_pct, s.change_1w_pct, s.change_1m_pct,
        s.minervini_score,
        'minervini_score', s.minervini_score, 'investment_score', s.investment_score,
        s.investment_score, s.technical_score, s.rsi, s.enhanced_fund_score,
        s.can_slim_score, s.minervini_score, s.stage, s.trading_signal,
        RANK() OVER (ORDER BY s.investment_score DESC NULLS LAST)
    FROM scores.stage_snapshots s
    LEFT JOIN scores.long_term_screeners lt
      ON lt.symbol = s.symbol AND lt.score_date = v_snap_date
    WHERE s.snapshot_date = v_snap_date
      AND s.minervini_score >= 12
      AND s.stage IN ('STAGE_1','STAGE_2')
      AND (lt.consolidation_breakout = TRUE OR lt.cup_handle = TRUE);
    GET DIAGNOSTICS v_count = ROW_COUNT;
    screen_id := 'T12_RANGE_CONTRACTION'; stocks_found := v_count; RETURN NEXT;

    -- ─────────────────────────────────────────────────────────────────────────
    -- C01: CANSLIM Elite
    -- ─────────────────────────────────────────────────────────────────────────
    INSERT INTO screener.screen_results
        (run_date, screen_id, symbol, company_name, sector, market_cap_cat,
         price, change_1d_pct, change_1w_pct, change_1m_pct, screen_score,
         indicator_1_name, indicator_1_value,
         investment_score, technical_score, rsi, enhanced_fund_score,
         can_slim_score, minervini_score, stage, trading_signal, rank_in_screen)
    SELECT
        p_date, 'C01_CANSLIM_ELITE',
        symbol, company_name, sector, market_cap_cat,
        COALESCE(live_price, price), change_1d_pct, change_1w_pct, change_1m_pct,
        can_slim_score,
        'can_slim_score', can_slim_score,
        investment_score, technical_score, rsi, enhanced_fund_score,
        can_slim_score, minervini_score, stage, trading_signal,
        RANK() OVER (ORDER BY can_slim_score DESC NULLS LAST)
    FROM scores.stage_snapshots
    WHERE snapshot_date = v_snap_date
      AND can_slim_score >= 18;
    GET DIAGNOSTICS v_count = ROW_COUNT;
    screen_id := 'C01_CANSLIM_ELITE'; stocks_found := v_count; RETURN NEXT;

    -- ─────────────────────────────────────────────────────────────────────────
    -- C02: CANSLIM Strong
    -- ─────────────────────────────────────────────────────────────────────────
    INSERT INTO screener.screen_results
        (run_date, screen_id, symbol, company_name, sector, market_cap_cat,
         price, change_1d_pct, change_1w_pct, change_1m_pct, screen_score,
         indicator_1_name, indicator_1_value,
         investment_score, technical_score, rsi, enhanced_fund_score,
         can_slim_score, minervini_score, stage, trading_signal, rank_in_screen)
    SELECT
        p_date, 'C02_CANSLIM_STRONG',
        symbol, company_name, sector, market_cap_cat,
        COALESCE(live_price, price), change_1d_pct, change_1w_pct, change_1m_pct,
        can_slim_score,
        'can_slim_score', can_slim_score,
        investment_score, technical_score, rsi, enhanced_fund_score,
        can_slim_score, minervini_score, stage, trading_signal,
        RANK() OVER (ORDER BY can_slim_score DESC NULLS LAST)
    FROM scores.stage_snapshots
    WHERE snapshot_date = v_snap_date
      AND can_slim_score BETWEEN 14 AND 17;
    GET DIAGNOSTICS v_count = ROW_COUNT;
    screen_id := 'C02_CANSLIM_STRONG'; stocks_found := v_count; RETURN NEXT;

    -- ─────────────────────────────────────────────────────────────────────────
    -- C03: Market Leaders (High RS)
    -- ─────────────────────────────────────────────────────────────────────────
    INSERT INTO screener.screen_results
        (run_date, screen_id, symbol, company_name, sector, market_cap_cat,
         price, change_1d_pct, change_1w_pct, change_1m_pct, screen_score,
         indicator_1_name, indicator_1_value,
         investment_score, technical_score, rsi, enhanced_fund_score,
         can_slim_score, minervini_score, stage, trading_signal, rank_in_screen)
    SELECT
        p_date, 'C03_MARKET_LEADERS',
        symbol, company_name, sector, market_cap_cat,
        COALESCE(live_price, price), change_1d_pct, change_1w_pct, change_1m_pct,
        LEAST(relative_strength * 200, 100),  -- normalize to 0-100
        'relative_strength', relative_strength,
        investment_score, technical_score, rsi, enhanced_fund_score,
        can_slim_score, minervini_score, stage, trading_signal,
        RANK() OVER (ORDER BY relative_strength DESC NULLS LAST)
    FROM scores.stage_snapshots
    WHERE snapshot_date = v_snap_date
      AND relative_strength >= 0.20
      AND stage IN ('STAGE_1','STAGE_2');
    GET DIAGNOSTICS v_count = ROW_COUNT;
    screen_id := 'C03_MARKET_LEADERS'; stocks_found := v_count; RETURN NEXT;

    -- ─────────────────────────────────────────────────────────────────────────
    -- C04: New High Momentum (CANSLIM + near highs)
    -- ─────────────────────────────────────────────────────────────────────────
    INSERT INTO screener.screen_results
        (run_date, screen_id, symbol, company_name, sector, market_cap_cat,
         price, change_1d_pct, change_1w_pct, change_1m_pct, screen_score,
         indicator_1_name, indicator_1_value, indicator_2_name, indicator_2_value,
         investment_score, technical_score, rsi, enhanced_fund_score,
         can_slim_score, minervini_score, stage, trading_signal, rank_in_screen)
    SELECT
        p_date, 'C04_NEW_HIGH_MOMENTUM',
        s.symbol, s.company_name, s.sector, s.market_cap_cat,
        COALESCE(s.live_price, s.price), s.change_1d_pct, s.change_1w_pct, s.change_1m_pct,
        s.can_slim_score,
        'can_slim_score', s.can_slim_score, 'institutional_backing', s.institutional_backing,
        s.investment_score, s.technical_score, s.rsi, s.enhanced_fund_score,
        s.can_slim_score, s.minervini_score, s.stage, s.trading_signal,
        RANK() OVER (ORDER BY s.can_slim_score DESC NULLS LAST)
    FROM scores.stage_snapshots s
    JOIN market.week52_extremes w
      ON w.symbol = s.symbol
    WHERE s.snapshot_date = v_snap_date
      AND w.snapshot_date = (SELECT MAX(snapshot_date) FROM market.week52_extremes)
      AND w.status = 'H'
      AND s.can_slim_score >= 14
      AND s.institutional_backing >= 50;
    GET DIAGNOSTICS v_count = ROW_COUNT;
    screen_id := 'C04_NEW_HIGH_MOMENTUM'; stocks_found := v_count; RETURN NEXT;

    -- ─────────────────────────────────────────────────────────────────────────
    -- C05: Earnings Momentum
    -- ─────────────────────────────────────────────────────────────────────────
    INSERT INTO screener.screen_results
        (run_date, screen_id, symbol, company_name, sector, market_cap_cat,
         price, change_1d_pct, change_1w_pct, change_1m_pct, screen_score,
         indicator_1_name, indicator_1_value,
         investment_score, technical_score, rsi, enhanced_fund_score,
         can_slim_score, minervini_score, stage, trading_signal, rank_in_screen)
    SELECT
        p_date, 'C05_EARNINGS_MOMENTUM',
        symbol, company_name, sector, market_cap_cat,
        COALESCE(live_price, price), change_1d_pct, change_1w_pct, change_1m_pct,
        earnings_quality,
        'earnings_quality', earnings_quality,
        investment_score, technical_score, rsi, enhanced_fund_score,
        can_slim_score, minervini_score, stage, trading_signal,
        RANK() OVER (ORDER BY earnings_quality DESC NULLS LAST)
    FROM scores.stage_snapshots
    WHERE snapshot_date = v_snap_date
      AND earnings_quality >= 65
      AND change_1m_pct > 5
      AND trading_signal IN ('BUY','STRONG_BUY');
    GET DIAGNOSTICS v_count = ROW_COUNT;
    screen_id := 'C05_EARNINGS_MOMENTUM'; stocks_found := v_count; RETURN NEXT;

    -- ─────────────────────────────────────────────────────────────────────────
    -- C06: Supply & Demand Breakout
    -- ─────────────────────────────────────────────────────────────────────────
    INSERT INTO screener.screen_results
        (run_date, screen_id, symbol, company_name, sector, market_cap_cat,
         price, change_1d_pct, change_1w_pct, change_1m_pct, screen_score,
         indicator_1_name, indicator_1_value, indicator_2_name, indicator_2_value,
         investment_score, technical_score, rsi, enhanced_fund_score,
         can_slim_score, minervini_score, stage, trading_signal, rank_in_screen)
    SELECT
        p_date, 'C06_SUPPLY_DEMAND_BREAKOUT',
        s.symbol, s.company_name, s.sector, s.market_cap_cat,
        COALESCE(s.live_price, s.price), s.change_1d_pct, s.change_1w_pct, s.change_1m_pct,
        s.can_slim_score,
        'can_slim_score', s.can_slim_score, 'above_200dma', m.above_200dma::int::numeric,
        s.investment_score, s.technical_score, s.rsi, s.enhanced_fund_score,
        s.can_slim_score, s.minervini_score, s.stage, s.trading_signal,
        RANK() OVER (ORDER BY s.can_slim_score DESC NULLS LAST)
    FROM scores.stage_snapshots s
    JOIN scores.ma_breadth m ON m.symbol = s.symbol AND m.snapshot_date = v_snap_date
    WHERE s.snapshot_date = v_snap_date
      AND s.can_slim_score >= 12
      AND m.above_50dma = TRUE
      AND m.above_200dma = TRUE
      AND s.change_1w_pct > 2;
    GET DIAGNOSTICS v_count = ROW_COUNT;
    screen_id := 'C06_SUPPLY_DEMAND_BREAKOUT'; stocks_found := v_count; RETURN NEXT;

    -- ─────────────────────────────────────────────────────────────────────────
    -- F01-F06: Fundamental Screens
    -- ─────────────────────────────────────────────────────────────────────────
    INSERT INTO screener.screen_results
        (run_date, screen_id, symbol, company_name, sector, market_cap_cat,
         price, change_1d_pct, change_1w_pct, change_1m_pct, screen_score,
         indicator_1_name, indicator_1_value,
         investment_score, technical_score, rsi, enhanced_fund_score,
         can_slim_score, minervini_score, stage, trading_signal, rank_in_screen)
    SELECT p_date, 'F01_QUALITY_GROWTH',
        symbol, company_name, sector, market_cap_cat,
        COALESCE(live_price, price), change_1d_pct, change_1w_pct, change_1m_pct,
        enhanced_fund_score, 'enhanced_fund_score', enhanced_fund_score,
        investment_score, technical_score, rsi, enhanced_fund_score,
        can_slim_score, minervini_score, stage, trading_signal,
        RANK() OVER (ORDER BY enhanced_fund_score DESC NULLS LAST)
    FROM scores.stage_snapshots
    WHERE snapshot_date = v_snap_date AND enhanced_fund_score >= 70
      AND trading_signal IN ('BUY','STRONG_BUY');
    GET DIAGNOSTICS v_count = ROW_COUNT;
    screen_id := 'F01_QUALITY_GROWTH'; stocks_found := v_count; RETURN NEXT;

    INSERT INTO screener.screen_results
        (run_date, screen_id, symbol, company_name, sector, market_cap_cat,
         price, change_1d_pct, change_1w_pct, change_1m_pct, screen_score,
         indicator_1_name, indicator_1_value, indicator_2_name, indicator_2_value,
         investment_score, technical_score, rsi, enhanced_fund_score,
         can_slim_score, minervini_score, stage, trading_signal, rank_in_screen)
    SELECT p_date, 'F02_VALUE_MOMENTUM',
        symbol, company_name, sector, market_cap_cat,
        COALESCE(live_price, price), change_1d_pct, change_1w_pct, change_1m_pct,
        investment_score, 'enhanced_fund_score', enhanced_fund_score,
        'technical_score', technical_score,
        investment_score, technical_score, rsi, enhanced_fund_score,
        can_slim_score, minervini_score, stage, trading_signal,
        RANK() OVER (ORDER BY investment_score DESC NULLS LAST)
    FROM scores.stage_snapshots
    WHERE snapshot_date = v_snap_date
      AND enhanced_fund_score BETWEEN 60 AND 80
      AND technical_score >= 60;
    GET DIAGNOSTICS v_count = ROW_COUNT;
    screen_id := 'F02_VALUE_MOMENTUM'; stocks_found := v_count; RETURN NEXT;

    INSERT INTO screener.screen_results
        (run_date, screen_id, symbol, company_name, sector, market_cap_cat,
         price, change_1d_pct, change_1w_pct, change_1m_pct, screen_score,
         indicator_1_name, indicator_1_value,
         investment_score, technical_score, rsi, enhanced_fund_score,
         can_slim_score, minervini_score, stage, trading_signal, rank_in_screen)
    SELECT p_date, 'F03_HIGH_EARNINGS_QUALITY',
        symbol, company_name, sector, market_cap_cat,
        COALESCE(live_price, price), change_1d_pct, change_1w_pct, change_1m_pct,
        earnings_quality, 'earnings_quality', earnings_quality,
        investment_score, technical_score, rsi, enhanced_fund_score,
        can_slim_score, minervini_score, stage, trading_signal,
        RANK() OVER (ORDER BY earnings_quality DESC NULLS LAST)
    FROM scores.stage_snapshots
    WHERE snapshot_date = v_snap_date AND earnings_quality >= 70;
    GET DIAGNOSTICS v_count = ROW_COUNT;
    screen_id := 'F03_HIGH_EARNINGS_QUALITY'; stocks_found := v_count; RETURN NEXT;

    INSERT INTO screener.screen_results
        (run_date, screen_id, symbol, company_name, sector, market_cap_cat,
         price, change_1d_pct, change_1w_pct, change_1m_pct, screen_score,
         indicator_1_name, indicator_1_value,
         investment_score, technical_score, rsi, enhanced_fund_score,
         can_slim_score, minervini_score, stage, trading_signal, rank_in_screen)
    SELECT p_date, 'F04_STRONG_BALANCE_SHEET',
        symbol, company_name, sector, market_cap_cat,
        COALESCE(live_price, price), change_1d_pct, change_1w_pct, change_1m_pct,
        financial_strength, 'financial_strength', financial_strength,
        investment_score, technical_score, rsi, enhanced_fund_score,
        can_slim_score, minervini_score, stage, trading_signal,
        RANK() OVER (ORDER BY financial_strength DESC NULLS LAST)
    FROM scores.stage_snapshots
    WHERE snapshot_date = v_snap_date AND financial_strength >= 70;
    GET DIAGNOSTICS v_count = ROW_COUNT;
    screen_id := 'F04_STRONG_BALANCE_SHEET'; stocks_found := v_count; RETURN NEXT;

    INSERT INTO screener.screen_results
        (run_date, screen_id, symbol, company_name, sector, market_cap_cat,
         price, change_1d_pct, change_1w_pct, change_1m_pct, screen_score,
         indicator_1_name, indicator_1_value,
         investment_score, technical_score, rsi, enhanced_fund_score,
         can_slim_score, minervini_score, stage, trading_signal, rank_in_screen)
    SELECT p_date, 'F05_INSTITUTIONAL_FAVOURITES',
        symbol, company_name, sector, market_cap_cat,
        COALESCE(live_price, price), change_1d_pct, change_1w_pct, change_1m_pct,
        institutional_backing, 'institutional_backing', institutional_backing,
        investment_score, technical_score, rsi, enhanced_fund_score,
        can_slim_score, minervini_score, stage, trading_signal,
        RANK() OVER (ORDER BY institutional_backing DESC NULLS LAST)
    FROM scores.stage_snapshots
    WHERE snapshot_date = v_snap_date
      AND institutional_backing >= 65
      AND trading_signal IN ('BUY','STRONG_BUY');
    GET DIAGNOSTICS v_count = ROW_COUNT;
    screen_id := 'F05_INSTITUTIONAL_FAVOURITES'; stocks_found := v_count; RETURN NEXT;

    INSERT INTO screener.screen_results
        (run_date, screen_id, symbol, company_name, sector, market_cap_cat,
         price, change_1d_pct, change_1w_pct, change_1m_pct, screen_score,
         indicator_1_name, indicator_1_value, indicator_2_name, indicator_2_value,
         investment_score, technical_score, rsi, enhanced_fund_score,
         can_slim_score, minervini_score, stage, trading_signal, rank_in_screen)
    SELECT p_date, 'F06_FUNDAMENTAL_IMPROVING',
        symbol, company_name, sector, market_cap_cat,
        COALESCE(live_price, price), change_1d_pct, change_1w_pct, change_1m_pct,
        investment_score, 'enhanced_fund_score', enhanced_fund_score,
        'investment_score', investment_score,
        investment_score, technical_score, rsi, enhanced_fund_score,
        can_slim_score, minervini_score, stage, trading_signal,
        RANK() OVER (ORDER BY investment_score DESC NULLS LAST)
    FROM scores.stage_snapshots
    WHERE snapshot_date = v_snap_date
      AND enhanced_fund_score BETWEEN 50 AND 65
      AND investment_score >= 55
      AND change_1m_pct > 3;
    GET DIAGNOSTICS v_count = ROW_COUNT;
    screen_id := 'F06_FUNDAMENTAL_IMPROVING'; stocks_found := v_count; RETURN NEXT;

    -- ─────────────────────────────────────────────────────────────────────────
    -- G01-G05: Growth Screens
    -- ─────────────────────────────────────────────────────────────────────────
    INSERT INTO screener.screen_results
        (run_date, screen_id, symbol, company_name, sector, market_cap_cat,
         price, change_1d_pct, change_1w_pct, change_1m_pct, screen_score,
         indicator_1_name, indicator_1_value,
         investment_score, technical_score, rsi, enhanced_fund_score,
         can_slim_score, minervini_score, stage, trading_signal, rank_in_screen)
    SELECT p_date, 'G01_SALES_GROWTH_LEADERS',
        symbol, company_name, sector, market_cap_cat,
        COALESCE(live_price, price), change_1d_pct, change_1w_pct, change_1m_pct,
        sales_growth, 'sales_growth', sales_growth,
        investment_score, technical_score, rsi, enhanced_fund_score,
        can_slim_score, minervini_score, stage, trading_signal,
        RANK() OVER (ORDER BY sales_growth DESC NULLS LAST)
    FROM scores.stage_snapshots
    WHERE snapshot_date = v_snap_date
      AND sales_growth >= 70
      AND trading_signal IN ('BUY','STRONG_BUY');
    GET DIAGNOSTICS v_count = ROW_COUNT;
    screen_id := 'G01_SALES_GROWTH_LEADERS'; stocks_found := v_count; RETURN NEXT;

    INSERT INTO screener.screen_results
        (run_date, screen_id, symbol, company_name, sector, market_cap_cat,
         price, change_1d_pct, change_1w_pct, change_1m_pct, screen_score,
         indicator_1_name, indicator_1_value, indicator_2_name, indicator_2_value,
         investment_score, technical_score, rsi, enhanced_fund_score,
         can_slim_score, minervini_score, stage, trading_signal, rank_in_screen)
    SELECT p_date, 'G02_EARNINGS_ACCELERATION',
        symbol, company_name, sector, market_cap_cat,
        COALESCE(live_price, price), change_1d_pct, change_1w_pct, change_1m_pct,
        earnings_quality, 'earnings_quality', earnings_quality, 'can_slim_score', can_slim_score,
        investment_score, technical_score, rsi, enhanced_fund_score,
        can_slim_score, minervini_score, stage, trading_signal,
        RANK() OVER (ORDER BY earnings_quality DESC NULLS LAST)
    FROM scores.stage_snapshots
    WHERE snapshot_date = v_snap_date
      AND earnings_quality >= 65
      AND can_slim_score >= 14
      AND change_1m_pct > 5;
    GET DIAGNOSTICS v_count = ROW_COUNT;
    screen_id := 'G02_EARNINGS_ACCELERATION'; stocks_found := v_count; RETURN NEXT;

    INSERT INTO screener.screen_results
        (run_date, screen_id, symbol, company_name, sector, market_cap_cat,
         price, change_1d_pct, change_1w_pct, change_1m_pct, screen_score,
         indicator_1_name, indicator_1_value,
         investment_score, technical_score, rsi, enhanced_fund_score,
         can_slim_score, minervini_score, stage, trading_signal, rank_in_screen)
    SELECT p_date, 'G03_SMALL_CAP_GROWTH',
        symbol, company_name, sector, market_cap_cat,
        COALESCE(live_price, price), change_1d_pct, change_1w_pct, change_1m_pct,
        investment_score, 'investment_score', investment_score,
        investment_score, technical_score, rsi, enhanced_fund_score,
        can_slim_score, minervini_score, stage, trading_signal,
        RANK() OVER (ORDER BY investment_score DESC NULLS LAST)
    FROM scores.stage_snapshots
    WHERE snapshot_date = v_snap_date
      AND market_cap_cat IN ('SMALL_CAP','MICRO_CAP')
      AND investment_score >= 60
      AND can_slim_score >= 14
      AND stage = 'STAGE_2';
    GET DIAGNOSTICS v_count = ROW_COUNT;
    screen_id := 'G03_SMALL_CAP_GROWTH'; stocks_found := v_count; RETURN NEXT;

    INSERT INTO screener.screen_results
        (run_date, screen_id, symbol, company_name, sector, market_cap_cat,
         price, change_1d_pct, change_1w_pct, change_1m_pct, screen_score,
         indicator_1_name, indicator_1_value,
         investment_score, technical_score, rsi, enhanced_fund_score,
         can_slim_score, minervini_score, stage, trading_signal, rank_in_screen)
    SELECT p_date, 'G04_MIDCAP_MOMENTUM',
        symbol, company_name, sector, market_cap_cat,
        COALESCE(live_price, price), change_1d_pct, change_1w_pct, change_1m_pct,
        investment_score, 'investment_score', investment_score,
        investment_score, technical_score, rsi, enhanced_fund_score,
        can_slim_score, minervini_score, stage, trading_signal,
        RANK() OVER (ORDER BY investment_score DESC NULLS LAST)
    FROM scores.stage_snapshots
    WHERE snapshot_date = v_snap_date
      AND market_cap_cat = 'MID_CAP'
      AND investment_score >= 65
      AND stage = 'STAGE_2';
    GET DIAGNOSTICS v_count = ROW_COUNT;
    screen_id := 'G04_MIDCAP_MOMENTUM'; stocks_found := v_count; RETURN NEXT;

    -- G05: Sector Rotation Leaders (top stocks from top 5 sectors)
    INSERT INTO screener.screen_results
        (run_date, screen_id, symbol, company_name, sector, market_cap_cat,
         price, change_1d_pct, change_1w_pct, change_1m_pct, screen_score,
         indicator_1_name, indicator_1_value,
         investment_score, technical_score, rsi, enhanced_fund_score,
         can_slim_score, minervini_score, stage, trading_signal, rank_in_screen)
    WITH sector_ranks AS (
        SELECT sector, AVG(investment_score) AS avg_score,
               RANK() OVER (ORDER BY AVG(investment_score) DESC NULLS LAST) AS sect_rank
        FROM scores.stage_snapshots
        WHERE snapshot_date = v_snap_date AND sector IS NOT NULL
        GROUP BY sector
    ),
    top_in_sector AS (
        SELECT s.*, RANK() OVER (PARTITION BY s.sector ORDER BY s.investment_score DESC NULLS LAST) AS r
        FROM scores.stage_snapshots s
        JOIN sector_ranks sr ON sr.sector = s.sector AND sr.sect_rank <= 5
        WHERE s.snapshot_date = v_snap_date AND s.trading_signal IN ('BUY','STRONG_BUY')
    )
    SELECT p_date, 'G05_SECTOR_ROTATION_LEADERS',
        symbol, company_name, sector, market_cap_cat,
        COALESCE(live_price, price), change_1d_pct, change_1w_pct, change_1m_pct,
        investment_score, 'investment_score', investment_score,
        investment_score, technical_score, rsi, enhanced_fund_score,
        can_slim_score, minervini_score, stage, trading_signal, r
    FROM top_in_sector
    WHERE r <= 5;
    GET DIAGNOSTICS v_count = ROW_COUNT;
    screen_id := 'G05_SECTOR_ROTATION_LEADERS'; stocks_found := v_count; RETURN NEXT;

    -- ─────────────────────────────────────────────────────────────────────────
    -- P01-P03: Piotroski (use fundamentals table when available, else skip)
    -- ─────────────────────────────────────────────────────────────────────────
    INSERT INTO screener.screen_results
        (run_date, screen_id, symbol, company_name, sector, market_cap_cat,
         price, change_1d_pct, change_1w_pct, change_1m_pct, screen_score,
         indicator_1_name, indicator_1_value, indicator_2_name, indicator_2_value,
         investment_score, technical_score, rsi, enhanced_fund_score,
         can_slim_score, minervini_score, stage, trading_signal, rank_in_screen)
    SELECT p_date, 'P01_HIGH_PIOTROSKI',
        s.symbol, s.company_name, s.sector, s.market_cap_cat,
        COALESCE(s.live_price, s.price), s.change_1d_pct, s.change_1w_pct, s.change_1m_pct,
        f.piotroski_score, 'piotroski_score', f.piotroski_score,
        'enhanced_fund_score', s.enhanced_fund_score,
        s.investment_score, s.technical_score, s.rsi, s.enhanced_fund_score,
        s.can_slim_score, s.minervini_score, s.stage, s.trading_signal,
        RANK() OVER (ORDER BY f.piotroski_score DESC NULLS LAST, s.investment_score DESC NULLS LAST)
    FROM scores.stage_snapshots s
    JOIN scores.fundamentals f ON f.symbol = s.symbol
    WHERE s.snapshot_date = v_snap_date
      AND f.piotroski_score >= 7;
    GET DIAGNOSTICS v_count = ROW_COUNT;
    screen_id := 'P01_HIGH_PIOTROSKI'; stocks_found := v_count; RETURN NEXT;

    INSERT INTO screener.screen_results
        (run_date, screen_id, symbol, company_name, sector, market_cap_cat,
         price, change_1d_pct, change_1w_pct, change_1m_pct, screen_score,
         indicator_1_name, indicator_1_value, indicator_2_name, indicator_2_value,
         investment_score, technical_score, rsi, enhanced_fund_score,
         can_slim_score, minervini_score, stage, trading_signal, rank_in_screen)
    SELECT p_date, 'P02_PIOTROSKI_MOMENTUM',
        s.symbol, s.company_name, s.sector, s.market_cap_cat,
        COALESCE(s.live_price, s.price), s.change_1d_pct, s.change_1w_pct, s.change_1m_pct,
        s.investment_score, 'piotroski_score', f.piotroski_score,
        'investment_score', s.investment_score,
        s.investment_score, s.technical_score, s.rsi, s.enhanced_fund_score,
        s.can_slim_score, s.minervini_score, s.stage, s.trading_signal,
        RANK() OVER (ORDER BY s.investment_score DESC NULLS LAST)
    FROM scores.stage_snapshots s
    JOIN scores.fundamentals f ON f.symbol = s.symbol
    WHERE s.snapshot_date = v_snap_date
      AND f.piotroski_score >= 6
      AND s.investment_score >= 60
      AND s.trading_signal IN ('BUY','STRONG_BUY');
    GET DIAGNOSTICS v_count = ROW_COUNT;
    screen_id := 'P02_PIOTROSKI_MOMENTUM'; stocks_found := v_count; RETURN NEXT;

    INSERT INTO screener.screen_results
        (run_date, screen_id, symbol, company_name, sector, market_cap_cat,
         price, change_1d_pct, change_1w_pct, change_1m_pct, screen_score,
         indicator_1_name, indicator_1_value,
         investment_score, technical_score, rsi, enhanced_fund_score,
         can_slim_score, minervini_score, stage, trading_signal, rank_in_screen)
    SELECT p_date, 'P03_LOW_PIOTROSKI_AVOID',
        s.symbol, s.company_name, s.sector, s.market_cap_cat,
        COALESCE(s.live_price, s.price), s.change_1d_pct, s.change_1w_pct, s.change_1m_pct,
        10 - f.piotroski_score, 'piotroski_score', f.piotroski_score,
        s.investment_score, s.technical_score, s.rsi, s.enhanced_fund_score,
        s.can_slim_score, s.minervini_score, s.stage, s.trading_signal,
        RANK() OVER (ORDER BY f.piotroski_score ASC NULLS LAST)
    FROM scores.stage_snapshots s
    JOIN scores.fundamentals f ON f.symbol = s.symbol
    WHERE s.snapshot_date = v_snap_date
      AND f.piotroski_score <= 2;
    GET DIAGNOSTICS v_count = ROW_COUNT;
    screen_id := 'P03_LOW_PIOTROSKI_AVOID'; stocks_found := v_count; RETURN NEXT;

    -- ─────────────────────────────────────────────────────────────────────────
    -- M01-M04: Macro Screens
    -- ─────────────────────────────────────────────────────────────────────────

    -- M01: FII Buying + Stage 2 (join fii_dii_flows — positive 5d flow)
    INSERT INTO screener.screen_results
        (run_date, screen_id, symbol, company_name, sector, market_cap_cat,
         price, change_1d_pct, change_1w_pct, change_1m_pct, screen_score,
         indicator_1_name, indicator_1_value,
         investment_score, technical_score, rsi, enhanced_fund_score,
         can_slim_score, minervini_score, stage, trading_signal, rank_in_screen)
    SELECT p_date, 'M01_FII_BUYING_STAGE2',
        s.symbol, s.company_name, s.sector, s.market_cap_cat,
        COALESCE(s.live_price, s.price), s.change_1d_pct, s.change_1w_pct, s.change_1m_pct,
        s.investment_score, 'fii_net_5d', f.fii_net_5d,
        s.investment_score, s.technical_score, s.rsi, s.enhanced_fund_score,
        s.can_slim_score, s.minervini_score, s.stage, s.trading_signal,
        RANK() OVER (ORDER BY s.investment_score DESC NULLS LAST)
    FROM scores.stage_snapshots s
    CROSS JOIN (
        SELECT fii_net_5d FROM signals.fii_dii_flows
        ORDER BY trade_date DESC LIMIT 1
    ) f
    WHERE s.snapshot_date = v_snap_date
      AND s.stage = 'STAGE_2'
      AND f.fii_net_5d > 0
      AND s.trading_signal IN ('BUY','STRONG_BUY');
    GET DIAGNOSTICS v_count = ROW_COUNT;
    screen_id := 'M01_FII_BUYING_STAGE2'; stocks_found := v_count; RETURN NEXT;

    -- M02: Macro Tailwind Sectors
    INSERT INTO screener.screen_results
        (run_date, screen_id, symbol, company_name, sector, market_cap_cat,
         price, change_1d_pct, change_1w_pct, change_1m_pct, screen_score,
         indicator_1_name, indicator_1_value,
         investment_score, technical_score, rsi, enhanced_fund_score,
         can_slim_score, minervini_score, stage, trading_signal, rank_in_screen)
    SELECT p_date, 'M02_SECTOR_MACRO_TAILWIND',
        s.symbol, s.company_name, s.sector, s.market_cap_cat,
        COALESCE(s.live_price, s.price), s.change_1d_pct, s.change_1w_pct, s.change_1m_pct,
        s.investment_score, 'macro_tailwind', 1,
        s.investment_score, s.technical_score, s.rsi, s.enhanced_fund_score,
        s.can_slim_score, s.minervini_score, s.stage, s.trading_signal,
        RANK() OVER (ORDER BY s.investment_score DESC NULLS LAST)
    FROM scores.stage_snapshots s
    JOIN macro.sector_tailwinds mt ON mt.sector_name = s.sector
    WHERE s.snapshot_date = v_snap_date
      AND mt.snapshot_date = (SELECT MAX(snapshot_date) FROM macro.sector_tailwinds)
      AND mt.macro_tailwind IN ('POSITIVE','STRONG_POSITIVE')
      AND s.trading_signal IN ('BUY','STRONG_BUY');
    GET DIAGNOSTICS v_count = ROW_COUNT;
    screen_id := 'M02_SECTOR_MACRO_TAILWIND'; stocks_found := v_count; RETURN NEXT;

    -- M03: Global Outperformers (Stage 2, positive relative strength vs global)
    INSERT INTO screener.screen_results
        (run_date, screen_id, symbol, company_name, sector, market_cap_cat,
         price, change_1d_pct, change_1w_pct, change_1m_pct, screen_score,
         indicator_1_name, indicator_1_value,
         investment_score, technical_score, rsi, enhanced_fund_score,
         can_slim_score, minervini_score, stage, trading_signal, rank_in_screen)
    SELECT p_date, 'M03_GLOBAL_OUTPERFORMERS',
        symbol, company_name, sector, market_cap_cat,
        COALESCE(live_price, price), change_1d_pct, change_1w_pct, change_1m_pct,
        investment_score, 'relative_strength', relative_strength,
        investment_score, technical_score, rsi, enhanced_fund_score,
        can_slim_score, minervini_score, stage, trading_signal,
        RANK() OVER (ORDER BY relative_strength DESC NULLS LAST)
    FROM scores.stage_snapshots
    WHERE snapshot_date = v_snap_date
      AND relative_strength >= 0.15
      AND stage IN ('STAGE_2')
      AND trading_signal IN ('BUY','STRONG_BUY');
    GET DIAGNOSTICS v_count = ROW_COUNT;
    screen_id := 'M03_GLOBAL_OUTPERFORMERS'; stocks_found := v_count; RETURN NEXT;

    -- M04: Insider Accumulation
    INSERT INTO screener.screen_results
        (run_date, screen_id, symbol, company_name, sector, market_cap_cat,
         price, change_1d_pct, change_1w_pct, change_1m_pct, screen_score,
         indicator_1_name, indicator_1_value,
         investment_score, technical_score, rsi, enhanced_fund_score,
         can_slim_score, minervini_score, stage, trading_signal, rank_in_screen)
    SELECT p_date, 'M04_INSIDER_ACCUMULATION',
        s.symbol, s.company_name, s.sector, s.market_cap_cat,
        COALESCE(s.live_price, s.price), s.change_1d_pct, s.change_1w_pct, s.change_1m_pct,
        s.investment_score, 'deal_count', COUNT(bd.id)::numeric,
        s.investment_score, s.technical_score, s.rsi, s.enhanced_fund_score,
        s.can_slim_score, s.minervini_score, s.stage, s.trading_signal,
        RANK() OVER (ORDER BY COUNT(bd.id) DESC, s.investment_score DESC NULLS LAST)
    FROM scores.stage_snapshots s
    JOIN signals.bulk_block_deals bd
      ON bd.symbol = s.symbol
      AND bd.side = 'BUY'
      AND bd.deal_date >= CURRENT_DATE - INTERVAL '30 days'
    WHERE s.snapshot_date = v_snap_date
      AND s.trading_signal IN ('BUY','STRONG_BUY','HOLD')
    GROUP BY s.symbol, s.company_name, s.sector, s.market_cap_cat,
             s.live_price, s.price, s.change_1d_pct, s.change_1w_pct, s.change_1m_pct,
             s.investment_score, s.technical_score, s.rsi, s.enhanced_fund_score,
             s.can_slim_score, s.minervini_score, s.stage, s.trading_signal;
    GET DIAGNOSTICS v_count = ROW_COUNT;
    screen_id := 'M04_INSIDER_ACCUMULATION'; stocks_found := v_count; RETURN NEXT;

    -- ─────────────────────────────────────────────────────────────────────────
    -- X01: High Conviction — All Factors Aligned
    -- ─────────────────────────────────────────────────────────────────────────
    INSERT INTO screener.screen_results
        (run_date, screen_id, symbol, company_name, sector, market_cap_cat,
         price, change_1d_pct, change_1w_pct, change_1m_pct, screen_score,
         indicator_1_name, indicator_1_value, indicator_2_name, indicator_2_value,
         indicator_3_name, indicator_3_value,
         investment_score, technical_score, rsi, enhanced_fund_score,
         can_slim_score, minervini_score, stage, trading_signal, rank_in_screen)
    SELECT p_date, 'X01_HIGH_CONVICTION',
        symbol, company_name, sector, market_cap_cat,
        COALESCE(live_price, price), change_1d_pct, change_1w_pct, change_1m_pct,
        investment_score,
        'investment_score', investment_score,
        'can_slim_score', can_slim_score,
        'enhanced_fund_score', enhanced_fund_score,
        investment_score, technical_score, rsi, enhanced_fund_score,
        can_slim_score, minervini_score, stage, trading_signal,
        RANK() OVER (ORDER BY investment_score DESC NULLS LAST)
    FROM scores.stage_snapshots
    WHERE snapshot_date = v_snap_date
      AND investment_score >= 75
      AND stage = 'STAGE_2'
      AND trading_signal IN ('BUY','STRONG_BUY')
      AND can_slim_score >= 15
      AND enhanced_fund_score >= 60;
    GET DIAGNOSTICS v_count = ROW_COUNT;
    screen_id := 'X01_HIGH_CONVICTION'; stocks_found := v_count; RETURN NEXT;

    -- X02: Turnaround Candidates (Stage 1 with improving scores)
    INSERT INTO screener.screen_results
        (run_date, screen_id, symbol, company_name, sector, market_cap_cat,
         price, change_1d_pct, change_1w_pct, change_1m_pct, screen_score,
         indicator_1_name, indicator_1_value, indicator_2_name, indicator_2_value,
         investment_score, technical_score, rsi, enhanced_fund_score,
         can_slim_score, minervini_score, stage, trading_signal, rank_in_screen)
    WITH recent_change AS (
        SELECT DISTINCT ON (sc.symbol) sc.symbol, sc.change_type, sc.change_date
        FROM scores.stage_changes sc
        WHERE sc.change_date >= CURRENT_DATE - INTERVAL '14 days'
          AND sc.stage_now = 'STAGE_2'
          AND sc.stage_prev = 'STAGE_1'
        ORDER BY sc.symbol, sc.change_date DESC, sc.compare_date DESC
    )
    SELECT p_date, 'X02_TURNAROUND_CANDIDATES',
        s.symbol, s.company_name, s.sector, s.market_cap_cat,
        COALESCE(s.live_price, s.price), s.change_1d_pct, s.change_1w_pct, s.change_1m_pct,
        s.investment_score,
        'stage_change', 1, 'days_ago', (CURRENT_DATE - rc.change_date)::numeric,
        s.investment_score, s.technical_score, s.rsi, s.enhanced_fund_score,
        s.can_slim_score, s.minervini_score, s.stage, s.trading_signal,
        RANK() OVER (ORDER BY s.investment_score DESC NULLS LAST)
    FROM scores.stage_snapshots s
    JOIN recent_change rc ON rc.symbol = s.symbol
    WHERE s.snapshot_date = v_snap_date;
    GET DIAGNOSTICS v_count = ROW_COUNT;
    screen_id := 'X02_TURNAROUND_CANDIDATES'; stocks_found := v_count; RETURN NEXT;

    -- X03: Defensive Quality
    INSERT INTO screener.screen_results
        (run_date, screen_id, symbol, company_name, sector, market_cap_cat,
         price, change_1d_pct, change_1w_pct, change_1m_pct, screen_score,
         indicator_1_name, indicator_1_value, indicator_2_name, indicator_2_value,
         investment_score, technical_score, rsi, enhanced_fund_score,
         can_slim_score, minervini_score, stage, trading_signal, rank_in_screen)
    SELECT p_date, 'X03_DEFENSIVE_QUALITY',
        symbol, company_name, sector, market_cap_cat,
        COALESCE(live_price, price), change_1d_pct, change_1w_pct, change_1m_pct,
        financial_strength, 'financial_strength', financial_strength,
        'enhanced_fund_score', enhanced_fund_score,
        investment_score, technical_score, rsi, enhanced_fund_score,
        can_slim_score, minervini_score, stage, trading_signal,
        RANK() OVER (ORDER BY financial_strength DESC NULLS LAST, enhanced_fund_score DESC NULLS LAST)
    FROM scores.stage_snapshots
    WHERE snapshot_date = v_snap_date
      AND enhanced_fund_score >= 65
      AND financial_strength >= 65
      AND stage IN ('STAGE_1','STAGE_2')
      AND trading_signal NOT IN ('SELL','STRONG_SELL');
    GET DIAGNOSTICS v_count = ROW_COUNT;
    screen_id := 'X03_DEFENSIVE_QUALITY'; stocks_found := v_count; RETURN NEXT;

    -- X04: Momentum Beast
    INSERT INTO screener.screen_results
        (run_date, screen_id, symbol, company_name, sector, market_cap_cat,
         price, change_1d_pct, change_1w_pct, change_1m_pct, screen_score,
         indicator_1_name, indicator_1_value, indicator_2_name, indicator_2_value,
         indicator_3_name, indicator_3_value,
         investment_score, technical_score, rsi, enhanced_fund_score,
         can_slim_score, minervini_score, stage, trading_signal, rank_in_screen)
    SELECT p_date, 'X04_MOMENTUM_BEAST',
        symbol, company_name, sector, market_cap_cat,
        COALESCE(live_price, price), change_1d_pct, change_1w_pct, change_1m_pct,
        investment_score,
        'relative_strength', relative_strength,
        'can_slim_score', can_slim_score,
        'minervini_score', minervini_score,
        investment_score, technical_score, rsi, enhanced_fund_score,
        can_slim_score, minervini_score, stage, trading_signal,
        RANK() OVER (ORDER BY investment_score DESC NULLS LAST)
    FROM scores.stage_snapshots
    WHERE snapshot_date = v_snap_date
      AND relative_strength >= 0.15
      AND can_slim_score >= 14
      AND minervini_score >= 14
      AND stage = 'STAGE_2'
      AND rsi BETWEEN 55 AND 75
    ORDER BY investment_score DESC
    LIMIT 30;
    GET DIAGNOSTICS v_count = ROW_COUNT;
    screen_id := 'X04_MOMENTUM_BEAST'; stocks_found := v_count; RETURN NEXT;

    -- ─────────────────────────────────────────────────────────────────────────
    -- Build stock_screen_summary
    -- ─────────────────────────────────────────────────────────────────────────
    INSERT INTO screener.stock_screen_summary
        (run_date, symbol, company_name, sector, market_cap_cat, price, change_1d_pct,
         screens_passed_total, screens_technical, screens_canslim, screens_fundamental,
         screens_growth, screens_piotroski, screens_macro, screens_composite,
         investment_score, technical_score, enhanced_fund_score, can_slim_score,
         stage, trading_signal, passed_screens)
    SELECT
        p_date, r.symbol, r.company_name, r.sector, r.market_cap_cat,
        r.price, r.change_1d_pct,
        COUNT(*)                                                        AS screens_passed_total,
        COUNT(*) FILTER (WHERE d.category = 'TECHNICAL')               AS screens_technical,
        COUNT(*) FILTER (WHERE d.category = 'CANSLIM')                 AS screens_canslim,
        COUNT(*) FILTER (WHERE d.category = 'FUNDAMENTAL')             AS screens_fundamental,
        COUNT(*) FILTER (WHERE d.category = 'GROWTH')                  AS screens_growth,
        COUNT(*) FILTER (WHERE d.category = 'PIOTROSKI')               AS screens_piotroski,
        COUNT(*) FILTER (WHERE d.category = 'MACRO')                   AS screens_macro,
        COUNT(*) FILTER (WHERE d.category = 'COMPOSITE')               AS screens_composite,
        MAX(r.investment_score), MAX(r.technical_score),
        MAX(r.enhanced_fund_score), MAX(r.can_slim_score),
        MAX(r.stage), MAX(r.trading_signal),
        ARRAY_AGG(r.screen_id ORDER BY r.screen_id)
    FROM screener.screen_results r
    JOIN screener.screen_definitions d ON d.screen_id = r.screen_id
    WHERE r.run_date = p_date
      AND d.direction = 'BULLISH'   -- only count bullish passes
    GROUP BY r.symbol, r.company_name, r.sector, r.market_cap_cat, r.price, r.change_1d_pct;
    GET DIAGNOSTICS v_count = ROW_COUNT;
    screen_id := '__SUMMARY__'; stocks_found := v_count; RETURN NEXT;

    -- ─────────────────────────────────────────────────────────────────────────
    -- Detect ENTRY/EXIT alerts vs previous run
    -- ─────────────────────────────────────────────────────────────────────────
    -- Entries: in today but not in yesterday
    INSERT INTO screener.screen_alerts
        (alert_date, screen_id, symbol, company_name, event_type, screen_score, price)
    SELECT p_date, r.screen_id, r.symbol, r.company_name, 'ENTRY',
           r.screen_score, r.price
    FROM screener.screen_results r
    WHERE r.run_date = p_date
    AND NOT EXISTS (
        SELECT 1 FROM screener.screen_results prev
        WHERE prev.screen_id = r.screen_id
          AND prev.symbol    = r.symbol
          AND prev.run_date  = p_date - 1
    )
    ON CONFLICT DO NOTHING;

    RAISE NOTICE 'Screens complete for %', p_date;
END;
$$;

-- =============================================================================
-- REFRESH SCREENER VIEWS
-- =============================================================================
CREATE OR REPLACE FUNCTION screener.refresh_views()
RETURNS void LANGUAGE plpgsql AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY screener.mv_latest_results;
    REFRESH MATERIALIZED VIEW CONCURRENTLY screener.mv_latest_summary;
    RAISE NOTICE 'Screener views refreshed at %', now();
END;
$$;

-- =============================================================================
-- CONVENIENCE VIEWS
-- =============================================================================

-- Quick: which screens does a symbol currently pass?
CREATE OR REPLACE VIEW screener.v_symbol_screens AS
SELECT
    r.symbol, r.company_name, r.sector,
    r.price, r.change_1d_pct,
    r.investment_score, r.stage, r.trading_signal,
    d.screen_name, d.category, d.direction,
    r.screen_score, r.rank_in_screen,
    r.indicator_1_name, r.indicator_1_value,
    r.run_date
FROM screener.mv_latest_results r
JOIN screener.screen_definitions d ON d.screen_id = r.screen_id
ORDER BY r.symbol, d.category, r.screen_score DESC;

-- Quick: top conviction stocks right now
CREATE OR REPLACE VIEW screener.v_top_conviction AS
SELECT
    symbol, company_name, sector, market_cap_cat,
    price, change_1d_pct, investment_score,
    stage, trading_signal,
    screens_passed_total, conviction_tier,
    screens_technical, screens_canslim, screens_fundamental,
    screens_growth, screens_macro, screens_composite,
    passed_screens,
    run_date
FROM screener.mv_latest_summary
ORDER BY screens_passed_total DESC, investment_score DESC;
