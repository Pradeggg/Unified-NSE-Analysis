// Background service worker (Manifest V3).
// Responsibilities:
//   - Open side panel when toolbar icon is clicked
//   - Relay page-metadata messages from content script to side panel
//   - Maintain per-tab capture state

chrome.sidePanel
  .setPanelBehavior({ openPanelOnActionClick: true })
  .catch(console.error);

// Relay content-script metadata to the side panel.
chrome.runtime.onMessage.addListener((message, sender, _sendResponse) => {
  if (message.type === "PAGE_METADATA" && sender.tab?.id != null) {
    // Forward to side panel (all contexts in this extension).
    chrome.runtime.sendMessage({ ...message, tabId: sender.tab.id }).catch(() => {
      // Side panel may not be open yet — ignore.
    });
  }
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
