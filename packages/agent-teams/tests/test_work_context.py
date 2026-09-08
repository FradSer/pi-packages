from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

import pytest

PACKAGE = Path(__file__).resolve().parents[1]


def run_fixture(tmp_path: Path, scenario: str) -> None:
    env = {key: value for key, value in os.environ.items() if not key.startswith("PI_TEAMMATE_")}
    env["WORK_CONTEXT_FIXTURE_DIR"] = str(tmp_path / "context")
    result = subprocess.run(
        ["node", "tests/work-context-fixture.ts", scenario],
        cwd=PACKAGE, env=env, capture_output=True, text=True, timeout=20,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"ok": True, "scenario": scenario}


@pytest.mark.parametrize("scenario", ["snapshot-active", "snapshot-in-memory", "snapshot-empty", "snapshot-interleaved", "snapshot-selected-leaf"])
def test_fork_snapshot_is_active_complete_and_detached(tmp_path: Path, scenario: str) -> None:
    run_fixture(tmp_path, scenario)


@pytest.mark.parametrize("scenario", ["spawn-fork", "spawn-empty", "spawn-user-only", "spawn-fresh", "spawn-parallel"])
def test_spawn_selects_an_independent_context_without_changing_the_tool_grant(tmp_path: Path, scenario: str) -> None:
    run_fixture(tmp_path, scenario)


@pytest.mark.parametrize("scenario", ["spawn-throw", "spawn-error", "spawn-seed-failure", "spawn-runtime-error"])
def test_context_cleanup_matches_failed_start_or_observed_close(tmp_path: Path, scenario: str) -> None:
    run_fixture(tmp_path, scenario)
