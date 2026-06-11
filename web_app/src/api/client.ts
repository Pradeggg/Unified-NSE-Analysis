// Agent Adda Web App — API client (calls localhost:8765 via Vite proxy /api)

const BASE = "/api";

export type Bar = {
  time: number;   // UNIX seconds
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
};

export type OhlcvResponse = {
  symbol: string;
  exchange: string;
  timeframe: string;
  source: string;
  bars: Bar[];
};

export type SymbolInfo = {
  symbol: string;
  name: string;
  sector: string;
  industry: string;
  exchange: string;
  stage: number | null;
  rs_rank: number | null;
  market_cap: number | null;
};

export type SearchResult = { symbol: string; name: string; score: number };

export type KeyLevels = {
  support: number | null;
  resistance: number | null;
  ema20: number | null;
  ema50: number | null;
  ema100: number | null;
  ema200: number | null;
  supertrend: number | null;
  supertrend_direction: "bullish" | "bearish" | null;
  vwap: number | null;
};

async function get<T>(path: string): Promise<{ ok: true; data: T } | { ok: false; error: string }> {
  try {
    const res = await fetch(BASE + path);
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      return { ok: false, error: body.detail ?? `HTTP ${res.status}` };
    }
    return { ok: true, data: await res.json() };
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

export const api = {
  health: () => get<{ status: string }>("/health"),

  searchSymbols: (q: string, limit = 10) =>
    get<{ query: string; results: SearchResult[] }>(`/symbols/search?q=${encodeURIComponent(q)}&limit=${limit}`),

  getSymbolInfo: (symbol: string) =>
    get<SymbolInfo>(`/symbols/${symbol.toUpperCase()}`),

  getOhlcv: (symbol: string, timeframe = "1D", limit = 300) =>
    get<OhlcvResponse>(`/chart/ohlcv?symbol=${symbol.toUpperCase()}&timeframe=${timeframe}&limit=${limit}`),

  getKeyLevels: (symbol: string, timeframe = "1D") =>
    get<KeyLevels>(`/chart/levels?symbol=${symbol.toUpperCase()}&timeframe=${timeframe}`),

  analyzeChart: (payload: object) =>
    fetch(BASE + "/analysis/chart", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }).then((r) => r.json()),

  followUp: (captureId: string, question: string) =>
    fetch(BASE + "/analysis/followup", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ capture_id: captureId, question }),
    }).then((r) => r.json()),
};
