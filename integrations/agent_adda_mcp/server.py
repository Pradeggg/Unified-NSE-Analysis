#!/usr/bin/env python3
"""Dependency-free stdio MCP server for the bounded Agent Adda tool surface."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, BinaryIO


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from terminal.tools import TOOL_REGISTRY, call_tool  # noqa: E402


SERVER_NAME = "agent-adda-finance"
SERVER_VERSION = "1.0.0"
PROTOCOL_VERSION = "2024-11-05"
EXPOSED_TOOLS = (
    "render_fundamental_analysis_report",
    "list_agent_adda_skills",
    "find_agent_adda_skills",
    "execute_agent_adda_skill",
)


def tool_definitions() -> list[dict[str, Any]]:
    return [
        {"name": name, "description": TOOL_REGISTRY[name][1], "inputSchema": TOOL_REGISTRY[name][2]}
        for name in EXPOSED_TOOLS
    ]


def dispatch(message: dict[str, Any]) -> dict[str, Any] | None:
    method, request_id = message.get("method"), message.get("id")
    if method == "notifications/initialized":
        return None
    if method == "initialize":
        requested = str((message.get("params") or {}).get("protocolVersion") or PROTOCOL_VERSION)
        return _result(request_id, {
            "protocolVersion": requested,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        })
    if method == "ping":
        return _result(request_id, {})
    if method == "tools/list":
        return _result(request_id, {"tools": tool_definitions()})
    if method == "tools/call":
        params = message.get("params") or {}
        name, arguments = str(params.get("name") or ""), params.get("arguments") or {}
        if name not in EXPOSED_TOOLS:
            return _error(request_id, -32602, f"tool is not exposed: {name}")
        if not isinstance(arguments, dict):
            return _error(request_id, -32602, "tool arguments must be an object")
        output = call_tool(name, arguments)
        failed = isinstance(output, dict) and (bool(output.get("error")) or output.get("success") is False or output.get("passed") is False)
        return _result(request_id, {
            "content": [{"type": "text", "text": json.dumps(output, ensure_ascii=False, default=str)}],
            "isError": failed,
        })
    return _error(request_id, -32601, f"method not found: {method}")


def serve(stdin: BinaryIO | None = None, stdout: BinaryIO | None = None) -> int:
    source, sink = stdin or sys.stdin.buffer, stdout or sys.stdout.buffer
    while True:
        message = _read_message(source)
        if message is None:
            return 0
        response = dispatch(message)
        if response is not None:
            _write_message(sink, response)


def _read_message(stream: BinaryIO) -> dict[str, Any] | None:
    first = stream.readline()
    if not first:
        return None
    if first.lower().startswith(b"content-length:"):
        length = int(first.split(b":", 1)[1].strip())
        while True:
            header = stream.readline()
            if header in {b"\r\n", b"\n", b""}:
                break
        raw = stream.read(length)
    else:
        raw = first.strip()
    if not raw:
        return _read_message(stream)
    return json.loads(raw.decode("utf-8"))


def _write_message(stream: BinaryIO, message: dict[str, Any]) -> None:
    payload = json.dumps(message, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8") + b"\n"
    stream.write(payload)
    stream.flush()


def _result(request_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list-tools", action="store_true")
    parser.add_argument("--call", metavar="TOOL")
    parser.add_argument("--arguments", default="{}", help="JSON object used with --call")
    args = parser.parse_args(argv)
    if args.list_tools:
        print(json.dumps({"tools": tool_definitions()}, indent=2))
        return 0
    if args.call:
        if args.call not in EXPOSED_TOOLS:
            parser.error(f"tool is not exposed: {args.call}")
        arguments = json.loads(args.arguments)
        print(json.dumps(call_tool(args.call, arguments), indent=2, ensure_ascii=False, default=str))
        return 0
    return serve()


if __name__ == "__main__":
    raise SystemExit(main())
