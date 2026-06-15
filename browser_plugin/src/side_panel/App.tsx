import { useState, useEffect, useCallback } from "react";
import { Header }           from "./components/Header";
import { CaptureButton }    from "./components/CaptureButton";
import { ChatPanel }        from "./components/ChatPanel";
import { BacktestTab }      from "./components/BacktestTab";
import { RicTab }           from "./components/RicTab";
import { MultiChartPanel }  from "./components/MultiChartPanel";
import { useChartContext }   from "./store/chartContext";
import { analyzeChart, askFollowUp, healthCheck } from "./api/client";
import type {
  Exchange,
  Timeframe,
  AnalysisResult,
  PageMetadata,
  CaptureVisibleTabRequest,
  CaptureVisibleTabResponse,
  SelectCaptureAreaResponse,
  CaptureSelectionRect,
  SelectCaptureAreaRequest,
  GetChartPanesRequest,
  GetChartPanesResponse,
  MultiChartAnalysis,
} from "../types";
import "./App.css";

type MainTab = "analyze" | "backtest" | "ric" | "multi";

export function App() {
  const [symbol, setSymbol]       = useState("BANKNIFTY");
  const [exchange, setExchange]   = useState<Exchange>("NSE");
  const [timeframe, setTimeframe] = useState<Timeframe>("5m");
  const [apiReachable, setApiReachable] = useState(false);
  const [capturing, setCapturing] = useState(false);
  const [analysing, setAnalysing] = useState(false);
  const [captureError, setCaptureError] = useState<string | null>(null);
  const [mainTab, setMainTab]     = useState<MainTab>("analyze");
  const [multiAnalyses, setMultiAnalyses] = useState<MultiChartAnalysis[]>([]);
  const [multiRunning, setMultiRunning]   = useState(false);

  const { ctx, loading, createContext, addConclusion, applyAnalysisResult, resetContext } = useChartContext();


  function applyPageMetadata(metadata: PageMetadata) {
    const { symbol: s, exchange: e, timeframe: t } = metadata;
    if (s) setSymbol(s);
    if (e) setExchange(e);
    if (t) setTimeframe(t);
  }

  async function captureVisibleTabDirect(): Promise<CaptureVisibleTabResponse> {
    const [tab] = await chrome.tabs.query({
      active: true,
      lastFocusedWindow: true,
    });
    if (!tab?.id || tab.windowId == null) {
      throw new Error("No active chart tab was found.");
    }

    const dataUrl = await new Promise<string>((resolve, reject) => {
      chrome.tabs.captureVisibleTab(tab.windowId, { format: "png" }, (url) => {
        const error = chrome.runtime.lastError;
        if (error) {
          reject(new Error(error.message));
          return;
        }
        if (!url) {
          reject(new Error("Chrome returned an empty screenshot."));
          return;
        }
        resolve(url);
      });
    });

    return {
      ok: true,
      dataUrl,
      tab: {
        id: tab.id,
        windowId: tab.windowId,
        url: tab.url ?? null,
        title: tab.title ?? null,
      },
      error: null,
    };
  }

  async function requestVisibleTabCapture(): Promise<CaptureVisibleTabResponse> {
    const request: CaptureVisibleTabRequest = { type: "CAPTURE_VISIBLE_TAB" };
    try {
      return await new Promise((resolve, reject) => {
        chrome.runtime.sendMessage(request, (response: CaptureVisibleTabResponse | undefined) => {
          const error = chrome.runtime.lastError;
          if (error) {
            reject(new Error(error.message));
            return;
          }
          if (!response) {
            reject(new Error("The background worker did not return a capture response."));
            return;
          }
          resolve(response);
        });
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      if (
        message.includes("message port closed") ||
        message.includes("Receiving end does not exist") ||
        message.includes("background worker")
      ) {
        return captureVisibleTabDirect();
      }
      throw error;
    }
  }

  async function requestAreaSelection(): Promise<SelectCaptureAreaResponse> {
    const request: SelectCaptureAreaRequest = { type: "SELECT_CAPTURE_AREA" };
    return new Promise((resolve, reject) => {
      chrome.runtime.sendMessage(request, (response: SelectCaptureAreaResponse | undefined) => {
        const error = chrome.runtime.lastError;
        if (error) {
          reject(new Error(error.message));
          return;
        }
        if (!response) {
          reject(new Error("The chart page did not return a selected area."));
          return;
        }
        resolve(response);
      });
    });
  }

  async function cropDataUrlToRect(dataUrl: string, rect: CaptureSelectionRect): Promise<string> {
    const image = await new Promise<HTMLImageElement>((resolve, reject) => {
      const img = new Image();
      img.onload = () => resolve(img);
      img.onerror = () => reject(new Error("Failed to load screenshot for cropping."));
      img.src = dataUrl;
    });

    const scaleX = image.naturalWidth / rect.viewportWidth;
    const scaleY = image.naturalHeight / rect.viewportHeight;
    const sourceX = Math.max(0, Math.round(rect.x * scaleX));
    const sourceY = Math.max(0, Math.round(rect.y * scaleY));
    const sourceWidth = Math.min(image.naturalWidth - sourceX, Math.round(rect.width * scaleX));
    const sourceHeight = Math.min(image.naturalHeight - sourceY, Math.round(rect.height * scaleY));

    if (sourceWidth <= 0 || sourceHeight <= 0) {
      throw new Error("Selected area is outside the captured screenshot.");
    }

    const canvas = document.createElement("canvas");
    canvas.width = sourceWidth;
    canvas.height = sourceHeight;
    const context = canvas.getContext("2d");
    if (!context) {
      throw new Error("Browser canvas is unavailable for screenshot crop.");
    }
    context.drawImage(
      image,
      sourceX,
      sourceY,
      sourceWidth,
      sourceHeight,
      0,
      0,
      sourceWidth,
      sourceHeight
    );
    return canvas.toDataURL("image/png");
  }

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
        applyPageMetadata(msg.payload);
      }
    }
    chrome.runtime.onMessage.addListener(onMessage);

    chrome.runtime.sendMessage({ type: "GET_ACTIVE_METADATA" }, (msg) => {
      if (chrome.runtime.lastError) return;
      if (msg?.type === "ACTIVE_METADATA" && msg.payload) {
        applyPageMetadata(msg.payload);
      }
    });

    return () => chrome.runtime.onMessage.removeListener(onMessage);
  }, []);

  // ── Reset context when symbol/TF changes ─────────────────────────────────
  useEffect(() => {
    if (ctx && (ctx.symbol !== symbol || ctx.exchange !== exchange || ctx.timeframe !== timeframe)) {
      resetContext();
    }
  }, [symbol, exchange, timeframe]);

  async function requestChartPanes(): Promise<GetChartPanesResponse> {
    const request: GetChartPanesRequest = { type: "GET_CHART_PANES" };
    return new Promise((resolve, reject) => {
      chrome.runtime.sendMessage(request, (response: GetChartPanesResponse | undefined) => {
        const error = chrome.runtime.lastError;
        if (error) { reject(new Error(error.message)); return; }
        if (!response) { reject(new Error("No panes response from content script.")); return; }
        resolve(response);
      });
    });
  }

  // ── Capture + auto-analyse ────────────────────────────────────────────────
  const handleCapture = useCallback(async (mode: "visible" | "area" = "visible") => {
    if (capturing || analysing) return;
    setCaptureError(null);
    setCapturing(true);
    try {
      const selection = mode === "area" ? await requestAreaSelection() : null;
      if (selection && (!selection.ok || !selection.rect)) {
        throw new Error(selection.error ?? "Area selection failed.");
      }

      const capture = await requestVisibleTabCapture();
      if (!capture.ok || !capture.dataUrl) {
        throw new Error(capture.error ?? "Chart capture failed.");
      }

      const imageDataUrl = selection?.rect
        ? await cropDataUrlToRect(capture.dataUrl, selection.rect)
        : capture.dataUrl;

      createContext(symbol, exchange, timeframe, imageDataUrl);
      setCapturing(false);
      setAnalysing(true);

      // Auto-fire initial analysis immediately — image is the source of truth.
      const res = await analyzeChart({
        image: imageDataUrl,
        source_url: capture.tab?.url ?? null,
        page_title: capture.tab?.title ?? null,
        user_symbol: symbol,
        exchange,
        timeframe,
        visible_indicators: [],
        user_question: [
          "Analyze the captured chart as a technical trading setup.",
          `MANDATORY: Start the answer with ▶ IDENTITY and include Visible, Context (${exchange}:${symbol} · ${timeframe}), Match, and Type before any bias or trade setup.`,
          "If the screenshot/header is cropped or unreadable, explicitly say the visible instrument is unreadable and use the provided chart context.",
          "Inventory every visible indicator/annotation before concluding: EMAs, Supertrend, RSI, volume, levels, labels, and drawn zones.",
          "Use private plan-of-thought decomposition and tree-of-thought scenario checks for bull, bear, and range/no-trade cases.",
          "Then produce precise support, resistance, invalidation, targets, volume/RSI read, scenarios, final trade plan, and confidence.",
        ].join(" "),
        conflict_policy: "prefer_pg",
      });
      if (!res.ok || !res.data) {
        throw new Error(res.error ?? "Agent Adda analysis failed.");
      }
      if (res.data.error) {
        throw new Error(res.data.error);
      }
      applyAnalysisResult(res.data);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setCaptureError(message);
      console.error("Capture/analysis failed:", err);
    } finally {
      setCapturing(false);
      setAnalysing(false);
    }
  }, [capturing, analysing, symbol, exchange, timeframe, createContext, applyAnalysisResult]);

  // ── Multi-chart sequential capture+analyse ───────────────────────────────
  const handleMultiCapture = useCallback(async () => {
    if (capturing || analysing || multiRunning) return;
    setCaptureError(null);
    setMultiAnalyses([]);
    setMultiRunning(true);
    setCapturing(true);

    try {
      // 1. Ask the content script to identify all chart panes.
      const panesResp = await requestChartPanes();
      if (!panesResp.ok || panesResp.panes.length === 0) {
        throw new Error(panesResp.error ?? "No chart panes detected on this page.");
      }

      // 2. One full-page screenshot for all panes.
      const capture = await requestVisibleTabCapture();
      if (!capture.ok || !capture.dataUrl) {
        throw new Error(capture.error ?? "Chart capture failed.");
      }
      setCapturing(false);

      // 3. Seed the analysis slots and switch to the Multi tab.
      const initialSlots: MultiChartAnalysis[] = panesResp.panes.map((pane) => ({
        pane,
        status: "pending",
        answer: null,
        error: null,
        cost_usd: 0,
      }));
      setMultiAnalyses(initialSlots);
      setMainTab("multi");

      // 4. Analyze each pane sequentially so results stream in one by one.
      for (let i = 0; i < panesResp.panes.length; i++) {
        const pane = panesResp.panes[i];
        setMultiAnalyses((prev) =>
          prev.map((a, idx) => (idx === i ? { ...a, status: "analyzing" } : a)),
        );

        try {
          const croppedDataUrl = await cropDataUrlToRect(capture.dataUrl!, pane.rect);
          const sym   = pane.symbol   ?? symbol;
          const exch  = pane.exchange ?? exchange;
          const tf    = pane.timeframe ?? timeframe;

          const res = await analyzeChart({
            image:      croppedDataUrl,
            source_url: capture.tab?.url ?? null,
            page_title: capture.tab?.title ?? null,
            user_symbol: sym,
            exchange:    exch,
            timeframe:   tf,
            visible_indicators: [],
            user_question: [
              `Analyze Chart ${i + 1} of ${panesResp.panes.length} (${exch}:${sym} · ${tf}) as a technical trading setup.`,
              "MANDATORY: Start with ▶ IDENTITY including Visible, Context, Match, and Type.",
              "Inventory every visible indicator before concluding: EMAs, Supertrend, RSI, volume, levels, and drawn zones.",
              "Use tree-of-thought scenario checks for bull, bear, and range/no-trade cases.",
              "Produce precise support, resistance, invalidation, targets, volume/RSI read, and a final trade plan with confidence.",
            ].join(" "),
            conflict_policy: "prefer_pg",
          });

          setMultiAnalyses((prev) =>
            prev.map((a, idx) =>
              idx === i
                ? {
                    ...a,
                    status:   res.ok && res.data && !res.data.error ? "done" : "error",
                    answer:   res.data?.answer ?? null,
                    error:    res.data?.error ?? (res.ok ? null : (res.error ?? "Analysis failed.")),
                    cost_usd: res.data?.cost_usd ?? 0,
                  }
                : a,
            ),
          );
        } catch (err) {
          const msg = err instanceof Error ? err.message : String(err);
          setMultiAnalyses((prev) =>
            prev.map((a, idx) => (idx === i ? { ...a, status: "error", error: msg } : a)),
          );
        }
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setCaptureError(message);
    } finally {
      setCapturing(false);
      setMultiRunning(false);
    }
  }, [capturing, analysing, multiRunning, symbol, exchange, timeframe]);

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

  const busy = capturing || analysing || multiRunning;

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

      {/* Main tab strip */}
      <div className="main-tabs">
        <button
          className={`main-tab ${mainTab === "analyze" ? "main-tab--active" : ""}`}
          onClick={() => setMainTab("analyze")}
        >🔍 Analyze</button>
        <button
          className={`main-tab ${mainTab === "multi" ? "main-tab--active" : ""}`}
          onClick={() => setMainTab("multi")}
        >🔲 Multi</button>
        <button
          className={`main-tab ${mainTab === "backtest" ? "main-tab--active" : ""}`}
          onClick={() => setMainTab("backtest")}
        >📊 Backtest</button>
        <button
          className={`main-tab ${mainTab === "ric" ? "main-tab--active" : ""}`}
          onClick={() => setMainTab("ric")}
        >🧠 RIC</button>
      </div>

      <main className="main">
        {mainTab === "analyze" && (
          <>
            <section className="capture-area">
              <CaptureButton
                disabled={!apiReachable || busy}
                capturing={capturing}
                analysing={analysing}
                capturedAt={ctx?.captured_at ?? null}
                onCapture={handleCapture}
                onMultiCapture={handleMultiCapture}
                multiRunning={multiRunning}
              />
            </section>

            {captureError && (
              <div className="capture-error" role="alert">
                {captureError}
              </div>
            )}

            {/* Chat panel — locked for follow-up until initial analysis has run */}
            <ChatPanel
              captureId={ctx?.llm_conclusions.length ? ctx.capture_id : null}
              initialAnalysis={ctx?.llm_conclusions[0]}
              symbol={symbol}
              exchange={exchange}
              timeframe={timeframe}
              onSend={handleSend}
            />
          </>
        )}

        {mainTab === "multi" && (
          <>
            {!multiRunning && (
              <section className="capture-area">
                <button
                  className="capture-btn"
                  style={{ width: "100%" }}
                  disabled={!apiReachable || busy}
                  onClick={handleMultiCapture}
                >
                  {multiRunning ? "Analyzing charts…" : "Analyze All Charts"}
                </button>
              </section>
            )}
            {captureError && (
              <div className="capture-error" role="alert">{captureError}</div>
            )}
            <MultiChartPanel analyses={multiAnalyses} isRunning={multiRunning} />
          </>
        )}

        {mainTab === "backtest" && (
          <BacktestTab symbol={symbol} timeframe={timeframe} />
        )}

        {mainTab === "ric" && (
          <RicTab
            symbol={symbol}
            timeframe={timeframe}
            exchange={exchange}
            captureId={ctx?.capture_id ?? null}
          />
        )}
      </main>

      <footer className="footer">Research only — not investment advice</footer>
    </div>
  );
}
