// ResultCard — renders a single LLM analysis result with evidence trail.

import { useState } from "react";
import type { ReactNode } from "react";
import type { AnalysisResult } from "../../types";

interface ResultCardProps {
  result: AnalysisResult;
}

type SectionTone = "identity" | "bullish" | "bearish" | "levels" | "setup" | "risk" | "confidence" | "neutral";

function sectionTone(line: string): SectionTone {
  const upper = line.toUpperCase();
  if (upper.includes("IDENTITY")) return "identity";
  if (upper.includes("BIAS")) {
    if (upper.includes("BULL")) return "bullish";
    if (upper.includes("BEAR")) return "bearish";
    return "neutral";
  }
  if (upper.includes("KEY LEVEL") || upper.includes("SUPPORT") || upper.includes("RESISTANCE")) return "levels";
  if (upper.includes("TRADE") || upper.includes("TARGET") || upper.includes("SETUP")) return "setup";
  if (upper.includes("RISK") || upper.includes("INVALIDATION") || upper.includes("STOP")) return "risk";
  if (upper.includes("CONFIDENCE")) return "confidence";
  return "neutral";
}

function lineTone(line: string): SectionTone {
  const upper = line.toUpperCase();
  if (/\b(BULLISH|LONG|BUY|BREAKOUT|SUPPORT|HOLDS?|ABOVE|RECOVERY)\b/.test(upper)) return "bullish";
  if (/\b(BEARISH|SHORT|SELL|BREAKDOWN|RESISTANCE|BELOW|FAIL|INVALID|STOP|RISK)\b/.test(upper)) return "bearish";
  if (/\b(TARGET|R:R|ENTRY|TRIGGER|SETUP)\b/.test(upper)) return "setup";
  if (/\b(CONFIDENCE|MEDIUM|HIGH|LOW)\b/.test(upper)) return "confidence";
  return "neutral";
}

function normalizeSectionText(line: string): string {
  return line
    .replace(/^#{1,6}\s+/, "")
    .replace(/^▶\s*/, "")
    .trim();
}

function renderInlineMarkdown(text: string): ReactNode[] {
  const parts: ReactNode[] = [];
  const pattern = /(`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*)/g;
  let last = 0;
  let match: RegExpExecArray | null;

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > last) parts.push(text.slice(last, match.index));
    const token = match[0];
    if (token.startsWith("`")) {
      parts.push(<code key={match.index}>{token.slice(1, -1)}</code>);
    } else if (token.startsWith("**")) {
      parts.push(<strong key={match.index}>{token.slice(2, -2)}</strong>);
    } else if (token.startsWith("*")) {
      parts.push(<em key={match.index}>{token.slice(1, -1)}</em>);
    }
    last = match.index + token.length;
  }

  if (last < text.length) parts.push(text.slice(last));
  return parts;
}

export function ResultCard({ result }: ResultCardProps) {
  const [showTrail, setShowTrail] = useState(false);

  const lines = result.answer.split("\n");
  const hasIdentitySection = lines.some((line) => line.trim().toUpperCase().includes("IDENTITY"));
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
          {lines.map((line, i) => {
            const trimmed = line.trim();
            if (line.startsWith("━━━") && line.endsWith("━━━")) {
              return <p key={i} className="result-title">{renderInlineMarkdown(line.replace(/━/g, "").trim())}</p>;
            }
            if (/^#{1,6}\s+/.test(trimmed) || trimmed.startsWith("▶ ")) {
              const tone = sectionTone(trimmed);
              return (
                <p key={i} className={`result-section result-section--${tone}`}>
                  <span className="result-section-marker">▶</span>
                  {renderInlineMarkdown(normalizeSectionText(trimmed))}
                </p>
              );
            }
            if (/^\s*[-*•]\s+/.test(line)) {
              const text = line.replace(/^\s*[-*•]\s+/, "");
              return (
                <p key={i} className={`result-bullet result-line--${lineTone(text)}`}>
                  <span className="result-bullet-dot">•</span>
                  {renderInlineMarkdown(text)}
                </p>
              );
            }
            if (trimmed.startsWith("|")) {
              return <p key={i} className="result-table-line">{renderInlineMarkdown(trimmed)}</p>;
            }
            if (trimmed.startsWith(">")) {
              return <p key={i} className="result-quote">{renderInlineMarkdown(trimmed.replace(/^>\s*/, ""))}</p>;
            }
            if (trimmed.startsWith("⚠")) {
              return <p key={i} className="result-warning">{renderInlineMarkdown(trimmed)}</p>;
            }
            if (trimmed === "") return <div key={i} className="result-spacer" />;
            return <p key={i} className={`result-line result-line--${lineTone(trimmed)}`}>{renderInlineMarkdown(line)}</p>;
          })}
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
