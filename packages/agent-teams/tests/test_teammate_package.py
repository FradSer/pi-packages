from __future__ import annotations

import json
import os
import subprocess
import tempfile
import textwrap
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
SRC = PACKAGE / "src"

LEADER_TOOLS = {
    "agent",
    "agent_event",
    "work",
}
WORKER_TOOLS = {
    "agent_event",
    "work",
}
REMOVED_TOOLS = {
    "teammate_message",
    "teammate_run",
    "teammate_fanout",
    "teammate_cancel",
    "teammate_retry",
    "teammate_status",
    "teammate_register",
    "teammate_broadcast",
    "teammate_create_task",
    "teammate_start_task",
    "teammate_wait",
}


def source(name: str) -> str:
    return (SRC / name).read_text(encoding="utf-8")


def run_node(script: str, *args: str, env_overrides: dict[str, str] | None = None) -> dict[str, object]:
    env = {key: value for key, value in os.environ.items() if not key.startswith("PI_TEAMMATE_")}
    env.update(env_overrides or {})
    result = subprocess.run(
        ["node", "--input-type=module", "--eval", textwrap.dedent(script), *args],
        cwd=PACKAGE,
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    return json.loads(result.stdout)


def agent_dir_env(tmp: Path) -> dict[str, str]:
    return {"PI_CODING_AGENT_DIR": str(tmp)}


def test_manifest_declares_native_extension_package() -> None:
    manifest = json.loads((PACKAGE / "package.json").read_text(encoding="utf-8"))
    assert manifest["name"] == "@fradser/pi-agent-teams"
    assert "pi-package" in manifest["keywords"]
    assert manifest["pi"] == {"extensions": ["./index.ts"]}
    assert "skills" not in manifest["files"]
    assert "references" in manifest["files"] and not (PACKAGE / "agents").exists()


def test_leader_tool_surface_is_exact() -> None:
    ext = source("index.ts") + source("tools.ts") + source("worker.ts")
    for tool in LEADER_TOOLS:
        assert f'name: "{tool}"' in ext, tool
    for tool in REMOVED_TOOLS:
        assert f'name: "{tool}"' not in ext, tool
    assert source("tools.ts").count('name: "task_list"') == 0
    assert source("worker.ts").count('name: "task_list"') == 0


def test_worker_surface_is_capability_bound() -> None:
    worker = source("worker.ts")
    for tool in WORKER_TOOLS:
        assert f'name: "{tool}"' in worker, tool
    # Worker capabilities bind through environment, never runtime registration.
    assert "PI_TEAMMATE_WORKER_NAME" in worker
    assert "PI_TEAMMATE_CLAIMS_DIR" in worker
    for tool in LEADER_TOOLS - WORKER_TOOLS:
        assert f'name: "{tool}"' not in worker


def test_worker_claim_uses_exclusive_create_marker_files() -> None:
    worker = source("worker.ts")
    assert "createTaskIntent" in worker
    payload = run_node(
        f'''\
        import {{ createTaskIntent, takeTaskIntent }} from "{(SRC / "statefile.ts").as_uri()}";
        import fs from "node:fs";
        import os from "node:os";
        import path from "node:path";
        const dir = fs.mkdtempSync(path.join(os.tmpdir(), "agent-teams-intents-"));
        const intent = {{ taskId: "t_1", worker: "security", spawnId: "s1", timestamp: 1 }};
        const won = createTaskIntent(dir, "t_1", intent);
        const lost = createTaskIntent(dir, "t_1", {{ ...intent, worker: "backend" }});
        const drained = takeTaskIntent(dir);
        const next = takeTaskIntent(dir);
        console.log(JSON.stringify({{
          won,
          lost,
          drainedWorker: drained?.intent?.worker ?? null,
          boardEmptyAgain: next.intent === undefined && next.diagnostic === undefined,
        }}));
        '''
    )
    assert payload["won"] is True
    assert payload["lost"] is False
    assert payload["drainedWorker"] == "security"
    assert payload["boardEmptyAgain"] is True


def test_take_task_intent_skips_malformed_records() -> None:
    payload = run_node(
        f'''\
        import {{ takeTaskIntent }} from "{(SRC / "statefile.ts").as_uri()}";
        import fs from "node:fs";
        import os from "node:os";
        import path from "node:path";
        const dir = fs.mkdtempSync(path.join(os.tmpdir(), "agent-teams-badintents-"));
        fs.writeFileSync(path.join(dir, "a-broken.json"), "{{ not json");
        fs.writeFileSync(path.join(dir, "b-good.json"), JSON.stringify({{ taskId: "t_2", worker: "tests", spawnId: "s", timestamp: 2 }}));
        const first = takeTaskIntent(dir);
        const second = takeTaskIntent(dir);
        const third = takeTaskIntent(dir);
        console.log(JSON.stringify({{
          firstWasDiagnostic: typeof first.diagnostic === "string" && first.intent === undefined,
          goodWorker: second?.intent?.worker ?? null,
          malformedConsumed: !fs.existsSync(path.join(dir, "a-broken.json")),
          drainedEmpty: third.intent === undefined && third.diagnostic === undefined,
        }}));
        '''
    )
    assert payload["firstWasDiagnostic"] is True
    assert payload["goodWorker"] == "tests"
    assert payload["malformedConsumed"] is True
    assert payload["drainedEmpty"] is True


def test_inbox_roundtrip_offsets_and_diagnostics() -> None:
    payload = run_node(
        f'''\
        import {{ appendInboxMessage, inboxPath, readJsonlBatch, writeRoster, readRoster, rosterPath, stateFilePath, writeStateFile, readBoardFile, writeBoardFile }} from "{(SRC / "statefile.ts").as_uri()}";
        import fs from "node:fs";
        import os from "node:os";
        import path from "node:path";
        const dir = fs.mkdtempSync(path.join(os.tmpdir(), "agent-teams-mail-"));
        const stateFile = dir + "/state.json";
        const inbox = inboxPath(stateFile, "backend");
        appendInboxMessage(inbox, {{ id: "m1", from: "security", subject: "finding", body: "auth issue" }});
        appendInboxMessage(inbox, {{ id: "m2", from: "tests", subject: "flaky", body: "test flake" }});
        const first = readJsonlBatch(inbox, 0);
        const consumed = readJsonlBatch(inbox, first.nextOffset);
        fs.appendFileSync(inbox, "{{ broken\\n");
        const after = readJsonlBatch(inbox, first.nextOffset);
        writeRoster(rosterPath(stateFile), [{{ name: "backend", agent: "worker", status: "idle" }}]);
        const roster = readRoster(rosterPath(stateFile));
        writeStateFile(stateFile, {{ teammates: {{}}, tasks: {{}}, leaderMailbox: [], messageCounter: 0, taskCounter: 0, workerEventOffsets: {{}}, workerEventIds: {{}}, peerInboxOffsets: {{}}, peerDeliveredIds: {{}} }});
        writeBoardFile(dir + "/board.json", {{ t_1: {{ id: "t_1", subject: "s", dependsOn: [], status: "pending", createdAt: 1, updatedAt: 1 }} }});
        const board = readBoardFile(dir + "/board.json");
        console.log(JSON.stringify({{
          firstCount: first.records.length,
          secondId: consumed.records.length === 0 ? "none" : JSON.parse(JSON.stringify(consumed.records[0])).id,
          diagnostics: after.diagnostics.length,
          rosterName: roster[0]?.name ?? null,
          boardSubject: board?.tasks.t_1?.subject ?? null,
          inboxInsideSessionDir: inbox.startsWith(dir),
        }}));
        '''
    )
    assert payload["firstCount"] == 2
    assert payload["secondId"] == "none"
    assert payload["diagnostics"] >= 1
    assert payload["rosterName"] == "backend"
    assert payload["boardSubject"] == "s"
    assert payload["inboxInsideSessionDir"] is True


def test_state_machine_roster_and_board_rules() -> None:
    payload = run_node(
        f'''\
        import {{ resetState, registerTeammate, getTeammate, livingTeammates, idleTeammates,
                 releaseTasksOf, loadBoard, updateTeammate, isValidTeammateName,
                 createTask, applyClaimIntent, applySubmissionIntent, completeTask,
                 getTask, listTasks, pendingTasks, deliverToLeader, receiveWorkerMessage }} from "{(SRC / "state.ts").as_uri()}";
        function snapshot() {{
          const t = (id) => getTask(id)?.status ?? null;
          return {{}};
        }}
        resetState();
        const badName = registerTeammate({{ name: "has space", agent: "worker", spawnId: "s0", pid: 0, status: "starting", isolation: "none", createdAt: 1, updatedAt: 1 }});
        const first = registerTeammate({{ name: "security", agent: "reviewer", spawnId: "sa", pid: 1, status: "starting", isolation: "none", createdAt: 1, updatedAt: 1 }});
        const duplicate = registerTeammate({{ name: "security", agent: "worker", spawnId: "sb", pid: 2, status: "starting", isolation: "none", createdAt: 2, updatedAt: 2 }});
        updateTeammate("security", {{ status: "idle" }});
        const gate = createTask({{ subject: "base review" }});
        const dependent = createTask({{ subject: "fix findings", dependsOn: [gate.task.id] }});
        const unknownDep = createTask({{ subject: "x", dependsOn: ["t_missing"] }});
        const emptySubject = createTask({{ subject: "  " }});
        const claimBlocked = applyClaimIntent({{ taskId: dependent.task.id, worker: "security", spawnId: "sa", timestamp: 1 }});
        const claimOk = applyClaimIntent({{ taskId: gate.task.id, worker: "security", spawnId: "sa", timestamp: 1 }});
        registerTeammate({{ name: "ghost", agent: "worker", spawnId: "sx", pid: 2, status: "idle", isolation: "none", createdAt: 2, updatedAt: 2 }});
        const doubleClaim = applyClaimIntent({{ taskId: gate.task.id, worker: "ghost", spawnId: "sx", timestamp: 2 }});
        const wrongHolder = applySubmissionIntent({{ taskId: gate.task.id, worker: "ghost", spawnId: "sx", status: "completed", timestamp: 3 }});
        const submitted = applySubmissionIntent({{ taskId: gate.task.id, worker: "security", spawnId: "sa", status: "completed", result: "clean", timestamp: 4 }});
        const unlocked = pendingTasks().map((task) => task.id);
        const staleEvent = receiveWorkerMessage({{ id: "e1", type: "message", worker: "security", spawnId: "OLD", body: "b" }});
        const freshEvent = receiveWorkerMessage({{ id: "e2", type: "message", worker: "security", spawnId: "sa", body: "done\\nfull deliverable" }});
        const dupEvent = receiveWorkerMessage({{ id: "e2", type: "message", worker: "security", spawnId: "sa", body: "done\\nfull deliverable" }});
        const released = releaseTasksOf("nobody", "reason");
        // Capture pre-reset values before the resume simulation wipes the board.
        const before = {{
          gateStatus: getTask(gate.task.id)?.status ?? null,
          unlockedContainsDependent: pendingTasks().some((task) => task.id === dependent.task.id),
          staleEventAccepted: staleEvent,
          freshEventAccepted: freshEvent,
          duplicateSuppressed: dupEvent === false,
          releasedCount: released.length,
        }};
        // Resume semantics: claimed tasks die with their holders.
        resetState();
        const reloaded = loadBoard({{ t_9: {{ id: "t_9", subject: "carried over", dependsOn: [], status: "claimed", claimedBy: "dead", createdAt: 1, updatedAt: 1 }}, t_8: {{ id: "t_8", subject: "finished", dependsOn: [], status: "completed", createdAt: 1, updatedAt: 1 }} }});
        console.log(JSON.stringify({{
          badNameOk: badName.ok,
          firstOk: first.ok,
          duplicateOk: duplicate.ok,
          unknownDepOk: unknownDep.ok,
          emptySubjectOk: emptySubject.ok,
          claimBlockedReason: claimBlocked.reason ?? null,
          claimOkApplied: claimOk.applied,
          doubleClaimReason: (doubleClaim.reason ?? "").includes("already claimed"),
          wrongHolderError: (wrongHolder.error ?? "").includes("claimed by") || (wrongHolder.error ?? "").includes("not currently"),
          submittedOk: submitted.ok,
          ...before,
          reloadedCount: reloaded,
          resumedClaimBackToPending: getTask("t_9")?.status ?? null,
          resumeKeptCompleted: getTask("t_8")?.status ?? null,
        }}));
        ''',
    )
    assert payload["badNameOk"] is False
    assert payload["firstOk"] is True
    assert payload["duplicateOk"] is False
    assert payload["unknownDepOk"] is False
    assert payload["emptySubjectOk"] is False
    assert payload["claimBlockedReason"] is not None and "unmet dependencies" in payload["claimBlockedReason"]
    assert payload["claimOkApplied"] is True
    assert payload["doubleClaimReason"] is True
    assert payload["wrongHolderError"] is True
    assert payload["submittedOk"] is True
    assert payload["gateStatus"] == "completed"
    assert payload["unlockedContainsDependent"] is True
    assert payload["staleEventAccepted"] is False
    assert payload["freshEventAccepted"] is True
    assert payload["duplicateSuppressed"] is True
    assert payload["releasedCount"] == 0
    assert payload["reloadedCount"] == 2
    assert payload["resumedClaimBackToPending"] == "pending"
    assert payload["resumeKeptCompleted"] == "completed"


def test_wake_prompt_composes_deliveries_and_paced_notice() -> None:
    payload = run_node(
        f'''\
        import {{ buildWakePrompt, NOTICE_PACE_MS }} from "{(SRC / "team-machine.ts").as_uri()}";
        const prompt = buildWakePrompt(
          [{{ id: "m1", from: "security", subject: "challenge", body: "your finding misses X", timestamp: 1 }}],
          [{{ id: "t_3", subject: "verify hotfix" }}],
          true,
        );
        const quiet = buildWakePrompt([], [], false);
        console.log(JSON.stringify({{
          hasInbox: prompt.includes("=== INBOX (1 new) ==="),
          hasSender: prompt.includes("From security · challenge"),
          hasBody: prompt.includes("your finding misses X"),
          hasNotice: prompt.includes("Unclaimed tasks: t_3 (verify hotfix)"),
          suggestsClaim: prompt.includes("action=claim"),
          quietEmpty: quiet === "",
          paceMs: NOTICE_PACE_MS,
        }}));
        '''
    )
    assert payload["hasInbox"] is True
    assert payload["hasSender"] is True
    assert payload["hasBody"] is True
    assert payload["hasNotice"] is True
    assert payload["suggestsClaim"] is True
    assert payload["quietEmpty"] is True
    assert payload["paceMs"] == 5 * 60 * 1000


def test_notice_pacing_defaults_to_minutes_and_is_configurable() -> None:
    default_payload = run_node(
        f'''\
        import {{ NOTICE_PACE_MS }} from "{(SRC / "team-machine.ts").as_uri()}";
        console.log(JSON.stringify({{ paceMs: NOTICE_PACE_MS }}));
        '''
    )
    override_payload = run_node(
        f'''\
        import {{ NOTICE_PACE_MS }} from "{(SRC / "team-machine.ts").as_uri()}";
        console.log(JSON.stringify({{ paceMs: NOTICE_PACE_MS }}));
        ''',
        env_overrides={"PI_TEAMMATE_NOTICE_PACE_MS": "45000"},
    )
    invalid_payload = run_node(
        f'''\
        import {{ NOTICE_PACE_MS }} from "{(SRC / "team-machine.ts").as_uri()}";
        console.log(JSON.stringify({{ paceMs: NOTICE_PACE_MS }}));
        ''',
        env_overrides={"PI_TEAMMATE_NOTICE_PACE_MS": "not-a-number"},
    )
    assert default_payload["paceMs"] == 5 * 60 * 1000
    assert override_payload["paceMs"] == 45_000
    assert invalid_payload["paceMs"] == 5 * 60 * 1000


def test_fresh_claimable_filter_is_one_shot_per_task() -> None:
    payload = run_node(
        f'''\
        import {{ freshClaimableTasks }} from "{(SRC / "team-machine.ts").as_uri()}";
        const tasks = [{{ id: "t_1" }}, {{ id: "t_2" }}, {{ id: "t_3" }}];
        console.log(JSON.stringify({{
          firstPass: freshClaimableTasks(undefined, tasks).map((task) => task.id),
          afterNotice: freshClaimableTasks(["t_1", "t_2"], tasks).map((task) => task.id),
          emptyWhenAllSeen: freshClaimableTasks(["t_1", "t_2", "t_3"], tasks).length === 0,
        }}));
        '''
    )
    assert payload["firstPass"] == ["t_1", "t_2", "t_3"]
    assert payload["afterNotice"] == ["t_3"]
    assert payload["emptyWhenAllSeen"] is True


def test_repeated_verify_failures_escalate_once_then_go_quiet() -> None:
    payload = run_node(
        f'''\
        import {{ reactToVerifyFailure, VERIFY_FAILURE_ESCALATE_AFTER }} from "{(SRC / "team-machine.ts").as_uri()}";
        const first = reactToVerifyFailure(undefined);
        const second = reactToVerifyFailure(first);
        const third = reactToVerifyFailure(second);
        console.log(JSON.stringify({{
          escalateAfter: VERIFY_FAILURE_ESCALATE_AFTER,
          first,
          second,
          third,
        }}));
        '''
    )
    assert payload["escalateAfter"] == 2
    assert payload["first"] == {"count": 1, "escalated": False, "escalateToLeader": False}
    assert payload["second"] == {"count": 2, "escalated": True, "escalateToLeader": True}
    assert payload["third"] == {"count": 3, "escalated": True, "escalateToLeader": False}


def test_task_ids_are_meaningful_slugs_of_their_subjects() -> None:
    payload = run_node(
        f'''\
        import {{ resetState, createTask, loadBoard }} from "{(SRC / "state.ts").as_uri()}";
        resetState();
        const a = createTask({{ subject: "Polish login flow" }});
        const b = createTask({{ subject: "Polish login flow!" }});
        const c = createTask({{ subject: "修复登录流程" }});
        const d = createTask({{ subject: "***" }});
        loadBoard({{ t_9: {{ id: "t_9", subject: "carried over", dependsOn: [], status: "completed", createdAt: 1, updatedAt: 1 }} }});
        const afterResume = createTask({{ subject: "Carried over" }});
        console.log(JSON.stringify({{
          a: a.task.id,
          b: b.task.id,
          c: c.task.id,
          d: d.task.id,
          distinct: a.task.id !== b.task.id,
          afterResume: afterResume.task.id,
        }}));
        '''
    )
    assert payload["a"] == "polish-login-flow"
    assert payload["b"] == "polish-login-flow-2"
    assert payload["c"] == "修复登录流程"
    assert payload["d"] == "task"
    assert payload["distinct"] is True
    # A resumed board keeps its legacy ids; new slugs still never collide.
    assert payload["afterResume"] != "t_10"
    assert source("state.ts").count("taskCounter") == 0


def test_task_lookups_ignore_prototype_property_names() -> None:
    payload = run_node(
        f'''\
        import {{ resetState, createTask, getTask, applyClaimIntent, loadBoard, registerTeammate }} from "{(SRC / "state.ts").as_uri()}";
        resetState();
        registerTeammate({{ name: "w", agent: "worker", spawnId: "s", pid: 1, status: "idle", isolation: "none", createdAt: 1, updatedAt: 1 }});
        const depBefore = createTask({{ subject: "real work", dependsOn: ["constructor"] }});
        const made = createTask({{ subject: "Constructor" }});
        const resolved = getTask("constructor");
        const claim = applyClaimIntent({{ taskId: "constructor", worker: "w", spawnId: "s", timestamp: 1 }});
        // A JSON-parsed board (Object.prototype intact) must not leak either.
        resetState();
        loadBoard(JSON.parse(JSON.stringify({{ t_1: {{ id: "t_1", subject: "legacy", dependsOn: [], status: "completed", createdAt: 1, updatedAt: 1 }} }})));
        const afterLegacyDep = createTask({{ subject: "next step", dependsOn: ["hasOwnProperty"] }});
        console.log(JSON.stringify({{
          depBlockedBeforeCreation: depBefore.ok === false,
          madeId: made.task?.id ?? null,
          resolvedIsOwnEntry: resolved?.id === "constructor",
          resolvedNotAFunction: typeof resolved !== "function",
          claimApplied: claim.applied === true,
          legacyProtoDepBlocked: afterLegacyDep.ok === false,
        }}));
        '''
    )
    assert payload["depBlockedBeforeCreation"] is True
    assert payload["madeId"] == "constructor"
    assert payload["resolvedIsOwnEntry"] is True
    assert payload["resolvedNotAFunction"] is True
    assert payload["claimApplied"] is True
    assert payload["legacyProtoDepBlocked"] is True


def test_slug_ids_with_duplicate_suffixes_stay_within_length_cap() -> None:
    payload = run_node(
        f'''\
        import {{ resetState, createTask }} from "{(SRC / "state.ts").as_uri()}";
        resetState();
        const long = "Audit every single surface of the whole application very thoroughly".toLowerCase();
        const first = createTask({{ subject: long }});
        const second = createTask({{ subject: long + "!" }});
        console.log(JSON.stringify({{
          a: first.task.id,
          b: second.task.id,
          bothWithinCap: first.task.id.length <= 48 && second.task.id.length <= 48,
          distinct: first.task.id !== second.task.id,
        }}));
        '''
    )
    assert payload["bothWithinCap"] is True
    assert payload["distinct"] is True
    assert payload["b"].endswith("-2")


def test_retain_live_noticed_ids_prunes_stale_first() -> None:
    payload = run_node(
        f'''\
        import {{ retainLiveNoticedIds }} from "{(SRC / "team-machine.ts").as_uri()}";
        const noticed = ["old-done", "live-1", "live-2", "other-done"];
        const retained = retainLiveNoticedIds(noticed, new Set(["live-1", "live-2", "brand-new"]));
        console.log(JSON.stringify({{ retained }}));
        '''
    )
    assert payload["retained"] == ["live-1", "live-2"]


def test_unknown_agent_error_names_configured_user_dir_and_lists_agents() -> None:
    payload = run_node(
        f'''\
        import {{ unknownAgentError }} from "{(SRC / "team-machine.ts").as_uri()}";
        console.log(JSON.stringify({{ message: unknownAgentError("ghost-role", "/tmp/proj") }}));
        ''',
        env_overrides={"PI_CODING_AGENT_DIR": "/tmp/custom-agent-dir"},
    )
    message = payload["message"]
    assert "ghost-role" in message
    assert "/tmp/proj/.pi/agents" in message
    assert "/tmp/custom-agent-dir/agents" in message
    assert "~/.pi/agent/agents" not in message
    assert "stale" in message
    assert "definition" in message
    assert "references/agent-roles.md" in message
    assert "Available now:" in message


def test_stale_verify_result_cannot_complete_a_new_holding(tmp_path: Path) -> None:
    payload = run_node(
        f'''\
        import {{ initTeamMachine, shutdownTeamMachine, attemptSubmission, processTaskIntents, setVerifyGateRunner }} from "{(SRC / "team-machine.ts").as_uri()}";
        import {{ resetState, registerTeammate, createTask, applyClaimIntent, getTask }} from "{(SRC / "state.ts").as_uri()}";
        initTeamMachine({{ sessionManager: undefined, cwd: {str(tmp_path)!r} }}, {{ sendUpdate: () => {{}}, notifyChange: () => {{}} }});
        resetState();
        const tick = () => new Promise((resolve) => setTimeout(resolve, 10));
        registerTeammate({{ name: "w", agent: "reviewer", spawnId: "s1", pid: 0, status: "working", isolation: "none", createdAt: 1, updatedAt: 1 }});
        const made = createTask({{ subject: "gated work", verify: "Does the delivered gallery satisfy every acceptance criterion?" }});
        const id = made.task.id;
        applyClaimIntent({{ taskId: id, worker: "w", spawnId: "s1", timestamp: 1 }});
        let releaseStaleGate;
        setVerifyGateRunner(() => new Promise((resolve) => {{ releaseStaleGate = () => resolve({{ kind: "pass" }}); }}));
        attemptSubmission("w", "s1", id, "completed");
        processTaskIntents();
        await tick();
        attemptSubmission("w", "s1", id, "failed");
        processTaskIntents();
        const releasedWhileVerifying = getTask(id).status === "pending";
        applyClaimIntent({{ taskId: id, worker: "w", spawnId: "s1", timestamp: 2 }});
        releaseStaleGate();
        await tick();
        const staleCompleted = getTask(id).status === "completed";
        let releaseFreshGate;
        setVerifyGateRunner(() => new Promise((resolve) => {{ releaseFreshGate = () => resolve({{ kind: "pass" }}); }}));
        attemptSubmission("w", "s1", id, "completed");
        processTaskIntents();
        await tick();
        releaseFreshGate();
        await tick();
        console.log(JSON.stringify({{
          releasedWhileVerifying,
          staleCompleted,
          finalStatus: getTask(id).status,
        }}));
        shutdownTeamMachine();
        '''
    )
    assert payload["releasedWhileVerifying"] is True
    # The pre-release gate result must not complete the post-release holding.
    assert payload["staleCompleted"] is False
    assert payload["finalStatus"] == "completed"


def test_verify_review_verdict_protocol() -> None:
    payload = run_node(
        f'''\
        import {{ buildVerifyReviewPrompt, parseVerifyVerdict }} from "{(SRC / "team-machine.ts").as_uri()}";
        const NL = String.fromCharCode(10);
        const reply = (...lines) => lines.join(NL);
        console.log(JSON.stringify({{
          promptHasGate: buildVerifyReviewPrompt({{ verify: "Every scenario holds.", taskSubject: "Gallery refactor", workerResult: "Done.", cwd: "/repo" }}).includes("Every scenario holds."),
          pass: parseVerifyVerdict(reply("Evidence...", "VERDICT: PASS")),
          passLowerCase: parseVerifyVerdict("verdict: pass"),
          passTrailingProse: parseVerifyVerdict(reply("VERDICT: PASS", "(closing note)")),
          passWithJunkRejected: parseVerifyVerdict(reply("A", "VERDICT: PASS - also broken", "B")),
          failWithReason: parseVerifyVerdict(reply("Evidence...", "VERDICT: FAIL - overflow at 400px")),
          failExtraSpaces: parseVerifyVerdict("VERDICT:   FAIL   spaced reasons"),
          missing: parseVerifyVerdict("Looks good to me"),
          missingDetailTruncated: parseVerifyVerdict("x".repeat(5000)).detail.includes("[truncated]"),
        }}, (key, value) => (value === undefined ? null : value)));
        '''
    )
    assert payload["promptHasGate"] is True
    assert payload["pass"] == {"kind": "pass"}
    assert payload["passLowerCase"] == {"kind": "pass"}
    assert payload["passTrailingProse"] == {"kind": "pass"}
    assert payload["passWithJunkRejected"]["kind"] == "inconclusive"
    assert payload["failWithReason"]["kind"] == "fail"
    assert "overflow at 400px" in payload["failWithReason"]["detail"]
    assert payload["failExtraSpaces"]["kind"] == "fail"
    assert "spaced reasons" in payload["failExtraSpaces"]["detail"]
    assert payload["missing"]["kind"] == "inconclusive"
    assert payload["missingDetailTruncated"] is True


def test_agent_definitions_are_declarative_files_with_verify() -> None:
    ext = source("agents.ts") + source("tools.ts")
    assert "discoverAgents" in ext and "resolveAgent" in ext
    agents_ts = source("agents.ts")
    assert 'LOCAL_DEFINITION_SUFFIX = ".local.md"' in agents_ts
    assert 'gitManaged: scope === "project"' in agents_ts or 'return scope === "project";' in agents_ts
    assert "fields.verify" in agents_ts
    assert 'return scope === "project";' in agents_ts
    assert "PI_CODING_AGENT_DIR" in agents_ts or "getAgentDir" in agents_ts
    assert 'export type AgentScope = "user" | "project" | "project-local" | "session";' in agents_ts
    assert "registerSessionAgent" in agents_ts
    assert "clearSessionAgents" in agents_ts
    assert "source: undefined" in agents_ts


def test_generated_agent_roles_can_be_persisted_only_explicitly(tmp_path: Path) -> None:
    payload = run_node(
        f'''\
        import {{ discoverAgents, persistAgentDefinition, clearSessionAgents }} from "{(SRC / "agents.ts").as_uri()}";
        import fs from "node:fs";
        clearSessionAgents();
        const persisted = persistAgentDefinition({{
          name: "saved-reviewer",
          description: "Review a requested scope",
          tools: ["read"],
          prompt: "Review only the assigned scope.",
        }}, "project-local", {json.dumps(str(tmp_path))});
        const found = discoverAgents({json.dumps(str(tmp_path))}).get("saved-reviewer");
        console.log(JSON.stringify({{
          scope: persisted.scope,
          sourceExists: typeof persisted.source === "string" && fs.existsSync(persisted.source),
          discoveredScope: found?.scope ?? null,
          gitManaged: found?.gitManaged ?? null,
        }}));
        ''',
    )
    assert payload == {
        "scope": "project-local",
        "sourceExists": True,
        "discoveredScope": "project-local",
        "gitManaged": False,
    }


def test_generated_agent_roles_are_session_scoped_and_not_persisted(tmp_path: Path) -> None:
    payload = run_node(
        f'''\
        import {{ discoverAgents, registerSessionAgent, clearSessionAgents }} from "{(SRC / "agents.ts").as_uri()}";
        import fs from "node:fs";
        clearSessionAgents();
        const registered = registerSessionAgent({{
          name: "human-philosopher",
          description: "Analyze human nature",
          tools: ["read"],
          prompt: "Answer from philosophical traditions.",
        }});
        const current = discoverAgents({json.dumps(str(tmp_path))}).get("human-philosopher");
        const agentsDir = {json.dumps(str(tmp_path / ".pi" / "agents"))};
        const filesBefore = fs.existsSync(agentsDir) ? fs.readdirSync(agentsDir) : [];
        clearSessionAgents();
        const afterReset = discoverAgents({json.dumps(str(tmp_path))}).get("human-philosopher");
        console.log(JSON.stringify({{
          registered: registered.scope,
          sourceIsMemory: current?.source === undefined,
          gitManaged: current?.gitManaged ?? null,
          filesBefore,
          absentAfterReset: afterReset === undefined,
        }}));
        ''',
    )
    assert payload == {
        "registered": "session",
        "sourceIsMemory": True,
        "gitManaged": False,
        "filesBefore": [],
        "absentAfterReset": True,
    }


def test_persistent_definitions_outrank_generated_session_roles(tmp_path: Path) -> None:
    payload = run_node(
        f'''\
        import {{ discoverAgents, registerSessionAgent, clearSessionAgents }} from "{(SRC / "agents.ts").as_uri()}";
        import fs from "node:fs";
        clearSessionAgents();
        const agentsDir = {json.dumps(str(tmp_path / ".pi" / "agents"))};
        fs.mkdirSync(agentsDir, {{ recursive: true }});
        fs.writeFileSync(`${{agentsDir}}/scout.md`, [
          "---",
          "name: scout",
          "description: File-based scout",
          "tools: read",
          "---",
          "File role.",
          "",
        ].join("\\n"));
        registerSessionAgent({{
          name: "scout",
          description: "Session scout",
          tools: ["bash"],
          prompt: "Session prompt.",
        }});
        registerSessionAgent({{
          name: "ghost",
          description: "Only in memory",
          tools: ["bash"],
          prompt: "Ghost prompt.",
        }});
        const scout = discoverAgents({json.dumps(str(tmp_path))}).get("scout");
        const ghost = discoverAgents({json.dumps(str(tmp_path))}).get("ghost");
        console.log(JSON.stringify({{
          scoutScope: scout?.scope ?? null,
          scoutTools: scout?.tools ?? null,
          ghostScope: ghost?.scope ?? null,
        }}));
        ''',
    )
    assert payload == {
        "scoutScope": "project",
        "scoutTools": ["read"],
        "ghostScope": "session",
    }


def test_inline_definitions_replace_stale_session_roles_but_not_files(tmp_path: Path) -> None:
    payload = run_node(
        f'''\
        import {{ inlineDefinitionApplies }} from "{(SRC / "team-machine.ts").as_uri()}";
        import {{ resolveAgent, registerSessionAgent, clearSessionAgents }} from "{(SRC / "agents.ts").as_uri()}";
        import fs from "node:fs";
        const cwd = {json.dumps(str(tmp_path))};
        clearSessionAgents();
        const noResolution = inlineDefinitionApplies(undefined);
        const beforeFile = (() => {{
          registerSessionAgent({{ name: "scout", description: "Stale role", tools: ["bash"], prompt: "Old." }});
          return inlineDefinitionApplies(resolveAgent("scout", cwd));
        }})();
        const agentsDir = `${{cwd}}/.pi/agents`;
        fs.mkdirSync(agentsDir, {{ recursive: true }});
        fs.writeFileSync(`${{agentsDir}}/scout.md`, [
          "---",
          "name: scout",
          "description: File-based scout",
          "tools: read",
          "---",
          "File role.",
          "",
        ].join("\\n"));
        const afterFile = inlineDefinitionApplies(resolveAgent("scout", cwd));
        console.log(JSON.stringify({{ noResolution, sessionRoleCase: beforeFile, fileCase: afterFile }}));
        ''',
    )
    assert payload == {"noResolution": True, "sessionRoleCase": True, "fileCase": False}
    machine = source("team-machine.ts")
    # The spawn path must gate generation on the helper so a corrected inline
    # definition replaces a stale session role instead of being ignored.
    assert "input.definition && inlineDefinitionApplies(resolved)" in machine


def test_spawn_model_resolution_precedence() -> None:
    payload = run_node(
        f'''\
        import {{ resolveSpawnModel }} from "{(SRC / "team-machine.ts").as_uri()}";
        console.log(JSON.stringify({{
          pin: resolveSpawnModel("anthropic/claude-opus-4-6", "openai/gpt-5.2", "google/gemini-3-pro"),
          inherit: resolveSpawnModel("inherit", "openai/gpt-5.2", "openai/gpt-5.2-leader"),
          inheritCaseInsensitive: resolveSpawnModel("Inherit", undefined, "google/gemini-3-pro"),
          teamDefault: resolveSpawnModel(undefined, "openai/gpt-5.2", "google/gemini-3-pro"),
          none: resolveSpawnModel(undefined, undefined, undefined),
          fallbackSession: resolveSpawnModel(undefined, undefined, "google/gemini-3-pro"),
          inheritWithoutLeaderModel: resolveSpawnModel("inherit", undefined, undefined),
          blankPinIsUnset: resolveSpawnModel("  ", "openai/gpt-5.2", undefined),
        }}));
        '''
    )
    assert payload["pin"] == {"model": "anthropic/claude-opus-4-6", "source": "pin"}
    assert payload["inherit"] == {"model": "openai/gpt-5.2-leader", "source": "inherit"}
    assert payload["inheritCaseInsensitive"] == {"model": "google/gemini-3-pro", "source": "inherit"}
    assert payload["teamDefault"] == {"model": "openai/gpt-5.2", "source": "team-default"}
    assert payload["none"] == {"source": "none"}
    assert payload["fallbackSession"] == {"model": "google/gemini-3-pro", "source": "leader-session"}
    assert payload["inheritWithoutLeaderModel"] == {"source": "none"}
    assert payload["blankPinIsUnset"] == {"model": "openai/gpt-5.2", "source": "team-default"}


def test_leader_model_and_thinking_switch_apply_to_later_spawns() -> None:
    payload = run_node(
        f'''\
        import {{ currentLeaderModelRef, currentLeaderThinkingLevel, initTeamMachine, shutdownTeamMachine, syncLeaderContext }} from "{(SRC / "team-machine.ts").as_uri()}";
        initTeamMachine(
          {{ cwd: "/tmp", model: {{ provider: "cli-proxy", id: "gpt-6-astra" }}, thinkingLevel: "low" }},
          {{ sendUpdate: () => {{}}, notifyChange: () => {{}} }},
        );
        const beforeModel = currentLeaderModelRef();
        const beforeThinking = currentLeaderThinkingLevel();
        syncLeaderContext({{ model: {{ provider: "cli-proxy", id: "omen-alpha" }}, thinkingLevel: "high" }});
        const afterModel = currentLeaderModelRef();
        const afterThinking = currentLeaderThinkingLevel();
        const restore = process.env.PI_REASONING_LEVEL;
        process.env.PI_REASONING_LEVEL = "medium";
        process.env.PI_PROVIDER = "test-provider";
        process.env.PI_MODEL = "test-model";
        syncLeaderContext({{}});
        const envFallbackThinking = currentLeaderThinkingLevel();
        const envFallbackModel = currentLeaderModelRef();
        process.env.PI_REASONING_LEVEL = restore;
        shutdownTeamMachine();
        console.log(JSON.stringify({{ beforeModel, beforeThinking, afterModel, afterThinking, envFallbackThinking, envFallbackModel }}));
        '''
    )
    assert payload["beforeModel"] == "cli-proxy/gpt-6-astra"
    assert payload["beforeThinking"] == "low"
    assert payload["afterModel"] == "cli-proxy/omen-alpha"
    assert payload["afterThinking"] == "high"
    assert payload["envFallbackThinking"] == "medium"
    assert payload["envFallbackModel"] == "test-provider/test-model"


def test_spawner_forwards_thinking_flag() -> None:
    spawner = source("spawner.ts")
    assert '"--thinking", options.thinking' in spawner
    assert 'thinking?: string;' in spawner


def test_team_default_model_persists_in_state_snapshot() -> None:
    payload = run_node(
        f'''\
        import {{ getTeamDefaultModel, setTeamDefaultModel, getState }} from "{(SRC / "state.ts").as_uri()}";
        setTeamDefaultModel("openai/gpt-5.2");
        const stored = getTeamDefaultModel();
        const snapshotted = JSON.stringify(getState()).includes("openai/gpt-5.2");
        setTeamDefaultModel("  ");
        const cleared = getTeamDefaultModel();
        console.log(JSON.stringify({{ stored, snapshotted, cleared }}, (key, value) => (value === undefined ? null : value)));
        '''
    )
    assert payload["stored"] == "openai/gpt-5.2"
    assert payload["snapshotted"] is True
    assert payload["cleared"] is None


def test_picker_key_routes_printables_to_typing_and_keys_to_actions() -> None:
    payload = run_node(
        f'''\
        import {{ mapPickerKey }} from "{(SRC / "picker-keys.ts").as_uri()}";
        console.log(JSON.stringify({{
          letterC: mapPickerKey("c"),
          capitalC: mapPickerKey("C"),
          digit: mapPickerKey("3"),
          space: mapPickerKey(" "),
          escape: mapPickerKey("\\x1b"),
          enter: mapPickerKey("\\r"),
          up: mapPickerKey("\\x1b[A"),
          down: mapPickerKey("\\x1b[B"),
          backspace: mapPickerKey("\\x7f"),
          tabIgnored: mapPickerKey("\\t"),
          multiCharPasteIgnored: mapPickerKey("abc"),
        }}, (key, value) => (value === undefined ? null : value)));
        '''
    )
    # The regression core: letters route to typing, never to shortcuts.
    for key in ("letterC", "capitalC", "digit", "space"):
        assert payload[key] == {"kind": "type", "text": {"letterC": "c", "capitalC": "C", "digit": "3", "space": " "}[key]}, key
    assert payload["escape"] == {"kind": "cancel"}
    assert payload["enter"] == {"kind": "confirm"}
    assert payload["up"] == {"kind": "up"}
    assert payload["down"] == {"kind": "down"}
    assert payload["backspace"] == {"kind": "backspace"}
    assert payload["tabIgnored"] is None
    assert payload["multiCharPasteIgnored"] is None


def test_agent_frontmatter_parses_tools_model_verify(tmp_path: Path) -> None:
    agents_dir = tmp_path / ".pi" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "auditor.md").write_text(
        "---\n"
        "name: auditor\n"
        "description: Reviews code for exploitable problems\n"
        "tools: read,grep # execution allowlist\n"
        "model: anthropic/claude-sonnet-4\n"
        'verify: "Every declared acceptance scenario holds in the built gallery"\n'
        "worktree: true\n"
        "---\n"
        "Review the assigned scope.\n",
        encoding="utf-8",
    )
    payload = run_node(
        f'''\
        import {{ resolveAgent }} from "{(SRC / "agents.ts").as_uri()}";
        const agent = resolveAgent("auditor", {json.dumps(str(tmp_path))});
        console.log(JSON.stringify({{
          found: Boolean(agent),
          tools: agent?.tools ?? [],
          model: agent?.model ?? null,
          verify: agent?.verify ?? null,
          worktree: agent?.worktree ?? null,
          scope: agent?.scope ?? null,
          promptIsBody: (agent?.prompt ?? "").includes("Review the assigned scope."),
        }}));
        ''',
    )
    assert payload["found"] is True
    assert payload["tools"] == ["read", "grep"]
    assert payload["model"] == "anthropic/claude-sonnet-4"
    assert payload["verify"] == "Every declared acceptance scenario holds in the built gallery"
    assert payload["worktree"] is True
    assert payload["scope"] == "project"
    assert payload["promptIsBody"] is True


