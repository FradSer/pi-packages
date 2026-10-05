"""Consumer regression for the adopted disk-only identity execution contract."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from test_agent_package import PACKAGE, SRC, run_node


@pytest.mark.parametrize("mode", ["accepted", "queued", "rejected", "handled", "exit", "timeout", "fast-result", "disk", "registry-owner", "two-results", "idle-send", "interrupt", "interrupt-rejected", "interrupt-handled", "interrupt-timeout", "interrupt-exit", "send-rejected", "send-handled", "send-timeout", "send-exit", "send-fast-result", "late-negative", "pending-start", "gate-on-drain", "intent-fast-report"])
def test_team_resident_contract(tmp_path: Path, mode: str) -> None:
    env = {**os.environ, "PI_TEST_MODE": mode, "PI_TEST_DIR": str(tmp_path)}
    # The `timeout` mode waits out the runtime's own 30-second confirmation
    # window before it reports the failure it is modelling, so the budget covers
    # that deadline plus startup. A budget below it reports a harness timeout for
    # work the runtime is doing correctly.
    result = subprocess.run(
        ["node", "tests/disk-identity-resident-fixture.ts"], cwd=PACKAGE,
        env=env, capture_output=True, text=True, timeout=50,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout.strip().splitlines()[-1])["ok"] is True


def test_team_guidance_names_only_the_intent_tool_family() -> None:
    """The intent family replaces the retired `agent` surface, and the guidance
    must say so by naming the five tools and nothing else.

    ADR-0008 removed the legacy branch and its in-transcript notice: a recorded
    branch that named `agent` moves silently, so a "Legacy branches" line would
    now describe a surface no code can select. The guidance must still carry the
    surviving contract, and must not reintroduce the retired name as a tool.
    """
    payload = run_node(f'''
      import {{ buildIdleLeaderGuidance, buildTeamLeaderGuidance }} from "{(SRC / 'guidance.ts').as_uri()}";
      console.log(JSON.stringify({{ idle: buildIdleLeaderGuidance(), active: buildTeamLeaderGuidance() }}));
    ''')
    for text in payload.values():
        # The adopted fresh-session contract replaces six model actions with five intent tools.
        for tool in ("agent_start", "agent_input", "agent_inspect", "agent_list", "agent_stop"):
            assert f"`{tool}`" in text
        assert "Legacy branches" not in text, "The retired legacy branch has no selectable surface"
        assert "`agent`" not in text, "The retired agent tool must not appear as a surface"
        assert "next" in text and "steer" in text
        for obsolete in ("persist: true", "persistent:", "memory: true", "worktree: true", "promot"):
            assert obsolete not in text.lower()
        assert "agent.md" in text


def test_consumer_has_no_identity_write_or_git_workspace_hooks() -> None:
    source = (SRC / "team-machine.ts").read_text()
    for removed in ("persistAgentDefinition", "preserveAgentWorkspace", "releaseAgentWorkspace", "liveWorkspaces", "finalizeWorktree", "discardWorkspaceQuietly", "persistScope", "generated.persist", "agent.memory", "agent.isolation"):
        assert removed not in source, removed
    definition = run_node(f'''
      import {{ InlineAgentDefinitionParams }} from "{(SRC / 'types.ts').as_uri()}";
      console.log(JSON.stringify({{ fields: Object.keys(InlineAgentDefinitionParams.properties) }}));
    ''')
    assert not set(definition["fields"]) & {"persist", "persistScope", "persistent", "memory", "worktree", "isolation"}
