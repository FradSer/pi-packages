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
    "teammate_spawn",
    "teammate_shutdown",
    "send_message",
    "task_create",
    "task_list",
}
WORKER_TOOLS = {
    "send_message",
    "task_list",
    "task_claim",
    "task_submit",
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


def test_bdd_contract_covers_target_resources() -> None:
    feature = (PACKAGE / "features" / "agent-teams.feature").read_text(encoding="utf-8")
    for phrase in (
        "Feature: Agent Teams collaborative organization contract",
        "Agents are declarative Markdown files",
        "Discover agents from user, project, and project-local scopes",
        "Generated roles stay in memory by default",
        "Generated roles can be persisted only after an explicit request",
        "Project scopes distinguish git-managed from local definitions",
        "xxx.local.md files mark personal overrides inside .pi/agents",
        "Local override files dedupe against their shared counterpart by teammate name",
        "Agent frontmatter declares tools, model, verify, and worktree; the body is the role prompt",
        "Multi-line YAML tool lists are declared like inline lists",
        "An unknown agent name fails the spawn",
        "Teammates are named resident processes",
        "Spawning creates one named resident teammate",
        "Teammate names are unique among living teammates",
        "The session-wide cap bounds resident teammates",
        "Idle teammates are suspended between turns",
        "Shutdown stops one teammate and frees its slot",
        "An unexpected teammate crash is reported to the leader",
        "Teammates do not survive session shutdown",
        "Teammates run without turn or duration caps",
        "no configuration may automatically terminate a working teammate",
        "Messaging is peer-to-peer through local inboxes",
        "Teammates exchange messages directly by name",
        "Delivered messages wake an idle teammate automatically",
        "Messages reach a working teammate without dropping",
        "Inbox delivery is at-least-once and deduplicated",
        "Peer traffic never enters the leader's model context",
        "Reports to the leader use the unified send_message primitive",
        "A report enters Pi's native follow-up queue while the leader is active",
        "Direct-assignment completion is delivered without leader busywork",
        "Team status clears use the shared Pi-kit transient-status adapter",
        "A terminal report closes reporting until a new wake-up",
        "A terminal worker report ends its current worker turn",
        "Suppressed report events remain replay-safe",
        "The leader addresses a living teammate by name through send_message",
        "A teammate whose last report lacks terminal status is asked to self-finalize first",
        "neither request nor reminder repeats within the same spawn incarnation",
        "A repeated unfinalized idle transition escalates to the leader",
        "the shared task_list view includes the living roster on both leader and worker sides",
        "Stale spawn events cannot affect a newer teammate incarnation",
        "The task board is shared coordination state",
        "The leader creates tasks; teammates never do",
        "Creating a task reports the next execution action",
        "Creating a task wakes an existing idle teammate immediately",
        "Only resident teammates self-claim tasks",
        "Dependencies gate claimability",
        "Claimed tasks are released when their holder stops",
        "Completion is submitted by the claimer and gated by verify",
        "Failed submissions keep the task claimable by its holder",
        "The board persists across restarts while the runtime does not",
        "Board state has one writer",
        "The harness wakes idle teammates, the leader model never polls",
        "Claimable-task notices respect a per-teammate pacing interval",
        "Leader tool surface is exact",
        "Workers cannot access leader tools",
        "Teammate models resolve at spawn time",
        "The inherit alias pins the leader's current model",
        "An explicit role pin overrides inherit and the team default",
        "A role without a model uses the team default model",
        "Without a role model and without a team default no --model flag passes",
        "The console sets and clears the unified teammate model",
        "Worktree isolation is an agent-role option",
        "Console and widget visualize the team without intercepting input",
        "The agent-teams command opens the console directly",
        "Non-TUI sessions receive a text summary instead of the console",
        "The console roster separates session teammates from persistent agent roles",
        "A role row opens a read-only definition preview",
        "Teammates are shut down from the console with confirmation",
        "The widget shows only working teammates",
        "idle and stopped teammates never appear above the input box",
        "the widget stays hidden when nobody is working",
        "including idle and stopped teammates",
        "Spawning renders one started line per teammate",
        "Acceptance workflow — three-way review with cross-challenge",
    ):
        assert phrase in feature, phrase


def test_leader_tool_surface_is_exact() -> None:
    ext = source("index.ts") + source("tools.ts") + source("worker.ts")
    for tool in LEADER_TOOLS:
        assert f'name: "{tool}"' in ext, tool
    for tool in REMOVED_TOOLS:
        assert f'name: "{tool}"' not in ext, tool
    assert source("tools.ts").count('name: "task_list"') == 0
    assert source("worker.ts").count('name: "task_list"') == 1


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
          suggestsClaim: prompt.includes("task_claim"),
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


def test_direct_kickoff_executes_without_checking_task_list() -> None:
    feature = (PACKAGE / "features" / "agent-teams.feature").read_text(encoding="utf-8")
    assert "Direct kickoff tasks execute immediately without querying the task board" in feature
    guidance = source("guidance.ts")
    assert "When you have an assigned task" in guidance
    assert "without calling task_list" in guidance
    assert "terminal report is the sole completion signal" in guidance
    assert "direct-assignment teammate or reviewer is still working" in guidance

    payload = run_node(
        f'''\
        import {{ buildKickoffPrompt }} from "{(SRC / "team-machine.ts").as_uri()}";
        const withTask = buildKickoffPrompt("w1", "worker", "role", "implement feature X", "none");
        const withoutTask = buildKickoffPrompt("w1", "worker", "role", undefined, "none");
        console.log(JSON.stringify({{
          withTaskHasDirectInstruction: withTask.includes("Execute this assigned task directly. Do not call task_list"),
          withTaskHasBody: withTask.includes("implement feature X"),
          withoutTaskChecksBoard: withoutTask.includes("check the task board with task_list and claim suitable work with task_claim"),
        }}));
        '''
    )
    assert payload["withTaskHasDirectInstruction"] is True
    assert payload["withTaskHasBody"] is True
    assert payload["withoutTaskChecksBoard"] is True


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


def test_board_notices_are_one_shot_and_verify_loops_escalate() -> None:
    machine = source("team-machine.ts")
    types = source("types.ts")
    feature = (PACKAGE / "features" / "agent-teams.feature").read_text(encoding="utf-8")
    for phrase in (
        "Declined claimable work does not wake an idle teammate twice",
        "Released tasks are noticeable again",
        "Repeated verify failures escalate instead of looping",
    ):
        assert phrase in feature, phrase
    assert "noticedTaskIds" in types
    assert "rearmTaskNotice" in machine
    assert "freshClaimableTasks(teammate.noticedTaskIds" in machine
    assert "VERIFY_FAILURE_ESCALATE_AFTER" in machine
    # Released tasks re-arm notices for every living teammate.
    assert machine.count("rearmTaskNotice(intent.taskId)") >= 1
    wake = machine[machine.index("export function wakeIdleTeammates") :]
    assert "freshClaimableTasks(teammate.noticedTaskIds, claimableTasks().filter" in wake
    assert "const boardEligible = teammate.assignment === undefined" in wake
    assert "markTasksNoticed(teammate.name" in wake


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


def test_unknown_agent_spawn_error_is_actionable() -> None:
    payload = run_node(
        f'''\
        import {{ unknownAgentError }} from "{(SRC / "team-machine.ts").as_uri()}";
        console.log(JSON.stringify({{ message: unknownAgentError("ghost-role", "/tmp/proj") }}));
        '''
    )
    message = payload["message"]
    assert "ghost-role" in message
    assert "/tmp/proj/.pi/agents" in message
    assert "stale" in message
    assert "definition" in message
    assert "references/agent-roles.md" in message
    guidance = source("guidance.ts")
    assert "resolved live at spawn time" in guidance
    feature = (PACKAGE / "features" / "agent-teams.feature").read_text(encoding="utf-8")
    assert "Spawning an unknown agent names the recovery path" in feature


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


def test_verify_failure_residue_is_cleared_when_a_holder_is_released() -> None:
    machine = source("team-machine.ts")
    feature = (PACKAGE / "features" / "agent-teams.feature").read_text(encoding="utf-8")
    assert "A stopped holder leaves no verify-failure residue" in feature
    close = machine[machine.index("async function handleTeammateClose") :]
    synth = machine[machine.index("export async function shutdownTeammate") : machine.index("async function handleTeammateClose")]
    for section in (close, synth):
        assert "verifyFailures.delete(`${task.id}:${teammate.spawnId}`)" in section


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
          none: resolveSpawnModel(undefined, undefined, "google/gemini-3-pro"),
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
    assert payload["inheritWithoutLeaderModel"] == {"source": "none"}
    assert payload["blankPinIsUnset"] == {"model": "openai/gpt-5.2", "source": "team-default"}


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


def test_console_wires_searchable_teammate_model_picker() -> None:
    ui_source = source("ui.ts")
    for needle in (
        'createSearchPicker',
        'modelSearchText',
        'fuzzyFilter',
        'setTeamDefaultModel',
        'getAvailable()',
    ):
        assert needle in ui_source, f"console picker must use {needle}"
    # Key routing lives in the pure mapPickerKey table; the console handler
    # must consume it instead of matching raw letters itself.
    assert "mapPickerKey" in ui_source
    picker_input = ui_source[ui_source.index("function handlePickerInput"):]
    assert 'data === "c"' not in picker_input
    assert "isClearEntry" in ui_source
    feature = (PACKAGE / "features" / "agent-teams.feature").read_text(encoding="utf-8")
    assert "a searchable model picker lists registry models with type-to-filter" in feature
    assert "confirming the pinned clear entry restores Pi's own choice" in feature


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
    assert "TEAMMATE_SPAWN_GUIDANCE" in index_ts
    assert "? buildTeamLeaderGuidance" in index_ts


def test_team_status_clear_uses_pi_kit_transient_status_adapter() -> None:
    index = (PACKAGE / "src" / "index.ts").read_text(encoding="utf-8")
    assert 'clearPiStatus(ctx.ui, "teammate")' in index
    assert 'ctx.ui.setStatus("teammate", undefined)' not in index


def test_guidance_is_static_and_team_shaped() -> None:
    guidance = source("guidance.ts")
    feature = (PACKAGE / "features" / "agent-teams.feature").read_text(encoding="utf-8")
    assert "Prompt guidance reflects the team model" in feature
    assert "DO NOT poll or sleep" in guidance
    assert "or unsolicited steers" in guidance
    assert "delivers its terminal report automatically" in guidance
    assert "teammate_spawn(name, agent, optional kickoff prompt)" in guidance
    assert r"required \`agent\` role" in guidance
    assert "task_create(subject, description?, dependsOn?," in guidance
    assert "Peer traffic never reaches your" in guidance
    assert "resident teammate" in source("guidance.ts")
    # Worker protocol covers the five capabilities and mid-turn arrivals.
    for capability in ("send_message", "task_list", "task_claim", "task_submit"):
        assert capability in guidance
    assert 'to="leader"' in guidance
    assert "may arrive mid-turn" in guidance
    payload = run_node(
        f'''\
        import {{ buildTeamLeaderGuidance }} from "{(SRC / "guidance.ts").as_uri()}";
        const first = buildTeamLeaderGuidance("/tmp");
        const second = buildTeamLeaderGuidance("/tmp");
        console.log(JSON.stringify({{
          identical: first === second,
          noLiveState: !(first.includes("run_") || first.includes("@")),
        }}));
        '''
    )
    assert payload["identical"] is True
    assert payload["noLiveState"] is True


def test_first_turn_guidance_explains_how_to_create_a_role_on_demand() -> None:
    payload = run_node(
        f'''\
        import {{ TEAMMATE_SPAWN_GUIDANCE }} from "{(SRC / "guidance.ts").as_uri()}";
        console.log(JSON.stringify({{
          hasNoBuiltins: TEAMMATE_SPAWN_GUIDANCE.includes("no built-in roles"),
          requiresName: TEAMMATE_SPAWN_GUIDANCE.includes("`name`"),
          requiresAgent: TEAMMATE_SPAWN_GUIDANCE.includes("required `agent` role"),
          requiresDefinition: TEAMMATE_SPAWN_GUIDANCE.includes("`definition`"),
          explainsRegistration: TEAMMATE_SPAWN_GUIDANCE.includes("registered in memory under"),
          explainsAgentEquivalence: TEAMMATE_SPAWN_GUIDANCE.includes("agents / sub-agents"),
          routesAgentRequests: TEAMMATE_SPAWN_GUIDANCE.includes("teammate_spawn"),
        }}));
        '''
    )
    assert payload == {
        "hasNoBuiltins": True,
        "requiresName": True,
        "requiresAgent": True,
        "requiresDefinition": True,
        "explainsRegistration": True,
        "explainsAgentEquivalence": True,
        "routesAgentRequests": True,
    }


def test_unknown_agent_error_gives_the_complete_inline_spawn_recovery() -> None:
    team_machine = source("team-machine.ts")
    assert "name and an existing agent role id" in team_machine
    assert "name, a new agent role id, and an inline definition" in team_machine
    assert "includes description and prompt" in team_machine


def test_follow_up_reports_use_wrapped_marker_format() -> None:
    payload = run_node(
        f'''\
        import {{ formatReports }} from "{(SRC / "follow-up-queue.ts").as_uri()}";
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


def test_follow_up_queue_serializes_and_retries_with_backoff() -> None:
    payload = run_node(
        f'''\
        import {{ FollowUpQueue }} from "{(SRC / "follow-up-queue.ts").as_uri()}";
        const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
        const events = [];
        let settled = true;
        const queue = new FollowUpQueue({{
          isIdle: () => settled,
          agentStartTimeoutMs: 80,
          retryBaseDelayMs: 10,
          retryMaxDelayMs: 20,
          maxAttempts: 2,
          dispatch: (reports) => {{ events.push(["dispatch", reports.length]); }},
          onFailure: (message) => {{ events.push(["fail"]); }},
        }});
        queue.enqueue({{ teammate: "a", body: "one", finished: true }});
        await sleep(5);
        queue.onBeforeAgentStart(undefined);
        // No matching prompt was prepared: watchdog fires and retry begins.
        await sleep(150);
        console.log(JSON.stringify({{
          dispatchedTwice: events.filter(([kind]) => kind === "dispatch").length >= 2,
          failuresObserved: events.some(([kind]) => kind === "fail"),
        }}));
        '''
    )
    assert payload["dispatchedTwice"] is True
    assert payload["failuresObserved"] is True


def test_follow_up_queue_archives_stopped_spawn_reports_before_dispatch() -> None:
    payload = run_node(
        f'''\
        import {{ FollowUpQueue }} from "{(SRC / "follow-up-queue.ts").as_uri()}";
        const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
        const dispatches = [];
        const queue = new FollowUpQueue({{
          isIdle: () => true,
          prepareOnDispatch: true,
          dispatch: (reports) => dispatches.push(reports.map((report) => report.body).join(",")),
        }});
        queue.enqueue({{ teammate: "late", spawnId: "old", body: "late report" }});
        queue.archiveSpawn("old");
        await sleep(10);
        console.log(JSON.stringify({{
          noDispatch: dispatches.length === 0,
          pendingEmpty: queue.pendingCount === 0,
          archived: queue.archivedCount,
        }}));
        '''
    )
    assert payload == {"noDispatch": True, "pendingEmpty": True, "archived": 1}


def test_follow_up_queue_dispatches_each_report_as_its_own_turn() -> None:
    payload = run_node(
        f'''\
        import {{ FollowUpQueue }} from "{(SRC / "follow-up-queue.ts").as_uri()}";
        const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
        const dispatches = [];
        let settled = true;
        const queue = new FollowUpQueue({{
          isIdle: () => settled,
          prepareOnDispatch: true,
          dispatch: (reports, content) => dispatches.push({{ count: reports.length, content }}),
        }});
        queue.enqueue({{ teammate: "b", body: "1", finished: true, timestamp: 111 }});
        queue.enqueue({{ teammate: "a", body: "2" }});
        queue.enqueue({{ teammate: "b", body: "3" }});
        for (let turn = 0; turn < 3; turn++) {{
          await sleep(5);
          queue.onAgentStart();
          queue.onAgentSettled();
        }}
        await sleep(5);
        console.log(JSON.stringify({{
          dispatchCount: dispatches.length,
          sizes: dispatches.map((d) => d.count).join(","),
          contents: dispatches.map((d) => d.content),
          pendingEmpty: queue.pendingCount === 0,
        }}));
        '''
    )
    # No coalescing: three enqueued reports become three single-report turns,
    # in arrival order, even when consecutive reports share a sender.
    assert payload["dispatchCount"] == 3
    assert payload["sizes"] == "1,1,1"
    assert '<agent-message from="b" at="1970-01-01T00:00:00.111Z">' in payload["contents"][0]
    assert '<agent-message from="a">' in payload["contents"][1]
    assert '<agent-message from="b">\n3\n</agent-message>' in payload["contents"][2]
    assert payload["pendingEmpty"] is True


def test_follow_up_queue_dispatches_while_leader_is_active() -> None:
    payload = run_node(
        f'''\
        import {{ FollowUpQueue }} from "{(SRC / "follow-up-queue.ts").as_uri()}";
        const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
        const dispatches = [];
        let leaderActive = true;
        const queue = new FollowUpQueue({{
          isIdle: () => !leaderActive,
          prepareOnDispatch: true,
          dispatch: (reports) => dispatches.push(reports.map((report) => report.body).join(",")),
        }});
        queue.enqueue({{ teammate: "first", body: "first report" }});
        queue.enqueue({{ teammate: "second", body: "second report" }});
        await sleep(10);
        const whileActive = {{ dispatches: [...dispatches], pending: queue.pendingCount }};
        leaderActive = false;
        queue.onAgentSettled();
        await sleep(10);
        console.log(JSON.stringify({{
          whileActive,
          afterSettlement: {{ dispatches, pending: queue.pendingCount }},
        }}));
        '''
    )
    assert payload["whileActive"] == {"dispatches": ["first report"], "pending": 2}
    assert payload["afterSettlement"] == {"dispatches": ["first report", "second report"], "pending": 1}


def test_console_supports_mouse_wheel_scrolling() -> None:
    ext = source("ui.ts")
    # One SGR wheel parser shared by the list page and detail views.
    assert "function wheelDelta(data: string): number | undefined" in ext
    assert "/^\\x1b\\[<(\\d+);\\d+;\\d+[Mm]$/" in ext
    assert "(button & 64) === 0" in ext
    assert ext.count("const wheel = wheelDelta(data);") == 2


def test_agent_teams_command_opens_console_directly() -> None:
    tools = source("tools.ts")
    ui = source("ui.ts")
    guidance = source("guidance.ts")
    feature = (PACKAGE / "features" / "agent-teams.feature").read_text(encoding="utf-8")

    # Single-action entry: the command opens the console with no menu.
    assert 'pi.registerCommand("agent-teams"' in tools
    assert 'pi.registerCommand("teammate"' not in tools
    assert "ctx.ui.select(" not in tools
    assert "openTeamConsole(ctx)" in tools

    # The session-history generation flow is gone; creation is conversational.
    assert "createAgentFromHistory" not in tools
    assert "generateAgentPrompt" not in tools
    assert "parseGeneratedAgents" not in tools
    assert "teammate_spawn" in guidance  # conversational spawn stays routed to the tool
    assert ".pi/agents/<name>.md" in guidance  # explicit persistence writes definitions
    assert "${AGENT_REFERENCE_PATH}" in guidance  # on-demand generation consults shipped templates
    assert "no built-in roles" in guidance
    assert "bundled" not in guidance

    # The console is the management surface for both entity kinds.
    assert "buildRoleDetail" in ui
    assert "== teammates (this session) ==" in ui
    assert "== agent roles (persistent and session definitions) ==" in ui
    assert "discoverAgents" in ui

    # No stale references to the legacy command name anywhere user-visible;
    # the deprecation line in the contract is the one allowed mention.
    assert "/teammate" not in guidance
    teammate_feature_lines = [line.strip() for line in feature.splitlines() if "/teammate" in line]
    assert teammate_feature_lines == ["And the legacy /teammate command is not registered"]
    assert "/agent-teams" in guidance
    assert "/agent-teams" in feature


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
    assert 'ctx.ui.setWidget("teammate", undefined)' in widget
    assert "placement: \"belowEditor\"" in widget
    # Only working or starting teammates appear above the input box.
    assert "for (const teammate of working)" in widget
    assert 'teammate.status === "working" || teammate.status === "starting"' in widget
    assert "fitTeammateRow" in widget
    # Idle and stopped teammates never render in the widget: no dim rows, no markers.
    assert "style.dim(" not in widget
    assert "○" not in widget and "\u25a0" not in widget
    assert "listTeammates()" not in widget

def test_spawn_uses_one_native_text_started_line() -> None:
    tools = source("tools.ts")
    feature = (PACKAGE / "features" / "agent-teams.feature").read_text(encoding="utf-8")
    assert "Spawning renders one started line per teammate" in feature
    assert "formatToolLifecycleTitle({" in tools
    assert 'kind: "started"' in tools
    assert 'const prefix = theme.fg("customMessageLabel", theme.bold("[agent]"));' in tools
    assert 'return new Text(`${prefix} ${title}`, 0, 0);' in tools
    assert "renderLifecycleResult(" not in tools.split('name: "teammate_spawn"', 1)[1].split('name: "teammate_shutdown"', 1)[0]
    assert "formatAgentTaskName" in tools
    assert "details: { started: true }" in tools


def test_spawn_started_line_uses_one_native_text_row() -> None:
    tools = source("tools.ts")
    assert 'const prefix = theme.fg("customMessageLabel", theme.bold("[agent]"));' in tools
    assert 'return new Text(`${prefix} ${title}`, 0, 0);' in tools
    assert "native Text component wraps the row at the available width" in (
        PACKAGE / "features" / "agent-teams.feature"
    ).read_text(encoding="utf-8")


def test_render_lifecycle_result_survives_class_based_theme() -> None:
    script = f"""
import {{ initTheme }} from "@earendil-works/pi-coding-agent";
import {{ renderLifecycleResult }} from "{(SRC / "tool-render.ts").as_uri()}";

initTheme("dark");
class ClassTheme {{
  constructor() {{ this.bgColors = new Map([["customMessageBg", "\\u001B[44m"]]); }}
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


def test_teammate_spawn_started_row_fits_narrow_transcript_widths() -> None:
    feature = (PACKAGE / "features" / "agent-teams.feature").read_text(encoding="utf-8")
    assert "The teammate_spawn started row fits narrow transcript widths" in feature
    assert "started row shows the assignment without duplicate identity or tools" in feature
    payload = run_node(
        f'''\
        import {{ initTheme }} from "@earendil-works/pi-coding-agent";
        import {{ visibleWidth }} from "@earendil-works/pi-tui";
        import {{ registerLeaderTools }} from "{(SRC / "tools.ts").as_uri()}";
        initTheme("dark");
        const tools = [];
        registerLeaderTools({{ registerTool(tool) {{ tools.push(tool); }}, registerCommand() {{}} }});
        const spawn = tools.find((tool) => tool.name === "teammate_spawn");
        const theme = {{ fg: (color, text) => `<${{color}}>${{text}}</${{color}}>`, bold: (text) => `<bold>${{text}}</bold>`, bg: (_color, text) => text }};
        const renderRow = (width) => spawn.renderResult(
          {{ content: [{{ type: "text", text: "started" }}] }},
          {{}},
          theme,
          {{ args: {{ name: "very-long-teammate-name", agent: "reviewer", prompt: "Investigate the narrow transcript rendering regression" }} }},
        ).render(width);
        const rows = [1, 8, 16, 24].map((width) => ({{ width, lines: renderRow(width) }}));
        const row = renderRow(24)[0];
        const longPrompt = "Review the current uncommitted implementation for the Ox Alpha name-only co-author flow end to end";
        const wideLongRow = spawn.renderResult(
          {{ content: [{{ type: "text", text: "started" }}] }},
          {{}},
          theme,
          {{ args: {{ name: "coauthor-reviewer", agent: "reviewer", prompt: longPrompt }} }},
        ).render(200)[0];
        const fullResult = {{ content: [{{ type: "text", text: "@storm-auditor is alive as storm-auditor.\\nIt received the standard board-check kickoff." }}] }};
        const expandedRows = spawn.renderResult(fullResult, {{ expanded: true }}, theme, {{ args: {{ name: "storm-auditor", agent: "storm-auditor" }} }}).render(200);
        const collapsedWideRow = spawn.renderResult(fullResult, {{}}, theme, {{ args: {{ name: "storm-auditor", agent: "storm-auditor" }} }}).render(200)[0];
        const emptyContentRow = spawn.renderResult(
          {{ content: [], details: {{ started: true }} }},
          {{}},
          theme,
          {{ args: {{ name: "greeter-reload-test", agent: "reviewer", prompt: "short kickoff" }} }},
        ).render(120)[0];
        console.log(JSON.stringify({{
          row,
          collapsedWideRow,
          expandedRows,
          nativeTextRows: rows.every(({{ lines }}) => lines.length >= 1 && !lines.some((line) => line.includes("to expand"))),
          wideRowKeepsFullAssignment: visibleWidth(wideLongRow) > 100 && wideLongRow.includes("end to end"),
          rowIsSingleLine: !row.includes("\\n"),
          rowFitsWidth: visibleWidth(row) <= 24,
          zeroWidthLines: spawn.renderResult(
            {{ content: [{{ type: "text", text: "started" }}] }},
            {{}},
            theme,
            {{ args: {{ name: "name", agent: "reviewer", prompt: "task" }} }},
          ).render(0).length === 0,
          identifiesStarted: collapsedWideRow.includes("@storm-auditor started · check task board"),
          colorsOnlyAgentPrefix: collapsedWideRow.startsWith("<customMessageLabel><bold>[agent]</bold></customMessageLabel> @storm-auditor started · check task board") && !collapsedWideRow.slice("<customMessageLabel><bold>[agent]</bold></customMessageLabel>".length).includes("<customMessageLabel>"),
          collapsedHasExpandHint: collapsedWideRow.includes("to expand"),
          emptyContentHasExpandHint: emptyContentRow.includes("to expand"),
          expandedShowsResult: expandedRows.some((line) => line.includes("is alive as storm-auditor")),
          expandedHidesTools: expandedRows.every((line) => !line.includes("tools:")),
        }}));
        '''
    )
    assert payload["nativeTextRows"] is True
    assert payload["wideRowKeepsFullAssignment"] is True
    assert payload["rowIsSingleLine"] is True
    assert payload["rowFitsWidth"] is True
    assert payload["identifiesStarted"] is True
    assert payload["colorsOnlyAgentPrefix"] is True
    assert payload["collapsedHasExpandHint"] is False
    assert payload["emptyContentHasExpandHint"] is False
    assert payload["expandedShowsResult"] is False
    assert payload["expandedHidesTools"] is True


def test_shutdown_renders_one_collapsible_agent_event_line() -> None:
    tools = source("tools.ts")
    feature = (PACKAGE / "features" / "agent-teams.feature").read_text(encoding="utf-8")
    assert "Shutting down renders one collapsible agent event line" in feature
    assert "eventToolLifecycle(" in tools
    assert "renderLifecycleResult(" in tools
    assert "expandHint: keyHint(" in source("tool-render.ts")


def test_shutdown_row_hides_details_behind_the_shared_expand_hint() -> None:
    payload = run_node(
        f'''\
        import {{ registerLeaderTools }} from "{(SRC / "tools.ts").as_uri()}";
        import {{ initTheme }} from "@earendil-works/pi-coding-agent";
        initTheme("dark");
        const tools = [];
        registerLeaderTools({{ registerTool(tool) {{ tools.push(tool); }}, registerCommand() {{}} }});
        const shutdown = tools.find((tool) => tool.name === "teammate_shutdown");
        const theme = {{ fg: (_color, text) => text, bold: (text) => text, bg: (_color, text) => text }};
        const render = (expanded, width = 100) => shutdown.renderResult(
          {{ content: [{{ type: "text", text: "Teammate @scribe shut down (exit code 0).\\nLifetime usage: 1200 tokens, $0.0012." }}] }},
          {{ expanded }},
          theme,
          {{ args: {{ name: "scribe" }} }},
        ).render(width);
        const collapsed = render(false);
        const expandedRows = render(true);
        console.log(JSON.stringify({{
          collapsed,
          expandedRows,
          zeroWidthCollapsedIsEmpty: render(false, 0).length === 0,
          collapsedIsSingleLine: collapsed.length === 3 && collapsed[0].trim() === "" && collapsed[2].trim() === "" && !collapsed[1].includes("\\n"),
          collapsedNamesAgentEvent: collapsed[1].includes("[agent] @scribe shut down"),
          collapsedHasSharedHint: collapsed[1].includes(" · ") && collapsed[1].includes("to expand"),
          expandedKeepsTitle: expandedRows[1].includes("[agent] @scribe shut down") && !expandedRows[1].includes("to expand"),
          expandedRevealsDetails: expandedRows.some((line) => line.includes("exit code 0"))
            && expandedRows.some((line) => line.includes("Lifetime usage")),
          neverLabeledMonitor: !collapsed.join(" ").includes("[monitor]"),
        }}));
        '''
    )
    assert payload["zeroWidthCollapsedIsEmpty"] is True
    assert payload["collapsedIsSingleLine"] is True
    assert payload["collapsedNamesAgentEvent"] is True
    assert payload["collapsedHasSharedHint"] is True
    assert payload["expandedKeepsTitle"] is True
    assert payload["expandedRevealsDetails"] is True
    assert payload["neverLabeledMonitor"] is True


def test_send_message_renders_one_routing_line() -> None:
    tools = source("tools.ts")
    feature = (PACKAGE / "features" / "agent-teams.feature").read_text(encoding="utf-8")
    assert "Sending renders one routing line per message" in feature
    block = tools.split('name: "send_message"', 1)[1]
    assert 'renderShell: "self"' in block
    assert "renderCall: emptyToolCall" in block
    assert "eventToolLifecycle(" in block
    assert "renderLifecycleResult(" in block
    assert "outcome" in block
    assert "stalledMs" not in block.split('name: "task_create"', 1)[0]
    # Pi signals failures via the render context, handled by the shared adapter.
    assert "context.isError" in source("tool-render.ts")
    assert "result as { isError?: boolean }" not in tools


def test_send_message_routing_row_stays_single_and_carries_only_routing_outcome() -> None:
    payload = run_node(
        f'''\
        import {{ registerLeaderTools }} from "{(SRC / "tools.ts").as_uri()}";
        import {{ initTheme }} from "@earendil-works/pi-coding-agent";
        initTheme("dark");
        const tools = [];
        registerLeaderTools({{ registerTool(tool) {{ tools.push(tool); }}, registerCommand() {{}} }});
        const send = tools.find((tool) => tool.name === "send_message");
        const shutdown = tools.find((tool) => tool.name === "teammate_shutdown");
        const theme = {{ fg: (_color, text) => text, bold: (text) => text, bg: (_color, text) => text }};
        const render = (details, width = 100) => send.renderResult(
          {{ content: [{{ type: "text", text: "Routing accepted." }}], details }},
          {{}},
          theme,
          {{ args: {{ to: "audit", message: "hello" }} }},
        ).render(width);
        const errorRow = send.renderResult(
          {{ content: [{{ type: "text", text: "No living teammate named ghost." }}], details: {{}} }},
          {{}},
          theme,
          {{ args: {{ to: "ghost", message: "hi" }}, isError: true }},
        ).render(100).join("\\n");
        const shutdownErrorRow = shutdown.renderResult(
          {{ content: [{{ type: "text", text: "No living teammate named ghost." }}], details: {{}} }},
          {{ expanded: false }},
          theme,
          {{ args: {{ name: "ghost" }}, isError: true }},
        ).render(100).join("\\n");
        console.log(JSON.stringify({{
          callEmpty: send.renderCall({{ to: "audit" }}, theme).render(100).join("") === "",
          steeredRow: render({{ outcome: "steered" }}),
          queuedRow: render({{ outcome: "queued" }}),
          unrelatedDetailIgnored: render({{ outcome: "steered", silenceMs: 125_000 }}),
          zeroWidthEmpty: render({{ outcome: "steered" }}, 0).length === 0,
          routingIsSingleLine: render({{ outcome: "steered" }}).length === 3 && render({{ outcome: "steered" }})[0].trim() === "" && render({{ outcome: "steered" }})[2].trim() === "",
          noDuplicateSentence: !render({{ outcome: "steered" }})[1].includes("Routing accepted"),
          errorIsExactPlainLine: errorRow.trim() === "No living teammate named ghost." && !errorRow.includes("·"),
          shutdownErrorIsPlainLine: shutdownErrorRow.trim() === "No living teammate named ghost."
            && !shutdownErrorRow.startsWith("[agent]") && !shutdownErrorRow.includes("to expand"),
        }}));
        '''
    )
    assert payload["callEmpty"] is True
    for key, outcome in (
        ("steeredRow", "steered"),
        ("queuedRow", "queued"),
        ("unrelatedDetailIgnored", "steered"),
    ):
        assert f"[message] to @audit · {outcome}" in payload[key][1]
        assert "to expand" in payload[key][1]
    assert payload["zeroWidthEmpty"] is True
    assert payload["routingIsSingleLine"] is True
    assert payload["noDuplicateSentence"] is True
    assert payload["errorIsExactPlainLine"] is True
    assert payload["shutdownErrorIsPlainLine"] is True


def test_leader_tools_are_progressively_disclosed_by_team_and_board_state() -> None:
    feature = (PACKAGE / "features" / "agent-teams.feature").read_text(encoding="utf-8")
    assert "Leader controls follow living-team and board state" in feature
    payload = run_node(
        f'''\
        import {{ registerLeaderTools, refreshLeaderToolDisclosure }} from "{(SRC / "tools.ts").as_uri()}";
        import {{ resetState, registerTeammate, createTask, updateTeammate }} from "{(SRC / "state.ts").as_uri()}";
        let active = ["read", "teammate_spawn", "teammate_shutdown", "send_message", "task_create", "task_list"];
        const pi = {{ registerTool() {{}}, getActiveTools() {{ return active; }}, setActiveTools(next) {{ active = next; }} }};
        resetState();
        registerLeaderTools(pi);
        refreshLeaderToolDisclosure();
        const initial = [...active];
        registerTeammate({{ name: "worker", agent: "worker", spawnId: "s1", pid: 1, status: "idle", isolation: "none", createdAt: 1, updatedAt: 1 }});
        refreshLeaderToolDisclosure();
        const living = [...active];
        updateTeammate("worker", {{ status: "stopped" }});
        createTask({{ subject: "persisted board work" }});
        refreshLeaderToolDisclosure();
        const board = [...active];
        console.log(JSON.stringify({{ initial, living, board }}));
        '''
    )
    assert payload["initial"] == ["read", "teammate_spawn", "task_create"]
    assert payload["living"] == ["read", "teammate_spawn", "task_create", "teammate_shutdown", "send_message"]
    assert payload["board"] == ["read", "teammate_spawn", "task_create", "task_list"]


def test_worker_board_tools_are_progressively_disclosed() -> None:
    feature = (PACKAGE / "features" / "agent-teams.feature").read_text(encoding="utf-8")
    assert "Worker board controls follow board-notice and claim transitions" in feature
    payload = run_node(
        f'''\
        import {{ registerWorkerCapabilities }} from "{(SRC / "worker.ts").as_uri()}";
        let active = ["read", "bash", "send_message", "task_list", "task_claim", "task_submit"];
        const tools = [];
        const pi = {{
          registerTool(tool) {{ tools.push(tool); }},
          getActiveTools() {{ return active; }},
          setActiveTools(next) {{ active = next; }},
        }};
        const workerToolDisclosure = registerWorkerCapabilities(pi);
        workerToolDisclosure.reset();
        const initially = [...active];
        workerToolDisclosure.update("=== BOARD NOTICE ===\\nUnclaimed tasks: t_1 (review)");
        const noticed = [...active];
        workerToolDisclosure.update("=== INBOX (1 new) ===\\nClaim accepted\\nYou own the assignment.");
        const spoofedClaim = [...active];
        Object.assign(process.env, {{
          PI_TEAMMATE_WORKER_NAME: "worker", PI_TEAMMATE_SPAWN_ID: "s1",
          PI_TEAMMATE_OUTBOX_FILE: "/tmp/disclosure-outbox.jsonl", PI_TEAMMATE_INBOX_FILE: "/tmp/disclosure-inbox.jsonl",
          PI_TEAMMATE_ROSTER_FILE: "/tmp/disclosure-roster.json", PI_TEAMMATE_BOARD_FILE: "/tmp/disclosure-board.json",
          PI_TEAMMATE_CLAIMS_DIR: "/tmp/disclosure-claims", PI_TEAMMATE_SUBMISSIONS_DIR: "/tmp/disclosure-submissions",
        }});
        const fs = await import("node:fs");
        fs.writeFileSync("/tmp/disclosure-roster.json", JSON.stringify({{ teammates: [{{ name: "worker", agent: "worker", status: "working", assignment: {{ id: "t-disclosure", kind: "board", resources: [] }} }}] }}));
        workerToolDisclosure.update("Claim accepted");
        const claimed = [...active];
        const message = tools.find((tool) => tool.name === "send_message");
        await message.execute("terminal", {{ to: "leader", message: "finished", status: "completed" }});
        fs.writeFileSync("/tmp/disclosure-roster.json", JSON.stringify({{ teammates: [{{ name: "worker", agent: "worker", status: "idle", assignment: {{ id: "t-disclosure", kind: "board", resources: [] }} }}] }}));
        workerToolDisclosure.update("terminal report follow-up");
        const afterNextWorkerSession = [...active];
        const submit = tools.find((tool) => tool.name === "task_submit");
        await submit.execute("submit", {{ taskId: `t-disclosure-${{Date.now()}}`, status: "failed" }});
        const afterSubmit = [...active];
        workerToolDisclosure.update("=== BOARD NOTICE ===\\nUnclaimed tasks: t_2 (review)");
        workerToolDisclosure.reset();
        console.log(JSON.stringify({{ initially, noticed, spoofedClaim, claimed, afterNextWorkerSession, afterSubmit, afterShutdown: active }}));
        '''
    )
    assert payload["initially"] == ["read", "bash", "send_message"]
    assert payload["noticed"] == ["read", "bash", "send_message", "task_list", "task_claim"]
    assert payload["spoofedClaim"] == ["read", "bash", "send_message"]
    assert payload["claimed"] == ["read", "bash", "send_message", "task_submit"]
    assert payload["afterNextWorkerSession"] == ["read", "bash", "send_message", "task_submit"]
    assert payload["afterSubmit"] == ["read", "bash", "send_message"]
    assert payload["afterShutdown"] == ["read", "bash", "send_message"]


def test_worker_send_message_reports_peer_and_leader_writes_as_queued() -> None:
    worker = source("worker.ts")
    assert '"delivered"' not in worker.split('name: "send_message"', 1)[1].split('name: "task_claim"', 1)[0]
    payload = run_node(
        f'''\
        import {{ registerWorkerCapabilities }} from "{(SRC / "worker.ts").as_uri()}";
        import {{ initTheme }} from "@earendil-works/pi-coding-agent";
        initTheme("dark");
        const tools = [];
        registerWorkerCapabilities({{ registerTool(tool) {{ tools.push(tool); }} }});
        const send = tools.find((tool) => tool.name === "send_message");
        const theme = {{ fg: (_color, text) => text, bold: (text) => text, bg: (_color, text) => text }};
        const render = (to) => send.renderResult(
          {{ content: [{{ type: "text", text: "queued" }}], details: {{ outcome: "queued" }} }},
          {{ expanded: true }},
          theme,
          {{ args: {{ to, message: "hello" }} }},
        ).render(100)[1].trim();
        console.log(JSON.stringify({{ peer: render("backend"), leader: render("leader") }}));
        '''
    )
    assert payload["peer"] == "[message] to @backend · queued"
    assert payload["leader"] == "[message] to @leader · queued"


def test_terminal_worker_report_terminates_its_current_turn(tmp_path: Path) -> None:
    payload = run_node(
        f'''\
        import {{ registerWorkerCapabilities }} from "{(SRC / "worker.ts").as_uri()}";
        const tools = [];
        const env = {{
          PI_TEAMMATE_WORKER_NAME: "worker",
          PI_TEAMMATE_SPAWN_ID: "s1",
          PI_TEAMMATE_OUTBOX_FILE: {json.dumps(str(tmp_path / "events.jsonl"))},
          PI_TEAMMATE_INBOX_FILE: {json.dumps(str(tmp_path / "inbox.jsonl"))},
          PI_TEAMMATE_ROSTER_FILE: {json.dumps(str(tmp_path / "roster.json"))},
          PI_TEAMMATE_BOARD_FILE: {json.dumps(str(tmp_path / "board.json"))},
          PI_TEAMMATE_CLAIMS_DIR: {json.dumps(str(tmp_path / "claims"))},
          PI_TEAMMATE_SUBMISSIONS_DIR: {json.dumps(str(tmp_path / "submissions"))},
        }};
        Object.assign(process.env, env);
        registerWorkerCapabilities({{ registerTool(tool) {{ tools.push(tool); }} }});
        const send = tools.find((tool) => tool.name === "send_message");
        const intermediate = await send.execute("intermediate", {{ to: "leader", message: "progress", status: "in_progress" }});
        const unstated = await send.execute("unstated", {{ to: "leader", message: "finding" }});
        const completed = await send.execute("completed", {{ to: "leader", message: "done", status: "completed" }});
        const failed = await send.execute("failed", {{ to: "leader", message: "failed", status: "failed" }});
        console.log(JSON.stringify({{
          intermediateTerminates: intermediate.terminate === true,
          unstatedTerminates: unstated.terminate === true,
          completedTerminates: completed.terminate === true,
          failedTerminates: failed.terminate === true,
        }}));
        '''
    )
    assert payload == {
        "intermediateTerminates": False,
        "unstatedTerminates": False,
        "completedTerminates": True,
        "failedTerminates": True,
    }


def test_leader_send_message_ignores_stray_status_instead_of_throwing(tmp_path: Path) -> None:
    feature = (PACKAGE / "features" / "agent-teams.feature").read_text(encoding="utf-8")
    assert "a stray status field on a leader-sent message does not block delivery" in feature
    tools = source("tools.ts")
    assert 'status is reserved' not in tools
    payload = run_node(
        f'''\
        import {{ registerLeaderTools }} from "{(SRC / "tools.ts").as_uri()}";
        import {{ initTeamMachine, shutdownTeamMachine }} from "{(SRC / "team-machine.ts").as_uri()}";
        import {{ registerTeammate }} from "{(SRC / "state.ts").as_uri()}";
        const tools = [];
        registerLeaderTools({{ registerTool(tool) {{ tools.push(tool); }}, registerCommand() {{}} }});
        const send = tools.find((tool) => tool.name === "send_message");
        const dir = process.env.PI_TEST_DIR;
        initTeamMachine(
          {{ sessionManager: {{ getSessionFile: () => undefined }}, cwd: dir, model: undefined }},
          {{ sendUpdate() {{}}, notifyChange() {{}} }},
        );
        registerTeammate({{ name: "audit", agent: "worker", spawnId: "s1", pid: 0, status: "idle", isolation: "none", createdAt: 1, updatedAt: 1 }});
        let stray = null;
        try {{
          stray = (await send.execute("t1", {{ to: "audit", message: "please audit the theme", status: "in_progress" }})).content[0].text;
        }} catch (error) {{
          stray = `THREW: ${{error.message}}`;
        }}
        const normal = (await send.execute("t2", {{ to: "audit", message: "again" }})).content[0].text;
        shutdownTeamMachine();
        console.log(JSON.stringify({{ stray, normal }}));
        ''',
        env_overrides={"PI_TEST_DIR": str(tmp_path)},
    )
    assert not payload["stray"].startswith("THREW:"), payload["stray"]
    assert payload["stray"].startswith("MESSAGING\nQUEUED · to=@audit")
    assert "status ignored" in payload["stray"]
    assert payload["normal"].startswith("MESSAGING\nQUEUED · to=@audit")


def test_send_message_renders_recorded_terminal_report_without_resend(tmp_path: Path) -> None:
    feature = (PACKAGE / "features" / "agent-teams.feature").read_text(encoding="utf-8")
    assert "The leader reads a recorded terminal report without forcing a resend" in feature
    assert "Reading a terminal report renders a structured message event" in feature
    payload = run_node(
        f'''\
        import {{ registerLeaderTools }} from "{(SRC / "tools.ts").as_uri()}";
        import {{ initTheme }} from "@earendil-works/pi-coding-agent";
        import {{ initTeamMachine, shutdownTeamMachine, drainTeammateOutboxes }} from "{(SRC / "team-machine.ts").as_uri()}";
        import {{ registerTeammate }} from "{(SRC / "state.ts").as_uri()}";
        import {{ stateFilePath, workerOutboxPath, appendWorkerEvent }} from "{(SRC / "statefile.ts").as_uri()}";
        initTheme("dark");
        const tools = [];
        registerLeaderTools({{ registerTool(tool) {{ tools.push(tool); }}, registerCommand() {{}} }});
        const send = tools.find((tool) => tool.name === "send_message");
        const theme = {{ fg: (_color, text) => text, bold: (text) => text, bg: (_color, text) => text }};
        const dir = process.env.PI_TEST_DIR;
        initTeamMachine(
          {{ sessionManager: {{ getSessionFile: () => undefined }}, cwd: dir, model: undefined }},
          {{ sendUpdate() {{}}, notifyChange() {{}} }},
        );
        registerTeammate({{ name: "audit", agent: "reviewer", spawnId: "s1", pid: 0, status: "working", isolation: "none", createdAt: 1, updatedAt: 1 }});
        const outbox = workerOutboxPath(stateFilePath(undefined, dir), "audit", "s1");
        const reportTail = "REPORT-END-6d42";
        const report = `VERDICT: PASS with evidence ${{"x".repeat(6_000)}} ${{reportTail}}`;
        appendWorkerEvent(outbox, {{ id: "evt1", type: "message", worker: "audit", spawnId: "s1", body: report, status: "completed" }});
        drainTeammateOutboxes();
        const readback = await send.execute("t1", {{ to: "audit", message: "please resend your report" }});
        const render = (expanded, width = 120) => send.renderResult(
          readback,
          {{ expanded }},
          theme,
          {{ args: {{ to: "audit", message: "please resend your report" }} }},
        ).render(width);
        const reopened = (await send.execute("t2", {{ to: "audit", message: "audit the follow-up patch", reopen: true }})).content[0].text;
        shutdownTeamMachine();
        console.log(JSON.stringify({{
          readback: readback.content[0].text,
          details: readback.details,
          collapsed: render(false),
          expanded: render(true),
          narrowExpanded: render(true, 30),
          reportTail,
          reopened,
        }}));
        ''',
        env_overrides={"PI_TEST_DIR": str(tmp_path)},
    )
    assert "ROUTING · not sent" in payload["readback"]
    assert "VERDICT: PASS with evidence" in payload["readback"]
    assert payload["details"]["terminalReportAvailable"] is True
    assert payload["details"]["outcome"] == "not-sent"
    assert len(payload["collapsed"]) == 3
    assert "[message] to @audit · terminal report available" in payload["collapsed"][1]
    assert "to expand" in payload["collapsed"][1]
    assert all("VERDICT: PASS with evidence" not in line for line in payload["collapsed"])
    expanded = " ".join("\n".join(payload["expanded"]).split())
    assert "No new message was delivered" in expanded
    assert "duplicate leader turn" in expanded
    assert "VERDICT: PASS with evidence" in expanded
    # detailLimit="all" preserves a long report at narrow width; the tail
    # would disappear if pi-kit's default 50-detail cap applied.
    assert len(payload["narrowExpanded"]) > 53
    assert any(payload["reportTail"] in line for line in payload["narrowExpanded"])
    assert payload["reopened"].startswith("MESSAGING\nQUEUED · to=@audit")
    assert "duplicate delivery" in payload["reopened"]
    assert "PRIOR TERMINAL REPORT · VERDICT: PASS with evidence" in payload["reopened"]


def test_task_create_explains_execution_state_and_current_session(tmp_path: Path) -> None:
    feature = (PACKAGE / "features" / "agent-teams.feature").read_text(encoding="utf-8")
    assert "Creating a task reports the next execution action" in feature
    assert "task_create never spawns one automatically" in feature
    payload = run_node(
        f'''\
        import {{ initTeamMachine, shutdownTeamMachine, createBoardTask, formatBoardTaskCreation }} from "{(SRC / "team-machine.ts").as_uri()}";
        initTeamMachine({{ sessionManager: undefined, cwd: {str(tmp_path)!r} }}, {{ sendUpdate() {{}}, notifyChange() {{}} }});
        const created = createBoardTask({{ subject: "Skill prompt injection" }});
        console.log(JSON.stringify({{
          ok: created.ok,
          living: created.ok ? created.livingTeammates : null,
          notified: created.ok ? created.notifiedTeammates : null,
          text: created.ok ? formatBoardTaskCreation("Skill prompt injection", created) : null,
        }}));
        shutdownTeamMachine();
        '''
    )
    assert payload["ok"] is True
    assert payload["living"] == 0
    assert payload["notified"] == []
    text = str(payload["text"])
    assert "BOARD · current session" in text
    assert "no living teammates" in text
    assert "teammate_spawn" in text


def test_task_create_handoff_formats_each_execution_state() -> None:
    payload = run_node(
        f'''\
        import {{ formatBoardTaskCreation }} from "{(SRC / "team-machine.ts").as_uri()}";
        const base = {{ ok: true, id: "task", notifiedTeammates: [], livingTeammates: 0, claimable: true, supersededTaskIds: [] }};
        console.log(JSON.stringify({{
          noWorker: formatBoardTaskCreation("task", base),
          notified: formatBoardTaskCreation("task", {{ ...base, livingTeammates: 1, notifiedTeammates: ["reviewer"] }}),
          busy: formatBoardTaskCreation("task", {{ ...base, livingTeammates: 1 }}),
          blocked: formatBoardTaskCreation("task", {{ ...base, claimable: false }}),
        }}));
        '''
    )
    assert "teammate_spawn" in str(payload["noWorker"])
    assert "@reviewer" in str(payload["notified"])
    assert "no eligible idle teammate" in str(payload["busy"])
    assert "waits for dependencies" in str(payload["blocked"])


def test_task_create_renders_one_created_line() -> None:
    tools = source("tools.ts")
    feature = (PACKAGE / "features" / "agent-teams.feature").read_text(encoding="utf-8")
    assert "Creating a board task renders one created line" in feature
    block = tools.split('name: "task_create"', 1)[1].split('name: "task_list"', 1)[0]
    assert 'renderShell: "self"' in block
    assert "renderCall: emptyToolCall" in block
    assert "eventToolLifecycle(" in block
    assert 'label: "created"' in block
    payload = run_node(
        f'''\
        import {{ registerLeaderTools }} from "{(SRC / "tools.ts").as_uri()}";
        import {{ initTheme }} from "@earendil-works/pi-coding-agent";
        initTheme("dark");
        const tools = [];
        registerLeaderTools({{ registerTool(tool) {{ tools.push(tool); }}, registerCommand() {{}} }});
        const create = tools.find((tool) => tool.name === "task_create");
        const theme = {{ fg: (_color, text) => text, bold: (text) => text, bg: (_color, text) => text }};
        const render = (width = 100) => create.renderResult(
          {{ content: [{{ type: "text", text: "Created [t_3] Fix the login flow." }}], details: {{}} }},
          {{}},
          theme,
          {{ args: {{ subject: "Fix the login flow" }} }},
        ).render(width);
        const errorRow = create.renderResult(
          {{ content: [{{ type: "text", text: "Unknown dependency id in [t_9]." }}], details: {{}} }},
          {{}},
          theme,
          {{ args: {{ subject: "Broken task", dependsOn: ["t_9"] }}, isError: true }},
        ).render(100).join("\\n");
        console.log(JSON.stringify({{
          callEmpty: create.renderCall({{ subject: "x" }}, theme).render(100).join("") === "",
          createdRow: render(),
          zeroWidthEmpty: render(0).length === 0,
          noDuplicateSentence: !render()[1].includes("Idle teammates are notified"),
          errorIsPlainLine: errorRow.trim() === "Unknown dependency id in [t_9]." && !errorRow.includes("[board]"),
        }}));
        '''
    )
    assert payload["callEmpty"] is True
    assert "[board] created · Fix the login flow" in payload["createdRow"][1]
    assert "to expand" in payload["createdRow"][1]
    assert payload["zeroWidthEmpty"] is True
    assert payload["noDuplicateSentence"] is True
    assert payload["errorIsPlainLine"] is True


def test_completion_announced_once_per_spawn_incarnation() -> None:
    machine = source("team-machine.ts")
    extension = source("index.ts")
    feature = (PACKAGE / "features" / "agent-teams.feature").read_text(encoding="utf-8")
    assert "Completion is announced once per spawn incarnation" in feature
    # Both close paths (requested shutdown and unexpected stop) key their
    # terminal report on the incarnation so display dedup works per spawn.
    close = machine[machine.index("async function handleTeammateClose") :]
    assert close.count("spawnId: teammate.spawnId,") >= 2
    assert "markTeammateFinished(report)" in extension
    assert "announcedFinishKeys.clear()" in machine


def test_shutdown_after_finish_renders_no_second_event_line(tmp_path: Path) -> None:
    payload = run_node(
        f'''\
        import {{ initTeamMachine, shutdownTeamMachine, markTeammateFinished, hasAnnouncedFinish }} from "{(SRC / "team-machine.ts").as_uri()}";
        import {{ resetState, registerTeammate, updateTeammate }} from "{(SRC / "state.ts").as_uri()}";
        initTeamMachine({{ sessionManager: undefined, cwd: {str(tmp_path)!r} }}, {{ sendUpdate: () => {{}}, notifyChange: () => {{}} }});
        resetState();
        registerTeammate({{ name: "w", agent: "reviewer", spawnId: "s1", pid: 0, status: "stopped", isolation: "none", createdAt: 1, updatedAt: 1 }});
        const firstAnnounces = markTeammateFinished({{ teammate: "w", spawnId: "s1", body: "done", finished: true }});
        const currentIncarnationAnnounced = hasAnnouncedFinish("w");
        const repeatSuppressed = markTeammateFinished({{ teammate: "w", spawnId: "s1", body: "again", finished: true }});
        updateTeammate("w", {{ spawnId: "s2", status: "working" }});
        const respawnIncarnationQuiet = hasAnnouncedFinish("w");
        console.log(JSON.stringify({{
          firstAnnounces,
          currentIncarnationAnnounced,
          repeatSuppressed,
          respawnIncarnationQuiet,
        }}));
        shutdownTeamMachine();
        '''
    )
    assert payload == {
        "firstAnnounces": True,
        "currentIncarnationAnnounced": True,
        "repeatSuppressed": False,
        "respawnIncarnationQuiet": False,
    }
    tools = source("tools.ts")
    feature = (PACKAGE / "features" / "agent-teams.feature").read_text(encoding="utf-8")
    assert "Shutdown after a finish announcement adds no second event line" in feature
    assert "Shutdown without a finish announcement keeps its event line" in feature
    # The finished entry already announced this end of life; the event row is noise.
    # Suppression also covers terminal reports still queued for dispatch.
    assert "if (hasAnnouncedFinish(name) || hasTerminalReport(name))" in tools


def test_requested_shutdown_does_not_enqueue_harness_follow_up(tmp_path: Path) -> None:
    payload = run_node(
        f'''\
        import {{ initTeamMachine, shutdownTeamMachine, shutdownTeammate }} from "{(SRC / "team-machine.ts").as_uri()}";
        import {{ resetState, registerTeammate, getState }} from "{(SRC / "state.ts").as_uri()}";
        const sent = [];
        const cwd = {str(tmp_path)!r};
        initTeamMachine({{ sessionManager: undefined, cwd }}, {{ sendUpdate: (report) => sent.push(report), notifyChange: () => {{}} }});
        resetState();
        registerTeammate({{ name: "w", agent: "reviewer", spawnId: "s1", pid: 0, status: "working", isolation: "none", createdAt: 1, updatedAt: 1 }});
        const result = await shutdownTeammate("w");
        console.log(JSON.stringify({{
          shutdownSucceeded: result.ok,
          noFollowUp: sent.length === 0,
          mailboxKeepsSummary: getState().leaderMailbox.some((message) => message.subject === "Teammate shut down"),
        }}));
        shutdownTeamMachine();
        '''
    )
    assert payload == {
        "shutdownSucceeded": True,
        "noFollowUp": True,
        "mailboxKeepsSummary": True,
    }


def test_peer_only_kickoff_does_not_synthesize_leader_report() -> None:
    machine = source("team-machine.ts")
    feature = (PACKAGE / "features" / "agent-teams.feature").read_text(encoding="utf-8")
    assert "A peer-only kickoff does not synthesize a leader report" in feature
    assert "noticeKickoffWithoutReport" not in machine
    assert "kickoff-without-report" not in machine
    assert "kickoffPrompt" not in machine
    # A worker can remain idle while waiting for peer mail; only its own
    # explicit send_message(to="leader", ...) enters the leader pipeline.
    idle_transition = machine[machine.index("if (progress.finalResponse && teammate.status !== \"idle\")"):]
    idle_transition = idle_transition[: idle_transition.index("export function formatAgentHealthReport")]
    assert "nudgeIfUnfinalized(name, spawnId)" in idle_transition
    assert "deliverToLeader" not in idle_transition


def test_shutdown_suppression_covers_queued_terminal_reports(tmp_path: Path) -> None:
    payload = run_node(
        f'''\
        import {{ initTeamMachine, shutdownTeamMachine, drainTeammateOutboxes, hasTerminalReport }} from "{(SRC / "team-machine.ts").as_uri()}";
        import {{ resetState, registerTeammate }} from "{(SRC / "state.ts").as_uri()}";
        import {{ stateFilePath, workerOutboxPath, appendWorkerEvent }} from "{(SRC / "statefile.ts").as_uri()}";
        const sent = [];
        const cwd = {str(tmp_path)!r};
        initTeamMachine({{ sessionManager: undefined, cwd }}, {{ sendUpdate: (report) => sent.push(report), notifyChange: () => {{}} }});
        resetState();
        registerTeammate({{ name: "w", agent: "reviewer", spawnId: "s1", pid: 0, status: "working", isolation: "none", createdAt: 1, updatedAt: 1 }});
        const outbox = workerOutboxPath(stateFilePath(undefined, cwd), "w", "s1");
        appendWorkerEvent(outbox, {{ id: "evt1", type: "message", worker: "w", spawnId: "s1", body: "done", status: "completed" }});
        drainTeammateOutboxes();
        console.log(JSON.stringify({{
          terminalSentToQueue: sent.length === 1 && sent[0].finished === true,
          suppressionCoversQueuedReport: hasTerminalReport("w"),
          finishEntryNotDispatchedYet: true,
        }}));
        shutdownTeamMachine();
        '''
    )
    assert payload == {
        "terminalSentToQueue": True,
        "suppressionCoversQueuedReport": True,
        "finishEntryNotDispatchedYet": True,
    }


def test_live_activity_renders_markdown_without_literal_emphasis_markers() -> None:
    payload = run_node(
        f'''\
        import {{ fitTeammateRow, renderActivityMarkdown }} from "{(SRC / "activity.ts").as_uri()}";
        import {{ visibleWidth }} from "@earendil-works/pi-tui";
        const emphasis = renderActivityMarkdown("**Inspecting unused variable in report code**");
        const row = fitTeammateRow("⠼", "security", "**Inspecting unused variable**", 48);
        console.log(JSON.stringify({{
          emphasis,
          emphasisHasMarkers: emphasis.includes("**"),
          rowHasMarkers: row.includes("**"),
          rowIsSingleLine: !row.includes("\\n"),
          rowFitsWidth: visibleWidth(row) <= 47,
        }}));
        '''
    )
    assert payload["emphasis"] == "Inspecting unused variable in report code"
    assert payload["emphasisHasMarkers"] is False
    assert payload["rowHasMarkers"] is False
    assert payload["rowIsSingleLine"] is True
    assert payload["rowFitsWidth"] is True


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


def test_consolidated_tool_schemas_keep_one_message_primitive() -> None:
    types = source("types.ts")
    tools = source("tools.ts")
    worker = source("worker.ts")
    assert 'export const LEADER_RECIPIENT = "leader"' in types
    message_schema = types[types.index("export const SendMessageParams"):types.index("/** Self-claim")]
    assert "message: Type.String" in message_schema
    assert "subject: Type.String" not in message_schema
    assert "body: Type.String" not in message_schema
    assert "TeammateMessageParams" not in types
    assert "TeammateLeaderMessageParams" not in types
    spawn_schema = types[types.index("export const TeammateSpawnParams"):types.index("/** Shut down")]
    assert "definition: Type.Optional" in spawn_schema
    assert "persist" in spawn_schema and "persistScope" in spawn_schema
    assert "cwd:" not in spawn_schema
    assert 'name: "send_message"' in tools
    assert 'name: "send_message"' in worker
    assert 'name: "teammate_message"' not in tools + worker
    assert "agent.worktree" in source("team-machine.ts")


def test_rpc_control_stream_protocol_lines() -> None:
    spawner = source("spawner.ts")
    assert '{ type: "prompt", id: randomUUID(), message }' in spawner
    assert '{ type: "steer", message }' in spawner
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


def test_session_cap_and_shutdown_surface() -> None:
    machine = source("team-machine.ts")
    tools = source("tools.ts")
    assert "MAX_SESSION_WORKERS = 8" in machine
    assert "livingTeammates().length >= MAX_SESSION_WORKERS" in machine
    assert "DEFAULT_NOTICE_PACE_MS = 5 * 60 * 1000" in machine
    assert 'readDurationEnv("PI_TEAMMATE_NOTICE_PACE_MS", DEFAULT_NOTICE_PACE_MS)' in machine
    assert "shutdownTeammate" in tools and "teammate_shutdown" in tools
    assert "pendingShutdowns" in machine
    assert "releaseTasksOf" in machine


def test_harness_reports_have_a_distinct_event_renderer() -> None:
    feature = (PACKAGE / "features" / "agent-teams.feature").read_text(encoding="utf-8")
    index_ts = source("index.ts")
    queue = source("follow-up-queue.ts")
    assert "event uses a harness-event envelope instead of an agent-message envelope" in feature
    assert "TEAMMATE_HARNESS_MESSAGE_TYPE" in index_ts
    assert "registerMessageRenderer(TEAMMATE_HARNESS_MESSAGE_TYPE" in index_ts
    assert 'return `<harness-event type="${type}" subject="${subject}"${at}>' in queue
    assert 'type: "worktree-capture-failed"' in source("team-machine.ts")
    assert 'type: "worktree-cleanup-failed"' in source("team-machine.ts")
    machine = source("team-machine.ts")
    capture_failure = machine[machine.index('type: "worktree-capture-failed"') - 250 : machine.index('type: "worktree-capture-failed"') + 250]
    cleanup_failure = machine[machine.index('type: "worktree-cleanup-failed"') - 250 : machine.index('type: "worktree-cleanup-failed"') + 250]
    assert "sendUpdate" in capture_failure
    assert "sendUpdate" in cleanup_failure
    payload = run_node(
        f'''\
        import extension from "{(SRC / "index.ts").as_uri()}";
        const TEAMMATE_HARNESS_MESSAGE_TYPE = "agent-teams-harness";
        import {{ initTheme }} from "@earendil-works/pi-coding-agent";
        initTheme("dark");
        const renderers = new Map();
        extension({{
          on() {{}},
          registerCommand() {{}},
          registerEntryRenderer() {{}},
          registerMessageRenderer(name, renderer) {{ renderers.set(name, renderer); }},
          registerTool() {{}},
        }});
        const renderer = renderers.get(TEAMMATE_HARNESS_MESSAGE_TYPE);
        const message = {{
          content: "@audit stopped unexpectedly.",
          details: {{
            origin: "harness",
            harnessEvent: {{ type: "unexpected-stop", subject: "@audit stopped unexpectedly" }},
            body: "@audit stopped unexpectedly.",
          }},
        }};
        const theme = {{ fg: (_color, text) => text, bold: (text) => text, bg: (_color, text) => text }};
        const collapsed = renderer(message, {{ expanded: false, outputPad: 0 }}, theme).render(100);
        const expanded = renderer(message, {{ expanded: true, outputPad: 0 }}, theme).render(100);
        console.log(JSON.stringify({{
          collapsedEvent: collapsed.some((line) => line.includes("[agent] @audit stopped unexpectedly")),
          noAgentEnvelope: !collapsed.join("\\n").includes("[message] from @audit"),
          expandedDiagnostic: expanded.some((line) => line.includes("stopped unexpectedly")),
        }}));
        '''
    )
    assert payload == {
        "collapsedEvent": True,
        "noAgentEnvelope": True,
        "expandedDiagnostic": True,
    }


def test_stall_report_has_a_distinct_agent_health_event_renderer() -> None:
    feature = (PACKAGE / "features" / "agent-teams.feature").read_text(encoding="utf-8")
    index_ts = source("index.ts")
    machine = source("team-machine.ts")
    assert "one `[agent] @name stalled · silent <duration>` row" in feature
    assert "message routing rows never repeat the teammate health state" in feature
    assert "TEAMMATE_HEALTH_MESSAGE_TYPE" in index_ts
    assert "registerMessageRenderer(TEAMMATE_HEALTH_MESSAGE_TYPE" in index_ts
    assert 'eventToolLifecycle(' in index_ts
    assert 'healthReport.teammate' in index_ts
    assert 'formatSilenceDuration(health.silenceMs)' in index_ts
    assert "formatAgentHealthReport" in machine


def test_stall_health_event_renders_compact_and_expandable() -> None:
    payload = run_node(
        f'''\
        import extension, {{ TEAMMATE_HEALTH_MESSAGE_TYPE }} from "{(SRC / "index.ts").as_uri()}";
        import {{ initTheme }} from "@earendil-works/pi-coding-agent";
        initTheme("dark");
        const renderers = new Map();
        extension({{
          on() {{}},
          registerCommand() {{}},
          registerEntryRenderer() {{}},
          registerMessageRenderer(name, renderer) {{ renderers.set(name, renderer); }},
          registerTool() {{}},
        }});
        const renderer = renderers.get(TEAMMATE_HEALTH_MESSAGE_TYPE);
        const message = {{
          content: "@audit has been silent. Decide whether to wait or shut it down.",
          details: {{
            teammate: "audit",
            body: "@audit has been silent. Decide whether to wait or shut it down.",
            health: {{ state: "stalled", silenceMs: 125_000 }},
          }},
        }};
        const theme = {{ fg: (_color, text) => text, bold: (text) => text, bg: (_color, text) => text }};
        const collapsed = renderer(message, {{ expanded: false, outputPad: 0 }}, theme).render(100);
        const expanded = renderer(message, {{ expanded: true, outputPad: 0 }}, theme).render(100);
        console.log(JSON.stringify({{
          collapsed,
          expanded,
          compact: collapsed.some((line) => line.trim().startsWith("[agent] @audit stalled · silent 2m")),
          expandedTitle: expanded.some((line) => line.trim() === "[agent] @audit stalled · silent 2m"),
          expandedDiagnostic: expanded.some((line) => line.includes("Decide whether to wait")),
          noMessageRow: !collapsed.join(" ").includes("[message]"),
        }}));
        '''
    )
    assert payload["compact"] is True
    assert payload["expandedTitle"] is True
    assert payload["expandedDiagnostic"] is True
    assert payload["noMessageRow"] is True


def test_silent_teammate_watchdog_contract() -> None:
    feature = (PACKAGE / "features" / "agent-teams.feature").read_text(encoding="utf-8")
    machine = source("team-machine.ts")
    state = source("state.ts")
    types = source("types.ts")
    tools = source("tools.ts")
    ui = source("ui.ts")
    for phrase in (
        "A silent working teammate raises one stall notice per episode",
        "Activity re-arms the stall watchdog",
        "the notice is the last automatic action",
        "last output time",
        "stall notice",
    ):
        assert phrase in feature, phrase
    assert "lastOutputAt" in types
    assert "stallNoticeSentAt" in types
    assert "STALL_NOTICE_MS" in machine
    # No automatic reclaim may exist: shutdown thresholds are banned by design.
    assert "STALL_SHUTDOWN_MS" not in machine
    assert "PI_TEAMMATE_STALL_SHUTDOWN_MS" not in machine
    assert "void shutdownTeammate(teammate.name, reason)" not in machine
    assert "checkStalledTeammates" in machine
    assert "stallSilenceMs" in machine
    assert "sendUpdate" in machine
    assert "stalledMs" not in tools
    assert 'formatAgentHealthReport("stalled"' in machine
    assert "formatSilenceDuration" in ui
    payload = run_node(
        f'''\
        import {{ stallSilenceMs, formatSilenceDuration, isStallThresholdReached, STALL_NOTICE_MS }} from "{(SRC / "team-machine.ts").as_uri()}";
        const now = Date.now();
        const teammate = {{ status: "working", lastOutputAt: now - 3_725_000 }};
        console.log(JSON.stringify({{
          silence: stallSilenceMs(teammate, now),
          formatted: formatSilenceDuration(3_725_000),
          thresholdConfigured: STALL_NOTICE_MS > 0,
          reached: isStallThresholdReached(teammate, now, 3_000_000),
          notReached: isStallThresholdReached(teammate, now, 4_000_000),
        }}));
        '''
    )
    assert payload["silence"] == 3_725_000
    assert payload["formatted"] == "1h 2m"
    assert payload["thresholdConfigured"] is True
    assert payload["reached"] is True
    assert payload["notReached"] is False


def test_provider_hang_silent_stall_tier() -> None:
    feature = (PACKAGE / "features" / "agent-teams.feature").read_text(encoding="utf-8")
    machine = source("team-machine.ts")
    spawner = source("spawner.ts")
    state = source("state.ts")
    ui = source("ui.ts")
    for phrase in (
        "A provider hang is flagged before the default stall window",
        "Stall notices carry lifetime usage diagnostics",
    ):
        assert phrase in feature, phrase
    assert "PI_TEAMMATE_SILENT_STALL_MS" in machine
    assert "stallThresholdMs" in machine and "hasModelOutput" in machine
    assert "stallNoticeBody" in machine
    # Streaming activity and usage reach the roster so hangs are visible before shutdown.
    assert "modelOutputSeen?: boolean" in spawner
    assert "modelOutputSeen: streamState.modelOutputSeen" in spawner
    assert "progress.usage" in state
    assert "if (progress.modelOutputSeen) teammate.modelOutputSeen = true;" in state
    # Usage never sets the classifier: only streamed content does.
    assert "if (parts.trim()) state.modelOutputSeen = true;" in spawner
    assert "totalTokens ?? 0) > 0)) state.modelOutputSeen" not in spawner
    # The console marks the silent tier with the same effective threshold.
    assert "stallThresholdMs" in ui
    payload = run_node(
        f'''\
        import {{ hasModelOutput, stallThresholdMs, stallNoticeBody }} from "{(SRC / "team-machine.ts").as_uri()}";
        const now = 5 * 60_000;
        const hung = {{ status: "working", createdAt: 0, lastOutputAt: 0, activeTool: undefined, modelOutputSeen: undefined, usage: undefined }};
        const longTool = {{ ...hung, activeTool: "bash: pio run -t upload", modelOutputSeen: true }};
        const activityNoUsage = {{ ...hung, modelOutputSeen: true, usage: undefined }};
        const midWork = {{ ...hung, modelOutputSeen: true, usage: {{ input: 10, output: 5, cacheRead: 0, cacheWrite: 0, totalTokens: 15, cost: 0.01 }} }};
        console.log(JSON.stringify({{
          silentTier: stallThresholdMs(hung),
          longToolTier: stallThresholdMs(longTool),
          activityTier: stallThresholdMs(activityNoUsage),
          modelOutputTier: stallThresholdMs(midWork),
          zeroOutputDetected: !hasModelOutput(hung),
          outputDetected: hasModelOutput(midWork),
          hungBody: stallNoticeBody(hung, now, now),
          longToolBody: stallNoticeBody(longTool, now, now),
          midWorkBody: stallNoticeBody(midWork, 30 * 60_000, 30 * 60_000),
        }}));
        '''
    )
    assert payload["zeroOutputDetected"] is True
    assert payload["outputDetected"] is True
    # The provider-hang signature uses the shorter window; recognized stream
    # activity counts as output even when usage totals are absent.
    assert payload["silentTier"] < payload["longToolTier"] == payload["activityTier"] == payload["modelOutputTier"]
    hung_body: str = payload["hungBody"]  # type: ignore[assignment]
    assert "No model output received yet" in hung_body
    assert "respawning a successor" in hung_body
    assert "spawn age" in hung_body
    long_tool_body: str = payload["longToolBody"]  # type: ignore[assignment]
    assert "No model output received yet" not in long_tool_body
    assert "Tool still running: bash: pio run -t upload" in long_tool_body
    mid_work_body: str = payload["midWorkBody"]  # type: ignore[assignment]
    assert "Lifetime usage: 15 tokens, $0.0100." in mid_work_body
    assert "steer delivery is uncertain" in mid_work_body


def test_silent_stall_env_override() -> None:
    payload = run_node(
        f'''\
        import {{ stallThresholdMs }} from "{(SRC / "team-machine.ts").as_uri()}";
        const teammate = {{ status: "working", createdAt: 0, lastOutputAt: 0, activeTool: undefined, usage: undefined }};
        console.log(JSON.stringify({{ tier: stallThresholdMs(teammate) }}));
        ''',
        env_overrides={"PI_TEAMMATE_SILENT_STALL_MS": "120000"},
    )
    assert payload["tier"] == 120_000


def test_silent_stall_independent_of_notice_pace() -> None:
    # The provider-hang tier is documented as a fixed five-minute default; the
    # notice-pace floor must not silently move or disable it.
    payload = run_node(
        f'''\
        import {{ stallThresholdMs }} from "{(SRC / "team-machine.ts").as_uri()}";
        const teammate = {{ status: "working", createdAt: 0, lastOutputAt: 0, activeTool: undefined, usage: undefined }};
        console.log(JSON.stringify({{ tier: stallThresholdMs(teammate) }}));
        ''',
        env_overrides={"PI_TEAMMATE_NOTICE_PACE_MS": "120000"},
    )
    assert payload["tier"] == 300_000


def test_every_agent_teams_tool_executes_through_real_registrations(tmp_path: Path) -> None:
    feature = (PACKAGE / "features" / "agent-teams.feature").read_text(encoding="utf-8")
    assert "Every Agent Teams tool executes through the real tool harness" in feature
    payload = run_node(
        f'''\
        import fs from "node:fs";
        import path from "node:path";
        import {{ initTeamMachine, shutdownTeamMachine }} from "{(SRC / "team-machine.ts").as_uri()}";
        import {{ resetState, registerTeammate }} from "{(SRC / "state.ts").as_uri()}";
        import {{ registerLeaderTools }} from "{(SRC / "tools.ts").as_uri()}";
        import {{ registerWorkerCapabilities }} from "{(SRC / "worker.ts").as_uri()}";
        import {{ boardFilePath, inboxPath, writeRoster }} from "{(SRC / "statefile.ts").as_uri()}";

        const root = {str(tmp_path)!r};
        const stateFile = path.join(root, "state.json");
        const boardFile = boardFilePath(stateFile, root);
        const mailDir = path.join(root, "mail");
        const claimsDir = path.join(root, "claims");
        const submissionsDir = path.join(root, "submissions");
        fs.mkdirSync(mailDir, {{ recursive: true }});
        fs.mkdirSync(claimsDir, {{ recursive: true }});
        fs.mkdirSync(submissionsDir, {{ recursive: true }});
        resetState();
        initTeamMachine(
          {{ sessionManager: {{ getSessionFile: () => stateFile }}, cwd: root, model: undefined }},
          {{ sendUpdate() {{}}, notifyChange() {{}} }},
        );

        const leaderTools = [];
        registerLeaderTools({{ registerTool(tool) {{ leaderTools.push(tool); }}, registerCommand() {{}} }});
        const leader = Object.fromEntries(leaderTools.map((tool) => [tool.name, tool]));
        const leaderResults = {{}};
        leaderResults.spawn = await leader.teammate_spawn.execute("spawn", {{
          name: "worker", agent: "worker", definition: {{
            description: "test worker", tools: [], prompt: "test", worktree: false,
          }}, prompt: "test",
        }}, undefined, undefined, {{ cwd: root }});
        const worker = registerTeammate({{ name: "peer", agent: "worker", spawnId: "peer-spawn", pid: 0, status: "idle", isolation: "none", createdAt: 1, updatedAt: 1 }});
        writeRoster(path.join(root, "roster.json"), [
          {{ name: "worker", agent: "worker", status: "idle" }},
          {{ name: "peer", agent: "worker", status: "idle" }},
        ]);
        leaderResults.message = await leader.send_message.execute("message", {{ to: "worker", message: "hello" }});
        leaderResults.create = await leader.task_create.execute("create", {{ subject: "integration task" }}, undefined, undefined, {{}});
        leaderResults.list = await leader.task_list.execute("list", {{}}, undefined, undefined, {{}});
        const workerTools = [];
        const workerEnv = {{
          PI_TEAMMATE_WORKER_NAME: "peer",
          PI_TEAMMATE_SPAWN_ID: "peer-spawn",
          PI_TEAMMATE_OUTBOX_FILE: path.join(root, "peer-outbox.jsonl"),
          PI_TEAMMATE_INBOX_FILE: path.join(mailDir, "inbox-peer.jsonl"),
          PI_TEAMMATE_ROSTER_FILE: path.join(root, "roster.json"),
          PI_TEAMMATE_BOARD_FILE: boardFile,
          PI_TEAMMATE_CLAIMS_DIR: claimsDir,
          PI_TEAMMATE_SUBMISSIONS_DIR: submissionsDir,
        }};
        for (const [key, value] of Object.entries(workerEnv)) process.env[key] = value;
        registerWorkerCapabilities({{ registerTool(tool) {{ workerTools.push(tool); }} }});
        const workerMap = Object.fromEntries(workerTools.map((tool) => [tool.name, tool]));
        const workerResults = {{}};
        workerResults.message = await workerMap.send_message.execute("message", {{ to: "leader", message: "report", status: "completed" }});
        workerResults.list = await workerMap.task_list.execute("list", {{}}, undefined, undefined, {{}});
        workerResults.claim = await workerMap.task_claim.execute("claim", {{}}, undefined, undefined, {{}});
        const claimed = fs.readdirSync(claimsDir).length;
        workerResults.submit = await workerMap.task_submit.execute("submit", {{ taskId: "integration-task", status: "completed", result: "done" }});
        const submitted = fs.readdirSync(submissionsDir).length;
        leaderResults.shutdown = await leader.teammate_shutdown.execute("shutdown", {{ name: "worker" }}, undefined, undefined, {{}});
        shutdownTeamMachine();
        console.log(JSON.stringify({{
          leaderNames: Object.keys(leader), workerNames: Object.keys(workerMap),
          leaderSuccess: Object.values(leaderResults).every(Boolean),
          workerSuccess: Object.values(workerResults).every(Boolean),
          messageQueued: leaderResults.message.details?.outcome === "queued",
          workerReportWritten: fs.existsSync(path.join(root, "peer-outbox.jsonl")),
          claimMarkerWritten: claimed === 1,
          submissionMarkerWritten: submitted === 1,
          shutdownReturned: Boolean(leaderResults.shutdown),
        }}));
        ''',
        env_overrides={"PI_CODING_AGENT_DIR": str(tmp_path / "agent")},
    )
    assert payload["leaderNames"] == ["teammate_spawn", "teammate_shutdown", "send_message", "task_create", "task_list"]
    assert payload["workerNames"] == ["send_message", "task_list", "task_claim", "task_submit"]
    assert payload["leaderSuccess"] is True
    assert payload["workerSuccess"] is True
    assert payload["messageQueued"] is True
    assert payload["workerReportWritten"] is True
    assert payload["claimMarkerWritten"] is True
    assert payload["submissionMarkerWritten"] is True
    assert payload["shutdownReturned"] is True


def test_worker_tool_grant_is_visible_at_spawn() -> None:
    feature = (PACKAGE / "features" / "agent-teams.feature").read_text(encoding="utf-8")
    spawner = source("spawner.ts")
    machine = source("team-machine.ts")
    guidance = source("guidance.ts")
    types = source("types.ts")
    ui = source("ui.ts")
    tools_src = source("tools.ts")
    for phrase in (
        "The roster and detail view expose the effective tool allowlist",
        "The leader guidance requires explicit worker tooling",
        "a role derived inline without a tools field shows only the capability set",
    ):
        assert phrase in feature, phrase
    assert "resolveWorkerTools" in spawner and "WORKER_CAPABILITY_TOOLS" in spawner
    assert 'args.push("--tools", resolveWorkerTools(options.tools).join(","))' in spawner
    # The grant is flushed to both rosters before the kickoff can be consumed.
    assert "tools: resolveWorkerTools(agent.tools)" in machine
    grant_index = machine.index("tools: resolveWorkerTools(agent.tools)")
    spawn_window = machine[grant_index:grant_index + 1200]
    assert spawn_window.index("publishStateSnapshot()") < spawn_window.index("spawnResident({")
    assert "status: t.status," in machine
    assert "tools: t.tools," in machine
    assert "tools?: string[]" in types
    # Spawn rows identify the assignment; tool grants remain available in the roster/detail view.
    assert "details: { started: true }" in tools_src
    assert "check task board" in tools_src
    assert "Tools: ${teammate.tools.join(", ")}" in ui
    for phrase in (
        "grants only the capability set",
        "respawn with the right tools",
    ):
        assert phrase in guidance, phrase
    payload = run_node(
        f'''\
        import {{ resolveWorkerTools }} from "{(SRC / "spawner.ts").as_uri()}";
        console.log(JSON.stringify({{
          capabilityOnly: resolveWorkerTools(undefined),
          emptyRole: resolveWorkerTools([]),
          withShell: resolveWorkerTools(["read", "bash", "send_message"]),
          dedupesCapability: resolveWorkerTools(["task_list"]),
        }}));
        '''
    )
    capability = ["send_message", "task_list", "task_claim", "task_submit"]
    assert payload["capabilityOnly"] == capability
    assert payload["emptyRole"] == capability
    assert payload["withShell"] == ["read", "bash"] + capability
    assert payload["dedupesCapability"] == capability


def test_unknown_tool_ids_fail_the_spawn_before_side_effects() -> None:
    feature = (PACKAGE / "features" / "agent-teams.feature").read_text(encoding="utf-8")
    spawner = source("spawner.ts")
    machine = source("team-machine.ts")
    for phrase in (
        "Spawning rejects unknown execution-tool ids before any side effect",
        "the spawn fails immediately with no teammate, roster entry, worktree, or persisted role",
        "the universe is exactly the pi built-in tools plus the teammate capability set",
    ):
        assert phrase in feature, phrase
    assert "WORKER_TOOL_UNIVERSE" in spawner and "unknownWorkerTools" in spawner
    # Validation must run before every spawn side effect: no persisted inline
    # role, no worktree, no roster entry, no child process.
    body = machine[machine.index("export function spawnTeammate"):]
    check_index = body.index("unknownWorkerTools(requestedTools)")
    for side_effect in (
        "persistAgentDefinition(",
        "registerSessionAgent(",
        "createWorktree(",
        "registerTeammate(",
        "spawnResident({",
    ):
        assert side_effect in body and body.index(side_effect) > check_index, side_effect
    # The error names the unknown ids and teaches the bare-child constraint.
    for phrase in (
        "Unknown tool id",
        "runs a bare pi process",
        "Valid ids:",
        "leader session instead",
    ):
        assert phrase in machine, phrase
    payload = run_node(
        f'''\
        import {{ WORKER_TOOL_UNIVERSE, unknownWorkerTools }} from "{(SRC / "spawner.ts").as_uri()}";
        console.log(JSON.stringify({{
          typoDetected: unknownWorkerTools(["functions.read"]),
          keepsValidMixed: unknownWorkerTools(["functions.read", "read"]),
          dedupesUnknowns: unknownWorkerTools(["mcp.search", "mcp.search"]),
          acceptsUndefined: unknownWorkerTools(undefined),
          acceptsCapability: unknownWorkerTools(["send_message"]),
          universe: WORKER_TOOL_UNIVERSE,
        }}));
        '''
    )
    capability = ["send_message", "task_list", "task_claim", "task_submit"]
    builtins = ["read", "bash", "edit", "write", "grep", "find", "ls", "powershell"]
    assert payload["typoDetected"] == ["functions.read"]
    assert payload["keepsValidMixed"] == ["functions.read"]
    assert payload["dedupesUnknowns"] == ["mcp.search"]
    assert payload["acceptsUndefined"] == []
    assert payload["acceptsCapability"] == []
    assert payload["universe"] == builtins + capability


def test_stall_recovery_belongs_to_leader_alone() -> None:
    machine = source("team-machine.ts")
    tools = source("tools.ts")
    guidance = source("guidance.ts")
    feature = (PACKAGE / "features" / "agent-teams.feature").read_text(encoding="utf-8")
    # The harness never reclaims, restarts, or replaces a teammate on its own.
    assert "the harness never reclaims, restarts, or replaces a teammate on its own" in feature
    assert "no configuration may automatically terminate a working teammate" in feature
    assert "STALL_SHUTDOWN_MS" not in machine and "PI_TEAMMATE_STALL_SHUTDOWN_MS" not in machine
    assert "pendingShutdownReasons" not in machine
    # The stall notice itself carries the recovery decision menu.
    notice = machine[machine.index("export function stallNoticeBody"):]
    assert "keep waiting, steer again, or shut it down" in notice
    assert "respawn a successor with context" in notice
    # Leader guidance teaches recovery over punishment.
    assert "Teammates are autonomous: recover, never punish" in guidance
    assert "Never terminate a teammate" in guidance
    assert "The harness never reclaims, restarts, or replaces a teammate" in guidance or "never reclaims, restarts, or replaces a teammate" in guidance
    assert 'wait for its\nstatus="completed" or status="failed" report when possible' in guidance
    # A wake prompt restarts the silence clock so long-idle teammates never insta-stall.
    wake = machine[machine.index("export function wakeIdleTeammates"):]
    assert "lastOutputAt: Date.now()" in wake
    assert "stallNoticeSentAt: undefined" in wake
    # Steering reports only its synchronous routing transition. Teammate health
    # remains a separate watchdog report and transcript event.
    send = machine[machine.index("export function sendLeaderMessage"):]
    assert "stalledMs" not in send
    assert "isStallThresholdReached" not in send
    assert 'formatAgentHealthReport("stalled"' in machine
    assert "stalledMs" not in tools


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


def test_board_persists_but_runtime_does_not() -> None:
    machine = source("team-machine.ts")
    statefile = source("statefile.ts")
    assert "removeRuntimeDir" in machine
    assert "loadBoard(persisted.tasks)" in machine
    assert 'path.join(getAgentDir(), "tasks")' in statefile
    assert 'path.join(getAgentDir(), "teammate")' in statefile
    feature = (PACKAGE / "features" / "agent-teams.feature").read_text(encoding="utf-8")
    assert "no automatic cleanup deletes persisted boards" in feature
    assert "Board persistence is scoped to a board directory" in feature
    assert "different session file does not import another session's tasks automatically" in (PACKAGE / "README.md").read_text(encoding="utf-8")
    # cleanupExpiredStateDirs sweeps only the runtime root.
    sweep = statefile[statefile.index("export function cleanupExpiredStateDirs"):]
    assert "tasksRoot()" not in sweep


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
        appendWorkerEvent(outbox, {{ id: "evt5", type: "message", worker: "w", spawnId: "s1", body: "follow-up complete", status: "completed" }});
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
        "afterTerminal": {"sent": 3, "mailbox": 3, "closed": True, "idle": True, "sequenceEnded": True},
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


def test_non_finite_report_timestamps_are_rejected() -> None:
    types = source("types.ts")
    feature = (PACKAGE / "features" / "agent-teams.feature").read_text(encoding="utf-8")
    assert "Malformed report timestamps are rejected safely" in feature
    assert "Number.isFinite(event.timestamp)" in types
    queue = source("follow-up-queue.ts")
    assert "Number.isFinite(timestamp)" in queue
    payload = run_node(
        f'''\
        import {{ isWorkerEvent }} from "{(SRC / "types.ts").as_uri()}";
        const base = {{ id: "evt", type: "message", worker: "w", spawnId: "s", body: "ok" }};
        console.log(JSON.stringify({{
          finite: isWorkerEvent({{ ...base, timestamp: 1 }}),
          nan: isWorkerEvent({{ ...base, timestamp: NaN }}),
          infinity: isWorkerEvent({{ ...base, timestamp: Infinity }}),
          negativeInfinity: isWorkerEvent({{ ...base, timestamp: -Infinity }}),
        }}));
        '''
    )
    assert payload == {
        "finite": True,
        "nan": False,
        "infinity": False,
        "negativeInfinity": False,
    }


def test_requested_shutdown_stays_out_of_follow_up_queue() -> None:
    machine = source("team-machine.ts")
    feature = (PACKAGE / "features" / "agent-teams.feature").read_text(encoding="utf-8")
    assert "Requested shutdown stays a tool lifecycle event" in feature
    close = machine[machine.index("async function handleTeammateClose") :]
    requested = close[close.index("if (requested)") : close.index("} else {", close.index("if (requested)"))]
    assert "deliverToLeader" in requested
    assert "sendUpdate" not in requested


def test_leader_bound_harness_events_dispatch_through_the_queue() -> None:
    machine = source("team-machine.ts")
    feature = (PACKAGE / "features" / "agent-teams.feature").read_text(encoding="utf-8")
    assert "Leader-relevant harness events ride the same delivery channel" in feature
    assert "a failed capture commit preserves the worktree directory instead of destroying the work" in feature
    # Unexpected close summaries reach the leader queue; requested shutdowns
    # stay in the tool lifecycle result and console mailbox only.
    close = machine[machine.index("async function handleTeammateClose") :]
    assert close.count("recordTerminalReport(closeReport)") == 1
    assert close.count("sendUpdate(closeReport)") == 1
    assert "requested shutdown is already represented by the tool lifecycle row" in close
    # Verify-gate escalation narrates the parked task through the channel.
    gate = machine[machine.index("function resolveGateOutcome") :]
    assert 'teammate: "task-board"' in gate
    assert gate.count("sendUpdate({") >= 2
    # Worktree diffs dispatch a bounded preview with branch retrieval; the full
    # patch stays in the mailbox log.
    fin = machine[machine.index("async function finalizeWorktree") :]
    assert "sendUpdate({" in fin
    assert "Full diff: git diff" in fin
    assert "truncated(captured.diff.patch)" in fin
    # Cleanup itself commits remaining work onto the kept branch.
    wt = source("worktree.ts")
    cleanup_fn = wt[wt.index("export function cleanupWorktree") : wt.index("/** Best-effort cleanup used when a spawn fails")]
    assert "commitRemainingWork(setup)" in cleanup_fn
    # A failed keep-branch commit aborts removal instead of destroying work.
    assert "worktree left in place at" in wt
    # Failed spawns tear down through the deleteBranch path.
    discard_fn = machine[machine.index("function discardWorktreeQuietly") :]
    assert "discardWorktree(handle)" in discard_fn
    # An already-gone child gets its shutdown summary in the console mailbox;
    # no close event will fire, and requested shutdowns do not wake the leader.
    synth = machine[machine.index("export async function shutdownTeammate") : machine.index("async function handleTeammateClose")]
    assert "deliverToLeader({ from: name, subject: \"Teammate shut down\", body: summary })" in synth
    assert "sendUpdate(closeReport)" not in synth
    # Task outcome notices stay mailbox-only: workers announce outcomes
    # themselves via terminal send_message; no double reporting.
    board = machine[machine.index("function notifyTaskOutcome") :]
    assert "sendUpdate" not in board


def test_worker_guidance_rations_messages_by_value() -> None:
    guidance = source("guidance.ts")
    feature = (PACKAGE / "features" / "agent-teams.feature").read_text(encoding="utf-8")
    assert "Teammate messages are rationed by value instead of throttled" in feature
    assert "starts a full leader turn" in guidance
    assert "Never send bare status pings" in guidance
    assert "blockers needing a decision" in guidance
    assert 'status="completed" or status="failed"' in guidance


def test_worker_guidance_requires_one_substantive_terminal_report() -> None:
    guidance = source("guidance.ts")
    feature = (PACKAGE / "features" / "agent-teams.feature").read_text(encoding="utf-8")
    assert "Bounded reviewer assignments end with one substantive report" in feature
    assert "one concise terminal report bundles those findings, the recommendation, verification, and remaining risks" in feature
    assert "genuinely new blockers, plan-changing facts, or evidence that changes the conclusion" in feature
    assert "does not send a separate status-only assignment-complete message" in feature
    assert "after the terminal report, leader reporting resumes only for a new assignment or decision-useful fact" in feature
    assert "For bounded reviewer assignments" in guidance
    assert "terminal leader report ends the current worker turn" in guidance
    assert "harness suppresses all later reports" in guidance
    assert "identical bodies before terminal status" in guidance
    assert "same content is accepted again for a new assignment" in guidance.replace("\n  ", " ")
    assert "findings, the recommendation," in guidance
    assert "verification evidence" in guidance
    assert "risks in one concise terminal report" in guidance.replace("\n  ", " ")
    normalized_guidance = guidance.replace("\n  ", " ")
    assert "genuinely new blockers, plan-changing facts, or evidence that changes the conclusion" in normalized_guidance
    assert "status-only assignment-complete message" in normalized_guidance
    assert "repeat unchanged findings" in normalized_guidance
    assert "After a terminal" in guidance
    assert "new assignment or decision-useful" in normalized_guidance


def test_read_receipts_and_legacy_registry_are_gone() -> None:
    all_sources = "".join(source(name) for name in (
        "types.ts", "state.ts", "statefile.ts", "team-machine.ts", "worker.ts", "tools.ts", "ui.ts",
    ))
    for legacy in ("read receipt", "readReceipt", "markMessageRead", "broadcast"):
        assert legacy.lower() not in all_sources.lower(), legacy
    assert "ephemeral" not in all_sources.lower()

def test_idle_without_terminal_report_self_finalizes_before_escalating() -> None:
    machine = source("team-machine.ts")
    worker = source("worker.ts")
    feature = (PACKAGE / "features" / "agent-teams.feature").read_text(encoding="utf-8")
    assert "A teammate whose last report lacks terminal status is asked to self-finalize first" in feature
    assert "A repeated unfinalized idle transition escalates to the leader" in feature
    assert "export function hasUnfinalizedReport" in machine
    assert "nudgeIfUnfinalized" in machine
    # The decision reads post-drain mailbox state: the terminal report is
    # written to the outbox file before the final response arrives.
    nudge_body = machine[machine.index("function nudgeIfUnfinalized"):]
    assert "drainTeammateOutboxes();" in nudge_body[:400]
    # First miss: one inbox finalize request per spawn incarnation, no leader alert yet.
    assert "selfFinalizeAttempts" in machine
    assert "selfFinalizeAttempts.clear();" in machine
    assert machine.count("selfFinalizeAttempts.delete(") == 2
    # Second miss: the existing once-per-incarnation leader reminder.
    assert "idleNudgesSent" in machine
    # The worker-side send tool reinforces the rule at the exact moment of use.
    assert 'send status="completed" or status="failed" to end the assignment' in worker
    # A spawned teammate runs a kickoff turn, so status must stay "starting"
    # until real stream events arrive: the old synchronous idle mark mislabeled
    # an actively-running turn as idle and misrouted queued deliveries.
    assert 'updateTeammate(input.name, { status: "idle" })' not in machine


def test_worker_task_list_includes_roster_tail() -> None:
    worker = source("worker.ts")
    feature = (PACKAGE / "features" / "agent-teams.feature").read_text(encoding="utf-8")
    assert "the shared task_list view includes the living roster on both leader and worker sides" in feature
    roster_section = worker[worker.index("registerTaskListTool"):]
    assert "readRoster(binding.rosterFile)" in roster_section
    assert "renderRoster(roster)" in roster_section


def test_terminal_status_discipline_is_documented_for_workers() -> None:
    templates = " ".join((PACKAGE / "references" / "agent-roles.md").read_text(encoding="utf-8").split())
    guidance = source("guidance.ts")
    assert 'MUST carry status="completed"' in templates
    assert "MUST carry" in guidance and 'status="completed"' in guidance
    assert 'status="completed" or status="failed"' in templates
    assert "status-only assignment-complete" in templates
    assert "repeat unchanged findings" in templates
