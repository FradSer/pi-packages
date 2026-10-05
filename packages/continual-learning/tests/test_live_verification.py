from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import live_smoke


def test_live_prepare_isolates_authentication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source-agent"
    source.mkdir()
    original = {
        "auth.json": json.dumps({"synthetic": {"type": "api_key", "key": "synthetic-source-only"}}),
        "models.json": json.dumps({"providers": {"synthetic": {"models": []}}}),
        "memory.json": json.dumps({"provider": "synthetic", "model": "fixture"}),
    }
    for name, content in original.items():
        (source / name).write_text(content)
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(source))
    base = tmp_path / "live"
    base.mkdir()

    _, agent, _ = live_smoke.prepare(base, False)

    for name in ("auth.json", "models.json"):
        child_file = agent / name
        assert not child_file.is_symlink(), f"{name} must not link writable source configuration"
        assert child_file.stat().st_mode & 0o777 == 0o600
        assert child_file.read_text() == original[name]
    (agent / "auth.json").write_text('{"syntheticRefresh":true}')
    assert {name: (source / name).read_text() for name in original} == original


def test_live_learning_requires_actual_project_rule(monkeypatch: pytest.MonkeyPatch) -> None:
    # The signature has to track the real one: verify_learning now asks for
    # seeded Memory and an enabled AGENTS.md phase, and a test double with the
    # old signature fails on the call rather than on what it is meant to test.
    def prepare(base: Path, auto_memory: bool, *, seed_memory: bool = False, agents_md: bool = False, jev_enabled: bool | None = None) -> tuple[Path, Path, Path]:
        project, agent = base / "project", base / "agent"
        project.mkdir()
        memory = agent / "memory" / "scope"
        memory.mkdir(parents=True)
        (memory / "preference.md").write_text("Prefer concise updates.")
        runs = agent / "memory" / "runs" / "scope" / "run"
        runs.mkdir(parents=True)
        (runs / "learning-pipeline-receipt.json").write_text(json.dumps({
            "operations": 2,
            "attempts": [
                {"phase": "memory", "outcome": "applied", "operations": 1},
                {"phase": "harness", "outcome": "rejected", "operations": 0},
            ],
        }))
        return project, agent, base / "unused.ts"

    monkeypatch.setattr(live_smoke, "prepare", prepare)
    monkeypatch.setattr(live_smoke, "run_pi", lambda *args: {"notifications": "synthetic missing-rule diagnosis"})
    monkeypatch.setattr(live_smoke.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(stdout='{"blocked":"block","allowed":true}'))
    with pytest.raises(AssertionError, match="project harness"):
        live_smoke.verify_learning()


def test_live_acceptance_binds_canonical_agents_target_and_exact_blocked_call(tmp_path: Path) -> None:
    # Given a receipt path expressed through an alias and a transcript with an
    # unrelated failed Bash call, neither may satisfy the acceptance check.
    target = tmp_path / "project" / "AGENTS.md"
    alias = tmp_path / "alias"
    target.parent.mkdir(parents=True)
    target.write_text("instructions")
    alias.symlink_to(target.parent, target_is_directory=True)
    assert live_smoke.same_canonical_path(alias / "AGENTS.md", target)

    requested = "retired-smoke-compiler build"
    messages = [
        {"role": "assistant", "content": [{"type": "toolCall", "id": "requested", "name": "bash", "arguments": {"command": requested}}]},
        {"role": "assistant", "content": [{"type": "toolCall", "id": "other", "name": "bash", "arguments": {"command": "printf safe"}}]},
        {"role": "toolResult", "toolCallId": "other", "isError": True, "content": [{"type": "text", "text": "Harness blocked this unrelated call"}]},
    ]

    # When only the unrelated call failed, the requested command is unverified.
    assert not live_smoke.blocked_tool_call(messages, "bash", requested)

    # A matching successful result also cannot satisfy the refusal contract.
    messages.append({"role": "toolResult", "toolCallId": "requested", "isError": False, "content": [{"type": "text", "text": "command output"}]})
    assert not live_smoke.blocked_tool_call(messages, "bash", requested)

    # A result with the right id but a different native tool is still a
    # mismatch; a transcript cannot turn a read result into Bash evidence.
    messages[-1] = {"role": "toolResult", "toolCallId": "requested", "toolName": "read", "isError": True, "content": [{"type": "text", "text": "Harness policy refused the command"}]}
    assert not live_smoke.blocked_tool_call(messages, "bash", requested)

    # Only the matching failed result, with a policy reason, proves the block.
    messages[-1] = {"role": "toolResult", "toolCallId": "requested", "toolName": "bash", "isError": True, "content": [{"type": "text", "text": "Harness policy refused the command"}]}
    assert live_smoke.blocked_tool_call(messages, "bash", requested)


