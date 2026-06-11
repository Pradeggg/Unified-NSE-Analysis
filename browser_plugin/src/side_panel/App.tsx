import { useState, useEffect, useCallback } from "react";
import { Header } from "./components/Header";
import { CaptureButton } from "./components/CaptureButton";
import { LevelsPanel } from "./components/LevelsPanel";
import { PatternPanel } from "./components/PatternPanel";
import { ChatPanel } from "./components/ChatPanel";
import { useChartContext } from "./store/chartContext";
import {
  analyzeChart,
  askFollowUp,
  fetchKeyLevels,
  fetchPatterns,
  healthCheck,
} from "./api/client";
import type { Exchange, Timeframe, AnalysisResult, PageMetadata } from "../types";
import "./App.css";

export function App() {
  // ── State ─────────────────────────────────────────────────────────────
  const [symbol, setSymbol] = useState("BANKNIFTY");
  const [exchange, setExchange] = useState<Exchange>("NSE");
  const [timeframe, setTimeframe] = useState<Timeframe>("5m");
  const [apiReachable, setApiReachable] = useState(false);
  const [capturing, setCapturing] = useState(false);

  const { ctx, loading, createContext, updateLevels, addConclusion, updatePatterns, resetContext } =
    useChartContext();

  // ── API health check ──────────────────────────────────────────────────
  useEffect(() => {
    let alive = true;
    const check = async () => {
      const ok = await healthCheck();
      if (alive) setApiReachable(ok);
    };
    check();
    const timer = setInterval(check, 15_000);
    return () => { alive = false; clearInterval(timer); };
  }, []);

  // ── Listen for page metadata from content script ──────────────────────
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

  // ── Reset context when symbol/exchange/timeframe changes ─────────────
  useEffect(() => {
    if (ctx && (ctx.symbol !== symbol || ctx.exchange !== exchange || ctx.timeframe !== timeframe)) {
      resetContext();
    }
  }, [symbol, exchange, timeframe]);

  // ── Screenshot capture (CAPTURED-FIRST) ──────────────────────────────
  const handleCapture = useCallback(async () => {
    if (capturing) return;
    setCapturing(true);
    try {
      // Get the active tab's screenshot.
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (!tab?.id) throw new Error("No active tab");

      const dataUrl: string = await new Promise((resolve, reject) => {
        chrome.tabs.captureVisibleTab(
          tab.windowId!,
          { format: "png" },
          (url) => {
            if (chrome.runtime.lastError) reject(chrome.runtime.lastError);
            else resolve(url);
          }
        );
      });

      createContext(symbol, exchange, timeframe, dataUrl);

      // Fetch PG key levels and patterns in parallel.
      const [levelsRes, patternsRes] = await Promise.all([
        fetchKeyLevels(symbol, exchange, timeframe),
        fetchPatterns(symbol, exchange, timeframe),
      ]);
      if (levelsRes.ok && levelsRes.data) updateLevels(levelsRes.data);
      if (patternsRes.ok && patternsRes.data) updatePatterns(patternsRes.data.patterns);

      // Run initial analysis - setQuestion triggers ChatPanel default prompt.
      setSymbol(symbol);
    } catch (err) {
      console.error("Capture failed:", err);
    } finally {
      setCapturing(false);
    }
  }, [capturing, symbol, exchange, timeframe, createContext, updateLevels, updatePatterns]);

  // ── Send analysis / follow-up ─────────────────────────────────────────
  const handleSend = useCallback(
    async (q: string): Promise<AnalysisResult | null> => {
      if (!ctx) return null;

      if (ctx.llm_conclusions.length === 0) {
        // First question — send full capture payload with screenshot.
        const res = await analyzeChart({
          image: ctx.screenshot_data_url,
          source_url: null,
          page_title: null,
          user_symbol: symbol,
          exchange,
          timeframe,
          visible_indicators: ctx.visible_indicators,
          user_question: q,
          conflict_policy: "prefer_pg",
        });
        if (res.ok && res.data) {
          addConclusion(res.data.answer);
          if (res.data.key_levels) updateLevels(res.data.key_levels);
          if (res.data.pattern_findings?.length) updatePatterns(res.data.pattern_findings);
        }
        return res.data ?? null;
      } else {
        // Follow-up — bind to active capture context.
        const res = await askFollowUp(ctx.capture_id, q);
        if (res.ok && res.data) addConclusion(res.data.answer);
        return res.data ?? null;
      }
    },
    [ctx, symbol, exchange, timeframe, addConclusion, updateLevels, updatePatterns]
  );

  if (loading) {
    return <div className="loading">Loading…</div>;
  }

  return (
    <div className="app">
      <Header
        symbol={symbol}
        exchange={exchange}
        timeframe={timeframe}
        apiReachable={apiReachable}
        onSymbolChange={(s) => setSymbol(s)}
        onExchangeChange={(e) => setExchange(e)}
        onTimeframeChange={(t) => setTimeframe(t)}
      />

      <main className="main">
        <CaptureButton
          disabled={!apiReachable}
          capturing={capturing}
          capturedAt={ctx?.captured_at ?? null}
          onCapture={handleCapture}
        />

        {ctx && (
          <>
            <LevelsPanel
              levels={ctx.computed_levels}
              currentPrice={null}
            />
            <PatternPanel
              patterns={ctx.pattern_findings}
              symbol={symbol}
              timeframe={timeframe}
            />
          </>
        )}

        <ChatPanel
          captureId={ctx?.capture_id ?? null}
          onSend={handleSend}
        />
      </main>

      <footer className="footer">
        Research only — not investment advice
      </footer>
    </div>
  );
}
