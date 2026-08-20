from __future__ import annotations

import json
import subprocess
import textwrap
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
SRC = PACKAGE / "src"

LEADER_TOOLS = {
    "teammate_run",
    "teammate_fanout",
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
        "Feature: Agent Teams run-centric orchestration and messaging contract",
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
        "Background teammate_run suppresses startup text in tool return",
        "A long inline run detaches to background after the gather cap",
        "Cancel one node while the rest of the run continues",
        "Retry failed and cancelled nodes without re-running completed ones",
        "Workers report exclusively to the team leader",
        "No peer mailboxes, broadcasts, or worker inboxes exist",
        "no peer mailbox, broadcast, or worker inbox operation is available",
        "leader can steer a running RPC worker through teammate_message",
        "Completing a node injects its result into downstream prompts",
        "Messages carry no read receipts",
        "Multi-node runs synthesize a final summary by default",
        "Read nodes with overlapping paths may run concurrently",
        "Write nodes with overlapping paths are blocked without worktree isolation",
        "Worktree isolation allows parallel write experiments",
        "A failed node fails the run and downstream nodes are not started",
        "Reject malformed task graphs",
        "Reject ambiguous path ownership",
        "Paths and access are scheduling metadata, not enforcement",
        "paths and access are scheduling and prompt metadata only",
        "shared-workspace protection is advisory write/write coordination",
        "paths and access provide no OS or container sandbox",
        "paths and access provide no true read/write enforcement",
        "Run lifecycle is explicit",
        "The leader coordinates through dispatch, runtime steer, cancel, and retry",
        "Each completed teammate notifies the leader immediately",
        "Automatic teammate follow-ups are serialized",
        "exactly one idle prompt reservation is active before agent start",
        "later reports use the follow-up queue instead of starting another prompt",
        "When agent_settled fires",
        "A failed automatic follow-up preserves reports and retries with backoff",
        "Follow-up watchdog and retry timers are cleaned up at lifecycle boundaries",
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
        "Teammate widget adapts live activity to available width without wrapping",
        "activity text adapts to the remaining line width instead of a fixed character cap",
        "active tool execution takes priority over live thinking and live text",
        "each teammate row is strictly a single line without wrapping even in narrow terminals",
        "long tool activity is truncated inline with an ellipsis",
        "a teammate widget row never wraps a truncation notice onto a second line",
        "the idle widget stays hidden until a teammate is running",
        "Detail scrolling preserves every wrapped display line",
        "Terminal session state is bounded without removing active runs",
        "Deeply nested structured output cannot break event draining",
        "Worktree finalization failures still settle the node",
        "Shutdown preserves diagnostics for unconfirmed workers",
        "Malformed worker output becomes a leader diagnostic",
        "Follow-up retries stop at a bounded attempt count",
        "Follow-up retry attempts are scoped to each report batch",
        "Cancellation intent wins when termination sees an exited child",
        "Close observation before onExit preserves node-only cancellation",
        "Late close callbacks are harmless after shutdown",
        "Shutdown confirms workers only after close is observed",
        "confirmed closed means the child close event was observed",
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
    assert 'style.fg(color, node.agent)' in ext
    assert 'const role = style.dim(`(${node.agent})`)' not in ext
    assert 'visibleWidth' in ext or 'visibleWidth' in source("activity.ts")
    assert 'runningTeammateActivity' in ext or 'runningTeammateActivity' in source("activity.ts")
    assert 'runningTeammateLabel' in ext
    assert 'const spinner = PI_SPINNER_FRAMES[spinnerFrame];' in ext
    assert 'fitTeammateRow' in ext
    assert 'formatTeammateLabel' in ext
    assert 'const line = fitTeammateRow(' in ext
    assert 'PI_SPINNER_FRAMES[spinnerFrame]' in ext
    assert 'truncateToWidth(thinking, 48)' not in ext
    assert 'truncateToWidth(live, 48)' not in ext
    # Widget is placed belowEditor (under the input box)
    assert 'placement: "belowEditor"' in ext
    # Live activity: current tool first, then reasoning, then text.
    assert "node.spawn?.activeTool" in source("activity.ts") and "liveThinking" in source("activity.ts")
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
    assert 'function normalizeInline' in spawner
    assert 'text.replace(/\\s+/g, " ").trim()' in spawner
    assert 'bash: ${normalizeInline(command)}' in spawner


def test_running_teammate_activity_priority_and_fallback() -> None:
    ext = source("ui.ts")
    activity = source("activity.ts")
    assert "export function runningTeammateActivity" in activity
    assert "export function formatTeammateLabel" in activity
    assert "extractLatestLine" in activity
    payload = run_node(
        '''
        import { visibleWidth, truncateToWidth } from "@earendil-works/pi-tui";
        import { PI_SPINNER_FRAMES } from "@fradser/pi-kit";

        let spinnerFrame = 0;
        function extractLatestLine(text) {
          if (!text) return undefined;
          const lines = text.split("\\n");
          for (let i = lines.length - 1; i >= 0; i--) {
            const trimmed = lines[i].replace(/\\s+/g, " ").trim();
            if (trimmed.length > 0 && !trimmed.startsWith("... [truncated") && !trimmed.startsWith("…[truncated")) {
              return trimmed;
            }
          }
          return undefined;
        }

        function runningTeammateActivity(node) {
          const tool = node.spawn?.activeTool?.replace(/\\s+/g, " ").trim();
          if (tool) return tool;

          const thinking = extractLatestLine(node.spawn?.liveThinking);
          if (thinking) return thinking;

          const live = extractLatestLine(node.spawn?.liveText);
          if (live) return live;

          return "Working...";
        }

        function runningTeammateLabel(node, maxActivityWidth) {
          const frame = PI_SPINNER_FRAMES[spinnerFrame];
          const rawActivity = runningTeammateActivity(node);
          if (maxActivityWidth !== undefined) {
            if (maxActivityWidth <= 0) return frame;
            return `${frame} ${truncateToWidth(rawActivity, maxActivityWidth)}`;
          }
          return `${frame} ${rawActivity}`;
        }

        const baseNode = (spawn) => ({
          id: "w1", agent: "worker", workerKey: "run_1:w1", status: "running", prompt: "", paths: [], access: "read", dependsOn: [], spawn,
        });
        const withTool = runningTeammateActivity(baseNode({ activeTool: "bash: pnpm test", liveThinking: "thinking line 1\\nthinking line 2", liveText: "live line" }));
        const withThinking = runningTeammateActivity(baseNode({ liveThinking: "thinking line 1\\nthinking line 2\\n\\n", liveText: "live line" }));
        const withLiveText = runningTeammateActivity(baseNode({ liveThinking: "  \\n  ", liveText: "line 1\\nline 2\\n" }));
        const withNothing = runningTeammateActivity(baseNode({ liveThinking: "", liveText: "" }));
        const withoutSpawn = runningTeammateActivity(baseNode(undefined));
        const truncatedThinking = runningTeammateActivity(baseNode({ liveThinking: "real thought\\n... [truncated 100 chars]" }));
        const labelFull = runningTeammateLabel(baseNode({ activeTool: "bash: long-command-with-many-arguments-and-flags" }));
        const labelCapped = runningTeammateLabel(baseNode({ activeTool: "bash: long-command-with-many-arguments-and-flags" }), 15);
        console.log(JSON.stringify({
          withTool,
          withThinking,
          withLiveText,
          withNothing,
          withoutSpawn,
          truncatedThinking,
          labelFull,
          labelCapped,
        }));
        '''
    )
    assert payload["withTool"] == "bash: pnpm test"
    assert payload["withThinking"] == "thinking line 2"
    assert payload["withLiveText"] == "line 2"
    assert payload["withNothing"] == "Working..."
    assert payload["withoutSpawn"] == "Working..."
    assert payload["truncatedThinking"] == "real thought"
    assert payload["labelFull"].endswith("bash: long-command-with-many-arguments-and-flags")
    assert "..." in payload["labelCapped"]


def test_widget_and_console_responsive_width_rendering() -> None:
    ext = source("ui.ts")
    assert "fitTeammateRow" in ext
    assert "teammateRowWidths" in source("activity.ts")
    payload = run_node(
        '''
        import { visibleWidth, truncateToWidth } from "@earendil-works/pi-tui";
        import { PI_SPINNER_FRAMES } from "@fradser/pi-kit";

        let spinnerFrame = 0;
        const TEAM_COLORS = ["success", "warning", "error", "mdLink"];
        function hashName(name) {
          let h = 0;
          for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) | 0;
          return Math.abs(h);
        }

        function extractLatestLine(text) {
          if (!text) return undefined;
          const lines = text.split("\\n");
          for (let i = lines.length - 1; i >= 0; i--) {
            const trimmed = lines[i].replace(/\\s+/g, " ").trim();
            if (trimmed.length > 0 && !trimmed.startsWith("... [truncated") && !trimmed.startsWith("…[truncated")) {
              return trimmed;
            }
          }
          return undefined;
        }

        function runningTeammateActivity(node) {
          const tool = node.spawn?.activeTool?.replace(/\\s+/g, " ").trim();
          if (tool) return tool;

          const thinking = extractLatestLine(node.spawn?.liveThinking);
          if (thinking) return thinking;

          const live = extractLatestLine(node.spawn?.liveText);
          if (live) return live;

          return "Working...";
        }

        function runningTeammateLabel(node, maxActivityWidth) {
          const frame = PI_SPINNER_FRAMES[spinnerFrame];
          const rawActivity = runningTeammateActivity(node);
          if (maxActivityWidth !== undefined) {
            if (maxActivityWidth <= 0) return frame;
            return `${frame} ${truncateToWidth(rawActivity, maxActivityWidth)}`;
          }
          return `${frame} ${rawActivity}`;
        }

        function renderRow(node, width) {
          const maxLineWidth = Math.max(10, width - 1);
          const color = TEAM_COLORS[hashName(node.workerKey) % TEAM_COLORS.length];
          const name = node.agent;
          const spinner = PI_SPINNER_FRAMES[spinnerFrame];
          const prefix = ` ${spinner} ${name} · `;
          const prefixWidth = visibleWidth(prefix);
          const availableWidth = Math.max(0, maxLineWidth - prefixWidth);
          const rawActivity = runningTeammateActivity(node);
          const activityText = availableWidth > 0 ? truncateToWidth(rawActivity, availableWidth) : "";
          const line = availableWidth > 0 ? `${prefix}${activityText}` : prefix.trimEnd();
          return truncateToWidth(line, maxLineWidth);
        }

        const longTool = "bash: pytest packages/agent-teams/tests/test_teammate_package.py -v --capture=no";
        const node = {
          id: "w", agent: "specialist", workerKey: "run_1:w", status: "running", prompt: "", paths: ["x"], access: "read", dependsOn: [],
          spawn: {
            spawnId: "s1", pid: 1, status: "running", processClosed: false, startedAt: 1, isolation: "none",
            activeTool: longTool,
          },
        };

        const renderWide = renderRow(node, 120);
        const renderMed = renderRow(node, 50);
        const renderNarrow = renderRow(node, 15);
        const renderTiny = renderRow(node, 10);
        const consoleLabelWide = runningTeammateLabel(node, 100);
        const consoleLabelNarrow = runningTeammateLabel(node, 10);

        console.log(JSON.stringify({
          wideLine: renderWide,
          wideWidth: visibleWidth(renderWide),
          medLine: renderMed,
          medWidth: visibleWidth(renderMed),
          narrowLine: renderNarrow,
          narrowWidth: visibleWidth(renderNarrow),
          tinyLine: renderTiny,
          tinyWidth: visibleWidth(renderTiny),
          noWrappingWide: !renderWide.includes("\\n"),
          noWrappingNarrow: !renderNarrow.includes("\\n"),
          widePreservedFull: renderWide.includes(longTool),
          consoleLabelWideHasFull: consoleLabelWide.includes(longTool),
          consoleLabelNarrowTruncated: consoleLabelNarrow.includes("..."),
        }));
        '''
    )
    assert payload["noWrappingWide"] is True
    assert payload["noWrappingNarrow"] is True
    assert payload["widePreservedFull"] is True
    assert payload["wideWidth"] <= 120
    assert payload["medWidth"] <= 50
    assert payload["narrowWidth"] <= 15
    assert payload["tinyWidth"] <= 10
    assert payload["consoleLabelWideHasFull"] is True
    assert payload["consoleLabelNarrowTruncated"] is True


def test_follow_up_reports_use_direct_colored_teammate_format() -> None:
    queue = source("follow-up-queue.ts")
    index = source("index.ts")
    assert 'return `<agent-message from="${escapeAttribute(name)}">' in queue
    assert 'Teammate @${name} finished.' not in queue
    assert 'function escapeAttribute' in queue
    assert 'TEAMMATE_REPORT_MESSAGE_TYPE' in index
    assert 'registerMessageRenderer(TEAMMATE_REPORT_MESSAGE_TYPE' in index
    assert 'theme.fg(reportColor(teammate), `@${teammate}`)' in index
    assert 'customMessageLabel' in index
    assert 'Ctrl+O to expand' in index
    assert 'const label = theme.fg("customMessageLabel", theme.bold("[agent-message]"));' in index
    assert 'Teammate @${name} finished.' in index
    assert 'TEAMMATE_FINISHED_ENTRY_TYPE' in index
    assert 'registerEntryRenderer(TEAMMATE_FINISHED_ENTRY_TYPE' in index
    assert 'pi.appendEntry(TEAMMATE_FINISHED_ENTRY_TYPE' in index
    assert 'theme.fg("text", "</agent-message>")' not in index


def test_agent_report_renderer_uses_skill_style_collapsed_and_expanded_states() -> None:
    index = source("index.ts")
    feature = (PACKAGE / "features" / "agent-teams.feature").read_text(encoding="utf-8")
    assert 'theme.fg("customMessageLabel", theme.bold("[agent-message]"))' in index
    assert 'theme.fg("customMessageText", "from")' in index
    assert 'theme.fg(reportColor(teammate), `@${teammate}`)' in index
    assert 'Ctrl+O to expand' in index
    assert 'expanded' in index
    assert 'color: (text) => theme.fg("customMessageText", text)' in index
    assert "Agent reports use a distinct transcript renderer" in feature


def test_follow_up_queue_does_not_consume_unrelated_agent_start() -> None:
    module = (SRC / "follow-up-queue.ts").as_uri()
    payload = run_node(f'''\
        import {{ FollowUpQueue }} from "{module}";
        const sent = [];
        const queue = new FollowUpQueue({{
          isIdle: () => true,
          dispatch: (_reports, content) => sent.push(content),
          agentStartTimeoutMs: 100000,
        }});
        queue.enqueue({{ teammate: "worker", agent: "worker", body: "result", finished: true }});
        await new Promise((resolve) => setTimeout(resolve, 10));
        queue.onAgentStart();
        queue.onAgentSettled();
        const beforeMatch = {{ sent: sent.length, pending: queue.pendingCount }};
        queue.onBeforeAgentStart("<agent-message from=\\\"worker\\\">\\nresult\\n</agent-message>");
        queue.onAgentStart();
        queue.onAgentSettled();
        console.log(JSON.stringify({{ beforeMatch, pending: queue.pendingCount }}));
        ''')
    assert payload == {"beforeMatch": {"sent": 1, "pending": 1}, "pending": 0}


def test_follow_up_report_content_includes_full_body_and_finished_notice() -> None:
    module = (SRC / "follow-up-queue.ts").as_uri()
    payload = run_node(f'''\
        import {{ formatReports }} from "{module}";
        console.log(JSON.stringify(formatReports([{{ teammate: "synthesize", agent: "worker", body: "result", finished: true }}])));
        ''')
    assert payload == "<agent-message from=\"synthesize\">\nresult\n</agent-message>"


def test_terminal_result_omits_internal_node_prefix() -> None:
    module = (SRC / "terminal.ts").as_uri()
    payload = run_node(f'''\
        import {{ buildNodeTerminalResult }} from "{module}";
        console.log(JSON.stringify(buildNodeTerminalResult({{
          runId: "run_2", nodeId: "synthesize", agent: "worker",
          result: {{ stdout: "", stderr: "", signal: null, timedOut: false }},
          nodeResult: "worker result", cancelled: false, patchText: "",
        }})));
        ''')
    assert payload == "worker result"


def test_paths_and_access_contract_is_advisory_metadata() -> None:
    feature = (PACKAGE / "features" / "agent-teams.feature").read_text(encoding="utf-8")
    types = source("types.ts")
    assert "No peer mailboxes, broadcasts, or worker inboxes exist" in feature
    assert "leader can steer a running RPC worker through teammate_message" in feature
    assert "no peer mailbox, broadcast, or worker inbox operation is available" in feature
    assert "Scheduling and prompt metadata only" in types
    assert "advisory shared-workspace write/write coordination" in types
    assert "does not enforce filesystem permissions or provide an OS/container sandbox" in types
    assert "not a permission boundary" in types
    assert "paths do not enforce read/write access or provide an OS/container sandbox" in types
    fanout_schema = types[types.index("export const TeammateFanoutParams"):types.index("/** Leader-only runtime steer")]
    assert "Scheduling and prompt metadata only" in fanout_schema
    assert "do not enforce filesystem permissions" in fanout_schema


def test_guidance_and_description_use_one_way_worker_messages() -> None:
    guidance = source("guidance.ts")
    spawner = source("spawner.ts")
    manifest = json.loads((PACKAGE / "package.json").read_text(encoding="utf-8"))
    assert "no peer mailboxes, broadcasts, or worker inboxes" in guidance
    assert "leader may steer a running RPC" in guidance
    assert "no peer mailbox, broadcast, or worker inbox" in spawner
    assert "one-way worker messages" in manifest["description"]


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
        setNodeSpawnInfo(run.id, "b", {{ spawnId: "s1", pid: 1, status: "running", processClosed: false, startedAt: 1, isolation: "none" }});
        setNodeSpawnInfo(run.id, "c", {{ spawnId: "s2", pid: 2, status: "running", processClosed: false, startedAt: 1, isolation: "none" }});
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
        run.nodes.a.spawn = {{ spawnId: "spawn-1", pid: 1, status: "running", processClosed: false, startedAt: 1, isolation: "none" }};
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
        setNodeSpawnInfo(run.id, "w1", {{ spawnId: "s1", pid: 1, status: "running", processClosed: false, startedAt: 1, isolation: "none" }});
        const writeOverlap = findSharedWorkspaceWriteConflict(run.id, "w2")?.id ?? null;
        const readOverlap = findSharedWorkspaceWriteConflict(run.id, "r")?.id ?? null;
        setNodeSpawnInfo(run.id, "w2", {{ spawnId: "s2", pid: 2, status: "running", processClosed: false, startedAt: 1, isolation: "worktree" }});
        const isolated = findSharedWorkspaceWriteConflict(run.id, "w1")?.id ?? null;
        console.log(JSON.stringify({{ writeOverlap, readOverlap, isolated }}));
        '''
    )
    assert payload == {"writeOverlap": "w1", "readOverlap": None, "isolated": None}


def test_partial_run_cancellation_wins_over_completed_nodes() -> None:
    module = (SRC / "state.ts").as_uri()
    payload = run_node(
        f'''\
        import {{ createRun, resetState, cancelRun, setNodeSpawnInfo, settleRun }} from "{module}";
        resetState();
        const created = createRun({{ cwd: "/tmp", concurrency: 2, worktree: false, background: true, summarize: false,
          nodes: [
            {{ id: "done", agent: "worker", prompt: "", paths: ["x"], access: "read", dependsOn: [] }},
            {{ id: "live", agent: "worker", prompt: "", paths: ["y"], access: "read", dependsOn: [] }},
          ] }});
        const run = created.run;
        setNodeSpawnInfo(run.id, "done", {{ spawnId: "s1", pid: 1, status: "completed", processClosed: true, startedAt: 1, isolation: "none" }});
        setNodeSpawnInfo(run.id, "live", {{ spawnId: "s2", pid: 2, status: "running", processClosed: false, startedAt: 1, isolation: "none" }});
        const cancellation = cancelRun(run.id);
        const whileLive = settleRun(run.id);
        setNodeSpawnInfo(run.id, "live", {{ spawnId: "s2", pid: 2, status: "failed", processClosed: true, startedAt: 1, isolation: "none" }});
        const afterClose = settleRun(run.id);
        console.log(JSON.stringify({{ cancelRequested: run.cancelRequested, runningNodeIds: cancellation.runningNodeIds, whileLive, afterClose, done: run.nodes.done.status, live: run.nodes.live.status }}));
        '''
    )
    assert payload == {
        "cancelRequested": True,
        "runningNodeIds": ["live"],
        "whileLive": "running",
        "afterClose": "cancelled",
        "done": "completed",
        "live": "cancelled",
    }


def test_terminal_report_does_not_release_process_lifecycle_resources() -> None:
    module = (SRC / "state.ts").as_uri()
    payload = run_node(
        f'''\
        import {{ createRun, resetState, acceptTerminalReport, setNodeSpawnInfo, runningNodeCount, findSharedWorkspaceWriteConflict, nodeIsReady }} from "{module}";
        resetState();
        const created = createRun({{ cwd: "/tmp", concurrency: 2, worktree: false, background: true, summarize: false,
          nodes: [
            {{ id: "a", agent: "worker", prompt: "", paths: ["src"], access: "write", dependsOn: [] }},
            {{ id: "b", agent: "worker", prompt: "", paths: ["src/lib"], access: "write", dependsOn: [] }},
            {{ id: "downstream", agent: "worker", prompt: "", paths: ["out"], access: "read", dependsOn: ["a"] }},
          ] }});
        const run = created.run;
        setNodeSpawnInfo(run.id, "a", {{ spawnId: "s1", pid: 1, status: "running", processClosed: false, startedAt: 1, isolation: "none" }});
        setNodeSpawnInfo(run.id, "b", {{ spawnId: "s2", pid: 2, status: "running", processClosed: false, startedAt: 1, isolation: "none" }});
        const accepted = acceptTerminalReport(run.id, "a", "s1", "completed", "done");
        const beforeClose = {{ accepted, status: run.nodes.a.status, running: runningNodeCount(run.id), conflict: findSharedWorkspaceWriteConflict(run.id, "b")?.id ?? null, ready: nodeIsReady(run, run.nodes.downstream) }};
        setNodeSpawnInfo(run.id, "a", {{ spawnId: "s1", pid: 1, status: "completed", processClosed: true, startedAt: 1, isolation: "none" }});
        const afterClose = {{ status: run.nodes.a.status, running: runningNodeCount(run.id), conflict: findSharedWorkspaceWriteConflict(run.id, "b")?.id ?? null, ready: nodeIsReady(run, run.nodes.downstream) }};
        console.log(JSON.stringify({{ beforeClose, afterClose }}));
        '''
    )
    assert payload == {
        "beforeClose": {"accepted": True, "status": "running", "running": 2, "conflict": "a", "ready": False},
        "afterClose": {"status": "completed", "running": 1, "conflict": None, "ready": True},
    }


def test_each_spawn_accepts_only_one_terminal_report() -> None:
    module = (SRC / "state.ts").as_uri()
    payload = run_node(
        f'''\
        import {{ createRun, resetState, acceptTerminalReport, setNodeSpawnInfo }} from "{module}";
        resetState();
        const created = createRun({{ cwd: "/tmp", concurrency: 1, worktree: false, background: true, summarize: false,
          nodes: [{{ id: "a", agent: "worker", prompt: "", paths: ["src"], access: "read", dependsOn: [] }}] }});
        const run = created.run;
        setNodeSpawnInfo(run.id, "a", {{ spawnId: "s1", pid: 1, status: "running", processClosed: false, startedAt: 1, isolation: "none" }});
        const first = acceptTerminalReport(run.id, "a", "s1", "completed", "done");
        const second = acceptTerminalReport(run.id, "a", "s1", "failed", "late failure");
        console.log(JSON.stringify({{ first, second, report: run.nodes.a.spawn?.logicalTerminalReport, result: run.nodes.a.result, error: run.nodes.a.errorMessage }}));
        '''
    )
    assert payload == {
        "first": True,
        "second": False,
        "report": "completed",
        "result": "done",
    }


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
        setNodeSpawnInfo(run.id, "a", {{ spawnId: "s1", pid: 1, status: "running", processClosed: false, startedAt: 1, isolation: "none" }});
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
        run.nodes.a.spawn = {{ spawnId: "s1", pid: 1, status: "running", processClosed: false, startedAt: 1, isolation: "none" }};
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
    assert "run.background && !run.completionNotified" not in machine
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
    assert "sendUpdate({ kind: \"summary\"" not in machine
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


def test_cancellation_remains_authoritative_when_child_exit_precedes_close() -> None:
    module = (SRC / "spawner.ts").as_uri()
    payload = run_node(
        f'''\
        import {{ CancellationIntents }} from "{module}";
        const intents = new CancellationIntents();
        const outcomes = [];
        intents.begin("spawn-1");
        intents.request("spawn-1");
        intents.defer("spawn-1", (cancelled) => outcomes.push(cancelled ? "cancelled" : "normal"));
        const childExited = intents.resolve("spawn-1", false);
        console.log(JSON.stringify({{ childExited, outcomes, pending: intents.has("spawn-1") }}));
        '''
    )
    assert payload == {"childExited": True, "outcomes": ["cancelled"], "pending": False}


def test_close_before_on_exit_keeps_cancellation_until_deferred_finalizer() -> None:
    module = (SRC / "spawner.ts").as_uri()
    payload = run_node(
        f'''\
        import {{ CancellationIntents }} from "{module}";
        const intents = new CancellationIntents();
        const outcomes = [];
        intents.begin("spawn-1");
        intents.request("spawn-1");
        const observed = intents.close("spawn-1");
        const beforeOnExit = {{ outcomes: [...outcomes], pending: intents.has("spawn-1") }};
        const deferred = intents.defer("spawn-1", (cancelled) => outcomes.push(cancelled ? "cancelled" : "normal"));
        console.log(JSON.stringify({{ observed, deferred, beforeOnExit, outcomes, pending: intents.has("spawn-1") }}));
        '''
    )
    assert payload == {
        "observed": True,
        "deferred": True,
        "beforeOnExit": {"outcomes": [], "pending": True},
        "outcomes": ["cancelled"],
        "pending": False,
    }


def test_close_before_on_exit_node_cancellation_does_not_cancel_other_nodes() -> None:
    state_module = (SRC / "state.ts").as_uri()
    spawner_module = (SRC / "spawner.ts").as_uri()
    payload = run_node(
        f'''\
        import {{ createRun, resetState, cancelNode, setNodeSpawnInfo, settleRun, updateNodeStatus }} from "{state_module}";
        import {{ CancellationIntents }} from "{spawner_module}";
        resetState();
        const created = createRun({{ cwd: "/tmp", concurrency: 2, worktree: false, summarize: false, nodes: [
          {{ id: "cancelled", agent: "worker", prompt: "", paths: ["a"], access: "read", dependsOn: [] }},
          {{ id: "other", agent: "worker", prompt: "", paths: ["b"], access: "read", dependsOn: [] }},
        ] }});
        const run = created.run;
        setNodeSpawnInfo(run.id, "cancelled", {{ spawnId: "s1", pid: 1, status: "running", processClosed: false, startedAt: 1, isolation: "none" }});
        setNodeSpawnInfo(run.id, "other", {{ spawnId: "s2", pid: 2, status: "running", processClosed: false, startedAt: 1, isolation: "none" }});
        const cancellation = cancelNode(run.id, "cancelled");
        const intents = new CancellationIntents();
        intents.begin("s1");
        intents.request("s1");
        intents.close("s1");
        setNodeSpawnInfo(run.id, "cancelled", {{ spawnId: "s1", pid: 1, status: "completed", processClosed: true, startedAt: 1, isolation: "none" }});
        let finalized = "";
        intents.defer("s1", (cancelled) => {{
          finalized = cancelled ? "cancelled" : "normal";
          if (cancelled) updateNodeStatus(run.id, "cancelled", "cancelled");
        }});
        const status = settleRun(run.id);
        console.log(JSON.stringify({{ finalized, cancellation: cancellation.runningNodeIds, cancelled: run.nodes.cancelled.status, other: run.nodes.other.status, runStatus: status }}));
        '''
    )
    assert payload == {
        "finalized": "cancelled",
        "cancellation": ["cancelled"],
        "cancelled": "cancelled",
        "other": "running",
        "runStatus": "running",
    }


def test_late_close_after_shutdown_is_guarded_by_generation() -> None:
    machine = source("run-machine.ts")
    shutdown = machine[machine.index("export function shutdownRunMachine"):machine.index("function currentStateFile")]
    assert "runMachineGeneration++" in shutdown
    assert "if (generation !== runMachineGeneration)" in machine
    assert "if (generation !== runMachineGeneration || getNode(runId, nodeId)?.spawn?.spawnId !== spawnId) return;" in machine


def test_shutdown_does_not_treat_exit_code_as_observed_close() -> None:
    module = (SRC / "spawner.ts").as_uri()
    payload = run_node(
        f'''\
        import {{ EventEmitter }} from "node:events";
        import {{ terminateWorkerEntries }} from "{module}";
        const child = Object.assign(new EventEmitter(), {{ exitCode: 0, signalCode: null, pid: 1, kill: () => false }});
        const keepAlive = setTimeout(() => {{}}, 50);
        const results = await terminateWorkerEntries([["worker-1", child]], 5);
        clearTimeout(keepAlive);
        console.log(JSON.stringify(results[0]));
        '''
    )
    assert payload == {"name": "worker-1", "confirmedClosed": False}


def test_shutdown_requires_observed_close_before_confirming_worker() -> None:
    module = (SRC / "spawner.ts").as_uri()
    payload = run_node(
        f'''\
        import {{ spawn }} from "node:child_process";
        import {{ isWorkerCloseObserved, terminateWorkerEntries, watchWorkerClose }} from "{module}";
        const child = spawn(process.execPath, ["--eval", `process.exit(0)`], {{ stdio: ["ignore", "ignore", "ignore"] }});
        watchWorkerClose(child);
        await new Promise((resolve) => setTimeout(resolve, 30));
        const results = await terminateWorkerEntries([["worker-1", child]], 10);
        console.log(JSON.stringify({{ result: results[0], closeObserved: isWorkerCloseObserved(child) }}));
        '''
    )
    assert payload["result"] == {"name": "worker-1", "confirmedClosed": True}
    assert payload["closeObserved"] is True


def test_exit_code_without_close_does_not_release_node_resources() -> None:
    module = (SRC / "state.ts").as_uri()
    payload = run_node(
        f'''\
        import {{ createRun, resetState, setNodeSpawnInfo, runningNodeCount }} from "{module}";
        resetState();
        const run = createRun({{ cwd: "/tmp", concurrency: 1, worktree: false, summarize: false, nodes: [{{ id: "a", agent: "worker", prompt: "", paths: ["src"], access: "read", dependsOn: [] }}] }}).run;
        setNodeSpawnInfo(run.id, "a", {{ spawnId: "s1", pid: 1, status: "running", processClosed: false, startedAt: 1, isolation: "none" }});
        setNodeSpawnInfo(run.id, "a", {{ spawnId: "s1", pid: 1, status: "completed", exitCode: 0, startedAt: 1, isolation: "none" }});
        const beforeClose = {{ processClosed: run.nodes.a.spawn?.processClosed, status: run.nodes.a.status, running: runningNodeCount(run.id) }};
        setNodeSpawnInfo(run.id, "a", {{ spawnId: "s1", pid: 1, status: "completed", processClosed: true, exitCode: 0, startedAt: 1, isolation: "none" }});
        console.log(JSON.stringify({{ beforeClose, afterClose: {{ processClosed: run.nodes.a.spawn?.processClosed, status: run.nodes.a.status, running: runningNodeCount(run.id) }} }}));
        '''
    )
    assert payload == {"beforeClose": {"processClosed": False, "status": "running", "running": 1}, "afterClose": {"processClosed": True, "status": "completed", "running": 0}}


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


def test_rpc_steering_writes_to_child_stdin() -> None:
    module = (SRC / "spawner.ts").as_uri()
    payload = run_node(
        f'''\
        import {{ spawn }} from "node:child_process";
        import {{ sendWorkerSteerToChild }} from "{module}";
        const child = spawn(process.execPath, ["--eval", `process.stdin.on("data", (chunk) => {{ process.stdout.write(chunk); process.exit(0); }});`], {{ stdio: ["pipe", "pipe", "ignore"] }});
        let output = "";
        const done = new Promise((resolve) => child.stdout.on("data", (chunk) => {{ output += chunk.toString(); }}).on("close", resolve));
        const sent = sendWorkerSteerToChild(child, "adjust scope");
        await done;
        console.log(JSON.stringify({{ sent, message: JSON.parse(output).message, type: JSON.parse(output).type }}));
        '''
    )
    assert payload == {"sent": True, "message": "adjust scope", "type": "steer"}


def test_worker_prompt_allows_rpc_leader_steering_without_peer_mailboxes() -> None:
    module = (SRC / "spawner.ts").as_uri()
    payload = run_node(
        f'''\
        import {{ buildAutonomousPrompt }} from "{module}";
        const prompt = buildAutonomousPrompt({{ name: "worker", role: "worker", prompt: "task" }});
        console.log(JSON.stringify({{ steer: prompt.includes("leader may steer this worker through teammate_message in RPC mode"), noPeers: prompt.includes("no peer mailboxes, broadcasts, or worker inboxes") }}));
        '''
    )
    assert payload == {"steer": True, "noPeers": True}


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


def test_input_binding_and_fork_context_helpers_are_dependency_scoped() -> None:
    module = (SRC / "state.ts").as_uri()
    payload = run_node(
        f'''\
        import {{ createRun, resetState, resolveInputBinding, buildForkContext }} from "{module}";
        resetState();
        const run = createRun({{ cwd: "/tmp", concurrency: 1, worktree: false, summarize: false, nodes: [
          {{ id: "a", agent: "worker", prompt: "", paths: ["src"], access: "read", dependsOn: [] }},
          {{ id: "b", agent: "worker", prompt: "", paths: ["src"], access: "read", dependsOn: ["a"] }},
          {{ id: "c", agent: "worker", prompt: "", paths: ["src"], access: "read", dependsOn: ["a", "b"], forkContext: ["a"] }},
        ] }}).run;
        run.nodes.a.result = "raw";
        run.nodes.a.structuredOutput = {{ value: "bound" }};
        run.nodes.b.result = "other";
        console.log(JSON.stringify({{ binding: resolveInputBinding(run, run.nodes.b, "a#/json/value"), rejected: resolveInputBinding(run, run.nodes.b, "ghost"), fork: buildForkContext(run, run.nodes.c) }}));
        '''
    )
    assert payload["binding"] == '"bound"'
    assert payload["rejected"] == "(rejected: source is not a dependency)"
    assert payload["fork"] == ['--- a (worker, pending) ---\nraw\nStructured output: {"value":"bound"}']


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
    assert "acceptTerminalReport" in machine
    assert "terminalReportAccepted" in types
    assert "processClosed" in types
    assert 'name: "teammate_report"' not in machine


def test_deep_structured_output_validation_is_non_throwing() -> None:
    module = (SRC / "state.ts").as_uri()
    payload = run_node(
        f'''\
        import {{ validateStructuredOutput }} from "{module}";
        let value = {{}};
        for (let index = 0; index < 5000; index++) value = {{ child: value }};
        let diagnostic = "";
        try {{ diagnostic = validateStructuredOutput(value) ?? ""; }} catch (error) {{ diagnostic = `threw: ${{error}}`; }}
        console.log(JSON.stringify({{ diagnostic, threw: diagnostic.startsWith("threw:") }}));
        '''
    )
    assert payload["threw"] is False
    assert "depth" in payload["diagnostic"]


def test_terminal_run_compaction_preserves_active_and_recent_runs() -> None:
    module = (SRC / "state.ts").as_uri()
    payload = run_node(
        f'''\
        import {{ createRun, resetState, compactTerminalRuns, getState, MAX_TERMINAL_RUNS, deliverToLeader }} from "{module}";
        resetState();
        const first = createRun({{ cwd: "/tmp", concurrency: 1, worktree: false, background: true, summarize: false, nodes: [{{ id: "first", agent: "worker", prompt: "", paths: ["x"], access: "read", dependsOn: [] }}] }}).run;
        first.status = "completed"; first.settledMessageSent = true; first.updatedAt = 1;
        const active = createRun({{ cwd: "/tmp", concurrency: 1, worktree: false, background: true, summarize: false, nodes: [{{ id: "active", agent: "worker", prompt: "", paths: ["x"], access: "read", dependsOn: [] }}] }}).run;
        for (let i = 0; i < MAX_TERMINAL_RUNS + 1; i++) {{
          const run = createRun({{ cwd: "/tmp", concurrency: 1, worktree: false, background: true, summarize: false, nodes: [{{ id: `n-${{i}}`, agent: "worker", prompt: "", paths: ["x"], access: "read", dependsOn: [] }}] }}).run;
          run.status = "completed"; run.settledMessageSent = true; run.updatedAt = i + 2;
          deliverToLeader({{ from: run.id, subject: run.id, body: "message", runId: run.id }});
        }}
        const removed = compactTerminalRuns();
        console.log(JSON.stringify({{ removed: removed.length, terminalRuns: Object.values(getState().runs).filter((run) => run.status !== "running").length, hasActive: Boolean(getState().runs[active.id]), mailbox: getState().leaderMailbox.length }}));
        '''
    )
    assert payload["removed"] >= 1
    assert payload["hasActive"] is True
    assert payload["terminalRuns"] <= 256


def test_worktree_capture_failure_returns_structured_error() -> None:
    module = (SRC / "worktree.ts").as_uri()
    payload = run_node(
        f'''\
        import {{ captureWorktreeDiff }} from "{module}";
        const result = captureWorktreeDiff({{ path: "/tmp/agent-teams-missing-worktree", repoRoot: "/tmp", cwd: "/tmp", branch: "missing", baseCommit: "HEAD" }});
        console.log(JSON.stringify({{ ok: result.ok, hasError: !result.ok && result.error.length > 0 }}));
        '''
    )
    assert payload == {"ok": False, "hasError": True}


def test_finalize_handles_worktree_and_shutdown_diagnostics() -> None:
    machine = source("run-machine.ts")
    worktree = source("worktree.ts")
    index = source("index.ts")
    spawner = source("spawner.ts")
    assert "try {" in machine and "captureWorktreeDiff(worktree)" in machine
    assert "finally" in machine and "cleanupWorktree(worktree)" in machine
    assert "Worktree capture failed" in machine
    assert "terminateAllWorkers" in index
    assert "confirmedClosed" in spawner
    assert "shutdown" in index.lower()
    assert "cleanupError" in machine
    assert "captureWorktreeDiff" in worktree
    assert "WorktreeDiffResult" in worktree


def test_leader_followups_use_a_lifecycle_aware_queue() -> None:
    index = source("index.ts")
    queue = source("follow-up-queue.ts")
    assert 'FollowUpQueue' in index
    assert "followUpQueue?.onBeforeAgentStart(event.prompt)" in index
    assert "followUpQueue?.onAgentStart()" in index
    assert "followUpQueue?.onAgentSettled()" in index
    assert "followUpQueue?.reset()" in index
    assert "agentStartTimeoutMs" in queue
    assert "retryBaseDelayMs" in queue
    assert "this.pending.unshift({ reports: failed.reports" in queue
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
        queue.enqueue({{ teammate: "A", agent: "worker", body: "report" }});
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
        queue.enqueue({{ teammate: "A", agent: "worker", body: "report" }});
        await new Promise((resolve) => setTimeout(resolve, 20));
        const result = {{ pending: queue.pendingCount, failures: failures.length }};
        queue.reset();
        console.log(JSON.stringify(result));
        ''')
    assert payload == {"pending": 1, "failures": 1}


