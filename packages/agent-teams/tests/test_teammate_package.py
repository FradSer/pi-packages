from __future__ import annotations

import json
import subprocess
import textwrap
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
SRC = PACKAGE / "src"

LEADER_TOOLS = {
    "teammate_run",
    "teammate_status",
    "teammate_wait",
    "teammate_cancel",
    "teammate_retry",
    "teammate_cleanup",
    "teammate_message",
    "teammate_inbox",
}
WORKER_TOOLS = {"teammate_message", "teammate_inbox", "teammate_report"}
REMOVED_TOOLS = {
    "teammate_register",
    "teammate_list",
    "teammate_configure",
    "teammate_remove",
    "teammate_create_task",
    "teammate_list_tasks",
    "teammate_start_task",
    "teammate_cancel_task",
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
    feature = (PACKAGE / "features" / "teammate-status.feature").read_text(encoding="utf-8")
    for phrase in (
        "Agents are declarative Markdown files",
        "Discover agents from bundled, user, and project scopes",
        "Project agents override user and bundled agents with the same name",
        "Agent frontmatter declares tools and model; the body is the role prompt",
        "Agent descriptions are the routing contract",
        "An unknown agent name fails the dispatch",
        "A run is a single-call DAG dispatch",
        "Dispatch a single task in one call",
        "Dispatch a dependency graph in one call",
        "Downstream nodes auto-start after their dependencies complete",
        "Concurrency bounds simultaneous workers",
        "Foreground dispatch gathers results; background dispatch returns immediately",
        "A long foreground run detaches to background after the foreground cap",
        "A run-level timeout fails the whole run",
        "Cancel one node while the rest of the run continues",
        "Retry failed and cancelled nodes without re-running completed ones",
        "A worker messages the main session only",
        "Read nodes with overlapping paths may run concurrently",
        "Write nodes with overlapping paths are blocked without worktree isolation",
        "Worktree isolation allows parallel write experiments",
        "A failed node fails the run and downstream nodes are not started",
        "Reject malformed task graphs",
        "Reject ambiguous path ownership",
        "Run lifecycle is explicit",
        "Status lists agents, runs, and node detail",
        "Wait is the explicit gather barrier for runs",
        "Cancel a run stops its running nodes",
        "Cleanup prunes terminal runs",
        "Runs do not survive session restarts",
        "Messaging is capability-bound",
        "A worker messages the main session only",
        "Inbox reads are scoped to the caller",
        "A worker reports only its bound node",
        "Intermediate worker communication stays in the mailbox",
        "The harness delivers one canonical terminal result per node",
        "Workers cannot access leader tools",
        "Worker process outcomes are authoritative",
        "A normal worker exit completes its node",
        "An abnormal worker exit fails its node",
        "Completed run metadata is compacted safely",
        "Invalid tool operations surface as Pi failures",
        "Cancelled or timed-out waits surface as tool failures",
        "Legitimate empty and terminal data remains a normal result",
        "Console is a user interface, not an agent tool substitute",
        "Console shows live node activity without intercepting global input",
        "Detail scrolling preserves every wrapped display line",
    ):
        assert phrase in feature


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
    for tool in LEADER_TOOLS - {"teammate_message", "teammate_inbox"}:
        assert f'name: "{tool}"' not in worker_section
    assert "if (workerOutboxBinding())" in ext
    assert "registerWorkerCapabilities(pi);" in ext
    assert "return;" in ext[ext.index("if (workerOutboxBinding())"):ext.index("// ── Session lifecycle")]


def test_types_express_run_centric_surface() -> None:
    types = source("types.ts")
    for schema in (
        "TeammateRunParams",
        "TeammateStatusParams",
        "TeammateWaitParams",
        "TeammateCancelParams",
        "TeammateRetryParams",
        "EmptyParams",
        "TeammateMessageParams",
        "TeammateInboxParams",
        "TeammateReportParams",
        "RunTaskSpec",
    ):
        assert f"export const {schema}" in types
    assert "foregroundTimeoutMs" in types
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


def test_workers_cannot_message_peers() -> None:
    ext = source("index.ts")
    state = source("state.ts")
    assert "Workers may only message agent (the main session), not peers." in ext
    assert "mailboxExists" not in state
    assert "mailboxExists" not in ext


def test_run_timeout_and_retry_state_machine() -> None:
    module = (SRC / "state.ts").as_uri()
    payload = run_node(
        f'''\
        import {{ createRun, resetState, failRunTimeout, retryRun, setNodeSpawnInfo, getRun }} from "{module}";
        resetState();
        const created = createRun({{ cwd: "/tmp", concurrency: 1, worktree: false, background: false, timeoutMs: 5000,
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
        const created = createRun({{ cwd: "/tmp", concurrency: 1, worktree: false, background: false, timeoutMs: 60000,
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
        const created = createRun({{ cwd: "/tmp", concurrency: 2, worktree: false, background: false, summarize: true,
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


def test_run_creation_rejects_malformed_graphs() -> None:
    module = (SRC / "state.ts").as_uri()
    payload = run_node(
        f'''\
        import {{ createRun, resetState }} from "{module}";
        resetState();
        const node = (id, dependsOn = []) => ({{
          id, agent: "worker", prompt: "do it", paths: ["packages/a"], access: "read", dependsOn,
        }});
        const dup = createRun({{ cwd: "/tmp", concurrency: 2, worktree: false, background: false,
          nodes: [node("a"), node("a")] }});
        const unknownDep = createRun({{ cwd: "/tmp", concurrency: 2, worktree: false, background: false,
          nodes: [node("a", ["ghost"])] }});
        const cycle = createRun({{ cwd: "/tmp", concurrency: 2, worktree: false, background: false,
          nodes: [node("a", ["b"]), node("b", ["a"])] }});
        const badPath = createRun({{ cwd: "/tmp", concurrency: 2, worktree: false, background: false,
          nodes: [{{ ...node("a"), paths: ["/etc/passwd"] }}] }});
        const ok = createRun({{ cwd: "/tmp", concurrency: 2, worktree: false, background: false,
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
        const created = createRun({{ cwd: "/tmp", concurrency: 1, worktree: false, background: false,
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
        import {{ createRun, resetState, sendMessage, readMailbox, receiveWorkerMessage }} from "{module}";
        resetState();
        const created = createRun({{ cwd: "/tmp", concurrency: 1, worktree: false, background: false,
          nodes: [{{ id: "a", agent: "worker", prompt: "", paths: ["x"], access: "read", dependsOn: [] }}] }});
        const run = created.run;
        const key = run.nodes.a.workerKey;
        sendMessage({{ from: "agent", to: key, subject: "hi", body: "hello" }});
        const unread = readMailbox(key, {{ unreadOnly: true }}).length;
        const marked = readMailbox(key, {{ unreadOnly: false, markRead: true }}).map((m) => m.subject);
        const delivered = receiveWorkerMessage({{
          id: "evt-1", worker: key, runId: "s1", type: "message", to: "agent", subject: "plan", body: "p",
        }});
        const agentUnread = readMailbox("agent", {{ unreadOnly: true }}).length;
        console.log(JSON.stringify({{ unread, marked, delivered, agentUnread }}));
        '''
    )
    assert payload == {"unread": 1, "marked": ["hi"], "delivered": True, "agentUnread": 1}


def test_worker_spawn_is_nonblocking_and_identity_bound() -> None:
    ext = source("index.ts")
    spawner = source("spawner.ts")
    assert "spawnPiWorkerBlocking" not in ext
    assert "spawnPiWorkerBlocking" not in spawner
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
    assert "markLeaderMessagesReadForRun(run.id)" in ext
    # Wait claims completion delivery up front (and revokes on timeout/abort)
    # so a settled run does not also emit a follow-up.
    assert "for (const id of runIds) markRunCompletionDelivered(id)" in ext
    assert "clearRunCompletionClaim(id)" in ext
    assert "run.background && !run.completionNotified" in ext
    assert "markRunCompletionDelivered(run.id)" in ext
    # Foreground gather blocks; background returns immediately.
    assert "if (run.background)" in ext


def test_tool_returns_are_compact_and_detail_lives_in_status_inbox() -> None:
    ext = source("index.ts")
    state = source("state.ts")
    types = source("types.ts")
    # Tool returns (run/wait/follow-up) use the compact summary; the full
    # per-node transcript stays in teammate_status runId and teammate_inbox.
    assert "function buildRunSummary" in ext
    assert "function buildRunResultSummary" in ext
    assert "Detail: teammate_status runId=" in ext
    assert "text: buildRunSummary(run.id)" in ext
    assert "buildRunSummary(id)" in ext
    assert "text: buildRunResultSummary(params.runId)" in ext
    # No truncation heuristics: per-node rows are status-only unless a
    # synthesized __summary node produced a real summary.
    assert "nodeHeadline" not in ext
    assert "SUMMARY_NODE_ID" in ext
    assert "summarize" in types
    assert "summaryAgent" in types
    assert "settledRun.summary = nodeNow?.result" in ext
    assert "if (run.summary)" in ext
    # No full per-node Result blobs inside the wait loop anymore.
    wait_start = ext.index('name: "teammate_wait"')
    wait_end = ext.index('name: "teammate_cancel"', wait_start)
    assert "buildRunSummary(id)" in ext[wait_start:wait_end]
    assert "Result: ${cap(node.result)}" not in ext[wait_start:wait_end]
    assert "await sleep(500)" in ext


def test_guidance_is_run_centric_without_redundant_tool_list() -> None:
    ext = source("index.ts")
    guidance = ext[ext.index("const TEAMMATE_GUIDANCE"):ext.index("export default function")]
    assert "teammate_run" in guidance
    assert "teammate_status" in guidance
    assert "teammate_wait" in guidance
    assert "teammate_cancel" in guidance
    assert ".pi/agents" in guidance
    assert "~/.pi/agent/agents" in guidance
    assert "dependsOn" in guidance
    assert "teammate_register" not in guidance
    assert "inspect idle teammates" not in guidance
    assert "Available orchestration tools:" not in guidance


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
