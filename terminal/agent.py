"""
terminal/agent.py — Agent Adda NLP Query Agent.

Supports three backends (in priority order):
1. OpenAI API  (OPENAI_API_KEY env var)
2. Ollama REST (OLLAMA_HOST env var, default http://localhost:11434)
3. Keyword fallback (no external service needed)

The agent follows the spec:
  query → intent detection → entity resolution → tool plan → execution → synthesis
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any

from .tools import call_tool, get_symbol_snapshot, openai_tool_schemas, resolve_symbol

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL   = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OLLAMA_HOST    = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL   = os.getenv("OLLAMA_MODEL", "granite4:latest")

SYSTEM_PROMPT = """\
You are Agent Adda, a first-class NSE market research assistant for a power user.

Your role is RESEARCH ONLY. You:
- Help the user understand market data, technical setups, sector trends, and portfolio context.
- Frame outputs as setup quality, risk context, and research priority — never as buy/sell advice.
- Always cite data freshness (snapshot date, CSV date).
- Always include a disclaimer: "Not investment advice. For research and learning only."

You have access to a set of approved read-only tools. Use them to answer the user.

When answering a stock question, produce a balanced brief with sections:
1. Snapshot (price, stage, signals)
2. Technical Setup (RSI, ADX, MACD, supertrend, MAs)
3. Sector / Index Context
4. Latest Catalysts (if requested or relevant)
5. Risks / Watch Items
6. Source Trail (which tools were called, data freshness)

