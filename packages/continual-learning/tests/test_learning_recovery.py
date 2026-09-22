from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
HARNESS = Path(__file__).with_name("learning-recovery-harness.ts")


@pytest.mark.parametrize("scenario", ["invalid", "cancelled", "failed", "throw", "noop", "dossier-read-error"])
def test_manual_selection_releases_locks_and_can_run_again(scenario: str) -> None:
    result = subprocess.run(
        ["bun", str(HARNESS), scenario], cwd=REPO, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    value = json.loads(result.stdout.strip().splitlines()[-1])
    assert value["selectors"] == 2, value
    assert value["planners"] == 0, value
    assert value["locks"] == [False, False], value
    assert value["shutdownLock"] is False, value
    assert not any("already running" in notice for notice in value["notices"]), value
    if scenario == "noop":
        assert value["notices"] == [], value
        assert len(value["receipts"]) == 2
        assert all([attempt["phase"] for attempt in receipt["attempts"]] == ["selector"] for receipt in value["receipts"])
