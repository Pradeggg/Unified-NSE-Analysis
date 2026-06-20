// Header component — app identity, API status, and compact chart context (single row).

import { useEffect, useMemo, useState } from "react";
import type { Exchange, SymbolSearchResult, Timeframe } from "../../types";
import { fetchSymbolUniverse, searchSymbols } from "../api/client";

const TIMEFRAMES: Timeframe[] = ["1m","3m","5m","15m","30m","1h","4h","1D","1W","1M"];
const EXCHANGES: Exchange[]   = ["NSE","BSE"];
const DEFAULT_SYMBOLS: SymbolSearchResult[] = [
  { symbol: "BANKNIFTY", name: "Nifty Bank", score: 1 },
  { symbol: "NIFTY", name: "Nifty 50", score: 1 },
  { symbol: "FINNIFTY", name: "Nifty Financial Services", score: 1 },
  { symbol: "MIDCPNIFTY", name: "Nifty Mid Select", score: 1 },
  { symbol: "RELIANCE", name: "Reliance Industries Limited", score: 1 },
  { symbol: "HDFCBANK", name: "HDFC Bank Limited", score: 1 },
  { symbol: "ICICIBANK", name: "ICICI Bank Limited", score: 1 },
  { symbol: "TCS", name: "Tata Consultancy Services Limited", score: 1 },
  { symbol: "INFY", name: "Infosys Limited", score: 1 },
  { symbol: "SBIN", name: "State Bank of India", score: 1 },
  { symbol: "MUTHOOTFIN", name: "Muthoot Finance Limited", score: 1 },
];

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
  const [symbolQuery, setSymbolQuery] = useState("");
  const [symbolOptions, setSymbolOptions] = useState<SymbolSearchResult[]>(DEFAULT_SYMBOLS);
  const [symbolUniverse, setSymbolUniverse] = useState<SymbolSearchResult[]>(DEFAULT_SYMBOLS);
  const [symbolSearchStatus, setSymbolSearchStatus] = useState<"idle" | "loading" | "error">("idle");
  const contextLabel = `${exchange}:${symbol || "UNKNOWN"} · ${timeframe}`;

  useEffect(() => {
    if (!editing || !apiReachable) {
      return;
    }

    let cancelled = false;
    const loadUniverse = async () => {
      const res = await fetchSymbolUniverse();
      if (cancelled) return;
      if (res.ok && res.data?.results?.length) {
        setSymbolUniverse(res.data.results);
        setSymbolOptions(res.data.results);
      }
    };
    loadUniverse();

    return () => {
      cancelled = true;
    };
  }, [apiReachable, editing]);

  useEffect(() => {
    if (!editing) return;

    const query = symbolQuery.trim();
    if (query.length < 2 || !apiReachable) {
      setSymbolOptions(apiReachable ? symbolUniverse : DEFAULT_SYMBOLS);
      setSymbolSearchStatus("idle");
      return;
    }

    let cancelled = false;
    setSymbolSearchStatus("loading");
    const timer = window.setTimeout(async () => {
      const res = await searchSymbols(query, 20);
      if (cancelled) return;
      if (res.ok && res.data?.results?.length) {
        setSymbolOptions(res.data.results);
        setSymbolSearchStatus("idle");
      } else {
        setSymbolOptions(symbolUniverse);
        setSymbolSearchStatus(res.ok ? "idle" : "error");
      }
    }, 250);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [apiReachable, editing, symbolQuery, symbolUniverse]);

  const dropdownOptions = useMemo(() => {
    const bySymbol = new Map<string, SymbolSearchResult>();
    const current = symbol.trim().toUpperCase();
    if (current) bySymbol.set(current, { symbol: current, name: "Current selection", score: 1 });
    for (const option of symbolOptions) {
      const sym = option.symbol.trim().toUpperCase();
      if (sym) bySymbol.set(sym, { ...option, symbol: sym });
    }
    return [...bySymbol.values()];
  }, [symbol, symbolOptions]);

  const searchHint = symbolSearchStatus === "loading"
    ? "Searching..."
    : symbolSearchStatus === "error"
      ? "Symbol search unavailable; showing loaded universe."
      : "";

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
            className="symbol-input symbol-search-input"
            type="text"
            value={symbolQuery}
            placeholder="Search symbol or stock name"
            maxLength={60}
            onChange={(e) => setSymbolQuery(e.target.value)}
            aria-label="Search symbol or stock name"
          />
          <select
            className="select symbol-select"
            value={symbol}
            onChange={(e) => onSymbolChange(e.target.value)}
            aria-label="Symbol"
          >
            {dropdownOptions.map((option) => (
              <option key={option.symbol} value={option.symbol}>
                {option.name ? `${option.symbol} - ${option.name}` : option.symbol}
              </option>
            ))}
          </select>
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
          {searchHint && <span className="symbol-select-hint" role="status">{searchHint}</span>}
        </div>
      )}
    </header>
  );
}
