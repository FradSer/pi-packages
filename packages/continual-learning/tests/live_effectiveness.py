"""Does persisted Memory change held-out task behaviour?

Every other check in this package's verification asks whether a guard fires or a
hook is wired. Those are plumbing questions, and a package can pass all of them
while learning nothing. This checks whether held-out tasks whose answers are
stored in Memory are answered when that Memory is available.

The paired evaluation runs each task twice, once with no Memory and once with
Memory injected. Candidate cases also require evidence that Pi's native read
tool returned a marker from the Memory body. This is a bounded paired sample;
it is not a statistical or causal claim about learning generally.

Not collected by pytest; it spends real provider tokens. Run it explicitly.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
REPO = PACKAGE.parents[1]
EFFECTIVENESS_SUITE = PACKAGE / "examples" / "learning-effectiveness.json"


def assert_effectiveness_report(report: dict) -> None:
    execution_failures = [
        f"{arm}:{row.get('id')}:{row.get('error')}"
        for arm in ("baseline", "candidate")
        for row in report[arm]["results"]
        if row.get("error") is not None
    ]
    assert not execution_failures, f"Both evaluation arms must execute successfully; failures={execution_failures}"
    assert report["baseline"].get("executionFailures", 0) == 0
    assert report["candidate"].get("executionFailures", 0) == 0


def verify_learning_is_effective() -> dict:
    with tempfile.TemporaryDirectory(prefix="cl-effectiveness-") as raw:
        report_path = Path(raw) / "report.json"
        result = subprocess.run(
            [sys.executable, str(PACKAGE / "scripts" / "evaluate-learning.py"),
             str(EFFECTIVENESS_SUITE), "--output", str(report_path)],
            cwd=REPO, capture_output=True, text=True, check=False, timeout=2400,
        )
        assert result.returncode == 0, f"{result.stderr[-1500:]}"
        report = json.loads(report_path.read_text(encoding="utf-8"))

    baseline = report["baseline"]
    candidate = report["candidate"]
    candidate_failures = [row["id"] for row in candidate["results"] if not row["passed"]]

    assert_effectiveness_report(report)
    assert baseline["successRate"] == 0.0, (
        f"Baseline scored {baseline['successRate']}; the no-Memory precondition failed. "
        f"answers={[row['answer'] for row in baseline['results']]}"
    )
    assert candidate["successRate"] == 1.0, (
        f"Memory did not make every held-out task answerable; failures={candidate_failures}. "
        f"answers={[row['answer'] for row in candidate['results']]}"
    )
    assert report["regressions"] == [], report["regressions"]
    return {
        "model": report["model"],
        "tasks": len(candidate["results"]),
        "baselineSuccessRate": baseline["successRate"],
        "candidateSuccessRate": candidate["successRate"],
        "regressions": report["regressions"],
        "baselineAnswers": [row["answer"] for row in baseline["results"]],
        "candidateAnswers": [row["answer"] for row in candidate["results"]],
        "usage": {"baseline": baseline["usage"], "candidate": candidate["usage"]},
        "cost": {"baseline": baseline["cost"], "candidate": candidate["cost"]},
    }


if __name__ == "__main__":
    print("verify_learning_is_effective " + json.dumps(verify_learning_is_effective()), flush=True)
