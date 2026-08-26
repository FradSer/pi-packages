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
    assert "freshClaimableTasks(teammate.noticedTaskIds, claimableTasks())" in wake
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
        import {{ resetState, createTask, getTask, applyClaimIntent, loadBoard }} from "{(SRC / "state.ts").as_uri()}";
        resetState();
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
        setVerifyGateRunner(() => new Promise((resolve) => {{ releaseStaleGate = () => resolve({{ ok: true, detail: "stale pass" }}); }}));
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
        setVerifyGateRunner(() => new Promise((resolve) => {{ releaseFreshGate = () => resolve({{ ok: true, detail: "fresh pass" }}); }}));
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
    assert payload["pass"] == {"ok": True}
    assert payload["passLowerCase"] == {"ok": True}
    assert payload["passTrailingProse"] == {"ok": True}
    assert payload["passWithJunkRejected"]["ok"] is False
    assert payload["failWithReason"]["ok"] is False
    assert "overflow at 400px" in payload["failWithReason"]["detail"]
    assert payload["failExtraSpaces"]["ok"] is False
    assert "spaced reasons" in payload["failExtraSpaces"]["detail"]
    assert payload["missing"]["ok"] is False
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


def test_guidance_is_static_and_team_shaped() -> None:
    guidance = source("guidance.ts")
    feature = (PACKAGE / "features" / "agent-teams.feature").read_text(encoding="utf-8")
    assert "Prompt guidance reflects the team model" in feature
    assert "DO NOT poll or sleep" in guidance
    assert "teammate_spawn(name, agent, optional kickoff prompt)" in guidance
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
          fullBodyKept: content.includes("<b>bold finding</b>"),
          noRunIds: !content.includes("run_"),
          noFinishedNotice: !content.includes("finished."),
        }}));
        '''
    )
    assert payload["wrapped"] is True
    assert payload["escaped"] is True
    assert payload["fullBodyKept"] is True
    assert payload["noRunIds"] is True
    assert payload["noFinishedNotice"] is True


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


def test_follow_up_queue_batches_by_sender_order() -> None:
    payload = run_node(
        f'''\
        import {{ groupReportsByTeammate }} from "{(SRC / "follow-up-queue.ts").as_uri()}";
        const groups = groupReportsByTeammate([
          {{ teammate: "b", body: "1" }},
          {{ teammate: "a", body: "2" }},
          {{ teammate: "b", body: "silent", health: {{ state: "stalled", silenceMs: 120_000 }} }},
          {{ teammate: "b", body: "3" }},
          {{ teammate: "b", body: "silent again", health: {{ state: "stalled", silenceMs: 240_000 }} }},
        ]);
        console.log(JSON.stringify({{
          order: groups.map((group) => group.teammate).join(","),
          counts: groups.map((group) => group.reports.length).join(","),
          healthGroupsAreIsolated: groups.filter((group) => group.reports[0]?.health).every((group) => group.reports.length === 1),
          messagesStillGrouped: groups.find((group) => group.reports[0]?.body === "1")?.reports.map((report) => report.body).join(","),
        }}));
        '''
    )
    assert payload["order"] == "b,a,b,b"
    assert payload["counts"] == "2,1,1,1"
    assert payload["healthGroupsAreIsolated"] is True
    assert payload["messagesStillGrouped"] == "1,3"


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

def test_spawn_uses_shared_started_lifecycle_renderer() -> None:
    tools = source("tools.ts")
    feature = (PACKAGE / "features" / "agent-teams.feature").read_text(encoding="utf-8")
    assert "Spawning renders one started line per teammate" in feature
    assert "startedToolLifecycle(" in tools
    assert "renderLifecycleResult(" in tools
    assert "formatAgentTaskName" in tools
    assert "details: { started: true, tools: granted }" in tools


def test_spawn_started_line_fits_narrow_tui_width() -> None:
    tools = source("tool-render.ts")
    assert "renderToolLifecycle(" in tools
    assert "truncate: truncateToWidth" in tools
    assert "started line fits the available TUI width" in (
        PACKAGE / "features" / "agent-teams.feature"
    ).read_text(encoding="utf-8")


def test_teammate_spawn_started_row_fits_narrow_transcript_widths() -> None:
    feature = (PACKAGE / "features" / "agent-teams.feature").read_text(encoding="utf-8")
    assert "The teammate_spawn started row fits narrow transcript widths" in feature
    payload = run_node(
        f'''\
        import {{ registerLeaderTools }} from "{(SRC / "tools.ts").as_uri()}";
        import {{ visibleWidth }} from "@earendil-works/pi-tui";
        const tools = [];
        registerLeaderTools({{ registerTool(tool) {{ tools.push(tool); }}, registerCommand() {{}} }});
        const spawn = tools.find((tool) => tool.name === "teammate_spawn");
        const theme = {{ fg: (_color, text) => text, bold: (text) => text }};
        const renderRow = (width) => spawn.renderResult(
          {{ content: [{{ type: "text", text: "started" }}] }},
          {{}},
          theme,
          {{ args: {{ name: "very-long-teammate-name", agent: "reviewer", prompt: "Investigate the narrow transcript rendering regression" }} }},
        ).render(width);
        const rows = [1, 8, 16, 24].map((width) => ({{ width, lines: renderRow(width) }}));
        const row = renderRow(24)[0];
        console.log(JSON.stringify({{
          row,
          narrowRowsFit: rows.every(({{ width, lines }}) => lines.length === 1 && visibleWidth(lines[0]) <= width),
          rowIsSingleLine: !row.includes("\\n"),
          rowFitsWidth: visibleWidth(row) <= 24,
          zeroWidthLines: spawn.renderResult(
            {{ content: [{{ type: "text", text: "started" }}] }},
            {{}},
            theme,
            {{ args: {{ name: "name", agent: "reviewer", prompt: "task" }} }},
          ).render(0).length === 0,
          identifiesStarted: row.includes("[agent] started"),
        }}));
        '''
    )
    assert payload["narrowRowsFit"] is True
    assert payload["rowIsSingleLine"] is True
    assert payload["rowFitsWidth"] is True
    assert payload["identifiesStarted"] is True


def test_shutdown_renders_one_collapsible_agent_event_line() -> None:
    tools = source("tools.ts")
    feature = (PACKAGE / "features" / "agent-teams.feature").read_text(encoding="utf-8")
    assert "Shutting down renders one collapsible agent event line" in feature
    assert "eventToolLifecycle(" in tools
    assert "renderLifecycleResult(" in tools
    assert "formatExpandHint" in source("tool-render.ts")


def test_shutdown_row_hides_details_behind_the_shared_expand_hint() -> None:
    payload = run_node(
        f'''\
        import {{ registerLeaderTools }} from "{(SRC / "tools.ts").as_uri()}";
        import {{ initTheme }} from "@earendil-works/pi-coding-agent";
        initTheme("dark");
        const tools = [];
        registerLeaderTools({{ registerTool(tool) {{ tools.push(tool); }}, registerCommand() {{}} }});
        const shutdown = tools.find((tool) => tool.name === "teammate_shutdown");
        const theme = {{ fg: (_color, text) => text, bold: (text) => text }};
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
          collapsedIsSingleLine: !collapsed.join("\\n").includes("\\n"),
          collapsedNamesAgentEvent: collapsed[0].includes("[agent] event · @scribe shut down"),
          collapsedHasSharedHint: collapsed[0].includes(" · ") && collapsed[0].includes("to expand"),
          expandedKeepsTitle: expandedRows[0].startsWith("[agent] event · @scribe shut down") && !expandedRows[0].includes("to expand"),
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
        const theme = {{ fg: (_color, text) => text, bold: (text) => text }};
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
          routingIsSingleLine: render({{ outcome: "steered" }}).length === 1,
          noDuplicateSentence: !render({{ outcome: "steered" }})[0].includes("Routing accepted"),
          errorIsExactPlainLine: errorRow.trim() === "No living teammate named ghost." && !errorRow.includes("·"),
          shutdownErrorIsPlainLine: shutdownErrorRow.trim() === "No living teammate named ghost."
            && !shutdownErrorRow.includes("[agent] event") && !shutdownErrorRow.includes("to expand"),
        }}));
        '''
    )
    assert payload["callEmpty"] is True
    assert payload["steeredRow"] == ["[message] to @audit · steered"]
    assert payload["queuedRow"] == ["[message] to @audit · queued"]
    assert payload["unrelatedDetailIgnored"] == ["[message] to @audit · steered"]
    assert payload["zeroWidthEmpty"] is True
    assert payload["routingIsSingleLine"] is True
    assert payload["noDuplicateSentence"] is True
    assert payload["errorIsExactPlainLine"] is True
    assert payload["shutdownErrorIsPlainLine"] is True


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
        const theme = {{ fg: (_color, text) => text, bold: (text) => text }};
        const render = (to) => send.renderResult(
          {{ content: [{{ type: "text", text: "queued" }}], details: {{ outcome: "queued" }} }},
          {{ expanded: true }},
          theme,
          {{ args: {{ to, message: "hello" }} }},
        ).render(100)[0];
        console.log(JSON.stringify({{ peer: render("backend"), leader: render("leader") }}));
        '''
    )
    assert payload["peer"] == "[message] to @backend · queued"
    assert payload["leader"] == "[message] to @leader · queued"


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
        const base = {{ ok: true, id: "task", notifiedTeammates: [], livingTeammates: 0, claimable: true }};
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
    assert "no idle teammate" in str(payload["busy"])
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
        const theme = {{ fg: (_color, text) => text, bold: (text) => text }};
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
          noDuplicateSentence: !render()[0].includes("Idle teammates are notified"),
          errorIsPlainLine: errorRow.trim() === "Unknown dependency id in [t_9]." && !errorRow.includes("[board]"),
        }}));
        '''
    )
    assert payload["callEmpty"] is True
    assert payload["createdRow"] == ["[board] created · Fix the login flow"]
    assert payload["zeroWidthEmpty"] is True
    assert payload["noDuplicateSentence"] is True
    assert payload["errorIsPlainLine"] is True


def test_completion_announced_once_per_spawn_incarnation() -> None:
    tools = source("team-machine.ts")
    extension = source("index.ts")
    feature = (PACKAGE / "features" / "agent-teams.feature").read_text(encoding="utf-8")
    assert "Completion is announced once per spawn incarnation" in feature
    # The machine layer carries the spawn identity so the display can dedupe.
    assert "spawnId: teammate.spawnId," in tools
    # Crash diagnostics key on the incarnation too: a respawned teammate's
    # second unexpected stop must stay visible instead of sharing one session key.
    crash_block = tools[tools.index("if (!requested) {") :]
    assert "spawnId: teammate.spawnId," in crash_block[:400]
    # Crash diagnostics key on the incarnation too: a respawned teammate's
    # second unexpected stop must stay visible instead of sharing one session key.
    crash_block = tools[tools.index("if (!requested) {") :]
    assert "spawnId: teammate.spawnId," in crash_block[:400]
    assert "markTeammateFinished(report)" in extension
    assert "announcedFinishKeys.clear()" in tools


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


def test_stall_report_has_a_distinct_agent_health_event_renderer() -> None:
    feature = (PACKAGE / "features" / "agent-teams.feature").read_text(encoding="utf-8")
    index_ts = source("index.ts")
    machine = source("team-machine.ts")
    assert "one `[agent] event · @name stalled · silent <duration>` row" in feature
    assert "message routing rows never repeat the teammate health state" in feature
    assert "TEAMMATE_HEALTH_MESSAGE_TYPE" in index_ts
    assert "registerMessageRenderer(TEAMMATE_HEALTH_MESSAGE_TYPE" in index_ts
    assert 'eventToolLifecycle(' in index_ts
    assert '`@${health.teammate} ${health.health.state} · silent ${formatSilenceDuration(health.health.silenceMs)}`' in index_ts
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
        const theme = {{ fg: (_color, text) => text, bold: (text) => text }};
        const collapsed = renderer(message, {{ expanded: false, outputPad: 0 }}, theme).render(100);
        const expanded = renderer(message, {{ expanded: true, outputPad: 0 }}, theme).render(100);
        console.log(JSON.stringify({{
          collapsed,
          expanded,
          compact: collapsed.length === 1 && collapsed[0].startsWith("[agent] event · @audit stalled · silent 2m"),
          expandedTitle: expanded[0] === "[agent] event · @audit stalled · silent 2m",
          expandedDiagnostic: expanded.some((line) => line.includes("Decide whether to wait")),
          noMessageRow: !collapsed[0].includes("[message]"),
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
        "The roster and spawn render expose the effective tool allowlist",
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
    assert "status: t.status, tools: t.tools" in machine
    assert "tools?: string[]" in types
    # Persisted in result details so historical renders survive session restarts
    # and stay truthful across teammate-name reuse (no live-state fallback).
    assert "details: { started: true, tools: granted }" in tools_src
    assert "const tools = details?.tools;" in tools_src
    # Spawn surfaces name the granted list so missing read/bash is obvious immediately.
    assert "granted.join(\", \")" in tools_src
    assert "Tools: ${teammate.tools.join(", ")}" in ui
    for phrase in (
        "grants only the capability set",
        "respawn with the right tools instead of steering",
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
    assert "The harness never reclaims, restarts, or replaces a teammate" in guidance
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
