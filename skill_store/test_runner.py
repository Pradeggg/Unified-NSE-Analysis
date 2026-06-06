from __future__ import annotations

from dataclasses import dataclass
import multiprocessing as mp
import queue
from types import MappingProxyType
from typing import Any

from .code_policy import audit_python_tool


@dataclass(frozen=True)
class ToolTestResult:
    passed: bool
    output: dict[str, Any] | None
    findings: list[str]


SAFE_BUILTINS = MappingProxyType(
    {
        "all": all,
        "any": any,
        "bool": bool,
        "dict": dict,
        "enumerate": enumerate,
        "float": float,
        "int": int,
        "len": len,
        "list": list,
        "max": max,
        "min": min,
        "range": range,
        "round": round,
        "set": set,
        "sorted": sorted,
        "str": str,
        "sum": sum,
        "tuple": tuple,
    }
)


def _execute_python_tool(tool: dict[str, Any], context: dict[str, Any], result_queue: mp.Queue) -> None:
    globals_dict: dict[str, Any] = {"__builtins__": SAFE_BUILTINS}
    locals_dict: dict[str, Any] = {}
    try:
        exec(str(tool["code"]), globals_dict, locals_dict)
        run = locals_dict.get("run") or globals_dict.get("run")
        if not callable(run):
            result_queue.put(("error", "run(context) is not callable"))
            return
        output = run(context)
        result_queue.put(("ok", output))
    except Exception as exc:
        result_queue.put(("error", f"execution failed: {type(exc).__name__}: {exc}"))


def run_python_tool_test(
    tool: dict[str, Any],
    context: dict[str, Any] | None = None,
    *,
    timeout_seconds: float = 2.0,
) -> ToolTestResult:
    findings = audit_python_tool(tool)
    if findings:
        return ToolTestResult(passed=False, output=None, findings=findings)

    result_queue: mp.Queue = mp.Queue(maxsize=1)
    process = mp.Process(target=_execute_python_tool, args=(tool, context or {}, result_queue))
    process.start()
    process.join(timeout_seconds)
    if process.is_alive():
        process.terminate()
        process.join(1.0)
        return ToolTestResult(passed=False, output=None, findings=["execution timed out"])
    if process.exitcode not in (0, None) and result_queue.empty():
        return ToolTestResult(passed=False, output=None, findings=[f"execution failed: process exited {process.exitcode}"])
    try:
        status, payload = result_queue.get_nowait()
    except queue.Empty:
        return ToolTestResult(passed=False, output=None, findings=["execution produced no result"])
    if status != "ok":
        return ToolTestResult(passed=False, output=None, findings=[str(payload)])
    output = payload

    if not isinstance(output, dict):
        return ToolTestResult(passed=False, output=None, findings=["run(context) must return a dict"])

    missing_outputs = [name for name in tool.get("outputs", []) if name not in output]
    if missing_outputs:
        return ToolTestResult(
            passed=False,
            output=output,
            findings=[f"missing output {name}" for name in missing_outputs],
        )

    return ToolTestResult(passed=True, output=output, findings=[])


def run_card_python_tool_tests(card: dict[str, Any]) -> list[str]:
    findings: list[str] = []
    tools = card.get("python_tools") or []
    if not isinstance(tools, list):
        return ["python_tools must be a list"]
    for tool in tools:
        if not isinstance(tool, dict):
            findings.append("python tool must be an object")
            continue
        result = run_python_tool_test(tool, {})
        findings.extend(f"{tool.get('id', '<missing-id>')}: {finding}" for finding in result.findings)
    return findings
