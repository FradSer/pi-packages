from __future__ import annotations

import json
import subprocess
import textwrap
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
SRC = PACKAGE / "src"

LEADER_TOOLS = {
    "teammate_register",
    "teammate_list",
    "teammate_configure",
    "teammate_remove",
    "teammate_message",
    "teammate_inbox",
    "teammate_create_task",
    "teammate_list_tasks",
    "teammate_start_task",
    "teammate_wait",
    "teammate_cancel_task",
    "teammate_cleanup",
}
WORKER_TOOLS = {"teammate_message", "teammate_inbox", "teammate_report"}
LEGACY_TOOLS = {
    "teammate_assign_task",
    "teammate_update_task",
    "teammate_task_deps",
    "teammate_update_model",
    "teammate_spawn",
    "teammate_reset",
    "teammate_send",
    "teammate_read_mailbox",
    "teammate_emit_message",
    "teammate_mark_message_read",
    "teammate_update_own_task",
    "teammate_broadcast",
}


def source(name: str) -> str:
    return (SRC / name).read_text(encoding="utf-8")


def run_node(script: str, *args: str) -> dict[str, object]:
    result = subprocess.run(
        ["node", "--input-type=module", "--eval", textwrap.dedent(script), *args],
        cwd=PACKAGE,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def test_manifest_declares_native_extension_package() -> None:
    manifest = json.loads((PACKAGE / "package.json").read_text(encoding="utf-8"))
    assert manifest["name"] == "@fradser/pi-agent-teams"
    assert "pi-package" in manifest["keywords"]
    assert manifest["pi"] == {"extensions": ["./src/index.ts"]}
    assert "skills" not in manifest["files"]
    assert not (PACKAGE / "skills").exists()


def test_bdd_contract_covers_target_resources() -> None:
    feature = (PACKAGE / "features" / "teammate-status.feature").read_text(encoding="utf-8")
    for phrase in (
        "Teammates are reusable current-session executors",
        "Reuse a compatible idle teammate",
        "Do not silently reuse a materially different teammate",
        "Retire only a truly expired teammate",
        "Tasks declare scopes and access before they run",
        "Partition a parallel team before it starts",
        "Allow overlapping read scopes",
        "Block unsafe overlapping writes in a shared workspace",
        "Allow isolated overlapping write experiments",
        "Reject ambiguous path ownership",
        "Queue follow-up work for the same teammate",
        "A task run is explicit and never blocks the leader",
        "Retry failed work with a fresh run",
        "Messaging is symmetric, proactive, and capability-bound",
        "Intermediate worker communication stays in the mailbox",
        "The harness delivers every terminal result to the main session",
        "A worker terminal report is not treated as final delivery",
        "Worker process outcomes are authoritative",
        "A worker process exits after its assigned task",
        "teammate_create_task",
        "teammate_start_task",
        "teammate_cancel_task",
        "Cancel a task run only after its worker closes",
        "leader records cancellation intent for that run before awaiting its close event",
        "SIGTERM-cooperative worker that exits 0 is not recorded completed or failed before cancellation",
        "SIGTERM-resistant worker receives SIGKILL after a bounded grace period",
        "cancellation intent is cleared after the cancellation attempt finishes",
        "teammate_report",
        "Keep an idle teammate with pending communication",
        "Retain a reported terminal task until its worker closes",
        "Do not restore a prior session's team",
        "Invalid tool operations surface as Pi failures",
        "Cancelled or timed-out waits surface as tool failures",
        "Legitimate empty and terminal data remains a normal result",
    ):
        assert phrase in feature


def test_leader_tool_surface_is_exact() -> None:
    ext = source("index.ts")
    for tool in LEADER_TOOLS:
        assert f'name: "{tool}"' in ext
    for tool in LEGACY_TOOLS:
        assert f'name: "{tool}"' not in ext


def test_worker_surface_is_capability_bound() -> None:
    ext = source("index.ts")
    worker_section = ext[ext.index("function registerWorkerCapabilities"):ext.index("function notifyUnblockedTasks")]
    for tool in WORKER_TOOLS:
        assert f'name: "{tool}"' in worker_section
    for tool in LEADER_TOOLS - {"teammate_message", "teammate_inbox"}:
        assert f'name: "{tool}"' not in worker_section
    assert "if (workerOutboxBinding())" in ext
    assert "registerWorkerCapabilities(pi);" in ext
    assert "return;" in ext[ext.index("if (workerOutboxBinding())"):ext.index("// ── Session lifecycle")]


def test_types_express_target_surface_without_invalid_role() -> None:
    types = source("types.ts")
    for schema in (
        "TeammateRegisterParams",
        "TeammateConfigureParams",
        "TeammateMessageParams",
        "TeammateInboxParams",
        "TeammateCreateTaskParams",
        "TeammateListTasksParams",
        "TeammateStartTaskParams",
        "TeammateWaitParams",
        "TeammateCancelTaskParams",
        "TeammateReportParams",
    ):
        assert f"export const {schema}" in types
    assert 'Type.Literal("team-leader")' not in types
    assert 'Type.Literal("created")' not in types
    assert "blocks: Type.Optional" not in types
    assert "blockedBy" in types
    for old_schema in (
        "TeammateAssignTaskParams",
        "TeammateUpdateTaskParams",
        "TeammateTaskDepsParams",
        "TeammateUpdateModelParams",
        "TeammateSpawnParams",
        "TeammateUpdateOwnTaskParams",
    ):
        assert old_schema not in types


def test_create_task_declares_access_and_defers_shared_write_conflicts_to_start() -> None:
    ext = source("index.ts")
    state = source("state.ts")
    types = source("types.ts")
    create_start = ext.index('name: "teammate_create_task"')
    create_end = ext.index('name: "teammate_list_tasks"', create_start)
    create_body = ext[create_start:create_end]
    assert 'createTask(params.title, params.description, params.paths, params.access ?? "write", params.assignee, "agent", params.blockedBy ?? [])' in create_body
    assert "Access:" in create_body
    assert "access:" in types
    assert "normalizeTaskPaths" in state
    assert "findSharedWorkspaceWriteConflict" in state
    assert "uniqueBlockedBy" in state
    assert "for (const dep of uniqueBlockedBy)" in state
    assert "setTaskDeps" not in state


def test_start_task_reuses_assignee_and_allows_explicit_retry() -> None:
    ext = source("index.ts")
    state = source("state.ts")
    types = source("types.ts")
    start = ext.index('name: "teammate_start_task"')
    end = ext.index('name: "teammate_cancel_task"', start)
    body = ext[start:end]
    assert "getTeammate(task.assignee)" in body
    assert "params.retry === true" in body
    assert "retryFailedTask" in state
    assert "retry:" in types
    assert "findSharedWorkspaceWriteConflict" in body
    assert "markTeammateRunning(teammate.name, params.taskId, runId)" in body
    assert "spawnPiWorker({" in body
    assert "The main session is free to continue" in body
    assert "params.name" not in body


def test_start_task_is_nonblocking_and_wait_is_only_join_barrier() -> None:
    ext = source("index.ts")
    spawner = source("spawner.ts")
    assert "spawnPiWorkerBlocking" not in ext
    assert "spawnPiWorkerBlocking" not in spawner
    assert "Abort signal" not in spawner
    assert "options.signal" not in spawner
    wait_start = ext.index('name: "teammate_wait"')
    wait_end = ext.index('name: "teammate_configure"', wait_start)
    wait_body = ext[wait_start:wait_end]
    assert "await new Promise" in wait_body
    assert "isSettled" in wait_body


def test_cancel_task_is_the_only_leader_run_interruption() -> None:
    ext = source("index.ts")
    state = source("state.ts")
    spawner = source("spawner.ts")
    cancel_start = ext.index('name: "teammate_cancel_task"')
    cancel_end = ext.index('name: "teammate_remove"', cancel_start)
    cancel_body = ext[cancel_start:cancel_end]
    assert "await terminateWorker(task.assignee" in cancel_body
    assert "const result = cancelTask(params.taskId);" in cancel_body
    assert "throw new Error" in cancel_body
    assert "export function cancelTask" in state
    assert "still has a running worker" in state
    assert "export async function terminateWorker" in spawner
    assert "SIGKILL" in spawner
    assert "force" not in source("types.ts")


def test_cancel_task_stays_nonterminal_until_its_worker_close_is_recorded() -> None:
    module = (SRC / "state.ts").as_uri()
    payload = run_node(
        f'''\
        import {{ cancelTask, createTask, registerTeammate, setSpawnInfo, updateTaskStatus }} from "{module}";
        registerTeammate({{ name: "worker", role: "worker", description: "", prompt: "", registeredAt: 1 }});
        const task = createTask("resistant", "", ["packages/worker"], "write", "worker", "agent").task;
        setSpawnInfo(task.id, {{ runId: "run-1", pid: 1, status: "running", startedAt: 1 }});
        updateTaskStatus(task.id, "in_progress");
        const beforeClose = cancelTask(task.id);
        const statusBeforeClose = task.status;
        setSpawnInfo(task.id, {{ runId: "run-1", pid: 1, status: "failed", startedAt: 1, finishedAt: 2 }});
        const afterClose = cancelTask(task.id);
        console.log(JSON.stringify({{
          beforeClose: beforeClose.ok,
          beforeCloseError: beforeClose.error,
          statusBeforeClose,
          afterClose: afterClose.ok,
          finalStatus: task.status,
        }}));
        '''
    )
    assert payload == {
        "beforeClose": False,
        "beforeCloseError": 'Task "task_1" still has a running worker and cannot be cancelled until it closes.',
        "statusBeforeClose": "in_progress",
        "afterClose": True,
        "finalStatus": "cancelled",
    }


def test_cancellation_intent_defers_close_finalization_until_the_cancel_outcome_is_known() -> None:
    module = (SRC / "spawner.ts").as_uri()
    payload = run_node(
        f'''\
        import {{ CancellationIntents }} from "{module}";
        const intents = new CancellationIntents();
        const outcomes = [];
        intents.begin("run-1");
        const deferred = intents.defer("run-1", (cancelled) => outcomes.push(cancelled ? "cancelled" : "normal"));
        const beforeResolve = outcomes.length;
        const resolved = intents.resolve("run-1", true);
        console.log(JSON.stringify({{ deferred, beforeResolve, resolved, outcomes, pending: intents.has("run-1") }}));
        '''
    )
    assert payload == {
        "deferred": True,
        "beforeResolve": 0,
        "resolved": True,
        "outcomes": ["cancelled"],
        "pending": False,
    }


def test_sigterm_cooperative_worker_closes_with_exit_zero_before_termination_resolves() -> None:
    module = (SRC / "spawner.ts").as_uri()
    payload = run_node(
        f'''\
        import {{ spawn }} from "node:child_process";
        import {{ terminateChildProcess }} from "{module}";
        const child = spawn(process.execPath, ["--eval", `
          process.on("SIGTERM", () => process.exit(0));
          setInterval(() => {{}}, 1_000);
        `], {{ stdio: "ignore" }});
        await new Promise((resolve) => setTimeout(resolve, 50));
        let closed = false;
        child.once("close", () => {{ closed = true; }});
        const completion = terminateChildProcess(child, 100);
        const beforeClose = !closed && child.exitCode === null;
        const terminated = await completion;
        console.log(JSON.stringify({{ beforeClose, closed, terminated, exitCode: child.exitCode, signal: child.signalCode }}));
        '''
    )
    assert payload == {"beforeClose": True, "closed": True, "terminated": True, "exitCode": 0, "signal": None}


def test_sigterm_resistant_worker_is_escalated_and_close_is_observed_before_termination_resolves() -> None:
    module = (SRC / "spawner.ts").as_uri()
    payload = run_node(
        f'''\
        import {{ spawn }} from "node:child_process";
        import {{ terminateChildProcess }} from "{module}";
        const child = spawn(process.execPath, ["--eval", `
          process.on("SIGTERM", () => {{}});
          setInterval(() => {{}}, 1_000);
        `], {{ stdio: "ignore" }});
        await new Promise((resolve) => setTimeout(resolve, 50));
        let closed = false;
        child.once("close", () => {{ closed = true; }});
        const completion = terminateChildProcess(child, 25);
        const beforeClose = !closed && child.exitCode === null;
        const terminated = await completion;
        console.log(JSON.stringify({{ beforeClose, closed, terminated, signal: child.signalCode }}));
        '''
    )
    assert payload == {"beforeClose": True, "closed": True, "terminated": True, "signal": "SIGKILL"}


def test_teammates_expire_only_after_idle_ttl_and_cleanup_is_terminal_only() -> None:
    ext = source("index.ts")
    state = source("state.ts")
    assert "activeTask" in state
    assert "retireExpiredTeammates" in state
    assert "DEFAULT_IDLE_TTL_MS = 5 * 60 * 1000" in ext
    assert "cancel or complete it before removing" in state
    remove_start = ext.index('name: "teammate_remove"')
    remove_end = ext.index('name: "teammate_cleanup"', remove_start)
    assert "params.force" not in ext[remove_start:remove_end]
    cleanup_start = ext.index('name: "teammate_cleanup"')
    cleanup_body = ext[cleanup_start:]
    assert "pruneFinishedTasks()" in cleanup_body
    assert "parameters: EmptyParams" in cleanup_body
    assert "export function pruneFinishedTasks" in state
    assert 'new Set<Task["status"]>(["completed", "failed", "cancelled"])' in state


def test_configure_requires_a_real_change() -> None:
    state = source("state.ts")
    ext = source("index.ts")
    assert "export function configureTeammate" in state
    assert "Provide at least one teammate configuration field." in state
    configure_start = ext.index('name: "teammate_configure"')
    configure_end = ext.index('name: "teammate_start_task"', configure_start)
    assert "configureTeammate(params.name" in ext[configure_start:configure_end]


def test_unified_message_inbox_and_main_session_delivery() -> None:
    ext = source("index.ts")
    worker_section = ext[ext.index("function registerWorkerCapabilities"):ext.index("function notifyUnblockedTasks")]
    assert 'params.to === "all" || params.role' in worker_section
    assert 'params.to !== "agent" && !snapshot?.teammates[params.to]' in worker_section
    assert "acknowledgedWorkerMessageIds" in worker_section
    leader_message = ext[ext.index('name: "teammate_message"', ext.index("// ── Leader tools")):ext.index('name: "teammate_inbox"', ext.index("// ── Leader tools"))]
    assert 'params.to === "all"' in leader_message
    assert "params.role" in leader_message
    assert "if (liveStateFile) applyWorkerEvents(liveStateFile);" in ext
    assert "Intermediate worker communication stays in the mailbox" in (PACKAGE / "features" / "teammate-status.feature").read_text(encoding="utf-8")
    assert "sendMainSessionUpdate(event.subject, event.body, taskId);" not in ext
    assert "Task progress" not in ext
    assert "Task started" not in ext
    assert "buildTerminalResult" in ext
    assert "sendMainSessionUpdate(terminalSubject, terminalBody, params.taskId);" in ext
    assert 'deliverAs: "followUp"' in ext
    assert 'triggerTurn: true' in ext
    assert "Before substantive work, call teammate_message" in source("spawner.ts")
    assert "does not interrupt the leader" in source("spawner.ts")


def test_role_defaults_and_explicit_tools_are_least_privilege() -> None:
    ext = source("index.ts")
    spawner = source("spawner.ts")
    for role, tools in {
        'case "worker"': '["read", "bash", "edit", "write"]',
        'case "reviewer"': '["read", "bash"]',
        'case "observer"': '["read"]',
    }.items():
        assert role in ext
        assert tools in ext
    assert "function executionToolsFor" in ext
    assert "tools: executionToolsFor(teammate)" in ext
    assert 'const capabilityTools = ["teammate_message", "teammate_inbox", "teammate_report"]' in spawner
    assert "const requestedTools = (options.tools ?? []).filter" in spawner
    assert '"edit", "write", "teammate_message"' not in spawner


def test_worker_report_is_bound_to_current_task_and_run() -> None:
    ext = source("index.ts")
    report_start = ext.index('name: "teammate_report"')
    report_end = ext.index("function notifyUnblockedTasks", report_start)
    report = ext[report_start:report_end]
    assert "taskId: binding.taskId" in report
    assert "runId: binding.runId" in report
    assert 'type: "task_update"' in report
    assert "event.taskId !== teammate.currentTaskId" in ext
    assert "event.worker !== workerName || event.runId !== runId" in ext


def test_worker_event_validation_checks_optional_fields() -> None:
    ext = source("index.ts")
    assert 'event.taskId === undefined || typeof event.taskId === "string"' in ext
    assert 'event.result === undefined || typeof event.result === "string"' in ext
    assert 'event.errorMessage === undefined || typeof event.errorMessage === "string"' in ext


def test_terminal_result_builder_is_harness_owned_and_fallback_backed() -> None:
    module = (SRC / "terminal.ts").as_uri()
    payload = run_node(
        f'''\
        import {{ buildTerminalResult }} from "{module}";
        const base = {{ taskId: "task_1", teammate: "worker", patchText: "" }};
        const silent = buildTerminalResult({{ ...base, result: {{ stdout: "", stderr: "", signal: null, timedOut: false }}, cancelled: false }});
        const timeout = buildTerminalResult({{ ...base, result: {{ stdout: "", stderr: "", signal: "SIGKILL", timedOut: true }}, cancelled: false }});
        const cancelled = buildTerminalResult({{ ...base, result: {{ stdout: "", stderr: "", signal: "SIGTERM", timedOut: false }}, cancelled: true }});
        console.log(JSON.stringify({{ silent, timeout, cancelled }}));
        '''
    )
    assert payload == {
        "silent": "Task [task_1] completed — teammate worker.\nNo worker summary was produced.",
        "timeout": "Task [task_1] timed out — teammate worker.\nNo worker summary was produced.",
        "cancelled": "Task [task_1] cancelled — teammate worker.\nNo worker summary was produced.",
    }
    assert "sendMainSessionUpdate(terminalSubject, terminalBody, params.taskId);" in source("index.ts")


def test_terminal_delivery_contract_uses_child_close_as_authoritative_boundary() -> None:
    ext = source("index.ts")
    report_start = ext.index('name: "teammate_report"')
    report_end = ext.index("function notifyUnblockedTasks", report_start)
    report = ext[report_start:report_end]
    assert "sendMainSessionUpdate" not in report
    finalize_start = ext.index("const finalizeWorker")
    finalize_end = ext.index("const finish", finalize_start)
    finalize = ext[finalize_start:finalize_end]
    assert "applyWorkerEvents(stateFile);" in finalize
    assert "buildTerminalResult" in finalize
    assert "sendMessage({" in finalize
    assert "sendMainSessionUpdate(terminalSubject, terminalBody, params.taskId);" in finalize


def test_normal_exit_is_required_for_success() -> None:
    module = (SRC / "spawner.ts").as_uri()
    payload = run_node(
        f'''\
        import {{ isSuccessfulWorkerExit }} from "{module}";
        const check = (exitCode, signal, timedOut) => isSuccessfulWorkerExit({{ exitCode, signal, timedOut }});
        console.log(JSON.stringify({{
          normal: check(0, null, false),
          nonZero: check(1, null, false),
          signal: check(null, "SIGTERM", false),
          timeout: check(null, "SIGKILL", true),
        }}));
        '''
    )
    assert payload == {"normal": True, "nonZero": False, "signal": False, "timeout": False}


def test_state_runtime_reuses_teammates_tracks_access_and_expires_only_after_ttl() -> None:
    module = (SRC / "state.ts").as_uri()
    payload = run_node(
        f'''\
        import {{ configureTeammate, createTask, findReusableTeammate, findSharedWorkspaceWriteConflict, getState, listTasks, pruneFinishedTasks, registerTeammate, retireExpiredTeammates, retryFailedTask, sendMessage, setSpawnInfo, updateTaskStatus }} from "{module}";
        registerTeammate({{ name: "worker", role: "worker", description: "old", prompt: "shared", registeredAt: 1, lastActiveAt: 1 }});
        registerTeammate({{ name: "reader", role: "reviewer", description: "", prompt: "review", registeredAt: 1, lastActiveAt: 1 }});
        registerTeammate({{ name: "writer", role: "worker", description: "", prompt: "write", registeredAt: 1, lastActiveAt: 1 }});
        registerTeammate({{ name: "stale", role: "observer", description: "", prompt: "observe", registeredAt: 1, lastActiveAt: 1 }});
        const empty = configureTeammate("worker", {{}});
        const configured = configureTeammate("worker", {{ description: "new" }});
        const reusable = findReusableTeammate({{ role: "worker", prompt: "shared", model: undefined, tools: undefined }})?.name;
        const differentPrompt = findReusableTeammate({{ role: "worker", prompt: "different", model: undefined, tools: undefined }})?.name;
        const first = createTask("first", "", ["packages/api"], "write", "worker", "agent").task;
        const read = createTask("read", "", ["packages/api/src"], "read", "reader", "agent").task;
        const write = createTask("write", "", ["packages/api/src"], "write", "writer", "agent").task;
        const invalid = createTask("invalid", "", ["../secrets"], "write", "worker", "agent");
        setSpawnInfo(first.id, {{ runId: "run-1", pid: 1, status: "running", startedAt: 1, isolation: "none" }});
        updateTaskStatus(first.id, "in_progress");
        const writeConflict = findSharedWorkspaceWriteConflict(write.id)?.id;
        const readConflict = findSharedWorkspaceWriteConflict(read.id);
        updateTaskStatus(first.id, "completed", "kept result");
        const prunedWhileRunning = pruneFinishedTasks();
        const retainedWhileRunning = listTasks().some((task) => task.id === first.id);
        setSpawnInfo(first.id, {{ runId: "run-1", pid: 1, status: "failed", startedAt: 1, finishedAt: 2, isolation: "none" }});
        const retry = retryFailedTask(first.id);
        sendMessage({{ from: "agent", to: "stale", subject: "pending", body: "reply" }});
        const expiredWithUnread = retireExpiredTeammates(100, 200);
        getState().mailboxes.stale[0].read = true;
        const expiredAfterRead = retireExpiredTeammates(100, 200);
        console.log(JSON.stringify({{
          empty: empty.ok,
          configured: configured.ok,
          reusable,
          differentPrompt: differentPrompt ?? null,
          read: read?.id,
          write: write?.id,
          invalid: invalid.error,
          prunedWhileRunning,
          retainedWhileRunning,
          retry: retry.ok,
          writeConflict: writeConflict ?? null,
          readConflict: readConflict?.id ?? null,
          expiredWithUnread,
          expiredAfterRead,
        }}));
        '''
    )
    assert payload == {
        "empty": False,
        "configured": True,
        "reusable": "worker",
        "differentPrompt": None,
        "read": "task_2",
        "write": "task_3",
        "invalid": 'Invalid task path: "../secrets".',
        "prunedWhileRunning": 0,
        "retainedWhileRunning": True,
        "retry": True,
        "writeConflict": "task_1",
        "readConflict": None,
        "expiredWithUnread": 0,
        "expiredAfterRead": 1,
    }


def test_session_start_does_not_restore_a_previous_team_and_shutdown_stops_workers() -> None:
    ext = source("index.ts")
    session_start = ext[ext.index('pi.on("session_start"'):ext.index('pi.on("session_shutdown"')]
    session_shutdown = ext[ext.index('pi.on("session_shutdown"'):ext.index('pi.on("turn_end"')]
    assert "resetState()" in session_start
    assert "tryRestoreState" not in session_start
    assert "await terminateAllWorkers()" in session_shutdown
    assert "persistState(pi)" not in session_shutdown


def test_statefile_outbox_reads_complete_records_only(tmp_path: Path) -> None:
    module = (SRC / "statefile.ts").as_uri()
    payload = run_node(
        f'''\
        import * as fs from "node:fs";
        import * as path from "node:path";
        import {{ appendWorkerEvent, readWorkerEvents, workerOutboxPath }} from "{module}";
        const stateFile = path.join(process.argv[1], "state.json");
        const outbox = workerOutboxPath(stateFile, "worker/a", "run-1");
        appendWorkerEvent(outbox, {{ id: "one", type: "message", worker: "worker/a", runId: "run-1", to: "agent", subject: "s", body: "b" }});
        const first = readWorkerEvents(outbox, 0);
        fs.appendFileSync(outbox, '{{"id":"partial"');
        const partial = readWorkerEvents(outbox, first.nextOffset);
        fs.appendFileSync(outbox, '}}\\n');
        const second = readWorkerEvents(outbox, first.nextOffset);
        console.log(JSON.stringify({{ first: first.events.length, partial: partial.events.length, stable: partial.nextOffset === first.nextOffset, second: second.events.length }}));
        ''',
        str(tmp_path),
    )
    assert payload == {"first": 1, "partial": 0, "stable": True, "second": 1}


def test_console_is_fullscreen_display_only_and_uses_working_text() -> None:
    ext = source("index.ts")
    assert 'registerCommand("teammate"' in ext
    assert "ctx.ui.custom" in ext
    assert "onTerminalInput" not in ext
    assert "working..." in ext
    assert "setWidget" in ext


def test_tool_failures_throw_and_guidance_lists_the_full_surface() -> None:
    ext = source("index.ts")
    spawner = source("spawner.ts")

    assert "isError" not in ext
    for message in (
        "This capability is available only inside a spawned teammate.",
        "Workers may message one teammate or agent, not broadcast.",
        "The role filter is only valid when to is all.",
        "Waiting for parallel tasks was cancelled.",
        "Timed out waiting for:",
        "Failed to start worker:",
    ):
        assert f'throw new Error(`{message}' in ext or f'throw new Error("{message}' in ext

    guidance = ext[ext.index("const TEAMMATE_GUIDANCE"):ext.index("export default function")]
    for tool in LEADER_TOOLS:
        assert tool in guidance
    assert "reuse a compatible role/model/tool/prompt configuration" in guidance
    assert "Only the harness-delivered terminal result triggers a main-session follow-up" in guidance
    assert "Use Pi's read tool to inspect the snapshot" in spawner
    assert "`cat ${opts.stateFile}`" not in spawner


def test_empty_lists_and_terminal_waits_remain_normal_results() -> None:
    ext = source("index.ts")
    leader = ext[ext.index("// ── Leader tools"):]
    teammate_list = leader[leader.index('name: "teammate_list"'):leader.index('name: "teammate_message"')]
    task_list = leader[leader.index('name: "teammate_list_tasks"'):leader.index('name: "teammate_wait"')]
    wait = leader[leader.index('name: "teammate_wait"'):leader.index('name: "teammate_configure"')]

    assert "No teammates registered yet." in teammate_list
    assert "return {" in teammate_list
    assert "No tasks found." in task_list
    assert "return {" in task_list
    assert 'new Set(["completed", "failed", "cancelled"])' in wait
    assert "if (tasks.every(isSettled)) break;" in wait


def test_readme_documents_the_target_surface() -> None:
    readme = (PACKAGE / "README.md").read_text(encoding="utf-8")
    for tool in LEADER_TOOLS | {"teammate_report"}:
        assert f"`{tool}`" in readme
    for tool in LEGACY_TOOLS:
        assert f"`{tool}`" not in readme
    assert "not a registerable role" in readme
    assert "reuse a compatible role/model/tool configuration" in readme
    assert "read" in readme and "write" in readme
    assert "retry=true" in readme
    assert "blockedBy" in readme
