from __future__ import annotations

import json
import subprocess
import textwrap
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
SRC = PACKAGE / "src"

LEADER_TOOLS = {
    "teammate_run",
    "teammate_message",
    "teammate_cancel",
    "teammate_retry",
}
WORKER_TOOLS = {"teammate_message"}
REMOVED_TOOLS = {
    "teammate_status",
    "teammate_report",
    "teammate_inbox",
    "teammate_register",
    "teammate_list",
    "teammate_configure",
    "teammate_remove",
    "teammate_create_task",
    "teammate_list_tasks",
    "teammate_start_task",
    "teammate_cancel_task",
    "teammate_cleanup",
}
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
    assert manifest["pi"] == {"extensions": ["./index.ts"]}
    assert "skills" not in manifest["files"]
    assert not (PACKAGE / "skills").exists()
    # Declarative agent files ship with the package.
    assert "agents" in manifest["files"] or (PACKAGE / "agents").exists()


def test_bdd_contract_covers_target_resources() -> None:
    feature = (PACKAGE / "features" / "agent-teams.feature").read_text(encoding="utf-8")
    for phrase in (
        "Agents are declarative Markdown files",
        "Discover agents from bundled, user, and project scopes",
        "Project agents override user and bundled agents with the same name",
        "Agent frontmatter declares tools and model; the body is the role prompt",
        "Agent descriptions are injected into prompt guidance",
        "An unknown agent name fails the dispatch",
        "Workers use turn budgets instead of wall-clock timeouts",
        "The default turn budget is high and only protects edge cases",
        "A completed worker may dynamically fan out child tasks",
        "Fanout rejects invalid source output before spawning",
        "Input bindings resolve only declared dependency data",
        "Structured output is bounded before entering run state",
        "Named data flow and fork context stay explicit",
        "Runtime steer is delivered only through teammate_message",
        "A run is a single-call DAG dispatch",
        "Dispatch a single task in one call",
        "Dispatch a dependency graph in one call",
        "Downstream nodes auto-start after their dependencies complete",
        "Concurrency bounds simultaneous workers",
        "Teammates run in the background by default",
        "A long inline run detaches to background after the gather cap",
        "Cancel one node while the rest of the run continues",
        "Retry failed and cancelled nodes without re-running completed ones",
        "Workers report exclusively to the team leader",
        "No peer or leader-to-worker channels exist",
        "Completing a node injects its result into downstream prompts",
        "Messages carry no read receipts",
        "Multi-node runs synthesize a final summary by default",
        "Read nodes with overlapping paths may run concurrently",
        "Write nodes with overlapping paths are blocked without worktree isolation",
        "Worktree isolation allows parallel write experiments",
        "A failed node fails the run and downstream nodes are not started",
        "Reject malformed task graphs",
        "Reject ambiguous path ownership",
        "Run lifecycle is explicit",
        "The leader coordinates through dispatch, runtime steer, cancel, and retry",
        "Each completed teammate notifies the leader immediately",
        "Automatic teammate follow-ups are serialized",
        "exactly one idle prompt reservation is active before agent start",
        "later reports use the follow-up queue instead of starting another prompt",
        "When agent_settled fires",
        "A failed automatic follow-up preserves reports and retries with backoff",
        "A delayed follow-up cannot cross a session boundary",
        "Run completion is delivered automatically without a wait tool",
        "worker's teammate_message reports are available to the leader",
        "single-node run delivers its result directly through teammate_message",
        "Cancel a run stops its running nodes",
        "Runs do not survive session restarts",
        "Messaging is capability-bound and leader-only",
        "Prompt guidance does not embed live run status",
        "A session-wide cap bounds concurrent worker processes",
        "Long task prompts spill to a temporary file that is removed on close",
        "The shared state snapshot is persisted on transitions, not per stream delta",
        "Background runs drain worker reports",
        "Worker setup failures clean temporary task files and settle the node",
        "A worker delivers its outcome via teammate_message",
        "Intermediate worker communication does not interrupt the main session",
        "The harness delivers one canonical terminal result per node",
        "Workers cannot access leader tools",
        "Worker process outcomes are authoritative",
        "Worker children run with only the agent-teams extension",
        "A normal worker exit completes its node",
        "An abnormal worker exit fails its node",
        "Completed run metadata is compacted safely",
        "Invalid tool operations surface as Pi failures",
        "Inline foreground gather remains the explicit sync option",
        "Legitimate empty and terminal data remains a normal result",
        "Console is a user interface, not an agent tool substitute",
        "Console shows live teammate activity without intercepting global input",
        "long tool activity is truncated inline with an ellipsis",
        "a teammate widget row never wraps a truncation notice onto a second line",
        "the idle widget stays hidden until a teammate is running",
        "Detail scrolling preserves every wrapped display line",
    ):
        assert phrase in feature


def test_console_supports_mouse_wheel_scrolling() -> None:
    ext = source("ui.ts")
    assert "const sgrWheel = /^\\x1b\\[<(\\d+);(\\d+);(\\d+)[Mm]$/" in ext
    assert "(button & 64) !== 0" in ext
    assert "direction === 0" in ext and "direction === 1" in ext


def test_leader_tool_surface_is_exact() -> None:
    ext = source("index.ts") + source("tools.ts")
    for tool in LEADER_TOOLS:
        assert f'name: "{tool}"' in ext
    assert 'name: "teammate_message"' in source("worker.ts")
    for tool in REMOVED_TOOLS | LEGACY_TOOLS:
        assert f'name: "{tool}"' not in ext


def test_worker_surface_is_capability_bound() -> None:
    ext = source("index.ts")
    worker = source("worker.ts")
    for tool in WORKER_TOOLS:
        assert f'name: "{tool}"' in worker
    for tool in LEADER_TOOLS - WORKER_TOOLS:
        assert f'name: "{tool}"' not in worker
    assert "if (workerOutboxBinding())" in ext
    assert "registerWorkerCapabilities(pi);" in ext
    assert "return;" in ext[ext.index("if (workerOutboxBinding())"):ext.index("leaderPi = pi;")]
    assert "PI_TEAMMATE_STATE_FILE" not in worker