Keep responses concise but complete. Use bullet points for clarity.
"""


# ─────────────────────────────────────────────────────────────────────────────
# LLM backends
# ─────────────────────────────────────────────────────────────────────────────

class _OpenAIBackend:
    def __init__(self):
        from openai import OpenAI
        self.client = OpenAI(api_key=OPENAI_API_KEY)
        self.model  = OPENAI_MODEL

    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        kwargs: dict[str, Any] = {"model": self.model, "messages": messages}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        resp = self.client.chat.completions.create(**kwargs)
        msg = resp.choices[0].message
        return {
            "content":    msg.content or "",
            "tool_calls": [
                {"id": tc.id, "name": tc.function.name, "args": json.loads(tc.function.arguments)}
                for tc in (msg.tool_calls or [])
            ],
            "finish_reason": resp.choices[0].finish_reason,
        }

    def tool_result_message(self, tool_call_id: str, result: dict) -> dict:
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": json.dumps(result, default=str),
        }

    def format_tool_calls_in_message(self, tool_calls: list[dict]) -> dict:
        from openai.types.chat import ChatCompletionMessageToolCall
        return {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {"name": tc["name"], "arguments": json.dumps(tc["args"])},
                }
                for tc in tool_calls
            ],
        }


class _OllamaBackend:
    """Ollama REST backend — uses /api/chat with tool support if model supports it."""

    def __init__(self):
        import requests
        self.requests = requests
        self.host     = OLLAMA_HOST.rstrip("/")
        self.model    = OLLAMA_MODEL
        # Check connection
        self.requests.get(f"{self.host}/api/tags", timeout=3)

    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        body: dict[str, Any] = {"model": self.model, "messages": messages, "stream": False}
        if tools:
            body["tools"] = tools
        resp = self.requests.post(f"{self.host}/api/chat", json=body, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        msg  = data.get("message", {})

        tool_calls = []
        for tc in msg.get("tool_calls", []):
            fn = tc.get("function", {})
            tool_calls.append({
                "id":   f"ollama_{fn.get('name','')}_{int(time.time())}",
                "name": fn.get("name", ""),
                "args": fn.get("arguments", {}),
            })

        return {
            "content":     msg.get("content", ""),
            "tool_calls":  tool_calls,
            "finish_reason": "stop",
        }

    def tool_result_message(self, tool_call_id: str, result: dict) -> dict:
        return {"role": "tool", "content": json.dumps(result, default=str)}

    def format_tool_calls_in_message(self, tool_calls: list[dict]) -> dict:
        return {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"function": {"name": tc["name"], "arguments": tc["args"]}}
                for tc in tool_calls
            ],
        }


def _detect_backend() -> _OpenAIBackend | _OllamaBackend | None:
    if OPENAI_API_KEY:
        try:
            return _OpenAIBackend()
        except Exception:
            pass
    try:
        return _OllamaBackend()
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Keyword-based intent router (no LLM fallback)
# ─────────────────────────────────────────────────────────────────────────────

def _keyword_intent(query: str) -> dict:
    """Detect intent and build a tool plan from keywords alone."""
    q = query.lower()

    # Index query
    index_words = ["nifty", "sensex", "bank nifty", "nifty it", "nifty 50"]
    if any(w in q for w in index_words):
        idx = "NIFTY BANK" if "bank" in q else ("NIFTY IT" if " it" in q else "NIFTY 50")
        return {"intent": "index_status", "plan": [("get_index_snapshot", {"index_name": idx})]}

    # Breadth / market overview
    breadth_words = ["breadth", "advance decline", "a/d", "market today", "market outlook",
                     "nifty direction", "overall market", "how is market", "market status"]
    if any(w in q for w in breadth_words):
        return {"intent": "market_overview", "plan": [
            ("get_market_breadth", {}),
            ("get_index_snapshot", {"index_name": "NIFTY 50"}),
        ]}

    # Screener queries
    if any(w in q for w in ["strong buy", "top buy", "buy signals", "best stocks"]):
        return {"intent": "screener", "plan": [("run_screener_query", {"screen_type": "strong_buy"})]}
    if any(w in q for w in ["stage 2", "stage2", "weinstein", "advancing stocks"]):
        return {"intent": "screener", "plan": [("run_screener_query", {"screen_type": "stage2"})]}
    if any(w in q for w in ["new entrant", "new stage 2", "recently upgraded"]):
        return {"intent": "screener", "plan": [("run_screener_query", {"screen_type": "new_entrants"})]}
    if any(w in q for w in ["supertrend", "super trend"]):
        return {"intent": "screener", "plan": [("run_screener_query", {"screen_type": "supertrend_buy"})]}

    # Data health
    if any(w in q for w in ["data health", "data fresh", "stale", "last update", "when was"]):
        return {"intent": "data_health", "plan": [("get_data_health", {})]}

    # Reports
    if any(w in q for w in ["report", "html", "generated", "latest report"]):
        return {"intent": "report_lookup", "plan": [("find_latest_report", {})]}

    # Sector queries
    sector_words = ["sector", "pharma", "it sector", "auto sector", "bank sector",
                    "metals", "fmcg", "real estate", "energy"]
    for sw in sector_words:
        if sw in q:
            sector = sw.replace(" sector", "").title()
            return {"intent": "sector_scan", "plan": [("get_sector_context", {"sector_or_symbol": sector})]}

    # Stock-specific query — extract likely symbol
    words = re.findall(r"[A-Za-z][A-Za-z0-9\-&\.]+", query)
    skip  = {"show","me","the","latest","on","for","what","is","how","tell",
              "about","give","setup","stock","NSE","India","market","today","brief"}
    candidates = [w for w in words if w.upper() not in skip and len(w) >= 2]

    if candidates:
        sym_q = candidates[0]
        plan = [
            ("resolve_symbol",       {"query": sym_q}),
            ("get_symbol_snapshot",  {"symbol": sym_q.upper()}),
            ("get_technical_setup",  {"symbol": sym_q.upper()}),
            ("get_sector_context",   {"sector_or_symbol": sym_q.upper()}),
        ]
        if any(w in q for w in ["news", "catalyst", "recent", "latest news"]):
            plan.append(("search_latest_catalysts", {"symbol": sym_q.upper()}))
        return {"intent": "stock_brief", "plan": plan}

    return {"intent": "unknown", "plan": [("get_market_breadth", {})]}


# ─────────────────────────────────────────────────────────────────────────────
# Tool execution
# ─────────────────────────────────────────────────────────────────────────────

def _execute_plan(plan: list[tuple[str, dict]]) -> list[dict]:
    """Execute a list of (tool_name, args) tuples, resolving symbols first."""
    results: list[dict] = []
    resolved_sym: str | None = None

    for tool_name, args in plan:
        # Auto-substitute resolved symbol
        if resolved_sym and "symbol" in args and not args["symbol"]:
            args["symbol"] = resolved_sym

        result = call_tool(tool_name, args)

        # Capture resolved symbol for downstream tools
        if tool_name == "resolve_symbol" and result.get("symbol"):
            resolved_sym = result["symbol"]
            # Patch subsequent args that reference the original fuzzy query
            for _, a in plan:
                for k, v in a.items():
                    if isinstance(v, str) and v.upper() == args["query"].upper():
                        a[k] = resolved_sym

        results.append({"tool": tool_name, "args": args, "result": result})

    return results


# ─────────────────────────────────────────────────────────────────────────────
# Response synthesis (no-LLM path)
# ─────────────────────────────────────────────────────────────────────────────

def _synthesize_no_llm(intent: str, tool_results: list[dict]) -> str:
    """Build a structured text response from tool results without an LLM."""
    lines: list[str] = []

    def _get(name: str) -> dict | None:
        for tr in tool_results:
            if tr["tool"] == name:
                return tr["result"]
        return None

    snap = _get("get_symbol_snapshot")
    tech = _get("get_technical_setup")
    sec  = _get("get_sector_context")
    idx  = _get("get_index_snapshot")
    brd  = _get("get_market_breadth")
    scr  = _get("run_screener_query")
    cat  = _get("search_latest_catalysts")
    res  = _get("resolve_symbol")

    sym = (snap or {}).get("symbol") or (tech or {}).get("symbol") or ""
    cname = (snap or {}).get("company_name") or sym

    if sym:
        lines.append(f"━━━ {cname} ({sym}) — Market Brief ━━━")
        snap_date = (snap or {}).get("snapshot_date", "N/A")
        lines.append(f"Data: EOD snapshot {snap_date}\n")

    # 1. Snapshot
    if snap and not snap.get("error"):
        lines.append("▶ SNAPSHOT")
        price = snap.get("price") or (tech or {}).get("price")
        chg1d = snap.get("change_1d_pct")
        if price:
            chg_str = f"  ({chg1d:+.2f}%)" if chg1d else ""
            lines.append(f"  Price:  ₹{price:,.2f}{chg_str}")
        lines.append(f"  Stage:  {snap.get('stage','—')}  (score: {snap.get('stage_score','—')})")
        lines.append(f"  Signal: {snap.get('trading_signal','—')}")
        rs = snap.get("rs_pct")
        lines.append(f"  RS:     {rs:+.0f}%" if rs is not None else "  RS:     —")
        lines.append(f"  Sector: {snap.get('sector','—')}")
        lines.append(f"  MCap:   {snap.get('market_cap_cat','—')}")
        if snap.get("narrative"):
            lines.append(f"  Note:   {snap['narrative'][:120]}")

    # 2. Technical Setup
    if tech and not tech.get("error"):
        lines.append("\n▶ TECHNICAL SETUP")
        lines.append(f"  RSI:        {tech.get('rsi','—')}")
        lines.append(f"  ADX:        {tech.get('adx','—')}  (>25 = trending)")
        lines.append(f"  MACD:       {tech.get('macd','—')}")
        lines.append(f"  Supertrend: {tech.get('supertrend','—')}")
        ma_flags = []
        if tech.get("above_sma20"):   ma_flags.append("▲ SMA20")
        if tech.get("above_sma50"):   ma_flags.append("▲ SMA50")
        if tech.get("above_sma200"):  ma_flags.append("▲ SMA200")
        lines.append(f"  MAs:        {' | '.join(ma_flags) or '— below key MAs'}")
        h52, l52, pct = tech.get("52w_high"), tech.get("52w_low"), tech.get("pct_from_52h")
        if h52:
            lines.append(f"  52W Range:  ₹{l52:,.0f} – ₹{h52:,.0f}  ({pct:+.1f}% from high)" if pct else "")
        vr = tech.get("vol_ratio")
        lines.append(f"  Volume:     {vr:.1f}x avg" if vr else "")

    # 3. Sector Context
    if sec and not sec.get("error"):
        lines.append("\n▶ SECTOR CONTEXT")
        lines.append(f"  Sector:         {sec.get('sector','—')}")
        lines.append(f"  Stocks in DB:   {sec.get('total_stocks','—')}")
        lines.append(f"  Stage 2 count:  {sec.get('stage2_count','—')}")
        lines.append(f"  Buy signals:    {sec.get('buy_signals','—')}")
        lines.append(f"  Avg RS:         {sec.get('avg_rs_pct','—'):+.1f}%" if sec.get('avg_rs_pct') is not None else "")
        lines.append(f"  Avg 1M chg:     {sec.get('avg_1m_pct','—'):+.2f}%" if sec.get('avg_1m_pct') is not None else "")
        top5 = sec.get("top5_by_score", [])
        if top5:
            lines.append("  Top peers:      " + ", ".join(s["symbol"] for s in top5[:5]))

    # 4. Index / breadth
    if idx and not idx.get("error"):
        lines.append("\n▶ INDEX")
        lines.append(f"  {idx.get('index')}: {idx.get('close'):,.2f}  ({idx.get('chg_pct'):+.2f}%)")
        t = idx.get("trend_10d", {})
        lines.append(f"  10d trend: {t.get('chg_pct',0):+.2f}%  ({t.get('up_days',0)}/{len(t.get('closes',[]))-1} up-days)")

    if brd and not brd.get("error"):
        lines.append("\n▶ MARKET BREADTH")
        lines.append(f"  Advances: {brd.get('advances')}  Declines: {brd.get('declines')}  "
                     f"A/D ratio: {brd.get('ad_ratio')}")
        lines.append(f"  Universe avg RS: {brd.get('avg_rs_pct',0):+.1f}%")
        sd = brd.get("stage_distribution", {})
        if sd:
            lines.append("  Stage dist: " + " | ".join(f"{k}: {v}" for k, v in sd.items()))

    # 5. Screener results
    if scr:
        lines.append(f"\n▶ SCREENER: {scr.get('screen_type','').upper()}  ({scr.get('count',0)} results)")
        for s in (scr.get("results") or [])[:8]:
            rs_str = f"RS:{s['rs_pct']:+.0f}%" if s.get("rs_pct") is not None else ""
            lines.append(f"  {s['symbol']:<12}  ₹{s.get('price',0):>8,.0f}  "
                         f"{rs_str:<8}  {s.get('trading_signal','—')}")

    # 6. Catalysts
    if cat and cat.get("results"):
        lines.append("\n▶ LATEST CATALYSTS (web)")
        for r in cat["results"][:4]:
            title = r.get("title","")[:90]
            lines.append(f"  • {title}")
            if r.get("url"):
                lines.append(f"    {r['url'][:80]}")

    # 7. Risks / Watch
    risks: list[str] = []
    if tech:
        if tech.get("rsi", 50) > 75:  risks.append("RSI overbought (>75)")
        if not tech.get("above_sma50"): risks.append("Price below SMA50")
        if tech.get("adx", 0) < 20:  risks.append("ADX < 20 — weak trend")
    if snap:
        if snap.get("stage") not in ("STAGE_2", None) and snap.get("stage"):
            risks.append(f"Not in Stage 2 ({snap.get('stage')})")
    if risks:
        lines.append("\n▶ RISKS / WATCH")
        for r in risks:
            lines.append(f"  ⚠ {r}")

    # Source trail
    lines.append("\n▶ SOURCE TRAIL")
    for tr in tool_results:
        err = tr["result"].get("error", "")
        status = f"ERROR: {err}" if err else "ok"
        lines.append(f"  {tr['tool']}: {status}")

    lines.append("\n━━━ Not investment advice. For research and learning only. ━━━")
    return "\n".join(l for l in lines if l.strip() != "")


# ─────────────────────────────────────────────────────────────────────────────
# Main Agent class
# ─────────────────────────────────────────────────────────────────────────────

class Agent:
    """Agent Adda NLP Query Agent."""

    def __init__(self):
        self.backend    = _detect_backend()
        self.tool_schemas = openai_tool_schemas()
        self.backend_name = (
            "OpenAI" if isinstance(self.backend, _OpenAIBackend) else
            "Ollama" if isinstance(self.backend, _OllamaBackend) else
            "Keyword (no LLM)"
        )

    def query(self, user_input: str, show_trace: bool = False) -> dict:
        """Process a user query. Returns {"answer": str, "trace": list, "backend": str}."""
        trace: list[dict] = []

        # ── LLM path ──────────────────────────────────────────────────────────
        if self.backend is not None:
            return self._llm_query(user_input, show_trace)

        # ── Keyword fallback path ──────────────────────────────────────────────
        intent_plan = _keyword_intent(user_input)
        trace.append({"step": "intent", "result": intent_plan})

        tool_results = _execute_plan(intent_plan["plan"])
        trace.extend(tool_results)

        answer = _synthesize_no_llm(intent_plan["intent"], tool_results)
        return {"answer": answer, "trace": trace, "backend": self.backend_name,
                "intent": intent_plan["intent"]}

    def _llm_query(self, user_input: str, show_trace: bool) -> dict:
        """Full LLM-powered agentic query loop."""
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_input},
        ]
        tool_results: list[dict] = []
        max_rounds = 6

        for round_n in range(max_rounds):
            resp = self.backend.chat(messages, tools=self.tool_schemas)

            if resp["tool_calls"]:
                # Execute each tool call
                asst_msg = self.backend.format_tool_calls_in_message(resp["tool_calls"])
                messages.append(asst_msg)

                for tc in resp["tool_calls"]:
                    result = call_tool(tc["name"], tc["args"])
                    tool_results.append({"tool": tc["name"], "args": tc["args"], "result": result})
                    tool_msg = self.backend.tool_result_message(tc["id"], result)
                    messages.append(tool_msg)
            else:
                # Final text response
                answer = resp["content"]
                if not answer.rstrip().endswith("research and learning only."):
                    answer += "\n\n━━━ Not investment advice. For research and learning only. ━━━"
                return {
                    "answer":  answer,
                    "trace":   tool_results,
                    "backend": self.backend_name,
                    "intent":  "llm_driven",
                }

        # If we exhausted rounds without a text response, synthesize from tool results
        answer = _synthesize_no_llm("stock_brief", tool_results)
        return {"answer": answer, "trace": tool_results, "backend": self.backend_name,
                "intent": "llm_driven_fallback"}
