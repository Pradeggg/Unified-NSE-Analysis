#!/usr/bin/env python3
"""
NSE Sector Research Agent – Ollama Granite4 with tool calling.

Takes user inputs and runs pipeline phases (2–5) via tool calls. Ensure Ollama is
running (e.g. ollama serve) and the model is available: ollama pull granite4

Run from project root:
  python working-sector/agent.py
Or from working-sector:
  python agent.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure working-sector is on path so pipeline and config imports work
WORKING_SECTOR = Path(__file__).resolve().parent
PROJECT_ROOT = WORKING_SECTOR.parent
if str(WORKING_SECTOR) not in sys.path:
    sys.path.insert(0, str(WORKING_SECTOR))

# Optional: run from project root for consistent paths
try:
    os.chdir(PROJECT_ROOT)
except OSError:
    pass

from pipeline_tools import TOOL_FUNCTIONS, get_tool_by_name


def run_agent_loop(model: str = "granite4:latest", sector_name: str | None = None):
    try:
        from ollama import chat
    except ImportError:
        print("Install the Ollama Python client: pip install ollama")
        sys.exit(1)

    sector_ctx = f" Current sector: {sector_name}." if sector_name else ""
    system_prompt = f"""You are an assistant for NSE sector research.{sector_ctx}
You can run pipeline phases via tools. Phases must be run in order when running individually: Phase 2 before 3, 3 before 5; Phase 4 can run after 2/3.
When the user asks to run everything or run the full pipeline, use run_full_pipeline.
When the user asks to build narratives after the pipeline, use run_narratives.
For research that must use the LATEST data and be clearly sourced and dated for the user: use run_sector_research. It runs multi-step web search (emphasising latest data), then LLM synthesis that cites sources and retrieval dates, and writes research_sources.md so the report and user understand data/research source and when it is from.
For one-off web lookups use web_search; for multi-round search without synthesis use web_search_iterative (both emphasise latest data where possible).
When the user asks what phases do or what outputs exist, use get_phase_help or list_outputs as appropriate.
Always confirm what you did and remind the user that sources and dates are in the report (sector note and research_sources.md) so they can verify recency and provenance."""

    messages = [{"role": "system", "content": system_prompt}]
    tools = TOOL_FUNCTIONS

    print("NSE Sector Research Agent (Ollama Granite4 + tool calling)")
    if sector_name:
        print(f"Sector: {sector_name}")
    print("Commands: run phase 2/3/4/5, run full pipeline, run narratives, list outputs, help. Type 'quit' or 'exit' to stop.\n")

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
            # Append assistant message (may contain tool_calls); keep as object for ollama client compatibility
            msg = response.message
            messages.append(msg)

            if not getattr(msg, "tool_calls", None):
                # No tool calls: show final reply and exit inner loop
                content = (getattr(msg, "content", None) or "").strip()
                if content:
                    print(f"\nAssistant: {content}\n")
                break

            # Execute each tool call and append results
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
                print(f"  [Tool] {name} -> {result[:200]}{'...' if len(str(result)) > 200 else ''}")


def run_agent_single_prompt(
    user_prompt: str,
    model: str = "granite4:latest",
    sector_name: str | None = None,
) -> str:
    """
    Run the agent with a single user prompt; keep processing tool calls until the model
    replies without calling tools, then return the final reply. Use for scripted research
    (e.g. 'Run sector research then full pipeline and narratives').
    """
    try:
        from ollama import chat
    except ImportError:
        return "Install the Ollama Python client: pip install ollama"
    sector_ctx = f" Current sector: {sector_name}." if sector_name else ""
    system_prompt = f"""You are an assistant for NSE sector research.{sector_ctx}
You can run pipeline phases via tools. Phases must be run in order when running individually: Phase 2 before 3, 3 before 5; Phase 4 can run after 2/3.
When the user asks to run everything or run the full pipeline, use run_full_pipeline.
When the user asks to build narratives after the pipeline, use run_narratives.
For research that must use the LATEST data and be clearly sourced and dated for the user: use run_sector_research. It runs multi-step web search (emphasising latest data), then LLM synthesis that cites sources and retrieval dates, and writes research_sources.md so the report and user understand data/research source and when it is from.
For one-off web lookups use web_search; for multi-round search without synthesis use web_search_iterative (both emphasise latest data where possible).
When the user asks what phases do or what outputs exist, use get_phase_help or list_outputs as appropriate.
Always confirm what you did and remind the user that sources and dates are in the report (sector note and research_sources.md) so they can verify recency and provenance."""
    messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
    tools = TOOL_FUNCTIONS
    max_rounds = 20  # prevent infinite tool loops
    for _ in range(max_rounds):
        response = chat(model=model, messages=messages, tools=tools, think=False)
        msg = response.message
        messages.append(msg)
        if not getattr(msg, "tool_calls", None):
            return (getattr(msg, "content", None) or "").strip()
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
    return "(Agent stopped after max rounds.)"


if __name__ == "__main__":
    model = os.environ.get("OLLAMA_MODEL", "granite4:latest")
    sector = os.environ.get("NSE_SECTOR", "auto_components")
    try:
        from config import SECTOR_DISPLAY_NAME
        sector_name = SECTOR_DISPLAY_NAME
    except Exception:
        sector_name = sector.replace("_", " ").title()
    run_agent_loop(model=model, sector_name=sector_name)
