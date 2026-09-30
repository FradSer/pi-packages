"""Keep the package test suite hermetic.

The suite must not depend on whether the person running it has a provider
credential configured, must not spend money, and must not touch real state. Every
outbound call in this package's verification goes through an explicit live script
that is never collected; everything pytest runs is a loopback endpoint or a
fixture.

An earlier increment proved this was not automatic: a feature activated by an
environment variable made ``pytest`` silently issue live billed calls and write
into the caller's real ``~/.pi/agent`` for anyone who had that variable set.
"""

from __future__ import annotations

import os

import pytest

# Any variable that could make a collected test reach a real provider.
PROVIDER_ENV_VARS = ("TYPESAFE_API_KEY", "TYPESAFE_MODEL", "TYPESAFE_BASE_URL")


@pytest.fixture(autouse=True, scope="session")
def _no_provider_credentials_during_the_suite() -> None:
    saved = {name: os.environ.pop(name, None) for name in PROVIDER_ENV_VARS}
    try:
        yield
    finally:
        for name, value in saved.items():
            if value is not None:
                os.environ[name] = value


def test_the_suite_cannot_reach_a_live_provider() -> None:
    for name in PROVIDER_ENV_VARS:
        assert name not in os.environ, (
            f"{name} is set during the test suite; a unit test could make a live billed "
            "call. The conftest strips it for the whole session."
        )