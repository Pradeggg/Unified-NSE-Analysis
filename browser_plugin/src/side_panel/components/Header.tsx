// Header component — app identity, API status, and compact chart context.

import { useState } from "react";

import type { Exchange, Timeframe } from "../../types";

const TIMEFRAMES: Timeframe[] = ["1m","3m","5m","15m","30m","1h","4h","1D","1W","1M"];
const EXCHANGES: Exchange[] = ["NSE","BSE"];

interface HeaderProps {
  symbol: string;
  exchange: Exchange;
  timeframe: Timeframe;
  apiReachable: boolean;
  onSymbolChange: (s: string) => void;
  onExchangeChange: (e: Exchange) => void;
  onTimeframeChange: (t: Timeframe) => void;
}

export function Header({
  symbol, exchange, timeframe, apiReachable,
  onSymbolChange, onExchangeChange, onTimeframeChange,
}: HeaderProps) {
  const [editing, setEditing] = useState(false);
  const contextLabel = `${exchange}:${symbol || "UNKNOWN"} · ${timeframe}`;

  return (
    <header className="header">
      <div className="header-top">
        <span className="brand">⚡ Agent Adda</span>
        <div className="header-status">
          <span className="api-status-text">{apiReachable ? "API ready" : "API offline"}</span>
          <span className={`api-dot ${apiReachable ? "api-dot--ok" : "api-dot--err"}`}
                title={apiReachable ? "API connected" : "API unreachable — start local server"} />
        </div>
      </div>

      <div className="chart-context">
        <div className="context-copy">
          <span className="context-label">Chart context</span>
          <span className="context-value">{contextLabel}</span>
        </div>
        <button
          type="button"
          className="context-edit-btn"
          onClick={() => setEditing((value) => !value)}
          aria-expanded={editing}
          aria-label={editing ? "Hide chart context editor" : "Edit chart context"}
        >
          {editing ? "Done" : "Edit"}
        </button>
      </div>

      {editing && (
        <div className="header-controls">
          <input
            className="symbol-input"
            type="text"
            value={symbol}
            placeholder="BANKNIFTY"
            maxLength={20}
            onChange={(e) => onSymbolChange(e.target.value.toUpperCase())}
            aria-label="Symbol"
          />

          <select
            className="select"
            value={exchange}
            onChange={(e) => onExchangeChange(e.target.value as Exchange)}
            aria-label="Exchange"
          >
            {EXCHANGES.map((ex) => (
              <option key={ex} value={ex}>{ex}</option>
            ))}
          </select>

          <select
            className="select"
            value={timeframe}
            onChange={(e) => onTimeframeChange(e.target.value as Timeframe)}
            aria-label="Timeframe"
          >
            {TIMEFRAMES.map((tf) => (
              <option key={tf} value={tf}>{tf}</option>
            ))}
          </select>
        </div>
      )}
    </header>
  );
}
