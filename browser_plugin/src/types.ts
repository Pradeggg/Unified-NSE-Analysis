// Shared TypeScript types for the Agent Adda browser plugin.
// These mirror the Pydantic schemas in agent_adda/web_api/schemas.py.

export type Exchange = "NSE" | "BSE";
export type Timeframe = "1m" | "3m" | "5m" | "15m" | "30m" | "1h" | "4h" | "1D" | "1W" | "1M";
export type PatternStatus = "confirmed" | "forming" | "none" | "engine_unavailable";
export type ConflictPolicy = "prefer_pg" | "show_mismatch";

// ── Capture payload sent to Agent Adda API ─────────────────────────────────

export interface ChartCapturePayload {
  /** Base64-encoded PNG screenshot (may be null for structured-evidence-only path). */
  image: string | null;
  source_url: string | null;
  page_title: string | null;
  user_symbol: string;
  exchange: Exchange;
  timeframe: Timeframe;
  /** Indicator names visible on the captured chart. */
  visible_indicators: string[];
  user_question: string;
  /** Structured evidence fetched from PG — injected by backend, not the plugin. */
  pg_evidence?: Record<string, unknown>;
  conflict_policy: ConflictPolicy;
}

// ── Active chart context (persisted in side panel state) ──────────────────

export interface KeyLevels {
  support: number | null;
  resistance: number | null;
  ema20: number | null;
  ema50: number | null;
  ema100: number | null;
  ema200: number | null;
  supertrend: number | null;
  supertrend_direction: "bullish" | "bearish" | null;
  vwap: number | null;
}

export interface PatternFinding {
  pattern_type: string;
  status: PatternStatus;
  neckline: number | null;
  breakout_level: number | null;
  target: number | null;
  stop: number | null;
  win_rate: number | null;
  avg_move_pct: number | null;
  sample_size: number | null;
  detected_at: string | null;
}

export interface ActiveChartContext {
  capture_id: string;
  symbol: string;
  exchange: Exchange;
  timeframe: Timeframe;
  captured_at: string;         // ISO timestamp
  screenshot_data_url: string | null;
  visible_indicators: string[];
  computed_levels: KeyLevels;
  user_drawings: unknown[];
  llm_conclusions: string[];
  pg_evidence_version: string | null;
  pattern_findings: PatternFinding[];
}

// ── Analysis result from Agent Adda API ──────────────────────────────────

export interface EvidenceTrail {
  source: string;
  as_of: string;
  pg_levels_used: boolean;
  screenshot_used: boolean;
  pattern_engine_used: boolean;
}

export interface AnalysisResult {
  capture_id: string;
  symbol: string;
  exchange: Exchange;
  timeframe: Timeframe;
  answer: string;             // Formatted markdown/terminal text response
  key_levels: KeyLevels;
  pattern_findings: PatternFinding[];
  evidence_trail: EvidenceTrail;
  model: string;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  error: string | null;
}

// ── Content script → side panel message ──────────────────────────────────

export interface PageMetadata {
  symbol: string | null;
  exchange: Exchange | null;
  timeframe: Timeframe | null;
  page_title: string;
  source_url: string;
  detected_from: "url" | "dom" | "title" | "none";
}

// ── Chat turn ────────────────────────────────────────────────────────────

export type ChatRole = "user" | "assistant" | "system";

export interface ChatTurn {
  id: string;
  role: ChatRole;
  content: string;
  timestamp: string;
  evidence_trail?: EvidenceTrail;
  cost_usd?: number;
}

// ── API response envelope ─────────────────────────────────────────────────

export interface ApiResponse<T> {
  ok: boolean;
  data: T | null;
  error: string | null;
  status_code: number;
}
