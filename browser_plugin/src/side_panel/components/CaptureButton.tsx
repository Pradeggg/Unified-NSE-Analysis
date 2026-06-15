// CaptureButton — the central control for screenshot capture.
// Before capture: full card with large capture button.
// After capture: collapses to a slim toolbar to maximise space for analysis.

interface CaptureButtonProps {
  disabled: boolean;
  capturing: boolean;
  analysing: boolean;
  capturedAt: string | null;
  onCapture: (mode?: "visible" | "area") => void;
  onMultiCapture: () => void;
  multiRunning: boolean;
}

export function CaptureButton({
  disabled, capturing, analysing, capturedAt, onCapture, onMultiCapture, multiRunning,
}: CaptureButtonProps) {
  const busy = capturing || analysing || multiRunning;

  // ── Collapsed toolbar — shown after first capture ─────────────────────────
  if (capturedAt && !busy) {
    return (
      <div className="capture-toolbar">
        <span className="capture-toolbar-time">
          📸 {new Date(capturedAt).toLocaleTimeString("en-IN")}
        </span>
        <button
          className="capture-toolbar-btn"
          onClick={() => onCapture("visible")}
          disabled={disabled}
          title="Recapture full visible chart"
        >⟳ Recapture</button>
        <button
          className="capture-toolbar-btn"
          onClick={() => onCapture("area")}
          disabled={disabled}
          title="Select a specific chart area"
        >◻ Area</button>
        <button
          className="capture-toolbar-btn"
          onClick={onMultiCapture}
          disabled={disabled}
          title="Detect and analyze all chart panes"
        >⊞ All Charts</button>
      </div>
    );
  }

  // ── Expanded card — shown before first capture or while busy ─────────────
  const status = capturing
    ? "Capturing visible chart…"
    : analysing
      ? "Reading candles, indicators, and levels…"
      : multiRunning
        ? "Analyzing all chart panes…"
        : "Ready to capture the visible chart";

  return (
    <div className="capture-section">
      <div className={`capture-card ${busy ? "capture-card--active" : ""}`}>
        <div className="capture-preview" aria-hidden="true">
          <span className="capture-preview-bar capture-preview-bar--top" />
          <span className="capture-preview-candle capture-preview-candle--one" />
          <span className="capture-preview-candle capture-preview-candle--two" />
          <span className="capture-preview-candle capture-preview-candle--three" />
          <span className="capture-preview-level" />
          {busy && <span className="capture-scanline" />}
        </div>
        <div className="capture-copy">
          <span className="capture-title">Screenshot capture</span>
          <span className="capture-status">{status}</span>
        </div>
      </div>

      <button
        className="capture-btn"
        onClick={() => onCapture("visible")}
        disabled={disabled || busy}
        aria-label="Capture visible chart for analysis"
      >
        {capturing ? "Capturing…" : analysing ? "Analyzing…" : "Capture Chart"}
      </button>

      <div style={{ display: "flex", gap: "6px" }}>
        <button
          className="capture-area-btn"
          style={{ flex: 1 }}
          onClick={() => onCapture("area")}
          disabled={disabled || busy}
          aria-label="Select chart area for analysis"
        >Select Area</button>
        <button
          className="capture-area-btn"
          style={{ flex: 1 }}
          onClick={onMultiCapture}
          disabled={disabled || busy}
          title="Detect and analyze all chart panes"
        >{multiRunning ? "Analyzing…" : "All Charts"}</button>
      </div>
    </div>
  );
}

