from __future__ import annotations

import json
import os
import signal
import subprocess
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def run_accuracy_matrix() -> dict:
    with tempfile.TemporaryDirectory(prefix="monitor-accuracy-") as directory:
        pid_file = Path(directory) / "pids"
        try:
            completed = subprocess.run(
                ["node", "--import", "tsx", "packages/monitor/tests/accuracy-matrix-fixture.mts"],
                cwd=REPO, env={**os.environ, "MONITOR_MATRIX_PID_FILE": str(pid_file)},
                capture_output=True, text=True, timeout=90,
            )
            assert completed.stdout.strip(), completed.stderr
            report = json.loads(completed.stdout.strip().splitlines()[-1])
            failures = [case for case in report["observed"] if not case["passed"]]
            assert completed.returncode == 0, json.dumps(failures, ensure_ascii=False, indent=2) + completed.stderr
            return report
        finally:
            if pid_file.exists():
                for entry in pid_file.read_text().splitlines():
                    try:
                        os.killpg(int(entry), signal.SIGKILL)
                    except ProcessLookupError:
                        pass


def test_real_process_accuracy_matrix() -> None:
    report = run_accuracy_matrix()
    assert report["cases"] >= 75
    assert report["uniqueMonitorIds"] == report["cases"]
    assert all(case["passed"] for case in report["observed"])


if __name__ == "__main__":
    print(json.dumps(run_accuracy_matrix(), ensure_ascii=False, indent=2))
