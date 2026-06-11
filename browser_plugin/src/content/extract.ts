// Content script — read-only page metadata extractor.
// Injected into TradingView, Zerodha Kite, ChartInk, NSE India.
//
// Rules:
//  - Read-only: never mutates the DOM or interacts with the page.
//  - No user data, cookies, or page content is sent — only symbol/timeframe metadata.
//  - Sends metadata on load and when the background requests it.

import type {
  PageMetadata,
  Exchange,
  Timeframe,
  CaptureSelectionRect,
  SelectCaptureAreaResponse,
} from "../types";

// ── TradingView timeframe normalisation ───────────────────────────────────
// TradingView uses raw numbers: "1"=1m, "5"=5m, "60"=1h, "D"=1D etc.
function normalizeTVTimeframe(raw: string): Timeframe | null {
  const MAP: Record<string, Timeframe> = {
    "1":   "1m",  "3":   "3m",  "5":   "5m",  "15":  "15m",
    "30":  "30m", "45":  "30m", "60":  "1h",  "120": "1h",
    "240": "4h",  "D":   "1D",  "1D":  "1D",  "W":   "1W",
    "1W":  "1W",  "M":   "1M",  "1M":  "1M",
    // Already-normalised pass-throughs.
    "1m":  "1m",  "3m":  "3m",  "5m":  "5m",  "15m": "15m",
    "30m": "30m", "1h":  "1h",  "4h":  "4h",
    // Daily aliases
    "day": "1D",  "daily": "1D", "week": "1W", "month": "1M",
  };
  return MAP[raw.trim()] ?? null;
}

// Strip futures/options suffix: "TORNTPHARM1!" → "TORNTPHARM", "NIFTY50!" → "NIFTY50"
function cleanSymbol(raw: string): string {
  return raw.replace(/[!0-9]+$/, "").trim().toUpperCase();
}

// ── TradingView DOM-based extraction ─────────────────────────────────────

function readTVSymbolFromDOM(): string | null {
  // TradingView renders the active symbol in several places — try in priority order.
  const selectors = [
    // Chart header symbol text (various TV versions)
    '[class*="symbolTitle"]',
    '[class*="symbol-title"]',
    '[class*="title-"]>[class*="symbol"]',
    '.chart-header [class*="titleWrapper"] span',
    // Legend title in pane
    '[class*="pane-legend"] [class*="title"]',
    '[class*="legendTitle"]',
    // Data-attributes
    '[data-symbol-short]',
    '[data-name="legend-series-item"] [class*="title"]',
  ];
  for (const sel of selectors) {
    const el = document.querySelector<HTMLElement>(sel);
    const text = el?.getAttribute("data-symbol-short") || el?.textContent?.trim();
    if (text && /^[A-Z0-9&!.]{2,30}$/.test(text.toUpperCase().split(" ")[0])) {
      return cleanSymbol(text.split(" ")[0]);
    }
  }
  return null;
}

function readTVTimeframeFromDOM(): Timeframe | null {
  // Active timeframe button in the toolbar
  const selectors = [
    // Common pattern: active/selected state
    'button[class*="isActive"][class*="interval"]',
    'button[class*="interval"][class*="active"]',
    '[class*="timeframes"] button[class*="active"]',
    '[class*="timeframes"] button[aria-checked="true"]',
    // Fallback: read from the chart legend subtitle
    '[class*="pane-legend"] [class*="description"]',
  ];
  for (const sel of selectors) {
    const el = document.querySelector<HTMLElement>(sel);
    const text = el?.textContent?.trim();
    if (text) {
      const tf = normalizeTVTimeframe(text);
      if (tf) return tf;
    }
  }
  return null;
}

// ── Extractor registry per hostname ──────────────────────────────────────

