// ResultCard — renders a single LLM analysis result with evidence trail.

import { useState } from "react";
import type { AnalysisResult } from "../../types";
import { renderMarkdown } from "../utils/renderMarkdown";

interface ResultCardProps {
  result: AnalysisResult;
}

export function ResultCard({ result }: ResultCardProps) {
  const [showTrail, setShowTrail] = useState(false);

  const lines = result.answer.split("\n");
  const hasIdentitySection = lines.some((l) => l.trim().toUpperCase().includes("IDENTITY"));
  const costStr = result.cost_usd > 0
    ? `$${result.cost_usd.toFixed(4)} · ${result.input_tokens}+${result.output_tokens} tok`
    : "";

  return (
    <div className={`result-card ${result.error ? "result-card--error" : ""}`}>
      {result.error ? (
        <p className="result-error">⚠️ {result.error}</p>
      ) : (
        <div className="result-body">
          {!hasIdentitySection && (
            <div className="result-context-warning">
              <strong>Chart context:</strong> {result.exchange}:{result.symbol} · {result.timeframe}
              <span> Model omitted identity section; using provided context.</span>
            </div>
          )}
          {renderMarkdown(result.answer)}
        </div>
      )}

      <div className="result-footer">
        {costStr && <span className="result-cost">{costStr}</span>}
        <button
          className="trail-toggle"
          onClick={() => setShowTrail((v) => !v)}
          aria-expanded={showTrail}
        >
          {showTrail ? "Hide" : "Source trail"}
        </button>
      </div>

      {showTrail && (
        <div className="trail">
          <p>Model: {result.model}</p>
          <p>PG levels used: {result.evidence_trail.pg_levels_used ? "✅" : "❌"}</p>
          <p>Screenshot used: {result.evidence_trail.screenshot_used ? "✅" : "❌"}</p>
          <p>Pattern engine: {result.evidence_trail.pattern_engine_used ? "✅" : "❌"}</p>
          <p>Source: {result.evidence_trail.source}</p>
          <p>As of: {result.evidence_trail.as_of}</p>
        </div>
      )}
    </div>
  );
}
