#!/usr/bin/env python3
"""
Portfolio Analyzer Agent – LLM + rules, with search for market sentiment.

Runs phases (ingest, PnL summary, risk + scenarios, market sentiment) via tool calling.
Can perform web searches to build market sentiment and combine with portfolio/risk data.
Requires Ollama (e.g. ollama pull granite4) or OpenAI-compatible API.

Run from project root or portfolio-analyzer:
  python portfolio-analyzer/agent.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

PORTFOLIO_ANALYZER = Path(__file__).resolve().parent
PROJECT_ROOT = PORTFOLIO_ANALYZER.parent
if str(PORTFOLIO_ANALYZER) not in sys.path:
    sys.path.insert(0, str(PORTFOLIO_ANALYZER))

from pipeline_tools import TOOL_FUNCTIONS, get_tool_by_name


def run_agent_loop(model: str = "granite4:latest"):
    try:
        from ollama import chat
    except ImportError:
        print("Install the Ollama Python client: pip install ollama")
        sys.exit(1)

    system_prompt = """You are an assistant for portfolio analysis (CDSL/PnL, risk, market sentiment).
You can run pipeline phases via tools. Run Phase 0 first (ingest), then Phase 1 (PnL summary), Phase 7 (risk + scenarios), and run_market_sentiment (web search + LLM synthesis). Use run_full_pipeline to run 0→1→7→sentiment in one go.
To build market sentiment from the web: use run_market_sentiment (multi-step search + synthesis; writes market_sentiment.md with cited sources and dates). For one-off lookups use web_search or web_search_iterative (India equity, Nifty, sectors).
When the user asks what outputs exist, use list_outputs. Always confirm what you did and remind that sources/dates are in market_sentiment.md and risk outputs for verification."""

    messages = [{"role": "system", "content": system_prompt}]
    tools = TOOL_FUNCTIONS

    print("Portfolio Analyzer Agent (Ollama + tool calling)")
    print("Commands: run phase 0/1/7, run full pipeline, run market sentiment, web search, list outputs. Type 'quit' or 'exit' to stop.\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            break
        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            print("Bye.")
            break

        messages.append({"role": "user", "content": user_input})

        while True:
            response = chat(
                model=model,
                messages=messages,
                tools=tools,
                think=False,
            )
            msg = response.message
            messages.append(msg)

            if not getattr(msg, "tool_calls", None):
                content = (getattr(msg, "content", None) or "").strip()
                if content:
                    print(f"\nAssistant: {content}\n")
                break

            for tc in msg.tool_calls:
                name = tc.function.name
                args = getattr(tc.function, "arguments", None) or {}
                if isinstance(args, str):
                    try:
                        import json
                        args = json.loads(args) if args.strip() else {}
                    except Exception:
                        args = {}
                fn = get_tool_by_name(name)
                if fn is None:
                    result = f"Unknown tool: {name}"
                else:
                    try:
                        result = fn(**args)
                    except Exception as e:
                        result = f"Error: {e!s}"
                messages.append({"role": "tool", "tool_name": name, "content": str(result)})
                print(f"  [Tool] {name} -> {str(result)[:200]}{'...' if len(str(result)) > 200 else ''}")


if __name__ == "__main__":
    run_agent_loop()
