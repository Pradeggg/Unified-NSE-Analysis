CREATE SCHEMA IF NOT EXISTS agent_memory;

CREATE TABLE IF NOT EXISTS agent_memory.turn_events (
    id             BIGSERIAL PRIMARY KEY,
    session_id     TEXT NOT NULL,
    turn_index     INTEGER NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    user_input     TEXT NOT NULL,
    answer         TEXT NOT NULL,
    intent         TEXT,
    mode           TEXT,
    source_label   TEXT,
    freshness      TEXT,
    result_type    TEXT,
    result_summary TEXT,
    symbols        TEXT[] NOT NULL DEFAULT '{}',
    result_items   TEXT[] NOT NULL DEFAULT '{}',
    tool_names     TEXT[] NOT NULL DEFAULT '{}',
    tool_results   JSONB NOT NULL DEFAULT '[]'::jsonb,
    turn_context   JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (session_id, turn_index)
);

CREATE TABLE IF NOT EXISTS agent_memory.session_snapshots (
    session_id  TEXT PRIMARY KEY,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    turn_count  INTEGER NOT NULL DEFAULT 0,
    memory_json JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_agent_memory_turn_events_session_turn
    ON agent_memory.turn_events (session_id, turn_index DESC);
CREATE INDEX IF NOT EXISTS idx_agent_memory_turn_events_symbols
    ON agent_memory.turn_events USING GIN (symbols);
