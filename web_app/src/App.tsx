import { useState, useEffect, useCallback, useRef } from "react";
import { SymbolSearch }      from "./components/SymbolSearch";
import { TimeframeSelector } from "./components/TimeframeSelector";
import { ChartContainer }    from "./components/ChartContainer";
import { LevelsPanel }       from "./components/LevelsPanel";
import { AgentChatPanel }    from "./components/AgentChatPanel";
import { BacktestPanel, type BtTrade } from "./components/BacktestPanel";
import { api, type Bar, type KeyLevels } from "./api/client";

const INTRADAY_TF = new Set(["1m","3m","5m","15m","30m","1h","4h"]);
const WATCHLIST   = ["BANKNIFTY","NIFTY","SENSEX","RELIANCE","TCS","HDFCBANK","INFY","ICICIBANK","SBIN","WIPRO"];

function isMarketOpen(): boolean {
  const ist  = new Date(new Date().toLocaleString("en-US", { timeZone: "Asia/Kolkata" }));
  const mins = ist.getHours() * 60 + ist.getMinutes();
  return ist.getDay() >= 1 && ist.getDay() <= 5 && mins >= 9 * 60 + 15 && mins <= 15 * 60 + 30;
}

export function App() {
  const [symbol, setSymbol]     = useState("BANKNIFTY");
  const [exchange]              = useState("NSE");
  const [timeframe, setTimeframe] = useState("5m");
  const [bars, setBars]         = useState<Bar[]>([]);
  const [levels, setLevels]     = useState<KeyLevels | null>(null);
  const [barsLoading, setBarsLoading]     = useState(false);
  const [levelsLoading, setLevelsLoading] = useState(false);
  const [apiOk, setApiOk]       = useState<boolean | null>(null);
  const [marketOpen, setMarketOpen] = useState(false);
  const [error, setError]       = useState<string | null>(null);

  // Resizable sidebar
  const [sidebarW, setSidebarW] = useState(420);
  const [sidebarTab, setSidebarTab] = useState<"chat" | "backtest">("chat");
  const [btTrades, setBtTrades] = useState<BtTrade[]>([]);
  const [signalToast, setSignalToast] = useState<{ strategy: string; direction: string } | null>(null);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const dragging = useRef(false);
  const dragStartX = useRef(0);
  const dragStartW = useRef(420);

  const chartApiRef  = useRef<{ takeScreenshot: () => string | null } | null>(null);
  const liveTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ── Resize sidebar ────────────────────────────────────────────────────────
  useEffect(() => {
    function onMove(e: MouseEvent) {
      if (!dragging.current) return;
      const delta = dragStartX.current - e.clientX;
      setSidebarW(Math.max(280, Math.min(700, dragStartW.current + delta)));
    }
    function onUp() { dragging.current = false; document.body.style.cursor = ""; document.body.style.userSelect = ""; }
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup",   onUp);
    return () => { window.removeEventListener("mousemove", onMove); window.removeEventListener("mouseup", onUp); };
  }, []);

  function onDividerDown(e: React.MouseEvent) {
    dragging.current   = true;
    dragStartX.current = e.clientX;
    dragStartW.current = sidebarW;
    document.body.style.cursor     = "col-resize";
    document.body.style.userSelect = "none";
  }

  // ── Market open ───────────────────────────────────────────────────────────
  useEffect(() => {
    const check = () => setMarketOpen(isMarketOpen());
    check();
    const t = setInterval(check, 30_000);
    return () => clearInterval(t);
  }, []);

  // ── API health ────────────────────────────────────────────────────────────
  useEffect(() => {
    api.health().then(r => setApiOk(r.ok));
    const t = setInterval(() => api.health().then(r => setApiOk(r.ok)), 15_000);
    return () => clearInterval(t);
  }, []);

  // ── Load chart ────────────────────────────────────────────────────────────
  const loadChart = useCallback((silent = false) => {
    const ac = new AbortController();
    setError(null);
    if (!silent) { setBarsLoading(true); setLevelsLoading(true); setBars([]); setLevels(null); }

    Promise.all([
      fetch(`/api/chart/ohlcv?symbol=${symbol.toUpperCase()}&timeframe=${timeframe}&limit=400`, { signal: ac.signal }).then(r => r.json()),
      fetch(`/api/chart/levels?symbol=${symbol.toUpperCase()}&timeframe=${timeframe}`, { signal: ac.signal }).then(r => r.json()),
    ]).then(([ohlcv, lvls]) => {
      setBarsLoading(false); setLevelsLoading(false);
      if (ohlcv.bars) setBars(ohlcv.bars);
      else if (!silent) setError(ohlcv.detail ?? "Failed to load bars");
      setLevels(lvls.support !== undefined ? lvls : null);
    }).catch(err => {
      if ((err as Error).name === "AbortError") return;
      setBarsLoading(false); setLevelsLoading(false);
      if (!silent) setError(String(err));
    });
    return () => ac.abort();
  }, [symbol, timeframe]);

  useEffect(() => loadChart(false), [loadChart]);

  // ── Live refresh ──────────────────────────────────────────────────────────
  useEffect(() => {
    if (liveTimerRef.current) clearInterval(liveTimerRef.current);
    if (!marketOpen || !INTRADAY_TF.has(timeframe)) return;
    liveTimerRef.current = setInterval(() => loadChart(true), 30_000);
    return () => { if (liveTimerRef.current) clearInterval(liveTimerRef.current); };
  }, [marketOpen, symbol, timeframe, loadChart]);

  // ── Live signal scan: on each bar refresh, run best leaderboard strategy ──
  useEffect(() => {
    if (!marketOpen || !INTRADAY_TF.has(timeframe) || !apiOk) return;
    let cancelled = false;
    async function scan() {
      try {
        const lbRes = await fetch(`/api/backtest/leaderboard?symbol=${symbol}&timeframe=${timeframe}&limit=1`);
        if (!lbRes.ok || cancelled) return;
        const lb = await lbRes.json();
        const best = lb?.leaderboard?.[0];
        if (!best) return;

        const runRes = await fetch("/api/backtest/run", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ symbol, timeframe, strategy: best.strategy_id }),
        });
        if (!runRes.ok || cancelled) return;
        const run = await runRes.json();
        const lastTrade = run?.trades?.[run.trades.length - 1];
        if (!lastTrade) return;

        // Show toast if the last trade's entry is within the last 2 bars
        const nowUnix = Date.now() / 1000;
        const tfMins: Record<string, number> = { "1m": 1, "3m": 3, "5m": 5, "15m": 15, "30m": 30, "1h": 60, "4h": 240 };
        const barSecs = (tfMins[timeframe] ?? 5) * 60;
        if (lastTrade.entry_time && nowUnix - lastTrade.entry_time < barSecs * 2) {
          if (!cancelled) {
            setSignalToast({ strategy: best.strategy_name, direction: lastTrade.direction });
            if (toastTimer.current) clearTimeout(toastTimer.current);
            toastTimer.current = setTimeout(() => setSignalToast(null), 8000);
          }
        }
      } catch { /* ignore */ }
    }
    scan();
    const t = setInterval(scan, 5 * 60 * 1000);
    return () => { cancelled = true; clearInterval(t); };
  }, [marketOpen, apiOk, symbol, timeframe]);

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh", background: "var(--bg)", overflow: "hidden" }}>

      {/* ── Signal toast ──────────────────────────────────────────────────── */}
      {signalToast && (
        <div style={{
          position: "fixed", bottom: 24, left: "50%", transform: "translateX(-50%)",
          background: signalToast.direction === "BUY" ? "#1a7f371a" : "#f851491a",
          border: `1px solid ${signalToast.direction === "BUY" ? "var(--bullish)" : "var(--bearish)"}`,
          borderRadius: 8, padding: "8px 16px", fontSize: 12, fontWeight: 600,
          color: signalToast.direction === "BUY" ? "var(--bullish)" : "var(--bearish)",
          zIndex: 9999, cursor: "pointer", boxShadow: "0 4px 16px #00000055",
          display: "flex", alignItems: "center", gap: 10,
        }} onClick={() => setSignalToast(null)}>
          {signalToast.direction === "BUY" ? "▲ BUY" : "▼ SELL"} signal · {signalToast.strategy}
          <span style={{ fontSize: 10, opacity: 0.6 }}>✕</span>
        </div>
      )}

      {/* ── Toolbar ───────────────────────────────────────────────────────── */}
      <header style={{
        display: "flex", alignItems: "center", gap: 10,
        padding: "6px 12px", background: "var(--surface)",
        borderBottom: "1px solid var(--border)", flexShrink: 0,
      }}>
        <div style={{ fontWeight: "bold", fontSize: 13, color: "var(--accent)", letterSpacing: "0.06em", whiteSpace: "nowrap" }}>
          AGENT ADDA
        </div>

        <SymbolSearch value={symbol} onChange={setSymbol} />
        <TimeframeSelector current={timeframe} onChange={setTimeframe} />

        <button onClick={() => loadChart(false)} disabled={barsLoading} style={{ padding: "3px 9px", fontSize: 11 }}>
          {barsLoading ? "…" : "↺"}
        </button>

        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 10, fontSize: 11 }}>
          {marketOpen && INTRADAY_TF.has(timeframe) && <span className="live-badge">● LIVE</span>}
          <span style={{ color: apiOk === true ? "var(--bullish)" : "var(--bearish)" }}>
            ● {apiOk === true ? "API" : apiOk === false ? "offline" : "…"}
          </span>
        </div>
      </header>

      {/* ── Workspace ─────────────────────────────────────────────────────── */}
      <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>

        {/* Chart area */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
          {error && (
            <div style={{ padding: "5px 12px", background: "#f851491a", color: "var(--bearish)", fontSize: 11, flexShrink: 0 }}>
              {error}
            </div>
          )}
          <ChartContainer
            bars={bars} levels={levels} symbol={symbol} timeframe={timeframe}
            markers={btTrades}
            onReady={api => { chartApiRef.current = api; }}
          />
        </div>

        {/* Resize handle */}
        <div
          onMouseDown={onDividerDown}
          style={{
            width: 5, flexShrink: 0, cursor: "col-resize",
            background: "var(--border)",
            transition: "background 0.15s",
          }}
          onMouseEnter={e => (e.currentTarget.style.background = "var(--accent)")}
          onMouseLeave={e => (e.currentTarget.style.background = "var(--border)")}
        />

        {/* Sidebar */}
        <div style={{
          width: sidebarW, flexShrink: 0,
          display: "flex", flexDirection: "column", overflow: "hidden",
          background: "var(--surface)",
        }}>
          {/* Watchlist */}
          <div style={{ padding: "6px 10px", borderBottom: "1px solid var(--border)", flexShrink: 0 }}>
            <div style={{ fontSize: 10, color: "var(--muted)", marginBottom: 5, fontWeight: "bold", letterSpacing: "0.08em" }}>
              WATCHLIST
            </div>
            <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
              {WATCHLIST.map(s => (
                <button
                  key={s}
                  onClick={() => setSymbol(s)}
                  style={{
                    fontSize: 10, padding: "2px 7px", borderRadius: 4,
                    border: `1px solid ${symbol === s ? "var(--accent)" : "var(--border)"}`,
                    background: symbol === s ? "#1f6feb22" : "transparent",
                    color: symbol === s ? "var(--accent)" : "var(--muted)",
                  }}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>

          {/* Key levels */}
          <div style={{ padding: "8px 10px", borderBottom: "1px solid var(--border)", flexShrink: 0 }}>
            <LevelsPanel levels={levels} loading={levelsLoading} />
          </div>

          {/* Chat / Backtest tab strip */}
          <div style={{ display: "flex", borderBottom: "1px solid var(--border)", flexShrink: 0 }}>
            {(["chat", "backtest"] as const).map(tab => (
              <button
                key={tab}
                onClick={() => setSidebarTab(tab)}
                style={{
                  flex: 1, padding: "7px 0", fontSize: 11, fontWeight: "bold",
                  background: sidebarTab === tab ? "#1f6feb22" : "transparent",
                  color: sidebarTab === tab ? "var(--accent)" : "var(--muted)",
                  border: "none", borderBottom: sidebarTab === tab ? "2px solid var(--accent)" : "2px solid transparent",
                  cursor: "pointer", letterSpacing: "0.06em",
                }}
              >
                {tab === "chat" ? "💬 Chat" : "📊 Backtest"}
              </button>
            ))}
            {sidebarTab === "backtest" && btTrades.length > 0 && (
              <button
                onClick={() => setBtTrades([])}
                title="Clear chart markers"
                style={{ padding: "5px 8px", fontSize: 10, background: "transparent", color: "#8b949e", border: "none", cursor: "pointer" }}
              >
                ✕ clear
              </button>
            )}
          </div>

          {/* Panel content */}
          <div style={{ flex: 1, padding: 8, overflow: "hidden", minHeight: 0 }}>
            {sidebarTab === "chat" ? (
              <AgentChatPanel
                symbol={symbol} exchange={exchange} timeframe={timeframe}
                onCapture={() => chartApiRef.current?.takeScreenshot() ?? null}
              />
            ) : (
              <BacktestPanel
                symbol={symbol} timeframe={timeframe}
                onResult={trades => setBtTrades(trades)}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
