CREATE SCHEMA IF NOT EXISTS recommendation_reports;

ALTER TABLE recommendation_reports.runs
    ADD COLUMN IF NOT EXISTS council_mode TEXT,
    ADD COLUMN IF NOT EXISTS horizon TEXT,
    ADD COLUMN IF NOT EXISTS risk_budget TEXT,
    ADD COLUMN IF NOT EXISTS universe_filter TEXT,
    ADD COLUMN IF NOT EXISTS evidence_pack_id TEXT,
    ADD COLUMN IF NOT EXISTS plan_iterations INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS revision_count INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS final_label TEXT,
    ADD COLUMN IF NOT EXISTS council_status TEXT,
    ADD COLUMN IF NOT EXISTS budgets_remaining JSONB,
    ADD COLUMN IF NOT EXISTS wall_clock_ms INTEGER;

ALTER TABLE recommendation_reports.recommendations
    ADD COLUMN IF NOT EXISTS disclaimer_version TEXT DEFAULT 'v1.0_research_only';

ALTER TABLE signals.signal_log
    ADD COLUMN IF NOT EXISTS council_run_id TEXT,
    ADD COLUMN IF NOT EXISTS disclaimer_version TEXT;

CREATE TABLE IF NOT EXISTS recommendation_reports.evidence_packs (
    pack_id TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    as_of DATE NOT NULL,
    mode TEXT NOT NULL,
    universe_filter TEXT,
    symbols TEXT[],
    pack_body JSONB NOT NULL,
    source_trail JSONB NOT NULL DEFAULT '[]'::jsonb,
    missing_evidence JSONB NOT NULL DEFAULT '[]'::jsonb
);

CREATE TABLE IF NOT EXISTS recommendation_reports.agent_findings (
    finding_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES recommendation_reports.runs(run_id) ON DELETE CASCADE,
    agent_name TEXT NOT NULL,
    iteration INTEGER NOT NULL DEFAULT 0,
    stance TEXT,
    confidence NUMERIC(4,3),
    thesis TEXT,
    body JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS recommendation_reports.branch_summaries (
    summary_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES recommendation_reports.runs(run_id) ON DELETE CASCADE,
    branch TEXT NOT NULL,
    stance TEXT,
    body JSONB NOT NULL,
    requires_quant BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS recommendation_reports.council_plans (
    plan_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES recommendation_reports.runs(run_id) ON DELETE CASCADE,
    iteration INTEGER NOT NULL,
    central_question TEXT,
    steps JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS recommendation_reports.execution_results (
    result_id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL REFERENCES recommendation_reports.council_plans(plan_id) ON DELETE CASCADE,
    step_id TEXT NOT NULL,
    status TEXT NOT NULL,
    outputs JSONB NOT NULL DEFAULT '[]'::jsonb,
    error TEXT,
    elapsed_ms INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS recommendation_reports.strategy_specs (
    spec_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES recommendation_reports.runs(run_id) ON DELETE CASCADE,
    strategy_family TEXT NOT NULL,
    hypothesis TEXT,
    body JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS recommendation_reports.backtest_results (
    result_id TEXT PRIMARY KEY,
    spec_id TEXT NOT NULL REFERENCES recommendation_reports.strategy_specs(spec_id) ON DELETE CASCADE,
    split TEXT NOT NULL,
    trade_count INTEGER,
    win_rate NUMERIC(5,4),
    return_pct NUMERIC(8,4),
    sharpe NUMERIC(6,3),
    max_drawdown_pct NUMERIC(6,3),
    profit_factor NUMERIC(6,3),
    body JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS recommendation_reports.critic_reviews (
    review_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES recommendation_reports.runs(run_id) ON DELETE CASCADE,
    iteration INTEGER NOT NULL,
    critic TEXT NOT NULL,
    severity_max TEXT NOT NULL,
    findings JSONB NOT NULL,
    summary TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS runs_council_mode_idx
    ON recommendation_reports.runs(council_mode, generated_at DESC);

CREATE INDEX IF NOT EXISTS runs_final_label_idx
    ON recommendation_reports.runs(final_label, generated_at DESC);

CREATE INDEX IF NOT EXISTS evidence_packs_as_of_idx
    ON recommendation_reports.evidence_packs(as_of DESC);

CREATE INDEX IF NOT EXISTS agent_findings_run_idx
    ON recommendation_reports.agent_findings(run_id, iteration);

CREATE INDEX IF NOT EXISTS branch_summaries_run_idx
    ON recommendation_reports.branch_summaries(run_id);

CREATE INDEX IF NOT EXISTS council_plans_run_idx
    ON recommendation_reports.council_plans(run_id, iteration);

CREATE INDEX IF NOT EXISTS execution_results_plan_idx
    ON recommendation_reports.execution_results(plan_id);

CREATE INDEX IF NOT EXISTS strategy_specs_run_idx
    ON recommendation_reports.strategy_specs(run_id);

CREATE INDEX IF NOT EXISTS backtest_results_spec_idx
    ON recommendation_reports.backtest_results(spec_id, split);

CREATE INDEX IF NOT EXISTS critic_reviews_run_idx
    ON recommendation_reports.critic_reviews(run_id, iteration);

CREATE INDEX IF NOT EXISTS signal_log_council_run_idx
    ON signals.signal_log(council_run_id);
