// Header component — symbol/TF/exchange selector + API status indicator.


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
  return (
    <header className="header">
      <div className="header-top">
        <span className="brand">⚡ Agent Adda</span>
        <span className={`api-dot ${apiReachable ? "api-dot--ok" : "api-dot--err"}`}
              title={apiReachable ? "API connected" : "API unreachable — start local server"} />
      </div>

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
    </header>
  );
}
