// CaptureButton — the central control for screenshot capture.
// CAPTURED-FIRST: no analysis runs until the user clicks this button.



interface CaptureButtonProps {
  disabled: boolean;
  capturing: boolean;
  capturedAt: string | null;
  onCapture: () => void;
}

export function CaptureButton({
  disabled, capturing, capturedAt, onCapture,
}: CaptureButtonProps) {
  const label = capturing ? "Capturing…" : "📷  Capture Chart";
  const sub = capturedAt
    ? `Last capture: ${new Date(capturedAt).toLocaleTimeString("en-IN")}`
    : "No capture yet — analysis requires a capture first";

  return (
    <div className="capture-section">
      <button
        className="capture-btn"
        onClick={onCapture}
        disabled={disabled || capturing}
        aria-label="Capture visible chart for analysis"
      >
        {label}
      </button>
      <p className="capture-hint">{sub}</p>
    </div>
  );
}
