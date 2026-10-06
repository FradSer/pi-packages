"""Public strict child control registration contract."""

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


INTENT_TOOLS = ["agent_start", "agent_input", "agent_stop", "agent_list"]


def test_intent_tool_schemas_are_strict_flat_objects():
    """One closed flat object per intent tool, not a union root.

    The retired `agent` tool was a union of per-action objects, which forces a
    tolerance layer into every consumer because some harnesses deliver a nested
    object as a JSON string. The intent family keeps the same strictness without
    the nesting, and every registered operation still refuses unknown keys.
    """
    result = run_node("""
    import { registerComposedTools } from "./tests/composed-tools.ts";
    const tools = new Map();
    registerComposedTools({ registerTool(tool) { tools.set(tool.name, tool); }, getActiveTools() { return []; }, setActiveTools() {} });
    const payload = {};
    for (const name of %s) {
      const tool = tools.get(name);
      payload[name] = {
        name: tool.name,
        required: tool.parameters.required,
        strict: tool.parameters.additionalProperties === false,
        outputStrict: tool.outputSchema.additionalProperties === false,
        dispositions: tool.outputSchema.properties.disposition.enum,
      };
    }
    console.log(JSON.stringify(payload));
    """ % json.dumps(INTENT_TOOLS))
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert set(payload) == set(INTENT_TOOLS)
    for name in INTENT_TOOLS:
        assert payload[name]["name"] == name
        assert payload[name]["strict"] is True, name
        assert payload[name]["outputStrict"] is True, name
        # One closed input object and one closed receipt vocabulary per operation.
        assert "started" in payload[name]["dispositions"], name
        assert "rejected" in payload[name]["dispositions"], name
    assert payload["agent_start"]["required"] == ["prompt"]
    assert payload["agent_input"]["required"] == ["session", "prompt", "delivery"]
    assert payload["agent_stop"]["required"] == ["session"]
    assert payload["agent_list"]["required"] == [], "the roster reads a page, so it requires nothing"


def test_strict_agent_action_dispatcher_contracts():
    result = subprocess.run(["node", "tests/agent-actions-fixture.ts"], cwd=PACKAGE, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, f"{result.stderr}\n{result.stdout}"
    assert "AGENT_ACTIONS_OK" in result.stdout