def test_agent_frontmatter_parses_multiline_dash_list_tools(tmp_path: Path) -> None:
    agents_dir = tmp_path / ".pi" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "scribe.md").write_text(
        "---\n"
        "name: scribe\n"
        "description: Worktree writer\n"
        "tools:\n"
        "  - read\n"
        "  - bash\n"
        "  - edit # allow file edits\n"
        "  - write\n"
        "worktree: true\n"
        "---\n"
        "Write inside your worktree.\n",
        encoding="utf-8",
    )
    payload = run_node(
        f'''\
        import {{ resolveAgent }} from "{(SRC / "agents.ts").as_uri()}";
        const agent = resolveAgent("scribe", {json.dumps(str(tmp_path))});
        console.log(JSON.stringify({{
          found: Boolean(agent),
          tools: agent?.tools ?? [],
          worktree: agent?.worktree ?? null,
          promptIsBody: (agent?.prompt ?? "").includes("Write inside your worktree."),
        }}));
        ''',
    )
    assert payload["found"] is True
    assert payload["tools"] == ["read", "bash", "edit", "write"]
    assert payload["worktree"] is True
    assert payload["promptIsBody"] is True


def test_agent_frontmatter_dash_list_edge_cases(tmp_path: Path) -> None:
    """Flush-left dashes, interleaved comments, no-space dashes, and
    comment-only entries must parse like a standard YAML block sequence."""
    agents_dir = tmp_path / ".pi" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "edge.md").write_text(
        "---\n"
        "name: edge\n"
        "description: Dash-list edge cases\n"
        "tools:\n"
        "# allowlist comment\n"
        "- read\n"
        "  - bash\n"
        "-edit\n"
        "  - # not a tool\n"
        "- write # trailing comment\n"
        "model: m\n"
        "---\n"
        "Edge body.\n",
        encoding="utf-8",
    )
    payload = run_node(
        f'''\
        import {{ resolveAgent }} from "{(SRC / "agents.ts").as_uri()}";
        const agent = resolveAgent("edge", {json.dumps(str(tmp_path))});
        console.log(JSON.stringify({{ tools: agent?.tools ?? [], model: agent?.model ?? null }}));
        ''',
    )
    assert payload["tools"] == ["read", "bash", "edit", "write"]
    assert payload["model"] == "m"