def test_follow_up_queue_retry_budget_is_per_report_batch() -> None:
    module = (SRC / "follow-up-queue.ts").as_uri()
    payload = run_node(f'''\
        import {{ FollowUpQueue }} from "{module}";
        const sent = [];
        const failures = [];
        const queue = new FollowUpQueue({{ isIdle: () => true, dispatch: () => {{ throw new Error("failed"); }}, onFailure: (message) => failures.push(message), maxAttempts: 2, retryBaseDelayMs: 1, retryMaxDelayMs: 1 }});
        queue.enqueue({{ teammate: "first", agent: "worker", body: "report" }});
        await new Promise((resolve) => setTimeout(resolve, 10));
        queue.enqueue({{ teammate: "second", agent: "worker", body: "report" }});
        await new Promise((resolve) => setTimeout(resolve, 15));
        console.log(JSON.stringify({{ deadLetter: queue.deadLetterCount, failures: failures.length, pending: queue.pendingCount, sent: sent.length }}));
        '''
    )
    assert payload == {"deadLetter": 2, "failures": 4, "pending": 0, "sent": 0}


def test_follow_up_queue_dead_letters_after_max_attempts_without_timer() -> None:
    module = (SRC / "follow-up-queue.ts").as_uri()
    script = f'''\
        import {{ FollowUpQueue }} from "{module}";
        const failures = [];
        const queue = new FollowUpQueue({{
          isIdle: () => true,
          dispatch: () => {{ throw new Error("preflight failed"); }},
          onFailure: (message) => failures.push(message),
          maxAttempts: 2,
          retryBaseDelayMs: 1,
          retryMaxDelayMs: 1,
        }});
        queue.enqueue({{ teammate: "A", agent: "worker", body: "report" }});
        await new Promise((resolve) => setTimeout(resolve, 25));
        console.log(JSON.stringify({{ pending: queue.pendingCount, deadLetter: queue.deadLetterCount, failures: failures.length }}));
        '''
    result = subprocess.run(
        ["node", "--input-type=module", "--eval", textwrap.dedent(script)],
        cwd=PACKAGE,
        check=True,
        capture_output=True,
        text=True,
        timeout=1,
    )
    assert json.loads(result.stdout) == {"pending": 0, "deadLetter": 1, "failures": 2}