def test_idle_widget_stays_hidden_until_a_teammate_is_running() -> None:
    ext = source("ui.ts")
    # Widget is hidden when no teammates are running
    assert 'if (running.length === 0) {' in ext
    assert 'ctx.ui.setWidget("teammate", undefined);' in ext
    assert "runningTeammateLabel" in ext
    assert "runningNodeLabel" not in ext


def test_widget_rows_align_with_native_loader_and_show_live_activity() -> None:
    ext = source("ui.ts")
    spawner = source("spawner.ts")
    types = source("types.ts")
    # Widget uses theme colors via createPiThemeStyle
    assert 'createPiThemeStyle(theme)' in ext
    assert 'const TEAM_COLORS = ["success", "warning", "error", "mdLink"] as const;' in ext
    assert 'assignedColors.set(node.workerKey, color ?? TEAM_COLORS[start]);' in ext
    assert 'style.fg(color, node.id)' in ext
    assert 'style.dim(`(${node.agent})`)' in ext
    assert 'const spinner = separator === -1 ? label : label.slice(0, separator)' in ext
    assert 'theme.bold(style.fg("accent", activityText))' in ext
    # The pi-kit spinner is first, followed by the colored identity and bold activity.
    assert 'const line = ` ${spinner} ${name} ${role} · ${activity}`' in ext
    assert 'const activityText = separator === -1 ? "Working..." : label.slice(separator + 1).trim();' in ext
    assert 'PI_SPINNER_FRAMES[spinnerFrame]' in ext
    # Widget is placed belowEditor (under the input box)
    assert 'placement: "belowEditor"' in ext
    # Live activity: current tool first, then reasoning, then text.
    assert "node.spawn?.activeTool" in ext and "liveThinking" in ext
    assert "liveThinking?: string" in types
    # The JSON stream parser tracks streamed tool calls and live execution events.
    assert '"toolcall_start"' in spawner and '"toolcall_delta"' in spawner and '"toolcall_end"' in spawner
    assert 'event.type === "tool_execution_start"' in spawner
    assert 'event.type === "tool_execution_end"' in spawner
    assert 'state.activeTool = undefined;' in spawner
    assert 'case "toolcall_end":' in spawner
    # Reasoning deltas are accumulated for the activity line.
    assert '"thinking_delta"' in spawner
    # Tool labels are collapsed and truncated inline so a long command cannot
    # add a visible "[truncated N chars]" row to the passive widget.
    assert 'function truncateInline' in spawner
    assert 'text.replace(/\\s+/g, " ").trim()' in spawner
    assert 'return `${oneLine.slice(0, cap).trimEnd()} ...`' in spawner
    assert 'bash: ${truncateInline(command, 40)}' in spawner


def test_types_express_run_centric_surface() -> None:
    types = source("types.ts")
    for schema in (
        "TeammateRunParams",
        "TeammateCancelParams",
        "TeammateRetryParams",
        "TeammateMessageParams",
        "RunTaskSpec",
    ):
        assert f"export const {schema}" in types
    assert "TeammateStatusParams" not in types
    assert "TeammateReportParams" not in types
    assert "foregroundTimeoutMs" not in types
    assert "turnBudget" in types
    assert "timeoutMs" not in types
    assert "deadlineAt" not in types
    assert "nodeId: Type.Optional" in types
    assert "markRead" not in types
    assert "workerKey" in types
    for old_schema in (
        "TeammateRegisterParams",
        "TeammateConfigureParams",
        "TeammateCreateTaskParams",
        "TeammateListTasksParams",
        "TeammateStartTaskParams",
        "TeammateCancelTaskParams",
    ):
        assert old_schema not in types


def test_read_receipt_protocol_is_removed() -> None:
    types = source("types.ts")
    state = source("state.ts")
    ext = source("index.ts")
    assert "message_read" not in types
    assert "WorkerMessageReadEvent" not in types
    assert "message_read" not in ext
    assert "syncReadFlagsToFile" not in ext
    assert "acknowledgedWorkerMessageIds" not in ext
    assert "emits receipts" not in source("spawner.ts")
    assert "emits read receipts" not in ext
    # The dead read flag is gone from the message shape.
    assert "read: boolean" not in types
    assert "read: false" not in state


def test_workers_report_only_to_the_team_leader() -> None:
    state = source("state.ts")
    worker = source("worker.ts")
    machine = source("run-machine.ts")
    types = source("types.ts")
    assert "resolveWorkerRecipientFromRuns" not in state
    assert "resolveLeaderRecipient" not in state
    assert "sentMessages" not in types and "inboxMessages" not in types
    assert "recipient" not in worker
    assert "=== UPSTREAM HANDOFF ===" in machine
    assert "PI_TEAMMATE_STATE_FILE" not in worker
    message_schema = types[types.index("export const TeammateMessageParams"):types.index("/** Leader-only operation")]
    assert "to:" not in message_schema and "runId:" not in message_schema

