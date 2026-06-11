import { defineConfig, devices } from "@playwright/test";
import path from "path";

const EXTENSION_PATH = path.resolve(__dirname, "../browser_plugin/dist");
const API_BASE       = "http://127.0.0.1:8765";

export default defineConfig({
  testDir: "./tests",
  timeout: 30_000,
  expect: { timeout: 8_000 },
  reporter: [["list"], ["html", { open: "never", outputFolder: "playwright-report" }]],
  fullyParallel: false,

  /* ── API project: standard chromium, no extension needed ─────────── */
  projects: [
    {
      name: "api",
      testMatch: "**/api.spec.ts",
      use: {
        baseURL: API_BASE,
        extraHTTPHeaders: { Accept: "application/json" },
      },
    },

    /* ── Plugin project: Chromium with extension loaded ────────────── */
    {
      name: "plugin",
      testMatch: "**/plugin.spec.ts",
      use: {
        // Extensions require a persistent context — configured per-test.
        // We pass the path via env so tests can use it.
        ...devices["Desktop Chrome"],
      },
    },
  ],

  /* ── Start the FastAPI backend before all tests ───────────────────── */
  webServer: {
    command: `AGENT_ADDA_SKIP_VENV_CHECK=1 ${path.resolve(__dirname, "../.venv/bin/python")} -m uvicorn agent_adda.web_api.main:app --host 127.0.0.1 --port 8765 --no-access-log`,
    url: `${API_BASE}/api/health`,
    cwd: path.resolve(__dirname, ".."),
    reuseExistingServer: true,
    timeout: 30_000,
    stdout: "ignore",
    stderr: "pipe",
  },
});
