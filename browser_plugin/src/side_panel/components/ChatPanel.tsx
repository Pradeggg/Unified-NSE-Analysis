// ChatPanel — conversational interface bound to the active chart capture context.

import { useState, useRef, useEffect } from "react";
import type { ChatTurn, AnalysisResult, Exchange, Timeframe } from "../../types";
import { ResultCard } from "./ResultCard";

interface ChatPanelProps {
  /** null = no active capture — follow-up is blocked */
  captureId: string | null;
  /** The initial analysis auto-fired after capture (shown as first assistant turn) */
  initialAnalysis?: string;
  symbol: string;
  exchange: Exchange;
  timeframe: Timeframe;
  onSend: (question: string) => Promise<AnalysisResult | null>;
}

const SUGGESTED: string[] = [
  "Intraday long/short setup",
  "Support, resistance, invalidation",
  "Targets with R:R",
  "Volume and RSI read",
  "Bull case vs bear case",
  "What would make this trade invalid?",
];

export function ChatPanel({
  captureId,
  initialAnalysis,
  symbol,
  exchange,
  timeframe,
  onSend,
}: ChatPanelProps) {
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const initialShown = useRef(false);

  // Show auto-fired initial analysis as the first assistant turn.
  useEffect(() => {
    if (initialAnalysis && !initialShown.current) {
      initialShown.current = true;
      setTurns([{
        id: "t_initial",
        role: "assistant",
        content: initialAnalysis,
        timestamp: new Date().toISOString(),
      }]);
    }
  }, [initialAnalysis]);

  // Reset when capture changes.
  useEffect(() => {
    if (!captureId) {
      setTurns([]);
      initialShown.current = false;
    }
  }, [captureId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns]);

  const locked = captureId == null;

  async function submit(question: string) {
    if (!question.trim() || locked || loading) return;
    const userTurn: ChatTurn = {
      id: `t_${Date.now()}`,
      role: "user",
      content: question,
      timestamp: new Date().toISOString(),
    };
    setTurns((prev) => [...prev, userTurn]);
    setInput("");
    setLoading(true);

    const result = await onSend(question);
    const asstTurn: ChatTurn = {
      id: `t_${Date.now()}_a`,
      role: "assistant",
      content: result?.answer ?? "No response from Agent Adda.",
      timestamp: new Date().toISOString(),
      evidence_trail: result?.evidence_trail,
      cost_usd: result?.cost_usd,
    };
    setTurns((prev) => [...prev, asstTurn]);
    setLoading(false);
  }

  return (
    <section className="chat-panel">
      {locked && (
        <div className="chat-locked">
          <p>Capture a chart first to enable analysis</p>
        </div>
      )}

      <div className="chat-history" aria-live="polite">
        {turns.length === 0 && !locked && (
          <div className="chat-suggestions">
            <p className="panel-note">Ask Agent Adda:</p>
            {SUGGESTED.map((q) => (
              <button
                key={q}
                className="suggestion-chip"
                onClick={() => submit(q)}
                disabled={loading}
              >
                {q}
              </button>
            ))}
          </div>
        )}

        {turns.map((turn) => (
          <div key={turn.id} className={`chat-turn chat-turn--${turn.role}`}>
            {turn.role === "user" ? (
              <p className="chat-user-msg">{turn.content}</p>
            ) : (
              <ResultCard
                result={{
                  capture_id: captureId ?? "",
                  symbol,
                  exchange,
                  timeframe,
                  answer: turn.content,
                  key_levels: {
                    support: null, resistance: null, ema20: null,
                    ema50: null, ema100: null, ema200: null,
                    supertrend: null, supertrend_direction: null, vwap: null,
                  },
                  pattern_findings: [],
                  evidence_trail: turn.evidence_trail ?? {
                    source: "unknown", as_of: "", pg_levels_used: false,
                    screenshot_used: false, pattern_engine_used: false,
                  },
                  model: "",
                  input_tokens: 0,
                  output_tokens: 0,
                  cost_usd: turn.cost_usd ?? 0,
                  error: null,
                }}
              />
            )}
          </div>
        ))}

        {loading && (
          <div className="chat-turn chat-turn--assistant">
            <p className="chat-loading">⏳ Agent Adda is thinking…</p>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <div className="chat-input-row">
        <input
          className="chat-input"
          type="text"
          placeholder={locked ? "Capture a chart first..." : "Ask support, targets, stop, volume, RSI..."}
          value={input}
          disabled={locked || loading}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit(input)}
          aria-label="Chat input"
        />
        <button
          className="chat-send-btn"
          disabled={locked || loading || !input.trim()}
          onClick={() => submit(input)}
          aria-label="Send"
        >
          ↑
        </button>
      </div>
    </section>
  );
}