def test_node_cancel_keeps_run_running() -> None:
    module = (SRC / "state.ts").as_uri()
    payload = run_node(
        f'''\
        import {{ createRun, resetState, cancelNode, setNodeSpawnInfo }} from "{module}";
        resetState();
        const created = createRun({{ cwd: "/tmp", concurrency: 2, worktree: false, background: false,
          nodes: [
            {{ id: "a", agent: "worker", prompt: "", paths: ["x"], access: "read", dependsOn: [] }},
            {{ id: "b", agent: "worker", prompt: "", paths: ["y"], access: "read", dependsOn: [] }},
            {{ id: "c", agent: "worker", prompt: "", paths: ["z"], access: "read", dependsOn: ["b"] }},
          ] }});
        const run = created.run;
        setNodeSpawnInfo(run.id, "b", {{ spawnId: "s1", pid: 1, status: "running", startedAt: 1, isolation: "none" }});
        setNodeSpawnInfo(run.id, "c", {{ spawnId: "s2", pid: 2, status: "running", startedAt: 1, isolation: "none" }});
        const cancelled = cancelNode(run.id, "b");
        console.log(JSON.stringify({{ ok: cancelled.ok, running: cancelled.runningNodeIds.join(","), b: run.nodes.b.status, c: run.nodes.c.status, a: run.nodes.a.status, runStatus: run.status }}));
        '''
    )
    # b was cancelled while running (its worker must be terminated by the caller);
    # c was running on a cancelled prerequisite (b) and is propagated for termination;
    # unrelated node a stays pending; the run itself keeps running.
    assert payload == {
        "ok": True,
        "running": "b,c",
        "b": "running",
        "c": "running",
        "a": "pending",
        "runStatus": "running",
    }


def test_agent_definitions_are_declarative_files() -> None:
    agents_src = source("agents.ts")
    assert "discoverAgents" in agents_src
    assert "resolveAgent" in agents_src
    assert '"bundled"' in agents_src and '"user"' in agents_src and '"project"' in agents_src
    assert "PI_CODING_AGENT_DIR" in agents_src
    assert ".pi" in agents_src and "agents" in agents_src
    bundled = sorted(path.name for path in (PACKAGE / "agents").glob("*.md"))
    assert {"worker.md", "reviewer.md", "specialist.md", "observer.md"} <= set(bundled)
    worker = (PACKAGE / "agents" / "worker.md").read_text(encoding="utf-8")
    assert "name: worker" in worker
    assert "description:" in worker
    assert "tools:" in worker


def test_agent_frontmatter_parses_tools_and_model() -> None:
    module = (SRC / "agents.ts").as_uri()
    payload = run_node(
        f'''\
        import {{ resolveAgent, discoverAgents }} from "{module}";
        const bundled = discoverAgents();
        const worker = bundled.get("worker");
        const reviewer = bundled.get("reviewer");
        console.log(JSON.stringify({{
          workerTools: worker?.tools ?? [],
          workerPrompt: Boolean(worker?.prompt?.includes("worker agent")),
          workerScope: worker?.scope,
          reviewerTools: reviewer?.tools ?? [],
          hasUnknown: bundled.has("no-such-agent"),
        }}));
        '''
    )
    assert payload == {
        "workerTools": ["read", "bash", "edit", "write"],
        "workerPrompt": True,
        "workerScope": "bundled",
        "reviewerTools": ["read", "bash"],
        "hasUnknown": False,
    }


def test_agent_frontmatter_strips_inline_comments(tmp_path) -> None:
    module = (SRC / "agents.ts").as_uri()
    agents_dir = tmp_path / ".pi" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "commented.md").write_text(
        "---\n"
        "name: commented\n"
        "description: Agent with comments\n"
        "tools: read, bash  # read-only audit\n"
        "model: provider/model  # pinned\n"
        "---\n"
        "You are the commented agent.\n",
        encoding="utf-8",
    )
    payload = run_node(
        f'''\
        import {{ discoverAgents }} from "{module}";
        const agents = discoverAgents("{tmp_path}");
        const agent = agents.get("commented");
        console.log(JSON.stringify({{ tools: agent?.tools ?? [], model: agent?.model ?? null }}));
        '''
    )
    assert payload == {"tools": ["read", "bash"], "model": "provider/model"}


def test_project_agent_overrides_bundled_and_user(tmp_path) -> None:
    module = (SRC / "agents.ts").as_uri()
    agents_dir = tmp_path / ".pi" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "reviewer.md").write_text(
        "---\n"
        "name: reviewer\n"
        "description: Project-scoped reviewer override\n"
        "tools: read\n"
        "---\n"
        "Project reviewer prompt.\n",
        encoding="utf-8",
    )
    payload = run_node(
        f'''\
        import {{ discoverAgents }} from "{module}";
        const project = discoverAgents("{tmp_path}");
        const reviewer = project.get("reviewer");
        const bundled = discoverAgents();
        console.log(JSON.stringify({{
          scope: reviewer?.scope,
          tools: reviewer?.tools ?? [],
          prompt: reviewer?.prompt ?? "",
          bundledPrompt: bundled.get("reviewer")?.prompt ?? "",
        }}));
        '''
    )
    assert payload["scope"] == "project"
    assert payload["tools"] == ["read"]
    assert "Project reviewer prompt" in payload["prompt"]
    assert "Project reviewer prompt" not in payload["bundledPrompt"]


def test_summary_node_appends_after_leaves_and_reserves_its_id() -> None:
    module = (SRC / "state.ts").as_uri()
    payload = run_node(
        f'''\
        import {{ createRun, resetState, SUMMARY_NODE_ID }} from "{module}";
        resetState();
        const created = createRun({{ cwd: "/tmp", concurrency: 2, worktree: false, background: false,
          nodes: [
            {{ id: "a", agent: "worker", prompt: "", paths: ["x"], access: "read", dependsOn: [] }},
            {{ id: "b", agent: "worker", prompt: "", paths: ["y"], access: "read", dependsOn: [] }},
            {{ id: "c", agent: "worker", prompt: "", paths: ["z"], access: "read", dependsOn: ["a"] }},
          ] }});
        const run = created.run;
        const summary = run.nodes[SUMMARY_NODE_ID];
        const conflict = createRun({{ cwd: "/tmp", concurrency: 1, worktree: false, background: false, summarize: true,
          nodes: [{{ id: SUMMARY_NODE_ID, agent: "worker", prompt: "", paths: ["x"], access: "read", dependsOn: [] }}] }});
        console.log(JSON.stringify({{
          summaryExists: Boolean(summary),
          summaryAgent: summary?.agent,
          summaryDepends: summary?.dependsOn.join(","),
          summaryStatus: summary?.status,
          summaryAccess: summary?.access,
          conflictOk: conflict.ok,
        }}));
        '''
    )
    assert payload["summaryExists"] is True
    assert payload["summaryAgent"] == "observer"
    # Leaves are b and c (c depends on a, so a is not a leaf); the summary runs after both.
    assert sorted(payload["summaryDepends"].split(",")) == ["b", "c"]
    assert payload["summaryStatus"] == "pending"
    assert payload["summaryAccess"] == "read"
    assert payload["conflictOk"] is False


