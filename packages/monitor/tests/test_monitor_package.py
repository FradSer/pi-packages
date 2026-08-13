from __future__ import annotations

import json
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
SKILLS = PACKAGE / "skills"
SRC = PACKAGE / "src"


def frontmatter(text: str) -> str:
    parts = text.split("---", 2)
    assert len(parts) == 3, "SKILL.md must have YAML frontmatter delimited by ---"
    return parts[1]


def test_manifest_declares_native_pi_package() -> None:
    manifest = json.loads((PACKAGE / "package.json").read_text(encoding="utf-8"))
    assert "pi-package" in manifest["keywords"]
    assert manifest["pi"]["skills"] == ["./skills"]
    assert manifest["pi"]["extensions"] == ["./src/index.ts"]


def test_extension_entry_points_exist() -> None:
    assert (SRC / "index.ts").is_file(), "Extension entry point src/index.ts is missing"
    assert (SRC / "monitor.ts").is_file(), "Monitor manager src/monitor.ts is missing"
    assert (SRC / "types.ts").is_file(), "Types module src/types.ts is missing"


def test_extension_declares_peer_dependency() -> None:
    manifest = json.loads((PACKAGE / "package.json").read_text(encoding="utf-8"))
    assert "peerDependencies" in manifest
    # Every imported core package must be listed as a peer dependency (packages.md).
    for pkg in ("@earendil-works/pi-coding-agent", "@earendil-works/pi-tui", "typebox"):
        assert pkg in manifest["peerDependencies"], f"{pkg} missing from peerDependencies"
        assert manifest["peerDependencies"][pkg] == "*"


def test_single_skill_using_monitor_is_present() -> None:
    skills = sorted(SKILLS.glob("*/SKILL.md"))
    assert [skill.parent.name for skill in skills] == ["using-monitor"]


def test_skill_has_valid_frontmatter() -> None:
    skill = SKILLS / "using-monitor" / "SKILL.md"
    metadata = frontmatter(skill.read_text(encoding="utf-8"))
    assert "name:" in metadata
    assert "description:" in metadata
    assert "name: using-monitor" in metadata


def test_skill_is_usage_guide() -> None:
    skill = (SKILLS / "using-monitor" / "SKILL.md").read_text(encoding="utf-8")
    assert "monitor_start" in skill
    assert "monitor_list" in skill
    assert "monitor_stop" in skill


def test_claude_only_artifacts_are_not_shipped() -> None:
    assert not (PACKAGE / ".claude-plugin").exists()
    assert not list(PACKAGE.rglob("plugin.json"))
    content = "\n".join(path.read_text(encoding="utf-8") for path in PACKAGE.rglob("*.md"))
    for forbidden in (
        "allowed-tools:",
        "user-invocable:",
        "CLAUDE_PLUGIN_ROOT",
        "AskUserQuestion",
    ):
        assert forbidden not in content


def test_no_emojis() -> None:
    for path in [SKILLS / "using-monitor" / "SKILL.md", PACKAGE / "README.md"]:
        text = path.read_text(encoding="utf-8")
        for char in text:
            if 0x1F600 < ord(char) < 0x1F9FF:
                raise AssertionError(f"Emoji found in {path.name}: {char}")


def test_extension_registers_tools() -> None:
    ext = (SRC / "index.ts").read_text(encoding="utf-8")
    for tool in ("monitor_start", "monitor_list", "monitor_stop"):
        assert f'name: "{tool}"' in ext, f"Tool {tool} not found in extension"


def test_extension_registers_command() -> None:
    ext = (SRC / "index.ts").read_text(encoding="utf-8")
    assert 'registerCommand("monitor"' in ext


def test_before_agent_start_injects_guidance() -> None:
    ext = (SRC / "index.ts").read_text(encoding="utf-8")
    assert 'pi.on("before_agent_start"' in ext
    assert "MONITOR_GUIDANCE" in ext
    assert "systemPrompt" in ext


def test_types_module_exports_schemas() -> None:
    types = (SRC / "types.ts").read_text(encoding="utf-8")
    for schema in ("MonitorStartParams", "MonitorStopParams", "EmptyParams"):
        assert f"export const {schema}" in types, f"Schema {schema} not found in types.ts"


def test_monitor_manager_exports() -> None:
    monitor = (SRC / "monitor.ts").read_text(encoding="utf-8")
    assert "export class MonitorManager" in monitor
    assert "DEFAULT_TIMEOUT_MS" in monitor
    assert "MAX_TIMEOUT_MS" in monitor
    assert "BATCH_WINDOW_MS" in monitor
    assert "MAX_EVENTS" in monitor


def test_monitor_spawns_background_process() -> None:
    monitor = (SRC / "monitor.ts").read_text(encoding="utf-8")
    assert "node:child_process" in monitor
    assert "spawn(" in monitor
    assert "shell: true" in monitor
    assert "detached: true" in monitor


def test_monitor_kills_process_group() -> None:
    monitor = (SRC / "monitor.ts").read_text(encoding="utf-8")
    assert "process.kill(-pid, sig)" in monitor
    assert '"SIGTERM"' in monitor
    assert '"SIGKILL"' in monitor
    assert "KILL_GRACE_MS" in monitor