def test_project_agent_overrides_user_scope(tmp_path: Path) -> None:
    user_dir = tmp_path / "user-agents"
    project_dir = tmp_path / ".pi" / "agents"
    project_dir.mkdir(parents=True)
    user_dir.mkdir(parents=True)
    (user_dir / "dup.md").write_text("---\nname: dup\n---\nuser body\n", encoding="utf-8")
    # Same teammate, shared layer + personal local override in ONE directory.
    (project_dir / "dup.md").write_text("---\nname: dup\n---\nproject body\n", encoding="utf-8")
    (project_dir / "dup.local.md").write_text("---\nname: dup\n---\nproject-local body\n", encoding="utf-8")
    (project_dir / "shared.md").write_text("---\nname: shared\n---\nshared role\n", encoding="utf-8")
    (project_dir / "personal.local.md").write_text("---\nname: personal\n---\npersonal role\n", encoding="utf-8")
    payload = run_node(
        f'''\
        import {{ discoverAgents, resolveAgent }} from "{(SRC / "agents.ts").as_uri()}";
        const all = discoverAgents({json.dumps(str(tmp_path))});
        const dup = resolveAgent("dup", {json.dumps(str(tmp_path))});
        const shared = resolveAgent("shared", {json.dumps(str(tmp_path))});
        const personal = resolveAgent("personal", {json.dumps(str(tmp_path))});
        console.log(JSON.stringify({{
          keys: [...all.keys()].sort(),
          dupScope: dup?.scope,
          dupBody: dup?.prompt,
          dupGitManaged: dup?.gitManaged,
          sharedScope: shared?.scope,
          sharedGitManaged: shared?.gitManaged,
          personalScope: personal?.scope,
          personalGitManaged: personal?.gitManaged,
        }}));
        ''',
        env_overrides={"PI_CODING_AGENT_DIR": str(user_dir)},
    )
    # dedup: dup.md + dup.local.md collapse into ONE entry; no "dup.local" key.
    # There are no built-in roles, so only the fixture definitions exist.
    assert sorted(payload["keys"]) == ["dup", "personal", "shared"]
    assert payload["dupScope"] == "project-local"
    assert payload["dupBody"] == "project-local body"
    assert payload["dupGitManaged"] is False
    assert payload["sharedScope"] == "project"
    assert payload["sharedGitManaged"] is True
    assert payload["personalScope"] == "project-local"
    assert payload["personalGitManaged"] is False


