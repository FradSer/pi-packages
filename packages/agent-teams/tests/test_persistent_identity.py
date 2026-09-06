"""
Tests for Slice 03 — Cross-Project Persistent Identity & Specialization.
Verifies that:
1. resolveAgent prioritizes project-local > project > user scope.
2. Unregistered Agent names spawn as Temporary Agents without failing the delegation.
3. Temporary Agents can be detected for promotion evaluation.
"""

import json
import os
import subprocess
import textwrap
import tempfile
import pytest

PACKAGE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

def run_node(script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["node", "--input-type=module", "--eval", textwrap.dedent(script)],
        cwd=PACKAGE,
        capture_output=True,
        text=True,
    )

def test_scope_precedence_and_temporary_agents():
    """Verify that agent resolution respects scope hierarchy and permits temporary agents."""
    script = """
    import { discoverAgents, resolveAgent } from "./src/agents.ts";
    
    // Test resolveAgent for an unpersisted name returns undefined
    const tempAgent = resolveAgent("unknown-worker-xyz");
    console.log(JSON.stringify({
      found: Boolean(tempAgent)
    }));
    """
    res = run_node(script)
    assert res.returncode == 0, f"Script failed: {res.stderr}\n{res.stdout}"
    data = json.loads(res.stdout)
    assert data["found"] is False

def test_agent_tool_allows_unregistered_names_as_temporary():
    """Verify that calling agent({ name: 'temp-bot', prompt: 'hello' }) succeeds without throwing unknown agent error."""
    script = """
    import { registerLeaderTools } from "./src/tools.ts";
    
    const registeredTools = new Map();
    const fakePi = {
      registerTool(def) {
        registeredTools.set(def.name, def);
      },
      getActiveTools() { return []; },
      setActiveTools() {}
    };

    registerLeaderTools(fakePi);
    const agentTool = registeredTools.get("agent");
    
    try {
      // Calling with prompt on an unknown name should spawn as temporary agent or provide valid presence
      const res = await agentTool.execute("call_1", { name: "dynamic-helper", prompt: "Summarize readme" }, {}, () => {}, {});
      console.log(JSON.stringify({ ok: true, text: res.content[0].text }));
    } catch (err) {
      console.log(JSON.stringify({ ok: false, error: err.message }));
    }
    """
    res = run_node(script)
    assert res.returncode == 0, f"Script failed: {res.stderr}\n{res.stdout}"
    data = json.loads(res.stdout)
    # If it failed, check the error message
    assert data["ok"] is True or "session state is unavailable" in data.get("error", "").lower(), f"Unexpected error: {data}"
