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
        "Teammate configuration is a persistent resource",
        "Tasks are immutable definitions until their run starts",
        "A task run is explicit and never blocks the leader",
        "Messaging is symmetric and capability-bound",
        "Worker process outcomes are authoritative",
        "teammate_create_task",
        "teammate_start_task",
        "teammate_cancel_task",
        "teammate_report",
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


def test_create_task_owns_assignment_and_dependency_direction() -> None:
    ext = source("index.ts")
    state = source("state.ts")
    create_start = ext.index('name: "teammate_create_task"')
    create_end = ext.index('name: "teammate_list_tasks"', create_start)
    create_body = ext[create_start:create_end]
    assert "createTask(params.title, params.description, params.assignee, \"agent\", params.blockedBy ?? [])" in create_body
    assert "New task:" in create_body
    assert "uniqueBlockedBy" in state
    assert "for (const dep of uniqueBlockedBy)" in state
    assert "setTaskDeps" not in state


def test_start_task_uses_assignee_and_requires_explicit_retry() -> None:
    ext = source("index.ts")
    start = ext.index('name: "teammate_start_task"')
    end = ext.index('name: "teammate_cancel_task"', start)
    body = ext[start:end]
    assert "getTeammate(task.assignee)" in body
    assert "params.retry === true" in body
    assert "use retry=true" in body
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
    cancel_start = ext.index('name: "teammate_cancel_task"')
    cancel_end = ext.index('name: "teammate_remove"', cancel_start)
    cancel_body = ext[cancel_start:cancel_end]
    assert "cancelTask(params.taskId)" in cancel_body
    assert 'killWorker(task.assignee, "SIGTERM")' in cancel_body
    assert "export function cancelTask" in state
    assert 'task.status === "completed" || task.status === "cancelled"' in state
    assert "force" not in source("types.ts")


def test_remove_is_idle_only_and_cleanup_is_terminal_only() -> None:
    ext = source("index.ts")
    state = source("state.ts")
    assert "activeTask" in state
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


def test_unified_message_and_inbox_authorization() -> None:
    ext = source("index.ts")
    worker_section = ext[ext.index("function registerWorkerCapabilities"):ext.index("function notifyUnblockedTasks")]
    assert 'params.to === "all" || params.role' in worker_section
    assert 'params.to !== "agent" && !snapshot?.teammates[params.to]' in worker_section
    assert "acknowledgedWorkerMessageIds" in worker_section
    leader_message = ext[ext.index('name: "teammate_message"', ext.index("// ── Leader tools")):ext.index('name: "teammate_inbox"', ext.index("// ── Leader tools"))]
    assert 'params.to === "all"' in leader_message
    assert "params.role" in leader_message
    assert "if (liveStateFile) applyWorkerEvents(liveStateFile);" in ext


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


def test_state_runtime_enforces_configuration_and_terminal_cleanup() -> None:
    module = (SRC / "state.ts").as_uri()
    payload = run_node(
        f'''\
        import {{ cancelTask, configureTeammate, createTask, listTasks, pruneFinishedTasks, registerTeammate, updateTaskStatus }} from "{module}";
        registerTeammate({{ name: "worker", role: "worker", description: "old", prompt: "old", registeredAt: 1 }});
        const empty = configureTeammate("worker", {{}});
        const configured = configureTeammate("worker", {{ description: "new" }});
        const first = createTask("first", "", "worker", "agent").task;
        const second = createTask("second", "", "worker", "agent", [first.id, first.id]).task;
        const deduped = second.blockedBy.length;
        updateTaskStatus(first.id, "completed");
        const cancelled = cancelTask(second.id);
        const removed = pruneFinishedTasks();
        console.log(JSON.stringify({{
          empty: empty.ok,
          configured: configured.ok,
          deduped,
          cancelled: cancelled.task.status,
          removed,
          remaining: listTasks().length,
        }}));
        '''
    )
    assert payload == {
        "empty": False,
        "configured": True,
        "deduped": 1,
        "cancelled": "cancelled",
        "removed": 2,
        "remaining": 0,
    }


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


def test_readme_documents_the_target_surface() -> None:
    readme = (PACKAGE / "README.md").read_text(encoding="utf-8")
    for tool in LEADER_TOOLS | {"teammate_report"}:
        assert f"`{tool}`" in readme
    for tool in LEGACY_TOOLS:
        assert f"`{tool}`" not in readme
    assert "not a registerable role" in readme
    assert "retry=true" in readme
    assert "blockedBy" in readme