def test_leader_guidance_is_disclosed_only_for_active_team_state() -> None:
    payload = run_node(
        f'''\
        import {{ hasActiveTeamState }} from "{(SRC / "index.ts").as_uri()}";
        import {{ resetState, registerTeammate, createTask, updateTeammate }} from "{(SRC / "state.ts").as_uri()}";
        resetState();
        const inactive = hasActiveTeamState();
        registerTeammate({{ name: "worker", agent: "worker", spawnId: "s1", pid: 1, status: "idle", isolation: "none", createdAt: 1, updatedAt: 1 }});
        const rosterActive = hasActiveTeamState();
        updateTeammate("worker", {{ status: "stopped" }});
        createTask({{ subject: "board work" }});
        const boardActive = hasActiveTeamState();
        console.log(JSON.stringify({{ inactive, rosterActive, boardActive }}));
        '''
    )
    assert payload == {"inactive": False, "rosterActive": True, "boardActive": True}
    index_ts = source("index.ts")
    assert "teamIsActive" in index_ts
    assert "buildIdleLeaderGuidance" in index_ts
    assert "? buildTeamLeaderGuidance" in index_ts


def test_team_status_clear_uses_pi_kit_transient_status_adapter() -> None:
    index = (PACKAGE / "src" / "index.ts").read_text(encoding="utf-8")
    assert 'clearPiStatus(ctx.ui, "teammate")' in index
    assert 'ctx.ui.setStatus("teammate", undefined)' not in index


