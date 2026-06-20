import { useState, useCallback } from "react";
import type { RicResult, RicSetup } from "../../types";
import { fetchRic, sendDrawSignals, clearChartOverlay } from "../api/client";

interface Props {
  symbol:    string;
  timeframe: string;
  exchange:  string;
  captureId?: string | null;
}

// ── Small helpers ──────────────────────────────────────────────────────────

function BiasTag({ bias }: { bias: string }) {
  const colors: Record<string, string> = {
    BULLISH: "#00c853",
    BEARISH: "#f85149",
    NEUTRAL: "#ffd740",
  };
  return (
    <span className="ric-bias-tag" style={{ color: colors[bias] ?? "#8b949e" }}>
      {bias === "BULLISH" ? "▲" : bias === "BEARISH" ? "▼" : "●"} {bias}
    </span>
  );
}

function SetupCard({ title, setup, icon }: { title: string; setup: RicSetup; icon: string }) {
  const pnl = setup.potential_pct
    ? `+${setup.potential_pct}%`
    : null;
  const isWatchOnly = setup.actionable === false;
  const reasons = setup.quality_reasons ?? [];
  return (
    <div className={`ric-card ${isWatchOnly ? "ric-card--watch" : ""}`}>
      <div className="ric-card-header">
        <span className="ric-card-title">{icon} {title}</span>
        <div className="ric-card-tags">
          {isWatchOnly ? (
            <span className="ric-quality-badge ric-quality-badge--watch">WATCH ONLY</span>
          ) : (
            <span className="ric-quality-badge ric-quality-badge--trade">TRADEABLE</span>
          )}
          <BiasTag bias={setup.bias} />
        </div>
      </div>
      <div className="ric-card-body">
        <div className="ric-row">
          <span className="ric-lbl">{isWatchOnly ? "Trigger" : "Entry"}</span>
          <span className="ric-val ric-val--entry">₹{setup.trigger?.toLocaleString("en-IN")}</span>
        </div>
        <div className="ric-row">
          <span className="ric-lbl">Stop</span>
          <span className="ric-val ric-val--stop">₹{setup.stop?.toLocaleString("en-IN")}</span>
        </div>
        <div className="ric-row">
          <span className="ric-lbl">T1</span>
          <span className="ric-val ric-val--target">₹{setup.targets?.[0]?.toLocaleString("en-IN")}</span>
          {setup.targets?.[1] && (
            <>
              <span className="ric-lbl" style={{ marginLeft: 6 }}>T2</span>
              <span className="ric-val ric-val--target">₹{setup.targets[1].toLocaleString("en-IN")}</span>
            </>
          )}
        </div>
        <div className="ric-row">
          <span className="ric-lbl">R:R</span>
          <span className="ric-val">{setup.rr}x</span>
          {pnl && <>
            <span className="ric-lbl" style={{ marginLeft: 6 }}>Pot.</span>
            <span className="ric-val ric-val--target">{pnl}</span>
          </>}
        </div>
        <div className="ric-strategy">{setup.strategy}</div>
        {reasons.length ? (
          <div className="ric-quality-reasons">
            {reasons.map((reason) => (
              <span key={reason}>• {reason}</span>
            ))}
          </div>
        ) : null}
        <div className="ric-holding">⏱ {setup.holding}</div>
      </div>
    </div>
  );
}

type RecommendationTone = "verdict" | "trade" | "swing" | "options" | "risk" | "watch" | "neutral";

interface RecommendationSection {
  title: string;
  body: string;
  chips: string[];
  tone: RecommendationTone;
  icon: string;
}

function stripMarkdown(value: string): string {
  return value
    .replace(/\*\*/g, "")
    .replace(/^[-•]\s*/, "")
    .replace(/^\d+[.)]\s*/, "")
    .trim();
}

function displayTitle(value: string): string {
  return value
    .toLowerCase()
    .replace(/^KEY\s+/i, "Key ")
    .replace(/\b\w/g, (match) => match.toUpperCase())
    .replace(/\bAi\b/g, "AI")
    .replace(/\bRr\b/g, "R:R");
}

