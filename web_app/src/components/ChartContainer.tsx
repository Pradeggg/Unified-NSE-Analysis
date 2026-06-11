import { useState, useEffect, useRef } from "react";
import {
  createChart,
  type IChartApi,
  type ISeriesApi,
  type CandlestickData,
  ColorType,
  CrosshairMode,
  LineStyle,
} from "lightweight-charts";
import type { Bar, KeyLevels } from "../api/client";

import type { BtTrade } from "./BacktestPanel";

type Props = {
  bars: Bar[];
  levels: KeyLevels | null;
  symbol: string;
  timeframe: string;
  markers?: BtTrade[];
  onReady?: (api: { takeScreenshot: () => string | null }) => void;
};

type IndicatorKey = "ema9" | "ema21" | "ema50" | "ema200" | "bb" | "rsi" | "macd";

const C = {
  bg: "#0d1117", text: "#8b949e", grid: "#21262d", border: "#30363d",
  up: "#3fb950", down: "#f85149", cross: "#58a6ff",
  ema9: "#f0883e", ema21: "#d29922", ema50: "#79c0ff", ema200: "#58a6ff",
  bb: "#8b949e", rsi: "#bc8cff", macd: "#58a6ff", signal: "#f0883e",
};

// ── Indicator math ─────────────────────────────────────────────────────────────

function calcEMA(v: number[], n: number): (number | null)[] {
  const k = 2 / (n + 1);
  const out: (number | null)[] = new Array(v.length).fill(null);
  if (v.length < n) return out;
  let ema = v.slice(0, n).reduce((s, x) => s + x, 0) / n;
  out[n - 1] = ema;
  for (let i = n; i < v.length; i++) { ema = v[i] * k + ema * (1 - k); out[i] = ema; }
  return out;
}

function calcBB(closes: number[], n = 20, mult = 2) {
  const upper: (number | null)[] = new Array(closes.length).fill(null);
  const mid:   (number | null)[] = new Array(closes.length).fill(null);
  const lower: (number | null)[] = new Array(closes.length).fill(null);
  for (let i = n - 1; i < closes.length; i++) {
    const sl = closes.slice(i - n + 1, i + 1);
    const mean = sl.reduce((s, v) => s + v, 0) / n;
    const sd = Math.sqrt(sl.reduce((s, v) => s + (v - mean) ** 2, 0) / n);
    mid[i] = mean; upper[i] = mean + mult * sd; lower[i] = mean - mult * sd;
  }
  return { upper, mid, lower };
}

function calcRSI(closes: number[], n = 14): (number | null)[] {
  const out: (number | null)[] = new Array(closes.length).fill(null);
  if (closes.length < n + 1) return out;
  let avgG = 0, avgL = 0;
  for (let i = 1; i <= n; i++) { const d = closes[i] - closes[i-1]; d > 0 ? (avgG += d) : (avgL -= d); }
  avgG /= n; avgL /= n;
  out[n] = 100 - 100 / (1 + avgG / (avgL || 1e-10));
  for (let i = n + 1; i < closes.length; i++) {
    const d = closes[i] - closes[i-1];
    avgG = (avgG * (n-1) + Math.max(0, d)) / n;
    avgL = (avgL * (n-1) + Math.max(0, -d)) / n;
    out[i] = 100 - 100 / (1 + avgG / (avgL || 1e-10));
  }
  return out;
}

function calcMACD(closes: number[], fast = 12, slow = 26, sig = 9) {
  const ef = calcEMA(closes, fast), es = calcEMA(closes, slow);
  const macdLine = closes.map((_, i) => ef[i] != null && es[i] != null ? ef[i]! - es[i]! : null);
  const vals = macdLine.filter(v => v != null) as number[];
  const sigEMA = calcEMA(vals, sig);
  const signalLine: (number | null)[] = new Array(closes.length).fill(null);
  const histogram:  (number | null)[] = new Array(closes.length).fill(null);
  let idx = 0;
  for (let i = 0; i < closes.length; i++) {
    if (macdLine[i] != null) {
      const sv = sigEMA[idx++] ?? null;
      signalLine[i] = sv;
      if (sv != null) histogram[i] = macdLine[i]! - sv;
    }
  }
  return { macd: macdLine, signal: signalLine, histogram };
}

function fmt(n: number) { return n.toLocaleString("en-IN", { maximumFractionDigits: 2 }); }

