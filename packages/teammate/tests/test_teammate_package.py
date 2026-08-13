from __future__ import annotations

import json
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
SKILLS = PACKAGE / "skills"
SRC = PACKAGE / "src"
MEMORY = PACKAGE / ".memory"


def frontmatter(text: str) -> str:
    parts = text.split("---", 2)
    assert len(parts) == 3, "SKILL.md must have YAML frontmatter delimited by ---"
    return parts[1]


def test_manifest_declares_native_pi_package() -> None:
    manifest = json.loads((PACKAGE / "package.json").read_text(encoding="utf-8"))
    assert "pi-package" in manifest["keywords"]
    assert manifest["pi"]["skills"] == ["./skills"]
    assert manifest["pi"]["extensions"] == ["./src/index.ts"]


def test_extension_entry_point_exists() -> None:
    assert (SRC / "index.ts").is_file(), "Extension entry point src/index.ts is missing"
    assert (SRC / "state.ts").is_file(), "State module src/state.ts is missing"
    assert (SRC / "types.ts").is_file(), "Types module src/types.ts is missing"
    assert (SRC / "spawner.ts").is_file(), "Spawner module src/spawner.ts is missing"
    assert (SRC / "worktree.ts").is_file(), "Worktree module src/worktree.ts is missing"


def test_extension_declares_peer_dependency() -> None:
    manifest = json.loads((PACKAGE / "package.json").read_text(encoding="utf-8"))
    assert "peerDependencies" in manifest
    for pkg in ("@earendil-works/pi-coding-agent", "@earendil-works/pi-tui", "typebox"):
        assert pkg in manifest["peerDependencies"]
        assert manifest["peerDependencies"][pkg] == "*"


def test_single_skill_using_teammate_is_present() -> None:
    skills = sorted(SKILLS.glob("*/SKILL.md"))
    assert [skill.parent.name for skill in skills] == ["using-teammate"]


def test_skill_has_valid_frontmatter() -> None:
    skill = SKILLS / "using-teammate" / "SKILL.md"
    text = skill.read_text(encoding="utf-8")
    metadata = frontmatter(text)
    assert "name:" in metadata
    assert "description:" in metadata
    assert "name: using-teammate" in metadata


def test_skill_is_usage_guide_not_openai_reference() -> None:
    """SKILL.md should be a Pi extension usage guide, not the OpenAI API reference."""
    skill = (SKILLS / "using-teammate" / "SKILL.md").read_text(encoding="utf-8")
    # Should contain Pi extension tool references
    assert "teammate_register" in skill
    assert "teammate_assign_task" in skill
    assert "teammate_broadcast" in skill
    # Should NOT contain the OpenAI API reference content
    assert "Workspace Agents API" not in skill
    assert "developers.openai.com" not in skill
    assert "api.chatgpt.com" not in skill


def test_memory_reference_is_separate_file() -> None:
    """OpenAI API reference should be in .memory/, not in SKILL.md."""
    ref = MEMORY / "openai_teammate_api_reference.md"
    assert ref.is_file(), "OpenAI API reference missing from .memory/"
    content = ref.read_text(encoding="utf-8")
    assert "Workspace Agents API" in content
    assert "developers.openai.com" in content
    assert "api.chatgpt.com" in content


def test_memory_index_exists() -> None:
    idx = MEMORY / "MEMORY.md"
    assert idx.is_file(), "Memory index MEMORY.md missing"
    content = idx.read_text(encoding="utf-8")
    assert "openai_teammate_api_reference.md" in content


def test_claude_only_artifacts_are_not_shipped() -> None:
    assert not (PACKAGE / ".claude-plugin").exists()
    assert not list(PACKAGE.rglob("plugin.json"))
    assert not list(PACKAGE.rglob("openai.yaml"))
    content = "\n".join(path.read_text(encoding="utf-8") for path in PACKAGE.rglob("*.md"))
    for forbidden in (
        "allowed-tools:",
        "user-invocable:",
        "CLAUDE_PLUGIN_ROOT",
        "/teammate:",
        "AskUserQuestion",
    ):
        assert forbidden not in content


