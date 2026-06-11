"""Chart analysis routes — vision LLM reads the screenshot directly."""
from __future__ import annotations

import uuid
import os
import sys
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException

from ..schemas import ChartCapturePayload, AnalysisResult, FollowUpRequest, EvidenceTrail, KeyLevels

router = APIRouter()

# In-memory session store: capture_id → {symbol, exchange, timeframe, system, history, image_b64}
_sessions: dict[str, dict] = {}

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def _system_prompt(
    symbol: str,
    exchange: str,
    timeframe: str,
    indicators: list[str],
    page_title: Optional[str] = None,
    source_url: Optional[str] = None,
) -> str:
    ind_str = ", ".join(indicators) if indicators else "unknown (read from chart)"
    title = page_title or "unknown"
    url = source_url or "unknown"
    return f"""You are Agent Adda — an expert NSE/BSE equity and derivatives chart analyst.
You are reading a screenshot of a live trading chart captured from the browser.

Chart context:
  Symbol:    {symbol}
  Exchange:  {exchange}
  Timeframe: {timeframe}
  Visible indicators: {ind_str}
  Page title: {title}
  Source URL: {url}

Your first task is identity assessment:
- Read the instrument name/symbol from the chart header, page title, and visible chart labels.
- Compare it with the provided Symbol/Exchange/Timeframe.
- If they disagree, state the mismatch clearly and base the analysis on what is visible in the screenshot.
- If the chart looks like an index, futures contract, option, or equity, say so.
- This identity assessment is mandatory. Never start with BIAS, KEY LEVELS, or TRADE SETUP.
- If the screenshot header is cropped out or unreadable, use the provided chart context and say: "Visible instrument unreadable; using provided context: {exchange}:{symbol} · {timeframe}."

Your main task is to extract every actionable detail that is actually visible:
- Current/last price, OHLC values if visible, last candle body/wicks, and immediate direction.
- Overall bias: bullish / bearish / neutral / range-bound, with the exact visual reason.
- Key levels: horizontal levels, marked yellow/dashed lines, support/resistance zones, swing highs/lows, gaps, previous rejection zones, and visible axis prices.
- Moving averages/indicator lines: EMA/SMA stack, slope, compression/coil, crossovers, price position versus 20/50/100/200, VWAP if visible.
- Supertrend/strategy labels: current color/state, buy/sell tags, flip level, and whether price is above or below it.
- RSI/stoch/oscillators: current reading if visible, slope, MA crossover, 50/60/70/30 thresholds, divergence, overbought/oversold recovery.
- Volume: spikes, climax bars, dry-up, accumulation/distribution clues, whether rallies or selloffs carry stronger volume.
- Pattern structure: breakout, breakdown, retest, double top/bottom, V-shape recovery, wedge, flag, range, lower-high distribution, higher-low reversal, liquidity sweep, fakeout, or failed breakout.
- Time-based behavior: repeated flushes/pumps around the same visible time slot, session open/close pressure, or recurring high-volume candles if visible.
- Trade setup: long trigger, short trigger, invalidation, stop-loss, targets, risk/reward, and what must happen before taking the trade.
- Confidence: high / medium / low, based on chart readability and signal agreement.

Use structured private analysis before answering:
- First build a visual inventory of every readable indicator and annotation: instrument header, timeframe, price/OHLC, drawn horizontal levels, EMAs/SMAs, VWAP, Supertrend, RSI/oscillators, volume, strategy buy/sell labels, and visible text labels.
- Then use plan-of-thought style decomposition internally: identity → indicator inventory → price structure → momentum → volume → pattern → scenario resolution → trade plan.
- Then use tree-of-thought style scenario checks internally: bull case, bear case, range/no-trade case. Compare evidence for and against each branch.
- Resolve conflicts explicitly in the answer: for example, bullish price reclaim but weak volume, RSI strength but resistance overhead, Supertrend buy but lower-high distribution.
- Do not reveal hidden chain-of-thought. Show only concise evidence, scenario summaries, and the final actionable conclusion.

Format your response with these sections:
▶ IDENTITY      — MUST BE FIRST. Include:
                  Visible: <instrument from screenshot or unreadable>
                  Context: {exchange}:{symbol} · {timeframe}
                  Match: yes/no/uncertain
                  Type: equity/index/futures/options/unknown
▶ INDICATORS    — MUST BE SECOND. Inventory readable indicators/annotations and their visible values/states
▶ BIAS          — bullish / bearish / neutral / range-bound + brief reason
▶ KEY LEVELS    — support, resistance, EMAs/VWAP/Supertrend with only visible values
▶ CANDLE/PRICE  — latest candle, wick/body read, current price position
▶ VOLUME/RSI    — volume behavior and oscillator read
▶ PATTERN       — pattern name, status (forming / confirmed / failed), confirmation level
▶ SCENARIOS     — bull case | bear case | range/no-trade case | resolution level
▶ TRADE SETUP   — long trigger | short trigger | stop | targets | R:R if computable
▶ INVALIDATION  — what would prove the setup wrong
▶ CONFIDENCE    — high / medium / low + why

Rules:
- ONLY cite price levels you can actually read from the chart image.
- Do NOT make up numbers. If you cannot read an EMA value, say "EMA visible but value unclear".
- If an indicator is visible but unreadable, say "visible but value unclear" and use only its direction/color/relative position if clear.
- If no clean trade exists, say "No clean trade" and explain the condition required before entry.
- If a user asks for a direct answer such as support/stop/target, answer that first, then add context.
- Use exact price numbers wherever visible.
- Be specific, grounded, and concise; avoid generic market commentary.
- This is research only, not investment advice."""


