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

export interface SymbolSearchResult {
  symbol: string;
  name: string;
  score: number;
}

// ── Backtest types ────────────────────────────────────────────────────────

export interface BtMetrics {
  total_trades: number;
  wins: number;
  losses: number;
  win_rate: number;
  total_pnl: number;
  return_pct: number;
  avg_win: number;
  avg_loss: number;
  max_drawdown_pct: number;
  sharpe: number;
}

export interface BtTrade {
  entry_time: number | null;
  exit_time: number | null;
  direction: "BUY" | "SELL";
  entry_price: number;
  exit_price: number;
  qty: number;
  pnl: number;
  exit_reason: string;
  note: string;
  rr: number;
}

export interface BacktestResult {
  symbol: string;
  timeframe: string;
  strategy: string;
  bars_used: number;
  metrics: BtMetrics;
  trades: BtTrade[];
  run_id: number | null;
}

export interface LeaderRow {
  rank: number;
  symbol: string;
  timeframe: string;
  strategy_id: string;
  strategy_name: string;
  total_trades: number;
  win_rate: number;
  return_pct: number;
  sharpe: number;
  options_score: number;
}

// ── RIC (Recursive Insights Composite) types ─────────────────────────────

export interface DrawSignal {
  type:  string;
  price: number;
  label: string;
  color: string;
  width: number;
  dash:  boolean;
}

export interface RicSetup {
  bias:          "BULLISH" | "BEARISH" | "NEUTRAL";
  trigger:       number;
  stop:          number;
  targets:       number[];
  rr:            number;
  strategy:      string;
  potential_pct: number;
  holding:       string;
  actionable?:   boolean;
  quality_label?: "TRADEABLE" | "WATCH_ONLY";
  quality_reasons?: string[];
}

export interface RicSafety {
  score:   number;
  rating:  "SAFE" | "MODERATE" | "CAUTION" | "RISKY";
  color:   string;
  reasons: string[];
}

export interface RicFno {
  pcr:           number;
  atm:           number;
  max_pain:      number;
  ce_resistance: number[];
  pe_support:    number[];
  basis_pct:     number | null;
  fno_signal:    string;
  expiry:        string;
}

export interface RicMarket {
  nifty_close:    number;
  nifty_chg_pct:  number;
  nifty_up_days:  number;
  nifty_trend:    string;
  nifty_52w_high: number;
  nifty_52w_low:  number;
  // Symbol's own index data (populated when symbol is a known index)
  symbol_close:    number;
  symbol_chg_pct:  number;
  symbol_52w_high: number;
  symbol_52w_low:  number;
  symbol_trend:    string;
  symbol_up_days:  number;
  is_index:        boolean;
}

export interface RicOptionsPlay {
  strategy:    string;
  description: string;
  expiry:      string;
  risk_note:   string;
}

export interface RicKeyLevels {
  price:        number;
  pivot:        number;
  supports:     number[];
  resistances:  number[];
  ema9:         number;
  ema21:        number;
  ema50:        number;
  ema200:       number;
  pivot_levels: Record<string, number>;
}

export interface RicResult {
  symbol:          string;
  timeframe:       string;
  as_of:           string;
  safety:          RicSafety;
  market:          RicMarket;
  fno:             RicFno;
  intraday:        RicSetup;
  swing:           RicSetup;
  options_play:    RicOptionsPlay;
  key_levels:      RicKeyLevels;
  draw_signals:    DrawSignal[];
  recommendation:  string;
  model:           string;
  input_tokens:    number;
  output_tokens:   number;
}

export interface CaptureVisibleTabRequest {
  type: "CAPTURE_VISIBLE_TAB";
}

export interface CapturedTabInfo {
  id: number | null;
  windowId: number | null;
  url: string | null;
  title: string | null;
}

export interface CaptureVisibleTabResponse {
  ok: boolean;
  dataUrl: string | null;
  tab: CapturedTabInfo | null;
  error: string | null;
}

export interface CaptureSelectionRect {
  x: number;
  y: number;
  width: number;
  height: number;
  viewportWidth: number;
  viewportHeight: number;
}

export interface SelectCaptureAreaRequest {
  type: "SELECT_CAPTURE_AREA";
}

export interface SelectCaptureAreaResponse {
  ok: boolean;
  rect: CaptureSelectionRect | null;
  error: string | null;
}

export interface DrawRicLevelsRequest {
  type: "DRAW_RIC_LEVELS";
  signals: DrawSignal[];
}

export interface ClearRicOverlayRequest {
  type: "CLEAR_RIC_OVERLAY";
}

export interface DrawOverlayResponse {
  ok: boolean;
  error: string | null;
}

// ── Multi-chart pane detection ────────────────────────────────────────────

export interface ChartPane {
  index: number;
  symbol: string | null;
  exchange: Exchange | null;
  timeframe: Timeframe | null;
  is_active?: boolean;
  rect: CaptureSelectionRect;
}

export interface GetChartPanesRequest {
  type: "GET_CHART_PANES";
}

export interface GetChartPanesResponse {
  ok: boolean;
  panes: ChartPane[];
  error: string | null;
}

// ── Multi-chart sequential analysis state ────────────────────────────────

export type MultiChartStatus = "pending" | "analyzing" | "done" | "error";

export interface MultiChartAnalysis {
  pane: ChartPane;
  status: MultiChartStatus;
  answer: string | null;
  error: string | null;
  cost_usd: number;
}
