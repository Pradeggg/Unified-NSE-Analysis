// CaptureButton — the central control for screenshot capture.
// Before capture: full card with large capture button.
// After capture: collapses to a slim toolbar to maximise space for analysis.

interface CaptureButtonProps {
  disabled: boolean;
  capturing: boolean;
  analysing: boolean;
  capturedAt: string | null;
  onCapture: (mode?: "visible" | "area") => void;
  multiRunning: boolean;
}

export function CaptureButton({
  disabled, capturing, analysing, capturedAt, onCapture, multiRunning,
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
          title="Re-analyze (auto-detects single or multi-chart)"
        >⟳ Analyze</button>
        <button
          className="capture-toolbar-btn"
          onClick={() => onCapture("area")}
          disabled={disabled}
          title="Select a specific chart area"
        >◻ Area</button>
      </div>
    );
  }

  // ── Expanded card — shown before first capture or while busy ─────────────
  const status = capturing
    ? "Capturing visible chart…"
    : analysing
      ? "Reading candles, indicators, and levels…"
      : multiRunning
        ? "Analyzing chart panes…"
        : "Ready to capture — detects single or multiple charts automatically";

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
        aria-label="Capture and analyze chart(s)"
      >
        {capturing ? "Capturing…" : analysing ? "Analyzing…" : multiRunning ? "Analyzing panes…" : "Analyze"}
      </button>

      <button
        className="capture-area-btn"
        onClick={() => onCapture("area")}
        disabled={disabled || busy}
        aria-label="Select chart area for analysis"
      >Select Area</button>
    </div>
  );
}

