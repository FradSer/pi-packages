"""Shared helpers for the pi-continual-learning test suite.

Every contract check runs a Bun snippet against the package's TypeScript
extensions. This module owns the one subprocess harness so individual test
files only declare the scenario, not the plumbing.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from functools import partial
from pathlib import Path
from typing import Literal, TypeAlias, overload

JSONValue: TypeAlias = str | int | float | bool | None | list["JSONValue"] | dict[str, "JSONValue"]

PKG_DIR = Path(__file__).resolve().parents[1]
REPO = PKG_DIR.parents[1]
PKG_REL = "packages/continual-learning"
EXTENSIONS = f"./{PKG_REL}/extensions"
ENGINE = f"{EXTENSIONS}/guardrail-engine.ts"
CONSOLIDATION = f"{EXTENSIONS}/harness-consolidation.ts"

_TIMEOUT_SECONDS = 120


@overload
def run_bun(
    source: str,
    env: dict[str, str] | None = None,
    *,
    timeout: int = _TIMEOUT_SECONDS,
    temp_dirs: tuple[str, ...] = (),
    parse: Literal[True] = True,
) -> JSONValue: ...


@overload
def run_bun(
    source: str,
    env: dict[str, str] | None = None,
    *,
    timeout: int = _TIMEOUT_SECONDS,
    temp_dirs: tuple[str, ...] = (),
    parse: Literal[False],
) -> subprocess.CompletedProcess[str]: ...


@overload
def run_bun(
    source: str,
    env: dict[str, str] | None = None,
    *,
    timeout: int = _TIMEOUT_SECONDS,
    temp_dirs: tuple[str, ...] = (),
    parse: bool,
) -> JSONValue | subprocess.CompletedProcess[str]: ...


def run_bun(
    source: str,
    env: dict[str, str] | None = None,
    *,
    timeout: int = _TIMEOUT_SECONDS,
    temp_dirs: tuple[str, ...] = (),
    parse: bool = True,
) -> JSONValue | subprocess.CompletedProcess[str]:
    """Run ``bun -e source`` from the repository root.

    ``temp_dirs`` names environment variables that receive a fresh temporary
    directory for the run, overriding any inherited value. With ``parse`` the
    final stdout line is decoded as JSON; otherwise the raw
    ``CompletedProcess`` is returned for the caller to inspect.
    """
    with tempfile.TemporaryDirectory(prefix="cl-bun-") as temporary:
        result = subprocess.run(
            ["bun", "-e", source],
            cwd=REPO,
            env=_merged_env(env, temp_dirs, temporary),
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    if not parse:
        return result
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


def run_bun_script(
    script: Path,
    *args: str,
    env: dict[str, str] | None = None,
    timeout: int = _TIMEOUT_SECONDS,
    temp_dirs: tuple[str, ...] = (),
) -> JSONValue:
    """Run a checked-in Bun harness script and decode its final JSON line."""
    with tempfile.TemporaryDirectory(prefix="cl-bun-") as temporary:
        result = subprocess.run(
            ["bun", str(script), *args],
            cwd=REPO,
            env=_merged_env(env, temp_dirs, temporary),
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


def _merged_env(
    env: dict[str, str] | None,
    temp_dirs: tuple[str, ...],
    temporary: str,
) -> dict[str, str]:
    merged = {**os.environ, **(env or {})}
    for name in temp_dirs:
        merged[name] = tempfile.mkdtemp(dir=temporary)
    return merged


# Runs with an isolated agent directory, so snippets that resolve config paths
# never read or write the caller's real ``~/.pi/agent``.
isolated_run_bun = partial(run_bun, temp_dirs=("PI_CODING_AGENT_DIR",))


def initialize_git_repo(path: Path, *, identity: bool = False) -> None:
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    if identity:
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)


# Shared flat-harness fixtures (guardrail-engine / harness-consolidation).

def rule(id: str = "learned") -> dict:
    return {"id": id, "bash": "^dangerous-fixture$", "action": "block", "message": "Use the safe fixture."}


def cases() -> dict:
    return {"positive": [{"bash": "dangerous-fixture", "expected": "block"}], "negative": [{"bash": "safe-fixture"}]}


def snapshot() -> dict:
    return {"entries": [{"message": {"role": "user", "content": "Block dangerous-fixture; use the safe fixture."}}]}


def evidence() -> list[dict]:
    return [{"index": 0, "source": "user", "quote": snapshot()["entries"][0]["message"]["content"], "count": 1}]