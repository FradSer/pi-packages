"""Test support for @fradser/pi-subagents.

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


def run_isolated_node(script: str, *, env_overrides: dict[str, str] | None = None,
                      module_mocks: bool = False) -> dict[str, object]:
    """Run a scenario with a private HOME, Pi directory and project root."""
    with tempfile.TemporaryDirectory(prefix="subagents-test-") as directory:
        root = Path(directory)
        return run_node(script, module_mocks=module_mocks, env_overrides={
            "HOME": directory, "PI_CODING_AGENT_DIR": str(root / "agent"),
            "PI_TEST_CWD": directory, "XDG_CONFIG_HOME": str(root / "config"),
            "XDG_CACHE_HOME": str(root / "cache"), **(env_overrides or {}),
        })


def run_node(
    script: str,
    *args: str,
    env_overrides: dict[str, str] | None = None,
    module_mocks: bool = False,
) -> dict[str, object]:
    """Run an inline ES module against the package source and parse its last
    stdout line as JSON.

    `PI_TEAMMATE_*` is stripped so a coordination binding left over in the
    developer's shell cannot make a spawned child believe it is an agent.
    `module_mocks` enables node's module mocking, for the cases where the seam
    under test is the real spawn and only the child process is faked.
    """
    env = {key: value for key, value in os.environ.items() if not key.startswith("PI_TEAMMATE_")}
    env.update(env_overrides or {})
    result = subprocess.run(
        [
            "node",
            *(["--experimental-test-module-mocks"] if module_mocks else []),
            "--input-type=module",
            "--eval",
            textwrap.dedent(script),
            *args,
        ],
        cwd=PACKAGE,
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    return json.loads(result.stdout)
