// Header component — app identity, API status, and compact chart context (single row).

import { useState } from "react";
import type { Exchange, Timeframe } from "../../types";

const TIMEFRAMES: Timeframe[] = ["1m","3m","5m","15m","30m","1h","4h","1D","1W","1M"];
const EXCHANGES: Exchange[]   = ["NSE","BSE"];

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
      {/* Single compact row: brand | context | edit | api dot */}
      <div className="header-row">
        <span className="brand">⚡ Agent Adda</span>
        <span className="header-context">{contextLabel}</span>
        <button
          type="button"
          className="context-edit-btn"
          onClick={() => setEditing((v) => !v)}
          aria-expanded={editing}
          aria-label={editing ? "Close editor" : "Edit chart context"}
        >{editing ? "Done" : "Edit"}</button>
        <span
          className={`api-dot ${apiReachable ? "api-dot--ok" : "api-dot--err"}`}
          title={apiReachable ? "API connected" : "API unreachable — start local server"}
        />
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
            {EXCHANGES.map((ex) => <option key={ex} value={ex}>{ex}</option>)}
          </select>
          <select
            className="select"
            value={timeframe}
            onChange={(e) => onTimeframeChange(e.target.value as Timeframe)}
            aria-label="Timeframe"
          >
            {TIMEFRAMES.map((tf) => <option key={tf} value={tf}>{tf}</option>)}
          </select>
        </div>
      )}
    </header>
  );
}
