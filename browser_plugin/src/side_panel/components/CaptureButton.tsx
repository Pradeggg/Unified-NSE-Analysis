// CaptureButton — the central control for screenshot capture.
// CAPTURED-FIRST: no analysis runs until the user clicks this button.



interface CaptureButtonProps {
  disabled: boolean;
  capturing: boolean;
  analysing: boolean;
  capturedAt: string | null;
  onCapture: (mode?: "visible" | "area") => void;
}

export function CaptureButton({
  disabled, capturing, analysing, capturedAt, onCapture,
}: CaptureButtonProps) {
  const active = capturing || analysing;
  const status = capturing
    ? "Capturing visible chart"
    : analysing
      ? "Reading candles, indicators, and levels"
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
      <button
        className="capture-area-btn"
        onClick={() => onCapture("area")}
        disabled={disabled || active}
        aria-label="Select chart area for analysis"
      >
        Select Area
      </button>
    </div>
  );
}
