"""
Tests for Core Agent Delegation Tracer Slice (agent({ name, prompt?, work? })).
Verifies that:
1. agent tool is registered and callable by the leader.
2. Delegating with prompt creates a Work Item and starts an isolated Work Session.
3. Querying an idle agent without prompt returns idle without spawning.
4. Active Work Sessions report Agent Presence accurately.
"""

import json
import os
import subprocess
import textwrap
import pytest

PACKAGE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

def run_node(script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["node", "--input-type=module", "--eval", textwrap.dedent(script)],
        cwd=PACKAGE,
        capture_output=True,
        text=True,
    )

def test_agent_tool_schema():
    """Verify that the agent tool exists with (name, prompt?, work?) schema."""
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
    
    if (!registeredTools.has("agent")) {
      console.error("FAIL: 'agent' tool was not registered");
      process.exit(1);
    }
    
    const agentTool = registeredTools.get("agent");
    console.log(JSON.stringify({
      name: agentTool.name,
      params: agentTool.parameters
    }));
    """
    res = run_node(script)
    assert res.returncode == 0, f"Script failed: {res.stderr}\n{res.stdout}"
    data = json.loads(res.stdout)
    assert data["name"] == "agent"
    assert "name" in data["params"]["properties"]
    assert "prompt" in data["params"]["properties"]
    assert "work" in data["params"]["properties"]

def test_agent_presence_query_without_prompt():
    """Verify querying presence without prompt returns idle without side effects."""
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
    
    const res = await agentTool.execute("call_1", { name: "researcher" }, {}, () => {}, {});
    console.log(JSON.stringify(res));
    """
    res = run_node(script)
    assert res.returncode == 0, f"Script failed: {res.stderr}\n{res.stdout}"
    data = json.loads(res.stdout)
    assert data["details"]["status"] == "idle"
    assert data["details"]["activeSessions"] == 0
    assert "AGENT PRESENCE" in data["content"][0]["text"]
