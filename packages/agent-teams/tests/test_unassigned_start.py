"""Public unassigned-start lifecycle regression."""
import os
import subprocess
import pytest
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("mode", ["assign", "not-ready", "rejected", "timeout", "exit", "notice", "inbox", "in_progress"])
def test_public_start_then_assign_without_unassigned_model_turn(tmp_path, mode):
    env = {**os.environ, "PI_TEST_MODE": mode, "PI_TEST_DIR": str(tmp_path), "PI_CODING_AGENT_DIR": str(tmp_path / "agent")}
    # The `timeout` mode waits out the runtime's own 30-second confirmation
    # window before it reports the failure it is modelling, so the budget covers
    # that deadline plus startup. A budget below it reports a harness timeout for
    # work the runtime is doing correctly.
    result = subprocess.run(["node", "tests/unassigned-start-fixture.ts"], cwd=PACKAGE, env=env, capture_output=True, text=True, timeout=50)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "UNASSIGNED_START_OK" in result.stdout


def test_leader_priority_transport_and_fresh_assignment_queue():
    result = subprocess.run(["node", "tests/leader-priority-lifecycle-fixture.ts"], cwd=PACKAGE, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert '"ok":true' in result.stdout
