"""Native evidence must come from the pinned cohort and an isolated parent."""
from __future__ import annotations

import secrets
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from subagents_helpers import REPO
from native_support import native_command


def test_native_parent_does_not_inherit_credentials_or_startup_hooks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    ambient = ("OPENAI_API_KEY", "AWS_SECRET_ACCESS_KEY", "NODE_OPTIONS", "HTTPS_PROXY", "XDG_CONFIG_HOME")
    for name in ambient:
        monkeypatch.setenv(name, secrets.token_hex(16))
    fixture = native_command.__wrapped__(tmp_path, SimpleNamespace())
    try:
        _, env, _, _, _ = next(fixture)
        inherited_names = sorted(set(ambient) & set(env))
        assert inherited_names == []
        assert env["HOME"] == str(tmp_path)
        assert env["PI_CODING_AGENT_DIR"] == str(tmp_path / "agent")
    finally:
        fixture.close()


def test_native_parent_uses_repository_pi_when_global_pi_differs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(shutil, "which", lambda _name: "/fixture-global-pi")
    fixture = native_command.__wrapped__(tmp_path, SimpleNamespace())
    try:
        command, _, _, _, _ = next(fixture)
        assert command[0] == str(REPO / "node_modules" / ".bin" / "pi")
    finally:
        fixture.close()
