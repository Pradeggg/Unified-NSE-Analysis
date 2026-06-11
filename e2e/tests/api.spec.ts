/**
 * Agent Adda Web API — endpoint tests
 *
 * Tests every route without a browser / extension.
 * The API server must be running on http://127.0.0.1:8765
 * (playwright.config.ts webServer block starts it automatically).
 */
import { test, expect } from "@playwright/test";

// ── Health ───────────────────────────────────────────────────────────────────

test("GET /api/health returns ok", async ({ request }) => {
  const res = await request.get("/api/health");
  expect(res.status()).toBe(200);
  const body = await res.json();
  expect(body.status).toBe("ok");
  expect(body.service).toBe("agent_adda_web_api");
});

// ── Symbol search ─────────────────────────────────────────────────────────────

test("GET /api/symbols/search returns results for BANKNIFTY", async ({ request }) => {
  const res = await request.get("/api/symbols/search?q=BANKNIFTY");
  expect(res.status()).toBe(200);
  const body = await res.json();
  expect(body.query).toBe("BANKNIFTY");
  expect(Array.isArray(body.results)).toBe(true);
  expect(body.results.length).toBeGreaterThan(0);
  // Each result has symbol and score fields.
  const first = body.results[0];
  expect(first).toHaveProperty("symbol");
  expect(first).toHaveProperty("score");
});

test("GET /api/symbols/search returns results for RELIANCE", async ({ request }) => {
  const res = await request.get("/api/symbols/search?q=RELIANCE&limit=3");
  expect(res.status()).toBe(200);
  const body = await res.json();
  expect(body.results.length).toBeGreaterThan(0);
  expect(body.results[0].symbol).toBeTruthy();
});

// ── Chart OHLCV ───────────────────────────────────────────────────────────────

test("GET /api/chart/ohlcv returns bars for BANKNIFTY 5m", async ({ request }) => {
  const res = await request.get("/api/chart/ohlcv?symbol=BANKNIFTY&timeframe=5m&limit=20");
  expect(res.status()).toBe(200);
  const body = await res.json();
  expect(body.symbol).toBe("BANKNIFTY");
  expect(body.timeframe).toBe("5m");
  expect(Array.isArray(body.bars)).toBe(true);
  expect(body.bars.length).toBeGreaterThan(0);
  // Each bar has the lightweight-charts shape.
  const bar = body.bars[0];
  expect(bar).toHaveProperty("time");
  expect(bar).toHaveProperty("open");
  expect(bar).toHaveProperty("high");
  expect(bar).toHaveProperty("low");
  expect(bar).toHaveProperty("close");
  expect(bar).toHaveProperty("volume");
  // Timestamps are UNIX seconds (10 digits).
  expect(String(bar.time).length).toBe(10);
});

test("GET /api/chart/ohlcv bars are sorted ascending by time", async ({ request }) => {
  const res = await request.get("/api/chart/ohlcv?symbol=BANKNIFTY&timeframe=5m&limit=10");
  expect(res.status()).toBe(200);
  const { bars } = await res.json();
  for (let i = 1; i < bars.length; i++) {
    expect(bars[i].time).toBeGreaterThan(bars[i - 1].time);
  }
});

test("GET /api/chart/ohlcv OHLC values are positive numbers", async ({ request }) => {
  const res = await request.get("/api/chart/ohlcv?symbol=BANKNIFTY&timeframe=5m&limit=5");
  const { bars } = await res.json();
  for (const bar of bars) {
    expect(bar.open).toBeGreaterThan(0);
    expect(bar.high).toBeGreaterThanOrEqual(bar.open);
    expect(bar.low).toBeLessThanOrEqual(bar.open);
    expect(bar.close).toBeGreaterThan(0);
  }
});

// ── Key levels ────────────────────────────────────────────────────────────────

