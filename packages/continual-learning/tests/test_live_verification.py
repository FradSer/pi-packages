from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import live_smoke


def test_live_prepare_isolates_authentication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source-agent"
    source.mkdir()
    original = {
        "auth.json": json.dumps({"synthetic": {"type": "api_key", "key": "synthetic-source-only"}}),
        "models.json": json.dumps({"providers": {"synthetic": {"models": []}}}),
        "memory.json": json.dumps({"provider": "synthetic", "model": "fixture"}),
    }
    for name, content in original.items():
        (source / name).write_text(content)
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(source))
    base = tmp_path / "live"
    base.mkdir()

    _, agent, _ = live_smoke.prepare(base, False)

    for name in ("auth.json", "models.json"):
        child_file = agent / name
        assert not child_file.is_symlink(), f"{name} must not link writable source configuration"
        assert child_file.stat().st_mode & 0o777 == 0o600
        assert child_file.read_text() == original[name]
    (agent / "auth.json").write_text('{"syntheticRefresh":true}')
    assert {name: (source / name).read_text() for name in original} == original


def test_live_learning_requires_actual_project_rule(monkeypatch: pytest.MonkeyPatch) -> None:
    def prepare(base: Path, auto_memory: bool) -> tuple[Path, Path, Path]:
        project, agent = base / "project", base / "agent"
        project.mkdir()
        memory = agent / "memory" / "scope"
        memory.mkdir(parents=True)
        (memory / "preference.md").write_text("Prefer concise updates.")
        runs = agent / "memory" / "runs" / "scope" / "run"
        runs.mkdir(parents=True)
        (runs / "learning-pipeline-receipt.json").write_text(json.dumps({
            "operations": 2,
            "attempts": [
                {"phase": "memory", "outcome": "applied", "operations": 1},
                {"phase": "harness", "outcome": "rejected", "operations": 0},
            ],
        }))
        return project, agent, base / "unused.ts"

    monkeypatch.setattr(live_smoke, "prepare", prepare)
    monkeypatch.setattr(live_smoke, "run_pi", lambda *args: {"notifications": "synthetic missing-rule diagnosis"})
    monkeypatch.setattr(live_smoke.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(stdout='{"blocked":"block","allowed":true}'))
    with pytest.raises(AssertionError, match="project harness"):
        live_smoke.verify_learning()
