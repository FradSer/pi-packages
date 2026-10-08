"""Native offline TUI probe. Run explicitly; it uses a fresh project and agent dir."""
from __future__ import annotations

import os
import signal
import subprocess


def terminate_fixture(child: subprocess.Popen, grace_seconds: float = 2.0) -> None:
    """Stop only the isolated process group created by this probe, then reap it."""
    if child.poll() is not None:
        return
    try:
        os.killpg(child.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        child.wait(timeout=grace_seconds)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        child.wait(timeout=3)


def main() -> None:
    from goal_native_completion import main as run_native_acceptance
    run_native_acceptance()


if __name__ == "__main__":
    main()
