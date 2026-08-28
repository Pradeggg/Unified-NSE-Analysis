/**
 * Talk 2 Stocks MVP+1 — UI/API smoke tests.
 *
 * Run with:
 *   T2S_BASE_URL=http://127.0.0.1:8766 npx playwright test --project=talk2stocks
 */
import { test, expect, type Page } from "@playwright/test";

const BASE_URL = process.env.T2S_BASE_URL || "http://127.0.0.1:8765";

async function openT2S(page: Page) {
  await page.goto(`${BASE_URL}/talk-2-stocks`, { waitUntil: "domcontentloaded" });
  await expect(page.locator(".brand").filter({ hasText: "Talk 2 Stocks" })).toBeVisible();
  await expect(page.locator("#question")).toBeVisible();
}

async function ask(page: Page, question: string) {
  await page.locator("#question").fill(question);
  await page.locator("#send").click();
  await expect(page.locator(".message").last().locator(".bubble")).not.toContainText("Checking evidence", {
    timeout: 45_000,
  });
}

test("T2S shell loads and switches primary tabs", async ({ page }) => {
  await openT2S(page);

  await expect(page.locator(".tab", { hasText: "Chat" })).toHaveClass(/active/);
  await page.locator(".tab", { hasText: "Screener" }).click();
  await expect(page.locator(".tab", { hasText: "Screener" })).toHaveClass(/active/);
  await expect(page.locator("#question")).toHaveValue(/high RS leaders/i);

  await page.locator(".tab", { hasText: "RIC" }).click();
  await expect(page.locator("#ric-view")).toBeVisible();
  await expect(page.locator(".composer")).toBeHidden();

  await page.locator(".tab", { hasText: "Chat" }).click();
  await expect(page.locator(".composer")).toBeVisible();
});

test("T2S screener prompt returns table evidence and no resolution noise", async ({ page }) => {
  test.setTimeout(60_000);
  await openT2S(page);
  await ask(page, "Show high RS leaders");

  await expect(page.locator("#evidence-panel")).toContainText("Screener Results", { timeout: 10_000 });
  await expect(page.locator("#evidence-panel")).toContainText("High RS leaders");
  await expect(page.locator("#evidence-panel")).toContainText("run_screener_query");
  await expect(page.locator("#evidence-panel")).not.toContainText("No NSE symbol found");
});

test("T2S intraday health is gated without symbol resolution noise", async ({ page }) => {
  test.setTimeout(60_000);
  await openT2S(page);
  await ask(page, "Check intraday source health");

  await expect(page.locator("#evidence-panel")).toContainText("Intraday Source Health", { timeout: 10_000 });
  await expect(page.locator("#evidence-panel")).toContainText(/Status: (FRESH|PRESENT|STALE|MISSING|UNKNOWN)/);
  await expect(page.locator("#evidence-panel")).not.toContainText("CHECK INTRADAY");
});

test("T2S compare still renders side-by-side evidence", async ({ page }) => {
  test.setTimeout(60_000);
  await openT2S(page);
  await page.locator(".tab", { hasText: "Compare" }).click();
  await ask(page, "Compare TCS vs INFY vs HCLTECH");

  await expect(page.locator("#evidence-panel")).toContainText("Comparison", { timeout: 10_000 });
  await expect(page.locator("#evidence-panel table").first()).toContainText("TCS");
  await expect(page.locator("#evidence-panel table").first()).toContainText("INFY");
  await expect(page.locator("#evidence-panel table").first()).toContainText("HCLTECH");
});

test("T2S unknown screener API returns explicit gap without hallucinated rows", async ({ request }) => {
  const res = await request.post(`${BASE_URL}/api/talk/screener`, {
    data: { screen_type: "unknown_screen", top_n: 3, mode: "permissive" },
  });
  expect(res.status()).toBe(200);
  const body = await res.json();
  expect(body.intent).toBe("screener");
  expect(body.screener_results).toEqual([]);
  expect(body.gaps.join(" ")).toContain("Unknown screener");
});

test("T2S mobile viewport keeps core controls usable", async ({ browser }) => {
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    isMobile: true,
    hasTouch: true,
  });
  const page = await context.newPage();
  await openT2S(page);

  await expect(page.locator(".brand").filter({ hasText: "Talk 2 Stocks" })).toBeVisible();
  await expect(page.locator("#question")).toBeVisible();
  await expect(page.locator("#send")).toBeVisible();

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 2);
  expect(overflow).toBe(false);
  await context.close();
});
