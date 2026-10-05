"""Real RPC parser and control stream with only OS process creation faked."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from subagents_helpers import PACKAGE


@pytest.mark.parametrize("probe", ["long", "utf8", "unterminated", "successor-on-close", "readiness", "prompt", "copies", "tail", "session-dir", "fork-dir", "kickoff-rejected", "steer", "steer-timeout", "resume-symlink", "final-evidence", "later-message", "stop-reason-budget", "startup-delayed-kickoff", "startup-delayed-idle", "startup-delayed-fork", "startup-timeout", "resident-timeout", "fork-kickoff-timeout", "cancel-replace-late-ack"])
def test_resident_transport_contract(probe: str, tmp_path: Path) -> None:
    env = {key: value for key, value in os.environ.items() if not key.startswith("PI_")}
    env.update(HOME=str(tmp_path), TMPDIR=str(tmp_path), PI_CODING_AGENT_DIR=str(tmp_path / "agent"))
    result = subprocess.run([
        "node", "--experimental-test-module-mocks",
        str(PACKAGE / "tests" / "resident-transport-fixture.ts"), probe,
    ], cwd=PACKAGE, env=env, capture_output=True, text=True, timeout=15, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert '"ok":true' in result.stdout
