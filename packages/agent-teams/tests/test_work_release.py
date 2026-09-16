"""Leader work.release public-seam test."""

import os
import subprocess

PACKAGE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def test_leader_releases_claimed_work_without_completion(tmp_path):
    environment = os.environ.copy()
    environment["PI_TEST_DIR"] = str(tmp_path)
    result = subprocess.run(
        ["node", "tests/work-release-fixture.ts"],
        cwd=PACKAGE,
        capture_output=True,
        text=True,
        env=environment,
        timeout=30,
    )
    assert result.returncode == 0, f"{result.stderr}\n{result.stdout}"
    assert "WORK_RELEASE_OK" in result.stdout
