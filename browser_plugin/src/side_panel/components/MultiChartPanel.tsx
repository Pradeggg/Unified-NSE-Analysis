// MultiChartPanel — sequential analysis display for multi-chart TradingView layouts.
// Each detected chart pane gets its own result card; they load one after another.

import { useState } from "react";
import type { MultiChartAnalysis } from "../../types";

interface MultiChartPanelProps {
  analyses: MultiChartAnalysis[];
  isRunning: boolean;
}

function statusIcon(status: MultiChartAnalysis["status"]): string {
  switch (status) {
    case "pending":   return "⏳";
    case "analyzing": return "🔍";
    case "done":      return "✅";
    case "error":     return "❌";
  }
}

function statusLabel(status: MultiChartAnalysis["status"]): string {
  switch (status) {
    case "pending":   return "Waiting…";
    case "analyzing": return "Analyzing…";
    case "done":      return "Done";
    case "error":     return "Error";
  }
}

function paneLabel(analysis: MultiChartAnalysis): string {
  const { pane } = analysis;
  const parts: string[] = [`Chart ${pane.index + 1}`];
  if (pane.symbol) parts.push(`${pane.exchange ?? "NSE"}:${pane.symbol}`);
  if (pane.timeframe) parts.push(pane.timeframe);
  return parts.join(" · ");
}

function renderAnalysisText(text: string) {
  return text.split("\n").map((line, i) => {
    const trimmed = line.trim();
    if (trimmed === "") return <div key={i} style={{ height: "4px" }} />;

    if (line.startsWith("━━━") && line.endsWith("━━━")) {
      return <p key={i} className="result-title">{line.replace(/━/g, "").trim()}</p>;
    }
    if (/^#{1,6}\s+/.test(trimmed) || trimmed.startsWith("▶ ")) {
      return (
        <p key={i} className="result-section result-section--neutral">
          <span className="result-section-marker">▶</span>
          {trimmed.replace(/^#{1,6}\s+/, "").replace(/^▶\s*/, "")}
        </p>
      );
    }
    if (/^\s*[-*•]\s+/.test(line)) {
      return (
        <p key={i} className="result-bullet">
          <span className="result-bullet-dot">•</span>
          {line.replace(/^\s*[-*•]\s+/, "")}
        </p>
      );
    }
    return <p key={i} className="result-line result-line--neutral">{line}</p>;
  });
}

function ChartAnalysisCard({ analysis }: { analysis: MultiChartAnalysis }) {
  const [collapsed, setCollapsed] = useState(false);
  const { status, answer, error, cost_usd } = analysis;
  const isDone = status === "done";
  const isAnalyzing = status === "analyzing";

  return (
    <div className="multi-chart-card" data-status={status}>
      <div
        className="multi-chart-card-header"
        onClick={() => isDone && setCollapsed((v) => !v)}
        style={{ cursor: isDone ? "pointer" : "default" }}
      >
        <span className="multi-chart-card-icon">{statusIcon(status)}</span>
        <span className="multi-chart-card-label">{paneLabel(analysis)}</span>
        <span className="multi-chart-card-status">{statusLabel(status)}</span>
        {isDone && cost_usd > 0 && (
          <span className="multi-chart-card-cost">${cost_usd.toFixed(4)}</span>
        )}
        {isDone && (
          <span className="multi-chart-card-toggle">{collapsed ? "▸" : "▾"}</span>
        )}
      </div>

      {isAnalyzing && (
        <div className="multi-chart-card-scanning">
          <span className="capture-scanline" style={{ position: "relative", display: "block", height: "2px" }} />
          <span style={{ fontSize: "10px", color: "var(--text-dim)", padding: "4px 0 0" }}>
            Reading candles, indicators, and levels…
          </span>
        </div>
      )}

      {status === "error" && error && (
        <p className="multi-chart-card-error">⚠️ {error}</p>
      )}

      {isDone && answer && !collapsed && (
        <div className="multi-chart-card-body result-body">
          {renderAnalysisText(answer)}
        </div>
      )}
    </div>
  );
}

export function MultiChartPanel({ analyses, isRunning }: MultiChartPanelProps) {
  if (analyses.length === 0) {
    return (
      <div className="multi-chart-empty">
        <p>Click <strong>Analyze All Charts</strong> to detect and analyze all charts visible on the page.</p>
        <p style={{ marginTop: "8px", color: "var(--text-dim)" }}>
          Works best with TradingView multi-layout (2×2, 3×1, etc.).
        </p>
      </div>
    );
  }

  const done  = analyses.filter((a) => a.status === "done").length;
  const total = analyses.length;

  return (
    <div className="multi-chart-panel">
      <div className="multi-chart-header">
        <span className="multi-chart-title">📊 Multi-Chart Analysis</span>
        <span className="multi-chart-progress">
          {isRunning ? `${done} / ${total} charts` : `${total} chart${total !== 1 ? "s" : ""}`}
        </span>
      </div>
      <div className="multi-chart-list">
        {analyses.map((a) => (
          <ChartAnalysisCard key={a.pane.index} analysis={a} />
        ))}
      </div>
    </div>
  );
}
