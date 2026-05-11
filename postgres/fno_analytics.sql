-- F&O analytics and what-if scenarios
-- Run after postgres/schema.sql and after derivatives.fno_eod is loaded.

CREATE SCHEMA IF NOT EXISTS derivatives;

CREATE TABLE IF NOT EXISTS derivatives.fno_scenario_runs (
    scenario_id         BIGSERIAL PRIMARY KEY,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    trade_date          DATE,
    symbol              TEXT NOT NULL,
    expiry_date         DATE,
    option_type         TEXT,
    strike              NUMERIC(12,2),
    entry_premium       NUMERIC(12,2),
    lots                INTEGER NOT NULL DEFAULT 1,
    lot_size            INTEGER,
    underlying_base     NUMERIC(12,2),
    move_pct            NUMERIC(8,4),
    scenario_underlying NUMERIC(12,2),
    intrinsic_value     NUMERIC(12,2),
    pnl                 NUMERIC(16,2),
    breakeven           NUMERIC(12,2),
    notes               TEXT
);

DROP MATERIALIZED VIEW IF EXISTS derivatives.mv_fno_symbol_analytics;
DROP MATERIALIZED VIEW IF EXISTS derivatives.mv_fno_max_pain;
DROP MATERIALIZED VIEW IF EXISTS derivatives.mv_fno_option_chain;
DROP MATERIALIZED VIEW IF EXISTS derivatives.mv_fno_nearest_options;

CREATE MATERIALIZED VIEW derivatives.mv_fno_nearest_options AS
WITH latest_date AS (
    SELECT max(trade_date) AS trade_date FROM derivatives.fno_eod
),
nearest_expiry AS (
    SELECT e.symbol, min(e.expiry_date) AS expiry_date
    FROM derivatives.fno_eod e
    JOIN latest_date d ON d.trade_date = e.trade_date
    WHERE e.option_type IN ('CE', 'PE')
      AND e.expiry_date >= e.trade_date
    GROUP BY e.symbol
)
SELECT e.*
FROM derivatives.fno_eod e
JOIN latest_date d ON d.trade_date = e.trade_date
JOIN nearest_expiry n
  ON n.symbol = e.symbol
 AND n.expiry_date = e.expiry_date
WHERE e.option_type IN ('CE', 'PE');

CREATE UNIQUE INDEX idx_mv_fno_nearest_options
    ON derivatives.mv_fno_nearest_options (trade_date, symbol, expiry_date, option_type, strike_key);

CREATE MATERIALIZED VIEW derivatives.mv_fno_option_chain AS
WITH ce AS (
    SELECT trade_date, symbol, expiry_date, strike,
           max(underlying_price) AS underlying_price,
           sum(open_interest) AS ce_oi,
           sum(oi_change) AS ce_oi_change,
           sum(volume) AS ce_volume,
           max(last_price) AS ce_ltp,
           max(close) AS ce_close
    FROM derivatives.mv_fno_nearest_options
    WHERE option_type = 'CE'
    GROUP BY trade_date, symbol, expiry_date, strike
),
pe AS (
    SELECT trade_date, symbol, expiry_date, strike,
           max(underlying_price) AS underlying_price,
           sum(open_interest) AS pe_oi,
           sum(oi_change) AS pe_oi_change,
           sum(volume) AS pe_volume,
           max(last_price) AS pe_ltp,
           max(close) AS pe_close
    FROM derivatives.mv_fno_nearest_options
    WHERE option_type = 'PE'
    GROUP BY trade_date, symbol, expiry_date, strike
)
SELECT
    COALESCE(ce.trade_date, pe.trade_date) AS trade_date,
    COALESCE(ce.symbol, pe.symbol) AS symbol,
    COALESCE(ce.expiry_date, pe.expiry_date) AS expiry_date,
    COALESCE(ce.strike, pe.strike) AS strike,
    COALESCE(ce.underlying_price, pe.underlying_price) AS underlying_price,
    COALESCE(ce.ce_oi, 0) AS ce_oi,
    COALESCE(pe.pe_oi, 0) AS pe_oi,
    COALESCE(ce.ce_oi_change, 0) AS ce_oi_change,
    COALESCE(pe.pe_oi_change, 0) AS pe_oi_change,
    COALESCE(ce.ce_volume, 0) AS ce_volume,
    COALESCE(pe.pe_volume, 0) AS pe_volume,
    ce.ce_ltp,
    pe.pe_ltp,
    ce.ce_close,
    pe.pe_close