def test_unknown_agent_error_gives_the_complete_inline_spawn_recovery() -> None:
    team_machine = source("team-machine.ts")
    assert "name and an existing agent role id" in team_machine
    assert "name, a new agent role id, and an inline definition" in team_machine
    assert "includes description and prompt" in team_machine
    agent_control = source("agent-control.ts")
    assert "unknownAgentError" in agent_control


def test_follow_up_reports_use_wrapped_marker_format() -> None:
    payload = run_node(
        f'''\
        import {{ formatReports }} from "{(SRC / "leader-reports.ts").as_uri()}";
        const content = formatReports([
          {{ teammate: "security", body: "<b>bold finding</b>" }},
        ]);
        console.log(JSON.stringify({{
          wrapped: content.includes('<agent-message from="security">'),
          escaped: formatReports([{{ teammate: 'a"b', body: "x" }}]).includes('from="a&quot;b"'),
          stamped: formatReports([{{ teammate: "x", body: "y", timestamp: 0 }}]).includes('<agent-message from="x" at="1970-01-01T00:00:00.000Z">'),
          unstampedOmitsAt: !formatReports([{{ teammate: "x", body: "y" }}]).includes(" at="),
          fullBodyKept: content.includes("<b>bold finding</b>"),
          noRunIds: !content.includes("run_"),
          noFinishedNotice: !content.includes("finished."),
          harnessEvent: formatReports([{{ origin: "harness", harnessEvent: {{ type: "unexpected-stop", subject: "@audit stopped unexpectedly" }}, body: "diagnostic" }}]).includes('<harness-event type="unexpected-stop" subject="@audit stopped unexpectedly">'),
          harnessIsNotAgentMessage: !formatReports([{{ origin: "harness", harnessEvent: {{ type: "unexpected-stop", subject: "@audit stopped unexpectedly" }}, body: "diagnostic" }}]).includes("<agent-message"),
        }}));
        '''
    )
    assert payload["wrapped"] is True
    assert payload["escaped"] is True
    assert payload["stamped"] is True
    assert payload["unstampedOmitsAt"] is True
    assert payload["fullBodyKept"] is True
    assert payload["noRunIds"] is True
    assert payload["noFinishedNotice"] is True
    assert payload["harnessEvent"] is True
    assert payload["harnessIsNotAgentMessage"] is True


