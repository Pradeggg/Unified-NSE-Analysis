-- Partition derivatives.fno_eod by trade_date and add retention helpers.
-- Safe to rerun after the first conversion.

CREATE SCHEMA IF NOT EXISTS derivatives;

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

CREATE OR REPLACE FUNCTION derivatives.ensure_fno_partitions(p_start DATE, p_end DATE)
RETURNS INTEGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_month DATE;
    v_count INTEGER := 0;
BEGIN
    IF p_start IS NULL OR p_end IS NULL THEN
        RETURN 0;
    END IF;

    v_month := date_trunc('month', p_start)::date;
    WHILE v_month <= date_trunc('month', p_end)::date LOOP
        PERFORM derivatives.ensure_fno_monthly_partition(v_month);
        v_count := v_count + 1;
        v_month := (v_month + INTERVAL '1 month')::date;
    END LOOP;

    RETURN v_count;
END;
$$;

DO $$
DECLARE
    v_is_partitioned BOOLEAN;
    v_min_date DATE;
    v_max_date DATE;
    v_old_count BIGINT;
    v_new_count BIGINT;
BEGIN
    SELECT c.relkind = 'p'
    INTO v_is_partitioned
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'derivatives'
      AND c.relname = 'fno_eod';

    IF COALESCE(v_is_partitioned, FALSE) THEN
        RAISE NOTICE 'derivatives.fno_eod is already partitioned';
        RETURN;
    END IF;

    DROP MATERIALIZED VIEW IF EXISTS derivatives.mv_fno_symbol_analytics;
    DROP MATERIALIZED VIEW IF EXISTS derivatives.mv_fno_max_pain;
    DROP MATERIALIZED VIEW IF EXISTS derivatives.mv_fno_option_chain;
    DROP MATERIALIZED VIEW IF EXISTS derivatives.mv_fno_nearest_options;

    SELECT min(trade_date), max(trade_date), count(*)
    INTO v_min_date, v_max_date, v_old_count
    FROM derivatives.fno_eod;

    ALTER TABLE derivatives.fno_eod RENAME TO fno_eod_unpartitioned_backup;

    CREATE TABLE derivatives.fno_eod (
        trade_date       DATE          NOT NULL,
        symbol           TEXT          NOT NULL,
        expiry_date      DATE          NOT NULL,
        instrument       TEXT          NOT NULL,
        option_type      TEXT          NOT NULL,
        strike           NUMERIC(12,2) NOT NULL DEFAULT 0,
        open             NUMERIC(12,2),
        high             NUMERIC(12,2),
        low              NUMERIC(12,2),
        close            NUMERIC(12,2),
        last_price       NUMERIC(12,2),
        prev_close       NUMERIC(12,2),
        underlying_price NUMERIC(12,2),
        settle_price     NUMERIC(12,2),
        open_interest    BIGINT,
        oi_change        BIGINT,
        volume           BIGINT,
        turnover_cr      NUMERIC(16,4),
        total_trades     INTEGER,
        lot_size         INTEGER,
        strike_key       NUMERIC(12,2) GENERATED ALWAYS AS (COALESCE(strike, 0)) STORED,
        PRIMARY KEY (trade_date, symbol, expiry_date, instrument, option_type, strike_key)
    ) PARTITION BY RANGE (trade_date);

    CREATE TABLE derivatives.fno_eod_default PARTITION OF derivatives.fno_eod DEFAULT;

    PERFORM derivatives.ensure_fno_partitions(v_min_date, v_max_date);

    INSERT INTO derivatives.fno_eod (
        trade_date, symbol, expiry_date, instrument, option_type, strike,
        open, high, low, close, last_price, prev_close, underlying_price, settle_price,
        open_interest, oi_change, volume, turnover_cr, total_trades, lot_size
    )
    SELECT
        trade_date,
        symbol,
        expiry_date,
        instrument,
        CASE
            WHEN option_type IS NULL OR lower(option_type) IN ('', 'nan', 'none', 'na', 'null') THEN 'FUT'
            ELSE option_type
        END AS option_type,
        COALESCE(strike, 0) AS strike,
        open,
        high,
        low,
        close,
        last_price,
        prev_close,
        underlying_price,
        settle_price,
        open_interest,
        oi_change,
        volume,
        turnover_cr,
        total_trades,
        lot_size
    FROM derivatives.fno_eod_unpartitioned_backup;

    SELECT count(*) INTO v_new_count FROM derivatives.fno_eod;
    IF v_new_count <> v_old_count THEN
        RAISE EXCEPTION 'F&O partition migration row count mismatch: old %, new %', v_old_count, v_new_count;
    END IF;

    DROP TABLE derivatives.fno_eod_unpartitioned_backup;

    IF EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'derivatives.fno_eod'::regclass
          AND conname = 'fno_eod_pkey1'
    ) THEN
        ALTER TABLE derivatives.fno_eod RENAME CONSTRAINT fno_eod_pkey1 TO fno_eod_pkey;
    END IF;

    CREATE INDEX idx_fno_symbol_date ON derivatives.fno_eod (symbol, trade_date DESC);
    CREATE INDEX idx_fno_expiry ON derivatives.fno_eod (expiry_date, symbol);
    CREATE INDEX idx_fno_date_instr ON derivatives.fno_eod (trade_date, instrument);
    RAISE NOTICE 'derivatives.fno_eod partitioned successfully with % rows', v_new_count;
END;
$$;
