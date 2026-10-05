"""Public registration tests for the first unified Work tracer slice."""

import os
import subprocess

PACKAGE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def test_leader_work_create_and_list_share_the_pending_work_projection(tmp_path):
    # A spawned teammate runs the suite with its own holder bound. Copying the
    # whole environment inherits that binding, and the fixture then takes work
    # as the teammate instead of as the caller it is written for.
    environment = {
        key: value for key, value in os.environ.items()
        if not key.startswith("PI_TEAMMATE_") and key not in {"PI_TASK_HOLDER", "PI_TEAM_STATE_DIR"}
    }
    environment["PI_TEST_DIR"] = str(tmp_path)
    result = subprocess.run(
        ["node", "tests/unified-work-interface-fixture.ts"],
        cwd=PACKAGE,
        capture_output=True,
        text=True,
        env=environment,
        timeout=30,
    )
    assert result.returncode == 0, f"{result.stderr}\n{result.stdout}"
    assert "UNIFIED_WORK_INTERFACE_OK" in result.stdout
