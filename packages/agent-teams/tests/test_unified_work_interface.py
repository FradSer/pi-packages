"""Public registration tests for the first unified Work tracer slice."""

import os
import subprocess

PACKAGE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def test_leader_work_create_and_list_share_the_pending_work_projection(tmp_path):
    environment = os.environ.copy()
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
