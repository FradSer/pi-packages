"""Does learning actually change behaviour?

Every other check in this package's verification asks whether a guard fires or a
hook is wired. Those are plumbing questions, and a package can pass all of them
while learning nothing. This asks the one that matters: do held-out tasks whose
answers live only in Memory get answered because of it?

The paired evaluation runs each task twice, once with no Memory and once with
Memory injected, and Memory is the only difference between the arms. So a
baseline that cannot answer and a candidate that can is a causal result rather
than a correlation. The check requires the baseline to score exactly zero: a
baseline that could already answer would mean the tasks are not testing Memory
at all, and the comparison would prove nothing.

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

    assert baseline["successRate"] == 0.0, (
        f"Baseline scored {baseline['successRate']}. The tasks are not unanswerable "
        f"without Memory, so this comparison cannot demonstrate that learning did "
        f"anything. answers={[row['answer'] for row in baseline['results']]}"
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
    }


if __name__ == "__main__":
    print("verify_learning_is_effective " + json.dumps(verify_learning_is_effective()), flush=True)