def _call_vision(system: str, image_b64: Optional[str], question: str,
                 history: Optional[list] = None) -> tuple[str, str, int, int]:
    """Call OpenAI vision API. image_b64 is only sent on the first (capture) call."""
    if _REPO_ROOT not in sys.path:
        sys.path.insert(0, _REPO_ROOT)
    from openai import OpenAI  # type: ignore

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY not set — set it in .env or environment")

    client = OpenAI(api_key=api_key)
    model = os.getenv("AGENT_ADDA_VISION_MODEL", "gpt-4o")

    # Build content for this turn.
    content: list = []
    if image_b64:
        # Strip data URL prefix if present.
        b64 = image_b64.split(",", 1)[-1] if "," in image_b64 else image_b64
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{b64}", "detail": "high"},
        })
    content.append({"type": "text", "text": question})

    messages = [{"role": "system", "content": system}]
    if history:
        messages += history
    messages.append({"role": "user", "content": content})

    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=1200,
    )
    answer = resp.choices[0].message.content or ""
    in_tok  = resp.usage.prompt_tokens     if resp.usage else 0
    out_tok = resp.usage.completion_tokens if resp.usage else 0
    return answer, model, in_tok, out_tok


@router.post("/chart", response_model=AnalysisResult)
async def analyze_chart(payload: ChartCapturePayload):
    """Analyze a captured chart screenshot using vision LLM.

    The image is the single source of truth. The LLM reads price levels,
    EMAs, patterns, and signals directly from what is visible in the chart.
    """
    if not payload.image:
        raise HTTPException(status_code=400, detail="No chart image provided. Capture the chart first.")

    capture_id = str(uuid.uuid4())
    system = _system_prompt(
        payload.user_symbol, payload.exchange,
        payload.timeframe, payload.visible_indicators,
        payload.page_title, payload.source_url,
    )

    try:
        answer, model, in_tok, out_tok = _call_vision(
            system=system,
            image_b64=payload.image,
            question=payload.user_question or "Analyze this chart and give me the full setup.",
        )
    except Exception as exc:
        answer = f"[Analysis error: {exc}]"
        model, in_tok, out_tok = "", 0, 0

    # Persist session for follow-ups.
    _sessions[capture_id] = {
        "symbol":    payload.user_symbol,
        "exchange":  payload.exchange,
        "timeframe": payload.timeframe,
        "system":    system,
        # Store text-only history from this point; image was in the first turn.
        "history": [
            {
                "role": "user",
                "content": [
                    # Keep image reference in history so follow-up context is richer.
                    {"type": "image_url",
                     "image_url": {"url": f"data:image/png;base64,{(payload.image.split(',', 1)[-1] if ',' in payload.image else payload.image)}", "detail": "low"}},
                    {"type": "text", "text": payload.user_question or "Analyze this chart."},
                ],
            },
            {"role": "assistant", "content": answer},
        ],
    }

    return AnalysisResult(
        capture_id=capture_id,
        symbol=payload.user_symbol,
        exchange=payload.exchange,
        timeframe=payload.timeframe,
        answer=answer,
        key_levels=KeyLevels(),   # empty — LLM answer text contains the levels
        evidence_trail=EvidenceTrail(
            source="vision_llm_image_only",
            as_of=datetime.utcnow().isoformat(),
            pg_levels_used=False,
            screenshot_used=True,
            pattern_engine_used=False,
        ),
        model=model,
        input_tokens=in_tok,
        output_tokens=out_tok,
    )


@router.post("/followup", response_model=AnalysisResult)
async def follow_up(req: FollowUpRequest):
    """Continue analysing in the same capture context (no new image needed)."""
    session = _sessions.get(req.capture_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session '{req.capture_id}' not found. Re-capture the chart.")

    try:
        answer, model, in_tok, out_tok = _call_vision(
            system=session["system"],
            image_b64=None,               # image was already in the first turn
            question=req.question,
            history=session["history"],
        )
        session["history"].append({"role": "user",      "content": req.question})
        session["history"].append({"role": "assistant", "content": answer})
    except Exception as exc:
        answer = f"[Follow-up error: {exc}]"
        model, in_tok, out_tok = "", 0, 0

    return AnalysisResult(
        capture_id=req.capture_id,
        symbol=session["symbol"],
        exchange=session["exchange"],
        timeframe=session["timeframe"],
        answer=answer,
        evidence_trail=EvidenceTrail(
            source="vision_llm_followup",
            as_of=datetime.utcnow().isoformat(),
            screenshot_used=False,
        ),
        model=model,
        input_tokens=in_tok,
        output_tokens=out_tok,
    )
