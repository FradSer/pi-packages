"""Task naming at the persistence, worker, and assignment seams."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

PACKAGE = Path(__file__).resolve().parents[1]


def test_worker_binding_and_assignment_use_task_vocabulary(tmp_path: Path) -> None:
    env = {key: value for key, value in os.environ.items()
           if not key.startswith("PI_TEAMMATE_") and key not in {"PI_TASK_HOLDER", "PI_TEAM_STATE_DIR"}}
    env.update({"HOME": str(tmp_path), "PI_CODING_AGENT_DIR": str(tmp_path / "agent")})
    script = r'''
    import assert from "node:assert/strict";
    import * as tasks from "@fradser/pi-tasks";
    import { workerBinding } from "./src/worker.ts";
    Object.assign(process.env, {
      PI_TEAMMATE_WORKER_NAME: "fixture", PI_TEAMMATE_SPAWN_ID: "fixture-1",
      PI_TEAMMATE_OUTBOX_FILE: "/tmp/events", PI_TEAMMATE_INBOX_FILE: "/tmp/inbox",
      PI_TEAMMATE_ROSTER_FILE: "/tmp/roster", PI_TEAMMATE_TASKS_FILE: "/tmp/tasks.json",
      PI_TEAMMATE_CLAIMS_DIR: "/tmp/claims", PI_TEAMMATE_SUBMISSIONS_DIR: "/tmp/submissions",
    });
    const binding = workerBinding();
    assert.ok(binding, "Current task environment must activate the worker");
    assert.equal(binding.tasksFile, "/tmp/tasks.json");
    delete process.env.PI_TEAMMATE_TASKS_FILE;
    process.env.PI_TEAMMATE_BOARD_FILE = "/tmp/board.json";
    assert.equal(workerBinding(), undefined, "Retired environment must not activate a worker");
    let assignment;
    tasks.configureTaskStore({ get: () => ({name:"fixture",spawnId:"fixture-1",status:"idle"}),
      current: () => true, conflicting: () => undefined,
      sync: (_name, value) => { assignment=value; }, changed() {} });
    assert.equal(tasks.createTask({subject:"Task vocabulary"}).ok,true);
    assert.equal(tasks.takeTask("task-vocabulary","fixture").ok,true);
    assert.equal(assignment.kind,"task");
    assert.ok(assignment.id.startsWith("task:"));
    console.log(JSON.stringify({binding,assignment}));
    '''
    result = subprocess.run(["node", "--input-type=module", "--eval", script],
        cwd=PACKAGE, env=env, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    observed = json.loads(result.stdout)
    assert observed["assignment"]["kind"] == "task"
