/**
 * draw_levels.ts — TradingView chart overlay for Agent Adda RIC signals.
 *
 * Strategy:
 *  1. Find the main chart container element.
 *  2. Read Y-axis price label elements to build a price→pixel mapping.
 *  3. Paint a fixed-position <canvas> over the chart area with horizontal
 *     lines + labels at each signal price.
 *  4. Refresh every 2 s so lines stay aligned after zoom/scroll.
 *  5. Expose drawRicLevels() / clearRicOverlay() for the message handler.
 */

export interface DrawSignal {
  type:  string;
  price: number;
  label: string;
  color: string;
  width: number;
  dash:  boolean;
}

const OVERLAY_ID = "agent-adda-ric-overlay";
let _signals: DrawSignal[]   = [];
let _timer:   ReturnType<typeof setInterval> | null = null;

// ── Public API ────────────────────────────────────────────────────────────────

export function drawRicLevels(signals: DrawSignal[]): void {
  _signals = signals ?? [];
  _render();
  if (_timer) clearInterval(_timer);
  _timer = setInterval(_render, 2000);
}

export function clearRicOverlay(): void {
  document.getElementById(OVERLAY_ID)?.remove();
  if (_timer) { clearInterval(_timer); _timer = null; }
  _signals = [];
}

// ── Internals ─────────────────────────────────────────────────────────────────

/** Locate the TV chart canvas container (try several class patterns). */
function findChartContainer(): HTMLElement | null {
  const CANDIDATES = [
    ".chart-container-border",
    ".chart-gui-wrapper",
    '[class*="chart-container"]',
    '[class*="chartContainer"]',
    ".layout__area--center",
    ".chart-widget",
  ];
  for (const sel of CANDIDATES) {
    const el = document.querySelector<HTMLElement>(sel);
    if (el && el.offsetWidth > 200 && el.offsetHeight > 150) return el;
  }
  // Last resort: parent of the largest canvas
  const canvases = Array.from(document.querySelectorAll<HTMLCanvasElement>("canvas"));
  if (canvases.length) {
    const biggest = canvases.sort((a, b) => (b.width * b.height) - (a.width * a.height))[0];
    if (biggest.parentElement) return biggest.parentElement;
  }
  return null;
}

interface AxisPoint { price: number; screenY: number; }

/**
 * Read price labels from the right Y-axis of TradingView.
 * Returns at least 2 points so we can interpolate, sorted by screenY ascending.
 */
function readAxisPoints(chartRect: DOMRect): AxisPoint[] {
  const points: AxisPoint[] = [];

  // TradingView renders the right-axis price labels in elements whose class
  // names are hashed but consistently contain recognisable fragments.
  const LABEL_SELECTORS = [
    '[class*="priceScale"] [class*="label-text"]',
    '[class*="priceScale"] [class*="labelText"]',
    '[class*="price-scale"] [class*="label"]',
    '[class*="priceAxis"] [class*="label"]',
    '[class*="yAxis"] [class*="label"]',
    '[class*="right-single-wrapper"] [class*="label"]',
    '[class*="axis"] [class*="tickMark"] span',
    '[class*="tickMarkLabel"]',
    // Older TV versions
    ".price-axis .label",
    ".pricescale-label",
  ];

  for (const sel of LABEL_SELECTORS) {
    const els = document.querySelectorAll<HTMLElement>(sel);
    if (els.length < 2) continue;

    for (const el of els) {
      const raw   = el.textContent?.trim().replace(/[,\s]/g, "") ?? "";
      const price = parseFloat(raw);
      if (!isFinite(price) || price < 10) continue;  // skip non-price text

      const rect    = el.getBoundingClientRect();
      const centerY = rect.top + rect.height / 2;

      // Must be within the vertical bounds of the chart area
      if (centerY < chartRect.top - 5 || centerY > chartRect.bottom + 5) continue;

      points.push({ price, screenY: centerY });
    }

    if (points.length >= 2) break;
  }

  // Deduplicate (same price might appear twice at different positions)
  const seen = new Set<number>();
  const deduped = points.filter(p => {
    if (seen.has(p.price)) return false;
    seen.add(p.price);
    return true;
  });

  return deduped.sort((a, b) => a.screenY - b.screenY);
}