def test_follow_up_queue_cleans_timers_at_lifecycle_boundaries() -> None:
    module = (SRC / "follow-up-queue.ts").as_uri()
    script = f'''\
        import {{ FollowUpQueue }} from "{module}";
        const resetQueue = new FollowUpQueue({{
          isIdle: () => true,
          dispatch: () => {{ throw new Error("preflight failed"); }},
          retryBaseDelayMs: 100000,
          retryMaxDelayMs: 100000,
        }});
        resetQueue.enqueue({{ teammate: "retry", agent: "worker", body: "report" }});
        await new Promise((resolve) => setTimeout(resolve, 20));
        resetQueue.reset();

        const sent = [];
        let settledQueue;
        settledQueue = new FollowUpQueue({{
          isIdle: () => true,
          dispatch: (_reports, content) => {{
            sent.push(content);
            settledQueue.onBeforeAgentStart(content);
            settledQueue.onAgentStart();
            settledQueue.onAgentSettled();
          }},
          agentStartTimeoutMs: 100000,
        }});
        settledQueue.enqueue({{ teammate: "success", agent: "worker", body: "report" }});
        await new Promise((resolve) => setTimeout(resolve, 20));
        console.log(JSON.stringify({{
          resetPending: resetQueue.pendingCount,
          settledPending: settledQueue.pendingCount,
          sent: sent.length,
        }}));
        '''
    try:
        result = subprocess.run(
            ["node", "--input-type=module", "--eval", textwrap.dedent(script)],
            cwd=PACKAGE,
            check=True,
            capture_output=True,
            text=True,
            timeout=1,
        )
    except subprocess.TimeoutExpired as error:
        raise AssertionError("follow-up queue left a timer keeping the child alive") from error
    assert json.loads(result.stdout) == {
        "resetPending": 0,
        "settledPending": 0,
        "sent": 1,
    }


