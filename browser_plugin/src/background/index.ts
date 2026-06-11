// Background service worker (Manifest V3).
// Responsibilities:
//   - Open side panel when toolbar icon is clicked
//   - Relay page-metadata messages from content script to side panel
//   - Maintain per-tab capture state

import type {
  PageMetadata,
  CaptureVisibleTabRequest,
  CaptureVisibleTabResponse,
  SelectCaptureAreaRequest,
  SelectCaptureAreaResponse,
} from "../types";

interface StoredPageMetadata {
  tabId: number;
  payload: PageMetadata;
  receivedAt: number;
}

const pageMetadataByTab = new Map<number, StoredPageMetadata>();

chrome.sidePanel
  .setPanelBehavior({ openPanelOnActionClick: true })
  .catch(console.error);

function emptyCaptureResponse(error: string): CaptureVisibleTabResponse {
  return {
    ok: false,
    dataUrl: null,
    tab: null,
    error,
  };
}

async function getActivePageTab(): Promise<chrome.tabs.Tab | null> {
  const [focusedTab] = await chrome.tabs.query({
    active: true,
    lastFocusedWindow: true,
  });
  if (focusedTab?.id != null && !isExtensionTab(focusedTab)) return focusedTab;

  const [currentTab] = await chrome.tabs.query({
    active: true,
    currentWindow: true,
  });
  if (currentTab?.id != null && !isExtensionTab(currentTab)) return currentTab;

  return getLastMetadataTab();
}

function isExtensionTab(tab: chrome.tabs.Tab): boolean {
  return Boolean(tab.url?.startsWith(`chrome-extension://${chrome.runtime.id}/`));
}

async function getLastMetadataTab(): Promise<chrome.tabs.Tab | null> {
  const cached = [...pageMetadataByTab.values()].sort(
    (left, right) => right.receivedAt - left.receivedAt
  );

  for (const item of cached) {
    try {
      const tab = await chrome.tabs.get(item.tabId);
      if (tab?.id != null) return tab;
    } catch {
      pageMetadataByTab.delete(item.tabId);
    }
  }

  return null;
}

function captureVisibleTab(windowId: number): Promise<string> {
  return new Promise((resolve, reject) => {
    chrome.tabs.captureVisibleTab(windowId, { format: "png" }, (url) => {
      const error = chrome.runtime.lastError;
      if (error) {
        reject(new Error(error.message));
        return;
      }
      if (!url) {
        reject(new Error("Chrome returned an empty screenshot."));
        return;
      }
      resolve(url);
    });
  });
}

async function captureActiveChart(): Promise<CaptureVisibleTabResponse> {
  const tab = await getActivePageTab();
  if (!tab?.id || tab.windowId == null) {
    return emptyCaptureResponse("No active chart tab was found.");
  }

  const dataUrl = await captureVisibleTab(tab.windowId);
  return {
    ok: true,
    dataUrl,
    tab: {
      id: tab.id,
      windowId: tab.windowId,
      url: tab.url ?? null,
      title: tab.title ?? null,
    },
    error: null,
  };
}

async function getActivePageMetadata(): Promise<StoredPageMetadata | null> {
  const tab = await getActivePageTab();
  if (tab?.id != null) {
    const activeMetadata = pageMetadataByTab.get(tab.id);
    if (activeMetadata) return activeMetadata;
  }

  const cached = [...pageMetadataByTab.values()].sort(
    (left, right) => right.receivedAt - left.receivedAt
  );
  return cached[0] ?? null;
}

async function selectCaptureArea(): Promise<SelectCaptureAreaResponse> {
  const tab = await getActivePageTab();
  if (!tab?.id) {
    return { ok: false, rect: null, error: "No active chart tab was found." };
  }

  try {
    return await chrome.tabs.sendMessage(tab.id, { type: "SELECT_CAPTURE_AREA" } satisfies SelectCaptureAreaRequest);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    if (message.includes("Receiving end does not exist") || message.includes("Could not establish connection")) {
      const injected = await injectContentScript(tab.id);
      if (!injected.ok) {
        return injected;
      }
      try {
        return await chrome.tabs.sendMessage(tab.id, { type: "SELECT_CAPTURE_AREA" } satisfies SelectCaptureAreaRequest);
      } catch (retryError) {
        const retryMessage = retryError instanceof Error ? retryError.message : String(retryError);
        return { ok: false, rect: null, error: retryMessage };
      }
    }
    return { ok: false, rect: null, error: message };
  }
}

async function injectContentScript(tabId: number): Promise<SelectCaptureAreaResponse> {
  try {
    await chrome.scripting.executeScript({
      target: { tabId },
      files: ["content.js"],
    });
    await new Promise((resolve) => setTimeout(resolve, 100));
    return { ok: true, rect: null, error: null };
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return {
      ok: false,
      rect: null,
      error: `Could not inject selection overlay into this page: ${message}`,
    };
  }
}

// Relay content-script metadata to the side panel and handle side-panel
// capture requests from the background context.
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "PAGE_METADATA" && sender.tab?.id != null) {
    pageMetadataByTab.set(sender.tab.id, {
      tabId: sender.tab.id,
      payload: message.payload,
      receivedAt: Date.now(),
    });

    // Forward to side panel (all contexts in this extension).
    chrome.runtime.sendMessage({ ...message, tabId: sender.tab.id }).catch(() => {
      // Side panel may not be open yet — ignore.
    });
  }

  if ((message as CaptureVisibleTabRequest).type === "CAPTURE_VISIBLE_TAB") {
    captureActiveChart()
      .then(sendResponse)
      .catch((error: Error) => {
        sendResponse(emptyCaptureResponse(error.message));
      });
    return true;
  }

  if (message.type === "GET_ACTIVE_METADATA") {
    getActivePageMetadata()
      .then((metadata) => {
        sendResponse({
          type: "ACTIVE_METADATA",
          payload: metadata?.payload ?? null,
          tabId: metadata?.tabId ?? null,
        });
      })
      .catch(() => {
        sendResponse({ type: "ACTIVE_METADATA", payload: null, tabId: null });
      });
    return true;
  }

  if ((message as SelectCaptureAreaRequest).type === "SELECT_CAPTURE_AREA") {
    selectCaptureArea()
      .then(sendResponse)
      .catch((error: Error) => {
        sendResponse({ ok: false, rect: null, error: error.message } satisfies SelectCaptureAreaResponse);
      });
    return true;
  }

  return false;
});

// When a tab is activated, ask its content script for fresh metadata.
chrome.tabs.onActivated.addListener(({ tabId }) => {
  chrome.tabs.sendMessage(tabId, { type: "REQUEST_METADATA" }).catch(() => {
    // Tab may not have a content script (e.g. chrome:// pages) — ignore.
  });
});

// When a tab's URL changes, re-request metadata.
chrome.tabs.onUpdated.addListener((tabId, changeInfo) => {
  if (changeInfo.status === "complete") {
    chrome.tabs.sendMessage(tabId, { type: "REQUEST_METADATA" }).catch(() => {});
  }
});

export {};
