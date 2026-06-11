import { useState, useEffect, useCallback } from "react";
import { SymbolSearch }      from "./components/SymbolSearch";
import { TimeframeSelector } from "./components/TimeframeSelector";
import { ChartContainer }    from "./components/ChartContainer";
import { LevelsPanel }       from "./components/LevelsPanel";
import { AgentChatPanel }    from "./components/AgentChatPanel";
import { api, type Bar, type KeyLevels } from "./api/client";

export function App() {
  const [symbol, setSymbol]       = useState("BANKNIFTY");
  const [exchange]                = useState("NSE");
  const [timeframe, setTimeframe] = useState("5m");
  const [bars, setBars]           = useState<Bar[]>([]);
  const [levels, setLevels]       = useState<KeyLevels | null>(null);
  const [barsLoading, setBarsLoading]     = useState(false);
  const [levelsLoading, setLevelsLoading] = useState(false);
  const [apiOk, setApiOk]         = useState<boolean | null>(null);
  const [error, setError]         = useState<string | null>(null);

  // ── API health ─────────────────────────────────────────────────────────────
  useEffect(() => {
    api.health().then((r) => setApiOk(r.ok));
    const t = setInterval(() => api.health().then((r) => setApiOk(r.ok)), 15_000);
    return () => clearInterval(t);
  }, []);

  // ── Load chart data ────────────────────────────────────────────────────────
  const loadChart = useCallback(async () => {
    setError(null);
    setBarsLoading(true);
    setLevelsLoading(true);

    const [ohlcvRes, levelsRes] = await Promise.all([
      api.getOhlcv(symbol, timeframe, 300),
      api.getKeyLevels(symbol, timeframe),
    ]);

    setBarsLoading(false);
    setLevelsLoading(false);

    if (ohlcvRes.ok) {
      setBars(ohlcvRes.data.bars);
    } else {
      setError(ohlcvRes.error);
      setBars([]);
    }

    setLevels(levelsRes.ok ? levelsRes.data : null);
  }, [symbol, timeframe]);

  useEffect(() => { loadChart(); }, [loadChart]);

  return (
    <div style={{
      display: "flex", flexDirection: "column", height: "100vh",
      background: "var(--bg)", overflow: "hidden",
    }}>
      {/* ── Toolbar ─────────────────────────────────────────────────────── */}
      <header style={{
        display: "flex", alignItems: "center", gap: 12,
        padding: "8px 14px",
        background: "var(--surface)",
        borderBottom: "1px solid var(--border)",
        flexShrink: 0,
      }}>
        {/* Logo */}
        <div style={{ fontWeight: "bold", fontSize: 14, color: "var(--accent)", letterSpacing: "0.06em" }}>
          AGENT ADDA
        </div>

        <SymbolSearch
          value={symbol}
          onChange={(s) => { setSymbol(s); }}
        />

        <TimeframeSelector current={timeframe} onChange={setTimeframe} />

        <button
          onClick={loadChart}
          disabled={barsLoading}
          style={{ padding: "4px 10px", fontSize: 11 }}
        >
          {barsLoading ? "…" : "↺ Refresh"}
        </button>

        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 6, fontSize: 11 }}>
          <span style={{ color: apiOk === true ? "var(--bullish)" : "var(--bearish)" }}>
            ● {apiOk === true ? "API connected" : apiOk === false ? "API offline" : "checking…"}
          </span>
        </div>
      </header>

      {/* ── Main workspace ─────────────────────────────────────────────── */}
      <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>

        {/* Left: chart */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
          {error && (
            <div style={{ padding: "8px 14px", background: "#f851491a", color: "var(--bearish)", fontSize: 12 }}>
              {error}
            </div>
          )}
          <ChartContainer
            bars={bars}
            levels={levels}
            symbol={symbol}
            timeframe={timeframe}
          />
        </div>

        {/* Right sidebar */}
        <div style={{
          width: 320, flexShrink: 0,
          borderLeft: "1px solid var(--border)",
          display: "flex", flexDirection: "column", gap: 0, overflow: "hidden",
        }}>
          {/* Key levels (top quarter) */}
          <div style={{ padding: 12, borderBottom: "1px solid var(--border)", flexShrink: 0 }}>
            <LevelsPanel levels={levels} loading={levelsLoading} />
          </div>

          {/* Agent chat (remaining space) */}
          <div style={{ flex: 1, overflow: "hidden", padding: 12 }}>
            <AgentChatPanel
              symbol={symbol}
              exchange={exchange}
              timeframe={timeframe}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
