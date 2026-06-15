// CaptureButton — the central control for screenshot capture.
// CAPTURED-FIRST: no analysis runs until the user clicks this button.



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
  const active = capturing || analysing || multiRunning;
  const status = capturing
    ? "Capturing visible chart"
    : analysing
      ? "Reading candles, indicators, and levels"
      : multiRunning
        ? "Analyzing all charts…"
        : capturedAt
          ? `Captured ${new Date(capturedAt).toLocaleTimeString("en-IN")}`
          : "Ready to capture the visible chart";
  const buttonLabel = capturedAt ? "Recapture Chart" : "Capture Chart";

  return (
    <div className="capture-section">
      <div className={`capture-card ${active ? "capture-card--active" : ""} ${capturedAt ? "capture-card--done" : ""}`}>
        <div className="capture-preview" aria-hidden="true">
          <span className="capture-preview-bar capture-preview-bar--top" />
          <span className="capture-preview-candle capture-preview-candle--one" />
          <span className="capture-preview-candle capture-preview-candle--two" />
          <span className="capture-preview-candle capture-preview-candle--three" />
          <span className="capture-preview-level" />
          {active && <span className="capture-scanline" />}
        </div>
        <div className="capture-copy">
          <span className="capture-title">Screenshot capture</span>
          <span className="capture-status">{status}</span>
        </div>
      </div>
      <button
        className="capture-btn"
        onClick={() => onCapture("visible")}
        disabled={disabled || active}
        aria-label="Capture visible chart for analysis"
      >
        {capturing ? "Capturing..." : analysing ? "Analyzing..." : buttonLabel}
      </button>
      <div style={{ display: "flex", gap: "6px" }}>
        <button
          className="capture-area-btn"
          style={{ flex: 1 }}
          onClick={() => onCapture("area")}
          disabled={disabled || active}
          aria-label="Select chart area for analysis"
        >
          Select Area
        </button>
        <button
          className="capture-area-btn"
          style={{ flex: 1 }}
          onClick={onMultiCapture}
          disabled={disabled || active}
          aria-label="Analyze all visible charts"
          title="Detects and analyzes each chart pane individually"
        >
          {multiRunning ? "Analyzing…" : "All Charts"}
        </button>
      </div>
    </div>
  );
}
