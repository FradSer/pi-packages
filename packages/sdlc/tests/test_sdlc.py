from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[3]
PACKAGE = REPO / "packages/sdlc"


@pytest.mark.parametrize("scenario", ["playbook-guard", "format", "correction", "settlement", "interrupt", "custom", "custom-continuation", "unsafe", "markers", "lock", "bounded", "crlf", "shutdown", "error", "recovered-error", "carriage-return", "raw-input", "steer", "extension-input", "queued-input", "session-isolation", "streaming-error"])
def test_sdlc_contract(scenario: str) -> None:
    """Given real files and Pi events, when the workflow runs, then its public records satisfy the contract."""
    result = subprocess.run(["node", "--import", "tsx", str(PACKAGE / "tests/contracts.mts"), scenario],
                            cwd=REPO, text=True, capture_output=True, timeout=25)
    assert result.returncode == 0, result.stdout + result.stderr
