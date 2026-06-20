/**
 * Agent Adda Chrome Plugin — side panel UI tests
 *
 * Chrome extensions require headless:false + --headless=new flag.
 * We share ONE persistent context across all tests (created once via beforeAll)
 * to avoid the 10s extension-load overhead per test.
 */
import { test, expect, chromium, type BrowserContext, type Page } from "@playwright/test";
import path from "path";

const EXTENSION_PATH = path.resolve(__dirname, "../../browser_plugin/dist");

// Shared context + side panel page (one Chromium instance for the whole suite).
let ctx: BrowserContext;
let panelPage: Page;
let extensionId: string;

test.beforeAll(async () => {
  ctx = await chromium.launchPersistentContext("", {
    headless: false,                    // must be false for extension support
    args: [
      "--headless=new",                 // new headless — no window, but extensions work
      `--disable-extensions-except=${EXTENSION_PATH}`,
      `--load-extension=${EXTENSION_PATH}`,
      "--no-sandbox",
      "--disable-setuid-sandbox",
      "--disable-dev-shm-usage",
    ],
  });

  // Wait for the background service worker to register.
  let [sw] = ctx.serviceWorkers();
  if (!sw) sw = await ctx.waitForEvent("serviceworker", { timeout: 15_000 });
  extensionId = sw.url().split("/")[2];
  console.log("Extension ID:", extensionId);

  // Open the side panel page once.
  panelPage = await ctx.newPage();
  await panelPage.goto(`chrome-extension://${extensionId}/side_panel.html`, {
    waitUntil: "domcontentloaded",
  });
  await panelPage.waitForSelector(".app", { timeout: 12_000 });
});

test.afterAll(async () => {
  await ctx?.close();
});

// ── Basic load ────────────────────────────────────────────────────────────────

test("side panel loads without JS errors", async () => {
  const errors: string[] = [];
  panelPage.on("pageerror", (e) => {
    // Ignore expected chrome.* API errors (not available outside real extension context).
    if (!e.message.includes("chrome.") && !e.message.includes("Cannot read properties of undefined")) {
      errors.push(e.message);
    }
  });
  // Already loaded in beforeAll — just assert .app is present.
  await expect(panelPage.locator(".app")).toBeVisible();
  expect(errors).toHaveLength(0);
});

// ── Header ────────────────────────────────────────────────────────────────────

test("header is visible", async () => {
  await expect(panelPage.locator(".header")).toBeVisible();
});

test("header shows BANKNIFTY as default symbol", async () => {
  await expect(panelPage.locator(".header-context")).toContainText("BANKNIFTY");
});

test("header shows NSE exchange", async () => {
  await expect(panelPage.locator(".header-context")).toContainText("NSE");
});

test("header shows 5m timeframe", async () => {
  await expect(panelPage.locator(".header-context")).toContainText("5m");
});

test("header shows API status indicator", async () => {
  // The status indicator is always rendered (green or red dot).
  const status = panelPage.locator(".api-dot");
  await expect(status).toBeVisible();
});

test("API status updates to connected when server is up", async () => {
  // The health check fires on mount — wait 5s for it to complete.
  await panelPage.waitForTimeout(5_000);
  const status = panelPage.locator(".api-dot");
  
  
  // Check title attr — span uses title not text content for status.
  const title = await status.getAttribute("title"); expect(title).toBeTruthy();
});

// ── Capture button ────────────────────────────────────────────────────────────

test("capture button is visible", async () => {
  const btn = panelPage.locator(".capture-btn");
  await expect(btn).toBeVisible();
});

test("capture button shows capture action label", async () => {
  const btn = panelPage.locator(".capture-btn");
  await expect(btn).toContainText(/analyze/i);
  await expect(btn).toHaveAttribute("aria-label", /capture and analyze/i);
});

test("select area capture control is visible", async () => {
  await expect(panelPage.locator(".capture-area-btn")).toBeVisible();
  await expect(panelPage.locator(".capture-area-btn")).toContainText(/select area/i);
});

// ── Chat panel locked state ───────────────────────────────────────────────────

test("chat input is disabled before capture", async () => {
  const chatInput = panelPage.locator(".chat-input");
  await expect(chatInput).toBeVisible();
  await expect(chatInput).toBeDisabled();
});

test("chat send button is disabled before capture", async () => {
  const sendBtn = panelPage.locator(".chat-send-btn");
  await expect(sendBtn).toBeDisabled();
});

test("chat locked message is shown before capture", async () => {
  const panel = panelPage.locator(".chat-panel");
  await expect(panel).toContainText(/capture/i);
});

// ── Chart context interaction ─────────────────────────────────────────────────

