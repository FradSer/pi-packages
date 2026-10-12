"""Real Pi lifecycle verification without model credentials or network calls."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

import pytest

from task_helpers import PACKAGE, REPO


@pytest.mark.parametrize("mode", ["recover", "ignore", "progress", "restore", "inspect-only", "content"])
def test_native_pi_delivers_task_state_and_bounds_continuation(tmp_path: Path, mode: str) -> None:
    agent_dir = tmp_path / "agent"
    agent_dir.mkdir()
    (agent_dir / "settings.json").write_text(json.dumps({
        "quietStartup": True, "extensions": [], "packages": [],
        "compaction": {"enabled": False}, "retry": {"enabled": False},
    }), encoding="utf-8")
    output = tmp_path / "events.jsonl"
    env = {
        key: value for key, value in os.environ.items()
        if not key.startswith("PI_TEAMMATE_")
        and key not in {"PI_TASK_HOLDER", "PI_TEAM_STATE_DIR", "PI_CODING_AGENT_SESSION_DIR"}
    }
    env.update({
        "PI_CODING_AGENT_DIR": str(agent_dir),
        "PI_TASK_TEST_MODE": mode,
        "PI_TASK_TEST_OUTPUT": str(output),
        "PI_TASK_TEST_WORK_DIR": str(tmp_path),
    })
    session_args: list[str] = []
    if mode in {"restore", "inspect-only"}:
        # Prepare a real saved session and its interrupted task, then let the
        # shipping extension restore it rather than seeding in-memory state.
        prepare = subprocess.run([
            "node", "--input-type=module", "--eval",
            f'''
            import {{ SessionManager }} from "@earendil-works/pi-coding-agent";
            import {{ tasksFilePath, writeTasksFile }} from {json.dumps((PACKAGE / "index.ts").as_uri())};
            const session = SessionManager.create({json.dumps(str(tmp_path))}, {json.dumps(str(tmp_path / "sessions"))});
            session.appendMessage({{ role: "user", content: "Implement the saved task", timestamp: Date.now() }});
            const sessionFile = session.getSessionFile();
            writeTasksFile(tasksFilePath(sessionFile, {json.dumps(str(tmp_path))}), {{
              "restored-task": {{
                id: "restored-task", subject: "Continue existing work", status: "in_progress", claimedBy: "main",
                dependsOn: [], resources: [], createdAt: 1, updatedAt: 1,
                result: "The interrupted attempt created a partial output",
              }},
            }});
            console.log(JSON.stringify({{ sessionFile }}));
            ''',
        ], cwd=REPO, env=env, capture_output=True, text=True, timeout=30)
        assert prepare.returncode == 0, prepare.stdout + prepare.stderr
        session_args = ["--session", json.loads(prepare.stdout)["sessionFile"]]
        (tmp_path / "first.txt").write_text("Interrupted task output\n", encoding="utf-8")
    run = subprocess.run([
        str(REPO / "node_modules/.bin/pi"), "--print", *session_args,
        "--provider", "tasks-stop-test", "--model", "scripted",
        "--no-extensions", "--no-skills", "--no-prompt-templates",
        "--extension", str(PACKAGE / "index.ts"),
        "--extension", str(PACKAGE / "tests/task-stop-live-fixture.ts"),
        "--tools", "create_task,get_task,list_tasks,update_task,read,write",
        "Complete the two tasks in dependency order.",
    ], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stdout + run.stderr
    # Headless output contract: `pi --print` prints the final assistant text.
    # ignore, progress, and inspect-only end with unfinished work, and their
    # last settlement used to append a passive task row, which printed nothing.
    assert run.stdout.strip(), "a run that ends with unfinished work still prints its final text"
    events = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    requests = [event for event in events if event["type"] == "request"]
    settlements = [event for event in events if event["type"] == "settled"]
    assert len(settlements) == 1, events
    settled = settlements[0]
    assert settled["failures"] == [], settled["failures"]
    assert len(settled["saved"]) == 1
    tasks = settled["saved"][0]["tasks"]
    if mode == "content":
        assert len(requests) == 15
        assert settled["reminders"] == []
        assert list(tasks) == ["content-prerequisite", "inspect-the-task-surface"]
        assert [item["status"] for item in tasks.values()] == ["completed", "completed"]
        edited = tasks["inspect-the-task-surface"]
        assert edited["subject"] == "Inspect the task content and confirm the collapsed row wraps"
        assert edited["description"] == "Inspect the current interaction.\nCheck the input handling and report failures."
        assert edited["dependsOn"] == ["content-prerequisite"]
        assert len(settled["taskReads"]) == 2
        assert settled["taskReads"][0]["task"]["blockedBy"] == ["content-prerequisite"]
        assert "blockedBy" not in settled["taskReads"][1]["task"]
        assert len(settled["taskLists"]) == 1
        assert all("description" not in item for item in settled["taskLists"][0]["tasks"])
        assert (tmp_path / "first.txt").read_text() == "First task implementation\n"
        assert (tmp_path / "second.txt").read_text() == "Dependent task implementation\n"
        return
    if mode in {"restore", "inspect-only"}:
        assert list(tasks) == ["restored-task"]
        assert requests[0]["reminders"] == 0
        assert settled["reminders"] == [], "blocked work must not trigger an automatic inspection turn"
        assert len(settled["taskReads"]) == 1
        observed = settled["taskReads"][0]["task"]
        assert observed["status"] == "blocked"
        assert "holder" not in observed
        if mode == "restore":
            assert len(requests) == 7
            assert tasks["restored-task"]["status"] == "completed"
            assert "Read the saved output" in tasks["restored-task"]["recoveryNote"]
            assert (tmp_path / "first.txt").read_text() == "Recovered task implementation\n"
            assert len(settled["reminders"]) == 0
        else:
            assert len(requests) == 3, "An unchanged recovery blocker receives only one continuation run"
            # Inspection is read-only. The saved pre-recovery attempt remains
            # unchanged until a task mutation persists the restored state.
            assert tasks["restored-task"]["status"] == "in_progress"
            assert tasks["restored-task"]["result"] == "The interrupted attempt created a partial output"
            assert (tmp_path / "first.txt").read_text() == "Interrupted task output\n"
        return
    assert len(tasks) == 2
    assert requests[3]["reminders"] == 0
    assert requests[4]["reminders"] == 1, "The reminder must reach the next real provider request"
    if mode == "recover":
        assert len(requests) == 12
        assert len(settled["reminders"]) == 1
        assert [tasks[id]["status"] for id in ["first-task", "second-task"]] == ["completed", "completed"]
        assert "blocked_by=first-task" in settled["reminders"][0]["content"]
        assert (tmp_path / "first.txt").read_text() == "First task implementation\n"
        assert (tmp_path / "second.txt").read_text() == "Dependent task implementation\n"
    else:
        assert [task["status"] for task in tasks.values()] == ["in_progress", "pending"]
        assert not (tmp_path / "first.txt").exists()
        assert not (tmp_path / "second.txt").exists()
        if mode == "ignore":
            assert len(requests) == 5, "An unchanged task snapshot receives only one continuation"
            # Only the continuation row reaches a headless transcript. The
            # waiting row is a transcript row for a session that has one; its
            # content contract lives in tests/test_task_stop_check.py.
            assert [item["details"]["status"] for item in settled["reminders"]] == ["continue"]
        else:
            assert len(requests) == 6, "Metadata edits do not buy another automatic turn"
            # Three continuation rows. The paused notice needs a transcript, so
            # headless settlement returns no result and the run prints instead.
            # The paused-row contract lives in tests/test_task_stop_check.py.
            assert [item["details"]["status"] for item in settled["reminders"]] == ["continue"]