def test_single_task_run_skips_summary_unless_requested() -> None:
    module = (SRC / "state.ts").as_uri()
    payload = run_node(
        f'''\
        import {{ createRun, resetState, SUMMARY_NODE_ID }} from "{module}";
        resetState();
        const implicit = createRun({{ cwd: "/tmp", concurrency: 1, worktree: false, background: false,
          nodes: [{{ id: "only", agent: "worker", prompt: "", paths: ["x"], access: "read", dependsOn: [] }}] }});
        const explicit = createRun({{ cwd: "/tmp", concurrency: 1, worktree: false, background: false, summarize: true,
          nodes: [{{ id: "only", agent: "worker", prompt: "", paths: ["x"], access: "read", dependsOn: [] }}] }});
        const off = createRun({{ cwd: "/tmp", concurrency: 2, worktree: false, background: false, summarize: false,
          nodes: [
            {{ id: "a", agent: "worker", prompt: "", paths: ["x"], access: "read", dependsOn: [] }},
            {{ id: "b", agent: "worker", prompt: "", paths: ["y"], access: "read", dependsOn: [] }},
          ] }});
        console.log(JSON.stringify({{
          implicit: Boolean(implicit.run.nodes[SUMMARY_NODE_ID]),
          explicit: Boolean(explicit.run.nodes[SUMMARY_NODE_ID]),
          off: Boolean(off.run.nodes[SUMMARY_NODE_ID]),
        }}));
        '''
    )
    assert payload == {"implicit": False, "explicit": True, "off": False}


def test_worker_report_is_leader_only_and_deduplicated() -> None:
    module = (SRC / "state.ts").as_uri()
    payload = run_node(
        f'''\
        import {{ createRun, resetState, receiveWorkerMessage, getState }} from "{module}";
        resetState();
        const created = createRun({{ cwd: "/tmp", concurrency: 1, worktree: false, background: false, summarize: false,
          nodes: [{{ id: "a", agent: "worker", prompt: "", paths: ["x"], access: "read", dependsOn: [] }}] }});
        const run = created.run;
        run.nodes.a.spawn = {{ spawnId: "spawn-1", pid: 1, status: "running", startedAt: 1, isolation: "none" }};
        const event = {{ id: "evt-1", worker: run.nodes.a.workerKey, spawnId: "spawn-1", type: "message", subject: "Plan", body: "ready" }};
        const first = receiveWorkerMessage(event);
        const duplicate = receiveWorkerMessage(event);
        console.log(JSON.stringify({{ first, duplicate, messages: getState().leaderMailbox.map((m) => m.subject).join(","), runId: getState().leaderMailbox[0]?.runId }}));
        '''
    )
    assert payload == {"first": True, "duplicate": False, "messages": "Plan", "runId": "run_1"}

def test_run_creation_rejects_malformed_graphs() -> None:
    module = (SRC / "state.ts").as_uri()
    payload = run_node(
        f'''\
        import {{ createRun, resetState }} from "{module}";
        resetState();
        const node = (id, dependsOn = []) => ({{
          id, agent: "worker", prompt: "do it", paths: ["packages/a"], access: "read", dependsOn,
        }});
        const dup = createRun({{ cwd: "/tmp", concurrency: 2, worktree: false, background: false, summarize: false,
          nodes: [node("a"), node("a")] }});
        const unknownDep = createRun({{ cwd: "/tmp", concurrency: 2, worktree: false, background: false, summarize: false,
          nodes: [node("a", ["ghost"])] }});
        const cycle = createRun({{ cwd: "/tmp", concurrency: 2, worktree: false, background: false, summarize: false,
          nodes: [node("a", ["b"]), node("b", ["a"])] }});
        const badPath = createRun({{ cwd: "/tmp", concurrency: 2, worktree: false, background: false, summarize: false,
          nodes: [{{ ...node("a"), paths: ["/etc/passwd"] }}] }});
        const ok = createRun({{ cwd: "/tmp", concurrency: 2, worktree: false, background: false, summarize: false,
          nodes: [node("a"), node("b", ["a"])] }});
        console.log(JSON.stringify({{
          dupOk: dup.ok, dupError: dup.ok ? "" : dup.error,
          unknownDepOk: unknownDep.ok,
          cycleOk: cycle.ok,
          badPathOk: badPath.ok,
          okRun: ok.ok ? ok.run.id : "",
          okStatus: ok.ok ? ok.run.status : "",
          nodeKeys: ok.ok ? Object.keys(ok.run.nodes).join(",") : "",
          workerKey: ok.ok ? ok.run.nodes.a.workerKey : "",
          edges: ok.ok ? ok.run.nodes.b.dependsOn.join(",") : "",
        }}));
        '''
    )
    assert payload["dupOk"] is False
    assert "Duplicate node id" in payload["dupError"]
    assert payload["unknownDepOk"] is False
    assert payload["cycleOk"] is False
    assert payload["badPathOk"] is False
    assert payload["okRun"].startswith("run_")
    assert payload["okStatus"] == "running"
    assert payload["nodeKeys"] == "a,b"
    assert payload["workerKey"].startswith("run_1:a")
    assert payload["edges"] == "a"


