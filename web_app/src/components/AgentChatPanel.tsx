import { useState, useRef, useEffect } from "react";
import { api } from "../api/client";

type Message = { role: "user" | "agent"; text: string; ts: number };

type Props = {
  symbol: string;
  exchange: string;
  timeframe: string;
};

export function AgentChatPanel({ symbol, exchange, timeframe }: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [captureId, setCaptureId] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Reset on symbol/TF change.
  useEffect(() => {
    setMessages([]);
    setCaptureId(null);
  }, [symbol, exchange, timeframe]);

  async function sendMessage(q: string) {
    if (!q.trim() || loading) return;
    const userMsg: Message = { role: "user", text: q, ts: Date.now() };
    setMessages((m) => [...m, userMsg]);
    setInput("");
    setLoading(true);

    try {
      let result: { answer?: string; capture_id?: string; error?: string };

      if (!captureId) {
        // First message — no screenshot; use text-only analysis.
        result = await api.analyzeChart({
          user_symbol: symbol,
          exchange,
          timeframe,
          visible_indicators: [],
          user_question: q,
          conflict_policy: "prefer_pg",
        });
        if (result.capture_id) setCaptureId(result.capture_id);
      } else {
        result = await api.followUp(captureId, q);
      }

      const answer = result.answer ?? result.error ?? "[No response]";
      setMessages((m) => [...m, { role: "agent", text: answer, ts: Date.now() }]);
    } catch (err) {
      setMessages((m) => [...m, { role: "agent", text: `Error: ${String(err)}`, ts: Date.now() }]);
    } finally {
      setLoading(false);
    }
  }

  function handleKey(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter" && !e.shiftKey) sendMessage(input);
  }

  return (
    <div style={{
      display: "flex", flexDirection: "column",
      background: "var(--surface)",
      border: "1px solid var(--border)", borderRadius: 8,
      height: "100%", overflow: "hidden",
    }}>
      <div style={{ padding: "8px 12px", borderBottom: "1px solid var(--border)", fontSize: 11, color: "var(--muted)", fontWeight: "bold", letterSpacing: "0.08em" }}>
        AGENT ADDA ·{" "}
        <span style={{ color: captureId ? "var(--bullish)" : "var(--warn)" }}>
          {captureId ? "context active" : "new session"}
        </span>
      </div>

      <div style={{ flex: 1, overflowY: "auto", padding: 12, display: "flex", flexDirection: "column", gap: 10 }}>
        {messages.length === 0 && (
          <div style={{ color: "var(--muted)", fontSize: 12, textAlign: "center", marginTop: 20 }}>
            Ask anything about {symbol} {timeframe}
          </div>
        )}
        {messages.map((msg) => (
          <div
            key={msg.ts}
            style={{
              alignSelf: msg.role === "user" ? "flex-end" : "flex-start",
              maxWidth: "90%",
              background: msg.role === "user" ? "var(--accent)" : "#21262d",
              color: "#e6edf3",
              borderRadius: msg.role === "user" ? "12px 12px 4px 12px" : "12px 12px 12px 4px",
              padding: "8px 12px",
              lineHeight: 1.5,
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
            }}
          >
            {msg.text}
          </div>
        ))}
        {loading && (
          <div style={{ alignSelf: "flex-start", color: "var(--muted)", fontStyle: "italic", fontSize: 12 }}>
            Agent thinking…
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <div style={{ padding: "8px 10px", borderTop: "1px solid var(--border)", display: "flex", gap: 6 }}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKey}
          placeholder={`Ask about ${symbol}…`}
          disabled={loading}
          style={{ flex: 1 }}
        />
        <button onClick={() => sendMessage(input)} disabled={loading || !input.trim()}>
          →
        </button>
      </div>
    </div>
  );
}
