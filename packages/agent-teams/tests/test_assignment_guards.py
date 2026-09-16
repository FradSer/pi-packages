from __future__ import annotations

import json
import os
import subprocess
import textwrap
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
SRC = PACKAGE / "src"


def run_node(script: str) -> dict[str, object]:
    env = {key: value for key, value in os.environ.items() if not key.startswith("PI_TEAMMATE_")}
    result = subprocess.run(
        ["node", "--input-type=module", "--eval", textwrap.dedent(script)],
        cwd=PACKAGE,
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    return json.loads(result.stdout)


def test_handoff_requires_stopped_predecessor(tmp_path: Path) -> None:
    payload = run_node(
        f'''\
        import {{ initTeamMachine, shutdownTeamMachine, spawnTeammate }} from "{(SRC / "team-machine.ts").as_uri()}";
        import {{ resetState, registerTeammate, updateTeammate }} from "{(SRC / "state.ts").as_uri()}";
        initTeamMachine({{ sessionManager: undefined, cwd: {str(tmp_path)!r} }}, {{ sendUpdate: () => {{}}, notifyChange: () => {{}} }});
        resetState();
        registerTeammate({{ name: "old", agent: "reviewer", spawnId: "s1", pid: 1, status: "working", isolation: "none", createdAt: 1, updatedAt: 1 }});
        const live = spawnTeammate({{ name: "new", agent: "missing", handoffFrom: "old" }});
        updateTeammate("old", {{ status: "stopped" }});
        const stopped = spawnTeammate({{ name: "new", agent: "missing", handoffFrom: "old" }});
        console.log(JSON.stringify({{ live, stopped }}));
        shutdownTeamMachine();
        '''
    )
    assert payload["live"]["ok"] is False
    assert "living @old" in payload["live"]["error"]
    # Agent lookup happens after stopped-predecessor validation.
    assert payload["stopped"]["ok"] is False
    assert "Agent \"missing\"" in payload["stopped"]["error"]


def test_direct_assignment_blocks_board_claim_after_terminal_close() -> None:
    payload = run_node(
        f'''\
        import {{ resetState, registerTeammate, updateTeammate, assignTeammate, createTask, applyClaimIntent }} from "{(SRC / "state.ts").as_uri()}";
        resetState();
        registerTeammate({{ name: "writer", agent: "executor", spawnId: "s1", pid: 1, status: "idle", isolation: "none", createdAt: 1, updatedAt: 1 }});
        assignTeammate("writer", {{ id: "direct:s1", kind: "direct", resources: ["firmware/sub-node"], closed: true }});
        const task = createTask({{ subject: "old board work", resources: ["firmware/sub-node"] }}).task;
        const result = applyClaimIntent({{ taskId: task.id, worker: "writer", spawnId: "s1", timestamp: 1 }});
        console.log(JSON.stringify({{ applied: result.applied, reason: result.reason ?? "" }}));
        '''
    )
    assert payload["applied"] is False
    assert "closed pending leader reopen" in payload["reason"]


def test_resource_overlap_rejects_and_unrelated_resource_claims() -> None:
    payload = run_node(
        f'''\
        import {{ resetState, registerTeammate, assignTeammate, createTask, applyClaimIntent }} from "{(SRC / "state.ts").as_uri()}";
        resetState();
        registerTeammate({{ name: "main", agent: "executor", spawnId: "m1", pid: 1, status: "working", isolation: "none", createdAt: 1, updatedAt: 1 }});
        registerTeammate({{ name: "sub", agent: "executor", spawnId: "s1", pid: 2, status: "idle", isolation: "none", createdAt: 1, updatedAt: 1 }});
        assignTeammate("main", {{ id: "direct:m1", kind: "direct", resources: ["firmware/sub-node"] }});
        const nested = createTask({{ subject: "nested", resources: ["firmware/sub-node/app"] }}).task;
        const app = createTask({{ subject: "ios", resources: ["app/Hydra"] }}).task;
        const blocked = applyClaimIntent({{ taskId: nested.id, worker: "sub", spawnId: "s1", timestamp: 1 }});
        const free = applyClaimIntent({{ taskId: app.id, worker: "sub", spawnId: "s1", timestamp: 2 }});
        console.log(JSON.stringify({{ blocked, free }}));
        '''
    )
    assert payload["blocked"]["applied"] is False
    assert "resource conflict" in payload["blocked"]["reason"]
    assert payload["free"]["applied"] is True


def test_superseding_claimed_work_keeps_holder_locked_until_cancellation_acknowledgment() -> None:
    payload = run_node(
        f'''\
        import {{ resetState, registerTeammate, createTask, applyClaimIntent, applySubmissionIntent, getTask, getTeammate, completeTask }} from "{(SRC / "state.ts").as_uri()}";
        resetState();
        registerTeammate({{ name: "worker", agent: "executor", spawnId: "s1", pid: 1, status: "working", isolation: "none", createdAt: 1, updatedAt: 1 }});
        const old = createTask({{ subject: "obsolete" }}).task;
        applyClaimIntent({{ taskId: old.id, worker: "worker", spawnId: "s1", timestamp: 1 }});
        const holdingId = getTeammate("worker").assignment.id;
        const replacement = createTask({{ subject: "replacement", supersedes: [old.id] }});
        const cancellation = applySubmissionIntent({{ taskId: old.id, worker: "worker", spawnId: "s1", status: "failed", result: "stopped", timestamp: 2 }});
        console.log(JSON.stringify({{
          oldStatus: getTask(old.id)?.status,
          supersededBy: getTask(old.id)?.supersededBy,
          holderAssignment: getTeammate("worker")?.lastAssignment ?? null,
          holdingId,
          lastTaskId: getTeammate("worker")?.lastTaskId,
          assignmentAfterAck: getTeammate("worker")?.assignment ?? null,
          completeObsolete: completeTask(old.id, "late") ?? null,
          cancellation,
          replacementId: replacement.task.id,
        }}));
        '''
    )
    assert payload["oldStatus"] == "superseded"
    assert payload["supersededBy"] == payload["replacementId"]
    assert payload["holdingId"].startswith("board:")
    assert payload["holderAssignment"] == {"id": payload["holdingId"], "kind": "board", "resources": []}
    assert payload["lastTaskId"] == "obsolete"
    assert payload["assignmentAfterAck"] is None
    assert payload["completeObsolete"] is None
    assert payload["cancellation"] == {"ok": True}


def test_supersede_migrates_pending_downstream_dependencies() -> None:
    payload = run_node(
        f'''\
        import {{ resetState, createTask, getTask, completeTask }} from "{(SRC / "state.ts").as_uri()}";
        resetState();
        const old = createTask({{ subject: "old" }}).task;
        const downstream = createTask({{ subject: "downstream", dependsOn: [old.id] }}).task;
        const replacement = createTask({{ subject: "replacement", supersedes: [old.id] }}).task;
        const after = getTask(downstream.id);
        const invalid = createTask({{ subject: "self-cycle", dependsOn: [replacement.id], supersedes: [replacement.id] }});
        const postSupersede = createTask({{ subject: "later", dependsOn: [old.id] }}).task;
        const completeOld = createTask({{ subject: "complete-old" }}).task;
        getTask(completeOld.id).status = "completed";
        const completeDependent = createTask({{ subject: "complete-dependent", dependsOn: [completeOld.id] }}).task;
        const completedSupersede = createTask({{ subject: "illegal-completed-replacement", supersedes: [completeOld.id] }});
        const cycleOld = createTask({{ subject: "cycle-old" }}).task;
        const cycleDownstream = createTask({{ subject: "cycle-downstream", dependsOn: [cycleOld.id] }}).task;
        const cycle = createTask({{ subject: "cycle", dependsOn: [cycleDownstream.id], supersedes: [cycleOld.id] }});
        const chainA = createTask({{ subject: "chain-a" }}).task;
        const chainR1 = createTask({{ subject: "chain-r1", supersedes: [chainA.id] }}).task;
        const chainD = createTask({{ subject: "chain-d", dependsOn: [chainA.id] }}).task;
        const chainR2 = createTask({{ subject: "chain-r2", dependsOn: [chainD.id], supersedes: [chainA.id] }});
        getTask(chainR1.id).status = "completed";
        const chainR3 = createTask({{ subject: "chain-r3", supersedes: [chainA.id] }});
        console.log(JSON.stringify({{
          dependencies: after?.dependsOn,
          postSupersedeDependencies: getTask(postSupersede.id)?.dependsOn,
          invalidOk: invalid.ok,
          invalidError: invalid.ok ? "" : invalid.error,
          completedSupersedeOk: completedSupersede.ok,
          completedSupersedeError: completedSupersede.ok ? "" : completedSupersede.error,
          completedDependentDependencies: getTask(completeDependent.id)?.dependsOn,
          cycleOk: cycle.ok,
          cycleError: cycle.ok ? "" : cycle.error,
          chainR1: getTask(chainR1.id)?.status,
          chainDDependencies: getTask(chainD.id)?.dependsOn,
          chainR2Ok: chainR2.ok,
          chainR2Error: chainR2.ok ? "" : chainR2.error,
          chainR3Ok: chainR3.ok,
          chainR3Error: chainR3.ok ? "" : chainR3.error,
        }}));
        '''
    )
    assert payload["dependencies"] == ["replacement"]
    assert payload["postSupersedeDependencies"] == ["replacement"]
    assert payload["invalidOk"] is False
    assert "both depend on and supersede" in payload["invalidError"]
    assert payload["completedSupersedeOk"] is False
    assert "cannot supersede completed" in payload["completedSupersedeError"]
    assert payload["completedDependentDependencies"] == ["complete-old"]
    assert payload["cycleOk"] is False
    assert "dependency cycle" in payload["cycleError"]
    assert payload["chainR1"] == "completed"
    assert payload["chainDDependencies"] == ["chain-r1"]
    assert payload["chainR2Ok"] is False
    assert "dependency cycle" in payload["chainR2Error"]
    assert payload["chainR3Ok"] is False
    assert "cannot supersede completed" in payload["chainR3Error"]


def test_exported_submission_reducer_rejects_invalid_status() -> None:
    payload = run_node(
        f'''\
        import {{ resetState, registerTeammate, createTask, applyClaimIntent, applySubmissionIntent, getTask }} from "{(SRC / "state.ts").as_uri()}";
        resetState();
        registerTeammate({{ name: "w", agent: "executor", spawnId: "s1", pid: 1, status: "working", isolation: "none", createdAt: 1, updatedAt: 1 }});
        const task = createTask({{ subject: "task" }}).task;
        applyClaimIntent({{ taskId: task.id, worker: "w", spawnId: "s1", timestamp: 1 }});
        const result = applySubmissionIntent({{ taskId: task.id, worker: "w", spawnId: "s1", status: "bogus", timestamp: 2 }});
        console.log(JSON.stringify({{ result, status: getTask(task.id)?.status }}));
        '''
    )
    assert payload["result"]["ok"] is False
    assert "invalid submission status" in payload["result"]["error"]
    assert payload["status"] == "claimed"


def test_invalid_persisted_supersession_chain_rejects_new_dependency() -> None:
    payload = run_node(
        f'''\
        import {{ resetState, loadBoard, createTask }} from "{(SRC / "state.ts").as_uri()}";
        resetState();
        loadBoard({{ bad: {{ id: "bad", subject: "bad", dependsOn: [], resources: [], status: "superseded", createdAt: 1, updatedAt: 1 }} }});
        const created = createTask({{ subject: "dependent", dependsOn: ["bad"] }});
        console.log(JSON.stringify({{ ok: created.ok, error: created.ok ? "" : created.error }}));
        '''
    )
    assert payload["ok"] is False
    assert "invalid or cyclic" in payload["error"]


def test_submission_reducer_rejects_stale_same_name_spawn() -> None:
    payload = run_node(
        f'''\
        import {{ resetState, registerTeammate, updateTeammate, createTask, applyClaimIntent, applySubmissionIntent, getTask }} from "{(SRC / "state.ts").as_uri()}";
        resetState();
        registerTeammate({{ name: "w", agent: "executor", spawnId: "old", pid: 1, status: "working", isolation: "none", createdAt: 1, updatedAt: 1 }});
        const task = createTask({{ subject: "task" }}).task;
        applyClaimIntent({{ taskId: task.id, worker: "w", spawnId: "old", timestamp: 1 }});
        updateTeammate("w", {{ status: "stopped" }});
        // Release is simulated by a fresh task state after the old session dies.
        getTask(task.id).status = "pending";
        getTask(task.id).claimedBy = undefined;
        registerTeammate({{ name: "w", agent: "executor", spawnId: "new", pid: 2, status: "working", isolation: "none", createdAt: 2, updatedAt: 2 }});
        applyClaimIntent({{ taskId: task.id, worker: "w", spawnId: "new", timestamp: 2 }});
        const stale = applySubmissionIntent({{ taskId: task.id, worker: "w", spawnId: "old", status: "completed", timestamp: 3 }});
        console.log(JSON.stringify({{ stale, status: getTask(task.id)?.status, holder: getTask(task.id)?.claimedBy }}));
        '''
    )
    assert payload["stale"]["ok"] is False
    assert "not a living current incarnation" in payload["stale"]["error"]
    assert payload["status"] == "claimed"
    assert payload["holder"] == "w"


def test_resume_clears_dead_holder_from_superseded_task() -> None:
    payload = run_node(
        f'''\
        import {{ resetState, registerTeammate, createTask, applyClaimIntent, getTask, loadBoard }} from "{(SRC / "state.ts").as_uri()}";
        resetState();
        registerTeammate({{ name: "w", agent: "executor", spawnId: "s1", pid: 1, status: "working", isolation: "none", createdAt: 1, updatedAt: 1 }});
        const old = createTask({{ subject: "old", resources: ["firmware/sub-node"] }}).task;
        applyClaimIntent({{ taskId: old.id, worker: "w", spawnId: "s1", timestamp: 1 }});
        createTask({{ subject: "new", supersedes: [old.id] }});
        const persisted = {{ [old.id]: getTask(old.id) }};
        resetState();
        loadBoard(persisted);
        const restored = getTask(old.id);
        console.log(JSON.stringify({{ status: restored?.status, claimedBy: restored?.claimedBy ?? null, resources: restored?.resources ?? [] }}));
        '''
    )
    assert payload == {"status": "superseded", "claimedBy": None, "resources": ["firmware/sub-node"]}


def test_active_verify_rejects_replacement_submission(tmp_path: Path) -> None:
    payload = run_node(
        f'''\
        import {{ initTeamMachine, shutdownTeamMachine, attemptSubmission, processTaskIntents, setVerifyGateRunner }} from "{(SRC / "team-machine.ts").as_uri()}";
        import {{ resetState, registerTeammate, createTask, applyClaimIntent, getTask }} from "{(SRC / "state.ts").as_uri()}";
        initTeamMachine({{ sessionManager: undefined, cwd: {str(tmp_path)!r} }}, {{ sendUpdate: () => {{}}, notifyChange: () => {{}} }});
        resetState();
        registerTeammate({{ name: "w", agent: "reviewer", spawnId: "s1", pid: 1, status: "working", isolation: "none", createdAt: 1, updatedAt: 1 }});
        const task = createTask({{ subject: "gated", verify: "verify it" }}).task;
        applyClaimIntent({{ taskId: task.id, worker: "w", spawnId: "s1", timestamp: 1 }});
        let release;
        let calls = 0;
        setVerifyGateRunner(() => new Promise((resolve) => {{ calls++; release = () => resolve({{ kind: "pass" }}); }}));
        const pause = () => new Promise((resolve) => setTimeout(resolve, 15));
        attemptSubmission("w", "s1", task.id, "completed", "first");
        processTaskIntents();
        await pause();
        attemptSubmission("w", "s1", task.id, "completed", "replacement");
        processTaskIntents();
        await pause();
        const callsBeforeRelease = calls;
        release();
        await pause();
        console.log(JSON.stringify({{ callsBeforeRelease, finalStatus: getTask(task.id)?.status }}));
        shutdownTeamMachine();
        '''
    )
    assert payload == {"callsBeforeRelease": 1, "finalStatus": "completed"}


def test_reopen_cannot_replace_active_direct_assignment(tmp_path: Path) -> None:
    payload = run_node(
        f'''\
        import {{ initTeamMachine, shutdownTeamMachine, sendLeaderMessage }} from "{(SRC / "team-machine.ts").as_uri()}";
        import {{ resetState, registerTeammate, assignTeammate, getTeammate }} from "{(SRC / "state.ts").as_uri()}";
        initTeamMachine({{ sessionManager: undefined, cwd: {str(tmp_path)!r} }}, {{ sendUpdate: () => {{}}, notifyChange: () => {{}} }});
        resetState();
        registerTeammate({{ name: "w", agent: "executor", spawnId: "s1", pid: 1, status: "idle", isolation: "none", createdAt: 1, updatedAt: 1 }});
        assignTeammate("w", {{ id: "direct:s1", kind: "direct", resources: ["firmware/sub-node"] }});
        const result = sendLeaderMessage("w", "switch work", {{ reopen: true, resources: ["app/Hydra"] }});
        console.log(JSON.stringify({{ result, assignment: getTeammate("w")?.assignment }}));
        shutdownTeamMachine();
        '''
    )
    assert payload["result"]["ok"] is False
    assert "active direct assignment" in payload["result"]["error"]
    assert payload["assignment"] == {
        "id": "direct:s1",
        "kind": "direct",
        "resources": ["firmware/sub-node"],
    }


def test_inconclusive_verify_retries_once_for_each_submission(tmp_path: Path) -> None:
    payload = run_node(
        f'''\
        import {{ initTeamMachine, shutdownTeamMachine, attemptSubmission, processTaskIntents, setVerifyGateRunner }} from "{(SRC / "team-machine.ts").as_uri()}";
        import {{ resetState, registerTeammate, createTask, applyClaimIntent, getTask }} from "{(SRC / "state.ts").as_uri()}";
        initTeamMachine({{ sessionManager: undefined, cwd: {str(tmp_path)!r} }}, {{ sendUpdate: () => {{}}, notifyChange: () => {{}} }});
        resetState();
        registerTeammate({{ name: "w", agent: "reviewer", spawnId: "s1", pid: 1, status: "working", isolation: "none", createdAt: 1, updatedAt: 1 }});
        const task = createTask({{ subject: "gated", verify: "verify it" }}).task;
        applyClaimIntent({{ taskId: task.id, worker: "w", spawnId: "s1", timestamp: 1 }});
        const outcomes = [
          {{ kind: "inconclusive", detail: "missing one" }},
          {{ kind: "fail", detail: "real finding" }},
          {{ kind: "inconclusive", detail: "missing two" }},
          {{ kind: "pass" }},
        ];
        let calls = 0;
        setVerifyGateRunner(async () => outcomes[calls++]);
        const pause = () => new Promise((resolve) => setTimeout(resolve, 15));
        attemptSubmission("w", "s1", task.id, "completed", "first");
        processTaskIntents();
        await pause();
        await pause();
        const stillClaimedAfterExplicitFail = getTask(task.id)?.status === "claimed";
        attemptSubmission("w", "s1", task.id, "completed", "second");
        processTaskIntents();
        await pause();
        await pause();
        console.log(JSON.stringify({{ calls, stillClaimedAfterExplicitFail, finalStatus: getTask(task.id)?.status }}));
        shutdownTeamMachine();
        '''
    )
    assert payload == {
        "calls": 4,
        "stillClaimedAfterExplicitFail": True,
        "finalStatus": "completed",
    }


def test_task_intent_requires_nonempty_identity_and_finite_timestamp() -> None:
    payload = run_node(
        f'''\
        import {{ takeTaskIntent }} from "{(SRC / "statefile.ts").as_uri()}";
        import fs from "node:fs";
        import os from "node:os";
        import path from "node:path";
        const dir = fs.mkdtempSync(path.join(os.tmpdir(), "agent-teams-invalid-identity-"));
        const records = [
          {{ taskId: "", worker: "w", spawnId: "s", timestamp: 1 }},
          {{ taskId: "t", worker: "", spawnId: "s", timestamp: 1 }},
          {{ taskId: "t", worker: "w", spawnId: "", timestamp: 1 }},
          {{ taskId: "t", worker: "w", spawnId: "s", timestamp: "bad" }},
          {{ taskId: "t", worker: "w", spawnId: "s", timestamp: 1, result: 42 }},
        ];
        records.forEach((record, index) => fs.writeFileSync(path.join(dir, `${{index}}.json`), JSON.stringify(record)));
        const diagnostics = records.map(() => takeTaskIntent(dir).diagnostic ?? "");
        console.log(JSON.stringify({{ diagnostics }}));
        '''
    )
    assert all("malformed task intent" in item for item in payload["diagnostics"])


def test_invalid_submission_status_is_consumed_before_state_machine() -> None:
    payload = run_node(
        f'''\
        import {{ takeTaskIntent }} from "{(SRC / "statefile.ts").as_uri()}";
        import fs from "node:fs";
        import os from "node:os";
        import path from "node:path";
        const dir = fs.mkdtempSync(path.join(os.tmpdir(), "agent-teams-invalid-submit-"));
        fs.writeFileSync(path.join(dir, "bad.json"), JSON.stringify({{ taskId: "t", worker: "w", spawnId: "s", status: "bogus", timestamp: 1 }}));
        const result = takeTaskIntent(dir);
        console.log(JSON.stringify({{ intent: result.intent ?? null, diagnostic: result.diagnostic ?? "" }}));
        '''
    )
    assert payload["intent"] is None
    assert "invalid submission status" in payload["diagnostic"]


def test_two_explicit_verify_failures_park_until_leader_steer(tmp_path: Path) -> None:
    payload = run_node(
        f'''\
        import {{ initTeamMachine, shutdownTeamMachine, attemptSubmission, processTaskIntents, setVerifyGateRunner, sendLeaderMessage }} from "{(SRC / "team-machine.ts").as_uri()}";
        import {{ resetState, registerTeammate, createTask, applyClaimIntent, getTask }} from "{(SRC / "state.ts").as_uri()}";
        initTeamMachine({{ sessionManager: undefined, cwd: {str(tmp_path)!r} }}, {{ sendUpdate: () => {{}}, notifyChange: () => {{}} }});
        resetState();
        registerTeammate({{ name: "w", agent: "reviewer", spawnId: "s1", pid: 1, status: "working", isolation: "none", createdAt: 1, updatedAt: 1 }});
        const task = createTask({{ subject: "gated", verify: "verify it" }}).task;
        applyClaimIntent({{ taskId: task.id, worker: "w", spawnId: "s1", timestamp: 1 }});
        const outcomes = [{{ kind: "fail", detail: "one" }}, {{ kind: "fail", detail: "two" }}, {{ kind: "pass" }}];
        let calls = 0;
        setVerifyGateRunner(async () => outcomes[calls++]);
        const pause = () => new Promise((resolve) => setTimeout(resolve, 15));
        attemptSubmission("w", "s1", task.id, "completed", "first");
        processTaskIntents();
        await pause();
        attemptSubmission("w", "s1", task.id, "completed", "second");
        processTaskIntents();
        await pause();
        attemptSubmission("w", "s1", task.id, "completed", "blocked");
        processTaskIntents();
        await pause();
        const callsWhileParked = calls;
        const steer = sendLeaderMessage("w", "Leader direction: fix the finding and resubmit.");
        attemptSubmission("w", "s1", task.id, "completed", "after-steer");
        processTaskIntents();
        await pause();
        console.log(JSON.stringify({{ callsWhileParked, steer: steer.ok, finalStatus: getTask(task.id)?.status, calls }}));
        shutdownTeamMachine();
        '''
    )
    assert payload == {"callsWhileParked": 2, "steer": True, "finalStatus": "completed", "calls": 3}


def test_twice_inconclusive_park_requires_leader_steer_before_resubmit(tmp_path: Path) -> None:
    payload = run_node(
        f'''\
        import {{ initTeamMachine, shutdownTeamMachine, attemptSubmission, processTaskIntents, setVerifyGateRunner, sendLeaderMessage }} from "{(SRC / "team-machine.ts").as_uri()}";
        import {{ resetState, registerTeammate, updateTeammate, createTask, applyClaimIntent, getTask }} from "{(SRC / "state.ts").as_uri()}";
        initTeamMachine({{ sessionManager: undefined, cwd: {str(tmp_path)!r} }}, {{ sendUpdate: () => {{}}, notifyChange: () => {{}} }});
        resetState();
        registerTeammate({{ name: "w", agent: "reviewer", spawnId: "s1", pid: 1, status: "working", isolation: "none", createdAt: 1, updatedAt: 1 }});
        const task = createTask({{ subject: "gated", verify: "verify it" }}).task;
        applyClaimIntent({{ taskId: task.id, worker: "w", spawnId: "s1", timestamp: 1 }});
        const outcomes = [{{ kind: "inconclusive", detail: "one" }}, {{ kind: "inconclusive", detail: "two" }}, {{ kind: "pass" }}];
        let calls = 0;
        setVerifyGateRunner(async () => outcomes[calls++]);
        const pause = () => new Promise((resolve) => setTimeout(resolve, 15));
        attemptSubmission("w", "s1", task.id, "completed", "first");
        processTaskIntents();
        await pause();
        await pause();
        attemptSubmission("w", "s1", task.id, "completed", "blocked");
        processTaskIntents();
        await pause();
        const callsWhileParked = calls;
        const rejectedReopen = sendLeaderMessage("w", "wrong reopen", {{ reopen: true }});
        attemptSubmission("w", "s1", task.id, "completed", "still-blocked");
        processTaskIntents();
        await pause();
        const callsAfterRejectedReopen = calls;
        // The holder now reports terminally, but its board task remains active.
        updateTeammate("w", {{ reportSequenceEnded: true }});
        const terminalSteer = sendLeaderMessage("w", "terminal board holder: revise and resubmit");
        attemptSubmission("w", "s1", task.id, "completed", "after-steer");
        processTaskIntents();
        await pause();
        console.log(JSON.stringify({{ callsWhileParked, rejectedReopen: rejectedReopen.ok, callsAfterRejectedReopen, terminalSteer: terminalSteer.ok, finalStatus: getTask(task.id)?.status, calls }}));
        shutdownTeamMachine();
        '''
    )
    assert payload == {
        "callsWhileParked": 2,
        "rejectedReopen": False,
        "callsAfterRejectedReopen": 2,
        "terminalSteer": True,
        "finalStatus": "completed",
        "calls": 3,
    }


def test_missing_verdict_is_inconclusive() -> None:
    payload = run_node(
        f'''\
        import {{ parseVerifyVerdict }} from "{(SRC / "team-machine.ts").as_uri()}";
        console.log(JSON.stringify({{
          missing: parseVerifyVerdict("The diff looks good."),
          pass: parseVerifyVerdict("VERDICT: PASS"),
          fail: parseVerifyVerdict("VERDICT: FAIL - regression"),
        }}));
        '''
    )
    assert payload["missing"]["kind"] == "inconclusive"
    assert payload["pass"] == {"kind": "pass"}
    assert payload["fail"] == {"kind": "fail", "detail": "regression"}


def test_successor_handoff_uses_archived_assignment_and_reports() -> None:
    payload = run_node(
        f'''\
        import {{ resetState, registerTeammate, assignTeammate, receiveWorkerMessage }} from "{(SRC / "state.ts").as_uri()}";
        import {{ buildSuccessorHandoff, directAssignment, resolveDirectResources }} from "{(SRC / "team-machine.ts").as_uri()}";
        resetState();
        registerTeammate({{ name: "stalled", agent: "executor", spawnId: "s1", pid: 1, status: "stopped", isolation: "none", createdAt: 1, updatedAt: 1 }});
        assignTeammate("stalled", {{ id: "direct:s1", kind: "direct", resources: ["firmware/sub-node"] }}, "old-task");
        assignTeammate("stalled", undefined, undefined);
        receiveWorkerMessage({{ id: "r1", type: "message", worker: "stalled", spawnId: "s1", body: "Found the radio recovery defect", status: "in_progress" }});
        const handoff = buildSuccessorHandoff(undefined, "stalled") ?? "";
        const successor = directAssignment(handoff, resolveDirectResources(undefined, "stalled"), "s2");
        console.log(JSON.stringify({{ handoff, successor }}));
        '''
    )
    assert "SUCCESSOR HANDOFF FROM @stalled" in payload["handoff"]
    assert "direct direct:s1" in payload["handoff"]
    assert "old-task" in payload["handoff"]
    assert "radio recovery defect" in payload["handoff"]
    assert payload["successor"] == {
        "id": "direct:s2",
        "kind": "direct",
        "resources": ["firmware/sub-node"],
    }


def test_fresh_reset_requires_the_emitting_child_and_is_single_flight() -> None:
    payload = run_node(
        f'''\
        import childProcess from "node:child_process";
        import {{ EventEmitter }} from "node:events";
        import {{ syncBuiltinESMExports }} from "node:module";
        import {{ PassThrough, Writable }} from "node:stream";
        import {{ mock }} from "node:test";
        const commands = new Map();
        const children = [];
        mock.method(childProcess, "spawn", () => {{
          const child = Object.assign(new EventEmitter(), {{
            pid: children.length + 1,
            stdout: new PassThrough(),
            stderr: new PassThrough(),
          }});
          const writes = [];
          child.stdin = new Writable({{ write(chunk, _encoding, done) {{ writes.push(JSON.parse(String(chunk))); done(); }} }});
          commands.set(child, writes);
          children.push(child);
          return child;
        }});
        syncBuiltinESMExports();
        const {{ deliverFreshAssignment, spawnResident }} = await import("{(SRC / "spawner.ts").as_uri()}");
        spawnResident({{ workerName: "pending", onUpdate: () => {{}}, onExit: () => {{}} }});
        spawnResident({{ workerName: "other", onUpdate: () => {{}}, onExit: () => {{}} }});
        const promise = deliverFreshAssignment("pending", "new assignment");
        children[0].stdout.write(`${{JSON.stringify({{ type: "agent_settled" }})}}\\n${{JSON.stringify({{ type: "agent_settled" }})}}\\n`);
        const reset = commands.get(children[0]).find((command) => command.type === "new_session");
        children[1].stdout.write(JSON.stringify({{ id: reset.id, type: "response", command: "new_session", success: true, data: {{ cancelled: false }} }}) + "\\n");
        await new Promise((resolve) => setImmediate(resolve));
        const promptsAfterWrongChild = commands.get(children[0]).filter((command) => command.type === "prompt").length;
        children[0].stdout.write(JSON.stringify({{ id: reset.id, type: "response", command: "new_session", success: true, data: {{ cancelled: false }} }}) + "\\n");
        const success = await promise;
        const own = commands.get(children[0]);
        console.log(JSON.stringify({{
          resetCount: own.filter((command) => command.type === "new_session").length,
          promptCount: own.filter((command) => command.type === "prompt").length,
          promptsAfterWrongChild,
          success,
        }}));
        children.forEach((child) => child.emit("close", 0, null));
        mock.restoreAll();
        ''',
    )
    assert payload == {
        "resetCount": 1,
        "promptCount": 1,
        "promptsAfterWrongChild": 0,
        "success": True,
    }


def test_rejected_cancelled_timed_out_and_closed_fresh_resets_never_prompt_old_session() -> None:
    payload = run_node(
        f'''\
        import childProcess from "node:child_process";
        import {{ EventEmitter }} from "node:events";
        import {{ syncBuiltinESMExports }} from "node:module";
        import {{ PassThrough, Writable }} from "node:stream";
        import {{ mock }} from "node:test";
        mock.timers.enable({{ apis: ["setTimeout"] }});
        const children = [];
        mock.method(childProcess, "spawn", () => {{
          const child = Object.assign(new EventEmitter(), {{
            pid: children.length + 1,
            stdout: new PassThrough(),
            stderr: new PassThrough(),
          }});
          child.commands = [];
          child.stdin = new Writable({{ write(chunk, _encoding, done) {{ child.commands.push(JSON.parse(String(chunk))); done(); }} }});
          children.push(child);
          return child;
        }});
        syncBuiltinESMExports();
        const {{ deliverFreshAssignment, sendWorkerSteer, spawnResident }} = await import("{(SRC / "spawner.ts").as_uri()}");
        const outcomes = [];
        for (const mode of ["rejected", "cancelled", "timed-out", "closed"]) {{
          spawnResident({{ workerName: mode, onUpdate: () => {{}}, onExit: () => {{}} }});
          const child = children.at(-1);
          const promise = deliverFreshAssignment(mode, `${{mode}} assignment`);
          child.stdout.write(JSON.stringify({{ type: "agent_settled" }}) + "\\n");
          const reset = child.commands.find((command) => command.type === "new_session");
          const guidanceAccepted = sendWorkerSteer(mode, `${{mode}} guidance`);
          if (mode === "closed") child.emit("close", 1, null);
          else if (mode === "timed-out") mock.timers.tick(5_000);
          else child.stdout.write(JSON.stringify({{
            id: reset.id,
            type: "response",
            command: "new_session",
            success: mode !== "rejected",
            data: {{ cancelled: mode === "cancelled" }},
            error: mode === "rejected" ? "reset rejected" : undefined,
          }}) + "\\n");
          outcomes.push({{
            mode,
            success: await promise,
            guidanceAccepted,
            resetCount: child.commands.filter((command) => command.type === "new_session").length,
            promptCount: child.commands.filter((command) => command.type === "prompt").length,
          }});
        }}
        console.log(JSON.stringify({{ outcomes }}));
        mock.timers.reset();
        mock.restoreAll();
        ''',
    )
    assert payload["outcomes"] == [
        {"mode": "rejected", "success": False, "guidanceAccepted": True, "resetCount": 1, "promptCount": 0},
        {"mode": "cancelled", "success": False, "guidanceAccepted": True, "resetCount": 1, "promptCount": 0},
        {"mode": "timed-out", "success": False, "guidanceAccepted": True, "resetCount": 1, "promptCount": 0},
        {"mode": "closed", "success": False, "guidanceAccepted": True, "resetCount": 1, "promptCount": 0},
    ]


def test_fresh_reset_failure_releases_work_without_delivering_queued_guidance(tmp_path: Path) -> None:
    payload = run_node(
        f'''\
        import childProcess from "node:child_process";
        import {{ EventEmitter }} from "node:events";
        import {{ syncBuiltinESMExports }} from "node:module";
        import {{ PassThrough, Writable }} from "node:stream";
        import {{ mock }} from "node:test";
        mock.timers.enable({{ apis: ["setTimeout"] }});
        const children = [];
        mock.method(childProcess, "spawn", () => {{
          const child = Object.assign(new EventEmitter(), {{
            pid: children.length + 1,
            stdout: new PassThrough(),
            stderr: new PassThrough(),
          }});
          child.commands = [];
          child.stdin = new Writable({{ write(chunk, _encoding, done) {{ child.commands.push(JSON.parse(String(chunk))); done(); }} }});
          children.push(child);
          return child;
        }});
        syncBuiltinESMExports();
        const {{ spawnResident }} = await import("{(SRC / "spawner.ts").as_uri()}");
        const {{ initTeamMachine, sendLeaderMessage, shutdownTeamMachine }} = await import("{(SRC / "team-machine.ts").as_uri()}");
        const {{ getTask, getTeammate, registerTeammate, resetState }} = await import("{(SRC / "state.ts").as_uri()}");
        const cwd = {str(tmp_path)!r};
        initTeamMachine({{ sessionManager: undefined, cwd }}, {{ sendUpdate: () => {{}}, notifyChange: () => {{}} }});
        resetState();
        const outcomes = [];
        for (const mode of ["rejected", "cancelled", "timed-out", "closed"]) {{
          const name = `worker-${{mode}}`;
          const workId = `work-${{mode}}`;
          spawnResident({{ workerName: name, onUpdate: () => {{}}, onExit: () => {{}} }});
          const child = children.at(-1);
          registerTeammate({{ name, agent: "reviewer", spawnId: `spawn-${{mode}}`, workId, pid: child.pid, status: "idle", isolation: "none", createdAt: 1, updatedAt: 1 }});
          const opened = sendLeaderMessage(name, `${{mode}} assignment`);
          child.stdout.write(JSON.stringify({{ type: "agent_settled" }}) + "\\n");
          const reset = child.commands.find((command) => command.type === "new_session");
          const guidance = sendLeaderMessage(name, `${{mode}} same-attempt guidance`);
          if (mode === "closed") child.emit("close", 1, null);
          else if (mode === "timed-out") mock.timers.tick(5_000);
          else child.stdout.write(JSON.stringify({{
            id: reset.id,
            type: "response",
            command: "new_session",
            success: mode !== "rejected",
            data: {{ cancelled: mode === "cancelled" }},
            error: mode === "rejected" ? "reset rejected" : undefined,
          }}) + "\\n");
          await new Promise((resolve) => setImmediate(resolve));
          outcomes.push({{
            mode,
            opened: opened.ok,
            guidance: guidance.ok ? guidance.outcome : "rejected",
            taskStatus: getTask(workId)?.status,
            taskError: getTask(workId)?.errorMessage,
            assignmentReleased: getTeammate(name)?.assignment === undefined,
            promptCount: child.commands.filter((command) => command.type === "prompt").length,
          }});
        }}
        shutdownTeamMachine();
        children.forEach((child) => child.emit("close", 0, null));
        mock.timers.reset();
        mock.restoreAll();
        console.log(JSON.stringify({{ outcomes }}));
        ''',
    )
    for outcome in payload["outcomes"]:
        assert outcome == {
            "mode": outcome["mode"],
            "opened": True,
            "guidance": "steered",
            "taskStatus": "pending",
            "taskError": "Pi session reset failed before the new Assignment Attempt started.",
            "assignmentReleased": True,
            "promptCount": 0,
        }


def test_unexpected_owner_execution_requires_a_fresh_session_before_recovery(tmp_path: Path) -> None:
    payload = run_node(
        f'''\
        import childProcess from "node:child_process";
        import {{ EventEmitter }} from "node:events";
        import {{ syncBuiltinESMExports }} from "node:module";
        import {{ PassThrough, Writable }} from "node:stream";
        import {{ mock }} from "node:test";
        const commands = [];
        const child = Object.assign(new EventEmitter(), {{
          pid: 1,
          stdout: new PassThrough(),
          stderr: new PassThrough(),
          stdin: new Writable({{ write(chunk, _encoding, done) {{ commands.push(JSON.parse(String(chunk))); done(); }} }}),
        }});
        mock.method(childProcess, "spawn", () => child);
        syncBuiltinESMExports();
        const {{ spawnResident }} = await import("{(SRC / "spawner.ts").as_uri()}");
        const {{ applyProgress, initTeamMachine, shutdownTeamMachine, attemptSubmission, processTaskIntents, sendLeaderMessage, setVerifyGateRunner }} = await import("{(SRC / "team-machine.ts").as_uri()}");
        const {{ resetState, registerTeammate, createDirectWork, getTask, getTeammate }} = await import("{(SRC / "state.ts").as_uri()}");
        spawnResident({{ workerName: "w", onUpdate: () => {{}}, onExit: () => {{}} }});
        initTeamMachine({{ sessionManager: undefined, cwd: {str(tmp_path)!r} }}, {{ sendUpdate: () => {{}}, notifyChange: () => {{}} }});
        resetState();
        registerTeammate({{ name: "w", agent: "reviewer", spawnId: "s1", pid: 1, status: "working", isolation: "none", createdAt: 1, updatedAt: 1 }});
        const taskId = "direct-work";
        createDirectWork({{ id: taskId, subject: "gated", resources: ["firmware/direct"], verify: "verify", workerName: "w", assignment: {{ id: "direct:s1", kind: "direct", resources: ["firmware/direct"] }} }});
        let release;
        setVerifyGateRunner(() => new Promise((resolve) => {{ release = () => resolve({{ kind: "pass" }}); }}));
        attemptSubmission("w", "s1", taskId, "completed", "result");
        processTaskIntents();
        await new Promise((resolve) => setImmediate(resolve));
        applyProgress("w", "s1", {{ text: "new execution", turns: 2, finalResponse: false }});
        const firstAttempt = getTeammate("w")?.assignment?.id;
        const recovery = sendLeaderMessage("w", "Recover invalidated review", {{ reopen: true, workId: taskId }});
        const nextAttempt = getTeammate("w")?.assignment?.id;
        child.stdout.write(JSON.stringify({{ type: "agent_settled" }}) + "\\n");
        await new Promise((resolve) => setImmediate(resolve));
        const reset = commands.find((command) => command.type === "new_session");
        child.stdout.write(JSON.stringify({{ id: reset.id, type: "response", command: "new_session", success: true, data: {{ cancelled: false }} }}) + "\\n");
        await new Promise((resolve) => setImmediate(resolve));
        release();
        await new Promise((resolve) => setImmediate(resolve));
        setVerifyGateRunner(undefined);
        const payload = {{ status: getTask(taskId)?.status, recovery: recovery.ok, resources: getTeammate("w")?.assignment?.resources, freshAttempt: nextAttempt !== firstAttempt, reset: Boolean(reset) }};
        shutdownTeamMachine();
        child.emit("close", 0, null);
        mock.restoreAll();
        console.log(JSON.stringify(payload));
        ''',
    )
    assert payload == {"status": "claimed", "recovery": True, "resources": ["firmware/direct"], "freshAttempt": True, "reset": True}


def test_superseded_direct_holder_retains_resources_until_cancellation_acknowledgement(tmp_path: Path) -> None:
    payload = run_node(
        f'''\
        import {{ initTeamMachine, shutdownTeamMachine, createBoardTask }} from "{(SRC / "team-machine.ts").as_uri()}";
        import {{ resetState, registerTeammate, createDirectWork, activeAssignmentConflict, updateTeammate }} from "{(SRC / "state.ts").as_uri()}";
        initTeamMachine({{ sessionManager: undefined, cwd: {str(tmp_path)!r} }}, {{ sendUpdate: () => {{}}, notifyChange: () => {{}} }});
        resetState();
        registerTeammate({{ name: "direct", agent: "reviewer", spawnId: "s1", pid: 1, status: "working", isolation: "none", createdAt: 1, updatedAt: 1 }});
        const bound = createDirectWork({{ id: "direct-work", subject: "direct", resources: ["firmware/gated"], workerName: "direct", assignment: {{ id: "direct:s1", kind: "direct", resources: ["firmware/gated"] }} }});
        updateTeammate("direct", {{ assignment: {{ id: "direct:s1", kind: "direct", resources: ["firmware/gated"], closed: true }} }});
        const replacement = createBoardTask({{ subject: "replacement", resources: ["firmware/gated"], supersedes: ["direct-work"] }});
        const conflict = activeAssignmentConflict(["firmware/gated/subdir"]);
        shutdownTeamMachine();
        console.log(JSON.stringify({{ bound: bound.ok, replacement: replacement.ok, conflict: conflict?.name ?? null }}));
        ''',
    )
    assert payload == {"bound": True, "replacement": True, "conflict": "direct"}


def test_superseding_a_verifying_holder_routes_cancellation_without_waiting_for_gate(tmp_path: Path) -> None:
    payload = run_node(
        f'''\
        import {{ initTeamMachine, shutdownTeamMachine, createBoardTask, attemptSubmission, processTaskIntents, routePeerInboxes, setVerifyGateRunner }} from "{(SRC / "team-machine.ts").as_uri()}";
        import {{ resetState, registerTeammate, createTask, applyClaimIntent }} from "{(SRC / "state.ts").as_uri()}";
        import {{ inboxPath, stateFilePath, readJsonlBatch }} from "{(SRC / "statefile.ts").as_uri()}";
        const root = {str(tmp_path)!r};
        initTeamMachine({{ sessionManager: undefined, cwd: root }}, {{ sendUpdate: () => {{}}, notifyChange: () => {{}} }});
        resetState();
        registerTeammate({{ name: "w", agent: "reviewer", spawnId: "s1", pid: 1, status: "idle", isolation: "none", createdAt: 1, updatedAt: 1 }});
        const old = createTask({{ subject: "old", verify: "verify" }}).task;
        applyClaimIntent({{ taskId: old.id, worker: "w", spawnId: "s1", timestamp: 1 }});
        let release;
        setVerifyGateRunner(() => new Promise((resolve) => {{ release = () => resolve({{ kind: "pass" }}); }}));
        attemptSubmission("w", "s1", old.id, "completed", "result");
        processTaskIntents();
        await new Promise((resolve) => setImmediate(resolve));
        const replacement = createBoardTask({{ subject: "replacement", supersedes: [old.id] }});
        routePeerInboxes();
        const messages = readJsonlBatch(inboxPath(stateFilePath(undefined, root), "w"), 0).records;
        release();
        await new Promise((resolve) => setImmediate(resolve));
        setVerifyGateRunner(undefined);
        shutdownTeamMachine();
        console.log(JSON.stringify({{ replacementOk: replacement.ok, cancellationRouted: messages.some((entry) => entry.subject === `Task superseded: ${{old.id}}`) }}));
        ''',
    )
    assert payload == {"replacementOk": True, "cancellationRouted": True}