def test_extension_registers_tools() -> None:
    """Extension source should register all expected tools."""
    ext = (SRC / "index.ts").read_text(encoding="utf-8")
    expected_tools = [
        "teammate_register",
        "teammate_list",
        "teammate_send",
        "teammate_read_mailbox",
        "teammate_assign_task",
        "teammate_list_tasks",
        "teammate_update_task",
        "teammate_broadcast",
        "teammate_spawn",
        "teammate_task_deps",
    ]
    for tool in expected_tools:
        assert f'name: "{tool}"' in ext, f"Tool {tool} not found in extension"


def test_extension_registers_command() -> None:
    ext = (SRC / "index.ts").read_text(encoding="utf-8")
    assert 'registerCommand("teammate"' in ext


def test_extension_handles_worktree_isolation() -> None:
    """Extension should create/cleanup worktrees when isolation is requested."""
    ext = (SRC / "index.ts").read_text(encoding="utf-8")
    assert "createWorktree" in ext
    assert "cleanupWorktree" in ext
    assert 'isolation === "worktree"' in ext


def test_before_agent_start_injects_guidance() -> None:
    """Extension should inject teammate guidance via before_agent_start."""
    ext = (SRC / "index.ts").read_text(encoding="utf-8")
    assert 'pi.on("before_agent_start"' in ext
    assert "TEAMMATE_GUIDANCE" in ext
    assert "systemPrompt" in ext


def test_state_module_exports() -> None:
    """State module should export all required functions."""
    state = (SRC / "state.ts").read_text(encoding="utf-8")
    expected_exports = [
        "registerTeammate",
        "listTeammates",
        "getTeammate",
        "sendMessage",
        "readMailbox",
        "createTask",
        "updateTaskStatus",
        "listTasks",
        "persistState",
        "tryRestoreState",
    ]
    for exp in expected_exports:
        assert f"export function {exp}" in state, f"Export {exp} not found in state.ts"


def test_types_module_exports_schemas() -> None:
    """Types module should export all typebox schemas."""
    types = (SRC / "types.ts").read_text(encoding="utf-8")
    expected_schemas = [
        "TeammateRegisterParams",
        "TeammateSendParams",
        "TeammateReadMailboxParams",
        "TeammateAssignTaskParams",
        "TeammateListTasksParams",
        "TeammateUpdateTaskParams",
        "TeammateBroadcastParams",
        "TeammateSpawnParams",
        "TeammateTaskDepsParams",
    ]
    for schema in expected_schemas:
        assert f"export const {schema}" in types, f"Schema {schema} not found in types.ts"


def test_types_define_task_dependencies_and_spawn() -> None:
    """Task type should model dependency graph and spawn status."""
    types = (SRC / "types.ts").read_text(encoding="utf-8")
    assert "blocks: string[]" in types
    assert "blockedBy: string[]" in types
    assert "spawn" in types
    assert "running" in types


def test_types_define_teammate_liveness_and_isolation() -> None:
    """Teammate type should model liveness; spawn params should support worktree isolation."""
    types = (SRC / "types.ts").read_text(encoding="utf-8")
    # Liveness fields on the teammate record.
    assert "status" in types and "idle" in types
    assert "lastActiveAt" in types
    assert "currentTaskId" in types
    # Worktree isolation option on spawn params.
    assert "isolation" in types
    assert "\"worktree\"" in types


def test_types_define_usage_and_timeout() -> None:
    """Spawn info should carry worker usage; spawn params should support timeout."""
    types = (SRC / "types.ts").read_text(encoding="utf-8")
    assert "totalTokens" in types
    assert "cost" in types
    assert "usage" in types
    assert "timedOut" in types
    assert "timeoutMs" in types


def test_state_module_exports_liveness_helpers() -> None:
    """State module should export teammate liveness transitions."""
    state = (SRC / "state.ts").read_text(encoding="utf-8")
    for exp in ["markTeammateRunning", "markTeammateIdle"]:
        assert f"export function {exp}" in state, f"Export {exp} not found in state.ts"