def test_console_supports_mouse_wheel_scrolling() -> None:
    ext = source("ui.ts")
    # One SGR wheel parser shared by the list page and detail views.
    assert "function wheelDelta(data: string): number | undefined" in ext
    assert "/^\\x1b\\[<(\\d+);\\d+;\\d+[Mm]$/" in ext
    assert "(button & 64) === 0" in ext
    assert ext.count("const wheel = wheelDelta(data);") == 2


def test_console_has_roster_and_board_pages() -> None:
    ext = source("ui.ts")
    assert '"roster"' in ext and '"board"' in ext
    assert 'Key.tab' in ext
    assert "shutdownFromConsole" in ext
    assert "buildTaskDetail" in ext and "buildTeammateDetail" in ext
    assert "peer mail" in ext


def test_widget_shows_only_working_teammates() -> None:
    ext = source("ui.ts")
    widget = ext[ext.index("export function ensureTeamWidget"):ext.index("export function refreshTeamUI")]
    assert "createLiveActivityWidget" in ext
    assert 'key: "teammate"' in ext
    assert 'placement: "aboveEditor"' in ext
    assert "teamActivityWidget.update(ctx, working.map" in widget
    assert "id: teammate.name" in widget
    assert "identity: teammate.name" in widget
    assert "activity: runningTeammateActivity(teammate) + stallSuffix(teammate)" in widget
    assert 'teammate.status === "working" || teammate.status === "starting"' in ext
    assert "listTeammates()" not in widget

def test_render_lifecycle_result_survives_class_based_theme() -> None:
    script = f"""
import {{ initTheme }} from "@earendil-works/pi-coding-agent";
import {{ renderLifecycleResult }} from "{(SRC / "tool-render.ts").as_uri()}";

initTheme("dark");
class ClassTheme {{
  constructor() {{ this.bgColors = new Map([["toolSuccessBg", "\\u001B[44m"]]); }}
  fg(_color, text) {{ return text; }}
  bold(text) {{ return text; }}
  bg(color, text) {{ return this.bgColors.get(color) + text + "\\u001B[49m"; }}
}}
const view = renderLifecycleResult(
  {{ content: [{{ type: "text", text: "ok" }}] }},
  {{ expanded: true }},
  new ClassTheme(),
  {{ isError: false }},
  {{ kind: "started", tool: "teammate_spawn", subject: "reviewer", label: "spawn" }},
  ["detail line"],
);
const rendered = view.render(100).join("\\n");
console.log(JSON.stringify({{ painted: rendered.includes("\\u001B[44m"), rendered }}));
"""
    result = run_node(script)
    assert result["painted"], result["rendered"]


def test_activity_priority_tool_then_thinking_then_text(tmp_path: Path) -> None:
    payload = run_node(
        f'''\
        import {{ runningTeammateActivity }} from "{(SRC / "activity.ts").as_uri()}";
        const base = {{ name: "security", agent: "reviewer", spawnId: "s", pid: 1, status: "working", isolation: "none", createdAt: 1, updatedAt: 1 }};
        const withTool = runningTeammateActivity({{ ...base, activeTool: "bash: npm test", liveThinking: "**thinking**", liveText: "text" }});
        const withThinking = runningTeammateActivity({{ ...base, liveThinking: "reasoning about auth", liveText: "older text" }});
        const withText = runningTeammateActivity({{ ...base, liveText: "older\\nlatest" }});
        const fallback = runningTeammateActivity(base);
        console.log(JSON.stringify({{
          withTool, withThinking,
          latestLineWins: withText === "latest",
          fallback, fallbackIsWorking: fallback === "Working...",
        }}));
        '''
    )
    assert payload["withTool"] == "bash: npm test"
    assert payload["withThinking"] == "reasoning about auth"
    # The widget shows the LATEST non-empty line of streamed text.
    assert payload["latestLineWins"] is True
    assert payload["fallbackIsWorking"] is True


def test_rpc_control_stream_protocol_lines() -> None:
    spawner = source("spawner.ts")
    assert 'streamingBehavior: "followUp"' in spawner
    assert 'streamingBehavior: "steer"' in spawner
    assert '{ type: "steer", message }' not in spawner
    assert '"--mode", "rpc"' in spawner
    assert '"--no-session"' in spawner
    # The constitution: sequences are uncapped; the harness never terminates a
    # working child on its own — no budget counters, no auto-reclaim.
    assert "DEFAULT_TURN_BUDGET" not in spawner
    assert "turnBudgetExceeded" not in spawner
    assert "budgetExceeded" not in spawner
    # Residents never auto-exit after a report: no post-report grace shutdown.
    assert "finishReportedWorker" not in spawner
    assert "POST_REPORT_GRACE_MS" not in spawner


def test_resident_stream_limits_are_per_turn_and_fail_closed() -> None:
    spawner = source("spawner.ts")
    assert "MAX_JSONL_LINE_BYTES" in spawner
    assert "MAX_TURN_OUTPUT_BYTES" in spawner
    assert "outputLimitError" in spawner
    assert "terminateChildProcess" in spawner
    assert "failureReason" in spawner


