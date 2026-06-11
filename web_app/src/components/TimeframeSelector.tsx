type Props = {
  current: string;
  onChange: (tf: string) => void;
};

const TIMEFRAMES = [
  { group: "Intraday", tfs: ["1m","3m","5m","15m","30m","1h"] },
  { group: "EOD",      tfs: ["1D","1W","1M"] },
];

export function TimeframeSelector({ current, onChange }: Props) {
  return (
    <div style={{ display: "flex", gap: 2, alignItems: "center" }}>
      {TIMEFRAMES.map(({ tfs }) =>
        tfs.map((tf) => (
          <button
            key={tf}
            onClick={() => onChange(tf)}
            style={{
              padding: "3px 7px",
              fontSize: 11,
              fontWeight: tf === current ? "bold" : "normal",
              background: tf === current ? "var(--accent)" : "var(--surface)",
              color: tf === current ? "#fff" : "var(--text)",
              border: "1px solid var(--border)",
              borderRadius: 4,
            }}
          >
            {tf}
          </button>
        ))
      )}
    </div>
  );
}
