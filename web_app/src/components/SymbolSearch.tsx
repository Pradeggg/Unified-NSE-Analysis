import { useState, useRef, useEffect, useCallback } from "react";
import { api, type SearchResult } from "../api/client";

type Props = {
  value: string;
  onChange: (symbol: string) => void;
};

export function SymbolSearch({ value, onChange }: Props) {
  const [query, setQuery] = useState(value);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => { setQuery(value); }, [value]);

  const search = useCallback(async (q: string) => {
    if (q.length < 1) { setResults([]); return; }
    setLoading(true);
    const res = await api.searchSymbols(q, 8);
    setLoading(false);
    if (res.ok) setResults(res.data.results);
  }, []);

  function handleInput(e: React.ChangeEvent<HTMLInputElement>) {
    const q = e.target.value;
    setQuery(q);
    setOpen(true);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => search(q), 250);
  }

  function handleSelect(symbol: string) {
    setQuery(symbol);
    setOpen(false);
    onChange(symbol);
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter" && query.trim()) {
      handleSelect(query.trim().toUpperCase());
    }
    if (e.key === "Escape") setOpen(false);
  }

  return (
    <div style={{ position: "relative", width: 200 }}>
      <input
        value={query}
        onChange={handleInput}
        onKeyDown={handleKeyDown}
        onFocus={() => results.length && setOpen(true)}
        placeholder="Symbol / name…"
        style={{ width: "100%", fontWeight: "bold", letterSpacing: "0.05em" }}
        spellCheck={false}
        autoCorrect="off"
      />
      {loading && (
        <span style={{ position: "absolute", right: 8, top: 5, color: "var(--muted)", fontSize: 11 }}>
          …
        </span>
      )}
      {open && results.length > 0 && (
        <ul style={{
          position: "absolute", top: "calc(100% + 4px)", left: 0, right: 0,
          background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 6,
          listStyle: "none", zIndex: 100, maxHeight: 240, overflowY: "auto",
        }}>
          {results.map((r) => (
            <li
              key={r.symbol}
              onClick={() => handleSelect(r.symbol)}
              style={{ padding: "6px 10px", cursor: "pointer", borderBottom: "1px solid var(--border)" }}
              onMouseEnter={(e) => (e.currentTarget.style.background = "#21262d")}
              onMouseLeave={(e) => (e.currentTarget.style.background = "")}
            >
              <span style={{ fontWeight: "bold" }}>{r.symbol}</span>
              {r.name && (
                <span style={{ marginLeft: 8, color: "var(--muted)", fontSize: 11 }}>
                  {r.name}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
