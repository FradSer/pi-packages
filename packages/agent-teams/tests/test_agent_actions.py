"""Strict Agent action dispatcher contract."""

import os
import subprocess

PACKAGE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def test_agent_actions_use_exact_incarnation_handles_and_inline_definitions():
    result = subprocess.run(["node", "tests/agent-actions-fixture.ts"], cwd=PACKAGE, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, f"{result.stderr}\n{result.stdout}"
    assert "AGENT_ACTIONS_OK" in result.stdout