def test_resident_unterminated_output_is_terminated_without_partial_success() -> None:
    payload = run_node(
        f'''\
        import fs from "node:fs";
        import os from "node:os";
        import path from "node:path";
        const root = fs.mkdtempSync(path.join(os.tmpdir(), "agent-teams-stream-limit-"));
        const pkg = path.join(root, "fake-package");
        fs.mkdirSync(pkg);
        fs.writeFileSync(path.join(pkg, "package.json"), JSON.stringify({{ name: "@earendil-works/pi-coding-agent" }}));
        const child = path.join(pkg, "cli.mjs");
        fs.writeFileSync(child, `
          process.stderr.write("child-diagnostic-noise".repeat(1000));
          setTimeout(() => process.stdout.write("x".repeat(Number(process.env.PI_LINE_LIMIT) + 1)), 50);
          process.on("SIGTERM", () => {{}});
          const stream = setInterval(() => process.stdout.write("x".repeat(4096)), 1);
          setTimeout(() => {{ clearInterval(stream); process.exit(0); }}, 1000);
        `, {{ mode: 0o755 }});
        const originalArgv1 = process.argv[1];
        process.argv[1] = child;
        process.env.PI_LINE_LIMIT = "1048576";
        const {{ spawnResident, MAX_JSONL_LINE_BYTES }} = await import("{(SRC / "spawner.ts").as_uri()}");
        process.env.PI_LINE_LIMIT = String(MAX_JSONL_LINE_BYTES);
        const outcome = await new Promise((resolve) => spawnResident({{
          workerName: "limit-test",
          cwd: root,
          onUpdate: () => {{}},
          onExit: (result) => resolve({{ exitCode: result.exitCode, stdout: result.stdout, stderr: result.stderr }}),
          onError: (error) => resolve({{ error: error.message }}),
        }}));
        process.argv[1] = originalArgv1;
        fs.rmSync(root, {{ recursive: true, force: true }});
        console.log(JSON.stringify(outcome));
        '''
    )
    assert payload["exitCode"] != 0
    assert payload["stdout"] == ""
    assert payload["stderr"].startswith("Resident worker JSONL line exceeded")
    assert "child-diagnostic-noise" in payload["stderr"]


def test_finish_entry_announces_assignment_finished() -> None:
    payload = run_node(
        f'''\
        import extension from "{(PACKAGE / "index.ts").as_uri()}";
        import {{ initTheme }} from "@earendil-works/pi-coding-agent";
        initTheme("dark");
        const renderers = new Map();
        extension({{
          on() {{}},
          registerCommand() {{}},
          registerEntryRenderer(type, renderer) {{ renderers.set(type, renderer); }},
          registerMessageRenderer() {{}},
          registerTool() {{}},
        }});
        const renderer = renderers.get("agent-teams-teammate-finished");
        const theme = {{ fg: (_color, text) => text, bold: (text) => text, bg: (_color, text) => text }};
        const lines = renderer({{ data: {{ teammate: "e2e-layout-luna" }} }}, {{}}, theme).render(80);
        console.log(JSON.stringify({{ lines }}));
        '''
    )
    assert any("Assignment for @e2e-layout-luna finished." in line for line in payload["lines"])
    assert not any("Teammate @" in line for line in payload["lines"])


def test_peer_traffic_stays_out_of_leader_context() -> None:
    machine = source("team-machine.ts")
    index_ts = source("index.ts")
    # Inbox routing never calls sendUpdate or deliverToLeader for peer messages.
    routing = machine[machine.index("export function routePeerInboxes"):machine.index("// ── Task intents")]
    assert "deliverToLeader" not in routing
    assert "sendUpdate" not in routing
    assert "dispatchInboxMessage" in machine
    # Only reports and harness diagnostics reach the leader mailbox.
    assert "receiveWorkerMessage" in machine
    assert "deliverFeedback" in machine


def test_board_path_is_stable_only_for_the_same_session_file(tmp_path: Path) -> None:
    payload = run_node(
        f'''\
        import {{ boardFilePath, sessionKey }} from "{(SRC / "statefile.ts").as_uri()}";
        const cwd = {str(tmp_path)!r};
        const first = "/sessions/first.jsonl";
        const second = "/sessions/second.jsonl";
        console.log(JSON.stringify({{
          sameSession: boardFilePath(first, cwd) === boardFilePath(first, cwd),
          differentSessions: boardFilePath(first, cwd) !== boardFilePath(second, cwd),
          sameKey: sessionKey(first, cwd) === sessionKey(first, cwd),
          differentKey: sessionKey(first, cwd) !== sessionKey(second, cwd),
        }}));
        '''
    )
    assert payload == {
        "sameSession": True,
        "differentSessions": True,
        "sameKey": True,
        "differentKey": True,
    }


def test_intermediate_worker_reports_reach_the_leader_queue(tmp_path: Path) -> None:
    payload = run_node(
        f'''\
        import {{ initTeamMachine, shutdownTeamMachine, drainTeammateOutboxes }} from "{(SRC / "team-machine.ts").as_uri()}";
        import {{ resetState, registerTeammate, getState }} from "{(SRC / "state.ts").as_uri()}";
        import {{ stateFilePath, workerOutboxPath, appendWorkerEvent }} from "{(SRC / "statefile.ts").as_uri()}";
        const sent = [];
        const cwd = {str(tmp_path)!r};
        initTeamMachine({{ sessionManager: undefined, cwd }}, {{ sendUpdate: (report) => sent.push(report), notifyChange: () => {{}} }});
        resetState();
        registerTeammate({{ name: "w", agent: "reviewer", spawnId: "s1", pid: 0, status: "working", isolation: "none", createdAt: 1, updatedAt: 1 }});
        const outbox = workerOutboxPath(stateFilePath(undefined, cwd), "w", "s1");
        appendWorkerEvent(outbox, {{ id: "evt1", type: "message", worker: "w", spawnId: "s1", body: "blocker: need model pin decision", status: "in_progress", timestamp: 222 }});
        appendWorkerEvent(outbox, {{ id: "evt2", type: "message", worker: "w", spawnId: "s1", body: "found the root cause" }});
        drainTeammateOutboxes();
        const mailboxEvt1 = getState().leaderMailbox.find((m) => m.id === "evt1");
        console.log(JSON.stringify({{
          bothQueued: sent.length === 2,
          noneTerminal: sent.every((report) => report.finished !== true),
          stampedFromRecord: sent[0].timestamp === 222,
          fallbackStamp: typeof sent[1].timestamp === "number",
          mailboxKeepsAuthoredAt: mailboxEvt1?.timestamp === 222,
          keepsEventEvidence: sent[0].eventId === "evt1" && sent[0].status === "in_progress"
            && sent[1].eventId === "evt2" && sent[1].status === undefined,
        }}));
        shutdownTeamMachine();
        '''
    )
    assert payload == {
        "bothQueued": True,
        "noneTerminal": True,
        "stampedFromRecord": True,
        "fallbackStamp": True,
        "mailboxKeepsAuthoredAt": True,
        "keepsEventEvidence": True,
    }


def test_terminal_report_closes_reporting_and_suppresses_following_reports(tmp_path: Path) -> None:
    payload = run_node(
        f'''\
        import {{ initTeamMachine, shutdownTeamMachine, drainTeammateOutboxes, sendLeaderMessage }} from "{(SRC / "team-machine.ts").as_uri()}";
        import {{ resetState, registerTeammate, getState }} from "{(SRC / "state.ts").as_uri()}";
        import {{ stateFilePath, workerOutboxPath, appendWorkerEvent }} from "{(SRC / "statefile.ts").as_uri()}";
        const sent = [];
        const cwd = {str(tmp_path)!r};
        initTeamMachine({{ sessionManager: undefined, cwd }}, {{ sendUpdate: (report) => sent.push(report), notifyChange: () => {{}} }});
        resetState();
        registerTeammate({{ name: "w", agent: "reviewer", spawnId: "s1", pid: 0, status: "working", isolation: "none", createdAt: 1, updatedAt: 1 }});
        const outbox = workerOutboxPath(stateFilePath(undefined, cwd), "w", "s1");
        appendWorkerEvent(outbox, {{ id: "evt1", type: "message", worker: "w", spawnId: "s1", body: "analysis", status: "in_progress" }});
        appendWorkerEvent(outbox, {{ id: "evt2", type: "message", worker: "w", spawnId: "s1", body: "recommendation", status: "in_progress" }});
        appendWorkerEvent(outbox, {{ id: "evt3", type: "message", worker: "w", spawnId: "s1", body: "review complete", status: "completed" }});
        appendWorkerEvent(outbox, {{ id: "evt4", type: "message", worker: "w", spawnId: "s1", body: "assignment complete", status: "completed" }});
        drainTeammateOutboxes();
        const afterTerminal = {{
          sent: sent.length,
          mailbox: getState().leaderMailbox.length,
          closed: getState().teammates.w.reportSequenceEnded === true,
          idle: getState().teammates.w.status === "idle",
          sequenceEnded: getState().teammates.w.sequenceEnded === true,
        }};
        sent.length = afterTerminal.sent;
        const replayBeforeWake = getState().leaderMailbox.length;
        drainTeammateOutboxes();
        const replayAfterWake = getState().leaderMailbox.length;
        const rejectedSteer = sendLeaderMessage("w", "please report again");
        const reopened = sendLeaderMessage("w", "review a distinct follow-up assignment", {{ reopen: true }});
        appendWorkerEvent(outbox, {{ id: "evt5", type: "message", worker: "w", spawnId: "s1", assignmentId: getState().teammates.w.assignment.id, body: "follow-up complete", status: "completed" }});
        drainTeammateOutboxes();
        console.log(JSON.stringify({{
          afterTerminal,
          sentBodies: sent.slice(0, afterTerminal.sent).map((report) => report.body),
          rejectedSteer: rejectedSteer.ok ? rejectedSteer.outcome : rejectedSteer.error,
          rejectedReport: rejectedSteer.ok && rejectedSteer.outcome === "not-sent" ? rejectedSteer.terminalReport : null,
          reopened: reopened.ok,
          reopenedPrior: reopened.ok ? (reopened.priorTerminalReport ?? null) : null,
          afterNewSequence: sent.length,
          mailboxAfterNewSequence: getState().leaderMailbox.length,
          mailboxBodies: getState().leaderMailbox.map((message) => message.body),
          replayBeforeWake,
          replayAfterWake,
        }}));
        shutdownTeamMachine();
        '''
    )
    rejected_steer = str(payload.pop("rejectedSteer"))
    rejected_report = payload.pop("rejectedReport")
    assert payload == {
        "afterTerminal": {"sent": 3, "mailbox": 3, "closed": True, "idle": False, "sequenceEnded": False},
        "sentBodies": ["analysis", "recommendation", "review complete"],
        "reopened": True,
        "reopenedPrior": "review complete",
        "afterNewSequence": 4,
        "mailboxAfterNewSequence": 4,
        "mailboxBodies": ["analysis", "recommendation", "review complete", "follow-up complete"],
        "replayBeforeWake": 3,
        "replayAfterWake": 3,
    }
    assert rejected_steer == "not-sent"
    # The leader reads the recorded report directly from the structured result
    # instead of steering the teammate into a duplicate resend.
    assert rejected_report == "review complete"