def test_spawner_supports_json_mode_usage_and_timeout() -> None:
    """Spawner should parse JSON-mode usage and kill workers on timeout."""
    spawner = (SRC / "spawner.ts").read_text(encoding="utf-8")
    assert '"--mode", "json"' in spawner
    assert "parseWorkerOutput" in spawner
    assert "timeoutMs" in spawner
    assert "timedOut" in spawner


def test_extension_surfaces_usage_and_timeout() -> None:
    """Extension should surface worker usage on tasks and handle timeouts."""
    ext = (SRC / "index.ts").read_text(encoding="utf-8")
    assert "timeoutMs" in ext
    assert "usage" in ext
    assert "timedOut" in ext
    assert "Worker timed out" in ext


def test_state_module_exports_spawn_and_deps() -> None:
    """State module should export dependency and spawn helpers."""
    state = (SRC / "state.ts").read_text(encoding="utf-8")
    for exp in ["setTaskDeps", "isTaskReady", "setSpawnInfo"]:
        assert f"export function {exp}" in state, f"Export {exp} not found in state.ts"


def test_spawner_module_exports() -> None:
    """Spawner module should export the CLI resolver and worker spawner."""
    spawner = (SRC / "spawner.ts").read_text(encoding="utf-8")
    assert "export function resolvePiCli" in spawner
    assert "export function spawnPiWorker" in spawner
    assert "child_process" in spawner


def test_worktree_module_exports() -> None:
    """Worktree module should export setup and cleanup helpers."""
    wt = (SRC / "worktree.ts").read_text(encoding="utf-8")
    assert "export function createWorktree" in wt
    assert "export function cleanupWorktree" in wt
    assert "captureWorktreeDiff" in wt


def test_session_persistence_events() -> None:
    """Extension should hook into session lifecycle for persistence."""
    ext = (SRC / "index.ts").read_text(encoding="utf-8")
    assert 'pi.on("session_start"' in ext
    assert 'pi.on("session_shutdown"' in ext
    assert 'pi.on("turn_end"' in ext


def test_skill_has_no_openai_urls() -> None:
    """SKILL.md should not contain OpenAI API URLs (they're in .memory/)."""
    skill = (SKILLS / "using-teammate" / "SKILL.md").read_text(encoding="utf-8")
    assert "developers.openai.com" not in skill
    assert "platform.openai.com" not in skill
    assert "api.chatgpt.com" not in skill


def test_memory_reference_has_no_emojis() -> None:
    for path in [
        SKILLS / "using-teammate" / "SKILL.md",
        PACKAGE / "README.md",
        MEMORY / "MEMORY.md",
    ]:
        text = path.read_text(encoding="utf-8")
        for char in text:
            if ord(char) > 0x1F600 and ord(char) < 0x1F9FF:
                raise AssertionError(f"Emoji found in {path.name}: {char}")

def test_session_start_sets_status_unconditionally() -> None:
    """Footer status must be (re)evaluated at session start — not gated on a
    restored snapshot. getSummary() decides whether anything is shown."""
    ext = (SRC / "index.ts").read_text(encoding="utf-8")
    # session_start must call tryRestoreState AND setStatus unconditionally.
    assert 'pi.on("session_start"' in ext
    assert 'tryRestoreState(ctx.sessionManager)' in ext
    assert "setupTeamWidget(ctx)" in ext
    assert "refreshTeamUI(ctx)" in ext
    assert 'setStatus("teammate", undefined)' in ext
    # The status must NOT be wrapped in an "if (restored)" gate.
    start = ext.index('pi.on("session_start"')
    segment = ext[start:start + 600]
    assert "if (restored)" not in segment, "session_start must not gate the status on restore"


