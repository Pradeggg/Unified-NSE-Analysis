// Active chart context store.
// Persists to chrome.storage.local so state survives panel close/reopen.

import { useState, useEffect, useCallback } from "react";
import type {
  ActiveChartContext,
  PatternFinding,
  KeyLevels,
  Exchange,
  Timeframe,
} from "../../types";

const STORAGE_KEY = "agent_adda_active_context";

const EMPTY_LEVELS: KeyLevels = {
  support: null,
  resistance: null,
  ema20: null,
  ema50: null,
  ema100: null,
  ema200: null,
  supertrend: null,
  supertrend_direction: null,
  vwap: null,
};

function makeId(): string {
  return `cap_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
}

// ── Hook ─────────────────────────────────────────────────────────────────

export function useChartContext() {
  const [ctx, setCtx] = useState<ActiveChartContext | null>(null);
  const [loading, setLoading] = useState(true);

  // Load from storage on mount.
  useEffect(() => {
    chrome.storage.local.get(STORAGE_KEY, (result) => {
      const stored = result[STORAGE_KEY] as ActiveChartContext | undefined;
      setCtx(stored ?? null);
      setLoading(false);
    });
  }, []);

  // Persist whenever context changes.
  useEffect(() => {
    if (loading) return;
    if (ctx) {
      chrome.storage.local.set({ [STORAGE_KEY]: ctx });
    } else {
      chrome.storage.local.remove(STORAGE_KEY);
    }
  }, [ctx, loading]);

  // Create a new capture context (called immediately after screenshot).
  const createContext = useCallback(
    (
      symbol: string,
      exchange: Exchange,
      timeframe: Timeframe,
      screenshotDataUrl: string | null
    ) => {
      const newCtx: ActiveChartContext = {
        capture_id: makeId(),
        symbol,
        exchange,
        timeframe,
        captured_at: new Date().toISOString(),
        screenshot_data_url: screenshotDataUrl,
        visible_indicators: [],
        computed_levels: EMPTY_LEVELS,
        user_drawings: [],
        llm_conclusions: [],
        pg_evidence_version: null,
        pattern_findings: [],
      };
      setCtx(newCtx);
      return newCtx;
    },
    []
  );

  // Update key levels after PG fetch.
  const updateLevels = useCallback((levels: KeyLevels) => {
    setCtx((prev) =>
      prev ? { ...prev, computed_levels: levels } : prev
    );
  }, []);

  // Append a new LLM conclusion to the context.
  const addConclusion = useCallback((text: string) => {
    setCtx((prev) =>
      prev
        ? { ...prev, llm_conclusions: [...prev.llm_conclusions, text] }
        : prev
    );
  }, []);

  // Update pattern findings.
  const updatePatterns = useCallback((patterns: PatternFinding[]) => {
    setCtx((prev) =>
      prev ? { ...prev, pattern_findings: patterns } : prev
    );
  }, []);

  // Explicit context reset (symbol change, timeframe change, or user action).
  const resetContext = useCallback(() => setCtx(null), []);

  return {
    ctx,
    loading,
    createContext,
    updateLevels,
    addConclusion,
    updatePatterns,
    resetContext,
  };
}
