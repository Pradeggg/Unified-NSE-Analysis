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


def _system_prompt(symbol: str, exchange: str, timeframe: str, indicators: list[str]) -> str:
    ind_str = ", ".join(indicators) if indicators else "unknown (read from chart)"
    return f"""You are Agent Adda — an expert NSE/BSE equity and derivatives chart analyst.
You are reading a screenshot of a live trading chart captured from the browser.

Chart context:
  Symbol:    {symbol}
  Exchange:  {exchange}
  Timeframe: {timeframe}
  Visible indicators: {ind_str}

Your job is to extract everything you can SEE in the chart image:
- Current price, direction, and overall bias (bullish / bearish / neutral)
- Key price levels: support, resistance, EMA lines (read their exact values from the chart axes)
- Any visible indicators: Supertrend signal, RSI reading, MACD cross, VWAP, Bollinger squeeze
- Chart patterns: head & shoulders, double top/bottom, flag, wedge, VCP compression, flush
- Volume context: climactic volume, drying volume, distribution signs
- Trade setup: entry level, stop-loss level, target(s) with R:R

Format your response with these sections:
▶ BIAS         — one line: bullish / bearish / neutral + brief reason
▶ KEY LEVELS   — list price levels you can see (support, resistance, EMAs with values)
▶ PATTERN      — name the pattern if any, its status (forming / confirmed / failed)
▶ TRADE SETUP  — entry | stop | target(s) | R:R
▶ RISK         — what would invalidate this setup

Rules:
- ONLY cite price levels you can actually read from the chart image.
- Do NOT make up numbers. If you cannot read an EMA value, say "EMA visible but value unclear".
- Be specific and concise. Use exact price numbers wherever visible."""


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
