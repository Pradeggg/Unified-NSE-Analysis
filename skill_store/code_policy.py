from __future__ import annotations

import ast
import re
from typing import Any


ALLOWED_IMPORTS = {"collections", "datetime", "itertools", "math", "statistics"}
BLOCKED_CALLS = {
    "__import__",
    "compile",
    "eval",
    "exec",
    "input",
    "open",
}
BLOCKED_ATTR_CALLS = {
    "connect",
    "delete",
    "execute",
    "makedirs",
    "mkdir",
    "open",
    "popen",
    "post",
    "put",
    "remove",
    "request",
    "rmdir",
    "run",
    "system",
    "unlink",
    "write",
    "write_bytes",
    "write_text",
}
SQL_WRITE_RE = re.compile(r"\b(insert|update|delete|merge|drop|alter|create|truncate|grant|revoke|copy|call|exec)\b", re.I)


def _import_root(name: str) -> str:
    return name.split(".", 1)[0].lower()


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parts = [node.attr]
        current = node.value
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            parts.append(current.id)
        return ".".join(reversed(parts))
    return None


def _has_run_function(tree: ast.Module) -> bool:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "run":
            args = [arg.arg for arg in node.args.args]
            return args == ["context"]
    return False


def audit_python_tool(tool: dict[str, Any]) -> list[str]:
    findings: list[str] = []
    tool_id = str(tool.get("id") or "<missing-id>")
    code = str(tool.get("code") or "")

    if tool.get("language") != "python":
        findings.append(f"{tool_id}: language must be python")
    if tool.get("mode") != "read_only":
        findings.append(f"{tool_id}: mode must be read_only")
    if not isinstance(tool.get("inputs"), list):
        findings.append(f"{tool_id}: inputs must be a list")
    elif not all(isinstance(item, str) for item in tool.get("inputs", [])):
        findings.append(f"{tool_id}: inputs must contain only strings")
    if not isinstance(tool.get("outputs"), list) or not tool.get("outputs"):
        findings.append(f"{tool_id}: outputs must be a non-empty list")
    elif not all(isinstance(item, str) for item in tool.get("outputs", [])):
        findings.append(f"{tool_id}: outputs must contain only strings")
    if not isinstance(tool.get("approved_tables"), list):
        findings.append(f"{tool_id}: approved_tables must be a list")
    elif not all(isinstance(item, str) for item in tool.get("approved_tables", [])):
        findings.append(f"{tool_id}: approved_tables must contain only strings")
    if not code.strip():
        findings.append(f"{tool_id}: code is required")
        return findings

    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return [*findings, f"{tool_id}: python syntax error: {exc.msg}"]

    if not _has_run_function(tree):
        findings.append(f"{tool_id}: must define run(context)")

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = _import_root(alias.name)
                if root not in ALLOWED_IMPORTS:
                    findings.append(f"import {root} is not allowed")
        elif isinstance(node, ast.ImportFrom):
            root = _import_root(node.module or "")
            if root not in ALLOWED_IMPORTS:
                findings.append(f"import {root} is not allowed")
        elif isinstance(node, ast.Call):
            name = _call_name(node.func)
            if not name:
                continue
            short = name.rsplit(".", 1)[-1]
            if short in BLOCKED_CALLS:
                findings.append(f"call {short} is not allowed")
            elif short in BLOCKED_ATTR_CALLS:
                findings.append(f"call {name} is not allowed")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if SQL_WRITE_RE.search(node.value):
                findings.append(f"{tool_id}: SQL write operation string is not allowed")

    return sorted(dict.fromkeys(findings))


def audit_python_tools(card: dict[str, Any]) -> list[str]:
    tools = card.get("python_tools") or []
    if not isinstance(tools, list):
        return ["python_tools must be a list"]
    findings: list[str] = []
    for tool in tools:
        if not isinstance(tool, dict):
            findings.append("python tool must be an object")
            continue
        findings.extend(audit_python_tool(tool))
    return findings