test("GET /api/chart/levels returns levels for BANKNIFTY", async ({ request }) => {
  const res = await request.get("/api/chart/levels?symbol=BANKNIFTY&timeframe=5m");
  expect(res.status()).toBe(200);
  const body = await res.json();
  // At least one level must be present.
  const levelValues = [body.support, body.resistance, body.ema20, body.ema50, body.ema200, body.vwap];
  const nonNull = levelValues.filter((v) => v !== null && v !== undefined);
  expect(nonNull.length).toBeGreaterThan(0);
  // All non-null levels must be positive numbers in a reasonable NSE price range.
  for (const v of nonNull) {
    expect(typeof v).toBe("number");
    expect(v).toBeGreaterThan(0);
  }
});

test("GET /api/chart/levels support < resistance when both present", async ({ request }) => {
  const res = await request.get("/api/chart/levels?symbol=BANKNIFTY&timeframe=5m");
  const { support, resistance } = await res.json();
  if (support !== null && resistance !== null) {
    expect(support).toBeLessThan(resistance);
  }
});

// ── Analysis — chart (image-only) ─────────────────────────────────────────────

const TINY_PNG =
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==";

test("POST /api/analysis/chart → 400 when no image", async ({ request }) => {
  const res = await request.post("/api/analysis/chart", {
    data: {
      user_symbol: "BANKNIFTY",
      exchange: "NSE",
      timeframe: "5m",
      visible_indicators: [],
      user_question: "Analyze",
      conflict_policy: "prefer_pg",
      // no image field
    },
  });
  expect(res.status()).toBe(400);
  const body = await res.json();
  expect(body.detail).toMatch(/image/i);
  expect(body.detail).toMatch(/capture/i);
});

test("POST /api/analysis/chart → 200 with image, returns capture_id and evidence", async ({ request }) => {
  const res = await request.post("/api/analysis/chart", {
    data: {
      user_symbol: "BANKNIFTY",
      exchange: "NSE",
      timeframe: "5m",
      visible_indicators: ["EMA20", "Supertrend"],
      user_question: "Analyze this chart setup.",
      conflict_policy: "prefer_pg",
      image: TINY_PNG,
    },
  });
  expect(res.status()).toBe(200);
  const body = await res.json();

  // capture_id must be a UUID.
  expect(body.capture_id).toMatch(/^[0-9a-f-]{36}$/);
  expect(body.symbol).toBe("BANKNIFTY");
  expect(body.exchange).toBe("NSE");
  expect(body.timeframe).toBe("5m");

  // Evidence trail: image-only source.
  expect(body.evidence_trail.screenshot_used).toBe(true);
  expect(body.evidence_trail.pg_levels_used).toBe(false);
  expect(body.evidence_trail.source).toBe("vision_llm_image_only");

  // answer is present (may contain error text if no OPENAI_API_KEY, but field exists).
  expect(typeof body.answer).toBe("string");
  expect(body.answer.length).toBeGreaterThan(0);
});

// ── Analysis — follow-up ──────────────────────────────────────────────────────

test("POST /api/analysis/followup → 404 for unknown capture_id", async ({ request }) => {
  const res = await request.post("/api/analysis/followup", {
    data: { capture_id: "00000000-0000-0000-0000-000000000000", question: "Stop?" },
  });
  expect(res.status()).toBe(404);
  const body = await res.json();
  expect(body.detail).toMatch(/not found/i);
  expect(body.detail).toMatch(/re-capture/i);
});

test("POST /api/analysis/followup → 200 with valid capture_id", async ({ request }) => {
  test.setTimeout(90_000); // two GPT-4o calls can take up to 60s total
  // First, create a capture.
  const capture = await request.post("/api/analysis/chart", {
    data: {
      user_symbol: "NIFTY",
      exchange: "NSE",
      timeframe: "15m",
      visible_indicators: [],
      user_question: "What is the setup?",
      conflict_policy: "prefer_pg",
      image: TINY_PNG,
    },
  });
  const { capture_id } = await capture.json();

  // Follow-up uses that capture_id.
  const followup = await request.post("/api/analysis/followup", {
    data: { capture_id, question: "Where is the stop loss?" },
  });
  expect(followup.status()).toBe(200);
  const body = await followup.json();
  expect(body.capture_id).toBe(capture_id);
  expect(body.symbol).toBe("NIFTY");
  expect(typeof body.answer).toBe("string");
  expect(body.answer.length).toBeGreaterThan(0);
  expect(body.evidence_trail.source).toBe("vision_llm_followup");
  expect(body.evidence_trail.screenshot_used).toBe(false); // no re-send
});

