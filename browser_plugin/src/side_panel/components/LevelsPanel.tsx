// LevelsPanel — displays PG-sourced key levels for the active capture.


import type { KeyLevels } from "../../types";

interface LevelsPanelProps {
  levels: KeyLevels;
  currentPrice: number | null;
}

function fmt(v: number | null): string {
  if (v == null) return "—";
  return v.toLocaleString("en-IN", { maximumFractionDigits: 2 });
}

function Row({ label, value, highlight }: { label: string; value: string; highlight?: "green"|"red"|"yellow" }) {
  return (
    <tr>
      <td className="level-label">{label}</td>
      <td className={`level-value ${highlight ? `level-value--${highlight}` : ""}`}>{value}</td>
    </tr>
  );
}

export function LevelsPanel({ levels, currentPrice }: LevelsPanelProps) {
  const stDir = levels.supertrend_direction;
  const stHighlight = stDir === "bullish" ? "green" : stDir === "bearish" ? "red" : undefined;

  return (
    <section className="panel">
      <h3 className="panel-title">🔍 Key Levels <span className="panel-badge">PG</span></h3>
      <table className="levels-table">
        <tbody>
          {currentPrice != null && (
            <Row label="Current" value={`₹${fmt(currentPrice)}`} highlight="yellow" />
          )}
          <Row label="Resistance" value={`₹${fmt(levels.resistance)}`} highlight="red" />
          <Row label="Support" value={`₹${fmt(levels.support)}`} highlight="green" />
          <tr><td colSpan={2} className="level-divider">EMAs</td></tr>
          <Row label="EMA 20" value={fmt(levels.ema20)} />
          <Row label="EMA 50" value={fmt(levels.ema50)} />
          <Row label="EMA 100" value={fmt(levels.ema100)} />
          <Row label="EMA 200" value={fmt(levels.ema200)} />
          {levels.supertrend != null && (
            <Row
              label={`Supertrend (${stDir ?? "?"})`}
              value={fmt(levels.supertrend)}
              highlight={stHighlight}
            />
          )}
          {levels.vwap != null && <Row label="VWAP" value={fmt(levels.vwap)} />}
        </tbody>
      </table>
      <p className="panel-note">Source: PostgreSQL structured evidence</p>
    </section>
  );
}
