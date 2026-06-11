// PatternPanel — shows K13 engine pattern findings for the active capture.


import type { PatternFinding } from "../../types";

interface PatternPanelProps {
  patterns: PatternFinding[];
  symbol: string;
  timeframe: string;
}

function fmt(v: number | null, prefix = "₹"): string {
  if (v == null) return "—";
  return `${prefix}${v.toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
}

function statusBadge(status: PatternFinding["status"]) {
  const map: Record<PatternFinding["status"], { label: string; cls: string }> = {
    confirmed:          { label: "✅ Confirmed", cls: "badge--green" },
    forming:            { label: "🔄 Forming",   cls: "badge--yellow" },
    none:               { label: "—",            cls: "badge--gray" },
    engine_unavailable: { label: "⚠️ Engine N/A", cls: "badge--red" },
  };
  const { label, cls } = map[status] ?? { label: status, cls: "" };
  return <span className={`badge ${cls}`}>{label}</span>;
}

function PatternCard({ p }: { p: PatternFinding }) {
  return (
    <div className="pattern-card">
      <div className="pattern-header">
        <span className="pattern-name">{p.pattern_type.replace(/_/g, " ")}</span>
        {statusBadge(p.status)}
      </div>
      {p.status !== "none" && p.status !== "engine_unavailable" && (
        <table className="levels-table levels-table--compact">
          <tbody>
            {p.neckline      != null && <tr><td>Neckline</td><td>{fmt(p.neckline)}</td></tr>}
            {p.breakout_level != null && <tr><td>Breakout</td><td>{fmt(p.breakout_level)}</td></tr>}
            {p.target        != null && <tr><td>Target</td><td className="level-value--green">{fmt(p.target)}</td></tr>}
            {p.stop          != null && <tr><td>Stop</td><td className="level-value--red">{fmt(p.stop)}</td></tr>}
            {p.win_rate      != null && <tr><td>Win rate</td><td>{(p.win_rate * 100).toFixed(0)}%</td></tr>}
            {p.avg_move_pct  != null && <tr><td>Avg move</td><td>{fmt(p.avg_move_pct, "")}%</td></tr>}
            {p.sample_size   != null && <tr><td>Samples</td><td>{p.sample_size}</td></tr>}
          </tbody>
        </table>
      )}
    </div>
  );
}

export function PatternPanel({ patterns, symbol, timeframe }: PatternPanelProps) {
  const active = patterns.filter((p) => p.status !== "none");

  return (
    <section className="panel">
      <h3 className="panel-title">📐 Pattern Engine <span className="panel-badge">K13</span></h3>
      {active.length === 0 ? (
        <p className="panel-empty">No patterns confirmed for {symbol} {timeframe}</p>
      ) : (
        active.map((p, i) => <PatternCard key={i} p={p} />)
      )}
      <p className="panel-note">Levels from backtested K13/K15 engine — not visual guesses</p>
    </section>
  );
}
