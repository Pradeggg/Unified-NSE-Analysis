import { useEffect, useRef } from "react";
import {
  createChart,
  type IChartApi,
  type ISeriesApi,
  type CandlestickData,
  ColorType,
} from "lightweight-charts";
import type { Bar, KeyLevels } from "../api/client";

type Props = {
  bars: Bar[];
  levels: KeyLevels | null;
  symbol: string;
  timeframe: string;
};

const CHART_COLORS = {
  bg:        "#0d1117",
  text:      "#8b949e",
  grid:      "#21262d",
  upBody:    "#3fb950",
  downBody:  "#f85149",
  upWick:    "#3fb950",
  downWick:  "#f85149",
  crosshair: "#58a6ff",
};

export function ChartContainer({ bars, levels, symbol, timeframe }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef     = useRef<IChartApi | null>(null);
  const candlesRef   = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeRef    = useRef<ISeriesApi<"Histogram"> | null>(null);

  // ── Initialise chart ──────────────────────────────────────────────────────
  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: CHART_COLORS.bg },
        textColor: CHART_COLORS.text,
      },
      grid: {
        vertLines: { color: CHART_COLORS.grid },
        horzLines: { color: CHART_COLORS.grid },
      },
      crosshair: { vertLine: { labelBackgroundColor: CHART_COLORS.crosshair } },
      rightPriceScale: { borderColor: "#30363d" },
      timeScale: {
        borderColor: "#30363d",
        timeVisible: true,
        secondsVisible: false,
      },
      width: containerRef.current.clientWidth,
      height: containerRef.current.clientHeight,
    });

    const candles = chart.addCandlestickSeries({
      upColor:   CHART_COLORS.upBody,
      downColor: CHART_COLORS.downBody,
      borderUpColor:   CHART_COLORS.upBody,
      borderDownColor: CHART_COLORS.downBody,
      wickUpColor:   CHART_COLORS.upWick,
      wickDownColor: CHART_COLORS.downWick,
    });

    const volume = chart.addHistogramSeries({
      color: "#58a6ff40",
      priceFormat: { type: "volume" },
      priceScaleId: "volume",
    });
    chart.priceScale("volume").applyOptions({ scaleMargins: { top: 0.85, bottom: 0 } });

    chartRef.current   = chart;
    candlesRef.current = candles;
    volumeRef.current  = volume;

    const ro = new ResizeObserver(() => {
      if (containerRef.current) {
        chart.resize(containerRef.current.clientWidth, containerRef.current.clientHeight);
      }
    });
    ro.observe(containerRef.current);

    return () => {
      ro.disconnect();
      chart.remove();
      chartRef.current   = null;
      candlesRef.current = null;
      volumeRef.current  = null;
    };
  }, []);

  // ── Update data ────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!candlesRef.current || !volumeRef.current || bars.length === 0) return;
    const sorted = [...bars].sort((a, b) => a.time - b.time);
    const candleData: CandlestickData[] = sorted.map((b) => ({
      time: b.time as unknown as CandlestickData["time"],
      open: b.open, high: b.high, low: b.low, close: b.close,
    }));
    candlesRef.current.setData(candleData);
    volumeRef.current.setData(
      sorted.map((b) => ({
        time: b.time as unknown as CandlestickData["time"],
        value: b.volume,
        color: b.close >= b.open ? "#3fb95040" : "#f8514940",
      }))
    );
    chartRef.current?.timeScale().fitContent();
  }, [bars]);

  // ── Draw PG key levels as horizontal price lines ──────────────────────────
  useEffect(() => {
    if (!candlesRef.current || !levels) return;
    candlesRef.current.setMarkers([]); // clear old

    const lines: Array<{ price: number; color: string; label: string; dash?: boolean }> = [
      levels.ema20    && { price: levels.ema20,    color: "#d29922",  label: "EMA20" },
      levels.ema50    && { price: levels.ema50,    color: "#f0883e",  label: "EMA50" },
      levels.ema200   && { price: levels.ema200,   color: "#58a6ff",  label: "EMA200" },
      levels.vwap     && { price: levels.vwap,     color: "#bc8cff",  label: "VWAP" },
      levels.support  && { price: levels.support,  color: "#3fb950",  label: "S",     dash: true },
      levels.resistance && { price: levels.resistance, color: "#f85149", label: "R",  dash: true },
      levels.supertrend && {
        price: levels.supertrend,
        color: levels.supertrend_direction === "bullish" ? "#3fb950" : "#f85149",
        label: `ST ${levels.supertrend_direction === "bullish" ? "↑" : "↓"}`,
      },
    ].filter(Boolean) as Array<{ price: number; color: string; label: string; dash?: boolean }>;

    for (const l of lines) {
      candlesRef.current.createPriceLine({
        price: l.price,
        color: l.color,
        lineWidth: 1,
        lineStyle: l.dash ? 2 : 0, // 2 = dashed
        axisLabelVisible: true,
        title: l.label,
      });
    }
  }, [levels]);

  return (
    <div style={{ position: "relative", flex: 1 }}>
      {/* Symbol + TF watermark */}
      <div style={{
        position: "absolute", top: 8, left: 12, zIndex: 10,
        pointerEvents: "none",
        fontSize: 14, fontWeight: "bold",
        color: "rgba(230,237,243,0.6)",
      }}>
        {symbol} · {timeframe}
      </div>
      <div ref={containerRef} style={{ width: "100%", height: "100%" }} />
    </div>
  );
}
