// Shared markdown renderer for Agent Adda analysis text.
// Used by ResultCard, MultiChartPanel, and any future analysis display component.

import type { ReactNode } from "react";

type SectionTone =
  | "identity" | "bullish" | "bearish" | "levels"
  | "setup"    | "risk"    | "confidence" | "neutral";

export function sectionTone(line: string): SectionTone {
  const u = line.toUpperCase();
  if (u.includes("IDENTITY"))                         return "identity";
  if (u.includes("BIAS")) {
    if (u.includes("BULL")) return "bullish";
    if (u.includes("BEAR")) return "bearish";
    return "neutral";
  }
  if (u.includes("KEY LEVEL") || u.includes("SUPPORT") || u.includes("RESISTANCE")) return "levels";
  if (u.includes("TRADE") || u.includes("TARGET")  || u.includes("SETUP"))  return "setup";
  if (u.includes("RISK")  || u.includes("INVALID")  || u.includes("STOP"))  return "risk";
  if (u.includes("CONFIDENCE"))                       return "confidence";
  if (u.includes("INDICATOR") || u.includes("TECHNICAL"))                    return "levels";
  return "neutral";
}

export function lineTone(line: string): SectionTone {
  const u = line.toUpperCase();
  if (/\b(BULLISH|LONG|BUY|BREAKOUT|SUPPORT|HOLDS?|ABOVE|RECOVERY|GREEN)\b/.test(u)) return "bullish";
  if (/\b(BEARISH|SHORT|SELL|BREAKDOWN|RESISTANCE|BELOW|FAIL|INVALID|STOP|RISK|RED)\b/.test(u)) return "bearish";
  if (/\b(TARGET|R:R|ENTRY|TRIGGER|SETUP)\b/.test(u)) return "setup";
  if (/\b(CONFIDENCE|MEDIUM|HIGH|LOW)\b/.test(u)) return "confidence";
  return "neutral";
}

/** Render inline markdown: `code`, **bold**, *italic* */
export function renderInline(text: string): ReactNode[] {
  const parts: ReactNode[] = [];
  const pattern = /(`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*)/g;
  let last = 0;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(text)) !== null) {
    if (match.index > last) parts.push(text.slice(last, match.index));
    const token = match[0];
    if (token.startsWith("`"))
      parts.push(<code key={match.index}>{token.slice(1, -1)}</code>);
    else if (token.startsWith("**"))
      parts.push(<strong key={match.index}>{token.slice(2, -2)}</strong>);
    else if (token.startsWith("*"))
      parts.push(<em key={match.index}>{token.slice(1, -1)}</em>);
    last = match.index + token.length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}

function stripSectionPrefix(line: string): string {
  return line.replace(/^#{1,6}\s+/, "").replace(/^▶\s*/, "").trim();
}

/** Render a full analysis text block (newline-separated) into React elements. */
export function renderMarkdown(text: string): ReactNode[] {
  return text.split("\n").map((line, i) => {
    const trimmed = line.trim();

    if (trimmed === "") {
      return <div key={i} className="result-spacer" />;
    }

    // Divider title: ━━━ TITLE ━━━
    if (trimmed.startsWith("━━━") && trimmed.endsWith("━━━")) {
      return (
        <p key={i} className="result-title">
          {trimmed.replace(/━/g, "").trim()}
        </p>
      );
    }

    // Section heading: ▶ HEADING or ## Heading
    if (/^#{1,6}\s+/.test(trimmed) || trimmed.startsWith("▶ ")) {
      const tone = sectionTone(trimmed);
      return (
        <p key={i} className={`result-section result-section--${tone}`}>
          <span className="result-section-marker">▶</span>
          {renderInline(stripSectionPrefix(trimmed))}
        </p>
      );
    }

    // Bullet point
    if (/^\s*[-*•]\s+/.test(line)) {
      const content = line.replace(/^\s*[-*•]\s+/, "");
      return (
        <p key={i} className={`result-bullet result-line--${lineTone(content)}`}>
          <span className="result-bullet-dot">•</span>
          {renderInline(content)}
        </p>
      );
    }

    // Table line
    if (trimmed.startsWith("|")) {
      return (
        <p key={i} className="result-table-line">
          {renderInline(trimmed)}
        </p>
      );
    }

    // Blockquote
    if (trimmed.startsWith(">")) {
      return (
        <p key={i} className="result-quote">
          {renderInline(trimmed.replace(/^>\s*/, ""))}
        </p>
      );
    }

    // Warning
    if (trimmed.startsWith("⚠")) {
      return <p key={i} className="result-warning">{renderInline(trimmed)}</p>;
    }

    // Plain line
    return (
      <p key={i} className={`result-line result-line--${lineTone(trimmed)}`}>
        {renderInline(line)}
      </p>
    );
  });
}
