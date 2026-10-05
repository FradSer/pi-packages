"""Parent-message transport and result-shape regression tests."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from subagents_helpers import PACKAGE


@pytest.mark.parametrize("probe", ["parse", "extension", "route", "ownership"])
def test_parent_message_contract(probe: str, tmp_path: Path) -> None:
    env = {
        "PATH": os.environ.get("PATH", os.defpath),
        "HOME": str(tmp_path),
        "TMPDIR": str(tmp_path),
        "PI_CODING_AGENT_DIR": str(tmp_path / "agent"),
        "PI_OFFLINE": "1",
    }
    result = subprocess.run(
        ["node", "--experimental-test-module-mocks", str(PACKAGE / "tests" / "parent-message-fixture.ts"), probe],
        cwd=PACKAGE,
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert '"ok":true' in result.stdout