def test_dependency_readiness_and_settlement() -> None:
    module = (SRC / "state.ts").as_uri()
    payload = run_node(
        f'''\
        import {{ createRun, resetState, nodeIsReady, settleRun, cancelBlockedDependents,
                 updateNodeStatus, runningNodeCount, listRuns }} from "{module}";
        resetState();
        const created = createRun({{ cwd: "/tmp", concurrency: 1, worktree: false, background: false, summarize: false,
          nodes: [
            {{ id: "a", agent: "worker", prompt: "", paths: ["x"], access: "read", dependsOn: [] }},
            {{ id: "b", agent: "worker", prompt: "", paths: ["y"], access: "read", dependsOn: ["a"] }},
            {{ id: "c", agent: "worker", prompt: "", paths: ["z"], access: "read", dependsOn: ["b"] }},
          ] }});
        const run = created.run;
        const before = {{
          aReady: nodeIsReady(run, run.nodes.a),
          bReady: nodeIsReady(run, run.nodes.b),
          running: runningNodeCount(run.id),
        }};
        updateNodeStatus(run.id, "a", "failed");
        const cancelled = cancelBlockedDependents(run.id, "a");
        const after = {{
          aStatus: run.nodes.a.status,
          bStatus: run.nodes.b.status,
          cStatus: run.nodes.c.status,
          cancelled,
          settled: settleRun(run.id),
        }};
        console.log(JSON.stringify({{ before, after }}));
        '''
    )
    assert payload["before"] == {"aReady": True, "bReady": False, "running": 0}
    assert payload["after"]["aStatus"] == "failed"
    assert payload["after"]["bStatus"] == "cancelled"
    assert payload["after"]["cStatus"] == "cancelled"
    assert payload["after"]["cancelled"] == 2
    assert payload["after"]["settled"] == "failed"


def test_write_conflict_detection_is_run_scoped() -> None:
    module = (SRC / "state.ts").as_uri()
    payload = run_node(
        f'''\
        import {{ createRun, resetState, findSharedWorkspaceWriteConflict, setNodeSpawnInfo }} from "{module}";
        resetState();
        const created = createRun({{ cwd: "/tmp", concurrency: 2, worktree: false, background: false,
          nodes: [
            {{ id: "w1", agent: "worker", prompt: "", paths: ["packages/a"], access: "write", dependsOn: [] }},
            {{ id: "w2", agent: "worker", prompt: "", paths: ["packages/a/lib"], access: "write", dependsOn: [] }},
            {{ id: "r", agent: "reviewer", prompt: "", paths: ["packages/a"], access: "read", dependsOn: [] }},
          ] }});
        const run = created.run;
        setNodeSpawnInfo(run.id, "w1", {{ spawnId: "s1", pid: 1, status: "running", startedAt: 1, isolation: "none" }});
        const writeOverlap = findSharedWorkspaceWriteConflict(run.id, "w2")?.id ?? null;
        const readOverlap = findSharedWorkspaceWriteConflict(run.id, "r")?.id ?? null;
        setNodeSpawnInfo(run.id, "w2", {{ spawnId: "s2", pid: 2, status: "running", startedAt: 1, isolation: "worktree" }});
        const isolated = findSharedWorkspaceWriteConflict(run.id, "w1")?.id ?? null;
        console.log(JSON.stringify({{ writeOverlap, readOverlap, isolated }}));
        '''
    )
    assert payload == {"writeOverlap": "w1", "readOverlap": None, "isolated": None}


def test_cancel_run_marks_pending_and_returns_running_nodes() -> None:
    module = (SRC / "state.ts").as_uri()
    payload = run_node(
        f'''\
        import {{ createRun, resetState, cancelRun, setNodeSpawnInfo, isRunTerminal }} from "{module}";
        resetState();
        const created = createRun({{ cwd: "/tmp", concurrency: 2, worktree: false, background: false,
          nodes: [
            {{ id: "a", agent: "worker", prompt: "", paths: ["x"], access: "read", dependsOn: [] }},
            {{ id: "b", agent: "worker", prompt: "", paths: ["y"], access: "read", dependsOn: [] }},
            {{ id: "c", agent: "worker", prompt: "", paths: ["z"], access: "read", dependsOn: ["a"] }},
          ] }});
        const run = created.run;
        setNodeSpawnInfo(run.id, "a", {{ spawnId: "s1", pid: 1, status: "running", startedAt: 1, isolation: "none" }});
        const cancelled = cancelRun(run.id);
        const terminal = isRunTerminal(run);
        console.log(JSON.stringify({{
          ok: cancelled.ok,
          runningNodeIds: cancelled.runningNodeIds.join(","),
          a: run.nodes.a.status,
          b: run.nodes.b.status,
          c: run.nodes.c.status,
          terminal,
        }}));
        '''
    )
    assert payload == {
        "ok": True,
        "runningNodeIds": "a",
        "a": "running",
        "b": "cancelled",
        "c": "cancelled",
        "terminal": False,
    }


def test_mailbox_is_leader_only_without_receipts() -> None:
    module = (SRC / "state.ts").as_uri()
    payload = run_node(
        f'''\
        import {{ createRun, resetState, deliverToLeader, receiveWorkerMessage, getState }} from "{module}";
        resetState();
        const created = createRun({{ cwd: "/tmp", concurrency: 1, worktree: false, background: false,
          nodes: [{{ id: "a", agent: "worker", prompt: "", paths: ["x"], access: "read", dependsOn: [] }}] }});
        const run = created.run;
        deliverToLeader({{ from: "run_1:a", subject: "harness", body: "hello", runId: run.id }});
        run.nodes.a.spawn = {{ spawnId: "s1", pid: 1, status: "running", startedAt: 1, isolation: "none" }};
        const event = {{ id: "evt-1", worker: run.nodes.a.workerKey, spawnId: "s1", type: "message", subject: "plan", body: "p" }};
        const delivered = receiveWorkerMessage(event);
        const duplicate = receiveWorkerMessage(event);
        const messages = getState().leaderMailbox.map((m) => m.subject).join(",");
        console.log(JSON.stringify({{ delivered, messages, duplicate, hasInbox: "inboxMessages" in run.nodes.a }}));
        '''
    )
    assert payload == {"delivered": True, "messages": "harness,plan", "duplicate": False, "hasInbox": False}