def test_live_acceptance_binds_native_read_paths_and_exact_allowed_bash(tmp_path: Path) -> None:
    # Given a fresh project and a relative read path, the native result must
    # carry the same tool name and call id as the requested operation.
    project = tmp_path / "project"
    target = project / ".memory" / "release.md"
    target.parent.mkdir(parents=True)
    target.write_text("bun run verify; PROJECT_FACT_CALDERA")
    messages = [
        {"role": "assistant", "content": [{"type": "toolCall", "id": "read-target", "name": "read", "arguments": {"path": ".memory/release.md"}}]},
        {"role": "toolResult", "toolCallId": "read-target", "toolName": "read", "isError": False, "content": [{"type": "text", "text": target.read_text()}]},
        {"role": "assistant", "content": [{"type": "toolCall", "id": "read-wrong", "name": "read", "arguments": {"path": ".memory/other.md"}}]},
        {"role": "toolResult", "toolCallId": "read-wrong", "toolName": "read", "isError": False, "content": [{"type": "text", "text": "PROJECT_FACT_CALDERA"}]},
        {"role": "assistant", "content": [{"type": "toolCall", "id": "allow-other", "name": "bash", "arguments": {"command": "printf OTHER"}}]},
        {"role": "toolResult", "toolCallId": "allow-other", "toolName": "bash", "isError": False, "content": [{"type": "text", "text": "CL_RUNTIME_FRESH_OK"}]},
        {"role": "assistant", "content": [{"type": "toolCall", "id": "allow-target", "name": "bash", "arguments": {"command": "printf CL_RUNTIME_FRESH_OK"}}]},
        {"role": "toolResult", "toolCallId": "allow-target", "toolName": "bash", "isError": False, "content": [{"type": "text", "text": "CL_RUNTIME_FRESH_OK"}]},
    ]

    assert live_smoke.successful_tool_call(
        messages, "read", lambda arguments: live_smoke.path_argument_matches(project, target, arguments), "PROJECT_FACT_CALDERA"
    )
    assert not live_smoke.successful_tool_call(
        messages, "read", lambda arguments: live_smoke.path_argument_matches(project, project / ".memory" / "missing.md", arguments), "PROJECT_FACT_CALDERA"
    )
    assert not live_smoke.successful_tool_call(
        messages[:-2], "bash", lambda arguments: arguments.get("command") == "printf CL_RUNTIME_FRESH_OK", "CL_RUNTIME_FRESH_OK"
    )
    assert live_smoke.successful_tool_call(
        messages, "bash", lambda arguments: arguments.get("command") == "printf CL_RUNTIME_FRESH_OK", "CL_RUNTIME_FRESH_OK"
    )


def test_live_acceptance_accepts_only_exact_private_or_public_memory_mirror(tmp_path: Path) -> None:
    # Given the two verified roots, either complete path is valid while a
    # suffix-only or unrelated path is not.
    project = tmp_path / "project"
    private = tmp_path / "agent" / "memory" / "--scope--"
    public = project / ".memory"
    private.mkdir(parents=True)
    public.mkdir(parents=True)
    targets = (private / "fact.md", public / "fact.md")

    assert live_smoke.path_argument_matches_any(project, targets, {"path": str(targets[0])})
    assert live_smoke.path_argument_matches_any(project, targets, {"path": ".memory/fact.md"})
    assert not live_smoke.path_argument_matches_any(project, targets, {"path": "fact.md"})
    assert not live_smoke.path_argument_matches_any(project, targets, {"path": ".memory/other.md"})


