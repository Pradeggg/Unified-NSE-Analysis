import { useState, useEffect, useCallback } from "react";
import { Header }        from "./components/Header";
import { CaptureButton } from "./components/CaptureButton";
import { ChatPanel }     from "./components/ChatPanel";
import { useChartContext } from "./store/chartContext";
import { analyzeChart, askFollowUp, healthCheck } from "./api/client";
import type { Exchange, Timeframe, AnalysisResult, PageMetadata } from "../types";
import "./App.css";

export function App() {
  const [symbol, setSymbol]       = useState("BANKNIFTY");
  const [exchange, setExchange]   = useState<Exchange>("NSE");
  const [timeframe, setTimeframe] = useState<Timeframe>("5m");
  const [apiReachable, setApiReachable] = useState(false);
  const [capturing, setCapturing] = useState(false);
  const [analysing, setAnalysing] = useState(false);

  const { ctx, loading, createContext, addConclusion, resetContext } = useChartContext();

  // ── API health ────────────────────────────────────────────────────────────
  useEffect(() => {
    let alive = true;
    const check = async () => { const ok = await healthCheck(); if (alive) setApiReachable(ok); };
    check();
    const timer = setInterval(check, 15_000);
    return () => { alive = false; clearInterval(timer); };
  }, []);

  // ── Content script → update symbol/TF from page ──────────────────────────
  useEffect(() => {
    function onMessage(msg: { type: string; payload?: PageMetadata }) {
      if (msg.type === "PAGE_METADATA" && msg.payload) {
        const { symbol: s, exchange: e, timeframe: t } = msg.payload;
        if (s) setSymbol(s);
        if (e) setExchange(e);
        if (t) setTimeframe(t);
      }
    }
    chrome.runtime.onMessage.addListener(onMessage);
    return () => chrome.runtime.onMessage.removeListener(onMessage);
  }, []);

  // ── Reset context when symbol/TF changes ─────────────────────────────────
  useEffect(() => {
    if (ctx && (ctx.symbol !== symbol || ctx.exchange !== exchange || ctx.timeframe !== timeframe)) {
      resetContext();
    }
  }, [symbol, exchange, timeframe]);

  // ── Capture + auto-analyse ────────────────────────────────────────────────
  const handleCapture = useCallback(async () => {
    if (capturing || analysing) return;
    setCapturing(true);
    try {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (!tab?.id) throw new Error("No active tab");

      // Screenshot the visible chart.
      const dataUrl: string = await new Promise((resolve, reject) => {
        chrome.tabs.captureVisibleTab(
          tab.windowId!,
          { format: "png" },
          (url) => chrome.runtime.lastError ? reject(chrome.runtime.lastError) : resolve(url)
        );
      });

      createContext(symbol, exchange, timeframe, dataUrl);
      setCapturing(false);
      setAnalysing(true);

      // Auto-fire initial analysis immediately — image is the source of truth.
      const res = await analyzeChart({
        image: dataUrl,
        source_url: tab.url ?? null,
        page_title: tab.title ?? null,
        user_symbol: symbol,
        exchange,
        timeframe,
        visible_indicators: [],
        user_question: "Analyze this chart and give me the full setup.",
        conflict_policy: "prefer_pg",
      });
      if (res.ok && res.data) addConclusion(res.data.answer);
    } catch (err) {
      console.error("Capture/analysis failed:", err);
    } finally {
      setCapturing(false);
      setAnalysing(false);
    }
  }, [capturing, analysing, symbol, exchange, timeframe, createContext, addConclusion]);

  // ── Follow-up send ────────────────────────────────────────────────────────
  const handleSend = useCallback(
    async (q: string): Promise<AnalysisResult | null> => {
      if (!ctx) return null;
      const res = await askFollowUp(ctx.capture_id, q);
      if (res.ok && res.data) addConclusion(res.data.answer);
      return res.data ?? null;
    },
    [ctx, addConclusion]
  );

  if (loading) return <div className="loading">Loading…</div>;

  const busy = capturing || analysing;

  return (
    <div className="app">
      <Header
        symbol={symbol}
        exchange={exchange}
        timeframe={timeframe}
        apiReachable={apiReachable}
        onSymbolChange={setSymbol}
        onExchangeChange={setExchange}
        onTimeframeChange={setTimeframe}
      />

      <main className="main">
        <CaptureButton
          disabled={!apiReachable || busy}
          capturing={capturing}
          capturedAt={ctx?.captured_at ?? null}
          onCapture={handleCapture}
        />

        {analysing && (
          <div className="analysing-banner">
            🔍 Agent Adda is reading the chart…
          </div>
        )}

        {/* Chat panel — locked for follow-up until initial analysis has run */}
        <ChatPanel
          captureId={ctx?.llm_conclusions.length ? ctx.capture_id : null}
          initialAnalysis={ctx?.llm_conclusions[0]}
          onSend={handleSend}
        />
      </main>

      <footer className="footer">Research only — not investment advice</footer>
    </div>
  );
}
