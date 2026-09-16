"""Registered leader work.assign public-seam test."""

import os
import subprocess

PACKAGE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def test_leader_assigns_pending_work_to_an_exact_idle_session(tmp_path):
    environment = os.environ.copy()
    environment["PI_TEST_DIR"] = str(tmp_path)
    result = subprocess.run(
        ["node", "tests/work-assign-fixture.ts"],
        cwd=PACKAGE,
        capture_output=True,
        text=True,
        env=environment,
        timeout=30,
    )
    assert result.returncode == 0, f"{result.stderr}\n{result.stdout}"
    assert "WORK_ASSIGN_OK" in result.stdout
