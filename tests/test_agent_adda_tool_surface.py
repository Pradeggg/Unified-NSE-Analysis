from __future__ import annotations

import io
import json
from pathlib import Path

import yaml


def _example_dataset() -> dict:
    text = Path(".agents/skills/fundamental-analyze/references/input-schema.md").read_text(encoding="utf-8")
    return json.loads(text.split("```json\n", 1)[1].split("\n```", 1)[0])


def test_native_registry_exposes_bounded_skill_tools():
    from terminal.tools import TOOL_REGISTRY

    expected = {
        "render_fundamental_analysis_report",
        "list_agent_adda_skills",
        "find_agent_adda_skills",
        "execute_agent_adda_skill",
    }
    assert expected <= set(TOOL_REGISTRY)
    assert all(TOOL_REGISTRY[name][2]["type"] == "object" for name in expected)


def test_fundamental_report_tool_validates_and_writes_html(tmp_path, monkeypatch):
    from terminal.skills import tool_surface

    monkeypatch.setattr(tool_surface, "PROJECT_ROOT", tmp_path)
    result = tool_surface.render_fundamental_analysis_report(
        _example_dataset(), output_format="html", output_path="reports/elgi.html"
    )

    assert result["success"] is True
    report = Path(result["path"])
    assert report.exists()
    assert report.read_text(encoding="utf-8").startswith("<!doctype html>")


def test_fundamental_report_tool_rejects_invalid_dataset():
    from terminal.skills.tool_surface import render_fundamental_analysis_report

    result = render_fundamental_analysis_report({"company": {}})

    assert result["success"] is False
    assert result["errors"]


class _TelemetryRepo:
    def __init__(self):
        self.retrieval_events = []
        self.execution_events = []

    def list_runtime_eligible(self, domain=None):
        return [{
            "id": "quality_v1",
            "version": 1,
            "status": "production",
            "domain": "screening",
            "title": "Quality screen",
            "tags": ["quality", "screening"],
            "input_patterns": ["quality stocks"],
        }]

    def log_retrieval(self, event):
        self.retrieval_events.append(event)
        return 11

    def get_skill_card(self, skill_id, version=None):
        return {
            "id": skill_id,
            "version": 1,
            "status": "production",
            "domain": "diagnosis",
            "title": "Driver",
            "description": "Driver evidence",
            "card_payload": {
                "id": skill_id,
                "version": 1,
                "status": "production",
                "domain": "diagnosis",
                "title": "Driver",
                "description": "Driver evidence",
                "tool_plan_template": [{"name": "snapshot", "tool_name": "get_symbol_snapshot", "required_params": ["symbol"]}],
                "sql_templates": [],
                "output_contract": ["snapshot"],
                "evidence_required": {"freshness": {}},
                "metadata": {"runtime": {"default_params": {"symbol": "ELGIEQUIP"}}},
            },
        }

    def log_execution(self, event):
        self.execution_events.append(event)
        return 22


def test_find_and_execute_tools_record_runtime_telemetry():
    from terminal.skills.tool_surface import execute_agent_adda_skill, find_agent_adda_skills

    repo = _TelemetryRepo()
    found = find_agent_adda_skills("quality stocks", repository=repo)
    executed = execute_agent_adda_skill(
        "driver_v1",
        repository=repo,
        call_tool_fn=lambda name, params: {"rows": [{"symbol": params["symbol"]}], "row_count": 1},
    )

    assert found["candidates"][0]["skill_id"] == "quality_v1"
    assert len(repo.retrieval_events) == 1
    assert executed["passed"] is True
    assert executed["execution_id"] == 22
    assert executed["params"]["symbol"] == "ELGIEQUIP"
    assert len(repo.execution_events) == 1


def test_mcp_server_handshake_lists_only_bounded_tools(monkeypatch):
    from integrations.agent_adda_mcp import server

    source = io.BytesIO(
        (json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05"}}) + "\n"
         + json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}) + "\n").encode()
    )
    sink = io.BytesIO()
    assert server.serve(source, sink) == 0
    responses = [json.loads(line) for line in sink.getvalue().splitlines()]

    assert responses[0]["result"]["serverInfo"]["name"] == "agent-adda-finance"
    assert {tool["name"] for tool in responses[1]["result"]["tools"]} == set(server.EXPOSED_TOOLS)


def test_cross_client_mcp_configs_point_to_shared_server():
    cursor = json.loads(Path(".cursor/mcp.json").read_text())
    claude = json.loads(Path(".mcp.json").read_text())
    vscode = json.loads(Path(".vscode/mcp.json").read_text())

    assert cursor["mcpServers"]["agent-adda"]["args"] == ["integrations/agent_adda_mcp/server.py"]
    assert claude["mcpServers"]["agent-adda"]["args"] == ["integrations/agent_adda_mcp/server.py"]
    assert "agent_adda_mcp/server.py" in vscode["servers"]["agent-adda"]["args"][0]
