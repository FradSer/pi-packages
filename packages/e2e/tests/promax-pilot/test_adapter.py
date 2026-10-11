"""Real subprocess checks for the pilot's evidence and cancellation boundary."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time

import pytest

ADAPTER = Path(__file__).with_name("adapter.mjs")


@pytest.mark.parametrize("exit_code", [0, 7])
def test_adapter_reports_actual_exit(tmp_path: Path, exit_code: int) -> None:
    # Given an actual command outcome, when producing fresh evidence, then the
    # observed exit value is preserved even when the runner itself exits zero.
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"command": f"exit {exit_code}", "timeoutMs": 1000}))
    evidence = tmp_path / "evidence.json"
    run = subprocess.run([shutil.which("node") or "node", str(ADAPTER), str(config)],
                         cwd=tmp_path, env={**os.environ, "PI_E2E_EVIDENCE_PATH": str(evidence)},
                         capture_output=True, text=True, timeout=5)
    assert run.returncode == 0
    observed = json.loads(evidence.read_text())["run"]["observations"]
    assert observed["exitCode"] == exit_code
    assert observed["timedOut"] is False


@pytest.mark.skipif(os.name == "nt", reason="Pilot uses Linux Docker process groups")
def test_cancel_terminates_detached_test_group(tmp_path: Path) -> None:
    # Given a running detached command, when the adapter is cancelled, then its
    # process group is killed rather than continuing to mutate the sandbox.
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"command": "echo $$ > child.pid; exec sleep 60", "timeoutMs": 60000}))
    process = subprocess.Popen([shutil.which("node") or "node", str(ADAPTER), str(config)], cwd=tmp_path,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        deadline = time.monotonic() + 5
        marker = tmp_path / "child.pid"
        while not marker.exists() and time.monotonic() < deadline:
            assert process.poll() is None
            time.sleep(0.01)
        assert marker.exists()
        child_pid = int(marker.read_text())
        process.send_signal(signal.SIGTERM)
        process.communicate(timeout=5)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                os.kill(child_pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.01)
        else:
            pytest.fail("Detached child survived cancellation")
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=5)


def test_coverage_adapter_cannot_clear_unmapped_requirements(tmp_path: Path) -> None:
    config = tmp_path / 'config.json'
    config.write_text(json.dumps({'command': 'true', 'timeoutMs': 1000,
                                 'coverageFile': str(tmp_path / 'missing.json'), 'requirements': ['one', 'two']}))
    evidence = tmp_path / 'evidence.json'
    run = subprocess.run(['node', str(ADAPTER), str(config)], cwd=tmp_path,
                         env={**os.environ, 'PI_E2E_EVIDENCE_PATH': str(evidence)},
                         capture_output=True, text=True, timeout=5)
    assert run.returncode == 0
    result = json.loads(evidence.read_text())
    assert result['run']['observations']['requirements']['1']['exitCode'] is None
    assert {c['clause'] for c in result['checks']} == {1, 2}


def test_claimed_tests_must_be_observed_in_focused_output(tmp_path: Path) -> None:
    config = tmp_path / 'config.json'
    plan = tmp_path / 'coverage.json'
    plan.write_text(json.dumps({'1': {'command': 'true', 'tests': ['does-not-exist']}}))
    config.write_text(json.dumps({'command': 'echo original', 'timeoutMs': 1000,
                                 'coverageFile': str(plan), 'requirements': ['behavior']}))
    result = subprocess.run(['node', str(ADAPTER), str(config)], cwd=tmp_path, capture_output=True, text=True, timeout=5)
    assert result.returncode == 1
    observation = json.loads(result.stdout)['run']['observations']['requirements']['1']
    assert not observation['testNamesObserved']


def test_failed_command_in_pipeline_remains_failed(tmp_path: Path) -> None:
    config = tmp_path / 'config.json'
    config.write_text(json.dumps({'command': 'exit 7 | cat', 'timeoutMs': 1000}))
    result = subprocess.run(['node', str(ADAPTER), str(config)], cwd=tmp_path, capture_output=True, text=True, timeout=5)
    assert result.returncode == 1
    assert json.loads(result.stdout)['run']['observations']['exitCode'] == 7
