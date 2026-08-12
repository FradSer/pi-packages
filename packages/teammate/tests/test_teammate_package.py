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
    assert "@earendil-works/pi-coding-agent" in manifest["peerDependencies"]


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
    assert "teammate-status" in ext


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