def test_follow_up_queue_ignores_stale_session_callbacks() -> None:
    module = (SRC / "follow-up-queue.ts").as_uri()
    payload = run_node(f'''\
        import {{ FollowUpQueue }} from "{module}";
        const sent = [];
        const queue = new FollowUpQueue({{
          isIdle: () => true,
          dispatch: (_reports, content) => sent.push(content),
          agentStartTimeoutMs: 100000,
        }});
        queue.enqueue({{ teammate: "old", agent: "worker", body: "report" }});
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
          dispatch: (_reports, content) => sent.push(content),
          agentStartTimeoutMs: 100000,
        }});
        queue.enqueue({{ teammate: "A", agent: "worker", body: "first" }});
        await new Promise((resolve) => setTimeout(resolve, 10));
        queue.enqueue({{ teammate: "B", agent: "worker", body: "second" }});
        queue.onAgentSettled();
        await new Promise((resolve) => setTimeout(resolve, 10));
        const beforeStart = sent.length;
        queue.onBeforeAgentStart("<agent-message from=\\\"A\\\">\\nfirst\\n</agent-message>");
        queue.onAgentStart();
        queue.onAgentSettled();
        await new Promise((resolve) => setTimeout(resolve, 10));
        const result = {{ beforeStart, sent }};
        queue.reset();
        console.log(JSON.stringify(result));
        ''')
    assert payload == {"beforeStart": 1, "sent": ["<agent-message from=\"A\">\nfirst\n</agent-message>", "<agent-message from=\"B\">\nsecond\n</agent-message>"]}


