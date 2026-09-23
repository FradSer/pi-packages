from __future__ import annotations

import os
import secrets
import shutil
import subprocess
from pathlib import Path

import pytest

from test_teammate_package import PACKAGE


@pytest.mark.parametrize("transition", ["stopped", "released", "superseded", "completed", "replacement", "active"])
def test_real_pi_excludes_retired_attempt_reports_but_preserves_history(tmp_path: Path, transition: str) -> None:
    pi = shutil.which("pi")
    if pi is None:
        pytest.skip("Pi CLI is required for the native report delivery regression")
    env = {key: value for key, value in os.environ.items() if not key.startswith("PI_")}
    env.update({
        "HOME": str(tmp_path),
        "PI_CODING_AGENT_DIR": str(tmp_path / "agent"),
        "PI_OFFLINE": "1",
        "PI_REPORT_FIXTURE_AUTH": secrets.token_hex(16),
        "PI_REPORT_HISTORY_TRANSITION": transition,
    })
    result = subprocess.run(
        [pi, "--print", "--no-session", "--no-extensions", "--no-skills", "--no-prompt-templates",
         "--no-themes", "--no-context-files", "--no-approve",
         "--extension", str(PACKAGE / "tests/historical-report-fixture.ts"),
         "--provider", "historical-report-fixture", "--model", "deterministic", "--thinking", "off",
         "--tools", "produce_historical_reports,check_historical_reports", "Run the historical report fixture"],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=25,
    )
    assert result.returncode == 0, result.stderr
    assert "PI_HISTORICAL_REPORT_OK" in result.stdout, result.stdout + result.stderr
    assert "PI_HISTORICAL_REPORT_FAILED" not in result.stdout
