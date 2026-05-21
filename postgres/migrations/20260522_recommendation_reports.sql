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