function recommendationMeta(title: string, body: string): { tone: RecommendationTone; icon: string } {
  const text = `${title} ${body}`.toLowerCase();
  if (text.includes("risk") || text.includes("invalid")) return { tone: "risk", icon: "⚠" };
  if (text.includes("option") || text.includes("condor") || text.includes("spread")) return { tone: "options", icon: "🎯" };
  if (text.includes("swing")) return { tone: "swing", icon: "📈" };
  if (text.includes("intraday") || text.includes("trade") || text.includes("entry")) return { tone: "trade", icon: "⚡" };
  if (text.includes("watch") || text.includes("next")) return { tone: "watch", icon: "👁" };
  if (text.includes("verdict") || text.includes("safe") || text.includes("risky") || text.includes("caution")) {
    return { tone: "verdict", icon: "🧭" };
  }
  return { tone: "neutral", icon: "•" };
}

function splitBody(body: string): { body: string; chips: string[] } {
  const pieces = body.split(/\s+\|\s+/).map((part) => part.trim()).filter(Boolean);
  if (pieces.length <= 1) return { body: body.trim(), chips: [] };

  const firstLooksLikeChip = /^(action|entry|stop|target|r:r|strategy|strikes|holding|invalidation):/i.test(pieces[0]);
  return {
    body: firstLooksLikeChip ? "" : pieces[0],
    chips: firstLooksLikeChip ? pieces : pieces.slice(1),
  };
}

function parseRecommendation(text: string): RecommendationSection[] {
  const sections: RecommendationSection[] = [];
  const lines = text.split(/\r?\n/).map(stripMarkdown).filter(Boolean);

  for (const raw of lines) {
    const clean = raw.replace(/^▶\s*/, "").trim();
    const match = clean.match(/^([A-Za-z][A-Za-z\s/&]+?)(?::| — | - )\s*(.*)$/);
    if (match) {
      const title = displayTitle(match[1].trim());
      const bodyParts = splitBody(match[2].trim());
      const meta = recommendationMeta(title, bodyParts.body || bodyParts.chips.join(" "));
      sections.push({ title, body: bodyParts.body, chips: bodyParts.chips, ...meta });
      continue;
    }

    if (sections.length) {
      const last = sections[sections.length - 1];
      last.body = [last.body, clean].filter(Boolean).join(" ");
    } else {
      const bodyParts = splitBody(clean);
      const meta = recommendationMeta("Observation", clean);
      sections.push({ title: "Observation", body: bodyParts.body, chips: bodyParts.chips, ...meta });
    }
  }

  return sections.length ? sections : [{
    title: "Recommendation",
    body: stripMarkdown(text),
    chips: [],
    tone: "neutral",
    icon: "•",
  }];
}

function chipTone(chip: string): string {
  const text = chip.toLowerCase();
  if (text.includes("stop") || text.includes("risk") || text.includes("invalid")) return "risk";
  if (text.includes("target") || text.includes("r:r") || text.includes("rr")) return "target";
  if (text.includes("entry") || text.includes("action") || text.includes("buy")) return "entry";
  if (text.includes("sell") || text.includes("short")) return "risk";
  return "neutral";
}

