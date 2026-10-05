from __future__ import annotations

import builtins
import os
from pathlib import Path
import subprocess
import sys

import pytest

from live_upgrade_smoke import assert_expected_tool_results


TESTS = Path(__file__).parent
REPO = TESTS.parents[2]


def test_live_upgrade_smoke_import_does_not_require_pytest() -> None:
    script = """
import builtins
import runpy

real_import = builtins.__import__

def reject_pytest(name, *args, **kwargs):
    if name == "pytest" or name.startswith("pytest."):
        raise ModuleNotFoundError("pytest intentionally unavailable")
    return real_import(name, *args, **kwargs)

builtins.__import__ = reject_pytest
runpy.run_path("packages/continual-learning/tests/live_upgrade_smoke.py", run_name="live_upgrade_smoke")
"""
    env = {**os.environ, "PYTHONPATH": str(TESTS)}
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr


def test_live_upgrade_smoke_rejects_extra_native_tool_result() -> None:
    results = [
        {"toolName": "bash"},
        {"toolName": "write"},
        {"toolName": "edit"},
        {"toolName": "write"},
        {"toolName": "read"},
    ]
    with pytest.raises(AssertionError):
        assert_expected_tool_results(results)
