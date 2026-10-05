from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

import pytest

import live_design_e2e as design
import live_harness_learning as harness
import live_smoke


def stub_prepare(base: Path, *args: object, **kwargs: object) -> tuple[Path, Path, Path]:
    project, agent = base / "project", base / "agent"
    project.mkdir()
    agent.mkdir()
    (project / "AGENTS.md").write_text("Report progress as a paragraph.\n")
    return project, agent, base / "probe.ts"


def test_direct_runtime_probe_overrides_ambient_agent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "source-agent"
    source.mkdir()
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(source))
    observed: list[dict[str, str]] = []

    def run(*args: object, **kwargs: object) -> SimpleNamespace:
        observed.append(kwargs.get("env", {}))
        return SimpleNamespace(returncode=0, stdout="{}", stderr="")

    monkeypatch.setattr(design.subprocess, "run", run)
    design.bun("console.log('{}')")
    assert observed[0].get("PI_CODING_AGENT_DIR")
    assert Path(observed[0]["PI_CODING_AGENT_DIR"]) != source
    assert os.environ["PI_CODING_AGENT_DIR"] == str(source)
    assert list(source.iterdir()) == []


@pytest.mark.parametrize("check", [design.verify_secret_rejection, design.verify_recovery_isolation, design.verify_path_containment])
def test_failed_safety_probe_cannot_pass(check: Callable[[], dict], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(design, "prepare", stub_prepare)
    monkeypatch.setattr(design, "bun", lambda *args, **kwargs: {
        "secretsRejected": False, "ordinaryAccepted": False,
        "appliedSurvived": False, "unrelatedUnchanged": False, "recoveryIdempotent": False,
        "pendingDetected": False, "pendingAbandoned": False,
        "escapeRefused": False, "symlinkRefused": False,
        "escapeDetail": "", "symlinkDetail": "",
    })
    with pytest.raises(AssertionError):
        check()


def test_unchanged_agents_document_cannot_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(design, "prepare", stub_prepare)
    monkeypatch.setattr(design, "run_pi", lambda *args, **kwargs: {"records": [], "messages": []})
    with pytest.raises(AssertionError, match="AGENTS"):
        design.verify_agents_applied()


def test_unrelated_tool_error_cannot_prove_bash_block(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(design, "prepare", stub_prepare)
    monkeypatch.setattr(design, "run_pi", lambda *args, **kwargs: {
        "records": [{"customType": "harness-event", "data": {"action": "block"}}],
        "messages": [
            {"role": "assistant", "content": [{"type": "toolCall", "id": "target", "name": "bash", "arguments": {"command": "touch gate-probe-ran"}}]},
            {"role": "toolResult", "toolCallId": "unrelated", "toolName": "bash", "isError": True, "content": [{"type": "text", "text": "Harness policy refused this unrelated command"}]},
        ],
    })
    with pytest.raises(AssertionError):
        design.verify_execution_gate()


@pytest.mark.parametrize("command", ["touch ./gate-probe-ran", "touch gate-probe-ran\n"])
def test_bash_probe_accepts_matching_command_with_its_own_refusal(command: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(design, "prepare", stub_prepare)
    monkeypatch.setattr(design, "run_pi", lambda *args, **kwargs: {
        "records": [{"customType": "harness-event", "data": {"action": "block", "policy": "gate-probe"}}],
        "messages": [
            {"role": "assistant", "content": [{"type": "toolCall", "id": "target", "name": "bash", "arguments": {"command": command}}]},
            {"role": "toolResult", "toolCallId": "target", "toolName": "bash", "isError": True, "content": [{"type": "text", "text": "Harness policy refused the prohibited operation"}]},
        ],
    })
    assert design.verify_execution_gate()["blocked"] is True


def test_uncorrected_output_cannot_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(design, "prepare", stub_prepare)
    monkeypatch.setattr(design, "run_pi", lambda *args, **kwargs: {
        "records": [{"customType": "harness-post-generation-repair"}],
        "messages": [{"role": "assistant", "content": [{"type": "text", "text": "OUTPUT_GATE_TOKEN"}]}],
        "final": "OUTPUT_GATE_TOKEN",
    })
    with pytest.raises(AssertionError):
        design.verify_output_check()


@pytest.mark.parametrize("entry", ["knowledge.md", "MEMORY.md"])
def test_memory_probe_refuses_symlink_without_reading_target(tmp_path: Path, entry: str) -> None:
    root = tmp_path / "memory"
    root.mkdir()
    target = tmp_path / "outside.md"
    target.write_text("unrelated bytes")
    (root / entry).symlink_to(target)
    with pytest.raises(AssertionError, match="symlink"):
        live_smoke.memory_bodies(root)


def test_harness_measurement_does_not_count_unowned_rule() -> None:
    summary = harness.summarize_outcomes([{
        "learned": True, "correct": True, "blocked": "block", "allowed": "execute", "ownershipBound": False,
    }])
    assert summary["learnedAndCorrect"] == 0


def test_explicit_history_wording_does_not_mask_current_command_errors() -> None:
    from live_smoke import assert_current_memory_command
    body = ('---\nname: command\ndescription: Use bun run verify\ntype: project\n---\n'
            'The settled command is `bun run verify`. The user directed updating this entry from '
            '`bun run check` to `bun run verify`.\n')
    assert_current_memory_command(body, 'bun run check', 'bun run verify')