def test_follow_up_queue_removes_protocol_and_run_identifiers() -> None:
    module = (SRC / "follow-up-queue.ts").as_uri()
    payload = run_node(f'''\
        import {{ FollowUpQueue }} from "{module}";
        const sent = [];
        const queue = new FollowUpQueue({{ isIdle: () => true, dispatch: (_reports, content) => sent.push(content) }});
        queue.enqueue({{ teammate: "synthesize", agent: "worker", body: "result", finished: true, runId: "run_6" }});
        await new Promise((resolve) => setTimeout(resolve, 10));
        queue.reset();
        console.log(JSON.stringify(sent));
        ''')
    assert payload == ["<agent-message from=\"synthesize\">\nresult\n</agent-message>"]


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
        import {{ createRun, resetState, getState, setNodeSpawnInfo, receiveWorkerMessage, acceptTerminalReport, nodeIsReady, settleRun }} from "{state_module}";
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
        setNodeSpawnInfo(run.id, "node_a", {{ spawnId, pid: 1001, status: "running", processClosed: false, startedAt: Date.now(), isolation: "none" }});
        const outbox = workerOutboxPath(stateFile, run.nodes.node_a.workerKey, spawnId);
        appendWorkerEvent(outbox, {{ id: "evt-a-1", type: "message", worker: run.nodes.node_a.workerKey, spawnId, subject: "Artifact", body: "Architecture", status: "completed" }});
        const {{ events }} = readWorkerEvents(outbox, 0);
        for (const event of events) {{
          if (event.type !== "message") continue;
          receiveWorkerMessage(event);
          acceptTerminalReport(run.id, "node_a", spawnId, event.status, event.body);
        }}
        setNodeSpawnInfo(run.id, "node_a", {{ spawnId, pid: 1001, status: "completed", processClosed: true, startedAt: Date.now(), isolation: "none" }});
        const ready = nodeIsReady(run, run.nodes.node_b);
        setNodeSpawnInfo(run.id, "node_b", {{ spawnId: "spawn-b-1", pid: 1002, status: "completed", processClosed: true, startedAt: Date.now(), isolation: "none" }});
        const settled = settleRun(run.id);
        console.log(JSON.stringify({{ messages: getState().leaderMailbox.map((m) => m.subject).join(","), ready, settled }}));
        '''
    )
    assert payload == {"messages": "Artifact", "ready": True, "settled": "completed"}


def test_background_run_suppresses_startup_notice_text() -> None:
    tools_src = source("tools.ts")
    assert "if (run.background)" in tools_src
    assert "content: []" in tools_src
    assert "Started run [" not in tools_src
    assert "gatherForeground(run.id, signal)" in tools_src
