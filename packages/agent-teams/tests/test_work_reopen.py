"""Leader work.reopen public-seam test."""

import os
import subprocess

PACKAGE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def test_leader_reopens_completed_work_without_starting_execution(tmp_path):
    environment = os.environ.copy()
    environment["PI_TEST_DIR"] = str(tmp_path)
    result = subprocess.run(
        ["node", "tests/work-reopen-fixture.ts"],
        cwd=PACKAGE,
        capture_output=True,
        text=True,
        env=environment,
        timeout=30,
    )
    assert result.returncode == 0, f"{result.stderr}\n{result.stdout}"
    assert "WORK_REOPEN_OK" in result.stdout
