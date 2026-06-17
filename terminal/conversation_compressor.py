"""Context compression for long conversations.

After _COMPRESSION_TRIGGER_TURNS (default 10) user/assistant turn-pairs the
oldest half of _history is collapsed into a CompressedContext block.  The
block is then injected into every subsequent LLM prompt as a concise system
header so critical analysis state (symbols analysed, price/RSI/verdict, tools
run) is always available without consuming the full token budget.

Compression is LLM-assisted (uses the agent backend) with a structured JSON
extraction step followed by a brief prose summary.  A rule-based fallback
handles the case where the LLM call fails.

Usage (from NseAnalysisAgent):

    from .conversation_compressor import compress_turns, CompressedContext, merge_compressed

    new = compress_turns(history_pairs, tool_data_per_turn, backend)
    self._compressed_context = merge_compressed(self._compressed_context, new)
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Data model
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CompressedContext:
    """Immutable snapshot of what happened in compressed turns."""
    turn_range: tuple[int, int]                    # (first_turn_idx, last_turn_idx)
    created_at: float = field(default_factory=time.time)
    symbols_analyzed: list[str] = field(default_factory=list)
    # symbol → {price, rsi, pe, verdict, tools}
    key_findings: dict[str, dict[str, Any]] = field(default_factory=dict)
    topics_covered: list[str] = field(default_factory=list)
    summary: str = ""
    raw_turns: int = 0

    # ── Rendering ────────────────────────────────────────────────────────────

    def as_system_block(self) -> str:
        """Compact system-prompt block for LLM injection."""
        lines = [
            "╔══════════════════════════════════════════════════════════════════╗",
            "║           COMPRESSED PRIOR CONTEXT — USE THIS DATA               ║",
            "╠══════════════════════════════════════════════════════════════════╣",
            f"  Turns compressed : {self.raw_turns}",
        ]
        if self.symbols_analyzed:
            lines.append(f"  Symbols analysed : {', '.join(self.symbols_analyzed)}")
        if self.topics_covered:
            lines.append(f"  Topics covered   : {'; '.join(self.topics_covered)}")
        if self.key_findings:
            lines.append("")
            lines.append("  ┌─ KEY FINDINGS (use these directly for synthesis) ───────────────┐")
            for sym, data in self.key_findings.items():
                parts: list[str] = [f"    {sym}:"]
                if data.get("price"):
                    parts.append(f"price=₹{data['price']}")
                if data.get("rsi") is not None:
                    parts.append(f"RSI={data['rsi']}")
                if data.get("pe") is not None:
                    parts.append(f"PE={data['pe']}")
                if data.get("verdict"):
                    parts.append(f"verdict={data['verdict']}")
                lines.append("  " + "  ".join(parts))
            lines.append("  └──────────────────────────────────────────────────────────────────┘")
        if self.summary:
            lines.append("")
            lines.append("  Summary:")
            for ln in self.summary.strip().splitlines():
                lines.append(f"    {ln}")
        lines.append("")
        lines.append("╔══════════════════════════════════════════════════════════════════╗")
        lines.append("║  CRITICAL: For synthesis questions about these stocks (which     ║")
        lines.append("║  has the best RSI, compare all, rank them, top pick), DO NOT     ║")
        lines.append("║  call tools. Answer DIRECTLY from key_findings above.            ║")
        lines.append("╚══════════════════════════════════════════════════════════════════╝")
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# LLM extraction prompt
# ─────────────────────────────────────────────────────────────────────────────

_COMPRESS_SYSTEM = (
    "You are a concise financial-research assistant.  "
    "You will be given conversation turns (user + assistant pairs) from a stock-analysis session.  "
    "Summarise them into a compact JSON object so that a downstream LLM can answer follow-up "
    "questions without re-reading every turn.  Be factual — do not invent numbers."
)

_COMPRESS_USER_TMPL = """\
Compress the following {n} conversation turns into a JSON object.

The JSON must have EXACTLY these keys:
{{
  "symbols_analyzed": ["NSE_TICKER", ...],          // NSE tickers that were explicitly analysed (UPPERCASE, 2-12 chars)
  "key_findings": {{                                 // one entry per symbol — include only if real data was found
    "TICKER": {{
      "price": <float or null>,
      "rsi": <float or null>,
      "pe": <float or null>,
      "verdict": "<buy|sell|hold|watch|mixed|null>",
      "tools": ["tool_name", ...]                   // tools that ran for this symbol
    }}
  }},
  "topics_covered": ["short phrase", ...],          // e.g. "RIC sherlock for DIACABS", "screener scan", "portfolio review"
  "summary": "<2-3 sentence prose summary>"
}}

CONVERSATION TURNS:
{turns_text}

