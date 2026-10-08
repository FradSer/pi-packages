"""Real-run harnesses retain compatibility with the Pi 1.0 baseline."""
from types import SimpleNamespace

import pi_cli


def test_pi_10_does_not_receive_newer_optional_flags(monkeypatch) -> None:
    monkeypatch.setattr(pi_cli.shutil, "which", lambda _name: "/bin/pi")
    monkeypatch.setattr(pi_cli.subprocess, "run", lambda *_args, **_kwargs: SimpleNamespace(stdout="--no-extensions"))
    assert pi_cli.isolated_pi_command() == ["/bin/pi"]


def test_newer_pi_disables_mcp_when_supported(monkeypatch) -> None:
    monkeypatch.setattr(pi_cli.shutil, "which", lambda _name: "/bin/pi")
    monkeypatch.setattr(pi_cli.subprocess, "run", lambda *_args, **_kwargs: SimpleNamespace(stdout="--no-extensions --no-mcp"))
    assert pi_cli.isolated_pi_command() == ["/bin/pi", "--no-mcp"]