FROM ce
FULL OUTER JOIN pe
  ON ce.trade_date = pe.trade_date
 AND ce.symbol = pe.symbol
 AND ce.expiry_date = pe.expiry_date
 AND ce.strike = pe.strike;

CREATE UNIQUE INDEX idx_mv_fno_option_chain
    ON derivatives.mv_fno_option_chain (trade_date, symbol, expiry_date, strike);

CREATE MATERIALIZED VIEW derivatives.mv_fno_max_pain AS
WITH pain AS (
    SELECT
        c.trade_date,
        c.symbol,
        c.expiry_date,
        candidate.strike AS max_pain,
        sum(GREATEST(candidate.strike - c.strike, 0) * c.ce_oi)
          + sum(GREATEST(c.strike - candidate.strike, 0) * c.pe_oi) AS total_pain
    FROM derivatives.mv_fno_option_chain c
    JOIN derivatives.mv_fno_option_chain candidate
      ON candidate.trade_date = c.trade_date
     AND candidate.symbol = c.symbol
     AND candidate.expiry_date = c.expiry_date
    GROUP BY c.trade_date, c.symbol, c.expiry_date, candidate.strike
),
ranked AS (
    SELECT *,
           row_number() OVER (
               PARTITION BY trade_date, symbol, expiry_date
               ORDER BY total_pain ASC, max_pain ASC
           ) AS rn
    FROM pain
)
SELECT trade_date, symbol, expiry_date, max_pain, total_pain
FROM ranked
WHERE rn = 1;

CREATE UNIQUE INDEX idx_mv_fno_max_pain
    ON derivatives.mv_fno_max_pain (trade_date, symbol, expiry_date);

CREATE MATERIALIZED VIEW derivatives.mv_fno_symbol_analytics AS
WITH latest_date AS (
    SELECT max(trade_date) AS trade_date FROM derivatives.fno_eod
),
chain_agg AS (
    SELECT
        trade_date,
        symbol,
        expiry_date,
        max(underlying_price) AS underlying_price,
        sum(ce_oi) AS call_oi,
        sum(pe_oi) AS put_oi,
        sum(ce_volume) AS call_volume,
        sum(pe_volume) AS put_volume,
        sum(ce_oi_change) AS call_oi_change,
        sum(pe_oi_change) AS put_oi_change,
        round((sum(pe_oi)::numeric / NULLIF(sum(ce_oi), 0)), 4) AS pcr_oi,
        round((sum(pe_volume)::numeric / NULLIF(sum(ce_volume), 0)), 4) AS pcr_volume
    FROM derivatives.mv_fno_option_chain
    GROUP BY trade_date, symbol, expiry_date
),
max_call AS (
    SELECT DISTINCT ON (trade_date, symbol, expiry_date)
        trade_date, symbol, expiry_date, strike AS max_call_oi_strike, ce_oi AS max_call_oi
    FROM derivatives.mv_fno_option_chain
    ORDER BY trade_date, symbol, expiry_date, ce_oi DESC, strike ASC
),
max_put AS (
    SELECT DISTINCT ON (trade_date, symbol, expiry_date)
        trade_date, symbol, expiry_date, strike AS max_put_oi_strike, pe_oi AS max_put_oi
    FROM derivatives.mv_fno_option_chain
    ORDER BY trade_date, symbol, expiry_date, pe_oi DESC, strike DESC
),
futures AS (
    SELECT DISTINCT ON (e.symbol)
        e.trade_date,
        e.symbol,
        e.expiry_date AS futures_expiry,
        e.close AS futures_close,
        e.prev_close AS futures_prev_close,
        e.underlying_price,
        e.open_interest AS futures_oi,
        e.oi_change AS futures_oi_change,
        e.volume AS futures_volume,
        round(((e.close - NULLIF(e.prev_close, 0)) / NULLIF(e.prev_close, 0) * 100), 4) AS futures_price_change_pct,
        round((e.oi_change::numeric / NULLIF(e.open_interest - e.oi_change, 0) * 100), 4) AS futures_oi_change_pct
    FROM derivatives.fno_eod e
    JOIN latest_date d ON d.trade_date = e.trade_date
    WHERE e.instrument IN ('STF', 'IDF', 'FUTSTK', 'FUTIDX')
    ORDER BY e.symbol, e.expiry_date ASC
)
SELECT
    c.trade_date,
    c.symbol,
    c.expiry_date AS options_expiry,
    f.futures_expiry,
    COALESCE(c.underlying_price, f.underlying_price) AS underlying_price,
    f.futures_close,
    f.futures_price_change_pct,
    f.futures_oi,
    f.futures_oi_change,
    f.futures_oi_change_pct,
    f.futures_volume,
    c.call_oi,
    c.put_oi,
    c.call_volume,
    c.put_volume,
    c.call_oi_change,
    c.put_oi_change,
    c.pcr_oi,
    c.pcr_volume,
    mc.max_call_oi_strike,
    mc.max_call_oi,
    mp.max_put_oi_strike,
    mp.max_put_oi,
    pain.max_pain,
    round(((COALESCE(c.underlying_price, f.underlying_price) - pain.max_pain)
        / NULLIF(COALESCE(c.underlying_price, f.underlying_price), 0) * 100), 4) AS distance_from_max_pain_pct,
    CASE
        WHEN f.futures_oi_change_pct > 5 AND f.futures_price_change_pct > 0 THEN 'LONG_BUILDUP'
        WHEN f.futures_oi_change_pct > 5 AND f.futures_price_change_pct <= 0 THEN 'SHORT_BUILDUP'
        WHEN f.futures_oi_change_pct <= -5 AND f.futures_price_change_pct > 0 THEN 'SHORT_COVERING'
        WHEN f.futures_oi_change_pct <= -5 AND f.futures_price_change_pct <= 0 THEN 'LONG_UNWINDING'
        ELSE 'NEUTRAL'
    END AS buildup,
    CASE
        WHEN c.pcr_oi > 1.0 AND f.futures_oi_change_pct > 5 AND f.futures_price_change_pct > 0 THEN 'BULL'
        WHEN c.pcr_oi < 0.7 AND f.futures_oi_change_pct > 5 AND f.futures_price_change_pct <= 0 THEN 'BEAR'
        WHEN f.futures_oi_change_pct > 5 AND f.futures_price_change_pct > 0 THEN 'MILD_BULL'
        WHEN f.futures_oi_change_pct > 5 AND f.futures_price_change_pct <= 0 THEN 'MILD_BEAR'
        ELSE 'NEUTRAL'
    END AS fno_signal
