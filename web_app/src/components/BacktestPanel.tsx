import { useState, useEffect } from "react";

type Strategy = { id: string; name: string; min_bars: number };

type Metrics = {
  total_trades: number; wins: number; losses: number;
  win_rate: number; total_pnl: number; return_pct: number;
  avg_pnl: number; avg_win: number; avg_loss: number;
  max_drawdown_pct: number; sharpe: number;
};

export type BtTrade = {
  entry_time: number | null; exit_time: number | null;
  direction: "BUY" | "SELL"; entry_price: number; exit_price: number;
  qty: number; pnl: number; exit_reason: string; note: string; rr: number;
};

type BtResult = {
  symbol: string; strategy: string; timeframe: string; bars_used: number;
  metrics: Metrics; trades: BtTrade[];
  equity_curve: { time: number | null; value: number }[];
};

type Props = {
  symbol: string;
  timeframe: string;
  onResult?: (trades: BtTrade[]) => void;
};

const fmtNum = (n: number, dec = 0) =>
  n.toLocaleString("en-IN", { minimumFractionDigits: dec, maximumFractionDigits: dec });

const UP   = "#3fb950";
const DOWN = "#f85149";
const MUTED = "#8b949e";

const MetricPill = ({ label, value, color }: { label: string; value: string; color?: string }) => (
  <div style={{ textAlign: "center", flex: 1, minWidth: 80 }}>
    <div style={{ fontSize: 9, color: MUTED, letterSpacing: "0.06em", marginBottom: 2 }}>{label}</div>
    <div style={{ fontSize: 13, fontWeight: "bold", color: color ?? "#e6edf3" }}>{value}</div>
  </div>
);

type CompareRow = { id: string; name: string; trades: number; win_rate: number; return_pct: number; sharpe: number; max_dd: number; score: number };
type LeaderRow  = { rank: number; symbol: string; timeframe: string; strategy_id: string; strategy_name: string; total_trades: number; win_rate: number; return_pct: number; sharpe: number; options_score: number };

// Options-optimised score
function optScore(m: { win_rate: number; return_pct: number; sharpe: number; max_drawdown_pct: number }, trades: number): number {
  if (trades < 3) return -999;
  return Math.round((m.win_rate * 0.5 + m.sharpe * 25 + m.return_pct * 0.5 - m.max_drawdown_pct * 0.4) * 10) / 10;
}

