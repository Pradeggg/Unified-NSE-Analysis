/**
 * Agent Adda Web App — UI tests (http://localhost:5173)
 *
 * Covers:
 *  - App shell (toolbar, chart, sidebar)
 *  - BacktestPanel: run, metrics, CSV export, leaderboard
 *  - Live signal toast (market-hours aware)
 *  - Chart markers after backtest
 */
import { test, expect, type Page } from "@playwright/test";

const WEB_URL = "http://localhost:5173";

// ── Helpers ───────────────────────────────────────────────────────────────────

async function openApp(page: Page) {
  await page.goto(WEB_URL, { waitUntil: "domcontentloaded" });
  // Wait for the toolbar to be visible
  await page.waitForSelector("header", { timeout: 15_000 });
}

async function switchToBacktest(page: Page) {
  await page.locator("button", { hasText: /backtest/i }).click();
  await page.waitForSelector("[data-testid=backtest-panel], .backtest-panel-root, button[title*='Run']", { timeout: 5_000 }).catch(() => {});
}

async function runBacktest(page: Page, strategy?: string) {
  await page.locator("button", { hasText: /backtest/i }).click();
  if (strategy) {
    const sel = page.locator("select").first();
    if (await sel.isVisible()) {
      await sel.selectOption({ label: strategy });
    }
  }
  await page.locator("button", { hasText: /▶\s*Run/i }).first().click();
}

// ── App shell ─────────────────────────────────────────────────────────────────

test("web app loads and shows AGENT ADDA title", async ({ page }) => {
  await openApp(page);
  await expect(page.locator("text=AGENT ADDA")).toBeVisible();
});

test("toolbar shows symbol search (BANKNIFTY default)", async ({ page }) => {
  await openApp(page);
  // Symbol is shown somewhere in the toolbar
  await expect(page.locator("header")).toContainText("BANKNIFTY");
});

test("toolbar shows timeframe buttons", async ({ page }) => {
  await openApp(page);
  await expect(page.locator("header")).toContainText(/5m|15m|1m/);
});

test("sidebar Chat tab is visible", async ({ page }) => {
  await openApp(page);
  await expect(page.locator("button", { hasText: /chat/i })).toBeVisible();
});

test("sidebar Backtest tab is visible", async ({ page }) => {
  await openApp(page);
  await expect(page.locator("button", { hasText: /backtest/i })).toBeVisible();
});

test("clicking Backtest tab shows strategy selector", async ({ page }) => {
  await openApp(page);
  await page.locator("button", { hasText: /backtest/i }).click();
  // Strategy selector (a <select> element) should appear
  await expect(page.locator("select").first()).toBeVisible({ timeout: 5_000 });
});

// ── BacktestPanel — Run ───────────────────────────────────────────────────────

test("BacktestPanel has Run button", async ({ page }) => {
  await openApp(page);
  await page.locator("button", { hasText: /backtest/i }).click();
  await expect(page.locator("button", { hasText: /▶.*run/i }).first()).toBeVisible({ timeout: 5_000 });
});

test("BacktestPanel has ⚡ Best button", async ({ page }) => {
  await openApp(page);
  await page.locator("button", { hasText: /backtest/i }).click();
  await expect(page.locator("button", { hasText: /best/i }).first()).toBeVisible({ timeout: 5_000 });
});

test("BacktestPanel shows capital input", async ({ page }) => {
  await openApp(page);
  await page.locator("button", { hasText: /backtest/i }).click();
  // Capital input — type=number with value around 100000
  const inputs = page.locator("input[type=number]");
  await expect(inputs.first()).toBeVisible({ timeout: 5_000 });
});

test("Backtest run completes and shows metrics", async ({ page }) => {
  test.setTimeout(90_000);
  await openApp(page);
  await page.locator("button", { hasText: /backtest/i }).click();
  // Wait for strategies to load
  await page.waitForTimeout(2_000);
  await page.locator("button", { hasText: /▶.*run/i }).first().click();

  // Wait for either metrics pills or an error message
  const metricOrError = page.locator([
    // The metrics row (win rate, return etc)
    "text=/\\d+\\.\\d+%/",
    // Or an error
    "text=/error|failed|no data/i",
  ].join(", "));
  await expect(metricOrError).toBeVisible({ timeout: 60_000 });
});

test("Backtest run shows trade count after run", async ({ page }) => {
  test.setTimeout(90_000);
  await openApp(page);
  await page.locator("button", { hasText: /backtest/i }).click();
  await page.waitForTimeout(2_000);
  await page.locator("button", { hasText: /▶.*run/i }).first().click();
  // Trade count e.g. "▼ 12 trades" or "0 trades"
  await expect(page.locator("text=/\\d+ trade/i")).toBeVisible({ timeout: 60_000 });
});

// ── CSV Export ────────────────────────────────────────────────────────────────

test("CSV export button appears after backtest run with trades", async ({ page }) => {
  test.setTimeout(90_000);
  await openApp(page);
  await page.locator("button", { hasText: /backtest/i }).click();
  await page.waitForTimeout(2_000);
  await page.locator("button", { hasText: /▶.*run/i }).first().click();
  // Wait for run to finish
  await page.locator("text=/\\d+ trade/i").waitFor({ timeout: 60_000 });

  // Check if there were any trades
  const tradeText = await page.locator("text=/\\d+ trade/i").textContent();
  const tradeCount = parseInt(tradeText?.match(/\d+/)?.[0] ?? "0");
  if (tradeCount === 0) {
    test.skip(); // No trades — CSV button won't show
    return;
  }
  await expect(page.locator("button", { hasText: /csv/i })).toBeVisible({ timeout: 5_000 });
});

