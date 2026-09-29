"""Keep the package test suite hermetic.

Judgment is opt-in and activated by ``TYPESAFE_API_KEY`` in the environment. An
earlier increment wired it into the selector, and because a contributor who has
configured the feature also has the key set, ``pytest`` silently made live billed
calls to the decision service and wrote observation logs into the caller's real
``~/.pi/agent``. Six such scopes accumulated before this was noticed.

The suite must not depend on whether the person running it has configured a
credential, and it must not spend money or touch real state. Stripping the
variables here is the same separation the live scripts already draw:
``live_smoke.py`` and ``live_judgment_e2e.ts`` are explicit, never collected, and
are the only places a live call belongs.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

JUDGMENT_ENV_VARS = ("TYPESAFE_API_KEY", "TYPESAFE_MODEL", "TYPESAFE_BASE_URL")


def _real_judgment_scopes() -> set[str]:
    """Scopes under the caller's *real* agent directory, if it has one."""
    agent_dir = Path(os.environ.get("REAL_PI_CODING_AGENT_DIR") or (Path.home() / ".pi" / "agent"))
    judgment = agent_dir / "judgment"
    return {entry.name for entry in judgment.iterdir()} if judgment.is_dir() else set()


@pytest.fixture(autouse=True, scope="session")
def _judgment_is_unconfigured_for_the_suite() -> None:
    saved = {name: os.environ.pop(name, None) for name in JUDGMENT_ENV_VARS}
    before = _real_judgment_scopes()
    try:
        yield
    finally:
        for name, value in saved.items():
            if value is not None:
                os.environ[name] = value
        added = _real_judgment_scopes() - before
        assert not added, (
            f"The suite added Judgment scopes to the real agent directory: {sorted(added)}. "
            "A test resolved the caller's PI_CODING_AGENT_DIR instead of an isolated one. "
            "Use isolated_run_bun rather than run_bun for anything that reaches the agent directory."
        )


def test_the_suite_cannot_reach_the_decision_service() -> None:
    for name in JUDGMENT_ENV_VARS:
        assert name not in os.environ, (
            f"{name} is set during the test suite; a unit test could make a live billed call. "
            "The conftest strips it for the whole session."
        )
