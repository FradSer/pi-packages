"""Behavioral checks for independent Work Sessions through registered tools."""

from pathlib import Path
import subprocess
import json
import sys

import pytest

PACKAGE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE.parents[1] / "tests" / "e2e" / "support"))
from harness import isolated_environment  # noqa: E402


def run_work_fixture(tmp_path: Path, probe: str = "independent") -> subprocess.CompletedProcess[str]:
    env = isolated_environment(tmp_path)
    return subprocess.run(
        ["node", str(PACKAGE / "tests" / "independent-work-fixture.ts"), probe],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=50,
    )


def test_new_delegations_are_independent_and_work_ids_route_exactly(tmp_path: Path) -> None:
    result = run_work_fixture(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "INDEPENDENT_WORK_OK" in result.stdout


# The intent family starts a child only with a prompt, so the acknowledgement that
# proves the start is the prompt's. The former readiness-only probes collapsed onto
# this path and are kept once, as `readiness`.
@pytest.mark.parametrize("probe", [
    "readiness", "prompt-rejected", "prompt-timeout", "prompt-handled", "prompt-wrong-id",
])
def test_child_start_requires_parsed_rpc_confirmation(tmp_path: Path, probe: str) -> None:
    result = run_work_fixture(tmp_path, probe)
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"RPC_CONFIRMATION_OK {probe}" in result.stdout


def test_result_envelope_keeps_work_and_failure_evidence_in_model_context(tmp_path: Path) -> None:
    result = subprocess.run(
        ["node", "--input-type=module", "--eval", '''
        import { formatReports } from "@fradser/pi-subagents";
        const report = { agent: "worker", workId: "work:one", assignmentId: "attempt:two", body: "Same response" };
        console.log(JSON.stringify({
          completed: formatReports([{ ...report, status: "completed", finished: true }]),
          failed: formatReports([{ ...report, status: "failed", finished: true }]),
          progress: formatReports([{ ...report, status: "in_progress" }]),
          escaped: formatReports([{ ...report, workId: 'a"<b', status: "completed" }]),
        }));
        '''], cwd=PACKAGE, env=isolated_environment(tmp_path), capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert 'work="work:one"' in output["completed"]
    assert 'assignment="attempt:two"' in output["completed"]
    assert 'status="completed"' in output["completed"]
    assert 'status="failed"' in output["failed"]
    assert 'status="in_progress"' in output["progress"]
    assert len({output["completed"], output["failed"], output["progress"]}) == 3
    assert 'work="a&quot;&lt;b"' in output["escaped"]
