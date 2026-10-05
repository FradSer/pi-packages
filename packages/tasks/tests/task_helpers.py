"""Test support for @fradser/pi-tasks.

Mirrors the helper shape the agent-teams suite uses so a test moving between the
two packages during the split keeps reading the same way.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import textwrap
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
REPO = PACKAGE.parents[1]
SRC = PACKAGE / "src"


def source(name: str) -> str:
    return (SRC / name).read_text(encoding="utf-8")


def run_node(
    script: str,
    *args: str,
    env_overrides: dict[str, str] | None = None,
) -> dict[str, object]:
    """Run an inline module and read its one JSON result.

    Use a temporary agent directory when the test does not supply one. Remove
    inherited holder bindings so the shell cannot change the caller's identity.
    """
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("PI_TEAMMATE_")
        and key not in {"PI_TASK_HOLDER", "PI_TEAM_STATE_DIR"}
    }
    with tempfile.TemporaryDirectory(prefix="tasks-test-agent-") as agent_dir:
        env["PI_CODING_AGENT_DIR"] = agent_dir
        env.update(env_overrides or {})
        result = subprocess.run(
            ["node", "--input-type=module", "--eval", textwrap.dedent(script), *args],
            cwd=PACKAGE,
            check=False,
            capture_output=True,
            text=True,
            env=env,
            timeout=60,
        )
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    return json.loads(result.stdout)
