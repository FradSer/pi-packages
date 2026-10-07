"""End-to-end gate for the matt-pocock case in the repository E2E layer.

The runner starts the real Pi CLI against the package's runtime fixture. These
cases assert that grill-me completes through both entry points and that the
committed result artifact records that completion, so a regression in the
model-facing route cannot pass silently.

The runner is skipped, not failed, when the Pi CLI is absent: the package tests
already cover the same contract without a host binary.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
RUNNER = REPO / "tests" / "e2e" / "matt_pocock_grill_me.py"
ARTIFACT = REPO / "tests" / "e2e" / "matt-pocock-grill-me-results.json"

pytestmark = pytest.mark.skipif(
    shutil.which("pi") is None, reason="the E2E layer requires the Pi CLI"
)


def test_grill_me_completes_through_both_entry_points(tmp_path: Path) -> None:
    """Given the real Pi CLI, grill-me completes from the menu and from the model."""
    output = tmp_path / "result.json"
    result = subprocess.run(
        [sys.executable, str(RUNNER), "--output", str(output)],
        cwd=REPO, text=True, capture_output=True, timeout=300,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(output.read_text())
    assert report["status"] == "completed", report
    assert report["capability"] == "grill-me"
    cases = {case["entryPoint"]: case for case in report["cases"]}
    assert set(cases) == {"menu", "model-gateway"}, report
    for entry_point, case in cases.items():
        assert case["status"] == "completed", (entry_point, case)
        # The eager dependency closure must arrive, not just the root body.
        assert case["deliveredSources"] == ["grill-me", "grilling"], (entry_point, case)
    # The model route must not widen autonomous use: capability mode still refuses it.
    assert cases["model-gateway"]["mode"] == "user-capability"
    assert cases["model-gateway"]["autonomousModeRefused"] is True


def test_the_committed_result_artifact_records_completion() -> None:
    """Given the recorded artifact, every case is completed rather than pending."""
    report = json.loads(ARTIFACT.read_text())
    assert report["status"] == "completed", report
    assert report["cases"], report
    for case in report["cases"]:
        assert case["status"] == "completed", case
        assert case["status"] != "pending", case
        assert case["deliveredSources"] == ["grill-me", "grilling"], case