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


def test_agent_tool_schema_is_a_strict_flat_object():
    """One flat schema, not a union root.

    The old tool was a union of per-action objects, which forces a tolerance layer
    into every consumer because some harnesses deliver a nested object as a JSON
    string. One object with a closed action enum keeps the same strictness without
    the nesting.
    """
    result = run_node("""
    import { registerComposedTools } from "./tests/composed-tools.ts";
    const tools = new Map();
    registerComposedTools({ registerTool(tool) { tools.set(tool.name, tool); }, getActiveTools() { return []; }, setActiveTools() {} });
    const agent = tools.get("agent");
    console.log(JSON.stringify({ name: agent.name, actions: agent.parameters.properties.action.enum, strict: agent.parameters.additionalProperties === false }));
    """)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload == {"name": "agent", "actions": ["start", "inspect", "list", "stop"], "strict": True}


def test_strict_agent_action_dispatcher_contracts():
    result = subprocess.run(["node", "tests/agent-actions-fixture.ts"], cwd=PACKAGE, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, f"{result.stderr}\n{result.stdout}"
    assert "AGENT_ACTIONS_OK" in result.stdout