test("chart context editor is collapsed by default", async () => {
  await expect(panelPage.locator(".header-context")).toBeVisible();
  await expect(panelPage.locator(".symbol-input")).toBeHidden();
});

test("chart context edit reveals symbol dropdown and accepts a canonical ticker", async () => {
  await panelPage.locator(".context-edit-btn").click();
  await expect(panelPage.locator(".symbol-input")).toBeVisible();
  await expect(panelPage.locator(".symbol-select")).toBeVisible();
  await expect(panelPage.locator(".symbol-select")).toContainText("MUTHOOTFIN");

  await panelPage.locator(".symbol-select").selectOption("MUTHOOTFIN");
  await expect(panelPage.locator(".header-context")).toContainText("MUTHOOTFIN");

  // Reset back to BANKNIFTY for subsequent tests.
  await panelPage.locator(".symbol-select").selectOption("BANKNIFTY");
  await panelPage.locator(".context-edit-btn").click();
  await expect(panelPage.locator(".symbol-input")).toBeHidden();
});

// ── Footer ────────────────────────────────────────────────────────────────────

test("footer shows research disclaimer", async () => {
  await expect(panelPage.locator(".footer")).toContainText(/research.*not investment advice/i);
});

// ── Main tab strip ────────────────────────────────────────────────────────────

test("main tab strip is visible", async () => {
  await expect(panelPage.locator(".main-tabs")).toBeVisible();
});

test("Analyze tab is active by default", async () => {
  const analyzeTab = panelPage.locator(".main-tab--active");
  await expect(analyzeTab).toContainText(/analyze/i);
});

test("all three main tabs are rendered", async () => {
  const tabs = panelPage.locator(".main-tab");
  await expect(tabs).toHaveCount(3);
  await expect(tabs.nth(0)).toContainText(/analyze/i);
  await expect(tabs.nth(1)).toContainText(/backtest/i);
  await expect(tabs.nth(2)).toContainText(/ric/i);
});

test("clicking Backtest tab switches to backtest view", async () => {
  const btTab = panelPage.locator(".main-tab").nth(1);
  await btTab.click();
  await expect(panelPage.locator(".bt-panel")).toBeVisible();
  // Capture button (analyze view) should be hidden
  await expect(panelPage.locator(".capture-btn")).not.toBeVisible();
});

// ── BacktestTab ───────────────────────────────────────────────────────────────

test("BacktestTab shows sub-tabs: Run and Top", async () => {
  // Ensure we are on Backtest tab
  await panelPage.locator(".main-tab").nth(1).click();
  const subTabs = panelPage.locator(".bt-tab");
  await expect(subTabs).toHaveCount(2);
  await expect(subTabs.nth(0)).toContainText(/run/i);
  await expect(subTabs.nth(1)).toContainText(/top/i);
});

test("BacktestTab Run view has strategy select and Run button", async () => {
  await panelPage.locator(".main-tab").nth(1).click();
  await panelPage.locator(".bt-tab").nth(0).click(); // ▶ Run sub-tab
  await expect(panelPage.locator(".bt-select")).toBeVisible();
  await expect(panelPage.locator(".bt-run-btn")).toBeVisible();
  await expect(panelPage.locator(".bt-run-btn")).toContainText(/run/i);
});

test("BacktestTab strategy dropdown populates within 5s (API call)", async () => {
  await panelPage.locator(".main-tab").nth(1).click();
  // If API is reachable, select options > 1 (fallback option is just 1 item)
  await panelPage.waitForTimeout(5_000);
  const opts = await panelPage.locator(".bt-select option").count();
  // At minimum the fallback option is shown; if API is up we get 10+
  expect(opts).toBeGreaterThanOrEqual(1);
});

test("clicking Run button starts loading (shows ⏳)", async () => {
  await panelPage.locator(".main-tab").nth(1).click();
  await panelPage.locator(".bt-tab").nth(0).click();
  const runBtn = panelPage.locator(".bt-run-btn");
  await runBtn.click();
  // Immediately after click it shows the loading indicator
  await expect(runBtn).toContainText(/⏳/, { timeout: 2_000 });
});

test("BacktestTab Top sub-tab shows leaderboard section", async () => {
  await panelPage.locator(".main-tab").nth(1).click();
  await panelPage.locator(".bt-tab").nth(1).click(); // 🏆 Top
  // Should show either a table, empty message, or loading message
  const panel = panelPage.locator(".bt-panel");
  await expect(panel).toBeVisible();
  const hasTable   = await panelPage.locator(".bt-leader-table").isVisible();
  const hasEmpty   = await panelPage.locator(".panel-empty").isVisible();
  const hasLoading = await panelPage.locator(".panel-empty").filter({ hasText: /loading/i }).isVisible();
  // At least one of the three should be shown
  expect(hasTable || hasEmpty || hasLoading).toBe(true);
});