FROM chain_agg c
LEFT JOIN futures f ON f.symbol = c.symbol AND f.trade_date = c.trade_date
LEFT JOIN max_call mc ON mc.trade_date = c.trade_date AND mc.symbol = c.symbol AND mc.expiry_date = c.expiry_date
LEFT JOIN max_put mp ON mp.trade_date = c.trade_date AND mp.symbol = c.symbol AND mp.expiry_date = c.expiry_date
LEFT JOIN derivatives.mv_fno_max_pain pain
  ON pain.trade_date = c.trade_date
 AND pain.symbol = c.symbol
 AND pain.expiry_date = c.expiry_date;

CREATE UNIQUE INDEX idx_mv_fno_symbol_analytics
    ON derivatives.mv_fno_symbol_analytics (trade_date, symbol);

CREATE OR REPLACE FUNCTION derivatives.refresh_fno_analytics()
RETURNS INTEGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_date DATE;
    v_count INTEGER;
BEGIN
    REFRESH MATERIALIZED VIEW derivatives.mv_fno_nearest_options;
    REFRESH MATERIALIZED VIEW derivatives.mv_fno_option_chain;
    REFRESH MATERIALIZED VIEW derivatives.mv_fno_max_pain;
    REFRESH MATERIALIZED VIEW derivatives.mv_fno_symbol_analytics;

    SELECT max(trade_date) INTO v_date FROM derivatives.mv_fno_symbol_analytics;
    IF v_date IS NULL THEN
        RETURN 0;
    END IF;

    DELETE FROM derivatives.fno_signals WHERE snapshot_date = v_date;

    INSERT INTO derivatives.fno_signals (
        snapshot_date, symbol, pcr, oi_change_5d, price_change, buildup, max_pain, fno_signal
    )
    SELECT
        trade_date,
        symbol,
        pcr_oi,
        futures_oi_change_pct,
        futures_price_change_pct,
        buildup,
        max_pain,
        fno_signal
    FROM derivatives.mv_fno_symbol_analytics;

    GET DIAGNOSTICS v_count = ROW_COUNT;
    RETURN v_count;
END;
$$;

