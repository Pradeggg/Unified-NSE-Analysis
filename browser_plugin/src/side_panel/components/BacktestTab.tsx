// BacktestTab — compact backtest + leaderboard panel for the plugin side panel.

import { useState, useEffect } from "react";
import { runBacktest, fetchStrategies, fetchLeaderboard } from "../api/client";
import type { BacktestResult, LeaderRow } from "../../types";

interface BacktestTabProps {
  symbol: string;
  timeframe: string;
}

type View = "run" | "leader";

function fmt1(v: number) { return v.toFixed(1); }
function fmtPct(v: number) { return `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`; }

export function BacktestTab({ symbol, timeframe }: BacktestTabProps) {
  const [view, setView]         = useState<View>("run");
  const [strategies, setStrats] = useState<Array<{ id: string; name: string }>>([]);
  const [strategy, setStrategy] = useState("orb_vwap");
  const [running, setRunning]   = useState(false);
  const [result, setResult]     = useState<BacktestResult | null>(null);
  const [error, setError]       = useState<string | null>(null);

  const [leaderRows, setLeaderRows] = useState<LeaderRow[]>([]);
  const [leaderLoading, setLeaderLoading] = useState(false);
  const [leaderError, setLeaderError] = useState<string | null>(null);

  // Load strategy list once
  useEffect(() => {
    fetchStrategies().then((res) => {
      if (res.ok && res.data) setStrats(res.data.strategies);
    });
  }, []);

  // Load leaderboard when view switches to leader
  useEffect(() => {
    if (view !== "leader") return;
    setLeaderLoading(true);
    setLeaderError(null);
    fetchLeaderboard(symbol, undefined, 15).then((res) => {
      setLeaderLoading(false);
      if (res.ok && res.data) setLeaderRows(res.data.leaderboard);
      else setLeaderError(res.error ?? "Failed to load leaderboard");
    });
  }, [view, symbol]);

  async function handleRun() {
    setRunning(true);
    setError(null);
    setResult(null);
    const res = await runBacktest(symbol, timeframe, strategy);
    setRunning(false);
    if (res.ok && res.data) {
      setResult(res.data);
    } else {
      setError(res.error ?? "Backtest failed");
    }
  }

  const m = result?.metrics;

  return (
    <section className="panel bt-panel">
      {/* Sub-tab bar */}
      <div className="bt-tabs">
        <button
          className={`bt-tab ${view === "run" ? "bt-tab--active" : ""}`}
          onClick={() => setView("run")}
        >▶ Run</button>
        <button
          className={`bt-tab ${view === "leader" ? "bt-tab--active" : ""}`}
          onClick={() => setView("leader")}
        >🏆 Top</button>
      </div>

      {view === "run" && (
        <>
          <div className="bt-controls">
            <select
              className="bt-select"
              value={strategy}
              onChange={(e) => setStrategy(e.target.value)}
            >
              {strategies.length === 0 && (
                <option value="orb_vwap">ORB + VWAP</option>
              )}
              {strategies.map((s) => (
                <option key={s.id} value={s.id}>{s.name}</option>
              ))}
            </select>
            <button
              className="bt-run-btn"
              onClick={handleRun}
              disabled={running}
            >
              {running ? "⏳" : "▶ Run"}
            </button>
          </div>

          <p className="bt-subtitle">
            {symbol} · {timeframe}
          </p>

          {error && <p className="bt-error">{error}</p>}

          {m && (
            <>
              <div className="bt-pills">
                <span className="bt-pill bt-pill--neutral">{m.total_trades} trades</span>
                <span className={`bt-pill ${m.win_rate >= 50 ? "bt-pill--green" : "bt-pill--red"}`}>
                  {fmt1(m.win_rate)}% WR
                </span>
                <span className={`bt-pill ${m.return_pct >= 0 ? "bt-pill--green" : "bt-pill--red"}`}>
                  {fmtPct(m.return_pct)}
                </span>
                <span className="bt-pill bt-pill--neutral">DD {fmt1(m.max_drawdown_pct)}%</span>
              </div>

              {result && result.trades.length > 0 && (
                <div className="bt-trades">
                  <p className="bt-trades-header">Recent trades</p>
                  {result.trades.slice(-5).reverse().map((t, i) => (
                    <div key={i} className={`bt-trade ${t.pnl >= 0 ? "bt-trade--win" : "bt-trade--loss"}`}>
                      <span className="bt-trade-dir">{t.direction === "BUY" ? "▲" : "▼"} {t.direction}</span>
                      <span className="bt-trade-entry">@{t.entry_price.toFixed(0)}</span>
                      <span className={`bt-trade-pnl ${t.pnl >= 0 ? "bt-pnl--green" : "bt-pnl--red"}`}>
                        ₹{t.pnl.toFixed(0)}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </>
      )}

      {view === "leader" && (
        <>
          <p className="bt-subtitle">Top strategies for {symbol}</p>
          {leaderLoading && <p className="panel-empty">Loading…</p>}
          {leaderError && <p className="bt-error">{leaderError}</p>}
          {!leaderLoading && !leaderError && leaderRows.length === 0 && (
            <p className="panel-empty">No leaderboard data for {symbol}. Run backtests first.</p>
          )}
          {leaderRows.length > 0 && (
            <table className="bt-leader-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Strategy</th>
                  <th>TF</th>
                  <th>WR</th>
                  <th>Ret</th>
                  <th>Score</th>
                </tr>
              </thead>
              <tbody>
                {leaderRows.map((r) => (
                  <tr key={`${r.symbol}-${r.timeframe}-${r.strategy_id}`}>
                    <td className="bt-rank">{r.rank}</td>
                    <td className="bt-strat">{r.strategy_name}</td>
                    <td>{r.timeframe}</td>
                    <td className={r.win_rate >= 50 ? "bt-green" : "bt-red"}>
                      {fmt1(r.win_rate)}%
                    </td>
                    <td className={r.return_pct >= 0 ? "bt-green" : "bt-red"}>
                      {fmtPct(r.return_pct)}
                    </td>
                    <td className="bt-score">{r.options_score.toFixed(0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </section>
  );
}
