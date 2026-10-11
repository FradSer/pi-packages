"""Build a pilot receipt from independent grading, not plugin verdicts."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from protocol import compiler_failure


def summarize(root: Path, sample: list[dict[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for task in sample:
        item: dict[str, Any] = {"instance_id": task["instance_id"], "language": task["language"]}
        folder = root / task["instance_id"]
        gate = folder / "gate.json"
        item["gate"] = json.loads(gate.read_text()) if gate.exists() else None
        for arm in ("baseline", "e2e"):
            attempt_file = folder / arm / "attempt.json"
            grade_file = folder / arm / "grade/result.json"
            if not attempt_file.exists():
                item[arm] = {"state": "pending"}
                continue
            attempt = json.loads(attempt_file.read_text())
            grade = json.loads(grade_file.read_text()) if grade_file.exists() else None
            grading_blocked = grade is not None and (
                grade.get("compilerFailure", False)
                or (not grade.get("passed", False) and (folder / arm / "grade/stderr.log").exists()
                    and compiler_failure((folder / arm / "grade/stderr.log").read_text()))
                or grade.get("testPatchApplyFailed", False)
                or (grade.get("reason") != "patch_apply_failed"
                    and (grade.get("reason") != "verifier_finished" or not grade.get("scriptExitCodes"))))
            state = ("infrastructure_blocked" if attempt.get("infrastructureError") or grading_blocked else
                     "pending_grade" if grade is None else "passed" if grade["passed"] else "failed")
            calls = len(attempt.get("e2eResults", []))
            events_file = folder / arm / "events.jsonl"
            if events_file.exists():
                calls = 0
                for line in events_file.read_text().splitlines():
                    try:
                        event = json.loads(line)
                    except ValueError:
                        continue
                    calls += event.get("type") == "tool_execution_start" and event.get("toolName") == "e2e_verify"
            item[arm] = {"state": state, "grade": grade, "inferenceRequests": attempt.get("inferenceRequests"),
                         "transportErrors": attempt.get("transportErrors"), "elapsedSeconds": attempt.get("elapsedSeconds"),
                         "e2eVerifyCalls": None if attempt.get("toolTraceLost") else calls,
                         "e2eStatuses": [result.get("status") for result in attempt.get("e2eResults", [])],
                         "verifiedRuns": [result.get("verifiedRun") for result in attempt.get("e2eResults", [])]}
        rows.append(item)
    paired = [row for row in rows if row["gate"] and row["gate"]["eligible"]
              and all(row[arm]["state"] in {"passed", "failed"} for arm in ("baseline", "e2e"))]
    return {"plannedTasks": len(rows), "completedPairs": len(paired),
            "baselinePassed": sum(row["baseline"]["state"] == "passed" for row in paired),
            "e2ePassed": sum(row["e2e"]["state"] == "passed" for row in paired),
            "e2eOnlyPassed": sum(row["e2e"]["state"] == "passed" and row["baseline"]["state"] == "failed" for row in paired),
            "baselineOnlyPassed": sum(row["baseline"]["state"] == "passed" and row["e2e"]["state"] == "failed" for row in paired),
            "pairedTreatmentsWithVerification": sum(row["e2e"]["e2eVerifyCalls"] > 0 for row in paired),
            "tasks": rows,
            "limitations": ["Eight-task exploratory pilot cannot establish small general gains.",
                            "Linux/amd64 task images run under emulation on an arm64 Docker host.",
                            "Public command evidence measures regression-suite execution, not full requirement coverage.",
                            "Offline deterministic E2E evaluation does not measure Jev judgment quality."]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sample", type=Path, required=True)
    args = parser.parse_args()
    result = summarize(args.output, json.loads(args.sample.read_text()))
    (args.output / "summary.json").write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(json.dumps({key: value for key, value in result.items() if key != "tasks"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
