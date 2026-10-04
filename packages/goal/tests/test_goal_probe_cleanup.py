"""Bounded cleanup for isolated E2E processes."""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time

from goal_native_tui import terminate_fixture


def test_cleanup_reaps_a_child_that_ignores_sigterm() -> None:
    child = subprocess.Popen(
        [sys.executable, "-c", "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); print('ready', flush=True); time.sleep(60)"],
        stdout=subprocess.PIPE, text=True, start_new_session=True,
    )
    try:
        assert child.stdout is not None
        assert child.stdout.readline().strip() == "ready"
        start = time.monotonic()
        terminate_fixture(child, grace_seconds=0.1)
        assert child.returncode == -signal.SIGKILL
        assert time.monotonic() - start < 3
        terminate_fixture(child, grace_seconds=0.1)
    finally:
        if child.poll() is None:
            os.killpg(child.pid, signal.SIGKILL)
            child.wait(timeout=3)
        if child.stdout is not None:
            child.stdout.close()
