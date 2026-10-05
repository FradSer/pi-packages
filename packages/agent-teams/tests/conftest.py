"""Per-test isolation for the harness runtime and tasks directories.

The runtime dir is keyed by the session key, a hash of the session file or the
working directory, and pytest reuses a test's `tmp_path` across runs. A leftover
outbox would then be replayed into a fresh run: `resetState()` clears the
in-memory replay offsets, so every synthetic event id from an earlier run is
re-read and deduplicated as if it had already been applied, silently suppressing
the current run's reports. A leftover tasks is the same hazard for persisted Work
and archived snapshots (a run that asserts one archive would find two). Every
test therefore starts from a clean runtime dir and tasks dir.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_harness_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Isolation must precede imports and subprocesses, not merely clean one hash
    # under the real user config. Each test owns its HOME and Pi data root.
    home = tmp_path / "home"
    config = tmp_path / "agent-config"
    home.mkdir()
    config.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(config))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(home / ".cache"))
    monkeypatch.setenv("XDG_STATE_HOME", str(home / ".local" / "state"))
    monkeypatch.setenv("XDG_DATA_HOME", str(home / ".local" / "share"))
    for key in tuple(os.environ):
        if key.startswith(("PI_TEAMMATE_", "PI_SUBAGENT_", "LIVE_AGENT_")):
            monkeypatch.delenv(key)
    monkeypatch.setenv("PI_OFFLINE", "1")