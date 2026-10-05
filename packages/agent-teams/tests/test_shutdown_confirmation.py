import json
import os
from pathlib import Path
import subprocess

import pytest

PACKAGE = Path(__file__).resolve().parents[1]


def run_fixture(tmp_path, mode="unconfirmed"):
    env = {
        key: value for key, value in os.environ.items()
        if not key.startswith("PI_TEAMMATE_")
        and key not in {"PI_TASK_HOLDER", "PI_TEAM_STATE_DIR", "PI_CODING_AGENT_SESSION_DIR"}
    }
    env["HOME"] = str(tmp_path)
    env["PI_CODING_AGENT_DIR"] = str(tmp_path / "agent")
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
    assert result["task"]["status"] == "in_progress"
    assert result["task"]["claimedBy"] == "worker"


def test_retry_confirms_stop_and_rejects_work_while_stopping(tmp_path):
    result = run_fixture(tmp_path, "retry")
    assert result["rejected"]["ok"] is False
    assert "stopping" in result["rejected"]["error"]
    assert result["retry"]["ok"] is True
    assert "requested" not in result["retry"]["body"].lower()
    assert result["status"] == "stopped"
    assert isinstance(result["stopTime"], int)
    assert result["task"]["status"] == "recovery_hold"


def test_delayed_close_is_intentional_and_absent_replacement_preserves_evidence(tmp_path):
    result = run_fixture(tmp_path, "delayed")
    assert result["stopped"]["status"] == "stopped"
    assert result["stopped"].get("error") is None
    assert isinstance(result["stopTime"], int)
    assert result["retained"] == result["stopTime"]
    assert result["absent"]["ok"] is True
    assert result["replacementTime"] == 1234567890000
    assert result["resetTime"] is None


def test_clean_idle_close_keeps_results_without_a_crash_notification(tmp_path: Path) -> None:
    result = run_fixture(tmp_path, "close-idle")
    assert result["status"] == "stopped"
    assert result["stopTime"] == 1234567890000
    assert result["error"] is None
    assert result["reports"] == [], "A clean idle close must not start another leader turn"
    assert result["task"]["status"] == "completed"
    assert result["task"]["result"] == "Accepted review evidence"
    assert [message["subject"] for message in result["mailbox"]] == ["Agent stopped"]
    assert "unexpected" not in result["mailbox"][0]["body"].lower()


@pytest.mark.parametrize("mode, expected_alarm", [
    ("close-mail-current", True),
    ("close-mail-unbound", True),
    ("close-mail-late", True),
    ("close-mail-invalid-body", True),
    ("close-mail-invalid-binding", True),
    ("close-mail-broken-json", True),
    ("close-mail-incomplete", True),
    ("close-mail-stale", False),
    ("close-mail-delivered", False),
])
def test_unread_current_mail_prevents_passive_close_without_consuming_it(
    tmp_path: Path, mode: str, expected_alarm: bool,
) -> None:
    result = run_fixture(tmp_path, mode)
    assert result["status"] == "stopped"
    assert result["error"] is None
    assert result["stopTime"] == 1234567890000
    assert len(result["reports"]) == int(expected_alarm)
    if expected_alarm:
        assert result["reports"][0]["harnessEvent"]["type"] == "unexpected-stop"
    expected_subject = "Agent stopped unexpectedly" if expected_alarm else "Agent stopped"
    assert [message["subject"] for message in result["mailbox"]] == [expected_subject]
    assert result["task"]["status"] == "completed"
    assert result["task"]["result"] == "Accepted review evidence"
    assert result["inboxUnchanged"] is True
    assert result["deliveryStateUnchanged"] is True


@pytest.mark.parametrize("mode", ["close-owned", "close-crash", "close-signal", "close-unreported"])
def test_unrequested_failure_or_unfinished_work_still_reaches_the_leader(tmp_path: Path, mode: str) -> None:
    result = run_fixture(tmp_path, mode)
    assert result["status"] == "stopped"
    assert result["stopTime"] == 1234567890000
    assert len(result["reports"]) == 1, "Repeated close events must not repeat the alarm"
    assert result["reports"][0]["harnessEvent"]["type"] == "unexpected-stop"
    assert [message["subject"] for message in result["mailbox"]] == ["Agent stopped unexpectedly"]
    if mode in {"close-owned", "close-unreported"}:
        assert result["task"]["status"] == "recovery_hold"
        assert "claimedBy" not in result["task"]
    else:
        assert result["error"] is not None
        assert result["task"]["status"] == "completed"
        assert result["task"]["result"] == "Accepted review evidence"