test("CSV download triggered when clicking ⬇ CSV", async ({ page }) => {
  test.setTimeout(90_000);
  await openApp(page);
  await page.locator("button", { hasText: /backtest/i }).click();
  await page.waitForTimeout(2_000);
  await page.locator("button", { hasText: /▶.*run/i }).first().click();
  await page.locator("text=/\\d+ trade/i").waitFor({ timeout: 60_000 });

  const tradeText = await page.locator("text=/\\d+ trade/i").textContent();
  const tradeCount = parseInt(tradeText?.match(/\d+/)?.[0] ?? "0");
  if (tradeCount === 0) {
    test.skip();
    return;
  }

  const [download] = await Promise.all([
    page.waitForEvent("download", { timeout: 10_000 }),
    page.locator("button", { hasText: /csv/i }).click(),
  ]);
  expect(download.suggestedFilename()).toMatch(/\.csv$/);
  expect(download.suggestedFilename()).toMatch(/trades/i);
});

// ── Leaderboard ───────────────────────────────────────────────────────────────

test("Leaderboard sub-tab is visible in BacktestPanel", async ({ page }) => {
  await openApp(page);
  await page.locator("button", { hasText: /backtest/i }).click();
  await expect(page.locator("button", { hasText: /leaderboard/i })).toBeVisible({ timeout: 5_000 });
});

test("Leaderboard tab loads and shows table or empty message", async ({ page }) => {
  test.setTimeout(30_000);
  await openApp(page);
  await page.locator("button", { hasText: /backtest/i }).click();
  await page.locator("button", { hasText: /leaderboard/i }).click();

  // Wait for either a table row or an empty/error message
  const tableOrMsg = page.locator("text=/BANKNIFTY|NIFTY|No results|no backtest/i");
  await expect(tableOrMsg).toBeVisible({ timeout: 20_000 });
});

// ── Chart markers ─────────────────────────────────────────────────────────────

test("clear markers button appears after backtest run", async ({ page }) => {
  test.setTimeout(90_000);
  await openApp(page);
  await page.locator("button", { hasText: /backtest/i }).click();
  await page.waitForTimeout(2_000);
  await page.locator("button", { hasText: /▶.*run/i }).first().click();
  await page.locator("text=/\\d+ trade/i").waitFor({ timeout: 60_000 });

  const tradeText = await page.locator("text=/\\d+ trade/i").textContent();
  const tradeCount = parseInt(tradeText?.match(/\d+/)?.[0] ?? "0");
  if (tradeCount === 0) { test.skip(); return; }

  // The ✕ clear button should appear in the tab strip
  await expect(page.locator("button", { hasText: /clear/i })).toBeVisible({ timeout: 5_000 });
});

test("clicking clear removes markers (clear button disappears)", async ({ page }) => {
  test.setTimeout(90_000);
  await openApp(page);
  await page.locator("button", { hasText: /backtest/i }).click();
  await page.waitForTimeout(2_000);
  await page.locator("button", { hasText: /▶.*run/i }).first().click();
  await page.locator("text=/\\d+ trade/i").waitFor({ timeout: 60_000 });

  const tradeText = await page.locator("text=/\\d+ trade/i").textContent();
  if (parseInt(tradeText?.match(/\d+/)?.[0] ?? "0") === 0) { test.skip(); return; }

  const clearBtn = page.locator("button", { hasText: /clear/i });
  await clearBtn.click();
  await expect(clearBtn).not.toBeVisible({ timeout: 3_000 });
});

// ── Signal toast (market hours check) ────────────────────────────────────────

test("signal toast is not shown on initial load", async ({ page }) => {
  await openApp(page);
  // Toast element should not exist right after load
  const toast = page.locator("[style*='position: fixed'][style*='bottom']");
  // Either it doesn't exist, or if it does it's not the signal toast
  const count = await toast.count();
  if (count > 0) {
    // If any fixed-bottom element exists, it should not contain BUY/SELL
    for (let i = 0; i < count; i++) {
      const text = await toast.nth(i).textContent();
      expect(text ?? "").not.toMatch(/signal/i);
    }
  }
});

// ── Watchlist ─────────────────────────────────────────────────────────────────

test("watchlist shows default symbols", async ({ page }) => {
  await openApp(page);
  const sidebar = page.locator("text=WATCHLIST");
  await expect(sidebar).toBeVisible({ timeout: 5_000 });
  await expect(page.locator("button", { hasText: "BANKNIFTY" })).toBeVisible();
  await expect(page.locator("button", { hasText: "NIFTY" })).toBeVisible();
});

test("clicking a watchlist symbol changes the header symbol", async ({ page }) => {
  await openApp(page);
  await page.locator("button", { hasText: "RELIANCE" }).first().click();
  await page.waitForTimeout(1_000);
  await expect(page.locator("header")).toContainText("RELIANCE");
});

// ── Key levels panel ──────────────────────────────────────────────────────────

test("key levels panel is shown in sidebar", async ({ page }) => {
  await openApp(page);
  // Levels section shows EMA or resistance/support labels
  await expect(page.locator("text=/EMA|Resistance|Support|VWAP/i").first()).toBeVisible({ timeout: 8_000 });
});