def test_get_summary_hides_empty_team() -> None:
    """getSummary() must return undefined (clears the footer) when no teammate
    is registered — an all-zero line must never be shown on entry."""
    state = (SRC / "state.ts").read_text(encoding="utf-8")
    assert "getSummary" in state
    assert "teammateCount" in state
    assert "return undefined" in state
    assert "if (teammateCount === 0) return undefined;" in state
    # The canonical footer format is still produced when a teammate exists.
    assert "teammate(s)" in state
    assert "unread message(s)" in state
    assert "active task(s)" in state
    assert "total" in state


# ── Autonomous worker (no parent polling) ──────────────────────────

def test_spawner_builds_autonomous_prompt() -> None:
    """Workers get a guardian-loop prompt: watch mailbox, decide when to close."""
    spawner = (SRC / "spawner.ts").read_text(encoding="utf-8")
    assert "buildAutonomousPrompt" in spawner
    assert "FULLY AUTONOMOUS" in spawner
    assert "decide when to close" in spawner
    assert "mailboxes" in spawner
    assert "sleep" in spawner
    assert "stateFile" in spawner


def test_spawner_has_blocking_variant() -> None:
    """The parent awaits the worker's OWN exit — no sleep-polling."""
    spawner = (SRC / "spawner.ts").read_text(encoding="utf-8")
    assert "spawnPiWorkerBlocking" in spawner
    assert "SpawnWorkerResult" in spawner


def test_spawner_appends_bash_tool_for_polling() -> None:
    """Autonomous workers must get bash appended when a tool allowlist omits it."""
    spawner = (SRC / "spawner.ts").read_text(encoding="utf-8")
    assert '"bash"' in spawner
    assert "includes(\"bash\")" in spawner


def test_statefile_module_exports() -> None:
    """Shared state file module must exist with session-scoped paths + atomic writes."""
    sf = (SRC / "statefile.ts").read_text(encoding="utf-8")
    for exp in ("sessionStateDir", "stateFilePath", "writeStateFile", "readStateFile"):
        assert f"export function {exp}" in sf, f"Export {exp} not found in statefile.ts"
    assert "renameSync" in sf  # atomic tmp + rename
    assert "teammate" in sf


def test_spawn_param_has_background_flag() -> None:
    """teammate_spawn defaults to blocking; background=true fires and forgets."""
    types = (SRC / "types.ts").read_text(encoding="utf-8")
    assert "background" in types
    assert "block until the worker autonomously closes" in types


def test_extension_uses_shared_state_file() -> None:
    """teammate_spawn must publish the board to the shared state file and merge
    worker-written replies/task updates back after the worker closes."""
    ext = (SRC / "index.ts").read_text(encoding="utf-8")
    assert "stateFilePath" in ext
    assert "writeStateFile(stateFile, getState())" in ext
    assert "applyStateFile(stateFile, readStateFile)" in ext
    assert "buildAutonomousPrompt" in ext
    assert "spawnPiWorkerBlocking" in ext
    assert "params.background" in ext
    assert "Worker final report" in ext


def test_state_module_exports_apply_state_file() -> None:
    """State module must merge worker-written changes back into memory."""
    state = (SRC / "state.ts").read_text(encoding="utf-8")
    assert "export function applyStateFile" in state
    assert "messageCounter = Math.max" in state


# ── Assignment notification consumption (B) ────────────────────────

def test_state_module_marks_task_notifications_read() -> None:
    """State module must expose markTaskNotificationsRead for assignment notifications."""
    state = (SRC / "state.ts").read_text(encoding="utf-8")
    assert "export function markTaskNotificationsRead" in state
    assert "msg.taskId === taskId" in state


def test_spawn_consumes_assignment_notification() -> None:
    """teammate_spawn must mark the task's assignment notification read before spawning."""
    ext = (SRC / "index.ts").read_text(encoding="utf-8")
    assert "markTaskNotificationsRead(params.taskId)" in ext
    spawn_segment = ext[ext.index("const stateFile = stateFilePath"):ext.index("const stateFile = stateFilePath") + 400]
    assert "markTaskNotificationsRead(params.taskId)" in spawn_segment
    assert "writeStateFile(stateFile, getState())" in spawn_segment


