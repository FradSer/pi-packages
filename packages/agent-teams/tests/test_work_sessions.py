"""Behavioral checks for independent Work Sessions through registered tools."""

from pathlib import Path
import subprocess
import json

PACKAGE = Path(__file__).resolve().parents[1]


def test_new_delegations_are_independent_and_work_ids_route_exactly() -> None:
    result = subprocess.run(
        ["node", "tests/independent-work-fixture.ts"],
        cwd=PACKAGE, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "INDEPENDENT_WORK_OK" in result.stdout


def test_result_envelope_keeps_work_and_failure_evidence_in_model_context() -> None:
    result = subprocess.run(
        ["node", "--input-type=module", "--eval", '''
        import { formatReports } from "./src/leader-reports.ts";
        const report = { teammate: "worker", workId: "work:one", assignmentId: "attempt:two", body: "Same response" };
        console.log(JSON.stringify({
          completed: formatReports([{ ...report, status: "completed", finished: true }]),
          failed: formatReports([{ ...report, status: "failed", finished: true }]),
          progress: formatReports([{ ...report, status: "in_progress" }]),
          escaped: formatReports([{ ...report, workId: 'a"<b', status: "completed" }]),
        }));
        '''], cwd=PACKAGE, capture_output=True, text=True, timeout=15,
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