/**
 * Build a price→canvas-y mapper from the collected axis points.
 * In standard stock charts: top of screen = high price, bottom = low price.
 * After sorting axis points by screenY ascending:
 *   points[0]   = top of chart   = HIGHEST price
 *   points[last]= bottom of chart= LOWEST  price
 */
function buildMapper(
  axisPoints: AxisPoint[],
  chartRect:  DOMRect,
): ((price: number) => number | null) {
  if (axisPoints.length < 2) return () => null;

  const top = axisPoints[0];                          // smallest screenY → highest price
  const bot = axisPoints[axisPoints.length - 1];      // largest  screenY → lowest  price

  if (top.price === bot.price) return () => null;

  return (price: number): number | null => {
    const ratio    = (top.price - price) / (top.price - bot.price);
    const screenY  = top.screenY + (bot.screenY - top.screenY) * ratio;
    return screenY - chartRect.top;   // canvas-relative y
  };
}

function _render(): void {
  if (!_signals.length) return;

  // Remove stale overlay
  document.getElementById(OVERLAY_ID)?.remove();

  const chartEl = findChartContainer();
  if (!chartEl) return;

  const chartRect = chartEl.getBoundingClientRect();
  if (chartRect.width < 100 || chartRect.height < 100) return;

  const axisPoints = readAxisPoints(chartRect);
  if (axisPoints.length < 2) {
    // Silently skip — TV may not have rendered axis yet
    return;
  }

  const priceToY = buildMapper(axisPoints, chartRect);
  const W = Math.round(chartRect.width);
  const H = Math.round(chartRect.height);

  // Create canvas
  const canvas = document.createElement("canvas");
  canvas.id     = OVERLAY_ID;
  canvas.width  = W;
  canvas.height = H;
  Object.assign(canvas.style, {
    position:      "fixed",
    left:          `${chartRect.left}px`,
    top:           `${chartRect.top}px`,
    width:         `${W}px`,
    height:        `${H}px`,
    pointerEvents: "none",
    zIndex:        "9990",
  });
  document.body.appendChild(canvas);

  const ctx = canvas.getContext("2d")!;

  // Sort so pivot/ema (thin) draw first, trading signals (thick) on top
  const ordered = [..._signals].sort((a, b) => a.width - b.width);

  for (const sig of ordered) {
    const canvasY = priceToY(sig.price);
    if (canvasY === null || canvasY < 4 || canvasY > H - 4) continue;

    const yInt = Math.round(canvasY) + 0.5; // crisp 1-px lines

    ctx.save();
    ctx.strokeStyle  = sig.color;
    ctx.lineWidth    = sig.width;
    ctx.globalAlpha  = sig.width > 1 ? 0.9 : 0.7;
    ctx.setLineDash(sig.dash ? [5, 4] : []);

    // Line (leave ~90px on right for label)
    const lineEndX = W - 92;
    ctx.beginPath();
    ctx.moveTo(0, yInt);
    ctx.lineTo(lineEndX, yInt);
    ctx.stroke();

    // Label pill
    ctx.setLineDash([]);
    const labelText = `${sig.label}  ${sig.price.toLocaleString("en-IN")}`;
    ctx.font        = `${sig.width > 1 ? "bold " : ""}11px monospace`;
    const tw        = ctx.measureText(labelText).width;

    ctx.globalAlpha = 0.85;
    ctx.fillStyle   = "rgba(13,17,23,0.88)";
    ctx.fillRect(lineEndX + 1, yInt - 9, tw + 10, 15);

    ctx.globalAlpha = 1;
    ctx.fillStyle   = sig.color;
    ctx.fillText(labelText, lineEndX + 5, yInt + 3);

    ctx.restore();
  }
}