function extractTradingView(): Partial<PageMetadata> {
  // 1. URL query param: tradingview.com/chart/.../?symbol=NSE:BANKNIFTY
  const params = new URLSearchParams(window.location.search);
  const symParam = params.get("symbol");
  if (symParam) {
    const [exch, sym] = symParam.includes(":") ? symParam.split(":") : ["NSE", symParam];
    return {
      symbol: cleanSymbol(sym ?? ""),
      exchange: (exch as Exchange) ?? "NSE",
      detected_from: "url",
    };
  }

  // 2. Page title — multiple TV formats:
  //   "TORNTPHARM, D — TradingView"
  //   "BANKNIFTY, 5 — TradingView"
  //   "TORRENT PHARM FUTURES · 1D · NSE — TradingView"
  //   "TORNTPHARM · D — TradingView"
  const title = document.title;

  // Pattern A: "SYMBOL, TF" (comma-separated)
  const mA = title.match(/^([A-Z0-9&!.]+),\s*([A-Z0-9]+)/);
  if (mA) {
    const tf = normalizeTVTimeframe(mA[2]);
    return { symbol: cleanSymbol(mA[1]), timeframe: tf ?? undefined, detected_from: "title" };
  }

  // Pattern B: "SYMBOL · TF" or "SYMBOL • TF" (bullet/middot separator)
  const mB = title.match(/^([A-Z0-9&!.\s]{2,25?})\s*[·•]\s*([A-Z0-9]+)/i);
  if (mB) {
    const rawSym = mB[1].trim().split(/\s+/).pop() ?? mB[1].trim();
    const tf = normalizeTVTimeframe(mB[2]);
    if (rawSym.length >= 2) {
      return { symbol: cleanSymbol(rawSym), timeframe: tf ?? undefined, detected_from: "title" };
    }
  }

  // Pattern C: match NSE:SYMBOL or BSE:SYMBOL anywhere in the title
  const mC = title.match(/\b(NSE|BSE):([A-Z0-9&!]{2,20})\b/);
  if (mC) {
    return { exchange: mC[1] as Exchange, symbol: cleanSymbol(mC[2]), detected_from: "title" };
  }

  // 3. DOM — TradingView-specific elements
  const domSym = readTVSymbolFromDOM();
  const domTF  = readTVTimeframeFromDOM();
  if (domSym) {
    return { symbol: domSym, timeframe: domTF ?? undefined, detected_from: "dom" };
  }

  // 4. Generic fallback: data-symbol / data-ticker attributes
  const symbolEl = document.querySelector<HTMLElement>(
    "[data-symbol], [data-ticker], .chart-container [title]"
  );
  if (symbolEl) {
    const raw = symbolEl.getAttribute("data-symbol") || symbolEl.getAttribute("data-ticker") || symbolEl.title;
    if (raw) {
      const [exch, sym] = raw.includes(":") ? raw.split(":") : ["NSE", raw];
      return { symbol: cleanSymbol(sym), exchange: exch as Exchange, detected_from: "dom" };
    }
  }

  return { detected_from: "none" };
}

function extractKite(): Partial<PageMetadata> {
  // kite.zerodha.com/chart/ext/ciq/NSE/BANKNIFTY/...
  const parts = window.location.pathname.split("/");
  const exchIdx = parts.indexOf("NSE") !== -1 ? parts.indexOf("NSE") : parts.indexOf("BSE");
  if (exchIdx !== -1 && parts[exchIdx + 1]) {
    return {
      exchange: parts[exchIdx] as Exchange,
      symbol: cleanSymbol(parts[exchIdx + 1]),
      detected_from: "url",
    };
  }
  return { detected_from: "none" };
}

function extractGeneric(): Partial<PageMetadata> {
  // Generic fallback: try to find NSE/BSE symbol in title
  const match = document.title.match(/\b(NSE|BSE):([A-Z0-9&]{2,20})\b/);
  if (match) {
    return { exchange: match[1] as Exchange, symbol: cleanSymbol(match[2]), detected_from: "title" };
  }
  return { detected_from: "none" };
}

// ── Build full metadata ───────────────────────────────────────────────────

function buildMetadata(): PageMetadata {
  const host = window.location.hostname;
  let partial: Partial<PageMetadata> = { detected_from: "none" };

  if (host.includes("tradingview.com")) partial = extractTradingView();
  else if (host.includes("zerodha.com")) partial = extractKite();
  else partial = extractGeneric();

  return {
    symbol: partial.symbol ?? null,
    exchange: partial.exchange ?? null,
    timeframe: partial.timeframe ?? null,
    page_title: document.title,
    source_url: window.location.href,
    detected_from: partial.detected_from ?? "none",
  };
}

// ── Messaging ─────────────────────────────────────────────────────────────

function sendMetadata() {
  chrome.runtime.sendMessage({
    type: "PAGE_METADATA",
    payload: buildMetadata(),
  }).catch(() => {});
}

// Send on load.
sendMetadata();

// Re-send when requested by the background worker.
chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message.type === "REQUEST_METADATA") {
    sendMetadata();
  }

  if (message.type === "SELECT_CAPTURE_AREA") {
    startAreaSelection()
      .then((rect) => {
        sendResponse({ ok: true, rect, error: null } satisfies SelectCaptureAreaResponse);
      })
      .catch((error: Error) => {
        sendResponse({
          ok: false,
          rect: null,
          error: error.message,
        } satisfies SelectCaptureAreaResponse);
      });
    return true;
  }

  return false;
});