function exportTradesToCsv(trades: BtTrade[], strategy: string, symbol: string, timeframe: string) {
  const header = "direction,entry_time,entry_price,exit_time,exit_price,qty,pnl,rr,exit_reason,note";
  const rows = trades.map(t => [
    t.direction,
    t.entry_time ? new Date(t.entry_time * 1000).toISOString() : "",
    t.entry_price,
    t.exit_time  ? new Date(t.exit_time  * 1000).toISOString() : "",
    t.exit_price,
    t.qty,
    t.pnl.toFixed(2),
    t.rr.toFixed(2),
    t.exit_reason,
    `"${t.note.replace(/"/g, '""')}"`,
  ].join(","));
  const csv = [header, ...rows].join("\n");
  const blob = new Blob([csv], { type: "text/csv" });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement("a");
  a.href     = url;
  a.download = `${symbol}_${timeframe}_${strategy}_trades.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

export function BacktestPanel({ symbol, timeframe, onResult }: Props) {
  const [strategies,   setStrategies]   = useState<Strategy[]>([]);
  const [stratId,      setStratId]      = useState("orb");
  const [capital,      setCapital]      = useState(100000);
  const [riskPct,      setRiskPct]      = useState(1.0);
  const [maxBars,      setMaxBars]      = useState(20);
  const [loading,      setLoading]      = useState(false);
  const [comparing,    setComparing]    = useState(false);
  const [result,       setResult]       = useState<BtResult | null>(null);
  const [activeView,   setActiveView]   = useState<"run" | "leaderboard">("run");
  const [leaderboard,  setLeaderboard]  = useState<LeaderRow[]>([]);
  const [lbLoading,    setLbLoading]    = useState(false);
  const [error,     setError]     = useState<string | null>(null);
  const [showTrades, setShowTrades] = useState(false);
  const [compareRows, setCompareRows] = useState<CompareRow[]>([]);

  useEffect(() => {
    fetch("/api/backtest/strategies").then(r => r.json())
      .then(d => setStrategies(d.strategies ?? []));
  }, []);

  async function loadLeaderboard() {
    setLbLoading(true);
    try {
      const res = await fetch("/api/backtest/leaderboard?limit=100");
      const data = await res.json();
      setLeaderboard(data.leaderboard ?? []);
    } catch { /* ignore */ }
    finally { setLbLoading(false); }
  }

  useEffect(() => {
    if (activeView === "leaderboard" && leaderboard.length === 0) loadLeaderboard();
  }, [activeView]);

  async function runBacktest() {
    setLoading(true); setError(null); setResult(null);
    try {
      const res = await fetch("/api/backtest/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol, timeframe: timeframe, strategy: stratId,
          initial_capital: capital, risk_per_trade_pct: riskPct, max_holding_bars: maxBars,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? "Backtest failed");
      setResult(data);
      onResult?.(data.trades ?? []);
      // Refresh leaderboard after a new run
      if (activeView === "leaderboard") loadLeaderboard();
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  async function compareAll() {
    if (!strategies.length) return;
    setComparing(true); setCompareRows([]); setError(null);
    const rows: CompareRow[] = [];
    for (const s of strategies) {
      try {
        const res = await fetch("/api/backtest/run", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            symbol, timeframe, strategy: s.id,
            initial_capital: capital, risk_per_trade_pct: riskPct, max_holding_bars: maxBars,
          }),
        });
        if (!res.ok) continue;
        const data = await res.json();
        const m = data.metrics;
        rows.push({
          id: s.id, name: s.name,
          trades: m.total_trades, win_rate: m.win_rate,
          return_pct: m.return_pct, sharpe: m.sharpe,
          max_dd: m.max_drawdown_pct,
          score: optScore(m, m.total_trades),
        });
      } catch { /* skip */ }
    }
    rows.sort((a, b) => b.score - a.score);
    setCompareRows(rows);
    // Auto-load best strategy signals on chart
    if (rows.length > 0 && rows[0].score > 0) {
      const best = rows[0].id;
      setStratId(best);
      // Run it to get trades for chart markers
      try {
        const res2 = await fetch("/api/backtest/run", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ symbol, timeframe, strategy: best,
            initial_capital: capital, risk_per_trade_pct: riskPct, max_holding_bars: maxBars }),
        });
        if (res2.ok) { const d2 = await res2.json(); setResult(d2); onResult?.(d2.trades ?? []); }
      } catch { /* ignore */ }
    }
    setComparing(false);
  }

  const m = result?.metrics;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8, height: "100%", overflowY: "auto", fontSize: 12 }}>

      {/* Sub-tab: Run / Leaderboard */}
      <div style={{ display: "flex", borderBottom: "1px solid #30363d", flexShrink: 0, gap: 0 }}>
        {(["run", "leaderboard"] as const).map(v => (
          <button key={v} onClick={() => setActiveView(v)}
            style={{
              flex: 1, padding: "5px 0", fontSize: 10, fontWeight: "bold", border: "none",
              background: activeView === v ? "#1f6feb22" : "transparent",
              color: activeView === v ? "var(--accent, #58a6ff)" : MUTED,
              borderBottom: activeView === v ? "2px solid var(--accent, #58a6ff)" : "2px solid transparent",
              cursor: "pointer", letterSpacing: "0.07em",
            }}
          >
            {v === "run" ? "▶ RUN" : "🏆 LEADERBOARD"}
          </button>
        ))}
      </div>

      {activeView === "leaderboard" ? (
        <LeaderboardView rows={leaderboard} loading={lbLoading} onRefresh={loadLeaderboard}
          onSelect={async (_sym, _tf, sid) => {
            setStratId(sid);
            setActiveView("run");
            // auto-run the selected strategy so markers appear immediately
            setLoading(true); setError(null); setResult(null);
            try {
              const res = await fetch("/api/backtest/run", {
                method: "POST", headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ symbol, timeframe, strategy: sid,
                  initial_capital: capital, risk_per_trade_pct: riskPct, max_holding_bars: maxBars }),
              });
              const data = await res.json();
              if (res.ok) { setResult(data); onResult?.(data.trades ?? []); }
            } catch { /* ignore */ }
            finally { setLoading(false); }
          }} />
      ) : (
      <>{/* Run config + results */}
      {/* Config */}
      <div style={{ background: "#161b22", border: "1px solid #30363d", borderRadius: 6, padding: "10px 12px", display: "flex", flexDirection: "column", gap: 8 }}>

        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <label style={{ color: MUTED, fontSize: 10, width: 60, flexShrink: 0 }}>Strategy</label>
          <select
            value={stratId} onChange={e => setStratId(e.target.value)}
            style={{ flex: 1, background: "#0d1117", color: "#e6edf3", border: "1px solid #30363d", borderRadius: 4, padding: "3px 6px", fontSize: 11 }}
          >
            {strategies.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </div>

        <div style={{ display: "flex", gap: 8 }}>
          <div style={{ flex: 1 }}>
            <div style={{ color: MUTED, fontSize: 9, marginBottom: 2 }}>CAPITAL (₹)</div>
            <input type="number" value={capital} onChange={e => setCapital(+e.target.value)} min={10000} step={10000}
              style={{ width: "100%", background: "#0d1117", color: "#e6edf3", border: "1px solid #30363d", borderRadius: 4, padding: "3px 6px", fontSize: 11, boxSizing: "border-box" }} />
          </div>
          <div style={{ width: 60 }}>
            <div style={{ color: MUTED, fontSize: 9, marginBottom: 2 }}>RISK %</div>
            <input type="number" value={riskPct} onChange={e => setRiskPct(+e.target.value)} min={0.1} max={10} step={0.1}
              style={{ width: "100%", background: "#0d1117", color: "#e6edf3", border: "1px solid #30363d", borderRadius: 4, padding: "3px 6px", fontSize: 11, boxSizing: "border-box" }} />
          </div>
          <div style={{ width: 55 }}>
            <div style={{ color: MUTED, fontSize: 9, marginBottom: 2 }}>MAX BARS</div>
            <input type="number" value={maxBars} onChange={e => setMaxBars(+e.target.value)} min={1} max={200}
              style={{ width: "100%", background: "#0d1117", color: "#e6edf3", border: "1px solid #30363d", borderRadius: 4, padding: "3px 6px", fontSize: 11, boxSizing: "border-box" }} />
          </div>
        </div>

        <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
          <div style={{ fontSize: 10, color: MUTED }}>
            {symbol} · {timeframe}
          </div>
          <button
            onClick={runBacktest} disabled={loading || comparing}
            style={{
              marginLeft: "auto", padding: "5px 12px", fontSize: 11, fontWeight: "bold",
              background: loading ? "#21262d" : "#1f6feb", color: "#fff",
              border: "none", borderRadius: 5, cursor: loading ? "wait" : "pointer",
            }}
          >
            {loading ? "Running…" : "▶ Run"}
          </button>
          <button
            onClick={compareAll} disabled={loading || comparing}
            title="Run all strategies, rank by options score, plot best on chart"
            style={{
              padding: "5px 10px", fontSize: 11, fontWeight: "bold",
              background: comparing ? "#21262d" : "#2ea043", color: "#fff",
              border: "none", borderRadius: 5, cursor: comparing ? "wait" : "pointer",
            }}
          >
            {comparing ? "Comparing…" : "⚡ Best"}
          </button>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div style={{ padding: "6px 10px", background: "#f851491a", color: DOWN, borderRadius: 4, fontSize: 11 }}>
          {error}
        </div>
      )}

      {/* Compare table */}
      {compareRows.length > 0 && (
        <div style={{ border: "1px solid #30363d", borderRadius: 6, overflow: "hidden" }}>
          <div style={{ padding: "5px 10px", background: "#161b22", fontSize: 10, color: MUTED, display: "flex", justifyContent: "space-between" }}>
            <span>📊 Strategy Comparison ({timeframe})</span>
            <span style={{ color: UP }}>★ = best for options</span>
          </div>
          <div style={{ overflowY: "auto", maxHeight: 200 }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 10 }}>
              <thead>
                <tr style={{ background: "#0d1117", color: MUTED }}>
                  {["Strategy","Tr","WR%","Ret%","Sharpe","Score"].map(h => (
                    <th key={h} style={{ padding: "4px 6px", textAlign: "left", fontWeight: "normal", whiteSpace: "nowrap" }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {compareRows.map((r, i) => (
                  <tr
                    key={r.id}
                    onClick={() => { setStratId(r.id); }}
                    style={{
                      borderTop: "1px solid #21262d", cursor: "pointer",
                      background: r.id === stratId ? "#1f6feb22" : i % 2 === 0 ? "transparent" : "#0d111766",
                    }}
                  >
                    <td style={{ padding: "4px 6px", color: i === 0 ? UP : "#e6edf3" }}>
                      {i === 0 ? "★ " : ""}{r.name.replace(" Breakout","").replace(" Crossover","").replace(" Bounce","")}
                    </td>
                    <td style={{ padding: "4px 6px", color: MUTED }}>{r.trades}</td>
                    <td style={{ padding: "4px 6px", color: r.win_rate >= 50 ? UP : DOWN }}>{r.win_rate}%</td>
                    <td style={{ padding: "4px 6px", color: r.return_pct >= 0 ? UP : DOWN }}>{r.return_pct >= 0 ? "+" : ""}{r.return_pct}%</td>
                    <td style={{ padding: "4px 6px", color: r.sharpe >= 1 ? UP : MUTED }}>{r.sharpe}</td>
                    <td style={{ padding: "4px 6px", color: r.score > 80 ? UP : r.score > 0 ? "#d29922" : DOWN, fontWeight: "bold" }}>{r.score > -999 ? r.score : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Results */}
      {result && m && (
        <>
          {/* Header */}
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontWeight: "bold", color: "#e6edf3", fontSize: 11 }}>{result.strategy}</span>
            <span style={{ color: MUTED, fontSize: 10 }}>{result.bars_used} bars</span>
            <span
              style={{
                marginLeft: "auto", fontSize: 12, fontWeight: "bold",
                color: (result.metrics.total_pnl ?? 0) >= 0 ? UP : DOWN,
              }}
            >
              {(result.metrics.total_pnl ?? 0) >= 0 ? "+" : ""}₹{fmtNum(result.metrics.total_pnl)}
            </span>
          </div>

          {/* Metric pills row 1 */}
          <div style={{ display: "flex", gap: 4, background: "#161b22", border: "1px solid #30363d", borderRadius: 6, padding: "8px 6px" }}>
            <MetricPill label="TRADES" value={String(m.total_trades)} />
            <MetricPill label="WIN RATE" value={`${m.win_rate}%`} color={m.win_rate >= 50 ? UP : DOWN} />
            <MetricPill label="RETURN" value={`${m.return_pct >= 0 ? "+" : ""}${m.return_pct}%`} color={m.return_pct >= 0 ? UP : DOWN} />
            <MetricPill label="SHARPE" value={String(m.sharpe)} color={m.sharpe >= 1 ? UP : m.sharpe >= 0.5 ? "#d29922" : DOWN} />
          </div>

          {/* Metric pills row 2 */}
          <div style={{ display: "flex", gap: 4, background: "#161b22", border: "1px solid #30363d", borderRadius: 6, padding: "8px 6px" }}>
            <MetricPill label="AVG WIN" value={`₹${fmtNum(m.avg_win)}`} color={UP} />
            <MetricPill label="AVG LOSS" value={`₹${fmtNum(m.avg_loss)}`} color={DOWN} />
            <MetricPill label="MAX DD" value={`${m.max_drawdown_pct}%`} color={m.max_drawdown_pct > 10 ? DOWN : MUTED} />
            <MetricPill label="W/L" value={`${m.wins}/${m.losses}`} />
          </div>

          {/* Equity sparkline */}
          {result.equity_curve.length > 1 && (
            <EquitySparkline data={result.equity_curve} initial={capital} />
          )}

          {/* Trade list toggle */}
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <button
              onClick={() => setShowTrades(s => !s)}
              style={{
                background: "transparent", border: "1px solid #30363d", borderRadius: 4,
                color: MUTED, fontSize: 10, padding: "3px 8px", cursor: "pointer", textAlign: "left",
              }}
            >
              {showTrades ? "▲" : "▼"} {result.trades.length} trades
            </button>
            {result.trades.length > 0 && (
              <button
                onClick={() => exportTradesToCsv(result.trades, result.strategy, result.symbol, result.timeframe)}
                style={{
                  background: "transparent", border: "1px solid #30363d", borderRadius: 4,
                  color: MUTED, fontSize: 10, padding: "3px 8px", cursor: "pointer",
                }}
                title="Download trades as CSV"
              >
                ⬇ CSV
              </button>
            )}
          </div>

          {showTrades && (
            <div style={{ overflowY: "auto", maxHeight: 260, border: "1px solid #30363d", borderRadius: 6 }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 10 }}>
                <thead>
                  <tr style={{ background: "#161b22", color: MUTED, position: "sticky", top: 0 }}>
                    {["Dir","Entry","Exit","PnL","Reason"].map(h => (
                      <th key={h} style={{ padding: "5px 6px", textAlign: "left", fontWeight: "normal", letterSpacing: "0.06em" }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {result.trades.map((t, i) => (
                    <tr key={i} style={{ borderTop: "1px solid #21262d", background: i % 2 === 0 ? "transparent" : "#0d111799" }}>
                      <td style={{ padding: "4px 6px", color: t.direction === "BUY" ? UP : DOWN, fontWeight: "bold" }}>{t.direction}</td>
                      <td style={{ padding: "4px 6px", color: "#e6edf3" }}>{t.entry_price.toLocaleString("en-IN")}</td>
                      <td style={{ padding: "4px 6px", color: "#e6edf3" }}>{t.exit_price.toLocaleString("en-IN")}</td>
                      <td style={{ padding: "4px 6px", color: t.pnl >= 0 ? UP : DOWN, fontWeight: "bold" }}>
                        {t.pnl >= 0 ? "+" : ""}₹{fmtNum(t.pnl)}
                      </td>
                      <td style={{ padding: "4px 6px", color: MUTED }}>
                        {t.exit_reason === "target" ? "🎯" : t.exit_reason === "stoploss" ? "🛑" : "⏱"} {t.exit_reason}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
      </> /* end run view */
      )} {/* end activeView ternary */}
    </div>
  );
}

// Mini SVG sparkline for equity curve
function EquitySparkline({ data, initial }: { data: { time: number | null; value: number }[]; initial: number }) {
  const vals = data.map(d => d.value);
  const min  = Math.min(...vals);
  const max  = Math.max(...vals);
  const range = max - min || 1;
  const W = 280, H = 50;
  const pts = vals.map((v, i) => {
    const x = (i / (vals.length - 1)) * W;
    const y = H - ((v - min) / range) * H;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  const lastVal = vals[vals.length - 1];
  const color   = lastVal >= initial ? "#3fb950" : "#f85149";

  return (
    <div style={{ background: "#161b22", border: "1px solid #30363d", borderRadius: 6, padding: "8px 10px" }}>
      <div style={{ fontSize: 9, color: "#8b949e", marginBottom: 4, letterSpacing: "0.06em" }}>EQUITY CURVE</div>
      <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ display: "block" }}>
        <polyline points={pts} fill="none" stroke={color} strokeWidth="1.5" />
      </svg>
    </div>
  );
}


function LeaderboardView({
  rows, loading, onRefresh, onSelect,
}: {
  rows: LeaderRow[];
  loading: boolean;
  onRefresh: () => void;
  onSelect: (sym: string, tf: string, sid: string) => void;
}) {
  const [filterSym, setFilterSym] = useState("");

  const shown = filterSym
    ? rows.filter(r => r.symbol.toLowerCase().includes(filterSym.toLowerCase()))
    : rows;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
        <input
          placeholder="Filter symbol…" value={filterSym} onChange={e => setFilterSym(e.target.value)}
          style={{ flex: 1, background: "#0d1117", color: "#e6edf3", border: "1px solid #30363d", borderRadius: 4, padding: "3px 8px", fontSize: 10 }}
        />
        <button onClick={onRefresh} disabled={loading}
          style={{ padding: "3px 10px", fontSize: 10, background: "#21262d", color: "#e6edf3", border: "1px solid #30363d", borderRadius: 4, cursor: "pointer" }}>
          {loading ? "…" : "↻"}
        </button>
      </div>
      <div style={{ fontSize: 9, color: "#8b949e", letterSpacing: "0.06em" }}>
        {shown.length} strategies · sorted by options score · click to load
      </div>
      <div style={{ overflowY: "auto", maxHeight: 400, border: "1px solid #30363d", borderRadius: 6 }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 10 }}>
          <thead>
            <tr style={{ background: "#161b22", color: "#8b949e", position: "sticky", top: 0 }}>
              {["#","Symbol","TF","Strategy","Tr","WR%","Ret%","Score"].map(h => (
                <th key={h} style={{ padding: "5px 6px", textAlign: "left", fontWeight: "normal", whiteSpace: "nowrap" }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {shown.map((r, i) => (
              <tr key={`${r.symbol}-${r.timeframe}-${r.strategy_id}`}
                onClick={() => onSelect(r.symbol, r.timeframe, r.strategy_id)}
                style={{ borderTop: "1px solid #21262d", cursor: "pointer", background: i % 2 === 0 ? "transparent" : "#0d111766" }}
              >
                <td style={{ padding: "4px 6px", color: "#8b949e" }}>{r.rank}</td>
                <td style={{ padding: "4px 6px", color: "#e6edf3", fontWeight: "bold" }}>{r.symbol}</td>
                <td style={{ padding: "4px 6px", color: "#8b949e" }}>{r.timeframe}</td>
                <td style={{ padding: "4px 6px", color: i < 3 ? "#3fb950" : "#e6edf3" }}>
                  {i === 0 ? "★ " : ""}{r.strategy_name.replace(" Breakout","").replace(" Crossover","").replace(" Bounce","").replace(" Candle","").replace(" Confluence","")}
                </td>
                <td style={{ padding: "4px 6px", color: "#8b949e" }}>{r.total_trades}</td>
                <td style={{ padding: "4px 6px", color: r.win_rate >= 50 ? "#3fb950" : "#f85149" }}>{r.win_rate}%</td>
                <td style={{ padding: "4px 6px", color: r.return_pct >= 0 ? "#3fb950" : "#f85149" }}>
                  {r.return_pct >= 0 ? "+" : ""}{r.return_pct}%
                </td>
                <td style={{ padding: "4px 6px", fontWeight: "bold",
                  color: (r.options_score ?? 0) > 100 ? "#3fb950" : (r.options_score ?? 0) > 0 ? "#d29922" : "#f85149" }}>
                  {r.options_score ?? "—"}
                </td>
              </tr>
            ))}
            {shown.length === 0 && !loading && (
              <tr><td colSpan={8} style={{ padding: 16, textAlign: "center", color: "#8b949e" }}>No data yet. Run a backtest first.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