def test_update_task_consumes_notification_on_start() -> None:
    """teammate_update_task must consume the notification when a task starts (in_progress)."""
    ext = (SRC / "index.ts").read_text(encoding="utf-8")
    assert 'params.status === "in_progress"' in ext
    assert "markTaskNotificationsRead" in ext


# ── Management: remove / cleanup / reset / /teammate menu ──────────

def test_state_module_exports_management_functions() -> None:
    """State module must expose removeTeammate, removeTask, pruneFinishedTasks, resetBoard."""
    state = (SRC / "state.ts").read_text(encoding="utf-8")
    for exp in ("removeTeammate", "removeTask", "pruneFinishedTasks", "resetBoard"):
        assert f"export function {exp}" in state, f"Export {exp} not found in state.ts"


def test_management_tools_registered() -> None:
    """Extension must register teammate_remove, teammate_cleanup, teammate_reset."""
    ext = (SRC / "index.ts").read_text(encoding="utf-8")
    for tool in ("teammate_remove", "teammate_cleanup", "teammate_reset"):
        assert f'name: "{tool}"' in ext, f"Tool {tool} not found in extension"


def test_teammate_console_is_not_a_select_menu() -> None:
    """The /teammate console is a full-screen command, not a ui.select menu."""
    ext = (SRC / "index.ts").read_text(encoding="utf-8")
    assert 'registerCommand("teammate"' in ext
    assert 'openTeamConsole' in ext
    assert '"View team"' not in ext


def test_persistent_widget_is_display_only() -> None:
    """The widget is passive (no onTerminalInput) — interaction lives in the console."""
    ext = (SRC / "index.ts").read_text(encoding="utf-8")
    assert 'setWidget("teammate"' in ext
    assert "onTerminalInput" not in ext, "no global key interception"
    assert "setupTeamWidget" in ext
    assert "refreshTeamUI" in ext
    assert "panelRows" in ext
    assert "openTeamConsole" in ext
    assert "TEAM_COLORS" in ext
    assert "PANEL_IDLE_COLLAPSE_MS" in ext


def test_console_owns_navigation_keys() -> None:
    """Inside the full-screen console, ↑/↓/Enter are safe (the console owns input).
    No shift-key hacks, no global interception."""
    ext = (SRC / "index.ts").read_text(encoding="utf-8")
    assert "openTeamConsole" in ext
    assert "\\u001bOA" in ext, "console matches arrow sequences"
    assert "onTerminalInput" not in ext, "no global input listener"
    assert "shiftUp" not in ext and "shiftDown" not in ext, "no shift-key matching"
    assert "buildTeammateDetail" in ext
    assert "killWorker" in ext
    assert "getEditorText" not in ext, "no global editor probing"
    assert "consume: true" not in ext, "no global consumption"


def test_no_footer_status_anymore() -> None:
    """The footer status line is gone; the panel shows no aggregate summary row."""
    ext = (SRC / "index.ts").read_text(encoding="utf-8")
    assert 'setStatus("teammate", getSummary())' not in ext
    assert 'setStatus("teammate", undefined)' in ext
    assert "unreadTotal" not in ext, "team-wide unread/task aggregate removed from the panel"
    assert "active task(s)" not in ext, "summary row removed from the panel"


def test_agent_page_shows_special_sections() -> None:
    """Unread messages + tasks appear as special sections on the agent's detail view."""
    ext = (SRC / "index.ts").read_text(encoding="utf-8")
    assert "buildTeammateDetail" in ext
    assert "unread message(s)" in ext
    assert "task(s)" in ext
    assert "mailbox" in ext


def test_leader_inbox_supported() -> None:
    """Teammates can message the leader: inbox row in panel, full-page inbox view,
    and teammate_read_mailbox accepts name=agent without a registered teammate."""
    ext = (SRC / "index.ts").read_text(encoding="utf-8")
    assert "buildPanelRows" in ext
    assert '"inbox"' in ext
    assert "buildInboxContent" in ext
    assert 'name !== "agent"' in ext, "read_mailbox must special-case the leader inbox"
    assert "message(s) to you" in ext
    spawner = (SRC / "spawner.ts").read_text(encoding="utf-8")
    assert "mailboxes[\"agent\"]" in spawner, "workers must be told they can message the leader"