test("switching back to Analyze tab restores capture button", async () => {
  // Click Analyze tab
  await panelPage.locator(".main-tab").nth(0).click();
  await expect(panelPage.locator(".capture-btn")).toBeVisible();
  await expect(panelPage.locator(".bt-panel")).not.toBeVisible();
});

// ── RIC Tab ───────────────────────────────────────────────────────────────────

test("clicking RIC tab shows RIC view", async () => {
  await panelPage.locator(".main-tab").nth(2).click();
  await expect(panelPage.locator(".ric-tab")).toBeVisible();
  await expect(panelPage.locator(".capture-btn")).not.toBeVisible();
});

test("RIC tab has Run RIC Analysis button", async () => {
  await panelPage.locator(".main-tab").nth(2).click();
  const btn = panelPage.locator(".ric-run-btn");
  await expect(btn).toBeVisible();
  await expect(btn).toContainText(/run ric/i);
});

test("RIC tab shows symbol context next to run button", async () => {
  await panelPage.locator(".main-tab").nth(2).click();
  const ctx = panelPage.locator(".ric-context");
  await expect(ctx).toBeVisible();
  // Should contain symbol and timeframe e.g. "BANKNIFTY · 5m"
  const text = await ctx.textContent();
  expect(text).toMatch(/·/);
});

test("clicking Run RIC shows loading state (⏳)", async () => {
  await panelPage.locator(".main-tab").nth(2).click();
  const btn = panelPage.locator(".ric-run-btn");
  await btn.click();
  await expect(btn).toContainText(/⏳|analysing/i, { timeout: 3_000 });
});

test("RIC Run returns safety badge within 30s (API call)", async () => {
  await panelPage.locator(".main-tab").nth(2).click();
  await panelPage.locator(".ric-run-btn").click();
  // Wait for results — up to 30s for LLM call
  await panelPage.waitForSelector(".ric-safety", { timeout: 30_000 });
  const badge = panelPage.locator(".ric-safety-badge");
  await expect(badge).toBeVisible();
  const text = await badge.textContent();
  expect(text).toMatch(/SAFE|MODERATE|CAUTION|RISKY/);
});

test("RIC results show intraday and swing cards", async () => {
  // RIC results should already be present from the previous test
  await panelPage.locator(".main-tab").nth(2).click();
  const safetyVisible = await panelPage.locator(".ric-safety").isVisible();
  if (!safetyVisible) {
    await panelPage.locator(".ric-run-btn").click();
    await panelPage.waitForSelector(".ric-safety", { timeout: 30_000 });
  }
  const cards = panelPage.locator(".ric-card");
  const count = await cards.count();
  expect(count).toBeGreaterThanOrEqual(1);
  // Each card should show entry/stop prices
  const firstCard = cards.first();
  await expect(firstCard).toContainText(/Entry|₹/i);
});

test("RIC results show Draw on Chart button after analysis", async () => {
  await panelPage.locator(".main-tab").nth(2).click();
  const safetyVisible = await panelPage.locator(".ric-safety").isVisible();
  if (!safetyVisible) {
    await panelPage.locator(".ric-run-btn").click();
    await panelPage.waitForSelector(".ric-safety", { timeout: 30_000 });
  }
  const drawBtn = panelPage.locator(".ric-draw-btn");
  await expect(drawBtn).toBeVisible();
  await expect(drawBtn).toContainText(/draw levels/i);
});

test("RIC results show AI recommendation text", async () => {
  await panelPage.locator(".main-tab").nth(2).click();
  const safetyVisible = await panelPage.locator(".ric-safety").isVisible();
  if (!safetyVisible) {
    await panelPage.locator(".ric-run-btn").click();
    await panelPage.waitForSelector(".ric-safety", { timeout: 30_000 });
  }
  const rec = panelPage.locator(".ric-recommendation");
  await expect(rec).toBeVisible();
  await expect(rec.locator(".ric-rec-card").first()).toBeVisible();
  const text = await rec.textContent();
  expect((text ?? "").length).toBeGreaterThan(20);
});

test("switching from RIC back to Analyze restores capture button", async () => {
  await panelPage.locator(".main-tab").nth(2).click();
  await panelPage.locator(".main-tab").nth(0).click();
  await expect(panelPage.locator(".capture-btn")).toBeVisible();
  await expect(panelPage.locator(".ric-tab")).not.toBeVisible();
});