// ── Patterns ──────────────────────────────────────────────────────────────────

test("GET /api/patterns/query returns graceful response", async ({ request }) => {
  const res = await request.get("/api/patterns/query?symbol=BANKNIFTY&timeframe=5m");
  expect(res.status()).toBe(200);
  const body = await res.json();
  expect(body.symbol).toBe("BANKNIFTY");
  expect(Array.isArray(body.patterns)).toBe(true);
  // K13 not yet available — engine_unavailable status expected.
  if (body.patterns.length > 0) {
    expect(body.patterns[0]).toHaveProperty("status");
    expect(body.patterns[0]).toHaveProperty("pattern_type");
  }
});

// ── TF normalisation (TradingView sends raw numbers) ─────────────────────────

test("POST /api/analysis/chart accepts TradingView TF '1' → normalised to 1m", async ({ request }) => {
  const res = await request.post("/api/analysis/chart", {
    data: {
      user_symbol: "BANKNIFTY",
      exchange: "NSE",
      timeframe: "1",          // TradingView raw 1-min code
      visible_indicators: [],
      user_question: "Bias?",
      conflict_policy: "prefer_pg",
      image: TINY_PNG,
    },
  });
  expect(res.status()).toBe(200);
  const body = await res.json();
  expect(body.timeframe).toBe("1m");   // must be normalised
});

test("POST /api/analysis/chart accepts TradingView TF '60' → normalised to 1h", async ({ request }) => {
  const res = await request.post("/api/analysis/chart", {
    data: {
      user_symbol: "NIFTY", exchange: "NSE", timeframe: "60",
      visible_indicators: [], user_question: "test",
      conflict_policy: "prefer_pg", image: TINY_PNG,
    },
  });
  expect(res.status()).toBe(200);
  expect((await res.json()).timeframe).toBe("1h");
});

// ── BANKNIFTY 1D fallback (index has no EOD snapshot) ────────────────────────

test("GET /api/chart/ohlcv BANKNIFTY 1D returns bars via intraday fallback", async ({ request }) => {
  const res = await request.get("/api/chart/ohlcv?symbol=BANKNIFTY&timeframe=1D&limit=5");
  expect(res.status()).toBe(200);
  const body = await res.json();
  expect(Array.isArray(body.bars)).toBe(true);
  expect(body.bars.length).toBeGreaterThan(0);   // fallback must provide bars
  // Timestamps are UNIX seconds.
  expect(String(body.bars[0].time).length).toBe(10);
});

test("GET /api/chart/ohlcv NIFTY 1D also returns bars", async ({ request }) => {
  const res = await request.get("/api/chart/ohlcv?symbol=NIFTY&timeframe=1D&limit=5");
  expect(res.status()).toBe(200);
  expect((await res.json()).bars.length).toBeGreaterThan(0);
});

// ── Web app proxy (Vite :5173 → API :8765) ───────────────────────────────────

test("Vite proxy /api/health returns 200", async ({ request }) => {
  const res = await fetch("http://localhost:5173/api/health");
  expect(res.status).toBe(200);
  const body = await res.json();
  expect(body.status).toBe("ok");
});

test("Vite proxy /api/chart/ohlcv returns bars", async () => {
  const res = await fetch("http://localhost:5173/api/chart/ohlcv?symbol=BANKNIFTY&timeframe=5m&limit=3");
  expect(res.status).toBe(200);
  const body = await res.json();
  expect(body.bars.length).toBeGreaterThan(0);
});

