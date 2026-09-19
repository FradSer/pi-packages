"""Per-test isolation for the harness runtime and board directories.

The runtime dir is keyed by the session key, a hash of the session file or the
working directory, and pytest reuses a test's `tmp_path` across runs. A leftover
outbox would then be replayed into a fresh run: `resetState()` clears the
in-memory replay offsets, so every synthetic event id from an earlier run is
re-read and deduplicated as if it had already been applied, silently suppressing
the current run's reports. A leftover board is the same hazard for persisted Work
and archived snapshots (a run that asserts one archive would find two). Every
test therefore starts from a clean runtime dir and board dir.
"""

from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path

import pytest


def _agents_root() -> Path:
    configured = os.environ.get("PI_CODING_AGENT_DIR")
    return Path(configured) if configured else Path.home() / ".pi" / "agent"


def _runtime_dir_for(cwd: Path) -> Path:
    return _agents_root() / "teammate" / hashlib.sha256(str(cwd).encode()).hexdigest()[:16]


def _board_dir_for(cwd: Path) -> Path:
    return _agents_root() / "tasks" / hashlib.sha256(str(cwd).encode()).hexdigest()[:16]


@pytest.fixture(autouse=True)
def isolated_harness_runtime(tmp_path: Path) -> None:
    # A test that redirects HOME keeps its runtime dir under its own tmp_path.
    targets = [_runtime_dir_for(tmp_path), _board_dir_for(tmp_path), tmp_path / ".pi" / "agent"]
    for target in targets:
        shutil.rmtree(target, ignore_errors=True)
    yield
    for target in targets:
        shutil.rmtree(target, ignore_errors=True)