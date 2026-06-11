// Content script — read-only page metadata extractor.
// Injected into TradingView, Zerodha Kite, ChartInk, NSE India.
//
// Rules:
//  - Read-only: never mutates the DOM or interacts with the page.
//  - No user data, cookies, or page content is sent — only symbol/timeframe metadata.
//  - Sends metadata on load and when the background requests it.

import type { PageMetadata, Exchange, Timeframe } from "../types";

// ── Extractor registry per hostname ──────────────────────────────────────

function extractTradingView(): Partial<PageMetadata> {
  // URL pattern: tradingview.com/chart/XXXXX/?symbol=NSE:BANKNIFTY
  const params = new URLSearchParams(window.location.search);
  const symParam = params.get("symbol");
  if (symParam) {
    const [exch, sym] = symParam.includes(":") ? symParam.split(":") : ["NSE", symParam];
    return {
      symbol: sym ?? null,
      exchange: (exch as Exchange) ?? "NSE",
      detected_from: "url",
    };
  }

  // Fallback: read from page title e.g. "BANKNIFTY, 5 — TradingView"
  const titleMatch = document.title.match(/^([A-Z0-9&]+),?\s*([\d]+[mhDWM]?)/);
  if (titleMatch) {
    return {
      symbol: titleMatch[1],
      timeframe: titleMatch[2] as Timeframe,
      detected_from: "title",
    };
  }

  // Fallback: look for data-symbol or data-ticker attributes (chart header)
  const symbolEl = document.querySelector<HTMLElement>(
    "[data-symbol], [data-ticker], .chart-container [title]"
  );
  if (symbolEl) {
    const raw = symbolEl.getAttribute("data-symbol") || symbolEl.getAttribute("data-ticker") || symbolEl.title;
    if (raw) {
      const [exch, sym] = raw.includes(":") ? raw.split(":") : ["NSE", raw];
      return { symbol: sym, exchange: exch as Exchange, detected_from: "dom" };
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
      symbol: parts[exchIdx + 1],
      detected_from: "url",
    };
  }
  return { detected_from: "none" };
}

function extractGeneric(): Partial<PageMetadata> {
  // Generic fallback: try to find NSE/BSE symbol in title
  const match = document.title.match(/\b(NSE|BSE):([A-Z0-9&]{2,20})\b/);
  if (match) {
    return { exchange: match[1] as Exchange, symbol: match[2], detected_from: "title" };
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
chrome.runtime.onMessage.addListener((message) => {
  if (message.type === "REQUEST_METADATA") {
    sendMetadata();
  }
});

// Re-send on URL change (SPA navigation).
let lastUrl = window.location.href;
const observer = new MutationObserver(() => {
  if (window.location.href !== lastUrl) {
    lastUrl = window.location.href;
    setTimeout(sendMetadata, 500); // allow new page DOM to settle
  }
});
observer.observe(document.body, { childList: true, subtree: false });