CREATE OR REPLACE FUNCTION derivatives.option_payoff(
    p_symbol TEXT,
    p_option_type TEXT DEFAULT 'CE',
    p_strike NUMERIC DEFAULT NULL,
    p_expiry_date DATE DEFAULT NULL,
    p_entry_premium NUMERIC DEFAULT NULL,
    p_lots INTEGER DEFAULT 1,
    p_move_start NUMERIC DEFAULT -10,
    p_move_end NUMERIC DEFAULT 10,
    p_move_step NUMERIC DEFAULT 2.5,
    p_store BOOLEAN DEFAULT FALSE,
    p_notes TEXT DEFAULT NULL
)
RETURNS TABLE (
    trade_date DATE,
    symbol TEXT,
    expiry_date DATE,
    option_type TEXT,
    strike NUMERIC,
    entry_premium NUMERIC,
    lots INTEGER,
    lot_size INTEGER,
    underlying_base NUMERIC,
    move_pct NUMERIC,
    scenario_underlying NUMERIC,
    intrinsic_value NUMERIC,
    pnl NUMERIC,
    breakeven NUMERIC
)
LANGUAGE plpgsql
AS $$
DECLARE
    rec RECORD;
BEGIN
    SELECT e.trade_date, e.symbol, e.expiry_date, e.option_type, e.strike,
           COALESCE(p_entry_premium, NULLIF(e.last_price, 0), NULLIF(e.close, 0), e.settle_price) AS premium,
           COALESCE(e.lot_size, 1) AS lot_size,
           e.underlying_price
    INTO rec
    FROM derivatives.fno_eod e
    WHERE e.trade_date = (SELECT max(e2.trade_date) FROM derivatives.fno_eod e2)
      AND e.symbol = upper(p_symbol)
      AND e.option_type = upper(p_option_type)
      AND (p_expiry_date IS NULL OR e.expiry_date = p_expiry_date)
      AND (p_strike IS NULL OR e.strike = p_strike)
    ORDER BY e.expiry_date ASC, abs(e.strike - COALESCE(e.underlying_price, e.strike)) ASC
    LIMIT 1;

    IF rec IS NULL THEN
        RAISE EXCEPTION 'No option row found for %.%, strike %, expiry %',
            upper(p_symbol), upper(p_option_type), p_strike, p_expiry_date;
    END IF;

    RETURN QUERY
    WITH scenarios AS (
        SELECT generate_series(p_move_start, p_move_end, p_move_step)::numeric AS move_pct
    ),
    calc AS (
        SELECT
            rec.trade_date AS trade_date,
            rec.symbol AS symbol,
            rec.expiry_date AS expiry_date,
            rec.option_type AS option_type,
            rec.strike AS strike,
            rec.premium AS entry_premium,
            GREATEST(p_lots, 1) AS lots,
            rec.lot_size AS lot_size,
            rec.underlying_price AS underlying_base,
            s.move_pct AS move_pct,
            round((rec.underlying_price * (1 + s.move_pct / 100.0)), 2) AS scenario_underlying,
            CASE
                WHEN rec.option_type = 'CE' THEN GREATEST(round((rec.underlying_price * (1 + s.move_pct / 100.0)), 2) - rec.strike, 0)
                ELSE GREATEST(rec.strike - round((rec.underlying_price * (1 + s.move_pct / 100.0)), 2), 0)
            END AS intrinsic_value,
            CASE
                WHEN rec.option_type = 'CE' THEN rec.strike + rec.premium
                ELSE rec.strike - rec.premium
            END AS breakeven
        FROM scenarios s
    )
    SELECT
        c.trade_date,
        c.symbol,
        c.expiry_date,
        c.option_type,
        c.strike,
        c.entry_premium,
        c.lots,
        c.lot_size,
        c.underlying_base,
        c.move_pct,
        c.scenario_underlying,
        c.intrinsic_value,
        round((c.intrinsic_value - c.entry_premium) * c.lot_size * c.lots, 2) AS pnl,
        c.breakeven
    FROM calc c
    ORDER BY c.move_pct;

    IF p_store THEN
        INSERT INTO derivatives.fno_scenario_runs (
            trade_date, symbol, expiry_date, option_type, strike, entry_premium, lots, lot_size,
            underlying_base, move_pct, scenario_underlying, intrinsic_value, pnl, breakeven, notes
        )
        SELECT q.trade_date, q.symbol, q.expiry_date, q.option_type, q.strike, q.entry_premium,
               q.lots, q.lot_size, q.underlying_base, q.move_pct, q.scenario_underlying,
               q.intrinsic_value, q.pnl, q.breakeven, p_notes
        FROM derivatives.option_payoff(
            p_symbol, p_option_type, p_strike, p_expiry_date, p_entry_premium, p_lots,
            p_move_start, p_move_end, p_move_step, FALSE, NULL
        ) q;
    END IF;
END;
$$;

SELECT derivatives.refresh_fno_analytics();
