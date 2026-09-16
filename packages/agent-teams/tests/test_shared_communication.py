"""
Tests for communication-only shared Agent Event (agent_event({ message, to?, intent? })).
Verifies that:
1. agent_event tool is registered and available for both leader and worker.
2. Leader can send messages to a specific worker without an Assignment Attempt.
3. Message parameters are strictly (message, to?, status?).
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

def test_agent_event_registered_on_leader_and_worker():
    """Verify agent_event tool exists with (message, to?, intent?) schema on leader tools."""
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
    
    if (!registeredTools.has("agent_event")) {
      console.error("FAIL: 'agent_event' tool was not registered on leader");
      process.exit(1);
    }
    
    const eventTool = registeredTools.get("agent_event");
    console.log(JSON.stringify({
      name: eventTool.name,
      params: eventTool.parameters
    }));
    """
    res = run_node(script)
    assert res.returncode == 0, f"Script failed: {res.stderr}\n{res.stdout}"
    data = json.loads(res.stdout)
    assert data["name"] == "agent_event"
    assert "message" in data["params"]["properties"]
    assert "to" in data["params"]["properties"]
    assert "intent" in data["params"]["properties"]
    assert "status" not in data["params"]["properties"]


def test_agent_event_registered_on_worker_and_allowed_in_universe():
    """Verify agent_event is registered on worker capabilities and accepted in WORKER_TOOL_UNIVERSE."""
    script = """
    import { registerWorkerCapabilities } from "./src/worker.ts";
    import { unknownWorkerTools, WORKER_TOOL_UNIVERSE, resolveWorkerTools } from "./src/spawner.ts";
    
    const subscriptions = new Map();
    const registeredTools = new Map();
    const fakePi = {
      registerTool(def) {
        registeredTools.set(def.name, def);
      },
      getActiveTools() { return []; },
      setActiveTools() {}
    };

    fakePi.on = (event, handler) => subscriptions.set(event, handler);
    registerWorkerCapabilities(fakePi);
    
    const hasWorkerEvent = registeredTools.has("agent_event");
    const unknownWithEvent = unknownWorkerTools(["agent_event", "read"]);
    const resolvedTools = resolveWorkerTools([]);
    
    console.log(JSON.stringify({
      hasWorkerEvent,
      lifecycleEvents: [...subscriptions.keys()],
      unknownWithEvent,
      hasInResolved: resolvedTools.includes("agent_event"),
      universeHasEvent: WORKER_TOOL_UNIVERSE.includes("agent_event")
    }));
    """
    res = run_node(script)
    assert res.returncode == 0, f"Script failed: {res.stderr}\n{res.stdout}"
    data = json.loads(res.stdout)
    assert data["hasWorkerEvent"] is True
    assert "message_start" in data["lifecycleEvents"]
    assert data["unknownWithEvent"] == []
    assert data["hasInResolved"] is True
    assert data["universeHasEvent"] is True


def test_model_resolution_defaults_to_session_model_when_unset():
    """Verify resolveSpawnModel defaults to current session model when role has no pin and no team default."""
    script = """
    import { resolveSpawnModel } from "./src/team-machine.ts";
    
    // Role has no model pin (undefined), no team default (undefined), leader has model 'gemini-3.8-flash-high'
    const res = resolveSpawnModel(undefined, undefined, "cli-proxy/gemini-3.8-flash-high");
    console.log(JSON.stringify(res));
    """
    res = run_node(script)
    assert res.returncode == 0, f"Script failed: {res.stderr}\n{res.stdout}"
    data = json.loads(res.stdout)
    assert data["model"] == "cli-proxy/gemini-3.8-flash-high"
    assert data["source"] == "leader-session"

