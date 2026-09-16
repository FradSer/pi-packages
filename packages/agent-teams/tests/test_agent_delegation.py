"""Public strict Agent action registration contract."""

import json
import os
import subprocess
import textwrap

PACKAGE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def run_node(script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["node", "--input-type=module", "--eval", textwrap.dedent(script)],
        cwd=PACKAGE,
        capture_output=True,
        text=True,
    )


def test_agent_tool_schema_is_a_strict_action_union():
    result = run_node("""
    import { registerLeaderTools } from "./src/tools.ts";
    const tools = new Map();
    registerLeaderTools({ registerTool(tool) { tools.set(tool.name, tool); }, getActiveTools() { return []; }, setActiveTools() {} });
    const agent = tools.get("agent");
    console.log(JSON.stringify({ name: agent.name, actions: agent.parameters.anyOf.map((entry) => entry.properties.action.const).sort(), strict: agent.parameters.anyOf.every((entry) => entry.additionalProperties === false) }));
    """)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload == {"name": "agent", "actions": ["delegate", "inspect", "start", "stop"], "strict": True}


def test_strict_agent_action_dispatcher_contracts():
    result = subprocess.run(["node", "tests/agent-actions-fixture.ts"], cwd=PACKAGE, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, f"{result.stderr}\n{result.stdout}"
    assert "AGENT_ACTIONS_OK" in result.stdout
