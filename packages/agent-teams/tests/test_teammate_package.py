from __future__ import annotations

import json
import subprocess
import textwrap
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
SRC = PACKAGE / "src"

LEADER_TOOLS = {
    "teammate_run",
    "teammate_cancel",
    "teammate_retry",
    "teammate_message",
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
    assert manifest["pi"] == {"extensions": ["./src/index.ts"]}
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
        "A run is a single-call DAG dispatch",
        "Dispatch a single task in one call",
        "Dispatch a dependency graph in one call",
        "Downstream nodes auto-start after their dependencies complete",
        "Concurrency bounds simultaneous workers",
        "Teammates run in the background by default",
        "A long inline run detaches to background after the gather cap",
        "A run-level timeout fails the whole run",
        "Cancel one node while the rest of the run continues",
        "Retry failed and cancelled nodes without re-running completed ones",
        "A worker messages the team leader or a peer in the same run",
        "Completing a node injects its result into downstream prompts",
        "Leader replies and broadcasts land in the worker's inbox",
        "Messages carry no read receipts",
        "Multi-node runs synthesize a final summary by default",
        "Read nodes with overlapping paths may run concurrently",
        "Write nodes with overlapping paths are blocked without worktree isolation",
        "Worktree isolation allows parallel write experiments",
        "A failed node fails the run and downstream nodes are not started",
        "Reject malformed task graphs",
        "Reject ambiguous path ownership",
        "Run lifecycle is explicit",
        "No model status polling tool exists",
        "Run completion is delivered automatically without a wait tool",
        "follow-up includes the full final deliverable submitted by the worker",
        "single-node run delivers its result directly in the follow-up",
        "Cancel a run stops its running nodes",
        "Runs do not survive session restarts",
        "Messaging is capability-bound",
        "A worker delivers its outcome via teammate_message",
        "Intermediate worker communication does not interrupt the main session",
        "The harness delivers one canonical terminal result per node",
        "Workers cannot access leader tools",
        "Worker process outcomes are authoritative",
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
    ext = source("index.ts")
    assert "const sgrWheel = /^\\x1b\\[<(\\d+);(\\d+);(\\d+)[Mm]$/" in ext
    assert "(button & 64) !== 0" in ext
    assert "direction === 0" in ext and "direction === 1" in ext


def test_leader_tool_surface_is_exact() -> None:
    ext = source("index.ts")
    for tool in LEADER_TOOLS:
        assert f'name: "{tool}"' in ext
    for tool in REMOVED_TOOLS | LEGACY_TOOLS:
        assert f'name: "{tool}"' not in ext


def test_worker_surface_is_capability_bound() -> None:
    ext = source("index.ts")
    worker_section = ext[ext.index("function registerWorkerCapabilities"):ext.index("// ── Team UI")]
    for tool in WORKER_TOOLS:
        assert f'name: "{tool}"' in worker_section
    for tool in LEADER_TOOLS - {"teammate_message"}:
        assert f'name: "{tool}"' not in worker_section
    assert "if (workerOutboxBinding())" in ext
    assert "registerWorkerCapabilities(pi);" in ext
    assert "return;" in ext[ext.index("if (workerOutboxBinding())"):ext.index("// ── Session lifecycle")]


def test_idle_widget_stays_hidden_until_a_teammate_is_running() -> None:
    ext = source("index.ts")
    assert "if (running.length === 0) return [];" in ext
    assert "Team idle" not in ext
    assert "runningTeammateLabel" in ext
    assert "runningNodeLabel" not in ext


def test_widget_rows_align_with_native_loader_and_show_live_activity() -> None:
    ext = source("index.ts")
    spawner = source("spawner.ts")
    types = source("types.ts")
    # Leading space before each widget row so spinner columns align with pi's
    # native " ⠋ Working..." loader row.
    assert '` ${fit(`${bold(fg(color, node.id))}' in ext
    assert '` ${fit(fg("dim", "/teammate — open console"))}' in ext
    # Live activity: current tool first, then reasoning, then text.
    assert "node.spawn?.activeTool" in ext and "liveThinking" in ext
    assert "liveThinking?: string" in types
    # The JSON stream parser tracks tool calls via message_update subtypes
    # (toolcall_start/delta/end) — the obsolete tool_execution_* events do not
    # exist in pi's JSON mode output.
    assert '"toolcall_start"' in spawner and '"toolcall_delta"' in spawner and '"toolcall_end"' in spawner
    assert "tool_execution_start" not in spawner
    assert "tool_execution_end" not in spawner
    # toolcall_end keeps the richer delta-derived label ("bash: echo hello")
    # instead of overwriting it with the bare tool name.
    assert "if (tc?.name && !state.activeTool)" in spawner
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
    assert "timeoutMs" in types
    assert "nodeId: Type.Optional" in types
    assert "markRead" not in types
    assert "workerKey" in types
    assert "deadlineAt" in types
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


def test_workers_can_message_same_run_peers() -> None:
    ext = source("index.ts")
    state = source("state.ts")
    assert "resolveWorkerRecipientFromRuns" in state
    assert "handoffNodeResult" not in state
    assert "=== UPSTREAM HANDOFF ===" in ext
    assert "Workers may only message agent" not in ext
    # Peer messages are recorded for the transcript, not delivered into a peer mailbox.
    assert "sent transcript" in state
    assert "sentMessages" in source("types.ts")


def test_run_timeout_and_retry_state_machine() -> None:
    module = (SRC / "state.ts").as_uri()
    payload = run_node(
        f'''\
        import {{ createRun, resetState, failRunTimeout, retryRun, setNodeSpawnInfo, getRun }} from "{module}";
        resetState();
        const created = createRun({{ cwd: "/tmp", concurrency: 1, worktree: false, background: false, summarize: false, timeoutMs: 5000,
          nodes: [
            {{ id: "a", agent: "worker", prompt: "", paths: ["x"], access: "read", dependsOn: [] }},
            {{ id: "b", agent: "worker", prompt: "", paths: ["y"], access: "read", dependsOn: ["a"] }},
          ] }});
        const run = created.run;
        const hasDeadline = Boolean(run.deadlineAt && run.timeoutMs === 5000);
        setNodeSpawnInfo(run.id, "a", {{ runId: "s1", pid: 1, status: "running", startedAt: 1, isolation: "none" }});
        const failed = failRunTimeout(run.id, "Run timed out after 5s.");
        const afterFail = {{ status: run.status, running: failed.runningNodeIds.join(","), b: run.nodes.b.status, error: run.errorMessage }};
        const retried = retryRun(run.id);
        const afterRetry = {{ status: run.status, reset: retried.reset.join(","), a: run.nodes.a.status, b: run.nodes.b.status, notified: run.completionNotified }};
        console.log(JSON.stringify({{ hasDeadline, afterFail, afterRetry }}));
        '''
    )
    assert payload["hasDeadline"] is True
    assert payload["afterFail"] == {"status": "failed", "running": "a", "b": "cancelled", "error": "Run timed out after 5s."}
    assert payload["afterRetry"] == {"status": "running", "reset": "a,b", "a": "pending", "b": "pending", "notified": False}


def test_retry_rearms_deadline_propagates_and_validates() -> None:
    module = (SRC / "state.ts").as_uri()
    payload = run_node(
        f'''\
        import {{ createRun, resetState, retryRun, updateNodeStatus, cancelBlockedDependents, settleRun }} from "{module}";
        resetState();
        const created = createRun({{ cwd: "/tmp", concurrency: 1, worktree: false, background: false, summarize: false, timeoutMs: 60000,
          nodes: [
            {{ id: "a", agent: "worker", prompt: "", paths: ["x"], access: "read", dependsOn: [] }},
            {{ id: "b", agent: "worker", prompt: "", paths: ["y"], access: "read", dependsOn: ["a"] }},
            {{ id: "c", agent: "worker", prompt: "", paths: ["z"], access: "read", dependsOn: ["b"] }},
          ] }});
        const run = created.run;
        // a fails -> finalizeNode cancels b and c as its dependents and settles the run.
        updateNodeStatus(run.id, "a", "failed", undefined, "boom");
        cancelBlockedDependents(run.id, "a");
        settleRun(run.id);
        // Unknown node ids are validated before any retry is attempted.
        const unknown = retryRun(run.id, ["ghost"]);
        // Simulate an expired run cap, then verify retry re-arms it to the future.
        run.deadlineAt = Date.now() - 1000;
        const oldDeadline = run.deadlineAt;
        const retried = retryRun(run.id, ["a"]);
        const rearmed = Boolean(run.deadlineAt && run.deadlineAt > Date.now());
        const completed = retryRun(run.id, ["c"]);
        console.log(JSON.stringify({{
          ok: retried.ok, reset: retried.reset.join(","), rearmed,
          a: run.nodes.a.status, b: run.nodes.b.status, c: run.nodes.c.status,
          unknownOk: unknown.ok, unknownError: unknown.ok ? "" : unknown.error,
          completedOk: completed.ok,
        }}));
        '''
    )
    assert payload["ok"] is True
    assert payload["reset"] == "a,b,c"  # b and c propagated as cancelled dependents of a
    assert payload["rearmed"] is True
    assert payload["a"] == "pending" and payload["b"] == "pending" and payload["c"] == "pending"
    assert payload["unknownOk"] is False and "ghost" in payload["unknownError"]
    assert payload["completedOk"] is False


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
        setNodeSpawnInfo(run.id, "b", {{ runId: "s1", pid: 1, status: "running", startedAt: 1, isolation: "none" }});
        setNodeSpawnInfo(run.id, "c", {{ runId: "s2", pid: 2, status: "running", startedAt: 1, isolation: "none" }});
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


def test_worker_peer_message_is_recorded_not_delivered() -> None:
    module = (SRC / "state.ts").as_uri()
    payload = run_node(
        f'''\
        import {{ createRun, resetState, receiveWorkerMessage, getState }} from "{module}";
        resetState();
        const created = createRun({{ cwd: "/tmp", concurrency: 2, worktree: false, background: false, summarize: false,
          nodes: [
            {{ id: "a", agent: "worker", prompt: "", paths: ["x"], access: "read", dependsOn: [] }},
            {{ id: "b", agent: "reviewer", prompt: "", paths: ["y"], access: "read", dependsOn: ["a"] }},
          ] }});
        const run = created.run;
        receiveWorkerMessage({{
          id: "evt-1", worker: run.nodes.a.workerKey, runId: "s1", type: "message",
          to: run.nodes.b.workerKey, subject: "Sync", body: "design ready", taskId: run.id,
        }});
        const peerInbox = run.nodes.b.inboxMessages;
        const sentA = run.nodes.a.sentMessages.map((m) => m.subject).join(",");
        const leaderMessages = getState().leaderMailbox.length;
        console.log(JSON.stringify({{ peerInboxCount: peerInbox.length, sentA, leaderMessages }}));
        '''
    )
    # A peer message is recorded in the sender's sent transcript (console trace)
    # but must not land in the peer's worker inbox — DAG upstream results are
    # injected into downstream prompts at spawn instead.
    assert payload == {"peerInboxCount": 0, "sentA": "Sync", "leaderMessages": 0}


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
        setNodeSpawnInfo(run.id, "w1", {{ runId: "s1", pid: 1, status: "running", startedAt: 1, isolation: "none" }});
        const writeOverlap = findSharedWorkspaceWriteConflict(run.id, "w2")?.id ?? null;
        const readOverlap = findSharedWorkspaceWriteConflict(run.id, "r")?.id ?? null;
        setNodeSpawnInfo(run.id, "w2", {{ runId: "s2", pid: 2, status: "running", startedAt: 1, isolation: "worktree" }});
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
        setNodeSpawnInfo(run.id, "a", {{ runId: "s1", pid: 1, status: "running", startedAt: 1, isolation: "none" }});
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


def test_mailbox_is_best_effort_without_receipts() -> None:
    module = (SRC / "state.ts").as_uri()
    payload = run_node(
        f'''\
        import {{ createRun, resetState, sendMessage, receiveWorkerMessage, getState }} from "{module}";
        resetState();
        const created = createRun({{ cwd: "/tmp", concurrency: 1, worktree: false, background: false,
          nodes: [{{ id: "a", agent: "worker", prompt: "", paths: ["x"], access: "read", dependsOn: [] }}] }});
        const run = created.run;
        const key = run.nodes.a.workerKey;
        // Leader → worker reply lands in the worker's inbox (best-effort read).
        sendMessage({{ from: "team-leader", to: key, subject: "hi", body: "hello" }});
        // Worker → leader message lands in the leader inbox and the sender's transcript.
        const event = {{
          id: "evt-1", worker: key, runId: "s1", type: "message", to: "team-leader", subject: "plan", body: "p",
        }};
        const delivered = receiveWorkerMessage(event);
        const duplicate = receiveWorkerMessage(event);
        const nodeInbox = run.nodes.a.inboxMessages;
        const leaderMessages = getState().leaderMailbox;
        const sentTranscript = run.nodes.a.sentMessages.map((m) => m.subject).join(",");
        console.log(JSON.stringify({{
          delivered,
          nodeMessages: nodeInbox.map((m) => m.subject).join(","),
          leaderMessages: leaderMessages.map((m) => m.subject).join(","),
          sentTranscript,
          duplicate,
        }}));
        '''
    )
    assert payload == {"delivered": True, "nodeMessages": "hi", "leaderMessages": "plan", "sentTranscript": "plan", "duplicate": False}


def test_worker_spawn_is_nonblocking_and_identity_bound() -> None:
    ext = source("index.ts")
    spawner = source("spawner.ts")
    assert "spawnPiWorkerBlocking" not in ext
    assert "spawnPiWorkerBlocking" not in spawner
    # Worker knows its mailbox key and the push-only receive path (read state.json).
    assert "workerKey: node.workerKey" in ext
    assert "Your worker key:" in spawner
    assert "inboxMessages" in spawner
    assert "watch and process the mailbox" not in spawner
    # Worker identity is the node key (runId:nodeId) plus a fresh spawn id.
    assert "PI_TEAMMATE_WORKER_NAME: workerKey" in ext
    assert "PI_TEAMMATE_TASK_ID: node.id" in ext
    assert "PI_TEAMMATE_RUN_ID: spawnId" in ext
    assert 'const spawnId = randomUUID()' in ext
    # Stale close events from an older spawn cannot affect a newer spawn.
    assert 'getNode(runId, nodeId)?.spawn?.runId !== spawnId' in ext


def test_run_dispatch_is_single_call_with_scheduler() -> None:
    ext = source("index.ts")
    assert 'name: "teammate_run"' in ext
    assert "scheduleRun(run.id, ctx)" in ext
    assert "readyPendingNodes(run)" in ext
    assert "run.concurrency - runningNodeCount(runId)" in ext
    assert "findSharedWorkspaceWriteConflict(runId, node.id)" in ext
    assert "startNode(runId, node.id, ctx)" in ext
    assert "onRunSettled(runId, ctx)" in ext
    assert "markLeaderMessagesReadForRun" not in ext
    assert "readMailbox" not in ext
    # Foreground gather claims completion delivery so a settled run does not
    # also emit a follow-up; background runs notify once via completionNotified.
    assert "run.background && !run.completionNotified" in ext
    assert "markRunCompletionDelivered(run.id)" in ext    # Teammates run in the background by default.
    assert "background: params.background ?? true" in ext
    # Console detail includes the full sent message flow (push-only transcript).
    assert "sent messages" in ext
    assert "node.sentMessages" in ext
    # Foreground gather blocks; background returns immediately.
    assert "if (run.background)" in ext


def test_tool_returns_are_compact_and_summary_is_synthesized() -> None:
    ext = source("index.ts")
    state = source("state.ts")
    types = source("types.ts")
    # Tool returns (run/follow-up) use the compact summary; the full
    # per-node transcript stays in the /teammate console.
    assert "function buildRunSummary" in ext
    assert "buildRunResultSummary" not in ext
    assert "Console: /teammate" in ext
    assert "text: buildRunSummary(run.id)" in ext
    # No truncation heuristics: per-node rows are status-only unless a
    # synthesized __summary node produced a real summary.
    assert "nodeHeadline" not in ext
    assert "SUMMARY_NODE_ID" in ext
    assert "summarize" in types
    assert "summaryAgent" in types
    assert "settledRun.summary = nodeNow?.result" in ext
    assert "if (run.summary)" in ext
    assert "else if (nodes.length === 1)" in ext
    assert "node.result?.trim() || node.errorMessage?.trim()" in ext
    # No wait/status polling tool: delivery is the automatic completion follow-up; the
    # foreground gather loop is the only inline blocking path.
    assert 'name: "teammate_wait"' not in ext
    assert 'name: "teammate_status"' not in ext
    assert "await sleep(" in ext


def test_guidance_is_run_centric_without_redundant_tool_list() -> None:
    ext = source("index.ts")
    agents = source("agents.ts")
    assert "formatAgentGuidance" in agents
    assert "buildTeamLeaderGuidance" in ext
    assert "before_agent_start" in ext
    assert "teammate_run" in ext
    assert 'name: "teammate_status"' not in ext
    assert "teammate_wait" not in ext
    assert "teammate_cancel" in ext
    assert ".pi/agents" in ext
    assert "~/.pi/agent/agents" in ext
    assert "dependsOn" in ext
    assert "teammate_register" not in ext
    assert "teammate_inbox" not in ext
    assert "teammate_message" in ext


def test_no_runtime_identity_registry_remains() -> None:
    state = source("state.ts")
    ext = source("index.ts")
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
          workerKey: "run_1:task_1",
          stateFile: "/tmp/state.json",
          outboxFile: "/tmp/outbox.jsonl",
          timeoutSec: 120,
        }});
        console.log(JSON.stringify({{
          hasTask: prompt.includes("task_1"),
          hasTimeoutCap: prompt.includes("120s"),
          hasDirectScope: prompt.includes("Work directly on your assigned scope"),
          hasDeliverInstruction: prompt.includes('status="completed"'),
        }}));
        '''
    )
    assert payload == {
        "hasTask": True,
        "hasTimeoutCap": True,
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
    ext = source("index.ts")
    types = source("types.ts")
    assert 'status?: "in_progress" | "completed" | "failed"' in types
    assert 'updateNodeStatus(run.id, node.id, "completed", event.body, undefined)' in ext
    assert 'updateNodeStatus(run.id, node.id, "failed", undefined, event.body)' in ext
    assert 'name: "teammate_report"' not in ext


def test_end_to_end_worker_message_flow_and_peer_communication() -> None:
    state_module = (SRC / "state.ts").as_uri()
    statefile_module = (SRC / "statefile.ts").as_uri()
    payload = run_node(
        f'''
        import * as fs from "node:fs";
        import * as path from "node:path";
        import * as os from "node:os";
        import {{
          createRun, resetState, updateNodeStatus, getNode, getState, setNodeSpawnInfo,
          nodeIsReady, settleRun, resolveWorkerRecipientFromRuns, receiveWorkerMessage
        }} from "{state_module}";
        import {{
          appendWorkerEvent, readWorkerEvents, workerOutboxPath, writeStateFile
        }} from "{statefile_module}";

        resetState();
        const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "test-agent-teams-e2e-"));
        const stateFile = path.join(tmpDir, "state.json");
        writeStateFile(stateFile, getState());

        const created = createRun({{
          cwd: tmpDir,
          concurrency: 2,
          worktree: false,
          background: true,
          summarize: false,
          nodes: [
            {{ id: "node_a", agent: "worker", prompt: "design system", paths: ["src"], access: "read", dependsOn: [] }},
            {{ id: "node_b", agent: "worker", prompt: "implement system", paths: ["src"], access: "read", dependsOn: ["node_a"] }}
          ]
        }});
        const run = created.run;
        const spawnIdA = "spawn-a-1";
        setNodeSpawnInfo(run.id, "node_a", {{
          runId: spawnIdA, pid: 1001, status: "running", startedAt: Date.now(), isolation: "none"
        }});
        writeStateFile(stateFile, getState());

        const outboxA = workerOutboxPath(stateFile, run.nodes.node_a.workerKey, spawnIdA);
        // Node A sends progress message to leader
        appendWorkerEvent(outboxA, {{
          id: "evt-a-1", type: "message", worker: run.nodes.node_a.workerKey, runId: spawnIdA,
          to: "team-leader", subject: "Plan", body: "Designing architecture", status: "in_progress", taskId: "node_a"
        }});
        // Node A delivers final deliverable with completed status
        appendWorkerEvent(outboxA, {{
          id: "evt-a-2", type: "message", worker: run.nodes.node_a.workerKey, runId: spawnIdA,
          to: "team-leader", subject: "Artifact A", body: "Architecture document V1", status: "completed", taskId: "node_a"
        }});

        function applyEvents(sf) {{
          const state = getState();
          for (const r of Object.values(state.runs)) {{
            for (const node of Object.values(r.nodes)) {{
              const spawn = node.spawn;
              if (!spawn || spawn.status !== "running") continue;
              const sId = spawn.runId;
              const outboxKey = `${{node.workerKey}}:${{sId}}`;
              const ob = workerOutboxPath(sf, node.workerKey, sId);
              const {{ events, nextOffset }} = readWorkerEvents(ob, state.workerEventOffsets[outboxKey] ?? 0);
              state.workerEventOffsets[outboxKey] = nextOffset;
              for (const event of events) {{
                if (state.workerEventIds[`${{sId}}:${{event.id}}`]) continue;
                if (event.worker !== node.workerKey || event.runId !== sId) continue;
                if (event.type === "message") {{
                  const recipient = resolveWorkerRecipientFromRuns(state.runs, node.workerKey, event.to);
                  if (!recipient.ok) continue;
                  state.workerEventIds[`${{sId}}:${{event.id}}`] = sId;
                  receiveWorkerMessage({{
                    id: event.id, worker: node.workerKey, runId: sId, type: "message",
                    to: recipient.to, subject: event.subject, body: event.body,
                    taskId: event.taskId === node.id ? r.id : undefined,
                  }});
                  if (event.status && !["completed", "failed", "cancelled"].includes(node.status)) {{
                    if (event.status === "completed") {{
                      updateNodeStatus(r.id, node.id, "completed", event.body, undefined);
                    }} else if (event.status === "failed") {{
                      updateNodeStatus(r.id, node.id, "failed", undefined, event.body);
                    }}
                  }}
                }}
              }}
            }}
          }}
        }}

        applyEvents(stateFile);
        const nodeAAfter = getNode(run.id, "node_a");
        const nodeBReady = nodeIsReady(run, run.nodes.node_b);
        const leaderMessagesAfterA = getState().leaderMailbox.map((m) => m.subject).join(",");
        // No worker-to-worker mailbox handoff: B's inbox is untouched.
        const mailboxB = run.nodes.node_b.inboxMessages;

        // Now Node B starts and sends a peer message to Node A (transcript-only)
        // and its final deliverable to the leader.
        const spawnIdB = "spawn-b-1";
        setNodeSpawnInfo(run.id, "node_b", {{
          runId: spawnIdB, pid: 1002, status: "running", startedAt: Date.now(), isolation: "none"
        }});
        writeStateFile(stateFile, getState());
        const outboxB = workerOutboxPath(stateFile, run.nodes.node_b.workerKey, spawnIdB);
        appendWorkerEvent(outboxB, {{
          id: "evt-b-1", type: "message", worker: run.nodes.node_b.workerKey, runId: spawnIdB,
          to: "node_a", subject: "Sync", body: "Consuming your architecture doc", taskId: "node_b"
        }});
        appendWorkerEvent(outboxB, {{
          id: "evt-b-2", type: "message", worker: run.nodes.node_b.workerKey, runId: spawnIdB,
          to: "team-leader", subject: "Artifact B", body: "Implementation finished", status: "completed", taskId: "node_b"
        }});
        applyEvents(stateFile);

        const mailboxA = run.nodes.node_a.inboxMessages;
        const sentB = run.nodes.node_b.sentMessages.map((m) => m.subject).join(",");
        const sentA = run.nodes.node_a.sentMessages.map((m) => m.subject).join(",");
        const nodeBAfter = getNode(run.id, "node_b");
        const finalSettled = settleRun(run.id);

        console.log(JSON.stringify({{
          nodeAStatus: nodeAAfter.status,
          nodeAResult: nodeAAfter.result,
          nodeBReady,
          nodeBStatus: nodeBAfter.status,
          nodeBResult: nodeBAfter.result,
          leaderMessagesAfterA,
          mailboxBCount: mailboxB.length,
          peerDeliveredToA: mailboxA.length,
          sentA,
          sentB,
          leaderMessagesTotal: getState().leaderMailbox.map((m) => m.subject).join(","),
          finalSettled,
        }}));
        '''
    )
    assert payload == {
        "nodeAStatus": "completed",
        "nodeAResult": "Architecture document V1",
        "nodeBReady": True,
        "nodeBStatus": "completed",
        "nodeBResult": "Implementation finished",
        "leaderMessagesAfterA": "Plan,Artifact A",
        "mailboxBCount": 0,
        "peerDeliveredToA": 0,
        "sentA": "Plan,Artifact A",
        "sentB": "Sync,Artifact B",
        "leaderMessagesTotal": "Plan,Artifact A,Artifact B",
        "finalSettled": "completed",
    }

