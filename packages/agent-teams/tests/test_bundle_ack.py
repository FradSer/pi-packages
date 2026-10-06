"""The native bundle smoke must be backed by a real correlated prompt receipt."""

from __future__ import annotations

import sys
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
REPO = PACKAGE.parents[1]
sys.path.insert(0, str(REPO / "tests" / "e2e" / "support"))
from harness import run_install  # noqa: E402


def test_bundle_kickoff_has_native_ack_and_all_session_controls(tmp_path: Path) -> None:
    run = run_install(tmp_path, ["agent-teams"], scenario="bundle", host="team")
    assert run.completed.returncode == 0, run.text
    started = run.calls_named("agent_start")[0]
    assert not started["isError"] and started["details"]["prompted"] is True
    # The intent family mints the roster name; the label is what a reader knows.
    assert started["details"]["session"].startswith("session:")
    assert started["details"]["label"] == "scout"
    assert started["details"]["grant"] == ["message", "task"]
    # The surfaces are the tool names this install registered: the intent family,
    # the mail tool, and the four task tools; there is no tool named `task`.
    assert set(run.surfaces()) >= {"agent_start", "agent_input", "agent_stop", "agent_list",
                                   "message", "create_task", "get_task", "list_tasks", "update_task"}
    assert run.live_children == [], "parent shutdown must close its child"
    spawn, = [event for event in run.rpc_events if event["type"] == "spawn"]
    assert "--no-session" in spawn["args"]
    commands = [event["command"] for event in run.rpc_events if event["type"] == "command" and event["pid"] == spawn["pid"]]
    kickoff = next(command for command in commands if command["type"] == "prompt" and "ROLE PROMPT" in command["message"])
    receipts = [event["response"] for event in run.rpc_events if event["type"] == "response" and event["pid"] == spawn["pid"]]
    accepted = next(receipt for receipt in receipts if receipt.get("id") == kickoff["id"])
    assert accepted["command"] == "prompt" and accepted["success"] is True
    assert accepted.get("data", {}).get("disposition") in {"started", "queued"}
    assert not any(command["type"] == "new_session" for command in commands)
    assert "@fradser/pi-agent-teams" not in str(spawn.get("bindings", {}))