def test_worker_spawn_is_nonblocking_and_identity_bound() -> None:
    ext = source("run-machine.ts")
    spawner = source("spawner.ts")
    assert "spawnPiWorkerBlocking" not in ext
    assert '"--no-extensions"' in spawner
    assert '"--extension"' in spawner
    assert 'path.resolve(path.dirname(fileURLToPath(import.meta.url)), "index.ts")' in spawner
    assert "spawnPiWorkerBlocking" not in spawner
    assert "Your worker key:" not in spawner
    assert "inboxMessages" not in spawner
    assert "PI_TEAMMATE_WORKER_NAME: workerKey" in ext
    assert "PI_TEAMMATE_TASK_ID: node.id" in ext
    assert "PI_TEAMMATE_SPAWN_ID: spawnId" in ext
    assert 'const spawnId = randomUUID()' in ext
    assert 'getNode(runId, nodeId)?.spawn?.spawnId !== spawnId' in ext

def test_run_dispatch_is_single_call_with_scheduler() -> None:
    ext = source("index.ts") + source("tools.ts")
    machine = source("run-machine.ts")
    assert 'name: "teammate_run"' in ext
    assert "scheduleRun(run.id, dctx)" in ext
    assert "readyPendingNodes(run)" in machine
    assert "run.concurrency - runningNodeCount(runId)" in machine
    assert "MAX_SESSION_WORKERS" in machine
    assert "findSharedWorkspaceWriteConflict(runId, node.id)" in machine
    assert "startNode(runId, node.id, ctx)" in machine
    assert "onRunSettled(runId)" in machine
    assert "run.background && !run.completionNotified" in machine
    assert "markRunCompletionDelivered(runId)" in ext
    assert "background: params.background ?? true" in ext
    assert "reports to team-leader" in source("ui.ts")
    assert "if (run.background)" in ext

def test_tool_returns_are_compact_and_summary_is_synthesized() -> None:
    ext = source("index.ts") + source("tools.ts")
    machine = source("run-machine.ts")
    types = source("types.ts")
    assert "buildRunSummary" in machine
    assert "Console: /teammate" not in machine
    assert "buildRunSummary(runId)" in source("tools.ts")
    assert "nodeHeadline" not in machine
    assert "SUMMARY_NODE_ID" in machine
    assert "summarize" in types
    assert "summaryAgent" in types
    assert "settledRun.summary" in machine
    assert "if (run.summary)" in machine
    assert "node.result?.trim() || node.errorMessage?.trim()" in machine
    assert 'name: "teammate_wait"' not in ext
    assert 'name: "teammate_status"' not in ext
    assert "await sleep(" in ext

def test_guidance_is_static_and_run_centric() -> None:
    ext = source("index.ts")
    guidance = source("guidance.ts")
    agents = source("agents.ts")
    assert "formatAgentGuidance" in agents
    assert "buildTeamLeaderGuidance" in guidance
    assert "before_agent_start" in ext
    assert "teammate_run" in guidance
    assert 'name: "teammate_status"' not in ext
    assert "teammate_wait" not in ext
    assert "teammate_cancel" in guidance
    assert ".pi/agents" in guidance
    assert "~/.pi/agent/agents" in guidance
    assert "dependsOn" in guidance
    assert "Active background runs" not in guidance
    assert "listActiveRuns" not in guidance
    assert 'name: "teammate_message"' not in ext

def test_no_runtime_identity_registry_remains() -> None:
    state = source("state.ts")
    ext = source("index.ts") + source("tools.ts")
    for legacy in ("registerTeammate", "configureTeammate", "removeTeammate", "findReusableTeammate",
                   "retireExpiredTeammates", "retryFailedTask", "createTask(", "cancelTask(",
                   "setSpawnInfo(", "listTeammates", "markTeammateRunning"):
        assert legacy not in state and legacy not in ext


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


def test_is_completed_worker_exit_semantics() -> None:
    module = (SRC / "spawner.ts").as_uri()
    payload = run_node(
        f'''
        import {{ isCompletedWorkerExit, isSuccessfulWorkerExit }} from "{module}";
        const normalZero = isSuccessfulWorkerExit({{ exitCode: 0, signal: null, timedOut: false }});
        const abnormalExit = isSuccessfulWorkerExit({{ exitCode: 1, signal: null, timedOut: false }});
        const reportedCompletedWithSigterm = isCompletedWorkerExit({{ exitCode: null, signal: "SIGTERM", timedOut: false }}, true);
        const reportedCompletedWithTimeout = isCompletedWorkerExit({{ exitCode: null, signal: "SIGKILL", timedOut: true }}, true);
        const unreportedTimeout = isCompletedWorkerExit({{ exitCode: null, signal: "SIGKILL", timedOut: true }}, false);
        console.log(JSON.stringify({{ normalZero, abnormalExit, reportedCompletedWithSigterm, reportedCompletedWithTimeout, unreportedTimeout }}));
        '''
    )
    assert payload == {
        "normalZero": True,
        "abnormalExit": False,
        "reportedCompletedWithSigterm": True,
        "reportedCompletedWithTimeout": True,
        "unreportedTimeout": False,
    }


def test_spawner_prompt_focuses_on_direct_execution() -> None:
    module = (SRC / "spawner.ts").as_uri()
    payload = run_node(
        f'''
        import {{ buildAutonomousPrompt }} from "{module}";
        const prompt = buildAutonomousPrompt({{
          name: "worker_1",
          role: "reviewer",
          prompt: "Review code",
          taskId: "task_1",
          turnBudget: 12,
        }});
        console.log(JSON.stringify({{
          hasTask: prompt.includes("task_1"),
          hasTurnBudget: prompt.includes("12 assistant turn(s)"),
          hasDirectScope: prompt.includes("Work directly on your assigned scope"),
          hasDeliverInstruction: prompt.includes('status="completed"'),
        }}));
        '''
    )
    assert payload == {
        "hasTask": True,
        "hasTurnBudget": True,
        "hasDirectScope": True,
        "hasDeliverInstruction": True,
    }