def test_monitor_kills_process_on_stop_timeout_and_event_limit() -> None:
    """killTree must run on stop, timeout, and event cap — not just clear state."""
    monitor = (SRC / "monitor.ts").read_text(encoding="utf-8")
    assert monitor.count("this.killTree(monitor.child)") >= 3


def test_stdout_handlers_are_gated_on_running_status() -> None:
    """handleStdout and flush must drop output once a monitor is finalized."""
    monitor = (SRC / "monitor.ts").read_text(encoding="utf-8")
    assert monitor.count('monitor.status !== "running") return') >= 2


def test_timeout_drains_buffered_lines_before_finalize() -> None:
    """The timeout path must flush final buffered stdout, not drop it."""
    monitor = (SRC / "monitor.ts").read_text(encoding="utf-8")
    timeout_segment = monitor[monitor.index('this.finalize(monitor, "timeout")') - 200:monitor.index('this.finalize(monitor, "timeout")')]
    assert "drainBuffer" in timeout_segment
    assert "this.flush(monitor)" in timeout_segment


def test_monitor_batches_output_lines() -> None:
    monitor = (SRC / "monitor.ts").read_text(encoding="utf-8")
    assert "BATCH_WINDOW_MS" in monitor
    assert "scheduleFlush" in monitor
    assert "pending" in monitor


def test_monitor_caps_events() -> None:
    monitor = (SRC / "monitor.ts").read_text(encoding="utf-8")
    assert "MAX_EVENTS" in monitor
    assert '"event_limit"' in monitor


def test_monitor_has_timeout_and_persistent() -> None:
    monitor = (SRC / "monitor.ts").read_text(encoding="utf-8")
    assert "timeoutTimer" in monitor
    assert '"timeout"' in monitor
    assert "persistent" in monitor


def test_extension_streams_events_via_send_message() -> None:
    ext = (SRC / "index.ts").read_text(encoding="utf-8")
    assert "pi.sendMessage" in ext
    assert 'customType: "monitor"' in ext
    assert 'deliverAs: "steer"' in ext
    assert "triggerTurn: true" in ext


def test_extension_cleans_up_on_shutdown() -> None:
    ext = (SRC / "index.ts").read_text(encoding="utf-8")
    assert 'pi.on("session_shutdown"' in ext
    assert "stopAllOnShutdown" in ext


def test_manual_stop_sends_no_notification() -> None:
    ext = (SRC / "index.ts").read_text(encoding="utf-8")
    assert 'reason === "stopped"' in ext
    assert "agent-initiated, no notification needed" in ext


def test_stderr_is_captured_not_streamed() -> None:
    monitor = (SRC / "monitor.ts").read_text(encoding="utf-8")
    assert "stderr" in monitor
    assert 'monitor.stderr += chunk.toString()' in monitor
    assert "handleStdout" in monitor


def test_match_param_in_schema() -> None:
    types = (SRC / "types.ts").read_text(encoding="utf-8")
    assert "match" in types
    assert "regex" in types
    assert "suppressed" in types


def test_monitor_filters_non_matching_lines() -> None:
    monitor = (SRC / "monitor.ts").read_text(encoding="utf-8")
    assert "matcher" in monitor
    assert "monitor.skipped += 1" in monitor
    assert "monitor.matcher.test(line)" in monitor


def test_finalize_reports_suppressed_lines() -> None:
    monitor = (SRC / "monitor.ts").read_text(encoding="utf-8")
    assert "non-matching stdout line(s)" in monitor
    assert "monitor.skipped" in monitor


def test_widget_shows_monitor_count_below_editor() -> None:
    ext = (SRC / "index.ts").read_text(encoding="utf-8")
    assert 'setWidget("monitor"' in ext
    assert 'placement: "belowEditor"' in ext
    assert "monitor(s) running" in ext


def test_widget_is_display_only_no_key_interception() -> None:
    ext = (SRC / "index.ts").read_text(encoding="utf-8")
    assert "onTerminalInput" not in ext
    assert "setupMonitorWidget" in ext
    assert "requestRender" in ext


def test_console_owns_input_via_custom() -> None:
    ext = (SRC / "index.ts").read_text(encoding="utf-8")
    assert "openMonitorConsole" in ext
    assert "ctx.ui.custom" in ext
    assert "handleInput" in ext


def test_guidance_teaches_match_and_noise_avoidance() -> None:
    ext = (SRC / "index.ts").read_text(encoding="utf-8")
    assert "MONITOR_GUIDANCE" in ext
    assert "Avoid noise" in ext
    assert "match=" in ext


def test_tools_have_prompt_snippets() -> None:
    """Tools must surface in the Available-tools summary via promptSnippet."""
    ext = (SRC / "index.ts").read_text(encoding="utf-8")
    assert ext.count("promptSnippet:") >= 3
    assert "Run a shell command in the background and stream matching stdout lines" in ext


def test_monitor_start_has_prompt_guidelines() -> None:
    """monitor_start must teach usage + noise avoidance via promptGuidelines."""
    ext = (SRC / "index.ts").read_text(encoding="utf-8")
    assert "promptGuidelines:" in ext
    assert "Use monitor_start to watch logs, deploys, CI runs, or test output" in ext
    assert "match=" in ext
