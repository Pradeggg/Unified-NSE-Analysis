import { useState, useRef, useEffect } from "react";
import { api } from "../api/client";

type Message = { role: "user" | "agent"; text: string; ts: number };

type Props = {
  symbol: string;
  exchange: string;
  timeframe: string;
  onCapture?: () => string | null;
};

export function AgentChatPanel({ symbol, exchange, timeframe, onCapture }: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput]       = useState("");
  const [loading, setLoading]   = useState(false);
  const [captureId, setCaptureId] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    setMessages([]);
    setCaptureId(null);
  }, [symbol, exchange, timeframe]);

  function addAgent(text: string) {
    setMessages(m => [...m, { role: "agent", text, ts: Date.now() }]);
  }

  async function sendMessage(q: string, imageDataUrl?: string | null) {
    if (!q.trim() || loading) return;
    setMessages(m => [...m, { role: "user", text: q, ts: Date.now() }]);
    setInput("");
    setLoading(true);

    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      let result: any;

      if (!captureId) {
        result = await api.analyzeChart({
          user_symbol: symbol,
          exchange,
          timeframe,
          visible_indicators: ["EMA9", "EMA21", "EMA50", "EMA200", "RSI", "MACD"],
          user_question: q,
          conflict_policy: "prefer_pg",
          ...(imageDataUrl ? { image: imageDataUrl } : {}),
        });
        if (result.capture_id) setCaptureId(result.capture_id);
      } else {
        result = await api.followUp(captureId, q);
      }

      const answer = result.answer ?? result.detail ?? result.error ?? "[No response]";
      addAgent(answer);
    } catch (err) {
      addAgent(`Error: ${String(err)}`);
    } finally {
      setLoading(false);
    }
  }

  async function handleAnalyze() {
    const img = onCapture ? onCapture() : null;
    if (!img) {
      addAgent("⚠️ Screenshot failed. Try refreshing the page.");
      return;
    }
    // Reset session for fresh analysis
    setCaptureId(null);
    await sendMessage(
      `Analyze this ${symbol} ${timeframe} chart. Identify: trend bias, key EMAs, support/resistance, RSI state, MACD signal, trade setup and risk.`,
      img
    );
  }

  function handleKey(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter" && !e.shiftKey) sendMessage(input);
  }

  return (
    <div style={{
      display: "flex", flexDirection: "column",
      background: "var(--surface)", border: "1px solid var(--border)",
      borderRadius: 8, height: "100%", overflow: "hidden",
    }}>
      {/* Header */}
      <div style={{
        padding: "6px 10px", borderBottom: "1px solid var(--border)",
        display: "flex", alignItems: "center", justifyContent: "space-between",
        flexShrink: 0,
      }}>
        <span style={{ fontSize: 10, color: "var(--muted)", fontWeight: "bold", letterSpacing: "0.08em" }}>
          AGENT ADDA ·{" "}
          <span style={{ color: captureId ? "var(--bullish)" : "var(--warn)" }}>
            {captureId ? "context active" : "new session"}
          </span>
        </span>

        {/* Capture & Analyze button */}
        <button
          onClick={handleAnalyze}
          disabled={loading}
          style={{
            fontSize: 10, padding: "3px 8px",
            background: loading ? "transparent" : "#1f6feb22",
            border: "1px solid var(--accent)",
            color: "var(--accent)",
            borderRadius: 4,
          }}
        >
          {loading ? "thinking…" : "📸 Analyze Chart"}
        </button>
      </div>

      {/* Messages */}
      <div style={{ flex: 1, overflowY: "auto", padding: 10, display: "flex", flexDirection: "column", gap: 8 }}>
        {messages.length === 0 && (
          <div style={{ color: "var(--muted)", fontSize: 11, textAlign: "center", marginTop: 20, lineHeight: 1.6 }}>
            Click <strong style={{ color: "var(--accent)" }}>📸 Analyze Chart</strong> to get<br />
            AI technical analysis of the visible chart,<br />
            or ask a question below.
          </div>
        )}
        {messages.map(msg => (
          <div key={msg.ts} style={{
            alignSelf: msg.role === "user" ? "flex-end" : "flex-start",
            maxWidth: "92%",
            background: msg.role === "user" ? "var(--accent)" : "#21262d",
            color: "#e6edf3",
            borderRadius: msg.role === "user" ? "12px 12px 4px 12px" : "12px 12px 12px 4px",
            padding: "7px 11px", lineHeight: 1.55,
            whiteSpace: "pre-wrap", wordBreak: "break-word", fontSize: 12,
          }}>
            {msg.text}
          </div>
        ))}
        {loading && (
          <div style={{ alignSelf: "flex-start", color: "var(--muted)", fontStyle: "italic", fontSize: 11 }}>
            Agent thinking…
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div style={{ padding: "6px 8px", borderTop: "1px solid var(--border)", display: "flex", gap: 5, flexShrink: 0 }}>
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKey}
          placeholder={`Ask about ${symbol}…`}
          disabled={loading}
          style={{ flex: 1, fontSize: 11 }}
        />
        <button onClick={() => sendMessage(input)} disabled={loading || !input.trim()} style={{ padding: "4px 8px" }}>
          →
        </button>
      </div>
    </div>
  );
}