Respond with valid JSON only — no markdown fences."""


# ─────────────────────────────────────────────────────────────────────────────
# Rule-based fallback extraction
# ─────────────────────────────────────────────────────────────────────────────

_VERDICT_RE = re.compile(
    r"\b(strong buy|buy|accumulate|hold|sell|strong sell|watch|mixed|bullish|bearish)\b",
    re.I,
)
_PRICE_RE = re.compile(r"₹\s*([\d,]+(?:\.\d+)?)")
_RSI_RE   = re.compile(r"\bRSI\b[^\d]*([\d.]+)", re.I)
_PE_RE    = re.compile(r"\bP/?E\b[^\d]*([\d.]+)", re.I)

_VERDICT_MAP = {
    "strong buy": "buy", "accumulate": "buy",
    "bullish": "buy", "bearish": "sell",
    "strong sell": "sell",
}


def _normalise_verdict(raw: str) -> str:
    return _VERDICT_MAP.get(raw.lower(), raw.lower())


def _rule_based_extract(
    history_pairs: list[tuple[str, str]],
    tool_data: list[list[dict[str, Any]]],
) -> dict[str, Any]:
    """Extract symbols/findings from tool data + answer text without LLM."""
    symbols: list[str] = []
    findings: dict[str, dict[str, Any]] = {}
    topics: list[str] = []

    for turn_idx, (user_msg, assistant_msg) in enumerate(history_pairs):
        turn_tools = tool_data[turn_idx] if turn_idx < len(tool_data) else []
        turn_syms: list[str] = []

        for tr in turn_tools:
            result  = tr.get("result") or {}
            args    = tr.get("args") or {}
            tool    = str(tr.get("tool", ""))
            sym     = (result.get("symbol") or args.get("symbol") or "").upper()
            if sym and re.fullmatch(r"[A-Z0-9&-]{2,12}", sym):
                if sym not in symbols:
                    symbols.append(sym)
                turn_syms.append(sym)
                if sym not in findings:
                    findings[sym] = {"price": None, "rsi": None, "pe": None,
                                     "verdict": None, "tools": set()}
                findings[sym]["tools"].add(tool)
                # Price
                for key in ("last_price", "close", "ltp", "price"):
                    v = result.get(key)
                    if isinstance(v, (int, float)) and v > 0:
                        findings[sym]["price"] = round(float(v), 2)
                        break
                # RSI
                rsi = (result.get("rsi") or
                       (result.get("indicators") or {}).get("rsi_14") or
                       (result.get("indicators") or {}).get("rsi"))
                if isinstance(rsi, (int, float)):
                    findings[sym]["rsi"] = round(float(rsi), 1)
                # PE
                pe = result.get("pe") or result.get("pe_ttm")
                if isinstance(pe, (int, float)):
                    findings[sym]["pe"] = round(float(pe), 1)

        # Extract verdict from assistant answer text
        if turn_syms:
            m = _VERDICT_RE.search(assistant_msg)
            if m:
                verdict = _normalise_verdict(m.group(1))
                for s in turn_syms:
                    if findings.get(s) and not findings[s]["verdict"]:
                        findings[s]["verdict"] = verdict

        # Infer topic from intent/tools
        tool_names = [str(tr.get("tool", "")) for tr in turn_tools]
        if "ric_sherlock" in " ".join(tool_names) or "run_ric" in " ".join(tool_names):
            for s in turn_syms:
                topics.append(f"RIC sherlock for {s}")
        elif any(t in tool_names for t in ("get_symbol_snapshot", "get_technical_setup")):
            for s in turn_syms:
                topics.append(f"stock analysis for {s}")
        elif any("screener" in t or "scan" in t for t in tool_names):
            topics.append("screener/scan")
        elif any("portfolio" in t for t in tool_names):
            topics.append("portfolio review")

    # Serialise tool sets
    for sym in findings:
        findings[sym]["tools"] = sorted(findings[sym]["tools"])

    return {
        "symbols_analyzed": symbols,
        "key_findings": findings,
        "topics_covered": list(dict.fromkeys(topics)),
        "summary": "",
    }


# ─────────────────────────────────────────────────────────────────────────────
# LLM-assisted compression
# ─────────────────────────────────────────────────────────────────────────────

def _build_turns_text(
    history_pairs: list[tuple[str, str]],
    tool_data: list[list[dict[str, Any]]],
) -> str:
    """Format turns as a readable text block for the LLM prompt."""
    lines: list[str] = []
    for idx, (user_msg, asst_msg) in enumerate(history_pairs, 1):
        lines.append(f"--- Turn {idx} ---")
        lines.append(f"USER: {user_msg[:400]}")
        # Summarise tool calls compactly
        tools_in_turn = tool_data[idx - 1] if idx - 1 < len(tool_data) else []
        if tools_in_turn:
            tool_summary = ", ".join(
                f"{tr.get('tool')}({(tr.get('args') or {}).get('symbol', '')})"
                for tr in tools_in_turn[:8]
            )
            lines.append(f"TOOLS: {tool_summary}")
        lines.append(f"ASSISTANT: {asst_msg[:600]}")
    return "\n".join(lines)


def _llm_compress(
    history_pairs: list[tuple[str, str]],
    tool_data: list[list[dict[str, Any]]],
    backend: Any,
) -> dict[str, Any] | None:
    """Call the LLM backend to compress turns.  Returns raw dict or None."""
    try:
        turns_text = _build_turns_text(history_pairs, tool_data)
        user_content = _COMPRESS_USER_TMPL.format(
            n=len(history_pairs),
            turns_text=turns_text,
        )
        resp = backend.chat(
            [
                {"role": "system", "content": _COMPRESS_SYSTEM},
                {"role": "user",   "content": user_content},
            ],
            tools=None,
        )
        raw = (resp.get("content") or "").strip()
        # Strip markdown fences if the model added them
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        return json.loads(raw)
    except Exception as exc:
        logger.debug("LLM compression failed — using rule-based fallback: %s", exc)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def compress_turns(
    history_pairs: list[tuple[str, str]],
    tool_data: list[list[dict[str, Any]]],
    backend: Any,
    *,
    turn_offset: int = 0,
) -> CompressedContext:
    """Compress history_pairs into a CompressedContext.

    Args:
        history_pairs: list of (user_message, assistant_message) tuples.
        tool_data:     per-turn list of tool-result dicts (same length as history_pairs).
        backend:       LLM backend with a .chat() method (may be None for tests).
        turn_offset:   absolute turn index of the first pair (for range tracking).
    """
    extracted = None
    if backend is not None:
        extracted = _llm_compress(history_pairs, tool_data, backend)

    if extracted is None:
        extracted = _rule_based_extract(history_pairs, tool_data)

    symbols    = [str(s).upper() for s in (extracted.get("symbols_analyzed") or [])]
    raw_find   = extracted.get("key_findings") or {}
    topics     = [str(t) for t in (extracted.get("topics_covered") or [])]
    summary    = str(extracted.get("summary") or "").strip()

    # Normalise key_findings — ensure tools is always a list
    key_findings: dict[str, dict[str, Any]] = {}
    for sym, data in raw_find.items():
        sym = str(sym).upper()
        if not re.fullmatch(r"[A-Z0-9&-]{2,12}", sym):
            continue
        entry: dict[str, Any] = {
            "price":   data.get("price"),
            "rsi":     data.get("rsi"),
            "pe":      data.get("pe"),
            "verdict": data.get("verdict"),
            "tools":   list(data.get("tools") or []),
        }
        key_findings[sym] = entry

    return CompressedContext(
        turn_range=(turn_offset, turn_offset + len(history_pairs) - 1),
        symbols_analyzed=symbols,
        key_findings=key_findings,
        topics_covered=topics,
        summary=summary,
        raw_turns=len(history_pairs),
    )


def merge_compressed(
    existing: CompressedContext | None,
    new: CompressedContext,
) -> CompressedContext:
    """Merge a new CompressedContext into the existing one.

    Symbols and findings from both are unioned; topics de-duped; summaries
    concatenated (newest last).  This way the agent carries a running
    cumulative compression that grows across many sessions.
    """
    if existing is None:
        return new

    # Merge symbols (preserve order, dedupe)
    all_syms = list(dict.fromkeys(existing.symbols_analyzed + new.symbols_analyzed))

    # Merge findings: new data overwrites old for same symbol keys
    merged_findings: dict[str, dict[str, Any]] = dict(existing.key_findings)
    for sym, data in new.key_findings.items():
        if sym not in merged_findings:
            merged_findings[sym] = data
        else:
            old = dict(merged_findings[sym])
            # Only overwrite with non-None values from new
            for k in ("price", "rsi", "pe", "verdict"):
                if data.get(k) is not None:
                    old[k] = data[k]
            old_tools = set(old.get("tools") or [])
            old_tools.update(data.get("tools") or [])
            old["tools"] = sorted(old_tools)
            merged_findings[sym] = old

    # Merge topics (dedupe)
    all_topics = list(dict.fromkeys(existing.topics_covered + new.topics_covered))

    # Merge summary
    parts = [p for p in (existing.summary, new.summary) if p]
    merged_summary = "  ".join(parts)

    return CompressedContext(
        turn_range=(existing.turn_range[0], new.turn_range[1]),
        created_at=existing.created_at,
        symbols_analyzed=all_syms,
        key_findings=merged_findings,
        topics_covered=all_topics[:20],
        summary=merged_summary[:800],
        raw_turns=existing.raw_turns + new.raw_turns,
    )
