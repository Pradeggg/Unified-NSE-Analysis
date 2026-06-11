import type { KeyLevels } from "../api/client";

type Props = { levels: KeyLevels | null; loading: boolean };

function Row({ label, value, className }: { label: string; value: number | null | undefined; className?: string }) {
  if (!value) return null;
  return (
    <div style={{ display: "flex", justifyContent: "space-between", padding: "3px 0" }}>
      <span style={{ color: "var(--muted)" }}>{label}</span>
      <span className={className} style={{ fontWeight: "bold" }}>
        {value.toLocaleString("en-IN", { maximumFractionDigits: 2 })}
      </span>
    </div>
  );
}

export function LevelsPanel({ levels, loading }: Props) {
  if (loading) return <div style={{ padding: 8, color: "var(--muted)" }}>Loading levels…</div>;
  if (!levels)  return null;

  return (
    <div style={{
      padding: "10px 12px",
      background: "var(--surface)",
      borderRadius: 8,
      border: "1px solid var(--border)",
      minWidth: 180,
    }}>
      <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 6, fontWeight: "bold", letterSpacing: "0.08em" }}>
        KEY LEVELS
      </div>

      {levels.supertrend != null && (
        <div style={{ display: "flex", justifyContent: "space-between", padding: "3px 0", borderBottom: "1px solid var(--border)", marginBottom: 4 }}>
          <span style={{ color: "var(--muted)" }}>Supertrend</span>
          <span className={levels.supertrend_direction === "bullish" ? "bullish" : "bearish"} style={{ fontWeight: "bold" }}>
            {levels.supertrend.toLocaleString("en-IN", { maximumFractionDigits: 2 })}
            {" "}{levels.supertrend_direction === "bullish" ? "↑" : "↓"}
          </span>
        </div>
      )}

      <Row label="Resistance" value={levels.resistance} className="bearish" />
      <Row label="Support"    value={levels.support}    className="bullish" />
      <Row label="VWAP"       value={levels.vwap} />
      <Row label="EMA 20"     value={levels.ema20} />
      <Row label="EMA 50"     value={levels.ema50} />
      <Row label="EMA 100"    value={levels.ema100} />
      <Row label="EMA 200"    value={levels.ema200} />
    </div>
  );
}