def test_worktree_cleanup_preserves_directory_when_commit_fails(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "t"], check=True)
    (tmp_path / "f.txt").write_text("one", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "base"], check=True)
    hooks = tmp_path / "hooks"
    hooks.mkdir()
    (hooks / "pre-commit").write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    (hooks / "pre-commit").chmod(0o755)
    subprocess.run(["git", "-C", str(tmp_path), "config", "core.hooksPath", str(hooks)], check=True)
    payload = run_node(
        f'''\
        import {{ createWorktree, captureWorktreeDiff, cleanupWorktree }} from "{(SRC / "worktree.ts").as_uri()}";
        import {{ spawnSync }} from "node:child_process";
        import * as fs from "node:fs";
        const cwdUri = "{tmp_path.as_uri()}";
        const root = cwdUri.startsWith("file://") ? cwdUri.slice(7) : cwdUri;
        const setup = createWorktree(root, "doomed-commit");
        if ("error" in setup) throw new Error(setup.error);
        fs.writeFileSync(setup.path + "/precious.txt", "only copy");
        captureWorktreeDiff(setup);
        const cleaned = cleanupWorktree(setup);
        const workStillOnDisk = fs.existsSync(setup.path + "/precious.txt");
        // Cleanup must not have force-removed the directory over a failed commit.
        console.log(JSON.stringify({{
          failed: !cleaned.ok,
          namesDirectory: cleaned.error?.includes("worktree left in place") ?? false,
          workStillOnDisk,
        }}));
        '''
    )
    assert payload == {
        "failed": True,
        "namesDirectory": True,
        "workStillOnDisk": True,
    }


def test_worktree_cleanup_keeps_branch_and_cleans_failed_spawns(tmp_path: Path) -> None:
    subprocess.run([
        "git", "init", "-q", str(tmp_path),
    ], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "t"], check=True)
    (tmp_path / "f.txt").write_text("one", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "base"], check=True)
    payload = run_node(
        f'''\
        import {{ createWorktree, captureWorktreeDiff, cleanupWorktree }} from "{(SRC / "worktree.ts").as_uri()}";
        import {{ spawnSync }} from "node:child_process";
        const cwdUri = "{tmp_path.as_uri()}";
        const setup = createWorktree(cwdUri.startsWith("file://") ? cwdUri.slice(7) : cwdUri, "demo");
        if ("error" in setup) throw new Error(setup.error);
        const fs = await import("node:fs");
        fs.writeFileSync(setup.path + "/patched.txt", "work");
        const captured = captureWorktreeDiff(setup);
        const kept = cleanupWorktree(setup);
        const branchAlive = spawnSync("git", ["-C", setup.repoRoot, "rev-parse", "--verify", setup.branch]);
        const diffWorks = spawnSync("git", ["-C", setup.repoRoot, "diff", setup.baseCommit + ".." + setup.branch]);
        const fresh = createWorktree(cwdUri.startsWith("file://") ? cwdUri.slice(7) : cwdUri, "doomed");
        let discardedBranchGone = true;
        if (!("error" in fresh)) {{
          cleanupWorktree(fresh, {{ deleteBranch: true }});
          discardedBranchGone = spawnSync("git", ["-C", fresh.repoRoot, "rev-parse", "--verify", fresh.branch]).status !== 0;
        }}
        console.log(JSON.stringify({{
          capturedOk: captured.ok,
          cleanupOk: kept.ok,
          worktreeDirGone: !fs.existsSync(setup.path),
          branchAlive: branchAlive.status === 0,
          diffRetrievable: diffWorks.status === 0 && (diffWorks.stdout || "").includes("patched.txt"),
          discardedBranchGone,
        }}));
        '''
    )
    assert payload == {
        "capturedOk": True,
        "cleanupOk": True,
        "worktreeDirGone": True,
        "branchAlive": True,
        "diffRetrievable": True,
        "discardedBranchGone": True,
    }


def test_worktree_capture_failure_returns_structured_error(tmp_path: Path) -> None:
    payload = run_node(
        f'''\
        import {{ captureWorktreeDiff, createWorktree }} from "{(SRC / "worktree.ts").as_uri()}";
        const outside = createWorktree("{tmp_path.as_uri()[7:]}", "nope");
        console.log(JSON.stringify({{
          createFailsCleanly: "error" in outside,
        }}));
        ''',
    )
    assert payload["createFailsCleanly"] is True


def test_read_receipts_and_legacy_registry_are_gone() -> None:
    all_sources = "".join(source(name) for name in (
        "types.ts", "state.ts", "statefile.ts", "team-machine.ts", "worker.ts", "tools.ts", "ui.ts",
    ))
    for legacy in ("read receipt", "readReceipt", "markMessageRead", "broadcast"):
        assert legacy.lower() not in all_sources.lower(), legacy
    assert "ephemeral" not in all_sources.lower()

def test_teammate_report_message_renderer_toggles_with_mouse_click() -> None:
    payload = run_node(
        f'''\
        import extension from "{(PACKAGE / "index.ts").as_uri()}";
        import {{ TEAMMATE_REPORT_MESSAGE_TYPE }} from "{(SRC / "leader-reports.ts").as_uri()}";
        import {{ initTheme }} from "@earendil-works/pi-coding-agent";

        initTheme();

        const messageRenderers = new Map();
        const fakePi = {{
          registerEntryRenderer() {{}},
          registerMessageRenderer(type, renderer) {{ messageRenderers.set(type, renderer); }},
          registerTool() {{}},
          registerCommand() {{}},
          on() {{}},
        }};
        extension(fakePi);

        const renderer = messageRenderers.get(TEAMMATE_REPORT_MESSAGE_TYPE);
        const message = {{
          customType: TEAMMATE_REPORT_MESSAGE_TYPE,
          content: "Audit complete",
          details: [
            {{
              teammate: "audit",
              agent: "audit",
              body: "PASS with verified evidence.",
            }}
          ],
        }};

        const theme = {{
          fg: (color, text) => `<${{color}}>${{text}}</${{color}}>`,
          bg: (_color, text) => text,
          bold: (text) => text,
        }};

        const comp = renderer(message, {{ expanded: false, outputPad: 1 }}, theme);
        const collapsedLines = comp.render(120);
        // Mouse click on content row (y: 0 in child coordinates)
        const clickRes1 = comp.handleMouse({{ type: "click", button: "left", x: 10, y: 0 }});
        const expandedLines = comp.render(120);
        const clickRes2 = comp.handleMouse({{ type: "click", button: "left", x: 10, y: 0 }});
        const reCollapsedLines = comp.render(120);

        console.log(JSON.stringify({{
          hasHandleMouse: typeof comp.handleMouse === "function",
          click1Handled: clickRes1?.handled,
          collapsed: collapsedLines,
          expanded: expandedLines,
          click2Handled: clickRes2?.handled,
          reCollapsed: reCollapsedLines,
        }}));
        '''
    )
    assert payload["hasHandleMouse"] is True
    assert payload["click1Handled"] is True
    assert "[message] from" in payload["collapsed"][1]
    assert "@audit" in payload["collapsed"][1]
    assert "to expand" in payload["collapsed"][1]
    assert "PASS with verified evidence" not in payload["collapsed"][1]
    assert "PASS with verified evidence" in " ".join(payload["expanded"])
    assert payload["click2Handled"] is True
    assert "[message] from" in payload["reCollapsed"][1]
    assert "to expand" in payload["reCollapsed"][1]