def test_console_is_fullscreen_not_overlay() -> None:
    """The console is a full-screen custom component (no overlay popups)."""
    ext = (SRC / "index.ts").read_text(encoding="utf-8")
    assert "openTeamConsole" in ext
    assert "{ overlay: true }" not in ext, "no overlay popups — console is full-screen"
    assert "panelPageOpen" not in ext, "no page-open input flag needed"


def test_panel_collapses_idle_team() -> None:
    """Idle rows collapse to a summary after 30s; any key expands."""
    ext = (SRC / "index.ts").read_text(encoding="utf-8")
    assert "isPanelCollapsed" in ext
    assert "scheduleIdleCollapse" in ext
    assert "Team idle" in ext
    assert "30_000" in ext


def test_spawner_exports_kill_worker() -> None:
    """Spawner must expose killWorker and register workers by teammate name."""
    spawner = (SRC / "spawner.ts").read_text(encoding="utf-8")
    assert "export function killWorker" in spawner
    assert "workers.set" in spawner
    assert "workerName" in spawner


def test_spawn_passes_worker_name() -> None:
    """teammate_spawn must register the child under the teammate name so the panel can interrupt it."""
    ext = (SRC / "index.ts").read_text(encoding="utf-8")
    assert "workerName: teammate.name" in ext


def test_statefile_exports_cleanup_helpers() -> None:
    """State file module must export expired-dir sweep and session-dir removal."""
    sf = (SRC / "statefile.ts").read_text(encoding="utf-8")
    for exp in ("stateDirsRoot", "cleanupExpiredStateDirs", "removeSessionStateDir"):
        assert f"export function {exp}" in sf, f"Export {exp} not found in statefile.ts"
    assert "rmSync" in sf
    assert "mtimeMs" in sf


def test_session_lifecycle_cleans_state_dirs() -> None:
    """session_shutdown must drop the session's shared state dir; session_start sweeps expired ones."""
    ext = (SRC / "index.ts").read_text(encoding="utf-8")
    assert "removeSessionStateDir" in ext
    assert "cleanupExpiredStateDirs" in ext
    assert "session_shutdown" in ext
    assert "session_start" in ext


def test_remove_refuses_running_worker() -> None:
    """removeTeammate must refuse while the teammate is running unless force."""
    state = (SRC / "state.ts").read_text(encoding="utf-8")
    assert 'status === "running"' in state
    assert "force" in state


def test_reset_refuses_running_worker() -> None:
    """resetBoard must refuse while any teammate is running."""
    state = (SRC / "state.ts").read_text(encoding="utf-8")
    assert "is running a worker" in state
    assert "removedTeammates" in state


# ── Esc CSI-u, leader = main session, inline reply, display role ──

def test_escape_matches_csi_u_form() -> None:
    """Esc arrives as bare \\x1b or as CSI-u \\x1b[27u under the Kitty protocol — both must close pages."""
    ext = (SRC / "index.ts").read_text(encoding="utf-8")
    assert "isEscapeKey" in ext
    assert "\\u001b\\[27" in ext, "CSI-u Escape (\\x1b[27u) regex must be present"


def test_reply_is_inline_not_ui_input() -> None:
    """Replying happens inside the full page (inline buffer), not via ctx.ui.input
    (which raced with the full-screen custom component)."""
    ext = (SRC / "index.ts").read_text(encoding="utf-8")
    assert "replyMode" in ext
    assert "replyBuffer += data" in ext, "inline reply input accumulates typed chars"
    assert "ctx.ui.input" not in ext, "reply must not use ctx.ui.input inside the console"