function RicRecommendation({ text }: { text: string }) {
  const sections = parseRecommendation(text);
  return (
    <div className="ric-rec-list">
      {sections.map((section, index) => (
        <article key={`${section.title}-${index}`} className={`ric-rec-card ric-rec-card--${section.tone}`}>
          <div className="ric-rec-heading">
            <span className="ric-rec-icon">{section.icon}</span>
            <span>{section.title}</span>
          </div>
          {section.body && <p className="ric-rec-body">{section.body}</p>}
          {section.chips.length ? (
            <div className="ric-rec-chips">
              {section.chips.map((chip) => (
                <span key={chip} className={`ric-rec-chip ric-rec-chip--${chipTone(chip)}`}>
                  {chip}
                </span>
              ))}
            </div>
          ) : null}
        </article>
      ))}
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────

export function RicTab({ symbol, timeframe, exchange, captureId }: Props) {
  const [ric,      setRic]      = useState<RicResult | null>(null);
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState<string | null>(null);
  const [drawn,    setDrawn]    = useState(false);

  const handleRun = useCallback(async () => {
    setLoading(true);
    setError(null);
    setDrawn(false);

    const res = await fetchRic(symbol, timeframe, exchange, captureId ?? undefined);
    setLoading(false);

    if (!res.ok || !res.data) {
      setError(res.error ?? "RIC analysis failed");
      return;
    }
    setRic(res.data);
  }, [symbol, timeframe, exchange, captureId]);

  const handleDraw = useCallback(async () => {
    if (!ric?.draw_signals?.length) return;
    setError(null);

    if (drawn) {
      try {
        await clearChartOverlay();
        setDrawn(false);
      } catch (drawError) {
        setError(drawError instanceof Error ? drawError.message : String(drawError));
      }
    } else {
      try {
        await sendDrawSignals(ric.draw_signals);
        setDrawn(true);
      } catch (drawError) {
        setError(drawError instanceof Error ? drawError.message : String(drawError));
      }
    }
  }, [ric, drawn]);

  const safetyColors: Record<string, string> = {
    SAFE:     "#00c853",
    MODERATE: "#ffd740",
    CAUTION:  "#ff9100",
    RISKY:    "#f85149",
  };

  return (
    <div className="ric-tab">
      {/* Run button */}
      <div className="ric-header">
        <button
          className="ric-run-btn"
          onClick={handleRun}
          disabled={loading}
        >
          {loading ? "⏳ Analysing…" : "🧠 Run RIC Analysis"}
        </button>
        <span className="ric-context">{symbol} · {timeframe}</span>
      </div>

      {error && <div className="ric-error">{error}</div>}

      {ric && (
        <div className="ric-results">

          {/* ── Safety badge ─────────────────────────────────────────────── */}
          <div className="ric-safety" style={{ borderColor: safetyColors[ric.safety.rating] }}>
            <div className="ric-safety-badge" style={{ background: safetyColors[ric.safety.rating] }}>
              {ric.safety.rating}
            </div>
            <div className="ric-safety-score">{ric.safety.score}/10</div>
            <div className="ric-safety-reasons">
              {ric.safety.reasons.map((r, i) => (
                <div key={i} className="ric-safety-reason">• {r}</div>
              ))}
            </div>
          </div>

          {/* ── Trade setups ─────────────────────────────────────────────── */}
          <div className="ric-setups">
            {ric.intraday?.trigger ? (
              <SetupCard title="Intraday" icon="🕐" setup={ric.intraday} />
            ) : null}
            {ric.swing?.trigger ? (
              <SetupCard title="Swing" icon="📈" setup={ric.swing} />
            ) : null}
          </div>

          {/* ── Options play ─────────────────────────────────────────────── */}
          {ric.options_play?.strategy && (
            <div className="ric-section">
              <div className="ric-section-title">🎯 Options Play</div>
              <div className="ric-options-strat">{ric.options_play.strategy}</div>
              <div className="ric-options-desc">{ric.options_play.description}</div>
              {ric.options_play.expiry && (
                <div className="ric-options-expiry">Expiry: {ric.options_play.expiry}</div>
              )}
              <div className="ric-options-risk">⚠ {ric.options_play.risk_note}</div>
            </div>
          )}

          {/* ── F&O context ───────────────────────────────────────────────── */}
          {(ric.fno?.pcr || ric.fno?.atm) ? (
            <div className="ric-section">
              <div className="ric-section-title">📊 F&O Context</div>
              <div className="ric-fno-grid">
                {ric.fno.pcr     ? <><span>PCR</span><span>{ric.fno.pcr}</span></> : null}
                {ric.fno.atm     ? <><span>ATM</span><span>₹{ric.fno.atm?.toLocaleString("en-IN")}</span></> : null}
                {ric.fno.max_pain? <><span>Max Pain</span><span>₹{ric.fno.max_pain?.toLocaleString("en-IN")}</span></> : null}
                {ric.fno.fno_signal ? <><span>Signal</span><span className={`ric-signal ric-signal--${ric.fno.fno_signal.toLowerCase()}`}>{ric.fno.fno_signal}</span></> : null}
              </div>
              {ric.fno.ce_resistance?.length ? (
                <div className="ric-walls">
                  <span className="ric-wall-label ric-wall-label--ce">CE Wall</span>
                  {ric.fno.ce_resistance.map(s => (
                    <span key={s} className="ric-wall-strike ric-wall-strike--ce">
                      {s?.toLocaleString("en-IN")}
                    </span>
                  ))}
                </div>
              ) : null}
              {ric.fno.pe_support?.length ? (
                <div className="ric-walls">
                  <span className="ric-wall-label ric-wall-label--pe">PE Floor</span>
                  {ric.fno.pe_support.map(s => (
                    <span key={s} className="ric-wall-strike ric-wall-strike--pe">
                      {s?.toLocaleString("en-IN")}
                    </span>
                  ))}
                </div>
              ) : null}
            </div>
          ) : null}

          {/* ── Market context ────────────────────────────────────────────── */}
          <div className="ric-section">
            <div className="ric-section-title">🌍 Market</div>
            <div className="ric-fno-grid">
              {/* Analysed instrument first; NIFTY 50 is only the broad benchmark. */}
              {(ric.market.symbol_close > 0 || ric.key_levels.price > 0) && (
                <>
                  <span>{symbol}</span>
                  <span>
                    ₹{(ric.market.symbol_close || ric.key_levels.price)?.toLocaleString("en-IN")}
                    {ric.market.symbol_chg_pct !== 0 && (
                      <>
                        &nbsp;
                        <span style={{ color: ric.market.symbol_chg_pct >= 0 ? "#00c853" : "#f85149" }}>
                          {ric.market.symbol_chg_pct >= 0 ? "+" : ""}{ric.market.symbol_chg_pct?.toFixed(2)}%
                        </span>
                      </>
                    )}
                  </span>
                  <span>Instrument trend</span>
                  <span style={{ color: ric.market.symbol_trend === "bullish" ? "#00c853" : ric.market.symbol_trend === "bearish" ? "#f85149" : "#ffd740" }}>
                    {ric.market.symbol_trend !== "unknown"
                      ? `${ric.market.symbol_up_days}/10 up · ${ric.market.symbol_trend}`
                      : "intraday levels only"}
                  </span>
                </>
              )}
              {/* NIFTY 50 as broader market benchmark */}
              <span style={{ color: "#8b949e" }}>NIFTY 50</span>
              <span>
                ₹{ric.market.nifty_close?.toLocaleString("en-IN")}
                &nbsp;
                <span style={{ color: ric.market.nifty_chg_pct >= 0 ? "#00c853" : "#f85149" }}>
                  {ric.market.nifty_chg_pct >= 0 ? "+" : ""}{ric.market.nifty_chg_pct?.toFixed(2)}%
                </span>
              </span>
              <span style={{ color: "#8b949e" }}>Trend 10d</span>
              <span style={{ color: ric.market.nifty_trend === "bullish" ? "#00c853" : ric.market.nifty_trend === "bearish" ? "#f85149" : "#ffd740" }}>
                {ric.market.nifty_up_days}/10 up · {ric.market.nifty_trend}
              </span>
            </div>
          </div>

          {/* ── AI Recommendation ─────────────────────────────────────────── */}
          {ric.recommendation && (
            <div className="ric-section ric-recommendation">
              <div className="ric-section-title">🤖 AI Recommendation</div>
              <RicRecommendation text={ric.recommendation} />
            </div>
          )}

          {/* ── Draw on chart ─────────────────────────────────────────────── */}
          <div className="ric-draw-row">
            <button
              className={`ric-draw-btn ${drawn ? "ric-draw-btn--active" : ""}`}
              onClick={handleDraw}
            >
              {drawn ? "🗑 Clear Chart Overlay" : "🎨 Draw Levels on Chart"}
            </button>
            {drawn && (
              <span className="ric-draw-note">
                {ric.draw_signals.length} levels painted on TradingView
              </span>
            )}
          </div>

          <div className="ric-footer">
            Model: {ric.model} · {ric.input_tokens + ric.output_tokens} tok
          </div>
        </div>
      )}
    </div>
  );
}