// Re-send on URL change (SPA navigation).
let lastUrl = window.location.href;
let lastTitle = document.title;

const observer = new MutationObserver(() => {
  const urlChanged   = window.location.href !== lastUrl;
  const titleChanged = document.title !== lastTitle;
  if (urlChanged || titleChanged) {
    lastUrl   = window.location.href;
    lastTitle = document.title;
    // Delay slightly to let TradingView finish rendering the new symbol
    setTimeout(sendMetadata, 300);
    setTimeout(sendMetadata, 800); // second pass in case DOM settles later
  }
});

// Watch document.title changes (head > title) AND body for SPA navigation
observer.observe(document.head, { childList: true, subtree: true });
observer.observe(document.body, { childList: true, subtree: false });

// Also poll every 3s during active session to catch missed SPA navigations
setInterval(() => {
  if (window.location.href !== lastUrl || document.title !== lastTitle) {
    lastUrl   = window.location.href;
    lastTitle = document.title;
    sendMetadata();
  }
}, 3_000);

// ── Interactive region selection ─────────────────────────────────────────

function startAreaSelection(): Promise<CaptureSelectionRect> {
  return new Promise((resolve, reject) => {
    const existing = document.getElementById("agent-adda-selection-overlay");
    existing?.remove();

    const overlay = document.createElement("div");
    overlay.id = "agent-adda-selection-overlay";
    overlay.style.position = "fixed";
    overlay.style.inset = "0";
    overlay.style.zIndex = "2147483647";
    overlay.style.cursor = "crosshair";
    overlay.style.background = "rgba(2, 6, 23, 0.32)";
    overlay.style.userSelect = "none";

    const label = document.createElement("div");
    label.textContent = "Drag to select chart area · Esc cancels";
    label.style.position = "fixed";
    label.style.top = "14px";
    label.style.left = "50%";
    label.style.transform = "translateX(-50%)";
    label.style.padding = "8px 12px";
    label.style.border = "1px solid rgba(88, 166, 255, .65)";
    label.style.borderRadius = "6px";
    label.style.background = "rgba(13, 17, 23, .94)";
    label.style.color = "#e6edf3";
    label.style.font = "600 12px ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace";
    label.style.boxShadow = "0 8px 30px rgba(0,0,0,.35)";
    overlay.appendChild(label);

    const box = document.createElement("div");
    box.style.position = "fixed";
    box.style.display = "none";
    box.style.border = "2px solid #58a6ff";
    box.style.background = "rgba(88, 166, 255, .14)";
    box.style.boxShadow = "0 0 0 9999px rgba(0,0,0,.42)";
    box.style.borderRadius = "2px";
    overlay.appendChild(box);

    let startX = 0;
    let startY = 0;
    let dragging = false;

    function cleanup() {
      window.removeEventListener("keydown", onKeyDown, true);
      overlay.remove();
    }

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        cleanup();
        reject(new Error("Area selection cancelled."));
      }
    }

    function draw(clientX: number, clientY: number) {
      const left = Math.min(startX, clientX);
      const top = Math.min(startY, clientY);
      const width = Math.abs(clientX - startX);
      const height = Math.abs(clientY - startY);
      box.style.display = "block";
      box.style.left = `${left}px`;
      box.style.top = `${top}px`;
      box.style.width = `${width}px`;
      box.style.height = `${height}px`;
    }

    overlay.addEventListener("mousedown", (event) => {
      event.preventDefault();
      dragging = true;
      startX = event.clientX;
      startY = event.clientY;
      draw(event.clientX, event.clientY);
    });

    overlay.addEventListener("mousemove", (event) => {
      if (!dragging) return;
      event.preventDefault();
      draw(event.clientX, event.clientY);
    });

    overlay.addEventListener("mouseup", (event) => {
      if (!dragging) return;
      event.preventDefault();
      dragging = false;

      const x = Math.min(startX, event.clientX);
      const y = Math.min(startY, event.clientY);
      const width = Math.abs(event.clientX - startX);
      const height = Math.abs(event.clientY - startY);

      if (width < 24 || height < 24) {
        cleanup();
        reject(new Error("Selected area is too small."));
        return;
      }

      cleanup();
      resolve({
        x,
        y,
        width,
        height,
        viewportWidth: window.innerWidth,
        viewportHeight: window.innerHeight,
      });
    });

    window.addEventListener("keydown", onKeyDown, true);
    document.documentElement.appendChild(overlay);
  });
}
