// Local Agent Adda API client.
// Calls localhost:8765 — the local FastAPI server (agent_adda/web_api/main.py).

import type {
  ApiResponse,
  AnalysisResult,
  ChartCapturePayload,
  KeyLevels,
  PatternFinding,
  BacktestResult,
  LeaderRow,
  RicResult,
  DrawOverlayResponse,
} from "../../types";

const BASE_URL = "http://localhost:8765";
const TOKEN_KEY = "agent_adda_api_token";
const REQUEST_TIMEOUT_MS = 45_000;

// ── Auth token ────────────────────────────────────────────────────────────

async function getToken(): Promise<string> {
  const result = await chrome.storage.local.get(TOKEN_KEY);
  return (result[TOKEN_KEY] as string) || "";
}

export async function setToken(token: string): Promise<void> {
  await chrome.storage.local.set({ [TOKEN_KEY]: token });
}

// ── Base fetch with timeout + auth ────────────────────────────────────────

async function apiFetch<T>(
  path: string,
  options: RequestInit = {}
): Promise<ApiResponse<T>> {
  const token = await getToken();
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  try {
    const res = await fetch(`${BASE_URL}${path}`, {
      ...options,
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(options.headers ?? {}),
      },
    });
    clearTimeout(timer);

    if (!res.ok) {
      const text = await res.text().catch(() => "");
      return { ok: false, data: null, error: text || res.statusText, status_code: res.status };
    }

    const data = (await res.json()) as T;
    return { ok: true, data, error: null, status_code: res.status };
  } catch (err) {
    clearTimeout(timer);
    if ((err as Error).name === "AbortError") {
      return { ok: false, data: null, error: "Request timed out after 45s", status_code: 0 };
    }
    return { ok: false, data: null, error: (err as Error).message, status_code: 0 };
  }
}

// ── Health check ──────────────────────────────────────────────────────────

export async function healthCheck(): Promise<boolean> {
  const res = await apiFetch<{ status: string }>("/api/health");
  return res.ok && res.data?.status === "ok";
}

// ── Chart analysis ────────────────────────────────────────────────────────

export async function analyzeChart(
  payload: ChartCapturePayload
): Promise<ApiResponse<AnalysisResult>> {
  return apiFetch<AnalysisResult>("/api/analysis/chart", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

// ── Follow-up question bound to active capture context ───────────────────

export async function askFollowUp(
  captureId: string,
  question: string
): Promise<ApiResponse<AnalysisResult>> {
  return apiFetch<AnalysisResult>("/api/analysis/followup", {
    method: "POST",
    body: JSON.stringify({ capture_id: captureId, question }),
  });
}

// ── Key levels from PG evidence ───────────────────────────────────────────

export async function fetchKeyLevels(
  symbol: string,
  exchange: string,
  timeframe: string
): Promise<ApiResponse<KeyLevels>> {
  const params = new URLSearchParams({ symbol, exchange, timeframe });
  return apiFetch<KeyLevels>(`/api/chart/levels?${params}`);
}

// ── Backtest ──────────────────────────────────────────────────────────────

export async function runBacktest(
  symbol: string,
  timeframe: string,
  strategy: string,
  initialCapital = 100000,
  riskPct = 1.0,
  maxHoldBars = 20,
): Promise<ApiResponse<BacktestResult>> {
  return apiFetch<BacktestResult>("/api/backtest/run", {
    method: "POST",
    body: JSON.stringify({
      symbol, timeframe, strategy,
      initial_capital: initialCapital,
      risk_per_trade_pct: riskPct,
      max_holding_bars: maxHoldBars,
    }),
  });
}

export async function fetchStrategies(): Promise<ApiResponse<{ strategies: Array<{ id: string; name: string; min_bars: number }> }>> {
  return apiFetch("/api/backtest/strategies");
}

export async function fetchLeaderboard(
  symbol?: string,
  timeframe?: string,
  limit = 20,
): Promise<ApiResponse<{ leaderboard: LeaderRow[]; count: number }>> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (symbol)    params.set("symbol", symbol);
  if (timeframe) params.set("timeframe", timeframe);
  return apiFetch(`/api/backtest/leaderboard?${params}`);
}

// ── Pattern findings from K13 engine ──────────────────────────────────────

export async function fetchPatterns(
  symbol: string,
  exchange: string,
  timeframe: string
): Promise<ApiResponse<{ patterns: PatternFinding[] }>> {
  const params = new URLSearchParams({ symbol, exchange, timeframe });
  return apiFetch<{ patterns: PatternFinding[] }>(`/api/patterns/query?${params}`);
}

// ── RIC (Recursive Insights Composite) ───────────────────────────────────

export async function fetchRic(
  symbol:    string,
  timeframe: string,
  exchange:  string  = "NSE",
  captureId?: string,
): Promise<ApiResponse<RicResult>> {
  const params = new URLSearchParams({ symbol, timeframe, exchange });
  if (captureId) params.set("capture_id", captureId);
  return apiFetch<RicResult>(`/api/ric/analyze?${params}`);
}

export async function sendDrawSignals(signals: unknown[]): Promise<void> {
  const response = (await chrome.runtime.sendMessage({
    type: "DRAW_RIC_LEVELS",
    signals,
  })) as DrawOverlayResponse | undefined;
  if (!response?.ok) {
    throw new Error(response?.error ?? "Could not draw RIC levels on the active chart.");
  }
}

export async function clearChartOverlay(): Promise<void> {
  const response = (await chrome.runtime.sendMessage({
    type: "CLEAR_RIC_OVERLAY",
  })) as DrawOverlayResponse | undefined;
  if (!response?.ok) {
    throw new Error(response?.error ?? "Could not clear the RIC chart overlay.");
  }
}