def test_teammates_run_in_background_by_default() -> None:
    module = (SRC / "state.ts").as_uri()
    payload = run_node(
        f'''
        import {{ createRun, resetState }} from "{module}";
        resetState();
        const defaultRun = createRun({{
          cwd: "/tmp",
          concurrency: 2,
          worktree: false,
          nodes: [{{ id: "task_1", agent: "worker", prompt: "task 1", paths: ["src"], access: "read", dependsOn: [] }}]
        }});
        const explicitBgRun = createRun({{
          cwd: "/tmp",
          concurrency: 2,
          worktree: false,
          background: true,
          nodes: [{{ id: "task_2", agent: "worker", prompt: "task 2", paths: ["src"], access: "read", dependsOn: [] }}]
        }});
        const explicitFgRun = createRun({{
          cwd: "/tmp",
          concurrency: 2,
          worktree: false,
          background: false,
          nodes: [{{ id: "task_3", agent: "worker", prompt: "task 3", paths: ["src"], access: "read", dependsOn: [] }}]
        }});
        console.log(JSON.stringify({{
          defaultBackground: defaultRun.run?.background,
          explicitBgBackground: explicitBgRun.run?.background,
          explicitFgBackground: explicitFgRun.run?.background,
        }}));
        '''
    )
    assert payload == {
        "defaultBackground": True,
        "explicitBgBackground": True,
        "explicitFgBackground": False,
    }


def test_worker_message_delivers_completed_and_failed_status() -> None:
    machine = source("run-machine.ts")
    types = source("types.ts")
    assert 'status?: "in_progress" | "completed" | "failed"' in types
    assert 'updateNodeStatus(run.id, node.id, "completed", event.body, undefined)' in machine
    assert 'updateNodeStatus(run.id, node.id, "failed", undefined, event.body)' in machine
    assert 'name: "teammate_report"' not in machine


def test_leader_followups_use_a_lifecycle_aware_queue() -> None:
    index = source("index.ts")
    queue = source("follow-up-queue.ts")
    assert 'import { FollowUpQueue } from "./follow-up-queue"' in index
    assert "followUpQueue?.onBeforeAgentStart(event.prompt)" in index
    assert "followUpQueue?.onAgentStart()" in index
    assert "followUpQueue?.onAgentSettled()" in index
    assert "followUpQueue?.reset()" in index
    assert "agentStartTimeoutMs" in queue
    assert "retryBaseDelayMs" in queue
    assert "this.pending.unshift(...failed.reports)" in queue
    assert "generation !== this.generation" in queue
    assert "clearTimeout" in queue


def test_follow_up_queue_requeues_failed_dispatch_with_backoff() -> None:
    module = (SRC / "follow-up-queue.ts").as_uri()
    payload = run_node(f'''\
        import {{ FollowUpQueue }} from "{module}";
        const failures = [];
        const queue = new FollowUpQueue({{
          isIdle: () => true,
          dispatch: () => {{ throw new Error("preflight failed"); }},
          onFailure: (message) => failures.push(message),
          retryBaseDelayMs: 100000,
          retryMaxDelayMs: 100000,
        }});
        queue.enqueue({{ subject: "A", body: "report" }});
        await new Promise((resolve) => setTimeout(resolve, 10));
        const result = {{ pending: queue.pendingCount, failures: failures.length }};
        queue.reset();
        console.log(JSON.stringify(result));
        ''')
    assert payload == {"pending": 1, "failures": 1}


def test_follow_up_queue_requeues_when_void_dispatch_never_starts() -> None:
    module = (SRC / "follow-up-queue.ts").as_uri()
    payload = run_node(f'''\
        import {{ FollowUpQueue }} from "{module}";
        const failures = [];
        const queue = new FollowUpQueue({{
          isIdle: () => true,
          dispatch: () => {{}},
          onFailure: (message) => failures.push(message),
          agentStartTimeoutMs: 5,
          retryBaseDelayMs: 100000,
          retryMaxDelayMs: 100000,
        }});
        queue.enqueue({{ subject: "A", body: "report" }});
        await new Promise((resolve) => setTimeout(resolve, 20));
        const result = {{ pending: queue.pendingCount, failures: failures.length }};
        queue.reset();
        console.log(JSON.stringify(result));
        ''')
    assert payload == {"pending": 1, "failures": 1}


def test_follow_up_queue_ignores_stale_session_callbacks() -> None:
    module = (SRC / "follow-up-queue.ts").as_uri()
    payload = run_node(f'''\
        import {{ FollowUpQueue }} from "{module}";
        const sent = [];
        const queue = new FollowUpQueue({{
          isIdle: () => true,
          dispatch: (content) => sent.push(content),
          agentStartTimeoutMs: 100000,
        }});
        queue.enqueue({{ subject: "old", body: "report" }});
        queue.reset();
        await new Promise((resolve) => setImmediate(resolve));
        console.log(JSON.stringify({{ sent: sent.length, pending: queue.pendingCount }}));
        ''')
    assert payload == {"sent": 0, "pending": 0}