def test_live_acceptance_uses_all_visible_assistant_text(tmp_path: Path) -> None:
    # Given knowledge appears in assistant prose before the final tool report,
    # it counts; thinking and native tool results do not become assistant text.
    messages = [
        {"role": "assistant", "content": [
            {"type": "thinking", "thinking": "PROJECT_FACT_CALDERA"},
            {"type": "text", "text": "I read the Memory: PROJECT_FACT_CALDERA uses bun run verify."},
        ]},
        {"role": "toolResult", "toolName": "read", "content": [{"type": "text", "text": "hidden tool result"}]},
        {"role": "assistant", "content": [{"type": "text", "text": "I ran the requested checks."}]},
    ]

    visible = live_smoke.assistant_visible_text(messages)
    assert "PROJECT_FACT_CALDERA" in visible and "bun run verify" in visible
    assert "hidden tool result" not in visible


def test_live_acceptance_allows_explicit_memory_history_but_rejects_stale_current_value(tmp_path: Path) -> None:
    # Given a rewritten entry whose frontmatter and current instruction use the
    # new command, an explicitly marked superseded line remains valid history.
    historical = (
        "---\n"
        "description: The settled build command is `bun run verify`.\n"
        "type: project\n"
        "---\n\n"
        "The settled build command is `bun run verify`.\n"
        "The previous command `bun run check` is superseded history.\n"
    )
    live_smoke.assert_current_memory_command(historical, "bun run check", "bun run verify")
    # A real planner used this equivalent historical wording; it must pass
    # without allowing the old value to remain the current build instruction.
    updated_from = historical.replace(
        "The previous command `bun run check` is superseded history.",
        "The settled build command is `bun run verify` (updated from the earlier `bun run check`).",
    )
    live_smoke.assert_current_memory_command(updated_from, "bun run check", "bun run verify")

    # When the old value is still presented as the current command, acceptance
    # must fail even if the new command appears elsewhere in the file.
    stale_current = historical.replace(
        "The previous command `bun run check` is superseded history.",
        "The settled build command is still `bun run check`.",
    )
    with pytest.raises(AssertionError, match="historical marker"):
        live_smoke.assert_current_memory_command(stale_current, "bun run check", "bun run verify")


def test_live_acceptance_rejects_private_marker_on_any_shared_surface(tmp_path: Path) -> None:
    # Given the private marker is copied into an index, AGENTS.md, or Harness,
    # the shared-surface scan must report the exact leaking files.
    project = tmp_path / "project"
    (project / ".memory").mkdir(parents=True)
    (project / ".memory" / "MEMORY.md").write_text("PRIVATE_PREF_QUARTZ")
    (project / "AGENTS.md").write_text("PRIVATE_PREF_QUARTZ")
    (project / ".pi").mkdir()
    (project / ".pi" / "harness.json").write_text('{"instructions":"PRIVATE_PREF_QUARTZ"}')
    leaked = live_smoke.shared_surface_leaks(project, "PRIVATE_PREF_QUARTZ")
    assert {path.relative_to(project) for path in leaked} == {
        Path(".memory/MEMORY.md"), Path("AGENTS.md"), Path(".pi/harness.json"),
    }


def test_live_acceptance_rejects_shared_symlinks_without_reading_targets(tmp_path: Path) -> None:
    # Given a shared alias to private data or a missing target, When public
    # surfaces are verified, Then the alias itself is an invalid shared output.
    project = tmp_path / "project"
    public = project / ".memory"
    public.mkdir(parents=True)
    private = tmp_path / "private.md"
    private.write_text("PRIVATE_PREF_QUARTZ")
    alias = public / "alias.md"
    alias.symlink_to(private)
    assert alias in live_smoke.shared_surface_leaks(project, "PRIVATE_PREF_QUARTZ")
    private.unlink()
    assert alias in live_smoke.shared_surface_leaks(project, "PRIVATE_PREF_QUARTZ")
