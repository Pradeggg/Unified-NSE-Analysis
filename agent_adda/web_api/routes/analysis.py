"""Chart analysis routes — vision LLM + PG evidence grounding."""
from __future__ import annotations

import base64
import uuid
import os
import sys
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException

from ..schemas import ChartCapturePayload, AnalysisResult, FollowUpRequest, EvidenceTrail, KeyLevels

router = APIRouter()

# In-memory session store (capture_id → context dict).  For prototype use.
_sessions: dict[str, dict] = {}


def _build_system_prompt(payload: ChartCapturePayload) -> str:
    pg = payload.pg_evidence or {}
    levels_block = ""
    if pg:
        lines = [f"  {k}: {v}" for k, v in pg.items() if v is not None]
        levels_block = "\nPG-SOURCED KEY LEVELS (authoritative):\n" + "\n".join(lines) + "\n"
    return (
        "You are Agent Adda, an expert NSE/BSE equity and derivatives analyst.\n"
        "You are analyzing a chart captured from the browser.\n"
        f"Symbol: {payload.user_symbol}  Exchange: {payload.exchange}  Timeframe: {payload.timeframe}\n"
        f"Visible indicators: {', '.join(payload.visible_indicators) or 'unknown'}\n"
        f"{levels_block}"
        "\nInstructions:\n"
        "- Ground your analysis in the PG-sourced levels above when provided.\n"
        "- If the chart image contradicts PG levels, flag the discrepancy (don't silently ignore).\n"
        "- Be precise: cite specific levels, patterns, and signals visible in the chart.\n"
        "- Format your answer with clear sections: BIAS, KEY LEVELS, PATTERN, TRADE SETUP, RISK.\n"
        "- Do NOT hallucinate price levels not visible in the chart or in the PG evidence.\n"
    )


def _call_openai_vision(system: str, image_b64: Optional[str], question: str) -> tuple[str, str, int, int]:
    """Call OpenAI vision API. Returns (answer, model, input_tokens, output_tokens)."""
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))))
    from openai import OpenAI  # type: ignore

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY not set")

    client = OpenAI(api_key=api_key)
    model = os.getenv("AGENT_ADDA_VISION_MODEL", "gpt-4o")

    content: list = [{"type": "text", "text": question}]
    if image_b64:
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{image_b64}", "detail": "high"},
        })

    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": content},
        ],
        max_tokens=1024,
    )
    answer = resp.choices[0].message.content or ""
    in_tok = resp.usage.prompt_tokens if resp.usage else 0
    out_tok = resp.usage.completion_tokens if resp.usage else 0
    return answer, model, in_tok, out_tok


@router.post("/chart", response_model=AnalysisResult)
async def analyze_chart(payload: ChartCapturePayload):
    """Analyze a captured chart image with PG evidence grounding."""
    capture_id = str(uuid.uuid4())

    evidence = EvidenceTrail(
        source="agent_adda_web_api",
        as_of=datetime.utcnow().isoformat(),
        pg_levels_used=bool(payload.pg_evidence),
        screenshot_used=bool(payload.image),
        pattern_engine_used=False,
    )

    try:
        system = _build_system_prompt(payload)
        answer, model, in_tok, out_tok = _call_openai_vision(
            system, payload.image, payload.user_question
        )
    except Exception as exc:
        answer = f"[Analysis error: {exc}]"
        model, in_tok, out_tok = "", 0, 0

    # Build key levels from pg_evidence if provided.
    pg = payload.pg_evidence or {}
    key_levels = KeyLevels(
        support=pg.get("support"),
        resistance=pg.get("resistance"),
        ema20=pg.get("ema20"),
        ema50=pg.get("ema50"),
        ema100=pg.get("ema100"),
        ema200=pg.get("ema200"),
        vwap=pg.get("vwap"),
    )

    # Persist session for follow-up.
    _sessions[capture_id] = {
        "symbol": payload.user_symbol,
        "exchange": payload.exchange,
        "timeframe": payload.timeframe,
        "system": _build_system_prompt(payload),
        "history": [
            {"role": "user", "content": payload.user_question},
            {"role": "assistant", "content": answer},
        ],
    }

    return AnalysisResult(
        capture_id=capture_id,
        symbol=payload.user_symbol,
        exchange=payload.exchange,
        timeframe=payload.timeframe,
        answer=answer,
        key_levels=key_levels,
        evidence_trail=evidence,
        model=model,
        input_tokens=in_tok,
        output_tokens=out_tok,
    )


@router.post("/followup", response_model=AnalysisResult)
async def follow_up(req: FollowUpRequest):
    """Continue a conversation using a prior capture context."""
    session = _sessions.get(req.capture_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Capture session '{req.capture_id}' not found.")

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))))
    try:
        from openai import OpenAI  # type: ignore
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not set")
        client = OpenAI(api_key=api_key)
        model = os.getenv("AGENT_ADDA_VISION_MODEL", "gpt-4o")

        messages = [{"role": "system", "content": session["system"]}]
        messages += session["history"]
        messages.append({"role": "user", "content": req.question})

        resp = client.chat.completions.create(model=model, messages=messages, max_tokens=768)
        answer = resp.choices[0].message.content or ""
        in_tok = resp.usage.prompt_tokens if resp.usage else 0
        out_tok = resp.usage.completion_tokens if resp.usage else 0

        # Update history.
        session["history"].append({"role": "user", "content": req.question})
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
            source="agent_adda_web_api_followup",
            as_of=datetime.utcnow().isoformat(),
            pg_levels_used=False,
            screenshot_used=False,
        ),
        model=model,
        input_tokens=in_tok,
        output_tokens=out_tok,
    )