def test_follow_up_queue_waits_for_matching_start_and_settle() -> None:
    module = (SRC / "follow-up-queue.ts").as_uri()
    payload = run_node(f'''\
        import {{ FollowUpQueue }} from "{module}";
        const sent = [];
        const queue = new FollowUpQueue({{
          isIdle: () => true,
          dispatch: (content) => sent.push(content),
          agentStartTimeoutMs: 100000,
        }});
        queue.enqueue({{ subject: "A", body: "first" }});
        await new Promise((resolve) => setTimeout(resolve, 10));
        queue.enqueue({{ subject: "B", body: "second" }});
        queue.onAgentSettled();
        await new Promise((resolve) => setTimeout(resolve, 10));
        const beforeStart = sent.length;
        queue.onBeforeAgentStart("Teammate update: A\\nfirst");
        queue.onAgentStart();
        queue.onAgentSettled();
        await new Promise((resolve) => setTimeout(resolve, 10));
        const result = {{ beforeStart, sent }};
        queue.reset();
        console.log(JSON.stringify(result));
        ''')
    assert payload == {"beforeStart": 1, "sent": ["Teammate update: A\nfirst", "Teammate update: B\nsecond"]}


def test_follow_up_queue_removes_protocol_and_run_identifiers() -> None:
    module = (SRC / "follow-up-queue.ts").as_uri()
    payload = run_node(f'''\
        import {{ FollowUpQueue }} from "{module}";
        const sent = [];
        const queue = new FollowUpQueue({{ isIdle: () => true, dispatch: (content) => sent.push(content) }});
        queue.enqueue({{ subject: "Node completed", body: "result", runId: "run_6" }});
        await new Promise((resolve) => setTimeout(resolve, 10));
        console.log(JSON.stringify(sent));
        ''')
    assert payload == ["Teammate update: Node completed\\nresult"]


def test_dirty_state_tracking_and_session_worker_cap() -> None:
    state_module = (SRC / "state.ts").as_uri()
    machine = source("run-machine.ts")
    payload = run_node(
        f'''
        import {{ createRun, resetState, isStateDirty, clearStateDirty }} from "{state_module}";
        resetState();
        const afterReset = isStateDirty();
        clearStateDirty();
        createRun({{ cwd: "/tmp", concurrency: 2, worktree: false, summarize: false,
          nodes: [{{ id: "a", agent: "worker", prompt: "task", paths: ["src"], access: "read", dependsOn: [] }}] }});
        console.log(JSON.stringify({{ afterReset, afterCreate: isStateDirty() }}));
        '''
    )
    assert payload == {"afterReset": True, "afterCreate": True}
    assert "export const MAX_SESSION_WORKERS = 8" in machine
    assert "isStateDirty()" in machine and "clearStateDirty()" in machine
    assert "Keep the dirty bit set" in machine


def test_long_task_temp_directory_is_cleaned_on_worker_exit() -> None:
    spawner = source("spawner.ts")
    assert "fs.mkdtempSync(path.join(os.tmpdir(), \"teammate-\"))" in spawner
    assert "const cleanupTempDir = () =>" in spawner
    assert "fs.rmSync(tempDir, { recursive: true, force: true })" in spawner
    assert "cleanupTempDir();" in spawner
    assert "let taskText = `Task: ${options.description}`;" in spawner
    assert "taskText.length > TASK_ARG_LIMIT" in spawner
    assert "return setupError(error);" in spawner


def test_background_runs_start_the_live_poll() -> None:
    machine = source("run-machine.ts")
    assert "export function ensureLivePoll()" in machine
    assert "ensureLivePoll();" in machine
    assert "applyWorkerEvents();" in machine
    assert "applyWorkerEvents();" in machine


def test_leader_guidance_is_static_and_excludes_live_runs() -> None:
    ext = source("guidance.ts")
    assert "formatAgentGuidance" in ext
    assert "buildTeamLeaderGuidance" in ext
    assert "Active background runs" not in ext
    assert "listActiveRuns" not in ext
    assert "run.id" not in ext
    assert "teammate_run" in ext
    assert "teammate_cancel" in ext
    assert "teammate_retry" in ext


def test_end_to_end_worker_message_flow_is_leader_only() -> None:
    state_module = (SRC / "state.ts").as_uri()
    statefile_module = (SRC / "statefile.ts").as_uri()
    payload = run_node(
        f'''\
        import * as fs from "node:fs";
        import * as path from "node:path";
        import * as os from "node:os";
        import {{ createRun, resetState, getState, setNodeSpawnInfo, receiveWorkerMessage, updateNodeStatus, nodeIsReady, settleRun }} from "{state_module}";
        import {{ appendWorkerEvent, readWorkerEvents, workerOutboxPath }} from "{statefile_module}";
        resetState();
        const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "test-agent-teams-e2e-"));
        const stateFile = path.join(tmpDir, "state.json");
        const created = createRun({{ cwd: tmpDir, concurrency: 2, worktree: false, background: true, summarize: false,
          nodes: [
            {{ id: "node_a", agent: "worker", prompt: "design", paths: ["src"], access: "read", dependsOn: [] }},
            {{ id: "node_b", agent: "worker", prompt: "implement", paths: ["src"], access: "read", dependsOn: ["node_a"] }}
          ] }});
        const run = created.run;
        const spawnId = "spawn-a-1";
        setNodeSpawnInfo(run.id, "node_a", {{ spawnId, pid: 1001, status: "running", startedAt: Date.now(), isolation: "none" }});
        const outbox = workerOutboxPath(stateFile, run.nodes.node_a.workerKey, spawnId);
        appendWorkerEvent(outbox, {{ id: "evt-a-1", type: "message", worker: run.nodes.node_a.workerKey, spawnId, subject: "Artifact", body: "Architecture", status: "completed" }});
        const {{ events }} = readWorkerEvents(outbox, 0);
        for (const event of events) {{
          if (event.type !== "message") continue;
          receiveWorkerMessage(event);
          updateNodeStatus(run.id, "node_a", event.status, event.body, undefined);
        }}
        const ready = nodeIsReady(run, run.nodes.node_b);
        updateNodeStatus(run.id, "node_b", "completed", "Implementation", undefined);
        const settled = settleRun(run.id);
        console.log(JSON.stringify({{ messages: getState().leaderMailbox.map((m) => m.subject).join(","), ready, settled }}));
        '''
    )
    assert payload == {"messages": "Artifact", "ready": True, "settled": "completed"}