def test_leader_is_main_session() -> None:
    """The team leader is the main session: registering a team-leader is rejected,
    and assign/broadcast no longer require a registered team-leader."""
    ext = (SRC / "index.ts").read_text(encoding="utf-8")
    assert 'params.role === "team-leader"' in ext, "register must reject team-leader"
    assert "The team leader is the current main session" in ext
    assert "getTeamLeaders" not in ext, "no team-leader gate in assign/broadcast anymore"


def test_worker_displays_as_teammate() -> None:
    """A registered worker is shown as (teammate), not (worker)."""
    ext = (SRC / "index.ts").read_text(encoding="utf-8")
    assert "displayRole" in ext
    assert 'return role === "worker" ? "teammate" : role;' in ext


# ── Model switching must keep working (panel must not hijack pi's keys) ──

def test_no_global_interception_means_no_model_conflict() -> None:
    """The redesign removes onTerminalInput entirely — the console owns input via
    ctx.ui.custom, so pi's model selector / history / dialogs can never be hijacked."""
    ext = (SRC / "index.ts").read_text(encoding="utf-8")
    assert "onTerminalInput" not in ext, "no global input listener at all"
    assert "handlePanelInput" not in ext
    assert "PANEL_ENGAGE_MS" not in ext
    assert "panelEngagedAt" not in ext
    assert "openTeamConsole" in ext


# ── Full conversation view (bidirectional) ────────────────────────

def test_state_exports_list_all_messages() -> None:
    """State must expose every message across all mailboxes (for transcripts)."""
    state = (SRC / "state.ts").read_text(encoding="utf-8")
    assert "export function listAllMessages" in state
    assert "Object.values(state.mailboxes).flat()" in state


def test_teammate_detail_shows_all_conversations() -> None:
    """Selecting a teammate shows ALL its conversations: messages received (←)
    and messages it sent (→), merged and sorted, plus the special sections."""
    ext = (SRC / "index.ts").read_text(encoding="utf-8")
    assert "all conversations" in ext
    assert "m.from === name" in ext, "outgoing messages must be included"
    assert 'sent ? "→" : "←"' in ext, "direction markers for sent/received"
    assert "listAllMessages()" in ext
    # Special sections stay.
    assert "unread message(s)" in ext
    assert "task(s)" in ext


def test_teammate_detail_shows_full_running_content() -> None:
    """Selecting an agent must show its full running content: task description,
    the worker's final report (spawn.stdout), stderr, and usage — not just a
    one-line task status."""
    ext = (SRC / "index.ts").read_text(encoding="utf-8")
    assert "buildTaskSection" in ext, "a dedicated task-section renderer must exist"
    assert "t.description" in ext, "task description must be rendered"
    assert "spawn.stdout" in ext, "worker final report (stdout) must be rendered"
    assert "spawn.stderr" in ext, "worker stderr must be rendered"
    assert "spawn.usage" in ext, "worker usage must be rendered"
    assert "flatMap(buildTaskSection)" in ext, "task section must render full content per task"


# ── Live state merge + btw-style console ──────────────────────────

def test_live_poll_merges_worker_writes() -> None:
    """While any teammate runs, poll the shared state file and merge worker
    writes back into memory so mid-run progress is visible live."""
    ext = (SRC / "index.ts").read_text(encoding="utf-8")
    assert "ensureLivePoll" in ext
    assert "LIVE_POLL_MS" in ext
    assert "setInterval" in ext
    assert "applyStateFile(liveStateFile!, readStateFile)" in ext
    assert "liveStateFile = stateFilePath(" in ext, "state file path captured at session_start"


def test_console_matches_btw_style() -> None:
    """The /teammate console uses the @fradser/pi-btw popup style language:
    top/bottom borders, accent header, dim footer hints, same color callbacks."""
    ext = (SRC / "index.ts").read_text(encoding="utf-8")
    assert 'accent: (s: string) => theme.fg("accent", s)' in ext
    assert 'border: (s: string) => theme.fg("border", s)' in ext
    assert '"─".repeat(Math.max(1, width))' in ext
    assert "teammate  " in ext, "accent header prefix like btw"
    assert "… " in ext, "more-lines hint like btw"
    assert "esc back" in ext or "esc interrupt" in ext


