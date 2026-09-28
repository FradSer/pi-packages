"""
Tests for communication-only shared Agent Event (message({ message, to?, intent? })).
Verifies that:
1. message tool is registered and available for both leader and worker.
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

def test_message_registered_on_leader_and_worker():
    """Verify message tool exists with (message, to?, intent?) schema on leader tools."""
    script = """
    import { registerComposedTools } from "./tests/composed-tools.ts";
    
    const registeredTools = new Map();
    const fakePi = {
      registerTool(def) {
        registeredTools.set(def.name, def);
      },
      getActiveTools() { return []; },
      setActiveTools() {}
    };

    registerComposedTools(fakePi);
    
    if (!registeredTools.has("message")) {
      console.error("FAIL: 'message' tool was not registered on leader");
      process.exit(1);
    }
    
    const eventTool = registeredTools.get("message");
    console.log(JSON.stringify({
      name: eventTool.name,
      params: eventTool.parameters
    }));
    """
    res = run_node(script)
    assert res.returncode == 0, f"Script failed: {res.stderr}\n{res.stdout}"
    data = json.loads(res.stdout)
    assert data["name"] == "message"
    assert "message" in data["params"]["properties"]
    assert "to" in data["params"]["properties"]
    assert "intent" in data["params"]["properties"]
    assert "status" not in data["params"]["properties"]


def test_message_registered_on_worker_and_allowed_in_universe():
    """Verify message is registered by this package's worker capabilities and
    is grantable once that capability set is contributed to the spawn.

    The universe is no longer a spawner constant: it is built from the capability
    tools the loaded worker extensions declare, so this asserts the contribution
    rather than a hardcoded list."""
    script = """
    import { registerWorkerCapabilities } from "./src/worker.ts";
    import { unknownWorkerTools, workerToolUniverse, resolveWorkerTools } from "@fradser/pi-subagents";
    import { WORKER_CAPABILITY_TOOLS } from "./src/capability-tools.ts";
    
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
    
    const hasWorkerEvent = registeredTools.has("message");
    const unknownWithEvent = unknownWorkerTools(["message", "read"], WORKER_CAPABILITY_TOOLS);
    const resolvedTools = resolveWorkerTools([], WORKER_CAPABILITY_TOOLS);
    // Every declared capability tool must be something this extension registers,
    // otherwise a spawn advertises an id nothing implements.
    const declaredButUnregistered = WORKER_CAPABILITY_TOOLS.filter((name) => !registeredTools.has(name));
    // With no contributed capability set, nothing beyond pi built-ins is grantable.
    const bareUnknown = unknownWorkerTools(["message", "read"], []);
    
    console.log(JSON.stringify({
      hasWorkerEvent,
      lifecycleEvents: [...subscriptions.keys()],
      unknownWithEvent,
      hasInResolved: resolvedTools.includes("message"),
      universeHasEvent: workerToolUniverse(WORKER_CAPABILITY_TOOLS).includes("message"),
      declaredButUnregistered,
      bareUnknown
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
    # The contributed set must name only tools this extension actually registers,
    # so no spawn can advertise an id nothing implements.
    assert data["declaredButUnregistered"] == []
    # With nothing contributed, the coordination tools are correctly ungrantable:
    # this is what keeps the execution layer honest when installed alone.
    assert data["bareUnknown"] == ["message"]


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

