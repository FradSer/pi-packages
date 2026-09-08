import json
import os
from pathlib import Path
import subprocess

PACKAGE = Path(__file__).resolve().parents[1]


def run_fixture(tmp_path, mode="unconfirmed"):
    env = {key: value for key, value in os.environ.items() if not key.startswith("PI_TEAMMATE_")}
    env["HOME"] = str(tmp_path)
    run = subprocess.run(
        ["node", "--experimental-test-module-mocks", "tests/shutdown-confirmation-fixture.ts", mode],
        cwd=PACKAGE, env=env, capture_output=True, text=True, timeout=20,
    )
    assert run.returncode == 0, run.stderr
    return json.loads(run.stdout)


def test_unconfirmed_registered_child_keeps_shutdown_and_ownership_open(tmp_path):
    result = run_fixture(tmp_path)
    assert result["stopTime"] is None
    assert result["stoppedSummaries"] == 0
    assert result["terminationCalls"] == 1
    assert result["closeObserved"] is False
    assert result["result"]["ok"] is False, result
    assert result["status"] != "stopped"
    assert result["task"]["status"] == "claimed"
    assert result["task"]["claimedBy"] == "worker"


def test_retry_confirms_stop_and_rejects_work_while_stopping(tmp_path):
    result = run_fixture(tmp_path, "retry")
    assert result["rejected"]["ok"] is False
    assert "stopping" in result["rejected"]["error"]
    assert result["retry"]["ok"] is True
    assert "requested" not in result["retry"]["body"].lower()
    assert result["status"] == "stopped"
    assert isinstance(result["stopTime"], int)
    assert result["task"]["status"] == "pending"


def test_delayed_close_is_intentional_and_absent_replacement_preserves_evidence(tmp_path):
    result = run_fixture(tmp_path, "delayed")
    assert result["stopped"]["status"] == "stopped"
    assert result["stopped"].get("error") is None
    assert isinstance(result["stopTime"], int)
    assert result["retained"] == result["stopTime"]
    assert result["absent"]["ok"] is True
    assert result["replacementTime"] == 1234567890000
    assert result["resetTime"] is None
