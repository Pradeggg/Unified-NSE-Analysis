-- AA-UR-2 Agent Context: structured per-session context (workflows, reports,
-- pending NEXT options, source trails) that augments agent_memory.* with
-- lossless rows the unified router can query directly.
--
-- All tables are additive and use IF NOT EXISTS so this migration is
-- idempotent and safe to re-run.

CREATE SCHEMA IF NOT EXISTS agent_context;

-- A multi-step (Sherlock-style) workflow currently in flight for a
-- session. ``steps`` is an ordered JSONB array; each entry follows the
-- terminal.router.context.WorkflowStep schema and stores its own
-- structured ``evidence`` list. We never persist evidence in prose only.
CREATE TABLE IF NOT EXISTS agent_context.active_workflows (
    workflow_id  TEXT PRIMARY KEY,
    session_id   TEXT NOT NULL,
    kind         TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'open',
    steps        JSONB NOT NULL DEFAULT '[]'::jsonb,
    started_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_agent_context_active_workflows_session
    ON agent_context.active_workflows (session_id, updated_at DESC);

-- Generated reports addressable by (path, type, symbol). The same
-- report path is unique per session so we can upsert on regeneration.
CREATE TABLE IF NOT EXISTS agent_context.active_reports (
    session_id   TEXT NOT NULL,
    path         TEXT NOT NULL,
    report_type  TEXT NOT NULL DEFAULT '',
    symbol       TEXT NOT NULL DEFAULT '',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (session_id, path)
);

CREATE INDEX IF NOT EXISTS idx_agent_context_active_reports_symbol
    ON agent_context.active_reports (session_id, symbol);
CREATE INDEX IF NOT EXISTS idx_agent_context_active_reports_type
    ON agent_context.active_reports (session_id, report_type);

-- NEXT OPTIONS rendered to the user that are still selectable by label.
CREATE TABLE IF NOT EXISTS agent_context.pending_options (
    session_id    TEXT NOT NULL,
    label         TEXT NOT NULL,
    text          TEXT NOT NULL,
    bound_action  JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at    TIMESTAMPTZ NULL,
    PRIMARY KEY (session_id, label)
);

CREATE INDEX IF NOT EXISTS idx_agent_context_pending_options_session
    ON agent_context.pending_options (session_id, created_at DESC);

-- Append-only trail of (source_label, freshness) observations so the
-- router can audit where each piece of evidence came from.
CREATE TABLE IF NOT EXISTS agent_context.source_trails (
    id            BIGSERIAL PRIMARY KEY,
    session_id    TEXT NOT NULL,
    source_label  TEXT NOT NULL,
    freshness     TEXT NOT NULL DEFAULT '',
    observed_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    meta          JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_agent_context_source_trails_session
    ON agent_context.source_trails (session_id, observed_at DESC);