// ── Toggle button ─────────────────────────────────────────────────────────────

function ToggleBtn({ label, color, active, onClick }: {
  label: string; color: string; active: boolean; onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      style={{
        padding: "2px 7px", fontSize: 10, borderRadius: 4,
        border: `1px solid ${active ? color : "#30363d"}`,
        background: active ? `${color}22` : "transparent",
        color: active ? color : "#8b949e",
        cursor: "pointer",
      }}
    >
      {label}
    </button>
  );
}

// ── ChartContainer ────────────────────────────────────────────────────────────

export function ChartContainer({ bars, levels, symbol, timeframe, markers, onReady }: Props) {
  const [shown, setShown] = useState<Record<IndicatorKey, boolean>>({
    ema9: true, ema21: true, ema50: true, ema200: true,
    bb: false, rsi: true, macd: true,
  });
  const [drawMode, setDrawMode] = useState(false);
  const [userLines, setUserLines] = useState<{ id: string; price: number }[]>([]);

  const toggle = (k: IndicatorKey) => setShown(s => ({ ...s, [k]: !s[k] }));

  type UserLineMeta = { id: string; price: number; pl: ReturnType<ISeriesApi<"Candlestick">["createPriceLine"]> };
  const userLinesRef = useRef<UserLineMeta[]>([]);
  const drawModeRef  = useRef(false);

  const mainRef = useRef<HTMLDivElement>(null);
  const rsiRef  = useRef<HTMLDivElement>(null);
  const macdRef = useRef<HTMLDivElement>(null);
  const legendRef = useRef<HTMLSpanElement>(null);

  const chartRef     = useRef<IChartApi | null>(null);
  const rsiChartRef  = useRef<IChartApi | null>(null);
  const macdChartRef = useRef<IChartApi | null>(null);

  const candlesRef  = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeRef   = useRef<ISeriesApi<"Histogram">   | null>(null);
  const ema9Ref     = useRef<ISeriesApi<"Line"> | null>(null);
  const ema21Ref    = useRef<ISeriesApi<"Line"> | null>(null);
  const ema50Ref    = useRef<ISeriesApi<"Line"> | null>(null);
  const ema200Ref   = useRef<ISeriesApi<"Line"> | null>(null);
  const bbUpRef     = useRef<ISeriesApi<"Line"> | null>(null);
  const bbMidRef    = useRef<ISeriesApi<"Line"> | null>(null);
  const bbLowRef    = useRef<ISeriesApi<"Line"> | null>(null);
  const rsiRef2     = useRef<ISeriesApi<"Line"> | null>(null);
  const macdLineRef = useRef<ISeriesApi<"Line">      | null>(null);
  const macdSigRef  = useRef<ISeriesApi<"Line">      | null>(null);
  const macdHistRef = useRef<ISeriesApi<"Histogram"> | null>(null);

  const priceLinesRef = useRef<ReturnType<ISeriesApi<"Candlestick">["createPriceLine"]>[]>([]);
  const prevSymbolRef = useRef<string>("");
  const syncingRef    = useRef(false);

  // ── Init charts ───────────────────────────────────────────────────────────
  useEffect(() => {
    if (!mainRef.current || !rsiRef.current || !macdRef.current) return;

    const sharedBg = { background: { type: ColorType.Solid, color: C.bg }, textColor: C.text };
    const sharedGrid = { vertLines: { color: C.grid }, horzLines: { color: C.grid } };
    const noTimeScale = { borderColor: C.border, visible: false };

    const chart = createChart(mainRef.current, {
      layout: sharedBg, grid: sharedGrid,
      crosshair: { mode: CrosshairMode.Normal, vertLine: { labelBackgroundColor: C.cross } },
      rightPriceScale: { borderColor: C.border },
      timeScale: { borderColor: C.border, timeVisible: true, secondsVisible: false },
      width: mainRef.current.clientWidth,
      height: mainRef.current.clientHeight,
    });

    const candles = chart.addCandlestickSeries({
      upColor: C.up, downColor: C.down,
      borderUpColor: C.up, borderDownColor: C.down,
      wickUpColor: C.up, wickDownColor: C.down,
      priceLineVisible: true, lastValueVisible: true,
    });
    const volume = chart.addHistogramSeries({
      color: "#58a6ff40", priceFormat: { type: "volume" }, priceScaleId: "volume",
    });
    chart.priceScale("volume").applyOptions({ scaleMargins: { top: 0.85, bottom: 0 } });

    const ema9   = chart.addLineSeries({ color: C.ema9,   lineWidth: 1, priceLineVisible: false, lastValueVisible: false, title: "E9"   });
    const ema21  = chart.addLineSeries({ color: C.ema21,  lineWidth: 1, priceLineVisible: false, lastValueVisible: false, title: "E21"  });
    const ema50  = chart.addLineSeries({ color: C.ema50,  lineWidth: 1, priceLineVisible: false, lastValueVisible: false, title: "E50"  });
    const ema200 = chart.addLineSeries({ color: C.ema200, lineWidth: 1, lineStyle: LineStyle.Dashed, priceLineVisible: false, lastValueVisible: false, title: "E200" });
    const bbUp   = chart.addLineSeries({ color: C.bb, lineWidth: 1, lineStyle: LineStyle.Dotted, priceLineVisible: false, lastValueVisible: false });
    const bbMid  = chart.addLineSeries({ color: C.bb, lineWidth: 1, lineStyle: LineStyle.Dashed, priceLineVisible: false, lastValueVisible: false });
    const bbLow  = chart.addLineSeries({ color: C.bb, lineWidth: 1, lineStyle: LineStyle.Dotted, priceLineVisible: false, lastValueVisible: false });

    // RSI chart
    const rsiChart = createChart(rsiRef.current!, {
      layout: sharedBg, grid: sharedGrid,
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: C.border, scaleMargins: { top: 0.1, bottom: 0.1 } },
      timeScale: noTimeScale,
      width: rsiRef.current!.clientWidth,
      height: rsiRef.current!.clientHeight,
    });
    const rsiSeries = rsiChart.addLineSeries({ color: C.rsi, lineWidth: 1, priceLineVisible: false, lastValueVisible: true });
    rsiSeries.createPriceLine({ price: 70, color: "#f8514980", lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: false, title: "OB" });
    rsiSeries.createPriceLine({ price: 30, color: "#3fb95080", lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: false, title: "OS" });
    rsiSeries.createPriceLine({ price: 50, color: "#8b949e30", lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: false, title: "" });

    // MACD chart
    const macdChart = createChart(macdRef.current!, {
      layout: sharedBg, grid: sharedGrid,
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: C.border, scaleMargins: { top: 0.1, bottom: 0.1 } },
      timeScale: noTimeScale,
      width: macdRef.current!.clientWidth,
      height: macdRef.current!.clientHeight,
    });
    const macdHist = macdChart.addHistogramSeries({ priceLineVisible: false, lastValueVisible: false });
    const macdLine = macdChart.addLineSeries({ color: C.macd,   lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
    const macdSig  = macdChart.addLineSeries({ color: C.signal, lineWidth: 1, priceLineVisible: false, lastValueVisible: false });

    // ── Time scale sync ───────────────────────────────────────────────────────
    const sync = (src: IChartApi, ...targets: IChartApi[]) => {
      src.timeScale().subscribeVisibleLogicalRangeChange((range) => {
        if (syncingRef.current || !range) return;
        syncingRef.current = true;
        targets.forEach(t => t.timeScale().setVisibleLogicalRange(range));
        syncingRef.current = false;
      });
    };
    sync(chart, rsiChart, macdChart);
    sync(rsiChart, chart, macdChart);
    sync(macdChart, chart, rsiChart);

    // ── OHLCV legend ──────────────────────────────────────────────────────────
    chart.subscribeCrosshairMove((param) => {
      if (!legendRef.current) return;
      const d = param.seriesData.get(candles) as CandlestickData | undefined;
      if (d && "open" in d) {
        const bull = d.close >= d.open;
        legendRef.current.innerHTML =
          `<span style="color:#8b949e">O</span><span style="color:${bull?C.up:C.down}"> ${fmt(d.open)} </span>` +
          `<span style="color:#8b949e">H</span><span style="color:${C.up}"> ${fmt(d.high)} </span>` +
          `<span style="color:#8b949e">L</span><span style="color:${C.down}"> ${fmt(d.low)} </span>` +
          `<span style="color:#8b949e">C</span><span style="color:${bull?C.up:C.down}"> ${fmt(d.close)}</span>`;
      } else {
        legendRef.current.innerHTML = "";
      }
    });

    // ── H-Line drawing via chart click ───────────────────────────────────────
    chart.subscribeClick((param) => {
      if (!drawModeRef.current || !param.point || !candlesRef.current) return;
      const price = candlesRef.current.coordinateToPrice(param.point.y);
      if (price == null) return;
      const pl = candlesRef.current.createPriceLine({
        price, color: "#58a6ff", lineWidth: 1,
        lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: "━",
      });
      const id = Math.random().toString(36).slice(2);
      userLinesRef.current.push({ id, price, pl });
      setUserLines(prev => [...prev, { id, price }]);
      drawModeRef.current = false;
      setDrawMode(false);
    });

    // ── Resize ────────────────────────────────────────────────────────────────
    const ro = new ResizeObserver(() => {
      if (mainRef.current) chart.resize(mainRef.current.clientWidth, mainRef.current.clientHeight);
      if (rsiRef.current)  rsiChart.resize(rsiRef.current.clientWidth, rsiRef.current.clientHeight);
      if (macdRef.current) macdChart.resize(macdRef.current.clientWidth, macdRef.current.clientHeight);
    });
    [mainRef, rsiRef, macdRef].forEach(r => r.current && ro.observe(r.current));

    chartRef.current = chart; rsiChartRef.current = rsiChart; macdChartRef.current = macdChart;
    candlesRef.current = candles; volumeRef.current = volume;
    ema9Ref.current = ema9; ema21Ref.current = ema21; ema50Ref.current = ema50; ema200Ref.current = ema200;
    bbUpRef.current = bbUp; bbMidRef.current = bbMid; bbLowRef.current = bbLow;
    rsiRef2.current = rsiSeries;
    macdHistRef.current = macdHist; macdLineRef.current = macdLine; macdSigRef.current = macdSig;
    priceLinesRef.current = [];

    // Expose screenshot API to parent.
    onReady?.({
      takeScreenshot: () => {
        const canvas = chartRef.current?.takeScreenshot();
        return canvas ? canvas.toDataURL("image/png") : null;
      },
    });

    return () => {
      ro.disconnect();
      [chart, rsiChart, macdChart].forEach(c => c.remove());
      chartRef.current = rsiChartRef.current = macdChartRef.current = null;
      candlesRef.current = volumeRef.current = null;
      ema9Ref.current = ema21Ref.current = ema50Ref.current = ema200Ref.current = null;
      bbUpRef.current = bbMidRef.current = bbLowRef.current = null;
      rsiRef2.current = macdHistRef.current = macdLineRef.current = macdSigRef.current = null;
      priceLinesRef.current = [];
    };
  }, []);

  // ── Sync drawMode ref ─────────────────────────────────────────────────────
  useEffect(() => { drawModeRef.current = drawMode; }, [drawMode]);

  function removeUserLine(id: string) {
    const idx = userLinesRef.current.findIndex(l => l.id === id);
    if (idx !== -1) {
      candlesRef.current?.removePriceLine(userLinesRef.current[idx].pl);
      userLinesRef.current.splice(idx, 1);
      setUserLines(prev => prev.filter(l => l.id !== id));
    }
  }

  // ── Toggle indicator visibility ───────────────────────────────────────────
  useEffect(() => {
    ema9Ref.current?.applyOptions({ visible: shown.ema9 });
    ema21Ref.current?.applyOptions({ visible: shown.ema21 });
    ema50Ref.current?.applyOptions({ visible: shown.ema50 });
    ema200Ref.current?.applyOptions({ visible: shown.ema200 });
    [bbUpRef, bbMidRef, bbLowRef].forEach(r => r.current?.applyOptions({ visible: shown.bb }));
    rsiRef2.current?.applyOptions({ visible: shown.rsi });
    [macdHistRef, macdLineRef, macdSigRef].forEach(r => r.current?.applyOptions({ visible: shown.macd }));
  }, [shown]);

  // ── Update data ────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!candlesRef.current || !volumeRef.current || bars.length === 0) return;
    const sorted = [...bars].sort((a, b) => a.time - b.time);
    type T = CandlestickData["time"];
    const toT = (b: Bar) => b.time as unknown as T;
    const toLine = (vals: (number|null)[]) =>
      vals.map((v, i) => v != null ? { time: sorted[i].time as unknown as T, value: v } : null)
          .filter(Boolean) as { time: T; value: number }[];

    candlesRef.current.setData(sorted.map(b => ({ time: toT(b), open: b.open, high: b.high, low: b.low, close: b.close })));
    volumeRef.current.setData(sorted.map(b => ({ time: toT(b), value: b.volume, color: b.close >= b.open ? "#3fb95040" : "#f8514940" })));

    const closes = sorted.map(b => b.close);
    ema9Ref.current?.setData(toLine(calcEMA(closes, 9)));
    ema21Ref.current?.setData(toLine(calcEMA(closes, 21)));
    ema50Ref.current?.setData(toLine(calcEMA(closes, 50)));
    ema200Ref.current?.setData(toLine(calcEMA(closes, 200)));

    const { upper, mid, lower } = calcBB(closes);
    bbUpRef.current?.setData(toLine(upper));
    bbMidRef.current?.setData(toLine(mid));
    bbLowRef.current?.setData(toLine(lower));

    rsiRef2.current?.setData(toLine(calcRSI(closes, 14)));

    const { macd, signal, histogram } = calcMACD(closes);
    macdLineRef.current?.setData(toLine(macd));
    macdSigRef.current?.setData(toLine(signal));
    macdHistRef.current?.setData(
      histogram.map((v, i) => v != null ? { time: sorted[i].time as unknown as T, value: v, color: v >= 0 ? "#3fb95099" : "#f8514999" } : null)
               .filter(Boolean) as { time: T; value: number; color: string }[]
    );

    const key = `${symbol}|${timeframe}`;
    if (prevSymbolRef.current !== key) {
      prevSymbolRef.current = key;
      chartRef.current?.timeScale().fitContent();
    }
  }, [bars, symbol, timeframe]);

  // ── Draw PG key levels ────────────────────────────────────────────────────
  useEffect(() => {
    if (!candlesRef.current || !levels) return;
    for (const pl of priceLinesRef.current) candlesRef.current.removePriceLine(pl);
    priceLinesRef.current = [];

    const defs: Array<{ price: number; color: string; label: string; dash?: boolean }> = [
      levels.support    && { price: levels.support,    color: C.up,      label: "S",   dash: true },
      levels.resistance && { price: levels.resistance, color: C.down,    label: "R",   dash: true },
      levels.vwap       && { price: levels.vwap,       color: "#bc8cff", label: "VWAP" },
      levels.supertrend && {
        price: levels.supertrend,
        color: levels.supertrend_direction === "bullish" ? C.up : C.down,
        label: `ST ${levels.supertrend_direction === "bullish" ? "↑" : "↓"}`,
      },
    ].filter(Boolean) as Array<{ price: number; color: string; label: string; dash?: boolean }>;

    for (const d of defs) {
      priceLinesRef.current.push(candlesRef.current.createPriceLine({
        price: d.price, color: d.color, lineWidth: 1,
        lineStyle: d.dash ? LineStyle.Dashed : LineStyle.Solid,
        axisLabelVisible: true, title: d.label,
      }));
    }
  }, [levels]);

  // Backtest trade markers
  useEffect(() => {
    if (!candlesRef.current) return;
    if (!markers || markers.length === 0) {
      candlesRef.current.setMarkers([]);
      return;
    }
    type M = { time: import("lightweight-charts").Time; position: "aboveBar" | "belowBar"; color: string; shape: "arrowUp" | "arrowDown" | "circle"; text?: string };
    const out: M[] = [];
    for (const t of markers) {
      if (t.entry_time) out.push({
        time: t.entry_time as import("lightweight-charts").Time,
        position: t.direction === "BUY" ? "belowBar" : "aboveBar",
        color: t.direction === "BUY" ? "#3fb950" : "#f85149",
        shape: t.direction === "BUY" ? "arrowUp" : "arrowDown",
        text: t.direction === "BUY" ? "▲" : "▼",
      });
      if (t.exit_time) out.push({
        time: t.exit_time as import("lightweight-charts").Time,
        position: t.direction === "BUY" ? "aboveBar" : "belowBar",
        color: t.pnl >= 0 ? "#3fb950" : "#f85149",
        shape: "circle",
        text: t.exit_reason === "target" ? "T" : t.exit_reason === "stoploss" ? "SL" : "X",
      });
    }
    out.sort((a, b) => (a.time as number) - (b.time as number));
    candlesRef.current.setMarkers(out);
    // Scroll chart to show the first marker
    if (out.length > 0 && chartRef.current) {
      chartRef.current.timeScale().fitContent();
    }
  }, [markers]);

  const PANEL_H = 90;

  return (
    <div style={{ position: "relative", flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>

      {/* ── Indicator toggles ── */}
      <div style={{
        display: "flex", alignItems: "center", gap: 4, padding: "4px 10px",
        borderBottom: "1px solid #30363d", flexShrink: 0, flexWrap: "wrap",
      }}>
        <ToggleBtn label="EMA9"   color={C.ema9}   active={shown.ema9}   onClick={() => toggle("ema9")}   />
        <ToggleBtn label="EMA21"  color={C.ema21}  active={shown.ema21}  onClick={() => toggle("ema21")}  />
        <ToggleBtn label="EMA50"  color={C.ema50}  active={shown.ema50}  onClick={() => toggle("ema50")}  />
        <ToggleBtn label="EMA200" color={C.ema200} active={shown.ema200} onClick={() => toggle("ema200")} />
        <ToggleBtn label="BB"     color={C.bb}     active={shown.bb}     onClick={() => toggle("bb")}     />
        <span style={{ width: 1, height: 14, background: "#30363d", margin: "0 2px" }} />
        <ToggleBtn label="RSI"    color={C.rsi}    active={shown.rsi}    onClick={() => toggle("rsi")}    />
        <ToggleBtn label="MACD"   color={C.macd}   active={shown.macd}   onClick={() => toggle("macd")}   />

        {/* H-Line draw tool */}
        <span style={{ width: 1, height: 14, background: "#30363d", margin: "0 2px" }} />
        <button
          onClick={() => setDrawMode(d => !d)}
          title="Click then click on chart to draw horizontal line"
          style={{
            padding: "2px 7px", fontSize: 10, borderRadius: 4,
            border: `1px solid ${drawMode ? "#f0883e" : "#30363d"}`,
            background: drawMode ? "#f0883e22" : "transparent",
            color: drawMode ? "#f0883e" : "#8b949e",
            cursor: "crosshair",
          }}
        >
          {drawMode ? "✚ click chart…" : "✚ H-Line"}
        </button>

        {/* User-drawn lines list */}
        {userLines.map(l => (
          <span key={l.id} style={{
            display: "inline-flex", alignItems: "center", gap: 3,
            fontSize: 10, padding: "1px 5px",
            border: "1px solid #58a6ff55", borderRadius: 3,
            color: "#58a6ff", background: "#58a6ff11",
          }}>
            {fmt(l.price)}
            <span
              onClick={() => removeUserLine(l.id)}
              style={{ cursor: "pointer", opacity: 0.7, marginLeft: 2 }}
              title="Remove line"
            >×</span>
          </span>
        ))}

        {/* OHLCV legend */}
        <span style={{ marginLeft: "auto", fontSize: 11 }}>
          <span style={{ color: "#8b949e", marginRight: 6, fontSize: 10 }}>{symbol} · {timeframe}</span>
          <span ref={legendRef} />
        </span>
      </div>

      {/* ── Main chart ── */}
      <div ref={mainRef} style={{ flex: 1, minHeight: 0 }} />

      {/* ── RSI panel ── */}
      <div style={{
        height: shown.rsi ? PANEL_H : 0,
        flexShrink: 0,
        borderTop: shown.rsi ? "1px solid #30363d" : "none",
        position: "relative", overflow: "hidden", transition: "height 0.2s",
      }}>
        {shown.rsi && <span style={{ position: "absolute", top: 3, left: 8, zIndex: 10, fontSize: 9, color: C.rsi, pointerEvents: "none", fontWeight: "bold" }}>RSI(14)</span>}
        <div ref={rsiRef} style={{ width: "100%", height: "100%" }} />
      </div>

      {/* ── MACD panel ── */}
      <div style={{
        height: shown.macd ? PANEL_H : 0,
        flexShrink: 0,
        borderTop: shown.macd ? "1px solid #30363d" : "none",
        position: "relative", overflow: "hidden", transition: "height 0.2s",
      }}>
        {shown.macd && <span style={{ position: "absolute", top: 3, left: 8, zIndex: 10, fontSize: 9, color: C.macd, pointerEvents: "none", fontWeight: "bold" }}>MACD(12,26,9)</span>}
        <div ref={macdRef} style={{ width: "100%", height: "100%" }} />
      </div>
    </div>
  );
}