# ── Model update ───────────────────────────────────────────────────

def test_update_model_tool_registered() -> None:
    """Extension must register teammate_update_model and call the state updater."""
    ext = (SRC / "index.ts").read_text(encoding="utf-8")
    assert 'name: "teammate_update_model"' in ext
    assert "updateTeammateModel(params.name, params.model)" in ext
    assert "next spawn" in ext


def test_state_exports_update_teammate_model() -> None:
    """State module must expose updateTeammateModel (no-op while running is fine — applies next spawn)."""
    state = (SRC / "state.ts").read_text(encoding="utf-8")
    assert "export function updateTeammateModel" in state
    assert "teammate.model = model" in state


# ── Inbox alert: content preview + read sticks ────────────────────

def test_inbox_alert_shows_message_content() -> None:
    """The leader-inbox alert must preview the actual message (from: subject — body),
    not just a count, in both the widget and the console."""
    ext = (SRC / "index.ts").read_text(encoding="utf-8")
    assert "inboxPreview" in ext
    assert "message(s) to you —" in ext, "alert shows a content preview"
    assert "latest.from" in ext


def test_apply_state_file_preserves_read_flag() -> None:
    """Merging worker file writes back must NOT un-read a message the leader
    already consumed — otherwise the alert resurrects after reading."""
    state = (SRC / "state.ts").read_text(encoding="utf-8")
    assert "if (prior?.read) m.read = true;" in state
    assert "The parent owns read state" in state


# ── Tool discoverability + output truncation ──────────────────────

def test_all_tools_have_prompt_snippets() -> None:
    """Every teammate tool must surface in the Available-tools summary."""
    ext = (SRC / "index.ts").read_text(encoding="utf-8")
    assert ext.count("promptSnippet:") >= 14


def test_worker_output_is_truncated() -> None:
    """Worker/task/mailbox output must be truncated to the built-in tool-output limits."""
    ext = (SRC / "index.ts").read_text(encoding="utf-8")
    assert "truncateTail" in ext
    assert "DEFAULT_MAX_BYTES" in ext
    assert "cap(outcome.result.stdout)" in ext
    assert "cap(task.result)" in ext
    assert "cap(msg.body)" in ext


# ── Read status + leader receipt ──────────────────────────────────

def test_read_status_markers_shown() -> None:
    """Messages carry read/unread markers in the inbox and the conversation view."""
    ext = (SRC / "index.ts").read_text(encoding="utf-8")
    assert "received" in ext, "inbox shows received/unread label"
    assert "✓ leader received" in ext, "sender sees the leader read receipt"
    assert "○ leader pending" in ext


def test_read_receipt_synced_to_file() -> None:
    """Reading the leader inbox (or via teammate_read_mailbox) writes the read
    flags back to the shared state file so the sender sees them."""
    ext = (SRC / "index.ts").read_text(encoding="utf-8")
    assert "syncReadFlagsToFile" in ext
    assert "writeStateFile(liveStateFile, fresh)" in ext
    assert "syncReadFlagsToFile();" in ext


def test_finish_writes_merged_state_back_to_file() -> None:
    """On worker exit the merged board (with final read receipts) is written back
    to the shared file so the sender sees the leader read its messages."""
    ext = (SRC / "index.ts").read_text(encoding="utf-8")
    assert "writeStateFile(stateFile, getState())" in ext
    assert "read receipts" in ext


# ── Leader→worker messages reach the shared file ──────────────────

def test_send_publishes_to_state_file() -> None:
    """teammate_send/broadcast/assign/update_task must write the board to the
    shared state file so running workers see leader-side messages (the ping
    never arrived before — only the pre-spawn snapshot was in the file)."""
    ext = (SRC / "index.ts").read_text(encoding="utf-8")
    assert "publishToStateFile" in ext
    assert "writeStateFile(liveStateFile, getState())" in ext
    # wired into the message + task mutation paths
    assert ext.count("publishToStateFile();") >= 4
